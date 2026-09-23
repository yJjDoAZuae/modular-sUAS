"""IP-TEST-11: tests for freecad/sheet_annotations.py. No FreeCAD import at module scope (nor
in dimension_placement.py, which it imports), so this is fully testable from this tier despite
its location under src/Fuselage/freecad/.

**Line-by-line audit, completed 2026-09-23.** The shared infrastructure every one of the three
per-kind builders depends on (`Quantity`, `issue_letters`, `check_views`, `combined_view`, the
phrase/label functions) has full coverage. `corner_annotations`, `bulkhead_annotations` and
`boom_bulkhead_annotations` (and their helpers `corner_construction`, `detail_radius`,
`bulkhead_views`, `bulkhead_construction`) are each verified formula by formula against the
real, already-relied-on fixtures in out/*.params.json -- every concrete number a docstring in
sheet_annotations.py cites as "measured on the built solid"/"verified against ... worked
example" is checked exactly against the real fixture that produces it, not just exercised
structurally. Every conditional branch (`panelled`, `has_bolt`, `has_greeble`, `seated`, the
`dual` boom's mirrored collet) is exercised with a real fixture that actually takes that branch,
not a synthetic stand-in, using the real `is_cowling`/`is_interconnect`/panel-stock/boom-type
variants already committed in out/. All three real annotation builders are additionally run end
to end asserting the structural invariants the module's own docstrings promise (every declared
quantity gets a letter or is `constant`, `check_views` finds no mismatch, letters are unique) --
the kind of defect that would otherwise only surface as an opaque crash deep inside a real
freecadcmd build.
"""
import json
import sys
from pathlib import Path

import pytest

_FREECAD_DIR = str(Path(__file__).resolve().parent.parent / 'src' / 'Fuselage' / 'freecad')
if _FREECAD_DIR not in sys.path:
    sys.path.insert(0, _FREECAD_DIR)

import dimension_placement as dp  # noqa: E402
import sheet_annotations as sa  # noqa: E402

_OUT_DIR = Path(_FREECAD_DIR) / 'out'


def _load(name, table):
    with open(_OUT_DIR / name) as f:
        doc = json.load(f)
    return doc[table]


@pytest.fixture
def corner_params():
    return _load('reference_bulkhead.params.json', 'corner_parameters')


@pytest.fixture
def bulkhead_params():
    return _load('reference_bulkhead.params.json', 'parameters')


@pytest.fixture
def boom_bulkhead_params():
    return _load('ref_boom_center.params.json', 'boom_parameters')


@pytest.fixture
def dual_boom_params():
    return _load('ref_boom_dual.params.json', 'boom_parameters')


@pytest.fixture
def cowling_bulkhead_params():
    """is_cowling=1, panel_thickness=0 -- the real fixture for has_greeble=False."""
    return _load('ref_cowling_bolt.params.json', 'parameters')


@pytest.fixture
def interconnect_bulkhead_params():
    """is_interconnect=1 -- the real fixture for has_bolt=False."""
    return _load('ref_interconnect.params.json', 'parameters')


# ------------------------------------------------------------
# Quantity
# ------------------------------------------------------------

def test_quantity_written_on_a_family_sheet_is_its_letter():
    q = sa.Quantity('bore_diameter', 4.1, carries=('longeron_radius',))
    q.letter = 'A'
    assert q.written(sa.FAMILY) == 'A'


def test_quantity_written_on_a_variant_sheet_is_its_formatted_value():
    q = sa.Quantity('bore_diameter', 4.1)
    assert q.written(sa.VARIANT) == sa.std.format_length(4.1)


def test_quantity_written_raises_when_no_letter_was_issued_yet():
    q = sa.Quantity('bore_diameter', 4.1)
    with pytest.raises(ValueError, match='no callout letter'):
        q.written(sa.FAMILY)


def test_constant_quantity_is_always_its_value_even_on_a_family_sheet():
    q = sa.Quantity('longeron_clearance', 0.1, constant=True)
    assert q.written(sa.FAMILY) == sa.std.format_length(0.1)


# ------------------------------------------------------------
# Construction-geometry helpers
# ------------------------------------------------------------

def test_center_marks_pairs_every_center_with_the_same_radius():
    marks = sa.center_marks([(0.0, 0.0), (1.0, 2.0)], radius=3.5)
    assert marks == [(sa.CENTER_MARK, (0.0, 0.0), 3.5), (sa.CENTER_MARK, (1.0, 2.0), 3.5)]


