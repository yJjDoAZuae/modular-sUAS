"""IP-TEST-2 (doc/implementation/test_coverage.md): unit tests for fuselage_variants.py.

Covers this module's pure, deterministic logic -- filename generation, parameter
derivation, validity checks, constant validation, the parameter-mapping functions
(corner_parameters/bulkhead_parameters/cowl_parameters and friends), the small file-I/O
functions (CSV/JSON read, .scad reference rewriting), the backend/resume/preview state
setters, render_definition's file-management contract (atomic write, resume-skip,
renderer-lied-about-success detection), preview rasterization (real, since stl_preview has
no OpenSCAD/FreeCAD dependency), `RenderQueue`'s own thread-pool/retry/fail_fast mechanics
(real subprocess commands, decoupled from OpenSCAD via sys.executable one-liners), and
`solid_render`'s real OpenSCAD backend branch (also real: a trivial solid2 cube renders in
well under a second, so there was no need to fake it once tried). Not yet covered:
`freecad_render`'s own subprocess branch and top-level orchestration (`sweep_session`,
`main`, `run_*_parametric_sweep`, `_run_all_sweeps`) -- follow-up work under IP-TEST-2, not
this pass.

This is retrofit coverage on adoption-phase code (general.md's TDD section): each test pins
the function's current, intended behavior. Where a test exposed an actual defect rather than
documenting a design choice, that is called out in the test's docstring rather than silently
matching what the bug produced.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import fuselage_variants as fv
import pytest

# ------------------------------------------------------------
# oml_ref
# ------------------------------------------------------------

def test_oml_ref_prefixes_and_normalizes_backslashes():
    assert fv.oml_ref('tail_v2.stl') == '../oml/tail_v2.stl'
    assert fv.oml_ref('sub\\tail_v2.stl') == '../oml/sub/tail_v2.stl'


def test_oml_ref_strips_a_leading_slash():
    assert fv.oml_ref('/tail_v2.stl') == '../oml/tail_v2.stl'


# ------------------------------------------------------------
# generate_filename_from_params
# ------------------------------------------------------------

def test_generate_filename_from_params_sorts_keys_and_replaces_spaces():
    name = fv.generate_filename_from_params({'b': 'two words', 'a': 1}, prefix='p',
                                             extension='.json')
    assert name == 'p__a=1__b=two_words.json'


# ------------------------------------------------------------
# Filename generators for each part family -- all pure functions of a Parameters/
# NoseParameters tree, so built directly rather than through derived_parameters().
# ------------------------------------------------------------

def _dp_with_panel(is_metric=True, panel_name='1mm', U=1.0, FX=1.0, type_name='end_bolt'):
    dp = fv.null_parameters()
    dp.bulkhead.U = U
    dp.corner.FX = FX
    dp.panel.is_metric = is_metric
    dp.panel.type_name = panel_name
    dp.bulkhead.type_name = type_name
    return dp


def test_corner_filename_uses_metric_or_imperial_and_slashes_are_escaped():
    dp = _dp_with_panel(is_metric=True, panel_name='3/16in')
    path = fv.generate_fuselage_corner_variant_filename_from_params(dp)
    assert path == fv.os.path.join(
        'U_1.0', 'metric', 'panel_3_16in', 'corner',
        'U_1.0__metric_panel_3_16in__corner_FX_1.0.scad')

    dp_imp = _dp_with_panel(is_metric=False, panel_name='3/16in')
    path_imp = fv.generate_fuselage_corner_variant_filename_from_params(dp_imp)
    assert '__imperial_panel_' in path_imp


def test_bulkhead_filename_names_the_bulkhead_type():
    dp = _dp_with_panel(type_name='end_anchor')
    path = fv.generate_fuselage_bulkhead_variant_filename_from_params(dp)
    assert path == fv.os.path.join(
        'U_1.0', 'metric', 'panel_1mm', 'bulkhead',
        'U_1.0__metric_panel_1mm__bulkhead_end_anchor.scad')


def test_boom_bulkhead_filename_shares_the_bulkhead_directory_but_prefixes_the_file():
    """Pins current behavior: the boom bulkhead's directory name is literally "bulkhead",
    the same as the frame bulkhead's -- they do not collide only because the boom variant's
    file name additionally carries a "boom_bulkhead_" prefix the frame variant does not."""
    dp = _dp_with_panel(type_name='offset_single')
    path = fv.generate_fuselage_boom_bulkhead_variant_filename_from_params(dp)
    assert path == fv.os.path.join(
        'U_1.0', 'metric', 'panel_1mm', 'bulkhead',
        'U_1.0__metric_panel_1mm__boom_bulkhead_offset_single.scad')


def _nose_dp(type_name='nose_round'):
    dp = fv.null_nose_parameters()
    dp.type_name = type_name
    return dp


@pytest.mark.parametrize('flags,expected_type', [
    ((True, False, False), 'cowl'),
    ((False, True, False), 'nose'),
    ((False, False, True), 'plate'),
    ((False, False, False), ''),
])
def test_nose_filename_encodes_which_part_of_the_kind(flags, expected_type):
    dp = _nose_dp()
    path = fv.generate_fuselage_nose_variant_filename_from_params(1.0, dp, *flags)
    assert path == fv.os.path.join(
        'U_1.0', 'nose', 'nose_round',
        f'U_1.0__nose_round__nose_{expected_type}.scad')


def test_nose_shell_filename_suffixes_the_part_not_the_directory():
    dp = _nose_dp()
    path = fv.generate_fuselage_nose_variant_filename_from_params(
        1.0, dp, True, False, False, is_shell=True)
    assert path.endswith('nose_cowl_shell.scad')
    assert fv.os.path.join('U_1.0', 'nose', 'nose_round') in path


def test_tail_filename_shell_suffix():
    dp = fv.null_nose_parameters()
    dp.type_name = 'tail_round'
    plain = fv.generate_fuselage_tail_variant_filename_from_params(1.0, dp)
    shell = fv.generate_fuselage_tail_variant_filename_from_params(1.0, dp, is_shell=True)
    assert plain.endswith('__tail.scad')
    assert shell.endswith('__tail_shell.scad')


# ------------------------------------------------------------
# scaled_standard_values / greeble_nub_thickness_of
# ------------------------------------------------------------

def test_scaled_standard_values_scales_length_by_u_and_bay_length_by_u_times_fx():
    sv = fv.standard_values()
    scaled = fv.scaled_standard_values(U=2.0, FX=3.0)
    assert scaled['unit_width'] == pytest.approx(sv['unit_width'] * 2.0)
    assert scaled['unit_length'] == pytest.approx(sv['unit_length'] * 2.0 * 3.0)
    assert scaled['corner_radius'] == pytest.approx(sv['corner_radius'] * 2.0)
    assert scaled['longeron_radius'] == pytest.approx(sv['longeron_radius'] * 2.0)
    assert scaled['bolt_offset'] == pytest.approx(sv['bolt_offset'] * 2.0)


def test_scaled_standard_values_at_u_1_fx_1_matches_standard_values():
    sv = fv.standard_values()
    scaled = fv.scaled_standard_values(U=1.0, FX=1.0)
    assert scaled == sv


def test_greeble_nub_thickness_of_is_currently_the_identity():
    """Not a tautology to pin: greeble_nub_thickness_of's docstring says this is a formula
    that happens to be the identity today and may not stay one -- see the function's own
    docstring and OQ-DES-B4/B7 in doc/design/bulkhead.md. A future change to the formula
    should change this test, not the other way around."""
    assert fv.greeble_nub_thickness_of(1.23) == 1.23


# ------------------------------------------------------------
# bulkhead type encode/decode
#
# encode_bulkhead_type/decode_bulkhead_type are meant to round-trip for all five
# BulkheadType values. Writing this test found that decode_bulkhead_type crashes with
# UnboundLocalError for TAIL_BOOM and NULL -- both branches assign a local named
# `is_bolt` instead of the `is_end` the function returns, a copy-paste typo from the
# END/INTERCONNECT/COWLING branches above them. It has never fired because no CSV in
# variant_param/ ever sets is_boom=TRUE on the frame-bulkhead axis (only on
# boom_bulkhead_type_variants.csv, which never reaches decode_bulkhead_type -- see
# boom_bulkhead_parameters/boom_bulkhead_render, which decode nothing). Fixed alongside
# this test, 2026-09-22: both branches now assign is_end like every other branch.
# ------------------------------------------------------------

@pytest.mark.parametrize('bulkhead_type,expected', [
    (fv.BulkheadType.END, (True, False, False, False)),
    (fv.BulkheadType.INTERCONNECT, (False, True, False, False)),
    (fv.BulkheadType.COWLING, (False, False, True, False)),
    (fv.BulkheadType.TAIL_BOOM, (False, False, False, True)),
    (fv.BulkheadType.NULL, (False, False, False, False)),
])
def test_decode_bulkhead_type_covers_every_enum_value(bulkhead_type, expected):
    assert fv.decode_bulkhead_type(bulkhead_type) == expected


@pytest.mark.parametrize('is_end,is_interconnect,is_cowling,is_boom,expected', [
    (True, False, False, False, fv.BulkheadType.END),
    (False, True, False, False, fv.BulkheadType.INTERCONNECT),
    (False, False, True, False, fv.BulkheadType.COWLING),
    (False, False, False, True, fv.BulkheadType.TAIL_BOOM),
    (False, False, False, False, fv.BulkheadType.NULL),
])
def test_encode_decode_bulkhead_type_round_trip(is_end, is_interconnect, is_cowling,
                                                 is_boom, expected):
    encoded = fv.encode_bulkhead_type(is_end, is_interconnect, is_cowling, is_boom)
    assert encoded == expected
    assert fv.decode_bulkhead_type(encoded) == (is_end, is_interconnect, is_cowling, is_boom)


# ------------------------------------------------------------
# lookup_anchor_diameter -- reads the real, committed threaded_insert_dimensions.csv
# ------------------------------------------------------------

def test_lookup_anchor_diameter_known_bolt_size():
    assert fv.lookup_anchor_diameter(2) == pytest.approx(3.1)


def test_lookup_anchor_diameter_unknown_bolt_size_returns_zero():
    assert fv.lookup_anchor_diameter(-1) == 0


# ------------------------------------------------------------
# corner_validity_check / bulkhead_validity_check / boom_key_validity_check
# ------------------------------------------------------------

def _corner_ish_dp(panel_thickness, corner_radius=20.0, longeron_radius=2.0,
                    longeron_tolerance=0.0, greeble_thickness=1.0, greeble_nub_thickness=1.0,
                    unit_width=None, bulkhead_width=None):
    dp = fv.null_parameters()
    sv = fv.standard_values()
    dp.bulkhead.width = bulkhead_width if bulkhead_width is not None else sv['unit_width']
    dp.corner.radius = corner_radius
    dp.longeron.radius = longeron_radius
    dp.longeron.tolerance = longeron_tolerance
    dp.greeble.thickness = greeble_thickness
    dp.greeble.nub_thickness = greeble_nub_thickness
    dp.panel.thickness = panel_thickness
    return dp


def test_corner_validity_check_accepts_zero_panel_thickness_regardless_of_bounds():
    dp = _corner_ish_dp(panel_thickness=0)
    assert fv.corner_validity_check(dp) is True


def test_corner_validity_check_rejects_panel_thicker_than_the_max_bound():
    dp = _corner_ish_dp(panel_thickness=1000.0)
    assert fv.corner_validity_check(dp) is False


def test_corner_validity_check_accepts_a_panel_within_bounds():
    # bulkhead.width == unit_width -> U == 1, so min bound is 1 mm; max bound is
    # corner_radius - (longeron_radius + longeron_tolerance + greeble_thickness + nub)
    # = 20 - (2 + 0 + 1 + 1) = 16.
    dp = _corner_ish_dp(panel_thickness=2.0, corner_radius=20.0, longeron_radius=2.0,
                        greeble_thickness=1.0, greeble_nub_thickness=1.0)
    assert fv.corner_validity_check(dp) is True


def test_bulkhead_validity_check_rejects_nonzero_panel_on_a_cowling_bulkhead():
    dp = _corner_ish_dp(panel_thickness=2.0, corner_radius=20.0)
    dp.bulkhead.type = fv.BulkheadType.COWLING
    assert fv.bulkhead_validity_check(dp) is False


def test_bulkhead_validity_check_accepts_zero_panel_on_a_cowling_bulkhead():
    dp = _corner_ish_dp(panel_thickness=0, corner_radius=20.0)
    dp.bulkhead.type = fv.BulkheadType.COWLING
    assert fv.bulkhead_validity_check(dp) is True


def _boom_key_dp(key_width, key_height, key_radius, diameter=20.0, collet_thickness=1.0,
                 tolerance=0.2):
    dp = fv.null_parameters()
    dp.boom_bulkhead.key_width = key_width
    dp.boom_bulkhead.key_height = key_height
    dp.boom_bulkhead.key_radius = key_radius
    dp.boom_bulkhead.diameter = diameter
    dp.boom_bulkhead.collet_thickness = collet_thickness
    dp.boom_bulkhead.tolerance = tolerance
    return dp


def test_boom_key_validity_check_accepts_a_well_formed_key():
    dp = _boom_key_dp(key_width=6.0, key_height=6.0, key_radius=2.0)
    assert fv.boom_key_validity_check(dp) is True


def test_boom_key_validity_check_rejects_width_narrower_than_two_radii():
    """The docstring's singularity domain: key_width must be at least 2*key_radius."""
    dp = _boom_key_dp(key_width=3.0, key_height=6.0, key_radius=2.0)
    assert fv.boom_key_validity_check(dp) is False


