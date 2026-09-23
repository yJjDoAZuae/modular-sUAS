"""IP-TEST-3 (doc/implementation/test_coverage.md): tests for drawing_families.py.

Covers the pure table/topology logic (`flatten`, `_identifiers`, `written`, `sheet_rows`,
`_sort_key`, `minimal_axes`, `factor`, `topology_of`) with a mix of synthetic fixtures
(where the function is deterministic given plain data) and real corpus data (where the
claim being tested is specifically that the real register/sweep agree with this module's
own reading of them). `check_register()` and `check_topology_fields()` are, like
`check_derivation.check()` and `requirements.check_register()`, already comprehensive
self-checks against the real data -- wired into the suite here for the same reason: nothing
previously ran them except a person invoking `python drawing_families.py` by hand.

Not covered in this pass: `block_columns`, `sheet_blocks`, and the rest of the sheet-layout
machinery past `factor()` -- that is presentation logic (how a table's columns are laid out
on the page) rather than the correctness logic (which axes a field actually follows, which
family a variant belongs to) this pass focuses on, and is a reasonable place to stop for now
rather than a gap being glossed over.

Adoption-phase retrofit (general.md's TDD section).
"""

import drawing_families as df
import fuselage_variants as fv
import pytest


def _user_parameters(**overrides):
    params = dict(
        is_end=True, is_interconnect=False, is_cowling=False, is_boom=False,
        is_anchor=False, bulkhead_type_name='end_bolt', bulkhead_thickness=4.0,
        panel_is_metric=True, panel_thickness_mm=1.0, panel_name='1mm',
        bulkhead_bolt_diameter=3.0,
    )
    params.update(overrides)
    return params


# ------------------------------------------------------------
# flatten -- a dataclass tree as flat dotted names
# ------------------------------------------------------------

def test_flatten_walks_nested_dataclasses_into_dotted_names():
    dp = fv.derived_parameters(1.0, 1.0, _user_parameters(), fv.null_printer_settings(),
                               is_bulkhead=True)
    flat = df.flatten(dp)
    assert flat['bulkhead.U'] == dp.bulkhead.U
    assert flat['corner.radius'] == dp.corner.radius
    assert flat['printer.extrusion_width'] == dp.printer.extrusion_width


def test_flatten_a_leaf_value_with_no_prefix_returns_it_under_the_empty_key():
    assert df.flatten(5.0) == {'': 5.0}


# ------------------------------------------------------------
# _identifiers -- parameter names out of backtick-quoted spans, with alias substitution
# ------------------------------------------------------------

def test_identifiers_reads_only_backtick_quoted_names():
    cell = 'the `corner_radius` minus `panel_thickness`, in plain English words too'
    assert df._identifiers(cell, {}) == {'corner_radius', 'panel_thickness'}


def test_identifiers_applies_aliases():
    cell = 'the fit is `w` wide'
    assert df._identifiers(cell, {'w': 'extrusion_width'}) == {'extrusion_width'}


def test_identifiers_ignores_non_identifier_characters_inside_a_span():
    cell = '`corner_radius - panel_thickness`'
    assert df._identifiers(cell, {}) == {'corner_radius', 'panel_thickness'}


# ------------------------------------------------------------
# written -- a value as the sheet would print it
# ------------------------------------------------------------

def test_written_formats_a_float_to_the_sheet_decimal_places():
    assert df.written(5.0) == '5.00'
    assert df.written(5.004) == '5.00'


def test_written_returns_none_for_a_bool_or_a_non_number():
    assert df.written(True) is None
    assert df.written('end_bolt') is None
    assert df.written(None) is None


# ------------------------------------------------------------
# sheet_rows / _sort_key
# ------------------------------------------------------------

def test_sheet_rows_counts_distinct_first_axis_values_not_total_rows():
    # A 2-axis table: 2 values of the first axis x 3 of the second = 6 rows, 2 sheet rows.
    rows = [[1.0, 'a', 'x'], [1.0, 'b', 'x'], [1.0, 'c', 'x'],
            [2.0, 'a', 'y'], [2.0, 'b', 'y'], [2.0, 'c', 'y']]
    assert df.sheet_rows(('U', 'panel'), rows) == 2


