"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for stl_preview.py.

The rasterizer is exercised with `rot_deg=(0, 0, 0)` wherever a specific screen-space
result is asserted: with no rotation, `_rotation` is the identity, so camera space equals
world space and the winding-sign math (front vs. back) can be worked out by hand instead of
trusted from the code under test. `write_png` is checked by manually decoding the PNG bytes
back to pixels (signature, IHDR dims, zlib-inflating IDAT, stripping the per-row filter
byte) rather than depending on an external PNG library. `__main__`'s CLI block is not
covered, consistent with the other CLI-entry-point modules in this plan.
"""
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
import stl_preview as sp

# ------------------------------------------------------------
# Fixture geometry
# ------------------------------------------------------------

_CUBE_VERTS = {
    0: (0, 0, 0), 1: (1, 0, 0), 2: (1, 1, 0), 3: (0, 1, 0),
    4: (0, 0, 1), 5: (1, 0, 1), 6: (1, 1, 1), 7: (0, 1, 1),
}
_CUBE_TRI_IDX = [
    (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
]


def _cube_points():
    return [[_CUBE_VERTS[i] for i in tri] for tri in _CUBE_TRI_IDX]


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


# A unit square in the XZ plane (y = 0, i.e. facing the camera when rot_deg = (0, 0, 0),
# since depth is cam[:, :, 1]). Winding chosen by hand so that, working through
# `_render_at`'s screen-space area formula with sx ~ +x and sy ~ -z, the signed area comes
# out negative -- i.e. `facing_front` -- for this vertex order. See the module docstring.
_SQ_A, _SQ_B, _SQ_C, _SQ_D = (-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)
_SQUARE_FRONT = np.array([(_SQ_A, _SQ_B, _SQ_C), (_SQ_A, _SQ_C, _SQ_D)], dtype=float)
_SQUARE_BACK = np.array([(_SQ_A, _SQ_C, _SQ_B), (_SQ_A, _SQ_D, _SQ_C)], dtype=float)


# ------------------------------------------------------------
# load_stl / _load_ascii_stl
# ------------------------------------------------------------

def test_load_stl_reads_a_binary_file(tmp_path):
    path = tmp_path / 'cube.stl'
    _write_binary_stl(str(path), _cube_points())
    tris = sp.load_stl(str(path))
    assert tris.shape == (12, 3, 3)
    assert tris.dtype == np.float64


def test_load_stl_reads_an_ascii_file(tmp_path):
    path = tmp_path / 'cube.stl'
    _write_ascii_stl(str(path), _cube_points())
    tris = sp.load_stl(str(path))
    assert tris.shape == (12, 3, 3)


def test_load_stl_raises_when_shorter_than_a_header(tmp_path):
    path = tmp_path / 'tiny.stl'
    path.write_bytes(b'x' * 83)
    with pytest.raises(ValueError, match='too short'):
        sp.load_stl(str(path))


def test_load_stl_raises_when_the_binary_count_mismatches_and_the_body_is_not_ascii(tmp_path):
    """A binary-looking file whose header triangle count does not match the file length
    falls through to the ASCII path; if the bytes are not text with 'vertex' lines either,
    that path must raise rather than silently return an empty mesh."""
    path = tmp_path / 'bad.stl'
    _write_binary_stl(str(path), _cube_points())
    data = bytearray(path.read_bytes())
    data[80:84] = struct.pack('<I', 999)   # header now disagrees with the actual length
    path.write_bytes(bytes(data))
    with pytest.raises(ValueError, match='not a readable STL'):
        sp.load_stl(str(path))


def test_load_ascii_stl_raises_on_a_vertex_count_not_a_multiple_of_three():
    data = b'solid t\nvertex 0 0 0\nvertex 1 0 0\nendsolid t\n'
    with pytest.raises(ValueError, match='not a readable STL'):
        sp._load_ascii_stl(data, 'inline')


def test_load_ascii_stl_raises_on_no_vertices_at_all():
    data = b'solid empty\nendsolid empty\n'
    with pytest.raises(ValueError, match='not a readable STL'):
        sp._load_ascii_stl(data, 'inline')


def test_load_ascii_stl_parses_vertices_regardless_of_surrounding_lines():
    data = (b'solid t\nfacet normal 0 0 0\nouter loop\n'
            b'vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n'
            b'endloop\nendfacet\nendsolid t\n')
    tris = sp._load_ascii_stl(data, 'inline')
    assert tris.shape == (1, 3, 3)
    assert np.array_equal(tris[0], [[0, 0, 0], [1, 0, 0], [0, 1, 0]])


# ------------------------------------------------------------
# _rotation
# ------------------------------------------------------------

def test_rotation_at_zero_degrees_is_the_identity():
    r = sp._rotation((0.0, 0.0, 0.0))
    assert np.allclose(r, np.eye(3))


@pytest.mark.parametrize('angles', [
    (10.0, 0.0, 0.0), (0.0, 33.0, 0.0), (0.0, 0.0, -47.0), sp.CAMERA_ROTATION_DEG,
])
def test_rotation_is_orthogonal_with_unit_determinant(angles):
    r = sp._rotation(angles)
    assert np.allclose(r @ r.T, np.eye(3), atol=1e-9)
    assert np.linalg.det(r) == pytest.approx(1.0)


# ------------------------------------------------------------
# _shift
# ------------------------------------------------------------

def test_shift_by_zero_returns_an_equal_copy():
    arr = np.arange(9, dtype=float).reshape(3, 3)
    out = sp._shift(arr, 0, 0, -1.0)
    assert np.array_equal(out, arr)
    assert out is not arr


def test_shift_down_and_right_pads_the_exposed_edges_with_fill():
    arr = np.array([[1.0, 2.0], [3.0, 4.0]])
    out = sp._shift(arr, 1, 1, fill=9.0)
    # Row/col 0 are exposed (nothing shifts into them) and must read as fill; (1, 1) receives
    # the old (0, 0).
    assert np.array_equal(out, [[9.0, 9.0], [9.0, 1.0]])


def test_shift_up_and_left_pads_the_opposite_edges():
    arr = np.array([[1.0, 2.0], [3.0, 4.0]])
    out = sp._shift(arr, -1, -1, fill=0.0)
    assert np.array_equal(out, [[4.0, 0.0], [0.0, 0.0]])


def test_shift_by_at_least_the_array_size_moves_everything_off_canvas():
    """Regression: a shift magnitude >= the array's own dimension used to raise
    ValueError (mismatched slice shapes) instead of correctly returning all-fill -- found
    via _occlusion, whose largest sampling radius (16) exceeds some small test images."""
    arr = np.full((10, 10), 3.0)
    out = sp._shift(arr, 16, 0, fill=-1.0)
    assert np.array_equal(out, np.full((10, 10), -1.0))


def test_shift_by_exactly_the_array_size_moves_everything_off_canvas():
    arr = np.full((10, 10), 3.0)
    out = sp._shift(arr, 0, 10, fill=-1.0)
    assert np.array_equal(out, np.full((10, 10), -1.0))


# ------------------------------------------------------------
# _smoothstep
# ------------------------------------------------------------

def test_smoothstep_is_zero_at_and_below_the_lower_bound():
    x = np.array([-5.0, 0.0])
    assert np.array_equal(sp._smoothstep(x, 0.0, 1.0), [0.0, 0.0])


def test_smoothstep_is_one_at_and_above_the_upper_bound():
    x = np.array([1.0, 5.0])
    assert np.array_equal(sp._smoothstep(x, 0.0, 1.0), [1.0, 1.0])


def test_smoothstep_is_one_half_at_the_midpoint():
    x = np.array([0.5])
    assert sp._smoothstep(x, 0.0, 1.0)[0] == pytest.approx(0.5)


# ------------------------------------------------------------
# _occlusion
# ------------------------------------------------------------

def test_occlusion_is_fully_lit_where_nothing_is_solid():
    zbuf = np.full((10, 10), np.inf)
    nbuf = np.zeros((10, 10, 3), dtype=np.float32)
    ao = sp._occlusion(zbuf, nbuf, unit=1.0)
    assert np.array_equal(ao, np.ones((10, 10), dtype=np.float32))


def test_occlusion_is_fully_lit_across_a_flat_uniform_depth_solid():
    """A flat region at constant depth with a constant normal: the occlusion prediction
    exactly matches every neighbour's actual depth (gap == 0 everywhere), so nothing should
    be darkened."""
    zbuf = np.full((20, 20), 5.0)
    nbuf = np.zeros((20, 20, 3), dtype=np.float32)
    nbuf[:, :, 1] = 1.0   # ny = 1, well clear of the near-zero clamp
    ao = sp._occlusion(zbuf, nbuf, unit=0.1)
    assert np.allclose(ao, 1.0)


def test_occlusion_darkens_a_concave_step():
    """A near region beside a far region, both facing the camera dead-on (nz = 1, ny ~ 0):
    the far side's prediction (its own depth) is unchanged by the step, but the near side
    sees a genuinely closer neighbour once the step is within range, so at least part of the
    buffer must come out darkened."""
    zbuf = np.zeros((20, 20), dtype=np.float32)
    zbuf[:, 10:] = 2.0   # right half sits nearer the camera (smaller z)
    nbuf = np.zeros((20, 20, 3), dtype=np.float32)
    nbuf[:, :, 2] = 1.0
    nbuf[:, :, 1] = 0.2
    ao = sp._occlusion(zbuf, nbuf, unit=0.1)
    assert ao.min() < 1.0
    assert ao.max() <= 1.0


# ------------------------------------------------------------
# _edge_strength
# ------------------------------------------------------------

def test_edge_strength_is_zero_deep_inside_a_flat_solid_region():
    zbuf = np.full((20, 20), 5.0)
    nbuf = np.zeros((20, 20, 3), dtype=np.float32)
    nbuf[:, :, 2] = 1.0
    strength = sp._edge_strength(zbuf, nbuf, unit=0.1, crease_deg=28.0)
    assert strength[10, 10] == pytest.approx(0.0)


def test_edge_strength_is_full_at_a_silhouette_boundary():
    zbuf = np.full((20, 20), np.inf)
    zbuf[5:15, 5:15] = 3.0   # a solid island surrounded by background
    nbuf = np.zeros((20, 20, 3), dtype=np.float32)
    nbuf[5:15, 5:15, 2] = 1.0
    strength = sp._edge_strength(zbuf, nbuf, unit=0.1, crease_deg=28.0)
    assert strength[5, 10] == pytest.approx(1.0)   # top row of the island: silhouette edge
    assert strength[10, 10] == pytest.approx(0.0)  # deep interior: no edge


def test_edge_strength_detects_a_sharp_crease_between_differing_normals():
    zbuf = np.full((20, 20), 5.0)
    nbuf = np.zeros((20, 20, 3), dtype=np.float32)
    nbuf[:, :10, 2] = 1.0            # left half faces +z
    nbuf[:, 10:, 0] = 1.0            # right half faces +x: a 90 degree crease at the seam
    strength = sp._edge_strength(zbuf, nbuf, unit=0.1, crease_deg=28.0)
    assert strength[10, 9] == pytest.approx(1.0)
    assert strength[10, 2] == pytest.approx(0.0)


# ------------------------------------------------------------
# render / _render_at / _rasterize -- end to end with rot_deg=(0,0,0)
#
# With no camera rotation, `_rotation` is the identity, so camera space equals world space
# and the front/back winding rule can be worked out by hand (see the module docstring above
# `_SQUARE_FRONT`).
# ------------------------------------------------------------

def test_render_of_an_empty_mesh_is_solid_background():
    image = sp.render(np.empty((0, 3, 3)), size=(16, 16), supersample=1)
    assert image.shape == (16, 16, 3)
    assert np.all(image == np.array(sp.BACKGROUND, dtype=np.uint8))


def test_render_of_a_degenerate_zero_extent_mesh_is_solid_background():
    tris = np.zeros((2, 3, 3))   # every vertex coincides: zero bounding-box extent
    image = sp.render(tris, size=(16, 16), supersample=1)
    assert np.all(image == np.array(sp.BACKGROUND, dtype=np.uint8))


def test_render_shades_a_front_facing_square_and_leaves_the_border_as_background():
    image = sp.render(_SQUARE_FRONT, size=(64, 64), rot_deg=(0, 0, 0),
                      edges=False, occlusion=False, supersample=1)
    center = image[32, 32]
    corner = image[0, 0]
    assert tuple(corner) == sp.BACKGROUND
    assert center[2] > center[0]   # blue channel above red: FACE_FRONT, not FACE_BACK


def test_render_shades_a_back_facing_square_in_the_defect_color():
    image = sp.render(_SQUARE_BACK, size=(64, 64), rot_deg=(0, 0, 0),
                      edges=False, occlusion=False, supersample=1)
    center = image[32, 32]
    assert center[0] > center[2]   # red channel above blue: FACE_BACK


def test_render_supersampled_output_has_the_requested_final_size():
    image = sp.render(_SQUARE_FRONT, size=(32, 32), rot_deg=(0, 0, 0), supersample=2)
    assert image.shape == (32, 32, 3)
    assert image.dtype == np.uint8


def test_render_of_the_cube_with_full_effects_produces_more_than_the_background_color():
    image = sp.render(_cube_array(), size=(48, 48), supersample=1)
    assert image.shape == (48, 48, 3)
    unique_colors = {tuple(c) for c in image.reshape(-1, 3)}
    assert len(unique_colors) > 1


# ------------------------------------------------------------
# write_png -- decoded by hand, not by a PNG library
# ------------------------------------------------------------

def _decode_png(data: bytes):
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos = 8
    width = height = None
    idat = b''
    while pos < len(data):
        (length,) = struct.unpack('>I', data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        if tag == b'IHDR':
            width, height = struct.unpack('>II', payload[:8])
        elif tag == b'IDAT':
            idat += payload
        pos += 8 + length + 4
    raw = zlib.decompress(idat)
    stride = width * 3 + 1
    rows = [raw[i * stride + 1:(i + 1) * stride] for i in range(height)]
    rgb = np.frombuffer(b''.join(rows), dtype=np.uint8).reshape(height, width, 3)
    return width, height, rgb


def test_write_png_round_trips_pixel_data(tmp_path):
    rgb = np.zeros((4, 3, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 0, 0]
    rgb[2, 2] = [0, 128, 255]
    path = tmp_path / 'out.png'
    sp.write_png(str(path), rgb)
    width, height, decoded = _decode_png(path.read_bytes())
    assert (width, height) == (3, 4)
    assert np.array_equal(decoded, rgb)


# ------------------------------------------------------------
# render_stl_to_png / render_one
# ------------------------------------------------------------

def test_render_stl_to_png_writes_a_file_and_returns_its_path(tmp_path):
    stl_path = tmp_path / 'cube.stl'
    png_path = tmp_path / 'cube.png'
    _write_binary_stl(str(stl_path), _cube_points())
    out = sp.render_stl_to_png(str(stl_path), str(png_path), size=(24, 24))
    assert out == png_path
    assert png_path.exists()
    width, height, _ = _decode_png(png_path.read_bytes())
    assert (width, height) == (24, 24)


def test_render_one_succeeds_and_writes_the_png_beside_the_stl(tmp_path):
    stl_path = tmp_path / 'part.stl'
    _write_binary_stl(str(stl_path), _cube_points())
    path, error = sp.render_one((str(stl_path), (16, 16), False, False, 1))
    assert path == str(stl_path)
    assert error is None
    assert stl_path.with_suffix('.png').exists()


def test_render_one_reports_the_error_instead_of_raising_for_a_missing_file(tmp_path):
    missing = tmp_path / 'missing.stl'
    path, error = sp.render_one((str(missing), (16, 16), False, False, 1))
    assert path == str(missing)
    assert error is not None
    assert 'Error' in error
