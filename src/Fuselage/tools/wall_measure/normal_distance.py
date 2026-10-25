"""IP-WTM-26: the wall measured **perpendicular to its own inner surface**, in three dimensions.

**Why a new measure, when this package already has five.** Every measure here is *in-plane*: it
sections the wall at a station `z` and measures from the inner loop to the outer loop within that
plane. Section 6.8.2.1 records what that cannot answer and says so explicitly -- "whether the real
three-dimensional wall at a notch junction is at least `t` is a different question, because every
measure here is in-plane and the surfaces at a junction are inclined to the layer plane. A 3-D
normal-distance measurement would settle it and none exists in this subsystem." This is that
measurement.

**It has to be the normal distance, and a 3-D *minimum* distance would be worse than useless.** The
in-plane nearest-point distance is a minimum taken over the inner loop within one plane; the 3-D
minimum from the same point to the same surface is a minimum over a strictly larger set, so it is
**always less than or equal** to the in-plane figure and can only ever make a thin reading thinner.
It could not exonerate a wall even in principle. What the in-plane measure gets wrong at a junction
is its *direction*: at a concave turn the nearest point lies across the corner rather than through
the material, which is the whole reason `candidates.corner_excluded_min` exists. The physically
meaningful quantity -- and the one a single-perimeter wall has to satisfy -- is the depth of material
found by leaving the inner surface along its own outward normal, and that can be larger than the
in-plane minimum. So the direction is the measurement.

**How the depth is found: `isInside` and bisection, not a boolean.** From an inner-surface point `p`
with the material-ward unit normal `n`, the wall ends at the largest `d` for which `p + d*n` is still
in the solid. Bisecting `Shape.isInside` finds that to any tolerance with no boolean operation, no
sectioning and no face classification -- which matters because the alternatives all failed here
before: a `common` between a line and a 2 400-face solid is slow and tolerance-sensitive, and
separating the wall's "inner" faces from its "outer" ones on a saved BREP has no reliable handle,
the part being neither a revolve nor convex.

**The normal is `boolean_edges.face_normal`, which is parameter-free, and that is not incidental.**
Section 6.1's fourth caution records `Surface.parameter` and `projectPoint` placing points on this
exact surface 2.411 mm out, because the interior surface is periodic in `u` and a parameter solve
returns a local minimum that looks plausible. `face_normal` instead offsets along a spread of
directions, snaps each back onto the face with `distToShape`, and takes the normal of the plane they
span.

**Four ways this declines rather than answering**, each recorded per sample, because a measurement
that guesses at a junction would be answering the question it was built to settle:

* `on_crease` -- more than one face contains `p` within tolerance, so `p` is on an edge where two
  surfaces meet and has no single normal. These are precisely the samples at issue, so they are
  named rather than silently assigned one of the two answers.
* `no_normal` -- `face_normal` found fewer than three usable neighbors, which happens at a point
  pinched between trim boundaries.
* `not_entered` -- neither `+n` nor `-n` puts the probe inside the solid at the entry step, so `p` is
  not on the boundary of this solid or the step overshoots a wall thinner than it.
* `unbounded` -- the probe is still inside at `limit`. The ray is running along the wall rather than
  across it, or it has entered a rib; either way the figure is a lower bound and not a thickness, and
  it is reported as one.

Nothing here imports a vendor module at module scope: `Part` and `App` arrive as arguments, the rule
the rest of this package holds to and that `tests/test_wall_measure_sweep.py` enforces by AST.
"""
import math

import numpy as np

from . import boolean_edges, candidates, sections

#: How far along the candidate normal the first containment probe is taken, in mm. Small against
#: `WALL_TOL` = 0.01 and against the 0.6 mm wall -- 1/600 of it -- so a wall has to be
#: pathologically thin before the entry probe overshoots it. A ladder of smaller steps is tried
#: before a sample is declined as `not_entered`, so this is a starting point rather than a floor.
ENTRY_STEP_MM = 1.0e-3

#: Successively smaller entry probes, for a wall thinner than `ENTRY_STEP_MM`.
ENTRY_LADDER = (1.0e-3, 1.0e-4, 1.0e-5)

#: Bisection stops when the bracket is narrower than this, in mm. A hundredth of `WALL_TOL`, so the
#: reading is two orders finer than the tolerance it is compared against.
DEPTH_TOL_MM = 1.0e-4

#: How far the probe may travel before the reading is called `unbounded`, as a multiple of nominal.
#: A ray that has gone five wall thicknesses is not measuring a wall.
LIMIT_FACTOR = 5.0

#: `Shape.isInside`'s own tolerance. Tight: a point this far outside counts as inside, so a loose
#: value would report material where there is none, which is the error direction that matters here.
INSIDE_TOL = 1.0e-7

#: How close a face must come to a point to be said to contain it, in mm. `distToShape` on a
#: trimmed B-spline face does not return an exact zero.
ON_FACE_TOL = 1.0e-6

