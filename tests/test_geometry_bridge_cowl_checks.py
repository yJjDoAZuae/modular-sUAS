"""IP-GB-21: `check_cowl_interior`'s measurement functions, tested on geometry with exact answers.

The five private helpers this item names — `_check_slope`, `_Polyline`, `_thin_stations`,
`station_floor`, `section_regions` — are covered in `test_geometry_bridge_freecad.py`. This file
covers the rest of the item's scope: `_is_annulus`, `wall_thickness` and `in_plane_width`, the
functions whose results exist today only as printed lines inside the checker's `main()`.

**Everything here runs on a tube or a slab, not on a cowl.** A `tail_shell` build is 1 200 to
4 900 s and gives no exact answer to compare against; a tube of known wall thickness gives one
exactly, and the functions under test do not know what shape they were handed. That is this
project's own rule about testing a method at a fraction of its cost, and it is what makes these
assertions equalities rather than ranges.

`in_plane_width` in particular is derived trigonometry, not a measurement, so its answers are
exact: a slab of thickness `d` whose unit normal is `n` meets a horizontal plane in a strip of
width `d / hypot(n.x, n.y)`. Its docstring gives the tail's real case — a 30-degree rotation takes
the normal to (0, -0.5, 0.866), so `hypot` is 0.5 and a 0.1 mm cut is 0.2 mm wide in the layer
plane. That is checked here against a synthetic slab at the same angle.

See doc/architecture/geometry_bridge.md §6.1 and doc/design/cowl_interior_surface.md §6.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from geometry_bridge.remote_errors import PreconditionFailed                # noqa: E402

from conftest import requires_freecad                                       # noqa: E402

pytestmark = requires_freecad

#: Outer radius, wall and height of the test tube, in millimetres. The wall is the cowl's own
#: 0.6 mm so the numbers read on the same scale as the real part's.
R_OUTER = 10.0
WALL = 0.6
HEIGHT = 20.0


@pytest.fixture
def tube(Part):
    """A straight tube: one solid, a known uniform wall, an annular section at every station."""
    outer = Part.makeCylinder(R_OUTER, HEIGHT)
    inner = Part.makeCylinder(R_OUTER - WALL, HEIGHT)
    out = outer.cut(inner)
    assert len(out.Solids) == 1
    return out


def _wires_at(shape, z, App):
    """The closed section wires of `shape` at height `z`."""
    return [w for w in shape.slice(App.Vector(0, 0, 1), z).items() if w.isClosed()]


class TestIsAnnulus:
    """One region with one hole, and nothing else, is a wall section."""

    def test_a_tube_section_is_an_annulus(self, cci, tube, App):
        assert cci._is_annulus(_wires_at(tube, HEIGHT / 2.0, App)) is True

    def test_a_solid_discs_section_is_not(self, cci, Part, App):
        """The converse that matters most: a disc is one region with **no** hole, so it has no
        wall and no thickness to report. Without this, `_is_annulus` returning `True` for
        everything would pass the test above."""
        rod = Part.makeCylinder(R_OUTER, HEIGHT)
        assert cci._is_annulus(_wires_at(rod, HEIGHT / 2.0, App)) is False

    def test_two_separate_rings_are_not_one_annulus(self, cci, Part, App):
        """Two regions, two holes. A wall that has come apart into separate rings is exactly the
        failure the ring classifier exists to catch."""
        a = Part.makeCylinder(R_OUTER, HEIGHT).cut(Part.makeCylinder(R_OUTER - WALL, HEIGHT))
        b = Part.makeCylinder(R_OUTER, HEIGHT, App.Vector(40.0, 0.0, 0.0))
        b_hole = Part.makeCylinder(R_OUTER - WALL, HEIGHT, App.Vector(40.0, 0.0, 0.0))
        pair = a.fuse(b.cut(b_hole))
        wires = _wires_at(pair, HEIGHT / 2.0, App)
        assert len(wires) == 4
        assert cci._is_annulus(wires) is False

    def test_an_open_arc_is_not_an_annulus(self, cci, tube, Part, App):
        """A ring broken open is the §7.1 failure: still one piece, no longer a ring."""
        notch = Part.makeBox(4.0, 4.0, HEIGHT + 2.0,
                             App.Vector(R_OUTER - 2.0, -2.0, -1.0))
        broken = tube.cut(notch)
        wires = _wires_at(broken, HEIGHT / 2.0, App)
        assert cci._is_annulus(wires) is False


class TestWallThickness:
    """A tube's wall is exactly `WALL` everywhere, so every sample has a known right answer."""

    def test_a_uniform_wall_reads_its_own_thickness(self, cci, tube):
        got = cci.wall_thickness(tube, HEIGHT / 2.0, WALL, 0.01)
        assert got is not None
        n, near, worst_low, median, worst_high = got
        assert n > 0
        assert near == n, '%d of %d samples landed outside 0.01 mm of %.2f' % (n - near, n, WALL)
        assert worst_low == pytest.approx(WALL, abs=0.01)
        assert median == pytest.approx(WALL, abs=0.01)
        assert worst_high == pytest.approx(WALL, abs=0.01)

    def test_a_thicker_wall_reads_thicker(self, cci, Part):
        """Pins that the function measures the wall rather than returning its `expect` argument."""
        thick = (Part.makeCylinder(R_OUTER, HEIGHT)
                 .cut(Part.makeCylinder(R_OUTER - 2.0, HEIGHT)))
        got = cci.wall_thickness(thick, HEIGHT / 2.0, 2.0, 0.01)
        assert got is not None
        _n, _near, worst_low, median, _worst_high = got
        assert median == pytest.approx(2.0, abs=0.01)
        assert worst_low == pytest.approx(2.0, abs=0.01)

    def test_a_wrong_expectation_is_reported_not_absorbed(self, cci, tube):
        """Asked for 2.0 mm on a 0.6 mm wall, no sample may count as near."""
        got = cci.wall_thickness(tube, HEIGHT / 2.0, 2.0, 0.01)
        assert got is not None
        n, near, _worst_low, median, _worst_high = got
        assert near == 0
        assert median == pytest.approx(WALL, abs=0.01)
        assert n > 0

    def test_a_station_outside_the_solid_returns_none(self, cci, tube):
        """The first documented `None` case: no closed loop at all at that station.

        "Fewer than two loops" in the docstring means *no* loops -- a station the solid does not
        reach. A station with exactly one loop is a different case, handled below.
        """
        assert cci.wall_thickness(tube, HEIGHT + 50.0, WALL, 0.01) is None

    def test_a_single_loop_section_is_measured_as_a_strip(self, cci, Part):
        """Not `None`: a one-loop section is treated as a thin strip and measured by `2A/P`.

        Worth pinning because it is easy to assume any non-annular section returns `None`. It does
        not, and for a wall piece that is right -- a C-shaped remnant of a ring really is a strip
        of the wall's own thickness. **But the estimator is only meaningful for a thin strip**: on
        a solid disc of radius 10, `2A/P` is 10.0, the radius, which is not a wall thickness and
        not a defect in the function either. §6.1 states the same limit for the area-based mean.
        """
        rod = Part.makeCylinder(R_OUTER, HEIGHT)
        got = cci.wall_thickness(rod, HEIGHT / 2.0, WALL, 0.01)
        assert got is not None
        n, near, _low, median, _high = got
        assert near == 0, 'a disc must not pass as a 0.6 mm wall'
        assert median == pytest.approx(R_OUTER, rel=1e-3)

    def test_a_ring_broken_into_one_arc_still_measures_correctly(self, cci, tube, Part, App):
        """A single radial slot leaves a C: one closed loop, so the strip estimator applies and
        gives the wall's true thickness. The annulus guard does not fire, and should not."""
        notch = Part.makeBox(4.0, 4.0, HEIGHT + 2.0, App.Vector(R_OUTER - 2.0, -2.0, -1.0))
        broken = tube.cut(notch)
        wires = _wires_at(broken, HEIGHT / 2.0, App)
        assert len(wires) == 1, 'a single slot should leave one C-shaped loop'
        assert cci._is_annulus(wires) is False
        got = cci.wall_thickness(broken, HEIGHT / 2.0, WALL, 0.01)
        assert got is not None
        _n, _near, _low, median, _high = got
        assert median == pytest.approx(WALL, abs=0.01)

    def test_a_ring_broken_into_two_arcs_returns_none(self, cci, tube, Part, App):
        """**The case the annulus guard exists for, and the one OQ-DES-CW26 is about.**

        Two opposing slots leave two separate arcs. Each arc's own boundary is a closed loop, so
        the section has two loops and the outer/inner pairing engages -- but the second loop is
        beside the first, not inside it, so the distance measured is the gap across the break and
        not a thickness. Measured on a real `tail_shell` at `U` = 3.0, that misreported a ring
        broken over 93 mm of 1 600 as a 0.355705 mm wall, and every build check passed it. `None`
        is the right answer.

        The guard only engages at two or more loops, which is why the one-arc case above is
        handled by the strip estimator instead and still reads correctly.

        **The slots must not run the full height.** Full-height slots split the tube into two
        separate solids, and `wall_thickness` loops over `wall.Solids` and measures each one on its
        own -- so each arc is a single-loop strip and reads a correct 0.586, with the guard never
        engaging. That is the function behaving properly on two separate pieces, and it is not the
        defect. The real case is **one** solid, still joined above and below, whose section comes
        apart only at this station; partial-height slots reproduce exactly that.
        """
        z = HEIGHT / 2.0
        a = Part.makeBox(4.0, 4.0, 10.0, App.Vector(R_OUTER - 2.0, -2.0, z - 5.0))
        b = Part.makeBox(4.0, 4.0, 10.0, App.Vector(-R_OUTER - 2.0, -2.0, z - 5.0))
        broken = tube.cut(a).cut(b)
        assert len(broken.Solids) == 1, 'the wall must stay one solid, as the real one does'
        wires = _wires_at(broken, z, App)
        assert len(wires) == 2, 'two opposing slots should leave two arcs at this station'
        assert cci._is_annulus(wires) is False
        assert cci.wall_thickness(broken, z, WALL, 0.01) is None


