"""OQ-DES-CW25: real TechDraw cross-sections of the geometry Metric A is measured on.

**Why this replaces a hand-drawn figure.** An earlier attempt at this drew the sections as SVG
polylines from exported coordinates. That is a second implementation of projection, it owns every
error it makes, and it produced exactly the failure the method invites: a "contact" view 0.30 mm
across in which the quantity it claimed to show, 81 nm, is 0.12 of a pixel. Here the geometry is
sectioned by the kernel and projected by TechDraw, so the drawing is the model's own and the only
choices left are scale and what to put beside it.

**What is drawn.** A `nose_cowl_shell` cavity is built as one 45 degree symmetry cell and
mirrored, and a buttress rib stands on the cell plane `x` = 0. So per station:

* the **cell view** -- the whole wedge: the fitted interior surface, the two radial cell cuts, and
  the tool cropped to the cell's own radial reach, with the detail window marked on it;
* the **detail** at 13:1 -- a window anchored on where the fitted surface crosses the cell plane,
  holding the surface and its mirror, the 0.100 mm slab, the 0.600 mm dilation, and a dimension
  spine for each of the two reaches.

**The anchor is the surface, not the tool, and that is the whole design.** The first revision
centered a +/- 1.1 mm window on the tool's end at 42:1. Everything in that window is a straight
vertical line -- two cheeks, two dilated faces, and the cell plane between the cheeks -- the two
stations differed by one line in a bundle of five, and the caption read the cell plane as the
interior surface, which is 3.65 mm from where the surface actually is. Anchored on the surface,
the two sheets put it at the same height and what moves between them is the tool's end: at
`z` = -36.9470 the slab reaches 3.651 mm into the cavity, which is the rib; at `z` = -8.0479 it
stops 0.409 mm short of the cavity and there is no rib at all.

There is deliberately **no view of "the contact itself"**, because there is nothing there to draw.
At the worst station the two boundaries *intersect*: the reported 81 nm is the residue of a
minimum taken between two discretized boundaries that cross, not a gap. A view magnified until
81 nm is visible would be two coincident lines, and the honest statement is the measured overlap
area, which this module computes from the kernel and puts on the sheet as a note.

**Metric A's own figure goes on the sheet, and that was a regression to fix.** The hand-drawn
figures this replaced printed `Metric A = 81 nm` in their legend; the first TechDraw revision
named the quantity without ever printing it. What was left was a drawing of a 0.600 mm dilation
working correctly, with no sign anywhere on it of the problem it was drawn to show -- a figure a
reader can only read as geometry behaving exactly as intended. The figure's subject is the
number, so the number is note 9, beside the statement that it is not a clearance.

**Built headless, rendered by the GUI binary, which is this project's established split**
(`tools/render_sheets.py`, IP-FC-129): `freecadcmd` has no Qt and therefore no TechDraw page
renderer, while `freecad.exe` from the same install renders pages under
`QT_QPA_PLATFORM=offscreen`. So this writes a `.FCStd` and `render_sheets.py` turns it into SVG
and PDF.

Run it as::

    freecadcmd clearance_sheet.py --pass --kind=nose_cowl_shell --pass --u=1.0
    python ../tools/render_sheets.py --out <the out dir this printed>

`freecadcmd`'s exit code is unreliable, so read the log and the files.
"""
import io
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

import FreeCAD as App
import Part

import cowl_interior as ci
import cowl_tree
import drawing
import drawing_standard as std
import soak_cowl_shell as soak
from corner_common import is_entry_point

V = App.Vector

#: The two stations drawn, chosen from IP-FC-148's own scan of this configuration: the worst
#: reported figure, which is a `crossing`, and the one station of fifteen that is a real `clear`.
STATIONS = {'nose_cowl_shell': {1.0: (-36.9470, -8.0479)}}

#: The detail window in mm, measured from where the fitted interior surface crosses the cell
#: plane the rib stands on.
#:
#: **Anchored on the surface, not on the tool.** The first revision centered the window on the
#: tool's own end at +/- 1.1 mm and 42:1, and at that magnification every curve in it is a
#: straight vertical line: the two cheeks, the two dilated faces, and -- between the cheeks --
#: the cell plane. Nothing in the picture said which line was which, and the two stations
#: differed by one line in a bundle of five. Anchoring on the surface instead puts the surface
#: at the same height on both sheets, so the thing that moves between them is the tool's end,
#: which is the comparison the section is making.
DETAIL_X_MM = (-2.0, 3.0)
DETAIL_Y_MM = (-5.0, 2.0)

#: Scales. The cell view is fitted; the detail is fixed so the two stations are comparable.
DETAIL_SCALE = 13.0

#: Where the dimension spines stand, in mm from the cell plane, and how far their ticks reach.
DIM_X_MM = (-1.55, 1.65)
DIM_TICK_MM = 0.35

