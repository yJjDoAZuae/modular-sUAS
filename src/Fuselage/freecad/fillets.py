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

**All four rounded corners are solved, not computed, and they share one sketch**
(OQ-ARCH-14, decided 2026-08-17; IP-FC-73). Each center used to be spreadsheet arithmetic --
subtractions, a square root under `max(...; 0)` twice over, and one `max` selecting which
face the circle was measured from. What every one of them describes is a circle of radius
`flange_fillet_radius` touching two named features at once, so that is now *stated*:
`FilletTangency` is a fully constrained construction sketch holding the four features the
corners are cut between --

    the flange's inner face      x = flange_inner_x        (vertical line)
    the flange's y face          y = flange_y              (horizontal line)
    the bolt boss                bolt_boss_r at the bolt   (circle)
    the greeble web's wall face  45 degrees, half a flange_thickness off the diagonal

-- and one circle per fillet, each carrying two `Tangent` constraints and reading its solved
center back out through reference dimensions. The four pair up around the corner:
`outer_corner_fillet` is flange face + flange y face, `greeble_to_web_fillet` is flange face
+ wall, `bolt_flange_fillet` is flange face + boss, `web_to_bolt_fillet` is boss + wall.

**The sketch carries only the fillets that exist at these parameters.** Which corners a
variant has is a property of the variant, and it was previously expressed nowhere: the
greeble-to-web fillet's `gtw_start = max(flange_inner_x; -bolt_offset)` was that question
answered by relocating the body onto the bolt centerline, inside the bolt hole, rather than
by leaving it out. See `_web_meets_flange()` for the geometric condition that replaces it and
for what it costs. The other three exist at every valid parameter set measured.

See `_fillet_tangency_sketch()` for why the sketch holds only centers and not profiles, and
why the sheet is not allowed to read it back.

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

    # The two flange faces the outer corner is cut between. The fillet center one radius in
    # from their corner is NOT here any more: it is solved by `FilletTangency`, along with
    # the other three -- see `_fillet_tangency_sketch()`.
    ('flange_inner_x', '=-panel_tolerance - panel_offset - panel_overlap - flange_thickness'),
    ('flange_y', '=corner_radius - panel_thickness - panel_tolerance - flange_thickness'),

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

    # greeble_to_web_fillet's center is solved by `FilletTangency` too, and the five rows that
    # used to be here (`gtw_start`, `gtw_cx`, `gtw_ex`, `gtw_ey`, `gtw_cy`) went with it,
    # along with the two `gtw_d*` rows that placed its diagonal clip. `gtw_start`'s
    # `max(flange_inner_x; -bolt_offset)` is the clamp OQ-ARCH-14 removed: it did not select
    # between two faces, it moved the fillet onto a face it is not tangent to. What replaces
    # it is a condition on whether the corner exists at all -- `_web_meets_flange()`.
    ('far', '=unit_width'),
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

    # bulkhead_bolt_flange_fillet's outboard extent -- the x its covering block stops at.
    # **This `max` is not the clamp OQ-ARCH-14 removed, and the difference is the point.** It
    # does not move the fillet: the two tangencies place the center regardless, and this only
    # says how far the block that carries it reaches, which is the further in of the flange
    # face and the bolt center. Where the flange face is the outer one the quad's bottom edge
    # collapses and the profile is a triangle -- a topology the generator is entitled to
    # choose, since it emits one document per parameter set (IP-FC-76). A clamp returns a
    # plausible wrong answer for a question that has none; this returns the right answer to a
    # question about extent.
    ('bbf_sx', '=max(flange_inner_x; bolt_c)'),

    # The centers of all four rounded corners are solved by `FilletTangency` and read back
    # from its reference dimensions. The rows that used to hold them are expressions on the
    # objects that need them instead: a sheet row reading the sketch would close a dependency
    # cycle, since the sketch reads the sheet. `bbf_cy` and `wtb_tan` were the module's two
    # `sqrt(max(...; 0))` clamps, and both are gone -- the sketch refuses to solve rather
    # than returning a plausible wrong position.
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


