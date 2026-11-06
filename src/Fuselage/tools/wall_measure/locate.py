"""Where a wall is thinnest, and whether it is thin or broken.

Section 6.4 established that no fully measured cowl wall meets `WALL_TOL`, and section 6.5 that the
shortfall is zero below `U` = 3 and 0.11-0.17 mm above it. Neither says *where* on the wall the thin
spot is, and the first thing to settle before looking for a cause is whether those readings are a
thin wall at all: a severed section ring was once misreported as a 0.355705 mm thickness
(cowl.md OQ-DES-CW26), and the `U` >= 4 readings sit above that.

This module answers both from a saved wall, with no build:

* `ring_state` classifies a section's topology -- a healthy annulus, one severed arc, several arcs,
  or no wall -- from the loops alone, in `numpy`.
* `station_detail` adds where the minimum sits: `(x, y)`, its polar angle, and its radius, so a
  reading can be set against the construction's own angles (`top_diag_angle` = 30 degrees on the
  tail) and against the notch edges.
* `profile` runs a dense scan in `z`, which is what bounds the 12-station acceptance grid's own
  blind spots.

**The topology test here is a cheap proxy for the kernel's, deliberately.**
`check_cowl_interior._is_annulus` builds faces and asks for one region with one hole, which is
authoritative and costs a kernel call a station; a dense scan wants hundreds of stations. The test
below is point-in-polygon nesting on the sampled loops, which agrees with the kernel on every case
the kernel calls healthy and is not a substitute for it at a tangency. `agrees_with_kernel` exists
to check that on a sample rather than to assume it.

Nothing here imports a vendor module: `Part` and `App` arrive as arguments.
"""
import numpy as np

from . import candidates, kern, sections

#: Classifications `ring_state` returns.
ANNULUS = 'annulus'                  #: Two nested loops: a healthy wall section.
SEVERED_ONE = 'severed_one_arc'      #: One loop and no hole: the ring broke once, leaving a C.
SEVERED_MANY = 'severed_arcs'        #: Several loops, none nested: the ring broke more than once.
NO_WALL = 'no_wall'                  #: Nothing closed at this station.
NESTED_EXTRA = 'nested_extra'        #: More than two loops with nesting: unexpected, reported.

#: Section 6.4's working sampling density, as a **count**.
#:
#: **A fixed count is the wrong parameterization on a part that scales, and this module was caught
#: by it.** The cowl grows with `U` while the wall stays 0.6 mm, so 720 points is 0.37 mm apart on a
#: `tail_shell` at `U` = 1 and about 3 mm apart at `U` = 4. At that spacing the sampled inner loop
#: can cross outside the sampled outer loop even though the real wall is intact, and `ring_state`
#: then called a healthy `U` = 4 annulus `severed_arcs` -- a false positive caught by
#: `agrees_with_kernel` at `z` = -285.2857, where the kernel said annulus. Callers that care about
#: absolute accuracy should pass a count from `density.counts_for_spacing`, which fixes the spacing
#: instead. This default is kept only for the small sections where it is already fine.
N_POINTS = 720

#: Circumferential spacing that `station_detail` targets when it is given a perimeter to work
#: from. A third of the wall, so a chord's sag is well inside the quantity being measured.
#: Converted from 0.2 mm by IP-FC-163 and is the same spacing.
TARGET_SPACING_M = 2.0e-4

#: The spacing the acceptance gate reads the finished wall at, mirrored here the way `density`'s
#: gate constants mirror the gate's. Was 0.125 mm.
GATE_ARC_M = 1.25e-4

#: The arc-length window `curvature_profile` fits its circle over. Was 2.0 mm: long enough that
#: three samples of a finely sampled B-spline are not collinear to within round-off.
CURV_WINDOW_M = 2.0e-3

#: How far `dense_grid` stands off each end of the wall. Was 1.0 mm.
DENSE_INSET_M = 1.0e-3

#: The cowl's own nominal wall, `cowl_n_perimeters` * `extrusion_width` = 1 * 0.6 mm.
NOMINAL_M = 6.0e-4

#: `cowl_interior.WALL_TOL_M` and `TAU_M`, carried here so a reader of this module's output does
#: not have to go and find them. The port is authoritative for both values.
WALL_TOL_M = 1.0e-5
TAU_M = 5.0e-5

#: How close two exterior readings have to be before `exterior_verdict` calls them the same
#: number. Was 1.0e-6 mm, so it moved with the readings it compares (IP-FC-163).
COINCIDE_TOL_M = 1.0e-9

#: The margin by which a subset measure is allowed to exceed the measure it is a subset of before
#: that is reported as a defect rather than round-off. Was 1e-12 mm.
SUBSET_TOL_M = 1.0e-15

#: Below this, three points are collinear and the circle through them is meaningless. **An area,
#: not a length**: `_circle_radius`'s determinant is twice a triangle's signed area, so this moved
#: by a million where every length in this module moved by a thousand. Was 1.0e-12 mm2.
COLLINEAR_AREA_M2 = 1.0e-18


def _winding_inside(point, poly):
    """Is `point` strictly inside the closed polyline `poly`? Crossing-number, vectorized over edges.

    Used instead of a signed-area or bounding-box test because an inner loop that traces into a
    notch and back out is strongly non-convex, and its bounding box overlaps the outer loop's
    almost exactly.
    """
    x, y = float(point[0]), float(point[1])
    ax, ay = poly[:, 0], poly[:, 1]
    bx, by = np.roll(ax, -1), np.roll(ay, -1)
    # Edges that straddle the horizontal ray y = const, counted on one side only so a vertex on the
    # ray is not counted twice.
    straddles = ((ay > y) != (by > y))
    with np.errstate(divide='ignore', invalid='ignore'):
        t = (y - ay) / (by - ay)
        xs = ax + t * (bx - ax)
    crossings = np.count_nonzero(straddles & (xs > x))
    return bool(crossings % 2)


def _is_nested(outer, inner, samples=16):
    """Does `inner` lie inside `outer`? Tested at several points, not one.

    One point can fall inside by accident when two arcs interleave, which is the case this has to
    separate from a real annulus. Every sampled point must be inside.
    """
    if len(inner) == 0:
        return False
    idx = np.linspace(0, len(inner) - 1, min(samples, len(inner))).astype(int)
    return all(_winding_inside(inner[i], outer) for i in idx)


def ring_state(loops):
    """Classify a station's section from its loops, ordered outer-first as `station_loops` returns.

    Returns `(state, detail)` where `detail` carries the loop count, the enclosed areas and -- for an
    annulus -- the area ratio, which is a scale-free health figure: a 0.6 mm wall on a large section
    makes the inner area very nearly the outer's, and a ratio far from 1 means the inner loop is not
    a wall bore at all. The ratio is unit-invariant; the areas are square meters.
    """
    areas_m2 = [abs(sections.signed_area(a)) for a in loops]
    detail = {'loops': len(loops), 'areas_m2': areas_m2, 'area_ratio': None}
    if not loops:
        return NO_WALL, detail
    if len(loops) == 1:
        return SEVERED_ONE, detail
    nested = [i for i in range(1, len(loops)) if _is_nested(loops[0], loops[i])]
    if not nested:
        return SEVERED_MANY, detail
    detail['area_ratio'] = (areas_m2[nested[0]] / areas_m2[0]) if areas_m2[0] else None
    detail['nested'] = nested
    if len(loops) == 2:
        return ANNULUS, detail
    return NESTED_EXTRA, detail


