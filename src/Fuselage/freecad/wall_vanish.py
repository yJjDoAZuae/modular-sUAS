"""At what displacement does the fitted wall vanish? Measured without a single boolean.

**The question.** `cowl.md` OQ-DES-CW26 reproduced a severed wall ring at a 0.03 mm row
displacement while 0.01 mm was benign, and `freecad_migration.md` IP-FC-146 records the threshold
as bracketed in (0.01, 0.03] mm with the mechanism unidentified. The obvious way to narrow it is a
dose series through the real cut, and that costs a tail build per dose.

**It does not need the cut.** A wall ring severs where the wall has no material left, and the
fitted interior reaching the exterior is a property of the *fit*, measurable before any boolean
runs. §5's first pass already measures exactly this quantity -- it sections the fitted surface,
samples the section, and takes the distance from each sample to the exterior polyline -- and
reduces it to the worst *departure from* `t`. Taking the **minimum** of the same distances instead
answers a different question: how much wall is left at its thinnest. When that reaches zero the
ring must come apart, and the dose at which it reaches zero is a prediction of the severance
threshold that costs a fit rather than a build.

So this is the cheap half of the dose series. It cannot say what the boolean does -- a wall that
still has material can sever for other reasons, and `shell_solid`'s own checks catch cases this
measure would call healthy -- so a threshold from here is a prediction to be confirmed against a
real cut, not a replacement for one.

**Three arms, and the differences between them are the point.**

- `--row=floor` perturbs a station that *survives* `station_floor(t)`, which is what a build
  today actually fits through. This is the arm that bears on whether current code can reach the
  severed state at all.
- `--row=historic` **forces** `z` = -283.9951339 into the station set before `_thin_stations`
  runs, so the filter sees it as one of two legitimate neighbors and may drop the other. That is
  the accident the original probe's seed set had, and it is a control against a known result
  rather than a measurement of anything that ships.
- `--row=unfloored` fits the **whole unfiltered union**, 32 stations at `U` = 3.0, in which that
  station occurs naturally and nothing is forced. This is the station set the construction seeded
  before IP-FC-144 and it is the only configuration OQ-DES-CW26's *silent* break has appeared in.

**Why the third arm was added, 2026-10-28.** Run through the real booleans on that set,
δ = 0.03 mm makes section 5's post-cut pass report a finished-wall gap of **0.5999 mm against
`t` = 0.600** -- the wall closed to 0.0001 mm, a hole rather than a thin spot -- flat to four
decimals across two rounds while 19 and then 46 stations were inserted, and then `Unconverged`.
So the failure reproduces and is caught. What that measurement cannot say is **which step loses
the wall**, because it is taken after the rib cut. This arm answers it: if the fit alone already
closes to zero on this station set, the fit is the carrier and the rib cut is incidental; if the
fit leaves material, the wall is lost in the cut. §4.4's existing "the fit alone predicts no
severance" was measured on the *floored* set and at a different station, so it does not settle it.

Run it as::

    freecadcmd wall_vanish.py --pass --kind=tail_shell --pass --u=3.0 --pass --row=floor
    freecadcmd wall_vanish.py --pass --kind=tail_shell --pass --u=3.0 --pass --row=historic
    freecadcmd wall_vanish.py --pass --kind=tail_shell --pass --u=3.0 --pass --row=unfloored

`freecadcmd`'s exit code is unreliable, so read the printed table and the JSON. One `--pass` per
argument.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App                                                    # noqa: E402

import cowl_interior as ci                                               # noqa: E402
import cowl_tree                                                        # noqa: E402
import si                                                                # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from station_gaps import BUILDERS, PARAMS, notch_compound, with_u        # noqa: E402
from wall_measure import fit_response as fr                              # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'wall_vanish')

#: The station OQ-DES-CW26's probe displaced, to four more decimals than the item's own heading
#: carries. Forcing a four-decimal *printing* of a notch edge into the seed set is what
#: manufactured a 0.0000459 mm pair and invalidated a whole run once (§6.1's sixth caution), so
#: the full value is used and never the printed one.
#:
#: **Converted from -283.9951339 mm by IP-FC-163, and this arm could not have run without it.**
#: The station set it is matched against comes from `ci.z_extent`, which has returned meters since
#: IP-FC-162, and the match is `abs(z - HISTORIC_Z) <= 1e-6`; a millimeter constant against a
#: meter station set misses by a factor of a thousand at every row, so the `historic` arm raised
#: `PreconditionFailed` -- "the historic station is not in this station set" -- whatever was built.
HISTORIC_Z_M = -0.2839951339

#: The dose series. Spans the bracket IP-FC-146 reports -- benign at 0.01 mm, severed at 0.03 mm
#: -- with five steps inside it, which is what "narrow the bracket" means here. Converted from
#: (0.0, 0.001, 0.003, 0.01, 0.014, 0.018, 0.022, 0.026, 0.03, 0.05, 0.1) mm.
DOSES_M = (0.0, 1.0e-6, 3.0e-6, 1.0e-5, 1.4e-5, 1.8e-5, 2.2e-5, 2.6e-5, 3.0e-5, 5.0e-5, 1.0e-4)

#: Axial spacing of the wall scan. The fitted surface is sectioned at every step, so this sets the
#: cost; 2 mm over a 300 mm tail is 150 sections a dose. Was 2.0 mm.
SCAN_M = 2.0e-3

#: How close a station has to be to `HISTORIC_Z_M` to be the same station. Was 1.0e-6 mm, and it
#: is a length, so it moved with the stations it compares (IP-FC-163).
SAME_STATION_M = 1.0e-9


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def harness(doc, kind, u):
    """`cavity`'s own station set and its two contour accessors, rebuilt outside it.

    `fit_at` and `outer_at` are closures inside `cavity`, so reaching them means reproducing the
    few lines that set them up. Every function they call is the real one, imported unmodified --
    the alternative is a second implementation of the eroded contour, which is the mistake
    §4.2 was written to stop.
    """
    cowl_tree.emit(doc, None, with_u(PARAMS[kind], u), BUILDERS[kind])
    doc.recompute()
    body_node, tools, _mirrors, _cell_cut = cowl_tree.pieces(doc)
    body = body_node.Shape
    # **The two cells are a `Spreadsheet`'s, so their product is millimeters, and every
    # `cowl_interior` function below takes meters** (IP-FC-163). Handing the raw product over as
    # `t` made every erosion a thousand times deeper than the wall it was supposed to leave, which
    # is the defect `sever_doses` shipped in its own form.
    t_m = si.m(float(doc.getObject('Params').get('cowl_n_perimeters'))
               * float(doc.getObject('Params').get('extrusion_width')))

    planes = ci.cell_boundary_planes(body)
    lo_m, hi_m = ci.z_extent(body)
    z_lo_m, z_hi_m = lo_m + ci.END_INSET_M, hi_m - ci.END_INSET_M
    arcs = {}

    def body_arc(z_m):
        k = round(z_m / ci.Z_TOL_M)
        if k not in arcs:
            wires = ci._slice_wires(body, z_m)
            if len(wires) != 1:
                raise ci.PreconditionFailed(
                    'the cell body sections into %d loops at z = %.4f mm, not one'
                    % (len(wires), si.mm(z_m)))
            arcs[k] = ci.open_arc(wires[0], planes)
        return arcs[k]

    widest_m = max(si.length_m(body_arc(z_m)[0])
                   for z_m in (z_lo_m, 0.5 * (z_lo_m + z_hi_m), z_hi_m))
    n_fit = ci.fit_samples(widest_m)
    n_check = ci.check_samples(widest_m)

    def fit_at(z_m):
        arc, p_start, p_end, flip = body_arc(z_m)
        return ci._resample_open(ci.eroded_arc(arc, t_m, z_m, p_start, p_end, flip), n_fit)

    def outer_at(z_m):
        arc, _p0, _p1, flip = body_arc(z_m)
        return ci.open_contour(arc, n_check, flip)[1]

    return {'body': body, 'notches': notch_compound(tools), 't_m': t_m,
            'z_lo_m': z_lo_m, 'z_hi_m': z_hi_m,
            'fit_at': fit_at, 'outer_at': outer_at, 'n_check': n_check,
            'n_fit': n_fit, 'planes': planes}


def stations(h, force_m=None):
    """The station set `cavity` would fit through, optionally with `force` unioned in first.

    `force_m` is how the historic arm defeats the floor: the station is added to the union
    *before*
    `_thin_stations` runs, so the filter sees it as one of two legitimate neighbors and may drop
    the other -- which is what the original probe's seed set did by accident.
    """
    notch_edges = ci.feature_stations(h['notches'], h['z_lo_m'], h['z_hi_m'])
    body_features = ci.feature_stations(h['body'], h['z_lo_m'], h['z_hi_m'])
    patches = ci._patches(h['z_lo_m'], h['z_hi_m'], body_features)
    if len(patches) != 1:
        raise ci.PreconditionFailed('expected one patch, got %d' % len(patches))
    p_lo_m, p_hi_m = patches[0]
    seed_m = ci._seed(p_lo_m, p_hi_m, True, True)
    union_m = set(seed_m) | {e for e in notch_edges if p_lo_m < e < p_hi_m}
    if force_m is not None:
        union_m.add(float(force_m))
    return (ci._thin_stations(sorted(union_m), ci.station_floor(h['t_m'])),
            sorted(union_m))


def min_wall(h, surf, zs_m):
    """The thinnest wall the fitted surface leaves anywhere on `zs_m`, and where. In meters.

    Uses §5's own measurement -- the fitted section's samples against the exterior polyline -- and
    takes the minimum rather than the worst departure from `t`. A station whose surface will not
    section into one open arc is counted separately and never folded into the minimum, because
    "no section" and "no wall" are different failures.
    """
    face = surf.toShape()
    worst_m, at_m, unsliceable = None, None, 0
    for z_m in zs_m:
        sliced = ci._slice_wires(face, z_m)
        cut = [w for w in sliced if not w.isClosed()]
        if len(cut) != 1:
            unsliceable += 1
            continue
        here, _dense = ci.open_contour(cut[0], h['n_check'])
        # `_Polyline.distances` works in whatever unit its points carry, and `open_contour`'s come
        # from an SI construction, so this is meters.
        low_m = float(h['outer_at'](z_m).distances(here).min())
        if worst_m is None or low_m < worst_m:
            worst_m, at_m = low_m, z_m
    return worst_m, at_m, unsliceable


def run(kind, u, which, out_dir, scan_m):
    started = time.time()
    doc = App.newDocument('wall_vanish')
    h = harness(doc, kind, u)
    force_m = HISTORIC_Z_M if which == 'historic' else None
    kept_m, union_m = stations(h, force_m)
    t_m = h['t_m']

    # `_thin_stations` returns heights, not rows, so the row is located by height here.
    # The `unfloored` arm fits the union itself -- nothing forced, nothing dropped -- which is
    # the pre-IP-FC-144 station set and the one the silent break lives on.
    zs_fit_m = list(union_m) if which == 'unfloored' else list(kept_m)
    if which in ('historic', 'unfloored'):
        i_row = next((i for i, z_m in enumerate(zs_fit_m)
                      if abs(z_m - HISTORIC_Z_M) <= SAME_STATION_M), None)
        if i_row is None:
            raise ci.PreconditionFailed(
                'the historic station is not in this station set (%d stations), so this arm '
                'cannot run as described' % len(zs_fit_m))
    else:
        # The station nearest the historic one that the floor actually keeps, so the two arms
        # perturb the same region of the part and differ only in the crowding around it.
        i_row = min(range(len(zs_fit_m)), key=lambda i: abs(zs_fit_m[i] - HISTORIC_Z_M))

    rows = [(z_m, h['fit_at'](z_m)) for z_m in zs_fit_m]
    neighbors_m = []
    if i_row > 0:
        neighbors_m.append(zs_fit_m[i_row] - zs_fit_m[i_row - 1])
    if i_row < len(zs_fit_m) - 1:
        neighbors_m.append(zs_fit_m[i_row + 1] - zs_fit_m[i_row])
    setup_s = time.time() - started

    scan_m_list = []
    z_m = h['z_lo_m']
    while z_m <= h['z_hi_m']:
        scan_m_list.append(z_m)
        z_m += scan_m

    print('')
    print('%s at U = %g, arm %r: how thin the fitted wall gets, per dose.'
          % (kind, u, which))
    print('  setup %.1f s; t = %.3f mm, floor %.3f mm'
          % (setup_s, si.mm(t_m), si.mm(ci.station_floor(t_m))))
    print('  %d station(s) in the union, %d fitted (%s); perturbing row %d at z = %.7f mm'
          % (len(union_m), len(zs_fit_m),
             'the union itself, unfiltered' if which == 'unfloored' else 'after the floor',
             i_row, si.mm(zs_fit_m[i_row])))
    print('  its neighbor gaps: %s mm'
          % ', '.join('%.7f' % si.mm(g_m) for g_m in neighbors_m))
    print('  scanning %d station(s) at %.1f mm axially'
          % (len(scan_m_list), si.mm(scan_m)))
    print('')
    print('   delta/mm   thinnest wall/mm   at z/mm     unsliceable   s')
    print('   ' + '-' * 62)

    records = []
    for delta_m in DOSES_M:
        at_start = time.time()
        surf = ci._fit(rows if delta_m == 0.0
                       else fr.nudge_rows(rows, i_row, delta_m))
        worst_m, at_m, bad = min_wall(h, surf, scan_m_list)
        took = time.time() - at_start
        flag = ''
        if worst_m is not None and worst_m <= 0.0:
            flag = '   WALL GONE'
        elif worst_m is not None and worst_m < t_m - ci.WALL_TOL_M:
            flag = '   under WALL_TOL'
        print('   %9.4f   %17s   %-10s  %11d   %4.0f%s'
              % (si.mm(delta_m),
                 'none sliced' if worst_m is None else '%.6f' % si.mm(worst_m),
                 '--' if at_m is None else '%.4f' % si.mm(at_m), bad, took, flag))
        records.append({'delta_mm': si.mm(delta_m),
                        'min_wall_mm': None if worst_m is None else si.mm(worst_m),
                        'at_z_mm': None if at_m is None else si.mm(at_m),
                        'unsliceable': bad, 'seconds': took})

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    stem = os.path.join(out_dir, '%s_U%g_%s' % (kind, u, which))
    # **The record stays a millimeter file format**, with every key naming its unit, because the
    # dose series in `doc/implementation/freecad_migration.md` quotes these figures in
    # millimeters and a file whose numbers silently changed meaning would make the two disagree.
    with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
        fh.write(json.dumps({'kind': kind, 'u': float(u), 'arm': which, 't_mm': si.mm(t_m),
                             'station_floor_mm': si.mm(ci.station_floor(t_m)),
                             'i_row': i_row, 'row_z_mm': si.mm(zs_fit_m[i_row]),
                             'neighbor_gaps_mm': [si.mm(g_m) for g_m in neighbors_m],
                             'stations_mm': [si.mm(z_m) for z_m in zs_fit_m],
                             'scan_mm': si.mm(scan_m),
                             'doses': records},
                            indent=1, sort_keys=True, default=float))
    print('')
    print('  wrote %s.json in %.0f s total' % (stem, time.time() - started))
    return records


def main():
    # **The flag names its unit**, which `--scan` did not (IP-FC-163).
    run(_opt('kind', 'tail_shell'), float(_opt('u', '3.0')),
        _opt('row', 'floor'), os.path.normpath(_opt('out-dir', OUT_DIR)),
        si.m(float(_opt('scan-mm', str(si.mm(SCAN_M))))))


if is_entry_point(__name__):
    main()
