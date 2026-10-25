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

from . import candidates, sections

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

#: Circumferential spacing, in mm, that `station_detail` targets when it is given a perimeter to
#: work from. A third of the wall, so a chord's sag is well inside the quantity being measured.
TARGET_SPACING = 0.2


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
    a wall bore at all.
    """
    areas = [abs(sections.signed_area(a)) for a in loops]
    detail = {'loops': len(loops), 'areas': areas, 'area_ratio': None}
    if not loops:
        return NO_WALL, detail
    if len(loops) == 1:
        return SEVERED_ONE, detail
    nested = [i for i in range(1, len(loops)) if _is_nested(loops[0], loops[i])]
    if not nested:
        return SEVERED_MANY, detail
    detail['area_ratio'] = (areas[nested[0]] / areas[0]) if areas[0] else None
    detail['nested'] = nested
    if len(loops) == 2:
        return ANNULUS, detail
    return NESTED_EXTRA, detail


def station_detail(shape, z, measure=None, nominal=0.6, n_points=N_POINTS, App=None,
                   spacing=None):
    """One station: its topology, and where the wall is thinnest.

    `measure` defaults to the incumbent nearest-point minimum because it returns a value per inner
    sample, which is what makes the thin spot locatable. The *figure* it reports does not converge
    (section 6.4), so read `worst_thin` here as a location finder and take the magnitude from the
    selected measure; `angle_deg` and `radius` are what this function is for.

    **Pass `spacing` rather than `n_points` on a large-`U` part.** With `spacing` the sample count is
    derived from this station's own perimeter, so the discretization is the same in millimeters at
    every `U`; with `n_points` it is not, and at `U` = 4 a 720-point default misclassified a healthy
    annulus as severed. `spacing` costs one extra section to measure the perimeter.

    Returns a dict always, never `None`: a station with no wall is a finding, not an absence.
    """
    measure = measure or candidates.nearest_point_min
    if spacing is not None:
        from . import density                      # local: avoids a cycle, density imports nothing
        perimeter = density.section_perimeter(shape, z, App=App)
        if perimeter is not None:
            n_points = density.counts_for_spacing(perimeter, spacing)
    loops = sections.station_loops(shape, z, n_points, App=App)
    state, detail = ring_state(loops)
    row = {'z': float(z), 'state': state, 'loops': detail['loops'],
           'area_ratio': detail['area_ratio'], 'worst_thin': None, 'thickness': None,
           'x': None, 'y': None, 'angle_deg': None, 'radius': None, 'median': None}
    if state != ANNULUS:
        return row
    outer, inner = loops[0], loops[detail['nested'][0]]
    points, dists = measure(outer, inner)
    k = int(np.argmin(dists))
    x, y = float(points[k][0]), float(points[k][1])
    row.update(thickness=float(dists[k]), worst_thin=max(0.0, nominal - float(dists[k])),
               x=x, y=y, angle_deg=float(np.degrees(np.arctan2(y, x))),
               radius=float(np.hypot(x, y)), median=float(np.median(dists)))
    return row


def profile(shape, zs, measure=None, nominal=0.6, n_points=N_POINTS, App=None, on_station=None,
            spacing=None):
    """`station_detail` over many stations. `on_station` is called with each row as it is produced."""
    out = []
    for z in zs:
        row = station_detail(shape, z, measure, nominal, n_points, App=App, spacing=spacing)
        out.append(row)
        if on_station is not None:
            on_station(row)
    return out


def dense_grid(shape, stations=None, inset=1.0, App=None, spacing_mm=None, extent=None):
    """Evenly spaced `z` across the saved wall, inset from each end.

    Separate from `corpus.station_grid` -- which takes the acceptance grid's own count -- because
    this is for a *scan*, where the point is to sample between the gate's 12 stations rather than at
    them.

    **Give `spacing_mm`, not `stations`.** The axial extent scales with `U` while a defect's extent
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

    **Pass `extent` if you already have it.** Finding it is not free: `sectioning_extent` bisects
    each end to 1e-3 mm, which is about forty sections on a wall whose box spans 400 mm, and a
    section costs seconds on these face counts. A caller that sections for the extent itself -- to
    report it, or to decide a spacing from it -- and then calls this would pay for the same forty
    twice. Given `extent`, no sectioning happens here at all and `App` is unused.
    """
    lo_hi = tuple(extent) if extent is not None else None
    if lo_hi is None and App is not None:
        from . import corpus                     # local: corpus imports only sections, no cycle
        lo_hi = corpus.sectioning_extent(shape, App=App)
    if lo_hi is None:
        bb = shape.BoundBox
        lo_hi = (bb.ZMin, bb.ZMax)
    lo, hi = lo_hi[0] + inset, lo_hi[1] - inset
    if hi <= lo:
        return [0.5 * (lo_hi[0] + lo_hi[1])]
    if spacing_mm is not None:
        n = max(int((hi - lo) / float(spacing_mm)) + 1, 2)
    else:
        n = int(stations) if stations else 2
    if n < 2:
        return [0.5 * (lo + hi)]
    return [lo + (hi - lo) * i / float(n - 1) for i in range(n)]


def state_profile(shape, zs, n_points=N_POINTS, App=None, spacing=None, on_station=None):
    """The ring's topology at each station and nothing else -- no thickness measured.

    **The cheap half of `profile`, and the one a severed-ring scan needs.** Classifying the ring
    needs the loops; locating a thin spot needs a distance from every inner sample to the outer
    loop, which is the expensive part and is irrelevant to whether the ring is closed. Splitting
    them is what makes a dense axial scan affordable: `cowl.md` OQ-DES-CW26 asks whether any
    unperturbed build reaches the severed state and records that its own evidence is bounded by the
    acceptance grid's 12 stations -- about 25 mm apart on a tail -- so an axially short break could
    fall between them. That item names the closing move as "a denser scan on a saved wall", and
    this is it.

    `spacing` is the circumferential one and should be passed: at a fixed `n_points` a healthy
    `U` = 4 annulus was misclassified as severed (see `N_POINTS`), which in this scan is exactly
    the false positive that would matter.

    **One slice a station, not two.** Deriving the count from the perimeter through
    `density.section_perimeter` would slice the shape again at the same `z` for wires already in
    hand; `sections.loops_from_wires` takes the ones this function already sliced.
    """
    from . import density                        # local: avoids a cycle, density imports nothing
    out = []
    for z in zs:
        wires = sections.closed_wires(shape, z, App=App)
        n = n_points
        if spacing is not None and wires:
            longest = max(float(w.Length) for w in wires)
            n = density.counts_for_spacing(longest, spacing)
        loops = sections.loops_from_wires(wires, n)
        state, detail = ring_state(loops)
        row = {'z': float(z), 'state': state, 'loops': detail['loops'],
               'area_ratio': detail['area_ratio'], 'samples': n}
        out.append(row)
        if on_station is not None:
            on_station(row)
    return out


def _circle_radius(p0, p1, p2):
    """Radius of the circle through three planar points; `inf` when they are collinear."""
    ax, ay = float(p0[0]), float(p0[1])
    bx, by = float(p1[0]), float(p1[1])
    cx, cy = float(p2[0]), float(p2[1])
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1.0e-12:
        return float('inf')
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return float(np.hypot(ax - ux, ay - uy))


def curvature_profile(points, window_mm=2.0):
    """Local radius of curvature at every sample of a closed polyline, over an arc-length window.

    **A window, not adjacent samples.** Three consecutive points of a finely sampled B-spline are
    nearly collinear to within round-off, so the circle through them is numerically meaningless; the
    same trap made the windowed-normal candidate (C2) oscillate. The window is a fixed arc length,
    so the estimate means the same thing at every sampling density and at every `U`.

    Returns an array of radii, `inf` where the boundary is locally straight.
    """
    s = sections.arc_length(points, closed=True)
    total = s[-1] + float(np.linalg.norm(points[0, :2] - points[-1, :2]))
    n = len(points)
    if n < 3 or total <= 0.0:
        return np.full(n, float('inf'))
    step = max(1, int(round(n * float(window_mm) / total)))
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        out[i] = _circle_radius(points[(i - step) % n], points[i], points[(i + step) % n])
    return out


def curvature_at_thin_spot(shape, z, measure=None, n_points=N_POINTS, App=None, spacing=None,
                           window_mm=2.0, nominal=0.6):
    """Is the wall thinnest where the section's boundary is most curved?

    Returns a dict with the thin spot's own local radius on both loops, the section's median radius,
    and the thin spot's percentile rank by curvature -- `rank` near 1.0 means the thin spot is among
    the most curved places on the section, which is what a corner-driven defect looks like.

    `None` when the station has no annular section.
    """
    measure = measure or candidates.nearest_point_min
    if spacing is not None:
        from . import density
        perimeter = density.section_perimeter(shape, z, App=App)
        if perimeter is not None:
            n_points = density.counts_for_spacing(perimeter, spacing)
    loops = sections.station_loops(shape, z, n_points, App=App)
    state, detail = ring_state(loops)
    if state != ANNULUS:
        return None
    outer, inner = loops[0], loops[detail['nested'][0]]
    pts, dists = measure(outer, inner)
    k = int(np.argmin(dists))
    # The inner sample's own curvature, and the outer boundary's at the nearest place to it.
    r_inner = curvature_profile(inner, window_mm)
    r_outer = curvature_profile(outer, window_mm)
    j = int(np.argmin(np.linalg.norm(outer[:, :2] - pts[k][:2], axis=1)))
    finite_in = r_inner[np.isfinite(r_inner)]
    # Rank by curvature (1/radius), so 1.0 is the sharpest place on the loop.
    kappa = 1.0 / np.where(np.isfinite(r_inner), r_inner, np.inf)
    rank = float(np.count_nonzero(kappa <= kappa[k])) / float(len(kappa))
    return {'z': float(z), 'thin': max(0.0, nominal - float(dists[k])),
            'thickness': float(dists[k]),
            'x': float(pts[k][0]), 'y': float(pts[k][1]),
            'angle_deg': float(np.degrees(np.arctan2(pts[k][1], pts[k][0]))),
            'radius_from_axis': float(np.hypot(pts[k][0], pts[k][1])),
            'inner_curv_radius': float(r_inner[k]),
            'outer_curv_radius': float(r_outer[j]),
            'inner_median_curv_radius': float(np.median(finite_in)) if finite_in.size else None,
            'curvature_rank': rank, 'samples': int(n_points)}


#: Axial offsets, in mm, `nearby_states` re-probes a `no_wall` station at. Spans the 0.05 mm at
#: which section 6.1's recorded case already returned a normal section, with a tighter and a looser
#: pair either side so an artifact and a real hole are told apart by how far it extends.
NEARBY_OFFSETS = (-0.20, -0.05, -0.01, 0.01, 0.05, 0.20)


def nearby_states(shape, z, offsets=NEARBY_OFFSETS, App=None, spacing=None, n_points=N_POINTS):
    """Re-probe just either side of `z`. **The only way a `no_wall` reading means anything.**

    `Shape.slice()` can return nothing at one exact plane on a perfectly healthy wall: section 6.1
    records a wall returning no section at `z` = -141.0000 and a normal one at +-0.05 mm. A scan
    that reports that as `no_wall` has found an artifact of the plane it chose, not a hole, and
    neither `ring_state` nor `agrees_with_kernel` can tell the two apart -- with zero wires the
    nesting test and `Part.makeFace` both say "not an annulus" and agree, trivially and
    uninformatively.

    So a `no_wall` is only a finding if the wall is still absent a little either side. Returns the
    rows for `z` plus each offset, nearest first, which `is_slice_artifact` reads.
    """
    zs = [float(z)] + [float(z) + float(d) for d in offsets]
    return state_profile(shape, zs, n_points=n_points, App=App, spacing=spacing)


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
    scored = [r for r in rows if r['worst_thin'] is not None]
    return max(scored, key=lambda r: r['worst_thin']) if scored else None


def scan_verdict(walls):
    """Fold per-wall scan records into one answer for the whole corpus.

    Takes the `walls` list a `ring_scan` run writes -- one dict a wall, each with `label`,
    `stations`, `states`, `severed`, `no_wall`, `no_wall_verdicts` and `kernel_disagreements`.
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
    """
    merged, severed_at, gaps_at, disagree_at = {}, [], [], []
    artifacts = 0
    for w in walls:
        for state, n in (w.get('states') or {}).items():
            merged[state] = merged.get(state, 0) + n
        label = w.get('label', '?')
        severed_at += [(label, float(z)) for z in (w.get('severed') or [])]
        gaps_at += [(label, float(z)) for z in (w.get('real_gaps') or [])]
        artifacts += sum(1 for v in (w.get('no_wall_verdicts') or []) if v.get('slice_artifact'))
        disagree_at += [(label, d) for d in (w.get('kernel_disagreements') or [])]
    return {'walls': len(walls), 'stations': sum(int(w.get('stations') or 0) for w in walls),
            'states': merged, 'severed': severed_at, 'real_gaps': gaps_at,
            'artifacts': artifacts, 'kernel_disagreements': disagree_at,
            'flagged': sorted({label for label, _ in severed_at + gaps_at}),
            'clean': not (severed_at or gaps_at or disagree_at)}


def scan_table(walls):
    """The corpus scan as text, one row a wall, with what each station cost.

    The cost column is not decoration: it is the figure that makes the next run schedulable, and
    `cowl.md` OQ-DES-CW26's own estimate for this scan ("costs a file read") was wrong by orders of
    magnitude for want of it.
    """
    head = '%-26s %8s %7s %8s %8s %8s %9s %9s' % (
        'wall', 'stations', 'axial', 'annulus', 'severed', 'no_wall', 'artifact', 's/station')
    out = [head, '-' * len(head)]
    for w in sorted(walls, key=lambda w: w.get('label', '')):
        meta = w.get('meta') or {}
        per = meta.get('seconds_per_station')
        n_art = sum(1 for v in (w.get('no_wall_verdicts') or []) if v.get('slice_artifact'))
        out.append('%-26s %8d %7.2f %8d %8d %8d %9d %9s'
                   % (w.get('label', '?'), int(w.get('stations') or 0),
                      float(w.get('axial_mm') or 0.0),
                      int((w.get('states') or {}).get(ANNULUS, 0)),
                      len(w.get('severed') or []), len(w.get('no_wall') or []), n_art,
                      '-' if per is None else '%.1f' % per))
    v = scan_verdict(walls)
    out.append('-' * len(head))
    out.append('%-26s %8d %7s %8d %8d %8d %9d'
               % ('%d wall(s)' % v['walls'], v['stations'], '', v['states'].get(ANNULUS, 0),
                  len(v['severed']), v['states'].get(NO_WALL, 0), v['artifacts']))
    return '\n'.join(out)


#: Circumferential spacing, in mm, that `cowl_interior`'s second pass measures the finished wall at
#: -- its `CHECK_ARC`, mirrored here the way `density`'s gate constants mirror the gate's. A build's
#: log prints the realized figure ("480 check points (0.199 mm apart)"), which is what this is
#: checked against rather than against the constant.
PASS2_ARC = 0.20


def criterion_split(shape, zs, nominal=0.6, App=None, pass2_arc=PASS2_ARC, gate_arc=0.125,
                    on_station=None):
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

    * `thin_pass2`     -- the incumbent measure at `pass2_arc`: what the criterion sees.
    * `thin_incumbent` -- the incumbent measure at `gate_arc`.
    * `thin_selected`  -- the corner-excluded measure at `gate_arc`: what the corpus publishes.
    * `sampling_term`  -- `thin_pass2 - thin_incumbent`, one measure at two spacings.
    * `corner_term`    -- `thin_incumbent - thin_selected`, one spacing and two measures.

    **The two fine readings come from one section at one sampling**, which is what makes
    `corner_term` non-negative by construction rather than by tolerance: `corner_excluded_min`
    minimizes over a subset of the distances the incumbent minimizes over, so its distance is never
    smaller and its thinness never larger (IP-WTM-10). A negative `corner_term` is a defect, not a
    rounding artifact, and is reported in the row as `subset_violated` rather than being clamped.

    `sampling_term` has no such guarantee and is signed on purpose: a coarser sampling can miss a
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

    for z in zs:
        perimeter = density.section_perimeter(shape, z, App=App)
        row = {'z': float(z), 'perimeter_mm': perimeter, 'state': None,
               'thin_pass2': None, 'thin_incumbent': None, 'thin_selected': None,
               'sampling_term': None, 'corner_term': None, 'subset_violated': False,
               'n_pass2': None, 'n_gate': None}
        if perimeter is None:
            _emit(row)
            continue
        n_pass2 = density.counts_for_spacing(perimeter, pass2_arc)
        n_gate = density.counts_for_spacing(perimeter, gate_arc)
        row.update(n_pass2=n_pass2, n_gate=n_gate)
        coarse = sections.station_loops(shape, z, n_pass2, App=App)
        state_c, detail_c = ring_state(coarse)
        fine = sections.station_loops(shape, z, n_gate, App=App)
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
        thin_pass2 = max(0.0, nominal - float(np.min(d_pass2)))
        thin_inc = max(0.0, nominal - float(np.min(d_inc)))
        finite = d_sel[d_sel == d_sel]
        thin_sel = max(0.0, nominal - float(np.min(finite))) if len(finite) else None
        row.update(thin_pass2=thin_pass2, thin_incumbent=thin_inc, thin_selected=thin_sel,
                   sampling_term=thin_pass2 - thin_inc)
        if thin_sel is not None:
            row.update(corner_term=thin_inc - thin_sel,
                       subset_violated=bool(thin_sel > thin_inc + 1e-12))
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


def row_spacing_split(shape, row_zs, zs, nominal=0.6, App=None, arc=0.125, margin_mm=0.30,
                      angle_deg=30.0, on_station=None):
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

    `row_zs` must come from the **same build** as `shape` -- `cavity`'s `station_positions` and the
    wall that build returned. Taking rows from one build and the wall from another assumes a
    reproducibility this subsystem only has away from degenerate configurations, and nothing here
    needs that assumption.
    """
    from . import density                           # local: avoids a cycle, density imports nothing
    rows_sorted = sorted(float(z) for z in row_zs)
    out = []
    for z in zs:
        z = float(z)
        row = {'z': z, 'state': None, 'thin_incumbent': None, 'thin_excluded': None,
               'interval_mm': None, 'nearest_row_mm': None, 'interval_lo': None,
               'interval_hi': None}
        lo = hi = None
        for a, b in zip(rows_sorted, rows_sorted[1:]):
            if a <= z <= b:
                lo, hi = a, b
                break
        if lo is not None:
            row.update(interval_mm=hi - lo, interval_lo=lo, interval_hi=hi,
                       nearest_row_mm=min(z - lo, hi - z))
        perimeter = density.section_perimeter(shape, z, App=App)
        if perimeter is not None:
            n = density.counts_for_spacing(perimeter, arc)
            loops = sections.station_loops(shape, z, n, App=App)
            state, detail = ring_state(loops)
            row['state'] = state
            if state == ANNULUS:
                outer, inner = loops[0], loops[detail['nested'][0]]
                _p, d_inc = candidates.nearest_point_min(outer, inner)
                _k, d_exc = candidates.outer_corner_excluded_min(
                    outer, inner, margin_mm=margin_mm, angle_deg=angle_deg)
                row['thin_incumbent'] = max(0.0, nominal - float(np.min(d_inc)))
                if len(d_exc):
                    row['thin_excluded'] = max(0.0, nominal - float(np.min(d_exc)))
        out.append(row)
        if on_station is not None:
            on_station(row)
    return out


