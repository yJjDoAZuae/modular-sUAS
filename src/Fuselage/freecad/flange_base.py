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


def flange_base(doc):
    """Geometry only, against whatever sheet the document already has -- the assembly in
    bulkhead_positive.py supplies one merged sheet for every constituent."""
    P = 'Params.'
    strip = C._box(doc, 'FlangeStrip',
                   '-' + P + 'flange_end_x', P + 'flange_thickness', P + 'bulkhead_thickness',
                   P + 'flange_end_x', P + 'flange_y_bot', '0')
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


def emit(doc):
    C._SEEN.clear()
    sheet(doc)
    tip = flange_base(doc)
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('flange_base')
    tip = emit(doc)
    s = tip.Shape
    d = s.Volume - REF_VOL
    bb = s.BoundBox

    print('PART:: CSG tree -- bulkhead flange base profile')
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD)' % REF_VOL)
    print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * d / REF_VOL))
    print('  bbox    = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
          % (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    print('  expect  = [-40.0000, -8.0000, 0.0000, 0.0000, 5.1375, 6.0000]')
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))


if is_entry_point(__name__):
    main()
