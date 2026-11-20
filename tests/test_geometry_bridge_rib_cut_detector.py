"""IP-FC-169: the rib-cut detector on residues of known depth, either side of the threshold.

`cowl_interior_surface.md` section 7.2 sets the qualification criteria for a failed-rib-cut detector;
this file is the third: it must flag residue at and above the wall tolerance and pass residue below
it. Real cowls cannot supply that -- the residue a real failed cut leaves is the unknown -- so the
cases are a box cavity and a slab tool, where the residue depth past the slab's face is exactly what
the test builds. Box booleans are the kernel's easiest case, and each fixture's volume is checked
against its closed form before it is used, so the fixture is known to be what it claims.

The threshold is `WALL_TOL_M` = 0.01 mm. The detector places each face's copy `eps + clearance` deep
so the flag fires exactly there; 0.009 and 0.011 mm straddle it by a tenth of the tolerance.

Fixtures are kernel geometry and so millimeters, as in the other bridge tests.
"""
import pytest

from conftest import requires_freecad                                       # noqa: E402

pytestmark = requires_freecad

#: The slab tool: 10 x 2 x 10 mm at the origin. Its y = 0 face is the one residue is built behind.
TOOL = (10.0, 2.0, 10.0)

#: The smooth interior the tool is cut from: it contains the slab in x and y and is crossed by it in
#: z, so the cut leaves one connected cavity with a slot through it.
BODY_ORIGIN = (-5.0, -5.0, 1.0)
BODY = (20.0, 12.0, 8.0)


def _cavity(Part, App, residue_mm):
    """The body cut by the slab with its y = 0 face pulled back by `residue_mm`, or uncut for
    `None`. Returns `(cavity, tool)`; the tool is always the full slab."""
    body = Part.makeBox(BODY[0], BODY[1], BODY[2], App.Vector(*BODY_ORIGIN))
    tool = Part.makeBox(*TOOL)
    if residue_mm is None:
        return body, tool
    cutter = Part.makeBox(TOOL[0], TOOL[1] - residue_mm, TOOL[2],
                          App.Vector(0.0, residue_mm, 0.0))
    cavity = body.cut(cutter)
    # The slab crosses the body's whole z range (1..9), so the cut removes x 10 by z 8 by
    # (2 - residue) of it, and the fixture is checked against that before it is trusted.
    expected = BODY[0] * BODY[1] * BODY[2] - TOOL[0] * BODY[2] * (TOOL[1] - residue_mm)
    assert abs(cavity.Volume - expected) < 1e-6
    assert len(cavity.Solids) == 1
    return cavity, tool


@pytest.fixture
def det(fc):
    return fc.module('rib_cut_detector')


class TestQualification(object):

    def test_a_correct_cut_raises_no_flag_and_leaves_nothing_unexamined(self, det, Part, App):
        cavity, tool = _cavity(Part, App, 0.0)
        rec = det.examine(cavity, tool)
        assert rec['counts']['flagged'] == 0
        assert rec['counts']['untestable'] == 0
        assert rec['unplaced_area_mm2'] == 0.0

    def test_an_uncut_tool_is_flagged(self, det, Part, App):
        cavity, tool = _cavity(Part, App, None)
        rec = det.examine(cavity, tool)
        assert rec['counts']['flagged'] > 0

    def test_residue_just_below_the_tolerance_passes(self, det, Part, App):
        cavity, tool = _cavity(Part, App, 0.009)
        rec = det.examine(cavity, tool)
        assert rec['counts']['flagged'] == 0

    def test_residue_just_above_the_tolerance_is_flagged(self, det, Part, App):
        cavity, tool = _cavity(Part, App, 0.011)
        rec = det.examine(cavity, tool)
        assert rec['counts']['flagged'] >= 1

    def test_residue_well_above_the_tolerance_is_flagged_on_the_face_it_is_behind(
            self, det, Part, App):
        cavity, tool = _cavity(Part, App, 0.5)
        rec = det.examine(cavity, tool)
        flagged = [f for f in rec['faces'] if f['verdict'] == 'flagged']
        assert flagged
        # The residue is behind the y = 0 face only; a face elsewhere flagging would be a
        # false positive the threshold argument does not allow.
        for f in flagged:
            assert f['z_mm'] == [0.0, 10.0]


