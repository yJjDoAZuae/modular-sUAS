"""IP-WTM-1 and IP-WTM-2: the ground-truth fixtures, and the section extraction they feed.

**A fixture that claims to carry closed-form truth has to prove it**, or the whole screening rests
on an assumption -- and the reason this plan exists is that no measure here was ever checked against
a known answer. So these tests check the fixtures against the kernel: the patch really is `depth_m`
thinner, the rib really is `rise_m` thicker, the surfaces really are concentric cylinders, and the
truth function really agrees with the geometry it describes.

**Every figure here is SI since IP-FC-163**, which moved three kinds of assertion and not only the
names: a `Shape.Volume` now has to be read through `kern.volume_m3`, because the kernel's own
attribute is still mm3 and comparing it against a closed form in m3 is wrong by 1e9; an absolute
tolerance had to scale with the quantity it bounds, so `abs=2e-3` became `abs=2e-6`; and a station
named outright moved from `1.0` to `1.0e-3`, which on a 0.020 m tube is the same place and in
meters would have been off the end of it.

The arithmetic checks that need no vendor run first and run in milliseconds; the geometry checks
follow against real FreeCAD.

See doc/implementation/wall_thickness_measure.md.
"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import kern, sections, truth                           # noqa: E402

from conftest import requires_freecad                                    # noqa: E402


# ------------------------------------------------------------------ the truth model, no vendor


#: The hand-built patch this class reasons about, **on the real fixture's own SI scale**.
#:
#: It used to be a millimeter model -- r = 10, wall 0.6, patch 8..12 deep by 0.15 -- which was
#: readable and, once `truth.EDGE_MARGIN_M` became 5e-5 m, no longer self-consistent: a point
#: 0.01 from the `z` edge was "inside EDGE_MARGIN" in millimeters and two hundred margins away in
#: meters, so the ambiguity test asserted the opposite of what it says. Scaling the model is the
#: fix rather than scaling the one assertion, because every number here is compared against a
#: module constant and only a consistent scale keeps them comparable (IP-FC-163).
R_OUTER_M = 0.010
WALL_M = 6.0e-4
PATCH_DEPTH_M = 1.5e-4
PATCH_Z_LO_M, PATCH_Z_HI_M, PATCH_Z_MID_M = 0.008, 0.012, 0.010
PATCH_HALF_ANGLE_RAD = 0.03
PATCH_ARC_M = 6.0e-4

#: The wall inside the patch and outside it: the two answers every test below checks for.
THIN_M = WALL_M - PATCH_DEPTH_M
NOMINAL_M = WALL_M


def _patch_feature(angle_rad=0.0):
    """One outer-surface thin patch, as `truth`'s builders spell a feature."""
    return {'kind': 'thin', 'thickness_m': THIN_M, 'depth_m': PATCH_DEPTH_M,
            'surface': 'outer', 'delta_m': -PATCH_DEPTH_M,
            'z_lo_m': PATCH_Z_LO_M, 'z_hi_m': PATCH_Z_HI_M,
            'half_angle_rad': PATCH_HALF_ANGLE_RAD, 'arc_m': PATCH_ARC_M,
            'angle_rad': angle_rad, 'z_mid_m': PATCH_Z_MID_M}


