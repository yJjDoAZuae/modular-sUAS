"""OQ-DES-CW40: the planar rib tools, their exact inner offsets, and the 48-gon they replaced.

`freecad/rib_geometry.py` is the production construction (the `geo` fixture) and
`freecad/rib_hull.py` the harness it was measured with (`hull`), which keeps the 48-gon hull and the
convex `shrink` the inner offset is checked against. Every case here has a closed form: a box dilated
by a regular polygon, a box shrunk by a margin, and an L split at its one concave edge.

Fixtures are kernel geometry and so millimeters, as in the other bridge tests.
"""
import math

import pytest

from conftest import requires_freecad                                       # noqa: E402

pytestmark = requires_freecad


@pytest.fixture
def hull(fc):
    return fc.module('rib_hull')


@pytest.fixture
def geo(fc):
    return fc.module('rib_geometry')


def _ell(Part, App):
    """A 10 x 10 x 10 block with its x > 5, y > 5 quarter removed: one concave edge."""
    return Part.makeBox(10.0, 10.0, 10.0).cut(
        Part.makeBox(5.0, 5.0, 10.0, App.Vector(5.0, 5.0, 0.0)))


def _material_around(solid, edge, App):
    """How many of 72 directions square to `edge`, 0.01 mm from its midpoint, lie in `solid`."""
    mid = 0.5 * (edge.FirstParameter + edge.LastParameter)
    at, t = edge.valueAt(mid), edge.tangentAt(mid)
    u = App.Vector(1, 0, 0) if abs(t.x) < 0.9 else App.Vector(0, 1, 0)
    u = u - t * t.dot(u)
    u.normalize()
    w = t.cross(u)
    return sum(solid.isInside(at + (u * math.cos(a) + w * math.sin(a)) * 0.01, 1e-9, False)
               for a in (2.0 * math.pi * k / 72.0 for k in range(72)))


class TestConvexity(object):

    def test_a_box_is_convex(self, geo, Part):
        box = Part.makeBox(3.0, 4.0, 5.0)
        assert geo.is_convex(box)
        assert len(geo.concave_edges(box)) == 0

    def test_an_ell_has_one_concave_edge(self, geo, Part, App):
        ell = _ell(Part, App)
        assert not geo.is_convex(ell)
        assert len(geo.concave_edges(ell)) == 1

    def test_the_edge_test_is_local_in_either_face_order(self, geo, Part, App):
        # Each of these has convex edges where one face is not convex and reaches past the other
        # face's plane elsewhere; a test over a face's vertices calls those edges concave.
        box = Part.makeBox(10.0, 10.0, 10.0)
        shapes = [
            box.cut(Part.makeBox(5.0, 5.0, 10.0, App.Vector(5.0, 5.0, 0.0))),
            box.cut(Part.makeBox(4.0, 10.0, 6.0, App.Vector(3.0, 0.0, 4.0))),
            box.cut(Part.makeBox(5.0, 10.0, 5.0, App.Vector(5.0, 0.0, 5.0)))
               .cut(Part.makeBox(10.0, 5.0, 5.0, App.Vector(0.0, 5.0, 5.0))),
        ]
        found = []
        for solid in shapes:
            solid = solid.removeSplitter()
            n = 0
            for e in solid.Edges:
                fa, fb = [f for f in solid.Faces if any(e.isSame(g) for g in f.Edges)]
                concave = _material_around(solid, e, App) > 36
                assert geo.bends_out(e, fa, fb) == concave
                assert geo.bends_out(e, fb, fa) == concave
                n += concave
            found.append(n)
        assert found == [1, 2, 2]

    def test_an_ell_splits_into_two_convex_parts_with_its_volume(self, geo, Part, App):
        ell = _ell(Part, App)
        parts = geo.convex_parts(ell)
        assert len(parts) == 2
        assert all(geo.is_convex(p) for p in parts)
        assert abs(sum(p.Volume for p in parts) - 750.0) < 1e-9


