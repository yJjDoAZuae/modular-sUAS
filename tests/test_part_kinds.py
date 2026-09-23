"""IP-TEST-11: part_kinds.py's own functions (`unbuilt_types`, `geometry_roots`) had no direct
assertions anywhere -- test_freecad_render.py (IP-TEST-6) only checks that `KINDS` exists, is
sorted, and is non-empty, as infrastructure for freecad_render.py's own tests. Like
sheet_naming.py and variants.py, this module deliberately carries no FreeCAD import (its own
docstring: "Nothing here may import FreeCAD, or anything that imports FreeCAD") specifically so
both `build_part.py` and `tools/freecad_render.py` can read it, which makes it fully testable
from this tier despite its location under src/Fuselage/freecad/.
"""
import sys
from pathlib import Path

_FREECAD_DIR = str(Path(__file__).resolve().parent.parent / 'src' / 'Fuselage' / 'freecad')
if _FREECAD_DIR not in sys.path:
    sys.path.insert(0, _FREECAD_DIR)

import part_kinds as pk  # noqa: E402


def test_unbuilt_types_is_empty_for_every_name_a_kind_actually_builds():
    for name in pk.BUILT_TYPES['bulkhead']:
        assert pk.unbuilt_types('bulkhead', [name]) == []


def test_unbuilt_types_names_a_type_the_backend_cannot_build():
    assert pk.unbuilt_types('bulkhead', ['not_a_real_type']) == ['not_a_real_type']


def test_unbuilt_types_mixes_built_and_unbuilt_correctly_and_sorts_the_result():
    result = pk.unbuilt_types('bulkhead', ['zz_unbuilt', 'end_bolt', 'aa_unbuilt'])
    assert result == ['aa_unbuilt', 'zz_unbuilt']


def test_unbuilt_types_returns_nothing_for_a_kind_with_no_type_axis():
    """A kind absent from BUILT_TYPES (e.g. `corner`) has no type restriction at all -- every
    variant of it is buildable, per the module's own docstring."""
    assert pk.unbuilt_types('corner', ['whatever_type_name']) == []


def test_built_types_bulkhead_lists_exactly_the_five_documented_types():
    assert pk.BUILT_TYPES['bulkhead'] == (
        'end_anchor', 'end_bolt', 'cowling_anchor', 'cowling_bolt', 'interconnect')


def test_geometry_roots_names_build_part_and_the_kind_own_module_for_every_kind():
    for kind, (module_name, _table) in pk.KINDS.items():
        assert pk.geometry_roots(kind) == ('build_part.py', module_name + '.py')


def test_kinds_maps_every_kind_to_a_two_element_module_table_pair():
    for kind, value in pk.KINDS.items():
        assert isinstance(value, tuple) and len(value) == 2
        module_name, table_name = value
        assert isinstance(module_name, str) and module_name
        assert isinstance(table_name, str) and table_name.isupper()


# Whether each kind's table_name is a real attribute of parameters.py is not checked here --
# parameters.py imports corner_common, which imports FreeCAD, so it cannot be reached from this
# tier. build_part.py's own `KINDS = {kind: (module, getattr(parameters, table)) ...}` resolves
# every one of these names at import time, so check_build_part.py (freecadcmd tier) already
# proves this for real every time it runs: a wrong table name would raise AttributeError before
# any of that check's own assertions ran.
