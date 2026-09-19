"""IP-FC-84: the 72-set batch itself -- every (`U`, panel) pair this backend can produce a
build kit for, not just one proven at a time.

    uv run python src/Fuselage/tools/sweep_variant_sets.py [--out DIR] [--force]

**The 72 pairs are read off the shared axes, not retyped.** `fuselage_variants.SHARED_AXES`
is `panel_variants.csv` and `bulkhead_size_variants.csv`, the same two files both bulkhead
families sweep against -- so `fv.family_combinations('bulkhead')`, deduplicated on
`(U, panel_name)`, is the authoritative 8x9 grid, the one `render_variant.py` itself lists.
Hand-copying the CSV values here would be a second copy of that grid to keep in sync.

**Bounded and instrumented, per the project's own batch-job rule, not a bare loop.** Each
pair writes a `_manifest.json` into its own output directory only after every one of
`draw_variant_set.PARTS` has been attempted for it, recording what was drawn, what was
owed, and how long the pair took. A pair whose manifest already exists is skipped on the
next invocation, so a run can be interrupted (Ctrl-C, a closed terminal, a machine restart)
and resumed by running this again with the same `--out` -- no wildcard cleanup, and no
work already on disk is redone. `--force` ignores existing manifests and redoes every pair,
for when the generator itself changed and the old sheets are known stale.

**Sized before running, not guessed.** `render_variant.py`'s own validity grid (piped to a
count) shows six of the eight buildable types valid at 44 of 72 (`U`, panel) pairs each and
the two cowling types valid at all 8 `U` values whenever queried at their own fixed 0 mm
panel (`draw_variant_set.FIXED_PANEL` always queries them there) -- 6*44 + 2*72 = 408, plus
the corner riding on `end_bolt`'s own 44, is 452 of the 9*72 = 648 slots this sweep visits,
the remaining 196 being genuinely invalid combinations `export_parameters.py` refuses, not
failures. Two sampled pairs (2 of 9 valid, 9 of 9 valid) measured 19 s/sheet including
`freecadcmd` startup, so 452 sheets is of the order of 2.5 hours end to end -- ask before
running this unattended on a machine that is needed for anything else meanwhile.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FREECAD_DIR = os.path.normpath(os.path.join(HERE, '..', 'freecad'))
sys.path.insert(0, HERE)
sys.path.insert(0, FREECAD_DIR)

import draw_variant_set as dvs
import freecad_render
import fuselage_variants as fv

MANIFEST_NAME = '_manifest.json'


def all_pairs():
    """Every (`U`, panel_name) point on the shared axes, in `family_combinations`'s own
    order. Deduplicated because that function also varies the type axis, which a (`U`,
    panel) pair does not care about -- the same pair recurs once per type otherwise."""
    seen = set()
    pairs = []
    for p in fv.family_combinations('bulkhead'):
        key = (p['U'], p['panel_name'])
        if key not in seen:
            seen.add(key)
            pairs.append(key)
    return pairs


def run_pair(u, panel, out_dir, freecadcmd, force):
    """One pair. Returns the manifest dict, or `None` if it was skipped because a manifest
    from a prior run is already there and `force` was not given."""
    the_dir = dvs.pair_dir(out_dir, u, panel)
    manifest_path = os.path.join(the_dir, MANIFEST_NAME)
    if not force and os.path.isfile(manifest_path):
        return None

    t0 = time.time()
    drawn, owed = dvs.build_set(u, panel, the_dir, freecadcmd, say=lambda s: None)
    elapsed = time.time() - t0

    manifest = {
        'U': u,
        'panel': panel,
        'drawn': [{'label': label, 'panel': p} for label, p in drawn],
        'owed': [{'label': label, 'reason': reason} for label, reason in owed],
        'elapsed_s': round(elapsed, 1),
    }
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main(argv):
    out_dir = dvs.DEFAULT_OUT
    if '--out' in argv:
        out_dir = argv[argv.index('--out') + 1]
    force = '--force' in argv

    try:
        freecadcmd = freecad_render.freecadcmd_path()
    except Exception as exc:                                            # noqa: BLE001
        print('freecadcmd not found: %s' % exc)
        return 2

    pairs = all_pairs()
    print('SWEEP -- %d (U, panel) pairs, out=%s%s'
          % (len(pairs), out_dir, ', --force' if force else ''))
    sys.stdout.flush()

    done = skipped = total_drawn = total_owed = 0
    t_start = time.time()
    for i, (u, panel) in enumerate(pairs, 1):
        manifest = run_pair(u, panel, out_dir, freecadcmd, force)
        if manifest is None:
            skipped += 1
            print('[%3d/%d] U=%-5s panel=%-8s SKIPPED (manifest exists)'
                  % (i, len(pairs), u, panel))
            sys.stdout.flush()
            continue
        done += 1
        total_drawn += len(manifest['drawn'])
        total_owed += len(manifest['owed'])
        avg = (time.time() - t_start) / done
        eta_min = avg * (len(pairs) - i) / 60.0
        print('[%3d/%d] U=%-5s panel=%-8s drawn=%d owed=%d  (%.0fs this pair, ETA %.0f min)'
              % (i, len(pairs), u, panel, len(manifest['drawn']), len(manifest['owed']),
                 manifest['elapsed_s'], eta_min))
        sys.stdout.flush()

    print('')
    print('DONE -- %d pairs run, %d skipped, %d sheets drawn, %d owed, %.1f min total'
          % (done, skipped, total_drawn, total_owed, (time.time() - t_start) / 60.0))
    sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
