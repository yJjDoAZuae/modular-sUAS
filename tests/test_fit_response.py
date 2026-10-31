"""Tests for the row-nudge probe's measurement core.

Every test here is a property OQ-DES-CW26's own numbers depend on. The two that matter most are
`test_the_response_is_exactly_zero_at_every_other_row`, which is the structural reason a nudge
cannot reach a target station that is itself a row, and
`test_a_uniform_stack_decays_about_the_figure_section_4_4_quotes`, which is where
`cowl_interior_surface.md`'s "about 3.7x per station" comes from.
"""
import io
import math
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'src', 'Fuselage', 'tools'))

from wall_measure import fit_response as fr                              # noqa: E402

COWL_INTERIOR = os.path.join(REPO, 'src', 'Fuselage', 'freecad', 'cowl_interior.py')


def square_rows(zs, n=48, size=10.0):
    """A plain centered ring per station: enough for the algebraic properties."""
    rows = []
    for z in zs:
        pts = [(size * math.cos(2.0 * math.pi * i / n),
                size * math.sin(2.0 * math.pi * i / n)) for i in range(n)]
        rows.append((float(z), pts))
    return rows


class _V(object):
    """The three fields `response` asks of a point."""

    def __init__(self, x, y, z):
        self.x, self.y, self.z = float(x), float(y), float(z)


class _LinearFit(object):
    """A degree-1 interpolant through the rows: the simplest thing that is still an interpolant.

    It is not the kernel's C2 fit, and it is not meant to be. What it shares with the kernel is the
    only property `response` relies on -- that it passes through its own rows -- so it is the right
    stand-in for testing the plumbing without a FreeCAD process.
    """

    def __init__(self, rows):
        self.zs = [float(z) for z, _pts in rows]
        self.pts = [np.asarray(pts, dtype=float) for _z, pts in rows]
        self.params = fr.uparams(rows)

    def value(self, u, v):
        params = self.params
        k = int(np.clip(np.searchsorted(params, u) - 1, 0, len(params) - 2))
        span = params[k + 1] - params[k]
        f = 0.0 if span <= 0.0 else (u - params[k]) / span
        a, b = self.pts[k], self.pts[k + 1]
        n = len(a)
        t = v * (n - 1)
        j = int(min(max(math.floor(t), 0), n - 2))
        g = t - j
        ra = a[j] * (1.0 - g) + a[j + 1] * g
        rb = b[j] * (1.0 - g) + b[j + 1] * g
        p = ra * (1.0 - f) + rb * f
        return _V(p[0], p[1], self.zs[k] * (1.0 - f) + self.zs[k + 1] * f)


# --- the nudge itself ------------------------------------------------------------------------

def test_a_nudge_moves_every_point_by_exactly_the_displacement():
    pts = [(10.0, 0.0), (0.0, 10.0), (-10.0, 0.0), (0.0, -10.0)]
    moved = fr.nudge(pts, 0.03)
    for (ax, ay), (bx, by) in zip(pts, moved):
        assert math.hypot(bx - ax, by - ay) == pytest.approx(0.03, abs=1e-12)


def test_a_nudge_is_outward_not_in_some_fixed_direction():
    moved = fr.nudge([(10.0, 0.0), (-10.0, 0.0)], 0.5)
    assert moved[0][0] == pytest.approx(10.5)
    assert moved[1][0] == pytest.approx(-10.5)


def test_a_point_on_the_center_has_no_outward_direction_and_is_left_alone():
    # A real row never has one, but inventing a direction here would put a silent arbitrary
    # choice inside a probe whose whole output is a displacement.
    pts = [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (0.0, 0.0)]
    assert fr.nudge(pts, 0.1)[4] == (0.0, 0.0)


def test_a_radial_nudge_from_the_origin_keeps_a_row_end_on_its_construction_plane():
    # The trap that cost five wasted tail builds. A cowl row is the symmetry cell's open arc, its
    # two ends lying on construction planes that all pass through the origin, and the patch is
    # closed across those planes. Displacing from the origin moves each point along a ray inside
    # those planes, so an end on the plane y = 0 stays on it.
    pts = [(18.0100, 0.0), (10.0, 14.0), (-12.0, 18.1), (-25.0, 0.0)]   # a real tail row's ends
    moved = fr.nudge(pts, 0.03, center=(0.0, 0.0))
    assert moved[0][1] == pytest.approx(0.0, abs=1e-12)
    assert moved[-1][1] == pytest.approx(0.0, abs=1e-12)
    assert moved[0][0] > pts[0][0]                       # and it did move, outward
    assert moved[-1][0] < pts[-1][0]


