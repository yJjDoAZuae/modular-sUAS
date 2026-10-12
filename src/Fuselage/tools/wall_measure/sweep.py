"""IP-WTM-11: measure every saved wall with a chosen measure, and answer the compliance question.

The question this whole package exists for is whether the finished cowl wall meets `WALL_TOL` =
0.01 mm. It could not be answered before, because the only instrument that measured the real wall
did not converge: its minimum moved 0.13 mm across a refinement sweep while the wall it was
measuring did not move at all. With a measure that converges, the answer is a sweep over the 28
walls the 2026-10-06 soak saved -- **no cowl build, because the builds are already paid for**, at
0.2 s to load and about 1.1 s a station.

What comes out is one row per wall: the worst thinness the measure reports, how it compares against
the figure the soak recorded with the incumbent, and whether the wall meets the tolerance. The
comparison column is the point — it is the difference between "the wall is thin" and "the old
instrument said the wall was thin".

Nothing here imports a vendor module. `Part` and `App` arrive as arguments.
"""
import json
import time

import numpy as np

from . import corpus, sections


class StationReading(object):
    """One station of one wall, as one measure saw it."""

    __slots__ = ('z', 'worst', 'median', 'samples', 'note')

    def __init__(self, z, worst, median, samples, note=''):
        self.z = z
        #: How much thinner than nominal the worst sample read; 0.0 if nothing was under nominal.
        self.worst = worst
        self.median = median
        self.samples = samples
        self.note = note


def measure_wall(measure, shape, App, nominal, stations=corpus.STATIONS, level=1440, grid=None,
                 spacing=None):
    """Every station of one wall. Returns `(readings, worst_thin)`.

    `worst_thin` is `max(0, nominal - min_thickness)` over every station that **had a section**,
    which is the same one-sided quantity the soak records. Note what that leniency means: a station
    with no closed annular section contributes nothing, whereas `check_cowl_interior.main` counts
    one as a failure outright (`bad += 1`). So a `worst_thin` of 0.0 on a wall with four missing
    stations is not a pass, and `stations_measured` has to be read beside it.

    `grid` lets a caller measure several instruments on identical stations.

    **Pass `spacing`, not `level`. A fixed `level` is what made this function's first corpus figures
    wrong by a factor of six.** `level` is a sample *count* per loop, so the circumferential spacing
    it buys is proportional to the section's perimeter -- and a cowl's perimeter grows with `U` while
    its wall stays an absolute 0.6 mm. At `level` = 1440 that is 0.30 mm on a `tail_shell` at
    `U` = 1 and 1.45 mm at `U` = 4. Measured 2026-10-10 at `U` = 4, station `z` = -362.8182: the
    reading is 0.2136 mm at `level` = 1440 and **0.00264 mm** at a fixed 0.125 mm spacing, so 99 % of
    that station's published thinness was the discretization. With `spacing` the count is derived
    per station from its own perimeter and a reading means the same thing at every `U`.
    `density.SPACINGS` and the refinement study behind it are in `wall_measure.density`.
    """
    readings = []
    worst_thin = 0.0
    for z in (grid if grid is not None
              else corpus.measurable_station_grid(shape, stations, App=App)):
        n = level
        if spacing is not None:
            from . import density
            perimeter = density.section_perimeter(shape, z, App=App)
            if perimeter is not None:
                n = density.counts_for_spacing(perimeter, spacing)
        loops = sections.station_loops(shape, z, n, App=App)
        if len(loops) < 2:
            readings.append(StationReading(z, None, None, 0, 'fewer than two loops'))
            continue
        pts, thick = measure(loops[0], loops[1])
        if pts.shape[0] == 0 or not np.any(np.isfinite(thick)):
            readings.append(StationReading(z, None, None, 0, 'measure reported nothing'))
            continue
        lo = float(np.nanmin(thick))
        readings.append(StationReading(z, max(0.0, nominal - lo), float(np.nanmedian(thick)),
                                       pts.shape[0]))
        worst_thin = max(worst_thin, max(0.0, nominal - lo))
    return readings, worst_thin


