"""IP-FC-86: the sheet template, generated from the geometry that decided its size.

OQ-DES-D5 decided on 2026-08-22 that the sheet gets a title block of this project's own. The
reason is measured rather than aesthetic: the stock ASME block is 146.66 x 48.074 mm = 7 051
mm2, which is **63 % of everything on an ANSI A frame that is not the drawn view**, and it
binds the layout twice. Its *depth* caps the view at 74.3 % of the frame with no value table on
the sheet at all, so the 75 % requirement is unreachable on the stock template whatever the
table does. Its *width* leaves 91.9 mm beside it where the compacted table is 95.1,
which forces the table to stack above it and drops the view to 38.4 %.

**The block is generated rather than drawn by hand because its size is a derivation.** The
envelope is `drawing_standard.title_block_envelope`, and the block has to fit inside it or the
requirement fails; writing the SVG by hand would put a number in a file with nothing tying it
to the reason for the number. `verify_template` then re-reads what this wrote and refuses on
disagreement, the same way `verify_font` does for the font metrics -- so the sheet is pinned by
measurement at both ends.

**The frame is deliberately unchanged from the stock template.** Every figure already pinned in
`drawing_standard` and measured in `check_table_width` is against that frame, and changing two
things at once when one of them is the thing under test is how a measurement stops meaning
anything. What changes is the title block, which is what OQ-DES-D5 decided.

**What the block states that the stock one cannot.** The sheet's units. Cells in a value table
are bare numbers, annotations are bare numbers, and the stock ASME template has no field for a
unit anywhere -- a drawing whose numbers are millimeters and does not say so is wrong in a way
no amount of layout work reaches. It is written as **fixed text rather than an
editable field**, because an editable field can be edited to blank and the whole point is
that the statement cannot go missing.

Run:

    python make_sheet_template.py                # writes the template
    python make_sheet_template.py --check        # writes nowhere, reports what it would write

**Unit regime: millimeters.** The SVG's user unit is the millimeter and its `width` says so,
which `verify_template` checks rather than assumes -- a template authored at another scale
would report a frame of plausible numbers in the wrong unit.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'freecad'))

import drawing_standard as ds

NL = chr(10)

OUT_RELPATH = ('templates', 'fuselage_ansi_a_landscape.svg')

# The sheet, unchanged from the stock ANSI A landscape template.
SHEET_MM = (279.4, 215.9)
FRAME_MM = (20.107, 14.473, 239.52, 187.2)

# The title block, inside the envelope OQ-DES-D5's decision produces. 130 x 46 rather than the
# 143.4 x 46.8 the envelope allows, because the envelope is a *limit* and spending all of it
# would leave the value table 3.4 mm of margin -- one more dimension on the widest family and
# the sheet stops meeting the requirement. At 130 the table has 108.5 mm against the 95.1 it
# needs. The view gets 75.4 %, against the 75.7 % the envelope's own corner would give: a third
# of a percent of drawing for 13 mm of headroom.
BLOCK_MM = (130.0, 46.0)

# The widest value table any family prints, and its row count, from `check_table_width.py`
# -- which measures it by laying it out with `sheet_table.py`, so this is the width of the
# strings the sheet prints rather than of the strings the factoring produced. It was 104.0
# until 2026-08-27, measured before the renderer uppercased its cells.
# The block has to leave room beside it, so the generator refuses rather than emitting a
# template that cannot carry the drawing set it is for.
TABLE_MM = (105.8, 10)

# Row depths, top to bottom, summing to the block's. The title row is deeper because it holds
# the one field a reader looks for from across a bench.
#
# **They were 12.0 and 8.5 x 4 until 2026-08-27, and an 8.5 mm row could not hold its own
# contents.** A 2.5 mm caption and a 3.5 mm value at a 1.6 mm pad put the value's cap height
# 0.7 mm *above* the caption's baseline -- they overlapped, on every field of every sheet, and
# nothing would have reported it because a title block is drawn by the template rather than
# placed by the solver. `check_rows` below is the refusal that would have caught it.
ROWS_MM = (10.0, 9.0, 9.0, 9.0, 9.0)

# Text sizes. The value height is the drawing standard's pinned 3.5 mm; the caption is the
# 2.5 mm the value table sets at, which is the next size down in ISO 3098's preferred series
# rather than a fraction chosen to fit. Captions are smaller than values on every title block
# ever drawn, and for the reason the standard has a series: the caption is read once and the
# value every time.
VALUE_MM = ds.TEXT_HEIGHT_MM
CAPTION_MM = ds.TABLE_TEXT_HEIGHT_MM

# The clear space above a caption and below a value, inside its cell.
PAD_MM = 0.8

# Baseline to baseline, caption to value, as a multiple of the **larger** of the two heights --
# ISO 3098's minimum line spacing for type B lettering, which is the rule the note line pitch
# and the table row pitch both follow. A caption and its field are not running text and a
# tighter setting would be defensible, but having the sheet obey one rule everywhere is worth
# more than the two millimeters an exception would save.
LINE_SPACING_HEIGHTS = 1.4

LINE_MM = 0.35
FRAME_LINE_MM = 0.7

# The fixed statement this template exists to make.
UNITS_TEXT = 'DIMENSIONS IN MILLIMETERS'


def cells():
    """The block's cells, as (row, x offset, width, caption, field, default).

    `field` None makes the cell fixed text -- the caption is the whole of it. Everything else
    becomes a `freecad:editable`, which is what TechDraw fills in from the document.
    """
    w = BLOCK_MM[0]
    return [
        (0, 0.0, w, 'DRAWING TITLE', 'DrawingTitle', 'PART TITLE'),

        (1, 0.0, w * 0.55, 'PART NUMBER', 'PartNumber', '--'),
        (1, w * 0.55, w * 0.18, 'REV', 'Revision', '--'),
        (1, w * 0.73, w * 0.27, 'SHEET', 'Sheet', '1 OF 1'),

        (2, 0.0, w * 0.55, 'MATERIAL', 'Material', '--'),
        (2, w * 0.55, w * 0.45, 'PROCESS', 'Process', '--'),

        (3, 0.0, w * 0.55, UNITS_TEXT, None, None),
        (3, w * 0.55, w * 0.18, 'SCALE', 'Scale', '1:1'),
        (3, w * 0.73, w * 0.27, 'SIZE', 'Size', 'ANSI A'),

        (4, 0.0, w * 0.55, 'DRAWN BY', 'DrawnBy', '--'),
        (4, w * 0.55, w * 0.45, 'DATE', 'Date', '--'),
    ]


def block_origin():
    """The block's top left corner, in template coordinates."""
    frame_x, frame_y, frame_w, frame_h = FRAME_MM
    return (frame_x + frame_w - BLOCK_MM[0], frame_y + frame_h - BLOCK_MM[1])


