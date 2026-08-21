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

**Where the boundary is, and where it is not.**

    parameters (SI)  ->  THIS MODULE  ->  FreeCAD API (mm)  ->  STL / 3MF (mm)

Everything from the FreeCAD API inward is millimeters and stays that way. The ported geometry
modules in this directory call `Part::` with millimeter numbers because that is the API's unit,
not because they are unconverted -- so `fillets.py` carrying bare millimeter rows is correct,
and "fixing" it would be the error. **Never call a conversion function inside geometry or
analysis code.** Needing one there means the boundary is in the wrong place, and the fix is to
move the boundary rather than to convert twice.

**The SI side has no members yet, and this module is written before it does.** The port's
parameters still come from `fuselage_variants.derived_parameters()`, which is the OpenSCAD
sweep's, and that path is millimeters throughout by a deliberate exemption that is not going to
change (doc/guidelines/general.md, "The OpenSCAD path stays in millimeters"). So today every
number crossing into the port is already mm and needs no conversion at all. That is why this
file defines a boundary instead of servicing a busy one: the factor and the check exist in one
place from the start, rather than being introduced later alongside the first code that needs
them, when a wrong sign would arrive with them.

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

#: Pascals in one megapascal. FreeCAD's FEM stack works in N/mm^2, and 1 N/mm^2 is exactly
#: 1 MPa, so this is the whole of the stress conversion. Treat that stack as file interface:
#: convert on the way out of it and never let MPa into project code.
PA_PER_MPA = 1.0e6


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
