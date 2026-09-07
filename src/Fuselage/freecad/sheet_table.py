"""IP-FC-21: the value table, laid out -- where every cell and every rule goes.

`tools/drawing_families.py` decides *what* a family sheet tabulates and `drawing_standard`
decides how wide it may be. Neither says where anything is printed, and until this module
existed the table was a width and a row count rather than something a reader could look at.

**Why it is not in `drawing.py`.** Same reason as `sheet_annotations`: `drawing.py` imports
FreeCAD at module scope, so the project virtualenv cannot read it, and the table's width has to
be measurable from the virtualenv -- `check_table_width.py` fails a family whose table does not
fit the band, and it can only do that if it measures the strings that are actually printed. So
the layout lives here, in plain arithmetic, and `drawing.py` does nothing but put objects where
this says. Nothing in this file may import FreeCAD.

**The coordinate frame is the table's own**: origin at its top-left corner, x to the right and
**y downward**, in millimeters, because that is reading order and a table is read rather than
projected. The page's own y runs upward, so `drawing.py` flips once, in one place. Producing
page coordinates here instead would have put the flip in the middle of the layout arithmetic,
where getting it wrong prints a table that is correct about everything except which way up it
is.

**Every string this returns is the string it measured.** The uppercasing is done here, before
the width is taken, and `column_width_mm` is asked about the printed form. A module that
uppercases at draw time and measures the lowercase form produces a table whose columns are
narrower than their contents, and nothing reports it -- the cells simply overlap the rules.

**Why the rules are load-bearing.** OQ-DES-D5 compacted the column gutter to 1.0 mm, which is
0.4 of the table's text height and well inside section 5.2's H2 clearance. That was allowed on
the stated grounds that H2 governs annotations floating on a view with nothing between them,
and a table has a rule between its columns. This module is where that debt is paid: the gutter
and the rule are produced by the same function, so a table cannot be drawn at the compacted
gutter without them.

**Unit regime: millimeters.**
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_standard as std

LEFT = 'left'
RIGHT = 'right'
CENTER = 'center'


class Cell(object):
    """One printed string, at the center of the box it occupies.

    The center rather than a corner because that is what a TechDraw annotation is positioned
    by, and converting an alignment into a center is arithmetic this module can do once with
    the width it already measured. A caller that only knows the string would have to measure
    it again to place it, and a second measurement is a second chance to measure something
    else.
    """

    def __init__(self, text, x, y, height, align=RIGHT):
        self.text = text
        self.x = float(x)
        self.y = float(y)
        self.height = float(height)
        self.align = align

    def __repr__(self):
        return '<Cell %r at %.2f, %.2f>' % (self.text, self.x, self.y)


class Table(object):
    """A laid-out value table: its cells, its rules, and the box it fills.

    `cells`   every string to print, positioned
    `rules`   every line to draw, as ((x1, y1), (x2, y2))
    `width`   what the table needs, which is what `check_table_width` measures
    `height`  the same, downward
    `rows`    printed rows in the deepest block, headings included
    """

    def __init__(self, cells, rules, width, height, rows):
        self.cells = list(cells)
        self.rules = list(rules)
        self.width = float(width)
        self.height = float(height)
        self.rows = int(rows)

    def fits(self, region=None):
        """Complaints about the table not fitting the band, or an empty list.

        A list rather than a boolean because a table can miss on either axis and for
        different reasons, and "it does not fit" is not something a reader of a failing
        checker can act on.
        """
        region = std.table_region_mm() if region is None else region
        problems = []
        if self.width > region[2] + 1e-9:
            problems.append('the table is %.1f mm wide and the band beside the title block is '
                            '%.1f -- over by %.1f'
                            % (self.width, region[2], self.width - region[2]))
        if self.height > region[3] + 1e-9:
            problems.append('the table is %.1f mm deep over %d rows and the band is %.1f -- '
                            'over by %.1f, so the drawn view loses the share OQ-DES-D5 '
                            'requires'
                            % (self.height, self.rows, region[3], self.height - region[3]))
        return problems


def printed(text):
    """The form a string takes on the drawing.

    Uppercase, because every other string on the sheet is: the OQ-DES-D2 notes are, the title
    block's captions are, and a table setting `1/16in` beside a note reading `FOR 1.59 PANEL`
    reads as two drawings. Numbers are unaffected, which is most of a value table.
    """
    return str(text).upper()


def is_numeric(cells):
    """Whether a column holds measurements, which decides how it is aligned."""
    for cell in cells:
        try:
            float(cell)
        except (TypeError, ValueError):
            return False
    return bool(cells)


def column_strings(column, letters, heading=None):
    """Every string one column prints, heading included, in printed form.

    The heading is the callout letter for a value column, which is where OQ-DES-D5's
    addressability is enforced: a column whose field has no letter is a column the reader
    cannot look up from the view, and it raises here rather than printing a headless column
    of numbers.
    """
    strings = [printed(cell) for cell in column['cells']]
    strings.append(heading_of(column, letters) if heading is None else heading)
    return [s for s in strings if s]


def common_prefix(names):
    """The longest shared leading run of `name_` segments, or the empty string.

    Used to shorten a band's headings, and it works on segments rather than characters so it
    cannot cut a name in the middle: `end_anchor` and `end_bolt` share `end_`, while `1/16in`
    and `1/8in` share nothing this will take.
    """
    if len(names) < 2:
        return ''
    parts = [name.split('_') for name in names]
    shared = []
    for index in range(min(len(p) for p in parts) - 1):
        segment = parts[0][index]
        if any(p[index] != segment for p in parts):
            break
        shared.append(segment)
    return ('_'.join(shared) + '_') if shared else ''


def band_headings(block, letters):
    """What is written above each column of a block, by column index.

    **A band heading only has to tell its band's members apart**, which is the same argument
    OQ-DES-D5 made for dropping the unit from a panel stock and stating it once above the
    band. A block whose second axis is the bulkhead type heads its columns `cowling_anchor`
    and `cowling_bolt` -- fourteen characters over four-character numbers, so the heading, not
    the data, sets the column width. The shared `cowling_` is a property of the whole sheet
    (it is in the title block) rather than of either column, and removing it took the cowling
    family's table from **122.9 mm to inside the band**.

    Only a shared prefix that ends at a segment boundary is removed, and only when what is
    left still tells the columns apart -- otherwise the heading is left exactly as the
    factoring produced it.
    """
    out = {}
    bands = band_of(block, letters)
    for field, (first, last) in bands.items():
        names = [str(block['columns'][i]['heading']) for i in range(first, last + 1)]
        prefix = common_prefix(names)
        short = [n[len(prefix):] for n in names] if prefix else names
        if len(set(short)) != len(short) or any(not n for n in short):
            short = names
        for offset, index in enumerate(range(first, last + 1)):
            out[index] = printed(short[offset])
    for index, column in enumerate(block['columns']):
        out.setdefault(index, heading_of(column, letters))
    return out


def heading_of(column, letters):
    """What is written above a column: the axis name, a coupled axis value, or the letter."""
    if column['field'] is None:
        return printed(column['heading'])
    if column['heading'] is not None:
        return printed(column['heading'])
    letter = letters.get(column['field'])
    if letter is None:
        raise ValueError(
            'the table has a column for %r and the view has no callout letter for it, so the '
            'reader has a column of numbers with nothing on the drawing pointing at it. That '
            'is the failure OQ-DES-D5 was decided to prevent: either the annotation '
            'set states the quantity or the table does not carry it.' % column['field'])
    return letter


def band_of(block, letters):
    """Which columns of a block belong to a coupled field, as {field: (first, last)}.

    A field that follows two axes is printed as a *band* of columns -- the second axis spent
    across the page -- so its letter is written once above the band rather than once per
    column, and the band needs a rule under the letter to say how far it reaches. Without
    that a reader sees eight columns headed `1/16IN`, `1/32IN` and so on with no indication
    which dimension they are values of.
    """
    bands = {}
    for index, column in enumerate(block['columns']):
        field = column['field']
        if field is None or column['heading'] is None:
            continue
        first, _last = bands.get(field, (index, index))
        bands[field] = (first, index)
    return bands


def _cells_by_key(column):
    """A column's cells looked up by the leading axis's value.

    The pairing is `keys`, not position: a coupled band holds a cell only where the
    combination is valid, so a band column can have three cells where the key column has
    eight values. Zipping them by index would print the right numbers in the wrong rows,
    which is the failure mode a drawing cannot survive because every number is plausible.
    """
    return dict(zip([printed(k) for k in column['keys']],
                    [printed(c) for c in column['cells']]))


def block_layout(block, letters, origin_x, text_height_mm=None, pitch_mm=None):
    """One block of the table, laid out. Returns (cells, rules, width, rows).

    A block is one leading axis and everything read against it. Its first row is the heading
    row; a block carrying a coupled field takes a second heading row above that for the
    field letters, which is the row `drawing_families.sheet_blocks` already counts.
    """
    height = std.TABLE_TEXT_HEIGHT_MM if text_height_mm is None else text_height_mm
    pitch = std.table_row_pitch_mm(height) if pitch_mm is None else pitch_mm
    gutter = std.TABLE_COLUMN_GUTTER_MM

    columns = block['columns']
    bands = band_of(block, letters)
    headings = band_headings(block, letters)
    heading_rows = 2 if bands else 1
    keys = [printed(k) for k in columns[0]['cells']]

    widths = [std.column_width_mm(column_strings(column, letters, headings[index]), height)
              for index, column in enumerate(columns)]
    lefts = []
    x = origin_x
    for width in widths:
        lefts.append(x)
        x += width + gutter
    block_width = sum(widths) + gutter * (len(widths) - 1)

    def place(text, index, row, align):
        """A string in column `index`, row `row`, at the row's vertical center."""
        left, width = lefts[index], widths[index]
        y = row * pitch + pitch / 2.0
        if align == RIGHT:
            cx = left + width - std.text_width_mm(text, height) / 2.0
        elif align == LEFT:
            cx = left + std.text_width_mm(text, height) / 2.0
        else:
            cx = left + width / 2.0
        return Cell(text, cx, y, height, align)

    cells = []
    rules = []

    # The letter row, where a coupled field names itself once above the band it spans. A
    # single-axis column's letter is its own heading and stays on the heading row, because a
    # letter written twice above the same column is a reader asking what the difference is.
    if bands:
        for field, (first, last) in sorted(bands.items()):
            letter = letters.get(field)
            if letter is None:
                raise ValueError(
                    'the table bands %r across %d columns and the view has no callout letter '
                    'for it' % (field, last - first + 1))
            left = lefts[first]
            right = lefts[last] + widths[last]
            cells.append(Cell(letter,
                              left + (right - left) / 2.0,
                              pitch / 2.0, height, CENTER))
            # The rule that says how far the band reaches.
            rules.append(((left, pitch), (right, pitch)))

    # The heading row. A single-axis column's letter *is* its heading and sits here even in a
    # banded block, because a letter written twice above one column is a reader asking what
    # the difference between the two rows is.
    heading_row = heading_rows - 1
    for index, column in enumerate(columns):
        cells.append(place(headings[index], index, heading_row, CENTER))

    for index, column in enumerate(columns):
        align = RIGHT if is_numeric(column['cells']) else LEFT
        by_key = _cells_by_key(column)
        for row, key in enumerate(keys):
            text = by_key.get(key)
            if text is None:
                # Not an error and not a blank to be filled: a coupled band holds a cell only
                # where the combination exists, and inventing one would state a variant the
                # sweep does not build.
                continue
            cells.append(place(text, index, heading_rows + row, align))

    rows = heading_rows + len(keys)
    depth = rows * pitch

    # The block's frame, the rule under its headings, and one rule down the middle of every
    # gutter. The gutter rules are the reason the gutter may be 1.0 mm at all.
    left, right = origin_x, origin_x + block_width
    rules.append(((left, 0.0), (right, 0.0)))
    rules.append(((left, depth), (right, depth)))
    rules.append(((left, 0.0), (left, depth)))
    rules.append(((right, 0.0), (right, depth)))
    rules.append(((left, heading_rows * pitch), (right, heading_rows * pitch)))
    for index in range(len(widths) - 1):
        x = lefts[index] + widths[index] + gutter / 2.0
        rules.append(((x, 0.0), (x, depth)))

    return cells, rules, block_width, rows


