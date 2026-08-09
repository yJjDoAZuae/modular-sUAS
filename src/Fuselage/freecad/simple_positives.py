"""IP-FC-9: the six plain positives of bulkhead_section, as a Part:: CSG tree.

The bolt boss with its web and chamfer, the plate, and the longeron flange with its chamfer.
Every one is a cylinder, a cone or a box, so the whole group is primitives with no sketches
and no booleans beyond the union.

Derived parameters for U=1.0 end_bolt 3/16in -- not the hand driver's constants. See
IP-FC-41.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import is_entry_point

REF_VOL = 1090.6367096

PARAMS = [
    ('bulkhead_thickness', '6'),
    ('corner_radius', '10.0'),
    ('bolt_hole_radius', '2.0'),
    ('bolt_thickness', '3.0'),
    ('bolt_offset', '8.0'),
    ('plate_thickness', '0.8'),
    ('web_width', '3.0'),
    ('flange_chamfer', '1.0'),
    ('panel_overlap', '4.7625'),
    ('longeron_radius', '2.0'),

    ('bolt_boss_r', '=bolt_hole_radius + bolt_thickness'),
    ('bolt_boss_web_r', '=bolt_boss_r + web_width'),
    ('bolt_boss_chamfer_r', '=bolt_boss_r + flange_chamfer'),
    ('long_r', '=longeron_radius + bolt_thickness'),
    ('long_chamfer_r', '=long_r + flange_chamfer'),
    ('bolt_x', '=-bolt_offset'),
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


def _at(obj, x_expr, y_expr):
    """Place a solid of revolution at the bolt centre."""
    obj.setExpression('Placement.Base.x', x_expr)
    obj.setExpression('Placement.Base.y', y_expr)
    return obj


def emit(doc):
    P = 'Params.'
    C._SEEN.clear()
    sheet(doc)
    bx, by = P + 'bolt_x', P + 'bolt_x'

    boss = _at(C._cyl(doc, 'BoltBoss', P + 'bolt_boss_r', P + 'bulkhead_thickness', '0'),
               bx, by)
    fillet = _at(C._cone(doc, 'BoltChamfer', P + 'bolt_boss_chamfer_r', P + 'bolt_boss_r',
                         P + 'flange_chamfer', P + 'plate_thickness'), bx, by)
    web = _at(C._cyl(doc, 'BoltWeb', P + 'bolt_boss_web_r', P + 'plate_thickness', '0'),
              bx, by)

    node = C._fuse(doc, 'BoltA', boss, fillet)
    node = C._fuse(doc, 'BoltB', node, web)

    plate = C._box(doc, 'Plate', P + 'panel_overlap', P + 'corner_radius',
                   P + 'plate_thickness', '-' + P + 'panel_overlap', '0', '0')
    node = C._fuse(doc, 'PlateFuse', node, plate)

    long_flange = C._cyl(doc, 'LongeronFlange', P + 'long_r', P + 'bulkhead_thickness', '0')
    node = C._fuse(doc, 'LongeronA', node, long_flange)

    long_chamfer = C._cone(doc, 'LongeronChamfer', P + 'long_chamfer_r', P + 'long_r',
                           P + 'flange_chamfer', P + 'plate_thickness')
    node = C._fuse(doc, 'SimplePositives', node, long_chamfer)

    tip = C._owned(doc, 'Part::Refine', 'PositivesTip')
    tip.Source = node
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('simple_positives')
    tip = emit(doc)
    s = tip.Shape
    d = s.Volume - REF_VOL
    bb = s.BoundBox

    print('PART:: CSG tree -- bulkhead simple positives')
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, faceted)' % REF_VOL)
    print('  delta   = %+.7f  (%+.4f%%)' % (d, 100 * d / REF_VOL))
    print('  bbox    = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
          % (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    print('  expect  = [-16.0000, -16.0000, 0.0000, 6.0000, 10.0000, 6.0000]')
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))


if is_entry_point(__name__):
    main()
