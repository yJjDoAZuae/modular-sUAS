"""IP-FC-38: the derived-part workflow -- own the parameters, keep your own geometry.

The wanted workflow is a modified part that takes the generated part as its starting point,
where the user can BOTH re-parameterise the original (a tolerance, a bolt diameter) AND add
or subtract their own geometry (a mounting bracket, a clearance notch).

A link does not deliver the first half. App::Link and SubShapeBinder reference the source's
*shape*; there is no route from the referencing document back into the source's parameter
table, and editing the source in place is exactly what the sweep overwrites.

What does deliver both is treating the generator as a library rather than a file: the user's
document owns a parameter sheet and the generated CSG nodes, and the user's own features
hang off a stable tip. Re-running the generator updates its own nodes in place and leaves
everything else alone.

Two properties make that safe, and both are measured here:

  * generated objects are TAGGED, so a regenerate can tell its own nodes from the user's;
  * the tree ends in a STABLE TIP whose identity never changes, so user features keep a
    valid reference even when the generated internals restructure.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import is_entry_point, out_path

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
GENERATOR = 'corner_demo'
DEFAULTS = [('U', '1.0'), ('longeron_tolerance', '0.05'), ('bolt_diameter', '4.0')]


def _owned(doc, typename, name):
    """Fetch the generator's own object by name, creating and tagging it if absent.

    The tag is what makes a regenerate safe: anything without it belongs to the user and
    is never touched.
    """
    obj = doc.getObject(name)
    if obj is None:
        obj = doc.addObject(typename, name)
        obj.addProperty('App::PropertyString', 'Generator',
                        'Provenance', 'Which generator owns this object')
        obj.Generator = GENERATOR
    return obj


def emit(doc):
    """Create or update the generated part in `doc`. Returns the stable tip object.

    Safe to call repeatedly. Parameter *values* are only written when the sheet is first
    created -- a regenerate must not silently undo the user's re-parameterisation.
    """
    fresh = doc.getObject('Params') is None
    sheet = doc.getObject('Params') or doc.addObject('Spreadsheet::Sheet', 'Params')
    if fresh:
        for row, (alias, value) in enumerate(DEFAULTS, start=1):
            sheet.set('A%d' % row, alias)
            sheet.set('B%d' % row, value)
            sheet.setAlias('B%d' % row, alias)
        doc.recompute()

    outer = _owned(doc, 'Part::Cylinder', 'Outer')
    outer.Height = 20.0
    outer.setExpression('Radius', 'Params.U * 10')

    bore = _owned(doc, 'Part::Cylinder', 'Bore')
    bore.Height = 60.0
    bore.Placement = App.Placement(V(0, 0, -20), App.Rotation())
    bore.setExpression('Radius', 'Params.U * 2 + Params.longeron_tolerance')

    bolt = _owned(doc, 'Part::Cylinder', 'BoltHole')
    bolt.Height = 60.0
    bolt.Placement = App.Placement(V(7, 0, -20), App.Rotation())
    bolt.setExpression('Radius', 'Params.bolt_diameter / 2')

    cut1 = _owned(doc, 'Part::Cut', 'CutBore')
    cut1.Base, cut1.Tool = outer, bore
    cut2 = _owned(doc, 'Part::Cut', 'CutBolt')
    cut2.Base, cut2.Tool = cut1, bolt

    # The stable tip. User features bind to this name and only this name, so the
    # generated internals can restructure without invalidating anything downstream.
    tip = _owned(doc, 'Part::Refine', 'Tip')
    tip.Source = cut2

    doc.recompute()
    return tip


def user_features(doc, tip):
    """What the user adds: a mounting bracket fused on, a clearance notch cut out."""
    bracket = doc.addObject('Part::Box', 'UserBracket')
    bracket.Length, bracket.Width, bracket.Height = 6.0, 12.0, 4.0
    bracket.setExpression('Placement.Base.x', 'Params.U * 10 - 1')
    bracket.Placement = App.Placement(V(9, -6, 8), App.Rotation())

    fuse = doc.addObject('Part::Fuse', 'UserFuse')
    fuse.Base, fuse.Tool = tip, bracket

    notch = doc.addObject('Part::Box', 'UserNotch')
    notch.Length, notch.Width, notch.Height = 20.0, 3.0, 6.0
    notch.setExpression('Placement.Base.y', '-1.5')
    notch.Placement = App.Placement(V(-20, -1.5, -1), App.Rotation())

    cut = doc.addObject('Part::Cut', 'UserCut')
    cut.Base, cut.Tool = fuse, notch
    doc.recompute()
    return cut


def show(doc, label, tip, final):
    gen = [o.Name for o in doc.Objects
           if getattr(o, 'Generator', None) == GENERATOR]
    usr = [o.Name for o in doc.Objects
           if o.Name.startswith('User')]
    print('  %-22s tip=%10.4f  final=%10.4f  valid=%s'
          % (label, tip.Shape.Volume, final.Shape.Volume, final.Shape.isValid()))
    return gen, usr


def main():
    doc = App.newDocument('derived')
    tip = emit(doc)
    final = user_features(doc, tip)

    print('Derived part: user document owns parameters + generated nodes + own geometry')
    gen, usr = show(doc, 'as generated', tip, final)
    print('  generated nodes: %s' % ', '.join(gen))
    print('  user nodes     : %s' % ', '.join(usr))

    sheet = doc.getObject('Params')

    print('')
    print('1. Re-parameterise the original from the user document')
    sheet.set('B2', '0.25')                    # longeron_tolerance 0.05 -> 0.25
    doc.recompute()
    show(doc, 'tolerance 0.05->0.25', tip, final)
    sheet.set('B3', '6.0')                     # bolt_diameter 4 -> 6
    doc.recompute()
    show(doc, 'bolt dia 4->6', tip, final)
    sheet.set('B1', '1.5')                     # U 1 -> 1.5
    doc.recompute()
    show(doc, 'U 1->1.5', tip, final)

    print('')
    print('2. Regenerate: does the generator disturb the user nodes or the overrides?')
    before = (final.Shape.Volume, sheet.get('longeron_tolerance'),
              sheet.get('bolt_diameter'), sheet.get('U'))
    emit(doc)
    doc.recompute()
    after = (final.Shape.Volume, sheet.get('longeron_tolerance'),
             sheet.get('bolt_diameter'), sheet.get('U'))
    print('   volume  %.4f -> %.4f' % (before[0], after[0]))
    print('   params  tol=%s dia=%s U=%s  ->  tol=%s dia=%s U=%s'
          % (before[1], before[2], before[3], after[1], after[2], after[3]))
    print('   user nodes still present: %s'
          % ', '.join(o.Name for o in doc.Objects if o.Name.startswith('User')))
    print('   UserFuse.Base is still %s' % doc.getObject('UserFuse').Base.Name)
    print('   duplicate generated nodes: %d'
          % (len([o for o in doc.Objects
                  if getattr(o, 'Generator', None) == GENERATOR]) - len(gen)))

    print('')
    print('3. Save, reload, edit again')
    out = out_path('derived.FCStd')
    doc.saveAs(out)
    App.closeDocument(doc.Name)
    doc = App.openDocument(out)
    sheet, tip = doc.getObject('Params'), doc.getObject('Tip')
    final = doc.getObject('UserCut')
    sheet.set('B1', '2.0')
    doc.recompute()
    show(doc, 'reloaded, U->2', tip, final)
    print('   expressions survived: Bore=%s' % doc.getObject('Bore').ExpressionEngine)
    print('   user chain intact  : UserCut.Base=%s Tool=%s'
          % (final.Base.Name, final.Tool.Name))
    os.remove(out)


if is_entry_point(__name__):
    main()
