"""What do the booleans after the fit do with a perturbed surface? The dose series, through the cut.

**Why this exists.** `cowl.md` OQ-DES-CW26 reproduced a wall whose cross-section ring was broken
over 93 mm of its 1600 mm circumference while every existing check passed, and its alternative 1
asks which decision changes between that build and a healthy one.
`cowl_interior_surface.md` §4.4 narrowed it by elimination: the **fit** is not the switch, because
the thinnest wall the fitted surface leaves falls smoothly from 0.512454 mm to 0.338927 mm across a
0 to 0.1 mm row displacement and never approaches zero, straight through the bracket the severance
is reported in. So the ring comes apart in one of the three booleans `shell_solid` performs after
the fit -- extend across the cell planes, `notched.cut(inside)`, and `mirror_across_cell` -- and
none of them had ever been measured under a perturbation.

**What made that impossible, and what changed.** `cavity` derives its own station set and returns
only the finished cavity solid, and the functions that assemble that solid are closures inside it,
so nothing outside could feed a perturbed surface through the real pipeline. OQ-DES-CW34 is that
question, resolved; this script is the only caller of the seam it decided on. That seam is not a
parameter -- `cavity` and `shell_solid` take no measurement arguments. `wall_measure.probe`
installs an inert module-level hook on `cowl_interior` for the duration of one build and removes it
whether the build returns or raises, which is what the `with` block in `run` below is doing.
Whether the production module should carry such a hook at all is OQ-DES-CW35, and it does not
affect how this script is used either way.

**The hook is on the eroded contour, not on the converged rows, and the placement is load-bearing.**
An earlier version transformed the rows `_refine` returned, which looks equivalent and is not:
section 5's second pass rebuilds its rows with `fit_at` after the rib cut, so a perturbation applied
downstream of `_refine` is discarded on the first post-cut round. Measured, the cavity's first fuse
differed per dose -- 36399.76, 36401.90 and 36409.40 mm3 against a 36398.69 control -- while its
*second* came back at the control's value for every one, so the finished wall was unperturbed and
the series read as a clean null result. Hooking the contour source makes every row the construction
builds carry the perturbation.

**What is recorded at each dose**, because the point is to see which check moves first:

- whether the build raised at all, and with what -- `Unconverged` from the solid count, from the
  cavity's own connectivity, or `PreconditionFailed` from a section that would not form
- the wall's solid count and volume, and the partition slip against `PARTITION_TOL` = 2.0e-3
- the rib residue against `RIB_RESIDUE` = 0.01 mm3
- **the annulus identity at every sampled station**, via `check_cowl_interior.section_regions`:
  one face with two wires means the ring is continuous, several one-wire faces mean it is broken
  into that many arcs. This is the measure OQ-DES-CW26's alternative 2 is about, and it is the only
  one of these that caught the reproduced failure.

A dose that severs while every check but the last passes reproduces the silent case. A dose that
raises reproduces the caught case. A dose that does neither says the boolean is not sensitive at
that magnitude on this configuration.

**Cost, from the soak corpus's own build times rather than estimated.** One full build a dose, and a
`tail_shell` build is **727 s at `U` = 0.5 and 4 170 s at `U` = 3.0** -- 5.7x, because the part is
50 mm against 300 mm. The scan adds roughly 7 s a station, and the station count follows `SCAN_M`,
so `U` = 3.0 pays about 150 slices a dose on top. Budget **about 1.5 hours a dose at `U` = 3.0**,
against 15 minutes at `U` = 0.5. The six-dose series is therefore around 9 hours at `U` = 3.0, which
is why the doses are ordered so an interrupted run still answers the question it was started for.

**What it measures when a ring does break.** `break_extent` resolves the break's two axial ends by
bisecting between the last continuous station and the first broken one, and the wall is written to
BREP. Both happen on the wall already in memory: the severance on record was reproduced on
2026-10-04 and the shape discarded, so its axial extent is still unknown and recovering it would
cost another full build at the `U` it happened on. The figure that exists -- 93 mm of a 1600 mm ring
-- is circumferential, at one station, and says nothing about how far the break runs along the axis.

**What it keeps when a dose is refused instead.** A refusal used to carry only a sentence, so the
shape its own measurement was taken on died with the exception: the post-cut pass reported the
finished wall closed to 0.0001 mm at `z` = -73.1818 on 2026-10-29, and the cut cavity behind that
number was already gone by the time anyone could ask what it looked like. `Unconverged` now carries
the shape and the station, and the `except` clause in `run` writes them through
`wall_measure.refusals` -- inside the `except` and before the `finally` that closes the document,
which is the only window where the shape is still valid. The write cannot fail the run: a refusal
that also could not be written down is still a refusal, and is reported as both.

**Recreating OQ-DES-CW26's own result needs two arguments, and this is the only configuration the
silent failure has ever appeared in.** Three station sets were run on 2026-10-04 and they behave
differently: a `forced` 33-station set with a manufactured 0.0000339 mm pair fails loudly 3 of 3;
the real **32-station unfiltered union** breaks the ring with all six checks passing; and the
**27-station floored set** severs at the same dose and *is* caught. `--floor=0` restores that
32-station union -- not by forcing anything, but by declining to drop stations the construction
derived for itself -- and `--target=` displaces the row that question displaced rather than a
notch edge chosen by position. Together they are the comparison that says whether IP-FC-144 is a
fix or a mask.

Run it as::

    freecadcmd sever_doses.py --pass --kind=tail_shell --pass --u=0.5
    freecadcmd sever_doses.py --pass --kind=tail_shell --pass --u=0.5 --pass --doses=0,0.03

and to recreate the silent severance::

    freecadcmd sever_doses.py --pass --kind=tail_shell --pass --u=3.0 --pass --floor=0 \
        --pass --target=-283.9951339 --pass --doses=0,0.03

`freecadcmd`'s exit code is unreliable, so read the printed table and the JSON. One `--pass` per
argument.
"""
import io
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App                                                    # noqa: E402

