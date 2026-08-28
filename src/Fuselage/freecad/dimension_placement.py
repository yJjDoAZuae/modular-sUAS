"""IP-FC-21: where each dimension goes on the sheet.

Implements `doc/design/dimension_scheme.md` section 5. That document decides *what* the rules
are and why; this module is the solver, and it deliberately adds no rules of its own.

**What this module is not.** It does not choose which dimensions a drawing carries -- that is
section 1's membership test and section 3's completeness test, and it arrives here as input. It
does not talk to FreeCAD: it takes projected geometry as plain 2D coordinates and returns
placements as plain 2D coordinates, so it is testable without building a part and its
correctness does not depend on a kernel. `drawing.py` is what connects it to a `DrawViewPart`.

**The one idea the whole solver rests on**, from section 5.3: nesting by magnitude -- smaller
dimensions inboard, larger outboard -- is not a matter of taste. A larger dimension spans a
wider range, so its witness lines stand outside the span of every smaller one, and they
therefore do not cross the smaller dimensions' lines. Nesting is what makes **H4** satisfiable
instead of a constraint to fight. `check_placement` verifies that rather than assuming it.

**Determinism** (section 5.5): every ordering here is total. Sorts are by (magnitude, letter)
and iteration is over sorted sequences, never over a dict or set. The same input produces the
same output, byte for byte.

**Unit regime: millimeters**, in *view* coordinates -- the space `DrawViewPart` reports its
projected geometry in, which is page millimeters at the view's scale, origin at the view
centre. Model values are carried alongside for magnitude ordering and never mixed in.
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawing_standard as std


# Lane geometry, both derived from the text height per section 5.4. The multipliers are the
# ISO 129-1 spacings expressed in text heights rather than as absolute millimeters: at the
# 3.5 mm standard height they give a 10.5 mm standoff and 7.0 mm lane pitch, which are the
# conventional 10 mm and 7 mm. Writing them as multiples is what makes section 5.4's "both
# scale with text height, not with U" true by construction rather than by discipline.
FIRST_LANE_GAP_HEIGHTS = 3.0
LANE_PITCH_HEIGHTS = 2.0

# Section 5.2 H2 requires a clear gap of at least one text height between text blocks.
TEXT_CLEARANCE_HEIGHTS = 1.0

# The pitch between the lines *inside* one note, as a multiple of the text height. **1.4,
# which is ISO 3098's minimum line spacing for type B lettering** -- the same standard the
# 3.5 mm text height comes from, so it is a number the drawing convention already fixes rather
# than one this module picks.
#
# It was `std.TABLE_ROW_PITCH_HEIGHTS` on the reasoning that a note is a short column of text
# lines and a table row pitch already spaces those. That borrowing was wrong and OQ-DES-D5
# exposed it: the table's pitch is set by how much sheet the table may occupy, which is a
# question about the *sheet*, and when the decision moved it from 2.0 to 1.3 it would have
# silently tightened every note's line spacing below what the lettering standard allows.
NOTE_LINE_PITCH_HEIGHTS = 1.4

# The arrowhead allowance. Section 5.2's H1 counts arrowheads in an annotation's extent, and
# they cannot be measured headlessly -- `getArrowPositions()` returns the origin. They are the
# same on every annotation, so a fixed multiple of the text height is the whole of the model.
ARROWHEAD_LENGTH_HEIGHTS = 1.0

# A value whose magnitude is under this is structurally zero (H5). It is not a fit tolerance
# and must not be confused with one: printed clearances in this project are around 0.1 mm, two
# orders of magnitude above this. This asks "did the expression evaluate to nothing", which is
# a question about the design, not about manufacturing.
ZERO_MM = 1.0e-9

# How many note-side assignments the solver will try before giving up. Four sides raised to
# the number of notes, so it is the note count this bounds rather than the search: six notes
# is 4096 assignments and each is arithmetic over a dozen rectangles. A drawing needing more
# than six leader notes on one view is a drawing that wants splitting, which is section 5.6's
# remedy and not something a longer search should paper over.
MAX_NOTE_ASSIGNMENTS = 4096

# Written as a name because a literal escape does not survive every route this file has
# been edited through. It is one character either way.
NEWLINE = chr(10)

HORIZONTAL = 'horizontal'
VERTICAL = 'vertical'

# Sides are named for where the dimension line sits relative to the view. The order is the
# tie-break order when balancing (section 5.3 item 5), and it is fixed so the result is
# reproducible.
SIDES = {HORIZONTAL: ('below', 'above'), VERTICAL: ('left', 'right')}


class PlacementError(Exception):
    """A drawing that cannot be placed. Section 5.6: fail rather than emit."""


class Dimension(object):
    """One dimension to be placed, as the caller describes it.

    `letter`  the callout letter, from `drawing_standard.CALLOUT_ALPHABET`
    `p1, p2`  the two referenced points, in view coordinates (mm)
    `axis`    HORIZONTAL for a DistanceX, VERTICAL for a DistanceY
    `value`   the model value in mm -- used here for magnitude ordering and the H5 zero test
    `text`    None on a family sheet, where the view shows `letter`; the rendered value string
              on a single-variant sheet, where the view shows the number
    """

    def __init__(self, letter, p1, p2, axis, value, text=None):
        if letter not in std.CALLOUT_ALPHABET:
            raise ValueError(
                '%r is not a callout letter. The alphabet is %s -- I, O and Q are omitted '
                'because they read as 1, 0 and 0.' % (letter, std.CALLOUT_ALPHABET))
        if axis not in SIDES:
            raise ValueError('%r is not an axis; expected %r or %r'
                             % (axis, HORIZONTAL, VERTICAL))
        self.letter = letter
        self.p1 = (float(p1[0]), float(p1[1]))
        self.p2 = (float(p2[0]), float(p2[1]))
        self.axis = axis
        self.value = float(value)
        # None means a family sheet: the view shows the callout letter and the value lives in
        # the table, so every annotation is the same width. A string means a single-variant
        # sheet, where the view carries the value itself and annotations differ in width by up
        # to 5x. The two products place differently for exactly this reason.
        self.text = text

    def span(self):
        """The interval the dimension covers along its own axis, in view coordinates."""
        i = 0 if self.axis == HORIZONTAL else 1
        lo, hi = sorted((self.p1[i], self.p2[i]))
        return lo, hi

    def __repr__(self):
        return '<Dimension %s %s %.4f mm>' % (self.letter, self.axis, self.value)


class Placed(object):
    """A dimension with a position. Everything here is derived, nothing is a preference."""

    def __init__(self, dimension, side, lane, offset, text_box, dimension_line, witnesses):
        self.dimension = dimension
        self.side = side
        self.lane = lane
        self.offset = offset
        self.text_box = text_box                # (x_min, y_min, x_max, y_max)
        self.dimension_line = dimension_line    # ((x1, y1), (x2, y2))
        self.witnesses = witnesses              # [((x1, y1), (x2, y2)), ...]

    @property
    def letter(self):
        return self.dimension.letter

    def __repr__(self):
        return '<Placed %s %s lane %d>' % (self.letter, self.side, self.lane)


class Note(object):
    """A leader note: a point on the geometry and one or more lines of text beside it.

    **This is [OQ-DES-D2]'s annotation**, decided 2026-08-22: the dimension gives the feature
    as built and a note beside it names the hardware the feature is for, so one annotation
    serves the inspector and the integrator and the two numbers cannot drift apart. A corner's
    bore note is

        Ø4.10 BORE / FOR Ø4.00 LONGERON / 0.10 DIA CLEARANCE

    `key`     an identifier for messages -- the joint it states, or the letter it sits beside
    `anchor`  the point on the geometry the leader points at, in view coordinates (mm)
    `lines`   the text, one string per line, already rendered

    **A note is not a dimension and does not become one.** It has no value, so H5 does not
    apply to it; it has no witness lines, so H4 does not; and it is never sorted by magnitude,
    because it does not measure anything. What it shares with a dimension is the only thing
    section 5.2 is actually about -- a rectangle of text that must not touch another rectangle
    of text, another part of the drawing, or the edge of the sheet.
    """

    def __init__(self, key, anchor, lines):
        lines = [str(line) for line in lines]
        if not lines:
            raise ValueError('note %r has no text, so there is nothing to place' % (key,))
        self.key = key
        self.anchor = (float(anchor[0]), float(anchor[1]))
        self.lines = tuple(lines)

    def size(self, text_height_mm=std.TEXT_HEIGHT_MM):
        """The rectangle the note's text occupies, as (width, height).

        Width is *measured*, never bounded by the callout letter: a note carries words, and
        `FOR Ø4.00 LONGERON` is twelve times the width of a `W`. That is why OQ-DES-D2
        recorded an unmeasured risk when it chose this annotation -- section 5.2's extent
        argument rests on a family sheet's text being one known letter, and a note is the one
        thing on such a sheet that escapes it.
        """
        width = max(std.text_width_mm(line, text_height_mm) for line in self.lines)
        pitch = NOTE_LINE_PITCH_HEIGHTS * text_height_mm
        height = text_height_mm + pitch * (len(self.lines) - 1)
        return width, height

    def __repr__(self):
        return '<Note %s, %d lines>' % (self.key, len(self.lines))


class PlacedNote(object):
    """A note with a position, its leader running from the anchor to the block."""

    def __init__(self, note, side, text_box, leader):
        self.note = note
        self.side = side
        self.text_box = text_box            # (x_min, y_min, x_max, y_max)
        self.leader = leader                # ((x1, y1), (x2, y2))

    @property
    def key(self):
        return self.note.key

    def __repr__(self):
        return '<PlacedNote %s %s>' % (self.key, self.side)


class Layout(list):
    """The placed dimensions, with the placed notes alongside.

    A list of `Placed`, so everything written against `place` before notes existed reads
    unchanged, carrying the `PlacedNote`s on `.notes`. A drawing with no notes is the empty
    case rather than a different kind of result.
    """

    def __init__(self, placed, notes=()):
        list.__init__(self, placed)
        self.notes = list(notes)


def _rects_overlap(a, b, clearance):
    """Do two rectangles come within `clearance` of each other?"""
    return not (a[2] + clearance <= b[0] or b[2] + clearance <= a[0]
                or a[3] + clearance <= b[1] or b[3] + clearance <= a[1])


def _spans_overlap(a, b):
    """Do two intervals share more than an endpoint?

    Endpoint contact is allowed: two dimensions measuring adjacent features from a common
    boundary meet at a point and are conventionally drawn in one lane.
    """
    return min(a[1], b[1]) - max(a[0], b[0]) > 0.0


def _segments_cross(a, b):
    """Do two line segments properly cross? Touching at an endpoint does not count.

    Endpoint contact is excluded deliberately: a witness line legitimately *ends* on its own
    dimension line, and counting that as a crossing would make H4 unsatisfiable for every
    dimension ever drawn.
    """
    def orient(p, q, r):
        return ((q[0] - p[0]) * (r[1] - p[1])) - ((q[1] - p[1]) * (r[0] - p[0]))

    d1 = orient(a[0], a[1], b[0])
    d2 = orient(a[0], a[1], b[1])
    d3 = orient(b[0], b[1], a[0])
    d4 = orient(b[0], b[1], a[1])
    # Strictly opposite signs on both pairs. A zero means an endpoint lies *on* the other
    # segment, which is a touch and not a crossing -- and it is the common case here, since
    # every witness line ends exactly on a dimension line. Testing `(d1 > 0) != (d2 > 0)`
    # instead reads a zero as negative and reports every witness as crossing its own lane.
    return (d1 * d2 < 0.0) and (d3 * d4 < 0.0)


def _text_box(centre, text_height_mm, text=None):
    """The rectangle an annotation's text occupies, centred on a point.

    With `text` None this is the family sheet's uniform callout bound: every callout is one
    character from `CALLOUT_ALPHABET`, so the widest letter bounds all of them, and being
    uniform is what makes it safe to be conservative -- it shifts the layout without
    distorting it.

    With `text` given this is a single-variant sheet, and the width is *measured* rather than
    bounded, because a conservative bound over value strings is the thing that does distort a
    layout. `112.50 mm` is 5.3 times the width of `W`, and value strings differ from each
    other, so there is no uniform number that is both safe and useful.
    """
    width = (std.callout_width_mm(text_height_mm) if text is None
             else std.text_width_mm(text, text_height_mm))
    half_w = width / 2.0
    half_h = text_height_mm / 2.0
    return (centre[0] - half_w, centre[1] - half_h,
            centre[0] + half_w, centre[1] + half_h)


def place(dimensions, geometry_bbox, frame=None, geometry_edges=None, notes=(),
          text_height_mm=std.TEXT_HEIGHT_MM):
    """Place every dimension, or raise `PlacementError` naming the ones that would not go.

    `geometry_bbox`   (x_min, y_min, x_max, y_max) of the projected view, in view coordinates
    `frame`           the same, for the region placements must stay inside (H1). None skips
                      the containment check, which is only correct in a test.
    `geometry_edges`  the projected edges, for H3. None skips it -- again, tests only.
    `notes`           OQ-DES-D2's leader notes, placed inboard of every dimension lane.

    Returns a `Layout` -- a list of `Placed` ordered by (axis, side, lane, letter), carrying
    the placed notes on `.notes`, so the result is a stable sequence rather than whatever
    order the input arrived in.

    **The notes take the innermost band and the dimensions start outside it**, which is not a
    matter of taste either. A leader placed inside the first lane lives entirely between the
    geometry and the innermost dimension line, so it cannot cross a dimension line -- the same
    kind of structural argument that makes nesting the answer to H4, rather than a rule to be
    checked case by case. The cost is that every dimension on a side stands off by that side's
    note band, and where the sheet cannot afford it H1 says so.

    **The result is checked before it is returned.** H5 and the duplicate-letter rule are
    enforced on the way in, and H2 holds by construction from the lane rule -- but H3 and H4
    are properties of the finished layout and cannot be established while building it. Without
    this final pass a layout with a witness line through a dimension line would be returned
    without complaint, and section 5.6 says fail rather than emit.

    Running the checker here does not make it dependent on the placer: it re-derives every
    constraint from the produced coordinates and takes nothing on trust. Who calls it is not
    what independence means.
    """
    zero = [d.letter for d in dimensions if abs(d.value) < ZERO_MM]
    if zero:
        raise PlacementError(
            'H5: %s would be placed with a structurally-zero value. A dimensioned zero '
            'asserts an inspectable coincident fit; where the joint is absent there is '
            'nothing to inspect, so the dimension is omitted rather than printed as 0.'
            % ', '.join(sorted(zero)))

    letters = [d.letter for d in dimensions]
    duplicates = sorted(set(x for x in letters if letters.count(x) > 1))
    if duplicates:
        raise PlacementError(
            'callout %s appears more than once. A letter is the only thing tying a view to '
            'its value table, so a repeat makes the table unreadable.'
            % ', '.join(duplicates))

    keys = [str(n.key) for n in notes]
    repeated = sorted(set(k for k in keys if keys.count(k) > 1))
    if repeated:
        raise PlacementError(
            'note %s appears more than once. A note is addressed by its key when its side is '
            'assigned, so two notes sharing one makes the assignment ambiguous.'
            % ', '.join(repeated))

    # Canonical order before anything reads it. The note side comes out of a search whose ties
    # are broken by position, so without this the same drawing built from the same annotations
    # in a different order puts a note on a different **side of the sheet** -- a much larger
    # movement than the lane shuffle section 5.5 was written against, and the reason the
    # determinism test is run on the notes and not only on the dimensions.
    notes = sorted(notes, key=lambda n: str(n.key))

    failure = None
    for assignment in _note_assignments(notes, geometry_bbox):
        try:
            return _attempt(dimensions, geometry_bbox, frame, geometry_edges, notes,
                            assignment, text_height_mm)
        except PlacementError as exc:
            if failure is None:
                failure = exc
    raise failure


def _note_assignments(notes, geometry_bbox):
    """Every side a note might go on, best first. One empty assignment when there are none.

    **A note's side is a freedom, not a fact about the note.** The side its anchor faces is
    where it reads best, and section 5.3 item 4 is why that comes first -- but section 5.2 is
    hard and section 5.3 is soft, so a preference that puts an annotation off the sheet loses
    to one that does not. Measured on the corner 2026-08-22: with each of the four notes on the
    side its anchor faces the sheet is refused by H1, and with all four moved above and below
    the same four notes and the same six dimensions place clean in two lanes. A solver that
    fixed the side would have reported that drawing impossible.

    Assignments come out ordered by how many notes are away from their preferred side, then by
    the side order, so the natural layout is always tried first and the search is a total order
    -- section 5.5.
    """
    if not notes:
        yield {}
        return

    order = ('below', 'above', 'left', 'right')
    if len(order) ** len(notes) > MAX_NOTE_ASSIGNMENTS:
        raise PlacementError(
            '%d leader notes on one view is %d side assignments to search, past the %d this '
            'solver will try. That is a refusal about the drawing rather than about the '
            'search: a view carrying that many notes is one to split, which is what '
            'section 5.6 prescribes.'
            % (len(notes), len(order) ** len(notes), MAX_NOTE_ASSIGNMENTS))
    preferred = [_note_side(n.anchor, geometry_bbox) for n in notes]
    keys = [n.key for n in notes]

    combinations = itertools.product(range(len(order)), repeat=len(notes))
    ranked = sorted(combinations,
                    key=lambda pick: (sum(1 for i, p in enumerate(pick)
                                          if order[p] != preferred[i]), pick))
    for pick in ranked[:MAX_NOTE_ASSIGNMENTS]:
        yield dict(zip(keys, (order[p] for p in pick)))


def _attempt(dimensions, geometry_bbox, frame, geometry_edges, notes, assignment,
             text_height_mm):
    """One candidate layout, complete and checked.

    Raises `PlacementError` if any hard constraint does not hold.
    """
    gap = FIRST_LANE_GAP_HEIGHTS * text_height_mm
    pitch = LANE_PITCH_HEIGHTS * text_height_mm
    clearance = TEXT_CLEARANCE_HEIGHTS * text_height_mm

    placed_notes, standoff = _place_notes(notes, geometry_bbox, gap, clearance,
                                          text_height_mm, assignment)

    placed = []
    for axis in (HORIZONTAL, VERTICAL):
        group = [d for d in dimensions if d.axis == axis]
        # Section 5.3 item 1: ascending magnitude, so the smallest takes the innermost lane.
        #
        # The sort key is the **span in view coordinates**, not the model value. For a linear
        # dimension the two are the same number scaled by the view scale, so on well-formed
        # input the orderings are identical -- but the span is the quantity nesting actually
        # depends on, because what must not happen is a wider dimension line sitting inboard
        # of a narrower one whose witness lines then cross it. Sorting on the value makes the
        # H4 guarantee contingent on the caller's value agreeing with the geometry; sorting on
        # the span makes it structural. The value stays for the table and for H5.
        #
        # Value then letter break ties, giving the total order section 5.5 requires.
        group.sort(key=lambda d: (d.span()[1] - d.span()[0], abs(d.value), d.letter))

        # Section 5.3 item 5: balance across the sides rather than stacking on one. Alternating
        # by rank keeps the two sides within one lane of each other while preserving the
        # nesting within each side, which is what H4 actually depends on.
        by_side = {}
        for rank, dimension in enumerate(group):
            side = SIDES[axis][rank % 2]
            by_side.setdefault(side, []).append(dimension)

        for side in SIDES[axis]:
            lanes = []
            # Seeded with every note, not with this side's notes: a note stacked down the left
            # runs past the bottom of the view and into where a `below` dimension's text goes,
            # and H2 does not care which side either of them was assigned to.
            side_boxes = [n.text_box for n in placed_notes]
            for dimension in by_side.get(side, []):
                placement = _place_one(dimension, side, lanes, side_boxes, geometry_bbox,
                                       gap + standoff[side], pitch, clearance,
                                       text_height_mm)
                placed.append(placement)

    if frame is not None:
        _require_containment(placed, placed_notes, frame, text_height_mm)

    placed.sort(key=lambda p: (p.dimension.axis, p.side, p.lane, p.letter))

    if frame is not None:
        complaints = check_placement(placed, geometry_edges or [], frame, text_height_mm,
                                     notes=placed_notes)
        if complaints:
            raise PlacementError(
                'the layout violates constraints the solver cannot resolve by lane '
                'assignment:' + NEWLINE
                + NEWLINE.join('  - ' + c for c in complaints)
                + NEWLINE + 'The remedy is to split the view or add a detail view -- a '
                  'drafting decision made deliberately -- not to relax a constraint.')

    return Layout(placed, placed_notes)


def _note_side(anchor, geometry_bbox):
    """Which side of the view a note goes on: the one its anchor faces.

    Taken from the anchor's direction out of the view centre, dominant axis first, so a note
    points outward from the feature rather than across it. The tie-breaks -- a diagonal
    anchor going horizontal, an anchor exactly at the centre going left -- are arbitrary in
    the sense that nothing prefers them, and fixed in the sense section 5.5 requires: the
    same input must produce the same sheet, and a tie decided by anything but a stated rule
    is a sheet that moves between runs.
    """
    x_min, y_min, x_max, y_max = geometry_bbox
    dx = anchor[0] - (x_min + x_max) / 2.0
    dy = anchor[1] - (y_min + y_max) / 2.0
    if abs(dx) >= abs(dy):
        return 'right' if dx > 0.0 else 'left'
    return 'above' if dy > 0.0 else 'below'


def _place_notes(notes, geometry_bbox, gap, clearance, text_height_mm, assignment=None):
    """Stack the notes into one band per side, and report how deep each band is.

    Returns (placed notes, {side: band depth}). The depth is what `place` adds to the first
    lane's standoff on that side, which is what keeps every dimension line outboard of every
    leader.

    **One band per side, with the notes stacked along the side rather than out from it.** The
    alternative -- notes at increasing offsets, like lanes -- puts one note's leader across
    another note's text, which is H3's failure with a leader instead of an edge. Stacked along
    the side, no note is outboard of another and nothing has to cross anything: ordering them
    by their anchors' position along that same side is then enough for the leaders not to
    cross each other either, since two leaders in a strip cross only if their endpoints are in
    opposite orders.

    **The band's depth is the widest note, not the widest line of any note.** A side with one
    three-line note and one one-line note is as deep as the wider block, and the narrower one
    leaves its own trailing space rather than being padded out to match -- the sheet is short
    of width, and paying for symmetry it does not need is what a generated drawing should not
    do.
    """
    x_min, y_min, x_max, y_max = geometry_bbox
    standoff = {'below': 0.0, 'above': 0.0, 'left': 0.0, 'right': 0.0}
    if not notes:
        return [], standoff

    by_side = {}
    for note in notes:
        side = (assignment or {}).get(note.key) or _note_side(note.anchor, geometry_bbox)
        by_side.setdefault(side, []).append(note)

    placed = []
    for side in ('below', 'above', 'left', 'right'):
        group = by_side.get(side)
        if not group:
            continue
        sizes = {}
        for note in group:
            sizes[note.key] = note.size(text_height_mm)

        if side in ('left', 'right'):
            # Down the side, topmost anchor first, so the leaders keep their order.
            group.sort(key=lambda n: (-n.anchor[1], str(n.key)))
            standoff[side] = max(w for w, _h in sizes.values()) + gap
            cursor = y_max
            for note in group:
                width, height = sizes[note.key]
                top, bottom = cursor, cursor - height
                if side == 'left':
                    right = x_min - gap
                    box = (right - width, bottom, right, top)
                    landing = (right, (top + bottom) / 2.0)
                else:
                    left = x_max + gap
                    box = (left, bottom, left + width, top)
                    landing = (left, (top + bottom) / 2.0)
                placed.append(PlacedNote(note, side, box, (note.anchor, landing)))
                cursor = bottom - clearance
        else:
            # Across the side, leftmost anchor first, for the same reason.
            group.sort(key=lambda n: (n.anchor[0], str(n.key)))
            standoff[side] = max(h for _w, h in sizes.values()) + gap
            cursor = x_min
            for note in group:
                width, height = sizes[note.key]
                left, right = cursor, cursor + width
                if side == 'below':
                    top = y_min - gap
                    box = (left, top - height, right, top)
                    landing = ((left + right) / 2.0, top)
                else:
                    bottom = y_max + gap
                    box = (left, bottom, right, bottom + height)
                    landing = ((left + right) / 2.0, bottom)
                placed.append(PlacedNote(note, side, box, (note.anchor, landing)))
                cursor = right + clearance

    placed.sort(key=lambda p: (p.side, str(p.key)))
    return placed, standoff


def _text_positions(lo, hi, clearance):
    """Where along its own dimension line a text block may sit, best position first.

    The midpoint, then alternating either side of it in steps of one text clearance, to the
    ends of the span. **This is section 5.3 item 4 -- "text nearest the feature it dimensions"
    -- being used rather than assumed away**, and until 2026-08-22 it was assumed away: the
    text went at the midpoint and nowhere else.

    That was invisible on a family sheet, where a callout is 2.7 mm of letter and two lanes
    are 7.0 mm apart, and it is not invisible on a single-variant sheet, where the text is the
    value. Two stacked vertical dimensions reading `7.60` and `20.00` centre 8.1 mm of digits
    on lines 7.0 mm apart and collide by H2 -- which is why every drafted stack of dimensions
    staggers its text along the lines rather than lining it up in a column.

    Staggering is not a relaxation of anything. The text stays on its own dimension line
    between its own arrowheads, so which measurement it belongs to is not in doubt; what moves
    is where along that line it sits, which nothing in section 5 fixes.
    """
    midpoint = (lo + hi) / 2.0
    yield midpoint
    step = clearance
    reach = (hi - lo) / 2.0
    offset = step
    while offset <= reach:
        yield midpoint - offset
        yield midpoint + offset
        offset += step


def _place_one(dimension, side, lanes, side_boxes, geometry_bbox, gap, pitch, clearance,
               text_height_mm):
    """Give one dimension the innermost lane whose text it does not collide with (H2).

    `lanes` is a list of lists of (text_box, span) for what is already in each lane, and
    `side_boxes` is every text box already placed on this side, in any lane. Both are mutated.
    Section 5.3 item 3 wants the fewest lanes, so this takes the first lane that fits rather
    than opening a new one -- two dimensions at different positions along the same offset
    legitimately share a lane.

    **The text is tested against the whole side, not against its own lane.** Lanes are one
    lane pitch apart and a value string is wider than that pitch, so the collision a stack of
    dimensions actually produces is between *adjacent* lanes. Testing within the lane finds
    nothing and returns a layout the independent checker then rejects.

    **Sharing a lane requires disjoint spans, not merely non-overlapping text.** Two nested
    spans at one offset would draw collinear dimension lines, and the outer one's witness lines
    would cross the inner one's line -- which is H4, and it is the specific failure that
    nesting by magnitude exists to prevent. Testing only the text boxes lets a small dimension
    and a large one that contains it share lane 0, undoing the nesting the sort just
    established.
    """
    x_min, y_min, x_max, y_max = geometry_bbox
    lo, hi = dimension.span()

    index = 0
    while True:
        while len(lanes) <= index:
            lanes.append([])
        offset = gap + index * pitch

        if side in ('below', 'above'):
            line_y = (y_min - offset) if side == 'below' else (y_max + offset)
            line = ((lo, line_y), (hi, line_y))
            witnesses = [((dimension.p1[0], dimension.p1[1]), (dimension.p1[0], line_y)),
                         ((dimension.p2[0], dimension.p2[1]), (dimension.p2[0], line_y))]

            def centre_at(along):
                return (along, line_y + text_height_mm * 0.6)
        else:
            line_x = (x_min - offset) if side == 'left' else (x_max + offset)
            line = ((line_x, lo), (line_x, hi))
            witnesses = [((dimension.p1[0], dimension.p1[1]), (line_x, dimension.p1[1])),
                         ((dimension.p2[0], dimension.p2[1]), (line_x, dimension.p2[1]))]

            def centre_at(along):
                return (line_x, along)

        clear_span = not any(_spans_overlap((lo, hi), other) for _, other in lanes[index])
        if clear_span:
            for along in _text_positions(lo, hi, clearance):
                text = _text_box(centre_at(along), text_height_mm, dimension.text)
                if any(_rects_overlap(text, other, clearance) for other in side_boxes):
                    continue
                lanes[index].append((text, (lo, hi)))
                side_boxes.append(text)
                return Placed(dimension, side, index, offset, text, line, witnesses)
        index += 1


def _require_containment(placed, notes, frame, text_height_mm):
    """H1. Everything -- text, line, arrowheads, witnesses, leaders -- inside the frame."""
    arrow = ARROWHEAD_LENGTH_HEIGHTS * text_height_mm
    outside = []
    for n in notes:
        xs = [n.text_box[0], n.text_box[2], n.leader[0][0], n.leader[1][0]]
        ys = [n.text_box[1], n.text_box[3], n.leader[0][1], n.leader[1][1]]
        if (min(xs) < frame[0] or min(ys) < frame[1]
                or max(xs) > frame[2] or max(ys) > frame[3]):
            outside.append(str(n.key))
    for p in placed:
        xs = [p.text_box[0], p.text_box[2], p.dimension_line[0][0], p.dimension_line[1][0]]
        ys = [p.text_box[1], p.text_box[3], p.dimension_line[0][1], p.dimension_line[1][1]]
        for w in p.witnesses:
            xs.extend([w[0][0], w[1][0]])
            ys.extend([w[0][1], w[1][1]])
        # The arrowheads sit at the dimension line's ends, pointing along it.
        if p.dimension.axis == HORIZONTAL:
            xs.extend([min(xs) - arrow, max(xs) + arrow])
        else:
            ys.extend([min(ys) - arrow, max(ys) + arrow])
        if (min(xs) < frame[0] or min(ys) < frame[1]
                or max(xs) > frame[2] or max(ys) > frame[3]):
            outside.append(p.letter)
    if outside:
        raise PlacementError(
            'H1: %s would fall outside the frame. The remedy is to split the view or add a '
            'detail view -- a drafting decision made deliberately -- not to shrink the text.'
            % ', '.join(sorted(outside)))


def check_placement(placed, geometry_edges, frame, text_height_mm=std.TEXT_HEIGHT_MM,
                    notes=()):
    """Re-derive every hard constraint from the placed annotations. Returns complaints.

    **Independent of `place` on purpose** (section 5.6). It shares the extent model, because
    that is read from the font rather than judged, but it takes nothing else on trust: it
    re-tests H1, H2, H3 and H4 from the coordinates that were actually produced. A placer that
    certifies its own output has only proved it is self-consistent, which is not the claim
    anyone needs.

    `geometry_edges` is a list of ((x1, y1), (x2, y2)) for the projected view.
    `notes` is a list of `PlacedNote`. H2 and H3 do not distinguish them from dimension text
    -- a rectangle of digits misread because another rectangle of text touches it is the same
    failure whichever annotation the second one belongs to -- so they are checked together
    against each other rather than in two passes.
    """
    complaints = []
    clearance = TEXT_CLEARANCE_HEIGHTS * text_height_mm
    arrow = ARROWHEAD_LENGTH_HEIGHTS * text_height_mm
    ordered = sorted(placed, key=lambda p: p.letter)
    noted = sorted(notes, key=lambda n: str(n.key))

    # Every rectangle of text on the view, named the way a complaint should name it.
    boxes = [('callout %s' % p.letter, p.text_box) for p in ordered]
    boxes += [('note %s' % n.key, n.text_box) for n in noted]

    for p in ordered:
        if abs(p.dimension.value) < ZERO_MM:
            complaints.append('H5: %s carries a structurally-zero value' % p.letter)

    for i, (a_name, a_box) in enumerate(boxes):
        for b_name, b_box in boxes[i + 1:]:
            if _rects_overlap(a_box, b_box, clearance):
                complaints.append(
                    'H2: %s and %s are closer than one text height (%.2f mm)'
                    % (a_name, b_name, clearance))

    for name, box in boxes:
        for edge in geometry_edges:
            if _segment_hits_rect(edge, box):
                complaints.append('H3: %s sits on a projected edge' % name)
                break

    # Not a sixth constraint -- an assertion that the band arrangement did what it is for.
    # Notes take the innermost band precisely so a leader stays between the geometry and the
    # first dimension line, and that holds as long as a side's notes fit along that side. When
    # they do not they run past its end into another side's lanes, and this is what says so.
    for n in noted:
        for p in ordered:
            if _segments_cross(n.leader, p.dimension_line):
                complaints.append(
                    'the leader of note %s crosses the dimension line of %s -- the note band '
                    'is meant to sit inboard of every lane, so this means a side is carrying '
                    'more note than it has length for' % (n.key, p.letter))
                break

    for p in ordered:
        for other in ordered:
            if other.letter == p.letter:
                continue
            for witness in p.witnesses:
                if _segments_cross(witness, other.dimension_line):
                    complaints.append(
                        'H4: a witness line of %s crosses the dimension line of %s -- the '
                        'reader cannot tell which extension belongs to which measurement'
                        % (p.letter, other.letter))
                    break

    for p in ordered:
        xs = [p.text_box[0], p.text_box[2]]
        ys = [p.text_box[1], p.text_box[3]]
        for seg in [p.dimension_line] + list(p.witnesses):
            xs.extend([seg[0][0], seg[1][0]])
            ys.extend([seg[0][1], seg[1][1]])
        if p.dimension.axis == HORIZONTAL:
            xs = [min(xs) - arrow, max(xs) + arrow]
        else:
            ys = [min(ys) - arrow, max(ys) + arrow]
        if (min(xs) < frame[0] or min(ys) < frame[1]
                or max(xs) > frame[2] or max(ys) > frame[3]):
            complaints.append('H1: %s extends outside the frame' % p.letter)

    for n in noted:
        xs = [n.text_box[0], n.text_box[2], n.leader[0][0], n.leader[1][0]]
        ys = [n.text_box[1], n.text_box[3], n.leader[0][1], n.leader[1][1]]
        if (min(xs) < frame[0] or min(ys) < frame[1]
                or max(xs) > frame[2] or max(ys) > frame[3]):
            complaints.append('H1: note %s extends outside the frame' % n.key)

    return sorted(set(complaints))


def _segment_hits_rect(segment, rect):
    """Does a line segment touch a rectangle? Endpoint-inside counts; this is a clash test."""
    (x1, y1), (x2, y2) = segment
    if (rect[0] <= x1 <= rect[2] and rect[1] <= y1 <= rect[3]) or \
       (rect[0] <= x2 <= rect[2] and rect[1] <= y2 <= rect[3]):
        return True
    corners = [(rect[0], rect[1]), (rect[2], rect[1]),
               (rect[2], rect[3]), (rect[0], rect[3])]
    sides = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    return any(_segments_cross(segment, side) for side in sides)
