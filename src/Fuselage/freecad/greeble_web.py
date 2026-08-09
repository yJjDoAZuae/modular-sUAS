"""IP-FC-9: greeble_bolt_web -- the diagonal web from the greeble corner to the bolt boss.

Two pieces, and neither needs a sketch.

The plan-view polygon
`(0,0) (-d, d) (-d-bolt_offset, d-bolt_offset) (-bolt_offset, -bolt_offset)`, where
`d = flange_thickness / (2*sqrt(2))`, is a **parallelogram**: a strip of width
`flange_thickness/2` laid along the corner-to-bolt diagonal. So it is one box rotated -135
degrees, its length the diagonal `bolt_offset * sqrt(2)` and its width the half thickness.

The rib on top of it is the same pentagon as `bulkhead_flange_chamfer` with `flange_thickness`
halved -- a box minus the half-plane `x - y > plate_thickness + flange_chamfer +
flange_thickness/2` -- built in the source's own frame and then placed, since its extrusion
runs along the diagonal rather than an axis.

This is the module whose arguments were rotated until 2026-08-08; see OQ-DES-B10. The
parameters below are the corrected association at derived values for U=1.0 end_bolt 3/16in,
where `plate_thickness` 0.8 and `flange_thickness` 1.2 are distinct -- the hand driver makes
them both 0.8 and hides the difference.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import build_sheet, is_entry_point

V = App.Vector
REF_VOL = 55.4365498      # ref_greeble_web.scad
EXPECT_BBOX = (-9.1314, -8.0, 0.0, 0.0, 1.1314, 6.0)

PARAMS = [
    ('bulkhead_thickness', '6'),
    ('bolt_offset', '8.0'),
    ('plate_thickness', '0.8'),
    ('flange_thickness', '1.2'),
    ('flange_chamfer', '1.0'),
    ('unit_width', '100.0'),

    ('web_half', '=flange_thickness / 2'),
    ('web_d', '=flange_thickness / (2 * sqrt(2))'),
    ('web_diag', '=bolt_offset * sqrt(2)'),

    ('rib_top', '=plate_thickness + flange_chamfer'),
    ('rib_deep', '=web_half + flange_chamfer'),
    ('rib_cut', '=rib_top + web_half'),

    ('far', '=unit_width'),
    ('diag_len', '=far * 2'),
    ('diag_wid', '=far * 2 * sqrt(2)'),
    # half-plane x - y > rib_cut, as a box rotated -45
    ('rib_dx', '=(rib_cut - far * 2) / 2'),
    ('rib_dy', '=(-rib_cut - far * 2) / 2'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def greeble_bolt_web(doc):
    """Geometry only, against whatever sheet the document already has -- the assembly in
    bulkhead_positive.py supplies one merged sheet for every constituent."""
    P = 'Params.'
    # the parallelogram strip, as one rotated box
    strip = C._box(doc, 'WebStrip', P + 'web_diag', P + 'web_half',
                   P + 'bulkhead_thickness',
                   '-' + P + 'web_d', P + 'web_d', '0', angle=-135)

    # the rib: pentagon prism in the source's frame, then rotated onto the diagonal
    rib_box = C._box(doc, 'RibBox', P + 'rib_top', P + 'rib_deep', P + 'web_diag',
                     '0', '-' + P + 'rib_deep', '0')
    rib = C._cut(doc, 'RibCut', rib_box,
                 C._box(doc, 'RibDiag', P + 'diag_len', P + 'diag_wid',
                        P + 'web_diag * 3', P + 'rib_dx', P + 'rib_dy',
                        '-' + P + 'web_diag', angle=-45))
    rib.Placement = App.Placement(
        V(0, 0, 0), App.Rotation(V(0, 0, 1), -135).multiply(
            App.Rotation(V(0, 1, 0), -90)))
    rib.setExpression('Placement.Base.x', '-' + P + 'bolt_offset')
    rib.setExpression('Placement.Base.y', '-' + P + 'bolt_offset')

    node = C._fuse(doc, 'GreebleBoltWeb', strip, rib)
    tip = C._owned(doc, 'Part::Refine', 'GreebleBoltWebTip')
    tip.Source = node
    return tip


def emit(doc):
    C._SEEN.clear()
    sheet(doc)
    tip = greeble_bolt_web(doc)
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('greeble_web')
    tip = emit(doc)
    s = tip.Shape
    bb = s.BoundBox
    got = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
    d = s.Volume - REF_VOL

    print('PART:: CSG tree -- greeble_bolt_web')
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, ref_greeble_web.scad)' % REF_VOL)
    print('  delta   = %+.7f  (%+.4f%%)' % (d, 100 * d / REF_VOL))
    print('  bbox    = [%s]' % ', '.join('%.4f' % v for v in got))
    print('  expect  = [%s]' % ', '.join('%.4f' % v for v in EXPECT_BBOX))
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    fail = []
    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids' % len(s.Solids))
    if abs(d) / REF_VOL > 1e-3:
        fail.append('volume off by more than 0.1%')
    if max(abs(a - b) for a, b in zip(got, EXPECT_BBOX)) > 1e-3:
        fail.append('bounding box moved')
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
