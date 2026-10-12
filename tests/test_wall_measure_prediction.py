"""IP-WTM-13: pass 2's own prediction, set against the real wall a converging measure reads.

OQ-DES-CW23 is built on a residual gap between `cavity()`'s post-cut prediction and the real,
rib-cut wall. The figures it was argued on came from one build's 12 stations with the real side read
by the nearest-point minimum — the measure since shown not to converge (gate G2). This file holds
the re-answer at corpus scale, and the parser that makes it reproducible.

**No vendor module and no build.** Both sides of the comparison are already on disk: the prediction
in the soak's own log, the real reading in the sweep's JSONL. Every test here is a parse plus
arithmetic, so the whole file runs in the fast tier.

The synthetic-log tests are the ones that pin the parser's behaviour; the corpus tests assert what
this project's own 28 builds say and skip when the artifacts are absent, since they are build output
and are not in version control.

See doc/implementation/wall_thickness_measure.md and doc/design/cowl.md OQ-DES-CW23.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import prediction                                         # noqa: E402

#: Two builds, one that passed round 0 outright and one that needed two insertion rounds. Written to
#: the real log's own format, including the indentation and the surrounding noise a `freecadcmd` run
#: leaves, so a change to `note()`'s wording fails these tests rather than silently returning zero
#: builds in production.
SYNTHETIC_LOG = """=== nose_cowl_shell U=0.5 repeat=0 ===
    interior: z -24.999 .. -3.001, 120 fit points (0.199 mm apart), 480 check points
    patch 1/1  z  -24.9987 ..   -3.0015 (21.997 mm)  10 seeded -> 10 stations  worst wall 0.0064   11.9 s  [12 s total]
        at -24.9977 -24.0000 -22.9497
    fusing 3 pieces
    ribs cut in 1 s, 0.000000 mm3 left inside
        patch 1/1 scan: 40 uniform + 18 edge-focused (4 notch edge(s)) -> 57 points
    cavity closed: 1 solids, valid=True, 5980.6207 mm3, worst finished wall error 0.0019 mm, 29 s in all
    wall: 2406.5128 mm3 in 1 solid(s) after 3 mirror step(s)
SOAK_RESULT {"kind": "nose_cowl_shell", "u": 0.5, "repeat": "0"}
FreeCAD 1.1.3, Libs: 1.1.3R20260725 (Git shallow)
(C) 2001-2026 FreeCAD contributors


=== tail_shell U=3.0 repeat=0 ===
    patch 1/2  z  -283.9951 ..  -217.7261 (66.269 mm)  12 seeded -> 12 stations  worst wall 0.0129   14.2 s
    patch 2/2  z  -217.7261 ..  -142.5218 (75.204 mm)  12 seeded -> 12 stations  worst wall 0.0301   15.0 s
        patch 1/2 scan: 43 uniform + 20 edge-focused (4 notch edge(s)) -> 63 points
        patch 2/2 scan: 50 uniform + 24 edge-focused (6 notch edge(s)) -> 74 points
        post-cut refine: round 1, worst finished-wall gap 0.0601 mm over 0.050, inserting 2 station(s)
        post-cut refine: round 2, worst finished-wall gap 0.0576 mm over 0.050, inserting 1 station(s)
    cavity closed: 1 solids, valid=True, 47243.2157 mm3, worst finished wall error 0.0484 mm, 333 s in all
SOAK_RESULT {"kind": "tail_shell", "u": 3.0, "repeat": "0"}
"""

#: A build that ran out of rounds: pass 2 kept inserting and `Unconverged` ended it, so there is no
#: `cavity closed` line and nothing shipped.
UNCONVERGED_LOG = """=== tail_shell U=4.0 repeat=0 ===
    patch 1/1  z  -300.0 ..  -200.0 (100.0 mm)  12 seeded -> 12 stations  worst wall 0.0200   14.2 s
        patch 1/1 scan: 60 uniform + 20 edge-focused (4 notch edge(s)) -> 80 points
        post-cut refine: round 1, worst finished-wall gap 0.0900 mm over 0.050, inserting 3 station(s)
