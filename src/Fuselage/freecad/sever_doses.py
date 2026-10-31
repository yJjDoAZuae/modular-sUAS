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
50 mm against 300 mm. The scan adds roughly 7 s a station, and the station count follows `SCAN_MM`,
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
#: once already (`cowl_interior_surface.md` §6.1, sixth caution).
HISTORIC_Z = -283.9951339

#: Spans the reported bracket -- benign at 0.01, severed at 0.03 -- with the ends that are recorded
#: as caught, so a run reproduces both the silent and the loud case if either is reachable.
#:
#: **Ordered by what it answers, not by magnitude**, because a dose costs a full build and the JSON
#: is written after each one: the control first, then 0.03 where the silent severance is reported,
#: so an interrupted run has already answered "does it sever at the reported magnitude" rather than
#: having spent the time walking up to it. `inputs.cases` orders its own excursions the same way
#: and for the same reason.
DOSES = (0.0, 0.03, 0.01, 0.02, 0.05, 0.1)

#: **Axial scan spacing, in millimeters -- not a station count.** A count is the mistake this
#: project has made in a published figure already: the cowl's length scales with `U` and the wall it
#: builds does not, so 24 stations is 2.1 mm apart on a 50 mm `U` = 0.5 tail and **12.5 mm apart on
#: a 300 mm `U` = 3.0 one**. The break whose axial extent nobody has measured would have to be
#: longer than the spacing to be seen at all, so holding the spacing is what makes two `U` values
#: comparable. `wall_vanish` scans at the same 2.0 mm.
SCAN_MM = 2.0

#: The station floor, the ceiling and the refinement tolerance come from the library module rather
#: than being restated here, so there is one source for them. 24 stations is the floor however short
#: the part; 400 is the ceiling, which at 2.0 mm binds above a 600 mm part and leaves a `U` = 3.0
#: tail's 150 well inside; 0.25 mm is what an end is resolved to, about three slices an end.
MIN_STATIONS = rb.MIN_STATIONS
MAX_STATIONS = rb.MAX_STATIONS
EXTENT_TOL = rb.EXTENT_TOL


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def ring_state_at(wall, z):
    """The annulus identity at one station: `(state, faces, wires, area)`.

    `state` is `'annulus'`, `'broken'` or `'unreadable'`. Factored out of `ring_states` so
    `break_extent` can bisect with exactly the classification the scan used -- a refinement that
    asked the question a second way would be measuring a different quantity.
    """
    wires = [w for w in ci._slice_wires(wall, z) if w.isClosed()]
    got = cci.section_regions(wires)
    if got is None:
        return 'unreadable', None, None, None
    faces, wire_counts, area = got
    if faces == 1 and wire_counts == [2]:
        return 'annulus', faces, wire_counts, area
    return 'broken', faces, wire_counts, area


def ring_states(wall, z_lo, z_hi, stations=None, scan_mm=SCAN_MM):
    """The annulus identity at each station: `(continuous, broken, unreadable, worst, detail)`.

    `worst` names the station with the most arcs, which is where to look first. A station whose
    section will not form a face at all is counted `unreadable` and never folded into either of the
    other two, since "the maker refused" and "the ring is broken" are different answers.

    `stations` defaults to whatever `scan_mm` spacing requires over this span, so the sampling is a
    spacing and not a count -- see `SCAN_MM`.
    """
    if stations is None:
        stations = rb.station_count(z_lo, z_hi, scan_mm, MIN_STATIONS, MAX_STATIONS)
    continuous, broken, unreadable, worst = 0, 0, 0, None
    detail = []
    for z in rb.scan_grid(z_lo, z_hi, stations):
        state, faces, wire_counts, area = ring_state_at(wall, z)
        if state == 'unreadable':
            unreadable += 1
            detail.append({'z': z, 'state': 'unreadable'})
        elif state == 'annulus':
            continuous += 1
            detail.append({'z': z, 'state': 'annulus', 'area': area})
        else:
            broken += 1
            detail.append({'z': z, 'state': 'broken', 'faces': faces,
                           'wires': wire_counts, 'area': area})
            if worst is None or faces > worst[1]:
                worst = (z, faces)
    return continuous, broken, unreadable, worst, detail


def break_extent(wall, detail, tol=EXTENT_TOL):
    """Each run of broken stations, with its axial ends refined off the scan grid.

    The run-finding and the bisection are `wall_measure.ring_breaks`, which takes the classifier as
    an argument so the logic is testable against a synthetic break of **known** extent -- the one
    test real geometry cannot provide, since the extent is the unknown. This function is only the
    part that needs the kernel: classifying a real section.

    It runs on the wall already in memory, which is the point: the 2026-10-04 severance was
    reproduced and its shape discarded, so recovering the figure now would cost another full build
    at the `U` it happened on.
    """
    grid = [item['z'] for item in detail]
    states = [item['state'] for item in detail]
    found = rb.extents(lambda z: ring_state_at(wall, z)[0], grid, states, tol)
    faces = dict((item['z'], item.get('faces')) for item in detail)
    for span in found:
        first, last = span['broken_stations_z']
        inside = [faces.get(z) or 0 for z in grid if first <= z <= last]
        span['max_faces'] = max(inside) if inside else None
    return found


