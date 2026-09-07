"""IP-FC-21: what a part's sheet states, and which quantity each callout letter points at.

**Split out of `drawing.py` because both sides of the boundary need it.** `drawing.py` imports
FreeCAD at module scope, so the project virtualenv cannot read it -- and the value table is
computed there, by `tools/drawing_families.py`, from every variant a family covers. A table
whose columns were derived independently of the annotations that point at them is exactly the
failure OQ-DES-D5's recommendation turned on: a column the reader cannot address. So the
annotation set lives here, where both can read it, and nothing in this file may import FreeCAD.

**Two products, and one difference between them.** Section 5.1: a *family* sheet's view carries
callout letters and the values live in the table, because one sheet serves every size; a
*single-variant* sheet's view carries the numbers, because there is nothing to look up. That is
the only thing `product` changes.

**Unit regime: millimeters**, as the OpenSCAD path uses them.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dimension_placement as dp
import drawing_standard as std

# U+00D8. U+2300 is the drafting diameter sign and osifont has no glyph for it.
DIA = chr(216)


class Quantity(object):
    """One number a sheet states, and everything that decides how it is stated.

    **This is the record that makes OQ-DES-D5's recommendation true rather than aspirational.**
    That decision turned on a table column being addressable -- headed by a callout letter that
    points at an annotation on the view -- so a column with no annotation is a number the
    reader cannot look up. The way to guarantee that is to stop having two lists: a quantity
    *is* the
    thing the annotation states and the thing the table tabulates, and the letter is issued
    once to both.

    `name`     what it is called in the parameter mapping, or a derived name for a feature the
               part has that no single parameter is
    `value`    its value on this variant, in millimeters
    `carries`  the interface parameters section 3 counts as stated by this quantity. A feature
               dimension carries the parameters its expression consumes, which is how the
               completeness test reads a *pair* -- the dimension and its callout -- rather than
               a dimension alone.
    `constant` True where the value does not vary across the family. Section 5.1 puts those on
               the view rather than in the table: a column of one repeated number is a column
               spent saying nothing.
    """

    def __init__(self, name, value, carries=(), constant=False):
        self.name = name
        self.value = float(value)
        self.carries = tuple(carries)
        self.constant = bool(constant)
        self.letter = None

    def written(self, product):
        """How this appears in an annotation: its letter on a family sheet, its value on a
        single-variant one.

        Section 5.1's two products differ here and nowhere else in this module. A family
        sheet's view carries letters because one sheet serves every size; a single-variant
        sheet's view
        carries the numbers because there is nothing to look up. A constant is written as
        itself on both, because a letter pointing at a column that says 0.05 nine times is
        worse than the number.
        """
        if product == FAMILY and not self.constant:
            if self.letter is None:
                raise ValueError('%s has no callout letter, so nothing on the view can point '
                                 'at its column' % self.name)
            return self.letter
        return std.format_length(self.value)


FAMILY = 'family'
VARIANT = 'variant'


#: What each quantity is, in words, for the sheet's dimension key.
#:
#: **A callout letter is an index, not a name.** The value table gives `A` seven numbers and
#: the view puts `A` beside a dimension line, which together say what `A` measures *if you can
#: see the view* -- and say nothing at all about the columns whose letters appear only in the
#: table. A reader looking at the `J` column has no way to learn that it is the boss the bolt
#: runs through. So every letter gets a phrase and the sheet prints them.
#:
#: These are deliberately short: the key is a block on a crowded sheet, and a phrase that
#: wraps is a phrase that pushes the value table off the paper. They are also deliberately
#: *nouns for features*, not restatements of the parameter name -- `bolt_offset` is stored as
#: an offset and read as the distance from the longeron axis to the bolt axis, and it is the
#: second that a machinist needs.
DESCRIPTIONS = {
    # The corner
    'corner_radius': 'MOLD LINE RADIUS',
    'bore_diameter': 'LONGERON BORE DIA',
    'longeron_diameter': 'LONGERON DIA',
    'longeron_clearance': 'LONGERON DIA CLEARANCE',
    'lead_in_chamfer': 'BORE LEAD-IN',
    'socket_diameter': 'GREEBLE SOCKET DIA',
    'post_diameter': 'GREEBLE POST DIA',
    'greeble_clearance': 'GREEBLE DIA CLEARANCE',
    'panel_extension': 'PANEL SEAT EXTENSION',
    # Shared with the bulkhead
    'panel_pocket': 'PANEL POCKET DEPTH',
    'panel_thickness': 'PANEL THICKNESS',
    'panel_tolerance': 'PANEL FIT CLEARANCE',
    # The bulkhead
    'mold_half_width': 'MOLD LINE HALF-WIDTH',
    'longeron_offset': 'LONGERON AXIS OFFSET',
    'nub_diameter': 'CORNER NUB DIA',
    'bolt_offset': 'BOLT AXIS FROM LONGERON',
    'bolt_diameter': 'BOLT HOLE DIA',
    'boss_diameter': 'BOLT BOSS DIA',
    'corner_seat_offset': 'CORNER SEAT OFFSET',
}


# ---------------------------------------------------------------------------------------
# Construction geometry
# ---------------------------------------------------------------------------------------
#
# **What the part is not, drawn so that one dimension can stand for four.** A sheet that
# dimensions the bolt at one of four holes, on a plate that is symmetric about both axes and
# both diagonals, has stated the bolt position once and said nothing about the other three --
# and a reader has no way to tell whether the omission means "the same" or "not dimensioned".
# Centre lines on the symmetry axes are the drafting convention that closes that gap, and they
# are the reason the marks and lines below are declared per part rather than switched on for
# the view: which axes a part is symmetric about is a fact about the part.
#
# **The symmetry declared here was measured, not assumed** (2026-09-07, on built solids by
# reflecting the shape and intersecting it with itself):
#
#     corner     mirror about y = x        0.999950 of the volume    the only one
#                mirror about x = 0        0.539851
#                mirror about y = 0        0.539851
#                mirror about y = -x       0.283603
#     bulkhead   all four                  1.000000 each             full D4
#
# The corner's 5e-5 shortfall is 0.34 mm3 of 6781 and sits at the boolean tolerance; the
# bulkhead's four are exact to six figures. So the corner gets one centre line and the
# bulkhead gets four, which is what the parts are rather than what looks tidy.
#
# A record is a plain tuple whose first element says which kind it is. Nothing here may
# import FreeCAD -- `drawing.py` turns these into cosmetic edges on its side of the boundary.

#: How much wider than the features it takes in a detail view's boundary is drawn. A
#: quarter, so the circle stands clear rather than cutting the outermost feature.
DETAIL_MARGIN = 1.25

#: A cross on a feature's axis: `(CENTER_MARK, (x, y), radius)`.
#:
#: **Only on an axis a dimension is taken from.** TechDraw's `ArcCenterMarks` marks every arc
#: in the projection, which on a bulkhead is every fillet and every lead-in as well as the
#: bores and the bolts, and a mark on a fillet asserts an axis that locates nothing. The
#: switch is off (`drawing_standard.view_appearance`) and these are what get one.
CENTER_MARK = 'center_mark'

#: A symmetry axis: `(CENTER_LINE, (x1, y1), (x2, y2))`.
#:
#: **The endpoints are where the *geometry* ends, not where the line should be drawn to.** A
#: centre line has to stand a few millimetres clear of the part to read as an axis rather than
#: as an edge, and a few millimetres is a quantity on the *paper* -- like the text height it is
#: derived from, and unlike everything else in this module, which is the part. `drawing.py`
#: adds the overrun, because it is the side that knows the scale.
#:
#: Applied here instead it cost a preferred scale on every sheet: 5.25 mm of model overrun at
#: each end is 26 mm of paper at the corner's 5:1, so the extent the view was fitted to grew by
#: half again and the scale search dropped to 2:1. Measured 2026-09-07.
CENTER_LINE = 'center_line'

#: The outline of a part that is not this one: `(REFERENCE, ((x, y), ...), closed, label)`.
#: Drawn in phantom line, ISO 128 type K. Without it there is nothing on the sheet for a fit
#: to be a fit *to*: `panel_pocket` and `panel_thickness` are two numbers whose whole content
#: is the gap between them, and a sheet showing only the pocket shows one side of a joint.
REFERENCE = 'reference'

#: Another *part* in phantom outline, sectioned and placed:
#: `(REFERENCE_PART, kind, section_z, ((sx, sy, tx, ty), ...), label)`.
#:
#: **The mating part is drawn from the mating part.** A corner's section is an arc, two
#: seating flats, a diagonal mask and a greeble mouth, and any outline of it written here would
#: be a second implementation of `corner_tree` -- one that no cross-kernel check covers and
#: that goes quietly wrong the first time the corner changes. `drawing.py` builds the real one
#: from the `corner_parameters` the same export already carries, slices it at `section_z`, and
#: draws the wire.
#:
#: Each placement is `(sx, sy, tx, ty)`, applied as `(sx * (x + tx), sy * (y + ty))`: a
#: translation to where the part sits and a mirror for the instances the symmetry produces.
REFERENCE_PART = 'reference_part'


def center_marks(centers, radius):
    """A centre mark on each of `centers`, all of one radius."""
    return [(CENTER_MARK, (x, y), radius) for x, y in centers]


def rectangle(x0, y0, x1, y1):
    """The four corners of an axis-aligned rectangle, counter-clockwise."""
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def axis_line(direction, reach):
    """A centre line through the origin along `direction`, out to `reach` each way."""
    dx, dy = direction
    return (CENTER_LINE, (-dx * reach, -dy * reach), (dx * reach, dy * reach))


# ---------------------------------------------------------------------------------------
# What a family sheet covers, and which variant it was drawn from
# ---------------------------------------------------------------------------------------
#
# **A family sheet is drawn from one variant and stands for many, and until 2026-09-07 it said
# neither.** Three bulkhead sheets came out of the set, identical in title, differing in their
# tables and in the shape of the drawn view, with nothing anywhere on the paper to say what
# distinguished them or which size the geometry was. A reader could see that the three were
# different and had no way to learn how -- and could measure the view and get one variant's
# numbers while the table gave eight.
#
# `topology` on a family record is the branch: a list of `[condition, value]` that
# `drawing_families` partitions on. These turn it into something a person reads.

#: A topology condition as a phrase, `(when true, when false)`. A condition absent from this
#: falls back to its own text, which reads as unfinished -- which it is -- rather than
#: silently dropping a branch the sheets differ by.
TOPOLOGY_PHRASES = {
    'panel.thickness != 0': ('PANELLED', 'NO PANEL'),
    'corner seating flat': ('CORNER SEAT', 'NO CORNER SEAT'),
    'boom_bulkhead.make_vert_web': ('VERTICAL WEB', 'NO VERTICAL WEB'),
    'boom_bulkhead.make_lower_web': ('LOWER WEB', 'NO LOWER WEB'),
}


def topology_phrase(condition, value):
    """One topology entry in words."""
    if isinstance(value, bool):
        phrases = TOPOLOGY_PHRASES.get(condition)
        if phrases:
            return phrases[0] if value else phrases[1]
        return ('' if value else 'NO ') + str(condition).replace('_', ' ').upper()
    # A valued condition is named by its value alone -- `END` rather than `TYPE END` -- once
    # the sheet is already headed by the kind. The block is measured against what is left of
    # a strip beside the value table, and a word that adds nothing costs a real millimetre.
    return str(value).upper()


def branch_phrase(family, siblings=()):
    """What distinguishes this family from the other families of its kind, in words.

    **Only the conditions that actually differ.** Every frame bulkhead family carries
    `bulkhead.type = END` and both boom-web flags false, so naming them would fill the line
    with facts that separate nothing while the two that matter -- whether there is a panel and
    whether the corner seating flat survives -- got no more room than they did. What a reader
    wants from three sheets with one title is the difference.

    With no siblings to compare against, every condition is a distinguishing one: a sheet
    standing alone still has to say what it is.
    """
    topology = list((family or {}).get('topology') or [])
    others = [list(s.get('topology') or []) for s in siblings
              if s.get('key') != (family or {}).get('key')]
    phrases = []
    for index, entry in enumerate(topology):
        condition, value = entry[0], entry[1]
        varies = not others or any(
            index < len(other) and other[index][1] != value for other in others)
        if varies:
            phrases.append(topology_phrase(condition, value))
    return ', '.join(phrases)


def variant_phrase(variant):
    """The variant the geometry was drawn from, in words.

    Reads out the axes the sweep is over -- size, panel stock, type -- because those are what
    the reader has in hand when they ask which of the table's rows the picture is.
    """
    variant = variant or {}
    parts = []
    if variant.get('U') is not None:
        parts.append('U %s' % variant['U'])
    if variant.get('panel_name'):
        parts.append('%s PANEL' % str(variant['panel_name']).upper())
    for key in ('bulkhead_type_name', 'type_name'):
        if variant.get(key):
            parts.append(str(variant[key]).upper())
            break
    return ', '.join(parts) or 'NOT RECORDED'


def coverage_rows(family, variant, siblings=()):
    """The sheet-coverage block's rows, as (label, value).

    **`DO NOT SCALE` is a row rather than a remark.** The view is drawn at a stated scale from
    one variant, which is honest and also an invitation to measure it: at 1:1 a reader gets
    the drawn variant's numbers, and the table gives eight others. The scale stays -- a view
    with no scale is worse -- and the sheet says outright that the numbers come from the
    table.
    """
    rows = [('GEOMETRY SHOWN', variant_phrase(variant))]
    branch = branch_phrase(family, siblings)
    if branch:
        rows.append(('FAMILY', branch))
    count = (family or {}).get('variants')
    if count:
        rows.append(('VARIANTS', '%d, SEE TABLE BELOW' % int(count)))
    rows.append(('DO NOT SCALE', 'VALUES ARE TABULATED'))
    return rows


# ---------------------------------------------------------------------------------------
# What views a sheet carries, and which annotations go on which
# ---------------------------------------------------------------------------------------
#
# **One view could not carry a bulkhead, and the review said so before the layout did.** The
# plate is 50 mm across at U = 0.5 and the features that need dimensioning -- the bolt in its
# boss, the greeble post and nub, the corner seat, the panel inset -- are all inside a 9 mm
# radius of one longeron axis. Drawn on the plan at a scale that fits the plate, those are
# four dimensions and five notes crowding a corner a few millimetres wide, and the plate has
# to shrink to make room for the note bands: measured 1:2, with the view at 52.4 % of the
# frame. The mold line half-width and the longeron offset are the opposite case -- they span
# the plate and mean nothing magnified.
#
# So a sheet has a **plan** and a **detail**, and each says which annotations it carries.
#
# **The view says what it carries, rather than each annotation saying where it goes.** Two
# records per kind against thirty tuples to edit, and it gives the invariant for free:
# `check_views` refuses a sheet where an annotation is named by no view or by two. An
# annotation that quietly landed on neither would be a dimension the sheet was supposed to
# state and does not, which is section 3's completeness test failing where nothing looks.


class SheetView(object):
    """One view on a sheet.

    `name`        what it is called, and what its caption says
    `clip`        `(x, y, radius)` in model millimeters, or None for the whole part. A clipped
                  view is drawn from the part intersected with a cylinder on that axis.
    `dimensions`  the quantity names whose dimensions this view carries
    `notes`       the note keys this view carries
    `caption`     what is printed under it, `None` for the plan, which needs none

    **A clip is a solid intersection, not a `DrawViewDetail`.** TechDraw's detail view does
    its cut on a worker thread, and under `freecadcmd` -- which is what builds these documents
    -- the first recompute after adding one prints *"Detail is waiting for detail cut to
    finish"* and the process dies. Measured 2026-09-07 on FreeCAD 1.1.3. Intersecting the
    solid is synchronous, and it is better in the way that matters here: the clipped solid is
    in the **same model coordinates as the whole part**, so a dimension on the detail binds to
    the same model points the annotation set already declares, with no translation and no
    second frame to get wrong.
    """

    def __init__(self, name, clip=None, dimensions=(), notes=(), caption=None):
        self.name = name
        self.clip = tuple(clip) if clip else None
        self.dimensions = tuple(dimensions)
        self.notes = tuple(notes)
        self.caption = caption

    def __repr__(self):
        return '<SheetView %s%s>' % (self.name, ' clipped' if self.clip else '')


def combined_view(views, dimensions, notes):
    """The declared views collapsed into one that carries everything.

    **The fallback for a sheet whose split will not fit the paper**, and it is a fallback
    rather than the answer: a plan and a detail exist because the features differ in size by
    a factor of ten, and putting them back on one view puts that problem back. It keeps the
    leading view's name and drops the clip, so the sheet is the whole part with every
    annotation on it -- which is what these sheets were before the split and what they go
    back to being when a sheet has no room for two.
    """
    return [SheetView(views[0].name,
                      dimensions=tuple(q.name for q, _p1, _p2, _a, _v in dimensions),
                      notes=tuple(key for key, _anchor, _lines in notes))]


def check_views(views, dimensions, notes):
    """Refuse a view set that does not account for every annotation exactly once."""
    declared = {}
    for view in views:
        for name in view.dimensions:
            declared.setdefault(('dimension', name), []).append(view.name)
        for key in view.notes:
            declared.setdefault(('note', key), []).append(view.name)

    problems = []
    for quantity, _p1, _p2, _axis, _value in dimensions:
        seen = declared.pop(('dimension', quantity.name), [])
        if not seen:
            problems.append('%s is dimensioned and no view carries it' % quantity.name)
        elif len(seen) > 1:
            problems.append('%s is carried by %s' % (quantity.name, ' and '.join(seen)))
    for key, _anchor, _lines in notes:
        seen = declared.pop(('note', key), [])
        if not seen:
            problems.append('the %s note is written and no view carries it' % key)
        elif len(seen) > 1:
            problems.append('the %s note is carried by %s' % (key, ' and '.join(seen)))
    for (what, name), views_named in sorted(declared.items()):
        problems.append('%s carries the %s %s, which this variant does not have'
                        % (' and '.join(views_named), what, name))
    return problems


def description(field):
    """What `field` is, in words, for the dimension key.

    Falls back to the field's own name rather than raising. A quantity added without a phrase
    should print something a reader can at least recognise -- `GREEBLE TOLERANCE` reads as an
    unfinished description, which is what it is, where a missing row reads as a letter that
    means nothing and a raise would cost the whole sheet.
    """
    return DESCRIPTIONS.get(field) or str(field).replace('_', ' ').upper()


def issue_letters(quantities):
    """Give each varying quantity a callout letter, in a stated order.

    Deterministic by construction: the order is the order the part's annotation set declares,
    which is fixed source, and section 5.5 wants the same sheet from the same input every time.
    Constants take no letter -- they are printed as themselves.
    """
    alphabet = iter(std.CALLOUT_ALPHABET)
    for quantity in quantities:
        if quantity.constant:
            continue
        try:
            quantity.letter = next(alphabet)
        except StopIteration:
            raise dp.PlacementError(
                'this sheet needs more than %d callout letters. The alphabet omits I, O and Q '
                'because they read as digits, and running out of it means the view is '
                'carrying more than one drawing.' % len(std.CALLOUT_ALPHABET))
    return quantities


def corner_seat_span(params):
    """The corner seating flat's span, in millimeters. Zero means the face is not there.

    **One implementation, read from both sides**, because two things depend on it and they
    must not disagree: `bulkhead_annotations` dimensions the flat, and
    `tools/drawing_families` partitions families on whether it exists. A part whose sheet
    dimensions a face its family signature says is absent is the failure both are for.

    The flat's inboard end is set by `corner_tree.nominal_flat_offset`,

        -max(longeron_radius + longeron_tolerance + longeron_chamfer,
             (panel_overlap + panel_offset) - (corner_radius - panel_thickness
                                               - panel_tolerance))

    with `longeron_chamfer = extrusion_width`. Writing the two branches `a` and `b`, the span
    works out as `max(a, b) - b` -- so it is **exactly zero when the panel branch wins**, and
    the face is gone rather than narrow. Verified against built solids on 2026-08-28 at four
    variants: 1U/3-16in span 0.5250 at x 32.7375, 1U/0mm span 7.1500, 4U/1-4in span 27.8500,
    and 0.5U/1mm where the formula says absent and the part has no such face.

    Returns None where the part is not driven by `extrusion_width` at all -- the boom
    bulkhead's mapping does not pass it and no boom module mentions `longeron_chamfer`, so a
    boom bulkhead has no flat of this kind to have.
    """
    if 'extrusion_width' not in params:
        return None
    pocket = params['panel_thickness'] + params['panel_tolerance']
    chamfer_branch = (params['longeron_radius'] + params['longeron_tolerance']
                      + params['extrusion_width'])
    panel_branch = ((params['panel_overlap'] + params['panel_offset'])
                    - (params['corner_radius'] - pocket))
    return max(chamfer_branch, panel_branch) - panel_branch


def corner_annotations(params, product=FAMILY):
    """The corner's interface quantities, dimensions and OQ-DES-D2 notes.

    **Section 3's floor for the corner is ten parameters and they do not become ten
    dimensions.** Six of them reach the reader through a *note* rather than a dimension line,
    because the parameter is a nominal and the part is built to the nominal plus a clearance --
    there is no pair of faces the nominal is the distance between. That is section 3's fourth
    gap, and OQ-DES-D2 decided the pairing: the dimension carries the feature as built and the
    note beside it names the hardware the feature is for, both generated from the same
    expression so they cannot drift.

    The corner's section is drawn looking down the bay axis, and its local origin is the
    longeron axis -- the bore is centred there and the mold line is an arc of `corner_radius`
    about it, which is why every dimension below is taken from 0.

    **The bore and the pocket get quantities of their own even though neither is a parameter.**
    They are what the part is built to, and OQ-DES-D2 says the sheet states them; a reader who
    had only the nominal and the clearance would be doing arithmetic to find out what the part
    actually measures, which is the thing the decision refused.

    **A corner with no panel states no panel pocket, and that is section 2 rather than a
    special case.** A parameter that is zero across a whole family is the *absence* of the
    joint, not a dimension the sheet is missing, and the corner's two families differ by
    exactly that: one has a panel slot and one does not. `drawing_families` already drops
    those columns from the table as structural zeros. Until 2026-08-27 this function did not
    drop them from the annotation set, so the unpanelled corner's sheet asked for a
    `panel_pocket` dimension of 0.00 -- and section 5.2's H5 refused it at every preferred
    scale, correctly, because a dimensioned zero asserts an inspectable coincident fit and
    there is nothing there to inspect. The sheet could not be drawn at all. **`panel_extension`
    stays**: `panel_overlap` is nonzero whether or not a panel is fitted, so the corner still
    extends past the longeron axis and the distance is still a distance.
    """
    radius = params['corner_radius']
    longeron = params['longeron_radius']
    longeron_fit = params['longeron_tolerance']
    thickness = params['panel_thickness']
    panel_fit = params['panel_tolerance']

    greeble = params['greeble_thickness']
    greeble_fit = params['greeble_tolerance']
    chamfer = params['extrusion_width']

    bore = longeron + longeron_fit
    pocket = thickness + panel_fit
    seat = radius - pocket

    # Joint 2, from `greeble_radius_of` in `fuselage_corner_geometry.scad`: the socket is the
    # bore plus the greeble wall plus the clearance, and the *post* is the same without the
    # clearance. Section 2 says the joint is carried entirely on the corner -- the bulkhead
    # re-evaluates the same shape and passes 0 -- so a drawing that dimensioned both sides at
    # nominal would be right about each part and wrong about the joint.
    socket = bore + greeble + greeble_fit
    post = bore + greeble

    # Joint 4's remaining term. **Measured on the built solid rather than read off the
    # register**: the corner has a planar face normal to X at x = -7.2625 at U = 1 with 3/16 in
    # panel, and `panel_overlap + panel_offset` is 7.2625 -- so the extension runs from the
    # longeron axis to exactly that face, and the expression is the distance rather than
    # something the clearance has already been folded into.
    #
    # **Measuring rather than reading is what caught the register being wrong.** Section 2's
    # row 4 said `panel_overlap + panel_offset - panel_tolerance` until 2026-08-28 -- one
    # clearance short, 7.1625 against the part's 7.2625, and 14.2500 against 14.3500 at 4U with
    # 1/4 in panel. Section 3's completeness test could never have found it: both forms name
    # the same parameters. Corrected under OQ-DES-D8, on OQ-DES-D9's finding that section 2 is
    # an analysis of the implementation, so where it and a part disagree the part is right.
    #
    # The slot mouth sits at `-(panel_offset - panel_tolerance)`, which makes the slot itself
    # `panel_overlap + panel_tolerance` deep: the panel's entry plus its fit.
    extension = params['panel_overlap'] + params['panel_offset']

    panelled = abs(thickness) > dp.ZERO_MM

    declared = [
        Quantity('corner_radius', radius, ('corner_radius',)),
        Quantity('bore_diameter', 2.0 * bore, ('longeron_radius', 'longeron_tolerance')),
        Quantity('longeron_diameter', 2.0 * longeron, ('longeron_radius',)),
        Quantity('longeron_clearance', 2.0 * longeron_fit, ('longeron_tolerance',),
                 constant=True),
        Quantity('lead_in_chamfer', chamfer, ('extrusion_width',), constant=True),
        # `greeble_thickness` is in both sums and was in neither `carries` tuple until
        # 2026-08-30. The values were always right; what was missing was the declaration, so
        # section 3 could not demand the wall thickness that sets the socket. IP-FC-107.
        Quantity('socket_diameter', 2.0 * socket,
                 ('longeron_radius', 'longeron_tolerance', 'greeble_thickness',
                  'greeble_tolerance')),
        Quantity('post_diameter', 2.0 * post,
                 ('longeron_radius', 'longeron_tolerance', 'greeble_thickness')),
        Quantity('greeble_clearance', 2.0 * greeble_fit, ('greeble_tolerance',),
                 constant=True),
    ]
    if panelled:
        declared += [
            Quantity('panel_pocket', pocket, ('panel_thickness', 'panel_tolerance')),
            Quantity('panel_thickness', thickness, ('panel_thickness',)),
            Quantity('panel_tolerance', panel_fit, ('panel_tolerance',), constant=True),
        ]
    declared.append(
        Quantity('panel_extension', extension, ('panel_overlap', 'panel_offset')))

    quantities = issue_letters(declared)
    by_name = {q.name: q for q in quantities}

    def w(name):
        return by_name[name].written(product)

    # A point on the bore arc, on the lower left where a leader has room to leave the section.
    angle = math.radians(255.0)
    bore_point = (bore * math.cos(angle), bore * math.sin(angle), 0.0)
    mold_point = (radius * math.cos(math.radians(52.0)),
                  radius * math.sin(math.radians(52.0)), 0.0)
    socket_point = (socket * math.cos(math.radians(160.0)),
                    socket * math.sin(math.radians(160.0)), 0.0)

    # **Where the pocket actually is, along the seating face.** The pocket runs from the
    # part's end face at `-extension` to the slot's inner end at `-panel_offset`; halfway
    # along that is a point on the pocket floor with material above and below it.
    #
    # It was taken at `x = 0` until 2026-09-07 -- on the vertical through the longeron axis,
    # where there is no pocket at all, only the bore below and the mold arc above. The value
    # was right, because the seating face is flat and the distance to the mold line is the
    # same everywhere along it; what was wrong is that `F PANEL POCKET DEPTH` pointed at a
    # place the part has no pocket, and a dimension that measures the right distance in the
    # wrong place is a dimension a reader cannot check.
    pocket_x = -(extension + params['panel_offset']) / 2.0

    dimensions = []
    if panelled:
        # The pocket the panel seats in, which is the one interface on this part that *is* a
        # distance between two real parallel faces.
        dimensions.append(
            (by_name['panel_pocket'], (pocket_x, seat, 0.0), (pocket_x, radius, 0.0),
             dp.VERTICAL, pocket))
    dimensions += [
        # The mold line as a half-width from the longeron axis, which is where the panel's
        # outer surface has to land.
        (by_name['corner_radius'], (0.0, 0.0, 0.0), (0.0, radius, 0.0), dp.VERTICAL, radius),
        # The panel extension, from the longeron axis out to the end face, taken along the
        # slot's outer surface because that is the face the panel lies on.
        (by_name['panel_extension'], (0.0, seat, 0.0), (-extension, seat, 0.0),
         dp.HORIZONTAL, extension),
    ]

    notes = [
        ('bore', bore_point,
         ('%s%s BORE' % (DIA, w('bore_diameter')),
          'FOR %s%s LONGERON' % (DIA, w('longeron_diameter')),
          '%s DIA CLEARANCE' % w('longeron_clearance'),
          '%s LEAD-IN' % w('lead_in_chamfer'))),
        ('socket', socket_point,
         ('%s%s SOCKET' % (DIA, w('socket_diameter')),
          'FOR %s%s POST' % (DIA, w('post_diameter')),
          '%s DIA CLEARANCE' % w('greeble_clearance'))),
        ('mold', mold_point,
         ('R%s MOLD LINE' % w('corner_radius'),)),
    ]
    if panelled:
        notes.append(
            ('pocket', (pocket_x, seat, 0.0),
             ('%s POCKET' % w('panel_pocket'),
              'FOR %s PANEL' % w('panel_thickness'),
              '%s CLEARANCE' % w('panel_tolerance'))))

    construction = corner_construction(params, radius, bore, seat, thickness, extension,
                                       panelled)
    # **One view, because the corner is already a detail.** It is a section a few millimetres
    # across drawn at 5:1, and every quantity on it is about the same few millimetres -- there
    # is no pair of scales to separate. What crowds this sheet is the four multi-line notes,
    # which a second view would not thin out.
    views = [SheetView('SECTION',
                       dimensions=tuple(q.name for q, _p1, _p2, _a, _v in dimensions),
                       notes=tuple(key for key, _anchor, _lines in notes))]
    return quantities, dimensions, notes, construction, views


def corner_construction(params, radius, bore, seat, thickness, extension, panelled):
    """The corner's centre mark, its one symmetry axis, and the panels it seats.

    **One centre mark, because the corner has one located axis.** The longeron bore, the
    greeble socket and the lead-in are all about the same origin, so they share a mark; every
    other arc in the projection is a fillet, and a fillet is a blend rather than a feature a
    dimension is taken from.

    **One centre line, on `y = x`, because that is the only mirror the part has.** Measured
    2026-09-07 by reflecting the built solid and intersecting: `y = x` recovers 0.999950 of
    the volume and the other three candidates recover 0.54, 0.54 and 0.28. So the corner is
    *not* symmetric about its own axes -- the panel it laps and the panel it seats are the
    same panel seen twice, and the diagonal is what says so.

    **The panels are drawn because the pocket is one side of a fit.** `panel_pocket` and
    `panel_thickness` differ by `panel_tolerance`, and with no panel on the sheet the reader
    sees two numbers a tenth apart and nothing to tell them the tenth is the clearance.

    **The panel's outer surface is the mold line, and the clearance is behind it**, on both
    faces of the joint:

        outer surface     `y = corner_radius`. The panel skins the airframe, so its outside
                          *is* the outer mold line -- that is what the mold line is
        inner surface     one `panel_thickness` in, at `corner_radius - panel_thickness`,
                          which leaves `panel_tolerance` between it and the pocket floor at
                          `corner_radius - panel_thickness - panel_tolerance`
        the lapped end    `x = -panel_offset`, one `panel_tolerance` short of the slot's own
                          end at `slot_x + slot_w = -panel_offset + panel_tolerance`

    So the fit shows as a gap on both faces of the joint rather than as the panel lying on
    the pocket floor with all the slack outboard -- which is what this drew until 2026-09-07,
    and which put the panel's outer surface a tenth of a millimetre *inside* the airframe's
    own outer surface.

    It runs out past the part's end face because a panel does not stop there -- it spans the
    bay to the next corner -- and an outline stopping flush would read as a part this size.
    """
    root_half = 0.5 ** 0.5

    construction = center_marks([(0.0, 0.0)], bore)
    # The diagonal, from the far end of the seating faces out to the mold line. **The two ends
    # are not the same distance from the origin, because the part is not.** Outboard it ends on
    # the mold arc, at `radius`, so the coordinate is `radius / sqrt(2)`; inboard the two
    # seating faces cross at `(-extension, -extension)`, which is `extension` in each
    # coordinate already.
    construction.append(
        (CENTER_LINE, (-extension, -extension),
         (radius * root_half, radius * root_half)))

    if panelled:
        # **How far past the part's end face the panel is drawn, and why it is short.** The
        # outline goes into the bbox the dimension placer lanes around, so every millimetre of
        # overhang is a millimetre the part loses on the sheet: drawn a full mold line radius
        # past the face it grew the corner's extent from 12.3 mm to 19.8 mm and cost a
        # preferred scale. Two panel thicknesses, or a third of the radius, is enough to read
        # as a part that continues and small enough not to be paid for.
        far = -(extension + max(2.0 * thickness, radius / 3.0))
        end = -params['panel_offset']
        inner = radius - thickness
        construction.append(
            (REFERENCE, rectangle(far, inner, end, radius), True, 'PANEL'))
        # The same panel on the other seating face, which is the `y = x` mirror of the first.
        construction.append(
            (REFERENCE, rectangle(inner, far, radius, end), True, 'PANEL'))
    return construction


def bulkhead_annotations(params, product=FAMILY):
    """The frame bulkhead's interface quantities, dimensions and OQ-DES-D2 notes.

    **The view is the plate face, looking down the airframe axis**, and the part's local origin
    is the airframe axis itself -- the plate is four-fold symmetric about it, so every
    dimension below is taken from 0 or between two hole axes.

    **Every value here was measured on the built solid before it was written.** At 1U with
    3/16 in panel and the `end_bolt` type the part has planar faces normal to X at
    **+/-45.1375**, cylinders of **R2.05** at (+/-40, +/-40), **R3.25** and **R4.45** about the
    same axes, and **R2.00** at (+/-32, +/-32) -- which is
    `unit_width/2 - panel_thickness - panel_tolerance`, the longeron axis at
    `unit_width/2 - corner_radius`, the bore, the greeble post, its nub, and the
    bolt at `bolt_offset` in each axis from the longeron. Reading those
    off the parameter list instead would have got `bolt_offset` wrong: §2's register describes
    it as "on the diagonal", and the part places it **8.00 in each axis**, 11.31 along the
    diagonal. The dimension states what the part measures.

    **Joint 2 is stated from the other side here.** §2 says the corner's socket is opened out
    by `greeble_tolerance` and the bulkhead's post stays nominal, so the post is dimensioned
    at nominal and the note says which side carries the clearance -- otherwise a reader
    measuring the post against the corner's socket finds a 0.05 discrepancy and no statement of
    which one is deliberate.

    **What this does not carry, and it is not an oversight.** The cowling type's
    flange -- section 2's joint 7, and the only thing on a frame bulkhead that
    consumes `cowl_flange_tolerance`,
    `cowl_n_perimeters` or `extrusion_width` -- is not here, because `bulkhead_full.emit()`
    builds the plain end type and nothing else (IP-FC-9; IP-FC-12 ports the rest). Writing
    annotations for a feature no code path can build would put untested strings on the one
    sheet nothing can draw. The consequence is a gap in §3's completeness test, and it is
    reported rather than papered over -- see OQ-DES-D6.
    """
    half = params['unit_width'] / 2.0
    radius = params['corner_radius']
    longeron = params['longeron_radius']
    longeron_fit = params['longeron_tolerance']
    greeble = params['greeble_thickness']
    nub = params['greeble_nub_thickness']
    thickness = params['panel_thickness']
    panel_fit = params['panel_tolerance']
    bolt = params['bolt_hole_radius']
    boss = params['bolt_thickness']
    offset = params['bolt_offset']

    panelled = abs(thickness) > dp.ZERO_MM

    # The outer face, which §2 establishes *is* the panel's seating surface: it sits
    # `panel_thickness + panel_tolerance` inboard of the mold line, and one of its flats
    # measures the panel's exposed span times the bulkhead thickness.
    pocket = thickness + panel_fit
    seat = half - pocket

    # Register joint 3's face. Present or absent for the whole family, since OQ-DES-D6 put the
    # condition in the topology signature -- so this is not a per-variant dodge, it is asking
    # which of two families this sheet is for.
    seat_span = corner_seat_span(params)
    seated = seat_span is not None and seat_span > dp.ZERO_MM
    # The corner seating faces' offset from the longeron axis -- `nominal_flat_offset` in
    # `corner_tree`, and the larger of the two branches OQ-DES-D6 measured. The diagonal face
    # sits at this over root two from the axis, verified on built solids 2026-08-28: 1.8738 at
    # 1U with 3/16 in panel where the bore branch wins, and 2.0153 at 0.5U with 1 mm panel
    # where the panel branch does.
    seat_offset = ((longeron + longeron_fit + params['extrusion_width']) if seated
                   else ((params['panel_overlap'] + params['panel_offset'])
                         - (radius - pocket)))
    # The longeron axis, which is where the corner sits and therefore where everything on this
    # part is arranged around.
    axis = half - radius
    bore = longeron + longeron_fit
    post = bore + greeble
    nub_radius = post + nub
    boss_radius = bolt + boss
    bolt_axis = axis - offset

    declared = [
        # `half` is `unit_width / 2`, so this states `unit_width` -- declared as of
        # 2026-08-30, IP-FC-107. Register row 5 locates the panel's seating face from it.
        Quantity('mold_half_width', half, ('unit_width',)),
        Quantity('longeron_offset', axis, ('corner_radius',)),
        Quantity('bore_diameter', 2.0 * bore, ('longeron_radius', 'longeron_tolerance')),
        Quantity('longeron_diameter', 2.0 * longeron, ('longeron_radius',)),
        Quantity('longeron_clearance', 2.0 * longeron_fit, ('longeron_tolerance',),
                 constant=True),
        Quantity('post_diameter', 2.0 * post,
                 ('longeron_radius', 'longeron_tolerance', 'greeble_thickness')),
        Quantity('nub_diameter', 2.0 * nub_radius, ()),
        Quantity('bolt_offset', offset, ('bolt_offset',)),
        Quantity('bolt_diameter', 2.0 * bolt, ('bolt_offset',)),
        Quantity('boss_diameter', 2.0 * boss_radius, ()),
    ]
    if panelled:
        declared += [
            Quantity('panel_pocket', pocket, ('panel_thickness', 'panel_tolerance')),
            Quantity('panel_thickness', thickness, ('panel_thickness',)),
            Quantity('panel_tolerance', panel_fit, ('panel_tolerance',), constant=True),
        ]
    # **Register joint 3's offset, and it carries what actually sets it.** Where the bore
    # branch wins -- every member of a family the seating flat exists on, since OQ-DES-D6 put
    # that condition in the topology signature -- the offset is
    # `longeron_radius + longeron_tolerance + extrusion_width` and follows `U` alone, so it is
    # one table column. Where the panel branch wins it follows `U` and the panel stock both.
    # Declaring one `carries` list for both cases would have the sheet claim to state
    # parameters that set nothing on it.
    declared.append(
        Quantity('corner_seat_offset', seat_offset,
                 ('longeron_radius', 'longeron_tolerance', 'extrusion_width') if seated
                 else ('corner_radius', 'panel_overlap', 'panel_offset', 'panel_thickness',
                       'panel_tolerance')))

    quantities = issue_letters(declared)
    by_name = {q.name: q for q in quantities}

    def w(name):
        return by_name[name].written(product)

    # **The outer face is located by a datum and a setback, not by its own coordinate**, and
    # the reason is measurable rather than aesthetic. The face sits at
    # `unit_width/2 - panel_thickness - panel_tolerance`, which follows *both* size axes, so
    # tabulating it directly prints a band of **eight columns** -- one per panel stock -- of
    # three-digit numbers, and the panelled end family's table came to **167.0 mm** against a
    # 108.5 mm band. Split into the mold line (`U` alone) and the pocket (`panel` alone) it is
    # two ordinary columns.
    #
    # It is also how the corner already states the same joint: `corner_radius` locates the mold
    # line and `panel_pocket` is the setback from it, and the reader subtracts. Two parts
    # meeting at one joint should not describe it two different ways.
    dimensions = [
        # The mold line, from the airframe axis. A datum rather than a face -- the bulkhead is
        # cut back from it by exactly the panel it seats -- which is what a mold line is, and
        # section 2 already treats `unit_width/2` as this airframe's.
        (by_name['mold_half_width'], (0.0, 0.0, 0.0), (0.0, half, 0.0),
         dp.VERTICAL, half),
        # Where the corner sits.
        (by_name['longeron_offset'], (0.0, 0.0, 0.0), (axis, 0.0, 0.0),
         dp.HORIZONTAL, axis),
        # The bolt from the longeron axis, taken between the two hole axes because that is
        # what the part places rather than a distance to a face.
        (by_name['bolt_offset'], (axis, axis, 0.0), (bolt_axis, bolt_axis, 0.0),
         dp.HORIZONTAL, offset),
    ]
    if panelled:
        # The setback from the mold line to the seating face, which is the panel and its fit.
        #
        # **Taken at the longeron axis rather than on the plate's own centreline**, and the
        # reason is where it gets drawn. The seating face is flat across the whole side, so
        # the distance is the same wherever it is measured -- but a dimension on the
        # centreline belongs to no local feature, and the placer put its line out at the
        # frame's margin with an extension line running most of the sheet to reach a 1.1 mm
        # gap. Measured at the corner it sits inside the detail view with the bolt, the post
        # and the corner seat, which is where a reader looking at the panel joint is already
        # looking.
        dimensions.append(
            (by_name['panel_pocket'], (axis, seat, 0.0), (axis, half, 0.0),
             dp.VERTICAL, pocket))
    # The corner seating faces, register joint 3, dimensioned where the diagonal crosses the
    # line through the longeron axis -- which is the offset the geometry is built from.
    #
    # **Not the flat's span, which was the first attempt and cost eight table columns.** The
    # span is `max(a, b) - b` of the two branches, so it follows `U` and the panel stock both
    # and prints as a band; the panelled end bulkhead's table came to 158.6 mm against a
    # 108.5 mm band. The offset is the same face located from the axis instead of measured
    # across, and where the bore branch wins it is a function of `U` alone.
    dimensions.append(
        (by_name['corner_seat_offset'], (axis, axis, 0.0), (axis - seat_offset, axis, 0.0),
         dp.HORIZONTAL, seat_offset))

    def on_circle(center, r, degrees):
        angle = math.radians(degrees)
        return (center[0] + r * math.cos(angle), center[1] + r * math.sin(angle), 0.0)

    notes = [
        ('bore', on_circle((axis, axis), bore, 115.0),
         ('%s%s BORE' % (DIA, w('bore_diameter')),
          'FOR %s%s LONGERON' % (DIA, w('longeron_diameter')),
          '%s DIA CLEARANCE' % w('longeron_clearance'))),
        ('post', on_circle((axis, axis), nub_radius, 45.0),
         ('%s%s POST, %s%s NUB' % (DIA, w('post_diameter'), DIA, w('nub_diameter')),
          'NOMINAL -- CORNER SOCKET',
          'CARRIES THE CLEARANCE')),
        ('bolt', on_circle((bolt_axis, bolt_axis), boss_radius, 225.0),
         ('%s%s HOLE IN %s%s BOSS' % (DIA, w('bolt_diameter'), DIA, w('boss_diameter')),
          '%s FROM LONGERON AXIS' % w('bolt_offset'),
          'EACH AXIS, 4 PLACES')),
    ]
    notes.append(
        ('corner_seat', (axis - seat_offset * 0.7, axis + seat_offset * 0.7, 0.0),
         ('%s CORNER SEAT' % w('corner_seat_offset'),
          'CLEARS BORE AND LEAD-IN' if seated else 'SET BY PANEL ENTRY')))
    if panelled:
        notes.append(
            ('seat', (axis, seat, 0.0),
             ('%s POCKET FROM MOLD LINE' % w('panel_pocket'),
              'FOR %s PANEL' % w('panel_thickness'),
              '%s CLEARANCE' % w('panel_tolerance'))))

    construction = bulkhead_construction(params, half, axis, bolt_axis, bore, boss_radius,
                                         seat, thickness, panelled)
    views = bulkhead_views(params, half, axis, bolt_axis, boss_radius, nub_radius, panelled)
    return quantities, dimensions, notes, construction, views


def detail_radius(axis, bolt_axis, boss_radius, nub_radius, corner_radius):
    """How much of the plate the corner detail takes in, in model millimeters.

    Everything the detail is for, and a margin. The furthest of them from the longeron axis
    sets it: the mold line is `corner_radius` out, the bolt boss reaches
    `(axis - bolt_axis) * sqrt(2) + boss_radius` along the diagonal, and the greeble nub is
    `nub_radius`. A quarter more so the boundary stands clear of the features rather than
    cutting the outermost one in half.
    """
    bolt_reach = abs(axis - bolt_axis) * (2.0 ** 0.5) + boss_radius
    return DETAIL_MARGIN * max(corner_radius, bolt_reach, nub_radius)


def bulkhead_views(params, half, axis, bolt_axis, boss_radius, nub_radius, panelled):
    """The bulkhead's plan and its corner detail, and what each carries.

    **The split is by what a dimension is about, not by what fits.** Two quantities are about
    the plate -- the mold line half-width and where the longeron axis sits in it -- and they
    span it; magnified they would say nothing. Everything else is about one corner: the bolt
    in its boss, the greeble post and nub, the corner seat, the panel pocket. Those are
    within a few millimetres of one axis on a plate up to 200 mm across, and on the plan they
    are illegible whatever the layout does with them.

    One detail, not four, because the plate is symmetric about both axes and both diagonals --
    measured, see `bulkhead_construction` -- so the other three corners are the same corner
    and the centre lines on the plan say so.
    """
    radius = detail_radius(axis, bolt_axis, boss_radius, nub_radius, half - axis)
    detail_dimensions = ['bolt_offset', 'corner_seat_offset']
    detail_notes = ['bore', 'post', 'bolt', 'corner_seat']
    if panelled:
        detail_dimensions.append('panel_pocket')
        detail_notes.append('seat')
    return [
        SheetView('PLAN', dimensions=('mold_half_width', 'longeron_offset')),
        SheetView('DETAIL A', clip=(axis, axis, radius),
                  dimensions=detail_dimensions, notes=detail_notes,
                  caption='DETAIL A -- CORNER, 4 PLACES'),
    ]


def bulkhead_construction(params, half, axis, bolt_axis, bore, boss_radius, seat, thickness,
                          panelled):
    """The bulkhead's centre marks, its four symmetry axes, and the panels it seats.

    **Four centre lines, because the plate has four mirrors and every dimension on the sheet
    relies on it.** Measured 2026-09-07 by reflecting the built solid and intersecting it with
    itself: `x = 0`, `y = 0`, `y = x` and `y = -x` each recover 1.000000 of the volume, at two
    variants. That is full D4, and it is what makes one bolt dimension state four bolts. Until
    the axes are drawn the sheet has not said so, and a reader looking at `bolt_offset` beside
    one hole cannot tell a stated position from an omitted one.

    The two diagonals do double duty: `y = x` runs through the longeron axis at `(axis, axis)`
    **and** the bolt axis at `(bolt_axis, bolt_axis)`, because the part places the bolt along
    the diagonal from the longeron. So the same line is the symmetry axis and the hole
    pattern's centre line, which is the relationship `bolt_offset` is measured along.

    **Centre marks on the eight located axes and nothing else** -- four longeron bores and
    four bolt bosses. Every other arc on this part is a fillet, a lead-in or a nub blend.

    **The panels are drawn because otherwise the pocket has nothing to be a pocket for.** Each
    of the four sides seats one. Its **outer surface is the mold line** at `unit_width/2` --
    the panel skins the airframe -- and its inner surface one `panel_thickness` in, which
    leaves `panel_tolerance` between it and the seating face at
    `unit_width/2 - panel_thickness - panel_tolerance`. The fit is the gap behind the panel,
    not in front of it.

    It runs from one longeron axis to the other, less `panel_offset` at each end:
    `corner_tree`'s slot reaches `slot_x + slot_w`, which is `-panel_offset + panel_tolerance`
    in the corner's frame, so the panel's own end is at `-panel_offset` and the remaining
    tolerance is the fit at that face too.
    """
    root_half = 0.5 ** 0.5

    construction = center_marks(
        [(sx * axis, sy * axis) for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)], bore)
    construction += center_marks(
        [(sx * bolt_axis, sy * bolt_axis) for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)],
        boss_radius)

    construction += [
        axis_line((1.0, 0.0), half),
        axis_line((0.0, 1.0), half),
        # The diagonals reach the plate's own corners, which are a half-diagonal out.
        axis_line((root_half, root_half), half * (2.0 ** 0.5)),
        axis_line((-root_half, root_half), half * (2.0 ** 0.5)),
    ]

    # **The corner, at all four longeron axes.** Section 2's joints 2, 3 and 4 are all
    # corner-to-bulkhead, and until now the bulkhead's sheet showed none of the other side of
    # any of them: `corner_seat_offset` located a face against nothing, and a reader had no way
    # to see what the seat seats. Sectioned at the middle of the plate, which is where the two
    # parts actually overlap -- the corner's end section runs the plate's own thickness.
    #
    # The four placements are the plate's own symmetry: the corner sits at `(axis, axis)` with
    # its local axes pointing outboard, and the other three are its mirrors in `x` and `y`.
    construction.append(
        (REFERENCE_PART, 'corner', params['bulkhead_thickness'] / 2.0,
         tuple((sx, sy, axis, axis) for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)),
         'CORNER'))

    if panelled:
        end = axis - params['panel_offset']
        inner = half - thickness
        for sign in (-1.0, 1.0):
            # The two panels normal to Y, then the two normal to X.
            construction.append(
                (REFERENCE,
                 rectangle(-end, sign * inner, end, sign * half), True, 'PANEL'))
            construction.append(
                (REFERENCE,
                 rectangle(sign * inner, -end, sign * half, end), True, 'PANEL'))
    return construction


# The kinds that have an annotation set. Read from both sides of the boundary: `drawing.py`
# uses it to draw a sheet and `tools/drawing_families.py` to tabulate one, which is the whole
# reason this module exists apart from `drawing.py`.
ANNOTATIONS = {'corner': corner_annotations, 'bulkhead': bulkhead_annotations}


def quantities_for(kind, params):
    """Just the quantities, for a caller that is tabulating rather than drawing."""
    return ANNOTATIONS[kind](params)[0]

