// The negative shape that forms the bulkhead's greeble post: corner_end called exactly as
// bulkhead_section() calls it. Two arguments differ from the corner's own end section and
// both matter:
//
//   * greeble_tolerance is a literal 0 -- the post is nominal by construction and all of
//     the fit clearance is taken on the corner's bore, because split across both halves the
//     joint would carry it twice;
//   * bulkhead_thickness is bt + 2*eps, so the rib height (bt/3) and the nub z levels are
//     computed from 6.02 rather than 6.00.
//
// The whole shape is then shifted down by eps to clean up the bottom of the cutout. So
// "reuse the corner's end section" means re-evaluating the description at different
// arguments -- not referencing the corner's built shape, which carries the clearance.
$fa=1;
$fs=0.1;

use <../scad/fuselage_corner_geometry.scad>

U = 1.0;
eps = 0.01;                       // geometry_eps()
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
extrusion_width = 0.4;

translate([0, 0, -eps]) {
    corner_end(U, bulkhead_thickness + 2*eps, corner_radius, panel_thickness,
               panel_offset, panel_overlap, panel_tolerance, longeron_radius,
               longeron_tolerance, greeble_thickness, greeble_nub_thickness, 0,
               extrusion_width);
}