def test_boom_key_validity_check_rejects_height_shorter_than_two_radii():
    dp = _boom_key_dp(key_width=6.0, key_height=3.0, key_radius=2.0)
    assert fv.boom_key_validity_check(dp) is False


def test_boom_key_validity_check_rejects_a_key_wider_than_the_collet_hole():
    collet_radius = 20.0 / 2 + 1.0 + 0.2  # 11.2
    dp = _boom_key_dp(key_width=2 * collet_radius + 1, key_height=6.0, key_radius=2.0)
    assert fv.boom_key_validity_check(dp) is False


# ------------------------------------------------------------
# bolt_flange_fillet_gap
# ------------------------------------------------------------

def test_bolt_flange_fillet_gap_matches_its_own_documented_formula():
    dp = fv.null_parameters()
    dp.panel.tolerance = 0.1
    dp.panel.offset = 2.0
    dp.panel.overlap = 0.5
    dp.bulkhead_flange.thickness = 1.2
    dp.bulkhead_flange.fillet_radius = 0.8
    dp.bolt.offset = 8.0
    dp.bolt.radius = 1.5
    dp.bolt.thickness = 0.6

    gap, reach = fv.bolt_flange_fillet_gap(dp)

    flange_inner_x = -(0.1 + 2.0 + 0.5 + 1.2)
    expected_gap = (flange_inner_x - 0.8) - (-8.0)
    expected_reach = 0.8 + 1.5 + 0.6
    assert gap == pytest.approx(expected_gap)
    assert reach == pytest.approx(expected_reach)


# ------------------------------------------------------------
# derived_parameters -- the central derivation. Only the keys each branch actually reads
# are required; extras would be silently ignored, which is itself pinned below.
# ------------------------------------------------------------

def _base_user_parameters(**overrides):
    params = dict(
        is_end=True, is_interconnect=False, is_cowling=False, is_boom=False,
        is_anchor=False, bulkhead_type_name='end_bolt', bulkhead_thickness=4.0,
        panel_is_metric=True, panel_thickness_mm=1.0, panel_name='1mm',
        bulkhead_bolt_diameter=3.0,
    )
    params.update(overrides)
    return params


def test_derived_parameters_scales_standard_dimensions_with_u_and_fx():
    dp = fv.derived_parameters(2.0, 3.0, _base_user_parameters(), fv.null_printer_settings(),
                                is_bulkhead=True)
    scaled = fv.scaled_standard_values(2.0, 3.0)
    assert dp.bulkhead.width == pytest.approx(scaled['unit_width'])
    assert dp.corner.radius == pytest.approx(scaled['corner_radius'])
    assert dp.longeron.radius == pytest.approx(scaled['longeron_radius'])
    assert dp.bolt.offset == pytest.approx(scaled['bolt_offset'])
    assert dp.corner.FX == 3.0
    assert dp.bulkhead.U == 2.0


def test_derived_parameters_cowling_branch_zeroes_the_panel_gap_and_sizes_the_cowl_flange():
    dp = fv.derived_parameters(1.0, 1.0, _base_user_parameters(is_cowling=True),
                                fv.null_printer_settings(), is_bulkhead=True)
    assert dp.panel.tolerance == 0.0
    assert dp.panel.overlap == 0
    assert dp.panel.offset == 0
    assert dp.cowl_flange.height == pytest.approx(fv.COWL_FLANGE_HEIGHT_PER_U * 1.0)
    assert dp.cowl_flange.tolerance == pytest.approx(fv.COWL_FLANGE_TOLERANCE_MM)
    assert dp.bulkhead_flange.thickness == pytest.approx(max(
        math.ceil(fv.COWL_BULKHEAD_FLANGE_EXTRUSIONS * 1.0) * dp.printer.extrusion_width,
        fv.COWL_BULKHEAD_FLANGE_EXTRUSIONS * dp.printer.extrusion_width))


def test_derived_parameters_non_cowling_branch_leaves_the_cowl_flange_at_zero():
    dp = fv.derived_parameters(1.0, 1.0, _base_user_parameters(is_cowling=False),
                                fv.null_printer_settings(), is_bulkhead=True)
    assert dp.cowl_flange.height == 0
    assert dp.cowl_flange.tolerance == 0.0
    assert dp.bulkhead_flange.thickness == pytest.approx(max(
        math.ceil(fv.BULKHEAD_FLANGE_EXTRUSIONS * 1.0) * dp.printer.extrusion_width,
        fv.BULKHEAD_FLANGE_EXTRUSIONS * dp.printer.extrusion_width))


