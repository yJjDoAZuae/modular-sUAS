
# Write a collection of python functions to perform parametric analysis for a design tool. The functions will read an array of properties from the rows of each of N csv files that represent N independent axes of parametric variation, then flattens the parametric iteration into a single axis table of parameter values that will be iterated over, with an example call to a library function using the iterated parameters from the csv files. The library call will produces an output data object that these functions will save to a uniquely named file generated from the parameter values used for that iteration.

# Got it — you want a Python toolkit that:
# 1. Reads N CSV files — each one representing a set of values for a single independent parameter axis.
# 2. Produces a full factorial combination (Cartesian product) of all parameter values.
# 3. Iterates through that flattened list, calling a library function for each combination.
# 4. Saves the resulting object to a uniquely named file derived from the parameter values.

import pandas as pd
import itertools
import math
import os
import re
from pathlib import Path
import json  # example for saving results

import solid2
import subprocess
import argparse
import concurrent.futures
import contextlib
import filecmp
import sys
import time
from dataclasses import dataclass, field, fields
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry_version
import mesh_stats
import stl_preview
# Aliased: `freecad_render` is also the name of the render function below, and the module is
# what the backend switch consults for which kinds are ported.
import freecad_render as freecad_render_backend

# Every path below is anchored to this file, not to the working directory, so
# the sweeps produce the same result whether they are run from the Fuselage
# root, from tools/, or from anywhere else.
_HERE = os.path.dirname(os.path.abspath(__file__))      # .../Fuselage/tools
_ROOT = os.path.dirname(_HERE)                          # .../Fuselage

# The CSVs are axes of parametric variation and stay at the Fuselage root.
PARAM_DIR = os.path.join(_ROOT, "variant_param")

# The cowl JSONs are not variation parameters -- each one is a named shape
# definition that a row of a *_type_variants.csv refers to by filename -- so
# they travel with the scripts that interpret them.
COWL_DIR = _HERE

# The unvaried parameters, at the Fuselage root beside the axes rather than in
# variant_param/ with them. It is deliberately NOT in that directory: everything
# there is an axis, read by read_all_param_axes() and combined factorially, and a
# settings file sitting among them invites exactly the mistake of adding it to an
# axis list -- where each constant would become a swept dimension.
CONSTANTS_FILE = os.path.join(_ROOT, "design_constants.json")

# Insert dimensions are a fixed reference table, likewise beside the scripts.
INSERT_TABLE = os.path.join(_HERE, "threaded_insert_dimensions.csv")

# Sweep output, at the Fuselage root alongside the parameter axes.
OUTPUT_DIR = os.path.join(_ROOT, "variant_output")

# The OpenSCAD geometry modules. import_scad() resolves a bare filename against
# the working directory, so once these moved into scad/ the sweeps could only
# run from inside that one directory -- and not from tools/, where this script
# lives. Anchoring the lookup here makes the working directory irrelevant.
SCAD_DIR = os.path.join(_ROOT, "scad")


def scad_module(name):
    """Load an OpenSCAD geometry module by name, wherever the caller stands."""
    return solid2.import_scad(os.path.join(SCAD_DIR, name), use_not_include=True)


def oml_ref(filename):
    """An OML mesh named the way cowl_geometry.scad will resolve it.

    The `import()` call lives in scad/cowl_geometry.scad, and OpenSCAD resolves
    import() against the file containing the call -- not the root document and
    not the working directory. So the reference hops up out of scad/ and into
    oml/, where the meshes now live. Verified against OpenSCAD 2021.01 with a
    fixture: a module in scad/ importing "../oml/x.stl", invoked from a root
    document in a third directory, resolves correctly.

    Kept relative rather than absolute on purpose: an absolute path is what put
    a long-dead `R:\\` drive mapping into every file the 2025-09-22 sweep wrote.
    """
    return '../oml/' + filename.replace('\\', '/').lstrip('/')


# ------------------------------------------------------------
# Example "library function" to simulate your design tool call
# ------------------------------------------------------------
def example_design_tool(**params):
    """
    Simulates a library function call for the design tool.
    Replace this with your actual library call.
    """
    # Pretend the output is a dict with results
    result = {
        "input_parameters": params,
        "output_metric": sum(v for v in params.values() if isinstance(v, (int, float)))
    }
    return result

# The unvaried parameters are data, in design_constants.json, not literals here.
#
# **Membership is decided by measurement, not by category.** A parameter belongs in that
# file when the sweep passes it to the geometry and its value is the same on every variant
# -- established by resolving the `Parameters` tree for all three families and collecting
# what each numeric field actually takes. That is how `boom_tolerance` and
# `cowl_flange_tolerance` were found: neither sits near the others in the source, and
# neither is named like a setting at its definition site. Reading the file and picking out
# what looks like configuration finds the ones that are already tidy and misses the rest.
#
# They were literals until 2026-08-14, and only two -- longeron and greeble -- were even
# reviewable constants. The other eight were bare numbers inside `derived_parameters()`, or
# in `extrusion_width`'s case the same literal restated seven times across three files. So
# the set a builder would adjust together could not be seen together.
#
# The names below are this module's interface and have not changed; only where the number
# comes from has. Each is also exactly the name of the corresponding OpenSCAD parameter,
# which is what the JSON keys are, so there is one vocabulary from the settings file to the
# geometry module.
#
# Units are millimeters and degrees: this is the OpenSCAD path, which is exempt from the
# project's SI standard. See doc/guidelines/openscad.md.
#
# Loaded once at import. A sweep must not be able to change a constant halfway through.
#
# The groups are not decoration -- each carries a different rule about what a legal value
# is, which is the whole reason they are separate rather than one flat table.
CONSTANT_GROUPS = {
    'tolerances': ('longeron_tolerance', 'greeble_tolerance', 'corner_tolerance',
                   'panel_tolerance', 'boom_tolerance', 'cowl_flange_tolerance'),
    'geometry': ('greeble_opening_angle', 'boom_key_angle'),
    'printer': ('extrusion_width', 'layer_height'),
}


def _check_tolerance(name, value, path):
    # These are clearances between parts that are bonded, not press fits, so a negative is
    # a sign error. Relaxing it is a deliberate design decision, not something to slip past
    # a loader.
    if value < 0:
        raise ValueError('%s: %s is %g. A negative clearance is an interference fit, and '
                         'none of these joints is one.' % (path, name, value))


def _check_printer(name, value, path):
    # Zero is as wrong as negative here: a zero extrusion width silently collapses every
    # feature sized in whole multiples of it -- the greeble wall, both flanges -- rather
    # than failing.
    if value <= 0:
        raise ValueError('%s: %s is %g, and a printer dimension must be positive.'
                         % (path, name, value))


# Angles are unconstrained on purpose: a negative boom_key_angle is a legal rotation.
_GROUP_RULES = {'tolerances': _check_tolerance, 'printer': _check_printer}


def load_constants(path=None):
    """The unvaried parameters, read from `design_constants.json`.

    **Every name is required and no other name is accepted.** A settings file that silently
    tolerates a missing key hands back a default, and the sweep then builds every part at a
    value nobody chose while reporting success -- the same failure `check_unseeded` exists
    to prevent on the FreeCAD side, one layer further out. An unrecognized key is refused
    for the mirror reason: it is almost always a misspelling of one that matters, and
    accepting it means the edit appears to have been made.

    Returns one flat dict. The groups exist in the file to carry the per-group validity
    rule and to keep it readable; nothing downstream needs to know which group a name is
    in, and `merge_params`-style collisions cannot arise because the names are checked
    unique across the whole file.
    """
    path = path or CONSTANTS_FILE
    with open(path, encoding='utf-8') as f:
        doc = json.load(f)

    out = {}
    problems = []
    for group, names in CONSTANT_GROUPS.items():
        table = doc.get(group)
        if not isinstance(table, dict):
            problems.append('  %s: missing or not an object' % group)
            continue
        # `_about` is prose for whoever opens the file, not a parameter.
        supplied = [k for k in sorted(table) if not k.startswith('_')]
        missing = [n for n in names if n not in supplied]
        unknown = [n for n in supplied if n not in names]
        if missing:
            problems.append('  %s missing: %s' % (group, ', '.join(missing)))
        if unknown:
            problems.append('  %s unknown: %s' % (group, ', '.join(unknown)))

        for name in names:
            if name not in table:
                continue
            entry = table[name]
            value = entry['value'] if isinstance(entry, dict) else entry
            try:
                value = float(value)
            except (TypeError, ValueError):
                problems.append('  %s.%s is %r, which is not a number'
                                % (group, name, value))
                continue
            rule = _GROUP_RULES.get(group)
            if rule:
                rule(name, value, path)
            out[name] = value

    if problems:
        raise ValueError('%s does not define the constant set:\n%s'
                         % (path, '\n'.join(problems)))
    return out


_CONSTANTS = load_constants()

LONGERON_TOLERANCE_MM = _CONSTANTS['longeron_tolerance']
GREEBLE_TOLERANCE_CORNER_MM = _CONSTANTS['greeble_tolerance']
CORNER_TOLERANCE_MM = _CONSTANTS['corner_tolerance']
PANEL_TOLERANCE_MM = _CONSTANTS['panel_tolerance']
BOOM_TOLERANCE_MM = _CONSTANTS['boom_tolerance']
COWL_FLANGE_TOLERANCE_MM = _CONSTANTS['cowl_flange_tolerance']

GREEBLE_OPENING_ANGLE_DEG = _CONSTANTS['greeble_opening_angle']
BOOM_KEY_ANGLE_DEG = _CONSTANTS['boom_key_angle']

EXTRUSION_WIDTH_MM = _CONSTANTS['extrusion_width']
LAYER_HEIGHT_MM = _CONSTANTS['layer_height']


def greeble_nub_thickness_of(greeble_thickness):
    """Wall thickness of the snap rib, derived from the greeble's seat wall.

    The two are **not independent parameters** -- there is one wall thickness and a
    formula relating the rib to it. Identity today, because a rib the same thickness as
    the wall it stands on is what has been printed and assembled at both ends of the
    swept range (U=0.5 and U=4; see OQ-DES-B4 and OQ-DES-B7 in doc/design/bulkhead.md).

    It is written as a formula rather than collapsed into a single value on purpose: if
    scale problems turn up and the rib needs to be thicker or thinner than the seat,
    the fix belongs here, in one place. Reintroducing a second independent parameter
    would let the rib and its mating groove drift apart silently -- and they are the two
    halves of a snap fit, so drift means parts that do not assemble.

    Authoritative here rather than in OpenSCAD (OQ-DES-C1). The geometry modules take
    both values as arguments and never derive either, so Python is the only place the
    relationship is stated -- and it is the side that survives the FreeCAD port.
    """
    return greeble_thickness


def standard_values():
    
    c = dict()
    
    c["unit_width"] = 100
    c["unit_length"] = 100
    c["corner_radius"] = 10
    c["longeron_radius"] = 2
    c["bolt_offset"] = 8

    return c

class BulkheadType(Enum):
    NULL         = 0
    END          = 1
    INTERCONNECT = 2
    COWLING      = 3
    TAIL_BOOM    = 4


# ------------------------------------------------------------
# Parameter groups
# ------------------------------------------------------------
# Each group is a dataclass rather than a dict. The difference that matters is
# assignment: a dict accepts `c["greeble"]["thicknes"] = 1.2` in silence, adding
# a new key while the real field keeps its default, so the part comes out wrong
# by exactly the amount the assignment was meant to change. Reads were already
# safe -- a dict raises KeyError -- so this closes the half that was open.
#
# `slots=True` is what actually closes it, and it is not optional. A PLAIN
# dataclass accepts `c.greeble.thicknes = 1.2` just as silently as the dict did:
# instances carry a __dict__ and Python is happy to add an attribute to it. Only
# __slots__ removes that __dict__ and turns the typo into an AttributeError at
# the line that made it.
#
# This was found the hard way. IP-GEO-24 renamed nozzle_diameter to
# extrusion_width; a verification script still assigning the old name kept
# working, silently left extrusion_width at its default, and reported bulkheads
# 13-30% off in volume -- the exact failure the dataclasses were introduced to
# prevent, reproduced by the dataclasses because slots had been left off.
#
# Every field default is the value the corresponding null_*_parameters()
# constructor used to assign a line at a time, and those constructors remain as
# the named way to obtain a zeroed group.
#
# This is deliberately on the Python side. OQ-GEO-1 in
# doc/implementation/geometry_refactor.md weighed grouping these in OpenSCAD
# instead and rejected it: the groups already exist here, they are flattened
# only to cross into SCAD, and FreeCAD is driven from Python -- so structure
# built here survives the Phase 3 port and an OpenSCAD vector encoding does not.


