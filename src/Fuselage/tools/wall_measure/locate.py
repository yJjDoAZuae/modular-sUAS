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
    derived from this station's own perimeter, so the discretization is the same in millimetres at
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
    """Did the wall come back at a neighbouring plane? Then the `no_wall` was the slicer's.

    Takes `nearby_states`' rows. `True` means at least one neighbour is a healthy annulus, so the
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