class TestDilate(object):
    """A box a x b x c dilated by a regular N-gon of circumradius t with a vertex on +x. For N a
    multiple of 4 the polygon's support is t along each axis, so the plan area is
    ab + 2 (a + b) t + (N / 2) t^2 sin(2 pi / N), and the volume is c times that."""

    @pytest.mark.parametrize('facets', [4, 48])
    def test_a_box_matches_the_closed_form(self, hull, geo, Part, facets):
        a, b, c, t = 10.0, 4.0, 3.0, 0.6
        solid, hull_volume = hull.dilate(Part.makeBox(a, b, c), t / 1000.0, facets)
        polygon = 0.5 * facets * t * t * math.sin(2 * math.pi / facets)
        want = c * (a * b + 2.0 * (a + b) * t + polygon)
        assert solid.isValid()
        assert len(solid.Solids) == 1
        assert abs(solid.Volume - want) < 1e-9 * want
        assert abs(hull_volume - want) < 1e-9 * want
        assert geo.is_convex(solid)

    def test_it_contains_every_copy_the_union_is_made_of(self, hull, Part, App):
        box = Part.makeBox(10.0, 4.0, 3.0)
        solid, _v = hull.dilate(box, 0.0006, 48)
        for i in range(48):
            a = 2 * math.pi * i / 48
            copy = box.translated(App.Vector(0.6 * math.cos(a), 0.6 * math.sin(a), 0.0))
            assert abs(copy.cut(solid).Volume) < 1e-9


def _wedge(Part, App, apex_deg=30.0, h=3.0):
    """A vertical prism on an isosceles triangle with its apex angle `apex_deg` at the origin,
    pointing along -x, legs 10 long, `h` tall."""
    a = math.radians(apex_deg / 2.0)
    pts = [App.Vector(0, 0, 0), App.Vector(10 * math.cos(a), 10 * math.sin(a), 0),
           App.Vector(10 * math.cos(a), -10 * math.sin(a), 0)]
    face = Part.Face(Part.makePolygon(pts + [pts[0]]))
    return face.extrude(App.Vector(0, 0, h))


def _slanted_slab(Part, App):
    """A slab tilted 30 degrees out of the vertical, as the ribs are: every face normal has a
    vertical component except the two ends."""
    slab = Part.makeBox(10.0, 0.1, 6.0)
    slab.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 30.0)
    return slab


class TestDilatePlanar(object):
    """Flat faces moved out by the layer-plane disc's support, square or beveled corners."""

    def test_a_box_grows_by_t_on_its_four_sides_only(self, geo, Part):
        a, b, c, t = 10.0, 4.0, 3.0, 0.6
        solid, _v = geo.dilate_planar(Part.makeBox(a, b, c), t / 1000.0)
        assert solid.isValid()
        assert len(solid.Faces) == 6
        assert abs(solid.Volume - (a + 2 * t) * (b + 2 * t) * c) < 1e-9 * solid.Volume

    @pytest.mark.parametrize('make', ['box', 'wedge', 'slanted'])
    def test_it_contains_the_round_dilation(self, hull, geo, Part, App, make):
        part = {'box': lambda: Part.makeBox(10.0, 4.0, 3.0),
                'wedge': lambda: _wedge(Part, App),
                'slanted': lambda: _slanted_slab(Part, App)}[make]()
        planar, _v = geo.dilate_planar(part, 0.0006)
        round_, _v = hull.dilate(part, 0.0006, 48)
        assert planar.isValid()
        assert round_.cut(planar).Volume < 1e-9

    @pytest.mark.parametrize('make', ['box', 'wedge', 'slanted'])
    def test_every_face_is_the_disc_support_from_the_part(self, geo, Part, App, make):
        """No wall thinner than t: each face plane is exactly the disc's support past the part."""
        part = {'box': lambda: Part.makeBox(10.0, 4.0, 3.0),
                'wedge': lambda: _wedge(Part, App),
                'slanted': lambda: _slanted_slab(Part, App)}[make]()
        planar, _v = geo.dilate_planar(part, 0.0006)
        for f in planar.Faces:
            n, d = geo._plane(f)
            reach = max(n.dot(v.Point) for v in part.Vertexes)
            assert abs((d - reach) - 0.6 * math.hypot(n.x, n.y)) < 1e-9

    def test_a_sharp_wedge_is_beveled_and_reaches_little_past_the_round(self, geo, Part, App):
        """A 30 degree apex turns 150 degrees and the base corners 105: all three are beveled, so
        the plan is a hexagon, and no point is more than t / cos(45 degrees) from the wedge."""
        wedge = _wedge(Part, App)
        planar, _v = geo.dilate_planar(wedge, 0.0006)
        assert len(planar.Faces) == 8
        far = max(wedge.distToShape(Part.Vertex(v.Point))[0] for v in planar.Vertexes)
        assert far <= 0.6 / math.cos(math.radians(45.0)) + 1e-9

    def test_a_right_angle_is_left_square(self, geo, Part):
        planar, _v = geo.dilate_planar(Part.makeBox(10.0, 4.0, 3.0), 0.0006)
        far = max(Part.makeBox(10.0, 4.0, 3.0).distToShape(Part.Vertex(v.Point))[0]
                  for v in planar.Vertexes)
        assert abs(far - 0.6 * math.sqrt(2.0)) < 1e-9


