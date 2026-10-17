"""IP-WTM-45: is a thin reading taken *at a crease of the exterior* trustworthy?

`cowl_interior`'s second pass compares `TAU` against a plain minimum distance from the cavity to the
**notched** exterior. On `tail_shell` at `U` = 0.5 it reads 0.06005 mm at `z` = -15.27863 -- the
figure that is invariant in `TAU` and refuses the build at 0.02 and 0.01 -- while the same wall
measured to the **un-notched OML** reads 0.00175 mm at that same station (section 6.8.2). Two
explanations fit: the wall really is thin where a notch cuts it, or the in-plane nearest-point
distance is short because it is taken across the crease where a notch face meets the OML.

`candidates.outer_corner_excluded_min` exists to separate those on the real wall.

**These tests do not try to settle which explanation is right, and deliberately so.** A synthetic
fixture built to show the artifact would be built on an assumption about the artifact, and the
fixture lesson this plan has already paid for twice -- concentric circles cannot exercise a corner
measure at all (section 6.4), and a pocket on the *outer* face leaves the inner contour convex so a
corner exclusion excludes nothing (IP-WTM-10) -- is that a fixture which assumes the answer confirms
nothing. What is tested here is the instrument's own properties: that it finds a crease and not a
sampled arc, that it drops the samples it claims to drop, that it keeps the rest, and that it is a
subset of the incumbent. The real geometry answers the question.

See doc/implementation/wall_thickness_measure.md.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import candidates                               # noqa: E402


def ring(radius, n=1000, cx=0.0, cy=0.0):
    a = np.radians(np.linspace(0.0, 360.0, n, endpoint=False))
    return np.stack([cx + radius * np.cos(a), cy + radius * np.sin(a), np.zeros_like(a)], axis=1)


def vee(radius, n, span_deg, depth, at_deg=40.0):
    """A circle with a V notch cut **inward**, so its apex is the nearest exterior point.

    This is the shape a corner-at-the-exterior artifact needs: the crease has to be where the
    measurement lands, which means pointing toward the inner loop. A corner pointing *away* — a
    square's, say — is the farthest part of the boundary and is never nearest to anything inside.
    """
    a = np.radians(np.linspace(0.0, 360.0, n, endpoint=False))
    deg = np.degrees(a)
    r = np.full_like(a, radius)
    m = np.abs(deg - at_deg) < span_deg / 2.0
    r[m] = radius - depth * (1.0 - np.abs(deg[m] - at_deg) / (span_deg / 2.0))
    return np.stack([r * np.cos(a), r * np.sin(a), np.zeros_like(a)], axis=1)


def square(half, per_side=250):
    """A closed square as a polyline: four genuine creases of 90 degrees and nothing else."""
    t = np.linspace(-half, half, per_side, endpoint=False)
    top = np.stack([t, np.full_like(t, half)], axis=1)
    right = np.stack([np.full_like(t, half), -t], axis=1)
    bottom = np.stack([-t, np.full_like(t, -half)], axis=1)
    left = np.stack([np.full_like(t, -half), t], axis=1)
    xy = np.concatenate([top, right, bottom, left], axis=0)
    return np.column_stack([xy, np.zeros(len(xy))])


class TestOuterCreases:
    """The threshold has to separate a crease from a finely sampled curve, nothing subtler."""

    def test_a_finely_sampled_circle_has_no_creases(self):
        assert not candidates.outer_creases(ring(20.0, 1000)).any()

    def test_a_square_has_exactly_four(self):
        assert int(candidates.outer_creases(square(20.0)).sum()) == 4

    def test_the_threshold_is_not_a_tuned_parameter(self):
        """A 1000-sample circle turns about 0.36 degrees a vertex and a notch junction turns tens,
        so any threshold across a wide band gives the same answer. If that stops being true the
        separation this rests on has gone."""
        circle, sq = ring(20.0, 1000), square(20.0)
        for angle in (10.0, 20.0, 30.0, 45.0, 60.0):
            assert not candidates.outer_creases(circle, angle).any(), angle
            assert int(candidates.outer_creases(sq, angle).sum()) == 4, angle


class TestOuterCornerExcludedMin:

    def test_with_no_crease_it_is_exactly_the_incumbent(self):
        """**The vacuity case, asserted rather than assumed.** On concentric circles there is no
        crease to exclude, so this must return the incumbent's own samples and distances
        unchanged — not a slightly different number from a different code path."""
        outer, inner = ring(20.0, 1000), ring(19.4, 1000)
        _p0, d0 = candidates.nearest_point_min(outer, inner)
        _p1, d1 = candidates.outer_corner_excluded_min(outer, inner)
        assert len(d1) == len(d0)
        assert np.allclose(d1, d0)

    def test_samples_nearest_a_crease_are_dropped_and_the_rest_kept(self):
        """**A square outer cannot test this and the first version of this test used one.** With a
        circular inner loop inside a square, the nearest exterior point is always a *face* — the
        corners are the farthest part of a square — so nothing was ever dropped and the assertion
        failed. The fixture has to put the crease where it is *nearest*, which means a notch cut
        inward, not a corner pointing away."""
        outer, inner = vee(20.0, 1000, span_deg=2.0, depth=0.3), ring(19.4, 1000)
        _p0, d0 = candidates.nearest_point_min(outer, inner)
        kept, d1 = candidates.outer_corner_excluded_min(outer, inner, margin_mm=0.60)
        assert 0 < len(d1) < len(d0), 'it must drop some samples and keep some'
        assert float(np.min(d0)) == pytest.approx(0.312, abs=0.01)
        assert float(np.min(d1)) == pytest.approx(0.600, abs=0.01), (
            'excluding the crease should restore the wall away from the notch')

    def test_a_notch_too_gentle_to_be_a_crease_is_left_alone(self):
        """**The negative control, and it matters for reading a null result.** A notch spread over
        8 degrees turns too little per vertex to pass the threshold, so no sample is excluded and
        the reading stands. That is correct — but it means a "no change" result on real geometry is
        ambiguous unless the crease count is reported with it, which is why
        `locate.junction_split` reports creases and dropped samples per station."""
        outer, inner = vee(20.0, 1000, span_deg=8.0, depth=0.3), ring(19.4, 1000)
        assert not candidates.outer_creases(outer).any()
        _p0, d0 = candidates.nearest_point_min(outer, inner)
        kept, d1 = candidates.outer_corner_excluded_min(outer, inner, margin_mm=0.60)
        assert len(d1) == len(d0)
        assert float(np.min(d1)) == pytest.approx(float(np.min(d0)))

    def test_it_never_reports_more_thinness_than_the_incumbent(self):
        """It minimizes over a **subset** of the incumbent's distances, so its minimum can only be
        larger or equal. That is structural, not a tolerance — the same identity
        `corner_excluded_min` is held to, where a violation once revealed a real defect."""
        outer, inner = square(20.0), ring(19.4, 1000)
        _p0, d0 = candidates.nearest_point_min(outer, inner)
        _p1, d1 = candidates.outer_corner_excluded_min(outer, inner, margin_mm=1.0)
        assert float(np.min(d1)) >= float(np.min(d0)) - 1.0e-12

    def test_a_margin_that_covers_the_whole_exterior_reports_nothing(self):
        """Reporting nothing is the honest outcome when every sample is excluded, and the caller
        has to see it rather than receive a minimum over an empty set."""
        outer, inner = square(20.0), ring(19.4, 200)
        kept, d = candidates.outer_corner_excluded_min(outer, inner, margin_mm=1.0e6)
        assert len(kept) == 0 and len(d) == 0

    def test_the_dropped_samples_are_the_ones_near_the_crease_in_space(self):
        """Not merely *some* samples: the ones whose nearest exterior point is the crease. The
        notch sits at 40 degrees, so samples near there must go and samples on the far side stay."""
        outer, inner = vee(20.0, 1000, span_deg=2.0, depth=0.3, at_deg=40.0), ring(19.4, 1000)
        kept, _d = candidates.outer_corner_excluded_min(outer, inner, margin_mm=0.60)
        ang = np.degrees(np.arctan2(kept[:, 1], kept[:, 0])) % 360.0
        assert np.min(np.abs(ang - 40.0)) > 0.5, 'a sample aimed at the notch survived'
        assert np.min(np.abs(ang - 220.0)) < 1.0, 'a sample on the far side was dropped'


class TestSegmentNearest:

    def test_the_distance_matches_the_existing_measure_exactly(self):
        """`_segment_nearest` adds an index to `_segment_distances` and must not change the number
        — a second implementation of the same arithmetic is a place for the two to drift."""
        outer, inner = square(20.0), ring(19.4, 500)
        d_old = candidates._segment_distances(inner, outer)
        d_new, _which = candidates._segment_nearest(inner, outer)
        assert np.allclose(d_old, d_new)

    def test_the_index_points_at_a_segment_that_really_is_nearest(self):
        outer, inner = square(20.0), ring(19.4, 64)
        d, which = candidates._segment_nearest(inner, outer)
        a = outer[:, :2]
        b = np.roll(a, -1, axis=0)
        for i in range(len(inner)):
            p, s, e = inner[i, :2], a[which[i]], b[which[i]]
            ab = e - s
            t = np.clip(np.dot(p - s, ab) / max(np.dot(ab, ab), 1e-30), 0.0, 1.0)
            assert np.linalg.norm(p - (s + t * ab)) == pytest.approx(d[i], abs=1e-9)

    def test_an_empty_point_set_returns_two_empty_arrays(self):
        d, which = candidates._segment_nearest(np.zeros((0, 3)), square(20.0))
        assert len(d) == 0 and len(which) == 0
