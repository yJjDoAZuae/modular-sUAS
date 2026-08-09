// Three of bulkhead_flange_positive's constituent modules, isolated one at a time so the
// port can be checked against each rather than against their union.
//
// Derived parameters for U=1.0 end_bolt 3/16in.
//
//   which = 0  outer_corner_fillet
//   which = 1  bulkhead_flange_chamfer
//   which = 2  greeble_to_web_fillet
//
// All three are the same shape of thing: a small block of material at a corner, minus a
// stepped stack of a cylinder, a cone and a cylinder. The step is the chamfer, and the
// result is a true fillet -- these are not the morphological fillet_inner.
$fa=1;
$fs=0.05;

use <../scad/fuselage_bulkhead_geometry.scad>

make_web = true;
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
flange_fillet_radius = 2.0;
flange_thickness = 1.2;
flange_chamfer = 1.0;

which = 0;

if (which == 0) {
    outer_corner_fillet(make_web, bulkhead_thickness, corner_radius, panel_thickness,
                        panel_offset, panel_overlap, panel_tolerance, plate_thickness,
                        flange_fillet_radius, flange_thickness, flange_chamfer);
} else if (which == 1) {
    bulkhead_flange_chamfer(is_interconnect, unit_width, corner_radius, panel_thickness,
                            panel_offset, panel_overlap, panel_tolerance, bolt_offset,
                            plate_thickness, flange_thickness, flange_chamfer);
} else if (which == 2) {
    greeble_to_web_fillet(bulkhead_thickness, panel_offset, panel_overlap, panel_tolerance,
                          bolt_offset, plate_thickness, flange_fillet_radius,
                          flange_thickness, flange_chamfer);
}
