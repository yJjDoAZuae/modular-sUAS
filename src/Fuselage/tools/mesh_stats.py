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

import re
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


#: Decimal places the canonical hash rounds coordinates to before hashing.
#:
#: Binary STL stores coordinates as float32, about seven significant digits, so six places is
#: below the format's own resolution on a part of this size and two runs of one mesher on one
#: input produce identical values to round. It exists so the hash is not hostage to a last-bit
#: difference that means nothing.
HASH_PLACES = 6


def canonical_hash(tris, places: int = HASH_PLACES) -> str:
    """A hash of the triangle set that does not depend on the order it is written in.

    **This is the only comparison here with no false negatives**, which is why it exists. Volume
    and bounding box can both agree while the shape has changed -- move material from one side of
    a part to the other and the volume difference is exactly zero, the box is untouched, and the
    solids are different. That is the loophole OQ-ARCH-19 names, and it sits in the baseline
    check today. Equal hashes, by contrast, mean the two meshes are the same set of triangles:
    the same geometry, exactly.

    **Its errors run one way only.** A last-bit difference in a coordinate changes the hash on
    geometry that is fine, so it can say "different" about parts that agree -- which costs a
    closer look and never a missed change. It can never say "same" about parts that differ.

    **Order-invariant, and winding-preserving.** Each triangle is rotated so its lowest vertex
    comes first rather than sorted, because sorting three vertices flips the winding of half of
    them and winding is what distinguishes a solid from its own inside-out twin. The triangles
    are then sorted. OpenSCAD emits the same mesh in a different facet order on every run, so
    order-invariance is what makes this usable at all.
    """
    import hashlib

    canonical = []
    for tri in tris:
        pts = [(round(float(v[0]), places), round(float(v[1]), places),
                round(float(v[2]), places)) for v in tri]
        low = min(range(3), key=lambda i: pts[i])
        canonical.append((pts[low], pts[(low + 1) % 3], pts[(low + 2) % 3]))
    canonical.sort()
    digest = hashlib.sha256()
    for tri in canonical:
        for point in tri:
            digest.update(("%.*f,%.*f,%.*f;" % (places, point[0], places, point[1],
                                                places, point[2])).encode("ascii"))
    return digest.hexdigest()


def mesh_stats(path: str | Path, bbox_places: int = 4) -> dict:
    """Triangle count, enclosed volume, surface area, and bounding box of an STL.

    Volume is the divergence-theorem sum over signed tetrahedra, taken absolute so
    that winding direction does not change the answer. Vectorized rather than
    looped: these meshes reach 367k triangles, where a per-triangle Python loop
    costs seconds per file and makes verifying a 576-part sweep impractical.

    **`area` is here because a volume difference is a surface quantity** (OQ-ARCH-20,
    decided 2026-09-06). A mesh's volume error goes as offset x area, so a comparison
    that divides it by the part's own volume charges a hollow part for being hollow:
    the same tolerance asked a solid cowl for 0.0066 mm of surface agreement and its
    shell for 0.000168 mm. The area costs one cross product per triangle on data
    already in hand.

    Older recorded measurements have no `area` key. Readers must treat it as optional
    rather than assume it -- `same_geometry` does.
    """
    tris = load_triangles(path)
    if len(tris) == 0:
        return {"triangles": 0, "volume": 0.0, "area": 0.0, "bbox": None,
                "hash": canonical_hash(tris)}

    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    volume = float(np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)
    area = float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2.0)

    flat = tris.reshape(-1, 3)
    lo = np.round(flat.min(axis=0), bbox_places)
    hi = np.round(flat.max(axis=0), bbox_places)

    return {
        "triangles": int(len(tris)),
        "volume": volume,
        "area": area,
        "bbox": [float(v) for v in lo] + [float(v) for v in hi],
        "hash": canonical_hash(tris),
    }


def volume_offset(a: dict, b: dict, u: float | None = None) -> float | None:
    """`|Va - Vb| / (A * 100U)` -- the volume difference as a fraction of the part.

    **What it means.** Divide a volume difference by the surface area and it becomes the
    average distance the surface would have to move to account for it; divide that by
    `100U`, the unit width, and it is a pure number comparable between parts of different
    sizes and between a solid and its shell. OQ-ARCH-20, decided 2026-09-06.

    `None` when either measurement predates the `area` key, or when the area is zero --
    the caller then has no offset to test and must say so rather than substitute one.
    """
    if a is None or b is None:
        return None
    area = a.get("area")
    if not area:
        return None
    scale = 100.0 * (u if u else 1.0)
    return abs(a["volume"] - b["volume"]) / (area * scale)


