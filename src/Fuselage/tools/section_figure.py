"""Draw a 2-D section of real CAD geometry as an SVG, to scale, with what was measured on it.

**Why this exists, and why it is not a screenshot.** The figures this project already has under
`doc/design/img/` are viewport captures of solids, which is the right instrument for "is the wall
severed" or "where are the ribs". It is the wrong instrument for a question about a *distance*: a
raster view of two nearly-touching boundaries at 0.6 mm separation, inside a part 400 mm across,
shows one line. OQ-DES-CW25 asks which face of a cutting tool carries a measured minimum, and that
is a question about a few tenths of a millimeter on a specific face of a specific slab. It needs a
drawing with a known scale, the measured segment drawn where it was actually taken, and the faces
labeled by what they bound.

**Why SVG, and why no plotting library.** A section is polylines, points and text, so the output is
a few hundred lines of markup and needs nothing installed -- which matters because this repository's
Python is deliberately not FreeCAD's and not OpenVSP's, and a figure in the design documentation
should not be the thing that adds a dependency to it. SVG also keeps the geometry exact and
inspectable: the coordinates in the file are the model's own, transformed once by a similarity, so a
reader can measure the drawing and get the part back.

**This module never computes geometry.** It receives coordinate arrays and annotations that a
FreeCAD-side driver extracted from a real build, and turns them into markup. That split is what lets
it be unit-tested without FreeCAD, and it is the same split `wall_measure` uses: the kernel produces
sections, the library reasons about them.

The units are millimeters throughout, and `scale` is px/mm. Model `y` grows up and SVG `y` grows
down, so `_project` flips it; that flip is the only coordinate subtlety here and it is tested.
"""
import math

#: Stroke widths in px, independent of `scale` so a zoomed inset does not draw fatter lines.
WIDTH_GEOMETRY = 1.6
WIDTH_TOOL = 1.4
WIDTH_MEASURE = 1.4
WIDTH_HAIRLINE = 0.7

#: Figure padding in px, outside the fitted geometry window.
PAD_PX = 54.0

#: Radius in px of a marked point.
DOT_PX = 3.0

#: Text sizes in px.
FONT_LABEL = 12.0
FONT_TITLE = 14.0
FONT_SMALL = 10.5

#: Role colors. Deliberately not a rainbow: the whole point of OQ-DES-CW25 is that one role
#: (`floor`) bounds the wall and the others do not, so `floor` is the only saturated color and
#: everything else is a grey or a muted tone.
ROLE_STYLE = {
    'floor': dict(stroke='#c2410c', width=2.6, label='floor - bounds the wall'),
    'cheek': dict(stroke='#1d4ed8', width=1.8, label='cheek - bounds the rib, not the wall'),
    'end': dict(stroke='#6b7280', width=1.4, label='end - bounds the slot run'),
    'outer': dict(stroke='#9ca3af', width=1.2, label='outer - outside the blank, bounds nothing'),
}

#: The interior candidate surface's own section.
SURFACE_STROKE = '#0f766e'
#: The dilated tool, which is what the metric actually measures against.
DILATED_STROKE = '#7c3aed'
#: Engagement shading, keyed by `clearance_face_scan`'s own three states.
ENGAGEMENT_FILL = {
    'clear': '#16a34a',
    'crossing': '#d97706',
    'engulfed': '#dc2626',
}


def _esc(text):
    """XML-escape a caption. Section labels carry `<`, `>` and `&` often enough to matter."""
    return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def _fmt(value):
    """Trim a float to a short, stable decimal so two runs give byte-identical markup."""
    out = '%.3f' % float(value)
    if out.endswith('.000'):
        return out[:-4]
    return out.rstrip('0').rstrip('.') if '.' in out else out


def _mm(value):
    """A length with units, written at a precision the magnitude justifies.

    A 0.0785 mm dilation chord and a 20 mm part cannot share a format string: "0.079 mm" is
    right for one and "20.000 mm" is noise for the other. Below 1 micron the figure switches to
    nanometers, because several of these readings are tens of nanometers and "0.000081 mm" is
    a number most readers have to count the zeros in.
    """
    v = abs(float(value))
    if v < 1.0e-3:
        return '%.0f nm' % (float(value) * 1.0e6)
    if v < 1.0:
        return '%.3f mm' % float(value)
    if v < 10.0:
        return '%.2f mm' % float(value)
    return '%.4g mm' % float(value)


