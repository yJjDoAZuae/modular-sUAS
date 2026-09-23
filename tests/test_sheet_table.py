"""IP-TEST-11: tests for freecad/sheet_table.py's pure helper functions -- the ones that do
not call column_width_mm/text_width_mm and so need no real font. sheet_table.py has no FreeCAD
import at module scope (its own docstring: "the table's width has to be measurable from the
virtualenv"), but most of its functions (block_layout, legend_table, caption_table, layout,
cell_box, check_layout, measure) route through drawing_standard's font-measuring functions and
so need fontTools, absent from this venv -- those get a freecadcmd-tier check instead
(check_sheet_table.py). This file covers what is left: string formatting, column/band
bookkeeping, and Table.fits()'s pure comparison against a region.
"""
import sys
from pathlib import Path

import pytest

_FREECAD_DIR = str(Path(__file__).resolve().parent.parent / 'src' / 'Fuselage' / 'freecad')
if _FREECAD_DIR not in sys.path:
    sys.path.insert(0, _FREECAD_DIR)

import sheet_table as st  # noqa: E402


# ------------------------------------------------------------
# printed / is_numeric
# ------------------------------------------------------------

def test_printed_uppercases_strings():
    assert st.printed('1/16in') == '1/16IN'


def test_printed_handles_non_string_values():
    assert st.printed(4.77) == '4.77'


def test_is_numeric_true_for_a_column_of_numbers():
    assert st.is_numeric(['1', '2.5', '-3']) is True


def test_is_numeric_false_for_a_column_with_any_non_numeric_cell():
    assert st.is_numeric(['1', '3/16in']) is False


def test_is_numeric_false_for_an_empty_column():
    assert st.is_numeric([]) is False


# ------------------------------------------------------------
# common_prefix
# ------------------------------------------------------------

def test_common_prefix_of_two_names_sharing_a_leading_segment():
    assert st.common_prefix(['end_anchor', 'end_bolt']) == 'end_'


def test_common_prefix_stops_at_a_segment_boundary_not_a_character():
    # 'end_anchor' vs 'endless' share no whole leading segment ('end' != 'endless').
    assert st.common_prefix(['end_anchor', 'endless_thing']) == ''


def test_common_prefix_of_names_sharing_nothing():
    assert st.common_prefix(['1/16in', '1/8in']) == ''


def test_common_prefix_of_fewer_than_two_names_is_empty():
    assert st.common_prefix(['only_one']) == ''
    assert st.common_prefix([]) == ''


def test_common_prefix_of_three_names_requires_all_to_share_it():
    assert st.common_prefix(['cowling_anchor', 'cowling_bolt', 'end_anchor']) == ''
    assert st.common_prefix(['cowling_anchor', 'cowling_bolt', 'cowling_plate']) == 'cowling_'


# ------------------------------------------------------------
# heading_of
# ------------------------------------------------------------

def test_heading_of_uses_the_explicit_heading_when_field_is_none():
    column = {'field': None, 'heading': 'axis label'}
    assert st.heading_of(column, {}) == 'AXIS LABEL'


def test_heading_of_uses_the_explicit_heading_even_with_a_field():
    column = {'field': 'panel_thickness', 'heading': 'custom'}
    assert st.heading_of(column, {}) == 'CUSTOM'


def test_heading_of_falls_back_to_the_callout_letter():
    column = {'field': 'panel_thickness', 'heading': None}
    assert st.heading_of(column, {'panel_thickness': 'A'}) == 'A'


def test_heading_of_raises_when_no_letter_was_issued_for_the_field():
    column = {'field': 'panel_thickness', 'heading': None}
    with pytest.raises(ValueError, match='no callout letter'):
        st.heading_of(column, {})


# ------------------------------------------------------------
# band_of
# ------------------------------------------------------------

def test_band_of_groups_consecutive_columns_sharing_a_field_and_heading():
    block = {'columns': [
        {'field': 'panel_thickness', 'heading': '1/16IN'},
        {'field': 'panel_thickness', 'heading': '1/8IN'},
        {'field': None, 'heading': 'U'},
    ]}
    assert st.band_of(block, {}) == {'panel_thickness': (0, 1)}


def test_band_of_ignores_columns_with_no_heading():
    block = {'columns': [{'field': 'panel_thickness', 'heading': None}]}
    assert st.band_of(block, {}) == {}


def test_band_of_empty_for_a_block_with_no_banded_columns():
    block = {'columns': [{'field': None, 'heading': 'U'}]}
    assert st.band_of(block, {}) == {}


# ------------------------------------------------------------
# _cells_by_key
# ------------------------------------------------------------

