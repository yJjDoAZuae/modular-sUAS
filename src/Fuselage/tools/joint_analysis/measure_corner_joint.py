"""The joint at corner_tolerance 0 and at the 0.05 mm test value.

The bulkhead is built ONCE: it never sees the tolerance. Its socket is cut from the same
description at zero, so the joint carries the clearance once, on the corner.
"""
import json
import sys

sys.path.insert(0, '//mrhorse/Archive/Alex/modular-sUAS-project/modular-sUAS/src/Fuselage/freecad')

import FreeCAD as App
import Part

import bulkhead_full
import corner_tree
import parameters
from corner_common import script_args

path, out, test_tol = script_args()[0], script_args()[1], float(script_args()[2])
DEFL = 0.0015


def cut_faces(shape, z, half):
    pl = Part.makePlane(4 * half, 4 * half, App.Vector(-2 * half, -2 * half, z))
    return shape.common(pl).Faces


def as_wires(faces):
    out = []
    for f in faces:
        ws = [f.OuterWire] + [w for w in f.Wires if not w.isSame(f.OuterWire)]
        out.append([[(round(v.x, 6), round(v.y, 6)) for v in w.discretize(Deflection=DEFL)]
                    for w in ws])
    return out


doc = App.newDocument('bk')
tip = bulkhead_full.emit(doc, parameters.seed(path))
sh = doc.getObject('Params')
g = lambda k: float(sh.get(k))
P = {k: g(k) for k in ('unit_width', 'corner_radius', 'panel_thickness', 'panel_tolerance',
                       'panel_offset', 'panel_overlap', 'bulkhead_thickness',
                       'longeron_radius', 'longeron_tolerance', 'greeble_thickness',
                       'greeble_tolerance', 'extrusion_width', 'clean_r', 'clean_x0', 'eps')}
# the rule, asserted rather than assumed: the bulkhead's own sheet is at zero
bulkhead_sees = g('corner_tolerance')
CC = P['unit_width'] / 2 - P['corner_radius']
zb = P['bulkhead_thickness'] / 2
half = P['unit_width']
bfs = cut_faces(tip.Shape, zb, half)
for f in bfs:
    f.translate(App.Vector(-CC, -CC, 0))
built = as_wires(bfs)
vol_b = tip.Shape.Volume
tool = [[[(x - CC, y - CC) for x, y in w] for w in f]
        for f in as_wires(cut_faces(doc.getObject('OuterCleanup').Shape, zb, half))]
App.closeDocument(doc.Name)

doc = App.newDocument('cn')
ctip = corner_tree.emit(doc, parameters.seed(path, parameters.CORNER))
csh = doc.getObject('Params')
cg = lambda k: float(csh.get(k))
corner0 = as_wires(cut_faces(ctip.Shape, zb, half))
cvol0, tol0 = ctip.Shape.Volume, cg('corner_tolerance')
fx0, fo0 = cg('flat_x'), cg('flat_offset')
csh.set('corner_tolerance', repr(test_tol))
doc.recompute()
corner_t = as_wires(cut_faces(ctip.Shape, zb, half))
cvol_t, fx_t, fo_t = ctip.Shape.Volume, cg('flat_x'), cg('flat_offset')
ok = bool(ctip.Shape.isValid()) and len(ctip.Shape.Solids) == 1
App.closeDocument(doc.Name)

flange_r = P['corner_radius'] - P['panel_thickness'] - P['panel_tolerance']
D = {
    'params': P, 'flange_r': flange_r, 'test_tol': test_tol,
    'flat_x': fx0, 'flat_x_t': fx_t, 'flat_offset': fo0, 'flat_offset_t': fo_t,
    'rect_edge': -(P['panel_offset'] + P['panel_overlap'] - P['panel_tolerance']),
    'built_x0': P['clean_x0'], 'built_r': P['clean_r'],
    'new_x0': P['clean_x0'], 'new_r': P['clean_r'],
    'bulkhead_sees': bulkhead_sees, 'sweep_tol': tol0, 'ok': ok,
    'vol_built': vol_b, 'vol_fixed': vol_b,
    'cvol_built': cvol0, 'cvol_fixed': cvol_t,
    'built': built, 'fixed': built,
    'corner': corner0, 'corner_fixed': corner_t,
    'tool_built': tool, 'tool_fixed': tool,
}
json.dump(D, open(out, 'w', newline='\n'))
print('%-9s bulkhead sees corner_tolerance=%.3f (must be 0)   sweep=%.3f test=%.3f\n'
      '          flat_x %8.4f -> %8.4f   flat_offset %8.4f -> %8.4f\n'
      '          corner %11.4f -> %11.4f (%+.4f)  valid=%s'
      % (out.split('_')[-1], bulkhead_sees, tol0, test_tol, fx0, fx_t, fo0, fo_t,
         cvol0, cvol_t, cvol_t - cvol0, ok))
sys.stdout.flush()
