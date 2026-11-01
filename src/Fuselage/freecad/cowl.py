"""IP-FC-12: the nose and tail cowls, ported from `scad/cowl_geometry.scad`.

A cowl is the OML blank with material cut away: `oml_blank` supplies the blank as a B-rep
solid, this module supplies the cutting tools and the boolean tree. Nothing here builds a
wall. **The cowls print in spiral vase mode and that capability is kept** (DES-12,
doc/design/cowl.md section 6.4): vase mode spirals a single contour per layer and admits no
interior geometry at all, so a cowl given a modeled inner surface is no longer vase-mode
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
in millimeters, except the three `oml.*_m` fields, which are meters and say so (OQ-DES-CW1).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import oml_blank
import si
from corner_common import is_entry_point

# The parameter rows each cowl part's sheet carries, as (alias, value).
#
# Every row is a literal rather than a relationship, which is the opposite of `corner_tree`'s
# choice and is deliberate. A cowl's dimensions are fractions of `unit_width` *in the
# parameter file*, and `derived_cowl_parameters()` is where that scaling is applied and
# documented; restating those fractions here as expressions would put the same design decision
# in two places, and the one that moved would win silently. `U` and `unit_width` are both
# carried so a reader of a generated document can see the size it was built at.
#
# **All four tables below are dead code as of 2026-09-21.** They are kept only as the
# reference this module's own `main()` checks against, and as what the ported versions in
# `cowl_tree.py` were verified byte-for-byte-in-volume against -- nothing here is what a real
# build actually runs any more. `nose_cowl`/`tail_cowl` moved to `cowl_tree.py`'s sheet-bound
# mechanism on 2026-09-01; `nose_plate` and `nose_tip` followed on 2026-09-21, closing
# IP-FC-12's "cowl documents are not yet parametric" gap for all four cowl kinds. Each move
# was verified against this module's own version of the part: zero symmetric difference and
# matching face count at two separate `U` values (not just the reference row), and a
# built document's sheet edited in place and recomputed to confirm it actually tracks a
# changed value rather than merely agreeing with a second independent build.
# `cowl_nose_cowl.py`, `cowl_tail.py`, `cowl_nose_plate.py` and `cowl_nose_tip.py` all import
# `cowl_tree` now, not this module. This module's own `emit_part()` mechanism has no more
# callers among the four cowl kinds; it stays for now as the thing the reference checks build
# against, not because anything still depends on it to produce a document.
#: **These four tables are parameter-sheet rows, so they are millimeters and degrees** -- a
#: `Spreadsheet::Sheet` evaluates in millimeters and the seed the sweep exports comes from
#: `derived_parameters()`, the exempt OpenSCAD path. The `oml_*_m` rows are the exception the
#: names already carry: they are meters, because the OML is a meter-scaled surface
#: (OQ-DES-CW1). `from_flat` is where the whole set crosses into SI, and nothing below it
#: reads a millimeter.
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

#: Rows of a parameter sheet that are **not** lengths, so `from_flat` must not convert them.
#: Listed rather than inferred, because the failure mode of getting one wrong is silent: `U` is
#: a multiplier, and scaling a multiplier by 1/1000 moves the part's size without moving any
#: stated dimension, which is the one scale error that does not look like one.
#:
#: `overhang_angle_from_bed` is degrees from the bed (OQ-DES-CW2) and becomes radians, which is
#: a conversion but not a length one. `oml_reversed` is a flag. The `oml_*_m` rows are already
#: meters and are passed through.
DIMENSIONLESS_ROWS = ('U', 'oml_reversed', 'oml_scale_m_per_mm')
ANGLE_ROWS = ('overhang_angle_from_bed',)
ALREADY_SI_ROWS = ('oml_length_m', 'oml_offset_x_m')


def from_flat(seed):
    """The nested form the builders take, in SI, from the flat millimeter sheet the sweep exports.

    **This is the cowl family's unit boundary.** Every row of `seed` is a parameter-sheet value:
    millimeters for a length, degrees for the overhang angle, except the `oml_*_m` rows which
    are already meters (OQ-DES-CW1). Everything this returns is meters and radians, and every
    builder below reads it that way.

    The OML fields stay grouped because they travel together and because `oml['offset_x_m']`
    reading as meters at the point of use is what OQ-DES-CW1 decided.
    """
    p = {}
    for key, value in seed.items():
        if key.startswith('oml_'):
            continue
        if key in DIMENSIONLESS_ROWS:
            p[key] = value
        elif key in ANGLE_ROWS:
            p[key.replace('_from_bed', '_rad')] = math.radians(value)
        else:
            p[key] = si.m(value)
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

def buttress_shape(unit_width_m, body_len_m, z_end_m, z_offset_m, r_start_m, r_end_m,
                   r_inset_m, overhang_rad):
    """The buttress cutting profile, in the plane it is extruded from. Meters throughout.

    Six points, and the two carrying `r_inset_m` are the reason it is not a simple trapezoid:
    they step the profile inward by `r_inset_m` over a rise of `r_inset_m * tan(angle)`, which
    is what keeps both ends of the cut at or above the overhang angle so the notch prints
    without support. `overhang_rad` is measured from the bed (OQ-DES-CW2), so the tangent is
    taken of the angle as given.
    """
    rise_m = r_inset_m * math.tan(overhang_rad)
    return [
        (-unit_width_m, z_offset_m),
        (r_start_m, z_offset_m),
        (r_start_m + r_inset_m, z_offset_m + rise_m),
        (r_end_m + r_inset_m, body_len_m - z_end_m - rise_m),
        (r_end_m, body_len_m - z_end_m),
        (-unit_width_m, body_len_m - z_end_m),
    ]


def diag_buttress_shape(unit_width_m, buttress_depth_m):
    """The diagonal buttress profile -- a plain rectangle, unlike `buttress_shape`."""
    return [
        (-unit_width_m, -unit_width_m / 2.0),
        (buttress_depth_m, -unit_width_m / 2.0),
        (buttress_depth_m, unit_width_m / 2.0),
        (-unit_width_m, unit_width_m / 2.0),
    ]


def _extruded(points_m, thickness_m):
    """`linear_extrude(height=thickness, center=true)` of a 2D profile."""
    return si.prism_m(points_m, -thickness_m / 2.0, thickness_m)


def _rot_x(shape, angle_rad):
    out = shape.copy()
    out.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), math.degrees(angle_rad))
    return out


def _rot_z(shape, angle_rad):
    out = shape.copy()
    out.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), math.degrees(angle_rad))
    return out


def _moved(shape, x_m=0.0, y_m=0.0, z_m=0.0):
    out = shape.copy()
    out.translate(si.vec_m(x_m, y_m, z_m))
    return out


def top_buttress(ang_rad, unit_width_m, tail_len_m, cut_thickness_m, z_end_m, z_offset_m,
                 r_start_m, r_end_m, r_inset_m, overhang_rad):
    """`rotate([ang,0,0]) translate([-w/2,0,-tail_len]) rotate([90,0,0]) extrude(profile)`.

    OpenSCAD applies its transforms innermost-first, so the profile is stood upright, moved
    out to the part's flank and down to its aft end, and only then swung by `ang_rad`.
    """
    shape = _extruded(buttress_shape(unit_width_m, tail_len_m, z_end_m, z_offset_m,
                                     r_start_m, r_end_m, r_inset_m, overhang_rad),
                      cut_thickness_m)
    shape = _rot_x(shape, math.pi / 2.0)
    shape = _moved(shape, x_m=-unit_width_m / 2.0, z_m=-tail_len_m)
    return _rot_x(shape, ang_rad)


def top_diag_buttress(ang_rad, unit_width_m, cut_thickness_m, depth_m):
    shape = _extruded(diag_buttress_shape(unit_width_m, depth_m), cut_thickness_m)
    shape = _moved(shape, x_m=-unit_width_m / 2.0)
    return _rot_x(shape, ang_rad)


def side_buttress(ang_rad, unit_width_m, body_len_m, cut_thickness_m, z_end_m, z_offset_m,
                  r_start_m, r_end_m, r_inset_m, overhang_rad):
    """As `top_buttress`, with the whole thing then swung a quarter turn onto the side."""
    shape = _extruded(buttress_shape(unit_width_m, body_len_m, z_end_m, z_offset_m,
                                     r_start_m, r_end_m, r_inset_m, overhang_rad),
                      cut_thickness_m)
    shape = _rot_x(shape, math.pi / 2.0)
    shape = _rot_x(shape, ang_rad)
    shape = _moved(shape, x_m=-unit_width_m / 2.0, z_m=-body_len_m)
    return _rot_z(shape, -math.pi / 2.0)


def bottom_buttress(ang_rad, unit_width_m, body_len_m, cut_thickness_m, z_end_m, z_offset_m,
                    r_start_m, r_end_m, r_inset_m, overhang_rad):
    """As `top_buttress`, turned to face the other way before being swung by `ang_rad`."""
    shape = _extruded(buttress_shape(unit_width_m, body_len_m, z_end_m, z_offset_m,
                                     r_start_m, r_end_m, r_inset_m, overhang_rad),
                      cut_thickness_m)
    shape = _rot_x(shape, math.pi / 2.0)
    shape = _moved(shape, x_m=-unit_width_m / 2.0, z_m=-body_len_m)
    shape = _rot_z(shape, math.pi)
    return _rot_x(shape, ang_rad)


def pyramid(unit_width_m, tail_len_m, z_offset_m):
    """The protected core: a pyramid over a cube, and the bulkhead interface.

    This is *subtracted from the buttress tools*, not from the blank -- so it is a region the
    buttresses are forbidden to reach rather than material in its own right. It is
    load-bearing (section 6.3): the buttress cuts stopping short of it is what leaves the cowl
    something to seat on.
    """
    half_m = unit_width_m / 2.0
    apex_m = unit_width_m / 4.0
    base = si.vecs_m([(half_m, half_m, 0.0), (half_m, -half_m, 0.0),
                      (-half_m, -half_m, 0.0), (-half_m, half_m, 0.0)])
    faces = [Part.Face(Part.makePolygon(base + [base[0]]))]
    tip = si.vec_m(0.0, 0.0, apex_m)
    for i in range(4):
        a, b = base[i], base[(i + 1) % 4]
        faces.append(Part.Face(Part.makePolygon([a, b, tip, a])))
    shell = Part.Shell(faces)
    shell.sewShape()
    tip_solid = Part.makeSolid(shell)
    tip_solid.translate(si.vec_m(0.0, 0.0, -tail_len_m + z_offset_m))

    box = si.box_m(unit_width_m, unit_width_m, tail_len_m,
                   si.vec_m(-half_m, -half_m, -2 * tail_len_m + z_offset_m))
    return tip_solid.fuse(box)


# --------------------------------------------------------------------------------
# The blank, and the masks that cut it down
# --------------------------------------------------------------------------------

def _square_prism(unit_width_m, z0_m, height_m):
    """`linear_extrude` of the source's oversized square -- 2*unit_width on a side.

    Deliberately larger than the part: these masks select a *range of z*, and the square is
    only there because a 2D profile has to have some extent.
    """
    w = unit_width_m
    return si.prism_m([(w, w), (-w, w), (-w, -w), (w, -w)], z0_m, height_m)


def right_half_mask(unit_width_m, body_len_m):
    w = unit_width_m
    return si.prism_m([(w, 0), (w, w), (-w, w), (-w, 0)],
                      -body_len_m - 1.5 * body_len_m, 3 * body_len_m)


def octant_mask(unit_width_m, body_len_m):
    w = unit_width_m
    return si.prism_m([(0, 0), (w, w), (0, w)],
                      -body_len_m - 1.5 * body_len_m, 3 * body_len_m)


def body_blank_full(name, U, oml):
    solid, repairs = oml_blank.blank(name, U, oml['scale_m_per_mm'],
                                     oml['offset_x_m'], oml['reversed'])
    return solid, repairs


def body_len_m_of(U, oml):
    """The blank's length **in meters**, as the model holds it.

    `U * oml_length_m / oml_scale_m_per_mm` is the length in the model's millimeters, which is
    what `oml_blank.blank` scales the imported surface to; this converts that to meters.

    **The scale does not cancel.** It is 1e-3 in every configuration shipped today, which makes
    `si.m(x / 1e-3)` look like `x` -- but `oml_scale_m_per_mm` is a parameter, so writing
    `U * oml['length_m']` would silently stop tracking it and the mask would be the wrong
    length at any other scale, with no stated dimension having moved.
    """
    return si.m(U * oml['length_m'] / oml['scale_m_per_mm'])


def body_blank_full_lower(blank, unit_width_m, body_len_m, cut_len_m):
    """Everything aft of `cut_len_m`: the cowl's own extent."""
    return blank.common(_square_prism(unit_width_m, -body_len_m, body_len_m - cut_len_m))


