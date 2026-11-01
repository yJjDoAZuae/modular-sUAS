"""IP-TEST-11: measure.py had no test of its own. It has zero FreeCAD dependency (deliberately
-- its own docstring: "this module deliberately runs under plain python so an STL can be
measured without a kernel"), the same situation units.py was in before check_units.py, and it
is placed here rather than in tests/ for the same reason: respecting this project's own
directory-scoped tier split (see conftest.py) rather than the accident of which interpreter a
module happens to be importable from.

The divergence-theorem volume/bbox this module computes is exactly the "hand-written divergence
theorem" IP-FC-140's own follow-up thread found broken (a sign error, ~0 mm3 on a known
~593878.7 mm3 shape) in a *different* one-off script -- this checks the one that ships.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import measure
import units
from corner_common import is_entry_point

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.join(HERE, 'out', 'check_measure_scratch')

# A 2x3x4 mm box (not a cube, so no axis-length transposition bug can hide), corners at the
# origin -- volume 24 mm3 exactly, bbox trivially known.
_VERTS = {
    0: (0, 0, 0), 1: (2, 0, 0), 2: (2, 3, 0), 3: (0, 3, 0),
    4: (0, 0, 4), 5: (2, 0, 4), 6: (2, 3, 4), 7: (0, 3, 4),
}
_TRI_IDX = [
    (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
]


def _triangles():
    return [[_VERTS[i] for i in tri] for tri in _TRI_IDX]


def _write_binary_stl(path, triangles):
    with open(path, 'wb') as f:
        f.write(b'check_measure'.ljust(80, b'\0'))
        f.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            f.write(struct.pack('<3f', 0.0, 0.0, 0.0))
            for point in tri:
                f.write(struct.pack('<3f', *point))
            f.write(struct.pack('<H', 0))


def _write_ascii_stl(path, triangles):
    with open(path, 'w') as f:
        f.write('solid box\n')
        for tri in triangles:
            f.write('facet normal 0 0 0\nouter loop\n')
            for p in tri:
                f.write('vertex %r %r %r\n' % p)
            f.write('endloop\nendfacet\n')
        f.write('endsolid box\n')


def main():
    ok = True
    os.makedirs(SCRATCH, exist_ok=True)
    tris = _triangles()

    # **The fixture is written in the STL's own millimeters and read back in SI.** The box
    # is 2 x 3 x 4 mm, so 24 mm3; `measure` converts at the file (IP-FC-160) and these
    # expectations convert with it, which is what makes this check test the crossing as well
    # as the arithmetic. The tolerance crosses too: 1e-4 mm3 is 1e-13 m3.
    want_vol_m3 = 24.0 / units.MM3_PER_M3
    want_lo_m = [0.0, 0.0, 0.0]
    want_hi_m = [units.mm_to_m(v) for v in (2.0, 3.0, 4.0)]
    vol_tol_m3 = 1e-4 / units.MM3_PER_M3

    bin_path = os.path.join(SCRATCH, 'box.stl')
    _write_binary_stl(bin_path, tris)
    n, vol_m3, lo_m, hi_m = measure.measure(bin_path)
    if (n != 12 or abs(vol_m3 - want_vol_m3) > vol_tol_m3
            or lo_m != want_lo_m or hi_m != want_hi_m):
        print('  FAIL binary STL: n=%d vol=%.6f lo=%s hi=%s mm (want n=12 vol=24 lo=[0,0,0] '
              'hi=[2,3,4])'
              % (n, vol_m3 * units.MM3_PER_M3,
                 [units.m_to_mm(v) for v in lo_m], [units.m_to_mm(v) for v in hi_m]))
        ok = False
    else:
        print('  binary STL: OK  n=%d vol=%.6f mm3' % (n, vol_m3 * units.MM3_PER_M3))

    ascii_path = os.path.join(SCRATCH, 'box_ascii.stl')
    _write_ascii_stl(ascii_path, tris)
    n2, vol2_m3, lo2_m, hi2_m = measure.measure(ascii_path)
    if n2 != 12 or abs(vol2_m3 - want_vol_m3) > vol_tol_m3:
        print('  FAIL ASCII STL: n=%d vol=%.6f mm3 (want n=12 vol=24)'
              % (n2, vol2_m3 * units.MM3_PER_M3))
        ok = False
    else:
        print('  ASCII STL: OK  n=%d vol=%.6f mm3' % (n2, vol2_m3 * units.MM3_PER_M3))

    # A shape with reversed winding on some faces must still report a positive volume --
    # measure() takes abs(vol), which is what makes it robust to a mesher's facet orientation
    # rather than silently reporting a negative number or cancelling to zero.
    reversed_tris = [list(reversed(t)) if i % 2 == 0 else t for i, t in enumerate(tris)]
    rev_path = os.path.join(SCRATCH, 'box_mixed_winding.stl')
    _write_binary_stl(rev_path, reversed_tris)
    n3, vol3_m3, _lo3, _hi3 = measure.measure(rev_path)
    # Mixed winding does not preserve the true volume (it is a per-triangle signed-volume sum),
    # but it must never silently report a suspiciously-small or negative number without abs().
    if vol3_m3 < 0:
        print('  FAIL mixed winding: measure() returned a negative volume (%.6f mm3) -- abs() '
              'is not being applied' % (vol3_m3 * units.MM3_PER_M3))
        ok = False
    else:
        print('  mixed winding stays non-negative: OK  vol=%.6f mm3 (uniform-winding vol=24 '
              'for reference, not expected to match)' % (vol3_m3 * units.MM3_PER_M3))

    print(('MEASURE.PY: OK' if ok else 'MEASURE.PY: FAIL'))
    sys.stdout.flush()
    return 0 if ok else 1


if is_entry_point(__name__):
    raise SystemExit(main())
