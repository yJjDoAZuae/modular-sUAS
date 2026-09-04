"""IP-FC-12: the cowls as parametric documents, not baked shapes.

A first pass built these as one `Part::Feature` holding a finished solid. It measured
correctly and was worthless: a corner document carries dozens of expression bindings and
rebuilds when you change a value, and that cowl document carried none. A shape in a `.FCStd`
is an STL with extra steps, and `build_part.py`'s own docstring names that failure.

Everything here is an ordinary `Part::` document object reading the sheet, the same way
`corner_tree` and `plane2d` are. Three things needed establishing before it could be:

* **Composed rotations bind.** Each buttress is a profile stood upright, carried out to the
  body's flank and swung by its own angle, which is a rotation about X composed with a fixed
  quarter turn. `Placement.Rotation.Yaw/Pitch/Roll` accept expressions, and so do
  `Placement.Base.x/y/z` with `sin` and `cos` in them, so the composition is written directly
  rather than baked (verified 2026-08-31).
* **An imported surface can be scaled parametrically.** No `Part::` primitive represents the
  OML, and `Part::Feature` has a placement but no scale -- so a document where changing `U`
  moved every buttress and left the blank at its built size. `Draft::Clone` carries an
  expression-bound `Scale` and recomputes headless, which closes that gap.
* **The buttress placements are sheet rows**, per OQ-DES-CW4 (resolved 2026-08-09: "the full
  fix wants a list of buttress placements"). They are the cowl's structure -- the slots are
  what make the printed wall fold into a rib -- so they are data, not literals in code.

Two nodes here are not stock `Part::` features, and both are that way for a measured reason
rather than a preference. The protected core's pyramid is a `Part::Wedge` because a
`Draft::Clone` scales a shape's *tolerance* along with its geometry (`core()`), and the
cutter's booleans run through `Part.Shape` because the stock ones cannot cut this part at all
(`_ShapeBoolean`). Both still read the sheet, and both still rebuild when a value changes.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import corner_tree as C
import oml_blank

V = App.Vector
P = 'Params.'

# The OML surface is imported in the STEP's own units and scaled from there. 304.8 is what the
# exporter's FOOT label makes a reader apply where the project's convention means 1000 mm --
# see `oml_blank`, which owns that reasoning and the assertion that keeps it honest.
NATIVE_PER_MODEL_UNIT = oml_blank.NATIVE_PER_MODEL_UNIT
_SCALE = '(%(p)sU / %(p)soml_scale_m_per_mm / 304.8)' % {'p': P}

# Where the blank sits after the pitch. The OpenSCAD source translates by `offset_x_m` *before*
# scaling, in the mesh's own frame, so the offset scales with everything else; a placement
# applies its rotation first, so the translation it needs is the pitched, scaled offset. The
# `1 - 2*reversed` term is the pitch's sign: +90 sends model +x to -z, -90 sends it to +z.
_OFFSET_Z = ('(-%(p)soml_offset_x_m * %(p)sU / %(p)soml_scale_m_per_mm '
             '* (1 - 2 * %(p)soml_reversed))' % {'p': P})


class _ScaledSurface(object):
    """The imported OML surface, uniformly scaled from the sheet on every recompute.

    No `Part::` primitive represents the OML, and `Part::Feature` has a placement but no
    scale, so something has to carry the scale for the blank to follow `U`. This was a
    `Draft::Clone`, whose `Scale` is expression-bindable, and then for a while it was not
    parametric at all: the blank was scaled once with `Shape.scale` at build time and frozen,
    on a note claiming a clone rebuilt the B-spline into something the kernel could not
    boolean against.

    That note was wrong. The failures blamed on it were the widened diagonal plate, the
    clone-scaled core's tolerance, and the stock `Part::` booleans -- all since fixed and each
    recorded where it was found. What freezing the blank actually bought was a document whose
    every other feature followed `U` while the body did not, so editing `U` on a saved file
    cut a full-size body with double-size tools: the nose came out invalid at 2.72 times its
    volume where 8 was right, and the tail's tools missed the body altogether and returned
    nothing.

    A scripted feature does the same scaling without pulling in Draft, and recomputes whenever
    `Factor` does.
    """

    def __init__(self, obj, source):
        obj.addProperty('App::PropertyLink', 'Source', 'Blank',
                        'The imported surface, in the units the STEP file states')
        obj.addProperty('App::PropertyFloat', 'Factor', 'Blank',
                        'Uniform scale from those units into the model')
        obj.Source = source
        obj.Proxy = self

    def execute(self, obj):
        if obj.Source is None or not obj.Factor:
            return
        shape = obj.Source.Shape.copy()
        shape.scale(obj.Factor)
        obj.Shape = shape

    def dumps(self):
        return None

    def loads(self, state):
        return None


class _ShapeBoolean(object):
    """A boolean run through `Part.Shape` instead of a stock `Part::` feature.

    **FreeCAD's document booleans return the wrong solid for this part.** Not a coarser one --
    the wrong one. Measured 2026-09-01 on FreeCAD 1.1.1 with byte-identical operands, the same
    half cut by the same cutter:

        Part.Shape.cut        faces=39  valid=True   volume 308777.93   tessellated 297004.19
        Part::Cut             faces=69  valid=False  volume 310563.18   tessellated 232547.58
        PartDesign::Boolean   faces=69  valid=False
        PartDesign::Pocket    (slots in sequence)    invalid at the second diagonal

    The document result is missing 68 mm3 of material the correct one has, carries six invalid
    faces including one whose boundary does not close, and tessellates 22% smaller -- it would
    print wrong, not merely report oddly. All three document routes agree with each other and
    disagree with the geometry API because in FreeCAD 1.1 they share one `TopoShape` layer,
    which logs `TopoShapeExpansion.cpp: hasher mismatch` throughout the operation.

    **Tolerance is the whole cause**, established 2026-09-01 on 1.1.3. An earlier note here said
    it was not, on the grounds that handing `Part::Cut` a cutter cleaned to 1.5e-07 changes
    nothing -- which is true, but only because `Part::Cut` re-applies its own automatic fuzz
    whatever the tool carries. The isolating measurement is the pair: force the *stock* cutter's
    recorded tolerance down and the cut returns 39 faces and valid; force the *clean* cutter's
    up to the stock value and it returns the 69-face invalid solid. The two cutters are the
    same geometry to +/-0.000000 mm3, so nothing but the recorded number separates them.

    The number is proportional to how big the operands are: 7.0e-07 per mm of bounding-box
    diagonal, measured over the six overlapping tools (170.3 mm -> 1.20e-04) and over all eleven
    (371.2 mm -> 2.63e-04). What the cut needs is absolute -- 1.5e-07 exact, 1.0e-06 already 68
    faces and +1565 mm3, nothing working in between -- so a stock-built tool is clean enough
    only if it fits in a box about 0.2 mm across. Nothing stock re-records it either:
    `Part::Refine`, `Part::Mirroring` twice about one plane, and `Draft::Clone` at scale 1 all
    hand back the identical shape at the identical 2.63e-04.

    **The fuzz is a preference, and turning it off makes the stock objects correct.** Set
    `BooleanFuzzy = 0` under `BaseApp/Preferences/Mod/Part/Boolean` and `Part::MultiFuse` records
    2.12e-07 instead of 2.63e-04 and `Part::Cut` returns the reference solid at zero symmetric
    difference; both whole cowls then build from stock objects alone, matching this construction
    exactly (74 faces tail, 64 nose). Two things hid it: an earlier search of the binaries looked
    only for 7-bit ASCII, and the value is read *once at module load* (`AppPart.cpp`), so setting
    the parameter from a running session does nothing. Whether the port adopts that -- it is a
    per-install setting, and a file that silently depends on one fails as a wrong part rather
    than an error -- is alternative 6 of OQ-DES-CW16, which is Alex's call, not this module's.

    **1.1.3 fixes the cut and only the cut.** `PartDesign::Boolean` gains a `FuzzyTolerance`
    property, and at 0 it reproduces the reference solid exactly, zero symmetric difference,
    where auto (-1) still gives the 69-face invalid one. But a cowl is not one cut. PartDesign's
    `Fuse` returns a *compound* rather than a union at every fuzzy value tried -- `Top1` fused
    with `Diag11`, which overlap by 1.1 mm3, comes back as two solids at exactly the sum of
    their volumes -- and its `Common` collapses the mask intersection against the NURBS blank to
    5 faces, +4067.96 mm3, tolerance 19.7 mm. So the cowl gains nothing it can use: the cut it
    would fix still needs a clean fused tool, and nothing stock can build one.

    What the design asks for is two 0.1 mm slots crossing each other inside a B-spline solid,
    which is the hard case for any kernel. The OpenSCAD source gets it free because CGAL meshes
    have no such thing as a curve-intersection tolerance.

    The deployment consequence -- FreeCAD will not restore this class from a document unless
    its module is an addon -- is OQ-DES-CW16, which carries the alternatives.

    **Every boolean in both cowls goes through this**, not only the ones that need it. The
    nose's single octant cut is easy enough that a stock `Part::Cut` survives it, but building
    the two parts by two different mechanisms would mean the path the tail depends on is
    exercised by one part only, and any divergence between them would surface as a geometry
    discrepancy with no obvious cause.

    This stays a first-class document object: it links its operands, recomputes when they or
    the sheet change, and is saved and reloaded like any other node.
    """

    def __init__(self, obj, operation):
        obj.addProperty('App::PropertyLink', 'Base', 'Boolean',
                        'The shape the operation is applied to')
        obj.addProperty('App::PropertyLinkList', 'Tools', 'Boolean',
                        'The shapes applied to it, in order')
        obj.addProperty('App::PropertyEnumeration', 'Operation', 'Boolean',
                        'Which boolean to run')
        obj.Operation = ['cut', 'fuse', 'common']
        obj.Operation = operation
        obj.Proxy = self

    #: The three operations, applied to each tool in turn. `Part.Shape`'s own methods rather
    #: than the `Part::` features', which is the entire point of this class.
    OPS = {'cut': Part.Shape.cut, 'fuse': Part.Shape.fuse, 'common': Part.Shape.common}

    def execute(self, obj):
        if obj.Base is None or not obj.Tools:
            return
        apply = self.OPS[obj.Operation]
        out = obj.Base.Shape
        for tool in obj.Tools:
            out = apply(out, tool.Shape)
        obj.Shape = out

    # FreeCAD 1.x persists a scripted object's proxy through these; there is no state to keep,
    # the operands being ordinary links.
    def dumps(self):
        return None

    def loads(self, state):
        return None


class _CowlShell(object):
    """IP-FC-17: the notched blank with its interior cavity removed.

    A document node rather than a shape computed once and stored, for the reason
    `_ScaledSurface` is one: a cowl document whose wall did not follow `U` would be a document
    that lies about being parametric, and the failure mode is a full-size body carrying a wall
    built at another scale. `cowl_interior` does the geometry; this owns the links and the two
    sheet-bound numbers it needs.

    **`Inset` is `cowl_n_perimeters * extrusion_width` and does not scale with `U`.** The wall
    is what a nozzle lays down, so it is 0.6 mm on a 50 mm cowl and 0.6 mm on a 400 mm one --
    the one dimension on this part that is absolute. Binding it to an expression over two sheet
    rows rather than storing 0.6 keeps that visible in the document.
    """

    def __init__(self, obj):
        obj.addProperty('App::PropertyLink', 'Base', 'Shell',
                        'The notched blank -- the print representation, unchanged')
        obj.addProperty('App::PropertyLink', 'Body', 'Shell',
                        'The same blank before any notch reached it')
        obj.addProperty('App::PropertyLinkList', 'Notches', 'Shell',
                        'The cutting tools, in the symmetry cell they were built in')
        obj.addProperty('App::PropertyStringList', 'Mirrors', 'Shell',
                        'The mirror normals that take that cell out to the whole part')
        obj.addProperty('App::PropertyFloat', 'Inset', 'Shell',
                        'The horizontal inset: cowl_n_perimeters * extrusion_width, in mm')
        obj.addProperty('App::PropertyFloat', 'Overhang', 'Shell',
                        'overhang_angle_from_bed, which P1 is asserted against')
        obj.Proxy = self

    def execute(self, obj):
        import cowl_interior
        if obj.Base is None or obj.Body is None or not obj.Notches or not obj.Inset:
            return
        shapes = [n.Shape for n in obj.Notches]
        for text in obj.Mirrors:
            normal = App.Vector(*[float(v) for v in text.split(',')])
            normal.normalize()
            shapes = shapes + [s.mirror(App.Vector(0, 0, 0), normal) for s in shapes]
        obj.Shape = cowl_interior.shell_solid(
            obj.Base.Shape, obj.Body.Shape, Part.makeCompound(shapes),
            obj.Inset, obj.Overhang)

    def dumps(self):
        return None

    def loads(self, state):
        return None


def _shell(doc, name, tip, body, notches, mirrors):
    """One `_CowlShell`, wired to the tree the print representation already built.

    **The tools are handed over as a compound, not as a fused solid.** `cowl_interior` only
    sections them and reads their vertices, and neither wants a union: overlapping wires at a
    station are what the dilation fuses anyway, per IP-FC-52. Recovering the same set as
    `body - notched` instead was measured at 47 s a part, and leaves a 202-face solid that is
    slower to section than the eleven slabs are.
    """
    node = C._owned(doc, 'Part::FeaturePython', name)
    if getattr(node, 'Proxy', None) is None:
        _CowlShell(node)
    node.Base = tip
    node.Body = body
    node.Notches = list(notches)
    node.Mirrors = ['%g,%g,%g' % m for m in mirrors]
    node.setExpression('Inset', '%(p)scowl_n_perimeters * %(p)sextrusion_width' % {'p': P})
    node.setExpression('Overhang', '%soverhang_angle_from_bed' % P)
    return node


def _shape_bool(doc, name, operation, base, tools):
    """One `_ShapeBoolean` node, created and wired the way `C._cut` wires a `Part::Cut`."""
    node = C._owned(doc, 'Part::FeaturePython', name)
    if getattr(node, 'Proxy', None) is None:
        _ShapeBoolean(node, operation)
    node.Base = base
    node.Tools = list(tools)
    return node


def blank(doc, name, oml_name):
    """The OML surface, scaled and pitched from the sheet.

    `oml_blank.surface` does the import and repairs the tail's folded aft closure
    (OQ-DES-CW13); what is added here is that the result tracks `U` instead of being frozen at
    the size it was built.
    """
    src = doc.getObject('OmlSurface')
    if src is None:
        solid, _repairs = oml_blank.surface(oml_name)
        src = doc.addObject('Part::Feature', 'OmlSurface')
        src.Shape = solid
    node = C._owned(doc, 'Part::FeaturePython', name)
    if getattr(node, 'Proxy', None) is None:
        _ScaledSurface(node, src)
    node.setExpression('Factor', _SCALE)
    node.setExpression('Placement.Base.z', _OFFSET_Z)
    node.setExpression('Placement.Rotation.Pitch',
                       '90 - 180 * %soml_reversed' % P)
    return node


def core(doc, name, body_len_expr):
    """The protected core: the pyramid over its cube, which the buttresses may not reach.

    Subtracted from the *tools*, never from the blank, so it is a region the cuts are forbidden
    to enter rather than material in its own right (Section 6.3). It is the bulkhead interface
    and it is load-bearing.

    **The pyramid is a `Part::Wedge`, not a scaled clone, and that is a correctness matter
    rather than a preference.** A `Draft::Clone` scales a shape's *tolerance* along with its
    geometry, so cloning a unit pyramid up by `unit_width / 2` took the core from OCC's 1e-7 to
    5e-6. Subtracting a core that coarse inflated the cutter's edges to 2.6e-4, and cutting the
    blank with that cutter returned an empty shape -- measured 2026-09-01, with the same tools
    and the same blank, only the core's tolerance differing. A wedge whose top face degenerates
    to a point is the same pyramid, stays at 1e-7, and every dimension still reads the sheet.
    """
    hw = '(%sunit_width / 2)' % P
    pyr = C._owned(doc, 'Part::Wedge', name + 'Pyr')
    for prop, expr in (('Xmin', '-' + hw), ('Xmax', hw),
                       ('Zmin', '-' + hw), ('Zmax', hw),
                       ('Ymin', '0'), ('Ymax', '%sunit_width / 4' % P),
                       ('X2min', '0'), ('X2max', '0'),
                       ('Z2min', '0'), ('Z2max', '0')):
        pyr.setExpression(prop, expr)
    # The wedge tapers along its own +Y, so a quarter turn about X stands it up in +Z.
    pyr.setExpression('Placement.Rotation.Roll', '90')
    pyr.setExpression('Placement.Base.z',
                      '-%s + %sunit_width * %sbuttress_z_offset'
                      % (body_len_expr, P, P))

    cube = C._box(doc, name + 'Cube',
                  '%sunit_width' % P, '%sunit_width' % P, body_len_expr,
                  '-%sunit_width / 2' % P, '-%sunit_width / 2' % P,
                  '-2 * %s + %sunit_width * %sbuttress_z_offset'
                  % (body_len_expr, P, P))
    return _shape_bool(doc, name, 'fuse', pyr, [cube])


# --------------------------------------------------------------------------------
# The cutting tools
# --------------------------------------------------------------------------------

def _val(doc, alias):
    """A sheet value as a plain number, for seeding a sketch."""
    v = doc.getObject('Params').get(alias)
    return float(getattr(v, 'Value', v))


def _seed_points(doc, group):
    """The profile's vertices at the sheet's current values.

    **The seed is not cosmetic.** `_sketch` hands these to the solver as its starting guess,
    and a guess far from the answer can land on a *different* configuration that satisfies
    every constraint -- a crossed polygon, fully constrained, `solve()` returning 0. Seeding
    the nose's profile into the tail's sketch did exactly that: the tail's cuts came out in
    the wrong place and removed a tenth of what they should, with both of `_sketch`'s guards
    reporting healthy. Computing the seed from the same values the constraints use is what
    makes the solver's answer the intended one.
    """
    w = _val(doc, 'unit_width')
    body = (_val(doc, 'U') * _val(doc, 'oml_length_m')
            / _val(doc, 'oml_scale_m_per_mm'))
    z0 = w * _val(doc, 'buttress_z_offset')
    inset = w * _val(doc, 'buttress_r_inset')
    rise = inset * math.tan(math.radians(_val(doc, 'overhang_angle_from_bed')))
    z1 = body - w * _val(doc, group + '_z_end')
    r0 = w * _val(doc, group + '_r_start')
    r1 = w * _val(doc, group + '_r_end')
    return [(-w, z0), (r0, z0), (r0 + inset, z0 + rise),
            (r1 + inset, z1 - rise), (r1, z1), (-w, z1)]


def _buttress_sketch(doc, name, group, body_len_expr):
    """The six-sided cutting profile, every corner driven from the sheet.

    Two of the six carry `r_inset`, and they are why this is not a trapezoid: they step the
    profile inward over a rise of `r_inset * tan(overhang)`, which keeps both ends of the cut
    at or above the angle the part prints at. `overhang_angle_from_bed` is degrees from the bed
    (OQ-DES-CW2), so the tangent is of the angle as written.
    """
    g = P + group + '_'
    rise = ('(%(p)sunit_width * %(p)sbuttress_r_inset '
            '* tan(%(p)soverhang_angle_from_bed))' % {'p': P})
    far = '-%sunit_width' % P
    z0 = '%(p)sunit_width * %(p)sbuttress_z_offset' % {'p': P}
    z1 = '(%s - %sunit_width * %sz_end)' % (body_len_expr, P, g)
    dims = [
        (0, 'X', far),              (0, 'Y', z0),
        (1, 'X', '%sunit_width * %sr_start' % (P, g)), (1, 'Y', z0),
        (2, 'X', '%sunit_width * (%sr_start + %sbuttress_r_inset)' % (P, g, P)),
        (2, 'Y', '%s + %s' % (z0, rise)),
        (3, 'X', '%sunit_width * (%sr_end + %sbuttress_r_inset)' % (P, g, P)),
        (3, 'Y', '%s - %s' % (z1, rise)),
        (4, 'X', '%sunit_width * %sr_end' % (P, g)), (4, 'Y', z1),
        (5, 'X', far),              (5, 'Y', z1),
    ]
    # Seed coordinates only; the constraints above are what place the vertices. Any six points
    # in the right winding will do, and these are the reference configuration's.
    pts = _seed_points(doc, group)
    return C._sketch(doc, name, pts, (), (), (), dims, 0, '0')


def _diag_sketch(doc, name):
    """The diagonal buttress profile -- a plain rectangle, unlike the six-sided one."""
    w = '%sunit_width' % P
    hw = '(%sunit_width / 2)' % P
    d = '%(p)sunit_width * %(p)stop_diag_depth' % {'p': P}
    # The plate is +/-unit_width/2 across, which is the source's own figure. An earlier version
    # here widened it to +/-unit_width on the theory that its edges were landing tangent to the
    # surface; that was wrong, and measured 2026-09-01 the widening is what broke the part --
    # with it, cutting the half returns an empty shape, and without it the same cut is valid.
    # The source's width is not incidental, so it is not a free parameter to widen.
    #
    # The cut's *depth* is `top_diag_depth`, how far in it reaches (2 mm at U = 1).
    dims = [(0, 'X', '-' + w), (0, 'Y', '-' + hw),
            (1, 'X', d),       (1, 'Y', '-' + hw),
            (2, 'X', d),       (2, 'Y', hw),
            (3, 'X', '-' + w), (3, 'Y', hw)]
    uw = _val(doc, 'unit_width')
    depth = uw * _val(doc, 'top_diag_depth')
    pts = [(-uw, -uw / 2.0), (depth, -uw / 2.0), (depth, uw / 2.0), (-uw, uw / 2.0)]
    return C._sketch(doc, name, pts, (), (), (), dims, 0, '0')


def _slab(doc, name, sketch):
    """The sketch extruded symmetrically through the cut thickness.

    Symmetric because the source's `linear_extrude(center = true)` is, and the thickness is
    `buttress_cut_thickness` with the doubling already folded in (OQ-DES-CW8) -- so it is the
    whole cut, not a half.
    """
    ext = C._owned(doc, 'Part::Extrusion', name)
    ext.Base = sketch
    ext.DirMode = 'Normal'
    ext.Solid = True
    ext.setExpression('LengthFwd', '%sbuttress_cut_thickness / 2' % P)
    ext.setExpression('LengthRev', '%sbuttress_cut_thickness / 2' % P)
    return ext


def _place(node, base, ypr):
    for prop, expr in zip(('Placement.Base.x', 'Placement.Base.y', 'Placement.Base.z'), base):
        node.setExpression(prop, expr)
    for prop, expr in zip(('Placement.Rotation.Yaw', 'Placement.Rotation.Pitch',
                           'Placement.Rotation.Roll'), ypr):
        node.setExpression(prop, expr)
    return node


def side_buttress(doc, name, group, ang, dx, body_len_expr):
    """`rotate([0,0,-90]) translate([-w/2,0,-L]) rotate([ang,0,0]) rotate([90,0,0])`.

    Composed into one placement rather than nested, because a placement is what a document
    object has. The quarter turn about Z carries the whole assembly onto the flank, so it also
    carries the translation: `(-w/2, 0, -L)` becomes `(0, w/2, -L)`.
    """
    slab = _slab(doc, name + 'Slab', _buttress_sketch(doc, name + 'Prof', group,
                                                      body_len_expr))
    return _place(slab,
                  (dx, '%sunit_width / 2' % P, '-' + body_len_expr),
                  ('-90', '0', '%s + 90' % ang))


def top_buttress(doc, name, group, ang, dy, body_len_expr):
    """`rotate([ang,0,0]) translate([-w/2,0,-L]) rotate([90,0,0])`.

    Here the swing is applied *after* the translation, so it carries the offset round with it
    -- which is where the sine and cosine in the position come from.
    """
    slab = _slab(doc, name + 'Slab', _buttress_sketch(doc, name + 'Prof', group,
                                                      body_len_expr))
    return _place(slab,
                  ('-%sunit_width / 2' % P,
                   '%s + %s * sin(%s)' % (dy, body_len_expr, ang),
                   '-%s * cos(%s)' % (body_len_expr, ang)),
                  ('0', '0', '%s + 90' % ang))


def bottom_buttress(doc, name, group, ang, dy, body_len_expr):
    """`rotate([ang,0,0]) rotate([0,0,180]) translate([-w/2,0,-L]) rotate([90,0,0])`.

    The half turn about Z before the translation flips it to the underside, and composing the
    three rotations gives yaw 180 with roll `90 - ang` -- not `ang + 90`, because the half turn
    reverses the swing's sense.
    """
    slab = _slab(doc, name + 'Slab', _buttress_sketch(doc, name + 'Prof', group,
                                                      body_len_expr))
    return _place(slab,
                  ('%sunit_width / 2' % P,
                   '%s + %s * sin(%s)' % (dy, body_len_expr, ang),
                   '-%s * cos(%s)' % (body_len_expr, ang)),
                  ('180', '0', '90 - %s' % ang))


def diag_buttress(doc, name, ang, z_expr):
    """`rotate([ang,0,0]) translate([-w/2,0,0])` -- and no upright quarter turn, unlike the
    others, because this profile is already extruded in the direction it cuts."""
    slab = _slab(doc, name + 'Slab', _diag_sketch(doc, name + 'Prof'))
    return _place(slab, ('-%sunit_width / 2' % P, '0', z_expr), ('0', '0', ang))


# --------------------------------------------------------------------------------
# The masks, and the parts
# --------------------------------------------------------------------------------

# `U * oml_length_m / oml_scale_m_per_mm` -- the cowl's length in millimetres. Written as an
# expression rather than a number so a document rebuilt at another U follows it.
BODY_LEN = '(%(p)sU * %(p)soml_length_m / %(p)soml_scale_m_per_mm)' % {'p': P}


def _mirror(doc, name, source, normal):
    """`Part::Mirroring` -- OpenSCAD's `mirror(v)`, as a document object."""
    node = C._owned(doc, 'Part::Mirroring', name)
    node.Source = source
    node.Normal = App.Vector(*normal)
    node.Base = App.Vector(0, 0, 0)
    return node


