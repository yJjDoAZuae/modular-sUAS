
use <fuselage_geometry.scad>

// draft settings
$fa=15;
$fs=0.5;
// publish settings
//$fa=1;
//$fs=0.1;


// FX -- the bay length multiplier -- is deliberately absent. It scales unit_length,
// which only the corner uses, so the same bulkhead serves every bay length. This driver
// used to set FX = 0.5 while fuselage_bulkhead.scad set FX = 1, and the two produced
// identically shaped bulkheads: the clearest demonstration that it never mattered.
U = 1;

DTF_thickness = 4.77;

// User parameters
is_interconnect = false;
is_cowling = true;

bulkhead_thickness = 6;

panel_thickness = 0;
panel_overlap = 4;
panel_offset = 0;
panel_tolerance = 0.0;

longeron_tolerance = 0.05;

//bolt_hole_radius=4.3/2;
bolt_hole_radius=5.33/2;
bolt_thickness=2;

greeble_opening_angle = 35;
// Derived from the seat wall, not chosen separately -- see greeble_nub_thickness_of()
// in fuselage_variants.py. Keep them equal unless that formula changes.
greeble_thickness = 0.8;
greeble_nub_thickness = greeble_thickness;
// No greeble tolerance here: the bulkhead's greeble post is nominal by
// construction and the corner's bore carries the clearance.

web_fillet_radius=2;
web_width=3;

flange_fillet_radius=2;
flange_chamfer=1;

cowl_flange_height=2;
cowl_flange_tolerance=0.2;

extrusion_width = 0.4;
layer_height=0.2;

// These are based on the standard, don't change these
corner_radius = 10*U;
longeron_radius = 2*U+0.15;
// No unit_length here: a bulkhead is independent of bay length.
unit_width=100*U;
bolt_offset=8*U;
flange_thickness=3*extrusion_width;
plate_thickness=4*layer_height;

bulkhead_section_full(is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width);
