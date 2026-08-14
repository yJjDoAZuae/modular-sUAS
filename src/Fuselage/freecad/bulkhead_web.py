"""IP-FC-12: bulkhead_web_inner_shape -- the lightening pocket inside the bulkhead frame.

This is the fifth and last rounding site in the boom bulkhead, and it is the only one that
comes from the frame rather than from the boom. What survives is the pocket: everything at
least `web_width` in from the outline, with its convex corners rounded to `web_fillet_radius`
and anything thinner than twice that radius removed.

    bulkhead_web_inner_shape = oml_outer  n  fillet_inner(r)[ offset(-web_width)(oml) ]

**It is built region-wide here, and the source builds it as an octant.** That is not a
shortcut taken on the geometry's behalf; the two are the same set, and the reason is worth
stating because every other octant in this port would be wrong built this way.

The source's octant is

    octant_tiled(uw, cr) { translate(-arm, -arm) { intersection(A, B, C) } }

where A and B are the whole-region outline and the whole-region eroded-and-filleted outline,
and C is the wedge triangle (0,0)-(uw/2,uw/2)-(0,uw/2). `octant_tiled` opens with
`corner_translate`, which is `translate(+arm, +arm)`, so the two translates cancel exactly and
the intersection is evaluated in world coordinates -- unlike every other `*_octant` module in
`fuselage_bulkhead_geometry.scad`, whose contents really are drawn corner-local. The tiling
that follows is the eight-element dihedral group, and

    U_g  g(A n B n C)  =  A n B n (U_g gC)  =  A n B

because A and B are each invariant under every g (they are themselves `octant_tiled`, and
`offset` commutes with isometries), and the eight images of C tile the square of half-width
uw/2, which contains A. So the tiling is doing nothing here but reassembling what a
region-wide intersection already gives, and the reference confirms it to 0.00007%.

The trap this shape sets is the other direction: computing A and B *locally* -- one octant's
worth of outline, eroded on its own -- and then tiling. That gives a closed, plausible,
completely wrong region, because an erosion of one wedge sees boundary where the full outline
has none. The wedge is a window onto a whole-region computation, not a unit of it.

Derived parameters for U=1.0 boom offset_single 3 mm.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import boom_oml
import corner_tree as C
import plane2d
from corner_common import build_sheet, is_entry_point, merge_params

P = 'Params.'

# ref_boom_bulkhead.scad mode 10
REF_AREA = 5700.1741175
EXPECT_BBOX = (-40.9, -40.9, 40.9, 40.9)

OWN = [
    ('web_width', '6.0'),
    ('web_fillet_radius', '2.0'),
]

PARAMS = merge_params([boom_oml]) + OWN


def sheet(doc, seed=None):
    return build_sheet(doc, PARAMS, seed)


def web_inner_shape(doc, bores=None):
    """Geometry only, against whatever sheet the document already has.

    `bores` is `bulkhead_oml_inner_shape` when the caller has already built it -- the assembly
    has, and one object driven by one set of rows is the point of the port. Left out, this
    module builds its own.

    **The source erodes the whole OML by `web_width`; this erodes the outline and grows the
    bores instead.** They are the same region, by the morphological identity

        erosion(A - B, w)  ==  erosion(A, w) - dilation(B, w)

    -- a disc of radius `w` fits inside `A - B` exactly when it fits inside `A` and misses `B`
    -- and only the right-hand side is computable here. `Part::Offset2D` returns a **null
    shape** for the left-hand side at U=0.75 with a 3 mm panel, taking the whole part with it
    (IP-FC-54). Not at one value either: every erosion from 3.0 to 5.0 mm is null there while
    6.0 mm succeeds, so it is not a tangency that a nudge would clear.

    What OCCT is being asked for in that form is a boundary that self-intersects heavily. The
    longeron bore is *concentric with the corner arc*, so eroding by more than
    `corner_radius - longeron_radius - longeron_tolerance` makes the grown bore swallow the
    shrunk arc entirely, and at U=0.75 the panel notch is 4.4 mm deep against a 4.5 mm erosion
    as well -- two features crossing the offset distance at once. Split in two, neither half is
    degenerate: the outline erodes cleanly and dilating eight separated circles is trivial.

    The identity is exact, not an approximation. Where the direct form works it agrees to the
    last digit -- 5770.975162 either way at U=1.0 -- which is what says this is a change of
    route and not of shape.

    Both operands are built before the node that consumes them. Writing one inline as
    `clip.Shapes = [oml_outer_shape(doc), pocket]` creates the clip first and its dependency
    afterwards, and FreeCAD's first recompute pass then reaches the clip while that dependency
    still holds a null shape -- an "Access violation" on stderr, after which a later pass
    quietly recomputes it correctly. The final area is right either way, so the only symptom
    is a line of stderr that is easy to read past. Build dependencies first.
    """
    outer = boom_oml.oml_outer_shape(doc)
    if bores is None:
        bores = boom_oml.oml_inner_shape(doc)

    eroded_outer = plane2d.offset(doc, 'WebErodeOuter', outer, '-' + P + 'web_width')
    # The eight dilated bores overlap each other here, which `Part::Cut` handles correctly --
    # but merged anyway, so no node in the tree carries overlapping faces for a later offset
    # to double-count (IP-FC-52).
    grown = plane2d.merge(doc, 'WebBores',
                          plane2d.offset(doc, 'WebBoresGrow', bores, P + 'web_width'),
                          P + 'oml_reach')
    eroded = C._cut(doc, 'WebErode', eroded_outer, grown)

    # `oml_reach` encloses the OML itself, so it encloses an erosion of it dilated back by
    # less than it was eroded by.
    pocket = plane2d.fillet_inner(doc, 'Web', eroded, P + 'web_fillet_radius',
                                  P + 'oml_reach')

    clip = C._owned(doc, 'Part::MultiCommon', 'BulkheadWebInner')
    clip.Shapes = [outer, pocket]
    return clip


def emit(doc, seed=None):
    C._SEEN.clear()
    sheet(doc, seed)
    tip = web_inner_shape(doc)
    doc.recompute()
    return tip


def main():
    doc = App.newDocument('bulkhead_web')
    tip = emit(doc)
    print('PART:: 2D CSG tree -- bulkhead_web_inner_shape')
    print('  %-22s %13s %13s %11s  %s'
          % ('shape', 'FreeCAD', 'OpenSCAD', 'delta', 'checks'))
    ok = plane2d.report(doc, 'web_inner', tip.Shape, REF_AREA, 'oml_reach', EXPECT_BBOX)
    print('')
    print('  %s' % ('agrees' if ok else 'MISMATCH -- see checks above'))


if is_entry_point(__name__):
    main()
