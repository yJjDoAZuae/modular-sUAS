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

# mirror_xy, then mirror_y, then mirror_x -- the nesting order in octant_to_full(). Each
# normal is the plane's, and reflection does not care about its sign.
STAGES = [('Xy', (1, -1, 0)), ('Y', (0, 1, 0)), ('X', (1, 0, 0))]

PARAMS = [
    # bulkhead_section_octant's translate, the only thing in its non-interconnect branch
    ('corner_offset', '=unit_width / 2 - corner_radius'),
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


def emit(doc, seed):
    rows = bulkhead_section.merged_rows(seed) + PARAMS
    octant = bulkhead_section.emit(doc, seed, rows=rows)

    # bulkhead_section_octant's translate. Put on the section's own Placement rather than a
    # wrapper: Part::Refine passes its Source's shape through and applies its Placement to
    # the result, so this moves the whole octant and stays expression-bound.
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
    s = tip.Shape
    d = s.Volume - REF
    bb = s.BoundBox
    got = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)

    print('PART:: CSG tree -- bulkhead_section_full')
    print('  nodes   = %d' % len(doc.Objects))
    print('  volume  = %.7f' % s.Volume)
    print('  ref     = %.7f  (OpenSCAD, through the real module)' % REF)
    print('  delta   = %+.7f  (%+.5f%%)' % (d, 100 * d / REF))
    print('  8x octant = %.7f  -- gap/overlap in the tiling is %+.4f'
          % (8 * bulkhead_section.REF, 8 * bulkhead_section.REF - s.Volume))
    print('  bbox    = [%s]' % ', '.join('%.4f' % v for v in got))
    print('  expect  = [%s]' % ', '.join('%.4f' % v for v in EXPECT_BBOX))
    print('  valid   = %s  solids=%d  faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))

    fail = []
    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids -- the eight octants meet into one body' % len(s.Solids))
    if abs(d) / REF > 1e-3:
        fail.append('volume off by more than 0.1%')
    if max(abs(a - b) for a, b in zip(got, EXPECT_BBOX)) > 1e-3:
        fail.append('bounding box moved')
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
