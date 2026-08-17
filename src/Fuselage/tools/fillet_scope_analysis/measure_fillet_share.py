"""How much material each flange fillet actually contributes, as a volume.

Tracing the bulkhead for OQ-ARCH-14 showed the greeble-to-web fillet's section lying inside
material the other bodies already supply. A section at two heights cannot settle that -- it
samples two planes out of a solid -- so this measures it the only way that is conclusive.

Two separate questions, because a fillet can fail either test and they mean different things.

**Does the fuse gain anything by including it?** `flange_positive()` fuses eight bodies, and
for each fillet among them:

    own        the fillet's own volume, in mm^3
    shared     the part of it the other seven already occupy
    net        what the fuse gains by including it

**Does any of it survive into the part?** The positives are fused before the bolt hole, the
corner socket and the octant mask are cut, so a body can contribute to the positive and still
be drilled straight out again:

    in_part    the volume left after `bulkhead_section` finishes cutting

A `net` of zero means the fillet is inert in the fuse. An `in_part` of zero means it is absent
from the finished part however the fuse went. Both are facts about the design rather than the
port, and both hold for the OpenSCAD source too -- the FreeCAD generator is a transcription of
it, and `fillets.py` builds the same polygon minus the same relief stack.

    freecadcmd src/Fuselage/tools/fillet_scope_analysis/measure_fillet_share.py \\
        --pass params.json [out.json]

Volumes are mm^3, as the OpenSCAD path uses them.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', '..', 'freecad')))

import FreeCAD as App

import bulkhead_section
import parameters
from corner_common import is_entry_point, script_args

# Every body `flange_positive()` fuses, in its build order.
UNION = ('FlangeTip', 'FlangeChamfer', 'FlangeBoss', 'OuterCornerFillet',
         'GreebleBoltWebTip', 'GreebleToWebFillet', 'WebToBoltFillet', 'BoltFlangeFillet')

FILLETS = ('OuterCornerFillet', 'GreebleToWebFillet', 'WebToBoltFillet', 'BoltFlangeFillet')

# Below this a difference is the boolean kernel's noise, not material. The same threshold
# IP-FC-68 settled on for a volume delta between two builds of one part.
NIL = 1.0e-6


def main():
    args = script_args()
    if not args:
        print('usage: freecadcmd measure_fillet_share.py --pass params.json [out.json]')
        return 0
    path = args[0]

    doc = App.newDocument('fshare')
    # The octant, not just the positive: `in_part` needs what the negatives leave behind, and
    # building the section gives both, since the positive is one of its inputs.
    bulkhead_section.emit(doc, parameters.seed(path))
    doc.recompute()

    cells = doc.getObject('Params')
    P = {}
    for key in ('unit_width', 'flange_inner_x', 'bolt_offset', 'gtw_start',
                'flange_fillet_radius'):
        P[key] = float(cells.get(key))
    P['branch'] = ('flange face' if abs(P['gtw_start'] - P['flange_inner_x']) < 1e-9
                   else 'bolt center')

    shapes = {}
    for name in UNION:
        obj = doc.getObject(name)
        if obj is None:
            print('NOT FOUND in the document: %s' % name)
            return 1
        shapes[name] = obj.Shape

    # `obj.Shape` already carries the object's Placement, so the section has to be brought
    # back to the frame the fillets are built in before it can meet them. Undoing the
    # object's own translate rather than subtracting `corner_offset` keeps this right in both
    # documents: `bulkhead_full` puts that translate on the section's Placement, and
    # `bulkhead_section` on its own does not translate at all and has no such row. Getting it
    # wrong makes every intersection empty, which reads as "no fillet is in the part" rather
    # than as a frame mismatch.
    section = doc.getObject('BulkheadSection')
    if section is None:
        print('NOT FOUND in the document: BulkheadSection')
        return 1
    local = section.Shape.copy()
    local.translate(section.Placement.Base.negative())

    # How much of the bolt-to-corner web is outside the flange base at all.
    #
    # The greeble-to-web fillet rounds the junction where that web emerges from the corner
    # block, so the junction only exists if some of the web is outside the block. When
    # `flange_inner_x` falls outboard of the bolt center the block reaches past the bolt and
    # swallows the whole web, there is no junction, and `max(flange_inner_x; -bolt_offset)`
    # parks the fillet on the bolt centerline instead of reporting that.
    web = doc.getObject('GreebleBoltWebTip')
    base = doc.getObject('FlangeTip')
    exposed = None
    if web is not None and base is not None:
        exposed = web.Shape.cut(base.Shape).Volume
        P['web_volume'] = web.Shape.Volume
        P['web_exposed'] = exposed
        print('web outside the flange base  %10.5f of %10.5f mm^3%s'
              % (exposed, web.Shape.Volume,
                 '   NONE -- no junction to fillet' if exposed < NIL else ''))

    rows = {}
    for who in FILLETS:
        rest = [shapes[n] for n in UNION if n != who]
        merged = rest[0].fuse(rest[1:])
        own = shapes[who].Volume
        shared = shapes[who].common(merged).Volume
        net = own - shared
        in_part = shapes[who].common(local).Volume
        rows[who] = {'own': own, 'shared': shared, 'net': net, 'in_part': in_part,
                     'inert': net < NIL, 'absent': in_part < NIL}
        print('%-19s own %10.5f   shared %10.5f   net %10.5f%s   in_part %10.5f%s'
              % (who, own, shared, net, ' INERT' if net < NIL else '      ',
                 in_part, '   ABSENT' if in_part < NIL else ''))

    print('gtw_start %.4f = max(flange_inner_x %.4f; -bolt_offset %.4f) -> %s branch'
          % (P['gtw_start'], P['flange_inner_x'], -P['bolt_offset'], P['branch']))

    if len(args) > 1:
        with open(args[1], 'w') as f:
            json.dump({'params': P, 'fillets': rows}, f, indent=1)
        print('wrote %s' % args[1])
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