#: Second-chance tolerance for a point no face claims at `ON_FACE_TOL`, in mm.
#:
#: **Required, and the reason is a bias that ran the worst possible way.** `distToShape` to a planar
#: face returns an exact distance; to a trimmed B-spline it is an iterative solve that stops at its
#: own tolerance. So a 1e-6 mm threshold systematically fails to place **B-spline** samples while
#: placing planar ones -- and the B-spline faces are the fitted interior surface, the only class
#: whose readings are wall thicknesses. Measured 2026-10-15 across three walls: of the samples no
#: face claimed at 1e-6, **every single one** lands on a B-spline at 1e-4 -- 20 of 20 on a
#: `tail_shell` at `U` = 0.5, 86 of 86 on a `nose_cowl_shell` at `U` = 4.0, and 336 of 336 on a
#: `tail_shell` at `U` = 1.0. Those three walls' fitted-surface share goes 1 % to 6.5 %, **3 % to
#: 37 %**, and 68 % to 82 %, so the tight tolerance was under-counting the real readings and
#: over-weighting the artifacts.
#:
#: **Applied as a fallback and not as the primary tolerance**, deliberately. Loosening the first
#: pass to 1e-4 would let a sample within 1e-4 of *two* faces come back as `on_crease` and be
#: declined, which would lose placements that are currently unambiguous. Strict first, loose only
#: where strict finds nothing, and a loosely placed sample is named `(loose)` so the two are never
#: indistinguishable -- keeping them apart is what exposed this in the first place.
FALLBACK_TOL = 1.0e-4

#: Beyond this angle, in degrees, between the inner surface's own normal and the in-plane shortest
#: path, the two are not measuring the same wall and the normal reading must not be read as the
#: in-plane one's correction.
#:
#: **This is the quantity section 6.8.2.1 is actually asking about, and the first real run showed
#: why it has to be measured rather than assumed.** On a `nose_cowl_shell` at `U` = 1 the thin
#: in-plane samples came back with normals of exactly `(1, 0, 0)` at points where the outward
#: direction is `-y` -- tangential to the wall. They are on **rib-slot cheeks**, which are planar
#: because the side slabs sit at constant `x`, and a depth measured perpendicular to a slot cheek is
#: the material across the slot, not across the wall: it read 0.95 and 1.05 mm on a 0.6 mm wall, and
#: four of six samples ran past the limit entirely. A measure that reported those as the wall
#: "exonerated" would have been confidently wrong in the same breath as answering the question.
#:
#: 30 degrees is generous on purpose: the inner surface really is inclined to the layer plane at a
#: junction -- that is the premise -- so some disagreement is the effect being looked for rather
#: than a fault. What it separates is disagreement from orthogonality.
#:
#: **Superseded as the discriminator, 2026-10-15, and kept only as a reported diagnostic: the angle
#: does not separate the two populations.** Measured on a real `tail_shell`, samples on the fitted
#: interior surface run 3.1 to 30.7 degrees and samples on slot cheeks run 33.2 to 50.8 -- adjacent
#: ranges with a 2.5 degree gap, so any cutoff in between is arbitrary and this one was discarding
#: genuine readings at 30.1 to 30.8 degrees. `CONSISTENCY_TOL` is the test that replaced it.
ALIGN_DEG = 30.0

#: How far `normal / cos(theta)` may fall from the in-plane reading before the two are not measuring
#: the same wall, in mm.
#:
#: **This is a measurable relationship rather than a chosen threshold, which is why it replaced the
#: angle.** A plane cutting a slab inclined at theta sees a width of `thickness / cos theta`, so on
#: any sample where both instruments really are reading one wall, `normal / cos theta` must reproduce
#: the in-plane figure. Measured on a `tail_shell` at `U` = 0.5 the two populations separate by more
#: than two orders of magnitude:
#:
#:     on the fitted interior surface   residual 0.00023 .. 0.00200 mm
#:     on rib-slot cheeks               residual 0.688   .. 0.737   mm
#:
#: `WALL_TOL` as the tolerance sits 5x above the worst real residual and 69x below the best cheek
#: one, so the gap is wide enough that the exact value does not matter -- which is the property an
#: arbitrary cutoff lacked.
CONSISTENCY_TOL = 0.01

#: The acceptance tolerance, as the rest of this package spells it. A sample counts as thin when it
#: is under `nominal - WALL_TOL`, which is the gate's own failure threshold.
#:
#: **Not "under nominal", and the difference is not pedantic -- it was measured here.** Selecting
#: every sample under nominal picked **all 360** inner samples of a `uniform_tube` whose wall is
#: exactly 0.6 mm, because both loops are discretized and the outer polygon's chords cut inside the
#: true circle: at `R` = 10 with 360 points the sag is 0.000381 mm, so every reading is 0.59962. That
#: is the same bias section 6.8.3 measures on `CHECK_ARC`, where a coarse exterior polyline makes
#: every distance to it short -- here it would have filled this measure's sample set with
#: sub-micron noise and buried the twelve samples that actually fail.
WALL_TOL = 0.01