def row_spacing_verdict(rows):
    """Score the monotone claim both ways, and say when there is not enough spread to score it."""
    scored = [r for r in rows if r['interval_mm'] is not None]
    inc = rank_correlation([r['interval_mm'] for r in scored],
                           [r['thin_incumbent'] for r in scored])
    exc = rank_correlation([r['interval_mm'] for r in scored],
                           [r['thin_excluded'] for r in scored])
    widths = [r['interval_mm'] for r in scored]
    return {
        'stations': len(rows),
        'scored': len(scored),
        'rho_incumbent': inc,
        'rho_excluded': exc,
        'interval_min': min(widths) if widths else None,
        'interval_max': max(widths) if widths else None,
        'spread': (max(widths) / min(widths)) if widths and min(widths) > 0 else None,
        'vacuous': len(scored) < 3 or not widths or min(widths) <= 0
                   or (max(widths) / min(widths)) < 2.0,
    }


def row_spacing_table(rows):
    """`row_spacing_split` as text, with the rank correlations and a vacuity note."""
    v = row_spacing_verdict(rows)
    head = '%12s %10s %10s %11s %11s %s' % (
        'z', 'interval', 'to nearest', 'incumbent', 'excluded', 'state')
    out = [head, '-' * len(head)]

    def _f(x, w=10):
        return ('%*s' % (w, '-')) if x is None else ('%*.5f' % (w, x))

    for r in sorted(rows, key=lambda r: -(r['interval_mm'] or 0.0)):
        out.append('%12.5f %s %s %s %s %s'
                   % (r['z'], _f(r['interval_mm']), _f(r['nearest_row_mm']),
                      _f(r['thin_incumbent'], 11), _f(r['thin_excluded'], 11),
                      r['state'] or '-'))
    out.append('-' * len(head))
    out.append('%d of %d station(s) fell inside a row interval; widths %s to %s mm'
               % (v['scored'], v['stations'], _f(v['interval_min']).strip(),
                  _f(v['interval_max']).strip()))
    out.append("Spearman rho against interval width: incumbent %s, crease-excluded %s"
               % ('-' if v['rho_incumbent'] is None else '%+.3f' % v['rho_incumbent'],
                  '-' if v['rho_excluded'] is None else '%+.3f' % v['rho_excluded']))
    if v['vacuous']:
        out.append('NOT SCORABLE: fewer than three stations, or the interval widths span less '
                   'than a factor of two, so no monotone claim can be tested on this set')
    return '\n'.join(out)


