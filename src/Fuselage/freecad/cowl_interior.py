"""IP-FC-17: the cowl's interior surface, and the shelled solid it closes.

Implements [doc/design/cowl_interior_surface.md](../../../doc/design/cowl_interior_surface.md),
which is IP-FC-16 and states the method. This module is the construction; that document is
the specification, and where the two disagree the document is right and this is a defect.

**What this produces is the solid representation, never the print export.** Cowls print in
spiral vase mode, which spirals one contour per layer and admits no interior geometry at all,
so a cowl given a modelled inner surface is no longer vase-printable (OQ-DES-CW6,
[cowl.md](../../../doc/design/cowl.md) section 6.4). The un-shelled notched blank stays what
UC-1 exports. That is why the shelled cowls are separate *kinds* -- `nose_cowl_shell` and
`tail_shell` -- rather than an improvement applied to `nose_cowl` and `tail`: two kinds cannot
be mistaken for one another by a downstream consumer, where a flag on one kind can.

The construction, all of it in section 4 of the algorithm document:

    exterior A, notches B
      -> stations z0 ... zn          4.1  feature stations, then refined by 5
      -> sections A(z), B(z)
      -> eroded contours Cin(z)      4.2  by the morphological identity, in the layer plane
      -> consistent parameterization 4.3  arc-length from a geometric anchor
      -> fitted interior surface     4.4  C2 approximation, one patch per feature interval
      -> closed cavity, and the wall 4.5

**A is the un-notched masked body, and it is already in the tree.** Both cowls are built by
masking the scaled OML and then cutting a symmetry cell, so `Lower` -- the blank met with
`lower_mask` -- is the whole body before any notch reaches it, for the nose and the tail
alike. The mirrors that take the cut cell out to the whole part put the notches back over
exactly the region `Lower` already covers, so nothing has to be mirrored a second time to
recover A.

**The OCC entry point is chosen here because the algorithm document deliberately does not
choose one** (its section 8): it states the requirement and the acceptance test, and says an
API named without being measured would read as decided. Measured 2026-09-02 on FreeCAD 1.1.3,
fitting a 24-station superelliptic stack:

    Continuity  DegMax   result
    C1          3        GeomAPI_PointsToBSplineSurface: Surface not done
    C2          3        Surface not done
    C1          5        ok, degree 3, worst point deviation 0.00052 mm
    C2          5        ok, degree 5, worst point deviation 0.00049 mm   <- here
    C2          8        ok, degree 8, worst 0.00077 mm

So `Part.BSplineSurface.approximate` is the entry point, and **C2 is only reachable at
DegMax >= 5** -- the API says so and the measurement agrees, which means a *cubic* C2 fit is
not available through it at all. The interior therefore carries a higher degree than the
cubic exterior it is offset from, and the wall-thickness check is what establishes that this
does not matter in the one place it could.

`ParamType` is left unset deliberately. Naming any of the three -- Uniform, Centripetal,
ChordLength -- made the same fit sixteen times worse (0.0082 against 0.00049), because the
keyword selects a different overload of the underlying algorithm rather than a parameter of
the one above.
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import FreeCAD as App
import Part


#: Section 5: the tolerance on the **wall**, in millimetres, and **absolute at every `U`**.
#: The wall is `n_p * w` thick at every scale because extrusion width is a property of the
#: machine, so a tolerance that scaled with `U` would be 2% of the wall at U=0.5 and 67% of it
#: at U=4. The algorithm document states the reasoning and IP-FC-56 is the precedent for
#: getting it backwards.
#:
#: **What this bounds is the perimeter width, not the distance between two curves.** It used
#: to be the Hausdorff distance from the fitted contour to an ideal eroded contour, which is a
#: proxy: it bounds the wall only indirectly, and it made the acceptance test in
#: `check_cowl_interior` measure a different quantity from the one refinement converged on.
#: Section 5 now measures the wall itself -- in the layer plane, from the fitted interior out
#: to the exterior -- so the criterion and the acceptance test are the same measurement.
TAU = 0.05

#: The floor on interval length. **Reaching it is a failure to report, not a result to
#: accept** -- section 5 -- because it means the fitted surface does not represent the erosion
#: there and nothing downstream would know.
MIN_INTERVAL = 0.20

#: Circumferential spacing, in millimetres, for the grid the surface is **fitted through**,
#: and the range the resulting count is clamped to.
#:
#: **This is set by the shape being fitted, and that shape is smooth.** The surface follows the
#: eroded *body* only; the ribs are applied afterwards, as a solid, so no rib corner is ever
#: fitted through. What is left is a rounded rectangle, and interpolating one needs the points
#: a rounded rectangle needs.
#:
#: It used to be 0.075 mm, derived from the 1.3 mm rib gap the erosion leaves at a notch --
#: an argument about how finely the result must be *checked*, applied to how finely it is
#: *built*. That conflation is what made the construction unaffordable. Every comparison in
#: section 5 is a product of two sample counts, so the cost is quadratic in this number:
#: measured 2026-09-03 on the nose at U = 1, dropping it 32x took the cavity from 5266 s to
#: 30 s.
FIT_ARC = 1.0
FIT_MIN = 120
FIT_MAX = 1200

#: Circumferential spacing, in millimetres, for **evaluating** the fitted surface against the
#: wall tolerance, and the range that count is clamped to.
#:
#: **This is the one the rib sets.** A check that steps over a rib cannot see a wall violation
#: inside it, and the gap the erosion leaves at a notch is `t_cut + 2*n_p*w` = 1.3 mm, so the
#: spacing has to resolve that. 0.20 mm puts six or seven evaluation points across the
#: narrowest feature that can carry a violation.
#:
#: Evaluating is not fitting, and it is far cheaper: a point-to-curve distance against a
#: polyline, not an interpolation through a grid. Spending the samples here rather than in
#: `FIT_ARC` is the whole point of keeping the two apart.
CHECK_ARC = 0.20
CHECK_MIN = 480
CHECK_MAX = 6000

#: How many directions the ribs are dilated in. See `dilated_notches`: the structuring element
#: is a horizontal disc, and it is approximated by an inscribed regular polygon with this many
#: sides.
#:
#: **Chosen against the rib gap, which is the thing it has to get right.** Measured 2026-09-03
#: on the tail's first side slab at U = 1, whose 0.1004 mm section the exact 2-D offset dilates
#: to a 1.3004 mm gap:
#:
#:     n = 32    gap 0.3670 mm    volume 10543.589    <- wrong shape, not merely coarse
#:     n = 48    gap 1.3004 mm    volume 11096.319    4.0 s a tool
#:     n = 64    gap 1.3004 mm    volume 11097.462    8.6 s a tool
#:     n = 96    gap 1.3004 mm    volume 11098.575   23.6 s a tool
#:
#: 48 is the first count that reproduces the exact offset's gap, and going further buys three
#: parts in ten thousand of volume for twice the time.
RIB_FACETS = 48

#: Below this, a cutting slab's plane is horizontal and P4 is violated.
#:
#: **A numerical guard, not a design threshold.** The value is the sine of the angle between
#: the cut plane and the layer plane, so 1 is a vertical cut and 0 is a horizontal one; this
#: only separates "horizontal" from "not horizontal" through floating-point noise, and it is
#: deliberately not a limit on how shallow a cut may be. P4 says no notch *lies in* the layer
#: plane, because a rib forms only where the perimeter can walk into the notch and back out
#: within a layer -- a horizontal notch offers no such path and comes out malformed under
#: thin-wall perimeter slicing. It does not say a 5-degree cut is acceptable and a 4-degree one
#: is not. Nothing in the design is shallower than the tail's 30-degree diagonal, no minimum
#: angle is stated anywhere, and picking one here would be inventing a design decision in a
#: constant. If a floor is ever wanted it is an open question, not a number in this file.
#: Meanwhile `dilated_notches` reports the shallowest cut it saw, so a shallow one is visible
#: rather than silent.
FLAT_TOL = 1.0e-9

#: How much dilated rib may remain inside the finished cavity, in cubic millimetres.
#:
#: **Zero is the right answer and the measured one.** `cavity` subtracts the dilated ribs from
#: the smooth interior, so afterwards the two must not intersect at all: on a correct build,
#: measured 2026-09-04 on the tail at U = 1, `cavity.common(ribs)` is 0.000000 mm3 in 0 solids.
#:
#: **And this is the check that catches the failure the others miss.** The rib cut fails
#: *partially*, which nothing downstream notices. Measured on the same part: the wall is
#: 23745.5810 mm3 in one solid when every rib forms, 17041.8581 mm3 in five when the ribs are
#: not cut at all, and the bad builds came out around 22000 in five -- about a quarter of the
#: 6703.7229 mm3 of rib material missing. The ribs are what bridge the buttress slots, so
#: losing some of them is what separates the wall into pieces, and the partition identity in
#: `shell_solid` cannot see it because the result is still self-consistent: the cavity is
#: simply larger, and it eats the wall.
#:
#: The floor is five orders below that failure and three above the kernel's own reproducibility
#: on these operands.
RIB_RESIDUE = 1.0e-2

#: How many times finer the polyline a distance is *measured against* is than the sample set.
#:
#: **Three, not eight, because the sample set now carries the resolution.** When `CHECK_ARC`
#: was 0.3 mm this factor had to make up the difference on its own; at 0.075 mm a factor of 3
#: already puts 0.025 mm between the chords being measured against, which is a fiftieth of
#: `TAU`. Eight cost 40,832 points per contour on the tail -- one `discretize` and one polyline
#: build of that size for every station -- and measured 463 s a contour for accuracy nothing
#: needed.
#: **The measurement is curve-to-curve and the discretisation error has to sit well below
#: `TAU`.** Measured 2026-09-02: comparing 160 sampled points against a 160-point
#: parameter-spaced polyline of the same contour reported 0.076 mm where the true deviation
#: was 0.003 mm -- twenty-five times over, and over `TAU`, so the refinement chased its own
#: chord error down to the interval floor and reported a part that does not converge.
#: `discretize` spaces by *parameter*, not arc length, so its chords cut the corners wherever
#: the curve's speed varies, which on a rounded-rectangle section is everywhere.
DENSE_FACTOR = 3

#: Stations seeded in a patch before section 5 refines it, per millimetre of patch length,
#: and the range that is clamped to. **The seed is deliberately thin and the criterion is the
#: arbiter**, which is what "spacing is derived, not tuned" means: a patch seeded with two
#: stations and left there is one where the midpoint check found the surface already within
#: `TAU` of the erosion. Seeding six everywhere instead cost 23 minutes a part on a tail whose
#: 59 feature stations make 60 patches, most of them a fraction of a millimetre long, and
#: bought nothing the criterion did not already guarantee.
#: A patch at least this long is seeded with the six stations a C2 fit needs; a shorter one is
#: seeded with its two ends and left for section 5 to subdivide if the erosion turns out not to
#: be straight across it. Below six rows `approximate` cannot produce C2 at all -- it raises
#: `NCollection_Array1::Value`, measured 2026-09-02 -- so this is where the continuity ladder
#: in `_fit` gets its rows from.
SEED_LONG_MM = 3.0
SEED_MIN = 2
SEED_MAX = 6

#: Target spacing, in millimetres, for the uniform samples a section is refit through, and the
#: range the resulting count is clamped to. See `eroded_body` for why the spacing has to be
#: uniform and why there is a ladder above it.
SAMPLE_SPACING = 0.25
SAMPLE_MIN = 400
SAMPLE_MAX = 3000

#: How far a section may move when it is refit as one B-spline, in millimetres. A tenth of
#: `TAU`, because the refit is of the *exterior* the wall is measured from: an error here is
#: not a fitting error to be refined away but a changed part, and it would show up in the
#: wall-thickness check as a bias no station disagrees with.
REFIT_TOL = 0.005

#: Fuzzy tolerances tried, in order, for the one boolean that needs one: taking the dilated
#: notches out of the eroded section. Millimetres. Unused since the ribs became a 3-D cut; see
#: ladder climbed against the result rather than a single value.
#:
#: The ceiling is a fifth of `TAU`, which bounds the whole mechanism: whichever rung answers,
#: the section cannot have moved by more than that, and `TAU` is itself a twelfth of the wall.
CUT_FUZZ_LADDER = (1.0e-5, 1.0e-4, 1.0e-3, 1.0e-2)

#: Below this area, in square millimetres, a clipped notch section is a tangency artifact and
#: not a notch. The narrowest notch the design has is `buttress_cut_thickness` = 0.1 mm wide,
#: so even a 0.1 mm long one encloses 0.01 mm2 -- four orders above this.
SLIVER_AREA = 1.0e-6

#: Below this perimeter, in millimetres, a loop left by the notch subtraction is boolean debris
#: rather than a hole. See `_one_region`, which records why the floor sits where it does and
#: what it is checked against.
SLIVER_LENGTH = 0.01

#: How far inside its own end a station may sit. Sectioning exactly at a planar end returns the
#: end face's boundary rather than the body's, which is the same curve for a prismatic part and
#: not for this one.
END_INSET = 1.0e-3

#: How far past each open end the cavity is carried, so the ends are actually open. Any value
#: clear of `END_INSET` does; 1 mm is far enough to be unambiguous and short enough to stay
#: inside the blank's own bounding box arithmetic.
END_OVERRUN = 1.0

#: Two stations closer than this are one station.
Z_TOL = 1.0e-6

#: Slack on the P1 slope assertion, in degrees, for the discretisation the check runs on.
SLOPE_SLACK = 0.5

#: Angular half-window, in bins of one degree, searched when measuring a point against a
#: polyline. Both contours are star-shaped about the section centroid -- a 1.3 mm slot in a
#: body tens of millimetres across leaves them so -- which makes the nearest segment a local
#: one and turns an O(n*m) scan into an O(n) one. 25 degrees is far wider than any nearest
#: point observed and is what makes the pruning safe rather than merely fast.
ANGLE_WINDOW = 25


# **Do not test a section for emptiness with `Face.Area`.** A planar face built on a single
# closed periodic B-spline -- which is exactly what `smoothed()` produces and what every
# section here is -- reports an area that is simply wrong, while its geometry is right.
# Measured 2026-09-02 at three stations on the tail:
#
#     station     wire signed area   Face.Area    offset(-0.6) area
#     -97.9004         9912.153       7588.258         9683.637
#     -60.0000         7048.147       5800.412         6856.579
#     -42.5001         5045.318       5029.483         4883.383
#
# The signed area of the wire matches the un-refit section to 1e-5 relative, the perimeter
# matches to 1e-5, and the offsets match the un-refit section's offsets to 1e-5 -- so nothing
# about the curve is wrong. Only `Face.Area` is, and it is wrong by up to 23% and by a
# different amount at every station, which makes it read as a real geometric signal. This is
# `Shape.Volume` on a NURBS solid one dimension down (OQ-DES-CW12). Count faces, or take the
# signed area of the discretised wire.


def note(text):
    """One progress line, to stderr, flushed.

    **A build that says nothing for twenty minutes is indistinguishable from a hung one**, and
    this one legitimately takes that long: every station is three kernel booleans on a NURBS
    section, and a cowl has scores of them. Without this the only way to tell work from a hang
    is to watch the process's CPU time from outside, which is not a thing anyone should have to
    do to find out whether their machine is busy on purpose.
    """
    sys.stderr.write('    %s\n' % text)
    sys.stderr.flush()


class PreconditionFailed(Exception):
    """A property section 2 relies on does not hold of this input.

    Raised rather than worked around. Each of the three is a statement about the *design*,
    not about the kernel, so one failing means a part is outside the domain the method was
    written for and the answer is to say which station and stop -- not to emit the knife edge,
    which renders, exports, passes `isValid()` and resurfaces as a stress singularity in a
    UC-8 result nobody re-derives by hand.
    """


class Unconverged(Exception):
    """Section 5's floor was reached with the deviation still above `TAU`."""


