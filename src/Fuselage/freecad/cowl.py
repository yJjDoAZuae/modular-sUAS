"""IP-FC-12: the nose and tail cowls, ported from `scad/cowl_geometry.scad`.

A cowl is the OML blank with material cut away: `oml_blank` supplies the blank as a B-rep
solid, this module supplies the cutting tools and the boolean tree. Nothing here builds a
wall. **The cowls print in spiral vase mode and that capability is kept** (DES-12,
doc/design/cowl.md section 6.4): vase mode spirals a single contour per layer and admits no
interior geometry at all, so a cowl given a modelled inner surface is no longer vase-mode
printable, and nothing in the geometry would flag it -- the STL would look better and slice
worse. The notched blank this module produces *is* the print representation. Shelling is a
separate downstream operation for the other use cases (IP-FC-16), never a replacement.

**The buttresses are cutting tools, not ribs** (section 4). Each one is a thin prism swept
through the blank, and the rib the printed part ends up with is what the single wall does as
it follows the notch in and back out again. So a buttress that looks too thin to be structure
is not a mistake: `buttress_cut_thickness` is the *cut*, and it is deliberately 0.1 mm and
unscaled by unit_width (OQ-DES-CW3, OQ-DES-CW8).

**Both cowls are built from one octant or half and mirrored**, exactly as the source does,
because the OML is symmetric and the buttress placements are stated for one sector only. The
nose is an octant taken out to the full shape; the tail is a half mirrored in y.

Values in the cowl parameter files are fractions of `unit_width` -- `cut_len` of 0.06 is 6 mm
at U = 1 -- with a short list of exceptions that are absolute or in other units entirely. The
scaling is `derived_cowl_parameters()`'s job, not this module's: what arrives here is already
in millimetres, except the three `oml.*_m` fields, which are metres and say so (OQ-DES-CW1).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import oml_blank
from corner_common import is_entry_point, prism

# The parameter rows each cowl part's sheet carries, as (alias, value).
#
# Every row is a literal rather than a relationship, which is the opposite of `corner_tree`'s
# choice and is deliberate. A cowl's dimensions are fractions of `unit_width` *in the
# parameter file*, and `derived_cowl_parameters()` is where that scaling is applied and
# documented; restating those fractions here as expressions would put the same design decision
# in two places, and the one that moved would win silently. `U` and `unit_width` are both
# carried so a reader of a generated document can see the size it was built at.
#
# **The geometry does not yet read these rows through expressions.** It is built from the seed
# and the sheet records it, where the corner and bulkhead sheets actually drive their features.
# So a cowl document is inspectable but not yet re-solvable by editing `U` -- that is the
# remaining half of IP-FC-12 and it is a genuine gap, not a simplification.
_OML = [('oml_scale_m_per_mm', 1e-3), ('oml_length_m', 0.05),
        ('oml_offset_x_m', 0.0), ('oml_reversed', 0.0)]
_COMMON = [('U', 1.0), ('unit_width', 100.0), ('overhang_angle_from_bed', 35.0)]

PARAMS_NOSE_COWL = _COMMON + _OML + [
    ('cut_len', 6.0), ('buttress_cut_thickness', 0.1), ('buttress_z_offset', 2.0),
    ('buttress_r_start', 0.0), ('buttress_r_end', 6.6), ('buttress_r_inset', 3.0)]

PARAMS_TAIL = _COMMON + [('oml_scale_m_per_mm', 1e-3), ('oml_length_m', 0.1),
                         ('oml_offset_x_m', -0.25), ('oml_reversed', 1.0)] + [
    ('cut_len', 0.0), ('buttress_cut_thickness', 0.1), ('buttress_z_offset', 2.0),
    ('buttress_r_inset', 5.0),
    ('side_z_end', 25.0), ('side_r_start', 0.0), ('side_r_end', 23.3),
    ('top_z_end', 3.0), ('top_r_start', 0.0), ('top_r_end', 0.0),
    ('bottom_z_end', 20.0), ('bottom_r_start', 0.0), ('bottom_r_end', 28.8),
    ('top_diag_z_start', 20.0), ('top_diag_depth', 2.0)]

PARAMS_NOSE_TIP = _COMMON + _OML + [
    ('cut_len', 6.0), ('nose_flange_height', 1.0), ('nose_flange_inset', 0.5),
    ('plate_diam', 60.0), ('plate_thickness', 0.8), ('plate_tol', 0.1)]

PARAMS_NOSE_PLATE = [('U', 1.0), ('overhang_angle_from_bed', 35.0),
                     ('plate_diam', 60.0), ('plate_thickness', 0.8),
                     ('plate_flange_height', 1.0), ('plate_flange_width', 2.0)]


def from_flat(seed):
    """The nested form the builders take, from the flat sheet the sweep exports.

    The OML fields are grouped because they travel together and because three of them are
    metres while everything around them is millimetres -- keeping them under one key is what
    makes `oml['offset_x_m']` read as metres at the point of use (OQ-DES-CW1).
    """
    p = {k: v for k, v in seed.items() if not k.startswith('oml_')}
    if any(k.startswith('oml_') for k in seed):
        p['oml'] = {'scale_m_per_mm': seed['oml_scale_m_per_mm'],
                    'length_m': seed['oml_length_m'],
                    'offset_x_m': seed['oml_offset_x_m'],
                    'reversed': bool(seed['oml_reversed'])}
    return p


def emit_part(doc, seed, params, builder, name):
    """Build one cowl part into `doc`, and return its tip node.

    The shape is wrapped in a `Part::Feature` rather than left loose because `build_part.py`
    reads `tip.Shape` and saves the document: a part that exists only as a Python value would
    produce a mesh and an empty `.FCStd`, which is the artifact this backend exists for.
    """
    from corner_common import build_sheet
    build_sheet(doc, params, seed)
    shape, repairs = builder(from_flat(seed) if seed else _reference_for(params))
    feature = doc.addObject('Part::Feature', name)
    feature.Shape = shape
    doc.recompute()
    return feature


def _reference_for(params):
    return from_flat(dict(params))


def _mirror(shape, normal):
    """OpenSCAD's `mirror(normal)` -- reflection in the plane through the origin."""
    return shape.mirror(App.Vector(0, 0, 0), App.Vector(*normal))