#: Surface-outline point counts at which Metric A is re-measured on each drawn station. The tool
#: gets twice each count, which is the 200/400 ratio `_min_wire_distance` ships.
#:
#: **This is the measurement the whole figure exists to support, so it is taken here rather than
#: quoted.** Metric A is a sampled quantity: `_min_wire_distance` reduces one outline to points
#: and the other to chords and returns the least point-to-chord distance. At a station where the
#: two outlines cross, the exact distance is zero and that method cannot return it, because no
#: sample is a crossing point. What it returns instead is a leftover, and re-running it at other
#: densities on geometry that has not changed is what shows the leftover for what it is.
#:
#: Measured on `nose_cowl_shell` at `U` = 1, `z` = -36.9470: 0.000081 mm at the shipped 200/400,
#: and 0.000081 to 0.216 mm across this range -- a factor of 2700, no convergence toward the
#: exact zero, and `CLEARANCE_MARGIN_MM` crossed in both directions. A flagged station is
#: therefore a fact about where the samples fell, not about the part.
#:
#: **An earlier revision swept the station instead of the sampling**, on the since-withdrawn
#: account that the figure was the distance from the sampled station to a crossing. Moving the
#: station does move the figure smoothly, but that is the samples moving with the section; the
#: sampling sweep is what distinguishes the two, because a real distance would survive it.
METRIC_A_DENSITIES = (100, 150, 200, 250, 300, 400, 600, 1000, 2000, 5000, 20000)

#: The sampling `_min_wire_distance` ships, and so the one the scan's own figures come from.
METRIC_A_SHIPPED = 200

#: Step, in mm, for the census of a tool's whole axial run.
#:
#: **This is the measurement that decides OQ-DES-CW25, and it is one line of output.** Metric A
#: is a clearance between the interior surface's section and the dilated tool's section. Section
#: 4.2 forms a rib by cutting `dilate(B, t)` out of the cavity, so a tool doing any work must
#: overlap the cavity; overlapping regions have crossing boundaries; crossing boundaries have no
#: clearance between them. The census checks that reasoning against the kernel at every station
#: of the run rather than at the two the figures draw, and on `nose_cowl_shell` at `U` = 1 it
#: returns 160 crossing and 0 apart.
#:
#: So the quantity is identically zero wherever it can be evaluated, every non-zero figure the
#: scan has reported is error, and its flag list is the stations where that error was smallest.
#: The sampling sweep above says the reported figures are arbitrary; this says there are no
#: right ones to report. 0.25 mm is well under the 1.0 mm coarse step the scan itself uses.
CENSUS_STEP_MM = 0.25

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'cw25')


#: A template that draws nothing, on a sheet large enough to hold the figure.
#:
#: **A `DrawPage` cannot exist without one** -- building a page with `Template` unset raises
#: *"Template not set for Page"* at recompute. The project's ANSI A template is the wrong one
#: for a documentation figure: it carries a border, a revision box and a parts block, none of
#: which says anything about a clearance, and it crowds the geometry and clips any label placed
#: past its frame. So the page gets a blank one. Nothing is drawn by it, and `render_pages`'
#: figure mode crops to the content rather than to the sheet, so the size never shows.
#:
#: **The sheet size is the figure size, and both matter.** The first revision made it 10 x 10 mm
#: on the reasoning that a blank template's size cannot matter. It does, twice over. Every view
#: and annotation was then off-sheet, TechDraw logged *"larger than page. Will be scaled."* for
#: each one, and the figure crop picked up an off-sheet object and returned a 627 mm tall raster
#: for 166 mm of drawing. And a page's own frame is an item in the scene, so the crop can never
#: come in tighter than the sheet: sizing the sheet to the layout is how the figure gets a tight
#: margin. It also has to be big enough for every label, because the crop is clamped to the
#: sheet and a label past the edge is cut off -- which is the complaint this figure started from.
SHEET_MM = (270.0, 255.0)

#: Where the two views and the note block sit on that sheet, in mm. The views sit high enough
#: that the note clears them: at eight notes the block is about 60 mm tall, and the detail view
#: is 91 mm tall about its own center, so the two met when the views sat at 108. Adding the
#: Metric A note took the block to sixteen lines, about 72 mm, which met them again at 120 and
#: at 130 -- at 130 the block's own first line was drawn across the detail view's bottom edge.
#: An annotation's X and Y are the center of its text block, and its width is `MaxWidth`, so
#: the block spans 200 mm and sits under both views however it is placed: the separation has to
#: be vertical. Measured off the render: at 270 x 240 mm with the views at 155, the block's
#: twenty-one lines spanned 19.0 to 99.7 mm and the detail view's lower edge sat at 111.4 mm,
#: an 11.7 mm separation. Saying what Metric A *is* on the sheet, rather than only printing
#: it, took the block to twenty-five lines, so the sheet and both anchors moved up together to
#: keep that separation and keep the last line on the paper.
CELL_AT = (58.0, 163.0)
DETAIL_AT = (178.0, 163.0)
NOTE_AT = (148.0, 55.0)