# --------------------------------------------------------------------------------
# Plane geometry, in the layer plane
# --------------------------------------------------------------------------------

def _signed_area(pts):
    """Twice the signed area of a closed polyline, positive counter-clockwise about +z."""
    total = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        total += x1 * y2 - x2 * y1
    return total


def _wire_area(wire, n=200):
    """The area a closed wire encloses, from its own points rather than from `Face.Area`."""
    pts = [(p.x, p.y) for p in wire.discretize(Number=n)]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return abs(_signed_area(pts)) / 2.0


def _seg_distance(px, py, ax, ay, bx, by):
    """Distance from a point to a segment. Point-to-segment rather than point-to-point
    because section 5 measures against `TAU` = 0.05 mm and the sampling interval is 1 mm."""
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    if den <= 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / den
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class _Polyline(object):
    """A closed polyline you can measure many points against at once.

    **Vectorised because the measurement, not the geometry, was the cost.** Section 5 compares
    every sample of a contour against a dense polyline of another, both sides, at every
    midpoint of every patch -- and the sampling has to resolve a 1.3 mm rib, which puts
    thousands of points on each side. In pure Python that measured 70 s per contour and made
    the whole construction unaffordable at the resolution it actually needs. The arithmetic is
    a point-to-segment distance, which is the same three lines for every pair, so it belongs in
    numpy rather than in a loop.

    Queries run in chunks: the full (points x segments) matrix would be hundreds of megabytes
    at the resolutions this now uses, and nothing is gained by materialising it at once.
    """

    CHUNK = 256

    def __init__(self, pts):
        self.pts = pts
        a = np.asarray(pts, dtype=float)
        b = np.roll(a, -1, axis=0)
        self.ax, self.ay = a[:, 0], a[:, 1]
        self.dx, self.dy = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
        self.den = self.dx * self.dx + self.dy * self.dy
        self.den[self.den <= 0.0] = 1.0e-300

    def distances(self, points):
        """Distance from each of `points` to this polyline, as an array."""
        q = np.asarray(points, dtype=float)
        out = np.empty(len(q))
        for lo in range(0, len(q), self.CHUNK):
            hi = min(lo + self.CHUNK, len(q))
            px = q[lo:hi, 0][:, None]
            py = q[lo:hi, 1][:, None]
            t = ((px - self.ax) * self.dx + (py - self.ay) * self.dy) / self.den
            np.clip(t, 0.0, 1.0, out=t)
            ex = px - (self.ax + t * self.dx)
            ey = py - (self.ay + t * self.dy)
            out[lo:hi] = np.sqrt(np.min(ex * ex + ey * ey, axis=1))
        return out

    def distance(self, px, py):
        return float(self.distances([(px, py)])[0])


