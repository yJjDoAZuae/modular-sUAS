"""IP-FC-158: the port's unit boundary, and the only module that hands numbers to the kernel.

**Unit regime of this file: it is the boundary, so it names both sides explicitly.**

The project standard is SI -- meters, seconds, kilograms, radians (`doc/guidelines/general.md`).
OpenCASCADE, which is what `Part` is, works in millimeters. Those two facts need exactly one
place to meet, and `doc/guidelines/general.md` says where it is not: *"Never call a conversion
function inside geometry or analysis code -- if you need one there, the boundary is in the wrong
place."* Scattering `units.m_to_mm` through `cowl_interior` would satisfy the letter of the
standard and defeat its purpose, because a factor written in a hundred places is a hundred
chances to write it once as a multiply and once as a divide.

So the boundary is given a shape: **this module owns the kernel calls that carry numbers, takes
SI in, and gives SI back.** Geometry modules compose these, hold meters, and never see a factor.

    geometry modules (SI)  ->  THIS MODULE  ->  Part / OpenCASCADE (mm)

**A shape is a foreign object, like an open file.** `box_m(...)` returns a real `Part.Shape`
whose own coordinates are millimeters, because that is what the kernel stores. That is not a
leak: the shape is the kernel's, and every *number* going in or coming out crosses here. It is
why the readers below exist rather than letting a caller write `shape.Volume` -- that attribute
is mm3, and `volume_m3` is the same figure in the project's units.

**What this module does not do.** It does not wrap calls that carry no numbers. `Part.Face(wire)`,
`shape.cut(tool)`, `shape.removeSplitter()` and the rest pass no dimensioned value, so wrapping
them would add indirection without moving a unit. The rule for a caller is narrow and checkable:
**if you are writing a number into the kernel or reading one out, it goes through here.**

**Why `units.py` is still separate.** That module is pure arithmetic with no FreeCAD import, so
the pytest tier can test it in the project venv. This one cannot be imported without the kernel,
so its own regression lives in `check_si.py` under `freecadcmd`, and the pytest tier checks its
source instead. Keeping the factor where it can be tested cheaply is worth the second file.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import FreeCAD as App
import Part

from units import (M_PER_MM, MM2_PER_M2, MM3_PER_M3, MM_PER_M, deg_to_rad, m_to_mm, mm_to_m,
                   rad_to_deg)

#: `MM2_PER_M2` and `MM3_PER_M3` are re-exported from `units` rather than defined here, so the
#: modules that touch no FreeCAD API -- `measure.py` reading an STL -- can have them too. They
#: are named in `__all__` below because `si.MM3_PER_M3` is how the port spells them at 40-odd
#: call sites and moving them should not move the spelling.


# ---------------------------------------------------------------------------------------------
# Kernel-domain tolerances.
#
# These are millimeters and they stay millimeters, because they are not dimensions of the part:
# they are arguments to OpenCASCADE, calibrated against its own behavior. `Precision::Confusion`
# is 1e-7 mm, and a fuzz value is meaningful only relative to that. The guidelines already draw
# this line for the FEM stack -- mm/N/MPa is internally self-consistent, so it is treated as file
# interface and converted on the way out -- and a boolean's fuzz is the same case.
#
# They live here rather than in the geometry module that uses them for one reason: a geometry
# module holding a millimeter number is indistinguishable, to a reader or to `unit_regime.py`,
# from a geometry module that was never converted.
# ---------------------------------------------------------------------------------------------

#: Fuzz for the rib cut, in millimeters. Chosen empirically and not free of side effects at any
#: size: 1.0e-6 left the near-tangent split in place; 1.0e-5 closed it into one valid solid and
#: moved the real piece's volume by 0.0006 mm3 in 122902.77, a relative 4.9e-9 -- a snap of
#: near-tangent geometry rather than a bulk change; 1.0e-4 and above moved tens of mm3, well past
#: what a tangency snap should cost. It is three orders below `cowl_interior.RIB_RESIDUE_M3` and
#: four below `TAU_M`, so it cannot be mistaken for tolerating a real gap.
RIB_CUT_FUZZ_MM = 1.0e-5

#: The retry ladder for that cut, in millimeters, coarsening only as far as a value whose own
#: displacement stays well inside the wall's acceptance tolerance.
CUT_FUZZ_LADDER_MM = (1.0e-5, 1.0e-4, 1.0e-3, 1.0e-2)


# ---------------------------------------------------------------------------------------------
# Points and vectors.
# ---------------------------------------------------------------------------------------------

def vec_m(x_m, y_m=0.0, z_m=0.0):
    """An `App.Vector` in the kernel's millimeters, from meters.

    This is the most-used crossing in the port -- 138 `App.Vector` constructions at the time the
    boundary was drawn -- so it is the one most worth having a single implementation of.
    """
    return App.Vector(m_to_mm(x_m), m_to_mm(y_m), m_to_mm(z_m))


def point_m(vector):
    """A kernel vector or vertex as `(x_m, y_m, z_m)` in meters.

    Accepts an `App.Vector`, anything with a `.Point` (a `Part.Vertex`), or a 3-sequence, because
    all three turn up where the kernel hands a position back and a caller should not have to know
    which one it got.
    """
    point = getattr(vector, 'Point', vector)
    x = getattr(point, 'x', None)
    if x is None:
        x, y, z = point[0], point[1], point[2]
    else:
        y, z = point.y, point.z
    return (mm_to_m(x), mm_to_m(y), mm_to_m(z))


def points_m(vectors):
    """`point_m` over a sequence, as a list."""
    return [point_m(vector) for vector in vectors]


def vecs_m(points):
    """`vec_m` over a sequence of `(x, y, z)` in meters, as a list."""
    return [vec_m(p[0], p[1], p[2]) for p in points]


# ---------------------------------------------------------------------------------------------
# Primitives. Every argument is SI; every return is a kernel shape.
# ---------------------------------------------------------------------------------------------

def box_m(length_m, width_m, height_m, placement=None, direction=None):
    """`Part.makeBox` from meters."""
    args = [m_to_mm(length_m), m_to_mm(width_m), m_to_mm(height_m)]
    if placement is not None:
        args.append(placement)
    if direction is not None:
        args.append(direction)
    return Part.makeBox(*args)


def _positional(sizes, placement, direction, angle_rad):
    """`Part.make*`'s trailing `(pnt, dir, angle)` arguments, filled in from the left.

    The kernel takes them positionally, so an angle cannot be passed without a point and a
    direction before it -- omitting them and appending the angle third makes the angle the
    point and raises `argument 3 must be Base.Vector`. Each one defaults to the value the
    kernel itself would have used, so supplying a later argument does not change the shape.
    """
    args = list(sizes)
    if placement is None and direction is None and angle_rad is None:
        return args
    args.append(App.Vector(0, 0, 0) if placement is None else placement)
    if direction is None and angle_rad is None:
        return args
    args.append(App.Vector(0, 0, 1) if direction is None else direction)
    if angle_rad is not None:
        args.append(rad_to_deg(angle_rad))
    return args


def cylinder_m(radius_m, height_m, placement=None, direction=None, angle_rad=None):
    """`Part.makeCylinder` from meters and radians.

    The kernel's angle argument is degrees, which is the other half of this boundary and is as
    easy to get wrong as the length -- a cylinder built with radians reads as a 57x error in
    sweep angle and still produces a valid solid.
    """
    sizes = (m_to_mm(radius_m), m_to_mm(height_m))
    return Part.makeCylinder(*_positional(sizes, placement, direction, angle_rad))


def cone_m(radius1_m, radius2_m, height_m, placement=None, direction=None, angle_rad=None):
    """`Part.makeCone` from meters and radians."""
    sizes = (m_to_mm(radius1_m), m_to_mm(radius2_m), m_to_mm(height_m))
    return Part.makeCone(*_positional(sizes, placement, direction, angle_rad))


def line_m(start_m, end_m):
    """`Part.makeLine` between two `(x, y, z)` in meters."""
    return Part.makeLine(vec_m(*start_m), vec_m(*end_m))


def polygon_m(points):
    """`Part.makePolygon` over `(x, y, z)` points in meters."""
    return Part.makePolygon(vecs_m(points))


def prism_m(points, z0_m, height_m):
    """A closed polygon of `(x, y)` points in meters, extruded from `z0_m` through `height_m`.

    The port's most common composite: every cut in the corner's profile is a prism of constant
    cross-section, so the profile is built by extruding and differencing in 3D rather than
    taking 2D booleans first. It lives here rather than in a geometry module because it is a
    numeric constructor -- the polygon's points and the extrusion height are both lengths.

    The polygon is closed for the caller, which is what every call site did by hand.
    """
    pts = [vec_m(x, y, z0_m) for x, y in points]
    pts.append(pts[0])
    return Part.Face(Part.makePolygon(pts)).extrude(vec_m(0.0, 0.0, height_m))


def circle_m(radius_m, center_m=None, normal=None):
    """`Part.Circle` from meters."""
    if center_m is None:
        return Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), m_to_mm(radius_m))
    normal = App.Vector(0, 0, 1) if normal is None else normal
    return Part.Circle(vec_m(*center_m), normal, m_to_mm(radius_m))


def bspline_curve_m(points, **kwargs):
    """A `Part.BSplineCurve` interpolating `(x, y, z)` points in meters."""
    curve = Part.BSplineCurve()
    curve.interpolate(vecs_m(points), **kwargs)
    return curve


def offset_shape_m(shape, offset_m, tolerance_m, **kwargs):
    """`Part.makeOffsetShape` from meters."""
    return Part.makeOffsetShape(shape, m_to_mm(offset_m), m_to_mm(tolerance_m), **kwargs)


def mesh_from_shape_m(shape, linear_deflection_m, angular_deflection_rad=None, **kwargs):
    """`Part.meshFromShape` from meters and radians.

    The mesher's own arguments are millimeters and degrees. A deflection is a length even though
    it is a setting rather than a dimension of the part, so it is stored in meters like any
    other length and converted here.
    """
    kwargs['LinearDeflection'] = m_to_mm(linear_deflection_m)
    if angular_deflection_rad is not None:
        kwargs['AngularDeflection'] = rad_to_deg(angular_deflection_rad)
    return Part.meshFromShape(Shape=shape, **kwargs)


# ---------------------------------------------------------------------------------------------
# Readers. Every return is SI.
# ---------------------------------------------------------------------------------------------

def volume_m3(shape):
    """A shape's volume in cubic meters."""
    return shape.Volume / MM3_PER_M3


