"""How much wall held a strip on before a nudge tore it off: the healthy wall read at the seam.

**The question.** A 0.03 mm nudge at one station makes `notched.cut(inside)` return the wall in
three solids: the main body and two strips, 4349.3071 and 718.2009 mm3, that run the full 300 mm
(`cowl_interior_surface.md` section 7). The slots very nearly isolate those strips already, and the
nudge decides whether the last connection survives. **How thick is that last connection when
nothing is nudged?** If the healthy wall is already near zero there, the build sits on the edge of
failing and any small disturbance tips it. If it is the full wall `t`, the nudge is doing something
discrete -- a flip in the cut's topology -- and thinness is not the mechanism.

**The first answer replaced the question.** Measured 2026-11-15, the strips do not touch the main
body anywhere: the nearest approach at every station is a slot width (0.10 to 1.20 mm), and the
healthy wall at that point is full thickness. There is no thin torn connection. What there is, is
missing material -- the dosed cell wall is about 9430 mm3 lighter than the healthy one -- so the
tool now asks both questions, composed from production functions and nothing restated:

1. Rebuild the dosed wall's pieces from the refusal artifact with `refused_wall.finish`, stopping
   before the mirror (which refuses on this input and is not needed: the strips exist in the cell).
2. **What the nudge removed.** At each station, a 2D boolean of the healthy section (cell side,
   `y >= 0`) against the dosed one gives the regions present in one and not the other, with an
   accounting residue -- (healthy - dosed) - (removed - added) -- so a boolean that fails silently
   is seen rather than read as "nothing changed".
3. **Where each strip is nearest the main body.** Walking a strip's section outline, the sample
   nearest the main body's section and its distance; `wall_measure.contact.contact_runs` reports any
   stretch actually in contact. At that point the healthy wall is read: `Q` is the nearest point on
   the healthy outer loop, the wall is `Q`'s distance to the inner loop, and `|PQ|` is recorded so a
   point not on the exterior shows itself.

**In-plane, so a reading is an upper bound.** A plane cutting a slab inclined at angle theta reads
`thickness / cos theta` (OQ-DES-CW33). The x = -150 face is near-vertical, so the inflation there is
small, but a reading is never thinner than the wall is.

Run it as::

    freecadcmd strip_ligament.py --pass --brep=<refusal cavity .brep> \\
        --pass --healthy=<control wall .brep> --pass --kind=tail_shell --pass --u=3.0

One `--pass` per argument; `freecadcmd`'s exit code is unreliable, so read the report and JSON.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))

import FreeCAD as App                                                    # noqa: E402
import Part                                                              # noqa: E402

import check_cowl_interior as cci                                        # noqa: E402
import cowl_interior as ci                                               # noqa: E402
import cowl_tree                                                         # noqa: E402
import si                                                                # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from refused_wall import finish, load_brep, say                          # noqa: E402
from station_gaps import BUILDERS, PARAMS, notch_compound, with_u        # noqa: E402
from wall_measure.contact import contact_runs                            # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'strip_ligament')

#: Station spacing along a strip. 5 mm gives about 60 stations over the 300 mm part, which is enough
#: to see whether the healthy wall at the seam is uniform or thins somewhere.
STEP_M = 5.0e-3

#: Spacing of the samples along a strip's section outline.
SAMPLE_M = 1.0e-4

#: A sample this close to the main body's section is on the seam. The seam is where two pieces of
#: one cut parted, so the true distance there is zero; 2 microns allows for discretization only.
SEAM_TOL_M = 2.0e-6

#: Stations this close to a strip's own ends are skipped: its end faces lie on the part's end
#: planes, where a section is degenerate.
END_MARGIN_M = 5.0e-4


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def _compound_of_wires(wires):
    return Part.Compound(list(wires)) if wires else None


def _healthy_loops(wall, z_m):
    """`(outer, inner)` wires of the healthy wall's section at `z_m`, or `None` if not an annulus.

    Uses the same face maker `check_cowl_interior.section_regions` does, so "annulus" here means
    what it means to the ring scan.
    """
    wires = [w for w in ci._slice_wires(wall, z_m) if w.isClosed()]
    if not wires:
        return None
    try:
        built = Part.makeFace(wires, cci.FACE_MAKER)
    except Exception:                                                     # noqa: BLE001
        return None
    if len(built.Faces) != 1 or len(built.Faces[0].Wires) != 2:
        return None
    face = built.Faces[0]
    outer = face.OuterWire
    inner = [w for w in face.Wires if not w.isSame(outer)][0]
    return outer, inner


def seams_at(strip, main, z_m, sample_m=SAMPLE_M, tol_m=SEAM_TOL_M):
    """Where the strip's section is nearest the main body's at `z_m`.

    Returns `(nearest, seams)`. `nearest` is `{'point', 'gap_m'}` for the one sample closest to
    the main body -- always reported, because measured 2026-11-15 the strips do not touch the
    main body anywhere: they parted with a gap, and its width is part of the answer. `seams` are
    the runs within `tol_m`, if any. Points are kernel millimeters.
    """
    main_sec = _compound_of_wires(ci._slice_wires(main, z_m))
    if main_sec is None:
        return None, []
    nearest, seams = None, []
    for wire in ci._slice_wires(strip, z_m):
        n = max(8, int(wire.Length / si.mm(sample_m)))
        pts = wire.discretize(Number=n)
        dists_m = [si.m(Part.Vertex(p).distToShape(main_sec)[0]) for p in pts]
        k = min(range(len(pts)), key=lambda i: dists_m[i])
        if nearest is None or dists_m[k] < nearest['gap_m']:
            nearest = {'point': pts[k], 'gap_m': dists_m[k]}
        for first, last, mid in contact_runs(dists_m, tol_m, closed=wire.isClosed()):
            seams.append({'point': pts[mid], 'samples': (last - first) % len(pts) + 1,
                          'of': len(pts)})
    return nearest, seams


def healthy_reading(loops, p):
    """`(wall_m, offset_m)` of the healthy section at seam point `p`: the wall at the nearest
    exterior point, and how far `p` is from that exterior."""
    outer, inner = loops
    d_pq, pairs, _info = Part.Vertex(p).distToShape(outer)
    q = pairs[0][1]
    wall = Part.Vertex(q).distToShape(inner)[0]
    return si.m(wall), si.m(d_pq)


#: Section regions smaller than this are reported as a count, not individually. The nudge moves the
#: fitted interior slightly everywhere, so the healthy-minus-dosed difference carries a film of
#: slivers along the whole inner surface; what the strips lost is far larger than any of them.
REGION_MIN_M2 = 1.0e-6

#: A half-plane far larger than the part, used to keep the healthy wall's cell side (`y >= 0`).
HALF_PLANE_MM = 2000.0


def _section_face(shape, z_m):
    """The material region of `shape` at `z_m` as one planar shape, or `None`."""
    wires = [w for w in ci._slice_wires(shape, z_m) if w.isClosed()]
    if not wires:
        return None
    try:
        built = Part.makeFace(wires, cci.FACE_MAKER)
    except Exception:                                                     # noqa: BLE001
        return None
    return built if built.Faces else None


def interior_point(face, grid=40):
    """A point strictly inside a planar face, or `None`: the first grid point the face contains.

    A region's center of mass is not one -- measured 2026-11-15, the centers of the two slot-line
    regions lie outside the healthy wall altogether, since a rib joined to the wall is not convex.
    A containment test made at such a point says nothing about the region.
    """
    bb = face.BoundBox
    z = 0.5 * (bb.ZMin + bb.ZMax)
    best = None
    for i in range(1, grid):
        for j in range(1, grid):
            p = App.Vector(bb.XMin + bb.XLength * i / grid, bb.YMin + bb.YLength * j / grid, z)
            if face.isInside(p, 1.0e-6, False):
                d = face.OuterWire.distToShape(Part.Vertex(p))[0]
                if best is None or d > best[0]:
                    best = (d, p)
    return None if best is None else best[1]


def _regions(shape, min_m2=REGION_MIN_M2):
    """`(big, small_count, small_total_m2)`: each face of `shape` at least `min_m2`, as
    `{'area_mm2', 'center_mm', 'x_mm', 'y_mm'}`, and the count and total of the rest."""
    big, small_n, small_m2 = [], 0, 0.0
    for f in shape.Faces:
        a_m2 = si.area_m2(f)
        if a_m2 < min_m2:
            small_n += 1
            small_m2 += a_m2
            continue
        bb = f.BoundBox
        c = f.CenterOfMass
        q = interior_point(f)
        big.append({'area_mm2': f.Area, 'center_mm': [c.x, c.y],
                    'inside_mm': None if q is None else [q.x, q.y],
                    'x_mm': [bb.XMin, bb.XMax], 'y_mm': [bb.YMin, bb.YMax]})
    big.sort(key=lambda r: -r['area_mm2'])
    return big, small_n, small_m2


def removed_at(healthy, dosed, z_m):
    """What the healthy cell wall has at `z_m` that the dosed one does not, and the converse.

    A 2D boolean on the two sections, restricted to the cell side `y >= 0` because the healthy
    wall is mirrored and the dosed one is not. Returns `None` when either section is missing.
    """
    h = _section_face(healthy, z_m)
    d = _section_face(dosed, z_m)
    if h is None or d is None:
        return None
    z = si.mm(z_m)
    half = Part.makePlane(HALF_PLANE_MM, HALF_PLANE_MM, App.Vector(-HALF_PLANE_MM / 2, 0.0, z))
    h_cell = h.common(half)
    gone, gone_n, gone_small = _regions(h_cell.cut(d))
    extra, extra_n, extra_small = _regions(d.cut(h_cell))
    # **The accounting identity, so a boolean that fails silently is seen.** Measured
    # 2026-11-15: at z = -299.5 both differences came back empty while the two areas differed by
    # 103 mm2. Whatever the booleans return must account for the area difference, and the residue
    # is reported at every station rather than trusted.
    removed_mm2 = sum(r['area_mm2'] for r in gone) + si.mm(si.mm(gone_small))
    added_mm2 = sum(r['area_mm2'] for r in extra) + si.mm(si.mm(extra_small))
    unaccounted = (h_cell.Area - d.Area) - (removed_mm2 - added_mm2)
    return {'healthy_mm2': h_cell.Area, 'dosed_mm2': d.Area,
            'removed_mm2': removed_mm2, 'added_mm2': added_mm2,
            'unaccounted_mm2': unaccounted,
            'removed': gone, 'removed_slivers': gone_n,
            'removed_sliver_mm2': si.mm(si.mm(gone_small)),
            'added': extra, 'added_slivers': extra_n,
            'added_sliver_mm2': si.mm(si.mm(extra_small))}


def run(brep, healthy_path, kind, u, out_dir, step_m=STEP_M):
    started = time.time()
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    stem = os.path.join(out_dir, '%s_U%g' % (kind, u))
    rec = {'brep': brep, 'healthy': healthy_path, 'kind': kind, 'u': float(u),
           'step_mm': si.mm(step_m), 'seam_tol_mm': si.mm(SEAM_TOL_M), 'strips': []}

    def keep():
        rec['seconds'] = time.time() - started
        with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(rec, indent=1, sort_keys=True, default=float))

    say('')
    say('the healthy wall at the seams a nudge tears: %s' % os.path.basename(brep))
    doc = App.newDocument('strip_ligament')
    try:
        cowl_tree.emit(doc, None, with_u(PARAMS[kind], u), BUILDERS[kind])
        doc.recompute()
        body_node, _tools, _mirrors, cell_cut = cowl_tree.pieces(doc)
        params = doc.getObject('Params')
        t_m = si.m(float(params.get('cowl_n_perimeters')) * float(params.get('extrusion_width')))
        rec['t_mm'] = si.mm(t_m)
        say('  tree built in %.0f s; t = %.3f mm' % (time.time() - started, si.mm(t_m)))

        cavity = load_brep(brep)
        healthy = load_brep(healthy_path)
        rec['healthy_wall'] = {'volume_mm3': healthy.Volume, 'solids': len(healthy.Solids),
                               'valid': bool(healthy.isValid())}
        say('  healthy wall: %.4f mm3 in %d solid(s)' % (healthy.Volume, len(healthy.Solids)))

        wall, stages, _complete = finish(cavity, cell_cut.Shape, body_node.Shape, [])
        solids = sorted(wall.Solids, key=lambda s: -s.Volume)
        rec['dosed_pieces_mm3'] = [s.Volume for s in solids]
        say('  dosed cell wall: %s mm3' % ', '.join('%.4f' % s.Volume for s in solids))
        keep()
        if len(solids) < 2:
            say('  the dosed wall is one solid; there is no seam to read')
            return rec
        main = solids[0]

        # **What the nudge removed, station by station.** Measured 2026-11-15: the strips do not
        # touch the main body anywhere -- the nearest approach is a slot width -- and the dosed
        # cell wall is about 9430 mm3 lighter than the healthy one, so a thin torn connection is
        # not the picture. This reads the material itself.
        z_lo_m = si.m(wall.BoundBox.ZMin) + END_MARGIN_M
        z_hi_m = si.m(wall.BoundBox.ZMax) - END_MARGIN_M
        n_all = int((z_hi_m - z_lo_m) / step_m) + 1
        rec['removed'] = []
        say('')
        say('  what the nudge removed: %d stations' % n_all)
        say('       z mm   healthy mm2   dosed mm2   unaccounted   removed regions (mm2 at x, y mm)')
        for i in range(n_all):
            z_m = z_lo_m + i * (z_hi_m - z_lo_m) / max(1, n_all - 1)
            got = removed_at(healthy, wall, z_m)
            if got is None:
                rec['removed'].append({'z_mm': si.mm(z_m), 'section': 'missing'})
                say('  %9.3f   (a section is missing)' % si.mm(z_m))
                continue
            got['z_mm'] = si.mm(z_m)
            rec['removed'].append(got)
            text = ', '.join('%.3f at (%.1f, %.1f)' % (r['area_mm2'], r['center_mm'][0],
                                                         r['center_mm'][1])
                             for r in got['removed'][:4]) or '(none)'
            say('  %9.3f   %11.4f   %9.4f   %11.4f   %s'
                % (si.mm(z_m), got['healthy_mm2'], got['dosed_mm2'], got['unaccounted_mm2'],
                   text))
            keep()

        for k, strip in enumerate(solids[1:]):
            bb = strip.BoundBox
            lo_m = si.m(bb.ZMin) + END_MARGIN_M
            hi_m = si.m(bb.ZMax) - END_MARGIN_M
            n = int((hi_m - lo_m) / step_m) + 1
            entry = {'volume_mm3': strip.Volume, 'stations': []}
            rec['strips'].append(entry)
            say('')
            say('  strip %d, %.4f mm3: %d stations' % (k + 1, strip.Volume, n))
            say('       z mm   gap mm    at (x, y) mm          seams   healthy wall mm   '
                'to exterior mm')
            for i in range(n):
                z_m = lo_m + i * (hi_m - lo_m) / max(1, n - 1)
                nearest, seams = seams_at(strip, main, z_m)
                loops = _healthy_loops(healthy, z_m)
                row = {'z_mm': si.mm(z_m), 'seams': len(seams)}
                if loops is None:
                    row['healthy'] = 'not an annulus'
                if nearest is None:
                    entry['stations'].append(row)
                    say('  %9.3f   (no section)' % si.mm(z_m))
                    continue
                p = nearest['point']
                row.update({'gap_mm': si.mm(nearest['gap_m']), 'x_mm': p.x, 'y_mm': p.y})
                wall_txt, off_txt = '-', '-'
                if loops is not None:
                    wall_m, off_m = healthy_reading(loops, p)
                    row['healthy_wall_mm'] = si.mm(wall_m)
                    row['nearest_to_exterior_mm'] = si.mm(off_m)
                    wall_txt, off_txt = '%.4f' % si.mm(wall_m), '%.4f' % si.mm(off_m)
                entry['stations'].append(row)
                say('  %9.3f   %7.4f   (%8.3f, %8.3f)   %5d   %15s   %14s'
                    % (si.mm(z_m), si.mm(nearest['gap_m']), p.x, p.y, len(seams), wall_txt,
                       off_txt))
                keep()
        keep()
        return rec
    finally:
        App.closeDocument(doc.Name)


def residue_check(cavity, ribs, fused, implicated):
    """`cavity`'s own residue boolean, rerun on the saved cavity, beside each implicated rib alone.

    `cut_and_check` decides "the ribs were cut" by `cut.common((tool,), RIB_CUT_FUZZ_MM)` having no
    volume. On the dosed build it read 0.000000 mm3 while points inside the fused tool lay inside
    the cavity (measured 2026-11-15). Rerunning that exact call here says whether the check is
    blind on this cavity or failed only in the build; the per-rib calls, on smaller operands, say
    whether the material is there for a boolean to find. Both use the production fuzz.
    """
    out = {'fuzz_mm': si.RIB_CUT_FUZZ_MM}
    say('')
    say('  the residue check, rerun on the saved cavity (fuzz %g mm)' % si.RIB_CUT_FUZZ_MM)
    at = time.time()
    left = cavity.common((fused,), si.RIB_CUT_FUZZ_MM)
    out['fused'] = {'volume_mm3': left.Volume, 'solids': len(left.Solids),
                    'faces': len(left.Faces), 'valid': bool(left.isValid()),
                    'seconds': time.time() - at}
    say('    fused tool:  %.6f mm3, %d solid(s), %d face(s), valid=%s, %.0f s'
        % (left.Volume, len(left.Solids), len(left.Faces), out['fused']['valid'],
           time.time() - at))
    out['per_rib'] = []
    for k in implicated:
        at = time.time()
        got = cavity.common((ribs[k],), si.RIB_CUT_FUZZ_MM)
        row = {'rib': k, 'rib_volume_mm3': ribs[k].Volume, 'volume_mm3': got.Volume,
               'solids': len(got.Solids), 'valid': bool(got.isValid()),
               'seconds': time.time() - at}
        out['per_rib'].append(row)
        say('    rib %2d alone: %.6f mm3 of its %.4f, %d solid(s), valid=%s, %.0f s'
            % (k, got.Volume, ribs[k].Volume, len(got.Solids), row['valid'], row['seconds']))
    return out


def whose_material(brep, healthy_path, json_path, every=1, with_tool=False,
                   with_residue=False):
    """Is a point inside each removed region also inside the dosed cavity, and the healthy wall?

    The rib cut's own check read 0.000000 mm3 of rib left in the dosed cavity, yet the dosed wall
    is missing the ribs along every slot on the x = -150 face (measured 2026-11-15). If the saved
    cavity contains those points, the cut did not remove the ribs there and the residue check
    missed it. Reads the stations from a previous run's JSON.

    **`with_tool` asks the decisive question without a boolean.** The rib tool depends only on the
    notches and `t`, the same in both builds, so it is rebuilt here exactly as `cavity` builds it
    -- `dilated_notches`, then one fuse -- and each point is tested against every rib solid on its
    own and against the fused tool. A point inside the tool and inside the cavity is rib material
    the cut left behind, whatever the residue check read; a point inside some rib but not the fused
    tool means the fuse lost it.
    """
    cavity = load_brep(brep)
    healthy = load_brep(healthy_path)
    with io.open(json_path, 'r', encoding='utf-8') as fh:
        rec = json.load(fh)
    # Rebuild the dosed cell wall so each region can be re-derived with an interior point.
    doc = App.newDocument('whose_material')
    try:
        cowl_tree.emit(doc, None, with_u(PARAMS[rec['kind']], rec['u']), BUILDERS[rec['kind']])
        doc.recompute()
        body_node, tools, _mirrors, cell_cut = cowl_tree.pieces(doc)
        wall, _stages, _complete = finish(cavity, cell_cut.Shape, body_node.Shape, [])
        ribs, fused = None, None
        if with_tool:
            params = doc.getObject('Params')
            t_m = si.m(float(params.get('cowl_n_perimeters'))
                       * float(params.get('extrusion_width')))
            at = time.time()
            ribs = ci.dilated_notches(notch_compound(tools), t_m)
            say('  %d rib solids dilated in %.0f s' % (len(ribs), time.time() - at))
            at = time.time()
            # Exactly `cavity`'s line, so the fused tool is the one the build cut with.
            fused = ribs[0] if len(ribs) == 1 else ribs[0].fuse(ribs[1:]).removeSplitter()
            say('  fused in %.0f s: %d solid(s), %d face(s), valid=%s'
                % (time.time() - at, len(fused.Solids), len(fused.Faces), fused.isValid()))
            rec['rib_tool'] = {'ribs': len(ribs), 'fused_solids': len(fused.Solids),
                               'fused_faces': len(fused.Faces),
                               'fused_valid': bool(fused.isValid())}
    finally:
        App.closeDocument(doc.Name)
    stations = [r for r in rec.get('removed', []) if r.get('removed')][::max(1, every)]
    rows = []
    for r in stations:
        got = removed_at(healthy, wall, si.m(r['z_mm']))
        if got is not None:
            got['z_mm'] = r['z_mm']
            rows.append(got)
    out = []
    say('')
    say('  whose material: is each removed region inside the dosed cavity?')
    say('       z mm   interior point (x, y) mm  mm2      in cavity   in healthy wall')
    for row in rows:
        for reg in row['removed']:
            if reg.get('inside_mm') is None:
                continue
            p = App.Vector(reg['inside_mm'][0], reg['inside_mm'][1], row['z_mm'])
            in_cav = bool(cavity.isInside(p, si.mm(SEAM_TOL_M), True))
            in_wall = bool(healthy.isInside(p, si.mm(SEAM_TOL_M), True))
            item = {'z_mm': row['z_mm'], 'inside_mm': reg['inside_mm'],
                    'area_mm2': reg['area_mm2'], 'in_dosed_cavity': in_cav,
                    'in_healthy_wall': in_wall}
            tool_txt = ''
            if ribs is not None:
                tol = si.mm(SEAM_TOL_M)
                which = [k for k, r in enumerate(ribs) if r.isInside(p, tol, True)]
                item['in_ribs'] = which
                item['in_fused_tool'] = bool(fused.isInside(p, tol, True))
                tool_txt = '   ribs %s, fused %s' % (which or '-', item['in_fused_tool'])
            out.append(item)
            say('  %9.3f   (%8.3f, %8.3f)   %7.3f   %9s   %15s%s'
                % (row['z_mm'], p.x, p.y, reg['area_mm2'], in_cav, in_wall, tool_txt))
    rec['whose_material'] = out
    if with_residue and fused is not None:
        rec['residue'] = residue_check(cavity, ribs, fused,
                                       sorted(set(k for it in out for k in it.get('in_ribs', ()))))
    with io.open(json_path, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(rec, indent=1, sort_keys=True, default=float))
    return out


def main():
    brep, healthy = _opt('brep'), _opt('healthy')
    if not brep or not healthy:
        raise SystemExit('--brep=<refusal cavity> and --healthy=<control wall> are required')
    if _opt('from-json'):
        whose_material(os.path.normpath(brep), os.path.normpath(healthy),
                       os.path.normpath(_opt('from-json')), every=int(_opt('every', '1')),
                       with_tool=_opt('tool') not in (None, '0', ''),
                       with_residue=_opt('residue') not in (None, '0', ''))
        return
    run(os.path.normpath(brep), os.path.normpath(healthy), _opt('kind', 'tail_shell'),
        float(_opt('u', '3.0')), os.path.normpath(_opt('out-dir', OUT_DIR)),
        step_m=si.m(float(_opt('step-mm', si.mm(STEP_M)))))


if is_entry_point(__name__):
    main()