import check_cowl_interior as cci                                        # noqa: E402
import cowl_interior as ci                                               # noqa: E402
import cowl_tree                                                        # noqa: E402
import si                                                                # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from station_gaps import BUILDERS, PARAMS, notch_compound, with_u        # noqa: E402
from wall_measure import fit_response as fr                              # noqa: E402
from wall_measure import refusals as wm_refusals                          # noqa: E402
from wall_measure import ring_breaks as rb                               # noqa: E402
from wall_measure import probe as wm_probe                                # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'sever_doses')

# **The builders are the *un-shelled* ones, and that is load-bearing.** `BUILDERS` comes from
# `station_gaps`, where it maps `tail_shell` to `cowl_tree.tail_cowl` -- the tree without the
# `_CowlShell` node. Emitting the shelled builder instead makes `doc.recompute()` build the entire
# wall through the node's own `shell_solid` call, which does not carry the hook, and this script
# then builds it a second time with the hook: measured at 675 s wasted a dose before the discarded
# first build was noticed. Stopping the tree at `pieces()` and calling `shell_solid` here is one
# build a dose rather than two.

#: The station OQ-DES-CW26's probe displaced. Carried to its full precision: forcing a four-decimal
#: printing of a notch edge into a seed set manufactured a 0.0000459 mm pair and invalidated a run
#: once already (`cowl_interior_surface.md` §6.1, sixth caution). Converted from -283.9951339 mm
#: by IP-FC-163; it is the same station, to the last digit.
HISTORIC_Z_M = -0.2839951339

#: Spans the reported bracket -- benign at 0.01, severed at 0.03 -- with the ends that are recorded
#: as caught, so a run reproduces both the silent and the loud case if either is reachable.
#:
#: **Ordered by what it answers, not by magnitude**, because a dose costs a full build and the JSON
#: is written after each one: the control first, then 0.03 where the silent severance is reported,
#: so an interrupted run has already answered "does it sever at the reported magnitude" rather than
#: having spent the time walking up to it. `inputs.cases` orders its own excursions the same way
#: and for the same reason.
DOSES = (0.0, 0.03, 0.01, 0.02, 0.05, 0.1)

#: **Axial scan spacing -- not a station count.** A count is the mistake this
#: project has made in a published figure already: the cowl's length scales with `U` and the wall it
#: builds does not, so 24 stations is 2.1 mm apart on a 50 mm `U` = 0.5 tail and **12.5 mm apart on
#: a 300 mm `U` = 3.0 one**. The break whose axial extent nobody has measured would have to be
#: longer than the spacing to be seen at all, so holding the spacing is what makes two `U` values
#: comparable. `wall_vanish` scans at the same 2.0 mm (2.0e-3 m).
SCAN_M = 2.0e-3

#: The station floor, the ceiling and the refinement tolerance come from the library module rather
#: than being restated here, so there is one source for them. 24 stations is the floor however short
#: the part; 400 is the ceiling, which at 2.0 mm binds above a 600 mm part and leaves a `U` = 3.0
#: tail's 150 well inside; 0.25 mm is what an end is resolved to, about three slices an end.
MIN_STATIONS = rb.MIN_STATIONS
MAX_STATIONS = rb.MAX_STATIONS
EXTENT_TOL_M = rb.EXTENT_TOL_M


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def ring_state_at(wall, z_m):
    """The annulus identity at one station: `(state, faces, wires, area)`.

    `state` is `'annulus'`, `'broken'` or `'unreadable'`. Factored out of `ring_states` so
    `break_extent` can bisect with exactly the classification the scan used -- a refinement that
    asked the question a second way would be measuring a different quantity.

    `z_m` is meters, because `_slice_wires` is (IP-FC-163). Handing it millimeters sliced every
    station a thousand times outside the part, so every scan station read `unreadable`.
    """
    wires = [w for w in ci._slice_wires(wall, z_m) if w.isClosed()]
    got = cci.section_regions(wires)
    if got is None:
        return 'unreadable', None, None, None
    faces, wire_counts, area = got
    if faces == 1 and wire_counts == [2]:
        return 'annulus', faces, wire_counts, area
    return 'broken', faces, wire_counts, area