def hausdorff(a_samples, a_dense, b_samples, b_dense):
    """The two-sided Hausdorff distance between two closed contours.

    **Two-sided, per section 5 step 4.** One-sided misses a fitted contour that bulges outward
    where the true one has no material: every point of the true contour still has a fitted
    point near it, and the excursion goes unmeasured.

    Each side's *samples* are measured against the other side's *dense* polyline, so what is
    reported is the distance between the curves and not the distance between two coarse
    approximations of them.
    """
    return max(float(b_dense.distances(a_samples).max()),
               float(a_dense.distances(b_samples).max()))


# --------------------------------------------------------------------------------
# Sections and the erosion
# --------------------------------------------------------------------------------

def _slice_wires(shape, z):
    return shape.slice(App.Vector(0, 0, 1), z)


def smoothed(wire, n, tol=REFIT_TOL):
    """One closed cubic B-spline through a section, replacing the fragment chain OCC returns.

    **This is what makes the erosion possible at all, and it is not a nudge.** Sectioning the
    conditioned blank returns the section as one edge per surface patch -- 64 of them on the
    tail -- and on the smaller forward sections the shortest of those is under 0.05 mm. OCC's
    2-D offset refuses that input: measured 2026-09-02 over 81 stations, 19 returned
    `makeOffset2D: result of offsetting is null!`, every one of them forward of z = -42.5 where
    the section has shrunk enough to bring the fragments below a tenth of a millimetre. Neither
    join style, nor `intersection`, nor `removeSplitter`, nor a 1600-point polygon changed any
    of them; a single B-spline through the same points offset correctly on the first try.

    That is IP-FC-54's failure exactly -- the algorithm document's section 7 predicts it and
    warns that hunting for an offset distance that works leaves the defect in place. The defect
    here is the fragmentation, so the fragmentation is what is fixed.

    **Every station is smoothed, not only the ones that fail.** Two constructions across a stack
    of contours would put a systematic step between a station offset directly and its neighbour
    offset from a refit, and the path that runs on 62 stations of 81 is not the path that gets
    exercised when something breaks.

    The refit is *verified*, which is the whole difference between substituting a curve and
    assuming one: the original wire is sampled densely and every sample must lie within `tol`
    of the new curve, or the build stops. Without that this would be a silent change to the
    exterior the wall is measured from.
    """
    pts = wire.discretize(Number=n)
    if pts[0].distanceToPoint(pts[-1]) < Z_TOL:
        pts = pts[:-1]
    curve = Part.BSplineCurve(pts, None, None, True, 3, None, False)
    shape = curve.toShape()

    # Measured against a dense polyline of the new curve rather than by `distToShape` per
    # point: the curve interpolates the `n` samples exactly, so what is being checked is what
    # it does *between* them, and 4n `distToShape` calls on a B-spline cost more than the
    # erosion they are guarding.
    dense = _Polyline([(p.x, p.y) for p in shape.discretize(Number=4 * n)])
    worst = float(dense.distances(
        [(p.x, p.y) for p in wire.discretize(Number=2 * n)]).max())
    return Part.Wire(shape), worst


def eroded_body(wire, t, z, tol=REFIT_TOL):
    """The refit section, its face, and the face eroded by `t` -- refining until all three work.

    **Uniform sampling, and a ladder rather than one attempt.** Measured 2026-09-02 on the nose
    at z = -29.79, a 355 mm section, every refit verified against the original wire:

        413 points spaced by deflection    moved 0.0027 mm   offset FAILED
        300 points spaced uniformly        moved 0.0219 mm   offset ok
        600 points spaced uniformly        moved 0.0065 mm   offset ok
       1200 points spaced uniformly        moved 0.0019 mm   offset ok

    Deflection sampling puts points where the curvature is, which is the right instinct and the
    wrong result: the uneven spacing leaves the interpolant with local wiggles, and a 0.6 mm
    offset of a wiggle self-intersects and returns null. The count is not what decides it --
    413 uneven points fail where 300 even ones succeed -- so the fix is the spacing, and the
    ladder is there because the *deviation* still needs enough points to come inside `tol`.

    Both conditions are checked on every rung, and reaching the end of the ladder is a failure
    to report rather than a coarser answer to accept.
    """
    n0 = max(SAMPLE_MIN, min(SAMPLE_MAX, int(wire.Length / SAMPLE_SPACING)))
    why = None
    for n in (n0, 2 * n0, 4 * n0):
        refit, moved = smoothed(wire, n, tol)
        if moved > tol:
            why = ('refitting at %d points moved the section %.6f mm, over the %.6f mm '
                   'allowed' % (n, moved, tol))
            continue
        face = Part.Face(refit)
        try:
            inner = face.makeOffset2D(-t, 0, False, False, True)
        except Exception as exc:                       # noqa: BLE001 -- reported below
            why = 'the refit at %d points (%.6f mm) would not offset: %s' % (n, moved, exc)
            continue
        if inner is None or not inner.Faces:
            why = 'the refit at %d points offset to nothing' % n
            continue
        return refit, face, inner
    raise PreconditionFailed(
        'P3: no refit of the %.3f mm section at z = %.4f both reproduced it and eroded by '
        '%.4f mm. Last: %s. The wall is measured from this curve, so a refit that does not '
        'reproduce the section is a changed exterior, and one that will not offset is the '
        'IP-FC-54 failure.' % (wire.Length, z, t, why))


def slab_normal(tool):
    """The unit normal of a cutting slab's own plane, or `None` if it has no planar face.

    A slab's two largest faces are the pair that give it its thickness, so their normal is the
    direction the slab is thin in, and `hypot(n.x, n.y)` is the sine of the angle between the
    slab's plane and the layer plane -- 1 for a vertical cut, 0 for a horizontal one.
    """
    planar = [f for f in tool.Faces if isinstance(f.Surface, Part.Plane)]
    if not planar:
        return None
    n = max(planar, key=lambda f: f.Area).Surface.Axis
    n.normalize()
    return n