def station_detail(shape, z_m, measure=None, nominal_m=NOMINAL_M, n_points=N_POINTS, App=None,
                   spacing_m=None):
    """One station: its topology, and where the wall is thinnest.

    `measure` defaults to the incumbent nearest-point minimum because it returns a value per inner
    sample, which is what makes the thin spot locatable. The *figure* it reports does not converge
    (section 6.4), so read `worst_thin_m` here as a location finder and take the magnitude from the
    selected measure; `angle_rad` and `radius_m` are what this function is for.

    **Pass `spacing_m` rather than `n_points` on a large-`U` part.** With `spacing_m` the sample
    count is derived from this station's own perimeter, so the discretization is the same absolute
    length at every `U`; with `n_points` it is not, and at `U` = 4 a 720-point default
    misclassified a healthy annulus as severed. `spacing_m` costs one extra section to measure the
    perimeter.

    Returns a dict always, never `None`: a station with no wall is a finding, not an absence. Every
    length in it is meters and says so; `angle_rad` is radians, which is the standard's angle unit,
    and `table` is where it becomes degrees for a reader.
    """
    measure = measure or candidates.nearest_point_min
    if spacing_m is not None:
        from . import density                      # local: avoids a cycle, density imports nothing
        perimeter_m = density.section_perimeter(shape, z_m, App=App)
        if perimeter_m is not None:
            n_points = density.counts_for_spacing(perimeter_m, spacing_m)
    loops = sections.station_loops(shape, z_m, n_points, App=App)
    state, detail = ring_state(loops)
    row = {'z_m': float(z_m), 'state': state, 'loops': detail['loops'],
           'area_ratio': detail['area_ratio'], 'worst_thin_m': None, 'thickness_m': None,
           'x_m': None, 'y_m': None, 'angle_rad': None, 'radius_m': None, 'median_m': None}
    if state != ANNULUS:
        return row
    outer, inner = loops[0], loops[detail['nested'][0]]
    points, dists = measure(outer, inner)
    k = int(np.argmin(dists))
    x_m, y_m = float(points[k][0]), float(points[k][1])
    row.update(thickness_m=float(dists[k]),
               worst_thin_m=max(0.0, nominal_m - float(dists[k])),
               x_m=x_m, y_m=y_m, angle_rad=float(np.arctan2(y_m, x_m)),
               radius_m=float(np.hypot(x_m, y_m)), median_m=float(np.median(dists)))
    return row


def profile(shape, zs_m, measure=None, nominal_m=NOMINAL_M, n_points=N_POINTS, App=None,
            on_station=None, spacing_m=None):
    """`station_detail` over many stations. `on_station` is called with each row as it is produced."""
    out = []
    for z_m in zs_m:
        row = station_detail(shape, z_m, measure, nominal_m, n_points, App=App,
                             spacing_m=spacing_m)
        out.append(row)
        if on_station is not None:
            on_station(row)
    return out


def dense_grid(shape, stations=None, inset_m=DENSE_INSET_M, App=None, spacing_m=None,
               extent_m=None):
    """Evenly spaced `z_m` across the saved wall, inset from each end.

    Separate from `corpus.station_grid` -- which takes the acceptance grid's own count -- because
    this is for a *scan*, where the point is to sample between the gate's 12 stations rather than at
    them.

    **Give `spacing_m`, not `stations`.** The axial extent scales with `U` while a defect's extent
    does not, so a fixed station count buys an axial spacing proportional to `U` -- the same error
    that made this subsystem's first corpus figures six times too large circumferentially
    (section 6.6). `stations` is kept for the existing callers and for the case where a fixed count
    is what is wanted.

    **The extent comes from sectioning, not from `Shape.BoundBox`.** A box on these solids is an
    outer bound and nothing more: measured 2026-10-10, a `nose_cowl_shell` wall at `U` = 4 has a box
    spanning `z` -400 to -12 where the part spans -200 to -24, twice its length (section 6.7). A
    dense scan placed across that box would spend half its stations on empty space and report them
    as `no_wall` -- which in a scan looking for a broken ring is a false positive, in the one
    function whose whole purpose is to find one. `App` is needed for the sectioning; without it this
    falls back to the box, so a caller that cares which was used asks
    `corpus.sectioning_extent` itself rather than reading it back out of here.

    **Pass `extent_m` if you already have it.** Finding it is not free: `sectioning_extent`
    bisects each end to 1e-6 m, which is about forty sections on a wall whose box spans 400 mm, and
    a section costs seconds on these face counts. A caller that sections for the extent itself --
    to report it, or to decide a spacing from it -- and then calls this would pay for the same
    forty twice. Given `extent_m`, no sectioning happens here at all and `App` is unused.

    **The station count is `round`, not `int`, and that is a unit-invariance fix** (IP-FC-163).
    This line used to read `int((hi - lo) / spacing)`, which is the `_steps` defect `unit_regime
    --counts` sweeps for: a span of exactly `n` spacings is `n` in millimeters and `n` minus an
    ulp in meters, so truncating it drops a station whenever the division comes out just above a
    whole number -- the common case, since a spacing is usually chosen to divide the span.
    Rounding puts the boundary at the half-integers, where a ratio of two real lengths lands only
    by coincidence.
    """
    lo_hi_m = tuple(extent_m) if extent_m is not None else None
    if lo_hi_m is None and App is not None:
        from . import corpus                     # local: corpus imports only sections, no cycle
        lo_hi_m = corpus.sectioning_extent(shape, App=App)
    if lo_hi_m is None:
        lo_hi_m = kern.z_extent_m(shape)
    lo_m, hi_m = lo_hi_m[0] + inset_m, lo_hi_m[1] - inset_m
    if hi_m <= lo_m:
        return [0.5 * (lo_hi_m[0] + lo_hi_m[1])]
    if spacing_m is not None:
        n = max(int(round((hi_m - lo_m) / float(spacing_m))) + 1, 2)
    else:
        n = int(stations) if stations else 2
    if n < 2:
        return [0.5 * (lo_m + hi_m)]
    return [lo_m + (hi_m - lo_m) * i / float(n - 1) for i in range(n)]


