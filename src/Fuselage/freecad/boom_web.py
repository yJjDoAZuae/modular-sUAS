"""IP-FC-12: the boom bulkhead's web spine and the shapes offset from it.

`upper_boom_support_centerline_shape` is a **centreline**, not an outline -- the web is what
you get by stroking it to `web_width`, exactly as a road is a centreline stroked to its width.
So the port is one sketch and then offsets: `offset(+web_width/2)` gives the web, and
`offset(-web_width/2)` gives the region inside it that later becomes lightening.

Two things here are not obvious.

**The spine is a sketch, not a polygon.** `Part::Polygon` takes its vertices as a plain list of
vectors, and a list of vectors cannot carry expressions -- every one of these seven vertices is
a function of the sheet. A fully constrained `Sketcher::SketchObject` with each vertex pinned by
an expression-driven DistanceX/DistanceY is the parametric equivalent, and it is what
`corner_tree._sketch` already does for the corner's profiles.

**Its first two vertices coincide whenever the boom is on the centreline.** The source writes
`[0, z]` then `[y, z]`, which is a zero-length edge at `boom_y_position = 0` -- harmless in
OpenSCAD, and an unsolvable sketch here. Two of the three swept boom types (`offset_single`,
`center_single`) sit at `y = 0` and the third (`dual`) does not, so this is a real topology
change across the corpus rather than a guard against nonsense, and it is branched on the same
way `corner_tree._degenerate` branches on the no-panel variant.

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

# ref_boom_bulkhead.scad modes 0, 1, 2, 3
REFS = {
    'centerline': (556.0000000, (0.0, 25.0, 40.0, 43.9)),
    'mirrored': (1112.0000000, (-40.0, 25.0, 40.0, 43.9)),
    'stroke': (1668.0908114, (-43.0, 22.0004, 43.0, 46.9)),
    'erosion': (616.9927776, (-36.6573, 28.0709, 36.6573, 40.9)),
}

PARAMS = [
    ('unit_width', '100.0'),
    ('corner_radius', '10.0'),
    ('panel_thickness', '3.0'),
    ('panel_tolerance', '0.1'),
    ('bolt_offset', '8.0'),
    ('web_width', '6.0'),
    ('boom_y_position', '0.0'),
    ('boom_z_position', '25.0'),

    # the three x/y values the spine turns at
    ('cl_corner', '=unit_width / 2 - corner_radius'),
    ('cl_bolt', '=unit_width / 2 - corner_radius - bolt_offset'),
    ('cl_web', '=unit_width / 2 - panel_thickness - web_width / 2 - panel_tolerance'),
    ('half_web', '=web_width / 2'),

    # enclosure for plane2d.union -- the stroke reaches half a web width beyond the spine
    ('web_reach', '=2 * (unit_width / 2 + web_width)'),
]


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def _on_centreline(doc):
    """True when the spine's first two vertices coincide, so the sketch needs six not seven."""
    return abs(float(doc.getObject('Params').get('boom_y_position'))) < 1e-12


def spine(doc, tag='', z=P + 'boom_z_position'):
    """The seven-vertex centreline, fully constrained from the sheet.

    `z` is the one input the lower web changes -- the source evaluates it at
    `-boom_z_position`. The three `cl_*` turning values are frame dimensions and do not move
    with the boom, so they are read straight from the sheet in both evaluations.
    """
    flat = _on_centreline(doc)
    y = P + 'boom_y_position'
    # (seed x, seed y, x expression, y expression)
    verts = [(0.0, 25.0, '0', z)]
    if not flat:
        verts.append((10.0, 25.0, y, z))
    verts += [
        (32.0, 32.0, P + 'cl_bolt', P + 'cl_bolt'),
        (40.0, 40.0, P + 'cl_corner', P + 'cl_corner'),
        (40.0, 43.9, P + 'cl_corner', P + 'cl_web'),
        (0.0, 43.9, '0', P + 'cl_web'),
        (0.0, 40.0, '0', P + 'cl_corner'),
    ]
    pts = [(vx, vy) for vx, vy, _, _ in verts]
    dims = []
    for i, (_, _, ex, ey) in enumerate(verts):
        dims.append((i, 'X', ex))
        dims.append((i, 'Y', ey))
    return C._sketch(doc, tag + 'Spine', pts, (), (), (), dims, 0, '0')


def centerline(doc, tag='', z=P + 'boom_z_position'):
    return plane2d.face(doc, tag + 'Centerline', spine(doc, tag, z))


def mirror_x(doc, name, base):
    """`mirror_x()` -- a shape unioned with its reflection in the YZ plane."""
    flip = C._owned(doc, 'Part::Mirroring', name + 'Mirror')
    flip.Source = base
    flip.Normal = V(1, 0, 0)
    return plane2d.union(doc, name, [base, flip], P + 'web_reach')


def emit(doc, seed=None):
    """The spine and the two shapes offset from it, as a dict of tips."""
    C._SEEN.clear()
    sheet(doc, seed)
    base = centerline(doc)
    tips = {'centerline': base, 'mirrored': mirror_x(doc, 'Mirrored', base)}
    tips['stroke'] = plane2d.offset(doc, 'Stroke', tips['mirrored'], P + 'half_web')
    tips['erosion'] = plane2d.offset(doc, 'Erosion', tips['mirrored'],
                                     '-' + P + 'half_web')
    doc.recompute()
    return tips


def main():
    doc = App.newDocument('boom_web')
    tips = emit(doc)

    print('PART:: 2D CSG tree -- boom bulkhead web spine and its offsets')
    print('  %-22s %13s %13s %11s  %s'
          % ('shape', 'FreeCAD', 'OpenSCAD', 'delta', 'checks'))
    ok = True
    for name in ('centerline', 'mirrored', 'stroke', 'erosion'):
        ref, bbox = REFS[name]
        ok &= plane2d.report(doc, name, tips[name].Shape, ref, 'web_reach', bbox)
    print('')
    print('  %s' % ('all shapes agree' if ok else 'MISMATCH -- see checks above'))
    print('  spine vertices: %d (%s)'
          % (tips['centerline'].Shape.Wires[0].Edges.__len__(),
             'boom on the centreline' if _on_centreline(doc) else 'boom offset in y'))


if is_entry_point(__name__):
    main()
