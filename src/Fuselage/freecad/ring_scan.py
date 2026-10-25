"""Can any unperturbed build reach the severed-ring state? A dense axial scan, no build.

**The question, and why it is worth a run.** `cowl.md` OQ-DES-CW26 records that the rib cut can
break the finished wall's cross-section ring over 93 mm of its circumference while passing all five
of the construction's checks -- rib residue 0.000000 mm3, one valid solid, a healthy partition
identity, the mirror sewing closed, no exception. Alternative 1 of that question is "measure whether
an unperturbed build can reach it, then decide", and it is **partly answered**: the 28-build soak of
2026-10-06 ran with the annulus guard active and reported `missing_stations` = 0 for every build,
336 station readings with no severed section, and a separate 21-case design-input sweep never
produced a construction failure.

**That evidence is bounded by the axial sampling, and the item says so.** Twelve stations across a
tail of roughly 300 mm is about 25 mm apart. The reproduced break spanned 93 mm of the ring's
*circumference*; its extent in `z` was never measured, so an axially short break could sit between
two gate stations and be missed by every reading taken so far. The item names the closing move --
"a denser scan on a saved wall would close that, and costs a file read" -- and this is that scan.

**Three things keep it as cheap as it can be.**

* **No build.** The 12 distinct corpus walls are already on disk as `.brep`; this reads them.
* **No thickness.** `locate.state_profile` classifies the ring from the section loops alone.
  Locating a thin spot needs a distance from every inner sample to the outer loop and is the
  expensive part; whether the ring is closed does not need it.
* **The extent comes from sectioning, not from a bounding box.** A box on these solids is an outer
  bound only -- a nose wall at `U` = 4 has one twice the length of the part -- and a scan placed
  across it would report its empty half as `no_wall`, which in a scan looking for a broken ring is
  a false positive in the one tool meant to find one.

**It is not, however, "a file read", and OQ-DES-CW26's own evidence is what says so.** That item
estimates the closing scan at the cost of reading a file; alternative 2 of the same item records
that "the slice costs about 7 s on a 2464-face wall". A slice per station is the whole job, so the
estimate and the measurement in that one document disagree by orders of magnitude. **Measured
2026-10-11** on `tail_shell` at `U` = 3.0, 1 mm axially and 0.2 mm circumferentially: **16.3 s a
station** (50 stations in 814 s), 298 stations, about **81 minutes for one wall**.

**The whole corpus has since been run, and the cost model is the measured one, 2026-10-11:** twelve
walls, 1 704 stations at 1 mm axially and 0.2 mm circumferentially, **3 h 4 min**, at 1.2-2.2 s a
station on a `nose_cowl_shell` and 5.2-9.2 s on a `tail_shell`. **Budget by kind and station count,
not by `U`**: the per-station cost moves only 1.8x across an eightfold range of `U` within a kind
while the gap between the kinds is about 4x, so it tracks the face count (536 against 2 464) and not
the part's size. Two things cut it, and only the first was taken:

1. **One slice a station instead of two, taken.** `state_profile` reads `Wire.Length` off the wires
   it already sliced rather than calling `density.section_perimeter`, which slices again at the same
   `z`. Measured on the same wall before and after: **16.3 s a station to 8.1 s**, the 2x the
   arithmetic predicted.
2. **`--around` is the circumferential spacing, and 0.2 mm is finer than this question needs --
   not taken.** `WALL_TOL`-grade *thickness* needs 0.125 mm (section 6.6); *classifying* a ring only
   needs the sampled loops not to cross each other falsely, and the known false positive happened at
   2.9 mm (`locate.N_POINTS`). At 0.5 mm the chord sag on these radii is about 0.0016 mm against a
   0.6 mm wall, still an order of magnitude inside what it has to resolve, for 2.5x fewer points.
   **The corpus run kept 0.2 mm deliberately**, so that all twelve walls are one measurement at one
   density rather than a figure whose sampling has to be qualified per wall; the saving was not
   needed once the run fitted in an evening.

**Circumferential sampling is a spacing, never a count.** At a fixed 720 points a healthy `U` = 4
annulus was already misclassified as severed once (`locate.N_POINTS`), and in this scan that is
precisely the false positive that would matter. Every station derives its sample count from its own
perimeter.

**Any station reported severed is re-checked against the kernel before it is believed.**
`locate.ring_state` is point-in-polygon nesting on the sampled loops, which is a proxy for
`check_cowl_interior._is_annulus`'s face-building question. It agrees with the kernel on every case
the kernel calls healthy and is not a substitute for it at a tangency, so a positive is escalated
rather than reported.

Ordered by value, not by `U`: `tail_shell` at `U` = 3.0 first, because that is the exact
configuration the break was reproduced on.

**The whole corpus runs as one process a wall, not one process.** `--only` picks the wall and
`--json` says where its result goes; `--summarize` folds those files back into one verdict without
touching geometry. The reason is `freecadcmd`'s exit code, which is 0 even when the script raised:
the JSON is the only honest record of how far a run got, and a wall is up to an hour, so a crash on
the eleventh wall must not cost the ten already paid for.

**The input axis is a second population, not more of this one (IP-WTM-41).** The twelve walls above
vary `U` alone, with every other design input at the parameter sheet's literal, and that is the
bound this scan leaves. `--family=screen` scans `input_screen.py`'s walls instead -- one design
input moved per wall at a fixed `U` -- and the two are kept apart deliberately: a verdict has to be
able to say which population it covered.

**That population is measured too, 2026-10-14: 36 walls, 1 638 stations, every one a healthy
annulus**, at the same 1 mm axially and 0.2 mm circumferentially. Its cost confirms this module's
cost model rather than extending it -- **budget by kind and face count, not by `U`**: 35-89 s a nose
wall at 0.83-2.12 s a station against 536-928 faces, and 242-359 s a tail wall at 5.05-7.48 s a
station against 2 262-2 930 faces. A screen wall costs what a corpus wall of the same kind and size
costs, so a further screen is schedulable off the figures already here.

Usage, one `--pass` per argument (see `tau_study.py` for why)::

    freecadcmd ring_scan.py --pass --only=tail_shell_U3.0 --pass --axial=1.0
    freecadcmd ring_scan.py --pass --only=nose_cowl_shell_U4.0 --pass --json=out/scan/nose4.json
    freecadcmd ring_scan.py --pass --family=screen --pass --only=tail_shell_U0.5_top_diag_angle_hi
    freecadcmd ring_scan.py --pass --summarize=out/scan

The whole corpus, tails before noses and descending `U` within a kind -- the order the walls were
scanned in on 2026-10-11, and deliberate: the break was reproduced on a tail, and `U` = 4 is where
the acceptance grid is coarsest in millimetres, so an interrupted run leaves the walls that matter
most already finished. Skipping a wall that already has a result makes it resumable::

    for w in tail_shell_U4.0 tail_shell_U1.5 tail_shell_U2.0 tail_shell_U1.0 tail_shell_U0.5 \
             nose_cowl_shell_U4.0 nose_cowl_shell_U3.0 nose_cowl_shell_U2.0 \
             nose_cowl_shell_U1.5 nose_cowl_shell_U1.0 nose_cowl_shell_U0.5 tail_shell_U3.0; do
      [ -f "out/ring_scan/$w.json" ] && continue
      timeout 7200 freecadcmd ring_scan.py --pass "--only=$w" \
          --pass "--json=out/ring_scan/$w.json" > "out/ring_scan/$w.log" 2>&1
    done
    freecadcmd ring_scan.py --pass --summarize=out/ring_scan
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))

import FreeCAD as App                                              # noqa: E402,N813
import Part                                                        # noqa: E402

from corner_common import is_entry_point                           # noqa: E402

from wall_measure import corpus, locate                            # noqa: E402

#: Axial spacing, in mm, between scanned stations. **A spacing, not a count**, for the reason in
#: `locate.dense_grid`: the part's length scales with `U` and a defect's extent does not.
#:
#: 1.0 mm is twenty-five times finer than the acceptance grid's own ~25 mm on a tail, which is the
#: gap OQ-DES-CW26's evidence is bounded by. It is not chosen against a known defect width, because
#: the reproduced break's extent in `z` was never measured -- so this bounds how short a break could
#: still hide rather than guaranteeing none does.
AXIAL_MM = 1.0

#: Circumferential spacing, in mm, each station discretizes its loops at. `locate.TARGET_SPACING`'s
#: value: a third of the wall, so a chord's sag is well inside the quantity being classified.
AROUND_MM = 0.2

#: Scanned first, because it is the configuration OQ-DES-CW26's break was reproduced on.
PRIORITY = ('tail_shell_U3.0', 'tail_shell_U4.0', 'tail_shell_U1.5')


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def _write_json(path, payload):
    """Write the run's result where a later process can read it back."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, 'w') as handle:
        json.dump(payload, handle, default=str, indent=1)


