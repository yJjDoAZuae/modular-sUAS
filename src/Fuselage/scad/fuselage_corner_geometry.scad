// mirror_xy() lives here. This file had no includes and open-coded that union three
// times; fuselage_bulkhead_geometry.scad already includes both files, so the module
// was always available there and only missing when corner geometry is used on its own
// -- which is exactly how the sweep uses it.
include <shape_modifier_utils.scad>

module fuselage_corner(U, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, nozzle_diameter) {


    union() {
    corner_middle(unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, nozzle_diameter);
    corner_transition(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, nozzle_diameter);
    corner_end(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, nozzle_diameter);
        translate([0,0,unit_length]) {
            mirror([0,0,1]) {
                union() {    
                    corner_middle(unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, nozzle_diameter);
                    corner_transition(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, nozzle_diameter);
                    corner_end(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, nozzle_diameter);
                }
            }
        }
    }
}


module corner_end(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, nozzle_diameter) {
    
    eps = 0.01;
    
    longeron_chamfer = nozzle_diameter;
    greeble_nub_height = bulkhead_thickness/3;
    greeble_radius = longeron_radius+longeron_tolerance+greeble_thickness+greeble_tolerance;
    greeble_nub_radius = longeron_radius+longeron_tolerance+greeble_thickness+greeble_nub_thickness+greeble_tolerance;
    
    difference() {
        linear_extrude(height=bulkhead_thickness+eps,center=false,convexity=3,twist=0,slices=1) {
            mirror_xy() {
                corner_middle_shape(corner_radius, panel_thickness, longeron_radius, panel_offset, panel_overlap, longeron_chamfer, longeron_tolerance, panel_tolerance);
            }
        }
    
        cylinder(h=3*bulkhead_thickness,r1=greeble_radius, r2=greeble_radius, center=true);
        
        rotate([0,0,45]){
            translate([-(greeble_radius),0,0]) {
                cube([2*(greeble_radius),2*(greeble_radius), 3*bulkhead_thickness], center = true);
            }
        }
        difference() {
            rotate_extrude(angle = 360, convexity = 2) {
                polygon(
                    [[0,0], 
                    [greeble_radius,0],
                    [greeble_radius,bulkhead_thickness/2 - greeble_nub_height/2-greeble_nub_thickness],
                    [greeble_nub_radius,bulkhead_thickness/2 - greeble_nub_height/2],
                    [greeble_nub_radius,bulkhead_thickness/2 + greeble_nub_height/2],
                    [greeble_radius,bulkhead_thickness/2 + greeble_nub_height/2+greeble_nub_thickness],
                    [greeble_radius,bulkhead_thickness,],
                    [0,bulkhead_thickness]] 
                );
            }
            rotate([0,0,-45]) {
                linear_extrude(height = 3*bulkhead_thickness, center=true, convexity=3,twist=0,slices=1) {
                    polygon(
                        [[-(greeble_nub_radius+eps),-(greeble_nub_radius)],
                        [greeble_nub_radius+eps,-greeble_nub_radius],
                        [greeble_nub_radius+eps,0],
                        [longeron_radius+greeble_thickness,-greeble_nub_thickness],
                        [-greeble_radius,-greeble_nub_thickness],
                    [-(greeble_nub_radius+eps),0],
                    ]
                    );
                }
            }
        }
        
    }
}

module corner_transition(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, nozzle_diameter) {
    
    eps = 0.01;
    
    longeron_chamfer = nozzle_diameter;
    greeble_nub_height = bulkhead_thickness/3;
    greeble_radius = longeron_radius+longeron_tolerance+greeble_thickness+greeble_tolerance;
    greeble_nub_radius = longeron_radius+longeron_tolerance+greeble_thickness+greeble_nub_thickness+greeble_tolerance;
    
    translate([0,0,1*bulkhead_thickness]) {
        
        difference() {
        
            linear_extrude(height=bulkhead_thickness,center=false,convexity=3,twist=0,slices=1) {

                mirror_xy() {
                    corner_middle_shape(corner_radius, panel_thickness, longeron_radius, panel_offset, panel_overlap, longeron_chamfer, longeron_tolerance, panel_tolerance);
                }
            }
            
            translate([0,0,-eps]) {
                cylinder(h = bulkhead_thickness+2*eps,r1=greeble_radius,
                    r2=longeron_radius+longeron_tolerance,center=false);
                rotate([0,0,-45]) {
                    
                    rotate([90,0,0]) {
                    
                    linear_extrude(height = longeron_radius+greeble_thickness+greeble_tolerance, center=false,convexity=3,twist=0,slices=1,scale=1.0) {
                        polygon([
                        [greeble_radius,-eps],
                        [longeron_radius+longeron_tolerance,0.75*bulkhead_thickness+eps],
                        [longeron_radius/sqrt(2),bulkhead_thickness+eps],
                        [-longeron_radius/sqrt(2),bulkhead_thickness+eps],
                        [-(longeron_radius+longeron_tolerance),0.75*bulkhead_thickness+eps],
                        [-(greeble_radius),-eps],
                        ]);
                    }
                }
                    
                }
                
            }
        }
    }
}


module corner_middle(unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, nozzle_diameter) {
    
    eps = 0.01;
    longeron_chamfer = nozzle_diameter;
    
    translate([0,0,2*bulkhead_thickness-eps]) {
        linear_extrude(height=unit_length/2-2*bulkhead_thickness+2*eps,center=false,convexity=3,twist=0,slices=1) {

            mirror_xy() {
                corner_middle_shape(corner_radius, panel_thickness, longeron_radius, panel_offset, panel_overlap, longeron_chamfer, longeron_tolerance, panel_tolerance);
            }
        }
    }
}

module corner_middle_shape(corner_radius, panel_thickness, longeron_radius, panel_offset, panel_overlap, longeron_chamfer, longeron_tolerance, panel_tolerance) {

    // use longeron_chamfer as a minimum and ensure panel_overlap is at least the specified dimension
    flat_offset = -max(longeron_radius + longeron_tolerance + longeron_chamfer, (panel_overlap+panel_offset)-(corner_radius-panel_thickness-panel_tolerance));
    flat_x = -(panel_overlap+panel_offset);
    flat_y = flat_offset - flat_x;

    difference(){
        union(){
            circle(corner_radius);
            
            // rectangular extension
            translate([-(panel_overlap+panel_offset-panel_tolerance),0,0]) {
                square(size = [panel_overlap+panel_offset-panel_tolerance,corner_radius], center = false);
            }
        }
        union() {
            circle(longeron_radius+longeron_tolerance);
            
            // panel cutout
            translate([-2*panel_overlap-panel_offset+panel_tolerance,corner_radius-panel_thickness-panel_tolerance,0]) {
                square(size = [2*panel_overlap,2*panel_thickness+2*panel_tolerance], center = false);
            }
            
            // bulkhead boundary
            polygon(points = [
            [flat_x,corner_radius],  // top inner edge of the panel interface
            [flat_x,flat_y],
            [flat_offset,0],
            [0,flat_offset],
            [flat_y,flat_x],
            [0,-2*corner_radius],
            [-2*corner_radius,-2*corner_radius],
            [-2*corner_radius,2*corner_radius]]);
            
            // diagonal mirror line mask
            polygon(points = [[-2*corner_radius,-2*corner_radius],[2*corner_radius,2*corner_radius],[2*corner_radius,-2*corner_radius]]);
            
            // longeron chamfer
            polygon(points = [[0,0.0],[-2*corner_radius,0.0],[-2*corner_radius,-2*corner_radius],[0,-2*corner_radius]]);
            
        }

    }
}

