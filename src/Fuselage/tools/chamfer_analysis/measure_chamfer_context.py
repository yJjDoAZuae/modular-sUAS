"""Where the flange bevel is on the bulkhead, measured from the built solid.

OQ-ARCH-13 needs a reader who has never opened this project to see *which* edge is beveled and
where it runs. That cannot be answered from the bevel's own arithmetic -- the arithmetic gives
a five-corner outline floating in its own rotated frame, which is exactly the drawing that was
rejected as unreadable. So the shapes here are traced from the assembled bulkhead.

Three traces, all from one build:

    plan        a horizontal slice through the middle of the bulkhead, giving the whole part
                in outline so the bevel's run can be marked on it
    section     a vertical slice straight across the flange, giving the profile a reader
                would see if the bulkhead were sawn through there -- plate, flange and the
                beveled edge in place, at the same scale as each other
    piece       the same vertical slice through the chamfer feature on its own. It is one
                of eight positives that are union'd into the flange, so this is material it
                ADDS -- a 45 degree gusset filling the inside corner where the flange meets
                the plate -- not material it removes

Run with FreeCAD's console interpreter, not the venv:

    freecadcmd src/Fuselage/tools/chamfer_analysis/measure_chamfer_context.py \\
        --pass params.json out.json

The output is a snapshot, not a live query: if the bulkhead moves, re-run this before trusting
the drawings that read it.
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

DEFL = 0.04

KEEP = ('unit_width', 'corner_radius', 'corner_offset', 'plate_thickness',
        'bulkhead_thickness', 'flange_thickness', 'flange_chamfer', 'flange_inner_x',
        'flange_y', 'chm_x', 'chm_y_a', 'chm_top', 'chm_deep', 'chm_len_a', 'chm_len_b',
        'bolt_c', 'bolt_offset', 'flange_fillet_radius')


def slice_at(shape, point, normal, _half=None):
    """The closed outlines where `shape` meets the plane through `point` with `normal`.

    `Shape.slice()` rather than intersecting with a constructed rectangle: building a big
    enough rectangle needs its in-plane axes, which are not simply the two world axes the
    normal is not, and getting that wrong returns an empty result that looks like "the
    feature is not here" rather than like a mistake. `slice` takes the normal and the plane's
    offset along it and has no such trap.
    """
    n = App.Vector(*normal)
    return shape.slice(n, n.dot(App.Vector(*point)))


def wires_of(wires, project):
    """Outlines as 2D point lists. `project` maps a 3D point to the drawing's two axes.

    One list per outline. A section can produce several -- separate lumps of material, or a
    lump with a hole in it -- and the drawing fills them with the even-odd rule, so a hole
    nested inside an outline punches through without either having to be labeled as such.
    """
    return [[project(p) for p in w.discretize(Deflection=DEFL)] for w in wires]


def main():
    args = script_args()
    if len(args) < 2:
        print('usage: freecadcmd measure_chamfer_context.py --pass params.json out.json')
        return 0
    path, out = args[0], args[1]

    doc = App.newDocument('chmctx')
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
    res = {'params': P}

    full = doc.getObject('BulkheadFull')
    xy = lambda p: (round(p.x, 4), round(p.y, 4))          # noqa: E731
    yz = lambda p: (round(p.y, 4), round(p.z, 4))          # noqa: E731

    # The bevel's cutting tool is built in the octant's own frame; the octant is then moved
    # by `corner_offset` in x and y before being tiled. Everything below works in the
    # assembled part's frame, so the tool is moved to match rather than the reverse.
    off = P['corner_offset']
    tool = doc.getObject('FlangeChamfer')
    tool_shape = None
    if tool is not None:
        tool_shape = tool.Shape.copy()
        tool_shape.translate(App.Vector(off, off, 0))
    res['tool_bbox'] = None if tool_shape is None else [
        tool_shape.BoundBox.XMin, tool_shape.BoundBox.YMin, tool_shape.BoundBox.ZMin,
        tool_shape.BoundBox.XMax, tool_shape.BoundBox.YMax, tool_shape.BoundBox.ZMax]

    # (1) the whole part in plan, at mid thickness -- the outline a reader recognizes
    z_mid = P['bulkhead_thickness'] / 2.0
    res['plan'] = wires_of(slice_at(full.Shape, (0, 0, z_mid), (0, 0, 1), half), xy)
    res['plan_z'] = z_mid

    # (2) the chamfer's own footprint in plan, at a height inside it, so the drawing marks
    #     its run from measurement rather than asserting where it is
    z_low = P['plate_thickness'] / 2.0
    res['run_z'] = z_low
    res['run'] = [] if tool_shape is None else wires_of(
        slice_at(tool_shape, (0, 0, z_low), (0, 0, 1), half), xy)

    # (3) straight across the flange. The chamfer's long run goes in x, so the plane that
    #     cuts square across it is one of constant x, taken at the middle of that run.
    x_cut = (res['tool_bbox'][0] + res['tool_bbox'][3]) / 2.0 if tool_shape else 0.0
    res['section_x'] = x_cut
    res['section'] = wires_of(slice_at(full.Shape, (x_cut, 0, 0), (1, 0, 0), half), yz)
    res['piece'] = [] if tool_shape is None else wires_of(
        slice_at(tool_shape, (x_cut, 0, 0), (1, 0, 0), half), yz)

    print('plan     z=%7.3f  %d face(s)' % (z_mid, len(res['plan'])))
    print('run      z=%7.3f  %d face(s)' % (z_low, len(res['run'])))
    print('section  x=%7.3f  %d face(s)' % (x_cut, len(res['section'])))
    print('piece    x=%7.3f  %d outline(s)' % (x_cut, len(res['piece'])))
    with open(out, 'w') as f:
        json.dump(res, f)
    print('wrote %s (%d bytes)' % (out, os.path.getsize(out)))
    return 0


if is_entry_point(__name__):
    _c = main()
    sys.stdout.flush()
    sys.exit(_c)
