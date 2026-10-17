"""IP-WTM-26: the wall measured perpendicular to its own inner surface, checked against closed form.

**A new measure in this subsystem has to be checked against a known answer before it is pointed at
the question it was built for.** That is the standing lesson of this whole plan: the incumbent
nearest-point minimum was trusted for months and does not converge, and the area-based mean reads
0.4753 mm where the wall is 0.6. So `normal_distance` is checked here against `truth`'s fixtures,
whose local thickness is exact by construction — concentric cylinders, so an inner-surface point has
a radial normal and the thickness is a difference of two radii.

Three fixtures give three different right answers, and the measure has to get all three:

* `uniform_tube` — 0.6 mm everywhere.
* `thin_patch_tube` — 0.45 mm inside a patch cut into the **outer** surface, 0.6 mm outside it. The
  probe starts on the bore, so this tests that the ray stops where the *far* surface moved.
* `ribbed_tube` — 1.0 mm on a rib raised 0.4 mm off the **inner** surface, where the probe starts on
  the rib itself.

And it has to decline in the cases it cannot read, rather than returning a plausible number: a point
on a crease has two normals, and a ray along the wall never leaves the solid. Both are asserted,
because a measure built to settle whether material is present at a junction must not answer by
assumption at exactly the samples that are at a junction.

See doc/implementation/wall_thickness_measure.md and
doc/design/cowl_interior_surface.md section 6.8.2.1.
"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import candidates                                      # noqa: E402
from wall_measure import normal_distance as nd                           # noqa: E402
from wall_measure import truth                                           # noqa: E402

from conftest import requires_freecad                                    # noqa: E402

#: The bore radius of every fixture here: `R_OUTER` less the nominal wall.
R_BORE = truth.R_OUTER - truth.WALL

#: A reading is checked against closed form to a hundredth of `WALL_TOL`, which is the bisection
#: tolerance `DEPTH_TOL_MM` the measure itself stops at. Tighter would be asserting on noise.
TOL = 2.0 * nd.DEPTH_TOL_MM


# ----------------------------------------------------------------- arithmetic, no vendor


def _row(in_plane, normal, declined=None, z=-15.0, i=0, bounded=True, aligned=True,
         plane_angle_deg=2.0, consistent=True, cos_residual_mm=0.0002):
    return {'z': z, 'i': i, 'in_plane_mm': in_plane, 'thickness_mm': normal,
            'bounded': bounded if normal is not None else None, 'declined': declined,
            'faces': 1, 'normal_residual_mm': 1e-6, 'offsets_used': 8,
            'aligned': aligned, 'plane_angle_deg': plane_angle_deg,
            'consistent': consistent, 'cos_residual_mm': cos_residual_mm,
            'x': 1.0, 'y': 2.0}


class TestCosConsistency:
    """**The discriminator, and it replaced an arbitrary angle cutoff that was discarding real
    readings.** A plane cutting a slab inclined at theta sees `thickness / cos theta`, so wherever
    both instruments read one wall that identity must hold. Measured on a real `tail_shell` it
    separates the populations by over two orders of magnitude — 0.0002–0.0020 mm on the fitted
    interior surface against 0.688–0.737 mm on rib-slot cheeks — while the **angle does not separate
    them at all**: 3.1–30.7° on the fitted surface against 33.2–50.8° on cheeks, a 2.5° gap."""

    def test_the_identity_holds_for_an_inclined_wall(self):
        got = nd.cos_consistency(0.58845, 0.54487, 22.07)
        assert got == pytest.approx(-0.0005, abs=1e-4)

    def test_a_cheek_reading_fails_it_by_two_orders_of_magnitude(self):
        got = nd.cos_consistency(0.56880, 1.05200, 33.19)
        assert got == pytest.approx(0.688, abs=1e-3)

    def test_a_zero_angle_is_the_degenerate_but_valid_case(self):
        """Perpendicular to the layer plane: the two measures must agree exactly."""
        assert nd.cos_consistency(0.6, 0.6, 0.0) == pytest.approx(0.0)

    def test_an_orthogonal_normal_has_no_consistent_reading(self):
        """`cos 90` is zero, so the identity has no finite value — the honest answer is `inf`, not a
        division that raises or a number that looks like a measurement."""
        assert nd.cos_consistency(0.6, 0.6, 90.0) == float('inf')
        assert nd.cos_consistency(0.6, 0.6, 120.0) == float('inf')

    def test_a_nan_angle_is_inf_not_nan(self):
        """`angle_deg` returns `nan` for a degenerate vector; that must become a definite
        inconsistency rather than a `nan` that compares false against every threshold and so would
        silently pass an `abs(residual) <= tol` test."""
        assert nd.cos_consistency(0.6, 0.6, float('nan')) == float('inf')

    def test_a_missing_input_is_none(self):
        assert nd.cos_consistency(None, 0.6, 2.0) is None
        assert nd.cos_consistency(0.6, None, 2.0) is None
        assert nd.cos_consistency(0.6, 0.6, None) is None


class TestNearestFoot:
    """The in-plane shortest path's **direction**, which the distance alone cannot give."""

    def _square(self):
        return np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0],
                         [0.0, 10.0, 0.0]], dtype=float)

    def test_the_foot_lands_on_the_perpendicular(self):
        foot = nd.nearest_foot((3.0, 4.0, 0.0), self._square(), 0)
        assert foot[0] == pytest.approx(3.0)
        assert foot[1] == pytest.approx(0.0)

    def test_the_foot_is_clamped_to_the_segment_ends(self):
        """A point beyond a segment's end projects onto the end, not past it -- the `clip` that
        makes this point-to-*segment* rather than point-to-infinite-line."""
        foot = nd.nearest_foot((-5.0, 3.0, 0.0), self._square(), 0)
        assert foot[0] == pytest.approx(0.0)
        assert foot[1] == pytest.approx(0.0)

    def test_the_segment_index_wraps_like_the_closed_polyline_it_indexes(self):
        """`_segment_nearest` indexes a *closed* polyline, so the last segment joins back to the
        first vertex and an index of `len(poly)` is the zeroth segment again."""
        poly = self._square()
        assert nd.nearest_foot((3.0, 4.0, 0.0), poly, 4)[1] == pytest.approx(0.0)
        assert nd.nearest_foot((3.0, 4.0, 0.0), poly, 3)[0] == pytest.approx(0.0)

    def test_a_degenerate_segment_does_not_divide_by_zero(self):
        poly = np.array([[1.0, 1.0, 0.0], [1.0, 1.0, 0.0], [5.0, 1.0, 0.0]], dtype=float)
        foot = nd.nearest_foot((2.0, 2.0, 0.0), poly, 0)
        assert np.all(np.isfinite(foot))

    def test_it_agrees_with_the_distance_the_package_already_computes(self):
        """**The two must not drift.** `_segment_nearest` gives the distance and the index; this
        gives the foot from the index, so the foot's own distance has to reproduce the first."""
        poly = self._square()
        points = np.array([[3.0, 4.0, 0.0], [9.0, 2.0, 0.0], [-1.0, 11.0, 0.0]], dtype=float)
        dists, which = candidates._segment_nearest(points, poly)
        for k in range(points.shape[0]):
            foot = nd.nearest_foot(points[k], poly, which[k])
            assert float(np.hypot(*(foot - points[k][:2]))) == pytest.approx(float(dists[k]))


