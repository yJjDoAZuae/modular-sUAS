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
    # `max_panel_thickness` is SI (IP-FC-160) and `fuselage_variants` is the exempt OpenSCAD
    # path, so the input crosses in and the expectation crosses out. **The tolerance crosses
    # too:** 1e-9 mm is 1e-12 m, and leaving it at 1e-9 would have loosened this assertion by
    # a factor of 1000 while still reading as tight.
    got_m = v.max_panel_thickness(U, extrusion_width=fv.EXTRUSION_WIDTH_MM / 1000.0,
                                  greeble_wall_extrusions=fv.GREEBLE_WALL_EXTRUSIONS)
    want_m = _real_ceiling(U) / 1000.0
    assert got_m == pytest.approx(want_m, abs=1e-12)


def test_panel_overlap_matches_fuselage_variants_own_rule() -> None:
    # Meters: the 4 mm floor is 0.004, and the samples straddle it as before.
    for pt in (0.0, 0.002, 0.0035, 0.004, 0.00477, 0.010):
        assert v.panel_overlap(pt) == max(pt, 0.004)


def test_table_bulkhead_thicknesses_match_the_real_variant_csv() -> None:
    """The docstring's own claim: bulkhead_thickness here comes from
    bulkhead_size_variants.csv, not a fixed constant -- cross-checked against the real file
    rather than trusted as a hand-copied literal."""
    import csv
    csv_path = (Path(__file__).resolve().parent.parent / 'src' / 'Fuselage' / 'variant_param'
               / 'bulkhead_size_variants.csv')
    with open(csv_path, newline='') as f:
        rows = {float(r['U']): float(r['bulkhead_thickness']) for r in csv.DictReader(f)}
    # The CSV belongs to the OpenSCAD sweep and is millimeters; the table is SI.
    for u, bulkhead_thickness_m, _panel_thickness in v.TABLE_M:
        assert rows[u] == pytest.approx(bulkhead_thickness_m * 1000.0), (
            'variants.TABLE_M bulkhead_thickness for U=%s (%s m) does not match '
            'bulkhead_size_variants.csv (%s mm)'
            % (u, bulkhead_thickness_m, rows[u]))


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
    # The floor is U * 1 mm, which is U * 0.001 m.
    for u, _bulkhead_thickness, panel_thickness_m in v.TABLE_M:
        floor_m = u * 0.001
        assert panel_thickness_m >= floor_m, (
            'U=%s panel_thickness=%s m is below the real floor %s m'
            % (u, panel_thickness_m, floor_m))
