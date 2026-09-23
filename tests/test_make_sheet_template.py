"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for make_sheet_template.py.

Lives under `src/Fuselage/tools/` but imports `drawing_standard` from
`src/Fuselage/freecad/`, which -- like `sheet_naming.py` (IP-TEST-4) -- has no FreeCAD
import of its own, so this module is importable and testable from the venv/pytest tier too.

`out_path()` returns a FIXED, hardcoded path into the real committed template location --
`main()` without `--check` really does write there. Every `main()` test either passes
`--check` (which returns before any write) or monkeypatches `mst.out_path` to a `tmp_path`
location first, so no test in this file ever touches the real committed
`fuselage_ansi_a_landscape.svg`.
"""
import make_sheet_template as mst
import pytest

# ------------------------------------------------------------
# cells
# ------------------------------------------------------------

def test_cells_widths_sum_to_the_full_block_width_in_every_row():
    w = mst.BLOCK_MM[0]
    by_row = {}
    for row, offset, width, _caption, _field, _default in mst.cells():
        by_row.setdefault(row, []).append((offset, width))
    for row, entries in by_row.items():
        entries.sort()
        total = sum(width for _offset, width in entries)
        assert total == pytest.approx(w), f'row {row} widths sum to {total}, not {w}'


def test_cells_the_units_statement_is_the_only_fixed_non_editable_cell():
    fixed = [c for c in mst.cells() if c[4] is None]
    assert len(fixed) == 1
    assert fixed[0][3] == mst.UNITS_TEXT
    assert fixed[0][5] is None


def test_cells_every_other_cell_has_a_field_and_a_default():
    editable = [c for c in mst.cells() if c[3] != mst.UNITS_TEXT]
    assert all(field is not None and default is not None
              for _row, _off, _w, _cap, field, default in editable)


# ------------------------------------------------------------
# block_origin / row_top / caption_baseline / value_baseline
# ------------------------------------------------------------

def test_block_origin_is_the_frame_bottom_right_corner_minus_the_block_size():
    frame_x, frame_y, frame_w, frame_h = mst.FRAME_MM
    block_w, block_h = mst.BLOCK_MM
    assert mst.block_origin() == (frame_x + frame_w - block_w, frame_y + frame_h - block_h)


def test_row_top_zero_is_the_block_origin_y():
    assert mst.row_top(0) == mst.block_origin()[1]


def test_row_top_accumulates_preceding_row_heights():
    expected = mst.block_origin()[1] + mst.ROWS_MM[0] + mst.ROWS_MM[1]
    assert mst.row_top(2) == pytest.approx(expected)


def test_row_top_at_the_row_count_reaches_the_block_bottom():
    bottom = mst.row_top(len(mst.ROWS_MM))
    assert bottom == pytest.approx(mst.block_origin()[1] + mst.BLOCK_MM[1])


def test_caption_baseline_is_pad_plus_caption_height_below_the_top():
    assert mst.caption_baseline(0.0) == pytest.approx(mst.PAD_MM + mst.CAPTION_MM)


def test_value_baseline_is_below_the_caption_baseline_by_the_line_spacing():
    expected = mst.caption_baseline(0.0) + mst.LINE_SPACING_HEIGHTS * max(
        mst.CAPTION_MM, mst.VALUE_MM)
    assert mst.value_baseline(0.0) == pytest.approx(expected)


# ------------------------------------------------------------
# check_rows
# ------------------------------------------------------------

def test_check_rows_finds_no_problems_with_the_real_committed_constants():
    """A regression pin for the module's own stated purpose: a caption-over-value overlap
    inside a title block cell renders and exports with no other check ever seeing it."""
    assert mst.check_rows() == []


def test_check_rows_flags_a_row_sum_mismatch(monkeypatch):
    monkeypatch.setattr(mst, 'ROWS_MM', (10.0, 9.0, 9.0, 9.0, 8.0))   # short by 1.0mm
    problems = mst.check_rows()
    assert any('rows sum to' in p for p in problems)


def test_check_rows_flags_a_row_too_short_to_hold_its_text(monkeypatch):
    tiny_rows = (1.0,) * len(mst.ROWS_MM)
    monkeypatch.setattr(mst, 'ROWS_MM', tiny_rows)
    monkeypatch.setattr(mst, 'BLOCK_MM', (mst.BLOCK_MM[0], sum(tiny_rows)))
    problems = mst.check_rows()
    assert any('does not fit in it' in p for p in problems)


# ------------------------------------------------------------
# rect / text
# ------------------------------------------------------------

def test_rect_omits_the_id_attribute_when_none_given():
    svg = mst.rect(1.0, 2.0, 3.0, 4.0)
    assert ' id=' not in svg
    assert 'x="1.0000"' in svg and 'height="4.0000"' in svg


def test_rect_includes_the_id_attribute_when_given():
    svg = mst.rect(0, 0, 1, 1, element_id='myFrame')
    assert 'id="myFrame"' in svg


def test_text_with_no_field_is_not_editable():
    svg = mst.text(1.0, 2.0, 3.5, 'HELLO')
    assert 'freecad:editable' not in svg
    assert '<tspan x="1.0000" y="2.0000">HELLO</tspan>' in svg


def test_text_with_a_field_carries_the_editable_attribute():
    svg = mst.text(1.0, 2.0, 3.5, 'default', field='PartNumber')
    assert 'freecad:editable="PartNumber"' in svg


# ------------------------------------------------------------
# build
# ------------------------------------------------------------

def test_build_declares_the_sheet_size_in_millimeters():
    svg = mst.build()
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    sheet_w, sheet_h = mst.SHEET_MM
    assert f'width="{sheet_w:g}mm" height="{sheet_h:g}mm"' in svg


def test_build_marks_the_frame_and_title_block_with_their_known_ids():
    import drawing_standard as ds
    svg = mst.build()
    assert f'id="{ds.TEMPLATE_FRAME_ID}"' in svg
    assert f'id="{ds.TEMPLATE_TITLE_BLOCK_ID}"' in svg


def test_build_has_exactly_one_editable_field_per_non_fixed_cell():
    svg = mst.build()
    editable_cells = [c for c in mst.cells() if c[4] is not None]
    assert svg.count('freecad:editable="') == len(editable_cells)


def test_build_includes_the_fixed_units_statement_as_literal_text():
    svg = mst.build()
    assert f'>{mst.UNITS_TEXT}<' in svg


# ------------------------------------------------------------
# out_path
# ------------------------------------------------------------

def test_out_path_points_at_the_freecad_templates_directory():
    path = mst.out_path()
    assert path.replace('\\', '/').endswith('freecad/templates/fuselage_ansi_a_landscape.svg')


# ------------------------------------------------------------
# main -- --check never writes; a real write always goes through a monkeypatched out_path
# ------------------------------------------------------------

def test_main_check_mode_reports_and_returns_zero_without_writing(monkeypatch, tmp_path, capsys):
    fake_path = tmp_path / 'template.svg'
    monkeypatch.setattr(mst, 'out_path', lambda: str(fake_path))
    result = mst.main(['--check'])
    assert result == 0
    assert not fake_path.exists()
    out = capsys.readouterr().out
    assert 'would write' in out
    assert 'title block' in out


def test_main_without_check_writes_the_real_svg_to_a_monkeypatched_path(monkeypatch, tmp_path):
    fake_path = tmp_path / 'nested' / 'template.svg'
    monkeypatch.setattr(mst, 'out_path', lambda: str(fake_path))
    result = mst.main([])
    assert result == 0
    assert fake_path.is_file()
    assert fake_path.read_text(encoding='utf-8').startswith('<?xml')


def test_main_raises_when_the_title_block_exceeds_its_envelope(monkeypatch):
    monkeypatch.setattr(mst, 'BLOCK_MM', (1000.0, 1000.0))
    with pytest.raises(SystemExit, match='outside the'):
        mst.main(['--check'])


def test_main_raises_when_the_rows_do_not_hold_their_text(monkeypatch):
    monkeypatch.setattr(mst, 'ROWS_MM', (1.0,) * len(mst.ROWS_MM))
    with pytest.raises(SystemExit, match='do not hold their text'):
        mst.main(['--check'])
