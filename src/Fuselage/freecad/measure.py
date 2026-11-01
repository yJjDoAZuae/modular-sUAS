"""Volume and bounding box of a binary or ASCII STL, by the divergence theorem.

**The file is this module's unit boundary (IP-FC-160).** An STL carries no unit metadata and is
millimeters by convention -- it is what every slicer assumes and what this project's own exports
write -- so `measure` converts at the read and returns SI. Nothing downstream has to know what
unit the file was written in, which is the whole point of putting the crossing here.

`units` rather than `si`: this module touches no FreeCAD API at all, so it stays importable
under any interpreter, and `units` is the half of the conversion layer that has no FreeCAD
import in it.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from units import MM3_PER_M3, m_to_mm, mm_to_m                                   # noqa: E402


def read_stl(path):
    with open(path, 'rb') as f:
        head = f.read(5)
        f.seek(0)
        if head == b'solid':
            txt = f.read().decode('ascii', 'replace').split()
            tris, cur = [], []
            for i, tok in enumerate(txt):
                if tok == 'vertex':
                    cur.append(tuple(float(x) for x in txt[i + 1:i + 4]))
                    if len(cur) == 3:
                        tris.append(cur)
                        cur = []
            if tris:
                return tris
            f.seek(0)
        f.seek(80)
        n = struct.unpack('<I', f.read(4))[0]
        tris = []
        for _ in range(n):
            d = struct.unpack('<12fH', f.read(50))
            tris.append([d[3:6], d[6:9], d[9:12]])
        return tris


def measure(path):
    """`(triangles, volume_m3, lo_m, hi_m)` for an STL. See the module docstring on the unit.

    The volume is converted once at the return rather than each vertex on the way in: it is the
    same number, and three multiplications instead of nine per triangle on a mesh of up to
    170 000 of them.
    """
    tris = read_stl(path)
    vol = 0.0
    lo = [float('inf')] * 3
    hi = [float('-inf')] * 3
    for a, b, c in tris:
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        for p in (a, b, c):
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    return (len(tris), abs(vol) / MM3_PER_M3,
            [mm_to_m(v) for v in lo], [mm_to_m(v) for v in hi])


def main():
    # argv[1] under freecadcmd is this script, not an STL. Dropping .py arguments is what
    # makes `freecadcmd measure.py foo.stl` and `python measure.py foo.stl` do the same
    # thing -- without it the first one tries to parse measure.py as a mesh and fails with
    # "unpack requires a buffer of 50 bytes", which reads like a corrupt STL.
    # corner_common.script_args() states this once for everything else, but importing it here
    # would drag in FreeCAD, and this module deliberately runs under plain python so an STL
    # can be measured without a kernel. `--pass` is dropped for the same reason as there:
    # freecadcmd forwards the token as well as the value.
    for path in [a for a in sys.argv[1:] if a != '--pass' and not a.endswith('.py')]:
        n, vol_m3, lo_m, hi_m = measure(path)
        print('%s' % path)
        print('  triangles = %d' % n)
        # Printed in millimeters: an STL is a millimeter file and whoever runs this is
        # comparing it against a slicer or a drawing.
        print('  volume    = %.7f mm3' % (vol_m3 * MM3_PER_M3))
        print('  bbox      = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f] mm'
              % tuple(m_to_mm(v) for v in list(lo_m) + list(hi_m)))


# Only when run directly -- importing this from a check script must not consume its argv.
# freecadcmd names the script it is handed after the file rather than '__main__', so the
# plain test is not enough on its own. Not imported from corner_common: this file is also
# run under the project virtualenv, which has no FreeCAD to import.
if __name__ == '__main__' or 'measure.py' in [os.path.basename(a) for a in sys.argv]:
    main()
