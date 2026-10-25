"""Sampling density as a *spacing*, not a count, because the cowl scales with `U` and the wall does not.

`unit_width` = `U` * 100, so every length on a cowl's parameter sheet is a fraction of `U` except
two: `cowl_n_perimeters` and `extrusion_width`, which are absolute because a nozzle does not scale
with the airframe. The wall is their product, 0.6 mm, at every `U`. A tail section's perimeter
therefore grows roughly linearly with `U` while the quantity being measured across it stays fixed.

**Every measurement of that wall fixed the sample count, which makes the spacing scale with `U`.**
`check_cowl_interior.wall_thickness` discretized the inner loop at `AROUND` = 240 points and the
outer at `8 * AROUND`, regardless of `U`, and `sweep.measure_wall` uses `level` = 1440 for both.
`cowl_interior`'s own `check_samples` did *not* -- it is arc-length based at `CHECK_ARC` = 0.20 mm,
which is why pass 2's scan density holds up at large `U` -- so the inconsistency was between the
construction and the things that measure it.

**The gate has since been fixed (IP-WTM-25) and now samples at `WALL_ARC` = 0.125 mm**, derived per
station from that station's own perimeter, with one spacing for both loops. The count-based figures
are kept here as `PRIOR_GATE_AROUND`/`prior_gate_spacing`, because every published corpus number
taken before the fix was taken with them and a reader comparing against one needs to know what it
was measured with. `sweep.measure_wall`'s `level` remains available for exactly that reason.

Two separate errors follow from a coarse discretization, and they push in opposite directions:

* **The inner loop is sampled too sparsely**, so the minimum is taken over fewer places and a thin
  spot between samples is missed. This *under*-reports thinness.
* **The outer loop is a polyline whose chords cut inside the true boundary.** A point on the inner
  loop then measures to a chord rather than to the curve, and reads *closer* than it is. This
  *over*-reports thinness, and it is the dangerous one, because it makes a sound wall look thin.

**On a smooth arc that second error is far too small to matter, and saying otherwise was this
module's first mistake.** For a circular arc of radius `R` sampled at spacing `s` the chord sags by
about `s^2 / (8R)`, which at the spacing the published corpus sweep used on a `tail_shell` at
`U` = 4 is about 0.0005 mm. The error measured on that wall was 0.18-0.21 mm -- four hundred times
larger. The smooth-arc calculation is correct arithmetic over the wrong geometry, and
`tests/test_wall_measure_density.py` keeps it as a recorded negative result rather than deleting it.
What the real sections have and a circle does not is **features of absolute size**: concave slot
mouths and rib flanks whose width is `t_cut + 2*n_p*w`, of which `2*n_p*w` = 1.2 mm does not scale
with `U` at all. A fixed sample count spends proportionally fewer samples on those features as the
part grows, and `realized_spacing` is here because the mean spacing turned out to be the wrong
number to reason from in the first place.

This module measures a reading against spacing in millimeters, which is the form that is comparable
across `U`. Nothing here imports a vendor module: `App` arrives as an argument.
"""
import numpy as np

from . import candidates, sections

#: Circumferential spacings, in mm, to refine through.
#:
#: The coarsest is worse than any production reading and the finest is a tenth of the wall, which
#: is a 32-fold refinement -- enough for a trend to declare itself. **It stops at 0.0625 mm because
#: of cost, not taste:** a `tail_shell` section at `U` = 4 is 2 088 mm round, so 0.0625 mm is 33 414
#: samples a loop and the distance computation is 1.1e9 point-segment pairs. Going one step finer
#: quadruples that. A caller who needs more can pass its own tuple.
SPACINGS = (2.0, 1.0, 0.5, 0.25, 0.125, 0.0625)

#: Spacing used for merely *finding* which station is worst, before refining at it. Coarser than
#: `SPACINGS`'s finest on purpose: locating the thin spot does not need the accuracy that measuring
#: it does, and the saved `U` = 4 wall takes minutes to scan at a fine spacing.
LOCATE_SPACING = 0.5

#: `check_cowl_interior.WALL_ARC` -- the spacing the production gate samples at since IP-WTM-25.
#:
#: **A mirror, and it has to be changed in step with the gate.** This module must import no vendor
#: module, so it cannot read the real constant; the pair is kept honest by
#: `tests/test_wall_measure_density.py`, which asserts the value against the gate's own source.
GATE_ARC = 0.125

