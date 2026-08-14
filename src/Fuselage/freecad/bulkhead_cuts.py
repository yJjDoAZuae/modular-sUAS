"""IP-FC-9: the four geometric cut tools of bulkhead_section.

    opening_wedge     the mouth the longeron snaps in through
    outer_cleanup     tidies the outer faces of the corner cutout
    longeron_hole     bore plus fit tolerance
    bolt_hole
    octant_mask       keeps the lower diagonal half

The fifth cut, the greeble-forming `corner_end`, is a real module and is covered by
`bulkhead_tree.py`.

Like `flange_boss.py` this is checked against a transcription -- `bulkhead_section` builds
these inline, so `ref_bulkhead_cuts.scad` has to copy them and on its own proves only that
the port matches the copy. The binding check is the assembled `bulkhead_section`.

Two things worth recording:

**The octant mask is the `x > y` half-plane again**, shifted by `mask_eps`. Its three
vertices look arbitrary until the deltas come out equal -- 2*corner_radius + unit_width/2 on
both axes -- so the hypotenuse is the line `y = x - mask_eps`. That makes it a box minus the
same half-plane every other profile in this port has needed. `mask_eps` is 0 here and `eps`
in the OpenSCAD source; see its row for why.

**The opening wedge is the one shape with genuinely arbitrary angles.** Its two edges run at
45 +/- greeble_opening_angle from the origin and it closes on a chord. It is still not a
sketch: being convex it is a box clipped by three half-planes, and the half-planes take
their rotation from expressions the way `fillets.py` does. So the whole bulkhead ports with
no sketches at all -- see the migration note.

Derived parameters for U=1.0 end_bolt 3/16in, is_cowling = false, is_interconnect = false.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import corner_tree as C
from corner_common import build_sheet, is_entry_point

# The cut tool, at mask_eps = 0. **This is deliberately not the OpenSCAD number.** OpenSCAD's
# is 49812.1210938 with the bounding box starting at x = -59.99; the 0.01 mm is the mask
# overlap it needs and OCCT does not (IP-FC-49), so the tool here is that sliver smaller and
# starts at a round -60.0. The difference is confined to this intermediate: the finished part
# is unchanged and still agrees with OpenSCAD -- see bulkhead_full.
#
# Regenerated 2026-08-14 for OQ-DES-B13, which took the eps out of `clean_r`. The mask-overlap
# sliver is unchanged at 1.7951847; both backends moved by the same amount, -1.4697 in OpenSCAD
# against -1.4685 here.
REF = 49810.3259091
EXPECT_BBOX = (-60.0, -60.0, -9.0, 20.0, 20.0, 9.0)

PARAMS = [
    ('unit_width', '100.0'),
    ('bulkhead_thickness', '6'),
    ('corner_radius', '10.0'),
    ('panel_thickness', '4.7625'),
    ('panel_offset', '2.5'),
    ('panel_overlap', '4.7625'),
    ('panel_tolerance', '0.1'),
    ('longeron_radius', '2.0'),
    ('longeron_tolerance', '0.05'),
    ('bolt_hole_radius', '2.0'),
    ('bolt_offset', '8.0'),
    ('greeble_opening_angle', '35'),
    ('eps', '0.01'),

    # The octant mask's overlap, separate from `eps` and zero, because OCCT does not want
    # it. In OpenSCAD the mask is grown by eps so adjacent octants interpenetrate and the
    # union resolves reliably; CGAL is exact, but a union of two solids meeting on an exact
    # shared plane is the case that wanted help. OCCT does not need the help and is actively
    # harmed by it -- a 0.01 mm sliver is 4e-5 of a 250 mm part, below what its booleans
    # resolve, so the tiling fuse went invalid at U >= 2.5 (IP-FC-49). Measured directly:
    # a solid fused with its own mirror about the touching plane is valid and exact at 10,
    # 100, 250 and 400 mm with no overlap at all.
    #
    # Kept as a named row rather than deleted, because the *reason* is the whole point: this
    # is a kernel-specific workaround, and a reader who finds a bare `mask_lo` here would
    # have no way to know the OpenSCAD source says `mask_lo + eps` on purpose.
    ('mask_eps', '0.0'),

    # through_cut(extent) = 3 * extent, centred; mask_reach(extent) = 2 * extent
    ('through_h', '=3 * bulkhead_thickness'),
    ('through_z', '=-through_h / 2'),
    ('mask_reach', '=2 * corner_radius'),
    ('far', '=unit_width'),
    ('span', '=far * 2'),
    ('mask_span', '=far * 4'),

    # opening wedge: edges at 45 +/- the half-angle, closing on a chord at corner_radius
    ('wedge_lo', '=45 - greeble_opening_angle'),
    ('wedge_hi', '=45 + greeble_opening_angle'),
    ('wedge_lo_back', '=wedge_lo + 180'),
    ('wedge_lox', '=far * cos(wedge_lo)'),
    ('wedge_loy', '=far * sin(wedge_lo)'),
    ('wedge_hix', '=-far * cos(wedge_hi)'),
    ('wedge_hiy', '=-far * sin(wedge_hi)'),
    ('wedge_chord', '=corner_radius * cos(greeble_opening_angle)'),
    ('wedge_cx', '=(wedge_chord - far) / sqrt(2)'),
    ('wedge_cy', '=(wedge_chord + far) / sqrt(2)'),

    # Outer-face cleanup: two boxes clipped to y >= x, then the inner bore removed.
    #
    # **`clean_r`'s eps is load bearing, and a single-variant measurement said the opposite.**
    # It is the odd one of the port's eps sites -- not union slop and not a cut overshoot, but
    # 0.01 mm off a real bore radius, and stated that way by the source. Measured at U=1 with
    # a 3/16 in panel it changed the part by nothing at all, to seven decimals. Measured
    # across the 132 bulkhead variants that build it changes 27 of them, by 0.0017 to
    # 0.048 mm3 -- and the ones it touches are exactly where 0.01 mm is a large fraction of a
    # small corner radius: U = 0.5 to 1.5 with the thin panels, 1 mm, 3 mm, 1/32 in, 1/16 in.
    #
    # The way it nearly did not get measured is worth keeping (IP-FC-55): slop can be audited
    # at one variant, because being locally irrelevant is its whole job, but a *dimension*
    # cannot -- one variant not using it says nothing about the rest.
    #
    # **`clean_r` carried an eps until OQ-DES-B13 (2026-08-14); it does not now.** The row is
    # the radius the flange's outer surface ends up at -- flush behind the panel -- so it is a
    # material face, not a cut overshoot, and the eps cut it 0.01 mm too deep.
    #
    # It read as load bearing because deleting it alone changed 27 of the 132 buildable
    # variants by 0.0017 to 0.048 mm3. That was the tell, not the justification: the only
    # material within reach of the overcut was the bulkhead's own overhang over the corner,
    # which the corner's rectangular extension used to create by stopping one `panel_tolerance`
    # short of `flat_x`. With `rect_w` reaching `flat_x` (corner_tree.py) the overhang is gone
    # and this eps removes nothing measurable -- verified on six variants, volume identical
    # with and without.
    #
    # `clean_x0` is NOT toleranced and must not become so. `flat_x` is the corner/bulkhead
    # interface itself, cut into both parts by the same polygon, so the cleanup already stops
    # exactly at the joint. In particular do not reintroduce a `sqrt` here: an earlier reading
    # had `clean_x0` follow the outer mold line's crossing with the flange face, which predicts
    # the material loss on all 132 -- but it describes where the overhang ended, not where the
    # joint is. IP-FC-59.
    ('clean_x0', '=-(panel_offset + panel_overlap)'),
    ('clean_r', '=corner_radius - (panel_thickness + panel_tolerance)'),

    # octant mask: hypotenuse is y = x - mask_eps, legs 2*corner_radius + unit_width/2
    ('mask_lo', '=-unit_width / 2 - corner_radius'),
    ('mask_leg', '=corner_radius - mask_lo'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def _through_box(doc, name, length, width, x, y, angle=None):
    """A cut tool spanning the full through_cut height, like every negative here."""
    P = 'Params.'
    return C._box(doc, name, length, width, P + 'through_h', x, y, P + 'through_z',
                  angle=angle)


def _halfplane(doc, name, x, y, angle_expr=None, angle=None, size=None):
    """The material on the local +y side of a line through (x, y). When `angle_expr` is
    given the rotation is bound to the sheet, for edges whose angle moves with the
    parameters."""
    P = 'Params.'
    size = size or P + 'span'
    box = _through_box(doc, name, size, size, x, y, angle=90 if angle is None else angle)
    if angle_expr is not None:
        box.setExpression('Placement.Rotation.Angle', angle_expr)
    return box


def _at(obj, x_expr, y_expr):
    obj.setExpression('Placement.Base.x', x_expr)
    obj.setExpression('Placement.Base.y', y_expr)
    return obj


def opening_wedge(doc):
    """Convex, so a covering box clipped by its three edges. The two radial edges are
    clipped by half-planes whose rotation is an expression; the chord's is a fixed -45
    because it is always normal to the diagonal, whatever the opening angle."""
    P = 'Params.'
    node = _through_box(doc, 'WedgeBlock', P + 'corner_radius', P + 'corner_radius',
                        '0', '0')
    node = C._cut(doc, 'WedgeCutLo', node,
                  _halfplane(doc, 'WedgeLoBox', P + 'wedge_lox', P + 'wedge_loy',
                             angle_expr=P + 'wedge_lo_back'))
    node = C._cut(doc, 'WedgeCutHi', node,
                  _halfplane(doc, 'WedgeHiBox', P + 'wedge_hix', P + 'wedge_hiy',
                             angle_expr=P + 'wedge_hi'))
    return C._cut(doc, 'OpeningWedge', node,
                  _halfplane(doc, 'WedgeChordBox', P + 'wedge_cx', P + 'wedge_cy',
                             angle=-45))


def outer_cleanup(doc):
    P = 'Params.'
    both = C._fuse(
        doc, 'CleanBoth',
        _through_box(doc, 'CleanUpper', P + 'mask_reach - ' + P + 'clean_x0',
                     P + 'mask_reach - ' + P + 'clean_r', P + 'clean_x0', P + 'clean_r'),
        _through_box(doc, 'CleanRight', P + 'mask_reach', P + 'mask_reach', '0', '0'))
    # keep y >= x: the same half-plane the flange base, the web and the corner all use
    node = C._cut(doc, 'CleanDiag', both,
                  _halfplane(doc, 'CleanDiagBox', '-' + P + 'far', '-' + P + 'far',
                             angle=-45))
    return C._cut(doc, 'OuterCleanup', node,
                  C._cyl(doc, 'CleanBore', P + 'clean_r', P + 'through_h',
                         P + 'through_z'))


def octant_mask(doc):
    """The eighth of the bulkhead that gets mirrored seven times.

    Both shifts are `mask_eps`, which is 0 here and `eps` in the OpenSCAD source -- see the
    row for why the kernels want opposite things. At `mask_eps = 0` the octant stops one
    plane short of overlapping its neighbour and meets it exactly instead, which is also
    what makes the tiled part exactly eight times the octant rather than slightly less.
    """
    P = 'Params.'
    block = _through_box(doc, 'MaskBlock', P + 'mask_leg', P + 'mask_leg',
                         P + 'mask_lo + ' + P + 'mask_eps', P + 'mask_lo')
    # keep y <= x - mask_eps, so the complement is clipped away rather than the usual side
    return C._cut(doc, 'OctantMask', block,
                  _halfplane(doc, 'MaskDiagBox', P + 'far + ' + P + 'mask_eps', P + 'far',
                             angle=135, size=P + 'mask_span'))


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    return cuts(doc)


def cuts(doc):
    """Geometry only, against whatever sheet the document already has."""
    P = 'Params.'

    tools = [
        opening_wedge(doc),
        outer_cleanup(doc),
        C._cyl(doc, 'LongeronHole', P + 'longeron_radius + ' + P + 'longeron_tolerance',
               P + 'through_h', P + 'through_z'),
        _at(C._cyl(doc, 'BoltHole', P + 'bolt_hole_radius', P + 'through_h',
                   P + 'through_z'), '-' + P + 'bolt_offset', '-' + P + 'bolt_offset'),
        octant_mask(doc),
    ]

    node = tools[0]
    for i, tool in enumerate(tools[1:], start=1):
        node = C._fuse(doc, 'CutFuse%d' % i, node, tool)

    tip = C._owned(doc, 'Part::Refine', 'BulkheadCuts')
    tip.Source = node
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('bulkhead_cuts')
    tip = emit(doc)
    s = tip.Shape
    d = s.Volume - REF

    print('PART:: CSG tree -- bulkhead_section cut tools')
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, transcribed)' % REF)
    print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * d / REF))
    bb = s.BoundBox
    got = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
    print('  bbox    = [%s]' % ', '.join('%.4f' % v for v in got))
    print('  expect  = [%s]' % ', '.join('%.4f' % v for v in EXPECT_BBOX))
    print('  valid   = %s  solids=%d  faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    fail = []
    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids -- the tools should overlap into one' % len(s.Solids))
    if abs(d) / REF > 1e-3:
        fail.append('volume off by more than 0.1%')
    if max(abs(a - b) for a, b in zip(got, EXPECT_BBOX)) > 1e-2:
        fail.append('bounding box moved')
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