def _fuse(shapes):
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    return out


def mirror_y(shape):
    """`shape` united with its reflection in y, as `shape_modifier_utils.mirror_y`."""
    return shape.fuse(_mirror(shape, (0, -1, 0)))


def octant_to_full(shape):
    """One octant taken out to the whole part.

    `mirror_x(mirror_y(mirror_xy(shape)))` in the source, and the order matters: the diagonal
    mirror runs first, so it acts on the octant alone rather than on an already-doubled
    quadrant. `mirror([1, -1, 0])` reflects in the plane whose normal is that vector, which
    maps (x, y) to (y, x) -- the diagonal, not either axis.
    """
    out = shape.fuse(_mirror(shape, (1, -1, 0)))
    out = out.fuse(_mirror(out, (0, -1, 0)))
    return out.fuse(_mirror(out, (-1, 0, 0)))


# --------------------------------------------------------------------------------
# The cutting tools
# --------------------------------------------------------------------------------

def buttress_shape(unit_width, body_len, z_end, z_offset, r_start, r_end, r_inset,
                   overhang_angle_from_bed):
    """The buttress cutting profile, in the plane it is extruded from.

    Six points, and the two carrying `r_inset` are the reason it is not a simple trapezoid:
    they step the profile inward by `r_inset` over a rise of `r_inset * tan(angle)`, which is
    what keeps both ends of the cut at or above the overhang angle so the notch prints without
    support. `overhang_angle_from_bed` is degrees from the bed (OQ-DES-CW2), so the tangent is
    taken of the angle as given.
    """
    rise = r_inset * math.tan(math.radians(overhang_angle_from_bed))
    return [
        (-unit_width, z_offset),
        (r_start, z_offset),
        (r_start + r_inset, z_offset + rise),
        (r_end + r_inset, body_len - z_end - rise),
        (r_end, body_len - z_end),
        (-unit_width, body_len - z_end),
    ]


def diag_buttress_shape(unit_width, buttress_depth):
    """The diagonal buttress profile -- a plain rectangle, unlike `buttress_shape`."""
    return [
        (-unit_width, -unit_width / 2.0),
        (buttress_depth, -unit_width / 2.0),
        (buttress_depth, unit_width / 2.0),
        (-unit_width, unit_width / 2.0),
    ]


def _extruded(points, thickness):
    """`linear_extrude(height=thickness, center=true)` of a 2D profile."""
    return prism(points, -thickness / 2.0, thickness)


def _rot_x(shape, degrees):
    out = shape.copy()
    out.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), degrees)
    return out


