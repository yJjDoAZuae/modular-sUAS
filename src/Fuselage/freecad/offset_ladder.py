"""OQ-DES-CW36 alternative 4: why `makeOffset2D` refuses a refit arc, and what distinguishes
the rungs of `eroded_arc`'s retry ladder.

    freecadcmd offset_ladder.py --pass --kind=nose_cowl_shell
    freecadcmd offset_ladder.py --pass --kind=nose_cowl_shell --pass --stations=-41.199,-32.400

**The question this answers.** `cowl_interior.eroded_arc` samples a cell section's open arc at `n`
points, builds a cubic B-spline whose **poles** are those samples, and offsets it inward by the
wall thickness. OpenCASCADE sometimes answers `makeOffset2D: result of offsetting is null!`, and
the construction responds by doubling `n` over a three-rung ladder.

**A sample is not a fit, and this tool now measures the difference.** A sample is an observation of
the arc; a fit is a parameterization of it. The shipped construction uses the samples *as* the
fit's control points, so one integer `n` sets both how often the arc is observed and how many
degrees of freedom the curve gets, and the ladder cannot move one without the other. `CONSTRUCTIONS`
runs `poles` (as shipped) and `interpolate` (the curve honors every sample) over identical
observations so the two can be told apart. OQ-DES-CW37 is the decision this measurement informs. Measured 2026-11-01, two of the nose's ten fit stations sit
exactly on that failure boundary: a station position differing by one unit in the last place --
7.1e-15 mm -- flips which rung succeeds, and the rungs produce contours up to 2.0e-4 mm apart.
That is inside every stated tolerance and is still a part whose recorded volume depends on a last
bit.

**What this measures, and why these quantities.** For each station it walks the same ladder the
construction walks, and for every rung records what the refit curve *is*, so a failure can be
attributed to a property of the curve rather than to OpenCASCADE's mood:

* **Near-duplicate input points.** `discretize` can return the same position twice -- an
  established hazard in this project, which is why distinct positions are counted and not just
  spacing. A cubic through a repeated point is degenerate, and doubling `n` resamples away from it.
* **Minimum radius of curvature against the offset distance.** An inward offset by `t` is
  singular wherever the curve bends tighter than `t`: the offset of that stretch turns inside out,
  and a kernel that will not build a self-intersecting wire returns nothing. This was the
  hypothesis OQ-DES-CW36 recorded as most likely, and `min_radius_m` against `t_m` tests it.
* **The refit's own deviation**, which the ladder also checks, so a failure can be told apart from
  a refit that simply did not reproduce the arc.
* **Self-intersection of the offset result** where one is produced at all.

**What it found, run on `nose_cowl_shell` at `U` = 1 over ten stations and fifty rungs.** Three
candidate mechanisms are refuted, including the leading one:

* Not near-duplicate points -- distinct positions equal `n` at every rung.
* Not the refit's accuracy -- every rung reproduced its arc inside `REFIT_TOL_M`, including every
  rung whose offset was refused.
* **Not the curvature.** The offset was refused at `radius / t` of 8.59, 6.72, 4.67 and 2.26 and
  **succeeded at the two tightest readings measured, 1.16 and 1.23** -- refuted in its own
  predicted direction.

Two findings stand. **Sampling more densely makes the curve bend tighter**: the minimum radius
falls monotonically as `n` rises (5.35, 2.80, 1.74, 1.35, 0.70 mm at one station) -- so *always use
the finest rung* would adopt the tightest curve available. And **failure is not monotonic in `n`**:
one station succeeds at 200, is refused at 400, succeeds at 800, is refused at 1600 and succeeds at
3200, so the ladder is a sequence of independent attempts rather than a refinement. The coarsest
rung tried, `n` = 200, offset successfully at all ten stations with a curve deviation of 1.2e-3 to
1.7e-3 mm against the 5.0e-3 mm allowed, which is a measured lead in the opposite direction to the
ladder.

**One explanation given for the first of those was wrong, corrected 2026-11-02.** It was written up
as denser *interpolation* injecting oscillation. There is no interpolation in the shipped path at
all: measured on a 10 mm circle sampled at 12 points, the poles construction misses its own samples
by 0.177923 mm and sits 0.178070 mm off the circle, while `interpolate()` on the same twelve
samples honors every one exactly and holds the circle to 0.002571 mm -- 69x closer from identical
observations. The trend stands and its mechanism is open; the candidate worth testing is that
denser poles let the control polygon resolve a genuinely tight corner that coarse poles round off.

**Both constructions, identical samples, run 2026-11-02 on `nose_cowl_shell` at `U` = 1.** This is
what `CONSTRUCTIONS` was added for, and it separates reliability from accuracy:

    n      poles          interpolate
    200    10/10          10/10
    400    8/10           9/10        <-- SAMPLE_MIN, the shipped floor, worst under both
    800    9/10           9/10
    1600   9/10           10/10
    3200   10/10          9/10
    all    46/50          47/50
    worst deviation from the arc: 1.710e-03 mm (poles)  5.985e-04 mm (interpolate)
    rungs inside REFIT_TOL_M:     50/50                 50/50

**One caution on cost.** Both constructions offset without incident at every rung on real cowl
sections, but they are not interchangeable in cost. On an exact quarter-circle of radius 10 mm
sampled at 150 points -- the synthetic arc `check_offset_ladder.py` uses -- `makeOffset2D` on the
*interpolated* curve did not return in several minutes, while the poles curve over the same samples
offset in 0.261 s. Unexplained, and absent from every real section measured. It is why the
regression pins row structure at `n` = 4 and 8 rather than at production densities, and it is a
drawback recorded against OQ-DES-CW37's alternative 5.

Three readings. `n` = 200 offset every station under **both** constructions, so that lead is a
property of the density and not of the curve-building. The shipped floor of 400 is the **worst**
density measured, under both. And **interpolating does not fix the refusals** -- 47 of 50 against 46
-- so the poles construction is not the cause either, which is the fourth refuted mechanism. What
interpolation buys is accuracy: 2.9x closer to the arc at the worst rung, 28x at the best, from the
same observations. OQ-DES-CW37 carries the decision.

**The ladder's doubling does not alias the sample positions**, which was worth checking because a
shared periodicity between rungs would make any comparison across them meaningless.
`discretize(Number=n)` returns `n` points including both ends, so a rung has `n-1` intervals, and
399, 799 and 1599 are pairwise coprime: rungs `n0` and `2n0` share 2 sample positions out of 400,
and `n0` and `4n0` share 4. A coprime-increment ladder (401, 601, 801) shares exactly as few, so
switching increments would not change the overlap. One invariant does run through every rung: for
even `n0` the interval count is always odd, so no rung ever places a sample at the arc's midpoint.

What decides the outcome inside OpenCASCADE's offset is still unidentified. See
`doc/design/cowl_interior_surface.md` §10.0.1 for the figures and §10.0 for the floor they bound.

**The stations this reconstructs are the construction's own seeding, and they can differ from a
build's by the patch inset** -- `cavity` seeds from its patch bounds and this seeds from the body's
extent, which puts them within about a thousandth of a millimeter of each other rather than on top
of each other. Pass `--stations` with figures off a build's own log to probe exactly what it built.

Nothing here changes any geometry. It builds the part, reads sections out of it, and reports.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import FreeCAD as App
import Part

import cowl_interior as ci
import cowl_tree
import si
from corner_common import is_entry_point

#: Rungs of the ladder, as multipliers on the construction's own first count. `eroded_arc` tries
#: `n`, `2n`, `4n`; this adds one more above and one below so a failure can be seen as a band
#: rather than as a verdict at three points.
RUNGS = (0.5, 1.0, 2.0, 4.0, 8.0)

#: How many points to sample a refit curve at when measuring its curvature. Dense relative to the
#: refit's own control net, because the tightest bend is between control points and not at one.
CURVATURE_SAMPLES = 4000

#: Below this, two consecutive sample positions count as the same point. One nanometer in meters,
#: ten times OpenCASCADE's `Precision::Confusion` of 1e-7 mm, so it cannot call two genuinely
#: distinct kernel positions duplicates.
DUPLICATE_TOL_M = 1.0e-9

#: The two ways of turning `n` samples of an arc into one curve, measured side by side at equal
#: observations. `poles` is what the construction ships -- the samples become the curve's control
#: points, so the curve does not pass through them. `interpolate` makes the curve honor every
#: sample. The distinction is the subject of OQ-DES-CW37: a sample is an observation of the arc,
#: a fit is a parameterization of it, and `poles` conflates the two by making one integer set
#: both the observation count and the fit's degrees of freedom.
CONSTRUCTIONS = ('poles', 'interpolate')


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def min_radius_m(curve_shape, samples=CURVATURE_SAMPLES):
    """`(minimum radius of curvature in meters, the parameter it occurs at)` along an edge.

    Read from the kernel's own `curvatureAt`, which is the curve's analytic curvature rather than
    a finite difference over sampled points -- a finite difference across a tight bend
    underestimates it badly, and underestimating curvature is exactly the error that would hide
    the mechanism being tested for.

    A straight stretch has zero curvature and infinite radius; those parameters are skipped rather
    than reported as the minimum.
    """
    edge = curve_shape.Edges[0]
    lo, hi = edge.FirstParameter, edge.LastParameter
    best_m, at = float('inf'), None
    for i in range(samples + 1):
        u = lo + (hi - lo) * i / float(samples)
        try:
            kappa = edge.curvatureAt(u)
        except Exception:                               # noqa: BLE001 -- a parameter the kernel
            continue                                    # will not evaluate is not a finding
        if kappa <= 0.0:
            continue
        radius_m = si.m(1.0 / kappa)
        if radius_m < best_m:
            best_m, at = radius_m, u
    return best_m, at


def duplicate_points(points, tol_m=DUPLICATE_TOL_M):
    """`(count of consecutive near-duplicates, smallest gap in meters)` over kernel points."""
    worst_m = float('inf')
    repeats = 0
    for a, b in zip(points, points[1:]):
        gap_m = si.m(a.distanceToPoint(b))
        worst_m = min(worst_m, gap_m)
        if gap_m < tol_m:
            repeats += 1
    return repeats, worst_m


def curve_from(arc, points, n, flip, how):
    """`(wire, worst deviation from `arc` in meters)` for one construction over given samples.

    **The two constructions see identical observations**, which is the whole point: `points` is
    sampled once per rung and handed to both, so any difference is the construction's and not the
    sampling's.

    `poles` delegates to the shipped `ci._smoothed_open` rather than reimplementing it, so what is
    measured is the production path. `interpolate` mirrors that function's own measurement exactly
    -- a dense polyline of the new curve against `2n` samples of the source arc -- because a
    deviation measured two ways is not a comparison.
    """
    if how == 'poles':
        return ci._smoothed_open(arc, n, flip, ci.REFIT_TOL_M)
    curve = Part.BSplineCurve()
    curve.interpolate(Points=points)
    shape = curve.toShape()
    dense = ci._Polyline([(si.m(p.x), si.m(p.y))
                          for p in shape.discretize(Number=4 * n)], closed=False)
    worst_m = float(dense.distances(
        [(si.m(p.x), si.m(p.y)) for p in ci._disc(arc, 2 * n, flip)]).max())
    return Part.Wire(shape), worst_m


def probe_station(arc, flip, t_m, z_m, rungs=RUNGS, constructions=CONSTRUCTIONS):
    """Walk the ladder at one station and describe every rung under every construction.

    Returns `(n0, rows)`, one row per rung per construction. The sampling is done once per rung
    and shared, so `distinct`, `repeats` and `min_gap_m` are properties of the observations and
    read the same for both constructions by design -- a difference there would be a bug in this
    tool, not a finding.
    """
    n0 = ci._steps(si.length_m(arc), ci.SAMPLE_SPACING_M, ci.SAMPLE_MIN, ci.SAMPLE_MAX)
    rows = []
    for factor in rungs:
        n = max(4, int(round(n0 * factor)))
        points = ci._disc(arc, n, flip)
        repeats, min_gap_m = duplicate_points(points)
        distinct = len(set((round(p.x, 9), round(p.y, 9), round(p.z, 9)) for p in points))
        for how in constructions:
            row = {'n': n, 'factor': factor, 'how': how, 'repeats': repeats,
                   'min_gap_m': min_gap_m, 'distinct': distinct,
                   'intervals': n - 1}
            try:
                refit, moved_m = curve_from(arc, points, n, flip, how)
            except Exception as exc:                    # noqa: BLE001 -- a construction that will
                row['moved_m'] = float('nan')           # not build is itself the measurement
                row['refit_over_tol'] = True
                row['min_radius_m'] = float('nan')
                row['radius_over_t'] = float('nan')
                row['offset'] = 'no curve'
                row['edges'] = 0
                row['self_intersects'] = False
                row['why'] = str(exc).strip()
                rows.append(row)
                continue
            row['moved_m'] = moved_m
            row['refit_over_tol'] = moved_m > ci.REFIT_TOL_M
            row['min_radius_m'], row['at'] = min_radius_m(refit)
            row['radius_over_t'] = row['min_radius_m'] / t_m if t_m else float('inf')
            try:
                offset = refit.makeOffset2D(-si.mm(t_m), 0, False, True, True)
                row['offset'] = 'ok' if (offset is not None and offset.Edges) else 'empty'
                row['edges'] = 0 if offset is None else len(offset.Edges)
                row['self_intersects'] = (
                    bool(offset is not None and offset.Edges and not offset.isValid()))
            except Exception as exc:                    # noqa: BLE001 -- the result being measured
                row['offset'] = 'raised'
                row['edges'] = 0
                row['self_intersects'] = False
                row['why'] = str(exc).strip()
            rows.append(row)
    return n0, rows


def main():
    kind = _opt('kind', 'nose_cowl_shell')
    builder = {'tail_shell': cowl_tree.tail_shell,
               'nose_cowl_shell': cowl_tree.nose_cowl_shell}[kind]
    params = {'tail_shell': cowl_tree.PARAMS_TAIL_SHELL,
              'nose_cowl_shell': cowl_tree.PARAMS_NOSE_COWL_SHELL}[kind]

    doc = App.newDocument('offset_ladder')
    tip = cowl_tree.emit(doc, None, params, builder)
    doc.recompute()
    body = tip.Body.Shape
    t_m = si.m(tip.Inset)

    planes = ci.cell_boundary_planes(body)
    z_lo_m, z_hi_m = ci.z_extent(body)

    wanted = _opt('stations')
    if wanted:
        stations_m = [si.m(float(v)) for v in wanted.split(',')]
    else:
        # **The construction's own seeded stations, rebuilt the way `cavity` builds them**, so
        # the ones that fail are found rather than copied out of a previous run's log. The part
        # is one patch at every shipped configuration, so its two ends are the part's own ends
        # and both are inset.
        notches = Part.makeCompound([n.Shape for n in tip.Notches])
        edges_m = [e for e in ci.feature_stations(notches, z_lo_m, z_hi_m)
                   if z_lo_m < e < z_hi_m]
        stations_m = ci._thin_stations(
            sorted(set(ci._seed(z_lo_m, z_hi_m, True, True)) | set(edges_m)),
            ci.station_floor(t_m))

    print('OFFSET LADDER: %s, inset t = %.4f mm, %d station(s)'
          % (kind, si.mm(t_m), len(stations_m)))
    print('  an inward offset by t is singular wherever the curve bends tighter than t, so'
          ' radius/t <= 1 is the mechanism under test')
    print('')
    print('  %-11s %-6s %-12s %-9s %-8s %-11s %-9s %-10s %-6s %s'
          % ('z (mm)', 'n', 'fit', 'distinct', 'min gap', 'min radius', 'radius/t', 'curve dev',
             'within', 'offset'))

    failures = 0
    first_rung_failed = []
    #: Per construction: rungs attempted, rungs whose offset succeeded, rungs whose curve stayed
    #: inside `REFIT_TOL_M`, and the deviation band. These are what decide OQ-DES-CW37.
    tally = dict((how, {'tried': 0, 'offset_ok': 0, 'within': 0,
                        'dev_lo_m': float('inf'), 'dev_hi_m': 0.0,
                        'first_rung_ok': 0, 'first_rung_tried': 0})
                 for how in CONSTRUCTIONS)
    for z_m in stations_m:
        wires = ci._slice_wires(body, z_m)
        if len(wires) != 1:
            print('  %-11.4f sections into %d loops, not one -- skipped'
                  % (si.mm(z_m), len(wires)))
            continue
        arc, p_start, p_end, flip = ci.open_arc(wires[0], planes)
        n0, rows = probe_station(arc, flip, t_m, z_m)
        for index, row in enumerate(rows):
            mark = ''
            if row['offset'] != 'ok':
                failures += 1
                mark = '  <-- %s' % row.get('why', row['offset'])
            if row['factor'] == 1.0 and row['how'] == 'poles' and row['offset'] != 'ok':
                first_rung_failed.append(si.mm(z_m))
            t = tally[row['how']]
            t['tried'] += 1
            t['offset_ok'] += 1 if row['offset'] == 'ok' else 0
            t['within'] += 0 if row['refit_over_tol'] else 1
            if row['moved_m'] == row['moved_m']:        # not NaN
                t['dev_lo_m'] = min(t['dev_lo_m'], row['moved_m'])
                t['dev_hi_m'] = max(t['dev_hi_m'], row['moved_m'])
            if row['factor'] == 1.0:
                t['first_rung_tried'] += 1
                t['first_rung_ok'] += 1 if row['offset'] == 'ok' else 0
            print('  %-11s %-6d %-12s %-9d %-8.2e %-11.4e %-9.3f %-10.3e %-6s %s%s'
                  % ('%.4f' % si.mm(z_m) if index == 0 else '',
                     row['n'], row['how'], row['distinct'], si.mm(row['min_gap_m']),
                     si.mm(row['min_radius_m']), row['radius_over_t'],
                     si.mm(row['moved_m']),
                     'over' if row['refit_over_tol'] else 'ok',
                     row['offset'], mark))
        print('')

    print('  %d rung(s) refused the offset across %d station(s); the construction\'s own first '
          'rung failed at %s'
          % (failures, len(stations_m),
             ', '.join('%.4f' % v for v in first_rung_failed) or 'no station'))
    print('')
    print('  CONSTRUCTION COMPARISON -- identical samples, two ways of making a curve from them')
    print('  %-12s %-12s %-14s %-14s %s'
          % ('fit', 'offset ok', 'at n0 only', 'within tol', 'curve deviation from arc (mm)'))
    for how in CONSTRUCTIONS:
        t = tally[how]
        if not t['tried']:
            continue
        print('  %-12s %-12s %-14s %-14s %.3e .. %.3e'
              % (how, '%d/%d' % (t['offset_ok'], t['tried']),
                 '%d/%d' % (t['first_rung_ok'], t['first_rung_tried']),
                 '%d/%d' % (t['within'], t['tried']),
                 si.mm(t['dev_lo_m']), si.mm(t['dev_hi_m'])))
    print('')
    print('  min gap, min radius and curve dev are millimeters; radius/t is nondimensional.')
    print('  `curve dev` is how far the curve sits from the arc it was sampled from, against'
          ' REFIT_TOL_M = %.4f mm. For `poles` it is nonzero at every rung by construction --'
          ' the samples are the control points, so the curve never passes through them.'
          % si.mm(ci.REFIT_TOL_M))
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    raise SystemExit(main())
