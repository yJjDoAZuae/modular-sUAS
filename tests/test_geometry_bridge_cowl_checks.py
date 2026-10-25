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

#: Outer radius, wall and height of the test tube, in millimeters. The wall is the cowl's own
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

    def test_the_sample_count_comes_from_the_section_not_from_a_constant(self, cci, Part):
        """IP-WTM-25. A tube ten times round gets ten times the samples, so the spacing in
        millimeters -- the thing the 0.6 mm wall is measured in -- stays put."""
        small = (Part.makeCylinder(20.0, HEIGHT).cut(Part.makeCylinder(20.0 - WALL, HEIGHT)))
        large = (Part.makeCylinder(200.0, HEIGHT).cut(Part.makeCylinder(200.0 - WALL, HEIGHT)))
        n_small = cci.wall_thickness(small, HEIGHT / 2.0, WALL, 0.01)[0]
        n_large = cci.wall_thickness(large, HEIGHT / 2.0, WALL, 0.01)[0]
        assert n_small == pytest.approx(2.0 * math.pi * 20.0 / cci.WALL_ARC, rel=0.02)
        assert n_large / n_small == pytest.approx(10.0, rel=0.02)

    def test_a_short_section_is_sampled_finer_than_asked_never_coarser(self, cci, Part):
        """`WALL_MIN` is a floor on the count, so on a small section it buys a spacing finer than
        `WALL_ARC`. Which way the clamp errs is the whole of its safety: finer is harmless, coarser
        would silently undo the fix."""
        small = (Part.makeCylinder(5.0, HEIGHT).cut(Part.makeCylinder(5.0 - WALL, HEIGHT)))
        n = cci.wall_thickness(small, HEIGHT / 2.0, WALL, 0.01)[0]
        assert n == cci.WALL_MIN
        assert 2.0 * math.pi * 5.0 / n < cci.WALL_ARC

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


#: A pocket milled into the tube's outer face: `POCKET_WIDTH` mm around, `POCKET_DEPTH` mm deep,
#: full height. Both are **absolute**, so they stay the same size as the tube grows -- which is the
#: property that makes this model the real mechanism rather than merely a thin spot. A cowl's slot
#: mouths and rib flanks are absolute too (`2 * n_p * w` = 1.2 mm of the rib gap does not scale with
#: `U` at all), so a fixed sample count spends proportionally fewer samples on them as `U` rises.
POCKET_WIDTH = 1.2
POCKET_DEPTH = 0.2


def pocketed_tube(Part, App, r_outer):
    """A tube of known wall with one pocket milled into its **outer** face.

    The thinnest wall is exactly `WALL - POCKET_DEPTH`, wherever the sampling happens to land. The
    pocket is on the outside deliberately: the inner loop stays a plain circle with no concave
    turn anywhere, which isolates the sparse-sampling error from everything to do with corners.
    """
    tube = Part.makeCylinder(r_outer, HEIGHT).cut(Part.makeCylinder(r_outer - WALL, HEIGHT))
    cutter = Part.makeBox(5.0, POCKET_WIDTH, 3.0 * HEIGHT,
                          App.Vector(r_outer - POCKET_DEPTH, -0.5 * POCKET_WIDTH, -HEIGHT))
    out = tube.cut(cutter)
    assert len(out.Solids) == 1
    return out


def notched_tube(Part, App, r_outer, width=POCKET_WIDTH, depth=POCKET_DEPTH):
    """A tube whose **inner** contour dips outward into the wall and back, over `width` mm.

    This is the one that models the real section, and the difference from `pocketed_tube` is not
    cosmetic: `check_cowl_interior.wall_thickness`'s own docstring says the wall "follows the notch
    in and back out and the inner contour dips with it", so a cowl's concave turns are on the
    **inner** loop -- and the selected measure looks for reflex turns there and nowhere else. A
    pocket on the outer face leaves the inner loop convex everywhere, so it excludes no samples at
    all and any test of the exclusion built on it is vacuous.

    The thinnest wall is exactly `WALL - depth`.
    """
    r_inner = r_outer - WALL
    tube = Part.makeCylinder(r_outer, HEIGHT).cut(Part.makeCylinder(r_inner, HEIGHT))
    cutter = Part.makeBox(depth + 1.0, width, 3.0 * HEIGHT,
                          App.Vector(r_inner - 1.0, -0.5 * width, -HEIGHT))
    out = tube.cut(cutter)
    assert len(out.Solids) == 1
    return out