def _rot_z(shape, degrees):
    out = shape.copy()
    out.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), degrees)
    return out


def _moved(shape, x=0.0, y=0.0, z=0.0):
    out = shape.copy()
    out.translate(App.Vector(x, y, z))
    return out


def top_buttress(ang, unit_width, tail_len, cut_thickness, z_end, z_offset,
                 r_start, r_end, r_inset, overhang_angle_from_bed):
    """`rotate([ang,0,0]) translate([-w/2,0,-tail_len]) rotate([90,0,0]) extrude(profile)`.

    OpenSCAD applies its transforms innermost-first, so the profile is stood upright, moved
    out to the part's flank and down to its aft end, and only then swung by `ang`.
    """
    shape = _extruded(buttress_shape(unit_width, tail_len, z_end, z_offset,
                                     r_start, r_end, r_inset, overhang_angle_from_bed),
                      cut_thickness)
    shape = _rot_x(shape, 90.0)
    shape = _moved(shape, x=-unit_width / 2.0, z=-tail_len)
    return _rot_x(shape, ang)


def top_diag_buttress(ang, unit_width, cut_thickness, depth):
    shape = _extruded(diag_buttress_shape(unit_width, depth), cut_thickness)
    shape = _moved(shape, x=-unit_width / 2.0)
    return _rot_x(shape, ang)


def side_buttress(ang, unit_width, body_len, cut_thickness, z_end, z_offset,
                  r_start, r_end, r_inset, overhang_angle_from_bed):
    """As `top_buttress`, with the whole thing then swung a quarter turn onto the side."""
    shape = _extruded(buttress_shape(unit_width, body_len, z_end, z_offset,
                                     r_start, r_end, r_inset, overhang_angle_from_bed),
                      cut_thickness)
    shape = _rot_x(shape, 90.0)
    shape = _rot_x(shape, ang)
    shape = _moved(shape, x=-unit_width / 2.0, z=-body_len)
    return _rot_z(shape, -90.0)


def bottom_buttress(ang, unit_width, body_len, cut_thickness, z_end, z_offset,
                    r_start, r_end, r_inset, overhang_angle_from_bed):
    """As `top_buttress`, turned to face the other way before being swung by `ang`."""
    shape = _extruded(buttress_shape(unit_width, body_len, z_end, z_offset,
                                     r_start, r_end, r_inset, overhang_angle_from_bed),
                      cut_thickness)
    shape = _rot_x(shape, 90.0)
    shape = _moved(shape, x=-unit_width / 2.0, z=-body_len)
    shape = _rot_z(shape, 180.0)
    return _rot_x(shape, ang)


def pyramid(unit_width, tail_len, z_offset):
    """The protected core: a pyramid over a cube, and the bulkhead interface.

    This is *subtracted from the buttress tools*, not from the blank -- so it is a region the
    buttresses are forbidden to reach rather than material in its own right. It is
    load-bearing (section 6.3): the buttress cuts stopping short of it is what leaves the cowl
    something to seat on.
    """
    half = unit_width / 2.0
    apex = unit_width / 4.0
    base = [App.Vector(half, half, 0), App.Vector(half, -half, 0),
            App.Vector(-half, -half, 0), App.Vector(-half, half, 0)]
    faces = [Part.Face(Part.makePolygon(base + [base[0]]))]
    tip = App.Vector(0, 0, apex)
    for i in range(4):
        a, b = base[i], base[(i + 1) % 4]
        faces.append(Part.Face(Part.makePolygon([a, b, tip, a])))
    shell = Part.Shell(faces)
    shell.sewShape()
    tip_solid = Part.makeSolid(shell)
    tip_solid.translate(App.Vector(0, 0, -tail_len + z_offset))

    box = Part.makeBox(unit_width, unit_width, tail_len,
                       App.Vector(-half, -half, -2 * tail_len + z_offset))
    return tip_solid.fuse(box)


# --------------------------------------------------------------------------------
# The blank, and the masks that cut it down
# --------------------------------------------------------------------------------

def _square_prism(unit_width, z0, height):
    """`linear_extrude` of the source's oversized square -- 2*unit_width on a side.

    Deliberately larger than the part: these masks select a *range of z*, and the square is
    only there because a 2D profile has to have some extent.
    """
    w = unit_width
    return prism([(w, w), (-w, w), (-w, -w), (w, -w)], z0, height)


def right_half_mask(unit_width, body_len):
    w = unit_width
    return prism([(w, 0), (w, w), (-w, w), (-w, 0)], -body_len - 1.5 * body_len,
                 3 * body_len)


