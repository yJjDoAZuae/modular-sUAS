"""IP-FC-5: shared parameters and the corner's 2D section, in Part:: primitives.

`corner_middle_shape` is the one profile every axial section of the corner extrudes -- the
middle run, the two ends and the two transitions all start from it. It is factored out here
for the same reason it is a separate module in the OpenSCAD source.

Everything is built as 3D prisms rather than 2D faces: each cut in the profile is a prism of
constant cross-section, so extruding first and differencing in 3D gives the same result with
fewer 2D-boolean edge cases.

Parameters are a value object rather than module constants, so a regenerate is a new
`Params(U=...)` and a re-run -- the Part:: paradigm has no stored feature tree to update.

**Unit regime: SI, converted at the kernel through `si.py` (IP-FC-160).** Every length on
`Params` and every argument to the geometry helpers below is in meters. The FreeCAD shapes they
return hold millimeters, because that is what OpenCASCADE stores -- so a measurement taken off
one comes back through `si.volume_m3` and friends rather than off `shape.Volume`.

**The parameter *spreadsheet* is a separate thing and stays millimeters.** `build_sheet` writes
a FreeCAD `Spreadsheet::Sheet`, which is a document artifact whose expressions FreeCAD evaluates
in its own units, and `check_seed` compares it against `derived_parameters()`, which is the
exempt OpenSCAD path. So the `PARAMS` alias tables, the seed, and everything in this file that
touches them are millimeters by the same rule that makes an exported STL millimeters: they
belong to something outside the library. `Params` is the library's own value object and is SI.
"""
import os
import sys

import FreeCAD as App
import Part

import si

# Everything these scripts write goes here, and nothing here is source. The scripts used to
# save beside themselves, which put `.FCStd` documents, their rotating `.FCStd1` backups,
# `.step` exports, check meshes and a whole `preview/` tree into the source directory --
# and two of them into git, where a 440 KB binary was rewritten on every check run.
#
# One directory rather than a system temp dir, because several of these are a producer and a
# consumer that have to agree: check_tree.py writes `regen_U*.stl` for check_regenerate.py,
# pd_end.py writes the document verify_pd_end.py reloads. A path that vanishes between runs
# would break those pairs, and being able to open the artifact after a failed check is most
# of what makes these scripts useful.
_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')


def out_path(*parts):
    """A path under `freecad/out/`, with the directory created. Never beside the source."""
    path = os.path.join(_OUT_DIR, *parts)
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    return path


# Only unit_width, unit_length, corner_radius and longeron_radius scale with U; the
# thicknesses, overlaps and tolerances are user parameters that do not. See
# scaled_standard_values() in fuselage_variants.py and the "1.0U parameters" block in
# fuselage_corner.scad.