#: The fitted interior surface's own surface type. `_fit` produces a B-spline, so a sample on one of
#: these is on the wall's real inner boundary; a sample on a `Part::GeomPlane` is on a **cut** face
#: -- a rib-slot cheek or a cell-cut face -- and a sample on `Part::GeomSurfaceOfExtrusion` is on
#: one of the end-overrun walls section 6.1's fifth caution names.
#:
#: **Measured on a `nose_cowl_shell` wall at `U` = 1: 480 planes, 40 B-splines, 16 extrusions.** So
#: most of this boundary is cut faces, and which class a thin reading is taken on decides whether it
#: is a wall thickness at all.
FITTED_SURFACE = 'Part::GeomBSplineSurface'

#: What `surface_type` reports when the kernel will not say. Under `freecadcmd` it always will; the
#: geometry bridge may not proxy `Surface` for every surface class, and a measurement must not fail
#: because a diagnostic field is unavailable.
UNKNOWN_SURFACE = 'unknown'


def surface_type(face):
    """`face`'s underlying surface class, or `UNKNOWN_SURFACE`.

    Guarded because this is a *diagnostic* field: it decides how a reading is reported, not whether
    the reading happens, so a kernel or bridge that will not answer must not take the measurement
    down with it.
    """
    try:
        return str(face.Surface.TypeId)
    except Exception:                                  # noqa: BLE001 - a diagnostic, not a result
        return UNKNOWN_SURFACE


def faces_at(solid, point, tol=ON_FACE_TOL, Part=None):
    """Every face of `solid` containing `point`, as `(index, face)`. Pruned by bounding box first.

    **More than one is a finding, not a tie to break.** Two faces containing a point means the point
    is on the edge where they meet -- a crease -- and a crease has no single normal. Returning the
    list lets the caller decline; picking one would answer the junction question by assumption.

    The bounding-box prune is what makes this affordable: a `tail_shell` wall has about 2 400 faces
    and a `distToShape` against each is the whole cost of this measure, while a point is inside the
    box of only a handful.
    """
    p = np.asarray(point, dtype=float)
    vertex = Part.Vertex(float(p[0]), float(p[1]), float(p[2]))
    out = []
    for i, face in enumerate(solid.Faces):
        # Plain arithmetic on the box's six floats rather than `BoundBox.isInside` plus a
        # point-distance call: it needs no vendor method beyond the attributes, and the margin has
        # to be applied anyway because a point *on* a face is on its box's boundary.
        box = face.BoundBox
        if not (box.XMin - tol <= p[0] <= box.XMax + tol
                and box.YMin - tol <= p[1] <= box.YMax + tol
                and box.ZMin - tol <= p[2] <= box.ZMax + tol):
            continue
        if float(vertex.distToShape(face)[0]) <= tol:
            out.append((i, face))
    return out


def _inside(solid, point, App, tol=INSIDE_TOL):
    return bool(solid.isInside(App.Vector(float(point[0]), float(point[1]), float(point[2])),
                               tol, True))


def entry_direction(solid, point, normal, App, ladder=ENTRY_LADDER, tol=INSIDE_TOL):
    """`normal` turned to point into the material, with the step that proved it, or `(None, None)`.

    `face_normal`'s sign is arbitrary -- it comes from a singular vector -- so which way is into the
    wall has to be established rather than assumed. Tries both signs at each step of the ladder and
    takes the first that lands inside. Returns `(oriented_normal, step)`.

    **Both signs inside is not possible for a point on the boundary of a solid and is treated as a
    failure**, because it means the probe is not on the boundary at all: a point in the interior has
    material both ways, and measuring a wall outward from it would return a number with no meaning.
    """
    n = np.asarray(normal, dtype=float)
    norm = float(np.linalg.norm(n))
    if not np.isfinite(norm) or norm == 0.0:
        return None, None
    n = n / norm
    p = np.asarray(point, dtype=float)
    for step in ladder:
        plus = _inside(solid, p + step * n, App, tol)
        minus = _inside(solid, p - step * n, App, tol)
        if plus and minus:
            return None, None
        if plus:
            return n, step
        if minus:
            return -n, step
    return None, None


def exit_depth(solid, point, direction, App, limit, step, tol=DEPTH_TOL_MM,
               inside_tol=INSIDE_TOL):
    """How far along `direction` the solid extends from `point`, by bisection on `isInside`.

    Returns `(depth, bounded)`. `bounded` is `False` when the probe is still inside at `limit`, in
    which case `depth` is `limit` and is a **lower bound rather than a thickness** -- the caller must
    not report it as one.

    Assumes `point + step*direction` is inside, which `entry_direction` has established.
    """
    p = np.asarray(point, dtype=float)
    n = np.asarray(direction, dtype=float)
    if _inside(solid, p + limit * n, App, inside_tol):
        return float(limit), False
    lo, hi = float(step), float(limit)
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if _inside(solid, p + mid * n, App, inside_tol):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi), True