def ring_states(wall, z_lo_m, z_hi_m, stations=None, scan_m=SCAN_M):
    """The annulus identity at each station: `(continuous, broken, unreadable, worst, detail)`.

    `worst` names the station with the most arcs, which is where to look first. A station whose
    section will not form a face at all is counted `unreadable` and never folded into either of the
    other two, since "the maker refused" and "the ring is broken" are different answers.

    `stations` defaults to whatever `scan_m` spacing requires over this span, so the sampling is a
    spacing and not a count -- see `SCAN_M`.

    **The span and the grid are SI and the kernel call converts** (IP-FC-163). `ring_breaks` is
    SI since that item, so handing it a millimeter grid would refine each end a thousand times
    finer than `EXTENT_TOL_M` intends and pay for it in kernel sections.
    """
    if stations is None:
        stations = rb.station_count(z_lo_m, z_hi_m, scan_m, MIN_STATIONS, MAX_STATIONS)
    continuous, broken, unreadable, worst = 0, 0, 0, None
    detail = []
    for z_m in rb.scan_grid(z_lo_m, z_hi_m, stations):
        state, faces, wire_counts, area = ring_state_at(wall, z_m)
        if state == 'unreadable':
            unreadable += 1
            detail.append({'z_m': z_m, 'state': 'unreadable'})
        elif state == 'annulus':
            continuous += 1
            detail.append({'z_m': z_m, 'state': 'annulus', 'area': area})
        else:
            broken += 1
            detail.append({'z_m': z_m, 'state': 'broken', 'faces': faces,
                           'wires': wire_counts, 'area': area})
            if worst is None or faces > worst[1]:
                worst = (z_m, faces)
    return continuous, broken, unreadable, worst, detail


def break_extent(wall, detail, tol_m=EXTENT_TOL_M):
    """Each run of broken stations, with its axial ends refined off the scan grid.

    The run-finding and the bisection are `wall_measure.ring_breaks`, which takes the classifier as
    an argument so the logic is testable against a synthetic break of **known** extent -- the one
    test real geometry cannot provide, since the extent is the unknown. This function is only the
    part that needs the kernel: classifying a real section.

    It runs on the wall already in memory, which is the point: the 2026-10-04 severance was
    reproduced and its shape discarded, so recovering the figure now would cost another full build
    at the `U` it happened on.
    """
    grid = [item['z_m'] for item in detail]
    states = [item['state'] for item in detail]
    # The grid, the tolerance and the section are all SI; `_slice_wires` converts for the kernel.
    found = rb.extents(lambda z_m: ring_state_at(wall, z_m)[0], grid, states, tol_m)
    faces = dict((item['z_m'], item.get('faces')) for item in detail)
    for span in found:
        first, last = span['broken_stations_z']
        inside = [faces.get(z) or 0 for z in grid if first <= z <= last]
        span['max_faces'] = max(inside) if inside else None
    return found


#: The station OQ-DES-CW26 measured the broken ring at, 66 mm from the row it displaced. Read
#: here as well as scanned, so a result can be set against the 0.355705 mm on record directly.
#: Was -217.7261 mm.
BREAK_Z_M = -0.2177261

#: What the healthy wall reads at `BREAK_Z_M`, reproduced to six decimals across five fresh builds
#: and two independently fitted station sets, and 0.546559 mm on IP-FC-144's own set. Was
#: 0.546556 mm -- the figure is unchanged and only its unit is stated differently.
HEALTHY_M = 5.46556e-4

#: What the silent failure read there: not a thickness at all, but the gap between the two broken
#: ends, which `wall_thickness` cannot distinguish from a thickness (section 7.1). Was
#: 0.355705 mm.
SILENT_M = 3.55705e-4


