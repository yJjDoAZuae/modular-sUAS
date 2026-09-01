"""IP-FC-4: the cowl's outer mould line, as a B-rep solid rather than a triangle mesh.

`cowl_geometry.scad` builds every cowl by cutting an imported OML down, and what it imports
is a tessellation -- `vsp_nose.stl` and `vsp_tail.stl`, 36 MB of committed triangles that are
the *authoritative* definition of the outer surface. A mesh has no cylindrical face to write
into a STEP file, no surface for an assembly constraint to attach to, and no arc for a drawing
to dimension, so UC-2, UC-3, UC-4 and UC-7 are blocked for cowls for as long as that holds
(doc/design/cowl.md section 6.1). This module is the other side of that: it reads the
*surface* export, `vsp_nose.step` and `vsp_tail.step`, and hands back a solid.

**The surfaces and the meshes are the same shape.** Measured 2026-08-31, in case the 36 MB is
ever mistaken for the more trustworthy artifact: the volume enclosed by the STEP's own
triangulation agrees with the committed STL to +0.010% on the nose and +0.001% on the tail,
and station-by-station silhouettes agree to 0.14 mm at worst.

**Do not read `Shape.Volume` off what this returns.** On freeform surfaces that figure is
unreliable in a way that looks like a geometry error and is not: a sphere primitive reports
its volume to 0.000000%, the same sphere converted to a freeform surface reports -0.0437%,
this module's nose reports +0.077% and its tail +6.79%, all against answers known
independently. `volume()` below integrates the tessellation instead, which is also what the
OpenSCAD side reports and so is the like-for-like comparison. That is OQ-DES-CW12.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import MeshPart
import Part

from corner_common import is_entry_point

HERE = os.path.dirname(os.path.abspath(__file__))
OML_DIR = os.path.join(os.path.dirname(HERE), 'oml')

# What one OpenVSP model unit measures, and what the STEP file's header claims it measures.
#
# OpenVSP is dimensionless: the model holds bare numbers and every consumer declares its own
# interpretation. This project's convention is that one model unit is one metre, which is what
# the OpenSCAD path applies as `scale = U / oml_scale_m_per_mm` at `oml_scale_m_per_mm = 1e-3`.
# The STEP exporter must nonetheless write *something* into the header and writes FOOT, so a
# reader applies 304.8 mm per unit where the convention means 1000. Neither number is wrong;
# they are two different statements and the ratio between them is the correction.
#
# These duplicate `tools/oml_export.py`, deliberately: that module runs under OpenVSP's Python
# and this one under `freecadcmd`, and neither interpreter can import the other's environment.
# IP-FC-37 resolved the value; the assertion in `blank()` is what keeps the two in step.
MODEL_UNIT_MM = 1000.0
NATIVE_PER_MODEL_UNIT = 304.8
STEP_IMPORT_SCALE = MODEL_UNIT_MM / NATIVE_PER_MODEL_UNIT      # 3.28084

# Tessellation for `volume()`. A tolerance quoted against this constant is meaningless if it
# changes, so it is stated here once and the value is chosen by measurement rather than taste.
#
# **It is set by the smallest part, not the largest.** A tessellation inscribes a cylinder, so
# a bore removes slightly too little and leaves the part slightly too big, and the error is
# absolute rather than proportional -- which makes it negligible on a cowl and dominant on the
# nose tip, whose 30 mm plate bore is most of its surface. Measured 2026-08-31 against the
# reference, with the OML held constant so only the tessellation varies:
#
#     deflection   nose tip      tail cowl
#     0.05         +0.3186%      -0.0104%
#     0.02         +0.1176%      -0.0000%
#     0.01         +0.0575%
#     0.005        +0.0242%
#     0.002        +0.0018%   <- here
#     0.001        -0.0058%
#
# 0.02 would have passed both cowls and failed the tip by twelve times the tolerance, for a
# part whose geometry is exact. 0.002 is the coarsest value at which every part converges
# inside 0.010%.
VOLUME_DEFLECTION = 0.002

# How flat a face must be, in the STEP's own units, to count as lying in a plane -- and how
# close two such faces must be to count as lying in the *same* plane.
_FLAT = 1e-9
_COPLANAR = 1e-4


def _folds(face, grid=7):
    """Does this face's surface double back on itself?

    A well-formed patch faces consistently across its whole extent. Four of the tail's twelve
    patches -- the flat closure over its aft opening -- do not: the surface covers part of its
    own plane twice, facing opposite ways, over a contiguous band a quarter to a third of the
    patch wide. `isValid()` and `isClosed()` both report healthy through it, and the only
    symptom that reaches a caller is that cutting operations near that end return *nothing*:
    9 of 20 test positions, against 0 for the nose. See OQ-DES-CW13.

    Sampled coarsely on purpose. The defect covers a third of the patch, so it does not need
    a fine grid to find, and this runs for every part the sweep builds.
    """
    umin, umax, vmin, vmax = face.ParameterRange
    normals = []
    for i in range(grid):
        u = umin + (umax - umin) * i / (grid - 1.0)
        for j in range(grid):
            v = vmin + (vmax - vmin) * j / (grid - 1.0)
            try:
                du, dv = face.Surface.tangent(u, v)
                cross = App.Vector(du).cross(App.Vector(dv))
            except Exception:                                           # noqa: BLE001
                continue
            # Near a collapsed pole the normal is numerically meaningless rather than
            # reversed, and every patch on both parts has one such row. Skipping them is what
            # keeps this from reporting a fold on healthy geometry.
            if cross.Length <= 1e-9:
                continue
            normals.append(App.Vector(cross).normalize())
    if len(normals) < 4:
        return False
    mean = App.Vector(0, 0, 0)
    for n in normals:
        mean = mean.add(n)
    if mean.Length < 1e-9:
        return True
    mean.normalize()
    against = sum(1 for n in normals if n.dot(mean) < 0)
    # A tenth is far above the noise floor and far below what the defect produces: the four
    # bad patches score between 0.24 and 0.33, and every sound patch on both parts scores 0.
    return against > 0.10 * len(normals)


def _flat_axis(face):
    """Which axis this face is flat in, and where, or None if it is not planar."""
    bb = face.BoundBox
    for axis, length, low in (('x', bb.XLength, bb.XMin), ('y', bb.YLength, bb.YMin),
                              ('z', bb.ZLength, bb.ZMin)):
        if length < _FLAT:
            return axis, low
    return None


def repair_closure(shape):
    """Replace any folded flat closure with one sound face across the same opening.

    The tail's aft closure arrives from OpenVSP as four folded patches (OQ-DES-CW13). No
    export setting avoids them -- surface splitting is what creates the closure at all, and
    with it off each part exports as a single uncapped surface that will not sew -- so the
    repair belongs here.

    It is shape-preserving, and that is the point rather than a hope: the opening is planar,
    so one flat face across the boundary the remaining patches leave behind covers exactly
    what the discarded patches covered. Measured 2026-08-31, the repaired tail encloses
    594449.974 mm3 against the original's 594449.974, and passes 20 of 20 cutting positions
    where the original passed 11.

    Returns (faces, repairs) with `repairs` naming what was replaced, so a caller can report
    a repair rather than perform one silently.
    """
    groups, loose = {}, []
    for face in shape.Faces:
        flat = _flat_axis(face)
        if flat is None:
            loose.append(face)
            continue
        axis, position = flat
        # Round to the coplanarity tolerance so patches sharing a plane share a key.
        groups.setdefault((axis, round(position / _COPLANAR)), []).append(face)

    kept, repairs = list(loose), []
    for (axis, _key), faces in sorted(groups.items()):
        folded = [f for f in faces if _folds(f)]
        if not folded:
            kept.extend(faces)
            continue
        if len(folded) != len(faces):
            # A plane with both sound and folded patches is not the case this repair was
            # measured against, and guessing at it would be worse than declining.
            raise ValueError(
                'closure in %s has %d folded of %d coplanar faces; repair_closure only '
                'handles a wholly folded closure' % (axis, len(folded), len(faces)))
        repairs.append({'axis': axis, 'replaced': len(faces),
                        'position': _flat_axis(faces[0])[1]})

    if not repairs:
        return list(shape.Faces), []

    # Rebuild each discarded closure from the boundary the survivors leave. The edges wanted
    # are those lying wholly in the closure's plane; they are shared with the body patches, so
    # they are found on the kept faces rather than on the discarded ones.
    shell = Part.Shell(kept)
    shell.sewShape()
    faces = list(shell.Faces)
    for repair in repairs:
        axis = repair['axis']
        # Edges lying in the closure's *own* plane, not merely perpendicular to its axis.
        # Both ends of a part close in the same axis, and the nose's forward end and the
        # patch seams do too, so without the position test this collects several rings at
        # once and `sortEdges` correctly reports that they are not one loop.
        ring = []
        for edge in shell.Edges:
            bb = edge.BoundBox
            length, low = {'x': (bb.XLength, bb.XMin), 'y': (bb.YLength, bb.YMin),
                           'z': (bb.ZLength, bb.ZMin)}[axis]
            if length < _COPLANAR and abs(low - repair['position']) < _COPLANAR:
                ring.append(edge)
        if not ring:
            raise ValueError('no boundary found for the %s closure' % axis)
        loops = Part.sortEdges(ring)
        if len(loops) != 1:
            raise ValueError('the %s closure boundary is %d loops, not one'
                             % (axis, len(loops)))
        faces.append(Part.Face(Part.Wire(loops[0])))
        repair['cap_edges'] = len(loops[0])
    return faces, repairs


#: No conditioned face spans more than this many knot intervals in either direction.
#: Three is the measured requirement; see `condition()`.
MAX_SPANS = 3

#: How far a joint's speed ratio may vary along that joint before the reparameterisation is
#: declined as inexact. The measured spreads are 2.7e-11 in u and 5.7e-08 in v.
RATIO_SPREAD_TOL = 1e-4

_EPS = 1e-7
_SAMPLES = (0.1, 0.35, 0.6, 0.85)


def _joint_ratios(surf, direction):
    """The parametric speed ratio across each interior knot, and its spread along the joint.

    A ratio of 1 is a joint that is already C1. Anything else is a joint whose two sides agree
    in tangent *direction* but not in speed -- which is what makes these surfaces C0 in
    parameterisation while being smooth in space.
    """
    u0, u1, v0, v1 = surf.bounds()
    if direction == 'u':
        knots = list(surf.getUKnots())
        along = [v0 + (v1 - v0) * t for t in _SAMPLES]
        derivative = lambda k, step, other: surf.getDN(k + step, other, 1, 0)
    else:
        knots = list(surf.getVKnots())
        along = [u0 + (u1 - u0) * t for t in _SAMPLES]
        derivative = lambda k, step, other: surf.getDN(other, k + step, 0, 1)

    ratios = []
    for knot in knots[1:-1]:
        seen = []
        for other in along:
            try:
                before = derivative(knot, -_EPS, other).Length
                after = derivative(knot, +_EPS, other).Length
            except Exception:
                continue
            if before > 1e-12 and after > 1e-12:
                seen.append(after / before)
        if not seen:
            ratios.append((1.0, 0.0))
        else:
            mean = sum(seen) / len(seen)
            ratios.append((mean, (max(seen) - min(seen)) / max(seen)))
    return knots, ratios


def _respaced(knots, ratios):
    """Knot values whose intervals make the chain C1, over the original parameter range.

    C1 at a joint wants `d_before / dv_before == d_after / dv_after`, so the interval after a
    joint is the interval before it times that joint's speed ratio. The result is rescaled onto
    the original range, which is a linear reparameterisation and so changes nothing further.
    """
    deltas = [1.0]
    for ratio, _spread in ratios:
        deltas.append(deltas[-1] * ratio)
    running = [knots[0]]
    for delta in deltas:
        running.append(running[-1] + delta)
    scale = (knots[-1] - knots[0]) / (running[-1] - running[0])
    return [knots[0] + (x - running[0]) * scale for x in running]


def _condition_surface(surf, report):
    """A C1 copy of `surf` -- or the original, in any direction whose precondition fails."""
    conditioned = surf.copy()
    for direction in ('u', 'v'):
        if direction == 'u':
            degree, mults = conditioned.UDegree, list(conditioned.getUMultiplicities())
        else:
            degree, mults = conditioned.VDegree, list(conditioned.getVMultiplicities())
        if len(mults) <= 2 or max(mults[1:-1]) < degree:
            continue                              # no interior C0 joints in this direction

        knots, ratios = _joint_ratios(conditioned, direction)
        spread = max((s for _r, s in ratios), default=0.0)
        report.setdefault('spread', {})
        report['spread'][direction] = max(report['spread'].get(direction, 0.0), spread)
        if spread > RATIO_SPREAD_TOL:
            # The ratio varies along the joint, so no single knot vector makes this exact.
            # Decline rather than approximate -- subdivision alone still fixes the cut.
            report.setdefault('declined', []).append((direction, spread))
            continue

        respaced = _respaced(knots, ratios)
        rebuilt = Part.BSplineSurface()
        rebuilt.buildFromPolesMultsKnots(
            conditioned.getPoles(),
            list(conditioned.getUMultiplicities()), list(conditioned.getVMultiplicities()),
            respaced if direction == 'u' else list(conditioned.getUKnots()),
            list(conditioned.getVKnots()) if direction == 'u' else respaced,
            conditioned.isUPeriodic(), conditioned.isVPeriodic(),
            conditioned.UDegree, conditioned.VDegree, conditioned.getWeights())

        count = rebuilt.NbUKnots if direction == 'u' else rebuilt.NbVKnots
        for index in range(2, count):
            for tol in (1e-9, 1e-7, 1e-5):
                try:
                    dropped = (rebuilt.removeUKnot(index, degree - 1, tol) if direction == 'u'
                               else rebuilt.removeVKnot(index, degree - 1, tol))
                except Exception:
                    dropped = False
                if dropped:
                    report['reduced'] = report.get('reduced', 0) + 1
                    break
        conditioned = rebuilt
    return conditioned


def _cut_points(knots, max_spans):
    indices = list(range(0, len(knots), max_spans))
    if indices[-1] != len(knots) - 1:
        indices.append(len(knots) - 1)
    return [knots[i] for i in indices]


def condition(solid, max_spans=MAX_SPANS):
    """Make an imported OML solid one OCC's booleans behave on, without moving a point.

    **This is what makes the cowls correct across the swept range** (OQ-DES-CW17). Cutting a
    0.1 mm slot -- deliberately absolute, so it does not grow with `U` (section 6.3) -- into
    the OML as exported fails progressively as the body grows: at `U` = 4 the tail returned an
    empty shape, and at 1.5 it removed nineteen times too much while reporting a valid solid.

    Two operations, neither of which changes the geometry:

    * **Reparameterise, then reduce multiplicity.** OpenVSP's STEP writer emits its native
      piecewise-Bezier form, with interior knot multiplicity equal to the degree. That is C0 by
      definition even though the surface is smooth in space -- the worst tangent break across a
      face's 45 interior knots measures 0.000029 degrees. The joints are G1 but not C1: the
      tangents agree in direction, not in speed. Choosing knot *intervals* that match the
      speeds fixes that exactly, knot values not being geometry, after which the multiplicity
      drops from `degree` to `degree - 1`. Measured deviation 5.5e-10 mm on the tail, 9.5e-10
      on the nose.
    * **Subdivide** so no face spans more than `max_spans` knot intervals. This is the part
      that actually fixes the cut.

    **Both are wanted and neither is sufficient.** A blank made genuinely C1 but left at 9
    faces still returns -3573.933 mm3 at `U` = 4; a blank left C0 and subdivided is correct.
    So legality is not the mechanism -- a subdivided blank still carrying 256 C0 errors builds
    the part to +0.0036%. What the reparameterisation buys is *margin*: with it the cut
    survives `max_spans` = 6, without it 6 returns a negative volume and 3 is the limit. Three
    is used because it costs nothing.

    The reparameterisation is exact only where a joint's speed ratio is the same all along it.
    That holds for OpenVSP's dyadic subdivision -- the ratios are exact powers of two -- and is
    **checked per direction**, not assumed: a direction whose spread exceeds
    `RATIO_SPREAD_TOL` is left alone and named in `declined`, with subdivision still carrying
    it. The nose needs both directions and the tail only v, so neither part alone exercises it.
    """
    report = {'faces_in': len(solid.Faces), 'max_spans': max_spans}
    pieces = []
    for face in solid.Faces:
        surf = face.Surface
        if not hasattr(surf, 'NbUKnots'):
            pieces.append(face)              # planes, and the closures repair_closure rebuilt
            continue
        conditioned = _condition_surface(surf, report)
        u_cuts = _cut_points(list(conditioned.getUKnots()), max_spans)
        v_cuts = _cut_points(list(conditioned.getVKnots()), max_spans)
        for u0, u1 in zip(u_cuts[:-1], u_cuts[1:]):
            for v0, v1 in zip(v_cuts[:-1], v_cuts[1:]):
                pieces.append(conditioned.toShape(u0, u1, v0, v1))

    shell = Part.Shell(pieces)
    shell.sewShape()
    out = Part.makeSolid(shell)
    if not out.isClosed():
        raise ValueError('conditioning did not sew into a closed shell')
    report['faces_out'] = len(out.Faces)
    return out, report


def surface(name):
    """The named OML surface as a solid, in the STEP's own units, repaired and conditioned.

    `name` is 'vsp_nose' or 'vsp_tail' -- the stems `tools/oml_export.py` writes.

    Conditioning happens here rather than in either cowl because both import through this one
    function, and two cowls conditioned by two different mechanisms is the trap `nose_cowl()`
    already names for its booleans: the path that is never exercised is the one that breaks.
    """
    path = os.path.join(OML_DIR, name + '.step')
    if not os.path.exists(path):
        raise SystemExit(
            'OML surface not found: %s\n'
            'Export it with:  uv run python src/Fuselage/tools/oml_export.py '
            '--out src/Fuselage/oml' % path)
    raw = Part.read(path)
    faces, repairs = repair_closure(raw)
    shell = Part.Shell(faces)
    shell.sewShape()
    solid = Part.makeSolid(shell)
    if not solid.isClosed():
        raise ValueError('%s did not sew into a closed shell' % name)
    solid, conditioning = condition(solid)
    return solid, list(repairs) + [dict(conditioning, kind='conditioning')]


def blank(name, U, scale_m_per_mm, offset_x_m, reversed_):
    """`cowl_geometry.scad`'s `body_blank_full`, on the surface instead of the mesh.

    The OpenSCAD source is

        rotate([0, 90 - (reversed ? 180 : 0), 0])
          scale(U / scale_m_per_mm)
            translate([offset_x_m, 0, 0])
              import(mesh)

    and OpenSCAD applies those innermost first, so the offset is added in the *mesh's own
    frame* before anything scales it. That ordering is the whole reason `offset_x_m` carries
    a metre suffix (OQ-DES-CW1): the tail's -0.25 is -250 mm at U = 1, not -0.25 mm, and
    applying it after the scale puts the tail a quarter of a millimetre from where it belongs
    instead of a quarter of a metre.

    The surface arrives in the STEP's own units rather than the mesh's model units, so the
    offset is converted into them and the scale carries the reciprocal. At U = 1 with the
    conventional `scale_m_per_mm = 1e-3` the scale factor is exactly STEP_IMPORT_SCALE, which
    is the check `main()` makes.
    """
    solid, repairs = surface(name)
    solid = solid.copy()
    solid.translate(App.Vector(offset_x_m * NATIVE_PER_MODEL_UNIT, 0, 0))
    solid.scale(U / scale_m_per_mm / NATIVE_PER_MODEL_UNIT)
    solid.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0),
                 90.0 - (180.0 if reversed_ else 0.0))
    return solid, repairs


def volume(shape, deflection=VOLUME_DEFLECTION):
    """The volume the shape's triangles enclose.

    Not `Shape.Volume`, which is unreliable on freeform surfaces by up to 6.79% here while
    reporting `isValid()` and `isClosed()` throughout -- OQ-DES-CW12. This is the quantity the
    OpenSCAD side reports, so the two are comparable.
    """
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=deflection,
                                  AngularDeflection=0.2, Relative=False)
    points, facets = mesh.Topology
    total = 0.0
    for f in facets:
        a, b, c = points[f[0]], points[f[1]], points[f[2]]
        total += (a.x * (b.y * c.z - b.z * c.y)
                  - a.y * (b.x * c.z - b.z * c.x)
                  + a.z * (b.x * c.y - b.y * c.x))
    return abs(total) / 6.0


def main():
    print('PART:: oml_blank -- the OML surfaces, imported and repaired')
    print('  %-10s %6s %8s %14s %14s  %s'
          % ('surface', 'faces', 'repairs', 'volume', 'Shape.Volume', 'checks'))
    ok = True
    for name in ('vsp_nose', 'vsp_tail'):
        solid, repairs = surface(name)
        scaled = solid.copy()
        scaled.scale(STEP_IMPORT_SCALE)
        tess, occ = volume(scaled), scaled.Volume

        checks = []
        if not solid.isClosed():
            checks.append('NOT CLOSED')
        if len(solid.Solids) != 1:
            checks.append('SOLIDS=%d' % len(solid.Solids))
        # The scale is a convention shared with a module this one cannot import, so it is
        # checked rather than assumed: at U = 1 the OML is one unit_width across.
        bb = scaled.BoundBox
        if abs(bb.YLength - 100.0) > 0.5 or abs(bb.ZLength - 100.0) > 0.5:
            checks.append('SCALE y=%.3f z=%.3f, expected 100' % (bb.YLength, bb.ZLength))
        print('  %-10s %6d %8d %14.3f %14.3f  %+8.4f%%  %s'
              % (name, len(solid.Faces), len(repairs), tess, occ,
                 100.0 * (occ - tess) / tess, ' '.join(checks) if checks else 'ok'))
        ok &= not checks

    print('')
    print('  Shape.Volume is shown only to record how far it is out; nothing reads it.')
    print('  %s' % ('imports' if ok else 'FAILED -- see checks above'))
    # freecadcmd discards buffered stdout when the script exits cleanly, so a report that
    # ends in SystemExit(0) prints nothing at all unless it is flushed first.
    sys.stdout.flush()
    return 0 if ok else 1


if is_entry_point(__name__):
    raise SystemExit(main())