def junction_split(shape, zs, nominal=0.6, App=None, arc=0.125, margin_mm=0.30,
                   angle_deg=30.0, on_station=None):
    """IP-WTM-45: how much of a wall's thinness is read *at a crease of the exterior*?

    Per station, on one section at one sampling: the incumbent plain minimum, and the same
    minimum with samples whose nearest point on the **outer** contour sits within `margin_mm` of
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
    for z in zs:
        perimeter = density.section_perimeter(shape, z, App=App)
        row = {'z': float(z), 'state': None, 'thin_incumbent': None, 'thin_excluded': None,
               'creases': None, 'dropped': None, 'samples': None, 'subset_violated': False}
        if perimeter is None:
            out.append(row)
            if on_station is not None:
                on_station(row)
            continue
        n = density.counts_for_spacing(perimeter, arc)
        loops = sections.station_loops(shape, z, n, App=App)
        state, detail = ring_state(loops)
        row['state'] = state
        if state == ANNULUS:
            outer, inner = loops[0], loops[detail['nested'][0]]
            _p, d_inc = candidates.nearest_point_min(outer, inner)
            kept, d_exc = candidates.outer_corner_excluded_min(
                outer, inner, margin_mm=margin_mm, angle_deg=angle_deg)
            thin_inc = max(0.0, nominal - float(np.min(d_inc)))
            thin_exc = (max(0.0, nominal - float(np.min(d_exc)))
                        if len(d_exc) else None)
            row.update(thin_incumbent=thin_inc, thin_excluded=thin_exc,
                       creases=int(candidates.outer_creases(outer, angle_deg).sum()),
                       samples=int(len(d_inc)), dropped=int(len(d_inc) - len(d_exc)))
            if thin_exc is not None:
                row['subset_violated'] = bool(thin_exc > thin_inc + 1e-12)
        out.append(row)
        if on_station is not None:
            on_station(row)
    return out


def junction_table(rows):
    """`junction_split` as text, worst-incumbent first, with the counts that make it readable."""
    head = '%12s %11s %11s %8s %8s %8s %s' % (
        'z', 'incumbent', 'excluded', 'creases', 'dropped', 'samples', 'state')
    out = [head, '-' * len(head)]

    def _f(v, w=11):
        return ('%*s' % (w, '-')) if v is None else ('%*.5f' % (w, v))

    for r in sorted(rows, key=lambda r: -(r['thin_incumbent'] or 0.0)):
        out.append('%12.5f %s %s %8s %8s %8s %s'
                   % (r['z'], _f(r['thin_incumbent']), _f(r['thin_excluded']),
                      '-' if r['creases'] is None else r['creases'],
                      '-' if r['dropped'] is None else r['dropped'],
                      '-' if r['samples'] is None else r['samples'],
                      (r['state'] or '-')))
    scored = [r for r in rows if r['thin_incumbent'] is not None]
    with_exc = [r for r in scored if r['thin_excluded'] is not None]
    worst_inc = max((r['thin_incumbent'] for r in scored), default=None)
    worst_exc = max((r['thin_excluded'] for r in with_exc), default=None)
    total_creases = sum(r['creases'] or 0 for r in scored)
    total_dropped = sum(r['dropped'] or 0 for r in scored)
    out.append('-' * len(head))
    out.append('%d station(s) scored, %d crease(s) found in total, %d sample(s) dropped'
               % (len(scored), total_creases, total_dropped))
    out.append('worst incumbent %s, worst with creases excluded %s'
               % ('-' if worst_inc is None else '%.5f' % worst_inc,
                  '-' if worst_exc is None else '%.5f' % worst_exc))
    if total_creases == 0:
        out.append('NOTHING EXCLUDED: no station\'s exterior turns sharply enough to register a '
                   'crease, so this run cannot say whether a crease would explain the reading')
    elif worst_inc is not None and worst_exc is not None:
        out.append('the exclusion removes %.5f mm of the worst reading (%.1f%%)'
                   % (worst_inc - worst_exc,
                      100.0 * (worst_inc - worst_exc) / worst_inc if worst_inc else 0.0))
    if any(r['subset_violated'] for r in rows):
        out.append('SUBSET VIOLATED: the excluded measure cannot exceed the incumbent')
    return '\n'.join(out)


def exterior_verdict(rows, tau=0.05, wall_tol=0.01, coincide_tol=1.0e-6):
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

    * `coincident` -- the two readings agree to `coincide_tol`. No notch in reach.
    * `explained` -- thin against the notched exterior, not against the OML. The reference
      surface accounts for it.
    * `unexplained` -- thin against **both**. The reference surface does not account for it, and
      these are the stations a mechanism has to explain.

    **`clean` requires the record to have exercised the question, in two separate ways.** It is
    `True` only when `unexplained` is empty *and* `coincident` is non-empty *and* at least one
    station was thin at all. Both guards were paid for:

    * A record in which the exteriors never coincide has not exercised the converse.
    * A record with **no station over `wall_tol`** cannot distinguish the hypotheses either, and
      this one was found the hard way -- the first run of `exterior_split.py`, on
      `nose_cowl_shell` at `U` = 1.0, returned 63 stations whose worst reading was 0.0037 mm
      against a 0.01 mm tolerance, so `explained` and `unexplained` were both empty and an earlier
      version of this function reported **CLEAN**. A compliant specimen cannot test an explanation
      of non-compliance. The nose at `U` = 1 is the wrong build to ask, not evidence.

    Both are the same error as cross-checking two measures of an empty input, which this subsystem
    had already made six times before this became the seventh (section 6.1).
    """
    coincident, explained, unexplained, unreadable, thin = [], [], [], [], []
    for row in rows:
        z, notched, oml = row[0], row[1], row[2]
        if notched is None or oml is None:
            unreadable.append(row)
            continue
        if abs(notched - oml) <= coincide_tol:
            coincident.append(row)
        if notched > wall_tol:
            thin.append(row)
            if oml > wall_tol:
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
                       'test an explanation of non-compliance' % wall_tol)
    return {
        'stations': len(rows),
        'readable': len(readable),
        'unreadable': len(unreadable),
        'coincident': coincident,
        'explained': explained,
        'unexplained': unexplained,
        'thin': thin,
        'worst_notched': max((r[1] for r in readable), default=None),
        'worst_oml': max((r[2] for r in readable), default=None),
        'worst_unexplained_oml': max((r[2] for r in unexplained), default=None),
        'vacuous': bool(reasons),
        'vacuous_because': reasons,
        'clean': bool(not unexplained and coincident and thin),
    }


