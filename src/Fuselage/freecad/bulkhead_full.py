"""IP-FC-9: `bulkhead_section_full` -- the octant translated to its corner and tiled.

`octant_to_full()` is `mirror_x(mirror_y(mirror_xy(...)))`, three nested doublings about the
fuselage centre. Each stage is a `Part::Mirroring` document object plus a fuse, so the tiling
stays in the parametric tree: seven mirrors, seven fuses, no rebuilt geometry and nothing for
a downstream edit to fall out of sync with.

The mirrors are about the ORIGIN, which is why the octant is translated to
`(W/2 - R, W/2 - R)` first -- `bulkhead_section_octant` does exactly that, and this is the
whole of its non-interconnect branch.

**The full part is exactly eight times the octant, and it did not used to be.** `octant_mask`
was shifted by `eps` so adjacent octants overlapped by a sliver the union then reclaimed --
6922.50 against 8 x 865.77 = 6926.15. That overlap was there for OpenSCAD, whose union wanted
help resolving two solids that meet on an exact shared plane. **OCCT does not want the help
and is harmed by it**: a 0.01 mm sliver is 4e-5 of a 250 mm part, under what its booleans
resolve, and the tiling fuse went invalid at U >= 2.5 while the octant and its mirror were
each still valid (IP-FC-49). The mask overlap is now `mask_eps = 0` and every U from 0.5 to
4.0 tiles into one valid solid.

Measured directly before changing it: a solid fused with its own mirror about the touching
plane is valid and volume-exact at 10, 100, 250 and 400 mm with no overlap at all.

**Removing it did not move the part.** The full volume is identical either way -- 7122.0983
at U=1, 39413.112 at U=2 -- because the sliver really was being reclaimed. What changed is
what `8 x octant` means, and it got *stronger* as a check: it was "matches 6926.15, a number
with no independent meaning", and it is now exact equality, which says the eight pieces tile
with neither gap nor overlap. A mirror about the wrong plane still fails it.

    U      full            8 x octant      difference
    1.0    7122.0983       7122.0983       -0.0000      (was -3.6477)
    2.0    39413.1120      39413.1856      -0.0736      (was -10.2960)
    4.0    304571.8350     304572.1779     -0.3429      (would not build)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import bulkhead_section
import corner_tree as C
import parameters
from corner_common import is_entry_point, script_args

V = App.Vector

# ref_bulkhead_full.scad. `bulkhead_render()` calls bulkhead_section_full and nothing else,
# so this is the whole part -- and `render_variant.py 1.0 end_bolt 3/16in`, which resolves the
# variant through derived_parameters() rather than through a hand-typed .scad, gave the
# pre-B12 value 6922.5048968 identically. That cross-check says the reference chain is not
# just internally consistent but agrees with what the sweep actually produces; it has NOT been
# re-run since the fix, so treat it as evidence about the chain rather than about this number.
#
# Regenerated 2026-08-11 for OQ-DES-B12, by re-rendering ref_bulkhead_full.scad. The part lost
# 0.2322237 mm3, which is 8 x the 0.0290279 the octant lost -- the eight corners each carrying
# the same nominal-rib correction, and a check that the fix did not leak into the tiling.
REF = 6922.2726731
EXPECT_BBOX = (-45.1375, -45.1375, 0.0, 45.1375, 45.1375, 6.0)

# IP-FC-132: U=1.0 cowling_bolt 0mm, rendered through the real OpenSCAD module and measured
# from the STL mesh (mesh_stats.py) -- 34,256 triangles, so this is a faceted volume like
# every other REF in this port, not an analytic one. FreeCAD came out at 9854.8937182 on the
# first build that produced a valid single solid, +0.0017% and the bounding box exact.
REF_COWLING = 9854.7238
EXPECT_BBOX_COWLING = (-50.0, -50.0, 0.0, 50.0, 50.0, 8.0)

# IP-FC-132: U=1.0 interconnect 3/16in, rendered through the real OpenSCAD module and measured
# from the STL mesh (mesh_stats.py) -- 25,288 triangles. FreeCAD came out at 8209.5318, +0.0013%
# and the bounding box exact. Cross-checked at two more variants (not kept as REFs, since one
# is enough to gate the sweep and the others exist only to rule out a one-parameter-set
# coincidence): U=1.0 0mm, FreeCAD 7259.3321 vs OpenSCAD 7259.2816 (+0.0007%); U=2.5 3/16in,
# FreeCAD 66047.5561 vs OpenSCAD 66046.4679 (+0.0016%). All three landed after fixing
# `fillets.outer_corner_fillet` to take `make_web`: the source only cuts the stepped
# chamfer-relief stack when `make_web` is true, and cuts a single full-radius cylinder
# otherwise, a branch the port had never carried, so every `make_web=False` half (the
# interconnect's top) kept about 2.92 mm3 of material at that corner that the real geometry
# does not have.
REF_INTERCONNECT = 8209.4223
EXPECT_BBOX_INTERCONNECT = (-45.1375, -45.1375, 0.0, 45.1375, 45.1375, 12.0)

# mirror_xy, then mirror_y, then mirror_x -- the nesting order in octant_to_full(). Each
# normal is the plane's, and reflection does not care about its sign.
STAGES = [('Xy', (1, -1, 0)), ('Y', (0, 1, 0)), ('X', (1, 0, 0))]

PARAMS = [
    # bulkhead_section_octant's translate, the only thing in its non-interconnect branch
    ('corner_offset', '=unit_width / 2 - corner_radius'),

    # IP-FC-132: the interconnect octant's mass-reduction cut -- see `_mass_reduction_cut`.
    # `ramp_x3` is the source's own `-(panel_offset + panel_overlap + flange_thickness +
    # 2*flange_fillet_radius)`, the ramp's top-inboard corner; `ramp_x2` is one
    # bulkhead_thickness further out, its bottom-inboard corner, the same 45 degree drop
    # every self-supporting overhang in this port uses.
    ('ramp_x3', '=-(panel_offset + panel_overlap + flange_thickness '
                '+ 2 * flange_fillet_radius)'),
    ('ramp_x2', '=ramp_x3 - bulkhead_thickness'),
]


def _mirror(doc, name, source, normal):
    node = C._owned(doc, 'Part::Mirroring', name)
    node.Source = source
    node.Normal = V(*normal)
    node.Base = V(0, 0, 0)
    return node


def octant_to_full(doc, node):
    for tag, normal in STAGES:
        node = C._fuse(doc, 'Tile' + tag, node,
                       _mirror(doc, 'Mirror' + tag, node, normal))
    return node


def _mass_reduction_cut(doc):
    """The interconnect's mass-reduction ramp, IP-FC-132.

    The source cuts this from the union of both halves, over the full depth `2 *
    bulkhead_thickness` down to `bulkhead_thickness`, everywhere outboard of the flange --
    full depth is kept only out to the flange plus two fillet radii, which is why the ramp's
    inboard corner is `ramp_x3` rather than the flange face itself. A 45 degree ramp between
    the two depths, self-supporting when printed, the same reasoning every other 45 degree
    face in this port carries.

    **This is the one profile in the whole bulkhead that is not in the X-Y plane.** Every
    other non-axis-aligned edge in this port is a half-plane in X-Y, clipped by a box rotated
    about Z; this one is a half-plane in X-Z, extruded the full `unit_width` along Y. Rather
    than derive a Y-axis half-plane box from scratch, it is a fully constrained sketch --
    `corner_tree._sketch()`'s pattern, the same one `web.py`'s interconnect profile uses --
    reoriented into the X-Z plane by a 90 degree rotation about X applied to the finished
    sketch, and extruded `Symmetric` so the sign of that rotation cannot matter: a symmetric
    extrusion covers `+far` and `-far` from the sketch plane either way, which is exactly
    `linear_extrude(height=unit_width, center=true)`.
    """
    P = 'Params.'
    pts = [(-50.0, 6.0), (-18.0, 6.0), (-12.0, 12.0), (-50.0, 12.0)]
    dims = [
        (0, 'X', '-' + P + 'unit_width / 2'), (0, 'Y', P + 'bulkhead_thickness'),
        (1, 'X', P + 'ramp_x2'), (1, 'Y', P + 'bulkhead_thickness'),
        (2, 'X', P + 'ramp_x3'), (2, 'Y', '2 * ' + P + 'bulkhead_thickness'),
        (3, 'X', '-' + P + 'unit_width / 2'), (3, 'Y', '2 * ' + P + 'bulkhead_thickness'),
    ]
    sk = C._sketch(doc, 'RampProfile', pts, horizontals=(), verticals=(), on_x=(),
                  dims=dims, angle=0, z_expr='0')
    # Reorient into the X-Z plane: local (u, v) becomes world (X, Z) rather than (X, Y).
    sk.Placement = App.Placement(V(0, 0, 0), App.Rotation(V(1, 0, 0), 90))

    ext = C._prism(doc, 'RampCut', sk, P + 'unit_width')
    ext.Symmetric = True
    return ext


def _interconnect_octant(doc, seed, rows):
    """`bulkhead_section_octant`'s `is_interconnect` branch: two mirrored halves of the
    same octant, sharing one document and one Params sheet, distinguished only by `make_web`
    and by the `Bot`/`Top` tag every object each half builds carries (IP-FC-132; see
    `corner_tree.tag()`).
    """
    with C.tag('Bot'):
        bottom = bulkhead_section.emit(doc, seed, rows=rows, make_web=True)
    with C.tag('Top'):
        top = bulkhead_section.emit(doc, seed, rows=rows, make_web=False)

    # mirror([0,0,-1]) { translate([0,0,-2*bulkhead_thickness]) { <top half> } } -- translate
    # on the section's own Placement, same as the outer corner_offset translate below, then
    # a Part::Mirroring about the z = 0 plane.
    top.setExpression('Placement.Base.z', '-2 * Params.bulkhead_thickness')
    top_mirrored = _mirror(doc, 'TopMirror', top, (0, 0, 1))

    halves = C._fuse(doc, 'IcHalves', bottom, top_mirrored)
    return C._cut(doc, 'IcOctant', halves, _mass_reduction_cut(doc))


def emit(doc, seed):
    rows = bulkhead_section.merged_rows(seed) + PARAMS
    # is_interconnect is a seeded literal row, so its value comes from the SEED, read the
    # way every other Python-level branch in this port reads a type flag (bulkhead_section's
    # own is_cowling/is_interconnect are read off the sheet AFTER seeding instead, because
    # they are needed post-seed there; here the branch has to be taken BEFORE anything is
    # built, so it reads the seed directly).
    is_interconnect = float(seed.get('is_interconnect', 0.0)) >= 0.5

    octant = (_interconnect_octant(doc, seed, rows) if is_interconnect
             else bulkhead_section.emit(doc, seed, rows=rows))

    # bulkhead_section_octant's translate. Put on the octant's own Placement rather than a
    # wrapper -- Part::Refine and Part::Cut both pass a Placement through to the result --
    # so this moves the whole octant and stays expression-bound. is_interconnect's octant is
    # a Part::Cut (`_interconnect_octant`'s tip), not a Part::Refine; both carry a Placement.
    octant.setExpression('Placement.Base.x', 'Params.corner_offset')
    octant.setExpression('Placement.Base.y', 'Params.corner_offset')

    tip = C._owned(doc, 'Part::Refine', 'BulkheadFull')
    tip.Source = octant_to_full(doc, octant)
    doc.recompute()
    return tip


def main():
    args = script_args()
    if not args:
        print('usage: freecadcmd bulkhead_full.py params.json')
        return 0

    doc = App.newDocument('bulkhead_full')
    tip = emit(doc, parameters.seed(args[0]))
    is_cowling = float(doc.getObject('Params').get('is_cowling')) >= 0.5
    is_interconnect = float(doc.getObject('Params').get('is_interconnect')) >= 0.5
    if is_cowling:
        ref, expect_bbox, label = REF_COWLING, EXPECT_BBOX_COWLING, ' (is_cowling)'
    elif is_interconnect:
        ref, expect_bbox, label = REF_INTERCONNECT, EXPECT_BBOX_INTERCONNECT, ' (is_interconnect)'
    else:
        ref, expect_bbox, label = REF, EXPECT_BBOX, ''

    s = tip.Shape
    d = s.Volume - ref
    bb = s.BoundBox
    got = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)

    print('PART:: CSG tree -- bulkhead_section_full%s' % label)
    print('  nodes   = %d' % len(doc.Objects))
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, through the real module)' % ref)
    print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * d / ref))
    if not is_cowling and not is_interconnect:
        # Only meaningful against the end type's own octant reference -- a cowling or
        # interconnect bulkhead's octant is a different shape and bulkhead_section.REF does
        # not describe it.
        print('  8x octant = %.7f  -- gap/overlap in the tiling is %+.4f'
              % (8 * bulkhead_section.REF, 8 * bulkhead_section.REF - s.Volume))
    print('  bbox    = [%s]' % ', '.join('%.4f' % v for v in got))
    print('  expect  = [%s]' % ', '.join('%.4f' % v for v in expect_bbox))
    print('  valid   = %s  solids=%d  faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    fail = []
    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids -- the eight octants meet into one body' % len(s.Solids))
    if abs(d) / ref > 1e-3:
        fail.append('volume off by more than 0.1%')
    if max(abs(a - b) for a, b in zip(got, expect_bbox)) > 1e-3:
        fail.append('bounding box moved')
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