def state_profile(shape, zs_m, n_points=N_POINTS, App=None, spacing_m=None, on_station=None):
    """The ring's topology at each station and nothing else -- no thickness measured.

    **The cheap half of `profile`, and the one a severed-ring scan needs.** Classifying the ring
    needs the loops; locating a thin spot needs a distance from every inner sample to the outer
    loop, which is the expensive part and is irrelevant to whether the ring is closed. Splitting
    them is what makes a dense axial scan affordable: `cowl.md` OQ-DES-CW26 asks whether any
    unperturbed build reaches the severed state and records that its own evidence is bounded by the
    acceptance grid's 12 stations -- about 25 mm apart on a tail -- so an axially short break could
    fall between them. That item names the closing move as "a denser scan on a saved wall", and
    this is it.

    `spacing_m` is the circumferential one and should be passed: at a fixed `n_points` a healthy
    `U` = 4 annulus was misclassified as severed (see `N_POINTS`), which in this scan is exactly
    the false positive that would matter.

    **One slice a station, not two.** Deriving the count from the perimeter through
    `density.section_perimeter` would slice the shape again at the same `z` for wires already in
    hand; `sections.loops_from_wires` takes the ones this function already sliced.
    """
    from . import density                        # local: avoids a cycle, density imports nothing
    out = []
    for z_m in zs_m:
        wires = sections.closed_wires(shape, z_m, App=App)
        n = n_points
        if spacing_m is not None and wires:
            # `kern.length_m`, not `float(w.Length)`: a wire's own attribute is millimeters, and
            # handing that to a meter spacing is the defect `sever_doses` shipped (IP-FC-163).
            longest_m = max(kern.length_m(w) for w in wires)
            n = density.counts_for_spacing(longest_m, spacing_m)
        loops = sections.loops_from_wires(wires, n)
        state, detail = ring_state(loops)
        row = {'z_m': float(z_m), 'state': state, 'loops': detail['loops'],
               'area_ratio': detail['area_ratio'], 'samples': n}
        out.append(row)
        if on_station is not None:
            on_station(row)
    return out


def _circle_radius(p0, p1, p2):
    """Radius of the circle through three planar points; `inf` when they are collinear.

    SI in, SI out. `d` is twice the triangle's signed area, which is why the collinearity
    threshold is `COLLINEAR_AREA_M2` and scaled by a million rather than a thousand.
    """
    ax, ay = float(p0[0]), float(p0[1])
    bx, by = float(p1[0]), float(p1[1])
    cx, cy = float(p2[0]), float(p2[1])
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < COLLINEAR_AREA_M2:
        return float('inf')
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return float(np.hypot(ax - ux, ay - uy))


def curvature_profile(points, window_m=CURV_WINDOW_M):
    """Local radius of curvature at every sample of a closed polyline, over an arc-length window.

    **A window, not adjacent samples.** Three consecutive points of a finely sampled B-spline are
    nearly collinear to within round-off, so the circle through them is numerically meaningless; the
    same trap made the windowed-normal candidate (C2) oscillate. The window is a fixed arc length,
    so the estimate means the same thing at every sampling density and at every `U`.

    Returns an array of radii in meters, `inf` where the boundary is locally straight. The window
    is a count of samples derived from two lengths, and it is `round`, so it is unit-invariant.
    """
    s = sections.arc_length(points, closed=True)
    total_m = s[-1] + float(np.linalg.norm(points[0, :2] - points[-1, :2]))
    n = len(points)
    if n < 3 or total_m <= 0.0:
        return np.full(n, float('inf'))
    step = max(1, int(round(n * float(window_m) / total_m)))
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        out[i] = _circle_radius(points[(i - step) % n], points[i], points[(i + step) % n])
    return out


def curvature_at_thin_spot(shape, z_m, measure=None, n_points=N_POINTS, App=None,
                           spacing_m=None, window_m=CURV_WINDOW_M, nominal_m=NOMINAL_M):
    """Is the wall thinnest where the section's boundary is most curved?

    Returns a dict with the thin spot's own local radius on both loops, the section's median radius,
    and the thin spot's percentile rank by curvature -- `rank` near 1.0 means the thin spot is among
    the most curved places on the section, which is what a corner-driven defect looks like.

    `None` when the station has no annular section.
    """
    measure = measure or candidates.nearest_point_min
    if spacing_m is not None:
        from . import density
        perimeter_m = density.section_perimeter(shape, z_m, App=App)
        if perimeter_m is not None:
            n_points = density.counts_for_spacing(perimeter_m, spacing_m)
    loops = sections.station_loops(shape, z_m, n_points, App=App)
    state, detail = ring_state(loops)
    if state != ANNULUS:
        return None
    outer, inner = loops[0], loops[detail['nested'][0]]
    pts, dists = measure(outer, inner)
    k = int(np.argmin(dists))
    # The inner sample's own curvature, and the outer boundary's at the nearest place to it.
    r_inner_m = curvature_profile(inner, window_m)
    r_outer_m = curvature_profile(outer, window_m)
    j = int(np.argmin(np.linalg.norm(outer[:, :2] - pts[k][:2], axis=1)))
    finite_in_m = r_inner_m[np.isfinite(r_inner_m)]
    # Rank by curvature (1/radius), so 1.0 is the sharpest place on the loop. A ratio of two
    # curvatures, so the rank is unit-invariant.
    kappa = 1.0 / np.where(np.isfinite(r_inner_m), r_inner_m, np.inf)
    rank = float(np.count_nonzero(kappa <= kappa[k])) / float(len(kappa))
    return {'z_m': float(z_m), 'thin_m': max(0.0, nominal_m - float(dists[k])),
            'thickness_m': float(dists[k]),
            'x_m': float(pts[k][0]), 'y_m': float(pts[k][1]),
            'angle_rad': float(np.arctan2(pts[k][1], pts[k][0])),
            'radius_from_axis_m': float(np.hypot(pts[k][0], pts[k][1])),
            'inner_curv_radius_m': float(r_inner_m[k]),
            'outer_curv_radius_m': float(r_outer_m[j]),
            'inner_median_curv_radius_m': (float(np.median(finite_in_m))
                                           if finite_in_m.size else None),
            'curvature_rank': rank, 'samples': int(n_points)}


#: Axial offsets `nearby_states` re-probes a `no_wall` station at. Spans the 0.05 mm at which
#: section 6.1's recorded case already returned a normal section, with a tighter and a looser pair
#: either side so an artifact and a real hole are told apart by how far it extends. Converted from
#: (-0.20, -0.05, -0.01, 0.01, 0.05, 0.20) mm by IP-FC-163; the same six places.
NEARBY_OFFSETS_M = (-2.0e-4, -5.0e-5, -1.0e-5, 1.0e-5, 5.0e-5, 2.0e-4)


def nearby_states(shape, z_m, offsets_m=NEARBY_OFFSETS_M, App=None, spacing_m=None,
                  n_points=N_POINTS):
    """Re-probe just either side of `z_m`. **The only way a `no_wall` reading means anything.**

    `Shape.slice()` can return nothing at one exact plane on a perfectly healthy wall: section 6.1
    records a wall returning no section at `z` = -141.0000 and a normal one at +-0.05 mm. A scan
    that reports that as `no_wall` has found an artifact of the plane it chose, not a hole, and
    neither `ring_state` nor `agrees_with_kernel` can tell the two apart -- with zero wires the
    nesting test and `Part.makeFace` both say "not an annulus" and agree, trivially and
    uninformatively.

    So a `no_wall` is only a finding if the wall is still absent a little either side. Returns the
    rows for `z_m` plus each offset, nearest first, which `is_slice_artifact` reads.
    """
    zs_m = [float(z_m)] + [float(z_m) + float(d) for d in offsets_m]
    return state_profile(shape, zs_m, n_points=n_points, App=App, spacing_m=spacing_m)


