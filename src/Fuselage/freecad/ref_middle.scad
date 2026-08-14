// Isolate corner_middle at the driver's parameters, as the first porting milestone.
// The constant-section run is the 2D profile extruded, so matching its volume proves
// the profile before any of the greeble geometry is attempted.
$fa=1;
$fs=0.1;

use <../scad/fuselage_corner_geometry.scad>

U = 1.0;
FX = 1.0;
unit_length = 100*U*FX;
bulkhead_thickness = 6;
corner_radius = 10*U;
longeron_radius = 2*U;
panel_thickness = 4.77;
panel_offset = 0;
panel_overlap = 4;
panel_tolerance = 0.1;
longeron_tolerance = 0.05;
corner_tolerance = 0;
extrusion_width = 0.4;

corner_middle(unit_length, bulkhead_thickness, corner_radius, panel_thickness,
              panel_offset, panel_overlap, panel_tolerance, longeron_radius,
              longeron_tolerance, extrusion_width, corner_tolerance);
