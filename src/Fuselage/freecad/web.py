"""IP-FC-9: bulkhead_web as a Part:: CSG tree.

`bulkhead_web_shape`'s 10-vertex polygon looks like it needs a sketch and does not. Its
vertices are

    (0,0) (0,5.1375) (-40,5.1375) (-40,0.9375) (-16,0.9375) (-18,0.9375)
    (-18,-1.0625) (-16,-1.0625) (-16,-8) (-8,-8)

and every edge is axis-aligned except the closing one, from (-8,-8) to the origin along
y = x. Note (-40,0.9375) -> (-16,0.9375) -> (-18,0.9375) are collinear and the middle one
doubles back, so that pair is a zero-area spur: the boundary is really -40 to -18. So the
profile is three stacked boxes minus the half-plane x > y:

    Box1  x in [-40, 0]   y in [ 0.9375,  5.1375]
    Box2  x in [-18, 0]   y in [-1.0625,  0.9375]
    Box3  x in [-16, 0]   y in [-8,      -1.0625]

**The web's fillet is already a true fillet.** The module subtracts a cylinder of
web_fillet_radius at the re-entrant corner, which is why the profile carries that little
step out to x = -18: the step is the material the cylinder then rounds. This is not the
morphological `fillet_inner` that OQ-DES-B9 concerns -- that one is in
`bulkhead_web_inner_shape_octant`, which the non-interconnect path never calls.

Derived parameters for U=1.0 end_bolt 3/16in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import build_sheet, is_entry_point

REF_VOL = 223.8866978

PARAMS = [
    ('unit_width', '100.0'),
    ('corner_radius', '10.0'),
    ('panel_thickness', '4.7625'),
    ('panel_tolerance', '0.1'),
    ('bulkhead_thickness', '6'),
    ('flange_thickness', '1.2'),
    ('bolt_hole_radius', '2.0'),
    ('bolt_thickness', '3.0'),
    ('bolt_offset', '8.0'),
    ('plate_thickness', '0.8'),
    ('web_fillet_radius', '2.0'),
    ('web_width', '3.0'),
    # IP-FC-132: the interconnect web's `big_r` reaches the panel joint, which the
    # non-interconnect web never has to -- see the docstring below.
    ('panel_offset', '2.5'),
    ('panel_overlap', '4.7625'),

    ('web_y_top', '=corner_radius - panel_thickness - panel_tolerance'),
    ('web_y_mid', '=web_y_top - flange_thickness - web_width'),
    ('web_x_left', '=-(unit_width / 2 - corner_radius)'),
    # the bolt boss outer edge, and the step the fillet cylinder rounds
    ('boss_x', '=-bolt_offset - (bolt_hole_radius + bolt_thickness + web_width)'),
    ('step_x', '=boss_x - web_fillet_radius'),
    ('step_y', '=web_y_mid - web_fillet_radius'),
    ('far', '=unit_width'),

    ('diag_base', '=-far'),
    ('diag_len', '=far * 2'),
    ('diag_wid', '=far * 2 * sqrt(2)'),

    # IP-FC-132: bulkhead_web_shape's is_interconnect branch. `ic_big_r` is the radius of
    # the arc the web blends into near the corner axis -- reaching the panel joint rather
    # than a bolt, since an interconnect has none. `step_y` (`web_y_mid -
    # web_fillet_radius`) is the source's `y_center`, unchanged; `ic_x_center` is the same
    # point's x, solved so the fillet circle at (ic_x_center, step_y) sits exactly
    # `web_fillet_radius` outside a circle of radius `ic_big_r` centred on the corner axis
    # -- Pythagoras given `step_y`, not a second tangency to solve for. `ic_x_end`/`ic_y_end`
    # are that same fillet's tangent point on the big arc, along the ray from the axis
    # through the fillet centre, scaled by `ic_big_r / (ic_big_r + web_fillet_radius)` --
    # except `ic_y_end` is NOT scaled where `step_y` is already non-negative, which is the
    # source's own `max(...)` and is why the two are computed separately rather than both
    # from one scale factor.
    ('ic_big_r', '=panel_offset + panel_overlap + flange_thickness + web_width'),
    ('ic_x_center', '=-sqrt((ic_big_r + web_fillet_radius) ^ 2 - min(step_y, 0) ^ 2)'),
    ('ic_y_end', '=max(step_y * ic_big_r / (ic_big_r + web_fillet_radius), step_y)'),
    ('ic_x_end', '=ic_x_center * ic_big_r / (ic_big_r + web_fillet_radius)'),
    ('ic_y_end_lo', '=min(ic_y_end, 0)'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    return bulkhead_web(doc)


def bulkhead_web(doc):
    """Geometry only, against whatever sheet the document already has."""
    P = 'Params.'
    t = P + 'plate_thickness'

    top = C._box(doc, 'WebTop', '-' + P + 'web_x_left',
                 P + 'web_y_top - ' + P + 'web_y_mid', t,
                 P + 'web_x_left', P + 'web_y_mid', '0')
    mid = C._box(doc, 'WebMid', '-' + P + 'step_x',
                 P + 'web_y_mid - ' + P + 'step_y', t,
                 P + 'step_x', P + 'step_y', '0')
    low = C._box(doc, 'WebLow', '-' + P + 'boss_x',
                 P + 'step_y + ' + P + 'bolt_offset', t,
                 P + 'boss_x', '-' + P + 'bolt_offset', '0')

    node = C._fuse(doc, 'WebA', top, mid)
    node = C._fuse(doc, 'WebB', node, low)

    node = C._cut(doc, 'WebDiag', node,
                  C._box(doc, 'WebDiagBox', P + 'diag_len', P + 'diag_wid',
                         t + ' * 3', P + 'diag_base', P + 'diag_base',
                         '-' + t, angle=-45))

    # the fillet: a cylinder subtracted at the re-entrant corner
    fillet = C._cyl(doc, 'WebFillet', P + 'web_fillet_radius', t + ' * 3', '-' + t)
    fillet.setExpression('Placement.Base.x', P + 'step_x')
    fillet.setExpression('Placement.Base.y', P + 'step_y')
    node = C._cut(doc, 'Web', node, fillet)

    tip = C._owned(doc, 'Part::Refine', 'WebTip')
    tip.Source = node
    doc.recompute()
    return tip


def _common(doc, name, base, tool):
    node = C._owned(doc, 'Part::Common', name)
    node.Base, node.Tool = base, tool
    return node


def bulkhead_web_interconnect(doc):
    """`bulkhead_web_shape`'s `is_interconnect` branch, IP-FC-132.

    The source's `union()` has two children -- a polygon and a quarter-disk -- then the
    fillet circle is cut from the whole, the same "material minus a rounding cylinder"
    pattern `bulkhead_web`'s own `WebFillet` already uses.

    **The polygon needs a real sketch, unlike the rest of this port.** Every other profile
    here is a box clipped by half-planes because its non-axis-aligned edges are cuts at a
    fixed or expression-bound angle. This one is different: the edge from the fillet centre
    `(ic_x_center, step_y)` to its tangent point on the arc `(ic_x_end, ic_y_end)` is a ray
    from the corner axis, but the tangency is what places BOTH ends -- there is no box to
    clip, because the far end is not a corner this port can reach by clipping one. Every
    vertex is pinned by its own `DistanceX`/`DistanceY` instead, following
    `corner_tree._sketch()`'s pattern for exactly this situation (see its `WedgeProfile`).
    **Vertex 7 exists only where `ic_y_end >= 0`.** Where it is negative, the source's own
    `[x_end, min(y_end, 0)]` is `[x_end, y_end]` again -- the same point as vertex 6, and the
    edge between them the zero-area spur `web.py`'s other branch already carries at
    (-40, 0.9375)-(-16, 0.9375)-(-18, 0.9375). OpenSCAD's `polygon()` tolerates a
    zero-LENGTH edge; a sketch does not -- `Part.LineSegment` refuses two coincident points
    outright, at construction, before any constraint that might legally collapse them to the
    same place is even added. So the generator reads which case this parameter set is at,
    the way `bolt_flange_fillet` already does for its own quad-vs-triangle degeneracy, and
    emits a 7-vertex polygon rather than an 8-vertex one with a doomed edge.
    """
    P = 'Params.'
    t = P + 'plate_thickness'
    y_end = float(doc.getObject('Params').get('ic_y_end'))

    pts = [(0.0, 0.0), (0.0, 5.1375), (-40.0, 5.1375), (-40.0, 0.9375),
          (-13.4, 0.9375), (-13.4, -1.0625), (-11.4, -0.9)]
    dims = [
        (0, 'X', '0'), (0, 'Y', '0'),
        (1, 'X', '0'), (1, 'Y', P + 'web_y_top'),
        (2, 'X', P + 'web_x_left'), (2, 'Y', P + 'web_y_top'),
        (3, 'X', P + 'web_x_left'), (3, 'Y', P + 'web_y_mid'),
        (4, 'X', P + 'ic_x_center'), (4, 'Y', P + 'web_y_mid'),
        (5, 'X', P + 'ic_x_center'), (5, 'Y', P + 'step_y'),
        (6, 'X', P + 'ic_x_end'), (6, 'Y', P + 'ic_y_end'),
    ]
    if y_end >= 0.0:
        pts.append((-11.0, 0.0))
        dims.append((7, 'X', P + 'ic_x_end'))
        dims.append((7, 'Y', '0'))

    sk = C._sketch(doc, 'WebProfileIc', pts, horizontals=(), verticals=(), on_x=(),
                  dims=dims, angle=0, z_expr='0')
    poly = C._prism(doc, 'WebPolyIc', sk, t)

    reach = '(' + P + 'ic_big_r + ' + P + 'web_fillet_radius)'
    quad = C._box(doc, 'WebQuadIc', reach, reach, t,
                 '-' + reach, '-' + reach, '0')
    disk = C._cyl(doc, 'WebDiskIc', P + 'ic_big_r', t, '0')
    quarter = _common(doc, 'WebQuarterIc', disk, quad)

    node = C._fuse(doc, 'WebUnionIc', poly, quarter)

    fillet = C._cyl(doc, 'WebFilletIc', P + 'web_fillet_radius', t + ' * 3', '-' + t)
    fillet.setExpression('Placement.Base.x', P + 'ic_x_center')
    fillet.setExpression('Placement.Base.y', P + 'step_y')
    node = C._cut(doc, 'WebIc', node, fillet)

    tip = C._owned(doc, 'Part::Refine', 'WebTipIc')
    tip.Source = node
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('web')
    tip = emit(doc)
    s = tip.Shape
    d = s.Volume - REF_VOL
    bb = s.BoundBox

    print('PART:: CSG tree -- bulkhead_web')
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, faceted)' % REF_VOL)
    print('  delta   = %+.7f  (%+.4f%%)' % (d, 100 * d / REF_VOL))
    print('  bbox    = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
          % (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    print('  expect  = [-40.0000, -8.0000, 0.0000, 0.0000, 5.1375, 0.8000]')
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))


if is_entry_point(__name__):
    main()
