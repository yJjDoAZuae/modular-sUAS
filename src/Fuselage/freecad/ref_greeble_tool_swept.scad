// ref_greeble_tool.scad at the SWEPT parameter set instead of the hand driver's.
//
// The corner's port was only ever compared against corner_end at fuselage_corner.scad's
// values. bulkhead_section evaluates the same description at the sweep's -- greeble_thickness
// 1.2 rather than 0.8, panel_offset 2.5 rather than 0, extrusion_width 0.6 rather than 0.4 --
// and a port that agrees at one configuration and not another is exactly what seeding the
// sheet from derived_parameters() is meant to catch.
//
// Derived parameters for U=1.0 end_bolt 3/16in.
$fa=1;
$fs=0.1;

use <../scad/fuselage_corner_geometry.scad>

U = 1.0;
eps = 0.01;                       // geometry_eps()
bulkhead_thickness = 6;
corner_radius = 10.0;
longeron_radius = 2.0;
panel_thickness = 4.7625;
panel_offset = 2.5;
panel_overlap = 4.7625;
panel_tolerance = 0.1;
longeron_tolerance = 0.05;
greeble_thickness = 1.2;
greeble_nub_thickness = 1.2;
extrusion_width = 0.6;

translate([0, 0, -eps]) {
    corner_end(U, bulkhead_thickness + 2*eps, corner_radius, panel_thickness,
               panel_offset, panel_overlap, panel_tolerance, longeron_radius,
               longeron_tolerance, greeble_thickness, greeble_nub_thickness, 0,
               extrusion_width);
}
