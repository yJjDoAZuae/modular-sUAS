"""Volume and bounding box of a binary or ASCII STL, by the divergence theorem."""
import struct
import sys


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
    return len(tris), abs(vol), lo, hi


def main():
    for path in sys.argv[1:]:
        n, vol, lo, hi = measure(path)
        print('%s' % path)
        print('  triangles = %d' % n)
        print('  volume    = %.7f' % vol)
        print('  bbox      = [%.4f, %.4f, %.4f, %.4f, %.4f, %.4f]'
              % (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]))


# Only when run directly. Importing this under freecadcmd must not touch sys.argv, where
# argv[1] is the *script* path, not an STL.
if __name__ == '__main__':
    main()
