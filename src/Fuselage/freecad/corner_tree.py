"""IP-FC-38: the corner as a parametric Part:: CSG document tree.

Where part_*.py build static TopoShapes, this builds *document objects* -- primitives with
live properties, boolean nodes, and every dimension an expression over a spreadsheet. The
result is what a user actually receives: a .FCStd whose parameters are visible and editable,
ending in a stable tip their own geometry can hang off.

Most of the corner reduces to primitives, which is not obvious from the source.

**The section profile is all half-planes.** Each polygon mask in corner_middle_shape is a
union of half-planes, so every one is a box:

  * the longeron chamfer, [(0,0), (-r,0), (-r,-r), (0,-r)], is the third quadrant;
  * the mirror-line mask, [(-r,-r), (r,r), (r,-r)], is the half-plane y < x -- where r is
    mask_reach(corner_radius), the alias these rows are named for;
  * the bulkhead boundary is an 8-gon whose vertices (-4, 1.55), (-2.45, 0), (0, -2.45) and
    (1.55, -4) are COLLINEAR on x + y = flat_offset -- so it is three half-planes.

**The snap groove is a stack of primitives.** rotate_extrude of the nub profile is a bore
cylinder, an expanding cone, the rib cylinder, and a contracting cone, fused.

**Two polygons genuinely need sketches**: corner_end's wedge and corner_transition's relief
are non-convex with no collinear vertices. Sketch coordinates are not expression-bindable but
constraints are, so each is generated FULLY CONSTRAINED with every dimension driven from the
sheet. Full constraint is not optional -- an under-constrained sketch deforms silently under
a parameter change and still extrudes to a valid solid.

Half-plane box placements are derived in the spreadsheet rather than in expressions on the
objects, so the trigonometry is visible to whoever opens the file.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part
import Sketcher

from corner_common import build_sheet, is_entry_point

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
GENERATOR = 'fuselage_corner'

# name, formula-or-value. Plain values are the user's to edit; '=' rows are derived and
# exist so the geometry expressions stay readable. NB: an alias may not collide with a unit
# symbol -- 'w' (watt) and 'h' (hour) are rejected as "Invalid alias".
PARAMS = [
    ('U', '1.0'),
    ('FX', '1.0'),
    ('bulkhead_thickness', '6.0'),
    ('panel_thickness', '4.77'),
    ('panel_offset', '0.0'),
    ('panel_overlap', '4.0'),
    ('panel_tolerance', '0.1'),
    ('longeron_tolerance', '0.05'),
    ('greeble_thickness', '0.8'),
    ('greeble_nub_thickness', '0.8'),
    ('greeble_tolerance', '0.05'),
    ('extrusion_width', '0.4'),

    ('corner_radius', '=U * 10'),
    ('longeron_radius', '=U * 2'),
    ('unit_length', '=U * FX * 100'),
    ('eps', '0.01'),
    ('longeron_chamfer', '=extrusion_width'),
    # mask_reach() from shape_modifier_utils.scad -- how far a masking half-plane has to
    # extend to cover the profile. Named `far` until it had to share a sheet with the
    # bulkhead, where `far` is unit_width: two "big enough" distances, one name, and the
    # rows built on it (mask_diag_*) would have silently taken the wrong one.
    ('mask_reach', '=2 * corner_radius'),
    ('through_cut', '=bulkhead_thickness * 3'),

    # flat_offset takes the chamfer as a floor, so the flat face clears the bore and its
    # chamfer *and* wherever the panel interface has been pushed out to.
    ('flat_offset', '=-max(longeron_radius + longeron_tolerance + longeron_chamfer, '
                    '(panel_overlap + panel_offset) - '
                    '(corner_radius - panel_thickness - panel_tolerance))'),
    ('flat_x', '=-(panel_overlap + panel_offset)'),

    # section z extents: end, transition, middle
    ('end_z0', '0.0'),
    ('end_h', '=bulkhead_thickness + eps'),
    ('trans_z0', '=bulkhead_thickness'),
    ('trans_h', '=bulkhead_thickness'),
    ('mid_z0', '=bulkhead_thickness * 2 - eps'),
    ('mid_h', '=unit_length / 2 - bulkhead_thickness * 2 + eps * 2'),

    # panel interface
    ('rect_w', '=panel_overlap + panel_offset - panel_tolerance'),
    ('slot_x', '=-panel_overlap * 2 - panel_offset + panel_tolerance'),
    ('slot_y', '=corner_radius - panel_thickness - panel_tolerance'),
    ('slot_w', '=panel_overlap * 2'),
    ('slot_d', '=panel_thickness * 2 + panel_tolerance * 2'),

    # A half-plane is a box rotated onto the cut line. For a box rotated by t about z,
    # local +x advances (x+y) by sqrt(2) per unit at +45 and (y-x) by -sqrt(2) at -45, so
    # the base corner is placed by solving for the sum and difference of its coordinates.
    ('mask_diag_base', '=-mask_reach'),               # mirror line, y < x, at -45
    ('mask_diag_len', '=mask_reach * 2'),
    ('mask_diag_wid', '=mask_reach * 2 * sqrt(2)'),
    ('flatd_x', '=flat_offset / 2 + mask_reach * (1 - sqrt(2))'),   # x+y < flat_offset, +45
    ('flatd_y', '=flat_offset / 2 - mask_reach * (1 + sqrt(2))'),

    # the greeble socket
    ('greeble_radius', '=longeron_radius + longeron_tolerance + greeble_thickness '
                       '+ greeble_tolerance'),
    ('greeble_nub_radius', '=greeble_radius + greeble_nub_thickness'),
    ('greeble_nub_height', '=bulkhead_thickness / 3'),
    ('nub_span', '=bulkhead_thickness'),      # the revolve's full z extent
    ('nub_z1', '=bulkhead_thickness / 2 - greeble_nub_height / 2 - greeble_nub_thickness'),
    ('nub_z2', '=bulkhead_thickness / 2 - greeble_nub_height / 2'),
    ('nub_z3', '=bulkhead_thickness / 2 + greeble_nub_height / 2'),
    ('nub_z4', '=bulkhead_thickness / 2 + greeble_nub_height / 2 + greeble_nub_thickness'),
    # The mouth is a box rotated 45 about z. Placement.Base of a rotated box is the corner
    # AFTER rotation, not before -- unlike Part.makeBox(...).rotate(), which turns an
    # already-placed box about the world origin. The unrotated corner is (-2r, -r), so
    # rotating it by 45 gives (-r, -3r)/sqrt(2).
    ('mouth_w', '=greeble_radius * 2'),
    ('mouth_x', '=-greeble_radius / sqrt(2)'),
    ('mouth_y', '=-greeble_radius * 3 / sqrt(2)'),
    ('cut_z0', '=-through_cut / 2'),

    # the transition's tapered bore
    ('relief_depth', '=longeron_radius + greeble_thickness + greeble_tolerance'),
    ('relief_mid', '=0.75 * bulkhead_thickness + eps'),
    ('relief_top', '=bulkhead_thickness + eps'),
    ('relief_diag', '=longeron_radius / sqrt(2)'),
]


# Every object name must be touched exactly once per emit(). Re-fetching a name that has
# already been built this pass means two different nodes were given the same name, and
# re-pointing the earlier one's Base at a descendant produces a dependency cycle -- which
# FreeCAD reports only as "The graph must be a DAG", after which recompute order is wrong
# and shapes come back null. Cheap to assert, very hard to diagnose from the symptom.
_SEEN = set()


def _owned(doc, typename, name):
    """Fetch the generator's own object by name, creating and tagging it if absent."""
    if name in _SEEN:
        raise RuntimeError('duplicate node name %r -- the second use would re-point the '
                           'first and create a cycle' % name)
    _SEEN.add(name)
    obj = doc.getObject(name)
    if obj is None:
        obj = doc.addObject(typename, name)
        obj.addProperty('App::PropertyString', 'Generator', 'Provenance',
                        'Which generator owns this object')
        obj.Generator = GENERATOR
    return obj


