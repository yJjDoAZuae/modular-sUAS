"""Diagrams for OQ-ARCH-14 -- the two flange fillets that are still expressed as arithmetic.

OQ-ARCH-13 settled that a feature whose position is *measured* from flat faces does not belong
in the constraint work, while one whose position has to be *worked out* does. Applying that
test to the two fillets still unconverted gives an answer nobody has ruled on, so the evidence
is drawn here.

An earlier version of this file drew each fillet as a circle on an empty page. That was
rejected, correctly: a circle tangent to two lines tells the reader nothing about whether the
feature matters, and one of the two was not drawn at all. So every shape below is traced out
of the assembled bulkhead by `fillet_scope_analysis/measure_fillet_context.py`, and the plan
view exists so a detail can be pointed at the place it came from.

    bulkhead        the whole part, with all four fillets marked and the details located
    outer_corner    the outer corner fillet, in the notch it fills
    greeble_buried  the greeble-to-web fillet, in both branches of its conditional, against
                    the bodies that already occupy the same space

    uv run python src/Fuselage/tools/draw_fillet_scope.py

writes SVGs into doc/architecture/img/fillet_scope/. Labels are checked for overlap and for
running off the drawing, and the run exits non-zero if either happens -- a figure whose text
sits on top of itself is worse than no figure, which is a lesson these drawings have already
had to learn once.

The net volumes quoted in the captions come from `fillet_scope_analysis/sweep_fillet_share.py`
and are restated here as constants rather than recomputed: recomputing them would mean 44
FreeCAD builds every time a label moves.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from draw_bolt_flange_fillet import (  # noqa: E402
    View, arc, bbox, circle, dot, face, hdim, legend, line, poly, rect, svg, svg_raw, tiled,
    txt, vdim, xml_safe)
from draw_flange_chamfer import off_frame, overlaps  # noqa: E402

DOC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'doc', 'architecture'))
IMG_SUBDIR = os.path.join('img', 'fillet_scope')
ANALYSIS = os.path.join(HERE, 'fillet_scope_analysis')

# One variant per branch of `gtw_start = max(flange_inner_x; -bolt_offset)`, chosen for the
# widest separation between the two candidates rather than for convenience. The first pair
# drawn here were U=0.75/0mm and U=0.5/0mm, where `flange_inner_x` is -5.95 against a bolt at
# -6.00 -- a 0.05 mm tie. At that spacing the two candidate references are indistinguishable
# on the page and the fillet is small enough to vanish into the bolt hole, so the figure showed
# a degenerate case and read as an error in the geometry. These two differ by 8.8 mm and
# 2.3 mm, and share a panel, so only `U` flips the branch.
FLANGE_BRANCH = (os.path.join(ANALYSIS, 'context_U3.0_end_bolt_1_8in.json'),
                 'U=3.0 end_bolt 1/8in')
BOLT_BRANCH = (os.path.join(ANALYSIS, 'context_U0.75_end_bolt_1_8in.json'),
               'U=0.75 end_bolt 1/8in')

# From sweep_fillet_share.py over the 44 end_bolt variants, which visit every distinct corner
# geometry. `net` is what the fuse gains by including the fillet at all.
SHARE = {
    'gtw_max_net': 0.04185, 'gtw_inert': 33, 'gtw_n': 44,
    'ocf_min_net': 0.74932, 'ocf_max_net': 163.89858,
    # Absent from the finished part -- cut away wholesale by the bolt hole. This is NOT the
    # general case and the captions must not imply it is: it happens in 5 of the 44, all at
    # U <= 1.0, which happens to include both variants drawn below. From U = 1.5 up the whole
    # body sits inside the part. What holds corpus-wide is `net`, above.
    'gtw_absent': 5, 'gtw_absent_max_u': 1.0, 'gtw_max_in_part': 168.15997,
}

# The section areas of the greeble-to-web fillet, in closed form. Both are multiples of the
# radius squared with no dependence on `flange_thickness`, because the center's y is defined
# relative to the web face, so the ratio below is the same in every variant.
#
#     as built    r^2 (1/sqrt(2) - 1/4 - pi/8)   = 0.064408 r^2
#     the fillet  r^2 (sqrt(2) - 1 - pi/8)       = 0.021515 r^2
#
# The remainder lies below the web face, inside the greeble web.
BUILT_OVER_R2 = 1 / math.sqrt(2) - 0.25 - math.pi / 8
FILLET_OVER_R2 = math.sqrt(2) - 1 - math.pi / 8
FILLET_FRACTION = FILLET_OVER_R2 / BUILT_OVER_R2

# Three classes the shared vocabulary does not have. All four fillets need to be told apart
# from each other, not just the two this question is about: drawn in one color, the pair
# already converted reads as a single pinwheel around the bolt and there is no way to check
# which blade is which.
EXTRA_CSS = """
.focf  { fill:rgba(28,122,84,.30); stroke:#1c7a54; stroke-width:1.4; }
.fgtw  { fill:rgba(184,55,42,.45); stroke:#b8372a; stroke-width:1.4; }
.fwtb  { fill:rgba(168,106,31,.30); stroke:#a86a1f; stroke-width:1.4; }
@media (prefers-color-scheme: dark) {
  .focf { fill:rgba(79,211,155,.30); stroke:#4fd39b; }
  .fgtw { fill:rgba(255,111,94,.45); stroke:#ff6f5e; }
  .fwtb { fill:rgba(224,169,74,.30); stroke:#e0a94a; }
}
"""


def load(path):
    with open(path) as f:
        return json.load(f)


def octant(ctx, level, name):
    """One body's traced faces, in the octant's own frame."""
    return ctx['levels'][level][name]


def section_local(ctx, level):
    """`BulkheadSection` moved back into the octant frame the generator writes in."""
    co = ctx['params']['corner_offset']
    return [[[(x - co, y - co) for x, y in w] for w in f]
            for f in ctx['levels'][level]['BulkheadSection']]


def styled(body):
    return '<style>%s</style>%s' % (EXTRA_CSS, body)


# --------------------------------------------------------------------------- figures

def fig_bulkhead(ctx, label, cid):
    """All four fillets, on the part, with the two detail windows marked.

    Two sections at once: the plate, which is the silhouette, and a cut through the standing
    flange, where the four fillets are separate bodies. Eight copies of each, because the
    bulkhead is eight mirrored copies of one octant.
    """
    P = ctx['params']
    half = P['unit_width'] / 2
    plate = ctx['levels']['plate']['BulkheadFull'][0]
    stand = ctx['levels']['flange']['BulkheadFull'][0]

    v = View(-half * 1.06, -half * 1.34, half * 1.06, half * 1.30, px=520)
    b = [face(v, plate, 'fplate'), face(v, stand, 'fstand')]

    # `...InPart`, not the fillet as built. A fillet is a positive, fused before the bolt hole
    # and the corner socket are cut, so drawing the body itself paints over the finished
    # part's holes and reads as a placement error. What belongs on a plan of the part is what
    # is left in the part.
    groups = [('OuterCornerFillet', 'focf'), ('GreebleToWebFillet', 'fgtw'),
              ('WebToBoltFillet', 'fwtb'), ('BoltFlangeFillet', 'fquad')]
    drawn, gone = {}, []
    for name, cls in groups:
        faces = octant(ctx, 'flange', name + 'InPart')
        if not faces:
            gone.append(name)
            drawn[name] = []
            continue
        wire = faces[0][0]
        drawn[name] = [tiled(wire, P['corner_offset'], *t) for t in ctx['tiling']]
        for c in drawn[name]:
            b.append(poly(v, c, cls))

    # the +x +y corner, which is where both details are cut from
    def window(names, pad):
        pts = [p for n in names if drawn[n]
               for t, c in zip(ctx['tiling'], drawn[n], strict=True)
               if t[1] > 0 and t[2] > 0 for p in c]
        x0, y0, x1, y1 = bbox(pts)
        return x0 - pad, y0 - pad, x1 + pad, y1 + pad

    ax0, ay0, ax1, ay1 = window(['OuterCornerFillet'], half * 0.045)
    b.append(rect(v, ax0, ay0, ax1, ay1, 'zoom'))
    b.append(txt(v, ax0, ay1, 'detail 1', 'gclbl', dx=-7, dy=-4, anchor='end'))

    bx0, by0, bx1, by1 = window(['GreebleToWebFillet', 'WebToBoltFillet',
                                 'BoltFlangeFillet'], half * 0.045)
    b.append(rect(v, bx0, by0, bx1, by1, 'zoom'))
    b.append(txt(v, bx0, by0, 'detail 2', 'gclbl', dx=-7, dy=10, anchor='end'))

    b.append(hdim(v, -half, half, -half * 1.20,
                  'unit_width %.0f mm' % P['unit_width'], up=15))
    rows = [('fplate', 'the plate, z = %.2f mm' % ctx['levels']['plate']['z']),
            ('fstand', 'standing flange and corner bosses, z = %.2f mm'
             % ctx['levels']['flange']['z']),
            ('focf', 'outer corner fillet -- still arithmetic'),
            ('fquad', 'bolt-flange fillet -- converted'),
            ('fwtb', 'web-to-bolt fillet -- converted')]
    # Only true at the smallest sizes, so it is phrased as a fact about this variant. At
    # U >= 1.5 the whole body sits inside the part; what holds everywhere is that it adds
    # nothing the bodies around it do not already supply.
    if 'GreebleToWebFillet' in gone:
        rows.append(('fgtw', 'greeble-to-web fillet -- at this size, cut away by the bolt '
                             'hole'))
    else:
        rows.append(('fgtw', 'greeble-to-web fillet -- still arithmetic'))
    b.append(legend(v.px * 0.145, v.py * 0.350, rows))

    b.append('<text class="ttl" x="8" y="14">the four flange fillets &mdash; %s</text>'
             % label)
    b.append('<text class="lbl" x="8" y="28">what each one leaves in the finished part; '
             'eight copies of each, one per octant</text>')
    b.append('<text class="lbl" x="8" y="%.0f">%.1f mm fillets on a %.0f mm part; the two '
             'details below are at about %.0fx</text>'
             % (v.py - 8, P['flange_fillet_radius'], P['unit_width'],
                P['unit_width'] / (P['flange_fillet_radius'] * 4.2)))
    return svg(v, styled('\n'.join(b)), cid, 'the four flange fillets located on the bulkhead')


def fig_outer_corner(ctx, label, cid):
    """Detail 1: the notch the outer corner fillet fills, and why its center is a subtraction.

    The two faces meeting here are at right angles, so each coordinate of the center is one
    face minus the radius. There is nothing to solve, and no configuration in which no such
    circle exists.

    The material is the octant as finally built, not the flange positive: the positive still
    has the corner block that the negatives hollow out, and drawing that would show the fillet
    buried in material the finished part does not have.
    """
    P = ctx['params']
    r = P['flange_fillet_radius']
    fx, fy = P['flange_inner_x'], P['flange_y']
    cx, cy = P['ocf_cx'], P['ocf_cy']

    span = r * 4.2
    lo_x, lo_y = cx - span * 0.33, cy - span * 0.40
    v = View(lo_x, lo_y, lo_x + span, lo_y + span, px=470)
    b = [face(v, f, 'fbody') for f in section_local(ctx, 'flange')]
    b.append(poly(v, octant(ctx, 'flange', 'OuterCornerFillet')[0][0], 'focf'))

    # only as far as the faces actually run, so the lines read as edges and not as axes
    b.append(line(v, fx, cy - r * 1.2, fx, fy + r * 0.8, 'edge'))
    b.append(line(v, cx - r * 1.3, fy, fx + r * 0.8, fy, 'edge'))
    b.append(dot(v, cx, cy, 3.0, '#7a5ea8'))

    b.append(hdim(v, cx, fx, cy - r * 0.55, 'r %.1f' % r))
    b.append(vdim(v, cy, fy, cx - r * 0.55, 'r %.1f' % r, dx=-30))
    b.append(txt(v, lo_x + span * 0.04, fy, 'flange_y %.2f' % fy, 'plbl', dy=-6))
    b.append(txt(v, fx, cy - r * 1.2, 'flange_inner_x %.2f' % fx, 'plbl',
                 dx=-6, dy=12, anchor='end'))
    b.append(txt(v, cx, cy, 'center (%.2f, %.2f)' % (cx, cy), 'nclbl',
                 dx=-7, dy=14, anchor='end'))
    # in the wall itself, directly above the sliver it names -- a leader from here would have
    # to cross both faces to reach it
    b.append(txt(v, fx - r * 0.3, fy, 'the fillet', 'xlbl', dy=-6, anchor='end'))

    b.append('<text class="ttl" x="8" y="14">detail 1 &mdash; the outer corner fillet, %s</text>'
             % label)
    b.append('<text class="lbl" x="8" y="28">two faces at right angles: each coordinate is '
             'one face minus the radius</text>')
    b.append('<text class="lbl" x="8" y="%.0f">it fills a real notch &mdash; %.2f to %.1f '
             'mm&#179; no other body supplies</text>'
             % (v.py - 8, SHARE['ocf_min_net'], SHARE['ocf_max_net']))
    return svg(v, styled('\n'.join(b)), cid,
               'the outer corner fillet in the notch between two perpendicular flange faces')


# Everything `flange_positive()` fuses except the greeble-to-web fillet itself. The plain
# material is one mass in one class -- which particular body covers the fillet is not the
# question -- but the two converted fillets keep their own colors, so the reader can check
# each of them against the place it is supposed to be rather than against a single blur.
NEIGHBORS = (('FlangeTip', 'fstand'), ('FlangeChamfer', 'fstand'), ('FlangeBoss', 'fstand'),
             ('OuterCornerFillet', 'fstand'), ('GreebleBoltWebTip', 'fstand'),
             ('WebToBoltFillet', 'fwtb'), ('BoltFlangeFillet', 'fquad'))


def _buried_panel(ctx, px, pid, caption):
    """One variant's view of the greeble-to-web fillet, against everything already there.

    Clipped to its own window. Without that the neighboring bodies -- which run the whole
    length of the flange -- draw straight across the next panel, and the two variants become
    impossible to tell apart.
    """
    P = ctx['params']
    gs, fx, bc = P['gtw_start'], P['flange_inner_x'], P['bolt_c']
    r, hole = P['flange_fillet_radius'], P['bolt_hole_radius']
    fillet = octant(ctx, 'flange', 'GreebleToWebFillet')[0][0]

    # The greeble web's outer face, which is the surface the fillet's arc is tangent to at its
    # far end: the 45 degree line y = x + sqrt(2)/2 * flange_thickness, with web material
    # below it. `gtw_ey - gtw_ex` is that offset, read back rather than recomputed.
    web_c = P['gtw_ey'] - P['gtw_ex']

    # tight on the fillet, but still holding both candidate references and the whole bolt hole
    xs = [p[0] for p in fillet] + [gs, fx, bc - hole, bc + hole]
    ys = [p[1] for p in fillet] + [bc - hole, bc + hole]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) + r * 1.3
    lo_x = (min(xs) + max(xs) - span) / 2
    lo_y = (min(ys) + max(ys) - span) / 2
    v = View(lo_x, lo_y, lo_x + span, lo_y + span, px=px)

    b = [face(v, f, 'fplate') for f in section_local(ctx, 'flange')]
    for name, cls in NEIGHBORS:
        for f in octant(ctx, 'flange', name):
            b.append(face(v, f, cls))
    b.append(poly(v, fillet, 'fgtw'))

    # the bolt hole, which is what actually decides this: the fillet is a positive, fused
    # before the hole is drilled, and it lies inside it
    # `zoom`, not `ray`: the line classes carry no `fill`, so a closed path drawn with one
    # comes out as a filled black disc and hides everything the panel is about.
    b.append(circle(v, bc, bc, hole, 'zoom'))
    b.append(dot(v, bc, bc, 3.0, '#1c7a54'))

    # only the quarter the fillet is a piece of: tangent to x = gtw_start at one end and to
    # the web face at the other. The whole circle drawn here dwarfs the sliver it belongs to.
    b.append(arc(v, P['gtw_cx'], P['gtw_cy'], r, -math.pi / 4, 0.0, 'tool'))
    b.append(line(v, lo_x + span * 0.05, lo_x + span * 0.05 + web_c,
                  lo_x + span * 0.95, lo_x + span * 0.95 + web_c, 'edge'))

    # the two candidates the conditional picks between, and which one won
    b.append(line(v, gs, lo_y + span * 0.06, gs, lo_y + span * 0.90, 'edge'))
    if abs(fx - gs) > 1e-9:
        b.append(line(v, fx, lo_y + span * 0.06, fx, lo_y + span * 0.66, 'rule'))
        # to the right of its line, and well below gtw_start's label: this line sits close
        # enough to the panel's left edge that a label ending on it is cut in half
        b.append(txt(v, fx, lo_y + span * 0.66, 'flange_inner_x', 'lbl', dx=4, dy=-4))

    # anchored to the left of the line: in the bolt-center branch the line sits far enough
    # right that a label starting there runs off the panel
    b.append(txt(v, gs, lo_y + span * 0.90, 'x = gtw_start %.2f' % gs, 'plbl', dx=-4, dy=-4,
                 anchor='end'))
    b.append(txt(v, bc, bc - hole, 'bolt hole', 'gclbl', dy=15, anchor='middle'))
    # along the line, well clear of the bolt hole's own label at the other end of it
    b.append(txt(v, lo_x + span * 0.55, lo_x + span * 0.55 + web_c, 'the web face, 45&#176;',
                 'plbl', dx=2, dy=-5))

    fx0 = min(p[0] for p in fillet)
    fym = sum(p[1] for p in fillet) / len(fillet)
    lx, ly = lo_x + span * 0.05, fym + r * 0.45
    b.append(line(v, fx0, fym, lx + span * 0.10, ly, 'rule'))
    b.append(txt(v, lx, ly, 'the fillet', 'gclbl', dy=4))

    body = ('<defs><clipPath id="%s"><rect x="0" y="0" width="%.0f" height="%.0f"/>'
            '</clipPath></defs><g clip-path="url(#%s)">%s</g>'
            '<rect x="0" y="0" width="%.0f" height="%.0f" fill="none" stroke="#9fb0ba" '
            'stroke-width="1"/><text class="lbl" x="0" y="%.0f">%s</text>'
            % (pid, v.px, v.py, pid, '\n'.join(b), v.px, v.py, v.py + 16, caption))
    return v, body


def fig_greeble_buried(a, alabel, c, clabel, cid):
    """Detail 2: the greeble-to-web fillet, in both branches, against the bodies around it.

    Left, the conditional picks the flange's inner face; right, it picks a plane through the
    bolt center. The pair is the whole argument: the reference does switch, and it changes
    almost nothing, because the bodies around it close the same gap either way.
    """
    gap, head, foot = 44, 60, 126
    va, pa = _buried_panel(a, 400, 'pa', 'left: gtw_start = flange_inner_x  (%.2f > %.2f, '
                           'by %.2f mm)'
                           % (a['params']['flange_inner_x'], -a['params']['bolt_offset'],
                              abs(a['params']['flange_inner_x']
                                  + a['params']['bolt_offset'])))
    vb, pb = _buried_panel(c, 400, 'pb', 'right: gtw_start = -bolt_offset  (%.2f > %.2f, '
                           'by %.2f mm)'
                           % (-c['params']['bolt_offset'], c['params']['flange_inner_x'],
                              abs(c['params']['flange_inner_x']
                                  + c['params']['bolt_offset'])))

    px = va.px + vb.px + gap
    py = max(va.py, vb.py) + head + foot
    b = ['<g transform="translate(0 %.1f)">%s</g>' % (head, pa),
         '<g transform="translate(%.1f %.1f)">%s</g>' % (va.px + gap, head, pb)]
    b.append('<text class="ttl" x="0" y="14">detail 2 &mdash; the greeble-to-web fillet, in '
             'both branches of its conditional</text>')
    b.append('<text class="lbl" x="0" y="28">left %s, right %s &mdash; same panel, so only the '
             'size flips the branch; each scaled to its own fillet</text>' % (alabel, clabel))
    b.append('<text class="lbl" x="0" y="42">grey is the finished octant, teal the plain '
             'flange material, purple the bolt-flange fillet, amber the web-to-bolt, red '
             'this one</text>')
    b.append('<text class="lbl" x="0" y="%.0f">the reference switches and it changes nothing: '
             'in both, the bodies around the fillet already supply everything it</text>'
             % (py - foot + 46))
    b.append('<text class="lbl" x="0" y="%.0f">would add &mdash; net zero in %d of the %d '
             'variants measured, at most %.3f mm&#179; in the rest.</text>'
             % (py - foot + 62, SHARE['gtw_inert'], SHARE['gtw_n'], SHARE['gtw_max_net']))
    b.append('<text class="lbl" x="0" y="%.0f">its lower edge is not the web face: the body '
             'is squared off below the tangent point, so %.0f%% of it lies</text>'
             % (py - foot + 82, 100 * (1 - FILLET_FRACTION)))
    b.append('<text class="lbl" x="0" y="%.0f">inside the web &mdash; the same fraction in '
             'every variant. In the right-hand one the bolt hole then removes what is '
             'left,</text>' % (py - foot + 98))
    b.append('<text class="lbl" x="0" y="%.0f">which happens in %d of the %d, all at '
             'U &#8804; %.1f; above that the body stays, as on the left.</text>'
             % (py - foot + 114, SHARE['gtw_absent'], SHARE['gtw_n'],
                SHARE['gtw_absent_max_u']))
    return svg_raw(px, py, styled('\n'.join(b)), cid,
                   'the greeble-to-web fillet among the bodies around it')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--doc-dir', default=DOC_DIR)
    args = ap.parse_args(argv)
    out = os.path.join(args.doc_dir, IMG_SUBDIR)
    os.makedirs(out, exist_ok=True)

    (fpath, flabel), (bpath, blabel) = FLANGE_BRANCH, BOLT_BRANCH
    for path in (fpath, bpath):
        if not os.path.exists(path):
            raise SystemExit(
                'missing %s -- run fillet_scope_analysis/measure_fillet_context.py first'
                % os.path.relpath(path, HERE))
    flange, bolt = load(fpath), load(bpath)

    figures = {
        'bulkhead': fig_bulkhead(flange, flabel, 'bh'),
        'outer_corner': fig_outer_corner(flange, flabel, 'oc'),
        'greeble_buried': fig_greeble_buried(flange, flabel, bolt, blabel, 'gb'),
    }

    bad = 0
    for name, body in sorted(figures.items()):
        clash, cut = overlaps(body), off_frame(body)
        if clash or cut:
            bad += 1
        for a, c in clash[:6]:
            print('%s: %r overlaps %r' % (name, a[:44], c[:44]))
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