class Params(object):
    """One variant's parameters, **in meters** (IP-FC-160).

    Every default below is the same physical value it has always been, written in the project's
    units: `bulkhead_thickness` is 6 mm and so is `0.006`. The millimeter figures are kept in
    the comments beside them, because every number this project has recorded is a millimeter
    number and a reader checking one against a drawing should not have to convert in their head.

    `from_mm` is the constructor for the millimeter side -- a seed read from
    `derived_parameters()`, which is the exempt OpenSCAD path. That is the only place a
    millimeter value should enter.
    """

    def __init__(self, U=1.0, FX=1.0, bulkhead_thickness=0.006, panel_thickness=0.00477,
                 panel_offset=0.0, panel_overlap=0.004, panel_tolerance=0.0001,
                 longeron_tolerance=0.00005, greeble_thickness=0.0008,
                 greeble_tolerance=0.00005, extrusion_width=0.0004,
                 greeble_nub_thickness=None):
        self.U, self.FX = U, FX
        self.unit_length = 0.100 * U * FX           # 100 mm at U = 1
        self.corner_radius = 0.010 * U              # 10 mm at U = 1
        self.longeron_radius = 0.002 * U            # 2 mm at U = 1

        self.bulkhead_thickness = bulkhead_thickness
        self.panel_thickness = panel_thickness
        self.panel_offset = panel_offset
        self.panel_overlap = panel_overlap
        self.panel_tolerance = panel_tolerance
        self.longeron_tolerance = longeron_tolerance
        self.greeble_thickness = greeble_thickness
        self.greeble_tolerance = greeble_tolerance
        self.extrusion_width = extrusion_width
        # greeble_nub_thickness_of() is the identity today; the driver sets them equal.
        self.greeble_nub_thickness = (greeble_thickness if greeble_nub_thickness is None
                                      else greeble_nub_thickness)

        self.eps = 0.00001                           # geometry_eps(), 0.01 mm
        self.longeron_chamfer = extrusion_width
        self.far = 2.0 * self.corner_radius          # mask_reach()

        # greeble derived values (fuselage_corner_geometry.scad)
        self.greeble_radius = (self.longeron_radius + longeron_tolerance
                               + greeble_thickness + greeble_tolerance)
        self.greeble_nub_radius = self.greeble_radius + self.greeble_nub_thickness
        self.greeble_nub_height = bulkhead_thickness / 3.0

        # flat_offset uses longeron_chamfer as a floor, so the flat face clears the bore
        # and its chamfer *and* whatever the panel interface has been pushed out to.
        self.flat_offset = -max(
            self.longeron_radius + longeron_tolerance + self.longeron_chamfer,
            (panel_overlap + panel_offset)
            - (self.corner_radius - panel_thickness - panel_tolerance))
        self.flat_x = -(panel_overlap + panel_offset)
        self.flat_y = self.flat_offset - self.flat_x

    #: Keyword arguments that are lengths, so `from_mm` converts exactly these and nothing
    #: else. `U` and `FX` are dimensionless multipliers and must not be touched -- scaling a
    #: multiplier by 1/1000 is the one error in this conversion that would not look like a
    #: scale error, because it moves the part's size without moving any stated dimension.
    LENGTHS = ('bulkhead_thickness', 'panel_thickness', 'panel_offset', 'panel_overlap',
               'panel_tolerance', 'longeron_tolerance', 'greeble_thickness',
               'greeble_tolerance', 'extrusion_width', 'greeble_nub_thickness')

    @classmethod
    def from_mm(cls, **kwargs):
        """`Params` from a millimeter parameter set -- the seed boundary, and the only one.

        `derived_parameters()` belongs to the exempt OpenSCAD path and is millimeters
        throughout, so a seed read from it crosses into SI here. An unknown key is passed
        through untouched rather than converted, so a dimensionless addition to the parameter
        set does not silently become a thousandth of itself; a length added to the set must be
        added to `LENGTHS` as well, and `check_corner_common.py` asserts the two agree.
        """
        converted = {}
        for key, value in kwargs.items():
            if key in cls.LENGTHS and value is not None:
                converted[key] = si.m(value)
            else:
                converted[key] = value
        return cls(**converted)


def through_cut(extent):
    """Length for a *centered* cutting solid that must pass entirely through `extent`."""
    return 3.0 * extent


def is_entry_point(name):
    """True when `name` is the module freecadcmd was handed on the command line.

    `if __name__ == '__main__'` does not work under freecadcmd: it *imports* the script as
    a module named after the file's basename, so __name__ is 'part_end', never '__main__',
    and the guard silently suppresses the whole script. Compare against argv instead.
    """
    if name == '__main__':
        return True
    for arg in sys.argv:
        if arg.endswith('.py') and os.path.splitext(os.path.basename(arg))[0] == name:
            return True
    return False


def script_args():
    """The arguments meant for the script, with freecadcmd's own tokens removed.

    Two things have to come out of `sys.argv`. The script paths, because freecadcmd puts the
    file it is running there. And `--pass`, which is freecadcmd's escape for arguments meant
    for the script rather than for itself -- it forwards the token *as well as* the value, so
    a script that filters only `.py` reads the flag as its first argument.

    That failure is quiet in the worst way: the run dies on a file-not-found naming `--pass`,
    which reads like a malformed command line rather than like the script ignoring a flag it
    was handed. Six scripts had their own copy of this filter and five of them had this bug,
    so it is stated once here.
    """
    return [a for a in sys.argv[1:] if a != '--pass' and not a.endswith('.py')]