class TestAngleDeg:

    def test_parallel_and_perpendicular(self):
        assert nd.angle_deg((1, 0, 0), (2, 0, 0)) == pytest.approx(0.0)
        assert nd.angle_deg((1, 0, 0), (0, 1, 0)) == pytest.approx(90.0)
        assert nd.angle_deg((1, 0, 0), (-1, 0, 0)) == pytest.approx(180.0)

    def test_a_degenerate_vector_gives_nan_not_an_exception(self):
        assert math.isnan(nd.angle_deg((0, 0, 0), (1, 0, 0)))

    def test_it_is_numerically_safe_at_the_ends_of_the_range(self):
        """`arccos` of a dot product that floating point pushed past 1 would raise or return nan;
        the clip is what stops a parallel pair reporting `nan` degrees."""
        v = (1.0, 0.0, 0.0)
        assert nd.angle_deg(v, v) == pytest.approx(0.0)


class TestExoneration:

    def test_a_thin_plane_reading_with_a_full_normal_reading_is_exonerated(self):
        """**The claim section 6.8.2.1 asks for.** The in-plane figure fails the gate's own
        threshold and the normal figure does not, which is what "the in-plane reading was a
        direction artifact" means in numbers."""
        got = nd.exoneration([_row(0.5667, 0.6012)], nominal=0.6, tol=0.01)
        assert len(got['exonerated']) == 1
        assert got['confirmed'] == []

    def test_both_readings_thin_is_confirmed_not_exonerated(self):
        """The opposite result and just as important: the material really is absent, and no
        exclusion or change of direction rescues it."""
        got = nd.exoneration([_row(0.5667, 0.5701)], nominal=0.6, tol=0.01)
        assert got['exonerated'] == []
        assert len(got['confirmed']) == 1

    def test_a_sample_the_plane_already_passes_is_neither(self):
        """Only samples the incumbent fails are at issue; a passing one has nothing to explain."""
        got = nd.exoneration([_row(0.5995, 0.6001)], nominal=0.6, tol=0.01)
        assert got['exonerated'] == [] and got['confirmed'] == []
        assert got['read'] == 1

    def test_an_unbounded_reading_is_not_counted_as_a_thickness(self):
        """A probe still inside the solid at the limit has a lower bound, not a measurement, and
        counting it would exonerate a wall on the strength of a ray that ran along it."""
        rows = [_row(0.5667, 3.0, declined='unbounded', bounded=False)]
        got = nd.exoneration(rows, nominal=0.6, tol=0.01)
        assert got['read'] == 0
        assert got['exonerated'] == [] and got['confirmed'] == []
        assert got['declined'] == {'unbounded': 1}

    def test_declined_samples_are_counted_by_reason(self):
        rows = [_row(0.56, None, declined='on_crease'), _row(0.57, None, declined='on_crease'),
                _row(0.58, None, declined='no_normal'), _row(0.59, 0.61)]
        got = nd.exoneration(rows, nominal=0.6, tol=0.01)
        assert got['declined'] == {'on_crease': 2, 'no_normal': 1}
        assert got['read'] == 1

    def test_the_worst_of_each_column_is_reported(self):
        rows = [_row(0.52, 0.61), _row(0.58, 0.59)]
        got = nd.exoneration(rows, nominal=0.6, tol=0.01)
        assert got['worst_in_plane_mm'] == pytest.approx(0.52)
        assert got['worst_normal_mm'] == pytest.approx(0.59)


