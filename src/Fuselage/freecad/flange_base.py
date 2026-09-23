"""IP-FC-9: bulkhead_flange_positive's base profile as a Part:: CSG tree.

Built at the DERIVED parameters for U=1.0 end_bolt 3/16in, not the hand driver's constants --
see IP-FC-41. Its own parameter sheet for now; the pieces are wired together once every
module is ported and the whole part can be re-anchored in one step.

The profile looks like it needs a sketch and does not. The larger of the two polygons is

    (0,0) (0,5.1375) (-40,5.1375) (-40,3.9375) (-8.5625,3.9375) (-8.5625,-8) (-8,-8)

whose only non-axis-aligned edge is the closing one, from (-8,-8) back to the origin -- the
line y = x. So the whole thing is two boxes minus a half-plane:

    Box1  x in [-40, 0]      y in [3.9375, 5.1375]      the flange strip
    Box2  x in [-8.5625, 0]  y in [-8, 3.9375]          the pad carrying the bolt boss
    cut   x > y                                          the diagonal closing edge

The second polygon is the flange strip again -- identical to Box1, and entirely inside the
first polygon whenever `is_cowling` is false. It is not redundant in the source: for a
cowling bulkhead the first polygon is skipped and only this one is built.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import build_sheet, is_entry_point

REF_VOL = 709.2890625

# Derived for U=1.0 end_bolt 3/16in, read from the .scad that render_variant.py emits.
PARAMS = [
    ('unit_width', '100.0'),
    ('corner_radius', '10.0'),
    ('panel_thickness', '4.7625'),
    ('panel_offset', '2.5'),
    ('panel_overlap', '4.7625'),
    ('panel_tolerance', '0.1'),
    ('bulkhead_thickness', '6'),
    ('flange_thickness', '1.2'),
    ('bolt_offset', '8.0'),

    ('flange_y_top', '=corner_radius - panel_thickness - panel_tolerance'),
    ('flange_y_bot', '=flange_y_top - flange_thickness'),
    ('flange_end_x', '=-(unit_width / 2 - corner_radius)'),
    ('x_start', '=-panel_tolerance - panel_offset - panel_overlap - flange_thickness'),
    ('y_start', '=max(x_start, -bolt_offset)'),
    ('far', '=unit_width'),

    # the diagonal half-plane x > y, as a box rotated -45 about z. Placement.Base of a
    # rotated box is the corner AFTER rotation, so it is solved from the sum and
    # difference of the coordinates rather than written down directly.
    ('diag_base', '=-far'),
    ('diag_len', '=far * 2'),
    ('diag_wid', '=far * 2 * sqrt(2)'),
]


def sheet(doc, seed=None):
    """Its own sheet, not corner_tree's -- those aliases carry the hand driver's values and
    would collide here with "Alias already defined"."""
    return build_sheet(doc, PARAMS, seed)


def flange_strip(doc):
    """The flange strip alone -- the second polygon in the docstring above, and ALL of
    `bulkhead_flange_positive` that an `is_cowling` bulkhead builds. IP-FC-132: for a
    cowling bulkhead the pad and the diagonal cut below never run at all."""
    P = 'Params.'
    return C._box(doc, 'FlangeStrip',
                 '-' + P + 'flange_end_x', P + 'flange_thickness', P + 'bulkhead_thickness',
                 P + 'flange_end_x', P + 'flange_y_bot', '0')


def flange_base(doc):
    """Geometry only, against whatever sheet the document already has -- the assembly in
    bulkhead_positive.py supplies one merged sheet for every constituent."""
    P = 'Params.'
    strip = flange_strip(doc)
    pad = C._box(doc, 'FlangePad',
                 '-' + P + 'x_start', P + 'flange_y_bot - ' + P + 'y_start',
                 P + 'bulkhead_thickness',
                 P + 'x_start', P + 'y_start', '0')
    both = C._fuse(doc, 'FlangeBoth', strip, pad)

    diagonal = C._box(doc, 'FlangeDiag', P + 'diag_len', P + 'diag_wid',
                      P + 'bulkhead_thickness * 3',
                      P + 'diag_base', P + 'diag_base',
                      '-' + P + 'bulkhead_thickness', angle=-45)
    cut = C._cut(doc, 'FlangeBase', both, diagonal)

    tip = C._owned(doc, 'Part::Refine', 'FlangeTip')
    tip.Source = cut
    return tip


def flange_base_interconnect(doc):
    """`bulkhead_flange_positive`'s `is_interconnect` branch, IP-FC-132: the flange strip
    fused with a pad running from the flange face straight down to y = 0 -- no diagonal
    cut. An interconnect has none of the bolt-side complexity the end type's pad (which
    starts at `y_start = max(x_start, -bolt_offset)`, clipped by the diagonal) exists for;
    it simply runs the pad to the octant boundary.
    """
    P = 'Params.'
    strip = flange_strip(doc)
    pad = C._box(doc, 'FlangePadIc', '-' + P + 'x_start', P + 'flange_y_bot',
                P + 'bulkhead_thickness', P + 'x_start', '0', '0')
    tip = C._owned(doc, 'Part::Refine', 'FlangeTipIc')
    tip.Source = C._fuse(doc, 'FlangeBothIc', strip, pad)
    return tip


def emit(doc):
    C._SEEN.clear()
    sheet(doc)
    tip = flange_base(doc)
    doc.recompute()
    return tip


# flange_base_interconnect() had no coverage at all before this -- bulkhead_positive.py's
# `is_interconnect` branch calls it instead of flange_base(), and there is no ref_*.scad for
# it, so it is checked against a hand-derived closed form instead of an OpenSCAD reference.
# It is two boxes with no diagonal cut (see its own docstring): the flange strip (unchanged,
# -flange_end_x * flange_thickness * bulkhead_thickness = 40 * 1.2 * 6 = 288) fused with a
# pad running from y=0 to y=flange_y_bot (-x_start * flange_y_bot * bulkhead_thickness =
# 8.5625 * 3.9375 * 6 = 202.2890625), abutting at y = flange_y_bot with zero overlap:
# 288 + 202.2890625 = 490.2890625.
INTERCONNECT_REF_VOL = 490.2890625


def main():
    """Found while auditing IP-TEST-7 (doc/implementation/test_coverage.md): this printed a
    volume delta but never checked it against a tolerance, so the script always exited 0
    regardless of whether the tree actually matched OpenSCAD -- the same gap fixed in
    corner_common.report() for the part_*.py cluster.
    """
    doc = App.newDocument('flange_base')
    tip = emit(doc)
    s = tip.Shape
    d = s.Volume - REF_VOL
    rel = d / REF_VOL
    bb = s.BoundBox
    ok = s.isValid() and len(s.Solids) == 1 and abs(rel) <= 1e-4

    print('PART:: CSG tree -- bulkhead flange base profile')
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD)' % REF_VOL)
    print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * rel))
    print('  bbox    = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
          % (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    print('  expect  = [-40.0000, -8.0000, 0.0000, 0.0000, 5.1375, 6.0000]')
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))
    print('  result  = %s' % ('PASS' if ok else 'FAIL'))

    doc2 = App.newDocument('flange_base_ic')
    C._SEEN.clear()
    sheet(doc2)
    tip_ic = flange_base_interconnect(doc2)
    doc2.recompute()
    s2 = tip_ic.Shape
    d2 = s2.Volume - INTERCONNECT_REF_VOL
    rel2 = d2 / INTERCONNECT_REF_VOL
    ok2 = s2.isValid() and len(s2.Solids) == 1 and abs(rel2) <= 1e-6

    print('PART:: CSG tree -- bulkhead flange base profile (is_interconnect)')
    print('  volume  = %.7f' % s2.Volume)
    print('  ref     = %.7f  (hand-derived closed form)' % INTERCONNECT_REF_VOL)
    print('  delta   = %+.7f  (%+.5f%%)' % (d2, 100 * rel2))
    print('  valid   = %s  solids=%d faces=%d'
          % (s2.isValid(), len(s2.Solids), len(s2.Faces)))
    print('  result  = %s' % ('PASS' if ok2 else 'FAIL'))

    return 0 if (ok and ok2) else 1


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
