"""IP-WTM-3: the five-gate screening harness.

**The thresholds are fixed here, in code, before any candidate is scored**, and they are derived
rather than chosen -- which is why selecting a thickness measure needs no design decision. A
candidate passes all five or it does not, and if more than one passes, `rank` applies the
pre-committed tie-break. Nothing in this module reserves a judgment call.

| gate | asks | threshold |
| --- | --- | --- |
| G1 locality | does it see a thin patch one extrusion width long? | >= 80% of the patch's true depth |
| G2 convergence | does the reported value settle under refinement? | <= 0.001 mm between the two finest levels, and shrinking |
| G3 accuracy | does it read a known constant wall correctly? | <= 0.001 mm from closed form |
| G4 discrimination | does it say how deep the defect is, and where? | depth within 0.002 mm, location within 2 mm |
| G5 cost | can it run in a build and in the suite? | <= 60 s for 12 stations of a real tail wall |

The 0.001 mm figures are a tenth of `WALL_TOL` = 0.01 mm, so an instrument's own residual can never
be confused with the quantity it measures. G1's 0.6 mm patch length is one extrusion width
(`cowl_n_perimeters * extrusion_width` = 1 x 0.6), the shortest thin spot a single-perimeter
spiral-vase wall can actually fail at.

G5 needs a real wall and is therefore opt-in: `cost_gate` takes a shape the caller has loaded, so
the other four gates stay in the fast test tier. The 28 finished walls the 2026-10-06 soak saved as
BREP are what it runs against -- no cowl build.

See doc/implementation/wall_thickness_measure.md.
"""
import time

import numpy as np

from . import sections

#: Gate thresholds. A tenth of `WALL_TOL` wherever the gate is about the instrument's own residual.
ACCURACY_TOL = 0.001          # G3: mm from the closed-form answer
CONVERGE_TOL = 0.001          # G2: mm of movement between the two finest refinements
LOCALITY_FRAC = 0.80          # G1: fraction of a patch's true depth that must be seen
DEPTH_TOL = 0.002             # G4: mm of error allowed on the reported depth
LOCATION_TOL = 2.0            # G4: mm along the section the reported minimum may be out by
COST_LIMIT_S = 60.0           # G5: seconds for 12 stations of the largest real wall
CONTRACTION = 0.6             # G2: how much each refinement step must shrink the one before

#: Refinement levels for G2, each a doubling, so "movement between the two finest" is a halving of
#: the sample spacing and not an arbitrary pair.
LEVELS = (360, 720, 1440, 2880)


class GateResult(object):
    """One gate's verdict, with the number behind it so a failure is readable."""

    __slots__ = ('gate', 'passed', 'value', 'threshold', 'detail')

    def __init__(self, gate, passed, value, threshold, detail=''):
        self.gate = gate
        self.passed = bool(passed)
        self.value = value
        self.threshold = threshold
        self.detail = detail

    def __repr__(self):
        return '<%s %s value=%s limit=%s>' % (
            self.gate, 'PASS' if self.passed else 'FAIL', _fmt(self.value), _fmt(self.threshold))


def _fmt(v):
    if v is None:
        return '-'
    if isinstance(v, float):
        return '%.6f' % v
    return str(v)


def _truth_vector(truth_obj, points):
    """Closed-form thickness at each sample, with ambiguous samples masked out.

    A sample within `EDGE_MARGIN` of a feature boundary has two defensible answers, so scoring it
    would measure the fixture. Those are dropped rather than guessed.
    """
    want = np.array([truth_obj.true_thickness_at(p[0], p[1], p[2])
                     if truth_obj.true_thickness_at(p[0], p[1], p[2]) is not None else np.nan
                     for p in points], dtype=np.float64)
    return want