class TestWallThicknessSampling:
    """IP-WTM-25: the circumferential sampling is a spacing derived per station, not a constant.

    It was a fixed 240 inner samples with the outer loop at eight times that. A cowl's perimeter
    grows roughly linearly with `U` while its wall stays an absolute 0.6 mm, so that count bought a
    spacing proportional to the part -- 1.8 mm on a `tail_shell` section at `U` = 1 and 8.7 mm at
    `U` = 4, against the wall it was measuring.
    """

    def test_a_fixed_width_thin_spot_is_found_at_every_section_size(self, cci, Part, App):
        """The property the gate needs and a fixed count cannot give it: the same answer on a
        section twenty times round as on a small one, because the defect is the same size on both.
        """
        for r in (10.0, 50.0, 200.0):
            got = cci.wall_thickness(pocketed_tube(Part, App, r), HEIGHT / 2.0, WALL, 0.01)
            assert got is not None, 'r = %.0f gave no section' % r
            assert got[2] == pytest.approx(WALL - POCKET_DEPTH, abs=1e-3), 'r = %.0f' % r

    def test_a_coarse_spacing_misses_part_of_that_same_thin_spot(self, cci, Part, App):
        """**The converse, measured rather than assumed.** A cause needs its converse tested, so
        `arc` is a parameter: handed a spacing twice the pocket's own width, the function reads the
        wall 0.0486 mm thicker than it is -- nearly five times `WALL_TOL` of thinning simply not
        seen. At the default spacing the same geometry reads the pocket exactly.

        Measured at `r` = 200, where a coarse count is unambiguously coarse: the floor on the
        sample count keeps smaller sections fine whatever is asked for.
        """
        part = pocketed_tube(Part, App, 200.0)
        fine = cci.wall_thickness(part, HEIGHT / 2.0, WALL, 0.01)[2]
        coarse = cci.wall_thickness(part, HEIGHT / 2.0, WALL, 0.01, 2.5)[2]
        assert fine == pytest.approx(WALL - POCKET_DEPTH, abs=1e-3)
        assert coarse > fine + 4.0 * 0.01
        assert coarse < WALL, 'it should still see some of the pocket, just not its floor'

    def test_the_two_sampling_errors_push_opposite_ways_and_both_are_real(self, cci, Part, App):
        """Recorded because it is the trap in reasoning about this, and `wall_measure.density` says
        so in prose: a coarse discretization both **under**-reports thinness, by sampling the inner
        loop too sparsely to land on a thin spot, and **over**-reports it, by measuring to outer
        chords that cut inside the true boundary. This geometry isolates the first -- a smooth tube
        has no chord error worth the name at these radii -- so the coarse reading here is too
        *thick*. On the real sections the second dominates and the coarse reading is too *thin*:
        measured on the saved `tail_shell` at `U` = 4, a 1.24 mm spacing reads 0.4454 mm where
        0.125 mm reads 0.5675 mm. A test that only ever saw one direction would license the wrong
        conclusion about the other.
        """
        part = pocketed_tube(Part, App, 200.0)
        coarse = cci.wall_thickness(part, HEIGHT / 2.0, WALL, 0.01, 2.5)[2]
        fine = cci.wall_thickness(part, HEIGHT / 2.0, WALL, 0.01)[2]
        assert coarse > fine, 'on a smooth tube the sparse-sampling error is the only one'

    def test_the_sample_count_is_derived_and_clamped_at_both_ends(self, cci):
        """`wall_samples` alone, with no geometry: the arithmetic and both clamps."""
        assert cci.wall_samples(1000.0) == 8000
        assert cci.wall_samples(1000.0, 0.5) == 2000
        assert cci.wall_samples(1.0) == cci.WALL_MIN
        assert cci.wall_samples(1.0e9) == cci.WALL_MAX