def test_derived_parameters_zero_thickness_panel_has_no_overlap_but_still_computes_an_offset():
    """Pins a subtle, easy-to-misread branch: `panel.thickness == 0` forces `overlap` to 0,
    but `offset` is still computed by the general clearance formula below it, not forced to
    0 -- only the `is_cowling` branch forces offset to 0. A reader skimming derived_parameters
    could plausibly assume thickness==0 implies offset==0 too; it does not."""
    dp = fv.derived_parameters(1.0, 1.0, _base_user_parameters(panel_thickness_mm=0),
                                fv.null_printer_settings(), is_bulkhead=True)
    assert dp.panel.overlap == 0
    assert dp.panel.offset > 0


def test_derived_parameters_boom_branch_populates_boom_bulkhead_and_widens_the_web():
    dp = fv.derived_parameters(
        1.0, 1.0,
        _base_user_parameters(is_boom=True, is_end=False, boom_diameter=0.08,
                              y_position=0.0, z_position=0.25,
                              make_vert_web=True, make_lower_web=False),
        fv.null_printer_settings(), is_bulkhead=True)
    assert dp.boom_bulkhead.diameter > 0
    assert dp.boom_bulkhead.make_vert_web is True
    assert dp.web.width == pytest.approx(fv.BOOM_WEB_WIDTH_PER_U * 1.0)


def test_derived_parameters_non_boom_branch_leaves_boom_bulkhead_at_its_null_default():
    dp = fv.derived_parameters(1.0, 1.0, _base_user_parameters(is_boom=False),
                                fv.null_printer_settings(), is_bulkhead=True)
    assert dp.boom_bulkhead == fv.null_boom_bulkhead_parameters()
    assert dp.web.width == pytest.approx(fv.FRAME_WEB_WIDTH_PER_U * 1.0)


def test_derived_parameters_anchor_branch_uses_the_insert_table_not_half_the_bolt_diameter():
    dp = fv.derived_parameters(
        1.0, 1.0, _base_user_parameters(is_anchor=True, bulkhead_bolt_diameter=2.0),
        fv.null_printer_settings(), is_bulkhead=True)
    assert dp.bolt.radius == pytest.approx(fv.lookup_anchor_diameter(2.0) / 2)
    assert dp.bolt.radius != pytest.approx(2.0 / 2)


def test_derived_parameters_non_bulkhead_path_sets_the_corner_greeble_tolerance():
    """is_bulkhead=False is the corner path: the greeble post there is a real snap fit and
    takes a clearance; on a bulkhead it is nominal by construction and takes none."""
    dp_corner = fv.derived_parameters(1.0, 1.0, _base_user_parameters(),
                                       fv.null_printer_settings(), is_bulkhead=False)
    dp_bulkhead = fv.derived_parameters(1.0, 1.0, _base_user_parameters(),
                                         fv.null_printer_settings(), is_bulkhead=True)
    assert dp_corner.greeble.tolerance == pytest.approx(fv.GREEBLE_TOLERANCE_CORNER_MM)
    assert dp_bulkhead.greeble.tolerance == 0
    assert dp_corner.bulkhead.type_name == ''


# ------------------------------------------------------------
# derived_boom_bulkhead_parameters
# ------------------------------------------------------------

def test_derived_boom_bulkhead_parameters_scales_position_by_unit_width():
    user_parameters = dict(boom_diameter=0.08, y_position=0.1, z_position=0.2,
                           bulkhead_type_name='offset_single', make_vert_web=True,
                           make_lower_web=False)
    b = fv.derived_boom_bulkhead_parameters(1.0, 1.0, user_parameters,
                                            fv.null_printer_settings())
    unit_width = fv.scaled_standard_values(1.0, 1.0)['unit_width']
    assert b.diameter == pytest.approx(unit_width * 0.08)
    assert b.y_position == pytest.approx(unit_width * 0.1)
    assert b.z_position == pytest.approx(unit_width * 0.2)
    assert b.key_angle == pytest.approx(fv.BOOM_KEY_ANGLE_DEG)
    assert b.tolerance == pytest.approx(fv.BOOM_TOLERANCE_MM)


def test_derived_boom_bulkhead_parameters_key_dimensions_floor_at_u_1_coefficient():
    """max(U*COEF, COEF): below U=1 the key stops shrinking rather than becoming too small
    to print -- e.g. U=0.5 must still floor at the U=1 value, not half of it."""
    user_parameters = dict(boom_diameter=0.08, y_position=0.0, z_position=0.0,
                           bulkhead_type_name='offset_single', make_vert_web=False,
                           make_lower_web=False)
    b = fv.derived_boom_bulkhead_parameters(0.5, 1.0, user_parameters,
                                            fv.null_printer_settings())
    assert b.key_width == pytest.approx(fv.BOOM_KEY_WIDTH_PER_U)
    assert b.key_height == pytest.approx(fv.BOOM_KEY_HEIGHT_PER_U)
    assert b.key_radius == pytest.approx(fv.BOOM_KEY_RADIUS_PER_U)


# ------------------------------------------------------------
# flatten_param_space / read_param_csv / read_all_param_axes / read_param_json
# ------------------------------------------------------------

def test_flatten_param_space_is_the_cartesian_product_merged_per_combination():
    axes = [[{'a': 1}, {'a': 2}], [{'b': 'x'}, {'b': 'y'}]]
    combos = fv.flatten_param_space(axes)
    assert combos == [
        {'a': 1, 'b': 'x'}, {'a': 1, 'b': 'y'},
        {'a': 2, 'b': 'x'}, {'a': 2, 'b': 'y'},
    ]


def test_flatten_param_space_later_axis_overwrites_a_shared_key():
    axes = [[{'a': 1}], [{'a': 2}]]
    assert fv.flatten_param_space(axes) == [{'a': 2}]


def test_read_param_csv_round_trips_a_written_csv(tmp_path):
    path = tmp_path / 'axis.csv'
    path.write_text('a,b\n1,x\n2,y\n', encoding='utf-8')
    rows = fv.read_param_csv(str(path))
    assert rows == [{'a': 1, 'b': 'x'}, {'a': 2, 'b': 'y'}]


def test_read_all_param_axes_reads_each_file_as_its_own_axis(tmp_path):
    p1 = tmp_path / 'ax1.csv'
    p2 = tmp_path / 'ax2.csv'
    p1.write_text('a\n1\n2\n', encoding='utf-8')
    p2.write_text('b\nx\n', encoding='utf-8')
    axes = fv.read_all_param_axes([str(p1), str(p2)])
    assert axes == [[{'a': 1}, {'a': 2}], [{'b': 'x'}]]


def test_read_param_json_round_trips(tmp_path):
    path = tmp_path / 'shape.json'
    data = {'cowl_type': 'nose', 'cut_len': 0.06}
    path.write_text(json.dumps(data), encoding='utf-8')
    assert fv.read_param_json(str(path)) == data


# ------------------------------------------------------------
# relativize_scad_references
# ------------------------------------------------------------

def test_relativize_scad_references_rewrites_an_absolute_use_to_a_relative_one(tmp_path):
    target_dir = tmp_path / 'scad'
    target_dir.mkdir()
    included = tmp_path / 'included.scad'
    included.write_text('module x() {}\n', encoding='utf-8')
    scad_path = target_dir / 'main.scad'
    scad_path.write_text(f'use <{included}>;\n', encoding='utf-8')

    fv.relativize_scad_references(str(scad_path))

    text = scad_path.read_text(encoding='utf-8')
    assert 'use <../included.scad>;' in text
    assert str(included) not in text


def test_relativize_scad_references_leaves_an_already_relative_reference_untouched(tmp_path):
    scad_path = tmp_path / 'main.scad'
    original = 'use <lib/helper.scad>;\ninclude <../oml/mesh.stl>;\n'
    scad_path.write_text(original, encoding='utf-8')

    fv.relativize_scad_references(str(scad_path))

    assert scad_path.read_text(encoding='utf-8') == original


def test_relativize_scad_references_does_not_touch_the_file_when_nothing_changes(tmp_path):
    """Guards the `if rewritten != text` early-out: an unmodified file must not be
    rewritten, which would otherwise touch its mtime on every sweep re-run for no reason."""
    scad_path = tmp_path / 'main.scad'
    scad_path.write_text('use <lib/helper.scad>;\n', encoding='utf-8')
    before = scad_path.stat().st_mtime_ns

    fv.relativize_scad_references(str(scad_path))

    assert scad_path.stat().st_mtime_ns == before


# ------------------------------------------------------------
# Constant-group validators (_check_tolerance / _check_printer / _check_standard /
# _check_scaling / _check_slicing) and load_constants()
# ------------------------------------------------------------

def test_check_tolerance_accepts_negative_values_as_a_deliberate_interference_fit():
    """See the function's own docstring: a negative tolerance used to be refused as a sign
    error and is now a legitimate interference-fit choice -- nose_flange_tolerance is -0.1
    in the real design_constants.json."""
    fv._check_tolerance('x', -0.1, 'path')  # must not raise


def test_check_tolerance_rejects_a_non_number():
    with pytest.raises(ValueError):
        fv._check_tolerance('x', 'not a number', 'path')
    with pytest.raises(ValueError):
        fv._check_tolerance('x', True, 'path')  # bool is an int subclass, excluded on purpose