def octant_mask(unit_width, body_len):
    w = unit_width
    return prism([(0, 0), (w, w), (0, w)], -body_len - 1.5 * body_len, 3 * body_len)


def body_blank_full(name, U, oml):
    solid, repairs = oml_blank.blank(name, U, oml['scale_m_per_mm'],
                                     oml['offset_x_m'], oml['reversed'])
    return solid, repairs


def body_len_of(U, oml):
    """`U * oml_length_m / oml_scale_m_per_mm` -- the blank's length in millimetres."""
    return U * oml['length_m'] / oml['scale_m_per_mm']


def body_blank_full_lower(blank, unit_width, body_len, cut_len):
    """Everything aft of `cut_len`: the cowl's own extent."""
    return blank.common(_square_prism(unit_width, -body_len, body_len - cut_len))


def body_blank_full_upper(blank, unit_width, cut_len):
    """Everything forward of `cut_len`: what the nose tip is made from."""
    return blank.common(_square_prism(unit_width, -cut_len, cut_len))


# --------------------------------------------------------------------------------
# The parts
# --------------------------------------------------------------------------------

def nose_cowl(p):
    """The nose cowl: one octant, one side buttress, taken out to the full shape."""
    blank, repairs = body_blank_full('vsp_nose', p['U'], p['oml'])
    unit_width, U = p['unit_width'], p['U']
    body_len = body_len_of(U, p['oml'])
    cut_len = p['cut_len']

    lower = body_blank_full_lower(blank, unit_width, body_len, cut_len)
    octant = lower.common(octant_mask(unit_width, body_len))

    tool = side_buttress(0.0, unit_width, body_len, p['buttress_cut_thickness'],
                         cut_len + p['buttress_z_offset'], p['buttress_z_offset'],
                         p['buttress_r_start'], p['buttress_r_end'], p['buttress_r_inset'],
                         p['overhang_angle_from_bed'])
    return octant_to_full(octant.cut(tool)), repairs


def tail_cowl(p):
    """The tail cowl: one half, eleven buttress cuts, mirrored in y.

    The buttress tools are unioned and then have the protected core taken *out of them*
    before any of it reaches the blank, which is what stops the cuts eating the bulkhead
    interface. Building it the other way round -- cutting the blank and then adding the core
    back -- would give a different and wrong part wherever a cut crosses the core boundary.
    """
    blank, repairs = body_blank_full('vsp_tail', p['U'], p['oml'])
    unit_width, U = p['unit_width'], p['U']
    tail_len = body_len_of(U, p['oml'])
    cut_len = p['cut_len']
    thickness, z_offset = p['buttress_cut_thickness'], p['buttress_z_offset']
    r_inset, angle = p['buttress_r_inset'], p['overhang_angle_from_bed']

    lower = body_blank_full_lower(blank, unit_width, tail_len, cut_len)
    half = lower.common(right_half_mask(unit_width, tail_len))

    tools = []
    for dx, ang in ((-unit_width * 0.30, 5.0), (0.0, 12.5), (unit_width * 0.30, 20.0)):
        tools.append(_moved(side_buttress(
            ang, unit_width, tail_len, thickness, p['side_z_end'], z_offset,
            p['side_r_start'], p['side_r_end'], r_inset, angle), x=dx))

    for dy, ang in ((unit_width * 0.07, 15.0), (0.0, 0.0)):
        tools.append(_moved(top_buttress(
            ang, unit_width, tail_len, thickness, p['top_z_end'], z_offset,
            p['top_r_start'], p['top_r_end'], r_inset, angle), y=dy))
        tools.append(_moved(bottom_buttress(
            ang, unit_width, tail_len, thickness, p['bottom_z_end'], z_offset,
            p['bottom_r_start'], p['bottom_r_end'], r_inset, angle), y=dy))

    # The two diagonal pairs, the second a unit_width*sin(30) further aft than the first.
    diag_z = -tail_len + p['top_diag_z_start']
    for dz in (0.0, unit_width * math.sin(math.radians(30.0))):
        for ang in (30.0, -30.0):
            tools.append(_moved(top_diag_buttress(
                ang, unit_width, thickness, p['top_diag_depth']), z=diag_z + dz))

    cutter = _fuse(tools).cut(pyramid(unit_width, tail_len, z_offset))
    return mirror_y(half.cut(cutter)), repairs


