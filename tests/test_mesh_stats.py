"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for mesh_stats.py.

The core of every geometry comparison in this project -- render_definition's resume check
(IP-TEST-2) already depends on `is_complete`. Built around a real, hand-verified fixture (a
unit cube, 12 triangles, volume 1.0, surface area 6.0) written as both binary and ASCII STL,
plus deliberately truncated variants of each, so every claim is checked against real STL
bytes rather than against `mesh_stats`' own internal state.

Adoption-phase retrofit (general.md's TDD section).
"""
import struct
from pathlib import Path

import mesh_stats as ms
import numpy as np
import pytest

# A unit cube, 0..1 on each axis, 12 triangles (2 per face), wound so the divergence-theorem
# volume comes out positive without needing abs() -- verified by hand before writing any
# assertion against it: volume 1.0, surface area 6.0.
_VERTS = {
    0: (0, 0, 0), 1: (1, 0, 0), 2: (1, 1, 0), 3: (0, 1, 0),
    4: (0, 0, 1), 5: (1, 0, 1), 6: (1, 1, 1), 7: (0, 1, 1),
}
_CUBE_TRIS = [
    (0, 2, 1), (0, 3, 2),   # bottom z=0
    (4, 5, 6), (4, 6, 7),   # top z=1
    (0, 1, 5), (0, 5, 4),   # front y=0
    (1, 2, 6), (1, 6, 5),   # right x=1
    (2, 3, 7), (2, 7, 6),   # back y=1
    (3, 0, 4), (3, 4, 7),   # left x=0
]


def _cube_points():
    return [[_VERTS[i] for i in tri] for tri in _CUBE_TRIS]


def _write_binary_stl(path, triangles, header=b'test cube'):
    with Path(path).open('wb') as f:
        f.write(header.ljust(80, b'\0')[:80])
        f.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            f.write(struct.pack('<3f', 0.0, 0.0, 0.0))   # normal, unused by mesh_stats
            for point in tri:
                f.write(struct.pack('<3f', *point))
            f.write(struct.pack('<H', 0))                 # attribute byte count


def _write_ascii_stl(path, triangles, name='test'):
    lines = [f'solid {name}']
    for tri in triangles:
        lines.append('facet normal 0 0 0')
        lines.append('outer loop')
        for point in tri:
            lines.append('vertex {} {} {}'.format(*point))
        lines.append('endloop')
        lines.append('endfacet')
    lines.append(f'endsolid {name}')
    with Path(path).open('w', encoding='ascii') as f:
        f.write('\n'.join(lines) + '\n')


@pytest.fixture(params=['binary', 'ascii'])
def cube_stl(request, tmp_path):
    """The same unit cube, written both ways, so every geometry test runs against both
    formats without being written twice."""
    path = tmp_path / f'cube_{request.param}.stl'
    writer = _write_binary_stl if request.param == 'binary' else _write_ascii_stl
    writer(str(path), _cube_points())
    return str(path), request.param


# ------------------------------------------------------------
# load_triangles -- both formats, and both formats' truncation detection
# ------------------------------------------------------------

def test_load_triangles_reads_the_cube_in_both_formats(cube_stl):
    path, _fmt = cube_stl
    tris = ms.load_triangles(path)
    assert tris.shape == (12, 3, 3)


def test_load_triangles_raises_on_a_binary_stl_shorter_than_its_header_claims(tmp_path):
    path = tmp_path / 'truncated.stl'
    _write_binary_stl(str(path), _cube_points())
    # Chop off the last triangle's worth of bytes -- the header still claims 12.
    data = path.read_bytes()
    path.write_bytes(data[:-50])
    with pytest.raises(ms.TruncatedMesh):
        ms.load_triangles(str(path))


def test_load_triangles_raises_on_a_binary_stl_too_short_to_have_a_header(tmp_path):
    path = tmp_path / 'tiny.stl'
    path.write_bytes(b'not enough bytes')
    with pytest.raises(ms.TruncatedMesh):
        ms.load_triangles(str(path))


def test_load_triangles_raises_on_an_ascii_stl_missing_its_endsolid_terminator(tmp_path):
    path = tmp_path / 'truncated.stl'
    _write_ascii_stl(str(path), _cube_points())
    text = path.read_text(encoding='ascii')
    path.write_text(text.rsplit('endsolid', 1)[0], encoding='ascii')
    with pytest.raises(ms.TruncatedMesh, match='no .endsolid. terminator'):
        ms.load_triangles(str(path))


def test_load_triangles_raises_on_an_ascii_stl_with_a_partial_triangles_vertices(tmp_path):
    """A vertex count that is not a multiple of 3 -- landing mid-triangle -- is the ASCII
    truncation case an 'endsolid' check alone cannot catch, per the module's own docstring
    (two cases in three are visible only this way)."""
    path = tmp_path / 'partial.stl'
    lines = ['solid test', 'facet normal 0 0 0', 'outer loop',
             'vertex 0 0 0', 'vertex 1 0 0',   # only 2 of 3 vertices, then EOF-like truncation
             'endsolid test']
    path.write_text('\n'.join(lines), encoding='ascii')
    with pytest.raises(ms.TruncatedMesh, match='not a whole number of triangles'):
        ms.load_triangles(str(path))


def test_load_triangles_empty_binary_mesh_returns_a_zero_length_array(tmp_path):
    """A genuinely empty mesh is representable as a binary STL with a zero triangle count
    in its header -- an ASCII 'solid ... endsolid' with no facets at all is not reachable
    through this path, because load_triangles' own format sniff requires seeing 'facet
    normal' to route a file to the ASCII parser; lacking any facets, it falls through to
    the binary parser and is correctly rejected as too short to be a binary STL at all."""
    path = tmp_path / 'empty.stl'
    _write_binary_stl(str(path), [])
    tris = ms.load_triangles(str(path))
    assert tris.shape == (0, 3, 3)


# ------------------------------------------------------------
# mesh_stats -- triangle count, volume, area, bounding box, hash
# ------------------------------------------------------------

def test_mesh_stats_measures_the_cube_correctly_in_both_formats(cube_stl):
    path, _fmt = cube_stl
    stats = ms.mesh_stats(path)
    assert stats['triangles'] == 12
    assert stats['volume'] == pytest.approx(1.0, abs=1e-5)
    assert stats['area'] == pytest.approx(6.0, abs=1e-5)
    assert stats['bbox'] == pytest.approx([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    assert isinstance(stats['hash'], str) and len(stats['hash']) == 64


def test_mesh_stats_on_an_empty_mesh_returns_zeros_and_no_bbox(tmp_path):
    path = tmp_path / 'empty.stl'
    _write_binary_stl(str(path), [])
    stats = ms.mesh_stats(str(path))
    assert stats == {'triangles': 0, 'volume': 0.0, 'area': 0.0, 'bbox': None,
                     'hash': ms.canonical_hash(np.zeros((0, 3, 3)))}


# ------------------------------------------------------------
# canonical_hash -- order-invariant, winding-preserving
# ------------------------------------------------------------

def test_canonical_hash_is_invariant_to_triangle_order():
    tris = np.array(_cube_points(), dtype=float)
    reversed_order = tris[::-1]
    assert ms.canonical_hash(tris) == ms.canonical_hash(reversed_order)


def test_canonical_hash_is_invariant_to_which_vertex_a_triangle_starts_from():
    """Rotating a triangle's vertex order (not reversing it) does not change its winding."""
    tri = np.array(_cube_points()[:1], dtype=float)          # one triangle, [p0, p1, p2]
    rotated = np.array([[tri[0][1], tri[0][2], tri[0][0]]])  # [p1, p2, p0] -- same winding
    assert ms.canonical_hash(tri) == ms.canonical_hash(rotated)


def test_canonical_hash_changes_when_winding_is_reversed():
    """Swapping two vertices flips winding, which distinguishes a solid from its own
    inside-out twin -- the hash must not treat the two as the same triangle."""
    tri = np.array(_cube_points()[:1], dtype=float)
    flipped = tri[:, [0, 2, 1], :]                            # swap p1 and p2
    assert ms.canonical_hash(tri) != ms.canonical_hash(flipped)


def test_canonical_hash_rounds_below_binary_stl_precision():
    tri = np.array(_cube_points()[:1], dtype=float)
    nudged = tri.copy()
    nudged[0][0][0] += 1e-9  # far below HASH_PLACES=6 resolution
    assert ms.canonical_hash(tri) == ms.canonical_hash(nudged)


# ------------------------------------------------------------
# u_of_name / bbox_tol / volume_offset
# ------------------------------------------------------------

def test_u_of_name_reads_the_scale_out_of_a_real_sweep_filename():
    assert ms.u_of_name('U_1.5__1mm__bulkhead_end_bolt.stl') == 1.5
    assert ms.u_of_name('U_4__panel__corner.stl') == 4.0


def test_u_of_name_returns_none_when_the_name_carries_no_u():
    assert ms.u_of_name('not_a_swept_part.stl') is None


def test_bbox_tol_scales_with_u_but_floors_at_u_1():
    assert ms.bbox_tol(4.0) == pytest.approx(ms.BBOX_TOL_PER_U * 4.0)
    assert ms.bbox_tol(0.5) == pytest.approx(ms.BBOX_TOL_PER_U * ms.BBOX_TOL_FLOOR_U)
    assert ms.bbox_tol(None) == pytest.approx(ms.BBOX_TOL_PER_U * ms.BBOX_TOL_FLOOR_U)


def test_volume_offset_is_none_when_either_measurement_predates_the_area_key():
    """Pins a fix made alongside this test, 2026-09-22: volume_offset's docstring always
    promised None when 'either measurement' lacks 'area', but the code only ever checked
    `a`'s -- latent because the one real caller (compare_backends.py) always passes two
    freshly-computed mesh_stats() results, which carry 'area' together or not at all, so
    the asymmetry never fired in practice. Fixed to check both, matching the docstring."""
    a = {'volume': 10.0, 'area': 6.0}
    b_no_area = {'volume': 10.0}            # no 'area' -- an older recorded measurement
    assert ms.volume_offset(a, b_no_area) is None
    assert ms.volume_offset(b_no_area, a) is None  # order must not matter either
    assert ms.volume_offset(None, a) is None


def test_volume_offset_matches_its_own_documented_formula():
    a = {'volume': 10.0, 'area': 6.0}
    b = {'volume': 10.5, 'area': 6.0}
    assert ms.volume_offset(a, b, u=1.0) == pytest.approx(abs(10.0 - 10.5) / (6.0 * 100.0))


# ------------------------------------------------------------
# same_geometry / describe_difference
# ------------------------------------------------------------

def test_same_geometry_true_for_identical_measurements():
    stats_a = {'volume': 10.0, 'area': 6.0, 'bbox': [0, 0, 0, 1, 1, 1], 'triangles': 12,
              'hash': 'x'}
    stats_b = dict(stats_a)
    assert ms.same_geometry(stats_a, stats_b) is True


def test_same_geometry_short_circuits_on_a_matching_hash_even_with_different_bbox():
    """The hash is the one test with no false negatives -- equal hashes mean identical
    triangle sets, so nothing below it can overturn a match (OQ-ARCH-19)."""
    stats_a = {'volume': 10.0, 'area': 6.0, 'bbox': [0, 0, 0, 1, 1, 1], 'triangles': 12,
              'hash': 'same'}
    stats_b = {'volume': 99.0, 'area': 1.0, 'bbox': [9, 9, 9, 9, 9, 9], 'triangles': 1,
              'hash': 'same'}
    assert ms.same_geometry(stats_a, stats_b) is True


def test_same_geometry_false_when_volume_differs_beyond_tolerance():
    stats_a = {'volume': 10.0, 'area': 6.0, 'bbox': [0, 0, 0, 1, 1, 1], 'triangles': 12,
              'hash': 'a'}
    stats_b = dict(stats_a, volume=20.0, hash='b')
    assert ms.same_geometry(stats_a, stats_b) is False


def test_same_geometry_false_when_bbox_differs_beyond_tolerance():
    stats_a = {'volume': 10.0, 'area': 6.0, 'bbox': [0, 0, 0, 1, 1, 1], 'triangles': 12,
              'hash': 'a'}
    stats_b = dict(stats_a, bbox=[0, 0, 0, 2, 1, 1], hash='b')
    assert ms.same_geometry(stats_a, stats_b) is False


def test_same_geometry_ignores_a_triangle_count_difference():
    """Deliberately not a criterion -- two tessellations of one solid are one solid
    (OQ-ARCH-16)."""
    stats_a = {'volume': 10.0, 'area': 6.0, 'bbox': [0, 0, 0, 1, 1, 1], 'triangles': 12,
              'hash': 'a'}
    stats_b = dict(stats_a, triangles=9000, hash='b')
    assert ms.same_geometry(stats_a, stats_b) is True


def test_same_geometry_false_when_either_side_is_none():
    assert ms.same_geometry(None, {'volume': 1.0, 'area': 1.0, 'bbox': None,
                                   'triangles': 1, 'hash': 'x'}) is False


def test_describe_difference_names_missing_sides():
    assert ms.describe_difference(None, {}) == 'missing on the left'
    assert ms.describe_difference({}, None) == 'missing on the right'


def test_describe_difference_reports_triangle_count_as_not_disqualifying():
    stats_a = {'volume': 10.0, 'bbox': [0, 0, 0, 1, 1, 1], 'triangles': 12}
    stats_b = dict(stats_a, triangles=13)
    text = ms.describe_difference(stats_a, stats_b)
    assert 'not disqualifying' in text
    assert 'volume' not in text  # only the differing fields are reported


def test_describe_difference_identical_measurements_says_so():
    stats_a = {'volume': 10.0, 'bbox': [0, 0, 0, 1, 1, 1], 'triangles': 12}
    assert ms.describe_difference(stats_a, dict(stats_a)) == 'identical'


# ------------------------------------------------------------
# is_complete
# ------------------------------------------------------------

def test_is_complete_true_for_a_whole_mesh(cube_stl):
    path, _fmt = cube_stl
    assert ms.is_complete(path) is True


def test_is_complete_false_for_a_missing_file(tmp_path):
    assert ms.is_complete(str(tmp_path / 'does_not_exist.stl')) is False


def test_is_complete_false_for_an_empty_file(tmp_path):
    path = tmp_path / 'empty.stl'
    path.write_bytes(b'')
    assert ms.is_complete(str(path)) is False


def test_is_complete_false_for_a_truncated_binary_stl(tmp_path):
    path = tmp_path / 'truncated.stl'
    _write_binary_stl(str(path), _cube_points())
    path.write_bytes(path.read_bytes()[:-50])
    assert ms.is_complete(str(path)) is False