class TestObliqueSamples:
    """**The correction the first real run forced.** A normal orthogonal to the in-plane shortest
    path is not measuring the same wall, and a depth taken along it must not be read as the in-plane
    figure's correction. On a `nose_cowl_shell` the thin samples came back with normals of exactly
    `(1, 0, 0)` where the outward direction is `-y` -- rib-slot cheeks, planar because the side
    slabs sit at constant `x` -- reading 0.95 and 1.05 mm on a 0.6 mm wall.

    The test is now `cos_consistency` rather than the angle; see `TestCosConsistency`."""

    def test_an_oblique_sample_is_not_counted_as_exonerating(self):
        rows = [_row(0.5688, 1.0520, consistent=False, cos_residual_mm=0.688,
                     plane_angle_deg=33.19, declined='inconsistent')]
        got = nd.exoneration(rows, nominal=0.6, tol=0.01)
        assert got['exonerated'] == []
        assert got['confirmed'] == []
        assert len(got['oblique']) == 1
        assert got['aligned'] == 0

    def test_an_oblique_sample_does_not_set_the_worst_normal_figure(self):
        """A 1.05 mm depth across a slot must not become "the worst normal reading" on a wall whose
        aligned samples read 0.59."""
        rows = [_row(0.5688, 1.0520, consistent=False, cos_residual_mm=0.688,
                     plane_angle_deg=33.19, declined='inconsistent'),
                _row(0.5900, 0.5950)]
        got = nd.exoneration(rows, nominal=0.6, tol=0.01)
        assert got['worst_normal_mm'] == pytest.approx(0.5950)

    def test_a_sample_measured_without_a_plane_direction_stays_comparable(self):
        """`aligned` is `None` when no in-plane direction was supplied -- the direct
        `normal_thickness` call the closed-form tests make -- and that must not be read as
        oblique."""
        rows = [_row(0.5667, 0.6012, consistent=None, cos_residual_mm=None, plane_angle_deg=None)]
        got = nd.exoneration(rows, nominal=0.6, tol=0.01)
        assert len(got['exonerated']) == 1
        assert got['oblique'] == []

    def test_a_verdict_of_only_oblique_samples_establishes_nothing(self):
        """Every thin sample being on a cheek means the measure has not shown the wall is sound --
        it has shown the in-plane figures were never wall thicknesses. A real finding, and not an
        exoneration."""
        rows = [_row(0.5688, 1.0520, consistent=False, cos_residual_mm=0.688,
                     plane_angle_deg=33.19, declined='inconsistent')]
        got = nd.normal_verdict([{'z': -15.0, 'rows': rows, 'loops': 2}], nominal=0.6)
        assert got['established'] is False
        assert got['n_oblique'] == 1
        assert any('bounded normal reading' in r for r in got['vacuous_because'])

    def test_the_angle_is_in_the_table(self):
        rows = [_row(0.5688, 1.0520, consistent=False, cos_residual_mm=0.688,
                     plane_angle_deg=33.19, declined='inconsistent')]
        text = nd.normal_table([{'z': -15.0, 'rows': rows}], nominal=0.6)
        assert '33.19' in text and 'inconsistent' in text


