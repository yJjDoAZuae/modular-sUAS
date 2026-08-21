"""Measure how far one mesh's surface has moved from another's, on a sampled subset.

OQ-ARCH-16 decided on 2026-08-18 to keep the cheap criteria in `mesh_stats` *and* add a
surface distance, because volume and bounding box are proxies: both can agree while a
surface has moved. A distance in millimeters is the only measure on that list that can be
checked against what a printer actually holds. The cheap criteria screen; this adjudicates.

**Sampled, not exhaustive.** Points are drawn from the surface rather than every vertex
measured, so cost is set by the sample size instead of the mesh size. That matters here:
cowls carry around 90,000 triangles and the corpus is 576 parts.

**Sampling makes the answer a lower bound.** A sample can miss a small displaced feature
entirely, so this reports the largest deviation *it found*, never the largest that exists.
Two consequences worth stating plainly, because a lower bound reported as a maximum is the
kind of thing that gets trusted for years:

- A clean result means "nothing was found to have moved", not "nothing moved".
- The default sample size below is **provisional and uncalibrated**. What it should be is
  set by the smallest feature worth catching and how likely a sample of a given size is to
  land on it, which OQ-ARCH-16 says to measure rather than guess. That calibration has not
  been done. Until it is, treat a pass as screening rather than proof.

**Why brute force.** The project depends on numpy alone -- no scipy, no trimesh -- and
adding a dependency is not this module's decision to make. Point-to-triangle distance is
exact and vectorizes cleanly, so the sample is compared against every triangle in chunks.
That is O(samples x triangles), which is affordable precisely because the sample is small,
and it avoids an approximate nearest-vertex shortcut that would report a distance the
surface does not have.

Usage, from the repository root:

    uv run python src/Fuselage/tools/surface_distance.py <a.stl> <b.stl> [--samples N]
                                                          [--seed S] [--u U]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesh_stats  # noqa: E402

# Provisional. See the docstring: this is a screening default, not a calibrated one.
DEFAULT_SAMPLES = 4000
DEFAULT_SEED = 20260818          # fixed, so a verification run is reproducible
VERTEX_SHARE = 0.75              # calibrated 2026-08-18; see sample_points()
SURFACE_TOL_PER_U = 5.0e-4       # mm at U = 1, matching bbox_tol's figure (OQ-ARCH-12)
SURFACE_TOL_FLOOR_U = 1.0
CHUNK = 64                       # sample points per vectorized block against all triangles


def surface_tol(u: float | None = None) -> float:
    """Distance threshold in mm for a part built at size `u`, floored at U = 1."""
    scale = SURFACE_TOL_FLOOR_U if u is None else u
    return SURFACE_TOL_PER_U * max(scale, SURFACE_TOL_FLOOR_U)


def sample_surface(tris: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """`n` points drawn uniformly over the mesh's area, not over its triangles.

    Area weighting matters: picking triangles uniformly would concentrate samples on the
    dense tessellation of curved regions and leave a large flat face almost unsampled,
    which is exactly where a displaced surface would hide.
    """
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = areas.sum()
    if total <= 0:
        return tris.reshape(-1, 3)[:n]
    idx = rng.choice(len(tris), size=n, p=areas / total)
    # Square-root parameterization gives a uniform point inside the triangle.
    u1 = np.sqrt(rng.random(n))[:, None]
    u2 = rng.random(n)[:, None]
    return a[idx] + u1 * ((1 - u2) * (b[idx] - a[idx]) + u2 * (c[idx] - a[idx]))


def _closest_on_triangles(p: np.ndarray, a: np.ndarray, ab: np.ndarray, ac: np.ndarray):
    """Closest point on each triangle to each point, by barycentric region (Ericson).

    `p` is (P, 1, 3); `a`, `ab`, `ac` are (1, T, 3). Returns (P, T, 3).
    """
    ap = p - a
    d1 = np.einsum("ptk,ptk->pt", np.broadcast_to(ab, ap.shape), ap)
    d2 = np.einsum("ptk,ptk->pt", np.broadcast_to(ac, ap.shape), ap)
    d3 = np.einsum("tk,tk->t", ab[0], ab[0])[None, :]
    d4 = np.einsum("tk,tk->t", ab[0], ac[0])[None, :]
    d5 = np.einsum("tk,tk->t", ac[0], ac[0])[None, :]

    denom = d3 * d5 - d4 * d4
    safe = np.where(denom == 0, 1.0, denom)
    s = (d5 * d1 - d4 * d2) / safe
    t = (d3 * d2 - d4 * d1) / safe

    # Clamp into the triangle: first onto each edge's parameter range, then the interior.
    s_e0 = np.clip(np.divide(d1, d3, out=np.zeros_like(d1), where=d3 != 0), 0, 1)
    t_e1 = np.clip(np.divide(d2, d5, out=np.zeros_like(d2), where=d5 != 0), 0, 1)
    e2_den = d3 - 2 * d4 + d5
    t_e2 = np.clip(np.divide(d5 - d4, e2_den, out=np.zeros_like(d4), where=e2_den != 0), 0, 1)

    inside = (s >= 0) & (t >= 0) & (s + t <= 1)
    s_c = np.where(inside, s, np.where(t < 0, s_e0, np.where(s < 0, 0.0, 1.0 - t_e2)))
    t_c = np.where(inside, t, np.where(s < 0, t_e1, np.where(t < 0, 0.0, t_e2)))
    s_c = np.clip(s_c, 0, 1)
    t_c = np.clip(t_c, 0, 1)
    over = s_c + t_c > 1
    scale = np.where(over, s_c + t_c, 1.0)
    s_c, t_c = s_c / scale, t_c / scale

    return a + s_c[..., None] * ab + t_c[..., None] * ac


def distances_to_mesh(points: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Shortest distance from each point to the mesh surface, in mm."""
    a = tris[:, 0][None, :, :]
    ab = (tris[:, 1] - tris[:, 0])[None, :, :]
    ac = (tris[:, 2] - tris[:, 0])[None, :, :]
    out = np.empty(len(points))
    for i in range(0, len(points), CHUNK):
        block = points[i:i + CHUNK][:, None, :]
        closest = _closest_on_triangles(block, a, ab, ac)
        out[i:i + CHUNK] = np.sqrt(((block - closest) ** 2).sum(-1)).min(axis=1)
    return out