def cos_consistency(in_plane_mm, thickness_mm, angle_deg_value):
    """`normal / cos(theta) - in_plane`, the residual of the inclined-slab identity, in mm.

    `None` when any input is missing; `inf` when `cos(theta)` is zero or negative, which is a normal
    orthogonal to or facing away from the in-plane path and so has no consistent reading at all.
    """
    if in_plane_mm is None or thickness_mm is None or angle_deg_value is None:
        return None
    if not np.isfinite(angle_deg_value):
        return float('inf')
    cos = math.cos(math.radians(float(angle_deg_value)))
    # **`<= 0` is not the right guard and does not fire**: `cos(radians(90.0))` is 6.12e-17, not
    # zero, so a perfectly orthogonal normal would divide by it and return 9.8e15 -- a number, not
    # an `inf`, and one that happens to be classified correctly while telling the reader nothing.
    # Below this the identity is numerically meaningless rather than merely large.
    if cos <= 1.0e-12:
        return float('inf')
    return float(thickness_mm) / cos - float(in_plane_mm)


def normal_thickness(solid, point, App, Part, nominal=0.6, limit=None, h=None,
                     depth_tol=DEPTH_TOL_MM, on_face_tol=ON_FACE_TOL, plane_dir=None,
                     align_deg=ALIGN_DEG, fallback_tol=FALLBACK_TOL,
                     in_plane_mm=None, consistency_tol=CONSISTENCY_TOL):
    """The wall depth at `point`, measured along the inner surface's own outward normal.

    Returns a dict always, never `None`: `declined` names why there is no reading, because a sample
    this measure cannot read is the thing worth knowing at a junction and dropping it silently would
    bias the answer toward whichever samples happen to be easy.

    Keys: `thickness_mm`, `bounded`, `declined`, `faces`, `normal`, `normal_residual_mm`,
    `offsets_used`, `entry_step_mm`.
    """
    limit = float(nominal * LIMIT_FACTOR) if limit is None else float(limit)
    row = {'x': float(point[0]), 'y': float(point[1]), 'z': float(point[2]),
           'thickness_mm': None, 'bounded': None, 'declined': None, 'faces': 0,
           'normal': None, 'normal_residual_mm': None, 'offsets_used': None,
           'entry_step_mm': None, 'plane_angle_deg': None, 'aligned': None,
           'surface': None, 'exit_surface': None, 'exit_point': None, 'exit_faces': None,
           'placed_loose': False, 'cos_residual_mm': None, 'consistent': None}
    found = faces_at(solid, point, on_face_tol, Part=Part)
    # **The same fallback the census needs, for the same reason** -- see `FALLBACK_TOL`. Without it
    # this function declines exactly the B-spline samples it most needs to read: the first targeted
    # run on a `tail_shell` measured 4 samples where 24 were on the fitted surface, the other 20
    # having been turned away as `off_surface` by a tolerance a planar face meets and a trimmed
    # B-spline does not.
    if not found and fallback_tol:
        found = faces_at(solid, point, float(fallback_tol), Part=Part)
        row['placed_loose'] = bool(found)
    row['faces'] = len(found)
    if not found:
        row['declined'] = 'off_surface'
        return row
    if len(found) > 1:
        # **Named, not resolved.** A point on a crease has two normals and two defensible answers;
        # these are the samples section 6.8.2.1's question is about.
        row['declined'] = 'on_crease'
        return row
    _index, face = found[0]
    row['surface'] = surface_type(face)
    kwargs = {} if h is None else {'h': h}
    normal, residual, used = boolean_edges.face_normal(Part, face, point, **kwargs)
    row.update(normal_residual_mm=float(residual), offsets_used=int(used))
    if normal is None:
        row['declined'] = 'no_normal'
        return row
    oriented, step = entry_direction(solid, point, normal, App)
    if oriented is None:
        row['declined'] = 'not_entered'
        return row
    row['normal'] = [float(v) for v in oriented]
    row['entry_step_mm'] = float(step)
    if plane_dir is not None:
        # **The angle between the two measurements' directions, recorded before either is
        # believed.** See `ALIGN_DEG`: a normal orthogonal to the in-plane path means the sample is
        # on a face whose normal runs *along* the wall -- a rib-slot cheek -- and the depth found
        # that way is the material across the slot, not the wall.
        theta = angle_deg(oriented, plane_dir)
        row['plane_angle_deg'] = theta
        row['aligned'] = bool(np.isfinite(theta) and theta <= float(align_deg))
    depth, bounded = exit_depth(solid, point, oriented, App, limit, step, depth_tol)
    row.update(thickness_mm=float(depth), bounded=bool(bounded))
    if bounded:
        # **What the ray leaves through, which decides what the depth is a thickness *of*.** A
        # normal reading shorter than the in-plane minimum is not a contradiction: the in-plane
        # figure is a minimum over the outer loop within one plane, while the ray can exit anywhere
        # on the boundary -- including through a rib slot it runs into. Leaving through the OML makes
        # the depth a wall thickness to the exterior; leaving through a cut face makes it the web
        # between the interior surface and that slot, which is a different quantity the construction
        # also intends to be `t` (it dilates each notch by `t` for exactly that) but which is not
        # what `WALL_TOL` gates.
        exit_point = np.asarray(point, dtype=float) + float(depth) * np.asarray(oriented,
                                                                               dtype=float)
        # **The exit's tolerance is the bisection's, not the entry's**, and getting that wrong made
        # all four readings on a real tail report `off_surface`. The entry point comes off a section
        # wire and lies on its face to kernel tolerance, so 1e-6 mm is right for it; the exit point
        # is wherever bisection stopped, which is within `depth_tol` = 1e-4 mm of the boundary and
        # therefore up to a hundred times further out than that. Classifying it at the entry's
        # tolerance asks whether a point known to be 1e-4 from the surface is within 1e-6 of it.
        exit_tol = max(float(on_face_tol), 2.0 * float(depth_tol))
        at_exit = faces_at(solid, exit_point, exit_tol, Part=Part)
        row['exit_point'] = [float(v) for v in exit_point]
        row['exit_faces'] = len(at_exit)
        row['exit_surface'] = (surface_type(at_exit[0][1]) if len(at_exit) == 1
                               else ('on_crease' if at_exit else 'off_surface'))
    # **The inclined-slab identity, which is the discriminator.** See `CONSISTENCY_TOL`: the angle
    # alone does not separate a reading on the fitted surface from one on a slot cheek, but whether
    # `normal / cos(theta)` reproduces the in-plane figure does, by two orders of magnitude.
    residual = cos_consistency(in_plane_mm, row['thickness_mm'], row['plane_angle_deg'])
    row['cos_residual_mm'] = residual
    if residual is not None:
        row['consistent'] = bool(abs(residual) <= float(consistency_tol))
    if not bounded:
        row['declined'] = 'unbounded'
    elif row['consistent'] is False:
        row['declined'] = 'inconsistent'
    return row