BLANK_TEMPLATE = '\n'.join([
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
    '<svg xmlns="http://www.w3.org/2000/svg" version="1.1"',
    '     width="%gmm" height="%gmm" viewBox="0 0 %g %g">' % (SHEET_MM + SHEET_MM),
    '  <!-- deliberately empty: a documentation figure has no frame, no title block -->',
    '</svg>',
    ''])


def _blank_template_path(out_dir):
    """Write the blank template beside the figures and return its path.

    It lives with the output rather than in the drawing standard's resources because it is not
    part of the standard -- nothing is ever issued on it.
    """
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'figure_blank.svg')
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(BLANK_TEMPLATE)
    return path


def _opt(name, default=None):
    for arg in sys.argv:
        if arg.startswith('--%s=' % name):
            return arg.split('=', 1)[1]
    return default


def _section(shape, z):
    """The kernel's own planar section of `shape` at `z`, as a list of wires."""
    try:
        return [w for w in shape.slice(V(0, 0, 1), z) if w]
    except Exception:                                                   # noqa: BLE001
        return []


def _face_area(wires):
    """Area enclosed by a section, through faces built on its wires.

    `Face.Area` is unreliable on B-spline faces in this project (section 9.6), but these are
    planar sections of planar wires, which is the case it is exact on.
    """
    total = 0.0
    for wire in wires:
        try:
            total += abs(Part.Face(wire).Area)
        except Exception:                                               # noqa: BLE001
            pass
    return total


def _overlap_area(a_wires, b_wires):
    """Area where two sections overlap, in mm^2 -- the number that says they intersect."""
    def faces(wires):
        out = []
        for wire in wires:
            try:
                out.append(Part.Face(wire))
            except Exception:                                           # noqa: BLE001
                pass
        return out

    total = 0.0
    for fa in faces(a_wires):
        for fb in faces(b_wires):
            try:
                common = fa.common(fb)
                total += sum(abs(f.Area) for f in common.Faces)
            except Exception:                                           # noqa: BLE001
                pass
    return total


def _run_census(surf, tool, step=CENSUS_STEP_MM):
    """Classify every station of `tool`'s axial run: do the two outlines cross, or are they apart?

    Returns `(crossing, apart, absent, gaps)`, where `gaps` lists `(z, distance)` for any station
    that really does have a clearance. `distToShape` is exact, so a zero here is a zero and not a
    tolerance: `apart` being 0 means the clearance Metric A reports never exists.
    """
    bb = tool.BoundBox
    crossing = apart = absent = 0
    gaps = []
    steps = int((bb.ZMax - bb.ZMin) / step)
    for i in range(steps + 1):
        z = bb.ZMin + i * step
        s_w = [w for w in ci._slice_wires(surf, z) if w]
        t_w = [w for w in ci._slice_wires(tool, z) if w]
        if not (s_w and t_w):
            absent += 1
            continue
        d = min(a.distToShape(b)[0] for a in s_w for b in t_w)
        if d < 1.0e-9:
            crossing += 1
        else:
            apart += 1
            gaps.append((z, d))
    return crossing, apart, absent, gaps


def _metric_a_at(wires_a, wires_b, n_a, n_b):
    """`_min_wire_distance`'s own computation with its sampling counts exposed.

    Deliberately a re-implementation of three lines rather than a call: the point of the sweep
    is to vary the two `Number` arguments that function hard-codes, and it takes neither. It
    reproduces that function exactly at `n_a` = 200, `n_b` = 400 -- measured 0.000080625 mm at
    `nose_cowl_shell` `U` = 1, `z` = -36.9470, against the scan's own 0.000081 -- which is what
    makes the rest of the sweep comparable to a shipped figure.
    """
    a_pts = []
    for w in wires_a:
        a_pts.extend((p.x, p.y) for p in w.discretize(Number=n_a))
    if not a_pts:
        return None
    best = None
    for w in wires_b:
        pts = [(p.x, p.y) for p in w.discretize(Number=n_b)]
        if len(pts) < 2:
            continue
        d = float(min(ci._Polyline(pts).distances(a_pts)))
        if best is None or d < best:
            best = d
    return best


def _rect(x0, x1, y0, y1, z):
    """The window as a closed polygon, in the section plane."""
    return Part.makePolygon([V(x0, y0, z), V(x1, y0, z), V(x1, y1, z),
                             V(x0, y1, z), V(x0, y0, z)])


def _window(wires, x0, x1, y0, y1, z):
    """Keep only the parts of `wires` inside a rectangle.

    **Why not clip the solid.** Intersecting the solid with a box and sectioning the result
    puts the box's own four faces into the section, and at the detail scale that rectangle is
    the biggest thing on the drawing -- an artifact of the clipping, drawn in the same line as
    the geometry it was supposed to isolate. Trimming the section curves against a planar face
    keeps the real edges and adds none.

    The detail view draws the window outline as well, but as a deliberate detail frame matching
    the marker on the cell view, not as a leftover of the clip: it is what makes the two sheets
    frame identically, since without it each view would center on its own geometry's extent and
    the surface would land at a different height on each.
    """
    face = Part.Face(_rect(x0, x1, y0, y1, z))
    kept = []
    for wire in wires:
        try:
            inside = wire.common(face)
        except Exception:                                               # noqa: BLE001
            continue
        for edge in inside.Edges:
            if edge.Length > 1.0e-9:
                kept.append(Part.Wire([edge]))
    return kept


