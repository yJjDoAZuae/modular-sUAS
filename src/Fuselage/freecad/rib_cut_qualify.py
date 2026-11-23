"""IP-FC-169: judge a cavity cut with a failure made on purpose, against an answer known in advance.

Implements the first qualification criterion of the algorithm document's section 7.2, as
[OQ-DES-CW42](../../../doc/design/cowl.md) restated it. A cavity is cut by the planar tool with
chosen ribs left out (`--omit`) or grown by `t - delta` instead of `t` (`--thinner`), through
`sever_doses.py --dilate=failed:...`. This judges it against the inner offset of the *full* planar
tool, built from the same notches, and compares each tool solid's verdict with the one the geometry
fixes beforehand:

- a tool solid holding a left-out rib must be flagged;
- a tool solid holding a thinner rib must be flagged exactly when that rib's residue reaches
  `WALL_TOL_M` deep. The residue is `delta * |n_xy|` deep on each face of the full rib that bounds
  the cavity, so the deepest is `delta` times the largest `|n_xy|` among those faces. Which faces
  bound the cavity is read from `--control`, the cavity the full tool cut;
- every other tool solid must be clear.

    freecadcmd rib_cut_qualify.py --pass --cavity=c.brep --pass --control=c0.brep
        --pass --notches=n.brep --pass --t=0.6 --pass --omit=2,7 --pass --out=r.json
    freecadcmd rib_cut_qualify.py ... --pass --thinner=4@0.010249235,6@0.0101 ...

`--t` and the `--thinner` depths are millimeters, like every figure these harnesses take on the
command line, and convert to SI where they are read. The inner offset is built as production builds
it, in a child process with a time limit (`rib_offset_worker`). Measurement only.
"""
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cowl_interior as ci  # noqa: E402
import Part  # noqa: E402
import rib_geometry  # noqa: E402
import rib_offset_worker  # noqa: E402
import si  # noqa: E402
from corner_common import is_entry_point  # noqa: E402

#: How closely a cavity face must share a rib face's plane to count as cut by it: unit normals
#: (reversed, since outward from the cavity is into the rib) and plane offsets, in the kernel's mm.
NORMAL_TOL = 1.0e-7
PLANE_TOL_M = 1.0e-8

#: A rib face bounds the cavity where at least this much of it is a cavity face.
CONTACT_M2 = 1.0e-12

#: The tolerance for a rib part's center lying in a tool solid. Every part is a solid of the tool,
#: so its center is well inside; this only absorbs the kernel's rounding.
INSIDE_TOL_M = 1.0e-9


def contact_h(rib_parts, control):
    """The largest `|n_xy|` among the faces of `rib_parts` that bound the `control` cavity, or `None`
    where none does."""
    planes = []
    for g in control.Faces:
        if g.Surface.__class__.__name__ == 'Plane':
            n, d = rib_geometry._plane(g)
            planes.append((g, n, d))
    best = None
    for part in rib_parts:
        for f in part.Faces:
            nf, df = rib_geometry._plane(f)
            area = sum(g.common(f).Area for g, n, d in planes
                       if (n + nf).Length < NORMAL_TOL and abs(d + df) < si.mm(PLANE_TOL_M))
            if area > CONTACT_M2 * si.MM2_PER_M2:
                h = math.hypot(nf.x, nf.y)
                best = h if best is None else max(best, h)
    return best


def _pairs(text):
    """`4@0.010249235,6@0.0101` -> {4: 1.0249235e-05, 6: 1.01e-05}, the depths converted to SI."""
    out = {}
    for item in filter(None, (text or '').split(',')):
        i, _, d = item.partition('@')
        out[int(i)] = si.m(float(d))
    return out


def qualify(cavity, control, notches, t_m, omit=(), thinner_m=None):
    """The record of one judgment: expected and measured verdicts per tool solid."""
    thinner_m = dict(thinner_m or {})
    ribs = rib_geometry.planar_ribs(notches, t_m)
    parts = [r for _i, r in ribs]
    tool = parts[0] if len(parts) == 1 else parts[0].fuse(parts[1:]).removeSplitter()

    def solid_of(rib):
        c = rib.CenterOfMass
        hits = [k for k, s in enumerate(tool.Solids) if s.isInside(c, si.mm(INSIDE_TOL_M), True)]
        if len(hits) != 1:
            raise RuntimeError('a rib part is in %d tool solids' % len(hits))
        return hits[0]

    expect = {k: False for k in range(len(tool.Solids))}
    why = {}
    for i in sorted(set(omit) | set(thinner_m)):
        mine = [r for j, r in ribs if j == i]
        k = solid_of(mine[0])
        if i in omit:
            expect[k] = True
            why[k] = 'notch %d left out' % i
            continue
        h = contact_h(mine, control)
        depth_m = 0.0 if h is None else thinner_m[i] * h
        reaches = depth_m >= ci.WALL_TOL_M
        expect[k] = expect[k] or reaches
        why[k] = ('notch %d thinner by %.9f mm: deepest residue %.9f mm on a face with '
                  '|n_xy| = %s, so %s' % (i, si.mm(thinner_m[i]), si.mm(depth_m),
                                          'none' if h is None else '%.9f' % h,
                                          'flagged' if reaches else 'clear'))

    at = time.time()
    cores, offset_report = rib_offset_worker.bounded_inner_offset(tool, ci.WALL_TOL_M)
    offset_s = time.time() - at
    verdicts = rib_geometry.judge_cut(cavity, cores)
    rows = []
    for k, distance_m in verdicts:
        flagged = distance_m is not None and distance_m <= rib_geometry.TOUCH_TOL_M
        rows.append({'solid': k, 'expected': 'flagged' if expect[k] else 'clear',
                     'verdict': 'flagged' if flagged else 'clear',
                     'distance_mm': None if distance_m is None else si.mm(distance_m),
                     'why': why.get(k, 'no rib changed')})
    return {'tool_solids': len(tool.Solids), 'tool_faces': len(tool.Faces),
            'rows': rows, 'wrong': sum(r['expected'] != r['verdict'] for r in rows),
            'offset_seconds': offset_s, 'offset_report': offset_report}


def main():
    opt = {}
    for arg in sys.argv[1:]:
        if arg.startswith('--') and '=' in arg:
            name, _, value = arg[2:].partition('=')
            opt[name] = value
    record = qualify(Part.read(opt['cavity']), Part.read(opt['control']),
                     Part.read(opt['notches']), si.m(float(opt['t'])),
                     omit=tuple(int(i) for i in filter(None, opt.get('omit', '').split(','))),
                     thinner_m=_pairs(opt.get('thinner')))
    record.update(cavity=opt['cavity'], omit=opt.get('omit', ''), thinner=opt.get('thinner', ''))
    for r in record['rows']:
        print('solid %d: expected %-7s got %-7s distance %s mm  (%s)%s'
              % (r['solid'], r['expected'], r['verdict'],
                 '-' if r['distance_mm'] is None else '%.7f' % r['distance_mm'], r['why'],
                 '' if r['expected'] == r['verdict'] else '   WRONG'))
    print('rib_cut_qualify: %d tool solids, %d wrong, offset %.0f s'
          % (record['tool_solids'], record['wrong'], record['offset_seconds']))
    Path(opt['out']).write_text(json.dumps(record, indent=1, default=float))
    sys.stdout.flush()


if is_entry_point(__name__):
    main()