# The names the rest of the module reads the solved centers back through.
# `Constraints.<name>` resolves a *reference* (non-driving) dimension, whose value the solver
# writes. One sketch means one flat namespace for those names, which is why every one of them
# keeps its `ocf_` / `gtw_` / `bbf_` / `wtb_` prefix.
#
# `/ 1mm` is not decoration. A sketch constraint is a Quantity carrying a length unit; every
# row of this sheet is a bare number, because that is what the OpenSCAD source's millimetres
# port to. Mixing them fails at recompute with "Unit mismatch in minus operation", so the
# unit is divided out here, once, rather than at each of the places these are used.
SKETCH = 'FilletTangency'
SK = SKETCH + '.Constraints.'


def _read(tag):
    return '(%s%s_cx / 1mm)' % (SK, tag), '(%s%s_cy / 1mm)' % (SK, tag)


OCF_CX, OCF_CY = _read('ocf')
GTW_CX, GTW_CY = _read('gtw')
BBF_CX, BBF_CY = _read('bbf')
WTB_CX, WTB_CY = _read('wtb')


SQ2 = math.sqrt(2.0)


def cells(doc):
    """A reader for the parameter sheet, recomputed so the values are current."""
    sheet = doc.getObject('Params')
    doc.recompute()
    return lambda alias: float(sheet.get(alias))


def _always(_g):
    return True


def _web_meets_flange(g):
    """Does the bolt-to-corner web actually reach the flange's inner face?

    **This is what replaces `gtw_start = max(flange_inner_x; -bolt_offset)`** (OQ-ARCH-14).
    The greeble-to-web fillet rounds the corner where the web's upper face runs into the
    flange's inner face, and that corner exists only if the two surfaces meet.

    `greeble_web.py` builds the web as a 45 degree strip along the segment from the corner at
    the origin to the bolt center at `(bolt_c, bolt_c)` -- it stops at the bolt and does not
    continue past it. The flange's inner face is the plane `x = flange_inner_x`. So the plane
    crosses the web exactly while it lies within the segment's x span, which runs from
    `bolt_c` up to 0, and `flange_inner_x` is negative in every valid parameter set. That
    leaves one comparison: **the flange face is inboard of the bolt center**.

    That is the same inequality the `max` tested, and saying so is the honest description --
    but it is not the same statement, and the difference is the whole of OQ-ARCH-14. The
    `max` used the comparison to pick a *different face* to measure from, which put the
    fillet one radius outboard of the bolt centerline, inside the bolt hole, tangent to
    nothing and rounding nothing. This uses it to decide whether the corner is there, and
    when it is not the fillet is left out.

    **Leaving it out costs nothing, measured over the whole affected population.** The
    condition fails on 27 of 148 valid variants, all at U <= 1.0, and in every one of them the
    finished octant is identical to below 1e-6 mm3 with the clamped body and without it
    (`tools/fillet_scope_analysis/sweep_clamped_gtw.py`, 2026-08-17). The clamped body is not
    small -- 0.46 to 3.14 mm3 -- but it lies inside the bolt hole, and a fillet is a positive
    fused *before* the hole is cut, so the cut removed all of it anyway. OQ-ARCH-14 accepted a
    cost of "at most 0.042 mm3 per variant" on the way in; that figure was this fillet's net
    share of the **positive**, which is the wrong stage to ask at.

    **Being buried is not the same as being absent, and is not tested here.** In many
    variants where the corner does exist the bolt boss or the neighboring fillets cover it
    completely, so the fillet adds nothing to the fused solid -- the web-to-bolt fillet is
    hidden the same way at U = 3.0. A fillet in the right place that something else happens
    to cover is correct and stays; the test is on the corner, not on the visible result.
    """
    return g('flange_inner_x') >= g('bolt_c')


def _ocf_seed(g):
    r = g('flange_fillet_radius')
    return g('flange_inner_x') - r, g('flange_y') - r


def _gtw_seed(g):
    r, ft = g('flange_fillet_radius'), g('flange_thickness')
    cx = g('flange_inner_x') - r
    # one radius in from the face, and one radius off the wall along its 45 degree normal
    return cx, cx + r * SQ2 + ft / SQ2


