include <shape_modifier_utils.scad>
include <fuselage_bulkhead_geometry.scad>

module upper_boom_support_centerline_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_width, boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness) {
    
    polygon([
//        [0, boom_z_position-boom_diameter/2-boom_collet_thickness],
//        [boom_y_position, boom_z_position-boom_diameter/2-boom_collet_thickness],
        [0, boom_z_position],
        [boom_y_position, boom_z_position],
        [unit_width/2-corner_radius-bolt_offset, unit_width/2-corner_radius-bolt_offset],
        [unit_width/2-corner_radius, unit_width/2-corner_radius],
        [unit_width/2-corner_radius, unit_width/2-panel_thickness-web_width/2-panel_tolerance],
        [0, unit_width/2-panel_thickness-web_width/2-panel_tolerance],
        [0, unit_width/2-corner_radius],
    ]);
}

module boom_bulkhead(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset, web_fillet_radius, web_width, boom_diameter, boom_bulkhead_thickness, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width, boom_tolerance, boom_make_vert_web, boom_make_lower_web) {
        
    linear_extrude(boom_bulkhead_thickness, center=false, convexity=5, twist=0, slices=1, scale=1.0) {
        difference() {
            
            bulkhead_oml_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);


            fillet_inner(web_fillet_radius) {
                difference() {

                    bulkhead_oml_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);

                    difference() {
                        union() {
            
                            difference() {
                                bulkhead_oml_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);
                                
                                bulkhead_web_inner_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset, web_fillet_radius, web_width);
                            }

                            difference() {
                                
                                union() {
                                boom_web_outer_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_fillet_radius, web_width,boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width, boom_tolerance);
                                    
                                    if (boom_make_lower_web) {
                                        
                                        mirror([0,-1,0]) {
                                        boom_web_outer_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_fillet_radius, web_width,boom_diameter, boom_y_position, -boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, 180-boom_key_angle, boom_key_web_width, boom_tolerance);
                                        }
                                        
                                    }
                                    
                                }
                                
                                union() {                                
                                boom_web_inner_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_fillet_radius, web_width,boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width, boom_tolerance, boom_make_vert_web);
                                    
                                   if (boom_make_lower_web) {
                                        
                                        mirror([0,-1,0]) {
                                            boom_web_inner_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_fillet_radius, web_width,boom_diameter, boom_y_position, -boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, 180-boom_key_angle, boom_key_web_width, boom_tolerance, boom_make_vert_web);
                                        }
                                    }                                    
                                }
                                
                                boom_key_shape(boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_tolerance);
                
                            }
                        }
                        bulkhead_oml_inner_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);

                    }
                }
            }
            boom_key_shape(boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_tolerance);

        }
    }
}

module boom_web_outer_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_fillet_radius, web_width,boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width, boom_tolerance) {
    
    fillet_outer(web_fillet_radius) {
        union() {
            offset(r = boom_key_web_width) {
                boom_key_shape(boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_tolerance);
            }
        
            offset(r = web_width/2) {
                mirror_x() {
                    upper_boom_support_centerline_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_width, boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness);
                }
            }
        
        }
    }
}

module boom_web_inner_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_fillet_radius, web_width,boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_key_web_width, boom_tolerance, boom_make_vert_web) {
    
    fillet_inner(web_fillet_radius) {
    difference() {
        
        if (boom_make_vert_web) {
            mirror_x() {
                
                offset(r = -web_width/2) {
                    upper_boom_support_centerline_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_width, boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness);
                }
            }
        
        } else {
            offset(r = -web_width/2) {
                mirror_x() {
                    upper_boom_support_centerline_shape(unit_width, corner_radius, panel_thickness, panel_tolerance, bolt_offset, web_width, boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness);
                }

            }
        }
        
        offset(r = boom_key_web_width) {
            boom_key_shape(boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius,  boom_key_angle, boom_tolerance);
        }
    
    }
    }
    
}

module boom_key_shape(boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_tolerance) {

    fillet_outer(boom_key_radius) {
        fillet_inner(boom_key_radius) {

            mirror_x() {

                translate([boom_y_position, boom_z_position]) {

                    rotate([0,0,boom_key_angle]) {
                        union() {
                            circle(r = boom_diameter/2 + boom_collet_thickness+boom_tolerance);
                            
                            translate([-boom_key_width/2,0,0]) {
                                square([boom_key_width, boom_diameter/2 + boom_collet_thickness+boom_tolerance+boom_key_height], center=false);
                            }
                        }
                    }
                }
            }
        
        }
    }
}
