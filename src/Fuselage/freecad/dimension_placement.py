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

# The arrowhead allowance. Section 5.2's H1 counts arrowheads in an annotation's extent, and
# they cannot be measured headlessly -- `getArrowPositions()` returns the origin. They are the
# same on every annotation, so a fixed multiple of the text height is the whole of the model.
ARROWHEAD_LENGTH_HEIGHTS = 1.0

# A value whose magnitude is under this is structurally zero (H5). It is not a fit tolerance
# and must not be confused with one: printed clearances in this project are around 0.1 mm, two
# orders of magnitude above this. This asks "did the expression evaluate to nothing", which is
# a question about the design, not about manufacturing.
ZERO_MM = 1.0e-9

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
    `value`   the model value in mm -- what the table will carry, used here only for
              magnitude ordering and the H5 zero test
    """

    def __init__(self, letter, p1, p2, axis, value):
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


def _text_box(centre, text_height_mm):
    """The bound on a lettered callout's text, centred on a point.

    Every callout is one character from `CALLOUT_ALPHABET`, so this is the same size for all
    of them -- section 5.2's uniform bound. Being uniform is what makes it safe to be
    conservative: it shifts the layout without distorting it.
    """
    half_w = std.callout_width_mm(text_height_mm) / 2.0
    half_h = text_height_mm / 2.0
    return (centre[0] - half_w, centre[1] - half_h,
            centre[0] + half_w, centre[1] + half_h)


def place(dimensions, geometry_bbox, frame=None, text_height_mm=std.TEXT_HEIGHT_MM):
    """Place every dimension, or raise `PlacementError` naming the ones that would not go.

    `geometry_bbox`  (x_min, y_min, x_max, y_max) of the projected view, in view coordinates
    `frame`          the same, for the region placements must stay inside (H1). None skips
                     the containment check, which is only correct in a test.

    Returns a list of `Placed`, ordered by (axis, side, lane, letter) so the result is a
    stable sequence rather than whatever order the input arrived in.
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

    gap = FIRST_LANE_GAP_HEIGHTS * text_height_mm
    pitch = LANE_PITCH_HEIGHTS * text_height_mm
    clearance = TEXT_CLEARANCE_HEIGHTS * text_height_mm

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
            for dimension in by_side.get(side, []):
                placement = _place_one(dimension, side, lanes, geometry_bbox,
                                       gap, pitch, clearance, text_height_mm)
                placed.append(placement)

    if frame is not None:
        _require_containment(placed, frame, text_height_mm)

    placed.sort(key=lambda p: (p.dimension.axis, p.side, p.lane, p.letter))
    return placed


def _place_one(dimension, side, lanes, geometry_bbox, gap, pitch, clearance, text_height_mm):
    """Give one dimension the innermost lane whose text it does not collide with (H2).

    `lanes` is a list of lists of (text_box, span) for what is already in each lane. It is
    mutated. Section 5.3 item 3 wants the fewest lanes, so this takes the first lane that fits
    rather than opening a new one -- two dimensions at different positions along the same
    offset legitimately share a lane.

    **Sharing requires disjoint spans, not merely non-overlapping text.** Two nested spans at
    one offset would draw collinear dimension lines, and the outer one's witness lines would
    cross the inner one's line -- which is H4, and it is the specific failure that nesting by
    magnitude exists to prevent. Testing only the text boxes lets a small dimension and a
    large one that contains it share lane 0, undoing the nesting the sort just established.
    """
    x_min, y_min, x_max, y_max = geometry_bbox
    lo, hi = dimension.span()
    midpoint = (lo + hi) / 2.0

    index = 0
    while True:
        while len(lanes) <= index:
            lanes.append([])
        offset = gap + index * pitch

        if side == 'below':
            line_y = y_min - offset
            line = ((lo, line_y), (hi, line_y))
            text = _text_box((midpoint, line_y + text_height_mm * 0.6), text_height_mm)
            witnesses = [((dimension.p1[0], dimension.p1[1]), (dimension.p1[0], line_y)),
                         ((dimension.p2[0], dimension.p2[1]), (dimension.p2[0], line_y))]
        elif side == 'above':
            line_y = y_max + offset
            line = ((lo, line_y), (hi, line_y))
            text = _text_box((midpoint, line_y + text_height_mm * 0.6), text_height_mm)
            witnesses = [((dimension.p1[0], dimension.p1[1]), (dimension.p1[0], line_y)),
                         ((dimension.p2[0], dimension.p2[1]), (dimension.p2[0], line_y))]
        elif side == 'left':
            line_x = x_min - offset
            line = ((line_x, lo), (line_x, hi))
            text = _text_box((line_x, midpoint), text_height_mm)
            witnesses = [((dimension.p1[0], dimension.p1[1]), (line_x, dimension.p1[1])),
                         ((dimension.p2[0], dimension.p2[1]), (line_x, dimension.p2[1]))]
        else:
            line_x = x_max + offset
            line = ((line_x, lo), (line_x, hi))
            text = _text_box((line_x, midpoint), text_height_mm)
            witnesses = [((dimension.p1[0], dimension.p1[1]), (line_x, dimension.p1[1])),
                         ((dimension.p2[0], dimension.p2[1]), (line_x, dimension.p2[1]))]

        clear_text = not any(_rects_overlap(text, other, clearance)
                             for other, _ in lanes[index])
        clear_span = not any(_spans_overlap((lo, hi), other) for _, other in lanes[index])
        if clear_text and clear_span:
            lanes[index].append((text, (lo, hi)))
            return Placed(dimension, side, index, offset, text, line, witnesses)
        index += 1


def _require_containment(placed, frame, text_height_mm):
    """H1. Everything -- text, line, arrowheads, witnesses -- inside the frame."""
    arrow = ARROWHEAD_LENGTH_HEIGHTS * text_height_mm
    outside = []
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


def check_placement(placed, geometry_edges, frame, text_height_mm=std.TEXT_HEIGHT_MM):
    """Re-derive every hard constraint from the placed annotations. Returns complaints.

    **Independent of `place` on purpose** (section 5.6). It shares the extent model, because
    that is read from the font rather than judged, but it takes nothing else on trust: it
    re-tests H1, H2, H3 and H4 from the coordinates that were actually produced. A placer that
    certifies its own output has only proved it is self-consistent, which is not the claim
    anyone needs.

    `geometry_edges` is a list of ((x1, y1), (x2, y2)) for the projected view.
    """
    complaints = []
    clearance = TEXT_CLEARANCE_HEIGHTS * text_height_mm
    arrow = ARROWHEAD_LENGTH_HEIGHTS * text_height_mm
    ordered = sorted(placed, key=lambda p: p.letter)

    for p in ordered:
        if abs(p.dimension.value) < ZERO_MM:
            complaints.append('H5: %s carries a structurally-zero value' % p.letter)

    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if _rects_overlap(a.text_box, b.text_box, clearance):
                complaints.append(
                    'H2: callouts %s and %s are closer than one text height (%.2f mm)'
                    % (a.letter, b.letter, clearance))

    for p in ordered:
        for edge in geometry_edges:
            if _segment_hits_rect(edge, p.text_box):
                complaints.append('H3: callout %s sits on a projected edge' % p.letter)
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
