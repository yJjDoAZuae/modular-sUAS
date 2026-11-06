"""How far a one-row nudge travels through the interior fit, measured instead of argued.

**What this is for.** `cowl.md` OQ-DES-CW26 alternative 1 asks what the switch actually is: which
decision a 0.03 mm displacement of one input row flips, when 0.01 mm is benign and linear. The item
records a contradiction it calls its own sharpest open thread. The construction's measured gain at
the target station is **0.408 mm of wall reading per mm of nudge**, at a station 66 mm and about 7.5
station intervals away from the nudged row, while `cowl_interior_surface.md` section 4.4 says the
fit attenuates about **3.7x per station**. Those two cannot both describe the fit: 3.7x per station
over 7.5 intervals is a factor of 1.3e-4, which is three orders of magnitude under the measured
gain. `freecad_migration.md` IP-FC-146 records the discrepancy and says it is unexplained.

**Why it can be settled cheaply.** `cowl_interior._fit` is an *interpolation*, and interpolation is
a linear operator. So the surface's response to displacing one row by `delta_m` is exactly it
times a fixed shape -- the interpolating spline's cardinal function for that row -- and that shape
can be computed in closed form and compared against the real kernel. Two consequences follow
without any boolean, any rib cut, or any build:

- **At every other row the response is exactly zero.** An interpolant passes through its own data,
  so nudging row `m` moves the fitted surface at row `m` and leaves the surface at row `j` alone.
  The response lives strictly *between* rows.
- **Between rows the response is bounded and computable.** It is the cardinal function, and
  `cardinal` below evaluates it from the same station parameters `_fit` itself uses.

So if the nudge reaches a target station at all, it reaches it as a between-rows overshoot, and this
module measures how big that is. A measured response near 1.3e-4 says the fit does not carry the
nudge and the 0.408 gain is produced downstream, in the refinement's station choice or in the
boolean. A measured response near 0.4 says section 4.4's figure is wrong and the fit does carry it.
Either way the contradiction closes on a number.

**The kernel is injected, never imported.** `response` takes the fit as a callable, so a test can
hand it a pure-Python stand-in and the real run hands it `cowl_interior._fit`. Nothing here imports
`Part` or `App`, which is what lets the geometry-free half be tested at all.

**A note on "radial".** The nudge displaces a row's points along the outward direction from that
row's own centroid, which is what the probe that produced OQ-DES-CW26's numbers did. It is a
displacement of an *input* to the fit, not an edit of a built surface -- the distinction
`freecad_migration.md` IP-FC-142 had to correct once already.
"""
import math

import numpy as np


#: How many points to compare around a row when measuring a response. The rows themselves carry
#: `n_fit` points; this is independent of that, because the comparison is at matched surface
#: parameters and not at row points.
N_CIRCUM = 240

#: Bisection tolerance when solving the surface's own axial parameter for a target `z`. The fit's
#: `z` is independent of the circumferential parameter (every pole track interpolates the same
#: station list), so this solve is one-dimensional and exact to round-off.
#:
#: **Scaled with the unit by IP-FC-163**, from 1.0e-9 mm. A bisection tolerance is a length, so
#: carrying the literal across would have tightened this solve by a thousand and cost iterations
#: for nothing -- the mirror of the loosening `station_sets.FLOOR_TOL_M` would have suffered.
Z_TOL_M = 1.0e-12

#: How close two station `z` values must be to count as the same station. 1.0e-9 m is the 1.0e-6
#: mm this was before IP-FC-163.
SAME_STATION_M = 1.0e-9


