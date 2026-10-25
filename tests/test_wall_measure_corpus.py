"""IP-WTM-15: the saved-wall corpus, and the convergence gate measured on a real section.

**This file exists because the measurement in it was first run from a throwaway heredoc.** The
single most important result so far — that the incumbent wall-thickness measure does not converge
on a real wall — had no reproducible provenance: a number quoted in a design document that nobody
could re-derive and nothing would regress. The sweep now lives in `gates.refinement_sweep`, the
corpus access in `wall_measure.corpus`, and the claim is asserted here.

The corpus is build output and is not in version control, so every test that needs it skips rather
than fails when it is absent — a missing 412 MB of BREP is not a code defect.

See doc/implementation/wall_thickness_measure.md.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import candidates, corpus, gates, sections                # noqa: E402

from conftest import requires_freecad                                       # noqa: E402

#: The corpus is build output; without it there is nothing to measure.
requires_corpus = pytest.mark.skipif(
    not corpus.available(),
    reason='no saved soak walls in %s; run soak_shell_variants.py to build them' % corpus.SHAPES_DIR)


# ------------------------------------------------------------------ corpus bookkeeping, no vendor



class _ClosedWire(object):
    """Enough of a wire for `sections.closed_wires`, which only asks whether it is closed."""

    Length = 1.0

    def isClosed(self):                                            # noqa: N802 - vendor spelling
        return True

class TestCorpusDiscovery:

    def test_an_absent_corpus_is_empty_not_an_error(self, tmp_path):
        """A test that needs real geometry should skip, not fail, when the files are not there."""
        assert corpus.available(shapes_dir=str(tmp_path / 'nope')) == []
        assert corpus.recorded_results(results=str(tmp_path / 'nope.jsonl')) == {}

    def test_a_filename_parses_into_its_build_parameters(self, tmp_path):
        d = tmp_path / 'shapes'
        d.mkdir()
        for name in ('tail_shell_U4.0_r3.brep', 'nose_cowl_shell_U0.5_r0.brep', 'notes.txt'):
            (d / name).write_text('x')
        got = corpus.available(shapes_dir=str(d), results=str(tmp_path / 'none.jsonl'))
        assert [r.label for r in got] == ['nose_cowl_shell_U0.5_r0', 'tail_shell_U4.0_r3']
        assert got[1].kind == 'tail_shell' and got[1].u == '4.0' and got[1].repeat == 3

    def test_records_sort_by_kind_then_u_numerically(self, tmp_path):
        """`U` = 10 must not sort before `U` = 2, which it would as text."""
        d = tmp_path / 'shapes'
        d.mkdir()
        for u in ('0.5', '2.0', '10.0'):
            (d / ('tail_shell_U%s_r0.brep' % u)).write_text('x')
        got = corpus.available(shapes_dir=str(d), results=str(tmp_path / 'none.jsonl'))
        assert [r.u for r in got] == ['0.5', '2.0', '10.0']

    def test_a_results_row_is_joined_to_its_shape(self, tmp_path):
        d = tmp_path / 'shapes'
        d.mkdir()
        (d / 'tail_shell_U1.0_r2.brep').write_text('x')
        res = tmp_path / 'r.jsonl'
        res.write_text('{"kind":"tail_shell","u":1.0,"repeat":2,"worst_wall_error":0.0243}\n')
        got = corpus.available(shapes_dir=str(d), results=str(res))
        assert got[0].recorded['worst_wall_error'] == pytest.approx(0.0243)

    def test_a_shape_with_no_results_row_still_appears(self, tmp_path):
        d = tmp_path / 'shapes'
        d.mkdir()
        (d / 'tail_shell_U9.0_r0.brep').write_text('x')
        got = corpus.available(shapes_dir=str(d), results=str(tmp_path / 'none.jsonl'))
        assert len(got) == 1 and got[0].recorded is None


@requires_corpus
class TestTheRealCorpus:

    def test_all_28_soak_walls_are_present_and_joined(self):
        recs = corpus.available()
        assert len(recs) == 28, 'expected the 2026-10-06 soak corpus, found %d' % len(recs)
        assert all(r.recorded is not None for r in recs), 'every wall should have a results row'
        kinds = sorted(set(r.kind for r in recs))
        assert kinds == ['nose_cowl_shell', 'tail_shell']

    def test_the_cheapest_useful_wall_is_findable(self):
        rec = corpus.one()
        assert rec is not None and rec.label == 'nose_cowl_shell_U1.0_r0'
        assert os.path.getsize(rec.path) > 1_000_000


# ------------------------------------------------------------------ against the real geometry


@pytest.fixture
def real_wall(fc, Part):
    rec = corpus.one()
    if rec is None:
        pytest.skip('no saved wall')
    return rec, corpus.load(Part, rec)


@requires_freecad
@requires_corpus
class TestLoadingAndStations:

    def test_a_saved_wall_loads_as_one_valid_solid(self, real_wall):
        _rec, wall = real_wall
        assert len(wall.Solids) == 1
        assert wall.isValid()

    def test_the_station_grid_is_evenly_spaced_across_the_saved_wall(self, real_wall):
        """**Not the acceptance check's own grid, and this test asserted that it was.** The gate and
        the soak both place stations from `ci.z_extent(body)` -- the full cowl solid -- while the
        corpus saves only the finished wall, whose z extent is different. What is checkable here is
        what the function actually promises: `STATIONS` stations, evenly spaced, inset from the
        wall's own ends. `gate_station_grid` is the one that reproduces the gate (IP-WTM-18)."""
        _rec, wall = real_wall
        zs = corpus.station_grid(wall)
        assert len(zs) == corpus.STATIONS
        bb = wall.BoundBox
        assert zs[0] == pytest.approx(bb.ZMin + corpus.END_INSET)
        assert zs[-1] == pytest.approx(bb.ZMax - corpus.END_INSET)
        gaps = np.diff(zs)
        assert np.allclose(gaps, gaps[0])

    def test_a_sectioning_extent_ignores_a_loose_bounding_box(self):
        """**The defect that lost the nose its stations.** A bounding box on these solids is an
        outer bound only -- measured 2026-10-10, a `nose_cowl_shell` wall at `U` = 4 has a box
        spanning -400 to -12 where the part really spans -200 to -24, twice its length. A box-based
        grid then places end stations in empty space. Modeled here with a stub whose box is
        deliberately twice its material."""

        class LooseBox(object):
            class BoundBox(object):
                ZMin, ZMax = -400.0, 0.0

            def __init__(self, lo, hi):
                self.lo, self.hi = lo, hi

            def slice(self, _direction, z):
                return [_ClosedWire()] if self.lo <= z <= self.hi else []

        shape = LooseBox(-200.0, -24.0)
        lo, hi = corpus.sectioning_extent(shape, tol=1.0e-4)
        assert lo == pytest.approx(-200.0, abs=1.0e-3)
        assert hi == pytest.approx(-24.0, abs=1.0e-3)

    def test_a_station_grid_on_the_real_extent_stays_inside_the_material(self):
        class LooseBox(object):
            class BoundBox(object):
                ZMin, ZMax = -400.0, 0.0

            def slice(self, _direction, z):
                return [_ClosedWire()] if -200.0 <= z <= -24.0 else []

        zs = corpus.measurable_station_grid(LooseBox())
        assert len(zs) == corpus.STATIONS
        assert all(-200.0 <= z <= -24.0 for z in zs), zs
        assert zs[0] == pytest.approx(-199.0, abs=0.01)
        assert zs[-1] == pytest.approx(-25.0, abs=0.01)

    def test_a_shape_that_sections_nowhere_reports_no_extent(self):
        """A finding about the shape, not something to guess around."""

        class Empty(object):
            class BoundBox(object):
                ZMin, ZMax = -10.0, 10.0

            def slice(self, _direction, _z):
                return []

        assert corpus.sectioning_extent(Empty()) is None
        # ...and the grid falls back rather than raising, so a caller always gets stations.
        assert len(corpus.measurable_station_grid(Empty())) == corpus.STATIONS

    def test_the_gate_grid_is_none_when_the_soak_did_not_record_it(self):
        """**It must not fall back to the wall-based grid.** The two are answers about different
        places, and a silent fallback is how a figure from one gets differenced against a figure
        from the other -- which withdrew a whole sweep column once already. Every wall in the
        2026-10-06 corpus predates IP-WTM-18, so every one of them returns `None` here."""
        assert corpus.gate_station_grid(corpus.WallRecord('k', '1.0', 0, 'x.brep')) is None
        assert corpus.gate_station_grid(corpus.WallRecord('k', '1.0', 0, 'x.brep',
                                                          recorded={'worst_wall_error': 0.1})) is None

    def test_the_gate_grid_is_rebuilt_from_the_recorded_bounds(self):
        """What IP-WTM-18 added to `soak_cowl_shell`: the body-derived bounds the gate placed its
        own stations from, which is the one thing the saved wall cannot recover."""
        rec = corpus.WallRecord('k', '1.0', 0, 'x.brep',
                                recorded={'station_z_lo': -100.0, 'station_z_hi': -10.0})
        zs = corpus.gate_station_grid(rec)
        assert len(zs) == corpus.STATIONS
        assert zs[0] == pytest.approx(-100.0) and zs[-1] == pytest.approx(-10.0)
        gaps = np.diff(zs)
        assert np.allclose(gaps, gaps[0])

    def test_a_real_section_has_two_closed_loops(self, real_wall, App):
        _rec, wall = real_wall
        loops = sections.station_loops(wall, corpus.interior_station(wall), 720, App=App)
        assert len(loops) == 2


