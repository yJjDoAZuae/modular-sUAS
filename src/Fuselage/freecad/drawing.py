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
import Part

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
#
# **This is a bound on the search, not a rule about the drawing, and at 0.55 it had become the
# second.** It exists so a hopeless scale fails as arithmetic instead of as a placement search
# that always loses: the annotations live outside the part's outline, so a part filling its
# region leaves them nowhere to go. But `layout_at` already answers the real question -- it
# *places* the annotations and refuses if they do not fit -- and a pre-filter set well inside
# that answer does not make the sheet safer, it just throws away the scales that would have
# worked. At 0.55 the part was held to a third of the region's area whatever the annotations
# actually needed, which is why parts on these sheets came out small enough to be asked about:
# a 72.8 mm bulkhead was allowed 55% of a 143 mm-wide region and so could not use 1:1.
#
# 0.95 leaves a hair so the outline is not drawn on the frame, and lets the placement test be
# the thing that decides. A scale that genuinely cannot carry its notes still refuses, one
# step later and for the true reason.
VIEW_FILL = 0.95

#: How far below the largest scale the geometry fits at the search may go before it gives up
#: and lets the sheet split into more views instead.
#:
#: **A quarter, which is two steps of the preferred series.** The series is 10, 5, 2, 1, 1/2,
#: ... so a quarter admits 5:1 where 10:1 fits, or 1:2 where 1:1 does. Below that the drawing
#: is being made small so its own text will fit around it, and the answer to that is a detail
#: view rather than a smaller drawing -- which is the whole reason `SheetView` exists.
SCALE_FLOOR_FRACTION = 0.25

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
    """A model point in millimeters on the page, **origin at the model origin**.

    Arithmetic on the point, not a question to the projection. That is the binding rule this
    module exists to keep.

    **Not the view's origin, whatever this used to say.** A `DrawViewPart` centres its
    projection on its own `X, Y`, so the view's origin is the middle of the projected bounding
    box; this returns the model origin scaled, which is a different point on every part that is
    not symmetric about it. Both frames are needed -- the annotation sets are written from the
    model origin and TechDraw positions from the view's -- and `origin_offset` is the one
    conversion between them. The docstring claimed the second and delivered the first, and
    every leader on every sheet was displaced by the difference.
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
#: How closely a reference part's curved edges are followed when they are turned into
#: straight segments, in model millimeters. A tenth of the smallest printed clearance on this
#: airframe, so the outline cannot be mistaken for a fit.
REFERENCE_DEFLECTION_MM = 0.01

VIEW_DIRECTION = {
    'corner': ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    'bulkhead': ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    'boom_bulkhead': ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
}


# ----------------------------------------------------------------------------------------
# The sheet
# ----------------------------------------------------------------------------------------

def add_page(doc, name='Page'):
    """A page carrying the project's template. Returns (page, template)."""
    std.require_standard()
    template = doc.addObject('TechDraw::DrawSVGTemplate', 'Template' + name[len('Page'):])
    template.Template = std.template_path()
    page = doc.addObject('TechDraw::DrawPage', name)
    page.Template = template
    doc.recompute()
    return page, template


def frame_page_box():
    """The drawing frame as (left, bottom, width, height) in page coordinates.

    Page coordinates run y *up* from the bottom left, where the template's own run y down
    from the top left. This is the one conversion, so the rest of the module can stop
    thinking about it.
    """
    frame_x, frame_y, frame_w, frame_h = std.frame_region_mm()
    bottom = std.TEMPLATE_HEIGHT_MM - (frame_y + frame_h)
    return (frame_x, bottom, frame_w, frame_h)


class Placement(object):
    """Where the view and the value table go on one sheet.

    `name`          `drawing_standard.PLACEMENT_BAND` or `PLACEMENT_COLUMN`
    `view_region`   (x, y, w, h) in page coordinates
    `table_anchor`  the table's top-left corner in page coordinates, or None
    """

    def __init__(self, name, view_region, table_anchor=None, key_anchor=None,
                 coverage_anchor=None, coverage_width=0.0):
        self.name = name
        self.view_region = view_region
        self.table_anchor = table_anchor
        # Where the sheet-coverage block goes, and how much width is left for it. It sits in
        # the strip beside the value table -- the one place on a family sheet with room that
        # nothing else wants -- so the width depends on how wide that sheet's table came out.
        self.coverage_anchor = coverage_anchor
        self.coverage_width = float(coverage_width)
        # Where the dimension key goes, when there is one. `None` means the sheet has no key
        # to place, not that it has one with nowhere to go -- that is a refusal.
        self.key_anchor = key_anchor

    def __repr__(self):
        return '<Placement %s view %s>' % (self.name, self.view_region)


def band_region():
    """The rectangle beside the title block, as (x, y, width, height) in page coordinates.

    The whole of the sheet's non-view area that is not the title block: 108.5 mm wide by the
    block's own 46.0 deep, across the bottom of the frame. Everything a family sheet carries
    besides the drawing goes in here, and the view gets the rest of the frame.
    """
    left, bottom, width, _height = frame_page_box()
    block_w = std.TEMPLATE_TITLE_BLOCK_MM[2]
    block_h = std.TEMPLATE_TITLE_BLOCK_MM[3]
    return (left, bottom, width - block_w - std.TABLE_COLUMN_GUTTER_MM, block_h)


def pack_band(table, key, coverage):
    """Fit the three blocks into the band, or return None saying nothing about why.

    Two rows: the value table across the top, the dimension key and the sheet-coverage block
    side by side under it. The table is the widest of the three and the only one that has to
    span, and the other two are each about half the band -- so this is the packing that wastes
    least, which is the whole game when the band is what the view is not getting.

    Returns `(table_anchor, key_anchor, coverage_anchor)` in page coordinates, anchored
    top-left the way `add_table` wants them.
    """
    x, y, width, height = band_region()
    gutter = std.TABLE_COLUMN_GUTTER_MM
    top = y + height

    blocks = [b for b in (table, key, coverage) if b is not None]
    if not blocks:
        return (None, None, None)
    if table is not None and table.width > width + 1e-9:
        return None

    second = [b for b in (key, coverage) if b is not None]
    second_w = sum(b.width for b in second) + gutter * max(0, len(second) - 1)
    if second_w > width + 1e-9:
        return None

    table_depth = table.height if table is not None else 0.0
    second_depth = max([b.height for b in second] or [0.0])
    needed = table_depth + (gutter if table is not None and second else 0.0) + second_depth
    if needed > height + 1e-9:
        return None

    anchors = {}
    if table is not None:
        anchors['table'] = (x, top)
    run_y = top - table_depth - (gutter if table is not None and second else 0.0)
    run_x = x
    for block, name in ((key, 'key'), (coverage, 'coverage')):
        if block is None:
            continue
        anchors[name] = (run_x, run_y)
        run_x += block.width + gutter
    return (anchors.get('table'), anchors.get('key'), anchors.get('coverage'))


