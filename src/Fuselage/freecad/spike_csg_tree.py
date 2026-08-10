"""IP-FC-5 follow-up: Part:: as a *parametric document tree*, not a static shape.

The first prototype used the Part module's Python API -- Part.makeCylinder and friends --
which returns a TopoShape with no history. That satisfies the sweep and fails UC-2: opened
in FreeCAD it is a dumb solid with nothing to edit.

Part:: document objects are a different thing with the same name. Part::Cylinder has live
Radius and Height properties, Part::Cut has Base and Tool, and together they form a CSG
tree that maps one-to-one onto the OpenSCAD source and stays editable downstream.

This measures whether that tree can be built headless, driven by expressions, changed after
the fact, and reloaded still parametric.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import is_entry_point, out_path

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = out_path('csg_tree.FCStd')


def build():
    doc = App.newDocument('csg_tree')

    # parameters live in a spreadsheet, which is what expressions can bind to and what a
    # human can edit without touching geometry
    sheet = doc.addObject('Spreadsheet::Sheet', 'Params')
    sheet.set('A1', 'U')
    sheet.set('B1', '1.0')
    sheet.setAlias('B1', 'U')
    sheet.set('A2', 'longeron_radius')
    sheet.set('B2', '=U * 2')
    sheet.setAlias('B2', 'longeron_radius')
    doc.recompute()

    outer = doc.addObject('Part::Cylinder', 'Outer')
    outer.Height = 20.0
    outer.setExpression('Radius', 'Params.U * 10')

    bore = doc.addObject('Part::Cylinder', 'Bore')
    bore.Height = 60.0
    bore.Placement = App.Placement(V(0, 0, -20), App.Rotation())
    bore.setExpression('Radius', 'Params.longeron_radius')

    cut = doc.addObject('Part::Cut', 'Cut')
    cut.Base = outer
    cut.Tool = bore
    doc.recompute()
    return doc, sheet, cut


def main():
    import math

    doc, sheet, cut = build()

    def expected(U):
        return math.pi * (10 * U) ** 2 * 20 - math.pi * (2 * U) ** 2 * 20

    print('PART:: as a parametric CSG document tree')
    print('  %-8s %14s %14s %10s' % ('U', 'volume', 'expected', 'delta'))
    for U in (1.0, 0.5, 2.0, 4.0):
        sheet.set('B1', str(U))
        doc.recompute()
        v, e = cut.Shape.Volume, expected(U)
        print('  %-8g %14.5f %14.5f %10.2e' % (U, v, e, abs(v - e)))

    # back to U=1 and persist
    sheet.set('B1', '1.0')
    doc.recompute()
    doc.saveAs(OUT)
    App.closeDocument(doc.Name)

    # reload: is it still a live tree, or did it save as a baked shape?
    doc = App.openDocument(OUT)
    sheet, cut = doc.getObject('Params'), doc.getObject('Cut')
    print('')
    print('  reloaded: %s' % ', '.join('%s(%s)' % (o.Name, o.TypeId.split('::')[-1])
                                       for o in doc.Objects))
    print('  Outer.Radius expression = %s'
          % doc.getObject('Outer').ExpressionEngine)
    sheet.set('B1', '3.0')
    doc.recompute()
    v, e = cut.Shape.Volume, math.pi * 900 * 20 - math.pi * 36 * 20
    print('  edit after reload: U=3 -> %.5f (expected %.5f, delta %.2e)'
          % (v, e, abs(v - e)))

    # and what a downstream editor most wants: change one primitive, keep the rest
    doc.getObject('Bore').setExpression('Radius', None)
    doc.getObject('Bore').Radius = 5.0
    doc.recompute()
    print('  overrode Bore.Radius=5 by hand -> %.5f' % cut.Shape.Volume)
    print('  tree still live: Cut.Base=%s Cut.Tool=%s'
          % (cut.Base.Name, cut.Tool.Name))


if is_entry_point(__name__):
    main()
