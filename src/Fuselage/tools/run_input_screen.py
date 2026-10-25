"""Drive `freecad/input_screen.py` over a whole case list, one process per case.

**One process per case is the point, not an accident.** A screen case changes a parameter sheet
and rebuilds; running them in one process would share a FreeCAD document, a triangulation cache
(OQ-DES-CW27) and whatever state a refused build leaves behind, so a case could be measured
against geometry a previous case made. A fresh `freecadcmd` per case costs about 3 s of start-up
against 48 s to 629 s of work, which is the cheapest isolation available.

**Resumable, because these runs are hours long.** A case whose record already exists is skipped,
so an interrupted run continues where it stopped rather than rebuilding what it has. Pass
`--force=1` to rebuild regardless.

**This replaces a scratch PowerShell loop.** The 2026-10-14 screen was driven by a script that
lived outside the repository, which meant the run that produced
[cowl.md](../../doc/design/cowl.md) OQ-DES-CW26's 1 638-station evidence could not be re-run from
the repository alone. Measurements belong with the code that makes them.

Run it as::

    python run_input_screen.py --kind=nose_cowl_shell --u=1.0 --pairs=1
    python run_input_screen.py --kind=tail_shell --u=0.5

Cost, measured from the records the screen has already written: **48 s a case** on a
`nose_cowl_shell` at `U` = 1 and **629 s** on a `tail_shell` at `U` = 0.5, build plus measure.
The pair population is 128 cases plus the baseline, so a nose pair run is about **1.7 hours** and
a tail one about **42 hours**; `--limit` bounds a run that has to fit a smaller window.
"""
import io
import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import freecad_render                                                   # noqa: E402
from wall_measure import inputs                                         # noqa: E402

SCREEN = os.path.normpath(os.path.join(_HERE, '..', 'freecad', 'input_screen.py'))


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def run_case(exe, kind, u, case, pairs, records_dir):
    """Build one case in its own process. Returns `(ok, seconds, record_or_none)`."""
    argv = [exe, SCREEN,
            '--pass', '--kind=%s' % kind,
            '--pass', '--u=%g' % u,
            '--pass', '--case=%s' % case.name]
    if pairs:
        argv += ['--pass', '--pairs=1']
    started = time.time()
    done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    took = time.time() - started
    # **`freecadcmd` exits 0 on a script exception, so the exit code is not the result.** The
    # record on disk is, and `input_screen` writes one on both paths -- a refused configuration
    # gets a record carrying its error, which OQ-DES-CW32 counts rather than loses.
    path = os.path.join(records_dir, '%s.json' % case.label)
    if not os.path.isfile(path):
        return False, took, None
    with io.open(path, encoding='utf-8') as fh:
        record = json.load(fh)
    return 'error' not in record, took, record


def main():
    kind = _opt('kind', 'nose_cowl_shell')
    u = float(_opt('u', '1.0'))
    pairs = bool(_opt('pairs', ''))
    force = bool(_opt('force', ''))
    limit = int(_opt('limit', '0'))
    records_dir = _opt('records', inputs.PAIR_RECORDS if pairs else inputs.SCREEN_RECORDS)
    exe = freecad_render.freecadcmd_path()

    if pairs:
        # **Default to pairs whose both members build on their own.** A pair containing a row
        # the construction already refuses alone is refused for that inherited reason, so
        # counting it among the pair screen's refusals would report an interaction that is not
        # there. `--members=all` keeps them, for a run that wants the refusal census instead.
        members = None
        if _opt('members', 'built') != 'all':
            members = inputs.built_single_names(kind, u)
            if members is None:
                raise SystemExit('no single-row screen records for %s U=%g; run that screen '
                                 'first, or pass --members=all' % (kind, u))
        cases = inputs.pair_cases(kind, u, members=members)
    else:
        cases = inputs.cases(kind, u)
    if limit:
        cases = cases[:limit]
    if not os.path.isdir(records_dir):
        os.makedirs(records_dir)

    todo = [c for c in cases
            if force or not os.path.isfile(os.path.join(records_dir, '%s.json' % c.label))]
    print('%s %s U=%g: %d case(s), %d to build, %d already recorded'
          % ('PAIR screen' if pairs else 'screen', kind, u, len(cases), len(todo),
             len(cases) - len(todo)))
    print('records -> %s' % records_dir)
    sys.stdout.flush()

    started = time.time()
    built = refused = missing = 0
    for i, case in enumerate(todo, start=1):
        ok, took, record = run_case(exe, kind, u, case, pairs, records_dir)
        if record is None:
            missing += 1
            state = 'NO RECORD'
        elif ok:
            built += 1
            state = 'built  %d solid(s) %.1f mm3' % (record.get('solids', -1),
                                                     record.get('volume_raw', float('nan')))
        else:
            refused += 1
            state = 'REFUSED %s' % str(record.get('error'))[:60]
        done = time.time() - started
        eta = (done / i) * (len(todo) - i)
        print('  %3d/%-3d %-58s %6.0f s  %s   [elapsed %.0f m, eta %.0f m]'
              % (i, len(todo), case.name, took, state, done / 60.0, eta / 60.0))
        sys.stdout.flush()

    print('')
    print('%d built, %d refused, %d with no record, in %.0f min'
          % (built, refused, missing, (time.time() - started) / 60.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