#: `check_cowl_interior.WALL_MIN`/`WALL_MAX`, mirrored on the same terms as `GATE_ARC`. The floor
#: keeps a short section a polygon; the ceiling is a cost guard no swept configuration reaches.
GATE_MIN = 480
GATE_MAX = 60000

#: What the gate used **before** IP-WTM-25: a fixed 240 inner samples with the outer loop at eight
#: times that, at every `U`.
#:
#: Kept, rather than deleted with the defect, because every corpus figure published before the fix
#: was measured with them -- so `prior_gate_spacing` is what says that a `U` = 4 reading taken then
#: was sampled 8.7 mm apart on a 0.6 mm wall. Deleting it would leave those numbers in the
#: documents with nothing to explain them.
PRIOR_GATE_AROUND = 240
PRIOR_GATE_OUTER_FACTOR = 8

#: `cowl_interior.CHECK_ARC` -- the construction's own circumferential spacing, which is the one
#: figure in this subsystem already expressed as a spacing rather than a count.
CONSTRUCTION_ARC = 0.20

#: The wall, `cowl_n_perimeters * extrusion_width`, absolute at every `U`.
NOMINAL = 0.6

#: A cap, so a request for a very fine spacing on a very long section cannot ask the kernel for an
#: unbounded discretization. 2 000 000 points on one loop is already far past any useful density.
MAX_POINTS = 2000000


def loop_lengths(shape, z, App=None):
    """The true arc length of each closed loop of this section, **longest first**, from the wires.

    Taken from `Wire.Length` rather than from a sampled polyline, because the polyline's length is
    itself short by the chord error this module exists to measure, and using it would hide the
    effect in the denominator.

    **Longest, not outermost, and an earlier version of this said "outer first".** That was wrong
    by a mechanism `sections.station_loops` documents in the opposite direction: once a rib makes
    the inner loop trace into a notch and back out, the detour can add more perimeter than the
    smooth outer loop has while enclosing far less area, and on a real `tail_shell` two loops'
    lengths were measured within 0.25 % of each other while their areas were not close at all. So
    sorting by length does not order these loops by containment; `station_loops` sorts by enclosed
    area, which does.
    """
    wires = sections.closed_wires(shape, z, App=App)
    lengths = sorted((float(w.Length) for w in wires), reverse=True)
    return lengths


def section_perimeter(shape, z, App=None):
    """The longest closed loop's true arc length, or `None` when the station has no closed section.

    **Used to set a sample count, which is why longest rather than outermost is the right pick.**
    The count has to buy a target spacing in millimeters on whichever loop is longest, because that
    is the loop whose samples would otherwise be furthest apart. Anything needing the *outer* loop
    specifically must take it from `sections.station_loops`, which orders by enclosed area -- see
    `loop_lengths` on why those two orderings are not the same thing.
    """
    lengths = loop_lengths(shape, z, App=App)
    return lengths[0] if lengths else None


def counts_for_spacing(perimeter, spacing):
    """How many samples a loop of this length needs for roughly `spacing` mm between them."""
    return int(min(MAX_POINTS, max(16, round(float(perimeter) / float(spacing)))))


def gate_spacing(perimeter, arc=GATE_ARC, lo=GATE_MIN, hi=GATE_MAX):
    """What circumferential spacing the production gate achieves on this section, since IP-WTM-25.

    Returns `(inner_mm, outer_mm)`, which are now the same number: the gate derives one count from
    the longer loop and applies it to both. The pair is kept so a caller can still ask the question
    separately, and so the answer is comparable with `prior_gate_spacing`'s.

    **It is `arc` unless a clamp bites**, which is the only reason this is a function rather than a
    constant: at the floor a short section is sampled finer than asked, and at the ceiling a very
    long one coarser. Nothing in the swept range reaches either.
    """
    p = float(perimeter)
    n = max(lo, min(hi, int(round(p / float(arc)))))
    return p / n, p / n


