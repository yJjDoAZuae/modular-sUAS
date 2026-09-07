"""IP-FC-21: does the placer satisfy the hard constraints it claims to?

`dimension_placement.place` produces a layout and `dimension_placement.check_placement`
re-derives `dimension_scheme.md` section 5.2's hard constraints from the result. This runs the
second over the first, on cases chosen for difficulty rather than for coverage -- which is
section 5.7's rule, applied to the geometry the solver actually sees rather than to variants,
because the solver takes 2D coordinates and does not know what a variant is.

**Why the checker is worth running against the placer at all**, when both live in the same
file: it is not a tautology, and it earned that on its first input. The placer's original lane
rule let a small dimension and a larger one containing it share lane 0, because their *text*
did not collide -- which drew two collinear dimension lines and put a witness line through
one of them. The checker named it as H4. A placer that certifies its own output would have
reported success.

Neither FreeCAD nor a built part is needed, so this runs under any interpreter that can reach
`fontTools` for the font pin -- in practice FreeCAD's, since that is where `fontTools` is.

Run:

    freecadcmd check_dimension_placement.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dimension_placement as dp

NEWLINE = chr(10)
import drawing_standard as std

from corner_common import is_entry_point


# A plain rectangular outline, the shape the corner and bulkhead both project to from the
# front. Frame is the ANSI A sheet's printable area, centred on the view.
BBOX = (-30.0, -20.0, 30.0, 20.0)
EDGES = [((-30.0, -20.0), (30.0, -20.0)), ((30.0, -20.0), (30.0, 20.0)),
         ((30.0, 20.0), (-30.0, 20.0)), ((-30.0, 20.0), (-30.0, -20.0))]
FRAME = (-120.0, -95.0, 120.0, 95.0)


def _dim(letter, p1, p2, axis, value):
    return dp.Dimension(letter, p1, p2, axis, value)


def case_nested():
    """Three widths from a common datum -- the case section 5.3 item 1 is about."""
    return [_dim('A', (-30, -20), (-10, -20), dp.HORIZONTAL, 20.0),
            _dim('B', (-30, -20), (10, -20), dp.HORIZONTAL, 40.0),
            _dim('C', (-30, -20), (30, -20), dp.HORIZONTAL, 60.0),
            _dim('D', (-30, -20), (-30, 0), dp.VERTICAL, 20.0),
            _dim('E', (-30, -20), (-30, 20), dp.VERTICAL, 40.0)]


def case_interleaved():
    """Spans that overlap without nesting. No lane order fixes this; sides have to."""
    return [_dim('A', (-30, -20), (0, -20), dp.HORIZONTAL, 30.0),
            _dim('B', (-10, -20), (30, -20), dp.HORIZONTAL, 40.0)]


def case_coincident_magnitudes():
    """Four equal-length spans. Every tie falls to the letter, which is the total order."""
    return [_dim(letter, (x, -20), (x + 10, -20), dp.HORIZONTAL, 10.0)
            for letter, x in zip('ABCD', (-30, -15, 0, 15))]


def case_dense():
    """Twelve dimensions on a small outline -- the smallest variant, where room is least."""
    dims = []
    for i, letter in enumerate('ABCDEFGH'):
        dims.append(_dim(letter, (-30, -20), (-30 + 7.5 * (i + 1), -20),
                         dp.HORIZONTAL, 7.5 * (i + 1)))
    for i, letter in enumerate('JKLM'):
        dims.append(_dim(letter, (-30, -20), (-30, -20 + 10.0 * (i + 1)),
                         dp.VERTICAL, 10.0 * (i + 1)))
    return dims


def case_four_interleaved():
    """Four spans that pairwise interleave. Two sides cannot separate four of them."""
    return [_dim('A', (-30, -20), (0, -20), dp.HORIZONTAL, 30.0),
            _dim('B', (-10, -20), (30, -20), dp.HORIZONTAL, 40.0),
            _dim('C', (-25, -20), (5, -20), dp.HORIZONTAL, 30.0),
            _dim('D', (-5, -20), (25, -20), dp.HORIZONTAL, 30.0)]


CASES = (('nested from a datum', case_nested),
         ('interleaved spans', case_interleaved),
         ('equal magnitudes', case_coincident_magnitudes),
         ('dense, twelve dimensions', case_dense))


# --------------------------------------------------------------------------------------
# OQ-DES-D2's callouts, which the decision recorded as a risk it had not measured
# --------------------------------------------------------------------------------------

# The corner's interface annotations, as OQ-DES-D2 says they read. Four of the corner's ten
# interface parameters reach the reader through one of these rather than through a dimension
# line, which is section 3's fourth gap: the parameter is a nominal, the part is built to the
# nominal plus a clearance, and there is no pair of faces the nominal is the distance between.
#
# Two forms, because section 5.1 has two products and section 5.2 is explicit that they do not
# share an extent model. On a **family sheet** the numbers live in the value table and the note
# names the letters carrying them; on a **single-variant sheet** the note carries the numbers
# themselves. Written at U = 1 with 3/16 in panel, the size the parts were flown at.
DIA = chr(216)          # U+00D8. U+2300 is the drafting diameter sign and osifont lacks it.

NOTES_FAMILY = (
    ('bore', (-6.0, -6.0), ('%sA BORE' % DIA, 'FOR %sB LONGERON' % DIA,
                            'C DIA CLEARANCE')),
    ('pocket', (-4.0, 8.0), ('D POCKET', 'FOR E PANEL', 'F CLEARANCE')),
    ('socket', (6.0, -8.0), ('G SOCKET', 'FOR H POST', 'K CLEARANCE')),
    ('mold', (7.0, 7.0), ('RL MOLD LINE',)),
)

NOTES_VARIANT = (
    ('bore', (-6.0, -6.0), ('%s4.10 BORE' % DIA, 'FOR %s4.00 LONGERON' % DIA,
                            '0.10 DIA CLEARANCE')),
    ('pocket', (-4.0, 8.0), ('4.86 POCKET', 'FOR 4.76 PANEL', '0.10 CLEARANCE')),
    ('socket', (6.0, -8.0), ('1.30 SOCKET', 'FOR 1.20 POST', '0.05 CLEARANCE')),
    ('mold', (7.0, 7.0), ('R10.00 MOLD LINE',)),
)

# The corner's mid-bay section at U = 1 is 20 mm square. Drawn 1:1 and centred, which is the
# most generous scale a real sheet would use for it, so a refusal here is a refusal at every
# scale that leaves the view readable.
CORNER_BBOX = (-10.0, -10.0, 10.0, 10.0)
CORNER_EDGES = [((-10.0, -10.0), (10.0, -10.0)), ((10.0, -10.0), (10.0, 10.0)),
                ((10.0, 10.0), (-10.0, 10.0)), ((-10.0, 10.0), (-10.0, -10.0))]


def corner_notes(source):
    return [dp.Note(key, anchor, lines) for key, anchor, lines in source]


def corner_dimensions(valued):
    """Six linear dimensions on that section, three each way.

    `valued` False is the family sheet, where every annotation is one letter; True is the
    single-variant sheet, where the annotation is the number and the widths differ.
    """
    spans = (('A', dp.HORIZONTAL, -10.0, -2.4), ('B', dp.HORIZONTAL, -10.0, 2.5),
             ('C', dp.HORIZONTAL, -10.0, 10.0), ('D', dp.VERTICAL, -10.0, -2.4),
             ('E', dp.VERTICAL, -10.0, 4.76), ('F', dp.VERTICAL, -10.0, 10.0))
    out = []
    for letter, axis, lo, hi in spans:
        p1 = (lo, -10.0) if axis == dp.HORIZONTAL else (-10.0, lo)
        p2 = (hi, -10.0) if axis == dp.HORIZONTAL else (-10.0, hi)
        value = hi - lo
        out.append(dp.Dimension(letter, p1, p2, axis, value,
                                std.format_length(value) if valued else None))
    return out


def centred_frame(width, height):
    """A sheet region as the placer sees it: view coordinates, origin at the view centre."""
    return (-width / 2.0, -height / 2.0, width / 2.0, height / 2.0)


# The compacted family table at its widest, from `check_table_width.py` -- the panelled corner,
# 11 columns abreast of a 3-column panel block. Recorded here rather than recomputed because
# this checker does not read the family data, and cross-checked there: the width budget it
# reports is derived from `VIEW_WIDTH_RECORDED_MM` below, so the two cannot drift apart without
# one of them saying so.
TABLE_RECORDED_MM = 95.1
TABLE_RECORDED_ROWS = 10

# The title block, taken from the pinned template rather than named here. It was a literal
# 120 x 40 for a few hours -- a point inside OQ-DES-D5's envelope, written down before the
# template existed -- and that measured 75.7 % where the template's own 130 x 46 measures
# 75.4 %. A checker asserting a requirement against a sheet the build does not use is not
# asserting it.
TITLE_BLOCK_MM = (std.TEMPLATE_TITLE_BLOCK_MM[2], std.TEMPLATE_TITLE_BLOCK_MM[3])


# The regions a view actually gets, under the sheet OQ-DES-D5 decided on 2026-08-22: the title
# block and the value table side by side in a band across the bottom, the view the full width
# above them. A single-variant sheet carries no family table, so its view is bounded by the
# title block alone.
def sheet_regions():
    table_h = std.table_height_mm(TABLE_RECORDED_ROWS)
    family = std.best_view(TABLE_RECORDED_MM, table_h, *TITLE_BLOCK_MM)
    variant = std.best_view(0.0, 0.0, *TITLE_BLOCK_MM)
    return (('with the value table beside the title block', family[1], family[2]),
            ('with no family table on the sheet', variant[1], variant[2]))


# What `check_table_width.py` records the view as needing, so a table beside it can be sized.
# Re-derived below on every run: if the annotation set changes, the two disagree and say so,
# rather than the table being budgeted against a view that no longer exists.
#
# **84.5 until 2026-09-07, and the disagreement is what the pair is for.** The number is the
# narrowest region four leader notes will place in, so it is set by how wide the notes are --
# and the text width model was 32.8% short, because ISO 3098's `h` is a *cap height* and the
# glyph advances in the font are fractions of the *em*. Correcting it widened every note and
# with it the region they need, from 84.5 to 117.5 mm on the family sheet and from 100.0 to
# 136.0 on the single-variant one. Nothing recorded the new value, so the table beside the
# view was being budgeted 33 mm that the view needs.
VIEW_WIDTH_RECORDED_MM = 117.5


def narrowest_view_width(notes, valued, height_mm, step_mm=0.5):
    """The narrowest region this annotation set places in, to a step of half a millimeter.

    Searched rather than solved: the placer is not invertible -- a narrower region can change
    the note side assignment, which changes the lane standoffs, which changes everything -- so
    the honest way to ask "how much does this need" is to try.
    """
    def places(width):
        try:
            dp.place(corner_dimensions(valued), CORNER_BBOX,
                     centred_frame(width, height_mm), CORNER_EDGES,
                     notes=corner_notes(notes))
            return True
        except dp.PlacementError:
            return False

    # Coarse then fine, because a refusal is the expensive direction: it is the case where
    # every note-side assignment is tried and every one of them fails.
    coarse = step_mm * 20.0
    width = 20.0
    while width <= 400.0 and not places(width):
        width += coarse
    if width > 400.0:
        return None
    fine = width - coarse + step_mm
    while fine < width and not places(fine):
        fine += step_mm
    return min(fine, width)


def _placement_signature(placed):
    """A hashable, fully-ordered description of a layout, for the determinism test."""
    return tuple((p.letter, p.side, p.lane, round(p.offset, 9),
                  tuple(round(v, 9) for v in p.text_box)) for p in placed)


def _note_signature(layout):
    """The same, for the notes -- side and box, which is everything a note's placement is."""
    return tuple((str(n.key), n.side, tuple(round(v, 9) for v in n.text_box))
                 for n in sorted(layout.notes, key=lambda n: str(n.key)))