def exterior_table(rows, tau=0.05, wall_tol=0.01, limit=24):
    """`exterior_split` as text: the two readings a station and which bucket it fell in."""
    v = exterior_verdict(rows, tau, wall_tol)
    head = '%12s %11s %11s %11s %s' % ('z', 'to notched', 'to OML', 'difference', 'bucket')
    out = [head, '-' * len(head)]
    coin = {id(r) for r in v['coincident']}
    unex = {id(r) for r in v['unexplained']}
    expl = {id(r) for r in v['explained']}
    shown = sorted(rows, key=lambda r: -(r[1] or 0.0))[:limit]
    for r in shown:
        z, notched, oml = r[0], r[1], r[2]
        if notched is None or oml is None:
            out.append('%12.5f %11s %11s %11s %s' % (z, '-', '-', '-', 'unreadable'))
            continue
        bucket = ('UNEXPLAINED' if id(r) in unex else
                  'explained' if id(r) in expl else
                  'coincident' if id(r) in coin else 'thin-free')
        out.append('%12.5f %11.5f %11.5f %11.5f %s'
                   % (z, notched, oml, notched - oml, bucket))
    if len(rows) > limit:
        out.append('... %d more station(s), worst-first' % (len(rows) - limit))
    out.append('-' * len(head))
    out.append('%d station(s): %d over tolerance, %d coincident, %d explained by the exterior, '
               '%d UNEXPLAINED'
               % (v['stations'], len(v['thin']), len(v['coincident']), len(v['explained']),
                  len(v['unexplained'])))
    out.append('worst to notched %s, worst to OML %s'
               % ('-' if v['worst_notched'] is None else '%.5f' % v['worst_notched'],
                  '-' if v['worst_oml'] is None else '%.5f' % v['worst_oml']))
    if v['vacuous']:
        out.append('NOTHING TESTED: ' + '; and '.join(v['vacuous_because']))
    elif v['clean']:
        out.append('CLEAN: every thin station is thin only against the notched exterior')
    else:
        out.append('%d station(s) read thin against BOTH exteriors -- worst %.5f mm to the OML. '
                   'The reference surface does not explain these.'
                   % (len(v['unexplained']), v['worst_unexplained_oml']))
    return '\n'.join(out)


