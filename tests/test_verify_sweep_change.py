"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for verify_sweep_change.py.

`sample_names` and `compare` are pure filesystem/geometry-comparison logic and are tested
directly with hand-built trees. `build_sample` is tested against the real sweep machinery
(fuselage_variants, real CSVs) exactly as in test_scad_snapshot.py/test_params_snapshot.py,
but with `fv.solid_render` replaced by a recorder *before* the call so that `build_sample`'s
own `real_render = fv.solid_render` capture points at the fake -- this exercises its genuine
sample-membership decision and its restore-on-exit, without ever invoking OpenSCAD. `main()`
(argparse/tempdir wiring) is not covered, consistent with the other CLI-entry-point modules
in this plan.
"""
import struct
from pathlib import Path

import fuselage_variants as fv
import mesh_stats
import pytest
import verify_sweep_change as vsc

# ------------------------------------------------------------
# sample_names
# ------------------------------------------------------------

def _touch(root, *names):
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b'')


def test_sample_names_selects_only_files_matching_each_kind(tmp_path):
    _touch(tmp_path, 'U_1.0__corner_FX_1.0.stl', 'U_1.0__nose_type_a.stl')
    wanted = vsc.sample_names(tmp_path, per_kind=2)
    assert 'U_1.0__corner_FX_1.0.stl' in wanted
    assert 'U_1.0__nose_type_a.stl' in wanted


def test_sample_names_excludes_partial_stl_files(tmp_path):
    _touch(tmp_path, 'U_1.0__corner_FX_1.0.stl', 'U_1.0__corner_FX_2.0.partial.stl')
    wanted = vsc.sample_names(tmp_path, per_kind=5)
    assert 'U_1.0__corner_FX_1.0.stl' in wanted
    assert not any('partial' in n for n in wanted)


def test_sample_names_does_not_let_a_boom_bulkhead_file_starve_the_bulkhead_kind(tmp_path):
    """'bulkhead' is a substring of 'boom_bulkhead', so without the module's explicit
    exclusion, the plain 'bulkhead' kind's scan would also match boom-bulkhead files. Named
    so that if it sorted first and per_kind capped the pick at 1, the bug would starve every
    real bulkhead file out of the sample entirely -- not just double-count one file, which a
    set's own de-duplication would hide."""
    _touch(tmp_path, 'boom_bulkhead_x.stl',        # sorts first if wrongly included
          'zz_bulkhead_a.stl', 'zz_bulkhead_b.stl', 'zz_bulkhead_c.stl')
    wanted = vsc.sample_names(tmp_path, per_kind=1)
    assert 'boom_bulkhead_x.stl' in wanted           # picked under the boom_bulkhead kind
    assert any(n.startswith('zz_bulkhead') for n in wanted)   # a real bulkhead file too


def test_sample_names_caps_the_count_per_kind_and_spreads_across_the_range(tmp_path):
    names = [f'U_1.0__corner_FX_{i}.0.stl' for i in range(10)]
    _touch(tmp_path, *names)
    wanted = vsc.sample_names(tmp_path, per_kind=3)
    assert len(wanted) == 3
    assert wanted.issubset(set(names))


def test_sample_names_returns_an_empty_set_when_nothing_matches_any_kind(tmp_path):
    _touch(tmp_path, 'unrelated_file.stl')
    assert vsc.sample_names(tmp_path, per_kind=2) == set()


# ------------------------------------------------------------
# build_sample -- real sweep machinery, fake solid_render so no OpenSCAD ever runs
# ------------------------------------------------------------

_ONE_SWEEP = (vsc.SWEEPS[0],)   # ('corner', 'run_corner_parametric_sweep', (...))


def _discover_one_stl_name(monkeypatch):
    """A real filename the corner sweep would produce, found the same way
    test_scad_snapshot.py does: a fake solid_render that only records names."""
    names = []

    def fake(_scad_obj, _output_dir, filename):
        names.append(filename)
        return (filename + '.scad', filename + '.stl', filename + '.png')

    monkeypatch.setattr(fv, 'solid_render', fake)
    _kind, driver, axis_names = _ONE_SWEEP[0]
    import tempfile
    with tempfile.TemporaryDirectory(prefix='discover_') as scratch:
        getattr(fv, driver)(fv.axes(*axis_names), scratch)
    assert names, 'the corner sweep produced no candidate filenames to sample from'
    return Path(sorted(names)[0]).with_suffix('.stl').name


