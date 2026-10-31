"""The station-gap screen's records read as a population, and the three ways that misleads.

`station_gaps.py` prints a table a person reads one case at a time. The pair screen writes 243 of
them, and every question worth asking of that run is about the population: did any pair seed a gap
tighter than the baseline's, did the floor remove every one of them, and is a tight gap in a pair
case something neither of its rows does alone.

Each test here is a trap rather than a demonstration, because all three of those questions have an
answer that looks right and is wrong:

* the floor moves with `t`, so two of the screened rows change the number a case must be judged
  against;
* a record holds several patches, so the tightest gap in a configuration is not the first one
  printed;
* a pair's tight gap is inherited unless both of its members are known to be clean, and an absent
  member reads exactly like a clean one if nobody checks.

See doc/design/cowl_interior_surface.md section 4.4 and `cowl.md` OQ-DES-CW26.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import station_sets                                       # noqa: E402

#: The screen's own measured figures, so the fixtures are not arbitrary: the `tail_shell` baseline
#: at `U` = 3 seeded a 0.0003433 mm pair and the floor is 0.600 mm at the current wall.
BASE_TIGHT = 0.0003433
FLOOR = 0.6


def _patch(index=0, union_mm=BASE_TIGHT, kept_mm=1.9983671, under=7, union=32, kept=27):
    return {'patch': index, 'z_lo': -300.0 + index, 'z_hi': -100.0 + index,
            'seed': union - 4, 'notch_edges': 4, 'union': union, 'kept': kept,
            'tightest_union_mm': union_mm, 'under_floor': under,
            'tightest_kept_mm': kept_mm}


def _record(kind='tail_shell', u=3.0, case=None, floor=FLOOR, t=0.6,
            patches=None, moves=None):
    return {'kind': kind, 'u': u, 'case': case, 'moves': moves,
            't_mm': t, 'station_floor_mm': floor,
            'z_lo': -300.0, 'z_hi': -8.0,
            'notch_edges': [-283.9951339, -60.0], 'body_creases': [-150.0],
            'patches': [_patch()] if patches is None else patches}


def _write(directory, name, row):
    path = os.path.join(str(directory), name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(row))
    return path


class TestDiscovery:

    def test_an_absent_directory_is_empty_not_an_error(self, tmp_path):
        """A test that needs the screen's output should skip, not fail, when it has not run."""
        assert station_sets.available(records_dir=str(tmp_path / 'nope')) == []

    def test_the_configuration_is_read_from_the_record_and_not_the_file_name(self, tmp_path):
        """`nose_cowl_shell` contains the same separator a case name does, so names are not parsed.

        The file is deliberately named nothing like its contents. Parsing the name would be a trap
        with no upside, since `station_gaps.run` writes the configuration into the record.
        """
        _write(tmp_path, 'whatever.json',
               _record(kind='nose_cowl_shell', u=1.0, case='top1_angle_hi'))
        got = station_sets.available(records_dir=str(tmp_path))
        assert len(got) == 1
        assert got[0].kind == 'nose_cowl_shell' and got[0].u == 1.0
        assert got[0].case == 'top1_angle_hi'

    def test_another_tool_s_json_in_the_same_directory_is_skipped_not_guessed_at(self, tmp_path):
        _write(tmp_path, 'something_else.json', {'hello': 'world'})
        _write(tmp_path, 'tail_shell_U3.json', _record())
        got = station_sets.available(records_dir=str(tmp_path))
        assert [r.label for r in got] == ['tail_shell_U3']

    def test_a_truncated_record_is_skipped_rather_than_killing_the_read(self, tmp_path):
        """A run interrupted mid-write must not make the other 242 unreadable."""
        path = os.path.join(str(tmp_path), 'tail_shell_U3_half.json')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('{"kind": "tail_shell", "patch')
        _write(tmp_path, 'tail_shell_U3.json', _record())
        assert [r.label for r in station_sets.available(records_dir=str(tmp_path))] \
            == ['tail_shell_U3']

    def test_the_u_filter_compares_as_a_number(self, tmp_path):
        """`3` has to find a record written as `3.0`, which it would not as text."""
        _write(tmp_path, 'tail_shell_U3.json', _record(u=3.0))
        assert len(station_sets.available(records_dir=str(tmp_path), u=3)) == 1
        assert station_sets.available(records_dir=str(tmp_path), u=4) == []

    def test_the_baseline_sorts_before_its_cases(self, tmp_path):
        """The control is what every comparison reads first, so it is not buried alphabetically."""
        _write(tmp_path, 'a.json', _record(case='buttress_r_inset_hi'))
        _write(tmp_path, 'b.json', _record(case='aaa_lo'))
        _write(tmp_path, 'c.json', _record())
        got = station_sets.available(records_dir=str(tmp_path))
        assert [r.case for r in got] == [None, 'aaa_lo', 'buttress_r_inset_hi']

    def test_the_label_matches_the_file_stem_the_screen_writes(self, tmp_path):
        """`station_gaps` writes `%s_U%g` and `%s_U%g_%s`; a label that disagrees cannot be traced."""
        _write(tmp_path, 'tail_shell_U3.json', _record())
        _write(tmp_path, 'tail_shell_U3_top1_y_lo.json', _record(case='top1_y_lo'))
        got = station_sets.available(records_dir=str(tmp_path))
        assert [r.label for r in got] == ['tail_shell_U3', 'tail_shell_U3_top1_y_lo']


