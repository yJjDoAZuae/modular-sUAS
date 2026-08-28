"""IP-FC-21: the family drawing, built.

Everything else in this corner of the project decides *what* a drawing says and *where* the
annotations go; this is what turns those into a TechDraw page. It is the last piece and it is
deliberately thin, because each thing it needs was settled somewhere it could be checked:

    `drawing_standard`   the sheet -- template, font, precision, and the packing OQ-DES-D5
                         decided: title block and value table in a band across the bottom,
                         the drawn view the full width above them
    `dimension_placement`  where each annotation goes, and a refusal when they will not go
    `drawing_families`   which variants share a sheet and what the value table holds

**How a dimension binds to the model rather than to the projection.** `makeCosmeticVertex3d`
takes a point in *model* coordinates and the view projects and scales it, so a dimension can
reference two points computed by arithmetic on the parameters. That is the whole of why this
does not ask the projection what its edges are called: IP-FC-5 showed face and edge names move
with `U`, so `Vertex4` means a different vertex on a different variant and the drawing would be
wrong in a way that renders.

**The trap is the index.** Cosmetic vertices are appended after the projected ones, so a
reference is `Vertex(n_geometric + i)` and `n_geometric` moves with the variant. It is read
immediately before the vertices are made, never cached.

**The scale is searched, not chosen.** The largest preferred scale whose annotations all place
is the one used, which serves OQ-DES-D5's requirement from the other end: the view is as large
as the sheet can carry rather than as large as a constant says. A part whose annotations do not
place at any scale is a refusal, per section 5.6 -- the remedy is to split the view, which is a
drafting decision made deliberately.

Run:

    freecadcmd drawing.py --pass --kind corner --params p.json --out sheet.dxf

**Unit regime: millimeters** on both sides. Model coordinates are millimeters because the
OpenSCAD path is; page coordinates are millimeters because a page is.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import build_part
import dimension_placement as dp
import part_kinds
import drawing_standard as std
import sheet_annotations
import sheet_table

from sheet_annotations import FAMILY, VARIANT

from corner_common import is_entry_point

V = App.Vector
NEWLINE = chr(10)

# ISO 5455's preferred scales, largest first. A drawing is drawn at one of these or it is not
# to scale, and searching them in this order gives the largest view the sheet can carry.
PREFERRED_SCALES = (10.0, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01)

# How much of the view region the projected part may occupy before annotations are placed.
# Not a margin for its own sake: the annotations live outside the part's outline, and a part
# filling its region leaves them nowhere to go, so every scale would be refused and the
# refusal would say H1 rather than "too big". This makes the common case fail as arithmetic
# rather than as a search that always loses.
VIEW_FILL = 0.55

# `DrawViewAnnotation.LineSpace` is a percentage of the text height. Set on every annotation
# even though each now carries a single line, because a one-line annotation with the wrong
# line space is one edit away from being a wrong two-line one.
LINE_SPACE_PERCENT = int(round(dp.NOTE_LINE_PITCH_HEIGHTS * 100.0))



# ----------------------------------------------------------------------------------------
# Projection
# ----------------------------------------------------------------------------------------

def view_axes(direction, x_direction):
    """The view's own basis, as (x, y) unit vectors in model space.

    TechDraw projects onto the plane normal to `Direction`, with `XDirection` running right.
    The vertical is then their cross product, and taking it that way round rather than the
    other is what makes a dimension's sign agree with what the reader sees.
    """
    normal = V(direction).normalize()
    x_axis = V(x_direction).normalize()
    y_axis = normal.cross(x_axis).normalize()
    return x_axis, y_axis


def project(point, direction, x_direction, scale=1.0):
    """A model point in view coordinates -- millimeters on the page, origin at the view center.

    Arithmetic on the point, not a question to the projection. That is the binding rule this
    module exists to keep.
    """
    x_axis, y_axis = view_axes(direction, x_direction)
    vector = V(point)
    return (vector.dot(x_axis) * scale, vector.dot(y_axis) * scale)


def projected_bbox(shape, direction, x_direction, scale=1.0):
    """The projected extent of a shape, from its vertices.

    Vertices rather than the 3D bounding box: a box aligned to the model axes is not the
    extent of the projection unless the view happens to look down one of them, and the
    drawings this module makes do not all look down one.
    """
    points = [project(v.Point, direction, x_direction, scale) for v in shape.Vertexes]
    if not points:
        raise ValueError('the shape has no vertices, so nothing would be drawn')
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


# ----------------------------------------------------------------------------------------
# What a corner's sheet carries
# ----------------------------------------------------------------------------------------

ANNOTATIONS = sheet_annotations.ANNOTATIONS

# The direction each kind's representative view looks along, and which way is right on it.
# The corner is a constant section down the bay, so the section is the view that says the most
# about it; the bulkheads are plates, and the same direction shows their face.
VIEW_DIRECTION = {
    'corner': ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    'bulkhead': ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    'boom_bulkhead': ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
}


# ----------------------------------------------------------------------------------------
# The sheet
# ----------------------------------------------------------------------------------------

def add_page(doc):
    """A page carrying the project's template. Returns (page, template)."""
    std.require_standard()
    template = doc.addObject('TechDraw::DrawSVGTemplate', 'Template')
    template.Template = std.template_path()
    page = doc.addObject('TechDraw::DrawPage', 'Page')
    page.Template = template
    doc.recompute()
    return page, template