@dataclass(slots=True)
class PrinterSettings:
    # From design_constants.json, not literals. The default used to be 0.4 -- the hand
    # drivers' nozzle -- and every one of the seven places that built a PrinterSettings for
    # the sweep immediately overrode it to 0.6 on the next line. Seven copies of one machine
    # setting, and changing six of them would have produced a run built at two nozzle sizes
    # with nothing to say so: the parts differ only in wall thickness, which a volume
    # comparison passes. `layer_height` was never overridden anywhere, so the two halves of
    # one profile were configured in opposite ways.
    extrusion_width: float = EXTRUSION_WIDTH_MM
    layer_height: float = LAYER_HEIGHT_MM


@dataclass(slots=True)
class CornerParameters:
    FX: float = 1
    radius: float = 0
    length: float = 0
    # Clearance on the two faces that seat against the bulkhead -- the flat at flat_x and the
    # diagonal -- over the corner's full height. Carried entirely on the corner: the bulkhead
    # cuts its socket from the same shape at 0, so the joint takes the clearance once. Held at
    # 0 for the sweep until a print says otherwise; 0 is the only value that has flown.
    # OQ-DES-C5.
    tolerance: float = CORNER_TOLERANCE_MM


@dataclass(slots=True)
class BulkheadParameters:
    U: float = 1
    width: float = 0
    thickness: float = 0
    type: BulkheadType = BulkheadType.NULL
    type_name: str = ""


@dataclass(slots=True)
class BoomBulkheadParameters:
    diameter: float = 0
    thickness: float = 0
    y_position: float = 0
    z_position: float = 0
    collet_thickness: float = 0
    key_width: float = 0
    key_height: float = 0
    key_radius: float = 0
    key_web_width: float = 0
    key_angle: float = 0
    tolerance: float = 0
    type_name: str = ""
    make_vert_web: bool = False
    make_lower_web: bool = False


@dataclass(slots=True)
class PanelParameters:
    thickness: float = 0
    offset: float = 0
    overlap: float = 0
    tolerance: float = 0
    type_name: str = ""
    is_metric: bool = True


@dataclass(slots=True)
class LongeronParameters:
    radius: float = 0
    tolerance: float = 0


@dataclass(slots=True)
class BoltParameters:
    radius: float = 0
    thickness: float = 0
    offset: float = 0
    is_anchor: bool = False
    # Declared here for the first time. derived_parameters() has always assigned
    # and read it, but null_bolt_parameters() never listed it -- the dict simply
    # accepted the new key. It is the nominal bolt size from the variant table;
    # `radius` is derived from it and differs for an anchor.
    diameter: float = 0


@dataclass(slots=True)
class GreebleParameters:
    opening_angle: float = 0
    tolerance: float = 0
    thickness: float = 0
    # Derived from `thickness`, never set independently -- see
    # greeble_nub_thickness_of(). The two are one wall thickness and a formula, not two
    # parameters: they are the mating halves of a snap fit, so letting them drift apart
    # produces parts that do not assemble.
    nub_thickness: float = 0


@dataclass(slots=True)
class PlateParameters:
    """The bulkhead's plate. NosePlateParameters is the different one."""
    thickness: float = 0


@dataclass(slots=True)
class WebParameters:
    fillet_radius: float = 0
    width: float = 0


@dataclass(slots=True)
class BulkheadFlangeParameters:
    fillet_radius: float = 0
    thickness: float = 0
    chamfer: float = 0


@dataclass(slots=True)
class CowlFlangeParameters:
    height: float = 0
    tolerance: float = 0


@dataclass(slots=True)
class Parameters:
    """Everything the bulkhead and corner geometry modules are driven from."""
    corner: CornerParameters = field(default_factory=CornerParameters)
    bulkhead: BulkheadParameters = field(default_factory=BulkheadParameters)
    boom_bulkhead: BoomBulkheadParameters = field(
        default_factory=BoomBulkheadParameters)
    panel: PanelParameters = field(default_factory=PanelParameters)
    longeron: LongeronParameters = field(default_factory=LongeronParameters)
    bolt: BoltParameters = field(default_factory=BoltParameters)
    greeble: GreebleParameters = field(default_factory=GreebleParameters)
    plate: PlateParameters = field(default_factory=PlateParameters)
    web: WebParameters = field(default_factory=WebParameters)
    bulkhead_flange: BulkheadFlangeParameters = field(
        default_factory=BulkheadFlangeParameters)
    cowl_flange: CowlFlangeParameters = field(default_factory=CowlFlangeParameters)
    printer: PrinterSettings = field(default_factory=PrinterSettings)


def null_printer_settings():
    return PrinterSettings()

def null_parameters():
    return Parameters()

def null_corner_parameters():
    return CornerParameters()

def null_bulkhead_parameters():
    return BulkheadParameters()

def null_boom_bulkhead_parameters():
    return BoomBulkheadParameters()

def null_panel_parameters():
    return PanelParameters()

def null_longeron_parameters():
    return LongeronParameters()

def null_bolt_parameters():
    return BoltParameters()

def null_greeble_parameters():
    return GreebleParameters()

def null_plate_parameters():
    return PlateParameters()

def null_web_parameters():
    return WebParameters()

def null_bulkhead_flange_parameters():
    return BulkheadFlangeParameters()

def null_cowl_flange_parameters():
    return CowlFlangeParameters()

@dataclass(slots=True)
class OmlParameters:
    """The OpenVSP import transform. Three of these are in METRES, not millimetres.

    The suffixes are load-bearing (OQ-DES-CW1, resolved 2026-08-09). Everything else
    in this generator is millimetres, so an unsuffixed `length` reads as 0.05 mm when
    it means 0.05 m -- a factor of 1000, and the part still renders. `offset_x_m` is
    worse than that, because it is applied *before* the scale, so it is metres in the
    mesh's own frame; the tail's -0.25 is -250 mm at U = 1.

    `scale_m_per_mm` is a divisor, not a multiplier: `scale = U/scale_m_per_mm`. At
    1e-3 that multiplies by 1000, converting metres to millimetres, which is the one
    reading the bare name `scale` did not suggest. The suffix states the ratio in the
    order the division takes it -- metres of real airframe per millimetre of model.

    These field names are also the JSON keys: derived_cowl_parameters() copies them by
    `fields()`, so renaming here renames the schema, and both cowl files move with it.
    """
    filename: str = ""
    scale_m_per_mm: float = 0
    length_m: float = 0
    offset_x_m: float = 0
    reversed: bool = False


@dataclass(slots=True)
class NosePlateParameters:
    """The nose plate, which is not the bulkhead plate.

    PlateParameters describes the bulkhead's plate and carries a thickness and
    nothing else; this one carries a diameter and a flange. Constructing the
    wrong one here silently produced a plate with no diameter.
    """
    active: bool = False
    diameter: float = 0
    thickness: float = 0
    flange_width: float = 0
    flange_height: float = 0
    tolerance: float = 0


@dataclass(slots=True)
class NoseTipParameters:
    active: bool = False
    flange_inset: float = 0
    flange_height: float = 0


@dataclass(slots=True)
class ButtressParameters:
    active: bool = False
    angle: float = 0
    y_offset: float = 0
    z_start: float = 0
    depth: float = 0      # named "depth" to match the JSON parameter files
    z_end: float = 0
    r_start: float = 0
    r_end: float = 0


@dataclass(slots=True)
class ButtressSet:
    """The buttresses, plus the three settings they share.

    Field order matters here in one respect only: the five buttress fields are
    the names read out of the JSON parameter files, so they are iterated by
    name rather than by position -- see derived_nose_parameters().
    """
    z_offset: float = 0
    r_inset: float = 0
    thickness: float = 0
    top: ButtressParameters = field(default_factory=ButtressParameters)
    top_diag1: ButtressParameters = field(default_factory=ButtressParameters)
    top_diag2: ButtressParameters = field(default_factory=ButtressParameters)
    bottom: ButtressParameters = field(default_factory=ButtressParameters)
    side: ButtressParameters = field(default_factory=ButtressParameters)


@dataclass(slots=True)
class NoseParameters:
    """Everything the nose and tail cowl geometry modules are driven from."""
    cowl_type: str = "nose"     # "nose" or "tail"; set from the parameter file
    type_name: str = ""
    U: float = 1
    unit_width: float = 0

    cut_len: float = 0
    cone_angle: float = 0

    oml: OmlParameters = field(default_factory=OmlParameters)
    plate: NosePlateParameters = field(default_factory=NosePlateParameters)
    nose: NoseTipParameters = field(default_factory=NoseTipParameters)
    buttress: ButtressSet = field(default_factory=ButtressSet)
    printer: PrinterSettings = field(default_factory=PrinterSettings)


def null_nose_parameters():
    return NoseParameters()

def null_oml_parameters():
    return OmlParameters()

def null_nose_plate_parameters():
    return NosePlateParameters()

def null_nose_nose_parameters():
    return NoseTipParameters()

def null_buttress_full_parameters():
    return ButtressSet()

def null_buttress_parameter():
    return ButtressParameters()
    
def scaled_standard_values(U,FX):

    sv = standard_values()
    
    c = dict()

    c["unit_width"] =sv["unit_width"]*U
    c["unit_length"] = sv["unit_length"]*U*FX
    c["corner_radius"] = sv["corner_radius"]*U
    c["longeron_radius"] = sv["longeron_radius"]*U
    c["bolt_offset"] = sv["bolt_offset"]*U

    return c

def derived_parameters(U,FX,user_parameters,printer_settings,is_bulkhead):

    c = null_parameters()

    # transcribe standard values
    ssv = scaled_standard_values(U,FX)
    c.bulkhead.U = U
    c.bulkhead.width = ssv["unit_width"]
    c.corner.FX = FX
    c.corner.radius = ssv["corner_radius"]
    c.corner.length = ssv["unit_length"]
    c.longeron.radius = ssv["longeron_radius"]
    c.bolt.offset = ssv["bolt_offset"]

    c.printer = printer_settings

    # fixed parameters -- see the constants beside standard_values() for what each is

    c.longeron.tolerance = LONGERON_TOLERANCE_MM
    c.greeble.opening_angle = GREEBLE_OPENING_ANGLE_DEG
    
    # derive values from user_paraemters

    if is_bulkhead:
        is_end = user_parameters["is_end"]
        is_interconnect = user_parameters["is_interconnect"]
        is_cowling = user_parameters["is_cowling"]
        is_boom = user_parameters["is_boom"]
        is_anchor = user_parameters["is_anchor"]
    
        c.bulkhead.type_name = user_parameters["bulkhead_type_name"]
        # greeble.tolerance is left at its zero default: the bulkhead's greeble post
        # is nominal by construction and the geometry takes no tolerance for it.
    else:
        is_end = False
        is_interconnect = False
        is_cowling = False
        is_boom = False
        is_anchor = False
        
        c.bulkhead.type_name = ""
        c.greeble.tolerance = GREEBLE_TOLERANCE_CORNER_MM
        
    c.bulkhead.type = encode_bulkhead_type(is_end, is_interconnect, is_cowling, is_boom)
    c.bulkhead.thickness = user_parameters["bulkhead_thickness"]
    c.panel.is_metric = user_parameters["panel_is_metric"]
    c.panel.thickness = user_parameters["panel_thickness_mm"]
    c.panel.type_name = user_parameters["panel_name"]

    # recreate derived dimensions from corner_end()
    #
    # sqrt(U), not U: the greeble wall is a printed feature sized to survive a snap fit,
    # so it scales in extrusions rather than as a fraction of the airframe. The max()
    # floors it at two extrusion widths, because a one-extrusion wall has no interior.
    c.greeble.thickness = max(2*math.sqrt(U)*c.printer.extrusion_width, 2*c.printer.extrusion_width)
    c.greeble.nub_thickness = greeble_nub_thickness_of(c.greeble.thickness)

    # The zero is structural, not a setting: a cowling has no panel and neither does the
    # 0 mm panel variant, so there is no gap to leave. Only the else branch is tunable,
    # which is why only it reads the tolerance file.
    if is_cowling or c.panel.thickness==0:
        c.panel.tolerance = 0.0
    else:
        c.panel.tolerance = PANEL_TOLERANCE_MM
    
    if not is_cowling:
        
        if c.panel.thickness==0:
            c.panel.overlap = 0
        else:
            c.panel.overlap = max(c.panel.thickness, 4)

        # keep the inside corner of the panel from coming too close to the greeble perimeter
        panel_clearance_radius = c.longeron.radius + c.longeron.tolerance + c.greeble.thickness  + c.greeble.nub_thickness + 2*c.printer.extrusion_width

        # lower edge of the panel
        panel_corner_y = max(c.corner.radius - c.panel.thickness - c.panel.tolerance, 0)

        if panel_clearance_radius > panel_corner_y:
            panel_offset = math.sqrt(panel_clearance_radius*panel_clearance_radius - panel_corner_y*panel_corner_y);
        else:
            panel_offset = 0

        # keep the offset + overlap outside of the greeble nub bevel

        # print("panel_offset = " + str(panel_offset))
        # print("panel_clearance_radius = " + str(panel_clearance_radius))
        
        greeble_clearance_width = 1*U # extra width around the greeble to allow the corner to snap in on the back side
        # print("greeble_clearance_width = " + str(greeble_clearance_width))
        
        panel_offset = max(panel_offset, (panel_clearance_radius - 2*c.printer.extrusion_width)/math.sqrt(2) + 2*c.printer.extrusion_width + greeble_clearance_width - c.panel.overlap)
        panel_offset = max(panel_offset, 0)
        panel_offset = min(panel_offset, math.sqrt(2)*c.corner.radius)
        panel_offset = 0.25*math.ceil(4*panel_offset) # inflate to nearest 0.25 mm

        # print("panel_offset = " + str(panel_offset))
        
        c.panel.offset = panel_offset
    else:
        c.panel.overlap = 0
        c.panel.offset = 0

    c.bolt.diameter = user_parameters["bulkhead_bolt_diameter"]
    
    if is_anchor:
        # look up anchor size from bolt radius
        c.bolt.radius = lookup_anchor_diameter(c.bolt.diameter)/2
    else:
        c.bolt.radius = c.bolt.diameter/2

    # As with panel.tolerance, the zero on the else branch is structural: a bulkhead that
    # mounts no cowl has no cowl flange, so there is no gap to leave. Only the cowling
    # branch reads the tolerance file.
    if is_cowling:
        c.cowl_flange.height=2*U;
        c.cowl_flange.tolerance=COWL_FLANGE_TOLERANCE_MM;
        c.bulkhead_flange.thickness=max(math.ceil(3*U)*c.printer.extrusion_width, 3*c.printer.extrusion_width)
    else:
        c.cowl_flange.height=0;
        c.cowl_flange.tolerance=0.0;
        c.bulkhead_flange.thickness=max(math.ceil(2*U)*c.printer.extrusion_width, 2*c.printer.extrusion_width)
    
    c.bolt.thickness=max(3*U, 3)
    c.plate.thickness=math.ceil(4*U)*c.printer.layer_height
    c.web.fillet_radius=2*U
    
    if is_boom:
        c.web.width=6*U
    else:
        c.web.width=3*U
        
    c.bulkhead_flange.fillet_radius=2*U
    c.bulkhead_flange.chamfer=1*U

    if is_boom:
        c.boom_bulkhead = derived_boom_bulkhead_parameters(U,FX,user_parameters,printer_settings)
    
    return c