def unique_vertices(tris: np.ndarray) -> np.ndarray:
    """The mesh's distinct vertices, rounded so shared corners collapse to one point."""
    return np.unique(np.round(tris.reshape(-1, 3), 6), axis=0)


def sample_points(tris: np.ndarray, n: int, rng: np.random.Generator,
                  vertex_share: float = VERTEX_SHARE) -> tuple[np.ndarray, float]:
    """`n` points biased toward vertices, plus the fraction of vertices they cover.

    Calibrated 2026-08-18 against the 0.05 mm that is the smallest linear dimension this
    project cares about, and the split is the result of that measurement rather than a
    preference. Two facts drove it:

    **Area sampling cannot find a small feature.** A 0.05 x 0.05 mm patch is 2.5e-3 mm^2
    against 1,174 mm^2 for a U = 0.5 corner and 47,551 mm^2 for a U = 4 one, so a 95%
    chance of landing on it needs 1.4 million samples at the small end and 57 million at
    the large. Uniform sampling scales with the *area* a change affects, not its
    magnitude -- which is why it caught the corner's 0.1 mm whole-face fix at 400 samples
    and would sail straight past an isolated feature.

    **Vertices are where features are.** Tessellation puts vertices on feature boundaries,
    so a displaced 0.05 mm feature has vertices on it. Sampling them spends the budget
    where detail lives instead of spreading it over large flat faces.

    Area samples are kept as a minority share because vertices alone are blind to one
    case: two meshes whose vertices coincide but whose triangle interiors do not, which is
    what coarse tessellation of the same surface produces.
    """
    verts = unique_vertices(tris)
    n_vert = min(int(n * vertex_share), len(verts))
    chosen = verts[rng.choice(len(verts), size=n_vert, replace=False)] if n_vert else \
        np.empty((0, 3))
    area_pts = sample_surface(tris, max(n - n_vert, 0), rng)
    coverage = n_vert / len(verts) if len(verts) else 1.0
    return np.vstack([chosen, area_pts]) if len(chosen) else area_pts, coverage