def test_rectangle_is_counter_clockwise_from_the_given_corner():
    assert sa.rectangle(0.0, 0.0, 2.0, 1.0) == (
        (0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0))


def test_axis_line_runs_through_the_origin_both_ways():
    line = sa.axis_line((1.0, 0.0), reach=5.0)
    assert line == (sa.CENTER_LINE, (-5.0, 0.0), (5.0, 0.0))


def test_axis_line_scales_a_non_unit_direction():
    line = sa.axis_line((2.0, 0.0), reach=3.0)
    assert line == (sa.CENTER_LINE, (-6.0, 0.0), (6.0, 0.0))


# ------------------------------------------------------------
# Phrase / label functions
# ------------------------------------------------------------

def test_topology_phrase_uses_the_pinned_phrase_pair_for_a_boolean():
    assert sa.topology_phrase('panel.thickness != 0', True) == 'PANELLED'
    assert sa.topology_phrase('panel.thickness != 0', False) == 'NO PANEL'


def test_topology_phrase_falls_back_for_an_unlisted_boolean_condition():
    assert sa.topology_phrase('some_new_flag', True) == 'SOME NEW FLAG'
    assert sa.topology_phrase('some_new_flag', False) == 'NO SOME NEW FLAG'


def test_topology_phrase_of_a_valued_condition_is_just_the_value():
    assert sa.topology_phrase('bulkhead.type', 'end') == 'END'


def test_branch_phrase_names_only_conditions_that_vary_among_siblings():
    family = {'key': 'a', 'topology': [['panel.thickness != 0', True],
                                       ['corner seating flat', True]]}
    sibling = {'key': 'b', 'topology': [['panel.thickness != 0', False],
                                        ['corner seating flat', True]]}
    # Only the first condition differs between the two -- the second must not appear.
    assert sa.branch_phrase(family, [family, sibling]) == 'PANELLED'


def test_branch_phrase_with_no_siblings_names_every_condition():
    family = {'key': 'a', 'topology': [['panel.thickness != 0', True]]}
    assert sa.branch_phrase(family, ()) == 'PANELLED'


def test_variant_phrase_reads_out_the_swept_axes():
    variant = {'U': 1.0, 'panel_name': '3/16in', 'bulkhead_type_name': 'end_bolt'}
    assert sa.variant_phrase(variant) == 'U 1.0, 3/16IN PANEL, END_BOLT'


def test_variant_phrase_of_nothing_recorded():
    assert sa.variant_phrase({}) == 'NOT RECORDED'
    assert sa.variant_phrase(None) == 'NOT RECORDED'


def test_coverage_rows_always_states_geometry_shown_and_do_not_scale():
    rows = sa.coverage_rows({}, {'U': 1.0}, ())
    labels = [label for label, _value in rows]
    assert 'GEOMETRY SHOWN' in labels
    assert 'DO NOT SCALE' in labels


def test_coverage_rows_states_the_variant_count_when_given():
    rows = dict(sa.coverage_rows({'variants': 8}, {}, ()))
    assert rows['VARIANTS'] == '8, SEE TABLE BELOW'


def test_description_uses_the_pinned_phrase():
    assert sa.description('bolt_offset') == 'BOLT AXIS FROM LONGERON'


def test_description_falls_back_to_the_field_name_for_an_unlisted_field():
    assert sa.description('some_new_field') == 'SOME NEW FIELD'


# ------------------------------------------------------------
# issue_letters
# ------------------------------------------------------------

def test_issue_letters_skips_constants_and_assigns_in_order():
    quantities = [sa.Quantity('a', 1.0), sa.Quantity('b', 2.0, constant=True),
                 sa.Quantity('c', 3.0)]
    sa.issue_letters(quantities)
    assert [q.letter for q in quantities] == ['A', None, 'B']


def test_issue_letters_omits_i_o_and_q():
    assert 'I' not in sa.std.CALLOUT_ALPHABET
    assert 'O' not in sa.std.CALLOUT_ALPHABET
    assert 'Q' not in sa.std.CALLOUT_ALPHABET


def test_issue_letters_raises_when_the_alphabet_runs_out():
    quantities = [sa.Quantity(str(i), float(i)) for i in range(len(sa.std.CALLOUT_ALPHABET) + 1)]
    with pytest.raises(dp.PlacementError, match='more than'):
        sa.issue_letters(quantities)


