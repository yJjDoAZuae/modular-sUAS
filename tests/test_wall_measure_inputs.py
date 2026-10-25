"""IP-WTM-41: the design-input screen's case arithmetic, and the two corpora kept apart.

IP-WTM-40 scanned all twelve saved walls densely and found no severed ring. Its bound, recorded with
it, is that those twelve **vary `U` alone** -- every other design input at the parameter sheet's
literal -- while the severed ring is a property of the rib cut, whose tools are placed and sized by
rows `U` does not touch. `wall_measure.inputs` is the case list that covers that axis, and this file
is why the case list can be trusted before six hours of builds are spent on it.

Three things here are not decoration:

* **An override that does not land is the whole failure mode.** `override` raising on an unknown
  alias, and `apply_case` changing exactly one cell, are what stop a case running the baseline under
  its own name and being counted as coverage of an input the build never saw.
* **`unmoved` is a vacuity guard** and is tested as one. A screen in which no override reached the
  geometry is an untested screen, not a clean one, and `screen_verdict` must say so.
* **The two corpora must not merge.** `corpus.available` and `corpus.screen` read different
  populations from different directories, and the filename patterns are tested against each other's
  names, because the soak's `_r3` suffix is a valid case name as far as a careless regex is
  concerned.

See doc/implementation/wall_thickness_measure.md.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'Fuselage', 'tools'))

from wall_measure import corpus, inputs                                     # noqa: E402

#: A sheet with one row of every form the real ones use: a plain literal, a `unit_width` fraction
#: expression, a negative one, a derived relationship, and `U` itself. Hand-written rather than
#: imported from `cowl_tree`, which imports FreeCAD at module scope; the real sheet is checked
#: against the real case list by `input_screen.py --check`, which runs under `freecadcmd`.
SHEET = [
    ('U', '1.0'),
    ('unit_width', '=U * 100'),
    ('overhang_angle_from_bed', '35.0'),
    ('buttress_cut_thickness', '0.1'),
    ('buttress_z_offset', '0.02'),
    ('buttress_z_end', '=cut_len + buttress_z_offset'),
    ('top1_y', '=unit_width * 0.07'),
    ('side1_x', '=-unit_width * 0.3'),
    ('top2_y', '0.0'),
    ('extrusion_width', '0.6'),
]


def _rows_to_dict(rows):
    return dict(rows)


# ----------------------------------------------------------------- the cell arithmetic


class TestBump:

    def test_a_literal_moves_by_the_delta_and_stays_a_float_literal(self):
        got = inputs.bump('0.1', -0.03)
        assert not got.startswith('=')
        assert float(got) == pytest.approx(0.07)

    def test_a_negative_delta_can_take_a_literal_through_zero(self):
        """`top2_y` is a literal 0.0 on the sheet, so its low case is genuinely negative."""
        assert float(inputs.bump('0.0', -2.0)) == pytest.approx(-2.0)

    def test_a_unit_width_fraction_keeps_its_expression_form(self):
        """A case must stay portable across `U`: the coefficient moves, the relationship does not.

        A cell rewritten as an absolute millimetre literal would be a different design at every
        `U`, which is the exact thing `cowl_tree.PARAMS_TAIL`'s own comment says the fraction
        convention exists to prevent.
        """
        got = inputs.bump('=unit_width * 0.07', 0.02)
        assert got.startswith('=unit_width * ')
        assert float(got.split('*')[1]) == pytest.approx(0.09)

    def test_the_sign_stays_on_unit_width_where_the_sheet_put_it(self):
        """`side1_x` is `=-unit_width * 0.30`, so a positive delta makes the placement *more*
        negative. Asserted because it is the kind of convention that silently inverts a reading."""
        got = inputs.bump('=-unit_width * 0.3', 0.05)
        assert got.startswith('=-unit_width * ')
        assert float(got.split('*')[1]) == pytest.approx(0.35)

    def test_a_derived_relationship_raises_rather_than_being_rewritten(self):
        """`=cut_len + buttress_z_offset` is a relationship. Bumping it would be editing the
        *rule*, not the value, and the two inputs it derives from have cases of their own."""
        with pytest.raises(ValueError) as exc:
            inputs.bump('=cut_len + buttress_z_offset', 0.01)
        assert 'relationship' in str(exc.value)

    def test_the_u_row_expression_raises_too(self):
        """`=U * 100` is how `U` reaches every other row; `U` is IP-WTM-40's axis, not this one."""
        with pytest.raises(ValueError):
            inputs.bump('=U * 100', 1.0)

    def test_whitespace_around_the_coefficient_is_tolerated(self):
        got = inputs.bump('= unit_width *  0.07 ', 0.01)
        assert float(got.split('*')[1]) == pytest.approx(0.08)


