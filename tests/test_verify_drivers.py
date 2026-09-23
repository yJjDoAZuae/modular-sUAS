"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for verify_drivers.py.

`find_drivers` and `render` are directly testable. The report classification (OK / WARNED /
FAILED / aggregator) lives entirely inside `main()`'s nested `run()` closure with no
standalone function to call -- unlike this plan's other CLI tools, that closure is where
this module's real logic is, so it is exercised through `main()` itself, with the
module-level `render` (looked up dynamically by `pool.map(render, jobs)`, so monkeypatching
the module attribute reaches it) faked out to avoid ever invoking OpenSCAD.
"""
import struct

import pytest
import verify_drivers as vd

# ------------------------------------------------------------
# find_drivers
# ------------------------------------------------------------

def test_find_drivers_includes_a_file_with_no_module_definitions(tmp_path):
    (tmp_path / 'fuselage_corner.scad').write_text('U = 1.5;\ncorner_geometry(U);\n')
    assert [p.name for p in vd.find_drivers(tmp_path)] == ['fuselage_corner.scad']


def test_find_drivers_excludes_a_file_that_defines_a_module(tmp_path):
    (tmp_path / 'corner_geometry.scad').write_text('module corner_geometry(U) {\n cube(U);\n}\n')
    assert vd.find_drivers(tmp_path) == []


def test_find_drivers_detects_an_indented_module_definition(tmp_path):
    (tmp_path / 'lib.scad').write_text('  module helper(x) {\n cube(x);\n}\n')
    assert vd.find_drivers(tmp_path) == []


def test_find_drivers_returns_files_sorted_by_name(tmp_path):
    for name in ('zeta.scad', 'alpha.scad', 'mid.scad'):
        (tmp_path / name).write_text('x = 1;\n')
    assert [p.name for p in vd.find_drivers(tmp_path)] == \
        ['alpha.scad', 'mid.scad', 'zeta.scad']


def test_find_drivers_ignores_non_scad_files(tmp_path):
    (tmp_path / 'driver.scad').write_text('x = 1;\n')
    (tmp_path / 'readme.txt').write_text('x = 1;\n')
    assert [p.name for p in vd.find_drivers(tmp_path)] == ['driver.scad']


# ------------------------------------------------------------
# render
# ------------------------------------------------------------

def test_render_invokes_openscad_and_decodes_stderr(tmp_path, monkeypatch):
    calls = []

    class _Done:
        returncode = 2
        stderr = b'WARNING: undefined variable\n'

    def fake_run(cmd, stdout=None, stderr=None):
        calls.append(cmd)
        return _Done()

    monkeypatch.setattr(vd.subprocess, 'run', fake_run)
    scad, out_stl, code, err = vd.render((tmp_path / 'a.scad', tmp_path / 'a.stl', 'openscad'))

    assert calls == [['openscad', '-o', str(tmp_path / 'a.stl'), str(tmp_path / 'a.scad')]]
    assert code == 2
    assert err == 'WARNING: undefined variable\n'


# ------------------------------------------------------------
# main -- report classification, exercised through the real nested `run()` closure
# ------------------------------------------------------------

def _write_binary_stl_with_n_triangles(path, n):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as f:
        f.write(b'test'.ljust(80, b'\0'))
        f.write(struct.pack('<I', n))
        for _ in range(n):
            f.write(struct.pack('<3f', 0.0, 0.0, 0.0))
            for _ in range(3):
                f.write(struct.pack('<3f', 1.0, 1.0, 1.0))
            f.write(struct.pack('<H', 0))


def _driver(scad_dir, name):
    (scad_dir / name).write_text('U = 1;\ngeometry(U);\n')


def _run_main(monkeypatch, scad_dir, keep_dir, fake_render, capsys):
    monkeypatch.setenv('OPENSCADPATH', 'dummy')
    monkeypatch.setattr(vd, 'render', fake_render)
    code = vd.main(['--scad-dir', str(scad_dir), '--keep', str(keep_dir)])
    return code, capsys.readouterr().out


def test_main_raises_when_openscadpath_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENSCADPATH', raising=False)
    with pytest.raises(SystemExit, match='OPENSCADPATH is not set'):
        vd.main(['--scad-dir', str(tmp_path)])


def test_main_reports_no_drivers_when_the_scad_dir_is_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OPENSCADPATH', 'dummy')
    result = vd.main(['--scad-dir', str(tmp_path)])
    assert result == 1
    assert 'no driver .scad files' in capsys.readouterr().out


def test_main_reports_ok_for_a_clean_render_with_geometry(tmp_path, monkeypatch, capsys):
    scad_dir, keep_dir = tmp_path / 'scad', tmp_path / 'keep'
    scad_dir.mkdir()
    _driver(scad_dir, 'fuselage_corner.scad')

    def fake_render(job):
        scad, out_stl, _binary = job
        _write_binary_stl_with_n_triangles(out_stl, 12)
        return scad, out_stl, 0, ''

    code, out = _run_main(monkeypatch, scad_dir, keep_dir, fake_render, capsys)
    assert code == 0
    assert 'OK       fuselage_corner.scad  (12 tris)' in out
    assert 'ALL DRIVERS OK' in out


def test_main_reports_warned_and_lists_the_warning_lines(tmp_path, monkeypatch, capsys):
    scad_dir, keep_dir = tmp_path / 'scad', tmp_path / 'keep'
    scad_dir.mkdir()
    _driver(scad_dir, 'fuselage_corner.scad')

    def fake_render(job):
        scad, out_stl, _binary = job
        _write_binary_stl_with_n_triangles(out_stl, 4)
        return scad, out_stl, 0, 'WARNING: Ignoring unknown variable foo\n'

    code, out = _run_main(monkeypatch, scad_dir, keep_dir, fake_render, capsys)
    assert code == 1
    assert 'WARNED   fuselage_corner.scad  (4 tris)' in out
    assert 'Ignoring unknown variable foo' in out
    assert '1 failed, 1 rendered with warnings' not in out   # 0 failed, 1 warned
    assert '0 failed, 1 rendered with warnings' in out


def test_main_reports_failed_for_a_nonzero_exit_with_a_real_error(tmp_path, monkeypatch, capsys):
    scad_dir, keep_dir = tmp_path / 'scad', tmp_path / 'keep'
    scad_dir.mkdir()
    _driver(scad_dir, 'fuselage_corner.scad')

    def fake_render(job):
        scad, out_stl, _binary = job
        return scad, out_stl, 1, 'ERROR: Parser error in file, line 3\n'

    code, out = _run_main(monkeypatch, scad_dir, keep_dir, fake_render, capsys)
    assert code == 1
    assert 'FAILED   fuselage_corner.scad  (exit 1)' in out
    assert 'Parser error in file, line 3' in out


def test_main_reports_aggregator_for_empty_output_with_no_warning(tmp_path, monkeypatch, capsys):
    """An aggregator of includes has no top-level geometry: OpenSCAD exits non-zero, but
    with no WARNING/ERROR/TRACE-prefixed line -- the `not notes` guard's positive case."""
    scad_dir, keep_dir = tmp_path / 'scad', tmp_path / 'keep'
    scad_dir.mkdir()
    _driver(scad_dir, 'fuselage_geometry.scad')

    def fake_render(job):
        scad, out_stl, _binary = job
        return scad, out_stl, 1, 'Current top level object is empty.\n'

    code, out = _run_main(monkeypatch, scad_dir, keep_dir, fake_render, capsys)
    assert code == 0
    assert 'no geom  fuselage_geometry.scad  (aggregator, not a driver)' in out
    assert 'ALL DRIVERS OK' in out
    assert '1 aggregator(s) skipped' in out


