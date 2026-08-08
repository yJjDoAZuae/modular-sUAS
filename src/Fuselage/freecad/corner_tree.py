"""IP-FC-38: the corner as a parametric Part:: CSG document tree.

Where part_middle.py builds a static TopoShape, this builds *document objects* -- primitives
with live properties, boolean nodes, and every dimension an expression over a spreadsheet.
The result is what a user actually receives: a .FCStd whose parameters are visible and
editable, ending in a stable tip their own geometry can hang off.

The profile decomposes entirely into primitives, which is not obvious from the source. Each
polygon mask in corner_middle_shape is a union of half-planes:

  * the longeron chamfer, [(0,0), (-far,0), (-far,-far), (0,-far)], is the third quadrant
    -- one axis-aligned box;
  * the mirror-line mask, [(-far,-far), (far,far), (far,-far)], is the half-plane y < x
    -- one box rotated -45 degrees;
  * the bulkhead boundary is an 8-gon whose vertices (-4, 1.55), (-2.45, 0), (0, -2.45) and
    (1.55, -4) are COLLINEAR on x + y = flat_offset. It is therefore the union of three
    half-planes -- x < flat_x, y < flat_x, and x + y < flat_offset -- so three boxes, one of
    them rotated 45 degrees.

So no sketches are needed and nothing is baked: every mask is a Part::Box whose size and
placement are expressions. The half-plane placements are derived in the spreadsheet rather
than in expressions on the objects, so the arithmetic is visible to whoever opens the file.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import is_entry_point

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
GENERATOR = 'fuselage_corner'

# name, formula-or-value. Plain values are the user's to edit; '=' rows are derived and
# exist so the geometry expressions stay readable.
PARAMS = [
    ('U', '1.0'),
    ('FX', '1.0'),
    ('bulkhead_thickness', '6.0'),
    ('panel_thickness', '4.77'),
    ('panel_offset', '0.0'),
    ('panel_overlap', '4.0'),
    ('panel_tolerance', '0.1'),
    ('longeron_tolerance', '0.05'),
    ('extrusion_width', '0.4'),

    ('corner_radius', '=U * 10'),
    ('longeron_radius', '=U * 2'),
    ('unit_length', '=U * FX * 100'),
    ('eps', '0.01'),
    ('longeron_chamfer', '=extrusion_width'),
    ('far', '=corner_radius * 2'),

    # flat_offset takes the chamfer as a floor, so the flat face clears the bore and its
    # chamfer *and* wherever the panel interface has been pushed out to.
    ('flat_offset', '=-max(longeron_radius + longeron_tolerance + longeron_chamfer, '
                    '(panel_overlap + panel_offset) - '
                    '(corner_radius - panel_thickness - panel_tolerance))'),
    ('flat_x', '=-(panel_overlap + panel_offset)'),

    # the section's z extent
    ('z0', '=bulkhead_thickness * 2 - eps'),
    ('height', '=unit_length / 2 - bulkhead_thickness * 2 + eps * 2'),
    ('cut_z0', '=z0 - eps'),
    ('cut_h', '=height + eps * 2'),

    # panel interface
    ('rect_w', '=panel_overlap + panel_offset - panel_tolerance'),
    ('slot_x', '=-panel_overlap * 2 - panel_offset + panel_tolerance'),
    ('slot_y', '=corner_radius - panel_thickness - panel_tolerance'),
    ('slot_w', '=panel_overlap * 2'),
    ('slot_d', '=panel_thickness * 2 + panel_tolerance * 2'),

    # A half-plane is a box rotated onto the cut line. For a box rotated by t about z,
    # local +x advances (x+y) by sqrt(2) per unit at +45 and (y-x) by -sqrt(2) at -45, so
    # the base corner is placed by solving for the sum and difference of its coordinates.
    # mirror line, y < x, rotated -45:
    ('diag_base', '=-far'),
    ('diag_len', '=far * 2'),
    ('diag_wid', '=far * 2 * sqrt(2)'),
    # bulkhead boundary, x + y < flat_offset, rotated +45:
    ('flatd_x', '=flat_offset / 2 + far * (1 - sqrt(2))'),
    ('flatd_y', '=flat_offset / 2 - far * (1 + sqrt(2))'),
]


def _owned(doc, typename, name):
    """Fetch the generator's own object by name, creating and tagging it if absent."""
    obj = doc.getObject(name)
    if obj is None:
        obj = doc.addObject(typename, name)
        obj.addProperty('App::PropertyString', 'Generator', 'Provenance',
                        'Which generator owns this object')
        obj.Generator = GENERATOR
    return obj


def _sheet(doc):
    fresh = doc.getObject('Params') is None
    sheet = doc.getObject('Params') or doc.addObject('Spreadsheet::Sheet', 'Params')
    if fresh:
        for row, (alias, value) in enumerate(PARAMS, start=1):
            sheet.set('A%d' % row, alias)
            sheet.setAlias('B%d' % row, alias)
            sheet.set('B%d' % row, value)
        doc.recompute()
    return sheet


