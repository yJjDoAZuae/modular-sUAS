"""IP-TEST-7 (doc/implementation/test_coverage.md): unit-level regression for plane2d.py.

`plane2d.py` had no coverage at all before this -- not even indirect, since its own module
docstring names it as shared construction for `boom_key.py`/`boom_web.py`, and neither of
those had a check either. This exercises every function against small, hand-verified shapes
(a disc, a rectangle, two overlapping rectangles) where the expected area has a closed form,
rather than against real swept geometry, so a wrong answer is caught against arithmetic
rather than against another measurement of the same kind.

`fillet_inner`/`fillet_outer` (morphological opening/closing) are checked against a bare
rectangle specifically because it isolates each to the one corner case it has a closed form
for there: opening rounds convex corners and leaves concave ones alone, closing is the
reverse, and a rectangle has four convex corners and no concave ones.

Run: freecadcmd check_plane2d.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
import plane2d as p2
from corner_common import is_entry_point

TOL = 1e-6          # exact polygon/circle area agreement expected to float precision
ARC_TOL = 1e-4       # offset()'s own measured faithfulness is ~5e-5; stay just above it


def _close(a, b, tol=TOL):
    return abs(a - b) <= tol * max(1.0, abs(b))


def main():
    doc = App.newDocument('check_plane2d')
    failures = []

    def check(label, got, want, tol=TOL):
        ok = _close(got, want, tol)
        print('  %-32s %14.6f %14.6f  %s' % (label, got, want, 'ok' if ok else 'FAIL'))
        if not ok:
            failures.append(label)

    # A minimal synthetic Params sheet, just the one alias enclosed()/report() need to read
    # -- not the real build_sheet() machinery, which belongs to parameters.py's own coverage,
    # not this module's.
    sheet = doc.addObject('Spreadsheet::Sheet', 'Params')
    sheet.set('A1', '20')
    sheet.setAlias('A1', 'test_reach')
    doc.recompute()

    # ------------------------------------------------------------
    # disc -- a filled circle. area = pi r^2, bbox is the circumscribing square.
    # ------------------------------------------------------------
    with C.tag('T1_'):
        d = p2.disc(doc, 'Disc', '10')
        doc.recompute()
        shape = d.Shape
        check('disc area r=10', p2.area(shape), math.pi * 10 * 10)
        bb = shape.BoundBox
        check('disc bbox xmin', bb.XMin, -10.0)
        check('disc bbox xmax', bb.XMax, 10.0)
        assert not p2.fragmented(shape), 'a single disc must not read as fragmented'

    with C.tag('T1b_'):
        d = p2.disc(doc, 'Disc', '5', x='3', y='4')
        doc.recompute()
        shape = d.Shape
        bb = shape.BoundBox
        check('offset disc bbox xmin', bb.XMin, 3.0 - 5.0)
        check('offset disc bbox ymax', bb.YMax, 4.0 + 5.0)

    # ------------------------------------------------------------
    # rect -- an axis-aligned rectangle, corner at (x, y). area = length * width.
    # ------------------------------------------------------------
    with C.tag('T2_'):
        r = p2.rect(doc, 'Rect', '20', '10', '0', '0')
        doc.recompute()
        shape = r.Shape
        check('rect area 20x10', p2.area(shape), 200.0)
        bb = shape.BoundBox
        check('rect bbox xmax', bb.XMax, 20.0)
        check('rect bbox ymax', bb.YMax, 10.0)

    # ------------------------------------------------------------
    # union -- De Morgan cut chain. Two overlapping rects: area = sum - overlap, exactly,
    # and the result must not read as fragmented (the whole reason union() exists instead
    # of Part::Fuse -- see its own docstring).
    #
    #   rect A = [0, 10] x [0, 10]     area 100
    #   rect B = [5, 15] x [0, 10]     area 100
    #   overlap = [5, 10] x [0, 10]    area 50
    #   union                          area 150
    # ------------------------------------------------------------
    with C.tag('T3_'):
        a = p2.rect(doc, 'A', '10', '10', '0', '0')
        b = p2.rect(doc, 'B', '10', '10', '5', '0')
        u = p2.union(doc, 'Union', [a, b], '20')
        doc.recompute()
        shape = u.Shape
        check('union of two overlapping rects', p2.area(shape), 150.0)
        assert not p2.fragmented(shape), (
            'union() must return one face for overlapping input, not the Fuse-style '
            'compound of abutting patches its own docstring warns about')

        # enclosed() -- positive margin when the rectangle genuinely contains the shape
        # (reach 20 against a union spanning x in [0, 15]), zero-or-negative when it does
        # not (reach shrunk to 12, which the union's x = 15 edge now exceeds).
        margin = p2.enclosed(doc, shape, 'test_reach')
        check('enclosed() margin, reach=20 truly encloses', margin, 20.0 - 15.0)

    with C.tag('T3c_'):
        # A shape whose bbox genuinely exceeds the 'test_reach' = 20 alias: enclosed() must
        # report a non-positive margin, the exact signal report() treats as TRUNCATED.
        far = p2.rect(doc, 'Far', '10', '10', '15', '0')   # xmax = 25 > reach 20
        doc.recompute()
        margin = p2.enclosed(doc, far.Shape, 'test_reach')
        ok = margin <= 0
        print('  %-32s %14.6f %14s  %s'
              % ('enclosed() negative past reach', margin, '<= 0', 'ok' if ok else 'FAIL'))
        if not ok:
            failures.append('enclosed() negative-margin case')

    # Two DISJOINT rects: union() still must not report shared edges (the actual invariant
    # fragmented() checks -- see its own docstring: disjoint pieces are legitimate).
    with C.tag('T3b_'):
        a = p2.rect(doc, 'A', '10', '10', '0', '0')
        b = p2.rect(doc, 'B', '10', '10', '30', '0')   # far apart, no overlap
        u = p2.union(doc, 'Union', [a, b], '50')
        doc.recompute()
        shape = u.Shape
        check('union of two disjoint rects', p2.area(shape), 200.0)
        assert not p2.fragmented(shape), 'disjoint pieces sharing no edge must not be flagged'

    # ------------------------------------------------------------
    # merge -- union() with one piece: an identity on area for a source that is already
    # one face, exercising the code path union() takes with len(pieces) == 1.
    # ------------------------------------------------------------
    with C.tag('T4_'):
        a = p2.rect(doc, 'Src', '10', '10', '0', '0')
        m = p2.merge(doc, 'Merged', a, '20')
        doc.recompute()
        check('merge of a single rect is an identity', p2.area(m.Shape), 100.0)

    # ------------------------------------------------------------
    # offset -- OpenSCAD's offset(r=value). Outward growth of a WxH rect by d:
    #   new area = (W + 2d)(H + 2d) - 4d^2 + pi*d^2   (square corners replaced by quarter-arcs)
    # Inward shrink by d (erosion of a convex rectangle -- no arcs needed):
    #   new area = (W - 2d)(H - 2d)
    # ------------------------------------------------------------
    with C.tag('T5_'):
        src = p2.rect(doc, 'Src', '10', '10', '0', '0')
        grown = p2.offset(doc, 'Grown', src, '2')
        doc.recompute()
        want = (10 + 4) * (10 + 4) - 4 * 4 + math.pi * 4
        check('outward offset +2 of 10x10 rect', p2.area(grown.Shape), want, ARC_TOL)

    with C.tag('T5b_'):
        src = p2.rect(doc, 'Src', '10', '10', '0', '0')
        shrunk = p2.offset(doc, 'Shrunk', src, '-2')
        doc.recompute()
        check('inward offset -2 of 10x10 rect', p2.area(shrunk.Shape), 6.0 * 6.0, ARC_TOL)

    # ------------------------------------------------------------
    # erode_difference -- erosion(A - B, r) == erosion(A, r) - dilation(B, r), for a window
    # (a big rect minus a smaller centered rect), against the closed form for axis-aligned
    # rectangles. Erosion of a convex rectangle keeps sharp corners (confirmed by T5b above);
    # DILATION does not -- it is offset()'s outward case, which rounds corners with a
    # quarter-circle arc (confirmed by T5). Both operands of the identity have to use the
    # form that matches what OCCT's offset actually produces, not a naive same-shape-bigger
    # assumption -- an earlier draft of this check used a sharp-cornered dilation and flagged
    # a false failure against `erode_difference`'s real, correct output.
    #
    #   A = [0, 20] x [0, 20]     erosion(A, 2), sharp        = [2, 18] x [2, 18]     area 256
    #   B = [8, 12] x [8, 12]     dilation(B, 2), rounded      area (4+2*2)^2 - 4*2^2 + pi*2^2
    #                                                          = 64 - 16 + 4*pi = 60.566371
    #   erosion(A - B, 2) = 256 - 60.566371 = 195.433629
    # ------------------------------------------------------------
    with C.tag('T6_'):
        outer = p2.rect(doc, 'Outer', '20', '20', '0', '0')
        inner = p2.rect(doc, 'Inner', '4', '4', '8', '8')
        eroded = p2.erode_difference(doc, 'Erode', outer, [inner], '2')
        doc.recompute()
        dilation_of_inner = (4 + 2 * 2) ** 2 - 4 * 2 ** 2 + math.pi * 2 ** 2
        want = 16.0 * 16.0 - dilation_of_inner
        check('erode_difference of a window', p2.area(eroded.Shape), want, ARC_TOL)
        assert eroded.Shape.isValid(), 'erode_difference must produce a valid shape'

    # ------------------------------------------------------------
    # fillet_inner / fillet_outer -- morphological opening/closing. Opening (fillet_inner)
    # rounds CONVEX corners smaller than the structuring disc and leaves concave ones alone;
    # closing (fillet_outer) is the reverse. A bare rectangle has four convex corners and no
    # concave ones, so it isolates each function to the one case it actually has a closed
    # form for here: fillet_inner removes exactly 4 * (r^2 - (pi/4) r^2) at r = 2 (small
    # enough that no two corners interact), and fillet_outer, with nothing concave to act
    # on, is an outward-then-inward round trip on a convex shape -- an identity.
    # ------------------------------------------------------------
    with C.tag('T7_'):
        src = p2.rect(doc, 'Src', '10', '10', '0', '0')
        doc.recompute()
        src_area = p2.area(src.Shape)

        radius = '2'
        filleted = p2.fillet_inner(doc, 'Fillet', src, radius, '30')
        doc.recompute()
        f_area = p2.area(filleted.Shape)
        removed_per_corner = 2.0 * 2.0 - (math.pi / 4.0) * 2.0 * 2.0
        check('fillet_inner rounds all 4 convex corners',
              src_area - f_area, 4 * removed_per_corner, ARC_TOL)
        assert filleted.Shape.isValid(), 'fillet_inner must produce a valid shape'
        assert not p2.fragmented(filleted.Shape), 'fillet_inner output must be one face'

    with C.tag('T8_'):
        # A single rect has no concave corners for fillet_outer to act on differently from a
        # plain outward-then-inward round trip of a convex shape, which is a no-op on area
        # to the offset chain's own tolerance -- a genuine identity check, not a bound.
        src = p2.rect(doc, 'Src', '10', '10', '0', '0')
        doc.recompute()
        src_area = p2.area(src.Shape)
        outered = p2.fillet_outer(doc, 'FilletOuter', src, '1', '30')
        doc.recompute()
        check('fillet_outer on a convex rect is a no-op', p2.area(outered.Shape), src_area,
              ARC_TOL)
        assert outered.Shape.isValid()
        assert not p2.fragmented(outered.Shape)

    # ------------------------------------------------------------
    # report -- the one-line measured-vs-reference summary. True when everything agrees,
    # False on any single complaint (tolerance here, not TRUNCATED/FRAGMENTED, which the
    # cases above already exercise the underlying enclosed()/fragmented() calls for).
    # ------------------------------------------------------------
    with C.tag('T9_'):
        r = p2.rect(doc, 'Rect', '10', '10', '0', '0')
        doc.recompute()
        print('  report(), correct reference:')
        ok_report = p2.report(doc, 'rect ok', r.Shape, 100.0, 'test_reach')
        if not ok_report:
            failures.append('report() should have passed a correct reference')

        print('  report(), wrong reference:')
        bad_report = p2.report(doc, 'rect bad', r.Shape, 50.0, 'test_reach')
        if bad_report:
            failures.append('report() should have failed a reference off by 2x')

    # ------------------------------------------------------------
    # area / fragmented -- edge cases the geometric tests above do not reach.
    # ------------------------------------------------------------
    class _NoFaces:
        Faces = []

    nan_result = p2.area(_NoFaces())
    ok = nan_result != nan_result   # nan is the only float that is not equal to itself
    print('  %-32s %14s %14s  %s' % ('area() with no faces -> nan', str(nan_result), 'nan',
                                     'ok' if ok else 'FAIL'))
    if not ok:
        failures.append('area() no-faces nan')

    print('')
    print('check_plane2d: %d failure(s)' % len(failures))
    for f in failures:
        print('  FAILED: %s' % f)

    App.closeDocument(doc.Name)
    return 1 if failures else 0


if is_entry_point(__name__):
    # The flush is not decoration: under `freecadcmd` a `sys.exit` with buffered stdout loses
    # the whole report, so the run looks like it printed nothing rather than like it failed.
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
