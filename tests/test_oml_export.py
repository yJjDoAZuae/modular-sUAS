"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for oml_export.py.

`import_vsp`/`list_model`/`export`/`_set_cad_len_unit` need the real OpenVSP Python API,
which turns out to be genuinely available and importable on this machine (OpenVSP is
installed under `C:\\Program Files`, just not on the venv's default `sys.path` -- exactly
what `import_vsp()`'s own path search exists to bridge) -- so unlike a `freecadcmd`-only
dependency, these are exercised for real, against the real committed `.vsp3`, into a
`tmp_path` output directory rather than the real committed `oml/` tree. The `vsp` API
object is imported once per test session (`import_vsp()` costs ~1.4s) via a module-scoped
fixture. `_vsp_python_roots`/`_model_hash`/`write_provenance`/`check_provenance` and
`main()`'s `--check` path need no OpenVSP at all and are tested directly.
"""
import hashlib
import json

import oml_export as oe
import pytest

# ------------------------------------------------------------
# _vsp_python_roots -- real machine state, plus a synthetic install layout
# ------------------------------------------------------------

def test_vsp_python_roots_finds_the_real_installed_openvsp_versions():
    roots = oe._vsp_python_roots()
    assert len(roots) >= 1
    assert all((r / 'openvsp').exists() for r in roots)


def test_vsp_python_roots_sorts_newest_version_first():
    roots = oe._vsp_python_roots()
    if len(roots) < 2:
        pytest.skip('only one OpenVSP install found on this machine')
    names = [r.parent.name for r in roots]
    assert names == sorted(names, reverse=True)


def test_vsp_python_roots_finds_an_install_via_openvsp_home(tmp_path, monkeypatch):
    install = tmp_path / 'CustomOpenVSP'
    (install / 'python' / 'openvsp').mkdir(parents=True)
    monkeypatch.setenv('OPENVSP_HOME', str(install))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'no_such_localappdata'))
    monkeypatch.setenv('ProgramFiles', str(tmp_path / 'no_such_program_files'))
    roots = oe._vsp_python_roots()
    assert install / 'python' in roots


def test_vsp_python_roots_finds_a_versioned_install_under_programfiles(tmp_path, monkeypatch):
    pf = tmp_path / 'ProgramFiles'
    (pf / 'OpenVSP-9.9.9-win64' / 'python' / 'openvsp').mkdir(parents=True)
    monkeypatch.delenv('OPENVSP_HOME', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'no_such_localappdata'))
    monkeypatch.setenv('ProgramFiles', str(pf))
    roots = oe._vsp_python_roots()
    assert pf / 'OpenVSP-9.9.9-win64' / 'python' in roots


# ------------------------------------------------------------
# import_vsp -- real import, plus the no-install-found failure path
# ------------------------------------------------------------

@pytest.fixture(scope='module')
def vsp():
    module, _root = oe.import_vsp()
    return module


def test_import_vsp_returns_a_working_api_module(vsp):
    assert isinstance(vsp.GetVSPVersion(), str)


def test_import_vsp_raises_a_clear_error_when_no_install_is_found(monkeypatch):
    monkeypatch.setattr(oe, '_vsp_python_roots', lambda: [])
    with pytest.raises(SystemExit, match='Could not import the OpenVSP Python API'):
        oe.import_vsp()


# ------------------------------------------------------------
# list_model / export / _set_cad_len_unit -- real committed .vsp3, real OpenVSP
# ------------------------------------------------------------

def test_list_model_reports_the_real_committed_geometry(vsp, capsys):
    oe.list_model(vsp)
    out = capsys.readouterr().out
    assert 'modular_sUAS_nose_tail.vsp3' in out
    assert 'Nose' in out
    assert 'Tail' in out


def test_export_writes_step_files_for_nose_and_tail(vsp, tmp_path, capsys):
    written = oe.export(vsp, tmp_path, fmt='step')
    names = sorted(p.name for p in written)
    assert names == ['vsp_nose.step', 'vsp_tail.step']
    for p in written:
        assert p.is_file()
        assert p.stat().st_size > 1000
    assert 'vsp_nose.step' in capsys.readouterr().out


def test_export_raises_when_a_named_geometry_is_missing_from_the_model(vsp, tmp_path, monkeypatch):
    monkeypatch.setattr(oe, 'EXPORTS', (('vsp_nose', ('NoSuchGeometry',)),))
    with pytest.raises(SystemExit, match='not found in'):
        oe.export(vsp, tmp_path, fmt='step')


def test_set_cad_len_unit_returns_a_list_of_container_parm_pairs(vsp):
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(oe.VSP3))
    result = oe._set_cad_len_unit(vsp, vsp.LEN_M)
    assert isinstance(result, list)
    assert all(isinstance(name, str) and isinstance(value, float) for name, value in result)


# ------------------------------------------------------------
# _model_hash -- real hashing, against a small synthetic fixture file
# ------------------------------------------------------------

def test_model_hash_matches_a_hand_computed_sha256(tmp_path, monkeypatch):
    fake = tmp_path / 'model.vsp3'
    fake.write_bytes(b'some vsp3 content')
    monkeypatch.setattr(oe, 'VSP3', fake)
    assert oe._model_hash() == hashlib.sha256(b'some vsp3 content').hexdigest()


def test_model_hash_changes_when_the_file_content_changes(tmp_path, monkeypatch):
    fake = tmp_path / 'model.vsp3'
    fake.write_bytes(b'version 1')
    monkeypatch.setattr(oe, 'VSP3', fake)
    first = oe._model_hash()
    fake.write_bytes(b'version 2')
    assert oe._model_hash() != first


# ------------------------------------------------------------
# write_provenance / check_provenance
# ------------------------------------------------------------

def _fake_model(tmp_path, monkeypatch, content=b'model bytes'):
    fake = tmp_path / 'model.vsp3'
    fake.write_bytes(content)
    monkeypatch.setattr(oe, 'VSP3', fake)
    return fake


def test_write_provenance_records_the_source_hash_and_file_list(tmp_path, monkeypatch):
    _fake_model(tmp_path, monkeypatch)
    written = [tmp_path / 'vsp_nose.step', tmp_path / 'vsp_tail.step']
    for w in written:
        w.write_bytes(b'x')
    path = oe.write_provenance(tmp_path, written)
    record = json.loads(path.read_text(encoding='utf-8'))
    assert record['source_sha256'] == oe._model_hash()
    assert record['files'] == ['vsp_nose.step', 'vsp_tail.step']
    assert record['model_unit_mm'] == oe.MODEL_UNIT_MM


def test_check_provenance_reports_no_provenance_when_absent(tmp_path, monkeypatch, capsys):
    _fake_model(tmp_path, monkeypatch)
    assert oe.check_provenance(tmp_path) == 1
    assert 'NO PROVENANCE' in capsys.readouterr().out


def test_check_provenance_reports_ok_when_the_hash_and_files_match(tmp_path, monkeypatch, capsys):
    _fake_model(tmp_path, monkeypatch)
    written = [tmp_path / 'vsp_nose.step']
    written[0].write_bytes(b'x')
    oe.write_provenance(tmp_path, written)

    assert oe.check_provenance(tmp_path) == 0
    assert 'OK  OML matches' in capsys.readouterr().out


def test_check_provenance_reports_stale_when_the_model_changed(tmp_path, monkeypatch, capsys):
    _fake_model(tmp_path, monkeypatch, content=b'original')
    oe.write_provenance(tmp_path, [])
    (tmp_path / 'model.vsp3').write_bytes(b'edited in the gui')

    assert oe.check_provenance(tmp_path) == 1
    assert 'STALE' in capsys.readouterr().out


def test_check_provenance_reports_missing_exported_files(tmp_path, monkeypatch, capsys):
    _fake_model(tmp_path, monkeypatch)
    oe.write_provenance(tmp_path, [tmp_path / 'vsp_nose.step'])   # never actually written

    assert oe.check_provenance(tmp_path) == 1
    out = capsys.readouterr().out
    assert 'MISSING' in out
    assert 'vsp_nose.step' in out


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

def test_main_check_mode_needs_no_openvsp_and_reports_missing_provenance(
    tmp_path, monkeypatch, capsys
):
    _fake_model(tmp_path, monkeypatch)
    result = oe.main(['--check', '--out', str(tmp_path)])
    assert result == 1
    assert 'NO PROVENANCE' in capsys.readouterr().out


def test_main_raises_when_the_source_model_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(oe, 'VSP3', tmp_path / 'does_not_exist.vsp3')
    with pytest.raises(SystemExit, match='Source model not found'):
        oe.main([])


def test_main_list_mode_reports_the_real_model_without_writing_anything(tmp_path, capsys):
    result = oe.main(['--list'])
    assert result == 0
    out = capsys.readouterr().out
    assert 'Nose' in out and 'Tail' in out


def test_main_full_export_writes_step_files_and_provenance_into_the_given_out_dir(tmp_path):
    result = oe.main(['--out', str(tmp_path)])
    assert result == 0
    assert (tmp_path / 'vsp_nose.step').is_file()
    assert (tmp_path / 'vsp_tail.step').is_file()
    assert (tmp_path / oe.PROVENANCE).is_file()
