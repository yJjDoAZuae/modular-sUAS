use <fuselage_bulkhead_geometry.scad>

// draft settings
$fa=15;
$fs=0.5;
// publish settings
//$fa=1;
//$fs=0.1;

// FX -- the bay length multiplier -- is deliberately absent. It scales unit_length,
// which only the corner uses, so the same bulkhead serves every bay length.
U = 1.0;

DTF_thickness = 4.77;

// printer settings
extrusion_width = 0.4;
layer_height=0.2;

// User parameters
is_interconnect = false;
is_cowling = false;
bulkhead_thickness = 6;
panel_thickness = DTF_thickness;
panel_offset = 0;
panel_overlap = 4;
panel_tolerance = 0.1;
longeron_tolerance = 0.05;
//bolt_hole_radius=4.3/2;
bolt_hole_radius=5.33/2;
bolt_thickness=3;
greeble_opening_angle = 35;
// Derived from the seat wall, not chosen separately -- see greeble_nub_thickness_of()
// in fuselage_variants.py. Keep them equal unless that formula changes.
greeble_thickness = 0.8;
greeble_nub_thickness = greeble_thickness;
// No greeble tolerance here: the bulkhead's greeble post is nominal by
// construction and the corner's bore carries the clearance.
plate_thickness=4*layer_height;
web_fillet_radius=2;
web_width=3;
flange_fillet_radius=2;
flange_thickness=2*extrusion_width;
flange_chamfer=1;
cowl_flange_height=0;
cowl_flange_tolerance=0;
cowl_n_perimeters=1;   // the COWL's perimeter count; the flange leaves room for its wall (OQ-DES-CW9)

// These are based on the standard, don't change these
unit_width=100*U;
// No unit_length here: a bulkhead is independent of bay length.
corner_radius = 10*U;
longeron_radius = 2*U;
bolt_offset=8*U;

bulkhead_section_full(is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width, cowl_n_perimeters);

//if (U==2) {
//    
//    // 2U parameters
//    panel_overlap = 6;
//    bulkhead_thickness = 8;
//    panel_offset = 0;
//    web_width=6;
//    web_fillet_radius=6;
//    flange_chamfer=2;
//    flange_fillet_radius=4;
//    flange_thickness=4*extrusion_width;
//    plate_thickness=8*layer_height;
//
//    bulkhead_section_full();
//
//} else if (U==1.5) {
//
//    // 1.5U parameters
//
//    panel_overlap = 4;
//    bulkhead_thickness = 6;
//    panel_offset = 0;
//    web_width=4;
//    web_fillet_radius=4;
//    flange_chamfer=1.5;
//    flange_fillet_radius=3;
//    flange_thickness=3*extrusion_width;
//    plate_thickness=5*layer_height;
//
//    bulkhead_section_full();
//
//} else if (U==1.0) {
//    
//    panel_overlap = 4;
//    bulkhead_thickness = 6;
//    panel_offset = 0;
//    web_width=3;
//    web_fillet_radius=2;
//    flange_chamfer=1.0;
//    flange_fillet_radius=2;
//    flange_thickness=2*extrusion_width;
//    plate_thickness=4*layer_height;
//
//    bulkhead_section_full();
//}

