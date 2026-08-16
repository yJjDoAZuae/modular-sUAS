"""Diagrams for OQ-DES-B14 -- the bolt-flange fillet and its singularity.

The bolt-flange fillet (`bbf` in `freecad/fillets.py`) is a quadrilateral of material clipped
by a stepped relief stack. Its shape is governed by one quantity,

    bbf_dx = (flange_inner_x - flange_fillet_radius) - (-bolt_offset)

the gap between the fillet's vertical construction line and the bolt centerline. Nothing in
the parameter derivation constrains it, and it passes through zero as U varies. These figures
show what the construction is, what happens as `bbf_dx` shrinks, and why the near-degenerate
case is worse behaved than the exactly degenerate one.

Every number is computed from `derived_parameters()` for a real swept variant -- these are
measured drawings, not schematics. Run:

    uv run python src/Fuselage/tools/draw_bolt_flange_fillet.py

which writes SVGs into doc/design/img/bolt_flange_fillet/.

The two context figures are traced from the built solid rather than from the derivation,
because "where in the bulkhead does this sit" cannot be answered from the fillet's own
arithmetic without re-deriving the whole outer profile. Their input is a snapshot written
by `bbf_analysis/measure_bbf_context.py` -- re-run that if the bulkhead moves, or these
two will keep showing the old shape while still looking authoritative.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DOC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'doc', 'design'))
IMG_SUBDIR = os.path.join('img', 'bolt_flange_fillet')
CONTEXT = os.path.join(HERE, 'bbf_analysis', 'context_U1.5_end_anchor_0mm.json')
CONTEXT_NOMINAL = os.path.join(HERE, 'bbf_analysis', 'context_U2.0_end_anchor_0mm.json')

import fuselage_variants as fv  # noqa: E402

# Same vocabulary as draw_corner_joint.py, so the two sets of figures read as one family.
SVG_CSS = """
.fbody   { fill:rgba(16,22,25,.14); stroke:#101619; stroke-width:1.3; }
.fquad   { fill:rgba(122,94,168,.22); stroke:#7a5ea8; stroke-width:1.6; }
.fplate  { fill:rgba(16,22,25,.10); stroke:#101619; stroke-width:1; }
.fstand  { fill:rgba(11,110,128,.16); stroke:#0b6e80; stroke-width:1; }
.zoom    { fill:none; stroke:#b8372a; stroke-width:1.6; stroke-dasharray:5 3; }
.fsliver { fill:#b8372a; stroke:#b8372a; stroke-width:.8; }
.tool    { fill:none; stroke:#0b6e80; stroke-width:1.1; stroke-dasharray:7 4; }
.relief  { fill:rgba(11,110,128,.10); stroke:#0b6e80; stroke-width:1.2; }
.ring    { fill:none; stroke:#1c7a54; stroke-width:1.6; }
.rule    { stroke:#9fb0ba; stroke-width:1; stroke-dasharray:3 4; }
.ray     { stroke:#b8372a; stroke-width:1.8; }
.edge    { stroke:#0b6e80; stroke-width:1.8; }
.axis    { stroke:#9fb0ba; stroke-width:1; }
.bar     { fill:rgba(122,94,168,.55); stroke:#7a5ea8; stroke-width:.8; }
.barbad  { fill:rgba(184,55,42,.65); stroke:#b8372a; stroke-width:.8; }
.band    { fill:rgba(184,55,42,.10); stroke:none; }
text.lbl   { font-family:monospace; font-size:10px; fill:#5d6f79; }
text.plbl  { font-family:monospace; font-size:10px; fill:#0b6e80; font-weight:600; }
text.nclbl { font-family:monospace; font-size:10px; fill:#7a5ea8; font-weight:600; }
text.gclbl { font-family:monospace; font-size:10px; fill:#b8372a; font-weight:600; }
text.xlbl  { font-family:monospace; font-size:10px; fill:#1c7a54; font-weight:600; }
text.ttl   { font-family:monospace; font-size:11px; fill:#5d6f79; font-weight:600; }
.dim line  { stroke:#b8372a; stroke-width:1.1; }
.dim text  { font-family:monospace; font-size:10px; fill:#b8372a; font-weight:600; }
.faint line { stroke:#5d6f79; stroke-width:1; }
.faint text { fill:#5d6f79; font-weight:400; }
@media (prefers-color-scheme: dark) {
  .fbody   { fill:rgba(220,230,234,.13); stroke:#dce6ea; }
  .fquad   { fill:rgba(179,154,224,.24); stroke:#b39ae0; }
  .fplate  { fill:rgba(220,230,234,.10); stroke:#dce6ea; }
  .fstand  { fill:rgba(69,194,214,.16); stroke:#45c2d6; }
  .zoom    { stroke:#ff6f5e; }
  .fsliver { fill:#ff6f5e; stroke:#ff6f5e; }
  .tool, .relief { stroke:#45c2d6; }
  .relief  { fill:rgba(69,194,214,.12); }
  .ring    { stroke:#4fd39b; }
  .rule, .axis { stroke:#5b6f79; }
  .ray     { stroke:#ff6f5e; }
  .edge    { stroke:#45c2d6; }
  .bar     { fill:rgba(179,154,224,.55); stroke:#b39ae0; }
  .barbad  { fill:rgba(255,111,94,.65); stroke:#ff6f5e; }
  .band    { fill:rgba(255,111,94,.12); }
  text.lbl { fill:#8ea3ad; } text.plbl { fill:#45c2d6; } text.nclbl { fill:#b39ae0; }
  text.gclbl { fill:#ff6f5e; } text.xlbl { fill:#4fd39b; } text.ttl { fill:#8ea3ad; }
  .dim line { stroke:#ff6f5e; } .dim text { fill:#ff6f5e; }
  .faint line { stroke:#8ea3ad; } .faint text { fill:#8ea3ad; }
}
"""


# A standalone `.svg` is parsed as XML, which defines only &amp; &lt; &gt; &quot; &apos; --
# the HTML named entities are undefined there and make the whole file fail to render, not
# merely show a wrong glyph. The corner_joint figures get away with them because they are
# embedded in markdown; these are written as files, so they are converted to numeric
# references, which are valid in both.
NAMED_ENTITIES = {
    '&mdash;': '&#8212;', '&ndash;': '&#8211;', '&deg;': '&#176;',
    '&times;': '&#215;', '&minus;': '&#8722;', '&sup3;': '&#179;',
    '&sup2;': '&#178;', '&nbsp;': '&#160;', '&hellip;': '&#8230;',
}


def xml_safe(text):
    for named, numeric in NAMED_ENTITIES.items():
        text = text.replace(named, numeric)
    return text


class Chart:
    """Non-uniform axes, for the scan plot only.

    `View` deliberately keeps one scale for both axes -- a drawing of geometry that stretched
    one axis would be a lie. A chart is not a drawing of geometry: 88 variants against a
    +/-6 mm range under a uniform scale is 460x56 px, unreadable. So the two are separate
    types rather than one type with a flag, and nothing that draws a part can reach this.
    """

    def __init__(self, x0, y0, x1, y1, px=460, py=300):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.px, self.py = px, py
        self.kx = px / (x1 - x0)
        self.ky = py / (y1 - y0)

    def p(self, x, y):
        return ((x - self.x0) * self.kx, (self.y1 - y) * self.ky)

    def wire(self, pts):
        out = []
        for i, (x, y) in enumerate(pts):
            a = self.p(x, y)
            out.append('%s%.4f %.4f' % ('M' if i == 0 else 'L', a[0], a[1]))
        return ' '.join(out) + ' Z'


class View:
    def __init__(self, x0, y0, x1, y1, px=460):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.px = px
        self.k = px / (x1 - x0)
        self.py = (y1 - y0) * self.k

    def p(self, x, y):
        return ((x - self.x0) * self.k, (self.y1 - y) * self.k)

    def wire(self, pts):
        out = []
        for i, (x, y) in enumerate(pts):
            a = self.p(x, y)
            out.append('%s%.4f %.4f' % ('M' if i == 0 else 'L', a[0], a[1]))
        return ' '.join(out) + ' Z'


def poly(v, pts, cls):
    return '<path class="%s" d="%s"/>' % (cls, v.wire(pts))


def face(v, wires, cls):
    """One face: outer wire then holes, punched with the even-odd rule."""
    return ('<path class="%s" fill-rule="evenodd" d="%s"/>'
            % (cls, ' '.join(v.wire(w) for w in wires)))


def rect(v, x0, y0, x1, y1, cls):
    return poly(v, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], cls)


def line(v, x1, y1, x2, y2, cls):
    a, b = v.p(x1, y1), v.p(x2, y2)
    return ('<line class="%s" x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f"/>'
            % (cls, a[0], a[1], b[0], b[1]))


def circle(v, cx, cy, r, cls, n=180):
    pts = [(cx + r * math.cos(2 * math.pi * i / n),
            cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return '<path class="%s" d="%s"/>' % (cls, v.wire(pts))


def arc(v, cx, cy, r, a0, a1, cls, n=120):
    pts = [(cx + r * math.cos(a0 + (a1 - a0) * i / n),
            cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    d = ' '.join('%s%.4f %.4f' % ('M' if i == 0 else 'L', *v.p(x, y))
                 for i, (x, y) in enumerate(pts))
    return '<path class="%s" fill="none" d="%s"/>' % (cls, d)


def dot(v, x, y, r, color):
    a = v.p(x, y)
    return ('<circle cx="%.3f" cy="%.3f" r="%.1f" fill="%s"/>'
            % (a[0], a[1], r, color))


def txt(v, x, y, s, cls='lbl', dx=0, dy=0, anchor='start'):
    a = v.p(x, y)
    return ('<text class="%s" x="%.2f" y="%.2f" text-anchor="%s">%s</text>'
            % (cls, a[0] + dx, a[1] + dy, anchor, s))


def hdim(v, x1, x2, y, label, up=-9):
    a, b = v.p(x1, y), v.p(x2, y)
    mid = (a[0] + b[0]) / 2
    return ('<g class="dim"><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<text x="%.2f" y="%.2f" text-anchor="middle">%s</text></g>'
            % (a[0], a[1], b[0], b[1], a[0], a[1] - 4, a[0], a[1] + 4,
               b[0], b[1] - 4, b[0], b[1] + 4, mid, a[1] + up, label))


def vdim(v, y1, y2, x, label, dx=8):
    a, b = v.p(x, y1), v.p(x, y2)
    mid = (a[1] + b[1]) / 2
    return ('<g class="dim"><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<text x="%.2f" y="%.2f">%s</text></g>'
            % (a[0], a[1], b[0], b[1], a[0] - 4, a[1], a[0] + 4, a[1],
               b[0] - 4, b[1], b[0] + 4, b[1], a[0] + dx, mid + 4, label))


def svg_raw(px, py, body, cid, title):
    return ('<div class="scroller"><svg class="sheet" viewBox="0 0 %.0f %.0f" role="img"\n'
            'preserveAspectRatio="xMidYMid meet"><title>%s</title>'
            '<style>%s</style>'
            '<defs><clipPath id="%s"><rect x="0" y="0" width="%.0f" height="%.0f"/>'
            '</clipPath></defs><g clip-path="url(#%s)">%s</g></svg></div>'
            % (px, py, title, SVG_CSS, cid, px, py, cid, body))


def svg(v, body, cid, title):
    return svg_raw(v.px, v.py, body, cid, title)


# --------------------------------------------------------------------------- geometry

def geometry(U, type_name, panel_name):
    """Every quantity the bbf construction uses, from the real derivation."""
    axes = fv.axes('panel_variants.csv', 'bulkhead_type_variants.csv',
                   'bulkhead_size_variants.csv')
    printer = fv.null_printer_settings()
    for params in fv.flatten_param_space(fv.read_all_param_axes(axes)):
        if params['U'] != U or params['bulkhead_type_name'] != type_name \
                or params['panel_name'] != panel_name:
            continue
        dp = fv.derived_parameters(U, 1.0, params, printer, True)
        ffr = dp.bulkhead_flange.fillet_radius
        g = {
            'U': U, 'type': type_name, 'panel': panel_name,
            'bolt_c': -dp.bolt.offset,
            'bolt_r': dp.bolt.radius,
            'bolt_t': dp.bolt.thickness,
            'ffr': ffr,
            'chamfer': dp.bulkhead_flange.chamfer,
            'flange_t': dp.bulkhead_flange.thickness,
        }
        g['flange_inner_x'] = -(dp.panel.tolerance + dp.panel.offset
                                + dp.panel.overlap + dp.bulkhead_flange.thickness)
        g['bbf_cx'] = g['flange_inner_x'] - ffr
        g['bbf_dx'] = g['bbf_cx'] - g['bolt_c']
        g['r_bolt_fillet'] = ffr + g['bolt_r'] + g['bolt_t']
        g['bbf_cy'] = math.sqrt(max(g['r_bolt_fillet'] ** 2 - g['bbf_dx'] ** 2, 0.0)) \
            + g['bolt_c']
        g['bbf_dy'] = g['bbf_cy'] - g['bolt_c']
        g['bbf_sx'] = max(g['flange_inner_x'], g['bolt_c'])
        g['bbf_bx'] = min(g['bbf_cx'], g['bolt_c'])
        g['relief_r_low'] = ffr - g['chamfer']
        g['theta'] = math.atan2(g['bbf_dx'], g['bbf_dy'])   # ray tilt from vertical
        g['sliver'] = g['relief_r_low'] * (1 - math.cos(g['theta']))
        return g
    raise SystemExit('no such variant: %s %s %s' % (U, type_name, panel_name))


def quad(g):
    """The four vertices the construction is trying to produce."""
    return [(g['bbf_cx'], g['bbf_cy']), (g['bbf_sx'], g['bbf_cy']),
            (g['bbf_sx'], g['bolt_c']), (g['bolt_c'], g['bolt_c'])]


# --------------------------------------------------------------------------- context

def load_context(path):
    """The measured snapshot, or None -- the five construction figures do not need it."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def tiled(pts, co, swap, sy, sx):
    """One octant's copy of `pts`, in the bulkhead's frame.

    The octant is translated to `(co, co)` and then doubled three times -- about x = y,
    then about y = 0, then about x = 0 -- so the swap comes first and the two sign flips
    after it, in that order. Getting this backwards puts the fillets in the right places
    by symmetry and the wrong ones individually, which is why the sign patterns are read
    from the measured file rather than re-derived here.
    """
    out = []
    for x, y in pts:
        x, y = x + co, y + co
        if swap:
            x, y = y, x
        out.append((sx * x, sy * y))
    return out


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def legend(x, y, rows):
    """Swatch and caption, placed in pixels -- these go in whatever hole the part leaves."""
    out = []
    for i, (cls, label) in enumerate(rows):
        yy = y + i * 17
        out.append('<rect class="%s" x="%.1f" y="%.1f" width="20" height="11"/>'
                   % (cls, x, yy))
        out.append('<text class="lbl" x="%.1f" y="%.1f">%s</text>'
                   % (x + 27, yy + 10, label))
    return '\n'.join(out)


def fig_terms(ctx, g, cid):
    """Every noun the rest of this question uses, drawn once.

    Four panels, left to right, in the order `bolt_flange_fillet()` builds them. The last
    is the measured section of the solid FreeCAD produced, so the first three are checked
    by it: if the block or the wedge were drawn wrong, panel 4 would not match panel 3.
    """
    bc, cx, cy = g['bolt_c'], g['bbf_cx'], g['bbf_cy']
    sx, bx, ffr, r = g['bbf_sx'], g['bbf_bx'], g['ffr'], g['relief_r_low']
    # The PLATE level, where the stepped relief is still at its low radius. One step up the
    # chamfer the same solid sections at flange_fillet_radius instead, and panel 4 would
    # then not match panel 3 -- the difference would be the chamfer, not an error.
    built = ctx['levels']['plate']['BoltFlangeFillet'][0][0]

    block = [(bx, bc), (sx, bc), (sx, cy), (bx, cy)]
    wedge = [(bx, bc), (bx, cy), (cx, cy)]        # left of the block edge, right of the ray
    region = quad(g)                              # what is left after the ray cut

    # the relief cylinder eats the interior angle at (cx, cy), between the edge running to
    # (sx, cy) and the edge running back down the ray to the bolt center
    a1 = math.atan2(bc - cy, bc - cx)
    sector = [(cx, cy)] + [(cx + r * math.cos(a1 * i / 48), cy + r * math.sin(a1 * i / 48))
                           for i in range(49)]

    pad = 1.6
    pv = View(min(bx, cx) - pad, bc - pad, sx + pad, cy + pad * 2.4, px=150)
    gap, head, foot, slack = 34, 46, 26, 12

    def panel(items, caption):
        b = list(items)
        b.append('<text class="lbl" x="0" y="%.0f">%s</text>' % (pv.py + 16, caption))
        return '\n'.join(b)

    panels = [
        panel([poly(pv, block, 'fstand'),
               hdim(pv, bx, sx, cy + 0.5, '%.3f' % (sx - bx)),
               vdim(pv, bc, cy, sx + 0.5, '%.3f' % (cy - bc)),
               txt(pv, bx, bc, 'the block', 'plbl', dx=2, dy=-5)],
              '1. BffBlock, the covering box'),
        panel([poly(pv, block, 'tool'), poly(pv, region, 'fquad'),
               poly(pv, wedge, 'fsliver'),
               line(pv, bc, bc, cx, cy, 'ray'),
               txt(pv, cx, cy, 'the wedge', 'gclbl', dx=-3, dy=-7, anchor='end'),
               txt(pv, sx, (bc + cy) / 2, 'the quad', 'nclbl', dx=-3, dy=0, anchor='end')],
              '2. minus the ray half-plane'),
        panel([poly(pv, region, 'fquad'), poly(pv, sector, 'fsliver'),
               arc(pv, cx, cy, ffr, a1, 0.0, 'tool'),
               dot(pv, cx, cy, 2.4, '#7a5ea8'),
               txt(pv, cx, cy - r, 'the relief cut', 'gclbl', dx=4, dy=13),
               txt(pv, cx, cy - ffr, 'relief_r_low %.2f' % r, 'plbl', dx=4, dy=13),
               txt(pv, cx, cy - ffr, 'then %.2f up the chamfer' % ffr, 'plbl',
                   dx=4, dy=25),
               txt(pv, cx, cy, 'fillet center', 'nclbl', dx=-3, dy=-6, anchor='end')],
              '3. minus the relief stack'),
        panel([poly(pv, built, 'fquad'),
               txt(pv, sx, (bc + cy) / 2, 'the fillet', 'nclbl', dx=-3, dy=0,
                   anchor='end')],
              '4. the result, as built'),
    ]

    px = len(panels) * pv.px + (len(panels) - 1) * gap + slack
    py = pv.py + head + foot
    b = ['<g transform="translate(%.1f %.1f)">%s</g>' % (i * (pv.px + gap), head, p)
         for i, p in enumerate(panels)]
    b.append('<text class="ttl" x="0" y="14">the four nouns &mdash; U=%s %s %s, after the '
             'fix</text>' % (g['U'], g['type'], g['panel']))
    b.append('<text class="lbl" x="0" y="28">plan view, one scale for both axes; '
             'dimensions in mm</text>')
    return svg_raw(px, py, '\n'.join(b), cid,
                   'the block, the wedge, the quad and the fillet')


def fig_context_bulkhead(ctx, g, cid):
    """The whole bulkhead in plan, with all eight bolt-flange fillets marked.

    Two sections at once: the plate, which is the part's silhouette, and a cut above the
    plate through the standing flange wall and the four corner bosses. The fillet lives in
    the second, in the notch between a boss and the wall.
    """
    P = ctx['params']
    co, half = P['corner_offset'], P['unit_width'] / 2
    plate = ctx['levels']['plate']['BulkheadFull'][0]
    stand = ctx['levels']['flange']['BulkheadFull'][0]
    fillet = ctx['levels']['flange']['BoltFlangeFillet'][0][0]

    v = View(-half * 1.05, -half * 1.30, half * 1.05, half * 1.34, px=470)
    b = [face(v, plate, 'fplate'), face(v, stand, 'fstand')]

    copies = [tiled(fillet, co, *t) for t in ctx['tiling']]
    for c in copies:
        b.append(poly(v, c, 'fquad'))

    # the pair in the +x +y corner, which is what the next figure zooms into
    pair = [p for t, c in zip(ctx['tiling'], copies, strict=True) if t[1] > 0 and t[2] > 0 for p in c]
    x0, y0, x1, y1 = bbox(pair)
    pad = half * 0.075
    b.append(rect(v, x0 - pad, y0 - pad, x1 + pad, y1 + pad, 'zoom'))
    b.append(txt(v, x0 - pad, (y0 + y1) / 2, 'next figure', 'gclbl', dx=-6, dy=4,
                 anchor='end'))

    b.append(hdim(v, -half, half, half * 1.17, 'unit_width %.0f mm' % P['unit_width']))
    b.append(legend(v.px * 0.20, v.py * 0.40, [
        ('fplate', 'the plate, z = %.2f mm' % ctx['levels']['plate']['z']),
        ('fstand', 'standing flange and corner bosses, z = %.2f mm'
         % ctx['levels']['flange']['z']),
        ('fquad', 'bolt-flange fillet, two per corner'),
    ]))

    b.append('<text class="ttl" x="8" y="14">where the bolt-flange fillet is &mdash; '
             'U=%s %s %s</text>' % (g['U'], g['type'], g['panel']))
    b.append('<text class="lbl" x="8" y="%.0f">two sections of the built solid; the fillets '
             'straddle the four bolt holes</text>' % (v.py - 8))
    return svg(v, '\n'.join(b), cid, 'the bolt-flange fillet located in the whole bulkhead')


def fig_context_octant(ctx, g, cid):
    """One octant, in the frame every other figure here uses.

    The bulkhead is eight copies of this, so the fillet is built once, here, and the
    octant mask along y = x cuts whatever of it falls on the other side. The dashed box is
    what the construction figures below show.
    """
    P = ctx['params']
    co = P['corner_offset']
    local = lambda w: [(x - co, y - co) for x, y in w]  # noqa: E731
    plate = [local(w) for w in ctx['levels']['plate']['BulkheadSection'][0]]
    stand = [local(w) for w in ctx['levels']['flange']['BulkheadSection'][0]]
    fillet = ctx['levels']['flange']['BoltFlangeFillet'][0][0]
    block = ctx['levels']['flange']['BffBlock'][0][0]

    ox0, oy0, ox1, oy1 = bbox(plate[0] + stand[0])
    v = View(ox0 - 3, oy0 - 13, ox1 + 3, oy1 + 10, px=560)
    b = [face(v, plate, 'fplate'), face(v, stand, 'fstand')]

    # the diagonal the octant mask cuts on, which passes through the bolt center
    b.append(line(v, oy0 - 5, oy0 - 5, 2, 2, 'rule'))
    b.append(txt(v, oy0 - 4, oy0 - 4, 'octant mask, y = x', 'lbl', dx=8, dy=11))

    b.append(poly(v, block, 'tool'))
    b.append(poly(v, fillet, 'fquad'))

    bc = g['bolt_c']
    b.append(circle(v, bc, bc, P['bolt_hole_radius'], 'fplate'))
    b.append(dot(v, bc, bc, 2.4, '#1c7a54'))

    # the construction figures' window
    zx0, zy0 = min(g['bbf_bx'], bc) - 6.0, bc - 2.6
    zx1, zy1 = g['bbf_sx'] + 3.2, g['bbf_cy'] + 4.6
    b.append(rect(v, zx0, zy0, zx1, zy1, 'zoom'))
    b.append(txt(v, zx0, zy1, 'the figures below', 'gclbl', dx=-6, dy=-4, anchor='end'))

    b.append(txt(v, g['bbf_bx'], g['bbf_cy'], 'BoltFlangeFillet', 'nclbl',
                 dx=-6, dy=-16, anchor='end'))
    b.append(txt(v, g['bbf_bx'], g['bbf_cy'], 'and the BffBlock it starts from', 'plbl',
                 dx=-6, dy=-4, anchor='end'))
    b.append(txt(v, bc, bc, 'bolt hole', 'xlbl', dx=-8, dy=4, anchor='end'))
    b.append(txt(v, ox1, oy1, 'flange wall', 'plbl', dx=-8, dy=-6, anchor='end'))

    b.append('<text class="ttl" x="8" y="14">the octant the fillet is built in &mdash; '
             'U=%s %s %s</text>' % (g['U'], g['type'], g['panel']))
    b.append('<text class="lbl" x="8" y="28">the bulkhead is eight mirrored copies of this; '
             'every figure below uses this frame</text>')
    b.append('<text class="lbl" x="8" y="%.0f">one solid crossing y = x: the mask keeps this '
             'side, its mirror supplies the rest</text>' % (v.py - 8))
    return svg(v, '\n'.join(b), cid, 'the octant the bolt-flange fillet is built in')


# --------------------------------------------------------------------------- figures

def fig_construction(g, cid, fixed=False):
    """The whole construction in plan: block, ray, relief stack, resulting quad.

    Drawn at one scale for both axes -- the region really is this tall and thin.
    """
    bc, cx, cy = g['bolt_c'], g['bbf_cx'], g['bbf_cy']
    sx, rbf, ffr = g['bbf_sx'], g['r_bolt_fillet'], g['ffr']
    blk_x = g['bbf_bx'] if fixed else cx
    left = min(blk_x, bc) - 6.0        # room for the center labels and the arc callout
    right = sx + 3.2
    bot = bc - 2.6
    top = cy + 4.6                     # room for the two title lines
    v = View(left, bot, right, top, px=560)
    b = []

    # context: the bolt hole and the ring of material around it
    b.append(circle(v, bc, bc, g['bolt_r'], 'fbody'))
    b.append(circle(v, bc, bc, g['bolt_r'] + g['bolt_t'], 'ring'))
    b.append(txt(v, bc, bc - g['bolt_r'] - g['bolt_t'], 'bolt ring', 'xlbl', dx=4, dy=13))

    # the arc the fillet center is required to lie on
    b.append(arc(v, bc, bc, rbf, math.radians(72), math.radians(104), 'rule'))
    a1 = math.radians(104)
    b.append(txt(v, bc + rbf * math.cos(a1), bc + rbf * math.sin(a1),
                 'r_bolt_fillet %.2f' % rbf, 'xlbl', dx=-5, dy=-5, anchor='end'))

    # the block the construction starts from -- this is what the fix moves
    b.append(poly(v, [(blk_x, bc), (sx, bc), (sx, cy), (blk_x, cy)], 'tool'))
    b.append(txt(v, sx, cy, 'BffBlock', 'plbl', dx=5, dy=-6))

    # the region the construction is meant to produce
    b.append(poly(v, quad(g), 'fquad'))

    # the flange face, and the fillet's construction line one radius outboard of it
    b.append(line(v, g['flange_inner_x'], bot, g['flange_inner_x'], top, 'rule'))
    b.append(txt(v, g['flange_inner_x'], top, 'flange_inner_x', 'lbl', dx=4, dy=26))
    b.append(line(v, cx, bot, cx, top, 'rule'))
    b.append(txt(v, cx, top, 'bbf_cx', 'nclbl', dx=-4, dy=14, anchor='end'))

    # the ray: bolt center through fillet center, extended as the half-plane's near edge
    b.append(line(v, bc, bc, bc + (cx - bc) * 1.26, bc + (cy - bc) * 1.26, 'ray'))
    b.append(txt(v, bc + (cx - bc) * 0.55, bc + (cy - bc) * 0.55, 'ray edge', 'gclbl',
                 dx=-7, dy=0, anchor='end'))

    # the relief stack, centerd on the fillet center
    b.append(circle(v, cx, cy, ffr, 'relief'))
    b.append(circle(v, cx, cy, g['relief_r_low'], 'tool'))

    # the two centers, labelled into the empty left margin
    b.append(dot(v, bc, bc, 2.8, '#1c7a54'))
    b.append(txt(v, bc, bc, 'bolt center', 'xlbl', dx=-9, dy=4, anchor='end'))
    b.append(dot(v, cx, cy, 2.8, '#7a5ea8'))
    b.append(txt(v, cx, cy, 'fillet center', 'nclbl', dx=-11, dy=-7, anchor='end'))
    b.append(txt(v, cx, cy, 'relief r %.2f / %.2f' % (ffr, g['relief_r_low']),
                 'plbl', dx=-11, dy=7, anchor='end'))

    # dimensions
    b.append(vdim(v, bc, cy, sx + 1.5, 'bbf_dy %.3f' % g['bbf_dy']))
    b.append(hdim(v, bc, cx, bc - 1.2, 'bbf_dx %.3f' % g['bbf_dx']))

    b.append('<text class="ttl" x="8" y="14">U=%s %s, %s panel</text>'
             % (g['U'], g['type'], g['panel']))
    b.append('<text class="ttl" x="8" y="28">bbf_dx %.3f mm, ray %.3f&deg; off vertical</text>'
             % (g['bbf_dx'], math.degrees(g['theta'])))
    if fixed:
        b.append('<text class="ttl" x="8" y="42">block starts at min(bbf_cx; bolt_c)'
                 '</text>')
    head = 'bolt-flange fillet construction, U=%s %s %s' % (g['U'], g['type'], g['panel'])
    return svg(v, '\n'.join(b), cid, head)


def fig_sliver(g, cid, fixed=False):
    """True scale at the fillet center. The defect is not visible here, and that is the point.

    At 1.118 degrees against a 1.5 mm circle, no honest drawing can show the residue. This
    figure shows the *concurrency* -- three constructions meeting at one vertex -- which is
    what is wrong and which is perfectly visible. `fig_detail` exaggerates the angle to show
    the consequence, and says so.
    """
    cx, cy = g['bbf_cx'], g['bbf_cy']
    r, ffr, th = g['relief_r_low'], g['ffr'], g['theta']
    blk_x = g['bbf_bx'] if fixed else cx
    half = ffr * 1.5
    v = View(min(blk_x, cx) - half, cy - half * 1.25, cx + half, cy + half * 0.72, px=520)
    b = []

    # the block, whose left edge is what the fix moves
    b.append(poly(v, [(blk_x, cy - half * 2), (cx + half * 2, cy - half * 2),
                      (cx + half * 2, cy), (blk_x, cy)], 'tool'))

    # the relief stack, centerd on the fillet center
    b.append(circle(v, cx, cy, ffr, 'relief'))
    b.append(circle(v, cx, cy, r, 'tool'))

    # the ray
    L = half * 2.6
    b.append(line(v, cx + L * math.sin(th), cy + L * math.cos(th),
                  cx - L * math.sin(th), cy - L * math.cos(th), 'ray'))

    # where the ray leaves the low relief cylinder -- the vertex the section really has
    ex, ey = cx - r * math.sin(th), cy - r * math.cos(th)
    b.append(dot(v, ex, ey, 2.4, '#b8372a'))
    b.append(txt(v, ex, ey, 'ray exits at (%.4f, %.4f)' % (ex, ey), 'gclbl',
                 dx=-8, dy=12, anchor='end'))

    b.append(dot(v, cx, cy, 3.0, '#7a5ea8'))

    if fixed:
        b.append(txt(v, blk_x, cy, 'block edge, now %.3f mm clear' % abs(cx - blk_x),
                     'plbl', dx=-6, dy=-8, anchor='end'))
        b.append(txt(v, cx, cy, 'fillet center &mdash; on the ray only', 'nclbl',
                     dx=8, dy=-8))
        b.append(hdim(v, blk_x, cx, cy + half * 0.45, 'bbf_dx %.3f' % g['bbf_dx']))
        note = 'the cut is transversal: it removes a real triangle'
    else:
        b.append(txt(v, cx, cy, 'block corner, ray and relief center', 'nclbl',
                     dx=8, dy=-8))
        b.append(txt(v, cx, cy, 'all three at one point', 'nclbl', dx=8, dy=6))
        note = 'the ray only touches the block here, it does not cross it'

    b.append('<text class="ttl" x="8" y="14">%s &mdash; true scale, U=%s %s %s</text>'
             % ('after the fix' if fixed else 'the concurrency',
                g['U'], g['type'], g['panel']))
    b.append('<text class="lbl" x="8" y="%.0f">%s</text>' % (v.py - 8, note))
    head = ('%s at the fillet center' % ('after the fix' if fixed else 'concurrency'))
    return svg(v, '\n'.join(b), cid, head)


def fig_detail(g, cid):
    """Why the cut is tangential: the wedge it removes lies entirely outside the block.

    **There is no sliver in exact arithmetic, and saying otherwise would be wrong.** With the
    block starting at `bbf_cx`, every point of the ray below the fillet center is to the left
    of the block, so the half-plane removes nothing at all -- it touches the block along a
    single point, its corner, which is also where the relief cylinder is centerd. The
    0.000335 mm fold-back edge and the negative-area face are OCCT's artifacts of that
    tangential contact, not geometry anyone modeled.

    The angle is exaggerated, and captioned as such, because at 1.118 degrees the wedge and
    the block edge are one line on any page.
    """
    r, th = g['relief_r_low'], g['theta']
    EXAG = 7.0
    ta = th * EXAG
    span = r * 1.9
    v = View(-span * 0.62, -span, span * 0.62, span * 0.30, px=520)
    b = []

    # the block: everything right of its left edge, which runs down from the corner
    b.append(poly(v, [(0, 0), (span, 0), (span, -span * 1.2), (0, -span * 1.2)], 'tool'))
    b.append(txt(v, span * 0.30, -span * 0.55, 'BffBlock', 'plbl', anchor='middle'))

    # the wedge the half-plane removes: left of the block edge, right of the ray
    b.append(poly(v, [(0, 0), (0, -span * 1.2),
                      (-span * 1.2 * math.tan(ta), -span * 1.2)], 'fsliver'))
    b.append(txt(v, -span * 0.30, -span * 0.72,
                 'where the wedge would be', 'gclbl', anchor='middle'))
    b.append(txt(v, -span * 0.30, -span * 0.86,
                 'entirely outside the block', 'gclbl', anchor='middle'))

    # the relief cylinder, centerd exactly on the corner
    b.append(arc(v, 0, 0, r, math.radians(-150), math.radians(-30), 'relief'))
    b.append(txt(v, 0, -r, 'relief_r_low %.2f' % r, 'plbl', dx=6, dy=14))

    # the corner where all three meet
    b.append(dot(v, 0, 0, 3.4, '#7a5ea8'))
    b.append(txt(v, 0, 0, 'block corner = fillet center = relief center',
                 'nclbl', dx=0, dy=-10, anchor='middle'))

    b.append('<text class="ttl" x="8" y="14">the cut only touches &mdash; angle exaggerated '
             '%.0f&times;</text>' % EXAG)
    b.append('<text class="lbl" x="8" y="28">true angle %.3f&deg;. The wedge is real but lies '
             'outside the block, so the</text>' % math.degrees(th))
    b.append('<text class="lbl" x="8" y="42">half-plane removes nothing and contact is a '
             'single point.</text>')
    b.append('<text class="lbl" x="8" y="%.0f">OCCT emits a %.6f mm fold-back edge and a '
             'negative-area face there.</text>' % (v.py - 8, 0.000334608))
    return svg(v, '\n'.join(b), cid, 'the tangential contact at the fillet center')


def fig_scan(cid):
    """bbf_dx for every valid end-type variant, sorted, with the unstable band marked."""
    axes = fv.axes('panel_variants.csv', 'bulkhead_type_variants.csv',
                   'bulkhead_size_variants.csv')
    printer = fv.null_printer_settings()
    rows = []
    for params in fv.flatten_param_space(fv.read_all_param_axes(axes)):
        dp = fv.derived_parameters(params['U'], 1.0, params, printer, True)
        if not fv.family_is_valid('bulkhead', dp):
            continue
        if dp.bulkhead.type != fv.BulkheadType.END:
            continue
        ffr = dp.bulkhead_flange.fillet_radius
        fix = -(dp.panel.tolerance + dp.panel.offset + dp.panel.overlap
                + dp.bulkhead_flange.thickness)
        rows.append(((fix - ffr) - (-dp.bolt.offset), params['U']))
    rows.sort()

    lo = min(r[0] for r in rows) - 0.6
    hi = max(r[0] for r in rows) + 1.2
    v = Chart(-2.0, lo, len(rows) + 0.5, hi, px=460, py=300)
    b = []
    top, bot = v.p(0, 1.0)[1], v.p(0, -1.0)[1]
    b.append('<rect class="band" x="0" y="%.2f" width="%.0f" height="%.2f"/>'
             % (top, v.px, bot - top))
    for i, (dx, _U) in enumerate(rows):
        y0, y1 = (0.0, dx) if dx > 0 else (dx, 0.0)
        cls = 'barbad' if abs(dx) < 1.0 else 'bar'
        b.append(poly(v, [(i + 0.12, y0), (i + 0.88, y0),
                          (i + 0.88, y1), (i + 0.12, y1)], cls))
    b.append(line(v, -2.0, 0, len(rows) + 0.5, 0, 'axis'))
    for tick in range(int(math.floor(lo)), int(math.ceil(hi)) + 1):
        if lo < tick < hi:
            b.append(txt(v, -2.0, tick, '%+d' % tick, 'lbl', dx=1, dy=3))
    b.append(txt(v, len(rows) * 0.45, 0, 'bbf_dx = 0', 'gclbl', dx=0, dy=-6))
    near = sum(1 for r in rows if abs(r[0]) < 1.0)
    head = ('bbf_dx across all %d valid end-type variants &mdash; %d within 1.0 mm of zero'
            % (len(rows), near))
    b.append('<text class="ttl" x="8" y="14">%s</text>' % head)
    b.append('<text class="lbl" x="8" y="%.0f">one bar per swept variant, sorted; mm on the '
             'vertical; shaded band is |bbf_dx| &lt; 1 mm</text>' % (v.py - 8))
    return svg(v, '\n'.join(b), cid, head)


# --------------------------------------------------------------------------- driver

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--doc-dir', default=DOC_DIR)
    ap.add_argument('--context', default=CONTEXT,
                    help='measured snapshot of the near case, U=1.5 end_anchor 0mm')
    ap.add_argument('--context-nominal', default=CONTEXT_NOMINAL,
                    help='measured snapshot of the nominal case, U=2.0 end_anchor 0mm')
    args = ap.parse_args(argv)

    out = os.path.join(args.doc_dir, IMG_SUBDIR)
    os.makedirs(out, exist_ok=True)

    nominal = geometry(2.0, 'end_anchor', '0mm')
    near = geometry(1.5, 'end_anchor', '0mm')

    figs = {
        'construction_nominal': fig_construction(nominal, 'cn'),
        'construction_near': fig_construction(near, 'cr'),
        'concurrency': fig_sliver(near, 'sl'),
        'concurrency_fixed': fig_sliver(near, 'sf', fixed=True),
        'residue_detail': fig_detail(near, 'rd'),
        'scan': fig_scan('sc'),
    }

    ctx, ctx_nom = load_context(args.context), load_context(args.context_nominal)
    for path, snap in ((args.context, ctx), (args.context_nominal, ctx_nom)):
        if snap is None:
            print('no measured snapshot at %s -- figures that need it are skipped.' % path)
            print('  freecadcmd src/Fuselage/tools/bbf_analysis/measure_bbf_context.py \\')
            print('      --pass params.json %s' % path)
    if ctx is not None:
        figs['context_bulkhead'] = fig_context_bulkhead(ctx, near, 'xb')
        figs['context_octant'] = fig_context_octant(ctx, near, 'xo')
    if ctx_nom is not None:
        figs['terms'] = fig_terms(ctx_nom, nominal, 'tm')
    for name, body in figs.items():
        # strip the wrapper div: a standalone .svg file must start with <svg>
        inner = body[body.index('<svg'):body.rindex('</svg>') + 6]
        inner = inner.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
        path = os.path.join(out, name + '.svg')
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(xml_safe(inner) + '\n')
        print('wrote %s' % os.path.relpath(path, args.doc_dir))

    print()
    print('%-22s %10s %10s %10s %12s' % ('variant', 'bbf_dx', 'bbf_dy', 'tilt deg', 'sliver'))
    for g in (nominal, near):
        print('%-22s %10.4f %10.4f %10.4f %12.9f'
              % ('U=%s %s %s' % (g['U'], g['type'], g['panel']),
                 g['bbf_dx'], g['bbf_dy'], math.degrees(g['theta']), g['sliver']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
