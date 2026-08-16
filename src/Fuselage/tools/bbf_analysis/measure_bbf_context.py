"""Where the bolt-flange fillet sits, measured from the built solid.

`draw_bolt_flange_fillet.py` draws the fillet's own construction from the parameter
derivation, which is right for that job -- the construction *is* arithmetic. But the
question "where in the bulkhead is this thing" cannot be answered from arithmetic without
re-deriving the whole outer profile, so the context views are traced from the solid
instead, exactly as `joint_analysis/measure_corner_joint.py` traces the corner joint.

Two heights are captured, both through the middle of a feature rather than at a boundary:

    plate     z = plate_thickness / 2, through the flat plate the bulkhead is cut from
    flange    z = (plate_thickness + bulkhead_thickness) / 2, above the plate, where the
              flange wall, the bolt boss and the fillet between them are separate

Run it with FreeCAD's console interpreter, not the venv:

    freecadcmd src/Fuselage/tools/bbf_analysis/measure_bbf_context.py \\
        --pass params.json out.json

`params.json` comes from `tools/export_parameters.py`. The output is a snapshot, not a live
query: if the bulkhead moves, re-run this before trusting the drawings that read it.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', '..', 'freecad')))

import FreeCAD as App
import Part

import bulkhead_full
import parameters
from corner_common import is_entry_point, script_args

DEFL = 0.05

# Everything the context drawings label. `corner_offset` is the octant's own translate, so
# it is what converts between the frame the fillet is built in and the bulkhead's.
KEEP = ('unit_width', 'corner_radius', 'corner_offset', 'plate_thickness',
        'bulkhead_thickness', 'flange_thickness', 'flange_inner_x', 'bolt_c',
        'bolt_hole_radius', 'bolt_thickness', 'flange_fillet_radius', 'relief_r_low',
        'r_bolt_fillet', 'bbf_cx', 'bbf_cy', 'bbf_dx', 'bbf_dy', 'bbf_sx', 'bbf_bx')

# The eight octants, as the sign pattern `bulkhead_full.octant_to_full()` produces: mirror
# about x = y, then about y = 0, then about x = 0. Stored so the drawing does not have to
# re-derive the tiling to place the eight fillets.
TILING = [(sw, sy, sx) for sx in (1, -1) for sy in (1, -1) for sw in (0, 1)]


def faces_at(shape, z, half):
    plane = Part.makePlane(4 * half, 4 * half, App.Vector(-2 * half, -2 * half, z))
    return shape.common(plane).Faces


def wires_of(faces):
    """Outer wire first, then any holes, per face -- `slice()` loses that distinction."""
    out = []
    for f in faces:
        ws = [f.OuterWire] + [w for w in f.Wires if not w.isSame(f.OuterWire)]
        out.append([[(round(p.x, 4), round(p.y, 4))
                     for p in w.discretize(Deflection=DEFL)] for w in ws])
    return out


def main():
    args = script_args()
    if len(args) < 2:
        print('usage: freecadcmd measure_bbf_context.py --pass params.json out.json')
        return 0
    path, out = args[0], args[1]

    doc = App.newDocument('bbfctx')
    bulkhead_full.emit(doc, parameters.seed(path))
    doc.recompute()

    cells = doc.getObject('Params')
    P = {}
    for key in KEEP:
        try:
            P[key] = float(cells.get(key))
        except Exception:
            P[key] = None

    half = P['unit_width']
    levels = {'plate': P['plate_thickness'] / 2.0,
              'flange': (P['plate_thickness'] + P['bulkhead_thickness']) / 2.0}

    res = {'params': P, 'tiling': TILING, 'levels': {}}
    for tag, z in levels.items():
        res['levels'][tag] = cur = {'z': z}
        for name, placed in (('BulkheadFull', False), ('BulkheadSection', True),
                             ('BoltFlangeFillet', False), ('BffBlock', False)):
            obj = doc.getObject(name)
            if obj is None:
                continue
            shape = obj.Shape
            if placed:
                shape = shape.copy()
                shape.Placement = obj.Placement
            cur[name] = wires_of(faces_at(shape, z, half))
        print('%-7s z=%6.3f  %s' % (tag, z, '  '.join(
            '%s:%d' % (k, len(v)) for k, v in cur.items() if k != 'z')))

    with open(out, 'w') as f:
        json.dump(res, f)
    print('wrote %s (%d bytes)' % (out, os.path.getsize(out)))
    return 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