#: The dimension key's heading, printed over its two columns.
LEGEND_HEADING = ('', 'DIMENSION KEY')


def legend_table(pairs, columns=1, text_height_mm=None, pitch_mm=None):
    """The dimension key as a `Table` of its own: `(letter, phrase)` rows in `columns` runs.

    **A table of its own, and not part of the value table, because it does not go where the
    values go.** Tried the other way first: appended to the value table so it would share an
    anchor and a fit test. The key is thirteen rows and the values are five, so it wrapped into
    three runs of four, added 150 mm to a 135 mm table, and ran off the right-hand edge of the
    frame. It belongs in the band beside the title block -- which the value table vacates when
    it moves to a strip of its own -- and that is a different rectangle with a different
    budget, so it is measured separately.

    One heading over the whole key, not one per run: three boxes each labelled DIMENSION KEY
    read as three different keys.
    """
    height = std.TABLE_TEXT_HEIGHT_MM if text_height_mm is None else text_height_mm
    pitch = std.table_row_pitch_mm(height) if pitch_mm is None else pitch_mm
    gutter = std.TABLE_COLUMN_GUTTER_MM
    pairs = list(pairs)
    if not pairs:
        return Table([], [], 0.0, 0.0, 0)

    columns = max(1, int(columns))
    per = -(-len(pairs) // columns)                 # ceiling, so no run is left over
    groups = [pairs[i:i + per] for i in range(0, len(pairs), per)]

    cells, rules = [], []
    rows = 1 + max(len(g) for g in groups)
    depth = rows * pitch
    x = 0.0
    for group in groups:
        letter_w = std.column_width_mm([p[0] for p in group], height)
        phrase_w = std.column_width_mm([p[1] for p in group], height)
        right = x + letter_w + gutter + phrase_w
        for index, (letter, phrase) in enumerate(group):
            y = (index + 1) * pitch + pitch / 2.0
            cells.append(Cell(letter, x + letter_w / 2.0, y, height, CENTER))
            cells.append(Cell(phrase,
                              x + letter_w + gutter + std.text_width_mm(phrase, height) / 2.0,
                              y, height, LEFT))
            rules.append(((x, y - pitch / 2.0), (right, y - pitch / 2.0)))
        # The run's own box, and the rule between a letter and its phrase.
        rules.append(((x, pitch), (x, depth)))
        rules.append(((right, pitch), (right, depth)))
        divider = x + letter_w + gutter / 2.0
        rules.append(((divider, pitch), (divider, depth)))
        x = right + 2.0 * gutter

    width = x - 2.0 * gutter
    cells.append(Cell(LEGEND_HEADING[1], width / 2.0, pitch / 2.0, height, CENTER))
    rules.append(((0.0, 0.0), (width, 0.0)))
    rules.append(((0.0, pitch), (width, pitch)))
    rules.append(((0.0, depth), (width, depth)))
    rules.append(((0.0, 0.0), (0.0, pitch)))
    rules.append(((width, 0.0), (width, pitch)))
    return Table(cells, rules, width, depth, rows)


#: The sheet-coverage block's heading.
COVERAGE_HEADING = 'SHEET COVERAGE'


def caption_table(rows, heading=COVERAGE_HEADING, text_height_mm=None, pitch_mm=None,
                  stacked=False):
    """A two-column label/value block: `(label, value)` rows under one heading.

    The same shape as the dimension key and for the same reason -- it is a small ruled block
    that has to be measured before it is placed -- but the columns mean different things, so
    it is its own layout rather than the key with different strings in it. Labels are left
    aligned against the rule, values left aligned in their own column, because a reader scans
    the labels down and reads one value across.
    """
    height = std.TABLE_TEXT_HEIGHT_MM if text_height_mm is None else text_height_mm
    pitch = std.table_row_pitch_mm(height) if pitch_mm is None else pitch_mm
    gutter = std.TABLE_COLUMN_GUTTER_MM
    rows = list(rows)
    if not rows:
        return Table([], [], 0.0, 0.0, 0)

    label_w = std.column_width_mm([r[0] for r in rows], height)
    value_w = std.column_width_mm([r[1] for r in rows], height)
    if stacked:
        # The value on its own row, indented under its label. One column, so the block is as
        # wide as its widest single string rather than as wide as the widest pair.
        indent = gutter
        width = max(label_w, indent + value_w)
        printed_rows = []
        for label, value in rows:
            printed_rows.append((label, 0.0))
            printed_rows.append((value, indent))
    else:
        width = label_w + gutter + value_w
        printed_rows = None

    count = len(printed_rows) if stacked else len(rows)
    depth = (1 + count) * pitch

    cells = [Cell(heading, width / 2.0, pitch / 2.0, height, CENTER)]
    rules = [((0.0, 0.0), (width, 0.0)), ((0.0, pitch), (width, pitch)),
             ((0.0, depth), (width, depth)),
             ((0.0, 0.0), (0.0, depth)), ((width, 0.0), (width, depth))]

    if stacked:
        for index, (text, indent) in enumerate(printed_rows):
            y = (index + 1) * pitch + pitch / 2.0
            cells.append(Cell(text, indent + std.text_width_mm(text, height) / 2.0,
                              y, height, LEFT))
        # A rule under each pair rather than under each row: the label and its value are one
        # statement, and a rule between them reads as two.
        for index in range(0, len(printed_rows), 2):
            y = (index + 1) * pitch
            rules.append(((0.0, y), (width, y)))
    else:
        for index, (label, value) in enumerate(rows):
            y = (index + 1) * pitch + pitch / 2.0
            cells.append(Cell(label, std.text_width_mm(label, height) / 2.0, y, height, LEFT))
            cells.append(Cell(value,
                              label_w + gutter + std.text_width_mm(value, height) / 2.0,
                              y, height, LEFT))
            rules.append(((0.0, y - pitch / 2.0), (width, y - pitch / 2.0)))
        divider = label_w + gutter / 2.0
        rules.append(((divider, pitch), (divider, depth)))
    return Table(cells, rules, width, depth, 1 + count)

def caption_fitting(rows, width_mm, heading=COVERAGE_HEADING, text_height_mm=None,
                    pitch_mm=None):
    """The coverage block in the widest form that fits `width_mm`, or the narrowest tried.

    Two forms, tried in order. **Side by side**, label and value on one row, which is how a
    reader wants it and what the block is for. **Stacked**, the value on its own row indented
    under its label, which is half the width and twice the depth -- and depth is what this
    sheet has to spare, because the block sits beside a value table that is deeper than it is.

    Returns `(table, complaints)`; the complaints name the width missed by, so a sheet that
    can carry neither says how much it is short rather than that it failed.
    """
    for stacked in (False, True):
        table = caption_table(rows, heading, text_height_mm, pitch_mm, stacked=stacked)
        if table.width <= width_mm + 1e-9:
            return table, []
    return table, ['the sheet-coverage block needs %.1f mm in its narrowest form and %.1f mm '
                   'is free -- over by %.1f'
                   % (table.width, width_mm, table.width - width_mm)]



def legend_fitting(pairs, region, text_height_mm=None, pitch_mm=None):
    """The key laid out in the fewest runs that fit `region`, or the widest tried.

    Fewest runs because a tall narrow key is easier to read than a short wide one, and because
    every run costs a letter column and two gutters. Returns `(table, complaints)`; the
    complaints are `Table.fits`'s, so a key that fits nothing still says by how much.
    """
    best = None
    for columns in range(1, len(list(pairs)) + 1):
        table = legend_table(pairs, columns, text_height_mm, pitch_mm)
        problems = table.fits(region)
        if not problems:
            return table, []
        best = (table, problems)
    return best if best else (legend_table([]), [])


def layout(blocks, letters, text_height_mm=None, pitch_mm=None):
    """The whole value table, laid out in its own frame. Returns a `Table`.

    `blocks` is a family's `quantity_blocks` as `drawing_families.py` writes them, and
    `letters` maps a quantity name to the callout letter its annotation carries, which comes
    from `sheet_annotations.issue_letters`. The two are the same source read twice: the
    letters are issued to the annotations, and the table's headings are those letters, so a
    column and the thing on the view that points at it cannot disagree.

    **Blocks print abreast**, separated by twice the column gutter, because that is what
    OQ-DES-D5 decided and what makes a panelled family cost its deepest block rather than the
    sum of them. Twice the gutter because the single gutter is the space *inside* a block,
    where a rule separates two columns; between two blocks there are two frame rules and the
    gap has to read as wider than the one inside.
    """
    gutter = std.TABLE_COLUMN_GUTTER_MM
    cells, rules = [], []
    x = 0.0
    rows = 0
    for index, block in enumerate(blocks):
        if index:
            x += 2.0 * gutter
        block_cells, block_rules, width, block_rows = block_layout(
            block, letters, x, text_height_mm, pitch_mm)
        cells.extend(block_cells)
        rules.extend(block_rules)
        rows = max(rows, block_rows)
        x += width

    height = std.TABLE_TEXT_HEIGHT_MM if text_height_mm is None else text_height_mm
    pitch = std.table_row_pitch_mm(height) if pitch_mm is None else pitch_mm
    return Table(cells, rules, x, rows * pitch, rows)


def cell_box(cell):
    """The rectangle a cell's text occupies, as (x_min, y_min, x_max, y_max).

    In the table's own frame, so y_min is the *top* of the text. The width is measured from
    the string rather than taken from the column, because the question this exists for is
    whether the column was sized against the string that is printed in it -- and a box taken
    from the column width could not tell.
    """
    width = std.text_width_mm(cell.text, cell.height)
    return (cell.x - width / 2.0, cell.y - cell.height / 2.0,
            cell.x + width / 2.0, cell.y + cell.height / 2.0)


def _overlap(a, b):
    return (a[0] < b[2] - 1e-9 and b[0] < a[2] - 1e-9
            and a[1] < b[3] - 1e-9 and b[1] < a[3] - 1e-9)


def check_layout(table, text_height_mm=None):
    """Complaints about a laid-out table, or an empty list.

    **Section 5.2's H1 and H2, asked of a table instead of a view.** They are the same two
    questions -- does the text stay inside the space it was given, and does any of it touch
    any other -- and a table is where they are easiest to get wrong, because a column is sized
    once against strings it is assumed to contain. A column measured against `1/16in` and
    printed as `1/16IN` passes every arithmetic check in this module and overlaps its
    neighbour on the sheet.

    The third question is the one this project owes: **is there a rule in every gutter**. The
    1.0 mm column gutter is 0.4 of the table's text height, which H2 would refuse outright on
    a view; OQ-DES-D5 allowed it on the grounds that a table has a rule between its columns.
    A table that lost its rules would be within its stated width, pass H1 and H2 as written,
    and be illegible. So the rule is checked for, not assumed.
    """
    height = std.TABLE_TEXT_HEIGHT_MM if text_height_mm is None else text_height_mm
    problems = []

    boxes = [(cell, cell_box(cell)) for cell in table.cells]

    for cell, box in boxes:
        if box[0] < -1e-9 or box[2] > table.width + 1e-9:
            problems.append(
                'the cell %r runs from %.2f to %.2f mm across a table %.2f mm wide, so it is '
                'outside the column it was measured for'
                % (cell.text, box[0], box[2], table.width))
        if box[1] < -1e-9 or box[3] > table.height + 1e-9:
            problems.append(
                'the cell %r sits from %.2f to %.2f mm down a table %.2f mm deep'
                % (cell.text, box[1], box[3], table.height))

    for index, (cell, box) in enumerate(boxes):
        for other, other_box in boxes[index + 1:]:
            if _overlap(box, other_box):
                problems.append(
                    'the cells %r and %r overlap at %.2f, %.2f -- two numbers printed on top '
                    'of each other, which a reader cannot recover'
                    % (cell.text, other.text, box[0], box[1]))

    # A vertical rule somewhere in the clear space between every pair of horizontally
    # adjacent cells that are closer than H2's clearance.
    verticals = sorted({round(x1, 6) for (x1, y1), (x2, y2) in table.rules
                        if abs(x1 - x2) < 1e-9})
    for index, (cell, box) in enumerate(boxes):
        for other, other_box in boxes[index + 1:]:
            if other_box[3] <= box[1] + 1e-9 or box[3] <= other_box[1] + 1e-9:
                continue                      # different rows, nothing between them
            left, right = (box, other_box) if box[2] <= other_box[0] else (other_box, box)
            gap = right[0] - left[2]
            if gap >= height - 1e-9 or gap < 0.0:
                continue                      # H2 is satisfied by the clearance alone
            if not any(left[2] - 1e-9 <= x <= right[0] + 1e-9 for x in verticals):
                problems.append(
                    'the cells %r and %r are %.2f mm apart, inside H2\'s %.1f mm clearance, '
                    'with no rule between them -- the compacted gutter OQ-DES-D5 took is only '
                    'legible because a rule is drawn in it'
                    % (left is box and cell.text or other.text,
                       left is box and other.text or cell.text, gap, height))
    return problems


def measure(blocks, letters, text_height_mm=None, pitch_mm=None):
    """The table's (width, height, rows) without keeping the layout.

    What `check_table_width.py` asks, and it asks the layout rather than re-deriving the
    arithmetic. A checker that measures a table by a formula and a renderer that draws it by
    another is two tables, and the one that fails the check is not the one on the sheet.
    """
    table = layout(blocks, letters, text_height_mm, pitch_mm)
    return table.width, table.height, table.rows
