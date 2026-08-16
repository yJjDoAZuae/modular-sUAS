"""Where the bolt-flange fillet's degeneracy actually lives: the kernel, not the arithmetic.

Backs the measurements quoted in [OQ-DES-B14](../../../../doc/design/bulkhead.md). Three
things, all on the real tree rather than a replica:

    scan     sweep bbf_dx through zero on the isolated fillet and report the topology
    stages   the same seed built up to the first tiling fuse, stage by stage
    edge     name the surfaces meeting at the sub-micron edge, if there is one

`bbf_dx` is moved by moving `bolt_offset`, which is the only cell it depends on that does not
also move `r_bolt_fillet`. So `r_bolt_fillet` stays put and the only thing changing is
`theta = asin(bbf_dx / r_bolt_fillet)`, the angle between the block's left face and the ray
plane.

`--pass ... broken` restores the pre-IP-FC-58 construction by setting `bbf_bx = bbf_cx`, so
the two can be compared without checking out an old revision. Run:

    freecadcmd src/Fuselage/tools/bbf_analysis/probe_bbf_degeneracy.py \\
        --pass params.json stages broken
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', '..', 'freecad')))

import FreeCAD as App

import bulkhead_full
import bulkhead_section
import fillets
import parameters
from corner_common import is_entry_point, script_args

# far enough either side of zero to show that the trouble is a neighborhood, not a point
DELTAS = [0.0, 1e-6, 1e-4, 1e-3, 0.01, 0.05, 0.1, 0.2, 0.4, 0.8, 1.1, 2.0, 3.0]

STAGES = ['BoltFlangeFillet', 'OuterCornerFillet', 'FlangePositive', 'SectionCut',
          'BulkheadSection', 'TileXy', 'BulkheadFull']

TINY_EDGE = 1e-3
TINY_FACE = 1e-4


def make_broken(cells):
    """The construction as it stood before IP-FC-58: block left edge at the fillet center."""
    cells.set('bbf_bx', '=bbf_cx')


def stats(shape):
    edges = [e.Length for e in shape.Edges]
    areas = [f.Area for f in shape.Faces]
    return dict(vol=shape.Volume, solids=len(shape.Solids), valid=shape.isValid(),
                nf=len(shape.Faces),
                min_edge=min(edges) if edges else 0.0,
                min_face=min(areas) if areas else 0.0,
                tiny_e=sum(1 for e in edges if e < TINY_EDGE),
                tiny_f=sum(1 for a in areas if a < TINY_FACE))


def describe(face):
    s = face.Surface
    kind = type(s).__name__
    if kind == 'Plane':
        n = s.Axis
        return '%-9s area %11.7f  n=(%.4f %.4f %.4f)' % (kind, face.Area, n.x, n.y, n.z)
    return '%-9s area %11.7f' % (kind, face.Area)


def isolated(seed, mode):
    """Just fillets.py, so the fillet's own booleans are measured with nothing else present."""
    doc = App.newDocument('bbfscan')
    fillets.sheet(doc, parameters.seed(seed))
    cells = doc.getObject('Params')
    if mode == 'broken':
        make_broken(cells)
    tip = fillets.bolt_flange_fillet(doc)
    doc.recompute()
    return doc, cells, tip


def assembled(seed, mode):
    """The octant and its first tiling fuse, in one document, on the same sheet."""
    doc = App.newDocument('bbfstage')
    s = parameters.seed(seed)
    rows = bulkhead_section.merged_rows(s) + bulkhead_full.PARAMS
    bulkhead_section.sheet(doc, s, rows)
    cells = doc.getObject('Params')
    if mode == 'broken':
        make_broken(cells)
        doc.recompute()
    octant = bulkhead_section.emit(doc, s, rows=rows)
    octant.setExpression('Placement.Base.x', 'Params.corner_offset')
    octant.setExpression('Placement.Base.y', 'Params.corner_offset')
    tip = doc.addObject('Part::Refine', 'BulkheadFull')
    tip.Source = bulkhead_full.octant_to_full(doc, octant)
    doc.recompute()
    return doc, cells