def test_a_nudge_from_the_arc_centroid_lifts_the_ends_off_the_plane():
    # The converse, and the reason the default is documented as wrong for a cell row: the arc's
    # centroid sits near (-3.5, 13.0) on a real tail row, nowhere near the axis, so the ends
    # acquire a y component. Measured consequence: `_side_caps` fails with "Failed to create face
    # from wire", identically at every magnitude, after the build has been paid for.
    pts = [(18.0100, 0.0), (10.0, 14.0), (-12.0, 18.1), (-25.0, 0.0)]
    moved = fr.nudge(pts, 0.03)
    assert abs(moved[0][1]) > 1e-6
    assert abs(moved[-1][1]) > 1e-6


def test_plane_ends_held_catches_the_lifted_end_in_microseconds():
    rows = [(0.0, [(18.01, 0.0), (10.0, 14.0), (-25.0, 0.0)])]
    normals = [(0.0, 1.0)]                                 # the tail's one plane, y = 0
    assert fr.plane_ends_held(rows, fr.nudge_rows(rows, 0, 0.03, center=(0.0, 0.0)), normals)
    assert not fr.plane_ends_held(rows, fr.nudge_rows(rows, 0, 0.03), normals)


def test_plane_ends_held_tests_the_plane_and_not_the_position():
    # A radial nudge is supposed to slide an end along its plane: (18.0100, 0) becomes
    # (18.0400, 0), which has moved and is still on y = 0. This function's first version demanded
    # the position be unchanged and so rejected the correct behavior.
    rows = [(0.0, [(18.01, 0.0), (10.0, 14.0), (-25.0, 0.0)])]
    out = fr.nudge_rows(rows, 0, 0.03, center=(0.0, 0.0))
    assert out[0][1][0][0] != rows[0][1][0][0]             # the end did move
    assert fr.plane_ends_held(rows, out, [(0.0, 1.0)])     # and it is still on its plane


def test_plane_ends_held_rejects_a_stack_of_the_wrong_shape():
    rows = [(0.0, [(1.0, 0.0), (0.0, 1.0)])]
    assert not fr.plane_ends_held(rows, [], [(0.0, 1.0)])
    assert not fr.plane_ends_held(rows, [(0.0, [(1.0, 0.0)])], [(0.0, 1.0)])


def test_nudging_a_stack_does_not_modify_the_stack_it_was_given():
    rows = square_rows([0.0, 1.0, 2.0])
    before = [list(pts) for _z, pts in rows]
    fr.nudge_rows(rows, 1, 0.01)
    assert [list(pts) for _z, pts in rows] == before


def test_nudging_a_stack_leaves_every_other_row_identical():
    rows = square_rows([0.0, 1.0, 2.0])
    out = fr.nudge_rows(rows, 1, 0.01)
    assert list(out[0][1]) == list(rows[0][1])
    assert list(out[2][1]) == list(rows[2][1])
    assert list(out[1][1]) != list(rows[1][1])


def test_a_row_outside_the_stack_is_an_error_not_a_wrap():
    rows = square_rows([0.0, 1.0])
    with pytest.raises(IndexError):
        fr.nudge_rows(rows, 2, 0.01)
    with pytest.raises(IndexError):
        fr.nudge_rows(rows, -1, 0.01)


# --- the parameters, and the duplicate that must not drift ----------------------------------

def test_uparams_normalizes_the_stations_onto_zero_to_one():
    rows = square_rows([-10.0, -4.0, 0.0])
    assert fr.uparams(rows) == pytest.approx([0.0, 0.6, 1.0])


def test_uparams_is_not_a_station_count_because_the_spacing_is_not_uniform():
    # The distinction the whole investigation turns on: 7.5 "station intervals" of a highly
    # non-uniform stack is not 7.5 equal steps.
    rows = square_rows([0.0, 0.001, 10.0])
    assert fr.uparams(rows)[1] == pytest.approx(0.0001)


def test_uparams_matches_the_line_in_the_real_fit():
    # `fit_response` recomputes one line of `cowl_interior._fit` so the analytic prediction can be
    # had without importing `Part`. If that line ever changes, the prediction silently stops
    # describing the kernel, so the duplicate is pinned to the source text.
    src = io.open(COWL_INTERIOR, encoding='utf-8').read()
    assert 'uparams = [(z - lo) / span for z in zs]' in src