def area_m2(shape):
    """A shape's area in square meters."""
    return shape.Area / MM2_PER_M2


def length_m(shape):
    """A shape's length in meters -- an edge's arc length, a wire's perimeter."""
    return mm_to_m(shape.Length)


def center_of_mass_m(shape):
    """A shape's center of mass as `(x_m, y_m, z_m)`."""
    return point_m(shape.CenterOfMass)


def distance_m(shape, other):
    """The minimum distance between two shapes, in meters.

    Returns the distance only. `distToShape` also hands back the points and the sub-elements
    that realize it; `closest_m` below returns those, in meters, for the callers that need them.
    """
    return mm_to_m(shape.distToShape(other)[0])


def closest_m(shape, other):
    """`(distance_m, point_on_shape_m, point_on_other_m)` for the closest approach."""
    distance, pairs, _info = shape.distToShape(other)
    first, second = pairs[0]
    return (mm_to_m(distance), point_m(first), point_m(second))


class BoundBoxM(object):
    """A bounding box in meters, with the same member names the kernel's own box uses.

    A wrapper rather than a tuple because `BoundBox` is read by name at 80 sites in the port --
    `.ZMin`, `.XLength`, `.Center` -- and a tuple would force every one of them to be rewritten
    into indexing, which is a worse diff and a worse read.
    """

    def __init__(self, box):
        self.XMin = mm_to_m(box.XMin)
        self.YMin = mm_to_m(box.YMin)
        self.ZMin = mm_to_m(box.ZMin)
        self.XMax = mm_to_m(box.XMax)
        self.YMax = mm_to_m(box.YMax)
        self.ZMax = mm_to_m(box.ZMax)

    @property
    def XLength(self):
        return self.XMax - self.XMin

    @property
    def YLength(self):
        return self.YMax - self.YMin

    @property
    def ZLength(self):
        return self.ZMax - self.ZMin

    @property
    def Center(self):
        return ((self.XMin + self.XMax) / 2.0,
                (self.YMin + self.YMax) / 2.0,
                (self.ZMin + self.ZMax) / 2.0)

    def as_tuple(self):
        """`(xmin, ymin, zmin, xmax, ymax, zmax)` in meters, which is what `units` compares."""
        return (self.XMin, self.YMin, self.ZMin, self.XMax, self.YMax, self.ZMax)

    def __repr__(self):
        return ('BoundBoxM(%.9g, %.9g, %.9g, %.9g, %.9g, %.9g)'
                % self.as_tuple())