def nice_length(span, fraction=0.2):
    """A round length near `span * fraction`, from the 1-2-5 series, for a scale bar.

    A bar labeled "11 mm" is a bar nobody reads off. The series is the one drafting and chart
    axes both use, and the result is always strictly positive so a scale bar can never collapse.
    """
    target = abs(float(span)) * float(fraction)
    if target <= 0.0:
        return 1.0
    exp = math.floor(math.log10(target))
    base = target / (10.0 ** exp)
    for step in (1.0, 2.0, 5.0, 10.0):
        if base <= step:
            return step * (10.0 ** exp)
    return 10.0 ** (exp + 1)


class Window(object):
    """The model-space rectangle a figure draws, and the similarity that maps it to px.

    Built either from geometry (`fit`) or from an explicit center and width (`around`), which is
    what a zoom inset needs: an inset has to be able to say "80 microns across, centered on the
    contact" without reference to how big the rest of the part is.
    """

    def __init__(self, x_lo, y_lo, x_hi, y_hi, scale, pad=PAD_PX,
                 pad_top=None, pad_bottom=None):
        """`pad_top` and `pad_bottom` reserve bands the geometry never enters.

        The legend and the title have to go somewhere, and over the drawing is the wrong
        somewhere: the first version of this put the legend at the top left of the frame, which
        is exactly where the cutting tool enters the part, so the two overlapped on every figure
        that mattered. Reserving the band moves the geometry down instead of moving the text
        around, which keeps the drawing itself to scale and uncluttered.
        """
        if not (x_hi > x_lo and y_hi > y_lo):
            raise ValueError('a window needs positive extent, got x %r..%r y %r..%r'
                             % (x_lo, x_hi, y_lo, y_hi))
        if not scale > 0.0:
            raise ValueError('scale must be positive px/mm, got %r' % (scale,))
        self.x_lo, self.y_lo, self.x_hi, self.y_hi = (float(x_lo), float(y_lo),
                                                      float(x_hi), float(y_hi))
        self.scale = float(scale)
        self.pad = float(pad)
        self.pad_top = float(pad if pad_top is None else pad_top)
        self.pad_bottom = float(pad if pad_bottom is None else pad_bottom)

    @classmethod
    def fit(cls, polylines, scale=None, width_px=760.0, margin=0.08, pad=PAD_PX,
            pad_top=None, pad_bottom=None):
        """Window the bounding box of every point in `polylines`, with a relative margin.

        With `scale` given the drawing is at that px/mm; otherwise the scale is chosen so the
        window is `width_px` wide, which is how a figure is made to fit a documentation page.
        """
        pts = [p for poly in polylines for p in poly]
        if not pts:
            raise ValueError('cannot fit a window to no points')
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x_lo, x_hi, y_lo, y_hi = min(xs), max(xs), min(ys), max(ys)
        span = max(x_hi - x_lo, y_hi - y_lo)
        if span <= 0.0:
            span = 1.0
        grow = span * float(margin)
        x_lo, x_hi = x_lo - grow, x_hi + grow
        y_lo, y_hi = y_lo - grow, y_hi + grow
        if scale is None:
            scale = float(width_px) / (x_hi - x_lo)
        return cls(x_lo, y_lo, x_hi, y_hi, scale, pad, pad_top, pad_bottom)

    @classmethod
    def around(cls, center, width_mm, scale=None, width_px=300.0, pad=PAD_PX,
               height_mm=None, pad_top=None, pad_bottom=None):
        """A window `width_mm` across centered on `center`, square unless `height_mm` is given."""
        half = float(width_mm) / 2.0
        if half <= 0.0:
            raise ValueError('width_mm must be positive, got %r' % (width_mm,))
        half_y = half if height_mm is None else float(height_mm) / 2.0
        if half_y <= 0.0:
            raise ValueError('height_mm must be positive, got %r' % (height_mm,))
        if scale is None:
            scale = float(width_px) / float(width_mm)
        return cls(center[0] - half, center[1] - half_y,
                   center[0] + half, center[1] + half_y, scale, pad, pad_top, pad_bottom)

    @property
    def size_px(self):
        return ((self.x_hi - self.x_lo) * self.scale + 2.0 * self.pad,
                (self.y_hi - self.y_lo) * self.scale + self.pad_top + self.pad_bottom)

    def project(self, point):
        """Model (x, y) in mm to SVG (x, y) in px. Model y grows up, SVG y grows down."""
        return (self.pad + (float(point[0]) - self.x_lo) * self.scale,
                self.pad_top + (self.y_hi - float(point[1])) * self.scale)

    def contains(self, point, slack=0.0):
        return (self.x_lo - slack <= point[0] <= self.x_hi + slack
                and self.y_lo - slack <= point[1] <= self.y_hi + slack)