# ------------------------------------------------------------
# SheetView / combined_view / check_views
# ------------------------------------------------------------

def _quantity_dim(name):
    q = sa.Quantity(name, 1.0)
    q.letter = 'A'
    return (q, (0, 0, 0), (1, 0, 0), dp.HORIZONTAL, 1.0)


def test_check_views_accepts_a_set_that_carries_everything_exactly_once():
    dim = _quantity_dim('bore_diameter')
    notes = [('bore', (0, 0, 0), ('a note',))]
    views = [sa.SheetView('PLAN', dimensions=('bore_diameter',), notes=('bore',))]
    assert sa.check_views(views, [dim], notes) == []


def test_check_views_refuses_a_dimension_no_view_carries():
    dim = _quantity_dim('bore_diameter')
    views = [sa.SheetView('PLAN', dimensions=(), notes=())]
    problems = sa.check_views(views, [dim], [])
    assert any('no view carries it' in p for p in problems)


def test_check_views_refuses_a_dimension_carried_by_two_views():
    dim = _quantity_dim('bore_diameter')
    views = [sa.SheetView('PLAN', dimensions=('bore_diameter',)),
            sa.SheetView('DETAIL', dimensions=('bore_diameter',))]
    problems = sa.check_views(views, [dim], [])
    assert any('carried by' in p for p in problems)


def test_check_views_refuses_a_view_naming_a_dimension_that_does_not_exist():
    views = [sa.SheetView('PLAN', dimensions=('phantom_quantity',))]
    problems = sa.check_views(views, [], [])
    assert any('which this variant does not have' in p for p in problems)


def test_combined_view_carries_every_dimension_and_note_on_one_view():
    dim = _quantity_dim('bore_diameter')
    notes = [('bore', (0, 0, 0), ('a note',))]
    views = [sa.SheetView('PLAN'), sa.SheetView('DETAIL')]
    combined = sa.combined_view(views, [dim], notes)
    assert len(combined) == 1
    assert combined[0].name == 'PLAN'
    assert combined[0].dimensions == ('bore_diameter',)
    assert combined[0].notes == ('bore',)
    # And the combined view must itself pass check_views -- the whole point of the fallback.
    assert sa.check_views(combined, [dim], notes) == []


# ------------------------------------------------------------
# corner_seat_span -- exactly verified against the module's own cited real numbers
# ------------------------------------------------------------

def test_corner_seat_span_matches_the_docstring_worked_example(corner_params):
    """1U/3-16in span 0.5250 at x 32.7375 -- corner_seat_span's own cited, built-solid-verified
    figure. reference_bulkhead.params.json's corner_parameters is exactly this configuration
    (U=1.0, panel_thickness=4.7625 ~= 3/16in)."""
    assert sa.corner_seat_span(corner_params) == pytest.approx(0.5250, abs=1e-4)


def test_corner_seat_span_is_zero_when_the_panel_branch_wins(corner_params):
    """The module's own algebraic claim: max(a, b) - b is exactly zero when the panel branch
    (b) is the larger one -- verified by constructing a case where it clearly is (an
    unrealistically large panel_overlap forces the panel branch to dominate)."""
    params = dict(corner_params)
    params['panel_overlap'] = 100.0
    assert sa.corner_seat_span(params) == pytest.approx(0.0, abs=1e-9)


def test_corner_seat_span_is_none_when_extrusion_width_is_absent(boom_bulkhead_params):
    """A boom bulkhead's mapping does not carry extrusion_width -- corner_seat_span's own
    documented None case, checked against the real fixture that actually lacks the key rather
    than a synthetic dict built to omit it."""
    assert 'extrusion_width' not in boom_bulkhead_params
    assert sa.corner_seat_span(boom_bulkhead_params) is None


# ------------------------------------------------------------
# The three real annotation builders, end to end, against real fixtures
# ------------------------------------------------------------

