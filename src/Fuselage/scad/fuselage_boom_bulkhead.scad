
use <fuselage_geometry.scad>

// draft settings
$fa=15;
$fs=0.5;
// publish settings
//$fa=1;
//$fs=0.1;

FX = 1;
U = 1;

DTF_thickness = 4.77;

// TODO:
//   Boom key orientation
//   External booms

// These are based on the standard, don't change these
corner_radius = 10*U;
longeron_radius = 2*U;
unit_length=100*U*FX;
unit_width=100*U;
bolt_offset=8*U;
boom_diameter=8*U;
boom_bulkhead_thickness=2*U;

// printer settings
extrusion_width = 0.4;

// User parameters

panel_thickness = DTF_thickness;
panel_offset = 0;
panel_overlap = 4;
panel_tolerance = 0.1;

longeron_tolerance = 0.05;

bolt_hole_radius=4.3/2;


web_fillet_radius=2;
web_width=6;

boom_tolerance = 0.2;
boom_collet_thickness = 3;
boom_key_width = 2;
boom_key_height = 2;
boom_key_radius = 0.5;
boom_key_angle = 0;
boom_key_web_width = 6;

// derived boom positions
boom_z_position = 0.25*unit_width;
boom_y_position = 0.0*unit_width;
boom_make_vert_web = true;
boom_make_lower_web = false;

//boom_web_inner_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_fillet_radius, web_width,boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width, boom_tolerance, boom_make_vert_web);

//boom_web_outer_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_fillet_radius, web_width,boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width, boom_tolerance);

boom_bulkhead(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset, web_fillet_radius, web_width, boom_diameter, boom_bulkhead_thickness, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width, boom_tolerance, boom_make_vert_web, boom_make_lower_web);