class TestOneRecord:

    def test_the_tightest_gap_is_the_minimum_over_patches_not_the_first_one(self, tmp_path):
        """`cavity` seeds each patch between body creases independently, and the tail has several.

        Reading `patches[0]` would report the station set of whichever end of the part happened to
        be recorded first.
        """
        rec = station_sets.StationSet('x', _record(patches=[
            _patch(0, union_mm=0.5), _patch(1, union_mm=0.0004578), _patch(2, union_mm=1.2)]))
        assert rec.tightest_union_mm == pytest.approx(0.0004578)

    def test_a_patch_with_no_surviving_gap_is_none_and_not_zero(self, tmp_path):
        """A patch that keeps one station has no gap at all; zero would read as a severe breach."""
        rec = station_sets.StationSet('x', _record(patches=[_patch(0, kept_mm=None)]))
        assert rec.tightest_kept_mm is None
        assert rec.breaches_floor is False

    def test_a_breach_is_judged_against_this_record_s_own_floor(self, tmp_path):
        """**The trap the two wall rows set.** `t` is `cowl_n_perimeters` times `extrusion_width`,
        both screened, so `station_floor(t)` is a different number in those cases. The same
        0.3 mm surviving gap is a breach at the baseline's 0.6 mm floor and perfectly legal at the
        0.2 mm floor a thinner wall gives.
        """
        thin = station_sets.StationSet('x', _record(
            case='extrusion_width_lo', floor=0.2, t=0.2, patches=[_patch(0, kept_mm=0.3)]))
        base = station_sets.StationSet('y', _record(patches=[_patch(0, kept_mm=0.3)]))
        assert thin.breaches_floor is False
        assert base.breaches_floor is True

    def test_a_gap_exactly_on_the_floor_is_not_a_breach(self, tmp_path):
        """`_thin_stations` keeps a gap equal to the floor, so equality is the pass and not the fail."""
        rec = station_sets.StationSet('x', _record(patches=[_patch(0, kept_mm=FLOOR)]))
        assert rec.breaches_floor is False

    def test_the_counts_sum_over_patches(self, tmp_path):
        rec = station_sets.StationSet('x', _record(patches=[
            _patch(0, under=7, union=32, kept=27), _patch(1, under=0, union=10, kept=10)]))
        assert rec.under_floor == 7
        assert rec.stations_union == 42 and rec.stations_kept == 37

    def test_a_pair_case_splits_into_its_two_members(self, tmp_path):
        rec = station_sets.StationSet('x', _record(
            case='buttress_cut_thickness_lo__top_diag_z_start_hi'))
        assert rec.members == ('buttress_cut_thickness_lo', 'top_diag_z_start_hi')

    def test_a_single_row_case_and_the_baseline_have_no_members(self, tmp_path):
        """A one-row case name never carries the separator, so this is exact and not a heuristic."""
        assert station_sets.StationSet('x', _record(case='top1_angle_hi')).members is None
        assert station_sets.StationSet('y', _record()).members is None

    def test_the_moves_come_back_as_a_list_of_pairs(self, tmp_path):
        rec = station_sets.StationSet('x', _record(
            case='a_lo__b_hi', moves=[['buttress_cut_thickness', -0.03], ['top1_y', 0.02]]))
        assert rec.moves == [['buttress_cut_thickness', -0.03], ['top1_y', 0.02]]
        assert station_sets.StationSet('y', _record()).moves == []