def test_sort_key_orders_numbers_before_names_and_numbers_numerically():
    items = [((2.0,), None), ((10.0,), None), ((1.0,), None), (('end_bolt',), None)]
    ordered = sorted(items, key=df._sort_key)
    assert [k for k, _ in ordered] == [(1.0,), (2.0,), (10.0,), ('end_bolt',)]


# ------------------------------------------------------------
# minimal_axes -- the smallest axis set a field is a function of
# ------------------------------------------------------------

def _synthetic_members():
    """A tiny 2x2 grid over (U, panel), with one field constant, one following U only, one
    following panel only, and one following both."""
    return [
        ({'U': 1.0, 'panel': 'a'},
         {'const': 5.0, 'by_u': 1.0, 'by_panel': 10.0, 'by_both': 11.0}),
        ({'U': 1.0, 'panel': 'b'},
         {'const': 5.0, 'by_u': 1.0, 'by_panel': 20.0, 'by_both': 21.0}),
        ({'U': 2.0, 'panel': 'a'},
         {'const': 5.0, 'by_u': 2.0, 'by_panel': 10.0, 'by_both': 12.0}),
        ({'U': 2.0, 'panel': 'b'},
         {'const': 5.0, 'by_u': 2.0, 'by_panel': 20.0, 'by_both': 22.0}),
    ]


@pytest.mark.parametrize('field,expected', [
    ('const', ()),
    ('by_u', ('U',)),
    ('by_panel', ('panel',)),
    ('by_both', ('U', 'panel')),
])
def test_minimal_axes_finds_the_smallest_consistent_subset(field, expected):
    assert df.minimal_axes(_synthetic_members(), field, ('U', 'panel')) == expected


def test_minimal_axes_returns_none_when_no_axis_subset_is_consistent():
    """Two rows share every axis value (both U=1, panel=a) but disagree on the field -- not
    a function of the declared axes at all, which is factor()'s trigger to raise."""
    members = [
        ({'U': 1.0, 'panel': 'a'}, {'x': 1.0}),
        ({'U': 1.0, 'panel': 'a'}, {'x': 2.0}),
    ]
    assert df.minimal_axes(members, 'x', ('U', 'panel')) is None


# ------------------------------------------------------------
# factor -- fields grouped into constants / structural zeros / per-axis-set tables
# ------------------------------------------------------------

def test_factor_separates_constants_zeros_and_per_axis_tables():
    members = _synthetic_members()
    result = df.factor(members, ('U', 'panel'), interface=set())

    assert result['constants'] == {'const': '5.00'}
    table_axes = {tuple(t['axes']) for t in result['tables']}
    assert table_axes == {('U',), ('panel',), ('U', 'panel')}


def test_factor_reports_a_field_that_is_zero_across_the_family_as_a_structural_zero():
    members = [
        ({'U': 1.0}, {'always_zero': 0.0}),
        ({'U': 2.0}, {'always_zero': 0.0}),
    ]
    result = df.factor(members, ('U',), interface=set())
    assert result['structural_zeros'] == {'always_zero': '0.00'}
    assert result['constants'] == {}


def test_factor_raises_when_a_field_is_not_a_function_of_the_declared_axes():
    members = [
        ({'U': 1.0}, {'x': 1.0}),
        ({'U': 1.0}, {'x': 2.0}),
    ]
    with pytest.raises(RuntimeError, match='not a function'):
        df.factor(members, ('U',), interface=set())


def test_factor_marks_interface_columns_on_their_table():
    members = _synthetic_members()
    result = df.factor(members, ('U', 'panel'), interface={'by_u'})
    [table] = [t for t in result['tables'] if t['axes'] == ['U']]
    assert table['interface'] == ['by_u']


# ------------------------------------------------------------
# read_register -- the real interface register, parsed from dimension_scheme.md
# ------------------------------------------------------------

def test_read_register_parses_the_real_register_into_ten_rows():
    rows = df.read_register()
    assert len(rows) == 10
    for number, names, clearance, parts in rows:
        assert isinstance(number, int)
        assert clearance <= names  # the clearance names are always a subset of all names
        assert all(isinstance(p, str) for p in parts)