class TestOverride:

    def test_one_cell_changes_and_every_other_is_byte_identical(self):
        """Byte-identical, not merely equal in value. The sweep compares definition files byte for
        byte, so a float that re-formats would re-render parts that did not change."""
        got = inputs.override(SHEET, 'top2_y', '2.0')
        assert len(got) == len(SHEET)
        for (alias, before), (alias2, after) in zip(SHEET, got):
            assert alias == alias2
            assert after == ('2.0' if alias == 'top2_y' else before)

    def test_an_unknown_alias_raises_and_names_itself(self):
        """**The failure this screen cannot afford to swallow.** A silently-ignored override would
        build the baseline, save it under a case's name, and be counted as coverage of an input the
        build never saw."""
        with pytest.raises(ValueError) as exc:
            inputs.override(SHEET, 'top3_angle', '1.0')
        assert 'top3_angle' in str(exc.value)

    def test_value_of_raises_for_an_absent_row_for_the_same_reason(self):
        with pytest.raises(ValueError):
            inputs.value_of(SHEET, 'nope')
        assert inputs.value_of(SHEET, 'extrusion_width') == '0.6'


class TestApplyCase:

    def test_the_baseline_sets_u_and_nothing_else(self):
        case = inputs.Case('tail_shell', 0.5, inputs.BASELINE)
        got = _rows_to_dict(inputs.apply_case(SHEET, case))
        assert float(got['U']) == pytest.approx(0.5)
        for alias, value in SHEET:
            if alias != 'U':
                assert got[alias] == value

    def test_an_excursion_sets_u_and_exactly_one_more_row(self):
        case = inputs.Case('tail_shell', 0.5, 'extrusion_width_hi', 'extrusion_width', 0.2, 'mm')
        got = _rows_to_dict(inputs.apply_case(SHEET, case))
        assert float(got['U']) == pytest.approx(0.5)
        assert float(got['extrusion_width']) == pytest.approx(0.8)
        for alias, value in SHEET:
            if alias not in ('U', 'extrusion_width'):
                assert got[alias] == value

    def test_an_excursion_on_an_absent_row_raises_before_any_build(self):
        case = inputs.Case('tail_shell', 0.5, 'bogus_hi', 'bogus', 1.0, 'mm')
        with pytest.raises(ValueError):
            inputs.apply_case(SHEET, case)

    def test_a_pair_sets_u_and_exactly_two_more_rows(self):
        case = inputs.PairCase('tail_shell', 0.5, 'two', 'extrusion_width', 0.2, 'mm',
                               'buttress_cut_thickness', 0.03, 'mm')
        got = _rows_to_dict(inputs.apply_case(SHEET, case))
        assert float(got['U']) == pytest.approx(0.5)
        assert float(got['extrusion_width']) == pytest.approx(0.8)
        assert float(got['buttress_cut_thickness']) == pytest.approx(0.13)
        for alias, value in SHEET:
            if alias not in ('U', 'extrusion_width', 'buttress_cut_thickness'):
                assert got[alias] == value

    def test_a_pairs_second_row_goes_through_the_same_bump_as_the_first(self):
        """An expression row moved as the *second* member keeps its expression form.

        The second move is the one that could have been written as a plain assignment, which
        would turn `=unit_width * 0.07` into a literal and silently decouple the row from `U`.
        """
        case = inputs.PairCase('tail_shell', 0.5, 'two', 'extrusion_width', 0.2, 'mm',
                               'top1_y', 0.02, 'fraction of unit_width')
        got = _rows_to_dict(inputs.apply_case(SHEET, case))
        assert got['top1_y'].startswith('=unit_width * ')
        assert float(got['top1_y'].split('*')[1]) == pytest.approx(0.09)

    def test_a_pair_on_an_absent_second_row_raises_before_any_build(self):
        case = inputs.PairCase('tail_shell', 0.5, 'two', 'extrusion_width', 0.2, 'mm',
                               'bogus', 1.0, 'mm')
        with pytest.raises(ValueError):
            inputs.apply_case(SHEET, case)