def sheet_blocks(family, variant, siblings):
    """The three blocks a family sheet carries, at the largest text height that packs.

    Returns `(table, key, coverage, height_mm, anchors)`, or raises `PlacementError` naming
    every height tried and what stopped it.

    **The search is over the lettering, not over the drawing.** The band is a fixed rectangle
    and the blocks in it are what is negotiable; the view gets whatever the band does not
    take, which is the requirement `VIEW_SHARE` states and the reason the sheet is drawn at
    all. Shrinking the *view* to make room for a table is the trade this refuses to make.
    """
    if family is None or not family.get('quantity_blocks'):
        return (None, None, None, std.TABLE_TEXT_HEIGHT_MM, (None, None, None))

    pairs = dimension_key(family)
    rows = sheet_annotations.coverage_rows(family, variant, siblings)
    width = band_region()[2]
    tried = []
    for height in std.TABLE_TEXT_HEIGHTS_MM:
        table = sheet_table.layout(family['quantity_blocks'], family['letters'],
                                   text_height_mm=height)
        key = None
        if pairs:
            key, _problems = sheet_table.legend_fitting(
                pairs, (0.0, 0.0, width, band_region()[3]), text_height_mm=height)
        coverage, _problems = sheet_table.caption_fitting(rows, width, text_height_mm=height)
        anchors = pack_band(table, key, coverage)
        if anchors is not None:
            return (table, key, coverage, height, anchors)
        tried.append('  %.1f mm: table %.1f x %.1f, key %.1f x %.1f, coverage %.1f x %.1f'
                     % (height, table.width, table.height,
                        key.width if key else 0.0, key.height if key else 0.0,
                        coverage.width, coverage.height))
    band = band_region()
    raise dp.PlacementError(
        'this sheet\'s blocks do not fit the %.1f x %.1f mm band beside the title block at '
        'any lettering height:' % (band[2], band[3]) + NEWLINE + NEWLINE.join(tried))


def band_placement(table=None):
    """OQ-DES-D5's layout: title block and table side by side across the bottom."""
    left, bottom, width, height = frame_page_box()
    depth = std.table_band_depth_mm()
    region = (left, bottom + depth, width, height - depth)
    anchor = None if table is None else (std.table_region_mm(table.width)[0],
                                         bottom + depth)
    return Placement(std.PLACEMENT_BAND, region, anchor)


#: A table in a full-width strip of its own, between the view and the title block. Not one
#: of the two placements `drawing_standard` names -- see `choose_placement` for why a third
#: one exists and why the one it names cannot be used here.
PLACEMENT_STACKED = 'stacked'


def key_region():
    """Where the dimension key goes, as (x, y, width, height) in page coordinates.

    The band beside the title block -- the rectangle the value table used to occupy and gives
    up when it moves to a strip of its own. Nothing else wants it, and it is the right shape:
    108.5 mm wide by the title block's own 46.0 deep, which holds a thirteen-row key in two
    runs with room to spare.
    """
    left, bottom, width, _height = frame_page_box()
    block_w = std.TEMPLATE_TITLE_BLOCK_MM[2]
    block_h = std.TEMPLATE_TITLE_BLOCK_MM[3]
    return (left, bottom, width - block_w - std.TABLE_COLUMN_GUTTER_MM, block_h)


def stacked_placement(table):
    """The table in a full-width strip between the view and the title block.

    Three strips up the sheet: the title block across the bottom at its own depth, the table
    above it at the table's depth, the view above that with everything left. The table gets
    the frame's whole width, which is the point -- it is only its width that the band cannot
    hold -- and the view keeps the whole width too, which is what its notes need.
    """
    left, bottom, width, height = frame_page_box()
    gutter = std.TABLE_COLUMN_GUTTER_MM
    block_h = std.TEMPLATE_TITLE_BLOCK_MM[3]
    strip_bottom = bottom + block_h + gutter
    region_bottom = strip_bottom + table.height + gutter
    region = (left, region_bottom, width, bottom + height - region_bottom)
    anchor = (left, strip_bottom + table.height)
    key = key_region()
    # **Beside the value table, in the strip the table already occupies.** The band by the
    # title block holds the dimension key and has nothing left -- the bulkhead's key runs to
    # two columns and 80 mm of a 108.5 mm band -- while the strip is the frame's full width
    # and the widest table measured is 156.2 mm, so 80 mm of it is empty on every sheet. Using
    # it costs the view nothing, and the alternative costed: a row added to the title block
    # for the same statement would have taken 9 mm off a view that already has 52% of a frame
    # where the standard asks for 75%.
    gutter_2 = 2.0 * gutter
    return Placement(PLACEMENT_STACKED, region, anchor,
                     key_anchor=(key[0], key[1] + key[3]),
                     coverage_anchor=(left + table.width + gutter_2,
                                      strip_bottom + table.height),
                     coverage_width=width - table.width - gutter_2)


def choose_placement(table, has_key=False):
    """Where this sheet's table, key and view go, or raise `PlacementError` saying why not.

    **The band is tried first because OQ-DES-D5 decided it**, and it is the placement that
    leaves the view the share the requirement asks for -- measured 75.7 % of the frame against
    the column's 38.4 %. What OQ-DES-D5 could not have weighed is that the table was being
    measured 33 % narrower than it draws (see `drawing_standard.EM_PER_TEXT_HEIGHT`): with the
    text measured against its cap height, the bulkhead family table needs 135.2 mm and the
    band beside the title block offers 108.5.

    **The other placement the standard names, `PLACEMENT_COLUMN`, is not tried, and that is
    measured rather than assumed.** A column wide enough for the bulkhead table leaves the view
    103.3 mm of the frame's 239.5. The bulkhead's own notes need more than that on their own:
    the widest note line is 58.0 mm at the 3.5 mm text height, and a sheet with notes on both
    sides of a 72.8 mm part needs 188.8 mm before a dimension is placed. So the column trades a
    table that does not fit for a view that does not, and every sheet that reached it refused
    at the next step instead of this one, with a message about scales that said nothing about
    the table.

    `PLACEMENT_STACKED` gives the table its own full-width strip between the view and the
    title block. Only the table's *width* is the problem -- it is 135.2 mm against the 108.5
    the band leaves beside a 130 mm title block -- and a full-width strip is 239.5. The view
    keeps the full width as well and pays in height instead, which is the axis its notes are
    not short of.

    **This is a third placement, and the sheet standard names two.** It is here so that the
    sheets exist to be looked at, not because the packing question is settled: whether to widen
    the sheet, narrow the title block, split a family across two sheets, or keep this, is
    OQ-DES-D15. Which placement a sheet got is returned so the caller can say so.
    """
    if table is None:
        return band_placement(None)

    left, bottom, width, height = frame_page_box()

    # **The band only has room for one of them.** A sheet with a dimension key has three
    # things to place besides the view -- the values, the key, and the title block -- and the
    # band across the bottom holds two. So a keyed sheet puts the values in a strip of their
    # own and the key in the band beside the block; the band layout is for a sheet with no key
    # to place, which on a family sheet does not happen.
    if has_key:
        band_problems = ['the sheet has a dimension key, which takes the band beside the '
                         'title block, so the values cannot also be there']
    else:
        band_problems = table.fits()
        if not band_problems:
            return band_placement(table)

    stacked = stacked_placement(table)
    strip_problems = []
    if table.width > width + 1e-9:
        strip_problems.append(
            'the table is %.1f mm wide and the frame is %.1f -- over by %.1f'
            % (table.width, width, table.width - width))
    if stacked.view_region[3] <= 0.0:
        strip_problems.append(
            'the table is %.1f mm deep over %d rows and the title block is %.1f, on a %.1f mm '
            'frame -- nothing is left for the view'
            % (table.height, table.rows, std.TEMPLATE_TITLE_BLOCK_MM[3], height))
    if not strip_problems:
        return stacked

    raise dp.PlacementError(
        'the value table fits neither the band nor a strip of its own:' + NEWLINE
        + 'band (OQ-DES-D5\'s layout):' + NEWLINE
        + NEWLINE.join('  - ' + problem for problem in band_problems) + NEWLINE
        + 'stacked (a full-width strip above the title block):' + NEWLINE
        + NEWLINE.join('  - ' + problem for problem in strip_problems))


