"""Export the real geometry OQ-DES-CW25's Metric A is measured on, and draw it to scale.

**What this answers.** `cowl_interior_surface.md` section 6.3 describes Metric A in prose: the
smallest in-plane distance from the fitted interior candidate's section to the nearest *dilated*
buttress tool's section, and which of the tool's four face roles that minimum lands on. Prose is
not enough for it -- the quantity is a few tens of microns on a specific face of a 0.1 mm slab,
inside a part hundreds of millimetres across, and the finding that matters (the minimum lands on a
cheek, and the tool has usually already crossed the surface) is a statement about *where* on the
tool a distance was taken. This driver takes the sections off a real build and writes them as
drawings with a scale bar.

**It is a two-stage tool on purpose, and the slow stage caches.** Stage one builds the cowl, runs
`cavity` with `clearance_check` on, and writes a JSON capture of the real section coordinates, the
role-tagged tool edges and `clearance_face_scan`'s own rows. Stage two reads that JSON and renders
SVG through `tools/section_figure.py`, which needs no FreeCAD at all. So the drawing can be
re-styled, re-windowed and re-captioned any number of times for one build, and the build happens
once. `--from-capture` skips stage one entirely.

**Costs, measured on a `nose_cowl_shell` at `U` = 1.** The build is about 33 s and the clearance
scan adds roughly 180 s, so stage one is about 3.5 minutes; this is the cheapest configuration that
has the geometry, which is why it is the default. A `tail_shell` is the kind with the engulfed
station and costs an order of magnitude more. Stage two is well under a second.

Run it as::

    freecadcmd clearance_figure.py --pass --kind=nose_cowl_shell --pass --u=1.0
    freecadcmd clearance_figure.py --pass --from-capture=<path>

One `--pass` per argument: `freecadcmd` hands only the token after each `--pass` to the script, and
its exit code is unreliable, so read the capture and the SVGs rather than `$?`.
"""
import io
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'tools'))

from section_figure import (ENGAGEMENT_FILL, ROLE_STYLE, Window, _mm,
                            draw_clearance_station)

# **FreeCAD is imported inside `capture`, not here.** Stage two reads a JSON capture and writes
# SVG, so it needs nothing from the kernel -- and keeping the import lazy is what lets the
# drawing be iterated under this repository's own Python, in a second, instead of under
# `freecadcmd` behind a nine-minute build. `is_entry_point` is the one exception and is imported
# lazily too, so `main` still behaves correctly under `freecadcmd`'s missing `__main__` guard.

#: Points per closed section loop of the interior surface. The loop is hundreds of mm around and
#: the figure is a few hundred px wide, so this is already finer than the raster.
SURFACE_POINTS = 900

#: Points per *edge* of a tool section. Edges are tagged individually so the role colouring is
#: per face, which is the whole content of the figure; a straight cheek needs 2 and a dilation
#: bridge arc needs more.
EDGE_POINTS = 24

#: Margin in mm around the tool's *near end* in the tool-scale figure.
#:
#: **The window is placed on the end of the tool, not centred on the contact, and that is the
#: whole trick of this figure.** A buttress tool's section is a slab 0.1 mm thick and more than
#: a hundred millimetres long -- measured on the nose at U = 1 it runs y 43.33 to 150.00 -- so
#: the two cheeks are the only faces anywhere near the contact, and a box centred on the contact
#: shows two parallel lines and nothing else. The floor is the 0.1 mm segment capping the near
#: end, and it is what the question is about, so the window is fitted to the floor edge and the
#: dilated outline around it. The `outer` face is at the far end and is correctly out of frame.
TOOL_MARGIN_MM = 0.95

#: Width in mm of the contact figure, as a multiple of the measured distance, and its floor.
#:
#: **The floor is set by the dilation's own faceting, not by the distance being drawn.** A 48-gon
#: on a circle of radius `t` has a chord of `2*t*sin(pi/48)` = 0.0785 mm, and measurement says
#: most of these contacts sit on a facet *bridging* two faces rather than on either face's own
#: image -- so a window narrower than a few chords would crop out the one feature that explains
#: the reading. 0.30 mm is about four chords.
CONTACT_FACTOR = 80.0
CONTACT_MIN_MM = 0.30

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '..', '..', '..', 'doc', 'design', 'img', 'cowl_rib_cut')


def _opt(name, default=None):
    prefix = '--%s=' % name
    for arg in sys.argv:
        if arg.startswith(prefix):
            return arg[len(prefix):]
    return default


def _loop_points(wire, n):
    return [(float(p.x), float(p.y)) for p in wire.discretize(Number=int(n))]