class TestShrink(object):

    def test_a_box_shrinks_by_the_margin_on_every_side(self, hull, Part):
        core = hull.shrink(Part.makeBox(10.0, 4.0, 3.0), 0.01)
        assert core.isValid()
        assert abs(core.Volume - 9.98 * 3.98 * 2.98) < 1e-9

    def test_every_face_of_the_core_is_exactly_the_margin_from_the_solid(self, hull, Part):
        solid, _v = hull.dilate(Part.makeBox(10.0, 4.0, 3.0), 0.0006, 48)
        core = hull.shrink(solid, 0.01)
        shell = Part.Shell(solid.Faces)
        for f in core.Faces:
            assert abs(f.distToShape(shell)[0] - 0.01) < 1e-9

    def test_too_thin_to_shrink_is_none(self, hull, Part):
        assert hull.shrink(Part.makeBox(10.0, 0.01, 3.0), 0.01) is None


class TestInnerOffset(object):
    """The inner offset of a box is a box `2 eps` smaller each way. An ell's has a quarter-round
    at its concave edge. It is the ell's plan, eroded, times the height less `2 eps`, because a
    prism's erosion by a ball is the product of its plan's erosion and its height's. The plan is
    two `(10 - 2 eps) x (5 - 2 eps)` arms overlapping in a `(5 - 2 eps)` square, plus the corner
    square `eps x eps` with its quarter disk of radius `eps` removed."""

    def test_a_box_matches_shrink_and_the_closed_form(self, hull, geo, Part):
        eps = 0.5
        box = Part.makeBox(10.0, 4.0, 3.0)
        core = geo.inner_offset(box, eps / 1000.0)
        want = 9.0 * 3.0 * 2.0
        assert core.isValid()
        assert abs(core.Volume - want) < 1e-9
        assert abs(core.Volume - hull.shrink(box, eps).Volume) < 1e-9

    def test_an_ell_has_a_quarter_round_at_its_concave_edge(self, geo, Part, App):
        eps = 0.5
        core = geo.inner_offset(_ell(Part, App), eps / 1000.0)
        plan = (2.0 * (10.0 - 2 * eps) * (5.0 - 2 * eps) - (5.0 - 2 * eps) ** 2
                + eps * eps * (1.0 - math.pi / 4.0))
        assert core.isValid()
        assert abs(core.Volume - plan * (10.0 - 2 * eps)) < 1e-6

    def test_the_union_of_part_shrinks_is_not_the_inner_offset(self, hull, geo, Part, App):
        """Why `inner_offset` exists: the ell's two abutting convex parts, each shrunk, leave a
        slab `2 eps` thick along the face they share."""
        eps = 0.5
        ell = _ell(Part, App)
        shrunk = [hull.shrink(p, eps) for p in geo.convex_parts(ell)]
        union = shrunk[0].fuse(shrunk[1:])
        assert geo.inner_offset(ell, eps / 1000.0).Volume - union.Volume > 1.0

    def test_a_dilated_box_matches_shrink(self, hull, geo, Part):
        """A convex solid with the real ribs' many narrow faces: a box dilated by a 48-gon."""
        eps = 0.01
        rib, _v = hull.dilate(Part.makeBox(10.0, 4.0, 3.0), 0.0006, 48)
        core = geo.inner_offset(rib, eps / 1000.0)
        exact = hull.shrink(rib, eps)
        assert core.isValid() and len(core.Solids) == 1
        assert core.cut(exact).Volume + exact.cut(core).Volume < 1e-6

    def test_a_slotted_block_with_two_coplanar_tops(self, geo, Part, App):
        """A 10 x 10 x 4 block with a 4-wide, 2-deep slot along y: its two top faces share a plane,
        and the slot floor meets the walls at two concave edges. The plan is a 10 x 2 bar and two
        3-wide prongs; eroded, the bar is (10 - 2 eps)(2 - 2 eps), each prong adds (3 - 2 eps) x 2,
        and each concave corner adds eps^2 (1 - pi / 4). Times (10 - 2 eps) along y."""
        eps = 0.5
        block = Part.makeBox(10.0, 10.0, 4.0).cut(
            Part.makeBox(4.0, 10.0, 2.0, App.Vector(3.0, 0.0, 2.0)))
        core = geo.inner_offset(block, eps / 1000.0)
        plan = ((10.0 - 2 * eps) * (2.0 - 2 * eps) + 2.0 * (3.0 - 2 * eps) * 2.0
                + 2.0 * eps * eps * (1.0 - math.pi / 4.0))
        assert core.isValid()
        assert abs(core.Volume - plan * (10.0 - 2 * eps)) < 1e-6

    def test_cut_cell_by_cell_it_is_the_same(self, geo, Part, App):
        """The ell cut in 3 mm cubes, which slice through its concave edge and its quarter round:
        the cubes' results add up to the closed form, and their shares to the ell."""
        eps = 0.5
        ell = _ell(Part, App)
        core = geo.inner_offset(ell, eps / 1000.0, cell_m=0.003)
        plan = (2.0 * (10.0 - 2 * eps) * (5.0 - 2 * eps) - (5.0 - 2 * eps) ** 2
                + eps * eps * (1.0 - math.pi / 4.0))
        assert all(s.isValid() for s in core.Solids)
        assert abs(sum(s.Volume for s in core.Solids) - plan * (10.0 - 2 * eps)) < 1e-6

    def test_one_ball_where_concave_edges_meet(self, geo, Part, App):
        """A cube with one octant removed has three concave edges meeting at its center: six edge
        ends, four distinct points."""
        cube = Part.makeBox(10.0, 10.0, 10.0).cut(
            Part.makeBox(5.0, 5.0, 5.0, App.Vector(5.0, 5.0, 5.0)))
        assert len(geo.concave_edges(cube)) == 3
        assert len(geo.ball_centers(cube)) == 4
        assert geo.inner_offset(cube, 0.0005).isValid()

    def test_a_cut_that_lost_a_deep_point_is_suspect(self, geo, Part, App):
        core = Part.Compound([Part.makeBox(1.0, 1.0, 1.0)])
        assert geo._suspect(core, [App.Vector(0.5, 0.5, 0.5)]) is None
        assert 'lost 1 of 1' in geo._suspect(core, [App.Vector(5.0, 5.0, 5.0)])

    def test_material_left_on_the_boundary_is_suspect(self, hull, geo, Part):
        """A 'core' that is the solid itself touches the boundary and is 2 mm deep at its center:
        material the cut should have removed, not an artifact."""
        box = Part.makeBox(4.0, 4.0, 4.0)
        boundary = Part.Compound(box.Faces)
        core = Part.Compound([box])
        assert 'reaches 2 mm deep' in geo._suspect(core, [], boundary, 0.5)
        assert geo._suspect(Part.Compound([hull.shrink(box, 0.5)]), [], boundary, 0.5) is None

    def test_too_thin_gives_none(self, geo, Part):
        assert geo.inner_offset(Part.makeBox(10.0, 0.5, 3.0), 0.0003) is None