SOAK_ERROR {"kind": "tail_shell", "u": 4.0, "error": "Unconverged"}
"""

M = 'C4_corner_excluded_min'
OTHER = 'C0_nearest_point_min'


def write(tmp_path, text, name='soak_log.txt'):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return str(p)


def write_sweep(tmp_path, rows, name='sweep.jsonl'):
    p = tmp_path / name
    p.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    return str(p)


def sweep_row(kind, u, repeat=0, real=0.2, other=0.3, coverage=12, stations=12):
    return {'kind': kind, 'u': u, 'repeat': repeat,
            'label': '%s_U%s_r%d' % (kind, u, repeat),
            'stations': stations,
            'worst_thin': {M: real, OTHER: other},
            'stations_measured': {M: coverage, OTHER: coverage}}


# ------------------------------------------------------------------------------ the log parser


class TestParseBuildLog:

    def test_an_absent_log_is_empty_not_an_error(self, tmp_path):
        assert prediction.parse_build_log(str(tmp_path / 'nope.txt')) == []
        assert prediction.predictions(str(tmp_path / 'nope.txt')) == {}

    def test_each_build_header_starts_a_record(self, tmp_path):
        builds = prediction.parse_build_log(write(tmp_path, SYNTHETIC_LOG))
        assert [b.label for b in builds] == ['nose_cowl_shell_U0.5_r0', 'tail_shell_U3.0_r0']
        assert [b.key for b in builds] == [('nose_cowl_shell', 0.5, 0), ('tail_shell', 3.0, 0)]

    def test_the_predicted_thinness_is_the_cavity_closed_figure(self, tmp_path):
        a, b = prediction.parse_build_log(write(tmp_path, SYNTHETIC_LOG))
        assert a.predicted == pytest.approx(0.0019)
        assert b.predicted == pytest.approx(0.0484)

    def test_pass_1_worst_is_the_largest_over_the_patches(self, tmp_path):
        """Pass 1 prints one figure per patch; the build's own worst is the maximum of them."""
        a, b = prediction.parse_build_log(write(tmp_path, SYNTHETIC_LOG))
        assert a.pass1_worst == pytest.approx(0.0064)
        assert b.pass1_worst == pytest.approx(0.0301)

    def test_scan_points_sum_over_patches(self, tmp_path):
        """What makes the prediction a near-complete scan rather than a sample."""
        a, b = prediction.parse_build_log(write(tmp_path, SYNTHETIC_LOG))
        assert a.scan_points == 57
        assert b.scan_points == 63 + 74

    def test_rounds_and_their_gaps_are_recorded_in_order(self, tmp_path):
        a, b = prediction.parse_build_log(write(tmp_path, SYNTHETIC_LOG))
        assert a.rounds == 0 and a.round_gaps == []
        assert b.rounds == 2
        assert b.round_gaps == [pytest.approx(0.0601), pytest.approx(0.0576)]

    def test_pass_1_and_pass_2_figures_are_not_confused(self, tmp_path):
        """Both lines print a number after the words 'worst wall'. They are different quantities:
        pass 1 is the smooth surface against the true erosion, pass 2 the finished, rib-cut wall."""
        _a, b = prediction.parse_build_log(write(tmp_path, SYNTHETIC_LOG))
        assert b.pass1_worst != b.predicted

    def test_a_build_that_never_closed_is_not_converged(self, tmp_path):
        builds = prediction.parse_build_log(write(tmp_path, UNCONVERGED_LOG))
        assert len(builds) == 1
        assert builds[0].converged is False
        assert builds[0].predicted is None
        assert builds[0].rounds == 1

    def test_lines_before_the_first_header_are_ignored(self, tmp_path):
        """A log starts with the driver's own banner, not a build."""
        text = 'driver starting, 28 builds queued\ncavity closed: worst finished wall error 9 mm\n'
        assert prediction.parse_build_log(write(tmp_path, text + SYNTHETIC_LOG))[0].predicted == \
            pytest.approx(0.0019)


# ---------------------------------------------------------------------------------- the pairing


