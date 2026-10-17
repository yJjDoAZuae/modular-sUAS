"""Sampling density as a spacing, and the chord-sag error that a fixed sample count hides.

The cowl scales with `U` while the wall stays an absolute 0.6 mm, so every measurement that fixes a
sample *count* gets a spacing that grows with `U`. `check_cowl_interior` fixed `AROUND` = 240 and
`sweep.measure_wall` fixed `level` = 1440; `cowl_interior.check_samples` did not, being arc-length
based at `CHECK_ARC` = 0.20 mm. The gate is fixed as of IP-WTM-25 and samples at `WALL_ARC` = 0.125
mm; `prior_gate_spacing` keeps the old arithmetic, because the published figures were taken with it.

**The mechanism is checked against closed-form truth here, not just asserted.** A circle of radius
`R` sampled at spacing `s` has chords that sag by `R - sqrt(R^2 - (s/2)^2)`, about `s^2 / (8R)`. On
a concentric annulus that sag is subtracted from the measured wall directly, so the error is
predictable to three figures and a test can hold the code to it. That is what makes the
large-`U` finding a mechanism rather than a correlation.

See doc/implementation/wall_thickness_measure.md.
"""
import ast
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'src', 'Fuselage', 'tools'))

from wall_measure import candidates, density                             # noqa: E402

GATE_SOURCE = os.path.join(REPO, 'src', 'Fuselage', 'freecad', 'check_cowl_interior.py')


def gate_constant(name):
    """Read a module-level constant out of the gate's source, without importing it.

    `check_cowl_interior` imports FreeCAD at module level, so a test running on the project's own
    interpreter cannot import it to compare a value. Parsing is the way to hold a mirrored constant
    to its original anyway: it fails loudly if the gate's name changes, where a hand-copied number
    just goes quietly stale.
    """
    with open(GATE_SOURCE) as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError('%s is not a module-level constant of check_cowl_interior' % name)


def ring(radius, n, phase=0.0):
    a = np.radians(np.linspace(0.0, 360.0, n, endpoint=False)) + phase
    return np.stack([radius * np.cos(a), radius * np.sin(a), np.zeros_like(a)], axis=1)


def offset_ring(radius, n):
    """An inner ring sampled half a step out of phase with `ring(_, n)` -- the worst case.

    **Phase matters, and the first version of these tests missed it.** Sampling both loops on the
    *same* angular grid puts every inner point radially opposite an outer vertex, where the distance
    to the outer polyline is exactly the wall and the chord error is about 1e-6 mm. Half a step out
    of phase puts every inner point opposite a chord midpoint, which is where the full sag applies.
    A real section's two loops have different lengths and drift through every relative phase, so the
    minimum over the loop sees the worst case; that is what this models.
    """
    return ring(radius, n, phase=np.pi / n)


def sag(radius, spacing):
    """How far a chord of arc-spacing `spacing` falls inside a circle of radius `radius`."""
    half = 0.5 * float(spacing)
    return float(radius) - float(np.sqrt(max(0.0, radius * radius - half * half)))


# -------------------------------------------------------------------------- spacing arithmetic