def _bbf_seed(g):
    r, boss_r, bolt_c = g('flange_fillet_radius'), g('bolt_boss_r'), g('bolt_c')
    cx = g('flange_inner_x') - r
    span = (r + boss_r) ** 2 - (cx - bolt_c) ** 2
    if span <= 0:
        # What `max(...; 0)` used to swallow. The flange is too far out for any circle of
        # radius flange_fillet_radius to touch both it and the boss, so there is no fillet
        # to place and the sketch would be unsatisfiable.
        raise RuntimeError(
            'bolt_flange_fillet: no circle of radius %.4f can touch both the flange face at '
            'x = %.4f and the bolt boss of radius %.4f at (%.4f, %.4f). The two tangencies '
            'have no common solution (would-be discriminant %.4f mm2).'
            % (r, g('flange_inner_x'), boss_r, bolt_c, bolt_c, span))
    return cx, math.sqrt(span) + bolt_c


def _wtb_seed(g):
    """The web-to-bolt fillet's center, and **two** conditions rather than one.

    The circle has to be placeable, and then the covering block that carries it has to have
    some extent. Those are different configurations, and only the first was guarded until
    2026-08-17. Between them lies a band where the tangency is perfectly satisfiable and the
    build fails anyway, with OCCT's `Length of box too small` and then "shape is invalid"
    raised from several features downstream -- a failure naming nothing, which is the exact
    thing this whole item exists to remove.

    Measured at `1.5 end_anchor 0mm`: the body stops building at `bolt_boss_r` about 1.114
    times `flange_thickness / 2`, while the circle stays placeable down to 1.000. **No valid
    variant is anywhere near either** -- the corpus holds that ratio above 4.33 -- which is
    why it took a deliberately thin boss against a thick web to find it, and why the band is
    refused rather than redesigned. What a fillet *should* be there is a question no built part
    asks; the OpenSCAD source carries the same construction and the same limit.
    """
    r, ft = g('flange_fillet_radius'), g('flange_thickness')
    boss_r, bolt_c = g('bolt_boss_r'), g('bolt_c')
    # The perpendicular distance from the diagonal to the fillet center, if it touches the
    # wall: half the wall plus the radius. The old clamp fired when the boss was too small for
    # any such circle to also reach it -- `bolt_boss_r < flange_thickness / 2`.
    a = r + ft / 2.0
    span = (r + boss_r) ** 2 - a ** 2
    if span <= 0:
        raise RuntimeError(
            'web_to_bolt_fillet: no circle of radius %.4f can touch both the bolt boss of '
            'radius %.4f at (%.4f, %.4f) and a wall %.4f thick through it. The two tangencies '
            'have no common solution (would-be discriminant %.4f mm2).'
            % (r, boss_r, bolt_c, bolt_c, ft, span))
    tan = math.sqrt(span)
    # Where the fillet meets the wall, relative to the bolt center along x. `WtbBlock` runs
    # from the bolt center out to that point, so at or below zero there is no block to build.
    if tan <= ft / 2.0:
        raise RuntimeError(
            'web_to_bolt_fillet: the circle can be placed, but it meets the wall %.4f mm '
            'behind the bolt center, so the block that carries the fillet has no extent. A '
            'boss of radius %.4f against a wall %.4f thick needs %.4f to reach; every valid '
            'variant is above 4.3 times the wall half-thickness.'
            % ((ft / 2.0 - tan) / SQ2, boss_r, ft,
               math.sqrt((r + ft / 2.0) ** 2 + (ft / 2.0) ** 2) - r))
    return bolt_c + (tan - a) / SQ2, bolt_c + (tan + a) / SQ2


class _Sub:
    """One rounded corner's tangency sub-system inside `FilletTangency`.

    `touches` names the two reference features the circle is tangent to, `active` says
    whether this variant has the corner at all, and `seed` is the closed form -- kept as a
    test of where the solver landed, never as its source.
    """

    def __init__(self, tag, fillet, touches, active, seed):
        self.tag, self.fillet = tag, fillet
        self.touches, self.active, self.seed = touches, active, seed


SUBS = [
    _Sub('ocf', 'outer_corner_fillet', ('flange_face', 'flange_y_face'), _always, _ocf_seed),
    _Sub('gtw', 'greeble_to_web_fillet', ('flange_face', 'wall_face'),
         _web_meets_flange, _gtw_seed),
    _Sub('bbf', 'bolt_flange_fillet', ('flange_face', 'bolt_boss'), _always, _bbf_seed),
    _Sub('wtb', 'web_to_bolt_fillet', ('bolt_boss', 'wall_face'), _always, _wtb_seed),
]


