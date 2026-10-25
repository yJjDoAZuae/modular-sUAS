"""IP-WTM-3 and IP-WTM-4: the screening harness, and the incumbent scored as the baseline.

Two things have to be true before any candidate's score means anything:

1. **The harness must fail a measure that deserves to fail.** A gate that passes everything is not
   a gate. So the harness is checked against deliberately broken measures -- a constant, a mean,
   and one that reports nothing -- and each must be rejected by the specific gate it offends.
2. **The baseline must be the real incumbent.** `candidates.nearest_point_min` is a `numpy`
   reimplementation of what `check_cowl_interior.wall_thickness` does, and if it diverged the
   screening would be comparing candidates against a straw man. It is checked against the shipped
   `cowl_interior._Polyline.distance` on real geometry.

See doc/implementation/wall_thickness_measure.md.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import candidates, gates, sections, truth               # noqa: E402

from conftest import requires_freecad                                      # noqa: E402


# ------------------------------------------------------------------ the harness, no vendor needed


def _synthetic_annulus(n, r_out=10.0, wall=0.6, z=1.0):
    a = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    outer = np.column_stack((r_out * np.cos(a), r_out * np.sin(a), np.full(n, z)))
    ri = r_out - wall
    inner = np.column_stack((ri * np.cos(a), ri * np.sin(a), np.full(n, z)))
    return outer, inner


class _SyntheticSource(object):
    """Analytic loops, so the harness can be tested without FreeCAD at all."""

    def __call__(self, truth_obj, z, n):
        f = truth_obj.features[0] if truth_obj.features else None
        outer, inner = _synthetic_annulus(n, truth_obj.r_outer, truth_obj.nominal, z)
        if f is not None and f['kind'] == 'thin' and f['z_lo'] <= z <= f['z_hi']:
            ang = np.arctan2(outer[:, 1], outer[:, 0])
            hit = np.abs(ang) <= f['half_angle']
            r = np.hypot(outer[:, 0], outer[:, 1])
            r = np.where(hit, truth_obj.r_outer - f['depth'], r)
            outer = np.column_stack((r * np.cos(ang), r * np.sin(ang), outer[:, 2]))
        return outer, inner


def _uniform_truth():
    return truth.WallTruth(None, 'uniform_tube', 0.6, 10.0)


def _patch_truth(depth=0.15, arc=0.6):
    f = {'kind': 'thin', 'thickness': 0.6 - depth, 'depth': depth,
         'z_lo': 8.0, 'z_hi': 12.0, 'half_angle': arc / 20.0, 'arc': arc,
         'angle': 0.0, 'z_mid': 10.0}
    return truth.WallTruth(None, 'thin_patch_tube', 0.6, 10.0, [f])


@pytest.fixture
def synthetic():
    return {'uniform_tube': _uniform_truth(), 'thin_patch_tube': _patch_truth()}, _SyntheticSource()


class TestTheHarnessRejectsWhatItShould:
    """A gate that passes everything is not a gate."""

    def test_a_constant_measure_fails_locality_and_discrimination(self, synthetic):
        fixtures, src = synthetic

        def always_nominal(outer, inner):
            return inner, np.full(inner.shape[0], 0.6)

        res = gates.screen(always_nominal, fixtures, src)
        by = dict((r.gate, r) for r in res)
        assert by['G3 accuracy'].passed, 'a constant 0.6 is exactly right on a 0.6 wall'
        assert by['G2 convergence'].passed, 'and it converges trivially'
        assert not by['G1 locality'].passed, 'but it cannot see a thin patch'
        assert not by['G4 discrimination'].passed

    def test_a_mean_measure_fails_locality_the_way_the_area_mean_does(self, synthetic):
        """The real reason the converged area-based mean is not the answer, reproduced as a test."""
        fixtures, src = synthetic

        def mean_only(outer, inner):
            _p, t = candidates.nearest_point_min(outer, inner)
            return inner, np.full(inner.shape[0], float(np.mean(t)))

        by = dict((r.gate, r) for r in gates.screen(mean_only, fixtures, src))
        assert not by['G1 locality'].passed
        assert by['G1 locality'].value < gates.LOCALITY_FRAC

    def test_a_measure_reporting_nothing_fails_every_gate(self, synthetic):
        fixtures, src = synthetic

        def empty(outer, inner):
            return inner[:0], np.zeros(0)

        for r in gates.screen(empty, fixtures, src):
            assert not r.passed, r.gate

    def test_a_biased_measure_fails_accuracy_while_converging(self, synthetic):
        """Accuracy and convergence are different questions; the harness must separate them."""
        fixtures, src = synthetic

        def biased(outer, inner):
            p, t = candidates.nearest_point_min(outer, inner)
            return p, t + 0.02

        by = dict((r.gate, r) for r in gates.screen(biased, fixtures, src))
        assert by['G2 convergence'].passed, 'a constant offset still converges'
        assert not by['G3 accuracy'].passed
        assert by['G3 accuracy'].value == pytest.approx(0.02, abs=2e-3)

    def test_a_drifting_measure_fails_convergence_even_with_small_steps(self, synthetic):
        """G2's second condition. A measure moving 0.0009 mm per doubling forever has small steps
        and has not converged, which is the incumbent's actual behavior."""
        fixtures, src = synthetic
        state = {'n': 0}

        def drifting(outer, inner):
            state['n'] += 1
            return inner, np.full(inner.shape[0], 0.6 - 0.0009 * state['n'])

        by = dict((r.gate, r) for r in gates.screen(drifting, fixtures, src))
        assert not by['G2 convergence'].passed
        assert 'NOT contracting' in by['G2 convergence'].detail
        assert by['G2 convergence'].value < gates.CONVERGE_TOL, (
            'the point of this case: every step is under the threshold and it still fails')

    def test_the_tie_break_is_cost_then_residual(self):
        """Pre-committed, so selection is arithmetic. Checked rather than described."""
        ok = [gates.GateResult('G1 locality', True, 1.0, 0.8),
              gates.GateResult('G2 convergence', True, 0.0002, 0.001),
              gates.GateResult('G3 accuracy', True, 0.0001, 0.001),
              gates.GateResult('G4 discrimination', True, 0.0001, 0.002)]
        tighter = list(ok)
        tighter[1] = gates.GateResult('G2 convergence', True, 0.00001, 0.001)
        scored = {'cheap_loose': (ok, 10.0), 'cheap_tight': (tighter, 15.0),
                  'dear_tight': (tighter, 400.0)}
        order = gates.rank(scored)
        # 10 s and 15 s are within 2x, so the smaller G2 residual wins between them; 400 s is not.
        assert order[0] == 'cheap_tight'
        assert order[-1] == 'dear_tight'

    def test_a_failing_candidate_is_never_ranked(self):
        bad = [gates.GateResult('G1 locality', False, 0.1, 0.8)]
        assert gates.rank({'bad': (bad, 1.0)}) == []

    def test_the_table_names_the_offending_gate(self):
        res = [gates.GateResult('G1 locality', False, 0.12, 0.8),
               gates.GateResult('G2 convergence', True, 0.0001, 0.001),
               gates.GateResult('G3 accuracy', True, 0.0001, 0.001),
               gates.GateResult('G4 discrimination', True, 0.0001, 0.002)]
        text = gates.table({'C9_example': (res, 1.0)})
        assert 'C9_example' in text and 'FAIL' in text and 'rejected' in text


