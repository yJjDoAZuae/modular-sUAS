"""The saved corpus of finished cowl walls, as a thing code can iterate.

The 2026-10-06 soak built 28 walls over 11.6 hours and **saved every one as BREP** — both kinds at
`U` in {0.5, 1, 1.5, 2, 3, 4}, with five repeats at two of them, 412 MB in
`src/Fuselage/freecad/out/soak/shapes/`. That corpus is the reason this plan is affordable: a wall
costs 0.2 s to load and 1.6 to 6.0 s a station to measure, against 4 870 s to rebuild the largest
one. Every item in doc/implementation/wall_thickness_measure.md that needs real geometry reads from
here.

**This module exists because the measurement that justified it was first run from a throwaway
script.** A number quoted in a design document whose only provenance is a heredoc cannot be
re-derived, cannot be regression-tested, and cannot be run by anyone else. The convergence sweep in
`refinement_sweep` is that measurement, moved where it belongs.

Nothing here imports a vendor module: `Part` and `App` arrive as arguments, bridge proxies in a test
and real modules under `freecadcmd`.
"""
import json
import os
import re

from .sections import closed_wires

#: Where the soak leaves its artifacts, relative to this file.
_HERE = os.path.dirname(os.path.abspath(__file__))
SOAK_DIR = os.path.normpath(os.path.join(_HERE, '..', '..', 'freecad', 'out', 'soak'))
SHAPES_DIR = os.path.join(SOAK_DIR, 'shapes')
RESULTS = os.path.join(SOAK_DIR, 'soak_results.jsonl')

#: `nose_cowl_shell_U1.0_r0.brep`
_NAME = re.compile(r'^(?P<kind>.+?)_U(?P<u>[0-9.]+)_r(?P<repeat>\d+)\.brep$')

#: `tail_shell_U0.5_top1_angle_hi.brep`, `tail_shell_U0.5_base.brep` -- IP-WTM-41's screen walls,
#: which vary a design input rather than a repeat. **A separate pattern and a separate directory,
#: not an extra field on the soak's**: `_NAME` requires the trailing `_r<n>` and so skips these, and
#: a screen wall joining the `U` corpus silently would make any figure quoted "across the corpus"
#: mean two different populations depending on what had been built that week.
#: The `(?!r\d+\.)` is load-bearing: without it this pattern also matches the soak's own
#: `tail_shell_U4.0_r3.brep` with `case` = `r3`, and the two families would overlap.
_SCREEN_NAME = re.compile(
    r'^(?P<kind>.+?)_U(?P<u>[0-9.]+)_(?!r\d+\.)(?P<case>[A-Za-z][A-Za-z0-9_]*)\.brep$')

#: The acceptance check's own station count, so a measurement here samples where the gate does.
STATIONS = 12

#: How far in from each end the station grid starts, matching `check_cowl_interior`.
END_INSET = 1.0


class WallRecord(object):
    """One saved wall: how it was built, where the file is, what the soak measured."""

    __slots__ = ('kind', 'u', 'repeat', 'path', 'recorded', 'case')

    def __init__(self, kind, u, repeat, path, recorded=None, case=None):
        self.kind = kind
        self.u = u
        self.repeat = repeat
        self.path = path
        #: The soak's own row for this build, or `None` if the results file has no match. Carries
        #: `worst_wall_error`, `wall_volume`, `wall_hash` and the timings.
        self.recorded = recorded
        #: IP-WTM-41's screen case name (`base`, `top1_angle_hi`), or `None` for a soak wall, which
        #: is a repeat of the sheet's own configuration and has no case.
        self.case = case

    @property
    def label(self):
        if self.case is not None:
            return '%s_U%s_%s' % (self.kind, self.u, self.case)
        return '%s_U%s_r%d' % (self.kind, self.u, self.repeat)

    def __repr__(self):
        return '<WallRecord %s>' % self.label


def available(shapes_dir=None, results=None):
    """Every saved wall, sorted by kind then `U` then repeat, joined to the soak's own figures.

    Returns an empty list when the corpus is absent rather than raising: a test that needs real
    geometry should skip on an empty corpus, not fail, because the files are build output and are
    not in version control.
    """
    shapes_dir = shapes_dir or SHAPES_DIR
    if not os.path.isdir(shapes_dir):
        return []
    rows = recorded_results(results)
    out = []
    for name in os.listdir(shapes_dir):
        m = _NAME.match(name)
        if not m:
            continue
        kind, u, rep = m.group('kind'), m.group('u'), int(m.group('repeat'))
        key = (kind, float(u), rep)
        out.append(WallRecord(kind, u, rep, os.path.join(shapes_dir, name), rows.get(key)))
    out.sort(key=lambda r: (r.kind, float(r.u), r.repeat))
    return out