class TestPairCases:
    """OQ-DES-CW26 alternative 1's remaining axis: two inputs moved together."""

    def test_every_unordered_pair_appears_once_at_every_sign_combination(self):
        exc = (inputs.Excursion('extrusion_width', 0.2, 'mm', 'a'),
               inputs.Excursion('buttress_cut_thickness', 0.03, 'mm', 'b'),
               inputs.Excursion('buttress_z_offset', 0.01, 'mm', 'c'))
        got = inputs.pair_cases('tail_shell', 0.5, exc, include_baseline=False)
        assert len(got) == 12                      # 3 pairs x 4 sign combinations
        assert len({c.name for c in got}) == 12
        assert len({tuple(sorted(a for a, _d in c.moves)) for c in got}) == 3

    def test_a_one_sided_row_contributes_half_as_many_and_is_not_skipped(self):
        exc = (inputs.Excursion('extrusion_width', 0.2, 'mm', 'a'),
               inputs.Excursion('cowl_n_perimeters', 1, 'perimeters', 'b', signs=(1.0,)))
        got = inputs.pair_cases('tail_shell', 0.5, exc, include_baseline=False)
        assert len(got) == 2
        assert all(c.second_delta > 0 for c in got)

    def test_no_pair_moves_the_same_row_twice(self):
        for kind in inputs.EXCURSIONS:
            for case in inputs.pair_cases(kind, 1.0, include_baseline=False):
                aliases = [a for a, _d in case.moves]
                assert len(set(aliases)) == len(aliases)

    def test_the_baseline_leads_so_the_control_is_built_first(self):
        got = inputs.pair_cases('nose_cowl_shell', 1.0)
        assert got[0].is_baseline
        assert all(not c.is_baseline for c in got[1:])

    def test_the_crowding_axis_comes_first_as_it_does_for_the_single_row_screen(self):
        got = inputs.pair_cases('nose_cowl_shell', 1.0, include_baseline=False)
        assert got[0].alias == inputs.EXCURSIONS['nose_cowl_shell'][0].alias


# ----------------------------------------------------------------- the case list