def test_a_flat_stack_has_no_parameters():
    with pytest.raises(ValueError):
        fr.uparams(square_rows([2.0, 2.0]))


# --- which station is a row -------------------------------------------------------------------

def test_a_target_that_is_a_row_is_reported_as_one():
    rows = square_rows([-10.0, -5.0, 0.0])
    assert fr.row_index(rows, -5.0) == 1


def test_a_target_a_thousandth_off_a_row_is_not_that_row():
    # Not a quibble: at a row the fit's response is zero by construction and just off one it is
    # not, so conflating them would make a zero reading look like a refutation.
    rows = square_rows([-10.0, -5.0, 0.0])
    assert fr.row_index(rows, -5.001) is None


# --- the cardinal function: the analytic prediction -------------------------------------------

def test_the_cardinal_function_is_one_at_its_own_knot():
    params = [0.0, 0.25, 0.5, 0.75, 1.0]
    assert fr.cardinal(params, 2, 0.5) == pytest.approx(1.0, abs=1e-12)


def test_the_response_is_exactly_zero_at_every_other_row():
    # The structural heart of this module. An interpolant passes through its data, so nudging one
    # row cannot move the fitted surface at any other row at all -- which means a nudge reaches a
    # target station only as an overshoot between rows.
    params = [0.0, 0.1, 0.35, 0.6, 0.62, 1.0]
    for j, u in enumerate(params):
        expected = 1.0 if j == 3 else 0.0
        assert fr.cardinal(params, 3, u) == pytest.approx(expected, abs=1e-12)


def test_a_uniform_stack_decays_about_the_figure_section_4_4_quotes():
    # Where "about 3.7x per station" comes from: the cardinal function of a cubic interpolating
    # spline on a uniform knot stack decays by roughly 1 / (2 - sqrt(3)) = 3.73 per knot, measured
    # at the midpoints between knots so the exact zeros at the knots do not hide it.
    n = 15
    params = [i / float(n - 1) for i in range(n)]
    mids = [0.5 * (params[i] + params[i + 1]) for i in range(n - 1)]
    peak = 7
    at = [abs(fr.cardinal(params, peak, m)) for m in mids]
    ratios = [at[peak + k] / at[peak + k + 1] for k in range(1, 4)]
    for r in ratios:
        assert 3.0 < r < 4.5, ratios


def test_the_cardinal_function_is_linear_in_the_nudge_so_a_gain_is_a_constant():
    # Why a dose series may be summarized by one gain at all, and why a measured gain that is not
    # constant across magnitudes is evidence of something other than the fit.
    params = [0.0, 0.2, 0.45, 0.7, 1.0]
    base = fr.cardinal(params, 1, 0.33)
    assert 2.5 * base == pytest.approx(2.5 * fr.cardinal(params, 1, 0.33), abs=1e-15)
    assert base != 0.0


def test_a_two_row_patch_is_degree_one_and_its_cardinal_is_the_hat():
    # `_fit`'s own docstring records that a two-station patch comes out degree 1.
    assert fr.cardinal([0.0, 1.0], 0, 0.25) == pytest.approx(0.75)
    assert fr.cardinal([0.0, 1.0], 1, 0.25) == pytest.approx(0.25)


def test_a_knot_outside_the_stack_is_an_error():
    with pytest.raises(IndexError):
        fr.cardinal([0.0, 0.5, 1.0], 3, 0.5)


# --- the measured response --------------------------------------------------------------------