def view_region():
    """Where the drawn view goes, as (x, y, width, height) in page coordinates.

    Page coordinates run y *up* from the bottom left, where the template's own run y down from
    the top left, so this flips what `drawing_standard` reports. Getting that wrong puts the
    view where the title block is and nothing complains.
    """
    frame_x, frame_y, frame_w, frame_h = std.frame_region_mm()
    depth = std.table_band_depth_mm()
    sheet_h = std.TEMPLATE_HEIGHT_MM
    bottom = sheet_h - (frame_y + frame_h)
    return (frame_x, bottom + depth, frame_w, frame_h - depth)


def add_view(page, shape, direction, x_direction, scale):
    """The projected view, centerd in its region at `scale`."""
    doc = page.Document
    view = doc.addObject('TechDraw::DrawViewPart', 'View')
    page.addView(view)
    view.Source = [shape]
    view.Direction = V(*direction)
    view.XDirection = V(*x_direction)
    view.Scale = scale
    region = view_region()
    view.X = region[0] + region[2] / 2.0
    view.Y = region[1] + region[3] / 2.0
    doc.recompute()
    return view


def frame_in_view(view):
    """The view region expressed the way `dimension_placement` wants it.

    The placer works in view coordinates -- millimeters, origin at the view center -- so the
    frame it is given is the region translated by the view's position. Handing it page
    coordinates instead produces a layout that is correct about everything except where it is.
    """
    region = view_region()
    x = view.X.Value
    y = view.Y.Value
    return (region[0] - x, region[1] - y,
            region[0] + region[2] - x, region[1] + region[3] - y)


def table_anchor():
    """The value table's top-left corner, in page coordinates.

    `sheet_table` works in the table's own frame -- origin top-left, y downward, because that
    is reading order -- and the page's y runs upward. This is the one place the two meet, and
    it is a function rather than four lines inside the drawing loop so that getting it wrong
    is one failure rather than one per cell.
    """
    region = std.table_region_mm()
    frame_x, frame_y, frame_w, frame_h = std.frame_region_mm()
    sheet_h = std.TEMPLATE_HEIGHT_MM
    # The band sits at the bottom of the frame. In template coordinates that is the largest
    # y; on the page it is the smallest, and the table's *top* is one band depth above it.
    bottom = sheet_h - (frame_y + frame_h)
    return (region[0], bottom + std.table_band_depth_mm())


def page_point(local):
    """A point in the table's frame, in page coordinates."""
    x0, y0 = table_anchor()
    return (x0 + local[0], y0 - local[1])


