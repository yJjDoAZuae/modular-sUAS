"""IP-FC-12: the 2D primitives and the one union rule the boom bulkhead is built from.

The frame bulkhead and the corner are octant-and-mirror **solids**. The boom bulkhead is a flat
profile extruded once, and four of its five rounding sites need `Part::Offset2D`, which operates
on faces -- so its whole profile is built in the plane and a single `Part::Extrusion` sits at the
top. These are the pieces that construction needs, shared by `boom_key.py` and `boom_web.py`.

Everything here is an ordinary Part:: document object driven by the parameter sheet, so the
editability the port exists to preserve holds in the plane exactly as it does in space.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corner_tree as C

P = 'Params.'


def face(doc, name, *sources):
    """Close one or more wires into a face. The 2D counterpart of taking a solid."""
    node = C._owned(doc, 'Part::Face', name)
    node.Sources = list(sources)
    return node


def disc(doc, name, radius, x='0', y='0'):
    """A filled circle, as a parametric edge closed by a face."""
    circle = C._owned(doc, 'Part::Circle', name + 'Edge')
    circle.setExpression('Radius', radius)
    circle.setExpression('Placement.Base.x', x)
    circle.setExpression('Placement.Base.y', y)
    return face(doc, name, circle)


def rect(doc, name, length, width, x, y):
    """An axis-aligned rectangular face with its corner at (x, y)."""
    plane = C._owned(doc, 'Part::Plane', name)
    plane.setExpression('Length', length)
    plane.setExpression('Width', width)
    plane.setExpression('Placement.Base.x', x)
    plane.setExpression('Placement.Base.y', y)
    return plane


def union(doc, name, pieces, reach):
    """Union coplanar faces into ONE face, as `R - ((R - a) - b - ...)`.

    **Do not use `Part::Fuse` or `Part::MultiFuse` for coplanar faces.** They return a
    **Compound** of abutting faces rather than one face, and `Part::Offset2D` offsets each
    member of a compound *separately*, interior shared edges included. Measured on the boom
    key at `offset(r = 6)`, FreeCAD 1.1.1:

        fuse chain (15 faces)  ->  2434.87 mm2   vs OpenSCAD 567.31   +329%
        this route (1 face)    ->   567.34 mm2   vs OpenSCAD 567.31   +0.0054%

    and the +329% comes back as a closed, valid, plausible region with no warning. The fused
    compound's own area is right to 0.005%, so a check on that node alone never sees it.

    Nothing else reaches one face. `Part::Refine` is `ShapeUpgrade_UnifySameDomain` and cannot
    unify across a compound; `Part::MultiFuse` with `Refine = True` is still a compound;
    `Part::FaceMakerBullseye`, `...Simple` and `...Cheese` each rebuild the fragments, because
    the union's outer boundary is itself split across several wires. Only the scripted
    `shape.multiFuse(...).removeSplitter()` unifies -- it returns a Shell, which the document
    objects never do -- and baking that into a `Part::Feature` would cost the parametric
    editability the whole port exists to keep.

    `Part::Cut` does not fragment, so De Morgan gets there in stock objects: cut every piece
    out of a rectangle, then cut the result back out of the same rectangle.

    **The rectangle must strictly enclose every piece**, in the frame the union happens in. If
    it does not, the union silently truncates to whatever the rectangle held -- measured at
    -9.42% when a first attempt sized it for the placed key while the pieces were still in
    local coordinates. Callers supply `reach` from every term that can push material outward,
    and `enclosed()` asserts the result is clear of the rectangle's edge.
    """
    frame = rect(doc, name + 'Rect', '2 * ' + reach, '2 * ' + reach,
                 '-' + reach, '-' + reach)
    node = frame
    for i, piece in enumerate(pieces):
        node = C._cut(doc, '%sNeg%d' % (name, i), node, piece)
    return C._cut(doc, name, frame, node)


def merge(doc, name, source, reach):
    """One face out of a shape whose faces may OVERLAP. `union` with a single piece.

    Separate from `union` by name because it answers a different question. `union` is for
    pieces the caller built separately and wants combined; this is for a single node whose
    own faces have grown into each other, which is what an outward `Part::Offset2D` on a
    multi-face source produces -- see `offset`.
    """
    return union(doc, name, [source], reach)


def offset(doc, name, source, value, join='Arc'):
    """OpenSCAD's `offset(r = value)`. Round joins, which is Join='Arc'.

    Measured faithful to 0.00456% across the chain, including `fillet_inner` -- see
    spike_offset2d.py, and note that the 2026-08-08 reading of 19% was taken at a degenerate
    parameter value and is wrong.

    **An OUTWARD offset of a multi-face source does not merge faces that come to overlap.**
    `Part::Offset2D` treats each face of its source independently -- correctly for faces that
    stay apart, which is why `fragmented()` allows several faces -- but when a positive offset
    grows two of them into each other it keeps both, and the shared area is then counted
    twice. Every consumer downstream sees a closed, valid, plausible region that is too large.

    Found by IP-FC-13 at U=0.75 / 1/8 in panel / `dual`, the one swept boom bulkhead where the
    inner web's erosion disconnects into pieces closer together than twice the fillet radius.
    `offset(-r)` split it into four faces, `offset(+2r)` regrew them overlapping and read
    467.48 mm2 against OpenSCAD's 458.48, and the finished part came out +0.167% -- sixteen
    times the tolerance, on a part whose other eleven sampled variants agree to 0.0006%.

    An INWARD offset cannot create an overlap, so only the outward direction needs the merge.
    `fillet_inner` and `fillet_outer` do it at their dilation steps, which is where an offset
    is applied to a shape the same function just produced and so cannot be assumed to be one
    face. A caller offsetting outward by hand must decide for itself -- there is no reach here
    to merge with, and adding one to every offset would make the common single-face case pay
    for the rare one.
    """
    node = C._owned(doc, 'Part::Offset2D', name)
    node.Source = source
    node.Join = join
    node.Fill = False
    node.setExpression('Value', value)
    return node


def erode_difference(doc, tag, positive, negatives, radius):
    """`offset(-r)` of `positive - negatives[0] - ...`, without ever offsetting the difference.

    The morphological identity

        erosion(A - B, r)  ==  erosion(A, r) - dilation(B, r)

    -- a disc of radius r fits inside `A - B` exactly when it fits inside `A` and misses `B`
    -- extended to as many subtracted regions as the caller has. It is exact, and it is worth
    having because the two sides are not equally computable. `Part::Offset2D` fails on shapes
    that carry the history of the boolean that made them, and a difference is exactly such a
    shape; the operands going into that difference are usually simple, and eroding or dilating
    each one alone succeeds where eroding their difference does not.

    Used twice so far, at both of the null offsets the IP-FC-12 sweep found. IP-FC-54: the
    frame web's erosion of the OML with its bores cut. IP-FC-57: the lightening region, where
    `erosion(OUTER, r) - dilation(BORES, r) - dilation(MATERIAL, r)` succeeds and the direct
    erosion of the assembled difference is null at every distance down to 0.01 mm.

    **The dilated operands are not merged**, and that is deliberate rather than an oversight of
    the IP-FC-52 rule. They are only ever `Part::Cut` operands, which removes the union of an
    overlapping compound correctly, and a merge is itself a boolean round trip -- the thing
    whose output OCCT's offset cannot always consume. Adding one here would risk reintroducing
    the failure this function exists to route around, to normalise a shape nothing offsets.
    """
    node = offset(doc, tag + 'ErodePos', positive, '-(' + radius + ')')
    for i, negative in enumerate(negatives):
        grown = offset(doc, '%sGrowNeg%d' % (tag, i), negative, radius)
        node = C._cut(doc, '%sErodeCut%d' % (tag, i), node, grown)
    return node


def fillet_inner(doc, tag, source, radius, reach, eroded=None):
    """`intersection() { offset(-r) offset(2r) offset(-r) children; children; }`.

    `eroded` replaces the leading `offset(-r)` when the caller can compute it a better way --
    `erode_difference` above, when `source` is a difference OCCT will not offset. It must be
    exactly `offset(-r)` of `source`; anything else silently changes the fillet.

    An opening followed by a closing, clipped to the input: it rounds **convex** corners and
    removes anything thinner than 2*radius. Never adds material.

    **The `2r` dilation is done as two dilations of `r`, and that is not cosmetic.** The two
    are the same operation -- dilating by a disc of radius r twice covers exactly the disc of
    radius 2r -- and they produce the same shape here to every digit that can be measured:
    area 7009.984015 mm2, 5 faces, 78 edges, either way. But only the split one can then be
    eroded. `Part::Offset2D` returns a **null shape** for `offset(-r)` of the single `+2r`
    dilation on the no-panel twin-boom bulkhead, and null at every distance tried down to
    `r/4`, under all three `Join` settings, after `removeSplitter`, after rebuilding the face
    from its own wires, and on the outer wire alone (IP-FC-57). Nothing about the *shape* is
    wrong; OCCT's own offset leaves the wire in a state its own offset cannot consume, and
    going round twice leaves it in one that can.

    Each dilation is merged before the next step. That is the multi-face overlap `offset`
    describes, and this chain is exposed to it by construction rather than by accident: the
    erosion at the head exists precisely to pinch the shape apart at anything narrower than
    2*radius, so its output is multi-face whenever the fillet does anything at all, and the
    dilations are then asked to grow those pieces back across the gap that separated them.
    `reach` sizes the rectangle the merge complements against and must strictly enclose the
    widest intermediate -- which reaches `radius` beyond the source, not `2 * radius`, the
    first erosion having taken the other half.
    """
    node = eroded if eroded is not None \
        else offset(doc, tag + 'ErodeA', source, '-(' + radius + ')')
    node = merge(doc, tag + 'MergeA',
                 offset(doc, tag + 'DilateA', node, radius), reach)
    node = merge(doc, tag + 'MergeB',
                 offset(doc, tag + 'DilateB', node, radius), reach)
    node = offset(doc, tag + 'ErodeB', node, '-(' + radius + ')')
    clip = C._owned(doc, 'Part::MultiCommon', tag + 'FilletInner')
    clip.Shapes = [node, source]
    return clip


def fillet_outer(doc, tag, source, radius, reach):
    """`union() { offset(-r) offset(r) children; children; }`.

    A closing unioned with the input: it fills **concave** corners and bridges gaps narrower
    than 2*radius. Never removes material.

    Its dilation is merged for the same reason `fillet_inner`'s is, though the exposure is
    weaker here: this one offsets the caller's own shape rather than an erosion, and every
    current caller hands it a single face. It is merged anyway because "the caller happens to
    pass one face" is not a property this function can check or enforce, and the failure it
    would produce is a silently oversized region rather than an error.
    """
    node = offset(doc, tag + 'DilateA', source, radius)
    node = merge(doc, tag + 'DilateMerge', node, reach)
    node = offset(doc, tag + 'ErodeA', node, '-(' + radius + ')')
    return union(doc, tag + 'FilletOuter', [node, source], reach)


def fragmented(shape):
    """True when two faces share an edge -- one region stored as several abutting patches.

    **Not the same as a disconnected region.** A shape can legitimately be several faces that
    touch nowhere: `boom_web_inner_shape` is two islands, one either side of the key pad, and
    OpenSCAD's is too. `Part::Offset2D` handles disjoint islands correctly -- it is adjacency
    it gets wrong, offsetting the shared interior edges as though they were boundary. So the
    invariant is "no shared edges", not "one face"; a face count would reject a correct shape
    and, worse, teach the reader to expect the wrong thing.

    Every edge appears once in `shape.Edges`, and once per face that uses it in the faces'
    own lists, so the two totals differ exactly when some edge is shared.
    """
    return sum(len(f.Edges) for f in shape.Faces) > len(shape.Edges)


def area(shape):
    return sum(f.Area for f in shape.Faces) if shape.Faces else float('nan')


def enclosed(doc, shape, reach_alias):
    """Margin between the shape and the rectangle `union` complements against.

    Positive means the union was not truncated. Zero or negative means it was, silently.
    """
    reach = float(doc.getObject('Params').get(reach_alias))
    bb = shape.BoundBox
    return min(reach - abs(v) for v in (bb.XMin, bb.XMax, bb.YMin, bb.YMax))


def report(doc, label, shape, ref, reach_alias, expect_bbox=None, tol=6.0e-5):
    """One measured shape against its OpenSCAD reference, with the 2D invariants checked.

    `tol` defaults to the faceting floor for a circle capped at 360 segments by `$fa = 1`,
    which is what almost every shape here is limited by. A shape whose area is mostly small
    circles is limited by `$fs = 0.1` instead and needs a looser floor -- see `boom_oml.REFS`.
    Raise it only for that reason, and say which circles and at what radius.
    """
    got = area(shape)
    d = got - ref
    bb = shape.BoundBox
    checks = []
    if fragmented(shape):
        checks.append('FRAGMENTED faces=%d sharing edges -- any offset downstream is wrong'
                      % len(shape.Faces))
    if enclosed(doc, shape, reach_alias) <= 1e-9:
        checks.append('TRUNCATED -- %s does not enclose it' % reach_alias)
    if abs(d) / ref > tol:
        checks.append('OVER TOLERANCE')
    if expect_bbox is not None:
        want = expect_bbox
        real = (bb.XMin, bb.YMin, bb.XMax, bb.YMax)
        if max(abs(a - b) for a, b in zip(real, want)) > 5.0e-4:
            checks.append('BBOX [%.4f, %.4f, %.4f, %.4f]' % real)
    print('  %-22s %13.7f %13.7f %+10.5f%%  %s'
          % (label, got, ref, 100 * d / ref, ' '.join(checks) if checks else 'ok'))
    return not checks
