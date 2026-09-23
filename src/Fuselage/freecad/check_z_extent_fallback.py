"""IP-TEST-11 (doc/implementation/test_coverage.md): a committed regression for IP-FC-127
(freecad_migration.md), which had none until now.

`cowl_interior.z_extent` finds a body's real axial extent by bisecting from a starting point
inside the solid, probed at seven fixed fractions of `Shape.BoundBox` -- which is not tight on
these B-spline solids (see the function's own docstring). On the nose cowl and the tail (the
only kinds any committed check builds today, via `check_cowl_interior.py`/
`check_vase_printable.py`), the box is loose enough (139% of the part) that all seven probes
still land inside it. IP-FC-127 found one real part where they do not: the nose tip is 7.000 mm
tall inside a 61.159 mm box (874%), so every probe misses and the function must fall back to a
tessellation-seeded search instead of raising "the body does not section anywhere in its own
bounding box" -- a false statement about a body that sections everywhere in its real 7 mm
extent. Nothing in production calls `z_extent` on the tip today (only cowls are shelled), so
this fallback path was "latent rather than live" per the item's own words, and stays untested
by every check that touches z_extent -- until now.

The nose tip is small and fast to build (7 faces per IP-FC-126), so this is cheap to run
routinely, unlike the shell kinds' multi-minute builds.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import cowl_interior as ci
import cowl_nose_tip
from corner_common import is_entry_point

# IP-FC-127's own measured figures: box -100.0000..0.0000 (874% of the 7.000 mm part),
# real extent -6.9999..-0.0009.
EXPECT_LO, EXPECT_HI = -6.9999, -0.0009
TOL_MM = 1e-3


def main():
    doc = App.newDocument('z_extent_fallback')
    tip = cowl_nose_tip.emit(doc)
    shape = tip.Shape
    bb = shape.BoundBox
    print('nose_tip: %d solid(s) valid=%s' % (len(shape.Solids), shape.isValid()))
    print('  BoundBox z: %.4f .. %.4f  (span %.4f mm)' % (bb.ZMin, bb.ZMax, bb.ZLength))

    fail = []
    if not shape.isValid() or len(shape.Solids) != 1:
        fail.append('nose_tip did not build to a single valid solid')

    lo, hi = ci.z_extent(shape)
    print('  z_extent  : %.4f .. %.4f  (span %.4f mm)' % (lo, hi, hi - lo))
    print('  expected  : %.4f .. %.4f  (IP-FC-127)' % (EXPECT_LO, EXPECT_HI))

    # The real point of this check: the bounding box is loose enough (874%) that the cheap
    # probes must have failed and the tessellation fallback must have fired -- if the box were
    # tight, this check would not be exercising the path it exists to exercise.
    if bb.ZLength < 3 * (hi - lo):
        fail.append('bounding box is not loose enough to force the fallback path -- this '
                    'check would not be testing what it claims to')

    if abs(lo - EXPECT_LO) > TOL_MM or abs(hi - EXPECT_HI) > TOL_MM:
        fail.append('z_extent moved from its IP-FC-127 measured value by more than %.4f mm'
                    % TOL_MM)

    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