def test_read_register_raises_on_a_document_with_no_parseable_table(tmp_path):
    doc = tmp_path / 'dimension_scheme.md'
    doc.write_text('## 2. The interface register\n\nnothing table-shaped here\n\n## 3. x\n',
                   encoding='utf-8')
    with pytest.raises(RuntimeError, match='no register rows parsed'):
        df.read_register(str(doc))


# ------------------------------------------------------------
# interface_fields -- what section 3 obliges a kind's drawing to carry
# ------------------------------------------------------------

def test_interface_fields_for_corner_is_a_subset_of_its_own_mapping():
    dp = fv.derived_parameters(1.0, 1.0, _user_parameters(), fv.null_printer_settings(),
                               is_bulkhead=False)
    mapping_keys = set(fv.corner_parameters(dp))
    fields = df.interface_fields('corner', mapping_keys)
    assert fields  # the corner has a real, non-empty interface obligation
    assert set(fields) <= mapping_keys


def test_interface_fields_only_counts_names_the_kind_is_actually_driven_by():
    """A register row naming a boom-only name must not appear for the plain corner, whose
    mapping never carries it."""
    fields = df.interface_fields('corner', {'corner_radius'})
    assert fields == ['corner_radius'] or fields == []
    assert 'boom_collet_thickness' not in fields


# ------------------------------------------------------------
# check_register / check_topology_fields -- wired against the real data, the same assertion
# `python drawing_families.py` already prints as clean when run by hand.
# ------------------------------------------------------------

def test_check_register_has_no_problems_against_the_real_register():
    assert df.check_register() == []


def test_check_topology_fields_has_no_problems_against_the_real_sweep():
    assert df.check_topology_fields() == []


# ------------------------------------------------------------
# resolve -- every variant of a real sweep the sweep would actually generate
# ------------------------------------------------------------

def test_resolve_returns_the_real_bulkhead_corpus_with_the_documented_shape():
    rows = df.resolve('bulkhead')
    assert len(rows) == 148  # the real, current bulkhead corpus size
    axis_values, flat, mapped, type_name = rows[0]
    assert set(axis_values) == {'U', 'panel', 'type'}
    assert isinstance(flat, dict) and isinstance(mapped, dict)
    assert isinstance(type_name, str)


def test_resolve_drops_combinations_the_sweep_would_refuse():
    """corner_validity_check rejects a panel thicker than the corner allows -- resolve('corner')
    must never include a combination that check_derivation/family_is_valid would also drop."""
    rows = df.resolve('corner')
    for _axis_values, flat, _mapped, _type_name in rows:
        assert flat['panel.thickness'] <= flat['corner.radius']


# ------------------------------------------------------------
# topology_of -- a variant's family signature: features, not size
# ------------------------------------------------------------

def test_topology_of_end_bolt_and_end_anchor_share_one_signature():
    """The module's own headline finding: end_bolt and end_anchor differ in exactly one
    number (bolt_hole_radius) and so are one family, not two -- this is the partition
    decision that finding rests on."""
    rows = df.resolve('bulkhead')
    by_type = {}
    for _axis_values, flat, mapped, type_name in rows:
        by_type.setdefault(type_name, (flat, mapped))

    t_bolt = df.topology_of(*by_type['end_bolt'])
    t_anchor = df.topology_of(*by_type['end_anchor'])
    assert t_bolt == t_anchor


def test_topology_of_a_cowling_type_differs_from_an_end_type():
    rows = df.resolve('bulkhead')
    by_type = {}
    for _axis_values, flat, mapped, type_name in rows:
        by_type.setdefault(type_name, (flat, mapped))

    end_types = [name for name in by_type if 'end' in name]
    cowl_types = [name for name in by_type if 'cowl' in name.lower()]
    assert end_types and cowl_types
    t_end = df.topology_of(*by_type[end_types[0]])
    t_cowl = df.topology_of(*by_type[cowl_types[0]])
    assert t_end != t_cowl


def test_topology_of_reports_absent_for_a_field_the_object_does_not_have():
    """A cowl's resolved object has none of TOPOLOGY_FIELDS/PRESENCE_FIELDS -- 'absent' is a
    distinct, true statement, not the same as False."""
    dp = fv.null_nose_parameters()
    flat = df.flatten(dp)
    key = df.topology_of(flat)
    assert dict(key)['bulkhead.type'] == 'absent'