class TestThePopulation:

    def _dir(self, tmp_path, rows):
        for name, row in rows:
            _write(tmp_path, name, row)
        return station_sets.available(records_dir=str(tmp_path))

    def test_the_baseline_is_found_among_the_cases(self, tmp_path):
        got = self._dir(tmp_path, [('a.json', _record(case='x_lo')),
                                   ('b.json', _record())])
        assert station_sets.baseline(got).is_baseline

    def test_tighter_than_baseline_is_sorted_tightest_first(self, tmp_path):
        got = self._dir(tmp_path, [
            ('base.json', _record()),
            ('a.json', _record(case='a_lo', patches=[_patch(0, union_mm=0.0001)])),
            ('b.json', _record(case='b_lo', patches=[_patch(0, union_mm=0.00002)])),
            ('c.json', _record(case='c_lo', patches=[_patch(0, union_mm=0.5)]))])
        names = [r.case for r in station_sets.tighter_than_baseline(got)]
        assert names == ['b_lo', 'a_lo']

    def test_a_case_equal_to_the_baseline_is_not_tighter_than_it(self, tmp_path):
        """Every case carries the baseline's own notch edges, so most will tie. A tie is not news."""
        got = self._dir(tmp_path, [('base.json', _record()),
                                   ('a.json', _record(case='a_lo'))])
        assert station_sets.tighter_than_baseline(got) == []

    def test_without_a_baseline_the_comparison_returns_nothing(self, tmp_path):
        """An empty list from a missing control, not a list compared against the first case."""
        got = self._dir(tmp_path, [('a.json', _record(case='a_lo'))])
        assert station_sets.tighter_than_baseline(got) == []

    def test_floor_breaches_is_empty_on_a_sound_population(self, tmp_path):
        got = self._dir(tmp_path, [('base.json', _record()),
                                   ('a.json', _record(case='a_lo'))])
        assert station_sets.floor_breaches(got) == []

    def test_one_breach_is_found_among_many_sound_cases(self, tmp_path):
        got = self._dir(tmp_path, [
            ('base.json', _record()),
            ('a.json', _record(case='a_lo')),
            ('bad.json', _record(case='b_lo', patches=[_patch(0, kept_mm=0.0004578)]))])
        assert [r.case for r in station_sets.floor_breaches(got)] == ['b_lo']


