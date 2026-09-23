"""IP-TEST-4 (doc/implementation/test_coverage.md): tests for branching_dimensions.py.

branching_dimensions.py is IP-FC-99's real, reusable analysis tool -- distinct from the
one-off SVG-evidence generators alongside it in src/Fuselage/tools/ (draw_bolt_flange_
fillet.py, draw_dimension_alternatives.py, draw_corner_joint.py, draw_flat_offset.py,
draw_fillet_scope.py, draw_sheet_alternatives.py, draw_register_rows.py -- each answers one
specific, mostly-already-resolved open question and is not depended on by anything else, so
IP-TEST-4 does not chase deep coverage there; see this plan's Notes). This module, and
draw_set.py/draw_variant_set.py alongside it, remain live tools other work depends on, so
they get real coverage.

Covers `axis_values`, `_tally`, `_verdict` (pure), the `_watching` call-interception
mechanism directly (the trickiest piece: frame introspection, win/tie recording), and
`sweep()`/`uninstrumented()` against the real corpus -- including that `sweep()` restores
`check_derivation.max`/`.min` to the plain builtins even when a relation raises partway
through, which is the one guarantee the whole monkeypatch-based instrument depends on for
safety (a coverage run that ever left `check_derivation.RELATIONS` running under a broken
watcher would corrupt every result computed after it, silently).

`factor_report`/`geometry_layer` are not covered here: both shell out to `freecadcmd` as a
real subprocess, which is the same class of thing IP-TEST-2 already deferred for
`fuselage_variants.py`'s render orchestration.

Adoption-phase retrofit (general.md's TDD section).
"""
import branching_dimensions as bd
import check_derivation as cd
import pytest


@pytest.fixture(autouse=True)
def clear_instrumentation_state():
    """SITES/TIES/PER_VARIANT/AXIS_VALUES are process-global, so a test that watches a call
    would otherwise see totals left over from a previous test or a previous real sweep()."""
    bd.SITES.clear()
    bd.TIES.clear()
    bd.PER_VARIANT.clear()
    bd.AXIS_VALUES.clear()
    yield
    bd.SITES.clear()
    bd.TIES.clear()
    bd.PER_VARIANT.clear()
    bd.AXIS_VALUES.clear()


# ------------------------------------------------------------
# axis_values / _tally -- pure formatting helpers
# ------------------------------------------------------------

def test_axis_values_matches_drawing_families_resolve_shape():
    import drawing_families as df
    row = {'U': '1.0', 'FX': '2.0', 'panel_name': '1mm'}
    corner_axes = df.SWEEPS['corner']['axes']
    assert bd.axis_values('corner', row) == {
        label: (float(row[column]) if label in ('U', 'FX') else str(row[column]))
        for label, column in corner_axes
    }


def test_tally_formats_argument_win_counts_in_index_order():
    assert bd._tally({1: 3, 0: 5}) == 'arg 0 wins 5  arg 1 wins 3'


# ------------------------------------------------------------
# _verdict -- pure, all six branches
# ------------------------------------------------------------

def test_verdict_not_shown_short_circuits_before_anything_else():
    assert bd._verdict(('U',), ('U',), False).startswith('not shown')


def test_verdict_branch_not_a_function_of_the_axes():
    assert bd._verdict((), None, True).startswith('NOT A FUNCTION')


def test_verdict_one_branch_governs_the_whole_family():
    assert bd._verdict((), (), True).startswith('one branch governs')


def test_verdict_shown_but_not_tabled():
    assert bd._verdict(None, ('U',), True).startswith('shown, but not tabled')


def test_verdict_rides_beside_the_value_when_branch_axes_are_a_subset():
    assert bd._verdict(('U', 'panel'), ('U',), True) == 'rides beside the value'


def test_verdict_needs_its_own_block_when_branch_follows_more_axes_than_the_value():
    assert bd._verdict(('U',), ('U', 'panel'), True).startswith('follows MORE axes')


# ------------------------------------------------------------
# _watching -- the call-interception mechanism itself
# ------------------------------------------------------------