def _tag_edges(Part, section_wires, raw_tool, roles):
    """One record per edge of a tool's section, carrying the role of the face it came from.

    A section edge lies on exactly one face of the solid it was cut from, so the face is found by
    asking the kernel which face the edge's own midpoint is nearest -- the same route
    `clearance_face_scan` uses to attribute a contact, and for the same reason: a face index into
    a sectioned shape means nothing, while a distance to the original solid's faces does.
    """
    out = []
    for wire in section_wires:
        for edge in wire.Edges:
            try:
                mid = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
            except Exception:                        # a degenerate edge has no interior point
                continue
            probe = Part.Vertex(mid)
            near = sorted((face.distToShape(probe)[0], fi)
                          for fi, face in enumerate(raw_tool.Faces))
            _, fi = near[0]
            pts = _loop_points(Part.Wire([edge]), EDGE_POINTS)
            if len(pts) >= 2:
                out.append(dict(role=roles[fi]['role'], face=fi, points=pts))
    return out


def capture(kind, u, out_dir, stations=None, tau=None):
    """Stage one: build, scan, and write the JSON capture. Returns its path.

    **Progress goes through `ci.note`, not `print`.** Measured 2026-10-17: `freecadcmd` discards
    this script's stdout, so every `print` in an earlier version of this driver vanished while
    `note`'s lines appeared -- `note` writes to stderr and flushes, which is why it exists. A
    driver that reports through `print` under `freecadcmd` is silent for the whole run and
    indistinguishable from a hang, and that is the same hazard as the binary's unreliable exit
    code: the artifact is the evidence, not the channel.
    """
    import FreeCAD as App
    import Part

    import cowl_interior as ci
    import cowl_tree
    import soak_cowl_shell as soak

    builders = {'tail_shell': cowl_tree.tail_shell,
                'nose_cowl_shell': cowl_tree.nose_cowl_shell}
    started = time.time()
    report = {}
    doc = App.newDocument('clearance_figure')
    # A kind's parameter rows are a list of `(alias, literal)` pairs, not a dict -- `build_sheet`
    # reads them in order -- so `U` is overridden with `soak.with_u`, not by key assignment.
    tip = cowl_tree.emit(doc, None, soak.with_u(soak.BASE_PARAMS[kind], u), builders[kind])
    doc.recompute()
    notches = Part.makeCompound([n.Shape for n in tip.Notches])
    body, notched, t = tip.Body.Shape, tip.Base.Shape, float(tip.Inset)
    ci.note('figure capture: built %s at U=%.2f in %.0f s; t = %.4f mm'
            % (kind, u, time.time() - started, t))
    # **This is the second build of the wall and that is unavoidable here.** `doc.recompute()`
    # above already ran the shell node's own `execute`, which calls `shell_solid` itself, but the
    # node exposes no `report` -- and `report['clearance_faces']` is the entire point of this
    # driver. Measured on the nose at U=1: 33 s for the node's build against 515 s for the scan
    # below, so the duplicate is 6 % of the run rather than half of it. On a tail it would not be.

    # `tau` is passed rather than left to default: `cavity(..., tau=TAU)` binds the module
    # constant at import, so setting `ci.TAU` afterwards does nothing.
    kwargs = dict(report=report, clearance_check=True)
    if tau is not None:
        kwargs['tau'] = float(tau)
    scan_at = time.time()
    ci.cavity(body, notched, notches, t, tip.Overhang, **kwargs)
    ci.note('figure capture: cavity with the clearance scan took %.0f s'
            % (time.time() - scan_at))

    smooth = report.get('smooth_shape')
    rows = report.get('clearance_faces') or []
    if smooth is None:
        raise SystemExit('cavity reported no smooth_shape; nothing to section')
    if not rows:
        raise SystemExit('the clearance scan flagged no station, so there is nothing to draw')

    ribs = ci.dilated_notches(notches, t)
    raw_tools = notches.Solids
    roles_by_tool = {}

    wanted = rows
    if stations:
        keep = [float(s) for s in stations]
        wanted = [r for r in rows if any(abs(r['z'] - k) < 1.0e-6 for k in keep)]
        if not wanted:
            raise SystemExit('none of %r is a scanned station; the scan has %s'
                             % (keep, ', '.join('%.4f' % r['z'] for r in rows)))

    captured = []
    for row in wanted:
        index = row['tool']
        if index not in roles_by_tool:
            roles_by_tool[index] = ci.tool_face_roles(raw_tools[index])
        z = row['z']
        surface = [_loop_points(w, SURFACE_POINTS)
                   for w in ci._slice_wires(smooth, z) if w]
        dilated = [_loop_points(w, SURFACE_POINTS)
                   for w in ci._slice_wires(ribs[index], z) if w]
        raw_wires = [w for w in ci._slice_wires(raw_tools[index], z) if w]
        edges = _tag_edges(Part, raw_wires, raw_tools[index], roles_by_tool[index])
        entry = dict(surface=surface, dilated=dilated, raw_edges=edges)
        for key in ('z', 'tool', 'metric_a', 'contact_distance', 'engagement',
                    'fraction_inside', 'role', 'second_role', 'offset',
                    'expected_offset', 'on_face_image', 'in_blank', 'bounds_wall',
                    'normal_dot_gap'):
            if key in row:
                entry[key] = row[key]
        entry['p_surf'] = [float(v) for v in row['p_surf'][:2]]
        entry['p_tool'] = [float(v) for v in row['p_tool'][:2]]
        entry['roles'] = [dict(role=r['role'], area=r['area']) for r in roles_by_tool[index]]
        captured.append(entry)
        ci.note('  z=%-11.4f tool %-2d %-8s metric_a=%.6f role=%-5s bounds_wall=%s '
                '(%d surface loops, %d dilated loops, %d tagged edges)'
                % (z, index, entry['engagement'], entry['metric_a'], entry['role'],
                   entry.get('bounds_wall'), len(surface), len(dilated), len(edges)))

    payload = dict(kind=kind, u=float(u), t=t,
                   buttress_cut_thickness=float(
                       doc.getObject('Params').get('buttress_cut_thickness')),
                   rib_facets=ci.RIB_FACETS, clearance_margin_mm=ci.CLEARANCE_MARGIN_MM,
                   stations=captured)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'cw25_capture_%s_u%g.json' % (kind, u))
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(payload, indent=1, sort_keys=True))
    ci.note('capture written: %s (%d stations, %.0f s total)'
            % (path, len(captured), time.time() - started))
    return path


