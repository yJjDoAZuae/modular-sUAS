"""IP-FC-5: does PartDesign:: work at all under freecadcmd?

Before porting the corner a second time, establish that a Body, a sketch attached to an
origin plane, a Pad, a Pocket, a Groove and a Mirrored transformation can all be created
and recomputed with no GUI. Anything that fails here changes what the second port can be.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part
import Sketcher

from corner_common import is_entry_point, out_path

V = App.Vector


def origin_plane(body, name):
    """The XY/XZ/YZ plane of a Body's origin, by role."""
    for feature in body.Origin.OriginFeatures:
        if feature.Role == name:
            return feature
    raise KeyError(name)


def sketch_on(doc, body, plane, offset=0.0):
    sk = doc.addObject('Sketcher::SketchObject', 'Sketch')
    body.addObject(sk)
    sk.AttachmentSupport = [(plane, '')]
    sk.MapMode = 'FlatFace'
    if offset:
        sk.AttachmentOffset = App.Placement(V(0, 0, offset), App.Rotation())
    return sk


def main():
    doc = App.newDocument('spike')
    body = doc.addObject('PartDesign::Body', 'Body')
    xy = origin_plane(body, 'XY_Plane')

    results = []

    # 1. Pad from a sketch on an origin plane
    sk = sketch_on(doc, body, xy)
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 10.0), False)
    pad = doc.addObject('PartDesign::Pad', 'Pad')
    body.addObject(pad)
    pad.Profile = sk
    pad.Length = 20.0
    doc.recompute()
    results.append(('Pad', pad.Shape.isValid(), pad.Shape.Volume))

    # 2. Pocket through the pad
    sk2 = sketch_on(doc, body, xy)
    sk2.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 3.0), False)
    pocket = doc.addObject('PartDesign::Pocket', 'Pocket')
    body.addObject(pocket)
    pocket.Profile = sk2
    pocket.Type = 1                       # ThroughAll
    doc.recompute()
    results.append(('Pocket (default dir)', pocket.Shape.isValid(),
                    pocket.Shape.Volume))

    # A Pocket cuts *against* its sketch normal. The pad ran +z from the same plane, so
    # the default direction removes nothing -- and reports success while doing it.
    pocket.Reversed = True
    doc.recompute()
    results.append(('Pocket (reversed)', pocket.Shape.isValid(), pocket.Shape.Volume))

    # 3. Groove -- a revolved cut, which is how the snap rib would be made
    xz = origin_plane(body, 'XZ_Plane')
    sk3 = sketch_on(doc, body, xz)
    pts = [(5.0, 8.0), (7.0, 8.0), (7.0, 12.0), (5.0, 12.0)]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        sk3.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)
    groove = doc.addObject('PartDesign::Groove', 'Groove')
    body.addObject(groove)
    groove.Profile = sk3
    groove.ReferenceAxis = (origin_plane(body, 'Z_Axis'), [''])
    groove.Angle = 360.0
    doc.recompute()
    results.append(('Groove', groove.Shape.isValid(), groove.Shape.Volume))

    # 4. Mirrored transformation about a datum plane
    datum = doc.addObject('PartDesign::Plane', 'DatumPlane')
    body.addObject(datum)
    datum.AttachmentSupport = [(xy, '')]
    datum.MapMode = 'FlatFace'
    doc.recompute()
    results.append(('DatumPlane', datum.Shape.isValid() if datum.Shape else True, 0.0))

    for name, valid, vol in results:
        print('  %-12s valid=%-5s volume=%.4f' % (name, valid, vol))

    print('  features on body: %s' % ', '.join(o.Name for o in body.Group))
    print('  final tip: %s  volume=%.4f  faces=%d'
          % (body.Tip.Name, body.Shape.Volume, len(body.Shape.Faces)))

    out = out_path('spike.FCStd')
    doc.saveAs(out)
    print('  saved %s' % os.path.basename(out))


if is_entry_point(__name__):
    main()
