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

`boom_make_lower_web` adds a second pair of web shapes evaluated at `-boom_z_position` and
`180 - boom_key_angle` and mirrored in y. **That is a second evaluation of the web builders,
not a mirror of the first** -- the `bulkhead_tree` pattern. Mirroring what is already built
would be wrong by the key: at `180 - boom_key_angle` the tab faces the other way, so the pad
the web grows around it is a different shape, and the reference says so (the lower web's outer
shape is 2888.83 against the upper's 2868.85 at `center_single`).

Only two inputs change, and every derived row in `boom_key` and `boom_web` is independent of
both -- collet and tab dimensions, frame turning points, and a `key_reach` that takes an
absolute value. So the second evaluation reads the same sheet rows and adds just two of its
own. The builders take a `tag` for their node names and expressions for those two inputs.

This module is checked at **both** boom types that reach it: `offset_single`, which is
`ref_boom_bulkhead.scad`, and `center_single`, which is `ref_boom_bulkhead_center.scad` and is
the one that sets the flag. `dual` shares `offset_single`'s flag settings.

Derived parameters for U=1.0, 3 mm panel, from `derived_parameters()`.
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

# Mode 9 of each reference, which is the part itself and so a VOLUME, not an area. The rows
# each variant overrides are the only three that differ between them, and they come from
# `derived_parameters(1.0, 1.0, <type>, 3 mm)` -- see the head of each reference .scad.
VARIANTS = [
    ('offset_single', 7433.4744903, {}),
    ('center_single', 8296.1222588, {'boom_z_position': '0.0',
                                     'boom_make_vert_web': '0.0',
                                     'boom_make_lower_web': '1.0'}),
]
EXPECT_BBOX = (-50.0, -50.0, 0.0, 50.0, 50.0, 2.0)

# ref_boom_bulkhead_center.scad modes 16 and 17, as (node, area). The assembled part agreeing
# is the binding check; these say the lower web is right *on its own* rather than by two errors
# cancelling. They are worth having because the numbers are close to the upper web's and not
# equal to it -- 2888.83 against 2868.85 -- so a lower web built by mirroring the upper one
# would land within a percent of the truth and look plausible.
LOWER_REFS = [('LwOuterFlip', 2888.8332161), ('LwInnerFlip', 1265.7236228)]

OWN = [
    ('boom_bulkhead_thickness', '2.0'),
    # 1 when the lower web is wanted, 0 when it is not -- read in Python, never in an
    # expression, for the same reason `boom_make_vert_web` is.
    ('boom_make_lower_web', '0.0'),

    # The lower web's two inputs, and the whole of its second parameter set. Everything else
    # it needs is independent of them and is read from the rows above.
    ('lw_boom_z_position', '=-boom_z_position'),
    ('lw_boom_key_angle', '=180 - boom_key_angle'),
]

PARAMS = merge_params([boom_oml, boom_webs, bulkhead_web]) + OWN


def sheet(doc, seed=None, overlay=None):
    """The sheet, with a variant's overriding rows applied by alias.

    An overlay replaces a row's *definition*, so a relationship stays a relationship: only
    the three rows a boom type actually changes are literals here, and everything derived
    from them follows.
    """
    rows = PARAMS if not overlay else [(a, overlay.get(a, v)) for a, v in PARAMS]
    return build_sheet(doc, rows, seed)


def _union(doc, name, pieces):
    return plane2d.union(doc, name, pieces, P + 'webs_reach')


def _mirror_y(doc, name, source):
    """`mirror([0,-1,0])` -- the reflection alone, not unioned with its source."""
    node = C._owned(doc, 'Part::Mirroring', name)
    node.Source = source
    node.Normal = App.Vector(0, 1, 0)
    return node


def profile(doc):
    """The 2D profile, against whatever sheet the document already has."""
    lower = float(doc.getObject('Params').get('boom_make_lower_web')) >= 0.5

    oml = boom_oml.oml_shape(doc)
    bores = boom_oml.oml_inner_shape(doc)
    pocket = bulkhead_web.web_inner_shape(doc, bores=bores)
    w = boom_webs.webs(doc)
    outer, inner = w['outer'], w['inner']

    if lower:
        lw = boom_webs.webs(doc, 'Lw', P + 'lw_boom_z_position', P + 'lw_boom_key_angle')
        outer = _union(doc, 'WebsOuterBoth',
                       [outer, _mirror_y(doc, 'LwOuterFlip', lw['outer'])])
        inner = _union(doc, 'WebsInnerBoth',
                       [inner, _mirror_y(doc, 'LwInnerFlip', lw['inner'])])

    # Only the UPPER key is subtracted, in the source as here. The lower evaluation's key
    # exists to size the lower web's pad and is never cut from the part.
    rim = C._cut(doc, 'FrameRim', oml, pocket)
    webs = C._cut(doc, 'WebsHollow', outer, inner)
    webs = C._cut(doc, 'WebsKeyed', webs, w['key'])

    material = C._cut(doc, 'Material', _union(doc, 'MaterialRaw', [rim, webs]), bores)

    # The lightening region is inside the OML, so `oml_reach` encloses it and every dilation
    # of it the fillet performs.
    lighten = plane2d.fillet_inner(doc, 'Lighten', C._cut(doc, 'LightenRaw', oml, material),
                                   P + 'web_fillet_radius', P + 'oml_reach')
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


def emit(doc, seed=None, overlay=None):
    C._SEEN.clear()
    sheet(doc, seed, overlay)
    tip = part(doc)
    doc.recompute()
    return tip


def _check(label, shape, ref):
    got = shape.Volume
    d = got - ref
    bb = shape.BoundBox
    real = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
    checks = []
    if not shape.isValid():
        checks.append('INVALID')
    if len(shape.Solids) != 1:
        checks.append('SOLIDS=%d' % len(shape.Solids))
    if abs(d) / ref > 6.0e-5:
        checks.append('OVER TOLERANCE')
    if max(abs(a - b) for a, b in zip(real, EXPECT_BBOX)) > 5.0e-4:
        checks.append('BBOX [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]' % real)
    print('  %-22s %13.7f %13.7f %+10.5f%%  %s'
          % (label, got, ref, 100 * d / ref, ' '.join(checks) if checks else 'ok'))
    return not checks


def main():
    print('PART:: boom_bulkhead, at both boom types that reach this module')
    print('  %-22s %13s %13s %11s  %s'
          % ('boom type', 'FreeCAD', 'OpenSCAD', 'delta', 'checks'))
    ok = True
    for name, ref, overlay in VARIANTS:
        doc = App.newDocument('boom_bulkhead_' + name)
        tip = emit(doc, overlay=overlay)
        ok &= _check(name, tip.Shape, ref)
        for node, area_ref in LOWER_REFS:
            obj = doc.getObject(node)
            if obj is not None:
                ok &= plane2d.report(doc, '  ' + node, obj.Shape, area_ref, 'webs_reach')
        App.closeDocument(doc.Name)
    print('')
    print('  %s' % ('agrees' if ok else 'MISMATCH -- see checks above'))


if is_entry_point(__name__):
    main()