def is_literal(value):
    """True when a PARAMS row carries a plain number rather than an expression.

    The distinction is the whole of IP-FC-41: literal rows are *configuration* -- one
    variant's parameter values -- and belong to `derived_parameters()`. '=' rows are the
    *port*: the relationships the OpenSCAD source defines between those values, which no
    parameter set can supply and which have to agree between modules.
    """
    text = str(value).strip()
    if text.startswith('='):
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


# The literal rows no parameter table is required to supply, and why each is exempt.
#
# **Every other literal row is configuration and MUST come from `derived_parameters()`** --
# that is `is_literal`'s rule above, and until IP-FC-53 nothing made it true. `check_seed`
# walks the *seed* and compares each value it carries against the sheet, so a value the
# authority supplies is verified and a literal row the authority *fails* to supply is never
# looked at. A parameter file missing rows therefore built a part with the module's own
# reference values silently substituted for the variant's, under the variant's filename.
#
# This list is what lets the opposite check exist. Without it "every literal must be seeded"
# cannot be asserted, because nine rows legitimately cannot be -- and they are indistinguishable
# in the table from the ones that must, all nine being plain numbers like the rest.
#
# Keyed by alias rather than by module because aliases are already effectively global:
# `merge_params` refuses one that means two different things on a shared sheet.
# **`FX`, `unit_length`, `greeble_tolerance` and `mid_h` were here, exempted as a symptom
# rather than fixed.** They reached the bulkhead's sheet only because `bulkhead_section`
# merged the whole of `corner_tree.PARAMS` to reuse `corner_end`, and no bulkhead geometry read
# any of them -- setting FX to 7.0 on a built bulkhead and recomputing left the volume unchanged
# to the last digit, as did perturbing the other three, confirmed independently by
# `check_reachable_rows.py`'s expression-graph walk across all seven type/panel combinations a
# bulkhead has. **IP-FC-56, done 2026-09-10**: `bulkhead_section.py` now merges a filtered view
# of `corner_tree.PARAMS` that drops these and 22 more rows proved dead the same way, so none
# of the 26 reach the bulkhead's sheet at all and none of them need an exemption here anymore.
# `corner_tree.py` itself is untouched -- the corner's own sheet still carries every one of
# them, `FX` and `greeble_tolerance` genuinely are the corner's own design parameters, and its
# geometry reads both.
#
# `corner_tolerance` is NOT one of those, and is placed with `gt_tolerance` instead. The
# bulkhead does read it -- `bulkhead_section` reuses `corner_end` to cut the greeble socket --
# and the value it reads is a deliberate 0, exactly as `gt_tolerance` is.
UNSEEDED = {
    'eps': 'a constant of the OpenSCAD source, not a parameter -- geometry_eps(). IP-FC-49 '
           'and IP-FC-50 measured what it is for and zeroed the two uses that had none, and '
           'IP-FC-55 is auditing whether FreeCAD needs the rest of them at all',
    'mask_eps': 'the same constant at the diagonal mask, kept named rather than dropped so a '
                'reader can see the source says `+ eps` on purpose. Already 0.0',
    'end_z0': 'where the port places the end section in z. A construction choice of the port, '
              'and not a dimension of the part: the source has no such value',
    'gt_tolerance': 'the clearance the greeble TOOL is built at, which is always 0 -- the tool '
                    'forms the bulkhead post, and the post is nominal by construction because '
                    'the whole fit clearance is carried on the corner bore. Distinct from '
                    '`greeble_tolerance`, which is the corner-side parameter',
    'corner_tolerance': 'the clearance the corner\'s two seating faces are built at when the '
                        'BULKHEAD builds them, which is always 0. `bulkhead_section` reuses '
                        '`corner_end` to cut the greeble socket, and that socket has to be '
                        'nominal: the corner takes the whole clearance on its own copy of the '
                        'same shape, so seeding this row would apply it twice and the joint '
                        'would end up with a gap it was never designed for. The seed boundary '
                        'is what enforces it -- bulkhead_parameters() does not export the row, '
                        'exactly as it does not export greeble_tolerance. On the CORNER\'s '
                        'sheet the row is seeded normally, from corner_parameters(). OQ-DES-C5',
}


