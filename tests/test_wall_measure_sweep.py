"""IP-WTM-11: the corpus sweep — its bookkeeping without a vendor, and one real wall with one.

The sweep's arithmetic is where a wrong answer would be least visible: a sign error on
`worst_thin`, or a verdict that counted the wrong instrument's column, would produce a plausible
table and a false conclusion about whether the cowl wall is compliant. So the summary logic is
tested on constructed rows where the right answer is obvious, and the measurement path is tested
on one real wall.

See doc/implementation/wall_thickness_measure.md.
"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import candidates, corpus, sweep                         # noqa: E402

from conftest import requires_freecad                                      # noqa: E402

requires_corpus = pytest.mark.skipif(not corpus.available(),
                                     reason='no saved soak walls to sweep')

TOL = 0.01


NEW, OLD = 'C4_corner_excluded_min', 'C0_nearest_point_min'


def _row(label, worst, incumbent, kind='tail_shell', u=1.0, repeat=0, coverage=12,
         stations=12, soak=None):
    """One sweep row in the shape `sweep.sweep` produces: a figure per measure, on one grid."""
    return {'kind': kind, 'u': u, 'repeat': repeat, 'label': label,
            'worst_thin': {NEW: worst, OLD: incumbent},
            'stations_measured': {NEW: coverage, OLD: coverage},
            'median_of_medians': {NEW: 0.6, OLD: 0.6},
            'stations': stations, 'soak_recorded_worst': soak, 'elapsed_s': 1.0}


class TestThePackageIsPortableToTheWorker:
    """IP-WTM-10 adopts the selected measure inside `check_cowl_interior`, which runs under
    FreeCAD's embedded Python 3.11 with numpy 1.26 -- not the project's 3.13.

    **So the measure has to depend on nothing but numpy and the standard library.** Verified by
    probe under `freecadcmd` (3.11.14, numpy 1.26.4: imports and reads 0.599977 on a 0.6 mm
    annulus), and asserted here as the property that keeps it true: a later import of scipy or
    shapely would break the production path while every test in this repo still passed.
    """

    def test_no_module_imports_anything_beyond_numpy_and_the_stdlib(self):
        import ast
        import pathlib
        allowed = {'numpy', 'json', 'os', 're', 'sys', 'time', 'math', 'collections',
                   'itertools', 'functools'}
        pkg = pathlib.Path(sweep.__file__).parent
        offenders = []
        for path in sorted(pkg.glob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        root = a.name.split('.')[0]
                        if root not in allowed:
                            offenders.append('%s: import %s' % (path.name, a.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:                      # relative, within the package
                        continue
                    root = (node.module or '').split('.')[0]
                    if root not in allowed:
                        offenders.append('%s: from %s import ...' % (path.name, node.module))
        assert not offenders, 'not importable under the worker: %s' % '; '.join(offenders)

    def test_no_module_imports_a_vendor_at_module_scope(self):
        """`Part` and `App` arrive as arguments, so this package is importable from either
        interpreter -- the same rule the geometry bridge holds itself to."""
        import pathlib
        pkg = pathlib.Path(sweep.__file__).parent
        for path in sorted(pkg.glob('*.py')):
            text = path.read_text(encoding='utf-8')
            for bad in ('\nimport FreeCAD', '\nimport Part', '\nimport MeshPart'):
                assert bad not in text, '%s imports a vendor at module scope' % path.name


class TestTheVerdictArithmetic:

    def test_it_counts_each_measure_on_its_own(self):
        rows = [_row('a', 0.002, 0.050), _row('b', 0.004, 0.030), _row('c', 0.020, 0.025)]
        assert sweep.verdict(rows, TOL, NEW)['meets_tolerance'] == 2
        assert sweep.verdict(rows, TOL, OLD)['meets_tolerance'] == 0

    def test_a_wall_with_incomplete_coverage_is_excluded_not_passed(self):
        """**The leniency that would manufacture compliance.** A wall where five of twelve stations
        produced a section has not been shown to meet anything: the seven unmeasured stations could
        be the thin ones, and `check_cowl_interior` counts a station with no section as a failure
        rather than a skip. Found because a real sweep lost 3 to 7 stations on every nose wall and
        would otherwise have reported eight walls as compliant."""
        rows = [_row('partial', 0.000, 0.000, coverage=5, stations=12),
                _row('complete', 0.000, 0.000, coverage=12, stations=12)]
        v = sweep.verdict(rows, TOL, NEW)
        assert v['walls'] == 2
        assert v['walls_with_full_coverage'] == 1
        assert v['walls_excluded_for_coverage'] == 1
        assert v['meets_tolerance'] == 1, 'only the fully covered wall may count as meeting it'

    def test_incomplete_coverage_can_be_included_deliberately(self):
        rows = [_row('partial', 0.000, 0.000, coverage=5, stations=12)]
        v = sweep.verdict(rows, TOL, NEW, full_coverage_only=False)
        assert v['meets_tolerance'] == 1 and v['walls_excluded_for_coverage'] == 0

    def test_the_three_outcomes_are_disjoint_and_account_for_every_wall(self):
        """**IP-WTM-19.** A wall is one of: measured and compliant, measured and thin, or not fully
        measured -- and the gate counts the third a failure, not a set-aside. An earlier version
        reported only `meets_tolerance` beside a coverage exclusion count, which leaves the excluded
        walls in a limbo reading as neither pass nor fail and invites quoting the pass count as
        though it covered the corpus."""
        rows = [_row('ok', 0.002, 0.002, coverage=12, stations=12),
                _row('thin', 0.150, 0.150, coverage=12, stations=12),
                _row('partial', 0.000, 0.000, coverage=5, stations=12)]
        v = sweep.verdict(rows, TOL, NEW)
        assert (v['meets_tolerance'], v['fails_tolerance'], v['fails_coverage']) == (1, 1, 1)
        assert v['meets_tolerance'] + v['fails_tolerance'] + v['fails_coverage'] == v['walls']
        assert v['fails_total'] == 2

    def test_a_sectionless_station_fails_rather_than_abstains(self):
        """The acceptance gate's own convention: `check_cowl_interior` does `bad += 1` at a station
        with no section. A sweep that abstains instead cannot say whether the part passes the gate,
        which is the only question it exists to answer."""
        v = sweep.verdict([_row('absent', 0.000, 0.000, coverage=0, stations=12)], TOL, NEW)
        assert v['meets_tolerance'] == 0
        assert v['fails_coverage'] == 1 and v['fails_total'] == 1

    def test_it_reports_the_worst_wall(self):
        rows = [_row('mild', 0.002, 0.01), _row('bad', 0.150, 0.20)]
        v = sweep.verdict(rows, TOL, NEW)
        assert v['worst_label'] == 'bad' and v['worst_thin'] == pytest.approx(0.150)

    def test_exactly_at_the_tolerance_counts_as_meeting_it(self):
        """One-sided and inclusive, matching `check_cowl_interior`'s own `lowv < t - WALL_TOL`."""
        assert sweep.verdict([_row('edge', TOL, TOL)], TOL, NEW)['meets_tolerance'] == 1

    def test_an_empty_sweep_does_not_raise(self):
        v = sweep.verdict([], TOL, NEW)
        assert v['walls'] == 0 and v['worst_label'] is None

    def test_disagreements_compare_two_measures_on_the_same_stations(self):
        """The comparison the soak's recorded column cannot support, since it was taken on a
        different station grid."""
        rows = [_row('flipped_to_pass', 0.002, 0.050),
                _row('agree_thin', 0.020, 0.030),
                _row('flipped_to_thin', 0.020, 0.005)]
        got = sweep.disagreements(rows, OLD, NEW, TOL)
        assert sorted(d['label'] for d in got) == ['flipped_to_pass', 'flipped_to_thin']

    def test_the_soak_column_is_carried_but_never_differenced(self):
        """It is an answer about different places, so the sweep must not subtract it."""
        r = _row('a', 0.002, 0.004, soak=0.0384)
        assert r['soak_recorded_worst'] == pytest.approx(0.0384)
        assert 'delta_vs_incumbent' not in r

    def test_the_table_shows_coverage_beside_every_figure(self):
        """A 0.0000 on five of twelve stations and a 0.0000 on twelve are different claims."""
        rows = [_row('ok', 0.002, 0.050, coverage=12), _row('partial', 0.000, 0.000, coverage=5)]
        text = sweep.table(rows, TOL, names=[OLD, NEW])
        assert 'meets' in text and 'THIN' in text
        assert '5/5 of 12' in text and '12/12 of 12' in text

    def test_a_sweep_round_trips_through_jsonl(self, tmp_path):
        """Persisted so a later run is compared against it rather than re-argued."""
        rows = [_row('a', 0.002, 0.05), _row('b', 0.02, 0.03)]
        p = sweep.write_jsonl(rows, str(tmp_path / 's.jsonl'))
        back = [json.loads(ln) for ln in open(p, encoding='utf-8')]
        assert [r['label'] for r in back] == ['a', 'b']
        assert back[0]['worst_thin'][NEW] == pytest.approx(0.002)


