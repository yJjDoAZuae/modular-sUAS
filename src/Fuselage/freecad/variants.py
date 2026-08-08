"""The regenerate test's parameter table, taken from the real variant tables.

bulkhead_thickness is tabulated per U in bulkhead_size_variants.csv -- it does not scale
with U and it is not the driver's fixed 6. panel_thickness must satisfy the validity check
in fuselage_variants.py:

    U * 1 <= panel_thickness
          <= corner_radius - (longeron_radius + longeron_tolerance
                              + greeble_thickness + greeble_nub_thickness)

At U=0.5 that ceiling is 2.35 mm, so the driver's 4.77 mm DTF sheet is not a legal panel
for the smallest corner and the sweep never generates that combination. panel.overlap is
max(panel_thickness, 4), as fuselage_variants.py computes it.
"""

# U -> (bulkhead_thickness, panel_thickness)
TABLE = [
    (0.5, 4.0, 2.0),
    (1.0, 6.0, 4.77),
    (2.0, 8.0, 4.77),
    (4.0, 16.0, 4.77),
]


def panel_overlap(panel_thickness):
    return max(panel_thickness, 4.0)


def max_panel_thickness(U, longeron_tolerance=0.05, greeble_thickness=0.8,
                        greeble_nub_thickness=0.8):
    """fuselage_variants.py's upper bound on a legal panel."""
    return (10.0 * U) - (2.0 * U + longeron_tolerance + greeble_thickness
                         + greeble_nub_thickness)