def distinct(shapes_dir=None, results=None):
    """One record per distinct wall **shape**, dropping repeats that are byte-identical.

    The 2026-10-06 soak built five repeats at `U` = 1 and `U` = 4 on each kind to characterize
    build-to-build spread, and found all 16 of 16 repeat pairs bit-identical by `canonical_hash`.
    So the 28 saved walls are 12 distinct shapes, and a measurement that costs minutes a wall should
    not pay for the same geometry five times.

    **Deduplicated by the recorded hash, not by the parameters**, so a future soak that does find a
    difference between repeats keeps both: the dedup follows the evidence rather than assuming the
    reproducibility result still holds. A record with no hash is always kept, for the same reason.
    """
    out, seen = [], set()
    for rec in available(shapes_dir, results):
        h = (rec.recorded or {}).get('wall_hash')
        if h is not None:
            if h in seen:
                continue
            seen.add(h)
        out.append(rec)
    return out


def screen(shapes_dir=None, records_dir=None):
    """IP-WTM-41's design-input screen walls, sorted by kind then `U` then case name.

    The companion to `available`, for the other corpus. These walls vary a design input at a fixed
    `U`; the soak's vary `U` with every other input at the sheet's literal. **They are deliberately
    not merged**: OQ-DES-CW26's remaining bound is the input axis specifically, so a scan has to be
    able to say which population it covered.

    Returns an empty list when the screen has not been run, for the reason `available` does: the
    walls are build output and are not in version control.

    No deduplication. `distinct` drops byte-identical repeats because the soak built five of each
    configuration on purpose; here every wall is a different configuration by construction, and a
    case that *does* come back identical to the baseline is the finding `inputs.unmoved` reports
    rather than a duplicate to discard.
    """
    from . import inputs as _inputs
    shapes_dir = shapes_dir or _inputs.SCREEN_SHAPES
    if not os.path.isdir(shapes_dir):
        return []
    rows = screen_records(records_dir)
    out = []
    for name in os.listdir(shapes_dir):
        m = _SCREEN_NAME.match(name)
        if not m:
            continue
        kind, u, case = m.group('kind'), m.group('u'), m.group('case')
        out.append(WallRecord(kind, u, 0, os.path.join(shapes_dir, name),
                              rows.get('%s_U%s_%s' % (kind, u, case)), case=case))
    out.sort(key=lambda r: (r.kind, float(r.u), r.case))
    return out


def pairs(shapes_dir=None, records_dir=None):
    """The two-input interaction walls, sorted the way `screen` sorts its own.

    A **third** population, kept apart from the soak's `U` corpus and the screen's one-row corpus
    for the same reason those two are kept apart: OQ-DES-CW26 asks a different question of each,
    and a merged count would answer none of them. These walls move two design rows at once, which
    is the axis a one-row screen cannot reach however many rows it moves.
    """
    from . import inputs as _inputs
    return screen(shapes_dir or _inputs.PAIR_SHAPES, records_dir or _inputs.PAIR_RECORDS)


def screen_records(records_dir=None):
    """The screen's own per-case build records, keyed by label. Empty if the directory is absent.

    A file a case rather than one appended file, and for `ring_scan`'s reason: `freecadcmd` exits 0
    on an uncaught exception, a tail case is about 1 000 s, and a crash must cost that case alone.
    """
    from . import inputs as _inputs
    records_dir = records_dir or _inputs.SCREEN_RECORDS
    if not os.path.isdir(records_dir):
        return {}
    out = {}
    for name in sorted(os.listdir(records_dir)):
        if not name.endswith('.json'):
            continue
        with open(os.path.join(records_dir, name), encoding='utf-8') as fh:
            row = json.load(fh)
        if row.get('label'):
            out[row['label']] = row
    return out