#: Where a corpus sweep is persisted, if one has been run.
#:
#: **The spacing-based file, not the first one.** `sweep_selected.jsonl` was taken at a fixed 1 440
#: samples a loop and its large-`U` rows are wrong by up to a factor of six -- see
#: `measure_wall`'s own note. It is kept on disk as `sweep_selected.superseded-2026-10-10.jsonl`
#: for provenance and is deliberately not what these tests read.
SWEEP_RESULTS = os.path.join(corpus.SOAK_DIR, 'sweep_spacing.jsonl')


def _persisted_sweep():
    if not os.path.isfile(SWEEP_RESULTS):
        return None
    return [json.loads(ln) for ln in open(SWEEP_RESULTS, encoding='utf-8') if ln.strip()]


requires_sweep = pytest.mark.skipif(
    _persisted_sweep() is None,
    reason='no persisted corpus sweep at %s' % SWEEP_RESULTS)


@requires_sweep
class TestThePersistedCorpusSweep:
    """Properties the recorded sweep must have, checked against the file rather than re-argued.

    These exist so that the figures quoted in the design documents have something that fails when
    they stop being true, which is the whole reason the sweep is a library tool and not a script.
    """

    def test_every_repeat_of_a_configuration_reads_identically(self):
        """**Superseded in its original form, and recorded as such rather than deleted.**

        This asserted that repeated builds of one configuration measure identically -- the soak's
        bit-identical `canonical_hash` result, one level up. It cannot be asserted from this file
        any longer, because the corrected sweep measures `corpus.distinct()`: the soak found all 16
        repeat pairs byte-identical, so re-measuring the same bytes five times costs minutes a wall
        and tests nothing about the measure.

        What *is* checkable is the dedup's own premise -- that the repeats really do share a hash.
        If a future soak finds repeats differing, `corpus.distinct` keeps both, the rows come back,
        and the original assertion applies again; it is kept below and simply has nothing to compare
        while the corpus is deduplicated.
        """
        groups = {}
        for rec in corpus.available():
            groups.setdefault((rec.kind, rec.u), []).append(rec)
        repeated = {k: v for k, v in groups.items() if len(v) > 1}
        assert repeated, 'the saved corpus should contain repeated configurations'
        for key, members in sorted(repeated.items()):
            hashes = set((m.recorded or {}).get('wall_hash') for m in members)
            assert len(hashes) == 1,                 '%s: repeats differ by hash, so they must not be deduplicated' % (key,)

        measured = {}
        for r in _persisted_sweep():
            measured.setdefault((r['kind'], r['u']), []).append(r)
        for key, members in sorted(measured.items()):
            if len(members) < 2:
                continue
            values = set(round(m['worst_thin'][NEW], 9) for m in members)
            assert len(values) == 1, '%s disagrees across %d repeats: %s' % (
                key, len(members), sorted(values))

    def test_the_sweep_covers_every_distinct_wall_shape(self):
        """The dedup must not quietly lose a configuration: one row per distinct shape."""
        rows = _persisted_sweep()
        distinct = corpus.distinct()
        if not distinct:
            pytest.skip('no corpus')
        assert len(rows) == len(distinct)
        assert set((r['kind'], r['u']) for r in rows) ==             set((d.kind, float(d.u)) for d in distinct)

    def test_every_wall_was_measured_at_most_of_its_stations(self):
        rows = _persisted_sweep()
        for r in rows:
            got = r['stations_measured'][NEW]
            assert got >= 5, '%s measured only %d stations' % (r['label'], got)

    def test_the_medians_are_near_nominal_on_every_wall(self):
        """A floor under the whole corpus: whatever the minima do, a 0.6 mm wall's median thickness
        must read about 0.6 everywhere, or the sections being measured are not the wall."""
        rows = _persisted_sweep()
        for r in rows:
            assert r['median_of_medians'][NEW] == pytest.approx(0.6, abs=0.02), r['label']

    def test_the_selected_measure_can_never_report_more_thinness(self):
        """**A structural invariant, and it has now caught a defect in the measure itself.**

        C4 is C0 with the corner-adjacent samples discarded, so it takes its minimum over a subset
        of the same distances: that minimum can only be larger, and the thinness it reports only
        smaller or equal. On identical stations the two cannot disagree in the other direction.

        Two earlier claims about this failed. The first asserted they *did* disagree both ways, which
        the first corpus sweep appeared to show; that came entirely from differencing against the
        soak's recorded figures, taken on the body-based station grid, which is a comparison between
        answers about different places. The second — this test's own earlier form — asserted the
        invariant correctly but it was **not actually true of the code**, because
        `corner_excluded_min` resampled the inner loop to uniform arc spacing before subsetting, so
        it measured a different point set rather than a subset. That stayed hidden until the
        corrected corpus sweep, where `tail_shell` at `U` = 3.0 reported C4 at 0.04806 mm against C0
        at 0.04689 mm. The measure now takes its samples as given and applies the margin along true
        arc length, so the invariant holds exactly rather than by luck.
        """
        rows = _persisted_sweep()
        offenders = [(r['label'], r['worst_thin'][NEW] - r['worst_thin'][OLD])
                     for r in rows if r['worst_thin'][NEW] > r['worst_thin'][OLD] + 1e-12]
        assert not offenders, 'C4 reported more thinness than C0 on %s' % offenders
        # And it must sometimes be strictly better, or the corner exclusion does nothing at all.
        assert any(r['worst_thin'][NEW] < r['worst_thin'][OLD] - 0.005 for r in rows)

    def test_the_selected_measure_takes_its_samples_as_given(self):
        """The property the invariant above rests on, asserted directly on the measure rather than
        inferred from a sweep: every point C4 reports must be one of the points C0 reports."""
        a = np.radians(np.linspace(0.0, 360.0, 1200, endpoint=False))
        outer = np.stack([20 * np.cos(a), 20 * np.sin(a), np.zeros_like(a)], axis=1)
        r = np.where(np.abs(np.angle(np.exp(1j * (a - np.radians(45))))) < np.radians(4),
                     16.0, 19.4)
        inner = np.stack([r * np.cos(a), r * np.sin(a), np.zeros_like(a)], axis=1)
        p0, d0 = candidates.nearest_point_min(outer, inner)
        p4, d4 = candidates.corner_excluded_min(outer, inner)
        assert 0 < p4.shape[0] < p0.shape[0], 'the exclusion must drop some samples and not all'
        given = set(map(tuple, np.round(p0[:, :2], 12)))
        assert all(tuple(q) in given for q in np.round(p4[:, :2], 12))
        assert float(d4.min()) >= float(d0.min()) - 1e-15

    def test_five_of_the_twelve_distinct_walls_meet_the_tolerance(self):
        """**The corpus answer to the question this plan exists for, and it changed once.**

        Asserted rather than quoted, so a construction change that moves a wall across the
        tolerance fails this test and sends someone to re-read the conclusion instead of
        inheriting it. **That is what happened on 2026-10-11**: an earlier version asserted that
        *no* fully covered wall meets `WALL_TOL`, which held only while `corpus.station_grid`
        placed the nose's stations across its bounding box and so found 5 to 9 of 12 (§6.7). On
        `measurable_station_grid`'s real extent, five of the twelve distinct walls are inside the
        tolerance under the selected measure -- every one of them a nose.

        The incumbent still reports none of them compliant, and that is not a second opinion: C0
        reads a corner rather than the wall on every nose build (§6.4), which is why it is kept
        only for comparison.
        """
        rows = _persisted_sweep()
        selected = sweep.verdict(rows, TOL, NEW)
        assert selected['walls_with_full_coverage'] == 12, selected
        assert selected['meets_tolerance'] == 5, (
            '%s now reports %d of %d fully covered walls inside %.3f mm -- the plan\'s '
            'conclusion needs revisiting'
            % (NEW, selected['meets_tolerance'], selected['walls_with_full_coverage'], TOL))
        incumbent = sweep.verdict(rows, TOL, OLD)
        assert incumbent['walls_with_full_coverage'] > 0, 'nothing was fully covered'
        assert incumbent['meets_tolerance'] == 0, incumbent