def dilated_notches(notches, t, report=None):
    """`dilate(B, t)` as a list of solids, built once for the part: section 4.2's right-hand
    term.

    **The ribs are applied to the cavity, not fitted into its surface, and that is the whole
    change.** The identity is exact --

        erode(A - B, t) == erode(A, t) - dilate(B, t)

    -- and it was previously evaluated station by station in 2-D: erode the body section,
    dilate the notch sections, subtract, and fit a smooth surface through the creased contour
    that came out. A single periodic B-spline cannot represent a crease. It overshoots at every
    rib corner, and the overshoot is what produced self-intersecting wires, unorientable faces,
    and a final fuse that landed 9x off its own volume from identical inputs (measured
    2026-09-03 on the nose at U = 1: 323372, 326795 and 35828 mm3 from the same 14 stations).

    Evaluating the same identity in 3-D removes the cause rather than refining against it. The
    surface is fitted through `erode(A, t)` alone, which on these cowls is a rounded rectangle
    with no crease anywhere in it, and `dilate(B, t)` is subtracted afterwards as a solid. The
    creases then arrive as the edges of a boolean between two well-formed solids, which is
    where a crease belongs.

    It also removes a correction the 2-D form needed and the 3-D form does not. A tool that
    does not reach the body at a station still has a section there, and dilating that section
    in-plane reached back across the boundary and bit material the part has -- so the 2-D code
    clipped each tool against the body and used the clip as a predicate. In 3-D no clip is
    needed: a tool outside the body is at least `t` from `erode(A, t)`, so its dilation meets
    the cavity in nothing.

    **The structuring element is a horizontal disc, not a ball.** Perimeter width is what one
    layer lays down, so the wall is measured in the layer plane and the erosion that defines it
    is a 2-D one -- which is what `eroded_body` already computes with `makeOffset2D`. Dilating
    by the same element keeps the identity's two halves consistent.

    **And the dilation is a union of translates, not a loft through offset sections.** Both
    reproduce the geometry; only one of them does it without introducing features that break
    the boolean afterwards. Lofting the offset sections needs the sections taken a hair inside
    each end -- slicing a polyhedron on one of its own vertex planes returns that face's edges
    rather than a section, measured on the tail as zero closed loops at z = -98.0120 and again
    at z = -94.8136 -- and the slivers that have to be extruded back on to close the gap leave
    edges 1e-4 mm long. Measured 2026-09-03 on the tail's two congruent side slabs, same volume
    and same z range:

        loft with sliver caps   4 short edges   cut valid on one slab, INVALID on the other
        loft without the caps   0 short edges   cut valid on both, but the spans no longer meet
        union of translates     0 short edges   cut valid on both

    The invalid one reported "Bad orientation of sub-shape", and no fuzzy tolerance rescues it
    honestly: at fuzz 1e-3 the cut returns *valid* and the cavity comes out 588610 mm3 from a
    588454 mm3 interior -- larger after a cut than before it.

    A union of translates has none of that. Every piece is the original polyhedron, so nothing
    can be degenerate that was not degenerate already, and `RIB_FACETS` records how the count
    was chosen against the 1.3 mm rib gap.

    `Part.makeOffsetShape`, the obvious alternative, is not usable either: it dilates the
    nose's slab correctly (424.570 -> 5702.021 mm3) and returns a null shape on the first tail
    tool.

    Returned as a list, which `cavity` then fuses into a single tool before cutting with it.
    An earlier version of this note said fusing "bought nothing" because it cost 260 s and the
    cut looked the same; that was wrong, and `cavity`'s own comment records what it buys --
    cutting with twenty-two separate tools succeeds on some and fails on others, silently, and
    the wall comes out in pieces because the ribs are what bridge the buttress slots.
    """
    grown = []
    angles = []
    for tool in notches.Solids:
        # **P4: no notch lies in the layer plane.** A rib forms because the slicer's single
        # perimeter walks into the notch and back out again *within* a layer; a notch lying in
        # the layer plane offers no such path, so the feature would have to be formed between
        # layers instead, which thin-wall perimeter slicing cannot do, and it comes out
        # malformed. Horizontal ribs are therefore not used, which is also what keeps the rib
        # thickness `2*n_p*w + t_cut / sin(theta)` away from its singularity (OQ-DES-CW19).
        #
        # Asserted here rather than left true: this is the one place that sees every cutting
        # tool. It used to be visible only to `check_cowl_interior.in_plane_width`, which
        # returned `None` for a horizontal cut and whose caller answered with `continue` -- so
        # a design-domain violation was dropped from the rib check without comment and the
        # build reported OK.
        normal = slab_normal(tool)
        if normal is None:
            raise PreconditionFailed(
                'a cutting tool spanning z %.4f..%.4f has %d faces and not one of them is '
                'planar, so it is not a slab and its thickness has no direction. P4 cannot be '
                'evaluated on it and neither can the rib it is supposed to leave.'
                % (tool.BoundBox.ZMin, tool.BoundBox.ZMax, len(tool.Faces)))
        flat = math.hypot(normal.x, normal.y)
        if flat < FLAT_TOL:
            raise PreconditionFailed(
                'P4: a cutting tool spanning z %.4f..%.4f lies in the layer plane -- its own '
                'plane is %.3e from horizontal. A rib forms where the perimeter walks into the '
                'notch and back out within a layer, and a horizontal notch offers no such '
                'path, so this one would come out malformed rather than as a rib. Horizontal '
                'ribs are outside the design.' % (tool.BoundBox.ZMin, tool.BoundBox.ZMax, flat))
        angles.append(math.degrees(math.asin(min(1.0, flat))))

        copies = [tool.translated(App.Vector(t * math.cos(2.0 * math.pi * i / RIB_FACETS),
                                             t * math.sin(2.0 * math.pi * i / RIB_FACETS),
                                             0.0))
                  for i in range(RIB_FACETS)]
        solid = copies[0].fuse(copies[1:]).removeSplitter()
        if not solid.isValid() or not solid.Solids:
            raise PreconditionFailed(
                'dilating a cutting tool by %.4f mm produced %d solids, valid=%s. The tool '
                'spans z %.4f..%.4f with %d faces.'
                % (t, len(solid.Solids), solid.isValid(), tool.BoundBox.ZMin,
                   tool.BoundBox.ZMax, len(tool.Faces)))
        grown.append(solid)

    if report is not None:
        report.update(dilated_tools=len(grown),
                      dilated_volume=sum(g.Volume for g in grown),
                      shallowest_cut_deg=min(angles) if angles else None)
    # The shallowest angle is reported, not bounded -- see `FLAT_TOL`. A cut at theta leaves a
    # rib of `2*n_p*w + t_cut / sin(theta)`, so this number is the one to look at if a rib ever
    # measures wider than expected.
    note('ribs: %d tools dilated by %.4f mm in %d directions; shallowest cut plane %.2f deg '
         'from the layer plane' % (len(grown), t, RIB_FACETS,
                                   min(angles) if angles else float('nan')))
    return grown


def _one_region(shape, z, fuzz):
    """P2: the eroded section is a single closed loop. Returns its face.

    **Asserted against the loops that are geometry, not against the ones that are boolean
    debris.** Cutting the dilated notches out of the eroded section leaves micro wires at the
    dent tips -- measured on the nose at z = -10.10, three of them beside a correct 284.92 mm
    outer boundary, and so degenerate that `Wire.discretize` on one brings the kernel down with
    an access violation rather than returning points. They are not holes and the cavity does not
    have them.

    The floor is two orders below the narrowest feature the design has -- a notch is
    `buttress_cut_thickness` = 0.1 mm wide -- and two orders above the debris, so it cannot
    swallow a real loop. It would not have swallowed the ones that mattered either: when
    unclipped tools were biting spurious pinholes into the tail, those loops measured 0.603 and
    0.522 mm, and this floor reports both.
    """
    where = 'z = %.4f' % z + ('' if fuzz is None else ' (fuzz %g)' % fuzz)
    faces = [f for f in shape.Faces if f.OuterWire.Length > SLIVER_LENGTH]
    if len(faces) != 1:
        raise PreconditionFailed(
            'P2: the eroded section is %d regions at %s, not one -- the erosion pinched it '
            'apart' % (len(faces), where))
    loops = [w for w in faces[0].Wires if w.Length > SLIVER_LENGTH]
    if len(loops) != 1:
        raise PreconditionFailed(
            'P2: the eroded section at %s has %d loops, not one (lengths %s)'
            % (where, len(loops), ', '.join('%.4f' % w.Length for w in loops)))
    return faces[0]


def fit_samples(perimeter):
    """How many points of this contour go into the fit grid. See `FIT_ARC`."""
    return max(FIT_MIN, min(FIT_MAX, int(perimeter / FIT_ARC)))


def check_samples(perimeter):
    """How many points of this contour the wall is evaluated at. See `CHECK_ARC`."""
    return max(CHECK_MIN, min(CHECK_MAX, int(perimeter / CHECK_ARC)))


