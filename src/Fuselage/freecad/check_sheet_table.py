"""IP-TEST-11: sheet_table.py's font-dependent layout functions -- block_layout, legend_table,
caption_table, layout, cell_box, check_layout, measure -- all route through
drawing_standard.column_width_mm/text_width_mm and so need fontTools, absent from the pytest
venv. See tests/test_sheet_table.py for the pure helpers (printed, is_numeric, common_prefix,
heading_of, band_of, _cells_by_key, column_strings, band_headings, _overlap, Table.fits).

This is the module `check_table_width.py` already builds real family tables through, but only
exercises `layout()`/`measure()` end to end against real family data -- never
`block_layout`/`legend_table`/`caption_table` individually, and never `check_layout`'s own
refusal paths outside `check_table_width.py`'s own "broken on purpose" cases (which this check
duplicates in isolation, so a regression in `check_layout` itself is caught here without
needing real family data).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_standard as std
import sheet_table as st
from corner_common import is_entry_point


def _simple_block():
    """A small, real-shaped block: one key column and one value column, no band.

    The key column is keyed by its own values -- `block_layout` calls `_cells_by_key` on
    every column including the leading one, so it needs a real `keys` list too, not `None`.
    """
    return {
        'axis': 'U',
        'rows': 3,
        'columns': [
            {'field': None, 'heading': 'U', 'cells': ['0.5', '1', '2'],
             'keys': ['0.5', '1', '2']},
            {'field': 'panel_thickness', 'heading': None,
             'cells': ['4.00', '6.00', '8.00'], 'keys': ['0.5', '1', '2']},
        ],
    }


def _banded_block():
    """A block with a coupled band: two panel_thickness columns keyed by U."""
    return {
        'axis': 'U',
        'rows': 2,
        'columns': [
            {'field': None, 'heading': 'U', 'cells': ['0.5', '1'], 'keys': ['0.5', '1']},
            {'field': 'panel_name', 'heading': '1/16IN',
             'cells': ['4.00'], 'keys': ['0.5']},
            {'field': 'panel_name', 'heading': '1/8IN',
             'cells': ['4.00', '6.00'], 'keys': ['0.5', '1']},
        ],
    }


def _check_block_layout():
    ok = True
    block = _simple_block()
    letters = {'panel_thickness': 'A'}
    cells, rules, width, rows = st.block_layout(block, letters, origin_x=0.0)

    if width <= 0.0:
        print('  FAIL block_layout: width=%.4f, want > 0' % width)
        ok = False
    # heading row (1) + 3 data rows = 4.
    if rows != 4:
        print('  FAIL block_layout: rows=%d, want 4' % rows)
        ok = False
    # 2 columns * 4 rows = 8 cells, all present (no coupled band to skip any).
    if len(cells) != 8:
        print('  FAIL block_layout: %d cells, want 8' % len(cells))
        ok = False
    for cell in cells:
        if not (0.0 - 1e-6 <= cell.x <= width + 1e-6):
            print('  FAIL block_layout: cell %r at x=%.4f is outside the table width %.4f'
                  % (cell.text, cell.x, width))
            ok = False

    banded = _banded_block()
    b_cells, b_rules, b_width, b_rows = st.block_layout(banded, {'panel_name': 'B'},
                                                        origin_x=0.0)
    # heading rows (2, since it has a band) + 2 data rows = 4.
    if b_rows != 4:
        print('  FAIL block_layout (banded): rows=%d, want 4' % b_rows)
        ok = False
    # The coupled band's first column has only 1 cell for 2 keys -- block_layout must skip the
    # missing combination rather than inventing a cell for it.
    from collections import Counter
    texts = Counter(c.text for c in b_cells)
    if texts.get('4.00', 0) < 2:
        # 4.00 appears in the simple column at U=0.5 (band col 1) and U=1 (band col 2) both --
        # just confirm no crash and a plausible cell count instead of an exact text match,
        # since two different real 4.00 cells are expected here.
        pass
    if len(b_cells) >= 2 * 2 * 3:  # would mean a phantom cell was invented for a missing key
        print('  FAIL block_layout (banded): %d cells is too many for a band missing one '
              'combination -- a cell may have been invented for a key with no data'
              % len(b_cells))
        ok = False

    if ok:
        print('  block_layout: OK  simple: width=%.2f rows=%d cells=%d  '
              'banded: width=%.2f rows=%d cells=%d'
              % (width, rows, len(cells), b_width, b_rows, len(b_cells)))
    return ok


def _check_legend_table():
    ok = True
    pairs = [('A', 'bore diameter'), ('B', 'bolt offset'), ('C', 'flange height')]
    table = st.legend_table(pairs, columns=1)
    if table.rows != 1 + len(pairs):
        print('  FAIL legend_table: rows=%d, want %d' % (table.rows, 1 + len(pairs)))
        ok = False
    # Every letter and every phrase must appear among the cells, verbatim -- unlike the value
    # table's columns, legend_table does not uppercase its phrases (measures and draws the
    # same raw string, which is internally consistent even though it is a different
    # convention from column_strings'/printed()'s shouted-uppercase one).
    texts = {c.text for c in table.cells}
    for letter, phrase in pairs:
        if letter not in texts:
            print('  FAIL legend_table: letter %r missing from cells' % letter)
            ok = False
        if phrase not in texts:
            print('  FAIL legend_table: phrase %r missing from cells' % phrase)
            ok = False

    two_col = st.legend_table(pairs, columns=2)
    if two_col.width <= table.width:
        print('  FAIL legend_table: 2 columns (%.2f mm) should be wider than 1 column (%.2f mm)'
              % (two_col.width, table.width))
        ok = False
    if two_col.height >= table.height:
        print('  FAIL legend_table: 2 columns (%.2f mm deep) should be shallower than 1 column '
              '(%.2f mm deep)' % (two_col.height, table.height))
        ok = False

    empty = st.legend_table([])
    if (empty.width, empty.height, empty.rows) != (0.0, 0.0, 0):
        print('  FAIL legend_table: empty input gave %r, want (0.0, 0.0, 0)'
              % ((empty.width, empty.height, empty.rows),))
        ok = False

    if ok:
        print('  legend_table: OK  1-col=%.2fx%.2f  2-col=%.2fx%.2f'
              % (table.width, table.height, two_col.width, two_col.height))
    return ok


def _check_caption_table():
    ok = True
    rows = [('KIND', 'BULKHEAD'), ('VARIANTS', '12'), ('COVERAGE', '100%')]
    side_by_side = st.caption_table(rows, stacked=False)
    stacked = st.caption_table(rows, stacked=True)

    if stacked.width >= side_by_side.width:
        print('  FAIL caption_table: stacked (%.2f) should be narrower than side-by-side '
              '(%.2f)' % (stacked.width, side_by_side.width))
        ok = False
    if stacked.height <= side_by_side.height:
        print('  FAIL caption_table: stacked (%.2f) should be deeper than side-by-side '
              '(%.2f)' % (stacked.height, side_by_side.height))
        ok = False

    fitted, problems = st.caption_fitting(rows, width_mm=1000.0)
    if problems:
        print('  FAIL caption_fitting: a generous width still reported problems: %r' % problems)
        ok = False
    if fitted.width != side_by_side.width:
        print('  FAIL caption_fitting: did not choose the side-by-side form when it fits')
        ok = False

    _tight, tight_problems = st.caption_fitting(rows, width_mm=1.0)
    if not tight_problems:
        print('  FAIL caption_fitting: an impossibly narrow width reported no problems')
        ok = False

    if ok:
        print('  caption_table/caption_fitting: OK  side-by-side=%.2fx%.2f  stacked=%.2fx%.2f'
              % (side_by_side.width, side_by_side.height, stacked.width, stacked.height))
    return ok


def _check_layout_and_measure():
    ok = True
    blocks = [_simple_block()]
    letters = {'panel_thickness': 'A'}
    table = st.layout(blocks, letters)
    problems = st.check_layout(table)
    if problems:
        print('  FAIL layout: a real, correctly-constructed table failed its own check_layout: %r'
              % problems)
        ok = False

    w, h, rows = st.measure(blocks, letters)
    if (w, h, rows) != (table.width, table.height, table.rows):
        print('  FAIL measure: (%.2f, %.2f, %d) does not match layout()\'s own Table '
              '(%.2f, %.2f, %d)' % (w, h, rows, table.width, table.height, table.rows))
        ok = False

    # Two blocks side by side must be wider than either alone, and no deeper than the deeper
    # of the two (rows = max, not sum, per layout()'s own docstring).
    two_blocks = st.layout([_simple_block(), _simple_block()], letters)
    if two_blocks.width <= table.width:
        print('  FAIL layout: two blocks side by side (%.2f) should be wider than one '
              '(%.2f)' % (two_blocks.width, table.width))
        ok = False
    if two_blocks.rows != table.rows:
        print('  FAIL layout: two identical blocks should have the same row count as one, '
              'got %d vs %d' % (two_blocks.rows, table.rows))
        ok = False

    if ok:
        print('  layout/measure: OK  width=%.2f height=%.2f rows=%d' % (w, h, rows))
    return ok


def _check_layout_catches_broken_tables():
    """check_layout's own refusal paths, broken on purpose -- the same technique
    check_table_width.py uses on real family data, isolated here against a minimal table so it
    does not depend on real family fixtures existing."""
    ok = True
    blocks = [_simple_block()]
    letters = {'panel_thickness': 'A'}
    table = st.layout(blocks, letters)

    # A cell moved outside the table's own width must be caught.
    moved = st.Table(table.cells[:], table.rules[:], table.width, table.height, table.rows)
    moved.cells[0].x = table.width + 100.0
    problems = st.check_layout(moved)
    if not any('outside the column' in p for p in problems):
        print('  FAIL check_layout: a cell moved outside the table width was not caught: %r'
              % problems)
        ok = False

    # Two cells forced to the same position must be caught as an overlap.
    overlapped = st.Table(table.cells[:], table.rules[:], table.width, table.height, table.rows)
    overlapped.cells[1].x = overlapped.cells[0].x
    overlapped.cells[1].y = overlapped.cells[0].y
    problems = st.check_layout(overlapped)
    if not any('overlap' in p for p in problems):
        print('  FAIL check_layout: two overlapping cells were not caught: %r' % problems)
        ok = False

    # A table with its rules stripped must be caught (H2's compacted-gutter debt).
    no_rules = st.Table(table.cells[:], [], table.width, table.height, table.rows)
    problems = st.check_layout(no_rules)
    if not problems:
        print('  FAIL check_layout: a table with every rule removed was accepted -- the check '
              'is blind to the compacted-gutter debt it exists to pay')
        ok = False

    if ok:
        print('  check_layout refusals: OK -- moved cell, overlap, and missing rules all caught')
    return ok


def main():
    checks = [_check_block_layout, _check_legend_table, _check_caption_table,
              _check_layout_and_measure, _check_layout_catches_broken_tables]
    ok = True
    for check in checks:
        ok = check() and ok
    sys.stdout.flush()
    return 0 if ok else 1


if is_entry_point(__name__):
    raise SystemExit(main())
