"""IP-FC-9: the bulkhead's five true fillets and chamfers.

outer_corner_fillet, bulkhead_flange_chamfer, greeble_to_web_fillet,
bulkhead_bolt_flange_fillet and web_to_bolt_fillet.

All five are true fillets or chamfers already -- a block of material minus a stepped stack
of a cylinder, a cone and a cylinder, where the step *is* the chamfer. None of them is the
morphological `fillet_inner` of OQ-DES-B9, which the frame bulkhead never reaches.

The last two extrude a five-vertex polygon rather than an axis-aligned block, but the fifth
vertex carries no area: the source builds it as the fillet centre pushed one radius along
the ray from the bolt centre, so bolt centre, fillet centre and end point are collinear by
construction and the closing edge doubles back on the edge that reached it. The region is
therefore the quadrilateral of the first four vertices, at any parameters -- this is a
property of how the point is defined, not an artifact of one parameter set. Modelling the
quad rather than the pentagon also sidesteps the case seen here at U = 1.0, where
`x_corner_fillet_start` clamps to the bolt centre and two vertices coincide; a sketch would
need a zero-length edge, whereas the half-plane decomposition just degenerates to the
triangle on its own.

Each quad is convex, so it is a box clipped by the half-planes of its non-axis-aligned
edges. The edge from the bolt centre to the fillet centre lies at no fixed angle, so its
clipping box takes its rotation from an expression, `atan2(dy; dx)`, bound to
`Placement.Rotation.Angle` -- the first node in the port whose orientation is parametric
rather than a literal.

`bulkhead_flange_chamfer` is the first piece here whose prism is not axis-aligned. Rather
than solve its cutting plane in world coordinates, the prism is built in the frame the
source draws it in and the composed rotation is applied to the result -- the same approach
`corner_tree._relief()` uses. Its pentagon
`[[0,0],[1.8,0],[1.8,-1.2],[0.8,-2.2],[0,-2.2]]` is a box minus the half-plane
`x - y > plate_thickness + flange_chamfer + flange_thickness`.

Derived parameters for U=1.0 end_bolt 3/16in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import build_sheet, is_entry_point

V = App.Vector

REFS = {'OuterCornerFillet': 8.3462246,
        'FlangeChamfer': 151.5351660,
        'GreebleToWebFillet': 3.1435948,
        'BoltFlangeFillet': 38.1582400,
        'WebToBoltFillet': 89.9539546}

PARAMS = [
    ('unit_width', '100.0'),
    ('corner_radius', '10.0'),
    ('panel_thickness', '4.7625'),
    ('panel_offset', '2.5'),
    ('panel_overlap', '4.7625'),
    ('panel_tolerance', '0.1'),
    ('bulkhead_thickness', '6'),
    ('bolt_hole_radius', '2.0'),
    ('bolt_thickness', '3.0'),
    ('bolt_offset', '8.0'),
    ('plate_thickness', '0.8'),
    ('flange_fillet_radius', '2.0'),
    ('flange_thickness', '1.2'),
    ('flange_chamfer', '1.0'),
    ('eps', '0.01'),

    # the flange's inner face, and the fillet centre one radius in from its corner
    ('flange_inner_x', '=-panel_tolerance - panel_offset - panel_overlap - flange_thickness'),
    ('flange_y', '=corner_radius - panel_thickness - panel_tolerance - flange_thickness'),
    ('ocf_cx', '=flange_inner_x - flange_fillet_radius'),
    ('ocf_cy', '=flange_y - flange_fillet_radius'),

    # The stepped relief stack, shared by both fillets. `relief_h_top`'s eps is a cut
    # overshoot and it earns its place on TOPOLOGY rather than volume: forcing it flush
    # leaves the part's volume unchanged to the last digit but adds 4 faces, the cut then
    # ending exactly on the face it should pass through and leaving a coincident boundary
    # behind (IP-FC-55). Measured, not assumed -- and the reason a face count is checked
    # alongside a volume, since a volume alone calls this one inert.
    ('relief_r_low', '=flange_fillet_radius - flange_chamfer'),
    ('relief_h_top', '=bulkhead_thickness - flange_chamfer - plate_thickness + eps'),
    ('relief_z_mid', '=plate_thickness'),
    ('relief_z_top', '=plate_thickness + flange_chamfer'),

    # greeble_to_web_fillet: the centre sits one radius out from whichever of the flange
    # face or the bolt centre is further in, and the quad closes on the 45 degree radial
    ('gtw_start', '=max(flange_inner_x; -bolt_offset)'),
    ('gtw_cx', '=gtw_start - flange_fillet_radius'),
    ('gtw_ex', '=gtw_cx + flange_fillet_radius / sqrt(2)'),
    ('gtw_ey', '=gtw_ex + sqrt(2) / 2 * flange_thickness'),
    ('gtw_cy', '=gtw_ey + flange_fillet_radius / sqrt(2)'),

    ('far', '=unit_width'),
    # half-plane x + y < (cx + cy), as a box rotated +45
    ('gtw_dx', '=(gtw_cx + gtw_cy) / 2 + far * (1 - sqrt(2))'),
    ('gtw_dy', '=(gtw_cx + gtw_cy) / 2 - far * (1 + sqrt(2))'),
    ('diag_len', '=far * 2'),
    ('diag_wid', '=far * 2 * sqrt(2)'),

    # bulkhead_flange_chamfer, in the frame the source draws it in
    ('chm_x', '=-(panel_offset + panel_overlap + panel_tolerance)'),
    ('chm_top', '=plate_thickness + flange_chamfer'),
    ('chm_deep', '=flange_thickness + flange_chamfer'),
    ('chm_cut', '=chm_top + flange_thickness'),
    ('chm_len_a', '=unit_width / 2 - corner_radius + chm_x'),
    ('chm_len_b', '=corner_radius + bolt_offset - panel_thickness - panel_tolerance'),
    ('chm_y_a', '=corner_radius - panel_thickness - panel_tolerance'),
    # half-plane x - y > chm_cut, as a box rotated -45
    ('chm_dx', '=(chm_cut - far * 2) / 2'),
    ('chm_dy', '=(-chm_cut - far * 2) / 2'),

    # Both bolt fillets sit at distance flange_fillet_radius from the ring of material
    # around the bolt hole, so their centres lie on this radius from the bolt centre.
    ('bolt_c', '=-bolt_offset'),
    ('r_bolt_fillet', '=flange_fillet_radius + bolt_hole_radius + bolt_thickness'),

    # bulkhead_bolt_flange_fillet: centre one radius outboard of the flange face, at the
    # height where that vertical line meets the bolt ring. The discriminant clips at 0 for
    # a flange too far out to reach the ring at all.
    ('bbf_sx', '=max(flange_inner_x; bolt_c)'),
    ('bbf_cx', '=flange_inner_x - flange_fillet_radius'),
    ('bbf_dx', '=bbf_cx - bolt_c'),
    ('bbf_cy', '=sqrt(max(r_bolt_fillet ^ 2 - bbf_dx ^ 2; 0)) + bolt_c'),
    ('bbf_dy', '=bbf_cy - bolt_c'),
    ('bbf_r', '=sqrt(bbf_dx ^ 2 + bbf_dy ^ 2)'),
    # the bolt-centre-to-fillet-centre edge, as a half-plane box on its far side
    ('bbf_ang', '=atan2(bbf_dy; bbf_dx)'),
    ('bbf_hx', '=bolt_c - far * bbf_dx / bbf_r'),
    ('bbf_hy', '=bolt_c - far * bbf_dy / bbf_r'),

    # web_to_bolt_fillet: the greeble flange wall runs at 45 degrees, half a flange
    # thickness either side of the diagonal, and the fillet centre is one radius off it.
    ('wtb_a', '=flange_fillet_radius + flange_thickness / 2'),
    ('wtb_tan', '=sqrt(max(r_bolt_fillet ^ 2 - wtb_a ^ 2; 0))'),
    ('wtb_cx', '=bolt_c + (wtb_tan - wtb_a) / sqrt(2)'),
    ('wtb_cy', '=bolt_c + (wtb_tan + wtb_a) / sqrt(2)'),
    ('wtb_sx', '=bolt_c + (wtb_tan - flange_thickness / 2) / sqrt(2)'),
    ('wtb_dx', '=wtb_cx - bolt_c'),
    ('wtb_dy', '=wtb_cy - bolt_c'),
    ('wtb_r', '=sqrt(wtb_dx ^ 2 + wtb_dy ^ 2)'),
    ('wtb_ang', '=atan2(wtb_dy; wtb_dx)'),
    ('wtb_hx', '=bolt_c - far * wtb_dx / wtb_r'),
    ('wtb_hy', '=bolt_c - far * wtb_dy / wtb_r'),
    # half-plane x + y > wtb_sum, as a box rotated +45 with its near edge on the line
    ('wtb_sum', '=wtb_cx + wtb_cy'),
    ('wtb_45x', '=wtb_sum / 2 + far'),
    ('wtb_45y', '=wtb_sum / 2 - far'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def _relief_stack(doc, tag, node, cx, cy):
    """The cylinder / cone / cylinder the chamfer is cut with, at (cx, cy)."""
    P = 'Params.'

    def at(obj):
        obj.setExpression('Placement.Base.x', cx)
        obj.setExpression('Placement.Base.y', cy)
        return obj

    node = C._cut(doc, tag + 'CutLow', node,
                  at(C._cyl(doc, tag + 'ReliefLow', P + 'relief_r_low',
                            P + 'plate_thickness', '0')))
    node = C._cut(doc, tag + 'CutMid', node,
                  at(C._cone(doc, tag + 'ReliefMid', P + 'relief_r_low',
                             P + 'flange_fillet_radius', P + 'flange_chamfer',
                             P + 'relief_z_mid')))
    return C._cut(doc, tag + 'CutTop', node,
                  at(C._cyl(doc, tag + 'ReliefTop', P + 'flange_fillet_radius',
                            P + 'relief_h_top', P + 'relief_z_top')))


def outer_corner_fillet(doc):
    P = 'Params.'
    block = C._box(doc, 'OcfBlock', P + 'flange_fillet_radius',
                   P + 'flange_fillet_radius', P + 'bulkhead_thickness',
                   P + 'ocf_cx', P + 'ocf_cy', '0')
    node = _relief_stack(doc, 'Ocf', block, P + 'ocf_cx', P + 'ocf_cy')
    tip = C._owned(doc, 'Part::Refine', 'OuterCornerFillet')
    tip.Source = node
    return tip


def greeble_to_web_fillet(doc):
    P = 'Params.'
    block = C._box(doc, 'GtwBlock', P + 'gtw_start - ' + P + 'gtw_cx',
                   P + 'gtw_cy - ' + P + 'gtw_ey', P + 'bulkhead_thickness',
                   P + 'gtw_cx', P + 'gtw_ey', '0')
    node = C._cut(doc, 'GtwDiag', block,
                  C._box(doc, 'GtwDiagBox', P + 'diag_len', P + 'diag_wid',
                         P + 'bulkhead_thickness * 3', P + 'gtw_dx', P + 'gtw_dy',
                         '-' + P + 'bulkhead_thickness', angle=45))
    node = _relief_stack(doc, 'Gtw', node, P + 'gtw_cx', P + 'gtw_cy')
    tip = C._owned(doc, 'Part::Refine', 'GreebleToWebFillet')
    tip.Source = node
    return tip


def _chamfer_prism(doc, tag, length_expr):
    """The pentagon prism, built in the source's own frame: local x is the eventual world
    z, local y runs into the flange, and the extrusion runs along local +z."""
    P = 'Params.'
    box = C._box(doc, tag + 'Box', P + 'chm_top', P + 'chm_deep', length_expr,
                 '0', '-' + P + 'chm_deep', '0')
    return C._cut(doc, tag + 'Cut', box,
                  C._box(doc, tag + 'Diag', P + 'diag_len', P + 'diag_wid',
                         length_expr + ' * 3', P + 'chm_dx', P + 'chm_dy',
                         '-' + length_expr, angle=-45))


def flange_chamfer(doc):
    P = 'Params.'
    # (a) along the flange: rotate -90 about y, then translate
    a = _chamfer_prism(doc, 'ChmA', P + 'chm_len_a')
    a.Placement = App.Placement(V(0, 0, 0), App.Rotation(V(0, 1, 0), -90))
    a.setExpression('Placement.Base.x', P + 'chm_x')
    a.setExpression('Placement.Base.y', P + 'chm_y_a')

    # (b) down the side: rotate -90 about y, then -90 about z, then translate
    b = _chamfer_prism(doc, 'ChmB', P + 'chm_len_b')
    b.Placement = App.Placement(
        V(0, 0, 0), App.Rotation(V(0, 0, 1), -90).multiply(
            App.Rotation(V(0, 1, 0), -90)))
    b.setExpression('Placement.Base.x', P + 'chm_x')
    b.setExpression('Placement.Base.y', '-' + P + 'bolt_offset')

    node = C._fuse(doc, 'ChmFuse', a, b)
    tip = C._owned(doc, 'Part::Refine', 'FlangeChamfer')
    tip.Source = node
    return tip


def _ray_halfplane(doc, name, angle_expr, x, y):
    """The half-plane on the far side of the bolt-centre-to-fillet-centre edge. Its near
    edge lies along that ray and it extends to the side the quad is not on; the rotation
    comes from the sheet because the ray's angle moves with the parameters."""
    P = 'Params.'
    box = C._box(doc, name, P + 'diag_len', P + 'diag_wid', P + 'bulkhead_thickness * 3',
                 x, y, '-' + P + 'bulkhead_thickness', angle=90)
    box.setExpression('Placement.Rotation.Angle', angle_expr)
    return box


