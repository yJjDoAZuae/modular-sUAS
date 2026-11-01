"""The regenerate test's parameter table, taken from the real variant tables.

bulkhead_thickness is tabulated per U in bulkhead_size_variants.csv -- it does not scale
with U and it is not the driver's fixed 6. panel_thickness must satisfy the validity check
in fuselage_variants.py:

    U * 1 <= panel_thickness
          <= corner_radius - (longeron_radius + longeron_tolerance
                              + greeble_thickness + greeble_nub_thickness)

At U=0.5 that ceiling is 1.55 mm, so the driver's 4.77 mm DTF sheet is not a legal panel
for the smallest corner and the sweep never generates that combination. panel.overlap is
max(panel_thickness, 4), as fuselage_variants.py computes it.
"""

# U -> (bulkhead_thickness, panel_thickness). `U` is dimensionless; both thicknesses
# are **meters**, with the millimeter figure beside each row.
TABLE_M = [
    (0.5, 0.004, 0.002),                 # 4.0 mm, 2.0 mm
    (1.0, 0.006, 0.00477),               # 6.0 mm, 4.77 mm
    (2.0, 0.008, 0.00477),               # 8.0 mm, 4.77 mm
    (4.0, 0.016, 0.00477),               # 16.0 mm, 4.77 mm
]


def panel_overlap(panel_thickness):
    """`max(panel_thickness, 4 mm)`, as fuselage_variants.py computes it. Meters."""
    return max(panel_thickness, 0.004)


def max_panel_thickness(U, longeron_tolerance=0.00005, extrusion_width=0.0006,
                        greeble_wall_extrusions=2.0):
    """fuselage_variants.py's upper bound on a legal panel.

    **Corrected 2026-09-23** (IP-TEST-11): this used to take `greeble_thickness` and
    `greeble_nub_thickness` as fixed 0.8 mm defaults, restating a number instead of the
    formula that produces it. The real one scales with `sqrt(U)` and floors at two
    extrusion widths (`fuselage_variants.derived_parameters`'s own comment: "the greeble
    wall is a printed feature sized to survive a snap fit, so it scales in extrusions
    rather than as a fraction of the airframe"), so the fixed default was wrong at every
    `U` except the one value where `2*sqrt(U) == 2` -- silently, since nothing in the
    repository calls this function today (confirmed by grep) and so nothing had ever
    compared it against the real ceiling. `greeble_nub_thickness_of()` is the identity
    function on the real side today, restated as `== greeble_thickness` here rather than
    imported, since this module deliberately carries no FreeCAD or tools/ import.
    """
    greeble_thickness = max(greeble_wall_extrusions * (U ** 0.5) * extrusion_width,
                            greeble_wall_extrusions * extrusion_width)
    greeble_nub_thickness = greeble_thickness
    return (0.010 * U) - (0.002 * U + longeron_tolerance + greeble_thickness
                          + greeble_nub_thickness)
