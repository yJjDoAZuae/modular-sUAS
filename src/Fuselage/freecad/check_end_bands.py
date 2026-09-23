"""IP-FC-5: compare corner_end band by band, so a discrepancy is localised in z.

A single volume figure can hide a feature placed at the wrong height -- material gained in
one band cancelling material lost in another. Slicing both models at the heights the snap
groove is *defined* by removes that possibility: bore, lower ramp, groove, upper ramp, bore.

**The OpenSCAD side of the comparison has to be rendered first.** This script only reads
those meshes; it does not produce them. One per band, from `ref_end_band.scad`, into `out/`:

    for b in "0 1.2" "1.2 2" "2 4" "4 4.8" "4.8 6.01"; do
      set -- $b
      openscad -o "out/band_$1_$2.stl" -D "z0=$1" -D "z1=$2" ref_end_band.scad
    done
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App
import Part

from corner_common import Params, is_entry_point, out_path
from measure import measure
from part_end import build

HERE = os.path.dirname(os.path.abspath(__file__))
BANDS = [(0, 1.2, 'bore'), (1.2, 2, 'lower ramp'), (2, 4, 'groove'),
         (4, 4.8, 'upper ramp'), (4.8, 6.01, 'bore + eps')]

#: Relative tolerance per band, matching check_tree.py/check_regenerate.py's own bar for the
#: same corner geometry.
TOL = 1e-4


def fmt(z):
    return ('%g' % z)


def main():
    """Found while auditing IP-TEST-10 (doc/implementation/test_coverage.md): this whole
    script was top-level module code with no verdict of any kind -- not even a `main()` to
    return one from -- so it always exited 0 regardless of how far any band's volume was off.
    Wrapped into `main()` with a real per-band and total tolerance check, plus the standard
    flush-before-`sys.exit()` guard.
    """
    shape = build(Params())

    print('%-12s %-10s %14s %14s %12s %9s  %s'
          % ('band', 'z', 'OpenSCAD', 'FreeCAD', 'delta', 'rel', 'checks'))
    tot_ref = tot_fc = 0.0
    bad = 0
    for z0, z1, label in BANDS:
        stl = out_path('band_%s_%s.stl' % (fmt(z0), fmt(z1)))
        if not os.path.isfile(stl):
            # Said plainly, because the bare errno names a path in out/ and reads like the
            # script should have written it. It should not -- see the docstring. Written to
            # stderr and flushed rather than raised: freecadcmd discards a SystemExit's
            # message, so `raise SystemExit(text)` here produced no output at all.
            sys.stderr.write(
                'missing %s\nRender the OpenSCAD bands into out/ first; the command is in '
                "this script's docstring.\n" % os.path.basename(stl))
            sys.stderr.flush()
            return 1
        _, ref, _, _ = measure(stl)

        slab = Part.makeBox(100, 100, z1 - z0, App.Vector(-50, -50, z0))
        got = shape.common(slab).Volume

        tot_ref += ref
        tot_fc += got
        d = got - ref
        off = abs(d) / ref > TOL
        if off:
            bad += 1
        print('%-12s %-10s %14.6f %14.6f %+12.6f %+8.4f%%  %s'
              % (label, '%g-%g' % (z0, z1), ref, got, d, 100 * d / ref,
                 'OVER TOLERANCE' if off else 'ok'))

    d = tot_fc - tot_ref
    total_off = abs(d) / tot_ref > TOL
    print('%-12s %-10s %14.6f %14.6f %+12.6f %+8.4f%%  %s'
          % ('TOTAL', '', tot_ref, tot_fc, d, 100 * d / tot_ref,
             'OVER TOLERANCE' if total_off else 'ok'))

    ok = bad == 0 and not total_off
    print('%s' % ('ok' if ok else 'FAIL -- %d band(s) over tolerance' % bad))
    return 0 if ok else 1


if is_entry_point(__name__):
    _code = main()
    sys.stdout.flush()
    sys.exit(_code)