class TestPair:

    def test_a_build_is_paired_to_its_own_sweep_row(self, tmp_path):
        rows = prediction.pair(
            M, log=write(tmp_path, SYNTHETIC_LOG),
            sweep_path=write_sweep(tmp_path, [sweep_row('tail_shell', 3.0, real=0.1514),
                                              sweep_row('nose_cowl_shell', 0.5, real=0.0010)]))
        by = dict((r['label'], r) for r in rows)
        assert by['tail_shell_U3.0_r0']['predicted'] == pytest.approx(0.0484)
        assert by['tail_shell_U3.0_r0']['real'] == pytest.approx(0.1514)
        assert by['nose_cowl_shell_U0.5_r0']['predicted'] == pytest.approx(0.0019)

    def test_the_shortfall_is_clamped_at_zero_not_signed(self, tmp_path):
        """The two sides are maxima over different grids, and the sweep's is a lower bound. A real
        reading *below* the prediction is therefore not evidence the prediction was pessimistic, so
        this pairing refuses to report it as a negative gap."""
        rows = prediction.pair(
            M, log=write(tmp_path, SYNTHETIC_LOG),
            sweep_path=write_sweep(tmp_path, [sweep_row('tail_shell', 3.0, real=0.0001)]))
        assert rows[0]['real'] == pytest.approx(0.0001)
        assert rows[0]['shortfall'] == 0.0

    def test_an_incomplete_wall_is_excluded_by_default(self, tmp_path):
        """IP-WTM-19: an unmeasured station is not a passing one."""
        sweep = write_sweep(tmp_path, [sweep_row('tail_shell', 3.0, coverage=7)])
        log = write(tmp_path, SYNTHETIC_LOG)
        assert prediction.pair(M, log=log, sweep_path=sweep) == []
        kept = prediction.pair(M, log=log, sweep_path=sweep, full_coverage_only=False)
        assert len(kept) == 1 and kept[0]['coverage'] == 7

    def test_an_unconverged_build_is_never_paired(self, tmp_path):
        """It shipped nothing, so there is no prediction to hold against a wall."""
        rows = prediction.pair(
            M, log=write(tmp_path, UNCONVERGED_LOG),
            sweep_path=write_sweep(tmp_path, [sweep_row('tail_shell', 4.0)]))
        assert rows == []

    def test_a_measure_the_sweep_did_not_run_yields_nothing(self, tmp_path):
        rows = prediction.pair(
            'C9_not_a_measure', log=write(tmp_path, SYNTHETIC_LOG),
            sweep_path=write_sweep(tmp_path, [sweep_row('tail_shell', 3.0)]))
        assert rows == []

    def test_a_sweep_row_with_no_build_in_the_log_is_dropped(self, tmp_path):
        rows = prediction.pair(
            M, log=write(tmp_path, SYNTHETIC_LOG),
            sweep_path=write_sweep(tmp_path, [sweep_row('tail_shell', 1.0)]))
        assert rows == []


# ----------------------------------------------------------------------------------- the verdict


