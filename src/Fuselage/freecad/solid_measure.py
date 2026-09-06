"""IP-FC-119: measure a solid's volume by a method that converges, because `Shape.Volume` does not.

**`Shape.Volume` is wrong on this project's B-spline solids, by 0.16 to 0.24 %.** Measured
2026-09-05 on two `tail_shell` builds at `U` = 1: it reports 23680.884053 mm3 and 23700.694092,
a difference of 19.810039, where integrating the divergence theorem over a 1.8-million-triangle
tessellation of the same two solids gives 23737.997001 and 23738.003187 -- a difference of
0.006186 mm3 -- and puts both `Shape.Volume` figures 57 and 37 mm3 low.

`Face.Area` fails the same way and was caught first: 47.5811 mm2 against 48.6157 for a face
whose boundary wire is identical in both builds to 286 nm point for point, and whose *signed*
area is 48.2074 against 48.2070. That is 1.3 % low on one and 0.85 % high on the other for the
same geometry. `Face.CenterOfMass` comes from the same integration and moved 0.0915 mm on that
identical face.

**`Shape.BoundBox` is loose on the same solids, and by far more.** Measured 2026-09-06
(IP-FC-127): the nose cowl runs z = -50.000 to -6.000 and reports a box of -61.159 to 0.000 --
**139 % of the part** -- and the nose tip is 7.000 mm tall in that same 61.159 mm box, **874
%**. It is computed from the B-spline geometry rather than from the trimmed result, so it is
an outer bound and nothing more. `optimalBoundingBox(True)` is not the fix: it is 0.363 mm
loose on each side of the nose cowl and on the tail returns -102.482 to 2.764 where the plain
box is exactly right. **What is unaffected, and it is worth being specific**: `mesh_stats`
takes its bounding boxes from the triangles of a written STL, which are the part, so
`BBOX_TOL` and every cross-backend comparison are measuring a tight box. The loose one is
`Shape.BoundBox` on a B-rep, and the rule is the same as for volume -- ask the geometry, not a
property derived from the surfaces that carry it. `cowl_interior.z_extent` is what does the
asking.

**Three conclusions were drawn from those numbers before anyone checked them**, and all three
were wrong: that two builds of a cowl differ by up to 0.58 % of their volume, that the
difference is concentrated at one face on the open end, and that the project therefore needed a
new reproducibility tolerance. The builds agree to 2.6e-7. See OQ-ARCH-19.

**The rule this leaves.** A single integrated property is not a measurement. A measurement is a
value that stops moving when the method is refined, and `converged_volume` below returns one --
or raises, rather than returning a number that is still moving and letting a caller treat it as
though it had settled.

**A mesh volume can be wrong by half a percent while passing every check a mesh can be given.**
Measured 2026-09-06 under IP-FC-120 on a `tail_shell` wall: closed, consistently wound -- 0 of
5.2 million directed edges traversed twice -- inside the 0.001 mm deflection it was built to,
carrying the same total area as another mesh of the same solid to 7.5e-05, and its vertices on
the true surface; and it enclosed **112.5 mm3 less**, 4.7e-03, at every deflection from 0.005 to
0.00025. Sectioning the two solids at 101 stations put them 0.13 mm3 apart and agreed with the
*other* mesh to 0.02 %. The instrument is not generally at fault: on a hollow cylinder of the
same surface-to-volume ratio it converges to 4.2e-06 of the exact volume and two partitions of
it differ by 6.6e-09. **So a volume that matters is measured twice, by instruments that fail
differently, or it is not measured.** For a thin shell the independent one is a section
integral: it uses neither booleans nor tessellation nor point sampling.

**And a measurement that converges is still only a measurement of what it was pointed at.**
`converged_difference` cancels the discretisation error between two solids by tessellating both
the same way, which requires them to be *cut into faces* the same way. Pointed at two identical
walls with different face layouts it returned a settled, converged, entirely false 112.46 mm3
(IP-FC-115). It now refuses that case. The measurements that are indifferent to face layout are
the boolean difference and the surface distance.

**This is not an export setting.** Refining a tessellation to measure something is unrelated to
the deflection a part is *exported* at, which is chosen for printing and preview
(`build_part.COWL_LINEAR_DEFLECTION`). Analysis of the B-rep and export of a mesh are separate
concerns and neither may be adjusted to suit the other.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

#: Deflections tried in order, in millimetres, coarsest first.
#:
#: The tail wall converges by the third: successive volumes 23726.383, 23735.043, 23737.997,
#: with the step falling from 8.66 to 2.95 mm3, and the *difference between two builds* falling
#: 1.360 -> 0.170 -> 0.006. Below 0.001 the triangle count passes 1.8 million and the cost is
#: minutes per solid for a change in the fifth decimal place.
DEFLECTIONS = (0.02, 0.005, 0.001, 0.00025)

#: A volume is converged when refining changes it by less than this, relative to itself.
#:
#: **1e-4, because that is this method's own floor and not a target chosen to look good.**
#: Measured 2026-09-05 on the tail wall, the absolute volume does not settle below it and does
#: not even fall monotonically: 23729.508 at 0.02 mm, 23735.816 at 0.005, 23738.079 at 0.001,
#: then *down* to 23736.472 at 0.00025 with 5.7 million triangles. Refining past 0.001 mm buys
#: nothing and costs minutes. An earlier version of this constant was 1e-5 and nothing ever
#: reached it.
#:
#: **So an absolute volume from this module is good to about a part in ten thousand, and no
#: better.** For comparing two solids, use `converged_difference` instead -- see its docstring.
CONVERGENCE = 1.0e-4

#: The same test for a *difference*, and it is ten times tighter for a reason.
#:
#: A difference converges where an absolute does not, because two solids tessellated at one
#: deflection carry nearly the same discretisation error and it cancels. So it can afford the
#: tighter bar -- and it needs it. At 1e-4 the tail pair stopped at deflection 0.005 reporting
#: 0.169929 mm3, when one more refinement gives 0.006186: the step was 1.19 mm3, which is only
#: 5e-5 *of the part*, so it passed while the answer was still an order of magnitude out. At
#: 1e-5 it runs to 0.001 mm and returns 0.006186.
DIFFERENCE_CONVERGENCE = 1.0e-5


class NotConverged(Exception):
    """Refining the tessellation never settled, so there is no measurement to report."""


class TopologyMismatch(Exception):
    """The two solids are not cut into faces the same way, so their meshes cannot be differenced.

    See `converged_difference`. Compare them with a boolean difference and a surface distance
    instead: those measure the *sets*, and are indifferent to how the faces are laid out.
    """


def mesh_volume(shape, deflection):
    """Volume of `shape`'s tessellation at `deflection`, by the divergence theorem.

    Signed tetrahedra from the origin, summed and taken absolute so winding does not change the
    answer -- the same integral `tools/mesh_stats.py` performs on an STL, done here on the solid
    so that nothing has to be written to disk and no export setting is involved.
    """
    # **A shape hands back the triangulation it already has.** Asking for 0.02 mm after asking
    # for 0.001 mm returns the 0.001 mm mesh -- measured 2026-09-05, 1845851 facets both times
    # -- so a caller that refines from fine to coarse silently measures the fine mesh twice.
    # `converged_volume` and `converged_difference` both walk `DEFLECTIONS` coarsest first,
    # which is the order that does not have this problem.
    verts, facets = shape.tessellate(deflection)
    total = 0.0
    for i, j, k in facets:
        a, b, c = verts[i], verts[j], verts[k]
        total += (a.x * (b.y * c.z - c.y * b.z)
                  - b.x * (a.y * c.z - c.y * a.z)
                  + c.x * (a.y * b.z - b.y * a.z))
    return abs(total) / 6.0, len(facets)


def open_edges(shape, deflection):
    """`(points, facets, unpaired edges)` -- whether the tessellation is a closed surface.

    **The divergence theorem needs a closed surface, and nothing else here checks for one.** An
    open mesh still returns a number from `mesh_volume`, and it is wrong by however much the
    hole subtends.

    Every edge of a closed triangulation is shared by exactly two facets. Vertices are keyed by
    rounded coordinates rather than by index, because `tessellate` numbers each face's points
    separately where faces meet -- an index-keyed count calls every seam a hole.

    Measured 2026-09-05 at deflection 0.001 mm: one tail wall came out with **3 unpaired edges**
    in 2768775, and its differently-partitioned twin with none. Three is a degenerate triangle,
    not a hole with area, and it moves the volume by nothing measurable -- but it is the kind of
    thing to look at before believing a mesh volume, which is why this is here.
    """
    points, facets = shape.tessellate(deflection)
    keys = [(round(p.x, 6), round(p.y, 6), round(p.z, 6)) for p in points]
    seen = {}
    for i, j, k in facets:
        for u, v in ((i, j), (j, k), (k, i)):
            edge = (keys[u], keys[v]) if keys[u] < keys[v] else (keys[v], keys[u])
            seen[edge] = seen.get(edge, 0) + 1
    return len(points), len(facets), sum(1 for n in seen.values() if n != 2)


#: How many points a surface-difference estimate samples unless told otherwise.
#:
#: The estimate's error falls as 1/sqrt(N) and each sample costs two distance queries -- 44 ms
#: on the nose's 503 faces, 660 ms on the tail's 2480 -- so 800 is about a minute on one and ten
#: on the other. Calibrated at 1200: eight independent seeds on a difference of 62.8331 mm3
#: known in closed form gave a mean of 62.4327, 0.62 standard errors out, with the scatter
#: between seeds at 1.6468 against a predicted 1.8138. Unbiased, and the error bars are honest.
SURFACE_SAMPLES = 800


def _area_sampler(shape, deflection=0.02):
    """`(sample(rng), total area)` -- points on the surface, uniform by area.

    Triangles are drawn with probability proportional to area and a point is taken uniformly
    inside the chosen one, which is what makes the sample mean an estimate of the area-weighted
    mean rather than of a per-triangle one.
    """
    verts, facets = shape.tessellate(deflection)
    cumulative, total = [], 0.0
    for i, j, k in facets:
        a, b, c = verts[i], verts[j], verts[k]
        total += b.sub(a).cross(c.sub(a)).Length / 2.0
        cumulative.append(total)

    def sample(rng):
        target = rng.uniform(0.0, total)
        lo, hi = 0, len(cumulative) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cumulative[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        i, j, k = facets[lo]
        a, b, c = verts[i], verts[j], verts[k]
        r1, r2 = rng.random(), rng.random()
        if r1 + r2 > 1.0:
            r1, r2 = 1.0 - r1, 1.0 - r2
        return App.Vector(a.x + r1 * (b.x - a.x) + r2 * (c.x - a.x),
                          a.y + r1 * (b.y - a.y) + r2 * (c.y - a.y),
                          a.z + r1 * (b.z - a.z) + r2 * (c.z - a.z))

    return sample, total


def surface_difference(a, b, samples=SURFACE_SAMPLES, seed=99, deflection=0.02):
    """The symmetric difference of two solids, estimated by sampling one's surface.

    Returns `(estimate, standard_error, area, mean_gap, max_gap)`, all in millimetres and cubic
    millimetres.

    **Why this exists: the boolean symmetric difference does not work between two solids that
    were built independently.** Measured 2026-09-06 on two `tail_shell` builds from identical
    inputs, `a.cut(b)` and `b.cut(a)` returned shapes with `isValid()` false, in 9 and 7 solids,
    totalling 28.874616 mm3 over 1054 s -- for a pair whose volumes agree to 0.006186 mm3. A
    difference planted inside one of them turned up in the wrong half with the wrong sign. The
    boolean *is* exact between solids that share surfaces, where it recovered a planted
    0.001 mm3 exactly in 2 s, so **check `isValid()` on both halves and use the boolean when it
    holds; this is for when it does not.**

    **The method.** The symmetric difference between two nearly coincident solids is a thin band
    on their shared surface, and its volume is the integral of the gap:

        XOR = integral of |d| dA  ~=  area * mean(|d|)

    so points sampled on one surface, uniformly by area, with each one's distance to the other
    solid's faces, estimate it. It uses `|d|`, so excursions in and out **add** rather than
    cancelling -- which is what a difference of totals gets wrong, and by a lot: those two builds
    differ by 1.6 mm3 of material where subtracting their volumes says 0.006186.

    **Each sample is projected onto its own surface first, and that is not a refinement.** A
    point taken inside a triangle lies up to the deflection off the true surface, so every sample
    would otherwise carry a baseline distance of order the chordal error whether the solids
    differ there or not -- measured at 4.269e-03 mm on the nose against a true mean gap of
    6.2e-04, which turned an exact 21.41 mm3 into 148.08. `distToShape` returns the nearest
    points and not only the distance, so projecting costs one call and no approximation.

    **What it cannot see: a difference that does not reach the surface, or one confined to a
    small patch of it.** An interior void contributes nothing to a surface integral. A localised
    difference needs roughly `total area / patch area` samples before a single one lands on it,
    and until one does the estimate is zero with a standard error of zero -- false precision, and
    the reason a caller must read `max_gap` and not only the estimate. Measured: a 36 mm2 bite
    out of a 34688 mm2 surface, worth 21.41 mm3, was missed entirely by 800 samples. The boolean
    covers exactly that case on the pairs where it works, so the two instruments fail
    differently and neither replaces the other.
    """
    import random

    sample, area = _area_sampler(a, deflection)
    own = Part.makeCompound(a.Faces)
    other = Part.makeCompound(b.Faces)
    rng = random.Random(seed)
    gaps = []
    for _ in range(samples):
        landed = Part.Vertex(sample(rng)).distToShape(own)[1][0][1]
        gaps.append(Part.Vertex(landed).distToShape(other)[0])
    mean = sum(gaps) / len(gaps)
    variance = sum((g - mean) ** 2 for g in gaps) / max(len(gaps) - 1, 1)
    return (area * mean, area * (variance / len(gaps)) ** 0.5, area, mean, max(gaps))


def converged_volume(shape, tol=CONVERGENCE, deflections=DEFLECTIONS, report=None):
    """The solid's volume, refined until it stops moving. Raises if it never does.

    Returns `(volume, deflection, triangles)` for the first refinement whose result agrees with
    the one before it to `tol` relative. **Raising is the point**: a caller that is handed a
    number cannot tell a converged one from a still-moving one, and that is exactly the mistake
    `Shape.Volume` invites -- it always answers, and it answers wrongly.
    """
    history = []
    previous = None
    for deflection in deflections:
        volume, facets = mesh_volume(shape, deflection)
        history.append((deflection, volume, facets))
        if report is not None:
            report.setdefault('volume_history', []).append((deflection, volume, facets))
        if previous is not None:
            change = abs(volume - previous) / max(volume, 1.0e-12)
            if change <= tol:
                return volume, deflection, facets
        previous = volume
    raise NotConverged(
        'the volume was still moving at the finest deflection tried: %s. The last two differ '
        'by %.3e relative against a tolerance of %.0e, so there is no settled value to report.'
        % (', '.join('%.5f mm -> %.6f mm3 (%d triangles)' % h for h in history),
           abs(history[-1][1] - history[-2][1]) / max(history[-1][1], 1.0e-12), tol))


def wire_area(face):
    """A planar face's area from its outer wire, by the shoelace formula.

    `Face.Area` is not usable on a plane bounded by B-spline curves -- see the module docstring.
    The boundary itself is reliable, so the area is taken from it. Points come from
    `Wire.discretize`, so this is a polygon area and is a slight under-estimate on a convex
    boundary; refine `n` if that matters more than the 1 % `Face.Area` is out by.
    """
    import Part                                            # noqa: F401  (FreeCAD-only import)
    normal = face.Surface.Axis
    normal.normalize()
    # Project onto whichever plane the face is most nearly parallel to, so the shoelace runs on
    # the two coordinates that vary rather than on a degenerate pair.
    drop = max(range(3), key=lambda i: abs((normal.x, normal.y, normal.z)[i]))
    keep = [i for i in range(3) if i != drop]
    pts = [(p.x, p.y, p.z) for p in face.OuterWire.discretize(Number=400)]
    total = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i][keep[0]], pts[i][keep[1]]
        x2, y2 = pts[(i + 1) % len(pts)][keep[0]], pts[(i + 1) % len(pts)][keep[1]]
        total += x1 * y2 - x2 * y1
    scale = abs((normal.x, normal.y, normal.z)[drop])
    return abs(total) / 2.0 / max(scale, 1.0e-12)


def converged_difference(a, b, tol=DIFFERENCE_CONVERGENCE, deflections=DEFLECTIONS,
                         report=None):
    """How much two solids' volumes differ, refined until *the difference* stops moving.

    **This is the well-conditioned measurement, and `converged_volume` is not.** An absolute
    mesh volume carries a discretisation error of order 1e-4 that does not settle. But two
    nearly-identical solids tessellated at the *same* deflection carry nearly the same error,
    and it cancels in the difference -- which is why the difference converges cleanly where the
    absolutes do not. Measured 2026-09-05 on two `tail_shell` builds: the difference falls
    1.360063 -> 0.169929 -> 0.006186 mm3 across deflections 0.02, 0.005 and 0.001, while neither
    absolute value settles at all.

    Returns `(difference, deflection, relative)` where `relative` is against the larger volume.
    Raises `NotConverged` if the difference is still moving, for the same reason
    `converged_volume` does: a caller cannot tell a settled number from a moving one.

    The sign is `volume(b) - volume(a)`, measured at one deflection for both.

    **The cancellation has a precondition, and it is not "the solids are similar".** The two
    have to be cut into faces the *same way*, because the discretisation error is a property of
    the face layout and not only of the surface. Two solids that are geometrically identical but
    partitioned differently do not cancel at all.

    **Measured 2026-09-05 under IP-FC-115**, on two assemblies of one tail wall that are the
    same set by every test that measures sets: the symmetric difference is empty and valid in
    both directions, 2003 sampled boundary points of each lie on the other's *faces* to within
    6e-10 mm, and two closed surfaces that coincide enclose the same volume. One wall has 2480
    faces and the other 2735, because `removeSplitter` raises `Bnd_Box is void` on the second
    and its split faces stay in. Both tessellate closed. Their mesh volumes at deflection
    0.001 mm are **23737.913141 and 23625.451163** -- 112.46 mm3 apart, 4.7e-03 -- and this
    function called that a converged difference.

    **The size of that error is not predictable, which is the reason for the guard.** The nose
    is the same experiment with the opposite outcome: 503 faces against 449, and mesh volumes
    agreeing to 0.032 mm3, 3.3e-06. So a partition mismatch can cost 112 mm3 or nothing, and
    neither the value nor its convergence distinguishes the two -- the tail's figure held at
    111.33 and then 112.46 as the mesh was refined, which is what a real difference looks like.
    What the 112 mm3 *is* remains open under IP-FC-120; what is established is that it is not a
    difference between the solids.

    So this raises `TopologyMismatch` when the face counts differ. It is a coarse test -- equal
    counts do not prove equal layouts -- but it costs nothing and it catches the case that
    actually arises, which is one shape refined and the other not. When it fires, the question
    being asked is about sets, and the tools for that are a boolean difference and a surface
    distance **taken to the other solid's faces**: `distToShape` against a solid returns 0 for
    any point inside it, so measured against the solid it is blind to the missing-interior case
    it would be used to rule out.
    """
    if len(a.Faces) != len(b.Faces):
        raise TopologyMismatch(
            'the two solids have %d and %d faces, so they are not cut up the same way and the '
            'discretisation error does not cancel between their meshes -- which is the whole '
            'basis of this measurement. Two identical walls partitioned differently measured '
            '112.46 mm3 apart this way, 4.7e-03 of the part, while their symmetric difference '
            'was empty; two others, also identical and also partitioned differently, agreed to '
            '0.032 mm3. The error is there or it is not, and this measurement cannot tell you '
            'which. Compare them with a boolean difference and a surface distance taken to the '
            'faces instead.' % (len(a.Faces), len(b.Faces)))
    history = []
    previous = None
    for deflection in deflections:
        va, na = mesh_volume(a, deflection)
        vb, nb = mesh_volume(b, deflection)
        difference = vb - va
        history.append((deflection, difference, na + nb))
        if report is not None:
            report.setdefault('difference_history', []).append((deflection, difference, na + nb))
        if previous is not None:
            # Converged when the difference stops moving relative to the parts themselves, not
            # relative to itself -- a difference heading for zero would never satisfy the
            # latter, and zero is the answer this is most often used to confirm.
            change = abs(difference - previous) / max(abs(va), abs(vb), 1.0e-12)
            if change <= tol:
                return difference, deflection, difference / max(abs(va), abs(vb), 1.0e-12)
        previous = difference
    raise NotConverged(
        'the volume difference was still moving at the finest deflection tried: %s'
        % ', '.join('%.5f mm -> %+.6f mm3 (%d triangles)' % h for h in history))
