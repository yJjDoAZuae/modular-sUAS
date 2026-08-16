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

**`bulkhead_bolt_flange_fillet`'s center is solved, not computed** (OQ-DES-B14, 2026-08-16).
It used to be two spreadsheet rows: `bbf_cx` a subtraction, `bbf_cy` a square root under
`max(...; 0)`. What those two describe is a circle of radius `flange_fillet_radius` touching
the flange's inner face and the bolt boss at once, and that is now *stated* -- `BffTangency`
is a fully constrained construction sketch carrying two `Tangent` constraints, and the
geometry reads the solved center back from its reference dimensions. See
`_tangency_sketch()` for why the sketch holds only the center and not the profile, and why
the sheet is not allowed to read it back. The change is representation only: every stage of
the assembled bulkhead is bit-identical to the arithmetic it replaced.

`bulkhead_flange_chamfer` is the first piece here whose prism is not axis-aligned. Rather
than solve its cutting plane in world coordinates, the prism is built in the frame the
source draws it in and the composed rotation is applied to the result -- the same approach
`corner_tree._relief()` uses. Its pentagon
`[[0,0],[1.8,0],[1.8,-1.2],[0.8,-2.2],[0,-2.2]]` is a box minus the half-plane
`x - y > plate_thickness + flange_chamfer + flange_thickness`.