class TestCases:

    def test_the_baseline_comes_first_because_it_is_the_control(self):
        got = inputs.cases('tail_shell', 0.5)
        assert got[0].name == inputs.BASELINE
        assert got[0].is_baseline
        assert sum(1 for c in got if c.is_baseline) == 1

    def test_every_excursion_gets_one_case_per_sign_it_declares(self):
        excursions = inputs.EXCURSIONS['nose_cowl_shell']
        got = inputs.cases('nose_cowl_shell', 1.0)
        assert len(got) == 1 + sum(len(e.signs) for e in excursions)
        for e in excursions:
            for sign in e.signs:
                case = inputs.find('nose_cowl_shell', 1.0,
                                   '%s_%s' % (e.alias, 'lo' if sign < 0 else 'hi'))
                assert case is not None, '%s has no case for sign %+g' % (e.alias, sign)
                assert case.delta == pytest.approx(sign * e.delta)
                assert case.alias == e.alias

    def test_a_one_sided_excursion_gets_no_case_in_the_other_direction(self):
        """**`cowl_n_perimeters` = 0 is not a wall.** A screen that generated the low case anyway
        would spend a build refusing an input nobody would ask for, and would then report that
        refusal beside the two that mean something -- `buttress_cut_thickness` and
        `extrusion_width`, where `RIB_FACETS`' floor is the thing being measured."""
        for kind in inputs.EXCURSIONS:
            assert inputs.find(kind, 1.0, 'cowl_n_perimeters_hi') is not None
            assert inputs.find(kind, 1.0, 'cowl_n_perimeters_lo') is None

    def test_a_declared_sign_is_the_signs_tuple_and_not_inferred_from_the_delta(self):
        """A delta is a magnitude. An excursion that stored a negative delta and one sign would
        produce a `_hi` case that moved the row down, which is the sort of thing that reads as a
        result rather than as a bug."""
        one = (inputs.Excursion('top2_y', 1.0, 'mm', 'one-sided', signs=(-1.0,)),)
        got = inputs.cases('tail_shell', 0.5, excursions=one)
        assert [c.name for c in got] == ['base', 'top2_y_lo']
        assert got[1].delta == pytest.approx(-1.0)

    def test_the_order_is_the_excursion_tables_and_puts_the_crowding_axis_first(self):
        """**Not alphabetical, and the ordering is the schedule.** A tail case is about 1 000 s and
        a screen may be interrupted, so the four rows that move every tool at once -- the crowding
        axis IP-FC-137's follow-up reproduced a pathological topology from -- are run before the
        individual placements. An interrupted screen then leaves that axis covered."""
        names = [c.alias for c in inputs.cases('tail_shell', 0.5) if not c.is_baseline]
        assert names[:8] == ['buttress_cut_thickness', 'buttress_cut_thickness',
                             'buttress_r_inset', 'buttress_r_inset',
                             'overhang_angle_from_bed', 'overhang_angle_from_bed',
                             'extrusion_width', 'extrusion_width']
        assert names.index('top_diag_angle') < names.index('top1_angle')

    def test_a_label_carries_the_kind_the_u_and_the_case(self):
        case = inputs.find('tail_shell', 0.5, 'top1_angle_hi')
        assert case.label == 'tail_shell_U0.5_top1_angle_hi'
        assert inputs.find('nose_cowl_shell', 1.0, inputs.BASELINE).label == \
            'nose_cowl_shell_U1.0_base'

    def test_u_is_written_the_way_the_soak_writes_it(self):
        """`1.0` not `1`, `0.5` not `0.50`, so a screen label reads beside a soak one."""
        assert inputs.find('tail_shell', 4, inputs.BASELINE).label.startswith('tail_shell_U4.0_')
        assert inputs.find('tail_shell', 1.5, inputs.BASELINE).label == 'tail_shell_U1.5_base'

    def test_an_unknown_case_name_is_none_not_an_exception(self):
        assert inputs.find('tail_shell', 0.5, 'no_such_case') is None

    def test_every_excursion_carries_a_stated_reason(self):
        """A screen whose magnitudes have no recorded reasoning cannot be argued with later. The
        2026-09-30 screen is the example: 0.5 mm nudges, later found larger than the 0.6 mm wall
        they were perturbing, with nothing on record about why that size."""
        for kind, excursions in inputs.EXCURSIONS.items():
            for e in excursions:
                assert e.why, '%s %s has no reason' % (kind, e.alias)
                assert e.unit in ('mm', 'degrees', 'perimeters',
                                  'fraction of unit_width'), e.unit
                assert e.delta > 0, 'a delta is a magnitude; the sign comes from signs'
                assert e.signs, '%s %s has no direction' % (kind, e.alias)

    def test_no_excursion_names_a_row_twice(self):
        for kind, excursions in inputs.EXCURSIONS.items():
            aliases = [e.alias for e in excursions]
            assert len(aliases) == len(set(aliases)), kind

    def test_an_excursion_list_can_be_passed_in_for_a_narrower_screen(self):
        one = (inputs.Excursion('top2_y', 1.0, 'mm', 'a one-row screen'),)
        got = inputs.cases('tail_shell', 0.5, excursions=one)
        assert [c.name for c in got] == ['base', 'top2_y_lo', 'top2_y_hi']


# ----------------------------------------------------------------- the vacuity guard


def _record(case, solids=1, faces=2416, edges=7000, bbox=(0, 0, -300, 100, 100, 0),
            volume_raw=38987.0, kind='tail_shell', u=0.5, **extra):
    row = {'label': '%s_U%s_%s' % (kind, u, case), 'case': case, 'kind': kind, 'u': u,
           'solids': solids, 'faces': faces, 'edges': edges, 'wall_bbox': list(bbox)}
    if volume_raw is not None:
        row['volume_raw'] = volume_raw
    row.update(extra)
    return row


