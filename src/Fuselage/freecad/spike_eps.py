"""IP-FC-50: does OCCT need `eps` at all, and where?

`eps` (0.01 mm, `geometry_eps()` in shape_modifier_utils.scad) is inherited from the OpenSCAD
source, where it does three different jobs that the port had been carrying as one:

  A  UNION OVERLAP    -- two solids that meet on an exact shared plane are made to
                        interpenetrate by eps before being fused.
  B  CUT OVERSHOOT    -- a subtractive tool is made to poke out past the face it cuts
                        through, rather than ending flush with it.
  C  A REAL DIMENSION -- eps appears inside an expression that sizes material, so removing
                        it moves a surface. Not a robustness margin at all.

A was settled for the octant mask by IP-FC-49: OCCT fuses a solid with its own mirror about
the exact touching plane cleanly, and the sliver actively breaks the fuse at large U. This
spike asks the same question of the two cases IP-FC-49 did not cover:

  A2  an abutting fuse where the two solids have DIFFERENT cross-sections at the junction,
      which is the corner's end/transition/middle stack -- not a mirror pair;
  B   a cut whose tool cap is exactly coplanar with the face it exits through.

Each is measured against the analytic answer at four scales, because the failures IP-FC-49
found were scale-dependent: 0.01 mm is 1e-3 of a 10 mm part and 4e-5 of a 250 mm one, and
OCCT's tolerance is absolute.

RESULTS, and the one that matters most is the exception:

  B, flush cut     no benefit at any scale. Identical volume to machine precision, same
                   solid count, and the SAME OR FEWER faces than the padded version.
  B, tangent cut   exact here -- but this test is weaker than it looks, and believing it
                   in general is wrong. See below.
  A2, abut vs pad  both valid, but the padded fuse carries two extra faces, and the pad is
                   NOT free the way the octant mask's was: where the two cross-sections
                   differ, moving one solid by eps moves real material.

**The tangent result does not generalize, and the port has a counterexample.** In this
spike the tangent plane bounds nothing that is removed, so OCCT never has to construct the
intersection curve, and the answer is exact. In `corner_tree._greeble_wedge` the tangent
flank bounds a cut region -- the wedge's sides sit on `greeble_nub_radius`, tangent to the
nub cylinder they cut across. Exact arithmetic says tangency changes nothing there, because
the tool still covers the whole chord. OCCT under-removes by 0.0199 mm^3. So that eps stays,
and the rule is: **tangency is safe when it is incidental, and unsafe when the boolean
depends on it.** A spike that only measures the safe case will tell you the wrong thing.

Run: freecadcmd spike_eps.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

from corner_common import is_entry_point

V = App.Vector
SCALES = [10.0, 100.0, 250.0, 400.0]
EPS = 0.01


def _box(lx, ly, lz, x=0.0, y=0.0, z=0.0):
    return Part.makeBox(lx, ly, lz, V(x, y, z))


def _check(shape, want):
    """(valid, solids, faces, relative volume error) against an analytic volume."""
    return (shape.isValid(), len(shape.Solids), len(shape.Faces),
            (shape.Volume - want) / want)


def cut_through(s, overshoot):
    """B: a bore cut clean through a slab. Tool caps flush at overshoot = 0."""
    body = _box(2 * s, 2 * s, s)
    r = s / 4.0
    tool = Part.makeCylinder(r, s + 2 * overshoot, V(s, s, -overshoot))
    want = 4 * s * s * s - math.pi * r * r * s
    return _check(body.cut(tool), want)


def cut_side(s, overshoot):
    """B: a notch cut in from the side, tool flush with the slab's outer face."""
    body = _box(2 * s, 2 * s, s)
    w = s / 4.0
    tool = _box(w + overshoot, w, s + 2 * overshoot, 2 * s - w, s, -overshoot)
    want = 4 * s * s * s - w * w * s
    return _check(body.cut(tool), want)


def fuse_stack(s, overlap):
    """A2: two DIFFERENT cross-sections stacked, meeting exactly at overlap = 0.

    Not the IP-FC-49 mirror case: the upper solid's footprint is a strict subset of the
    lower's, so the shared plane carries a real step. The analytic volume is only the sum
    when overlap is 0 -- with an overlap the band z in [s - overlap, s] is counted once
    rather than twice, and the union is SMALLER than the sum by the step's area times the
    overlap. That difference is the thing to notice: the overlap is not free here, the way
    it was for the octant mask.
    """
    lower = _box(2 * s, 2 * s, s)
    upper = _box(s, s, s, 0.0, 0.0, s - overlap)
    want = 4 * s * s * s + s * s * s - (4 * s * s - s * s) * 0.0
    got = lower.fuse(upper)
    # analytic union: lower + upper, less the part of upper inside lower
    want = 4 * s * s * s + s * s * (s - overlap) + s * s * overlap
    return _check(got, want)


def cut_tangent(s, overshoot):
    """B, the hard variant: the tool's side face is TANGENT to a curved face, not flush
    with a flat one.

    This is the greeble mouth and the transition relief -- a straight-edged cut tool sized
    exactly to a radius, so its face touches the cylinder along a single line rather than
    crossing it. Tangency is a different question from coplanarity: a plane meeting a
    cylinder at one line is the case where a kernel has to decide whether an intersection
    curve exists at all, and the answer is not stable under rounding the way a flat/flat
    coincidence is. Tested separately for exactly that reason.
    """
    r = s / 4.0
    body = Part.makeCylinder(r, s)
    # a slab whose inner face sits at x = r - overshoot, i.e. tangent when overshoot = 0
    tool = _box(2 * s, 4 * s, 3 * s, r - overshoot, -2 * s, -s)
    if overshoot == 0.0:
        want = math.pi * r * r * s               # tangent: nothing removed
    else:
        # circular segment of height `overshoot`, times the height
        d = r - overshoot
        seg = r * r * math.acos(d / r) - d * math.sqrt(max(r * r - d * d, 0.0))
        want = math.pi * r * r * s - seg * s
    return _check(body.cut(tool), want)


def _row(label, s, res):
    valid, solids, faces, err = res
    return ('  %-22s %7.1f   %-5s %6d %6d   %+.3e'
            % (label, s, 'valid' if valid else 'INVALID', solids, faces, err))


def main():
    print('SPIKE:: does OCCT need eps?   (eps = %g mm)' % EPS)
    print('')
    print('B -- cut overshoot: is a tool cap coplanar with the exit face a problem?')
    print('  %-22s %7s   %-5s %6s %6s   %s'
          % ('case', 'scale', 'ok', 'solids', 'faces', 'vol error'))
    for s in SCALES:
        print(_row('through, flush', s, cut_through(s, 0.0)))
        print(_row('through, +eps', s, cut_through(s, EPS)))
    for s in SCALES:
        print(_row('side notch, flush', s, cut_side(s, 0.0)))
        print(_row('side notch, +eps', s, cut_side(s, EPS)))
    for s in SCALES:
        print(_row('tangent, flush', s, cut_tangent(s, 0.0)))
        print(_row('tangent, +eps', s, cut_tangent(s, EPS)))
    print('')
    print('A2 -- abutting fuse, different cross-sections (the axial section stack):')
    print('  %-22s %7s   %-5s %6s %6s   %s'
          % ('case', 'scale', 'ok', 'solids', 'faces', 'vol error'))
    for s in SCALES:
        print(_row('stack, abutting', s, fuse_stack(s, 0.0)))
        print(_row('stack, +eps', s, fuse_stack(s, EPS)))
    print('')
    print('  vol error is against the analytic volume of the intended shape.')


if is_entry_point(__name__):
    main()