def centroid(pts):
    """The mean of a row's points, as the center the radial nudge is measured from."""
    if not len(pts):
        raise ValueError('a row with no points has no centroid')
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def nudge(pts, delta_m, center=None):
    """`pts` displaced by `delta_m` meters along the outward direction from `center`.

    The displacement is absolute, not fractional: `delta_m` = 1e-5 moves every point 1e-5 m, which
    is how OQ-DES-CW26's dose series is quoted and the only reading that makes it comparable with
    `WALL_TOL`. A point sitting exactly on the center has no outward direction and is left alone
    rather than being given an arbitrary one.

    **`center` matters, and the default is wrong for a real cowl row.** A row is the symmetry
    cell's own *open arc*, bounded at each end by a construction plane, and
    `cowl_interior.cell_boundary_planes` records that every such plane passes through the origin
    and contains the part's axis. So a displacement measured from **(0, 0)** moves each point
    along a ray that lies in those planes, and a point on a plane stays on it. The default here is
    the arc's own centroid, which on a real tail row sits at about (-3.5, 13.0) -- well off the
    axis -- so displacing from it gives the endpoints a component out of the plane and the patch
    can no longer be closed. Measured: that produces `Failed to create face from wire` from
    `_side_caps`, identically at every magnitude, after a full build has been paid for. Pass
    `center=(0.0, 0.0)` for any row that came from a symmetry cell, and check the result with
    `endpoints_held`.
    """
    cx, cy = centroid(pts) if center is None else center
    out = []
    for px, py in pts:
        dx, dy = float(px) - cx, float(py) - cy
        r = math.hypot(dx, dy)
        if r <= 0.0:
            out.append((float(px), float(py)))
            continue
        out.append((float(px) + delta_m * dx / r, float(py) + delta_m * dy / r))
    return out


def nudge_rows(rows, i_row, delta_m, center=None):
    """`rows` with row `i_row` nudged by `delta_m`, every other row untouched.

    Returns a new list; the input is not modified, because a probe that mutated the row stack it
    was handed would make the second case in a dose series depend on the first.
    """
    if not 0 <= i_row < len(rows):
        raise IndexError('row %d is outside a stack of %d' % (i_row, len(rows)))
    out = []
    for i, (z, pts) in enumerate(rows):
        out.append((z, nudge(pts, delta_m, center) if i == i_row else list(pts)))
    return out


def plane_ends_held(before, after, normals, tol_m=1.0e-12):
    """Did a nudge leave every row end on the construction plane it started on?

    **The precondition a cell row's perturbation has to satisfy**, and the one worth checking
    rather than assuming. Each end of a row lies on a plane the patch is closed across, so an end
    that leaves its plane breaks the close -- and it breaks it *after* a full build has been paid
    for, reported only as `Failed to create face from wire`. Checking costs microseconds.

    **The test is the plane, not the position.** A radial displacement is supposed to slide an end
    *along* its plane: a tail row's end at (18.0100, 0) nudged 0.03 mm from the origin lands at
    (18.0400, 0), which has moved and is still on `y` = 0. Requiring the position to be unchanged
    would reject the correct behavior, which is a mistake worth recording because this function's
    first version made it.

    `normals` are the cell boundary plane normals as `(nx, ny)` pairs. Every such plane passes
    through the origin (`cowl_interior.cell_boundary_planes`), so lying on one means `x·nx + y·ny`
    is zero.
    """
    if len(before) != len(after):
        return False
    for (_z_a, pts_a), (_z_b, pts_b) in zip(before, after):
        if len(pts_a) != len(pts_b):
            return False
        for i in (0, -1):
            for nx, ny in normals:
                was = abs(pts_a[i][0] * nx + pts_a[i][1] * ny) <= tol_m
                now = abs(pts_b[i][0] * nx + pts_b[i][1] * ny) <= tol_m
                if was and not now:
                    return False
    return True


def uparams(rows):
    """The axial parameters `_fit` gives the rows: `z` normalized onto [0, 1].

    This duplicates one line of `cowl_interior._fit` deliberately. The analytic prediction has to
    be computed from the *same* parameters the kernel is given, and importing `_fit` here would
    drag `Part` into a module whose point is not needing it. `test_fit_response` pins the two
    against each other so the duplicate cannot drift.
    """
    zs = [float(z) for z, _pts in rows]
    lo, hi = zs[0], zs[-1]
    span = hi - lo
    if span == 0.0:
        raise ValueError('a row stack with no axial extent has no parameters')
    return [(z - lo) / span for z in zs]


def row_index(rows, z, tol_m=SAME_STATION_M):
    """Which row sits at `z`, or `None` if `z` falls between rows.

    Worth asking before interpreting any response: at a row the fit's response is zero by
    construction, so a target station that *is* a row and a target station 1.0e-6 m off one are
    completely different measurements.
    """
    for i, (rz, _pts) in enumerate(rows):
        if abs(float(rz) - float(z)) <= tol_m:
            return i
    return None


