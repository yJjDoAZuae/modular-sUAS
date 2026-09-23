"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for verify_scad_change.py.

`openscad_binary`/`sample_parts` are pure. `_render` is tested by faking `subprocess.run`
so no real OpenSCAD process is spawned. `verify()` is tested by faking the module-level
`_render` (looked up dynamically by `pool.map(_render, jobs)`, so monkeypatching the module
attribute reaches it) -- this exercises the real staging/cleanup and comparison logic
against real STL fixtures without ever invoking OpenSCAD. `main()` (argparse/tempdir
wiring) is not covered, consistent with the other CLI-entry-point modules in this plan.
"""
import struct
from pathlib import Path

import pytest
import verify_scad_change as vsc

# ------------------------------------------------------------
# openscad_binary
# ------------------------------------------------------------

def test_openscad_binary_raises_a_clear_error_when_unset(monkeypatch):
    monkeypatch.delenv('OPENSCADPATH', raising=False)
    with pytest.raises(SystemExit, match='OPENSCADPATH is not set'):
        vsc.openscad_binary()


def test_openscad_binary_joins_the_env_root_with_the_executable_name(monkeypatch):
    monkeypatch.setenv('OPENSCADPATH', 'C:\\Program Files\\OpenSCAD')
    import os
    # os.path.join deliberately, not pathlib's `/`: this must reproduce openscad_binary's
    # own os.path.join call exactly, which pathlib would not necessarily match.
    assert vsc.openscad_binary() == os.path.join(  # noqa: PTH118
        'C:\\Program Files\\OpenSCAD', 'openscad')


# ------------------------------------------------------------
# sample_parts
# ------------------------------------------------------------

def _touch(root, *names):
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text('// placeholder\n')


def test_sample_parts_selects_only_stl_scad_files_matching_a_kind(tmp_path):
    _touch(tmp_path, 'U_1.0__corner_FX_1.0.stl.scad', 'U_1.0__corner_FX_1.0.stl',
          'notes.txt')
    parts = vsc.sample_parts(tmp_path, per_kind=2)
    assert [p.name for p in parts] == ['U_1.0__corner_FX_1.0.stl.scad']


def test_sample_parts_excludes_boom_bulkhead_from_the_plain_bulkhead_kind(tmp_path):
    """Mirrors verify_sweep_change.sample_names's identical exclusion rule: without it, a
    boom-bulkhead file sorting first could starve every real bulkhead file out of a
    per_kind=1 sample entirely."""
    _touch(tmp_path, 'boom_bulkhead_x.stl.scad',
          'zz_bulkhead_a.stl.scad', 'zz_bulkhead_b.stl.scad', 'zz_bulkhead_c.stl.scad')
    parts = vsc.sample_parts(tmp_path, per_kind=1)
    names = [p.name for p in parts]
    assert 'boom_bulkhead_x.stl.scad' in names
    assert any(n.startswith('zz_bulkhead') for n in names)


def test_sample_parts_caps_the_count_per_kind(tmp_path):
    names = [f'U_1.0__corner_FX_{i}.0.stl.scad' for i in range(10)]
    _touch(tmp_path, *names)
    parts = vsc.sample_parts(tmp_path, per_kind=3)
    assert len(parts) == 3


def test_sample_parts_returns_empty_for_a_kind_with_no_matches(tmp_path):
    assert vsc.sample_parts(tmp_path, per_kind=2) == []


# ------------------------------------------------------------
# _render
# ------------------------------------------------------------

def test_render_invokes_openscad_with_the_staged_file_and_output_path(tmp_path, monkeypatch):
    calls = []

    class _Done:
        returncode = 0

    def fake_run(cmd, stdout=None, stderr=None):
        calls.append(cmd)
        return _Done()

    monkeypatch.setattr(vsc.subprocess, 'run', fake_run)
    staged = tmp_path / 'part.verify.scad'
    out_stl = tmp_path / 'out' / 'part.stl'
    staged, result_stl, code = vsc._render((staged, out_stl, '/bin/openscad'))

    assert calls == [['/bin/openscad', '-o', str(out_stl), str(staged)]]
    assert result_stl == out_stl
    assert code == 0


def test_render_returns_the_nonzero_exit_code_on_failure(tmp_path, monkeypatch):
    class _Done:
        returncode = 1

    monkeypatch.setattr(vsc.subprocess, 'run', lambda *a, **k: _Done())
    _staged, _out, code = vsc._render((tmp_path / 'a.scad', tmp_path / 'a.stl', 'openscad'))
    assert code == 1


# ------------------------------------------------------------
# verify -- real staging/cleanup/comparison logic, with _render faked out
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


def _cube_points(scale=1.0):
    return [[(_CUBE_VERTS[i][0] * scale, _CUBE_VERTS[i][1] * scale,
             _CUBE_VERTS[i][2] * scale) for i in tri] for tri in _CUBE_TRI_IDX]


def _write_binary_stl(path, triangles):
    with Path(path).open('wb') as f:
        f.write(b'test'.ljust(80, b'\0'))
        f.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            f.write(struct.pack('<3f', 0.0, 0.0, 0.0))
            for point in tri:
                f.write(struct.pack('<3f', *point))
            f.write(struct.pack('<H', 0))


def _stage_part(output_dir, name, scale=1.0):
    """A `.stl` and its matching `.stl.scad` sitting together, as a real sweep leaves them."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_binary_stl(output_dir / f'{name}.stl', _cube_points(scale))
    (output_dir / f'{name}.stl.scad').write_text('// placeholder\n')