class TestPopulations:

    def test_records_split_by_kind_and_u_in_a_stable_order(self):
        rows = [_record('base'), _record('base', kind='nose_cowl_shell', u=1.0),
                _record('top2_y_hi'), _record('base', kind='tail_shell', u=3.0)]
        got = inputs.populations(rows)
        assert [k for k, _ in got] == [('tail_shell', 0.5), ('nose_cowl_shell', 1.0),
                                       ('tail_shell', 3.0)]
        assert [len(v) for _, v in got] == [2, 1, 1]

    def test_a_verdict_refuses_records_from_more_than_one_population(self):
        """**One baseline per verdict, and mixing them was caught doing damage.** Over both kinds
        at once there are two records named `base`, so `unmoved` picks whichever came first off
        disk and compares the other kind's cases against it, and every shared case name prints
        twice in the refusal list. The 2026-10-14 run got the right answer anyway only because a
        nose wall and a tail wall never fingerprint alike."""
        rows = [_record('base'), _record('base', kind='nose_cowl_shell', u=1.0)]
        with pytest.raises(ValueError) as exc:
            inputs.screen_verdict(rows, [])
        assert 'populations()' in str(exc.value)
        assert 'nose_cowl_shell' in str(exc.value) and 'tail_shell' in str(exc.value)

    def test_one_population_is_not_refused(self):
        rows = [_record('base'), _record('top2_y_hi', volume_raw=40000.0)]
        assert inputs.screen_verdict(rows, [])['built'] == 2


class TestUnmoved:

    def test_a_case_whose_wall_matches_the_baseline_is_named(self):
        """**The seventh vacuity guard in this subsystem, and the first on a parameter.** If an
        override does not change the built wall, the case scanned the baseline a second time under
        another name; a verdict that counted it would overstate what was tested."""
        got = inputs.unmoved([_record('base'), _record('top2_y_hi'),
                              _record('extrusion_width_hi', faces=2500, volume_raw=40000.0)])
        assert got == ['top2_y_hi']

    def test_a_case_that_moved_any_part_of_the_fingerprint_is_not_named(self):
        base = _record('base')
        assert inputs.unmoved([base, _record('a', solids=2)]) == []
        assert inputs.unmoved([base, _record('b', edges=7001)]) == []
        assert inputs.unmoved([base, _record('c', bbox=(0, 0, -300.1, 100, 100, 0))]) == []

    def test_a_thinner_wall_is_caught_by_volume_and_by_nothing_else(self):
        """**The guard's own correction, measured 2026-10-14.** The nose screen's first report
        named `extrusion_width_lo` `unmoved` although that case takes the wall from 0.6 mm to
        0.4 mm: a thinner wall keeps the same outer surface, so the same faces, the same edges and
        the same bounding box, and the four topological fields cannot see it. `Shape.Volume` can --
        as a difference detector, never as a measure, since IP-FC-119 has it wrong by 0.16-0.24 %
        on these solids."""
        base = _record('base', volume_raw=38987.0)
        thinner = _record('extrusion_width_lo', volume_raw=26000.0)
        assert inputs.unmoved([base, thinner]) == []
        # And with the volume stripped out of both, the old fingerprint would have missed it.
        four_only = (base['solids'], base['faces'], base['edges'], tuple(base['wall_bbox']))
        assert four_only == (thinner['solids'], thinner['faces'], thinner['edges'],
                             tuple(thinner['wall_bbox']))

    def test_the_box_is_compared_at_1e_6_mm_not_exactly(self):
        """Kernel noise at the last bit must not read as a design change."""
        base = _record('base', bbox=(0, 0, -300.0, 100, 100, 0))
        near = _record('d', bbox=(0, 0, -300.0 + 1e-10, 100, 100, 0),
                       volume_raw=38987.0 + 1e-10)
        assert inputs.unmoved([base, near]) == ['d']

    def test_without_a_baseline_there_is_nothing_to_compare_against(self):
        """Returns empty rather than guessing a reference. `screen_verdict` then reports the
        screen as vacuous for having no case that moved, which is the honest reading."""
        assert inputs.unmoved([_record('top2_y_hi')]) == []


class TestUncomparable:

    def test_a_record_without_a_volume_cannot_be_judged_and_says_so(self):
        """**Not quietly compared on the four fields that are there.** That combination is exactly
        the one measured to miss a 0.2 mm change in wall thickness, so falling back to it would
        weaken the vacuity guard without announcing it."""
        records = [_record('base'), _record('old_case', volume_raw=None)]
        assert inputs.uncomparable(records) == ['old_case']
        assert inputs.fingerprint(records[1]) is None

    def test_a_refused_case_is_not_uncomparable_because_there_is_no_wall(self):
        records = [_record('base'),
                   {'label': 'x', 'case': 'refused', 'error': 'PreconditionFailed: ...'}]
        assert inputs.uncomparable(records) == []

    def test_an_uncomparable_case_counts_as_neither_moved_nor_unmoved(self):
        records = [_record('base'), _record('old_case', volume_raw=None),
                   _record('real', volume_raw=40000.0)]
        got = inputs.screen_verdict(records, [{'label': 'tail_shell_U0.5_base', 'stations': 48}])
        assert got['uncomparable'] == ['old_case']
        assert got['moved'] == ['real']
        assert 'old_case' not in got['unmoved']
        assert got['clean'] is False
        assert any('volume_raw' in r for r in got['vacuous_because'])

    def test_the_table_marks_an_uncomparable_case_rather_than_calling_it_unmoved(self):
        text = inputs.screen_table([_record('base'), _record('old_case', volume_raw=None)])
        assert 'uncomparable' in text
        assert 'unmoved' not in text


