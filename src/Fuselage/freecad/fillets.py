"""IP-FC-9: outer_corner_fillet, bulkhead_flange_chamfer and greeble_to_web_fillet.

All three are true fillets or chamfers already -- a block of material minus a stepped stack
of a cylinder, a cone and a cylinder, where the step *is* the chamfer. None of them is the
morphological `fillet_inner` of OQ-DES-B9, which the frame bulkhead never reaches.

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
from corner_common import is_entry_point

V = App.Vector

REFS = {'OuterCornerFillet': 8.3462246,
        'FlangeChamfer': 151.5351660,
        'GreebleToWebFillet': 3.1435948}

PARAMS = [
    ('unit_width', '100.0'),
    ('corner_radius', '10.0'),
    ('panel_thickness', '4.7625'),
    ('panel_offset', '2.5'),
    ('panel_overlap', '4.7625'),
    ('panel_tolerance', '0.1'),
    ('bulkhead_thickness', '6'),
    ('bolt_offset', '8.0'),
    ('plate_thickness', '0.8'),
    ('flange_fillet_radius', '2.0'),
    ('flange_thickness', '1.2'),
    ('flange_chamfer', '1.0'),
    ('eps', '0.01'),

    # the flange's inner face, and the fillet centre one radius in from its corner
    ('flange_x', '=-panel_tolerance - panel_offset - panel_overlap - flange_thickness'),
    ('flange_y', '=corner_radius - panel_thickness - panel_tolerance - flange_thickness'),
    ('ocf_cx', '=flange_x - flange_fillet_radius'),
    ('ocf_cy', '=flange_y - flange_fillet_radius'),

    # the stepped relief stack, shared by both fillets
    ('relief_r_low', '=flange_fillet_radius - flange_chamfer'),
    ('relief_h_top', '=bulkhead_thickness - flange_chamfer - plate_thickness + eps'),
    ('relief_z_mid', '=plate_thickness'),
    ('relief_z_top', '=plate_thickness + flange_chamfer'),

    # greeble_to_web_fillet: the centre sits one radius out from whichever of the flange
    # face or the bolt centre is further in, and the quad closes on the 45 degree radial
    ('gtw_start', '=max(flange_x, -bolt_offset)'),
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
]


def sheet(doc):
    fresh = doc.getObject('Params') is None
    sh = doc.getObject('Params') or doc.addObject('Spreadsheet::Sheet', 'Params')
    if fresh:
        for row, (alias, value) in enumerate(PARAMS, start=1):
            sh.set('A%d' % row, alias)
            sh.setAlias('B%d' % row, alias)
            sh.set('B%d' % row, value)
        doc.recompute()
    return sh


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


def emit(doc):
    C._SEEN.clear()
    sheet(doc)
    tips = [outer_corner_fillet(doc), flange_chamfer(doc), greeble_to_web_fillet(doc)]
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
