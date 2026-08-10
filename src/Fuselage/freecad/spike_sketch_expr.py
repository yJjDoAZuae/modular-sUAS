"""IP-FC-38: can a sketch's geometry be driven by the parameter sheet, headless?

corner_middle decomposed entirely into half-planes, so it needed no sketches. corner_end
does not: its wedge is a non-convex hexagon whose vertices are not collinear and whose edges
are not at nice angles. Either it becomes a pile of boolean primitives, or it becomes a
sketch -- and a sketch is only acceptable if its geometry tracks the parameters rather than
being baked at generation time.

A sketch's raw geometry coordinates are not expression-bindable. Its *constraints* are. So
the question is whether a fully constrained polygon with expression-driven constraints
recomputes correctly with no GUI, and survives a reload.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part
import Sketcher

from corner_common import is_entry_point, out_path

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = out_path('sketch_expr.FCStd')


def main():
    doc = App.newDocument('sketch_expr')
    sheet = doc.addObject('Spreadsheet::Sheet', 'Params')
    # NB: aliases may not collide with unit symbols -- 'w' (watt) and 'h' (hour) are both
    # rejected as "Invalid alias" by the expression parser.
    for row, (alias, value) in enumerate(
            [('width', '10.0'), ('height', '4.0'), ('notch_x', '6.0'), ('notch_y', '2.0')], start=1):
        sheet.set('A%d' % row, alias)
        sheet.setAlias('B%d' % row, alias)
        sheet.set('B%d' % row, value)
    doc.recompute()

    sk = doc.addObject('Sketcher::SketchObject', 'Profile')

    # a non-convex polygon, same character as the wedge: a rectangle with a bite taken out
    pts = [(0, 0), (10, 0), (10, 4), (6, 4), (6, 2), (0, 2)]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)

    # A sketch must be FULLY CONSTRAINED before its dimensions are driven. Six lines are
    # 24 degrees of freedom; closing the chain removes 12 and leaves the shape free to
    # deform into anything that still satisfies whatever dimensions were added. The solver
    # does that silently and the extrusion is still a valid solid.
    for i in range(len(pts)):
        sk.addConstraint(Sketcher.Constraint('Coincident', i, 2,
                                             (i + 1) % len(pts), 1))
    for i in (0, 2, 4):
        sk.addConstraint(Sketcher.Constraint('Horizontal', i))
    for i in (1, 3, 5):
        sk.addConstraint(Sketcher.Constraint('Vertical', i))
    sk.addConstraint(Sketcher.Constraint('Coincident', 0, 1, -1, 1))   # pin to origin
    doc.recompute()

    # the four dimensions that remain, all driven from the sheet
    for expr, con in (
            ('Params.width', Sketcher.Constraint('DistanceX', 0, 1, 0, 2, 10.0)),
            ('Params.height', Sketcher.Constraint('DistanceY', 1, 1, 1, 2, 4.0)),
            ('Params.notch_x', Sketcher.Constraint('DistanceX', 0, 1, 3, 1, 6.0)),
            ('Params.notch_y', Sketcher.Constraint('DistanceY', 0, 1, 4, 1, 2.0))):
        sk.setExpression('Constraints[%d]' % sk.addConstraint(con), expr)
    doc.recompute()

    pad = doc.addObject('Part::Extrusion', 'Prism')
    pad.Base = sk
    pad.DirMode = 'Normal'
    pad.LengthFwd = 5.0
    pad.Solid = True
    doc.recompute()

    def area():
        return pad.Shape.Volume / 5.0

    print('Sketch geometry driven by a spreadsheet')
    print('  constraints=%d  fully constrained=%s  solve=%d'
          % (sk.ConstraintCount, sk.FullyConstrained, sk.solve()))
    print('  width=10 height=4 notch=(6,2) -> area %.4f  (expect 28)' % area())

    sheet.set('B1', '20.0')
    doc.recompute()
    print('  width=20                       -> area %.4f  (expect 68)' % area())

    sheet.set('B4', '1.0')
    doc.recompute()
    print('  notch_y=1                      -> area %.4f  (expect 62)' % area())

    doc.saveAs(OUT)
    App.closeDocument(doc.Name)
    doc = App.openDocument(OUT)
    sheet, pad, sk = (doc.getObject('Params'), doc.getObject('Prism'),
                      doc.getObject('Profile'))
    print('  reloaded        -> area %.4f' % (pad.Shape.Volume / 5.0))
    print('  expressions     = %s' % sk.ExpressionEngine)
    sheet.set('B2', '8.0')
    doc.recompute()
    print('  height=8 after reload          -> area %.4f  (expect 118)'
          % (pad.Shape.Volume / 5.0))
    os.remove(OUT)


if is_entry_point(__name__):
    main()