class TestScreenVerdict:

    def _scan(self, label, stations=48, severed=(), gaps=(), disagree=()):
        return {'label': label, 'stations': stations, 'severed': list(severed),
                'real_gaps': list(gaps), 'kernel_disagreements': list(disagree)}

    def test_clean_needs_a_scan_a_moved_case_and_no_finding(self):
        records = [_record('base'), _record('extrusion_width_hi', volume_raw=40000.0)]
        scans = [self._scan('tail_shell_U0.5_base'),
                 self._scan('tail_shell_U0.5_extrusion_width_hi')]
        got = inputs.screen_verdict(records, scans)
        assert got['clean'] is True
        assert got['vacuous_because'] == []
        assert got['stations'] == 96
        assert got['moved'] == ['extrusion_width_hi']

    def test_a_screen_where_no_override_reached_the_wall_is_not_clean(self):
        """**The case this guard exists for.** Two walls, no severed ring, nothing to report -- and
        no input covered, because the excursion built the baseline. Reporting that as a clean
        screen of the input axis would be reporting a pass from having measured nothing."""
        records = [_record('base'), _record('top2_y_hi')]
        scans = [self._scan('tail_shell_U0.5_base'), self._scan('tail_shell_U0.5_top2_y_hi')]
        got = inputs.screen_verdict(records, scans)
        assert got['clean'] is False
        assert got['unmoved'] == ['top2_y_hi']
        assert any('no input was covered' in r for r in got['vacuous_because'])

    def test_built_walls_with_no_scan_are_not_a_clean_screen_either(self):
        records = [_record('base'), _record('extrusion_width_hi', faces=2500)]
        got = inputs.screen_verdict(records, [])
        assert got['clean'] is False
        assert any('no wall was scanned' in r for r in got['vacuous_because'])

    def test_a_severed_station_is_a_finding(self):
        records = [_record('base'), _record('top_diag_angle_hi', faces=2500)]
        scans = [self._scan('tail_shell_U0.5_base'),
                 self._scan('tail_shell_U0.5_top_diag_angle_hi', severed=[-15.5])]
        got = inputs.screen_verdict(records, scans)
        assert got['clean'] is False
        assert got['severed'] == [('tail_shell_U0.5_top_diag_angle_hi', -15.5)]

    def test_a_kernel_disagreement_is_a_finding_because_the_scan_is_a_proxy(self):
        records = [_record('base'), _record('x', faces=2500)]
        scans = [self._scan('tail_shell_U0.5_base',
                            disagree=[{'z': -1.0, 'scan': 'severed', 'kernel_annulus': True}])]
        assert inputs.screen_verdict(records, scans)['clean'] is False

    def test_a_build_failure_is_recorded_and_is_not_itself_unclean(self):
        """**A configuration the construction refuses is the safe outcome**, not a defect in the
        wall: the existing checks declining to hand back a broken part is them working. It is
        counted so the screen can say how much of the input space the construction will build at
        all -- found immediately, on the nose's own `buttress_cut_thickness_lo`, where
        `dilated_notches`' facet precondition refuses a 0.07 mm slot against a 0.6 mm dilation."""
        records = [_record('base'), _record('extrusion_width_hi', faces=2500),
                   {'label': 'tail_shell_U0.5_buttress_cut_thickness_lo', 'kind': 'tail_shell',
                    'u': 0.5, 'case': 'buttress_cut_thickness_lo',
                    'error': 'PreconditionFailed: ...'}]
        scans = [self._scan('tail_shell_U0.5_base'),
                 self._scan('tail_shell_U0.5_extrusion_width_hi')]
        got = inputs.screen_verdict(records, scans)
        assert got['build_failures'] == ['buttress_cut_thickness_lo']
        assert got['built'] == 2
        assert got['clean'] is True

    def test_an_empty_screen_is_vacuous_and_says_so_three_ways(self):
        got = inputs.screen_verdict([], [])
        assert got['clean'] is False
        assert len(got['vacuous_because']) == 3

    def test_the_table_renders_without_a_scan_and_marks_the_unmoved(self):
        records = [_record('base'), _record('top2_y_hi', build_s=727.0),
                   {'label': 'x', 'case': 'bad', 'error': 'boom'}]
        text = inputs.screen_table(records)
        assert 'unmoved' in text
        assert 'REFUSED' in text
        assert 'base' in text