def target_station(kept, z_lo, z_hi, notch_edges, want_m=None, tol_m=1.0e-6):
    """Which station to displace: an interior notch edge, never an end of the patch.

    **Not "nearest to the historical `z`".** That station belongs to a `U` = 3.0 tail, which is
    300 mm long; at `U` = 0.5 the part is 50 mm, so nearest-to--283.995 collapses onto the
    patch's first station. Measured, that displaced `z` = -49.9972, which is a patch boundary --
    pinned by section 4.5 so both adjacent patches sample it at the same height -- and the
    perturbation went almost nowhere: the wall volume moved 0.006 mm3 out of 5851.

    So the target is chosen by what it *is*, not by an absolute height: a notch edge, because
    every reproduction of the severance has been at one, and strictly inside the patch so it is
    not a boundary row. Falls back to the station nearest the middle if no interior notch edge
    survives the floor.

    **`want_m` names an exact station instead, and raises rather than substituting a near one.**
    Recreating OQ-DES-CW26's own result means displacing the row it displaced, and a target chosen
    as "nearest to" a height that is not in the set is how this harness produced a null result
    once already: at `U` = 0.5 it collapsed onto the patch's pinned first station. So an exact
    request that the station set cannot satisfy is an error, and the error names the nearest
    station and its distance, because that is the diagnosis -- a station absent at this floor is
    the finding, not a reason to move the probe somewhere else.

    **`want_m` is meters, like everything in `kept`, and the caller converts.** It took a
    millimeter value until 2026-11-13 and the diagnosis below reported a meters difference
    labeled "mm", so a target given in the units this module's own usage example prints missed
    by a factor of a thousand and the error blamed the station floor for it. The floor advice is
    now given only when the nearest station is near enough for the floor to be the explanation.
    """
    interior = [z for z in kept[1:-1]]
    if not interior:
        raise ci.PreconditionFailed('the patch has no interior station to displace')
    if want_m is not None:
        exact = [z for z in interior if abs(z - want_m) <= tol_m]
        if not exact:
            near_m = min(kept, key=lambda z: abs(z - want_m))
            off_m = abs(near_m - want_m)
            # Inside the patch and merely not in the set: the floor is the likely reason. Far
            # outside it: the floor cannot explain that, and saying so sends the reader to the
            # units instead of to a flag they have probably already passed.
            if z_lo - abs(z_hi - z_lo) <= want_m <= z_hi + abs(z_hi - z_lo):
                why = ('At the production floor that station is thinned away -- pass --floor=0 '
                       'to seed the unfiltered union it belongs to.')
            else:
                why = ('That target is outside the patch z = %.4f..%.4f mm entirely, so no floor '
                       'setting can produce it. `--target` is millimeters, like every other z '
                       'this harness prints.' % (si.mm(z_lo), si.mm(z_hi)))
            raise ci.PreconditionFailed(
                'no interior station at z = %.7f mm in this set of %d; the nearest is %.7f mm, '
                '%.7f mm away. %s'
                % (si.mm(want_m), len(kept), si.mm(near_m), si.mm(off_m), why))
        return exact[0], any(abs(exact[0] - e) <= tol_m for e in notch_edges)
    edges = [z for z in interior
             if any(abs(z - e) <= 1.0e-6 for e in notch_edges)]
    pool = edges or interior
    middle = 0.5 * (z_lo + z_hi)
    return min(pool, key=lambda z: abs(z - middle)), bool(edges)


def probe_for(delta_mm, target_z_m, normals, tol_m=1.0e-6):
    """A contour hook that nudges the station at `target_z_m` by `delta_mm`, radially.

    **The dose is millimeters and the contour is meters, so this converts.** Until
    2026-11-13 it passed the millimeter dose straight to `fit_response.nudge`, whose argument
    is `delta_m`, so a 0.03 mm dose moved the row 0.03 m -- thirty millimeters. The
    construction answered that correctly: the fitted surface read 24 to 29.5 mm off the
    exterior at exactly the displaced station, decaying over about 5 mm, and section 5 refused
    with an 18.49 mm wall error that looked like a construction defect and was a dose a
    thousand times too large. The contours became SI under IP-FC-163; the records from before
    it store the station as -283.995, which is millimeters, so the runs on file before that
    conversion applied the dose they claimed and are unaffected.

    Applied to the eroded contour as `cavity` builds it, so every row the construction makes --
    including the ones section 5's second pass inserts after the rib cut -- carries the
    perturbation.

    **Counting is `wall_measure.probe.Probe`'s job, not this function's.** This used to carry its
    own `moved` dict; the probe object counts every row it actually transformed and records each
    `z`, so the evidence that something moved comes from the one place that can see it. Returning
    `pts` unchanged is how this hook declines a row, and the probe does not count those.
    """

    delta_m = si.m(delta_mm)

    def hook(z_m, pts):
        if delta_m == 0.0 or abs(z_m - target_z_m) > tol_m:
            return pts
        # **Radial from the origin, not from the arc's centroid.** Every cell boundary plane
        # passes through the origin and contains the part's axis, so a ray from (0, 0) lies in
        # those planes and a point on one stays on it. The centroid default does not: on a real
        # tail row it sits near (-3.5, 13.0), which lifts the arc's two ends off the construction
        # plane and makes `_side_caps` fail with `Failed to create face from wire` -- measured,
        # identically at every magnitude, after the build was already paid for.
        out = fr.nudge(pts, delta_m, center=(0.0, 0.0))
        if not fr.plane_ends_held([(z_m, pts)], [(z_m, out)], normals):
            raise ci.PreconditionFailed(
                'the nudge moved a row end off its construction plane, so the patch could not '
                'be closed. The displacement must be radial from the axis; see '
                'fit_response.nudge.')
        return out

    return hook