#: How many points are taken round the offset section when it is re-fitted. 480 puts the
#: re-fitted curve within 8.3e-4 mm of the exact offset (measured 2026-09-01), two orders of
#: magnitude finer than the printed fit the flange has to hold.
FLANGE_OFFSET_SAMPLES = 480


def _clean_offset(face, inset):
    """`face`'s outline inset by `inset`, as one closed curve rather than 540 fragments.

    **`makeOffset2D` cannot be used directly here.** The nose section is four B-spline edges;
    offsetting it returns 540 `OffsetCurve` segments, 98 of them shorter than a micron and the
    shortest 2.2e-08 mm. OCC tolerates those in memory, so the part builds and reports valid --
    but they do not survive being written and read back. Measured 2026-09-01, the nose tip
    built valid and reloaded *invalid*, and the slivers dragged the finished part up to 548
    faces carrying 0.099 mm of edge tolerance, on a part whose own fit is a tenth of that.

    Re-fitting the offset as a single periodic B-spline removes them, and it does not cost
    fidelity against the authority: OpenSCAD's `offset()` acts on an already-discretized
    polygon, so the reference this port matches is itself an approximation of the true offset.
    """
    ref = face.makeOffset2D(-inset).OuterWire
    # A periodic interpolation needs each point once; discretize repeats the closing point.
    points = ref.discretize(Number=FLANGE_OFFSET_SAMPLES + 1)[:-1]
    curve = Part.BSplineCurve()
    curve.interpolate(Points=points, PeriodicFlag=True)
    return Part.Wire(curve.toShape())


def nose_tip(p):
    """`nose()` -- the cowl's forward closure, which is a separate printed part.

    The nose is split off so the cowl body never turns over, which is what keeps every
    surface on it above the overhang angle (section 6.2). It is the *upper* slice of the
    blank, given a short flange that plugs into the cowl, then bored for the plate.

    The flange is the blank's own silhouette inset by `nose_flange_inset`, which is the cowl's
    wall thickness plus a fit: `cowl_n_perimeters * extrusion_width + nose_flange_tolerance`,
    with the tolerance negative so the joint is an interference (OQ-DES-CW9, OQ-DES-CW10).
    That is why the nose seats and bonds rather than dropping in.

    `projection(cut=false)` in the source is the silhouette of the whole upper slice. The
    slice tapers monotonically toward the tip, so its silhouette is its widest cross-section,
    which is the one at `-cut_len` -- taken directly here rather than by projecting, and
    checked by the volume `main()` reports.
    """
    blank, repairs = body_blank_full('vsp_nose', p['U'], p['oml'])
    unit_width, cut_len = p['unit_width'], p['cut_len']
    flange_h, inset = p['nose_flange_height'], p['nose_flange_inset']
    plate_r = p['plate_diam'] / 2.0 + p['plate_tol']
    eps = 0.01

    upper = body_blank_full_upper(blank, unit_width, cut_len)

    wires = blank.slice(App.Vector(0, 0, 1), -cut_len)
    if not wires:
        raise ValueError('no cross-section at -cut_len; the flange silhouette needs one')
    face = Part.Face(max(wires, key=lambda w: Part.Face(w).Area))
    # The section is taken *at* -cut_len, so it is already at the height the flange hangs
    # from: extrude downward and do not also translate. The source translates because
    # `projection()` flattens its outline to z = 0 first, and carrying that translate across
    # to a section that never moved puts the flange at -13 instead of -7.
    flange = Part.Face(_clean_offset(face, inset)).extrude(App.Vector(0, 0, -flange_h))

    solid = upper.fuse(flange)

    bore = Part.makeCylinder(plate_r, 3 * (cut_len + flange_h),
                             App.Vector(0, 0, -1.5 * (cut_len + flange_h)))
    solid = solid.cut(bore)

    # The seat the plate drops onto, flared out at the overhang angle so it prints.
    height = cut_len - p['plate_thickness'] + flange_h + eps
    seat = Part.makeCone(
        plate_r + height / math.tan(math.radians(p['overhang_angle_from_bed'])),
        plate_r, height, App.Vector(0, 0, -cut_len - flange_h - eps))
    return solid.cut(seat), repairs


