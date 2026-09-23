"""IP-TEST-11: tests for freecad/variants.py, the regenerate test's parameter table.

Lives under src/Fuselage/freecad/ by location but -- like sheet_naming.py -- has no FreeCAD
import, so it is fully testable from the pytest tier. It had no test at all before this: its
`max_panel_thickness()` claims in its own docstring to restate fuselage_variants.py's real
validity ceiling, but nothing ever checked that the restatement stayed correct, and it had
drifted -- `greeble_thickness`/`greeble_nub_thickness` were hardcoded at a fixed 0.8 mm rather
than scaling with `sqrt(U)` the way the real formula does, wrong at every U except the one
value where the fixed default happened to coincide (fixed 2026-09-23). Nothing in the
repository calls `max_panel_thickness()` today (checked by grep), which is exactly how the
drift went unnoticed; this test is what keeps a future caller from inheriting it silently.
"""
import math
import sys
from pathlib import Path

import fuselage_variants as fv
import pytest

_FREECAD_DIR = str(Path(__file__).resolve().parent.parent / 'src' / 'Fuselage' / 'freecad')
if _FREECAD_DIR not in sys.path:
    sys.path.insert(0, _FREECAD_DIR)

import variants as v  # noqa: E402


def _real_ceiling(U: float) -> float:
    """fuselage_variants.derived_parameters()'s actual formula, computed independently of
    variants.max_panel_thickness() so this test does not just check the function against
    itself."""
    greeble_thickness = max(
        fv.GREEBLE_WALL_EXTRUSIONS * math.sqrt(U) * fv.EXTRUSION_WIDTH_MM,
        fv.GREEBLE_WALL_EXTRUSIONS * fv.EXTRUSION_WIDTH_MM)
    greeble_nub_thickness = fv.greeble_nub_thickness_of(greeble_thickness)
    corner_radius = fv.CORNER_RADIUS_MM * U
    longeron_radius = fv.LONGERON_RADIUS_MM * U
    return corner_radius - (longeron_radius + fv.LONGERON_TOLERANCE_MM
                            + greeble_thickness + greeble_nub_thickness)


@pytest.mark.parametrize('U', [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0])
def test_max_panel_thickness_matches_the_real_validity_ceiling(U: float) -> None:
    got = v.max_panel_thickness(U, extrusion_width=fv.EXTRUSION_WIDTH_MM,
                                greeble_wall_extrusions=fv.GREEBLE_WALL_EXTRUSIONS)
    want = _real_ceiling(U)
    assert got == pytest.approx(want, abs=1e-9)


def test_panel_overlap_matches_fuselage_variants_own_rule() -> None:
    for pt in (0.0, 2.0, 3.5, 4.0, 4.77, 10.0):
        assert v.panel_overlap(pt) == max(pt, 4.0)


def test_table_bulkhead_thicknesses_match_the_real_variant_csv() -> None:
    """The docstring's own claim: bulkhead_thickness here comes from
    bulkhead_size_variants.csv, not a fixed constant -- cross-checked against the real file
    rather than trusted as a hand-copied literal."""
    import csv
    csv_path = (Path(__file__).resolve().parent.parent / 'src' / 'Fuselage' / 'variant_param'
               / 'bulkhead_size_variants.csv')
    with open(csv_path, newline='') as f:
        rows = {float(r['U']): float(r['bulkhead_thickness']) for r in csv.DictReader(f)}
    for u, bulkhead_thickness, _panel_thickness in v.TABLE:
        assert rows[u] == bulkhead_thickness, (
            'variants.TABLE bulkhead_thickness for U=%s (%s) does not match '
            'bulkhead_size_variants.csv (%s)' % (u, bulkhead_thickness, rows[u]))


def test_table_panel_thicknesses_meet_the_real_validity_floor() -> None:
    """The floor (fuselage_variants.py's bulkhead_min_panel_thickness_parametric, U*1) is a
    real, load-bearing constraint every entry must meet. The ceiling is deliberately not
    asserted here: TABLE's own U=0.5 row (panel_thickness=2.0) sits above the corrected
    ceiling (1.55 mm, see max_panel_thickness's own docstring) even though it is comfortably
    below the *un*-corrected one this module used to compute (2.35 mm) -- so the value was
    plausibly picked against the wrong formula and never re-validated. Left as-is rather than
    changed here: check_regenerate.py already builds and reproduces this exact configuration
    successfully against real geometry, TABLE's purpose is reproducibility (its own name),
    not sweep-legality, and changing it would mean re-rendering the committed reference STL
    -- a real geometry decision, not a test-coverage one. See doc/implementation/
    test_coverage.md, IP-TEST-11 for the finding."""
    for u, _bulkhead_thickness, panel_thickness in v.TABLE:
        floor = u * 1.0
        assert panel_thickness >= floor, (
            'U=%s panel_thickness=%s is below the real floor %s' % (u, panel_thickness, floor))
