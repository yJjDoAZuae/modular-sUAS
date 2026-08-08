"""IP-FC-5: compare corner_end band by band, so a discrepancy is localised in z.

A single volume figure can hide a feature placed at the wrong height -- material gained in
one band cancelling material lost in another. Slicing both models at the heights the snap
groove is *defined* by removes that possibility: bore, lower ramp, groove, upper ramp, bore.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

from corner_common import Params
from measure import measure
from part_end import build

HERE = os.path.dirname(os.path.abspath(__file__))
BANDS = [(0, 1.2, 'bore'), (1.2, 2, 'lower ramp'), (2, 4, 'groove'),
         (4, 4.8, 'upper ramp'), (4.8, 6.01, 'bore + eps')]


def fmt(z):
    return ('%g' % z)


shape = build(Params())

print('%-12s %-10s %14s %14s %12s %9s'
      % ('band', 'z', 'OpenSCAD', 'FreeCAD', 'delta', 'rel'))
tot_ref = tot_fc = 0.0
for z0, z1, label in BANDS:
    stl = os.path.join(HERE, 'band_%s_%s.stl' % (fmt(z0), fmt(z1)))
    _, ref, _, _ = measure(stl)

    slab = Part.makeBox(100, 100, z1 - z0, App.Vector(-50, -50, z0))
    got = shape.common(slab).Volume

    tot_ref += ref
    tot_fc += got
    d = got - ref
    print('%-12s %-10s %14.6f %14.6f %+12.6f %+8.4f%%'
          % (label, '%g-%g' % (z0, z1), ref, got, d, 100 * d / ref))

d = tot_fc - tot_ref
print('%-12s %-10s %14.6f %14.6f %+12.6f %+8.4f%%'
      % ('TOTAL', '', tot_ref, tot_fc, d, 100 * d / tot_ref))