#: A triangular prism with a 30-degree corner, matching the real tool's shallowest cut plane: its
#: long face meets the base at 30 degrees, so the faces next to it are not square to it. The
#: threshold argument says nothing about angles -- residue below the threshold lies within `eps`
#: of the tool boundary, and every copy is certified `eps + clearance` from all of it -- and this is
#: where that is tested.
WEDGE_LEG = 8.0
WEDGE_RISE = WEDGE_LEG * 0.5773502691896257          # tan(30 degrees)

#: The long face's outward unit normal, (-sin 30, cos 30).
WEDGE_NORMAL = (-0.5, 0.8660254037844386)


def _wedge_cavity(Part, App, residue_mm):
    """The body cut by the wedge moved `residue_mm` inward across its long face.

    Moving the whole tool leaves residue behind the long face exactly `residue_mm` deep and
    shallower residue behind the faces next to it, so the deepest residue anywhere is
    `residue_mm`. Returns `(cavity, tool)`; the tool is always the unmoved wedge.
    """
    body = Part.makeBox(BODY[0], BODY[1] + 3.0, BODY[2], App.Vector(*BODY_ORIGIN))
    corners = [App.Vector(0.0, 0.0, 0.0), App.Vector(WEDGE_LEG, 0.0, 0.0),
               App.Vector(WEDGE_LEG, WEDGE_RISE, 0.0), App.Vector(0.0, 0.0, 0.0)]
    tool = Part.Face(Part.makePolygon(corners)).extrude(App.Vector(0.0, 0.0, TOOL[2]))
    shift = App.Vector(-WEDGE_NORMAL[0] * residue_mm, -WEDGE_NORMAL[1] * residue_mm, 0.0)
    cavity = body.cut(tool.translated(shift))
    assert len(cavity.Solids) == 1
    return cavity, tool


class TestTheThresholdIsExact(object):
    """A twentieth of the tolerance either side of it, on a square edge and on a 30-degree one."""

    def test_box_just_below(self, det, Part, App):
        cavity, tool = _cavity(Part, App, 0.0095)
        assert det.examine(cavity, tool)['counts']['flagged'] == 0

    def test_box_just_above(self, det, Part, App):
        cavity, tool = _cavity(Part, App, 0.0105)
        assert det.examine(cavity, tool)['counts']['flagged'] >= 1

    def test_wedge_correct_cut(self, det, Part, App):
        cavity, tool = _wedge_cavity(Part, App, 0.0)
        assert det.examine(cavity, tool)['counts']['flagged'] == 0

    def test_wedge_just_below(self, det, Part, App):
        cavity, tool = _wedge_cavity(Part, App, 0.0095)
        assert det.examine(cavity, tool)['counts']['flagged'] == 0

    def test_wedge_just_above(self, det, Part, App):
        cavity, tool = _wedge_cavity(Part, App, 0.0105)
        assert det.examine(cavity, tool)['counts']['flagged'] >= 1