def _mirror_union(doc, tag, source, normal):
    return _shape_bool(doc, tag, 'fuse', source,
                       [_mirror(doc, tag + 'M', source, normal)])


def lower_mask(doc, name):
    """Everything aft of `cut_len`: the cowl's own extent."""
    w = '%sunit_width' % P
    return C._box(doc, name, '2 * ' + w, '2 * ' + w,
                  '%s - %sunit_width * %scut_len' % (BODY_LEN, P, P),
                  '-' + w, '-' + w, '-' + BODY_LEN)


def upper_mask(doc, name):
    """Everything forward of `cut_len`: what the nose tip is made from."""
    w = '%sunit_width' % P
    return C._box(doc, name, '2 * ' + w, '2 * ' + w,
                  '%(p)sunit_width * %(p)scut_len' % {'p': P},
                  '-' + w, '-' + w, '-%(p)sunit_width * %(p)scut_len' % {'p': P})


def half_mask(doc, name):
    w = '%sunit_width' % P
    return C._box(doc, name, '2 * ' + w, w, '3 * ' + BODY_LEN,
                  '-' + w, '0', '-2.5 * ' + BODY_LEN)


def octant_mask(doc, name):
    """The eighth the nose cowl is built in: a triangle, so a sketch rather than a box."""
    w = '%sunit_width' % P
    dims = [(0, 'X', '0'), (0, 'Y', '0'),
            (1, 'X', w),   (1, 'Y', w),
            (2, 'X', '0'), (2, 'Y', w)]
    uw = _val(doc, 'unit_width')
    sk = C._sketch(doc, name + 'Prof', [(0.0, 0.0), (uw, uw), (0.0, uw)],
                   (), (), (), dims, 0, '-2.5 * ' + BODY_LEN)
    ext = C._owned(doc, 'Part::Extrusion', name)
    ext.Base = sk
    ext.DirMode = 'Normal'
    ext.Solid = True
    ext.setExpression('LengthFwd', '3 * ' + BODY_LEN)
    return ext