def _fillet_tangency_sketch(doc):
    """IP-FC-73: all four rounded corners' centers, stated as the tangencies they satisfy.

    Each center used to be arithmetic, and every one of them was true and invisible: a reader
    had to reconstruct the algebra to see that what the rows described was a circle of radius
    `flange_fillet_radius` touching two named features at once. Here the four reference
    features are drawn once, a circle is drawn per corner, the eight `Tangent` constraints are
    stated, and the solver places them.

    **One sketch rather than four, because the four are one picture.** They are cut between
    four surfaces in total, shared: the flange's inner face carries three of them and the bolt
    boss and the 45 degree wall two each. Four separate sketches would state the same face
    four different times and let the four drift apart silently. It also means the sketch can
    say which corners this variant *has* -- see `_web_meets_flange()`. Nothing here is
    conditional on a `max`; a corner that is not there is simply not drawn.

    **A single sketch fails as a unit, so the failure has to be attributed.** `solve()` and
    `FullyConstrained` are properties of the whole sketch, so one unsatisfiable sub-system
    would otherwise report as one failed sketch and lose which corner caused it. Two things
    prevent that: every sub-system's closed form runs *before* the sketch is built, and all
    the impossible ones are refused together by name rather than only the first, and if the
    assembled sketch still fails to solve, `_worst_sub()` names the sub-system furthest from
    where its own two tangencies put it. `Constraints.<name>` is one flat namespace per
    sketch, which is why the reference dimensions keep their `ocf_` / `gtw_` / `bbf_` /
    `wtb_` prefixes.

    **Merging costs precision after a parameter edit, and this is what it costs.** The solver
    stops on a residual over the whole system, so a system four times the size converges less
    tightly per constraint. Measured 2026-08-17 at `1.5 end_anchor 0mm`, sweeping
    `bolt_offset`: after a bare recompute the two bolt-related centers land 1.2e-7 mm and
    5.6e-8 mm from where their tangencies put them, against 3.5e-11 mm for the separate
    sketches they replace. Calling `solve()` once more on the same state brings both back to
    1.8e-15 mm, which is what identifies the cause as the convergence budget rather than
    anything geometric -- and the *generated* document is unaffected, because the line below
    is that extra solve. The looser figure is what a **delivered file** holds after someone
    edits a parameter, and it is worst where the geometry is already ill-conditioned: that
    variant has the bolt-flange fillet 0.2 mm from the degeneracy `report_bbf_gap.py` tracks,
    where the center's y is extremely sensitive to any residual at all. 1.2e-7 mm is a tenth
    of a nanometre on a printed part and every assembled volume is unchanged to six figures,
    so this is recorded rather than treated as a defect -- but `check_tangency.py` reads the
    sweep after a bare recompute on purpose, so the tolerance there is set for the state a
    delivered file is actually in, not for the state the generator leaves.

    A shorter reference line was tried and does not help; the first measurement that suggested
    it did came from seeding the endpoints at one length while the driving expression pinned
    them at another, which is a different thing entirely.

    **Construction geometry only, and the profiles are simply out of scope here.** The obvious
    reading of "build the fillet from a sketch" is to sketch its profile. An earlier version
    of this docstring claimed that could not be done for the bolt-flange fillet, because on 18
    of the 88 valid end-type variants `bbf_sx = max(flange_inner_x; bolt_c)` resolves to
    `bolt_c`, the quad's bottom edge collapses, and the profile is a triangle rather than a
    quad. **That argument was wrong**: it assumed one sketch has to serve the whole parameter
    space, which nothing requires -- a document is generated per parameter set, so the
    generator emits whichever topology the parameters call for, four edges or three.

    Measured on the real profile rather than argued (2026-08-16): a four-edge sketch is exact
    right up to *and including* the exactly-degenerate point, where the collapsed edge is
    0.0000 mm long and the volume still matches the trapezoid formula. Only past that point
    does it fail, and then `solve()` returns -1 while `FullyConstrained` stays True and the
    extrusion keeps serving the last geometry that solved. That is worth knowing generally,
    and `corner_tree._sketch()` now checks `solve()` for exactly this reason.

    So profile sketches are available and are the natural target for `PartDesign::`
    (IP-FC-75). They are not done here because this change is about where the centers come
    from, and moving the profiles as well would put a verified construction and an unverified
    one in the same step.

    **The sheet may not read this back.** FreeCAD's dependency graph is per object, so a
    `Params` cell referring to this sketch, which refers to `Params`, is a cycle: it reports
    "The graph must be a DAG" and then leaves the sketch permanently touched and never
    recomputed, with its last solved values still in place and looking correct. So solved
    centers flow sketch -> geometry only, and the quantities that used to be sheet rows are
    expressions on the objects that need them.

    **What a delivered file cannot do.** Which corners exist is decided here, at generation
    time, and a hand edit that moves a parameter across that boundary does not add or remove a
    circle -- the sketch has the geometry it was emitted with. That is the same limit every
    topology switch in this port has, including the bolt-flange fillet's quad-to-triangle, and
    it is why `check_tangency.py` measures what an edit past the boundary actually does rather
    than assuming it is harmless.
    """
    P = 'Params.'
    g = cells(doc)

    # Before anything is drawn: every sub-system's closed form, so an impossible configuration
    # is refused by the name of the fillet that cannot be built rather than by the sketch.
    # All of them are tried, not just up to the first failure -- one parameter can make two
    # corners impossible at once, and reporting only the earliest would send a reader to the
    # wrong one.
    subs = [s for s in SUBS if s.active(g)]
    seeds, refused = {}, []
    for s in subs:
        try:
            seeds[s.tag] = s.seed(g)
        except RuntimeError as exc:
            refused.append(str(exc))
    if refused:
        raise RuntimeError(' '.join(refused))

    sk = C._owned(doc, 'Sketcher::SketchObject', SKETCH)
    if sk.GeometryCount == 0:
        ffr, ft = g('flange_fillet_radius'), g('flange_thickness')
        face, fy, far = g('flange_inner_x'), g('flange_y'), g('far')
        bolt_c, boss_r = g('bolt_c'), g('bolt_boss_r')

        def con(c, expr=None, name=None, driving=True):
            i = sk.addConstraint(c)
            if expr is not None:
                sk.setExpression('Constraints[%d]' % i, expr)
            if not driving:
                sk.setDriving(i, False)
            if name:
                sk.renameConstraint(i, name)
            return i

        # --- the four features the corners are cut between. All construction: this sketch is
        # --- never extruded, it only places points. Line endpoints carry no meaning and are
        # --- pinned only so the sketch can reach full constraint.
        ref = {}

        # the flange's inner face: a vertical line at flange_inner_x
        i = ref['flange_face'] = sk.addGeometry(
            Part.LineSegment(V(face, bolt_c - far, 0), V(face, bolt_c + far, 0)), True)
        con(S.Constraint('Vertical', i))
        con(S.Constraint('DistanceX', -1, 1, i, 1, face), P + 'flange_inner_x')
        con(S.Constraint('DistanceY', -1, 1, i, 1, bolt_c - far),
            P + 'bolt_c - ' + P + 'far')
        con(S.Constraint('DistanceY', -1, 1, i, 2, bolt_c + far),
            P + 'bolt_c + ' + P + 'far')

        # the flange's y face: a horizontal line at flange_y
        i = ref['flange_y_face'] = sk.addGeometry(
            Part.LineSegment(V(face - far, fy, 0), V(face + far, fy, 0)), True)
        con(S.Constraint('Horizontal', i))
        con(S.Constraint('DistanceY', -1, 1, i, 1, fy), P + 'flange_y')
        con(S.Constraint('DistanceX', -1, 1, i, 1, face - far),
            P + 'flange_inner_x - ' + P + 'far')
        con(S.Constraint('DistanceX', -1, 1, i, 2, face + far),
            P + 'flange_inner_x + ' + P + 'far')

        # the bolt boss, at the bolt center
        i = ref['bolt_boss'] = sk.addGeometry(
            Part.Circle(V(bolt_c, bolt_c, 0), V(0, 0, 1), boss_r), True)
        con(S.Constraint('DistanceX', -1, 1, i, 3, bolt_c), P + 'bolt_c')
        con(S.Constraint('DistanceY', -1, 1, i, 3, bolt_c), P + 'bolt_c')
        con(S.Constraint('Radius', i, boss_r), P + 'bolt_boss_r')

        # the greeble web's wall face: a 45 degree line offset half a flange_thickness from
        # the bolt's diagonal. Both endpoints are pinned, which is four constraints for a
        # line's four degrees of freedom -- there is no `Vertical` to lean on here.
        off, reach = ft / 2.0 / SQ2, far / SQ2
        OFF = '%sflange_thickness / 2 / sqrt(2)' % P
        REACH = '%sfar / sqrt(2)' % P
        i = ref['wall_face'] = sk.addGeometry(
            Part.LineSegment(V(bolt_c - off - reach, bolt_c + off - reach, 0),
                             V(bolt_c - off + reach, bolt_c + off + reach, 0)), True)
        con(S.Constraint('DistanceX', -1, 1, i, 1, bolt_c - off - reach),
            '%sbolt_c - %s - %s' % (P, OFF, REACH))
        con(S.Constraint('DistanceY', -1, 1, i, 1, bolt_c + off - reach),
            '%sbolt_c + %s - %s' % (P, OFF, REACH))
        con(S.Constraint('DistanceX', -1, 1, i, 2, bolt_c - off + reach),
            '%sbolt_c - %s + %s' % (P, OFF, REACH))
        con(S.Constraint('DistanceY', -1, 1, i, 2, bolt_c + off + reach),
            '%sbolt_c + %s + %s' % (P, OFF, REACH))

        # --- one circle per corner this variant has, each carrying the two statements the
        # --- whole conversion is about, and the reference dimensions everything downstream
        # --- reads its solved center back through.
        for s in subs:
            cx, cy = seeds[s.tag]
            i = sk.addGeometry(Part.Circle(V(cx, cy, 0), V(0, 0, 1), ffr), True)
            con(S.Constraint('Radius', i, ffr), P + 'flange_fillet_radius')
            for what in s.touches:
                con(S.Constraint('Tangent', i, ref[what]),
                    name='%s_tangent_to_%s' % (s.tag, what))
            con(S.Constraint('DistanceX', -1, 1, i, 3, cx), name=s.tag + '_cx', driving=False)
            con(S.Constraint('DistanceY', -1, 1, i, 3, cy), name=s.tag + '_cy', driving=False)

    doc.recompute()
    dof = sk.solve()
    if dof != 0 or not sk.FullyConstrained:
        raise RuntimeError(
            '%s did not solve (solve()=%d, fully constrained %s). It carries %d tangency '
            'sub-system(s) -- %s -- and the one furthest from where its own two tangencies '
            'put it is %s.'
            % (SKETCH, dof, sk.FullyConstrained, len(subs),
               ', '.join(s.tag for s in subs), _worst_sub(sk, subs, seeds)))

    # The branch guard. A circle tangent to two circles, or to a circle and a line, has more
    # than one solution and the solver converges on whichever the seed is nearest; the closed
    # forms are kept HERE, as a test of the solved positions rather than as their source,
    # because a wrong branch is geometry that builds happily and is simply in the wrong place.
    #
    # Scaled with `U`, for the reason `compare_backends.bbox_tol()` gives: this is a millimetre
    # distance between two points whose coordinates are proportional to `U`, so a fixed figure
    # is four times stricter at U = 4 than at U = 1. Floored at U = 1. It is nowhere near
    # binding either way -- a wrong branch moves a center by millimetres, not by 1e-7 mm -- but
    # an absolute tolerance sitting among scaled ones is how these get written wrong.
    # `unit_width` is 100*U and is a row here; `U` itself is not, because the sheet carries
    # only the rows this octant is built from.
    branch_tol = 1e-7 * max(g('unit_width') / 100.0, 1.0)
    for s in subs:
        got, want = _solved(sk, s.tag), seeds[s.tag]
        if max(abs(got[0] - want[0]), abs(got[1] - want[1])) > branch_tol:
            raise RuntimeError(
                '%s: the %s sub-system (%s) solved to (%.9f, %.9f) but its two tangencies '
                'place the center at (%.9f, %.9f) -- the solver took the wrong branch.'
                % ((SKETCH, s.tag, s.fillet) + got + want))
    return sk