def recorded_results(results=None):
    """The soak's own measurements, keyed `(kind, u, repeat)`. Empty if the file is absent."""
    results = results or RESULTS
    if not os.path.isfile(results):
        return {}
    out = {}
    with open(results, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[(row['kind'], float(row['u']), int(row['repeat']))] = row
    return out


def one(kind='nose_cowl_shell', u=1.0, repeat=0, shapes_dir=None):
    """The single cheapest useful wall, for a test that needs real geometry and not all of it.

    `nose_cowl_shell` at `U` = 1 by default: 5.6 MB, 536 faces, one solid, and it reproduces the
    incumbent measure's non-convergence, so it is enough to exercise a real section without
    touching the 50 MB tail builds.
    """
    for rec in available(shapes_dir):
        if rec.kind == kind and float(rec.u) == float(u) and rec.repeat == repeat:
            return rec
    return None


def load(Part, record_or_path):
    """Read a saved wall into a shape. 0.2 s for the nose at `U` = 1."""
    path = getattr(record_or_path, 'path', record_or_path)
    shape = Part.Shape()
    shape.read(path)
    return shape


def station_grid(shape, stations=STATIONS, inset=END_INSET):
    """`stations` evenly spaced `z` values across `shape`, inset `inset` from each end.

    **This is NOT the acceptance check's own grid, and an earlier version of this docstring claimed
    it was.** `check_cowl_interior.main` and `soak_cowl_shell` both take `ci.z_extent(body)` -- the
    *body*, the full cowl solid -- and inset 1 mm. The corpus saves only the finished **wall**,
    whose z extent is not the body's, so the grid computed here is a different set of stations.

    The consequence is measurable and was found by it: the soak recorded `missing_stations` = 0 for
    all 28 builds on the body-based grid, while a sweep on this grid loses 3 to 7 of 12 stations on
    every `nose_cowl_shell` wall, because stations near the ends fall where the wall has no closed
    annular section. **So a figure from this grid cannot be differenced against a figure the soak
    recorded** -- they are answers about different places.

    The remedy is not to guess the body's extent, which this corpus cannot recover, but to measure
    every instrument on *this* grid and compare those to each other (`sweep.sweep` takes several
    measures for exactly that reason). `soak_cowl_shell` records `station_z_lo`/`station_z_hi` as of
    IP-WTM-18, so a wall built by a later soak *can* be measured on the gate's own grid --
    `gate_station_grid` reads them. The 2026-10-06 corpus predates that and has none.
    """
    bb = shape.BoundBox
    lo, hi = bb.ZMin + inset, bb.ZMax - inset
    return [lo + (hi - lo) * i / float(stations - 1) for i in range(stations)]


def sectioning_extent(shape, App=None, tol=1.0e-3, probes=9):
    """Where a shape **really** starts and ends in `z`, found by sectioning rather than from its box.

    **A bounding box on these solids is an outer bound and nothing more**, which is the whole reason
    `station_grid` loses stations. `cowl_interior.z_extent`'s own docstring records a nose whose box
    was 139 % of the part and a station the box called interior that returned no loops at all: the
    box is computed from the untrimmed B-spline geometry, not from the trimmed result. This is the
    same idea as `z_extent`, reimplemented here because that function lives in a module that imports
    FreeCAD and this package does not.

    Probes a handful of interior fractions of the box for one that sections, then bisects outward to
    each real end within `tol`. Returns `(lo, hi)`, or `None` when no probe finds material -- which
    is a finding about the shape rather than something to guess around.
    """
    bb = shape.BoundBox
    lo_box, hi_box = bb.ZMin, bb.ZMax

    def sections(z):
        return bool(closed_wires(shape, z, App=App))

    inside = None
    for i in range(1, probes + 1):
        z = lo_box + (hi_box - lo_box) * i / float(probes + 1)
        if sections(z):
            inside = z
            break
    if inside is None:
        return None

    def edge(outward):
        near, far = inside, outward          # near sections, far does not (or is the box end)
        if sections(far):
            return far
        while abs(far - near) > tol:
            mid = 0.5 * (near + far)
            if sections(mid):
                near = mid
            else:
                far = mid
        return near

    return edge(lo_box), edge(hi_box)


def measurable_station_grid(shape, stations=STATIONS, inset=END_INSET, App=None):
    """`stations` evenly spaced `z` across the shape's **real** extent, inset from each real end.

    The grid `station_grid` should have used all along. On a `nose_cowl_shell` wall the bounding box
    overstates the part, so `station_grid` places its end stations where there is no wall and loses
    3 to 7 of 12; this places them inside the material. Falls back to `station_grid` when nothing
    sections at all, so a caller always gets a grid.
    """
    extent = sectioning_extent(shape, App=App)
    if extent is None:
        return station_grid(shape, stations, inset)
    lo, hi = extent[0] + inset, extent[1] - inset
    if hi <= lo:
        return station_grid(shape, stations, inset)
    return [lo + (hi - lo) * i / float(stations - 1) for i in range(stations)]


def gate_station_grid(record, stations=STATIONS):
    """The acceptance gate's **own** stations for `record`, or `None` if the soak did not save them.

    `soak_cowl_shell` records the body-derived bounds it placed its stations from (IP-WTM-18), which
    is the one thing the saved wall cannot recover. Where they are present this returns the gate's
    exact grid, so a re-measurement is a reproduction of the gate's number rather than an
    independent reading; where they are absent -- every wall in the 2026-10-06 corpus, built before
    the soak recorded them -- it returns `None` rather than silently falling back to the wall-based
    grid, because the two are answers about different places and a caller must not confuse them.
    """
    recorded = getattr(record, 'recorded', None) or {}
    lo, hi = recorded.get('station_z_lo'), recorded.get('station_z_hi')
    if lo is None or hi is None:
        return None
    lo, hi = float(lo), float(hi)
    return [lo + (hi - lo) * i / float(stations - 1) for i in range(stations)]


def interior_station(shape, index=3, stations=STATIONS, inset=END_INSET):
    """One station well inside the part, for a single-station measurement."""
    return station_grid(shape, stations, inset)[index]