class SectionFigure(object):
    """An SVG figure of one station's section. Build it by adding layers, then `render`."""

    def __init__(self, window, title=None, subtitle=None, background='#ffffff'):
        self.window = window
        self.title = title
        self.subtitle = subtitle
        self.background = background
        self._body = []
        self._legend = []

    # -- primitives ----------------------------------------------------------------

    def _path(self, polyline, closed):
        pts = [self.window.project(p) for p in polyline]
        if not pts:
            return None
        head = 'M %s %s' % (_fmt(pts[0][0]), _fmt(pts[0][1]))
        rest = ' '.join('L %s %s' % (_fmt(x), _fmt(y)) for x, y in pts[1:])
        return (head + ' ' + rest + (' Z' if closed else '')).strip()

    def polyline(self, points, stroke='#000000', width=WIDTH_GEOMETRY, closed=False,
                 fill='none', dash=None, opacity=None, label=None):
        """Draw one polyline. `label` adds a legend row with this style."""
        d = self._path(points, closed)
        if d is None:
            return self
        bits = ['d="%s"' % d, 'fill="%s"' % fill, 'stroke="%s"' % stroke,
                'stroke-width="%s"' % _fmt(width), 'stroke-linejoin="round"',
                'stroke-linecap="round"']
        if dash:
            bits.append('stroke-dasharray="%s"' % dash)
        if opacity is not None:
            bits.append('opacity="%s"' % _fmt(opacity))
        self._body.append('  <path %s/>' % ' '.join(bits))
        if label:
            self._legend.append((label, stroke, width, dash))
        return self

    def dot(self, point, fill='#000000', r=DOT_PX, stroke='#ffffff', width=1.0):
        x, y = self.window.project(point)
        self._body.append(
            '  <circle cx="%s" cy="%s" r="%s" fill="%s" stroke="%s" stroke-width="%s"/>'
            % (_fmt(x), _fmt(y), _fmt(r), fill, stroke, _fmt(width)))
        return self

    def text(self, point, body, size=FONT_LABEL, fill='#111827', anchor='start',
             px_offset=(0.0, 0.0), weight=None, italic=False):
        x, y = self.window.project(point)
        bits = ['x="%s"' % _fmt(x + px_offset[0]), 'y="%s"' % _fmt(y + px_offset[1]),
                'font-size="%s"' % _fmt(size), 'fill="%s"' % fill,
                'text-anchor="%s"' % anchor,
                'font-family="DejaVu Sans, Helvetica, Arial, sans-serif"']
        if weight:
            bits.append('font-weight="%s"' % weight)
        if italic:
            bits.append('font-style="italic"')
        self._body.append('  <text %s>%s</text>' % (' '.join(bits), _esc(body)))
        return self

    def text_px(self, xy, body, size=FONT_LABEL, fill='#111827', anchor='start',
                weight=None, italic=False):
        """Text placed in px, for captions that belong to the sheet rather than the geometry."""
        bits = ['x="%s"' % _fmt(xy[0]), 'y="%s"' % _fmt(xy[1]),
                'font-size="%s"' % _fmt(size), 'fill="%s"' % fill,
                'text-anchor="%s"' % anchor,
                'font-family="DejaVu Sans, Helvetica, Arial, sans-serif"']
        if weight:
            bits.append('font-weight="%s"' % weight)
        if italic:
            bits.append('font-style="italic"')
        self._body.append('  <text %s>%s</text>' % (' '.join(bits), _esc(body)))
        return self

    # -- composites ----------------------------------------------------------------

    def measure(self, p_from, p_to, body=None, stroke='#111827', lead_mm=None,
                side=1.0, size=FONT_LABEL):
        """Draw the measured segment itself, with a leader out to a readable caption.

        The segment is drawn where the measurement was taken. The caption cannot go there -- at
        these magnitudes the two boundaries are a pixel or two apart -- so it is led out along the
        segment's own perpendicular, which keeps the association unambiguous without a bounding
        box. `lead_mm` defaults to a tenth of the window, so an inset leads out proportionally.
        """
        if lead_mm is None:
            lead_mm = 0.10 * (self.window.x_hi - self.window.x_lo)
        dx, dy = p_to[0] - p_from[0], p_to[1] - p_from[1]
        length = math.hypot(dx, dy)
        if length > 0.0:
            nx, ny = -dy / length, dx / length
        else:                                     # a zero-length measure is a crossing: lead up
            nx, ny = 0.0, 1.0
        mid = ((p_from[0] + p_to[0]) / 2.0, (p_from[1] + p_to[1]) / 2.0)
        tip = (mid[0] + nx * lead_mm * side, mid[1] + ny * lead_mm * side)
        self.polyline([p_from, p_to], stroke=stroke, width=WIDTH_MEASURE)
        self.polyline([mid, tip], stroke=stroke, width=WIDTH_HAIRLINE, dash='3 2')
        self.dot(p_from, fill=stroke, r=DOT_PX * 0.8)
        self.dot(p_to, fill=stroke, r=DOT_PX * 0.8)
        if body:
            up = tip[1] >= mid[1]
            self.text(tip, body, size=size, fill=stroke,
                      anchor='middle' if abs(nx) < 0.5 else ('start' if nx > 0 else 'end'),
                      px_offset=(0.0, -5.0 if up else 13.0), weight='bold')
        return self

    def scale_bar(self, length_mm=None, body=None, margin_px=14.0, stroke='#111827'):
        """A bar of known model length, so the drawing can be measured back to the part.

        Placed inside the drawing area rather than in the bottom band, which is the title's.
        With no length given it picks a round one off the window's own width.
        """
        if length_mm is None:
            length_mm = nice_length(self.window.x_hi - self.window.x_lo)
        w_px, _ = self.window.size_px
        draw_bottom = self.window.pad_top + (self.window.y_hi - self.window.y_lo) \
            * self.window.scale
        x1 = w_px - self.window.pad - margin_px
        x0 = x1 - length_mm * self.window.scale
        y = draw_bottom - margin_px
        self._body.append(
            '  <path d="M %s %s L %s %s" stroke="%s" stroke-width="%s" fill="none"/>'
            % (_fmt(x0), _fmt(y), _fmt(x1), _fmt(y), stroke, _fmt(WIDTH_MEASURE)))
        for x in (x0, x1):
            self._body.append(
                '  <path d="M %s %s L %s %s" stroke="%s" stroke-width="%s"/>'
                % (_fmt(x), _fmt(y - 4.0), _fmt(x), _fmt(y + 4.0), stroke, _fmt(WIDTH_HAIRLINE)))
        self.text_px((x1, y - 7.0), body or _mm(length_mm),
                     size=FONT_SMALL, anchor='end', fill=stroke)
        return self

    def legend(self, origin_px=(14.0, 20.0), line_px=15.0, swatch_px=22.0, extra=()):
        """Rows for every labeled layer, in the order they were added, then `extra` text rows."""
        x, y = origin_px
        for i, (label, stroke, width, dash) in enumerate(self._legend):
            yy = y + i * line_px
            bits = ['d="M %s %s L %s %s"' % (_fmt(x), _fmt(yy), _fmt(x + swatch_px), _fmt(yy)),
                    'stroke="%s"' % stroke, 'stroke-width="%s"' % _fmt(width), 'fill="none"']
            if dash:
                bits.append('stroke-dasharray="%s"' % dash)
            self._body.append('  <path %s/>' % ' '.join(bits))
            self.text_px((x + swatch_px + 7.0, yy + 3.6), label, size=FONT_SMALL)
        base = y + len(self._legend) * line_px
        for j, row in enumerate(extra):
            self.text_px((x, base + j * line_px + 3.6), row, size=FONT_SMALL, fill='#374151')
        return self

    def frame(self, stroke='#d1d5db'):
        w_px, h_px = self.window.size_px
        self._body.append(
            '  <rect x="0.5" y="0.5" width="%s" height="%s" fill="none" stroke="%s" '
            'stroke-width="1"/>' % (_fmt(w_px - 1.0), _fmt(h_px - 1.0), stroke))
        return self

    # -- output --------------------------------------------------------------------

    def render(self):
        w_px, h_px = self.window.size_px
        head = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" '
                'viewBox="0 0 %s %s" role="img">'
                % (_fmt(w_px), _fmt(h_px), _fmt(w_px), _fmt(h_px))]
        if self.title:
            head.append('  <title>%s</title>' % _esc(self.title))
        if self.subtitle:
            head.append('  <desc>%s</desc>' % _esc(self.subtitle))
        head.append('  <rect width="100%%" height="100%%" fill="%s"/>' % self.background)
        tail = []
        if self.title:
            tail.append('  <text x="%s" y="%s" font-size="%s" font-weight="bold" fill="#111827" '
                        'font-family="DejaVu Sans, Helvetica, Arial, sans-serif">%s</text>'
                        % (_fmt(14.0), _fmt(h_px - 30.0), _fmt(FONT_TITLE), _esc(self.title)))
        if self.subtitle:
            tail.append('  <text x="%s" y="%s" font-size="%s" fill="#4b5563" '
                        'font-family="DejaVu Sans, Helvetica, Arial, sans-serif">%s</text>'
                        % (_fmt(14.0), _fmt(h_px - 14.0), _fmt(FONT_SMALL), _esc(self.subtitle)))
        return '\n'.join(head + self._body + tail + ['</svg>', ''])

    def write(self, path):
        import io as _io
        with _io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(self.render())
        return path