def _sheet(doc, extra=(), seed=None):
    """The parameter sheet. `extra` appends rows for a part that re-evaluates these
    descriptions at different arguments -- see bulkhead_tree.py.

    Without a `seed` the literal rows below are `fuselage_corner.scad`'s hand driver
    values, which is what the isolated references in this directory are rendered at. A
    seed replaces them with the swept parameter set -- see parameters.py. The driver is
    not a source of truth about design intent, so anything assembling this alongside the
    bulkhead must seed it.
    """
    return build_sheet(doc, PARAMS, seed, extra)


def _box(doc, name, length, width, height, x, y, z, angle=None):
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


def _cone(doc, name, r1, r2, height, z):
    cone = _owned(doc, 'Part::Cone', name)
    cone.setExpression('Radius1', r1)
    cone.setExpression('Radius2', r2)
    cone.setExpression('Height', height)
    cone.setExpression('Placement.Base.z', z)
    return cone


def _cut(doc, name, base, tool):
    node = _owned(doc, 'Part::Cut', name)
    node.Base, node.Tool = base, tool
    return node


def _fuse(doc, name, base, tool):
    node = _owned(doc, 'Part::Fuse', name)
    node.Base, node.Tool = base, tool
    return node


def _sketch(doc, name, pts, horizontals, verticals, on_x, dims, angle, z_expr):
    """A fully constrained polygon sketch, every dimension driven from the sheet.

    `pts` seeds the geometry; the constraints are what actually place it. `dims` is a list
    of (vertex index, 'X'|'Y', expression) -- a signed distance from the origin to that
    vertex. Full constraint is asserted, because an under-constrained sketch deforms
    silently and still extrudes to a valid solid.
    """
    sk = _owned(doc, 'Sketcher::SketchObject', name)
    if sk.GeometryCount == 0:
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)
        for i in range(n):
            sk.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i + 1) % n, 1))
        for i in horizontals:
            sk.addConstraint(Sketcher.Constraint('Horizontal', i))
        for i in verticals:
            sk.addConstraint(Sketcher.Constraint('Vertical', i))
        for i in on_x:
            sk.addConstraint(Sketcher.Constraint('PointOnObject', i, 1, -1))
        for vertex, axis, expr in dims:
            seed = pts[vertex][0 if axis == 'X' else 1]
            ci = sk.addConstraint(Sketcher.Constraint(
                'Distance' + axis, -1, 1, vertex, 1, seed))
            sk.setExpression('Constraints[%d]' % ci, expr)
        sk.Placement = App.Placement(V(0, 0, 0), App.Rotation(V(0, 0, 1), angle))
        sk.setExpression('Placement.Base.z', z_expr)
    doc.recompute()
    if not sk.FullyConstrained:
        raise RuntimeError('%s is under-constrained (%d DoF) -- it would deform silently'
                           % (name, sk.solve()))
    return sk