def _is_radial(edge, tol=1.0e-6):
    """Is this a straight edge whose line passes through the part axis?

    That is the test for a cell-cut edge: `cavity` builds one 45 degree wedge and mirrors it,
    so a cell section is bounded by the fitted interior surface and by two radial planes.
    """
    if type(edge.Curve).__name__ != 'Line':
        return False
    a, b = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
    dx, dy = b.x - a.x, b.y - a.y
    span = math.hypot(dx, dy)
    if span < tol:
        return False
    return abs(dx * a.y - dy * a.x) / span < tol


def _surface_only(wires):
    """The fitted interior surface, with the cell's own cut edges dropped.

    **The cut edges are not interior surface and drawing them was the figure's worst error.**
    The rib stands on the cell plane `x` = 0, so that cut edge runs down the exact middle of the
    0.100 mm slab, 0.050 mm from each cheek. At any scale that resolves the slab it is a third
    line inside the tool, and the published first revision's caption read it as the interior
    surface -- which put the surface 3.65 mm from where it is.
    """
    return [Part.Wire([e]) for w in wires for e in w.Edges if not _is_radial(e)]


def _mirrored(shapes):
    """`shapes` reflected in the cell plane `x` = 0 -- the neighbor the build itself makes.

    `cavity` builds one cell and mirrors it, so the surface on the far side of the cell plane is
    this surface reflected, exactly. Drawing both halves is what makes the crossing legible: the
    surface then runs *through* the tool instead of stopping dead at its centerline.
    """
    return [s.mirror(V(0, 0, 0), V(1, 0, 0)) for s in shapes]


def _dim(x, y_a, y_b, z, tick):
    """A dimension spine and its two ticks, from measured coordinates.

    Not a `TechDraw::DrawViewDimension`: those reference projected sub-elements, which is the
    dimensioning work still open under IP-FC-153. This is annotation geometry whose endpoints
    are the kernel's own numbers and which is projected in the same view as the geometry it
    measures, so it cannot be out of register with it.
    """
    return [Part.makePolygon([V(x, y_a, z), V(x, y_b, z)]),
            Part.makePolygon([V(x, y_a, z), V(x + tick, y_a, z)]),
            Part.makePolygon([V(x, y_b, z), V(x + tick, y_b, z)])]


def _scale_text(scale):
    """`2.5:1` or `1:2.5` -- a magnified view is not `1:0`, which is what rounding gave."""
    return ('%.1f:1' % scale) if scale >= 1.0 else ('1:%.1f' % (1.0 / scale))


def _feature(doc, name, wires):
    obj = doc.addObject('Part::Feature', name)
    obj.Shape = Part.makeCompound(wires)
    return obj


