"""IP-TEST-3 (doc/implementation/test_coverage.md): tests for check_derivation.py.

IP-FC-87's derivation-vs-implementation check already has its own thorough validation --
`check_traceability()` and `check(kind)` re-derive every relation against the real
`variant_param/` corpus and return structured complaints -- what was missing is that
nothing ran it as part of the committed test suite; `python check_derivation.py` had to be
invoked by hand. `test_check_derivation_agrees_with_the_built_sweep_for_every_kind` below
is that wiring: it calls the module's own real check across the full corpus for every sweep
kind and asserts zero complaints, the same assertion `main()` prints as "ok". The smaller
pure helpers (`_floored`, `_extrusions`, `agrees`, `check_coverage`, `derive_all`, `label`)
get direct unit tests on top, since those are the pieces most likely to be touched in
isolation by a future edit.

Adoption-phase retrofit (general.md's TDD section).
"""

import check_derivation as cd
import pytest

# ------------------------------------------------------------
# _floored / _extrusions -- the two shared derivation helpers
# ------------------------------------------------------------

def test_floored_scales_above_1u_and_floors_below_it():
    assert cd._floored(2.0, 4.0) == pytest.approx(8.0)
    assert cd._floored(2.0, 0.5) == pytest.approx(2.0)   # floored at the 1U coefficient
    assert cd._floored(2.0, 1.0) == pytest.approx(2.0)


def test_extrusions_rounds_up_to_a_whole_extrusion_and_floors_at_1u():
    # count=3, U=1.4, w=0.6 -> ceil(3*1.4)=5 extrusions -> 5*0.6=3.0, above the 1U floor 1.8
    assert cd._extrusions(3, 1.4, 0.6) == pytest.approx(3.0)
    # Below 1U the wall must not thin past its 1U value.
    assert cd._extrusions(3, 0.5, 0.6) == pytest.approx(3 * 0.6)


# ------------------------------------------------------------
# agrees -- the derived-vs-built comparison, including the None/None case
# ------------------------------------------------------------

def test_agrees_within_relative_tolerance_of_the_built_value():
    assert cd.agrees(10.0, 10.0 + cd.TOL / 2) is True


def test_agrees_false_outside_tolerance():
    assert cd.agrees(10.0, 10.1) is False


def test_agrees_treats_none_as_equal_only_to_none():
    assert cd.agrees(None, None) is True
    assert cd.agrees(None, 0.0) is False
    assert cd.agrees(0.0, None) is False


# ------------------------------------------------------------
# check_coverage -- every numeric field must be a declared given or a derived relation
# ------------------------------------------------------------

def test_check_coverage_flags_an_unclassified_numeric_field():
    flat = dict(cd.GIVENS)  # names, not values -- only the keys matter below
    flat = {name: 1.0 for name in cd.GIVENS}
    flat.update({r.field: 1.0 for r in cd.RELATIONS})
    flat['a_brand_new_field_nobody_classified'] = 1.0

    unclassified = cd.check_coverage(flat)

    assert unclassified == ['a_brand_new_field_nobody_classified']


def test_check_coverage_ignores_non_numeric_and_boolean_fields():
    flat = {name: 1.0 for name in cd.GIVENS}
    flat.update({r.field: 1.0 for r in cd.RELATIONS})
    flat['some_flag'] = True
    flat['some_label'] = 'end_bolt'

    assert cd.check_coverage(flat) == []


def test_check_coverage_is_clean_for_every_given_and_relation_together():
    """Every GIVENS name and every RELATIONS field must itself be coverable -- this is what
    check() actually asserts per real sweep, isolated here from needing a real dp."""
    flat = {name: 1.0 for name in cd.GIVENS}
    flat.update({r.field: 1.0 for r in cd.RELATIONS})
    assert cd.check_coverage(flat) == []


# ------------------------------------------------------------
# derive_all -- relations run in order, each seeing only givens and what came before
# ------------------------------------------------------------

def test_derive_all_runs_relations_in_order_with_access_to_prior_results():
    relations = (
        cd.Relation('a', 'DES-1', 'base value', lambda g, d: g['base']),
        cd.Relation('b', 'DES-1', 'doubles a', lambda g, d: d['a'] * 2),
    )
    d = cd.derive_all({'base': 3}, relations)
    assert d == {'a': 3, 'b': 6}


def test_derive_all_on_the_real_relations_table_does_not_raise_for_a_full_given_set():
    """A structural smoke test independent of check(): every real Relation's lambda must be
    satisfiable from a plausible givens dict without a KeyError, which would mean a relation
    reads a name givens() never supplies."""
    const = cd.constants()
    g = dict(const, U=1.0, FX=1.0, w=const['extrusion_width'], h=const['layer_height'],
            is_bulkhead=True, panel_thickness=1.0, bolt_diameter=3.0,
            is_end=True, is_interconnect=False, is_cowling=False, is_boom=False,
            is_anchor=False, boom_diameter=0.0, y_position=0.0, z_position=0.0)
    d = cd.derive_all(g, cd.RELATIONS)
    assert set(d) == {r.field for r in cd.RELATIONS}


# ------------------------------------------------------------
# constants() -- reads the real design_constants.json directly, not through fv's globals
# ------------------------------------------------------------

def test_constants_reads_every_group_and_matches_fuselage_variants(tmp_path):
    import fuselage_variants as fv
    const = cd.constants()
    assert const['extrusion_width'] == fv.EXTRUSION_WIDTH_MM
    assert const['unit_width'] == fv.UNIT_WIDTH_MM
    assert const['corner_radius'] == fv.CORNER_RADIUS_MM


# ------------------------------------------------------------
# label -- the human-readable variant description used in every complaint
# ------------------------------------------------------------

def test_label_includes_fx_only_when_the_row_carries_it():
    with_fx = cd.label('corner', {'FX': 2.0}, 1.0, 2.0)
    without_fx = cd.label('bulkhead', {}, 1.0, 1.0)
    assert 'FX=2' in with_fx
    assert 'FX' not in without_fx


def test_label_includes_panel_and_type_names_when_present():
    text = cd.label('bulkhead', {'panel_name': '1mm', 'bulkhead_type_name': 'end_bolt'},
                    1.0, 1.0)
    assert '1mm' in text
    assert 'end_bolt' in text


# ------------------------------------------------------------
# check_traceability -- every relation names a real design requirement
# ------------------------------------------------------------

def test_check_traceability_has_no_broken_citations():
    broken, _notes = cd.check_traceability()
    assert broken == []


# ------------------------------------------------------------
# check(kind) -- the real, full-corpus check, wired into the test suite for the first time.
# This is check_derivation.py's own validation, run here instead of only by hand.
# ------------------------------------------------------------

@pytest.mark.parametrize('kind', ['corner', 'bulkhead', 'boom_bulkhead', 'nose', 'tail'])
def test_check_agrees_with_the_built_sweep_for_every_kind(kind):
    count, complaints = cd.check(kind)
    assert count > 0
    assert complaints == []
