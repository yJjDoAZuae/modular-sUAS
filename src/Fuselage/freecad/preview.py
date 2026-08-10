"""Render a generated FreeCAD part to PNGs for visual inspection.

Volume agreement says two solids enclose the same amount of space. It does not say they are
the same shape, and it certainly does not say the shape is *right* -- that judgement needs
eyes on the part. This exports a generated shape to a mesh and renders it through
[`stl_preview`](../tools/stl_preview.py), the software rasterizer the OpenSCAD sweep already
uses, so FreeCAD output and OpenSCAD output are drawn by the same renderer with the same
camera and can be compared directly rather than impressionistically.

Run it under freecadcmd:

    freecadcmd preview.py                 # the corner, three views, plus the OpenSCAD ref
    freecadcmd preview.py corner tip      # a named part and node

Tessellation is a *setting*, not a property of the B-rep, so DEVIATION is stated here rather
than left to a default -- the mesh is for looking at, and a coarse one would show facets that
are not in the model.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))

import FreeCAD as App

from corner_common import is_entry_point, out_path

# Angular and linear deviation for the display mesh. Fine enough that curvature reads as
# curvature; nothing here is dimensional.
DEVIATION = 0.05
ANGULAR_DEG = 5.0

# Three views: the sweep's standard camera, then straight down the print axis, then a low
# angle that shows the z-varying features in profile.
VIEWS = [
    ('iso', None),
    ('top', (0.0, 0.0, 0.0)),
    ('front', (90.0, 0.0, 0.0)),
]


def export_png(shape, stem, outdir):
    """Mesh a shape and render each view. Returns the paths written."""
    import stl_preview

    stl_path = os.path.join(outdir, stem + '.stl')
    shape.exportStl(stl_path)

    tris = stl_preview.load_stl(stl_path)
    written = []
    for name, rot in VIEWS:
        png = os.path.join(outdir, '%s_%s.png' % (stem, name))
        kw = {} if rot is None else {'rot_deg': rot}
        stl_preview.write_png(png, stl_preview.render(tris, **kw))
        written.append(png)
    print('  %-22s %6d triangles -> %s' % (stem, len(tris),
                                           ', '.join(os.path.basename(p)
                                                     for p in written)))
    return written


def main():
    outdir = out_path('preview')
    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    args = [a for a in sys.argv[1:] if not a.endswith('.py')]
    part = args[0] if args else 'corner'

    print('Preview renders -> %s' % outdir)

    if part == 'corner':
        import corner_tree
        doc = App.newDocument('preview_corner')
        tip = corner_tree.emit(doc)
        doc.recompute()
        export_png(tip.Shape, 'corner_freecad', outdir)

        # the OpenSCAD render of the same part, through the same renderer, for comparison
        ref = os.path.join(HERE, 'ref_corner.stl')
        if os.path.exists(ref):
            import stl_preview
            tris = stl_preview.load_stl(ref)
            for name, rot in VIEWS:
                kw = {} if rot is None else {'rot_deg': rot}
                stl_preview.write_png(
                    os.path.join(outdir, 'corner_openscad_%s.png' % name),
                    stl_preview.render(tris, **kw))
            print('  %-22s %6d triangles -> corner_openscad_*.png'
                  % ('corner_openscad', len(tris)))
        else:
            print('  (no ref_corner.stl beside this script, so no OpenSCAD comparison)')
    else:
        print('  unknown part %r' % part)


if is_entry_point(__name__):
    main()