def test_cells_by_key_pairs_by_key_value_not_by_position():
    column = {'keys': ['0.5', '1', '2'], 'cells': ['4.0', '6.0', '8.0']}
    assert st._cells_by_key(column) == {'0.5': '4.0', '1': '6.0', '2': '8.0'}


def test_cells_by_key_pairs_a_shorter_coupled_band_by_leading_keys_only():
    """A band column can hold fewer cells than the key column has keys -- the module's own
    docstring: "a band column can have three cells where the key column has eight values."
    `zip` pairs by position among the two lists given, so the band's cells land against the
    *first* N keys -- correct only when the caller has already dropped the keys with no
    matching cell, which block_layout's own `by_key.get(key)` lookup (returning None for a
    missing combination) is what actually makes safe, not this function."""
    column = {'keys': ['0.5', '1', '2'], 'cells': ['6.0']}
    assert st._cells_by_key(column) == {'0.5': '6.0'}


# ------------------------------------------------------------
# column_strings
# ------------------------------------------------------------

def test_column_strings_appends_the_heading_after_the_cells():
    column = {'cells': ['4.0', '6.0'], 'field': None, 'heading': 'note'}
    assert st.column_strings(column, {}) == ['4.0', '6.0', 'NOTE']


def test_column_strings_drops_empty_strings():
    column = {'cells': ['', '6.0'], 'field': None, 'heading': ''}
    assert st.column_strings(column, {}) == ['6.0']


def test_column_strings_uses_an_explicit_heading_override():
    column = {'cells': ['1'], 'field': 'x', 'heading': None}
    assert st.column_strings(column, {'x': 'A'}, heading='OVERRIDE') == ['1', 'OVERRIDE']


# ------------------------------------------------------------
# band_headings
# ------------------------------------------------------------

def test_band_headings_shortens_a_band_to_its_distinguishing_suffix():
    block = {'columns': [
        {'field': 'bulkhead_type_name', 'heading': 'cowling_anchor'},
        {'field': 'bulkhead_type_name', 'heading': 'cowling_bolt'},
    ]}
    headings = st.band_headings(block, {})
    assert headings == {0: 'ANCHOR', 1: 'BOLT'}


def test_band_headings_keeps_full_names_when_shortening_would_collide():
    block = {'columns': [
        {'field': 'x', 'heading': 'a_b'},
        {'field': 'x', 'heading': 'a_b'},
    ]}
    headings = st.band_headings(block, {})
    assert headings == {0: 'A_B', 1: 'A_B'}


def test_band_headings_falls_back_to_heading_of_for_unbanded_columns():
    block = {'columns': [{'field': None, 'heading': 'plain'}]}
    assert st.band_headings(block, {}) == {0: 'PLAIN'}


# ------------------------------------------------------------
# _overlap
# ------------------------------------------------------------

def test_overlap_detects_two_intersecting_boxes():
    assert st._overlap((0, 0, 10, 10), (5, 5, 15, 15)) is True


def test_overlap_false_for_boxes_that_merely_touch():
    assert st._overlap((0, 0, 10, 10), (10, 0, 20, 10)) is False


def test_overlap_false_for_disjoint_boxes():
    assert st._overlap((0, 0, 10, 10), (20, 20, 30, 30)) is False


# ------------------------------------------------------------
# Table.fits -- pure comparison against a region, no font measurement
# ------------------------------------------------------------

def test_table_fits_reports_nothing_when_within_the_region():
    table = st.Table(cells=[], rules=[], width=50.0, height=30.0, rows=5)
    assert table.fits((0.0, 0.0, 100.0, 40.0)) == []


def test_table_fits_reports_a_width_overflow():
    table = st.Table(cells=[], rules=[], width=150.0, height=30.0, rows=5)
    problems = table.fits((0.0, 0.0, 100.0, 40.0))
    assert len(problems) == 1
    assert 'wide' in problems[0]
    assert '50.0' in problems[0]


def test_table_fits_reports_a_height_overflow():
    table = st.Table(cells=[], rules=[], width=50.0, height=60.0, rows=5)
    problems = table.fits((0.0, 0.0, 100.0, 40.0))
    assert len(problems) == 1
    assert 'deep' in problems[0]


def test_table_fits_reports_both_overflows_independently():
    table = st.Table(cells=[], rules=[], width=150.0, height=60.0, rows=5)
    problems = table.fits((0.0, 0.0, 100.0, 40.0))
    assert len(problems) == 2


def test_cell_repr_is_readable():
    cell = st.Cell('4.77', 1.0, 2.0, 2.5)
    assert '4.77' in repr(cell)
