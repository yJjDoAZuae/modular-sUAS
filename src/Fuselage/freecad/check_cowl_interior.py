"""IP-FC-17: the acceptance tests section 6 of the algorithm document states.

    freecadcmd check_cowl_interior.py --pass --kind=tail_shell

Add --clearance-check to also run OQ-DES-CW24's rib clearance-margin scan (Metric A, flag-only --
never fails the build, and costs on the order of an hour on top of the ordinary build above). Off
by default; see cowl_interior.clearance_margin_scan. It is a clearance diagnostic, not a
wall-thickness measurement and not a construction-failure check -- see CLEARANCE_MARGIN_MM.

**The wall and rib checks are the load-bearing ones.** Volume agreement says two solids enclose
the same space; it does not say the wall is where it should be, and a wall in the wrong place
with a compensating error elsewhere passes on volume alone.

The wall check is run **in the layer plane, not along the surface normal**, and that is the
whole point of it rather than a convenience. The interior is a *horizontal* inset by `t`, so a
correct construction puts the inner contour exactly `t` from the outer one measured in the
plane, at every station and all the way round. A 3-D normal offset -- the error this method
exists to avoid, because it is what every "shell this solid" command does -- would put it `t`
along the normal and therefore `t / cos(alpha)` in the plane, which on the shallowest surface
the design permits is 0.6 / cos 55 = 1.05 mm, three quarters of a millimetre wide of the
answer and impossible to miss. Measuring the perpendicular distance instead would report
`t * cos(alpha)` for the 2-D inset and `t` for the 3-D one, which is the same test read the
other way round; this way needs no local surface normal to be estimated.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import cowl_interior as ci
import cowl_tree
from corner_common import is_entry_point

#: Stations the wall is measured at, and samples around each.
STATIONS = 12
AROUND = 240


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    if default is None:
        raise SystemExit('missing --%s=' % name)
    return default


#: The face maker that resolves a set of section wires into faces, nesting and all.
#:
#: **Bullseye, because it is the one that handles a hole.** Given the two wires of a wall section,
#: `Part::FaceMakerBullseye` returns one face with two wires -- an outer boundary and one hole --
#: and `Part::FaceMakerCheese` agrees with it exactly (958.819 mm2 on the reference station, both).
#: `Part::FaceMakerSimple` does not resolve nesting at all: it returns two separate faces totalling
#: 150914 mm2, the sum of the two enclosed areas rather than the material between them.
FACE_MAKER = 'Part::FaceMakerBullseye'


def section_regions(wires):
    """Classify a section's closed wires into material regions, letting the kernel do the nesting.

    **Replaces a hand-rolled containment vote, and the kernel's answer is both cheaper and more
    general.** The question is whether a section is the annulus a wall section must be, or a ring
    broken into arcs; an earlier version answered it by building a face from the largest wire and
    testing how many points of the next wire fell inside. That works -- measured 200 of 200 on a
    healthy section against 0 of 200 on a broken one -- but it is pairwise, so it cannot describe a
    section with more than two wires, and it costs a face build plus a sampled point test.
    `Part.makeFace` resolves the whole set at once in about 0.6 s and reports the structure directly:

        one face with two wires        the ring is continuous
        several faces with one wire    the ring is broken into that many arcs

    `Face.Area` on the result is then the material area directly, rather than a difference of two
    separately-integrated wire areas -- which matters, because that difference is of two numbers
    near 75000 mm2 and carries both their discretization errors.

    Returns `(faces, wire_counts, area)`, or `None` if the maker will not build. Failing to build
    is reported as unclassifiable rather than as an annulus, so a caller declines to measure
    something it cannot interpret.
    """
    if not wires:
        return None
    try:
        built = Part.makeFace(wires, FACE_MAKER)
    except Exception:                                                   # noqa: BLE001
        return None
    if not built.Faces:
        return None
    return (len(built.Faces), sorted(len(f.Wires) for f in built.Faces),
            sum(f.Area for f in built.Faces))


def _is_annulus(wires):
    """Is this section one closed ring of material, as a wall section must be?

    True only for a single region with a single hole. Anything else -- arcs with no hole, several
    regions, or a set the face maker will not resolve -- is not a wall section and has no thickness
    to report.
    """
    got = section_regions(wires)
    if got is None:
        return False
    faces, counts, _area = got
    return faces == 1 and counts == [2]


def wall_thickness(wall, z, expect, tol):
    """In-plane distance from the inner contour to the outer, at one station.

    Returns `(n, near, worst_low, median, worst_high)` -- how many samples, how many landed
    within `tol` of `expect`, and the spread. Samples over a rib legitimately read more than
    `expect`, because the wall follows the notch in and back out and the inner contour dips
    with it; samples reading *less* are the failure, and there should be none.

    **Returns `None` where there is no thickness to report**, which is two cases and not one: a
    station with fewer than two loops across every solid, and -- since 2026-10-05 -- a station
    whose section is not an annulus at all, because the ring has come apart into arcs. Both mean
    "no wall here" and both callers already count that as a failure.

    **`worst_low` is a nearest-point minimum and does not converge; do not compare it against
    `WALL_TOL`.** Measured 2026-10-05 on `nose_cowl_shell` at `U` = 1, it was still falling at 3840
    samples at 17 of 24 stations, because a nearest-point distance at a concave corner crosses the
    corner rather than the wall and this section has one at every slot mouth.
    cowl_interior_surface.md section 6.1 carries the evidence and what does converge.
    """
    # **Measured per solid, though `build_part.py` (line ~328) now requires exactly one.**
    # Before IP-FC-139/140/141's mirror-order fix, the tail's buttress slots cut through the
    # full depth of the wall and it came out in five pieces; taking the two longest loops of
    # the whole section then paired an outer loop of one piece with an inner loop of another
    # and reported a distance across the cavity rather than across the wall -- 13 to 31 mm
    # against a 0.6 mm wall, which is how this check read before it was fixed. The loop over
    # `wall.Solids` is kept rather than assuming a single solid outright, since it costs
    # nothing when there is exactly one and this is the check that would notice if the
    # single-solid invariant ever regressed.
    d = []
    for solid in wall.Solids:
        loops = [w for w in solid.slice(App.Vector(0, 0, 1), z) if w.isClosed()]
        if not loops:
            continue
        # **Sorted by enclosed area, not by perimeter length.** Length only tracks which loop is
        # outer while both are convex-ish; once a rib cut makes the inner loop trace in and back
        # out around the notch (this function's own docstring above), that detour can add more
        # perimeter than the smooth outer loop has, without the inner loop enclosing anywhere
        # near as much area. Found 2026-09-25 (IP-FC-143): at `tail_shell` `U` = 3.0,
        # `z` = -217.7270, the two loops' lengths differ by under 0.25% (1601.84 vs 1598.18 mm)
        # -- close enough that which one length calls "outer" is not reliable -- while their
        # enclosed areas are not remotely close, since one is the true exterior and the other is
        # the cavity retreating deep inward around a rib. Area tracks "which region is bigger"
        # directly, however convoluted either loop's own path is.
        loops.sort(key=lambda w: abs(ci._wire_area(w)), reverse=True)
        if len(loops) >= 2 and not _is_annulus(loops):
            # **A section that is not an annulus has no thickness to report, and returning one is
            # how a hole in the wall read as a thinning.** The pairing above is only a wall
            # measurement if the second loop lies INSIDE the first. When the ring comes apart into
            # arcs, each arc's own boundary is a separate closed loop, and the code below then
            # measures the distance from one arc to the other -- the gap across the break -- and
            # reports it as a thickness. Measured 2026-10-05 on `tail_shell` at `U` = 3.0: a wall
            # whose ring was broken over 93.2 mm of 1600, with both arcs at a correct 0.612 and
            # 0.613 mm, was reported at 0.355705 mm, and every check in the build passed it
            # (cowl.md OQ-DES-CW26). `None` is the right answer, not a number: it is what this
            # function already returns for a station with no wall, and both callers already treat
            # that as a failure rather than skipping it.
            return None
        if len(loops) >= 2:
            outer = ci._Polyline(
                [(p.x, p.y) for p in loops[0].discretize(Number=8 * AROUND)])
            for p in loops[1].discretize(Number=AROUND):
                d.append(outer.distance(p.x, p.y))
        else:
            # A piece whose section is a single loop is a strip: its own width is the wall.
            # `2 * area / perimeter` is that width for a long thin region, exact in the limit
            # and 0.1% low at the aspect ratios here.
            area = abs(ci._wire_area(loops[0]))
            if loops[0].Length > 0.0:
                d.extend([2.0 * area / loops[0].Length] * 8)
    if len(d) < 2:
        return None
    d = sorted(d)
    near = sum(1 for v in d if abs(v - expect) <= tol)
    return len(d), near, d[0], d[len(d) // 2], d[-1]


def in_plane_width(tool, t_cut):
    """How wide a layer plane cuts this notch, from the notch's own orientation.

    **Trigonometry, not a measurement.** A slab of thickness `d` whose unit normal is `n` meets
    a horizontal plane in a strip of width `d / hypot(n.x, n.y)`: within that plane the normal
    direction only advances by its horizontal component, so a slab tilted out of vertical cuts
    wider than it is thick. A vertical cut has `hypot = 1` and reads `t_cut`.

    The tail's diagonal buttresses are the case that matters. `top_diag_buttress` extrudes to
    `buttress_cut_thickness` and then applies `rotate([30, 0, 0])`, which takes the normal from
    (0, 0, 1) to (0, -0.5, 0.866); `hypot(0, -0.5)` is 0.5, so a 0.1 mm cut is 0.2 mm wide in
    the layer plane and the rib gap it leaves is 1.4 mm rather than 1.3 mm. Measured 2026-09-03
    at U = 1: every `Diag*Safe` section is 0.2000 mm, every other one 0.1000 to 0.1064.

    Deriving it is what makes this an acceptance test rather than a tautology. Reading the width
    off the section and adding `2t` would confirm only that the dilation added `2t` -- it would
    pass a notch cut to the wrong thickness. Starting from `t_cut` and the tool's orientation
    tests the notch as well as the erosion.

    The normal comes from the tool's largest planar face, which on a slab is one of the two
    faces that give it its thickness.
    """
    planar = [f for f in tool.Faces if isinstance(f.Surface, Part.Plane)]
    if not planar:
        raise ci.PreconditionFailed(
            'a cutting tool spanning z %.4f..%.4f has no planar face, so it is not a slab and '
            'its thickness has no direction.'
            % (tool.BoundBox.ZMin, tool.BoundBox.ZMax))
    face = max(planar, key=lambda f: f.Area)
    n = face.Surface.Axis
    n.normalize()
    flat = math.hypot(n.x, n.y)
    if flat < 1.0e-9:
        # **P4, and it raises rather than returning None.** A horizontal cut has no in-plane
        # width, so there is no rib to check -- but returning `None` here and letting the
        # caller `continue` is how a design-domain violation used to leave no trace at all: the
        # notch dropped out of the rib check and the part reported OK. The build now refuses
        # such a tool in `cowl_interior.dilated_notches`, so reaching this line means the
        # assertion there has been weakened or bypassed, which is worth saying loudly.
        raise ci.PreconditionFailed(
            'P4: a cutting tool spanning z %.4f..%.4f lies in the layer plane. It leaves no '
            'rib, and the build should have refused it before this check ran.'
            % (tool.BoundBox.ZMin, tool.BoundBox.ZMax))
    return t_cut / flat


def rib_gap(body, notches, z, t, t_cut):
    """The width the erosion leaves at each notch, against that notch's own in-plane width.

    Measured on the dilated notch rather than asserted from the arithmetic. The erosion removes
    a `t`-neighbourhood of the notch from each side, so the gap it leaves is the notch's width
    plus `2t`, and that gap *is* the rib. The rib is not modelled anywhere; it falls out of the
    erosion, which is the confirmation that the erosion is the right operation (algorithm
    document section 4.2).

    **The width compared against is derived by `in_plane_width`, not measured off the
    section.** `t_cut` is
    the thickness of the cutter, and only a cutter standing vertically has an in-plane section
    that thick. The tail's diagonal buttresses do not: `top_diag_buttress` extrudes to
    `buttress_cut_thickness` and then applies `rotate([30, 0, 0])`, so the slab's normal sits
    30 degrees off z and a horizontal plane cuts it 0.1 / sin(30) = 0.2000 mm wide. Measured
    2026-09-03 on the tail at U = 1, every `Diag*Safe` section is 0.2000 mm and every other one
    is 0.1000 to 0.1064, and the gaps that came out were 1.4000 and 1.3000 to 1.3064
    respectively -- all of them exactly their own width plus 1.2.

    Asserting one global `t_cut + 2t` called the diagonals 0.1 mm wrong when the construction
    had them exactly right. The wall the printer lays down at an inclined cut really is wider
    than the cut is thick, and that is a property of the design rather than an error in it.

    Returns `(width, gap)` per notch, so the caller can report both.

    **Eroded by `open_arc`/`eroded_arc`, the same route `cavity()` itself takes -- not
    `ci.eroded_body()`.** `body` is the un-mirrored symmetry cell (`tip.Body`, "the same cell
    before any notch reached it"), so its raw section at any `z` is a closed loop only in the
    topological sense: part of it is the cell's own straight construction boundary, not OML.
    `eroded_body()` (superseded 2026-09-21, when `cavity()` moved to the cell/arc method) fits
    one periodic B-spline through the *whole* raw loop, straight edge included -- exactly the
    anti-pattern `cell_boundary_planes`'s own comment names ("cannot hold a straight
    construction edge straight and a curved OML edge curved at the same point, so it rounds the
    corner"). That is what this function did until this fix, and it is why it raised P3 on
    essentially every real station regardless of sample count: the corner it was rounding is a
    real, fixed feature of the section, not a sampling shortfall, so no ladder rung converges on
    it. Stripping the construction boundary first (`open_arc`) and refitting only the true arc
    (`eroded_arc`) is what `cavity()` already does and never had this failure, so the eroded
    interior here is closed the same way: the arc's own two ends, snapped exactly onto the
    cell's plane(s) by `eroded_arc`, closed with a straight segment (one cell plane) or two
    straight segments through the axis point (two cell planes, meeting only there) -- which is
    the cell's own true pie-slice or "D" cross-section, not an approximation of it.
    """
    planes = ci.cell_boundary_planes(body)
    wires = ci._slice_wires(body, z)
    if len(wires) != 1:
        raise ci.PreconditionFailed(
            'P2: the cell body sections into %d loops at z = %.4f, not one' % (len(wires), z))
    arc, p_start, p_end, flip = ci.open_arc(wires[0], planes)
    xy = ci.eroded_arc(arc, t, z, p_start, p_end, flip)
    pts = [App.Vector(x, y, z) for x, y in xy]
    if len(planes) == 1:
        face = Part.Face(Part.makePolygon(pts + [pts[0]]))
    else:
        axis = App.Vector(0.0, 0.0, z)
        face = Part.Face(Part.makePolygon(pts + [axis, pts[0]]))
    widths = []
    for tool in notches.Solids:
        want = in_plane_width(tool, t_cut)
        for w in ci._slice_wires(tool, z):
            if not w.isClosed():
                continue
            clipped = Part.Face(w).common(face)
            if not clipped.Faces:
                continue
            # **The clip decides whether the tool cuts at this station; the *unclipped* section
            # is what gets dilated.** `common` returns a compound, which `makeOffset2D` refuses
            # outright -- "input shape is not an edge, wire or face or compound of those" -- and
            # offsetting the clip would in any case measure a different thing from the
            # construction, which dilates the whole tool
            # (`cowl_interior.dilated_notches`).
            grown = Part.Face(w).makeOffset2D(t, 0, False, False, True)
            # The dilated slab is thin in one direction and long in the other, so the short
            # side of its bounding box is the gap. Reported per notch rather than averaged,
            # because an averaged rib thickness hides a rib smoothed away at one end.
            bb = grown.BoundBox
            widths.append((want, min(bb.XLength, bb.YLength)))
    return widths


def main():
    kind = _opt('kind', 'tail_shell')
    # **Opt-in, off by default (OQ-DES-CW24).** `cowl_interior.clearance_margin_scan` costs on
    # the order of an hour on top of an ordinary build, so it is never run unless asked for --
    # `--clearance-check` forces a second recompute with `tip.ClearanceCheck` set, which only
    # re-executes `_CowlShell` (the one object whose input property changed), not the build
    # upstream of it.
    clearance_check = '--clearance-check' in sys.argv
    builder = {'tail_shell': cowl_tree.tail_shell,
               'nose_cowl_shell': cowl_tree.nose_cowl_shell}[kind]
    params = {'tail_shell': cowl_tree.PARAMS_TAIL_SHELL,
              'nose_cowl_shell': cowl_tree.PARAMS_NOSE_COWL_SHELL}[kind]

    doc = App.newDocument('check')
    tip = cowl_tree.emit(doc, None, params, builder)
    if clearance_check:
        tip.ClearanceCheck = True
    doc.recompute()

    wall = tip.Shape
    notched = tip.Base.Shape
    body = tip.Body.Shape
    t = tip.Inset
    t_cut = float(doc.getObject('Params').get('buttress_cut_thickness'))

    print('%s: wall %.4f mm3  valid=%s  solids=%d  shells=%d'
          % (kind, wall.Volume, wall.isValid(), len(wall.Solids), len(wall.Shells)))
    print('  notched blank %.4f mm3   cavity %.4f mm3   wall is %.2f%% of the blank'
          % (notched.Volume, notched.Volume - wall.Volume,
             100.0 * wall.Volume / notched.Volume))
    print('  inset t = %.4f mm (cowl_n_perimeters * extrusion_width), '
          'buttress_cut_thickness = %.4f mm' % (t, t_cut))

    # -- the wall, in the layer plane
    #
    # **The z range is bisected for, not read off the bounding box.** `Shape.BoundBox` is loose
    # on a NURBS solid -- it reports the nose body as z = -100..0 where the part runs -50..-6 --
    # so stations taken from it land outside the part, find no wall there, and were counted as
    # failures. Measured 2026-09-03: three of the nose's twelve stations, at z = -60.1587,
    # -54.7806 and -1.0000, on a wall that passed at every station it actually has one.
    # `ci.z_extent` exists for exactly this and is given the body, which is one solid.
    lo, hi = ci.z_extent(body)
    lo, hi = lo + 1.0, hi - 1.0
    # **`WALL_TOL`, not `TAU`, and one-sided.** Corrected 2026-10-05: this is the acceptance test
    # on the finished wall's thickness, and it had been running at `TAU` = 0.05 mm -- the fit's own
    # convergence criterion -- which is five times looser than the thickness requirement. The
    # constant's own note says why 0.01 mm is the right figure and why only the thin side counts.
    # The reported `near` count stays two-sided, because it is informational and a rib legitimately
    # reads high; only `worst_low` gates.
    print('  wall thickness in the layer plane, expecting %.3f mm, no sample under %.3f '
          '(WALL_TOL = %.3f, one-sided):' % (t, t - ci.WALL_TOL, ci.WALL_TOL))
    bad = 0
    worst_thin = 0.0
    for i in range(STATIONS):
        z = lo + (hi - lo) * i / float(STATIONS - 1)
        got = wall_thickness(wall, z, t, ci.WALL_TOL)
        if got is None:
            print('    z %9.4f   fewer than two loops -- no wall here' % z)
            bad += 1
            continue
        n, near, lowv, med, highv = got
        thin_by = max(0.0, t - lowv)
        worst_thin = max(worst_thin, thin_by)
        flag = '' if lowv >= t - ci.WALL_TOL else '   <-- THIN by %.4f mm' % thin_by
        if lowv < t - ci.WALL_TOL:
            bad += 1
        print('    z %9.4f   %3d/%3d within tol   min %.4f  median %.4f  max %.4f%s'
              % (z, near, n, lowv, med, highv, flag))
    print('    worst thin reading: %.4f mm under nominal, %.1fx the %.3f mm tolerance'
          % (worst_thin, worst_thin / ci.WALL_TOL, ci.WALL_TOL))
    if worst_thin > ci.WALL_TOL:
        # **What a failure here does and does not mean.** `worst_low` is a nearest-point minimum,
        # and that quantity does not converge on these sections (IP-FC-151): it was still falling
        # at 3840 inner samples at 17 of 24 stations, because a nearest-point distance at a concave
        # corner crosses the corner rather than the wall and there is such a corner at every slot
        # mouth. So this reading is a lower bound on the deviation, from a measure that cannot
        # settle. The honest reading of a failure is "compliance with WALL_TOL is not demonstrated",
        # not "the wall is demonstrably this thin" -- and reporting OK instead would be the worse
        # error, since a check that cannot show compliance has not shown it.
        print('    NOTE: this is a nearest-point minimum, which does not converge on these '
              'sections (IP-FC-151). Read it as "WALL_TOL compliance is not demonstrated", not '
              'as a settled deviation. The converged area-based mean at the one station measured '
              'that way is 0.0033 mm from nominal, inside tolerance.')

    # -- the rib
    shapes = [n.Shape for n in tip.Notches]
    for text in tip.Mirrors:
        normal = App.Vector(*[float(v) for v in text.split(',')])
        normal.normalize()
        shapes = shapes + [s.mirror(App.Vector(0, 0, 0), normal) for s in shapes]
    notches = Part.makeCompound(shapes)
    print('  rib gap left by the erosion, expecting t_cut/hypot(nx, ny) + %.3f mm per notch '
          '(t_cut = %.4f, so %.3f for a vertical cut):' % (2.0 * t, t_cut, t_cut + 2.0 * t))
    for i in range(3):
        z = lo + (hi - lo) * (i + 1) / 4.0
        # Found while auditing IP-TEST-7 (doc/implementation/test_coverage.md): an uncaught
        # ci.PreconditionFailed here crashed the whole script before it ever printed a verdict
        # -- and freecadcmd's own exit code is unreliable on an uncaught script exception (see
        # doc/guidelines -- it prints "Exception while processing file" and still exits 0), so
        # this read as a clean pass to any caller checking only the exit code. A real
        # precondition failure on real geometry belongs in `bad`, not in an uncaught exception.
        try:
            pairs = rib_gap(body, notches, z, t, t_cut)
        except ci.PreconditionFailed as exc:
            print('    z %9.4f   PRECONDITION FAILED: %s' % (z, exc))
            bad += 1
            continue
        if not pairs:
            print('    z %9.4f   no notch cutting here' % z)
            continue
        # **This one keeps `TAU` rather than moving to `WALL_TOL`, deliberately.** The rib gap is
        # `t_cut / sin(theta) + 2t`, so two wall thicknesses do enter it -- but what this compares
        # is a measured gap against its own closed-form construction value, which makes it a
        # construction identity rather than a thickness acceptance test. It measures at floating
        # point noise on every build tried (~1e-13 mm, IP-FC-143), thirteen orders inside either
        # figure, so the choice of tolerance here changes no verdict. Noted rather than switched
        # because switching it would imply the quantity had been mis-toleranced, and it had not.
        worst = max(abs(gap - (width + 2.0 * t)) for width, gap in pairs)
        gaps = [gap for _width, gap in pairs]
        print('    z %9.4f   %2d notches   %.4f .. %.4f   worst error %.4f%s'
              % (z, len(pairs), min(gaps), max(gaps), worst,
                 '   <-- OFF' if worst > ci.TAU else ''))
        if worst > ci.TAU:
            bad += 1
            for width, gap in sorted(pairs, key=lambda q: -abs(q[1] - (q[0] + 2.0 * t)))[:4]:
                print('        notch %.4f wide -> gap %.4f, wanted %.4f'
                      % (width, gap, width + 2.0 * t))

    # -- the preconditions fire
    try:
        ci._check_slope([(10.0, 0.0)], [(10.5, 0.0)], 0.0, 0.1, 35.0)
        print('  P1 did NOT fire on a deliberately shallow section  <-- FAIL')
        bad += 1
    except ci.PreconditionFailed:
        print('  P1 fires on a deliberately shallow section')
    try:
        mid = 0.5 * (lo + hi)
        planes = ci.cell_boundary_planes(body)
        arc, p_start, p_end, flip = ci.open_arc(body.slice(App.Vector(0, 0, 1), mid)[0], planes)
        ci.eroded_arc(arc, 1.0e4, mid, p_start, p_end, flip)
        print('  P2 did NOT fire on an erosion that annihilates the section  <-- FAIL')
        bad += 1
    except ci.PreconditionFailed:
        print('  P2 fires on an erosion that annihilates the section')
    try:
        flat_tool = Part.makeBox(10.0, 10.0, t_cut, App.Vector(-5.0, -5.0, 0.5 * (lo + hi)))
        ci.dilated_notches(Part.makeCompound([flat_tool]), t)
        print('  P4 did NOT fire on a notch lying in the layer plane  <-- FAIL')
        bad += 1
    except ci.PreconditionFailed:
        print('  P4 fires on a notch lying in the layer plane')

    # -- the station floor (IP-FC-144, OQ-DES-CW24 alternative 2)
    floor = ci.station_floor(t)
    if floor < t - 1e-12:
        print('  station floor %.4f is below the wall %.4f  <-- FAIL' % (floor, t))
        bad += 1
    else:
        print('  station floor is the wall thickness, %.4f mm' % floor)
    # the real defect this fixes: a uniform seed station and a notch edge 0.0009 mm apart
    near = ci._thin_stations([-300.0, -60.0009, -60.0, -30.0, 0.0], floor)
    if any(b - a < floor - 1e-12 for a, b in zip(near, near[1:])):
        print('  _thin_stations left a pair closer than the floor: %s  <-- FAIL' % (near,))
        bad += 1
    elif near[0] != -300.0 or near[-1] != 0.0:
        print('  _thin_stations moved an end station: %s  <-- FAIL' % (near,))
        bad += 1
    else:
        print('  _thin_stations removes a 0.0009 mm pair and keeps both ends')
    # an end station must survive even when its neighbour crowds it
    ends = ci._thin_stations([0.0, 1.0, 1.0 + 0.5 * floor], floor)
    if ends[-1] != 1.0 + 0.5 * floor or any(
            b - a < floor - 1e-12 for a, b in zip(ends, ends[1:])):
        print('  _thin_stations dropped or crowded the last station: %s  <-- FAIL' % (ends,))
        bad += 1
    else:
        print('  _thin_stations keeps the last station, displacing its neighbour')

    # -- the face roles the clearance minimum is classified against (IP-FC-148, OQ-DES-CW25)
    #
    # Checked on the real cutting tools rather than on a constructed stand-in, because what these
    # assertions are really guarding is that the labels still mean what OQ-DES-CW25 asks about
    # after whatever the next change to the buttress profile turns out to be. A slab has exactly
    # two cheeks and they are antiparallel; exactly one face of each profile is the far edge that
    # cuts nothing; and every tool has a cut floor, or there is nothing for the minimum to land on.
    role_bad = 0
    for i, raw in enumerate([n.Shape for n in tip.Notches]):
        for solid in raw.Solids:
            roles = ci.tool_face_roles(solid)
            cheeks = [r for r in roles if r['role'] == 'cheek']
            outers = [r for r in roles if r['role'] == 'outer']
            floors = [r for r in roles if r['role'] == 'floor']
            if len(cheeks) != 2:
                print('  tool %d has %d cheek face(s), not 2  <-- FAIL' % (i, len(cheeks)))
                role_bad += 1
            elif cheeks[0]['normal'].dot(cheeks[1]['normal']) > -0.999:
                print('  tool %d\'s two cheeks are not antiparallel (dot %.4f)  <-- FAIL'
                      % (i, cheeks[0]['normal'].dot(cheeks[1]['normal'])))
                role_bad += 1
            if len(outers) != 1:
                print('  tool %d has %d far face(s), not 1  <-- FAIL' % (i, len(outers)))
                role_bad += 1
            if not floors:
                print('  tool %d has no cut floor  <-- FAIL' % i)
                role_bad += 1
    if role_bad:
        bad += role_bad
    else:
        print('  tool_face_roles: every tool has 2 antiparallel cheeks, 1 far face and a floor')
    # `closest` has to return the distance `distances` returns, or the face a minimum is
    # attributed to is not the face the reported minimum is on.
    square = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    probes = [(2.0, 1.0), (-1.5, 1.5), (4.0, 3.0), (2.0, 7.0)]
    line = ci._Polyline(square)
    want = float(min(line.distances(probes)))
    got = line.closest(probes)
    if got is None or abs(got[0] - want) > 1.0e-12:
        print('  _Polyline.closest disagrees with distances: %s against %.12f  <-- FAIL'
              % (got, want))
        bad += 1
    else:
        print('  _Polyline.closest agrees with distances to %.1e mm' % abs(got[0] - want))

    # -- the clearance margin (OQ-DES-CW24), opt-in only
    if clearance_check:
        print('  clearance margin (Metric A, OQ-DES-CW24): %d station(s) under %.3f mm, '
              'worst %.6f mm -- flag-only, does not fail the build'
              % (tip.ThinWallFlags, ci.CLEARANCE_MARGIN_MM, tip.WorstClearanceMargin))
        print('    whether this metric is kept at all is OQ-DES-CW25 (cowl.md); its companion '
              'ratio was removed 2026-10-04, it did not measure tool-to-tool crowding')

    print('%s: %s' % (kind, 'OK' if bad == 0 else '%d CHECK(S) FAILED' % bad))
    sys.stdout.flush()
    return 1 if bad else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