def _moved(probe):
    """What a probe actually did, for the record. `None` when there was no probe at all.

    **`stations_m`, and the record is millimeters.** This read `probe.stations` until
    2026-11-13, which `Probe` has not had since IP-FC-163 renamed it -- and `Probe.__slots__`
    means the attribute does not merely read as empty, it raises. `_moved` runs on every outcome
    this harness records, success and both failure paths, so no dose could be written at all,
    and the raise happens *after* the build: a 70 minute run would finish and then discard its
    own result. Found by a run that got as far as the dose table and wrote no row.

    The fields carry `_mm` because the rest of this record does (`delta_mm`, `target_z_mm`) and
    because an unsuffixed `station` holding meters next to a `delta_mm` holding millimeters is
    the same trap one layer down. The pre-rename records held millimeters under the old names,
    so the numbers are comparable across the change; only the keys differ.
    """
    if probe is None:
        return None
    stations_mm = [si.mm(z_m) for z_m in probe.stations_m]
    return {'calls': probe.calls,
            'station_mm': stations_mm[-1] if stations_mm else None,
            'distinct_stations_mm': sorted(set(stations_mm))}


def _export_brep(shape, path):
    """Write whatever a refusal carries, which is not always a `TopoShape`.

    `Unconverged` carries "the fitted surface for the pre-cut station budget", and a
    `Part.BSplineSurface` is geometry rather than topology -- it has no `exportBrep`. Measured
    2026-11-13: the pre-cut refusal is the one this harness actually produces, so the one case
    the exporter did not handle was the common one, and the artifact was skipped with
    `AttributeError: 'Part.BSplineSurface' object has no attribute 'exportBrep'` every time.

    `toShape()` is the kernel's own geometry-to-topology step and is what the surface would
    have to go through to be written at all; doing it here keeps `wall_measure.refusals` free
    of the kernel, which is the division that makes it testable.
    """
    if not hasattr(shape, 'exportBrep') and hasattr(shape, 'toShape'):
        shape = shape.toShape()
    shape.exportBrep(path)


def _rounds(exc):
    """The post-cut pass's per-round interval lists, for the record. `()` when there are none.

    Carried by `cowl_interior.Unconverged` and dropped on the floor until 2026-11-13: the
    exception grew the field and nothing wrote it down, so a refusal that had the data still
    produced a record without it. Lengths become millimeters here, like every other length in
    this record.
    """
    out = []
    for entry in getattr(exc, 'rounds', ()) or ():
        out.append({
            'round': entry['round'],
            'worst_mm': si.mm(entry['worst_m']),
            'worst_z_mm': (None if entry['worst_z_m'] is None
                           else si.mm(entry['worst_z_m'])),
            'intervals': [{'patch': ei, 'interval': i,
                           'z_lo_mm': si.mm(lo_m), 'z_hi_mm': si.mm(hi_m),
                           'gap_mm': si.mm(gap_m)}
                          for ei, i, lo_m, hi_m, gap_m in entry['intervals']],
        })
    return out


def _save_wall(wall, out_dir, kind, u, delta):
    """Write a wall to BREP: the broken ones, because nobody has one, and the control.

    **The control is saved too, which it was not at first, and the omission cost a measurement.**
    The 2026-10-27 run read 0.563655 mm at the break station where the record says a healthy wall
    reads 0.546556 mm. The leading explanation is that `worst_low` is a nearest-point minimum that
    does not converge and the sampling changed from a fixed count to an arc-length spacing
    (IP-WTM-25), which `wall_thickness`'s own `arc` argument would settle in seconds -- on a wall
    that no longer existed, because only broken walls were kept. A 28 MB file against a 5 693 s
    rebuild is not a close call.

    Still not every dose: a dose that neither broke nor is the control has a reading in the record
    and nothing a shape would add.
    """
    shapes = os.path.join(out_dir, 'shapes')
    if not os.path.isdir(shapes):
        os.makedirs(shapes)
    path = os.path.join(shapes, '%s_U%g_d%g.brep' % (kind, u, delta))
    wall.exportBrep(path)
    return path