def cardinal(params, i_row, at):
    """The natural-cubic-spline cardinal function for knot `i_row`, evaluated at `at`.

    This is the analytic prediction for the fit's response, per mm of nudge. Interpolation is
    linear, so a `delta_m` bump at one row produces `delta_m` times this shape and nothing else.

    **The end condition is natural, and the kernel's may not be.** `Part.BSplineCurve.interpolate`
    does not document which end condition it applies, and the choice changes the response only
    near the two ends of the patch. So a disagreement between this and a measured response at an
    interior station is a real finding, while one in the first or last interval is more likely the
    end condition and is reported as such rather than as a defect.
    """
    n = len(params)
    if n < 2:
        raise ValueError('a cardinal function needs at least two knots')
    if not 0 <= i_row < n:
        raise IndexError('knot %d is outside a stack of %d' % (i_row, n))
    x = np.asarray(params, dtype=float)
    y = np.zeros(n, dtype=float)
    y[i_row] = 1.0
    if n == 2:
        f = (float(at) - x[0]) / (x[1] - x[0])
        return float(y[0] * (1.0 - f) + y[1] * f)

    # Second derivatives from the standard natural-spline tridiagonal system.
    h = np.diff(x)
    a = np.zeros((n, n), dtype=float)
    rhs = np.zeros(n, dtype=float)
    a[0, 0] = 1.0
    a[n - 1, n - 1] = 1.0
    for i in range(1, n - 1):
        a[i, i - 1] = h[i - 1]
        a[i, i] = 2.0 * (h[i - 1] + h[i])
        a[i, i + 1] = h[i]
        rhs[i] = 6.0 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
    m = np.linalg.solve(a, rhs)

    u = float(at)
    k = int(np.clip(np.searchsorted(x, u) - 1, 0, n - 2))
    dx = u - x[k]
    hk = h[k]
    return float(
        y[k]
        + dx * ((y[k + 1] - y[k]) / hk - hk * (2.0 * m[k] + m[k + 1]) / 6.0)
        + dx * dx * m[k] / 2.0
        + dx * dx * dx * (m[k + 1] - m[k]) / (6.0 * hk))


def _solve_u(surf, z, lo=0.0, hi=1.0, tol_m=Z_TOL_M):
    """The surface's own axial parameter at height `z`.

    **Not `(z - lo) / span`.** That is the parameter the rows were *given*, and it is exact at a
    row and wrong between rows, because the pole tracks interpolate the station heights rather than
    marching through them linearly. Bisection on the surface's own `z` is exact everywhere, and it
    is one-dimensional because the fit's `z` does not depend on the circumferential parameter:
    every track interpolates the same station list, so every pole at axial index `i` carries the
    same height.
    """
    z = float(z)
    z_lo = surf.value(lo, 0.0).z
    z_hi = surf.value(hi, 0.0).z
    rising = z_hi > z_lo
    for _step in range(200):
        mid = 0.5 * (lo + hi)
        z_mid = surf.value(mid, 0.0).z
        if abs(z_mid - z) <= tol_m:
            return mid
        if (z_mid < z) == rising:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _ring(surf, u, n_v):
    """`n_v` points around the surface at axial parameter `u`, as an array."""
    vs = [i / float(n_v - 1) for i in range(n_v)]
    return np.array([[surf.value(u, v).x, surf.value(u, v).y] for v in vs], dtype=float)


def response(fit, rows, i_row, delta_m, targets_m, n_v=N_CIRCUM):
    """How far the surface moves at each `z` in `targets_m`, for a `delta_m` nudge of `i_row`.

    `fit` is `cowl_interior._fit` in a real run and a stand-in in a test. It must return something
    with `.value(u, v)` giving a point with `.x`, `.y` and `.z`.

    Returns one record per target, carrying both the measured response and the analytic prediction
    so the two are never reported apart:

    - `z`, and `row` -- the row index if the target *is* a row, else `None`
    - `moved_m` -- the largest distance the surface moved at that height
    - `gain` -- `moved_m / delta_m`, which is **dimensionless and therefore the one figure here
      that did not move when IP-FC-163 converted the module** -- still comparable with
      OQ-DES-CW26's 0.408
    - `predicted_gain` -- `cardinal` at the same place, the natural-spline expectation
    - `u` -- the surface parameter the measurement was taken at

    The comparison is at matched surface parameters, which is a comparison at matched height: the
    nudge is purely radial, so both surfaces carry identical station heights and `u` means the same
    `z` on each.
    """
    if delta_m == 0.0:
        raise ValueError('a zero nudge has no gain; the probe needs a displacement')
    base = fit(rows)
    moved = fit(nudge_rows(rows, i_row, delta_m))
    params = uparams(rows)
    out = []
    for z_m in targets_m:
        u = _solve_u(base, z_m)
        ring_a = _ring(base, u, n_v)
        ring_b = _ring(moved, u, n_v)
        step = float(np.hypot(*(ring_b - ring_a).T).max())
        out.append({
            'z_m': float(z_m),
            'row': row_index(rows, z_m),
            'u': float(u),
            'moved_m': step,
            'gain': step / abs(delta_m),
            'predicted_gain': abs(cardinal(params, i_row, u)),
        })
    return out


