"""Candidate local-thickness measures, each one a function of two polylines.

Every measure here has the same signature and returns the same thing, so the screening harness can
score them on equal terms:

    measure(outer, inner) -> (points, thickness)

`outer` and `inner` are `(n, 3)` arrays from `sections.station_loops`, outer loop first. `points`
is the `(m, 3)` locations the measure reports at, and `thickness` is the `(m,)` local wall thickness
it reports there. A measure samples whichever boundary it likes and at whatever density it likes;
the harness compares its answers against closed-form truth at the points it chose.

**Everything in and out of here is meters** (IP-FC-163): the arrays arrive SI from
`sections._points_of`, so every distance computed from them is SI without this module converting
anything. The three places that needed a deliberate change were the window and margin parameters,
which are lengths and are now `_m`; the geometric epsilons, which are compared against a length
and so had to move with it; and `survives_erosion`, which is the one function here that hands
coordinates back to the kernel. The figures quoted in the docstrings stay in the millimeters they
were measured and reported in.

The incumbent is included as `nearest_point_min` so the candidates are scored against it rather
than against an impression of it, and `tests/test_wall_measure_gates.py` checks that this
reimplementation agrees with the real `cowl_interior._Polyline.distance` on the fixtures -- without
that, the baseline would be a different measure wearing the same name.

See doc/implementation/wall_thickness_measure.md and doc/design/cowl_interior_surface.md section 5.
"""
import math

import numpy as np

from . import kern
from . import sections


#: A turn at one vertex sharp enough to be a genuine crease rather than a sampled curve. Radians,
#: because the standard's angle unit is radians; it is the 30 degrees it always was, and
#: `outer_creases`' own docstring argues why anything from 10 to 60 degrees gives the same answer.
CREASE_ANGLE_RAD = math.radians(30.0)

#: How far from a crease or a reflex corner a sample is dropped, along the boundary's own arc. Half
#: an extrusion width. Converted from 0.30 mm by IP-FC-163 and is the same margin.
MARGIN_M = 3.0e-4

#: The arc-length window a tangent is fitted over in `windowed_normal`. Half an extrusion width:
#: wide enough to average a crease out, narrow enough that a 0.6 mm defect still has several
#: independent samples across it. Converted from 0.30 mm.
WINDOW_M = 3.0e-4

#: How far a ray is cast before it is treated as having missed. Converted from 5.0 mm, which is an
#: order of magnitude more than any wall this measures and an order less than the section's own
#: size, so a ray that travels this far has left the ribbon.
MAX_RAY_M = 5.0e-3

#: Geometric epsilons, **scaled with the coordinates they are compared against** (IP-FC-163).
#:
#: This is the trap the conversion keeps setting. `RAY_PARALLEL_M` guards a divide by a cross product
#: of a unit direction and a segment vector, so it carries one length and had to move by 1000 like
#: the segment did; `RAY_MIN_M` is a distance along a ray, so it moved too; `REFLEX_AREA_M2` is a
#: cross product of **two** segment vectors, an area, so it moved by a million. Carrying any of the
#: three across unchanged would have left the same literal meaning something 1000 or 1e6 times
#: looser or tighter -- which is the defect `station_sets.FLOOR_TOL_M` and `fit_response.Z_TOL_M`
#: each had to be rescued from. `RAY_U_EPS` is the one that does **not** move: `u` is a fraction
#: along a segment and is dimensionless.
RAY_PARALLEL_M = 1.0e-17
RAY_MIN_M = 1.0e-12
RAY_U_EPS = 1.0e-9
REFLEX_AREA_M2 = 1.0e-18