def main():
    fail = []
    print('CHECK:: dimension placement')
    print('  font pin           %s' % (std.verify_font() or 'holds'))
    for problem in std.verify_font():
        fail.append('font pin: ' + problem)

    for name, build in CASES:
        dims = build()
        try:
            placed = dp.place(dims, BBOX, FRAME, EDGES)
        except dp.PlacementError as exc:
            print('  %-26s PLACEMENT REFUSED: %s' % (name, exc))
            fail.append('%s: refused, %s' % (name, exc))
            continue

        complaints = dp.check_placement(placed, EDGES, FRAME)
        lanes = max(p.lane for p in placed) + 1
        print('  %-26s %2d dimensions, %d lanes, %s'
              % (name, len(placed), lanes, complaints or 'clean'))
        for complaint in complaints:
            fail.append('%s: %s' % (name, complaint))

        # Section 5.5: the same input produces the same output regardless of the order it
        # arrived in. Reversal is the cheapest input permutation that is not the identity.
        again = dp.place(list(reversed(dims)), BBOX, FRAME, EDGES)
        if _placement_signature(placed) != _placement_signature(again):
            fail.append('%s: placement depends on input order, so it is not reproducible'
                        % name)

    print('  --- OQ-DES-D2 callouts, the risk the decision recorded ---')
    for region, width, height in sheet_regions():
        frame = centred_frame(width, height)
        for product, notes, valued in (('family sheet', NOTES_FAMILY, False),
                                       ('single-variant', NOTES_VARIANT, True)):
            label = '%s, %s' % (product, region)
            dims = corner_dimensions(valued)
            placed_notes = corner_notes(notes)
            widest = max(n.size()[0] for n in placed_notes)
            try:
                layout = dp.place(dims, CORNER_BBOX, frame, CORNER_EDGES,
                                  notes=placed_notes)
            except dp.PlacementError as exc:
                print('  %-42s %5.1f mm widest note, REFUSED: %s'
                      % (label, widest, str(exc).split(NEWLINE)[0]))
                continue
            complaints = dp.check_placement(layout, CORNER_EDGES, frame,
                                            notes=layout.notes)
            lanes = max(p.lane for p in layout) + 1
            sides = ','.join('%s %s' % (n.key, n.side) for n in layout.notes)
            print('  %-42s %5.1f mm widest note, %d lanes, %s  [%s]'
                  % (label, widest, lanes, complaints or 'clean', sides))
            for complaint in complaints:
                fail.append('%s: %s' % (label, complaint))

            # Section 5.5, and it bites harder here than on a bare dimension set: the note
            # side is chosen by a search, so an input-order dependence would move annotations
            # between sides of the sheet rather than between lanes.
            again = dp.place(list(reversed(dims)), CORNER_BBOX, frame, CORNER_EDGES,
                             notes=list(reversed(placed_notes)))
            if (_placement_signature(layout) != _placement_signature(again)
                    or _note_signature(layout) != _note_signature(again)):
                fail.append('%s: the layout depends on the order its annotations arrived in'
                            % label)

    height = std.frame_region_mm()[3]
    needed = narrowest_view_width(NOTES_FAMILY, False, height)
    variant_needed = narrowest_view_width(NOTES_VARIANT, True, height)
    print('  narrowest view region  %s mm family sheet, %s mm single-variant, at %.1f mm tall'
          % (needed, variant_needed, height))
    if needed != VIEW_WIDTH_RECORDED_MM:
        fail.append('the family sheet now needs %s mm of view, not the %.1f mm '
                    'check_table_width.py budgets a table against'
                    % (needed, VIEW_WIDTH_RECORDED_MM))

    # The requirement OQ-DES-D5 was decided against, checked on the sheet it decided on rather
    # than left as a figure in a document.
    frame = std.frame_region_mm()
    placement = std.best_view(TABLE_RECORDED_MM,
                              std.table_height_mm(TABLE_RECORDED_ROWS), *TITLE_BLOCK_MM)
    share = placement[3] / (frame[2] * frame[3])
    print('  the decided sheet       view %.1f%% of the frame, placed as a %s'
          % (100.0 * share, placement[0]))
    if share < std.VIEW_SHARE:
        fail.append('the view gets %.1f%% of the frame, under the %.0f%% OQ-DES-D5 requires'
                    % (100.0 * share, 100.0 * std.VIEW_SHARE))

    print('  --- refusals, which must happen ---')
    for label, dims, frame, edges in (
            ('structurally-zero value',
             [_dim('A', (0, 0), (0, 0), dp.HORIZONTAL, 0.0)], FRAME, EDGES),
            ('repeated callout letter',
             [_dim('A', (-30, -20), (0, -20), dp.HORIZONTAL, 30.0),
              _dim('A', (-30, -20), (10, -20), dp.HORIZONTAL, 40.0)], FRAME, EDGES),
            ('frame too small to contain',
             case_nested(), (-35.0, -25.0, 35.0, 25.0), EDGES),
            # Four mutually interleaved spans. Two sides hold two each, and the two sharing a
            # side interleave, so no lane order avoids H4 -- the case section 5.6 exists for.
            ('unavoidable H4 crossing', case_four_interleaved(), FRAME, EDGES),
            # An edge lying exactly where the only available callout position falls.
            ('callout on a projected edge',
             [_dim('A', (-30, -20), (30, -20), dp.HORIZONTAL, 60.0)], FRAME,
             EDGES + [((-40.0, -28.4), (40.0, -28.4))])):
        try:
            dp.place(dims, BBOX, frame, edges)
            print('  %-26s NOT REFUSED' % label)
            fail.append('%s was placed when it should have been refused' % label)
        except dp.PlacementError as exc:
            print('  %-26s refused: %s' % (label, str(exc).split('.')[0].split(NEWLINE)[0]))

    for label, letter in (('I reads as 1', 'I'), ('O reads as 0', 'O'),
                          ('Q reads as 0', 'Q')):
        try:
            _dim(letter, (0, 0), (1, 0), dp.HORIZONTAL, 1.0)
            fail.append('%r was accepted as a callout letter' % letter)
            print('  %-26s NOT REFUSED' % label)
        except ValueError:
            print('  %-26s refused' % label)

    print('  %s' % ('FAIL:\n    ' + '\n    '.join(fail) if fail
                    else 'ok -- every case places and every refusal refuses'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
