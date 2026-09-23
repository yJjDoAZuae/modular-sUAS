"""IP-TEST-11 (doc/implementation/test_coverage.md): a committed regression for IP-FC-33's
claim (freecad_migration.md), which had none until now.

IP-FC-33 measured `mesh_to_brep.py` on `U_1.0 end_bolt 3/16in`: the real OpenSCAD mesh
against the matching FreeCAD bulkhead B-rep agrees to **max 0.000158 mm, mean 0.000025 mm**
over 300 points, and the same mesh against a *corner's* B-rep (a deliberately wrong part, the
negative control) disagrees by **max 57.310369 mm** -- five orders of magnitude apart. Nothing
committed re-built that pair; `mesh_to_brep.py`'s own `main()` is a generic CLI tool with no
default fixture, so this reproduces both halves of the claim from the same already-committed
`out/reference_bulkhead.params.json` fixture (which carries both the BULKHEAD and CORNER
tables for this exact configuration -- see `check_build_part.py`).

The reference mesh (`ref_bulkhead_full.stl`) is a build artifact, rendered from
`ref_bulkhead_full.scad` (which is already self-contained at this exact configuration -- no
`-D` overrides) and is not kept in the tree, the same convention `check_tree.py`'s
`regen_U*.stl` uses:

    openscad -o out/ref_bulkhead_full.stl ref_bulkhead_full.scad

Skips (does not false-pass) if the mesh is missing, the same fix `check_tree.py` needed for
the same reason.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import bulkhead_full
import corner_tree
import mesh_to_brep as mt
import parameters
from corner_common import is_entry_point, out_path, script_args

DEFAULT_PARAMS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'out', 'reference_bulkhead.params.json')
REF_MESH = out_path('ref_bulkhead_full.stl')

# The true pair: the mesh against its own part's B-rep, within the module's own DEFAULT_TOL_MM.
TRUE_TOL_MM = mt.DEFAULT_TOL_MM
# The false pair: the same mesh against a different part's B-rep. IP-FC-33 measured 57.3 mm;
# any value clearly on the "different part" side of TRUE_TOL_MM confirms the check would have
# caught a mismatch, without pinning today's corner geometry to that exact historical figure.
FALSE_FLOOR_MM = 1.0


def _build(doc_name, table, fcstd_name, params_path):
    doc = App.newDocument(doc_name)
    seed = parameters.seed(params_path, table)
    if table == parameters.BULKHEAD:
        tip = bulkhead_full.emit(doc, seed)
    else:
        tip = corner_tree.emit(doc, seed)
    doc.recompute()
    path = out_path(fcstd_name)
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    return path


def main():
    args = script_args()
    params_path = args[0] if args else DEFAULT_PARAMS
    if not os.path.isfile(params_path):
        print('no params.json at %s -- generate with tools/export_parameters.py '
              '1.0 end_bolt 3/16in' % params_path)
        return 1
    if not os.path.isfile(REF_MESH):
        print('no reference mesh at %s -- render with:' % REF_MESH)
        print('  openscad -o "%s" ref_bulkhead_full.scad' % REF_MESH)
        print('checked 0 of 2 pairs -- treating as a failure, not a skip (see check_tree.py '
              'IP-TEST-7 for why a zero-checked run must not read as a pass)')
        return 1

    bulkhead_doc = _build('mesh_to_brep_bulkhead', parameters.BULKHEAD,
                          'check_mesh_to_brep_bulkhead.FCStd', params_path)
    corner_doc = _build('mesh_to_brep_corner', parameters.CORNER,
                        'check_mesh_to_brep_corner.FCStd', params_path)

    fail = []

    print('TRUE PAIR -- the mesh against its own part (bulkhead_full)')
    shape = mt.tip_shape(bulkhead_doc, expect=bulkhead_full.REF)
    used, worst, mean, total = mt.deviation(REF_MESH, shape, mt.DEFAULT_POINTS)
    print('  %d of %d mesh point(s) sampled' % (used, total))
    print('  deviation  max %.6f mm   mean %.6f mm   threshold %.6f mm'
          % (worst, mean, TRUE_TOL_MM))
    if worst > TRUE_TOL_MM:
        fail.append('true pair: B-rep and mesh disagree by more than %.6f mm' % TRUE_TOL_MM)

    print('\nFALSE PAIR -- the same mesh against a different part (corner_tree), the negative '
          'control')
    shape = mt.tip_shape(corner_doc)
    used, worst, mean, total = mt.deviation(REF_MESH, shape, mt.DEFAULT_POINTS)
    print('  %d of %d mesh point(s) sampled' % (used, total))
    print('  deviation  max %.6f mm   mean %.6f mm   floor %.6f mm'
          % (worst, mean, FALSE_FLOOR_MM))
    if worst < FALSE_FLOOR_MM:
        fail.append('false pair: a mismatched part read as agreeing -- the method has no '
                    'separation left')

    print('\n  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