def row_top(index):
    return block_origin()[1] + sum(ROWS_MM[:index])


def caption_baseline(top):
    return top + PAD_MM + CAPTION_MM


def value_baseline(top):
    return caption_baseline(top) + LINE_SPACING_HEIGHTS * max(CAPTION_MM, VALUE_MM)


def check_rows():
    """Refuse a row that cannot hold a caption above a value. Returns complaints.

    The failure this exists for leaves no trace: a title block is drawn by the template rather
    than placed by the solver, so text that overlaps inside a cell is not something any
    placement check ever sees. It renders, it exports, it prints with two strings on top of
    each other.
    """
    problems = []
    if abs(sum(ROWS_MM) - BLOCK_MM[1]) > 1e-9:
        problems.append('the rows sum to %.3f mm, not the block\'s %.3f'
                        % (sum(ROWS_MM), BLOCK_MM[1]))
    for index, height in enumerate(ROWS_MM):
        needed = value_baseline(0.0) + PAD_MM
        if needed > height + 1e-9:
            problems.append(
                'row %d is %.2f mm and needs %.2f: a %.1f mm caption over a %.1f mm value at '
                '%.1f h line spacing does not fit in it'
                % (index, height, needed, CAPTION_MM, VALUE_MM, LINE_SPACING_HEIGHTS))
    return problems


def rect(x, y, w, h, element_id=None, width_mm=LINE_MM):
    ident = ' id="%s"' % element_id if element_id else ''
    return ('<rect%s x="%.4f" y="%.4f" width="%.4f" height="%.4f" fill="none" '
            'stroke="#000000" stroke-width="%.3f"/>' % (ident, x, y, w, h, width_mm))


def text(x, y, size, content, field=None, weight='normal'):
    """One text element, editable when `field` is given.

    TechDraw finds a template's fields by the `freecad:editable` attribute and replaces the
    inner tspan's content, so both have to be present -- an editable `<text>` with no tspan is
    not filled in.
    """
    editable = ' freecad:editable="%s"' % field if field else ''
    return ('<text x="%.4f" y="%.4f" font-family="osifont, sans-serif" font-size="%.4fpx" '
            'font-weight="%s" fill="#000000" stroke="none"%s>'
            '<tspan x="%.4f" y="%.4f">%s</tspan></text>'
            % (x, y, size, weight, editable, x, y, content))