class TestTheSurfaceCensus:
    """**The half of the question that can be asked of every thin sample, and on a real wall the
    decisive half.** A reading taken on a cut face -- a rib-slot cheek, a cell-cut face -- is not a
    wall thickness: measured on a `nose_cowl_shell` wall, the boundary is 480 planes to 40
    B-splines, and the thin samples' nearest outer points sit at exactly `buttress_cut_thickness`/2,
    i.e. across a slot mouth."""

    def _station(self, surfaces, thin, rows=()):
        return {'z': -15.0, 'rows': list(rows), 'loops': 2, 'thin_in_plane': thin,
                'thin_surfaces': dict(surfaces)}

    def test_a_census_with_nothing_on_the_fitted_surface_settles_it(self):
        station = self._station({'Part::GeomPlane': 12}, 12)
        got = nd.normal_verdict([station], nominal=0.6)
        assert got['thin_on_fitted'] == 0
        assert got['census_settles'] is True
        assert got['established'] is True, got['vacuous_because']

    def test_a_thin_sample_on_the_fitted_surface_does_not_let_the_census_settle_it(self):
        """One reading on the real inner boundary and the question is open again, whatever the cut
        faces do -- that sample is a wall thickness and it is under tolerance."""
        station = self._station({'Part::GeomPlane': 11, nd.FITTED_SURFACE: 1}, 12)
        got = nd.normal_verdict([station], nominal=0.6)
        assert got['thin_on_fitted'] == 1
        assert got['census_settles'] is False
        assert got['established'] is False

    def test_an_absent_census_cannot_settle_anything(self):
        """`census=False`, or a station with no thin samples to classify: silence, not a pass."""
        got = nd.normal_verdict([self._station({}, 12)], nominal=0.6)
        assert got['census_settles'] is False
        assert got['established'] is False

    def test_an_unplaced_sample_blocks_the_census_route(self):
        """**The hole the first version had.** `census_settles` required only that nothing was placed
        on the fitted surface, so a wall with twenty `off_surface` samples would have been called
        settled — and an unplaced sample is exactly one that was never asked whether it is on the
        fitted surface. It happened not to change the real tail's answer, because four placed samples
        blocked it anyway, but the guard was unsound."""
        station = self._station({'Part::GeomPlane': 352, 'off_surface': 20}, 372)
        got = nd.normal_verdict([station], nominal=0.6)
        assert got['thin_unplaced'] == 20
        assert got['census_settles'] is False
        assert got['established'] is False

    def test_an_ambiguous_crease_sample_blocks_it_too(self):
        station = self._station({'Part::GeomPlane': 371, 'on_crease': 1}, 372)
        assert nd.normal_verdict([station], nominal=0.6)['census_settles'] is False

    def test_a_loosely_placed_fitted_sample_blocks_it(self):
        """A sample that needed 1e-4 mm of slack to land on the fitted surface is still a reading on
        the fitted surface, and matching the class name exactly would have missed it."""
        station = self._station({'Part::GeomPlane': 11,
                                 nd.FITTED_SURFACE + ' (loose)': 1}, 12)
        got = nd.normal_verdict([station], nominal=0.6)
        assert got['thin_on_fitted'] == 0, 'the strict count stays strict'
        assert got['thin_on_fitted_any'] == 1
        assert got['census_settles'] is False

    def test_the_census_sums_over_stations(self):
        stations = [self._station({'Part::GeomPlane': 3}, 3),
                    self._station({'Part::GeomPlane': 4, 'on_crease': 2}, 6)]
        got = nd.normal_verdict(stations, nominal=0.6)
        assert got['thin_surfaces'] == {'Part::GeomPlane': 7, 'on_crease': 2}
        assert got['thin_total'] == 9

    def test_a_normal_reading_still_establishes_it_without_a_census(self):
        """The two routes are independent: a bounded aligned reading is enough on its own."""
        got = nd.normal_verdict([{'z': -15.0, 'rows': [_row(0.5667, 0.6012)], 'loops': 2}],
                                nominal=0.6)
        assert got['established'] is True
        assert got['census_settles'] is False