def read_param_json(file_path):
    """
    Reads one of the nose/tail JSON parameter files.
    """
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


# Values in the nose/tail JSON files are fractions of unit_width; a few are
# ratios or angles and are used as-is. Which is which was recovered from the
# hand-written drivers, e.g. nose_cowl.scad at U=1 (unit_width=100):
#
#     plate.diameter      0.6    -> plate_diam         = U*60
#     cut_len             0.06   -> cut_len            = U*6
#     buttress.z_offset   0.02   -> buttress_z_offset  = U*2
#     buttress.top.r_end  0.066  -> buttress_r_end     = U*6.6
#     nose.flange_height  0.01   -> nose_flange_height = 1.0
#
#     nose.flange_inset   0.5    -> nose_flange_inset  = 0.5    (unscaled)
#     plate.tolerance     0.1    -> plate_tol          = 0.1    (unscaled)
#     buttress.thickness  0.05   -> buttress_thickness = 0.05   (unscaled)
#     oml.length_m        0.05   -> oml_length_m       = 0.050  (unscaled, METRES)
#     cone_angle          35     -> cone_angle         = 35     (unscaled)
#
# Two of the unscaled names are not merely "not multiplied by unit_width" but are in
# different units entirely: the oml.*_m fields are metres (see OmlParameters), and
# cone_angle is degrees from the print bed (OQ-DES-CW2). Being in this tuple means
# only that unit_width does not touch them.
NOSE_UNSCALED = ("cone_angle", "tolerance", "flange_inset", "thickness",
                 "active", "angle", "filename", "scale_m_per_mm", "length_m",
                 "offset_x_m", "reversed")


def derived_cowl_parameters(U, FX, user_parameters, printer_settings):
    """
    Expands a nose or tail JSON parameter file into the nested dict the cowl
    geometry modules expect, scaling fractional values by unit_width.

    Nose and tail share this because they share the cowl bulkhead and the OML
    blank; the JSON schema is a superset covering both. What differs is which
    geometry module consumes it, and that is decided by "cowl_type" in the file
    itself rather than by which sweep happens to be running -- feeding a tail
    parameter file to the nose module produces a shape nobody designed.
    """
    c = null_nose_parameters()

    unit_width = scaled_standard_values(U, FX)["unit_width"]

    param_path = os.path.join(COWL_DIR, user_parameters["parameter_filename"])
    src = read_param_json(param_path)

    c.cowl_type = src.get("cowl_type", "nose")
    c.type_name = (user_parameters.get("nose_type_name")
                   or user_parameters.get("tail_type_name")
                   or user_parameters.get("cowl_type_name", ""))
    c.U = U
    c.unit_width = unit_width
    c.printer = printer_settings

    c.cone_angle = src["cone_angle"]
    c.cut_len = src["cut_len"] * unit_width

    # Driven by the declared fields, not by whatever the JSON happens to carry:
    # a missing key is still a KeyError at this line, and an extra one in the
    # file is still ignored -- the same behaviour the dict version had, now
    # stated by the dataclass rather than by the dict it was copied into.
    for f in fields(c.oml):
        setattr(c.oml, f.name, src["oml"][f.name])

    # Absolute millimetres from the per-U variation table
    # (nose_size_variants.csv), NOT scaled by unit_width. These are set by the
    # printing process as much as by airframe size: a plate is a whole number
    # of layers thick and a flange a whole number of extrusion widths wide.
    # Seeded from linear U scaling rounded UP to the next 0.2 mm layer (Z) or
    # 0.4 mm extrusion (XY); the U=1 row reproduces the original constants.
    # The table is the place to tune these -- do not reintroduce a formula.
    # The nose tip and its plate exist only on a nose. A tail parameter file
    # carries no size row for them, so they are read only when they apply --
    # requiring them of a tail would be demanding dimensions for parts it does
    # not have.
    c.nose.active = src["nose"]["active"]
    c.nose.flange_inset = src["nose"]["flange_inset"]
    c.nose.flange_height = user_parameters.get("nose_flange_height", 0)

    c.plate.active = src["plate"]["active"]
    c.plate.tolerance = src["plate"]["tolerance"]
    c.plate.diameter = src["plate"]["diameter"] * unit_width
    c.plate.thickness = user_parameters.get("plate_thickness", 0)
    c.plate.flange_width = user_parameters.get("plate_flange_width", 0)
    c.plate.flange_height = user_parameters.get("plate_flange_height", 0)

    b_src = src["buttress"]
    c.buttress.thickness = b_src["thickness"]
    c.buttress.z_offset = b_src["z_offset"] * unit_width
    c.buttress.r_inset = b_src["r_inset"] * unit_width

    for name in ("top", "top_diag1", "top_diag2", "bottom", "side"):
        s = b_src[name]
        d = getattr(c.buttress, name)
        for f in fields(d):
            value = s[f.name]
            setattr(d, f.name,
                    value if f.name in NOSE_UNSCALED else value * unit_width)

    return c


def derived_boom_bulkhead_parameters(U,FX,user_parameters,printer_settings):

    c = null_boom_bulkhead_parameters()
    ssv = scaled_standard_values(U,FX)

    c.diameter = ssv["unit_width"]*user_parameters["boom_diameter"]
    c.thickness = U*2
    c.y_position = ssv["unit_width"]*user_parameters["y_position"]
    c.z_position = ssv["unit_width"]*user_parameters["z_position"]
    c.collet_thickness = U*3
    c.key_width = max(U*2, 2)
    c.key_height = max(U*2, 2)
    c.key_radius = max(U*0.5, 0.5)
    c.key_web_width = U*6
    c.key_angle = BOOM_KEY_ANGLE_DEG
    c.tolerance = BOOM_TOLERANCE_MM
    c.type_name = user_parameters["bulkhead_type_name"]
    c.make_vert_web = user_parameters["make_vert_web"]
    c.make_lower_web = user_parameters["make_lower_web"]

    return c

# ------------------------------------------------------------
# Functions for parametric analysis
# ------------------------------------------------------------
def read_param_csv(file_path):
    """
    Reads a CSV file and returns a list of parameter dictionaries.
    Assumes each CSV has one parameter per column.
    """
    df = pd.read_csv(file_path)
    return df.to_dict(orient="records")


def read_all_param_axes(file_paths):
    """
    Reads all CSV files (each representing one axis of variation).
    Returns a list of lists of parameter dicts.
    """
    return [read_param_csv(path) for path in file_paths]


def flatten_param_space(param_axes):
    """
    Creates the full factorial combination of parameter values from each axis.
    Each axis is a list of dicts; we combine them into merged dicts.
    """
    combinations = []
    for combo in itertools.product(*param_axes):
        merged = {}
        for param_dict in combo:
            merged.update(param_dict)
        combinations.append(merged)
    return combinations


def generate_filename_from_params(params, prefix="result", extension=".json"):
    """
    Creates a unique filename based on parameter values.
    """
    safe_parts = [
        f"{k}={str(v).replace(' ', '_')}" for k, v in sorted(params.items())
    ]
    return prefix + "__" + "__".join(safe_parts) + extension