class TestReaches(object):
    """Residues of known depth. Material of a tool within a ball of radius `r` around a boundary
    point reaches exactly `r` deep when the point is on a face or a concave edge, and
    `r sin(a / 2)` deep on a convex edge of dihedral angle `a`: depth is at most the distance to
    the point, and on a convex edge it grows along the bisector at `sin(a / 2)` per unit. Each is
    tried 1% either side of the threshold."""

    EPS = 0.01

    def _verdicts(self, geo, Part, App, solid, point, scale):
        core = geo.inner_offset(solid, self.EPS / 1000.0)
        out = []
        for k in (0.99, 1.01):
            residue = solid.common(Part.makeSphere(k * self.EPS * scale, point))
            out.append(geo.reaches(residue, core) <= geo.TOUCH_TOL_M)
        return out

    def test_on_a_face(self, geo, Part, App):
        got = self._verdicts(geo, Part, App, Part.makeBox(10.0, 4.0, 3.0),
                             App.Vector(5.0, 2.0, 3.0), 1.0)
        assert got == [False, True]

    def test_on_a_convex_edge(self, geo, Part, App):
        scale = 1.0 / math.sin(math.pi / 4.0)
        got = self._verdicts(geo, Part, App, Part.makeBox(10.0, 4.0, 3.0),
                             App.Vector(5.0, 4.0, 3.0), scale)
        assert got == [False, True]

    def test_on_a_concave_edge(self, geo, Part, App):
        got = self._verdicts(geo, Part, App, _ell(Part, App), App.Vector(5.0, 5.0, 5.0), 1.0)
        assert got == [False, True]

    def test_an_uncut_rib_wholly_containing_the_offset_reaches(self, geo, Part, App):
        box = Part.makeBox(10.0, 4.0, 3.0)
        core = geo.inner_offset(box, self.EPS / 1000.0)
        whole = Part.makeBox(12.0, 6.0, 5.0, App.Vector(-1.0, -1.0, -1.0))
        assert geo.reaches(whole, core) <= geo.TOUCH_TOL_M

    def test_the_point_shortcut_agrees_with_the_kernel(self, geo, Part, App):
        box = Part.makeBox(10.0, 4.0, 3.0)
        core = geo.inner_offset(box, self.EPS / 1000.0)
        whole = Part.makeBox(12.0, 6.0, 5.0, App.Vector(-1.0, -1.0, -1.0))
        assert geo.reaches(whole, core) == 0.0
        assert geo.reaches(whole, core, probes=0) <= geo.TOUCH_TOL_M

    def test_a_shape_resting_on_the_tool_is_not_inside_the_offset(self, geo, Part, App):
        box = Part.makeBox(10.0, 4.0, 3.0)
        core = geo.inner_offset(box, self.EPS / 1000.0)
        outside = Part.makeBox(10.0, 4.0, 3.0, App.Vector(0.0, 0.0, 3.0))
        assert abs(geo.reaches(outside, core) * 1000.0 - self.EPS) < 1e-9