def _prism(doc, name, sketch, length_expr):
    ext = _owned(doc, 'Part::Extrusion', name)
    ext.Base = sketch
    ext.DirMode = 'Normal'
    ext.Solid = True
    ext.setExpression('LengthFwd', length_expr)
    return ext


def _section(doc, tag, z0, h):
    """The mirrored profile every axial section extrudes, from z0 through h."""
    P = 'Params.'
    cz = '%s - %seps' % (z0, P)
    ch = '%s + %seps * 2' % (h, P)

    body = _fuse(doc, tag + 'Body',
                 _cyl(doc, tag + 'Outer', P + 'corner_radius', h, z0),
                 _box(doc, tag + 'PanelExt', P + 'rect_w', P + 'corner_radius', h,
                      '-' + P + 'rect_w', '0', z0))
    node = _cut(doc, tag + 'CutBore', body,
                _cyl(doc, tag + 'Bore',
                     P + 'longeron_radius + ' + P + 'longeron_tolerance', ch, cz))
    node = _cut(doc, tag + 'CutSlot', node,
                _box(doc, tag + 'PanelSlot', P + 'slot_w', P + 'slot_d', ch,
                     P + 'slot_x', P + 'slot_y', cz))
    node = _cut(doc, tag + 'CutFlatX', node,
                _box(doc, tag + 'FlatX', P + 'mask_reach', P + 'mask_reach * 2', ch,
                     P + 'flat_x - ' + P + 'mask_reach', '-' + P + 'mask_reach', cz))
    node = _cut(doc, tag + 'CutFlatY', node,
                _box(doc, tag + 'FlatY', P + 'mask_reach * 2', P + 'mask_reach', ch,
                     '-' + P + 'mask_reach', P + 'flat_x - ' + P + 'mask_reach', cz))
    node = _cut(doc, tag + 'CutFlatD', node,
                _box(doc, tag + 'FlatDiag', P + 'mask_diag_len', P + 'mask_diag_wid', ch,
                     P + 'flatd_x', P + 'flatd_y', cz, angle=45))
    node = _cut(doc, tag + 'CutDiag', node,
                _box(doc, tag + 'Diag', P + 'mask_diag_len', P + 'mask_diag_wid', ch,
                     P + 'mask_diag_base', P + 'mask_diag_base', cz, angle=-45))
    half = _cut(doc, tag + 'CutChamfer', node,
                _box(doc, tag + 'Chamfer', P + 'mask_reach', P + 'mask_reach', ch,
                     '-' + P + 'mask_reach', '-' + P + 'mask_reach', cz))

    mirror = _owned(doc, 'Part::Mirroring', tag + 'Mirror')
    mirror.Source = half
    mirror.Normal = V(1, -1, 0)
    mirror.Base = V(0, 0, 0)
    return _fuse(doc, tag + 'Section', half, mirror)