def _common(doc, name, base, tool):
    return _shape_bool(doc, name, 'common', base, [tool])


#: What the shelled kinds need out of a built cowl and cannot recover from the tip alone: the
#: un-notched body, the cutting tools in the cell they were built in, and the mirrors that take
#: that cell out to the whole part. Recorded by the builders rather than looked up by node name
#: afterwards, because a name is a coincidence and this is the actual wiring -- a lookup that
#: silently found nothing would shell a cowl with no notches in it, which is a plausible solid
#: and the wrong part.
_PIECES = {}


def pieces(doc):
    """`(body, tools, mirrors)` for the cowl just built into `doc`."""
    if doc.Name not in _PIECES:
        raise KeyError('no cowl has been built into %r' % doc.Name)
    return _PIECES[doc.Name]


def nose_cowl(doc):
    """One octant, one buttress cut, taken out to the whole part by three mirrors.

    Built with the same nodes as `tail_cowl` -- the masks, the cut and the mirror unions are
    all `_ShapeBoolean`. The nose's single cut is easy enough that a stock `Part::Cut` happens
    to survive it, but two cowls built by two different mechanisms is a trap: the one that is
    never exercised is the one that breaks later, and a difference between them would show up
    as a geometry discrepancy nobody could place.
    """
    body = blank(doc, 'Blank', 'vsp_nose')
    lower = _common(doc, 'Lower', body, lower_mask(doc, 'LowerMask'))
    octant = _common(doc, 'Octant', lower, octant_mask(doc, 'OctantMask'))
    tool = side_buttress(doc, 'Butt', 'buttress', '%sbutt_angle' % P, '0', BODY_LEN)
    cut = _shape_bool(doc, 'OctantCut', 'cut', octant, [tool])

    # `mirror_x(mirror_y(mirror_xy(...)))`, and the order matters: the diagonal runs first, so
    # it acts on the octant alone rather than on an already-doubled quadrant.
    _PIECES[doc.Name] = (lower, [tool], [(1, -1, 0), (0, -1, 0), (-1, 0, 0)])

    quad = _mirror_union(doc, 'Diag', cut, (1, -1, 0))
    half = _mirror_union(doc, 'HalfY', quad, (0, -1, 0))
    return _mirror_union(doc, 'NoseCowl', half, (-1, 0, 0))


