"""What `flat_offset` is, and what `longeron_chamfer` measures, drawn from the booleans.

`longeron_chamfer` is the hardest quantity in the corner to picture, because it is one term
inside `flat_offset`'s `max` and `flat_offset` is an intercept rather than a face, so a reader
following the expressions gets two indirections before reaching anything visible. The name,
however, is exactly right, and this module took three readings to see it.

**The corner snaps onto the longeron.** It wraps 270 degrees of the bore and opens toward the
fuselage interior through a mouth that is narrower than the longeron -- 2.8991 mm of clear
opening against a 4 mm rod at U=1. The two walls of that mouth are flat cuts at 90 degrees to
each other, so each stands at 45 degrees to the direction the rod is pressed in: they are the
lead-in that spreads the arms. That is a chamfer in shape and in function, and
`longeron_chamfer` is the floor on how wide each face is. It is drawn here in orange.

**The material is rasterized from `corner_middle_shape`'s own boolean expression, not traced by
hand.** The first version of this module drew the outline from a reading of the source and got it
wrong in the one place that mattered: it drew a full 0-90 degree quarter, where the module also
subtracts a **mirror mask** (`[[-far,-far],[far,far],[far,-far]]`, keeping `y >= x`) and the
**third-quadrant mask that the source labels `// longeron chamfer`**. The real profile is a
wedge, and the face that mask leaves at `y = 0` -- between the bore and the diagonal -- is the
chamfer itself. Drawing solid material there hid the feature the figure existed to show. So
`solid()` below transcribes the source term for term and the fill is a scan of it; only the
annotation is drawn from the definition.

Two panels per case:

  * **as the module builds it** -- the wedge, where the chamfer is a single face lying on the
    x axis and looks like an artifact of where the cut falls;
  * **mirrored about y = x**, the first step of `octant_to_full()`, where the two halves join
    and the mouth appears: two chamfer faces at 90 degrees, and a clear opening narrower than
    the longeron they close around.

Two cases, because the `max` has two branches and the geometry differs in kind between them:

  * **U=1, 3/16 in panel** -- the bore branch governs, the chamfer is 0.6000 mm wide, exactly
    `longeron_chamfer`, and the flat face is 0.5250 mm tall.
  * **U=0.5, 1 mm panel** -- the panel branch governs, the chamfer is pushed out to 1.8000 mm
    against the same 0.60 minimum, and the flat face is *gone*, not small.

The split across the sweep is 240 corner variants to 24.

**These are diagrams of the definition, not tracings of a built solid**, which is the opposite of
`draw_corner_joint.py`. That the definition and the solid agree is established by
`freecad/check_derived_geometry.py` measuring faces on the part, and is not what these show.

    uv run python src/Fuselage/tools/draw_flat_offset.py

Writes `doc/design/img/flat_offset/*.svg`. Millimeters throughout.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

DOC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'doc', 'design'))
IMG_DIR = os.path.join(DOC_DIR, 'img', 'flat_offset')

FAR = 1000.0

SVG_CSS = """
.mat     { fill:#7a5ea8; stroke:none; opacity:.30; }
.oml     { fill:none; stroke:#1c7a54; stroke-width:2.2; }
.borel   { fill:none; stroke:#0b6e80; stroke-width:1.6; }
.diagline{ fill:none; stroke:#b8372a; stroke-width:2.6; }
.flatface{ fill:none; stroke:#b8372a; stroke-width:3.6; }
.chamfer { fill:none; stroke:#c2680f; stroke-width:4.6; }
.rule    { stroke:#9fb0ba; stroke-width:1; stroke-dasharray:3 4; }
.axis    { stroke:#5d6f79; stroke-width:1; }
.ext     { stroke:#9fb0ba; stroke-width:.9; stroke-dasharray:2 3; }
.mirror  { stroke:#9fb0ba; stroke-width:1.2; stroke-dasharray:8 3 2 3; }
.dim line { stroke:#b8372a; stroke-width:1.1; }
.dim text { font-family:monospace; font-size:10.5px; fill:#b8372a; font-weight:600; }
text.lbl  { font-family:monospace; font-size:10.5px; fill:#5d6f79; }
text.plbl { font-family:monospace; font-size:10.5px; fill:#0b6e80; font-weight:600; }
text.clbl { font-family:monospace; font-size:10.5px; fill:#c2680f; font-weight:700; }
text.xlbl { font-family:monospace; font-size:10.5px; fill:#1c7a54; font-weight:600; }
text.ttl  { font-family:monospace; font-size:12.5px; fill:#101619; font-weight:700; }
text.sub  { font-family:monospace; font-size:11px; fill:#5d6f79; }
.dot     { fill:#b8372a; stroke:none; }
@media (prefers-color-scheme: dark) {
  .mat { fill:#b39ae0; opacity:.32; }
  .oml { stroke:#4fd39b; } .borel { stroke:#45c2d6; }
  .diagline, .flatface, .dot { stroke:#ff6f5e; } .dot { fill:#ff6f5e; }
  .chamfer { stroke:#f5a33c; } text.clbl { fill:#f5a33c; }
  .rule, .ext, .mirror { stroke:#5b6f79; } .axis { stroke:#8ea3ad; }
  .dim line { stroke:#ff6f5e; } .dim text { fill:#ff6f5e; }
  text.lbl, text.sub { fill:#8ea3ad; } text.plbl { fill:#45c2d6; }
  text.xlbl { fill:#4fd39b; } text.ttl { fill:#dce6ea; }
}
"""


def in_polygon(x, y, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def geometry(p):
    """Everything `corner_middle_shape` computes, transcribed rather than simplified."""
    bore_branch = p['longeron_radius'] + p['longeron_tolerance'] + p['longeron_chamfer']
    panel_branch = ((p['panel_overlap'] + p['panel_offset'])
                    - (p['corner_radius'] - p['panel_thickness'] - p['panel_tolerance']))
    nominal = -max(bore_branch, panel_branch)

    g = dict(p)
    g['bore_branch'] = bore_branch
    g['panel_branch'] = panel_branch
    g['flat_offset'] = nominal + p['corner_tolerance'] * math.sqrt(2)
    g['flat_x'] = -(p['panel_overlap'] + p['panel_offset']) + p['corner_tolerance']
    g['flat_y'] = g['flat_offset'] - g['flat_x']
    g['bore_r'] = p['longeron_radius'] + p['longeron_tolerance']
    g['seat_y'] = p['corner_radius'] - p['panel_thickness'] - p['panel_tolerance']
    g['governs'] = 'bore' if bore_branch >= panel_branch else 'panel'
    g['flat_height'] = g['seat_y'] - g['flat_y']
    return g


def predicate(g):
    """`solid(x, y)`, term for term from `corner_middle_shape`.

    difference(union(circle, extension), union(bore, panel cutout, boundary, mirror, quadrant)).
    """
    cr = g['corner_radius']
    arm = g['panel_overlap'] + g['panel_offset']
    bore = g['bore_r']
    fx, fy, fo = g['flat_x'], g['flat_y'], g['flat_offset']

    cut_x0 = -2 * g['panel_overlap'] - g['panel_offset'] + g['panel_tolerance']
    cut_x1 = cut_x0 + 2 * g['panel_overlap']
    cut_y0 = cr - g['panel_thickness'] - g['panel_tolerance']
    cut_y1 = cut_y0 + 2 * g['panel_thickness'] + 2 * g['panel_tolerance']

    boundary = [(fx, cr), (fx, fy), (fo, 0.0), (0.0, fo), (fy, fx),
                (0.0, -FAR), (-FAR, -FAR), (-FAR, FAR)]
    mirror = [(-FAR, -FAR), (FAR, FAR), (FAR, -FAR)]
    quadrant = [(0.0, 0.0), (-FAR, 0.0), (-FAR, -FAR), (0.0, -FAR)]

    def solid(x, y):
        if not ((x * x + y * y <= cr * cr) or (-arm <= x <= 0.0 and 0.0 <= y <= cr)):
            return False
        if x * x + y * y <= bore * bore:
            return False
        if cut_x0 <= x <= cut_x1 and cut_y0 <= y <= cut_y1:
            return False
        if in_polygon(x, y, boundary):
            return False
        if in_polygon(x, y, mirror):
            return False
        if in_polygon(x, y, quadrant):
            return False
        return True

    return solid


class View(object):
    def __init__(self, x0, y0, x1, y1, px=470):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.k = px / float(x1 - x0)
        self.px = px
        self.py = (y1 - y0) * self.k

    def p(self, x, y):
        return ((x - self.x0) * self.k, (self.y1 - y) * self.k)

    def path(self, pts, close=True):
        """A closed SVG path through model-space points. Used by the filled-region figures."""
        d = []
        for i, (x, y) in enumerate(pts):
            a = self.p(x, y)
            d.append('%s%.2f %.2f' % ('M' if i == 0 else 'L', a[0], a[1]))
        return ' '.join(d) + (' Z' if close else '')


def line(v, x1, y1, x2, y2, cls):
    a, b = v.p(x1, y1), v.p(x2, y2)
    return ('<line class="%s" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            % (cls, a[0], a[1], b[0], b[1]))


def txt(v, x, y, s, cls='lbl', dx=0, dy=0, anchor='start'):
    a = v.p(x, y)
    return ('<text class="%s" x="%.2f" y="%.2f" text-anchor="%s">%s</text>'
            % (cls, a[0] + dx, a[1] + dy, anchor, s))


def dot(v, x, y, r=3.0):
    a = v.p(x, y)
    return '<circle class="dot" cx="%.2f" cy="%.2f" r="%.1f"/>' % (a[0], a[1], r)


def arc_path(v, cx, cy, r, a0, a1, cls, n=200):
    out = []
    for i in range(n + 1):
        t = math.radians(a0 + (a1 - a0) * i / float(n))
        a = v.p(cx + r * math.cos(t), cy + r * math.sin(t))
        out.append('%s%.2f %.2f' % ('M' if i == 0 else 'L', a[0], a[1]))
    return '<path class="%s" d="%s"/>' % (cls, ' '.join(out))


def scanfill(v, solid, rows=560):
    """The material, as horizontal runs of the predicate. A rasterization, so it cannot
    disagree with the booleans the way a hand-traced outline can."""
    out = []
    dy = (v.y1 - v.y0) / float(rows)
    cols = 900
    dx = (v.x1 - v.x0) / float(cols)
    for j in range(rows):
        y = v.y0 + (j + 0.5) * dy
        run = None
        for i in range(cols + 1):
            x = v.x0 + (i + 0.5) * dx
            on = (i <= cols) and solid(x, y)
            if on and run is None:
                run = x
            elif not on and run is not None:
                a = v.p(run, y + dy)
                b = v.p(x, y)
                out.append('<rect class="mat" x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>'
                           % (a[0], a[1], max(b[0] - a[0], 0.35), max(b[1] - a[1], 0.9)))
                run = None
    return out


def hdim(v, x1, x2, y, label, up=-11, anchor='middle'):
    a, b = v.p(x1, y), v.p(x2, y)
    return ('<g class="dim">'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<text x="%.2f" y="%.2f" text-anchor="%s">%s</text></g>'
            % (a[0], a[1] + up, b[0], b[1] + up,
               a[0], a[1] + up - 4, a[0], a[1] + up + 4,
               b[0], b[1] + up - 4, b[0], b[1] + up + 4,
               (a[0] + b[0]) / 2, a[1] + up - 6, anchor, label))


def vdim(v, y1, y2, x, label, dx=10):
    """hdim's transpose: a dimension between two y values, offset `dx` pixels to the right."""
    a, b = v.p(x, y1), v.p(x, y2)
    return ('<g class="dim">'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<text x="%.2f" y="%.2f" text-anchor="start">%s</text></g>'
            % (a[0] + dx, a[1], b[0] + dx, b[1],
               a[0] + dx - 4, a[1], a[0] + dx + 4, a[1],
               b[0] + dx - 4, b[1], b[0] + dx + 4, b[1],
               a[0] + dx + 6, (a[1] + b[1]) / 2 + 3.5, label))


# `arc` is the name the drawing modules share; `arc_path` is this module's own, kept because
# every call inside this file uses it.
arc = arc_path


def panel(g, mirrored, title):
    """One view. `mirrored` unions the octant with its reflection about y = x."""
    cr = g['corner_radius']
    fo, fx, fy = g['flat_offset'], g['flat_x'], g['flat_y']
    base = predicate(g)
    solid = (lambda x, y: base(x, y) or base(y, x)) if mirrored else base

    lo = fx - 1.4
    hi = cr + 1.4
    v = View(lo, fx - 1.4 if mirrored else -1.5, hi, cr + 1.4, px=430)

    b = scanfill(v, solid)

    b.append(arc_path(v, 0, 0, cr, 0, 90, 'oml'))
    b.append(arc_path(v, 0, 0, g['bore_r'], 0, 360 if mirrored else 90, 'borel'))
    b.append(line(v, v.x0, 0, hi, 0, 'axis'))
    b.append(line(v, 0, v.y0, 0, cr + 1.2, 'axis'))
    b.append(line(v, v.x0, g['seat_y'], cr, g['seat_y'], 'rule'))

    # the 45 degree line, x + y = flat_offset
    b.append(line(v, fx, fy, fo, 0.0, 'diagline'))
    if mirrored:
        b.append(line(v, fo, 0.0, 0.0, fo, 'diagline'))
        b.append(line(v, 0.0, fo, fy, fx, 'diagline'))
        b.append(line(v, v.x0, v.y0, min(hi, cr + 1.2), min(hi, cr + 1.2), 'mirror'))
        b.append(txt(v, cr * 0.72, cr * 0.72, 'y = x, the mirror', 'lbl', dx=6, dy=-6))
    b.append(dot(v, fo, 0.0))

    if g['flat_height'] > 1e-9:
        b.append(line(v, fx, fy, fx, g['seat_y'], 'flatface'))

    # THE CHAMFER. The face the `// longeron chamfer` mask leaves at y = 0, from the bore out
    # to the tip corner at flat_offset. Mirrored, the second face appears at x = 0 and the two
    # form the mouth the corner snaps onto the longeron through. It is drawn as its own line
    # because three readings of this geometry mistook it for a boundary of the fill.
    b.append(line(v, -g['bore_r'], 0, fo, 0, 'chamfer'))
    if mirrored:
        b.append(line(v, 0, -g['bore_r'], 0, fo, 'chamfer'))
        # The mouth. Its clear opening is the straight run between the two chamfer faces'
        # inner ends, both of which sit on the bore, so it is bore_r*sqrt(2) -- narrower than
        # the longeron, which is why the corner has to snap on rather than slide on.
        br = g['bore_r']
        b.append(line(v, -br, 0, 0, -br, 'rule'))
        b.append(txt(v, -br / 2.0, -br / 2.0, 'mouth', 'clbl', dx=-8, dy=14, anchor='end'))
        b.append(txt(v, (fo - br) / 2.0, 0, 'chamfer', 'clbl', dx=0, dy=-8, anchor='middle'))

    b.append(line(v, -g['bore_r'], 0, -g['bore_r'], -0.95, 'ext'))
    b.append(line(v, fo, 0, fo, -0.95, 'ext'))
    # longeron_chamfer is the FLOOR on the chamfer's width, which the source says in as many
    # words -- "use longeron_chamfer as a minimum". The two are equal only when the bore branch
    # governs. Labelling this longeron_chamfer unconditionally was an error in an earlier
    # version of this drawing.
    chamfer = -fo - g['bore_r']
    if g['governs'] == 'bore':
        label = 'chamfer %.2f = longeron_chamfer' % chamfer
    else:
        label = 'chamfer %.2f, minimum was %.2f' % (chamfer, g['longeron_chamfer'])
    b.append(hdim(v, fo, -g['bore_r'], 0, label, up=34))
    b.append(hdim(v, 0, fo, 0, 'flat_offset %.4f' % fo, up=62))

    b.append(txt(v, 0, cr, 'mold line %g' % cr, 'xlbl', dx=6, dy=-7))
    b.append(txt(v, 0, g['bore_r'], 'bore %.2f' % g['bore_r'], 'plbl', dx=8, dy=15))
    if g['flat_height'] > 1e-9:
        b.append(txt(v, fx, (fy + g['seat_y']) / 2, 'flat face %.4f' % g['flat_height'],
                     'dim', dx=-8, dy=4, anchor='end'))
    else:
        b.append(txt(v, fx, g['seat_y'], 'flat face GONE', 'dim', dx=-8, dy=4, anchor='end'))

    head = '<text class="sub" x="8" y="16">%s</text>' % title
    return v, b, head


def figure(g, title, sub):
    left = panel(g, False, 'as the module builds it &#8212; one chamfer face, on the axis')
    right = panel(g, True, 'mirrored about y = x &#8212; the mouth the corner snaps on through')

    # Measured, not asserted: the mouth's clear opening is the run between the two chamfer
    # faces' inner ends, both of which sit on the bore.
    sub = ('%s Mouth opens %.4f clear against a %.4f longeron, so the corner snaps on.'
           % (sub, g['bore_r'] * math.sqrt(2), 2 * g['longeron_radius']))

    w = left[0].px + 150
    h = max(left[0].py, right[0].py) + 128
    parts = []
    for i, (v, body, head) in enumerate((left, right)):
        parts.append('<g transform="translate(%d,%d)">%s<g transform="translate(84,34)">%s</g></g>'
                     % (18 + i * w, 62, head, ''.join(body)))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" width="%.0f" '
            'height="%.0f"><style>%s</style>'
            '<text class="ttl" x="18" y="24">%s</text>'
            '<text class="lbl" x="18" y="42">%s</text>%s</svg>'
            % (2 * w + 36, h + 62, 2 * w + 36, h + 62, SVG_CSS, title, sub, ''.join(parts)))


CASES = [
    ('bore_branch', 'U=1, 3/16 in panel &#8212; the bore branch governs',
     'flat_offset = -2.6500, and each chamfer face is 0.6000 wide &#8212; exactly '
     'longeron_chamfer. 240 of 264 corner variants land here.',
     dict(corner_radius=10.0, longeron_radius=2.0, longeron_tolerance=0.05,
          panel_thickness=4.7625, panel_tolerance=0.1, panel_overlap=4.7625,
          panel_offset=2.5, corner_tolerance=0.0, longeron_chamfer=0.6)),
    ('panel_branch', 'U=0.5, 1 mm panel &#8212; the panel branch governs',
     'flat_offset = -2.8500, pushed out past what the bore needs: each chamfer face measures '
     '1.80 where longeron_chamfer is only 0.60, because the parameter is a minimum and not the '
     'width. The flat face is gone rather than small. 24 variants.',
     dict(corner_radius=5.0, longeron_radius=1.0, longeron_tolerance=0.05,
          panel_thickness=1.0, panel_tolerance=0.1, panel_overlap=4.0,
          panel_offset=2.75, corner_tolerance=0.0, longeron_chamfer=0.6)),
]


def main():
    if not os.path.isdir(IMG_DIR):
        os.makedirs(IMG_DIR)
    for name, title, sub, params in CASES:
        g = geometry(params)
        path = os.path.join(IMG_DIR, name + '.svg')
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(figure(g, title, sub))

        # the chamfer face, measured off the predicate rather than asserted
        solid = predicate(g)
        eps = 1e-4
        xs = [x * 0.002 for x in range(-4000, 40)]
        run = [x for x in xs if solid(x, eps)]
        print('%-13s governs=%-5s flat_offset=%+.4f flat=%.4f  material at y=0+: '
              '%.4f .. %.4f  width %.4f'
              % (name, g['governs'], g['flat_offset'], g['flat_height'],
                 min(run), max(run), max(run) - min(run)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