def nearest_foot(point, poly, segment):
    """Where on `poly`'s `segment`-th edge the perpendicular from `point` lands, in 2-D.

    `candidates._segment_nearest` returns the distance and *which* segment was nearest; this is the
    foot itself, which is what gives the in-plane shortest path a **direction**. Kept here rather
    than added there because every existing caller of that function wants only the index, and this
    is new arithmetic that has to be tested on its own.
    """
    a = np.asarray(poly, dtype=float)[:, :2]
    j = int(segment) % a.shape[0]
    p0, p1 = a[j], a[(j + 1) % a.shape[0]]
    ab = p1 - p0
    denom = float(ab @ ab)
    t = 0.0 if denom == 0.0 else float(np.clip((np.asarray(point[:2], dtype=float) - p0) @ ab
                                               / denom, 0.0, 1.0))
    return p0 + t * ab


def angle_deg(a, b):
    """The unsigned angle between two vectors, in degrees, or `nan` if either is degenerate."""
    u, v = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    nu, nv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
    if not (np.isfinite(nu) and np.isfinite(nv)) or nu == 0.0 or nv == 0.0:
        return float('nan')
    return float(np.degrees(np.arccos(np.clip(float(u @ v) / (nu * nv), -1.0, 1.0))))


def thin_samples(outer, inner, nominal, measure=None, margin=WALL_TOL):
    """The inner samples an in-plane measure reads under `nominal - margin`, worst first.

    `measure` defaults to `candidates.nearest_point_min`'s own per-sample distances, which is the
    **incumbent** gate's reading -- the one whose figure section 6.8.2.1 calls 63 % junction
    artifact on a tail. The point of this module is to re-ask those same samples in 3-D, so the
    sample set has to be the incumbent's rather than a fresh one.
    """
    del measure                       # the incumbent's own reading; see the note below
    # **`_segment_nearest`, not `nearest_point_min`, and the extra return is the point.** The
    # distance alone cannot say which way the shortest path ran, and that direction is the whole
    # question here: section 6.8.2.1's claim is that at a junction the in-plane path does not cross
    # the wall. The distances are identical -- that function's own docstring records it is the same
    # arithmetic as `_segment_distances` with an `argmin` alongside the `min`, and a test holds the
    # two together so they cannot drift.
    dists, which = candidates._segment_nearest(inner, outer)          # noqa: SLF001 - same package
    order = np.argsort(dists)
    out = []
    for k in order:
        if float(dists[k]) >= nominal - margin:
            break
        # **The sample's own three coordinates, not a rebuilt point.** `station_loops` returns
        # `(n, 3)` arrays, so the `z` here is the one the kernel put on the section rather than the
        # station it was asked for. The two differ by the slicer's own tolerance, and a probe placed
        # at the requested `z` can miss the face by that much -- which `faces_at` would report as
        # `off_surface`.
        point = tuple(float(v) for v in inner[k][:3])
        foot = nearest_foot(point, outer, which[k])
        # In-plane by construction: the section is a `z` plane, so the shortest path has no `z`.
        step = np.array([foot[0] - point[0], foot[1] - point[1], 0.0], dtype=float)
        out.append({'i': int(k), 'in_plane_mm': float(dists[k]), 'point': point,
                    'outer_point': (float(foot[0]), float(foot[1]), point[2]),
                    'plane_dir': [float(v) for v in step]})
    return out