def accuracy_gate(measure, uniform_truth, loops_at, level=LEVELS[-1]):
    """**G3.** On a known constant wall, how far off is the measure at its worst sample?

    First because it is the gate nothing in this project has ever been asked to pass. A measure can
    settle beautifully on the wrong number -- the area-based mean settles to 1e-6 mm and reads
    0.4753 mm where the wall is 0.6 mm -- so convergence without accuracy is worth nothing.
    """
    outer, inner = loops_at(uniform_truth, _station_for(uniform_truth), level)
    pts, thick = measure(outer, inner)
    if pts.shape[0] == 0:
        return GateResult('G3 accuracy', False, None, ACCURACY_TOL, 'measure reported no samples')
    # **Against the per-sample truth, not against `nominal`.** An earlier version compared every
    # sample to the fixture's nominal wall, which is only right where the fixture has no feature.
    # On `ribbed_tube` that scored the rib's own 0.4 mm rise as a 0.4 mm measurement error and
    # failed the incumbent for reading the rib correctly. `_truth_vector` answers per point, and
    # masks a sample straddling a feature edge where the answer is genuinely ambiguous.
    want = _truth_vector(uniform_truth, pts)
    err = np.abs(thick - want)
    scored = int(np.sum(np.isfinite(err)))
    if scored == 0:
        return GateResult('G3 accuracy', False, None, ACCURACY_TOL,
                          'every sample fell on a feature edge; nothing to score')
    worst = float(np.nanmax(err))
    return GateResult('G3 accuracy', worst <= ACCURACY_TOL, worst, ACCURACY_TOL,
                      'worst of %d scored samples (%d masked at edges); median %.6f'
                      % (scored, pts.shape[0] - scored, float(np.nanmedian(err))))


def refinement_sweep(measure, loops_at_level, levels=LEVELS):
    """The reported minimum and median at each sampling density. **The measurement itself.**

    `loops_at_level(n)` returns `(outer, inner)` at `n` samples a loop, so this works identically
    on a synthetic fixture and on a real saved wall -- the two differ only in that callable. Both
    series are returned because which one moves is the finding: on a real wall the minimum wandered
    over 0.13 mm across a refinement sweep while the median moved 2.7e-5 mm.

    Returns `(minima, medians)`, each a list as long as `levels`.
    """
    minima, medians = [], []
    for n in levels:
        outer, inner = loops_at_level(n)
        pts, thick = measure(outer, inner)
        if pts.shape[0] == 0:
            minima.append(float('nan'))
            medians.append(float('nan'))
            continue
        minima.append(float(np.nanmin(thick)))
        medians.append(float(np.nanmedian(thick)))
    return minima, medians


def converged(values, tol=CONVERGE_TOL, contraction=CONTRACTION):
    """Did a refinement series settle? Returns `(ok, last_delta, deltas, contracting)`.

    Two conditions, not one: the last step must be small **and** the steps must be contracting. A
    measure that moves 0.0009 mm per doubling forever has small steps and has not converged -- and
    that is the incumbent's actual behavior, so a gate that missed it would be worthless. Split out
    of the gate so the same verdict can be applied to a real wall's series and to a fixture's.
    """
    deltas = [abs(values[i + 1] - values[i]) for i in range(len(values) - 1)]
    if not deltas:
        return False, float('nan'), deltas, False
    last = deltas[-1]
    contracting = last <= deltas[-2] * contraction if len(deltas) >= 2 else True
    return (last <= tol and contracting), last, deltas, contracting


def convergence_gate(measure, uniform_truth, loops_at, levels=LEVELS):
    """**G2 on a fixture.** The smooth-case contrast, not the authoritative gate.

    **A fixture cannot screen this gate**, which IP-WTM-15 exists to fix: concentric circular
    boundaries make a nearest-point distance exactly radial and exactly equal to the wall, so no
    diagonal shortcut across a corner exists to be found. Measured 2026-10-10, the incumbent passes
    here at 0.000018 mm contracting 4x a doubling and fails on a real section at 0.0043 mm still
    moving. Use `convergence_gate_on_section` for the verdict and this for the contrast: a candidate
    that converges smooth and not real has at least localized its own weakness.
    """
    station = _station_for(uniform_truth)
    vals, _med = refinement_sweep(
        measure, lambda n: loops_at(uniform_truth, station, n), levels)
    ok, last, deltas, contracting = converged(vals)
    return GateResult('G2 convergence', ok, last, CONVERGE_TOL,
                      'on %s; levels %s -> %s; deltas %s%s'
                      % (uniform_truth.label, list(levels), ['%.6f' % v for v in vals],
                         ['%.6f' % d for d in deltas],
                         '' if contracting else ', NOT contracting'))