def surface_distance(path_a, path_b, samples: int = DEFAULT_SAMPLES,
                     seed: int = DEFAULT_SEED, all_vertices: bool = False) -> dict:
    """Symmetric sampled distance between two meshes.

    Measured in both directions and reported as the worse of the two. One direction alone
    is not enough: sampling only A finds material A has that B lacks, and is blind to
    material B has that A lacks.

    `vertex_coverage` is the fraction of each mesh's vertices the sample included, and it
    is reported because it *is* the detection probability for the smallest case that
    matters. Choosing k of V vertices without replacement includes any particular one with
    probability k/V -- arithmetic, not an estimate -- so a run covering 23% of vertices has
    a 23% chance of catching a single displaced vertex, and that is what a clean result
    from it is worth. `all_vertices=True` takes every vertex and makes that probability 1
    for a vertex-displacement, at roughly V/samples times the cost.
    """
    ta, tb = mesh_stats.load_triangles(path_a), mesh_stats.load_triangles(path_b)
    if len(ta) == 0 or len(tb) == 0:
        return {"samples": 0, "max": float("inf"), "mean": float("inf"),
                "vertex_coverage": 0.0, "note": "one of the meshes is empty"}
    rng = np.random.default_rng(seed)
    if all_vertices:
        pa, pb = unique_vertices(ta), unique_vertices(tb)
        cov_a = cov_b = 1.0
    else:
        pa, cov_a = sample_points(ta, samples, rng)
        pb, cov_b = sample_points(tb, samples, rng)
    d_ab = distances_to_mesh(pa, tb)
    d_ba = distances_to_mesh(pb, ta)
    return {
        "samples": len(pa),
        "seed": seed,
        "vertex_coverage": float(min(cov_a, cov_b)),
        "max": float(max(d_ab.max(), d_ba.max())),
        "mean": float(max(d_ab.mean(), d_ba.mean())),
        "max_a_to_b": float(d_ab.max()),
        "max_b_to_a": float(d_ba.max()),
    }


def within(result: dict, u: float | None = None) -> bool:
    """Whether the sampled distance stays inside the threshold for size `u`.

    A lower bound: see the module docstring. False is conclusive, True is screening.
    """
    return result["max"] <= surface_tol(u)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                        help=f"points per direction (default {DEFAULT_SAMPLES})")
    parser.add_argument("--all-vertices", action="store_true",
                        help="measure every vertex instead of a subset: detection of a "
                             "displaced vertex becomes certain, at much higher cost")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--u", type=float, default=None,
                        help="the U the part was built at; read from the filename if omitted")
    args = parser.parse_args(argv)

    u = args.u if args.u is not None else mesh_stats.u_of_name(args.a)
    r = surface_distance(args.a, args.b, args.samples, args.seed, args.all_vertices)
    tol = surface_tol(u)
    cov = r.get("vertex_coverage", 0.0)
    print(f"samples   : {r['samples']} per direction, seed {r.get('seed')}")
    print(f"max       : {r['max']:.6f} mm  (a->b {r.get('max_a_to_b', 0):.6f}, "
          f"b->a {r.get('max_b_to_a', 0):.6f})")
    print(f"mean      : {r['mean']:.6f} mm")
    print(f"threshold : {tol:.6f} mm at U = {u if u is not None else 1.0}")
    print(f"coverage  : {cov:.1%} of vertices")
    ok = within(r, u)
    if not ok:
        print("SURFACE MOVED")
        return 1
    # Say what a clean result is worth rather than letting it read as proof. Coverage is
    # the detection probability for a single displaced vertex -- the 0.05 mm case.
    if cov >= 1.0:
        print("WITHIN THRESHOLD -- every vertex measured; a displaced vertex could not hide")
        return 0
    print(f"WITHIN THRESHOLD -- but this sample had a {cov:.0%} chance of catching a single "
          f"displaced vertex.\n  Nothing was found to have moved; that is not the same as "
          f"nothing moving. Use --all-vertices to settle it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