#: The station OQ-DES-CW26 measured the broken ring at, 66 mm from the row it displaced. Read
#: here as well as scanned, so a result can be set against the 0.355705 mm on record directly.
BREAK_Z = -217.7261

#: What the healthy wall reads at `BREAK_Z`, reproduced to six decimals across five fresh builds
#: and two independently fitted station sets, and 0.546559 mm on IP-FC-144's own set.
HEALTHY_MM = 0.546556

#: What the silent failure read there: not a thickness at all, but the gap between the two broken
#: ends, which `wall_thickness` cannot distinguish from a thickness (section 7.1).
SILENT_MM = 0.355705


def target_station(kept, z_lo, z_hi, notch_edges, want=None, tol=1.0e-6):
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

    **`want` names an exact station instead, and raises rather than substituting a near one.**
    Recreating OQ-DES-CW26's own result means displacing the row it displaced, and a target chosen
    as "nearest to" a height that is not in the set is how this harness produced a null result
    once already: at `U` = 0.5 it collapsed onto the patch's pinned first station. So an exact
    request that the station set cannot satisfy is an error, and the error names the nearest
    station and its distance, because that is the diagnosis -- a station absent at this floor is
    the finding, not a reason to move the probe somewhere else.
    """
    interior = [z for z in kept[1:-1]]
    if not interior:
        raise ci.PreconditionFailed('the patch has no interior station to displace')
    if want is not None:
        exact = [z for z in interior if abs(z - want) <= tol]
        if not exact:
            near = min(kept, key=lambda z: abs(z - want))
            raise ci.PreconditionFailed(
                'no interior station at z = %.7f in this set of %d; the nearest is %.7f, '
                '%.7f mm away. At the production floor that station is thinned away -- pass '
                '--floor=0 to seed the unfiltered union it belongs to.'
                % (want, len(kept), near, abs(near - want)))
        return exact[0], any(abs(exact[0] - e) <= tol for e in notch_edges)
    edges = [z for z in interior
             if any(abs(z - e) <= 1.0e-6 for e in notch_edges)]
    pool = edges or interior
    middle = 0.5 * (z_lo + z_hi)
    return min(pool, key=lambda z: abs(z - middle)), bool(edges)


def probe_for(delta, target_z, normals, tol=1.0e-6):
    """A contour hook that nudges the station at `target_z` by `delta` mm, radially.

    Applied to the eroded contour as `cavity` builds it, so every row the construction makes --
    including the ones section 5's second pass inserts after the rib cut -- carries the
    perturbation.

    **Counting is `wall_measure.probe.Probe`'s job, not this function's.** This used to carry its
    own `moved` dict; the probe object counts every row it actually transformed and records each
    `z`, so the evidence that something moved comes from the one place that can see it. Returning
    `pts` unchanged is how this hook declines a row, and the probe does not count those.
    """

    def hook(z, pts):
        if delta == 0.0 or abs(z - target_z) > tol:
            return pts
        # **Radial from the origin, not from the arc's centroid.** Every cell boundary plane
        # passes through the origin and contains the part's axis, so a ray from (0, 0) lies in
        # those planes and a point on one stays on it. The centroid default does not: on a real
        # tail row it sits near (-3.5, 13.0), which lifts the arc's two ends off the construction
        # plane and makes `_side_caps` fail with `Failed to create face from wire` -- measured,
        # identically at every magnitude, after the build was already paid for.
        out = fr.nudge(pts, delta, center=(0.0, 0.0))
        if not fr.plane_ends_held([(z, pts)], [(z, out)], normals):
            raise ci.PreconditionFailed(
                'the nudge moved a row end off its construction plane, so the patch could not '
                'be closed. The displacement must be radial from the axis; see '
                'fit_response.nudge.')
        return out

    return hook


def _moved(probe):
    """What a probe actually did, for the record. `None` when there was no probe at all."""
    if probe is None:
        return None
    return {'calls': probe.calls,
            'station': probe.stations[-1] if probe.stations else None,
            'distinct_stations': sorted(set(probe.stations))}


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


def thickness_at(wall, z, t):
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
        got = cci.wall_thickness(wall, z, t, ci.WALL_TOL)
    except Exception as exc:                                      # noqa: BLE001
        return {'error': '%s: %s' % (type(exc).__name__, str(exc)[:160])}
    if got is None:
        return {'refused': True}
    n, near, worst_low, median, worst_high = got
    return {'refused': False, 'samples': n, 'within_tol': near,
            'worst_low': worst_low, 'median': median, 'worst_high': worst_high}


def run(kind, u, doses, out_dir, floor_mm=None, want_z=None):
    started = time.time()
    print('')
    print('%s at U = %g: the booleans after the fit, under a row displacement.' % (kind, u))
    # **Not `HISTORIC_Z`.** An earlier version printed that constant here and called it the target,
    # which is wrong twice: `target_station` chooses an interior notch edge nearest the middle of
    # the patch, and at `U` = 3.0 the historical station is one the floor drops. A header naming a
    # station the run does not displace is the kind of figure that gets quoted. The station is
    # chosen per dose, from that dose's own station set, and printed in the table below.
    print('  the station displaced is chosen per dose: an interior notch edge, never a patch end')
    print('  (OQ-DES-CW26 produced its failure at z = %.7f, which the station floor now drops)'
          % HISTORIC_Z)
    print('')
    if floor_mm is not None:
        print('  station floor overridden to %.3f mm -- the unfiltered union, '
              'which is the pre-IP-FC-144 station set' % float(floor_mm))
    if want_z is not None:
        print('  displacing z = %.7f exactly; an absent station is an error, not a substitution'
              % want_z)
    print('  incumbent reading taken at z = %.4f, where the healthy wall reads %.6f mm and the '
          'silent failure read %.6f' % (BREAK_Z, HEALTHY_MM, SILENT_MM))
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
            t = float(params.get('cowl_n_perimeters')) * float(params.get('extrusion_width'))
            overhang = float(params.get('overhang_angle_from_bed'))
            # The planes the nudge has to respect, read off the cell itself rather than assumed
            # from the mirror chain -- the same source `cavity` uses.
            normals = [(p.x, p.y) for p in ci.cell_boundary_planes(body_node.Shape)]
            # The station set `cavity` will derive, computed here so the target can be chosen
            # from it rather than from an absolute height that may not exist at this `U`.
            z_lo, z_hi = ci.z_extent(body_node.Shape)
            z_lo, z_hi = z_lo + ci.END_INSET, z_hi - ci.END_INSET
            notch_edges = ci.feature_stations(notch_compound(tools), z_lo, z_hi)
            body_features = ci.feature_stations(body_node.Shape, z_lo, z_hi)
            p_lo, p_hi = ci._patches(z_lo, z_hi, body_features)[0]
            union = sorted(set(ci._seed(p_lo, p_hi, True, True))
                           | {e for e in notch_edges if p_lo < e < p_hi})
            floor = ci.station_floor(t) if floor_mm is None else float(floor_mm)
            kept = ci._thin_stations(union, floor)
            target, is_edge = target_station(kept, p_lo, p_hi, notch_edges, want=want_z)
            rec.update(target_z=target, target_is_notch_edge=is_edge,
                       floor_mm=floor, seeded_stations=len(union),
                       kept_stations=len(kept))
            probe = wm_probe.Probe(contour=probe_for(delta, target, normals),
                                   station_floor_mm=floor_mm)
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
                                      t, overhang, mirrors, report=report)
            w_lo, w_hi = ci.z_extent(wall)
            s_lo, s_hi = w_lo + ci.END_INSET, w_hi - ci.END_INSET
            cont, broken, unread, worst, detail = ring_states(wall, s_lo, s_hi)
            rec.update(outcome='built', solids=len(wall.Solids), volume=wall.Volume,
                       partition_slip=report.get('partition_slip'),
                       rib_residue=report.get('rib_residue'),
                       annulus=cont, broken=broken, unreadable=unread,
                       worst_station=worst, stations=detail,
                       scan_mm=SCAN_MM, scan_stations=len(detail),
                       scan_z=[s_lo, s_hi],
                       incumbent_at_break=thickness_at(wall, BREAK_Z, t),
                       moved_row=_moved(probe))
            flag = ''
            if delta == 0.0:
                rec['shape_path'] = _save_wall(wall, out_dir, kind, u, delta)
            if broken:
                flag = '   RING BROKEN'
                # **Measured here, on the wall already in memory.** Recovering this later would
                # cost another full build at this `U`, which is exactly what happened to the
                # 2026-10-04 severance: reproduced, then discarded unmeasured.
                extents = break_extent(wall, detail)
                rec['break_extent'] = extents
                for span in extents:
                    print('          break over %.3f mm, z %.4f to %.4f, up to %s arc(s)%s'
                          % (span['extent_mm'], span['z_lo'], span['z_hi'],
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
                at_break = '%.6f' % inc.get('worst_low', float('nan'))
            print('   %6.3f   %-13s %6d  %-9s  %-8s  %6d  %6d  %-9s %4.0f%s'
                  % (delta, 'built', len(wall.Solids),
                     '%.3e' % report['partition_slip'] if 'partition_slip' in report else '--',
                     '%.4f' % report['rib_residue'] if 'rib_residue' in report else '--',
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
            kept = wm_refusals.save(exc, out_dir, kind, u,
                                    lambda shape, path: shape.exportBrep(path), delta=delta)
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
            rec.update(outcome='error', error=traceback.format_exc()[-600:],
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
                                 'historic_z': HISTORIC_Z, 'scan_mm': SCAN_MM,
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
        want_z=None if target is None else float(target))


if is_entry_point(__name__):
    main()