def prior_gate_spacing(perimeter, around=PRIOR_GATE_AROUND, outer_factor=PRIOR_GATE_OUTER_FACTOR):
    """What the gate achieved **before** IP-WTM-25, for reading figures published then.

    Returns `(inner_mm, outer_mm)`. This is the diagnostic that found the defect: at `U` = 1 the
    figures are ordinary and at `U` = 4 they are several millimeters on a 0.6 mm wall, and nothing
    in the gate reported it. Both scale with the perimeter, which is the defect itself.
    """
    p = float(perimeter)
    return p / float(around), p / float(around * outer_factor)


def sweep_by_spacing(shape, z, measure=None, App=None, spacings=SPACINGS, nominal=NOMINAL):
    """One station's reading at each spacing. Returns a list of rows, coarsest first.

    Both loops are refined together, so a row's `spacing` is the circumferential spacing on each.
    Refining only the inner loop -- which is what raising `AROUND` alone would do -- leaves the
    outer polyline's chord sag in place, and that is the error that over-reports thinness.
    """
    measure = measure or candidates.corner_excluded_min
    perimeter = section_perimeter(shape, z, App=App)
    if perimeter is None:
        return []
    out = []
    for s in spacings:
        n = counts_for_spacing(perimeter, s)
        loops = sections.station_loops(shape, z, n, App=App)
        if len(loops) < 2:
            out.append({'spacing': float(s), 'samples': n, 'minimum': float('nan'),
                        'median': float('nan'), 'thin': float('nan'), 'perimeter': perimeter})
            continue
        _pts, thick = measure(loops[0], loops[1])
        lo = float(np.nanmin(thick))
        out.append({'spacing': float(s), 'samples': n, 'minimum': lo,
                    'median': float(np.nanmedian(thick)),
                    'thin': max(0.0, nominal - lo), 'perimeter': perimeter})
    return out


def realized_spacing(shape, z, samples, App=None):
    """What spacing `Wire.discretize(Number=samples)` **actually** delivers on this section.

    A nominal spacing is `perimeter / samples`, which assumes the discretization is uniform in arc
    length. A section wire here concatenates many edges -- B-spline runs, lines, the notch flanks --
    and if points are apportioned per edge rather than by length, the realized spacing is very
    uneven and the nominal figure is a fiction. Then a reading is set by the *worst* local spacing,
    not the average, and refining the count moves the worst stretch much less than it moves the
    mean.

    Returns one dict per loop, outer first, with the nominal spacing and the realized min, median
    and max. **Checked rather than assumed:** this function exists because a chord-sag calculation
    on the mean spacing came out 400 times too small to explain the error actually measured on a
    real wall, which means the mean spacing is the wrong number to reason from.
    """
    wires = sections.closed_wires(shape, z, App=App)
    rows = []
    for w in sorted(wires, key=lambda x: float(x.Length), reverse=True):
        pts = np.asarray([[p.x, p.y, p.z] for p in w.discretize(Number=int(samples))],
                         dtype=np.float64)
        lo, med, hi = sections.spacing_stats(pts)
        rows.append({'length': float(w.Length), 'samples': int(samples),
                     'nominal': float(w.Length) / float(samples),
                     'min': lo, 'median': med, 'max': hi,
                     'edges': len(w.Edges),
                     'max_over_nominal': hi / (float(w.Length) / float(samples))})
    return rows


def worst_station(shape, zs, measure=None, App=None, spacing=LOCATE_SPACING, nominal=NOMINAL):
    """Which of `zs` reads thinnest, measured at a fixed **spacing** so every station is comparable.

    Returns `(z, thin, perimeter)` or `(None, None, None)`. Separated from `sweep_by_spacing` so the
    expensive refinement runs at one station rather than at twelve.
    """
    measure = measure or candidates.corner_excluded_min
    best = (None, None, None)
    for z in zs:
        perimeter = section_perimeter(shape, z, App=App)
        if perimeter is None:
            continue
        loops = sections.station_loops(shape, z, counts_for_spacing(perimeter, spacing), App=App)
        if len(loops) < 2:
            continue
        _pts, thick = measure(loops[0], loops[1])
        if not np.any(np.isfinite(thick)):
            continue
        thin = max(0.0, nominal - float(np.nanmin(thick)))
        if best[1] is None or thin > best[1]:
            best = (float(z), thin, perimeter)
    return best


