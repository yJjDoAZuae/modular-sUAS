// Isolate corner_transition at the driver's parameters. It carries its own translate, so
// it lands at z = bulkhead_thickness .. 2*bulkhead_thickness without help.
$fa=1;
$fs=0.1;

use <../scad/fuselage_corner_geometry.scad>

U = 1.0;
bulkhead_thickness = 6;
corner_radius = 10*U;
longeron_radius = 2*U;
panel_thickness = 4.77;
panel_offset = 0;
panel_overlap = 4;
panel_tolerance = 0.1;
longeron_tolerance = 0.05;
greeble_thickness = 0.8;
greeble_nub_thickness = greeble_thickness;
greeble_tolerance = 0.05;
extrusion_width = 0.4;

corner_transition(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset,
                  panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance,
                  greeble_thickness, greeble_nub_thickness, greeble_tolerance,
                  extrusion_width);
