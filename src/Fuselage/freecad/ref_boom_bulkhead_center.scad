// IP-FC-12: the boom bulkhead at the SECOND boom type -- `center_single`, the one that
// sets `boom_make_lower_web`.
//
// ref_boom_bulkhead.scad is `offset_single`. Three assignments differ here and no others,
// all of them from `derived_parameters(1.0, 1.0, center_single, 3 mm)` rather than typed:
//
//     boom_z_position     25.0  ->  0.0     the boom sits on the centreline
//     boom_make_vert_web  true  ->  false
//     boom_make_lower_web false ->  true
//
// The lower web is the whole reason this file exists. `boom_bulkhead` evaluates
// `boom_web_outer_shape` and `boom_web_inner_shape` a second time at `-boom_z_position` and
// `180 - boom_key_angle`, mirrors each in y, and folds them into the same union and
// difference as the upper pair. Nothing in the FreeCAD port exercised that path, and one of
// the three swept boom types needs it.
//
// Modes 16 and 17 are TRANSCRIPTIONS, not module calls: the mirrored web has no module of
// its own in the source, it is written inline inside `boom_bulkhead`. They are here to
// localise a disagreement in the assembled part, and mode 9 -- which IS the real module --
// is what actually binds the port.
$fa=1;
$fs=0.1;

include <../scad/fuselage_boom_bulkhead_geometry.scad>

unit_width = 100.0;
corner_radius = 10.0;
panel_thickness = 3.0;
panel_offset = 1.5;
panel_overlap = 4.0;
panel_tolerance = 0.1;
longeron_radius = 2.0;
longeron_tolerance = 0.05;
bolt_hole_radius = 2.0;
bolt_offset = 8.0;
web_fillet_radius = 2.0;
web_width = 6.0;
boom_diameter = 8.0;
boom_bulkhead_thickness = 2.0;
boom_y_position = 0.0;
boom_z_position = 0.0;
boom_collet_thickness = 3.0;
boom_key_width = 2.0;
boom_key_height = 2.0;
boom_key_radius = 0.5;
boom_key_angle = 0.0;
boom_key_web_width = 6.0;
boom_tolerance = 0.2;
boom_make_vert_web = false;
boom_make_lower_web = true;

mode = 9;

if (mode == 9) {
    boom_bulkhead(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap,
        panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset,
        web_fillet_radius, web_width, boom_diameter, boom_bulkhead_thickness,
        boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width,
        boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width,
        boom_tolerance, boom_make_vert_web, boom_make_lower_web);
} else {
    linear_extrude(height = 1) {
        if (mode == 4) {
            boom_key_shape(boom_diameter, boom_y_position, boom_z_position,
                boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius,
                boom_key_angle, boom_tolerance);
        } else if (mode == 6) {
            boom_web_outer_shape(unit_width, corner_radius, panel_thickness,
                panel_tolerance, bolt_offset, web_fillet_radius, web_width, boom_diameter,
                boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width,
                boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width,
                boom_tolerance);
        } else if (mode == 7) {
            boom_web_inner_shape(unit_width, corner_radius, panel_thickness,
                panel_tolerance, bolt_offset, web_fillet_radius, web_width, boom_diameter,
                boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width,
                boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width,
                boom_tolerance, boom_make_vert_web);
        } else if (mode == 16) {
            // transcribed from boom_bulkhead -- the lower web's outer shape
            mirror([0,-1,0]) {
                boom_web_outer_shape(unit_width, corner_radius, panel_thickness,
                    panel_tolerance, bolt_offset, web_fillet_radius, web_width, boom_diameter,
                    boom_y_position, -boom_z_position, boom_collet_thickness, boom_key_width,
                    boom_key_height, boom_key_radius, 180-boom_key_angle, boom_key_web_width,
                    boom_tolerance);
            }
        } else if (mode == 17) {
            // transcribed from boom_bulkhead -- the lower web's inner shape
            mirror([0,-1,0]) {
                boom_web_inner_shape(unit_width, corner_radius, panel_thickness,
                    panel_tolerance, bolt_offset, web_fillet_radius, web_width, boom_diameter,
                    boom_y_position, -boom_z_position, boom_collet_thickness, boom_key_width,
                    boom_key_height, boom_key_radius, 180-boom_key_angle, boom_key_web_width,
                    boom_tolerance, boom_make_vert_web);
            }
        }
    }
}
