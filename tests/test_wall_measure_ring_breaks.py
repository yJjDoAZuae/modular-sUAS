"""A break of known axial extent, measured — which is the one test real geometry cannot provide.

OQ-DES-CW26's severed ring is quantified circumferentially and its axial extent is unknown, so
there is no real wall whose answer is known in advance to check a measurement against. A synthetic
classifier over an interval is: the break is exactly where the test says it is, and the measurement
either recovers it or does not.

Every test here is a trap rather than a demonstration, and the sharpest one is
`test_a_break_shorter_than_the_spacing_is_missed_entirely` — because the scan can only see a break
longer than its own station spacing, and a clean scan therefore means "no break longer than this",
never "no break".

See doc/design/cowl_interior_surface.md §4.4 and `cowl.md` OQ-DES-CW26.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import ring_breaks as rb                                  # noqa: E402


def broken_between(z_start, z_end, unreadable=()):
    """A classifier that reports `'broken'` strictly inside `[z_start, z_end]`.

    `unreadable` is a list of `(lo, hi)` spans the classifier refuses, standing in for a section
    the face maker will not build.
    """
    def state_at(z):
        for lo, hi in unreadable:
            if lo <= z <= hi:
                return rb.UNREADABLE
        return rb.BROKEN if z_start <= z <= z_end else rb.ANNULUS
    return state_at


def scan(state_at, z_lo, z_hi, scan_mm):
    """The grid, its states and the extents, the way a real run would compute them."""
    n = rb.station_count(z_lo, z_hi, scan_mm)
    grid = rb.scan_grid(z_lo, z_hi, n)
    states = [state_at(z) for z in grid]
    return grid, states, rb.extents(state_at, grid, states)


class TestTheSamplingIsASpacing:

    def test_the_same_spacing_gives_more_stations_on_a_longer_part(self):
        """**The trap a fixed count sets.** The cowl's length scales with `U`; its wall does not."""
        short = rb.station_count(-50.0, -1.0, 2.0)
        long_ = rb.station_count(-300.0, -1.0, 2.0)
        assert short == 25 and long_ == 151

    def test_a_fixed_count_would_have_scanned_a_long_tail_six_times_coarser(self):
        """The arithmetic behind the rule, so the rule is checkable and not just asserted."""
        at_u05 = rb.missable_mm(rb.scan_grid(-50.0, -1.0, 24))
        at_u30 = rb.missable_mm(rb.scan_grid(-300.0, -1.0, 24))
        assert at_u05 == pytest.approx(2.13, abs=0.01)
        assert at_u30 == pytest.approx(13.0, abs=0.01)
        assert at_u30 / at_u05 == pytest.approx(6.1, abs=0.1)

    def test_a_short_part_still_gets_the_floor_of_stations(self):
        assert rb.station_count(-5.0, -1.0, 2.0) == rb.MIN_STATIONS

    def test_a_long_part_is_capped_rather_than_scanned_without_bound(self):
        assert rb.station_count(-10000.0, 0.0, 2.0) == rb.MAX_STATIONS

    def test_a_nonpositive_spacing_is_refused(self):
        with pytest.raises(ValueError):
            rb.station_count(-50.0, -1.0, 0.0)

    def test_the_grid_spans_the_whole_interval_ends_included(self):
        grid = rb.scan_grid(-300.0, -1.0, 151)
        assert grid[0] == pytest.approx(-300.0) and grid[-1] == pytest.approx(-1.0)
        assert len(grid) == 151

    def test_the_blind_spot_is_the_widest_spacing_and_is_none_for_one_station(self):
        assert rb.missable_mm([0.0]) is None
        assert rb.missable_mm([0.0, 2.0, 5.0]) == pytest.approx(3.0)


class TestFindingTheRuns:

    def test_consecutive_broken_stations_are_one_run(self):
        states = [rb.ANNULUS, rb.BROKEN, rb.BROKEN, rb.BROKEN, rb.ANNULUS]
        assert rb.runs(states) == [(1, 3)]

    def test_two_separated_breaks_are_two_runs(self):
        states = [rb.BROKEN, rb.ANNULUS, rb.BROKEN, rb.BROKEN]
        assert rb.runs(states) == [(0, 0), (2, 3)]

    def test_an_unreadable_station_ends_a_run_rather_than_extending_it(self):
        """A station nobody could classify is not evidence of a break, in either direction."""
        states = [rb.BROKEN, rb.UNREADABLE, rb.BROKEN]
        assert rb.runs(states) == [(0, 0), (2, 2)]

    def test_no_break_is_no_runs(self):
        assert rb.runs([rb.ANNULUS] * 10) == []

    def test_a_wall_broken_end_to_end_is_one_run(self):
        assert rb.runs([rb.BROKEN] * 5) == [(0, 4)]


