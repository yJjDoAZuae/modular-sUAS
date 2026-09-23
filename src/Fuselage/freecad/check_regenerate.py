"""IP-FC-5: does the Part:: corner survive a parameter regenerate across several U?

The sweep produces 576 variants, so a paradigm that builds one corner correctly but breaks
when a parameter moves is no use. This rebuilds the whole corner at each U and checks the
result against the matching OpenSCAD render, plus the invariants that must hold at every U:
one valid solid, and a bounding box that follows corner_radius and unit_length.

Parameters come from variants.py -- the real tables, not the driver's 1.0U constants.
Reference volumes come from regen_U*.stl, rendered from ref_regenerate.scad at the same
values.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import Params, is_entry_point, out_path
from measure import measure
from part_corner import build
from variants import TABLE, panel_overlap

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    """Found while auditing IP-TEST-10 (doc/implementation/test_coverage.md): this whole
    script was top-level module code with no verdict of any kind -- not even a `main()` to
    return one from -- so it always exited 0 regardless of `failures`. Worse than
    check_end_bands.py's version of the same bug: there was no missing-reference guard either,
    so a missing `regen_U*.stl` would have raised inside `measure()` uncaught, and under
    freecadcmd's own exit-code-on-exception hazard (see general.md) that would ALSO have
    silently reported success -- the same "false pass" class check_tree.py had. Fixed with a
    real per-U and overall verdict, a missing-reference check before `measure()` runs at all,
    and the standard flush-before-`sys.exit()` guard.
    """
    App.newDocument('regen')

    print('%5s %6s %6s %14s %14s %12s %9s %7s %6s %s'
          % ('U', 'bt', 'pt', 'OpenSCAD', 'FreeCAD', 'delta', 'rel', 'build', 'faces',
             'checks'))

    failures = []
    checked = 0
    for U, bt, pt in TABLE:
        stl = out_path('regen_U%g.stl' % U)
        if not os.path.isfile(stl):
            print('%5g  -- reference %s not rendered, skipped' % (U, os.path.basename(stl)))
            continue
        checked += 1

        p = Params(U=U, bulkhead_thickness=bt, panel_thickness=pt,
                   panel_overlap=panel_overlap(pt))

        t0 = time.time()
        shape = build(p)
        dt = time.time() - t0

        _, ref, lo, hi = measure(stl)

        d = shape.Volume - ref
        bb = shape.BoundBox

        checks = []
        if not shape.isValid():
            checks.append('INVALID')
        if len(shape.Solids) != 1:
            checks.append('solids=%d' % len(shape.Solids))
        # the corner spans its full unit_length in z, and reaches corner_radius in x and y
        if abs(bb.ZMax - p.unit_length) > 1e-6 or abs(bb.ZMin) > 1e-6:
            checks.append('z=[%.4f,%.4f]' % (bb.ZMin, bb.ZMax))
        if abs(bb.XMax - p.corner_radius) > 0.01:
            checks.append('xmax=%.4f' % bb.XMax)
        if abs(d) / ref > 1e-4:
            checks.append('VOLUME')
        if checks:
            failures.append((U, checks))

        print('%5g %6g %6g %14.5f %14.5f %+12.5f %+8.4f%% %6.2fs %6d %s'
              % (U, bt, pt, ref, shape.Volume, d, 100 * d / ref, dt, len(shape.Faces),
                 ' '.join(checks) if checks else 'ok'))

    print('')
    if checked == 0:
        print('regenerate: NO REFERENCE MESHES RENDERED -- nothing was actually verified.')
        return 1
    print('regenerate: %d of %d U values clean' % (checked - len(failures), checked))
    for U, checks in failures:
        print('  U=%g: %s' % (U, ' '.join(checks)))
    return 0 if not failures else 1


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