def check_unseeded(params, seed):
    """Literal rows the seed does not supply and this file does not exempt.

    The mirror of `check_seed`, and the half that was missing. That one asks "is every value
    the authority gave reproduced by the sheet"; this asks "did the authority give every value
    the sheet needs". A part can pass the first and still be built at the module's reference
    configuration, which is the failure IP-FC-53 closes.
    """
    return sorted(alias for alias, value in params
                  if is_literal(value) and alias not in seed and alias not in UNSEEDED)


def seeded(params, seed=None):
    """`params` with its literal rows replaced by the exported parameter set.

    A row is only replaced when the authority actually defines it -- the rows it never
    defines are `UNSEEDED` above, and `check_unseeded` refuses any others.
    """
    if not seed:
        return list(params)
    out = []
    for alias, value in params:
        if is_literal(value) and alias in seed:
            out.append((alias, repr(float(seed[alias]))))
        else:
            out.append((alias, value))
    return out


def build_sheet(doc, params, seed=None, extra=()):
    """The parameter sheet, seeded from `derived_parameters()` when `seed` is given.

    Left alone if the document already has one: the assembly builds a single merged sheet
    and then calls each constituent's geometry against it.

    **A seed must cover every literal row it is not exempt from.** Checked here rather than in
    `build_part.py` so it holds for every route to a seeded sheet, including the modules' own
    `main()` when handed a parameter file. A run with no seed at all is the reference check,
    where the literals are the configuration being measured and are the point.
    """
    rows = list(params) + list(extra)
    if seed:
        missing = check_unseeded(rows, seed)
        if missing:
            # stderr and flushed, not the message of a SystemExit: freecadcmd discards that,
            # and a refusal nobody can read is barely better than the wrong part it stopped.
            sys.stderr.write(
                'build_sheet: the parameter set does not define %s.\nThese are literal rows, '
                'which means configuration -- they belong to derived_parameters(), and the '
                'part would otherwise be built with this module\'s own reference values '
                'silently substituted for the variant\'s. If one of them is genuinely not a '
                'parameter, add it to corner_common.UNSEEDED with the reason.\n'
                % ', '.join(missing))
            sys.stderr.flush()
            raise SystemExit(1)

    sheet = doc.getObject('Params')
    if sheet is not None:
        return sheet
    sheet = doc.addObject('Spreadsheet::Sheet', 'Params')
    for row, (alias, value) in enumerate(seeded(rows, seed), start=1):
        sheet.set('A%d' % row, alias)
        sheet.setAlias('B%d' % row, alias)
        # **A cell is text, and two of the cowl modules hand this floats.** `cowl_tree` runs
        # its tables through `_as_cells` at import time; `cowl.PARAMS_NOSE_TIP` and
        # `PARAMS_NOSE_PLATE` cannot, because those same tables are *also* the reference
        # configuration handed to the builder, which wants numbers. So the coercion belongs
        # here, where it is a property of the spreadsheet rather than of any one table.
        #
        # Measured 2026-09-06: without it `cowl_nose_tip.emit(doc)` and
        # `cowl_nose_plate.emit(doc)` raise `TypeError: set() argument 2 must be str, not
        # float`, while `cowl_nose_cowl` and `cowl_tail` build -- four sibling modules
        # presenting one interface, two of which could not honor it unseeded. It went
        # unnoticed because `cowl.main()`, the reference check for those two, calls the
        # builder directly and never makes a sheet.
        #
        # `repr(float(v))` is the spelling `_as_cells` and `seeded` already use, so a value
        # arriving by any of the three routes formats identically and the definition files
        # stay byte-comparable (IP-FC-11).
        sheet.set('B%d' % row, value if isinstance(value, str) else repr(float(value)))
    doc.recompute()
    return sheet