class TestStationMeasures:
    """IP-WTM-10: the selected measure reported beside the incumbent, from one section."""

    def test_the_incumbent_entry_is_what_wall_thickness_returns(self, cci, tube):
        """The compatibility the item asks for: the leading figure is unchanged, so a reading can
        still be compared against every one recorded before the second measure existed."""
        z = HEIGHT / 2.0
        both = cci.station_measures(tube, z, WALL, 0.01)
        assert tuple(both['incumbent']) == tuple(cci.wall_thickness(tube, z, WALL, 0.01))

    def test_both_measures_read_a_uniform_wall_as_its_own_thickness(self, cci, tube):
        both = cci.station_measures(tube, HEIGHT / 2.0, WALL, 0.01)
        assert both['selected'] == pytest.approx(WALL, abs=0.01)
        assert both['incumbent'][2] == pytest.approx(WALL, abs=0.01)
        assert both['samples_per_loop'] > 0

    @pytest.mark.parametrize('width', [2.0, 1.2, 0.8, 0.4])
    def test_the_selected_measure_never_reports_more_thinness_than_the_incumbent(self, cci, Part,
                                                                                App, width):
        """**A structural identity, not a tolerance.** The selected measure minimizes over a
        *subset* of the incumbent's distances -- the samples not within 0.30 mm of a concave turn
        of the inner loop -- so its minimum can only be larger or equal. A violation means the two
        are no longer reading one point set, which is precisely the defect an earlier version of
        that measure had (0.04806 against 0.04689 mm on a real `tail_shell`).

        Swept across notch widths because the margin is where the identity could fail: at 0.8 mm
        the two differ, measured, by 0.0002 mm in the permitted direction, and a version that
        sampled differently would have no reason to respect the sign of that.
        """
        part = notched_tube(Part, App, 50.0, width=width)
        both = cci.station_measures(part, HEIGHT / 2.0, WALL, 0.01)
        assert both['selected'] is not None
        assert both['selected'] >= both['incumbent'][2] - 1e-12
        assert both['selected_samples'] < both['incumbent'][0], \
            'an inner notch has concave turns, so some samples must have been excluded'

    def test_excluding_the_corners_does_not_remove_this_thin_spot(self, cci, Part, App):
        """The informative half of the selected measure's design, and it reports the same way the
        corpus did. `corner_excluded_min` was adopted on the theory that the incumbent's failure is
        a nearest-point distance taken *at* a concave corner; its own docstring says it fails
        informatively if excluding them removes the places a wall is thinnest. Here it does not:
        the thinning sits at the notch floor's ends, where the outer surface curves away, which is
        a real wall and not a corner artifact -- so both measures report it, and that matches the
        corpus result that the tail's thin spot is not at a corner and no corner-based fix reaches
        it.
        """
        part = notched_tube(Part, App, 50.0, width=1.2)
        both = cci.station_measures(part, HEIGHT / 2.0, WALL, 0.01)
        assert both['incumbent'][2] == pytest.approx(0.3968, abs=5e-4)
        assert both['selected'] == pytest.approx(both['incumbent'][2], abs=5e-4)
        assert both['selected'] < WALL - 0.19, 'the thinning must survive the exclusion'

    def test_a_section_with_no_loop_pair_reports_no_selected_figure(self, cci, Part):
        """The one-loop strip branch feeds the incumbent a `2A/P` estimate and the selected measure
        nothing, because that measure is defined on an inner/outer pair. Mixing the two would make
        the second figure a blend of two estimators and break the subset identity above."""
        rod = Part.makeCylinder(R_OUTER, HEIGHT)
        both = cci.station_measures(rod, HEIGHT / 2.0, WALL, 0.01)
        assert both['selected'] is None
        assert both['selected_samples'] == 0
        assert both['incumbent'][2] == pytest.approx(R_OUTER, abs=0.01)

    def test_a_broken_ring_returns_none_from_both(self, cci, tube, Part, App):
        """The annulus guard is upstream of either measure, so neither can report a thickness for a
        section that is not a wall section."""
        z = HEIGHT / 2.0
        a = Part.makeBox(4.0, 4.0, 10.0, App.Vector(R_OUTER - 2.0, -2.0, z - 5.0))
        b = Part.makeBox(4.0, 4.0, 10.0, App.Vector(-R_OUTER - 2.0, -2.0, z - 5.0))
        broken = tube.cut(a).cut(b)
        assert cci.station_measures(broken, z, WALL, 0.01) is None