class TestJudgeCut(object):
    """IP-FC-171's verdict, solid by solid. A block is cut by a two-solid tool: two 2 mm slots.
    Cut by the whole tool, the cavity sits exactly `eps` from both offsets; cut with the second slot
    1% short of `eps` too narrow, only that slot's solid is reached, and a slot too thin to have an
    offset is reported as `None` and so can never be flagged."""

    EPS = 0.01

    def _tool(self, Part, App, width=2.0):
        return Part.Compound([Part.makeBox(2.0, 10.0, 5.0, App.Vector(2.0, 0.0, 0.0)),
                              Part.makeBox(width, 10.0, 5.0, App.Vector(6.0, 0.0, 0.0))])

    def test_a_clean_cut_is_eps_from_every_offset(self, geo, Part, App):
        tool = self._tool(Part, App)
        cores = [geo.inner_offset(s, self.EPS / 1000.0) for s in tool.Solids]
        cavity = Part.makeBox(10.0, 10.0, 5.0).cut(tool)
        judged = geo.judge_cut(cavity, cores)
        assert [k for k, _d in judged] == [0, 1]
        assert all(abs(d * 1000.0 - self.EPS) < 1e-9 for _k, d in judged)

    def test_a_cut_left_short_is_flagged_in_its_own_solid_only(self, geo, Part, App):
        tool = self._tool(Part, App)
        cores = [geo.inner_offset(s, self.EPS / 1000.0) for s in tool.Solids]
        short = Part.Compound([tool.Solids[0],
                               Part.makeBox(2.0 - 1.01 * self.EPS, 10.0, 5.0,
                                            App.Vector(6.0, 0.0, 0.0))])
        cavity = Part.makeBox(10.0, 10.0, 5.0).cut(short)
        flagged = [k for k, d in geo.judge_cut(cavity, cores) if d <= geo.TOUCH_TOL_M]
        assert flagged == [1]

    def test_a_solid_with_no_offset_is_none(self, geo, Part, App):
        tool = self._tool(Part, App, width=0.015)
        cores = [geo.inner_offset(s, self.EPS / 1000.0) for s in tool.Solids]
        assert cores[1] is None
        judged = geo.judge_cut(Part.makeBox(10.0, 10.0, 5.0).cut(tool), cores)
        assert list(judged[1]) == [1, None]                   # the bridge returns tuples as lists
