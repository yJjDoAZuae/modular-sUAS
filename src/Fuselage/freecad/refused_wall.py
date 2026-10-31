"""Finish the wall a refusal abandoned, and measure it with the checks that already exist.

**Why this exists.** On 2026-10-29 the post-cut pass refused a `tail_shell` at `U` = 3.0 reporting
the finished wall closed to **0.0001 mm at `z` = -73.1818**, and left one question: what does the
geometry actually look like there? The reading is a scalar -- `max(0, t - d)` for `d` the minimum
distance from the cavity's section to the exterior -- so it says the cavity reaches the outside and
nothing about whether it crosses, how far the defect runs, or whether the wall has a hole.

**The refusal now carries the cavity it was measured on** (`cowl_interior.Unconverged.shape`,
written by `wall_measure.refusals`), so that question can be asked without rebuilding: the cavity
is the expensive part, at 1.94 hours, and everything below is minutes.

**Nothing here reimplements any step of the construction, and that is the whole method.** Four
earlier attempts at a comparison like this each produced a plausible wrong number by rebuilding an
operand instead of measuring the one the construction used (`cowl_interior_surface.md` section 6.1),
and `healthy - failed` as a boolean was refuted outright under IP-FC-146. So this script only
*composes* production functions that are already at module level -- `cell_boundary_planes`,
`_extend_across_cell`, `mirror_across_cell` -- and then applies the measures that already exist:
`sever_doses.ring_states` for the annulus identity, its `break_extent` for the axial ends, and
`check_cowl_interior.wall_thickness` for the incumbent reading. The classification of the
containment residue is `wall_measure.refusals.escape`, which exists because volume alone is the
wrong test (IP-FC-137's sliver read 0.000000 mm3 and was a genuine invalid shape).

**What it asks, in order, cheapest first.**

1. **What wall does that cavity produce?** The three booleans `shell_solid` performs after
   `cavity` returns, run here one at a time so a step that refuses is reported and the result it
   got to is still measured -- which `shell_solid` cannot do, because it is right to refuse.
2. **Is the ring broken, and where?** The annulus scan at `SCAN_MM`, plus a dense local scan
   around the station the refusal named, since a break shorter than the spacing is invisible.
3. **Did the cavity leave the blank?** Opt-in, last, and unbounded. Cutting the blank out of the
   cavity leaves whatever is not inside it, so a contained cavity leaves nothing -- and it has to
   be an *exact* boolean, because a fuzzy one would weld away the near-tangency sliver that is the
   interesting answer. Against a near-tangent operand that is the kernel's worst case: it ran
   **over 91 minutes on one core** on 2026-10-29 and was stopped, so it is behind
   `--containment=1`. OCC gives Python no way to bound a boolean, so making it a deliberate
   separate request is the only honest handling. It is redundant for the main question anyway: a
   cavity that crossed the exterior leaves a hole in the wall, which question 2 finds directly.

**Progress goes to stderr, flushed, and the JSON is written after every question.** Both are
corrections to this script's own first version, which printed to block-buffered stdout and wrote
once at the end -- so that 91 minute run produced an entirely empty log and no partial result, and
telling work from a hang meant reading the process's CPU time from outside. `cowl_interior.note`
exists for exactly this and its docstring says so.

Run it as::

    freecadcmd refused_wall.py --pass --brep=<path to the refusal artifact> \\
        --pass --kind=tail_shell --pass --u=3.0 --pass --z=-73.1818

`freecadcmd`'s exit code is unreliable, so read the printed report and the JSON. One `--pass` per
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
import Part                                                              # noqa: E402

import check_cowl_interior as cci                                        # noqa: E402
import cowl_interior as ci                                               # noqa: E402
import cowl_tree                                                         # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from station_gaps import BUILDERS, PARAMS, with_u                        # noqa: E402
from wall_measure import refusals as wm_refusals                         # noqa: E402
from wall_measure import ring_breaks as rb                               # noqa: E402

# The annulus scan, the break refinement and the incumbent reading are `sever_doses`'s, imported
# rather than restated: a refinement that asked the question a second way would be measuring a
# different quantity, and this script exists to measure the *same* one on a shape that survived.
# Importing is safe -- that module runs `main()` behind `is_entry_point`.
from sever_doses import (BREAK_Z, HEALTHY_MM, SCAN_MM, SILENT_MM,        # noqa: E402
                         ring_states, break_extent, thickness_at)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'refused_wall')

#: Half-width of the dense scan around the station the refusal named, in millimeters. 5 mm each
#: way at 0.25 mm is 41 stations, which resolves a defect an order of magnitude shorter than the
#: 2.0 mm the part-wide scan can see -- and `ring_breaks` records that a break shorter than the
#: spacing is missed entirely, so the local pass is not optional.
LOCAL_HALF_MM = 5.0
LOCAL_STEP_MM = 0.25


def _opt(name, default=None):
    for arg in sys.argv[1:]:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def say(text=''):
    """One progress line, to stderr, flushed. `cowl_interior.note`'s own reason, relearned.

    **The first version of this script printed to stdout**, which is block-buffered when
    redirected, so a 91 minute run produced a completely empty log and the only way to tell work
    from a hang was to read the process's CPU time from outside. `note` exists precisely so
    nobody has to do that, and its docstring says so; this script had the defect anyway.
    """
    sys.stderr.write('%s\n' % text)
    sys.stderr.flush()


def load_brep(path):
    """The saved shape. Tries both spellings rather than assuming one.

    `Part.Shape` has carried the BREP reader under more than one name across versions, and a
    wrong guess here fails after the tree has been built. The error names what was tried.
    """
    shape = Part.Shape()
    tried = []
    for name in ('importBrep', 'read'):
        fn = getattr(shape, name, None)
        if fn is None:
            tried.append('%s (absent)' % name)
            continue
        try:
            fn(path)
            return shape
        except Exception as exc:                                  # noqa: BLE001
            tried.append('%s (%s)' % (name, type(exc).__name__))
    raise RuntimeError('could not read %s; tried %s' % (path, ', '.join(tried)))


def span_of(shape):
    """The smallest dimension of a shape's bounding box, or `None` for an empty one.

    The *smallest*, because a sliver is thin in one direction and may be long in the others --
    IP-FC-137's was a ten-micron box, but a near-tangency residue between two large faces can be
    millimeters across and still be a sliver.
    """
    if not shape.Solids and not shape.Faces:
        return None
    bb = shape.BoundBox
    return min(bb.XLength, bb.YLength, bb.ZLength)


def containment(cavity_shape, blank):
    """Question 1: what of the cavity lies outside the blank. `(verdict, why, record)`.

    **An exact cut, with no fuzz, and that is deliberate.** `cut_and_check` uses `RIB_CUT_FUZZ`
    because it wants a robust rib cut; this wants the opposite. A fuzzy boolean welds across gaps
    below its tolerance, which is precisely the near-tangency residue `escape` exists to detect --
    so running this fuzzily would hide the most interesting answer and report `contained`.

    **Pieces are counted as solids where there are solids and faces where there are not.** The
    residue that defeated a volume-only check under IP-FC-137 was five faces and not a valid
    solid, so `len(shape.Solids)` on it is zero and the blind spot comes straight back.
    """
    at = time.time()
    outside = cavity_shape.cut(blank)
    try:
        valid = bool(outside.isValid())
    except Exception:                                             # noqa: BLE001
        valid = None
    span = span_of(outside)
    pieces = len(outside.Solids) or len(outside.Faces)
    verdict, why = wm_refusals.escape(outside.Volume, pieces, valid, span_mm=span)
    rec = {'volume_mm3': outside.Volume, 'solids': len(outside.Solids),
           'faces': len(outside.Faces), 'pieces': pieces, 'valid': valid,
           'narrowest_span_mm': span, 'verdict': verdict, 'why': why,
           'seconds': time.time() - at}
    if outside.Solids:
        rec['pieces'] = [{'volume_mm3': s.Volume,
                          'center': [s.CenterOfMass.x, s.CenterOfMass.y, s.CenterOfMass.z],
                          'z_lo': s.BoundBox.ZMin, 'z_hi': s.BoundBox.ZMax}
                         for s in sorted(outside.Solids, key=lambda s: -s.Volume)[:8]]
    return verdict, why, rec


def pieces_of(shape, limit=12):
    """Each piece of a shape, largest first: volume, `z` range and center of mass.

    **This is the localization, and it costs nothing.** When `notched.cut(inside)` comes back in
    three solids, *which* three and *where* is the whole finding -- IP-FC-146 characterized the
    2026-10-04 severance exactly this way (85512.09, 4349.27 and 718.19 mm3) and that is what
    made the detached piece identifiable across builds. It needs no section scan.

    Falls back to shells for a sewn compound, which has no solids at all.
    """
    parts = list(shape.Solids) or list(shape.Shells)
    out = []
    for part in sorted(parts, key=lambda s: -abs(s.Volume))[:limit]:
        bb = part.BoundBox
        rec = {'volume_mm3': part.Volume, 'z_lo': bb.ZMin, 'z_hi': bb.ZMax,
               'z_length': bb.ZLength, 'faces': len(part.Faces)}
        try:
            com = part.CenterOfMass
            rec['center'] = [com.x, com.y, com.z]
        except Exception:                                         # noqa: BLE001
            # A shell's center of mass is not always available and is not worth a failure here.
            pass
        out.append(rec)
    return out


def finish(cavity_shape, blank, body, mirrors):
    """Question 1: the three booleans after `cavity`, one at a time. `(wall, stages, complete)`.

    Each step is reported whether it refuses or not, and a refusal does not stop the next one
    being attempted. `shell_solid` cannot do that and should not -- it is right to refuse -- which
    is why this measurement needs its own composition rather than a flag on the production path.

    **`wall` is the last shape that is actually a wall, and `complete` says whether the pipeline
    got to the end.** A refusal's carried shape is recorded and measured for its pieces, but it is
    *not* returned as the wall when it is not one: measured 2026-10-29, continuing with the sewn
    compound a mirror refusal hands over sent a 151-station annulus scan over five disconnected
    shells, where it ran five times slower than on real geometry and could only ever have reported
    "broken" -- a true statement about a shape that is not a wall. The annulus identity is a
    property of the *mirrored* wall, so when the mirror refuses the question does not arise.
    """
    stages = []
    inside = cavity_shape
    for i, plane in enumerate(ci.cell_boundary_planes(body)):
        at = time.time()
        try:
            inside = ci._extend_across_cell(inside, plane)
            stages.append({'step': 'extend_across_cell', 'plane': i, 'ok': True,
                           'volume_mm3': inside.Volume, 'solids': len(inside.Solids),
                           'pieces': pieces_of(inside), 'seconds': time.time() - at})
        except (ci.Unconverged, ci.PreconditionFailed) as exc:
            got = wm_refusals.shape_of(exc)
            stages.append({'step': 'extend_across_cell', 'plane': i, 'ok': False,
                           'error': str(exc)[:300], 'seconds': time.time() - at,
                           'carried_pieces': None if got is None else pieces_of(got)})
            return None, stages, False
    at = time.time()
    wall = blank.cut(inside)
    stages.append({'step': 'notched_cut', 'ok': True, 'volume_mm3': wall.Volume,
                   'solids': len(wall.Solids), 'pieces': pieces_of(wall),
                   'seconds': time.time() - at})
    for i, normal in enumerate(mirrors):
        at = time.time()
        try:
            wall = ci.mirror_across_cell(wall, normal)
            stages.append({'step': 'mirror_across_cell', 'mirror': i, 'ok': True,
                           'volume_mm3': wall.Volume, 'solids': len(wall.Solids),
                           'pieces': pieces_of(wall), 'seconds': time.time() - at})
        except (ci.Unconverged, ci.PreconditionFailed) as exc:
            got = wm_refusals.shape_of(exc)
            stages.append({'step': 'mirror_across_cell', 'mirror': i, 'ok': False,
                           'error': str(exc)[:300], 'seconds': time.time() - at,
                           'carried_volume_mm3': None if got is None else got.Volume,
                           'carried_shells': None if got is None else len(got.Shells),
                           'carried_pieces': None if got is None else pieces_of(got)})
            return wall, stages, False
    return wall, stages, True


def local_scan(wall, z, half=LOCAL_HALF_MM, step=LOCAL_STEP_MM):
    """Question 3, locally: the annulus identity around one station at `step` spacing.

    The part-wide scan runs at `SCAN_MM` = 2.0 mm and `ring_breaks.missable_mm` records what that
    cannot see. A refusal names a station to four decimals, so the one place a dense pass is
    affordable and worth having is right there.
    """
    lo, hi = z - half, z + half
    n = int(round((hi - lo) / step)) + 1
    cont, broken, unread, worst, detail = ring_states(wall, lo, hi, stations=n)
    return {'z': z, 'z_lo': lo, 'z_hi': hi, 'step_mm': step, 'stations': n,
            'annulus': cont, 'broken': broken, 'unreadable': unread,
            'worst_station': worst, 'detail': detail}


def run(brep, kind, u, out_dir, z_of_interest=None, want_containment=False):
    """The questions, cheapest first, each written down before the next one starts.

    **The order and the incremental write are both corrections to this script's first version**,
    which asked the containment question first and wrote its JSON once at the end. Containment is
    an *exact* boolean against a near-tangent operand, which is the kernel's worst case: measured
    2026-10-29 it was still running after **91 minutes** on one core with nothing written, and was
    stopped. It is now opt-in (`--containment=1`), it runs last, and it is documented here as
    unbounded -- there is no way to put a time limit on an OCC boolean from Python, so the only
    honest handling is to make it a separate, deliberate request. It is also **redundant for the
    main question**: if the cavity crossed the exterior the wall has a hole there, and the ring
    scan below finds that directly.
    """
    started = time.time()
    rec = {'brep': brep, 'kind': kind, 'u': float(u), 'scan_mm': SCAN_MM,
           'z_of_interest': z_of_interest}
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    stem = os.path.join(out_dir, '%s_U%g' % (kind, u))

    def keep(outcome=None):
        """Write what is known so far. Called after every question, not at the end."""
        if outcome is not None:
            rec['outcome'] = outcome
        rec['seconds'] = time.time() - started
        with io.open(stem + '.json', 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(rec, indent=1, sort_keys=True, default=float))

    say('')
    say('the wall a refusal abandoned: %s' % os.path.basename(brep))
    say('  %s at U = %g' % (kind, u))
    if z_of_interest is not None:
        say('  the refusal named z = %.4f; scanned densely at %.2f mm over +/- %.1f mm'
            % (z_of_interest, LOCAL_STEP_MM, LOCAL_HALF_MM))
    say('  containment check: %s' % ('requested' if want_containment else
                                     'skipped (opt in with --containment=1; it is unbounded)'))
    say('')

    doc = None
    try:
        say('  building the cowl tree...')
        doc = App.newDocument('refused_wall')
        cowl_tree.emit(doc, None, with_u(PARAMS[kind], u), BUILDERS[kind])
        doc.recompute()
        body_node, tools, mirrors, cell_cut = cowl_tree.pieces(doc)
        params = doc.getObject('Params')
        t = float(params.get('cowl_n_perimeters')) * float(params.get('extrusion_width'))
        blank = cell_cut.Shape
        body = body_node.Shape
        say('  tree built in %.0f s; t = %.3f mm, %d mirror step(s)'
            % (time.time() - started, t, len(mirrors)))

        say('  reading the refusal artifact...')
        cavity_shape = load_brep(brep)
        rec['cavity'] = {'volume_mm3': cavity_shape.Volume,
                         'solids': len(cavity_shape.Solids),
                         'faces': len(cavity_shape.Faces),
                         'valid': bool(cavity_shape.isValid())}
        say('  cavity read: %.4f mm3, %d solid(s), %d face(s), valid=%s'
            % (cavity_shape.Volume, len(cavity_shape.Solids), len(cavity_shape.Faces),
               rec['cavity']['valid']))
        keep('read')
        say('')

        # 1. What wall does that cavity produce? The three booleans after `cavity`.
        say('  1. the booleans after the fit, one at a time...')
        wall, stages, complete = finish(cavity_shape, blank, body, mirrors)
        rec['stages'] = stages
        rec['pipeline_complete'] = complete
        for s in stages:
            say('     %-22s %-6s %s'
                % (s['step'], 'ok' if s['ok'] else 'RAISED',
                   ('%.4f mm3 in %d solid(s), %.0f s'
                    % (s['volume_mm3'], s['solids'], s['seconds'])) if s['ok']
                   else s['error'][:90]))
            # The pieces are the localization and they print whichever way the step went.
            for piece in (s.get('pieces') or s.get('carried_pieces') or []):
                say('       %14.4f mm3  z %10.4f .. %10.4f (%8.4f mm)  %d face(s)'
                    % (piece['volume_mm3'], piece['z_lo'], piece['z_hi'],
                       piece['z_length'], piece['faces']))
        if wall is None:
            say('     nothing survived to measure')
            keep('no wall')
            return rec
        rec['wall'] = {'volume_mm3': wall.Volume, 'solids': len(wall.Solids),
                       'valid': bool(wall.isValid())}
        say('     wall: %.4f mm3 in %d solid(s), valid=%s'
            % (wall.Volume, len(wall.Solids), rec['wall']['valid']))
        keep('wall built')
        say('')

        if not complete:
            # **The annulus identity is a property of the mirrored wall.** One cell's section is
            # an open arc, not a ring, so `section_regions` would call every station of it broken
            # -- a true statement about a shape that is not the thing the measure is for. When the
            # pipeline does not reach the end there is no ring to ask about, and the pieces above
            # are the answer instead. Measured 2026-10-29: scanning the refusal's own sewn
            # compound anyway ran 5x slower than real geometry and said exactly nothing.
            say('  2. the ring: not scanned, and not because it is expensive. The pipeline did '
                'not reach a mirrored wall, and the annulus identity is a property of one -- a '
                'single cell sections to an arc, so every station would read "broken" whatever '
                'the geometry. The piece list above is what localizes this failure.')
            keep('refused before a ring exists')
            return rec

        # 2. Is the ring broken, and where?
        w_lo, w_hi = ci.z_extent(wall)
        s_lo, s_hi = w_lo + ci.END_INSET, w_hi - ci.END_INSET
        n_scan = rb.station_count(s_lo, s_hi, SCAN_MM, rb.MIN_STATIONS, rb.MAX_STATIONS)
        # Said *before* the scan, not after. It is a quiet quarter of an hour otherwise, and the
        # whole point of this line is that silence should be expected rather than diagnosed.
        say('  2. the ring: %d stations at %.1f mm over z %.4f..%.4f, about %.0f min at the '
            '6.8 s a station on record...' % (n_scan, SCAN_MM, s_lo, s_hi, n_scan * 6.8 / 60.0))
        cont, broken, unread, worst, detail = ring_states(wall, s_lo, s_hi)
        rec['scan'] = {'annulus': cont, 'broken': broken, 'unreadable': unread,
                       'worst_station': worst, 'stations': len(detail),
                       'missable_mm': rb.missable_mm([d['z'] for d in detail]),
                       'detail': detail}
        say('     %d annulus, %d broken, %d unreadable; a break under %.3f mm is invisible here'
            % (cont, broken, unread, rec['scan']['missable_mm']))
        if broken:
            rec['scan']['break_extent'] = break_extent(wall, detail)
            for span in rec['scan']['break_extent']:
                say('     break over %.3f mm, z %.4f to %.4f, up to %s arc(s)%s'
                    % (span['extent_mm'], span['z_lo'], span['z_hi'], span['max_faces'],
                       ' (reaches the scan end)' if span['reaches_scan_end'] else ''))
        keep('ring scanned')

        # 3. The same question densely, at the station the refusal actually named.
        if z_of_interest is not None:
            say('')
            say('  3. dense pass at the refusal\'s own station, %.2f mm spacing...'
                % LOCAL_STEP_MM)
            local = local_scan(wall, z_of_interest)
            rec['local'] = local
            say('     %d stations: %d annulus, %d broken, %d unreadable'
                % (local['stations'], local['annulus'], local['broken'], local['unreadable']))
            if local['broken']:
                local['break_extent'] = break_extent(wall, local['detail'])
                for span in local['break_extent']:
                    say('     break over %.3f mm, z %.4f to %.4f, up to %s arc(s)'
                        % (span['extent_mm'], span['z_lo'], span['z_hi'], span['max_faces']))
            rec['local_incumbent'] = thickness_at(wall, z_of_interest, t)
            keep('local scanned')

        rec['incumbent_at_break'] = thickness_at(wall, BREAK_Z, t)
        inc = rec['incumbent_at_break'] or {}
        say('')
        say('     incumbent at z = %.4f (healthy %.6f, silent failure %.6f): %s'
            % (BREAK_Z, HEALTHY_MM, SILENT_MM,
               'REFUSED -- not an annulus' if inc.get('refused')
               else inc.get('error') or '%.6f mm' % inc.get('worst_low', float('nan'))))
        keep('measured')

        # 4. Opt-in and last: did the cavity leave the blank? Unbounded -- see the docstring.
        if want_containment:
            say('')
            say('  4. cavity outside the blank -- an exact boolean on a near-tangent operand. '
                'This has no time bound and has run over 90 min before now.')
            verdict, why, c_rec = containment(cavity_shape, blank)
            rec['containment'] = c_rec
            say('     %s: %s' % (verdict.upper(), why))
            for piece in c_rec.get('pieces', []):
                say('       piece %.6f mm3 at z %.4f..%.4f, center (%.3f, %.3f, %.3f)'
                    % (piece['volume_mm3'], piece['z_lo'], piece['z_hi'],
                       piece['center'][0], piece['center'][1], piece['center'][2]))
            keep('measured with containment')
    except Exception as exc:                                      # noqa: BLE001
        rec['error'] = traceback.format_exc()[-800:]
        keep('error')
        say('  ERROR: %s' % str(exc)[:200])
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)

    keep()
    say('')
    say('  wrote %s.json in %.0f s' % (stem, rec['seconds']))
    return rec


def main():
    brep = _opt('brep')
    if not brep:
        raise SystemExit('--brep=<path to a refusal artifact> is required')
    z = _opt('z')
    run(os.path.normpath(brep), _opt('kind', 'tail_shell'), float(_opt('u', '3.0')),
        os.path.normpath(_opt('out-dir', OUT_DIR)),
        z_of_interest=None if z is None else float(z),
        want_containment=_opt('containment') not in (None, '0', ''))


if is_entry_point(__name__):
    main()
