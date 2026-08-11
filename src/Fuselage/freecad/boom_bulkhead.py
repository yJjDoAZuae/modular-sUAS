"""IP-FC-12: boom_bulkhead -- the whole part, as one profile and one extrusion.

Everything below this module is a 2D shape. This is where they come together and where the
only `Part::Extrusion` in the boom bulkhead sits. Written as algebra, the source is

    profile = OML - fillet_inner(r)[ OML - MATERIAL ] - KEY

    MATERIAL = ( RIM u WEBS ) - BORES
    RIM      = OML - web_inner              the frame ring left by the lightening pocket
    WEBS     = web_outer - web_inner - KEY  the boom's own webs, hollowed and keyed
    BORES    = the longeron bores and bolt holes

The double negation is the interesting part and it is not redundant. `MATERIAL` is everything
that must be kept; `OML - MATERIAL` is therefore everything that may be removed; and the
`fillet_inner` then softens that removable region before it is taken out, which is what rounds
the lightening pockets and drops any sliver narrower than twice the radius rather than cutting
it. Subtracting `MATERIAL` directly would give the same pockets with sharp corners and with
those slivers cut as unprintable knife edges.

`BORES` is subtracted from the material rather than from the profile, so the bores are places
the pocket is *allowed* to reach, not holes punched through afterwards. The bore edges then get
the same `web_fillet_radius` rounding as everything else.

**The lower web is not ported yet.** `boom_make_lower_web` adds a second pair of web shapes
mirrored in y and evaluated at `-boom_z_position` and `180 - boom_key_angle`, which needs
`boom_webs` re-run against a second set of rows -- the `bulkhead_tree` pattern, not a mirror of
what is already built. One of the three boom types (`center_single`) sets it. This module
refuses rather than quietly dropping the web, because a boom bulkhead missing a web is a
plausible-looking part that would pass a visual check.

Derived parameters for U=1.0 boom offset_single 3 mm.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import boom_oml
import boom_webs
import bulkhead_web
import corner_tree as C
import plane2d
from corner_common import build_sheet, is_entry_point, merge_params

P = 'Params.'

# ref_boom_bulkhead.scad mode 9, which is the part itself and so a VOLUME, not an area.
REF_VOLUME = 7433.4744903
EXPECT_BBOX = (-50.0, -50.0, 0.0, 50.0, 50.0, 2.0)

OWN = [
    ('boom_bulkhead_thickness', '2.0'),
    # 1 when the lower web is wanted, 0 when it is not -- read in Python, never in an
    # expression, for the same reason `boom_make_vert_web` is.
    ('boom_make_lower_web', '0.0'),
]

PARAMS = merge_params([boom_oml, boom_webs, bulkhead_web]) + OWN


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def _union(doc, name, pieces):
    return plane2d.union(doc, name, pieces, P + 'webs_reach')


def profile(doc):
    """The 2D profile, against whatever sheet the document already has."""
    if float(doc.getObject('Params').get('boom_make_lower_web')) >= 0.5:
        raise NotImplementedError('boom_make_lower_web is set and the lower web is not ported '
                                  'yet -- see this module\'s docstring')

    oml = boom_oml.oml_shape(doc)
    bores = boom_oml.oml_inner_shape(doc)
    pocket = bulkhead_web.web_inner_shape(doc, oml=oml)
    w = boom_webs.webs(doc)

    rim = C._cut(doc, 'FrameRim', oml, pocket)
    webs = C._cut(doc, 'WebsHollow', w['outer'], w['inner'])
    webs = C._cut(doc, 'WebsKeyed', webs, w['key'])

    material = C._cut(doc, 'Material', _union(doc, 'MaterialRaw', [rim, webs]), bores)

    lighten = plane2d.fillet_inner(doc, 'Lighten', C._cut(doc, 'LightenRaw', oml, material),
                                   P + 'web_fillet_radius')
    return C._cut(doc, 'BoomBulkheadProfile',
                  C._cut(doc, 'ProfileLightened', oml, lighten), w['key'])


def part(doc):
    """The profile, extruded once through the bulkhead's thickness."""
    # the profile first, then the node that consumes it -- see bulkhead_web.web_inner_shape
    # for what building them the other way round costs
    base = profile(doc)
    ext = C._owned(doc, 'Part::Extrusion', 'BoomBulkhead')
    ext.Base = base
    ext.DirMode = 'Custom'
    ext.Dir = App.Vector(0, 0, 1)
    ext.Solid = True
    ext.setExpression('LengthFwd', P + 'boom_bulkhead_thickness')
    return ext


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    tip = part(doc)
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('boom_bulkhead')
    tip = emit(doc)
    shape = tip.Shape
    got = shape.Volume
    d = got - REF_VOLUME
    bb = shape.BoundBox
    real = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
    checks = []
    if not shape.isValid():
        checks.append('INVALID')
    if len(shape.Solids) != 1:
        checks.append('SOLIDS=%d' % len(shape.Solids))
    if abs(d) / REF_VOLUME > 6.0e-5:
        checks.append('OVER TOLERANCE')
    if max(abs(a - b) for a, b in zip(real, EXPECT_BBOX)) > 5.0e-4:
        checks.append('BBOX [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]' % real)

    print('PART:: boom_bulkhead')
    print('  %-22s %13s %13s %11s  %s'
          % ('shape', 'FreeCAD', 'OpenSCAD', 'delta', 'checks'))
    print('  %-22s %13.7f %13.7f %+10.5f%%  %s'
          % ('boom_bulkhead', got, REF_VOLUME, 100 * d / REF_VOLUME,
             ' '.join(checks) if checks else 'ok'))
    print('')
    print('  %s' % ('agrees' if not checks else 'MISMATCH -- see checks above'))


if is_entry_point(__name__):
    main()