def contour(face_or_wire, n, anchor=0.0):
    """Section 4.3: `n` points around a closed contour, in consistent correspondence, and the
    dense polyline they were taken from.

    **Anchored to a geometric feature and traversed in a fixed direction**, then distributed
    by arc-length fraction, so a station with a notch and a station without still correspond.
    Without this the surface twists between stations, and the result is a valid, closed,
    plausible solid -- the classic loft failure, which announces itself nowhere.

    The anchor is the contour's crossing of the +x ray from its own centroid. The algorithm
    document suggests one of the four corner arcs of the rounded-rectangle section; those are
    not usable here because the 2-D offset and the notch subtraction rebuild the contour's
    edge list, so the arc that was a corner on the exterior is not identifiable as one on the
    eroded contour. The ray is a feature of the section rather than of its edge list, which is
    the property the document is asking for, and it is stable across stations because the
    cowl's axis is the z axis by construction.
    """
    wire = face_or_wire if isinstance(face_or_wire, Part.Wire) else face_or_wire.OuterWire
    dense = [(p.x, p.y) for p in wire.discretize(Number=max(DENSE_FACTOR * n, 400))]
    if len(dense) > 1 and dense[0] == dense[-1]:
        dense.pop()
    if _signed_area(dense) < 0.0:
        dense.reverse()

    m = len(dense)
    # **Weighted by arc length, because the plain mean of the samples is a property of the
    # sampling and not of the curve.** `makeOffset2D` hands back a wire whose edge list starts
    # wherever the kernel left it, and `Wire.discretize` allocates its points per edge, so a
    # rotated edge list slides every sample along the curve -- measured 2026-09-04 on the tail,
    # up to 0.068 mm on a contour identical to 65 nanometres. An unweighted centroid moves with
    # that, the anchor ray swings with the centroid, and the parameter origin slides. It showed
    # up as the two end rows of a patch differing between processes by 0.0570 and 0.0169 mm
    # with the mean equal to the maximum -- every point shifted by the same amount, which is a
    # rigid twist of the correspondence rather than a change of shape. Weighting by segment
    # length makes the centroid the curve's, so redistributing the samples leaves it alone.
    seg = [math.hypot(dense[(i + 1) % m][0] - dense[i][0],
                      dense[(i + 1) % m][1] - dense[i][1]) for i in range(m)]
    total_len = sum(seg)
    if total_len <= 0.0:
        raise PreconditionFailed('a section at has zero perimeter')
    cx = sum(0.5 * (dense[i][0] + dense[(i + 1) % m][0]) * seg[i]
             for i in range(m)) / total_len
    cy = sum(0.5 * (dense[i][1] + dense[(i + 1) % m][1]) * seg[i]
             for i in range(m)) / total_len

    # The crossing of the ray at `anchor` radians from the centroid: a fixed direction, so the
    # same place on the section at every station.
    #
    # **The direction is chosen away from every notch, and that is not a detail.** The nose's
    # eight buttresses sit exactly on the +-x and +-y axes -- measured, their sections span
    # x = -0.050..0.050 and y = -0.050..0.050 -- so anchoring on +x put the parameter origin
    # inside a dent. As the dent's depth ramps between stations the crossing jumps from one
    # side of it to the other, the arc-length parameterisation rotates by that much between
    # neighbouring rows, and the fitted surface twists so badly that a z plane no longer cuts
    # it in one closed loop. The refinement then subdivides forever at a *measured gap of
    # zero*, because the intervals never reach the deviation test.
    #
    # The tail never showed it: its notches sit at 5, 12.5, 20 and 30 degrees, so +x happened
    # to land on clean surface. A default that works on one part and silently destroys the
    # other is the kind of thing section 4.3 is warning about when it says to anchor to a
    # feature rather than to whatever the sectioning returned.
    # **The origin is the crossing itself, not the sample before it, and that is what makes
    # the build reproducible.** `makeOffset2D` returns the eroded contour as a wire whose edge
    # list starts wherever the kernel left it: measured 2026-09-04 on the tail at z = -59.9996,
    # two processes produced the same ten edges with the same lengths and the same start points
    # to nine decimals, rotated by one position. The curve is identical -- 65 nanometres between
    # the two point sets -- but `Wire.discretize` allocates its points per edge, and this wire's
    # edges run from 0.0417 mm to 151.9 mm, so the rotation slides every sample along the curve
    # by up to 0.068 mm.
    #
    # Snapping the origin to the nearest sample turned that slide into a parameter shift of up
    # to one dense spacing, *different at every station*, which is a twist in the correspondence
    # rather than a shift of it: the rows no longer line up, the fitted surface moves, and the
    # measured wall error came out 0.5974, 0.6096 or 0.6439 mm from six identical seeded
    # stations depending on the run. Downstream that decided whether the tail's wall closed as
    # one solid or five.
    #
    # Interpolating the crossing removes the quantisation outright. The anchor is a geometric
    # feature of the section, so the origin it defines is exact, and what remains is the dense
    # polyline's chord error -- 1e-4 mm at this spacing, three orders under `TAU`.
    ux, uy = math.cos(anchor), math.sin(anchor)
    start = 0
    cross = None
    for i in range(m):
        c1 = (dense[i][0] - cx) * -uy + (dense[i][1] - cy) * ux
        j = (i + 1) % m
        c2 = (dense[j][0] - cx) * -uy + (dense[j][1] - cy) * ux
        if c1 <= 0.0 < c2 and ((dense[i][0] - cx) * ux + (dense[i][1] - cy) * uy) > 0.0:
            start = i
            span = c2 - c1
            f = 0.0 if span <= 0.0 else -c1 / span
            cross = (dense[i][0] + f * (dense[j][0] - dense[i][0]),
                     dense[i][1] + f * (dense[j][1] - dense[i][1]))
            break
    if cross is None:
        raise PreconditionFailed(
            'the contour at this station never crosses the anchor ray at %.4f rad. The '
            'correspondence has no origin, and every row would be parameterised from wherever '
            'the sectioning happened to start.' % anchor)
    # The crossing replaces the sample it fell between, so the list still has `m` points and
    # begins exactly on the ray.
    dense = [cross] + dense[start + 1:] + dense[:start + 1]
    m = len(dense)

    cum = [0.0]
    for i in range(m):
        x1, y1 = dense[i]
        x2, y2 = dense[(i + 1) % m]
        cum.append(cum[-1] + math.hypot(x2 - x1, y2 - y1))
    total = cum[-1]
    if total <= 0.0:
        raise PreconditionFailed('a section at has zero perimeter')

    samples = []
    j = 0
    for k in range(n):
        target = total * k / float(n)
        while j + 1 < len(cum) and cum[j + 1] < target:
            j += 1
        span = cum[j + 1] - cum[j]
        f = 0.0 if span <= 0.0 else (target - cum[j]) / span
        x1, y1 = dense[j % m]
        x2, y2 = dense[(j + 1) % m]
        samples.append((x1 + f * (x2 - x1), y1 + f * (y2 - y1)))
    return samples, _Polyline(dense)


def _check_slope(lower, upper, z_lo, z_hi, limit):
    """P1: every section steeper than `overhang_angle_from_bed`.

    Checked on the **un-notched** body, which is where section 4.2's `erode(A, t)` applies and
    where the `t*cos(alpha)` reasoning holds. The notch ramps are cut at this same angle by
    design and are handled by the dilation of B, so including them here would fire the
    assertion on the feature the design intends.
    """
    dz = abs(z_hi - z_lo)
    if dz <= 0.0:
        return
    worst = None
    at = 0.0
    for (x1, y1), (x2, y2) in zip(lower, upper):
        dr = math.hypot(x2 - x1, y2 - y1)
        ang = math.degrees(math.atan2(dz, dr))
        if worst is None or ang < worst:
            worst = ang
            at = math.atan2(y1, x1)
    if worst is not None and worst < limit - SLOPE_SLACK:
        raise PreconditionFailed(
            'P1: the body is %.2f deg from the bed between z = %.4f and %.4f, at %.1f deg '
            'around the section -- shallower than overhang_angle_from_bed = %.2f. The inset '
            'leaves t*cos(alpha) of perpendicular wall, so this station would emit a knife '
            'edge.' % (worst, z_lo, z_hi, math.degrees(at), limit))


# --------------------------------------------------------------------------------
# Stations
# --------------------------------------------------------------------------------

