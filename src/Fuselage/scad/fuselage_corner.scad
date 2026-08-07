$fa=1;
$fs=0.1;

use <fuselage_geometry.scad>

FX = 1.0;
U = 1.0;

DTF_thickness = 4.77;

// User parameters
panel_thickness = DTF_thickness;
panel_tolerance = 0.1;
longeron_tolerance = 0.05;
// The corner carries all of the greeble fit clearance -- this tolerance opens out
// the corner's bore. The bulkhead's greeble post is cut at nominal size. See
// bulkhead_section() in fuselage_bulkhead_geometry.scad.
// One wall thickness, stated twice. The rib thickness is derived from the seat wall by
// greeble_nub_thickness_of() in fuselage_variants.py -- identity today -- and the sweep
// can never make them disagree. This driver sets them by hand, so keep them equal
// unless that formula changes.
greeble_thickness = 0.8;
greeble_nub_thickness = greeble_thickness;
greeble_tolerance = 0.05;
nozzle_diameter = 0.4;

// These are based on the standard, don't change these
corner_radius = 10*U;
longeron_radius = 2*U;
unit_length=100*U*FX;

// 1.0U parameters
panel_overlap = 4;
bulkhead_thickness = 6;
panel_offset = 0;


fuselage_corner(U, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, nozzle_diameter);