def sweep(measures, Part, App, nominal, records=None, stations=corpus.STATIONS, level=1440,
          on_wall=None, spacing=None):
    """Measure every saved wall with **every** measure, on identical stations. One result per wall.

    `measures` is `{name: callable}`. Taking several and running them on the same sections is the
    whole point, not a convenience: the figure the soak recorded for the incumbent was taken on the
    *body*-based station grid, and this corpus can only produce the *wall*-based one
    (`corpus.station_grid`), so differencing against the recorded column compares answers about
    different places. Measuring every instrument here, on these stations, is the comparison that
    is actually valid. The recorded column is still carried, labelled as what it is.

    Section extraction is the expensive step and is shared across measures, so a paired run costs
    barely more than a single one.

    `on_wall(result)` is called after each wall: 28 walls take minutes, and a job that prints
    nothing for minutes is indistinguishable from a hung one.

    **`spacing` is the parameter to use; `level` is kept only for reproducing old figures.** See
    `measure_wall` for why a fixed sample count made this function's first corpus run wrong by a
    factor of six at `U` = 4. Each result records which of the two was used, so a row can never be
    read without knowing how it was sampled.
    """
    if callable(measures):
        measures = {'measure': measures}
    records = records if records is not None else corpus.available()
    out = []
    for rec in records:
        started = time.time()
        shape = corpus.load(Part, rec)
        # **The shape's real extent, not its bounding box.** A box on these solids is an
        # outer bound only -- a `nose_cowl_shell` wall at `U` = 4 has a box twice the
        # part's length -- so a box-based grid puts end stations where there is no wall and
        # loses 3 to 7 of 12 on every nose wall. Measured 2026-10-10: this recovers 12 of 12
        # on all six, and leaves every tail figure unchanged, the tail's box being tight.
        grid = corpus.measurable_station_grid(shape, stations, App=App)
        per_measure = {}
        coverage = {}
        medians = {}
        for name in sorted(measures):
            readings, worst = measure_wall(measures[name], shape, App, nominal, stations, level,
                                           grid=grid, spacing=spacing)
            per_measure[name] = worst
            coverage[name] = sum(1 for r in readings if r.worst is not None)
            vals = [r.median for r in readings if r.median is not None]
            medians[name] = float(np.nanmedian(vals)) if vals else float('nan')
        recorded = (rec.recorded or {}).get('worst_wall_error')
        result = {
            'kind': rec.kind,
            'u': float(rec.u),
            'repeat': rec.repeat,
            'label': rec.label,
            'worst_thin': per_measure,
            'stations_measured': coverage,
            'median_of_medians': medians,
            'stations': len(grid),
            #: What the soak recorded, on the **body**-based grid. Not comparable station for
            #: station with the figures above; kept for context, never differenced here.
            'soak_recorded_worst': recorded,
            #: **How this row was sampled, recorded so it can never be read without knowing.** A
            #: `spacing` row is comparable across `U`; a `level` row is not, and the first corpus
            #: sweep's `level` = 1440 rows were wrong by a factor of six at `U` = 4.
            'sampling': (('spacing %.5f mm' % spacing) if spacing is not None
                         else ('level %d samples' % level)),
            'spacing_mm': float(spacing) if spacing is not None else None,
            'level': None if spacing is not None else int(level),
            'elapsed_s': time.time() - started,
        }
        out.append(result)
        if on_wall is not None:
            on_wall(result)
    return out