def bbox_m(shape):
    """A shape's bounding box in meters."""
    return BoundBoxM(shape.BoundBox)


def value_at_m(curve, parameter):
    """A curve's point at a parameter, in meters. The parameter itself is not a length."""
    return point_m(curve.valueAt(parameter))


def vertexes_m(shape):
    """Every vertex position of a shape, in meters."""
    return [point_m(vertex.Point) for vertex in shape.Vertexes]


# ---------------------------------------------------------------------------------------------
# Section and tolerance helpers that carry a number.
# ---------------------------------------------------------------------------------------------

def tol_mm(tolerance_m):
    """A tolerance in meters as the millimeters a kernel argument wants.

    The one escape hatch, for a kernel call this module does not wrap. It is named so that it
    reads as a boundary crossing at the call site, and so that `unit_regime.py` and a reviewer
    can both find every place one happens.
    """
    return m_to_mm(tolerance_m)


def mm(value_m):
    """Meters to the kernel's millimeters. The same escape hatch for a length."""
    return m_to_mm(value_m)


def m(value_mm):
    """The kernel's millimeters back to meters."""
    return mm_to_m(value_mm)


__all__ = [
    'MM2_PER_M2', 'MM3_PER_M3', 'RIB_CUT_FUZZ_MM', 'CUT_FUZZ_LADDER_MM',
    'vec_m', 'point_m', 'points_m', 'vecs_m',
    'box_m', 'cylinder_m', 'cone_m', 'line_m', 'polygon_m', 'prism_m', 'circle_m',
    'bspline_curve_m', 'offset_shape_m', 'mesh_from_shape_m',
    'volume_m3', 'area_m2', 'length_m', 'center_of_mass_m', 'distance_m', 'closest_m',
    'BoundBoxM', 'bbox_m', 'value_at_m', 'vertexes_m',
    'tol_mm', 'mm', 'm', 'deg_to_rad', 'rad_to_deg', 'M_PER_MM', 'MM_PER_M',
]