def merge_params(sources, seed=None):
    """The union of several modules' alias tables, with conflicting definitions refused.

    Kept as a permanent assertion rather than a one-off audit, because the failure is
    silent: FreeCAD would take whichever definition landed in the row and the geometry
    would quietly follow the wrong one.

    A seed exempts the rows it supplies. Two modules disagreeing on what `panel_offset` is
    stops meaning anything once both take it from the same authority -- but disagreeing on
    a '=' row still does, and so does disagreeing on a literal the authority never defines.

    Where one module states a relationship and another states this variant's value --
    `corner_radius` is `=U * 10` in corner_tree and 10.0 in the bulkhead modules -- the
    RELATIONSHIP wins. Both are true, but only one of them survives the user changing U,
    and a sheet whose corner_radius stops tracking U is a worse deliverable than one whose
    rows are redundant. `check_seed` then confirms the expression reproduces the authority's
    number, which is a stronger check than either row on its own: it tests the port's
    derivations against `derived_parameters()`, not just its constants.
    """
    merged, at, owner = [], {}, {}
    for mod in sources:
        for alias, value in mod.PARAMS:
            if alias not in owner:
                owner[alias], at[alias] = (mod, value), len(merged)
                merged.append((alias, value))
                continue
            prev_mod, prev_value = owner[alias]
            if prev_value == value:
                continue
            if seed and alias in seed:
                if is_literal(prev_value) and not is_literal(value):
                    owner[alias] = (mod, value)
                    merged[at[alias]] = (alias, value)
                if is_literal(prev_value) != is_literal(value) or is_literal(value):
                    continue
            raise RuntimeError(
                'alias %r means two different things: %r in %s, %r in %s -- rename one '
                'before they share a sheet'
                % (alias, prev_value, prev_mod.__name__, value, mod.__name__))
    return merged


def check_seed(sheet, seed):
    """Every seeded alias the sheet carries, against the value the authority gave.

    Rows the seed replaced are trivially equal. The ones that matter are the expression
    rows kept in preference to a literal: this is where a derivation the port transcribed
    from the OpenSCAD source is measured against what `derived_parameters()` computes.
    """
    bad = []
    for alias in sorted(seed):
        try:
            got = float(sheet.get(alias))
        except Exception:
            continue                      # not an alias any module on this sheet declares
        if abs(got - float(seed[alias])) > 1e-9:
            bad.append((alias, got, float(seed[alias])))
    return bad


def prism_mm(points, z0, h):
    """A polygon extruded through `h` starting at `z0`, **in millimeters**.

    **Transitional, and named so it cannot be mistaken for the SI form.** `si.prism_m` is the
    one to use; this exists only for `cowl.py`'s three call sites, which are still millimeters
    until the cowl family is converted under IP-FC-160. Delete it with the last of them.
    """
    pts = [App.Vector(x, y, z0) for x, y in points]
    pts.append(pts[0])
    return Part.Face(Part.makePolygon(pts)).extrude(App.Vector(0, 0, h))


def half_shape(p, z0, h):
    """One half of the profile, before the diagonal mirror. All lengths in meters."""
    far = p.far
    solid = si.cylinder_m(p.corner_radius, h, si.vec_m(0, 0, z0))

    # rectangular extension carrying the panel interface outboard
    w = p.panel_overlap + p.panel_offset - p.panel_tolerance
    solid = solid.fuse(si.box_m(w, p.corner_radius, h, si.vec_m(-w, 0, z0)))

    # longeron bore
    solid = solid.cut(si.cylinder_m(p.longeron_radius + p.longeron_tolerance, h,
                                    si.vec_m(0, 0, z0)))

    # panel slot
    solid = solid.cut(si.box_m(
        2 * p.panel_overlap, 2 * p.panel_thickness + 2 * p.panel_tolerance, h,
        si.vec_m(-2 * p.panel_overlap - p.panel_offset + p.panel_tolerance,
                 p.corner_radius - p.panel_thickness - p.panel_tolerance, z0)))

    # bulkhead boundary
    solid = solid.cut(si.prism_m([
        (p.flat_x, p.corner_radius), (p.flat_x, p.flat_y), (p.flat_offset, 0),
        (0, p.flat_offset), (p.flat_y, p.flat_x), (0, -far), (-far, -far), (-far, far)],
        z0, h))

    # diagonal mirror-line mask
    solid = solid.cut(si.prism_m([(-far, -far), (far, far), (far, -far)], z0, h))

    # longeron chamfer
    solid = solid.cut(si.prism_m([(0, 0), (-far, 0), (-far, -far), (0, -far)], z0, h))
    return solid


