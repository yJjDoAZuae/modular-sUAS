"""The corner/bulkhead joint drawn from the built solids, four views per case.

Regenerates `doc/design/corner_bulkhead_joint.md` and the 24 SVGs beside it. The drawings
are traced from geometry FreeCAD actually built -- `joint_analysis/measure_corner_joint.py`
sections the corner and the bulkhead at the same height in the same frame and writes what it
finds to `joint_analysis/case_*.json`. Nothing here evaluates the design equations, which is
the point: an equation and the solid it is supposed to produce disagreeing is exactly the
class of defect this was built to find, and it found one (OQ-DES-B13).

    uv run python src/Fuselage/tools/draw_corner_joint.py             # markdown + SVGs
    uv run python src/Fuselage/tools/draw_corner_joint.py --html o.html --template t.html

**Regenerate the measured data first if the geometry moved.** The JSON under
`joint_analysis/` is a snapshot of built solids, not a live query, so a change to the corner
or the bulkhead leaves these drawings showing the old shape while still looking
authoritative.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, 'joint_analysis')
DOC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'doc', 'design'))
IMG_SUBDIR = 'img/corner_joint'

# The stroke and fill vocabulary the drawing functions emit class names against, inlined
# into every standalone SVG: an `.svg` referenced from a markdown file has no page around
# it to inherit from. The HTML build gets the same rules from its own stylesheet.
#
# Both themes, because a drawing that is only legible on white is half a drawing.
SVG_CSS = """
.fbody   { fill:rgba(16,22,25,.14); stroke:#101619; stroke-width:1.3; }
.fcorner { fill:rgba(122,94,168,.22); stroke:#7a5ea8; stroke-width:1.3; }
.fpanel  { fill:rgba(28,122,84,.14); stroke:#1c7a54; stroke-width:1.2; }
.tool    { fill:none; stroke:#0b6e80; stroke-width:1.1; stroke-dasharray:7 4; }
.oml     { fill:none; stroke:#1c7a54; stroke-width:2; }
.nominal { stroke:#9fb0ba; stroke-width:1.1; stroke-dasharray:9 3 2 3; }
.rule    { stroke:#9fb0ba; stroke-width:1; stroke-dasharray:3 4; }
.rule2   { stroke:#7a5ea8; stroke-width:1.2; stroke-dasharray:3 4; }
.toolrule{ stroke:#0b6e80; stroke-width:1.4; stroke-dasharray:2 3; }
.wasline { fill:none; stroke:#b8372a; stroke-width:1.8; stroke-dasharray:6 3; }
.xarc    { fill:#1c7a54; stroke:none; }
.gclr    { fill:none; stroke:#b8372a; stroke-width:2.2; }
.diagline{ stroke:#7a5ea8; stroke-width:2.4; opacity:.75; }
text.gclbl { font-family:monospace; font-size:10px; fill:#b8372a; font-weight:600; }
text.nclbl { font-family:monospace; font-size:10px; fill:#7a5ea8; font-weight:600; }
text.plbl  { font-family:monospace; font-size:10px; fill:#0b6e80; font-weight:600; }
text.lbl   { font-family:monospace; font-size:10px; fill:#5d6f79; }
text.xlbl  { font-family:monospace; font-size:10px; fill:#1c7a54; font-weight:600; }
.dim line  { stroke:#b8372a; stroke-width:1.1; }
.dim text  { font-family:monospace; font-size:10px; fill:#b8372a; font-weight:600; }
.faint line { stroke:#5d6f79; stroke-width:1; }
.faint text { fill:#5d6f79; font-weight:400; }
@media (prefers-color-scheme: dark) {
  .fbody   { fill:rgba(220,230,234,.13); stroke:#dce6ea; }
  .fcorner { fill:rgba(179,154,224,.24); stroke:#b39ae0; }
  .fpanel  { fill:rgba(79,211,155,.14); stroke:#4fd39b; }
  .tool, .toolrule { stroke:#45c2d6; }
  .oml { stroke:#4fd39b; } .xarc { fill:#4fd39b; }
  .nominal, .rule { stroke:#5b6f79; }
  .rule2, .diagline { stroke:#b39ae0; }
  .wasline, .gclr { stroke:#ff6f5e; }
  text.gclbl { fill:#ff6f5e; } text.nclbl { fill:#b39ae0; }
  text.plbl { fill:#45c2d6; } text.lbl { fill:#8ea3ad; } text.xlbl { fill:#4fd39b; }
  .dim line { stroke:#ff6f5e; } .dim text { fill:#ff6f5e; }
  .faint line { stroke:#8ea3ad; } .faint text { fill:#8ea3ad; }
}
"""

VIEW_TITLES = ('the joint in section', 'the junction as built',
               'flat face, close up', 'diagonal face, close up')


class View:
    def __init__(self, x0, y0, x1, y1, px=430):
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
            out.append('%s%.3f %.3f' % ('M' if i == 0 else 'L', a[0], a[1]))
        return ' '.join(out) + ' Z'


def fill(v, faces, cls):
    """Each face is [outer, hole...]; even-odd renders the holes."""
    out = []
    for f in faces:
        d = ' '.join(v.wire(w) for w in f)
        out.append('<path class="%s" fill-rule="evenodd" d="%s"/>' % (cls, d))
    return '\n'.join(out)


def outline(v, faces, cls):
    return '\n'.join('<path class="%s" d="%s"/>' % (cls, v.wire(w))
                     for f in faces for w in f)


def line(v, x1, y1, x2, y2, cls):
    a, b = v.p(x1, y1), v.p(x2, y2)
    return ('<line class="%s" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            % (cls, a[0], a[1], b[0], b[1]))


def txt(v, x, y, s, cls='lbl', dx=0, dy=0, anchor='start'):
    a = v.p(x, y)
    return ('<text class="%s" x="%.2f" y="%.2f" text-anchor="%s">%s</text>'
            % (cls, a[0] + dx, a[1] + dy, anchor, s))


def hdim(v, x1, x2, y, label, cls='dim', up=-9):
    """A horizontal dimension between two x values, with ticks and a label."""
    a, b = v.p(x1, y), v.p(x2, y)
    mid = (a[0] + b[0]) / 2
    return ('<g class="%s"><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<text x="%.2f" y="%.2f" text-anchor="middle">%s</text></g>'
            % (cls, a[0], a[1], b[0], b[1], a[0], a[1] - 4, a[0], a[1] + 4,
               b[0], b[1] - 4, b[0], b[1] + 4, mid, a[1] + up, label))


def vdim(v, y1, y2, x, label, cls='dim', dx=8):
    a, b = v.p(x, y1), v.p(x, y2)
    mid = (a[1] + b[1]) / 2
    return ('<g class="%s"><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<text x="%.2f" y="%.2f">%s</text></g>'
            % (cls, a[0], a[1], b[0], b[1], a[0] - 4, a[1], a[0] + 4, a[1],
               b[0] - 4, b[1], b[0] + 4, b[1], a[0] + dx, mid + 4, label))


def ndim(v, x1, y1, x2, y2, label, cls='dim', off=10):
    """A dimension between two arbitrary points, with ticks square to the run. For a face at
    45 degrees, measuring horizontally would read the offset times sqrt(2) rather than the
    clearance, so an angled face needs its dimension drawn along its own normal."""
    a, b = v.p(x1, y1), v.p(x2, y2)
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux                      # unit perpendicular, for the end ticks
    tick = 5.0
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return ('<g class="%s"><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
            '<text x="%.2f" y="%.2f" text-anchor="middle">%s</text></g>'
            % (cls, a[0], a[1], b[0], b[1],
               a[0] - px * tick, a[1] - py * tick, a[0] + px * tick, a[1] + py * tick,
               b[0] - px * tick, b[1] - py * tick, b[0] + px * tick, b[1] + py * tick,
               mid[0] + px * off, mid[1] + py * off, label))


def dot(v, x, y, r, cls):
    a = v.p(x, y)
    return '<circle class="%s" cx="%.2f" cy="%.2f" r="%.1f"/>' % (cls, a[0], a[1], r)


def mold(v, cr, cls='oml'):
    pts = []
    for i in range(241):
        y = v.y0 + (v.y1 - v.y0) * i / 240
        if abs(y) >= cr:
            continue
        pts.append((-math.sqrt(cr * cr - y * y), y))
    if len(pts) < 2:
        return ''
    d = ' '.join('%s%.3f %.3f' % ('M' if i == 0 else 'L', *v.p(x, y))
                 for i, (x, y) in enumerate(pts))
    return '<path class="%s" d="%s"/>' % (cls, d)


def svg(v, body, cid):
    return ('<div class="scroller"><svg class="sheet" viewBox="0 0 %.0f %.0f" role="img"\n'
            'preserveAspectRatio="xMidYMid meet">'
            '<defs><clipPath id="%s"><rect x="0" y="0" width="%.0f" height="%.0f"/>'
            '</clipPath></defs><g clip-path="url(#%s)">%s</g></svg></div>'
            % (v.px, v.py, cid, v.px, v.py, cid, body))


def crossing(D):
    cr, r = D['params']['corner_radius'], D['flange_r']
    return -math.sqrt(max(cr * cr - r * r, 0.0))


def panel(D):
    """The panel envelope. There is no panel solid anywhere in the project, so where the panel
    sits inside the corner's rebate is a design statement, not something the geometry fixes.

    The panel is spaced off the flange face by panel_tolerance, so:

        inner  = flange_r + panel_tolerance   = corner_radius - panel_thickness
        outer  = inner + panel_thickness      = corner_radius, flush with the mold line
        edge   = -panel_offset                rebate ends one panel_tolerance inboard of it

    An earlier version of this drawing rested the panel on the flange face and put its outer
    surface one panel_tolerance BELOW the mold line. That was an assumption, and it was wrong:
    the skin finishes flush, and the tolerance is the gap underneath it."""
    p = D['params']
    inner = D['flange_r'] + p['panel_tolerance']
    return {'edge': -p['panel_offset'],
            'pocket_end': -p['panel_offset'] + p['panel_tolerance'],
            'seat': D['flange_r'],
            'inner': inner, 'outer': inner + p['panel_thickness']}


def corner_edge(D):
    """Where the corner's material actually ends along the flange face -- whichever of the
    circle and the rectangular extension reaches further out, never past the mask at flat_x.
    Checked against the built corner on cases A, D, E and B."""
    return max(D['flat_x'], min(crossing(D), D['rect_edge']))


def binds(D):
    """Which of the corner's three features is outermost at the flange face."""
    ce = corner_edge(D)
    if abs(ce - D['flat_x']) < 1e-9:
        return 'mask, at flat_x'
    if abs(ce - D['rect_edge']) < 1e-9:
        return 'rectangular extension'
    return 'circle'


def greeble_r(D):
    p = D['params']
    return (p['longeron_radius'] + p['longeron_tolerance']
            + p['greeble_thickness'] + p['greeble_tolerance'])


def flats(D):
    """flat_offset and flat_y, the corner's diagonal face."""
    p = D['params']
    t_long = p['longeron_radius'] + p['longeron_tolerance'] + p['extrusion_width']
    t_panel = (p['panel_overlap'] + p['panel_offset']) - D['flange_r']
    fo = -max(t_long, t_panel)
    return fo, fo - D['flat_x']


def joint_view(D, cid):
    cr, fr = D['params']['corner_radius'], D['flange_r']
    fx, re_ = D['flat_x'], D['rect_edge']
    pn = panel(D)
    fo, fy = flats(D)
    fxt = D.get('flat_x_t', fx)
    fot = D.get('flat_offset_t', fo)
    t = D.get('test_tol', 0.0)
    v = View(min(fx, crossing(D)) - 1.5, -1.5, cr * 1.08, cr * 1.08)
    b = [
        # every view on the plate is at the test value; the corner as built at 0 is the
        # dashed outline underneath it
        fill(v, D.get('corner_fixed', D['corner']), 'fcorner'),
        outline(v, D['corner'], 'wasline'),
        fill(v, D['built'], 'fbody'),
        ('<path class="fpanel" d="%s"/>' % v.wire(
            [(v.x0 - 1, pn['inner']), (pn['edge'], pn['inner']),
             (pn['edge'], pn['outer']), (v.x0 - 1, pn['outer'])])
         ) if pn['outer'] > pn['inner'] else '',
        # the gap UNDER the panel, between the flange face and the panel's inner surface
        vdim(v, pn['seat'], pn['inner'], pn['edge'] - (cr - fr) * .8,
             'panel_tol %.3f, panel stands off' % D['params']['panel_tolerance']),
        # at the rebate wall it describes, not floating in the corner's solid
        hdim(v, pn['edge'], pn['pocket_end'], pn['outer'], 'panel_tol %.3f lateral'
             % D['params']['panel_tolerance'], up=-7),
        txt(v, v.x0 + .4, (pn['inner'] + pn['outer']) / 2, 'panel', 'plbl', dy=4),
        mold(v, cr),
        line(v, v.x0, fr, v.x1, fr, 'nominal'),
        line(v, fx, v.y0, fx, v.y1, 'rule'),
        line(v, re_, v.y0, re_, v.y1, 'rule2'),
        txt(v, v.x0 + .2, fr, 'flange face', 'lbl', dy=-5),
        txt(v, fx, v.y0, 'flat_x', 'lbl', dx=-4, dy=-6, anchor='end'),
        txt(v, re_, v.y0, 'rect_edge', 'lbl', dx=5, dy=-6),
        # the only clearance in this joint, and the face that has none -- both measured
        dot(v, 0, greeble_r(D), 4.5, 'gclr'),
        txt(v, 0, greeble_r(D), 'greeble clearance %.3f' % D['params']['greeble_tolerance'],
            'gclbl', dx=9, dy=-4),
        txt(v, (fx + fo) / 2, fy / 2, 'diagonal face, clear by %.3f' % t,
            'nclbl', dx=-6, dy=15, anchor='end'),
        line(v, fx, fy, fo, 0.0, 'diagline'),
        line(v, fxt, fot - fxt, fot, 0.0, 'toolrule'),
        txt(v, fx, v.y1 - (v.y1 - v.y0) * .05,
            'corner_tolerance %.3f test value; sweep is 0' % t, 'gclbl', dx=6),
    ]
    xc = crossing(D)
    if v.x0 < xc < v.x1:
        b += ['<circle class="xarc" cx="%.2f" cy="%.2f" r="4.5"/>' % v.p(xc, fr),
              txt(v, xc, fr, 'mold line meets it', 'xlbl', dy=-11, anchor='middle')]
    return svg(v, '\n'.join(b), cid)


def junction(D, cid, which):
    """which = 'built' or 'fixed'."""
    cr, fr = D['params']['corner_radius'], D['flange_r']
    fx, re_ = D['flat_x'], D['rect_edge']
    x0 = D['built_x0'] if which == 'built' else D['new_x0']
    rr = D['built_r'] if which == 'built' else D['new_r']
    ce = corner_edge(D)
    pn = panel(D)
    # Size the window so the mold line is actually in it. The arc can sit half a millimeter
    # below the flange face at this x, which a window scaled to the 0.01 mm step cannot reach,
    # so take the arc's depth over the x span and grow the window to match.
    w = 0.42
    lo = min(fx, x0) - w * .22
    for _ in range(2):
        arc_lo = math.sqrt(max(cr * cr - lo * lo, 0.0)) if abs(lo) < cr else fr
        y0 = min(arc_lo, fr) - 0.05
        y1 = fr + 0.12
        w = max(0.42, y1 - y0)
        lo = min(fx, x0) - w * .22
    v = View(lo, y0, lo + w, y1)
    b = [
        # at the test value, like every other view on the plate
        fill(v, D.get('corner_fixed', D['corner']), 'fcorner'),
        outline(v, D['corner'], 'wasline'),
        fill(v, D[which], 'fbody'),
        # the panel's edge is far inboard of this window, so the panel covers all of it
        ('<path class="fpanel" d="%s"/>' % v.wire(
            [(v.x0 - 1, pn['inner']), (v.x1 + 1, pn['inner']),
             (v.x1 + 1, v.y1 + 1), (v.x0 - 1, v.y1 + 1)])
         ) if pn['outer'] > pn['inner'] else '',
        txt(v, v.x0 + (v.x1-v.x0)*.02, fr + (v.y1 - fr) * .5, 'panel sits here', 'plbl'),
        outline(v, D['tool_' + which], 'tool'),
        mold(v, cr),
        line(v, v.x0, fr, v.x1, fr, 'nominal'),
        line(v, fx, v.y0, fx, v.y1, 'rule'),
        line(v, re_, v.y0, re_, v.y1, 'rule2'),
        line(v, x0, v.y0, x0, v.y1, 'toolrule'),
        txt(v, fx, v.y0, 'flat_x', 'lbl', dx=-3, dy=-5, anchor='end'),
        txt(v, re_, v.y0, 'rect_edge', 'lbl', dx=4, dy=-5),
        line(v, D.get('flat_x_t', fx), v.y0, D.get('flat_x_t', fx), v.y1, 'toolrule'),
        hdim(v, fx, D.get('flat_x_t', fx), fr - (fr - v.y0) * .30,
             'corner_tolerance %.3f' % D.get('test_tol', 0.0)),
        hdim(v, fx, re_, fr + (v.y1 - fr) * .72,
             'panel_tolerance %.3f' % D['params']['panel_tolerance'], cls='dim faint'),
        (hdim(v, fx, ce, fr + (v.y1 - fr) * .38, 'step %.4f' % (ce - fx))
         if which == 'built' else
         txt(v, fx, fr + (v.y1 - fr) * .38, 'no step: corner reaches flat_x',
             'xlbl', dx=6)),
    ]
    if which == 'built':
        b += [vdim(v, fr, rr, fx + (v.x1 - fx) * .45, 'eps %.3f' % D['params']['eps']),
              txt(v, v.x1 - .004, fr, 'flange face', 'lbl', dy=-5, anchor='end')]
    else:
        b += [txt(v, v.x1 - .004, fr, 'flange face = clean_r, no eps', 'lbl', dy=-5, anchor='end'),
              txt(v, x0, v.y1, 'clean_x0 = flat_x, unchanged', 'xlbl', dx=4, dy=13)]
    return svg(v, '\n'.join(b), cid)


def tol_view(D, cid):
    """The corner pulled back by corner_tolerance on both mating faces, against the bulkhead
    which is cut at zero. The gap between them IS the tolerance, carried once."""
    cr, fr = D['params']['corner_radius'], D['flange_r']
    fx, fxt = D['flat_x'], D['flat_x_t']
    t = D['test_tol']
    w = max(14.0 * t, 0.30)
    v = View(fx - w * .30, fr - w * .62, fx - w * .30 + w, fr + w * .38)
    b = [
        fill(v, D['corner_fixed'], 'fcorner'),
        fill(v, D['built'], 'fbody'),
        outline(v, D['corner'], 'wasline'),
        mold(v, cr),
        line(v, v.x0, fr, v.x1, fr, 'nominal'),
        line(v, fx, v.y0, fx, v.y1, 'rule'),
        line(v, fxt, v.y0, fxt, v.y1, 'toolrule'),
        txt(v, fx, v.y0, 'flat_x nominal', 'lbl', dx=-3, dy=-5, anchor='end'),
        txt(v, fxt, v.y1, 'corner face', 'xlbl', dx=4, dy=13),
        hdim(v, fx, fxt, fr - w * .22, 'corner_tolerance %.3f' % t),
        txt(v, v.x0 + w * .02, fr + w * .18, 'bulkhead, cut at 0', 'plbl'),
    ]
    return svg(v, '\n'.join(b), cid)


def tol_zoom(D, cid):
    """The same clearance on the DIAGONAL face, zoomed so 0.05 mm is legible. This is the face
    that carries no clearance today and the reason OQ-DES-C5 was raised."""
    fo, fot, t = D['flat_offset'], D['flat_offset_t'], D['test_tol']
    if t <= 0:
        return ('<div class="scroller"><svg class="sheet" viewBox="0 0 430 200" role="img">'
                '<text class="lbl" x="215" y="100" text-anchor="middle">'
                'corner_tolerance is 0 &mdash; no gap</text></svg></div>')
    # Mid-point of the face SEGMENT, from (flat_x, flat_y) to (flat_offset, 0). Not
    # (flat_offset/2, flat_offset/2): that is on the same infinite line but inside the longeron
    # bore, where neither part has material and the view showed nothing.
    fx, fy = D['flat_x'], D['flat_offset'] - D['flat_x']
    mx, my = (fx + fo) / 2.0, fy / 2.0
    w = max(10.0 * t, 0.25)
    v = View(mx - w / 2, my - w / 2, mx + w / 2, my + w / 2)
    b = [
        fill(v, D['corner_fixed'], 'fcorner'),
        fill(v, D['built'], 'fbody'),
        outline(v, D['corner'], 'wasline'),
        line(v, v.x0, fo - v.x0, v.x1, fo - v.x1, 'rule'),
        line(v, v.x0, fot - v.x0, v.x1, fot - v.x1, 'toolrule'),
        txt(v, mx, fo - mx, 'diagonal, nominal', 'lbl', dx=-4, dy=-6, anchor='end'),
        txt(v, mx, fot - mx, 'corner face', 'xlbl', dx=6, dy=12),
        # square to the face: from the nominal diagonal along (1,1)/sqrt(2) by t, which lands
        # on x + y = flat_offset + t*sqrt(2) -- the shifted face
        ndim(v, mx, my, mx + t / 2 ** 0.5, my + t / 2 ** 0.5,
             'corner_tolerance %.3f' % t),
    ]
    return svg(v, '\n'.join(b), cid)


def gain_view(D, cid):
    """Scaled to the change itself, not to the junction: the corner as built against the
    corner with the extension reaching flat_x. On case 3 the difference is 0.0105 mm, which
    is 2% of the junction window and invisible there."""
    cr, fr = D['params']['corner_radius'], D['flange_r']
    fx = D['flat_x']
    step = corner_edge(D) - fx
    if step <= 1e-9 or 'corner_fixed' not in D:
        return ('<div class="scroller"><svg class="sheet" viewBox="0 0 430 200" role="img">'
                '<text class="lbl" x="215" y="100" text-anchor="middle">'
                'nothing gained &mdash; the corner already reached flat_x</text></svg></div>')
    w = max(6.0 * step, 0.03)
    v = View(fx - w * .18, fr - w * .72, fx - w * .18 + w, fr + w * .28)
    b = [
        fill(v, D['corner_fixed'], 'fcorner'),
        outline(v, D['corner'], 'wasline'),
        line(v, v.x0, fr, v.x1, fr, 'nominal'),
        line(v, fx, v.y0, fx, v.y1, 'rule'),
        txt(v, fx, v.y0, 'flat_x', 'lbl', dx=-3, dy=-5, anchor='end'),
        txt(v, v.x1 - w * .01, fr, 'flange face', 'lbl', dy=-5, anchor='end'),
        hdim(v, fx, corner_edge(D), fr - w * .30, 'gained %.4f' % step),
    ]
    return svg(v, '\n'.join(b), cid)


def plate(D, tag, title, sub, note):
    p = D['params']
    xc = crossing(D)
    return '''<figure class="plate" id="case-%s">
  <div class="plate-head">
    <span class="casenum">CASE %s</span>
    <span class="id">%s</span><span class="scale">%s</span></div>
  <div class="views3">
    <div><div class="vlbl">%s.1 &nbsp; the joint, tol 0.05</div>%s</div>
    <div><div class="vlbl">%s.2 &nbsp; junction, tol 0.05</div>%s</div>
    <div><div class="vlbl">%s.3 &nbsp; flat face, close up</div>%s</div>
    <div><div class="vlbl">%s.4 &nbsp; diagonal face, close up</div>%s</div>
  </div>
  <figcaption class="capt">%s</figcaption>
  <div class="scroller"><table class="mini"><tbody>
    <tr><th>flange face</th><td class="num">%.4f</td>
        <th>corner_radius</th><td class="num">%.3f</td>
        <th>panel_thickness</th><td class="num">%.4f</td></tr>
    <tr><th>flat_x</th><td class="num">%.4f</td>
        <th>rect_edge</th><td class="num">%.4f</td>
        <th>mold line crossing</th><td class="num">%.4f</td></tr>
    <tr><th>corner's edge at flange face</th><td class="num">%.4f</td>
        <th>step in the interface</th><td class="num">%.4f</td>
        <th>which feature binds</th><td>%s</td></tr>
    <tr><th>corner volume change</th><td class="num">%+.4f mm&sup3;</td>
        <th>bulkhead volume change</th><td class="num">%+.4f mm&sup3;</td>
        <th>one solid, valid</th><td class="num">%s</td></tr>
  </tbody></table></div>
</figure>''' % (tag, tag, title, sub,
                tag, joint_view(D, 'jv' + tag),
                tag, junction(D, 'jb' + tag, 'built'),
                tag, tol_view(D, 'tv' + tag),
                tag, tol_zoom(D, 'gz' + tag), note,
                D['flange_r'], p['corner_radius'], p['panel_thickness'],
                D['flat_x'], D['rect_edge'], xc,
                corner_edge(D), corner_edge(D) - D['flat_x'], binds(D),
                D.get('cvol_fixed',0) - D.get('cvol_built',0), D['vol_fixed'] - D['vol_built'],
                'yes' if D['ok'] else 'NO')


def _strip_wrapper(fragment):
    """The bare <svg>...</svg> out of the scroller div `svg()` wraps it in."""
    i = fragment.index('<svg')
    j = fragment.rindex('</svg>') + len('</svg>')
    return fragment[i:j]


def _with_css(svg_text, title):
    """Inject the stylesheet and an accessible title into a standalone SVG."""
    head = svg_text[:svg_text.index('>') + 1]
    rest = svg_text[len(head):]
    head = head.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return ('%s<title>%s</title><style>%s</style>%s'
            % (head, title, SVG_CSS, rest))


def write_markdown(cases, doc_dir, img_subdir):
    """The document and its 24 drawings, as files the repo can hold."""
    img_dir = os.path.join(doc_dir, *img_subdir.split('/'))
    os.makedirs(img_dir, exist_ok=True)

    out = [MD_HEAD]
    toc = []
    body = []
    for path, tag, title, sub, note in cases:
        D = json.load(open(path, encoding='utf-8'))
        p = D['params']
        toc.append('- [Case %s — %s](#case-%s)' % (tag, title, tag))
        body.append('\n## Case %s — %s\n' % (tag, title))
        body.append('*%s*\n' % sub.replace('&middot;', '·')
                    .replace('&minus;', '−').replace('&sup3;', '³'))
        body.append('%s\n' % _entities(note))

        views = (joint_view(D, 'jv' + tag), junction(D, 'jb' + tag, 'built'),
                 tol_view(D, 'tv' + tag), tol_zoom(D, 'gz' + tag))
        for n, (frag, vtitle) in enumerate(zip(views, VIEW_TITLES), start=1):
            name = 'case%s.%d.svg' % (tag, n)
            svg_text = _with_css(_strip_wrapper(frag),
                                 'Case %s view %d — %s' % (tag, n, vtitle))
            with open(os.path.join(img_dir, name), 'w', encoding='utf-8',
                      newline='\n') as f:
                f.write(svg_text + '\n')
            body.append('**%s.%d — %s**\n' % (tag, n, vtitle))
            body.append('![Case %s, %s](%s/%s)\n' % (tag, vtitle, img_subdir, name))

        xc = crossing(D)
        body.append('''| | mm | | mm | | mm |
| --- | ---: | --- | ---: | --- | ---: |
| flange face | %.4f | corner_radius | %.3f | panel_thickness | %.4f |
| flat_x | %.4f | rect_edge | %.4f | mold line crossing | %.4f |
| corner's edge at flange face | %.4f | step in the interface | %.4f | which feature binds | %s |
| corner volume change | %+.4f | bulkhead volume change | %+.4f | one solid, valid | %s |
''' % (D['flange_r'], p['corner_radius'], p['panel_thickness'],
       D['flat_x'], D['rect_edge'], xc,
       corner_edge(D), corner_edge(D) - D['flat_x'], binds(D),
       D.get('cvol_fixed', 0) - D.get('cvol_built', 0),
       D['vol_fixed'] - D['vol_built'], 'yes' if D['ok'] else 'NO'))

    out.append('\n'.join(toc) + '\n')
    out.extend(body)
    out.append(MD_TAIL)

    md_path = os.path.join(doc_dir, 'corner_bulkhead_joint.md')
    with open(md_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out))
    return md_path, img_dir, len(cases) * 4


def _entities(s):
    for a, b in (('&middot;', '·'), ('&minus;', '−'), ('&sup3;', '³'),
                 ('&mdash;', '—'), ('&deg;', '°'), ('&half;', '½'),
                 ('<code>', '`'), ('</code>', '`')):
        s = s.replace(a, b)
    return s


MD_HEAD = '''# The corner/bulkhead joint

**Drawn from the built solids, not from the equations.** Each view is traced from geometry
FreeCAD produced, sectioned at mid-bulkhead height in the corner-local frame by
[`measure_corner_joint.py`](../../src/Fuselage/tools/joint_analysis/measure_corner_joint.py)
and drawn by [`draw_corner_joint.py`](../../src/Fuselage/tools/draw_corner_joint.py). That
separation is the whole value of the document: an equation and the solid it is supposed to
produce disagreeing is exactly the defect these drawings were made to find, and they found
one — see [OQ-DES-B13](bulkhead.md) and [OQ-DES-C5](corner.md).

`corner_tolerance` is drawn at a **0.05 mm test value** so the clearance is visible. The
swept value is 0; at 0 the two outlines are coincident and there is nothing to see, which is
the open question C5 records rather than a drafting choice.

## What the six cases are

Six variants chosen to span what the joint does, not six arbitrary samples: the two extremes
of corner size, the no-panel case, the case whose interface carried the defect, and the
family where the `max()` in `flat_offset` is decided by the panel term rather than the
longeron term.

## How to read the views

| View | Shows |
| --- | --- |
| `n.1` | the joint in section — corner, bulkhead, panel envelope, mold line |
| `n.2` | the junction as built, at the same scale |
| `n.3` | the flat face at `flat_x`, close up, with the clearance dimensioned |
| `n.4` | the diagonal face, close up, with the clearance dimensioned **normal to the face** |

The panel is drawn as an envelope, not a solid — **there is no panel solid anywhere in the
project**. Its inner surface stands off the flange face by `panel_tolerance` and its outer
surface lands flush with the mold line at `corner_radius`.

In `n.4` the clearance is measured perpendicular to the 45° face, which is why the parameter
carries a `sqrt(2)` on `flat_offset` and not on `flat_x`: dimension both the same way and
they get different gaps.

'''

MD_TAIL = '''
## Regenerating this

The measured data under
[`joint_analysis/`](../../src/Fuselage/tools/joint_analysis/) is a **snapshot of built
solids**, not a live query. A change to the corner or the bulkhead leaves these drawings
showing the old shape while still looking authoritative, so re-measure before redrawing:

```
uv run python src/Fuselage/tools/draw_corner_joint.py
```

## See also

- [corner.md](corner.md) — OQ-DES-C5, the clearance these drawings dimension.
- [bulkhead.md](bulkhead.md) — OQ-DES-B13, the defect they found.
'''


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--cases', default=os.path.join(DATA_DIR, 'cases.json'))
    ap.add_argument('--doc-dir', default=DOC_DIR)
    ap.add_argument('--html', help='also write the single-page HTML build here')
    ap.add_argument('--template', help='HTML template, required with --html')
    args = ap.parse_args([a for a in argv if not a.endswith('.py')])

    index = json.load(open(args.cases, encoding='utf-8'))
    cases = [(os.path.join(os.path.dirname(os.path.abspath(args.cases)), f),
              t, ttl, sub, note) for f, t, ttl, sub, note in index]

    md, img_dir, n = write_markdown(cases, args.doc_dir, IMG_SUBDIR)
    print('wrote %s' % md)
    print('wrote %d SVG(s) -> %s' % (n, img_dir))

    if args.html:
        if not args.template:
            ap.error('--html needs --template')
        plates = '\n'.join(plate(json.load(open(f, encoding='utf-8')), t, ttl, sub, note)
                           for f, t, ttl, sub, note in cases)
        tpl = open(args.template, encoding='utf-8').read()
        open(args.html, 'w', encoding='utf-8', newline='').write(
            tpl.replace('<!--PLATES-->', plates))
        print('wrote %s' % args.html)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
