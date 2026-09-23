"""IP-TEST-6 (doc/implementation/test_coverage.md): unit tests for export_parameters.py.

`check_agreement`/`scad_module_parameters`/`check_names`/`resolve` are tested against real
data throughout -- real `.scad` source for the module-parameter reader, and real resolved
`derived_parameters()` output for the rest -- because this module's whole purpose is
cross-checking real data against real data (its own docstring: "The names are checked, not
assumed"), so a synthetic stand-in would test nothing this module actually does. `main()` is
covered end to end, including writing a real JSON file to `tmp_path`.
"""
import json

import export_parameters as ep
import pytest

# ------------------------------------------------------------
# check_agreement
# ------------------------------------------------------------

def test_check_agreement_passes_when_every_shared_name_matches():
    ep.check_agreement({'a': 1.0, 'b': 2.0}, {'a': 1.0, 'b': 2.0, 'c': 3.0})


def test_check_agreement_raises_on_a_real_disagreement():
    with pytest.raises(RuntimeError, match='the two halves of the joint disagree'):
        ep.check_agreement({'corner_radius': 5.0}, {'corner_radius': 6.0})


def test_check_agreement_exempts_greeble_tolerance_even_when_it_differs():
    ep.check_agreement({'greeble_tolerance': 0.0, 'a': 1.0}, {'greeble_tolerance': 0.3, 'a': 1.0})


def test_check_agreement_exempts_the_panel_joint_only_for_a_cowling_variant():
    bulkhead = {'panel_thickness': 0.0, 'panel_offset': 0.0}
    corner = {'panel_thickness': 6.35, 'panel_offset': 2.5}
    ep.check_agreement(bulkhead, corner, is_cowling=True)   # must not raise
    with pytest.raises(RuntimeError):
        ep.check_agreement(bulkhead, corner, is_cowling=False)


# ------------------------------------------------------------
# scad_module_parameters -- real .scad source
# ------------------------------------------------------------

def test_scad_module_parameters_reads_real_bulkhead_module_parameters():
    names = ep.scad_module_parameters(
        'fuselage_bulkhead_geometry.scad', 'bulkhead_section_full')
    assert 'bulkhead_thickness' in names
    assert 'corner_radius' in names


def test_scad_module_parameters_reads_real_corner_module_parameters():
    names = ep.scad_module_parameters('fuselage_corner_geometry.scad', 'fuselage_corner')
    assert 'corner_radius' in names


def test_scad_module_parameters_raises_for_an_unknown_module():
    with pytest.raises(RuntimeError, match='no module'):
        ep.scad_module_parameters('fuselage_bulkhead_geometry.scad', 'no_such_module')


# ------------------------------------------------------------
# resolve -- real family_combinations / derived_parameters
# ------------------------------------------------------------

def test_resolve_returns_none_tuple_for_a_nonexistent_combination():
    result = ep.resolve('bulkhead', 999.0, 'end_bolt', '3/16in')
    assert result == (None, None, None, None)


def test_resolve_finds_a_real_valid_bulkhead_combination():
    p, dp, dp_corner, valid = ep.resolve('bulkhead', 1.0, 'end_bolt', '3/16in')
    assert p is not None
    assert valid is True
    assert dp.bulkhead.U == 1.0
    assert dp_corner is not None   # resolved alongside, even though this is a frame bulkhead


def test_resolve_finds_a_real_invalid_bulkhead_combination():
    """U=1.5, end_bolt, 1mm is confirmed invalid against the real corpus."""
    p, dp, dp_corner, valid = ep.resolve('bulkhead', 1.5, 'end_bolt', '1mm')
    assert p is not None
    assert valid is False


def test_resolve_finds_a_real_valid_boom_bulkhead_combination():
    p, dp, dp_corner, valid = ep.resolve('boom_bulkhead', 0.5, 'offset_single', '0mm')
    assert p is not None
    assert valid is True
    assert dp_corner is not None   # resolved but not exported, per the module's own docstring


