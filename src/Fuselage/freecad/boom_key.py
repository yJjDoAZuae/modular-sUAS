"""IP-FC-12: boom_key_shape as a 2D Part:: CSG tree, with real fillets.

**This is the first part of the port that is built in the plane rather than in space.** The
frame bulkhead and the corner are octant-and-mirror solids assembled from boxes, cylinders and
cones. The boom bulkhead is one flat profile extruded once, and four of its five rounding sites
need `Part::Offset2D`, which operates on faces -- so the whole profile is a 2D tree and a single
`Part::Extrusion` sits at the top of it.

The 2D primitives are all document objects, so the editability constraint holds exactly as it
does in 3D: `Part::Circle` for an arc, `Part::Polygon` for a spine, `Part::Face` to close either
into a face, `Part::Plane` for a rectangle, and the ordinary `Part::Cut`/`Part::Fuse` for the
booleans, which work face-to-face in a shared plane.

OQ-DES-B11 settles the key as the one site here that gets **real fillets** rather than the
morphological chain, because it is a named corner round with a fixed count of four: two convex
at the tab's top, two concave where the tab sides meet the collet. Reading the morphological
form is what makes the direct one obvious --

    fillet_outer(r) { fillet_inner(r) { circle ∪ tab } }

is an opening (which rounds the convex pair) followed by a closing (which fills the concave
pair), and nothing else. `fuselage_boom_bulkhead_geometry.scad` was changed to that
construction first and verified across all 24 distinct swept key geometries; this module is the
port of the changed source, not of the shape it replaced.

Two constructions are worth naming because neither is obvious:

**The cap is a stadium, not a hull.** OpenSCAD rounds the tab's top with `hull()` of two
circles, and FreeCAD has no hull operation. The hull of two equal circles is exactly a
rectangle spanning their centres plus the two circles, so it is written that way -- and the
rectangle's width is `2*(a - r) + 2*r = 2*a`, the tab width, exactly.

**The gusset is a box that needs no clipping of its own.** The junction fillet arc is tangent to
the collet externally and to the tab side, which fixes its centre at `(a + r, yc)`. The gusset
is everything in the notch outside that arc, and the box `[a, a+r] x [ty, yc]` bounds it exactly:
the box's right and top edges lie wholly inside the arc, its bottom edge lies inside the collet
up to the tangent point and inside the arc beyond it, and its remaining corner is the junction
itself. So subtracting the collet and the arc leaves the gusset and nothing else.

Derived parameters for U=1.0 boom offset_single 3 mm -- the same variant ref_boom_bulkhead.scad
is rendered at, and one of the 132 valid swept combinations.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
import plane2d
from corner_common import build_sheet, is_entry_point

V = App.Vector
P = 'Params.'

REF_AREA = 166.8606422        # ref_boom_bulkhead.scad mode 4, OpenSCAD, faceted
EXPECT_BBOX = (-7.2, 17.8, 7.2, 34.2)

PARAMS = [
    ('boom_diameter', '8.0'),
    ('boom_collet_thickness', '3.0'),
    ('boom_tolerance', '0.2'),
    ('boom_key_width', '2.0'),
    ('boom_key_height', '2.0'),
    ('boom_key_radius', '0.5'),
    ('boom_key_angle', '0.0'),
    ('boom_y_position', '0.0'),
    ('boom_z_position', '25.0'),

    # the hole the collet passes through -- the surface that fits the boom
    ('collet_radius', '=boom_diameter / 2 + boom_collet_thickness + boom_tolerance'),
    ('key_a', '=boom_key_width / 2'),
    ('key_y_top', '=collet_radius + boom_key_height'),

    # the concave junction fillet: tangent to the collet externally and to the tab side, so
    # its centre is collet_radius + radius from the origin and radius clear of the side
    ('key_yc', '=sqrt((collet_radius + boom_key_radius) ^ 2 '
               '- (key_a + boom_key_radius) ^ 2)'),
    ('key_ty', '=key_yc * collet_radius / (collet_radius + boom_key_radius)'),

    # the convex cap: two arcs whose centres are one radius in from each tab side
    ('key_cap_half', '=key_a - boom_key_radius'),
    ('key_cap_base', '=key_y_top - 2 * boom_key_radius'),

    # Half-width of the rectangle `_union` complements against. It has to strictly enclose
    # everything being unioned, in the frame the union happens in, or the union silently
    # truncates -- so it is built from every term that can push material outward and then
    # doubled, the same way `mask_reach()` is in shape_modifier_utils.scad.
    ('key_reach', '=2 * (abs(boom_y_position) + abs(boom_z_position) '
                  '+ collet_radius + boom_key_height)'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def union2(doc, name, pieces):
    return plane2d.union(doc, name, pieces, P + 'key_reach')


def junction_fillet(doc, tag, mirrored=False):
    """The gusset at one tab-to-collet junction."""
    sign = '-' if mirrored else ''
    # the box is [a, a+r] going outboard, so mirrored it starts at -(a+r)
    x0 = ('-(' + P + 'key_a + ' + P + 'boom_key_radius)') if mirrored else (P + 'key_a')
    node = C._cut(doc, tag + 'CutCollet',
                  plane2d.rect(doc, tag + 'Box', P + 'boom_key_radius',
                        P + 'key_yc - ' + P + 'key_ty', x0, P + 'key_ty'),
                  plane2d.disc(doc, tag + 'Collet', P + 'collet_radius'))
    return C._cut(doc, tag + 'CutArc', node,
                  plane2d.disc(doc, tag + 'Arc', P + 'boom_key_radius',
                        sign + '(' + P + 'key_a + ' + P + 'boom_key_radius)', P + 'key_yc'))


def key_profile(doc, tag=''):
    """One keyed collet, in the key's own frame with the tab pointing +y.

    Every piece is additive, so they go into one `_union` rather than a fuse chain -- see
    there for why that distinction is not stylistic.

    Nothing here depends on where the boom is or which way the key faces; that is all in the
    placement. So the lower web's second evaluation reuses every row of this and differs only
    in `tag` -- see `key_shape`.
    """
    cap_y = P + 'key_y_top - ' + P + 'boom_key_radius'
    return union2(doc, tag + 'KeyProfile', [
        plane2d.disc(doc, tag + 'KeyCollet', P + 'collet_radius'),
        plane2d.rect(doc, tag + 'KeyTab', P + 'boom_key_width',
              P + 'key_y_top - ' + P + 'boom_key_radius', '-' + P + 'key_a', '0'),
        # the cap: the hull of the two corner arcs, written out as the stadium it is
        plane2d.rect(doc, tag + 'KeyCapRect', '2 * ' + P + 'key_cap_half',
              '2 * ' + P + 'boom_key_radius', '-' + P + 'key_cap_half', P + 'key_cap_base'),
        plane2d.disc(doc, tag + 'KeyCapArcR', P + 'boom_key_radius', P + 'key_cap_half', cap_y),
        plane2d.disc(doc, tag + 'KeyCapArcL', P + 'boom_key_radius',
              '-' + P + 'key_cap_half', cap_y),
        junction_fillet(doc, tag + 'GusR'),
        junction_fillet(doc, tag + 'GusL', mirrored=True),
    ])


def key_shape(doc, tag='', z=P + 'boom_z_position', angle=P + 'boom_key_angle'):
    """`boom_key_shape` -- geometry only, against whatever sheet the document already has.

    The rotation and translation ride on the assembled profile rather than on each primitive,
    so `boom_key_angle` is carried properly rather than only working at the zero every swept
    variant sets today -- which is exactly the kind of thing that hides a defect.

    `tag`, `z` and `angle` are what the lower web needs: the source evaluates the whole web at
    `-boom_z_position` and `180 - boom_key_angle`, and those two are the ONLY inputs that
    change. Every derived row here is independent of both -- `key_reach` takes the absolute
    value, and the rest are collet and tab dimensions -- so the second evaluation reads the
    same sheet rows and needs no second copy of them.
    """
    profile = key_profile(doc, tag)
    placed = C._owned(doc, 'Part::Refine', tag + 'KeyPlaced')
    placed.Source = profile
    placed.Placement = App.Placement(V(0, 0, 0), App.Rotation(V(0, 0, 1), 0))
    placed.setExpression('Placement.Rotation.Angle', angle)
    placed.setExpression('Placement.Base.x', P + 'boom_y_position')
    placed.setExpression('Placement.Base.y', z)

    mirrored = C._owned(doc, 'Part::Mirroring', tag + 'KeyMirror')
    mirrored.Source = placed
    mirrored.Normal = V(1, 0, 0)
    return union2(doc, tag + 'BoomKey', [placed, mirrored])


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    tip = key_shape(doc)
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('boom_key')
    tip = emit(doc)
    s = tip.Shape
    got = plane2d.area(s)
    d = got - REF_AREA
    bb = s.BoundBox

    print('PART:: 2D CSG tree -- boom_key_shape, real fillets')
    print('  area    = %.7f' % got)
    print('  ref     = %.7f  (OpenSCAD, faceted)' % REF_AREA)
    print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * d / REF_AREA))
    print('  bbox    = [%.4f, %.4f] x [%.4f, %.4f]'
          % (bb.XMin, bb.YMin, bb.XMax, bb.YMax))
    print('  expect  = [%.4f, %.4f] x [%.4f, %.4f]' % EXPECT_BBOX)
    print('  valid   = %s  faces=%d wires=%d' % (s.isValid(), len(s.Faces), len(s.Wires)))

    # One face, or Part::Offset2D will offset the fragments separately -- see _union.
    if len(s.Faces) != 1:
        print('  FRAGMENTED -- %d faces where 1 is required; any offset downstream of this '
              'is wrong by hundreds of percent' % len(s.Faces))

    # And clear of the rectangle _union complements against, or the union truncated.
    reach = float(doc.getObject('Params').get('key_reach'))
    margin = min(reach - abs(v) for v in (bb.XMin, bb.XMax, bb.YMin, bb.YMax))
    print('  reach   = %.4f, nearest approach to its edge %.4f  %s'
          % (reach, margin, 'ok' if margin > 1e-6 else 'TRUNCATED'))


if is_entry_point(__name__):
    main()