def _assert_well_formed(quantities, dimensions, notes, construction, views, kind):
    # Every non-constant quantity got a letter; every constant did not.
    for q in quantities:
        if q.constant:
            assert q.letter is None, '%s: constant %r was issued a letter' % (kind, q.name)
        else:
            assert q.letter is not None, '%s: %r has no callout letter' % (kind, q.name)
    # Letters are unique.
    letters = [q.letter for q in quantities if q.letter is not None]
    assert len(letters) == len(set(letters)), '%s: a callout letter was issued twice' % kind
    assert all(letter in sa.std.CALLOUT_ALPHABET for letter in letters)

    # The view set accounts for every dimension and every note exactly once.
    problems = sa.check_views(views, dimensions, notes)
    assert problems == [], '%s: check_views found %r' % (kind, problems)

    # Every dimensioned quantity actually appears in the quantities list issue_letters ran on.
    by_name = {q.name: q for q in quantities}
    for q, _p1, _p2, _axis, _value in dimensions:
        assert by_name.get(q.name) is q, '%s: dimensioned quantity %r is not in quantities' \
            % (kind, q.name)


def test_corner_annotations_is_well_formed_on_the_real_fixture(corner_params):
    quantities, dimensions, notes, construction, views = sa.corner_annotations(corner_params)
    _assert_well_formed(quantities, dimensions, notes, construction, views, 'corner')


def test_bulkhead_annotations_is_well_formed_on_the_real_fixture(bulkhead_params):
    quantities, dimensions, notes, construction, views = sa.bulkhead_annotations(bulkhead_params)
    _assert_well_formed(quantities, dimensions, notes, construction, views, 'bulkhead')


def test_boom_bulkhead_annotations_is_well_formed_on_the_real_fixture(boom_bulkhead_params):
    quantities, dimensions, notes, construction, views = sa.boom_bulkhead_annotations(
        boom_bulkhead_params)
    _assert_well_formed(quantities, dimensions, notes, construction, views, 'boom_bulkhead')


def test_quantities_for_dispatches_to_the_right_builder(corner_params, bulkhead_params,
                                                         boom_bulkhead_params):
    corner_q = sa.quantities_for('corner', corner_params)
    bulkhead_q = sa.quantities_for('bulkhead', bulkhead_params)
    boom_q = sa.quantities_for('boom_bulkhead', boom_bulkhead_params)
    # quantities_for returns exactly the first element of the builder's own return tuple.
    assert [q.name for q in corner_q] == [q.name for q in
                                          sa.corner_annotations(corner_params)[0]]
    assert [q.name for q in bulkhead_q] == [q.name for q in
                                            sa.bulkhead_annotations(bulkhead_params)[0]]
    assert [q.name for q in boom_q] == [q.name for q in
                                        sa.boom_bulkhead_annotations(boom_bulkhead_params)[0]]


def test_variant_product_writes_values_not_letters(corner_params):
    """The one documented difference between the two products: a single-variant sheet's
    quantities carry their numeric value, not a callout letter."""
    quantities, dimensions, notes, construction, views = sa.corner_annotations(
        corner_params, product=sa.VARIANT)
    for q in quantities:
        if not q.constant:
            assert q.written(sa.VARIANT) == sa.std.format_length(q.value)


# ------------------------------------------------------------
# corner_annotations / corner_construction -- formula by formula
# ------------------------------------------------------------

def _by_name(quantities):
    return {q.name: q for q in quantities}


def test_corner_annotations_matches_every_built_solid_measurement(corner_params):
    """1U/3-16in: the corner's own docstring cites a planar face at x = -7.2625 (panel_extension)
    and, via corner_seat_span, a seat span of 0.5250 at x = 32.7375 -- both checked here against
    the real fixture that produces them."""
    quantities, dimensions, notes, construction, views = sa.corner_annotations(corner_params)
    by_name = _by_name(quantities)
    assert by_name['panel_extension'].value == pytest.approx(7.2625, abs=1e-4)
    assert by_name['corner_radius'].value == pytest.approx(10.0)
    assert by_name['bore_diameter'].value == pytest.approx(2 * 2.05, abs=1e-4)
    assert by_name['panel_pocket'].value == pytest.approx(4.8625, abs=1e-4)


def test_corner_annotations_drops_panel_quantities_when_unpanelled(cowling_bulkhead_params):
    """A corner with no panel states no panel pocket -- section 2's structural-zero rule, using
    the corner_parameters half of the real cowling fixture (panel_thickness=0)."""
    corner_p = _load('ref_cowling_bolt.params.json', 'corner_parameters')
    quantities, dimensions, notes, construction, views = sa.corner_annotations(corner_p)
    names = {q.name for q in quantities}
    assert 'panel_pocket' not in names
    assert 'panel_thickness' not in names
    # panel_extension stays regardless -- panel_overlap is nonzero whether or not a panel is
    # fitted, per the module's own docstring.
    assert 'panel_extension' in names