def _solved(sk, tag):
    return sk.getDatum(tag + '_cx').Value, sk.getDatum(tag + '_cy').Value


def _worst_sub(sk, subs, seeds):
    """Which sub-system is furthest from its own closed form, for a failure message.

    `solve()` reports one number for the whole sketch, so this is what turns that back into
    the name of a fillet. The datums still hold the last values the solver wrote, which is
    exactly what should be reported when it stops agreeing with the tangencies stated.
    """
    named = {c.Name for c in sk.Constraints}
    worst, at = -1.0, None
    for s in subs:
        if s.tag + '_cx' not in named:
            return '%s (%s), which has no solved center at all' % (s.tag, s.fillet)
        got, want = _solved(sk, s.tag), seeds[s.tag]
        err = max(abs(got[0] - want[0]), abs(got[1] - want[1]))
        if err > worst:
            worst, at = err, ('%s (%s), solved (%.6f, %.6f) against (%.6f, %.6f), %.3e mm off'
                              % ((s.tag, s.fillet) + got + want + (err,)))
    return at


def _tangency(doc):
    """`FilletTangency`, built once per emit and shared by every corner that reads it."""
    if SKETCH in C._SEEN:
        return doc.getObject(SKETCH)
    return _fillet_tangency_sketch(doc)


