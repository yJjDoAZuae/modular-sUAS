"""What OQ-DES-D7's three prose rows would have to say, drawn.

The question was decided on 2026-08-30 -- every row states the whole size -- and these
figures are what it was decided against, so they stay with the resolution note.

`dimension_scheme.md` section 2's *Governing expression* column does two jobs. Rows 1, 4, 6 and 7
give the whole nominal; rows 2, 3 and 5 give only the clearance, with the nominal it applies to
described in prose. Section 3's completeness test scrapes parameter names out of that column, so
the prose rows demand less than the geometry consumes.

The question is whether to require the whole nominal everywhere. **Answering it means seeing what
"the whole nominal" is**, which is what this draws: one figure per prose row, dimensioning every
term the full expression names, with the terms the register already names distinguished from the
ones it omits.

  * **Row 2**, greeble post to corner socket -- a radial stack-up of four terms, of which the
    register names one.
  * **Row 5**, panel to bulkhead flange -- a face whose POSITION is set by `unit_width` while
    the register's prose names `corner_radius`. That name is owed, but by the face's EXTENT:
    the exposed span consumes it. The row is right by accident.

**Row 3 needs no new drawing.** Its geometry is `flat_offset`, already drawn by
`draw_flat_offset.py`, and its full expression would add no parameter name that
rows 1 and 4 do not already name -- which is the finding, not an omission.

**Diagrams of the definition, not tracings of a built solid**, like `draw_flat_offset.py` and
unlike `draw_corner_joint.py`. Values are at 1U with a 3/16 in panel.

    uv run python src/Fuselage/tools/draw_register_rows.py

Writes `doc/design/img/register_rows/*.svg`. Millimeters throughout.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from draw_flat_offset import SVG_CSS, View, arc, dot, hdim, line, txt, vdim

DOC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'doc', 'design'))
IMG_DIR = os.path.join(DOC_DIR, 'img', 'register_rows')

# One extra rule on top of the shared vocabulary: a term the register already names is drawn
# solid, a term it omits is drawn heavier and in the accent, so the figure answers "what would
# this row gain" at a glance rather than by reading the labels.
EXTRA_CSS = """
.named   { stroke:#5d6f79; stroke-width:1.2; }
.omitted { stroke:#b8372a; stroke-width:2.4; }
text.omit { font-family:monospace; font-size:10.5px; fill:#b8372a; font-weight:700; }
text.name { font-family:monospace; font-size:10.5px; fill:#5d6f79; }
.ring    { fill:none; stroke:#5d6f79; stroke-width:1; stroke-dasharray:3 3; }
@media (prefers-color-scheme: dark) {
  .named { stroke:#8ea3ad; } .omitted { stroke:#ff6f5e; }
  text.omit { fill:#ff6f5e; } text.name { fill:#8ea3ad; }
  .ring { stroke:#8ea3ad; }
}
"""

P = dict(longeron_radius=2.0, longeron_tolerance=0.05, greeble_thickness=1.2,
         greeble_tolerance=0.05, unit_width=100.0, corner_radius=10.0,
         panel_thickness=4.7625, panel_tolerance=0.1, panel_overlap=4.7625,
         panel_offset=2.5)


def wrap(v, body, head, pad_l=104, pad_t=58, pad_r=58, pad_b=42):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" '
            'width="%.0f" height="%.0f"><style>%s%s</style>%s'
            '<g transform="translate(%d,%d)">%s</g></svg>'
            % (v.px + pad_l + pad_r, v.py + pad_t + pad_b,
               v.px + pad_l + pad_r, v.py + pad_t + pad_b,
               SVG_CSS, EXTRA_CSS, head, pad_l, pad_t, ''.join(body)))


def heading(title, sub):
    return ('<text class="ttl" x="10" y="20">%s</text>'
            '<text class="lbl" x="10" y="37">%s</text>') % (title, sub)


def row2():
    """The socket the corner is bored to, as four radial terms."""
    r1 = P['longeron_radius']
    r2 = r1 + P['longeron_tolerance']
    r3 = r2 + P['greeble_thickness']
    r4 = r3 + P['greeble_tolerance']

    v = View(-0.4, -0.4, 4.4, 4.4, px=380)
    b = []

    # the four radii as quarter arcs, largest first so the smaller draw over it
    b.append('<path class="fcorner" d="%s"/>' % v.path(
        [(0, 0)] + [(r4 * math.cos(math.radians(90.0 * i / 90)),
                     r4 * math.sin(math.radians(90.0 * i / 90))) for i in range(91)]))
    b.append('<path class="fpanel" d="%s"/>' % v.path(
        [(0, 0)] + [(r3 * math.cos(math.radians(90.0 * i / 90)),
                     r3 * math.sin(math.radians(90.0 * i / 90))) for i in range(91)]))
    b.append('<path class="fbore" d="%s"/>' % v.path(
        [(0, 0)] + [(r2 * math.cos(math.radians(90.0 * i / 90)),
                     r2 * math.sin(math.radians(90.0 * i / 90))) for i in range(91)]))
    b.append(arc(v, 0, 0, r1, 0, 90, 'ring'))

    b.append(line(v, 0, 0, 4.3, 0, 'axis'))
    b.append(line(v, 0, 0, 0, 4.3, 'axis'))

    # the stack-up along the x axis
    for r in (r1, r2, r3, r4):
        b.append(line(v, r, 0, r, -0.32, 'ext'))
    b.append(hdim(v, 0, r1, 0, 'longeron_radius 2.00', up=30))
    b.append(hdim(v, r1, r2, 0, 'longeron_tolerance 0.05', up=52))
    b.append(hdim(v, r2, r3, 0, 'greeble_thickness 1.20', up=74))
    b.append(hdim(v, r3, r4, 0, 'greeble_tolerance 0.05', up=96))

    b.append(txt(v, 0, r4, 'socket radius %.4f' % r4, 'omit', dx=8, dy=-8))
    b.append(txt(v, 0, r3, 'post, nominal %.2f' % r3, 'plbl', dx=8, dy=16))
    b.append(txt(v, 0, r2, 'bore %.2f' % r2, 'lbl', dx=8, dy=32))

    head = heading(
        'Row 2 &#8212; greeble post &#8594; corner socket',
        'the register names greeble_tolerance; the geometry consumes four terms')
    return wrap(v, b, head, pad_b=126)


def row5():
    """The bulkhead's outer face, set back from the flat mold line by the panel pocket."""
    half = P['unit_width'] / 2.0
    pocket = P['panel_thickness'] + P['panel_tolerance']
    face = half - pocket
    inner = half - P['panel_thickness']
    cx = half - P['corner_radius']
    span = half - (P['corner_radius'] + P['panel_offset']) - P['panel_overlap']

    v = View(-2.0, 36.0, 56.0, 54.0, px=560)
    b = []

    # the panel, lying with its outer face ON the mold line
    b.append('<path class="fpanel" d="%s"/>' % v.path(
        [(0, half), (cx + 2.0, half), (cx + 2.0, inner), (0, inner)]))

    # the bulkhead body below its outer face
    b.append('<path class="fcorner" d="%s"/>' % v.path(
        [(0, face), (span, face), (span, 37.0), (0, 37.0)]))

    # the mold line: flat, then the corner arc
    b.append(line(v, -1.5, half, cx, half, 'oml'))
    b.append(arc(v, cx, cx, P['corner_radius'], 0, 90, 'oml'))
    b.append(dot(v, cx, half, 2.6))

    # datums
    b.append(line(v, -1.5, face, 54.0, face, 'omitted'))
    b.append(line(v, -1.5, inner, cx, inner, 'named'))
    b.append(line(v, 0, 36.5, 0, 53.0, 'axis'))
    b.append(txt(v, 0, 36.5, 'fuselage centerline', 'lbl', dx=4, dy=12))

    b.append(vdim(v, 0.0 + face, half, 52.0, 'pocket %.4f' % pocket, dx=10))
    b.append(vdim(v, inner, half, 44.0, 'panel_thickness 4.7625', dx=10))
    b.append(vdim(v, face, inner, 30.0, 'panel_tolerance 0.10', dx=10))
    b.append(hdim(v, 0, span, face, 'exposed span %.4f (half)' % span, up=34))

    b.append(txt(v, 0, half, 'mold line at unit_width/2 = 50', 'omit', dx=6, dy=-9))
    b.append(txt(v, 8, face, 'bulkhead outer face %.4f' % face, 'omit', dx=0, dy=-7))
    b.append(txt(v, cx, cx + P['corner_radius'], 'corner_radius 10 -- sets the span, not this face', 'name', dx=10, dy=4))
    b.append(txt(v, cx, half, 'tangent: the arc starts here', 'lbl', dx=6, dy=18))

    head = heading(
        'Row 5 &#8212; panel &#8594; bulkhead flange',
        'position uses unit_width, not corner_radius; the span uses corner_radius')
    return wrap(v, b, head, pad_b=76)


def main():
    if not os.path.isdir(IMG_DIR):
        os.makedirs(IMG_DIR)
    for name, fn in (('row2_greeble_socket', row2), ('row5_bulkhead_face', row5)):
        path = os.path.join(IMG_DIR, name + '.svg')
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(fn())
        print('%-22s -> %s' % (name, os.path.relpath(path, DOC_DIR)))

    r4 = (P['longeron_radius'] + P['longeron_tolerance']
          + P['greeble_thickness'] + P['greeble_tolerance'])
    face = P['unit_width'] / 2.0 - P['panel_thickness'] - P['panel_tolerance']
    print('row 2 socket radius %.4f  (documented 3.3000)' % r4)
    print('row 5 outer face    %.4f  (documented 45.1375)' % face)
    return 0


if __name__ == '__main__':
    sys.exit(main())
