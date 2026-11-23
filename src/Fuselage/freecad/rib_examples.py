"""OQ-DES-CW40: build a cowl with a chosen rib dilation, as a mesh to load into a slicer.

Test and measurement only. The part is built by the production builder for its kind, from the
module's own rows with `U` set, and meshed at the deflection `build_part.py` uses. The one change
is the rib dilation, swapped through `cowl_interior`'s probe seam (`wall_measure.probe`) for the
duration of the build: `planar` is `rib_hull.planar_tools`, `hull` is `rib_hull.tools`, and `none`
is the construction as it ships.

The dilation only enters the shelled kinds, `tail_shell` and `nose_cowl_shell`. The print kinds,
`tail` and `nose_cowl`, are the notched blanks the slicer spirals in vase mode; they have no rib
dilation in them and come out the same whatever `--dilate` says.

    freecadcmd rib_examples.py --pass --kind=tail_shell --pass --u=3.0 --pass --dilate=planar
        --pass --out=out/rib_examples/tail_shell_U3_planar.stl

No `.FCStd` is written: opened later, the document would recompute with the shipped ribs, which
is not the part the mesh shows. The B-rep is written beside the mesh instead.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App                                                    # noqa: E402

import build_part                                                        # noqa: E402
import cowl_interior as ci                                               # noqa: E402
import cowl_tree                                                         # noqa: E402
import si                                                                # noqa: E402
from corner_common import is_entry_point                                 # noqa: E402
from station_gaps import with_u                                          # noqa: E402
from wall_measure import probe as wm_probe                               # noqa: E402

#: kind -> (its parameter rows, its builder), as each kind's own module pairs them.
KINDS = {
    'tail': (cowl_tree.PARAMS_TAIL, cowl_tree.tail_cowl),
    'nose_cowl': (cowl_tree.PARAMS_NOSE_COWL, cowl_tree.nose_cowl),
    'tail_shell': (cowl_tree.PARAMS_TAIL_SHELL, cowl_tree.tail_shell),
    'nose_cowl_shell': (cowl_tree.PARAMS_NOSE_COWL_SHELL, cowl_tree.nose_cowl_shell),
}

DILATIONS = ('none', 'planar', 'hull')


def dilation(name):
    """The `Probe(dilate=...)` hook for `name`; `None` for the shipped dilation."""
    if name not in DILATIONS:
        raise SystemExit('--dilate=%s: one of %s' % (name, ', '.join(DILATIONS)))
    if name == 'none':
        return None
    import rib_hull
    return rib_hull.planar_tools if name == 'planar' else rib_hull.tools


def build(kind, u, dilate):
    """The finished part's shape, built with `dilate`'s ribs."""
    params, builder = KINDS[kind]
    doc = App.newDocument('rib_examples')
    probe = wm_probe.Probe(dilate=dilation(dilate))
    with wm_probe.installed(ci, probe=probe):
        tip = cowl_tree.emit(doc, None, with_u(params, u), builder)
    return tip.Shape


def main():
    opt = {}
    for arg in sys.argv[1:]:
        if arg.startswith('--') and '=' in arg:
            name, _, value = arg[2:].partition('=')
            opt[name] = value
    for name in ('kind', 'u', 'out'):
        if name not in opt:
            raise SystemExit('missing --%s' % name)
    if opt['kind'] not in KINDS:
        raise SystemExit('--kind=%s: one of %s' % (opt['kind'], ', '.join(sorted(KINDS))))
    kind, u, dilate = opt['kind'], float(opt['u']), opt.get('dilate', 'none')
    started = time.time()
    shape = build(kind, u, dilate)
    problems = []
    if not shape.isValid():
        problems.append('invalid shape')
    if len(shape.Solids) != 1:
        problems.append('%d solids' % len(shape.Solids))
    if problems:
        print('rib_examples: %s U=%g %s: %s' % (kind, u, dilate, '; '.join(problems)))
        sys.stdout.flush()
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(opt['out'])), exist_ok=True)
    deflection = build_part.export_deflection(kind, {'U': u})
    facets = build_part.write_mesh(shape, opt['out'], deflection)
    shape.exportBrep(os.path.splitext(opt['out'])[0] + '.brep')
    print('rib_examples: %s U=%g ribs %s: %.3f mm3, %d facets at %.5f mm, %.0f s -> %s'
          % (kind, u, dilate, si.volume_m3(shape) * si.MM3_PER_M3, facets, si.mm(deflection),
             time.time() - started, opt['out']))
    sys.stdout.flush()
    return 0


if is_entry_point(__name__):
    raise SystemExit(main())
