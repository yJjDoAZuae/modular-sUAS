"""IP-FC-117: one instrumented build of one cowl shell at one `U`, for the reproducibility soak.

    freecadcmd soak_cowl_shell.py --pass --kind=tail_shell --pass --u=1.0 \
                                  --pass --out=DIR --pass --repeat=0

**This builds and records one variant; it does not judge it.** The criterion this row is held
to is [OQ-ARCH-19](../../../doc/architecture/freecad_migration.md)'s, decided 2026-09-06 and
implemented under IP-FC-124, and it is **pairwise**: two builds are screened with
`mesh_stats.canonical_hash`, and where the hash does not fire the difference is adjudicated
against `XOR / (A * 100U)` <= 1.0e-6 and `max surface gap / (100U)` <= 5.0e-5. A pairwise
criterion cannot be evaluated in a process that holds one build, and the spread being
characterised was found *between* processes, so it must not be. This script therefore emits a
hash and keeps the wall as a BREP; `soak_compare.py` does the judging afterwards.

**Builds directly against `cowl_tree`'s own parameter rows**, `PARAMS_TAIL_SHELL` /
`PARAMS_NOSE_COWL_SHELL`, with only the `U` row's literal replaced -- the same construction
`check_cowl_interior.py` uses, not the real sweep's seeded overlay path. This item's own
investigation already showed the two agree on every key the render records: the body, the
per-station pipeline, the fitted surface's poles, that surface sectioned, and that surface
closed as a solid are each bit-identical over four trials. Going through the nose/tail CSV
sweep for six `U` values would multiply the wiring (a fresh `derived_cowl_parameters` call,
the real `.stl.json` definition format, the render queue) without buying this item anything
it does not already have from the simpler path.

Prints exactly one line to stdout, prefixed so the driver can find it among `cowl_tree`'s own
build notes:

    SOAK_RESULT {"kind": ..., "u": ..., "solids": ..., "stations": ...,
                 "missing_stations": ..., "worst_wall_error": ..., "worst_rib_error": ...,
                 "partition_slip": ..., "wall_hash": ..., "brep": ...,
                 "wall_volume": ..., "volume_reliable": ..., "build_s": ..., "measure_s": ...}

or, if a build itself is what has to be reported:

    SOAK_ERROR {"kind": ..., "u": ..., "error": "..."}

**Volume is a fixed-deflection tessellation, never `Shape.Volume`** (IP-FC-119): this
project's B-spline solids report `Shape.Volume` wrong by 0.16 to 0.24%, the same order as the
spread this soak exists to characterise, so the wrong instrument would be measuring itself.

**Not `solid_measure.converged_volume`, though -- measured and rejected for this soak,
2026-09-11.** The adaptive search ran to its finest rung (0.00025 mm) on the nose at `U` =
0.5, this soak's cheapest case, and took 787 s to do it -- against 28 builds including the
much larger tail at `U` = 4, that is many hours of measurement the soak was not sized for
and does not need: it exists to compare repeats against each other, not to pin down any one
build's absolute volume to its own convergence floor. `mesh_volume` at one fixed deflection
(`VOLUME_DEFLECTION`, `solid_measure.DEFLECTIONS`'s third rung) is still refined-tessellation
volume and still not `Shape.Volume`; every build paying the same discretisation error is what
makes the *comparison* meaningful; it does not have to be a converged one.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# `mesh_stats` lives on the driver side but imports cleanly under freecadcmd -- checked, its
# numpy is present -- and `canonical_hash` is the screen OQ-ARCH-19 decided on, so it is worth
# reaching across for rather than reimplementing on this side.
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', 'tools')))

import FreeCAD as App
import Part

import check_cowl_interior as cci
import cowl_tree
import mesh_stats
import solid_measure
from corner_common import is_entry_point

BUILDERS = {'tail_shell': cowl_tree.tail_shell, 'nose_cowl_shell': cowl_tree.nose_cowl_shell}
BASE_PARAMS = {'tail_shell': cowl_tree.PARAMS_TAIL_SHELL,
              'nose_cowl_shell': cowl_tree.PARAMS_NOSE_COWL_SHELL}

#: The deflection every build in the soak is measured at -- `solid_measure.DEFLECTIONS`'s
#: third rung, the one its own module comment says the tail wall "converges by" in the
#: adaptive search. Fixed rather than adaptive: see the comment at the `mesh_volume` call.
VOLUME_DEFLECTION = 0.001


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    if default is None:
        raise SystemExit('missing --%s=' % name)
    return default


def with_u(params, u):
    """A copy of a cowl kind's own `PARAMS` with the `U` row's literal replaced.

    Every other row keeps the module's own reference value, which `build_sheet` already
    treats as a legitimate configuration (the no-seed path, "the reference check, where the
    literals are the configuration being measured"). Only `U` varies here.
    """
    out = []
    found = False
    for alias, value in params:
        if alias == 'U':
            out.append((alias, repr(float(u))))
            found = True
        else:
            out.append((alias, value))
    if not found:
        raise ValueError('%r has no U row' % (params,))
    return out


def measure(kind, u):
    params = with_u(BASE_PARAMS[kind], u)

    t0 = time.time()
    doc = App.newDocument('soak')
    tip = cowl_tree.emit(doc, None, params, BUILDERS[kind])
    doc.recompute()
    build_s = time.time() - t0

    # **Checked explicitly, not inferred from a Python exception.** A construction failure
    # inside a `Part::FeaturePython`'s `execute()` -- found at `U` = 0.5 on the tail,
    # 2026-09-11: the first rib cut left 5540.9 mm3 of residue, 550000x `RIB_RESIDUE`, the
    # retry cut then raised `ValueError: Null shape`, and `doc.recompute()` swallowed that
    # into an empty `tip.Shape` rather than propagating it -- does not raise here. Left
    # unchecked, every station and rib measurement below silently reads an empty shape and
    # this soak's first real run recorded it as a normal-looking result: `solids=0`,
    # every error metric `0.0`, indistinguishable at a glance from a wall that is merely very
    # thin. Caught here and reported as the failure it is.
    if not tip.Shape.Solids:
        raise ValueError(
            'the wall has no solids -- the construction failed inside execute() and '
            'doc.recompute() swallowed whatever it raised. Check the freecadcmd log above '
            'this result for the real traceback.')

    t1 = time.time()
    wall = tip.Shape
    body = tip.Body.Shape
    t = tip.Inset
    t_cut = float(doc.getObject('Params').get('buttress_cut_thickness'))

    lo, hi = cci.ci.z_extent(body)
    lo, hi = lo + 1.0, hi - 1.0
    stations = cci.STATIONS
    worst_wall_error = 0.0
    #: **Counted, not silently skipped.** `wall_thickness` returns `None` at a station with
    #: fewer than two loops -- no wall there at all -- and `check_cowl_interior.main` counts
    #: that as a failure (`bad += 1`). This soak's first draft did `continue` instead, which
    #: means a build missing its wall over *most* of its length could still report a small
    #: `worst_wall_error`, since only the stations that found wall material contribute to it.
    missing_stations = 0
    for i in range(stations):
        z = lo + (hi - lo) * i / float(stations - 1)
        got = cci.wall_thickness(wall, z, t, cci.ci.TAU)
        if got is None:
            missing_stations += 1
            continue
        _n, _near, lowv, _med, _highv = got
        worst_wall_error = max(worst_wall_error, max(0.0, t - lowv))

    shapes = [n.Shape for n in tip.Notches]
    for text in tip.Mirrors:
        normal = App.Vector(*[float(v) for v in text.split(',')])
        normal.normalize()
        shapes = shapes + [s.mirror(App.Vector(0, 0, 0), normal) for s in shapes]
    notches = Part.makeCompound(shapes)
    worst_rib_error = 0.0
    for i in range(3):
        z = lo + (hi - lo) * (i + 1) / 4.0
        pairs = cci.rib_gap(body, notches, z, t, t_cut)
        if not pairs:
            continue
        worst_rib_error = max(worst_rib_error,
                              max(abs(gap - (width + 2.0 * t)) for width, gap in pairs))

    # **A fixed deflection, not `converged_volume`'s adaptive search.** Measured on the nose
    # at U = 0.5, the cheapest case in this soak: the whole measure phase took 787 s, of
    # which the search was ~712 s -- it ran every rung down to the finest (0.00025 mm) before
    # settling. The same phase at one fixed deflection is 75 s. Across 28 builds including
    # the far larger tail at U = 4, that difference is hours the soak does not need to spend:
    # it exists to compare repeats against each other, not to pin any one build to its own
    # convergence floor. `mesh_volume` at one fixed deflection is still refined-tessellation
    # volume and still not `Shape.Volume`; every build paying the *same* discretisation error
    # is what makes the comparison mean something.
    #
    # **Closure checked, not assumed -- found necessary 2026-09-11.** `mesh_volume`'s own
    # docstring in `solid_measure.py` says it plainly: "An open mesh still returns a number
    # ... and it is wrong by however much the hole subtends," and "nothing else here checks
    # for one." The first real soak run proved that is not a theoretical caveat: at `U` >= 2
    # the fixed 0.001 mm tessellation came back with 1200-1400 unpaired edges on five
    # separate builds, and every one of those five reported a volume wrong by two to four
    # orders of magnitude -- 80.5 mm3 for a wall that measures ~38987 by every other check,
    # 2 060 850 mm3 for one that a clean tessellation of an identical build puts at ~156 468.
    # Every reading with zero unpaired edges was sane. The wall-thickness and rib-gap checks
    # on those same shapes read completely normally, which is why they are trusted above and
    # this one needs its own guard.
    #
    # **Refining an open tessellation does not close it -- measured 2026-09-11, and the
    # retry that used to be here is gone.** The obvious reflex when the mesh comes back open
    # is to ask for a finer one. On the nose at `U` = 4 that took the unpaired-edge count
    # from 1372 at 0.001 mm to **12320 at 0.00025 mm**, about ten times worse, and the volume
    # with it: 6 236 187 mm3 where a clean tessellation of the same variant reads ~156 468.
    # It is not mysterious in hindsight -- a finer mesh has more facets and therefore more
    # places to leave a gap -- but it is the opposite of what refinement is assumed to do,
    # and it cost 941 s of measurement against 75-170 s for the single pass. So there is one
    # pass, and `volume_reliable` carries the weight: a reading whose mesh is open is
    # reported as unreliable rather than retried into a worse one, silently trusted, or
    # dropped. What actually clears it is a different *build* -- the same variant built again
    # tessellates closed often enough that repeats can be compared -- which is a property of
    # this soak's own design rather than something to chase inside one build.
    volume, facets = solid_measure.mesh_volume(wall, VOLUME_DEFLECTION)
    deflection = VOLUME_DEFLECTION
    _points, _tess_facets, open_edge_count = solid_measure.open_edges(wall, VOLUME_DEFLECTION)

    # **The screen OQ-ARCH-19 decided on, and the reason it comes before any tolerance.**
    # Equal hashes mean the same set of triangles and therefore the same geometry exactly;
    # the errors run one way only, so it can cost a closer look but never miss a change. It
    # reuses the tessellation `mesh_volume` just built -- same deflection, handed straight
    # back -- so the only new cost is the hashing pass itself. Unaffected by the open-mesh
    # defect above: a gap changes the triangle set, which is a difference the hash is
    # supposed to report, not an integral it can silently corrupt.
    tris = [[(verts[i].x, verts[i].y, verts[i].z),
             (verts[j].x, verts[j].y, verts[j].z),
             (verts[k].x, verts[k].y, verts[k].z)]
            for verts, facet_list in [wall.tessellate(VOLUME_DEFLECTION)]
            for i, j, k in facet_list]
    wall_hash = mesh_stats.canonical_hash(tris)

    # **The wall is kept, because the criterion is pairwise and this process only has one
    # build.** The spread this soak exists to characterise was found *between* processes, so
    # repeats cannot be compared in one; they are compared afterwards, by `soak_compare.py`,
    # which needs the shapes. BREP rather than `.FCStd`: it is the shape alone, and a round
    # trip through it was checked to preserve the canonical hash exactly.
    brep_path = None
    out_dir = _opt('out', '')
    if out_dir:
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        brep_path = os.path.join(out_dir, '%s_U%s_r%s.brep' % (kind, u, _opt('repeat', '0')))
        wall.exportBrep(brep_path)

    measure_s = time.time() - t1

    return {
        # `repeat` is carried here as well as being set by the driver, so a record produced by
        # running this script directly is still usable by `soak_compare.py`.
        'kind': kind, 'u': u, 'repeat': _opt('repeat', '0'),
        'solids': len(wall.Solids),
        'stations': stations,
        'missing_stations': missing_stations,
        'worst_wall_error': worst_wall_error,
        'worst_rib_error': worst_rib_error,
        'partition_slip': tip.PartitionSlip,
        'wall_hash': wall_hash,
        'brep': brep_path,
        # **Diagnostic, not the criterion.** OQ-ARCH-19 set an absolute volume aside for this
        # question after measuring that a difference of totals understates build-to-build
        # disagreement by 260x. Kept because it is free here and because a volume is still
        # good at judging a difference already known to exist -- never as the answer.
        'wall_volume': volume,
        'volume_reliable': open_edge_count == 0,
        'volume_deflection': deflection,
        'volume_facets': facets,
        'open_edge_count': open_edge_count,
        'build_s': build_s,
        'measure_s': measure_s,
    }


def main():
    kind = _opt('kind')
    u = float(_opt('u'))
    if kind not in BUILDERS:
        raise SystemExit('unknown kind %r -- tail_shell or nose_cowl_shell' % kind)

    try:
        record = measure(kind, u)
    except Exception as exc:                                            # noqa: BLE001
        print('SOAK_ERROR ' + json.dumps({'kind': kind, 'u': u,
                                          'error': '%s: %s' % (type(exc).__name__, exc)}))
        sys.stdout.flush()
        return 1

    print('SOAK_RESULT ' + json.dumps(record))
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