def locality_gate(measure, patch_truth, loops_at, level=LEVELS[-1]):
    """**G1.** Does the measure see a thin patch one extrusion width long?

    The gate the converged area-based mean fails, and the reason a mean cannot be the acceptance
    measure however well it converges: a spiral-vase wall is one perimeter and the slicer drops it
    at a point.
    """
    f = patch_truth.features[0]
    outer, inner = loops_at(patch_truth, f['z_mid'], level)
    pts, thick = measure(outer, inner)
    if pts.shape[0] == 0:
        return GateResult('G1 locality', False, None, LOCALITY_FRAC, 'no samples')
    seen = patch_truth.nominal - float(np.nanmin(thick))
    frac = seen / f['depth']
    return GateResult('G1 locality', frac >= LOCALITY_FRAC, frac, LOCALITY_FRAC,
                      'saw %.6f mm of a %.6f mm patch over %.2f mm of arc'
                      % (seen, f['depth'], f['arc']))


def discrimination_gate(measure, patch_truth, loops_at, level=LEVELS[-1]):
    """**G4.** Does it report the defect's depth, and locate it?

    The converse test. A measure that flags something somewhere is not a measurement: the build has
    to know how thin and where, or the figure cannot be compared against `WALL_TOL` or acted on.
    """
    f = patch_truth.features[0]
    outer, inner = loops_at(patch_truth, f['z_mid'], level)
    pts, thick = measure(outer, inner)
    if pts.shape[0] == 0:
        return GateResult('G4 discrimination', False, None, DEPTH_TOL, 'no samples')
    k = int(np.nanargmin(thick))
    depth_err = abs((patch_truth.nominal - float(thick[k])) - f['depth'])
    # Where the patch actually is, on the outer surface, projected to the sampled boundary's radius.
    r = float(np.hypot(pts[k, 0], pts[k, 1]))
    want = np.array([np.cos(f['angle']), np.sin(f['angle'])]) * r
    miss = float(np.hypot(pts[k, 0] - want[0], pts[k, 1] - want[1]))
    ok = depth_err <= DEPTH_TOL and miss <= LOCATION_TOL
    return GateResult('G4 discrimination', ok, depth_err, DEPTH_TOL,
                      'depth error %.6f mm, located %.3f mm from the patch center (limit %.1f)'
                      % (depth_err, miss, LOCATION_TOL))


def convergence_gate_on_section(measure, shape, z, App, levels=LEVELS):
    """**G2, the authoritative form: does the measure converge on a real section?**

    IP-WTM-15. This is the gate that matters, because the defect being screened for lives in the
    real sections and nowhere else: they are convoluted B-splines with a concave corner at every
    slot mouth, where a nearest-point distance crosses the corner instead of the wall and denser
    sampling keeps finding a shorter path. A synthetic annulus has no such corner, so screening
    convergence there passes the very measure this work exists to replace.

    Measured on `nose_cowl_shell` at `U` = 1, one interior station, the incumbent reports minima of
    0.473496, 0.592148, 0.587314, 0.567506 and 0.563182 mm at 360 to 5760 samples -- non-monotone,
    not contracting, and still moving 0.0043 mm at the finest level, which is 4.3x `WALL_TOL`. The
    median over the same sweep moves 2.7e-5 mm.

    `shape` is a real wall, normally one of the soak's saved BREPs via `corpus.load`.
    """
    def at(n):
        loops = sections.station_loops(shape, z, n, App=App)
        if len(loops) < 2:
            raise ValueError('station z=%.4f has %d closed loops, not two' % (z, len(loops)))
        return loops[0], loops[1]

    minima, medians = refinement_sweep(measure, at, levels)
    ok, last, deltas, contracting = converged(minima)
    med_spread = float(np.nanmax(medians) - np.nanmin(medians))
    return GateResult(
        'G2 convergence', ok, last, CONVERGE_TOL,
        'on a real section at z=%.4f; levels %s -> %s; deltas %s%s; median spread %.6f'
        % (z, list(levels), ['%.6f' % v for v in minima], ['%.6f' % d for d in deltas],
           '' if contracting else ', NOT contracting', med_spread))