def tail_cowl(doc):
    """One half, eleven buttress cuts in a single fused cutter, mirrored in y.

    Each of the eleven tools has the protected core taken out of it, and the half is then cut
    by each in turn. **They are deliberately not fused first**, which is what the source does
    and what this did until 2026-09-01. Fusing the six overlapping tools -- `Top1`, `Top2` and
    the four diagonals -- produces a solid that removes *nothing* at `U` = 1: measured
    tessellated, the fused tree takes out 213.044 mm3 where 304.564 is right, silently losing
    the whole group's 91.5 mm3, while at `U` = 4 the same fuse is very nearly correct. It fails
    at the small end, not the large one. Cut individually the six all behave, and the part then
    agrees with the OpenSCAD reference to +0.0035% at every swept `U` (OQ-DES-CW17).

    A note here previously recorded that cutting by that group's union reproduces the reference
    exactly. It does -- but the reference it was checked against is the baked document, which
    carries the same omission.

    Two further things had to be right before it would build, and both were found by
    measurement rather than argument (2026-09-01):

    * **The booleans run through `Part.Shape`, not `Part::Cut`.** `_ShapeBoolean` records what
      each stock arrangement did and why none of them worked.
    * **The protected core is a `Part::Wedge`, not a scaled clone.** `core()` records why: a
      clone scales tolerance along with geometry, and a core fifty times coarser than OCC's
      floor was by itself enough to turn the final cut into an empty shape.

    An earlier version here fused the tools into six connected groups instead, on the belief
    that a lone 0.1 mm slab could not cut this blank at all. It can -- one side buttress cuts
    in 0.4 s, and the intersection volume is exactly linear in tool thickness from 0.1 mm to
    5 mm. That false result came from a harness that had seeded `OmlSurface` from the
    80,000-facet STL rather than the 12-face STEP surface, so it measured the mesh and
    reported it as the surface.

    The core comes out of each tool before any of it reaches the blank, never out of the blank
    afterwards: that makes it a region the cuts may not enter, and reversing it would give a
    different part wherever a cut crosses its boundary.
    """
    body = blank(doc, 'Blank', 'vsp_tail')
    lower = _common(doc, 'Lower', body, lower_mask(doc, 'LowerMask'))
    half = _common(doc, 'Half', lower, half_mask(doc, 'HalfMask'))

    sides = [side_buttress(doc, 'Side%d' % i, 'side', '%sside%d_angle' % (P, i),
                           '%sside%d_x' % (P, i), BODY_LEN) for i in (1, 2, 3)]
    tops = [top_buttress(doc, 'Top%d' % i, 'top', '%stop%d_angle' % (P, i),
                         '%stop%d_y' % (P, i), BODY_LEN) for i in (1, 2)]
    bottoms = [bottom_buttress(doc, 'Bot%d' % i, 'bottom', '%sbottom%d_angle' % (P, i),
                               '%sbottom%d_y' % (P, i), BODY_LEN) for i in (1, 2)]
    diags = []
    for i in (1, 2):
        z = ('-%s + %sunit_width * %stop_diag_z_start + %s' % (BODY_LEN, P, P,
             ('0' if i == 1 else '%sunit_width * sin(30)' % P)))
        for j, sign in ((1, ''), (2, '-')):
            diags.append(diag_buttress(doc, 'Diag%d%d' % (i, j),
                                       '%s%stop_diag_angle' % (sign, P), z))

    # The source's own order: the sides, then each top with the bottom that shares its angle,
    # then the diagonals. Kept because it is the order the working reference cuts in, and
    # because sequential cuts are order-independent only in exact arithmetic.
    tools = sides + [tops[0], bottoms[0], tops[1], bottoms[1]] + diags

    protected = core(doc, 'Core', BODY_LEN)
    # One `Safe` per tool rather than one for a fused cutter. `_ShapeBoolean.execute` applies
    # its operation over `Tools` in order, so the single `Cut` node below is eleven successive
    # cuts and not a multi-argument one.
    safes = [_shape_bool(doc, t.Name.replace('Slab', 'Safe'), 'cut', t, [protected])
             for t in tools]
    # **The safes, not the raw slabs.** The core is a region the cuts may not enter, so the
    # material actually removed is the tool minus the core; handing the shell the slabs would
    # dilate a notch the part does not have, right where the bulkhead interface is.
    _PIECES[doc.Name] = (lower, safes, [(0, -1, 0)])

    cut = _shape_bool(doc, 'Cut', 'cut', half, safes)
    return _mirror_union(doc, 'TailCowl', cut, (0, -1, 0))


