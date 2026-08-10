"""IP-FC-5, slice 2: corner_end in FreeCAD using Part:: primitives and booleans.

This is the greeble socket -- the cavity that receives the bulkhead's positive post -- and
it is the piece that actually exercises OQ-ARCH-1. The middle run is a prism and any
paradigm can extrude a prism; the socket is a revolved snap groove interrupted by a
half-space cut, which is where the two paradigms are expected to differ.

Compared against the isolated OpenSCAD render of `corner_end` at the driver's parameters.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

from corner_common import (Params, is_entry_point, out_path, report, section,
                           through_cut)

REF_VOL = 551.8157396


def nub_profile(p):
    """The revolved socket: an r=greeble_radius bore with the snap groove standing out to
    greeble_nub_radius over the middle third, ramped in and out by one wall thickness.

    Points are (radius, z) exactly as OpenSCAD's rotate_extrude reads a 2D polygon.
    """
    half_h = p.bulkhead_thickness / 2.0
    return [
        (0.0, 0.0),
        (p.greeble_radius, 0.0),
        (p.greeble_radius,
         half_h - p.greeble_nub_height / 2.0 - p.greeble_nub_thickness),
        (p.greeble_nub_radius, half_h - p.greeble_nub_height / 2.0),
        (p.greeble_nub_radius, half_h + p.greeble_nub_height / 2.0),
        (p.greeble_radius,
         half_h + p.greeble_nub_height / 2.0 + p.greeble_nub_thickness),
        (p.greeble_radius, p.bulkhead_thickness),
        (0.0, p.bulkhead_thickness),
    ]


def revolve(points):
    """Revolve a (radius, z) polygon a full turn about the z axis."""
    pts = [App.Vector(r, 0.0, z) for r, z in points]
    pts.append(pts[0])
    return Part.Face(Part.makePolygon(pts)).revolve(
        App.Vector(0, 0, 0), App.Vector(0, 0, 1), 360)


def wedge(p):
    """The half-space that interrupts the snap groove, so the socket has a mouth.

    A 2D polygon extruded centred on z, then rotated -45 degrees -- the same diagonal the
    profile is mirrored across, so the mouth opens along the corner's plane of symmetry.
    """
    depth = through_cut(p.bulkhead_thickness)
    poly = [
        (-(p.greeble_nub_radius + p.eps), -p.greeble_nub_radius),
        (p.greeble_nub_radius + p.eps, -p.greeble_nub_radius),
        (p.greeble_nub_radius + p.eps, 0.0),
        (p.longeron_radius + p.greeble_thickness, -p.greeble_nub_thickness),
        (-p.greeble_radius, -p.greeble_nub_thickness),
        (-(p.greeble_nub_radius + p.eps), 0.0),
    ]
    pts = [App.Vector(x, y, -depth / 2.0) for x, y in poly]
    pts.append(pts[0])
    prism = Part.Face(Part.makePolygon(pts)).extrude(App.Vector(0, 0, depth))
    return prism.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), -45)


def build(p):
    depth = through_cut(p.bulkhead_thickness)

    solid = section(p, 0.0, p.bulkhead_thickness + p.eps)

    # the through bore
    solid = solid.cut(Part.makeCylinder(p.greeble_radius, depth,
                                        App.Vector(0, 0, -depth / 2.0)))

    # the mouth: a square opening the bore to one side, on the mirror diagonal
    g = p.greeble_radius
    mouth = Part.makeBox(2 * g, 2 * g, depth, App.Vector(-2 * g, -g, -depth / 2.0))
    solid = solid.cut(mouth.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 45))

    # the snap groove, interrupted where the mouth is
    return solid.cut(revolve(nub_profile(p)).cut(wedge(p)))


def main():
    App.newDocument('part_end')
    shape = build(Params())
    report('corner_end', shape, REF_VOL)

    out = out_path('part_end.step')
    shape.exportStep(out)
    print('  wrote   %s' % os.path.basename(out))


if is_entry_point(__name__):
    main()
