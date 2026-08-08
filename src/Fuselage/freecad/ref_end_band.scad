// One axial band of corner_end, so the comparison can be localised in z rather than
// resting on a single total. The bands are the ones the snap groove is defined by:
// bore, lower ramp, groove, upper ramp, bore.
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

// supplied with -D
z0 = 0;
z1 = 6.01;

intersection() {
    corner_end(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset,
               panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance,
               greeble_thickness, greeble_nub_thickness, greeble_tolerance,
               extrusion_width);
    translate([-50, -50, z0]) cube([100, 100, z1 - z0]);
}