class TestTheTruthModel:
    """`WallTruth.true_thickness_at` is arithmetic and needs no geometry to check."""

    def _patch_truth(self, angle_rad=0.0):
        return truth.WallTruth(None, 'test', NOMINAL_M, R_OUTER_M,
                               [_patch_feature(angle_rad)])

    def test_away_from_every_feature_the_wall_is_nominal(self):
        t = self._patch_truth()
        assert t.true_thickness_at(R_OUTER_M, 0.0, 0.002) == pytest.approx(NOMINAL_M)
        assert t.true_thickness_at(-R_OUTER_M, 0.0, PATCH_Z_MID_M) == pytest.approx(NOMINAL_M)

    def test_inside_the_patch_the_wall_is_thinner_by_the_depth(self):
        t = self._patch_truth()
        assert t.true_thickness_at(R_OUTER_M, 0.0, PATCH_Z_MID_M) == pytest.approx(THIN_M)

    def test_a_point_near_a_feature_edge_is_ambiguous_not_guessed(self):
        """The wall steps at a patch boundary, so two answers are defensible and scoring such a
        sample would measure the fixture rather than the candidate."""
        t = self._patch_truth()
        # Exactly on the `z` edge, then well inside `EDGE_MARGIN_M` of it -- a fifth of the
        # margin, so the assertion does not sit on the threshold it is testing.
        assert t.true_thickness_at(R_OUTER_M, 0.0, PATCH_Z_LO_M) is None
        assert t.true_thickness_at(R_OUTER_M, 0.0,
                                   PATCH_Z_LO_M + 0.2 * truth.EDGE_MARGIN_M) is None
        on_edge_y_m = R_OUTER_M * math.tan(PATCH_HALF_ANGLE_RAD)
        assert t.true_thickness_at(R_OUTER_M, on_edge_y_m, PATCH_Z_MID_M) is None

    def test_the_angular_margin_is_an_arc_length_so_it_means_the_same_at_any_radius(self):
        """Expressed as `EDGE_MARGIN_M / radius`: a fixed angle would be a different distance on
        the bore than on the outer surface, and the two boundaries of one wall would disagree
        about where a feature ends."""
        t = self._patch_truth()
        inner_r_m, outer_r_m = R_OUTER_M - WALL_M, R_OUTER_M
        # A point the same arc distance inside the edge is unambiguous at both radii.
        for r_m in (inner_r_m, outer_r_m):
            ang = PATCH_HALF_ANGLE_RAD - (2.0 * truth.EDGE_MARGIN_M) / r_m
            got = t.true_thickness_at(r_m * math.cos(ang), r_m * math.sin(ang), PATCH_Z_MID_M)
            assert got == pytest.approx(THIN_M), r_m

    def test_a_feature_not_centered_on_the_x_axis_is_still_found(self):
        t = self._patch_truth(math.pi / 2.0)
        assert t.true_thickness_at(0.0, R_OUTER_M, PATCH_Z_MID_M) == pytest.approx(THIN_M)
        assert t.true_thickness_at(R_OUTER_M, 0.0, PATCH_Z_MID_M) == pytest.approx(NOMINAL_M)

    def test_a_feature_spanning_the_angle_wraparound_is_found(self):
        """A feature at angle pi straddles the atan2 branch cut; folding the difference is what
        keeps it one feature instead of two half-features."""
        t = self._patch_truth(math.pi)
        # A micron either side of the cut, which at this radius is well inside the patch's own
        # half-angle and well outside `EDGE_MARGIN_M` of its ends.
        for y_m in (0.0, 1.0e-6, -1.0e-6):
            assert t.true_thickness_at(-R_OUTER_M, y_m,
                                       PATCH_Z_MID_M) == pytest.approx(THIN_M), y_m


# ------------------------------------------------------------------ the section helpers, no vendor


