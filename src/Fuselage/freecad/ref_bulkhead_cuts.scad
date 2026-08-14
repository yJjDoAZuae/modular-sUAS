// The four geometric cut tools of bulkhead_section, as their union -- the longeron opening
// wedge, the outer-face cleanup, the longeron and bolt holes, and the octant mask. The fifth
// cut, the greeble-forming corner_end, is a real module and is checked by bulkhead_tree.py.
//
// Like ref_flange_boss.scad this is a TRANSCRIPTION: bulkhead_section builds these inline,
// so there is nothing to `use`, and on its own this file only proves the port matches the
// transcription. The binding check is the assembled bulkhead_section, which goes through the
// real module.
//
// Derived parameters for U=1.0 end_bolt 3/16in, is_cowling = false, is_interconnect = false.
$fa=1;
$fs=0.05;

use <../scad/shape_modifier_utils.scad>

unit_width = 100.0;
bulkhead_thickness = 6;
corner_radius = 10.0;
panel_thickness = 4.7625;
panel_offset = 2.5;
panel_overlap = 4.7625;
panel_tolerance = 0.1;
longeron_radius = 2.0;
longeron_tolerance = 0.05;
bolt_hole_radius = 2.0;
bolt_offset = 8.0;
greeble_opening_angle = 35;

eps = geometry_eps();

union() {

    // longeron opening cutout
    linear_extrude(height=through_cut(bulkhead_thickness), center=true, convexity=3,twist=0,slices=1,scale=1){
        polygon([[0,0],[sin(45-greeble_opening_angle)*corner_radius,cos(45-greeble_opening_angle)*corner_radius],[cos(45-greeble_opening_angle)*corner_radius,sin(45-greeble_opening_angle)*corner_radius]]);
    }

    // clean up the outer faces of the corner cutout
    linear_extrude(height=through_cut(bulkhead_thickness), center=true, convexity=5,twist=0,slices=1,scale=1){
        difference() {
            polygon([
                [0,0],
                [mask_reach(corner_radius),mask_reach(corner_radius)],
                [-(panel_offset+panel_overlap),mask_reach(corner_radius)],
                [-(panel_offset+panel_overlap),corner_radius-(panel_thickness+panel_tolerance)],
                [0,corner_radius-(panel_thickness+panel_tolerance)]
                ]);
            circle(r=corner_radius-(panel_thickness+panel_tolerance));
        }
    }

    // longeron hole
    cylinder(h=through_cut(bulkhead_thickness), r=longeron_radius+longeron_tolerance, center=true);

    // bolt hole
    translate([-bolt_offset,-bolt_offset,0]){
        cylinder(h=through_cut(bulkhead_thickness), r=bolt_hole_radius, center=true);
    }

    linear_extrude(height=through_cut(bulkhead_thickness), center=true, convexity=5,twist=0,slices=1,scale=1) {
        octant_mask(unit_width, corner_radius);
    }
}