def generate_fuselage_corner_variant_filename_from_params(dp, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    
    if dp.panel.is_metric:
        unit_str = "metric"
    else:
        unit_str = "imperial"
            
    # return "bulk" + "__U_" + str(dp.bulkhead.U) + "__metric_panel_" + dp.panel.type_name.replace('/', '_') + "__type_" + dp.bulkhead.type + extension
    
    dir_name = os.path.join("U_" + str(dp.bulkhead.U), unit_str, "panel_" + dp.panel.type_name.replace('/', '_'), "corner")
    file_name = "U_" + str(dp.bulkhead.U) + "__" + unit_str + "_panel_" + dp.panel.type_name.replace('/', '_') + "__" + "corner_FX_" + str(dp.corner.FX) + extension
    
    # return "bulk" + "__U_" + str(dp.bulkhead.U) + "__metric_panel_" + dp.panel.type_name.replace('/', '_') + "__type_" + dp.bulkhead.type + extension

    return os.path.join(dir_name, file_name)

def corner_validity_check(dp):
    """
    Tests the parameters for valid agreement
    """

    sv = standard_values()
    
    U = (dp.bulkhead.width/sv["unit_width"])
    
    bulkhead_min_panel_thickness_parametric = U * 1
    bulkhead_max_panel_thickness_parametric = dp.corner.radius - (dp.longeron.radius + dp.longeron.tolerance + dp.greeble.thickness + dp.greeble.nub_thickness)
    
    # check bulkead_thickness >= bulkhead_max_panel_thickness_parametric

    is_valid = dp.panel.thickness == 0 or dp.panel.thickness >= bulkhead_min_panel_thickness_parametric
    is_valid &= dp.panel.thickness <= bulkhead_max_panel_thickness_parametric
    
    return is_valid

def run_corner_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    printer_settings = null_printer_settings()

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        # print(params)
        U = params["U"]
        FX = params["FX"]
        
        dp = derived_parameters(U,FX,params,printer_settings,False)
        
        is_valid = corner_validity_check(dp)

        if is_valid:

            print(dp)
            # result = example_design_tool(**params)  # replace with your actual call
            filename = generate_fuselage_corner_variant_filename_from_params(dp)

            corner_render(dp, output_dir, filename)

def generate_fuselage_bulkhead_variant_filename_from_params(dp, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    
    if dp.panel.is_metric:
        unit_str = "metric"
    else:
        unit_str = "imperial"
            
    # return "bulk" + "__U_" + str(dp.bulkhead.U) + "__metric_panel_" + dp.panel.type_name.replace('/', '_') + "__type_" + dp.bulkhead.type + extension
    
    dir_name = os.path.join("U_" + str(dp.bulkhead.U), unit_str, "panel_" + dp.panel.type_name.replace('/', '_'), "bulkhead")
    file_name = "U_" + str(dp.bulkhead.U) + "__" + unit_str + "_panel_" + dp.panel.type_name.replace('/', '_') + "__" + "bulkhead_" + dp.bulkhead.type_name + extension
    
    # return "bulk" + "__U_" + str(dp.bulkhead.U) + "__metric_panel_" + dp.panel.type_name.replace('/', '_') + "__type_" + dp.bulkhead.type + extension

    return os.path.join(dir_name, file_name)

def generate_fuselage_boom_bulkhead_variant_filename_from_params(dp, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    
    if dp.panel.is_metric:
        unit_str = "metric"
    else:
        unit_str = "imperial"
            
    # return "bulk" + "__U_" + str(dp.bulkhead.U) + "__metric_panel_" + dp.panel.type_name.replace('/', '_') + "__type_" + dp.bulkhead.type + extension
    
    dir_name = os.path.join("U_" + str(dp.bulkhead.U), unit_str, "panel_" + dp.panel.type_name.replace('/', '_'), "bulkhead")
    file_name = "U_" + str(dp.bulkhead.U) + "__" + unit_str + "_panel_" + dp.panel.type_name.replace('/', '_') + "__" + "boom_bulkhead_" + dp.bulkhead.type_name + extension
    
    # return "bulk" + "__U_" + str(dp.bulkhead.U) + "__metric_panel_" + dp.panel.type_name.replace('/', '_') + "__type_" + dp.bulkhead.type + extension

    return os.path.join(dir_name, file_name)
    
def generate_fuselage_nose_variant_filename_from_params(U, dp, is_nose_cowl, is_nose_nose, is_nose_plate, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    if is_nose_cowl:
        type_name = "cowl"
    elif is_nose_nose:
        type_name = "nose"
    elif is_nose_plate:
        type_name = "plate"
    else:
        type_name = ""

    # The nose-type name has to be in the path: the sweep now runs one pass per
    # JSON parameter file, and without it every variant would write over the
    # previous one at the same U.
    variant = dp.type_name

    dir_name = os.path.join("U_" + str(U), "nose", variant)
    file_name = "U_" + str(U) + "__" + variant + "__nose_" + type_name + extension

    return os.path.join(dir_name, file_name)
    
def generate_fuselage_tail_variant_filename_from_params(U, dp, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    # The variant name is in the path for the same reason it is on the nose
    # side: one pass per parameter file, and without it a second tail type
    # would overwrite the first at the same path rather than sit beside it.
    variant = dp.type_name

    dir_name = os.path.join("U_" + str(U), "tail", variant)
    file_name = "U_" + str(U) + "__" + variant + "__tail" + extension

    return os.path.join(dir_name, file_name)

def bulkhead_validity_check(dp):
    """
    Tests the parameters for valid agreement
    """

    sv = standard_values()
    
    U = (dp.bulkhead.width/sv["unit_width"])
    
    bulkhead_min_panel_thickness_parametric = U * 1
    bulkhead_max_panel_thickness_parametric = dp.corner.radius - (dp.longeron.radius + dp.longeron.tolerance + dp.greeble.thickness + dp.greeble.nub_thickness)
    
    # check bulkead_thickness >= bulkhead_max_panel_thickness_parametric

    is_valid = dp.panel.thickness == 0 or dp.panel.thickness >= bulkhead_min_panel_thickness_parametric
    is_valid &= dp.panel.thickness <= bulkhead_max_panel_thickness_parametric
    is_valid &= (not dp.bulkhead.type == BulkheadType.COWLING) or dp.panel.thickness == 0
    
    return is_valid

def boom_key_validity_check(dp):
    """
    Tests the boom key parameters against the domain its fillet construction is defined on.

    `boom_key_shape` builds its four corners as true fillets, decided in OQ-DES-B11. Two arcs
    of key_radius have to fit across the tab and along its protrusion, and the tab has to stay
    narrower than the hole it keys.

    The hole is the one the collet passes through, not the boom itself: its radius is
    diameter/2 + collet_thickness + tolerance. The width limit and the geometric singularity
    are the same statement here rather than two -- the junction fillet centre sits at height
    sqrt((cr + r)^2 - (w/2 + r)^2), which goes imaginary at exactly w = 2*cr, where the tab
    spans the hole and the two junctions it is filleting no longer exist.

    The other two rules are not independent either. key_height >= 2*key_radius is what keeps
    the concave junction fillets clear of the convex cap fillets: the junction tangent point
    is at most cr + key_radius, the cap starts at cr + key_height - key_radius, and the first
    is below the second precisely when key_height >= 2*key_radius.

    This check is load bearing in a way it would not have been before. The morphological form
    it replaced failed LOUDLY outside the domain: an opening removes any protrusion thinner
    than twice its radius, so a tab below 2*key_radius did not round off, it vanished, and the
    part came out visibly wrong. The direct construction fails QUIETLY instead -- the two
    corner arcs cross over and the cap comes out wider than the tab it caps, which is a
    plausible-looking part. Trading a loud failure for a quiet one is only safe if the domain
    is checked, so it is checked here.
    """

    b = dp.boom_bulkhead

    collet_radius = b.diameter / 2 + b.collet_thickness + b.tolerance

    is_valid = b.key_width >= 2 * b.key_radius
    is_valid &= b.key_height >= 2 * b.key_radius
    is_valid &= b.key_width < 2 * collet_radius

    return is_valid

def run_bulkhead_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    printer_settings = null_printer_settings()
    
    FX = 1.0

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        # print(params)
        U = params["U"]
        
        dp = derived_parameters(U,FX,params,printer_settings,True)
        
        # Through the family table, so what BULKHEAD_FAMILIES says this sweep checks is what
        # it checks. The tools that offer to render one variant read that table; if it and
        # this loop drifted apart, they would offer combinations the sweep skips.
        is_valid = family_is_valid('bulkhead', dp)

        if is_valid:

            print(dp)
            filename = generate_fuselage_bulkhead_variant_filename_from_params(dp)

            bulkhead_render(dp, output_dir, filename)

def run_boom_bulkhead_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    printer_settings = null_printer_settings()
    
    FX = 1.0

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        # print(params)
        U = params["U"]
        
        dp = derived_parameters(U,FX,params,printer_settings,True)
        
        is_valid = family_is_valid('boom_bulkhead', dp)

        if is_valid:

            print(dp)
            filename = generate_fuselage_boom_bulkhead_variant_filename_from_params(dp)

            boom_bulkhead_render(dp, output_dir, filename)


def run_nose_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    # FX does not vary for cowl geometry -- a cowl is defined against the OML,
    # not a bay length -- but derived_cowl_parameters shares the scaling helper
    # with the other sweeps, which takes it.
    FX = 1.0
    printer_settings = null_printer_settings()

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        U = params["U"]

        dp = derived_cowl_parameters(U, FX, params, printer_settings)

        if dp.cowl_type != "nose":
            raise ValueError(
                "%s declares cowl_type=%r but is listed in the NOSE type axis. "
                "A tail parameter file rendered through the nose modules "
                "produces geometry nobody designed; put it in "
                "tail_type_variants.csv instead."
                % (params["parameter_filename"], dp.cowl_type))

        print(dp)

        # Which of the three parts exist is a property of the parameter file.
        wanted = [(True, False, False)]
        if dp.nose.active:
            wanted.append((False, True, False))
        if dp.plate.active:
            wanted.append((False, False, True))

        for (is_nose_cowl, is_nose_nose, is_nose_plate) in wanted:
            filename = generate_fuselage_nose_variant_filename_from_params(
                U, dp, is_nose_cowl, is_nose_nose, is_nose_plate)
            nose_render(U, dp, output_dir, filename,
                        is_nose_cowl, is_nose_nose, is_nose_plate)


def run_tail_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    FX = 1.0
    printer_settings = null_printer_settings()

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        U = params["U"]

        dp = derived_cowl_parameters(U, FX, params, printer_settings)

        if dp.cowl_type != "tail":
            raise ValueError(
                "%s declares cowl_type=%r but is listed in the TAIL type axis."
                % (params["parameter_filename"], dp.cowl_type))

        print(dp)

        filename = generate_fuselage_tail_variant_filename_from_params(U, dp)

        tail_render(U, dp, output_dir, filename)
            
_SCAD_REF_RE = re.compile(r'(?m)^(\s*)(use|include)\s*<([^>]+)>\s*;')


def relativize_scad_references(scad_path):
    """Rewrite absolute `use <...>` / `include <...>` lines to relative ones.

    solid2's resolve_scad_filename() calls .absolute() unconditionally, so every
    generated file records the exact directory it was produced in. The
    2025-09-22 sweep was run from a mapped drive, and all 1774 of its .scad
    files still say `use <R:\\Alex\\...>` -- a path that resolves nowhere now, so
    none of them can be re-rendered.

    OpenSCAD resolves `use` and `include` against the directory of the file
    containing them, so a path relative to the generated file is both correct
    and portable. Paths on another drive or share cannot be expressed relatively
    and are left absolute rather than mangled.
    """
    here = os.path.dirname(os.path.abspath(scad_path))

    def to_relative(match):
        indent, keyword, target = match.groups()
        if not os.path.isabs(target):
            return match.group(0)
        try:
            rel = os.path.relpath(target, here)
        except ValueError:
            return match.group(0)          # different drive; no relative form
        return '%s%s <%s>;' % (indent, keyword, rel.replace(os.sep, '/'))

    with open(scad_path, encoding='utf-8') as f:
        text = f.read()
    rewritten = _SCAD_REF_RE.sub(to_relative, text)
    if rewritten != text:
        with open(scad_path, 'w', encoding='utf-8', newline='') as f:
            f.write(rewritten)


class RenderFailed(RuntimeError):
    """One or more queued OpenSCAD runs failed."""


class RenderQueue:
    """Runs the sweep's OpenSCAD invocations, optionally across a thread pool.

    The sweep is a serial loop whose per-part cost is almost entirely a blocking
    `openscad` subprocess, so it uses one core out of however many the machine has.
    Splitting the loop is unnecessary: only the subprocess calls need to overlap,
    and the Python either side of them -- building the solid2 tree, writing the
    .scad, rewriting its references -- stays on the main thread where it belongs.

    Threads rather than processes, because each job blocks in a child process and
    releases the GIL while waiting. That also sidesteps solid2's module-level facet
    state (`set_global_fn`/`fa`/`fs`), which is set during generation and would be
    a race if generation itself were parallel.

    Work is drained in chunks rather than all at the end. A failing render would
    otherwise stay invisible until thousands more had been queued behind it, and
    the run would look like it was skipping everything.
    """

    def __init__(self, workers=1, chunk=None, progress_every=20):
        self.workers = max(1, int(workers))
        self.chunk = chunk or max(self.workers * 4, 8)
        self.progress_every = progress_every
        self._pending = []
        self._done = 0
        self._failed = 0
        self._recovered = 0
        self._start = None

    def submit(self, cmd, on_success=None):
        """Queue an OpenSCAD command, or run it now when not parallel.

        `on_success` runs only if the command exits zero. That is what makes the
        write atomic: OpenSCAD renders to a temporary path and the callback moves
        it into place, so a crashed or killed render leaves no file at the real
        path rather than a convincing partial one.
        """
        job = (cmd, on_success)
        if self.workers == 1:
            self._run(job)
            self._done += 1
            return
        self._pending.append(job)
        if len(self._pending) >= self.chunk:
            self.drain()

    @staticmethod
    def _run(job):
        cmd, on_success = job
        subprocess.check_call(cmd,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
        if on_success is not None:
            on_success()

    def drain(self):
        """Run everything queued. Raises RenderFailed if any job failed."""
        if not self._pending:
            return
        jobs, self._pending = self._pending, []
        if self._start is None:
            self._start = time.time()

        failures = []
        with concurrent.futures.ThreadPoolExecutor(self.workers) as pool:
            futures = {pool.submit(self._run, c): c for c in jobs}
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:                     # noqa: BLE001
                    failures.append((futures[future], exc))
                self._done += 1
                if self._done % self.progress_every == 0:
                    rate = (time.time() - self._start) / self._done
                    sys.stderr.write(
                        '      rendered %d  (%.1f s/part, %d worker(s))\n'
                        % (self._done, rate, self.workers))
                    sys.stderr.flush()

        if failures:
            failures = self._retry_serially(failures)

        if failures:
            detail = '\n'.join('  %s\n    %s' % (job[0], e)
                               for job, e in failures[:10])
            raise RenderFailed(
                '%d of %d render(s) failed after a serial retry '
                '(%d succeeded, %d recovered on retry):\n%s'
                % (len(failures), self._done, self._done - self._failed,
                   self._recovered, detail))

    def _retry_serially(self, failures):
        """Re-run failed commands one at a time; return those that failed again.

        The dominant failure mode here is memory, not geometry. A large tail holds
        well over a gigabyte during its CGAL solve, and several at once on a loaded
        machine abort with STATUS_FATAL_APP_EXIT -- which is transient and depends
        entirely on what else was resident at that moment. Retrying serially, with
        the rest of the batch finished and its memory returned, recovers them:
        measured on the U=0.75 and U=2.0 tails, both of which aborted at five
        workers and then completed cleanly on their own in about 255 s each.

        A genuine geometry error fails again here and is reported, so this cannot
        turn a real defect into a silent pass.
        """
        self._failed += len(failures)
        still_failing = []
        sys.stderr.write('      %d render(s) failed; retrying serially\n'
                         % len(failures))
        sys.stderr.flush()
        for job, original in failures:
            try:
                self._run(job)
                self._recovered += 1
            except Exception:                                # noqa: BLE001
                still_failing.append((job, original))
        sys.stderr.write('      recovered %d of %d on retry\n'
                         % (len(failures) - len(still_failing), len(failures)))
        sys.stderr.flush()
        return still_failing

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Only flush the tail on a clean exit; on an error the queue is abandoned
        # rather than run, so a failure does not drag thousands of renders with it.
        if exc_type is None:
            self.drain()
        return False


# Module-level so the five sweep functions and their render helpers need no
# plumbing. Serial by default, which is exactly the previous behaviour; main()
# installs a parallel queue for the duration of a run.
_RENDER_QUEUE = RenderQueue(workers=1)


def set_render_queue(queue):
    """Install the queue solid_render submits to. Returns the previous one."""
    global _RENDER_QUEUE
    previous, _RENDER_QUEUE = _RENDER_QUEUE, queue
    return previous


# Which geometry engine renders a part. IP-FC-10: the sweep drives either, and the choice
# is a run-time setting rather than a fork of the driver, so the two can be compared on the
# same command with one flag changed -- which is what IP-FC-13's equivalence check needs.
# OpenSCAD stays the default until that check passes.
_BACKEND = 'openscad'


def set_backend(name):
    """Select 'openscad' or 'freecad'. Returns the previous value.

    Only the corner and the bulkhead have FreeCAD generators. The other three sweeps fall
    back to OpenSCAD per part rather than failing the run -- see `_backend_for`, where that
    decision is made explicit rather than left to whichever call site notices first.
    """
    global _BACKEND
    if name not in ('openscad', 'freecad'):
        raise ValueError('unknown backend %r' % name)
    previous, _BACKEND = _BACKEND, name
    return previous


def _backend_for(kind, supported=True):
    """The backend that will actually render `kind`, which is not always the one selected.

    A part with no FreeCAD generator yet renders in OpenSCAD even under --backend freecad.
    Silently, and deliberately: the alternative is a sweep that cannot run at all until every
    part is ported, which would make the backend flag useless for exactly the period it is
    most needed. `main()` prints which parts this applies to, so it is not invisible.

    `supported` extends that per *variant*, not just per kind, and it exists because the
    coarser test was wrong. `bulkhead` is ported, but only its plain end type: the FreeCAD
    `bulkhead_full.emit()` takes no `is_cowling` or `is_interconnect`, where the OpenSCAD
    call site passes both. So `--backend freecad` rendered all five swept types as the end
    type -- three of five silently wrong, under the right filename, with a plausible volume.
    A part that falls back is a part still rendered correctly; a part built from the wrong
    branch is a part nobody has reason to re-examine.
    """
    if _BACKEND == 'freecad' and kind in freecad_render_backend.KINDS and supported:
        return 'freecad'
    return 'openscad'


# Resume state. Off by default so a plain run reproduces every part, which is what
# you want when geometry or parameters have changed; a resume trusts what is on disk.
_RESUME = False
_RESUME_COUNTS = {'skipped': 0, 'changed': 0}


def set_resume(enabled):
    """Skip parts that are already rendered and unchanged. Returns the previous value.

    Safe to leave on: a part is skipped only when the definition file it would write
    now is byte-identical to the one on disk *and* the STL beside it is a whole mesh.
    Edit a parameter CSV and the affected parts re-render on their own, because the
    parameters in that file move.

    Since IP-FC-11 that holds for the *geometry sources* too, which it did not before.
    The definition file is a call, not the geometry -- a `use <>` line and a parameter
    list on the OpenSCAD side, a parameter table on the FreeCAD side -- so editing
    fuselage_bulkhead_geometry.scad or bulkhead_full.py left every definition
    byte-identical and a resumed run skipped exactly the parts the edit invalidated.
    Both now carry a digest of their geometry sources, so the existing comparison sees
    them. See tools/geometry_version.py.

    Use --force to re-render regardless, e.g. after changing something no source file
    records -- an OpenSCAD or FreeCAD version bump, or an OML mesh replaced in place.
    """
    global _RESUME
    previous, _RESUME = _RESUME, bool(enabled)
    _RESUME_COUNTS['skipped'] = 0
    _RESUME_COUNTS['changed'] = 0
    return previous


# Preview PNGs are produced by the sweep, alongside each STL. On by default: a run
# should yield the parts and the images to check them by, in one command.
#
# They are rendered from the finished STL by stl_preview, not by a second OpenSCAD
# invocation. The old `--render` pass re-solved the whole CSG tree just to take a
# picture, which was the dominant cost of a run; rasterizing the mesh that the
# first invocation already produced costs a couple of seconds.
_PREVIEWS = True

# Parts a resumed run found already rendered but without a preview. Rendered in
# one parallel batch at the end rather than inline, because the resume path runs on
# the main thread and rasterizing is numpy-bound.
_PREVIEW_BACKLOG = []


def set_previews(enabled):
    """Enable or disable preview generation. Returns the previous value."""
    global _PREVIEWS
    previous, _PREVIEWS = _PREVIEWS, bool(enabled)
    del _PREVIEW_BACKLOG[:]
    return previous


def find_rendered_stls(output_dir):
    """Every finished STL under output_dir, in a stable order.

    '*.partial.stl' is excluded: those are in-flight or abandoned renders, named
    that way because OpenSCAD picks its export format from the extension and so
    cannot write to a name that does not end in .stl.
    """
    return [str(p) for p in sorted(Path(output_dir).rglob('*.stl'))
            if not p.name.endswith('.partial.stl')]


def render_preview_batch(stl_paths, workers=None, size=None, supersample=None,
                         progress_every=25):
    """Render previews for many STLs across a process pool. Returns failures.

    Processes rather than threads: rasterizing is numpy-bound, so a thread pool
    would serialize on the GIL and gain nothing. That is the opposite of the
    OpenSCAD render queue, where threads are right precisely because each job
    blocks in a child process.
    """
    size = size or stl_preview.DEFAULT_SIZE
    supersample = (stl_preview.DEFAULT_SUPERSAMPLE if supersample is None
                   else supersample)
    jobs = [(str(p), size, True, True, supersample) for p in stl_paths]
    if not jobs:
        return []
    workers = workers or default_render_workers()

    failures = []
    start = time.time()
    try:
        with concurrent.futures.ProcessPoolExecutor(workers) as pool:
            futures = [pool.submit(stl_preview.render_one, j) for j in jobs]
            for done, future in enumerate(
                    concurrent.futures.as_completed(futures), start=1):
                path, error = future.result()
                if error:
                    failures.append((path, error))
                    print('  preview FAILED  %s: %s'
                          % (os.path.basename(path), error), flush=True)
                if progress_every and (done % progress_every == 0
                                       or done == len(jobs)):
                    rate = (time.time() - start) / done
                    print('  previews %d/%d  %.2f s each  ~%.1f min left'
                          % (done, len(jobs), rate,
                             (len(jobs) - done) * rate / 60), flush=True)
    except concurrent.futures.process.BrokenProcessPool:
        # Windows spawns workers by re-importing the caller's __main__, so a driver
        # script without an `if __name__ == "__main__":` guard makes every worker
        # re-run that script and the pool collapses. Serial is slow but produces
        # the images; losing them to a harness detail would be the worse outcome.
        print('  preview pool broke -- falling back to serial. If the caller is a '
              'script, it needs an `if __name__ == "__main__":` guard.', flush=True)
        failures = [(p, e) for p, e in
                    (stl_preview.render_one(j) for j in jobs) if e]
    return failures


def rebuild_previews(output_dir=None, workers=None, force=False):
    """Regenerate previews across an existing output tree, without touching geometry.

    For look changes -- a camera fix, different edge or occlusion settings -- where
    the meshes are already correct and only the images are stale. Re-rendering the
    geometry to get new pictures would cost hours for no benefit.
    """
    output_dir = OUTPUT_DIR if output_dir is None else output_dir
    stls = find_rendered_stls(output_dir)
    if force:
        todo = stls
    else:
        todo = [p for p in stls
                if not os.path.isfile(str(Path(p).with_suffix('.png')))]

    print('previews: %d STL(s) under %s, %d to render%s'
          % (len(stls), output_dir, len(todo),
             '' if force else ' (missing only; --force redoes all)'), flush=True)
    if not todo:
        return []
    workers = workers or default_render_workers()
    failures = render_preview_batch(todo, workers=workers)
    if failures:
        print('previews: %d failed' % len(failures), flush=True)
    return failures


def _write_preview(stl_path, png_path):
    """Render a preview beside a finished STL.

    Runs on the worker thread, immediately after the STL is moved into place, so
    previews keep pace with the sweep rather than needing a second pass.

    A preview failure is reported but does not fail the part: the STL is the
    deliverable and is already written and verified by this point, so discarding a
    good part because its picture did not render would be the wrong trade. This is
    the one place a broad except is warranted, and it is not silent.
    """
    try:
        stl_preview.render_stl_to_png(stl_path, png_path)
    except Exception as exc:                                 # noqa: BLE001
        sys.stderr.write('      preview failed for %s: %s: %s\n'
                         % (os.path.basename(stl_path), type(exc).__name__, exc))
        sys.stderr.flush()


# Peak resident set observed for the heaviest part in the sweep -- a U=4.0 tail,
# roughly 367k triangles -- was about 1.27 GB. The headroom above that covers the
# larger boom bulkheads and leaves room for the CGAL peak to overshoot the steady
# state without pushing the machine into swap.
RENDER_MEMORY_PER_WORKER_MB = 1600


def _available_memory_bytes():
    """Physical memory currently available, or None if it cannot be determined."""
    try:
        if sys.platform == 'win32':
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong),
                            ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong),
                            ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong),
                            ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong),
                            ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return int(status.ullAvailPhys)
        return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (AttributeError, OSError, ValueError):
        return None


def render_worker_budget():
    """Return (workers, reason) for the default worker count.

    Bounded by cores *and* by free memory. The memory bound is not optional: a
    CGAL render of a large tail holds well over a gigabyte, and five of them at
    once on a loaded machine exhausts physical memory and aborts OpenSCAD with
    STATUS_FATAL_APP_EXIT -- which looks like a geometry failure but is not one.

    Measured live rather than from total RAM, because this machine routinely runs
    an IDE, MCP servers, and a FreeCAD GUI alongside the sweep; the memory that
    matters is what is free at the moment the sweep starts.
    """
    override = os.environ.get('FUSELAGE_RENDER_WORKERS')
    if override:
        return max(1, int(override)), 'FUSELAGE_RENDER_WORKERS'

    # An OpenSCAD render is compute-bound and gains little from hyperthreading, so
    # the physical count is the useful number; logical // 2 is the closest estimate
    # available without adding a dependency. One core is left for the machine.
    logical = os.cpu_count() or 2
    physical = max(1, logical // 2)
    by_cores = max(1, physical - 1)

    available = _available_memory_bytes()
    if available is None:
        return by_cores, '%d physical core(s) of %d logical, 1 reserved; memory unknown' % (
            physical, logical)

    per_worker = int(os.environ.get('FUSELAGE_RENDER_WORKER_MB',
                                    RENDER_MEMORY_PER_WORKER_MB))
    by_memory = max(1, int(available // (per_worker * 1024 * 1024)))
    workers = min(by_cores, by_memory)
    reason = ('%d physical core(s) of %d logical, 1 reserved -> %d; '
              '%.1f GB free / %d MB per worker -> %d; taking the lower'
              % (physical, logical, by_cores,
                 available / (1024 ** 3), per_worker, by_memory))
    return workers, reason


def default_render_workers():
    """Workers to use when the caller does not say."""
    return render_worker_budget()[0]


def render_definition(write_definition, definition_suffix, make_command,
                      output_dir, filename):
    """Render one part, whatever built its definition.

    IP-FC-10 split this out of `solid_render`. Everything here is engine-independent and had
    to stay that way for a second backend to be a setting rather than a fork: the resume
    comparison, the atomic write, the preview, the queue submission. Only two things differ
    between OpenSCAD and FreeCAD, and both arrive as arguments --

        write_definition(path)          put the file that *defines* this part at `path`
        make_command(definition, stl)   the argv (or command string) that renders it

    -- so a third backend would need nothing here at all.

    Returns (definition_path, stl_path, png_path).
    """
    file_dir = os.path.dirname(filename)
    file_name = os.path.basename(filename)

    full_output_dir = os.path.join(output_dir, file_dir)
    Path(full_output_dir).mkdir(parents=True, exist_ok=True)

    def beside(suffix):
        return os.path.join(full_output_dir,
                            Path(file_name).with_suffix(suffix).name)

    definition_filepath = beside(definition_suffix)
    stl_filepath = beside('.stl')
    png_filepath = beside('.png')

    # Write the definition to a temporary path first, so a resume can compare it against
    # what is already on disk. Writing it is cheap next to rendering, and it is what makes
    # --resume trustworthy: a resumed run that skipped purely on "the STL exists" would
    # silently keep stale parts after a geometry module or a parameter CSV changed. Same
    # code path for both sides of the comparison, so they are guaranteed comparable.
    partial_definition = beside('.partial' + definition_suffix)
    write_definition(partial_definition)

    definition_unchanged = (
        os.path.isfile(definition_filepath)
        and filecmp.cmp(partial_definition, definition_filepath, shallow=False)
    )

    # Resume: skip a part whose definition is unchanged and whose STL is already a
    # whole mesh. The mesh sentinel is mesh_stats.is_complete, not os.path.isfile --
    # a killed render used to leave a partial .stl that every existence check
    # treated as finished. Combined with the atomic write below, a present .stl now
    # genuinely means a finished render of the definition sitting beside it.
    if _RESUME and definition_unchanged and mesh_stats.is_complete(stl_filepath):
        os.remove(partial_definition)
        _RESUME_COUNTS['skipped'] += 1
        if _RESUME_COUNTS['skipped'] % 50 == 0:
            sys.stderr.write('    ...%d already rendered\n'
                             % _RESUME_COUNTS['skipped'])
            sys.stderr.flush()
        # The geometry is done, but its preview may not be -- a run interrupted
        # before the preview, or output from before previews existed. Collect the
        # gap rather than rendering it here: this runs on the main thread, so
        # backfilling inline would render hundreds of previews one at a time while
        # every core sat idle. sweep_session renders the backlog across a pool.
        if _PREVIEWS and not os.path.isfile(png_filepath):
            _PREVIEW_BACKLOG.append(stl_filepath)
        return (definition_filepath, stl_filepath, png_filepath)

    if _RESUME and not definition_unchanged and os.path.isfile(definition_filepath):
        _RESUME_COUNTS['changed'] += 1

    os.replace(partial_definition, definition_filepath)

    # Render to a temporary path and move it into place only on success. Both engines
    # write their output progressively, so without this an interrupted run leaves a
    # convincing partial .stl at the real path -- which a resume would then skip,
    # permanently baking in a truncated part. os.replace is atomic within a volume.
    #
    # The temporary name must still end in .stl: OpenSCAD picks its export format
    # from the extension, so `-o foo.stl.partial` fails outright with exit 1. Tools
    # that scan the tree for parts filter '*.partial.stl' back out.
    partial_filepath = beside('.partial.stl')

    def _finalize(src=partial_filepath, dst=stl_filepath, png=png_filepath):
        # The render "succeeded" -- meaning it exited zero -- so if there is no mesh here,
        # the exit code lied. **freecadcmd's does, routinely.** It exits 0 on an uncaught
        # exception in the script it was handed, printing "Exception while processing file"
        # and nothing else, and its code for an explicit `sys.exit(n)` is not even stable
        # between runs: the same sys.exit(3) was observed returning 3 once and 1 the next
        # time. So the artifact is the success criterion, not the status. Checking it here
        # rather than letting os.replace raise turns "cannot find the file specified",
        # which reads like a disk problem, into a sentence naming the part that failed.
        if not os.path.isfile(src):
            raise RenderFailed(
                '%s exited without error but wrote no mesh -- look for a traceback from '
                'the renderer above (freecadcmd reports script failures on stderr and '
                'still exits 0)' % os.path.basename(dst))
        os.replace(src, dst)
        if _PREVIEWS:
            _write_preview(dst, png)

    # Submitted rather than run directly. With a serial queue -- the default -- this
    # executes immediately and behaves exactly as the direct call did; with a parallel
    # queue installed by main() it is deferred and overlapped. The definition on disk is
    # complete either way, so nothing downstream is affected by the STL arriving later;
    # none of the five call sites use the returned STL path.
    _RENDER_QUEUE.submit(make_command(definition_filepath, partial_filepath),
                         on_success=_finalize)

    # The preview PNG is rendered by _finalize above, from the finished STL, as
    # soon as that STL is in place. OpenSCAD used to produce it with a second
    # invocation carrying --render, which re-solved the whole CSG tree purely to
    # take a picture -- the dominant cost of the sweep, for an image the STL
    # already contains all the information for.
    #
    # To regenerate previews across an existing tree without re-rendering any
    # geometry -- after a camera or shading change, say -- use --previews-only:
    #     uv run python src/Fuselage/tools/fuselage_variants.py --previews-only --force
    # The path is returned either way so callers know where the preview belongs.
    return (definition_filepath, stl_filepath, png_filepath)


def stamp_geometry_version(scad_path):
    """Record which geometry sources this generated file calls into, as a comment.

    IP-FC-11. Without it `--resume` cannot see a change to the .scad modules at all: the
    generated file is a `use <>` line and a call with the parameters substituted in, so
    editing fuselage_bulkhead_geometry.scad leaves it byte for byte identical and every
    part built from it is skipped as "already rendered". The comparison this stamp feeds
    is the same one that already catches parameter changes -- the definition file grows a
    line, and nothing else in the resume path has to know.

    A comment because the generated file has to stay a file OpenSCAD will render and a
    person can run by hand. The module names ride along beside the digest so a re-render
    everywhere is self-explaining rather than mysterious.
    """
    version, modules = geometry_version.scad_version(scad_path)
    header = '// geometry-version: %s  [%s]\n' % (version, ', '.join(modules))
    with open(scad_path, encoding='utf-8') as f:
        body = f.read()
    with open(scad_path, 'w', encoding='utf-8', newline='') as f:
        f.write(header + body)


def solid_render(scad_obj, output_dir, filename):
    """Render a part with OpenSCAD, from a solid2 object."""
    solid2.set_global_fn(0)
    solid2.set_global_fa(1)
    solid2.set_global_fs(0.05)

    user_path = os.environ.get('OPENSCADPATH')

    def write_scad(path):
        solid2.scad_render_to_file(scad_obj, path)
        relativize_scad_references(path)         # same directory, so same result
        stamp_geometry_version(path)             # after relativize: it reads the refs

    def make_command(scad_path, stl_path):
        cmd = solid2.config.config.openscad_stl_command.format(
            scadfile=scad_path, stlfile=stl_path)
        return os.path.join(user_path, cmd)

    return render_definition(write_scad, '.stl.scad', make_command,
                             output_dir, filename)


def freecad_render(kind, params, output_dir, filename, variant=None):
    """Render a part with FreeCAD, from the parameter set that defines it.

    The parameters play the role the generated `.scad` plays on the other path -- they are
    what the part *is*, and they go to disk beside it for the same reason: so a resume can
    tell a stale part from a current one, and so the STL is not the only record of what
    produced it. The definition is a `.stl.json` rather than a bare `.json` so it sorts and
    globs beside its `.stl.scad` counterpart, and so a tree can hold both.
    """
    def write_params(path):
        with open(path, 'w') as f:
            f.write(freecad_render_backend.definition_text(kind, params, variant))

    def make_command(params_path, stl_path):
        return freecad_render_backend.build_command(kind, params_path, stl_path)

    return render_definition(write_params, '.stl.json', make_command,
                             output_dir, filename)


def lookup_anchor_diameter(bolt_diameter):

    anchor = read_param_csv(INSERT_TABLE)

    anchor_diam = 0;
    for a in anchor:
        if a["bolt_diameter"] == bolt_diameter:
            return a["anchor_diameter"]
            
    return 0

def decode_bulkhead_type(bulkhead_type):

    if bulkhead_type == BulkheadType.END:

        is_end = True
        is_interconnect = False
        is_cowling = False
        is_boom = False

    elif bulkhead_type == BulkheadType.INTERCONNECT:

        is_end = False
        is_interconnect = True
        is_cowling = False
        is_boom = False

    elif bulkhead_type == BulkheadType.COWLING:

        is_end = False
        is_interconnect = False
        is_cowling = True
        is_boom = False

    elif bulkhead_type == BulkheadType.TAIL_BOOM:

        is_bolt = False
        is_interconnect = False
        is_cowling = False
        is_boom = True

    else:

        is_bolt = False
        is_interconnect = False
        is_cowling = False
        is_boom = False

    return (is_end, is_interconnect, is_cowling, is_boom)

def encode_bulkhead_type(is_end, is_interconnect, is_cowling, is_boom):

    if is_end:
        bulkhead_type = BulkheadType.END
    elif is_interconnect:
        bulkhead_type = BulkheadType.INTERCONNECT
    elif is_cowling:
        bulkhead_type = BulkheadType.COWLING
    elif is_boom:
        bulkhead_type = BulkheadType.TAIL_BOOM
    else:
        bulkhead_type = BulkheadType.NULL

    return bulkhead_type

def corner_parameters(dp):
    """The corner's parameters, by name, as both backends need them.

    Extracted from the `fuselage_corner` call below so the two engines are driven from one
    mapping rather than two. A parameter added here reaches both; a parameter added to only
    one of two copies is precisely the divergence a port is most likely to introduce and
    least likely to notice, because both sides keep rendering.

    `unit_length` and `greeble_tolerance` are the corner's alone -- a bulkhead has no bay
    length (OQ-DES-C3), and the fit clearance lives entirely in the corner's bore because
    split across both halves the joint would take it twice.
    """
    return {
        'U': dp.bulkhead.U,
        'unit_length': dp.corner.length,
        'bulkhead_thickness': dp.bulkhead.thickness,
        'corner_radius': dp.corner.radius,
        'panel_thickness': dp.panel.thickness,
        'panel_offset': dp.panel.offset,
        'panel_overlap': dp.panel.overlap,
        'panel_tolerance': dp.panel.tolerance,
        'longeron_radius': dp.longeron.radius,
        'longeron_tolerance': dp.longeron.tolerance,
        'greeble_thickness': dp.greeble.thickness,
        'greeble_nub_thickness': dp.greeble.nub_thickness,
        'greeble_tolerance': dp.greeble.tolerance,
        'extrusion_width': dp.printer.extrusion_width,
        'corner_tolerance': dp.corner.tolerance,
    }


def _variant_note(dp):
    """Which combination a definition file belongs to, for a human reading it later.

    `type_name` is here because the parameter table does not distinguish the bulkhead types
    -- `end_bolt` and `interconnect` produce the same 24 numbers and differ only in which
    branch consumes them. Two definition files that describe different parts must not read
    identically, whether a person or `--resume` is doing the comparing.
    """
    return {'U': dp.bulkhead.U, 'panel_name': dp.panel.type_name,
            'is_metric': bool(dp.panel.is_metric),
            'type_name': dp.bulkhead.type_name}


def corner_render(dp, output_dir, filename):

    if _backend_for('corner') == 'freecad':
        # FX on top of the shared mapping, and only here. `fuselage_corner` in OpenSCAD has
        # no FX parameter -- it takes the finished `unit_length` -- so adding it to
        # `corner_parameters` would make the solid2 call a TypeError.
        #
        # FreeCAD needs it because `corner_tree` keeps `unit_length` as the *relationship*
        # `=U * FX * 100` rather than a number, which is deliberate: it is what lets someone
        # change U on a generated document and have the part follow. `seeded()` only
        # replaces literal rows, so an expression row survives seeding and is evaluated from
        # whatever U and FX the sheet holds. Without FX in the seed it stayed at its literal
        # 1.0, and every corner in the sweep was built at FX=1.0 -- correct at FX=1.0, and
        # silently the wrong length everywhere else (IP-FC-48).
        params = dict(corner_parameters(dp), FX=dp.corner.FX)
        freecad_render('corner', params, output_dir, filename, _variant_note(dp))
        return

    fgeom = scad_module('fuselage_corner_geometry.scad')

    # Keyword arguments, not positional. solid2 resolves these against the .scad
    # module's own signature and emits the same named parameters it always did, so
    # the generated geometry is unchanged -- but a transposition here is now a
    # TypeError rather than a part that renders cleanly and is silently wrong.
    scadobj = fgeom.fuselage_corner(**corner_parameters(dp))

    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)
    
    
def bulkhead_parameters(dp):
    """The bulkhead's parameters, by name, as both backends need them.

    The type flags are not here: they are booleans selecting *which* features exist rather
    than dimensions. `bulkhead_render` adds them to the OpenSCAD call.

    The FreeCAD generator does not take them at all -- `bulkhead_full.emit()` implements the
    end type and nothing else -- which is why `bulkhead_render` routes the other three types
    to OpenSCAD instead of handing them a table that describes them correctly and a builder
    that would ignore the distinction. Two types producing the same 24 numbers is also why
    `_variant_note` carries `type_name`.
    """
    return {
        'unit_width': dp.bulkhead.width,
        # No unit_length: a bulkhead is independent of bay length, which is why one
        # bulkhead design serves every FX and why the bulkhead sweep carries no FX
        # axis at all. It used to be passed and ignored. See OQ-DES-C3.
        'bulkhead_thickness': dp.bulkhead.thickness,
        'corner_radius': dp.corner.radius,
        'panel_thickness': dp.panel.thickness,
        'panel_offset': dp.panel.offset,
        'panel_overlap': dp.panel.overlap,
        'panel_tolerance': dp.panel.tolerance,
        'longeron_radius': dp.longeron.radius,
        'longeron_tolerance': dp.longeron.tolerance,
        'bolt_hole_radius': dp.bolt.radius,
        'bolt_thickness': dp.bolt.thickness,
        'bolt_offset': dp.bolt.offset,
        'greeble_opening_angle': dp.greeble.opening_angle,
        'greeble_thickness': dp.greeble.thickness,
        'greeble_nub_thickness': dp.greeble.nub_thickness,
        # No greeble_tolerance: the bulkhead's greeble post is nominal by
        # construction, so bulkhead_section_full does not take one. The clearance
        # is on the corner -- see corner_render above.
        'plate_thickness': dp.plate.thickness,
        'web_fillet_radius': dp.web.fillet_radius,
        'web_width': dp.web.width,
        'flange_fillet_radius': dp.bulkhead_flange.fillet_radius,
        'flange_thickness': dp.bulkhead_flange.thickness,
        'flange_chamfer': dp.bulkhead_flange.chamfer,
        'cowl_flange_height': dp.cowl_flange.height,
        'cowl_flange_tolerance': dp.cowl_flange.tolerance,
        'extrusion_width': dp.printer.extrusion_width,
    }


def bulkhead_render(dp, output_dir, filename):

    (is_end, is_interconnect, is_cowling, is_boom) = decode_bulkhead_type(dp.bulkhead.type)

    # Only the plain end type is ported (IP-FC-9). `bulkhead_full.emit()` takes no
    # is_cowling and no is_interconnect, so routing those types here would render them as
    # end bulkheads -- wrong geometry under the right filename. They fall back to OpenSCAD,
    # which is the same treatment every unported kind already gets. IP-FC-12 ports them.
    if _backend_for('bulkhead', supported=is_end) == 'freecad':
        # U on top of the shared mapping, for the reason FX is added in `corner_render`:
        # the bulkhead sheet merges `corner_tree.PARAMS`, where `corner_radius` and
        # `longeron_radius` are the relationships `=U * 10` and `=U * 2`. `bulkhead_
        # section_full` in OpenSCAD takes neither U nor those relationships -- it is handed
        # the finished radii -- so U cannot go in the shared mapping.
        #
        # Without it the sheet's U stayed at its literal 1.0 and every bulkhead was built
        # with a 10 mm corner radius and a 2 mm longeron bore whatever its size (IP-FC-48).
        params = dict(bulkhead_parameters(dp), U=dp.bulkhead.U)
        freecad_render('bulkhead', params, output_dir, filename, _variant_note(dp))
        return

    fgeom = scad_module('fuselage_bulkhead_geometry.scad')

    scadobj = fgeom.bulkhead_section_full(
        is_interconnect=is_interconnect,
        is_cowling=is_cowling,
        **bulkhead_parameters(dp))

    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)


def boom_bulkhead_parameters(dp):
    """The boom bulkhead's parameters, by name, as both backends need them.

    Every one of the 25 names `boom_bulkhead` takes, including the two flags -- unlike
    `bulkhead_parameters`, which leaves the frame bulkhead's type flags out because they are
    decoded from `dp.bulkhead.type` at the call site rather than carried as dimensions.

    The boom's two are different. `boom_make_vert_web` and `boom_make_lower_web` come
    straight off the type axis CSV as their own columns, and the FreeCAD port reads them as
    ordinary sheet rows -- 1.0 or 0.0, read in Python, never in an expression, because each
    selects between two constructions rather than scaling one. Leaving them out of the
    mapping would mean the two backends were handed different information about the same
    part, which is the divergence this file exists to prevent.

    pandas reads the CSV's TRUE/FALSE as numpy booleans. They are kept as they arrive:
    OpenSCAD's `if` accepts them, and `float()` in the JSON export turns them into the 1.0
    and 0.0 the sheet wants.
    """
    return {
        'unit_width': dp.bulkhead.width,
        'corner_radius': dp.corner.radius,
        'panel_thickness': dp.panel.thickness,
        'panel_offset': dp.panel.offset,
        'panel_overlap': dp.panel.overlap,
        'panel_tolerance': dp.panel.tolerance,
        'longeron_radius': dp.longeron.radius,
        'longeron_tolerance': dp.longeron.tolerance,
        'bolt_hole_radius': dp.bolt.radius,
        'bolt_offset': dp.bolt.offset,
        'web_fillet_radius': dp.web.fillet_radius,
        'web_width': dp.web.width,
        'boom_diameter': dp.boom_bulkhead.diameter,
        'boom_bulkhead_thickness': dp.boom_bulkhead.thickness,
        'boom_y_position': dp.boom_bulkhead.y_position,
        'boom_z_position': dp.boom_bulkhead.z_position,
        'boom_collet_thickness': dp.boom_bulkhead.collet_thickness,
        'boom_key_width': dp.boom_bulkhead.key_width,
        'boom_key_height': dp.boom_bulkhead.key_height,
        'boom_key_radius': dp.boom_bulkhead.key_radius,
        'boom_key_angle': dp.boom_bulkhead.key_angle,
        'boom_key_web_width': dp.boom_bulkhead.key_web_width,
        'boom_tolerance': dp.boom_bulkhead.tolerance,
        'boom_make_vert_web': dp.boom_bulkhead.make_vert_web,
        'boom_make_lower_web': dp.boom_bulkhead.make_lower_web,
    }


def boom_bulkhead_render(dp, output_dir, filename):

    # All three boom types are ported, so there is no per-variant `supported` here as there
    # is on the frame bulkhead. `offset_single` and `dual` set the same two flags and are
    # `ref_boom_bulkhead.scad`; `center_single` sets the other pair and is
    # `ref_boom_bulkhead_center.scad`. Both were measured against the port (IP-FC-12).
    if _backend_for('boom_bulkhead') == 'freecad':
        # No U on top of the mapping, and that differs from `bulkhead_render` on purpose.
        # The frame bulkhead's sheet merges `corner_tree.PARAMS`, where `corner_radius` and
        # `longeron_radius` are the relationships `=U * 10` and `=U * 2`, so its sheet needs
        # U to evaluate them. The boom bulkhead's modules state both as literals seeded from
        # this mapping, so nothing on its sheet reads U and a U row would sit there unused.
        freecad_render('boom_bulkhead', boom_bulkhead_parameters(dp), output_dir, filename,
                       _variant_note(dp))
        return

    fbbgeom = scad_module('fuselage_boom_bulkhead_geometry.scad')

    scadobj = fbbgeom.boom_bulkhead(**boom_bulkhead_parameters(dp))

    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)


def nose_render(U, dp, output_dir, filename, is_nose_cowl, is_nose_nose, is_nose_plate):

    cgeom = scad_module('cowl_geometry.scad')

    # Every value below now comes from the JSON parameter file via
    # derived_nose_parameters(), rather than being hard-coded to the U=1
    # nose_round_plate case as it was before.
    unit_width = dp.unit_width
    cone_angle = dp.cone_angle
    cut_len = dp.cut_len

    plate_diam = dp.plate.diameter
    plate_tol = dp.plate.tolerance
    plate_thickness = dp.plate.thickness
    plate_flange_width = dp.plate.flange_width
    plate_flange_height = dp.plate.flange_height

    nose_flange_inset = dp.nose.flange_inset
    nose_flange_height = dp.nose.flange_height

    buttress_z_offset = dp.buttress.z_offset
    buttress_r_inset = dp.buttress.r_inset
    buttress_thickness = dp.buttress.thickness
    buttress_r_start = dp.buttress.top.r_start
    buttress_r_end = dp.buttress.top.r_end

    oml_filename = oml_ref(dp.oml.filename)
    oml_scale_m_per_mm = dp.oml.scale_m_per_mm
    oml_length_m = dp.oml.length_m
    oml_offset_x_m = dp.oml.offset_x_m
    oml_reversed = dp.oml.reversed

    if is_nose_cowl:
        scadobj = cgeom.nose_cowl(
            U=U,
            unit_width=unit_width,
            oml_filename=oml_filename,
            oml_scale_m_per_mm=oml_scale_m_per_mm,
            oml_length_m=oml_length_m,
            oml_offset_x_m=oml_offset_x_m,
            oml_reversed=oml_reversed,
            cut_len=cut_len,
            buttress_thickness=buttress_thickness,
            buttress_z_offset=buttress_z_offset,
            buttress_r_start=buttress_r_start,
            buttress_r_end=buttress_r_end,
            buttress_r_inset=buttress_r_inset,
            cone_angle=cone_angle)
    elif is_nose_nose:
        # Note this one takes no oml_length_m -- the nose is cut to the plate rather
        # than to a length. Easy to miss positionally, since every neighbouring
        # argument is the same type.
        scadobj = cgeom.nose(
            U=U,
            unit_width=unit_width,
            oml_filename=oml_filename,
            oml_scale_m_per_mm=oml_scale_m_per_mm,
            oml_offset_x_m=oml_offset_x_m,
            oml_reversed=oml_reversed,
            cut_len=cut_len,
            nose_flange_height=nose_flange_height,
            nose_flange_inset=nose_flange_inset,
            plate_diam=plate_diam,
            plate_thickness=plate_thickness,
            plate_tol=plate_tol,
            cone_angle=cone_angle)
    elif is_nose_plate:
        scadobj = solid2.mirror(v=(0, 0, -1))(
            cgeom.nose_plate(
                plate_diam=plate_diam,
                plate_thickness=plate_thickness,
                plate_flange_width=plate_flange_width,
                plate_flange_height=plate_flange_height,
                cone_angle=cone_angle))

    else:
        return

    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)


def tail_render(U, dp, output_dir, filename):

    cgeom = scad_module('cowl_geometry.scad')

    # Every value now comes from the JSON parameter file via
    # derived_cowl_parameters(), matching how the nose is driven. Verified to
    # reproduce the previous hard-coded values exactly at U = 0.5, 1.0, 2.5 and
    # 4.0 -- 22 of 22 each time -- before the hard-coded block was removed.
    #
    # The tail uses five independently specified buttress groups because it is
    # mirrored about one plane; the nose needs only one because it is built
    # from an octant and repeated radially.
    b = dp.buttress

    unit_width = dp.unit_width
    cut_len = dp.cut_len
    cone_angle = dp.cone_angle

    buttress_z_offset = b.z_offset
    buttress_r_inset = b.r_inset
    buttress_thickness = b.thickness

    side_buttress_z_end = b.side.z_end
    side_buttress_r_start = b.side.r_start
    side_buttress_r_end = b.side.r_end

    top_buttress_z_end = b.top.z_end
    top_buttress_r_start = b.top.r_start
    top_buttress_r_end = b.top.r_end

    top_diag_buttress_z_start = b.top_diag1.z_start
    top_diag_buttress_depth = b.top_diag1.depth

    bottom_buttress_z_end = b.bottom.z_end
    bottom_buttress_r_start = b.bottom.r_start
    bottom_buttress_r_end = b.bottom.r_end

    oml_filename = oml_ref(dp.oml.filename)
    oml_scale_m_per_mm = dp.oml.scale_m_per_mm
    oml_length_m = dp.oml.length_m
    oml_offset_x_m = dp.oml.offset_x_m
    oml_reversed = dp.oml.reversed

    # Twenty-three arguments, of which eighteen are floats describing buttresses in
    # four groups that differ only by prefix. Positionally this was the single most
    # transposable call in the sweep.
    scadobj = cgeom.tail_cowl(
        U=U,
        unit_width=unit_width,
        oml_filename=oml_filename,
        oml_scale_m_per_mm=oml_scale_m_per_mm,
        oml_length_m=oml_length_m,
        oml_offset_x_m=oml_offset_x_m,
        oml_reversed=oml_reversed,
        cut_len=cut_len,
        buttress_thickness=buttress_thickness,
        buttress_z_offset=buttress_z_offset,
        buttress_r_inset=buttress_r_inset,
        side_buttress_z_end=side_buttress_z_end,
        side_buttress_r_start=side_buttress_r_start,
        side_buttress_r_end=side_buttress_r_end,
        top_buttress_z_end=top_buttress_z_end,
        top_buttress_r_start=top_buttress_r_start,
        top_buttress_r_end=top_buttress_r_end,
        bottom_buttress_z_end=bottom_buttress_z_end,
        bottom_buttress_r_start=bottom_buttress_r_start,
        bottom_buttress_r_end=bottom_buttress_r_end,
        top_diag_buttress_depth=top_diag_buttress_depth,
        top_diag_buttress_z_start=top_diag_buttress_z_start,
        cone_angle=cone_angle)

    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)


