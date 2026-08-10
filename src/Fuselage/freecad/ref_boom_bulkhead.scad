// IP-FC-12: the boom bulkhead and its sub-shapes, isolated for the port.
//
// At the derived parameters for U=1.0 boom offset_single 3mm panel -- one of 132 valid
// swept variants, not the hand driver's values.
//
// The 2D shapes are extruded 1 mm so the reported volume is the area; mode 9 is the real
// part, already extruded to boom_bulkhead_thickness.
//
// **This part is built almost entirely from morphological offsets**, which is what makes it
// unlike the frame bulkhead. `fillet_inner`/`fillet_outer` appear four times and plain
// `offset(r=)` five more, and three of the four fillet uses wrap a whole compound region
// rather than a named corner. Which construction the port uses for them is OQ-DES-B11, open.
// These values are the reference under any of its alternatives -- they say what the shape is,
// not how FreeCAD should reach it.
//
// The offset degeneracy that ref_offset2d.scad documents cannot arise from the web here:
// web_width = 6U and web_fillet_radius = 2U across all 132 variants, so the ratio is a
// constant 1.5 and never the 1.0 that puts a limb exactly two radii wide.
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
boom_z_position = 25.0;
boom_collet_thickness = 3.0;
boom_key_width = 2.0;
boom_key_height = 2.0;
boom_key_radius = 0.5;
boom_key_angle = 0.0;
boom_key_web_width = 6.0;
boom_tolerance = 0.2;
boom_make_vert_web = true;
boom_make_lower_web = false;

mode = 9;

module centerline() {
    upper_boom_support_centerline_shape(unit_width, corner_radius, panel_thickness,
        panel_tolerance, bolt_offset, web_width, boom_diameter, boom_y_position,
        boom_z_position, boom_collet_thickness);
}

module key() {
    boom_key_shape(boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness,
        boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_tolerance);
}

if (mode == 9) {
    boom_bulkhead(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap,
        panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset,
        web_fillet_radius, web_width, boom_diameter, boom_bulkhead_thickness,
        boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width,
        boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width,
        boom_tolerance, boom_make_vert_web, boom_make_lower_web);
} else {
    linear_extrude(height = 1) {
        if (mode == 0) {
            // the seven-vertex spine the web is strokes of; no offsets yet
            centerline();
        } else if (mode == 1) {
            // mirror_x of it, which is what both web shapes actually offset
            mirror_x() { centerline(); }
        } else if (mode == 2) {
            // the stroke: offset(+web_width/2) gives a limb web_width wide
            offset(r = web_width / 2) { mirror_x() { centerline(); } }
        } else if (mode == 3) {
            // the erosion the inner web starts from
            offset(r = -web_width / 2) { mirror_x() { centerline(); } }
        } else if (mode == 4) {
            // fillet_outer(r) fillet_inner(r) over a circle unioned with a square --
            // the one place here that is unambiguously a corner round
            key();
        } else if (mode == 5) {
            offset(r = boom_key_web_width) { key(); }
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
        } else if (mode == 8) {
            // the OML the part is cut from, shared with the frame bulkhead
            bulkhead_oml_shape(unit_width, corner_radius, panel_thickness, panel_offset,
                panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance,
                bolt_hole_radius, bolt_offset);
        }
    }
}
