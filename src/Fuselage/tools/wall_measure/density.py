"""Sampling density as a *spacing*, not a count, because the cowl scales with `U` and the wall does not.

`unit_width` = `U` * 100, so every length on a cowl's parameter sheet is a fraction of `U` except
two: `cowl_n_perimeters` and `extrusion_width`, which are absolute because a nozzle does not scale
with the airframe. The wall is their product, 0.6 mm, at every `U`. A tail section's perimeter
therefore grows roughly linearly with `U` while the quantity being measured across it stays fixed.

**Every measurement of that wall so far has fixed the sample count, which makes the spacing scale
with `U`.** `check_cowl_interior.wall_thickness` discretizes the inner loop at `AROUND` = 240 points
and the outer at `8 * AROUND`, regardless of `U`. `sweep.measure_wall` uses `level` = 1440 for both.
`cowl_interior`'s own `check_samples` does *not* -- it is arc-length based at `CHECK_ARC` = 0.20 mm,
which is why pass 2's scan density holds up at large `U` -- so the inconsistency is between the
construction and the things that measure it.

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

This module measures a reading against spacing in millimetres, which is the form that is comparable
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

#: `check_cowl_interior.AROUND`, carried so this module can report what the gate achieves.
GATE_AROUND = 240

#: `check_cowl_interior`'s outer-loop multiplier.
GATE_OUTER_FACTOR = 8

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
    The count has to buy a target spacing in millimetres on whichever loop is longest, because that
    is the loop whose samples would otherwise be furthest apart. Anything needing the *outer* loop
    specifically must take it from `sections.station_loops`, which orders by enclosed area -- see
    `loop_lengths` on why those two orderings are not the same thing.
    """
    lengths = loop_lengths(shape, z, App=App)
    return lengths[0] if lengths else None


def counts_for_spacing(perimeter, spacing):
    """How many samples a loop of this length needs for roughly `spacing` mm between them."""
    return int(min(MAX_POINTS, max(16, round(float(perimeter) / float(spacing)))))


def gate_spacing(perimeter, around=GATE_AROUND, outer_factor=GATE_OUTER_FACTOR):
    """What circumferential spacing the production gate actually achieves on this section.

    Returns `(inner_mm, outer_mm)`. This is the diagnostic: at `U` = 1 the figures are ordinary and
    at `U` = 4 they are several millimetres on a 0.6 mm wall, and nothing in the gate reports it.
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

    A thinness that **falls** toward zero as the spacing refines is a discretization artefact: the
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


def artefact_fraction(rows):
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
