"""IP-TEST-11: tests for freecad/drawing_standard.py's pure layout/formatting functions.

drawing_standard.py has no FreeCAD import at module scope (`resource_dir()` imports FreeCAD
lazily, only when called with no explicit path), so everything not requiring a real font file
is testable from this tier. Font-measurement functions (`text_width_mm`, `verify_font`,
`typo_ascender_units`, and `column_width_mm`/anything that calls them) need `fontTools`, which
is not a project dependency and is not installed in this venv -- those get a freecadcmd-tier
check instead (`check_drawing_standard.py`), where FreeCAD's own Python has fontTools built in.

This module had no test of its own before this. Writing it surfaced a real, significant defect
fixed as part of the same change (see `test_table_height_mm_and_table_rows_available_use_the_
real_row_pitch` below): `table_height_mm()` and `table_rows_available()` computed table depth
from the raw `TABLE_ROW_PITCH_HEIGHTS * height` (the ISO 3098 baseline-spacing term alone),
while `sheet_table.py` -- the actual renderer -- spaces rows at `table_row_pitch_mm()` (the
larger of that term and the ruled-row clearance requirement). The two disagreed by about 30%.
Verified against the real family-sheet checks before fixing: `check_table_width.py`'s real
per-family verdicts (driven by `sheet_table.layout()`, which was already correct) were
unaffected -- only its printed "rows available" figure changed, from a wrong 13 to the correct
10 -- and `check_dimension_placement.py`/`check_sheet_standard.py`'s real verdicts were
unaffected too (the title block already dominated the band depth in both directions).
"""
import sys
from pathlib import Path

import pytest

_FREECAD_DIR = str(Path(__file__).resolve().parent.parent / 'src' / 'Fuselage' / 'freecad')
if _FREECAD_DIR not in sys.path:
    sys.path.insert(0, _FREECAD_DIR)

import drawing_standard as ds  # noqa: E402


# ------------------------------------------------------------
# format_length / format_column
# ------------------------------------------------------------

def test_format_length_rounds_to_the_decimal_places_given():
    assert ds.format_length(4.7625, 2) == '4.76'
    assert ds.format_length(4.0, 2) == '4.00'


def test_format_length_normalizes_negative_zero():
    assert ds.format_length(-0.001, 2) == '0.00'
    assert not ds.format_length(-0.001, 2).startswith('-')


def test_format_column_uses_the_fewest_decimal_places_that_loses_no_value():
    assert ds.format_column([4.0, 10.0, 5.0]) == ['4', '10', '5']
    assert ds.format_column([4.5, 10.0, 5.0]) == ['4.5', '10.0', '5.0']
    assert ds.format_column([4.76, 10.0]) == ['4.76', '10.00']


def test_format_column_passes_through_non_numeric_values_unchanged():
    assert ds.format_column(['1/16in', '3/8in']) == ['1/16in', '3/8in']


# ------------------------------------------------------------
# Sheet regions
# ------------------------------------------------------------

def test_table_region_defaults_to_the_widest_the_band_can_hold():
    frame_x, frame_y, frame_w, frame_h = ds.TEMPLATE_FRAME_MM
    _bx, _by, block_w, _bh = ds.TEMPLATE_TITLE_BLOCK_MM
    x, y, w, h = ds.table_region_mm()
    assert w == pytest.approx(frame_w - block_w - ds.TABLE_COLUMN_GUTTER_MM)
    assert h == pytest.approx(ds.table_band_depth_mm())
    assert x == frame_x
    assert y == pytest.approx(frame_y + frame_h - h)


def test_table_region_honors_an_explicit_width():
    _x, _y, w, _h = ds.table_region_mm(50.0)
    assert w == 50.0


def test_view_region_with_no_table_is_the_whole_frame():
    assert ds.view_region_mm() == ds.TEMPLATE_FRAME_MM


def test_view_region_with_a_table_subtracts_its_width_and_the_gutter():
    frame_x, frame_y, frame_w, frame_h = ds.TEMPLATE_FRAME_MM
    x, y, w, h = ds.view_region_mm(50.0)
    assert w == pytest.approx(frame_w - 50.0 - ds.TABLE_COLUMN_GUTTER_MM)
    assert (x, y, h) == (frame_x, frame_y, frame_h)


def test_frame_region_is_the_template_frame():
    assert ds.frame_region_mm() == ds.TEMPLATE_FRAME_MM


# ------------------------------------------------------------
# view_appearance
# ------------------------------------------------------------

def test_view_appearance_default_is_outline_weight_with_center_marks_off():
    appearance = ds.view_appearance()
    assert appearance['LineWidth'] == ds.WIDE_LINE_MM
    assert appearance['ArcCenterMarks'] is False


def test_view_appearance_for_a_rule_view_is_narrow_with_no_center_marks_key_conflict():
    appearance = ds.view_appearance('ValueTableRuleView')
    assert appearance['LineWidth'] == ds.NARROW_LINE_MM
    assert appearance['ArcCenterMarks'] is False