def nose_cowl_shell(doc):
    """IP-FC-17: the nose cowl's solid representation. Serves UC-2, UC-3, UC-4, UC-7, UC-8."""
    tip = nose_cowl(doc)
    body, tools, mirrors = pieces(doc)
    return _shell(doc, 'NoseCowlShell', tip, body, tools, mirrors)


def tail_shell(doc):
    """IP-FC-17: the tail cowl's solid representation. Serves UC-2, UC-3, UC-4, UC-7, UC-8."""
    tip = tail_cowl(doc)
    body, tools, mirrors = pieces(doc)
    return _shell(doc, 'TailShell', tip, body, tools, mirrors)


# --------------------------------------------------------------------------------
# The sheet
# --------------------------------------------------------------------------------
#
# Two kinds of row, and the difference is which of them is a *relationship*.
#
# The design values -- radii, end positions, the cut thickness -- come from the cowl's JSON
# shape file, where they are fractions of `unit_width`. The sheet holds the fraction and the
# geometry multiplies, which is what makes `U` alone sufficient: a document whose rows were
# absolute millimetres would put its ribs where they were built when someone changed U.
#
# The **placements** are relationships and are written as expressions, because the source
# states them that way in the geometry itself (`translate([-unit_width*0.30, 0, 0])`). This is
# OQ-DES-CW4's "list of buttress placements" -- the ribs are the cowl's structure, so where
# they sit is data on the sheet rather than a literal in code.
_OML_ROWS = [('oml_scale_m_per_mm', 1e-3), ('oml_length_m', 0.05),
             ('oml_offset_x_m', 0.0), ('oml_reversed', 0.0)]