def build(kind, u, out_dir):
    started = time.time()
    doc = App.newDocument('cw25_sheet')
    tip = cowl_tree.emit(doc, None, soak.with_u(soak.BASE_PARAMS[kind], u),
                         getattr(cowl_tree, kind))
    doc.recompute()
    notches = Part.makeCompound([n.Shape for n in tip.Notches])
    body, notched, t = tip.Body.Shape, tip.Base.Shape, float(tip.Inset)
    ci.note('cw25 sheet: emit+recompute %.0f s, t = %.4f mm' % (time.time() - started, t))

    report = {}
    at = time.time()
    ci.cavity(body, notched, notches, t, tip.Overhang, report=report)
    smooth = report['smooth_shape']
    ribs = ci.dilated_notches(notches, t)
    ci.note('cw25 sheet: cavity %.0f s; smooth %.1f mm3, %d dilated tool(s)'
            % (time.time() - at, smooth.Volume, len(ribs)))

    raw = notches.Solids[0]
    dilated = ribs[0]

    # **The claim the sheet rests on, measured rather than asserted.** If the dilated tool and
    # the interior candidate share volume, then at the stations where they meet the in-plane
    # distance between their boundaries is zero and any small figure reported there is a
    # discretization residue.
    penetration = 0.0
    try:
        penetration = smooth.common(dilated).Volume
    except Exception:                                                   # noqa: BLE001
        pass
    ci.note('cw25 sheet: dilated tool inside the interior candidate: %.4f mm3' % penetration)

    # The census of the whole run, which is what OQ-DES-CW25 now turns on.
    at = time.time()
    crossing, apart, absent, gaps = _run_census(smooth, dilated)
    ci.note('cw25 sheet: run census at %.2f mm: %d crossing, %d apart, %d with no section '
            '(%.0f s)' % (CENSUS_STEP_MM, crossing, apart, absent, time.time() - at))
    if apart:
        ci.note('cw25 sheet:   smallest real clearance %.6f mm at z=%.4f'
                % min(gaps, key=lambda g: g[1])[::-1])
    else:
        ci.note('cw25 sheet:   no station of the run has a clearance to measure')

    facts = dict(kind=kind, u=float(u), t=t, penetration_mm3=penetration,
                 cut_thickness=float(doc.getObject('Params').get('buttress_cut_thickness')),
                 rib_facets=ci.RIB_FACETS, stations=[],
                 census=dict(step_mm=CENSUS_STEP_MM, crossing=crossing, apart=apart,
                             absent=absent, gaps=gaps))

    z_lo, z_hi = ci.z_extent(body)
    # Pages must be named `Page`, `Page2`, ... -- `sheet_naming.page_number` refuses
    # anything else, and `render_sheets.py` sorts by it, so a descriptive page name costs
    # the render. The station goes in the view and feature names instead.
    for page_index, z in enumerate(STATIONS[kind][float(u)], start=1):
        s_wires = _section(smooth, z)
        d_wires = _section(dilated, z)
        r_wires = _section(raw, z)
        if not (s_wires and d_wires):
            ci.note('cw25 sheet: nothing to section at z=%.4f' % z)
            continue
        overlap = _overlap_area(s_wires, d_wires)
        row = dict(z=z, surface_area=_face_area(s_wires), tool_area=_face_area(d_wires),
                   overlap_area=overlap)
        row['overlap_fraction'] = (overlap / row['tool_area']) if row['tool_area'] else None

        # **The three numbers the figure exists to show**, all along the cell plane the rib
        # stands on: where the fitted interior surface is, where the real slab's inner end is,
        # and where the dilated tool's is. Positive reach means *into the cavity*, which is
        # what a rib is; negative means the tool stops short of the cavity altogether.
        surf_edges = _surface_only(s_wires)
        on_plane = [v.Point.y for w in surf_edges for v in w.Vertexes if abs(v.Point.x) < 1.0e-6]
        y_surf = max(on_plane) if on_plane else max(w.BoundBox.YMax for w in surf_edges)
        y_slab = min(w.BoundBox.YMin for w in r_wires)
        y_dil = min(w.BoundBox.YMin for w in d_wires)
        row['surface_y'] = y_surf
        row['slab_reach'] = y_surf - y_slab
        row['dilated_reach'] = y_surf - y_dil

        # **Metric A itself, measured here rather than quoted.** The figure exists to say what
        # this number is worth, so the number has to be on the sheet. `clearance_margin_scan`
        # costs about an hour because it samples a whole cowl adaptively; the per-station
        # quantity it reports is one `tool_clearance_ranked` call, which is cheap. Calling the
        # scan's own function means the sheet cannot drift from what the scan would print.
        ranked = ci.tool_clearance_ranked(smooth, ribs, z)
        row['metric_a'] = ranked[0][1] if ranked else None

        # **The exact answer, from the kernel, against the sampled one.** `distToShape` on the
        # two section wires is the real in-plane distance and returns 0.0 where they cross;
        # `section` gives the crossing points themselves, so the zero is not a tolerance
        # artifact. Metric A is measured against this, not the other way round.
        row['exact_distance'] = min(a.distToShape(b)[0] for a in s_wires for b in d_wires)
        row['crossing_points'] = sum(len(a.section(b).Vertexes)
                                     for a in s_wires for b in d_wires)

        # **And the sampled figure's dependence on its own sampling**, which is what says
        # whether it is a measurement at all. Each entry is one more `_min_wire_distance` on
        # wires already in hand.
        sweep = []
        for n in METRIC_A_DENSITIES:
            got = _metric_a_at(s_wires, d_wires, n, 2 * n)
            sweep.append(dict(surface_points=n, tool_segments=2 * n, metric_a=got,
                              flagged=bool(got is not None and got < ci.CLEARANCE_MARGIN_MM)))
        row['metric_a_sweep'] = sweep
        seen = [e['metric_a'] for e in sweep if e['metric_a'] is not None]
        if seen:
            row['metric_a_span'] = (min(seen), max(seen))
            row['metric_a_ratio'] = (max(seen) / min(seen)) if min(seen) > 0.0 else None
            row['flag_is_sampling_dependent'] = (
                len(set(e['flagged'] for e in sweep)) > 1)
        facts['stations'].append(row)
        ci.note('cw25 sheet: z=%.4f  tool section %.4f mm2, overlap %.4f mm2 (%.2f%%)'
                % (z, row['tool_area'], overlap, 100.0 * (row['overlap_fraction'] or 0.0)))
        ci.note('cw25 sheet:   surface at y=%.4f; slab reaches %+.4f, dilated %+.4f '
                '(+ = into the cavity)' % (y_surf, row['slab_reach'], row['dilated_reach']))
        ci.note('cw25 sheet:   exact in-plane distance %.12f mm, %d boundary crossing(s)'
                % (row['exact_distance'], row['crossing_points']))
        ci.note('cw25 sheet:   Metric A here reads %s mm'
                % ('%.6f' % row['metric_a'] if row['metric_a'] is not None else 'nothing'))
        for e in sweep:
            ci.note('cw25 sheet:     %6d/%-6d  %s mm  %s%s'
                    % (e['surface_points'], e['tool_segments'],
                       '%.9f' % e['metric_a'] if e['metric_a'] is not None else 'nothing',
                       'FLAGGED' if e['flagged'] else 'not flagged',
                       '   <- as shipped'
                       if e['surface_points'] == METRIC_A_SHIPPED else ''))
        if row.get('metric_a_ratio'):
            ci.note('cw25 sheet:   sampling alone moves Metric A by %.0fx; flag %s'
                    % (row['metric_a_ratio'],
                       'flips' if row['flag_is_sampling_dependent'] else 'holds'))

        tag = ('%+0.4f' % z).replace('.', 'p').replace('-', 'm').replace('+', 'p')

        # **A page with no template: no frame, no title block, no sheet size.**
        # These are documentation figures, not released drawings. The project's ANSI A
        # template exists so a drawing can be issued -- it carries a border, a revision box
        # and a parts block, none of which says anything about a clearance -- and on a figure
        # it is just furniture that crowds the geometry and clips any label placed past it.
        # `render_pages` crops a figure to its own content instead, so there is nothing for a
        # label to fall outside of, and paints it on white, so it survives a dark-themed
        # viewer. Published as PNG for the same reason: an SVG export carries no background.
        page = doc.addObject('TechDraw::DrawPage', 'Page' + ('' if page_index == 1
                                                             else str(page_index)))
        blank = doc.addObject('TechDraw::DrawSVGTemplate', 'Blank' + tag)
        blank.Template = _blank_template_path(out_dir)
        page.Template = blank

        # Plain page coordinates, chosen for the two views rather than taken from a frame.
        left_at, right_at = CELL_AT, DETAIL_AT

        # **One view per region, holding every curve, and NOT one view per curve.**
        #
        # An earlier revision put the interior surface, the dilated tool and the real slab in
        # three `DrawViewPart`s overlaid at one page position so each could be styled apart.
        # They do not register: `drawing.add_view` sets `view.X/Y` to the region center and
        # TechDraw then centers the projected geometry on *its own source's* extent, so three
        # sources of different extent land three different ways. The slab's section is
        # 0.100 mm wide and the dilated one 1.300 mm, and at 42:1 a 0.1 mm difference of bbox
        # centers is 4.2 mm of error on the sheet -- the drawing was showing the three curves
        # in wrong relative positions, which is the one thing a clearance figure must not do.
        # One projection of one compound cannot have that error.
        win = (DETAIL_X_MM[0], DETAIL_X_MM[1],
               y_surf + DETAIL_Y_MM[0], y_surf + DETAIL_Y_MM[1])
        row['window'] = win

        # **The whole sections, kept in the document although nothing draws them.** Both views
        # show cropped copies, so once the file is saved the figure's own inputs are gone and
        # any later question about them -- how a sampler lands on the tool's perimeter, say --
        # costs another 85 s build. A `Part::Feature` on no page is invisible to TechDraw, so
        # this adds nothing to the sheet and makes the sheet answerable.
        _feature(doc, 'SecFull' + tag, s_wires + d_wires + r_wires)

        # The cell, with its tool cropped to the cell's own radial reach. Uncropped the tool
        # runs out to y = 150 -- three times the cell's size -- and fitting that span shrank the
        # cell to a line with a wedge on it, which is what the first revision's left view was.
        cell_wires = (s_wires
                      + _window(d_wires + r_wires, -3.0, 3.0, 0.0, y_surf + 3.0, z)
                      + [_rect(*(win + (z,)))])
        cell = _feature(doc, 'SecCell' + tag, cell_wires)
        doc.recompute()
        cbox = cell.Shape.BoundBox
        span = max(cbox.XLength, cbox.YLength) or 1.0
        cell_scale = 70.0 / span
        cell_view = drawing.add_view(page, cell, (0.0, 0.0, 1.0), (1.0, 0.0, 0.0),
                                     cell_scale, (left_at[0], left_at[1], 0.0, 0.0),
                                     name='ViewCell' + tag)

        # The detail: the surface and its mirror, the tool, two dimension spines, two leaders,
        # and the window outline that makes both sheets frame identically.
        end_wires = _window(surf_edges + _mirrored(surf_edges) + d_wires + r_wires,
                            *(win + (z,)))
        end_wires += _dim(DIM_X_MM[0], y_surf, y_dil, z, DIM_TICK_MM)
        end_wires += _dim(DIM_X_MM[1], y_surf, y_slab, z, -DIM_TICK_MM)
        # Leaders, tails outside the window so they read as leaders rather than as geometry.
        # They put the compound's extent past the window, but by the same amount on both
        # sheets -- every coordinate here is either fixed or measured from `y_surf` -- so the
        # two still frame identically, which is the only thing the window outline was for.
        end_wires += [Part.makePolygon([V(-3.4, y_surf + 2.9, z),
                                        V(-0.65, y_surf + 1.4, z)]),
                      Part.makePolygon([V(4.4, y_surf + 2.9, z),
                                        V(0.05, y_surf + 1.4, z)])]
        end_wires += [_rect(*(win + (z,)))]
        end = _feature(doc, 'SecEnd' + tag, end_wires)
        doc.recompute()
        end_view = drawing.add_view(page, end, (0.0, 0.0, 1.0), (1.0, 0.0, 0.0),
                                    DETAIL_SCALE, (right_at[0], right_at[1], 0.0, 0.0),
                                    name='ViewEnd' + tag)
        doc.recompute()

        def label(view, model_xy, text, dx=0.0, dy=0.0, size=3.0, width=90.0):
            """Put `text` where `model_xy` landed in `view`.

            Computed from the view's own centring rule -- the view's page position, plus the
            model offset from the center of its source, times the scale -- so a label tracks
            the geometry instead of being placed by eye.
            """
            box = view.Source[0].Shape.BoundBox
            cx = (box.XMin + box.XMax) / 2.0
            cy = (box.YMin + box.YMax) / 2.0
            ann = doc.addObject('TechDraw::DrawViewAnnotation',
                                'Lbl%s%d' % (tag, len(doc.Objects)))
            ann.Text = [text]
            ann.TextSize = size
            ann.MaxWidth = width
            page.addView(ann)
            ann.X = view.X.Value + (model_xy[0] - cx) * view.Scale + dx
            ann.Y = view.Y.Value + (model_xy[1] - cy) * view.Scale + dy
            return ann

        # Labels are offset clear of the geometry they name; the offsets are in page mm and
        # were set by looking at the render, which is the only way to know a label collides.
        # **`wall material` and `cavity` are the two that make the figure self-explanatory**:
        # with the sides of the surface named, a band reaching across it reads as a rib without
        # any caption at all.
        label(end_view, (win[1], y_surf), 'fitted interior surface',
              dx=30.0, size=2.9, width=44.0)
        label(end_view, (2.45, y_surf + 0.9), 'wall', size=2.9, width=16.0)
        label(end_view, (2.45, y_surf - 0.9), 'cavity', size=2.9, width=18.0)
        label(end_view, (-3.4, y_surf + 2.9), 'dilated tool (slab + %.3f mm)' % t,
              dx=-4.0, dy=7.0, size=2.9, width=46.0)
        label(end_view, (4.4, y_surf + 2.9),
              'buttress slab, %.3f mm' % facts['cut_thickness'],
              dx=6.0, dy=7.0, size=2.9, width=40.0)
        label(end_view, (DIM_X_MM[0], (y_surf + y_dil) / 2.0),
              '%.3f' % abs(row['dilated_reach']), dx=-8.0, size=2.9, width=22.0)
        # Clear of its own spine: where the slab stops short the spine is only 0.4 mm long and
        # a label on its midpoint lands on the line it is measuring.
        label(end_view, (DIM_X_MM[1], (y_surf + y_slab) / 2.0),
              '%.3f' % abs(row['slab_reach']), dx=14.0, size=2.9, width=22.0)

        label(cell_view, (cbox.XMin, cbox.YMax),
              '%s at U = %g, one 45 deg symmetry cell' % (kind, u),
              dy=22.0, dx=26.0, size=3.4, width=80.0)
        label(cell_view, (cbox.XMin, cbox.YMax), 'station z = %.4f mm' % z,
              dy=15.0, dx=26.0, size=3.4, width=80.0)
        label(cell_view, (cbox.XMax * 0.5, cbox.YMin),
              'the two straight edges are cell cuts', dy=-6.0, size=2.9, width=50.0)

        # **Numbered notes, one statement each, the way a drawing carries them.** The first
        # revision put this block in prose and it read as a paragraph dropped on a drawing.
        # Every number is the kernel's, measured above, not a caption typed onto a figure, and
        # the two notes about the rib are chosen by the sign of the measurement, so the sheet
        # cannot describe a station as crossing that does not.
        rib = (('5. The slab reaches %.3f mm into the cavity. That overlap is the rib.'
                % row['slab_reach']) if row['slab_reach'] > 0.0 else
               ('5. The slab stops %.3f mm short of the cavity. No rib forms here.'
                % abs(row['slab_reach'])))
        # **Note 6 is what note 7 then contradicts**, so it names both curves rather than
        # saying "in": the reader has to be able to see that the same two outlines carry the
        # penetration and the clearance, because that is the whole argument.
        dil = ([('6. The dilated tool crosses the fitted interior surface and reaches'),
                ('   %.3f mm past it, into the cavity.' % row['dilated_reach'])]
               if row['dilated_reach'] > 0.0 else
               [('6. The dilated tool stops %.3f mm short of the fitted interior'
                 % abs(row['dilated_reach'])),
                ('   surface, so it does not cross it at this station.')])

        # **The note the sheet exists for.** Naming Metric A without printing it left the
        # drawing showing a correct 0.600 mm dilation and no sign of the problem, which is a
        # drawing of the construction working rather than of the metric failing. The wording is
        # chosen by the measured overlap, so the sheet cannot call a figure worthless at a
        # station where the outlines really are apart.
        if row['metric_a'] is None:
            metric_note = ['9. Metric A reports nothing at this station.']
        elif overlap > 0.0:
            lo, hi = row.get('metric_a_span', (None, None))
            # **A number on a drawing has to say what it is.** An earlier revision printed
            # "Metric A reports 0.000584 mm and flags the station as under 0.010 mm", which
            # states two figures and defines neither: a reader cannot tell what the quantity
            # measures, which way is bad, or what the right answer would have been.
            metric_note = [
                '8. Metric A is the clearance between those same two outlines -- the',
                '   fitted interior surface and the dilated tool -- and the scan warns',
                '   on any station below %.3f mm, since a tool that close to the cavity'
                % ci.CLEARANCE_MARGIN_MM,
                '   leaves no material between the slot and the inside of the part.',
                '9. Note 6 is the same pair of outlines %.3f mm PAST each other, so they'
                % abs(row['dilated_reach']),
                '   cross. Crossing outlines have no clearance between them. The correct',
                '   value of Metric A here is 0.000 mm, and the scan reports %.6f.'
                % row['metric_a'],
            ]
            if lo is not None and hi is not None:
                metric_note += [
                    '10. That figure is not a clearance but a leftover: the scan lays 200',
                    '   points round the cavity outline and takes the nearest one, and',
                    '   none sits on a crossing, so zero is unreachable. Varying only the',
                    '   point count, %d to %d, gives %.6f to %.3f mm -- every one of them'
                    % (METRIC_A_DENSITIES[0], METRIC_A_DENSITIES[-1], lo, hi),
                    '   wrong, with the %.3f mm warning line inside the range.'
                    % ci.CLEARANCE_MARGIN_MM,
                ]
        else:
            metric_note = [
                '9. Metric A reports %.6f mm here, and the outlines do not' % row['metric_a'],
                '   intersect at this station, so it is a real in-plane distance.',
            ]
        # The probe's own spread is deliberately *not* a note. It is a fact about the
        # instrument, not about this station's geometry, so it belongs in the design document's
        # section on the instrument's limits; the sheet records it in the JSON and the log. A
        # drawing already carrying nine notes does not need a tenth that the reader cannot
        # check against anything drawn.
        note = doc.addObject('TechDraw::DrawViewAnnotation', 'NoteFacts' + tag)
        note.Text = [
            'LEFT: one 45 deg symmetry cell, %s.    RIGHT: the boxed region, %s.'
            % (_scale_text(cell_scale), _scale_text(DETAIL_SCALE)),
            '',
            '1. Two radial planes cut the cell from its neighbors. Those cuts are not',
            '   interior surface. The detail view leaves them out.',
            '2. The surface left of the tool is this cell mirrored, as the build makes it.',
            '3. Wall t = %.3f mm. The buttress slab is %.3f mm thick.'
            % (t, facts['cut_thickness']),
            '4. The dilation is %d copies of the slab, each shifted t horizontally and'
            % facts['rib_facets'],
            '   fused. At the slab\'s end they trace the polygon drawn here, not a round end.',
            rib,
        ] + dil + [
            # Planar, and about this section: how much of the drawn tool outline is inside
            # the drawn surface outline. The 3-D volume that used to stand here was a
            # non-sequitur on a sheet whose whole subject is one horizontal slice.
            '7. Of the tool\'s %.3f mm2 section, %.4f mm2 (%.2f %%) lies inside the surface.'
            % (row['tool_area'], overlap, 100.0 * (row['overlap_fraction'] or 0.0)),
        ] + metric_note
        note.TextSize = 3.0
        note.MaxWidth = 200.0
        page.addView(note)
        note.X, note.Y = NOTE_AT
        doc.recompute()

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    stem = os.path.join(out_dir, 'cw25_%s_u%g' % (kind, u))
    doc.saveAs(stem + '.FCStd')
    with io.open(stem + '.json', 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(facts, indent=1, sort_keys=True))
    ci.note('cw25 sheet: wrote %s.FCStd and .json in %.0f s' % (stem, time.time() - started))
    return stem


def main():
    kind = _opt('kind', 'nose_cowl_shell')
    u = float(_opt('u', '1.0'))
    out_dir = os.path.normpath(_opt('out-dir', OUT_DIR))
    build(kind, u, out_dir)


if is_entry_point(__name__):
    main()