class TestSectionArrayHelpers:
    """Pure `numpy`, checked against closed forms on a circle."""

    @staticmethod
    def _circle(n, r=10.0, z=0.0):
        a = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
        return np.column_stack((r * np.cos(a), r * np.sin(a), np.full(n, z)))

    def test_signed_area_of_a_circle(self):
        got = sections.signed_area(self._circle(2048))
        assert got == pytest.approx(math.pi * 100.0, rel=1e-5)

    def test_signed_area_changes_sign_with_orientation(self):
        c = self._circle(512)
        assert sections.signed_area(c) > 0 > sections.signed_area(c[::-1])

    def test_perimeter_of_a_circle(self):
        assert sections.perimeter(self._circle(4096)) == pytest.approx(2.0 * math.pi * 10.0,
                                                                      rel=1e-6)

    def test_arc_length_starts_at_zero_and_is_monotone(self):
        s = sections.arc_length(self._circle(256))
        assert s[0] == 0.0
        assert np.all(np.diff(s) > 0.0)
        assert len(s) == 256

    def test_resampling_makes_the_spacing_even(self):
        """The remedy for `discretize`'s per-edge allocation. Built here on a deliberately uneven
        sampling, since an already-even one could not show the difference."""
        a = np.concatenate((np.linspace(0.0, 0.2, 400, endpoint=False),
                            np.linspace(0.2, 2.0 * np.pi, 100, endpoint=False)))
        uneven = np.column_stack((10.0 * np.cos(a), 10.0 * np.sin(a), np.zeros(a.size)))
        lo, _, hi = sections.spacing_stats(uneven)
        assert hi / lo > 50.0, 'the fixture must actually be uneven'
        even = sections.resample_by_arc_length(uneven, 1000)
        lo2, _, hi2 = sections.spacing_stats(even)
        assert hi2 / lo2 < 1.05

    def test_resampling_preserves_the_curve(self):
        c = self._circle(2048)
        out = sections.resample_by_arc_length(c, 777)
        r = np.hypot(out[:, 0], out[:, 1])
        assert np.allclose(r, 10.0, atol=1e-3)
        assert out.shape == (777, 3)

    def test_resampling_a_rotated_loop_gives_the_same_spacing(self):
        """A wire can come back rotated between processes -- same curve, different starting edge.
        Arc-length re-sampling has to be indifferent to that."""
        c = self._circle(1024)
        rolled = np.roll(c, 311, axis=0)
        a = sections.resample_by_arc_length(c, 512)
        b = sections.resample_by_arc_length(rolled, 512)
        assert sections.perimeter(a) == pytest.approx(sections.perimeter(b), rel=1e-9)
        assert sections.spacing_stats(a)[1] == pytest.approx(sections.spacing_stats(b)[1],
                                                             rel=1e-9)


# ------------------------------------------------------------------ against real geometry


@pytest.fixture
def uniform(fc, Part, App):
    return truth.uniform_tube(Part, App)


@pytest.fixture
def patched(fc, Part, App):
    return truth.thin_patch_tube(Part, App)


@pytest.fixture
def ribbed(fc, Part, App):
    return truth.ribbed_tube(Part, App)