def add_table(page, table):
    """Draw a laid-out value table: its rules as projected edges, its cells as annotations.

    **The rules are real geometry, and that is not decoration.** `writeDXFPage` exports a
    `DrawViewPart`'s edges as DXF LINE entities and silently drops a `DrawViewSymbol`
    entirely, so an SVG table -- the obvious way to draw one -- would render on the page and
    vanish from the only export this project can produce headlessly. Measured 2026-08-27:
    FreeCAD 1.1 headless offers `writeDXFPage` and `writeDXFView` and nothing else, so the DXF
    is not one deliverable among several, it is the deliverable a checker can read.

    So the rules are a compound of line segments projected at 1:1. They export, they render,
    and they come from the same layout the cells do, which is what keeps a rule between two
    columns rather than through one.

    **And the rules are what pays OQ-DES-D5's debt.** The 1.0 mm column gutter is 0.4 of the
    table's text height, well inside section 5.2's H2 clearance, allowed because a ruled table
    has a rule between its columns. This is the function that draws them.
    """
    import Part

    doc = page.Document

    edges = []
    for (x1, y1), (x2, y2) in table.rules:
        a = page_point((x1, y1))
        b = page_point((x2, y2))
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
            continue
        edges.append(Part.makeLine(V(a[0], a[1], 0.0), V(b[0], b[1], 0.0)))

    views = []
    if edges:
        shape = doc.addObject('Part::Feature', 'TableRules')
        shape.Shape = Part.makeCompound(edges)
        doc.recompute()

        rules = doc.addObject('TechDraw::DrawViewPart', 'TableRuleView')
        page.addView(rules)
        rules.Source = [shape]
        rules.Direction = V(0.0, 0.0, 1.0)
        rules.XDirection = V(1.0, 0.0, 0.0)
        rules.Scale = 1.0
        # The view centers its projection on the shape's own center, so a shape built in page
        # coordinates lands where it was built when the view is placed at that center. The
        # arithmetic is not trusted: `check_drawing` reads a rule's endpoints back out of the
        # exported DXF and compares them with the layout.
        box = shape.Shape.BoundBox
        rules.X = (box.XMin + box.XMax) / 2.0
        rules.Y = (box.YMin + box.YMax) / 2.0
        doc.recompute()
        views.append(rules)

    for index, cell in enumerate(table.cells):
        annotation = doc.addObject('TechDraw::DrawViewAnnotation', 'TableCell%d' % index)
        page.addView(annotation)
        annotation.Text = [cell.text]
        annotation.TextSize = cell.height
        annotation.LineSpace = LINE_SPACE_PERCENT
        annotation.X, annotation.Y = page_point((cell.x, cell.y))
        views.append(annotation)
    doc.recompute()
    return views


def layout_at(shape, kind, params, direction, x_direction, scale, frame,
              product=FAMILY):
    """Place one variant's annotations at one scale, or raise `PlacementError`."""
    _quantities, dimensions, notes = ANNOTATIONS[kind](params, product)

    placed_dimensions = []
    for quantity, p1, p2, axis, value in dimensions:
        placed_dimensions.append(dp.Dimension(
            quantity.written(product),
            project(p1, direction, x_direction, scale),
            project(p2, direction, x_direction, scale),
            axis, value,
            None if product == FAMILY else std.format_length(value)))

    placed_notes = [dp.Note(key, project(anchor, direction, x_direction, scale), lines)
                    for key, anchor, lines in notes]

    edges = []
    for edge in shape.Edges:
        ends = [project(v.Point, direction, x_direction, scale) for v in edge.Vertexes]
        if len(ends) == 2:
            edges.append((ends[0], ends[1]))

    bbox = projected_bbox(shape, direction, x_direction, scale)
    return dp.place(placed_dimensions, bbox, frame, edges, notes=placed_notes)