class TestSpacingArithmetic:

    def test_a_count_is_derived_from_the_perimeter(self):
        assert density.counts_for_spacing(1000.0, 0.5) == 2000
        assert density.counts_for_spacing(2088.4, 0.125) == 16707

    def test_a_count_is_never_absurdly_small(self):
        """A short section still needs enough points to be a polygon."""
        assert density.counts_for_spacing(1.0, 100.0) == 16

    def test_a_count_is_capped_so_a_request_cannot_be_unbounded(self):
        """The cap that the first density run needed and did not have."""
        assert density.counts_for_spacing(1.0e9, 0.001) == density.MAX_POINTS

    def test_the_prior_gate_spacing_grows_with_the_part(self):
        """**The defect, in one assertion, kept because the published figures carry it.**
        `PRIOR_GATE_AROUND` is a fixed 240, so the inner spacing is proportional to the perimeter --
        1.8 mm on a tail at `U` = 1 and 8.7 mm at `U` = 4, against a wall of 0.6 mm at both."""
        inner_u1, _outer_u1 = density.prior_gate_spacing(428.3)
        inner_u4, outer_u4 = density.prior_gate_spacing(2088.4)
        assert inner_u1 == pytest.approx(1.785, abs=0.002)
        assert inner_u4 == pytest.approx(8.702, abs=0.002)
        assert outer_u4 == pytest.approx(inner_u4 / density.PRIOR_GATE_OUTER_FACTOR)
        assert inner_u4 / inner_u1 == pytest.approx(2088.4 / 428.3, rel=1e-6)

    def test_the_prior_gate_sampled_coarser_than_the_wall_it_measured_at_large_u(self):
        """The figure that made the finding plain: at `U` = 4 the gate put its inner samples
        fourteen times the wall thickness apart."""
        inner, _outer = density.prior_gate_spacing(2088.4)
        assert inner > 10 * density.NOMINAL

    def test_the_fixed_gate_holds_its_spacing_across_the_whole_u_range(self):
        """IP-WTM-25: the same spacing at `U` = 0.5 and `U` = 4, which is the property a count
        cannot have. The ratio the prior test asserts grows by 4.9x is now exactly 1."""
        short = density.gate_spacing(214.0)[0]
        long_ = density.gate_spacing(2088.4)[0]
        assert short == pytest.approx(density.GATE_ARC, rel=1e-3)
        assert long_ == pytest.approx(density.GATE_ARC, rel=1e-3)
        assert long_ / short == pytest.approx(1.0, rel=1e-3)

    def test_the_fixed_gate_samples_an_order_finer_than_the_wall_it_measures(self):
        """The inverse of the prior gate's failure: the spacing has to be well inside the 0.6 mm
        being measured, not a multiple of it."""
        inner, outer = density.gate_spacing(2088.4)
        assert inner < density.NOMINAL / 4
        assert outer == inner, 'one spacing, both loops -- the 8x outer factor is retired'

    def test_a_short_section_hits_the_floor_and_is_sampled_finer_not_coarser(self):
        """Which direction the clamp errs in is the part that matters: finer than asked is
        harmless, coarser would silently undo the fix."""
        assert density.gate_spacing(10.0)[0] < density.GATE_ARC

    def test_a_section_past_the_ceiling_is_reported_coarser_so_it_cannot_hide(self):
        """The ceiling is a cost guard, so the one thing required of it is that the spacing it
        actually achieves is visible rather than assumed to be `GATE_ARC`."""
        huge = 10.0 * density.GATE_MAX * density.GATE_ARC
        assert density.gate_spacing(huge)[0] > density.GATE_ARC

    def test_the_mirrored_gate_constants_match_the_gates_own_source(self):
        """**A mirror that drifts is worse than no mirror.** This module cannot import the gate --
        it must stay importable with no FreeCAD -- so the values are copied, and the copy is held
        to the original by reading it."""
        assert density.GATE_ARC == gate_constant('WALL_ARC')
        assert density.GATE_MIN == gate_constant('WALL_MIN')
        assert density.GATE_MAX == gate_constant('WALL_MAX')
        assert density.PRIOR_GATE_AROUND == 240, 'history, not a mirror: the gate no longer has it'

    def test_the_constructions_own_scan_is_a_spacing_too_and_a_coarser_one(self):
        """`cowl_interior.CHECK_ARC` is why pass 2's scan density held at large `U` while the things
        measuring the result did not. Both are spacings now, and the gate's is the finer of the two
        deliberately: 0.20 mm resolves the 1.3 mm gap a rib leaves, 0.125 mm resolves a 0.01 mm
        departure in a 0.6 mm wall."""
        assert density.CONSTRUCTION_ARC == 0.20
        assert density.GATE_ARC < density.CONSTRUCTION_ARC


# ------------------------------------------------------------- the mechanism, against closed form