def thickness_at(wall, z_m, t_m):
    """The incumbent measure's reading at one station, as a dict, or `None` where it refuses.

    **Read because the figure on record is this measure's output, not because it is trusted.**
    Section 7.1 establishes that at the silent failure it returned 0.355705 mm, which is the gap
    between the two broken ends of a split ring and not a thickness at all. `wall_thickness` has
    since been made to return `None` for a section that is not an annulus, so on a true recreation
    it should **refuse where it once answered** -- and that refusal is the finding, because it is
    the external check catching what it used to misreport. The annulus scan is kept beside it
    rather than replaced by it, since the two say different things.
    """
    try:
        got = cci.wall_thickness(wall, z_m, t_m, ci.WALL_TOL_M)
    except Exception as exc:                                      # noqa: BLE001
        return {'error': '%s: %s' % (type(exc).__name__, str(exc)[:160])}
    if got is None:
        return {'refused': True}
    n, near, worst_low, median, worst_high = got
    return {'refused': False, 'samples': n, 'within_tol': near,
            'worst_low': worst_low, 'median': median, 'worst_high': worst_high}


#: The rib dilations a run can be made with. `None` is the construction as it ships; `hull` is
#: OQ-DES-CW40's alternative, each convex part of each slab dilated as an exact Minkowski sum;
#: `planar` is the same split with flat faces and square or beveled corners
#: (`rib_hull.dilate_planar`).
DILATIONS = ('hull', 'planar')


def _dilation(name):
    """The `Probe(dilate=...)` hook for `--dilate=name`, or `None` for the shipped dilation."""
    if name is None:
        return None
    if name not in DILATIONS:
        raise ValueError('--dilate=%s: known dilations are %s' % (name, ', '.join(DILATIONS)))
    import rib_hull
    return rib_hull.planar_tools if name == 'planar' else rib_hull.tools