def outer_corner_fillet(doc):
    """The corner between the flange's inner face and its y face. Two perpendicular planes,
    so this is the one center that never had a discriminant -- but it is stated the same way
    as the other three, because four separate accounts of the same flange face is what the
    single sketch exists to stop."""
    P = 'Params.'
    _tangency(doc)
    block = C._box(doc, 'OcfBlock', P + 'flange_fillet_radius',
                   P + 'flange_fillet_radius', P + 'bulkhead_thickness',
                   OCF_CX, OCF_CY, '0')
    node = _relief_stack(doc, 'Ocf', block, OCF_CX, OCF_CY)
    tip = C._owned(doc, 'Part::Refine', 'OuterCornerFillet')
    tip.Source = node
    return tip


def greeble_to_web_fillet(doc):
    """The corner where the greeble web's upper face runs into the flange's inner face.

    **Returns None where the variant has no such corner** -- see `_web_meets_flange()`. The
    caller fuses whatever it is given, so an absent corner is absent rather than relocated.

    `gtw_ey`, the y the covering block starts at, was a sheet row reached through `gtw_ex`;
    it is the y of the point where the fillet meets the wall, which the tangency makes exactly
    one radius along the wall's 45 degree normal from the center. Same value, without the
    intermediate rows.
    """
    P = 'Params.'
    _tangency(doc)
    if not _web_meets_flange(cells(doc)):
        return None

    # the covering block: from the wall tangent point up to the center, and out to the face
    ey = '(%s - %sflange_fillet_radius / sqrt(2))' % (GTW_CY, P)
    block = C._box(doc, 'GtwBlock', '%sflange_inner_x - %s' % (P, GTW_CX),
                   P + 'flange_fillet_radius / sqrt(2)', P + 'bulkhead_thickness',
                   GTW_CX, ey, '0')
    # half-plane x + y < (cx + cy), as a box rotated +45
    half = '((%s + %s) / 2)' % (GTW_CX, GTW_CY)
    node = C._cut(doc, 'GtwDiag', block,
                  C._box(doc, 'GtwDiagBox', P + 'diag_len', P + 'diag_wid',
                         P + 'bulkhead_thickness * 3',
                         '%s + %sfar * (1 - sqrt(2))' % (half, P),
                         '%s - %sfar * (1 + sqrt(2))' % (half, P),
                         '-' + P + 'bulkhead_thickness', angle=45))
    node = _relief_stack(doc, 'Gtw', node, GTW_CX, GTW_CY)
    tip = C._owned(doc, 'Part::Refine', 'GreebleToWebFillet')
    tip.Source = node
    return tip


