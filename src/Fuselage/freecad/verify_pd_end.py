"""IP-FC-5: re-open the saved PartDesign body and force a full recompute.

pd_end.py builds the body correctly but reports "The graph must be a DAG" and leaves
Mirrored touched, so measurements taken during construction can be of a stale shape. The
only measurement worth reporting is one taken from a reloaded document after a forced
recompute -- which is also what the sweep would do, since it saves and reloads .FCStd.

Requires pd_end.py to have been run first (it saves out_path('pd_end.FCStd')).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import si
from corner_common import is_entry_point, out_path

REF_VOL_M3 = 5.518157396e-7                 # 551.8157396 mm3, OpenSCAD
PART_VOL_M3 = 5.51827595e-7                 # 551.827595 mm3, the Part:: port
#: 0.1% of the reference, so already SI -- named for its unit because it is a volume, not the
#: dimensionless 1e-3 it is derived from.
TOL_M3 = 1e-3 * REF_VOL_M3

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    """Found while auditing IP-TEST-11 (doc/implementation/test_coverage.md): this whole
    script was bare top-level code with no main(), no is_entry_point guard, and no verdict
    at all -- it always exited 0 regardless of whether the reload-and-recompute actually left
    the body clean and valid, the exact "always exits 0" bug class check_end_bands.py and
    check_regenerate.py had before their own IP-TEST-10 fixes.
    """
    doc = App.openDocument(out_path('pd_end.FCStd'))
    body = doc.getObject('Body')

    touched = [o.Name for o in doc.Objects if 'Touched' in o.State]
    print('  touched on load : %s' % (', '.join(touched) if touched else 'none'))

    for obj in doc.Objects:
        obj.touch()
    doc.recompute(None, True, True)

    still = [o.Name for o in doc.Objects if 'Touched' in o.State or 'Invalid' in o.State]
    print('  after recompute : %s' % (', '.join(still) if still else 'all clean'))

    s = body.Shape
    volume_m3 = si.volume_m3(s)
    d = volume_m3 - REF_VOL_M3
    print('  volume          = %.6f mm3' % (volume_m3 * si.MM3_PER_M3))
    print('  OpenSCAD ref    = %.6f mm3 (%+.6f, %+.4f%%)'
          % (REF_VOL_M3 * si.MM3_PER_M3, d * si.MM3_PER_M3, 100 * d / REF_VOL_M3))
    print('  Part:: port     = %.6f mm3 (%+.9f)'
          % (PART_VOL_M3 * si.MM3_PER_M3,
             (volume_m3 - PART_VOL_M3) * si.MM3_PER_M3))
    print('  valid           = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    tree = [o.Name for o in body.Group]
    print('  feature tree    = %s' % ' -> '.join(tree))
    print('  tip             = %s' % body.Tip.Name)

    ok = (not still and s.isValid() and len(s.Solids) == 1 and abs(d) <= TOL_M3)
    print('  result          = %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