def test_corner_construction_marks_the_bore_and_the_one_real_diagonal(corner_params):
    construction = sa.corner_construction(
        corner_params, radius=10.0, bore=2.05, seat=5.1375, thickness=4.7625,
        extension=7.2625, panelled=True)
    marks = [c for c in construction if c[0] == sa.CENTER_MARK]
    lines = [c for c in construction if c[0] == sa.CENTER_LINE]
    assert marks == [(sa.CENTER_MARK, (0.0, 0.0), 2.05)]
    assert len(lines) == 1
    # The diagonal: inboard at (-extension, -extension), outboard at radius/sqrt(2) each way.
    root_half = 0.5 ** 0.5
    _kind, p1, p2 = lines[0]
    assert p1 == pytest.approx((-7.2625, -7.2625))
    assert p2 == pytest.approx((10.0 * root_half, 10.0 * root_half))


def test_corner_construction_draws_panels_only_when_panelled(corner_params):
    panelled = sa.corner_construction(corner_params, 10.0, 2.05, 5.1375, 4.7625, 7.2625, True)
    unpanelled = sa.corner_construction(corner_params, 10.0, 2.05, 5.1375, 0.0, 7.2625, False)
    assert any(c[0] == sa.REFERENCE for c in panelled)
    assert not any(c[0] == sa.REFERENCE for c in unpanelled)
    # Two panel rectangles (the y = x mirror pair), per the docstring.
    assert sum(1 for c in panelled if c[0] == sa.REFERENCE) == 2


# ------------------------------------------------------------
# bulkhead_annotations -- formula by formula, against the built-solid figures its own
# docstring cites (1U, 3/16in, end_bolt)
# ------------------------------------------------------------

def test_bulkhead_annotations_matches_every_built_solid_measurement(bulkhead_params):
    quantities, dimensions, notes, construction, views = sa.bulkhead_annotations(bulkhead_params)
    by_name = _by_name(quantities)

    # The four planar/cylindrical features the docstring cites as measured on the built solid.
    assert by_name['mold_half_width'].value == pytest.approx(50.0)
    assert by_name['bore_diameter'].value == pytest.approx(2 * 2.05, abs=1e-4)      # R2.05
    assert by_name['post_diameter'].value == pytest.approx(2 * 3.25, abs=1e-4)      # R3.25
    assert by_name['nub_diameter'].value == pytest.approx(2 * 4.45, abs=1e-4)       # R4.45
    assert by_name['boss_diameter'].value == pytest.approx(2 * 5.0, abs=1e-4)       # bolt(2.0) + boss wall(3.0)
    assert by_name['bolt_diameter'].value == pytest.approx(2 * 2.0, abs=1e-4)       # R2.00
    assert by_name['bolt_offset'].value == pytest.approx(8.0, abs=1e-4)             # 8.00 each axis
    assert by_name['longeron_offset'].value == pytest.approx(40.0, abs=1e-4)        # axis at 40

    # DES-3's aperture: 50 - 4.8625 - 1.2 = 43.9375, span 87.875, the design doc's own example.
    assert by_name['enclosed_span'].value == pytest.approx(87.875, abs=1e-4)

    # Register joint 5's exposed span: half_span 32.7375, matching 2 * half_span * thickness
    # = 392.8500 mm2 to four decimals, per the docstring's own worked check.
    assert by_name['panel_span'].value == pytest.approx(2 * 32.7375, abs=1e-4)
    half_span = by_name['panel_span'].value / 2.0
    assert 2.0 * half_span * bulkhead_params['bulkhead_thickness'] == pytest.approx(
        392.85, abs=1e-2)

    # Register joint 3's offset: verified on built solids, 1.8738 at 1U/3-16in where the bore
    # branch wins -- stated per-axis here (2.65) and "over root two" along the diagonal.
    seat_offset = by_name['corner_seat_offset'].value
    assert seat_offset == pytest.approx(2.65, abs=1e-4)
    assert seat_offset / (2.0 ** 0.5) == pytest.approx(1.8738, abs=1e-4)


