"""Where the four flange fillets sit, measured from the built bulkhead.

OQ-ARCH-14 asks whether the outer-corner and greeble-to-web fillets still need converting.
That cannot be judged from a drawing of a circle floating on its own -- the first attempt at
these figures was exactly that, and it was rejected for showing neither fillet in the part it
belongs to. So every shape here is traced out of the assembled bulkhead, and the detail views
are cut-outs of the same trace rather than separate schematics drawn to match.

Two horizontal sections, the same pair `bbf_analysis/measure_bbf_context.py` takes:

    plate     halfway up the base plate, which is the part's silhouette
    flange    halfway up the standing flange, where the wall, the greeble web, the bolt boss
              and all four fillets are separate bodies and can be told apart

At each level:

    BulkheadFull      the whole part, for the plan view
    BulkheadSection   the one octant it is built from, placed, for the detail views
    FlangePositive    the fuse of the eight bodies below
    UNION             each of those eight on its own, so a fillet can be told from the
                      material around it and asked whether it contributes any
    <fillet>InPart    each fillet intersected with the finished octant -- see IN_PART

The fillets and their neighbors are traced in the octant's own frame, not the bulkhead's, so
`draw_fillet_scope.tiled()` places the eight copies and the detail views can work in the frame
the generator writes its expressions in. `TILING` is stored rather than re-derived, for the
reason given beside it.

Run with FreeCAD's console interpreter, not the venv:

    freecadcmd src/Fuselage/tools/fillet_scope_analysis/measure_fillet_context.py \\
        --pass params.json out.json

The output is a snapshot, not a live query: re-run it if the bulkhead moves, or the drawings
that read it will keep showing the old shape while still looking authoritative.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', '..', 'freecad')))

import FreeCAD as App
import Part

import bulkhead_full
import parameters
from corner_common import is_entry_point, script_args

DEFL = 0.03

# Everything the drawings label or place something by, that is still a sheet row.
# `corner_offset` is the octant's own translate, so it is what converts between the frame the
# fillets are built in and the bulkhead's.
KEEP = ('unit_width', 'corner_radius', 'corner_offset', 'bulkhead_thickness',
        'plate_thickness', 'flange_thickness', 'flange_inner_x', 'flange_y',
        'flange_fillet_radius', 'bolt_c', 'bolt_offset', 'bolt_hole_radius', 'bolt_boss_r',
        'web_width')

# The fillet centers the drawings label. **These stopped being sheet rows when IP-FC-73
# converted the four corners** -- they are solved by `FilletTangency` and read back from its
# reference dimensions, so that is where this reads them too, rather than recomputing an
# arithmetic the model no longer contains. `gtw_ex` and `gtw_ey` are the point where the
# greeble-to-web fillet meets the 45 degree wall, one radius along the wall's normal from the
# center, which the tangency makes exact.
SKETCH = 'FilletTangency'
CENTERS = ('ocf', 'gtw', 'bbf', 'wtb')

# The eight octants, as the sign pattern `bulkhead_full.octant_to_full()` produces: mirror
# about x = y, then about y = 0, then about x = 0. Stored so the drawing does not have to
# re-derive the tiling to place eight copies of a fillet.
TILING = [(sw, sy, sx) for sx in (1, -1) for sy in (1, -1) for sw in (0, 1)]

# Which frame each trace comes back in is not a choice this script makes. `obj.Shape` already
# carries the object's own Placement, so `BulkheadSection` -- whose translate to the corner
# lives on its Placement -- arrives in the bulkhead's frame, while the fillets, which have no
# placement of their own, arrive in the octant's. Re-assigning `shape.Placement = obj.Placement`
# looks like it converts between the two and does nothing at all; the conversion is the
# translate by `corner_offset` applied explicitly below.
#
# `UNION` is every member `bulkhead_positive.flange_positive()` fuses, in its build order,
# and `FlangePositive` is the fuse itself. Both are traced, and keeping them apart is the
# point: a fillet's footprint always falls inside `FlangePositive`, because the fuse contains
# it, so asking "is this fillet adding material anything else already supplies" can only be
# answered against the other seven.
UNION = ('FlangeTip', 'FlangeChamfer', 'FlangeBoss', 'OuterCornerFillet',
         'GreebleBoltWebTip', 'GreebleToWebFillet', 'WebToBoltFillet', 'BoltFlangeFillet')

TRACED = ('BulkheadFull', 'BulkheadSection', 'FlangePositive') + UNION

# The four fillets, traced a second time as what survives into the finished octant.
#
# A fillet is a *positive*: it is fused into the flange before the bolt hole, the corner
# socket and the octant mask are cut. Drawn as built, it therefore paints straight over the
# bolt hole and across material the finished part does not have, which reads as a placement
# error rather than as a stage of the build. So each is also intersected with
# `BulkheadSection` -- the octant as finally built -- and it is that version the plan view
# uses. Both are kept: the detail views need the body as built, because what the body
# overlaps is the question being asked.
FILLETS = ('OuterCornerFillet', 'GreebleToWebFillet', 'WebToBoltFillet', 'BoltFlangeFillet')
IN_PART = '%sInPart'


def faces_at(shape, z, half):
    """The section at height `z`, as faces -- a horizontal plane big enough to cover the part.

    Intersecting with a constructed rectangle is safe here only because the plane is
    horizontal, so its in-plane axes are the two world axes. `slice()` would do as well but
    returns loose wires, and the drawings need to know which wire is a hole.
    """
    plane = Part.makePlane(4 * half, 4 * half, App.Vector(-2 * half, -2 * half, z))
    return shape.common(plane).Faces


def wires_of(faces):
    """Outer wire first, then any holes, per face -- so an even-odd fill punches correctly."""
    out = []
    for f in faces:
        ws = [f.OuterWire] + [w for w in f.Wires if not w.isSame(f.OuterWire)]
        out.append([[(round(p.x, 4), round(p.y, 4))
                     for p in w.discretize(Deflection=DEFL)] for w in ws])
    return out


def solved_centers(doc, P):
    """The four fillet centers, out of the sketch that solves them, plus what the drawings
    need alongside them.

    `gtw_start` is computed here rather than read: it was the sheet row
    `max(flange_inner_x; -bolt_offset)`, and OQ-ARCH-14 removed it. It is kept in the snapshot
    because these figures exist to show what that clamp did -- the drawings label both
    branches of it -- so the value has to come from somewhere once the model no longer holds
    it. `gtw_active` records the condition that replaced it.
    """
    out = {}
    sk = doc.getObject(SKETCH)
    for tag in CENTERS:
        for axis in ('cx', 'cy'):
            name = '%s_%s' % (tag, axis)
            try:
                out[name] = sk.getDatum(name).Value
            except Exception:
                out[name] = None
    r = P['flange_fillet_radius']
    if out['gtw_cx'] is not None:
        out['gtw_ex'] = out['gtw_cx'] + r / math.sqrt(2)
        out['gtw_ey'] = out['gtw_cy'] - r / math.sqrt(2)
    else:
        out['gtw_ex'] = out['gtw_ey'] = None
    out['gtw_start'] = max(P['flange_inner_x'], P['bolt_c'])
    out['gtw_active'] = P['flange_inner_x'] >= P['bolt_c']
    return out


def main():
    args = script_args()
    if len(args) < 2:
        print('usage: freecadcmd measure_fillet_context.py --pass params.json out.json')
        return 0
    path, out = args[0], args[1]

    doc = App.newDocument('fsctx')
    bulkhead_full.emit(doc, parameters.seed(path))
    doc.recompute()

    cells = doc.getObject('Params')
    P = {}
    for key in KEEP:
        try:
            P[key] = float(cells.get(key))
        except Exception:
            P[key] = None
    P.update(solved_centers(doc, P))

    half = P['unit_width']
    levels = {'plate': P['plate_thickness'] / 2.0,
              'flange': (P['plate_thickness'] + P['bulkhead_thickness']) / 2.0}

    # The finished octant, moved back into the octant's frame so it can be intersected with
    # bodies that were never placed.
    off = P['corner_offset']
    section = doc.getObject('BulkheadSection')
    local_section = None
    if section is not None:
        local_section = section.Shape.copy()
        local_section.translate(App.Vector(-off, -off, 0))

    res = {'params': P, 'tiling': TILING, 'levels': {}}
    missing = []
    for tag, z in sorted(levels.items()):
        res['levels'][tag] = cur = {'z': z}
        for name in TRACED:
            obj = doc.getObject(name)
            if obj is None:
                # An absent greeble-to-web fillet is a state the model has since OQ-ARCH-14
                # and is not a fault; anything else missing is.
                if not (name == 'GreebleToWebFillet' and not P['gtw_active']):
                    missing.append(name)
                continue
            cur[name] = wires_of(faces_at(obj.Shape, z, half))
        for name in FILLETS:
            obj = doc.getObject(name)
            if obj is None or local_section is None:
                continue
            cur[IN_PART % name] = wires_of(faces_at(
                obj.Shape.common(local_section), z, half))
        print('%-7s z=%6.3f  %s' % (tag, z, '  '.join(
            '%s:%d' % (k, len(v)) for k, v in cur.items() if k != 'z')))

    # An empty intersection everywhere means the two frames did not line up, which draws as
    # "these fillets are not in the part" rather than as a mistake.
    if not any(cur.get(IN_PART % n) for cur in res['levels'].values() for n in FILLETS):
        print('NO fillet survives into the octant at either level -- check the frames')
        return 1

    # A name that resolves to nothing traces as an absence, which draws as "the feature is
    # not there" rather than as a mistake. Say so instead.
    if missing:
        print('NOT FOUND in the document: %s' % ', '.join(sorted(set(missing))))
        return 1

    with open(out, 'w', newline='\n') as f:
        json.dump(res, f)
    print('wrote %s (%d bytes)' % (out, os.path.getsize(out)))
    return 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