PARAMS_NOSE_COWL = [
    ('U', 1.0), ('unit_width', '=U * 100'), ('overhang_angle_from_bed', 35.0),
    ('cut_len', 0.06), ('buttress_cut_thickness', 0.1), ('buttress_z_offset', 0.02),
    ('buttress_r_inset', 0.03), ('buttress_r_start', 0.0), ('buttress_r_end', 0.066),
    # Derived in the source, so derived here: `buttress_z_end = cut_len + buttress_z_offset`.
    ('buttress_z_end', '=cut_len + buttress_z_offset'),
    ('butt_angle', 0.0),
] + _OML_ROWS

PARAMS_TAIL = [
    ('U', 1.0), ('unit_width', '=U * 100'), ('overhang_angle_from_bed', 35.0),
    ('cut_len', 0.0), ('buttress_cut_thickness', 0.1), ('buttress_z_offset', 0.02),
    ('buttress_r_inset', 0.05),
    ('side_z_end', 0.25), ('side_r_start', 0.0), ('side_r_end', 0.233),
    ('top_z_end', 0.03), ('top_r_start', 0.0), ('top_r_end', 0.0),
    ('bottom_z_end', 0.2), ('bottom_r_start', 0.0), ('bottom_r_end', 0.288),
    ('top_diag_z_start', 0.2), ('top_diag_depth', 0.02), ('top_diag_angle', 30.0),
    # The eleven placements.
    ('side1_angle', 5.0),    ('side1_x', '=-unit_width * 0.30'),
    ('side2_angle', 12.5),   ('side2_x', 0.0),
    ('side3_angle', 20.0),   ('side3_x', '=unit_width * 0.30'),
    ('top1_angle', 15.0),    ('top1_y', '=unit_width * 0.07'),
    ('top2_angle', 0.0),     ('top2_y', 0.0),
    ('bottom1_angle', 15.0), ('bottom1_y', '=unit_width * 0.07'),
    ('bottom2_angle', 0.0),  ('bottom2_y', 0.0),
] + [('oml_scale_m_per_mm', 1e-3), ('oml_length_m', 0.1),
     ('oml_offset_x_m', -0.25), ('oml_reversed', 1.0)]