def role_polylines(edges):
    """Group role-tagged edges into one list of polylines per role.

    `edges` is what the driver exports: one entry per edge of the **undilated** tool's section,
    each `dict(role=..., points=[(x, y), ...])`. Grouping by role rather than drawing per edge is
    what makes the legend four rows instead of eight.
    """
    out = {}
    for edge in edges:
        out.setdefault(edge['role'], []).append(list(edge['points']))
    return out


def draw_clearance_station(record, surface, dilated, raw_edges, window=None,
                           title=None, subtitle=None, width_px=760.0, annotate=True,
                           pad_top=None, pad_bottom=None):
    """The section 6.3 figure for one station of `clearance_face_scan`'s output.

    `record` is one row of that scan. `surface` and `dilated` are lists of closed section
    polylines for the interior candidate and the dilated tool. `raw_edges` is the undilated
    tool's section as role-tagged edges. Everything is in millimeters, in the model's own frame.

    **Only roles with geometry in the window get a legend row.** A buttress tool's `outer` face
    sits a hundred millimeters away from the contact, so listing it on a 2 mm drawing promises a
    color that is not there -- which is worse than omitting it, because a reader then goes
    looking. `annotate=False` draws the measured segment without its caption, for a figure whose
    scale makes a micron-level number meaningless.
    """
    polys = list(surface) + list(dilated) + [e['points'] for e in raw_edges]
    win = window or Window.fit(polys, width_px=width_px,
                               pad_top=pad_top, pad_bottom=pad_bottom)
    fig = SectionFigure(win, title=title, subtitle=subtitle)

    engagement = record.get('engagement')
    for poly in surface:
        fig.polyline(poly, stroke=SURFACE_STROKE, width=WIDTH_GEOMETRY, closed=True,
                     fill=SURFACE_STROKE, opacity=0.07)
    for i, poly in enumerate(surface):
        fig.polyline(poly, stroke=SURFACE_STROKE, width=WIDTH_GEOMETRY, closed=True,
                     label='interior candidate surface (the wall\'s inner face)'
                           if i == 0 else None)
    for i, poly in enumerate(dilated):
        fig.polyline(poly, stroke=DILATED_STROKE, width=WIDTH_TOOL, closed=True, dash='5 3',
                     label='tool dilated by t - Metric A measures to THIS' if i == 0 else None)
    for role, polylines in sorted(role_polylines(raw_edges).items()):
        style = ROLE_STYLE.get(role, dict(stroke='#111827', width=WIDTH_TOOL, label=role))
        visible = any(win.contains(p, slack=0.0) for poly in polylines for p in poly)
        shown = False
        for poly in polylines:
            fig.polyline(poly, stroke=style['stroke'], width=style['width'],
                         label=(style['label'] if (visible and not shown) else None))
            shown = shown or visible

    p_surf, p_tool = record.get('p_surf'), record.get('p_tool')
    if p_surf and p_tool:
        color = ENGAGEMENT_FILL.get(engagement, '#111827')
        body = ('Metric A = %s' % _mm(float(record['metric_a']))) if annotate else None
        fig.measure(p_tool[:2], p_surf[:2], body=body, stroke=color)
    return fig