class TestChordSag:

    def test_a_coarse_outer_polyline_reads_the_wall_thinner_than_it_is(self):
        """On a concentric annulus the true wall is exactly `outer_r - inner_r`; a coarsely sampled
        outer polyline's chords lie inside the true circle, so an inner sample opposite a chord
        measures to the chord and reads closer. The error is the sag, in closed form."""
        outer_r, wall = 200.0, 0.6
        spacing = 4.0
        n = int(round(2 * np.pi * outer_r / spacing))
        _pts, thick = candidates.nearest_point_min(ring(outer_r, n), offset_ring(outer_r - wall, n))
        measured = float(np.min(thick))
        assert measured == pytest.approx(wall - sag(outer_r, spacing), rel=0.02)
        assert measured < wall

    def test_the_error_falls_as_the_square_of_the_spacing(self):
        """Halving the spacing quarters the sag."""
        outer_r, wall = 200.0, 0.6
        errs = []
        for spacing in (4.0, 2.0, 1.0):
            n = int(round(2 * np.pi * outer_r / spacing))
            _pts, thick = candidates.nearest_point_min(ring(outer_r, n),
                                                       offset_ring(outer_r - wall, n))
            errs.append(wall - float(np.min(thick)))
        assert errs[0] / errs[1] == pytest.approx(4.0, rel=0.1)
        assert errs[1] / errs[2] == pytest.approx(4.0, rel=0.1)

    def test_at_a_fixed_count_the_error_grows_linearly_with_the_part(self):
        """With the count fixed, spacing is proportional to radius, so the sag `s^2/(8R)` is
        proportional to `R`. Four times the part at the same sample count is four times the error,
        on a wall that has not changed."""
        wall, count = 0.6, 1440
        errs = []
        for outer_r in (50.0, 200.0):
            _pts, thick = candidates.nearest_point_min(ring(outer_r, count),
                                                       offset_ring(outer_r - wall, count))
            errs.append(wall - float(np.min(thick)))
        assert errs[1] / errs[0] == pytest.approx(4.0, rel=0.1)

    def test_at_a_fixed_spacing_the_error_falls_as_the_part_grows(self):
        """The fix, stated as the converse -- and it is better than merely scale-free.

        At fixed spacing `s` the sag is `s^2 / (8R)`, so it *falls* as `1/R`: a larger part sampled
        at the same millimetre spacing is measured **more** accurately, not equally. An earlier
        version of this test asserted the two were equal, which was a guess at the algebra rather
        than a reading of it."""
        wall, spacing = 0.6, 0.5
        errs = []
        for outer_r in (50.0, 200.0):
            n = int(round(2 * np.pi * outer_r / spacing))
            _pts, thick = candidates.nearest_point_min(ring(outer_r, n),
                                                       offset_ring(outer_r - wall, n))
            errs.append(wall - float(np.min(thick)))
        assert errs[1] < errs[0]
        assert errs[0] / errs[1] == pytest.approx(4.0, rel=0.1)

    def test_smooth_arc_sag_is_far_too_small_to_explain_the_real_error(self):
        """**The negative result that matters, and it rules out my own first explanation.**

        Smooth-arc chord sag is real, exactly predictable and linear in `U` -- and at the spacing the
        published corpus sweep actually used on a `tail_shell` at `U` = 4 (1 440 samples on a
        2 088 mm section, 1.45 mm apart, local radius of order 200 mm) it is about 0.0005 mm. The
        error measured on that wall was 0.18-0.21 mm, four hundred times larger. So the smooth-arc
        mechanism is *not* the cause, and an explanation that stopped here would have been a tidy
        derivation over the wrong geometry. The cause has to involve the section's features -- its
        concave slot mouths and rib flanks, whose size is absolute while the spacing grows with
        `U` -- and that is measured on the real wall, not here."""
        outer_r, wall, count = 200.0, 0.6, 1440
        _pts, thick = candidates.nearest_point_min(ring(outer_r, count),
                                                   offset_ring(outer_r - wall, count))
        smooth_error = wall - float(np.min(thick))
        assert smooth_error < 0.001
        assert smooth_error < 0.01 * 0.18


# ------------------------------------------------------------------------------ summarizing


class TestSummaries:

    def rows(self, thins):
        return [{'spacing': 2.0 / (2 ** i), 'samples': 100 * (2 ** i), 'minimum': 0.6 - t,
                 'thin': t, 'median': 0.6, 'perimeter': 200.0}
                for i, t in enumerate(thins)]

    def test_trend_reports_the_step_between_successive_refinements(self):
        got = density.trend(self.rows([0.25, 0.05, 0.035, 0.034]))
        assert got[0] == pytest.approx(-0.20)
        assert got[-1] == pytest.approx(-0.001)

    def test_settles_to_uses_the_finest_two_rows(self):
        ok, value, last = density.settles_to(self.rows([0.25, 0.05, 0.035, 0.0345]), tol=0.001)
        assert ok is True and value == pytest.approx(0.0345)
        assert last == pytest.approx(-0.0005)

    def test_a_series_still_moving_is_not_settled(self):
        ok, _value, last = density.settles_to(self.rows([0.25, 0.20, 0.15, 0.10]), tol=0.001)
        assert ok is False and abs(last) > 0.001

    def test_the_artefact_fraction_is_how_much_refinement_removed(self):
        """0.84 at tail `U` = 4 is the headline figure: most of the published reading was the
        instrument."""
        assert density.artefact_fraction(self.rows([0.2136, 0.05, 0.035, 0.0347])) == \
            pytest.approx(1.0 - 0.0347 / 0.2136, rel=1e-6)

    def test_the_artefact_fraction_is_none_when_the_coarse_reading_was_zero(self):
        assert density.artefact_fraction(self.rows([0.0, 0.0])) is None

    def test_summaries_tolerate_a_station_that_read_nothing(self):
        rows = [{'spacing': 1.0, 'samples': 100, 'minimum': float('nan'), 'thin': float('nan'),
                 'median': float('nan'), 'perimeter': 200.0}]
        assert density.settles_to(rows) == (False, None, None)
        assert density.artefact_fraction(rows) is None
        assert 'spacing' in density.table(rows)
