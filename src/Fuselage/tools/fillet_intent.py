"""IP-FC-73: what is each bulkhead fillet's center actually tangent to?

Stage 1 of OQ-ARCH-11 converts derived features from solved coordinates to stated constraints,
and the rule established by the bolt-flange fillet (OQ-DES-B14) is that a feature's **intent
must be established before it is constrained**, not inferred while converting it. For that
fillet the intent turned out to be recoverable from the algebra rather than needing a
designer's ruling, and the evidence was that the proposed tangencies hold as identities across
the whole corpus. This runs the same check for the others.

The claim being tested, for each fillet, is that its center is a circle of radius
`flange_fillet_radius` touching two named features at once -- so that the conversion is two
`Tangent` constraints and the part does not move. A residual near machine epsilon means the
closed form in `fillets.PARAMS` is that tangency written out as arithmetic; a residual that
grows with the parameters would mean it is something else and the conversion would move
geometry.

Pure arithmetic on exported parameters -- nothing is built, so the whole corpus takes seconds.

    uv run python src/Fuselage/tools/fillet_intent.py            # every valid bulkhead
    uv run python src/Fuselage/tools/fillet_intent.py --types end

`bulkhead_flange_chamfer` is deliberately absent: it is a chamfer, a prism cut at 45 degrees
across the flange's top edge, and it has no fillet center and no tangency to state. Converting
it is a profile-sketch question rather than a constraint question, so it needs a different
treatment from the other four and is not measured here.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import export_parameters  # noqa: E402
import fuselage_variants as fv  # noqa: E402

SQ2 = math.sqrt(2.0)
AXES = ('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv')

# A residual this size is the last bits of a double, not a modeling difference. The
# bolt-flange fillet came in at 3.6e-15 mm over 88 variants when its intent was established.
EPSILON = 1e-9


def variants(types):
    printer = fv.null_printer_settings()
    out = []
    for params in fv.flatten_param_space(fv.read_all_param_axes(fv.axes(*AXES))):
        dp = fv.derived_parameters(params['U'], 1.0, params, printer, True)
        if not fv.family_is_valid('bulkhead', dp):
            continue
        if types == 'end' and dp.bulkhead.type != fv.BulkheadType.END:
            continue
        out.append((params['U'], dp.bulkhead.type_name, dp.panel.type_name))
    return out


def derived(p):
    """The rows of `fillets.PARAMS` this check needs, in the same order the sheet builds them."""
    d = dict(p)
    d['flange_inner_x'] = -(p['panel_tolerance'] + p['panel_offset'] + p['panel_overlap']
                            + p['flange_thickness'])
    d['flange_y'] = (p['corner_radius'] - p['panel_thickness'] - p['panel_tolerance']
                     - p['flange_thickness'])
    d['bolt_c'] = -p['bolt_offset']
    d['bolt_boss_r'] = p['bolt_hole_radius'] + p['bolt_thickness']
    d['r_bolt_fillet'] = p['flange_fillet_radius'] + d['bolt_boss_r']
    return d


def point_to_line_45(x, y, through_x, through_y):
    """Signed perpendicular distance from (x, y) to the 45 degree line through a point.

    Positive on the upper-left side, which is the side every fillet here sits on.
    """
    return ((y - through_y) - (x - through_x)) / SQ2


def outer_corner_fillet(d):
    """Center one radius in from the corner of two perpendicular flange faces."""
    r = d['flange_fillet_radius']
    cx, cy = d['flange_inner_x'] - r, d['flange_y'] - r
    return [('tangent to the flange inner face (x = flange_inner_x)',
             abs(cx - d['flange_inner_x']) - r),
            ('tangent to the flange y face (y = flange_y)',
             abs(cy - d['flange_y']) - r)]


def greeble_to_web_fillet(d):
    """Center one radius off the flange's inner face and off the 45 degree wall face.

    **Checked only where the corner exists** (OQ-ARCH-14, 2026-08-17). This used to measure
    against `gtw_start = max(flange_inner_x; -bolt_offset)`, and the tangency held trivially
    because the arithmetic under test and the claim being tested were the same `max`. What the
    fillet rounds is where the web's upper face runs into the flange's inner face, so the face
    is `flange_inner_x` and nothing else; where the web stops short of it -- 27 of 148
    variants, every one at U <= 1.0 -- there is no corner, the model builds no body, and there
    is no tangency to check.
    """
    if d['flange_inner_x'] < d['bolt_c']:
        return []
    r, ft = d['flange_fillet_radius'], d['flange_thickness']
    cx = d['flange_inner_x'] - r
    cy = cx + r * SQ2 + ft / SQ2
    return [('tangent to the flange inner face (x = flange_inner_x)',
             abs(cx - d['flange_inner_x']) - r),
            ('tangent to the 45 degree wall face',
             point_to_line_45(cx, cy, cx, cx) - (ft / 2 + r))]


def web_to_bolt_fillet(d):
    """Center one radius off the bolt boss and off the 45 degree wall face."""
    r, ft = d['flange_fillet_radius'], d['flange_thickness']
    bolt_c, boss_r = d['bolt_c'], d['bolt_boss_r']
    a = r + ft / 2
    tan = math.sqrt(max(d['r_bolt_fillet'] ** 2 - a ** 2, 0.0))
    cx = bolt_c + (tan - a) / SQ2
    cy = bolt_c + (tan + a) / SQ2
    return [('tangent to the bolt boss (radius bolt_boss_r at the bolt center)',
             math.hypot(cx - bolt_c, cy - bolt_c) - (r + boss_r)),
            ('tangent to the 45 degree wall face',
             point_to_line_45(cx, cy, bolt_c, bolt_c) - (ft / 2 + r))]


def bolt_flange_fillet(d):
    """Already converted (OQ-DES-B14). Checked anyway, so a regression here is visible."""
    r = d['flange_fillet_radius']
    bolt_c, boss_r = d['bolt_c'], d['bolt_boss_r']
    cx = d['flange_inner_x'] - r
    span = (r + boss_r) ** 2 - (cx - bolt_c) ** 2
    if span <= 0:
        return [('unsatisfiable: no circle touches both', float('nan'))]
    cy = math.sqrt(span) + bolt_c
    return [('tangent to the flange inner face (x = flange_inner_x)',
             abs(cx - d['flange_inner_x']) - r),
            ('tangent to the bolt boss (radius bolt_boss_r at the bolt center)',
             math.hypot(cx - bolt_c, cy - bolt_c) - (r + boss_r))]


FILLETS = [
    ('outer_corner_fillet', outer_corner_fillet),
    ('greeble_to_web_fillet', greeble_to_web_fillet),
    ('bolt_flange_fillet (converted)', bolt_flange_fillet),
    ('web_to_bolt_fillet', web_to_bolt_fillet),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--types', choices=('end', 'all'), default='all')
    ap.add_argument('--epsilon', type=float, default=EPSILON,
                    help='a residual above this is a real difference (default 1e-9 mm)')
    args = ap.parse_args(argv)

    picked = variants(args.types)
    scratch = tempfile.mkdtemp(prefix='fillet_intent_')
    params = []
    for U, type_name, panel in picked:
        name = 'U_%s_%s_%s' % (U, type_name, panel.replace('/', '_'))
        path = os.path.join(scratch, name + '.json')
        export_parameters.main([str(U), type_name, panel, path])
        params.append((name, path))

    import json
    worst = {}
    for name, path in params:
        with open(path) as f:
            p = json.load(f)['parameters']
        d = derived(p)
        for fillet, fn in FILLETS:
            for claim, residual in fn(d):
                key = (fillet, claim)
                if key not in worst or abs(residual) > abs(worst[key][0]):
                    worst[key] = (residual, name)

    print('%d variant(s), %s bulkhead types' % (len(params), args.types))
    print()
    failed = 0
    for fillet, _fn in FILLETS:
        print('%s' % fillet)
        for (f, claim), (residual, where) in sorted(worst.items()):
            if f != fillet:
                continue
            ok = abs(residual) <= args.epsilon
            failed += not ok
            print('  %-58s %+.3e mm  %s' % (claim, residual, 'holds' if ok else '<-- DOES NOT HOLD'))
            if not ok:
                print('    worst on %s' % where)
        print()

    if failed:
        print('%d claim(s) do not hold -- the closed form is not the tangency it looks like, '
              'and converting it would move geometry' % failed)
        return 1
    print('every claim holds to within %g mm across the corpus, so each of these centers is '
          'the stated pair of tangencies written out as arithmetic' % args.epsilon)
    return 0


if __name__ == '__main__':
    sys.exit(main())
