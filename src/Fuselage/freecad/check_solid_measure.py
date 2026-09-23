"""IP-TEST-10 (doc/implementation/test_coverage.md): unit-level regression for solid_measure.py.

`solid_measure.py` exists because `Shape.Volume`/`Face.Area`/`Shape.BoundBox` are measurably
wrong on this project's B-spline solids (its own docstring gives the numbers). It has no
`main()` and no committed caller-independent check -- only `soak_compare.py`/
`soak_cowl_shell.py`, both real cowl builds too expensive to run just to exercise a
measurement library. This exercises the library directly against small, exact primitives (a
cube, a box) where every answer has a closed form -- volume, area and the difference between
two solids are all known exactly, which a real cowl never gives you.

Run: freecadcmd check_solid_measure.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

import solid_measure as sm
from corner_common import is_entry_point

TOL = 1e-6


def main():
    failures = []

    def check(label, got, want, tol=TOL):
        ok = abs(got - want) <= tol * max(1.0, abs(want))
        print('  %-52s %-20s %-20s  %s' % (label, got, want, 'ok' if ok else 'FAIL'))
        if not ok:
            failures.append(label)

    # ------------------------------------------------------------
    # mesh_volume / open_edges -- a 10x10x10 box tessellates exactly (six planar quads need
    # no curvature approximation), so its mesh volume is exactly 1000.0 at any deflection and
    # it must report a closed surface.
    # ------------------------------------------------------------
    box = Part.makeBox(10.0, 10.0, 10.0)
    vol, facets = sm.mesh_volume(box, 0.1)
    check('mesh_volume of a 10mm cube', vol, 1000.0)
    check('a box tessellates to at least 12 triangles (2 per face)', facets >= 12, True)

    points, facet_count, unpaired = sm.open_edges(box, 0.1)
    check('open_edges finds no unpaired edges on a closed box', unpaired, 0)
    check('open_edges facet count matches mesh_volume\'s', facet_count, facets)

    # ------------------------------------------------------------
    # converged_volume -- a box's mesh does not change with deflection, so it must converge
    # on the very first comparison (the second deflection tried) to exactly 1000.0.
    # ------------------------------------------------------------
    conv_vol, deflection, tri = sm.converged_volume(box)
    check('converged_volume of the same cube', conv_vol, 1000.0)
    check('converged_volume used the second (not the last) deflection tried',
          deflection, sm.DEFLECTIONS[1], tol=1e-9)

    # NotConverged -- a box's mesh volume is exactly 1000.0 at EVERY deflection (a planar
    # face tessellates exactly), so even tol=0.0 converges on the box instantly; that is not
    # a way to reach this path at all. A cylinder's mesh volume genuinely keeps changing as
    # deflection is refined (finer facets approximate the round wall better each time), so
    # tol=0.0 genuinely never converges there.
    cyl = Part.makeCylinder(5.0, 10.0)
    raised = False
    try:
        sm.converged_volume(cyl, tol=0.0)
    except sm.NotConverged:
        raised = True
    check('converged_volume raises NotConverged when it truly cannot converge', raised, True)

    # ------------------------------------------------------------
    # wire_area -- shoelace on a planar face's outer wire. The box's top face is a 10x10
    # square with a known exact area, and a face whose normal is NOT axis-aligned (a
    # 45-degree wedge cut) confirms the "project onto whichever plane it's most parallel to"
    # logic, not just the trivial axis-aligned case.
    # ------------------------------------------------------------
    # `discretize(Number=400)`'s 400 points do not land exactly on the square's four corners,
    # so even a straight-edged boundary picks up a tiny polygon-vs-square shortfall -- 0.003%
    # measured here. wire_area's own docstring already names this ("a slight under-estimate"),
    # so the tolerance reflects the method, not a looser standard for this one check.
    top_face = max(box.Faces, key=lambda f: f.CenterOfMass.z)
    check('wire_area of the box\'s top face', sm.wire_area(top_face), 100.0, tol=1e-3)

    wedge = box.cut(Part.makeBox(20.0, 20.0, 20.0, App.Vector(0, 0, 0),
                                 App.Vector(1, 0, 0)).rotate(App.Vector(0, 0, 0),
                                                             App.Vector(0, 1, 0), 45.0))
    slanted = [f for f in wedge.Faces
              if abs(f.Surface.Axis.normalize().z) < 0.9 and abs(f.Surface.Axis.z) > 1e-6]
    if slanted:
        # The cut face is a right triangle in its own plane; area is derivable from its
        # world-space vertices independently of wire_area's own projection logic.
        area = sm.wire_area(slanted[0])
        check('wire_area of a non-axis-aligned face is positive and finite',
              area > 0.0 and area < 200.0, True)
    else:
        print('  (no slanted face on this cut -- skipped, not a failure)')

    # ------------------------------------------------------------
    # surface_difference -- two identical boxes must show a mean gap of exactly zero (the
    # surfaces coincide everywhere); two boxes of different sizes must show a real, positive
    # gap. Small sample count: the shapes are simple enough that even 50 samples is exact
    # for the identical case and clearly nonzero for the different one.
    # ------------------------------------------------------------
    box_a = Part.makeBox(10.0, 10.0, 10.0)
    box_b = Part.makeBox(10.0, 10.0, 10.0)
    est, err, area, mean_gap, max_gap = sm.surface_difference(box_a, box_b, samples=50)
    check('surface_difference of two identical boxes: mean gap', mean_gap, 0.0, tol=1e-9)
    check('surface_difference of two identical boxes: estimate', est, 0.0, tol=1e-9)
    check('surface_difference reports the box\'s true surface area (6 * 100)', area, 600.0)

    box_c = Part.makeBox(12.0, 10.0, 10.0)          # 2mm taller in x -- a real difference
    est2, _err2, _area2, mean_gap2, max_gap2 = sm.surface_difference(box_a, box_c, samples=200)
    print('  %-52s %-20s %-20s  %s' % ('surface_difference of a genuinely different box',
                                       '%.4f mean, %.4f max' % (mean_gap2, max_gap2),
                                       '> 0', 'ok' if mean_gap2 > 0.0 else 'FAIL'))
    if not mean_gap2 > 0.0:
        failures.append('surface_difference did not detect a genuine size difference')

    # ------------------------------------------------------------
    # converged_difference -- two identical boxes: difference converges to exactly 0. Two
    # boxes with different face counts (one cut, one not): TopologyMismatch, per the
    # module's own stated precondition.
    # ------------------------------------------------------------
    diff, cd_deflection, relative = sm.converged_difference(box_a, box_b)
    check('converged_difference of two identical boxes', diff, 0.0, tol=1e-9)

    raised_topo = False
    try:
        sm.converged_difference(box_a, wedge)
    except sm.TopologyMismatch:
        raised_topo = True
    check('converged_difference raises TopologyMismatch on unequal face counts',
          raised_topo, True)

    print('')
    print('check_solid_measure: %d failure(s)' % len(failures))
    for f in failures:
        print('  FAILED: %s' % f)
    return 1 if failures else 0


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