class TestNormalSide(object):
    """The containment reading both certificates rest on, on solids where every answer is known.

    Ray casting (`isInside`) was measured misclassifying points well clear of a boundary, so the
    detector reads containment from the outward normals at the nearest boundary point instead.
    Each case here puts that nearest point somewhere specific: inside a face, on a convex edge, on
    a concave edge -- where the reading has to flip -- on convex and concave vertices, and on a
    saddle vertex, where it must decline.
    """

    def _box(self, Part, det):
        box = Part.makeBox(10.0, 10.0, 10.0)
        return box, det._shells(box)

    def _ell(self, Part, App, det):
        """An L: a 10 x 10 x 10 block with the x > 5, y > 5 quarter removed, so the edge at
        x = 5, y = 5 is concave."""
        ell = Part.makeBox(10.0, 10.0, 10.0).cut(
            Part.makeBox(5.0, 5.0, 10.0, App.Vector(5.0, 5.0, 0.0)))
        return ell, det._shells(ell)

    def test_near_a_face(self, det, Part, App):
        _box, sh = self._box(Part, det)
        assert det.normal_side(sh, App.Vector(5.0, 5.0, 9.9)) is True
        assert det.normal_side(sh, App.Vector(5.0, 5.0, 10.1)) is False

    def test_outside_a_convex_edge(self, det, Part, App):
        _box, sh = self._box(Part, det)
        # Diagonally off the edge x = 10, y = 10: nearest point is on the edge.
        assert det.normal_side(sh, App.Vector(10.1, 10.1, 5.0)) is False

    def test_outside_a_sharp_convex_edge_with_mixed_projections(self, det, Part, App):
        """A 30-degree wedge: outside its sharp edge the offset can point against one face's
        normal while still being outside, which is the case the cone solve exists for."""
        tri = Part.Face(Part.makePolygon([App.Vector(0, 0, 0), App.Vector(8, 0, 0),
                                          App.Vector(8, 4.618802153517006, 0),
                                          App.Vector(0, 0, 0)])).extrude(App.Vector(0, 0, 10))
        sh = det._shells(tri)
        assert det.normal_side(sh, App.Vector(-0.1, -0.01, 5.0)) is False
        assert det.normal_side(sh, App.Vector(4.0, 1.0, 5.0)) is True

    def test_inside_a_concave_edge(self, det, Part, App):
        _ell, sh = self._ell(Part, App, det)
        # Inside the L, diagonally toward the concave edge at (5, 5): nearest point is the edge.
        assert det.normal_side(sh, App.Vector(4.9, 4.9, 5.0)) is True
        # Outside, in the removed quarter, near the same edge: nearest point is a face.
        assert det.normal_side(sh, App.Vector(5.2, 5.1, 5.0)) is False

    def test_agrees_with_ray_casting_where_ray_casting_is_trustworthy(self, det, Part, App):
        ell, sh = self._ell(Part, App, det)
        for x in (0.5, 2.5, 4.5, 5.5, 7.5, 9.5):
            for y in (0.5, 4.5, 5.5, 9.5):
                q = App.Vector(x, y, 5.0)
                got = det.normal_side(sh, q)
                if got is not None:
                    assert got == ell.isInside(q, 1e-7, False), (x, y)

    def test_outside_a_convex_vertex(self, det, Part, App):
        """Measured on the dosed cavity 2026-11-19: copies 0.35 mm and 0.56 mm clear of it,
        whose every point was nearest a cavity vertex, read undecided and so flagged."""
        _box, sh = self._box(Part, det)
        assert det.normal_side(sh, App.Vector(10.1, 10.1, 10.1)) is False
        assert det.normal_side(sh, App.Vector(-0.2, -0.1, 10.3)) is False

    def test_inside_a_concave_vertex(self, det, Part, App):
        """A block with the x, y, z > 5 octant removed: the vertex at (5, 5, 5) is concave, and
        a point inside the block diagonally toward it is nearest that vertex."""
        notched = Part.makeBox(10.0, 10.0, 10.0).cut(
            Part.makeBox(5.0, 5.0, 5.0, App.Vector(5.0, 5.0, 5.0)))
        sh = det._shells(notched)
        q = App.Vector(4.9, 4.9, 4.9)
        assert Part.Vertex(q).distToShape(sh)[2][0][3] == 'Vertex'
        assert det.normal_side(sh, q) is True
        assert notched.isInside(q, 1e-7, False) is True

    def test_the_empty_ball_decides_where_the_point_itself_does_not(self, det, Part, App):
        """`ball_side` reads probes within the point's distance to the boundary, all of which are
        on its side. Off a box corner and off the notch's concave corner, its probes must give the
        known answers -- through edges and faces, not the vertex rule."""
        _box, sh = self._box(Part, det)
        assert det.ball_side(sh, App.Vector(10.1, 10.1, 10.1)) is False
        notched = Part.makeBox(10.0, 10.0, 10.0).cut(
            Part.makeBox(5.0, 5.0, 5.0, App.Vector(5.0, 5.0, 5.0)))
        assert det.ball_side(det._shells(notched), App.Vector(4.9, 4.9, 4.9)) is True

    def test_every_probe_stays_inside_the_empty_ball(self, det, Part, App):
        _box, sh = self._box(Part, det)
        q = App.Vector(10.1, 10.1, 10.1)
        d = Part.Vertex(q).distToShape(sh)[0]
        assert 0.0 < det.BALL_FRACTION < 1.0
        for u in det._probe_directions(sh, q):
            assert abs(u.Length - 1.0) < 1e-12
            assert (u * (det.BALL_FRACTION * d)).Length < d

    def test_a_saddle_vertex_is_undecided_not_guessed(self, det, Part, App):
        """The top of the L's concave edge, (5, 5, 10): the edge down is concave and the edges
        along the top are convex, so neither half-space rule holds."""
        _ell, sh = self._ell(Part, App, det)
        vertex = [v for v in sh.Vertexes
                  if (v.Point - App.Vector(5.0, 5.0, 10.0)).Length < 1e-9][0]
        for w in (App.Vector(0.1, 0.1, 0.1), App.Vector(-0.1, -0.1, -0.1)):
            assert det._vertex_side(sh, vertex, w) is None
