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
        Quantity('socket_diameter', 2.0 * socket,
                 ('longeron_radius', 'longeron_tolerance', 'greeble_tolerance')),
        Quantity('post_diameter', 2.0 * post, ('longeron_radius', 'longeron_tolerance')),
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

    dimensions = []
    if panelled:
        # The pocket the panel seats in, which is the one interface on this part that *is* a
        # distance between two real parallel faces.
        dimensions.append(
            (by_name['panel_pocket'], (0.0, seat, 0.0), (0.0, radius, 0.0),
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
            ('pocket', (0.0, seat, 0.0),
             ('%s POCKET' % w('panel_pocket'),
              'FOR %s PANEL' % w('panel_thickness'),
              '%s CLEARANCE' % w('panel_tolerance'))))
    return quantities, dimensions, notes


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
        Quantity('mold_half_width', half, ()),
        Quantity('longeron_offset', axis, ('corner_radius',)),
        Quantity('bore_diameter', 2.0 * bore, ('longeron_radius', 'longeron_tolerance')),
        Quantity('longeron_diameter', 2.0 * longeron, ('longeron_radius',)),
        Quantity('longeron_clearance', 2.0 * longeron_fit, ('longeron_tolerance',),
                 constant=True),
        Quantity('post_diameter', 2.0 * post, ('longeron_radius', 'longeron_tolerance')),
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
        dimensions.append(
            (by_name['panel_pocket'], (0.0, seat, 0.0), (0.0, half, 0.0),
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
            ('seat', (0.0, seat, 0.0),
             ('%s POCKET FROM MOLD LINE' % w('panel_pocket'),
              'FOR %s PANEL' % w('panel_thickness'),
              '%s CLEARANCE' % w('panel_tolerance'))))
    return quantities, dimensions, notes


# The kinds that have an annotation set. Read from both sides of the boundary: `drawing.py`
# uses it to draw a sheet and `tools/drawing_families.py` to tabulate one, which is the whole
# reason this module exists apart from `drawing.py`.
ANNOTATIONS = {'corner': corner_annotations, 'bulkhead': bulkhead_annotations}


def quantities_for(kind, params):
    """Just the quantities, for a caller that is tabulating rather than drawing."""
    return ANNOTATIONS[kind](params)[0]

