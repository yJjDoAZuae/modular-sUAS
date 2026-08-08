"""IP-FC-5: re-open the saved PartDesign body and force a full recompute.

pd_end.py builds the body correctly but reports "The graph must be a DAG" and leaves
Mirrored touched, so measurements taken during construction can be of a stale shape. The
only measurement worth reporting is one taken from a reloaded document after a forced
recompute -- which is also what the sweep would do, since it saves and reloads .FCStd.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import is_entry_point

REF_VOL = 551.8157396
PART_VOL = 551.827595                       # the Part:: port, same parameters

HERE = os.path.dirname(os.path.abspath(__file__))

doc = App.openDocument(os.path.join(HERE, 'pd_end.FCStd'))
body = doc.getObject('Body')

touched = [o.Name for o in doc.Objects if 'Touched' in o.State]
print('  touched on load : %s' % (', '.join(touched) if touched else 'none'))

for obj in doc.Objects:
    obj.touch()
doc.recompute(None, True, True)

still = [o.Name for o in doc.Objects if 'Touched' in o.State or 'Invalid' in o.State]
print('  after recompute : %s' % (', '.join(still) if still else 'all clean'))

s = body.Shape
d = s.Volume - REF_VOL
print('  volume          = %.6f' % s.Volume)
print('  OpenSCAD ref    = %.6f   (%+.6f, %+.4f%%)' % (REF_VOL, d, 100 * d / REF_VOL))
print('  Part:: port     = %.6f   (%+.9f)' % (PART_VOL, s.Volume - PART_VOL))
print('  valid           = %s  solids=%d faces=%d'
      % (s.isValid(), len(s.Solids), len(s.Faces)))

tree = [o.Name for o in body.Group]
print('  feature tree    = %s' % ' -> '.join(tree))
print('  tip             = %s' % body.Tip.Name)
