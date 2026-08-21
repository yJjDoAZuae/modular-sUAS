"""OQ-ARCH-14: how much part does omitting the clamped greeble-to-web fillet actually remove?

The decision leaves the fillet out wherever the bolt-to-corner web never reaches the flange's
inner face -- 27 of 148 valid variants, every one at U <= 1.0. OpenSCAD still builds a body
there, because `gtw_start = max(flange_inner_x; -bolt_offset)` relocated the fillet onto the
bolt centerline rather than omitting it, so in exactly those variants the port and the
reference now disagree by whatever that body contributed.

**This measures the disagreement directly, which the bit-identical check cannot.** The other
three corners are checked by building them and comparing volumes to the digit; this one has to
answer "how much material does the flown part lose".

That answer is not the body's own volume -- almost all of it overlaps the bolt boss and the
neighboring fillets. Nor is it what fusing the body into the finished octant adds, which is
the wrong stage and overstates it badly: **the clamped body sits on the bolt centerline,
inside the bolt hole**, so fusing it into a part whose hole is already cut fills the hole back
in. Measured that way at `U=0.75 end_bolt 1/8in` it reads 1.374 mm3, and the real figure is a
small fraction of that, because the bolt hole is cut *after* the fillet is fused. So the
octant is built twice, once each way, at the one point in the build where the difference is
the difference.

    freecadcmd measure_clamped_gtw.py --pass params.json [out.json]

Nothing here is a source of truth about the model. `clamped_body()` is the construction
OQ-ARCH-14 removed, restored locally so there is something to measure against; it is built
from literal numbers rather than sheet rows precisely so it cannot be mistaken for a live
parameter, and nothing in `fillets.py` reads it.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..', 'freecad')))

import FreeCAD as App

import bulkhead_section
import corner_tree as C
import fillets
import parameters
from corner_common import is_entry_point, script_args

SQ2 = math.sqrt(2.0)


def clamped_body(doc):
    """The body the clamp used to build, at the values the clamp used to produce.

    Stands in for `fillets.greeble_to_web_fillet` and builds under its name, so the octant
    around it is assembled and cut exactly as it was before OQ-ARCH-14.

    The five rows this reconstructs -- `gtw_start` through `gtw_cy` -- and the two that placed
    the diagonal clip were `fillets.PARAMS` rows until 2026-08-17. They are numbers here, not
    expressions, so the document this builds cannot be edited and re-measured; that is
    deliberate, since the construction being measured no longer exists and should not look
    live.
    """
    cells = doc.getObject('Params')

    def g(alias):
        return float(cells.get(alias))

    def n(x):
        return '%.17g' % x

    fillets._tangency(doc)
    r, ft, bt = g('flange_fillet_radius'), g('flange_thickness'), g('bulkhead_thickness')
    far = g('far')
    start = max(g('flange_inner_x'), g('bolt_c'))       # the clamp itself
    cx = start - r
    ey = cx + r / SQ2 + SQ2 / 2 * ft
    cy = ey + r / SQ2
    half = (cx + cy) / 2.0

    block = C._box(doc, 'GtwBlock', n(start - cx), n(cy - ey), n(bt), n(cx), n(ey), '0')
    node = C._cut(doc, 'GtwDiag', block,
                  C._box(doc, 'GtwDiagBox', n(far * 2), n(far * 2 * SQ2), n(bt * 3),
                         n(half + far * (1 - SQ2)), n(half - far * (1 + SQ2)), n(-bt),
                         angle=45))
    node = fillets._relief_stack(doc, 'Gtw', node, n(cx), n(cy))
    tip = C._owned(doc, 'Part::Refine', 'GreebleToWebFillet')
    tip.Source = node
    return tip


def octant(seed, clamped):
    """The finished octant, built with the clamp's fillet or with the port's."""
    doc = App.newDocument('clamped' if clamped else 'omitted')
    was = fillets.greeble_to_web_fillet
    if clamped:
        fillets.greeble_to_web_fillet = clamped_body
    try:
        bulkhead_section.emit(doc, seed)
        doc.recompute()
    finally:
        fillets.greeble_to_web_fillet = was
    section = doc.getObject('BulkheadSection')
    body = doc.getObject('GreebleToWebFillet')
    return doc, section.Shape.Volume, (body.Shape.Volume if body is not None else 0.0)


def main():
    args = script_args()
    if not args:
        print('usage: freecadcmd measure_clamped_gtw.py --pass params.json [out.json]')
        return 0
    seed = parameters.seed(args[0])

    doc, without, built = octant(seed, clamped=False)
    cells = doc.getObject('Params')
    inner, bolt = float(cells.get('flange_inner_x')), float(cells.get('bolt_c'))
    App.closeDocument(doc.Name)

    doc, with_, own = octant(seed, clamped=True)
    App.closeDocument(doc.Name)

    net = with_ - without
    print('flange face %.4f, bolt center %.4f -> the corner %s'
          % (inner, bolt, 'exists' if inner >= bolt else 'does NOT exist'))
    print('the port builds %s'
          % ('the fillet, %.5f mm3' % built if built else 'no fillet here'))
    print('the clamped body is %10.5f mm3' % own)
    print('octant with it %.7f, without it %.7f -> the flown part loses %.5f mm3 (%.5f%%)'
          % (with_, without, net, 100 * net / with_ if with_ else 0.0))

    if len(args) > 1:
        with open(args[1], 'w', newline='\n') as f:
            json.dump({'flange_inner_x': inner, 'bolt_c': bolt, 'corner': inner >= bolt,
                       'built': built, 'own': own, 'net': net,
                       'octant': without, 'octant_clamped': with_}, f, indent=1)
        print('wrote %s' % args[1])
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