Derived parameters for U=1.0 end_bolt 3/16in.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part
import Sketcher as S

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
    # identical to simple_positives' row, so the merge keeps one of them (IP-FC-41)
    ('bolt_boss_r', '=bolt_hole_radius + bolt_thickness'),

    # bulkhead_bolt_flange_fillet's outboard extent. Its CENTRE is not here any more: it is
    # solved by `BffTangency`, the sketch built in `_tangency_sketch()` below, and read back
    # from that sketch's reference dimensions. See OQ-DES-B14.
    ('bbf_sx', '=max(flange_inner_x; bolt_c)'),

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
    z, local y runs into the flange, and the extrusion runs along local +z.

    **This shape is a workaround, not a design (OQ-ARCH-13).** The feature is strain relief
    along the interior corner between the flange and the web -- it follows that corner around
    the full interior perimeter of the flange and on around the bolt or anchor, and its size
    is a structural quantity rather than a modeling convenience. What a CAD package would say
    is "chamfer that edge by `flange_chamfer`". OpenSCAD cannot designate an edge and chamfer
    it, so the source had to build the material explicitly, in as many pieces as the corner
    has runs, and this port transcribed that faithfully while OpenSCAD was the authority.

    So do not read the two prisms, the nine `chm_*` rows or the rotated frame as intent to be
    preserved: what is intended is the 45 degrees, the size, and that it follows the corner.
    Replacing it with a real chamfer feature is IP-FC-78, gated on `PartDesign` (IP-FC-75)
    because it needs to name an edge of a boolean result and those names are not yet stable.
    Recorded because the first draft of OQ-ARCH-13 reasoned from this construction as though
    it had been chosen, and recommended leaving it alone permanently on that basis.
    """
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


# The names the rest of the module reads the solved center back through. `Constraints.<name>`
# resolves a *reference* (non-driving) dimension, whose value the solver writes.
#
# `/ 1mm` is not decoration. A sketch constraint is a Quantity carrying a length unit; every
# row of this sheet is a bare number, because that is what the OpenSCAD source's millimetres
# port to. Mixing them fails at recompute with "Unit mismatch in minus operation", so the
# unit is divided out here, once, rather than at each of the six places these are used.
SK = 'BffTangency.Constraints.'
BBF_CX = '(%sbbf_cx / 1mm)' % SK
BBF_CY = '(%sbbf_cy / 1mm)' % SK


def _tangency_sketch(doc):
    """OQ-DES-B14: the fillet center, stated as the two tangencies it actually satisfies.

    The center used to be arithmetic -- `bbf_cx` a subtraction and `bbf_cy` a square root
    under `max(...; 0)`. Both are true, and both are invisible: a reader has to reconstruct
    the algebra to see that what they describe is a circle of radius `flange_fillet_radius`
    touching the flange's inner face and the bolt boss at the same time. Here that circle is
    drawn, the two `Tangent` constraints are stated, and the solver places it.

    **Construction geometry only, and the profile is simply out of scope here.** The obvious
    reading of "build the fillet from a sketch" is to sketch its profile. An earlier version
    of this docstring claimed that could not be done, because on 18 of the 88 valid end-type
    variants `bbf_sx = max(flange_inner_x; bolt_c)` resolves to `bolt_c`, the quad's bottom
    edge collapses, and the profile is a triangle rather than a quad. **That argument was
    wrong**: it assumed one sketch has to serve the whole parameter space, which nothing
    requires -- a document is generated per parameter set, so the generator emits whichever
    topology the parameters call for, four edges or three.

    Measured on the real profile rather than argued (2026-08-16): a four-edge sketch is exact
    right up to *and including* the exactly-degenerate point, where the collapsed edge is
    0.0000 mm long and the volume still matches the trapezoid formula. Only past that point
    does it fail, and then `solve()` returns -1 while `FullyConstrained` stays True and the
    extrusion keeps serving the last geometry that solved. That is worth knowing generally,
    and `corner_tree._sketch()` now checks `solve()` for exactly this reason.

    So a profile sketch is available and is the natural target for `PartDesign::` (IP-FC-75).
    It is not done here because this change is about where the center comes from, and moving
    the profile as well would put a verified construction and an unverified one in the same
    step.

    **The sheet may not read this back.** FreeCAD's dependency graph is per object, so a
    `Params` cell referring to this sketch, which refers to `Params`, is a cycle: it reports
    "The graph must be a DAG" and then leaves the sketch permanently touched and never
    recomputed, with its last solved values still in place and looking correct. So the
    solved center flows sketch -> geometry only, and the handful of quantities that used to
    be sheet rows are expressions on the objects that need them.
    """
    P = 'Params.'
    sheet = doc.getObject('Params')
    doc.recompute()

    def cell(alias):
        return float(sheet.get(alias))

    face, ffr = cell('flange_inner_x'), cell('flange_fillet_radius')
    bolt_c, boss_r = cell('bolt_c'), cell('bolt_boss_r')
    seed_cx = face - ffr
    span = (ffr + boss_r) ** 2 - (seed_cx - bolt_c) ** 2
    if span <= 0:
        # What `max(...; 0)` used to swallow. The flange is too far out for any circle of
        # radius flange_fillet_radius to touch both it and the boss, so there is no fillet
        # to place and the sketch below would be unsatisfiable.
        raise RuntimeError(
            'bolt_flange_fillet: no circle of radius %.4f can touch both the flange face at '
            'x = %.4f and the bolt boss of radius %.4f at (%.4f, %.4f). The two tangencies '
            'have no common solution (would-be discriminant %.4f mm2).'
            % (ffr, face, boss_r, bolt_c, bolt_c, span))
    seed_cy = math.sqrt(span) + bolt_c

    sk = C._owned(doc, 'Sketcher::SketchObject', 'BffTangency')
    if sk.GeometryCount == 0:
        # G0 the fillet circle, G1 the bolt boss, G2 the flange's inner face. All
        # construction: this sketch is never extruded, it only places a point.
        sk.addGeometry(Part.Circle(V(seed_cx, seed_cy, 0), V(0, 0, 1), ffr), True)
        sk.addGeometry(Part.Circle(V(bolt_c, bolt_c, 0), V(0, 0, 1), boss_r), True)
        far = cell('far')
        sk.addGeometry(Part.LineSegment(V(face, bolt_c - far, 0), V(face, bolt_c + far, 0)),
                       True)

        def con(c, expr=None, name=None, driving=True):
            i = sk.addConstraint(c)
            if expr is not None:
                sk.setExpression('Constraints[%d]' % i, expr)
            if not driving:
                sk.setDriving(i, False)
            if name:
                sk.renameConstraint(i, name)
            return i

        # the flange face: a vertical line at flange_inner_x. Its endpoints carry no meaning
        # and are pinned only so the sketch can reach full constraint.
        con(S.Constraint('Vertical', 2))
        con(S.Constraint('DistanceX', -1, 1, 2, 1, face), P + 'flange_inner_x')
        con(S.Constraint('DistanceY', -1, 1, 2, 1, bolt_c - far), P + 'bolt_c - ' + P + 'far')
        con(S.Constraint('DistanceY', -1, 1, 2, 2, bolt_c + far), P + 'bolt_c + ' + P + 'far')

        # the boss, at the bolt center
        con(S.Constraint('DistanceX', -1, 1, 1, 3, bolt_c), P + 'bolt_c')
        con(S.Constraint('DistanceY', -1, 1, 1, 3, bolt_c), P + 'bolt_c')
        con(S.Constraint('Radius', 1, boss_r), P + 'bolt_boss_r')

        # the fillet circle: its radius, and the two statements this whole question is about
        con(S.Constraint('Radius', 0, ffr), P + 'flange_fillet_radius')
        con(S.Constraint('Tangent', 0, 2), name='tangent_to_flange_face')
        con(S.Constraint('Tangent', 0, 1), name='tangent_to_bolt_boss')

        # what the solver produced, for everything downstream to read
        con(S.Constraint('DistanceX', -1, 1, 0, 3, seed_cx), name='bbf_cx', driving=False)
        con(S.Constraint('DistanceY', -1, 1, 0, 3, seed_cy), name='bbf_cy', driving=False)

    doc.recompute()
    dof = sk.solve()
    if dof != 0 or not sk.FullyConstrained:
        raise RuntimeError('BffTangency did not solve (solve()=%d, fully constrained %s). '
                           'The two tangencies have no common solution at these parameters.'
                           % (dof, sk.FullyConstrained))

    # The branch guard IP-FC-73 asks for. Two circles have two common tangent circles on a
    # given side and the solver converges on whichever the seed is nearest; the closed form
    # is kept HERE, as a test of the solved position rather than as its source, because a
    # wrong branch is geometry that builds happily and is simply in the wrong place.
    got = (sk.getDatum('bbf_cx').Value, sk.getDatum('bbf_cy').Value)
    if max(abs(got[0] - seed_cx), abs(got[1] - seed_cy)) > 1e-7:
        raise RuntimeError('BffTangency solved to (%.9f, %.9f) but the two tangencies place '
                           'the center at (%.9f, %.9f) -- the solver took the wrong branch.'
                           % (got[0], got[1], seed_cx, seed_cy))
    return sk


def bolt_flange_fillet(doc):
    """Quad (cx, cy) (sx, cy) (sx, -bolt) (-bolt, -bolt): the top edge is horizontal here
    because the start and center share a y, so only the ray edge needs clipping.

    `cx, cy` is solved by `BffTangency` rather than computed -- see `_tangency_sketch()`.
    The quantities that used to be sheet rows are expressions here for the reason given
    there: a sheet row reading this sketch would close a dependency cycle.
    """
    P = 'Params.'
    _tangency_sketch(doc)

    dx = '(%s - %sbolt_c)' % (BBF_CX, P)
    dy = '(%s - %sbolt_c)' % (BBF_CY, P)
    # The quad's leftmost vertex, which is NOT the fillet center -- IP-FC-58. Starting the
    # block at the center puts its left edge, the ray edge and the relief cylinder's center
    # concurrent, and OCCT does not survive that; see OQ-DES-B14.
    bx = 'min(%s; %sbolt_c)' % (BBF_CX, P)
    # `bbf_r` was sqrt(dx^2 + dy^2), which the circle rule makes identically r_bolt_fillet.
    # That was true before and is now true *by construction*: it is the tangency the sketch
    # states, so there is no clamped branch on which the identity could fail.
    ray = '%sbolt_c - %sfar * %%s / %sr_bolt_fillet' % (P, P, P)

    block = C._box(doc, 'BffBlock', '%sbbf_sx - %s' % (P, bx), dy,
                   P + 'bulkhead_thickness', bx, P + 'bolt_c', '0')
    node = C._cut(doc, 'BffRay', block,
                  _ray_halfplane(doc, 'BffRayBox', 'atan2(%s; %s)' % (dy, dx),
                                 ray % dx, ray % dy))
    node = _relief_stack(doc, 'Bff', node, BBF_CX, BBF_CY)
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