class TestSeamEdgesAreNotListedTwice:
    """A vendor assumption `boolean_edges.anomalous_edges` was built on, put to the kernel — and
    refuted. Kept because it is what the classifier's design now rests on.

    That function has to tell a periodic surface's closing **seam** from a genuine **open
    boundary**, and both present as "one adjacent face" to every cheap test: `face_adjacency`
    records a face index once per group, and the kernel's own `ancestorsOfType` returns *distinct*
    ancestors. The first version counted how many times that one face carries the edge, assuming
    `Face.Edges` lists a seam once per orientation.

    **It does not.** Measured here on a cylinder, whose lateral face certainly has a seam: the seam
    edge appears exactly **once**, like any other edge. So the occurrence count cannot carry the
    distinction, and `anomalous_edges` uses the surface's periodicity instead — a seam can only
    exist on a periodic surface. This test exists so that if the vendor ever starts listing seams
    twice, the fact is noticed here rather than inferred from a classification going quiet.
    """

    def lateral_face(self, cyl, r=5.0, h=10.0):
        """The curved face, picked by area. **Not by `type(...).__name__`**, which across the test
        bridge is the proxy's class rather than the vendor's, and not by `isUPeriodic`, which the
        bridge cannot return from a surface proxy. On a cylinder the lateral area `2*pi*r*h` and
        the cap area `pi*r^2` are exact, so area identifies it without ambiguity."""
        wanted = 2.0 * math.pi * r * h
        faces = [f for f in cyl.Faces if abs(f.Area - wanted) < 1e-6]
        assert len(faces) == 1, 'expected exactly one lateral face of area %.3f' % wanted
        return faces[0]

    def test_a_cylinders_lateral_face_lists_its_seam_edge_only_once(self, Part):
        """The measurement that refuted the assumption. One occurrence, not two."""
        face = self.lateral_face(Part.makeCylinder(5.0, 10.0))
        seams = [e for e in face.Edges if abs(e.Length - 10.0) < 1e-6]
        assert len(seams) == 1, (
            'if the vendor now lists a seam twice, anomalous_edges could use the occurrence count '
            'again -- see EDGE_SEAM')

    def test_so_a_seam_is_topologically_identical_to_an_open_boundary_here(self, Part):
        """Why periodicity had to become the discriminator: on the counts alone, a cylinder's seam
        and a hole in a shell are the same observation."""
        face = self.lateral_face(Part.makeCylinder(5.0, 10.0))
        seam = [e for e in face.Edges if abs(e.Length - 10.0) < 1e-6][0]
        owners = [f for f in Part.makeCylinder(5.0, 10.0).Faces
                  if any(abs(e.Length - seam.Length) < 1e-6 and abs(e.Area - seam.Area) < 1e-6
                         for e in f.Edges)]
        assert len(owners) == 1, 'one face carries it, exactly as an open boundary would'


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