def test_main_reports_failed_not_aggregator_when_empty_output_carries_a_warning(
    tmp_path, monkeypatch, capsys
):
    """The regression this module's own comment names: a broken driver (an undef import,
    say) also produces empty output. Without the `not notes` guard this would be waved
    through as a harmless aggregator instead of reported as the broken driver it is."""
    scad_dir, keep_dir = tmp_path / 'scad', tmp_path / 'keep'
    scad_dir.mkdir()
    _driver(scad_dir, 'nose_cowl.scad')

    def fake_render(job):
        scad, out_stl, _binary = job
        return (scad, out_stl, 1,
                'WARNING: Can\'t find import file oml.stl\n'
                'Current top level object is empty.\n')

    code, out = _run_main(monkeypatch, scad_dir, keep_dir, fake_render, capsys)
    assert code == 1
    assert 'FAILED   nose_cowl.scad  (exit 1)' in out
    assert 'no geom' not in out


def test_main_reports_empty_geometry_at_zero_exit_as_aggregator_too(tmp_path, monkeypatch, capsys):
    """The second empty-geometry path: a clean (code 0) render whose STL mesh_stats reads as
    zero triangles -- reached when the file was never written at all."""
    scad_dir, keep_dir = tmp_path / 'scad', tmp_path / 'keep'
    scad_dir.mkdir()
    _driver(scad_dir, 'fuselage_geometry.scad')

    def fake_render(job):
        scad, out_stl, _binary = job
        return scad, out_stl, 0, ''   # out_stl never written

    code, out = _run_main(monkeypatch, scad_dir, keep_dir, fake_render, capsys)
    assert code == 0
    assert 'no geom  fuselage_geometry.scad  (aggregator, not a driver)' in out


def test_main_writes_rendered_stls_into_the_keep_directory(tmp_path, monkeypatch, capsys):
    scad_dir, keep_dir = tmp_path / 'scad', tmp_path / 'keep'
    scad_dir.mkdir()
    _driver(scad_dir, 'fuselage_corner.scad')

    written = []

    def fake_render(job):
        scad, out_stl, _binary = job
        written.append(out_stl)
        _write_binary_stl_with_n_triangles(out_stl, 1)
        return scad, out_stl, 0, ''

    _run_main(monkeypatch, scad_dir, keep_dir, fake_render, capsys)
    assert written == [keep_dir / 'fuselage_corner.stl']
