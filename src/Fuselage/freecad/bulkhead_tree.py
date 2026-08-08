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
  * bulkhead_thickness is bt + 2*eps, so the rib height (bt/3) and every nub z level are
    computed from 6.02 rather than 6.00.

The whole shape is then shifted down by eps to clean up the bottom of the cutout.

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
    ('gt_bt', '=bulkhead_thickness + eps * 2'),
    ('gt_greeble_radius', '=longeron_radius + longeron_tolerance + greeble_thickness '
                          '+ gt_tolerance'),
    ('gt_greeble_nub_radius', '=gt_greeble_radius + greeble_nub_thickness'),
    ('gt_greeble_nub_height', '=gt_bt / 3'),
    ('gt_nub_span', '=gt_bt'),
    ('gt_through_cut', '=gt_bt * 3'),

    # the whole tool is shifted down by eps, so every z carries -eps
    ('gt_z0', '=-eps'),
    ('gt_h', '=gt_bt + eps'),
    ('gt_base_z', '=-eps'),
    ('gt_cut_z0', '=-gt_through_cut / 2 - eps'),
    ('gt_nub_z1', '=gt_bt / 2 - gt_greeble_nub_height / 2 - greeble_nub_thickness - eps'),
    ('gt_nub_z2', '=gt_bt / 2 - gt_greeble_nub_height / 2 - eps'),
    ('gt_nub_z3', '=gt_bt / 2 + gt_greeble_nub_height / 2 - eps'),
    ('gt_nub_z4', '=gt_bt / 2 + gt_greeble_nub_height / 2 + greeble_nub_thickness - eps'),

    ('gt_mouth_w', '=gt_greeble_radius * 2'),
    ('gt_mouth_x', '=-gt_greeble_radius / sqrt(2)'),
    ('gt_mouth_y', '=-gt_greeble_radius * 3 / sqrt(2)'),
]

REF_TOOL = 557.7463621


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
    print('  post tool rib height = %s   (from bt + 2*eps)'
          % sheet.get('gt_greeble_nub_height'))
    print('')
    print('  volume  = %.6f' % s.Volume)
    print('  ref     = %.6f  (OpenSCAD, faceted)' % REF_TOOL)
    print('  delta   = %+.6f  (%+.4f%%)' % (d, 100 * d / REF_TOOL))
    bb = s.BoundBox
    print('  z range = [%.4f, %.4f]  (expect -0.0100, 6.0200)' % (bb.ZMin, bb.ZMax))
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    # the clearance must appear once, on the corner, and never on the post
    corner_bore = float(sheet.get('greeble_radius'))
    post_bore = float(sheet.get('gt_greeble_radius'))
    print('  clearance carried once: corner bore - post bore = %.4f (= greeble_tolerance)'
          % (corner_bore - post_bore))


if is_entry_point(__name__):
    main()