def bolt_flange_fillet(doc):
    """Quad (cx, cy) (sx, cy) (sx, -bolt) (-bolt, -bolt): the top edge is horizontal here
    because the start and centre share a y, so only the ray edge needs clipping."""
    P = 'Params.'
    block = C._box(doc, 'BffBlock', P + 'bbf_sx - ' + P + 'bbf_cx', P + 'bbf_dy',
                   P + 'bulkhead_thickness', P + 'bbf_cx', P + 'bolt_c', '0')
    node = C._cut(doc, 'BffRay', block,
                  _ray_halfplane(doc, 'BffRayBox', P + 'bbf_ang', P + 'bbf_hx',
                                 P + 'bbf_hy'))
    node = _relief_stack(doc, 'Bff', node, P + 'bbf_cx', P + 'bbf_cy')
    tip = C._owned(doc, 'Part::Refine', 'BoltFlangeFillet')
    tip.Source = node
    return tip


def web_to_bolt_fillet(doc):
    """Quad (cx, cy) (sx, sy) (sx, -bolt) (-bolt, -bolt). Two clips: the 45 degree greeble
    flange wall through the centre, and the ray edge."""
    P = 'Params.'
    block = C._box(doc, 'WtbBlock', P + 'wtb_sx - ' + P + 'bolt_c', P + 'wtb_dy',
                   P + 'bulkhead_thickness', P + 'bolt_c', P + 'bolt_c', '0')
    node = C._cut(doc, 'WtbWall', block,
                  C._box(doc, 'WtbWallBox', P + 'diag_len', P + 'diag_wid',
                         P + 'bulkhead_thickness * 3', P + 'wtb_45x', P + 'wtb_45y',
                         '-' + P + 'bulkhead_thickness', angle=45))
    node = C._cut(doc, 'WtbRay', node,
                  _ray_halfplane(doc, 'WtbRayBox', P + 'wtb_ang', P + 'wtb_hx',
                                 P + 'wtb_hy'))
    node = _relief_stack(doc, 'Wtb', node, P + 'wtb_cx', P + 'wtb_cy')
    tip = C._owned(doc, 'Part::Refine', 'WebToBoltFillet')
    tip.Source = node
    return tip


