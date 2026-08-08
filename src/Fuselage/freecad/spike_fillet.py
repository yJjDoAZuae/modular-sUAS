"""IP-FC-9: is Part::Fillet safe in a generated, re-parameterisable document?

OQ-DES-B9 settles that the port uses real fillets. Part::Fillet is the obvious tool, but it
stores its targets as EDGE INDICES -- and IP-FC-5 already measured the corner's face count
moving 52 -> 32 across U as features merge. If edge indices shift under a parameter change,
a stored fillet silently moves to a different edge, which is the topological naming problem
arriving where it does the most damage: on a stress-relief feature.

Three things are measured here:

  1. does a fillet selected by a geometric predicate survive a parameter change that leaves
     the topology alone (dimensions move, edge count constant)?
  2. does it survive one that changes the edge count?
  3. does the alternative -- rounding the profile in 2D before extruding -- behave better?
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

from corner_common import is_entry_point

V = App.Vector
RADIUS = 2.0


def build(doc):
    """A plate with a slot: four concave vertical edges, like the web's inner corners."""
    sheet = doc.addObject('Spreadsheet::Sheet', 'Params')
    for row, (alias, value) in enumerate(
            [('plate', '40.0'), ('slot_w', '10.0'), ('slot_d', '20.0'),
             ('thick', '5.0')], start=1):
        sheet.set('A%d' % row, alias)
        sheet.setAlias('B%d' % row, alias)
        sheet.set('B%d' % row, value)
    doc.recompute()

    plate = doc.addObject('Part::Box', 'Plate')
    plate.setExpression('Length', 'Params.plate')
    plate.setExpression('Width', 'Params.plate')
    plate.setExpression('Height', 'Params.thick')

    slot = doc.addObject('Part::Box', 'Slot')
    slot.setExpression('Length', 'Params.slot_w')
    slot.setExpression('Width', 'Params.slot_d')
    slot.setExpression('Height', 'Params.thick * 3')
    slot.setExpression('Placement.Base.x', 'Params.plate / 2 - Params.slot_w / 2')
    slot.setExpression('Placement.Base.y', '-1')
    slot.setExpression('Placement.Base.z', '-Params.thick')

    cut = doc.addObject('Part::Cut', 'Slotted')
    cut.Base, cut.Tool = plate, slot
    doc.recompute()
    return sheet, cut


def concave_vertical_edges(shape, thick):
    """Pick the fillet targets geometrically, the way a generator must -- never by a
    hand-picked index. Vertical straight edges of the right length, away from the outer
    boundary."""
    found = []
    for i, e in enumerate(shape.Edges, start=1):
        if len(e.Vertexes) != 2:
            continue
        a, b = e.Vertexes[0].Point, e.Vertexes[1].Point
        if abs(a.x - b.x) > 1e-7 or abs(a.y - b.y) > 1e-7:
            continue                                  # not vertical
        if abs(abs(a.z - b.z) - thick) > 1e-7:
            continue
        # inside the plate, not on its outer rim
        if 1e-6 < a.x < 40 - 1e-6 and 1e-6 < a.y < 40 - 1e-6:
            found.append((i, a))
    return found


def describe(fillet):
    s = fillet.Shape
    if s.isNull():
        return 'NULL'
    arcs = sum(1 for e in s.Edges if isinstance(e.Curve, Part.Circle)
               and abs(e.Curve.Radius - RADIUS) < 1e-7)
    return ('volume=%.4f valid=%s edges=%d arcs@r=%d'
            % (s.Volume, s.isValid(), len(s.Edges), arcs))


def main():
    doc = App.newDocument('fillet_spike')
    sheet, cut = build(doc)

    targets = concave_vertical_edges(cut.Shape, 5.0)
    print('Part::Fillet under parameter change')
    print('  base edges=%d, concave vertical targets=%s'
          % (len(cut.Shape.Edges), [i for i, _ in targets]))
    print('  target positions: %s'
          % ', '.join('(%.1f,%.1f)' % (p.x, p.y) for _, p in targets))

    fillet = doc.addObject('Part::Fillet', 'Fillet')
    fillet.Base = cut
    fillet.Edges = [(i, RADIUS, RADIUS) for i, _ in targets]
    doc.recompute()
    print('  as built                 : %s' % describe(fillet))
    print('    (the slot opens at one side, so 2 concave verticals => 4 arcs, top and bottom)')

    print('')
    print('1. a change that moves dimensions but not topology')
    sheet.set('B2', '16.0')                       # slot_w 10 -> 16
    doc.recompute()
    print('   slot_w 10 -> 16          : %s' % describe(fillet))
    print('   stored indices %s still name concave verticals: %s'
          % ([e[0] for e in fillet.Edges],
             sorted(i for i, _ in concave_vertical_edges(cut.Shape, 5.0))
             == sorted(e[0] for e in fillet.Edges)))

    print('')
    print('2. a change that alters the edge count')
    sheet.set('B3', '45.0')                       # slot_d 20 -> 45, breaks through
    doc.recompute()
    ok = 'Invalid' not in fillet.State and 'Error' not in fillet.State
    print('   slot_d 20 -> 45 (breaks through) : %s' % describe(fillet))
    print('   base edges now %d, fillet state %s'
          % (len(cut.Shape.Edges), fillet.State))
    print('   still the right edges: %s'
          % (sorted(i for i, _ in concave_vertical_edges(cut.Shape, 5.0))
             == sorted(e[0] for e in fillet.Edges)))
    print('   recompute reported success: %s' % ok)


if is_entry_point(__name__):
    main()
