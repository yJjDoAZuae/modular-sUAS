"""IP-WTM-20: is the `U` >= 3 wall thin, or is its section ring severed?

A severed ring was once misreported as a 0.355705 mm thickness (cowl.md OQ-DES-CW26), and the
`U` = 4 readings sit above that, so a thickness figure alone cannot tell the two apart. `locate`
classifies a section's topology and finds where the thin spot is.

**The classifier is exercised from both sides, on synthetic loops with known topology**, because a
test that only ever sees healthy walls proves nothing about a classifier whose whole job is to spot
an unhealthy one. The real-wall tests then run it on the corpus and skip when the corpus is absent.

See doc/implementation/wall_thickness_measure.md.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import candidates, corpus, density, locate, sections  # noqa: E402

from conftest import requires_freecad                              # noqa: E402

requires_corpus = pytest.mark.skipif(
    not corpus.available(),
    reason='no saved soak walls in %s' % corpus.SHAPES_DIR)


def ring(radius, n=360, cx=0.0, cy=0.0, lo=0.0, hi=360.0):
    """A closed polyline arc or full circle, as an (n, 3) array in the xy plane."""
    a = np.radians(np.linspace(lo, hi, n, endpoint=(hi - lo) < 359.9))
    return np.stack([cx + radius * np.cos(a), cy + radius * np.sin(a), np.zeros_like(a)], axis=1)


def annulus(outer_r=20.0, wall=0.6, n=360):
    return [ring(outer_r, n), ring(outer_r - wall, n)]


def c_shape(outer_r=20.0, wall=0.6, gap_deg=20.0, n=240):
    """One severed arc: the outline of a C, traced out along the outside and back along the inside.

    This is what a ring broken in **one** place leaves -- a single closed loop with no hole, which
    is a different topology from two arcs and has to be classified differently.
    """
    out = ring(outer_r, n, lo=0.0, hi=360.0 - gap_deg)
    back = ring(outer_r - wall, n, lo=360.0 - gap_deg, hi=0.0)
    return [np.concatenate([out, back], axis=0)]


# ------------------------------------------------------------------- the classifier, no vendor


class TestRingState:

    def test_two_nested_loops_are_an_annulus(self):
        state, detail = locate.ring_state(annulus())
        assert state == locate.ANNULUS
        assert detail['loops'] == 2
        assert detail['area_ratio'] == pytest.approx((19.4 / 20.0) ** 2, rel=1e-3)

    def test_a_thin_wall_gives_an_area_ratio_near_one(self):
        """The scale-free health figure: a 0.6 mm wall on a 20 mm bore keeps the inner area within
        6% of the outer's, so a ratio far from 1 means the inner loop is not a wall bore."""
        _state, detail = locate.ring_state(annulus(outer_r=20.0, wall=0.6))
        assert 0.90 < detail['area_ratio'] < 1.0

    def test_one_severed_arc_is_not_an_annulus(self):
        state, detail = locate.ring_state(c_shape())
        assert state == locate.SEVERED_ONE
        assert detail['loops'] == 1
        assert detail['area_ratio'] is None

    def test_two_side_by_side_arcs_are_severed_not_nested(self):
        """**The case that misreported as a thickness.** Two separate arcs each bound a closed loop,
        and a nearest-point measure between them reads the gap across the break as a wall."""
        loops = [ring(6.0, cx=-10.0), ring(6.0, cx=10.0)]
        state, detail = locate.ring_state(loops)
        assert state == locate.SEVERED_MANY
        assert detail['loops'] == 2

    def test_an_empty_section_is_no_wall(self):
        assert locate.ring_state([])[0] == locate.NO_WALL

    def test_nesting_is_tested_at_several_points_not_one(self):
        """Two interleaving arcs can put *one* point of the second inside the first. Requiring every
        sampled point to be inside is what separates that from a real annulus."""
        outer = ring(20.0, 720)
        # A loop that starts inside the outer circle and swings well outside it.
        drifting = ring(20.0, 720, cx=12.0)
        assert locate.ring_state([outer, drifting])[0] == locate.SEVERED_MANY

    def test_a_strongly_non_convex_inner_loop_still_reads_as_nested(self):
        """The real case: an inner loop tracing into a notch and back out. Its bounding box is
        almost the outer's, so a box test would be useless; crossing-number is not fooled."""
        a = np.radians(np.linspace(0.0, 360.0, 720, endpoint=False))
        r = 19.4 - 3.0 * (np.cos(8 * a) > 0.9)                 # eight deep notches
        notched = np.stack([r * np.cos(a), r * np.sin(a), np.zeros_like(a)], axis=1)
        state, detail = locate.ring_state([ring(20.0, 720), notched])
        assert state == locate.ANNULUS
        assert detail['area_ratio'] < 1.0