def body_blank_full_upper(blank, unit_width_m, cut_len_m):
    """Everything forward of `cut_len_m`: what the nose tip is made from."""
    return blank.common(_square_prism(unit_width_m, -cut_len_m, cut_len_m))


# --------------------------------------------------------------------------------
# The parts
# --------------------------------------------------------------------------------

def nose_cowl(p):
    """The nose cowl: one octant, one side buttress, taken out to the full shape."""
    blank, repairs = body_blank_full('vsp_nose', p['U'], p['oml'])
    unit_width_m, U = p['unit_width'], p['U']
    body_len_m = body_len_m_of(U, p['oml'])
    cut_len_m = p['cut_len']

    lower = body_blank_full_lower(blank, unit_width_m, body_len_m, cut_len_m)
    octant = lower.common(octant_mask(unit_width_m, body_len_m))

    tool = side_buttress(0.0, unit_width_m, body_len_m, p['buttress_cut_thickness'],
                         cut_len_m + p['buttress_z_offset'], p['buttress_z_offset'],
                         p['buttress_r_start'], p['buttress_r_end'], p['buttress_r_inset'],
                         p['overhang_angle_rad'])
    return octant_to_full(octant.cut(tool)), repairs


def tail_cowl(p):
    """The tail cowl: one half, eleven buttress cuts, mirrored in y.

    The buttress tools are unioned and then have the protected core taken *out of them*
    before any of it reaches the blank, which is what stops the cuts eating the bulkhead
    interface. Building it the other way round -- cutting the blank and then adding the core
    back -- would give a different and wrong part wherever a cut crosses the core boundary.
    """
    blank, repairs = body_blank_full('vsp_tail', p['U'], p['oml'])
    unit_width_m, U = p['unit_width'], p['U']
    tail_len_m = body_len_m_of(U, p['oml'])
    cut_len_m = p['cut_len']
    thickness_m, z_offset_m = p['buttress_cut_thickness'], p['buttress_z_offset']
    r_inset_m, overhang_rad = p['buttress_r_inset'], p['overhang_angle_rad']

    lower = body_blank_full_lower(blank, unit_width_m, tail_len_m, cut_len_m)
    half = lower.common(right_half_mask(unit_width_m, tail_len_m))

    tools = []
    for dx_m, ang_rad in ((-unit_width_m * 0.30, math.radians(5.0)),
                          (0.0, math.radians(12.5)),
                          (unit_width_m * 0.30, math.radians(20.0))):
        tools.append(_moved(side_buttress(
            ang_rad, unit_width_m, tail_len_m, thickness_m, p['side_z_end'], z_offset_m,
            p['side_r_start'], p['side_r_end'], r_inset_m, overhang_rad), x_m=dx_m))

    for dy_m, ang_rad in ((unit_width_m * 0.07, math.radians(15.0)), (0.0, 0.0)):
        tools.append(_moved(top_buttress(
            ang_rad, unit_width_m, tail_len_m, thickness_m, p['top_z_end'], z_offset_m,
            p['top_r_start'], p['top_r_end'], r_inset_m, overhang_rad), y_m=dy_m))
        tools.append(_moved(bottom_buttress(
            ang_rad, unit_width_m, tail_len_m, thickness_m, p['bottom_z_end'], z_offset_m,
            p['bottom_r_start'], p['bottom_r_end'], r_inset_m, overhang_rad), y_m=dy_m))

    # The two diagonal pairs, the second a unit_width*sin(30) further aft than the first.
    diag_z_m = -tail_len_m + p['top_diag_z_start']
    for dz_m in (0.0, unit_width_m * math.sin(math.radians(30.0))):
        for ang_rad in (math.radians(30.0), math.radians(-30.0)):
            tools.append(_moved(top_diag_buttress(
                ang_rad, unit_width_m, thickness_m, p['top_diag_depth']),
                z_m=diag_z_m + dz_m))

    cutter = _fuse(tools).cut(pyramid(unit_width_m, tail_len_m, z_offset_m))
    return mirror_y(half.cut(cutter)), repairs


