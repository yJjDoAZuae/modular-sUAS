"""IP-FC-117: the cowl-shell reproducibility soak.

    uv run python src/Fuselage/tools/soak_shell_variants.py [--out DIR] [--force]

Builds both shelled cowl kinds at every `U` the item names -- 0.5, 1.0, 1.5, 2.0, 3.0, 4.0 --
with five repeats at `U` = 1.0 and `U` = 4.0 and one elsewhere, each repeat a fresh
`freecadcmd` process (not a loop in one process): the spread this item exists to
characterise was found *between* processes, not within one, so a soak that only repeated in
one process would not exercise the thing in question.

Each (kind, `U`, repeat) triple is one call to `soak_cowl_shell.py`, which does the actual
build and measurement and prints one `SOAK_RESULT {...}` or `SOAK_ERROR {...}` JSON line.
Results land in `out/soak_results.jsonl`, one JSON object per line, written as each build
finishes -- so a run that is interrupted keeps everything it already has. A (kind, `U`,
repeat) already present in that file is skipped on the next invocation unless `--force`,
the same resume shape `sweep_variant_sets.py` uses for the same reason: this is a real,
multi-hour batch job and it must not have to start over because it was interrupted once.

**Sized before running.** `U` = 1 measured close to the item's own "about ten minutes a
build" once the wall check and the two-instrument volume convergence are both included, and
`U` = 4 is expected to cost more (`--pass --u=4.0` builds four times the part). 2 kinds x
(4 U values x 1 repeat + 2 U values x 5 repeats) = 2 x 14 = 28 builds -- of the order of the
five hours a first estimate at 10 min/build would give, and this script reports the real
figure per build as it goes rather than trusting that estimate.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FREECAD_DIR = os.path.normpath(os.path.join(HERE, '..', 'freecad'))
sys.path.insert(0, HERE)

import freecad_render

WORKER = os.path.join(FREECAD_DIR, 'soak_cowl_shell.py')
DEFAULT_OUT = os.path.join(FREECAD_DIR, 'out', 'soak')

KINDS = ('nose_cowl_shell', 'tail_shell')
U_VALUES = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
#: At least five repeats at `U` = 1 and `U` = 4, per the item -- `U` = 1 is the reference
#: point every other measurement in this project is compared against, and `U` = 4 is named as
#: the case to expect trouble at (the 0.6 mm wall is proportionally thinnest there).
REPEATS = {1.0: 5, 4.0: 5}


def plan():
    """Every (kind, U, repeat) triple this soak runs, in a stable order."""
    out = []
    for kind in KINDS:
        for u in U_VALUES:
            for repeat in range(REPEATS.get(u, 1)):
                out.append((kind, u, repeat))
    return out


def load_done(results_path):
    """Which (kind, `U`, repeat) triples already have a record, of either sort.

    **A failed build counts as done and is not retried on resume.** A build that fails here
    fails reproducibly -- the tail at `U` = 0.5 fails the same way on every attempt, at a
    cost of about fifteen minutes each -- so retrying it on every resume would spend the
    whole soak re-confirming one known answer. `--force` is how to make it try again.
    """
    done = set()
    if not os.path.isfile(results_path):
        return done
    with open(results_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            done.add((rec['kind'], rec['u'], rec['repeat']))
    return done


def run_one(freecadcmd, kind, u, repeat, shapes_dir):
    """One `freecadcmd` invocation. Returns `(record, raw output)`.

    `record` is the worker's own parsed `SOAK_RESULT`/`SOAK_ERROR` payload, or -- when
    neither line came back at all, a crash `soak_cowl_shell.py` could not report on itself --
    an error record made here, so that case is recorded rather than silently dropped.
    freecadcmd's exit code is not trusted for any of this, the same reasoning as
    `draw_set.draw`: the artefact is what says whether the run worked."""
    argv = [freecadcmd, WORKER, '--pass', '--kind=%s' % kind, '--pass', '--u=%s' % u,
            '--pass', '--repeat=%s' % repeat, '--pass', '--out=%s' % shapes_dir]
    done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = done.stdout.decode('utf-8', 'replace')
    for line in text.splitlines():
        if line.startswith('SOAK_RESULT '):
            return json.loads(line[len('SOAK_RESULT '):]), text
        if line.startswith('SOAK_ERROR '):
            return json.loads(line[len('SOAK_ERROR '):]), text
    return {'kind': kind, 'u': u, 'error': 'no SOAK_RESULT/SOAK_ERROR line in output'}, text


def main(argv):
    out_dir = DEFAULT_OUT
    if '--out' in argv:
        out_dir = argv[argv.index('--out') + 1]
    force = '--force' in argv
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    results_path = os.path.join(out_dir, 'soak_results.jsonl')
    log_path = os.path.join(out_dir, 'soak_log.txt')
    # Each build's wall is kept here for `soak_compare.py`: OQ-ARCH-19's criterion is pairwise
    # and every build is its own process, so the shapes have to outlive the process that made
    # them or there is nothing to compare.
    shapes_dir = os.path.join(out_dir, 'shapes')

    try:
        freecadcmd = freecad_render.freecadcmd_path()
    except Exception as exc:                                            # noqa: BLE001
        print('freecadcmd not found: %s' % exc)
        return 2

    triples = plan()
    done = set() if force else load_done(results_path)
    print('SOAK -- %d builds (%d already done), out=%s'
          % (len(triples), sum(1 for t in triples if t in done), out_dir))
    sys.stdout.flush()

    t_start = time.time()
    completed = 0
    with open(results_path, 'a', encoding='utf-8') as results_f, \
            open(log_path, 'a', encoding='utf-8') as log_f:
        for i, (kind, u, repeat) in enumerate(triples, 1):
            if (kind, u, repeat) in done:
                print('[%3d/%d] %-16s U=%-4s repeat=%d  SKIPPED (already done)'
                      % (i, len(triples), kind, u, repeat))
                sys.stdout.flush()
                continue
            t0 = time.time()
            record, raw = run_one(freecadcmd, kind, u, repeat, shapes_dir)
            elapsed = time.time() - t0
            record['repeat'] = repeat
            record['elapsed_s'] = round(elapsed, 1)
            results_f.write(json.dumps(record) + '\n')
            results_f.flush()
            log_f.write('=== %s U=%s repeat=%d ===\n%s\n' % (kind, u, repeat, raw))
            log_f.flush()

            completed += 1
            avg = (time.time() - t_start) / completed
            remaining = sum(1 for t in triples[i:] if t not in done)
            eta_min = avg * remaining / 60.0
            if 'error' in record:
                print('[%3d/%d] %-16s U=%-4s repeat=%d  ERROR: %s  (%.0fs, ETA %.0f min)'
                      % (i, len(triples), kind, u, repeat, record['error'], elapsed, eta_min))
            else:
                # **`volume_reliable` belongs on this line, not only in the JSON.** The first
                # real run put five unreliable volumes on screen looking exactly like the good
                # ones -- the flag existed by then and reading it still meant opening the
                # results file separately, which is how four more builds went by before anyone
                # noticed. An unreliable reading is marked where it is read.
                print('[%3d/%d] %-16s U=%-4s repeat=%d  vol=%.4f%s solids=%d wall_err=%.4f '
                      'rib_err=%.4f slip=%.2e  (%.0fs, ETA %.0f min)'
                      % (i, len(triples), kind, u, repeat, record['wall_volume'],
                         '' if record.get('volume_reliable', True)
                         else ' UNRELIABLE(%d open edges)' % record.get('open_edge_count', -1),
                         record['solids'], record['worst_wall_error'],
                         record['worst_rib_error'], record['partition_slip'],
                         elapsed, eta_min))
            sys.stdout.flush()

    print('')
    print('DONE -- %d builds run, results in %s' % (completed, results_path))
    sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
