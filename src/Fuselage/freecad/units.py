"""IP-FC-8: the project's one named unit-conversion layer.

**Unit regime of this file: it is the boundary, so it names both sides explicitly.**

The project standard is SI -- meters, seconds, kilograms, radians (doc/guidelines/general.md).
Three things on the other side of this module are not, and none of them is negotiable:

    FreeCAD's Python API   millimeters
    FreeCAD's FEM stack    N/mm^2, which is MPa
    STL and 3MF export     millimeters, because those formats carry no unit metadata and
                           a slicer reads the numbers as mm regardless

So the port has a real unit boundary, and the architecture asks for exactly one named
conversion layer rather than factors scattered through geometry code
(doc/architecture/freecad_migration.md, "The unit boundary"). This is that module.

**Why this is worth a dedicated file for six factors.** A 1000x error still renders, still
exports, still passes `isValid()`, and still looks entirely plausible on screen -- a part
drawn at 1/1000 scale is a correct-looking part. It fails at the printer, or later, in a mass
property nobody re-derived by hand. The roadmap calls this "the single easiest place in the
project to be silently wrong by 1000x". A factor written in twelve places is twelve chances to
write it once as a multiply and once as a divide; `bbox_m_matches_mm` below is the measurement
that catches it either way.

**Where the boundary is.**

    parameters (SI)  ->  THIS MODULE + kernel adapter  ->  FreeCAD API (mm)  ->  STL / 3MF (mm)

**Never call a conversion function inside geometry or analysis code.** Needing one there means
the boundary is in the wrong place, and the fix is to move the boundary rather than to convert
twice. That is why the boundary has to have a shape: a thin adapter owns the `Part::` and
`Base.Vector` calls and converts at them, while the geometry modules hold SI and never see the
factor.

**That adapter does not exist yet, and until it does the port is non-conforming.** An earlier
version of this docstring said the opposite -- that "everything from the FreeCAD API inward is
millimeters and stays that way", and that a geometry module carrying bare millimeter rows was
therefore correct. It is not correct, and this file was the wrong place to say so: the standard
is `doc/guidelines/general.md`, which requires every stored value to be SI and confines non-SI to
a narrow file-interface layer that never propagates inward. A module cannot grant itself an
exemption from a guideline. Measured 2026-10-31: 46 of 79 port modules hold 173 module-level
millimeter constants. IP-FC-158 through IP-FC-161 close it.

**The SI side has no members yet, and this module is written before it does.** The port's
parameters still come from `fuselage_variants.derived_parameters()`, which is the OpenSCAD
sweep's, and that path is millimeters throughout by a deliberate exemption that is not going to
change (doc/guidelines/general.md, "The OpenSCAD path stays in millimeters"). So millimeters
enter the port at its inputs, before any constant in any geometry module is reached, and
IP-FC-159 gives the port a parameter layer of its own that is SI from its first line. That is
also why this file defines a boundary instead of servicing a busy one: the factor and the check
exist in one place from the start, rather than being introduced later alongside the first code
that needs them, when a wrong sign would arrive with them.

The exemption does not reach the port, and the difference is structural rather than a matter of
degree. In the OpenSCAD path the geometry layer is a separate language in a generated file, which
makes the emission step a genuine file interface -- the guidelines name it as one. The port's
geometry layer is project Python with no file between it and the kernel, so nothing in it is
"the narrow layer that reads a parameter file or writes a geometry file".

The OpenSCAD path is exempt and is never converted. A `_mm` name in that code is accurate.

**One other place writes this factor, deliberately.** `tools/oml_export.py` carries
`MODEL_UNIT_MM = 1000.0`, and it is not a duplicate of `MM_PER_M` even though the number is
the same. It states a *convention* -- one OpenVSP model unit is one meter -- about a program
whose geometry is dimensionless, and it composes with this module's factor rather than
repeating it. It also lives on the far side of an interpreter boundary: that script runs under
OpenVSP's Python, not under `freecadcmd`, and importing across for a constant would buy less
than it risks. If a third copy of 1000 ever appears, that one is a duplicate and belongs here.
"""
from __future__ import annotations

import math