def test_check_printer_rejects_zero_and_negative():
    with pytest.raises(ValueError):
        fv._check_printer('extrusion_width', 0, 'path')
    with pytest.raises(ValueError):
        fv._check_printer('extrusion_width', -0.4, 'path')


def test_check_standard_rejects_zero_and_negative():
    with pytest.raises(ValueError):
        fv._check_standard('unit_width', 0, 'path')


def test_check_scaling_allows_zero_but_rejects_negative():
    fv._check_scaling('x', 0, 'path')  # must not raise
    with pytest.raises(ValueError):
        fv._check_scaling('x', -1, 'path')


def test_check_slicing_perimeters_must_be_a_whole_number_at_least_one():
    fv._check_slicing('cowl_n_perimeters', 2, 'path')  # must not raise
    with pytest.raises(ValueError):
        fv._check_slicing('cowl_n_perimeters', 1.5, 'path')
    with pytest.raises(ValueError):
        fv._check_slicing('cowl_n_perimeters', 0, 'path')


def test_check_slicing_overhang_angle_must_be_strictly_between_0_and_90():
    fv._check_slicing('overhang_angle_from_bed', 35, 'path')  # must not raise
    with pytest.raises(ValueError):
        fv._check_slicing('overhang_angle_from_bed', 0, 'path')
    with pytest.raises(ValueError):
        fv._check_slicing('overhang_angle_from_bed', 90, 'path')


def test_check_slicing_rejects_an_unrecognized_name():
    with pytest.raises(ValueError):
        fv._check_slicing('not_a_real_slicing_setting', 1, 'path')


def test_load_constants_reads_every_declared_name():
    """Exercised against the real, committed design_constants.json (already loaded once at
    import as fv._CONSTANTS) rather than a fixture, since a fixture cannot stand in for
    whether the real file agrees with CONSTANT_GROUPS."""
    out = fv.load_constants()
    for names in fv.CONSTANT_GROUPS.values():
        for name in names:
            assert name in out


def test_load_constants_refuses_a_missing_required_name(tmp_path):
    path = tmp_path / 'design_constants.json'
    doc = {group: {name: 1 for name in names}
           for group, names in fv.CONSTANT_GROUPS.items()}
    del doc['printer']['extrusion_width']
    path.write_text(json.dumps(doc), encoding='utf-8')
    with pytest.raises(ValueError, match='missing'):
        fv.load_constants(str(path))


def test_load_constants_refuses_an_unknown_name_in_a_group(tmp_path):
    path = tmp_path / 'design_constants.json'
    doc = {group: {name: 1 for name in names}
           for group, names in fv.CONSTANT_GROUPS.items()}
    doc['printer']['not_a_real_printer_setting'] = 1
    path.write_text(json.dumps(doc), encoding='utf-8')
    with pytest.raises(ValueError, match='unknown'):
        fv.load_constants(str(path))


# ------------------------------------------------------------
# axes / family_axes / family_combinations / family_is_valid / family_of --
# against the real, committed variant_param/ CSVs.
# ------------------------------------------------------------

def test_axes_resolves_against_param_dir_not_the_cwd():
    [path] = fv.axes('panel_variants.csv')
    assert path == fv.os.path.join(fv.PARAM_DIR, 'panel_variants.csv')


def test_family_axes_lists_shared_axes_around_the_familys_own_type_axis():
    paths = fv.family_axes('bulkhead')
    names = [fv.os.path.basename(p) for p in paths]
    assert names == ['panel_variants.csv', 'bulkhead_type_variants.csv',
                     'bulkhead_size_variants.csv']


def test_family_combinations_returns_real_rows_for_both_families():
    assert len(fv.family_combinations('bulkhead')) > 0
    assert len(fv.family_combinations('boom_bulkhead')) > 0


def test_family_is_valid_applies_every_check_the_family_declares():
    dp = _corner_ish_dp(panel_thickness=2.0, corner_radius=20.0)
    dp.bulkhead.type = fv.BulkheadType.COWLING
    # 'bulkhead' family only runs bulkhead_validity_check, which rejects this.
    assert fv.family_is_valid('bulkhead', dp) is False


def test_family_of_finds_a_real_bulkhead_type_name():
    assert fv.family_of('end_bolt') == 'bulkhead'
    assert fv.family_of('offset_single') == 'boom_bulkhead'


def test_family_of_returns_none_for_an_unknown_type_name():
    assert fv.family_of('not_a_real_bulkhead_type') is None


# ------------------------------------------------------------
# null_*_parameters constructors -- one dataclass factory per group. Individually trivial,
# so covered as one parametrized sweep rather than N near-identical tests: each must return
# a fresh instance of its declared type, and two calls must not share mutable state.
# ------------------------------------------------------------

_NULL_CONSTRUCTORS = [
    (fv.null_printer_settings, fv.PrinterSettings),
    (fv.null_parameters, fv.Parameters),
    (fv.null_corner_parameters, fv.CornerParameters),
    (fv.null_bulkhead_parameters, fv.BulkheadParameters),
    (fv.null_boom_bulkhead_parameters, fv.BoomBulkheadParameters),
    (fv.null_panel_parameters, fv.PanelParameters),
    (fv.null_longeron_parameters, fv.LongeronParameters),
    (fv.null_bolt_parameters, fv.BoltParameters),
    (fv.null_greeble_parameters, fv.GreebleParameters),
    (fv.null_plate_parameters, fv.PlateParameters),
    (fv.null_web_parameters, fv.WebParameters),
    (fv.null_bulkhead_flange_parameters, fv.BulkheadFlangeParameters),
    (fv.null_cowl_flange_parameters, fv.CowlFlangeParameters),
    (fv.null_nose_parameters, fv.NoseParameters),
    (fv.null_oml_parameters, fv.OmlParameters),
    (fv.null_nose_plate_parameters, fv.NosePlateParameters),
    (fv.null_nose_nose_parameters, fv.NoseTipParameters),
    (fv.null_buttress_full_parameters, fv.ButtressSet),
    (fv.null_buttress_parameter, fv.ButtressParameters),
]


@pytest.mark.parametrize('constructor,expected_type', _NULL_CONSTRUCTORS,
                         ids=[c.__name__ for c, _ in _NULL_CONSTRUCTORS])
def test_null_constructor_returns_a_fresh_instance_of_its_type(constructor, expected_type):
    a = constructor()
    b = constructor()
    assert isinstance(a, expected_type)
    assert a == b
    assert a is not b


# ------------------------------------------------------------
# Backend/resume/preview state: set_backend, _backend_for, set_resume, set_previews,
# set_render_queue. All mutate module globals, so every test restores them.
# ------------------------------------------------------------

@pytest.fixture
def restore_global_render_state():
    prev_backend = fv._BACKEND
    prev_resume = fv._RESUME
    prev_previews = fv._PREVIEWS
    prev_queue = fv._RENDER_QUEUE
    yield
    fv._BACKEND = prev_backend
    fv._RESUME = prev_resume
    fv._PREVIEWS = prev_previews
    fv._RENDER_QUEUE = prev_queue


def test_set_backend_returns_the_previous_value(restore_global_render_state):
    fv.set_backend('openscad')
    previous = fv.set_backend('freecad')
    assert previous == 'openscad'
    assert fv._BACKEND == 'freecad'


def test_set_backend_rejects_an_unknown_name(restore_global_render_state):
    with pytest.raises(ValueError):
        fv.set_backend('povray')


def test_backend_for_is_freecad_only_when_selected_ported_and_supported(
        restore_global_render_state):
    fv.set_backend('openscad')
    assert fv._backend_for('corner') == 'openscad'  # freecad not selected at all

    fv.set_backend('freecad')
    assert fv._backend_for('corner') == 'freecad'                    # ported, supported
    assert fv._backend_for('corner', supported=False) == 'openscad'  # this variant is not
    assert fv._backend_for('not_a_real_kind') == 'openscad'          # not ported at all


def test_set_resume_returns_previous_and_resets_counters(restore_global_render_state):
    fv._RESUME_COUNTS['skipped'] = 3
    fv._RESUME_COUNTS['changed'] = 2
    previous = fv.set_resume(True)
    assert previous is False
    assert fv._RESUME is True
    assert fv._RESUME_COUNTS == {'skipped': 0, 'changed': 0}


def test_set_previews_returns_previous_and_clears_the_backlog(restore_global_render_state):
    fv._PREVIEW_BACKLOG.append('some.stl')
    previous = fv.set_previews(False)
    assert previous is True
    assert fv._PREVIEWS is False
    assert fv._PREVIEW_BACKLOG == []


def test_set_render_queue_returns_the_previous_queue(restore_global_render_state):
    marker = object()
    fv._RENDER_QUEUE = marker
    previous = fv.set_render_queue('new-queue')
    assert previous is marker
    assert fv._RENDER_QUEUE == 'new-queue'


# ------------------------------------------------------------
# find_rendered_stls
# ------------------------------------------------------------

