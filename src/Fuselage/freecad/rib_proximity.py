"""Is the wall thin *where the ribs are*? Distance from each thin spot to every buttress tool.

**The question this answers.** Measured 2026-10-10, every `tail_shell` wall reads 0.013 to 0.047 mm
thinner than nominal while five of six `nose_cowl_shell` walls meet `WALL_TOL`. The nose cell has no
diagonal buttresses and the tail has four, so the diagonals are the obvious suspect -- and the tail's
thin-spot angular positions rotate monotonically with `z` (141.4 degrees through 160.2 across nine
stations at `U` = 4), which is what the trace of a plate tilted about X would do. `diag_buttress`
rotates its slab by `+/-top_diag_angle` = 30 degrees about X, so that is a real possibility and not
a coincidence worth asserting without measurement.

Two mechanisms are separable here and this tool is built to tell them apart:

1. **The thin spot is at a rib.** Then the rib cut or its dilation is implicated: `dilated_notches`
   builds `dilate(B, t)` as a **union of 48 translates** of each tool around a horizontal circle of
   radius `t`, which rounds every convex edge by `t` and approximates the disc from inside. The
   scallop between adjacent translates is `t * (1 - cos(pi/48))` = 0.0013 mm at `t` = 0.6, an order
   of magnitude under what is observed -- so a simple faceting shortfall is already ruled out
   arithmetically, and what would remain is the behaviour where two dilated envelopes **merge**.
2. **The thin spot is nowhere near a rib.** Then the ribs are not the cause whatever their
   dilation does, and the residual belongs to the smooth surface fit -- which is bounded only by
   `TAU` = 0.05 mm, the same order as the thinning, and which `tau_study.py` shows responds
   proportionally when `TAU` is tightened.

So the measurement is simply: find the thinnest point at each station, and report its distance to
every buttress tool by name, raw and dilated. A thin spot tens of millimetres from any notch
refutes (1) directly. One sitting at a dilated envelope's boundary supports it.

**Named tools, not a compound.** `shell.Notches` carries one object per tool -- `Side1Safe`,
`Top1Safe`, `Diag11Safe` and so on, eleven for the tail -- so the nearest tool can be identified by
kind rather than merely by distance. `dilated_notches` is called on each tool separately for the
same reason; it takes a compound in production, and the per-tool dilation here is the same geometry
tool by tool.

Usage, one `--pass` per argument (see `tau_study.py` for why)::

    freecadcmd rib_proximity.py --pass --kind=tail_shell --pass --u=0.5
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

import check_cowl_interior as cci                                  # noqa: E402
import cowl_interior as ci                                         # noqa: E402
from corner_common import is_entry_point                           # noqa: E402
from tau_study import SPACING, _opt, build_cell                    # noqa: E402

from wall_measure import candidates, locate                        # noqa: E402

#: Beyond this many multiples of `t`, a thin spot is "nowhere near" a rib: the dilated envelope
#: reaches exactly `t` from its tool, so anything past `t` is outside the rib's own influence and
#: anything past a few `t` cannot plausibly be explained by how that envelope is built.
FAR_IN_T = 3.0


def tool_rows(shell, t):
    """Each buttress tool and its dilation, as `(name, kind, raw, dilated)`."""
    rows = []
    for obj in shell.Notches:
        name = obj.Name
        kind = ('diag' if 'Diag' in name else
                'side' if 'Side' in name else
                'top' if 'Top' in name else
                'bottom' if 'Bot' in name else 'other')
        raw = obj.Shape
        dilated = ci.dilated_notches(Part.makeCompound([raw]), t)
        rows.append((name, kind, raw,
                     dilated[0] if isinstance(dilated, (list, tuple)) else dilated))
    return rows


def _distance(shape, point):
    """In-plane-agnostic 3-D distance from a point to a shape, via the kernel."""
    try:
        return float(shape.distToShape(Part.Vertex(App.Vector(*point)))[0])
    except Exception:                                              # noqa: BLE001 kernel refusal
        return float('nan')


def probe(wall, tools, t, stations=cci.STATIONS, spacing=SPACING, out=None):
    """Every station's thin spot, with its distance to each tool raw and dilated."""
    out = out if out is not None else sys.stdout
    lo, hi = ci.z_extent(wall)
    lo, hi = lo + 1.0, hi - 1.0
    zs = [lo + (hi - lo) * i / float(stations - 1) for i in range(stations)]
    rows = []
    for z in zs:
        d = locate.station_detail(wall, z, measure=candidates.corner_excluded_min,
                                  nominal=t, App=App, spacing=spacing)
        if d['worst_thin'] is None:
            out.write('  z %10.4f  %s\n' % (z, d['state']))
            out.flush()
            continue
        pt = (d['x'], d['y'], z)
        per_tool = []
        for name, kind, raw, dil in tools:
            per_tool.append({'tool': name, 'kind': kind,
                             'raw_mm': _distance(raw, pt),
                             'dilated_mm': _distance(dil, pt)})
        nearest = min(per_tool, key=lambda r: r['raw_mm'])
        nearest_dil = min(per_tool, key=lambda r: r['dilated_mm'])
        row = {'z': z, 'thin': d['worst_thin'], 'angle_deg': d['angle_deg'],
               'x': d['x'], 'y': d['y'], 'tools': per_tool,
               'nearest': nearest, 'nearest_dilated': nearest_dil,
               'far_from_any_rib': nearest['raw_mm'] > FAR_IN_T * t}
        rows.append(row)
        out.write('  z %10.4f  thin %8.5f  angle %7.2f   nearest raw %-12s %8.3f mm'
                  '   nearest dilated %-12s %8.3f mm%s\n'
                  % (z, row['thin'], row['angle_deg'], nearest['tool'], nearest['raw_mm'],
                     nearest_dil['tool'], nearest_dil['dilated_mm'],
                     '   FAR' if row['far_from_any_rib'] else ''))
        out.flush()
    return rows