def verdict(results, tolerance, name, full_coverage_only=True):
    """Summarize one measure's sweep: how many walls meet `tolerance` on complete coverage.

    **`full_coverage_only` defaults to true, and that is the honest default.** A wall where only
    five of twelve stations produced a section has not been shown to meet anything: the seven
    unmeasured stations could be the thin ones, and `check_cowl_interior` counts a station with no
    section as a failure rather than a skip. Counting such a wall as passing is how a sweep
    manufactures compliance.

    **A station with no section is a failure, not a skip -- settled, IP-WTM-19.** Two conventions
    were in use and they give different answers on the nose: `check_cowl_interior.main`, the
    acceptance gate, counts such a station `bad += 1` and fails the build; `soak_cowl_shell` counts
    it `missing_stations` and drops it from `worst_wall_error`. The gate's convention is adopted
    here, for a reason that is not a preference: a sweep's job is to say whether the part would pass
    the gate, so it has to score the way the gate scores, and the soak's convention makes a wall
    that is *absent* over half its length indistinguishable from a wall that is merely thin. The
    soak's own field keeps its meaning as a description of coverage -- it is a count of stations, not
    a verdict -- and nothing about it needs changing.

    So the three counts below are disjoint and sum to `walls`: `meets_tolerance` (fully measured and
    within `tolerance`), `fails_tolerance` (fully measured and thinner), and `fails_coverage`
    (not fully measured, which the gate fails). `walls_with_full_coverage` and
    `walls_excluded_for_coverage` remain as the plain coverage description they always were.
    """
    def covered(r):
        return (not full_coverage_only) or r['stations_measured'][name] >= r['stations']

    usable = [r for r in results if covered(r)]
    ok = [r for r in usable if r['worst_thin'][name] <= tolerance]
    uncovered = len(results) - len(usable)
    worst = max(usable, key=lambda r: r['worst_thin'][name]) if usable else None
    return {
        'measure': name,
        'tolerance': tolerance,
        'walls': len(results),
        'walls_with_full_coverage': len(usable),
        'walls_excluded_for_coverage': uncovered,
        'meets_tolerance': len(ok),
        #: Fully measured and thinner than `tolerance`.
        'fails_tolerance': len(usable) - len(ok),
        #: Not fully measured. The acceptance gate counts each missing station a failure, so a wall
        #: here fails on the gate's own convention rather than being set aside (IP-WTM-19).
        'fails_coverage': uncovered,
        #: What the gate would report: anything not demonstrated compliant.
        'fails_total': (len(usable) - len(ok)) + uncovered,
        'worst_label': worst['label'] if worst else None,
        'worst_thin': worst['worst_thin'][name] if worst else None,
    }


def disagreements(results, name_a, name_b, tolerance):
    """Walls where two measures, on identical stations, give different verdicts.

    This is the comparison the recorded soak column cannot support, because it was taken on a
    different station grid. Two measures run here were given the same sections, so a difference
    between them is a difference between instruments and nothing else.
    """
    out = []
    for r in results:
        a, b = r['worst_thin'][name_a], r['worst_thin'][name_b]
        if (a <= tolerance) != (b <= tolerance):
            out.append({'label': r['label'], name_a: a, name_b: b, 'delta': a - b,
                        'coverage': r['stations_measured'][name_a], 'stations': r['stations']})
    return out


def table(results, tolerance, names=None):
    """The sweep as text: one row per wall, one column per measure, coverage shown beside.

    Coverage is not decoration. A `0.0000` on five of twelve stations and a `0.0000` on twelve are
    different claims, and only the second is a pass.
    """
    names = names or sorted(next(iter(results))['worst_thin']) if results else []
    head = '%-26s' % 'wall' + ''.join('%22s' % n[:21] for n in names) + '%11s  %s' % (
        'soak', 'coverage')
    out = [head, '-' * len(head)]
    for r in sorted(results, key=lambda r: (r['kind'], r['u'], r['repeat'])):
        cells = []
        for n in names:
            v = r['worst_thin'][n]
            mark = 'meets' if v <= tolerance else 'THIN'
            cells.append('%12.4f %-8s' % (v, mark))
        soak = '-' if r['soak_recorded_worst'] is None else '%.4f' % r['soak_recorded_worst']
        cov = '/'.join(str(r['stations_measured'][n]) for n in names) + ' of %d' % r['stations']
        out.append('%-26s' % r['label'] + ''.join('%22s' % c for c in cells)
                   + '%11s  %s' % (soak, cov))
    return '\n'.join(out)


def write_jsonl(results, path):
    """Persist a sweep so a later run can be compared against it rather than re-argued."""
    with open(path, 'w', encoding='utf-8') as fh:
        for r in results:
            fh.write(json.dumps(r, sort_keys=True) + '\n')
    return path