def cmd_scan(seed, mode):
    doc, cells, tip = isolated(seed, mode)
    r = float(cells.get('r_bolt_fillet'))
    cx = float(cells.get('bbf_cx'))
    print('mode=%s  r_bolt_fillet=%.4f  bbf_cx=%.4f' % (mode, r, cx))
    print('%9s %9s %9s | %10s %5s %3s %11s | %10s %5s %3s %11s'
          % ('bbf_dx', 'theta deg', 'r/bbf_dx', 'ray vol', 'valid', 'nf', 'min edge',
             'fillet vol', 'valid', 'nf', 'min edge'))
    for d in DELTAS:
        cells.set('bolt_offset', repr(-cx + d))
        doc.recompute()
        dx = float(cells.get('bbf_dx'))
        theta = math.degrees(math.asin(min(abs(dx) / r, 1.0)))
        amp = (r / dx) if dx > 1e-12 else float('inf')
        a, b = stats(doc.getObject('BffRay').Shape), stats(tip.Shape)
        print('%9.6f %9.4f %9.1f | %10.4f %5s %3d %11.8f | %10.4f %5s %3d %11.8f'
              % (dx, theta, amp, a['vol'], a['valid'], a['nf'], a['min_edge'],
                 b['vol'], b['valid'], b['nf'], b['min_edge']))


def cmd_stages(seed, mode):
    doc, cells = assembled(seed, mode)
    print('mode=%s  bbf_cx=%s  bbf_bx=%s  bolt_c=%s  bbf_dx=%s'
          % (mode, cells.get('bbf_cx'), cells.get('bbf_bx'), cells.get('bolt_c'),
             cells.get('bbf_dx')))
    for name in STAGES:
        obj = doc.getObject(name)
        if obj is None:
            print('  %-18s (absent)' % name)
            continue
        s = stats(obj.Shape)
        print('  %-18s vol %12.5f  solids %d  valid %s  faces %4d  min_edge %11.8f  '
              'min_face %11.8f  tiny_e %d  tiny_f %d'
              % (name, s['vol'], s['solids'], s['valid'], s['nf'], s['min_edge'],
                 s['min_face'], s['tiny_e'], s['tiny_f']))


def cmd_edge(seed, mode):
    doc, cells = assembled(seed, mode)
    sh = doc.getObject('SectionCut').Shape
    print('mode=%s  bbf_cx %s  bbf_cy %s  relief_r_low %s  plate_thickness %s'
          % (mode, cells.get('bbf_cx'), cells.get('bbf_cy'), cells.get('relief_r_low'),
             cells.get('plate_thickness')))
    found = False
    for i, e in enumerate(sh.Edges):
        if e.Length >= TINY_EDGE:
            continue
        found = True
        pts = [(v.Point.x, v.Point.y, v.Point.z) for v in e.Vertexes]
        print('\nEdge%d  length %.9f  curve %s' % (i + 1, e.Length, type(e.Curve).__name__))
        for p in pts:
            print('   vertex (%.6f, %.6f, %.6f)' % p)
        if len(pts) == 2:
            d = math.dist(pts[0], pts[1])
            print('   endpoint separation %.9f  length/separation %.4f'
                  % (d, e.Length / d if d else float('inf')))
        for j, f in enumerate(sh.Faces):
            if any(e.isSame(fe) for fe in f.Edges):
                print('   on Face%-4d %s' % (j + 1, describe(f)))
    for j, f in enumerate(sh.Faces):
        if f.Area >= TINY_FACE:
            continue
        found = True
        print('\nFace%d  %s' % (j + 1, describe(f)))
        for e in f.Edges:
            print('   bounded by %-10s %.9f' % (type(e.Curve).__name__, e.Length))
    if not found:
        print('\nno edge under %g mm and no face under %g mm2 -- the octant is clean'
              % (TINY_EDGE, TINY_FACE))


COMMANDS = {'scan': cmd_scan, 'stages': cmd_stages, 'edge': cmd_edge}


def main():
    args = script_args()
    if not args:
        print('usage: freecadcmd probe_bbf_degeneracy.py --pass params.json '
              '{scan|stages|edge} [fixed|broken]')
        return 0
    seed = args[0]
    cmd = args[1] if len(args) > 1 else 'stages'
    mode = args[2] if len(args) > 2 else 'fixed'
    if cmd not in COMMANDS:
        print('unknown command %r; expected one of %s' % (cmd, ', '.join(COMMANDS)))
        return 1
    if mode not in ('fixed', 'broken'):
        print('unknown mode %r; expected fixed or broken' % mode)
        return 1
    COMMANDS[cmd](seed, mode)
    return 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