def trend(rows):
    """How the reading moves as spacing halves. Returns the deltas between successive rows.

    A thinness that **falls** toward zero as the spacing refines is a discretization artifact: the
    coarse outer polyline was cutting the corner. A thinness that holds is a real thin wall.
    """
    thin = [r['thin'] for r in rows]
    return [thin[i + 1] - thin[i] for i in range(len(thin) - 1)]


def settles_to(rows, tol=0.001):
    """`(settled, value, last_delta)` for the finest two rows: did the reading stop moving?

    `value` is the finest reading, which is the best available estimate of the truth at this
    station -- not the production figure, which is what this module is testing.
    """
    usable = [r for r in rows if np.isfinite(r['thin'])]
    if len(usable) < 2:
        return False, None, None
    last = usable[-1]['thin'] - usable[-2]['thin']
    return bool(abs(last) <= tol), usable[-1]['thin'], float(last)


def convergence_survey(shape, zs, measures, App=None, spacings=SPACINGS, tol=0.001,
                       on_station=None):
    """Does each measure settle at *every* station, or only at the one it was gated on?

    **Why this exists as its own function.** `gates.convergence_gate_on_section` scores a candidate
    at a single station, and C4 was selected on one: `nose_cowl_shell` at `U` = 1, `z` = -44.8421.
    The incumbent's rejection, by contrast, was a 24-station survey -- "still falling at 3840
    samples at 17 of 24 stations" -- so the two are not comparable evidence, and a measure that
    settles at one station is not thereby a converged instrument. `cowl.md` OQ-DES-CW26's
    alternative 3 turns on having one, so the survey has to match the breadth that rejected the
    incumbent rather than the breadth that selected its replacement.

    `measures` maps a name to a callable taking `(outer, inner)` and returning `(points,
    thicknesses)`, as `candidates`' do. Each is swept independently over the same stations and
    spacings: the question here is each measure's own refinement behavior, not the structural
    identity between them that `station_measures` relies on.

    `on_station`, if given, is called with each finished row, so a long run reports progress
    instead of going quiet for an hour.

    Returns one row per station per measure: `settled`, the finest `value`, the `last_delta` that
    decided it, and the full `rows` from `sweep_by_spacing`. A station the section cannot be read
    at comes back with `settled` `None` rather than being dropped, so the denominator stays the
    station count that was asked for.
    """
    out = []
    for z in zs:
        for name, measure in measures.items():
            rows = sweep_by_spacing(shape, z, measure=measure, App=App, spacings=spacings)
            if not rows:
                row = {'z': float(z), 'measure': name, 'settled': None, 'value': None,
                       'last_delta': None, 'rows': []}
            else:
                settled, value, last = settles_to(rows, tol=tol)
                row = {'z': float(z), 'measure': name,
                       'settled': None if value is None else bool(settled),
                       'value': value, 'last_delta': last, 'rows': rows}
            out.append(row)
            if on_station is not None:
                on_station(row)
    return out


def survey_verdict(rows, measure):
    """`(settled, total)` for one measure across a `convergence_survey`.

    A station the section could not be read at counts in `total` and not in `settled`: a measure
    that cannot produce a reading has not converged to one.
    """
    mine = [r for r in rows if r['measure'] == measure]
    return sum(1 for r in mine if r['settled']), len(mine)


def artifact_fraction(rows):
    """How much of the coarsest reading the refinement removed, as a fraction of it.

    1.0 means the whole reading was discretization; 0.0 means none of it was. Returns `None` when
    the coarsest reading is zero, where the fraction has no meaning.
    """
    usable = [r for r in rows if np.isfinite(r['thin'])]
    if len(usable) < 2 or usable[0]['thin'] <= 0.0:
        return None
    return (usable[0]['thin'] - usable[-1]['thin']) / usable[0]['thin']


def table(rows, nominal=NOMINAL):
    """The sweep as text, spacing against reading."""
    head = '%9s %9s %11s %11s %11s' % ('spacing', 'samples', 'minimum', 'thin', 'median')
    out = [head, '-' * len(head)]
    for r in rows:
        if not np.isfinite(r['minimum']):
            out.append('%9.5f %9d %11s %11s %11s'
                       % (r['spacing'], r['samples'], '-', '-', '-'))
            continue
        out.append('%9.5f %9d %11.6f %11.6f %11.6f'
                   % (r['spacing'], r['samples'], r['minimum'], r['thin'], r['median']))
    return '\n'.join(out)
