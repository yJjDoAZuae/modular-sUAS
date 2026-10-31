"""Where a broken wall's ring stops being a ring, and how far the break runs along the axis.

**The measurement OQ-DES-CW26 has never had.** That question reproduced a wall whose cross-section
ring was broken while every existing check passed, and quantified the break *circumferentially*:
93 mm of a 1600 mm ring, at one station. How far it runs **along the axis** is unmeasured, and that
is the figure every future scan needs, because a scan can only see a break longer than its own
station spacing. Nothing on record says whether that condition was ever met.

**Two things this module is built around.**

*Sampling is a spacing, not a count.* A cowl's length scales with `U` and the wall it builds does
not, so a fixed station count means a different spacing at every `U` -- 24 stations are 2.1 mm apart
on a 50 mm `U` = 0.5 tail and 12.5 mm apart on a 300 mm `U` = 3.0 one. `station_count` turns a
spacing into a count for a given span instead, which is what makes two `U` values comparable.

*A scan grid cannot resolve an end it did not land on.* The grid brackets each end of a break to
its own spacing, and no finer. `extents` bisects between the last continuous station and the first
broken one, which costs about three classifications an end and resolves it to `tol`.

**The classifier is injected, not imported.** `state_at(z)` returns `'annulus'`, `'broken'` or
`'unreadable'`, and under `freecadcmd` it slices a real wall while in a test it is a function over
a known interval. That is this package's standing rule -- no vendor module at module scope -- and
here it buys the test that matters: a synthetic break of known extent, which real geometry cannot
provide because the extent is the unknown.
"""

#: Never fewer than this many stations, however short the part.
MIN_STATIONS = 24

#: A ceiling, so a large `U` cannot turn one scan into an unbounded one.
MAX_STATIONS = 400

#: How finely an end is resolved, in millimeters.
EXTENT_TOL = 0.25

#: The three answers a classifier may give. `'unreadable'` is never folded into either of the
#: others, because "the face maker refused" and "the ring is broken" are different findings.
ANNULUS, BROKEN, UNREADABLE = 'annulus', 'broken', 'unreadable'


def station_count(z_lo, z_hi, scan_mm, min_stations=MIN_STATIONS, max_stations=MAX_STATIONS):
    """How many stations a span needs at `scan_mm` spacing, clamped to the two limits."""
    if scan_mm <= 0.0:
        raise ValueError('scan_mm must be positive, got %r' % (scan_mm,))
    span = abs(float(z_hi) - float(z_lo))
    return max(min_stations, min(max_stations, int(round(span / float(scan_mm))) + 1))


def scan_grid(z_lo, z_hi, stations):
    """The station heights, ends included, as a list. One station is the low end alone."""
    if stations < 1:
        raise ValueError('stations must be at least 1, got %r' % (stations,))
    if stations == 1:
        return [float(z_lo)]
    step = (float(z_hi) - float(z_lo)) / float(stations - 1)
    return [float(z_lo) + step * i for i in range(stations)]


def runs(states):
    """Index ranges of consecutive `'broken'` entries, as `(first, last)` inclusive pairs.

    A run ends at anything that is not `'broken'`, including `'unreadable'`: a station nobody could
    classify does not extend a break, and treating it as broken would inflate the extent with a
    reading that was never taken.
    """
    out, start = [], None
    for i, state in enumerate(states):
        if state == BROKEN:
            if start is None:
                start = i
        elif start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(states) - 1))
    return out


def edge_z(state_at, z_good, z_bad, tol=EXTENT_TOL):
    """Where the ring stops being continuous between a continuous and a broken station.

    Returns `(z, unreadable)`, where `z` is the **broken** side of the final bracket. Taking the
    broken side means an extent built from two of these is a span the break is known to cover
    rather than one it might, so the figure never overstates itself.

    Stops early if an `'unreadable'` station turns up inside the bracket, and says so, because
    neither answer applies there and bisecting past it would be guessing.
    """
    z_good, z_bad = float(z_good), float(z_bad)
    while abs(z_bad - z_good) > tol:
        mid = 0.5 * (z_good + z_bad)
        state = state_at(mid)
        if state == UNREADABLE:
            return z_bad, True
        if state == ANNULUS:
            z_good = mid
        else:
            z_bad = mid
    return z_bad, False


def extents(state_at, grid, states, tol=EXTENT_TOL):
    """Each run of broken stations with its two axial ends refined off the grid.

    Each entry carries `z_lo`, `z_hi`, `extent_mm`, the grid stations it was found between, and two
    honesty flags: `reaches_scan_end` when the break runs to the end of the scanned span, so the
    figure is a lower bound rather than the extent, and `unreadable_in_bracket` when a station
    inside a refinement could not be classified.
    """
    out = []
    for first, last in runs(states):
        lo_unreadable = hi_unreadable = False
        if first == 0:
            lo = grid[0]
        else:
            lo, lo_unreadable = edge_z(state_at, grid[first - 1], grid[first], tol)
        if last == len(grid) - 1:
            hi = grid[-1]
        else:
            hi, hi_unreadable = edge_z(state_at, grid[last + 1], grid[last], tol)
        out.append({'z_lo': min(lo, hi), 'z_hi': max(lo, hi),
                    'extent_mm': abs(hi - lo),
                    'broken_stations_z': [grid[first], grid[last]],
                    'broken_station_count': last - first + 1,
                    'reaches_scan_end': first == 0 or last == len(grid) - 1,
                    'unreadable_in_bracket': lo_unreadable or hi_unreadable})
    return out


def missable_mm(grid):
    """The longest break this grid could miss entirely: its widest station spacing.

    **A scan's own blind spot, printed rather than left to be inferred.** A break shorter than the
    spacing can sit between two stations and be seen by neither, so a clean scan means "no break
    longer than this" and not "no break". A figure that cannot say what it would have missed is not
    a result anyone can act on.
    """
    if len(grid) < 2:
        return None
    return max(abs(grid[i + 1] - grid[i]) for i in range(len(grid) - 1))