class TestTheSelectorMeasurement:
    """**OQ-DES-CW33 alternative 2's own prerequisite.** That alternative uses the cheap in-plane
    measure as a search and re-measures the worst `N` samples a station in 3-D, so it stands or falls
    on whether in-plane severity ranks the readings that are wall thicknesses near the top. On the
    one real wall measured it does not: the four that matter were nowhere near any station's twelve
    worst and had to be selected by face class instead."""

    def _station(self, thin, ranks, z=-15.0):
        return {'z': z, 'thin_in_plane': thin, 'fitted_ranks': list(ranks), 'rows': []}

    def test_ranks_come_out_of_the_census_in_severity_order(self):
        per_sample = ['Part::GeomPlane', nd.FITTED_SURFACE, 'Part::GeomPlane', nd.FITTED_SURFACE]
        assert nd.surface_ranks(per_sample) == [1, 3]
        assert nd.surface_ranks(per_sample, 'Part::GeomPlane') == [0, 2]

    def test_a_loosely_placed_sample_counts_in_the_ranks(self):
        """**Measured 2026-10-15: on three real walls every sample no face claimed at 1e-6 mm turned
        out to be on the fitted surface at 1e-4** — 20 of 20, 86 of 86, 336 of 336 — because
        `distToShape` to a planar face is exact while to a trimmed B-spline it is an iterative solve.
        Exact class matching would therefore drop the majority of the class on two of those walls."""
        per_sample = ['Part::GeomPlane', nd.FITTED_SURFACE + ' (loose)', nd.FITTED_SURFACE]
        assert nd.surface_ranks(per_sample) == [1, 2]

    def test_the_needed_n_is_one_past_the_deepest_rank(self):
        """`N` has to *include* the deepest sample, so a pass with `worst` equal to the rank itself
        would miss it by one -- the kind of off-by-one that would silently under-size the gate."""
        got = nd.selector_verdict([self._station(55, [41, 48, 53])])
        assert got['deepest_rank'] == 53
        assert got['needed_n'] == 54
        assert got['established'] is True

    def test_it_takes_the_deepest_across_every_station(self):
        got = nd.selector_verdict([self._station(55, [9]), self._station(62, [60], z=-22.0)])
        assert got['needed_n'] == 61
        assert got['stations_with_kind'] == 2
        assert got['thin_total'] == 117

    def test_a_station_with_no_such_sample_counts_in_the_total_but_not_the_depth(self):
        got = nd.selector_verdict([self._station(33, []), self._station(55, [4], z=-22.0)])
        assert got['needed_n'] == 5
        assert got['stations_with_kind'] == 1
        assert got['thin_total'] == 88

    def test_a_wall_with_no_fitted_reading_anywhere_establishes_nothing(self):
        """**The ninth vacuity guard in this subsystem.** A wall whose thin readings are all on cut
        faces says nothing about how to rank the ones that are not, and a `needed_n` of `None`
        reported as a small number would under-size the gate on no evidence at all."""
        got = nd.selector_verdict([self._station(33, []), self._station(55, [], z=-22.0)])
        assert got['established'] is False
        assert got['needed_n'] is None
        assert any('cannot be judged' in r for r in got['vacuous_because'])

    def test_a_station_that_ran_no_census_is_not_read_as_having_none(self):
        """`fitted_ranks` is `None` when nobody looked and `[]` when the census found none. Treating
        the first as the second would report a clean ranking from a run that did not rank anything."""
        got = nd.selector_verdict([{'z': -15.0, 'thin_in_plane': 40, 'fitted_ranks': None}])
        assert got['stations'] == 0
        assert got['established'] is False
        assert any('no station reported a rank census' in r for r in got['vacuous_because'])

    def test_the_fraction_of_the_thin_set_a_pass_would_have_to_cover_is_reported(self):
        """The cost of alternative 2 is `N` against how many thin samples there are, so the ratio is
        the figure that decides whether it is a confirmation pass or a re-measurement of everything."""
        got = nd.selector_verdict([self._station(55, [53])])
        assert got['rows'][0]['fraction'] == pytest.approx(54.0 / 55.0)

    def test_the_table_renders(self):
        got = nd.selector_verdict([self._station(55, [41, 48, 53])])
        text = nd.rank_table(got)
        assert '41, 48, 53' in text and '54' in text


