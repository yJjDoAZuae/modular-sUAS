"""Diagrams for OQ-ARCH-13 -- the flange chamfer, shown on the bulkhead it belongs to.

OQ-ARCH-13 asks whether the flange chamfer belongs in the same piece of work as the bulkhead's
four rounded corners. A reader cannot judge that without seeing what the feature is and where it
sits, so both are drawn, traced from the assembled part rather than sketched.

    where       the whole bulkhead in plan, with the chamfer's run marked on it and the
                cutting plane of the next figure shown
    section     the flange sawn through square, with the chamfer picked out in the profile
    rounded     one of the four rounded corners, and the two surfaces it has to touch

The first two read a snapshot written by `chamfer_analysis/measure_chamfer_context.py`; re-run
that if the bulkhead moves, or these will keep showing the old shape while still looking
authoritative. The third is drawn from the parameter derivation, which is right for it: that
feature's position *is* arithmetic.

    uv run python src/Fuselage/tools/draw_flange_chamfer.py

writes SVGs into doc/architecture/img/flange_chamfer/.

Every figure is checked for overlapping labels before it is written, and the run exits non-zero
if any are found. An earlier version of these drawings shipped with its text piled on top of
itself: a viewBox check does not catch that, because labels can sit well inside the frame and
still be unreadable.
"""
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fuselage_variants as fv  # noqa: E402
from draw_bolt_flange_fillet import (  # noqa: E402
    View, circle, dot, hdim, line, poly, svg, txt, vdim, xml_safe)

DOC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'doc', 'architecture'))
IMG_SUBDIR = os.path.join('img', 'flange_chamfer')
SNAPSHOT = os.path.join(HERE, 'chamfer_analysis', 'context_U1.0_end_bolt_3_16in.json')
SQ2 = math.sqrt(2.0)

# 10px monospace: advance per character, and how far glyphs reach above and below the
# baseline. Only used to find labels that collide, so approximate is fine.
CH_W, ASCENT, DESCENT = 6.0, 8.0, 2.5


TOKEN = re.compile(r'<g\b[^>]*>|</g>|<text\b[^>]*>[^<]*</text>')
TRANSLATE = re.compile(r'translate\(\s*(-?[\d.]+)[\s,]+(-?[\d.]+)\s*\)')
CLIP_DEF = re.compile(
    r'<clipPath\s+id="([^"]+)"\s*>\s*<rect\b([^>]*)/>', re.S)
CLIP_USE = re.compile(r'clip-path="url\(#([^)]+)\)"')
BIG = 1e9


def _clip_rects(svg_text):
    """id -> (x, y, w, h) for every clipPath the drawing defines."""
    out = {}
    for m in CLIP_DEF.finditer(svg_text):
        attrs = {}
        for a in ('x', 'y', 'width', 'height'):
            v = re.search(r'\b%s="(-?[\d.]+)"' % a, m.group(2))
            attrs[a] = float(v.group(1)) if v else 0.0
        out[m.group(1)] = (attrs['x'], attrs['y'], attrs['width'], attrs['height'])
    return out


def label_boxes(svg_text):
    """Every label's box and the region it may occupy, as (x0, y0, x1, y1, text, clip).

    Two things a naive read of the `<text>` elements gets wrong, and both have shipped an
    unreadable figure at least once.

    A multi-panel figure puts each panel in a `<g transform="translate(...)">`, so two panels
    can carry the same label at the same local coordinates and still be drawn far apart. Read
    naively that looks like every panel colliding with every other -- a false alarm loud
    enough to train the reader to ignore the check.

    A panel is also usually clipped to its own rectangle, so a label can sit well inside the
    drawing and still be cut in half by the edge of the panel it belongs to. `clip` is the
    region actually available to that label, which is every enclosing clipPath intersected;
    checking against the viewBox alone misses this entirely.
    """
    clips = _clip_rects(svg_text)
    out = []
    stack = [(0.0, 0.0, (-BIG, -BIG, BIG, BIG))]
    for m in TOKEN.finditer(svg_text):
        tag = m.group(0)
        if tag == '</g>':
            if len(stack) > 1:
                stack.pop()
            continue
        if tag.startswith('<g'):
            ox, oy, clip = stack[-1]
            t = TRANSLATE.search(tag)
            if t:
                ox, oy = ox + float(t.group(1)), oy + float(t.group(2))
            u = CLIP_USE.search(tag)
            if u and u.group(1) in clips:
                cx, cy, cw, ch = clips[u.group(1)]
                clip = (max(clip[0], cx + ox), max(clip[1], cy + oy),
                        min(clip[2], cx + ox + cw), min(clip[3], cy + oy + ch))
            stack.append((ox, oy, clip))
            continue
        a = re.search(r'\bx="(-?[\d.]+)"', tag)
        c = re.search(r'\by="(-?[\d.]+)"', tag)
        s = tag[tag.index('>') + 1:tag.rindex('<')]
        if not (a and c and s.strip()):
            continue
        ox, oy, clip = stack[-1]
        x, y = float(a.group(1)) + ox, float(c.group(1)) + oy
        am = re.search(r'text-anchor="(\w+)"', tag)
        anchor = am.group(1) if am else 'start'
        w = len(s) * CH_W
        x0 = x if anchor == 'start' else (x - w / 2 if anchor == 'middle' else x - w)
        out.append((x0, y - ASCENT, x0 + w, y + DESCENT, s, clip))
    return out