def test_verify_reports_no_parts_to_verify_when_the_tree_is_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OPENSCADPATH', 'x')
    output = tmp_path / 'out'
    output.mkdir()
    scratch = tmp_path / 'scratch'
    assert vsc.verify(output, scratch) == 1
    assert 'nothing to verify' in capsys.readouterr().out


def test_verify_raises_when_openscadpath_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENSCADPATH', raising=False)
    output = tmp_path / 'out'
    output.mkdir()
    with pytest.raises(SystemExit, match='OPENSCADPATH is not set'):
        vsc.verify(output, tmp_path / 'scratch')


def test_verify_reports_ok_and_identical_when_the_rerender_matches(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OPENSCADPATH', 'x')
    output = tmp_path / 'out'
    _stage_part(output, 'U_1.0__corner_FX_1.0')

    def fake_render(job):
        staged, out_stl, _binary = job
        _write_binary_stl(out_stl, _cube_points())   # identical geometry
        return staged, out_stl, 0

    monkeypatch.setattr(vsc, '_render', fake_render)
    result = vsc.verify(output, tmp_path / 'scratch', per_kind=2)
    out = capsys.readouterr().out

    assert result == 0
    assert 'OK    U_1.0__corner_FX_1.0.stl' in out
    assert 'IDENTICAL GEOMETRY across 1 part(s)' in out
    # The staged .verify.scad copy must be cleaned up, not left in the output tree.
    assert list(output.glob('*.verify.scad')) == []


def test_verify_reports_diff_and_geometry_changed_when_volumes_differ(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OPENSCADPATH', 'x')
    output = tmp_path / 'out'
    _stage_part(output, 'U_1.0__corner_FX_1.0')

    def fake_render(job):
        staged, out_stl, _binary = job
        _write_binary_stl(out_stl, _cube_points(scale=2.0))   # 8x the volume
        return staged, out_stl, 0

    monkeypatch.setattr(vsc, '_render', fake_render)
    result = vsc.verify(output, tmp_path / 'scratch', per_kind=2)
    out = capsys.readouterr().out

    assert result == 1
    assert 'DIFF  U_1.0__corner_FX_1.0.stl' in out
    assert 'GEOMETRY CHANGED' in out


def test_verify_reports_a_nonzero_render_exit_as_render_failed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OPENSCADPATH', 'x')
    output = tmp_path / 'out'
    _stage_part(output, 'U_1.0__corner_FX_1.0')

    def fake_render(job):
        staged, out_stl, _binary = job
        return staged, out_stl, 1   # openscad "failed"; nothing written

    monkeypatch.setattr(vsc, '_render', fake_render)
    result = vsc.verify(output, tmp_path / 'scratch', per_kind=2)
    out = capsys.readouterr().out

    assert result == 1
    assert 'RENDER FAILED' in out and 'exit 1' in out
    assert list(output.glob('*.verify.scad')) == []


def test_verify_reports_an_unreadable_rerendered_mesh_without_crashing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OPENSCADPATH', 'x')
    output = tmp_path / 'out'
    _stage_part(output, 'U_1.0__corner_FX_1.0')

    def fake_render(job):
        staged, out_stl, _binary = job
        out_stl.parent.mkdir(parents=True, exist_ok=True)
        out_stl.write_bytes(b'not a real stl')
        return staged, out_stl, 0

    monkeypatch.setattr(vsc, '_render', fake_render)
    result = vsc.verify(output, tmp_path / 'scratch', per_kind=2)
    out = capsys.readouterr().out

    assert result == 1
    assert 'unreadable' in out


def test_verify_cleans_up_staged_files_even_when_rendering_raises(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENSCADPATH', 'x')
    output = tmp_path / 'out'
    _stage_part(output, 'U_1.0__corner_FX_1.0')

    def boom(job):
        raise RuntimeError('synthetic render pool failure')

    monkeypatch.setattr(vsc, '_render', boom)
    with pytest.raises(RuntimeError):
        vsc.verify(output, tmp_path / 'scratch', per_kind=2)
    assert list(output.glob('*.verify.scad')) == []
