"""IP-FC-117: judge the soak's repeats against OQ-ARCH-19's reproducibility criterion.

    freecadcmd soak_compare.py --pass --results=DIR/soak_results.jsonl

`soak_cowl_shell.py` builds one variant per process and keeps its wall as a BREP, because the
spread this row exists to characterise was found *between* processes and the criterion is
pairwise. This is the other half: it reads those records, groups the repeats by (kind, `U`),
and compares each pair.

**The criterion is not this file's to choose.** [OQ-ARCH-19](../../../doc/architecture/freecad_migration.md)
decided it on 2026-09-06 and IP-FC-124 implemented the screen:

* **Screen** with `mesh_stats.canonical_hash`. Equal hashes mean the same set of triangles and
  therefore the same geometry, exactly. Its errors run one way only -- a last-bit coordinate
  difference makes it say "different" about parts that agree, which costs a closer look, and it
  can never say "same" about parts that differ. So an equal hash ends the comparison.
* **Adjudicate** what the screen flags, against two thresholds, both measured at about four
  times what reproduction actually costs:

      XOR / (A * 100U)        <= 1.0e-6
      max surface gap / 100U  <= 5.0e-5

  Both nondimensional, in the form OQ-ARCH-20 settled, so this reads on the same scale as the
  cross-backend check. The surface distance is a separate criterion because the volume metric
  is an integral and averages a local excursion away -- and on these parts 5 % of the surface
  carries 83 % of the difference.

**Why `surface_difference` and not a volume.** A signed difference of volumes lets a surface
that wanders out and back cancel itself; between two builds of the tail it read 0.006 mm3 where
the symmetric difference is 2.08 -- 260x larger. It is also the only one of the instruments
that survives the open-mesh defect IP-FC-117 found: `surface_difference` samples points and
calls `distToShape`, and never integrates the divergence theorem, so an unpaired edge in the
tessellation cannot corrupt it the way it corrupts `mesh_volume`.

**What a boolean would give instead, and why it is not used here.** `solid_measure` records
that the boolean symmetric difference is exact between solids that share surfaces and unusable
between independently built ones -- on two `tail_shell` builds it returned invalid shapes in 9
and 7 solids totalling 28.87 mm3, over 1054 s, for a pair whose walls agree to 2.08. Two builds
from separate processes are exactly the case it fails on.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', 'tools')))

import Part

import solid_measure
from corner_common import is_entry_point

#: OQ-ARCH-19's two thresholds, decided 2026-09-06. Not tunable here: a soak that moved the
#: bar it is judged against would be measuring the bar.
XOR_TOL = 1.0e-6
GAP_TOL = 5.0e-5

#: Samples per seed, and the seeds. **Three seeds of 800 rather than one run of 2400, and that
#: is a measured choice, not a preference.** Measured 2026-09-12 on the first pair this judged
#: -- two nose builds at `U` = 0.5:
#:
#:     N  = 400, 800, 1200, 2400 at one seed -> max gap 0.00250 mm every time
#:     seed = 99, 7, 1234 at N = 800          -> max gap 0.00250, 0.00264, 0.00247
#:
#: The gap half of the criterion is a **maximum**, and a maximum cannot average down: raising N
#: does not move it at all here, because it is finding a real feature of the gap field rather
#: than a rare outlier, and 400 samples already land in it. What does move it is the seed, by
#: about 7 % -- enough to straddle the threshold, so a single run returns a verdict that a
#: different seed would reverse. Three seeds at 800 cost exactly what one run at 2400 costs and
#: report that spread instead of hiding it; the XOR half, which is a mean, gets its error bars
#: from the same samples either way.
SAMPLES = 800
SEEDS = (99, 7, 1234)


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    if default is None:
        raise SystemExit('missing --%s=' % name)
    return default


def load(results_path):
    """Every usable record, grouped by (kind, `U`). Errors and volume-only records are
    dropped with a reason rather than silently: a pair missing a BREP cannot be adjudicated,
    and saying so is the point."""
    groups, skipped = {}, []
    with open(results_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if 'error' in rec:
                skipped.append((rec.get('kind'), rec.get('u'), rec.get('repeat'),
                                'build failed: %s' % rec['error']))
                continue
            if not rec.get('brep') or not os.path.isfile(rec['brep']):
                skipped.append((rec.get('kind'), rec.get('u'), rec.get('repeat'),
                                'no BREP on disk -- built before the shape was kept'))
                continue
            groups.setdefault((rec['kind'], rec['u']), []).append(rec)
    return groups, skipped


def compare(a, b):
    """One pair. Returns a dict carrying the screen, and the adjudication if the screen fired."""
    out = {'kind': a['kind'], 'u': a['u'], 'a': a['repeat'], 'b': b['repeat'],
           'hash_equal': a['wall_hash'] == b['wall_hash']}
    if out['hash_equal']:
        # Equal hashes are the end of it -- the same triangles are the same geometry, and no
        # tolerance can say anything stronger than "identical".
        out['verdict'] = 'IDENTICAL'
        return out

    sa, sb = Part.Shape(), Part.Shape()
    sa.importBrep(a['brep'])
    sb.importBrep(b['brep'])

    scale = 100.0 * float(a['u'])
    runs = []
    for seed in SEEDS:
        xor, stderr, area, mean_gap, max_gap = solid_measure.surface_difference(
            sa, sb, samples=SAMPLES, seed=seed)
        runs.append({'seed': seed, 'xor_mm3': xor, 'xor_stderr': stderr, 'area': area,
                     'mean_gap': mean_gap, 'max_gap': max_gap,
                     'xor_ratio': xor / (area * scale), 'gap_ratio': max_gap / scale})

    xr = [r['xor_ratio'] for r in runs]
    gr = [r['gap_ratio'] for r in runs]
    out.update(runs=runs,
               xor_ratio_min=min(xr), xor_ratio_max=max(xr),
               gap_ratio_min=min(gr), gap_ratio_max=max(gr))

    # **Every seed has to agree before this says anything.** A pair whose seeds straddle a
    # threshold has not been shown to pass or to fail; reporting either would be reporting the
    # seed. `MARGINAL` is the honest third answer, and it is a result in its own right -- it
    # says the pair sits within the method's own resolution of the bar.
    passes = [r['xor_ratio'] <= XOR_TOL and r['gap_ratio'] <= GAP_TOL for r in runs]
    out['verdict'] = ('SAME PART' if all(passes)
                      else 'DIFFERS' if not any(passes)
                      else 'MARGINAL')
    return out


def main():
    results_path = _opt('results')
    if not os.path.isfile(results_path):
        print('no results file at %s' % results_path)
        return 2

    groups, skipped = load(results_path)
    print('COMPARE -- %d (kind, U) group(s) with a usable build, %d record(s) skipped'
          % (len(groups), len(skipped)))
    for kind, u, repeat, why in skipped:
        print('  skipped %-16s U=%-5s repeat=%s  %s' % (kind, u, repeat, why))
    sys.stdout.flush()

    verdicts = []
    for (kind, u) in sorted(groups, key=lambda k: (k[0], float(k[1]))):
        recs = sorted(groups[(kind, u)], key=lambda r: r['repeat'])
        print('')
        print('%s  U=%s  -- %d build(s)' % (kind, u, len(recs)))
        if len(recs) < 2:
            print('  only one build; a pairwise criterion has nothing to compare')
            continue
        hashes = {r['wall_hash'][:12] for r in recs}
        print('  distinct hashes: %d of %d builds' % (len(hashes), len(recs)))
        # **Each repeat against the first, not every pair against every other.** All pairs of
        # five repeats is ten comparisons; against a reference it is four, and the question --
        # does this build reproduce -- is answered either way. At roughly nine minutes per seed
        # on the tail, that is the difference between a comparison pass that finishes and one
        # that costs more than the builds did.
        reference = recs[0]
        for other in recs[1:]:
            res = compare(reference, other)
            verdicts.append(res)
            if res['hash_equal']:
                print('  r%s vs r%s  IDENTICAL (equal canonical hash)' % (res['a'], res['b']))
            else:
                print('  r%s vs r%s  %-9s  XOR/(A*100U) %.3e..%.3e (tol 1.0e-6)   '
                      'max gap/(100U) %.3e..%.3e (tol 5.0e-5)   over %d seed(s)'
                      % (res['a'], res['b'], res['verdict'],
                         res['xor_ratio_min'], res['xor_ratio_max'],
                         res['gap_ratio_min'], res['gap_ratio_max'], len(SEEDS)))
            sys.stdout.flush()

    print('')
    tally = {}
    for v in verdicts:
        tally[v['verdict']] = tally.get(v['verdict'], 0) + 1
    print('DONE -- %d pair(s) compared: %s'
          % (len(verdicts),
             ', '.join('%d %s' % (n, k) for k, n in sorted(tally.items())) or 'none'))
    if tally.get('MARGINAL'):
        print('  %d pair(s) MARGINAL -- the seeds straddle a threshold, so the method cannot '
              'separate them from the bar. That is a result about the criterion as much as '
              'about the parts; see IP-FC-117.' % tally['MARGINAL'])
    out_path = os.path.join(os.path.dirname(results_path), 'soak_comparisons.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(verdicts, f, indent=2)
    print('written %s' % out_path)
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