def summarize(where, out=None):
    """Merge every per-wall JSON under `where` into one corpus verdict. No geometry, no kernel.

    The corpus scan runs **a process a wall** -- one `freecadcmd` per `--only`, each writing its own
    JSON -- so that an hour-long wall's crash costs that wall and not the ones already finished.
    This is the step that puts them back together, and it needs neither FreeCAD nor the walls.
    """
    out = out if out is not None else sys.stdout
    paths = ([where] if os.path.isfile(where)
             else sorted(os.path.join(where, n) for n in os.listdir(where) if n.endswith('.json')))
    walls, seen = [], set()
    for path in paths:
        with open(path) as handle:
            payload = json.load(handle)
        for wall in payload.get('walls', []):
            # A whole-corpus run and a per-wall run can both have written the same wall; keep one.
            if wall.get('label') in seen:
                continue
            seen.add(wall.get('label'))
            walls.append(wall)
    out.write(locate.scan_table(walls) + '\n')
    verdict = locate.scan_verdict(walls)
    for label, z in verdict['severed']:
        out.write('  SEVERED  %-26s z %.4f\n' % (label, z))
    for label, z in verdict['real_gaps']:
        out.write('  GAP      %-26s z %.4f\n' % (label, z))
    for label, d in verdict['kernel_disagreements']:
        out.write('  DISAGREE %-26s %s\n' % (label, d))
    out.write('VERDICT: %s -- %d station(s) across %d wall(s), %d severed, %d confirmed gap(s), '
              '%d slice artifact(s)\n'
              % ('CLEAN' if verdict['clean'] else 'FINDINGS', verdict['stations'],
                 verdict['walls'], len(verdict['severed']), len(verdict['real_gaps']),
                 verdict['artifacts']))
    out.write('RING_SCAN_SUMMARY ' + json.dumps(verdict, default=str) + '\n')
    out.flush()
    return 0