@requires_freecad
@requires_corpus
class TestTheIncumbentDoesNotConvergeOnARealSection:
    """**IP-WTM-15's finding, as an assertion rather than a quoted number.**

    The claim recorded in the plan and in §6.1: the incumbent's minimum keeps moving on a real
    section while its median does not. If a future change makes this test fail, the measure has
    started converging and the plan's premise needs revisiting — which is exactly what a test
    should be for.
    """

    def test_the_minimum_does_not_converge(self, real_wall, App):
        _rec, wall = real_wall
        z = corpus.interior_station(wall)
        r = gates.convergence_gate_on_section(candidates.nearest_point_min, wall, z, App)
        assert not r.passed, (
            'the incumbent converged on a real section: %s -- if this is now true, §6.1 and '
            'OQ-DES-CW27-adjacent reasoning need revisiting' % r.detail)
        assert r.value > gates.CONVERGE_TOL

    def test_the_minimum_moves_by_more_than_the_tolerance_it_is_compared_against(self, real_wall,
                                                                                App):
        """The figure that matters: the instrument's own drift exceeds `WALL_TOL` = 0.01 mm, so it
        cannot certify a 0.01 mm requirement whatever it reads."""
        _rec, wall = real_wall
        z = corpus.interior_station(wall)
        minima, _med = gates.refinement_sweep(
            candidates.nearest_point_min,
            lambda n: tuple(sections.station_loops(wall, z, n, App=App)[:2]))
        spread = float(np.nanmax(minima) - np.nanmin(minima))
        assert spread > 0.01, 'minimum spread only %.6f mm across the sweep' % spread

    def test_the_median_is_stable_across_the_same_sweep(self, real_wall, App):
        """The converse, and the lead for IP-WTM-11: it is the minimum that is unstable, not the
        wall. A measure whose median also wandered would mean the section extraction was at fault
        rather than the nearest-point minimum."""
        _rec, wall = real_wall
        z = corpus.interior_station(wall)
        _minima, medians = gates.refinement_sweep(
            candidates.nearest_point_min,
            lambda n: tuple(sections.station_loops(wall, z, n, App=App)[:2]))
        spread = float(np.nanmax(medians) - np.nanmin(medians))
        assert spread < 0.001, 'median spread %.6f mm' % spread
        assert float(np.nanmedian(medians)) == pytest.approx(0.6, abs=0.005)

    def test_the_sweep_is_cheap_enough_to_run_on_the_whole_corpus(self, real_wall, App):
        """Why IP-WTM-11 is affordable: the expensive part was the build, and it is already paid."""
        import time
        _rec, wall = real_wall
        z = corpus.interior_station(wall)
        started = time.time()
        gates.refinement_sweep(
            candidates.nearest_point_min,
            lambda n: tuple(sections.station_loops(wall, z, n, App=App)[:2]),
            levels=(360, 720))
        assert time.time() - started < 30.0