def test_a_zero_nudge_is_refused_because_it_has_no_gain():
    rows = square_rows([0.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        fr.response(_LinearFit, rows, 1, 0.0, [0.5])


def test_the_measured_response_is_zero_at_the_other_rows():
    rows = square_rows([0.0, 1.0, 2.0, 3.0])
    got = fr.response(_LinearFit, rows, 1, 0.01, [0.0, 2.0, 3.0], n_v=24)
    for rec in got:
        assert rec['moved_mm'] == pytest.approx(0.0, abs=1e-9), rec


def test_the_measured_response_is_the_full_nudge_at_the_nudged_row():
    rows = square_rows([0.0, 1.0, 2.0])
    rec = fr.response(_LinearFit, rows, 1, 0.01, [1.0], n_v=24)[0]
    assert rec['moved_mm'] == pytest.approx(0.01, rel=1e-6)
    assert rec['gain'] == pytest.approx(1.0, rel=1e-6)


def test_a_response_between_rows_reports_the_gain_as_a_fraction_of_the_nudge():
    rows = square_rows([0.0, 1.0, 2.0])
    rec = fr.response(_LinearFit, rows, 1, 0.02, [1.5], n_v=24)[0]
    # Halfway between the nudged row and its neighbor, a degree-1 interpolant carries half.
    assert rec['gain'] == pytest.approx(0.5, rel=1e-3)
    assert rec['row'] is None


def test_a_response_record_carries_the_prediction_beside_the_measurement():
    # They are never reported apart, so a measurement cannot be quoted without the expectation it
    # is being compared against.
    rows = square_rows([0.0, 1.0, 2.0, 3.0])
    rec = fr.response(_LinearFit, rows, 1, 0.01, [1.5], n_v=16)[0]
    assert set(rec) == {'z', 'row', 'u', 'moved_mm', 'gain', 'predicted_gain'}


def test_the_axial_parameter_is_solved_from_the_surface_not_assumed():
    # `(z - lo) / span` is the parameter the rows were given, exact at a row and wrong between
    # rows. The solve has to land on the surface's own height.
    rows = square_rows([0.0, 0.01, 10.0])
    fit = _LinearFit(rows)
    u = fr._solve_u(fit, 5.0)
    assert fit.value(u, 0.0).z == pytest.approx(5.0, abs=1e-6)


# --- station distance -------------------------------------------------------------------------

def test_station_distance_counts_intervals_not_millimeters():
    rows = square_rows([0.0, 1.0, 2.0, 3.0, 4.0])
    assert fr.station_distance(rows, 0, 3.0) == pytest.approx(3.0)
    assert fr.station_distance(rows, 0, 2.5) == pytest.approx(2.5)


def test_station_distance_is_signed_so_a_direction_is_not_lost():
    rows = square_rows([0.0, 1.0, 2.0, 3.0])
    assert fr.station_distance(rows, 2, 0.0) == pytest.approx(-2.0)


def test_a_crowded_stack_puts_many_intervals_in_very_little_distance():
    # The reason a per-station attenuation figure and a per-millimeter one are not the same claim.
    rows = square_rows([0.0, 0.001, 0.002, 10.0])
    assert fr.station_distance(rows, 0, 0.002) == pytest.approx(2.0)


# --- the amplification law, and its converse --------------------------------------------------

def crowded(knots, at, tightness):
    """A uniform parameter mesh with the interval after `at` squeezed by `tightness`."""
    u = [i / float(knots - 1) for i in range(knots)]
    u[at + 1] = u[at] + tightness * (u[at + 1] - u[at])
    return sorted(u)


def test_a_crowded_station_pair_beside_the_nudge_amplifies_instead_of_attenuating():
    # The finding. Section 4.4's "about 3.7x per station" describes a well-spaced mesh; put a
    # near-duplicate pair next to the nudged row and the same interpolation amplifies.
    knots, i_row, offset = 21, 10, 7.5
    uniform = [i / float(knots - 1) for i in range(knots)]
    clean = abs(fr.cardinal(uniform, i_row, fr._at(uniform, i_row, offset)))
    tight = crowded(knots, i_row, 1.0e-4)
    amplified = abs(fr.cardinal(tight, i_row, fr._at(tight, i_row, offset)))
    assert clean < 1.0e-4
    assert amplified > 0.3
    assert amplified / clean > 1000.0


def test_the_gain_is_inversely_proportional_to_the_pair_gap():
    # A decade of tightening buys a decade of gain, which is what makes the mechanism a law
    # rather than an observation at one magnitude.
    knots, i_row, offset = 21, 10, 7.5
    gains = []
    for tightness in (1.0e-2, 1.0e-3, 1.0e-4, 1.0e-5):
        u = crowded(knots, i_row, tightness)
        gains.append(abs(fr.cardinal(u, i_row, fr._at(u, i_row, offset))))
    for a, b in zip(gains, gains[1:]):
        assert b / a == pytest.approx(10.0, rel=0.01)


def test_a_crowded_pair_away_from_the_nudged_row_does_not_amplify():
    # The converse, and the reason this is a statement about the pair and the nudge together
    # rather than about the mesh. Without it, "crowding amplifies" would be unfalsified.
    knots, i_row, offset = 21, 10, 7.5
    uniform = [i / float(knots - 1) for i in range(knots)]
    clean = abs(fr.cardinal(uniform, i_row, fr._at(uniform, i_row, offset)))
    for at in (0, 3, 19):
        u = crowded(knots, at, 1.0e-4)
        gain = abs(fr.cardinal(u, i_row, fr._at(u, i_row, offset)))
        assert gain == pytest.approx(clean, rel=0.05), at


def test_a_crowded_pair_just_past_the_nudge_suppresses_rather_than_amplifies():
    # Measured, and worth pinning because it is the opposite of the adjacent case and would
    # otherwise look like a contradiction of it.
    knots, i_row, offset = 21, 10, 7.5
    uniform = [i / float(knots - 1) for i in range(knots)]
    clean = abs(fr.cardinal(uniform, i_row, fr._at(uniform, i_row, offset)))
    u = crowded(knots, i_row + 1, 1.0e-4)
    assert abs(fr.cardinal(u, i_row, fr._at(u, i_row, offset))) < clean / 100.0


def test_a_floor_on_the_pair_gap_is_a_ceiling_on_the_gain():
    # Why IP-FC-144's station floor bounds this failure mode rather than only discouraging it.
    # The gain goes as 1 / gap, so `_thin_stations(zs, station_floor(t))` refusing a pair under
    # 0.6 mm caps what the fit can carry to a distant station. Measured against the 0.0015 mm
    # pair that reproduces the 0.408 mm per mm on record.
    knots, i_row, offset, interval = 21, 10, 7.5, 15.0
    def gain_at(gap_mm):
        u = crowded(knots, i_row, gap_mm / interval)
        return abs(fr.cardinal(u, i_row, fr._at(u, i_row, offset)))
    at_floor = gain_at(0.6)
    at_pair = gain_at(0.0015)
    assert at_pair / at_floor == pytest.approx(400.0, rel=0.05)
    assert at_floor < 2.0e-3


def test_the_station_floor_formula_matches_the_construction():
    # `station_floor` lives in `cowl_interior`, which cannot be imported without FreeCAD, so the
    # formula the bound above assumes is pinned to the source text instead of copied by hand.
    src = io.open(COWL_INTERIOR, encoding='utf-8').read()
    assert 'return max(t, MIN_INTERVAL)' in src
    # The call site moved twice on 2026-10-28 and this test caught both, which is what it is for.
    # First behind a `station_floor_mm` parameter so OQ-DES-CW26's own station set could be
    # rebuilt; then behind the measurement seam, when that parameter was judged unacceptable in a
    # production signature. What the bound above actually needs is unchanged: a real build thins
    # the union with `station_floor(t)`.
    assert 'default_floor = station_floor(t)' in src
    assert '_thin_stations(zs, floor)' in src
    # **And that a build takes that default**, which is the part the bound rests on. The seam is
    # inert unless a measurement installs one, so `_probe_floor` returns its argument; if the seam
    # ever defaulted to something live, every gain bound derived from a 0.6 mm floor would quietly
    # stop holding. `test_wall_measure_probe` owns the seam's own behavior; this is the one fact
    # this file's arithmetic depends on.
    assert 'floor = _probe_floor(default_floor)' in src
    assert '\n_probe = None\n' in src


def span_peaks(params, i_row, spans):
    """The largest |cardinal| inside each inter-knot span at `spans` intervals past `i_row`.

    Sampled between knots on purpose: at a knot the value is exactly zero, so a reading taken
    only at knots says nothing about how far a displacement actually travels.
    """
    out = []
    for k in spans:
        lo, hi = params[i_row + k], params[i_row + k + 1]
        out.append(max(abs(fr.cardinal(params, i_row, lo + (hi - lo) * m / 40.0))
                       for m in range(1, 40)))
    return out


def test_a_uniform_mesh_decays_at_the_rate_section_4_4_quotes():
    # The baseline the real mesh is judged against: 0.268 per span, which is the 3.7x figure.
    zs = [-300.0 + 300.0 * k / 26.0 for k in range(27)]
    peaks = span_peaks(fr.uparams([(z, []) for z in zs]), 6, (1, 2, 3, 4))
    for a, b in zip(peaks, peaks[1:]):
        assert b / a == pytest.approx(0.268, abs=0.02), peaks


def test_a_wide_gap_ratio_makes_the_fit_overshoot_instead_of_decay():
    # The trap that invalidated two explanations written into the design document and withdrawn
    # the same day. First "the floor bounds the gain", then "the mesh is merely coarse" -- a
    # uniform mesh of the real station count decays normally, as the test above shows. What the
    # real tail has is a 92:1 ratio between its widest and narrowest gap, and on such a mesh the
    # cardinal function rises *above* 1 for the first spans past the displaced row before
    # collapsing. Above 1 means the surface moves further than the row that was displaced.
    zs = ([-300.0, -291.0, -284.509, -283.5640440, -273.850, -239.999, -180.0, -165.043]
          + [-120.0 + 120.0 * k / 18.0 for k in range(19)])
    zs = sorted(set(zs))
    gp = fr.gaps(zs)
    assert gp[-1][0] / gp[0][0] > 50.0                 # a wide ratio, like the real mesh
    i_row = zs.index(-283.5640440)
    peaks = span_peaks(fr.uparams([(z, []) for z in zs]), i_row, (0, 1, 2))
    assert max(peaks) > 1.0, peaks                     # overshoot, not decay
    assert min(gp)[0] > 0.6                            # and nothing is under the station floor


def test_the_mesh_search_finds_the_crowded_pair_as_the_worst_arrangement():
    best, where = fr.mesh_bound(21, 7.5, trials=200)
    assert 'crowded pair' in where
    assert best > 1.0


def test_the_mesh_search_refuses_a_stack_too_short_for_a_cubic():
    with pytest.raises(ValueError):
        fr.mesh_bound(3, 1.5)


# --- station gaps -----------------------------------------------------------------------------

def test_gaps_come_back_tightest_first():
    assert [round(g, 6) for g, _l, _h in fr.gaps([0.0, 10.0, 10.5, 30.0])] == [0.5, 10.0, 19.5]


def test_gaps_name_both_ends_so_a_pair_can_be_located():
    gap, lo, hi = fr.gaps([-60.0003433, -60.0, -50.0])[0]
    assert gap == pytest.approx(0.0003433, abs=1e-9)
    assert (lo, hi) == (-60.0003433, -60.0)


def test_a_single_station_has_no_gaps():
    assert fr.gaps([1.0]) == []
    assert fr.gaps([]) == []


def test_sub_floor_counts_what_the_construction_would_drop():
    # The real tail_shell U = 3.0 union carries seven of these against a 0.6 mm floor; this is
    # the statistic that count comes from.
    zs = [-60.0003433, -60.0, -59.5, -58.0]      # gaps 0.0003433, 0.5, 1.5
    assert len(fr.sub_floor(zs, 0.6)) == 2
    assert fr.sub_floor(zs, 0.6)[0][0] == pytest.approx(0.0003433, abs=1e-9)


def test_nothing_is_sub_floor_when_the_stations_are_well_spaced():
    # The nose's case: its tightest gap is wider than the wall, so the floor drops nothing.
    assert fr.sub_floor([0.0, 2.0, 4.0, 6.0], 0.6) == []


# --- the synthetic stack ----------------------------------------------------------------------

def test_the_synthetic_section_has_genuine_fixed_radius_corners():
    rows = fr.rounded_rows([0.0, 1.0], n=720, half_x=60.0, half_y=40.0, radius=8.0)
    pts = rows[0][1]
    cx, cy = 60.0 - 8.0, 40.0 - 8.0
    corner = [(x, y) for x, y in pts if x > cx and y > cy]
    assert len(corner) > 10
    for x, y in corner:
        assert math.hypot(x - cx, y - cy) == pytest.approx(8.0, abs=1e-6)


def test_the_synthetic_section_has_flats_as_well_as_corners():
    # A section that was round everywhere would have no curvature discontinuity to exercise.
    rows = fr.rounded_rows([0.0], n=720, half_x=60.0, half_y=40.0, radius=8.0)
    xs = [x for x, y in rows[0][1] if abs(y) < 10.0]
    assert max(xs) == pytest.approx(60.0, abs=1e-9)


def test_a_corner_radius_that_does_not_fit_is_refused():
    with pytest.raises(ValueError):
        fr.rounded_rows([0.0], n=64, half_x=10.0, half_y=5.0, radius=6.0)


def test_the_synthetic_stack_can_taper_so_it_is_not_a_prism():
    rows = fr.rounded_rows([0.0, 10.0], n=64, half_x=60.0, half_y=40.0,
                           radius=8.0, taper=0.01)
    first = max(x for x, _y in rows[0][1])
    last = max(x for x, _y in rows[1][1])
    assert last < first