class TestVerdict:

    def test_a_real_reading_over_tau_defeats_any_tightening_of_pass_2(self, tmp_path):
        """The whole point. Pass 2 is inside its own criterion while the real wall is not, so no
        tighter criterion on pass 2's own quantity can certify the part."""
        v = prediction.verdict(
            M, log=write(tmp_path, SYNTHETIC_LOG),
            sweep_path=write_sweep(tmp_path, [sweep_row('tail_shell', 3.0, real=0.2136),
                                              sweep_row('nose_cowl_shell', 0.5, real=0.0010)]))
        assert v['builds_paired'] == 2
        assert v['predictions_within_tau'] is True
        assert v['max_predicted'] == pytest.approx(0.0484)
        assert v['builds_real_worse_than_tau'] == 1
        assert v['worst_label'] == 'tail_shell_U3.0_r0'
        assert v['worst_shortfall'] == pytest.approx(0.2136 - 0.0484)

    def test_it_counts_builds_meeting_the_acceptance_tolerance(self, tmp_path):
        v = prediction.verdict(
            M, log=write(tmp_path, SYNTHETIC_LOG),
            sweep_path=write_sweep(tmp_path, [sweep_row('tail_shell', 3.0, real=0.2136),
                                              sweep_row('nose_cowl_shell', 0.5, real=0.0010)]))
        assert v['builds_real_worse_than_tolerance'] == 1
        assert v['builds_meeting_tolerance'] == 1

    def test_an_empty_pairing_reports_no_figures_rather_than_zeros(self, tmp_path):
        """A verdict with nothing in it must not read as 'every build complies'."""
        v = prediction.verdict(M, log=write(tmp_path, SYNTHETIC_LOG),
                               sweep_path=write_sweep(tmp_path, [sweep_row('tail_shell', 9.0)]))
        assert v['builds_paired'] == 0
        assert v['worst_shortfall'] is None
        assert v['max_predicted'] is None
        assert v['builds_meeting_tolerance'] == 0

    def test_tau_is_pass_2s_criterion_and_wall_tol_is_five_times_tighter(self):
        """Carried in this module so a reader need not go and find them; asserted so a change to
        either in `cowl_interior` fails here instead of silently rescoring the verdict."""
        assert prediction.TAU == 0.05
        assert prediction.WALL_TOL == 0.01
        assert prediction.TAU == pytest.approx(5 * prediction.WALL_TOL)


# ------------------------------------------------------------- this project's own 28 builds


requires_log = pytest.mark.skipif(not os.path.isfile(prediction.DEFAULT_LOG),
                                  reason='no soak log at %s' % prediction.DEFAULT_LOG)
requires_sweep = pytest.mark.skipif(not os.path.isfile(prediction.DEFAULT_SWEEP),
                                    reason='no selected sweep at %s' % prediction.DEFAULT_SWEEP)


@requires_log
class TestTheRealSoakLog:

    def test_the_log_holds_twenty_eight_converged_builds(self):
        builds = prediction.parse_build_log()
        assert len(builds) == 28
        assert all(b.converged for b in builds)

    def test_every_build_shipped_inside_pass_2s_own_criterion(self):
        """What makes the comparison below an inequality rather than a correlation: pass 2's
        guarantee held on all 28, so the prediction side is not in doubt."""
        builds = prediction.parse_build_log()
        worst = max(b.predicted for b in builds)
        assert worst <= prediction.TAU
        assert worst == pytest.approx(0.0484, abs=1e-4)

    def test_pass_2s_scan_is_dense_enough_to_call_near_complete(self):
        """The one-sided inequality rests on this: pass 2 scans tens to hundreds of points per
        build, against the acceptance grid's 12 stations."""
        for b in prediction.parse_build_log():
            assert b.scan_points >= 50