def test_find_rendered_stls_excludes_partial_files_and_sorts(tmp_path):
    sub = tmp_path / 'a'
    sub.mkdir()
    (sub / 'z.stl').write_bytes(b'x')
    (sub / 'a.stl').write_bytes(b'x')
    (sub / 'b.partial.stl').write_bytes(b'x')

    found = fv.find_rendered_stls(str(tmp_path))

    assert len(found) == 2
    assert all(not f.endswith('.partial.stl') for f in found)
    assert found == sorted(found)


# ------------------------------------------------------------
# render_worker_budget / default_render_workers
# ------------------------------------------------------------

def test_render_worker_budget_honors_the_env_override(monkeypatch):
    monkeypatch.setenv('FUSELAGE_RENDER_WORKERS', '3')
    workers, reason = fv.render_worker_budget()
    assert workers == 3
    assert reason == 'FUSELAGE_RENDER_WORKERS'


def test_render_worker_budget_floors_the_override_at_one(monkeypatch):
    monkeypatch.setenv('FUSELAGE_RENDER_WORKERS', '0')
    workers, _reason = fv.render_worker_budget()
    assert workers == 1


def test_default_render_workers_matches_the_budgets_worker_count(monkeypatch):
    monkeypatch.setenv('FUSELAGE_RENDER_WORKERS', '2')
    assert fv.default_render_workers() == 2


# ------------------------------------------------------------
# corner_parameters / _variant_note / cowl_parameters / _cowl_variant_note -- the flat
# alias->value mappings both backends are driven from.
# ------------------------------------------------------------

def test_corner_parameters_maps_the_dp_tree_by_name_and_omits_fx():
    dp = fv.derived_parameters(1.0, 2.0, _base_user_parameters(), fv.null_printer_settings(),
                                is_bulkhead=False)
    params = fv.corner_parameters(dp)
    assert params['U'] == dp.bulkhead.U
    assert params['unit_length'] == dp.corner.length
    assert params['corner_radius'] == dp.corner.radius
    assert params['extrusion_width'] == dp.printer.extrusion_width
    # FX is added by corner_render at its call site, not here -- fuselage_corner_geometry.scad
    # takes the finished unit_length, and adding FX here would make solid2's call a TypeError.
    assert 'FX' not in params


def test_variant_note_carries_type_name_because_two_types_share_the_same_24_numbers():
    dp = fv.derived_parameters(
        1.0, 1.0,
        _base_user_parameters(bulkhead_type_name='interconnect', is_end=False,
                              is_interconnect=True),
        fv.null_printer_settings(), is_bulkhead=True)
    note = fv._variant_note(dp)
    assert note == {'U': dp.bulkhead.U, 'panel_name': dp.panel.type_name,
                    'is_metric': True, 'type_name': 'interconnect'}


def test_cowl_variant_note_reads_the_nose_tree_not_the_bulkhead_one():
    dp = fv.null_nose_parameters()
    dp.U = 1.5
    dp.cowl_type = 'nose'
    dp.type_name = 'nose_round'
    assert fv._cowl_variant_note(dp) == {'U': 1.5, 'cowl_type': 'nose',
                                         'type_name': 'nose_round'}


def _cowl_dp():
    """A NoseParameters tree with distinctive, traceable values in every field
    cowl_parameters reads, so a wrong mapping (wrong key, wrong scaling, wrong source
    field) shows up as a wrong number rather than an accidental match."""
    dp = fv.null_nose_parameters()
    dp.U = 2.0
    dp.unit_width = 200.0
    dp.overhang_angle_from_bed = 35.0
    dp.cut_len = 12.0  # absolute mm; cowl_parameters must divide back by unit_width
    dp.oml.scale_m_per_mm = 0.001
    dp.oml.length_m = 0.05
    dp.oml.offset_x_m = -0.25
    dp.oml.reversed = True
    dp.buttress.cut_thickness = 0.1
    dp.buttress.z_offset = 4.0
    dp.buttress.r_inset = 13.2
    dp.buttress.top.r_start = 5.0
    dp.buttress.top.r_end = 13.2
    dp.buttress.top.z_end = 20.0
    dp.buttress.bottom.z_end = 21.0
    dp.buttress.bottom.r_start = 6.0
    dp.buttress.bottom.r_end = 14.0
    dp.buttress.side.z_end = 22.0
    dp.buttress.side.r_start = 7.0
    dp.buttress.side.r_end = 15.0
    dp.buttress.top_diag1.z_start = 8.0
    dp.buttress.top_diag1.depth = 3.0
    dp.nose.flange_height = 1.0
    dp.nose.flange_inset = 0.5
    dp.plate.diameter = 120.0
    dp.plate.thickness = 0.8
    dp.plate.tolerance = 0.1
    dp.plate.flange_height = 1.0
    dp.plate.flange_width = 2.0
    return dp


def test_cowl_parameters_nose_cowl_expresses_lengths_as_fractions_of_unit_width():
    dp = _cowl_dp()
    params = fv.cowl_parameters('nose_cowl', dp.U, dp)
    assert params['cut_len'] == pytest.approx(dp.cut_len / dp.unit_width)
    assert params['buttress_r_end'] == pytest.approx(dp.buttress.top.r_end / dp.unit_width)
    assert params['buttress_r_inset'] == pytest.approx(dp.buttress.r_inset / dp.unit_width)
    assert params['butt_angle'] == 0.0
    assert params['oml_reversed'] == 1.0


def test_cowl_parameters_shell_kinds_add_the_wall_in_absolute_millimeters():
    dp = _cowl_dp()
    plain = fv.cowl_parameters('nose_cowl', dp.U, dp)
    shelled = fv.cowl_parameters('nose_cowl_shell', dp.U, dp)
    assert shelled['cowl_n_perimeters'] == fv.COWL_N_PERIMETERS
    assert shelled['extrusion_width'] == fv.EXTRUSION_WIDTH_MM
    for key in plain:
        assert shelled[key] == plain[key]


def test_cowl_parameters_tail_carries_the_placement_angles_as_stated_constants():
    dp = _cowl_dp()
    params = fv.cowl_parameters('tail', dp.U, dp)
    assert params['side1_angle'] == 5.0
    assert params['side2_angle'] == 12.5
    assert params['side3_angle'] == 20.0
    assert params['top_diag_angle'] == 30.0
    assert params['side_r_end'] == pytest.approx(dp.buttress.side.r_end / dp.unit_width)


def test_cowl_parameters_nose_nose_keeps_printer_and_table_values_absolute_but_diameters_fractional():
    dp = _cowl_dp()
    params = fv.cowl_parameters('nose_nose', dp.U, dp)
    assert params['nose_flange_height'] == dp.nose.flange_height
    assert params['nose_flange_inset'] == dp.nose.flange_inset
    assert params['plate_thickness'] == dp.plate.thickness
    assert params['plate_diam'] == pytest.approx(dp.plate.diameter / dp.unit_width)
    assert params['cut_len'] == pytest.approx(dp.cut_len / dp.unit_width)


def test_cowl_parameters_nose_plate_takes_no_oml_and_every_dimension_absolute():
    dp = _cowl_dp()
    params = fv.cowl_parameters('nose_plate', dp.U, dp)
    assert 'oml_reversed' not in params
    assert params['plate_diam'] == dp.plate.diameter  # absolute here, unlike nose_nose above
    assert params['plate_flange_height'] == dp.plate.flange_height
    assert params['plate_flange_width'] == dp.plate.flange_width


def test_cowl_parameters_rejects_an_unknown_kind():
    dp = _cowl_dp()
    with pytest.raises(ValueError):
        fv.cowl_parameters('not_a_cowl_kind', dp.U, dp)


# ------------------------------------------------------------
# solid_render's freecad-backend refusal path, and render_definition's file-management
# contract -- atomic write, resume-skip, and "the renderer exited zero but lied" detection
# -- all driven through a fake RenderQueue so no real OpenSCAD/FreeCAD subprocess runs.
# ------------------------------------------------------------

_MINIMAL_ASCII_STL = (
    'solid test\n'
    'facet normal 0 0 1\n'
    'outer loop\n'
    'vertex 0 0 0\n'
    'vertex 1 0 0\n'
    'vertex 0 1 0\n'
    'endloop\n'
    'endfacet\n'
    'endsolid test\n'
)


class _RefusalRecordingQueue:
    """Fake queue for solid_render's freecad-backend refusal path: submit() must never
    be called, since a refusal means nothing was queued at all."""

    def __init__(self):
        self.refused = []

    def refuse(self, description):
        self.refused.append(description)

    def submit(self, cmd, on_success=None):
        raise AssertionError('submit() must not be called when the backend refuses')


def test_solid_render_refuses_rather_than_rendering_under_the_freecad_backend(
        restore_global_render_state):
    fv.set_backend('freecad')
    queue = _RefusalRecordingQueue()
    fv.set_render_queue(queue)

    result = fv.solid_render(object(), 'unused_output_dir', 'some/path/part.scad')

    assert result == ('some/path/part.scad', 'some/path/part.scad', 'some/path/part.scad')
    assert queue.refused == ['part.scad']


