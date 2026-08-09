"""IP-FC-9: `bulkhead_section_full` -- the octant translated to its corner and tiled.

`octant_to_full()` is `mirror_x(mirror_y(mirror_xy(...)))`, three nested doublings about the
fuselage centre. Each stage is a `Part::Mirroring` document object plus a fuse, so the tiling
stays in the parametric tree: seven mirrors, seven fuses, no rebuilt geometry and nothing for
a downstream edit to fall out of sync with.

The mirrors are about the ORIGIN, which is why the octant is translated to
`(W/2 - R, W/2 - R)` first -- `bulkhead_section_octant` does exactly that, and this is the
whole of its non-interconnect branch.

**The full part is not eight times the octant.** `octant_mask` is shifted by `eps`, so
adjacent octants overlap by a sliver and the union reclaims it: 6922.50 against 8 x 865.77 =
6926.15, a 3.65 mm3 difference. That makes the tiling a real check rather than an arithmetic
one -- a mirror about the wrong plane would still give eight copies and a plausible volume,
but not this volume and not one solid.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import bulkhead_section
import corner_tree as C
import parameters
from corner_common import is_entry_point

V = App.Vector

# ref_bulkhead_full.scad. `bulkhead_render()` calls bulkhead_section_full and nothing else,
# so this is the whole part -- and `render_variant.py 1.0 end_bolt 3/16in`, which resolves
# the variant through derived_parameters() rather than through a hand-typed .scad, gives
# 6922.5048968 as well. Identical to the digit: the reference chain is not just internally
# consistent, it agrees with what the sweep actually produces.
REF = 6922.5048968
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
    args = [a for a in sys.argv[1:] if not a.endswith('.py')]
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
    print('  8x octant = %.7f  -- the eps overlap the union reclaims is %.4f'
          % (8 * bulkhead_section.REF, 8 * bulkhead_section.REF - REF))
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