def _as_cells(rows):
    """Sheet cells are text. A literal is written as `repr(float(v))` for the same reason
    `parameters.rows()` does it -- the sweep compares definition files byte for byte, so a
    float that formats differently between runs would re-render parts that did not change."""
    return [(alias, value if isinstance(value, str) else repr(float(value)))
            for alias, value in rows]


# The shelled kinds are the print kinds plus the two rows the wall is made of, and nothing
# else -- the shape is the same shape. **They are separate sheets rather than two more rows on
# the existing ones** because a row a part's geometry does not read is a row `check_unseeded`
# is right to complain about, and because adding them to `PARAMS_NOSE_COWL` would change the
# definition file of every already-verified `nose_cowl` in the sweep and re-render all of them
# to produce byte-different files describing identical parts.
#
# `extrusion_width` and `cowl_n_perimeters` are **absolute**, unlike every other length on
# these sheets, which are fractions of `unit_width`. A nozzle does not scale with the airframe.
_WALL_ROWS = [('cowl_n_perimeters', 1.0), ('extrusion_width', 0.6)]

PARAMS_NOSE_COWL_SHELL = PARAMS_NOSE_COWL + _WALL_ROWS
PARAMS_TAIL_SHELL = PARAMS_TAIL + _WALL_ROWS

PARAMS_NOSE_COWL = _as_cells(PARAMS_NOSE_COWL)
PARAMS_TAIL = _as_cells(PARAMS_TAIL)
PARAMS_NOSE_COWL_SHELL = _as_cells(PARAMS_NOSE_COWL_SHELL)
PARAMS_TAIL_SHELL = _as_cells(PARAMS_TAIL_SHELL)


def emit(doc, seed, params, builder):
    """Build one cowl into `doc` and return its tip, the way `build_part.py` expects.

    `_SEEN` is cleared first for the reason `boom_bulkhead.emit` clears it: it is a per-build
    registry of node names, and a second part built in the same process collides with the
    first's.
    """
    import corner_common
    C._SEEN.clear()
    corner_common.build_sheet(doc, params, seed)
    tip = builder(doc)
    doc.recompute()
    return tip
