"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for surface_distance.py.

The geometric kernel (`_closest_on_triangles`/`distances_to_mesh`) is exercised with a
single right triangle at known coordinates so every branch (interior, each of the three
clamped edges) has an exact expected answer computed by hand, not by trusting the code
under test. `surface_distance`/`sample_points`/`unique_vertices` use small hand-built STL
meshes (a unit cube, and matched parallel quads for an exact known offset) rather than the
real cowl corpus, per the same rationale as test_mesh_stats.py.

`main()` (argparse/print wiring) is not covered, consistent with the other CLI-entry-point
modules in this plan.
"""
import struct
from pathlib import Path

import numpy as np
import pytest
import surface_distance as sd

# ------------------------------------------------------------
# Fixture geometry
# ------------------------------------------------------------

# A unit cube, reused from test_mesh_stats.py's hand-verified fixture: 8 distinct vertices,
# 12 triangles.
_VERTS = {
    0: (0, 0, 0), 1: (1, 0, 0), 2: (1, 1, 0), 3: (0, 1, 0),
    4: (0, 0, 1), 5: (1, 0, 1), 6: (1, 1, 1), 7: (0, 1, 1),
}
_CUBE_TRIS = [
    (0, 2, 1), (0, 3, 2),
    (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4),
    (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6),
    (3, 0, 4), (3, 4, 7),
]


def _cube_points():
    return [[_VERTS[i] for i in tri] for tri in _CUBE_TRIS]


def _cube_array():
    return np.array(_cube_points(), dtype=float)


def _write_binary_stl(path, triangles, header=b'test'):
    with Path(path).open('wb') as f:
        f.write(header.ljust(80, b'\0')[:80])
        f.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            f.write(struct.pack('<3f', 0.0, 0.0, 0.0))
            for point in tri:
                f.write(struct.pack('<3f', *point))
            f.write(struct.pack('<H', 0))


def _quad_at_z(z):
    """A 2x2 square in the XY plane at height `z`, as 2 triangles."""
    a, b, c, d = (0, 0, z), (2, 0, z), (2, 2, z), (0, 2, z)
    return [(a, b, c), (a, c, d)]


# ------------------------------------------------------------
# surface_tol
# ------------------------------------------------------------

def test_surface_tol_defaults_to_the_u_1_floor():
    assert sd.surface_tol() == pytest.approx(sd.SURFACE_TOL_PER_U)


def test_surface_tol_below_the_floor_is_clamped_to_the_floor():
    assert sd.surface_tol(0.5) == pytest.approx(sd.SURFACE_TOL_PER_U)


def test_surface_tol_scales_linearly_above_the_floor():
    assert sd.surface_tol(4.0) == pytest.approx(sd.SURFACE_TOL_PER_U * 4.0)


# ------------------------------------------------------------
# sample_surface -- area-weighted sampling
# ------------------------------------------------------------

def test_sample_surface_returns_the_requested_point_count():
    tris = _cube_array()
    rng = np.random.default_rng(1)
    pts = sd.sample_surface(tris, 50, rng)
    assert pts.shape == (50, 3)


def test_sample_surface_points_lie_within_the_cube_bounds():
    tris = _cube_array()
    rng = np.random.default_rng(2)
    pts = sd.sample_surface(tris, 200, rng)
    assert np.all(pts >= -1e-9) and np.all(pts <= 1.0 + 1e-9)


def test_sample_surface_falls_back_to_raw_vertices_when_total_area_is_zero():
    """A degenerate (zero-area) triangle set: the area-weighted path divides by zero, so the
    function must fall back to returning raw triangle vertices instead."""
    degenerate = np.array([[(0, 0, 0), (0, 0, 0), (0, 0, 0)]], dtype=float)
    rng = np.random.default_rng(3)
    pts = sd.sample_surface(degenerate, 1, rng)
    assert pts.shape == (1, 3)
    assert np.allclose(pts, [[0, 0, 0]])


# ------------------------------------------------------------
# distances_to_mesh / _closest_on_triangles -- exact hand-computed answers
#
# A single right triangle in the z=0 plane: a=(0,0,0), b=(1,0,0), c=(0,1,0). Each test
# targets one of the geometric regions the closest-point routine must clamp into.
# ------------------------------------------------------------

_RIGHT_TRI = np.array([[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]])


def _dist(point):
    return sd.distances_to_mesh(np.array([point]), _RIGHT_TRI)[0]


def test_distance_to_mesh_directly_above_the_interior_is_the_perpendicular_drop():
    assert _dist((0.2, 0.2, 5.0)) == pytest.approx(5.0)


def test_distance_to_mesh_beyond_vertex_a_clamps_to_that_vertex():
    assert _dist((-1.0, -1.0, 0.0)) == pytest.approx(np.hypot(1.0, 1.0))


def test_distance_to_mesh_beyond_edge_ab_clamps_onto_that_edge():
    # (0.5, -1, 0): outside past edge a-b (the s_e0 / t<0 branch). Closest point (0.5, 0, 0).
    assert _dist((0.5, -1.0, 0.0)) == pytest.approx(1.0)


def test_distance_to_mesh_beyond_edge_ac_clamps_onto_that_edge():
    # (-1, 0.5, 0): outside past edge a-c (the t_e1 / s<0 branch). Closest point (0, 0.5, 0).
    assert _dist((-1.0, 0.5, 0.0)) == pytest.approx(1.0)


def test_distance_to_mesh_beyond_the_hypotenuse_clamps_onto_that_edge():
    # (1, 1, 0): outside past edge b-c (s+t>1, the "over" rescale branch).
    # Closest point on b-c is its midpoint (0.5, 0.5, 0).
    assert _dist((1.0, 1.0, 0.0)) == pytest.approx(np.hypot(0.5, 0.5))


def test_distance_to_mesh_at_a_vertex_is_zero():
    assert _dist((1.0, 0.0, 0.0)) == pytest.approx(0.0, abs=1e-12)


def test_distance_to_mesh_processes_more_points_than_one_chunk():
    """CHUNK=64: use enough points to force the loop in distances_to_mesh over more than
    one block, so the chunking itself (not just a single-block call) is exercised."""
    points = np.tile([0.2, 0.2, 3.0], (sd.CHUNK * 2 + 5, 1))
    out = sd.distances_to_mesh(points, _RIGHT_TRI)
    assert out.shape == (sd.CHUNK * 2 + 5,)
    assert np.allclose(out, 3.0)


# ------------------------------------------------------------
# unique_vertices
# ------------------------------------------------------------

def test_unique_vertices_collapses_the_cube_to_its_eight_corners():
    verts = sd.unique_vertices(_cube_array())
    assert verts.shape == (8, 3)


def test_unique_vertices_merges_points_within_rounding_precision():
    tris = np.array([[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                     [(1e-8, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]])
    verts = sd.unique_vertices(tris)
    # (0,0,0) and (1e-8,0,0) round to the same 6-decimal value and must collapse to one.
    assert len(verts) == 4


def test_unique_vertices_keeps_points_that_differ_above_rounding_precision():
    tris = np.array([[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                     [(1e-4, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]])
    verts = sd.unique_vertices(tris)
    assert len(verts) == 5


# ------------------------------------------------------------
# sample_points -- vertex/area split and reported coverage
# ------------------------------------------------------------

def test_sample_points_splits_between_vertices_and_area_by_the_given_share():
    tris = _cube_array()
    rng = np.random.default_rng(4)
    pts, coverage = sd.sample_points(tris, 4, rng, vertex_share=0.75)
    # n_vert = min(int(4 * 0.75), 8) = 3, leaving 1 area sample: 4 total.
    assert pts.shape == (4, 3)
    assert coverage == pytest.approx(3 / 8)


def test_sample_points_with_zero_vertex_share_returns_only_area_samples():
    tris = _cube_array()
    rng = np.random.default_rng(5)
    pts, coverage = sd.sample_points(tris, 6, rng, vertex_share=0.0)
    assert pts.shape == (6, 3)
    assert coverage == 0.0


def test_sample_points_covers_every_vertex_when_the_budget_exceeds_the_vertex_count():
    tris = _cube_array()
    rng = np.random.default_rng(6)
    pts, coverage = sd.sample_points(tris, 100, rng, vertex_share=1.0)
    assert coverage == 1.0
    # n_vert = min(100, 8) = 8, area samples fill the rest: 100 total.
    assert pts.shape == (100, 3)


# ------------------------------------------------------------
# surface_distance -- end to end against real STL files
# ------------------------------------------------------------

def test_surface_distance_of_a_mesh_against_itself_is_zero(tmp_path):
    path = tmp_path / 'cube.stl'
    _write_binary_stl(str(path), _cube_points())
    result = sd.surface_distance(str(path), str(path), samples=200, all_vertices=True)
    assert result['max'] == pytest.approx(0.0, abs=1e-6)
    assert result['vertex_coverage'] == 1.0


def test_surface_distance_reports_the_exact_offset_between_two_parallel_quads(tmp_path):
    """Two identical footprints, offset only in z: every vertex's closest point on the other
    mesh is directly above/below it, so the true answer is exactly the z offset -- not an
    approximation, letting `all_vertices=True` give a deterministic, exact-value assertion."""
    a = tmp_path / 'a.stl'
    b = tmp_path / 'b.stl'
    _write_binary_stl(str(a), _quad_at_z(0.0))
    _write_binary_stl(str(b), _quad_at_z(0.01))
    result = sd.surface_distance(str(a), str(b), all_vertices=True)
    assert result['max'] == pytest.approx(0.01, abs=1e-6)
    assert result['mean'] == pytest.approx(0.01, abs=1e-6)


def test_surface_distance_returns_infinite_when_one_mesh_is_empty(tmp_path):
    empty = tmp_path / 'empty.stl'
    real = tmp_path / 'cube.stl'
    _write_binary_stl(str(empty), [])
    _write_binary_stl(str(real), _cube_points())
    result = sd.surface_distance(str(empty), str(real))
    assert result['max'] == float('inf')
    assert result['vertex_coverage'] == 0.0
    assert 'empty' in result['note']


def test_surface_distance_seed_is_reproducible(tmp_path):
    a = tmp_path / 'a.stl'
    b = tmp_path / 'b.stl'
    _write_binary_stl(str(a), _cube_points())
    _write_binary_stl(str(b), _quad_at_z(0.5) + _cube_points())
    r1 = sd.surface_distance(str(a), str(b), samples=50, seed=99)
    r2 = sd.surface_distance(str(a), str(b), samples=50, seed=99)
    assert r1 == r2


# ------------------------------------------------------------
# within
# ------------------------------------------------------------

def test_within_is_true_when_the_max_distance_is_inside_the_threshold():
    result = {'max': sd.surface_tol() / 2}
    assert sd.within(result) is True


def test_within_is_false_when_the_max_distance_exceeds_the_threshold():
    result = {'max': sd.surface_tol() * 2}
    assert sd.within(result) is False


def test_within_uses_the_given_u_to_scale_the_threshold():
    result = {'max': sd.surface_tol(4.0) * 0.9}
    assert sd.within(result, u=4.0) is True
    assert sd.within(result, u=1.0) is False
