"""OQ-DES-D2's alternatives, drawn on the same geometry so they can be compared.

The question is what a part drawing carries. Every candidate answer annotates the *same*
outline differently, so describing them in prose compares nothing -- the difference between
them is entirely in what a reader can see. This draws each scheme on the corner's mid-bay
section, traced from the solid by `dimension_alternatives/measure_sections.py`, and scores
each against the things a drawing user actually came to find out.

    uv run python src/Fuselage/tools/draw_dimension_alternatives.py out.html

**The drawing user is an integrator, not an inspector.** That is the premise the schemes are
judged on and it is not this file's to invent: the questions in `QUESTIONS` below are the ones
asked of this drawing set on 2026-08-22 -- what size longerons and to what tolerance, what
size panels and to what tolerance, what size bolts and anchors, how big the structural cell's
interior aperture is, and how much volume each part uses, which is mass.

**Nothing here computes geometry.** The outline is traced from a built solid and the numbers
come from the exported parameter set, for the reason `draw_corner_joint.py` gives about its
own snapshot: a drawing that evaluates the design equations cannot disagree with them, and
disagreeing with them is the whole value of drawing the part.

Values are millimeters, as the OpenSCAD path uses them.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'dimension_alternatives', 'sections.json')

# What the drawing user came to find out, and what a scheme has to do about it.
#
# **Two of the five questions are not on this list, and that is the finding rather than an
# omission.** The interior aperture of the structural cell and the volume of a part are not
# distances between features of a joint -- the aperture is a hole nothing mates with, and
# volume is a property of a solid. No dimensioning scheme answers either, because neither is a
# dimension. They are handled in their own section of the page, and what they need is not a
# choice between the schemes below but a widening of section 1's membership test.
#
# The rows that remain are the ones the schemes genuinely differ on: three of them ask whether
# the drawing user learns the hardware, and the last two are what that costs.
QUESTIONS = [
    ('longeron', 'What size longeron, and what clearance on it?'),
    ('panel', 'What size panel, and what clearance on it?'),
    ('fastener', 'What size bolts and anchors?'),
    ('built', 'Is the feature as built also given, so a part can be checked?'),
    ('space', 'What does it cost off the view?'),
]

YES, NO, PART, FREE, COST = 'yes', 'no', 'part', 'free', 'cost'

SCORES = {
    # Feature dimensions alone. R2.05 and a 4.86 pocket are true and inspectable, and there is
    # no way to get from either to the hardware: the clearance is not on the sheet, so the
    # nominal cannot be recovered by arithmetic or by anything else.
    'A': {'longeron': NO, 'panel': NO, 'fastener': NO, 'built': YES, 'space': FREE},
    # Nominals to reference geometry. Every hardware size is stated and nothing dimensioned
    # exists: a caliper on the bore reads 4.10 against a drawing that says 4.00.
    'B': {'longeron': YES, 'panel': YES, 'fastener': YES, 'built': NO, 'space': FREE},
    # Feature dimension plus a callout naming the hardware. Both readings, on the view.
    'C': {'longeron': YES, 'panel': YES, 'fastener': YES, 'built': YES, 'space': FREE},
    # The same, with the hardware moved into a schedule. Costs table rows -- which five of the
    # thirteen family sheets do not have, measuring 19 of 19 already.
    'D': {'longeron': YES, 'panel': YES, 'fastener': YES, 'built': YES, 'space': COST},
}

MARKS = {
    YES: ('yes', 'states it'),
    NO: ('no', 'absent'),
    PART: ('arith', 'by arithmetic'),
    FREE: ('yes', 'nothing'),
    COST: ('arith', 'a table'),
}


# --------------------------------------------------------------------------------------
# The drawing vocabulary
# --------------------------------------------------------------------------------------
# Taken from `draw_corner_joint.py` rather than chosen again, so a reader who has seen one of
# this project's drawings can read this one: green is the mold line, purple is geometry that
# is referenced but not present, teal is a mating part, red is a dimension.

class View:
    """A window on the section, in millimeters, rendered at a fixed pixel width."""

    def __init__(self, x0, y0, x1, y1, px=420):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.px = px
        self.k = px / float(x1 - x0)
        self.py = (y1 - y0) * self.k

    def p(self, x, y):
        return ((x - self.x0) * self.k, (self.y1 - y) * self.k)

    def mm(self, value):
        return value * self.k


def path(view, points, close=True):
    out = []
    for index, (x, y) in enumerate(points):
        px, py = view.p(x, y)
        out.append('%s%.2f %.2f' % ('M' if index == 0 else 'L', px, py))
    return ' '.join(out) + (' Z' if close else '')


def poly(view, points, cls, close=True):
    return '<path class="%s" d="%s"/>' % (cls, path(view, points, close))


def line(view, x1, y1, x2, y2, cls):
    a, b = view.p(x1, y1), view.p(x2, y2)
    return ('<line class="%s" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            % (cls, a[0], a[1], b[0], b[1]))


def circle(view, cx, cy, r, cls):
    a = view.p(cx, cy)
    return ('<circle class="%s" cx="%.2f" cy="%.2f" r="%.2f"/>'
            % (cls, a[0], a[1], view.mm(r)))


def text(view, x, y, body, cls='lbl', dx=0, dy=0, anchor='start'):
    px, py = view.p(x, y)
    return ('<text class="%s" x="%.1f" y="%.1f" text-anchor="%s">%s</text>'
            % (cls, px + dx, py + dy, anchor, body))


def arrow(view, x, y, angle, cls='dim'):
    """A filled arrowhead at a model point, pointing along `angle` degrees."""
    import math

    px, py = view.p(x, y)
    radians = math.radians(angle)
    length, half = 7.0, 2.2
    tip = (px, py)
    back = (px - length * math.cos(radians), py + length * math.sin(radians))
    left = (back[0] - half * math.sin(radians), back[1] - half * math.cos(radians))
    right = (back[0] + half * math.sin(radians), back[1] + half * math.cos(radians))
    return ('<polygon class="dimhead" points="%.2f,%.2f %.2f,%.2f %.2f,%.2f"/>'
            % (tip[0], tip[1], left[0], left[1], right[0], right[1]))


def hdim(view, x1, x2, y, label, cls='dim', dy=-10):
    """A horizontal dimension between two x positions, offset from `y`."""
    a, b = view.p(x1, y), view.p(x2, y)
    out = ['<g>',
           '<line class="dimline" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
           % (a[0], a[1] + dy, b[0], b[1] + dy),
           '<line class="dimwit" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
           % (a[0], a[1], a[0], a[1] + dy - 3),
           '<line class="dimwit" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
           % (b[0], b[1], b[0], b[1] + dy - 3),
           '<text class="dimtext" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
           % ((a[0] + b[0]) / 2.0, a[1] + dy - 7, label),
           '</g>']
    return '\n'.join(out)


def vdim(view, y1, y2, x, label, cls='dim', dx=12):
    """A vertical dimension between two y positions, offset from `x`."""
    a, b = view.p(x, y1), view.p(x, y2)
    mid = (a[1] + b[1]) / 2.0
    out = ['<g>',
           '<line class="dimline" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
           % (a[0] + dx, a[1], b[0] + dx, b[1]),
           '<line class="dimwit" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
           % (a[0], a[1], a[0] + dx - 4, a[1]),
           '<line class="dimwit" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
           % (b[0], b[1], b[0] + dx - 4, b[1]),
           '<text class="dimtext" x="%.1f" y="%.1f" text-anchor="middle" '
           'transform="rotate(-90 %.1f %.1f)">%s</text>'
           % (a[0] + dx - 6, mid, a[0] + dx - 6, mid, label),
           '</g>']
    return '\n'.join(out)


def leader(view, x, y, tx, ty, lines, side='right', cls='dim'):
    """A leader from a point on the geometry to a shelf carrying a stack of text.

    `side` is stated rather than inferred from whether the shelf is left or right of the
    anchor: a note placed left of the geometry it points at still reads left to right, and
    inferring the anchor from the geometry put three of the four schemes' notes off the sheet.

    `fill="none"` is a presentation attribute rather than a rule in the stylesheet because the
    stylesheet is not always there -- these fragments are extracted and rasterized on their
    own to check them, and a leader that fills solid black when the CSS is missing hides the
    thing it points at.
    """
    import math

    a, b = view.p(x, y), view.p(tx, ty)
    shelf = 15.0 if side == 'right' else -15.0
    anchor = 'start' if side == 'right' else 'end'
    angle = math.degrees(math.atan2(b[1] - a[1], a[0] - b[0]))

    out = ['<g>',
           '<polyline class="ldr" fill="none" points="%.2f,%.2f %.2f,%.2f %.2f,%.2f"/>'
           % (a[0], a[1], b[0], b[1], b[0] + shelf, b[1]),
           arrow(view, x, y, angle, cls)]
    for index, body in enumerate(lines):
        out.append('<text class="%s" x="%.1f" y="%.1f" text-anchor="%s">%s</text>'
                   % ('dimnote' if index else 'dimtext', b[0] + shelf,
                      b[1] - 3 + index * 12, anchor, body))
    out.append('</g>')
    return chr(10).join(out)


def tag(view, x, y, mark):
    """A circled reference mark, keying a feature to a row in the interface schedule."""
    px, py = view.p(x, y)
    return ('<g><circle class="tagring" fill="none" cx="%.2f" cy="%.2f" r="8.5"/>'
            '<text class="tagtext" x="%.2f" y="%.2f" text-anchor="middle">%s</text></g>'
            % (px, py, px, py + 3.5, mark))


def svg(view, body, label):
    return ('<svg viewBox="0 0 %.1f %.1f" role="img" aria-label="%s" '
            'preserveAspectRatio="xMidYMid meet">%s</svg>'
            % (view.px, view.py, label, body))


# --------------------------------------------------------------------------------------
# The four schemes, each on the same outline
# --------------------------------------------------------------------------------------
# All four annotate the same two joints -- the longeron bore and the panel pocket -- because
# those are the two the drawing user's first two questions are about and both are visible in
# one section. The flats and the bay length are left undimensioned here; this is a comparison
# of schemes, not a complete sheet, and a complete sheet would bury the difference.

def base(view, outline, params):
    """Everything every scheme draws: the section, the mold line, the axes."""
    radius = params['corner_radius']
    return [
        poly(view, outline, 'body'),
        # The mold line is the fuselage's outer surface and the datum every panel dimension is
        # taken to, so it is drawn as itself in every scheme rather than left to be inferred
        # from the outline it happens to coincide with.
        '<path class="oml" fill="none" d="%s"/>'
        % arc_path(view, 0.0, 0.0, radius, 0.0, 90.0),
        line(view, -9.6, 0, 11.6, 0, 'axis'),
        line(view, 0, -9.6, 0, 11.6, 'axis'),
    ]


def arc_path(view, cx, cy, r, a0, a1, steps=64):
    import math

    points = []
    for index in range(steps + 1):
        angle = math.radians(a0 + (a1 - a0) * index / float(steps))
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return path(view, points, close=False)


def bore_point(params):
    """A point on the bore arc, on the lower-left side where the leader has room."""
    import math

    r = params['longeron_radius'] + params['longeron_tolerance']
    angle = math.radians(255.0)
    return (r * math.cos(angle), r * math.sin(angle))


def mold_point(params):
    import math

    r = params['corner_radius']
    return (r * math.cos(math.radians(52.0)), r * math.sin(math.radians(52.0)))


def scheme_a(view, outline, params, geometry):
    """Feature dimensions only -- every number is one a caliper can reach."""
    bore = params['longeron_radius'] + params['longeron_tolerance']
    seat = geometry['seat_y']
    bx, by = bore_point(params)
    mx, my = mold_point(params)
    body = base(view, outline, params)
    body += [
        leader(view, bx, by, -13.0, -8.4, ['R%.2f' % bore], 'right'),
        leader(view, mx, my, 13.0, 10.4, ['R%.2f' % params['corner_radius']], 'right'),
        vdim(view, seat, params['corner_radius'], -2.4,
             '%.2f' % (params['corner_radius'] - seat), dx=-32),
    ]
    return svg(view, chr(10).join(body), 'scheme A, feature dimensions only')


def scheme_b(view, outline, params, geometry):
    """Nominal dimensions, taken to the mating parts drawn as reference geometry."""
    import math

    nominal = params['longeron_radius']
    thickness = params['panel_thickness']
    radius = params['corner_radius']
    seat = geometry['seat_y']
    angle = math.radians(255.0)
    body = base(view, outline, params)
    body += [
        circle(view, 0, 0, nominal, 'mate'),
        # The panel, drawn where it lands: its outer face on the mold line, its inner face on
        # the seat, running out of the pocket to the left.
        poly(view, [(-2.4, seat + params['panel_tolerance']),
                    (-13.5, seat + params['panel_tolerance']),
                    (-13.5, radius), (-2.4, radius)], 'mate', close=True),
        leader(view, nominal * math.cos(angle), nominal * math.sin(angle),
               -13.0, -8.4, ['%s%.2f' % (DIA, 2 * nominal), 'LONGERON TUBE'], 'right'),
        leader(view, mx_of(radius), my_of(radius), 13.0, 10.4,
               ['R%.2f' % radius], 'right'),
        vdim(view, seat + params['panel_tolerance'], radius, -10.4,
             '%.4f' % thickness, dx=-30),
        text(view, -13.4, seat - 0.4, 'PANEL', 'mlbl', dx=0, dy=13),
    ]
    return svg(view, chr(10).join(body),
               'scheme B, nominal dimensions to reference geometry')


def mx_of(r):
    import math

    return r * math.cos(math.radians(52.0))


def my_of(r):
    import math

    return r * math.sin(math.radians(52.0))


def scheme_c(view, outline, params, geometry):
    """Feature dimensions, each carrying a callout naming the hardware it is cut for."""
    bore = params['longeron_radius'] + params['longeron_tolerance']
    seat = geometry['seat_y']
    pocket = params['corner_radius'] - seat
    bx, by = bore_point(params)
    mx, my = mold_point(params)
    body = base(view, outline, params)
    body += [
        leader(view, bx, by, -13.0, -8.4,
               ['%s%.2f BORE' % (DIA, 2 * bore),
                'FOR %s%.2f LONGERON' % (DIA, 2 * params['longeron_radius']),
                '%.2f DIA CLEARANCE' % (2 * params['longeron_tolerance'])], 'right'),
        leader(view, mx, my, 13.0, 11.0,
               ['R%.2f' % params['corner_radius'], 'MOLD LINE'], 'right'),
        vdim(view, seat, params['corner_radius'], -2.4, '%.2f' % pocket, dx=-32),
        leader(view, -6.0, seat, 1.0, 13.0,
               ['%.2f POCKET' % pocket,
                'FOR %.4f PANEL' % params['panel_thickness'],
                '%.2f CLEARANCE' % params['panel_tolerance']], 'right'),
    ]
    return svg(view, chr(10).join(body),
               'scheme C, feature dimensions with hardware callouts')


def scheme_d(view, outline, params, geometry):
    """Feature dimensions, tagged, with the hardware moved into a schedule beside the view."""
    bore = params['longeron_radius'] + params['longeron_tolerance']
    seat = geometry['seat_y']
    bx, by = bore_point(params)
    mx, my = mold_point(params)
    # A point on the diagonal seating face. Its own midpoint, at half `flat_offset` in
    # both axes, is 1.87 mm from the corner axis -- inside the 2.05 mm bore, so it lies in the
    # void the bore opens onto rather than on any face at all. The face survives as two
    # segments either side of that opening; this is the middle of the lower one, which runs
    # from (0, flat_offset) to (flat_offset - flat_x, flat_x).
    seat_x = (geometry['flat_offset'] - geometry['flat_x']) / 2.0
    seat_y = (geometry['flat_offset'] + geometry['flat_x']) / 2.0
    body = base(view, outline, params)
    body += [
        leader(view, bx, by, -13.0, -8.4, ['R%.2f' % bore], 'right'),
        tag(view, -14.6, -8.5, '1'),
        vdim(view, seat, params['corner_radius'], -2.4,
             '%.2f' % (params['corner_radius'] - seat), dx=-32),
        tag(view, -9.4, 7.6, '2'),
        leader(view, seat_x, seat_y, 13.0, -10.0, ['SEAT'], 'right'),
        tag(view, 17.8, -10.1, '3'),
        leader(view, mx, my, 13.0, 10.4, ['R%.2f' % params['corner_radius']], 'right'),
    ]
    return svg(view, chr(10).join(body),
               'scheme D, tagged features with an interface schedule')


def bulkhead_panel(section, params, bulkhead):
    """The bulkhead in section, showing what OQ-DES-D3 is about.

    Two annotations on one view, and the difference between them is the whole question. The
    bolt hole is a joint: something mates with it, so the rule that picks dimensions can see
    it, and it gets the callout OQ-DES-D2 decided on. The aperture is not a joint -- nothing in
    the model mates with the hole through the middle -- so the same rule says do not dimension
    it, and it is drawn here in the reference colour to show what would be missing.
    """
    outer = [tuple(q) for q in section['loops'][0]['points']]
    aperture = [tuple(q) for q in section['loops'][1]['points']]
    holes = [loop for loop in section['loops'][2:] if loop['area_mm2'] > 1.0]

    half = params['unit_width'] / 2.0 if 'unit_width' in params else 50.0
    view = View(-half - 22.0, -half - 21.0, half + 24.0, half + 15.0, px=560)

    span = section['loops'][1]['bbox'][0]
    top = max(y for _x, y in aperture)

    # One path with every loop in it and `fill-rule: evenodd`, so the openings read as
    # openings. Filling the outer profile alone and drawing the aperture on top of it as an
    # outline shows a solid slab with a line on it, which is the opposite of what the section
    # is about.
    subpaths = [path(view, outer)] + [path(view, aperture)]
    subpaths += [path(view, [tuple(q) for q in hole['points']]) for hole in holes]

    body = [
        '<path class="body" fill-rule="evenodd" d="%s"/>' % ' '.join(subpaths),
        poly(view, aperture, 'mate'),
        line(view, -half - 6.0, 0, half + 6.0, 0, 'axis'),
        line(view, 0, -half - 6.0, 0, half + 6.0, 'axis'),
        hdim(view, -span / 2.0, span / 2.0, top, '%.2f' % span, dy=-24),
        text(view, 0, top, 'CLEAR OPENING', 'dimnote', dy=-38, anchor='middle'),
    ]

    if holes:
        # The lower-left hole, which is the one with empty sheet beneath it to put a note on.
        hole = min(holes, key=lambda h: (min(q[0] for q in h['points'])
                                         + min(q[1] for q in h['points'])))
        cx = hole['bbox'][0] / 2.0 + min(q[0] for q in hole['points'])
        cy = hole['bbox'][1] / 2.0 + min(q[1] for q in hole['points'])
        radius = bulkhead['bolt_hole_radius']
        body.append(leader(view, cx - radius * 0.7, cy - radius * 0.7,
                           -half + 6.0, -half - 6.0,
                           ['%s%.2f' % (DIA, 2 * radius), 'FOR M4 BOLT',
                            'NO CLEARANCE'], 'right'))
    return svg(view, chr(10).join(body),
               'the bulkhead in section, with its aperture and a bolt hole')


def panel_panel(section, params, bulkhead):
    """The panel's allocation, drawn on the bulkhead section.

    The bulkhead is the full cross-section, so it is the one view that can carry a panel
    dimension: its outer profile *is* the panel's inner face, and the corner's panel extensions
    show on it as real features. The panel itself is reference geometry -- there is no panel
    part in the sweep, only a thickness -- and its envelope is drawn from the expressions §2's
    register carries, every one of which the corner confirms.
    """
    outer = [tuple(q) for q in section['loops'][0]['points']]
    aperture = [tuple(q) for q in section['loops'][1]['points']]
    holes = [loop for loop in section['loops'][2:] if loop['area_mm2'] > 1.0]

    unit_width = bulkhead['unit_width']
    half = unit_width / 2.0
    inner = half - bulkhead['panel_thickness'] - bulkhead['panel_tolerance']
    width = unit_width - 2.0 * (bulkhead['corner_radius'] + bulkhead['panel_offset'])
    exposed = width - 2.0 * bulkhead['panel_overlap']

    view = View(-half - 44.0, -half - 22.0, half + 46.0, half + 34.0, px=620)

    subpaths = [path(view, outer), path(view, aperture)]
    subpaths += [path(view, [tuple(q) for q in hole['points']]) for hole in holes]

    body = [
        '<path class="body" fill-rule="evenodd" d="%s"/>' % ' '.join(subpaths),
        # The mold line, which the bulkhead does not reach -- the panel's outer face lands on
        # it, so it is the datum the whole allocation is measured to.
        line(view, -width / 2.0 - 6.0, half, width / 2.0 + 6.0, half, 'oml'),
        # The panel, in its allocation.
        poly(view, [(-width / 2.0, inner), (width / 2.0, inner),
                    (width / 2.0, half), (-width / 2.0, half)], 'mate'),
        line(view, -exposed / 2.0, inner, -exposed / 2.0, half, 'mate'),
        line(view, exposed / 2.0, inner, exposed / 2.0, half, 'mate'),
        line(view, 0, -half - 8.0, 0, half + 12.0, 'axis'),
        hdim(view, -width / 2.0, width / 2.0, half, '%.3f' % width, dy=-40),
        hdim(view, -exposed / 2.0, exposed / 2.0, half, '%.3f' % exposed, dy=-20),
        text(view, 0, half, 'PANEL ALLOCATION', 'mlbl', dy=-62, anchor='middle'),
        leader(view, width / 2.0 - 2.0, (inner + half) / 2.0, half + 6.0, half - 12.0,
               ['%.4f PANEL' % bulkhead['panel_thickness'],
                'IN A %.4f POCKET' % (bulkhead['panel_thickness']
                                      + bulkhead['panel_tolerance']),
                'ON THE MOLD LINE'], 'right'),
        leader(view, exposed / 2.0 + bulkhead['panel_overlap'] / 2.0, inner,
               half + 6.0, -half + 4.0,
               ['%.4f' % bulkhead['panel_overlap'],
                'INTO EACH CORNER'], 'right'),
    ]
    return svg(view, chr(10).join(body),
               "the panel's allocation, drawn on the bulkhead section")


def assembly_panel(sections, params, bulkhead):
    """The assembly view: the panel and the corner projected onto the bulkhead top view.

    Required 2026-08-22, and the bulkhead top view is the carrier because it is the one view
    where all three parts share a plane rather than being constructed onto it. The bulkhead's
    outer flat face is the panel's seating surface; the corner's panel extension ends at
    32.7375 from the airframe axis and the bulkhead carries a face there too.

    The corner is projected by placing its traced mid-bay section at the corner's own origin in
    the airframe frame, `(unit_width/2 - corner_radius)` in both axes, and mirroring it into
    the other three quadrants. That is where the corner is, so the projection is a transform of
    measured geometry rather than a redrawing of it.
    """
    section = sections['bulkhead']
    outer = [tuple(q) for q in section['loops'][0]['points']]
    aperture = [tuple(q) for q in section['loops'][1]['points']]
    holes = [loop for loop in section['loops'][2:] if loop['area_mm2'] > 1.0]
    corner_profile = [tuple(q) for q in sections['corner']['loops'][0]['points']]

    unit_width = bulkhead['unit_width']
    half = unit_width / 2.0
    origin = half - bulkhead['corner_radius']
    inner = half - bulkhead['panel_thickness'] - bulkhead['panel_tolerance']
    width = unit_width - 2.0 * (bulkhead['corner_radius'] + bulkhead['panel_offset'])
    extension = origin - (bulkhead['panel_overlap'] + bulkhead['panel_offset'])
    # Half of `flat_offset`: the midpoint of the corner's diagonal seating plane, in the
    # corner's own frame. Negative, so the corner's origin plus it moves inboard.
    seat_diag = -max(params['longeron_radius'] + params['longeron_tolerance']
                     + params['extrusion_width'],
                     (params['panel_overlap'] + params['panel_offset'])
                     - (params['corner_radius'] - params['panel_thickness']
                        - params['panel_tolerance'])) / 2.0

    view = View(-half - 62.0, -half - 30.0, half + 62.0, half + 40.0, px=680)

    subpaths = [path(view, outer), path(view, aperture)]
    subpaths += [path(view, [tuple(q) for q in hole['points']]) for hole in holes]

    body = ['<path class="body" fill-rule="evenodd" d="%s"/>' % ' '.join(subpaths)]

    # The four corners, each the same traced profile reflected into its quadrant.
    for sx in (1.0, -1.0):
        for sy in (1.0, -1.0):
            placed = [(sx * (x + origin), sy * (y + origin)) for x, y in corner_profile]
            body.append(poly(view, placed, 'proj'))

    # The mold line on the two faces the dimensions are taken on.
    body.append(line(view, -half, half, half, half, 'oml'))
    body.append(line(view, -half, -half, half, -half, 'oml'))

    # The panel, projected into its allocation on the upper face.
    body.append(poly(view, [(-width / 2.0, inner), (width / 2.0, inner),
                            (width / 2.0, half), (-width / 2.0, half)], 'mate'))

    body += [
        line(view, 0, -half - 16.0, 0, half + 22.0, 'axis'),
        hdim(view, -width / 2.0, width / 2.0, half, '%.3f PANEL WIDTH' % width, dy=-34),
        vdim(view, inner, half, width / 2.0, '%.4f' % bulkhead['panel_thickness'], dx=40),
        text(view, width / 2.0, (inner + half) / 2.0, 'PANEL THK', 'mlbl', dx=52, dy=-6),
        leader(view, -width / 2.0 + 4.0, inner, -half - 6.0, -half + 30.0,
               ['PANEL TOLERANCE %.2f' % bulkhead['panel_tolerance'],
                'ON EACH PANEL FACE'], 'left'),
        # `corner_tolerance` comes from the corner's table, not the bulkhead's, and that is
        # not a lookup convenience: §2 says the corner carries the whole of this clearance and
        # the bulkhead passes 0, so the bulkhead's table does not contain the name at all. An
        # assembly drawing needs both parts' parameters, which is what makes it an assembly
        # drawing rather than two part drawings on one sheet.
        # Pointed at the corner's diagonal seating face, which is the face this clearance
        # is carried on -- x + y = flat_offset in the corner's own frame, on the near side of
        # the lower-left corner.
        leader(view, -(origin + seat_diag), -(origin + seat_diag),
               -half - 6.0, -half + 4.0,
               ['CORNER TOLERANCE %.2f' % params['corner_tolerance'],
                'ON THE DIAGONAL SEAT'], 'left'),
        text(view, 0, half, 'PANEL AND CORNER PROJECTED ON THE BULKHEAD', 'mlbl',
             dy=-52, anchor='middle'),
    ]
    return svg(view, chr(10).join(body),
               'assembly view: panel and corner projected onto the bulkhead top view')


DIA = '&#216;'

SCHEMES = [
    ('A', 'Feature dimensions only', scheme_a,
     'Every number is one a caliper reaches on the printed part. Nothing states what the '
     'features are cut <em>for</em>: the bore is R2.05 because a 4.00 mm longeron needs '
     '0.10 mm of diametral clearance, and neither of those numbers appears.'),
    ('B', 'Nominals, to the mating parts as reference geometry', scheme_b,
     'The longeron and the panel are drawn in as reference geometry and the dimensions are '
     'taken to <em>them</em>. Every hardware size is stated outright — and nothing '
     'dimensioned is on the part, so a caliper on the bore reads 4.10 against a drawing '
     'that says 4.00.'),
    ('C', 'Feature dimensions with hardware callouts', scheme_c,
     'The dimension is the feature as built; the callout beside it names the hardware and '
     'the clearance. One line carries both readings, and the two numbers cannot drift apart '
     'because the callout is generated from the same expression the feature is.'),
    ('D', 'Tagged features with an interface schedule', scheme_d,
     'The view carries feature dimensions with reference tags; the hardware, the clearance '
     'and the joint each tag belongs to move into a table beside it. The table has room for '
     'the two things no annotation on a view can carry — the cell aperture and the part '
     'volume.'),
]


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------

def schedule_rows(params):
    bore = params['longeron_radius'] + params['longeron_tolerance']
    seat = params['corner_radius'] - params['panel_thickness'] - params['panel_tolerance']
    return [
        ('1', 'longeron tube &rarr; corner bore',
         '%s%.2f tube' % (DIA, 2 * params['longeron_radius']),
         '%.2f dia' % (2 * params['longeron_tolerance']),
         '%s%.2f bore' % (DIA, 2 * bore)),
        ('2', 'panel &rarr; corner pocket',
         '%.4f sheet' % params['panel_thickness'],
         '%.2f' % params['panel_tolerance'],
         '%.4f pocket' % (params['corner_radius'] - seat)),
        ('3', 'corner seating faces &rarr; bulkhead',
         'bulkhead flat', '%.2f' % params['corner_tolerance'],
         '%.4f from axis' % 7.2625),
    ]


def build(data, out_path, template_path=None):
    params = data['corner_parameters']
    bulkhead = data['bulkhead_parameters']
    sections = data['sections']
    outline = [tuple(p) for p in sections['corner']['loops'][0]['points']]
    geometry = {
        'seat_y': params['corner_radius'] - params['panel_thickness']
                  - params['panel_tolerance'],
        'flat_x': -(params['panel_overlap'] + params['panel_offset'])
                  + params['corner_tolerance'],
        # The diagonal seating plane, x + y = flat_offset. Restated here from the same
        # expression `corner_tree` carries rather than read out of the solid, because the
        # drawing wants the plane and the solid only shows where the plane cut it.
        'flat_offset': -max(params['longeron_radius'] + params['longeron_tolerance']
                            + params['extrusion_width'],
                            (params['panel_overlap'] + params['panel_offset'])
                            - (params['corner_radius'] - params['panel_thickness']
                               - params['panel_tolerance']))
                       + params['corner_tolerance'] * (2.0 ** 0.5),
    }

    view = View(-21.0, -14.5, 23.0, 15.5, px=560)
    panels = []
    for key, title, draw, blurb in SCHEMES:
        panels.append(
            '<figure class="scheme">'
            '<figcaption><span class="key">%s</span><h3>%s</h3></figcaption>'
            '<div class="plate">%s</div>'
            '<p class="blurb">%s</p>'
            '</figure>' % (key, title, draw(view, outline, params, geometry), blurb))

    rows = '\n'.join(
        '<tr><td class="tagcell">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
        % row for row in schedule_rows(params))

    marks = {key: '<span class="s %s">%s</span>' % pair
             for key, pair in MARKS.items()}
    score = []
    for key, question in QUESTIONS:
        cells = ''.join('<td>%s</td>' % marks[SCORES[s][key]] for s, _t, _d, _b in SCHEMES)
        score.append('<tr><th scope="row">%s</th>%s</tr>' % (question, cells))

    aperture = sections['bulkhead']['loops'][1]
    bulkhead_view = bulkhead_panel(sections['bulkhead'], params, bulkhead)
    panel_view = panel_panel(sections['bulkhead'], params, bulkhead)
    assembly_view = assembly_panel(sections, params, bulkhead)
    panel_width = (bulkhead['unit_width']
                   - 2 * (bulkhead['corner_radius'] + bulkhead['panel_offset']))

    def shelled(kind, index):
        part = sections[kind]
        return '%.0f' % part['shelled_mm3'][index]

    def percent(kind, index):
        part = sections[kind]
        return '%.0f' % (100.0 * part['shelled_mm3'][index] / part['volume_mm3'])

    facts = {
        'variant': '%g&thinsp;U, %s panel, FX&thinsp;%g'
                   % (params['U'], data['variant']['panel_name'], params['FX']),
        'panels': '\n'.join(panels),
        'rows': rows,
        'score': '\n'.join(score),
        'heads': ''.join('<th scope="col">%s</th>' % s for s, _t, _d, _b in SCHEMES),
        'aperture_w': '%.2f' % aperture['bbox'][0],
        'aperture_a': '%.0f' % aperture['area_mm2'],
        'corner_v': '%.0f' % sections['corner']['volume_mm3'],
        'bulkhead_v': '%.0f' % sections['bulkhead']['volume_mm3'],
        'boom_v': '%.0f' % sections['boom_bulkhead']['volume_mm3'],
        'bulkhead_view': bulkhead_view,
        'panel_view': panel_view,
        'assembly_view': assembly_view,
        'panel_width': '%.3f' % panel_width,
        'panel_exposed': '%.3f' % (panel_width - 2 * bulkhead['panel_overlap']),
        'corner_wall': '%.0f' % sections['corner']['wall_area_mm2'],
        'bulkhead_wall': '%.0f' % sections['bulkhead']['wall_area_mm2'],
        'boom_wall': '%.0f' % sections['boom_bulkhead']['wall_area_mm2'],
        'corner_p1': shelled('corner', 0), 'corner_p1pc': percent('corner', 0),
        'corner_p2': shelled('corner', 1), 'corner_p2pc': percent('corner', 1),
        'bulkhead_p1': shelled('bulkhead', 0), 'bulkhead_p1pc': percent('bulkhead', 0),
        'bulkhead_p2': shelled('bulkhead', 1), 'bulkhead_p2pc': percent('bulkhead', 1),
        'boom_p1': shelled('boom_bulkhead', 0), 'boom_p1pc': percent('boom_bulkhead', 0),
        'boom_p2': shelled('boom_bulkhead', 1), 'boom_p2pc': percent('boom_bulkhead', 1),
        'bolt': '%s%.2f' % (DIA, 2 * bulkhead['bolt_hole_radius']),
        'bolt_bare': '%.2f' % (2 * bulkhead['bolt_hole_radius']),
        'bolt_offset': '%.2f' % bulkhead['bolt_offset'],
    }

    with open(template_path or os.path.join(HERE, 'dimension_alternatives',
                                            'template.html'), encoding='utf-8') as handle:
        page = handle.read()
    for name, value in facts.items():
        page = page.replace('{{%s}}' % name, value)

    with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(page)
    return out_path


def main(argv):
    out = argv[1] if len(argv) > 1 else 'dimension_alternatives.html'
    with open(DATA, encoding='utf-8') as handle:
        data = json.load(handle)
    print('wrote %s' % build(data, out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
