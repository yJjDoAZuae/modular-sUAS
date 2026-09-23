"""IP-TEST-3 (doc/implementation/test_coverage.md): unit tests for fillet_intent.py.

Covers the module's pure geometry: `point_to_line_45`, `derived`, and all four tangency-
claim functions (`outer_corner_fillet`, `greeble_to_web_fillet`, `web_to_bolt_fillet`,
`bolt_flange_fillet`). Each takes and returns plain numbers/dicts -- no FreeCAD, no
subprocess -- so the claims are checked against a real `d` built from the same pipeline
the module's own `main()` uses (`derived_parameters` -> `bulkhead_parameters` -> `derived`),
just for one hand-picked configuration rather than the whole swept corpus. Not covered:
`variants()` (a thin filter over `fv.family_is_valid`, already exercised indirectly by
building the real `dp` below) and `main()` (CLI/subprocess-shaped: calls
`export_parameters.main()` and shells out per variant -- out of scope for this pass).

Adoption-phase retrofit (general.md's TDD section). The module's own docstring states the
claim under test precisely: each fillet's center is the stated pair of tangencies written
out as arithmetic, to within EPSILON (1e-9 mm) -- these tests hold every fillet function to
that same bound rather than a looser one, so a regression that only partly breaks a formula
(and lands inside a sloppier tolerance) does not slip past coverage that exists to catch
exactly this.
"""
import math

import fillet_intent as fi
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


def _fillet_inputs(U=1.0):
    """A real `derived()` dict, built the same way fillet_intent.main() builds one per
    variant: derive the bulkhead, flatten it to the parameter dict both backends share,
    then add fillet_intent's own derived quantities (flange_inner_x, bolt_c, etc.)."""
    dp = fv.derived_parameters(U, 1.0, _user_parameters(), fv.null_printer_settings(),
                               is_bulkhead=True)
    return fi.derived(fv.bulkhead_parameters(dp))


# ------------------------------------------------------------
# point_to_line_45
# ------------------------------------------------------------

def test_point_to_line_45_is_zero_on_the_line():
    assert fi.point_to_line_45(3.0, 3.0, 0.0, 0.0) == pytest.approx(0.0)
    assert fi.point_to_line_45(5.0, 7.0, 2.0, 4.0) == pytest.approx(0.0)


def test_point_to_line_45_sign_matches_the_upper_left_side():
    """Positive on the upper-left side, per the function's own docstring: for the line
    y = x through the origin, a point straight up (0, 1) is on the upper-left side."""
    assert fi.point_to_line_45(0.0, 1.0, 0.0, 0.0) > 0
    assert fi.point_to_line_45(1.0, 0.0, 0.0, 0.0) < 0


def test_point_to_line_45_magnitude_is_the_true_perpendicular_distance():
    # (1, 0) is distance 1/sqrt(2) from the line y=x.
    assert fi.point_to_line_45(1.0, 0.0, 0.0, 0.0) == pytest.approx(-1.0 / math.sqrt(2))


# ------------------------------------------------------------
# derived
# ------------------------------------------------------------

def test_derived_adds_the_five_fillet_quantities_without_losing_the_input_keys():
    p = dict(panel_tolerance=0.1, panel_offset=2.0, panel_overlap=0.5,
             flange_thickness=1.2, corner_radius=20.0, panel_thickness=1.0,
             bolt_offset=8.0, bolt_hole_radius=1.5, bolt_thickness=0.6,
             flange_fillet_radius=0.8, unrelated_key='kept')

    d = fi.derived(p)

    assert d['unrelated_key'] == 'kept'  # derived() copies, does not replace, the input
    assert d['flange_inner_x'] == pytest.approx(-(0.1 + 2.0 + 0.5 + 1.2))
    assert d['flange_y'] == pytest.approx(20.0 - 1.0 - 0.1 - 1.2)
    assert d['bolt_c'] == pytest.approx(-8.0)
    assert d['bolt_boss_r'] == pytest.approx(1.5 + 0.6)
    assert d['r_bolt_fillet'] == pytest.approx(0.8 + 1.5 + 0.6)


def test_derived_does_not_mutate_its_input():
    p = dict(panel_tolerance=0.1, panel_offset=2.0, panel_overlap=0.5,
             flange_thickness=1.2, corner_radius=20.0, panel_thickness=1.0,
             bolt_offset=8.0, bolt_hole_radius=1.5, bolt_thickness=0.6,
             flange_fillet_radius=0.8)
    before = dict(p)
    fi.derived(p)
    assert p == before


# ------------------------------------------------------------
# The four tangency-claim functions, against a real derived() dict. Each claim must hold
# to the module's own stated bound (EPSILON, 1e-9 mm) -- not merely "close".
# ------------------------------------------------------------

def test_outer_corner_fillet_tangencies_hold_to_epsilon():
    d = _fillet_inputs(U=1.0)
    for _claim, residual in fi.outer_corner_fillet(d):
        assert abs(residual) <= fi.EPSILON


def test_bolt_flange_fillet_tangencies_hold_to_epsilon():
    d = _fillet_inputs(U=1.0)
    for _claim, residual in fi.bolt_flange_fillet(d):
        assert abs(residual) <= fi.EPSILON


def test_web_to_bolt_fillet_tangencies_hold_to_epsilon():
    d = _fillet_inputs(U=1.0)
    for _claim, residual in fi.web_to_bolt_fillet(d):
        assert abs(residual) <= fi.EPSILON


def test_greeble_to_web_fillet_tangencies_hold_to_epsilon_where_the_corner_exists():
    d = _fillet_inputs(U=1.0)
    assert d['flange_inner_x'] >= d['bolt_c']  # this U has the corner -- see the test below
    claims = fi.greeble_to_web_fillet(d)
    assert len(claims) == 2
    for _claim, residual in claims:
        assert abs(residual) <= fi.EPSILON


def test_greeble_to_web_fillet_returns_nothing_where_the_web_has_no_corner():
    """OQ-ARCH-14: 27 of 148 variants have flange_inner_x < bolt_c, every one at U <= 1.0 --
    the model builds no body there, so there is no tangency to state. U=0.5 reproduces it."""
    d = _fillet_inputs(U=0.5)
    assert d['flange_inner_x'] < d['bolt_c']
    assert fi.greeble_to_web_fillet(d) == []


def test_bolt_flange_fillet_reports_unsatisfiable_when_no_circle_touches_both():
    """The other branch of bolt_flange_fillet: constructed directly (not from a real dp,
    since the real corpus never reaches it -- OQ-DES-B14 found every swept combination
    satisfiable) by placing the bolt center too far from the flange face for any circle of
    the given radius to reach both."""
    d = dict(flange_inner_x=-10.0, flange_fillet_radius=1.0, bolt_c=-1000.0,
             bolt_boss_r=1.5)
    [(claim, residual)] = fi.bolt_flange_fillet(d)
    assert claim.startswith('unsatisfiable')
    assert math.isnan(residual)