def overlaps(svg_text):
    """Pairs of labels whose boxes intersect."""
    boxes = label_boxes(svg_text)
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                bad.append((a[4], b[4]))
    return bad


def off_frame(svg_text):
    """Labels cut off in the rendered figure -- by the drawing's edge or by their own panel."""
    m = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', svg_text)
    if not m:
        return []
    w, h = float(m.group(1)), float(m.group(2))
    bad = []
    for x0, y0, x1, y1, s, clip in label_boxes(svg_text):
        lo_x, lo_y = max(0.0, clip[0]), max(0.0, clip[1])
        hi_x, hi_y = min(w, clip[2]), min(h, clip[3])
        if x0 < lo_x or y0 < lo_y or x1 > hi_x or y1 > hi_y:
            bad.append(s)
    return bad


def geometry(U=1.0, type_name='end_bolt', panel_name='3/16in'):
    printer = fv.null_printer_settings()
    for params in fv.flatten_param_space(fv.read_all_param_axes(
            fv.axes('panel_variants.csv', 'bulkhead_type_variants.csv',
                    'bulkhead_size_variants.csv'))):
        if (params['U'] != U or params['bulkhead_type_name'] != type_name
                or params['panel_name'] != panel_name):
            continue
        dp = fv.derived_parameters(U, 1.0, params, printer, True)
        return dict(plate=dp.plate.thickness, wall=dp.bulkhead_flange.thickness,
                    bevel=dp.bulkhead_flange.chamfer,
                    radius=dp.bulkhead_flange.fillet_radius,
                    bolt_offset=dp.bolt.offset,
                    boss=dp.bolt.radius + dp.bolt.thickness)
    raise SystemExit('no such variant: U=%s %s %s' % (U, type_name, panel_name))


def bbox(wires):
    xs = [p[0] for w in wires for p in w]
    ys = [p[1] for w in wires for p in w]
    return min(xs), min(ys), max(xs), max(ys)


def fig_where(ctx, cid):
    """The whole bulkhead in plan, with the chamfer's run marked and the saw cut shown."""
    x0, y0, x1, y1 = bbox(ctx['plan'])
    pad = (x1 - x0) * 0.17
    v = View(x0 - pad, y0 - pad * 0.85, x1 + pad, y1 + pad * 1.15, px=440)
    b = ['<path class="fbody" fill-rule="evenodd" d="%s"/>'
         % ' '.join(v.wire(w) for w in ctx['plan'])]

    for w in ctx['run']:
        b.append(poly(v, w, 'fquad'))
    rx0, ry0, rx1, ry1 = bbox(ctx['run'])
    b.append(txt(v, (rx0 + rx1) / 2, ry1, 'the chamfer follows the inside of the flange',
                 dy=-10, anchor='middle'))
    b.append(txt(v, (rx0 + rx1) / 2, ry1, 'right around the part, and turns in to the bolt',
                 dy=2, anchor='middle'))
    # the turn toward the bolt is the part of the run a reader is least likely to expect,
    # so it is marked rather than left to be inferred from the shaded L
    bolt = ctx['params']['corner_offset'] + ctx['params']['bolt_c']
    b.append(dot(v, bolt, bolt, 3.0, '#1c7a54'))
    b.append(txt(v, bolt, ry0, 'to the bolt', dx=-9, dy=13, anchor='end'))

    xc = ctx['section_x']
    b.append(line(v, xc, y0 - pad * 0.6, xc, y1 + pad * 0.55, 'ray'))
    b.append(txt(v, xc, y0 - pad * 0.6, 'sawn through here, for the next figure', dy=-6,
                 anchor='middle'))
    b.append(txt(v, x0 - pad * 0.95, y1 + pad * 0.95,
                 'the whole bulkhead from above, %.0f mm across' % (x1 - x0)))
    return svg(v, ''.join(b), cid, 'where the flange chamfer runs on the bulkhead')


