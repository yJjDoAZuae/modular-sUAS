"""The package's kernel-unit boundary: SI on this side, millimeters on the other.

**Why this exists rather than `freecad/si.py`.** `si.py` is the port's boundary and does the same
job, but it imports `FreeCAD` and `Part`, and `tests/test_wall_measure_sweep.py` asserts that no
module here imports anything outside numpy, the standard library and `units` -- so that the
package stays loadable under FreeCAD's embedded Python 3.11, which is where `check_cowl_interior`
runs it. OQ-ARCH-24 settled that by admitting `units` to the allowlist, not `si`. This module is
therefore `si.py`'s surface over `units` alone: it never imports a kernel, and it reads the kernel
objects its callers already pass in.

**The one rule.** Everything stored, compared or returned in this package is SI. A kernel object's
own attributes are millimeters, because OpenCASCADE has no units and FreeCAD's convention is
millimeters, so every read of `.BoundBox`, `.Length`, `.Volume` or `.Area` goes through a function
here, and every `z` handed back to a kernel call goes through `mm`. A conversion that happens
anywhere else is the defect this module exists to make unnecessary -- IP-FC-163's own worked
example is `sever_doses`, which was handing `ci.z_extent`'s meters to a millimeter scan and
getting 24 stations and sections off the end of the part for its trouble.

**Names end in the unit they carry**, which is what `tools/unit_regime.py` screens for: `_m`,
`_m2`, `_m3`, `_rad`. A function returning a kernel figure says `mm` in its name instead.
"""
import units

#: Re-exported so a caller needs one import rather than two, and so the factor itself is never
#: restated in this package. `units.py` is the single definition; see its docstring on why a
#: second one is the thing to avoid.
MM_PER_M = units.MM_PER_M
M_PER_MM = units.M_PER_MM
MM2_PER_M2 = units.MM2_PER_M2
MM3_PER_M3 = units.MM3_PER_M3


def mm(value_m):
    """Meters to millimeters, for handing a figure to a kernel call."""
    return value_m * MM_PER_M


def m(value_mm):
    """Millimeters to meters, for taking a figure off a kernel object."""
    return value_mm * M_PER_MM


def vec_mm(App, x_m, y_m, z_m):
    """An `App.Vector` in kernel units from SI components.

    `App` is passed in rather than imported, the same way the three kernel-touching modules in
    this package already take it, which is what keeps the allowlist true.
    """
    return App.Vector(mm(x_m), mm(y_m), mm(z_m))


def point_m(point):
    """`(x_m, y_m, z_m)` from a kernel point or vector."""
    return (m(point.x), m(point.y), m(point.z))


def length_m(shape):
    """A kernel edge's or wire's `.Length`, in meters."""
    return m(float(shape.Length))


def area_m2(shape):
    """A kernel shape's `.Area`, in square meters."""
    return float(shape.Area) * M_PER_MM * M_PER_MM


def volume_m3(shape):
    """A kernel shape's `.Volume`, in cubic meters.

    **A difference detector, not a measure**, wherever this package uses it -- `inputs`' own note
    records why, and converting it does not change that.
    """
    return float(shape.Volume) / MM3_PER_M3


def bbox_m(shape):
    """`(x_lo, x_hi, y_lo, y_hi, z_lo, z_hi)` in meters from a kernel `BoundBox`.

    A plain tuple rather than a named structure, because this package has no dataclass layer and
    every caller wants two or six numbers rather than an object.

    **A box on these solids is an outer bound and nothing more.** `corpus.sectioning_extent`
    exists because of it, and three modules have had a station grid placed outside the material by
    trusting one -- see `cowl_interior.z_extent`. Converting the units does not make it tight.
    """
    bb = shape.BoundBox
    return (m(bb.XMin), m(bb.XMax), m(bb.YMin), m(bb.YMax), m(bb.ZMin), m(bb.ZMax))


def z_extent_m(shape):
    """`(z_lo_m, z_hi_m)` from a kernel `BoundBox`, which is the pair almost every caller wants.

    **Reads only `ZMin` and `ZMax`, not the whole box through `bbox_m`.** Asking for six
    attributes to return two is a needless coupling, and it has a cost a test found: the fake
    shapes in `tests/test_wall_measure_corpus.py` supply a `BoundBox` with a `z` extent and
    nothing else, because that is all the station grid is about, and routing this through
    `bbox_m` made every one of them raise `AttributeError` on `XMin`. A stub should have to
    provide what the function needs and no more.
    """
    box = shape.BoundBox
    return (m(box.ZMin), m(box.ZMax))