def criterion_table(rows, nominal=0.6):
    """`criterion_split` as text, plus the worst of each column -- which is the comparable figure.

    The per-station maxima are taken independently, so the three worst readings need not come from
    one station. That is correct for the question being asked: `TAU` and `WALL_TOL` are each
    compared against the worst reading of their own measure over the whole wall, not against each
    other at one `z`.
    """
    head = '%12s %9s %9s %9s %9s %9s %7s' % (
        'z', 'pass2', 'incumbent', 'selected', 'sampling', 'corner', 'state')
    out = [head, '-' * len(head)]

    def _f(v):
        return '-' if v is None else '%9.5f' % v

    for r in rows:
        out.append('%12.5f %s %s %s %s %s %7s'
                   % (r['z'], _f(r['thin_pass2']), _f(r['thin_incumbent']),
                      _f(r['thin_selected']), _f(r['sampling_term']), _f(r['corner_term']),
                      (r['state'] or '-')[:7]))
    out.append('-' * len(head))
    worst = {k: max([r[k] for r in rows if r.get(k) is not None] or [None],
                    key=lambda v: (v is not None, v))
             for k in ('thin_pass2', 'thin_incumbent', 'thin_selected')}
    out.append('%12s %s %s %s' % ('worst', _f(worst['thin_pass2']), _f(worst['thin_incumbent']),
                                  _f(worst['thin_selected'])))
    violations = [r['z'] for r in rows if r.get('subset_violated')]
    if violations:
        out.append('SUBSET VIOLATED at %d station(s): %s'
                   % (len(violations), ', '.join('%.5f' % z for z in violations)))
    return '\n'.join(out)