def thin_by_surface(shape, thin, Part, tol=ON_FACE_TOL, fallback_tol=FALLBACK_TOL):
    """Which face class each thin sample sits on, counted. **No normals, no bisection, so cheap.**

    This is the half of the question that can be asked of *every* thin sample rather than the worst
    dozen, and on a real wall it is the decisive half. If every reading under tolerance is taken on
    a cut face and none on the fitted interior surface, then the fitted wall is not thin anywhere and
    the residual is an artifact of measuring from a cut face -- which is what section 6.8.2.1 asks,
    answered without needing a direction at all.

    Returns `(counts, by_sample)`: the census, and the surface class per sample in the order given.
    """
    counts, per_sample = {}, []
    for s in thin:
        found = faces_at(shape, s['point'], tol, Part=Part)
        # **An `off_surface` is retried at a looser tolerance before it is counted as one, because
        # it would otherwise be an undercount of the class that matters.** A sample the census
        # cannot place is a sample excluded from the "is it on the fitted interior surface?"
        # question, and the first real run left 20 of 372 unplaced on a `tail_shell` -- against a
        # fitted-surface count of 4. If even a few of those 20 were on the fitted surface the
        # conclusion would move, so the retry is reported separately (`off_surface_loose`) rather
        # than silently folded in: a sample that needs 1e-4 mm of slack to land on a face is placed
        # less certainly than one that lands at 1e-6, and the two should not be indistinguishable.
        loose = False
        if not found and fallback_tol:
            found = faces_at(shape, s['point'], float(fallback_tol), Part=Part)
            loose = bool(found)
        if not found:
            kind = 'off_surface'
        elif len(found) > 1:
            kind = 'on_crease'
        else:
            kind = surface_type(found[0][1])
        if loose:
            kind = kind + ' (loose)'
        counts[kind] = counts.get(kind, 0) + 1
        per_sample.append(kind)
    return counts, per_sample


def surface_ranks(per_sample, kind=FITTED_SURFACE):
    """Where in the in-plane severity ordering the samples of one face class sit, 0-based.

    **The measurement OQ-DES-CW33's alternative 2 names as its prerequisite.** That alternative uses
    the cheap in-plane measure as a search and re-measures the worst `N` samples a station in 3-D, so
    everything turns on whether in-plane severity ranks the samples that matter near the top. It does
    not on the one wall measured so far -- the four readings that are wall thicknesses were nowhere
    near any station's twelve worst -- and `N` cannot be chosen until that is quantified.

    `per_sample` is `thin_by_surface`'s second return, which is in the same worst-first order
    `thin_samples` produced.

    **Matched by prefix, so a `(loose)` placement counts.** A sample that needed `FALLBACK_TOL` of
    slack to land on the fitted surface is still a reading on the fitted surface, and on the three
    walls measured every unplaced sample turned out to be one of those -- so exact matching would
    drop the majority of the class on two of them.
    """
    return [i for i, got in enumerate(per_sample) if str(got).startswith(kind)]


def selector_verdict(stations, kind=FITTED_SURFACE):
    """Could a worst-`N` in-plane selector have found this face class's samples, and at what `N`?

    Returns `needed_n` -- one past the deepest rank any such sample sits at, so a confirmation pass
    with `worst` below it provably misses one -- alongside the per-station ranks and how that compares
    with the thin count it would have had to re-measure.

    **`established` is `False` when no station has a sample of this class**, because a wall whose
    thin readings are all on cut faces cannot say anything about how to rank the ones that are not.
    That is this subsystem's recurring guard in its ninth place.
    """
    rows, deepest, thin_total, with_kind = [], -1, 0, 0
    for station in stations:
        ranks = station.get('fitted_ranks')
        if ranks is None:
            continue
        thin = int(station.get('thin_in_plane') or 0)
        thin_total += thin
        if ranks:
            with_kind += 1
            deepest = max(deepest, max(ranks))
        rows.append({'z': station.get('z'), 'thin': thin, 'ranks': list(ranks),
                     'fraction': (max(ranks) + 1) / float(thin) if (ranks and thin) else None})
    reasons = []
    if not rows:
        reasons.append('no station reported a rank census')
    if not with_kind:
        reasons.append('no station has a thin sample on %s, so the ranking cannot be judged' % kind)
    return {'kind': kind, 'stations': len(rows), 'stations_with_kind': with_kind,
            'thin_total': thin_total, 'deepest_rank': deepest if deepest >= 0 else None,
            'needed_n': deepest + 1 if deepest >= 0 else None, 'rows': rows,
            'vacuous_because': reasons, 'established': not reasons}


def rank_table(verdict):
    """`selector_verdict` as text: what `N` each station would have needed."""
    head = '%12s %8s %8s %10s  %s' % ('z', 'thin', 'on kind', 'needs N', 'ranks (0-based)')
    out = [head, '-' * len(head)]
    for r in verdict['rows']:
        ranks = r['ranks']
        out.append('%12.4f %8d %8d %10s  %s'
                   % (r['z'], r['thin'], len(ranks),
                      '-' if not ranks else str(max(ranks) + 1),
                      '-' if not ranks else ', '.join(str(v) for v in ranks[:12])))
    return '\n'.join(out)


