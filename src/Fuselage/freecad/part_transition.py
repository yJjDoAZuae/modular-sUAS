"""IP-FC-5, slice 3: corner_transition in FreeCAD using Part:: primitives and booleans.

The transition takes the socket bore at greeble_radius down to the longeron bore over one
bulkhead thickness, and relieves the diagonal so the longeron can enter. It is the section
with the most transform composition -- an extrusion rotated about two axes then translated
-- so it is the one most likely to expose a convention mismatch between the two systems.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

from corner_common import Params, is_entry_point, report, section

REF_VOL = 607.6699024


def relief(p):
    """The diagonal relief that lets the longeron enter the tapered bore.

    Built exactly as OpenSCAD composes it: a polygon extruded along +z, rotated 90 degrees
    about x so the extrusion runs along -y, then -45 degrees about z onto the mirror
    diagonal. Innermost transform first, so the order here is the reverse of the source's
    nesting.
    """
    depth = p.longeron_radius + p.greeble_thickness + p.greeble_tolerance
    bt, eps, lr = p.bulkhead_thickness, p.eps, p.longeron_radius
    poly = [
        (p.greeble_radius, -eps),
        (lr + p.longeron_tolerance, 0.75 * bt + eps),
        (lr / 2 ** 0.5, bt + eps),
        (-lr / 2 ** 0.5, bt + eps),
        (-(lr + p.longeron_tolerance), 0.75 * bt + eps),
        (-p.greeble_radius, -eps),
    ]
    pts = [App.Vector(x, y, 0.0) for x, y in poly]
    pts.append(pts[0])
    shape = Part.Face(Part.makePolygon(pts)).extrude(App.Vector(0, 0, depth))
    shape.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 90)
    shape.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), -45)
    return shape


def build(p):
    z0 = p.bulkhead_thickness                     # the module's own translate
    solid = section(p, z0, p.bulkhead_thickness)

    # the bore tapering from the socket down to the longeron
    solid = solid.cut(Part.makeCone(
        p.greeble_radius, p.longeron_radius + p.longeron_tolerance,
        p.bulkhead_thickness + 2 * p.eps, App.Vector(0, 0, z0 - p.eps)))

    tool = relief(p)
    tool.translate(App.Vector(0, 0, z0 - p.eps))
    return solid.cut(tool)


def main():
    App.newDocument('part_transition')
    shape = build(Params())
    report('corner_transition', shape, REF_VOL)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'part_transition.step')
    shape.exportStep(out)
    print('  wrote   %s' % os.path.basename(out))


if is_entry_point(__name__):
    main()
