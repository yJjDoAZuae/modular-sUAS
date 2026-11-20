"""Seams placed exactly where the test wants them, which real geometry cannot do.

`contact_runs` finds where a detached strip's section touches the main body's. On a real wall the
seam is the unknown, so these tests build distance lists with seams of known position and check
each is recovered -- including the one that wraps the end of a closed outline, which a naive scan
reports as two seams.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure.contact import contact_runs                               # noqa: E402

TOL = 1.0e-6


def distances(n, seams):
    """`n` samples at 1 m from the other outline, except inside each `(first, last)` seam."""
    out = [1.0] * n
    for first, last in seams:
        i = first
        while True:
            out[i] = 0.0
            if i == last:
                break
            i = (i + 1) % n
    return out


class TestContactRuns(object):

    def test_no_contact_is_no_runs(self):
        assert contact_runs([1.0] * 10, TOL) == []

    def test_no_samples_is_no_runs(self):
        assert contact_runs([], TOL) == []

    def test_one_seam_is_found_with_its_middle(self):
        assert contact_runs(distances(20, [(5, 9)]), TOL) == [(5, 9, 7)]

    def test_a_single_crossing_sample_is_a_run(self):
        assert contact_runs(distances(20, [(12, 12)]), TOL) == [(12, 12, 12)]

    def test_two_seams_stay_two(self):
        assert contact_runs(distances(30, [(2, 4), (20, 25)]), TOL) == [(2, 4, 3), (20, 25, 23)]

    def test_a_seam_across_the_end_of_a_closed_outline_is_one_seam(self):
        # Samples 17, 18, 19, 0, 1, 2: six long, middle three past the start.
        assert contact_runs(distances(20, [(17, 2)]), TOL) == [(17, 2, 0)]

    def test_an_open_outline_does_not_wrap(self):
        got = contact_runs(distances(20, [(17, 2)]), TOL, closed=False)
        assert got == [(0, 2, 1), (17, 19, 18)]

    def test_whole_outline_in_contact_is_one_run(self):
        assert contact_runs([0.0] * 8, TOL) == [(0, 7, 4)]

    def test_the_tolerance_is_inclusive(self):
        assert contact_runs([1.0, TOL, 1.0], TOL) == [(1, 1, 1)]
