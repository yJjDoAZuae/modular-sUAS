// fuselage_corner -- the half-length run and its mirror about z = unit_length/2.
//
// At the SWEPT corner parameters, not the hand driver's. Note `greeble_tolerance` is 0.05
// here and absent from the bulkhead's table: the corner's bore carries the whole fit
// clearance and the bulkhead's post is nominal, because split across both halves the joint
// would take it twice. The corner and the bulkhead are separate variants in the sweep --
// `derived_parameters()` branches on is_bulkhead -- so this file's values come from the
// export's `corner_parameters` table, and reading them off a bulkhead variant would give
// the bore no clearance at all.
//
// Derived parameters for U=1.0 3/16in.
$fa=1;
$fs=0.1;

use <../scad/fuselage_corner_geometry.scad>

U = 1.0;
unit_length = 100.0;
bulkhead_thickness = 6;
corner_radius = 10.0;
panel_thickness = 4.7625;
panel_offset = 2.5;
panel_overlap = 4.7625;
panel_tolerance = 0.1;
longeron_radius = 2.0;
longeron_tolerance = 0.05;
greeble_thickness = 1.2;
greeble_nub_thickness = 1.2;
greeble_tolerance = 0.05;
extrusion_width = 0.6;

fuselage_corner(U, unit_length, bulkhead_thickness, corner_radius, panel_thickness,
                panel_offset, panel_overlap, panel_tolerance, longeron_radius,
                longeron_tolerance, greeble_thickness, greeble_nub_thickness,
                greeble_tolerance, extrusion_width);