def axes(*names):
    """Parameter axis CSVs, resolved against PARAM_DIR rather than the cwd."""
    return [os.path.join(PARAM_DIR, n) for n in names]


# ------------------------------------------------------------
# The bulkhead families, as one table
# ------------------------------------------------------------
# A *family* is one bulkhead sweep: its own type axis, its own validity rules, its own
# parameter mapping, its own filename. The frame bulkhead and the boom bulkhead share the
# panel and size axes and nothing else, and until IP-FC-12 the difference was spread across
# `run_boom_bulkhead_parametric_sweep`, `boom_bulkhead_render` and the axis tuple each
# caller happened to type.
#
# It is gathered here because three tools outside this file need it and were each carrying a
# hard-coded copy of the frame bulkhead's half: `render_variant.py`, `export_parameters.py`
# and `compare_backends.py`. A tool that knows only one family cannot render, export or
# compare the other -- which is exactly the state the boom bulkhead port finished in, with a
# verified generator that no sweep could reach.
#
#   axis        the type CSV, which is the only axis that differs between families
#   validity    every check the family's sweep applies, in the order it applies them
#   parameters  the alias -> value mapping both backends are driven from
#   render      the function that turns a resolved variant into a part
#   filename    where that part lands
#   kind        the name `part_kinds.py` and `build_part.py` know it by
BULKHEAD_FAMILIES = {
    'bulkhead': {
        'axis': 'bulkhead_type_variants.csv',
        'validity': ('bulkhead_validity_check',),
        'parameters': 'bulkhead_parameters',
        'render': 'bulkhead_render',
        'filename': 'generate_fuselage_bulkhead_variant_filename_from_params',
        'kind': 'bulkhead',
    },
    'boom_bulkhead': {
        'axis': 'boom_bulkhead_type_variants.csv',
        'validity': ('bulkhead_validity_check', 'boom_key_validity_check'),
        'parameters': 'boom_bulkhead_parameters',
        'render': 'boom_bulkhead_render',
        'filename': 'generate_fuselage_boom_bulkhead_variant_filename_from_params',
        'kind': 'boom_bulkhead',
    },
}

