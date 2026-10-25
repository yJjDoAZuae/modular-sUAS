"""IP-WTM-28: `TAU` and `WALL_TOL` are not two thresholds on one quantity.

**What this answers, and why it had to be asked.** `cowl_interior.cavity`'s second pass converges
until the finished wall is within `TAU` of nominal, and the acceptance gate then asks whether the
wall is within `WALL_TOL`. Both are millimeters of wall error, so `TAU` = `WALL_TOL` reads like a
setting that makes the construction guarantee its own acceptance criterion
(`cowl.md` OQ-DES-CW28, alternative 1).

The two are measured differently, and the difference is not small. `_finished_wall_gap` takes a
plain minimum distance over the whole discretized inner loop at `CHECK_ARC` = 0.20 mm, with no
corner exclusion. The figure the corpus publishes -- and the one `tau_study` reports -- is
`candidates.corner_excluded_min` at 0.125 mm. Measured on `tail_shell` at `U` = 0.5, the two read
**0.03794 and 0.01346 mm on the same wall**, 2.8 times apart. So setting `TAU` = 0.01 does not ask
for a 0.01 mm wall; it asks pass 2's measure to reach 0.01 mm, and on that wall nothing the refiner
can do gets it there -- measured, it raises `Unconverged` against the 64-station patch budget after
3 827 s.

`locate.criterion_split` splits that difference into the part that is an instrument difference and
the part that is a disagreement about what a wall is:

* the **sampling term**, one measure read at both spacings, and
* the **corner term**, one spacing read by both measures.

Which measure *should* read the wall is `cowl.md` OQ-DES-CW29 and is not decided here. This script
reports what each one says, so that question and OQ-DES-CW28 can be answered against the same
numbers instead of against two different ones.

**Reads saved walls; no build, no boolean.** A station costs two sections and two distance fields,
so a twelve-station wall is seconds on a nose and tens of seconds on a tail.

Usage, one `--pass` per argument, and `freecadcmd`'s exit code is not to be trusted -- read the
printed table::

    freecadcmd criterion_check.py --pass --only=tail_shell_U0.5
    freecadcmd criterion_check.py

`--junctions` runs IP-WTM-45's measurement instead: the incumbent against the same minimum with
samples whose nearest point on the exterior sits at a **crease** dropped, which is how a reading
taken across a notch junction is separated from a thin wall::

    freecadcmd criterion_check.py --pass --only=tail_shell_U0.5 --pass --junctions
"""
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


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def check_wall(wall, label='', nominal=0.6, out=None):
    """One saved wall at the gate's own twelve stations, both measures at both spacings.

    **The grid is `measurable_station_grid`, not `station_grid`.** A bounding box overstates these
    walls -- a `nose_cowl_shell` at `U` = 4 has a box twice the part's length -- and a grid placed
    from it loses 3 to 7 of its 12 stations to empty space (section 6.7). The real extent comes
    from sectioning.
    """
    out = out if out is not None else sys.stdout
    started = time.time()
    zs = corpus.measurable_station_grid(wall, App=App)
    out.write('%s  %d face(s), %d station(s)\n' % (label, len(wall.Faces), len(zs)))
    out.flush()

    def _tick(row):
        """One line a station, so a stall names the station that owns it rather than going dark."""
        out.write('    %3d/%d  z %12.5f  %-8s  %5.0f s elapsed\n'
                  % (len(seen) + 1, len(zs), row['z'], (row['state'] or '-')[:8],
                     time.time() - started))
        out.flush()
        seen.append(row)

    seen = []
    rows = locate.criterion_split(wall, zs, nominal=nominal, App=App, on_station=_tick)
    out.write('\n'.join('    ' + line
                        for line in locate.criterion_table(rows).splitlines()) + '\n')

    def _worst(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return max(vals) if vals else None

    pass2, inc, sel = _worst('thin_pass2'), _worst('thin_incumbent'), _worst('thin_selected')
    seconds = time.time() - started
    if pass2 is not None and sel is not None:
        ratio = (pass2 / sel) if sel > 0 else float('inf')
        out.write('    pass 2 reads %.5f where the gate\'s selected measure reads %.5f '
                  '(%.2fx); incumbent %.5f. %.1f s, %.1f s a station\n'
                  % (pass2, sel, ratio, inc, seconds, seconds / max(1, len(zs))))
    violations = [r['z'] for r in rows if r.get('subset_violated')]
    if violations:
        out.write('    SUBSET VIOLATED at %d station(s): the corner-excluded measure cannot '
                  'report more thinness than the incumbent\n' % len(violations))
    out.flush()
    return {'label': label, 'stations': len(zs), 'rows': rows, 'seconds': seconds,
            'worst_pass2': pass2, 'worst_incumbent': inc, 'worst_selected': sel,
            'subset_violations': len(violations)}


def check_junctions(wall, label='', nominal=0.6, out=None):
    """IP-WTM-45: how much of this wall's thinness is read at a crease of its own exterior.

    The saved wall's outer loop **is** the notched exterior, so this asks `cavity`'s question with
    no build: is pass 2's large reading a thin wall, or an in-plane distance taken across the
    junction where a notch face meets the OML?
    """
    out = out if out is not None else sys.stdout
    started = time.time()
    zs = corpus.measurable_station_grid(wall, App=App)
    out.write('%s  junctions, %d station(s)\n' % (label, len(zs)))
    out.flush()
    seen = []

    def _tick(row):
        out.write('    %3d/%d  z %12.5f  %-8s  creases %-4s dropped %-5s %5.0f s\n'
                  % (len(seen) + 1, len(zs), row['z'], (row['state'] or '-')[:8],
                     row['creases'], row['dropped'], time.time() - started))
        out.flush()
        seen.append(row)

    rows = locate.junction_split(wall, zs, nominal=nominal, App=App, on_station=_tick)
    out.write('\n'.join('    ' + line
                        for line in locate.junction_table(rows).splitlines()) + '\n')
    out.flush()
    return rows


def main():
    only = _opt('only')
    nominal = float(_opt('nominal', '0.6'))
    junctions = any(a == '--junctions' for a in sys.argv)
    records = [r for r in corpus.distinct() if not only or only in r.label]
    print('criterion_check: %d wall(s)' % len(records), flush=True)
    walls = []
    for rec in records:
        wall = corpus.load(Part, rec)
        if junctions:
            check_junctions(wall, rec.label, nominal)
            continue
        walls.append(check_wall(wall, rec.label, nominal))
    if junctions:
        return 0
    bad = [w for w in walls if w['subset_violations']]
    ratios = [(w['label'], w['worst_pass2'] / w['worst_selected'])
              for w in walls
              if w['worst_selected'] not in (None, 0.0) and w['worst_pass2'] is not None]
    if ratios:
        worst = max(ratios, key=lambda kv: kv[1])
        print('%d wall(s): pass 2 over the selected measure ranges %.2fx to %.2fx, worst on %s'
              % (len(walls), min(r for _l, r in ratios), worst[1], worst[0]), flush=True)
    if bad:
        print('SUBSET VIOLATED on %d wall(s): %s'
              % (len(bad), ', '.join(w['label'] for w in bad)), flush=True)
    return 0


if is_entry_point(__name__):
    sys.exit(main())