def section(p, z0, h):
    """The full profile -- mirror_xy() of the half -- extruded from `z0` through `h`."""
    half = half_shape(p, z0, h)
    # mirror_xy(): mirror([1,-1,0]), i.e. reflect across the plane normal to (1,-1,0)
    full = half.fuse(half.mirror(App.Vector(0, 0, 0), App.Vector(1, -1, 0)))
    return full.removeSplitter()


#: How far a measured bounding box may sit from its recorded one, in meters. One micron -- the
#: same figure as the `1e-3` mm the reference modules each carried before the conversion. A
#: bounding box is exact arithmetic on the sheet's own expressions, so this bounds a wrong
#: expression and not a kernel tolerance.
BBOX_TOL_M = 1.0e-6


def report(name, shape, ref_volume_m3, tol=1e-4, expect_bbox_m=None, source='OpenSCAD, faceted',
           bbox_tol_m=BBOX_TOL_M):
    """Print the comparison IP-FC-5 is built to make, and say whether it passed.

    **Compared in SI, printed in millimeters.** The reference is cubic meters like every other
    stored value, and the measurement is taken through `si.volume_m3` rather than off
    `shape.Volume`, which is mm3. The figures are *printed* in mm because this is a human-facing
    report and because every volume this project has recorded is a mm3 figure -- a report that
    silently changed units would make a decade of recorded numbers unreadable against it. The
    units are named on each line so the two cannot be confused.

    **Found and fixed while writing check_plane2d.py (IP-TEST-7).** This used to print the
    delta and nothing else -- no tolerance, no verdict, no return value -- so `part_corner.py`
    /`part_end.py`/`part_middle.py`/`part_transition.py`'s `main()` always exited 0 whatever
    the volume actually came out to; a real regression here was visible only to someone
    reading the printed percentage by eye. `tol` matches `check_tree.py`'s own bar for the
    same Part:: corner (`abs(d) / ref > 1e-4`), since this is that check's static-port
    ancestor. Also requires a valid, single-solid shape -- a plausible volume on a shape that
    is not one solid is not a part.

    **`expect_bbox_m` is the recorded bounding box, in meters**, as
    `(xmin, ymin, zmin, xmax, ymax, zmax)`. Supplying it is what lets the reference modules --
    `simple_positives`, `greeble_web`, `bulkhead_positive` and the rest -- share this function
    instead of each carrying its own copy of the same comparison. They each had one, and every
    copy was a place for the millimeter-to-meter conversion to be made differently.
    """
    bb = si.bbox_m(shape)
    volume_m3 = si.volume_m3(shape)
    valid, n_solids = shape.isValid(), len(shape.Solids)
    print('PART:: %s' % name)
    print('  volume  = %.6f mm3' % (volume_m3 * si.MM3_PER_M3))
    print('  bbox    = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f] mm'
          % tuple(v * si.MM_PER_M for v in bb.as_tuple()))
    if expect_bbox_m is not None:
        print('  expect  = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f] mm'
              % tuple(v * si.MM_PER_M for v in expect_bbox_m))
    print('  valid   = %s   solids=%d faces=%d' % (valid, n_solids, len(shape.Faces)))
    print('  ref     = %.6f mm3  (%s)' % (ref_volume_m3 * si.MM3_PER_M3, source))
    d = volume_m3 - ref_volume_m3
    rel = d / ref_volume_m3
    print('  delta   = %+.6f mm3  (%+.4f%%)' % (d * si.MM3_PER_M3, 100 * rel))

    moved = None
    if expect_bbox_m is not None:
        moved = max(abs(a - b) for a, b in zip(bb.as_tuple(), expect_bbox_m))
        if moved > bbox_tol_m:
            print('  bbox    = MOVED by %.6f mm' % (moved * si.MM_PER_M))

    ok = (valid and n_solids == 1 and abs(rel) <= tol
          and (moved is None or moved <= bbox_tol_m))
    print('  result  = %s' % ('PASS' if ok else 'FAIL'))
    return ok
