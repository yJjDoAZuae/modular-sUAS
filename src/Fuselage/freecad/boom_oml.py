"""IP-FC-12: bulkhead_oml_shape in 2D -- the outline the boom bulkhead is cut from.

Shared with the frame bulkhead, which reaches it as a 3D octant through `bulkhead_cuts.py`.
The boom bulkhead is a flat profile, so it needs the same shape in the plane, built the same
way the source builds it: one octant drawn in a corner-local frame, moved out to its corner,
then tiled by three nested mirror-unions into the full outline.

    octant_tiled(uw, cr) = mirror_x { mirror_y { mirror_xy { corner_translate { octant } } } }

`mirror_xy` reflects across `y = x`, which is `Part::Mirroring` with a normal of (1, -1, 0) --
the one of the three that is not an axis plane.

The octant itself is an L of two rectangles plus the corner disc, less the panel notch and the
diagonal mask that trims it to its wedge, less the longeron bore and the bolt hole.

Derived parameters for U=1.0 boom offset_single 3 mm.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
import plane2d
from corner_common import build_sheet, is_entry_point

V = App.Vector
P = 'Params.'

REF_AREA = 8856.3094939                      # ref_boom_bulkhead.scad mode 8
EXPECT_BBOX = (-50.0, -50.0, 50.0, 50.0)

PARAMS = [
    ('unit_width', '100.0'),
    ('corner_radius', '10.0'),
    ('panel_thickness', '3.0'),
    ('panel_offset', '1.5'),
    ('panel_overlap', '4.0'),
    ('panel_tolerance', '0.1'),
    ('longeron_radius', '2.0'),
    ('longeron_tolerance', '0.05'),
    ('bolt_hole_radius', '2.0'),
    ('bolt_offset', '8.0'),

    # The diagonal mask's overlap past the mirror line, zero here and `eps` in the OpenSCAD
    # source. Same row, same reason as `bulkhead_cuts.mask_eps` -- CGAL wants neighbouring
    # octants to interpenetrate before it unions them, OCCT is harmed by it (IP-FC-49). Kept
    # named rather than dropped so a reader can see the source says `+ eps` on purpose.
    #
    # It cannot move the answer either way: the overhang each octant makes past the mirror
    # line lies inside its own mirror image, so the tiled union covers the same region at
    # 0 as at 0.01. That is why mode 8 matched before this row existed.
    ('mask_eps', '0.0'),

    ('oml_arm', '=unit_width / 2 - corner_radius'),
    # the panel notch, in the octant's corner-local frame
    ('notch_x', '=-(oml_arm + panel_tolerance)'),
    ('notch_y', '=corner_radius - panel_thickness - panel_tolerance'),
    ('notch_w', '=oml_arm - panel_offset + panel_tolerance'),
    # the diagonal mask's far corner
    ('mask_near', '=corner_radius + mask_eps'),
    ('mask_far', '=-(unit_width / 2 + corner_radius)'),
    ('lon_r', '=longeron_radius + longeron_tolerance'),

    ('oml_reach', '=2 * (unit_width / 2 + corner_radius)'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def _union(doc, name, pieces):
    return plane2d.union(doc, name, pieces, P + 'oml_reach')


def mask(doc):
    """The half-plane triangle that trims the octant to its wedge."""
    pts = [(10.0, 10.0), (10.0, -60.0), (-60.0, -60.0)]
    dims = [(0, 'X', P + 'mask_near'), (0, 'Y', P + 'corner_radius'),
            (1, 'X', P + 'mask_near'), (1, 'Y', P + 'mask_far'),
            (2, 'X', P + 'mask_far + ' + P + 'mask_eps'), (2, 'Y', P + 'mask_far')]
    return plane2d.face(doc, 'Mask', C._sketch(doc, 'MaskWire', pts, (), (), (), dims, 0, '0'))


def octant(doc):
    """One eighth of the outline, drawn in the corner-local frame the source uses."""
    arm = P + 'oml_arm'
    outer = _union(doc, 'OmlOuter', [
        plane2d.rect(doc, 'OmlArmA', arm, arm, '-' + arm, '-' + arm),
        plane2d.rect(doc, 'OmlArmB', arm, P + 'corner_radius', '-' + arm, '0'),
        plane2d.disc(doc, 'OmlCorner', P + 'corner_radius'),
    ])
    trim = _union(doc, 'OmlTrim', [
        plane2d.rect(doc, 'OmlNotch', P + 'notch_w', P + 'notch_y',
                     P + 'notch_x', P + 'notch_y'),
        mask(doc),
    ])
    bores = _union(doc, 'OmlBores', [
        plane2d.disc(doc, 'OmlLongeron', P + 'lon_r'),
        plane2d.disc(doc, 'OmlBolt', P + 'bolt_hole_radius',
                     '-' + P + 'bolt_offset', '-' + P + 'bolt_offset'),
    ])
    return C._cut(doc, 'OmlOctant', C._cut(doc, 'OmlTrimmed', outer, trim), bores)


def _mirror(doc, name, base, normal):
    flip = C._owned(doc, 'Part::Mirroring', name + 'Flip')
    flip.Source = base
    flip.Normal = normal
    return _union(doc, name, [base, flip])


def oml_shape(doc):
    """Geometry only, against whatever sheet the document already has."""
    placed = C._owned(doc, 'Part::Refine', 'OmlPlaced')
    placed.Source = octant(doc)
    placed.setExpression('Placement.Base.x', P + 'oml_arm')
    placed.setExpression('Placement.Base.y', P + 'oml_arm')

    node = _mirror(doc, 'OmlDiag', placed, V(1, -1, 0))
    node = _mirror(doc, 'OmlAcrossY', node, V(0, 1, 0))
    return _mirror(doc, 'BulkheadOml', node, V(1, 0, 0))


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    tip = oml_shape(doc)
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('boom_oml')
    tip = emit(doc)
    print('PART:: 2D CSG tree -- bulkhead_oml_shape')
    print('  %-22s %13s %13s %11s  %s'
          % ('shape', 'FreeCAD', 'OpenSCAD', 'delta', 'checks'))
    ok = plane2d.report(doc, 'bulkhead_oml', tip.Shape, REF_AREA, 'oml_reach', EXPECT_BBOX)
    print('')
    print('  %s' % ('agrees' if ok else 'MISMATCH -- see checks above'))


if is_entry_point(__name__):
    main()