def choose_scale(shape, kind, params, direction, x_direction, frame,
                 product=FAMILY):
    """The largest preferred scale whose annotations all place. Returns (scale, layout).

    Searched rather than computed, because whether a layout places is not a function of the
    projected size alone -- the note bands stand off by their own width, and which side each
    note takes is itself decided by a search. Ten scales is cheap; guessing is not.
    """
    region = view_region()
    refusals = []
    for scale in PREFERRED_SCALES:
        bbox = projected_bbox(shape, direction, x_direction, scale)
        if (bbox[2] - bbox[0] > region[2] * VIEW_FILL
                or bbox[3] - bbox[1] > region[3] * VIEW_FILL):
            continue
        try:
            return scale, layout_at(shape, kind, params, direction, x_direction,
                                    scale, frame, product)
        except dp.PlacementError as exc:
            refusals.append('  %g:1 -- %s' % (scale, str(exc).split(NEWLINE)[0]))
    raise dp.PlacementError(
        'no preferred scale places this part\'s annotations:' + NEWLINE
        + NEWLINE.join(refusals) + NEWLINE
        + 'The remedy is to split the view or add a detail view -- a drafting decision made '
          'deliberately -- not to shrink the text.')


def bind_dimensions(page, view, layout):
    """Turn placed dimensions into `DrawViewDimension`s bound to parameter-placed points.

    The vertex count is read here, immediately before the vertices are made, because cosmetic
    vertices are appended after the projected ones and the projected count moves with the
    variant. A literal index is the face-name defect wearing a different hat.
    """
    doc = page.Document
    n_geometric = len(view.getVisibleVertexes())

    made = []
    for index, placed in enumerate(layout):
        scale = view.Scale
        for point in (placed.dimension.p1, placed.dimension.p2):
            view.makeCosmeticVertex3d(model_point(view, point, scale))
        made.append((placed, n_geometric + 2 * index))
    doc.recompute()

    out = []
    for placed, first in made:
        dimension = doc.addObject('TechDraw::DrawViewDimension',
                                  'Dim' + placed.letter)
        page.addView(dimension)
        dimension.Type = ('DistanceX' if placed.dimension.axis == dp.HORIZONTAL
                          else 'DistanceY')
        dimension.References2D = [(view, 'Vertex%d' % first),
                                  (view, 'Vertex%d' % (first + 1))]
        dimension.X = placed.text_box[0] + (placed.text_box[2] - placed.text_box[0]) / 2.0
        dimension.Y = placed.text_box[1] + (placed.text_box[3] - placed.text_box[1]) / 2.0
        out.append(dimension)
    doc.recompute()
    return out


def model_point(view, view_point, scale):
    """A view-space point back in model space, on the projection plane.

    `makeCosmeticVertex3d` wants model coordinates, and the placer works in view coordinates,
    so this is the inverse of `project`. It is exact for the points this module makes, because
    they were projected from model points in the first place -- what it must not be used for is
    a point read back off the projection, which has lost a dimension.
    """
    x_axis, y_axis = view_axes(view.Direction, view.XDirection)
    return (x_axis * (view_point[0] / scale)) + (y_axis * (view_point[1] / scale))


