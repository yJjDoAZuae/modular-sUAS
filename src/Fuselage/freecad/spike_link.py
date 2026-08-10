"""IP-FC-38: what an App::Link to the generated file does and does not give you.

The link is the obvious reading of "use the generated part as a reference". It works for
geometry reuse. It does not give the referencing document any control over the source's
parameters, which is the other half of what the workflow needs -- measured here rather than
assumed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import is_entry_point, out_path

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
GEN = out_path('linked_generated.FCStd')
USR = out_path('linked_user.FCStd')


def main():
    # the generated part, as the sweep would emit it
    gen = App.newDocument('linked_generated')
    sheet = gen.addObject('Spreadsheet::Sheet', 'Params')
    sheet.set('B1', '1.0')
    sheet.setAlias('B1', 'U')
    gen.recompute()
    outer = gen.addObject('Part::Cylinder', 'Outer')
    outer.Height = 20.0
    outer.setExpression('Radius', 'Params.U * 10')
    gen.recompute()
    gen.saveAs(GEN)

    # the user's document, referencing it. An external link requires the *linking*
    # document to exist on disk first -- FreeCAD raises "Owner document not saved"
    # otherwise, so a derived part can never be a scratch document.
    usr = App.newDocument('linked_user')
    usr.saveAs(USR)
    link = usr.addObject('App::Link', 'GeneratedCorner')
    link.LinkedObject = outer
    usr.recompute()

    print('App::Link to a generated part')
    print('  link shape volume       = %.4f' % link.Shape.Volume)
    print('  link is external        = %s'
          % (link.LinkedObject.Document.Name != usr.Name))

    # 1. does the link follow when the source changes?
    sheet.set('B1', '2.0')
    gen.recompute()
    usr.recompute()
    print('  source U 1->2, link now = %.4f  (follows: %s)'
          % (link.Shape.Volume, abs(link.Shape.Volume - 25132.7412) < 1e-3))

    # 2. can the user's document drive the source's parameters?
    usr_sheet = usr.addObject('Spreadsheet::Sheet', 'MyParams')
    usr_sheet.set('B1', '3.0')
    usr_sheet.setAlias('B1', 'U')
    usr.recompute()
    try:
        # the only way to make the source follow the user's sheet is to rewrite the
        # SOURCE's expression to point at the user document -- i.e. modify the generated
        # file, which is the thing the sweep overwrites
        outer.setExpression('Radius', '<<linked_user>>#MyParams.U * 10')
        gen.recompute()
        usr.recompute()
        print('  after re-pointing the SOURCE at the user sheet: %.4f'
              % link.Shape.Volume)
        print('  -> possible, but it edited %s, not the user file'
              % os.path.basename(GEN))
    except Exception as exc:
        print('  driving source params from user doc REFUSED: %s' % exc)

    # 3. can the user add geometry to the link locally?
    box = usr.addObject('Part::Box', 'UserBracket')
    box.Length, box.Width, box.Height = 6.0, 12.0, 4.0
    box.Placement = App.Placement(V(18, -6, 8), App.Rotation())
    fuse = usr.addObject('Part::Fuse', 'UserFuse')
    fuse.Base, fuse.Tool = link, box
    usr.recompute()
    ok = fuse.Shape is not None and not fuse.Shape.isNull()
    print('  fuse user geometry onto the link: %s%s'
          % (ok, '  volume=%.4f' % fuse.Shape.Volume if ok else ''))

    for d in (usr.Name, gen.Name):
        App.closeDocument(d)
    for f in (GEN, USR):
        if os.path.exists(f):
            os.remove(f)


if is_entry_point(__name__):
    main()