# ----------------------------------------------------------------- the two corpora


class TestScreenCorpusDiscovery:

    def test_an_absent_screen_is_empty_not_an_error(self, tmp_path):
        assert corpus.screen(shapes_dir=str(tmp_path / 'nope')) == []
        assert corpus.screen_records(records_dir=str(tmp_path / 'nope')) == {}

    def test_a_screen_filename_parses_into_its_case(self, tmp_path):
        d = tmp_path / 'shapes'
        d.mkdir()
        for name in ('tail_shell_U0.5_base.brep', 'tail_shell_U0.5_top1_angle_hi.brep',
                     'nose_cowl_shell_U1.0_extrusion_width_lo.brep', 'notes.txt'):
            (d / name).write_text('x')
        got = corpus.screen(shapes_dir=str(d), records_dir=str(tmp_path / 'none'))
        assert [r.label for r in got] == ['nose_cowl_shell_U1.0_extrusion_width_lo',
                                          'tail_shell_U0.5_base',
                                          'tail_shell_U0.5_top1_angle_hi']
        assert got[2].kind == 'tail_shell' and got[2].u == '0.5'
        assert got[2].case == 'top1_angle_hi'

    def test_the_screen_pattern_does_not_claim_a_soak_wall(self, tmp_path):
        """**The collision that would merge the two corpora.** `_r3` is a perfectly good case name
        as far as a careless regex is concerned, and a soak repeat read as a screen case would put
        a `U`-axis wall into the input-axis population. OQ-DES-CW26's remaining question is about
        that axis specifically, so a verdict has to be able to say which population it covered."""
        d = tmp_path / 'shapes'
        d.mkdir()
        for name in ('tail_shell_U4.0_r3.brep', 'nose_cowl_shell_U0.5_r0.brep',
                     'tail_shell_U0.5_base.brep'):
            (d / name).write_text('x')
        got = corpus.screen(shapes_dir=str(d), records_dir=str(tmp_path / 'none'))
        assert [r.label for r in got] == ['tail_shell_U0.5_base']

    def test_the_soak_pattern_does_not_claim_a_screen_wall_either(self, tmp_path):
        d = tmp_path / 'shapes'
        d.mkdir()
        for name in ('tail_shell_U4.0_r3.brep', 'tail_shell_U0.5_base.brep',
                     'tail_shell_U0.5_top1_angle_hi.brep'):
            (d / name).write_text('x')
        got = corpus.available(shapes_dir=str(d), results=str(tmp_path / 'none.jsonl'))
        assert [r.label for r in got] == ['tail_shell_U4.0_r3']

    def test_the_pair_corpus_reads_its_own_directories_and_not_the_screens(self, tmp_path):
        """**A third population, and the same collision risk as the first two.** A two-row wall
        counted among the one-row screen's would make "the screen found no severed ring" cover an
        axis it never scanned, which is the distinction OQ-DES-CW26's alternatives turn on."""
        screen_dir, pair_dir = tmp_path / 'screen', tmp_path / 'pairs'
        screen_dir.mkdir()
        pair_dir.mkdir()
        (screen_dir / 'nose_cowl_shell_U1.0_cut_len_hi.brep').write_text('x')
        (pair_dir / 'nose_cowl_shell_U1.0_cut_len_hi__butt_angle_lo.brep').write_text('x')
        none = str(tmp_path / 'none')
        assert [r.case for r in corpus.screen(shapes_dir=str(screen_dir),
                                              records_dir=none)] == ['cut_len_hi']
        assert [r.case for r in corpus.pairs(shapes_dir=str(pair_dir),
                                             records_dir=none)] == ['cut_len_hi__butt_angle_lo']

    def test_an_absent_pair_corpus_is_empty_not_an_error(self, tmp_path):
        assert corpus.pairs(shapes_dir=str(tmp_path / 'nope'),
                            records_dir=str(tmp_path / 'nope')) == []


