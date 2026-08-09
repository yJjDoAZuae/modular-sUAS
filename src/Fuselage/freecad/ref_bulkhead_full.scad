// bulkhead_section_full -- the octant translated to its corner and tiled eight ways.
//
// Derived parameters for U=1.0 end_bolt 3/16in, the same set ref_bulkhead_section.scad uses.
$fa=1;
$fs=0.05;

use <../scad/fuselage_bulkhead_geometry.scad>

is_interconnect = false;
is_cowling = false;
unit_width = 100.0;
bulkhead_thickness = 6;
corner_radius = 10.0;
panel_thickness = 4.7625;
panel_offset = 2.5;
panel_overlap = 4.7625;
panel_tolerance = 0.1;
longeron_radius = 2.0;
longeron_tolerance = 0.05;
bolt_hole_radius = 2.0;
bolt_thickness = 3.0;
bolt_offset = 8.0;
greeble_opening_angle = 35.0;
greeble_thickness = 1.2;
greeble_nub_thickness = 1.2;
plate_thickness = 0.8;
web_fillet_radius = 2.0;
web_width = 3.0;
flange_fillet_radius = 2.0;
flange_thickness = 1.2;
flange_chamfer = 1.0;
cowl_flange_height = 0.0;         // unused at is_cowling = false, but the sweep's value
cowl_flange_tolerance = 0.0;
extrusion_width = 0.6;

bulkhead_section_full(is_interconnect, is_cowling, unit_width, bulkhead_thickness,
                      corner_radius, panel_thickness, panel_offset, panel_overlap,
                      panel_tolerance, longeron_radius, longeron_tolerance,
                      bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle,
                      greeble_thickness, greeble_nub_thickness, plate_thickness,
                      web_fillet_radius, web_width, flange_fillet_radius, flange_thickness,
                      flange_chamfer, cowl_flange_height, cowl_flange_tolerance,
                      extrusion_width);