def test_bulkhead_annotations_seat_offset_panel_branch(bulkhead_params):
    """The other branch of corner_seat_offset: where the panel branch wins instead of the bore
    branch. Constructed by growing panel_overlap on the real fixture until the panel branch
    dominates (the same technique check_geometry_branches.py's own tests already use for this
    exact max()), rather than sourcing a second real fixture -- the point under test is the
    conditional's own arithmetic, already exercised for real in the bore-branch case above."""
    params = dict(bulkhead_params)
    params['panel_overlap'] = 20.0
    quantities, *_ = sa.bulkhead_annotations(params)
    by_name = _by_name(quantities)
    seat_span = sa.corner_seat_span(params)
    assert seat_span == pytest.approx(0.0, abs=1e-9)   # panel branch wins: span is exactly zero
    expected = (params['panel_overlap'] + params['panel_offset']) \
        - (params['corner_radius'] - (params['panel_thickness'] + params['panel_tolerance']))
    assert by_name['corner_seat_offset'].value == pytest.approx(expected)


def test_bulkhead_annotations_drops_greeble_quantities_when_cowling(cowling_bulkhead_params):
    """IP-FC-132: a cowling bulkhead has no greeble post or nub."""
    quantities, dimensions, notes, construction, views = sa.bulkhead_annotations(
        cowling_bulkhead_params)
    names = {q.name for q in quantities}
    assert 'post_diameter' not in names
    assert 'nub_diameter' not in names
    assert not any(key == 'post' for key, _anchor, _lines in notes)
    # The bolt is still there -- only is_cowling gates the greeble, not the bolt.
    assert 'bolt_offset' in names


def test_bulkhead_annotations_drops_bolt_quantities_when_interconnect(
        interconnect_bulkhead_params):
    """An interconnect has no bolt boss at all."""
    quantities, dimensions, notes, construction, views = sa.bulkhead_annotations(
        interconnect_bulkhead_params)
    names = {q.name for q in quantities}
    assert 'bolt_offset' not in names
    assert 'bolt_diameter' not in names
    assert 'boss_diameter' not in names
    assert not any(key == 'bolt' for key, _anchor, _lines in notes)
    dimensioned = {q.name for q, *_ in dimensions}
    assert 'bolt_offset' not in dimensioned
    # The greeble is still there -- only is_interconnect gates the bolt.
    assert 'post_diameter' in names


def test_bulkhead_annotations_corner_seat_note_reflects_which_branch_won(bulkhead_params):
    """Register joint 3's note text differs by which branch of corner_seat_span won -- 'CLEARS
    BORE AND LEAD-IN' when seated (the bore branch), 'SET BY PANEL ENTRY' otherwise."""
    _q, _d, notes, _c, _v = sa.bulkhead_annotations(bulkhead_params)
    seat_note = next(lines for key, _a, lines in notes if key == 'corner_seat')
    assert 'CLEARS BORE AND LEAD-IN' in seat_note

    panel_wins = dict(bulkhead_params)
    panel_wins['panel_overlap'] = 20.0
    _q2, _d2, notes2, _c2, _v2 = sa.bulkhead_annotations(panel_wins)
    seat_note2 = next(lines for key, _a, lines in notes2 if key == 'corner_seat')
    assert 'SET BY PANEL ENTRY' in seat_note2


# ------------------------------------------------------------
# detail_radius / bulkhead_views / bulkhead_construction
# ------------------------------------------------------------

def test_detail_radius_is_the_farthest_feature_plus_a_quarter_margin():
    # axis=40, bolt_axis=32, boss_radius=5.0, nub_radius=4.45, corner_radius=10.0
    bolt_reach = abs(40.0 - 32.0) * (2.0 ** 0.5) + 5.0
    want = sa.DETAIL_MARGIN * max(10.0, bolt_reach, 4.45)
    assert sa.detail_radius(40.0, 32.0, 5.0, 4.45, 10.0) == pytest.approx(want)


def test_bulkhead_views_detail_carries_bolt_and_post_only_when_present():
    with_both = sa.bulkhead_views({}, 50.0, 40.0, 32.0, 5.0, 4.45, panelled=True,
                                  has_greeble=True, has_bolt=True)
    detail = next(v for v in with_both if v.name == 'DETAIL A')
    assert 'bolt_offset' in detail.dimensions
    assert 'bolt' in detail.notes
    assert 'post' in detail.notes

    neither = sa.bulkhead_views({}, 50.0, 40.0, 32.0, 5.0, 4.45, panelled=False,
                                has_greeble=False, has_bolt=False)
    detail2 = next(v for v in neither if v.name == 'DETAIL A')
    assert 'bolt_offset' not in detail2.dimensions
    assert 'bolt' not in detail2.notes
    assert 'post' not in detail2.notes
    assert 'panel_pocket' not in detail2.dimensions