#: Millimeters in one meter. The only length factor in the project.
MM_PER_M = 1000.0

#: Meters in one millimeter. Defined as its own literal rather than as `1 / MM_PER_M` so that
#: neither direction is the derived one -- a reader checking a call site should not have to
#: work out which way round the division went.
M_PER_MM = 0.001

#: Area and volume factors, derived once here rather than written as `MM_PER_M ** 2` at each
#: use. A squared or cubed factor is the easiest of all to get wrong by hand, and the error is
#: a million or a billion rather than a thousand -- large enough to be caught, which is exactly
#: why it is worth not relying on being caught.
#:
#: **Here rather than in `si.py`, which is where they started.** They are pure conversion
#: factors with nothing FreeCAD about them, and `measure.py` needs the volume one while
#: deliberately importing no FreeCAD API at all so it stays readable under any interpreter.
#: `si.py` re-exports both, so every existing `si.MM3_PER_M3` call site is unaffected.
MM2_PER_M2 = MM_PER_M * MM_PER_M
MM3_PER_M3 = MM_PER_M * MM_PER_M * MM_PER_M

#: Pascals in one megapascal. FreeCAD's FEM stack works in N/mm^2, and 1 N/mm^2 is exactly
#: 1 MPa, so this is the whole of the stress conversion. Treat that stack as file interface:
#: convert on the way out of it and never let MPa into project code.
PA_PER_MPA = 1.0e6


# --------------------------------------------------------------------------------
# What unit a generated document declares itself to be in
# --------------------------------------------------------------------------------
#
# **A file that cannot say which unit it is in cannot be checked, and this one could not.**
# Both generated parameter documents -- `tools/export_parameters.py`'s variant file and
# `tools/freecad_render.py`'s definition file -- have always carried a `units` field, and
# **nothing read it**: it was prose for a human, not a checked value. A millimeter document
# and a meter document were therefore indistinguishable to every consumer, and four readers
# load one without going through `freecad/parameters.py` at all. OQ-ARCH-25 moves
# `derived_parameters()` to meters, which changes what these files mean, so the field becomes
# a token a reader refuses on (IP-FC-159).
#
# The tokens name the unit of the document's *length* values. Angles are degrees in both
# documents and are not part of the token, because no document has ever carried radians and
# inventing a spelling for a case that does not exist would be guessing at a format.

#: Lengths in millimeters.
PARAM_UNITS_MM = 'mm'

#: Lengths in meters.
PARAM_UNITS_M = 'm'

#: Every token a reader may accept, in the order a listing should show them.
PARAM_UNITS = (PARAM_UNITS_MM, PARAM_UNITS_M)

#: The long spelling both writers emitted before the field was a token, and still the value
#: `tools/freecad_render.definition_text` writes. Read as `mm`.
#:
#: **It is public, and the definition file keeps it, because that text is what `--resume`
#: compares byte for byte.** Replacing it with `PARAM_UNITS_MM` would be a pure wording change
#: that marks all 576 parts stale, so the guard was introduced without touching it. The
#: variant file from `tools/export_parameters.py` has no byte-comparison consumer and writes
#: the short token. Both are the same unit, which is the point of normalizing them here rather
#: than letting each reader match strings.
PARAM_UNITS_MM_LEGACY = 'mm and degrees, as the OpenSCAD path uses them'

_TOKEN_OF = {PARAM_UNITS_MM: PARAM_UNITS_MM,
             PARAM_UNITS_M: PARAM_UNITS_M,
             PARAM_UNITS_MM_LEGACY: PARAM_UNITS_MM}


def param_units_token(declared):
    """The token `declared` means, or `None` when it means nothing this version knows.

    `None` is the answer for a missing field and for an unrecognized one alike, and the caller
    refuses on both. **Those two cases must not be told apart by defaulting**: a document with
    no `units` is older than the guard, and one with an unknown `units` is newer than this
    reader -- and guessing `mm` for either is precisely the silent 1000x error the guard
    exists to prevent.
    """
    if declared is None:
        return None
    return _TOKEN_OF.get(str(declared).strip())


def m_to_mm(value):
    """Meters to millimeters, crossing out of SI into FreeCAD's API or a mesh export."""
    return value * MM_PER_M


