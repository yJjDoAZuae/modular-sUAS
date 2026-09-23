"""IP-FC-5, PartDesign:: half: corner_middle as a Body of sketches and features.

The profile is built the way PartDesign wants it -- one additive or subtractive feature per
primitive, each from its own sketch -- and then the octant has to be mirrored onto the
diagonal. That last step is the whole question. In OpenSCAD the mirror wraps the *entire*
half expression:

    mirror_xy() { half }   ==   half  U  mirror(half)

which is not the same as mirroring each primitive in place, because the diagonal mask that
trims the octant would, mirrored, trim the octant that survives. This script builds the
half with PartDesign features, checks it against the Part:: half, and then measures what
PartDesign::Mirrored actually does with it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part
import Sketcher

from corner_common import Params, half_shape, is_entry_point, out_path, section

V = App.Vector


def origin_feature(body, role):
    for feature in body.Origin.OriginFeatures:
        if feature.Role == role:
            return feature
    raise KeyError(role)


def sketch_at(doc, body, plane, z):
    sk = doc.addObject('Sketcher::SketchObject', 'Sketch')
    body.addObject(sk)
    sk.AttachmentSupport = [(plane, '')]
    sk.MapMode = 'FlatFace'
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    return sk


def add_polygon(sk, points):
    for i in range(len(points)):
        a, b = points[i], points[(i + 1) % len(points)]
        sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)


def add_rect(sk, x0, y0, x1, y1):
    add_polygon(sk, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def pad(doc, body, sk, length):
    f = doc.addObject('PartDesign::Pad', 'Pad')
    body.addObject(f)
    f.Profile = sk
    f.Length = length
    doc.recompute()
    return f


def pocket(doc, body, sk):
    """A through-all cut in both directions -- the section is a prism, so a cut that
    reaches the whole height is what every primitive in the profile wants."""
    f = doc.addObject('PartDesign::Pocket', 'Pocket')
    body.addObject(f)
    f.Profile = sk
    f.Type = 1                       # ThroughAll
    f.Midplane = True                # ... in both directions, not just against the normal
    doc.recompute()
    return f


def build_half(doc, p, z0, h):
    body = doc.addObject('PartDesign::Body', 'Body')
    xy = origin_feature(body, 'XY_Plane')
    far = p.far

    sk = sketch_at(doc, body, xy, z0)
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), p.corner_radius), False)
    pad(doc, body, sk, h)

    # rectangular extension carrying the panel interface outboard
    w = p.panel_overlap + p.panel_offset - p.panel_tolerance
    sk = sketch_at(doc, body, xy, z0)
    add_rect(sk, -w, 0, 0, p.corner_radius)
    pad(doc, body, sk, h)

    # longeron bore
    sk = sketch_at(doc, body, xy, z0 + h / 2.0)
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1),
                               p.longeron_radius + p.longeron_tolerance), False)
    pocket(doc, body, sk)

    # panel slot
    sk = sketch_at(doc, body, xy, z0 + h / 2.0)
    x0 = -2 * p.panel_overlap - p.panel_offset + p.panel_tolerance
    y0 = p.corner_radius - p.panel_thickness - p.panel_tolerance
    add_rect(sk, x0, y0, x0 + 2 * p.panel_overlap,
             y0 + 2 * p.panel_thickness + 2 * p.panel_tolerance)
    pocket(doc, body, sk)

    # bulkhead boundary
    sk = sketch_at(doc, body, xy, z0 + h / 2.0)
    add_polygon(sk, [(p.flat_x, p.corner_radius), (p.flat_x, p.flat_y),
                     (p.flat_offset, 0), (0, p.flat_offset), (p.flat_y, p.flat_x),
                     (0, -far), (-far, -far), (-far, far)])
    pocket(doc, body, sk)

    # diagonal mirror-line mask
    sk = sketch_at(doc, body, xy, z0 + h / 2.0)
    add_polygon(sk, [(-far, -far), (far, far), (far, -far)])
    diagonal = pocket(doc, body, sk)

    # longeron chamfer
    sk = sketch_at(doc, body, xy, z0 + h / 2.0)
    add_polygon(sk, [(0, 0), (-far, 0), (-far, -far), (0, -far)])
    pocket(doc, body, sk)

    return body, diagonal


def main():
    """Found while auditing IP-TEST-10 (doc/implementation/test_coverage.md): every number
    below was printed with a delta but never compared to a tolerance, so this always exited 0
    -- the same silent-pass gap fixed throughout the freecad/ tier. The hardcoded "Part::
    full section = 4041.580837" literal is also replaced with a live call to
    `corner_common.section()`, which computes exactly that (the full profile, mirror_xy() of
    the half) rather than repeating a number nothing here re-derives.
    """
    p = Params()
    z0 = 2 * p.bulkhead_thickness - p.eps
    h = p.unit_length / 2 - 2 * p.bulkhead_thickness + 2 * p.eps

    doc = App.newDocument('pd_middle')
    body, diagonal = build_half(doc, p, z0, h)
    doc.recompute()

    ref_half = half_shape(p, z0, h)
    ref_full = section(p, z0, h)
    got = body.Shape

    print('PARTDESIGN:: corner_middle, the octant before mirroring')
    print('  features        = %d' % len([o for o in body.Group
                                          if o.isDerivedFrom('PartDesign::Feature')]))
    print('  volume          = %.6f' % got.Volume)
    print('  Part:: half     = %.6f' % ref_half.Volume)
    print('  delta           = %+.6f' % (got.Volume - ref_half.Volume))
    print('  valid           = %s  solids=%d  faces=%d'
          % (got.isValid(), len(got.Solids), len(got.Faces)))
    half_ok = (got.isValid() and len(got.Solids) == 1
              and abs(got.Volume - ref_half.Volume) <= 1e-4 * ref_half.Volume)
    print('  result          = %s' % ('PASS' if half_ok else 'FAIL'))

    # Now the mirror, across the diagonal plane whose normal is (1,-1,0) -- the same
    # plane mirror_xy() uses. PartDesign::Mirrored has two modes, and they mean different
    # things here, so try both and measure rather than assume.
    datum = doc.addObject('PartDesign::Plane', 'Diagonal')
    body.addObject(datum)
    datum.MapMode = 'Deactivated'
    datum.Placement = App.Placement(
        V(0, 0, 0), App.Rotation(V(0, 0, 1), V(1, -1, 0)))
    doc.recompute()

    originals = [o for o in body.Group if o.isDerivedFrom('PartDesign::Feature')]

    mirrored = doc.addObject('PartDesign::Mirrored', 'Mirrored')
    body.addObject(mirrored)
    mirrored.Originals = originals
    mirrored.MirrorPlane = (datum, [''])

    print('')
    print('  PartDesign::Mirrored across the (1,-1,0) plane')
    print('    TransformMode options: %s' % mirrored.getEnumerationsOfProperty(
        'TransformMode'))

    matching_modes = []
    for mode in mirrored.getEnumerationsOfProperty('TransformMode'):
        mirrored.TransformMode = mode
        doc.recompute()
        if 'Invalid' in mirrored.State or 'Error' in mirrored.State \
                or mirrored.Shape.isNull():
            print('    %-24s FAILED: %s' % (mode, mirrored.State))
            continue
        m = mirrored.Shape
        matches = (m.isValid() and len(m.Solids) == 1
                  and abs(m.Volume - ref_full.Volume) <= 1e-4 * ref_full.Volume)
        if matches:
            matching_modes.append(mode)
        print('    %-24s volume=%.6f valid=%s solids=%d  %s'
              % (mode, m.Volume, m.isValid(), len(m.Solids),
                 'matches full section' if matches else ''))
    print('    Part:: full section = %.6f' % ref_full.Volume)
    # At least one TransformMode has to reproduce mirror_xy()'s semantics -- that is the
    # question this script exists to answer -- though which one, and whether more than one
    # does, is exactly the measurement, not assumed in advance.
    mirror_ok = len(matching_modes) > 0
    print('  matching TransformMode(s) = %s  %s'
          % (matching_modes or 'none', 'PASS' if mirror_ok else 'FAIL'))

    out = out_path('pd_middle.FCStd')
    doc.saveAs(out)
    print('  saved %s' % os.path.basename(out))

    return 0 if (half_ok and mirror_ok) else 1


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
