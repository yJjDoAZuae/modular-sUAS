"""IP-FC-9: bulkhead_web as a Part:: CSG tree.

`bulkhead_web_shape`'s 10-vertex polygon looks like it needs a sketch and does not. Its
vertices are

    (0,0) (0,5.1375) (-40,5.1375) (-40,0.9375) (-16,0.9375) (-18,0.9375)
    (-18,-1.0625) (-16,-1.0625) (-16,-8) (-8,-8)

and every edge is axis-aligned except the closing one, from (-8,-8) to the origin along
y = x. Note (-40,0.9375) -> (-16,0.9375) -> (-18,0.9375) are collinear and the middle one
doubles back, so that pair is a zero-area spur: the boundary is really -40 to -18. So the
profile is three stacked boxes minus the half-plane x > y:

    Box1  x in [-40, 0]   y in [ 0.9375,  5.1375]
    Box2  x in [-18, 0]   y in [-1.0625,  0.9375]
    Box3  x in [-16, 0]   y in [-8,      -1.0625]

**The web's fillet is already a true fillet.** The module subtracts a cylinder of
web_fillet_radius at the re-entrant corner, which is why the profile carries that little
step out to x = -18: the step is the material the cylinder then rounds. This is not the
morphological `fillet_inner` that OQ-DES-B9 concerns -- that one is in
`bulkhead_web_inner_shape_octant`, which the non-interconnect path never calls.

Derived parameters for U=1.0 end_bolt 3/16in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import is_entry_point

REF_VOL = 223.8866978

PARAMS = [
    ('unit_width', '100.0'),
    ('corner_radius', '10.0'),
    ('panel_thickness', '4.7625'),
    ('panel_tolerance', '0.1'),
    ('bulkhead_thickness', '6'),
    ('flange_thickness', '1.2'),
    ('bolt_hole_radius', '2.0'),
    ('bolt_thickness', '3.0'),
    ('bolt_offset', '8.0'),
    ('plate_thickness', '0.8'),
    ('web_fillet_radius', '2.0'),
    ('web_width', '3.0'),

    ('web_y_top', '=corner_radius - panel_thickness - panel_tolerance'),
    ('web_y_mid', '=web_y_top - flange_thickness - web_width'),
    ('web_x_left', '=-(unit_width / 2 - corner_radius)'),
    # the bolt boss outer edge, and the step the fillet cylinder rounds
    ('boss_x', '=-bolt_offset - (bolt_hole_radius + bolt_thickness + web_width)'),
    ('step_x', '=boss_x - web_fillet_radius'),
    ('step_y', '=web_y_mid - web_fillet_radius'),
    ('far', '=unit_width'),

    ('diag_base', '=-far'),
    ('diag_len', '=far * 2'),
    ('diag_wid', '=far * 2 * sqrt(2)'),
]


def sheet(doc):
    fresh = doc.getObject('Params') is None
    sh = doc.getObject('Params') or doc.addObject('Spreadsheet::Sheet', 'Params')
    if fresh:
        for row, (alias, value) in enumerate(PARAMS, start=1):
            sh.set('A%d' % row, alias)
            sh.setAlias('B%d' % row, alias)
            sh.set('B%d' % row, value)
        doc.recompute()
    return sh


def emit(doc):
    P = 'Params.'
    C._SEEN.clear()
    sheet(doc)
    t = P + 'plate_thickness'

    top = C._box(doc, 'WebTop', '-' + P + 'web_x_left',
                 P + 'web_y_top - ' + P + 'web_y_mid', t,
                 P + 'web_x_left', P + 'web_y_mid', '0')
    mid = C._box(doc, 'WebMid', '-' + P + 'step_x',
                 P + 'web_y_mid - ' + P + 'step_y', t,
                 P + 'step_x', P + 'step_y', '0')
    low = C._box(doc, 'WebLow', '-' + P + 'boss_x',
                 P + 'step_y + ' + P + 'bolt_offset', t,
                 P + 'boss_x', '-' + P + 'bolt_offset', '0')

    node = C._fuse(doc, 'WebA', top, mid)
    node = C._fuse(doc, 'WebB', node, low)

    node = C._cut(doc, 'WebDiag', node,
                  C._box(doc, 'WebDiagBox', P + 'diag_len', P + 'diag_wid',
                         t + ' * 3', P + 'diag_base', P + 'diag_base',
                         '-' + t, angle=-45))

    # the fillet: a cylinder subtracted at the re-entrant corner
    fillet = C._cyl(doc, 'WebFillet', P + 'web_fillet_radius', t + ' * 3', '-' + t)
    fillet.setExpression('Placement.Base.x', P + 'step_x')
    fillet.setExpression('Placement.Base.y', P + 'step_y')
    node = C._cut(doc, 'Web', node, fillet)

    tip = C._owned(doc, 'Part::Refine', 'WebTip')
    tip.Source = node
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('web')
    tip = emit(doc)
    s = tip.Shape
    d = s.Volume - REF_VOL
    bb = s.BoundBox

    print('PART:: CSG tree -- bulkhead_web')
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, faceted)' % REF_VOL)
    print('  delta   = %+.7f  (%+.4f%%)' % (d, 100 * d / REF_VOL))
    print('  bbox    = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
          % (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    print('  expect  = [-40.0000, -8.0000, 0.0000, 0.0000, 5.1375, 0.8000]')
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))


if is_entry_point(__name__):
    main()
