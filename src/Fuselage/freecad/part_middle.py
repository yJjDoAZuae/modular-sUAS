"""IP-FC-5, slice 1: corner_middle in FreeCAD using Part:: primitives and booleans.

The constant-section run is the shared 2D profile extruded and nothing else, so matching
its volume proves the profile before any greeble geometry is attempted. The profile itself
lives in corner_common, because every other section of the corner extrudes the same one.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

from corner_common import Params, is_entry_point, out_path, report, section

REF_VOL = 4041.5795009


def build(p):
    z0 = 2 * p.bulkhead_thickness - p.eps
    h = p.unit_length / 2 - 2 * p.bulkhead_thickness + 2 * p.eps
    return section(p, z0, h)


def main():
    App.newDocument('part_middle')
    shape = build(Params())
    report('corner_middle', shape, REF_VOL)

    out = out_path('part_middle.step')
    shape.exportStep(out)
    print('  wrote   %s' % os.path.basename(out))


if is_entry_point(__name__):
    main()