def z_extent(body, tol=END_INSET):
    """The body's real axial extent, found by asking it where it sections.

    **`Shape.BoundBox` is not tight on these solids, and taking it at its word puts stations
    outside the part.** Measured 2026-09-02 on the nose at U = 1: `Lower` is the scaled OML met
    with a mask running z = -50 to -6, and it reports a bounding box of -100 to 0 -- the whole
    un-masked blank. Sectioning at -61.16, which that box calls interior, returns no loops at
    all. The box is computed from the B-spline geometry rather than from the trimmed result, so
    it is an outer bound and nothing more. The tail survived it only because its mask happens to
    span the whole OML.

    An earlier version read the extent off the faces perpendicular to z, which is exact and
    free -- and wrong, because only the nose has two of them. The tail's forward end is the mask
    cut but its aft end is the OML's own closure (OQ-DES-CW13), so that version found one plane
    and refused. Bisection makes no assumption about how either end is bounded, and it is the
    same path for both cowls, which is the property that matters more than the cost: an outer
    bound plus a predicate is all this needs, and both are reliable.

    About 34 sections at roughly 0.7 s each, once per part.
    """
    def sections(z):
        try:
            return len(_slice_wires(body, z)) >= 1
        except Exception:                              # noqa: BLE001 -- a miss is a miss
            return False

    box = body.BoundBox
    lo, hi = box.ZMin, box.ZMax
    inside = None
    for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
        z = lo + (hi - lo) * f
        if sections(z):
            inside = z
            break
    if inside is None:
        raise PreconditionFailed(
            'the body does not section anywhere in its own bounding box, %.4f to %.4f'
            % (lo, hi))

    def edge(outside, within):
        while abs(within - outside) > tol:
            mid = 0.5 * (outside + within)
            if sections(mid):
                within = mid
            else:
                outside = mid
        return within

    return edge(lo, inside), edge(hi, inside)


def feature_stations(notches, z_lo, z_hi):
    """Section 4.1: the axial positions where the exterior itself has an edge.

    **Derived from the geometry rather than restated from the parameters.** Every buttress
    ramp start and end, and the cut plane, appear as vertices of the notch solids, so reading
    them off the tools gets all of them and cannot fall out of step with the tools that made
    them. A list rebuilt from the sheet would be a second statement of one design, and the one
    that moved would win silently.

    These are **patch boundaries, not interior knots**: the exterior has a genuine crease
    there, and demanding continuity across a rib end would smooth away a feature the part
    really has.
    """
    seen = sorted(v.Point.z for v in notches.Vertexes
                  if z_lo + MIN_INTERVAL < v.Point.z < z_hi - MIN_INTERVAL)
    out = []
    for z in seen:
        if not out or abs(z - out[-1]) > max(Z_TOL, MIN_INTERVAL):
            out.append(z)
    return out


def anchor_direction(notch_wires, body_face):
    """Where to put the parameter origin: the direction furthest from any notch.

    Section 4.3 asks for the correspondence to be anchored to a feature and traversed in a
    fixed direction. What it must *not* be anchored to is a feature that **moves**, and a notch
    is exactly that -- its depth ramps with z, so a ray through one crosses the contour in a
    place that shifts from station to station. `contour` records what that cost.

    So the anchor is derived from the notches rather than chosen despite them: take the angle
    of every notch about the section centre and point at the middle of the widest gap between
    consecutive angles. On the nose, whose eight buttresses sit on the axes, that is a diagonal;
    on the tail, whose eleven sit between 0 and 30 degrees, it is the empty side. Neither is
    written down anywhere -- both fall out of where the tools actually are.
    """
    centre = body_face.CenterOfMass
    angles = []
    for wire in notch_wires:
        if not wire.isClosed():
            continue
        middle = wire.BoundBox.Center
        angles.append(math.atan2(middle.y - centre.y, middle.x - centre.x) % (2 * math.pi))
    if not angles:
        return 0.0
    angles.sort()
    best, at = -1.0, 0.0
    for i in range(len(angles)):
        lo = angles[i]
        hi = angles[(i + 1) % len(angles)] + (2 * math.pi if i + 1 == len(angles) else 0.0)
        if hi - lo > best:
            best, at = hi - lo, 0.5 * (lo + hi)
    return at % (2 * math.pi)


def _patches(z_lo, z_hi, features):
    edges = [z_lo] + list(features) + [z_hi]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)
            if edges[i + 1] - edges[i] > MIN_INTERVAL]


def _seed(z_lo, z_hi, inset_lo, inset_hi):
    n = SEED_MAX if (z_hi - z_lo) >= SEED_LONG_MM else SEED_MIN
    zs = [z_lo + (z_hi - z_lo) * i / float(n - 1) for i in range(n)]
    # Only the part's own ends are inset. An internal patch boundary is a station the patches
    # on both sides must sample at *exactly* the same z, or their two approximations of it are
    # separated by the inset.
    if inset_lo:
        zs[0] += END_INSET
    if inset_hi:
        zs[-1] -= END_INSET
    return zs


# --------------------------------------------------------------------------------
# The fit
# --------------------------------------------------------------------------------

def _fit(rows):
    """Section 4.4: a C2 approximation through the eroded contours of one patch.

    Not a loft. A `ruled=True` loft is excluded by requirement (4), and a `ruled=False` loft
    that interpolates the section curves without tangency constraints satisfies neither (3)
    nor generally (2). What the requirement asks for is an approximation with continuity
    constraints, which is the class of construction OpenVSP uses for the exterior.

    **The surface is genuinely periodic in the circumferential direction, and it has to be
    built that way rather than told to be that way afterwards.** `BSplineSurface.interpolate`
    takes no periodic flag -- checked against the API, its only signatures are `(points)` and
    the gridded-float form -- and `setVPeriodic()` applied to the result does not make the seam
    continuous, it only relabels it. What that leaves is a surface with a real defect at the
    parameter origin, and the defect is worst where the contour curves most.

    That is exactly where the anchor puts it. `anchor_direction` chooses the direction furthest
    from any notch, which on the nose's eight axis-aligned buttresses is the diagonal -- the
    corner arc of the rounded-rectangle section. Measured 2026-09-03 on the nose at U = 1, worst
    |wall - t| round the section, 9 rows and no refinement:

        interpolate + setVPeriodic          0.1552 at a row   0.1456 at a midpoint
        interpolate + repeated column       0.1409             0.1372
        repeated column + setVPeriodic      0.1409             0.1372
        skinned, genuinely V-periodic       0.0039             0.0084

    and in the first three the error sits *at the seam* -- 0.0040 away from it. A closed curve
    interpolated with `PeriodicFlag=True` holds the wall to 0.0025 mm with the seam on that same
    corner, so periodicity, not the anchor and not the sampling, is what was missing. This is
    what made section 5 refine forever against a floor: no number of axial stations fixes a
    circumferential seam, and the floor halved when the fit spacing halved because the seam gap
    is proportional to the spacing there.

    So the periodicity comes from curves that really have it, and is carried into the surface by
    `buildFromPolesMultsKnots`, which does take the flag. Every row carries the same number of
    points and is given the same explicit parameterisation, so every row curve comes out with
    the same knot vector and the same pole count -- which is what makes a pole track something
    it is meaningful to interpolate along.

    A patch seeded with two stations comes out degree 1 in the axial direction. That is not a
    violation of requirement (4): a patch is bounded by two genuine creases in the exterior,
    continuity is required *within* one, and a two-station patch has no interior join to be
    continuous across. It survives only because section 5's midpoint check found it already
    within `TAU` of the erosion.
    """
    zs = [z for z, _pts in rows]
    n = len(rows[0][1])

    # V: one genuinely periodic curve per row. The parameterisation is given explicitly rather
    # than left to chord length so that every row lands on the same knot vector -- rows differ
    # in perimeter, and chord length would give each its own.
    vparams = [i / float(n) for i in range(n + 1)]
    curves = []
    for z, pts in rows:
        curve = Part.BSplineCurve()
        curve.interpolate(Points=[App.Vector(x, y, z) for x, y in pts],
                          PeriodicFlag=True, Parameters=vparams)
        curves.append(curve)

    # U: interpolate each pole track through the stations. Same argument for giving the
    # parameters explicitly -- every track must share a knot vector for the poles to assemble
    # into a grid.
    lo, hi = zs[0], zs[-1]
    span = hi - lo
    uparams = [(z - lo) / span for z in zs]
    poles = [curve.getPoles() for curve in curves]
    tracks = []
    for j in range(len(poles[0])):
        track = Part.BSplineCurve()
        track.interpolate(Points=[poles[i][j] for i in range(len(rows))], Parameters=uparams)
        tracks.append(track)

    grid = [[track.getPoles()[i] for track in tracks] for i in range(tracks[0].NbPoles)]
    surf = Part.BSplineSurface()
    surf.buildFromPolesMultsKnots(
        grid,
        tracks[0].getMultiplicities(), curves[0].getMultiplicities(),
        tracks[0].getKnots(), curves[0].getKnots(),
        False, True,
        tracks[0].Degree, curves[0].Degree)
    return surf