# Both families share these, and neither owns them. Stated once so a caller assembling an
# axis list cannot get the frame bulkhead's panel axis and the boom's size axis.
SHARED_AXES = ('panel_variants.csv', 'bulkhead_size_variants.csv')


def family_axes(family):
    """The three axis CSVs of one bulkhead family, in the order its sweep reads them."""
    f = BULKHEAD_FAMILIES[family]
    return axes(SHARED_AXES[0], f['axis'], SHARED_AXES[1])


def family_combinations(family):
    """Every point in one family's parameter space, valid or not."""
    return flatten_param_space(read_all_param_axes(family_axes(family)))


def family_is_valid(family, dp):
    """Whether this family's sweep would generate `dp`.

    Runs every check the family declares, not just the first. The boom bulkhead adds
    `boom_key_validity_check` on top of the shared one, and a tool that applied only the
    shared check would offer to render combinations the sweep skips -- which for the boom key
    means a tab wider than the hole it keys, a part that builds and looks plausible.
    """
    ok = True
    for name in BULKHEAD_FAMILIES[family]['validity']:
        ok &= globals()[name](dp)
    return ok


def family_of(type_name):
    """Which family a bulkhead type name belongs to, read from the axis CSVs.

    So `render_variant.py 1.0 end_bolt 3/16in` and `render_variant.py 1.0 center_single 3mm`
    both work with no extra argument: the type name already says which sweep it came from.
    Read rather than hard-coded, and refused if a name ever appears on two axes -- at which
    point the type name would no longer identify a variant and every tool taking one would
    have to grow a family argument.
    """
    found = []
    for family, f in sorted(BULKHEAD_FAMILIES.items()):
        names = {row['bulkhead_type_name'] for row in read_param_csv(
            os.path.join(PARAM_DIR, f['axis']))}
        if type_name in names:
            found.append(family)
    if len(found) > 1:
        raise RuntimeError(
            'bulkhead type %r appears in %s -- the type name no longer identifies a family'
            % (type_name, ' and '.join(found)))
    return found[0] if found else None


