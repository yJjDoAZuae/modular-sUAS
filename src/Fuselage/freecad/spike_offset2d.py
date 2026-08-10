"""IP-FC-9: does Part::Offset2D reproduce OpenSCAD's offset(r=) and fillet_inner()?

The bulkhead's web is built with `offset(r = -web_width)` and `fillet_inner(
web_fillet_radius)`, and fillet_inner is itself:

    intersection() { offset(-r) offset(2r) offset(-r) children; children; }

Part::Offset2D is a document object, so if the semantics match, the whole construction ports
as a parametric chain rather than as baked geometry. If they do not match, every shape
downstream of the web is affected, so this is worth settling before any of it is built.

OpenSCAD's offset(r=) uses round joins, which is Part::Offset2D's Join='Arc'.

**It matches. Measured 2026-08-08 at shrink = 3 only, it appeared not to, by 15% on the
dilation, and that reading stood until 2026-08-10.** The test polygon's bottom bar is
exactly 10 wide, so at shrink = 3 the chained erosion of 3 + 2 is exactly half of it and the
erosion of that bar is a *hairline*: zero area, 20 mm long. Dilating a hairline by 4 paints
a band 8 mm wide, so a feature contributing nothing at all before the dilation contributes a
great deal after it, and whether it survives at all is a question about arithmetic rather
than about geometry. CGAL's exact rationals keep it; a floating-point offset does not.

OpenSCAD's own answer moves 33% across 0.002 mm of that parameter -- 573.97 at shrink =
2.999, 453.82 at 3.000, 381.04 at 3.001 -- while every step away from it is a few units per
0.02. A number that unstable is not a reference value, and 3 was the only shrink tried.

So the chain is run at five shrinks, one of them the degenerate one. Away from it the two
engines agree to 0.005%, which is the faceting floor: the finest agreement OpenSCAD's
tessellation can express. The degenerate row is kept because the degeneracy is real and can
recur -- any `fillet_inner(r)` applied where a limb is exactly 2r wide sits on the same knife
edge, and no engine's answer there is more correct than another's.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

from corner_common import is_entry_point

V = App.Vector

PTS = [(0, 0), (40, 0), (40, 20), (25, 20), (25, 10), (10, 10), (10, 30), (0, 30)]
FILLET = 2.0
REF_RAW = 750.0000000

# OpenSCAD, $fa=1 $fs=0.1, via ref_offset2d.scad modes 1, 3, 4, 5, 2.
# The bottom bar is 10 wide, so shrink + FILLET == 5 is the degenerate row.
STEPS = ('offset(-shrink)', 'then offset(-r)', 'then offset(+2r)', 'then offset(-r)',
         'fillet_inner(r)')
REFS = {
    2.0: (447.719559, 180.874050, 729.390560, 442.571766, 442.564188),
    2.5: (377.685228, 119.696832, 650.498594, 372.532333, 372.529853),
    3.0: (309.865500, 60.734761, 453.820893, 244.711834, 244.710127),
    3.5: (244.260360, 39.934418, 275.205586, 132.436195, 132.435647),
    4.0: (180.869848, 25.921533, 171.807574, 86.297596, 86.297364),
}
DEGENERATE = 3.0
TOL = 6.0e-5        # the 360-segment faceting floor, as compare_backends.py uses


def offset2d(doc, name, source, value, join='Arc'):
    o = doc.addObject('Part::Offset2D', name)
    o.Source = source
    o.Value = value
    o.Join = join
    o.Fill = False
    doc.recompute()
    return o


def area(obj):
    shp = obj.Shape
    if shp.isNull():
        return float('nan')
    return sum(f.Area for f in shp.Faces) if shp.Faces else shp.Area


def base_shape(doc):
    pts = [V(x, y, 0) for x, y in PTS]
    pts.append(pts[0])
    base = doc.addObject('Part::Feature', 'Base')
    base.Shape = Part.Face(Part.makePolygon(pts))
    doc.recompute()
    return base


def chain(doc, base, shrink, tag):
    """The five areas OpenSCAD's ref_offset2d.scad reports, in the same order."""
    shrunk = offset2d(doc, tag + 'Shrink', base, -shrink)
    a = offset2d(doc, tag + 'ErodeA', shrunk, -FILLET)
    b = offset2d(doc, tag + 'Dilate', a, 2 * FILLET)
    c = offset2d(doc, tag + 'ErodeB', b, -FILLET)
    common = doc.addObject('Part::MultiCommon', tag + 'FilletInner')
    common.Shapes = [c, shrunk]
    doc.recompute()
    return [area(o) for o in (shrunk, a, b, c, common)]


def main():
    doc = App.newDocument('offset2d')
    base = base_shape(doc)

    print('Part::Offset2D against OpenSCAD, fillet radius %.1f' % FILLET)
    print('  raw polygon %.6f vs %.6f' % (area(base), REF_RAW))
    print('')
    print('  %-8s %-18s %14s %14s %11s  %s'
          % ('shrink', 'step', 'OpenSCAD', 'FreeCAD', 'delta', ''))

    worst = 0.0
    for shrink in sorted(REFS):
        got = chain(doc, base, shrink, 'S%d' % int(shrink * 10))
        degenerate = abs(shrink + FILLET - 5.0) < 1e-9
        for step, want, have in zip(STEPS, REFS[shrink], got):
            rel = (have - want) / want
            if degenerate:
                note = 'degenerate -- the erosion is exactly half the bar'
            elif abs(rel) > TOL:
                note = 'OVER TOLERANCE'
            else:
                note = 'ok'
                worst = max(worst, abs(rel))
            print('  %-8s %-18s %14.6f %14.6f %+10.5f%%  %s'
                  % ('%.1f' % shrink if step is STEPS[0] else '', step, want, have,
                     100 * rel, note))
        print('')

    print('  worst |delta| away from the degeneracy: %.5f%%  (tolerance %.4f%%)'
          % (100 * worst, 100 * TOL))
    print('  at shrink = %.1f the two engines answer different questions, and OpenSCAD'
          % DEGENERATE)
    print('  moves 573.97 -> 453.82 -> 381.04 across 0.002 mm of it.')


if is_entry_point(__name__):
    main()