class _ImmediateQueue:
    """Fake queue standing in for RenderQueue.submit(): writes whatever render_definition
    asked make_command() to place (the mesh, and any sidecars), then runs on_success --
    exactly what a real renderer plus a workers=1 queue does, minus the subprocess.
    `write_stl`/`write_sidecars` simulate a renderer that exits zero without actually
    producing its output, which is the specific lie render_definition has to catch."""

    def __init__(self, write_stl=True, write_sidecars=True):
        self.write_stl = write_stl
        self.write_sidecars = write_sidecars

    def submit(self, cmd, on_success=None):
        stl_path, sidecar_paths = cmd
        if self.write_stl:
            Path(stl_path).write_text(_MINIMAL_ASCII_STL, encoding='ascii')
        if self.write_sidecars:
            for p in sidecar_paths:
                Path(p).write_text('fake fcstd', encoding='utf-8')
        if on_success is not None:
            on_success()


def _make_command(_definition_path, stl_path, sidecars):
    return (stl_path, list(sidecars.values()))


def test_render_definition_writes_the_definition_and_atomically_places_the_mesh(
        tmp_path, restore_global_render_state):
    fv.set_resume(False)
    fv.set_previews(False)
    fv.set_render_queue(_ImmediateQueue())

    definition_path, stl_path, _png_path = fv.render_definition(
        lambda path: Path(path).write_text('definition', encoding='utf-8'),
        '.stl.scad', _make_command, str(tmp_path), 'U_1.0/part.scad')

    assert Path(definition_path).read_text(encoding='utf-8') == 'definition'
    assert Path(stl_path).read_text(encoding='ascii') == _MINIMAL_ASCII_STL
    # Nothing left in the .partial state -- the whole point of the write-then-rename.
    assert not list(tmp_path.rglob('*.partial*'))


def test_render_definition_skips_an_unchanged_part_with_a_complete_mesh_on_resume(
        tmp_path, restore_global_render_state):
    fv.set_resume(False)
    fv.set_previews(False)
    fv.set_render_queue(_ImmediateQueue())

    def write_definition(path):
        Path(path).write_text('definition', encoding='utf-8')

    fv.render_definition(write_definition, '.stl.scad', _make_command, str(tmp_path),
                         'U_1.0/part.scad')

    fv.set_resume(True)

    def submit_must_not_be_called(cmd, on_success=None):
        raise AssertionError('a resumed, unchanged part must not be re-rendered')
    queue = _ImmediateQueue()
    queue.submit = submit_must_not_be_called
    fv.set_render_queue(queue)

    _definition_path, stl_path, _png_path = fv.render_definition(
        write_definition, '.stl.scad', _make_command, str(tmp_path), 'U_1.0/part.scad')

    assert Path(stl_path).is_file()
    assert fv._RESUME_COUNTS == {'skipped': 1, 'changed': 0}


def test_render_definition_raises_when_the_renderer_exits_zero_but_writes_no_mesh(
        tmp_path, restore_global_render_state):
    """freecadcmd's own documented failure mode (see render_definition's docstring): it
    exits 0 on an uncaught exception, so the mesh's presence -- not the exit code -- is
    what render_definition treats as success."""
    fv.set_resume(False)
    fv.set_previews(False)
    fv.set_render_queue(_ImmediateQueue(write_stl=False))

    with pytest.raises(fv.RenderFailed):
        fv.render_definition(lambda path: Path(path).write_text('d', encoding='utf-8'),
                             '.stl.scad', _make_command, str(tmp_path), 'part.scad')


def test_render_definition_raises_when_a_requested_sidecar_is_missing(
        tmp_path, restore_global_render_state):
    fv.set_resume(False)
    fv.set_previews(False)
    fv.set_render_queue(_ImmediateQueue(write_sidecars=False))

    with pytest.raises(fv.RenderFailed, match='FCStd'):
        fv.render_definition(lambda path: Path(path).write_text('d', encoding='utf-8'),
                             '.stl.json', _make_command, str(tmp_path), 'part.json',
                             sidecars=('.FCStd',))


# ------------------------------------------------------------
# _available_memory_bytes / stamp_geometry_version -- IP-TEST-2's second follow-up pass
# ------------------------------------------------------------

def test_available_memory_bytes_returns_a_plausible_figure_on_this_real_machine():
    """A real ctypes call on Windows (GlobalMemoryStatusEx), not mocked: the function's own
    contract is 'a real reading or None', so the meaningful check is that a real machine
    gives a real positive number, not an invented one."""
    available = fv._available_memory_bytes()
    assert available is None or (isinstance(available, int) and available > 0)


def test_stamp_geometry_version_prepends_a_header_comment_and_keeps_the_body(tmp_path):
    path = tmp_path / 'part.stl.scad'
    path.write_text('cube([1, 1, 1]);\n', encoding='utf-8')

    fv.stamp_geometry_version(str(path))

    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    assert lines[0].startswith('// geometry-version: ')
    assert text.endswith('cube([1, 1, 1]);\n')


def test_stamp_geometry_version_names_the_scad_modules_the_file_actually_uses(tmp_path):
    lib = tmp_path / 'helper.scad'
    lib.write_text('module helper() { cube(1); }\n', encoding='utf-8')
    part = tmp_path / 'part.stl.scad'
    part.write_text('use <helper.scad>\nhelper();\n', encoding='utf-8')

    fv.stamp_geometry_version(str(part))

    header = part.read_text(encoding='utf-8').splitlines()[0]
    assert 'helper.scad' in header


# ------------------------------------------------------------
# _write_preview / render_preview_batch / rebuild_previews -- real stl_preview rendering
# (pure numpy, no OpenSCAD/FreeCAD dependency, so these run for real rather than faked)
# ------------------------------------------------------------

def test_write_preview_renders_a_real_png_beside_the_stl(tmp_path, capsys):
    stl_path = tmp_path / 'part.stl'
    stl_path.write_text(_MINIMAL_ASCII_STL, encoding='ascii')
    png_path = tmp_path / 'part.png'

    fv._write_preview(str(stl_path), str(png_path))

    assert png_path.is_file()
    assert png_path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
    assert capsys.readouterr().err == ''


def test_write_preview_reports_a_failure_on_stderr_without_raising(tmp_path, capsys):
    stl_path = tmp_path / 'broken.stl'
    stl_path.write_text('not a real stl', encoding='ascii')
    png_path = tmp_path / 'broken.png'

    fv._write_preview(str(stl_path), str(png_path))   # must not raise

    assert not png_path.exists()
    assert 'preview failed for broken.stl' in capsys.readouterr().err


def test_render_preview_batch_with_no_paths_returns_immediately(monkeypatch):
    import stl_preview
    monkeypatch.setattr(stl_preview, 'render_one',
                        lambda job: (_ for _ in ()).throw(AssertionError('must not be called')))
    assert fv.render_preview_batch([]) == []


def test_render_preview_batch_renders_real_previews_with_a_real_process_pool(tmp_path):
    stl_path = tmp_path / 'part.stl'
    stl_path.write_text(_MINIMAL_ASCII_STL, encoding='ascii')

    failures = fv.render_preview_batch([str(stl_path)], workers=1, size=(16, 16))

    assert failures == []
    assert (tmp_path / 'part.png').is_file()


def test_render_preview_batch_reports_a_failure_for_one_bad_stl_among_good_ones(
        tmp_path, capsys):
    good = tmp_path / 'good.stl'
    good.write_text(_MINIMAL_ASCII_STL, encoding='ascii')
    bad = tmp_path / 'bad.stl'
    bad.write_text('not a real stl', encoding='ascii')

    failures = fv.render_preview_batch([str(good), str(bad)], workers=1, size=(16, 16))

    assert len(failures) == 1
    assert failures[0][0] == str(bad)
    assert (tmp_path / 'good.png').is_file()
    assert not (tmp_path / 'bad.png').exists()
    assert 'preview FAILED' in capsys.readouterr().out


def test_render_preview_batch_falls_back_to_serial_when_the_pool_is_broken(
        tmp_path, monkeypatch, capsys):
    """The documented Windows spawn/re-import failure mode: the pool context manager itself
    raises BrokenProcessPool, and the fallback must still produce every preview, serially,
    through the same stl_preview.render_one each job would have used."""
    stl_path = tmp_path / 'part.stl'
    stl_path.write_text(_MINIMAL_ASCII_STL, encoding='ascii')

    import concurrent.futures

    class _BrokenPool:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            raise concurrent.futures.process.BrokenProcessPool('synthetic pool break')

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(fv.concurrent.futures, 'ProcessPoolExecutor', _BrokenPool)

    failures = fv.render_preview_batch([str(stl_path)], workers=1, size=(16, 16))

    assert failures == []
    assert (tmp_path / 'part.png').is_file()
    assert 'preview pool broke -- falling back to serial' in capsys.readouterr().out


# ------------------------------------------------------------
# rebuild_previews -- orchestration only; render_preview_batch faked to bound cost
# ------------------------------------------------------------

