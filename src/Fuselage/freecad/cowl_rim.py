"""IP-FC-132: the three `is_cowling` positives that `simple_positives.py` does not cover.

`bulkhead_section`'s `if (is_cowling)` block builds six things (see the module docstring in
`simple_positives.py` for the finding that they are gated at all). Three are plain primitives
and are ported there already -- the plate, the longeron flange, and its chamfer. The other
three all clip a shape to the same quadrant wedge, `[[0,0], [0, corner_radius],
[corner_radius, corner_radius]]` -- the region `0 <= x <= corner_radius, x <= y <=
corner_radius` -- which is a box cut by the same `y >= x` half-plane every other profile in
this port has needed:

    rim_ring     an annulus at the corner rim, full bulkhead_thickness tall, from
                 corner_radius down to corner_radius - flange_thickness
    rim_disk     a shallow full-radius disk, plate_thickness tall -- together with rim_ring
                 this is a stepped profile, thin in the middle and full height at the rim
    flange_band  the cowl's own mating flange: a flat lip on the straight side plus an
                 annular arc on the curved side, at z = bulkhead_thickness, one
                 cowl_flange_height tall

The wedge is built once, tall enough to cover all three z-ranges (0 to bulkhead_thickness +
cowl_flange_height), and shared as the `Tool` of three `Part::Common` nodes -- the same
economy `bulkhead_cuts.py`'s named tools take, and the reason it is a function taking the
wedge rather than three private copies of it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corner_tree as C
from corner_common import build_sheet

PARAMS = [
    # Structural zeros on every non-cowling bulkhead (IP-FC-42): a plain end or interconnect
    # type carries these on its sheet at 0.0 / 0.0 / 1.0 and never builds this module's
    # geometry at all, since `bulkhead_section.emit()` gates the whole group on `is_cowling`.
    ('cowl_flange_height', '2.0'),
    ('cowl_flange_tolerance', '0.2'),
    ('cowl_n_perimeters', '1.0'),

    ('cowl_wedge_h', '=bulkhead_thickness + cowl_flange_height'),
    ('cowl_band_outer', '=corner_radius - cowl_n_perimeters * extrusion_width '
                        '- cowl_flange_tolerance'),
    ('cowl_band_inner', '=corner_radius - flange_thickness'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def _common(doc, name, base, tool):
    node = C._owned(doc, 'Part::Common', name)
    node.Base, node.Tool = base, tool
    return node


def _wedge_mask(doc):
    """Quadrant `[0, corner_radius] x [0, corner_radius]`, cut by the same `y >= x`
    half-plane `flange_base.FlangeDiag` and `bulkhead_cuts`'s cut tools use -- a box rotated
    -45 about z, whose `Placement.Base` is the corner AFTER rotation (see flange_base.py).
    Tall enough at both ends to clip every feature this module builds."""
    P = 'Params.'
    square = C._box(doc, 'CowlWedgeSquare', P + 'corner_radius', P + 'corner_radius',
                    P + 'cowl_wedge_h', '0', '0', '0')
    diag = C._box(doc, 'CowlWedgeDiag', P + 'far * 2', P + 'far * 2 * sqrt(2)',
                 '3 * ' + P + 'cowl_wedge_h', '-' + P + 'far', '-' + P + 'far',
                 '-' + P + 'cowl_wedge_h', angle=-45)
    return C._cut(doc, 'CowlWedgeMask', square, diag)


def rim_ring(doc, wedge):
    """The outer wall of the cowl seat: an annulus at the corner radius, full
    bulkhead_thickness tall, kept only in the wedge -- bulkhead_section's first `if
    (is_cowling)` intersection."""
    P = 'Params.'
    outer = C._cyl(doc, 'CowlRimOuter', P + 'corner_radius', P + 'bulkhead_thickness', '0')
    inner = C._cyl(doc, 'CowlRimInner', P + 'corner_radius - ' + P + 'flange_thickness',
                   P + 'bulkhead_thickness', '0')
    ring = C._cut(doc, 'CowlRimAnnulus', outer, inner)
    return _common(doc, 'CowlRim', ring, wedge)


def rim_disk(doc, wedge):
    """A shallow full-radius disk, plate_thickness tall, kept only in the wedge -- the
    second intersection. Together with `rim_ring` this is a stepped profile: thin across
    the middle, full height only at the rim."""
    P = 'Params.'
    disk = C._cyl(doc, 'CowlDisk', P + 'corner_radius', P + 'plate_thickness', '0')
    return _common(doc, 'CowlDiskWedge', disk, wedge)


def flange_band(doc, wedge):
    """The cowl's own mating flange, at z = bulkhead_thickness: a flat lip on the straight
    side (the polygon in the source) fused with an annular arc on the curved side (the
    `intersection()` in the source), the same flat-plus-curved pattern
    `bulkhead_flange_positive` itself uses for its strip and its boss."""
    P = 'Params.'
    outer_r = P + 'cowl_band_outer'
    inner_r = P + 'cowl_band_inner'

    lip = C._box(doc, 'CowlBandLip',
                '-' + P + 'flange_end_x', outer_r + ' - (' + inner_r + ')',
                P + 'cowl_flange_height', P + 'flange_end_x', inner_r,
                P + 'bulkhead_thickness')

    outer = C._cyl(doc, 'CowlBandOuter', outer_r, P + 'cowl_flange_height',
                   P + 'bulkhead_thickness')
    inner = C._cyl(doc, 'CowlBandInner', inner_r, P + 'cowl_flange_height',
                   P + 'bulkhead_thickness')
    ring = C._cut(doc, 'CowlBandAnnulus', outer, inner)
    arc = _common(doc, 'CowlBandArc', ring, wedge)

    return C._fuse(doc, 'CowlFlangeBand', lip, arc)


def add(doc, base):
    """`base`, fused with all three -- the shape `bulkhead_section.emit()` fuses onto its
    running positive when `is_cowling`, on top of what `simple_positives.cowl_positives`
    already adds (the plate, the longeron flange, its chamfer).

    No standalone `main()` here and no isolated OpenSCAD reference, unlike this port's other
    modules: every alias these three shapes read but do not define -- `corner_radius`,
    `flange_thickness`, `bulkhead_thickness`, `plate_thickness`, `far`, `flange_end_x`,
    `extrusion_width` -- belongs to another constituent, so a standalone build would need
    the same merge `bulkhead_section.py` already does and would only be exercising that
    merge again under another name. The binding check is the assembled `bulkhead_full` at
    `is_cowling`, against the real OpenSCAD render.
    """
    wedge = _wedge_mask(doc)
    node = C._fuse(doc, 'CowlRimFuse', base, rim_ring(doc, wedge))
    node = C._fuse(doc, 'CowlDiskFuse', node, rim_disk(doc, wedge))
    return C._fuse(doc, 'CowlBandFuse', node, flange_band(doc, wedge))