@contextlib.contextmanager
def sweep_session(workers=None, resume=False, previews=True):
    """Configure and tear down a sweep run.

    Owns the render queue, the resume and preview settings, and -- importantly --
    the preview backfill. Any driver of the `run_*_parametric_sweep` functions
    should go through this rather than setting the pieces up itself: the backfill
    is easy to omit, and omitting it silently leaves finished parts with no image.

        with sweep_session(workers=5, resume=True):
            run_nose_parametric_sweep(axes(...), out_dir)
    """
    workers = default_render_workers() if workers is None else max(1, int(workers))
    queue = RenderQueue(workers)
    previous_queue = set_render_queue(queue)
    previous_resume = set_resume(resume)
    previous_previews = set_previews(previews)
    try:
        yield queue
        # Only on the clean path: an abandoned run should not drag its whole
        # queue of pending renders along behind the failure.
        queue.drain()
    finally:
        set_render_queue(previous_queue)
        # Captured before set_resume, which zeroes the counters.
        skipped = _RESUME_COUNTS['skipped']
        changed = _RESUME_COUNTS['changed']
        backlog = list(_PREVIEW_BACKLOG)
        set_resume(previous_resume)
        set_previews(previous_previews)

    if resume:
        print('resume: skipped %d unchanged part(s)%s'
              % (skipped,
                 ', re-rendered %d whose definition changed' % changed
                 if changed else ''),
              flush=True)

    # After the queue has closed, so the OpenSCAD renders have finished and
    # released their memory before the preview pool starts competing for it.
    if previews and backlog:
        print('previews: backfilling %d missing preview(s) across %d process(es)'
              % (len(backlog), workers), flush=True)
        failures = render_preview_batch(backlog, workers=workers)
        if failures:
            print('previews: %d failed (the parts themselves are fine)'
                  % len(failures), flush=True)


