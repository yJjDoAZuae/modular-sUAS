"""IP-FC-158: integration regression for `si.py`, the port's unit boundary.

`units.py` holds the factor and `check_units.py` proves the arithmetic. This script proves the
part that arithmetic cannot: that a shape built from meters is the shape the kernel was asked
for, and that every reader hands back the same quantity in SI that the kernel holds in
millimeters. Those are two different claims and only the second one needs the kernel.

**Why each primitive is checked against a figure derived independently, not against itself.**
A boundary module is exactly the place where a test that reuses the module's own factor passes
while the factor is wrong -- `volume_m3(box_m(l, w, h)) == l * w * h` is the only form that
catches a squared-instead-of-cubed error, because the right-hand side never touches `si`. So
every expectation below is written in plain arithmetic on the SI inputs.

Run: freecadcmd check_si.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import Part

import si
from corner_common import is_entry_point

#: Relative tolerance. These are exact conversions on exact primitives, so the only error is
#: floating point -- a loose tolerance here would hide a real defect rather than absorb noise.
TOL = 1e-12


def main():
    failures = []

    def check(label, got, want, tol=TOL):
        if isinstance(got, float) or isinstance(want, float):
            ok = abs(got - want) <= tol * max(1.0, abs(want))
        else:
            ok = got == want
        print('  %-56s %-22s %-22s  %s'
              % (label, _fmt(got), _fmt(want), 'ok' if ok else 'FAIL'))
        sys.stdout.flush()
        if not ok:
            failures.append(label)

    def close(label, got, want, tol=TOL):
        """A 3-tuple of positions, compared componentwise."""
        ok = all(abs(g - w) <= tol * max(1.0, abs(w)) for g, w in zip(got, want))
        print('  %-56s %-22s %-22s  %s'
              % (label, _fmt(got), _fmt(want), 'ok' if ok else 'FAIL'))
        sys.stdout.flush()
        if not ok:
            failures.append(label)

    print('si.py -- the unit boundary')
    print('')

    # ------------------------------------------------------------
    # The factors themselves. A cubed factor written by hand is the error this module exists
    # to remove, so it is checked against the kernel's own arithmetic rather than restated.
    # ------------------------------------------------------------
    check('MM2_PER_M2 is the square of the length factor',
          si.MM2_PER_M2, 1000.0 * 1000.0)
    check('MM3_PER_M3 is the cube of the length factor',
          si.MM3_PER_M3, 1000.0 * 1000.0 * 1000.0)

    # ------------------------------------------------------------
    # Vectors, in both directions and as a round trip.
    # ------------------------------------------------------------
    vector = si.vec_m(0.001, 0.002, 0.003)
    check('vec_m writes millimeters into the kernel (x)', vector.x, 1.0)
    check('vec_m writes millimeters into the kernel (y)', vector.y, 2.0)
    check('vec_m writes millimeters into the kernel (z)', vector.z, 3.0)
    close('point_m/vec_m round trip', si.point_m(vector), (0.001, 0.002, 0.003))
    close('point_m reads a Part.Vertex', si.point_m(Part.Vertex(vector)), (0.001, 0.002, 0.003))
    close('point_m reads a bare 3-sequence', si.point_m((4.0, 5.0, 6.0)),
          (0.004, 0.005, 0.006))

    # ------------------------------------------------------------
    # Primitives. The expectation is arithmetic on the SI inputs and never touches `si`.
    # ------------------------------------------------------------
    length_m, width_m, height_m = 0.010, 0.020, 0.030
    box = si.box_m(length_m, width_m, height_m)
    check('box_m volume in m3 is l*w*h', si.volume_m3(box), length_m * width_m * height_m)
    check('box_m area in m2 is the six faces', si.area_m2(box),
          2.0 * (length_m * width_m + length_m * height_m + width_m * height_m))
    check('box_m bbox ZLength in m is the height', si.bbox_m(box).ZLength, height_m)
    close('box_m bbox center in m', si.bbox_m(box).Center,
          (length_m / 2.0, width_m / 2.0, height_m / 2.0))

    radius_m, tall_m = 0.005, 0.040
    cylinder = si.cylinder_m(radius_m, tall_m)
    check('cylinder_m volume in m3 is pi r^2 h', si.volume_m3(cylinder),
          math.pi * radius_m * radius_m * tall_m, tol=1e-6)
    check('cylinder_m bbox XLength in m is the diameter',
          si.bbox_m(cylinder).XLength, 2.0 * radius_m, tol=1e-6)

    # A quarter cylinder, which is the check that the angle argument is converted too: built
    # with radians handed straight to the kernel this is a 90-radian sweep and comes back whole.
    quarter = si.cylinder_m(radius_m, tall_m, angle_rad=math.pi / 2.0)
    check('cylinder_m angle_rad is converted to the kernel degrees',
          si.volume_m3(quarter), math.pi * radius_m * radius_m * tall_m / 4.0, tol=1e-6)

    cone = si.cone_m(0.004, 0.002, 0.010)
    check('cone_m volume in m3 is the frustum formula', si.volume_m3(cone),
          math.pi * 0.010 / 3.0 * (0.004 ** 2 + 0.004 * 0.002 + 0.002 ** 2), tol=1e-6)

    # ------------------------------------------------------------
    # Lines, polygons and the length reader.
    # ------------------------------------------------------------
    edge = si.line_m((0.0, 0.0, 0.0), (0.003, 0.004, 0.0))
    check('length_m of a 3-4-5 edge in m', si.length_m(edge), 0.005)

    square = si.polygon_m([(0.0, 0.0, 0.0), (0.010, 0.0, 0.0),
                           (0.010, 0.010, 0.0), (0.0, 0.010, 0.0), (0.0, 0.0, 0.0)])
    check('length_m of a closed 10 mm square in m', si.length_m(square), 0.040)
    check('area_m2 of the face it bounds', si.area_m2(Part.Face(square)), 0.010 * 0.010)

    # ------------------------------------------------------------
    # Distance, which is the reader most likely to be used for a tolerance comparison.
    # ------------------------------------------------------------
    here = si.box_m(0.010, 0.010, 0.010)
    there = si.box_m(0.010, 0.010, 0.010, placement=None)
    there.translate(si.vec_m(0.025, 0.0, 0.0))
    check('distance_m between boxes 15 mm apart', si.distance_m(here, there), 0.015, tol=1e-9)
    gap, first, second = si.closest_m(here, there)
    check('closest_m returns the same distance', gap, 0.015, tol=1e-9)
    check('closest_m first point is on this box', abs(first[0] - 0.010) < 1e-12, True)
    check('closest_m second point is on the other', abs(second[0] - 0.025) < 1e-12, True)

    # ------------------------------------------------------------
    # The bounding box wrapper, including that it feeds `units.bbox_m_matches_mm` -- the
    # roadmap's own named check for this boundary, which is dead code until something does.
    # ------------------------------------------------------------
    import units
    box_si = si.bbox_m(box).as_tuple()
    raw = box.BoundBox
    box_mm = (raw.XMin, raw.YMin, raw.ZMin, raw.XMax, raw.YMax, raw.ZMax)
    ok, report = units.bbox_m_matches_mm(box_si, box_mm)
    check('bbox_m agrees with units.bbox_m_matches_mm on the same shape', ok, True)
    check('and it reports no disagreeing component', report, [])

    # The converse: a box whose SI reading was left in millimeters must fail that check, or the
    # check is not testing anything.
    ok_bad, report_bad = units.bbox_m_matches_mm(box_mm, box_mm)
    check('an unconverted box fails it', ok_bad, False)
    check('and it names every nonzero component', len(report_bad) > 0, True)

    # ------------------------------------------------------------
    # Kernel-domain constants stay millimeters, which is the whole reason they live here.
    # ------------------------------------------------------------
    check('RIB_CUT_FUZZ_MM is unchanged at 1.0e-5 mm', si.RIB_CUT_FUZZ_MM, 1.0e-5)
    check('CUT_FUZZ_LADDER_MM is unchanged', tuple(si.CUT_FUZZ_LADDER_MM),
          (1.0e-5, 1.0e-4, 1.0e-3, 1.0e-2))
    check('the ladder starts at the fuzz', si.CUT_FUZZ_LADDER_MM[0], si.RIB_CUT_FUZZ_MM)

    # And that the fuzz still does its job: the escape hatches are the same factor as the
    # wrapped calls, so a caller mixing the two cannot disagree with itself.
    check('mm() and the primitives agree on the factor', si.mm(0.0125), 12.5)
    check('m() inverts mm()', si.m(si.mm(0.0125)), 0.0125)
    check('tol_mm is the same crossing as mm', si.tol_mm(1.0e-5), si.mm(1.0e-5))

    print('')
    if failures:
        print('%d check(s) FAILED:' % len(failures))
        for label in failures:
            print('  %s' % label)
    else:
        print('all checks passed')
    sys.stdout.flush()
    return len(failures)


def _fmt(value):
    if isinstance(value, tuple):
        return '(' + ', '.join('%.6g' % v for v in value) + ')'
    if isinstance(value, float):
        return '%.12g' % value
    return str(value)


if is_entry_point(__name__):
    sys.exit(main())
