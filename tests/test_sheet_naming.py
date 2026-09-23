"""IP-TEST-4 (doc/implementation/test_coverage.md): tests for freecad/sheet_naming.py.

Lives under src/Fuselage/freecad/ by location, but -- per its own module docstring -- has no
FreeCAD import specifically so the venv-side draw_set.py can import it too, alongside the
two FreeCAD-side modules that also use it (build_sheet.py, render_pages.py). Pure string/regex
logic, fully testable from the pytest tier despite its directory.

Adoption-phase retrofit (general.md's TDD section).
"""
import sys
from pathlib import Path

import pytest

_FREECAD_DIR = str(Path(__file__).resolve().parent.parent / 'src' / 'Fuselage' / 'freecad')
if _FREECAD_DIR not in sys.path:
    sys.path.insert(0, _FREECAD_DIR)

import sheet_naming as sn  # noqa: E402


def test_sheet_stem_keeps_the_bare_name_for_the_first_sheet():
    assert sn.sheet_stem('corner-corner-7faa02', 1) == 'corner-corner-7faa02'


def test_sheet_stem_suffixes_later_sheets():
    assert sn.sheet_stem('corner-corner-7faa02', 2) == 'corner-corner-7faa02-sheet2'
    assert sn.sheet_stem('corner-corner-7faa02', 3) == 'corner-corner-7faa02-sheet3'


def test_page_number_reads_the_bare_page_as_sheet_one():
    assert sn.page_number('Page') == 1


def test_page_number_reads_a_numbered_page():
    assert sn.page_number('Page2') == 2
    assert sn.page_number('Page17') == 17


def test_page_number_rejects_a_name_the_convention_did_not_produce():
    with pytest.raises(ValueError):
        sn.page_number('NotAPage')
    with pytest.raises(ValueError):
        sn.page_number('page2')  # case-sensitive: drawing.add_page always capitalizes


def test_sheet_glob_lists_the_first_sheet_bare_and_later_ones_wildcarded():
    assert sn.sheet_glob('corner-corner-7faa02') == [
        'corner-corner-7faa02', 'corner-corner-7faa02-sheet*']