@requires_freecad
@requires_corpus
class TestMeasuringOneRealWall:

    @pytest.fixture
    def wall(self, fc, Part):
        rec = corpus.one()
        return rec, corpus.load(Part, rec)

    def test_the_selected_measure_reads_every_station_it_can(self, wall, App):
        rec, shape = wall
        readings, worst = sweep.measure_wall(candidates.corner_excluded_min, shape, App, 0.6,
                                             level=720)
        assert len(readings) == corpus.STATIONS
        got = [r for r in readings if r.worst is not None]
        # **Not 12.** On this wall-based station grid the nose loses 3 to 7 of 12 stations, because
        # the grid is not the body-based one the acceptance check uses -- see
        # `corpus.station_grid`. The floor here is what the corpus actually delivers.
        assert len(got) >= 5, 'only %d of %d stations produced a section' % (len(got),
                                                                            len(readings))
        assert worst >= 0.0

    def test_worst_thin_is_one_sided(self, wall, App):
        """A wall reading *thicker* than nominal is not a defect -- over a rib it legitimately
        does -- so the reported figure must never go negative."""
        _rec, shape = wall
        _readings, worst = sweep.measure_wall(candidates.corner_excluded_min, shape, App, 0.6,
                                              level=720)
        assert worst >= 0.0

    def test_the_medians_sit_near_nominal(self, wall, App):
        """A sanity floor on the whole pipeline: whatever the minimum does, a 0.6 mm wall's median
        thickness has to read about 0.6, or the sections being measured are not the wall."""
        import numpy as np
        _rec, shape = wall
        readings, _worst = sweep.measure_wall(candidates.corner_excluded_min, shape, App, 0.6,
                                              level=720)
        meds = [r.median for r in readings if r.median is not None]
        assert np.median(meds) == pytest.approx(0.6, abs=0.01)