class TestWindingInside:

    def test_a_point_on_the_axis_is_inside_a_ring(self):
        assert locate._winding_inside(np.array([0.0, 0.0, 0.0]), ring(10.0))

    def test_a_point_well_outside_is_outside(self):
        assert not locate._winding_inside(np.array([50.0, 0.0, 0.0]), ring(10.0))

    def test_a_vertex_on_the_ray_is_not_double_counted(self):
        """The classic crossing-number bug: counting both edges at a vertex that lies exactly on the
        test ray flips the answer. The half-open straddle test is what avoids it."""
        square = np.array([[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0], [1.0, 0.0, 0.0],
                           [1.0, 1.0, 0.0], [-1.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
        assert locate._winding_inside(np.array([0.0, 0.0, 0.0]), square)


# --------------------------------------------------------------- locating the thin spot, synthetic


class TestStationDetail:

    def test_a_healthy_synthetic_section_reports_its_angle_and_radius(self, monkeypatch):
        loops = annulus(outer_r=20.0, wall=0.6, n=720)
        monkeypatch.setattr(sections, 'station_loops', lambda *a, **k: loops)
        row = locate.station_detail(None, -5.0)
        assert row['state'] == locate.ANNULUS
        assert row['thickness'] == pytest.approx(0.6, abs=0.01)
        assert row['worst_thin'] == pytest.approx(0.0, abs=0.01)
        assert row['radius'] == pytest.approx(19.4, abs=0.01)
        assert -180.0 <= row['angle_deg'] <= 180.0

    def test_it_finds_a_deliberately_thinned_sector_and_its_angle(self):
        """**The converse that makes the locator worth trusting.** A patch thinned at a known angle
        has to come back at that angle, not merely as a smaller number."""
        a = np.radians(np.linspace(0.0, 360.0, 1440, endpoint=False))
        target = np.radians(30.0)
        thin = np.abs(np.angle(np.exp(1j * (a - target)))) < np.radians(3.0)
        r = np.where(thin, 20.0 - 0.2, 20.0 - 0.6)
        loops = [ring(20.0, 1440), np.stack([r * np.cos(a), r * np.sin(a), np.zeros_like(a)],
                                            axis=1)]
        state, detail = locate.ring_state(loops)
        assert state == locate.ANNULUS
        outer, inner = loops[0], loops[detail['nested'][0]]
        pts, d = candidates.nearest_point_min(outer, inner)
        k = int(np.argmin(d))
        assert d[k] == pytest.approx(0.2, abs=0.01)
        assert float(np.degrees(np.arctan2(pts[k][1], pts[k][0]))) == pytest.approx(30.0, abs=3.0)

    def test_a_station_with_no_wall_returns_a_row_not_none(self, monkeypatch):
        """A station with no wall is a finding. Returning `None` is how the soak's own convention
        turned an absent wall into a skipped one (IP-WTM-19)."""
        monkeypatch.setattr(sections, 'station_loops', lambda *a, **k: [])
        row = locate.station_detail(None, -5.0)
        assert row is not None and row['state'] == locate.NO_WALL
        assert row['worst_thin'] is None


def toothed(outer_r=20.0, wall=0.6, n=4000, span_deg=1.0, bump=0.45, at_deg=40.0):
    """An annulus whose inner loop carries a narrow outward step: a genuinely thin spot.

    **This is a thin wall, not a corner artifact, and the difference matters for what can be
    tested with it.** Measured while writing `criterion_split`: on this shape the reflex detector
    does find the step's two shoulders and the exclusion does drop 20 samples, but the minimum is
    unmoved at every span from 0.085 to 0.677 mm of arc and at both step heights tried. The
    exclusion zone lands on the *smooth* side of each shoulder, because `_within_arc_of` measures
    its margin along the sampled polyline and the step's own height is charged against it -- so a
    0.45 mm step consumes a 0.30 mm margin by itself. That is the right answer here: the 0.15 mm
    reading on the step's flat top is a real wall thickness measured perpendicular, and dropping it
    would hide a thin wall. A synthetic convex loop therefore cannot produce a non-zero corner
    term, which is why the corner term is tested for its arithmetic and its guard here and measured
    on a real wall instead (IP-WTM-10, IP-WTM-28).
    """
    a = np.radians(np.linspace(0.0, 360.0, n, endpoint=False))
    deg = np.degrees(a)
    r = np.full_like(a, outer_r - wall)
    r[(deg > at_deg) & (deg < at_deg + span_deg)] += bump
    inner = np.stack([r * np.cos(a), r * np.sin(a), np.zeros_like(a)], axis=1)
    return [ring(outer_r, n), inner]


class TestCriterionSplit:
    """IP-WTM-28: `TAU` and `WALL_TOL` are thresholds on two different measures.

    `cavity`'s second pass converges a plain minimum at `CHECK_ARC` = 0.20 mm; the figure the
    corpus publishes is the corner-excluded minimum at 0.125 mm. On `tail_shell` at `U` = 0.5 the
    two read 0.03794 and 0.01346 mm on one wall. `criterion_split` attributes that difference, so
    that setting `TAU` = `WALL_TOL` can be judged for what it actually asks.
    """

    def _patch(self, monkeypatch, by_count, perimeter=121.9):
        """Serve a different set of loops per sample count, which is what the two spacings buy."""
        monkeypatch.setattr(density, 'section_perimeter', lambda *a, **k: perimeter)
        monkeypatch.setattr(sections, 'station_loops',
                            lambda shape, z, n, **k: by_count(n))

    def test_a_coarse_sampling_that_misses_a_thin_spot_reads_less_thinness(self, monkeypatch):
        """The sampling term's sign is the useful part. A coarser sampling can only *miss* a thin
        spot, never invent one, so when the two differ by sampling alone the coarse reading is the
        smaller thinness and the term is negative."""
        n_gate = density.counts_for_spacing(121.9, 0.125)
        n_pass2 = density.counts_for_spacing(121.9, locate.PASS2_ARC)
        assert n_pass2 < n_gate, 'the coarse sampling has to be the coarser one'
        fine = toothed(n=n_gate)
        coarse = annulus(outer_r=20.0, wall=0.6, n=n_pass2)    # the step is not resolved at all
        self._patch(monkeypatch, lambda n: fine if n == n_gate else coarse)
        row = locate.criterion_split(None, [-5.0])[0]
        assert row['state'] == locate.ANNULUS
        assert row['thin_incumbent'] == pytest.approx(0.45, abs=1.0e-3)
        assert row['thin_pass2'] == pytest.approx(0.0, abs=1.0e-3)
        assert row['sampling_term'] < 0.0
        assert row['sampling_term'] == pytest.approx(-0.45, abs=1.0e-3)

    def test_the_two_terms_add_up_to_the_whole_discrepancy(self, monkeypatch):
        """The split is only useful if it is exhaustive: whatever is not sampling is corners."""
        self._patch(monkeypatch, lambda n: toothed(n=max(400, n)))
        row = locate.criterion_split(None, [-5.0])[0]
        total = row['thin_pass2'] - row['thin_selected']
        assert row['sampling_term'] + row['corner_term'] == pytest.approx(total, abs=1.0e-12)

    def test_the_corner_term_is_zero_on_a_convex_synthetic_loop(self, monkeypatch):
        """**Recorded as a vacuity note, not as a pass.** The exclusion drops samples on this shape
        and the minimum does not move, so a zero corner term here says nothing about the real
        wall's corners -- see `toothed`. The test exists so that a change which made this shape
        report a corner term would be noticed, since on this geometry that would be a false
        positive."""
        self._patch(monkeypatch, lambda n: toothed(n=max(400, n)))
        row = locate.criterion_split(None, [-5.0])[0]
        assert row['corner_term'] == pytest.approx(0.0, abs=1.0e-9)
        assert row['subset_violated'] is False

    def test_a_selected_reading_thinner_than_the_incumbent_is_reported_not_clamped(
            self, monkeypatch):
        """`corner_excluded_min` minimizes over a *subset*, so its thinness can never exceed the
        incumbent's. A violation is a defect in the measure and once was one (0.04806 against
        0.04689 mm on a real wall), so it is surfaced rather than quietly clamped."""
        self._patch(monkeypatch, lambda n: annulus(outer_r=20.0, wall=0.6, n=max(400, n)))
        monkeypatch.setattr(candidates, 'corner_excluded_min',
                            lambda outer, inner, **k: (inner, np.full(len(inner), 0.4)))
        row = locate.criterion_split(None, [-5.0])[0]
        assert row['subset_violated'] is True
        assert row['corner_term'] < 0.0
        assert 'SUBSET VIOLATED' in locate.criterion_table([row])

    def test_a_station_whose_ring_is_not_an_annulus_reports_the_state_and_no_readings(
            self, monkeypatch):
        self._patch(monkeypatch, lambda n: c_shape(n=max(240, n // 8)))
        row = locate.criterion_split(None, [-5.0])[0]
        assert row['state'] == locate.SEVERED_ONE
        assert row['thin_pass2'] is None and row['thin_selected'] is None
        assert row['sampling_term'] is None

    def test_a_station_with_no_measurable_perimeter_returns_a_row(self, monkeypatch):
        """No perimeter means no spacing can be derived, which is an absent reading rather than an
        error -- the same convention `station_detail` follows."""
        monkeypatch.setattr(density, 'section_perimeter', lambda *a, **k: None)
        row = locate.criterion_split(None, [-5.0])[0]
        assert row['z'] == -5.0 and row['state'] is None
        assert row['n_pass2'] is None

    def test_the_table_reports_each_column_worst_independently(self, monkeypatch):
        """`TAU` and `WALL_TOL` are each compared against the worst reading of their own measure
        over the whole wall, so the three worst figures need not come from one station."""
        rows = [
            {'z': -1.0, 'thin_pass2': 0.03, 'thin_incumbent': 0.02, 'thin_selected': 0.001,
             'sampling_term': 0.01, 'corner_term': 0.019, 'subset_violated': False,
             'state': locate.ANNULUS},
            {'z': -2.0, 'thin_pass2': 0.01, 'thin_incumbent': 0.05, 'thin_selected': 0.004,
             'sampling_term': -0.04, 'corner_term': 0.046, 'subset_violated': False,
             'state': locate.ANNULUS},
        ]
        text = locate.criterion_table(rows)
        last = text.strip().splitlines()[-1]
        assert last.split()[0] == 'worst'
        assert '0.03000' in last and '0.05000' in last and '0.00400' in last


class TestRankCorrelation:

    def test_a_perfect_monotone_pair_scores_one(self):
        assert locate.rank_correlation([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)

    def test_a_perfectly_reversed_pair_scores_minus_one(self):
        assert locate.rank_correlation([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)

    def test_it_is_insensitive_to_a_nonlinear_but_monotone_relation(self):
        """Why a rank measure and not a straight-line fit: the claim under test is 'thin spots sit
        where the rows are further apart', which is monotone and need not be linear."""
        assert locate.rank_correlation([1, 2, 3, 4], [1, 4, 9, 16]) == pytest.approx(1.0)

    def test_too_few_points_or_no_spread_returns_none(self):
        assert locate.rank_correlation([1, 2], [1, 2]) is None
        assert locate.rank_correlation([1, 1, 1], [1, 2, 3]) is None

    def test_none_entries_are_dropped_in_pairs(self):
        assert locate.rank_correlation([1, None, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)

    def test_ties_are_averaged_rather_than_ordered_arbitrarily(self):
        rho = locate.rank_correlation([1, 1, 2, 2], [5, 5, 9, 9])
        assert rho == pytest.approx(1.0)


class TestRowSpacingVerdict:
    """IP-WTM-30: thin spots against the local fit row spacing."""

    def _row(self, z, interval, inc, exc):
        return {'z': z, 'interval_mm': interval, 'nearest_row_mm': 0.5 * interval,
                'interval_lo': z - 0.5 * interval, 'interval_hi': z + 0.5 * interval,
                'thin_incumbent': inc, 'thin_excluded': exc, 'state': locate.ANNULUS}

    def test_widely_spaced_rows_reading_thinner_gives_a_positive_rho(self):
        rows = [self._row(-1.0, 1.0, 0.001, 0.001), self._row(-2.0, 5.0, 0.005, 0.005),
                self._row(-3.0, 10.0, 0.010, 0.010), self._row(-4.0, 20.0, 0.020, 0.020)]
        v = locate.row_spacing_verdict(rows)
        assert v['rho_excluded'] == pytest.approx(1.0)
        assert v['vacuous'] is False

    def test_crowded_rows_reading_thinner_gives_a_negative_rho(self):
        """The crowding hypothesis predicts this sign — tight rows being the bad ones — which is
        the opposite of §6.8.3's nose result, so the verdict must be able to report either."""
        rows = [self._row(-1.0, 1.0, 0.020, 0.020), self._row(-2.0, 5.0, 0.010, 0.010),
                self._row(-3.0, 10.0, 0.005, 0.005), self._row(-4.0, 20.0, 0.001, 0.001)]
        v = locate.row_spacing_verdict(rows)
        assert v['rho_excluded'] == pytest.approx(-1.0)

    def test_intervals_without_enough_spread_are_not_scorable(self):
        """**A vacuity guard, like the others here.** If every station sits in a similarly wide
        interval there is no independent variable, and a rho computed from that would be noise
        presented as a finding."""
        rows = [self._row(-1.0, 5.0, 0.001, 0.001), self._row(-2.0, 5.5, 0.020, 0.020),
                self._row(-3.0, 6.0, 0.003, 0.003)]
        v = locate.row_spacing_verdict(rows)
        assert v['vacuous'] is True
        assert 'NOT SCORABLE' in locate.row_spacing_table(rows)

    def test_a_station_outside_every_interval_is_counted_but_not_scored(self):
        rows = [self._row(-1.0, 1.0, 0.001, 0.001), self._row(-2.0, 10.0, 0.010, 0.010),
                self._row(-3.0, 20.0, 0.020, 0.020),
                {'z': -99.0, 'interval_mm': None, 'nearest_row_mm': None, 'interval_lo': None,
                 'interval_hi': None, 'thin_incumbent': 0.5, 'thin_excluded': 0.5,
                 'state': locate.ANNULUS}]
        v = locate.row_spacing_verdict(rows)
        assert v['stations'] == 4 and v['scored'] == 3


class TestExteriorVerdict:
    """IP-WTM-26: whether the residual is only in the gap between the two exteriors.

    `_refine` converges the wall out to `body`'s un-notched OML; the post-cut loop measures it out
    to `notched`'s real exterior. IP-WTM-44 measured pass 1 reaching 0.0073 mm while the finished
    wall stayed at 0.0481, which makes a reference-surface explanation attractive. The test that
    could refute it is a station thin against **both** exteriors, and that is what this verdict
    isolates.
    """

    def test_a_station_thin_against_both_exteriors_is_unexplained(self):
        rows = [(-10.0, 0.048, 0.047), (-20.0, 0.002, 0.002)]
        v = locate.exterior_verdict(rows)
        assert len(v['unexplained']) == 1
        assert v['unexplained'][0][0] == -10.0
        assert v['clean'] is False
        assert v['worst_unexplained_oml'] == pytest.approx(0.047)

    def test_a_station_thin_only_against_the_notched_exterior_is_explained(self):
        rows = [(-10.0, 0.048, 0.0005), (-20.0, 0.002, 0.002)]
        v = locate.exterior_verdict(rows)
        assert len(v['explained']) == 1 and not v['unexplained']
        assert v['clean'] is True

    def test_a_record_where_the_exteriors_never_coincide_is_vacuous_not_a_pass(self):
        """**The converse has to be exercised.** If no station has the two exteriors agreeing,
        nothing has tested whether a station away from every notch is thin too, and reporting that
        as a clean result is the empty-input cross-check this subsystem has made six times."""
        rows = [(-10.0, 0.048, 0.0005), (-20.0, 0.030, 0.0004)]
        v = locate.exterior_verdict(rows)
        assert v['vacuous'] is True
        assert v['clean'] is False, 'a vacuous record must not report clean'
        assert 'NOTHING TESTED' in locate.exterior_table(rows)

    def test_a_record_with_no_thin_station_is_vacuous_not_a_pass(self):
        """**Found by running it.** The first `exterior_split.py` run, `nose_cowl_shell` at
        `U` = 1.0, returned 63 stations whose worst reading was 0.0037 mm against a 0.01 mm
        tolerance — a compliant build. With nothing thin, `explained` and `unexplained` are both
        empty and an earlier version of this verdict reported CLEAN. A compliant specimen cannot
        test an explanation of non-compliance."""
        rows = [(-10.0, 0.0037, 0.0034), (-20.0, 0.0012, 0.0012)]
        v = locate.exterior_verdict(rows, wall_tol=0.01)
        assert v['thin'] == []
        assert v['vacuous'] is True
        assert v['clean'] is False, 'a compliant build must not report clean'
        assert any('compliant' in r for r in v['vacuous_because'])
        assert 'NOTHING TESTED' in locate.exterior_table(rows, wall_tol=0.01)

    def test_both_vacuity_reasons_are_reported_together_when_both_apply(self):
        rows = [(-10.0, 0.0037, 0.0001), (-20.0, 0.0012, 0.0002)]
        v = locate.exterior_verdict(rows, wall_tol=0.01)
        assert len(v['vacuous_because']) == 2

    def test_coincident_stations_are_found_by_the_readings_not_by_geometry(self):
        """Two readings that agree to `coincide_tol` mean no buttress tool removed exterior
        material within reach — which is read off the measurement rather than recomputed from the
        tools, so it cannot disagree with what was actually measured."""
        rows = [(-10.0, 0.0020, 0.0020), (-20.0, 0.048, 0.0005)]
        v = locate.exterior_verdict(rows)
        assert [r[0] for r in v['coincident']] == [-10.0]

    def test_an_unreadable_station_is_counted_not_dropped(self):
        """`_finished_wall_gap` returns `None` when a section is not one closed loop. A station it
        could not evaluate is not evidence either way, and silently dropping it is how a thin
        reading becomes an absent one (IP-WTM-19, IP-WTM-35)."""
        rows = [(-10.0, 0.048, 0.0005), (-20.0, None, None), (-30.0, 0.002, 0.002)]
        v = locate.exterior_verdict(rows)
        assert v['unreadable'] == 1 and v['readable'] == 2
        assert v['stations'] == 3
        assert 'unreadable' in locate.exterior_table(rows)

    def test_the_table_names_the_unexplained_stations(self):
        rows = [(-10.0, 0.048, 0.047), (-20.0, 0.002, 0.002)]
        text = locate.exterior_table(rows)
        assert 'UNEXPLAINED' in text
        assert 'does not explain these' in text


class TestCurvature:

    def test_a_circle_reads_its_own_radius(self):
        r = locate.curvature_profile(ring(37.5, 720), window_mm=2.0)
        assert float(np.median(r)) == pytest.approx(37.5, rel=0.01)

    def test_the_window_is_arc_length_so_the_estimate_is_density_independent(self):
        """**The trap this avoids.** Three consecutive samples of a finely sampled curve are nearly
        collinear, so a three-point circle through them is numerically meaningless -- the same thing
        that made the windowed-normal candidate oscillate. A fixed arc-length window means the
        estimate says the same thing at 360 samples and at 7 200."""
        for n in (360, 1440, 7200):
            got = float(np.median(locate.curvature_profile(ring(37.5, n), window_mm=2.0)))
            assert got == pytest.approx(37.5, rel=0.02), n

    def test_a_straight_run_reads_as_a_very_large_radius(self):
        line = np.stack([np.linspace(0.0, 10.0, 200), np.zeros(200), np.zeros(200)], axis=1)
        r = locate.curvature_profile(line, window_mm=1.0)
        assert r[len(r) // 2] > 1.0e6

    def test_a_shape_with_two_curvature_scales_separates_them(self):
        """The shape the cowl section actually is: gentle runs joined by much tighter turns. The
        profile has to separate the two, because that separation is the whole claim when a thin spot
        is said to be at a corner."""
        a = np.radians(np.linspace(0.0, 360.0, 3600, endpoint=False))
        # A four-lobed curve: radius oscillates, so curvature does too, by a wide factor.
        rad = 40.0 + 8.0 * np.cos(4 * a)
        pts = np.stack([rad * np.cos(a), rad * np.sin(a), np.zeros_like(a)], axis=1)
        r = locate.curvature_profile(pts, window_mm=1.0)
        finite = r[np.isfinite(r)]
        assert float(np.max(finite)) / float(np.min(finite)) > 3.0

    def test_the_rank_is_one_at_the_sharpest_place_on_the_loop(self):
        """`curvature_rank` is a percentile, so it is comparable between sections of different size
        -- which is what makes it usable across `U`."""
        a = np.radians(np.linspace(0.0, 360.0, 1800, endpoint=False))
        rad = 40.0 + 8.0 * np.cos(4 * a)
        pts = np.stack([rad * np.cos(a), rad * np.sin(a), np.zeros_like(a)], axis=1)
        r = locate.curvature_profile(pts, window_mm=1.0)
        kappa = 1.0 / np.where(np.isfinite(r), r, np.inf)
        sharpest = int(np.argmax(kappa))
        rank = float(np.count_nonzero(kappa <= kappa[sharpest])) / float(len(kappa))
        assert rank == pytest.approx(1.0, abs=1.0e-3)


class TestDistinctCorpus:

    def test_repeats_with_the_same_hash_collapse_to_one(self):
        """The soak found all 16 repeat pairs bit-identical, so 28 saved walls are 12 shapes and a
        minutes-per-wall measurement should not pay for the same geometry five times."""
        recs = corpus.distinct()
        if not recs:
            pytest.skip('no corpus')
        assert len(recs) == 12
        assert len(corpus.available()) == 28
        assert len(set(r.label for r in recs)) == len(recs)

    def test_it_keeps_both_when_the_hashes_differ(self, tmp_path):
        """**Deduplication follows the evidence, not the reproducibility claim.** If a future soak
        does find repeats differing, both must survive -- otherwise the dedup would hide exactly the
        result the soak exists to detect."""
        d = tmp_path / 'shapes'
        d.mkdir()
        for name in ('k_U1.0_r0.brep', 'k_U1.0_r1.brep'):
            (d / name).write_text('x', encoding='utf-8')
        res = tmp_path / 'r.jsonl'
        res.write_text(
            '{"kind": "k", "u": 1.0, "repeat": 0, "wall_hash": "aaa"}\n'
            '{"kind": "k", "u": 1.0, "repeat": 1, "wall_hash": "bbb"}\n', encoding='utf-8')
        assert len(corpus.distinct(str(d), str(res))) == 2

    def test_a_record_with_no_hash_is_never_dropped(self, tmp_path):
        d = tmp_path / 'shapes'
        d.mkdir()
        for name in ('k_U1.0_r0.brep', 'k_U1.0_r1.brep'):
            (d / name).write_text('x', encoding='utf-8')
        assert len(corpus.distinct(str(d), str(tmp_path / 'absent.jsonl'))) == 2


class TestSummaries:

    def test_states_counts_each_classification(self):
        rows = [{'state': locate.ANNULUS, 'worst_thin': 0.0},
                {'state': locate.ANNULUS, 'worst_thin': 0.1},
                {'state': locate.SEVERED_ONE, 'worst_thin': None}]
        assert locate.states(rows) == {locate.ANNULUS: 2, locate.SEVERED_ONE: 1}
        assert len(locate.severed(rows)) == 1
        assert locate.worst(rows)['worst_thin'] == 0.1

    def test_worst_is_none_when_nothing_was_readable(self):
        assert locate.worst([{'state': locate.NO_WALL, 'worst_thin': None}]) is None

    def test_the_table_marks_only_readings_over_the_tolerance(self):
        rows = [{'z': -1.0, 'state': locate.ANNULUS, 'loops': 2, 'thickness': 0.599,
                 'worst_thin': 0.001, 'angle_deg': 10.0, 'radius': 5.0},
                {'z': -2.0, 'state': locate.ANNULUS, 'loops': 2, 'thickness': 0.4,
                 'worst_thin': 0.2, 'angle_deg': 30.0, 'radius': 5.0},
                {'z': -3.0, 'state': locate.NO_WALL, 'loops': 0, 'thickness': None,
                 'worst_thin': None, 'angle_deg': None, 'radius': None}]
        text = locate.table(rows, tolerance=0.01)
        assert text.count('THIN') == 1
        assert len(text.splitlines()) == 5

    def test_severed_also_accepts_a_state_only_row(self):
        """`state_profile`'s rows carry no `worst_thin`, and `severed` must still filter them --
        it is the function a dense ring scan reads its verdict from."""
        rows = [{'z': -1.0, 'state': locate.ANNULUS, 'loops': 2, 'area_ratio': 0.9, 'samples': 800},
                {'z': -2.0, 'state': locate.SEVERED_MANY, 'loops': 3, 'area_ratio': None,
                 'samples': 800}]
        assert [r['z'] for r in locate.severed(rows)] == [-2.0]
        assert locate.states(rows) == {locate.ANNULUS: 1, locate.SEVERED_MANY: 1}


# -------------------------------------------------------------------- the axial grid for a scan


class FakeBox(object):
    def __init__(self, lo, hi):
        self.ZMin, self.ZMax = float(lo), float(hi)


class FakeWall(object):
    """Only `BoundBox`, so `dense_grid`'s fallback path is reachable without a kernel."""

    def __init__(self, lo, hi):
        self.BoundBox = FakeBox(lo, hi)


class TestDenseGrid:

    def test_a_spacing_sets_the_station_count_from_the_length(self):
        """**A spacing, not a count.** The axial extent scales with `U` while a defect's extent
        does not, so a fixed count buys a spacing proportional to `U` -- the same error that made
        the first corpus figures six times too large circumferentially."""
        zs = locate.dense_grid(FakeWall(-101.0, 0.0), inset=1.0, spacing_mm=1.0)
        assert len(zs) == 100
        assert zs[0] == pytest.approx(-100.0) and zs[-1] == pytest.approx(-1.0)
        step = zs[1] - zs[0]
        assert step == pytest.approx(1.0, abs=1e-9)

    def test_the_same_spacing_on_a_longer_part_gives_more_stations_not_coarser_ones(self):
        short = locate.dense_grid(FakeWall(-51.0, 0.0), inset=1.0, spacing_mm=1.0)
        long_ = locate.dense_grid(FakeWall(-401.0, 0.0), inset=1.0, spacing_mm=1.0)
        assert len(long_) == 8 * (len(short) - 1) + 1 or len(long_) > len(short)
        assert (long_[1] - long_[0]) == pytest.approx(short[1] - short[0], abs=1e-9)

    def test_a_count_still_works_for_the_existing_callers(self):
        zs = locate.dense_grid(FakeWall(-11.0, -1.0), 5, inset=1.0)
        assert len(zs) == 5
        assert zs[0] == pytest.approx(-10.0) and zs[-1] == pytest.approx(-2.0)

    def test_without_app_it_falls_back_to_the_box(self):
        """Documented rather than silent: a caller that needs to know asks
        `corpus.sectioning_extent` itself."""
        zs = locate.dense_grid(FakeWall(-21.0, -1.0), 3, inset=1.0)
        assert zs[0] == pytest.approx(-20.0) and zs[-1] == pytest.approx(-2.0)

    def test_an_extent_shorter_than_the_inset_returns_one_midpoint_rather_than_raising(self):
        zs = locate.dense_grid(FakeWall(-1.0, 0.0), inset=1.0, spacing_mm=1.0)
        assert len(zs) == 1
        assert zs[0] == pytest.approx(-0.5)

    def test_a_spacing_coarser_than_the_part_still_gives_two_stations(self):
        zs = locate.dense_grid(FakeWall(-4.0, 0.0), inset=1.0, spacing_mm=1000.0)
        assert len(zs) == 2

    def test_a_given_extent_wins_over_the_box(self):
        """The box on these solids is an outer bound only -- a nose wall at `U` = 4 has one twice
        the length of the part -- so a caller that has sectioned for the real extent must be able
        to say so."""
        zs = locate.dense_grid(FakeWall(-400.0, 0.0), inset=1.0, spacing_mm=1.0,
                               extent=(-101.0, 0.0))
        assert len(zs) == 100
        assert zs[0] == pytest.approx(-100.0) and zs[-1] == pytest.approx(-1.0)

    def test_a_given_extent_sections_nothing_at_all(self):
        """**The point of the parameter.** `sectioning_extent` bisects each end to 1e-3 mm, about
        forty sections on a wall whose box spans 400 mm, and a section costs seconds here; a caller
        that already paid must not pay twice. Passing a shape with neither a `BoundBox` nor
        anything sliceable proves no other path was taken."""
        zs = locate.dense_grid(object(), inset=1.0, spacing_mm=1.0, extent=(-11.0, 0.0),
                               App=object())
        assert len(zs) == 10


# ----------------------------------------------------- a no_wall reading is not a hole by itself


def state_row(z, state, loops=2):
    return {'z': float(z), 'state': state, 'loops': loops, 'area_ratio': None, 'samples': 800}


class TestSliceArtifact:
    """**The gap the first real scan fell into.** `Shape.slice()` can return nothing at one exact
    plane on a healthy wall -- section 6.1 records a wall giving no section at `z` = -141.0000 and
    a normal one 0.05 mm away. With zero wires the nesting test and `Part.makeFace` both say "not
    an annulus" and agree, so the kernel cross-check confirms nothing. Only the neighbours can."""

    def test_a_neighbour_returning_an_annulus_means_the_gap_was_the_slicers(self):
        rows = [state_row(-293.98, locate.NO_WALL, loops=0),
                state_row(-294.18, locate.NO_WALL, loops=0),
                state_row(-293.93, locate.ANNULUS)]
        assert locate.is_slice_artifact(rows) is True

    def test_the_wall_absent_either_side_too_is_a_real_gap(self):
        rows = [state_row(-293.98, locate.NO_WALL, loops=0),
                state_row(-294.18, locate.NO_WALL, loops=0),
                state_row(-293.78, locate.NO_WALL, loops=0)]
        assert locate.is_slice_artifact(rows) is False

    def test_the_station_itself_does_not_count_as_its_own_neighbour(self):
        """Row 0 is the station being questioned; if it were counted, a station that is an annulus
        would 'confirm' itself and the test would never fire."""
        assert locate.is_slice_artifact([state_row(-1.0, locate.ANNULUS)]) is False

    def test_a_severed_neighbour_does_not_excuse_the_gap(self):
        """Only a healthy annulus nearby shows the wall is there; a severed neighbour is a worse
        finding, not a reassuring one."""
        rows = [state_row(-1.0, locate.NO_WALL, loops=0),
                state_row(-1.05, locate.SEVERED_MANY, loops=3)]
        assert locate.is_slice_artifact(rows) is False

    def test_no_rows_is_not_an_artifact(self):
        assert locate.is_slice_artifact([]) is False

    def test_the_offsets_straddle_the_station_and_span_the_recorded_case(self):
        """0.05 mm is the distance at which section 6.1's recorded case already returned a normal
        section, so the set has to include it either side, plus a tighter and a looser pair to tell
        how far a real gap extends."""
        assert 0.05 in [abs(d) for d in locate.NEARBY_OFFSETS]
        assert all(-d in locate.NEARBY_OFFSETS for d in locate.NEARBY_OFFSETS)
        assert 0.0 not in locate.NEARBY_OFFSETS, 'the station itself is added by nearby_states'


# ------------------------------------------------------- folding a wall-at-a-time scan together


def wall_record(label, stations=10, annulus=10, severed=(), no_wall=(), artifacts=(),
                disagreements=(), per_station=2.0):
    verdicts = [{'z': float(z), 'slice_artifact': bool(a)} for z, a in artifacts]
    states = {}
    if annulus:
        states[locate.ANNULUS] = annulus
    if severed:
        states[locate.SEVERED_MANY] = len(severed)
    if no_wall:
        states[locate.NO_WALL] = len(no_wall)
    return {'label': label, 'stations': stations, 'states': states,
            'severed': [float(z) for z in severed], 'no_wall': [float(z) for z in no_wall],
            'no_wall_verdicts': verdicts,
            'real_gaps': [v['z'] for v in verdicts if not v['slice_artifact']],
            'kernel_disagreements': list(disagreements), 'axial_mm': 1.0, 'around_mm': 0.2,
            'meta': {'seconds_per_station': per_station, 'faces': 2464}}


class TestScanVerdict:
    """The corpus scan runs a process a wall -- hours in total, and `freecadcmd` exits 0 on an
    uncaught exception -- so the answer is assembled from the per-wall artifacts afterwards."""

    def test_the_station_and_state_counts_add_up_across_walls(self):
        v = locate.scan_verdict([wall_record('a', stations=10, annulus=10),
                                 wall_record('b', stations=20, annulus=20)])
        assert v['walls'] == 2 and v['stations'] == 30
        assert v['states'] == {locate.ANNULUS: 30}
        assert v['clean'] is True

    def test_a_severed_station_is_a_finding_and_names_its_wall(self):
        v = locate.scan_verdict([wall_record('a', annulus=9, severed=(-12.5,))])
        assert v['severed'] == [('a', -12.5)]
        assert v['flagged'] == ['a']
        assert v['clean'] is False

    def test_a_no_wall_that_resolved_as_a_slice_artifact_is_not_a_finding(self):
        """**`Shape.slice()` can return nothing at one exact plane on a healthy wall.** Counting
        that would report the plane the scan happened to choose as a defect in the part."""
        v = locate.scan_verdict([wall_record('a', annulus=9, no_wall=(-7.0,),
                                             artifacts=((-7.0, True),))])
        assert v['real_gaps'] == []
        assert v['artifacts'] == 1
        assert v['clean'] is True
        assert v['states'][locate.NO_WALL] == 1, 'still reported, just not as a defect'

    def test_a_no_wall_absent_either_side_too_is_a_finding(self):
        v = locate.scan_verdict([wall_record('a', annulus=9, no_wall=(-7.0,),
                                             artifacts=((-7.0, False),))])
        assert v['real_gaps'] == [('a', -7.0)]
        assert v['artifacts'] == 0
        assert v['clean'] is False

    def test_a_kernel_disagreement_alone_withholds_the_clean_verdict(self):
        """The nesting test is a proxy, and a proxy that disagrees with the authority has not been
        shown to be measuring the right thing on this geometry."""
        v = locate.scan_verdict([wall_record('a', disagreements=((-3.0, 'severed_arcs', True),))])
        assert v['clean'] is False
        assert v['severed'] == [] and v['real_gaps'] == []

    def test_an_empty_corpus_is_not_silently_clean_of_anything_it_measured(self):
        v = locate.scan_verdict([])
        assert v['walls'] == 0 and v['stations'] == 0 and v['states'] == {}


class TestScanTable:

    def test_every_wall_gets_a_row_and_the_totals_line_sums_them(self):
        text = locate.scan_table([wall_record('tail_shell_U4.0_r0', stations=398, annulus=398),
                                  wall_record('tail_shell_U0.5_r0', stations=48, annulus=48)])
        assert 'tail_shell_U4.0_r0' in text and 'tail_shell_U0.5_r0' in text
        assert '2 wall(s)' in text
        assert '446' in text

    def test_the_cost_column_is_present_because_it_is_what_schedules_the_next_run(self):
        """OQ-DES-CW26 estimated this scan at "a file read" and was wrong by orders of magnitude
        for want of a measured per-station cost."""
        text = locate.scan_table([wall_record('a', per_station=16.3)])
        assert 's/station' in text and '16.3' in text

    def test_a_wall_whose_run_recorded_no_cost_still_gets_a_row(self):
        rec = wall_record('a')
        rec['meta'] = {}
        assert 'a' in locate.scan_table([rec])


# ------------------------------------------------------------------------- against a real wall


@requires_freecad
@requires_corpus
class TestOnARealWall:

    @pytest.fixture
    def tail_u4(self, fc, Part):
        rec = corpus.one('tail_shell', 4.0, 0)
        if rec is None:
            pytest.skip('no tail_shell U=4 wall saved')
        return rec, corpus.load(Part, rec)

    def test_a_fixed_sample_count_misclassifies_a_healthy_large_u_annulus(self, tail_u4, Part, App):
        """**The defect this module was caught by, kept as a regression.** At `U` = 4 a `tail_shell`
        section is about 2 100 mm round, so `N_POINTS` = 720 is roughly 3 mm between samples on a
        0.6 mm wall. The sampled inner loop can then cross outside the sampled outer loop while the
        real wall is intact, and the nesting test calls a healthy annulus severed. Found by
        `agrees_with_kernel` at `z` = -285.2857, where the kernel said annulus.

        This asserts the failure still happens at the fixed count, so that the fix below is shown to
        be the fix and not a coincidence."""
        _rec, wall = tail_u4
        zs = locate.dense_grid(wall, 8)
        bad = locate.agrees_with_kernel(wall, zs, Part, App, n_points=locate.N_POINTS)
        assert bad, 'the fixed-count defect no longer reproduces; this test has outlived its subject'
        assert all(kernel_says for _z, _here, kernel_says in bad), \
            'the disagreement should be this module calling a healthy annulus severed, not the other way'

    def test_fixing_the_spacing_instead_of_the_count_agrees_with_the_kernel(self, tail_u4, Part,
                                                                           App):
        """The fix: derive the count from the station's own perimeter so the spacing is the same in
        millimetres at every `U`."""
        _rec, wall = tail_u4
        zs = locate.dense_grid(wall, 8)
        n = density.counts_for_spacing(density.section_perimeter(wall, zs[0], App=App),
                                       locate.TARGET_SPACING)
        assert locate.agrees_with_kernel(wall, zs, Part, App, n_points=n) == []

    def test_the_worst_station_is_an_annulus_so_the_wall_is_thin_not_severed(self, tail_u4, App):
        """IP-WTM-20's answer for the worst wall in the corpus, measured at a fixed **spacing**. If
        this ever fails, the `U` >= 3 readings are a severed ring and OQ-DES-CW26 owns them rather
        than the thickness work."""
        _rec, wall = tail_u4
        rows = locate.profile(wall, corpus.station_grid(wall), App=App,
                              spacing=locate.TARGET_SPACING)
        bad = locate.severed(rows)
        assert bad == [], 'severed stations: %s' % [(r['z'], r['state']) for r in bad]
        w = locate.worst(rows)
        assert w is not None and w['state'] == locate.ANNULUS