def _lid(surf, u):
    """A patch's cap at one of its two ends, taken from the surface's own iso curve.

    From the surface rather than from the sample polygon, so the cap edge *is* the surface
    edge and the piece closes without a tolerance argument. The interpolated boundary passes
    exactly through a row of points that all share one z, so it should be planar; the filled
    face is kept as a fallback for the case where the kernel disagrees, since it bounds the
    same wire without requiring planarity.
    """
    wire = Part.Wire([surf.uIso(u).toShape()])
    if not wire.isClosed():
        a = wire.Vertexes[0].Point
        b = wire.Vertexes[-1].Point
        if a.distanceToPoint(b) > Z_TOL:
            wire = Part.Wire(wire.Edges + [Part.makeLine(b, a)])
    try:
        return Part.Face(wire)
    except Exception:                                  # noqa: BLE001 -- non-planar boundary
        return Part.makeFilledFace(wire.Edges)


def _refine(fit_at, outer_at, zs, t, tau, budget, n_check, anchor):
    """Section 5: refine until the fitted interior holds the wall, then stop.

    **The criterion is the wall, measured in the layer plane.** At each candidate station the
    fitted surface is sectioned, the section is sampled at `CHECK_ARC`, and every sample's
    distance to the exterior is compared with `t`. What is reported is the worst departure of
    the perimeter width from the width it is supposed to be.

    It used to be the two-sided Hausdorff distance between the fitted contour and an ideal
    eroded contour. That is a proxy for the wall rather than the wall: it bounds the width only
    indirectly, it made section 5 converge on a different quantity from the one
    `check_cowl_interior` accepts the part on, and because both of its sides scaled with the
    sample count it made the whole construction quadratic in a number the rib had set. A
    distance from points to one polyline is linear in the same number, which is what makes it
    affordable to check at the resolution a 1.3 mm rib actually needs.

    Spacing is still derived, not tuned. The tolerance is now the physical one.
    """
    rows = [(z, fit_at(z)) for z in zs]

    while True:
        surf = _fit(rows)
        face = surf.toShape()
        wanted = []
        worst = 0.0
        unsliceable = 0
        shapes = []
        for i in range(len(rows) - 1):
            z_a, z_b = rows[i][0], rows[i + 1][0]
            if z_b - z_a <= 2 * MIN_INTERVAL:
                continue
            z_m = 0.5 * (z_a + z_b)
            # **An insertion has two possible causes and they are not the same failure.**
            # Either the wall is measurably wrong -- which more stations fix -- or the surface
            # would not section into one closed loop at all, which more stations do not fix and
            # which subdividing turns into a silent loop that runs to the budget. They are
            # counted apart so the progress line can say which is happening.
            sliced = _slice_wires(face, z_m)
            cut = [w for w in sliced if w.isClosed()]
            if len(cut) != 1:
                unsliceable += 1
                shapes.append('%d wire(s), %d closed' % (len(sliced), len(cut)))
                wanted.append((i, z_m))
                continue
            here, _dense = contour(cut[0], n_check, anchor)
            gap = float(np.abs(outer_at(z_m).distances(here) - t).max())
            worst = max(worst, gap)
            if gap > tau:
                wanted.append((i, z_m))
        if not wanted:
            return rows, surf, worst
        note('    refining: %d stations -> %d, worst wall error %.4f mm over %.3f%s'
             % (len(rows), len(rows) + len(wanted), worst, tau,
                '' if not unsliceable else
                '   [%d of %d from a surface that would not section: %s]'
                % (unsliceable, len(wanted), '; '.join(sorted(set(shapes))))))
        if len(rows) + len(wanted) > budget:
            raise Unconverged(
                'section 5 wanted more than %d stations between z = %.4f and %.4f. Worst '
                'measured wall error %.4f mm against %.3f; %d of the %d insertions were not '
                'from a measured wall at all but from a fitted surface that would not section '
                'into one closed loop (%s). Subdividing does not fix that second kind, so if '
                'it dominates here the station count is a symptom and not the problem.'
                % (budget, rows[0][0], rows[-1][0], worst, tau, unsliceable, len(wanted),
                   '; '.join(sorted(set(shapes))) or 'none'))
        for offset, (i, z_m) in enumerate(wanted):
            rows.insert(i + 1 + offset, (z_m, fit_at(z_m)))


# --------------------------------------------------------------------------------
# The wall
# --------------------------------------------------------------------------------