def main(workers=None, resume=False, previews=True, backend='openscad'):
    """Run all five sweeps, writing an STL and a preview PNG for every part.

    `workers` is the number of concurrent OpenSCAD renders; None picks a default
    bounded by cores and free memory, and 1 restores strictly serial behaviour.
    Override without editing code via FUSELAGE_RENDER_WORKERS.

    `resume` skips parts whose STL is already a complete mesh, so an interrupted
    run finishes instead of starting over. It trusts what is on disk, so use it
    only when the inputs have not changed since. A skipped part still gets its
    preview if that is missing.

    `previews` renders each part's PNG from its finished STL, on the worker thread,
    as soon as the STL lands. One command produces the parts and the images.

    `backend` is 'openscad' or 'freecad' (IP-FC-10). Only the corner and the bulkhead have
    FreeCAD generators; the rest of the sweep renders in OpenSCAD either way, and which is
    which is printed rather than left to be inferred from the output.
    """
    workers = default_render_workers() if workers is None else max(1, int(workers))
    budget, why = render_worker_budget()
    previous_backend = set_backend(backend)
    print('render workers: %d  (%s)' % (workers, why if workers == budget else 'explicit'),
          flush=True)
    if backend == 'freecad':
        print('backend: FreeCAD for %s; OpenSCAD for everything else, which has no '
              'FreeCAD generator yet' % ', '.join(sorted(freecad_render_backend.KINDS)),
              flush=True)
        # Stated because "bulkhead is ported" is true of the kind and false of three of its
        # five types, and a run that silently rendered those in OpenSCAD would look like a
        # run that rendered them in FreeCAD.
        print('  bulkhead: end types only -- cowling and interconnect fall back to '
              'OpenSCAD until IP-FC-12', flush=True)
        print('  %s' % freecad_render_backend.freecadcmd_path(), flush=True)
    else:
        print('backend: OpenSCAD', flush=True)
    print('previews: %s' % ('on, rendered from each STL' if previews else 'off'),
          flush=True)
    if resume:
        print('resume: skipping parts whose STL is already complete and whose definition '
              'and geometry sources are unchanged', flush=True)

    try:
        with sweep_session(workers=workers, resume=resume, previews=previews):
            _run_all_sweeps()
    finally:
        set_backend(previous_backend)


def _run_all_sweeps():

    run_corner_parametric_sweep(axes('panel_variants.csv', 'bulkhead_size_variants.csv', 'corner_size_variants.csv'), OUTPUT_DIR)

    run_bulkhead_parametric_sweep(axes('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv'), OUTPUT_DIR)

    run_boom_bulkhead_parametric_sweep(axes('panel_variants.csv', 'bulkhead_size_variants.csv', 'boom_bulkhead_type_variants.csv'), OUTPUT_DIR)

    # nose_size_variants.csv carries U *and* the print-driven nose dimensions,
    # so it replaces bulkhead_size_variants.csv as this sweep's size axis --
    # using both would multiply the two U columns into a nonsense product.
    run_nose_parametric_sweep(axes('nose_size_variants.csv',
                                   'nose_type_variants.csv'), OUTPUT_DIR)

    # The tail is now JSON-driven like the nose. It borrows the nose size axis
    # for U; the nose-only columns in it (plate/flange dimensions) are simply
    # unused by a tail, which has neither a tip nor a plate.
    run_tail_parametric_sweep(axes('nose_size_variants.csv',
                                   'tail_type_variants.csv'), OUTPUT_DIR)

if __name__ == "__main__":
    _parser = argparse.ArgumentParser(
        description='Render every fuselage variant to STL.')
    _parser.add_argument('workers', nargs='?', type=int, default=None,
                         help='concurrent OpenSCAD renders '
                              '(default: bounded by cores and free memory)')
    _mode = _parser.add_mutually_exclusive_group()
    _mode.add_argument('--resume', action='store_true',
                       help='skip parts that are already rendered and whose '
                            'definition is unchanged; parts affected by a parameter '
                            'edit, or by an edit to the geometry sources they are '
                            'built from, re-render on their own (IP-FC-11)')
    _mode.add_argument('--force', action='store_true',
                       help='re-render every part regardless of what is on disk '
                            '(the default; state it explicitly to be unambiguous, '
                            'and to override a change this tool cannot see, such '
                            'as a new OpenSCAD version or an OML mesh replaced '
                            'in place)')
    _parser.add_argument('--no-previews', action='store_true',
                         help='skip the preview PNGs (they are generated by '
                              'default, from each finished STL)')
    _parser.add_argument('--backend', choices=('openscad', 'freecad'),
                         default='openscad',
                         help='which geometry engine renders each part (IP-FC-10). '
                              'freecad applies to the corner and the bulkhead, the two '
                              'parts that have been ported; the rest of the sweep uses '
                              'OpenSCAD either way. Point FREECADCMD at freecadcmd if it '
                              'is not on PATH')
    _parser.add_argument('--previews-only', action='store_true',
                         help='render no geometry; regenerate previews for the '
                              'STLs already in variant_output. Use after a look '
                              'change -- with --force to redo every preview, '
                              'without it to fill in only the missing ones')
    _args = _parser.parse_args()
    if _args.previews_only:
        _failures = rebuild_previews(workers=_args.workers, force=_args.force)
        raise SystemExit(1 if _failures else 0)
    main(workers=_args.workers, resume=_args.resume and not _args.force,
         previews=not _args.no_previews, backend=_args.backend)