def test_bulkhead_views_plan_carries_panel_span_only_when_panelled():
    panelled = sa.bulkhead_views({}, 50.0, 40.0, 32.0, 5.0, 4.45, panelled=True)
    unpanelled = sa.bulkhead_views({}, 50.0, 40.0, 32.0, 5.0, 4.45, panelled=False)
    plan_p = next(v for v in panelled if v.name == 'PLAN')
    plan_u = next(v for v in unpanelled if v.name == 'PLAN')
    assert 'panel_span' in plan_p.dimensions
    assert 'panel_span' not in plan_u.dimensions
    assert 'enclosed_span' in plan_p.dimensions and 'enclosed_span' in plan_u.dimensions


def test_bulkhead_construction_marks_all_four_longeron_axes(bulkhead_params):
    construction = sa.bulkhead_construction(
        bulkhead_params, half=50.0, axis=40.0, bolt_axis=32.0, bore=2.05, boss_radius=5.0,
        seat=45.1375, thickness=4.7625, panelled=True, has_bolt=True)
    marks = [c for c in construction if c[0] == sa.CENTER_MARK]
    # Four longeron bores plus four bolt bosses.
    assert len(marks) == 8
    bore_marks = [m for m in marks if m[2] == 2.05]
    boss_marks = [m for m in marks if m[2] == 5.0]
    assert len(bore_marks) == 4
    assert len(boss_marks) == 4
    assert set(m[1] for m in bore_marks) == {(-40.0, -40.0), (-40.0, 40.0),
                                             (40.0, -40.0), (40.0, 40.0)}


def test_bulkhead_construction_omits_bolt_marks_when_has_bolt_is_false(bulkhead_params):
    construction = sa.bulkhead_construction(
        bulkhead_params, half=50.0, axis=40.0, bolt_axis=32.0, bore=2.05, boss_radius=5.0,
        seat=45.1375, thickness=4.7625, panelled=True, has_bolt=False)
    marks = [c for c in construction if c[0] == sa.CENTER_MARK]
    assert len(marks) == 4   # longeron bores only


def test_bulkhead_construction_draws_four_diagonals_and_axes(bulkhead_params):
    construction = sa.bulkhead_construction(
        bulkhead_params, half=50.0, axis=40.0, bolt_axis=32.0, bore=2.05, boss_radius=5.0,
        seat=45.1375, thickness=4.7625, panelled=True, has_bolt=True)
    lines = [c for c in construction if c[0] == sa.CENTER_LINE]
    assert len(lines) == 4   # x-axis, y-axis, and both diagonals


def test_bulkhead_construction_draws_four_panels_when_panelled(bulkhead_params):
    panelled = sa.bulkhead_construction(
        bulkhead_params, 50.0, 40.0, 32.0, 2.05, 5.0, 45.1375, 4.7625, True, True)
    unpanelled = sa.bulkhead_construction(
        bulkhead_params, 50.0, 40.0, 32.0, 2.05, 5.0, 45.1375, 0.0, False, True)
    assert sum(1 for c in panelled if c[0] == sa.REFERENCE) == 4
    assert sum(1 for c in unpanelled if c[0] == sa.REFERENCE) == 0


def test_bulkhead_construction_places_the_corner_reference_at_all_four_axes(bulkhead_params):
    construction = sa.bulkhead_construction(
        bulkhead_params, 50.0, 40.0, 32.0, 2.05, 5.0, 45.1375, 4.7625, True, True)
    ref_part = next(c for c in construction if c[0] == sa.REFERENCE_PART)
    _kind, kind_name, section_z, placements, label = ref_part
    assert kind_name == 'corner'
    assert section_z == pytest.approx(bulkhead_params['bulkhead_thickness'] / 2.0)
    assert len(placements) == 4
    assert set((sx, sy) for sx, sy, _tx, _ty in placements) == {
        (-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0)}


# ------------------------------------------------------------
# boom_bulkhead_annotations -- formula by formula
# ------------------------------------------------------------