def agrees_with_kernel(shape, zs, Part, App, n_points=N_POINTS, spacing=None):
    """Check this module's nesting test against the kernel's face-making one, station by station.

    Returns the list of disagreements, each `(z, state_here, kernel_is_annulus)`. **Run this before
    trusting a dense scan's topology column**: the cheap test is a proxy, and a proxy that has not
    been checked against the authority on the geometry in hand is an assumption.
    """
    out = []
    for z in zs:
        wires = sections.closed_wires(shape, z, App=App)
        try:
            faces = Part.makeFace(wires, 'Part::FaceMakerBullseye') if wires else None
        except Exception:                                            # noqa: BLE001 - kernel refusal
            faces = None
        kernel_annulus = bool(faces is not None and len(faces.Faces) == 1
                              and len(faces.Faces[0].Wires) == 2)
        n = n_points
        if spacing is not None:
            from . import density
            perimeter = density.section_perimeter(shape, z, App=App)
            if perimeter is not None:
                n = density.counts_for_spacing(perimeter, spacing)
        here = ring_state(sections.station_loops(shape, z, n, App=App))[0]
        if (here == ANNULUS) != kernel_annulus:
            out.append((float(z), here, kernel_annulus))
    return out


def table(rows, tolerance=0.01):
    """The scan as text: one row per station, topology beside thickness."""
    head = '%10s %-16s %6s %10s %10s %9s %9s' % (
        'z', 'state', 'loops', 'thickness', 'thin', 'angle', 'radius')
    out = [head, '-' * len(head)]
    for r in rows:
        if r['worst_thin'] is None:
            out.append('%10.4f %-16s %6d %10s %10s %9s %9s'
                       % (r['z'], r['state'], r['loops'], '-', '-', '-', '-'))
            continue
        mark = '' if r['worst_thin'] <= tolerance else ' THIN'
        out.append('%10.4f %-16s %6d %10.4f %10.4f %9.2f %9.2f%s'
                   % (r['z'], r['state'], r['loops'], r['thickness'], r['worst_thin'],
                      r['angle_deg'], r['radius'], mark))
    return '\n'.join(out)
