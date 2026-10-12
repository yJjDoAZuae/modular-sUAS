"""IP-WTM-2: a station's section as plain coordinate arrays, at a bounded number of round trips.

A candidate thickness measure is numerical work over a few thousand points. Fetching those points
one attribute at a time would make the screening its own bottleneck: the incumbent's convergence
study needed 3840 samples a station, and at a round trip each that is 3840 trips to measure one
station once, before any refinement sweep. So the geometry work happens vendor-side, the
coordinates cross **once per wire** as values, and every measure afterwards is `numpy`.

`Remote.project` is what makes that one trip: it reads the same attribute paths from every element
of a vendor-side sequence and returns a table. Discretizing a wire produces a vendor-side list of
points; `project('x', 'y', 'z')` turns that list into coordinates in a single request regardless of
how many points there are.

**Arc length, never sample index.** `Wire.discretize` allocates its points per edge, so on a wire
whose edges run from 0.04 mm to 152 mm the sample spacing is wildly uneven, and the same wire can
come back *rotated* between processes -- same curve, different starting edge. Anything keyed on a
sample's position in the list inherits that. Every function here returns arrays a measure can
re-parameterize by arc length, and `resample_by_arc_length` does it.

Nothing here imports a vendor module: `shape` is whatever the caller has, a bridge proxy or a real
`Part.Shape`. See doc/implementation/wall_thickness_measure.md.
"""
import numpy as np


def _points_of(wire, n_points):
    """One wire's discretized points as an `(n, 3)` float64 array, in one round trip.

    The vendor's own `discretize` keyword is `Number`; it is passed positionally through the bridge
    because a bound vendor method takes its arguments the same way either side of the boundary.
    """
    pts = wire.discretize(Number=int(n_points))
    try:
        table = pts.project('x', 'y', 'z')             # one request for every coordinate
    except AttributeError:
        # A real (non-proxy) list of vendors' vectors, when this runs under freecadcmd.
        table = [(p.x, p.y, p.z) for p in pts]
    return np.asarray(table, dtype=np.float64)


def closed_wires(shape, z, direction=(0.0, 0.0, 1.0), App=None):
    """The closed section wires of `shape` at height `z`.

    Open wires are dropped: a wall section is made of closed loops, and `Shape.slice` can return
    an open fragment at a tangency. `App` is needed only to build the direction vector; when the
    caller already holds a vector it may pass it as `direction`.
    """
    if App is not None:
        direction = App.Vector(*direction)
    return [w for w in shape.slice(direction, float(z)) if w.isClosed()]


def station_loops(shape, z, n_points=720, direction=(0.0, 0.0, 1.0), App=None):
    """Every closed loop of one section, as a list of `(n, 3)` arrays, ordered outer-first.

    **Ordered by enclosed area, not by perimeter length.** Length only tracks which loop is outer
    while both are convex-ish; once a rib makes the inner loop trace in and back out around a
    notch, that detour can add more perimeter than the smooth outer loop has while enclosing far
    less. Measured on a real `tail_shell`, two loops' lengths differed by under 0.25% while their
    areas were not remotely close. Area answers "which region is bigger" directly, however
    convoluted either path is.
    """
    return loops_from_wires(closed_wires(shape, z, direction, App), n_points)


def loops_from_wires(wires, n_points=720):
    """`station_loops`' second half, for a caller that already holds the wires.

    **One slice instead of two, which halves a dense scan.** Deriving a sample count from the
    section's own perimeter means reading `Wire.Length`, and doing that through
    `density.section_perimeter` slices the shape a second time at the same `z` for wires the caller
    has already got. A dense axial scan pays that per station -- 298 stations on one `tail_shell` at
    1 mm -- so the duplicate slice is the whole second half of its run time. Splitting the
    discretization out lets the caller slice once, measure the wires, and discretize the same ones.
    """
    loops = [_points_of(w, n_points) for w in wires]
    loops.sort(key=lambda a: abs(signed_area(a)), reverse=True)
    return loops


def signed_area(points):
    """The shoelace area of a closed polyline, in the xy plane. Sign follows orientation."""
    x, y = points[:, 0], points[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def arc_length(points, closed=True):
    """Cumulative arc length along a polyline, starting at 0. Length `n` for `n` points."""
    d = np.diff(points, axis=0, append=points[:1]) if closed else np.diff(points, axis=0)
    seg = np.linalg.norm(d, axis=1)
    out = np.concatenate(([0.0], np.cumsum(seg)))
    return out[:-1] if closed else out


def perimeter(points):
    """Total closed-loop length."""
    d = np.diff(points, axis=0, append=points[:1])
    return float(np.sum(np.linalg.norm(d, axis=1)))


def resample_by_arc_length(points, n_out):
    """Re-sample a closed loop to `n_out` points spaced evenly in arc length.

    The remedy for `discretize`'s per-edge allocation. A measure that wants "a sample every 0.05 mm"
    asks for it here rather than hoping the vendor's own spacing is uniform, and a loop that comes
    back rotated between processes re-samples to the same spacing even though its start moved.
    """
    s = arc_length(points, closed=True)
    total = perimeter(points)
    closed_s = np.concatenate((s, [total]))
    closed_p = np.vstack((points, points[:1]))
    want = np.linspace(0.0, total, int(n_out), endpoint=False)
    out = np.empty((int(n_out), points.shape[1]), dtype=np.float64)
    for k in range(points.shape[1]):
        out[:, k] = np.interp(want, closed_s, closed_p[:, k])
    return out


def spacing_stats(points):
    """`(min, median, max)` segment length. How uneven the vendor's own sampling was."""
    d = np.diff(points, axis=0, append=points[:1])
    seg = np.linalg.norm(d, axis=1)
    return float(seg.min()), float(np.median(seg)), float(seg.max())