class TestWhereTheTightestGapIs:

    def test_the_pair_is_recomputed_from_the_stations_and_not_read_off_the_figure(self):
        """The gap figure cannot say *where*, and where is what distinguishes the two answers.

        The record's `tightest_union_mm` is deliberately set to a wrong value here: the pair must
        come from `union_stations`, which is the evidence, not from the summary field.
        """
        patch = _patch(0, union_mm=99.0)
        patch['union_stations'] = [-300.0, -283.9951339, -283.9947906, -100.0]
        rec = station_sets.StationSet('x', _record(patches=[patch]))
        gap, z_lo, z_hi = station_sets.tightest_pair(rec)
        assert gap == pytest.approx(0.0003433)
        assert (z_lo, z_hi) == pytest.approx((-283.9951339, -283.9947906))

    def test_it_takes_the_tightest_over_patches_not_the_first_patch_s(self):
        loose, tight = _patch(0), _patch(1)
        loose['union_stations'] = [-300.0, -299.0]
        tight['union_stations'] = [-100.0, -99.9999, -50.0]
        rec = station_sets.StationSet('x', _record(patches=[loose, tight]))
        assert station_sets.tightest_pair(rec)[0] == pytest.approx(0.0001)

    def test_a_patch_with_one_station_has_no_pair_and_does_not_raise(self):
        patch = _patch(0)
        patch['union_stations'] = [-100.0]
        rec = station_sets.StationSet('x', _record(patches=[patch]))
        assert station_sets.tightest_pair(rec) is None

    def test_one_census_entry_means_no_screened_row_moved_the_gap(self):
        """The structural answer: every configuration's tightest gap is the same two stations."""
        recs = []
        for case in (None, 'a_lo', 'b_hi__c_lo'):
            patch = _patch(0)
            patch['union_stations'] = [-300.0, -283.9951339, -283.9947906]
            recs.append(station_sets.StationSet('x', _record(case=case, patches=[patch])))
        census = station_sets.pair_census(recs)
        assert len(census) == 1
        key, holders = census[0]
        assert key == pytest.approx((-283.9951339, -283.9947906))
        assert len(holders) == 3

    def test_a_row_that_moves_the_gap_shows_as_a_second_entry_most_common_first(self):
        recs = []
        for case, zs in ((None, [-300.0, -283.9951339, -283.9947906]),
                         ('a_lo', [-300.0, -283.9951339, -283.9947906]),
                         ('b_hi', [-200.0, -150.0, -149.99])):
            patch = _patch(0)
            patch['union_stations'] = zs
            recs.append(station_sets.StationSet('x', _record(case=case, patches=[patch])))
        census = station_sets.pair_census(recs)
        assert [len(holders) for _key, holders in census] == [2, 1]
        assert census[1][0] == pytest.approx((-150.0, -149.99))


class TestInteractions:

    def _dir(self, tmp_path, rows):
        for name, row in rows:
            _write(tmp_path, name, row)
        return station_sets.available(records_dir=str(tmp_path))

    def test_a_pair_tighter_than_both_members_is_an_interaction(self, tmp_path):
        got = self._dir(tmp_path, [
            ('s1.json', _record(case='a_lo', patches=[_patch(0, union_mm=0.01)])),
            ('s2.json', _record(case='b_hi', patches=[_patch(0, union_mm=0.02)])),
            ('p.json', _record(case='a_lo__b_hi', patches=[_patch(0, union_mm=0.0001)]))])
        found = [i for i in station_sets.interactions(got)]
        assert [i.verdict for i in found] == ['interaction']
        assert found[0].gaps_mm == (pytest.approx(0.0001), pytest.approx(0.01),
                                    pytest.approx(0.02))

    def test_a_pair_no_tighter_than_a_member_inherited_it(self, tmp_path):
        """The one that would manufacture 242 findings: every case carries the same notch edges."""
        got = self._dir(tmp_path, [
            ('s1.json', _record(case='a_lo')),
            ('s2.json', _record(case='b_hi')),
            ('p.json', _record(case='a_lo__b_hi'))])
        assert [i.verdict for i in station_sets.interactions(got)] == ['inherited']

    def test_a_pair_tighter_than_one_member_only_inherited_it(self, tmp_path):
        """Tighter than *both* is the test. Beating the looser member is not an interaction."""
        got = self._dir(tmp_path, [
            ('s1.json', _record(case='a_lo', patches=[_patch(0, union_mm=0.0001)])),
            ('s2.json', _record(case='b_hi', patches=[_patch(0, union_mm=0.02)])),
            ('p.json', _record(case='a_lo__b_hi', patches=[_patch(0, union_mm=0.001)]))])
        assert [i.verdict for i in station_sets.interactions(got)] == ['inherited']

    def test_an_absent_member_is_unmeasured_and_names_itself(self, tmp_path):
        """**The trap worth the whole type.** The single-row family is a separate run, and an
        absent member must not read as a clean one -- "neither row does this alone" and "nobody
        looked" are different findings.
        """
        got = self._dir(tmp_path, [
            ('s1.json', _record(case='a_lo')),
            ('p.json', _record(case='a_lo__b_hi', patches=[_patch(0, union_mm=0.0001)]))])
        found = station_sets.interactions(got)
        assert [i.verdict for i in found] == ['unmeasured']
        assert found[0].missing == ['b_hi']

    def test_a_pair_run_on_its_own_reports_every_case_unmeasured(self, tmp_path):
        """Which is what the 243-case pair screen alone gives, and the honest answer for it."""
        got = self._dir(tmp_path, [
            ('base.json', _record()),
            ('p1.json', _record(case='a_lo__b_hi')),
            ('p2.json', _record(case='a_lo__c_lo'))])
        found = station_sets.interactions(got)
        assert len(found) == 2
        assert set(i.verdict for i in found) == {'unmeasured'}

    def test_the_members_can_come_from_a_separate_collection(self, tmp_path):
        """The two families are separate runs, so the singles may be read from their own directory."""
        (tmp_path / 'p').mkdir()
        (tmp_path / 's').mkdir()
        pairs = self._dir(tmp_path / 'p', [
            ('p.json', _record(case='a_lo__b_hi', patches=[_patch(0, union_mm=0.0001)]))])
        singles = self._dir(tmp_path / 's', [
            ('s1.json', _record(case='a_lo')),
            ('s2.json', _record(case='b_hi'))])
        found = station_sets.interactions(pairs, singles=singles)
        assert [i.verdict for i in found] == ['interaction']

    def test_the_baseline_and_single_cases_are_not_judged_as_pairs(self, tmp_path):
        got = self._dir(tmp_path, [('base.json', _record()),
                                   ('s.json', _record(case='a_lo'))])
        assert station_sets.interactions(got) == []


