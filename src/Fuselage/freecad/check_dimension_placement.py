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


def _placement_signature(placed):
    """A hashable, fully-ordered description of a layout, for the determinism test."""
    return tuple((p.letter, p.side, p.lane, round(p.offset, 9),
                  tuple(round(v, 9) for v in p.text_box)) for p in placed)


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