@requires_freecad
class TestTheFixturesAreWhatTheyClaim:
    """**The fixtures' own verification.** Each claim in `truth`'s docstrings, checked against the
    kernel rather than asserted."""

    def test_the_uniform_tube_is_one_solid_with_an_annular_section(self, uniform, cci, App):
        assert len(uniform.shape.Solids) == 1
        wires = sections.closed_wires(uniform.shape, truth.HEIGHT_M / 2.0, App=App)
        assert len(wires) == 2
        assert cci._is_annulus(wires) is True

    def test_the_uniform_tubes_volume_matches_the_closed_form(self, uniform):
        r_m, t_m, h_m = truth.R_OUTER_M, truth.WALL_M, truth.HEIGHT_M
        expect_m3 = math.pi * (r_m ** 2 - (r_m - t_m) ** 2) * h_m
        # `kern.volume_m3`, not `.Volume`: the kernel's attribute is mm3 and the closed form above
        # is m3, so comparing them directly is wrong by 1e9 (IP-FC-163).
        assert kern.volume_m3(uniform.shape) == pytest.approx(expect_m3, rel=1e-6)

    def test_the_patch_removes_exactly_the_volume_it_should(self, patched):
        """The fixture's own arithmetic: a sector of an annulus, `half_angle` each side, over the
        band. If this disagrees, the patch is not the shape the truth function describes."""
        f = patched.features[0]
        r_m, t_m = truth.R_OUTER_M, truth.WALL_M
        band_m = f['z_hi_m'] - f['z_lo_m']
        removed_m3 = ((f['half_angle_rad'])
                      * (r_m ** 2 - (r_m - f['depth_m']) ** 2) * band_m)
        full_m3 = math.pi * (r_m ** 2 - (r_m - t_m) ** 2) * truth.HEIGHT_M
        assert kern.volume_m3(patched.shape) == pytest.approx(full_m3 - removed_m3, rel=2e-3)

    def test_the_rib_adds_exactly_the_volume_it_should(self, ribbed):
        f = ribbed.features[0]
        r_m, t_m = truth.R_OUTER_M, truth.WALL_M
        band_m = f['z_hi_m'] - f['z_lo_m']
        r_in_m, r_rib_m = r_m - t_m, r_m - t_m - f['rise_m']
        added_m3 = (f['half_angle_rad']) * (r_in_m ** 2 - r_rib_m ** 2) * band_m
        full_m3 = math.pi * (r_m ** 2 - r_in_m ** 2) * truth.HEIGHT_M
        assert kern.volume_m3(ribbed.shape) == pytest.approx(full_m3 + added_m3, rel=2e-3)

    def test_the_patch_is_measurably_thinner_where_the_truth_says_so(self, patched, App):
        """Read straight off the section's two loops: the outer radius drops by `depth` inside the
        patch and nowhere else. This is the claim every later gate depends on."""
        f = patched.features[0]
        outer, inner = sections.station_loops(patched.shape, f['z_mid_m'], 2000, App=App)
        r_out = np.hypot(outer[:, 0], outer[:, 1])
        r_in = np.hypot(inner[:, 0], inner[:, 1])
        ang = np.arctan2(outer[:, 1], outer[:, 0])
        in_patch = np.abs(ang) < f['half_angle_rad'] * 0.5
        # Well outside, not merely "not well inside": the band between the two is the patch's own
        # edge, where the wall steps and neither answer is the one being checked.
        outside = np.abs(ang) > f['half_angle_rad'] * 2.0
        assert in_patch.sum() > 3, 'the patch must be sampled at all'
        # **The absolute tolerances scaled with the radii they bound** (IP-FC-163): 2e-3 was
        # 2 microns on a millimeter radius, and carrying the literal across would have made it
        # 2 mm on a meter radius -- three times the whole wall, so every one of these assertions
        # would have passed whatever the geometry did.
        assert r_out[in_patch].max() == pytest.approx(truth.R_OUTER_M - f['depth_m'], abs=2e-6)
        assert r_out[outside].min() == pytest.approx(truth.R_OUTER_M, abs=2e-6)
        # The bore is untouched, so the thickness change is entirely the patch's.
        assert r_in.max() == pytest.approx(truth.R_OUTER_M - truth.WALL_M, abs=2e-6)
        assert r_in.min() == pytest.approx(truth.R_OUTER_M - truth.WALL_M, abs=2e-6)

    def test_the_rib_is_measurably_thicker_where_the_truth_says_so(self, ribbed, App):
        f = ribbed.features[0]
        outer, inner = sections.station_loops(ribbed.shape, f['z_mid_m'], 2000, App=App)
        r_in = np.hypot(inner[:, 0], inner[:, 1])
        ang = np.arctan2(inner[:, 1], inner[:, 0])
        in_rib = np.abs(ang) < f['half_angle_rad'] * 0.5
        outside = np.abs(ang) > f['half_angle_rad'] * 2.0
        assert in_rib.sum() > 3
        assert r_in[in_rib].min() == pytest.approx(
            truth.R_OUTER_M - truth.WALL_M - f['rise_m'], abs=2e-6)
        assert r_in[outside].max() == pytest.approx(truth.R_OUTER_M - truth.WALL_M, abs=2e-6)

    def test_the_patch_has_the_arc_length_it_claims(self, patched, App):
        """Gate G1 is stated as a length along the section, so the fixture's arc has to be that
        length and not merely some angle."""
        f = patched.features[0]
        outer, _inner = sections.station_loops(patched.shape, f['z_mid_m'], 4000, App=App)
        r_m = np.hypot(outer[:, 0], outer[:, 1])
        thin = r_m < truth.R_OUTER_M - f['depth_m'] / 2.0
        pts = outer[thin]
        assert pts.shape[0] > 3
        width_m = float(np.hypot(*(pts[:, :2].max(axis=0) - pts[:, :2].min(axis=0))))
        # A ratio, so `rel` needed no scaling; the message prints millimeters and says so.
        assert width_m == pytest.approx(f['arc_m'], rel=0.25), (
            'patch chord %.4f mm against a claimed arc of %.4f mm'
            % (kern.mm(width_m), kern.mm(f['arc_m'])))

    def test_the_station_away_from_a_feature_reads_nominal_on_both_fixtures(self, patched,
                                                                           ribbed, App):
        """The converse: a fixture whose feature leaked along the whole tube would pass the tests
        above and be useless."""
        for t in (patched, ribbed):
            # 1.0e-3 m, not 1.0: the tube is `truth.HEIGHT_M` = 0.020 m tall, so a station at
            # `z` = 1.0 would be fifty tube-lengths past its end and section nothing at all --
            # which is exactly what it did before IP-FC-163 converted this assertion.
            loops = sections.station_loops(t.shape, 1.0e-3, 1200, App=App)
            assert len(loops) == 2
            r_out = np.hypot(loops[0][:, 0], loops[0][:, 1])
            r_in = np.hypot(loops[1][:, 0], loops[1][:, 1])
            assert r_out.min() == pytest.approx(truth.R_OUTER_M, abs=2e-6)
            assert r_in.max() == pytest.approx(truth.R_OUTER_M - truth.WALL_M, abs=2e-6)

    def test_the_rib_creates_concave_corners_on_the_bore(self, ribbed, App):
        """The feature that defeats the incumbent measure. Found as interior turning points in the
        bore's own boundary: a convex loop has none."""
        f = ribbed.features[0]
        _outer, inner = sections.station_loops(ribbed.shape, f['z_mid_m'], 1440, App=App)
        p = sections.resample_by_arc_length(inner, 1440)[:, :2]
        prev, nxt = np.roll(p, 1, axis=0), np.roll(p, -1, axis=0)
        cross = ((p - prev)[:, 0] * (nxt - p)[:, 1]
                 - (p - prev)[:, 1] * (nxt - p)[:, 0])
        sign = np.sign(sections.signed_area(inner))
        reflex = (cross * sign) < -1e-9
        assert reflex.sum() >= 2, 'a rib on the bore must leave at least two re-entrant corners'


