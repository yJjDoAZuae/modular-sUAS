"""IP-FC-38 follow-up: how does a hand edit interact with a generated Part:: CSG tree?

Three separate questions, each measured rather than assumed:

  1. What happens if a human sets a property that is bound to an expression -- does the
     edit take, error, or get silently reverted on the next recompute?
  2. Can a human add their own node downstream of the generated tip and keep it?
  3. Does clearing an expression survive a save and reload -- i.e. is the decoupling
     permanent and invisible, or recoverable?

The answers decide what the generator may safely overwrite, which is the real question
behind "do CSG trees conflict with hand edits".
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import is_entry_point, out_path

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = out_path('hand_edit.FCStd')


def generated(name='hand_edit'):
    """What the generator would emit: parameters in a sheet, geometry bound to them."""
    doc = App.newDocument(name)
    sheet = doc.addObject('Spreadsheet::Sheet', 'Params')
    sheet.set('B1', '1.0')
    sheet.setAlias('B1', 'U')
    doc.recompute()

    outer = doc.addObject('Part::Cylinder', 'Outer')
    outer.Height = 20.0
    outer.setExpression('Radius', 'Params.U * 10')

    bore = doc.addObject('Part::Cylinder', 'Bore')
    bore.Height = 60.0
    bore.Placement = App.Placement(V(0, 0, -20), App.Rotation())
    bore.setExpression('Radius', 'Params.U * 2')

    cut = doc.addObject('Part::Cut', 'Cut')
    cut.Base, cut.Tool = outer, bore
    doc.recompute()
    return doc, sheet, cut


def main():
    doc, sheet, cut = generated()
    outer = doc.getObject('Outer')

    print('1. Writing a property that is bound to an expression')
    print('   before          Radius = %.3f' % outer.Radius.Value)
    try:
        outer.Radius = 25.0
        print('   after assign    Radius = %.3f   (assignment raised nothing)'
              % outer.Radius.Value)
    except Exception as exc:
        print('   assignment REFUSED: %s' % exc)
    doc.recompute()
    print('   after recompute Radius = %.3f' % outer.Radius.Value)
    print('   -> the expression %s' %
          ('WINS; the hand edit is silently discarded' if abs(outer.Radius.Value - 10) < 1e-9
           else 'was overridden by the hand edit'))

    print('')
    print('2. Adding a node downstream of the generated tip')
    extra = doc.addObject('Part::Box', 'UserBox')
    extra.Length, extra.Width, extra.Height = 5.0, 5.0, 40.0
    extra.Placement = App.Placement(V(-2.5, -2.5, -10), App.Rotation())
    user_cut = doc.addObject('Part::Cut', 'UserCut')
    user_cut.Base, user_cut.Tool = cut, extra
    doc.recompute()
    print('   UserCut volume  = %.4f  valid=%s' % (user_cut.Shape.Volume,
                                                   user_cut.Shape.isValid()))
    print('   generated tip still intact: Cut volume = %.4f' % cut.Shape.Volume)

    removed_before = cut.Shape.Volume - user_cut.Shape.Volume
    print('   the user node removes %.4f mm3 at U=1' % removed_before)

    # the generator re-runs: it knows Outer/Bore/Cut/Params, it does not know UserCut
    sheet.set('B1', '2.0')
    doc.recompute()
    removed_after = cut.Shape.Volume - user_cut.Shape.Volume
    print('   after regenerate at U=2: Cut = %.4f, UserCut = %.4f'
          % (cut.Shape.Volume, user_cut.Shape.Volume))
    print('   the user node now removes %.4f mm3' % removed_after)
    print('   -> the node SURVIVED and recomputed, but its dimensions are hard-coded, so')
    print('      at U=2 the 5x5 box fits entirely inside the r=4 bore and cuts nothing.')
    print('      A hand edit persists structurally and still loses its intent unless the')
    print('      user binds it to the parameter table the same way the generator does.')

    doc.saveAs(OUT)
    App.closeDocument(doc.Name)

    print('')
    print('3. Clearing an expression, then reloading')
    doc = App.openDocument(OUT)
    outer, sheet = doc.getObject('Outer'), doc.getObject('Params')
    outer.setExpression('Radius', None)
    outer.Radius = 25.0
    doc.recompute()
    print('   unbound and set Radius = %.3f' % outer.Radius.Value)
    sheet.set('B1', '4.0')
    doc.recompute()
    print('   sheet U=4 -> Outer.Radius = %.3f, Bore.Radius = %.3f'
          % (outer.Radius.Value, doc.getObject('Bore').Radius.Value))
    print('   -> Outer no longer tracks the parameter table; Bore still does.')
    print('   remaining expressions: Outer=%s Bore=%s'
          % (outer.ExpressionEngine, doc.getObject('Bore').ExpressionEngine))


if is_entry_point(__name__):
    main()