def ordered(records, only=None):
    """The corpus records to scan, highest-value first."""
    if only:
        return [r for r in records if only in r.label]
    rank = {name: i for i, name in enumerate(PRIORITY)}
    return sorted(records, key=lambda r: (rank.get(r.label.rsplit('_r', 1)[0], len(PRIORITY)),
                                          r.label))


def scan_wall(wall, axial=AXIAL_MM, around=AROUND_MM, out=None, label=''):
    """One wall, densely in `z`.

    Returns `(rows, severed, no_wall, meta)` -- every station's classification, the two kinds of
    station that are not a healthy annulus, and what the run cost. `meta` carries the real extent,
    the face count and the seconds, because the per-station cost is the figure a caller needs to
    schedule the rest of the corpus and it is not recoverable from the rows.
    """
    out = out if out is not None else sys.stdout
    extent = corpus.sectioning_extent(wall, App=App)
    # `extent` is handed on rather than let `dense_grid` find it again: the bisection behind it is
    # about forty sections on a wall whose box spans 400 mm, and this function already paid for it.
    zs = locate.dense_grid(wall, inset=1.0, App=App, spacing_mm=axial, extent=extent)
    out.write('  %-26s real z %s, %d station(s) at %.2f mm\n'
              % (label, '%.3f..%.3f' % extent if extent else 'UNKNOWN (box fallback)',
                 len(zs), axial))
    out.flush()
    at = time.time()
    seen = {'n': 0}

    def tick(row):
        seen['n'] += 1
        if seen['n'] % 50 == 0:
            out.write('      %d of %d, %.0f s\n' % (seen['n'], len(zs), time.time() - at))
            out.flush()

    rows = locate.state_profile(wall, zs, App=App, spacing=around, on_station=tick)
    elapsed = time.time() - at
    bad = locate.severed(rows)
    no_wall = [r for r in rows if r['state'] == locate.NO_WALL]
    meta = {'extent': list(extent) if extent else None, 'faces': len(wall.Faces),
            'seconds': elapsed, 'seconds_per_station': elapsed / len(zs) if zs else None}
    out.write('      %s  %d station(s), %d severed, %d no_wall  [%.0f s, %.1f s/station]\n'
              % (label, len(rows), len(bad), len(no_wall), elapsed,
                 meta['seconds_per_station'] or 0.0))
    for r in (bad + no_wall)[:10]:
        out.write('        z %10.4f  %-16s loops %d  area_ratio %s  samples %d\n'
                  % (r['z'], r['state'], r['loops'],
                     'n/a' if r['area_ratio'] is None else '%.4f' % r['area_ratio'],
                     r['samples']))
    out.flush()
    return rows, bad, no_wall, meta