def station_distance(rows, i_row, z_m):
    """How many station intervals lie between row `i_row` and height `z_m`.

    OQ-DES-CW26 quotes its attenuation per *station*, so a response is only comparable with it
    alongside this count. Fractional between rows, and signed the way `rows` is ordered.

    **The count itself is unit-invariant**: `u` is a ratio of two spans, so the conversion could
    not move it (IP-FC-163).
    """
    params = uparams(rows)
    zs_m = [float(rz) for rz, _pts in rows]
    lo_m, hi_m = zs_m[0], zs_m[-1]
    u = (float(z_m) - lo_m) / (hi_m - lo_m)
    # Where `u` falls in the parameter list, counted in knots rather than in meters.
    k = int(np.clip(np.searchsorted(params, u) - 1, 0, len(params) - 2))
    span = params[k + 1] - params[k]
    frac = 0.0 if span <= 0.0 else (u - params[k]) / span
    return (k + frac) - i_row


def gaps(zs_m):
    """Consecutive station gaps as `(gap_m, z_lower_m, z_upper_m)`, tightest first.

    The tightest gap is what `station_floor` is compared against and what §4.4's amplification is
    inversely proportional to, so it is the one statistic a station set is read for. Sorted
    rather than returned in axial order because the question asked of it is always "what is the
    worst", never "what is at this height".
    """
    heights_m = [float(z_m) for z_m in zs_m]
    if len(heights_m) < 2:
        return []
    return sorted((heights_m[i + 1] - heights_m[i], heights_m[i], heights_m[i + 1])
                  for i in range(len(heights_m) - 1))


def sub_floor(zs_m, floor_m):
    """The gaps in `zs_m` that fall under `floor_m`, tightest first.

    A count of these is how a station set is judged: `cavity`'s own filter drops a station for
    each one, and §4.4's amplification needs at least one beside the row being displaced. Both
    sides are meters, so the comparison means what it did before IP-FC-163.
    """
    return [row for row in gaps(zs_m) if row[0] < floor_m]