def greeble_socket(doc, tag='', pfx='', base_z='0'):
    """The snap groove: a full revolution, interrupted by a wedge.

    The revolution is four primitives -- bore, expanding cone, rib, contracting cone. The
    wedge is the one polygon here that will not decompose, so it is a sketch.

    `pfx` selects which set of spreadsheet aliases drives it, so the same description can be
    re-evaluated at different arguments. That is exactly what the bulkhead needs: it forms
    its greeble post by cutting with this shape at greeble tolerance ZERO and at
    bulkhead_thickness + 2*eps -- never with the corner's built shape, which carries the fit
    clearance and would apply it a second time. See bulkhead_tree.py.
    """
    P = 'Params.'
    Q = P + pfx
    rev = _fuse(doc, tag + 'NubA',
                _cyl(doc, tag + 'NubBore', Q + 'greeble_radius',
                     Q + 'nub_span', base_z),
                _cone(doc, tag + 'NubRampUp', Q + 'greeble_radius',
                      Q + 'greeble_nub_radius',
                      Q + 'nub_z2 - ' + Q + 'nub_z1', Q + 'nub_z1'))
    rev = _fuse(doc, tag + 'NubB', rev,
                _cyl(doc, tag + 'NubRib', Q + 'greeble_nub_radius',
                     Q + 'nub_z3 - ' + Q + 'nub_z2', Q + 'nub_z2'))
    rev = _fuse(doc, tag + 'NubC', rev,
                _cone(doc, tag + 'NubRampDown', Q + 'greeble_nub_radius',
                      Q + 'greeble_radius',
                      Q + 'nub_z4 - ' + Q + 'nub_z3', Q + 'nub_z3'))

    # the wedge, seeded at the corner's parameters:
    #   (-3.71,-3.7) (3.71,-3.7) (3.71,0) (2.8,-0.8) (-2.9,-0.8) (-3.71,0)
    gnr, eps, gr, gnt, lr, gt = 3.7, 0.01, 2.9, 0.8, 2.0, 0.8
    pts = [(-(gnr + eps), -gnr), (gnr + eps, -gnr), (gnr + eps, 0.0),
           (lr + gt, -gnt), (-gr, -gnt), (-(gnr + eps), 0.0)]
    sk = _sketch(
        doc, tag + 'WedgeProfile', pts,
        horizontals=(0, 3), verticals=(1, 5), on_x=(2, 5),
        dims=[(0, 'X', '-(%sgreeble_nub_radius + %seps)' % (Q, P)),
              (0, 'Y', '-' + Q + 'greeble_nub_radius'),
              (1, 'X', Q + 'greeble_nub_radius + ' + P + 'eps'),
              (3, 'X', P + 'longeron_radius + ' + P + 'greeble_thickness'),
              (3, 'Y', '-' + P + 'greeble_nub_thickness'),
              (4, 'X', '-' + Q + 'greeble_radius')],
        angle=-45, z_expr=Q + 'cut_z0')
    wedge = _prism(doc, tag + 'Wedge', sk, Q + 'through_cut')
    return _cut(doc, tag + 'GrooveTool', rev, wedge)


