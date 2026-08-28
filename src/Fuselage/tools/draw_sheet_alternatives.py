"""IP-FC-21: OQ-DES-D5's layouts, drawn on the frame they have to fit.

The requirement is that **the drawn view takes at least 75 % of the frame**, and the answer
is a set of rectangles: a title block, a value table, and whatever rectangle is left for the
view.
Rectangles are not judgeable as numbers. A reader deciding how the sheet is laid out has to see
the view they would get, at the size they would get it, with the table and the title block
sitting where they would sit.

**Everything drawn here is measured.** Column widths come from the pinned drawing font through
`check_table_width.py`, the frame and title block are read out of the installed ASME templates
by element id, and the view's share is the largest rectangle left once both are placed --
computed, not eyeballed, because a view is a projection with a bounding box and its share is a
packing result rather than an area subtraction.

    freecadcmd check_table_width.py --pass families.json sheets.json
    python draw_sheet_alternatives.py sheets.json out.html

The running example is the **panelled corner**, which is both the family OQ-DES-D1 was decided
on and the largest table of the thirteen.

**Unit regime: millimeters**, which is what a page is measured in.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'freecad'))

# The packing is the sheet's own rule and there is one copy of it. This module ran with its
# own for a few hours and the two disagreed on the gap between the table and the title block
# -- 37.3 % against 38.4 % for the same layout -- which is exactly the class of drift a
# diagram is least able to reveal, since both numbers look plausible on the page.
import drawing_standard as ds                                          # noqa: E402

TEMPLATE = os.path.join(HERE, 'sheet_alternatives', 'template.html')

NL = chr(10)

# Millimeters to page pixels. One number for every sheet on the page, so an ANSI B frame is
# drawn 1.6 times an ANSI A one and the reader sees the difference rather than reading it.
PX_PER_MM = 1.55

# Title blocks of our own, as OQ-DES-D5's alternative 2 sizes them. Not a proposal for what one
# contains -- that is the drafting decision the question puts to the reader -- but the
# rectangles the measurements were taken at, so the drawing and the numbers agree.
OWN_BLOCK_MM = (120.0, 40.0)
SMALL_BLOCK_MM = (100.0, 32.0)

# What to draw. Each is (label, ladder rung, title block or None for stock, row pitch override,
# larger sheet, heading, blurb).
SCENES = (
    ('0', 'as built', None, None, False,
     'Before compaction',
     'The layout as the factoring left it: a 2 h row pitch, one text height between columns, '
     'two decimals on every value, blocks stacked one above the other.'),
    ('1', 'blocks packed abreast', None, None, False,
     'Compacted, stock title block',
     'The same values in under a third of the area. The table is now 3.2 mm too wide to sit '
     'beside the stock title block, so it has to stack above it and the view is squeezed into '
     'the column that is left.'),
    ('2', 'blocks packed abreast', OWN_BLOCK_MM, None, False,
     'Compacted, our own title block',
     'A 120 x 40 block. The table sits beside it in a 45.5 mm band and the view takes the '
     'full width above.'),
    ('2b', 'blocks packed abreast', SMALL_BLOCK_MM, None, False,
     'Compacted, a smaller block still',
     'A 100 x 32 block changes nothing. Past the point where the block is shallower than the '
     'table, the band depth is the table, and shrinking the block further buys none of it '
     'back.'),
    ('5', 'blocks packed abreast', None, None, True,
     'Compacted, on ANSI B',
     'The frame grows and the stock title block does not, so its depth costs proportionally '
     'less and the table fits beside it with room over.'),
)


def esc(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def rect(x, y, w, h, cls):
    return ('<rect class="%s" x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>'
            % (cls, x, y, max(w, 0.0), max(h, 0.0)))


def line(x1, y1, x2, y2, cls):
    return ('<line class="%s" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            % (cls, x1, y1, x2, y2))


def label(x, y, text, cls, anchor='start'):
    return ('<text class="%s" x="%.2f" y="%.2f" text-anchor="%s">%s</text>'
            % (cls, x, y, anchor, esc(text)))


def table_rect(layout, pitch_heights, text_height_mm):
    """The table's rectangle, with the row pitch overridden where the scene asks for one.

    Only the pitch is re-derived. The column widths came out of the font measurement and are
    not the drawing's to recompute -- a diagram that recalculates its own evidence is not
    evidence of anything.
    """
    pitch = layout['pitch'] if pitch_heights is None else pitch_heights * text_height_mm
    return layout['width'], layout['rows'] * pitch, pitch


def draw_table(blocks, left, top, pitch, gutter, packed):
    """The table as it would print, from its top left corner."""
    out = []
    x, y = left, top
    for block in blocks:
        widths = block['column_widths']
        rows = block['rows']
        cursor = x
        for width in widths:
            out.append(rect(cursor, y, width, rows * pitch, 'tcol'))
            cursor += width + gutter
        for row in range(1, rows):
            out.append(line(x, y + row * pitch, cursor - gutter, y + row * pitch, 'trow'))
        if packed:
            x = cursor + gutter
        else:
            y += rows * pitch
    return out


def sheet(scene, sheet_data, layout, text_height_mm):
    """One scene, drawn at true proportion on the frame it has to fit."""
    _number, _rung, block_mm, pitch_heights, _larger, _title, _blurb = scene
    template_w, template_h = sheet_data['template_mm']
    fx, fy, fw, fh = sheet_data['frame_mm']
    stock = sheet_data['title_block_mm']
    block_w, block_h = block_mm if block_mm else (stock[2], stock[3])

    gutter = layout['gutter']
    table_w, table_h, pitch = table_rect(layout, pitch_heights, text_height_mm)
    name, view_w, view_h, view_area, depth, column = ds.best_view(
        table_w, table_h, block_w, block_h, fw, fh)

    body = [rect(0, 0, template_w, template_h, 'paper'),
            rect(fx, fy, fw, fh, 'frame'),
            rect(fx, fy, view_w, view_h, 'viewbox'),
            rect(fx + fw - block_w, fy + fh - block_h, block_w, block_h, 'tblock')]

    # The room neither the view nor anything else can use. Drawn because the alternative is a
    # diagram that looks like it is wasting space for no reason: a view is a rectangle, so a
    # gap between the table and the title block is unreachable however large it is, and saying
    # so is the difference between evidence and an unanswered objection.
    if name == 'band':
        body += draw_table(layout['blocks'], fx, fy + fh - depth, pitch, gutter,
                           layout['packed'])
        waste = (fx + table_w + ds.TABLE_COLUMN_GUTTER_MM, fy + fh - depth,
                 fw - table_w - ds.TABLE_COLUMN_GUTTER_MM - block_w, depth)
    else:
        body += draw_table(layout['blocks'], fx + fw - column, fy, pitch, gutter,
                           layout['packed'])
        waste = (fx + fw - column, fy + table_h,
                 column, fh - table_h - block_h)
    if waste[2] > 1.0 and waste[3] > 1.0:
        body.append(rect(waste[0], waste[1], waste[2], waste[3], 'waste'))
        if waste[2] > 30.0 and waste[3] > 12.0:
            body.append(label(waste[0] + waste[2] / 2.0, waste[1] + waste[3] / 2.0 + 2.0,
                              'no rectangle reaches here', 'wlabel', 'middle'))

    share = 100.0 * view_area / (fw * fh)
    body.append(label(fx + view_w / 2.0, fy + view_h / 2.0 - 1.0,
                      'VIEW  %.1f%%' % share, 'vlabel', 'middle'))
    body.append(label(fx + view_w / 2.0, fy + view_h / 2.0 + 7.0,
                      '%.0f x %.0f mm' % (view_w, view_h), 'vnum', 'middle'))

    art = ('<svg viewBox="0 0 %.2f %.2f" role="img" aria-label="%s" '
           'preserveAspectRatio="xMidYMin meet">%s</svg>'
           % (template_w, template_h,
              esc('the view gets %.1f percent of the frame' % share), NL.join(body)))
    return art, share, name, table_w, table_h


def build(data, out_path, template_path):
    corner = [f for f in data['families'] if f['kind'] == 'corner']
    key = max(corner, key=lambda f: f['variants'])['key']
    text_height = data['text_height_mm']
    required = 100.0 * data['view_share']
    frame_area = data['frame_mm'][2] * data['frame_mm'][3]
    block_area = data['title_block_mm'][2] * data['title_block_mm'][3]

    ansi_a = {'template_mm': data['template_mm'], 'frame_mm': data['frame_mm'],
              'title_block_mm': data['title_block_mm']}
    ansi_b = data.get('larger_sheet')

    cards = []
    for scene in SCENES:
        number, rung, _block, _pitch, larger, title, blurb = scene
        sheet_data = ansi_b if larger else ansi_a
        if sheet_data is None:
            continue
        layout = data['layouts']['rung: ' + rung][key]
        art, share, placement, table_w, table_h = sheet(scene, sheet_data, layout,
                                                        text_height)
        cards.append(
            '<figure>'
            '<figcaption><span class="key">%s</span><h3>%s</h3></figcaption>'
            '<div class="plate">%s</div>'
            '<div class="verdictrow"><span class="s %s">view %.1f%%</span>'
            '<span class="pc">table %.0f &times; %.0f mm, placed as a %s</span></div>'
            '<p class="blurb">%s</p></figure>'
            % (number, esc(title), art, 'yes' if share >= required else 'no', share,
               table_w, table_h, placement, esc(blurb)))

    rows = []
    for step in data['ladder']:
        worst = None
        for family in data['families']:
            layout = data['layouts']['rung: ' + step][family['key']]
            if worst is None or layout['area'] > worst['area']:
                worst = layout
        rows.append(
            '<tr><th scope="row">%s</th><td>%.1f</td><td>%d</td><td>%.0f</td>'
            '<td>%.1f%%</td></tr>'
            % (esc(step), worst['width'], worst['rows'], worst['area'],
               100.0 * worst['area'] / frame_area))

    counts = []
    for family in sorted(data['families'], key=lambda f: -f['floor_values']):
        counts.append(
            '<tr><th scope="row">%s</th><td>%d</td><td>%d</td></tr>'
            % (esc(family['kind'] + ' ' + ','.join(family['types'])),
               family['floor_values'], family['every_values']))

    with open(template_path, encoding='utf-8') as handle:
        page = handle.read()

    for token, value in (
            ('{{sheets}}', NL.join(cards)),
            ('{{ladder}}', NL.join(rows)),
            ('{{counts}}', NL.join(counts)),
            ('{{required}}', '%.0f' % required),
            ('{{frame_area}}', '%.0f' % frame_area),
            ('{{block_area}}', '%.0f' % block_area),
            ('{{block_share}}', '%.1f' % (100.0 * block_area / frame_area)),
            ('{{block_of_rest}}', '%.0f' % (100.0 * block_area
                                            / ((1.0 - data['view_share']) * frame_area))),
            ('{{ceiling}}', '%.1f' % (100.0 * data['ceiling_area'] / frame_area)),
            ('{{px_per_mm}}', '%.3f' % PX_PER_MM)):
        page = page.replace(token, value)

    with open(out_path, 'w', encoding='utf-8', newline=NL) as handle:
        handle.write(page)
    return out_path


def main(argv):
    if len(argv) < 3:
        print('usage: python draw_sheet_alternatives.py sheets.json out.html')
        return 2
    with open(argv[1], encoding='utf-8') as handle:
        data = json.load(handle)
    path = build(data, argv[2], TEMPLATE)
    print('wrote %s' % path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