@requires_log
@requires_sweep
class TestTheCorpusAnswer:

    def test_pass_2s_prediction_tracks_the_real_wall(self):
        """**IP-WTM-13's answer, and it is the opposite of what this file first asserted.**

        An earlier version required the real wall to read thinner than `TAU` = 0.05 mm on at least
        one build and the worst shortfall to exceed `WALL_TOL`. Both held only against the first
        corpus sweep, which fixed the sample count at 1 440 a loop and so sampled a `U` = 4 section
        1.45 mm apart on a 0.6 mm wall. Measured at a fixed 0.125 mm spacing, **no build's real wall
        exceeds `TAU`** and pass 2's prediction is within half of `WALL_TOL` of the part everywhere.
        The quantity pass 2 converges is very nearly the one that matters.

        **The shortfall bound belongs to the selected measure only, and asserting it of both was
        this test's own error** -- caught 2026-10-11 once `corpus.measurable_station_grid` placed
        the nose's stations on its real extent rather than its bounding box. C0 is corner-blind:
        it reads 0.0294-0.0380 mm on every nose wall whatever `U` is, because it is reading a
        corner, which is the entire reason C4 was selected (§6.4). Pass 2 predicts the wall, so a
        shortfall against a measure that does not read the wall at a corner says nothing about
        pass 2. C0's figures are kept below as what they are.
        """
        for name in (M, OTHER):
            v = prediction.verdict(name)
            assert v['builds_paired'] >= 6, name
            assert v['predictions_within_tau'] is True, name
            assert v['builds_real_worse_than_tau'] == 0, name
        selected = prediction.verdict(M)
        assert selected['worst_shortfall'] <= prediction.WALL_TOL
        assert selected['mean_shortfall'] < 0.2 * prediction.WALL_TOL

    def test_the_incumbent_measures_a_corner_not_the_wall_on_every_nose_build(self):
        """The converse of the test above, and the evidence for scoping it. C0's nose readings sit
        in a 1.3x band across an 8x range of `U` while C4's span 12x over the same builds -- a
        reading that does not move with the part is not reading the part."""
        nose = [r for r in prediction.pair(OTHER) if r['kind'] == 'nose_cowl_shell']
        assert len(nose) >= 6
        thin = [r['real'] for r in nose]
        assert max(thin) / min(thin) < 1.5, nose
        assert min(thin) > 2.0 * prediction.WALL_TOL, nose

    def test_the_tail_fails_the_tolerance_at_every_u_and_the_nose_only_at_u4(self):
        """**Supersedes `test_no_fully_measured_wall_meets_the_acceptance_tolerance`, which
        asserted that no wall meets `WALL_TOL`.** That held while the nose was judged on a
        bounding-box station grid that found 5 to 9 of its 12 stations (§6.7); on the real extent
        five of the twelve distinct walls meet the tolerance. The finding is now a shape rather
        than a count, and it is the shape that matters to the mechanism: every `tail_shell` fails
        at every `U`, and the only nose failure is the largest one."""
        rows = prediction.pair(M)
        tail = [r for r in rows if r['kind'] == 'tail_shell']
        nose = [r for r in rows if r['kind'] == 'nose_cowl_shell']
        assert len(tail) >= 6 and len(nose) >= 6
        assert all(r['real'] > prediction.WALL_TOL for r in tail), tail
        over = [r['u'] for r in nose if r['real'] > prediction.WALL_TOL]
        assert over == [4.0], nose

    def test_the_tail_thinning_does_not_grow_with_u(self):
        """**The withdrawn finding, kept as a regression against its own return.** The published
        figures showed 0.0282, 0.1514 and 0.2136 mm at `U` = 1, 3 and 4 and were read as a defect
        worsening with scale. Properly sampled the whole tail range lies in one band, so a future
        run reproducing a strong `U` trend is reporting its own sampling, not the part.

        Scoped to the tail, which is what the withdrawn finding was about. Asserting it across both
        kinds passed only while the nose's own readings were being lost to the bounding-box grid;
        the nose does have a trend, and the test below is where that lives."""
        rows = [r for r in prediction.pair(M) if r['kind'] == 'tail_shell']
        thin = [r['real'] for r in rows]
        assert max(thin) / min(thin) < 5.0, rows
        assert max(thin) < 0.06, rows
        assert max(rows, key=lambda r: r['real'])['u'] < 4.0, 'worst is not the largest wall'

    def test_the_nose_thinning_does_grow_with_u_and_the_tail_does_not(self):
        """**A finding, not a guard, and it was invisible until the station grid was fixed.** The
        nose's thinning is strictly monotonic in `U` -- 0.00115, 0.00310, 0.00376, 0.00504,
        0.00829, 0.01403 mm over `U` = 0.5 to 4.0, a factor of 12 across a factor of 8 -- while the
        tail's is not monotonic at all and peaks at `U` = 3.0. Whatever the residual mechanism is
        (IP-WTM-26), it scales with the part on the cell that has no diagonal buttresses and does
        not on the cell that has four, and the tail is ten times the nose at `U` = 0.5."""
        rows = prediction.pair(M)
        nose = sorted((r for r in rows if r['kind'] == 'nose_cowl_shell'), key=lambda r: r['u'])
        tail = sorted((r for r in rows if r['kind'] == 'tail_shell'), key=lambda r: r['u'])
        thin = [r['real'] for r in nose]
        assert thin == sorted(thin), 'the nose is no longer monotonic in U: %s' % nose
        assert thin[-1] / thin[0] > 8.0, nose
        tail_thin = [r['real'] for r in tail]
        assert tail_thin != sorted(tail_thin), 'the tail is now monotonic in U: %s' % tail
        assert tail_thin[0] > 8.0 * thin[0], 'the tail no longer dwarfs the nose at U = 0.5'

    def test_the_table_renders_every_paired_build(self):
        text = prediction.table(M)
        assert 'pass2 pred' in text and 'shortfall' in text
        assert len(text.splitlines()) == 2 + prediction.verdict(M)['builds_paired']

    def test_the_selected_measure_never_reports_more_thinness_than_the_incumbent(self):
        """C4 takes its minimum over a subset of C0's samples, so this is structural. It failed on
        the first spacing-based sweep -- C4 0.04806 against C0 0.04689 at `tail_shell` `U` = 3.0 --
        because `corner_excluded_min` resampled the inner loop before subsetting and so measured a
        different point set. Fixed; asserted here against the recorded corpus as well as against the
        measure itself in `test_wall_measure_sweep.py`."""
        rows = prediction.read_sweep()
        bad = [(k, r['worst_thin'][OTHER], r['worst_thin'][M]) for k, r in rows.items()
               if r['worst_thin'][M] > r['worst_thin'][OTHER] + 1e-12]
        assert not bad, bad

    def test_the_corner_exclusion_matters_on_the_nose_and_not_on_the_tail(self):
        """**Where the corner artefact actually lives, and it is one kind and not the other.** On a
        `nose_cowl_shell` wall the incumbent reads about 0.03 mm thin where the corner-excluded
        measure reads 0.001 to 0.012 mm, so its reading there is dominated by nearest-point
        distances cutting across concave corners. On the tail the two agree closely -- at some
        stations exactly, which given the subset relationship means the worst sample survives the
        exclusion. So the tail's thinning is not at a corner and no corner-based fix reaches it."""
        rows = prediction.read_sweep()

        def gaps(kind):
            return [r['worst_thin'][OTHER] - r['worst_thin'][M]
                    for k, r in rows.items() if k[0] == kind]

        nose, tail = gaps('nose_cowl_shell'), gaps('tail_shell')
        assert nose and tail
        assert min(nose) > 0.01, nose
        assert min(tail) < 0.005, tail
        assert max(nose) > max(tail), (max(nose), max(tail))

    def test_the_hard_cases_are_the_ones_pass_2_worked_hardest_on(self):
        """Pass 2's round count is a signal that gates nothing, and it survives the correction: the
        build that needed 5 of its 6 allowed rounds is still the one with the largest shortfall."""
        rows = prediction.pair(M)
        worst = max(rows, key=lambda r: r['shortfall'])
        assert worst['rounds'] >= 1
        assert max(r['rounds'] for r in rows if r['u'] >= 3.0) == 5


# -------------------------------------------------------------------- the reproducible report


@requires_log
@requires_sweep
class TestTheReport:
    """`report` exists so every figure published in cowl_interior_surface.md 6.4 and 6.5 has a
    command behind it. These tests check the cheap half, which needs no vendor module."""

    def test_the_prediction_report_runs_and_names_both_measures(self):
        import io

        from wall_measure import report
        buf = io.StringIO()
        text = report.prediction_report(out=buf)
        assert buf.getvalue() == text + '\n'
        assert M in text and OTHER in text
        assert 'worst pass 2 prediction' in text

    def test_the_report_quotes_the_figures_the_design_document_publishes(self):
        import io

        from wall_measure import report
        text = report.prediction_report(out=io.StringIO())
        for figure in ('0.0484', '0.0430', '0.0393', '0.0481'):
            assert figure in text, figure

    def test_main_needs_no_vendor_module_and_succeeds(self):
        import io

        from wall_measure import report
        out, err = io.StringIO(), io.StringIO()
        saved = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            status = report.main([])
        finally:
            sys.stdout, sys.stderr = saved
        assert status == 0, err.getvalue()
        assert 'builds in the log' in out.getvalue()
