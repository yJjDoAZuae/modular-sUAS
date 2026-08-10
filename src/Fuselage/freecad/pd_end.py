"""IP-FC-5, PartDesign:: half: corner_end -- the greeble socket -- as a Body.

The socket is where the two paradigms are expected to part company. Its snap groove is a
full revolution *interrupted* by a wedge, so the cutting tool is itself a boolean:

    difference() { rotate_extrude(profile); rotate([0,0,-45]) linear_extrude(wedge); }

PartDesign::Groove revolves a sketch and nothing else -- it has no way to trim its own tool.
This script measures three things:

  1. the section and the plain cuts, which PartDesign handles natively;
  2. what a full-revolution Groove gives, i.e. how wrong the closest native feature is;
  3. whether PartDesign::Boolean can cut with a Part:: tool, which is the same mechanism
     IP-FC-9 needs to form the bulkhead's greeble from the corner's end section.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part
import Sketcher

from corner_common import Params, is_entry_point, out_path, through_cut
from part_end import nub_profile, revolve, wedge
from pd_middle import add_polygon, add_rect, origin_feature, pad, pocket, sketch_at

V = App.Vector
REF_VOL = 551.8157396


def build_section(doc, body, p, z0, h):
    """The mirrored profile, exactly as pd_middle builds it."""
    xy = origin_feature(body, 'XY_Plane')
    far, zm = p.far, z0 + h / 2.0

    sk = sketch_at(doc, body, xy, z0)
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), p.corner_radius), False)
    pad(doc, body, sk, h)

    w = p.panel_overlap + p.panel_offset - p.panel_tolerance
    sk = sketch_at(doc, body, xy, z0)
    add_rect(sk, -w, 0, 0, p.corner_radius)
    pad(doc, body, sk, h)

    sk = sketch_at(doc, body, xy, zm)
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1),
                               p.longeron_radius + p.longeron_tolerance), False)
    pocket(doc, body, sk)

    sk = sketch_at(doc, body, xy, zm)
    x0 = -2 * p.panel_overlap - p.panel_offset + p.panel_tolerance
    y0 = p.corner_radius - p.panel_thickness - p.panel_tolerance
    add_rect(sk, x0, y0, x0 + 2 * p.panel_overlap,
             y0 + 2 * p.panel_thickness + 2 * p.panel_tolerance)
    pocket(doc, body, sk)

    sk = sketch_at(doc, body, xy, zm)
    add_polygon(sk, [(p.flat_x, p.corner_radius), (p.flat_x, p.flat_y),
                     (p.flat_offset, 0), (0, p.flat_offset), (p.flat_y, p.flat_x),
                     (0, -far), (-far, -far), (-far, far)])
    pocket(doc, body, sk)

    sk = sketch_at(doc, body, xy, zm)
    add_polygon(sk, [(-far, -far), (far, far), (far, -far)])
    pocket(doc, body, sk)

    sk = sketch_at(doc, body, xy, zm)
    add_polygon(sk, [(0, 0), (-far, 0), (-far, -far), (0, -far)])
    pocket(doc, body, sk)

    datum = doc.addObject('PartDesign::Plane', 'Diagonal')
    body.addObject(datum)
    datum.MapMode = 'Deactivated'
    datum.Placement = App.Placement(V(0, 0, 0), App.Rotation(V(0, 0, 1), V(1, -1, 0)))
    doc.recompute()

    # Collect the originals *before* the Mirrored joins the body -- body.addObject puts it
    # in body.Group, and a Mirrored that lists itself is a dependency cycle that survives
    # into the saved file and throws on any forced recompute.
    originals = [o for o in body.Group if o.isDerivedFrom('PartDesign::Feature')]

    mirrored = doc.addObject('PartDesign::Mirrored', 'Mirrored')
    body.addObject(mirrored)
    mirrored.Originals = originals
    mirrored.MirrorPlane = (datum, [''])
    mirrored.TransformMode = 'Whole shape'
    doc.recompute()
    return mirrored


def rotated(points, degrees):
    """Rotate 2D points about the origin, for sketches that are not axis-aligned."""
    import math
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def main():
    p = Params()
    h = p.bulkhead_thickness + p.eps

    doc = App.newDocument('pd_end')
    body = doc.addObject('PartDesign::Body', 'Body')
    build_section(doc, body, p, 0.0, h)
    print('PARTDESIGN:: corner_end')
    print('  section         = %.6f' % body.Shape.Volume)

    xy = origin_feature(body, 'XY_Plane')
    g = p.greeble_radius

    # the through bore
    sk = sketch_at(doc, body, xy, h / 2.0)
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), g), False)
    pocket(doc, body, sk)

    # the mouth, a square on the mirror diagonal
    sk = sketch_at(doc, body, xy, h / 2.0)
    add_polygon(sk, rotated([(-2 * g, -g), (0, -g), (0, g), (-2 * g, g)], 45))
    pocket(doc, body, sk)
    print('  + bore + mouth  = %.6f' % body.Shape.Volume)

    # 2. the closest native feature: a full-revolution Groove, no interruption
    xz = origin_feature(body, 'XZ_Plane')
    sk = sketch_at(doc, body, xz, 0.0)
    # the XZ sketch's local (x, y) are global (x, z)
    add_polygon(sk, nub_profile(p))
    groove = doc.addObject('PartDesign::Groove', 'Groove')
    body.addObject(groove)
    groove.Profile = sk
    groove.ReferenceAxis = (origin_feature(body, 'Z_Axis'), [''])
    groove.Angle = 360.0
    doc.recompute()

    if 'Invalid' in groove.State or 'Error' in groove.State:
        print('  full Groove     FAILED: %s' % groove.State)
        native = None
    else:
        native = body.Shape.Volume
        print('  + full Groove   = %.6f   (reference %.6f, off by %+.6f)'
              % (native, REF_VOL, native - REF_VOL))

    # 3. the interrupted groove, cutting with a Part:: tool through PartDesign::Boolean
    doc.removeObject(groove.Name)
    doc.recompute()

    tool_shape = revolve(nub_profile(p)).cut(wedge(p))
    tool = doc.addObject('Part::Feature', 'GrooveTool')
    tool.Shape = tool_shape
    doc.recompute()

    boolean = doc.addObject('PartDesign::Boolean', 'Boolean')
    body.addObject(boolean)
    boolean.setObjects([tool])
    boolean.Type = 'Cut'
    doc.recompute()

    if 'Invalid' in boolean.State or 'Error' in boolean.State \
            or boolean.Shape.isNull():
        print('  PartDesign::Boolean FAILED: %s' % boolean.State)
    else:
        s = body.Shape
        d = s.Volume - REF_VOL
        print('  + Boolean cut   = %.6f   (reference %.6f, %+.6f  %+.4f%%)'
              % (s.Volume, REF_VOL, d, 100 * d / REF_VOL))
        print('  valid           = %s  solids=%d faces=%d'
              % (s.isValid(), len(s.Solids), len(s.Faces)))

    out = out_path('pd_end.FCStd')
    doc.saveAs(out)
    print('  saved %s' % os.path.basename(out))


if is_entry_point(__name__):
    main()