def end_section(doc, tag, pfx, z0, h, base_z='0'):
    """corner_end: the section, the greeble bore, the mouth, and the interrupted groove.

    Parameterised the same way as greeble_socket, because the bulkhead calls exactly this
    with a different thickness and a zero tolerance.
    """
    P = 'Params.'
    Q = P + pfx
    node = _section(doc, tag, z0, h)
    node = _cut(doc, tag + 'CutGreeble', node,
                _cyl(doc, tag + 'GreebleBore', Q + 'greeble_radius',
                     Q + 'through_cut', Q + 'cut_z0'))
    node = _cut(doc, tag + 'CutMouth', node,
                _box(doc, tag + 'Mouth', Q + 'mouth_w', Q + 'mouth_w',
                     Q + 'through_cut', Q + 'mouth_x', Q + 'mouth_y', Q + 'cut_z0',
                     angle=45))
    return _cut(doc, tag + 'CutGroove', node,
                greeble_socket(doc, tag, pfx, base_z))


def _relief(doc):
    """corner_transition's diagonal relief -- the second sketch, same pattern."""
    P = 'Params.'
    lr, lt, bt, eps, gr = 2.0, 0.05, 6.0, 0.01, 2.9
    pts = [(gr, -eps), (lr + lt, 0.75 * bt + eps), (lr / 2 ** 0.5, bt + eps),
           (-lr / 2 ** 0.5, bt + eps), (-(lr + lt), 0.75 * bt + eps), (-gr, -eps)]
    sk = _sketch(
        doc, 'ReliefProfile', pts,
        horizontals=(2, 5), verticals=(), on_x=(),
        dims=[(0, 'X', P + 'greeble_radius'), (0, 'Y', '-' + P + 'eps'),
              (1, 'X', P + 'longeron_radius + ' + P + 'longeron_tolerance'),
              (1, 'Y', P + 'relief_mid'),
              (2, 'X', P + 'relief_diag'), (2, 'Y', P + 'relief_top'),
              (3, 'X', '-' + P + 'relief_diag'),
              (4, 'X', '-(%slongeron_radius + %slongeron_tolerance)' % (P, P)),
              (4, 'Y', P + 'relief_mid'),
              (5, 'X', '-' + P + 'greeble_radius')],
        angle=0, z_expr='0')
    # OpenSCAD composes this as extrude +z, rotate x 90, rotate z -45, translate. The
    # sketch carries the first rotation as its own placement so the extrusion runs along
    # -y, and the -45 and the translate are applied to the prism.
    sk.Placement = App.Placement(V(0, 0, 0), App.Rotation(V(1, 0, 0), 90))
    prism = _prism(doc, 'Relief', sk, P + 'relief_depth')
    prism.Placement = App.Placement(V(0, 0, 0), App.Rotation(V(0, 0, 1), -45))
    prism.setExpression('Placement.Base.z', P + 'trans_z0 - ' + P + 'eps')
    return prism