def add_view(page, shape, direction, x_direction, scale, region, name='View'):
    """The projected view, centerd in its region at `scale`."""
    doc = page.Document
    view = doc.addObject('TechDraw::DrawViewPart', name)
    page.addView(view)
    view.Source = [shape]
    view.Direction = V(*direction)
    view.XDirection = V(*x_direction)
    view.Scale = scale
    view.X = region[0] + region[2] / 2.0
    view.Y = region[1] + region[3] / 2.0
    doc.recompute()
    return view


def frame_in_view(view, region, offset=(0.0, 0.0)):
    """The view region expressed the way `dimension_placement` wants it.

    The placer works in the frame `project` returns -- millimeters on the page, origin at the
    *model* origin -- so the region has to be translated twice: by the view's position on the
    page, and by where the model origin sits inside the view. `offset` is the second, from
    `origin_offset`, at the scale the layout is being tried at.

    **Both translations, or the frame and the geometry are in different frames.** They were:
    the geometry came from `project` about the model origin and the frame came from here about
    the view's, so the containment test H1 was asking whether annotations placed around the
    part fit a rectangle displaced from it -- 6.9 mm on the corner, in both axes at once. Some
    were let through that do not fit and some refused that do.
    """
    x = view.X.Value + offset[0]
    y = view.Y.Value + offset[1]
    return (region[0] - x, region[1] - y,
            region[0] + region[2] - x, region[1] + region[3] - y)


def page_point(local, anchor):
    """A point in the table's frame, in page coordinates.

    `sheet_table` works in the table's own frame -- origin top-left, y downward, because that
    is reading order -- and the page's y runs upward. `anchor` is where the two meet, and it
    comes from the `Placement` so that a table drawn in the column and a table drawn in the
    band cannot disagree with the view that was sized around them.
    """
    x0, y0 = anchor
    return (x0 + local[0], y0 - local[1])


def dimension_key(family):
    """Every callout letter on this sheet and what it measures, in letter order.

    Built from the family's own `letters` map, which is the same map the table headings come
    from, so the key cannot describe a letter the sheet does not print or miss one it does.
    Sorted by letter because that is how a reader arrives: they have seen `J` on the view or
    over a column and want to know what it is.
    """
    letters = (family or {}).get('letters') or {}
    return [(letter, sheet_annotations.description(field))
            for field, letter in sorted(letters.items(), key=lambda kv: kv[1])]


def add_table(page, table, anchor, name='Table'):
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
        a = page_point((x1, y1), anchor)
        b = page_point((x2, y2), anchor)
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
            continue
        edges.append(Part.makeLine(V(a[0], a[1], 0.0), V(b[0], b[1], 0.0)))

    views = []
    if edges:
        shape = doc.addObject('Part::Feature', name + 'Rules')
        shape.Shape = Part.makeCompound(edges)
        doc.recompute()

        rules = doc.addObject('TechDraw::DrawViewPart', name + 'RuleView')
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
        annotation = doc.addObject('TechDraw::DrawViewAnnotation',
                                   '%sCell%d' % (name, index))
        page.addView(annotation)
        annotation.Text = [cell.text]
        annotation.TextSize = cell.height
        annotation.LineSpace = LINE_SPACE_PERCENT
        x, y = page_point((cell.x, cell.y), anchor)
        # **A `DrawViewAnnotation` is placed by its baseline, not by the middle of its text**,
        # so a cell handed the middle of its row draws half a cap height high. Measured on the
        # rendered page 2026-09-07: every cell's ink sat 1.25 mm above where the layout put it,
        # against a 2.5 mm text height. That is what made the first data row of every block
        # touch the rule above it while the rows below it, which have no rule between them,
        # looked fine -- and it is why the table appeared to have a row-pitch problem when the
        # pitch was right all along. `bind_notes` has always applied the same half-height
        # correction; this is the same rule, in the one place that was missing it.
        annotation.Y = y - cell.height / 2.0
        annotation.X = x
        views.append(annotation)
    doc.recompute()
    return views


