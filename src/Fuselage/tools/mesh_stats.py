"""Measure and compare STL meshes by their geometric properties.

Generated `.stl` and `.scad` output is not stable byte-for-byte: facet counts shift
with library versions, floating-point rounding differs, and the same solid can be
tessellated more than one way. Comparing files directly therefore reports
differences that are not differences. Comparing measured properties -- triangle
count, enclosed volume, bounding box -- compares the geometry itself.

Direct measurement rather than a boolean difference is also a hard requirement
here, not a preference: CGAL raises an assertion violation when these particular
meshes are compared with `difference()`, so booleans are not trustworthy on this
geometry.

**Truncation detection is the other half of this module's job.** A binary STL
declares its triangle count in the header, so a file whose length disagrees with
that count is provably incomplete. This matters because a crashed or killed render
leaves a partial `.stl` that every existence check treats as finished -- which is
exactly how a 2.88 MB fragment of a 17.5 MB tail was nearly recorded as a
successful part.

Originally written for a migration tool that has since been discarded. See the
guidelines on keeping capability in the durable code.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

# Binary STL layout: an 80-byte header, a uint32 triangle count, then 50 bytes per
# facet (3 normal floats, 9 vertex floats, 2 attribute bytes).
_HEADER_BYTES = 84
_FACET_BYTES = 50


class TruncatedMesh(ValueError):
    """An STL that is provably incomplete, rather than merely unreadable."""


def load_triangles(path: str | Path) -> np.ndarray:
    """Return an (n, 3, 3) array of triangle vertices from a binary or ASCII STL.

    Raises TruncatedMesh when the file is demonstrably a partial write. Detecting
    that here means every caller -- verification, comparison, preview rendering --
    inherits the check rather than each having to remember it.
    """
    path = Path(path)
    data = path.read_bytes()

    if data[:5].lower() == b"solid" and b"facet normal" in data[:2000]:
        return _load_ascii(data, path)

    if len(data) < _HEADER_BYTES:
        raise TruncatedMesh(f"{path}: too short to be an STL ({len(data)} bytes)")

    count = struct.unpack("<I", data[80:84])[0]
    expected = _HEADER_BYTES + _FACET_BYTES * count
    if len(data) < expected:
        raise TruncatedMesh(
            f"{path}: truncated binary STL -- header claims {count:,} triangles "
            f"({expected:,} bytes) but the file is {len(data):,} bytes"
        )

    record = np.dtype([("n", "<3f4"), ("v", "<9f4"), ("attr", "<u2")])
    facets = np.frombuffer(data, dtype=record, count=count, offset=_HEADER_BYTES)
    return facets["v"].reshape(-1, 3, 3).astype(np.float64)


def _load_ascii(data: bytes, path: Path) -> np.ndarray:
    """Parse an ASCII STL, rejecting partial writes.

    OpenSCAD emits ASCII here, which is the weaker format to validate: binary
    declares its triangle count in the header, so any truncation is provable, while
    ASCII truncation is only visible if it happens to land mid-triangle -- two
    cases in three. The `endsolid` terminator closes that gap. It is written last,
    so its absence means the writer did not finish, whatever the vertex count says.
    """
    text = data.decode("utf-8", "replace")

    if not text.rstrip().endswith("endsolid") and "endsolid" not in text[-200:]:
        raise TruncatedMesh(
            f"{path}: truncated ASCII STL -- no 'endsolid' terminator, so the "
            "writer did not finish"
        )

    verts = [
        [float(v) for v in line.split()[1:4]]
        for line in text.splitlines()
        if line.strip().startswith("vertex")
    ]
    if len(verts) % 3:
        raise TruncatedMesh(
            f"{path}: truncated ASCII STL -- {len(verts)} vertices is not a whole "
            "number of triangles"
        )
    if not verts:
        return np.zeros((0, 3, 3))
    return np.asarray(verts, dtype=np.float64).reshape(-1, 3, 3)


def mesh_stats(path: str | Path, bbox_places: int = 4) -> dict:
    """Triangle count, enclosed volume, and bounding box of an STL.

    Volume is the divergence-theorem sum over signed tetrahedra, taken absolute so
    that winding direction does not change the answer. Vectorized rather than
    looped: these meshes reach 367k triangles, where a per-triangle Python loop
    costs seconds per file and makes verifying a 576-part sweep impractical.
    """
    tris = load_triangles(path)
    if len(tris) == 0:
        return {"triangles": 0, "volume": 0.0, "bbox": None}

    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    volume = float(np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)

    flat = tris.reshape(-1, 3)
    lo = np.round(flat.min(axis=0), bbox_places)
    hi = np.round(flat.max(axis=0), bbox_places)

    return {
        "triangles": int(len(tris)),
        "volume": volume,
        "bbox": [float(v) for v in lo] + [float(v) for v in hi],
    }


def same_geometry(a: dict | None, b: dict | None, tol: float = 1e-6) -> bool:
    """Whether two measurements describe the same solid, within `tol` on volume."""
    if a is None or b is None:
        return False
    return (
        a["triangles"] == b["triangles"]
        and abs(a["volume"] - b["volume"]) <= tol
        and a["bbox"] == b["bbox"]
    )


def describe_difference(a: dict | None, b: dict | None) -> str:
    """One line naming what differs, for reporting a failed comparison."""
    if a is None:
        return "missing on the left"
    if b is None:
        return "missing on the right"
    parts = []
    if a["triangles"] != b["triangles"]:
        parts.append(f"triangles {a['triangles']:,} vs {b['triangles']:,}")
    if a["volume"] != b["volume"]:
        delta = a["volume"] - b["volume"]
        rel = abs(delta) / a["volume"] if a["volume"] else float("inf")
        parts.append(f"volume {a['volume']:.4f} vs {b['volume']:.4f} ({rel:.3%})")
    if a["bbox"] != b["bbox"]:
        parts.append(f"bbox {a['bbox']} vs {b['bbox']}")
    return "; ".join(parts) if parts else "identical"


def is_complete(path: str | Path) -> bool:
    """Whether an STL exists and is a whole, non-empty mesh.

    The completion sentinel for resuming an interrupted sweep. File existence alone
    is not sufficient -- a killed render leaves a partial file that looks finished.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        return len(load_triangles(path)) > 0
    except (TruncatedMesh, ValueError, OSError):
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) not in (2, 3):
        sys.exit(f"usage: {sys.argv[0]} <a.stl> [b.stl]")
    left = mesh_stats(sys.argv[1])
    if len(sys.argv) == 2:
        print(f"triangles : {left['triangles']:,}")
        print(f"volume    : {left['volume']:.4f}")
        print(f"bbox      : {left['bbox']}")
    else:
        right = mesh_stats(sys.argv[2])
        match = same_geometry(left, right)
        print("same geometry" if match else "DIFFERENT")
        if not match:
            print(f"  {describe_difference(left, right)}")
        raise SystemExit(0 if match else 1)