def emit(doc, seed=None, extra=()):
    """Create or update the corner's half-length run as a live CSG tree.

    Returns the stable tip. `fuselage_corner` is this mirrored about
    z = unit_length/2 -- see corner_full.py.
    """
    P = 'Params.'
    _SEEN.clear()
    _sheet(doc, extra, seed)

    # --- the end: section, bore, mouth, interrupted groove ---------------------
    # NB: the node names inside end_section() must not collide with _section()'s own --
    # 'EndCutBore' is already the longeron bore, which is why the greeble bore is
    # 'EndCutGreeble'. _owned() asserts this.
    end = end_section(doc, 'End', '', P + 'end_z0', P + 'end_h')

    # --- the transition: section, tapered bore, diagonal relief ----------------
    trans = _section(doc, 'Trans', P + 'trans_z0', P + 'trans_h')
    trans = _cut(doc, 'TransCutCone', trans,
                 _cone(doc, 'TaperBore', P + 'greeble_radius',
                       P + 'longeron_radius + ' + P + 'longeron_tolerance',
                       P + 'trans_h + ' + P + 'eps * 2',
                       P + 'trans_z0 - ' + P + 'eps'))
    trans = _cut(doc, 'TransCutRelief', trans, _relief(doc))

    # --- the middle, and the half ----------------------------------------------
    mid = _section(doc, 'Mid', P + 'mid_z0', P + 'mid_h')

    half = _fuse(doc, 'HalfA', end, trans)
    half = _fuse(doc, 'HalfB', half, mid)

    # the corner is symmetric about mid-span
    mirror = _owned(doc, 'Part::Mirroring', 'MirrorZ')
    mirror.Source = half
    mirror.Normal = V(0, 0, 1)
    mirror.Base = V(0, 0, 0)
    mirror.setExpression('Placement.Base.z', P + 'unit_length')

    whole = _fuse(doc, 'Whole', half, mirror)

    # the stable tip: user features bind here and nowhere else
    tip = _owned(doc, 'Part::Refine', 'Tip')
    tip.Source = whole

    doc.recompute()
    return tip


# The whole part, at the hand driver's values and at the sweep's. `corner_render()` calls
# fuselage_corner and nothing else, so Tip is the deliverable in both cases; only the second
# is a configuration the sweep would produce. The corner had never been checked at the swept
# values until the bulkhead's assembly needed to share a sheet with it.
DRIVER_REFS = [('EndCutGroove', 551.8157396), ('TransCutRelief', 607.6699024),
               ('MidSection', 4041.5795009), ('Tip', 10395.9608969)]
SWEPT_REFS = [('Tip', 14146.8357350)]            # ref_corner_full.scad


def main():
    args = [a for a in sys.argv[1:] if not a.endswith('.py')]
    seed = None
    refs = DRIVER_REFS
    if args:
        import parameters
        # The CORNER table, never the bulkhead's: they differ on greeble_tolerance, 0.05
        # against 0, and that asymmetry is the joint. Seeding this from the bulkhead's would
        # build the bore with no clearance and the snap would be an interference fit.
        seed = parameters.seed(args[0], parameters.CORNER)
        refs = SWEPT_REFS

    doc = App.newDocument('corner_tree')
    tip = emit(doc, seed)

    print('PART:: CSG tree -- fuselage_corner  (%s)'
          % ('swept parameters' if seed else 'hand driver parameters'))
    fail = []
    for name, ref in refs:
        obj = doc.getObject(name)
        v = obj.Shape.Volume
        d = v - ref
        print('  %-16s %13.6f  ref %13.6f  %+10.6f  %+8.4f%%'
              % (name, v, ref, d, 100 * d / ref))
        if abs(d) / ref > 1e-3:
            fail.append('%s off by more than 0.1%%' % name)

    s = tip.Shape
    print('  valid = %s  solids=%d faces=%d' % (s.isValid(), len(s.Solids),
                                                len(s.Faces)))
    print('  nodes = %d generated, %d sketches'
          % (len([o for o in doc.Objects if getattr(o, 'Generator', None)]),
             len([o for o in doc.Objects
                  if o.isDerivedFrom('Sketcher::SketchObject')])))

    if not s.isValid():
        fail.append('invalid shape')
    if len(s.Solids) != 1:
        fail.append('%d solids' % len(s.Solids))

    out = os.path.join(HERE, 'corner_tree.FCStd')
    doc.saveAs(out)
    print('  saved %s' % os.path.basename(out))
    print('  %s' % ('FAIL: ' + '; '.join(fail) if fail else 'ok'))
    return 1 if fail else 0


if is_entry_point(__name__):
    _code = main()
    # freecadcmd tears the interpreter down on SystemExit without flushing stdout.
    sys.stdout.flush()
    sys.exit(_code)
