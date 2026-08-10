"""IP-FC-38: the CSG tree must pass everything the static port passed, and then some.

The static Part:: port was verified by volume against OpenSCAD and by a regenerate across
four sizes. A tree has to clear the same bar, but a regenerate now means something stronger:
editing a spreadsheet cell and recomputing, rather than re-running a script. It must also
still be a live tree after a save and reload, because that is the file the user opens.

References are regen_U*.stl, rendered from ref_regenerate.scad at the same parameters -- see
the README. They are build artifacts and are not kept in the tree.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import is_entry_point, out_path
from corner_tree import emit
from measure import measure
from variants import TABLE, panel_overlap

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = out_path('corner_tree.FCStd')


def set_params(sheet, U, bt, pt):
    sheet.set('U', str(U))
    sheet.set('bulkhead_thickness', str(bt))
    sheet.set('panel_thickness', str(pt))
    sheet.set('panel_overlap', str(panel_overlap(pt)))


def main():
    doc = App.newDocument('corner_tree')
    tip = emit(doc)
    sheet = doc.getObject('Params')

    print('CSG tree regenerate -- by editing the parameter sheet, not re-running')
    print('%5s %6s %6s %14s %14s %12s %9s %6s %s'
          % ('U', 'bt', 'pt', 'OpenSCAD', 'FreeCAD', 'delta', 'rel', 'faces', 'checks'))

    failures = []
    for U, bt, pt in TABLE:
        stl = out_path('regen_U%g.stl' % U)
        if not os.path.exists(stl):
            print('%5g  -- reference %s not rendered, skipped' % (U, os.path.basename(stl)))
            continue

        set_params(sheet, U, bt, pt)
        doc.recompute()

        _, ref, _, _ = measure(stl)
        s = tip.Shape
        d = s.Volume - ref

        checks = []
        if not s.isValid():
            checks.append('INVALID')
        if len(s.Solids) != 1:
            checks.append('solids=%d' % len(s.Solids))
        if abs(d) / ref > 1e-4:
            checks.append('VOLUME')
        stale = [o.Name for o in doc.Objects
                 if getattr(o, 'Generator', None) and
                 ('Touched' in o.State or 'Invalid' in o.State)]
        if stale:
            checks.append('stale=%s' % ','.join(stale[:3]))
        # a sketch that has come loose deforms silently -- assert it every time
        loose = [o.Name for o in doc.Objects
                 if o.isDerivedFrom('Sketcher::SketchObject') and not o.FullyConstrained]
        if loose:
            checks.append('UNCONSTRAINED=%s' % ','.join(loose))
        if checks:
            failures.append((U, checks))

        print('%5g %6g %6g %14.5f %14.5f %+12.5f %+8.4f%% %6d %s'
              % (U, bt, pt, ref, s.Volume, d, 100 * d / ref, len(s.Faces),
                 ' '.join(checks) if checks else 'ok'))

    print('')
    print('regenerate: %d failures' % len(failures))

    # back to the reference size, save, and check the file the user would open
    set_params(sheet, 1.0, 6.0, 4.77)
    sheet.set('panel_overlap', '4.0')
    doc.recompute()
    doc.saveAs(OUT)
    App.closeDocument(doc.Name)

    print('')
    print('Reloaded document')
    doc = App.openDocument(OUT)
    tip, sheet = doc.getObject('Tip'), doc.getObject('Params')
    print('  volume on load     = %.6f' % tip.Shape.Volume)
    print('  sketches still constrained = %s'
          % all(o.FullyConstrained for o in doc.Objects
                if o.isDerivedFrom('Sketcher::SketchObject')))
    print('  Outer.Radius       = %s'
          % [e for e in doc.getObject('MidOuter').ExpressionEngine if e[0] == 'Radius'])

    # the derived-part workflow: change a tolerance, then hang geometry off the tip
    before = tip.Shape.Volume
    sheet.set('greeble_tolerance', '0.25')
    doc.recompute()
    print('  greeble_tolerance 0.05 -> 0.25: %.6f -> %.6f (%+.4f)'
          % (before, tip.Shape.Volume, tip.Shape.Volume - before))

    box = doc.addObject('Part::Box', 'UserBracket')
    box.Length, box.Width, box.Height = 6.0, 12.0, 4.0
    box.setExpression('Placement.Base.x', 'Params.corner_radius - 1')
    box.setExpression('Placement.Base.z', 'Params.unit_length / 2')
    fuse = doc.addObject('Part::Fuse', 'UserFuse')
    fuse.Base, fuse.Tool = tip, box
    doc.recompute()
    added = fuse.Shape.Volume - tip.Shape.Volume
    sheet.set('U', '2.0')
    doc.recompute()
    added2 = fuse.Shape.Volume - tip.Shape.Volume
    print('  user bracket adds %.4f at U=1, %.4f at U=2 (bound, so it follows)'
          % (added, added2))
    print('  UserFuse.Base = %s' % fuse.Base.Name)

    os.remove(OUT)


if is_entry_point(__name__):
    main()