def test_view_appearance_only_matches_the_rule_suffix_not_any_substring():
    assert ds.view_appearance('RuleViewButNotAtTheEnd') == ds.view_appearance()


# ------------------------------------------------------------
# Row pitch / table depth -- the real bug found and fixed here
# ------------------------------------------------------------

def test_table_row_pitch_mm_is_the_larger_of_the_two_iso_3098_requirements():
    height = 2.5
    line_spacing = ds.TABLE_ROW_PITCH_HEIGHTS * height
    ruled_row = (ds.EM_PER_TEXT_HEIGHT + 2.0 * ds.TABLE_ROW_CLEARANCE_HEIGHTS) * height
    assert ds.table_row_pitch_mm(height) == pytest.approx(max(line_spacing, ruled_row))
    # At this project's table text height, the ruled-row term is the binding one -- the whole
    # reason table_height_mm/table_rows_available's old formula (line_spacing alone) was wrong.
    assert ruled_row > line_spacing


def test_table_height_mm_and_table_rows_available_use_the_real_row_pitch():
    """Regression test for the IP-TEST-11 fix: both functions must agree with the actual
    per-row pitch sheet_table.py draws at, not a cheaper approximation of it."""
    height = 2.5
    real_pitch = ds.table_row_pitch_mm(height)
    assert ds.table_height_mm(10, height) == pytest.approx(10 * real_pitch)
    assert ds.table_rows_available(height) == int(ds.table_band_depth_mm() // real_pitch)
    # The corrected figure: 10 rows fit in the band, not the 13 the pre-fix formula gave.
    assert ds.table_rows_available(height) == 10


def test_table_band_depth_is_the_quarter_the_view_does_not_get():
    assert ds.table_band_depth_mm() == pytest.approx(
        (1.0 - ds.VIEW_SHARE) * ds.TEMPLATE_FRAME_MM[3])


def test_table_column_height_mm_is_an_alias_for_table_band_depth_mm():
    assert ds.table_column_height_mm() == ds.table_band_depth_mm()


def test_table_width_available_mm_subtracts_the_view_and_one_gutter():
    got = ds.table_width_available_mm(100.0)
    assert got == pytest.approx(ds.TEMPLATE_FRAME_MM[2] - 100.0 - ds.TABLE_COLUMN_GUTTER_MM)


# ------------------------------------------------------------
# table_width_mm
# ------------------------------------------------------------

def test_table_width_mm_sums_columns_and_gutters_between_them():
    assert ds.table_width_mm([10.0, 20.0, 30.0]) == pytest.approx(
        60.0 + 2 * ds.TABLE_COLUMN_GUTTER_MM)


def test_table_width_mm_of_no_columns_is_zero():
    assert ds.table_width_mm([]) == 0.0


def test_table_width_mm_of_one_column_has_no_gutter():
    assert ds.table_width_mm([42.0]) == 42.0


# ------------------------------------------------------------
# best_view
# ------------------------------------------------------------

def test_best_view_with_no_table_gives_the_view_the_frame_less_the_title_block():
    placement, width, height, area, depth, column = ds.best_view(0.0, 0.0, 130.0, 46.0)
    assert placement == ds.PLACEMENT_BAND
    assert height == pytest.approx(ds.TEMPLATE_FRAME_MM[3] - 46.0)
    # With no table, the band's own depth is simply the title block's -- there is nothing
    # beside it to be the deeper of the two.
    assert depth == 46.0


def test_best_view_chooses_band_when_the_table_fits_beside_the_title_block():
    # 95.1 mm table beside a 130 mm block, comfortably under the 239.52 mm frame width.
    placement, _w, _h, _a, _d, _c = ds.best_view(95.1, ds.table_height_mm(10), 130.0, 46.0)
    assert placement == ds.PLACEMENT_BAND


def test_best_view_falls_back_to_column_when_the_table_does_not_fit_beside_the_block():
    # 150 mm table beside a 130 mm block: 130 + 1.0 gutter + 150 = 281 mm, over the 239.52 mm
    # frame, so the band option is excluded -- but a 150 mm column still leaves the view room.
    placement, _w, _h, _a, _d, _c = ds.best_view(150.0, 40.0, 130.0, 46.0)
    assert placement == ds.PLACEMENT_COLUMN


def test_best_view_column_width_is_the_wider_of_table_and_block():
    # 150 mm table, 130 mm block: band excluded (as in the fallback test above), so only the
    # column option survives, and its width is the wider of the two -- the table.
    placement, width, _h, _a, _d, column = ds.best_view(150.0, 40.0, 130.0, 46.0)
    assert placement == ds.PLACEMENT_COLUMN
    assert column == max(150.0, 130.0)
    frame_w = ds.TEMPLATE_FRAME_MM[2]
    assert width == pytest.approx(frame_w - column - ds.TABLE_COLUMN_GUTTER_MM)


def test_best_view_returns_none_placement_when_nothing_fits():
    result = ds.best_view(1e6, 1e6, 1e6, 1e6, frame_w=10.0, frame_h=10.0)
    assert result[0] == 'none'


# ------------------------------------------------------------
# title_block_envelope
# ------------------------------------------------------------

def test_title_block_envelope_matches_ansi_a_with_the_compacted_table():
    """The module's own documented figure: 143.4 x 46.8 mm on ANSI A with the compacted
    table."""
    width, depth = ds.title_block_envelope(95.1, ds.table_height_mm(10))
    assert width == pytest.approx(143.413, abs=1e-2)
    assert depth == pytest.approx(46.8, abs=1e-2)


def test_title_block_envelope_is_none_when_the_table_alone_exceeds_the_band():
    assert ds.title_block_envelope(95.1, 1000.0) is None


# ------------------------------------------------------------
# read_template_rect / verify_template -- against the real, committed template
# ------------------------------------------------------------

def test_read_template_rect_finds_the_real_frame_rectangle():
    path = ds.template_path()
    with open(path, encoding='utf-8') as f:
        text = f.read()
    found = ds.read_template_rect(text, ds.TEMPLATE_FRAME_ID)
    assert found == pytest.approx(ds.TEMPLATE_FRAME_MM, abs=1e-3)


def test_read_template_rect_returns_none_for_a_missing_id():
    with open(ds.template_path(), encoding='utf-8') as f:
        text = f.read()
    assert ds.read_template_rect(text, 'not_a_real_id') is None


def test_verify_template_holds_against_the_real_committed_template():
    """The real, committed template file -- not a synthetic fixture -- since it ships in the
    repository and this is exactly what require_standard() checks before every real build."""
    assert ds.verify_template() == []


def test_verify_template_reports_a_missing_file_rather_than_crashing(tmp_path):
    problems = ds.verify_template(str(tmp_path / 'does_not_exist.svg'))
    assert len(problems) == 1
    assert 'not at' in problems[0]


def test_verify_template_detects_a_moved_frame_rectangle(tmp_path):
    real_path = ds.template_path()
    with open(real_path, encoding='utf-8') as f:
        text = f.read()
    import re
    match = re.search('<rect[^>]*id="%s"[^>]*>' % re.escape(ds.TEMPLATE_FRAME_ID), text)
    assert match is not None, 'fixture assumption: the real template still has this rect'
    broken_tag = re.sub(r'width="[^"]*"', 'width="999"', match.group(0), count=1)
    moved = text.replace(match.group(0), broken_tag, 1)
    broken = tmp_path / 'moved_frame.svg'
    broken.write_text(moved, encoding='utf-8')
    problems = ds.verify_template(str(broken))
    assert any('drawing frame' in p for p in problems)


# ------------------------------------------------------------
# mm_from_units / callout_width_mm / digits_width_mm -- no font file needed, pure arithmetic
# ------------------------------------------------------------

def test_mm_from_units_scales_by_em_and_cap_height():
    got = ds.mm_from_units(ds.UNITS_PER_EM, 1.0)
    assert got == pytest.approx(ds.EM_PER_TEXT_HEIGHT)


def test_callout_width_mm_matches_the_pinned_widest_glyph():
    got = ds.callout_width_mm(ds.TEXT_HEIGHT_MM)
    want = ds.mm_from_units(ds.WIDEST_CALLOUT_UNITS, ds.TEXT_HEIGHT_MM)
    assert got == pytest.approx(want)


def test_digits_width_mm_adds_a_decimal_point_and_a_minus_sign_when_asked():
    height = ds.TEXT_HEIGHT_MM
    bare = ds.digits_width_mm(3, decimals=0, negative=False, text_height_mm=height)
    with_decimal = ds.digits_width_mm(3, decimals=1, negative=False, text_height_mm=height)
    with_minus = ds.digits_width_mm(3, decimals=0, negative=True, text_height_mm=height)
    assert with_decimal > bare
    assert with_minus > bare
    assert with_decimal == pytest.approx(
        bare + ds.mm_from_units(ds.DECIMAL_POINT_UNITS, height))
    assert with_minus == pytest.approx(bare + ds.mm_from_units(ds.MINUS_UNITS, height))


# ------------------------------------------------------------
# require_standard / _require -- error plumbing
# ------------------------------------------------------------

def test_require_raises_with_every_problem_listed():
    with pytest.raises(ValueError) as exc_info:
        ds._require(['problem one', 'problem two'], 'headline')
    message = str(exc_info.value)
    assert 'headline' in message
    assert 'problem one' in message
    assert 'problem two' in message


def test_require_does_nothing_when_there_are_no_problems():
    ds._require([], 'headline')  # must not raise
