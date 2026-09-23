"""Shared fixtures for the pytest tier -- everything importable in the project venv.

See doc/guidelines/general.md#two-test-tiers-because-two-python-interpreters-are-involved:
this tier covers src/Fuselage/tools/. FreeCAD-dependent code under src/Fuselage/freecad/
cannot be reached from here and is tested separately with freecadcmd check_*.py scripts.
"""
import pytest


@pytest.fixture
def baseline_params() -> dict:
    """The OpenSCAD-path standard parameter set, in millimeters (see general.md's SI
    exemption for that path)."""
    import fuselage_variants as fv
    return fv.standard_values()
