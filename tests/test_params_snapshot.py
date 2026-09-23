"""IP-TEST-5 (doc/implementation/test_coverage.md): unit tests for params_snapshot.py.

`encode`/`_flatten`/`compare` are pure and get exhaustive synthetic coverage. `capture` is
exercised against the real sweep machinery (see test_scad_snapshot.py for the rationale),
restricted to one fast sweep kind to bound cost, because the thing worth proving is that its
render-function monkeypatches genuinely intercept the derived parameters and restore
themselves afterward. `main()` (argparse/file I/O wiring) is not covered, consistent with
the other CLI-entry-point modules in this plan.
"""
import dataclasses
from enum import Enum, auto

import fuselage_variants as fv
import params_snapshot as ps
import pytest

# ------------------------------------------------------------
# encode
# ------------------------------------------------------------

class _Color(Enum):
    RED = auto()
    BLUE = auto()


@dataclasses.dataclass
class _Inner:
    b_field: int
    a_field: str


@dataclasses.dataclass
class _Outer:
    first: _Inner
    second: float
    color: _Color


def test_encode_passes_through_plain_scalars():
    assert ps.encode(3) == 3
    assert ps.encode('x') == 'x'
    assert ps.encode(True) is True
    assert ps.encode(None) is None


def test_encode_renders_a_float_as_its_repr_string():
    assert ps.encode(0.1) == repr(0.1)


def test_encode_renders_an_enum_as_type_dot_member():
    assert ps.encode(_Color.RED) == '_Color.RED'


def test_encode_renders_a_list_and_tuple_element_wise():
    assert ps.encode([1, 0.5, _Color.BLUE]) == [1, repr(0.5), '_Color.BLUE']
    assert ps.encode((1, 2)) == [1, 2]


def test_encode_stringifies_dict_keys_and_recurses_into_values():
    assert ps.encode({1: 0.5, 'k': _Color.RED}) == {'1': repr(0.5), 'k': '_Color.RED'}


def test_encode_renders_a_dataclass_as_a_dict_in_field_declaration_order():
    inner = _Inner(b_field=2, a_field='y')
    encoded = ps.encode(inner)
    assert encoded == {'b_field': 2, 'a_field': 'y'}
    assert list(encoded) == ['b_field', 'a_field']   # declaration order, not alphabetical


def test_encode_recurses_through_a_nested_dataclass_tree():
    outer = _Outer(first=_Inner(1, 'z'), second=1.5, color=_Color.BLUE)
    assert ps.encode(outer) == {
        'first': {'b_field': 1, 'a_field': 'z'},
        'second': repr(1.5),
        'color': '_Color.BLUE',
    }


# ------------------------------------------------------------
# _flatten
# ------------------------------------------------------------

def test_flatten_leaves_a_flat_dict_keys_unprefixed():
    assert ps._flatten('', {'a': 1, 'b': 2}, {}) == {'a': 1, 'b': 2}


def test_flatten_builds_dotted_paths_for_nested_dicts():
    tree = {'a': {'x': 1, 'y': 2}, 'b': 3}
    assert ps._flatten('', tree, {}) == {'a.x': 1, 'a.y': 2, 'b': 3}


def test_flatten_handles_multiple_levels_of_nesting():
    tree = {'a': {'b': {'c': 'deep'}}}
    assert ps._flatten('', tree, {}) == {'a.b.c': 'deep'}


def test_flatten_of_a_non_dict_top_level_value_keys_it_under_the_given_prefix():
    assert ps._flatten('', 'scalar', {}) == {'': 'scalar'}
    assert ps._flatten('root', 'scalar', {}) == {'root': 'scalar'}


def test_flatten_of_a_real_encoded_dataclass_tree_names_every_field():
    encoded = ps.encode(_Outer(first=_Inner(1, 'z'), second=1.5, color=_Color.BLUE))
    flat = ps._flatten('', encoded, {})
    assert flat == {
        'first.b_field': 1, 'first.a_field': 'z',
        'second': repr(1.5), 'color': '_Color.BLUE',
    }


# ------------------------------------------------------------
# compare
# ------------------------------------------------------------

def test_compare_returns_zero_for_identical_snapshots(capsys):
    before = {'a': {'x': 1}}
    after = {'a': {'x': 1}}
    assert ps.compare(before, after) == 0
    assert capsys.readouterr().out == ''


def test_compare_reports_a_missing_and_a_new_part(capsys):
    before = {'a': {'x': 1}, 'gone': {'x': 1}}
    after = {'a': {'x': 1}, 'brand_new': {'x': 1}}
    problems = ps.compare(before, after)
    assert problems == 2
    out = capsys.readouterr().out
    assert 'MISSING NOW   gone' in out
    assert 'NEW           brand_new' in out


def test_compare_reports_a_changed_field_with_its_dotted_path(capsys):
    before = {'a': {'x': {'y': 1}}}
    after = {'a': {'x': {'y': 2}}}
    assert ps.compare(before, after) == 1
    out = capsys.readouterr().out
    assert 'CHANGED       a' in out
    assert 'x.y' in out and '1 -> 2' in out


