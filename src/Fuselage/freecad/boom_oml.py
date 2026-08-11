"""IP-FC-12: the bulkhead outline in 2D -- the three region-wide shapes the boom part cuts from.

Shared with the frame bulkhead, which reaches them as 3D octants through `bulkhead_cuts.py`.
The boom bulkhead is a flat profile, so it needs the same shapes in the plane, built the same
way the source builds them: one octant drawn in a corner-local frame, moved out to its corner,
then tiled by three nested mirror-unions into the full outline.

    octant_tiled(uw, cr) = mirror_x { mirror_y { mirror_xy { corner_translate { octant } } } }

`mirror_xy` reflects across `y = x`, which is `Part::Mirroring` with a normal of (1, -1, 0) --
the one of the three that is not an axis plane.

Three shapes come out of the same octant, and all three have call sites:

    oml_outer_shape   the material before the bores -- an L of two rectangles plus the corner
                      disc, less the panel notch and the diagonal mask that trims it to its
                      wedge. `bulkhead_web.py` intersects against it.
    oml_inner_shape   the bores alone: the longeron bore at the corner centre and the bolt
                      hole inboard of it. The assembly subtracts it.
    oml_shape         outer less bores, which is what the erosions start from.

They are built as three independent trees rather than one tree with taps, because each is a
`Part::Cut`/mirror chain whose nodes belong to one result. Sharing the octant across them
would make the outline's node graph a lattice, and the port's rule is that a reader can follow
any shape from its tip to the sheet without leaving that shape.

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

# ref_boom_bulkhead.scad modes 12, 11 and 8, as (area, bbox, tolerance).
#
# The bores need their own tolerance and it is the reason this table carries one at all. The
# usual 6.0e-5 floor is what `$fa = 1` costs when a circle is capped at 360 segments; these
# circles are small enough that `$fs = 0.1` caps them near 128 instead, which is a 4.0e-4
# area deficit against a true circle. In `oml_shape` those same bores are 1% of the area and
# the deficit disappears into 3e-6, so the floor only becomes visible when the bores are
# measured alone. It is faceting, not disagreement -- FreeCAD's circles are exact.
REFS = {
    'oml_outer': (8959.3433819, (-50.0, -50.0, 50.0, 50.0), 6.0e-5),
    'oml_inner': (103.0474738, (-42.05, -42.05, 42.05, 42.05), 4.0e-4),
    'oml': (8856.3094939, (-50.0, -50.0, 50.0, 50.0), 6.0e-5),
}

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


def mask(doc, tag):
    """The half-plane triangle that trims the octant to its wedge."""
    pts = [(10.0, 10.0), (10.0, -60.0), (-60.0, -60.0)]
    dims = [(0, 'X', P + 'mask_near'), (0, 'Y', P + 'corner_radius'),
            (1, 'X', P + 'mask_near'), (1, 'Y', P + 'mask_far'),
            (2, 'X', P + 'mask_far + ' + P + 'mask_eps'), (2, 'Y', P + 'mask_far')]
    return plane2d.face(doc, tag + 'Mask',
                        C._sketch(doc, tag + 'MaskWire', pts, (), (), (), dims, 0, '0'))


def outer_octant(doc, tag):
    """One eighth of the material, drawn in the corner-local frame the source uses."""
    arm = P + 'oml_arm'
    outer = _union(doc, tag + 'OmlOuter', [
        plane2d.rect(doc, tag + 'OmlArmA', arm, arm, '-' + arm, '-' + arm),
        plane2d.rect(doc, tag + 'OmlArmB', arm, P + 'corner_radius', '-' + arm, '0'),
        plane2d.disc(doc, tag + 'OmlCorner', P + 'corner_radius'),
    ])
    trim = _union(doc, tag + 'OmlTrim', [
        plane2d.rect(doc, tag + 'OmlNotch', P + 'notch_w', P + 'notch_y',
                     P + 'notch_x', P + 'notch_y'),
        mask(doc, tag),
    ])
    return C._cut(doc, tag + 'OmlTrimmed', outer, trim)


def bores_octant(doc, tag):
    """One eighth of the bores: the longeron at the corner centre, the bolt hole inboard."""
    return _union(doc, tag + 'OmlBores', [
        plane2d.disc(doc, tag + 'OmlLongeron', P + 'lon_r'),
        plane2d.disc(doc, tag + 'OmlBolt', P + 'bolt_hole_radius',
                     '-' + P + 'bolt_offset', '-' + P + 'bolt_offset'),
    ])


def _mirror(doc, name, base, normal):
    flip = C._owned(doc, 'Part::Mirroring', name + 'Flip')
    flip.Source = base
    flip.Normal = normal
    return _union(doc, name, [base, flip])


def tiled(doc, tag, name, octant):
    """`octant_tiled`: out to the corner, then the three mirror-unions."""
    placed = C._owned(doc, 'Part::Refine', tag + 'OmlPlaced')
    placed.Source = octant
    placed.setExpression('Placement.Base.x', P + 'oml_arm')
    placed.setExpression('Placement.Base.y', P + 'oml_arm')

    node = _mirror(doc, tag + 'OmlDiag', placed, V(1, -1, 0))
    node = _mirror(doc, tag + 'OmlAcrossY', node, V(0, 1, 0))
    return _mirror(doc, name, node, V(1, 0, 0))


def oml_outer_shape(doc, tag='Outer'):
    """`bulkhead_oml_outer_shape` -- the outline before the bores."""
    return tiled(doc, tag, tag + 'BulkheadOml', outer_octant(doc, tag))


def oml_inner_shape(doc, tag='Inner'):
    """`bulkhead_oml_inner_shape` -- the four longeron bores and four bolt holes."""
    return tiled(doc, tag, tag + 'BulkheadOml', bores_octant(doc, tag))


def oml_shape(doc, tag=''):
    """`bulkhead_oml_shape` -- geometry only, against whatever sheet the document has."""
    octant = C._cut(doc, tag + 'OmlOctant',
                    outer_octant(doc, tag), bores_octant(doc, tag))
    return tiled(doc, tag, tag + 'BulkheadOml', octant)


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    tips = [('oml_outer', oml_outer_shape(doc)),
            ('oml_inner', oml_inner_shape(doc)),
            ('oml', oml_shape(doc))]
    doc.recompute()
    return tips


def main():
    doc = App.newDocument('boom_oml')
    tips = emit(doc)
    print('PART:: 2D CSG tree -- the bulkhead outline')
    print('  %-22s %13s %13s %11s  %s'
          % ('shape', 'FreeCAD', 'OpenSCAD', 'delta', 'checks'))
    ok = True
    for label, tip in tips:
        ref, bbox, tol = REFS[label]
        ok &= plane2d.report(doc, label, tip.Shape, ref, 'oml_reach', bbox, tol)
    print('')
    print('  %s' % ('agrees' if ok else 'MISMATCH -- see checks above'))


if is_entry_point(__name__):
    main()