def test_build_sample_forwards_only_the_wanted_part_to_the_real_renderer(
    monkeypatch, tmp_path
):
    wanted_stl = _discover_one_stl_name(monkeypatch)

    calls = []

    def fake_real_render(scad_obj, output_dir, filename):
        calls.append(filename)
        return (filename + '.scad', filename + '.stl', filename + '.png')

    monkeypatch.setattr(vsc, 'SWEEPS', _ONE_SWEEP)
    monkeypatch.setattr(fv, 'solid_render', fake_real_render)

    vsc.build_sample(tmp_path, {wanted_stl}, workers=1)

    assert len(calls) >= 1
    assert all(Path(c).with_suffix('.stl').name == wanted_stl for c in calls)
    # build_sample must restore solid_render to whatever it was before the call.
    assert fv.solid_render is fake_real_render


def test_build_sample_forwards_nothing_when_the_wanted_set_is_empty(monkeypatch, tmp_path):
    calls = []

    def fake_real_render(scad_obj, output_dir, filename):
        calls.append(filename)
        return (filename + '.scad', filename + '.stl', filename + '.png')

    monkeypatch.setattr(vsc, 'SWEEPS', _ONE_SWEEP)
    monkeypatch.setattr(fv, 'solid_render', fake_real_render)

    vsc.build_sample(tmp_path, set(), workers=1)

    assert calls == []
    assert fv.solid_render is fake_real_render


def test_build_sample_restores_solid_render_even_if_a_driver_raises(monkeypatch, tmp_path):
    def fake_real_render(*_a, **_k):
        return ('a', 'b', 'c')

    monkeypatch.setattr(vsc, 'SWEEPS', _ONE_SWEEP)
    monkeypatch.setattr(fv, 'solid_render', fake_real_render)

    def boom(*_a, **_k):
        raise RuntimeError('synthetic driver failure')

    monkeypatch.setattr(fv, _ONE_SWEEP[0][1], boom)

    with pytest.raises(RuntimeError):
        vsc.build_sample(tmp_path, set(), workers=1)
    assert fv.solid_render is fake_real_render


# ------------------------------------------------------------
# compare -- pure geometry comparison against real STL files
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


def _cube_points(scale=1.0, offset=(0.0, 0.0, 0.0)):
    ox, oy, oz = offset
    return [[(_CUBE_VERTS[i][0] * scale + ox, _CUBE_VERTS[i][1] * scale + oy,
             _CUBE_VERTS[i][2] * scale + oz) for i in tri] for tri in _CUBE_TRI_IDX]


def _write_binary_stl(path, triangles):
    with Path(path).open('wb') as f:
        f.write(b'test'.ljust(80, b'\0'))
        f.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            f.write(struct.pack('<3f', 0.0, 0.0, 0.0))
            for point in tri:
                f.write(struct.pack('<3f', *point))
            f.write(struct.pack('<H', 0))


def test_compare_reports_identical_geometry_as_ok(tmp_path, capsys):
    ref, scratch = tmp_path / 'ref', tmp_path / 'scratch'
    ref.mkdir()
    scratch.mkdir()
    name = 'U_1.0__corner_FX_1.0.stl'
    _write_binary_stl(ref / name, _cube_points())
    _write_binary_stl(scratch / name, _cube_points())

    assert vsc.compare(ref, scratch, {name}, tol=mesh_stats.VOLUME_TOL) == 0
    out = capsys.readouterr().out
    assert f'OK    {name}' in out
    assert 'IDENTICAL GEOMETRY across 1 sampled part(s)' in out