def is_slice_artifact(rows):
    """Did the wall come back at a neighboring plane? Then the `no_wall` was the slicer's.

    Takes `nearby_states`' rows. `True` means at least one neighbor is a healthy annulus, so the
    gap is an artifact of the exact plane; `False` means the wall is absent either side too, which
    is the reading that would matter.
    """
    if not rows:
        return False
    return any(r['state'] == ANNULUS for r in rows[1:])


def states(rows):
    """How many stations of each classification, as a plain dict."""
    out = {}
    for r in rows:
        out[r['state']] = out.get(r['state'], 0) + 1
    return out


def severed(rows):
    """Only the stations whose ring is not a healthy annulus and not simply absent."""
    return [r for r in rows if r['state'] in (SEVERED_ONE, SEVERED_MANY, NESTED_EXTRA)]


def worst(rows):
    """The station with the greatest thinness among those that have a reading, or `None`."""
    scored = [r for r in rows if r['worst_thin_m'] is not None]
    return max(scored, key=lambda r: r['worst_thin_m']) if scored else None


def scan_verdict(walls):
    """Fold per-wall scan records into one answer for the whole corpus.

    Takes the `walls` list a `ring_scan` run writes -- one dict a wall, each with `label`,
    `stations`, `states`, `severed`, `no_wall`, `no_wall_verdicts`, `kernel_disagreements` and
    `axial_mm`, all in the millimeters the file carries.
    Scanning the twelve distinct walls is hours and runs a process a wall, so the corpus answer is
    assembled from those records rather than held in one process's memory.

    **A `no_wall` resolved as a slice artifact is not a finding and is not counted as one.**
    `Shape.slice()` can return nothing at one exact plane on a healthy wall (section 6.1), so
    counting it would report the plane the scan happened to choose as a defect in the part. It is
    reported separately, as `artifacts`, because how often the slicer does this is worth knowing.

    `clean` is `True` only when no wall has a severed ring, no `no_wall` survived its re-probe, and
    the kernel disagreed nowhere -- the last because the nesting test is a proxy, and a proxy that
    disagrees with the authority has not been shown to be measuring the right thing here.

    **The kernel is asked only where the scan flagged something**, so an empty `kernel_disagreements`
    on a clean wall means it was never consulted, not that it concurred. That is sound rather than
    merely cheap: whether the ring is severed follows from the kernel's own wire count, which a
    break makes either one loop or two non-nested ones, and the discretization enters only the
    nesting decision between loops -- where under-sampling's failure direction is a false positive
    (`N_POINTS`) and not a missed break.

    **`ring_scan`'s JSON is a millimeter file format and this is one side of its boundary**
    (IP-FC-163). A corpus scan is hours a run and those records are the whole of OQ-DES-CW26's
    evidence that no unperturbed wall severs, so the format is left exactly as it is -- its keys
    already say `axial_mm` and `around_mm` -- and the conversion happens here, at ingest. What
    comes back out is SI with `_m` keys, so a verdict and a record can never be confused. The same
    decision, for the same reason, as `sweep.JSONL_LENGTH_KEYS`.
    """
    merged, severed_at, gaps_at, disagree_at = {}, [], [], []
    artifacts = 0
    for w in walls:
        for state, n in (w.get('states') or {}).items():
            merged[state] = merged.get(state, 0) + n
        label = w.get('label', '?')
        severed_at += [(label, kern.m(float(z_mm))) for z_mm in (w.get('severed') or [])]
        gaps_at += [(label, kern.m(float(z_mm))) for z_mm in (w.get('real_gaps') or [])]
        artifacts += sum(1 for v in (w.get('no_wall_verdicts') or []) if v.get('slice_artifact'))
        disagree_at += [(label, d) for d in (w.get('kernel_disagreements') or [])]
    return {'walls': len(walls), 'stations': sum(int(w.get('stations') or 0) for w in walls),
            'states': merged, 'severed_m': severed_at, 'real_gaps_m': gaps_at,
            'artifacts': artifacts, 'kernel_disagreements': disagree_at,
            'flagged': sorted({label for label, _ in severed_at + gaps_at}),
            'clean': not (severed_at or gaps_at or disagree_at)}
# `severed_m` and `real_gaps_m` are `(label, z_m)` pairs: the `z` is SI like every other station
# position in this package, and the key says so (IP-FC-163).


def scan_table(walls):
    """The corpus scan as text, one row a wall, with what each station cost.

    The cost column is not decoration: it is the figure that makes the next run schedulable, and
    `cowl.md` OQ-DES-CW26's own estimate for this scan ("costs a file read") was wrong by orders of
    magnitude for want of it.

    Reads the millimeter record `ring_scan` writes and prints it, so nothing converts here; see
    `scan_verdict` on why that format is frozen.
    """
    head = '%-26s %8s %9s %8s %8s %8s %9s %9s' % (
        'wall', 'stations', 'axial/mm', 'annulus', 'severed', 'no_wall', 'artifact', 's/station')
    out = [head, '-' * len(head)]
    for w in sorted(walls, key=lambda w: w.get('label', '')):
        meta = w.get('meta') or {}
        per = meta.get('seconds_per_station')
        n_art = sum(1 for v in (w.get('no_wall_verdicts') or []) if v.get('slice_artifact'))
        out.append('%-26s %8d %9.2f %8d %8d %8d %9d %9s'
                   % (w.get('label', '?'), int(w.get('stations') or 0),
                      float(w.get('axial_mm') or 0.0),
                      int((w.get('states') or {}).get(ANNULUS, 0)),
                      len(w.get('severed') or []), len(w.get('no_wall') or []), n_art,
                      '-' if per is None else '%.1f' % per))
    v = scan_verdict(walls)
    out.append('-' * len(head))
    out.append('%-26s %8d %9s %8d %8d %8d %9d'
               % ('%d wall(s)' % v['walls'], v['stations'], '', v['states'].get(ANNULUS, 0),
                  len(v['severed_m']), v['states'].get(NO_WALL, 0), v['artifacts']))
    return '\n'.join(out)


#: Circumferential spacing that `cowl_interior`'s second pass measures the finished wall at --
#: its `CHECK_ARC_M`, mirrored here the way `density`'s gate constants mirror the gate's. A build's
#: log prints the realized figure ("480 check points (0.199 mm apart)"), which is what this is
#: checked against rather than against the constant. Was 0.20 mm.
PASS2_ARC_M = 2.0e-4