class TestTheVacuityGuard:

    def _stations(self, rows):
        return [{'z': -15.0, 'rows': rows, 'loops': 2, 'declined': None}]

    def test_a_real_result_is_established(self):
        got = nd.normal_verdict(self._stations([_row(0.5667, 0.6012)]), nominal=0.6)
        assert got['established'] is True
        assert got['vacuous_because'] == []
        assert got['n_exonerated'] == 1

    def test_a_compliant_specimen_establishes_nothing_and_says_so(self):
        """**Section 6.1's first caution, and the eighth time this subsystem has needed it.** A
        wall with no thin sample cannot test an explanation of thinness; a verdict that reported
        success here would be reporting a pass from having measured nothing."""
        got = nd.normal_verdict(self._stations([_row(0.5995, 0.6001)]), nominal=0.6)
        assert got['established'] is False
        assert any('nothing to explain' in r for r in got['vacuous_because'])

    def test_all_samples_declining_is_silence_not_exoneration(self):
        """If every thin sample is on a crease, the measure has not shown material is present — it
        has shown it cannot see. Those are different answers and must not share a verdict."""
        rows = [_row(0.56, None, declined='on_crease'), _row(0.57, None, declined='on_crease')]
        got = nd.normal_verdict(self._stations(rows), nominal=0.6)
        assert got['established'] is False
        assert any('bounded normal reading' in r for r in got['vacuous_because'])
        assert got['thin_in_plane'] == 2
        assert got['census_settles'] is False

    def test_an_empty_scan_is_vacuous(self):
        got = nd.normal_verdict([], nominal=0.6)
        assert got['established'] is False
        assert any('no sample was measured' in r for r in got['vacuous_because'])

    def test_the_table_renders_a_read_row_and_a_declined_one(self):
        rows = [_row(0.5667, 0.6012), _row(0.57, None, declined='on_crease')]
        text = nd.normal_table(self._stations(rows), nominal=0.6)
        assert 'on_crease' in text and 'read' in text
        assert '+0.03450' in text or '+0.0345' in text


# ----------------------------------------------------------------- against closed-form geometry


@pytest.fixture
def uniform(fc, Part, App):
    return truth.uniform_tube(Part, App)


@pytest.fixture
def patched(fc, Part, App):
    return truth.thin_patch_tube(Part, App)


@pytest.fixture
def ribbed(fc, Part, App):
    return truth.ribbed_tube(Part, App)


def _bore_point(radius, angle=0.0, z=truth.HEIGHT / 2.0):
    return (radius * math.cos(angle), radius * math.sin(angle), z)


