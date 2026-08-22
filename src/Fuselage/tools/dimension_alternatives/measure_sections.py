"""Snapshot the geometry OQ-DES-D2's drawings are traced from.

The question is what a part drawing should carry, and it cannot be argued in prose -- every
candidate scheme annotates the *same* geometry differently, so the schemes only become
comparable when they are drawn. This sections the built parts and writes what it finds;
`draw_dimension_alternatives.py` reads the result and draws each scheme on it.

Nothing here evaluates a design equation. The outlines come from solids FreeCAD built, for
the reason `joint_analysis/measure_corner_joint.py` states about its own snapshot: an
equation and the solid it is supposed to produce disagreeing is exactly the class of defect
a traced drawing finds and a computed one hides.

    freecadcmd measure_sections.py --pass corner.json boom.json out.json

`corner.json` and `boom.json` are what `export_parameters.py` writes, one frame variant and
one boom variant. Values are millimeters, as the OpenSCAD path uses them.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', '..', 'freecad')))

import FreeCAD as App
import Part

import build_part
from corner_common import is_entry_point, script_args

# A face is a *cap* when its normal is within about ten degrees of the print axis, and a
# *wall* otherwise. The split is what makes a material estimate possible: printed at one or two
# perimeters with no infill, these parts get no top or bottom either, so the material is the
# wall and the caps are not there. 0.985 is cos(10 deg).
CAP_COSINE = 0.985

# From `design_constants.json`, printer group. Restated rather than read because this script
# runs under freecadcmd, which cannot import `fuselage_variants` -- and it is used only to
# report an estimate, never to build anything.
EXTRUSION_WIDTH = 0.6

# How finely a wire is reduced to a polyline. 0.02 mm is well under the 0.1 mm clearance the
# drawings are about, so a traced outline cannot visually misplace the thing being discussed,
# and it keeps a corner section to a few hundred points rather than a few thousand.
DEFLECTION = 0.02


def loops(shape, z):
    """The closed section loops at height `z`, largest area first.

    Sorted by area because that is what identifies them: the largest is the outer profile and
    the next is the interior aperture -- the "structural cell" a drawing user asks the size
    of. Identifying them by index in the slice result would depend on face ordering, which
    IP-FC-5 established is not stable across `U`.
    """
    found = []
    for wire in shape.slice(App.Vector(0, 0, 1), z):
        if not wire.isClosed():
            continue
        try:
            face = Part.Face(wire)
        except Exception:
            continue
        found.append((face.Area, wire, face))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def trace(wire):
    """One closed loop as a list of [x, y] points."""
    return [[round(p.x, 4), round(p.y, 4)]
            for p in wire.discretize(Deflection=DEFLECTION)]


def wall_and_cap(shape):
    """Surface area split into wall and cap, by face normal against the print axis.

    A face whose normal cannot be evaluated is counted as wall, which is the conservative
    direction: it raises the material estimate rather than lowering it.
    """
    wall = cap = 0.0
    for face in shape.Faces:
        try:
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
        except Exception:
            wall += face.Area
            continue
        if abs(normal.z) >= CAP_COSINE:
            cap += face.Area
        else:
            wall += face.Area
    return wall, cap


def section(kind, params_path, z):
    doc = App.newDocument(kind)
    tip = build_part.build(doc, kind, params_path)
    doc.recompute()
    shape = tip.Shape

    found = loops(shape, z)
    wall, cap = wall_and_cap(shape)
    out = {
        'kind': kind,
        'z': z,
        'volume_mm3': round(shape.Volume, 4),
        'area_mm2': round(shape.Area, 4),
        'wall_area_mm2': round(wall, 4),
        'cap_area_mm2': round(cap, 4),
        # Walls only, no caps, no infill -- the case the drawing user described. Capped at the
        # solid volume, because where the part is thinner than two walls the two walls are the
        # same material and the product would count it twice.
        'shelled_mm3': [round(min(wall * n * EXTRUSION_WIDTH, shape.Volume), 4)
                        for n in (1, 2, 3)],
        'faces': len(shape.Faces),
        'bbox': [round(v, 4) for v in (shape.BoundBox.XLength, shape.BoundBox.YLength,
                                       shape.BoundBox.ZLength)],
        'loops': [{'area_mm2': round(area, 4),
                   'bbox': [round(face.BoundBox.XLength, 4),
                            round(face.BoundBox.YLength, 4)],
                   'points': trace(wire)}
                  for area, wire, face in found],
    }
    App.closeDocument(doc.Name)
    return out


def main():
    args = script_args()
    if len(args) != 3:
        sys.stderr.write('usage: measure_sections.py --pass CORNER.json BOOM.json OUT.json\n')
        sys.stderr.flush()
        raise SystemExit(2)
    frame_path, boom_path, out_path = args

    with open(frame_path, encoding='utf-8') as handle:
        frame = json.load(handle)
    with open(boom_path, encoding='utf-8') as handle:
        boom = json.load(handle)

    corner = frame['corner_parameters']
    bulkhead = frame['parameters']

    document = {
        'variant': frame['variant'],
        'corner_parameters': corner,
        'bulkhead_parameters': bulkhead,
        'sections': {
            # The corner is sectioned at mid-bay, in the middle section, clear of the end and
            # transition features -- that is the profile the panel and longeron joints are
            # constant over, and the one a cross-section view would show.
            'corner': section('corner', frame_path, corner['unit_length'] / 2.0),
            'bulkhead': section('bulkhead', frame_path,
                                bulkhead['bulkhead_thickness'] / 2.0),
            'boom_bulkhead': section(
                'boom_bulkhead', boom_path,
                boom['boom_parameters']['boom_bulkhead_thickness'] / 2.0),
        },
    }

    with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(document, handle, indent=1, sort_keys=True)
        handle.write('\n')
    print('wrote %s' % out_path)
    return 0


if is_entry_point(__name__):
    raise SystemExit(main())
