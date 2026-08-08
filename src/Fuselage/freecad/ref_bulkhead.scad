// The bulkhead at the driver's parameters, as the reference the port is measured against.
// The driver ships with draft settings ($fa=15, $fs=0.5); publish settings are used here so
// the tessellation bias is the same order as the corner references and the comparison
// tolerances mean the same thing.
$fa=1;
$fs=0.1;

use <../scad/fuselage_bulkhead_geometry.scad>

U = 1.0;
DTF_thickness = 4.77;

extrusion_width = 0.4;
layer_height = 0.2;

is_interconnect = false;
is_cowling = false;
bulkhead_thickness = 6;
panel_thickness = DTF_thickness;
panel_offset = 0;
panel_overlap = 4;
panel_tolerance = 0.1;
longeron_tolerance = 0.05;
bolt_hole_radius = 5.33/2;
bolt_thickness = 3;
greeble_opening_angle = 35;
greeble_thickness = 0.8;
greeble_nub_thickness = greeble_thickness;
plate_thickness = 4*layer_height;
web_fillet_radius = 2;
web_width = 3;
flange_fillet_radius = 2;
flange_thickness = 2*extrusion_width;
flange_chamfer = 1;
cowl_flange_height = 0;
cowl_flange_tolerance = 0;

unit_width = 100*U;
corner_radius = 10*U;
longeron_radius = 2*U;
bolt_offset = 8*U;

bulkhead_section_full(is_interconnect, is_cowling, unit_width, bulkhead_thickness,
                      corner_radius, panel_thickness, panel_offset, panel_overlap,
                      panel_tolerance, longeron_radius, longeron_tolerance,
                      bolt_hole_radius, bolt_thickness, bolt_offset,
                      greeble_opening_angle, greeble_thickness, greeble_nub_thickness,
                      plate_thickness, web_fillet_radius, web_width,
                      flange_fillet_radius, flange_thickness, flange_chamfer,
                      cowl_flange_height, cowl_flange_tolerance, extrusion_width);