def confirm(wall, rows, out=None):
    """Re-ask the kernel about any station this scan called not an annulus.

    **A positive is escalated, not reported.** The polygon nesting test is a proxy; it agrees with
    the kernel wherever the kernel says healthy and is not authoritative at a tangency, and it has
    produced a false positive before (`locate.N_POINTS`).
    """
    out = out if out is not None else sys.stdout
    suspect = [r['z'] for r in rows if r['state'] != locate.ANNULUS]
    if not suspect:
        return []
    out.write('    kernel confirmation on %d suspect station(s)\n' % len(suspect))
    # `agrees_with_kernel` returns only the stations where the two disagree, as
    # `(z, scan_state, kernel_says_annulus)`. An empty list is full agreement.
    disagree = locate.agrees_with_kernel(wall, suspect[:40], Part, App, spacing=AROUND_MM)
    if not disagree:
        out.write('      kernel agrees with the scan at all %d\n' % min(len(suspect), 40))
    for z, state, kernel_annulus in disagree:
        out.write('      z %10.4f  scan says %-16s kernel says %s  DISAGREE\n'
                  % (z, state, 'annulus' if kernel_annulus else 'not an annulus'))
    out.flush()
    return [{'z': z, 'scan': state, 'kernel_annulus': bool(k)} for z, state, k in disagree]


def confirm_no_wall(wall, rows, out=None):
    """Re-probe either side of every `no_wall` station. **Agreement with the kernel is not enough.**

    With zero wires the nesting test and `Part.makeFace` both say "not an annulus" and agree, which
    says nothing: `Shape.slice()` can return nothing at one exact plane on a healthy wall, and
    section 6.1 records a case returning a normal section 0.05 mm away. So a `no_wall` is only a
    finding if the wall is still absent a little either side, and that is what this asks.

    The first run of this scan found exactly one such station -- `z` = -293.9823 on `tail_shell` at
    `U` = 3.0 -- reported it `no_wall`, got the kernel to agree, and had no way to tell an artifact
    from a hole. This is the step that was missing.

    **That station is the only one in the corpus, and it is deterministic.** Across 1 704 stations on
    all twelve distinct walls it is the single `no_wall`, and the wall was scanned twice hours apart
    in separate processes: identical `z` to the last printed digit, identical six healthy neighbours.
    So the re-probe is a sound test rather than a lucky one -- an intermittent slicer failure could
    in principle also strike a neighbour, a deterministic one cannot.
    """
    out = out if out is not None else sys.stdout
    gaps = [r['z'] for r in rows if r['state'] == locate.NO_WALL]
    verdicts = []
    for z in gaps:
        near = locate.nearby_states(wall, z, App=App, spacing=AROUND_MM)
        artifact = locate.is_slice_artifact(near)
        out.write('    no_wall at z %.4f: %s\n'
                  % (z, 'SLICE ARTIFACT, the wall returns nearby' if artifact
                     else 'REAL GAP, absent either side too'))
        for r in near:
            out.write('        z %10.4f  %-16s loops %d  samples %d\n'
                      % (r['z'], r['state'], r['loops'], r['samples']))
        out.flush()
        verdicts.append({'z': z, 'slice_artifact': bool(artifact),
                         'nearby': [{'z': r['z'], 'state': r['state'], 'loops': r['loops']}
                                    for r in near]})
    return verdicts