def _role_labels(fig, raw_edges, min_px=26.0):
    """Name each role on the drawing itself, next to the longest edge carrying it.

    A legend makes the reader hold four colours in their head while looking at a slab 0.1 mm
    thick. Labelling the geometry does not, and the roles are the content of the figure.
    """
    import math as _m
    best = {}
    for edge in raw_edges:
        pts = edge['points']
        span = max(_m.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])) \
            if len(pts) > 1 else 0.0
        total = sum(_m.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        if total > best.get(edge['role'], (0.0, None))[0]:
            best[edge['role']] = (total, pts)
    for role, (_, pts) in sorted(best.items()):
        mid = pts[len(pts) // 2]
        if not fig.window.contains(mid):
            continue
        px = fig.window.project(mid)
        w_px, h_px = fig.window.size_px
        if not (min_px < px[0] < w_px - min_px and min_px < px[1] < h_px - min_px):
            continue
        style = ROLE_STYLE.get(role, dict(stroke='#111827'))
        fig.text(mid, role, size=11.5, fill=style['stroke'], weight='bold',
                 anchor='middle', px_offset=(0.0, -6.0))
    return fig


def _tool_window(entry, margin):
    """The rectangle around the tool's near end -- the `floor` edge, and *not* the contact.

    **An earlier version included the contact, and that was the mistake the figure exists to
    expose.** At the worst station on the nose the contact sits on a **cheek, 3.65 mm from the
    cut floor**. The slab is 0.1 mm thick and over a hundred long, so a window forced to hold
    both the floor and the contact is 3.65 mm tall and draws the tool as two parallel lines with
    its end in a corner. The anatomy and the contact are in different places by the nature of
    the finding, so figure 2 draws the anatomy and points at where the contact went.

    "Near end" is read from the geometry rather than assumed: it is the end the `floor` role
    sits on, the only face that bounds the wall. With no floor in this plane it falls back to
    the contact so the figure still renders.
    """
    xs, ys = [], []
    for edge in entry['raw_edges']:
        if edge['role'] == 'floor':
            xs.extend(p[0] for p in edge['points'])
            ys.extend(p[1] for p in edge['points'])
    if not xs:
        xs = [entry['p_surf'][0], entry['p_tool'][0]]
        ys = [entry['p_surf'][1], entry['p_tool'][1]]
    half = max(margin, (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0)
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    return (cx - half, cy - half, cx + half, cy + half)


def _point_offscreen(fig, target, label, stroke, margin_px=18.0):
    """Mark a point outside the window: an arrow at the frame, and how far away it is.

    Without this a reader cannot tell "the contact is not drawn here" from "the contact is one
    of these lines". With it, figure 2 shows the tool's end at a useful scale and still says, in
    millimetres, where along the slab the measurement was actually taken.
    """
    win = fig.window
    if win.contains(target):
        return False
    cx = (win.x_lo + win.x_hi) / 2.0
    cy = (win.y_lo + win.y_hi) / 2.0
    dx, dy = target[0] - cx, target[1] - cy
    span = math.hypot(dx, dy)
    if span <= 0.0:
        return False
    half_x = (win.x_hi - win.x_lo) / 2.0 - margin_px / win.scale
    half_y = (win.y_hi - win.y_lo) / 2.0 - margin_px / win.scale
    k = min(half_x / abs(dx) if dx else float('inf'),
            half_y / abs(dy) if dy else float('inf'))
    tip = (cx + dx * k, cy + dy * k)
    back = (cx + dx * k * 0.72, cy + dy * k * 0.72)
    fig.polyline([back, tip], stroke=stroke, width=2.2)
    fig.dot(tip, fill=stroke, r=3.2)
    fig.text(back, '%s, %s along the slab' % (label, _mm(span)), size=11.0, fill=stroke,
             weight='bold', anchor='middle', px_offset=(0.0, 15.0 if dy < 0 else -9.0))
    return True


def _station_figures(payload, entry, out_dir, slug):
    """Stage two for one station: three drawings, at the part, tool and contact scales.

    **Three, because one cannot work.** The part's section is tens of millimetres across, the
    slab is 0.1 mm thick, the dilation is 0.6 mm and the measured distance is a few microns --
    five orders of magnitude between the thing being measured and the thing it is measured on. A
    single window either shows the part and hides the measurement, or shows the measurement and
    says nothing about where on the part it is. The first version of this driver fitted one
    window to everything and produced exactly that: the cutting tool runs 108 mm in `y` against
    the surface section's 43 mm, because a buttress tool deliberately reaches well outside the
    blank (that is what the `outer` role *is*), so the fitted figure was a 150 mm tall sliver.
    """
    kind, u, t = payload['kind'], payload['u'], payload['t']
    z, metric = entry['z'], entry['metric_a']
    engagement = entry['engagement']
    contact = ((entry['p_surf'][0] + entry['p_tool'][0]) / 2.0,
               (entry['p_surf'][1] + entry['p_tool'][1]) / 2.0)
    made = []

    pct = entry.get('fraction_inside')
    on_image = entry.get('on_face_image')
    verdict = ('this distance bounds the wall' if entry.get('bounds_wall')
               else 'this distance does NOT bound the wall')
    facts = ['%s at U = %g, station z = %.4f mm, tool %d' % (kind, u, z, entry['tool']),
             'Metric A = %s   (flag threshold %s)'
             % (_mm(metric), _mm(payload['clearance_margin_mm'])),
             'nearest face role: %s%s' % (entry['role'],
                                          '' if not entry.get('second_role')
                                          else ' (next nearest: %s)' % entry['second_role']),
             'engagement: %s%s' % (engagement,
                                   '' if pct is None else
                                   ' - %.1f %% of the tool section is inside the surface'
                                   % (100.0 * pct)),
             '--> %s' % verdict,
             'wall t = %.3f mm, slab %.3f mm thick, dilated by t in %d directions'
             % (t, payload['buttress_cut_thickness'], payload['rib_facets'])]
    if on_image is not None:
        facts.append('offset to that face %.4f mm against %.4f predicted: %s'
                     % (entry['offset'], entry['expected_offset'],
                        'on the face\'s own dilated image' if on_image
                        else 'NOT on it - the contact is on a bridging facet, i.e. a tool edge'))

    head = 20.0 + 15.0 * 6          # legend band: six rows plus the swatch rows above them
    # -- (1) part scale: where on the part this is. Windowed on the surface section, because
    #        the tool reaches far outside the blank and fitting it would hide the part.
    win = Window.fit(entry['surface'], width_px=520.0, margin=0.10,
                     pad_top=head, pad_bottom=46.0)
    fig = draw_clearance_station(
        entry, entry['surface'], entry['dilated'], entry['raw_edges'], window=win,
        annotate=False,
        title='1 of 3 - where on the part, at z = %.4f mm' % z,
        subtitle='%s at U = %g, one symmetry cell. Box = figure 2.' % (kind, u))
    box = _tool_window(entry, margin=TOOL_MARGIN_MM)
    fig.polyline([(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])],
                 stroke=ENGAGEMENT_FILL.get(engagement, '#111827'), width=1.3, closed=True,
                 dash='4 3', label='the area figure 2 draws')
    fig.scale_bar()
    fig.legend(extra=facts[:2]).frame()
    made.append(fig.write(os.path.join(out_dir, 'cw25_part_%s.svg' % slug)))

    # -- (2) tool scale: the face roles, the dilation, and whether the tool has crossed
    win = Window(box[0], box[1], box[2], box[3],
                 scale=560.0 / (box[2] - box[0]), pad_top=head, pad_bottom=46.0)
    fig = draw_clearance_station(
        entry, entry['surface'], entry['dilated'], entry['raw_edges'], window=win,
        annotate=False,
        title='2 of 3 - the end of the tool: which face is which',
        subtitle='Solid = the real slab, %.3f mm thick. Dashed = that slab grown by '
                 't = %.3f mm, which is what Metric A measures to.'
                 % (payload['buttress_cut_thickness'], t))
    _role_labels(fig, entry['raw_edges'])
    away = _point_offscreen(fig, contact, 'contact',
                            ENGAGEMENT_FILL.get(engagement, '#111827'))
    extra = list(facts[2:])
    if away:
        extra.append('the contact is NOT at this end - it is on a %s, off the top of this frame'
                     % entry['role'])
    fig.scale_bar()
    fig.legend(extra=extra).frame()
    made.append(fig.write(os.path.join(out_dir, 'cw25_tool_%s.svg' % slug)))

    # -- (3) contact scale: the measured segment, and what it lands on
    width = max(CONTACT_MIN_MM, metric * CONTACT_FACTOR)
    win = Window.around(contact, width, width_px=460.0, pad_top=head, pad_bottom=46.0)
    chord = 2.0 * t * math.sin(math.pi / payload['rib_facets'])
    fig = draw_clearance_station(
        entry, entry['surface'], entry['dilated'], entry['raw_edges'], window=win,
        title='3 of 3 - the contact itself, %.2f mm across' % width,
        subtitle='Dilated outline faceted: %d facets, %.4f mm chord.'
                 % (payload['rib_facets'], chord))
    fig.scale_bar()
    fig.legend(extra=['Metric A = %s' % _mm(metric),
                      'engagement: %s' % engagement,
                      'nearest role: %s' % entry['role'],
                      'dilation chord: %s' % _mm(chord),
                      '--> %s' % verdict]).frame()
    made.append(fig.write(os.path.join(out_dir, 'cw25_contact_%s.svg' % slug)))
    return made


def render(capture_path, out_dir):
    """Stage two: read a capture and write every figure it supports."""
    with io.open(capture_path, encoding='utf-8') as fh:
        payload = json.load(fh)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    made = []
    # One figure pair per engagement class, which is what section 6.3's own table is about:
    # drawing five crossings adds nothing a reader cannot get from one.
    seen = {}
    for entry in payload['stations']:
        seen.setdefault(entry['engagement'], entry)
    for engagement, entry in sorted(seen.items()):
        slug = '%s_u%g_%s' % (payload['kind'], payload['u'], engagement)
        made.extend(_station_figures(payload, entry, out_dir, slug))
    sys.stderr.write('rendered %d figures from %d stations (%s)\n'
                     % (len(made), len(payload['stations']),
                        ', '.join('%s x%d' % (k, sum(1 for e in payload['stations']
                                                     if e['engagement'] == k))
                                  for k in sorted(seen))))
    for path in made:
        sys.stderr.write('  %s\n' % path)
    sys.stderr.flush()
    return made


def main():
    out_dir = os.path.normpath(_opt('out-dir', DEFAULT_OUT))
    from_capture = _opt('from-capture')
    if from_capture:
        render(from_capture, out_dir)
        return
    kind = _opt('kind', 'nose_cowl_shell')
    u = float(_opt('u', '1.0'))
    stations = _opt('stations')
    tau = _opt('tau')
    path = capture(kind, u, out_dir,
                   stations=stations.split(',') if stations else None, tau=tau)
    render(path, out_dir)


def _is_entry_point(name):
    """`corner_common.is_entry_point`, imported lazily so stage two runs without FreeCAD.

    `freecadcmd` never sets `__name__` to `__main__`, which is why the project has its own
    predicate instead of the usual guard. Under plain CPython the usual guard is correct, and
    `corner_common` imports FreeCAD, so it is only reached when there is a kernel to import.
    """
    if name == '__main__':
        return True
    try:
        from corner_common import is_entry_point
    except ImportError:
        return False
    return is_entry_point(name)


if _is_entry_point(__name__):
    main()
