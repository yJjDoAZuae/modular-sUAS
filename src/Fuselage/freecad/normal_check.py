"""IP-WTM-26: is the tail's residual missing material, or an in-plane reading pointed the wrong way?

**The question, narrowed to what is left of it.** Every over-tolerance reading on a cowl wall has
now been accounted for except one. On a `nose_cowl_shell` the thinning was the convergence criterion
(section 6.8.3): at any `TAU` below 0.02 the worst configuration reaches 0.00268 mm, 3.7x inside
`WALL_TOL`. On a `tail_shell` it is none of that. `TAU` does not build one at all, generous seeding
buys 12 % and leaves the wall 3.3x over tolerance, and the reference surface accounts for 106 of its
114 over-tolerance stations but not the rest. What survives is a figure that IP-WTM-45 measured to be
**63 % junction artifact**: two independent exclusions, keyed on opposite contours, drop the same
samples and agree the real worst is 0.01345 mm rather than 0.03663.

**But both of those exclusions are still in-plane, and section 6.8.2.1 says exactly what that
leaves open**: "whether the real three-dimensional wall at a notch junction is at least `t` is a
different question, because every measure here is in-plane and the surfaces at a junction are
inclined to the layer plane. A 3-D normal-distance measurement would settle it and none exists in
this subsystem." `wall_measure.normal_distance` is that measure and this is the driver for it.

**What a reading here can and cannot say.** A 3-D *minimum* distance would be useless -- it is a
minimum over a superset of the in-plane one, so it is always smaller and could only make a thin
reading thinner. What the in-plane measure gets wrong at a junction is its direction: at a concave
turn its nearest point lies across the corner rather than through the material. So the measurement
is the depth of material found by leaving the inner surface along its **own outward normal**, which
can legitimately exceed the in-plane minimum. Two outcomes are informative and the driver separates
them:

* **exonerated** -- the in-plane figure fails `nominal - WALL_TOL` and the normal figure does not.
  The material is there and the in-plane reading was pointed the wrong way.
* **confirmed** -- both figures fail. The material really is absent and no exclusion rescues it.

**And a third outcome is silence, which is reported rather than hidden.** A sample on a crease has
two normals, and a crease is exactly where these samples are. `normal_distance` declines such a
sample as `on_crease` instead of choosing one of the two answers, and `normal_verdict` refuses to
call the run established if every thin sample declined -- because "the measure cannot see here" and
"the material is present" are different answers and must not share a verdict.

**No build.** This reads a saved wall, so it costs a file read plus the measurement: a `distToShape`
per candidate face to find the sample's own face, eight more for the parameter-free normal, and about
fifteen `isInside` calls to bisect the exit depth.

Usage, one `--pass` per argument (see `tau_study.py` for why)::

    freecadcmd normal_check.py --pass --kind=tail_shell --pass --u=0.5
    freecadcmd normal_check.py --pass --kind=nose_cowl_shell --pass --u=4.0 --pass --worst=6
    freecadcmd normal_check.py --pass --label=tail_shell_U0.5_base --pass --family=screen
    freecadcmd normal_check.py --pass --kind=tail_shell --pass --u=0.5 --pass --fitted=1
    freecadcmd normal_check.py --pass --kind=tail_shell --pass --u=0.5 --pass --worst=0
    freecadcmd normal_check.py --pass --kind=tail_shell --pass --u=1.0 \
                               --pass --zs=-72.2723 --pass --fitted=1 --pass --worst=16
    freecadcmd normal_check.py --pass --kind=tail_shell --pass --u=0.5 \
                               --pass --json=out/normal/tail05.json

Prints the per-sample table, then::

    NORMAL_CHECK {"label": ..., "established": ..., "n_exonerated": ..., "n_confirmed": ...}
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

from wall_measure import corpus, normal_distance as nd             # noqa: E402

#: The nominal wall: `cowl_n_perimeters` * `extrusion_width`. Absolute, so it is the same number at
#: every `U` -- which is why a thinness figure is comparable across the corpus at all.
NOMINAL = 0.6

#: Circumferential spacing each station is discretized at, in mm. `WALL_ARC`'s value, the spacing
#: IP-WTM-25 established a thickness measure needs: the gate's own 0.125 mm rather than the
#: construction's 0.20 mm, because this is a measurement and not a convergence criterion.
AROUND_MM = 0.125

#: How many of a station's thin samples get the 3-D treatment, worst first. Each is about a second;
#: the question is about the worst readings, and a station rarely has more than a dozen that fail.
WORST = 12


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def _write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, 'w') as handle:
        json.dump(payload, handle, default=str, indent=1)


def pick(label=None, kind=None, u=None, family='soak'):
    """The saved wall to measure, from either corpus. Raises with the options rather than guessing."""
    records = corpus.screen() if family == 'screen' else corpus.distinct()
    if not records:
        raise SystemExit('no saved walls in the %s corpus' % family)
    if label:
        for rec in records:
            if rec.label == label:
                return rec
        raise SystemExit('no %r in the %s corpus; have %s'
                         % (label, family, ', '.join(r.label for r in records)))
    for rec in records:
        if rec.kind == kind and float(rec.u) == float(u):
            return rec
    raise SystemExit('no %s at U=%s in the %s corpus; have %s'
                     % (kind, u, family, ', '.join(r.label for r in records)))


#: Retry tolerance for a thin sample the census cannot place at `ON_FACE_TOL` = 1e-6 mm.
#:
#: **Not cosmetic: an unplaced sample is one never asked whether it is on the fitted interior
#: surface**, and the first runs left 336 of 2 456 unplaced on a `tail_shell` at `U` = 1.0 and 86 of
#: 251 on a `nose_cowl_shell` at `U` = 4.0 -- against fitted-surface counts of 1 682 and 8. At those
#: proportions the census cannot be read until they are resolved. 1e-4 mm is the bisection's own
#: tolerance and still four orders inside `WALL_TOL`; a sample placed only at this slack is reported
#: as a separate `(loose)` class rather than folded in with the rest.
FALLBACK_TOL = 1.0e-4


def run(wall, zs, nominal=NOMINAL, around=AROUND_MM, worst=WORST, out=None, label='',
        only_surface=None, fallback_tol=None):
    """Scan the given stations and report. Returns `(stations, verdict)`."""
    out = out if out is not None else sys.stdout
    out.write('%s: %d station(s), %.3f mm circumferentially, nominal %.3f, worst %d a station%s\n'
              % (label, len(zs), around, nominal, worst,
                 '' if only_surface is None else ', only samples on %s' % only_surface))
    out.flush()
    stations, started = [], time.time()
    for z in zs:
        at = time.time()
        station = nd.station_normals(wall, z, nominal, App, Part, spacing=around, worst=worst,
                                     only_surface=only_surface, fallback_tol=fallback_tol)
        stations.append(station)
        read = sum(1 for r in station['rows'] if r.get('thickness_mm') is not None)
        out.write('  z %10.4f  %4d sample(s), %3d thin in-plane, %2d measured, %2d read  '
                  '[%.0f s]\n'
                  % (z, station.get('samples') or 0, station.get('thin_in_plane') or 0,
                     len(station['rows']), read, time.time() - at))
        out.flush()
    if worst:
        out.write('\n' + nd.normal_table(stations, nominal) + '\n')
    # **How deep in the in-plane ranking the readings that are wall thicknesses sit.** This is
    # OQ-DES-CW33 alternative 2's own prerequisite: that alternative re-measures the worst `N`
    # samples a station, so it stands or falls on whether in-plane severity ranks them near the top.
    selector = nd.selector_verdict(stations)
    out.write('\n' + nd.rank_table(selector) + '\n')
    out.write('SELECTOR: %s -- %s of %d station(s) carry a reading on the fitted surface; '
              'deepest rank %s, so a worst-N pass needs **N = %s** to catch them all '
              '(out of %d thin sample(s))\n'
              % ('ESTABLISHED' if selector['established'] else 'ESTABLISHES NOTHING',
                 selector['stations_with_kind'], selector['stations'],
                 selector['deepest_rank'], selector['needed_n'], selector['thin_total']))
    for reason in selector['vacuous_because']:
        out.write('  VACUOUS    %s\n' % reason)
    verdict = nd.normal_verdict(stations, nominal)
    # **The census first, because on a real wall it is what answers the question.** Which face class
    # a reading under tolerance was taken on decides whether it is a wall thickness at all.
    for kind, n in sorted(verdict['thin_surfaces'].items(), key=lambda kv: -kv[1]):
        out.write('  ON         %-32s %4d of %d thin sample(s)%s\n'
                  % (kind, n, verdict['thin_total'],
                     '   <-- the fitted interior surface' if kind == nd.FITTED_SURFACE else ''))
    for why, n in sorted(verdict['declined'].items()):
        out.write('  DECLINED   %-32s %4d sample(s)\n' % (why, n))
    for reason in verdict['vacuous_because']:
        out.write('  VACUOUS    %s\n' % reason)
    out.write('VERDICT: %s -- %d station(s), %d thin in-plane (%d on the fitted surface), '
              '%d re-measured, %d read, %d oblique, **%d exonerated**, **%d confirmed**; '
              'worst in-plane %s, worst aligned normal %s\n'
              % ('ESTABLISHED' if verdict['established'] else 'ESTABLISHES NOTHING',
                 verdict['stations'], verdict['thin_total'], verdict['thin_on_fitted'],
                 verdict['samples'], verdict['read'], verdict['n_oblique'],
                 verdict['n_exonerated'], verdict['n_confirmed'],
                 'n/a' if verdict['worst_in_plane_mm'] is None
                 else '%.5f' % verdict['worst_in_plane_mm'],
                 'n/a' if verdict['worst_normal_mm'] is None
                 else '%.5f' % verdict['worst_normal_mm']))
    out.write('  %.0f s in all\n' % (time.time() - started))
    out.flush()
    return stations, verdict


def main():
    family = _opt('family', 'soak')
    rec = pick(_opt('label'), _opt('kind', 'tail_shell'), _opt('u', '0.5'), family)
    wall = corpus.load(Part, rec)
    print('normal_check: %s, %d faces' % (rec.label, len(wall.Faces)), flush=True)

    # **The acceptance grid's own station count, on the wall's real sectioning extent.** Section
    # 6.7 is the reason it is not the bounding box: on a `nose_cowl_shell` at `U` = 4 the box is
    # twice the part and a grid across it puts half its stations in empty space. Comparability is
    # the point -- IP-WTM-45's exclusion figures and section 6.8.2's split are taken here.
    # `--zs` names stations outright, for following up one the grid already found. Kept separate
    # from `--stations` because changing the count moves every station, so a station identified on a
    # 12-point grid cannot be revisited by asking for a different number of them.
    if _opt('zs'):
        zs = [float(v) for v in _opt('zs').split(',') if v]
    else:
        zs = corpus.measurable_station_grid(wall, int(_opt('stations', str(corpus.STATIONS))),
                                            App=App)
    # `--fitted` is the shorthand for the only face class whose readings are wall thicknesses.
    only = nd.FITTED_SURFACE if _opt('fitted') else _opt('only-surface')
    stations, verdict = run(wall, zs, float(_opt('nominal', str(NOMINAL))),
                            float(_opt('around', str(AROUND_MM))),
                            int(_opt('worst', str(WORST))), label=rec.label, only_surface=only,
                            fallback_tol=float(_opt('fallback-tol', str(FALLBACK_TOL))))
    payload = {'label': rec.label, 'kind': rec.kind, 'u': rec.u, 'faces': len(wall.Faces),
               'nominal': float(_opt('nominal', str(NOMINAL))),
               'around_mm': float(_opt('around', str(AROUND_MM))),
               'stations': stations, 'verdict': verdict,
               'selector': nd.selector_verdict(stations)}
    if _opt('json'):
        _write_json(_opt('json'), payload)
    print('NORMAL_CHECK ' + json.dumps(payload, default=str), flush=True)
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    sys.exit(main())
