"""IP-FC-9: the bulkhead's greeble post, formed from the corner's end section.

The greeble is a POSITIVE post on the bulkhead, formed by subtracting the corner's end
section: bulkhead material is left exactly where the corner has none, so one description
gives both mating halves.

The subtlety this file exists to get right is *which* end section. bulkhead_section() calls
corner_end() with two arguments that differ from the corner's own:

  * greeble_tolerance is a literal 0. The post is nominal by construction and all of the
    fit clearance is taken on the corner's bore (GREEBLE_TOLERANCE_CORNER_MM), because
    split across both halves the joint would carry it twice. That is an invariant of the
    design, not a setting.
  * overshoot is eps, so the tool passes cleanly through the material it forms instead of
    ending flush with it. It moves the body and the greeble bore and sizes nothing.

**That second bullet used to read very differently, and the difference was OQ-DES-B12**
(decided and fixed 2026-08-11, IP-FC-51). The overshoot was bought by calling `corner_end`
with `bulkhead_thickness + 2*eps` and shifting the result down by eps -- but `corner_end`
also derives `greeble_nub_height = bt/3` and every nub z level from that argument, so the
socket's snap rib came out at 2.00667 mm against the post's 2.00000. The `-eps` shift nearly
cancelled the inflation, leaving the band centred and only its height wrong, which is why it
went unnoticed: about 0.0033 mm of gap at each end of a snap the design requires to be
nominal, and a second clearance on a joint whose whole rule is that clearance is carried once.

`corner_end` now takes an explicit `overshoot` argument. The z extent of this tool is exactly
what it was; only the rib and the nub z levels moved. REF_TOOL was regenerated against the
corrected authority, and `ref_end` -- the corner's own end section -- is bit-identical across
the change, which is what says the fix touched only the caller that was misusing the argument.

So "reuse the corner's end section" means re-evaluating the DESCRIPTION at different
arguments -- a second call to the same builder. It does not mean referencing the corner's
built shape, which is oversize on the bore by design; cutting the bulkhead with that would
apply the clearance a second time and leave the snap loose. This is why the natural
PartDesign idiom for cross-part reuse, a SubShapeBinder, is the wrong tool here: a binder
delivers the corner's actual shape.

Nothing about that is visible in the result. Cutting with the wrong one yields a valid
solid, one solid, and a plausible volume.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import is_entry_point

HERE = os.path.dirname(os.path.abspath(__file__))

# The greeble tool's parameters. Every one is derived from the shared set, so the post and
# the socket cannot drift apart -- which is the whole point of forming one from the other.
GREEBLE_TOOL_PARAMS = [
    ('gt_tolerance', '0.0'),                  # nominal by construction, see the docstring
    ('gt_bt', '=bulkhead_thickness'),         # the thickness, and nothing else -- OQ-DES-B12
    ('gt_overshoot', '=eps'),                 # slop for the boolean, and it sizes nothing
    ('gt_greeble_radius', '=longeron_radius + longeron_tolerance + greeble_thickness '
                          '+ gt_tolerance'),
    ('gt_greeble_nub_radius', '=gt_greeble_radius + greeble_nub_thickness'),
    ('gt_greeble_nub_height', '=gt_bt / 3'),
    ('gt_through_cut', '=gt_bt * 3'),

    # The overshoot reaches the body and the greeble bore, and stops there. Both extend past
    # both nominal faces, so the z extent is exactly what it was when the tool bought its
    # overshoot by inflating the thickness -- only the rib and the nub z levels move, which
    # is the whole point of the fix.
    ('gt_z0', '=-gt_overshoot'),
    ('gt_h', '=gt_bt + eps + gt_overshoot * 2'),
    ('gt_base_z', '=-gt_overshoot'),
    ('gt_nub_span', '=gt_bt + gt_overshoot * 2'),
    # centred on z = 0 and three thicknesses tall, so it clears everything by 1.5 * bt
    ('gt_cut_z0', '=-gt_through_cut / 2'),
    # dimensioned from gt_bt, never from the overshoot
    ('gt_nub_z1', '=gt_bt / 2 - gt_greeble_nub_height / 2 - greeble_nub_thickness'),
    ('gt_nub_z2', '=gt_bt / 2 - gt_greeble_nub_height / 2'),
    ('gt_nub_z3', '=gt_bt / 2 + gt_greeble_nub_height / 2'),
    ('gt_nub_z4', '=gt_bt / 2 + gt_greeble_nub_height / 2 + greeble_nub_thickness'),

    ('gt_mouth_w', '=gt_greeble_radius * 2'),
    ('gt_mouth_x', '=-gt_greeble_radius / sqrt(2)'),
    ('gt_mouth_y', '=-gt_greeble_radius * 3 / sqrt(2)'),
]

REF_TOOL = 557.8049247                        # regenerated 2026-08-11 for the B12 fix


def greeble_tool(doc):
    """corner_end re-evaluated at greeble tolerance 0 and bulkhead_thickness + 2*eps."""
    P = 'Params.'
    return C.end_section(doc, 'GT', 'gt_', P + 'gt_z0', P + 'gt_h', P + 'gt_base_z')


def emit(doc):
    C._SEEN.clear()
    C._sheet(doc, GREEBLE_TOOL_PARAMS)
    return greeble_tool(doc)


def main():
    doc = App.newDocument('bulkhead_tree')
    tool = emit(doc)
    doc.recompute()

    s = tool.Shape
    d = s.Volume - REF_TOOL
    sheet = doc.getObject('Params')

    print('IP-FC-9 -- the greeble-forming tool')
    print('  corner socket bore   = %s' % sheet.get('greeble_radius'))
    print('  post tool bore       = %s   (tolerance %s)'
          % (sheet.get('gt_greeble_radius'), sheet.get('gt_tolerance')))
    print('  corner rib height    = %s' % sheet.get('greeble_nub_height'))
    print('  post tool rib height = %s   (nominal since OQ-DES-B12)'
          % sheet.get('gt_greeble_nub_height'))
    print('')
    print('  volume  = %.6f' % s.Volume)
    print('  ref     = %.6f  (OpenSCAD, faceted)' % REF_TOOL)
    print('  delta   = %+.6f  (%+.4f%%)' % (d, 100 * d / REF_TOOL))
    bb = s.BoundBox
    print('  z range = [%.4f, %.4f]  (expect -0.0100, 6.0200)' % (bb.ZMin, bb.ZMax))
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    # The clearance must appear once, on the corner's bore, and never on the post. This was
    # asserted for the bore and merely printed for the rib, which is how OQ-DES-B12 survived
    # unnoticed -- the rib carried a second clearance of 0.00667 mm and nothing objected.
    # Both are checks now.
    corner_bore = float(sheet.get('greeble_radius'))
    post_bore = float(sheet.get('gt_greeble_radius'))
    tol = float(sheet.get('greeble_tolerance'))
    corner_rib = float(sheet.get('greeble_nub_height'))
    post_rib = float(sheet.get('gt_greeble_nub_height'))

    ok = abs((corner_bore - post_bore) - tol) < 1e-9
    print('  clearance carried once: corner bore - post bore = %.4f (= greeble_tolerance)  %s'
          % (corner_bore - post_bore, 'ok' if ok else 'MISMATCH'))
    rib_ok = abs(corner_rib - post_rib) < 1e-9
    print('  rib nominal on both halves: %.6f vs %.6f  %s'
          % (corner_rib, post_rib, 'ok' if rib_ok else 'MISMATCH -- OQ-DES-B12 has regressed'))
    if not (ok and rib_ok):
        sys.stderr.write('FAIL: the greeble joint does not carry its clearance once\n')
        sys.stderr.flush()
        raise SystemExit(1)


if is_entry_point(__name__):
    main()