class TestMeasuringTheExtent:

    def test_a_known_break_is_recovered_to_the_refinement_tolerance(self):
        """The whole point: a 7.0 mm break on a 2.0 mm grid, measured to 0.25 mm."""
        state_at = broken_between(-120.0, -113.0)
        _grid, _states, found = scan(state_at, -300.0, -1.0, 2.0)
        assert len(found) == 1
        assert found[0]['extent_mm'] == pytest.approx(7.0, abs=2 * rb.EXTENT_TOL)
        assert found[0]['z_lo'] == pytest.approx(-120.0, abs=rb.EXTENT_TOL)
        assert found[0]['z_hi'] == pytest.approx(-113.0, abs=rb.EXTENT_TOL)
        assert found[0]['reaches_scan_end'] is False

    def test_the_grid_alone_would_have_overstated_it(self):
        """Why the bisection is not a nicety: the grid's own answer is a whole spacing out."""
        state_at = broken_between(-120.0, -113.0)
        _grid, _states, found = scan(state_at, -300.0, -1.0, 2.0)
        first, last = found[0]['broken_stations_z']
        assert abs(last - first) < found[0]['extent_mm']
        assert found[0]['extent_mm'] - abs(last - first) < 2 * 2.0

    def test_a_break_shorter_than_the_spacing_is_missed_entirely(self):
        """**The sharpest trap here.** A clean scan means "no break longer than the spacing".

        A 0.4 mm break on a 2.0 mm grid can sit between two stations and be seen by neither, and
        the scan reports a healthy wall. `missable_mm` is what a result has to be read against.
        """
        # Placed strictly between two real stations, derived from the grid rather than guessed --
        # a hand-picked height lands *on* a station and the trap quietly stops being one.
        bare = rb.scan_grid(-300.0, -1.0, rb.station_count(-300.0, -1.0, 2.0))
        lo, hi = bare[90] + 0.4, bare[90] + 0.8
        state_at = broken_between(lo, hi)
        grid, states, found = scan(state_at, -300.0, -1.0, 2.0)
        assert found == []
        assert all(s == rb.ANNULUS for s in states)
        assert rb.missable_mm(grid) > (hi - lo)

    def test_a_break_running_to_the_scanned_end_is_flagged_as_a_lower_bound(self):
        state_at = broken_between(-300.0, -290.0)
        _grid, _states, found = scan(state_at, -300.0, -1.0, 2.0)
        assert len(found) == 1 and found[0]['reaches_scan_end'] is True

    def test_two_breaks_are_measured_separately(self):
        def state_at(z):
            if -120.0 <= z <= -113.0 or -60.0 <= z <= -56.0:
                return rb.BROKEN
            return rb.ANNULUS
        _grid, _states, found = scan(state_at, -300.0, -1.0, 2.0)
        assert len(found) == 2
        assert found[0]['extent_mm'] == pytest.approx(7.0, abs=2 * rb.EXTENT_TOL)
        assert found[1]['extent_mm'] == pytest.approx(4.0, abs=2 * rb.EXTENT_TOL)

    def test_an_unreadable_station_inside_a_refinement_is_reported_not_guessed_past(self):
        """The unreadable span sits on the first bisection midpoint and on no station at all.

        It has to miss every station, or the scan itself reports `unreadable` and the run boundary
        moves — which tests something else entirely.
        """
        bare = rb.scan_grid(-300.0, -1.0, rb.station_count(-300.0, -1.0, 2.0))
        first_mid = 0.5 * (bare[90] + bare[91])
        state_at = broken_between(bare[91], -113.0,
                                  unreadable=[(first_mid - 0.05, first_mid + 0.05)])
        _grid, states, found = scan(state_at, -300.0, -1.0, 2.0)
        assert rb.UNREADABLE not in states
        assert len(found) == 1
        assert found[0]['unreadable_in_bracket'] is True

    def test_the_reported_span_never_overstates_what_is_known_broken(self):
        """`edge_z` returns the broken side, so the extent is a span the break does cover."""
        state_at = broken_between(-120.0, -113.0)
        _grid, _states, found = scan(state_at, -300.0, -1.0, 2.0)
        assert state_at(found[0]['z_lo']) == rb.BROKEN
        assert state_at(found[0]['z_hi']) == rb.BROKEN

    def test_a_healthy_wall_measures_no_extent(self):
        _grid, _states, found = scan(lambda z: rb.ANNULUS, -300.0, -1.0, 2.0)
        assert found == []

    def test_refinement_costs_a_few_classifications_an_end_not_a_rescan(self):
        """A full re-scan at 0.25 mm would be 1 196 stations; this must be nothing like that."""
        calls = []
        inner = broken_between(-120.0, -113.0)

        def counted(z):
            calls.append(z)
            return inner(z)
        grid, states, _found = scan(counted, -300.0, -1.0, 2.0)
        refinement = len(calls) - len(grid)
        assert refinement <= 24, refinement
        assert len(states) == 151


class TestEdgeZ:

    def test_it_returns_the_broken_side_of_the_bracket(self):
        state_at = broken_between(-120.0, -113.0)
        z, unreadable = rb.edge_z(state_at, -122.0, -120.0)
        assert unreadable is False
        assert state_at(z) == rb.BROKEN
        assert z == pytest.approx(-120.0, abs=rb.EXTENT_TOL)

    def test_it_honors_a_tighter_tolerance(self):
        state_at = broken_between(-120.0, -113.0)
        coarse, _ = rb.edge_z(state_at, -122.0, -120.0, tol=1.0)
        fine, _ = rb.edge_z(state_at, -122.0, -120.0, tol=0.01)
        assert abs(fine + 120.0) < abs(coarse + 120.0) + 1.0e-9
        assert fine == pytest.approx(-120.0, abs=0.01)

    def test_an_unreadable_mid_point_stops_it_and_says_so(self):
        state_at = broken_between(-120.0, -113.0, unreadable=[(-121.1, -120.9)])
        _z, unreadable = rb.edge_z(state_at, -122.0, -120.0)
        assert unreadable is True