def criterion_split(shape, zs_m, nominal_m=NOMINAL_M, App=None, pass2_arc_m=PASS2_ARC_M,
                    gate_arc_m=GATE_ARC_M, on_station=None):
    """Why `cavity`'s own convergence criterion and the gate's reading are different numbers.

    **These are not two samplings of one quantity; they are two quantities.** `cavity`'s second
    pass converges `_finished_wall_gap`, a plain minimum distance over the whole discretized inner
    loop, at `CHECK_ARC` = 0.20 mm. The figure the corpus publishes is `corner_excluded_min` at
    0.125 mm. The first has no corner exclusion, so a concave corner of the wall -- where the inner
    loop turns inside the outer loop's own radius and the nearest-point distance stops being a wall
    thickness -- is scored as thinness by one and dropped by the other. Which of the two *should*
    read the wall is `cowl.md` OQ-DES-CW29, and that question is open.

    This matters beyond bookkeeping, because `TAU` is compared against the first and `WALL_TOL`
    against the second. Measured on `tail_shell` at `U` = 0.5 (IP-WTM-28): pass 2 read 0.03794 mm
    where the gate's measure read 0.01346 mm on the same wall, 2.8 times as much. Setting
    `TAU` = `WALL_TOL` therefore does not ask the construction for a 0.01 mm wall; it asks pass 2's
    measure to reach 0.01 mm, which on that wall is a different and much harder thing.

    Returns a row a station with the three readings and the difference split in two:

    * `thin_pass2_m`     -- the incumbent measure at `pass2_arc_m`: what the criterion sees.
    * `thin_incumbent_m` -- the incumbent measure at `gate_arc_m`.
    * `thin_selected_m`  -- the corner-excluded measure at `gate_arc_m`: what the corpus publishes.
    * `sampling_term_m`  -- `thin_pass2_m - thin_incumbent_m`, one measure at two spacings.
    * `corner_term_m`    -- `thin_incumbent_m - thin_selected_m`, one spacing and two measures.

    **The two fine readings come from one section at one sampling**, which is what makes
    `corner_term_m` non-negative by construction rather than by tolerance: `corner_excluded_min`
    minimizes over a subset of the distances the incumbent minimizes over, so its distance is never
    smaller and its thinness never larger (IP-WTM-10). A negative `corner_term_m` is a defect, not
    a rounding artifact, and is reported in the row as `subset_violated` rather than being clamped.

    `sampling_term_m` has no such guarantee and is signed on purpose: a coarser sampling can miss a
    thin spot (reading thinner than truth is impossible, so the term goes positive) and can also
    land on a different point of the same corner (either way). Its *size* is the useful output,
    since it is the part of the discrepancy that is an instrument difference rather than a
    disagreement about what a wall is.

    `on_station` is called with each row as it is produced, the same convention `profile` follows.
    **Pass it on a large-`U` tail.** Three sections a station on a 2 400-face solid is tens of
    seconds, so a twelve-station wall is minutes and a corpus run is an hour or more with nothing
    printed in between; a stall then cannot be told from slow progress.
    """
    from . import density                           # local: avoids a cycle, density imports nothing
    out = []

    def _emit(row):
        out.append(row)
        if on_station is not None:
            on_station(row)
        return row

    for z_m in zs_m:
        perimeter_m = density.section_perimeter(shape, z_m, App=App)
        row = {'z_m': float(z_m), 'perimeter_m': perimeter_m, 'state': None,
               'thin_pass2_m': None, 'thin_incumbent_m': None, 'thin_selected_m': None,
               'sampling_term_m': None, 'corner_term_m': None, 'subset_violated': False,
               'n_pass2': None, 'n_gate': None}
        if perimeter_m is None:
            _emit(row)
            continue
        n_pass2 = density.counts_for_spacing(perimeter_m, pass2_arc_m)
        n_gate = density.counts_for_spacing(perimeter_m, gate_arc_m)
        row.update(n_pass2=n_pass2, n_gate=n_gate)
        coarse = sections.station_loops(shape, z_m, n_pass2, App=App)
        state_c, detail_c = ring_state(coarse)
        fine = sections.station_loops(shape, z_m, n_gate, App=App)
        state, detail = ring_state(fine)
        row['state'] = state
        if state != ANNULUS or state_c != ANNULUS:
            _emit(row)
            continue
        o_c, i_c = coarse[0], coarse[detail_c['nested'][0]]
        _p, d_pass2 = candidates.nearest_point_min(o_c, i_c)
        outer, inner = fine[0], fine[detail['nested'][0]]
        _p, d_inc = candidates.nearest_point_min(outer, inner)
        _p, d_sel = candidates.corner_excluded_min(outer, inner)
        thin_pass2_m = max(0.0, nominal_m - float(np.min(d_pass2)))
        thin_inc_m = max(0.0, nominal_m - float(np.min(d_inc)))
        finite = d_sel[d_sel == d_sel]
        thin_sel_m = max(0.0, nominal_m - float(np.min(finite))) if len(finite) else None
        row.update(thin_pass2_m=thin_pass2_m, thin_incumbent_m=thin_inc_m,
                   thin_selected_m=thin_sel_m,
                   sampling_term_m=thin_pass2_m - thin_inc_m)
        if thin_sel_m is not None:
            row.update(corner_term_m=thin_inc_m - thin_sel_m,
                       subset_violated=bool(thin_sel_m > thin_inc_m + SUBSET_TOL_M))
        _emit(row)
    return out