def cost_gate(measure, shape, z_lo, z_hi, App, stations=12, level=LEVELS[1],
              limit=COST_LIMIT_S):
    """**G5.** Time the measure over a real wall's stations.

    Opt-in, because it needs a real wall: the caller loads one of the soak's saved BREPs and passes
    it in. This is what closed the morphological route on the exact B-spline section, where one
    `Face.makeOffset2D` call did not finish in six minutes.
    """
    started = time.time()
    n_done = 0
    for i in range(stations):
        z = z_lo + (z_hi - z_lo) * i / float(stations - 1)
        loops = sections.station_loops(shape, z, level, App=App)
        if len(loops) < 2:
            continue
        measure(loops[0], loops[1])
        n_done += 1
    took = time.time() - started
    return GateResult('G5 cost', took <= limit and n_done > 0, took, limit,
                      '%d of %d stations measured' % (n_done, stations))


def _station_for(truth_obj):
    """The station a gate should measure this fixture at.

    A fixture with a feature is measured **through** it, because the feature is the whole reason
    that fixture exists; a plain tube is measured anywhere.
    """
    if truth_obj.features:
        return truth_obj.features[0]['z_mid']
    return 1.0


def screen(measure, fixtures, loops_at):
    """Run G1 through G4 and return the four results in gate order.

    **Which fixture each gate runs on is itself load-bearing, and getting it wrong made this
    harness useless on its first run.** The incumbent passed all four gates -- convergence delta
    0.000001 mm, accuracy 0.000000 mm -- because convergence was being measured on
    `uniform_tube`, two smooth concentric circles. The incumbent's documented failure needs a
    **concave corner on the boundary being sampled**: that is where a nearest-point distance cuts
    across the corner instead of across the wall, and denser sampling keeps finding a shorter path.
    An annulus has no corner anywhere, so measuring convergence there measures nothing and reports
    a pass.

    That is the same mistake this plan exists to correct -- judging a measure on geometry that
    cannot expose its defect -- committed inside the harness built to correct it. So:

    * **G2 convergence runs on `ribbed_tube`**, the fixture whose rib leaves two re-entrant corners
      on the bore, which is the boundary the measures sample. `uniform_tube` is still measured and
      reported alongside, as the contrast: a measure that converges on the smooth case and not the
      cornered one has localized its own weakness.
    * **G3 accuracy runs on both** and takes the worse, since accuracy beside a crease is the hard
      case and accuracy on an annulus is the floor.
    * G1 and G4 run on `thin_patch_tube`, which is the only fixture with a thin defect to find.
    """
    uniform = fixtures['uniform_tube']
    patched = fixtures['thin_patch_tube']
    ribbed = fixtures.get('ribbed_tube')

    acc_uniform = accuracy_gate(measure, uniform, loops_at)
    out = [locality_gate(measure, patched, loops_at)]

    if ribbed is None:
        out.append(convergence_gate(measure, uniform, loops_at))
        out.append(acc_uniform)
    else:
        conv = convergence_gate(measure, ribbed, loops_at)
        conv_smooth = convergence_gate(measure, uniform, loops_at)
        conv.detail += '  [smooth contrast: %s %s]' % (
            'pass' if conv_smooth.passed else 'FAIL', _fmt(conv_smooth.value))
        out.append(conv)
        acc_ribbed = accuracy_gate(measure, ribbed, loops_at)
        worse = acc_ribbed if (acc_ribbed.value or 0.0) >= (acc_uniform.value or 0.0) \
            else acc_uniform
        worse.detail += '  [annulus: %s]' % _fmt(acc_uniform.value)
        out.append(worse)

    out.append(discrimination_gate(measure, patched, loops_at))
    return out


