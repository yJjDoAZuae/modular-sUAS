"""IP-FC-21: does the factored family table fit the sheet *across*, as well as down?

`drawing_families.py` answered how many rows each family costs and every one of the thirteen
fitted -- five of them exactly. That measurement is sound and it is only half the question. A
table also has a width, the width is set by the same factoring that set the rows, and until
2026-08-22 nothing measured it.

**It has to be measured here rather than there.** A column's width is the width of the widest
string in it, which is a question for the pinned font, and the font is read with `fontTools`
inside FreeCAD's own Python. The project virtualenv has neither. So this is the same boundary
hop `export_parameters.py` and `drawing_families.py` already make, crossed in the other
direction: the families are enumerated in the virtualenv and written as JSON, and the
millimeters are measured here.

    python drawing_families.py families.json          # in the project virtualenv
    freecadcmd check_table_width.py --pass families.json

**What it found, and it is the reason [OQ-DES-D5] exists.** Carrying every field the part is
driven by, **none of the thirteen families fits the 154.0 mm** the table has beside the
view, and three do not fit even the whole 239.5 mm frame. Carrying section 3's interface floor,
**all thirteen fit** with the worst at 112.4 mm. The row budget does not distinguish the two --
both are 19 rows or fewer -- so the choice that was invisible down the sheet is decisive across
it.

**Unit regime: millimeters**, as everything on a page is.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_standard as ds
import sheet_table as st

from corner_common import is_entry_point

NEWLINE = chr(10)

# What the view beside the table needs, in millimeters, so that what is left over is the
# table's budget. **Measured, not allowed for**: it is the narrowest view region the corner's
# family sheet places in -- four OQ-DES-D2 leader notes and six dimensions around a 20 mm
# section at the frame's full height -- found by `check_dimension_placement.py`, which prints
# it on every run so that a change in the annotation set shows up here as a disagreement
# rather than as a stale constant.
#
# The single-variant sheet needs 136.0 mm and is not the case that matters: those sheets carry
# no family table, so nothing is competing with them for the width.
#
# **84.5 until 2026-09-07**, when the text width model was corrected: ISO 3098's `h` is a cap
# height, not an em, so every string was measured 32.8% narrow and with it every note and the
# region the notes place in. See `check_dimension_placement.VIEW_WIDTH_RECORDED_MM`.
VIEW_WIDTH_MM = 117.5


def column_strings(column):
    """Every string that has to fit in one column, its heading included.

    A key column is headed by its axis name and a band column by the value of the axis the
    band is spent across -- `3/16in` is wider than any number under it, which is why the
    heading cannot be left out of the measurement. An ordinary field column is headed by a
    callout letter, and `column_width_mm` already floors every column at one of those.
    """
    strings = list(column['cells'])
    if column['heading'] is not None:
        strings.append(column['heading'])
    return strings


def block_width_mm(columns):
    """How wide one printed block is, in millimeters."""
    return ds.table_width_mm([ds.column_width_mm(column_strings(c)) for c in columns])


def transposed(block, interface, interface_only):
    """The same block turned on its side: fields down the page, axis values across it.

    The factored table puts the axis down the left and a field in each column, so a coupled
    field is a band of columns and the block is wide. Turned round it puts the *field* down the
    left and a value of the axis in each column, so a coupled field is a band of **rows** and
    the block is tall. The content is identical; what moves is which budget it spends.

    Returns (column widths in mm, printed rows, total width in mm). Rows count one heading
    row, then one row per single-axis field and one per value of the second axis for each
    coupled field. The widths come back rather than their count because a drawing of the sheet
    needs to lay the columns out, and recomputing them from a total would be a second
    authority on the same number.
    """
    fields = [c for c in block['columns'] if c['field'] is not None]
    if interface_only:
        fields = [c for c in fields if c['field'] in interface]
    if not fields:
        return [], 0, 0.0

    # The left-hand label column carries a callout letter, and a second one carries the
    # coupled axis's value where there is one -- `3/16in` beside `panel_offset`'s row band.
    labels = [ds.callout_width_mm()]
    banded = [c['heading'] for c in fields if c['heading'] is not None]
    if banded:
        labels.append(ds.column_width_mm(sorted(set(banded))))

    # One column per value of the leading axis, holding every field's value at that value.
    per_key = {}
    for key in block['columns'][0]['cells']:
        per_key.setdefault(key, [])
    for c in fields:
        for key, cell in zip(c['keys'], c['cells']):
            per_key.setdefault(key, []).append(cell)
    columns = [ds.column_width_mm(per_key[k] + [k]) for k in sorted(per_key)]

    rows = 1 + len(fields)
    return labels + columns, rows, ds.table_width_mm(labels + columns)


def widths(family, interface_only):
    """The width of each block of one family, in the order the sheet prints them."""
    out = []
    for block in family['blocks']:
        columns = [c for c in block['columns']
                   if c['field'] is None
                   or not interface_only
                   or c['field'] in family['interface']]
        out.append((block['axis'], len(columns), block_width_mm(columns)))
    return out


# The next stock sheet up, measured rather than assumed. OQ-DES-D5's alternative 3 is "use a
# bigger sheet", and the obvious form of that argument -- a B sheet is 1.6 times an A sheet, so
# everything fits -- is wrong in a way worth catching: **the ASME title block is the same
# 146.66 mm on both**, so any rule tying a table's width to the title block gives a B-size
# sheet no more table than an A-size one. It is the frame that grows, not the block.
ANSI_B_RELPATH = ('Mod', 'TechDraw', 'Templates', 'ASME', 'ANSIB_Landscape.svg')
ANSI_B_FRAME_ID = 'rect3675'
ANSI_B_TITLE_BLOCK_ID = 'rect2985'


def larger_sheet():
    """The ANSI B landscape frame and title block, or None if it is not installed."""
    path = os.path.join(ds.resource_dir(), *ANSI_B_RELPATH)
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    frame = ds.read_template_rect(text, ANSI_B_FRAME_ID)
    block = ds.read_template_rect(text, ANSI_B_TITLE_BLOCK_ID)
    if frame is None or block is None:
        return None
    return frame, block


# --------------------------------------------------------------------------------------
# Compaction
# --------------------------------------------------------------------------------------



# Every compaction available, as (name, knobs), each step adding to the ones before it. None
# of them removes a value from the sheet: the same numbers are printed either way.
#
#   decimals   drop trailing zeros a whole column can lose. `DECIMAL_PLACES` is a bound on
#              how much precision a value may carry, and it was being read as an instruction
#              to print that many places whatever the value is -- so a column of 4.00, 10.00,
#              5.00 prints six characters where one would do. Per-column rather than per-cell,
#              because a column with a ragged decimal point is harder to read than a wide one.
#   short      a band's heading is a panel stock name, and `3/16in` is wider than any number
#              under it. The `in` is carried by the column beside it in every case, so it is
#              stated once above the band instead of eight times inside it.
#   gutter     1.0 mm between columns instead of one text height. H2's one-text-height rule is
#              about two annotations floating on a view with nothing between them; a ruled
#              table has a rule between its columns, which is what a rule is for.
#   pitch      1.5 text heights per row instead of 2. The 2 was chosen to match the dimension
#              lane pitch so the sheet would have one vertical rhythm -- which is an argument
#              about how the sheet looks, made before anyone knew what the rhythm cost.
#   packed     blocks side by side instead of stacked. The `U` block and the panel block have
#              nothing to do with each other, and stacking them adds their row counts where
#              placing them abreast takes the larger. This is the non-rectangular packing
#              question: nothing about the table requires it to be one column of the sheet.
# Every rung states all five knobs rather than leaning on the module defaults, because the
# defaults are now OQ-DES-D5's decision -- so a rung that omitted them would measure the
# decided layout and call it "as built". A ladder whose first rung moves when the decision
# lands is not a before-and-after.
BEFORE = {'decimals': False, 'short': False, 'gutter_mm': 3.5, 'pitch_heights': 2.0,
          'packed': False, 'text_height_mm': ds.TEXT_HEIGHT_MM}


def _rung(**changes):
    return dict(BEFORE, **changes)


LADDER = (
    ('as built', _rung()),
    ('per-column decimals', _rung(decimals=True)),
    ('short band headings', _rung(decimals=True, short=True)),
    ('1.0 mm gutter', _rung(decimals=True, short=True, gutter_mm=1.0)),
    ('1.3 h row pitch',
     _rung(decimals=True, short=True, gutter_mm=1.0, pitch_heights=1.3)),
    ('blocks packed abreast',
     _rung(decimals=True, short=True, gutter_mm=1.0, pitch_heights=1.3, packed=True)),
    # **The last two rungs are the correction of 2026-08-27, and they belong on the ladder
    # rather than in a footnote to it.** 1.3 h is below ISO 3098's minimum line spacing for
    # type B lettering and was taken to make the band arithmetic work; putting the standard
    # back costs 3.5 mm of depth. The table setting at the *view's* 3.5 mm was never a
    # decision at all -- there was one text-height constant and the table inherited it -- and
    # setting it one size down in the standard's own preferred series pays for the pitch
    # several times over. The ladder has to end at the decided layout: a rung short of it
    # leaves the report measuring a table the sheet does not print, which is how the 1.3 h
    # figure survived being wrong.
    ('1.4 h row pitch, per ISO 3098',
     _rung(decimals=True, short=True, gutter_mm=1.0, pitch_heights=1.4, packed=True)),
    ('table sets at 2.5 mm',
     _rung(decimals=True, short=True, gutter_mm=1.0, pitch_heights=1.4, packed=True,
           text_height_mm=ds.TABLE_TEXT_HEIGHT_MM)),
)

# The `in` and `mm` are dropped from a band heading, not the number. Which unit a panel stock
# is quoted in is a property of the whole band and belongs above it.
SHORT_HEADINGS = {'1/16in': '1/16', '1/32in': '1/32', '1/4in': '1/4', '1/8in': '1/8',
                  '3/16in': '3/16', '1mm': '1', '3mm': '3', '6mm': '6'}


def compacted_blocks(family, interface_only=True, decimals=False, short=False,
                     gutter_mm=None, pitch_heights=None, packed=False,
                     text_height_mm=None):
    """One family's table under one set of compaction choices, block by block.

    Returns a dict with `blocks` -- each carrying its column widths in millimeters and its
    printed row count -- and the `gutter`, `pitch`, `width`, `rows` and `area` that follow.
    The column widths come back rather than only their total because the same measurement has
    to be *drawn*: a table's cost is a rectangle on a page, and a reader judges the rectangle.

    Nothing here changes which values are on the sheet. Every knob is a layout choice, and the
    value count is the same at the bottom of the ladder as at the top.
    """
    gutter = ds.TABLE_COLUMN_GUTTER_MM if gutter_mm is None \
        else gutter_mm
    height = ds.TABLE_TEXT_HEIGHT_MM if text_height_mm is None else text_height_mm
    pitch = (ds.TABLE_ROW_PITCH_HEIGHTS if pitch_heights is None
             else pitch_heights) * height

    blocks = []
    for block in family['blocks']:
        columns = [c for c in block['columns']
                   if c['field'] is None
                   or not interface_only
                   or c['field'] in family['interface']]
        if len(columns) <= 1:
            continue
        block_widths = []
        for column in columns:
            cells_ = ds.format_column(column['cells']) if decimals else list(column['cells'])
            heading = column['heading']
            if heading is not None and short:
                heading = SHORT_HEADINGS.get(heading, heading)
            if heading is not None:
                cells_ = cells_ + [heading]
            block_widths.append(ds.column_width_mm(cells_, height))
        blocks.append({'axis': block['axis'], 'rows': block['rows'],
                       'column_widths': block_widths,
                       'columns': len(block_widths),
                       'width': sum(block_widths) + gutter * (len(block_widths) - 1)})

    if not blocks:
        return {'blocks': [], 'gutter': gutter, 'pitch': pitch,
                'width': 0.0, 'rows': 0, 'area': 0.0, 'packed': packed}
    if packed:
        width = sum(b['width'] for b in blocks) + 2.0 * gutter * (len(blocks) - 1)
        rows = max(b['rows'] for b in blocks)
    else:
        width = max(b['width'] for b in blocks)
        rows = sum(b['rows'] for b in blocks)
    return {'blocks': blocks, 'gutter': gutter, 'pitch': pitch, 'packed': packed,
            'width': width, 'rows': rows, 'area': width * rows * pitch}


def compacted(family, **knobs):
    """`compacted_blocks`, as the (width, rows, area) triple the report prints."""
    measured = compacted_blocks(family, **knobs)
    return measured['width'], measured['rows'], measured['area']


def table_breakages(table):
    """A good table broken three ways, with what the layout check must say about each.

    Each break is one of the failures the table's arithmetic cannot produce and a change to
    the arithmetic could: a column sized against a string other than the one printed in it, a
    cell placed outside the table it was measured for, and -- the one this project owes an
    argument for -- a compacted gutter with no rule in it.
    """
    def copy(cells=None, rules=None):
        return st.Table([st.Cell(c.text, c.x, c.y, c.height, c.align)
                         for c in (cells if cells is not None else table.cells)],
                        list(rules if rules is not None else table.rules),
                        table.width, table.height, table.rows)

    # A cell widened after its column was measured -- what uppercasing at draw time does.
    widened = copy()
    for cell in widened.cells:
        if cell.text.replace('.', '').isdigit():
            cell.text = cell.text + '00000'
            break

    # A cell shoved off the right-hand edge.
    outside = copy()
    outside.cells[-1].x = table.width + 20.0

    # Every rule removed, which leaves a legible-looking table at a 1.0 mm gutter.
    unruled = copy(rules=[])

    return (('a cell wider than its column', widened, 'overlap'),
            ('a cell outside the table', outside, 'outside the column'),
            ('a table drawn without rules', unruled, 'no rule between them'))


def report(document):
    lines = []
    say = lines.append
    column = ds.table_width_available_mm(VIEW_WIDTH_MM)
    frame = ds.frame_region_mm()[2]
    failures = []

    say('the view needs %.1f mm, so a table beside it has %.1f mm of the %.1f mm frame'
        % (VIEW_WIDTH_MM, column, frame))
    say('gutter %.1f mm between columns, which is H2 applied to a column of digits'
        % (ds.TABLE_COLUMN_GUTTER_MM))
    say('')
    say('%-14s %-24s %5s %8s %5s %8s  %s'
        % ('kind', 'types', 'cols', 'width', 'ifc', 'ifc wide', 'fits'))

    for family in document['families']:
        every = widths(family, False)
        floor = widths(family, True)
        wide = max(w for _a, _n, w in every)
        columns = max(n for _a, n, _w in every)
        floor_wide = max(w for _a, _n, w in floor)
        floor_columns = max(n for _a, n, _w in floor)

        fits = []
        fits.append('column' if wide <= column else
                    ('frame' if wide <= frame else 'neither'))
        if floor_wide > column:
            fits.append('FLOOR OVER')
            failures.append(
                '%s %s needs %.1f mm for section 3\'s interface floor alone, and the table '
                'column is %.1f mm -- no choice about what else the table carries can '
                'recover that'
                % (family['kind'], ','.join(family['type_names']), floor_wide, column))

        say('%-14s %-24s %5d %8.1f %5d %8.1f  %s'
            % (family['kind'], ','.join(family['type_names'])[:24], columns, wide,
               floor_columns, floor_wide, ' '.join(fits)))

    say('')
    say('  cols/width  every field the part is driven by, which is what section 4 puts in')
    say('              the table; ifc  section 3\'s interface floor alone.')
    say('  fits        the widest block against the two budgets: `column` is what is left')
    say('              beside a view of the measured width, `frame` is the whole sheet')
    say('              with the view moved off it entirely.')

    for label, budget in (('the width beside the view', column),
                          ('the whole frame', frame)):
        over = [f for f in document['families']
                if max(w for _a, _n, w in widths(f, False)) > budget]
        say('')
        say('carrying every field, %d of %d families exceed %s (%.1f mm)'
            % (len(over), len(document['families']), label, budget))
        for f in over:
            say('  %-14s %-24s %.1f mm'
                % (f['kind'], ','.join(f['type_names']),
                   max(w for _a, _n, w in widths(f, False))))

    over = [f for f in document['families']
            if max(w for _a, _n, w in widths(f, True)) > column]
    say('')
    say('carrying the interface floor alone, %d of %d families exceed the view-side width'
        % (len(over), len(document['families'])))

    # The same content turned on its side, because it is the obvious response to a table that
    # is too wide and it is worth knowing what it costs before anyone proposes it.
    rows_available = document['rows_per_sheet']
    say('')
    say('%-30s %8s %8s' % ('family', 'values', 'floor'))
    for family in document['families']:
        every = sum(len(c['cells']) for b in family['blocks'] for c in b['columns']
                    if c['field'] is not None)
        floor_n = sum(len(c['cells']) for b in family['blocks'] for c in b['columns']
                      if c['field'] is not None and c['field'] in family['interface'])
        say('%-30s %8d %8d'
            % (family['kind'] + ' ' + ','.join(family['type_names'])[:16], every, floor_n))
    say('')
    say('  values  how many numbers the table prints. This is the question the sheet')
    say('          allocation is actually about, and it is a small number.')

    say('')
    say('turned round -- fields down the page, axis values across it:')
    say('')
    say('%-14s %-24s %8s %6s %8s %6s  %s'
        % ('kind', 'types', 'width', 'rows', 'ifc wide', 'ifc', 'fits'))
    for family in document['families']:
        measured = {}
        for only in (False, True):
            wide = 0.0
            tall = 0
            for block in family['blocks']:
                _cols, rows, w = transposed(block, family['interface'], only)
                wide = max(wide, w)
                tall += rows
            measured[only] = (wide, tall)
        wide, tall = measured[False]
        floor_wide, floor_tall = measured[True]
        verdict = []
        verdict.append('column' if wide <= column else
                       ('frame' if wide <= frame else 'neither'))
        verdict.append('%d rows' % rows_available if tall <= rows_available
                       else 'OVER %d rows' % rows_available)
        say('%-14s %-24s %8.1f %6d %8.1f %6d  %s'
            % (family['kind'], ','.join(family['type_names'])[:24], wide, tall,
               floor_wide, floor_tall, ' '.join(verdict)))

    bigger = larger_sheet()
    if bigger is not None:
        frame_b, block_b = bigger
        gutter = ds.TABLE_COLUMN_GUTTER_MM
        budget = frame_b[2] - VIEW_WIDTH_MM - gutter
        rows_b = int((block_b[1] - frame_b[1]) // (ds.TABLE_ROW_PITCH_HEIGHTS
                                                   * ds.TEXT_HEIGHT_MM))
        worst = max(max(w for _a, _n, w in widths(f, False))
                    for f in document['families'])
        over = [f for f in document['families']
                if max(w for _a, _n, w in widths(f, False)) > budget]
        say('')
        say('on ANSI B landscape, whose frame is %.1f mm wide and whose title block is the '
            % frame_b[2])
        say('same %.1f mm as on ANSI A:' % block_b[2])
        say('  a table beside the same %.1f mm view has %.1f mm, and holds %d rows'
            % (VIEW_WIDTH_MM, budget, rows_b))
        say('  the widest family carrying every field is %.1f mm, so %d of %d exceed it,'
            % (worst, len(over), len(document['families'])))
        say('  a margin of %.1f mm' % (budget - worst))

    frame_area = ds.TEMPLATE_FRAME_MM[2] * ds.TEMPLATE_FRAME_MM[3]
    block_area = ds.TEMPLATE_TITLE_BLOCK_MM[2] * ds.TEMPLATE_TITLE_BLOCK_MM[3]
    table_budget = (1.0 - ds.VIEW_SHARE) * frame_area - block_area

    say('')
    say('the frame is %.0f mm2. A view at %d%% of it leaves %.0f, of which the title block'
        % (frame_area, int(ds.VIEW_SHARE * 100), (1.0 - ds.VIEW_SHARE) * frame_area))
    say('already takes %.0f -- so the value table has %.0f mm2, which is %.1f%% of the frame.'
        % (block_area, table_budget, 100.0 * table_budget / frame_area))
    say('')
    frame_w, frame_h = ds.TEMPLATE_FRAME_MM[2], ds.TEMPLATE_FRAME_MM[3]
    block_w, block_h = ds.TEMPLATE_TITLE_BLOCK_MM[2], ds.TEMPLATE_TITLE_BLOCK_MM[3]
    gutter = ds.TABLE_COLUMN_GUTTER_MM

    # The ceiling, before any table is placed at all. It is worth stating on its own because
    # it is not something a table can be compacted out of.
    ceiling = ds.best_view(0.0, 0.0, block_w, block_h)
    say('')
    say('with **no table at all**, the largest rectangular view is %.1f x %.1f = %.0f mm2,'
        % (ceiling[1], ceiling[2], ceiling[3]))
    say('which is %.1f%% of the frame. The stock title block is %.1f mm deep, and that alone'
        % (100.0 * ceiling[3] / frame_area, block_h))
    say('puts %d%% out of reach on this template.' % int(ds.VIEW_SHARE * 100))

    say('')
    say('')
    say('the ladder below is measured on the pinned template, whose title block is %.0f x %.0f'
        % (block_w, block_h))
    say('mm. The stock ASME block it replaced is 146.7 x 48.1, and on that one the')
    say('bottom rung places as a column and gives the view 38.4% -- why it went.')
    say('')
    say('%-24s %8s %6s %8s %7s %8s  %s'
        % ('compaction', 'width', 'rows', 'area', 'placed', 'view', 'meets 75%'))
    for name, knobs in LADDER:
        worst = None
        for family in document['families']:
            measured = compacted_blocks(family, **knobs)
            table_h = measured['rows'] * measured['pitch']
            placement = ds.best_view(measured['width'], table_h, block_w, block_h)
            # The largest table, not the smallest view. Once the band is available every
            # family gives the same view share, so selecting on the share picks whichever
            # family happens to sort first and reports its width as the rung's.
            if worst is None or measured['area'] > worst[0]['area']:
                worst = (measured, placement, table_h)
        measured, placement, table_h = worst
        share = placement[3] / frame_area
        say('%-24s %8.1f %6d %8.0f %7s %7.1f%%  %s'
            % (name, measured['width'], measured['rows'], measured['area'],
               placement[0], 100.0 * share,
               'yes' if share >= ds.VIEW_SHARE else 'no, short by %.0f mm2'
               % (ds.VIEW_SHARE * frame_area - placement[3])))
    say('')
    say('  Worst of the thirteen families at each step, carrying section 3 interface floor.')
    say('  Every step is a layout choice: the same values are printed at the bottom of this')
    say('  ladder as at the top. `placed` is which packing wins -- `band` puts the table')
    say('  beside the title block with the view full width above, `column` stacks them on')
    say('  the right with the view full height beside. Value counts are above.')

    # The envelope OQ-DES-D5's alternative 2 specifies, which is the real output of that
    # decision -- a rectangle a template has to fit inside, not the size it was measured at.
    knobs = dict(LADDER[-1][1])
    worst_table = max((compacted_blocks(f, **knobs) for f in document['families']),
                      key=lambda m: m['area'])
    say('')
    say('the stock title block is %.0f mm2, %.0f%% of everything that is not the view.'
        % (block_w * block_h,
           100.0 * block_w * block_h / ((1.0 - ds.VIEW_SHARE) * frame_area)))
    say('with the compacted table (%.1f mm wide, %d rows):'
        % (worst_table['width'], worst_table['rows']))
    for label, bw, bh, pitch_h in (('stock, 1.5 h pitch', block_w, block_h, 1.5),
                                   ('stock, 1.3 h pitch', block_w, block_h, 1.3),
                                   ('120 x 40, 1.5 h', 120.0, 40.0, 1.5),
                                   ('120 x 40, 1.3 h', 120.0, 40.0, 1.3),
                                   ('100 x 32, 1.3 h', 100.0, 32.0, 1.3)):
        table = max((compacted_blocks(f, **dict(knobs, pitch_heights=pitch_h))
                     for f in document['families']), key=lambda m: m['area'])
        placement = ds.best_view(table['width'], table['rows'] * table['pitch'],
                                 bw, bh)
        say('  %-20s view %7.1f%%  %s' % (label, 100.0 * placement[3] / frame_area,
                                          placement[0]))

    say('')
    say('the envelope a title block of our own has to fit inside, for the view to reach %d%%:'
        % int(ds.VIEW_SHARE * 100))
    for pitch_h in (1.5, 1.4, 1.3, 1.2):
        table = max((compacted_blocks(f, **dict(knobs, pitch_heights=pitch_h))
                     for f in document['families']), key=lambda m: m['area'])
        table_h = table['rows'] * table['pitch']
        envelope = ds.title_block_envelope(table['width'], table_h)
        if envelope is None:
            say('  %.1f h pitch  table is %.1f mm deep, past the %.1f mm the band may be'
                % (pitch_h, table_h, (1.0 - ds.VIEW_SHARE) * frame_h))
            continue
        say('  %.1f h pitch  table %.1f x %.1f mm  ->  block up to %.1f x %.1f mm'
            % (pitch_h, table['width'], table_h, envelope[0], envelope[1]))
    say('')
    say('  The stock block is %.1f x %.1f, so it misses that envelope by %.1f mm of width'
        % (block_w, block_h, block_w - (frame_w - gutter - 95.1)))
    say('  and %.1f mm of depth -- which is how close the sheet was to working untouched.'
        % (block_h - (1.0 - ds.VIEW_SHARE) * frame_h))

    # The table the sheet actually prints, for the kinds that have an annotation set. Every
    # measurement above is of the *parameter* mapping, which is what the factoring produces;
    # this is of the **quantities the view points at**, which is what OQ-DES-D5's
    # recommendation turned on and what a reader can look up.
    drawn = [f for f in document['families'] if f.get('quantity_blocks')]
    if drawn:
        region = ds.table_region_mm()
        band_rows = ds.table_rows_available()
        say('')
        say('the sheet band leaves %.1f x %.1f mm and %d rows beside the title block:'
            % (region[2], region[3], band_rows))
        say('')
        say('%-34s %5s %8s %6s  %s'
            % ('family', 'cols', 'width', 'rows', 'against the band'))
        for family in drawn:
            # **Measured by laying it out, not by re-deriving the arithmetic.** An earlier
            # version summed `column_width_mm` here and `sheet_table.py` summed it again to
            # draw; two sums of the same intent are two tables, and the one that passes this
            # check is not necessarily the one on the sheet. It also measured the *unprinted*
            # strings -- the renderer uppercases before it measures, and `1/16IN` is wider
            # than `1/16in`, so the check was passing a table 1.8 mm narrower than the one
            # that would be drawn.
            table = st.layout(family['quantity_blocks'], family['letters'])
            columns = sum(len(b['columns']) for b in family['quantity_blocks'])
            problems = table.fits(region)
            verdict = 'fits' if not problems else '; '.join(problems)
            for problem in problems:
                failures.append(
                    '%s %s: %s -- the sheet cannot carry what section 3 obliges it to state'
                    % (family['kind'], ','.join(family['type_names']), problem))
            say('%-34s %5d %8.1f %6d  %s'
                % (family['kind'] + ' ' + ','.join(family['type_names'])[:12]
                   + '/' + str(family['variants']), columns, table.width, table.rows,
                   verdict))
            say('%-34s %5s %8s %6s  %d cells, %d rules, %.1f mm deep'
                % ('', '', '', '', len(table.cells), len(table.rules), table.height))

        say('')
        say('  A family with no annotation set is not listed: its sheet has no table to')
        say('  print yet, which is work rather than a finding.')

        # **Every family passes `check_layout`, which is only worth reading if the check is
        # capable of failing.** A layout checker that has never refused anything is a checker
        # whose thresholds are untested, and the swept corpus reaches none of these cases: a
        # table built by `sheet_table.layout` is correct by construction, so the only way to
        # see the refusals work is to break one on purpose.
        say('')
        say('the layout check, against tables broken on purpose:')
        table = st.layout(drawn[-1]['quantity_blocks'], drawn[-1]['letters'])
        for name, broken, expect in table_breakages(table):
            problems = st.check_layout(broken)
            hit = [q for q in problems if expect in q]
            say('  %-28s %s' % (name, 'refused' if hit else 'ACCEPTED -- the check is blind'))
            if not hit:
                failures.append(
                    'the table layout check accepts %s, so it cannot be read as evidence that '
                    'the tables it passes are laid out at all' % name)

    return NEWLINE.join(lines), failures


def layout(family, turned, interface_only):
    """One family's table under one of the four layouts, as a drawable description.

    `columns` is the width of each printed column in millimeters, block by block, which is what
    a drawing of the sheet needs. A table drawn at its measured width is the only form of
    this question a reader can judge; the numbers alone are not.
    """
    blocks = []
    for block in family['blocks']:
        if turned:
            cols, rows, width = transposed(block, family['interface'], interface_only)
            if not cols:
                continue
            blocks.append({'axis': block['axis'], 'rows': rows, 'width': width,
                           'columns': len(cols), 'column_widths': cols})
            continue
        columns = [c for c in block['columns']
                   if c['field'] is None
                   or not interface_only
                   or c['field'] in family['interface']]
        widths_mm = [ds.column_width_mm(column_strings(c)) for c in columns]
        blocks.append({'axis': block['axis'], 'rows': block['rows'],
                       'width': ds.table_width_mm(widths_mm),
                       'columns': len(columns), 'column_widths': widths_mm})
    return {'blocks': blocks,
            'width': max([b['width'] for b in blocks] or [0.0]),
            'rows': sum(b['rows'] for b in blocks)}


def _value_count(family, interface_only):
    """How many numbers the table prints. The question the sheet allocation is about."""
    return sum(len(c['cells']) for b in family['blocks'] for c in b['columns']
               if c['field'] is not None
               and (not interface_only or c['field'] in family['interface']))


def _larger_sheet_snapshot():
    """ANSI B landscape, for alternative 3, or None if the template is not installed."""
    bigger = larger_sheet()
    if bigger is None:
        return None
    frame, block = bigger
    gutter = ds.TABLE_COLUMN_GUTTER_MM
    return {'template_mm': [431.8, 279.4],
            'frame_mm': list(frame),
            'title_block_mm': list(block),
            'view_width_mm': VIEW_WIDTH_MM,
            'table_width_mm': frame[2] - VIEW_WIDTH_MM - gutter,
            'rows_available': int((block[1] - frame[1])
                                  // (ds.TABLE_ROW_PITCH_HEIGHTS * ds.TEXT_HEIGHT_MM))}


def snapshot(document):
    """Everything a drawing of these alternatives needs, measured rather than described."""
    layouts = {}
    for turned in (False, True):
        for only in (False, True):
            name = '%s-%s' % ('turned' if turned else 'factored',
                              'floor' if only else 'every')
            layouts[name] = {
                ','.join(f['type_names']) + '/' + str(f['variants']):
                    layout(f, turned, only)
                for f in document['families']}
    for step, knobs in LADDER:
        layouts['rung: ' + step] = {
            ','.join(f['type_names']) + '/' + str(f['variants']):
                compacted_blocks(f, **knobs)
            for f in document['families']}
    return {
        'text_height_mm': ds.TEXT_HEIGHT_MM,
        'row_pitch_mm': ds.TABLE_ROW_PITCH_HEIGHTS * ds.TEXT_HEIGHT_MM,
        'gutter_mm': ds.TABLE_COLUMN_GUTTER_MM,
        'rows_available': ds.table_rows_available(),
        'template_mm': [ds.TEMPLATE_WIDTH_MM, ds.TEMPLATE_HEIGHT_MM],
        'frame_mm': list(ds.frame_region_mm()),
        'title_block_mm': list(ds.TEMPLATE_TITLE_BLOCK_MM),
        # What the view needs and what that leaves the table. Both measured, and the pair is
        # the whole of the sheet allocation -- there is no third region.
        'view_width_mm': VIEW_WIDTH_MM,
        'table_width_mm': ds.table_width_available_mm(VIEW_WIDTH_MM),
        'larger_sheet': _larger_sheet_snapshot(),
        'view_share': ds.VIEW_SHARE,
        'ladder': [name for name, _knobs in LADDER],
        'families': [{'kind': f['kind'], 'types': f['type_names'],
                      'variants': f['variants'],
                      'every_values': _value_count(f, False),
                      'floor_values': _value_count(f, True),
                      'key': ','.join(f['type_names']) + '/' + str(f['variants'])}
                     for f in document['families']],
        # The largest rectangular view with no table on the sheet at all. Worth carrying
        # because it is the number no amount of compaction can move.
        'ceiling_area': ds.best_view(
            0.0, 0.0, ds.TEMPLATE_TITLE_BLOCK_MM[2], ds.TEMPLATE_TITLE_BLOCK_MM[3])[3],
        'layouts': layouts,
    }


def main(argv):
    paths = [a for a in argv if a.endswith('.json')]
    if not paths:
        print('usage: freecadcmd check_table_width.py --pass families.json [out.json]')
        return 2

    ds.require_standard()
    with open(paths[0], encoding='utf-8') as handle:
        document = json.load(handle)

    text, failures = report(document)
    print(text)

    if len(paths) > 1:
        with open(paths[1], 'w', encoding='utf-8', newline=NEWLINE) as handle:
            json.dump(snapshot(document), handle, indent=1, sort_keys=True)
            handle.write(NEWLINE)
        print('')
        print('wrote %s' % paths[1])
    print('')
    if failures:
        print('FAIL:')
        for problem in failures:
            print('  - ' + problem)
    else:
        print('ok -- the interface floor fits the column on every family')
    return 1 if failures else 0


if is_entry_point(__name__):
    _code = main(sys.argv)
    sys.stdout.flush()
    sys.exit(_code)