def _rank(values):
    """Ranks, averaging ties, so a rank correlation can be taken without `scipy`."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = 0.5 * (i + j) + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def rank_correlation(xs, ys):
    """Spearman's rho on paired samples, or `None` when there are fewer than three or no spread.

    **A rank correlation rather than a straight-line fit, deliberately.** The claim being tested is
    monotone -- "thin spots sit where the rows are further apart" -- and a rank measure does not
    assume the relationship is linear, which the one measurement here that *is* roughly linear
    (section 6.8.3) only turned out to be after the fact.
    """
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    rx = _rank([p[0] for p in pairs])
    ry = _rank([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 0.0 or syy <= 0.0:
        return None
    return sxy / ((sxx ** 0.5) * (syy ** 0.5))


def row_spacing_split(shape, row_zs_m, zs_m, nominal_m=NOMINAL_M, App=None, arc_m=GATE_ARC_M,
                      margin_m=candidates.MARGIN_M, angle_rad=candidates.CREASE_ANGLE_RAD,
                      on_station=None):
    """IP-WTM-30: does a thin spot's magnitude go with the local **fit row spacing**?

    §6.7.1 refuted the tail's diagonals acting through the *cut* -- ten of twelve thin spots sit
    more than 3`t` from any rib -- and left a refined hypothesis: that they act through the **fit**
    instead, because the fit's seed is front-loaded with every notch edge and `station_floor`
    then drops five or six as too close to a neighbor, so the diagonals *crowd* the rows rather
    than subdividing the domain.

    **That predicts the opposite sign from §6.8.3's nose result**, which is why both are worth
    having: on a nose, error grows with the axial spacing (sparse rows are bad); the crowding
    hypothesis says tight rows are bad. This function reports, per station, the width of the row
    interval the station falls in and the distance to the nearest row, beside the two thinness
    readings, and `rank_correlation` scores the monotone claim either way.

    `row_zs_m` must come from the **same build** as `shape` -- `cavity`'s `station_positions` and
    the wall that build returned. Taking rows from one build and the wall from another assumes a
    reproducibility this subsystem only has away from degenerate configurations, and nothing here
    needs that assumption.
    """
    from . import density                           # local: avoids a cycle, density imports nothing
    rows_sorted_m = sorted(float(z_m) for z_m in row_zs_m)
    out = []
    for z_m in zs_m:
        z_m = float(z_m)
        row = {'z_m': z_m, 'state': None, 'thin_incumbent_m': None, 'thin_excluded_m': None,
               'interval_m': None, 'nearest_row_m': None, 'interval_lo_m': None,
               'interval_hi_m': None}
        lo_m = hi_m = None
        for a_m, b_m in zip(rows_sorted_m, rows_sorted_m[1:]):
            if a_m <= z_m <= b_m:
                lo_m, hi_m = a_m, b_m
                break
        if lo_m is not None:
            row.update(interval_m=hi_m - lo_m, interval_lo_m=lo_m, interval_hi_m=hi_m,
                       nearest_row_m=min(z_m - lo_m, hi_m - z_m))
        perimeter_m = density.section_perimeter(shape, z_m, App=App)
        if perimeter_m is not None:
            n = density.counts_for_spacing(perimeter_m, arc_m)
            loops = sections.station_loops(shape, z_m, n, App=App)
            state, detail = ring_state(loops)
            row['state'] = state
            if state == ANNULUS:
                outer, inner = loops[0], loops[detail['nested'][0]]
                _p, d_inc = candidates.nearest_point_min(outer, inner)
                _k, d_exc = candidates.outer_corner_excluded_min(
                    outer, inner, margin_m=margin_m, angle_rad=angle_rad)
                row['thin_incumbent_m'] = max(0.0, nominal_m - float(np.min(d_inc)))
                if len(d_exc):
                    row['thin_excluded_m'] = max(0.0, nominal_m - float(np.min(d_exc)))
        out.append(row)
        if on_station is not None:
            on_station(row)
    return out


def row_spacing_verdict(rows):
    """Score the monotone claim both ways, and say when there is not enough spread to score it."""
    scored = [r for r in rows if r['interval_m'] is not None]
    inc = rank_correlation([r['interval_m'] for r in scored],
                           [r['thin_incumbent_m'] for r in scored])
    exc = rank_correlation([r['interval_m'] for r in scored],
                           [r['thin_excluded_m'] for r in scored])
    widths_m = [r['interval_m'] for r in scored]
    # A rank correlation and a spread are both ratios, so every figure here but the two extremes
    # is unit-invariant and the conversion could not move the verdict.
    return {
        'stations': len(rows),
        'scored': len(scored),
        'rho_incumbent': inc,
        'rho_excluded': exc,
        'interval_min_m': min(widths_m) if widths_m else None,
        'interval_max_m': max(widths_m) if widths_m else None,
        'spread': ((max(widths_m) / min(widths_m))
                   if widths_m and min(widths_m) > 0 else None),
        'vacuous': len(scored) < 3 or not widths_m or min(widths_m) <= 0
                   or (max(widths_m) / min(widths_m)) < 2.0,
    }


def row_spacing_table(rows):
    """`row_spacing_split` as text, with the rank correlations and a vacuity note."""
    v = row_spacing_verdict(rows)
    head = '%12s %13s %13s %14s %14s %s' % (
        'z/mm', 'interval/mm', 'to nearest/mm', 'incumbent/mm', 'excluded/mm', 'state')
    out = [head, '-' * len(head)]

    def _f(x_m, w=13):
        return ('%*s' % (w, '-')) if x_m is None else ('%*.5f' % (w, kern.mm(x_m)))

    for r in sorted(rows, key=lambda r: -(r['interval_m'] or 0.0)):
        out.append('%12.5f %s %s %s %s %s'
                   % (kern.mm(r['z_m']), _f(r['interval_m']), _f(r['nearest_row_m']),
                      _f(r['thin_incumbent_m'], 14), _f(r['thin_excluded_m'], 14),
                      r['state'] or '-'))
    out.append('-' * len(head))
    out.append('%d of %d station(s) fell inside a row interval; widths %s to %s mm'
               % (v['scored'], v['stations'], _f(v['interval_min_m']).strip(),
                  _f(v['interval_max_m']).strip()))
    out.append("Spearman rho against interval width: incumbent %s, crease-excluded %s"
               % ('-' if v['rho_incumbent'] is None else '%+.3f' % v['rho_incumbent'],
                  '-' if v['rho_excluded'] is None else '%+.3f' % v['rho_excluded']))
    if v['vacuous']:
        out.append('NOT SCORABLE: fewer than three stations, or the interval widths span less '
                   'than a factor of two, so no monotone claim can be tested on this set')
    return '\n'.join(out)


def junction_split(shape, zs_m, nominal_m=NOMINAL_M, App=None, arc_m=GATE_ARC_M,
                   margin_m=candidates.MARGIN_M, angle_rad=candidates.CREASE_ANGLE_RAD,
                   on_station=None):
    """IP-WTM-45: how much of a wall's thinness is read *at a crease of the exterior*?

    Per station, on one section at one sampling: the incumbent plain minimum, and the same
    minimum with samples whose nearest point on the **outer** contour sits within `margin_m` of
    a crease dropped (`candidates.outer_corner_excluded_min`). The question is whether
    `cowl_interior`'s second pass reads 0.0601 mm on a `tail_shell` at `U` = 0.5 because the wall
    is thin where a notch cuts it, or because the in-plane distance is taken across the junction
    where a notch face meets the OML (section 6.8.2).

    **`creases` and `dropped` are returned per station because a null result is otherwise
    unreadable.** The exclusion only fires where the exterior turns sharply enough to be called a
    crease; a junction spread over a gentle angle produces none, and then "the reading did not
    move" means "nothing was excluded" rather than "the crease was not the cause". Measured on a
    synthetic notch, an 8-degree span yields zero creases while a 2-degree span yields three, so
    the distinction is real and has to be reported rather than assumed.

    This reads the **finished wall's own section**, whose outer loop *is* the notched exterior, so
    it needs no build -- unlike the two-exterior comparison in `cavity`, which needs `body` as
    well and so needs one.
    """
    from . import density                           # local: avoids a cycle, density imports nothing
    out = []
    for z_m in zs_m:
        perimeter_m = density.section_perimeter(shape, z_m, App=App)
        row = {'z_m': float(z_m), 'state': None, 'thin_incumbent_m': None,
               'thin_excluded_m': None, 'creases': None, 'dropped': None, 'samples': None,
               'subset_violated': False}
        if perimeter_m is None:
            out.append(row)
            if on_station is not None:
                on_station(row)
            continue
        n = density.counts_for_spacing(perimeter_m, arc_m)
        loops = sections.station_loops(shape, z_m, n, App=App)
        state, detail = ring_state(loops)
        row['state'] = state
        if state == ANNULUS:
            outer, inner = loops[0], loops[detail['nested'][0]]
            _p, d_inc = candidates.nearest_point_min(outer, inner)
            kept, d_exc = candidates.outer_corner_excluded_min(
                outer, inner, margin_m=margin_m, angle_rad=angle_rad)
            thin_inc_m = max(0.0, nominal_m - float(np.min(d_inc)))
            thin_exc_m = (max(0.0, nominal_m - float(np.min(d_exc)))
                          if len(d_exc) else None)
            row.update(thin_incumbent_m=thin_inc_m, thin_excluded_m=thin_exc_m,
                       creases=int(candidates.outer_creases(outer, angle_rad).sum()),
                       samples=int(len(d_inc)), dropped=int(len(d_inc) - len(d_exc)))
            if thin_exc_m is not None:
                row['subset_violated'] = bool(thin_exc_m > thin_inc_m + SUBSET_TOL_M)
        out.append(row)
        if on_station is not None:
            on_station(row)
    return out


def junction_table(rows):
    """`junction_split` as text, worst-incumbent first, with the counts that make it readable."""
    head = '%12s %14s %14s %8s %8s %8s %s' % (
        'z/mm', 'incumbent/mm', 'excluded/mm', 'creases', 'dropped', 'samples', 'state')
    out = [head, '-' * len(head)]

    def _f(v_m, w=14):
        return ('%*s' % (w, '-')) if v_m is None else ('%*.5f' % (w, kern.mm(v_m)))

    for r in sorted(rows, key=lambda r: -(r['thin_incumbent_m'] or 0.0)):
        out.append('%12.5f %s %s %8s %8s %8s %s'
                   % (kern.mm(r['z_m']), _f(r['thin_incumbent_m']), _f(r['thin_excluded_m']),
                      '-' if r['creases'] is None else r['creases'],
                      '-' if r['dropped'] is None else r['dropped'],
                      '-' if r['samples'] is None else r['samples'],
                      (r['state'] or '-')))
    scored = [r for r in rows if r['thin_incumbent_m'] is not None]
    with_exc = [r for r in scored if r['thin_excluded_m'] is not None]
    worst_inc_m = max((r['thin_incumbent_m'] for r in scored), default=None)
    worst_exc_m = max((r['thin_excluded_m'] for r in with_exc), default=None)
    total_creases = sum(r['creases'] or 0 for r in scored)
    total_dropped = sum(r['dropped'] or 0 for r in scored)
    out.append('-' * len(head))
    out.append('%d station(s) scored, %d crease(s) found in total, %d sample(s) dropped'
               % (len(scored), total_creases, total_dropped))
    out.append('worst incumbent %s mm, worst with creases excluded %s mm'
               % ('-' if worst_inc_m is None else '%.5f' % kern.mm(worst_inc_m),
                  '-' if worst_exc_m is None else '%.5f' % kern.mm(worst_exc_m)))
    if total_creases == 0:
        out.append('NOTHING EXCLUDED: no station\'s exterior turns sharply enough to register a '
                   'crease, so this run cannot say whether a crease would explain the reading')
    elif worst_inc_m is not None and worst_exc_m is not None:
        out.append('the exclusion removes %.5f mm of the worst reading (%.1f%%)'
                   % (kern.mm(worst_inc_m - worst_exc_m),
                      (100.0 * (worst_inc_m - worst_exc_m) / worst_inc_m)
                      if worst_inc_m else 0.0))
    if any(r['subset_violated'] for r in rows):
        out.append('SUBSET VIOLATED: the excluded measure cannot exceed the incumbent')
    return '\n'.join(out)


def exterior_verdict(rows, tau_m=TAU_M, wall_tol_m=WALL_TOL_M,
                     coincide_tol_m=COINCIDE_TOL_M):
    """IP-WTM-26: does the residual live in the gap between the two exteriors, or not?

    Takes `cavity`'s `exterior_split` record -- `(z, gap_to_notched, gap_to_oml)` a station, the
    same measure on the same section with only the reference surface swapped -- and answers the
    one question that distinguishes a reference-surface explanation from every other.

    **The converse is what makes this a test rather than a restatement.** `_refine` converges the
    wall out to the un-notched OML and the post-cut loop measures it out to the notched exterior,
    so of course the two can differ. The claim worth testing is *stronger*: that the residual is
    **only** in that difference. If it is, then at a station where the two exteriors coincide --
    no buttress tool has removed exterior material within reach, so the two readings are the same
    number -- there should be no residual either. A station that reads thin against **both**
    exteriors refutes it, because no choice of reference surface explains that station.

    So the rows split three ways:

    * `coincident` -- the two readings agree to `coincide_tol_m`. No notch in reach.
    * `explained` -- thin against the notched exterior, not against the OML. The reference
      surface accounts for it.
    * `unexplained` -- thin against **both**. The reference surface does not account for it, and
      these are the stations a mechanism has to explain.

    **`clean` requires the record to have exercised the question, in two separate ways.** It is
    `True` only when `unexplained` is empty *and* `coincident` is non-empty *and* at least one
    station was thin at all. Both guards were paid for:

    * A record in which the exteriors never coincide has not exercised the converse.
    * A record with **no station over `wall_tol_m`** cannot distinguish the hypotheses either, and
      this one was found the hard way -- the first run of `exterior_split.py`, on
      `nose_cowl_shell` at `U` = 1.0, returned 63 stations whose worst reading was 0.0037 mm
      against a 0.01 mm tolerance, so `explained` and `unexplained` were both empty and an earlier
      version of this function reported **CLEAN**. A compliant specimen cannot test an explanation
      of non-compliance. The nose at `U` = 1 is the wrong build to ask, not evidence.

    Both are the same error as cross-checking two measures of an empty input, which this subsystem
    had already made six times before this became the seventh (section 6.1).
    """
    # `rows` are `cavity`'s own `exterior_split` records, and `cowl_interior` is SI, so the two
    # readings arrive in meters and nothing here converts (IP-FC-163).
    coincident, explained, unexplained, unreadable, thin = [], [], [], [], []
    for row in rows:
        notched_m, oml_m = row[1], row[2]
        if notched_m is None or oml_m is None:
            unreadable.append(row)
            continue
        if abs(notched_m - oml_m) <= coincide_tol_m:
            coincident.append(row)
        if notched_m > wall_tol_m:
            thin.append(row)
            if oml_m > wall_tol_m:
                unexplained.append(row)
            else:
                explained.append(row)
    readable = [r for r in rows if r[1] is not None and r[2] is not None]
    reasons = []
    if not coincident:
        reasons.append('the two exteriors coincide nowhere in this record, so the converse was '
                       'never exercised')
    if not thin:
        reasons.append('no station reads over %.3f mm, so this build is compliant and cannot '
                       'test an explanation of non-compliance' % kern.mm(wall_tol_m))
    return {
        'stations': len(rows),
        'readable': len(readable),
        'unreadable': len(unreadable),
        'coincident': coincident,
        'explained': explained,
        'unexplained': unexplained,
        'thin': thin,
        'worst_notched_m': max((r[1] for r in readable), default=None),
        'worst_oml_m': max((r[2] for r in readable), default=None),
        'worst_unexplained_oml_m': max((r[2] for r in unexplained), default=None),
        'vacuous': bool(reasons),
        'vacuous_because': reasons,
        'clean': bool(not unexplained and coincident and thin),
    }


def exterior_table(rows, tau_m=TAU_M, wall_tol_m=WALL_TOL_M, limit=24):
    """`exterior_split` as text: the two readings a station and which bucket it fell in."""
    v = exterior_verdict(rows, tau_m, wall_tol_m)
    head = '%12s %14s %11s %14s %s' % (
        'z/mm', 'to notched/mm', 'to OML/mm', 'difference/mm', 'bucket')
    out = [head, '-' * len(head)]
    coin = {id(r) for r in v['coincident']}
    unex = {id(r) for r in v['unexplained']}
    expl = {id(r) for r in v['explained']}
    shown = sorted(rows, key=lambda r: -(r[1] or 0.0))[:limit]
    for r in shown:
        z_m, notched_m, oml_m = r[0], r[1], r[2]
        if notched_m is None or oml_m is None:
            out.append('%12.5f %14s %11s %14s %s'
                       % (kern.mm(z_m), '-', '-', '-', 'unreadable'))
            continue
        bucket = ('UNEXPLAINED' if id(r) in unex else
                  'explained' if id(r) in expl else
                  'coincident' if id(r) in coin else 'thin-free')
        out.append('%12.5f %14.5f %11.5f %14.5f %s'
                   % (kern.mm(z_m), kern.mm(notched_m), kern.mm(oml_m),
                      kern.mm(notched_m - oml_m), bucket))
    if len(rows) > limit:
        out.append('... %d more station(s), worst-first' % (len(rows) - limit))
    out.append('-' * len(head))
    out.append('%d station(s): %d over tolerance, %d coincident, %d explained by the exterior, '
               '%d UNEXPLAINED'
               % (v['stations'], len(v['thin']), len(v['coincident']), len(v['explained']),
                  len(v['unexplained'])))
    out.append('worst to notched %s mm, worst to OML %s mm'
               % ('-' if v['worst_notched_m'] is None
                  else '%.5f' % kern.mm(v['worst_notched_m']),
                  '-' if v['worst_oml_m'] is None else '%.5f' % kern.mm(v['worst_oml_m'])))
    if v['vacuous']:
        out.append('NOTHING TESTED: ' + '; and '.join(v['vacuous_because']))
    elif v['clean']:
        out.append('CLEAN: every thin station is thin only against the notched exterior')
    else:
        out.append('%d station(s) read thin against BOTH exteriors -- worst %.5f mm to the OML. '
                   'The reference surface does not explain these.'
                   % (len(v['unexplained']), kern.mm(v['worst_unexplained_oml_m'])))
    return '\n'.join(out)


def criterion_table(rows, nominal_m=NOMINAL_M):
    """`criterion_split` as text, plus the worst of each column -- which is the comparable figure.

    The per-station maxima are taken independently, so the three worst readings need not come from
    one station. That is correct for the question being asked: `TAU` and `WALL_TOL` are each
    compared against the worst reading of their own measure over the whole wall, not against each
    other at one `z`.
    """
    head = '%12s %9s %11s %10s %10s %9s %7s' % (
        'z/mm', 'pass2/mm', 'incumbent/mm', 'selected/mm', 'sampling/mm', 'corner/mm', 'state')
    out = [head, '-' * len(head)]

    def _f(v_m, w=9):
        return ('%*s' % (w, '-')) if v_m is None else ('%*.5f' % (w, kern.mm(v_m)))

    for r in rows:
        out.append('%12.5f %s %s %s %s %s %7s'
                   % (kern.mm(r['z_m']), _f(r['thin_pass2_m']), _f(r['thin_incumbent_m'], 11),
                      _f(r['thin_selected_m'], 10), _f(r['sampling_term_m'], 10),
                      _f(r['corner_term_m']), (r['state'] or '-')[:7]))
    out.append('-' * len(head))
    worst = {k: max([r[k] for r in rows if r.get(k) is not None] or [None],
                    key=lambda v: (v is not None, v))
             for k in ('thin_pass2_m', 'thin_incumbent_m', 'thin_selected_m')}
    out.append('%12s %s %s %s' % ('worst', _f(worst['thin_pass2_m']),
                                  _f(worst['thin_incumbent_m'], 11),
                                  _f(worst['thin_selected_m'], 10)))
    violations_m = [r['z_m'] for r in rows if r.get('subset_violated')]
    if violations_m:
        out.append('SUBSET VIOLATED at %d station(s): %s mm'
                   % (len(violations_m),
                      ', '.join('%.5f' % kern.mm(z_m) for z_m in violations_m)))
    return '\n'.join(out)


def agrees_with_kernel(shape, zs_m, Part, App, n_points=N_POINTS, spacing_m=None):
    """Check this module's nesting test against the kernel's face-making one, station by station.

    Returns the list of disagreements, each `(z_m, state_here, kernel_is_annulus)`. **Run this
    before trusting a dense scan's topology column**: the cheap test is a proxy, and a proxy that
    has not been checked against the authority on the geometry in hand is an assumption.
    """
    out = []
    for z_m in zs_m:
        wires = sections.closed_wires(shape, z_m, App=App)
        try:
            faces = Part.makeFace(wires, 'Part::FaceMakerBullseye') if wires else None
        except Exception:                                            # noqa: BLE001 - kernel refusal
            faces = None
        kernel_annulus = bool(faces is not None and len(faces.Faces) == 1
                              and len(faces.Faces[0].Wires) == 2)
        n = n_points
        if spacing_m is not None:
            from . import density
            perimeter_m = density.section_perimeter(shape, z_m, App=App)
            if perimeter_m is not None:
                n = density.counts_for_spacing(perimeter_m, spacing_m)
        here = ring_state(sections.station_loops(shape, z_m, n, App=App))[0]
        if (here == ANNULUS) != kernel_annulus:
            out.append((float(z_m), here, kernel_annulus))
    return out


def table(rows, tolerance_m=WALL_TOL_M):
    """The scan as text: one row per station, topology beside thickness.

    A display boundary: millimeters and degrees, each named in its own heading. The rows
    themselves are meters and radians.
    """
    head = '%10s %-16s %6s %13s %10s %10s %11s' % (
        'z/mm', 'state', 'loops', 'thickness/mm', 'thin/mm', 'angle/deg', 'radius/mm')
    out = [head, '-' * len(head)]
    for r in rows:
        if r['worst_thin_m'] is None:
            out.append('%10.4f %-16s %6d %13s %10s %10s %11s'
                       % (kern.mm(r['z_m']), r['state'], r['loops'], '-', '-', '-', '-'))
            continue
        mark = '' if r['worst_thin_m'] <= tolerance_m else ' THIN'
        out.append('%10.4f %-16s %6d %13.4f %10.4f %10.2f %11.2f%s'
                   % (kern.mm(r['z_m']), r['state'], r['loops'],
                      kern.mm(r['thickness_m']), kern.mm(r['worst_thin_m']),
                      np.degrees(r['angle_rad']), kern.mm(r['radius_m']), mark))
    return '\n'.join(out)
