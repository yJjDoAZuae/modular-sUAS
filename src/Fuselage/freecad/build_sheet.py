"""IP-FC-114: build one family sheet and write it, as `build_part.py` does for a part.

    freecadcmd build_sheet.py --pass params.json --pass families.json --pass kind=corner \\
        --pass key=corner-corner-7faa02 --pass out=C:/path/without/extension

**Why this exists next to `check_drawing.py` rather than inside it.** `drawing.py` can build a
sheet and `drawing_families.py` says which sheets the set needs, and until now the only thing
joining them was a *checker* -- `check_drawing.py` builds one sheet, for one kind, from one
variant, and exports it under its own name as evidence for its own assertions. So the artefact
a reader would actually ask for existed only as a by-product. This is the builder half, with no
assertions in it: it takes a family and writes its sheet.

**It is handed the family key and then re-derives the family anyway.** The driver knows which
family it wants a sheet of, so it says so -- but a sheet drawn against the wrong family gets a
value table of columns the part has no dimensions for, every number in it plausible and none of
them about this part. That is the failure `check_drawing.family_of` was written to prevent, so
the same function runs here on the parameters actually loaded, and a disagreement is a refusal
rather than a sheet. Being told which family and working out which family are two different
claims, and this writes a sheet only when they agree.

**Two artefacts here, and two more from the renderer.** The `.FCStd` is the sheet itself and
loses nothing; it is the artefact of record, and it is one file even when the drawing is more
than one page -- `drawing.build_sheets` puts every sheet of one drawing in one document, so a
bulkhead's plan and its corner detail are `Page` and `Page2` of the same `.FCStd`, not two
documents. The `.dxf` is for a reader with a CAD program, and **TechDraw's DXF export is
per-page**, so a multi-sheet drawing writes one `.dxf` per page, named by `sheet_naming`. It is
also lossy: it drops all but the first line of a multi-line annotation and drops symbols
(IP-FC-33), so it is written but never relied on. The `.svg` and `.pdf` -- a picture of each
sheet as TechDraw draws it, which is what a person reviewing the set actually looks at -- are
written afterwards by `tools/render_sheets.py`, because rendering a page needs Qt and this
process is `freecadcmd`, which has none. See `render_pages.py`, which renders every page of the
document the same way this writes a `.dxf` for each.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import check_drawing
import dimension_placement as dp
import drawing
import sheet_annotations
import sheet_naming
from corner_common import is_entry_point, script_args


def _opt(name, default=None):
    for arg in sys.argv:
        for prefix in ('--%s=' % name, '%s=' % name):
            if arg.startswith(prefix):
                return arg.split('=', 1)[1]
    if default is None:
        raise SystemExit('missing %s=' % name)
    return default


def export(sheets, stem):
    """Write what this process can write. Returns the paths actually written.

    The `.FCStd` is the sheet -- one file for the whole drawing, however many pages
    `build_sheets` gave it -- and the `.dxf` is a lossy convenience, one per page since DXF has
    no notion of a multi-page document. A failure of a `.dxf` is reported and skipped rather
    than losing the `.FCStd`.

    **What is deliberately not written here is the picture of the sheet.** Rendering a
    TechDraw page needs TechDraw's renderer, which is Qt, which `freecadcmd` does not have --
    asking for it here raises *"Cannot load Gui module in console application"*. I once read
    that as FreeCAD 1.1 having no headless page export and wrote a compositor of my own to
    work around it; it drew geometry and annotation positions and silently dropped arrowheads,
    dimension text, line weights, the value table and the symbols. The message is about this
    executable, not about FreeCAD: `freecad.exe` from the same install renders the page fully
    with no display attached. `tools/render_sheets.py` does that, from the `.FCStd` this
    writes.
    """
    import TechDraw

    written = []
    doc = sheets[0].page.Document
    doc.saveAs(stem + '.FCStd')
    written.append(stem + '.FCStd')

    for sheet in sheets:
        dxf_stem = sheet_naming.sheet_stem(stem, sheet.number)
        try:
            TechDraw.writeDXFPage(sheet.page, dxf_stem + '.dxf')
            written.append(dxf_stem + '.dxf')
        except Exception as exc:                                        # noqa: BLE001
            print('  %s.dxf  not written: %s: %s'
                  % (os.path.basename(dxf_stem), type(exc).__name__, exc))
    return written


def main():
    argv = script_args()
    paths = [a for a in argv if a.endswith('.json')]
    if len(paths) < 2:
        print('usage: build_sheet.py --pass params.json --pass families.json '
              '--pass kind=KIND --pass key=FAMILY_KEY --pass out=STEM')
        return 2
    params_path, families_path = paths[0], paths[1]
    kind = _opt('kind')
    key = _opt('key')
    stem = _opt('out')

    if kind not in sheet_annotations.ANNOTATIONS:
        print('no annotation set for %r -- have %s'
              % (kind, ', '.join(sorted(sheet_annotations.ANNOTATIONS))))
        return 2

    with open(params_path, encoding='utf-8') as handle:
        exported = json.load(handle)
    params = exported[check_drawing.PARAMS_KEY[kind]]

    with open(families_path, encoding='utf-8') as handle:
        document = json.load(handle)

    named = [f for f in document['families'] if f['key'] == key]
    if not named:
        print('no family keyed %r in %s' % (key, families_path))
        return 2
    family = named[0]

    # Told which, and worked out which. Both, because they can disagree.
    derived = check_drawing.family_of(
        document, kind, params, (exported.get('variant') or {}).get('bulkhead_type_name'))
    if derived is None or derived['key'] != family['key']:
        print('REFUSED: asked for %s, but these parameters belong to %s. A sheet drawn '
              'against the wrong family carries a table of columns this part has no '
              'dimensions for.'
              % (key, derived['key'] if derived else 'no family of this kind'))
        return 1

    doc = App.newDocument('sheet_' + key.replace('-', '_'))
    try:
        sheets = drawing.build_sheets(
            doc, kind, params_path, params, family,
            variant=exported.get('variant'),
            siblings=[f for f in document['families'] if f.get('kind') == kind],
            say=print)
    except dp.PlacementError as exc:
        # Section 5.6: an unplaceable sheet is a drafting decision to be made deliberately,
        # and a traceback is a worse way to say so than the refusal's own words.
        #
        # **All of the words, not the first line.** These refusals carry the measurement --
        # what the table needs, what the band has, and by how much it misses -- and printing
        # only the headline threw exactly the part a person needs to decide what to do about
        # it, leaving a reader to rerun the build by hand to see the numbers.
        lines = str(exc).split(chr(10))
        print('REFUSED: %s' % lines[0])
        for line in lines[1:]:
            print('    %s' % line if line.strip() else '')
        return 1

    folder = os.path.dirname(os.path.abspath(stem))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    written = export(sheets, stem)

    for sheet in sheets:
        layout = sheet.view.layout
        scale = sheet.view.scale
        print('  %-42s %2d dimensions, %2d note(s), scale %s'
              % ('%s (sheet %d of %d)' % (key, sheet.number, len(sheets))
                 if len(sheets) > 1 else key,
                 len(layout), len(layout.notes),
                 '%g:1' % scale if scale >= 1.0 else '1:%g' % (1.0 / scale)))
    for path in written:
        print('    %s' % path)
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