def dilated_overlaps(tools, out=None):
    """Which dilated envelopes merge, and by how much. Only pairs that actually intersect."""
    out = out if out is not None else sys.stdout
    found = []
    for i in range(len(tools)):
        for j in range(i + 1, len(tools)):
            a, b = tools[i], tools[j]
            # **Bounding boxes first.** 11 tools is 55 pairs, and a `common` between two solids
            # each fused from 48 translates is not cheap; a box test is free and rejects most of
            # them. A box *overlap* proves nothing (these boxes are loose -- 6.7), so every
            # survivor is still checked properly.
            if not a[3].BoundBox.intersect(b[3].BoundBox):
                continue
            try:
                common = a[3].common(b[3])
            except Exception:                                      # noqa: BLE001 kernel refusal
                continue
            vol = float(common.Volume) if common.Solids else 0.0
            if vol <= 0.0:
                continue
            smaller = min(float(a[3].Volume), float(b[3].Volume))
            found.append({'a': a[0], 'b': b[0], 'kinds': '%s/%s' % (a[1], b[1]),
                          'common_mm3': vol,
                          'fraction_of_smaller': vol / smaller if smaller else float('nan')})
    for r in sorted(found, key=lambda r: -r['fraction_of_smaller']):
        out.write('  %-12s %-12s %-12s common %12.4f mm3  %6.2f %% of the smaller\n'
                  % (r['a'], r['b'], r['kinds'], r['common_mm3'],
                     100.0 * r['fraction_of_smaller']))
    if not found:
        out.write('  no two dilated envelopes intersect\n')
    out.flush()
    return found


def main():
    kind = _opt('kind', 'tail_shell')
    u = float(_opt('u', '0.5'))
    started = time.time()
    doc, shell = build_cell(kind, u)
    t = float(shell.Inset)
    print('rib_proximity %s U=%s, t = %.4f mm, %d tools  [%.0f s to build]'
          % (kind, u, t, len(shell.Notches), time.time() - started), flush=True)
    tools = tool_rows(shell, t)
    print('dilated envelopes that merge:', flush=True)
    overlaps = dilated_overlaps(tools)
    print('thin spot proximity, %.3f mm spacing:' % SPACING, flush=True)
    rows = probe(shell.Shape, tools, t)
    far = [r for r in rows if r['far_from_any_rib']]
    print('stations whose thin spot is more than %.1f t from any rib: %d of %d'
          % (FAR_IN_T, len(far), len(rows)), flush=True)
    by_kind = {}
    for r in rows:
        by_kind[r['nearest']['kind']] = by_kind.get(r['nearest']['kind'], 0) + 1
    print('nearest-rib kind at each thin spot: %s' % by_kind, flush=True)
    print('RIB_PROXIMITY ' + json.dumps(
        {'kind': kind, 'u': u, 't': t, 'overlaps': overlaps, 'rows': rows}, default=str))
    sys.stdout.flush()
    App.closeDocument(doc.Name)
    return 0


if is_entry_point(__name__):
    sys.exit(main())