def fig_section(ctx, cid):
    """The flange sawn through square, with the chamfer picked out."""
    P = ctx['params']
    wires = [w for w in ctx['section'] if max(p[0] for p in w) > 0]
    x0, y0, x1, y1 = bbox(wires)
    v = View(x0 - (x1 - x0) * 1.30, y0 - (y1 - y0) * 0.30,
             x1 + (x1 - x0) * 0.30, y1 + (y1 - y0) * 0.34, px=440)
    b = []

    for w in wires:
        b.append(poly(v, w, 'fbody'))
    for w in ctx['piece']:
        b.append(poly(v, w, 'fquad'))

    face, plate = x1, P['plate_thickness']
    bev, wall = P['flange_chamfer'], P['flange_thickness']
    top, inner = plate + bev, face - P['flange_thickness']
    b.append(line(v, inner - bev, plate, inner, top, 'ray'))

    b.append(txt(v, x0, plate, 'the plate, %.1f mm thick' % plate, dx=2, dy=14))
    b.append(txt(v, face, y1, 'the flange, %.1f mm thick,' % wall, dx=-4, dy=-16,
                 anchor='end'))
    b.append(txt(v, face, y1, 'standing %.0f mm up' % (y1 - y0), dx=-4, dy=-5, anchor='end'))
    b.append(txt(v, inner - bev, top, 'the chamfer fills this inside corner,', dx=-8, dy=-14,
                 anchor='end'))
    b.append(txt(v, inner - bev, top, 'at 45&#176;, %.1f mm each way' % bev, dx=-8, dy=-3,
                 anchor='end'))

    b.append(vdim(v, 0, top, x0 - (x1 - x0) * 0.30, '%.1f mm up' % top, dx=-10))
    b.append(hdim(v, inner - bev, face, y0 - (y1 - y0) * 0.16, '%.1f mm in' % (wall + bev)))
    for x, y in ((inner, top), (inner - bev, plate)):
        b.append(dot(v, x, y, 2.6, '#7a5ea8'))
    return svg(v, ''.join(b), cid, 'the flange sawn through, with the chamfer picked out')


def fig_rounded(g, cid):
    """One rounded corner, and the two surfaces it has to touch."""
    r, boss, wall = g['radius'], g['boss'], g['wall']
    bolt = -g['bolt_offset']
    a = r + wall / 2
    tan = math.sqrt((r + boss) ** 2 - a ** 2)
    cx, cy = bolt + (tan - a) / SQ2, bolt + (tan + a) / SQ2

    pad = boss + 2 * r + 3.4
    v = View(bolt - pad, bolt - pad * 0.68, bolt + pad, bolt + pad * 1.12, px=440)
    b = []

    off = wall / 2 / SQ2
    reach = pad * 0.90
    for s in (-1, 1):
        b.append(line(v, bolt + s * off - reach / SQ2, bolt - s * off - reach / SQ2,
                      bolt + s * off + reach / SQ2, bolt - s * off + reach / SQ2, 'edge'))
    b.append(txt(v, bolt - off - reach / SQ2 * 0.74, bolt + off + reach / SQ2 * 0.74,
                 'a wall %.1f mm thick' % wall, dy=-8, anchor='middle'))

    b.append(circle(v, bolt, bolt, boss, 'ring'))
    b.append(txt(v, bolt, bolt - boss, 'the raised boss around a bolt hole', dy=17,
                 anchor='middle'))
    b.append(dot(v, bolt, bolt, 2.6, '#1c7a54'))

    b.append(circle(v, cx, cy, r, 'fquad'))
    b.append(dot(v, cx, cy, 2.8, '#7a5ea8'))
    b.append(txt(v, cx, cy + r, 'a rounded corner, radius %.1f mm' % r, dy=-9,
                 anchor='middle'))

    k = r + boss
    tx, ty = bolt + (cx - bolt) * boss / k, bolt + (cy - bolt) * boss / k
    b.append(dot(v, tx, ty, 3.2, '#b8372a'))
    wx, wy = cx + r / SQ2, cy - r / SQ2
    b.append(dot(v, wx, wy, 3.2, '#b8372a'))
    b.append(txt(v, wx, wy, 'it must touch both;', dx=10, dy=6))
    b.append(txt(v, wx, wy, 'that is what fixes it', dx=10, dy=17))
    return svg(v, ''.join(b), cid, 'a rounded corner and the two surfaces it touches')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--doc-dir', default=DOC_DIR)
    ap.add_argument('--snapshot', default=SNAPSHOT)
    args = ap.parse_args(argv)

    out = os.path.join(args.doc_dir, IMG_SUBDIR)
    os.makedirs(out, exist_ok=True)

    figs = {'rounded_corner': fig_rounded(geometry(), 'rc')}
    if os.path.exists(args.snapshot):
        with open(args.snapshot) as f:
            ctx = json.load(f)
        figs['where'] = fig_where(ctx, 'wh')
        figs['section'] = fig_section(ctx, 'sc')
    else:
        print('no measured snapshot at %s -- the two context figures are skipped.'
              % args.snapshot)
        print('  freecadcmd src/Fuselage/tools/chamfer_analysis/measure_chamfer_context.py \\')
        print('      --pass params.json %s' % args.snapshot)

    bad = 0
    for name, body in sorted(figs.items()):
        clash, cut = overlaps(body), off_frame(body)
        if clash or cut:
            bad += 1
        if clash:
            print('%s: %d overlapping label pair(s)' % (name, len(clash)))
            for a, c in clash[:4]:
                print('    %-46r overlaps %r' % (a[:44], c[:44]))
        for s in cut:
            print('%s: label runs outside the drawing -- %r' % (name, s[:52]))
        inner = body[body.index('<svg'):body.rindex('</svg>') + 6]
        inner = inner.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
        path = os.path.join(out, name + '.svg')
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(xml_safe(inner) + '\n')
        print('wrote %s' % os.path.relpath(path, args.doc_dir))
    if bad:
        print('\n%d figure(s) have unreadable labels -- fix before publishing' % bad)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