def test_compare_treats_none_as_an_empty_tree_without_crashing(capsys):
    """capture() records None for a part whose render function was never reached (e.g. a
    combination the validity check rejects); compare must not crash on that."""
    before = {'a': None}
    after = {'a': {'x': 1}}
    assert ps.compare(before, after) == 1
    out = capsys.readouterr().out
    assert 'x' in out and 'None -> 1' in out


def test_compare_truncates_field_diffs_after_six_and_counts_the_rest(capsys):
    before = {'a': {f'f{i}': 0 for i in range(8)}}
    after = {'a': {f'f{i}': 1 for i in range(8)}}
    assert ps.compare(before, after) == 1
    out = capsys.readouterr().out
    assert out.count('0 -> 1') == 6
    assert '... 2 more field(s)' in out


def test_compare_truncates_changed_parts_after_five_and_counts_the_rest(capsys):
    before = {f'p{i}': {'x': 0} for i in range(7)}
    after = {f'p{i}': {'x': 1} for i in range(7)}
    problems = ps.compare(before, after)
    assert problems == 7
    out = capsys.readouterr().out
    assert out.count('CHANGED') == 5
    assert '... 2 more changed part(s)' in out


def test_compare_counts_every_missing_and_new_part_even_beyond_the_ten_printed(capsys):
    before = {f'gone{i}': {} for i in range(12)}
    after = {f'brand_new{i}': {} for i in range(12)}
    problems = ps.compare(before, after)
    assert problems == 24
    out = capsys.readouterr().out
    assert out.count('MISSING NOW') == 10
    assert out.count('NEW') == 10


# ------------------------------------------------------------
# capture -- against the real sweep machinery, restricted to one fast sweep kind
# ------------------------------------------------------------

_ONE_SWEEP = (ps.SWEEPS[0],)   # ('corner', 'run_corner_parametric_sweep', (...))
_RENDER_NAMES = ('corner_render', 'bulkhead_render', 'boom_bulkhead_render',
                 'nose_render', 'tail_render')


def test_capture_records_real_encoded_parameters_and_restores_every_patch(monkeypatch):
    monkeypatch.setattr(ps, 'SWEEPS', _ONE_SWEEP)
    original_render = fv.solid_render
    original_funcs = {name: getattr(fv, name) for name in _RENDER_NAMES}

    captured = ps.capture(quiet=True)

    assert len(captured) > 0
    assert fv.solid_render is original_render
    assert all(getattr(fv, name) is original_funcs[name] for name in _RENDER_NAMES)

    sample = next(iter(captured.values()))
    assert isinstance(sample, dict)
    assert 'corner' in sample   # a Parameters tree has a 'corner' field


def test_capture_restores_every_patch_even_when_a_sweep_raises(monkeypatch):
    monkeypatch.setattr(ps, 'SWEEPS', _ONE_SWEEP)
    original_render = fv.solid_render
    original_funcs = {name: getattr(fv, name) for name in _RENDER_NAMES}

    def boom(*_args, **_kwargs):
        raise RuntimeError('synthetic sweep failure')

    monkeypatch.setattr(fv, _ONE_SWEEP[0][1], boom)
    with pytest.raises(RuntimeError):
        ps.capture(quiet=True)

    assert fv.solid_render is original_render
    assert all(getattr(fv, name) is original_funcs[name] for name in _RENDER_NAMES)


def test_capture_output_is_json_serializable(monkeypatch):
    import json
    monkeypatch.setattr(ps, 'SWEEPS', _ONE_SWEEP)
    captured = ps.capture(quiet=True)
    json.dumps(captured)   # must not raise


def test_capture_and_compare_reproduce_ip_fc_2s_perturbed_constant_claim(monkeypatch):
    """IP-FC-2 (freecad_migration.md) claims this pair was self-tested by perturbing a
    single constant and observing that compare() named exactly the corner parts and exactly
    the 'greeble.tolerance' field -- a one-time claim with no committed regression until now.
    `GREEBLE_TOLERANCE_CORNER_MM` is assigned to every corner part's `c.greeble.tolerance` in
    `derived_parameters()`'s corner branch (a bulkhead leaves it at its zero default), so
    perturbing it should flip exactly the whole corner sweep and nothing else."""
    monkeypatch.setattr(ps, 'SWEEPS', _ONE_SWEEP)
    before = ps.capture(quiet=True)

    monkeypatch.setattr(fv, 'GREEBLE_TOLERANCE_CORNER_MM', fv.GREEBLE_TOLERANCE_CORNER_MM + 1.0)
    after = ps.capture(quiet=True)

    assert set(before) == set(after)
    problems = ps.compare(before, after)
    assert problems == len(before)   # every corner part changed, none missing/new

    for name, tree in before.items():
        diffs = {k: v for k, v in ps._flatten('', tree, {}).items()
                 if ps._flatten('', after[name], {}).get(k) != v}
        assert set(diffs) == {'greeble.tolerance'}, (name, diffs)
