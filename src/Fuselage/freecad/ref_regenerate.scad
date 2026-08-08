// fuselage_corner at a supplied U, for the regenerate comparison. Mirrors the driver
// exactly: only corner_radius, longeron_radius and unit_length scale with U; the
// thicknesses, overlaps and tolerances are user parameters that do not.
$fa=1;
$fs=0.1;

use <../scad/fuselage_corner_geometry.scad>

// supplied with -D: U, bulkhead_thickness, panel_thickness, panel_overlap
U = 1.0;
FX = 1.0;

panel_thickness = 4.77;
panel_tolerance = 0.1;
longeron_tolerance = 0.05;
greeble_thickness = 0.8;
greeble_nub_thickness = greeble_thickness;
greeble_tolerance = 0.05;
extrusion_width = 0.4;

corner_radius = 10*U;
longeron_radius = 2*U;
unit_length = 100*U*FX;

panel_overlap = 4;
bulkhead_thickness = 6;
panel_offset = 0;

fuselage_corner(U, unit_length, bulkhead_thickness, corner_radius, panel_thickness,
                panel_offset, panel_overlap, panel_tolerance, longeron_radius,
                longeron_tolerance, greeble_thickness, greeble_nub_thickness,
                greeble_tolerance, extrusion_width);