def run(kind, u, doses, out_dir, floor_mm=None, want_z_m=None, dilate=None):
    started = time.time()
    print('')
    print('%s at U = %g: the booleans after the fit, under a row displacement.' % (kind, u))
    # **Not `HISTORIC_Z`.** An earlier version printed that constant here and called it the target,
    # which is wrong twice: `target_station` chooses an interior notch edge nearest the middle of
    # the patch, and at `U` = 3.0 the historical station is one the floor drops. A header naming a
    # station the run does not displace is the kind of figure that gets quoted. The station is
    # chosen per dose, from that dose's own station set, and printed in the table below.
    print('  the station displaced is chosen per dose: an interior notch edge, never a patch end')
    print('  (OQ-DES-CW26 produced its failure at z = %.7f mm, which the station floor now '
          'drops)' % si.mm(HISTORIC_Z_M))
    print('')
    if floor_mm is not None:
        print('  station floor overridden to %.3f mm -- the unfiltered union, '
              'which is the pre-IP-FC-144 station set' % float(floor_mm))
    if want_z_m is not None:
        print('  displacing z = %.7f mm exactly; an absent station is an error, not a substitution'
              % si.mm(want_z_m))
    print('  incumbent reading taken at z = %.4f mm, where the healthy wall reads %.6f mm and '
          'the silent failure read %.6f mm'
          % (si.mm(BREAK_Z_M), si.mm(HEALTHY_M), si.mm(SILENT_M)))
    print('')
    print('   delta   outcome        solids  slip       residue   annulus  broken  at break  s')
    print('   ' + '-' * 86)

    records = []
    for delta in doses:
        at = time.time()
        rec = {'delta_mm': delta}
        report = {}
        probe = None
        doc = None
        try:
            doc = App.newDocument('sever_doses')
            cowl_tree.emit(doc, None, with_u(PARAMS[kind], u), BUILDERS[kind])
            doc.recompute()
            body_node, tools, mirrors, cell_cut = cowl_tree.pieces(doc)
            params = doc.getObject('Params')
            # **The two cells are a Spreadsheet's, so their product is millimeters, and
            # every `cowl_interior` call below takes meters** (IP-FC-163). This is the same
            # crossing `wall_vanish` and `tau_study` were getting wrong.
            t_m = si.m(float(params.get('cowl_n_perimeters'))
                       * float(params.get('extrusion_width')))
            # **Degrees on the sheet, radians in the construction.** `shell_solid` takes
            # `overhang_rad`, and this passed the sheet value straight through until
            # 2026-11-13, so the P1 slope guard compared real radians against 35 of them
            # and refused every dose before building anything -- reporting the limit as
            # `overhang_angle_from_bed = 2005.35`, which is 35 radians printed in
            # degrees, the number that gave it away. `cowl.from_flat` converts this row
            # for the production path (`cowl.ANGLE_ROWS`); this harness builds its
            # parameters itself and so has to convert for itself too.
            overhang_rad = si.deg_to_rad(float(params.get('overhang_angle_from_bed')))
            # The planes the nudge has to respect, read off the cell itself rather than assumed
            # from the mirror chain -- the same source `cavity` uses.
            normals = [(p.x, p.y) for p in ci.cell_boundary_planes(body_node.Shape)]
            # The station set `cavity` will derive, computed here so the target can be chosen
            # from it rather than from an absolute height that may not exist at this `U`.
            z_lo, z_hi = ci.z_extent(body_node.Shape)
            z_lo, z_hi = z_lo + ci.END_INSET_M, z_hi - ci.END_INSET_M
            notch_edges = ci.feature_stations(notch_compound(tools), z_lo, z_hi)
            body_features = ci.feature_stations(body_node.Shape, z_lo, z_hi)
            p_lo, p_hi = ci._patches(z_lo, z_hi, body_features)[0]
            union = sorted(set(ci._seed(p_lo, p_hi, True, True))
                           | {e for e in notch_edges if p_lo < e < p_hi})
            # `station_floor` is SI; the override arrives already converted from `--floor-mm`.
            floor_m = ci.station_floor(t_m) if floor_mm is None else si.m(float(floor_mm))
            kept = ci._thin_stations(union, floor_m)
            target, is_edge = target_station(kept, p_lo, p_hi, notch_edges, want_m=want_z_m)
            rec.update(target_z_mm=si.mm(target), target_is_notch_edge=is_edge,
                       floor_mm=si.mm(floor_m), seeded_stations=len(union),
                       kept_stations=len(kept))
            # `station_floor_m`, because the seam is SI: `cowl_interior._probe_floor` hands it a
            # meter default and uses whatever comes back (IP-FC-163).
            probe = wm_probe.Probe(contour=probe_for(delta, target, normals),
                                   station_floor_m=(None if floor_mm is None
                                                    else si.m(float(floor_mm))),
                                   dilate=_dilation(dilate))
            rec['dilate'] = dilate
            # `notches` is read for its vertices by `feature_stations`, so it must be one shape.
            # Handing over the list `pieces()` returns raises `'list' object has no attribute
            # 'Vertexes'` -- after the tree has already been built, so the cost is paid first.
            #
            # **The probe is installed around the build, not passed into it.** `shell_solid` takes
            # no measurement argument; `wall_measure.probe.installed` sets the seam and removes it
            # on the way out whether this succeeds or raises, so a dose that fails cannot leave
            # the next one perturbed.
            with wm_probe.installed(ci, probe=probe):
                wall = ci.shell_solid(cell_cut.Shape, body_node.Shape, notch_compound(tools),
                                      t_m, overhang_rad, mirrors, report=report)
            w_lo, w_hi = ci.z_extent(wall)
            s_lo, s_hi = w_lo + ci.END_INSET_M, w_hi - ci.END_INSET_M
            cont, broken, unread, worst, detail = ring_states(wall, s_lo, s_hi)
            rec.update(outcome='built', solids=len(wall.Solids), volume=wall.Volume,
                       partition_slip=report.get('partition_slip'),
                       # `rib_residue_m3` is the key `cavity` writes since IP-FC-163; reading
                       # `rib_residue` returned None on every build, so the column was blank.
                       rib_residue_mm3=(None if report.get('rib_residue_m3') is None
                                        else report['rib_residue_m3'] * si.MM3_PER_M3),
                       annulus=cont, broken=broken, unreadable=unread,
                       worst_station=worst, stations=detail,
                       scan_mm=si.mm(SCAN_M), scan_stations=len(detail),
                       scan_z=[s_lo, s_hi],
                       incumbent_at_break=thickness_at(wall, BREAK_Z_M, t_m),
                       moved_row=_moved(probe))
            flag = ''
            if delta == 0.0:
                rec['shape_path'] = _save_wall(wall, out_dir, kind, u, delta)
            # Every built dose's cavity is kept, not only the control's: a rib-cut detector is
            # qualified against both (IP-FC-169), the dosed one being the case IP-FC-146 is
            # about, and the wall alone cannot be turned back into either. About 4 MB each.
            if report.get('cavity_shape') is not None:
                rec['cavity_path'] = _save_wall(report['cavity_shape'], out_dir,
                                                kind + '_cavity', u, delta)
            if broken:
                flag = '   RING BROKEN'
                # **Measured here, on the wall already in memory.** Recovering this later would
                # cost another full build at this `U`, which is exactly what happened to the
                # 2026-10-04 severance: reproduced, then discarded unmeasured.
                extents = break_extent(wall, detail)
                rec['break_extent'] = extents
                for span in extents:
                    print('          break over %.3f mm, z %.4f to %.4f, up to %s arc(s)%s'
                          % (si.mm(span['extent_m']), si.mm(span['z_lo_m']),
                             si.mm(span['z_hi_m']),
                             span['max_faces'],
                             ' (reaches the scan end)' if span['reaches_scan_end'] else ''))
                rec['shape_path'] = _save_wall(wall, out_dir, kind, u, delta)
                print('          wall saved to %s' % os.path.basename(rec['shape_path']))
            inc = rec['incumbent_at_break'] or {}
            if inc.get('refused'):
                # The external check refusing is the headline, not a missing number: it refuses
                # exactly when the section is not an annulus, which is what it failed to notice
                # when this question was first characterized.
                at_break = 'REFUSED'
            elif inc.get('error'):
                at_break = 'error'
            else:
                # Millimeters, like the banner this column is read against: `worst_low` is
                # the incumbent's own meters, and printed raw a healthy 0.000547 sat beside a
                # stated 0.546556 mm and read as a thousandfold collapse.
                at_break = '%.6f' % si.mm(inc.get('worst_low', float('nan')))
            print('   %6.3f   %-13s %6d  %-9s  %-8s  %6d  %6d  %-9s %4.0f%s'
                  % (delta, 'built', len(wall.Solids),
                     '%.3e' % report['partition_slip'] if 'partition_slip' in report else '--',
                     ('%.4f' % (report['rib_residue_m3'] * si.MM3_PER_M3)
                      if 'rib_residue_m3' in report else '--'),
                     cont, broken, at_break, time.time() - at, flag))
        except (ci.Unconverged, ci.PreconditionFailed) as exc:
            rec.update(outcome=type(exc).__name__, error=str(exc)[:400],
                       moved_row=_moved(probe))
            print('   %6.3f   %-13s %s  (%.0f s)'
                  % (delta, type(exc).__name__, str(exc)[:46], time.time() - at))
            # **The shape the refusal was measured on, written before the document closes.**
            # A refusal used to carry only a sentence, so the geometry behind a 0.0001 mm
            # reading was destroyed with the exception and recovering it cost a second build of
            # the same dose. This runs inside the `except` and before the `finally` below, which
            # is the only window where the shape is still valid. `wall_measure.refusals` never
            # raises, deliberately: a failed write must not replace the refusal it was recording.
            # `delta` is millimeters here -- it is what `delta_mm` in the record is set from --
            # and `save` takes meters, so it converts at this call rather than anywhere inside.
            # Until 2026-11-13 this passed `delta=`, which `save` has never had: the keyword was
            # `delta_m` after IP-FC-163 and the call was not moved with it. That raised
            # `TypeError` *inside this except block*, replacing the refusal being diagnosed with
            # a failure to diagnose it -- the one outcome `wall_measure.refusals` is written to
            # prevent, reached by the call site instead of by the module.
            kept = wm_refusals.save(exc, out_dir, kind, u, _export_brep,
                                    delta_m=si.m(delta))
            rec['rounds'] = _rounds(exc)
            if kept is not None:
                rec['refusal_artifact'] = kept
                if kept.get('error'):
                    print('          refusal shape NOT saved: %s' % kept['error'])
                else:
                    print('          refusal shape saved to %s%s'
                          % (os.path.basename(kept['path']),
                             '' if 'bytes' not in kept
                             else ' (%.1f MB)' % (kept['bytes'] / 1048576.0)))
        except Exception as exc:                                  # noqa: BLE001
            # **The whole traceback, not its last 600 characters.** The tail holds the
            # frame that raised; the cause is usually further up, in which call produced
            # the operand. Measured 2026-11-13: a `Null shape` from the OML blank showed
            # three frames and none of the ones that would say which build asked for it,
            # in a file whose only purpose is to be read afterwards and where size costs
            # nothing.
            rec.update(outcome='error', error=traceback.format_exc(),
                       moved_row=_moved(probe))
            print('   %6.3f   %-13s %s  (%.0f s)'
                  % (delta, 'ERROR', str(exc)[:46], time.time() - at))
        finally:
            if doc is not None:
                App.closeDocument(doc.Name)
        rec['seconds'] = time.time() - at
        records.append(rec)
        # Written after every dose, not at the end: a run this long must not lose the doses it
        # already paid for if a later one takes the process down.
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        stem = os.path.join(out_dir, '%s_U%g' % (kind, u))
        with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
            # `historic_z`, not `target_z`: the station actually displaced is per dose, and a
            # top-level `target_z` holding the historical constant reads as though the run had
            # displaced it. At `U` = 3.0 it displaced z = -165.0433 while this said -283.9951339.
            fh.write(json.dumps({'kind': kind, 'u': float(u),
                                 'historic_z_mm': si.mm(HISTORIC_Z_M),
                                 'scan_mm': si.mm(SCAN_M),
                                 'doses': records}, indent=1, sort_keys=True, default=float))

    print('')
    print('  wrote %s.json in %.0f s total' % (stem, time.time() - started))
    return records


def main():
    doses = _opt('doses')
    doses = tuple(float(d) for d in doses.split(',')) if doses else DOSES
    floor = _opt('floor')
    target = _opt('target')
    run(_opt('kind', 'tail_shell'), float(_opt('u', '0.5')), doses,
        os.path.normpath(_opt('out-dir', OUT_DIR)),
        floor_mm=None if floor is None else float(floor),
        # `--target` is millimeters, like `--floor` and like every z this harness prints;
        # `target_station` compares against the SI station set, so it converts here.
        want_z_m=None if target is None else si.m(float(target)),
        dilate=_opt('dilate'))


if is_entry_point(__name__):
    main()