def mm_to_m(value):
    """Millimeters to meters, crossing into SI.

    This is the direction that reads a mesh, a FreeCAD measurement, or the OpenSCAD sweep's
    output. New code consuming the sweep converts here and says so, rather than reaching into
    the sweep and changing it.
    """
    return value * M_PER_MM


def mpa_to_pa(value):
    """N/mm^2 to pascals, crossing out of FreeCAD's FEM stack into SI."""
    return value * PA_PER_MPA


def pa_to_mpa(value):
    """Pascals to N/mm^2, crossing into FreeCAD's FEM stack."""
    return value / PA_PER_MPA


# Angles delegate to the standard library, which is already one unambiguous place and needs no
# wrapping. They are re-exported here anyway so that "the project's unit conversions" is a
# single import rather than a rule with an exception a reader has to remember.
rad_to_deg = math.degrees
deg_to_rad = math.radians


def bbox_m_matches_mm(bbox_m, bbox_mm, rel_tol=1.0e-6):
    """Check an SI bounding box against the same part measured in millimeters.

    The test the roadmap names for this boundary: a ported part's bounding box in meters must
    equal the OpenSCAD part's bounding box in millimeters divided by 1000. It is worth having
    as a function rather than an assertion at one call site because it is the only check that
    fails loudly on the error this module exists to prevent, and because a scale error is the
    one defect that every other check in this project passes.

    Both boxes are `(xmin, ymin, zmin, xmax, ymax, zmax)`, matching `compare_backends`.

    The tolerance is **relative to the millimeter figure**, not absolute. An absolute tolerance
    means completely different things on a 50 mm corner and a 400 mm cowl, which is the same
    defect that cost two silent forty-minute runs in IP-FC-56 -- see `check_unread_rows.py`.
    A near-zero coordinate is compared against the box's own largest extent instead, since a
    face that sits on the origin has no magnitude of its own to be relative to.

    Returns `(ok, report)`. `report` is a list of `(axis, expected_m, actual_m, rel_error)`
    for the components that disagree, empty when they all agree -- so a caller can say which
    axis is wrong rather than only that something is.
    """
    if len(bbox_m) != 6 or len(bbox_mm) != 6:
        raise ValueError('a bounding box is six numbers (xmin, ymin, zmin, xmax, ymax, zmax), '
                         'got %d and %d' % (len(bbox_m), len(bbox_mm)))

    names = ('xmin', 'ymin', 'zmin', 'xmax', 'ymax', 'zmax')
    # The scale of the part, used for the components that sit at or near zero.
    extent_mm = max(abs(v) for v in bbox_mm) or 1.0

    report = []
    for name, actual_m, value_mm in zip(names, bbox_m, bbox_mm):
        expected_m = mm_to_m(value_mm)
        denominator = abs(expected_m) if abs(value_mm) > extent_mm * 1.0e-9 \
            else mm_to_m(extent_mm)
        error = abs(actual_m - expected_m) / denominator
        if error > rel_tol:
            report.append((name, expected_m, actual_m, error))

    return not report, report


def describe_bbox_mismatch(report):
    """Format `bbox_m_matches_mm`'s report, naming the likely cause of a 1000x miss.

    A scale error does not look like a scale error in a table of numbers -- it looks like a
    part in the wrong place. Saying so where the failure is printed saves the reader deriving
    it, which is the whole reason this check is separate from a general geometry comparison.
    """
    if not report:
        return 'bounding boxes agree'

    lines = ['%d of 6 bounding-box components disagree:' % len(report)]
    for name, expected_m, actual_m, error in report:
        lines.append('  %-4s expected %.9g m, measured %.9g m  (%.3g relative)'
                     % (name, expected_m, actual_m, error))
        if expected_m and abs(actual_m / expected_m - MM_PER_M) < 1.0:
            lines.append('       measured is about 1000x expected -- a value in millimeters '
                         'is being read as meters')
        elif actual_m and abs(expected_m / actual_m - MM_PER_M) < 1.0:
            lines.append('       measured is about 1/1000 of expected -- a value in meters '
                         'is being written where millimeters are wanted')
    return '\n'.join(lines)