class TestTheReport:

    def test_it_prints_the_numbers_it_argues_about(self, tmp_path):
        """A report that says "no breaches" without the tightest surviving gap cannot be checked."""
        for name, row in [('base.json', _record()),
                          ('a.json', _record(case='a_lo', patches=[_patch(0, union_mm=0.00002)]))]:
            _write(tmp_path, name, row)
        lines = station_sets.report(station_sets.available(records_dir=str(tmp_path)))
        text = '\n'.join(lines)
        assert '0.0003433' in text          # the baseline's own seeded pair
        assert '0.0000200' in text          # the tighter case
        assert '1.9983671' in text          # the tightest surviving gap
        assert 'floor breaches: 0' in text

    def test_it_prints_the_floor_s_workload_and_names_both_extremes(self, tmp_path):
        """Whether the floor held matters less if every case handed it the same few gaps."""
        for name, row in [
                ('base.json', _record()),
                ('a.json', _record(case='extrusion_width_lo', floor=0.2,
                                   patches=[_patch(0, under=4)])),
                ('b.json', _record(case='cowl_n_perimeters_hi', floor=1.2,
                                   patches=[_patch(0, under=11)]))]:
            _write(tmp_path, name, row)
        text = '\n'.join(station_sets.report(
            station_sets.available(records_dir=str(tmp_path))))
        assert 'gaps handed to the floor: 4 to 11 across the population' in text
        assert 'extrusion_width_lo' in text and 'cowl_n_perimeters_hi' in text

    def test_an_empty_population_says_where_it_looked(self, tmp_path):
        lines = station_sets.report([])
        assert len(lines) == 1 and station_sets.RECORDS in lines[0]


#: The screen is build output and is not in version control.
requires_records = pytest.mark.skipif(
    not station_sets.available(),
    reason='no station-set records in %s; run station_gaps.py' % station_sets.RECORDS)


@requires_records
class TestTheRealRecords:

    def test_every_record_on_disk_parses_and_carries_a_floor(self):
        for rec in station_sets.available():
            assert rec.kind in ('tail_shell', 'nose_cowl_shell')
            assert rec.floor_mm > 0.0
            assert rec.patches

    def test_the_floor_removed_every_sub_floor_gap_it_was_given(self):
        """IP-FC-144's own claim, over whatever population has been measured so far."""
        breaches = station_sets.floor_breaches(station_sets.available())
        assert breaches == [], '\n'.join(
            '%s kept %.7f mm under its own %.3f mm floor'
            % (r.label, r.tightest_kept_mm, r.floor_mm) for r in breaches)
