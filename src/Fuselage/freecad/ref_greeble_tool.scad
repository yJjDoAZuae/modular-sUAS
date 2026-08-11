// The negative shape that forms the bulkhead's greeble post: corner_end called exactly as
// bulkhead_section() calls it. Two arguments differ from the corner's own end section and
// both matter:
//
//   * greeble_tolerance is a literal 0 -- the post is nominal by construction and all of
//     the fit clearance is taken on the corner's bore, because split across both halves the
//     joint would carry it twice;
//   * overshoot is eps, so the tool passes cleanly through the material it forms rather
//     than ending flush with it.
//
// The overshoot used to be bought by passing bulkhead_thickness + 2*eps and shifting the
// result down by eps, which also drove the rib height (bt/3) and the nub z levels from 6.02
// rather than 6.00 -- OQ-DES-B12, fixed 2026-08-11. The z extent is unchanged; the rib is
// now nominal. So "reuse the corner's end section" means re-evaluating the description at
// different arguments -- not referencing the corner's built shape, which carries the
// clearance.
//
// NOTE: these are the *hand driver's* values, matching fuselage_corner.scad, and they are
// deliberately not a sweep variant. This file exists to isolate one module so the FreeCAD
// port can be compared against it at identical inputs. To render a variant the sweep would
// actually produce, use tools/render_variant.py -- never -D overrides on a driver, because
// panel.offset and panel.overlap are derived and will not agree.
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

corner_end(U, bulkhead_thickness, corner_radius, panel_thickness,
           panel_offset, panel_overlap, panel_tolerance, longeron_radius,
           longeron_tolerance, greeble_thickness, greeble_nub_thickness, 0,
           extrusion_width, eps);