def station_normals(shape, z, nominal, App, Part, n_points=None, spacing=None, worst=12,
                    margin=WALL_TOL, limit=None, h=None, census=True, only_surface=None,
                    fallback_tol=None):
    """At one station: the in-plane thin samples, each re-measured along its own normal in 3-D.

    `worst` caps how many samples are re-measured, because each costs a `distToShape` per candidate
    face plus a bisection of about fourteen `isInside` calls. Ordered worst-first, so a cap keeps
    the samples the question is about.
    """
    # **A spacing, not a count, and it is derived here because `station_loops` takes a count.**
    # `locate.state_profile` does the same conversion for the same reason: the part scales with `U`
    # and the 0.6 mm wall does not, so a fixed count is a different circumferential resolution at
    # every size. The one extra slice `section_perimeter` costs is paid once a station.
    if spacing is not None:
        from . import density
        wires = sections.closed_wires(shape, z, App=App)
        if len(wires) < 2:
            return {'z': float(z), 'rows': [], 'loops': len(wires), 'declined': 'no_annulus',
                    'thin_in_plane': 0}
        perimeter = max(float(w.Length) for w in wires)
        loops = sections.loops_from_wires(wires, density.counts_for_spacing(perimeter, spacing))
    elif n_points is not None:
        loops = sections.station_loops(shape, z, n_points, App=App)
    else:
        loops = sections.station_loops(shape, z, App=App)
    if len(loops) < 2:
        return {'z': float(z), 'rows': [], 'loops': len(loops), 'declined': 'no_annulus',
                'thin_in_plane': 0}
    outer, inner = loops[0], loops[1]
    thin = thin_samples(outer, inner, nominal, margin=margin)
    counts, per_sample = (thin_by_surface(shape, thin, Part, fallback_tol=fallback_tol)
                          if (census and thin) else ({}, []))

    # **`only_surface` exists because the worst-N and the question are not the same set.** On a
    # `tail_shell` at `U` = 0.5, 347 of 372 thin samples sit on planar cut faces and just **4** on
    # the fitted interior surface -- and those 4 are the only ones whose in-plane reading is a wall
    # thickness at all. None of them need be among any station's twelve worst, so a cap ordered by
    # severity can measure a hundred samples and miss every sample that matters.
    chosen = list(enumerate(thin))
    if only_surface is not None and per_sample:
        # Prefix, for `surface_ranks`' reason: a `(loose)` placement on the fitted surface is a
        # reading on the fitted surface, and exact matching selected 4 samples where 24 qualified.
        chosen = [(k, s) for k, s in chosen if str(per_sample[k]).startswith(only_surface)]
    rows = []
    for _k, s in chosen[:int(worst)]:
        row = normal_thickness(shape, s['point'], App, Part, nominal=nominal, limit=limit, h=h,
                               plane_dir=s['plane_dir'], fallback_tol=fallback_tol,
                               in_plane_mm=s['in_plane_mm'])
        row.update(in_plane_mm=s['in_plane_mm'], i=s['i'], outer_point=s['outer_point'])
        rows.append(row)
    return {'z': float(z), 'rows': rows, 'loops': len(loops), 'declined': None,
            'thin_in_plane': len(thin), 'samples': len(inner), 'thin_surfaces': counts,
            'only_surface': only_surface,
            # The severity ranks of the samples that are actually wall thicknesses -- see
            # `surface_ranks`. `None` rather than `[]` when no census ran, so a caller can tell
            # "nothing on the fitted surface" from "nobody looked".
            'fitted_ranks': surface_ranks(per_sample) if per_sample else (
                [] if (census and thin) else None)}


def exoneration(rows, nominal, tol=0.01):
    """How the 3-D normal reading compares with the in-plane one, sample by sample.

    `exonerated` means the in-plane figure is under `nominal - tol` -- a real failure by the gate's
    own threshold -- while the normal reading is at or above `nominal - tol`. That is the only
    combination that says the in-plane reading was a direction artifact rather than missing
    material, and it is the claim section 6.8.2.1 asks for.

    `confirmed` is the opposite and equally important: both readings thin, so the material really is
    absent and no exclusion rescues it.
    """
    floor = float(nominal) - float(tol)
    # **Only a sample where both instruments are reading one wall can correct the other.**
    # `consistent` is `False` where `normal / cos(theta)` fails to reproduce the in-plane figure,
    # which means the two are measuring different walls: such a sample's depth is a real distance
    # through material and not a correction to the in-plane reading, so it is reported apart rather
    # than counted either way. `None` is a sample measured without an in-plane figure to compare
    # against -- the direct `normal_thickness` call a test makes -- and is treated as comparable.
    read = [r for r in rows if r.get('thickness_mm') is not None and r.get('bounded')]
    aligned = [r for r in read if r.get('consistent') is not False]
    oblique = [r for r in read if r.get('consistent') is False]
    exonerated, confirmed = [], []
    for r in aligned:
        if float(r['in_plane_mm']) >= floor:
            continue
        (exonerated if float(r['thickness_mm']) >= floor else confirmed).append(r)
    declined = {}
    for r in rows:
        why = r.get('declined')
        if why:
            declined[why] = declined.get(why, 0) + 1
    return {'read': len(read), 'aligned': len(aligned), 'oblique': oblique,
            'exonerated': exonerated, 'confirmed': confirmed, 'declined': declined,
            'worst_in_plane_mm': min((float(r['in_plane_mm']) for r in rows), default=None),
            'worst_normal_mm': min((float(r['thickness_mm']) for r in aligned), default=None)}