# ------------------------------------------------------------------ against real geometry


@pytest.fixture
def loops_at(fc, App):
    """Section loops for a fixture at a station, at a given sampling."""
    def go(truth_obj, z, n):
        loops = sections.station_loops(truth_obj.shape, z, n, App=App)
        assert len(loops) >= 2, 'expected two loops at z=%.3f, got %d' % (z, len(loops))
        return loops[0], loops[1]
    return go


@pytest.fixture
def real_fixtures(fc, Part, App):
    return {'uniform_tube': truth.uniform_tube(Part, App),
            'thin_patch_tube': truth.thin_patch_tube(Part, App),
            'ribbed_tube': truth.ribbed_tube(Part, App)}


@requires_freecad
class TestTheBaselineIsTheRealIncumbent:
    """IP-WTM-4's precondition: the reimplementation must be the shipped measure."""

    def test_it_agrees_with_cowl_interiors_own_polyline_distance(self, real_fixtures, loops_at,
                                                                ci):
        """Checked against `cowl_interior._Polyline.distance`, which is what
        `check_cowl_interior.wall_thickness` actually calls."""
        t = real_fixtures['uniform_tube']
        outer, inner = loops_at(t, 1.0, 360)
        _p, mine = candidates.nearest_point_min(outer, inner)

        line = ci._Polyline([(float(x), float(y)) for x, y in outer[:, :2]])
        theirs = np.array([line.distance(float(p[0]), float(p[1])) for p in inner[:40]])
        assert np.allclose(mine[:40], theirs, atol=1e-9), (
            'max divergence %.3e' % float(np.max(np.abs(mine[:40] - theirs))))

    def test_it_agrees_on_the_ribbed_fixture_too(self, real_fixtures, loops_at, ci):
        """The shape with concave corners, where the two could most easily differ."""
        t = real_fixtures['ribbed_tube']
        outer, inner = loops_at(t, t.features[0]['z_mid'], 360)
        _p, mine = candidates.nearest_point_min(outer, inner)
        line = ci._Polyline([(float(x), float(y)) for x, y in outer[:, :2]])
        theirs = np.array([line.distance(float(p[0]), float(p[1])) for p in inner[:60]])
        assert np.allclose(mine[:60], theirs, atol=1e-9)

    def test_distance_is_to_the_segment_not_the_nearest_vertex(self):
        """A vertex-only distance would add up to half the sample spacing -- 0.04 mm at 720 samples
        on a 60 mm loop, four times `WALL_TOL` -- and it would look like the measure's own error."""
        poly = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [0.0, 10.0, 0.0]])
        pt = np.array([[5.0, 3.0, 0.0]])
        got = candidates._segment_distances(pt, poly)
        assert got[0] == pytest.approx(3.0, abs=1e-12)      # to the segment, not to a corner