def test_compare_reports_a_missing_part_as_not_produced(tmp_path, capsys):
    ref, scratch = tmp_path / 'ref', tmp_path / 'scratch'
    ref.mkdir()
    scratch.mkdir()
    name = 'U_1.0__corner_FX_1.0.stl'
    _write_binary_stl(ref / name, _cube_points())

    assert vsc.compare(ref, scratch, {name}, tol=mesh_stats.VOLUME_TOL) == 1
    out = capsys.readouterr().out
    assert f'GONE  {name}' in out
    assert f'NOT PRODUCED  {name}' in out
    assert 'GEOMETRY CHANGED' in out


def test_compare_reports_a_volume_mismatch_as_diff(tmp_path, capsys):
    ref, scratch = tmp_path / 'ref', tmp_path / 'scratch'
    ref.mkdir()
    scratch.mkdir()
    name = 'U_1.0__corner_FX_1.0.stl'
    _write_binary_stl(ref / name, _cube_points(scale=1.0))
    _write_binary_stl(scratch / name, _cube_points(scale=1.5))   # volume differs a lot

    assert vsc.compare(ref, scratch, {name}, tol=mesh_stats.VOLUME_TOL) == 1
    out = capsys.readouterr().out
    assert f'DIFF  {name}' in out
    assert 'GEOMETRY CHANGED' in out


def test_compare_reports_an_unreadable_produced_mesh_without_crashing(tmp_path, capsys):
    ref, scratch = tmp_path / 'ref', tmp_path / 'scratch'
    ref.mkdir()
    scratch.mkdir()
    name = 'U_1.0__corner_FX_1.0.stl'
    _write_binary_stl(ref / name, _cube_points())
    _write_binary_stl(scratch / name, _cube_points())
    # Truncate the produced copy so mesh_stats.mesh_stats raises TruncatedMesh.
    data = (scratch / name).read_bytes()
    (scratch / name).write_bytes(data[:-40])

    assert vsc.compare(ref, scratch, {name}, tol=mesh_stats.VOLUME_TOL) == 1
    out = capsys.readouterr().out
    assert 'unreadable' in out


def test_compare_surface_distance_tier_catches_what_the_cheap_tier_would_miss(
    tmp_path, capsys, monkeypatch
):
    """The case the module's own docstring names: volume and bounding box agree (the cheap
    tier passes) but the surface has moved. `same_geometry` is monkeypatched to force that
    cheap-tier verdict -- constructing a real mesh pair that is simultaneously volume- and
    bbox-identical yet surface-displaced is exactly what `mesh_stats`'s own test suite
    already exercises the machinery for; forcing the verdict here isolates the one thing
    this test is actually about: `compare()`'s own `cheap_ok and not far` branch. The
    surface displacement itself is real (a genuine translation, well above surface_tol)."""
    import mesh_stats as ms
    monkeypatch.setattr(ms, 'same_geometry', lambda *_a, **_k: True)

    ref, scratch = tmp_path / 'ref', tmp_path / 'scratch'
    ref.mkdir()
    scratch.mkdir()
    name = 'U_1.0__corner_FX_1.0.stl'
    _write_binary_stl(ref / name, _cube_points())
    _write_binary_stl(scratch / name, _cube_points(offset=(0.01, 0.0, 0.0)))

    result = vsc.compare(ref, scratch, {name}, tol=mesh_stats.VOLUME_TOL, samples=200)
    out = capsys.readouterr().out
    assert result == 1
    assert 'volume and bbox agree but the surface moved' in out


def test_compare_surface_distance_tier_reports_ok_with_detail_when_within_tolerance(
    tmp_path, capsys
):
    ref, scratch = tmp_path / 'ref', tmp_path / 'scratch'
    ref.mkdir()
    scratch.mkdir()
    name = 'U_1.0__corner_FX_1.0.stl'
    _write_binary_stl(ref / name, _cube_points())
    _write_binary_stl(scratch / name, _cube_points())

    assert vsc.compare(ref, scratch, {name}, tol=mesh_stats.VOLUME_TOL, samples=200) == 0
    out = capsys.readouterr().out
    assert f'OK    {name}' in out
    assert 'surface max' in out
