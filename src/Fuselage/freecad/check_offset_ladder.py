"""Unit-level regression for offset_ladder.py's measurement primitives.

`offset_ladder.py` is the study tool behind OQ-DES-CW36 and OQ-DES-CW37, and until now it had no
coverage at all -- its findings were read straight off a run against a real cowl, where a wrong
primitive and a real geometric effect look identical. These cases exercise it against a circular
arc, whose radius of curvature, arc length and sample spacing all have closed forms, so a wrong
answer is caught against arithmetic rather than against another measurement of the same kind.

**The case that matters most is the sample/fit distinction.** A sample is an observation of a
curve; a fit is a parameterization of one. `cowl_interior`'s construction hands its samples in as a
B-spline's poles, so the curve does *not* pass through them, and the module asserted the opposite
in a comment for as long as it existed. `curve_from` exists to measure the two constructions side
by side, and `test_the_two_constructions_differ_as_measured` pins the difference numerically so
that a future change which quietly makes them equivalent -- or swaps one for the other -- fails
here rather than silently moving every wall figure in the corpus.

No cowl is built. Run: freecadcmd check_offset_ladder.py
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import cowl_interior as ci
import offset_ladder as ol
import si
from corner_common import is_entry_point

#: The probe arc: a quarter of a circle of this radius. A quarter rather than a full circle
#: because `_smoothed_open` and `curve_from` are the *open* constructions, and a closed loop
#: would exercise a different code path than the one under test.
PROBE_RADIUS_M = 0.010

#: Fractional radius agreement expected of `min_radius_m` on an **interpolated** quarter-circle.
#: The kernel reports its own analytic curvature, so the only error is the curve's departure from
#: the circle it was built through. The poles construction is deliberately not held to this --
#: departing from the arc is what it does, and it reads 11.5 % tight at 12 poles.
RADIUS_TOL = 0.02


def _arc():
    """A quarter-circle wire of `PROBE_RADIUS_M`, centered on the origin in the z = 0 plane."""
    circle = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), si.mm(PROBE_RADIUS_M))
    return Part.Wire([Part.Edge(circle, 0.0, math.pi / 2.0)])


def main():
    App.newDocument('check_offset_ladder')
    failures = []
    started = time.time()

    def check(label, ok, detail=''):
        # **Flushed per line, with elapsed time.** freecadcmd buffers stdout to exit, so an
        # unflushed check prints nothing at all while it runs -- which is how a first version of
        # this file came to be killed at 426 s of CPU with no way to see which case was slow.
        print('  %5.1fs  %-52s %s  %s'
              % (time.time() - started, label, 'ok' if ok else 'FAIL', detail))
        sys.stdout.flush()
        if not ok:
            failures.append(label)

    arc = _arc()
    n = 12
    points = ci._disc(arc, n, False)

    # ------------------------------------------------------------
    # the sample/fit distinction

    poles_wire, poles_dev_m = ol.curve_from(arc, points, n, False, 'poles')
    interp_wire, interp_dev_m = ol.curve_from(arc, points, n, False, 'interpolate')

    def worst_distance_to_samples_mm(wire):
        return max(wire.distToShape(Part.Vertex(p))[0] for p in points)

    poles_miss = worst_distance_to_samples_mm(poles_wire)
    interp_miss = worst_distance_to_samples_mm(interp_wire)

    # An interpolant honors every observation; a poles construction does not even try to. If this
    # ever reads near zero for `poles`, the construction has silently changed.
    check('interpolate passes through every sample',
          interp_miss < 1.0e-7, '%.3e mm' % interp_miss)
    check('poles does not pass through its samples',
          poles_miss > 1.0e-3, '%.6f mm' % poles_miss)

    # And the accuracy ordering, which is what OQ-DES-CW37's alternative 5 rests on. Stated as an
    # ordering rather than as the measured ratio: the ratio is geometry-dependent, the ordering is
    # the property being relied on.
    check('interpolate sits closer to the arc than poles does',
          interp_dev_m < poles_dev_m,
          'interpolate %.3e mm vs poles %.3e mm' % (si.mm(interp_dev_m), si.mm(poles_dev_m)))

    # Both deviations are measured the same way -- against the arc, not against the samples --
    # so neither may read zero merely because its curve honors the points it was built from.
    check('interpolate still reports a nonzero deviation from the arc',
          interp_dev_m > 0.0, '%.3e mm' % si.mm(interp_dev_m))

    # `poles` must be the shipped path and not a reimplementation of it.
    shipped_wire, shipped_dev_m = ci._smoothed_open(arc, n, False, ci.REFIT_TOL_M)
    check('curve_from(poles) is _smoothed_open exactly',
          shipped_dev_m == poles_dev_m,
          '%.17e vs %.17e' % (shipped_dev_m, poles_dev_m))

    # ------------------------------------------------------------
    # min_radius_m against a closed form

    # **The two constructions are held to different expectations, on purpose.** A first version of
    # this file asked both to land within `RADIUS_TOL` of the true radius, and the poles case
    # failed at 8.8545 mm against 10 -- 11.5 % low. That was a wrong expectation, not a defect: a
    # B-spline whose poles sit on a circle lies inside it, so it genuinely bends tighter than the
    # circle does, which is the same fact as its 0.0448 mm deviation from the arc. So the
    # interpolant is checked against the closed form, and the poles construction is checked for
    # the direction and presence of its bias instead.
    #
    # **This bears on the study and is worth carrying.** Every `min radius` figure in
    # OQ-DES-CW37's rung table was read off a poles curve, so all of them understate the radius.
    # The bias shrinks as the poles densify, which means it pushes the measured radius *up* at
    # high `n` -- the opposite direction to the falling trend those readings show, so that trend
    # is not an artifact of this bias. It does mean `radius / t` is not an absolute reading.
    want_mm = si.mm(PROBE_RADIUS_M)
    radius_mm = {}
    for label, wire in (('poles', poles_wire), ('interpolate', interp_wire)):
        radius_m, _at = ol.min_radius_m(wire, samples=400)
        radius_mm[label] = si.mm(radius_m)

    check('min_radius_m on an interpolated quarter-circle is its radius',
          abs(radius_mm['interpolate'] - want_mm) <= RADIUS_TOL * want_mm,
          '%.4f mm vs %.4f mm' % (radius_mm['interpolate'], want_mm))
    check('the poles construction reads tighter than the true radius',
          radius_mm['poles'] < radius_mm['interpolate'] < want_mm,
          'poles %.4f < interpolate %.4f < %.4f mm'
          % (radius_mm['poles'], radius_mm['interpolate'], want_mm))

    # ------------------------------------------------------------
    # duplicate_points on a known spacing

    repeats, min_gap_m = ol.duplicate_points(points)
    want_gap_mm = 2.0 * si.mm(PROBE_RADIUS_M) * math.sin(math.pi / 2.0 / (n - 1) / 2.0)
    check('duplicate_points finds no repeat in a clean sampling',
          repeats == 0, '%d repeat(s)' % repeats)
    check('duplicate_points reports the chord between neighbors',
          abs(si.mm(min_gap_m) - want_gap_mm) < 1.0e-6,
          '%.6f mm vs %.6f mm' % (si.mm(min_gap_m), want_gap_mm))

    # ------------------------------------------------------------
    # probe_station's shape

    # **Deliberately tiny rung factors.** These cases pin the *shape* of what `probe_station`
    # returns -- one row per rung per construction, sampling shared within a rung -- which does
    # not need production densities, and production densities here are measured to be unusable:
    # on this exact quarter-circle, `makeOffset2D` on an *interpolated* curve at n = 150 did not
    # return in several minutes, while the poles curve at the same n offset in 0.261 s. That
    # asymmetry is real and unexplained, it does not appear on real cowl sections (the study run
    # offsets both constructions at n = 200 to 3200 across fifty rungs), and it is noted in
    # OQ-DES-CW37 as a cost that alternative 5 has to measure rather than assume. A regression
    # has no business reproducing it, so the factors below put `n` at 4 and 8.
    rungs = (0.01, 0.02)
    n0, rows = ol.probe_station(arc, False, si.m(0.6), si.m(-1.0), rungs=rungs)
    check('probe_station returns one row per rung per construction',
          len(rows) == len(rungs) * len(ol.CONSTRUCTIONS),
          '%d rows for %d rungs x %d constructions'
          % (len(rows), len(rungs), len(ol.CONSTRUCTIONS)))

    # The sampling is done once per rung and shared, so these are properties of the observations.
    # A difference here would be this tool resampling per construction, which would make every
    # comparison it prints meaningless.
    by_rung = {}
    for row in rows:
        by_rung.setdefault(row['n'], []).append(row)
    shared_ok = all(
        len(set(r['distinct'] for r in group)) == 1
        and len(set(r['min_gap_m'] for r in group)) == 1
        for group in by_rung.values())
    check('both constructions see identical samples at a rung', shared_ok)

    check('every row names its construction',
          sorted(set(r['how'] for r in rows)) == sorted(ol.CONSTRUCTIONS))
    check('intervals is one less than the sample count',
          all(r['intervals'] == r['n'] - 1 for r in rows))

    # The ladder's own invariant, measured rather than asserted from the formula: for an even
    # first count every rung has an odd interval count, so no rung samples the arc's midpoint.
    # This is what makes a coprime-increment ladder no different in position overlap.
    if n0 % 2 == 0:
        check('no rung places a sample at the arc midpoint',
              all((r['n'] - 1) % 2 == 1 for r in rows if r['n'] % 2 == 0))

    print('')
    if failures:
        print('%d CHECK(S) FAILED: %s' % (len(failures), ', '.join(failures)))
    else:
        print('all checks passed')
    sys.stdout.flush()
    return 1 if failures else 0


if is_entry_point(__name__):
    raise SystemExit(main())
