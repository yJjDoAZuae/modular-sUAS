"""IP-FC-5: the whole fuselage_corner in Part::, assembled from the three ported sections.

fuselage_corner is end + transition + middle, unioned, then that half mirrored in z and
translated to unit_length -- the corner is symmetric about its mid-span, and the middle
run's eps overshoot is what makes the two halves overlap rather than merely touch.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import Params, is_entry_point, out_path, report
from part_end import build as build_end
from part_middle import build as build_middle
from part_transition import build as build_transition

REF_VOL = 10395.9608969


def build(p):
    lower = build_end(p).fuse(build_transition(p)).fuse(build_middle(p))
    upper = lower.mirror(App.Vector(0, 0, 0), App.Vector(0, 0, 1))
    upper.translate(App.Vector(0, 0, p.unit_length))
    return lower.fuse(upper).removeSplitter()


def main():
    App.newDocument('part_corner')
    shape = build(Params())
    ok = report('fuselage_corner', shape, REF_VOL)

    out = out_path('part_corner.step')
    shape.exportStep(out)
    print('  wrote   %s' % os.path.basename(out))
    return 0 if ok else 1


if is_entry_point(__name__):
    # The flush is not decoration: under `freecadcmd` a `sys.exit` with buffered stdout loses
    # the whole report, so the run looks like it printed nothing rather than like it failed.
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
