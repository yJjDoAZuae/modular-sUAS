"""IP-WTM-5 to IP-WTM-9: the screening run. Four candidates, five gates, one table.

The gates and their thresholds were fixed in `wall_measure.gates` before any candidate was written,
and the tie-break is pre-committed in `gates.rank`, so what comes out of here is a selection and not
a preference. This file runs it and asserts the properties the result must have, whichever candidate
wins — then prints the table that IP-WTM-9 records in the design document.

**G2 is scored on a real saved wall, not on a fixture.** That is the whole lesson of the first
screening run: the incumbent passes every synthetic gate, including convergence at 0.000018 mm
contracting 4x a doubling, and fails on a real section at 0.0043 mm still moving. A concentric
annulus has no concave corner for a nearest-point distance to cut across, so screening convergence
there would pass the measure this work exists to replace.

See doc/implementation/wall_thickness_measure.md.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import candidates, corpus, gates, sections, truth        # noqa: E402

from conftest import requires_freecad                                      # noqa: E402

requires_corpus = pytest.mark.skipif(
    not corpus.available(),
    reason='no saved soak walls; the authoritative convergence gate needs one')

#: The acceptance target a pass/fail candidate is asked about: nominal minus the tolerance.
TARGET = truth.WALL - 0.01


def _measures():
    """The per-sample thickness measures. C3 is screened separately: it reports one boolean a
    station, not a thickness a sample, so it cannot answer gates G1 or G4."""
    return dict(candidates.REGISTRY)


@pytest.fixture(scope='module')
def screened(request):
    """One screening run, shared by every assertion below -- it is the expensive fixture here."""
    from geometry_bridge.api import freecad_session
    session = freecad_session()
    request.addfinalizer(session.close)
    Part = session.module('Part')
    App = session.module('FreeCAD')

    fixtures = {'uniform_tube': truth.uniform_tube(Part, App),
                'thin_patch_tube': truth.thin_patch_tube(Part, App),
                'ribbed_tube': truth.ribbed_tube(Part, App)}

    def loops_at(truth_obj, z, n):
        loops = sections.station_loops(truth_obj.shape, z, n, App=App)
        assert len(loops) >= 2, 'expected two loops at z=%.3f, got %d' % (z, len(loops))
        return loops[0], loops[1]

    rec = corpus.one()
    wall = corpus.load(Part, rec) if rec is not None else None
    z = corpus.interior_station(wall) if wall is not None else None

    return gates.screen_full(_measures(), fixtures, loops_at, wall, z, App)


@requires_freecad
@requires_corpus
class TestTheScreeningRun:

    def test_every_candidate_was_scored_on_every_gate(self, screened):
        assert set(screened) == set(_measures())
        for name, (res, _cost) in screened.items():
            seen = [r.gate.split()[0] for r in res]
            assert seen == ['G1', 'G2', 'G3', 'G4', 'G5'], (name, seen)

    def test_the_incumbent_is_rejected_by_the_convergence_gate(self, screened):
        """The premise of this whole plan, asserted rather than assumed. If the incumbent were
        selectable there would be nothing to do."""
        res, _cost = screened['C0_nearest_point_min']
        by = dict((r.gate, r) for r in res)
        assert not by['G2 convergence'].passed, by['G2 convergence'].detail
        assert not all(r.passed for r in res)

    def test_at_least_one_candidate_improves_on_the_incumbent_somewhere(self, screened):
        """A screening in which nothing beats the baseline on any gate would mean the candidates
        were not worth writing, and that is worth knowing explicitly."""
        base_res, _base_cost = screened['C0_nearest_point_min']
        base = dict((r.gate, r) for r in base_res)
        better = []
        for name, (res, _cost) in screened.items():
            if name == 'C0_nearest_point_min':
                continue
            by = dict((r.gate, r) for r in res)
            for g, r in by.items():
                if r.passed and not base[g].passed:
                    better.append((name, g))
        assert better, 'no candidate passed a gate the incumbent failed'

    def test_the_erosion_guard_is_not_in_the_per_sample_table(self, screened):
        """C3 cannot answer a per-sample gate, and an earlier stand-in that pretended it could was
        the incumbent with a clamp -- it inherited the incumbent's depth readings and passed the
        very gate it should be unable to pass. It is screened on its own terms instead."""
        assert 'C3_polygon_erosion' not in screened

    def test_the_ranking_only_contains_candidates_that_passed_everything(self, screened):
        for name in gates.rank(screened):
            res, _cost = screened[name]
            assert all(r.passed for r in res), name

    def test_the_result_table_is_printed_for_the_record(self, screened, capsys):
        """IP-WTM-9's artifact. Printed so the figures reach the log and the design document."""
        text = gates.table(screened)
        order = gates.rank(screened)
        with capsys.disabled():
            print('\n' + text)
            print('\n  ranking (pre-committed tie-break: cheapest by G5, then smaller G2 '
                  'residual): %s' % (' > '.join(order) if order else 'NOTHING PASSED ALL GATES'))
            for name in sorted(screened):
                res, cost = screened[name]
                print('\n  %s  (G5 %s)' % (name, gates._fmt(cost)))
                for r in res:
                    print('    %-18s %-5s %-12s %s'
                          % (r.gate, 'pass' if r.passed else 'FAIL', gates._fmt(r.value),
                             r.detail))
        assert 'candidate' in text

    def test_the_outcome_is_recorded_as_a_decision_or_as_a_universal_failure(self, screened):
        """Either a candidate is selected, or every candidate failed and *which* gate they all
        failed is the next step. Both are answers; neither is a judgment call."""
        order = gates.rank(screened)
        if order:
            assert isinstance(order[0], str)
        else:
            failed_by_all = None
            for _name, (res, _cost) in screened.items():
                mine = set(r.gate for r in res if not r.passed)
                failed_by_all = mine if failed_by_all is None else (failed_by_all & mine)
            assert failed_by_all, (
                'nothing passed, yet no single gate was failed by everything -- the screening '
                'needs reading candidate by candidate')