def mesh_bound(knots, offset, trials=4000, seed=20261025):
    """The largest response a one-row nudge can produce `offset` knots away, over many meshes.

    **Why a bound and not a single case.** OQ-DES-CW26's 0.408 mm per mm is measured on one real
    station stack that no longer exists on disk, and the fit's response depends on where the
    stations sit. Rather than reconstruct that stack from a document, this asks the stronger
    question: is 0.408 reachable by *any* arrangement of `knots` stations at that separation? If
    the largest response over a wide search is orders of magnitude below the measured gain, then
    the fit cannot be what carries the nudge, whatever the real spacing was.

    The search covers the uniform mesh, meshes crowded hard at one end, meshes crowded around the
    nudged row, and random meshes. `offset` is counted in knots and may be fractional, since the
    response is evaluated between knots -- at a knot it is exactly zero and the question is empty.

    Returns `(worst_gain, where)`, where `where` names the arrangement that produced it.
    """
    if knots < 4:
        raise ValueError('a cubic cardinal function needs at least four knots')
    rng = np.random.RandomState(seed)
    i_row = int(knots // 2)
    best, where = 0.0, 'none'

    cases = []
    uniform = [i / float(knots - 1) for i in range(knots)]
    cases.append((uniform, 'uniform'))
    for power in (0.25, 0.5, 2.0, 4.0):
        cases.append(([(i / float(knots - 1)) ** power for i in range(knots)],
                      'graded p=%g' % power))
    for tight in (1.0e-2, 1.0e-3, 1.0e-4, 1.0e-5):
        # A near-duplicate pair at the nudged row: the condition IP-FC-144 exists to remove, and
        # the one most likely to misbehave.
        params = list(uniform)
        params[i_row + 1] = params[i_row] + tight * (params[i_row + 1] - params[i_row])
        cases.append((sorted(params), 'crowded pair %g' % tight))
    for _trial in range(int(trials)):
        raw = np.sort(rng.random_sample(knots - 2))
        cases.append(([0.0] + list(raw) + [1.0], 'random'))

    for params, name in cases:
        if len(set(params)) != len(params):
            continue
        gain = abs(cardinal(list(params), i_row, _at(params, i_row, offset)))
        if gain > best:
            best, where = gain, name
    return best, where


def _at(params, i_row, offset):
    """The parameter `offset` knots along from `params[i_row]`, fractional between knots."""
    k = int(math.floor(i_row + offset))
    frac = (i_row + offset) - k
    k = max(0, min(k, len(params) - 2))
    return params[k] + frac * (params[k + 1] - params[k])


def rounded_rows(zs_m, n, half_x_m, half_y_m, radius_m, taper=0.0):
    """A synthetic row stack with real corners: a rounded rectangle per station.

    **Fixed-radius corners, not a smooth stand-in.** A cowl cross-section is a rounded rectangle,
    and its curvature is discontinuous where each corner meets each flat. A synthetic case built
    from ellipses would be smooth there and would not exercise what the real geometry does -- the
    requirement a previous round of this investigation was given directly, and recorded under
    IP-FC-137.

    `taper` shrinks the section linearly with `z` so the stack is not a prism. The points run as an
    open arc, matching what `_fit` is given: the first and last point are distinct and the row does
    not wrap onto itself.
    """
    if radius_m <= 0.0 or radius_m > min(half_x_m, half_y_m):
        raise ValueError('a corner radius must be positive and fit inside the section')
    rows = []
    z_lo_m = float(zs_m[0])
    for z_m in zs_m:
        # `taper` is a reciprocal length -- a fraction of the section per meter of `z` -- so a
        # caller converting its own lengths must scale it by 1000 as well. Named in the docstring
        # rather than suffixed, because `_per_m` on a knob nobody passes but the two synthetic
        # harnesses would be noise at every call site (IP-FC-163).
        scale = 1.0 - taper * (float(z_m) - z_lo_m)
        hx_m, hy_m, r_m = half_x_m * scale, half_y_m * scale, radius_m * scale
        pts = []
        for i in range(n):
            # Walk the perimeter by angle and project onto the rounded rectangle, which keeps the
            # corner arcs at a genuine fixed radius instead of blending them away.
            a = math.pi * 2.0 * i / float(n)
            ca, sa = math.cos(a), math.sin(a)
            # The corner centers sit at (+-(hx_m-r_m), +-(hy_m-r_m)); solve along the ray for
            # the rounded-rectangle boundary by taking the nearer of the flats and the corner arc.
            # Every length here is meters; `ca` and `sa` are direction cosines and carry no unit.
            tx_m = (hx_m / abs(ca)) if abs(ca) > 1.0e-12 else float('inf')
            ty_m = (hy_m / abs(sa)) if abs(sa) > 1.0e-12 else float('inf')
            t_m = min(tx_m, ty_m)
            px_m, py_m = t_m * ca, t_m * sa
            cx_m = math.copysign(hx_m - r_m, px_m) if px_m else 0.0
            cy_m = math.copysign(hy_m - r_m, py_m) if py_m else 0.0
            if abs(px_m) > hx_m - r_m and abs(py_m) > hy_m - r_m:
                # Inside a corner quadrant: re-solve the ray against that corner's circle.
                fx, fy = ca, sa
                b_m = 2.0 * (fx * -cx_m + fy * -cy_m)
                c_m2 = cx_m * cx_m + cy_m * cy_m - r_m * r_m
                disc_m2 = max(b_m * b_m - 4.0 * c_m2, 0.0)
                t_m = (-b_m + math.sqrt(disc_m2)) / 2.0
                px_m, py_m = t_m * ca, t_m * sa
            pts.append((px_m, py_m))
        rows.append((float(z_m), pts))
    return rows