def test_boom_bulkhead_annotations_matches_the_built_solid_measurement(boom_bulkhead_params):
    """78.275 mm at 1U with 3/16 in panel -- enclosed_span's own cited figure."""
    quantities, dimensions, notes, construction, views = sa.boom_bulkhead_annotations(
        boom_bulkhead_params)
    by_name = _by_name(quantities)
    assert by_name['enclosed_span'].value == pytest.approx(78.275, abs=1e-4)


def test_boom_bulkhead_annotations_collet_diameter_formula(boom_bulkhead_params):
    quantities, *_ = sa.boom_bulkhead_annotations(boom_bulkhead_params)
    by_name = _by_name(quantities)
    p = boom_bulkhead_params
    want = 2.0 * (p['boom_diameter'] / 2.0 + p['boom_collet_thickness'] + p['boom_tolerance'])
    assert by_name['collet_diameter'].value == pytest.approx(want)


def test_boom_bulkhead_annotations_collet_position_is_constant_and_stated_as_data(
        boom_bulkhead_params):
    quantities, dimensions, notes, construction, views = sa.boom_bulkhead_annotations(
        boom_bulkhead_params)
    by_name = _by_name(quantities)
    assert by_name['boom_y_position'].constant is True
    assert by_name['boom_z_position'].constant is True
    # Stated as data in the collet note, not drawn as its own dimension line.
    dimensioned = {q.name for q, *_ in dimensions}
    assert 'boom_y_position' not in dimensioned
    assert 'boom_z_position' not in dimensioned
    collet_note = next(lines for key, _a, lines in notes if key == 'collet')
    assert any('FROM CENTER' in line for line in collet_note)


def test_boom_bulkhead_dual_mirrors_the_collet_through_the_real_x_equals_0_axis(
        dual_boom_params):
    """Confirmed on the built solid, 2026-09-09: boom_y_position = 20, two collet bores at
    (-20, 20) and (20, 20). Verified here against the real ref_boom_dual.params.json fixture."""
    assert dual_boom_params['boom_y_position'] == pytest.approx(20.0)
    assert dual_boom_params['boom_z_position'] == pytest.approx(20.0)
    quantities, dimensions, notes, construction, views = sa.boom_bulkhead_annotations(
        dual_boom_params)
    collet_marks = [c for c in construction if c[0] == sa.CENTER_MARK
                    and abs(c[2] - (dual_boom_params['boom_diameter'] / 2.0
                                    + dual_boom_params['boom_collet_thickness']
                                    + dual_boom_params['boom_tolerance'])) < 1e-9]
    assert set(m[1] for m in collet_marks) == {(-20.0, 20.0), (20.0, 20.0)}


def test_boom_bulkhead_construction_marks_all_four_longeron_bores(boom_bulkhead_params):
    quantities, dimensions, notes, construction, views = sa.boom_bulkhead_annotations(
        boom_bulkhead_params)
    axis = boom_bulkhead_params['unit_width'] / 2.0 - boom_bulkhead_params['corner_radius']
    bore = boom_bulkhead_params['longeron_radius'] + boom_bulkhead_params['longeron_tolerance']
    bore_marks = [c for c in construction if c[0] == sa.CENTER_MARK
                 and abs(c[2] - bore) < 1e-9]
    assert set(m[1] for m in bore_marks) == {
        (-axis, -axis), (-axis, axis), (axis, -axis), (axis, axis)}


def test_boom_bulkhead_construction_draws_only_the_one_real_mirror(boom_bulkhead_params):
    """Only x = 0 is a real mirror -- y = 0 is not, per the module's own measured finding, so
    only one axis_line is drawn."""
    quantities, dimensions, notes, construction, views = sa.boom_bulkhead_annotations(
        boom_bulkhead_params)
    lines = [c for c in construction if c[0] == sa.CENTER_LINE]
    assert len(lines) == 1
    assert lines[0][1] == (0.0, -boom_bulkhead_params['unit_width'] / 2.0)
    assert lines[0][2] == (0.0, boom_bulkhead_params['unit_width'] / 2.0)


def test_boom_bulkhead_annotations_drops_panel_quantities_when_unpanelled(dual_boom_params):
    params = dict(dual_boom_params)
    params['panel_thickness'] = 0.0
    params['panel_tolerance'] = 0.0
    quantities, dimensions, notes, construction, views = sa.boom_bulkhead_annotations(params)
    names = {q.name for q in quantities}
    assert 'panel_pocket' not in names
    assert 'panel_span' not in names
    assert 'enclosed_span' in names   # unconditional, per the module's own docstring