def test_watching_records_a_clean_win_by_argument_index():
    watched_max = bd._watching('max', max)
    bd._FIELD[0] = ('corner', 'some.field')
    bd._AT[0] = 0
    result = watched_max(3, 7)
    assert result == 7
    [key] = bd.SITES.keys()
    assert key[0] == ('corner', 'some.field') and key[3] == 'max'
    assert bd.SITES[key] == {1: 1}          # argument index 1 (the 7) won once
    assert bd.PER_VARIANT[key] == {0: 1.0}
    assert bd.TIES == {}


def test_watching_records_a_tie_separately_from_a_win():
    watched_max = bd._watching('max', max)
    bd._FIELD[0] = ('corner', 'some.field')
    bd._AT[0] = 2
    watched_max(5, 5)
    [key] = bd.TIES.keys()
    assert bd.TIES[key] == 1
    assert bd.PER_VARIANT[key] == {2: bd.TIE}
    assert bd.SITES == {}                   # a tie is not counted as either argument winning


def test_watching_ignores_the_single_iterable_fold_form():
    """max([1, 2, 3]) is a fold over a collection, not a choice between named alternatives --
    the module's own docstring says there is nothing to report for it."""
    watched_max = bd._watching('max', max)
    bd._FIELD[0] = ('corner', 'some.field')
    assert watched_max([1, 2, 3]) == 3
    assert bd.SITES == {}
    assert bd.TIES == {}


def test_watching_ignores_a_call_with_keyword_arguments():
    watched_max = bd._watching('max', max)
    bd._FIELD[0] = ('corner', 'some.field')
    assert watched_max(1, 2, key=abs) == 2
    assert bd.SITES == {}


def test_watching_accumulates_counts_across_repeated_calls_at_the_same_site():
    def call_site(a, b):
        return watched_max(a, b)

    watched_max = bd._watching('max', max)
    bd._FIELD[0] = ('corner', 'some.field')
    for i, (a, b) in enumerate([(1, 2), (1, 2), (2, 1)]):
        bd._AT[0] = i
        call_site(a, b)
    [key] = bd.SITES.keys()
    assert bd.SITES[key] == {1: 2, 0: 1}


# ------------------------------------------------------------
# sweep() -- the real, full-corpus instrumented run
# ------------------------------------------------------------

def test_sweep_counts_match_the_real_corpus_and_populates_sites():
    counted = bd.sweep()
    assert counted == {'corner': 264, 'bulkhead': 148, 'boom_bulkhead': 132,
                       'nose': 8, 'tail': 8}
    assert bd.SITES  # at least one max/min call site was observed


def test_sweep_restores_max_and_min_to_the_plain_builtins_after_a_clean_run():
    bd.sweep()
    assert cd.max is max
    assert cd.min is min


def test_sweep_restores_max_and_min_even_when_a_relation_raises(monkeypatch):
    """The one safety guarantee the whole instrument depends on: if a relation blows up
    mid-sweep, check_derivation must not be left running under the watcher -- every later
    caller of RELATIONS in the same process would otherwise get silently-instrumented
    results, or a stale reference to this test's now-out-of-scope SITES dict."""
    def broken_derive(g, d):
        raise ValueError('synthetic failure to prove the finally block runs')

    original_relations = cd.RELATIONS
    monkeypatch.setattr(cd, 'RELATIONS',
                        (cd.Relation('bulkhead.width', 'DES-1', 'x', broken_derive),))
    try:
        with pytest.raises(ValueError, match='synthetic failure'):
            bd.sweep()
    finally:
        monkeypatch.setattr(cd, 'RELATIONS', original_relations)

    assert cd.max is max
    assert cd.min is min


# ------------------------------------------------------------
# uninstrumented() -- relations that branch on a conditional max/min cannot see
# ------------------------------------------------------------

def test_uninstrumented_finds_panel_offset_as_the_des9_evidence_dimension():
    """panel.offset -- corner.flat_offset's DES-9 evidence -- is the dimension this whole
    module exists to characterize: both a max/min call AND a plain conditional, so it is
    reported as 'conditional as well as a max/min' rather than silently only half-seen."""
    found = dict(bd.uninstrumented())
    assert found['panel.offset'] == 'conditional as well as a max/min'


def test_uninstrumented_labels_a_conditional_only_relation_distinctly():
    found = dict(bd.uninstrumented())
    assert found['bolt.radius'] == 'conditional only -- nothing above sees this'