class TestBuiltSingleNames:
    """The filter that keeps an inherited refusal from being reported as an interaction."""

    def _record(self, where, label, case, error=None):
        payload = {'label': label, 'case': case}
        if error:
            payload['error'] = error
        (where / ('%s.json' % label)).write_text(json.dumps(payload))

    def test_a_refused_case_is_not_counted_as_built(self, tmp_path):
        d = tmp_path / 'records'
        d.mkdir()
        self._record(d, 'nose_cowl_shell_U1.0_cut_len_hi', 'cut_len_hi')
        self._record(d, 'nose_cowl_shell_U1.0_extrusion_width_hi', 'extrusion_width_hi',
                     error='ValueError: the wall has no solids')
        got = inputs.built_single_names('nose_cowl_shell', 1.0, records_dir=str(d))
        assert got == {'cut_len_hi'}

    def test_no_records_at_all_is_none_and_not_an_empty_set(self, tmp_path):
        """`None` and `set()` must not be confused: filtering a pair list against an empty set
        yields no cases, which would look like a screen with nothing to do."""
        d = tmp_path / 'records'
        d.mkdir()
        assert inputs.built_single_names('nose_cowl_shell', 1.0, records_dir=str(d)) is None
        assert inputs.built_single_names('nose_cowl_shell', 1.0,
                                         records_dir=str(tmp_path / 'nope')) is None

    def test_another_kinds_records_are_not_counted(self, tmp_path):
        d = tmp_path / 'records'
        d.mkdir()
        self._record(d, 'tail_shell_U1.0_cut_len_hi', 'cut_len_hi')
        assert inputs.built_single_names('nose_cowl_shell', 1.0, records_dir=str(d)) is None

    def test_pairs_filtered_by_members_drop_any_pair_with_a_refused_row(self):
        exc = (inputs.Excursion('extrusion_width', 0.2, 'mm', 'a'),
               inputs.Excursion('cut_len', 0.02, 'mm', 'b'))
        members = {'extrusion_width_lo', 'cut_len_lo', 'cut_len_hi'}   # extrusion_width_hi refused
        got = inputs.pair_cases('nose_cowl_shell', 1.0, exc, include_baseline=False,
                                members=members)
        assert len(got) == 2
        assert all(c.name.startswith('extrusion_width_lo__') for c in got)

    def test_a_soak_record_still_labels_itself_by_repeat(self):
        """The `case` field is additive: a wall without one labels itself exactly as before."""
        rec = corpus.WallRecord('tail_shell', '4.0', 3, 'x.brep')
        assert rec.label == 'tail_shell_U4.0_r3'
        assert rec.case is None

    def test_a_case_record_is_joined_to_its_shape(self, tmp_path):
        d = tmp_path / 'shapes'
        d.mkdir()
        (d / 'tail_shell_U0.5_top1_angle_hi.brep').write_text('x')
        r = tmp_path / 'records'
        r.mkdir()
        (r / 'anything.json').write_text(json.dumps(
            {'label': 'tail_shell_U0.5_top1_angle_hi', 'solids': 1, 'build_s': 727.0}))
        got = corpus.screen(shapes_dir=str(d), records_dir=str(r))
        assert got[0].recorded['build_s'] == 727.0

    def test_screen_walls_are_not_deduplicated(self, tmp_path):
        """`distinct` drops byte-identical repeats because the soak built five of each on purpose.
        Here every wall is a different configuration by construction, and a case that *does* come
        back identical to the baseline is `unmoved`'s finding rather than a duplicate to discard."""
        d = tmp_path / 'shapes'
        d.mkdir()
        r = tmp_path / 'records'
        r.mkdir()
        for case in ('base', 'top2_y_hi'):
            (d / ('tail_shell_U0.5_%s.brep' % case)).write_text('x')
            (r / ('%s.json' % case)).write_text(json.dumps(
                {'label': 'tail_shell_U0.5_%s' % case, 'wall_hash': 'same'}))
        got = corpus.screen(shapes_dir=str(d), records_dir=str(r))
        assert len(got) == 2
