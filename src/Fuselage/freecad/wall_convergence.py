"""Does the selected wall-thickness measure converge across a wall, or only where it was gated?

**The question, and why it is worth a run.** `cowl.md` OQ-DES-CW26 alternative 3 is a finished-wall
thickness check at `WALL_TOL` = 0.01 mm, and its stated prerequisite is "a converged *local*
thickness measure". That alternative records the standing candidate as refuted -- the erosion guard,
exact on a clean polygon, did not finish in six minutes against the real section's B-spline boundary
-- and ends "what to try instead is open".

**It has not been open since 2026-10-10.** `wall_thickness_measure.md` screened five candidates
against five pre-committed gates and selected C4, `candidates.corner_excluded_min`: the incumbent
nearest-point minimum with samples within 0.30 mm of a concave corner dropped, since a nearest-point
distance at such a corner crosses the corner rather than the wall. C4 passed all five gates and the
disqualifying converse that a corner-blind measure would fail.

**But the two measures were not judged on comparable breadth, and that is what this closes.** The
incumbent was rejected on a 24-station survey -- still falling at 3840 samples at 17 of 24 stations
-- while C4 was selected on the convergence gate at **one** station, `nose_cowl_shell` at `U` = 1,
`z` = -44.8421. A measure that settles at one station is not thereby a converged instrument, and
alternative 3 cannot be answered with the narrower evidence. This runs both measures over the same
station grid, at the same spacings, on a saved wall, so the comparison is like for like.

**No build.** The corpus walls are on disk as `.brep` and `wall_measure.corpus` loads them.

Run it as::

    freecadcmd wall_convergence.py --pass --kind=nose_cowl_shell --pass --u=1.0
    freecadcmd wall_convergence.py --pass --kind=tail_shell --pass --u=0.5 --pass --stations=12

`freecadcmd`'s exit code is unreliable, so read the log and the JSON.

**Cost.** Each station sweeps six spacings from 2.0 mm down to 0.0625 mm, and the finest dominates:
on a ~1150 mm nose perimeter that is about 18 400 samples a loop, against the 3840 the incumbent was
rejected at. Budget from the per-station time this prints rather than from a station count alone,
and use `--spacings` to stop short of the finest when a run has to be bounded.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

import FreeCAD as App                                                  # noqa: E402
import Part                                                            # noqa: E402

from corner_common import is_entry_point                               # noqa: E402
from wall_measure import candidates, corpus, density                   # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'wall_convergence')

#: The two measures the comparison is about: the one OQ-DES-CW26 rejected, and the one selected to
#: replace it. Kept in this order so the printed table reads rejected-then-selected.
MEASURES = {
    'incumbent_nearest_point': candidates.nearest_point_min,
    'selected_corner_excluded': candidates.corner_excluded_min,
}


def _opt(name, default=None):
    """`--name=value` from the args behind `--pass`, which is how freecadcmd forwards them."""
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
        if arg == '--%s' % name:
            return '1'
    return default


def run(kind, u, stations, spacings, out_dir):
    started = time.time()
    record = corpus.one(kind=kind, u=u)
    if record is None:
        print('no saved wall for %s U=%g' % (kind, u))
        return None
    shape = corpus.load(Part, record)
    # `App` is not optional here despite its default: `closed_wires` builds the slice direction
    # with it, and without it the kernel is handed a tuple and the grid fails before any
    # measuring starts.
    zs = corpus.measurable_station_grid(shape, stations=stations, App=App)
    print('')
    print('%s U=%g: %d faces, %d station(s), spacings %s'
          % (kind, u, len(shape.Faces), len(zs),
             ', '.join('%g' % s for s in spacings)))

    at = [time.time()]

    def progress(row):
        print('   z %9.4f  %-26s settled=%-5s value %s  delta %s   (%.0f s)'
              % (row['z'], row['measure'], row['settled'],
                 'n/a' if row['value'] is None else '%.6f' % row['value'],
                 'n/a' if row['last_delta'] is None else '%+.6f' % row['last_delta'],
                 time.time() - at[0]))
        at[0] = time.time()

    rows = density.convergence_survey(shape, zs, MEASURES, App=App, spacings=spacings,
                                      on_station=progress)

    print('')
    print('  measure                      settled / stations')
    summary = {}
    for name in MEASURES:
        got, total = density.survey_verdict(rows, name)
        summary[name] = {'settled': got, 'stations': total}
        print('  %-28s %d / %d' % (name, got, total))

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    stem = os.path.join(out_dir, '%s_U%g' % (kind, u))
    with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
        fh.write(json.dumps({'kind': kind, 'u': float(u), 'stations': len(zs),
                             'spacings': list(spacings), 'summary': summary,
                             'rows': rows}, indent=1, sort_keys=True, default=float))
    print('')
    print('  wrote %s.json in %.0f s' % (stem, time.time() - started))
    return summary


def main():
    kind = _opt('kind', 'nose_cowl_shell')
    u = float(_opt('u', '1.0'))
    stations = int(_opt('stations', '24'))
    spacings = _opt('spacings')
    spacings = (tuple(float(s) for s in spacings.split(','))
                if spacings else density.SPACINGS)
    run(kind, u, stations, spacings, os.path.normpath(_opt('out-dir', OUT_DIR)))


if is_entry_point(__name__):
    main()
