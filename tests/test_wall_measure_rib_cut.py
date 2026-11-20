"""The rib-cut decision rule may only err toward a flag.

Each test is one way the rule could pass a face it has not proven clear: a failed measurement, a
point inside the cavity, contact below the clearance, or a copy never certified to sit inside the
tool. None of them may return `CLEAR`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure.rib_cut import (CLEAR, FLAGGED, UNTESTABLE, placed,          # noqa: E402
                                  verdict)

C = 5.0e-6


class TestPlaced(object):

    def test_inside_with_clearance_is_placed(self):
        assert placed(C, True, C)

    def test_too_close_to_the_tool_boundary_is_not(self):
        assert not placed(C * 0.5, True, C)

    def test_outside_the_tool_is_not(self):
        assert not placed(1.0, False, C)

    def test_a_failed_measurement_never_places(self):
        assert not placed(None, True, C)
        assert not placed(C, None, C)


class TestVerdict(object):

    def test_clear_needs_distance_and_an_outside_point(self):
        assert verdict(True, C, False, C) == CLEAR

    def test_a_point_inside_the_cavity_flags(self):
        assert verdict(True, 1.0, True, C) == FLAGGED

    def test_contact_flags(self):
        assert verdict(True, 0.0, False, C) == FLAGGED

    def test_closer_than_the_clearance_flags(self):
        assert verdict(True, C * 0.999, False, C) == FLAGGED

    def test_a_failed_measurement_flags_and_never_clears(self):
        assert verdict(True, None, False, C) == FLAGGED
        assert verdict(True, C, None, C) == FLAGGED

    def test_an_unplaced_copy_is_untestable_not_clear(self):
        assert verdict(False, 1.0, False, C) == UNTESTABLE

    def test_no_input_combination_clears_without_both_certificates(self):
        for is_placed in (True, False):
            for d in (None, 0.0, C * 0.5, C, 1.0):
                for inside in (None, True, False):
                    got = verdict(is_placed, d, inside, C)
                    if got == CLEAR:
                        assert is_placed and inside is False and d is not None and d >= C


class TestInsetTriangle(object):
    """The inset must move every edge inward by exactly the margin, or the uncovered band is not
    the width the detector's threshold argument says it is."""

    @staticmethod
    def _edge_distance(p, a, b):
        ax, ay = b[0] - a[0], b[1] - a[1]
        return abs(ax * (p[1] - a[1]) - ay * (p[0] - a[0])) / (ax * ax + ay * ay) ** 0.5

    def test_every_edge_moves_in_by_the_margin(self):
        from wall_measure.rib_cut import inset_triangle
        a, b, c = (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (1.0, 3.0, 0.0)
        m = 0.25
        a2, b2, c2 = inset_triangle(a, b, c, m)
        for (p, q), (p2, q2), opposite in (((a, b), (a2, b2), c2), ((b, c), (b2, c2), a2),
                                           ((c, a), (c2, a2), b2)):
            assert abs(self._edge_distance(p2, p, q) - m) < 1e-12
            assert abs(self._edge_distance(q2, p, q) - m) < 1e-12

    def test_a_triangle_smaller_than_the_margin_vanishes(self):
        from wall_measure.rib_cut import inset_triangle
        assert inset_triangle((0.0, 0.0, 0.0), (0.01, 0.0, 0.0), (0.0, 0.01, 0.0), 0.01) is None

    def test_a_degenerate_triangle_vanishes(self):
        from wall_measure.rib_cut import inset_triangle
        assert inset_triangle((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), 1e-6) is None
