// bulkhead_flange_positive as a whole, at the same parameters its constituents were checked
// at one by one. This is the reference that binds ref_flange_boss.scad's transcription of
// the inline quadrant block: that file only proves the port matches the transcription, this
// one goes through the real module.
//
// Derived parameters for U=1.0 end_bolt 3/16in.
$fa=1;
$fs=0.05;

use <../scad/fuselage_bulkhead_geometry.scad>

make_web = true;
is_interconnect = false;
is_cowling = false;
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
flange_fillet_radius = 2.0;
flange_thickness = 1.2;
flange_chamfer = 1.0;

bulkhead_flange_positive(make_web, is_interconnect, is_cowling, unit_width,
                         bulkhead_thickness, corner_radius, panel_thickness, panel_offset,
                         panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness,
                         bolt_offset, plate_thickness, flange_fillet_radius,
                         flange_thickness, flange_chamfer);
