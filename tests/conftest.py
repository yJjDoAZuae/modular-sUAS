"""Shared fixtures for the pytest tier -- everything importable in the project venv.

See doc/guidelines/general.md#two-test-tiers-because-two-python-interpreters-are-involved.
This tier covers src/Fuselage/tools/ directly, and FreeCAD geometry under src/Fuselage/freecad/
**across a process boundary** through the geometry bridge: `FreeCAD` and `Part` cannot be imported
here -- a CPython ABI version lock, not a property of the tools -- but they can be driven. The
`freecadcmd` check_*.py tier remains for whole-part builds whose output is a report a person reads.
"""
import os
import sys

import pytest

#: Windows' extended-length form of a UNC path, `\\?\UNC\server\share\...`.
_EXTENDED_UNC = '\\\\?\\UNC\\'

# **`uv run pytest` starts Python from an extended-length path, and NumPy cannot load from one.**
# The `pytest.exe` launcher in the venv resolves its own location canonically, so on this share the
# interpreter runs from under the extended prefix and every `sys.path` entry carries it. NumPy
# registers its DLL directory from its package path, and Windows refuses an extended path there:
# `DLL load failed while importing _multiarray_umath: The parameter is incorrect`, at collection,
# measured 2026-11-24 on `test_wall_measure_truth.py`. `uv run python -m pytest` was
# unaffected. Rewritten here, before any test module imports NumPy, to the plain UNC form, which
# is the same files; with it the same interpreter imported NumPy cleanly.
sys.path[:] = ['\\\\' + p[len(_EXTENDED_UNC):] if p.startswith(_EXTENDED_UNC) else p
               for p in sys.path]


@pytest.fixture
def baseline_params() -> dict:
    """The OpenSCAD-path standard parameter set, in millimeters (see general.md's SI
    exemption for that path)."""
    import fuselage_variants as fv
    return fv.standard_values()


# ------------------------------------------------------------------ the geometry bridge
#
# One session per pytest process, so a parallel run under xdist gets one FreeCAD worker per worker
# process with nothing shared. Started lazily: a run that touches no geometry pays nothing.


def _freecad_available():
    try:
        from geometry_bridge.api import freecadcmd_path
        return os.path.isfile(freecadcmd_path())
    except Exception:                                                    # noqa: BLE001
        return False


#: Marks a test that needs the real vendor. The loopback tier needs none, which is the point.
requires_freecad = pytest.mark.skipif(
    not _freecad_available(),
    reason='FreeCAD not found; the bridge tier needs it (the loopback tier does not)')


@pytest.fixture(scope='session')
def fc():
    """A long-lived FreeCAD session. Right for ordinary assertions.

    **Not** for a measurement that feeds a reproducibility claim: this worker has accumulated kernel
    state from every test before it, and a fresh build is bit-identical only away from a degenerate
    configuration. Use `fresh_fc` for those.
    """
    from geometry_bridge.api import freecad_session
    session = freecad_session()
    yield session
    session.close()


@pytest.fixture
def fresh_fc():
    """A FreeCAD session whose worker has built nothing yet.

    Required wherever process cleanliness is part of what is being measured. A test comparing two
    builds asks for two of these, not for one twice.
    """
    from geometry_bridge.api import freecad_session
    session = freecad_session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _reset_vendor_state(request):
    """Close any document and drop any handle the test left behind.

    FreeCAD keeps a process-global open-document list, so without this a document created in one
    test is still open in the next -- cross-test contamination the bridge owns rather than each test
    remembering. Inert unless the session fixture was actually used.
    """
    yield
    session = getattr(request.node, 'funcargs', {}).get('fc')
    if session is not None:
        try:
            session.reset()
        except Exception:                                                # noqa: BLE001
            pass


@pytest.fixture
def Part(fc):
    return fc.module('Part')


@pytest.fixture
def App(fc):
    return fc.module('FreeCAD')


@pytest.fixture
def ci(fc):
    """`cowl_interior`, whose private helpers have no named test today."""
    return fc.module('cowl_interior')


@pytest.fixture
def cci(fc):
    """`check_cowl_interior`, for `section_regions` and the ring-continuity classifier."""
    return fc.module('check_cowl_interior')