def nose_plate(p):
    """`nose_plate()` -- the disc that closes the nose, with its own printed flange."""
    r = p['plate_diam'] / 2.0
    thickness, flange_h = p['plate_thickness'], p['plate_flange_height']
    flange_w = p['plate_flange_width']
    flare = flange_h / math.tan(math.radians(p['overhang_angle_from_bed']))
    eps = 0.01

    body = Part.makeCylinder(r, thickness + 2 * flange_h,
                             App.Vector(0, 0, -thickness - 2 * flange_h))
    taper = Part.makeCone(r + flare, r, flange_h,
                          App.Vector(0, 0, -thickness - flange_h))
    skirt = Part.makeCylinder(r + flare, flange_h,
                              App.Vector(0, 0, -thickness - 2 * flange_h))
    solid = body.fuse(taper).fuse(skirt)

    height = 2 * flange_h + eps
    pocket = Part.makeCone(
        r - flange_w + height / math.tan(math.radians(p['overhang_angle_from_bed'])),
        r - flange_w, height, App.Vector(0, 0, -thickness - 2 * flange_h - eps))
    solid = solid.cut(pocket)

    # The plate is the one cowl part whose *driver* transforms it: `nose_render` wraps the
    # module in `mirror([0,0,-1])`, so the rendered part sits at z 0..2.8 where the module
    # builds it at -2.8..0. Mirroring here keeps the ported part in the same place as the
    # one it replaces -- volume would not have caught this, being mirror-invariant, but a
    # print laid out from the STL would have been upside down.
    return _mirror(solid, (0, 0, -1)), []


# --------------------------------------------------------------------------------

REFERENCE = {
    'nose': dict(U=1.0, unit_width=100.0, cut_len=6.0, overhang_angle_from_bed=35.0,
                 buttress_cut_thickness=0.1, buttress_z_offset=2.0, buttress_r_inset=3.0,
                 buttress_r_start=0.0, buttress_r_end=6.6,
                 oml=dict(scale_m_per_mm=1e-3, length_m=0.05, offset_x_m=0.0,
                          reversed=False)),
    'nose_nose': dict(U=1.0, unit_width=100.0, cut_len=6.0, overhang_angle_from_bed=35.0,
                      nose_flange_height=1.0, nose_flange_inset=0.5,
                      plate_diam=60.0, plate_thickness=0.8, plate_tol=0.1,
                      oml=dict(scale_m_per_mm=1e-3, length_m=0.05, offset_x_m=0.0,
                               reversed=False)),
    'nose_plate': dict(U=1.0, overhang_angle_from_bed=35.0, plate_diam=60.0,
                       plate_thickness=0.8, plate_flange_height=1.0,
                       plate_flange_width=2.0),
    'tail': dict(U=1.0, unit_width=100.0, cut_len=0.0, overhang_angle_from_bed=35.0,
                 buttress_cut_thickness=0.1, buttress_z_offset=2.0, buttress_r_inset=5.0,
                 side_z_end=25.0, side_r_start=0.0, side_r_end=23.3,
                 top_z_end=3.0, top_r_start=0.0, top_r_end=0.0,
                 bottom_z_end=20.0, bottom_r_start=0.0, bottom_r_end=28.8,
                 top_diag_z_start=20.0, top_diag_depth=2.0,
                 oml=dict(scale_m_per_mm=1e-3, length_m=0.1, offset_x_m=-0.25,
                          reversed=True)),
}


def main():
    print('PART:: cowl -- nose and tail, at the reference configuration')
    print('  %-8s %8s %7s %9s %14s  %s'
          % ('cowl', 'solids', 'faces', 'repairs', 'volume', 'checks'))
    ok = True
    for label, build in (('nose', nose_cowl), ('nose_nose', nose_tip),
                         ('nose_plate', nose_plate), ('tail', tail_cowl)):
        try:
            shape, repairs = build(REFERENCE[label])
        except Exception as exc:                                        # noqa: BLE001
            print('  %-8s FAILED %s: %s' % (label, type(exc).__name__, exc))
            ok = False
            continue
        checks = []
        if not shape.isValid():
            checks.append('INVALID')
        if len(shape.Solids) != 1:
            checks.append('SOLIDS=%d' % len(shape.Solids))
        print('  %-8s %8d %7d %9d %14.3f  %s'
              % (label, len(shape.Solids), len(shape.Faces), len(repairs),
                 oml_blank.volume(shape), ' '.join(checks) if checks else 'ok'))
        ok &= not checks
    print('')
    print('  %s' % ('builds' if ok else 'FAILED -- see checks above'))
    sys.stdout.flush()
    return 0 if ok else 1


if is_entry_point(__name__):
    raise SystemExit(main())