#: How many points are taken round the offset section when it is re-fitted. 480 puts the
#: re-fitted curve within 8.3e-4 mm of the exact offset (measured 2026-09-01), two orders of
#: magnitude finer than the printed fit the flange has to hold.
FLANGE_OFFSET_SAMPLES = 480

#: The overshoot that keeps a cutting cone's end face off the surface it is cutting through.
#: 0.01 mm, the project's `geometry_eps()`. It is a construction epsilon rather than a
#: dimension -- nothing measures it -- but it is a length and so is stored in meters.
CUT_EPS_M = 1.0e-5


def _clean_offset(face, inset_m):
    """`face`'s outline inset by `inset_m` meters, as one closed curve rather than 540 fragments.

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
    ref = face.makeOffset2D(-si.mm(inset_m)).OuterWire
    # A periodic interpolation needs each point once; discretize repeats the closing point.
    # The points stay kernel vectors: they go straight back into `interpolate` without any
    # arithmetic on them, so converting out and in again would only add rounding.
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
    unit_width_m, cut_len_m = p['unit_width'], p['cut_len']
    flange_h_m, inset_m = p['nose_flange_height'], p['nose_flange_inset']
    plate_r_m = p['plate_diam'] / 2.0 + p['plate_tol']

    upper = body_blank_full_upper(blank, unit_width_m, cut_len_m)

    wires = blank.slice(App.Vector(0, 0, 1), si.mm(-cut_len_m))
    if not wires:
        raise ValueError('no cross-section at -cut_len; the flange silhouette needs one')
    face = Part.Face(max(wires, key=lambda w: Part.Face(w).Area))
    # The section is taken *at* -cut_len, so it is already at the height the flange hangs
    # from: extrude downward and do not also translate. The source translates because
    # `projection()` flattens its outline to z = 0 first, and carrying that translate across
    # to a section that never moved puts the flange at -13 instead of -7.
    flange = Part.Face(_clean_offset(face, inset_m)).extrude(si.vec_m(0.0, 0.0, -flange_h_m))

    solid = upper.fuse(flange)

    bore = si.cylinder_m(plate_r_m, 3 * (cut_len_m + flange_h_m),
                         si.vec_m(0.0, 0.0, -1.5 * (cut_len_m + flange_h_m)))
    solid = solid.cut(bore)

    # The seat the plate drops onto, flared out at the overhang angle so it prints.
    height_m = cut_len_m - p['plate_thickness'] + flange_h_m + CUT_EPS_M
    seat = si.cone_m(
        plate_r_m + height_m / math.tan(p['overhang_angle_rad']),
        plate_r_m, height_m, si.vec_m(0.0, 0.0, -cut_len_m - flange_h_m - CUT_EPS_M))
    return solid.cut(seat), repairs


def nose_plate(p):
    """`nose_plate()` -- the disc that closes the nose, with its own printed flange."""
    r_m = p['plate_diam'] / 2.0
    thickness_m, flange_h_m = p['plate_thickness'], p['plate_flange_height']
    flange_w_m = p['plate_flange_width']
    flare_m = flange_h_m / math.tan(p['overhang_angle_rad'])

    body = si.cylinder_m(r_m, thickness_m + 2 * flange_h_m,
                         si.vec_m(0.0, 0.0, -thickness_m - 2 * flange_h_m))
    taper = si.cone_m(r_m + flare_m, r_m, flange_h_m,
                      si.vec_m(0.0, 0.0, -thickness_m - flange_h_m))
    skirt = si.cylinder_m(r_m + flare_m, flange_h_m,
                          si.vec_m(0.0, 0.0, -thickness_m - 2 * flange_h_m))
    solid = body.fuse(taper).fuse(skirt)

    height_m = 2 * flange_h_m + CUT_EPS_M
    pocket = si.cone_m(
        r_m - flange_w_m + height_m / math.tan(p['overhang_angle_rad']),
        r_m - flange_w_m, height_m,
        si.vec_m(0.0, 0.0, -thickness_m - 2 * flange_h_m - CUT_EPS_M))
    solid = solid.cut(pocket)

    # The plate is the one cowl part whose *driver* transforms it: `nose_render` wraps the
    # module in `mirror([0,0,-1])`, so the rendered part sits at z 0..2.8 where the module
    # builds it at -2.8..0. Mirroring here keeps the ported part in the same place as the
    # one it replaces -- volume would not have caught this, being mirror-invariant, but a
    # print laid out from the STL would have been upside down.
    return _mirror(solid, (0, 0, -1)), []


# --------------------------------------------------------------------------------

#: The reference configuration of each part, **already in the builders' SI form** -- the same
#: thing `from_flat` returns, so it is built as `from_flat(dict(PARAMS_*))` rather than written
#: out twice. Writing it by hand was how the millimeter figures survived here while the
#: builders moved to meters; deriving it means the one conversion in `from_flat` is the only
#: place the units are decided, and a reader checking a figure against a drawing reads the
#: millimeter tables above.
REFERENCE = {
    'nose': from_flat(dict(PARAMS_NOSE_COWL)),
    'nose_nose': from_flat(dict(PARAMS_NOSE_TIP)),
    'nose_plate': from_flat(dict(PARAMS_NOSE_PLATE)),
    'tail': from_flat(dict(PARAMS_TAIL)),
}


def main():
    print('PART:: cowl -- nose and tail, at the reference configuration')
    print('  %-8s %8s %7s %9s %14s  %s'
          % ('cowl', 'solids', 'faces', 'repairs', 'volume mm3', 'checks'))
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
                 oml_blank.volume_m3(shape) * si.MM3_PER_M3,
                 ' '.join(checks) if checks else 'ok'))
        ok &= not checks
    print('')
    print('  %s' % ('builds' if ok else 'FAILED -- see checks above'))
    sys.stdout.flush()
    return 0 if ok else 1


if is_entry_point(__name__):
    raise SystemExit(main())