def test_rebuild_previews_renders_only_stls_missing_a_png_by_default(
        tmp_path, monkeypatch, capsys):
    (tmp_path / 'has_png.stl').write_text(_MINIMAL_ASCII_STL, encoding='ascii')
    (tmp_path / 'has_png.png').write_bytes(b'existing')
    (tmp_path / 'missing_png.stl').write_text(_MINIMAL_ASCII_STL, encoding='ascii')

    calls = []
    monkeypatch.setattr(fv, 'render_preview_batch',
                        lambda paths, workers=None, **k: calls.append(list(paths)) or [])

    failures = fv.rebuild_previews(output_dir=str(tmp_path), workers=1)

    assert failures == []
    assert len(calls) == 1
    assert [Path(p).name for p in calls[0]] == ['missing_png.stl']
    assert '2 STL(s)' in capsys.readouterr().out


def test_rebuild_previews_force_redoes_every_stl_even_with_a_png_present(
        tmp_path, monkeypatch):
    (tmp_path / 'has_png.stl').write_text(_MINIMAL_ASCII_STL, encoding='ascii')
    (tmp_path / 'has_png.png').write_bytes(b'existing')

    calls = []
    monkeypatch.setattr(fv, 'render_preview_batch',
                        lambda paths, workers=None, **k: calls.append(list(paths)) or [])

    fv.rebuild_previews(output_dir=str(tmp_path), workers=1, force=True)

    assert len(calls[0]) == 1