@requires_freecad
class TestAgainstClosedForm:

    def test_the_uniform_tube_reads_its_nominal_wall(self, uniform, App, Part):
        """The simplest case, and the one that would expose a sign error, an off-by-one in the
        bisection bracket, or a normal taken on the wrong surface."""
        point = _bore_point(R_BORE)
        got = nd.normal_thickness(uniform.shape, point, App, Part, nominal=truth.WALL)
        assert got['declined'] is None, got
        assert got['bounded'] is True
        assert got['thickness_mm'] == pytest.approx(truth.WALL, abs=TOL)

    def test_it_agrees_with_the_fixtures_own_truth_function(self, uniform, App, Part):
        """Not just the constant: the same number `true_thickness_at` reports, at several places."""
        for angle in (0.0, 1.0, 2.5, -2.0):
            point = _bore_point(R_BORE, angle)
            expect = uniform.true_thickness_at(*point)
            got = nd.normal_thickness(uniform.shape, point, App, Part, nominal=truth.WALL)
            assert got['thickness_mm'] == pytest.approx(expect, abs=TOL), (angle, got)

    def test_a_patch_in_the_outer_surface_shortens_the_reading(self, patched, App, Part):
        """The probe starts on the bore, which the patch does not touch, so this tests that the ray
        stops where the **far** surface moved rather than where the near one is."""
        feature = patched.features[0]
        point = _bore_point(R_BORE, 0.0, feature['z_mid'])
        got = nd.normal_thickness(patched.shape, point, App, Part, nominal=truth.WALL)
        assert got['declined'] is None, got
        assert got['thickness_mm'] == pytest.approx(feature['thickness'], abs=TOL)
        assert got['thickness_mm'] == pytest.approx(
            patched.true_thickness_at(*point), abs=TOL)

    def test_away_from_the_patch_the_same_tube_reads_nominal(self, patched, App, Part):
        """The converse of the row above: a measure that read 0.45 everywhere would pass that test
        and be useless."""
        point = _bore_point(R_BORE, math.pi, patched.features[0]['z_mid'])
        got = nd.normal_thickness(patched.shape, point, App, Part, nominal=truth.WALL)
        assert got['thickness_mm'] == pytest.approx(truth.WALL, abs=TOL)

    def test_a_rib_on_the_inner_surface_lengthens_the_reading(self, ribbed, App, Part):
        """Here the probe starts on the **rib's** own surface, 0.4 mm proud of the bore, so the
        reading has to be 1.0 mm. A measure that always started from the nominal bore radius would
        report 0.6 and look right on the other two fixtures."""
        feature = ribbed.features[0]
        radius = R_BORE + feature['delta']          # delta is negative: the bore moves inward
        point = _bore_point(radius, 0.0, feature['z_mid'])
        got = nd.normal_thickness(ribbed.shape, point, App, Part, nominal=truth.WALL)
        assert got['declined'] is None, got
        assert got['thickness_mm'] == pytest.approx(
            ribbed.true_thickness_at(*point), abs=TOL), got
        assert got['thickness_mm'] > truth.WALL

    def test_the_ray_is_reported_as_exiting_through_the_far_surface(self, uniform, App, Part):
        """**What the ray leaves through decides what the depth is a thickness *of*.** On a plain
        tube it must be the outer cylinder; on a real wall a ray can exit into a rib slot instead,
        which makes the figure a web thickness rather than a wall thickness to the exterior.

        The tolerance here is the bisection's, not the entry's, and getting that wrong made all four
        readings on a real `tail_shell` report `off_surface`: the exit point is within `DEPTH_TOL_MM`
        = 1e-4 mm of the boundary, a hundred times further out than `ON_FACE_TOL`.
        """
        point = _bore_point(R_BORE)
        got = nd.normal_thickness(uniform.shape, point, App, Part, nominal=truth.WALL)
        assert got['exit_surface'] not in (None, 'off_surface'), got
        assert got['exit_faces'] == 1
        # The outer surface of every fixture here is a cylinder, and the exit lands on it.
        assert got['exit_point'][0] == pytest.approx(truth.R_OUTER, abs=10.0 * TOL)

    def test_the_reading_is_insensitive_to_the_bisection_limit(self, uniform, App, Part):
        """A limit that happened to sit near the answer would make the figure an artifact of the
        search rather than of the wall."""
        point = _bore_point(R_BORE)
        a = nd.normal_thickness(uniform.shape, point, App, Part, nominal=truth.WALL, limit=1.5)
        b = nd.normal_thickness(uniform.shape, point, App, Part, nominal=truth.WALL, limit=6.0)
        assert a['thickness_mm'] == pytest.approx(b['thickness_mm'], abs=TOL)


@requires_freecad
class TestWhenItDeclines:

    def test_a_point_on_a_shared_edge_is_declined_as_a_crease(self, uniform, App, Part):
        """**The case the junction question turns on.** The top rim of the bore lies on both the
        bore cylinder and the end annulus, so it has two normals and two defensible readings. The
        measure must name that rather than pick one, because the real samples at issue on a
        `tail_shell` are exactly the ones on a crease."""
        point = _bore_point(R_BORE, 0.0, truth.HEIGHT)
        got = nd.normal_thickness(uniform.shape, point, App, Part, nominal=truth.WALL)
        assert got['declined'] == 'on_crease'
        assert got['faces'] >= 2
        assert got['thickness_mm'] is None

    def test_a_point_off_the_surface_is_declined_not_measured(self, uniform, App, Part):
        """A probe in the middle of the wall is inside the solid, and measuring a wall outward from
        an interior point would return a number with no meaning."""
        point = _bore_point(R_BORE + 0.3)
        got = nd.normal_thickness(uniform.shape, point, App, Part, nominal=truth.WALL)
        assert got['declined'] in ('off_surface', 'not_entered'), got
        assert got['thickness_mm'] is None

    def test_a_ray_along_the_wall_is_reported_as_unbounded(self, uniform, App, Part):
        """`exit_depth` is asked directly here, along the axis from a bore point: the solid runs
        10 mm that way and the limit is 3, so the honest answer is a lower bound."""
        point = _bore_point(R_BORE, 0.0, 2.0)
        depth, bounded = nd.exit_depth(uniform.shape, point, (0.0, 0.0, 1.0), App,
                                       limit=3.0, step=nd.ENTRY_STEP_MM)
        assert bounded is False
        assert depth == pytest.approx(3.0)


