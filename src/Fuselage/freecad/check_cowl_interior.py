"""IP-FC-17: the acceptance tests section 6 of the algorithm document states.

    freecadcmd check_cowl_interior.py --pass --kind=tail_shell

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


def wall_thickness(wall, z, expect, tol):
    """In-plane distance from the inner contour to the outer, at one station.

    Returns `(n, near, worst_low, median, worst_high)` -- how many samples, how many landed
    within `tol` of `expect`, and the spread. Samples over a rib legitimately read more than
    `expect`, because the wall follows the notch in and back out and the inner contour dips
    with it; samples reading *less* are the failure, and there should be none.
    """
    # **Measured per solid, because a shelled cowl need not be one.** The tail's buttress
    # slots cut through the full depth of the wall, so it comes out in five pieces
    # (`build_part.MULTI_SOLID_KINDS` records the measurement). Taking the two longest loops of
    # the whole section pairs an outer loop of one piece with an inner loop of another and
    # reports a distance across the cavity rather than across the wall -- 13 to 31 mm against a
    # 0.6 mm wall, which is how this check read before it was fixed.
    d = []
    for solid in wall.Solids:
        loops = [w for w in solid.slice(App.Vector(0, 0, 1), z) if w.isClosed()]
        if not loops:
            continue
        loops.sort(key=lambda w: w.Length, reverse=True)
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
        return None
    face = max(planar, key=lambda f: f.Area)
    n = face.Surface.Axis
    n.normalize()
    flat = math.hypot(n.x, n.y)
    if flat < 1.0e-9:
        return None                                    # a horizontal cut has no in-plane width
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
    """
    _refit, face, _inner = ci.eroded_body(body.slice(App.Vector(0, 0, 1), z)[0], t, z)
    widths = []
    for tool in notches.Solids:
        want = in_plane_width(tool, t_cut)
        if want is None:
            continue
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
    builder = {'tail_shell': cowl_tree.tail_shell,
               'nose_cowl_shell': cowl_tree.nose_cowl_shell}[kind]
    params = {'tail_shell': cowl_tree.PARAMS_TAIL_SHELL,
              'nose_cowl_shell': cowl_tree.PARAMS_NOSE_COWL_SHELL}[kind]

    doc = App.newDocument('check')
    tip = cowl_tree.emit(doc, None, params, builder)
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
    print('  wall thickness in the layer plane, expecting %.3f mm within %.3f:' % (t, ci.TAU))
    bad = 0
    for i in range(STATIONS):
        z = lo + (hi - lo) * i / float(STATIONS - 1)
        got = wall_thickness(wall, z, t, ci.TAU)
        if got is None:
            print('    z %9.4f   fewer than two loops -- no wall here' % z)
            bad += 1
            continue
        n, near, lowv, med, highv = got
        flag = '' if lowv >= t - ci.TAU else '   <-- THIN'
        if lowv < t - ci.TAU:
            bad += 1
        print('    z %9.4f   %3d/%3d within tol   min %.4f  median %.4f  max %.4f%s'
              % (z, near, n, lowv, med, highv, flag))

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
        pairs = rib_gap(body, notches, z, t, t_cut)
        if not pairs:
            print('    z %9.4f   no notch cutting here' % z)
            continue
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
        ci.eroded_body(body.slice(App.Vector(0, 0, 1), mid)[0], 1.0e4, mid)
        print('  P2 did NOT fire on an erosion that annihilates the section  <-- FAIL')
        bad += 1
    except ci.PreconditionFailed:
        print('  P2 fires on an erosion that annihilates the section')

    print('%s: %s' % (kind, 'OK' if bad == 0 else '%d CHECK(S) FAILED' % bad))
    sys.stdout.flush()
    return 1 if bad else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