def _box(doc, name, length, width, height, x, y, z, angle=None):
    """A Part::Box with every dimension and placement component an expression."""
    box = _owned(doc, 'Part::Box', name)
    for prop, expr in (('Length', length), ('Width', width), ('Height', height)):
        box.setExpression(prop, expr)
    if angle is not None:
        box.Placement = App.Placement(V(0, 0, 0), App.Rotation(V(0, 0, 1), angle))
    for prop, expr in (('Placement.Base.x', x), ('Placement.Base.y', y),
                       ('Placement.Base.z', z)):
        box.setExpression(prop, expr)
    return box


def _cyl(doc, name, radius, height, z):
    cyl = _owned(doc, 'Part::Cylinder', name)
    cyl.setExpression('Radius', radius)
    cyl.setExpression('Height', height)
    cyl.setExpression('Placement.Base.z', z)
    return cyl


def _cut(doc, name, base, tool):
    node = _owned(doc, 'Part::Cut', name)
    node.Base, node.Tool = base, tool
    return node


def emit(doc):
    """Create or update the corner's middle section as a live CSG tree."""
    P = 'Params.'
    _sheet(doc)

    body = _owned(doc, 'Part::Fuse', 'Body')
    body.Base = _cyl(doc, 'Outer', P + 'corner_radius', P + 'height', P + 'z0')
    body.Tool = _box(doc, 'PanelExt', P + 'rect_w', P + 'corner_radius', P + 'height',
                     '-' + P + 'rect_w', '0', P + 'z0')

    node = _cut(doc, 'CutBore', body,
                _cyl(doc, 'Bore', P + 'longeron_radius + ' + P + 'longeron_tolerance',
                     P + 'cut_h', P + 'cut_z0'))

    node = _cut(doc, 'CutSlot', node,
                _box(doc, 'PanelSlot', P + 'slot_w', P + 'slot_d', P + 'cut_h',
                     P + 'slot_x', P + 'slot_y', P + 'cut_z0'))

    # bulkhead boundary: three half-planes
    node = _cut(doc, 'CutFlatX', node,
                _box(doc, 'FlatX', P + 'far', P + 'far * 2', P + 'cut_h',
                     P + 'flat_x - ' + P + 'far', '-' + P + 'far', P + 'cut_z0'))
    node = _cut(doc, 'CutFlatY', node,
                _box(doc, 'FlatY', P + 'far * 2', P + 'far', P + 'cut_h',
                     '-' + P + 'far', P + 'flat_x - ' + P + 'far', P + 'cut_z0'))
    node = _cut(doc, 'CutFlatDiag', node,
                _box(doc, 'FlatDiag', P + 'diag_len', P + 'diag_wid', P + 'cut_h',
                     P + 'flatd_x', P + 'flatd_y', P + 'cut_z0', angle=45))

    # the diagonal mirror line, y < x
    node = _cut(doc, 'CutDiag', node,
                _box(doc, 'Diag', P + 'diag_len', P + 'diag_wid', P + 'cut_h',
                     P + 'diag_base', P + 'diag_base', P + 'cut_z0', angle=-45))

    # the longeron chamfer: the third quadrant
    half = _cut(doc, 'CutChamfer', node,
                _box(doc, 'Chamfer', P + 'far', P + 'far', P + 'cut_h',
                     '-' + P + 'far', '-' + P + 'far', P + 'cut_z0'))

    # mirror_xy(): reflect across the plane normal to (1,-1,0), then union
    mirror = _owned(doc, 'Part::Mirroring', 'MirrorHalf')
    mirror.Source = half
    mirror.Normal = V(1, -1, 0)
    mirror.Base = V(0, 0, 0)

    whole = _owned(doc, 'Part::Fuse', 'Whole')
    whole.Base, whole.Tool = half, mirror

    # the stable tip: user features bind here and nowhere else
    tip = _owned(doc, 'Part::Refine', 'Tip')
    tip.Source = whole

    doc.recompute()
    return tip


def main():
    REF = 4041.5795009
    doc = App.newDocument('corner_tree')
    tip = emit(doc)

    s = tip.Shape
    d = s.Volume - REF
    print('PART:: CSG tree -- corner_middle')
    print('  volume  = %.6f' % s.Volume)
    print('  ref     = %.6f  (OpenSCAD, faceted)' % REF)
    print('  delta   = %+.6f  (%+.4f%%)' % (d, 100 * d / REF))
    print('  valid   = %s  solids=%d faces=%d'
          % (s.isValid(), len(s.Solids), len(s.Faces)))
    print('  nodes   = %d generated' % len([o for o in doc.Objects
                                            if getattr(o, 'Generator', None)]))

    out = os.path.join(HERE, 'corner_tree.FCStd')
    doc.saveAs(out)
    print('  saved %s' % os.path.basename(out))


if is_entry_point(__name__):
    main()
