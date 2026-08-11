"""IP-FC-12: boom_web_outer_shape and boom_web_inner_shape -- the first region-wide roundings.

These are the two sites OQ-DES-B11 kept morphological. Unlike the key, whose four corners are a
fixed named set, these apply `fillet_outer`/`fillet_inner` to a **whole compound region** whose
concave-corner set moves with the parameters, so they port as `Part::Offset2D` chains rather
than as real fillets.

    boom_web_outer_shape = fillet_outer(r) [ offset(+key_web)(key) u stroke ]
    boom_web_inner_shape = fillet_inner(r) [ eroded_web - offset(+key_web)(key) ]

**`boom_make_vert_web` swaps an erode with a mirror, and the two do not commute.** The source
writes the eroded web as `mirror_x(offset(-w/2)(spine))` when the flag is set and
`offset(-w/2)(mirror_x(spine))` when it is not. Eroding before mirroring erodes each half
against its own boundary, so material survives on the mirror line that eroding afterwards
removes -- the vertical web the flag is named for. Two of the three swept boom types set it
(`offset_single`, `dual`) and `center_single` does not, so both orderings are built and both
are measured. `ref_boom_bulkhead.scad` mode 3 is the *unset* ordering, which is why it is not
the shape this module's inner web starts from.

Derived parameters for U=1.0 boom offset_single 3 mm.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import boom_key
import boom_web
import corner_tree as C
import plane2d
from corner_common import build_sheet, is_entry_point, merge_params

V = App.Vector
P = 'Params.'

# ref_boom_bulkhead.scad modes 6 and 7
REFS = {
    'outer': (1899.6654770, (-43.0, 11.8002, 43.0, 46.9)),
    'inner': (411.5218898, (-33.8288, 30.9520, 33.8286, 40.9)),
}

OWN = [
    ('web_fillet_radius', '2.0'),
    ('boom_key_web_width', '6.0'),
    # 1 when the vertical web is wanted, 0 when it is not -- the sheet carries no booleans,
    # and the flag changes the ORDER of two operations rather than a dimension, so it is read
    # in Python and never appears in an expression.
    ('boom_make_vert_web', '1.0'),
    # enclosure for plane2d.union: the outer shape reaches key_web_width beyond the collet
    ('webs_reach', '=2 * (unit_width / 2 + web_width + boom_key_web_width)'),
]

PARAMS = merge_params([boom_key, boom_web]) + OWN


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def _union(doc, name, pieces):
    return plane2d.union(doc, name, pieces, P + 'webs_reach')


def _vert_web(doc):
    return float(doc.getObject('Params').get('boom_make_vert_web')) >= 0.5


def key_dilated(doc, key):
    """`offset(r = boom_key_web_width) { boom_key_shape(...) }` -- the web pad around the key."""
    return plane2d.offset(doc, 'KeyPad', key, P + 'boom_key_web_width')


def eroded_web(doc, spine):
    """The web's inner region, at whichever of the two orderings the flag selects."""
    half = '-' + P + 'half_web'
    if _vert_web(doc):
        # erode each half against its own boundary, then mirror -- leaves the vertical web
        return boom_web.mirror_x(doc, 'ErodedMirrored',
                                 plane2d.offset(doc, 'ErodeHalf', spine, half))
    return plane2d.offset(doc, 'ErodeWhole',
                          boom_web.mirror_x(doc, 'SpineMirrored', spine), half)


def webs(doc):
    """Geometry only, against whatever sheet the document already has.

    Returns the key as well as the two webs. The assembly subtracts the key twice and this
    module already builds it, so handing it back is what keeps `boom_key.key_shape` from being
    called a second time -- which `_owned` refuses, and rightly: two key objects driven by the
    same rows is two things to keep in step.
    """
    key = boom_key.key_shape(doc)
    spine = boom_web.centerline(doc)
    pad = key_dilated(doc, key)

    stroke = plane2d.offset(doc, 'Stroke',
                            boom_web.mirror_x(doc, 'StrokeMirrored', spine), P + 'half_web')
    outer = plane2d.fillet_outer(doc, 'Outer', _union(doc, 'OuterRaw', [pad, stroke]),
                                 P + 'web_fillet_radius', P + 'webs_reach')

    inner = plane2d.fillet_inner(doc, 'Inner',
                                 C._cut(doc, 'InnerRaw', eroded_web(doc, spine), pad),
                                 P + 'web_fillet_radius')

    return {'outer': outer, 'inner': inner, 'key': key}


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    tips = webs(doc)
    doc.recompute()
    return tips


def main():
    doc = App.newDocument('boom_webs')
    tips = emit(doc)

    print('PART:: 2D CSG tree -- boom web outer and inner shapes')
    print('  vertical web: %s' % ('yes' if _vert_web(doc) else 'no'))
    print('  %-22s %13s %13s %11s  %s'
          % ('shape', 'FreeCAD', 'OpenSCAD', 'delta', 'checks'))
    ok = True
    for name in ('outer', 'inner'):
        ref, bbox = REFS[name]
        ok &= plane2d.report(doc, name, tips[name].Shape, ref, 'webs_reach', bbox)
    print('')
    print('  %s' % ('both shapes agree' if ok else 'MISMATCH -- see checks above'))


if is_entry_point(__name__):
    main()