@requires_freecad
class TestTheIncumbentScored:
    """**IP-WTM-4.** The baseline every candidate is compared against."""

    def test_the_incumbent_is_accurate_on_a_clean_annulus(self, real_fixtures, loops_at):
        """It is not a bad measure everywhere -- on a shape with no concave corner it is fine, and
        that is why the failure took so long to find."""
        r = gates.accuracy_gate(candidates.nearest_point_min,
                                real_fixtures['uniform_tube'], loops_at)
        assert r.passed, r.detail

    def test_the_incumbent_sees_the_thin_patch(self, real_fixtures, loops_at):
        """Also not its problem: locality is the one thing a nearest-point minimum does well."""
        r = gates.locality_gate(candidates.nearest_point_min,
                                real_fixtures['thin_patch_tube'], loops_at)
        assert r.passed, r.detail

    def test_the_incumbent_scored_against_all_four_gates(self, real_fixtures, loops_at, capsys):
        """The baseline row, recorded. Printed so the figures land in the test log."""
        res = gates.screen(candidates.nearest_point_min, real_fixtures, loops_at)
        with capsys.disabled():
            print('\n  incumbent (C0_nearest_point_min):')
            for r in res:
                print('    %-18s %-5s value %-12s limit %s'
                      % (r.gate, 'pass' if r.passed else 'FAIL',
                         gates._fmt(r.value), gates._fmt(r.threshold)))
                print('        %s' % r.detail)
        assert len(res) == 4