# ------------------------------------------------------------
# check_names -- real self-check, plus both injected-mismatch failure branches
# ------------------------------------------------------------

def test_check_names_passes_for_the_real_bulkhead_mapping():
    _p, dp, dp_corner, _valid = ep.resolve('bulkhead', 1.0, 'end_bolt', '3/16in')
    ep.check_names('bulkhead', dp, dp_corner)   # must not raise


def test_check_names_passes_for_the_real_boom_bulkhead_mapping():
    _p, dp, dp_corner, _valid = ep.resolve('boom_bulkhead', 0.5, 'offset_single', '0mm')
    ep.check_names('boom_bulkhead', dp, dp_corner)   # must not raise


def test_check_names_catches_a_mapping_that_carries_an_unknown_parameter(monkeypatch):
    _p, dp, dp_corner, _valid = ep.resolve('bulkhead', 1.0, 'end_bolt', '3/16in')
    real = ep.bulkhead_parameters

    def broken(dp_):
        return dict(real(dp_), not_a_real_scad_parameter=1.0)

    monkeypatch.setattr(ep, 'bulkhead_parameters', broken)
    with pytest.raises(RuntimeError, match='not parameters of'):
        ep.check_names('bulkhead', dp, dp_corner)


def test_check_names_catches_a_mapping_missing_a_parameter_the_module_needs(monkeypatch):
    _p, dp, dp_corner, _valid = ep.resolve('bulkhead', 1.0, 'end_bolt', '3/16in')
    real = ep.bulkhead_parameters

    def broken(dp_):
        d = dict(real(dp_))
        d.pop('bulkhead_thickness', None)
        return d

    monkeypatch.setattr(ep, 'bulkhead_parameters', broken)
    with pytest.raises(RuntimeError, match='takes parameters this export does not carry'):
        ep.check_names('bulkhead', dp, dp_corner)


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

def test_main_with_too_few_arguments_prints_usage(capsys):
    result = ep.main(['export_parameters.py'])
    assert result == 0
    assert 'usage:' in capsys.readouterr().out


def test_main_reports_an_unknown_bulkhead_type(capsys):
    result = ep.main(['1.0', 'no_such_type', '3/16in'])
    assert result == 1
    assert 'no bulkhead type named' in capsys.readouterr().out


def test_main_reports_no_such_combination(capsys):
    result = ep.main(['999.0', 'end_bolt', '3/16in'])
    assert result == 1
    assert 'no such combination' in capsys.readouterr().out


def test_main_prints_json_for_a_valid_bulkhead_variant_to_stdout(capsys):
    result = ep.main(['1.0', 'end_bolt', '3/16in'])
    assert result == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc['family'] == 'bulkhead'
    assert doc['valid'] is True
    assert 'parameters' in doc and 'corner_parameters' in doc
    assert doc['variant']['bulkhead_type_name'] == 'end_bolt'


def test_main_writes_json_to_the_given_output_file(tmp_path, capsys):
    out_path = tmp_path / 'variant.json'
    result = ep.main(['1.0', 'end_bolt', '3/16in', str(out_path)])
    assert result == 0
    assert out_path.is_file()
    doc = json.loads(out_path.read_text(encoding='utf-8'))
    assert doc['family'] == 'bulkhead'
    assert 'wrote' in capsys.readouterr().out


def test_main_exports_boom_parameters_for_a_boom_bulkhead_variant(capsys):
    result = ep.main(['0.5', 'offset_single', '0mm'])
    assert result == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc['family'] == 'boom_bulkhead'
    assert 'boom_parameters' in doc
    assert 'parameters' not in doc


def test_main_reports_invalid_combination_on_stderr_and_returns_one(capsys):
    result = ep.main(['1.5', 'end_bolt', '1mm'])
    assert result == 1
    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    assert doc['valid'] is False
    assert 'sweep would not generate' in captured.err
