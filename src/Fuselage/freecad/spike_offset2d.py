"""IP-FC-9: does Part::Offset2D reproduce OpenSCAD's offset(r=) and fillet_inner()?

The bulkhead's web is built with `offset(r = -web_width)` and `fillet_inner(
web_fillet_radius)`, and fillet_inner is itself:

    intersection() { offset(-r) offset(2r) offset(-r) children; children; }

Part::Offset2D is a document object, so if the semantics match, the whole construction ports
as a parametric chain rather than as baked geometry. If they do not match, every shape
downstream of the web is affected, so this is worth settling before any of it is built.

OpenSCAD's offset(r=) uses round joins, which is Part::Offset2D's Join='Arc'.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

from corner_common import is_entry_point

V = App.Vector

PTS = [(0, 0), (40, 0), (40, 20), (25, 20), (25, 10), (10, 10), (10, 30), (0, 30)]
SHRINK, FILLET = 3.0, 2.0

REF_RAW = 750.0000000
REF_OFFSET = 309.8654997
REF_FILLET = 244.7101271


def offset2d(doc, name, source, value, join='Arc'):
    o = doc.addObject('Part::Offset2D', name)
    o.Source = source
    o.Value = value
    o.Join = join
    o.Fill = False
    doc.recompute()
    return o


def area(obj):
    shp = obj.Shape
    if shp.isNull():
        return float('nan')
    return sum(f.Area for f in shp.Faces) if shp.Faces else shp.Area


def main():
    doc = App.newDocument('offset2d')

    pts = [V(x, y, 0) for x, y in PTS]
    pts.append(pts[0])
    base = doc.addObject('Part::Feature', 'Base')
    base.Shape = Part.Face(Part.makePolygon(pts))
    doc.recompute()

    print('Part::Offset2D against OpenSCAD')
    print('  %-26s %13s %13s %11s' % ('', 'OpenSCAD', 'FreeCAD', 'delta'))
    print('  %-26s %13.6f %13.6f %+11.6f'
          % ('raw', REF_RAW, area(base), area(base) - REF_RAW))

    shrunk = offset2d(doc, 'Shrink', base, -SHRINK)
    print('  %-26s %13.6f %13.6f %+11.6f'
          % ('offset(r=-3)', REF_OFFSET, area(shrunk), area(shrunk) - REF_OFFSET))

    # fillet_inner: offset(-r) offset(2r) offset(-r), intersected with the input
    REF_A, REF_B, REF_C = 60.7347605, 453.8208930, 244.7118342

    a = offset2d(doc, 'FilletA', shrunk, -FILLET)
    print('  %-26s %13.6f %13.6f %+11.6f  faces=%d wires=%d'
          % ('  then offset(-2)', REF_A, area(a), area(a) - REF_A,
             len(a.Shape.Faces), len(a.Shape.Wires)))

    # The dilation is where the two diverge. The shape after the erosion is in several
    # disjoint pieces, so try every Join and Fill combination rather than assume.
    print('')
    print('  the +4 dilation, OpenSCAD = %.6f' % REF_B)
    best = None
    for join in ('Arc', 'Tangent', 'Intersection'):
        for fill in (False, True):
            trial = doc.addObject('Part::Offset2D', 'Trial')
            trial.Source = a
            trial.Value = 2 * FILLET
            trial.Join = join
            trial.Fill = fill
            doc.recompute()
            got = area(trial)
            print('    Join=%-13s Fill=%-5s -> %13.6f  %+11.6f  faces=%d'
                  % (join, fill, got, got - REF_B, len(trial.Shape.Faces)))
            if best is None or abs(got - REF_B) < abs(best[1] - REF_B):
                best = (('%s/%s' % (join, fill)), got)
            doc.removeObject(trial.Name)
    doc.recompute()
    print('    closest: %s at %.6f' % best)

    # Is it a genuine geometric difference or an artifact of summing face areas? The
    # OpenSCAD dilation spans [1, 39] x [1, 19]; the erosion spanned [5, 35] x [5, 15],
    # so a correct +4 grows the bounding box by exactly 4 on every side.
    b = offset2d(doc, 'FilletB', a, 2 * FILLET)
    bb = b.Shape.BoundBox
    print('')
    print('  erosion  bbox = [%.4f, %.4f] x [%.4f, %.4f]  (OpenSCAD [5,35] x [5,15])'
          % (a.Shape.BoundBox.XMin, a.Shape.BoundBox.XMax,
             a.Shape.BoundBox.YMin, a.Shape.BoundBox.YMax))
    print('  dilation bbox = [%.4f, %.4f] x [%.4f, %.4f]  (OpenSCAD [1,39] x [1,19])'
          % (bb.XMin, bb.XMax, bb.YMin, bb.YMax))
    print('  individual face areas = %s'
          % ', '.join('%.4f' % f.Area for f in b.Shape.Faces))
    print('  islands overlap after dilation: %s'
          % (len(b.Shape.Faces) > 1 and
             b.Shape.Faces[0].common(b.Shape.Faces[1]).Area > 1e-9))

    # The workaround: offset each island in isolation, then fuse. If Offset2D is clipping
    # faces against each other, doing them separately should recover the union.
    print('')
    parts = []
    for i, face in enumerate(a.Shape.Faces):
        piece = doc.addObject('Part::Feature', 'Island%d' % i)
        piece.Shape = face
        doc.recompute()
        parts.append(offset2d(doc, 'IslandOff%d' % i, piece, 2 * FILLET))
    fused = doc.addObject('Part::MultiFuse', 'IslandsFused')
    fused.Shapes = parts
    doc.recompute()
    got = area(fused)
    print('  each island offset separately, then fused:')
    print('    areas %s -> fused %.6f  (OpenSCAD %.6f, %+.6f)'
          % (', '.join('%.4f' % area(p) for p in parts), got, REF_B, got - REF_B))

    # and the whole fillet_inner through that route
    c = offset2d(doc, 'FilletC', fused, -FILLET)
    common = doc.addObject('Part::MultiCommon', 'FilletInner')
    common.Shapes = [c, shrunk]
    doc.recompute()
    print('  fillet_inner via that route = %.6f  (OpenSCAD %.6f, %+.6f)'
          % (area(common), REF_FILLET, area(common) - REF_FILLET))


if is_entry_point(__name__):
    main()
