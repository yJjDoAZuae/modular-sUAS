// bulkhead_web isolated, at the derived parameters for U=1.0 end_bolt 3/16in.
//
// Note this web's fillet is already a TRUE fillet -- the module subtracts a cylinder of
// web_fillet_radius at the re-entrant corner. It is not the morphological fillet_inner that
// OQ-DES-B9 is about; that one appears in bulkhead_web_inner_shape_octant, which this
// non-interconnect path does not use.
$fa=1;
$fs=0.05;

use <../scad/fuselage_bulkhead_geometry.scad>

is_interconnect = false;
unit_width = 100.0;
bulkhead_thickness = 6;
corner_radius = 10.0;
panel_thickness = 4.7625;
panel_offset = 2.5;
panel_overlap = 4.7625;
panel_tolerance = 0.1;
bolt_hole_radius = 2.0;
bolt_thickness = 3.0;
bolt_offset = 8.0;
plate_thickness = 0.8;
web_fillet_radius = 2.0;
web_width = 3.0;
flange_thickness = 1.2;

bulkhead_web(is_interconnect, unit_width, bulkhead_thickness, corner_radius,
             panel_thickness, panel_offset, panel_overlap, panel_tolerance,
             bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness,
             web_fillet_radius, web_width, flange_thickness);