def normal_verdict(stations, nominal, tol=0.01):
    """The whole scan's answer, with the guard that stops it reporting a pass from nothing.

    `clean` here does **not** mean the wall is good -- it means *this measurement established
    something*. Specifically it requires that at least one sample was thin in-plane (otherwise there
    was nothing to explain and a compliant specimen cannot test an explanation of non-compliance --
    section 6.1's first caution, paid for seven times in this subsystem) and that at least one such
    sample produced a bounded normal reading (otherwise every sample declined and the answer is
    silence, not exoneration).
    """
    rows = [r for s in stations for r in s.get('rows', [])]
    agg = exoneration(rows, nominal, tol)
    thin_in_plane = sum(1 for r in rows if float(r.get('in_plane_mm', nominal)) < nominal - tol)
    # **The census over every thin sample, not only the re-measured ones.** `station_normals` caps
    # how many samples get a normal; the surface class is cheap enough to ask of all of them, and on
    # a real wall it is this column that answers the question.
    surfaces = {}
    for station in stations:
        for kind, n in (station.get('thin_surfaces') or {}).items():
            surfaces[kind] = surfaces.get(kind, 0) + n
    thin_total = sum(int(s.get('thin_in_plane') or 0) for s in stations)
    on_fitted = int(surfaces.get(FITTED_SURFACE, 0))
    # **Any class naming the fitted surface blocks the census route, including a loosely placed
    # one**, and so does any sample the census could not place at all. The first version required
    # only `on_fitted == 0`, which would have called the question settled on a wall with twenty
    # unplaced samples -- and an unplaced sample is precisely one that was never asked whether it is
    # on the fitted surface. It happened not to matter on the wall that exposed it, because four
    # samples were placed there and blocked it anyway, but the guard was unsound.
    fitted_any = sum(n for kind, n in surfaces.items() if kind.startswith(FITTED_SURFACE))
    unplaced = sum(n for kind, n in surfaces.items()
                   if kind.startswith('off_surface') or kind.startswith('on_crease'))
    reasons = []
    # **Counted from the stations, not from `rows`.** `station_normals` caps how many samples get a
    # normal, so `rows` is a subset of the thin ones and a guard reading it would call a run vacuous
    # whenever the census was the thing that answered it. Found by the census test: a station with
    # twelve thin samples all on cut faces reported "no sample is thin in-plane".
    if not rows and not surfaces:
        reasons.append('no sample was measured')
    if not (thin_total or thin_in_plane):
        reasons.append('no sample is thin in-plane, so there is nothing to explain')
    # **The surface census can establish the answer on its own**, so it excuses the normal
    # readings' silence: if every thin sample across every station sits on a cut face and none on
    # the fitted interior surface, then the fitted wall is nowhere thin and no direction was needed
    # to say so. Only when the census is absent or inconclusive does a missing normal reading leave
    # the run with nothing.
    census_settles = (bool(surfaces) and thin_total > 0
                      and fitted_any == 0 and unplaced == 0)
    if not (agg['exonerated'] or agg['confirmed']) and not census_settles:
        reasons.append('no thin sample produced a bounded normal reading, and the surface census '
                       'does not settle it either')
    return {'stations': len(stations), 'samples': len(rows), 'thin_in_plane': thin_in_plane,
            'thin_total': thin_total, 'thin_surfaces': surfaces, 'thin_on_fitted': on_fitted,
            'thin_on_fitted_any': fitted_any, 'thin_unplaced': unplaced,
            'census_settles': census_settles,
            'read': agg['read'], 'aligned': agg['aligned'], 'n_oblique': len(agg['oblique']),
            'n_exonerated': len(agg['exonerated']),
            'n_confirmed': len(agg['confirmed']), 'declined': agg['declined'],
            'worst_in_plane_mm': agg['worst_in_plane_mm'],
            'worst_normal_mm': agg['worst_normal_mm'],
            'vacuous_because': reasons, 'established': not reasons}


def normal_table(stations, nominal):
    """One row a re-measured sample: what the plane said, what the normal says, or why not."""
    head = '%10s %6s %10s %10s %9s %7s %10s %-26s %s' % (
        'z', 'i', 'in-plane', 'normal 3-D', 'delta', 'n vs u', 'cos resid', 'exits through', 'note')
    out = [head, '-' * len(head)]
    for s in stations:
        for r in s.get('rows', []):
            normal = r.get('thickness_mm')
            delta = None if normal is None else float(normal) - float(r['in_plane_mm'])
            theta = r.get('plane_angle_deg')
            resid = r.get('cos_residual_mm')
            out.append('%10.4f %6d %10.5f %10s %9s %7s %10s %-26s %s'
                       % (r['z'], r.get('i', -1), r['in_plane_mm'],
                          'n/a' if normal is None else '%.5f' % normal,
                          'n/a' if delta is None else '%+.5f' % delta,
                          'n/a' if theta is None else '%6.2f' % theta,
                          'n/a' if resid is None else '%+.5f' % resid,
                          r.get('exit_surface') or 'n/a',
                          r.get('declined') or 'read'))
    return '\n'.join(out)
