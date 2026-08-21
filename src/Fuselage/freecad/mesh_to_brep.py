"""Check a FreeCAD B-rep against an OpenSCAD mesh, without tessellating the B-rep.

IP-FC-33 trialled three shape-comparison methods the project did not use. Two earned their
place and are implemented here; the third is recorded in the plan rather than adopted.

**Why this is a better cross-engine tier than the one we had.** `compare_backends.py` also
compares the two engines, but it *meshes* the FreeCAD shape and compares mesh to mesh -- so
FreeCAD's tessellation sits inside the comparison as a third variable, and a difference could
be the model, the kernel, or the mesher. This measures the OpenSCAD mesh's points against the
FreeCAD B-rep **surface** directly. The B-rep is never tessellated, so the mesher drops out
and what is left is the geometry.

Measured 2026-08-18 on `U_1.0 end_bolt 3/16in`, bulkhead:

- **Deviation: max 0.000158 mm, mean 0.000025 mm** over 300 sampled points. The two kernels
  agree to under a fifth of a micron -- roughly 300x tighter than the 0.05 mm that is the
  smallest linear dimension this project cares about.
- **Volume: 6922.2727 mm^3 (OpenSCAD) against 6922.2805 (FreeCAD), 1.13e-06 relative.**
- Negative control, the same mesh against a *corner's* B-rep: max 57.310369 mm, mean 42.330773.
  Signal and noise are five orders of magnitude apart, so the threshold is not delicate.

**Sampling, and what a clean result is worth.** Points are taken evenly through the mesh's
vertex list rather than at random, so a run is reproducible without carrying a seed. As with
`tools/surface_distance.py`, a sample is a **lower bound**: it reports the largest deviation it
found, not the largest that exists. Cost is about 24 ms per point -- 300 points is 7 s, and a
whole-mesh check on a 29,000-triangle part would be tens of minutes. Sample deliberately.

**A trap this module exists to have already fallen into.** The first trial selected the
document's largest solid as "the part", which picked a construction blank -- 5,538,767 mm^3
against a real part of 6,922 -- and every method then compared bounding boxes while looking
like it compared parts. The tip node is the object nothing else depends on (`InList` empty),
which is what `tip_shape()` uses, and `--expect` exists so the selection is checked against a
known volume rather than trusted.

Usage, under freecadcmd, from the repository root:

    freecadcmd src/Fuselage/freecad/mesh_to_brep.py --pass --doc=part.FCStd
                                                    --pass --mesh=reference.stl
                                                    [--pass --points=300]
                                                    [--pass --expect=6922.2727]
                                                    [--pass --tol=0.001]
"""
import os
import sys

import FreeCAD as App
import Part

try:
    import Mesh
except ImportError:
    Mesh = None

DEFAULT_POINTS = 300
DEFAULT_TOL_MM = 1e-3      # 50x under the 0.05 mm floor, and 6x over the worst measured
TIP_CHECK_REL = 1e-3


def options(argv):
    out = {}
    for a in argv:
        if a.startswith('--') and '=' in a:
            k, v = a[2:].split('=', 1)
            out[k] = v
    return out


def say(*a):
    print(*a)
    sys.stdout.flush()


def refuse(message):
    """Fail loudly. freecadcmd discards a SystemExit's message, so write it out first."""
    sys.stderr.write('\nmesh_to_brep: %s\n' % message)
    sys.stderr.flush()
    sys.stdout.flush()
    raise SystemExit(1)


def tip_shape(doc_path, expect=None):
    """The document's tip solid -- the object nothing else consumes.

    Not the largest solid. See the module docstring: that heuristic silently selects a
    construction blank, and every comparison downstream then looks fine while meaning
    nothing.
    """
    doc = App.openDocument(doc_path)
    tips = [o for o in doc.Objects
            if getattr(o, 'Shape', None) is not None and o.Shape.Solids and not o.InList]
    if not tips:
        refuse('no tip solid in %s -- every solid is consumed by another object' % doc_path)
    shape = max(tips, key=lambda o: len(o.Shape.Faces)).Shape
    if expect is not None:
        rel = abs(shape.Volume - expect) / max(abs(expect), 1e-9)
        say('  tip volume %.4f against expected %.4f (%.2e relative)' % (shape.Volume, expect, rel))
        if rel > TIP_CHECK_REL:
            refuse('the tip solid is %.4f mm^3 but %.4f was expected, %.2e relative.\n'
                   'That is the wrong object, not a tolerance problem -- a construction blank '
                   'reads as a part and every number below would be meaningless.'
                   % (shape.Volume, expect, rel))
    return shape


def deviation(mesh_path, shape, n):
    """Max and mean distance from sampled mesh points to the B-rep surface, in mm."""
    if Mesh is None:
        refuse('FreeCAD Mesh module unavailable')
    points = Mesh.Mesh(mesh_path).Points
    if not points:
        refuse('%s has no points' % mesh_path)
    step = max(1, len(points) // n)
    picked = [p.Vector for i, p in enumerate(points) if i % step == 0][:n]
    worst, total = 0.0, 0.0
    for v in picked:
        d = Part.Vertex(v).distToShape(shape)[0]
        worst = max(worst, d)
        total += d
    return len(picked), worst, total / len(picked), len(points)


def main():
    opt = options(sys.argv[1:])
    for required in ('doc', 'mesh'):
        if required not in opt:
            refuse('--%s is required' % required)
    n = int(opt.get('points', DEFAULT_POINTS))
    tol = float(opt.get('tol', DEFAULT_TOL_MM))
    expect = float(opt['expect']) if opt.get('expect') else None

    shape = tip_shape(opt['doc'], expect)
    say('  %s: %d faces, %d solid(s), volume %.6f mm^3'
        % (os.path.basename(opt['doc']), len(shape.Faces), len(shape.Solids), shape.Volume))

    used, worst, mean, total = deviation(opt['mesh'], shape, n)
    say('  %s: %d points, %d sampled' % (os.path.basename(opt['mesh']), total, used))
    say('  deviation  max %.6f mm   mean %.6f mm   threshold %.6f mm' % (worst, mean, tol))
    say('  coverage   %.1f%% of mesh points -- a sample is a lower bound' % (100.0 * used / total))

    if worst > tol:
        say('  B-REP AND MESH DISAGREE')
        return 1
    say('  agree within threshold (nothing found to differ, which is not proof none does)')
    return 0


raise SystemExit(main())