@requires_freecad
class TestSectionExtractionCost:

    def test_a_whole_loop_costs_a_bounded_number_of_round_trips(self, fc, uniform, App):
        """What IP-WTM-2 exists for. Per-point access would be thousands of trips a station."""
        before = fc.round_trips
        loops = sections.station_loops(uniform.shape, truth.HEIGHT_M / 2.0, 2000, App=App)
        cost = fc.round_trips - before
        assert sum(a.shape[0] for a in loops) >= 4000
        assert cost < 40, '%d round trips for 2 loops of 2000 points' % cost

    def test_the_loops_come_back_outer_first(self, uniform, App):
        outer, inner = sections.station_loops(uniform.shape, truth.HEIGHT_M / 2.0, 600, App=App)
        assert abs(sections.signed_area(outer)) > abs(sections.signed_area(inner))

    def test_the_vendors_own_spacing_is_uneven_which_is_why_resampling_exists(self, ribbed, App):
        """Not an assumption: measured on the fixture that has edges of very different lengths."""
        f = ribbed.features[0]
        _outer, inner = sections.station_loops(ribbed.shape, f['z_mid_m'], 720, App=App)
        lo, _med, hi = sections.spacing_stats(inner)
        assert hi / lo > 3.0, 'spacing ratio only %.2f' % (hi / lo)
        even = sections.resample_by_arc_length(inner, 720)
        lo2, _m2, hi2 = sections.spacing_stats(even)
        # **Not 1.05 here, and that is not a weaker standard.** `spacing_stats` measures chords,
        # and re-sampling guarantees even spacing in *arc length*. Where a sharp corner falls
        # between two samples the chord across it is shorter than the arc, so a loop with real
        # corners -- which is the whole point of the ribbed fixture -- cannot reach 1.0 by chords.
        # The smooth-circle case asserts 1.05; here the claim is that the gross unevenness is gone.
        assert hi2 / lo2 < 1.35, 'chord ratio %.3f after re-sampling' % (hi2 / lo2)
        assert hi2 / lo2 < (hi / lo) / 2.0