@requires_freecad
class TestTheErosionGuardOnItsOwnTerms:
    """C3. One boolean a station: is the wall at least `target` everywhere here?

    Screened for the two things it can be judged on -- does it answer correctly, and is it cheap --
    since it cannot supply a depth or a location. If it works it is worth keeping as a build-time
    guard beside whichever measure the table selects, because its answer needs no sample spacing
    and so has nothing to converge.
    """

    @pytest.fixture
    def kit(self, fc, Part, App):
        return Part, App, {
            'uniform_tube': truth.uniform_tube(Part, App),
            'thin_patch_tube': truth.thin_patch_tube(Part, App),
        }

    def _loops(self, t, z, App, n=720):
        return sections.station_loops(t.shape, z, n, App=App)[:2]

    def test_a_compliant_wall_survives_the_erosion(self, kit, App):
        """0.6 mm of wall against a 0.59 mm target: it must survive."""
        Part, _App, fx = kit
        outer, inner = self._loops(fx['uniform_tube'], 1.0, App)
        ok, detail = candidates.survives_erosion(Part, App, outer, inner, TARGET)
        assert ok, detail

    def test_a_thin_patch_does_not_survive(self, kit, App):
        """The converse, and the whole point: 0.45 mm in the patch against a 0.59 mm target."""
        Part, _App, fx = kit
        t = fx['thin_patch_tube']
        outer, inner = self._loops(t, t.features[0]['z_mid'], App)
        ok, detail = candidates.survives_erosion(Part, App, outer, inner, TARGET)
        assert not ok, detail

    def test_the_target_is_what_decides_it(self, kit, App):
        """Not merely sensitive to the shape: the same section must flip with the target, or the
        guard is reporting something other than the thickness it was asked about."""
        Part, _App, fx = kit
        outer, inner = self._loops(fx['uniform_tube'], 1.0, App)
        assert candidates.survives_erosion(Part, App, outer, inner, 0.40)[0] is True
        assert candidates.survives_erosion(Part, App, outer, inner, 0.80)[0] is False

    def test_the_polygon_reopens_the_route_the_bspline_closed(self, kit, App, capsys):
        """**IP-FC-151 closed this route at over six minutes for one call on an exact B-spline
        section. On a polygon it completes, which reopens it -- but not cheaply.**

        Measured 2026-10-10 at 720 samples a loop (so 1440 polygon edges): about 12 s a station.
        That is better than the B-spline by more than an order of magnitude and still over gate
        G5's budget once multiplied by 12 stations, so the open question this leaves is whether a
        coarser polygon comes in under 60 s while staying accurate enough to decide a 0.01 mm
        question. Asserted loosely against the figure that closed the route, not against a
        threshold invented to fit this measurement.
        """
        import time
        Part, _App, fx = kit
        outer, inner = self._loops(fx['uniform_tube'], 1.0, App)
        started = time.time()
        ok, _detail = candidates.survives_erosion(Part, App, outer, inner, TARGET)
        took = time.time() - started
        with capsys.disabled():
            print('\n    erosion guard: %.1f s a station at 720 samples a loop '
                  '(12 stations ~ %.0f s against G5 %.0f s)'
                  % (took, took * 12.0, gates.COST_LIMIT_S))
        assert ok
        assert took < 60.0, (
            '%.1f s -- the B-spline route was closed at over 360 s for one call, so a polygon '
            'that is no better has not reopened anything' % took)

    def test_twelve_stations_at_this_density_exceeds_the_cost_gate(self, kit, App):
        """Recorded as an assertion so it is not mistaken for an unmeasured worry: at 720 samples
        the guard does not fit G5, and whether a coarser polygon does is untested."""
        import time
        Part, _App, fx = kit
        outer, inner = self._loops(fx['uniform_tube'], 1.0, App)
        started = time.time()
        candidates.survives_erosion(Part, App, outer, inner, TARGET)
        per_station = time.time() - started
        assert per_station * 12.0 > gates.COST_LIMIT_S, (
            'the guard now fits G5 at this density (%.1f s for 12 stations); if this fails, the '
            'cost finding has changed and the plan should say so' % (per_station * 12.0))