def bolt_flange_fillet(doc):
    """Quad (cx, cy) (sx, cy) (sx, -bolt) (-bolt, -bolt): the top edge is horizontal here
    because the start and center share a y, so only the ray edge needs clipping.

    `cx, cy` is solved by `FilletTangency` rather than computed -- see
    `_fillet_tangency_sketch()`. The quantities that used to be sheet rows are expressions
    here for the reason given there: a sheet row reading the sketch would close a dependency
    cycle.
    """
    P = 'Params.'
    _tangency(doc)

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
    flange wall through the center, and the ray edge.

    `cx, cy` is solved by `FilletTangency` rather than computed -- see
    `_fillet_tangency_sketch()`. The quantities that used to be sheet rows are expressions
    here, for the reason given there: a sheet row reading the sketch would close a dependency
    cycle.
    """
    P = 'Params.'
    _tangency(doc)

    dx = '(%s - %sbolt_c)' % (WTB_CX, P)
    dy = '(%s - %sbolt_c)' % (WTB_CY, P)
    # `wtb_r` was sqrt(dx^2 + dy^2), which the tangency to the boss makes identically
    # r_bolt_fillet -- the center sits flange_fillet_radius outside a boss of bolt_boss_r,
    # and those sum to exactly that row. True before by algebra, true now by construction.
    # Measured across all 148 buildable bulkheads, worst 3.6e-15 mm.
    ray = '%sbolt_c - %sfar * %%s / %sr_bolt_fillet' % (P, P, P)
    # `wtb_sx` was reached through the clamped square root; it is the x of the point where
    # the fillet meets the wall, which is the center offset one radius along the 45 degree
    # normal. Same value to 3.6e-15 mm over the corpus, without the clamp.
    sx = '(%s + %sflange_fillet_radius / sqrt(2))' % (WTB_CX, P)
    # half-plane x + y > cx + cy, as a box rotated +45 with its near edge on the line
    half = '(%s + %s) / 2' % (WTB_CX, WTB_CY)

    block = C._box(doc, 'WtbBlock', '%s - %sbolt_c' % (sx, P), dy,
                   P + 'bulkhead_thickness', P + 'bolt_c', P + 'bolt_c', '0')
    node = C._cut(doc, 'WtbWall', block,
                  C._box(doc, 'WtbWallBox', P + 'diag_len', P + 'diag_wid',
                         P + 'bulkhead_thickness * 3',
                         '%s + %sfar' % (half, P), '%s - %sfar' % (half, P),
                         '-' + P + 'bulkhead_thickness', angle=45))
    node = C._cut(doc, 'WtbRay', node,
                  _ray_halfplane(doc, 'WtbRayBox', 'atan2(%s; %s)' % (dy, dx),
                                 ray % dx, ray % dy))
    node = _relief_stack(doc, 'Wtb', node, WTB_CX, WTB_CY)
    tip = C._owned(doc, 'Part::Refine', 'WebToBoltFillet')
    tip.Source = node
    return tip


def emit(doc):
    """Every fillet this parameter set has. `greeble_to_web_fillet` returns None where the
    web never reaches the flange face, so the list is four entries or five."""
    C._SEEN.clear()
    sheet(doc)
    tips = [outer_corner_fillet(doc), flange_chamfer(doc), greeble_to_web_fillet(doc),
            bolt_flange_fillet(doc), web_to_bolt_fillet(doc)]
    doc.recompute()
    return [t for t in tips if t is not None]


def main():
    doc = App.newDocument('fillets')
    tips = emit(doc)

    print('PART:: CSG trees -- bulkhead fillets and chamfer')
    print('  %-20s %14s %14s %12s %9s  %s'
          % ('module', 'tree', 'OpenSCAD', 'delta', 'rel', 'checks'))
    built = {tip.Name for tip in tips}
    for name in REFS:
        if name in built:
            continue
        # Not a failure. The hand driver's own parameters are one of the 27 variants where
        # the greeble-to-web corner does not exist, so the OpenSCAD reference below is the
        # body the clamp used to produce -- the one OQ-ARCH-14 removed. Nothing here can be
        # checked against it, and the whole-corpus comparison is what covers the removal.
        print('  %-20s %14s %14.6f %12s %9s  omitted -- %s'
              % (name, 'not built', REFS[name], '', '',
                 'the web does not reach the flange face at these parameters'))
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