def bind_notes(page, view, layout):
    """Turn placed notes into annotations with leaders, per OQ-DES-D2.

    **One annotation per line, not one per note, and the reason is the export.** A
    `DrawViewAnnotation` holding four strings renders four lines on the page and writes
    exactly one TEXT entity to the DXF -- the first. Measured 2026-08-27: a three-line
    annotation exported `LINEONE` and dropped `LINETWO` and `LINETHREE` without a warning.
    Every corner sheet was losing three quarters of its bore note, three quarters of its
    socket note and two thirds of its pocket note in the deliverable, and `check_drawing`
    passed because it looked for `BORE`, which is on the first line.

    Splitting them also makes the drawn result and the placed model agree by construction.
    `Note.size` says the lines are `NOTE_LINE_PITCH_HEIGHTS` apart and the placer reserves a
    box that deep; positioning each line inside that box is arithmetic this module can do,
    where trusting TechDraw's own stacking was trusting a second implementation of the same
    rule to match the first.
    """
    doc = page.Document
    out = []
    for placed in layout.notes:
        name = 'Note' + str(placed.key).title()
        pitch = dp.NOTE_LINE_PITCH_HEIGHTS * std.TEXT_HEIGHT_MM
        top = placed.text_box[3]
        annotations = []
        for index, line in enumerate(placed.note.lines):
            annotation = doc.addObject('TechDraw::DrawViewAnnotation',
                                       name + ('L%d' % index))
            page.addView(annotation)
            annotation.Text = [line]
            annotation.TextSize = std.TEXT_HEIGHT_MM
            annotation.LineSpace = LINE_SPACE_PERCENT
            annotation.X = (view.X.Value
                            + (placed.text_box[0] + placed.text_box[2]) / 2.0)
            # The center of line `index`'s own row, measured down from the box's top edge.
            annotation.Y = (view.Y.Value + top - index * pitch
                            - std.TEXT_HEIGHT_MM / 2.0)
            annotations.append(annotation)

        leader = doc.addObject('TechDraw::DrawLeaderLine', 'Leader' + str(placed.key).title())
        leader.LeaderParent = view
        leader.X, leader.Y = placed.leader[0]
        leader.WayPoints = [V(0.0, 0.0, 0.0),
                            V(placed.leader[1][0] - placed.leader[0][0],
                              placed.leader[1][1] - placed.leader[0][1], 0.0)]
        out.append((annotations, leader))
    doc.recompute()
    return out


def build_sheet(doc, kind, params_path, params, family=None):
    """One family sheet: page, view, dimensions, notes, value table.

    Returns (page, view, layout, scale).

    `family` is one record out of `tools/drawing_families.py`'s JSON -- the family this
    variant belongs to -- and it carries the two things the sheet needs that a single
    variant's parameters cannot say: which values the whole family takes, and the callout
    letter each quantity was issued. Without it the sheet is drawn without its table, which
    on a *family* sheet means every annotation is a letter pointing at nothing. That is worth
    a refusal rather than a silent omission, so section 5.1's family product asks for it.
    """
    if family is not None:
        unbuilt = part_kinds.unbuilt_types(kind, family.get('type_names', ()))
        if unbuilt:
            raise dp.PlacementError(
                'this backend does not build the %s type%s, so a sheet drawn from it would '
                'show a different part under this family\'s title. %s builds the %s type and '
                'takes no type flag, so it does not fail on one it cannot make -- it returns '
                'the type it does make. See IP-FC-12.'
                % (', '.join(unbuilt), '' if len(unbuilt) == 1 else 's',
                   build_part.__name__, ', '.join(part_kinds.BUILT_TYPES[kind])))

    tip = build_part.build(doc, kind, params_path)
    doc.recompute()

    page, template = add_page(doc)
    direction, x_direction = VIEW_DIRECTION[kind]

    shape = tip.Shape
    probe = add_view(page, tip, direction, x_direction, 1.0)
    frame = frame_in_view(probe)
    scale, layout = choose_scale(shape, kind, params, direction, x_direction, frame)

    probe.Scale = scale
    doc.recompute()

    bind_dimensions(page, probe, layout)
    bind_notes(page, probe, layout)

    if family is not None and family.get('quantity_blocks'):
        table = sheet_table.layout(family['quantity_blocks'], family['letters'])
        problems = table.fits()
        if problems:
            raise dp.PlacementError(
                'the value table does not fit the band beside the title block:' + NEWLINE
                + NEWLINE.join('  - ' + problem for problem in problems))
        add_table(page, table)

    template.EditableTexts = dict(
        template.EditableTexts,
        DrawingTitle=kind.replace('_', ' ').upper(),
        Scale=('%g:1' % scale) if scale >= 1.0 else ('1:%g' % (1.0 / scale)))
    doc.recompute()
    return page, probe, layout, scale
