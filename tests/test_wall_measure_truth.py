"""IP-WTM-1 and IP-WTM-2: the ground-truth fixtures, and the section extraction they feed.

**A fixture that claims to carry closed-form truth has to prove it**, or the whole screening rests
on an assumption — and the reason this plan exists is that no measure here was ever checked against
a known answer. So these tests check the fixtures against the kernel: the patch really is `depth`
thinner, the rib really is `rise` thicker, the surfaces really are concentric cylinders, and the
truth function really agrees with the geometry it describes.

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

from wall_measure import sections, truth                                 # noqa: E402

from conftest import requires_freecad                                    # noqa: E402


# ------------------------------------------------------------------ the truth model, no vendor


class TestTheTruthModel:
    """`WallTruth.true_thickness_at` is arithmetic and needs no geometry to check."""

    def _patch_truth(self):
        f = {'kind': 'thin', 'thickness': 0.45, 'depth': 0.15,
             'surface': 'outer', 'delta': -0.15,
             'z_lo': 8.0, 'z_hi': 12.0, 'half_angle': 0.03, 'arc': 0.6,
             'angle': 0.0, 'z_mid': 10.0}
        return truth.WallTruth(None, 'test', 0.6, 10.0, [f])

    def test_away_from_every_feature_the_wall_is_nominal(self):
        t = self._patch_truth()
        assert t.true_thickness_at(10.0, 0.0, 2.0) == pytest.approx(0.6)
        assert t.true_thickness_at(-10.0, 0.0, 10.0) == pytest.approx(0.6)

    def test_inside_the_patch_the_wall_is_thinner_by_the_depth(self):
        t = self._patch_truth()
        assert t.true_thickness_at(10.0, 0.0, 10.0) == pytest.approx(0.45)

    def test_a_point_near_a_feature_edge_is_ambiguous_not_guessed(self):
        """The wall steps at a patch boundary, so two answers are defensible and scoring such a
        sample would measure the fixture rather than the candidate."""
        t = self._patch_truth()
        assert t.true_thickness_at(10.0, 0.0, 8.0) is None          # exactly on the z edge
        assert t.true_thickness_at(10.0, 0.0, 8.01) is None         # inside EDGE_MARGIN
        on_edge_y = 10.0 * math.tan(0.03)
        assert t.true_thickness_at(10.0, on_edge_y, 10.0) is None   # on the angular edge

    def test_the_angular_margin_is_an_arc_length_so_it_means_the_same_at_any_radius(self):
        """Expressed as `EDGE_MARGIN / radius`: a fixed angle would be a different distance on the
        bore than on the outer surface, and the two boundaries of one wall would disagree about
        where a feature ends."""
        t = self._patch_truth()
        inner_r, outer_r = 9.4, 10.0
        edge = 0.03
        # A point the same arc distance inside the edge is unambiguous at both radii.
        for r in (inner_r, outer_r):
            ang = edge - (2.0 * truth.EDGE_MARGIN) / r
            got = t.true_thickness_at(r * math.cos(ang), r * math.sin(ang), 10.0)
            assert got == pytest.approx(0.45), r

    def test_a_feature_not_centred_on_the_x_axis_is_still_found(self):
        f = {'kind': 'thin', 'thickness': 0.45, 'depth': 0.15, 'surface': 'outer', 'delta': -0.15,
             'z_lo': 8.0, 'z_hi': 12.0, 'half_angle': 0.03, 'arc': 0.6,
             'angle': math.pi / 2.0, 'z_mid': 10.0}
        t = truth.WallTruth(None, 'test', 0.6, 10.0, [f])
        assert t.true_thickness_at(0.0, 10.0, 10.0) == pytest.approx(0.45)
        assert t.true_thickness_at(10.0, 0.0, 10.0) == pytest.approx(0.6)

    def test_a_feature_spanning_the_angle_wraparound_is_found(self):
        """A feature at angle pi straddles the atan2 branch cut; folding the difference is what
        keeps it one feature instead of two half-features."""
        f = {'kind': 'thin', 'thickness': 0.45, 'depth': 0.15, 'surface': 'outer', 'delta': -0.15,
             'z_lo': 8.0, 'z_hi': 12.0, 'half_angle': 0.03, 'arc': 0.6,
             'angle': math.pi, 'z_mid': 10.0}
        t = truth.WallTruth(None, 'test', 0.6, 10.0, [f])
        assert t.true_thickness_at(-10.0, 0.0, 10.0) == pytest.approx(0.45)
        assert t.true_thickness_at(-10.0, 0.001, 10.0) == pytest.approx(0.45)
        assert t.true_thickness_at(-10.0, -0.001, 10.0) == pytest.approx(0.45)


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
        wires = sections.closed_wires(uniform.shape, truth.HEIGHT / 2.0, App=App)
        assert len(wires) == 2
        assert cci._is_annulus(wires) is True

    def test_the_uniform_tubes_volume_matches_the_closed_form(self, uniform):
        r, t, h = truth.R_OUTER, truth.WALL, truth.HEIGHT
        expect = math.pi * (r ** 2 - (r - t) ** 2) * h
        assert uniform.shape.Volume == pytest.approx(expect, rel=1e-6)

    def test_the_patch_removes_exactly_the_volume_it_should(self, patched):
        """The fixture's own arithmetic: a sector of an annulus, `half_angle` each side, over the
        band. If this disagrees, the patch is not the shape the truth function describes."""
        f = patched.features[0]
        r, t = truth.R_OUTER, truth.WALL
        band = f['z_hi'] - f['z_lo']
        removed = (f['half_angle']) * (r ** 2 - (r - f['depth']) ** 2) * band
        full = math.pi * (r ** 2 - (r - t) ** 2) * truth.HEIGHT
        assert patched.shape.Volume == pytest.approx(full - removed, rel=2e-3)

    def test_the_rib_adds_exactly_the_volume_it_should(self, ribbed):
        f = ribbed.features[0]
        r, t = truth.R_OUTER, truth.WALL
        band = f['z_hi'] - f['z_lo']
        r_in, r_rib = r - t, r - t - f['rise']
        added = (f['half_angle']) * (r_in ** 2 - r_rib ** 2) * band
        full = math.pi * (r ** 2 - r_in ** 2) * truth.HEIGHT
        assert ribbed.shape.Volume == pytest.approx(full + added, rel=2e-3)

    def test_the_patch_is_measurably_thinner_where_the_truth_says_so(self, patched, App):
        """Read straight off the section's two loops: the outer radius drops by `depth` inside the
        patch and nowhere else. This is the claim every later gate depends on."""
        f = patched.features[0]
        outer, inner = sections.station_loops(patched.shape, f['z_mid'], 2000, App=App)
        r_out = np.hypot(outer[:, 0], outer[:, 1])
        r_in = np.hypot(inner[:, 0], inner[:, 1])
        ang = np.arctan2(outer[:, 1], outer[:, 0])
        in_patch = np.abs(ang) < f['half_angle'] * 0.5
        # Well outside, not merely "not well inside": the band between the two is the patch's own
        # edge, where the wall steps and neither answer is the one being checked.
        outside = np.abs(ang) > f['half_angle'] * 2.0
        assert in_patch.sum() > 3, 'the patch must be sampled at all'
        assert r_out[in_patch].max() == pytest.approx(truth.R_OUTER - f['depth'], abs=2e-3)
        assert r_out[outside].min() == pytest.approx(truth.R_OUTER, abs=2e-3)
        # The bore is untouched, so the thickness change is entirely the patch's.
        assert r_in.max() == pytest.approx(truth.R_OUTER - truth.WALL, abs=2e-3)
        assert r_in.min() == pytest.approx(truth.R_OUTER - truth.WALL, abs=2e-3)

    def test_the_rib_is_measurably_thicker_where_the_truth_says_so(self, ribbed, App):
        f = ribbed.features[0]
        outer, inner = sections.station_loops(ribbed.shape, f['z_mid'], 2000, App=App)
        r_in = np.hypot(inner[:, 0], inner[:, 1])
        ang = np.arctan2(inner[:, 1], inner[:, 0])
        in_rib = np.abs(ang) < f['half_angle'] * 0.5
        outside = np.abs(ang) > f['half_angle'] * 2.0
        assert in_rib.sum() > 3
        assert r_in[in_rib].min() == pytest.approx(
            truth.R_OUTER - truth.WALL - f['rise'], abs=2e-3)
        assert r_in[outside].max() == pytest.approx(truth.R_OUTER - truth.WALL, abs=2e-3)

    def test_the_patch_has_the_arc_length_it_claims(self, patched, App):
        """Gate G1 is stated in millimetres along the section, so the fixture's arc has to be that
        length in millimetres and not merely some angle."""
        f = patched.features[0]
        outer, _inner = sections.station_loops(patched.shape, f['z_mid'], 4000, App=App)
        r = np.hypot(outer[:, 0], outer[:, 1])
        thin = r < truth.R_OUTER - f['depth'] / 2.0
        pts = outer[thin]
        assert pts.shape[0] > 3
        width = float(np.hypot(*(pts[:, :2].max(axis=0) - pts[:, :2].min(axis=0))))
        assert width == pytest.approx(f['arc'], rel=0.25), (
            'patch chord %.4f mm against a claimed arc of %.4f mm' % (width, f['arc']))

    def test_the_station_away_from_a_feature_reads_nominal_on_both_fixtures(self, patched,
                                                                           ribbed, App):
        """The converse: a fixture whose feature leaked along the whole tube would pass the tests
        above and be useless."""
        for t in (patched, ribbed):
            loops = sections.station_loops(t.shape, 1.0, 1200, App=App)
            assert len(loops) == 2
            r_out = np.hypot(loops[0][:, 0], loops[0][:, 1])
            r_in = np.hypot(loops[1][:, 0], loops[1][:, 1])
            assert r_out.min() == pytest.approx(truth.R_OUTER, abs=2e-3)
            assert r_in.max() == pytest.approx(truth.R_OUTER - truth.WALL, abs=2e-3)

    def test_the_rib_creates_concave_corners_on_the_bore(self, ribbed, App):
        """The feature that defeats the incumbent measure. Found as interior turning points in the
        bore's own boundary: a convex loop has none."""
        f = ribbed.features[0]
        _outer, inner = sections.station_loops(ribbed.shape, f['z_mid'], 1440, App=App)
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
        loops = sections.station_loops(uniform.shape, truth.HEIGHT / 2.0, 2000, App=App)
        cost = fc.round_trips - before
        assert sum(a.shape[0] for a in loops) >= 4000
        assert cost < 40, '%d round trips for 2 loops of 2000 points' % cost

    def test_the_loops_come_back_outer_first(self, uniform, App):
        outer, inner = sections.station_loops(uniform.shape, truth.HEIGHT / 2.0, 600, App=App)
        assert abs(sections.signed_area(outer)) > abs(sections.signed_area(inner))

    def test_the_vendors_own_spacing_is_uneven_which_is_why_resampling_exists(self, ribbed, App):
        """Not an assumption: measured on the fixture that has edges of very different lengths."""
        f = ribbed.features[0]
        _outer, inner = sections.station_loops(ribbed.shape, f['z_mid'], 720, App=App)
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
