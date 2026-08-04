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
greeble_thickness = 0.8;
greeble_nub_thickness = 0.8;
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

