"""IP-TEST-11: the font-measurement half of drawing_standard.py, which the pytest tier cannot
reach -- `text_width_mm`/`verify_font`/`typo_ascender_units`/`measure_advances` all need
`fontTools`, which is present in FreeCAD's own Python (this module's own docstring) and is not
a project dependency, so it is absent from the venv (confirmed: `uv run python -c "import
fontTools"` fails). See `tests/test_drawing_standard.py` for the pure layout/formatting
functions, which need neither FreeCAD nor a real font file.

Runs against the real, installed osifont -- `require_standard()`'s own real check -- and the
real committed template, the same artifacts every real drawing build is pinned to.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_standard as ds
from corner_common import is_entry_point


def _check_measure_advances():
    ok = True
    path = ds.font_path()
    advances, units_per_em = ds.measure_advances(path, 'AW1')
    if units_per_em != ds.UNITS_PER_EM:
        print('  FAIL measure_advances: unitsPerEm=%d, want %d' % (units_per_em, ds.UNITS_PER_EM))
        ok = False
    if advances.get('W') != ds.WIDEST_CALLOUT_UNITS:
        print('  FAIL measure_advances: W=%r, want %d' % (advances.get('W'), ds.WIDEST_CALLOUT_UNITS))
        ok = False
    if advances.get('1') != 700:
        # Cited directly in the module's own docstring: "'1' is 700 units".
        print('  FAIL measure_advances: 1=%r, want 700 (module docstring)' % (advances.get('1'),))
        ok = False

    try:
        ds.measure_advances(path, chr(0x1F600))  # an emoji: definitely not in a drawing font
        print('  FAIL measure_advances: a missing glyph did not raise')
        ok = False
    except ValueError as exc:
        if 'no glyph' not in str(exc):
            print('  FAIL measure_advances: wrong error message %r' % str(exc))
            ok = False

    if ok:
        print('  measure_advances: OK')
    return ok


def _check_typo_ascender_units():
    ok = True
    got = ds.typo_ascender_units(ds.font_path())
    if got != ds.TYPO_ASCENDER_UNITS:
        print('  FAIL typo_ascender_units: %d, want %d' % (got, ds.TYPO_ASCENDER_UNITS))
        ok = False
    if ok:
        print('  typo_ascender_units: OK (%d)' % got)
    return ok


def _check_text_width_mm():
    ok = True
    # A single 'W' at the pinned text height must equal callout_width_mm exactly -- they are
    # the same quantity measured two ways (a lookup table vs. a live font read).
    got = ds.text_width_mm('W', ds.TEXT_HEIGHT_MM)
    want = ds.callout_width_mm(ds.TEXT_HEIGHT_MM)
    if abs(got - want) > 1e-9:
        print('  FAIL text_width_mm(\'W\') = %.6f, callout_width_mm() = %.6f -- should be '
              'identical' % (got, want))
        ok = False

    # A wider string measures wider, and repeated characters are additive (no kerning on
    # digits, per the function's own docstring).
    one_digit = ds.text_width_mm('1', ds.TEXT_HEIGHT_MM)
    two_digits = ds.text_width_mm('11', ds.TEXT_HEIGHT_MM)
    if abs(two_digits - 2.0 * one_digit) > 1e-9:
        print('  FAIL text_width_mm: \'11\' = %.6f, expected exactly 2x \'1\' (%.6f) -- no '
              'kerning should apply' % (two_digits, one_digit))
        ok = False

    if ok:
        print('  text_width_mm: OK  W=%.4f mm  1=%.4f mm' % (got, one_digit))
    return ok


def _check_column_width_mm():
    ok = True
    # A column of short digit strings must be at least as wide as the callout floor (every
    # column's own documented lower bound), and must grow to fit a wider heading.
    narrow = ds.column_width_mm(['1', '2', '3'])
    with_heading = ds.column_width_mm(['1', '2', '3', 'A_WIDE_HEADING'])
    # column_width_mm defaults its height to TABLE_TEXT_HEIGHT_MM, not TEXT_HEIGHT_MM -- the
    # floor must use the same height callout_width_mm() was actually measured at inside it.
    floor = (ds.callout_width_mm(ds.TABLE_TEXT_HEIGHT_MM)
             + 2.0 * ds.TABLE_COLUMN_PADDING_HEIGHTS * ds.TABLE_TEXT_HEIGHT_MM)
    if narrow < floor - 1e-9:
        print('  FAIL column_width_mm: %.4f is under its own callout-letter floor %.4f'
              % (narrow, floor))
        ok = False
    if with_heading <= narrow:
        print('  FAIL column_width_mm: adding a wide heading did not widen the column '
              '(%.4f vs %.4f)' % (with_heading, narrow))
        ok = False
    if ok:
        print('  column_width_mm: OK  narrow=%.4f  with_heading=%.4f' % (narrow, with_heading))
    return ok


def _check_verify_font():
    ok = True
    problems = ds.verify_font()
    if problems:
        print('  FAIL verify_font: the pinned font metrics do not hold against the real '
              'installed font:')
        for p in problems:
            print('    - %s' % p)
        ok = False
    else:
        print('  verify_font: OK -- the pin holds against the real installed osifont')

    missing = ds.verify_font(os.path.join(os.path.dirname(ds.font_path()), 'not_a_real_font.ttf'))
    if not missing or 'not at' not in missing[0]:
        print('  FAIL verify_font: a missing font file did not report cleanly, got %r' % missing)
        ok = False
    else:
        print('  verify_font on a missing file: OK')
    return ok


def _check_require_standard():
    ok = True
    try:
        ds.require_standard()
    except ValueError as exc:
        print('  FAIL require_standard: raised against the real, pinned font and template -- '
              '%s' % exc)
        ok = False
    if ok:
        print('  require_standard: OK -- real font and template both hold')
    return ok


def main():
    checks = [_check_measure_advances, _check_typo_ascender_units, _check_text_width_mm,
              _check_column_width_mm, _check_verify_font, _check_require_standard]
    ok = True
    for check in checks:
        ok = check() and ok
    sys.stdout.flush()
    return 0 if ok else 1


if is_entry_point(__name__):
    raise SystemExit(main())
