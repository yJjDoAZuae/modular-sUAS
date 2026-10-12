"""IP-WTM-17: can a measure see a thin spot that sits **on** a concave corner?

This is the gate that decides whether C4 is selectable. C4 passes every other gate by discarding
samples within 0.3 mm of a concave corner, and on a real wall that makes the section read exactly
nominal — 0.600000 against a 0.6 mm wall. Two readings fit that result and no gate so far can tell
them apart:

* the corners were the whole artefact, the wall is compliant, and discarding them is the fix; or
* **the exclusion is blind exactly where a wall is thinnest**, so C4 would pass the screening and
  ship a part with a hole.

The fixtures used up to now cannot distinguish those, because each puts its thin patch on smooth
wall. `truth.corner_patch_tube` puts one on a corner.

**A measure that misses this is disqualified however well it converges.** That is stated as a
threshold here rather than decided later: `BLINDNESS_FRAC` is the same 80% of the defect's depth
that gate G1 asks for anywhere else, so a corner is not held to an easier standard than smooth
wall.

See doc/implementation/wall_thickness_measure.md.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import candidates, gates, sections, truth                 # noqa: E402

from conftest import requires_freecad                                       # noqa: E402

#: The same fraction gate G1 requires on smooth wall. A corner gets no easier standard.
BLINDNESS_FRAC = gates.LOCALITY_FRAC

pytestmark = requires_freecad


@pytest.fixture
def corner(fc, Part, App):
    return truth.corner_patch_tube(Part, App)


@pytest.fixture
def loops(fc, App):
    def go(t, z, n=2880):
        got = sections.station_loops(t.shape, z, n, App=App)
        assert len(got) >= 2, 'expected two loops, got %d' % len(got)
        return got[0], got[1]
    return go


class TestTheFixtureIsWhatItClaims:
    """Before it can disqualify anything, the fixture has to be the shape it says it is."""

    def test_it_is_one_solid(self, corner):
        assert len(corner.shape.Solids) == 1
        assert corner.shape.isValid()

    def test_the_patch_sits_on_the_ribs_corner(self, corner):
        rib, patch = corner.features
        assert patch['angle'] == pytest.approx(rib['half_angle'])
        assert patch.get('on_corner') is True

    def test_the_truth_composes_both_features_across_the_patch(self, corner):
        """The overlap the radius-modifier model exists for: on the rib side of the corner the wall
        is `wall + rise - depth`, on the other side `wall - depth`, and the patch spans both."""
        rib, patch = corner.features
        r = corner.r_outer - patch['depth'] / 2.0
        z = patch['z_mid']
        inside = patch['angle'] - patch['half_angle'] * 0.5      # rib side
        outside = patch['angle'] + patch['half_angle'] * 0.5     # plain-wall side
        got_in = corner.true_thickness_at(r * np.cos(inside), r * np.sin(inside), z)
        got_out = corner.true_thickness_at(r * np.cos(outside), r * np.sin(outside), z)
        assert got_in == pytest.approx(truth.WALL + rib['rise'] - patch['depth'])
        assert got_out == pytest.approx(truth.WALL - patch['depth'])

    def test_the_wall_really_is_thin_there(self, corner, loops):
        """Read off the geometry, not from the truth function: the outer radius drops by `depth`
        over the patch, and the patch straddles the rib's corner."""
        _rib, patch = corner.features
        outer, _inner = loops(corner, patch['z_mid'])
        r = np.hypot(outer[:, 0], outer[:, 1])
        ang = np.arctan2(outer[:, 1], outer[:, 0])
        near = np.abs(ang - patch['angle']) < patch['half_angle'] * 0.5
        assert near.sum() > 3
        assert r[near].max() == pytest.approx(truth.R_OUTER - patch['depth'], abs=2e-3)

    def test_the_bore_still_has_its_re_entrant_corners(self, corner, loops):
        """The patch must not have destroyed the corner it is meant to sit on."""
        _rib, patch = corner.features
        _outer, inner = loops(corner, patch['z_mid'], 1440)
        p = sections.resample_by_arc_length(inner, 1440)[:, :2]
        prev, nxt = np.roll(p, 1, axis=0), np.roll(p, -1, axis=0)
        cross = ((p - prev)[:, 0] * (nxt - p)[:, 1] - (p - prev)[:, 1] * (nxt - p)[:, 0])
        sign = np.sign(sections.signed_area(inner)) or 1.0
        assert ((cross * sign) < -1e-9).sum() >= 2


def _depth_seen(measure, t, loops):
    """How much of the corner patch's true depth a measure reports."""
    _rib, patch = t.features
    outer, inner = loops(t, patch['z_mid'])
    pts, thick = measure(outer, inner)
    if pts.shape[0] == 0:
        return 0.0, 0
    # The thinnest the wall truly gets anywhere at this station, from the truth function.
    want = min(truth.WALL - patch['depth'], truth.WALL + _rib['rise'] - patch['depth'])
    seen = truth.WALL - float(np.nanmin(thick))
    return seen / patch['depth'], pts.shape[0], want


class TestWhichMeasuresAreBlindAtACorner:
    """**The disqualifying test.** Reported for every candidate so the answer is comparative."""

    def test_the_incumbent_sees_a_corner_defect(self, corner, loops):
        """Expected: the incumbent excludes nothing, so whatever else is wrong with it, it is not
        blind here. This is the control — without it, a universal failure would be unreadable."""
        frac, n, _want = _depth_seen(candidates.nearest_point_min, corner, loops)
        assert n > 0
        assert frac >= BLINDNESS_FRAC, 'incumbent saw only %.2f of the depth' % frac

    def test_whether_the_corner_excluding_measure_is_blind(self, corner, loops, capsys):
        """**The result that decides C4.** Recorded either way, with the figure.

        If C4 sees the defect, the corner exclusion is safe and C4 is selectable. If it does not,
        C4 is disqualified no matter how well it converges, and the screening continues without it.
        """
        frac, n, _want = _depth_seen(candidates.corner_excluded_min, corner, loops)
        with capsys.disabled():
            print('\n    C4 at a corner defect: saw %.1f%% of the depth from %d surviving samples'
                  ' (limit %.0f%%)' % (frac * 100.0, n, BLINDNESS_FRAC * 100.0))
        if frac < BLINDNESS_FRAC:
            pytest.fail(
                'C4 is BLIND at a corner: saw %.3f of a %.3f mm defect from %d samples. It '
                'excludes corner-adjacent samples and a corner is where this defect is, so its '
                'exactly-nominal reading on a real wall cannot be trusted and it is disqualified.'
                % (frac, corner.features[1]['depth'], n))

    def test_every_candidate_is_reported_at_a_corner(self, corner, loops, capsys):
        """The comparative table. A measure that is blind here is unusable whatever else it does,
        so this is worth seeing for all of them at once."""
        rows = []
        for name, measure in sorted(candidates.REGISTRY.items()):
            try:
                frac, n, _want = _depth_seen(measure, corner, loops)
            except Exception as exc:                                     # noqa: BLE001
                rows.append((name, None, 0, type(exc).__name__))
                continue
            rows.append((name, frac, n, 'blind' if frac < BLINDNESS_FRAC else 'sees it'))
        with capsys.disabled():
            print('\n    corner-defect visibility (limit %.0f%% of the depth):'
                  % (BLINDNESS_FRAC * 100.0))
            for name, frac, n, note in rows:
                print('      %-26s %-10s %6d samples  %s'
                      % (name, '-' if frac is None else '%.1f%%' % (frac * 100.0), n, note))
        assert rows
