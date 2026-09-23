"""IP-TEST-1: proves the pytest harness itself works before anything is built on top of it --
that `pythonpath = ["src/Fuselage/tools"]` in pyproject.toml actually makes the generator
modules importable from tests/, and that the one parameter function every other tools/ test
will depend on (fuselage_variants.standard_values()) returns a self-consistent result.

This is harness scaffolding, not fuselage_variants.py's test coverage -- see
doc/implementation/test_coverage.md, IP-TEST-2 for the rest of that module's 108 functions.
"""
import fuselage_variants as fv


def test_tools_modules_are_importable() -> None:
    assert hasattr(fv, 'standard_values')


def test_standard_values_matches_its_own_module_constants(baseline_params: dict) -> None:
    assert baseline_params['unit_width'] == fv.UNIT_WIDTH_MM
    assert baseline_params['unit_length'] == fv.UNIT_LENGTH_MM
    assert baseline_params['corner_radius'] == fv.CORNER_RADIUS_MM
    assert baseline_params['longeron_radius'] == fv.LONGERON_RADIUS_MM
    assert baseline_params['bolt_offset'] == fv.BOLT_OFFSET_MM


def test_standard_values_are_positive_millimeter_dimensions(baseline_params: dict) -> None:
    for key in ('unit_width', 'unit_length', 'corner_radius', 'longeron_radius', 'bolt_offset'):
        assert baseline_params[key] > 0, key