def build():
    """The template, as SVG source."""
    sheet_w, sheet_h = SHEET_MM
    frame_x, frame_y, frame_w, frame_h = FRAME_MM
    block_x, block_y = block_origin()
    block_w, block_h = BLOCK_MM

    body = [rect(frame_x, frame_y, frame_w, frame_h,
                 ds.TEMPLATE_FRAME_ID, FRAME_LINE_MM),
            rect(block_x, block_y, block_w, block_h,
                 ds.TEMPLATE_TITLE_BLOCK_ID, FRAME_LINE_MM)]

    # The rules between rows. The block's own outline is drawn above, so these are interior.
    for index in range(1, len(ROWS_MM)):
        y = row_top(index)
        body.append('<line x1="%.4f" y1="%.4f" x2="%.4f" y2="%.4f" stroke="#000000" '
                    'stroke-width="%.3f"/>' % (block_x, y, block_x + block_w, y, LINE_MM))

    for row, offset, width, caption, field, default in cells():
        x = block_x + offset
        top = row_top(row)
        height = ROWS_MM[row]

        # The vertical rule to the left of every cell that is not the first in its row.
        if offset > 0.0:
            body.append('<line x1="%.4f" y1="%.4f" x2="%.4f" y2="%.4f" stroke="#000000" '
                        'stroke-width="%.3f"/>'
                        % (x, top, x, top + height, LINE_MM))

        if field is None:
            # A fixed statement, centred in its cell rather than captioned -- it is not a
            # label for something else, it is the thing itself.
            body.append(text(x + PAD_MM, top + height / 2.0 + VALUE_MM * 0.35,
                             VALUE_MM, caption, None, 'bold'))
            continue

        body.append(text(x + PAD_MM, caption_baseline(top), CAPTION_MM, caption))
        body.append(text(x + PAD_MM, value_baseline(top), VALUE_MM, default, field))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>' + NL
        + '<!-- Generated by src/Fuselage/tools/make_sheet_template.py for IP-FC-86.' + NL
        + '     Do not edit by hand: the block size is derived from OQ-DES-D5 and' + NL
        + '     re-asserted by drawing_standard.verify_template. -->' + NL
        + '<svg xmlns="http://www.w3.org/2000/svg" '
          'xmlns:freecad="https://www.freecad.org/wiki/index.php?title=Svg_Namespace" '
          'width="%gmm" height="%gmm" viewBox="0 0 %g %g">' % (sheet_w, sheet_h,
                                                               sheet_w, sheet_h) + NL
        + NL.join('  ' + element for element in body) + NL
        + '</svg>' + NL)


def out_path():
    return os.path.join(os.path.dirname(HERE), 'freecad', *OUT_RELPATH)


def main(argv):
    envelope = ds.title_block_envelope(TABLE_MM[0], ds.table_height_mm(TABLE_MM[1]))
    if envelope is None:
        raise SystemExit('the compacted table is deeper than the band may be, so no title '
                         'block reaches the required view share')
    if BLOCK_MM[0] > envelope[0] or BLOCK_MM[1] > envelope[1]:
        raise SystemExit(
            'the title block is %.1f x %.1f mm, outside the %.1f x %.1f envelope OQ-DES-D5 '
            'requires -- the view would not reach %.0f%% of the frame'
            % (BLOCK_MM[0], BLOCK_MM[1], envelope[0], envelope[1], 100.0 * ds.VIEW_SHARE))

    problems = check_rows()
    if problems:
        raise SystemExit('the title block\'s rows do not hold their text:' + NL
                         + NL.join('  - ' + problem for problem in problems))

    source = build()
    path = out_path()
    print('title block  %.1f x %.1f mm, inside the %.1f x %.1f envelope'
          % (BLOCK_MM[0], BLOCK_MM[1], envelope[0], envelope[1]))
    view = ds.best_view(TABLE_MM[0], ds.table_height_mm(TABLE_MM[1]), *BLOCK_MM)
    print('view         %.1f%% of the frame, placed as a %s'
          % (100.0 * view[3] / (FRAME_MM[2] * FRAME_MM[3]), view[0]))
    print('table beside %.1f mm, against the %.1f the widest family needs'
          % (FRAME_MM[2] - BLOCK_MM[0] - ds.TABLE_COLUMN_GUTTER_MM, TABLE_MM[0]))

    if '--check' in argv:
        print('would write %d bytes to %s' % (len(source), path))
        return 0

    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, 'w', encoding='utf-8', newline=NL) as handle:
        handle.write(source)
    print('wrote %s' % path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