@requires_freecad
class TestEntryDirection:

    def test_an_inward_pointing_normal_is_turned_round(self, uniform, App, Part):
        """`face_normal`'s sign comes from a singular vector and is arbitrary, so which way is into
        the material has to be established. Both signs must give the same reading."""
        point = _bore_point(R_BORE)
        out, step = nd.entry_direction(uniform.shape, point, (-1.0, 0.0, 0.0), App)
        assert out is not None and step is not None
        assert out[0] == pytest.approx(1.0, abs=1e-12)

    def test_an_already_outward_normal_is_left_alone(self, uniform, App, Part):
        point = _bore_point(R_BORE)
        out, _step = nd.entry_direction(uniform.shape, point, (1.0, 0.0, 0.0), App)
        assert out[0] == pytest.approx(1.0, abs=1e-12)

    def test_a_point_inside_the_material_is_refused_rather_than_oriented(self, uniform, App, Part):
        """Material lies both ways from an interior point, so neither direction is "into the wall"
        and a reading from there would be meaningless."""
        point = _bore_point(R_BORE + 0.3)
        out, step = nd.entry_direction(uniform.shape, point, (1.0, 0.0, 0.0), App)
        assert out is None and step is None

    def test_a_degenerate_normal_is_refused(self, uniform, App, Part):
        point = _bore_point(R_BORE)
        assert nd.entry_direction(uniform.shape, point, (0.0, 0.0, 0.0), App) == (None, None)


@requires_freecad
class TestStationScan:

    def test_a_uniform_tube_yields_no_thin_samples_and_a_vacuous_verdict(self, uniform, App, Part):
        """End to end on a wall that is exactly nominal: nothing is thin, so nothing is measured and
        the verdict says it established nothing. This is the shape of the seventh false CLEAN this
        subsystem produced, asserted here so this measure cannot repeat it."""
        station = nd.station_normals(uniform.shape, truth.HEIGHT / 2.0, truth.WALL, App, Part,
                                     n_points=360)
        assert station['thin_in_plane'] == 0
        assert station['rows'] == []
        verdict = nd.normal_verdict([station], nominal=truth.WALL)
        assert verdict['established'] is False

    def test_discretization_sag_is_not_mistaken_for_a_thin_wall(self, uniform, App, Part):
        """**The defect this measure shipped with for an hour, and what the test above caught.**
        Selecting every sample under *nominal* picked all 360 on an exactly-0.6 mm tube: both loops
        are polygons, so the outer one's chords cut inside the true circle and every reading is
        0.59962 — a sag of 0.000381 mm at `R` = 10 with 360 points. "Thin" has to mean "fails the
        gate", `nominal - WALL_TOL`, or this measure's sample set is sub-micron noise and the
        samples that actually fail are buried in it. The same bias is measured on `CHECK_ARC` in
        section 6.8.3, in the construction rather than here.
        """
        from wall_measure import candidates, sections
        outer, inner = sections.station_loops(uniform.shape, truth.HEIGHT / 2.0, 360, App=App)
        _pts, dists = candidates.nearest_point_min(outer, inner)
        assert float(dists.min()) < truth.WALL, 'the sag should make every reading short'
        assert float(dists.min()) > truth.WALL - nd.WALL_TOL, 'but only by sub-micron amounts'
        assert nd.thin_samples(outer, inner, truth.WALL) == []
        # And the margin is what does it: ask for "anything under nominal" and they all come back.
        assert len(nd.thin_samples(outer, inner, truth.WALL, margin=0.0)) == 360

    def test_a_patched_tube_yields_thin_samples_that_the_normal_confirms(self, patched, App, Part):
        """And the converse, on a wall with a real 0.15 mm thin patch: the in-plane measure finds it,
        the normal measure agrees it is genuinely thin, and the verdict is `confirmed` rather than
        `exonerated` — which is the right answer here, because the patch is real missing material."""
        feature = patched.features[0]
        station = nd.station_normals(patched.shape, feature['z_mid'], truth.WALL, App, Part,
                                     n_points=720, worst=4)
        assert station['thin_in_plane'] > 0
        verdict = nd.normal_verdict([station], nominal=truth.WALL)
        assert verdict['established'] is True
        assert verdict['n_confirmed'] > 0
        assert verdict['n_exonerated'] == 0
        assert verdict['worst_normal_mm'] == pytest.approx(feature['thickness'], abs=0.01)