#: Largest `(m, s)` intermediate `_segment_distances` will allocate at once, in elements. At 8 bytes
#: a float that is about 200 MB a temporary, and there are a few of them live at once.
#:
#: **The cap exists because the natural parameterization of this work is unbounded.** A refinement
#: study on a `tail_shell` at `U` = 4, whose section is 2 088 mm round, asks for 68 160 samples a
#: loop at 0.03 mm spacing; the un-chunked form below would then allocate a 68 160 x 68 160 array,
#: 37 TB. Measured 2026-10-10 by running exactly that and having to stop it. Chunking makes the
#: cost linear in memory and unchanged in result.
MAX_BLOCK = 25000000


def _segment_distances(points, poly, max_block=MAX_BLOCK):
    """Distance from every point in `points` to the closed polyline `poly`, exactly.

    Point-to-*segment*, not point-to-vertex: taking the distance to the nearest sampled vertex
    instead would add an error of up to half the vertex spacing, which at 720 samples on a 60 mm
    loop is 0.04 mm -- four times `WALL_TOL`, and it would masquerade as the measure's own error.

    Evaluated in blocks of `points` so the peak allocation is bounded by `max_block` elements
    regardless of how finely either loop is sampled. The arithmetic per point is identical to the
    single-block form; only the loop order changes.
    """
    a = poly[:, :2]
    b = np.roll(a, -1, axis=0)
    ab = b - a                                             # (s, 2)
    denom = np.einsum('ij,ij->i', ab, ab)
    denom = np.where(denom > 0.0, denom, 1.0)
    m, s = points.shape[0], a.shape[0]
    if m == 0:
        return np.zeros(0, dtype=np.float64)
    rows = max(1, int(max_block // max(1, s)))
    out = np.empty(m, dtype=np.float64)
    for lo in range(0, m, rows):
        chunk = points[lo:lo + rows, :2]
        p = chunk[:, None, :]                              # (k, 1, 2)
        ap = p - a[None, :, :]                             # (k, s, 2)
        t = np.einsum('ksj,sj->ks', ap, ab) / denom
        t = np.clip(t, 0.0, 1.0)
        closest = a[None, :, :] + t[:, :, None] * ab[None, :, :]
        out[lo:lo + chunk.shape[0]] = np.linalg.norm(p - closest, axis=2).min(axis=1)
    return out


def _segment_nearest(points, poly, max_block=MAX_BLOCK):
    """`_segment_distances`, and also *which* segment of `poly` each point was nearest to.

    Same arithmetic, same blocking, same result for the distance -- the only addition is the
    `argmin` alongside the `min`. Separate from `_segment_distances` rather than replacing it
    because the index costs an extra `(k, s)` reduction and every existing caller wants only the
    distance.

    Needed because a thin reading can be an artifact *of where on the exterior it was taken*,
    which the distance alone cannot say (IP-WTM-45).
    """
    a = poly[:, :2]
    b = np.roll(a, -1, axis=0)
    ab = b - a
    denom = np.einsum('ij,ij->i', ab, ab)
    denom = np.where(denom > 0.0, denom, 1.0)
    m, s = points.shape[0], a.shape[0]
    if m == 0:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.int64)
    rows = max(1, int(max_block // max(1, s)))
    dist = np.empty(m, dtype=np.float64)
    which = np.empty(m, dtype=np.int64)
    for lo in range(0, m, rows):
        chunk = points[lo:lo + rows, :2]
        p = chunk[:, None, :]
        ap = p - a[None, :, :]
        t = np.clip(np.einsum('ksj,sj->ks', ap, ab) / denom, 0.0, 1.0)
        closest = a[None, :, :] + t[:, :, None] * ab[None, :, :]
        d = np.linalg.norm(p - closest, axis=2)
        k = int(chunk.shape[0])
        which[lo:lo + k] = np.argmin(d, axis=1)
        dist[lo:lo + k] = d[np.arange(k), which[lo:lo + k]]
    return dist, which


def outer_creases(outer, angle_rad=CREASE_ANGLE_RAD):
    """Which vertices of `outer` are a genuine crease rather than a sampled curve.

    **The threshold separates two things that are far apart, not two that are close.** On a cowl
    section the smooth part is a rounded rectangle: at the gate's 0.125 mm sampling a 5 mm corner
    arc spans about 63 samples and turns 90 degrees in total, so roughly 1.4 degrees a vertex. A
    notch face meeting the OML turns tens of degrees at a *single* vertex. Anything from about 10
    to 60 degrees separates them, so the exact value is not a tuned parameter.

    **The turn is compared in radians**, which is what the standard's angle unit is; the threshold
    is unchanged and the comparison is the same one, since `arccos` already answers in radians and
    the `degrees()` call this used to make was a conversion in both directions.
    """
    xy = outer[:, :2]
    prev, nxt = np.roll(xy, 1, axis=0), np.roll(xy, -1, axis=0)
    v1, v2 = xy - prev, nxt - xy
    n1 = np.linalg.norm(v1, axis=1)
    n2 = np.linalg.norm(v2, axis=1)
    ok = (n1 > 0) & (n2 > 0)
    cos = np.ones(len(xy))
    cos[ok] = np.clip(np.einsum('ij,ij->i', v1[ok], v2[ok]) / (n1[ok] * n2[ok]), -1.0, 1.0)
    return np.arccos(cos) >= float(angle_rad)


def outer_corner_excluded_min(outer, inner, margin_m=MARGIN_M, angle_rad=CREASE_ANGLE_RAD):
    """The incumbent, with samples whose nearest *exterior* point sits at a crease dropped.

    **A different exclusion from `corner_excluded_min`, and for a different artifact.** That one
    drops inner samples near a concave turn of the *inner* contour, where the measured chord
    crosses the inner boundary's own corner. This one drops inner samples whose nearest point on
    the *outer* contour is at a crease of the exterior -- which is what a notch face meeting the
    OML is. The two can fire on different samples and neither subsumes the other.

    **Why this is worth measuring (IP-WTM-45).** `cowl_interior`'s second pass compares `TAU`
    against a plain minimum to the notched exterior and reads 0.0601 mm on a `tail_shell` at
    `U` = 0.5, invariant in `TAU`, while the same wall measured to the un-notched OML reads
    0.00175 mm at that very station. `dilate(B, t)` rounds a notch tool's convex edges to radius
    `t`, so where a notch emerges through the OML the cavity boundary lies `t` from a
    three-dimensional *edge*; an in-plane nearest-point distance from such a sample can read
    shorter than `t` with no material missing. If that is what the 0.0601 is, excluding the
    crease should remove it.

    Like `corner_excluded_min` this takes its minimum over a **subset** of the incumbent's own
    distances, so it can never report more thinness -- which is a structural check on it, not a
    tolerance.
    """
    dist, which = _segment_nearest(inner, outer)
    crease = outer_creases(outer, angle_rad)
    if not crease.any():
        return inner, dist
    # A sample is dropped when the segment it is nearest to lies within `margin_m` of a crease,
    # measured along the exterior's own arc. `_within_arc_of` works on the vertices; a segment is
    # indexed by its start vertex, so the vertex mask transfers directly.
    blocked = _within_arc_of(outer[:, :2], crease, float(margin_m))
    keep = ~blocked[which]
    if not keep.any():
        return inner[:0], np.zeros(0)
    return inner[keep], dist[keep]


def nearest_point_min(outer, inner):
    """**The incumbent.** Each inner sample's distance to the nearest point of the outer loop.

    This is what `check_cowl_interior.wall_thickness` reports and what the acceptance gate compares
    against `WALL_TOL`. **It is known not to converge**: at a concave corner the nearest point on
    the opposite boundary is reached by cutting *across* the corner rather than by crossing the
    wall, so denser sampling keeps finding a shorter path and the minimum keeps falling -- still
    drifting 0.0015 to 0.0079 mm per doubling at 3840 samples, at 17 of 24 real stations. It is
    here to be the baseline, not because it is expected to pass.
    """
    return inner, _segment_distances(inner, outer)


def windowed_normal(outer, inner, window_m=WINDOW_M, n_samples=None):
    """**Candidate C2.** Cast along a normal estimated over an arc-length window, not from
    neighbors.

    The straightforward local-normal measure was tried and **oscillates**, by up to 0.0139 mm per
    doubling, because the tangent estimate at a crease is itself unstable: two adjacent samples
    straddling a corner give a normal pointing anywhere. This fixes the known cause rather than the
    symptom -- the tangent is a least-squares fit over a window of arc length, so a single corner
    perturbs it by a bounded amount instead of dominating it.

    `window_m` defaults to half an extrusion width: wide enough to average a crease out, narrow
    enough that a 0.6 mm defect still has several independent samples across it.

    **The window is a count of samples, and it is `round`, not `int`.** Both operands are lengths,
    so the ratio is unit-invariant and the conversion did not move it -- but only because of the
    rounding: `int(a / b)` approaches a boundary from one side and flips whenever the ratio sits
    just above a whole number, which is exactly the `_steps` defect `tools/unit_regime.py
    --counts` sweeps for.
    """
    pts = sections.resample_by_arc_length(inner, n_samples or inner.shape[0])
    xy = pts[:, :2]
    n = xy.shape[0]
    step_m = sections.perimeter(pts) / float(n)
    half = max(1, int(round((window_m / 2.0) / step_m)))

    # Least-squares tangent over +/- `half` samples, via the window's principal direction.
    idx = (np.arange(n)[:, None] + np.arange(-half, half + 1)[None, :]) % n
    win = xy[idx]                                           # (n, w, 2)
    win = win - win.mean(axis=1, keepdims=True)
    # Principal direction of each window, from the 2x2 scatter matrix in closed form.
    sxx = np.einsum('nw,nw->n', win[:, :, 0], win[:, :, 0])
    syy = np.einsum('nw,nw->n', win[:, :, 1], win[:, :, 1])
    sxy = np.einsum('nw,nw->n', win[:, :, 0], win[:, :, 1])
    theta = 0.5 * np.arctan2(2.0 * sxy, sxx - syy)
    tang = np.column_stack((np.cos(theta), np.sin(theta)))
    nrm = np.column_stack((-tang[:, 1], tang[:, 0]))

    # Orient every normal outward, away from the loop's own centroid.
    out = xy - xy.mean(axis=0)
    flip = np.einsum('ij,ij->i', nrm, out) < 0.0
    nrm[flip] *= -1.0

    thick = _ray_to_polyline(xy, nrm, outer)
    return pts, thick


def _ray_to_polyline(origins, dirs, poly, max_t_m=MAX_RAY_M):
    """First positive intersection distance from each ray to a closed polyline; `inf` if none.

    A ray cast, not a nearest point: that is the whole difference from the incumbent. Crossing the
    wall along a direction cannot shortcut across a concave corner, because the direction is fixed
    before the opposite boundary is consulted.

    `dirs` are unit vectors, so `t` comes out in the coordinates' own unit -- meters -- and the
    three thresholds it meets are the scaled ones from this module's epsilon block.
    """
    a = poly[:, :2]
    b = np.roll(a, -1, axis=0)
    e = b - a                                               # (s, 2)
    o = origins[:, None, :]                                 # (m, 1, 2)
    d = dirs[:, None, :]                                    # (m, 1, 2)
    # Solve o + t*d = a + u*e for each (ray, segment).
    denom = d[:, :, 0] * e[None, :, 1] - d[:, :, 1] * e[None, :, 0]
    safe = np.where(np.abs(denom) > RAY_PARALLEL_M, denom, np.nan)
    ao = a[None, :, :] - o
    t = (ao[:, :, 0] * e[None, :, 1] - ao[:, :, 1] * e[None, :, 0]) / safe
    u = (ao[:, :, 0] * d[:, :, 1] - ao[:, :, 1] * d[:, :, 0]) / safe
    ok = (np.isfinite(t) & (t > RAY_MIN_M) & (t <= max_t_m)
          & (u >= -RAY_U_EPS) & (u <= 1.0 + RAY_U_EPS))
    t = np.where(ok, t, np.inf)
    return t.min(axis=1)


def inscribed_circle(outer, inner, n_samples=None):
    """**Candidate C1.** Local thickness as the diameter of the largest circle inside the ribbon.

    The textbook definition of local thickness, and the one a slicer's behavior actually follows:
    material is missing where no circle of the perimeter's width fits. Computed without rasterizing
    -- for each inner sample, the inscribed circle tangent to both boundaries along the inward
    normal has radius `r` where the center sits at distance `r` from this boundary and `r` from the
    other, so `r` solves a one-dimensional problem along the normal and the diameter is `2r`.

    On an annulus this returns exactly the radial wall, so it agrees with every other definition on
    gate G3's fixture.
    """
    pts = sections.resample_by_arc_length(inner, n_samples or inner.shape[0])
    xy = pts[:, :2]
    n = xy.shape[0]

    # **Oriented away from this loop's OWN centroid, not toward the other loop's.** The first
    # version aimed the normal at `outer`'s centroid, which on an annulus is the axis -- the exact
    # opposite of where the outer wall is. The normal pointed inward, the ray missed the outer
    # boundary, `gap` fell back to zero, and the walk never left the inner boundary, where the
    # distance to itself is zero: the measure reported a 0.000000 mm wall everywhere and
    # "converged" to it. The inner loop lies inside the outer one, so outward from the inner
    # loop's centroid is toward the wall.
    nrm = _windowed_normal_field(xy).copy()
    away = xy - xy.mean(axis=0)
    flip = np.einsum('ij,ij->i', nrm, away) < 0.0
    nrm[flip] *= -1.0

    # The inscribed circle's center lies along that normal at the point where the distance to this
    # boundary and the distance to the other are equal; the diameter is twice that distance. Found
    # by walking the normal to the far boundary and taking the largest circle that fits, which is
    # a one-dimensional maximization and needs no solve.
    gap = _ray_to_polyline(xy, nrm, outer)
    reached = np.isfinite(gap)
    gap = np.where(reached, gap, 0.0)
    best = np.zeros(n)
    for frac in np.linspace(0.0, 1.0, 33):
        c = xy + nrm * (gap[:, None] * frac)
        probe = np.column_stack((c, np.zeros(n)))
        r = np.minimum(_segment_distances(probe, inner), _segment_distances(probe, outer))
        best = np.maximum(best, r)
    # A sample whose normal never reaches the far boundary has no inscribed circle to report; NaN
    # rather than 0.0, so it is masked out of a gate's statistics instead of faking a zero wall.
    return pts, np.where(reached, 2.0 * best, np.nan)


def _windowed_normal_field(xy, window_frac=0.01):
    """Unit normals from a least-squares tangent over a window, used by more than one candidate."""
    n = xy.shape[0]
    half = max(1, int(round(window_frac * n / 2.0)))
    idx = (np.arange(n)[:, None] + np.arange(-half, half + 1)[None, :]) % n
    win = xy[idx]
    win = win - win.mean(axis=1, keepdims=True)
    sxx = np.einsum('nw,nw->n', win[:, :, 0], win[:, :, 0])
    syy = np.einsum('nw,nw->n', win[:, :, 1], win[:, :, 1])
    sxy = np.einsum('nw,nw->n', win[:, :, 0], win[:, :, 1])
    theta = 0.5 * np.arctan2(2.0 * sxy, sxx - syy)
    tang = np.column_stack((np.cos(theta), np.sin(theta)))
    return np.column_stack((-tang[:, 1], tang[:, 0]))


def corner_excluded_min(outer, inner, reflex_margin_m=MARGIN_M):
    """**Candidate C4.** The incumbent, with samples near a concave corner dropped.

    Tests whether the incumbent is salvageable rather than replaceable. Its failure has a known and
    specific cause -- a nearest-point distance taken *at a concave corner* crosses the corner -- so
    the cheapest possible fix is to not take it there. Corners are found as reflex turns in the
    sampled boundary, and every sample within `reflex_margin_m` of one along the arc is excluded.

    If this passes the gates it is the answer, because it is a few lines on top of a measure the
    project already ships. If it fails, it fails informatively: either the corners are not the whole
    cause, or excluding them removes the very places a wall is thinnest.

    **The samples are taken exactly as given, and the margin is applied along true arc length.** An
    earlier version resampled `inner` to uniform arc spacing first and then converted
    `reflex_margin_m` into a fixed number of steps. That made this measure a different *point set*
    from `nearest_point_min` rather than a subset of it, which quietly broke the one structural
    relationship between the two: C4 takes its minimum over a subset of C0's distances, so it can
    never report **more** thinness than C0. On a real `tail_shell` at `U` = 3.0 the resampled version
    reported 0.04806 mm against C0's 0.04689 mm -- a 0.0012 mm violation, small but impossible for a
    subset, and it made the screening a comparison of two changes at once. The resampling was also
    unnecessary: `Wire.discretize(Number=n)` was measured on real sections to be uniform in arc
    length to within 0.1 % at every density tried, so it corrected nothing. Using cumulative arc
    length for the margin drops the uniformity assumption instead of relying on it.
    """
    pts = inner
    xy = pts[:, :2]
    prev, nxt = np.roll(xy, 1, axis=0), np.roll(xy, -1, axis=0)
    # A cross product of two segment vectors, so an **area**: `REFLEX_AREA_M2` is the one epsilon in
    # this module that moved by a million rather than a thousand.
    cross = ((xy - prev)[:, 0] * (nxt - xy)[:, 1]
             - (xy - prev)[:, 1] * (nxt - xy)[:, 0])
    sign = np.sign(sections.signed_area(pts)) or 1.0
    reflex = (cross * sign) < -REFLEX_AREA_M2
    if not reflex.any():
        return pts, _segment_distances(pts, outer)

    blocked = _within_arc_of(xy, reflex, float(reflex_margin_m))
    keep = ~blocked
    if not keep.any():                      # every sample sat near a corner; report nothing
        return pts[:0], np.zeros(0)
    kept = pts[keep]
    return kept, _segment_distances(kept, outer)


def _within_arc_of(xy, marked, margin_m):
    """Which samples of a closed polyline lie within `margin_m` of a marked one, **along** the
    boundary.

    Arc distance, not index distance, so the margin means a real length on any sampling -- uniform
    or not. Each marked sample contributes an arc interval; the intervals are accumulated with a
    difference array and the wrap is handled by also placing each interval one perimeter either
    side. Linear in the samples and the marks, because a refined section carries tens of thousands
    of samples and an all-pairs comparison would be the slowest step in the measure.
    """
    n = xy.shape[0]
    seg = np.linalg.norm(np.roll(xy, -1, axis=0) - xy, axis=1)     # seg[i] = i -> i+1
    total_m = float(seg.sum())
    s = np.concatenate(([0.0], np.cumsum(seg)[:-1]))               # arc position of each sample
    delta = np.zeros(n + 1, dtype=np.int64)
    centers = s[marked]
    for shift in (-total_m, 0.0, total_m):
        lo = np.searchsorted(s, centers + shift - margin_m, side='left')
        hi = np.searchsorted(s, centers + shift + margin_m, side='right')
        np.add.at(delta, lo, 1)
        np.add.at(delta, hi, -1)
    return np.cumsum(delta[:-1]) > 0


def survives_erosion(Part, App, outer, inner, target_m):
    """**Candidate C3, and it answers a different question from the others.**

    Not "how thick is the wall here" but "is the wall at least `target_m` **anywhere** at this
    station" -- one boolean, sampling-free. The morphological argument is that a ribbon narrower
    than `target_m` somewhere comes apart when eroded by half of `target_m` from each side, so
    connectivity of the eroded region *is* the compliance test, with no sample spacing to converge
    and no nearest-point artifact to suffer from.

    IP-FC-151 closed this route against the **exact B-spline** section, where one
    `Face.makeOffset2D` call did not finish in six minutes, and left it explicitly open for a
    *simplified* section. This is that: the two loops are already polylines, so the face offset is
    the cheap polygon case that IP-FC-151 measured as textbook on a clean ribbon (1.9884 mm2 at
    d = 0.290, 0.0000 at 0.300, a refusal at 0.310, the transition landing exactly at the
    half-width).

    **It cannot supply gates G1 or G4**, which ask for a depth and a location, so it is not scored
    on the per-sample table with the others. It is screened to find out whether it works at all and
    cheaply enough to be worth keeping as a build-time *guard* beside whichever measure is selected.

    An earlier version of this function faked the morphology by clamping the incumbent's own
    nearest-point distance at `target_m`, which made it the incumbent in a hat: it inherited the
    incumbent's depth readings and so *passed* the depth gate it is supposed to be unable to pass.
    Caught by the screening's own expectation test.

    Returns `(survived, detail)`.

    **This is the only function in this module that hands coordinates back to the kernel**, and so
    the only one that converts (IP-FC-163). The loops arrive in meters from
    `sections._points_of`; `Part.makePolygon` and `makeOffset2D` are millimeters. Building the
    polygon from the meter values directly would have made a ribbon a thousandth of its true size
    and eroded it by a thousandth of the target -- a pair of errors that cancel in the *ratio* and
    so would have left the verdict looking plausible while the areas it reports were out by 1e-6.
    """
    def wire_of(points_m):
        vs = [kern.vec_mm(App, float(x), float(y), float(points_m[0][2]))
              for x, y in points_m[:, :2]]
        vs.append(vs[0])
        return Part.makePolygon(vs)

    try:
        face = Part.makeFace([wire_of(outer), wire_of(inner)], 'Part::FaceMakerBullseye')
    except Exception as exc:                                             # noqa: BLE001
        return False, 'the ribbon face would not build: %s' % type(exc).__name__
    area_before_m2 = kern.area_m2(face)
    try:
        eroded = face.makeOffset2D(-kern.mm(float(target_m)) / 2.0)
    except Exception as exc:                                             # noqa: BLE001
        # The kernel refusing the offset is itself the answer: nothing survived the erosion.
        return False, (
            'erosion refused (%s), so the ribbon is thinner than %.4f mm somewhere'
            % (type(exc).__name__, kern.mm(target_m)))
    faces = len(eroded.Faces)
    wires = len(eroded.Wires)
    area_after_m2 = kern.area_m2(eroded) if faces else 0.0
    survived = faces == 1 and wires == 2
    return survived, ('eroded by %.4f mm: %d face(s), %d wire(s), area %.4f -> %.4f mm2'
                      % (kern.mm(target_m) / 2.0, faces, wires,
                         area_before_m2 * kern.MM2_PER_M2, area_after_m2 * kern.MM2_PER_M2))


#: The per-sample thickness measures, which is what the five-gate table scores. **C3 is not here**:
#: it reports one boolean a station rather than a thickness a sample, so it cannot answer gates G1
#: or G4 and is screened separately by `survives_erosion`.
REGISTRY = {
    'C0_nearest_point_min': nearest_point_min,
    'C1_inscribed_circle': inscribed_circle,
    'C2_windowed_normal': windowed_normal,
    'C4_corner_excluded_min': corner_excluded_min,
}