def layout_at(shape, direction, x_direction, scale, frame, dimensions, notes,
              construction, product=FAMILY):
    """Place one view's annotations at one scale, or raise `PlacementError`.

    `frame` is already in the placer's frame at this scale -- `choose_scale` converts it,
    because the conversion depends on the scale and the search tries several.

    `dimensions` and `notes` are this *view's* share of the sheet's, chosen by the view set
    rather than by this function: a sheet with a plan and a detail places each independently,
    against its own region, at its own scale.
    """

    # IP-FC-84: `dp.Dimension`'s `letter` is the object-naming key ("DimA"), never what the
    # sheet displays -- `quantity.written(product)` answers that second question and is
    # right for a note's own text, but calling it here for `letter` handed a rendered number
    # like '10.00' to a slot that validates against the callout alphabet, and the check
    # correctly refused it the moment single-variant sheets were built for the first time.
    # `quantity.letter` is always a real letter for anything that reaches this loop: a
    # constant quantity is never given one, and by convention (`sheet_annotations.py`) a
    # constant is never put on a dimension line either.
    placed_dimensions = []
    for quantity, p1, p2, axis, value in dimensions:
        placed_dimensions.append(dp.Dimension(
            quantity.letter,
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

    # **Construction geometry is geometry as far as the placer is concerned.** A panel outline
    # runs past the part's own end face by design, so a bbox taken from the part alone puts
    # the first dimension lane *inside* the panel, and H4's crossing test never sees the lines
    # it would cross. Both go in: the segments as edges, and their extent into the bbox.
    construction_edges = construction_segments(construction, direction, x_direction, scale)
    edges += construction_edges

    bbox = projected_bbox(shape, direction, x_direction, scale)
    for start, end in construction_edges:
        bbox = (min(bbox[0], start[0], end[0]), min(bbox[1], start[1], end[1]),
                max(bbox[2], start[0], end[0]), max(bbox[3], start[1], end[1]))
    return dp.place(placed_dimensions, bbox, frame, edges, notes=placed_notes)


def construction_lines(construction, scale):
    """Every construction record as `(format, p1, p2)` model-space segments.

    One place turns the records into segments, and both the placer and the page read it. A
    centre mark drawn in one geometry and measured in another is a mark that lands where
    nothing checked it.

    **`scale` is here for the centre lines' overrun and for nothing else.** How far an axis
    stands clear of the part is a distance on the paper -- it comes from the text height, like
    the lane pitch and the note spacing -- so in model space it is that distance divided by the
    scale. `sheet_annotations` gives the ends at the geometry's own extent, which is a fact
    about the part and does not depend on how large it is drawn.
    """
    overrun = std.CENTER_LINE_OVERRUN_HEIGHTS * std.TEXT_HEIGHT_MM / float(scale)
    out = []
    for record in construction:
        if record[0] == sheet_annotations.CENTER_MARK:
            _kind, (x, y), radius = record
            arm = radius * std.CENTER_MARK_OVERRUN
            fmt = std.center_mark_format()
            out.append((fmt, (x - arm, y, 0.0), (x + arm, y, 0.0)))
            out.append((fmt, (x, y - arm, 0.0), (x, y + arm, 0.0)))
        elif record[0] == sheet_annotations.CENTER_LINE:
            _kind, (x1, y1), (x2, y2) = record
            span = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            ux, uy = ((x2 - x1) / span, (y2 - y1) / span) if span else (0.0, 0.0)
            out.append((std.center_line_format(),
                        (x1 - ux * overrun, y1 - uy * overrun, 0.0),
                        (x2 + ux * overrun, y2 + uy * overrun, 0.0)))
        elif record[0] == sheet_annotations.REFERENCE:
            _kind, points, closed, _label = record
            fmt = std.phantom_format()
            ordered = list(points) + ([points[0]] if closed else [])
            for (x1, y1), (x2, y2) in zip(ordered, ordered[1:]):
                out.append((fmt, (x1, y1, 0.0), (x2, y2, 0.0)))
        else:
            raise ValueError('unknown construction record %r' % (record[0],))
    return out


def construction_segments(construction, direction, x_direction, scale):
    """The construction lines in view coordinates, for the placer."""
    return [(project(p1, direction, x_direction, scale),
             project(p2, direction, x_direction, scale))
            for _fmt, p1, p2 in construction_lines(construction, scale)]


def bind_construction(view, construction, scale):
    """Draw the construction geometry on the view as formatted cosmetic edges.

    **A cosmetic edge carries its own format in the document**, unlike a view, whose line
    weight is a view-provider property a headless build never writes. So these come out of
    `freecadcmd` already looking right, and the renderer has nothing to supply. Verified on
    FreeCAD 1.1.3: `CosmeticEdge.Format` is a dict keyed `style`, `weight`, `color`,
    `visible`, in lower case; capitalised keys are rejected without an error.
    """
    made = []
    for fmt, p1, p2 in construction_lines(construction, scale):
        tag = view.makeCosmeticLine3D(V(*p1), V(*p2))
        edge = view.getCosmeticEdge(tag)
        edge.Format = fmt
        made.append(tag)
    return made


def choose_scale(shape, direction, x_direction, frame, unit_offset,
                 dimensions, notes, construction, product=FAMILY):
    """The largest preferred scale whose annotations all place. Returns (scale, layout).

    Searched rather than computed, because whether a layout places is not a function of the
    projected size alone -- the note bands stand off by their own width, and which side each
    note takes is itself decided by a search. Ten scales is cheap; guessing is not.
    """
    # **The region comes from the frame rather than being asked for again.** `frame` is the
    # view region already translated into view coordinates, so its extents *are* the region's
    # size; fetching the region separately would be a second answer to a question that has
    # one, and since the region now depends on which placement the sheet got, the second
    # answer would be the wrong one on any sheet that is not in the band.
    region_w = frame[2] - frame[0]
    region_h = frame[3] - frame[1]

    # **The largest scale the geometry itself fits**, before a single annotation is
    # considered. This is the scale the sheet wants, and every step below it is a step the
    # drawing pays for the text.
    fits = [scale for scale in PREFERRED_SCALES
            if projected_bbox(shape, direction, x_direction, scale)[2]
            - projected_bbox(shape, direction, x_direction, scale)[0] <= region_w * VIEW_FILL
            and projected_bbox(shape, direction, x_direction, scale)[3]
            - projected_bbox(shape, direction, x_direction, scale)[1] <= region_h * VIEW_FILL]
    if not fits:
        raise dp.PlacementError(
            'the part does not fit its region (%.1f x %.1f mm) at any preferred scale, so '
            'there is no drawing to annotate' % (region_w, region_h))
    ceiling = fits[0]

    refusals = []
    for scale in PREFERRED_SCALES:
        bbox = projected_bbox(shape, direction, x_direction, scale)
        if (bbox[2] - bbox[0] > region_w * VIEW_FILL
                or bbox[3] - bbox[1] > region_h * VIEW_FILL):
            continue
        # **The drawing is not shrunk indefinitely to make room for its own text.** A view
        # that will not carry its annotations at close to the size the region allows is a
        # view that wants splitting into a plan and a detail -- section 5.6's remedy, and
        # what the reader asked for. Left unbounded, the search answered "the notes do not
        # fit" by drawing a 200 mm plate at 1:5, which is a postage stamp in a frame of text.
        if scale < ceiling * SCALE_FLOOR_FRACTION:
            refusals.append(
                '  below %s the drawing is being shrunk to fit its own annotations. The '
                'geometry fits this region at %s; anything under %s is the text winning, '
                'and the remedy for that is a detail view.'
                % (format_scale(scale), format_scale(ceiling),
                   format_scale(ceiling * SCALE_FLOOR_FRACTION)))
            break
        # **The frame moves with the scale, because the offset does.** `unit_offset` is where
        # the model origin sits in the view's frame at 1:1; at 5:1 it is five times that. The
        # region on the paper does not move, so in the placer's frame it slides.
        scaled = (frame[0] - unit_offset[0] * (scale - 1.0),
                  frame[1] - unit_offset[1] * (scale - 1.0),
                  frame[2] - unit_offset[0] * (scale - 1.0),
                  frame[3] - unit_offset[1] * (scale - 1.0))
        try:
            return (scale, layout_at(shape, direction, x_direction, scale, scaled,
                                     dimensions, notes, construction, product), ceiling)
        except dp.PlacementError as exc:
            refusals.append('  %g:1 -- %s' % (scale, str(exc).split(NEWLINE)[0]))
    raise dp.PlacementError(
        'no preferred scale places this part\'s annotations:' + NEWLINE
        + NEWLINE.join(refusals) + NEWLINE
        + 'The remedy is to split the view or add a detail view -- a drafting decision made '
          'deliberately -- not to shrink the text.')


class BuiltView(object):
    """One view as it came out: what it was asked for, and what it is.

    `spec`    the `SheetView` it was built from
    `view`    the `DrawViewPart`
    `layout`  the placed annotations, in the placer's frame
    `scale`   what it was drawn at, which is per view rather than per sheet
    `region`  the rectangle of the sheet it was given
    """

    def __init__(self, spec, view, layout, scale, region, ceiling=None):
        self.spec = spec
        self.view = view
        self.layout = layout
        self.scale = float(scale)
        self.region = tuple(region)
        # The largest scale this view's geometry alone would fit its region at. What the
        # scale would have been if the annotations cost nothing, and so the yardstick an
        # arrangement is scored against.
        self.ceiling = float(ceiling) if ceiling else None

    def __repr__(self):
        return '<BuiltView %s at %s>' % (self.spec.name, format_scale(self.scale))


def format_scale(scale):
    """A scale as a drawing states it."""
    return ('%g:1' % scale) if scale >= 1.0 else ('1:%g' % (1.0 / scale))


#: How a sheet's two views may be arranged, as `(kind, share of the first view)`.
#:
#: **Every one is tried and the best is kept, because the answer is measurable and it is not
#: the same answer twice.** Columns keep each view the region's full height and divide its
#: width; rows do the opposite. A bulkhead's five leader notes need about 120 mm of width *at
#: any scale* -- note text does not shrink with the part -- so a bulkhead's detail wants rows;
#: a square plate with two dimensions and no notes wants as much height as it can get, which
#: is a larger share of them. An even split serves neither: the plate was drawn at 1:5 in
#: half the height while the detail, which needs width and not height, had the same half.
#:
#: The shares are the first view's; the rest divide what is left.
ARRANGEMENTS = (('columns', 0.5),
                ('rows', 0.5), ('rows', 0.6), ('rows', 0.65), ('rows', 0.7), ('rows', 0.4))


def view_regions(region, count, arrangement='columns', share=0.5):
    """`region` split into `count` parts, with a gutter between."""
    x, y, width, height = region
    gutter = std.TABLE_COLUMN_GUTTER_MM
    if count == 1:
        return [region]
    if arrangement == 'columns':
        each = (width - gutter * (count - 1)) / float(count)
        return [(x + index * (each + gutter), y, each, height) for index in range(count)]
    if arrangement == 'rows':
        usable = height - gutter * (count - 1)
        first = usable * share
        rest = (usable - first) / float(count - 1)
        # Top down, so the first view declared is the one at the top of the sheet.
        out = [(x, y + height - first, width, first)]
        cursor = y + height - first - gutter
        for _index in range(count - 1):
            out.append((x, cursor - rest, width, rest))
            cursor -= rest + gutter
        return out
    raise ValueError('unknown arrangement %r' % (arrangement,))


def arrangement_score(built):
    """How well an arrangement serves its *worst-served* view, from 0 to 1.

    Each view's scale as a fraction of the largest scale that view's own geometry would fit
    its region at, and then the smallest of those. Tie-broken by the total drawn area.

    **The minimum rather than the sum, and that was measured wrong first.** Summing the drawn
    area is the obvious reading of "make the drawing large", and it chose an arrangement that
    drew a 50 mm plate at 1:5 so that a 20 mm corner detail could be drawn at 2:1 -- because
    the detail's area grows with the square of a scale it had room to spare on, and the plan's
    loss was smaller in mm2 than the detail's gain. A sheet is not better for having one view
    enormous and the other illegible. The minimum makes an arrangement only as good as the
    view it treats worst, which is how a reader judges it.
    """
    fractions = [view.scale / view.ceiling for view in built if view.ceiling]
    total = 0.0
    for view in built:
        box = view.view.Source[0].Shape.BoundBox
        total += ((box.XMax - box.XMin) * (box.YMax - box.YMin)) * view.scale ** 2
    return (min(fractions) if fractions else 0.0, total)


def place_views(page, tip, specs, direction, x_direction, regions,
                dimensions, notes, construction, suffix='', all_specs=None,
                product=FAMILY):
    """Build every view into its region, or raise `PlacementError` naming the one that failed.

    Returns a list of `BuiltView`. Each view searches its own scale against its own region,
    because a plan and a detail are drawn at different sizes on purpose -- that is what the
    split is for.

    `specs` is what to build here; `all_specs` is the drawing's whole view set, which is a
    different thing as soon as the views go on separate sheets. Two decisions need the whole
    set and not this sheet's share of it: which view a construction record belongs to, and
    which view carries the circle saying where a detail was taken from. Both were read off
    `specs` and both were wrong the moment `build_sheets` started calling this one view at a
    time -- `construction_for`'s fallback is "the first view", so a sheet holding only the
    detail became the first view and took all sixteen of the plate's centre marks, axes and
    panel outlines onto a 30 mm corner. Measured 2026-09-07: the detail refused at 2:1 and
    1:1 and came out at 1:2, a *detail* drawn at half size, and the plan lost its detail
    circle in the same stroke.
    """
    all_specs = tuple(all_specs) if all_specs is not None else tuple(specs)
    doc = page.Document
    built = []
    for index, (spec, region) in enumerate(zip(specs, regions)):
        source = tip if spec.clip is None else clip_solid(
            doc, tip, spec.clip, 'Detail%s%d' % (suffix, index))
        doc.recompute()
        view = add_view(page, source, direction, x_direction, 1.0, region,
                        name='View' + (suffix if index == 0
                                       else '%s%d' % (suffix, index)))
        # Measured at 1:1, where it is the projection's centre in model millimeters, and
        # scaled from there. `origin_offset` asks the projection rather than predicting it.
        unit_offset = origin_offset(view)
        frame = frame_in_view(view, region, unit_offset)
        view_dimensions, view_notes = annotations_for(spec, dimensions, notes)
        view_construction = construction_for(spec, construction, all_specs)
        try:
            scale, layout, ceiling = choose_scale(
                source.Shape, direction, x_direction, frame, unit_offset,
                view_dimensions, view_notes, view_construction, product)
        except dp.PlacementError as exc:
            raise dp.PlacementError(
                'the %s view, given %.1f x %.1f mm, could not be placed:'
                % (spec.name, region[2], region[3]) + NEWLINE + str(exc))

        view.Scale = scale
        doc.recompute()

        bind_construction(view, view_construction, scale)
        # Every clipped view is marked on the view it is clipped out of, so the plan says
        # where the detail is and the detail is not a picture of nowhere.
        for other in all_specs:
            if other is not spec and other.clip is not None and spec.clip is None:
                add_detail_marker(page, view, other.clip, scale, other.name)
        bind_dimensions(page, view, layout)
        bind_notes(page, view, layout)
        if spec.caption:
            add_caption(page, view, region,
                        '%s  %s' % (spec.caption, format_scale(scale)))
        built.append(BuiltView(spec, view, layout, scale, region, ceiling))
    return built


def clear_views(doc):
    """Remove everything `place_views` made, so the next arrangement starts clean.

    An arrangement that refuses has still built views, dimensions and leaders up to the point
    it gave up, and they are on the page. Left there, the sheet that finally places would
    carry the failed attempt's objects underneath it.
    """
    prefixes = ('View', 'Detail', 'Dim', 'Note', 'Leader', 'Caption')
    for obj in [o for o in doc.Objects if o.Name.startswith(prefixes)]:
        try:
            doc.removeObject(obj.Name)
        except Exception:                                               # noqa: BLE001
            pass
    doc.recompute()


def clip_solid(doc, tip, clip, name):
    """The part intersected with a cylinder on `clip`'s axis, as a document object.

    **This is what a detail view is here**, rather than `TechDraw::DrawViewDetail`, which
    cannot be built by the binary that builds these documents -- it cuts on a worker thread
    and `freecadcmd` dies in the recompute. Intersecting the solid is synchronous, and the
    result stays in the part's own model coordinates, so a dimension on the detail binds to
    the same points the annotation set declares for the whole part.

    The cylinder overshoots the part in `z` at both ends: a cut flush with the end faces is a
    coincident-face boolean, which is the case OCC is least reliable on and the one that
    silently returns a shape missing a face.
    """
    cx, cy, radius = clip
    box = tip.Shape.BoundBox
    depth = box.ZMax - box.ZMin
    pad = max(1.0, depth * 0.1)
    cylinder = Part.makeCylinder(radius, depth + 2.0 * pad,
                                 V(cx, cy, box.ZMin - pad))
    solid = tip.Shape.common(cylinder)
    if solid.isNull() or not solid.Volume:
        raise dp.PlacementError(
            'the detail at (%.2f, %.2f) r%.2f takes in none of the part, so it would be an '
            'empty view' % (cx, cy, radius))
    feature = doc.addObject('Part::Feature', name)
    feature.Shape = solid
    return feature


def annotations_for(spec, dimensions, notes):
    """This view's share of the sheet's dimensions and notes, in the declared order."""
    wanted = set(spec.dimensions)
    keys = set(spec.notes)
    return ([row for row in dimensions if row[0].name in wanted],
            [row for row in notes if row[0] in keys])


def construction_for(spec, construction, others):
    """This view's share of the construction geometry.

    Assigned by where it *is*, unlike the dimensions and notes, which are assigned by what
    they are about. A centre mark belongs to the axis it marks and a panel outline to the
    panel; neither is a statement that could go on either view. So a record goes on the
    innermost view that contains all of it, and on the plan when no detail does.

    A record straddling a detail's boundary stays on the plan. Drawn on the detail it would
    run out past the clip the view is of, and the extent the layout is fitted to would be the
    part the detail deliberately excluded.
    """
    mine = []
    for record in construction:
        home = None
        for candidate in others:
            if candidate.clip and _record_inside(record, candidate.clip):
                home = candidate
                break
        if home is None:
            home = others[0]
        if home is spec:
            mine.append(record)
    return mine


def _record_inside(record, clip):
    """Is every point of `record` inside `clip`?"""
    cx, cy, radius = clip

    def inside(x, y, slack=0.0):
        return ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= radius - slack

    if record[0] == sheet_annotations.CENTER_MARK:
        _kind, (x, y), feature_radius = record
        return inside(x, y, feature_radius * std.CENTER_MARK_OVERRUN)
    if record[0] == sheet_annotations.CENTER_LINE:
        return all(inside(x, y) for x, y in record[1:3])
    if record[0] == sheet_annotations.REFERENCE:
        return all(inside(x, y) for x, y in record[1])
    return False


def add_caption(page, view, region, text):
    """The view's caption, centred under it inside its own region."""
    doc = page.Document
    annotation = doc.addObject('TechDraw::DrawViewAnnotation',
                               'Caption' + view.Name)
    page.addView(annotation)
    annotation.Text = [text]
    annotation.TextSize = std.TEXT_HEIGHT_MM
    annotation.LineSpace = LINE_SPACE_PERCENT
    annotation.X = region[0] + region[2] / 2.0
    annotation.Y = region[1] + std.TEXT_HEIGHT_MM / 2.0
    return annotation


def add_detail_marker(page, view, clip, scale, label=None):
    """The circle on the plan showing where a detail is taken from, and its name.

    Drawn on the view the detail is *of*, not on the detail: it is the plan's statement that
    a region of it is enlarged elsewhere, and without it the detail is a picture of something
    the reader has to find.

    **Labelled, because the detail is now on another sheet.** When both views shared a frame
    the circle and the enlargement were a hand's breadth apart and the reader joined them by
    looking. On separate sheets nothing joins them but the name, so the circle carries the
    same name the detail's caption does.
    """
    cx, cy, radius = clip
    tag = view.makeCosmeticCircle3d(V(cx, cy, 0.0), radius)
    edge = view.getCosmeticEdge(tag)
    edge.Format = std.detail_marker_format()
    if not label:
        return tag

    # Up and to the right of the circle, clear of it by half the lettering. `origin_offset`
    # is read at the view's present scale, so this is the same arithmetic the annotations
    # went through and the label cannot land in a frame of its own.
    offset_x, offset_y = origin_offset(view)
    reach = radius * scale * (0.5 ** 0.5) + std.TEXT_HEIGHT_MM
    annotation = page.Document.addObject('TechDraw::DrawViewAnnotation',
                                         'Detail' + view.Name + 'Label')
    page.addView(annotation)
    annotation.Text = [label]
    annotation.TextSize = std.TEXT_HEIGHT_MM
    annotation.LineSpace = LINE_SPACE_PERCENT
    annotation.X = view.X.Value + offset_x + cx * scale + reach
    annotation.Y = view.Y.Value + offset_y + cy * scale + reach
    return tag


def resolve_reference_parts(params_path, construction, say=None):
    """Replace every `REFERENCE_PART` record with the outline it stands for.

    Builds the named part in a document of its own, sections it, and returns the section's
    outer wire as `REFERENCE` polylines -- one per placement. A document of its own because a
    reference part is scaffolding: built into the sheet's document it would leave a second
    part tree in the saved file, shown by anything that opens it.

    **The outer wire only.** A section of a corner gives the silhouette and the bore, and the
    bore is the longeron -- a third part, on a sheet that is about the bulkhead. What the
    reader needs is where the corner's material is.

    Straight edges stay straight and curved ones are discretised, rather than discretising
    everything: a mold line arc wants points and a seating flat does not, and a flat drawn as
    forty collinear segments is forty chances for a rounding difference to show as a kink.
    """
    resolved = []
    for record in construction:
        if record[0] != sheet_annotations.REFERENCE_PART:
            resolved.append(record)
            continue
        _kind, part_kind, section_z, placements, label = record
        points = _section_outline(params_path, part_kind, section_z)
        if say:
            say('  %s reference: %d point(s) at z = %.3f, %d placement(s)'
                % (label.lower(), len(points), section_z, len(placements)))
        for sx, sy, tx, ty in placements:
            placed = tuple((sx * (x + tx), sy * (y + ty)) for x, y in points)
            resolved.append((sheet_annotations.REFERENCE, placed, True, label))
    return resolved


def _section_outline(params_path, part_kind, section_z):
    """The outer wire of `part_kind` sectioned at `section_z`, as (x, y) points."""
    doc = App.newDocument('Reference' + part_kind.title().replace('_', ''))
    try:
        tip = build_part.build(doc, part_kind, params_path)
        doc.recompute()
        wires = tip.Shape.slice(V(0.0, 0.0, 1.0), section_z)
        if not wires:
            raise dp.PlacementError(
                'the %s has no section at z = %.3f, so there is nothing to draw it as. The '
                'sheet would show a joint with one side missing.' % (part_kind, section_z))
        outer = max(wires, key=lambda w: abs(_wire_area(w)))
        return _wire_points(outer)
    finally:
        App.closeDocument(doc.Name)


def _wire_area(wire):
    """The signed area of a wire, from its own vertices.

    Not `Face.Area`: a face built on a wire with B-spline edges reports an area that is not
    the wire's -- measured 23% out on this project's own surfaces -- and all this needs is
    which of several wires is the outside one.
    """
    points = _wire_points(wire)
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _wire_points(wire):
    """A wire as (x, y) points in order round it, straight edges kept straight.

    **Every edge is taken in the wire's direction, not in its own.** An edge's parameter runs
    from `FirstParameter` to `LastParameter` in the *curve's* sense, and a wire holds edges
    whose sense is the opposite of the wire's -- `Edge.Orientation` is `'Reversed'` for those.
    Measured 2026-09-07 on a corner section: `OrderedEdges` is connected end to end, and
    **10 of its 14 edges run backwards**. Sampling each one as-is walks the outline forwards
    and backwards alternately, so the polyline jumps across the shape at every reversal --
    which drew the corner's reference outline as a star of crossing dashed lines sitting over
    the bulkhead's own geometry, with no resemblance to a corner.

    `OrderedEdges` rather than `Edges` because the ordering is the other half of the same
    assumption, and it costs nothing to stop relying on it.
    """
    points = []
    for edge in wire.OrderedEdges:
        if isinstance(edge.Curve, Part.Line):
            samples = [edge.valueAt(edge.FirstParameter), edge.valueAt(edge.LastParameter)]
        else:
            samples = edge.discretize(Deflection=REFERENCE_DEFLECTION_MM)
        if edge.Orientation == 'Reversed':
            samples = list(reversed(samples))
        for point in samples:
            if not points or abs(point.x - points[-1][0]) > dp.ZERO_MM \
                    or abs(point.y - points[-1][1]) > dp.ZERO_MM:
                points.append((point.x, point.y))
    if len(points) > 1 and abs(points[0][0] - points[-1][0]) <= dp.ZERO_MM \
            and abs(points[0][1] - points[-1][1]) <= dp.ZERO_MM:
        points.pop()
    return points


def origin_offset(view):
    """Where the model origin sits in the view's own frame, in page millimeters.

    **The placer and TechDraw do not use the same origin, and nothing said so.** Everything in
    `dimension_placement` is measured from the *model* origin -- the longeron axis on a corner,
    the airframe axis on a bulkhead -- because that is what the annotation sets are written
    from and what makes a dimension's two ends arithmetic on the parameters. A `DrawViewPart`
    centres its projection on its own `X, Y`, so a child's `X, Y` is measured from the centre
    of the *projected bounding box*. Those coincide only for a part that happens to be
    symmetric about its own origin, and none of these are: the corner's box runs -4.75 to 7.50
    in both axes, so its centre is 1.375 from the origin, which at 5:1 is **6.875 mm on the
    paper** -- most of two text heights, in both directions at once.

    Every leader tip, every note line and every dimension label carried that offset. It is why
    the leaders pointed into space beside the features they name rather than at them, and it is
    not something the placer could have got right: it placed them correctly in its own frame.

    **Measured, not predicted.** The obvious way to compute this is the centre of
    `projected_bbox`, which is taken from the shape's vertices -- and the extreme point of a
    projected arc is not a vertex, so on a part whose silhouette is an arc between two vertices
    the two answers differ. Asking TechDraw where it put a known point cannot differ from where
    TechDraw put it. A cosmetic vertex at the model origin comes back in view coordinates,
    unscaled and with `y` inverted, and that is the whole conversion.
    """
    tag = view.makeCosmeticVertex3d(V(0.0, 0.0, 0.0))
    view.Document.recompute()
    point = view.getCosmeticVertex(tag).Point
    view.removeCosmeticVertex(tag)
    view.Document.recompute()
    return (point.x * view.Scale, -point.y * view.Scale)


def bind_dimensions(page, view, layout):
    """Turn placed dimensions into `DrawViewDimension`s bound to parameter-placed points.

    The vertex count is read here, immediately before the vertices are made, because cosmetic
    vertices are appended after the projected ones and the projected count moves with the
    variant. A literal index is the face-name defect wearing a different hat.

    **Each dimension is made to say what the placer reserved room for, and that is the whole
    point of a tabulated sheet.** `dimension_placement.Dimension.text` is `None` on a family
    sheet, meaning the view shows the callout *letter* and the table carries the value per `U`;
    `_text_box` then reserves one letter, `callout_width_mm`, about 2.7 mm. Left alone,
    TechDraw formats a dimension with its own default `%.2w` and draws the measured value of
    whichever variant happened to be the representative -- so the sheet asserted `37.50` for a
    quantity its own table gives as seven different numbers, and did it in a box built for one
    character. Both of the things that made the first rendered sheets unreadable were this:
    the values were wrong for every variant but one, and at roughly five times the reserved
    width they collided with each other and with the notes, in lanes packed on the assumption
    that a callout is one letter wide.

    `Arbitrary` is what makes `FormatSpec` literal text rather than a format string. A
    single-variant sheet keeps its number, because there `text` is the value string and the
    placer measured that string rather than bounding it.
    """
    doc = page.Document
    offset_x, offset_y = origin_offset(view)
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
        # The letter on a family sheet, the value string on a single-variant one -- the same
        # choice the placer made when it sized the text box, made again from the same field so
        # the two cannot disagree.
        dimension.Arbitrary = True
        dimension.FormatSpec = (placed.letter if placed.dimension.text is None
                                else placed.dimension.text)
        dimension.References2D = [(view, 'Vertex%d' % first),
                                  (view, 'Vertex%d' % (first + 1))]
        dimension.X = (placed.text_box[0]
                       + (placed.text_box[2] - placed.text_box[0]) / 2.0 + offset_x)
        dimension.Y = (placed.text_box[1]
                       + (placed.text_box[3] - placed.text_box[1]) / 2.0 + offset_y)
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
    offset_x, offset_y = origin_offset(view)
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
            annotation.X = (view.X.Value + offset_x
                            + (placed.text_box[0] + placed.text_box[2]) / 2.0)
            # The center of line `index`'s own row, measured down from the box's top edge.
            annotation.Y = (view.Y.Value + offset_y + top - index * pitch
                            - std.TEXT_HEIGHT_MM / 2.0)
            annotations.append(annotation)

        # **On the page, not merely in the document.** A `DrawLeaderLine` with its
        # `LeaderParent` set but never added to the page is a complete, correctly
        # positioned object that draws nothing: a page renders the views it owns, and
        # it did not own these. Every note on every sheet was therefore floating text
        # with no line to the feature it describes -- which is how it read, and it was
        # not a placement fault. Measured 2026-09-07: three notes on the corner sheet
        # and four on the bulkhead, not one leader among them in the rendered page.
        # **However many points the leader has.** Straight is two -- anchor and text -- and
        # `dimension_placement._route_leaders` (OQ-DES-D16 alternative 4) makes some three, one
        # elbow bent around a dimension line or witness the straight line would have crossed.
        # `DrawLeaderLine.WayPoints` already takes a polyline relative to its own `X, Y`, so the
        # bend costs nothing more here than one more point in the list.
        origin = placed.leader[0]
        leader = doc.addObject('TechDraw::DrawLeaderLine', 'Leader' + str(placed.key).title())
        page.addView(leader)
        leader.LeaderParent = view
        leader.X = origin[0] + offset_x
        leader.Y = origin[1] + offset_y
        leader.WayPoints = [V(point[0] - origin[0], point[1] - origin[1], 0.0)
                            for point in placed.leader]
        out.append((annotations, leader))
    doc.recompute()
    return out


class BuiltSheet(object):
    """One sheet of a drawing: its page, its template, and the view on it.

    `page`      the `DrawPage`
    `template`  its `DrawSVGTemplate`, whose editable fields carry the title block
    `view`      the `BuiltView` this sheet carries
    `number`    which sheet of the drawing this is, from 1
    """

    def __init__(self, page, template, view, number):
        self.page = page
        self.template = template
        self.view = view
        self.number = int(number)

    def __repr__(self):
        return '<BuiltSheet %d: %s>' % (self.number, self.view.spec.name)


def build_sheets(doc, kind, params_path, params, family=None, variant=None,
                 siblings=(), say=None):
    """Every sheet of one family drawing. Returns a list of `BuiltSheet`.

    **One view to a sheet, because two views on one sheet compete for it.** A bulkhead needs
    a plan of the plate and a detail of one corner, and the features they carry differ in
    size by a factor of ten -- which is why there are two. Put on one ANSI A frame they
    divide 239.5 x 141.2 mm between them and *both* come out smaller than the single view
    they replaced: measured 2026-09-07, the plate fell to 1:5 in half the height while the
    detail, which needs width and not height, had the same half. The split was made to solve
    a crowding problem and was creating a second one.

    On separate sheets each view has the whole region and the drawing is as large as the
    frame allows. The cost is paper, and the title block has carried a `SHEET n OF m` field
    since it was generated.

    **Every sheet carries the whole band.** The value table, the dimension key and the
    sheet-coverage statement are laid out once and drawn on all of them: a reader holding the
    detail sheet has callout letters on it and needs the columns those letters head, and a
    sheet that sends them to another sheet to resolve its own annotations is the thing a
    tabulated family drawing exists to avoid.
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
    direction, x_direction = VIEW_DIRECTION[kind]

    # **The band is packed first and the view gets the whole of what is left.** The three
    # blocks a family sheet carries besides the drawing -- the values, the dimension key and
    # the sheet-coverage statement -- go into the fixed rectangle beside the title block, at
    # the largest lettering that fits it. The lettering is what gives: a drawing whose
    # geometry cannot be read is not saved by a legible table beside it, and the view is the
    # thing the sheet is for.
    table, key, coverage, table_height, anchors = sheet_blocks(family, variant, siblings)
    table_anchor, key_anchor, coverage_anchor = anchors
    band_depth = std.TEMPLATE_TITLE_BLOCK_MM[3]
    left, bottom, frame_w, frame_h = frame_page_box()
    region = (left, bottom + band_depth, frame_w, frame_h - band_depth)
    placement = Placement(std.PLACEMENT_BAND, region,
                          table_anchor, key_anchor, coverage_anchor)
    if say and table is not None:
        say('  blocks at %.1f mm lettering; each view has %.1f%% of its frame'
            % (table_height, 100.0 * (frame_h - band_depth) / frame_h))

    # IP-FC-84: a sheet with no family carries no value table to look a callout letter up
    # in, so its view has to carry the number instead -- `sheet_blocks` already returns
    # `(None, None, None, ...)` for this case, this is the other half. `family is not None`
    # rather than a caller-stated flag: the two have never disagreed before now, and a
    # single source keeps them from being asked to.
    product = FAMILY if family is not None else VARIANT
    _quantities, dimensions, notes, declared, specs = ANNOTATIONS[kind](params, product)
    unaccounted = sheet_annotations.check_views(specs, dimensions, notes)
    if unaccounted:
        raise dp.PlacementError(
            'the view set does not account for this drawing\'s annotations:' + NEWLINE
            + NEWLINE.join('  - ' + problem for problem in unaccounted))

    construction = resolve_reference_parts(params_path, declared)
    branch = sheet_annotations.branch_phrase(family, siblings)

    sheets = []
    for number, spec in enumerate(specs, start=1):
        page, template = add_page(doc, name='Page' if number == 1 else 'Page%d' % number)
        try:
            built = place_views(page, tip, [spec], direction, x_direction, [region],
                                dimensions, notes, construction,
                                suffix='' if number == 1 else str(number),
                                all_specs=specs, product=product)
        except dp.PlacementError as exc:
            raise dp.PlacementError(
                'sheet %d of %d, the %s view:' % (number, len(specs), spec.name) + NEWLINE
                + str(exc))
        view = built[0]

        if table is not None:
            add_table(page, table, placement.table_anchor, name='Table%d' % number)
        if key is not None:
            add_table(page, key, placement.key_anchor, name='Key%d' % number)
        if coverage is not None:
            add_table(page, coverage, placement.coverage_anchor,
                      name='Coverage%d' % number)

        template.EditableTexts = dict(
            template.EditableTexts,
            DrawingTitle=(kind.replace('_', ' ').upper()
                          + ((' -- ' + branch) if branch else '')),
            Sheet='%d OF %d' % (number, len(specs)),
            Scale=format_scale(view.scale))
        sheets.append(BuiltSheet(page, template, view, number))
        if say:
            say('  sheet %d of %d: %s at %s'
                % (number, len(specs), spec.name, format_scale(view.scale)))

    doc.recompute()
    return sheets


def build_sheet(doc, kind, params_path, params, family=None, variant=None,
                siblings=(), say=None):
    """The first sheet of a drawing, for callers that want one page.

    Returns `(page, view, layout, scale, placement, built)` as before. Kept because the
    checkers and the older callers ask for a sheet rather than a drawing; `build_sheets` is
    what the set uses.
    """
    sheets = build_sheets(doc, kind, params_path, params, family, variant, siblings, say)
    lead = sheets[0]
    left, bottom, frame_w, frame_h = frame_page_box()
    band_depth = std.TEMPLATE_TITLE_BLOCK_MM[3]
    placement = Placement(std.PLACEMENT_BAND,
                          (left, bottom + band_depth, frame_w, frame_h - band_depth))
    return (lead.page, lead.view.view, lead.view.layout, lead.view.scale, placement,
            [s.view for s in sheets])