def test_rebuild_previews_with_nothing_missing_never_calls_render_preview_batch(
        tmp_path, monkeypatch):
    (tmp_path / 'done.stl').write_text(_MINIMAL_ASCII_STL, encoding='ascii')
    (tmp_path / 'done.png').write_bytes(b'existing')

    monkeypatch.setattr(
        fv, 'render_preview_batch',
        lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not be called')))

    assert fv.rebuild_previews(output_dir=str(tmp_path), workers=1) == []


def test_rebuild_previews_defaults_to_the_module_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(fv, 'OUTPUT_DIR', str(tmp_path))
    (tmp_path / 'part.stl').write_text(_MINIMAL_ASCII_STL, encoding='ascii')

    calls = []
    monkeypatch.setattr(fv, 'render_preview_batch',
                        lambda paths, workers=None, **k: calls.append(list(paths)) or [])

    fv.rebuild_previews(workers=1)   # output_dir omitted
    assert len(calls) == 1


def test_rebuild_previews_reports_failures(tmp_path, monkeypatch, capsys):
    (tmp_path / 'part.stl').write_text(_MINIMAL_ASCII_STL, encoding='ascii')
    monkeypatch.setattr(fv, 'render_preview_batch',
                        lambda paths, workers=None, **k: [(paths[0], 'synthetic failure')])

    failures = fv.rebuild_previews(output_dir=str(tmp_path), workers=1)

    assert len(failures) == 1
    assert 'previews: 1 failed' in capsys.readouterr().out


# ------------------------------------------------------------
# RenderQueue -- its own thread-pool/retry/fail_fast mechanics, exercised with real
# subprocess commands (sys.executable one-liners: no OpenSCAD dependency needed to test
# the queue's own logic in isolation) rather than a fake, since a fake queue is exactly
# what IP-TEST-2's earlier passes already used to keep everything ELSE decoupled from this.
# ------------------------------------------------------------

def _ok_cmd():
    return [sys.executable, '-c', 'pass']


def _fail_cmd():
    return [sys.executable, '-c', 'import sys; sys.exit(1)']


def test_render_queue_submit_with_one_worker_runs_immediately_and_calls_on_success():
    calls = []
    q = fv.RenderQueue(workers=1)
    q.submit(_ok_cmd(), on_success=lambda: calls.append(1))
    assert calls == [1]
    assert q._done == 1


def test_render_queue_submit_with_one_worker_raises_directly_on_failure_uncaught():
    """A real, load-bearing asymmetry: with workers=1, submit() calls _run() inline with no
    try/except at all, so a failing job's CalledProcessError propagates straight out of
    submit() -- bypassing the retry, fail_fast and .failures machinery entirely. That
    machinery only exists on the drain() path (workers > 1)."""
    q = fv.RenderQueue(workers=1, fail_fast=False)
    with pytest.raises(subprocess.CalledProcessError):
        q.submit(_fail_cmd())
    assert q.failures == []


def test_render_queue_drains_automatically_once_the_chunk_size_is_reached():
    calls = []
    q = fv.RenderQueue(workers=2, chunk=2, progress_every=1000)
    q.submit(_ok_cmd(), on_success=lambda: calls.append('a'))
    assert q._pending  # not drained yet: chunk is 2, only one job submitted
    q.submit(_ok_cmd(), on_success=lambda: calls.append('b'))
    assert not q._pending  # the second submit crossed the chunk size and drained
    assert sorted(calls) == ['a', 'b']


def test_render_queue_drain_runs_every_pending_job_across_multiple_workers():
    calls = []
    q = fv.RenderQueue(workers=3, chunk=100, progress_every=1000)
    for i in range(5):
        q.submit(_ok_cmd(), on_success=lambda i=i: calls.append(i))
    assert len(q._pending) == 5
    q.drain()
    assert sorted(calls) == [0, 1, 2, 3, 4]
    assert q._done == 5
    assert q.failures == []


def test_render_queue_drain_with_fail_fast_true_raises_render_failed():
    q = fv.RenderQueue(workers=2, chunk=100, fail_fast=True, progress_every=1000)
    q.submit(_fail_cmd())
    q.submit(_ok_cmd())
    with pytest.raises(fv.RenderFailed, match='render.*failed'):
        q.drain()


def test_render_queue_drain_with_fail_fast_false_collects_the_failure_and_continues():
    q = fv.RenderQueue(workers=2, chunk=100, fail_fast=False, progress_every=1000)
    q.submit(_fail_cmd())
    q.submit(_ok_cmd())
    q.drain()   # must not raise
    assert len(q.failures) == 1
    assert q._done == 2


def test_render_queue_retries_a_failed_job_serially_and_reports_it_still_failing():
    q = fv.RenderQueue(workers=2, chunk=100, fail_fast=False, progress_every=1000)
    q.submit(_fail_cmd())
    q.drain()
    assert q._failed == 1
    assert q._recovered == 0
    assert len(q.failures) == 1


def test_render_queue_refuse_records_an_unported_part_as_a_failure():
    q = fv.RenderQueue(workers=1)
    q.refuse('some_unported_part.stl')
    assert len(q.failures) == 1
    (description, cmd), exc = q.failures[0]
    assert description == 'some_unported_part.stl'
    assert cmd is None
    assert isinstance(exc, fv.UnportedPart)
    assert q._refused == 1


def test_render_queue_refuse_does_not_raise_even_with_fail_fast_true(capsys):
    """A refusal is expected, catalogued porting debt, not a build failure -- fail_fast
    governs failed renders, not refusals, on purpose (see refuse()'s own docstring)."""
    q = fv.RenderQueue(workers=1, fail_fast=True)
    for i in range(3):
        q.refuse(f'part_{i}.stl')   # must not raise
    assert q._refused == 3
    assert 'REFUSED' in capsys.readouterr().err


def test_render_queue_refuse_stops_listing_individual_refusals_after_five(capsys):
    q = fv.RenderQueue(workers=1)
    for i in range(8):
        q.refuse(f'part_{i}.stl')
    err = capsys.readouterr().err
    assert err.count('REFUSED') == 5
    assert 'further refusals counted, not listed' in err
    assert q._refused == 8


def test_render_queue_as_context_manager_drains_on_clean_exit():
    calls = []
    with fv.RenderQueue(workers=2, chunk=100, progress_every=1000) as q:
        q.submit(_ok_cmd(), on_success=lambda: calls.append(1))
    assert calls == [1]


def test_render_queue_as_context_manager_does_not_drain_when_the_body_raises():
    q = fv.RenderQueue(workers=2, chunk=100, progress_every=1000)
    with pytest.raises(RuntimeError), q:
        q.submit(_ok_cmd())
        raise RuntimeError('synthetic failure inside the with-block')
    assert q._pending   # never drained: an abandoned run must not run its backlog


# ------------------------------------------------------------
# solid_render -- the real OpenSCAD subprocess branch. solid2's facet settings make even a
# genuine render of a trivial solid (a unit cube) fast (well under a second), so this is
# exercised for real rather than through a fake queue, the same "test the real thing when
# it's genuinely available" approach used for FreeCAD/OpenVSP elsewhere in this plan.
# ------------------------------------------------------------

def test_solid_render_openscad_backend_produces_a_real_correct_mesh(
        tmp_path, restore_global_render_state):
    import mesh_stats
    import solid2

    fv.set_backend('openscad')
    fv.set_resume(False)
    fv.set_previews(False)
    fv.set_render_queue(fv.RenderQueue(workers=1))

    scad_path, stl_path, png_path = fv.solid_render(
        solid2.cube([1, 1, 1]), str(tmp_path), 'testpart')

    assert Path(stl_path).is_file()
    stats = mesh_stats.mesh_stats(stl_path)
    assert stats['volume'] == pytest.approx(1.0, abs=1e-6)
    assert stats['triangles'] == 12
    assert not Path(png_path).exists()   # previews were off


def test_solid_render_writes_a_geometry_version_stamp_header(
        tmp_path, restore_global_render_state):
    import solid2

    fv.set_backend('openscad')
    fv.set_resume(False)
    fv.set_previews(False)
    fv.set_render_queue(fv.RenderQueue(workers=1))

    scad_path, _stl_path, _png_path = fv.solid_render(
        solid2.cube([2, 2, 2]), str(tmp_path), 'stamped')

    first_line = Path(scad_path).read_text(encoding='utf-8').splitlines()[0]
    assert first_line.startswith('// geometry-version: ')


def test_solid_render_openscad_backend_writes_a_preview_when_previews_are_on(
        tmp_path, restore_global_render_state):
    import solid2

    fv.set_backend('openscad')
    fv.set_resume(False)
    fv.set_previews(True)
    fv.set_render_queue(fv.RenderQueue(workers=1))

    _scad_path, _stl_path, png_path = fv.solid_render(
        solid2.cube([1, 1, 1]), str(tmp_path), 'withpreview')

    assert Path(png_path).is_file()
    assert Path(png_path).read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'


def test_solid_render_resume_skips_a_real_unchanged_render_on_the_second_call(
        tmp_path, restore_global_render_state):
    """End-to-end confirmation of the resume contract IP-TEST-2's earlier fake-queue tests
    already pin in isolation: a second real call with an identical definition and resume=True
    must not invoke OpenSCAD again."""
    import solid2

    fv.set_backend('openscad')
    fv.set_previews(False)

    fv.set_resume(False)
    fv.set_render_queue(fv.RenderQueue(workers=1))
    scad_obj = solid2.cube([1, 1, 1])
    _scad_path, stl_path, _png_path = fv.solid_render(scad_obj, str(tmp_path), 'resumeme')
    first_mtime = Path(stl_path).stat().st_mtime_ns

    fv.set_resume(True)

    def submit_must_not_be_called(cmd, on_success=None):
        raise AssertionError('a resumed, unchanged real render must not re-invoke OpenSCAD')
    queue = fv.RenderQueue(workers=1)
    queue.submit = submit_must_not_be_called
    fv.set_render_queue(queue)

    _scad_path2, stl_path2, _png_path2 = fv.solid_render(scad_obj, str(tmp_path), 'resumeme')

    assert stl_path2 == stl_path
    assert Path(stl_path).stat().st_mtime_ns == first_mtime
    assert fv._RESUME_COUNTS['skipped'] == 1


# ------------------------------------------------------------
# sweep_session / main -- top-level orchestration. A real run of _run_all_sweeps is the
# full parameter space (hundreds of parts per sweep) and must never run in this tier (see
# general.md's sweep-cost guidance); every test here fakes out the actual per-part
# rendering (solid_render, or _run_all_sweeps itself for main()) and checks the wiring
# around it -- queue/resume/preview state, the preview backfill, and the printed summary.
# ------------------------------------------------------------

def test_sweep_session_sets_and_restores_backend_adjacent_state(restore_global_render_state):
    fv.set_resume(False)
    fv.set_previews(False)
    outer_queue = fv.RenderQueue(workers=1)
    fv.set_render_queue(outer_queue)

    with fv.sweep_session(workers=1, resume=True, previews=False) as inner_queue:
        assert fv._RENDER_QUEUE is inner_queue
        assert inner_queue is not outer_queue
        assert fv._RESUME is True

    assert fv._RENDER_QUEUE is outer_queue
    assert fv._RESUME is False


def test_sweep_session_drains_its_queue_on_a_clean_exit():
    calls = []
    with fv.sweep_session(workers=2, resume=False, previews=False) as queue:
        queue.chunk = 100   # do not auto-drain before the with-block exits
        queue.submit(_ok_cmd(), on_success=lambda: calls.append(1))
    assert calls == [1]


def test_sweep_session_does_not_drain_when_the_body_raises(restore_global_render_state):
    holder = {}
    with pytest.raises(RuntimeError), fv.sweep_session(
            workers=2, resume=False, previews=False) as queue:
        holder['queue'] = queue
        queue.chunk = 100
        queue.submit(_ok_cmd())
        raise RuntimeError('synthetic failure inside the session')
    assert holder['queue']._pending   # abandoned, not drained


def test_sweep_session_prints_the_resume_summary_from_a_real_skip(
        tmp_path, capsys, restore_global_render_state):
    import solid2

    fv.set_backend('openscad')
    with fv.sweep_session(workers=1, resume=False, previews=False):
        fv.solid_render(solid2.cube([1, 1, 1]), str(tmp_path), 'sess_resume')

    with fv.sweep_session(workers=1, resume=True, previews=False):
        fv.solid_render(solid2.cube([1, 1, 1]), str(tmp_path), 'sess_resume')

    assert 'resume: skipped 1 unchanged part(s)' in capsys.readouterr().out


def test_sweep_session_backfills_previews_deferred_during_the_session(
        tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        fv, 'render_preview_batch',
        lambda backlog, workers=None: calls.append(list(backlog)) or [])

    stl_path = str(tmp_path / 'deferred.stl')
    with fv.sweep_session(workers=3, resume=False, previews=True) as queue:
        queue.chunk = 100
        fv._PREVIEW_BACKLOG.append(stl_path)   # what a real deferred render leaves behind

    assert calls == [[stl_path]]
    assert 'previews: backfilling 1 missing preview(s) across 3 process(es)' in \
        capsys.readouterr().out


def test_sweep_session_does_not_backfill_when_previews_are_off(monkeypatch):
    monkeypatch.setattr(
        fv, 'render_preview_batch',
        lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not be called')))
    with fv.sweep_session(workers=1, resume=False, previews=False) as queue:
        queue.chunk = 100
        fv._PREVIEW_BACKLOG.append('whatever.stl')
    # No assertion needed beyond "did not raise": previews=False means set_previews(False)
    # cleared the backlog on the way in and render_preview_batch is never reached.


def test_sweep_session_reports_preview_failures(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(fv, 'render_preview_batch',
                        lambda backlog, workers=None: [(backlog[0], 'synthetic failure')])
    with fv.sweep_session(workers=1, resume=False, previews=True) as queue:
        queue.chunk = 100
        fv._PREVIEW_BACKLOG.append(str(tmp_path / 'x.stl'))
    assert 'previews: 1 failed (the parts themselves are fine)' in capsys.readouterr().out


def test_main_defaults_output_dir_to_the_module_output_dir(monkeypatch, capsys):
    monkeypatch.setattr(fv, '_run_all_sweeps', lambda output_dir: None)
    fv.main(workers=1, resume=False, previews=False, backend='openscad')
    assert f'output: {fv.OUTPUT_DIR}' in capsys.readouterr().out


def test_main_resolves_a_relative_output_dir_to_an_absolute_path(monkeypatch, capsys, tmp_path):
    seen = {}
    monkeypatch.setattr(fv, '_run_all_sweeps', lambda output_dir: seen.setdefault('dir', output_dir))
    monkeypatch.chdir(tmp_path)
    fv.main(workers=1, resume=False, previews=False, backend='openscad', output_dir='relative_out')
    assert seen['dir'] == str(tmp_path / 'relative_out')
    assert seen['dir'] in capsys.readouterr().out


def test_main_restores_the_previous_backend_after_returning(
        monkeypatch, restore_global_render_state):
    fv.set_backend('openscad')
    monkeypatch.setattr(fv, '_run_all_sweeps', lambda output_dir: None)
    fv.main(workers=1, resume=False, previews=False, backend='freecad')
    assert fv._BACKEND == 'openscad'


def test_main_restores_the_previous_backend_even_if_the_sweep_raises(
        monkeypatch, restore_global_render_state):
    fv.set_backend('openscad')

    def boom(output_dir):
        raise RuntimeError('synthetic sweep failure')
    monkeypatch.setattr(fv, '_run_all_sweeps', boom)

    with pytest.raises(RuntimeError):
        fv.main(workers=1, resume=False, previews=False, backend='freecad')
    assert fv._BACKEND == 'openscad'


def test_main_prints_the_freecad_backend_banner_only_for_the_freecad_backend(
        monkeypatch, capsys, restore_global_render_state):
    monkeypatch.setattr(fv, '_run_all_sweeps', lambda output_dir: None)
    fv.main(workers=1, resume=False, previews=False, backend='freecad')
    out = capsys.readouterr().out
    assert 'backend: FreeCAD for' in out
    assert 'IP-FC-132' in out


def test_main_prints_the_openscad_backend_banner_for_the_default_backend(
        monkeypatch, capsys, restore_global_render_state):
    monkeypatch.setattr(fv, '_run_all_sweeps', lambda output_dir: None)
    fv.main(workers=1, resume=False, previews=False, backend='openscad')
    out = capsys.readouterr().out
    assert 'backend: OpenSCAD' in out
    assert 'backend: FreeCAD for' not in out


def test_main_prints_the_resume_note_only_when_resume_is_true(
        monkeypatch, capsys, restore_global_render_state):
    monkeypatch.setattr(fv, '_run_all_sweeps', lambda output_dir: None)
    fv.main(workers=1, resume=True, previews=False, backend='openscad')
    assert 'resume: skipping parts whose STL is already complete' in capsys.readouterr().out
