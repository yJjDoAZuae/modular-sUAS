# -*- coding: utf-8 -*-
"""IP-FC-131: the file-naming convention a multi-sheet drawing exports under.

`drawing.build_sheets` can put more than one page in a document -- a bulkhead's plan and its
corner detail no longer share a frame, so they are two pages of one drawing (see
`drawing.BuiltSheet`). Three other modules need to agree on what each page is called on disk,
and none of them can import the other two: `build_sheet.py` and `render_pages.py` run inside
FreeCAD and write the files, `draw_set.py` runs in the tools virtualenv and only has to name
them again to clear stale ones before a rebuild. This module has no FreeCAD import, so all
three can import it.

**The convention: sheet 1 is `stem`, sheet N>1 is `stem-sheetN`.** Sheet 1 keeps the bare name
so a single-page drawing -- every corner sheet, so far -- exports exactly as it always has,
and nothing that already reads `key.pdf` off disk has to change. A second sheet needs a name
that cannot collide with a first: `-sheetN` is not a character sequence any family key
produces (keys are `kind-type-hash`), so `glob(stem + '-sheet*')` cannot pick up a different
family's files by accident the way a bare numeric suffix might.
"""
import re

#: `Page` -> 1, `Page2` -> 2, ... -- the numbering `drawing.add_page` gives its pages.
_PAGE_NUMBER = re.compile(r'^Page(\d*)$')


def sheet_stem(stem, number):
    """The export stem for sheet `number` (1-based) of a drawing based at `stem`."""
    return stem if number <= 1 else '%s-sheet%d' % (stem, number)


def page_number(page_name):
    """The sheet number `drawing.add_page` gave a page, from its object name.

    Raises `ValueError` on a name this convention did not produce -- a page object that is
    not one of `build_sheets`' own is a sign the document is not what this code expects,
    and guessing a number for it would misname its export.
    """
    match = _PAGE_NUMBER.match(page_name)
    if not match:
        raise ValueError('%r is not a page name build_sheets produces' % (page_name,))
    return int(match.group(1)) if match.group(1) else 1


def sheet_glob(stem):
    """Every suffix pattern that could name a sheet of this drawing, first sheet first."""
    return [stem, stem + '-sheet*']
