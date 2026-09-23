"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for freecad_render.py.

`freecadcmd_path`/`freecad_gui_path` are tested against BOTH real machine state (FreeCAD 1.1
is genuinely installed under `%LOCALAPPDATA%\\Programs` on this machine, exactly the fallback
path the function searches) and monkeypatched failure paths, the same "test the real thing
when it is genuinely available" approach used for OpenVSP in test_oml_export.py.
`definition_text` is exercised for real (it depends on `geometry_version.freecad_version`,
already covered in full by IP-TEST-3's test_geometry_version.py). `build_command` and
`check_fcstd_length` are pure and get direct coverage, including the real IP-FC-69 path-length
regression.
"""
from pathlib import Path

import freecad_render as fr
import pytest

# ------------------------------------------------------------
# _load_part_kinds / KINDS
# ------------------------------------------------------------

def test_load_part_kinds_returns_a_module_with_kinds_and_geometry_roots():
    module = fr._load_part_kinds()
    assert hasattr(module, 'KINDS')
    assert hasattr(module, 'geometry_roots')


def test_kinds_is_sorted_and_non_empty():
    assert list(fr.KINDS) == sorted(fr.KINDS)
    assert len(fr.KINDS) > 0
    assert 'corner' in fr.KINDS


# ------------------------------------------------------------
# freecadcmd_path
# ------------------------------------------------------------

def test_freecadcmd_path_resolves_to_a_real_file_on_this_machine():
    """FreeCAD 1.1 is genuinely installed on this machine (LOCALAPPDATA fallback path) --
    tested against real state rather than only against mocks."""
    path = fr.freecadcmd_path()
    assert Path(path).is_file()
    assert path.lower().endswith('freecadcmd.exe') or path.lower().endswith('freecadcmd')


def test_freecadcmd_path_uses_the_explicit_env_var_when_set(tmp_path, monkeypatch):
    fake = tmp_path / 'freecadcmd.exe'
    fake.write_bytes(b'')
    monkeypatch.setenv(fr.ENV_VAR, str(fake))
    assert fr.freecadcmd_path() == str(fake)


def test_freecadcmd_path_raises_when_the_explicit_env_var_points_nowhere(monkeypatch):
    monkeypatch.setenv(fr.ENV_VAR, r'C:\does\not\exist\freecadcmd.exe')
    with pytest.raises(fr.FreeCADNotFound, match='does not exist'):
        fr.freecadcmd_path()


def test_freecadcmd_path_raises_with_a_clear_message_when_nothing_is_found(monkeypatch):
    monkeypatch.delenv(fr.ENV_VAR, raising=False)
    monkeypatch.setattr(fr.shutil, 'which', lambda name: None)
    monkeypatch.setattr(fr, '_DEFAULT_PATHS', [r'C:\nowhere\freecadcmd.exe'])
    with pytest.raises(fr.FreeCADNotFound, match='freecadcmd not found'):
        fr.freecadcmd_path()


# ------------------------------------------------------------
# freecad_gui_path
# ------------------------------------------------------------

def test_freecad_gui_path_resolves_to_a_real_file_beside_freecadcmd():
    path = fr.freecad_gui_path()
    assert Path(path).is_file()
    assert Path(path).parent == Path(fr.freecadcmd_path()).parent


def test_freecad_gui_path_uses_the_explicit_env_var_when_set(tmp_path, monkeypatch):
    fake = tmp_path / 'freecad.exe'
    fake.write_bytes(b'')
    monkeypatch.setenv(fr.GUI_ENV_VAR, str(fake))
    assert fr.freecad_gui_path() == str(fake)


def test_freecad_gui_path_raises_when_the_explicit_env_var_points_nowhere(monkeypatch):
    monkeypatch.setenv(fr.GUI_ENV_VAR, r'C:\does\not\exist\freecad.exe')
    with pytest.raises(fr.FreeCADNotFound, match='does not exist'):
        fr.freecad_gui_path()


def test_freecad_gui_path_raises_with_a_clear_message_when_nothing_is_found(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(fr.GUI_ENV_VAR, raising=False)
    # freecadcmd itself still resolves (real), but nothing named 'freecad' sits beside a
    # fake stand-in, and the search elsewhere is blocked too.
    fake_cmd = tmp_path / 'freecadcmd.exe'
    fake_cmd.write_bytes(b'')
    monkeypatch.setenv(fr.ENV_VAR, str(fake_cmd))
    monkeypatch.setattr(fr.shutil, 'which', lambda name: None)
    monkeypatch.setattr(fr, '_DEFAULT_GUI_PATHS', [r'C:\nowhere\freecad.exe'])
    with pytest.raises(fr.FreeCADNotFound, match='FreeCAD GUI executable was not found'):
        fr.freecad_gui_path()


# ------------------------------------------------------------
# definition_text -- real geometry_version.freecad_version underneath
# ------------------------------------------------------------

def test_definition_text_is_valid_deterministic_json_for_a_real_kind():
    import json
    text1 = fr.definition_text('corner', {'b': 2.0, 'a': 1.0})
    text2 = fr.definition_text('corner', {'b': 2.0, 'a': 1.0})
    assert text1 == text2   # --resume depends on this byte-for-byte
    doc = json.loads(text1)
    assert doc['kind'] == 'corner'
    assert doc['variant'] == {}
    assert doc['parameters'] == {'a': 1.0, 'b': 2.0}
    assert 'version' in doc['geometry'] and 'modules' in doc['geometry']
    assert len(doc['geometry']['modules']) > 0


def test_definition_text_carries_the_given_variant_dict():
    import json
    text = fr.definition_text('corner', {'a': 1.0}, variant={'U': 1.0, 'FX': 1.0})
    doc = json.loads(text)
    assert doc['variant'] == {'U': 1.0, 'FX': 1.0}


def test_definition_text_differs_when_the_kind_differs_even_with_identical_parameters():
    """`kind` is inside the document specifically so two parts of the same parameter set do
    not compare equal under --resume."""
    a = fr.definition_text('corner', {'x': 1.0})
    b = fr.definition_text('bulkhead', {'x': 1.0})
    assert a != b


# ------------------------------------------------------------
# check_fcstd_length / PathTooLong (IP-FC-69)
# ------------------------------------------------------------

def test_check_fcstd_length_accepts_a_short_path():
    fr.check_fcstd_length(r'C:\short\path\part.FCStd')   # must not raise


def test_check_fcstd_length_raises_past_the_real_measured_limit():
    long_path = 'C:\\' + ('a' * (fr.FCSTD_MAX + 20)) + '\\part.FCStd'
    with pytest.raises(fr.PathTooLong, match='cannot save past'):
        fr.check_fcstd_length(long_path)


def test_check_fcstd_length_message_names_how_many_characters_too_many():
    long_path = 'C:\\' + ('a' * (fr.FCSTD_MAX + 20)) + '\\part.FCStd'
    with pytest.raises(fr.PathTooLong, match=r'\d+ too many'):
        fr.check_fcstd_length(long_path)


# ------------------------------------------------------------
# build_command
# ------------------------------------------------------------

def test_build_command_without_fcstd_has_no_fcstd_flag():
    cmd = fr.build_command('corner', 'params.json', 'out.stl')
    assert fr.freecadcmd_path() == cmd[0]
    assert cmd[1] == fr.BUILDER
    assert '--pass' in cmd
    assert '--kind=corner' in cmd
    assert '--params=params.json' in cmd
    assert '--out=out.stl' in cmd
    assert not any(a.startswith('--fcstd=') for a in cmd)


def test_build_command_with_a_short_fcstd_path_includes_the_flag():
    cmd = fr.build_command('corner', 'params.json', 'out.stl', fcstd_path='out.FCStd')
    assert '--fcstd=out.FCStd' in cmd
    # every value argument is preceded by its own --pass
    idx = cmd.index('--fcstd=out.FCStd')
    assert cmd[idx - 1] == '--pass'


def test_build_command_raises_when_the_fcstd_path_is_too_long():
    long_fcstd = 'C:\\' + ('a' * (fr.FCSTD_MAX + 20)) + '\\part.FCStd'
    with pytest.raises(fr.PathTooLong):
        fr.build_command('corner', 'params.json', 'out.stl', fcstd_path=long_fcstd)