class TestInPlaneWidth:
    """Derived trigonometry: `d / hypot(n.x, n.y)`, so every answer is exact."""

    def test_a_vertical_cut_reads_its_own_thickness(self, cci, Part, App):
        """A **vertical** slab — one standing on edge, normal (1, 0, 0) — has `hypot` = 1, so the
        width is the cut thickness unchanged.

        Vertical means the slab's faces are vertical, not that it lies flat: a flat slab's normal
        is (0, 0, 1), `hypot` is 0, and the width would be infinite. That case is refused by name
        as precondition P4 rather than divided by zero — see
        `test_a_tool_lying_in_the_layer_plane_is_refused`.
        """
        slab = Part.makeBox(0.1, 20.0, 20.0, App.Vector(0.0, -10.0, 0.0))
        assert cci.in_plane_width(slab, 0.1) == pytest.approx(0.1, rel=1e-9)

    def test_a_tool_lying_in_the_layer_plane_is_refused(self, cci, Part, App):
        """Precondition P4. A flat slab's normal is vertical, so it has no horizontal component to
        divide by — it leaves no rib at all, and the build should have refused it earlier."""
        flat = Part.makeBox(20.0, 20.0, 0.1, App.Vector(-10.0, -10.0, 0.0))
        with pytest.raises(PreconditionFailed) as caught:
            cci.in_plane_width(flat, 0.1)
        assert 'layer plane' in str(caught.value)

    def test_a_thirty_degree_slab_cuts_twice_as_wide(self, cci, Part, App):
        """The tail's real case, from the function's own docstring: `rotate([30, 0, 0])` takes the
        normal to (0, -0.5, 0.866), `hypot` is 0.5, and a 0.1 mm cut is 0.2 mm wide."""
        slab = Part.makeBox(20.0, 20.0, 0.1, App.Vector(-10.0, -10.0, 0.0))
        slab.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 30.0)
        assert cci.in_plane_width(slab, 0.1) == pytest.approx(0.2, rel=1e-6)

    @pytest.mark.parametrize('degrees', [10.0, 30.0, 45.0, 60.0, 80.0])
    def test_the_width_follows_the_closed_form_at_every_angle(self, cci, Part, App, degrees):
        """Not just the one angle the docstring names. A rotation of `a` about x takes the normal
        from (0, 0, 1) to (0, -sin a, cos a), so the width is `d / sin a`."""
        slab = Part.makeBox(20.0, 20.0, 0.1, App.Vector(-10.0, -10.0, 0.0))
        slab.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), degrees)
        expect = 0.1 / math.sin(math.radians(degrees))
        assert cci.in_plane_width(slab, 0.1) == pytest.approx(expect, rel=1e-6)

    def test_the_width_is_independent_of_the_slabs_own_thickness(self, cci, Part, App):
        """`t_cut` is an argument, not a measurement -- which is the point the docstring makes:
        reading the width off the section would pass a notch cut to the wrong thickness."""
        slab = Part.makeBox(20.0, 20.0, 2.0, App.Vector(-10.0, -10.0, 0.0))
        slab.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 30.0)
        assert cci.in_plane_width(slab, 0.1) == pytest.approx(0.2, rel=1e-6)

    def test_a_tool_with_no_planar_face_is_refused_by_name(self, cci, Part):
        """A sphere is not a slab, so its thickness has no direction. The refusal must be the
        project's own exception, arriving as itself across the boundary."""
        with pytest.raises(PreconditionFailed) as caught:
            cci.in_plane_width(Part.makeSphere(5.0), 0.1)
        assert 'not a slab' in str(caught.value)