def emit(doc):
    C._SEEN.clear()
    sheet(doc)
    tips = [outer_corner_fillet(doc), flange_chamfer(doc), greeble_to_web_fillet(doc),
            bolt_flange_fillet(doc), web_to_bolt_fillet(doc)]
    doc.recompute()
    return tips


def main():
    doc = App.newDocument('fillets')
    tips = emit(doc)

    print('PART:: CSG trees -- bulkhead fillets and chamfer')
    print('  %-20s %14s %14s %12s %9s  %s'
          % ('module', 'tree', 'OpenSCAD', 'delta', 'rel', 'checks'))
    for tip in tips:
        ref = REFS[tip.Name]
        s = tip.Shape
        d = s.Volume - ref
        checks = []
        if not s.isValid():
            checks.append('INVALID')
        if len(s.Solids) != 1:
            checks.append('solids=%d' % len(s.Solids))
        if abs(d) / ref > 1e-3:
            checks.append('VOLUME')
        print('  %-20s %14.6f %14.6f %+12.6f %+8.4f%%  %s'
              % (tip.Name, s.Volume, ref, d, 100 * d / ref,
                 ' '.join(checks) if checks else 'ok'))
        bb = s.BoundBox
        print('  %-20s bbox [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
              % ('', bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))


if is_entry_point(__name__):
    main()