# A tolerance on a length or a volume scales with the part it measures. That is the
# rule OQ-ARCH-12 settled and the FreeCAD-side checks already follow; until IP-FC-82
# this file was the last place still comparing against absolute figures, which on a
# 1092 mm^3 part meant 9e-10 relative -- bitwise equality by another name.
VOLUME_TOL = 1e-6          # relative to the part's own volume, so it scales as U^3
BBOX_TOL_PER_U = 5.0e-4    # mm at U = 1, the figure compare_backends.bbox_tol() uses
BBOX_TOL_FLOOR_U = 1.0

U_IN_NAME = re.compile(r"U_([0-9]+(?:\.[0-9]+)?)")


def u_of_name(name: str | Path) -> float | None:
    """The `U` a swept part was built at, read off its filename, or None.

    Every part the sweep writes is named `U_<scale>__<panel>__<part>.stl`, so the
    scale a tolerance has to follow is already carried by the thing being compared.
    Returns None rather than guessing when the name carries no `U` -- a caller
    without one gets the floor, not a fabricated scale.
    """
    m = U_IN_NAME.search(Path(name).name)
    return float(m.group(1)) if m else None


def bbox_tol(u: float | None = None) -> float:
    """Bounding-box tolerance in mm for a part built at size `u`.

    An unknown `u` falls back to the U = 1 figure, which is the floor OQ-ARCH-12
    applies anyway: tight for a large part rather than silently loose.
    """
    return BBOX_TOL_PER_U * max(BBOX_TOL_FLOOR_U if u is None else u, BBOX_TOL_FLOOR_U)


def same_geometry(a: dict | None, b: dict | None,
                  tol: float = VOLUME_TOL, u: float | None = None) -> bool:
    """Whether two measurements describe the same solid.

    `tol` is *relative* to the part's own volume rather than an absolute mm^3 figure,
    and the bounding box is compared against `bbox_tol(u)` rather than for exact float
    equality -- neither mesh comes from a bit-reproducible kernel.

    **Triangle count is deliberately not a criterion.** Two tessellations of one solid
    are one solid, and disqualifying on the count rejects exactly the fillet, chamfer
    and mask refactors this check exists to bless: the boom bulkhead measured on
    2026-08-18 differed by 2,208 triangles with volumes agreeing to 8e-7 relative. The
    count is still reported by `describe_difference()`, because mesh churn is worth
    seeing -- it just no longer decides the answer. This is what the module docstring
    above already claimed the comparison did. OQ-ARCH-16.

    These are proxies for the question, not the question: volume and bounding box can
    both agree while a surface has moved. The sampled surface distance of IP-FC-83
    adjudicates that, with these criteria screening ahead of it.
    """
    if a is None or b is None:
        return False

    # **The hash first, because it is the only test here that cannot be wrong in the dangerous
    # direction.** Equal hashes mean the same set of triangles, so the parts are identical and
    # nothing below can overturn it. Unequal hashes mean the meshes genuinely differ, and the
    # tolerances below then judge whether the difference matters -- which is the question they
    # are good at and this test is not. Decided under OQ-ARCH-19: screen on something with no
    # false negatives, adjudicate with something that measures.
    #
    # Measurements recorded before the hash existed do not carry one, and fall through.
    if a.get("hash") and a.get("hash") == b.get("hash"):
        return True

    if a["bbox"] is None or b["bbox"] is None:
        return a["bbox"] == b["bbox"] and a["volume"] == b["volume"]
    if abs(a["volume"] - b["volume"]) > tol * max(abs(a["volume"]), 1.0):
        return False
    # strict=True: both boxes are six floats, and a length mismatch would mean a
    # malformed measurement rather than something to compare over a shorter list.
    pairs = zip(a["bbox"], b["bbox"], strict=True)
    return max(abs(x - y) for x, y in pairs) <= bbox_tol(u)


def describe_difference(a: dict | None, b: dict | None) -> str:
    """One line naming what differs, for reporting a failed comparison."""
    if a is None:
        return "missing on the left"
    if b is None:
        return "missing on the right"
    parts = []
    if a["volume"] != b["volume"]:
        delta = a["volume"] - b["volume"]
        rel = abs(delta) / a["volume"] if a["volume"] else float("inf")
        parts.append(f"volume {a['volume']:.4f} vs {b['volume']:.4f} ({rel:.3%})")
    if a["bbox"] != b["bbox"]:
        parts.append(f"bbox {a['bbox']} vs {b['bbox']}")
    # Reported last and marked, because it does not disqualify -- see same_geometry().
    # Without the label a reader takes a retessellation for the reason a check failed.
    if a["triangles"] != b["triangles"]:
        parts.append(f"triangles {a['triangles']:,} vs {b['triangles']:,} (not disqualifying)")
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