def screen_full(measures, fixtures, loops_at, real_shape=None, real_z=None, App=None,
                levels=LEVELS, cost_stations=12):
    """Score every candidate against all five gates. **The screening run, as one callable.**

    `measures` is `{name: callable}`. G1, G3 and G4 come from the fixtures, where closed-form truth
    exists. **G2 comes from `real_shape` when one is given**, because a synthetic annulus cannot
    expose the non-convergence being screened for -- see `convergence_gate_on_section`. G5 is timed
    on the same real wall. Without a real wall the result is a partial screening and says so.

    Returns `{name: (results, cost_seconds)}`, ready for `rank` and `table`.
    """
    out = {}
    for name in sorted(measures):
        measure = measures[name]
        res = [locality_gate(measure, fixtures['thin_patch_tube'], loops_at)]

        smooth = convergence_gate(measure, fixtures['uniform_tube'], loops_at, levels)
        if real_shape is not None:
            conv = convergence_gate_on_section(measure, real_shape, real_z, App, levels)
            conv.detail += '  [smooth fixture: %s %s]' % (
                'pass' if smooth.passed else 'FAIL', _fmt(smooth.value))
        else:
            conv = smooth
            conv.detail += '  [NO REAL SECTION -- partial screening]'
        res.append(conv)

        acc_uniform = accuracy_gate(measure, fixtures['uniform_tube'], loops_at)
        ribbed = fixtures.get('ribbed_tube')
        if ribbed is not None:
            acc_ribbed = accuracy_gate(measure, ribbed, loops_at)
            worse = acc_ribbed if (acc_ribbed.value or 0.0) >= (acc_uniform.value or 0.0) \
                else acc_uniform
            worse.detail += '  [annulus: %s]' % _fmt(acc_uniform.value)
            res.append(worse)
        else:
            res.append(acc_uniform)

        res.append(discrimination_gate(measure, fixtures['thin_patch_tube'], loops_at))

        cost = None
        if real_shape is not None:
            bb = real_shape.BoundBox
            g5 = cost_gate(measure, real_shape, bb.ZMin + 1.0, bb.ZMax - 1.0, App,
                           stations=cost_stations)
            res.append(g5)
            cost = g5.value
        out[name] = (res, cost)
    return out


def rank(scored):
    """The pre-committed tie-break, applied to `{name: (results, cost_seconds)}`.

    Cheapest by G5; if two are within 2x on cost, the smaller G2 residual wins. Stated in code so
    that selecting the measure is arithmetic and not a preference.
    """
    passing = [(name, res, cost) for name, (res, cost) in scored.items()
               if all(r.passed for r in res)]
    if not passing:
        return []
    cheapest = min(c for _n, _r, c in passing if c is not None) if any(
        c is not None for _n, _r, c in passing) else None

    def key(item):
        name, res, cost = item
        g2 = next((r.value for r in res if r.gate.startswith('G2')), float('inf'))
        if cheapest is None or cost is None:
            return (0, g2)
        band = 0 if cost <= cheapest * 2.0 else 1
        return (band, g2 if band == 0 else cost)

    return [name for name, _r, _c in sorted(passing, key=key)]


def table(scored):
    """The screening result as text: one row per candidate, one column per gate."""
    names = ['G1 locality', 'G2 convergence', 'G3 accuracy', 'G4 discrimination', 'G5 cost']
    head = '%-26s' % 'candidate' + ''.join('%-19s' % g for g in names) + 'verdict'
    out = [head, '-' * len(head)]
    for name in sorted(scored):
        res, _cost = scored[name]
        by = dict((r.gate, r) for r in res)
        cells = []
        for g in names:
            r = by.get(g)
            cells.append('-' if r is None else
                         ('%s %s' % ('pass' if r.passed else 'FAIL', _fmt(r.value))))
        failed = [r.gate.split()[0] for r in res if not r.passed]
        verdict = 'SELECTABLE' if not failed else 'rejected: ' + ', '.join(failed)
        out.append('%-26s' % name + ''.join('%-19s' % c for c in cells) + verdict)
    return '\n'.join(out)