def cavity(notched, body, notches, t, overhang_deg, tau=TAU, budget=64, report=None):
    """The solid the wall encloses: sections 4 and 4.5.

    `notched` is the finished print representation, `body` the same blank before any notch
    reached it, and `notches` the cutting tools. The tools are taken as given rather than
    recovered as `body - notched`: that difference is the same set inside the body, and
    measured 2026-09-02 it costs 47 s a part to compute and leaves a 202-face solid that is
    slower to section than the tools are.

    **Two steps, not one.** The surface is fitted through the eroded *body* -- a rounded
    rectangle, smooth everywhere -- and the ribs are then subtracted from the closed result as
    a solid. `dilated_notches` records what fitting a surface through the creased contour
    instead cost, and why the identity is evaluated in 3-D here rather than station by station
    in 2-D.
    """
    lo, hi = z_extent(body)
    z_lo, z_hi = lo + END_INSET, hi - END_INSET

    body_faces = {}
    outers = {}
    fits = {}

    def key(z):
        return round(z / Z_TOL)

    def body_face(z):
        """`(refit wire, its face, the face eroded by t)`, cached -- P1 wants the first, P2 the
        second, and the erosion the third, and all three cost one refit."""
        k = key(z)
        if k not in body_faces:
            wires = _slice_wires(body, z)
            if len(wires) != 1:
                raise PreconditionFailed(
                    'P2: the body sections into %d loops at z = %.4f, not one'
                    % (len(wires), z))
            body_faces[k] = eroded_body(wires[0], t, z)
        return body_faces[k]

    # **One sample count for the whole part, taken from its widest section.** The fit needs a
    # rectangular grid, so every station in a patch must carry the same number of points; taking
    # it from the widest section makes the spacing finest where the contour is longest and never
    # coarser than `FIT_ARC` anywhere.
    widest = max(body_face(z)[0].Length
                 for z in (z_lo, 0.5 * (z_lo + z_hi), z_hi))
    n_fit = fit_samples(widest)
    n_check = check_samples(widest)

    # The anchor is fixed once for the part and every station is parameterised from it. It has
    # to be one direction for the whole part: the correspondence only means anything if
    # consecutive rows start from the same place.
    mid = 0.5 * (z_lo + z_hi)
    anchor = anchor_direction(_slice_wires(notches, mid), body_face(mid)[1])

    def fit_at(z):
        """The eroded body contour at `z`, at fit resolution: one row of the grid."""
        k = key(z)
        if k not in fits:
            _refit, _face, inner = body_face(z)
            fits[k] = contour(_one_region(inner, z, None), n_fit, anchor)[0]
        return fits[k]

    def outer_at(z):
        """The exterior at `z` as a dense polyline: what the wall is measured out to."""
        k = key(z)
        if k not in outers:
            outers[k] = contour(body_face(z)[0], n_check, anchor)[1]
        return outers[k]

    note('interior: z %.3f .. %.3f, %d fit points (%.3f mm apart), %d check points '
         '(%.3f mm apart), anchor %.1f deg'
         % (z_lo, z_hi, n_fit, widest / n_fit, n_check, widest / n_check,
            math.degrees(anchor)))

    # **The body's own creases, not the notches'.** The surface follows the un-notched blank
    # now, so a rib start is not a boundary for it -- the rib is subtracted afterwards and
    # brings its own edges. Splitting at every rib end is what made the tail 60 patches.
    features = feature_stations(body, z_lo, z_hi)
    patches = _patches(z_lo, z_hi, features)
    if not patches:
        raise PreconditionFailed('the part is shorter than the %.2f mm interval floor'
                                 % MIN_INTERVAL)

    # **One closed solid per patch, fused, rather than one sewn shell.** Interpolation makes
    # adjacent patches pass exactly through the station they share, so their edges now coincide
    # rather than merely agreeing to a fitting tolerance -- but capping each patch and fusing is
    # kept regardless. A sew has to be told how far apart two edges may be before it joins them,
    # and a number that is wrong in either direction fails silently: too small and the shell
    # stays open, too large and it welds across a gap that was real. The fuse needs no such
    # number.
    pieces = []
    stations = 0
    chosen = []
    worst_wall = 0.0
    started = time.time()
    for index, (p_lo, p_hi) in enumerate(patches):
        at = time.time()
        zs = _seed(p_lo, p_hi, p_lo <= z_lo, p_hi >= z_hi)

        # P1 over the patch, on the un-notched body, before anything is fitted.
        prev = None
        for z in zs:
            here, _d = contour(body_face(z)[0], n_check, anchor)
            if prev is not None:
                _check_slope(prev[1], here, prev[0], z, overhang_deg)
            prev = (z, here)

        rows, surf, worst = _refine(fit_at, outer_at, zs, t, tau, budget, n_check, anchor)
        stations += len(rows)
        worst_wall = max(worst_wall, worst)
        # **The positions, not only the count.** Two builds that both settle on 16 stations
        # have not necessarily settled on the same 16, and the count is what the progress line
        # reports -- so a refinement that lands somewhere else is invisible in the log while
        # changing the surface, the cavity and the wall.
        chosen.extend(z for z, _pts in rows)

        # Section 4.5: both cowls are open -- the tail at both ends, the nose body where it is
        # cut to the closure parts -- so a patch is closed by the two contours it already has
        # and there is no turnover to handle. The caps come from the fitted surface's own iso
        # curves rather than from the sample polygon, so the cap edge *is* the surface edge and
        # the piece closes without a tolerance argument.
        u0, u1, _v0, _v1 = surf.bounds()
        lids = [_lid(surf, u) for u in (u0, u1)]
        pieces.append(Part.Solid(Part.Shell([surf.toShape()] + lids)))

        note('patch %d/%d  z %9.4f .. %9.4f (%6.3f mm)  %2d seeded -> %2d stations  '
             'worst wall %.4f  %5.1f s  [%.0f s total]'
             % (index + 1, len(patches), p_lo, p_hi, p_hi - p_lo, len(zs), len(rows),
                worst, time.time() - at, time.time() - started))
        # **The positions, in the log and not only in the report.** Two builds that both settle
        # on the same number of stations have not necessarily settled on the same stations, and
        # a build that lands elsewhere produces a different surface, different end caps and a
        # different wall while the progress line above reads identically.
        note('    at %s' % ' '.join('%.4f' % z for z, _pts in rows))

        # **The two open ends are extended past the part, not stopped at it.** A station may
        # not sit exactly on a planar end -- sectioning there returns the end face's boundary
        # rather than the body's -- so the cavity stops `END_INSET` short at each end, and a
        # cavity that stops short leaves a film of solid material closing the very opening the
        # cowl is open at. It renders, it is valid, and it is a cowl with its ends skinned
        # over. Extending the end caps outward removes it, and the extension falls outside the
        # blank so it cuts nothing else.
        if p_lo <= z_lo:
            pieces.append(lids[0].extrude(App.Vector(0, 0, -END_OVERRUN)))
        if p_hi >= z_hi:
            pieces.append(lids[1].extrude(App.Vector(0, 0, END_OVERRUN)))

    note('fusing %d pieces' % len(pieces))
    at = time.time()
    smooth = pieces[0]
    for piece in pieces[1:]:
        smooth = smooth.fuse(piece)
    smooth = smooth.removeSplitter()
    if report is not None:
        report.update(stations=chosen, smooth_volume=smooth.Volume,
                      smooth_faces=len(smooth.Faces))
    note('smooth interior: %d solids, valid=%s, %.4f mm3, %.0f s to fuse'
         % (len(smooth.Solids), smooth.isValid(), smooth.Volume, time.time() - at))

    # Section 4.2's right-hand term, applied here rather than fitted into the surface above.
    # **Fused into one tool, and the result verified against it.** Cutting with a list of
    # twenty-two separate tools is what the earlier code did, and it succeeds on one surface
    # and partially fails on another -- the failure is silent, because a cavity with a rib left
    # in it is still a valid closed solid. Fusing first costs a few seconds and gives the
    # kernel one boolean to reason about instead of twenty-two.
    ribs = dilated_notches(notches, t, report)
    at = time.time()
    tool = ribs[0] if len(ribs) == 1 else ribs[0].fuse(ribs[1:]).removeSplitter()
    solid = smooth.cut(tool).removeSplitter()

    # The ribs and the cavity must not intersect: that is what cutting them out means.
    left = solid.common(tool)
    if left.Volume > RIB_RESIDUE:
        note('    %.4f mm3 of rib survived the cut; taking it out again' % left.Volume)
        solid = solid.cut(left).removeSplitter()
        left = solid.common(tool)
    if left.Volume > RIB_RESIDUE:
        raise Unconverged(
            '%.4f mm3 of dilated rib is still inside the cavity after the cut and one retry, '
            'in %d piece(s). The cavity is therefore larger than the erosion allows and the '
            'wall will be thin or missing wherever that rib should have been -- and since the '
            'ribs are what bridge the buttress slots, the wall comes out in pieces. Nothing '
            'downstream catches this: the cavity is a valid closed solid either way.'
            % (left.Volume, len(left.Solids)))
    if report is not None:
        report.update(rib_residue=left.Volume, cavity_volume=solid.Volume,
                      cavity_faces=len(solid.Faces))
    note('ribs cut in %.0f s, %.6f mm3 left inside' % (time.time() - at, left.Volume))
    note('cavity closed: %d solids, valid=%s, %.4f mm3, worst wall error %.4f mm, '
         '%.0f s in all' % (len(solid.Solids), solid.isValid(), solid.Volume, worst_wall,
                            time.time() - started))
    if report is not None:
        report.update(patches=len(patches), stations=stations, features=len(features),
                      solids=len(solid.Solids), valid=solid.isValid(),
                      worst_wall=worst_wall, fit_points=n_fit, check_points=n_check)
    return solid


#: How much of the blank a cut may fail to account for, as a fraction of the blank.
#:
#: **The check it feeds is an identity, not a tolerance on the answer.** Cutting a solid in two
#: partitions it: `notched - cavity` and `notched & cavity` must together be exactly `notched`.
#: A boolean that drops material breaks that, and nothing else in this construction notices --
#: measured 2026-09-04, a nose build produced a 415.5423 mm3 wall where every other run gave
#: 9713.4 mm3, and the section-6 acceptance test passed it `OK` because a wall that is mostly
#: *missing* still measures 0.600 mm wherever it happens to exist.
#:
#: The floor is what the kernel's own reproducibility costs: repeated cuts of one fixed pair of
#: operands agreed to 0.25 mm3 in 581652 mm3, four parts in ten million, so 1e-4 leaves three
#: orders of headroom over that and still catches a loss of a tenth of a percent.
PARTITION_TOL = 1.0e-4


def shell_solid(notched, body, notches, t, overhang_deg, tau=TAU, report=None):
    """The wall: the notched blank with its cavity removed.

    Bounded by the exterior, the interior, and an annulus at each open end -- which is what
    cutting the closed cavity out of the closed blank leaves, without the annuli having to be
    constructed.

    **The cut is verified against the partition identity before it is returned.** This last
    boolean is between two NURBS solids `t` apart, which is the hardest thing asked of the
    kernel here, and it is not reliable: the same code has produced a correct 23745.581 mm3
    tail wall from one converged surface and a 21995 mm3 one in five pieces from another, both
    surfaces measured inside `TAU` at every station and between them. Until that is fixed the
    build must at least refuse to emit the wrong answer, because every check downstream of here
    is a check on the wall it is handed.
    """
    inside = cavity(notched, body, notches, t, overhang_deg, tau=tau, report=report)
    wall = notched.cut(inside)

    kept = notched.common(inside)
    total = wall.Volume + kept.Volume
    slip = abs(total - notched.Volume) / notched.Volume
    if report is not None:
        report.update(wall_volume=wall.Volume, wall_solids=len(wall.Solids),
                      partition_slip=slip)
    note('wall: %.4f mm3 in %d solid(s); the cut and the common account for %.6f%% of the '
         'blank' % (wall.Volume, len(wall.Solids), 100.0 * (1.0 - slip)))
    if slip > PARTITION_TOL:
        raise Unconverged(
            'the wall and the material it was cut from do not add up to the blank: '
            '%.4f + %.4f = %.4f against %.4f, off by %.4f mm3 (%.4f%%). Cutting a solid in '
            'two partitions it, so this boolean lost material, and the wall it returned is '
            'not the part. Section 6 would not catch it -- a wall that is mostly missing '
            'still measures %.3f mm thick wherever it survives.'
            % (wall.Volume, kept.Volume, total, notched.Volume,
               abs(total - notched.Volume), 100.0 * slip, t))
    return wall
