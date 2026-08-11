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


def offset(doc, name, source, value, join='Arc'):
    """OpenSCAD's `offset(r = value)`. Round joins, which is Join='Arc'.

    Measured faithful to 0.00456% across the chain, including `fillet_inner` -- see
    spike_offset2d.py, and note that the 2026-08-08 reading of 19% was taken at a degenerate
    parameter value and is wrong.
    """
    node = C._owned(doc, 'Part::Offset2D', name)
    node.Source = source
    node.Join = join
    node.Fill = False
    node.setExpression('Value', value)
    return node


def fillet_inner(doc, tag, source, radius):
    """`intersection() { offset(-r) offset(2r) offset(-r) children; children; }`.

    An opening followed by a closing, clipped to the input: it rounds **convex** corners and
    removes anything thinner than 2*radius. Never adds material.
    """
    node = offset(doc, tag + 'ErodeA', source, '-(' + radius + ')')
    node = offset(doc, tag + 'Dilate', node, '2 * (' + radius + ')')
    node = offset(doc, tag + 'ErodeB', node, '-(' + radius + ')')
    clip = C._owned(doc, 'Part::MultiCommon', tag + 'FilletInner')
    clip.Shapes = [node, source]
    return clip


def fillet_outer(doc, tag, source, radius, reach):
    """`union() { offset(-r) offset(r) children; children; }`.

    A closing unioned with the input: it fills **concave** corners and bridges gaps narrower
    than 2*radius. Never removes material.
    """
    node = offset(doc, tag + 'DilateA', source, radius)
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