def walls_of(family):
    """The population to scan. **Two corpora, and they are not merged.**

    `soak` is the 2026-10-06 corpus: twelve distinct walls varying `U` alone, every other design
    input at the parameter sheet's literal. That is the population IP-WTM-40 scanned, and the
    input axis is exactly the bound it left.

    `screen` is IP-WTM-41's: walls built by `input_screen.py`, each varying one design input at a
    fixed `U`. Kept separate because OQ-DES-CW26's remaining question is about that axis
    specifically, so a verdict has to be able to say which population it covered; a merged "the
    corpus" figure would mean a different thing depending on what had been built that week.

    `pairs` is the two-input interaction corpus: walls that move two design rows at once, which
    neither of the other two reaches. OQ-DES-CW26 names that axis as the one its alternative 1
    still has open, so it is a third population and not more of the second.
    """
    if family == 'screen':
        return corpus.screen()
    if family == 'pairs':
        return corpus.pairs()
    if family == 'soak':
        return corpus.distinct()
    raise SystemExit('unknown --family=%r -- soak, screen or pairs' % family)


def main():
    axial = float(_opt('axial', AXIAL_MM))
    around = float(_opt('around', AROUND_MM))
    only = _opt('only')
    out_json = _opt('json')
    family = _opt('family', 'soak')
    if _opt('summarize'):
        return summarize(_opt('summarize'))
    records = ordered(walls_of(family), only)
    print('ring_scan: %s family, %d wall(s), %.2f mm axially, %.2f mm circumferentially'
          % (family, len(records), axial, around), flush=True)
    results = []
    started = time.time()
    for rec in records:
        wall = corpus.load(Part, rec)
        rows, bad, no_wall, meta = scan_wall(wall, axial, around, label=rec.label)
        agree = confirm(wall, rows) if (bad or no_wall) else []
        gaps = confirm_no_wall(wall, rows) if no_wall else []
        real_gaps = [g['z'] for g in gaps if not g['slice_artifact']]
        results.append({'label': rec.label, 'stations': len(rows),
                        'severed': [r['z'] for r in bad],
                        'no_wall': [r['z'] for r in no_wall],
                        'no_wall_verdicts': gaps, 'real_gaps': real_gaps,
                        'states': locate.states(rows), 'kernel_disagreements': agree,
                        'axial_mm': axial, 'around_mm': around, 'meta': meta})
        # **Written after every wall, not at the end.** `freecadcmd` exits 0 on an uncaught
        # exception, so the artifact is the only honest record of how far a run got; a scan of the
        # whole corpus is hours, and losing the finished walls to the eleventh one's crash would
        # mean paying for them again.
        if out_json:
            _write_json(out_json, {'axial_mm': axial, 'around_mm': around, 'walls': results})
    total = sum(r['stations'] for r in results)
    # **Severed and a real gap are findings; a slice artifact is not.** Counting an artifact here
    # would report the plane the scan happened to choose as a defect in the part.
    flagged = [r for r in results if r['severed'] or r['real_gaps']]
    print('scanned %d station(s) across %d wall(s) in %.0f s; %d wall(s) with a severed ring or a '
          'confirmed gap' % (total, len(results), time.time() - started, len(flagged)), flush=True)
    print('RING_SCAN ' + json.dumps({'axial_mm': axial, 'around_mm': around,
                                     'walls': results}, default=str))
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    sys.exit(main())
