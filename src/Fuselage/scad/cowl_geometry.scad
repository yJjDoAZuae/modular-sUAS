include <shape_modifier_utils.scad>

module nose_cowl(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len, buttress_thickness, buttress_z_offset, buttress_r_start, buttress_r_end, buttress_r_inset, cone_angle) {

    octant_to_full() {
        nose_cowl_octant(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len, buttress_thickness, buttress_z_offset, buttress_r_start, buttress_r_end, buttress_r_inset, cone_angle);
    } 
}

module nose_cowl_octant(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len, buttress_thickness, buttress_z_offset, buttress_r_start, buttress_r_end, buttress_r_inset, cone_angle) {
    
    ang = 0;
    buttress_z_end = cut_len + buttress_z_offset;
    body_len = U*oml_length/oml_scale;
    
    difference() {
        body_blank_octant_lower(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len);
        
        side_buttress(ang, unit_width, body_len, buttress_thickness, buttress_z_end, buttress_z_offset, buttress_r_start, buttress_r_end, buttress_r_inset, cone_angle);
    }
}


module tail_cowl(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len, buttress_thickness, buttress_z_offset, buttress_r_inset, side_buttress_z_end, side_buttress_r_start, side_buttress_r_end, top_buttress_z_end, top_buttress_r_start, top_buttress_r_end, bottom_buttress_z_end, bottom_buttress_r_start, bottom_buttress_r_end, top_diag_buttress_depth, top_diag_buttress_z_start, cone_angle) {
    
    mirror_y() {
        tail_cowl_half(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len, buttress_thickness, buttress_z_offset, buttress_r_inset, side_buttress_z_end, side_buttress_r_start, side_buttress_r_end, top_buttress_z_end, top_buttress_r_start, top_buttress_r_end, bottom_buttress_z_end, bottom_buttress_r_start, bottom_buttress_r_end, top_diag_buttress_depth, top_diag_buttress_z_start, cone_angle);
    }
}

module tail_cowl_half(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len, buttress_thickness, buttress_z_offset, buttress_r_inset, side_buttress_z_end, side_buttress_r_start, side_buttress_r_end, top_buttress_z_end, top_buttress_r_start, top_buttress_r_end, bottom_buttress_z_end, bottom_buttress_r_start, bottom_buttress_r_end, top_diag_buttress_depth, top_diag_buttress_z_start, cone_angle) {
    
    
    tail_len = U*oml_length/oml_scale;
    
    difference() {
        body_blank_half_lower(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len);
        
        difference() {
            union() {
        
        translate([-unit_width*0.30,0,0]) {
            side_buttress(5, unit_width, tail_len, buttress_thickness, side_buttress_z_end, buttress_z_offset, side_buttress_r_start, side_buttress_r_end, buttress_r_inset, cone_angle);
        }

        translate([-unit_width*0.00,0,0]) {
            side_buttress(12.5, unit_width, tail_len, buttress_thickness, side_buttress_z_end, buttress_z_offset, side_buttress_r_start, side_buttress_r_end, buttress_r_inset, cone_angle);
        }
        
        translate([unit_width*0.30,0,0]) {
            side_buttress(20, unit_width, tail_len, buttress_thickness, side_buttress_z_end, buttress_z_offset, side_buttress_r_start, side_buttress_r_end, buttress_r_inset, cone_angle);
        }

        
        translate([0,unit_width*0.07,0]) {
        top_buttress(15, unit_width, tail_len, buttress_thickness, top_buttress_z_end, buttress_z_offset, top_buttress_r_start, top_buttress_r_end, buttress_r_inset, cone_angle);
        }
        top_buttress(0, unit_width, tail_len, buttress_thickness, top_buttress_z_end, buttress_z_offset, top_buttress_r_start, top_buttress_r_end, buttress_r_inset, cone_angle);
        
        translate([0,0,-tail_len+top_diag_buttress_z_start]) {
            top_diag_buttress(30, unit_width, buttress_thickness, top_diag_buttress_depth);
            top_diag_buttress(-30, unit_width, buttress_thickness, top_diag_buttress_depth);
        }
        translate([0,0,-tail_len+top_diag_buttress_z_start+unit_width*sin(30)]) {
            top_diag_buttress(30, unit_width, buttress_thickness, top_diag_buttress_depth);
            top_diag_buttress(-30, unit_width, buttress_thickness, top_diag_buttress_depth);
        }

        translate([0,unit_width*0.07,0]) {
        bottom_buttress(15, unit_width, tail_len, buttress_thickness, bottom_buttress_z_end, buttress_z_offset, bottom_buttress_r_start, bottom_buttress_r_end, buttress_r_inset, cone_angle);
        }
        bottom_buttress(0, unit_width, tail_len, buttress_thickness, bottom_buttress_z_end, buttress_z_offset, bottom_buttress_r_start, bottom_buttress_r_end, buttress_r_inset, cone_angle);
        
    }
    
    union() {
    translate([0,0,-tail_len+buttress_z_offset]) {
    scale([unit_width/2,unit_width/2,unit_width/4]) {
        pyramid();
    }
     }
     translate([-unit_width/2,-unit_width/2,-2*tail_len+buttress_z_offset]) {
     cube([unit_width,unit_width,tail_len], center=false);
     }
    }
    
    }
    }
}

module nose(U, unit_width, oml_filename, oml_scale, oml_offset_x, oml_reversed, cut_len, nose_flange_height, nose_flange_inset, plate_diam, plate_thickness, plate_tol, cone_angle) {
     
    eps = 0.01;
   
    difference() {
        union() {
        body_blank_full_upper(U, unit_width, oml_filename, oml_scale, oml_offset_x, oml_reversed, cut_len);
            
        translate([0,0,-cut_len-nose_flange_height]) {
        linear_extrude(height=nose_flange_height,center=false,convexity=5,twist=0,slices=1,scale=1.0) {
            offset(r = -nose_flange_inset) {
            projection(cut=false) body_blank_full_upper(U, unit_width, oml_filename, oml_scale, oml_offset_x, oml_reversed, cut_len);
            }
        }
        }
    }

        cylinder(h = 3*(cut_len+nose_flange_height), r = plate_diam/2+plate_tol, center=true);
        
        translate([0,0,-cut_len-nose_flange_height-eps]) {
            
            cylinder(h = cut_len-plate_thickness+nose_flange_height+eps, 
                r1 = plate_diam/2+plate_tol + (cut_len-plate_thickness+nose_flange_height+eps)/tan(cone_angle), 
                r2 = plate_diam/2+plate_tol, 
                center=false);
        }
    }
    
}
module nose_plate(plate_diam, plate_thickness, plate_flange_width, plate_flange_height, cone_angle) {
    
    eps = 0.01;
    
    difference() {
    union() {
        
        translate([0,0,-plate_thickness-2*plate_flange_height]) {
            cylinder(h = plate_thickness+2*plate_flange_height, r = plate_diam/2, center=false);
        }

        translate([0,0,-plate_thickness-plate_flange_height]) {
            cylinder(h = plate_flange_height, 
                r1 = plate_diam/2 + plate_flange_height/tan(cone_angle), 
                r2 = plate_diam/2, center=false);
        }

        translate([0,0,-plate_thickness-2*plate_flange_height]) {
            cylinder(h = plate_flange_height, 
                r = plate_diam/2 + plate_flange_height/tan(cone_angle));
        }
        
    }
    
    translate([0,0,-plate_thickness-2*plate_flange_height-eps]) {
            cylinder(h = 2*plate_flange_height+eps, 
                r1 = plate_diam/2 - plate_flange_width + (2*plate_flange_height+eps)/tan(cone_angle), 
                r2 = plate_diam/2 - plate_flange_width, center=false);
        }
    
    }
    
}


module assembly_tool(U, unit_width, oml_filename, oml_scale, oml_offset_x, oml_reversed, cut_len, plate_diam, plate_tol) {
    
    union() {
    
    difference() {

       
       translate([-unit_width/2,-unit_width/2,0]) {
        cube([unit_width,unit_width,2*cut_len+1], center=false);
       }
        
       translate([0,0,1]) {
           mirror([0,0,-1]) {
               body_blank_full(U, oml_filename, oml_scale, oml_offset_x, oml_reversed);
           }
       }
        
    }
    
    cylinder(h=2, r = plate_diam/2 + plate_tol, center = false);
    
    }
    
}




module body_blank_full(U, oml_filename, oml_scale, oml_offset_x, oml_reversed) {
    
    pitch_angle = 90-(oml_reversed?180:0);
    
    rotate([0,pitch_angle,0]) {
        scale([U/oml_scale,U/oml_scale,U/oml_scale]) {
            translate([oml_offset_x,0,0]) {
            import(oml_filename);
            }
        }
    }
}

module body_blank_full_upper(U, unit_width, oml_filename, oml_scale, oml_offset_x, oml_reversed, cut_len) {
    
    intersection() {

        body_blank_full(U, oml_filename, oml_scale,  oml_offset_x, oml_reversed);

        translate([0,0,-cut_len]) {

            linear_extrude(height=cut_len,center=false,convexity=1,twist=0,slices=1,scale=1.0) {
                polygon([
                    [+(unit_width),+(unit_width)],
                    [-(unit_width),+(unit_width)],
                    [-(unit_width),-(unit_width)],
                    [+(unit_width),-(unit_width)],
                ]);
            }
        }
    }  
}

module body_blank_full_lower(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len) {
    
    body_len = U*oml_length/oml_scale;
    
    intersection() {

        body_blank_full(U, oml_filename, oml_scale,  oml_offset_x, oml_reversed);

        translate([0,0,-body_len]) {

            linear_extrude(height=body_len-cut_len,center=false,convexity=1,twist=0,slices=1,scale=1.0) {
                polygon([
                    [+(unit_width),+(unit_width)],
                    [-(unit_width),+(unit_width)],
                    [-(unit_width),-(unit_width)],
                    [+(unit_width),-(unit_width)],
                ]);
            }
        }
    }  
}


module body_blank_half(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed) {

    body_len = U*oml_length/oml_scale;

    intersection() {
        
        body_blank_full(U, oml_filename, oml_scale, oml_offset_x, oml_reversed);

        right_half_mask(unit_width, body_len);

    }
}



module cowl_blank_full(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len) {

    body_len = U*oml_length/oml_scale;
    
    intersection() {

        body_blank_full(U, oml_filename, oml_scale, oml_offset_x, oml_reversed);

        translate([0,0,-body_len]) {

            linear_extrude(height=body_len-cut_len,center=false,convexity=1,twist=0,slices=1,scale=1.0) {
                polygon([
                    [+(unit_width),+(unit_width)],
                    [-(unit_width),+(unit_width)],
                    [-(unit_width),-(unit_width)],
                    [+(unit_width),-(unit_width)],
                ]);
            }
        }
    }  
}

module body_blank_half_lower(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len) {

    body_len = U*oml_length/oml_scale;

    intersection() {
        
        body_blank_full_lower(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len);

        right_half_mask(unit_width, body_len);

    }
}

module body_blank_octant_lower(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len) {
    
    body_len = U*oml_length/oml_scale;
    
    intersection() {

        body_blank_full_lower(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len);

        octant_mask(unit_width, body_len);

    }
}


module top_buttress(ang, unit_width, tail_len, buttress_thickness, top_buttress_z_end, buttress_z_offset, top_buttress_r_start, top_buttress_r_end, buttress_r_inset, cone_angle) {
    
    rotate([ang,0,0]) {
    rotate([0,0,0]) {
    translate([-unit_width/2,0,-tail_len]) {
    rotate([90,0,0]) {
    
    linear_extrude(height=2*buttress_thickness,center=true,convexity=2,twist=0,slices=1,scale=1.0) {
        buttress_shape(unit_width, tail_len, top_buttress_z_end, buttress_z_offset, top_buttress_r_start, top_buttress_r_end, buttress_r_inset, cone_angle);
    }
    }
    }
    }
    }
}

module top_diag_buttress(ang, unit_width, buttress_thickness, top_diag_buttress_depth) {
    
    rotate([ang,0,0]) {
    translate([-unit_width/2,0,0]) {
    
    linear_extrude(height=2*buttress_thickness,center=true,convexity=2,twist=0,slices=1,scale=1.0) {
        diag_buttress_shape(unit_width, top_diag_buttress_depth);
    }
    }
    }
}

module side_buttress(ang, unit_width, body_len, buttress_thickness, buttress_z_end, buttress_z_offset, buttress_r_start, buttress_r_end, buttress_r_inset, cone_angle) {
    
    rotate([0,0,-90]) {
    translate([-unit_width/2,0,-body_len]) {
    rotate([ang,0,0]) {
    rotate([90,0,0]) {
    
    linear_extrude(height=2*buttress_thickness,center=true,convexity=2,twist=0,slices=1,scale=1.0) {
        buttress_shape(unit_width, body_len, buttress_z_end, buttress_z_offset, buttress_r_start, buttress_r_end, buttress_r_inset, cone_angle);
    }
    }
    }
    }
    }
}

module bottom_buttress(ang, unit_width, body_len, buttress_thickness, bottom_buttress_z_end, buttress_z_offset, bottom_buttress_r_start, bottom_buttress_r_end, buttress_r_inset, cone_angle) {
    
    rotate([ang,0,0]) {
    rotate([0,0,180]) {
    translate([-unit_width/2,0,-body_len]) {
    rotate([90,0,0]) {
    
    linear_extrude(height=2*buttress_thickness,center=true,convexity=2,twist=0,slices=1,scale=1.0) {
        buttress_shape(unit_width, body_len, bottom_buttress_z_end, buttress_z_offset, bottom_buttress_r_start, bottom_buttress_r_end, buttress_r_inset, cone_angle);
    }
    }
    }
    }
    }
}

module buttress_shape(unit_width, body_len, z_end, z_offset, r_start, r_end, r_inset, cone_angle) {
    
    polygon([
        [-unit_width, z_offset],
        [r_start, z_offset],
        [r_start + r_inset, z_offset + r_inset*tan(cone_angle)],
        [r_end + r_inset, body_len - z_end - r_inset*tan(cone_angle)],
        [r_end, body_len - z_end],
        [-unit_width, body_len - z_end]
    ]);
}

module diag_buttress_shape(unit_width, buttress_depth) {
    
    polygon([
        [-unit_width, -unit_width/2],
        [buttress_depth, -unit_width/2],
        [buttress_depth, unit_width/2],
        [-unit_width, unit_width/2]
    ]);
    
}

module pyramid() {
    polyhedron(
        points=[ [1,1,0],[1,-1,0],[-1,-1,0],[-1,1,0], // the four points at base
               [0,0,1]  ],                                 // the apex point 
        faces=[ [0,1,4],[1,2,4],[2,3,4],[3,0,4],              // each triangle side
                  [1,0,3],[2,1,3] ]                         // two triangles for square base
    );
}

module right_half_mask(unit_width, body_len) {
    
    translate([0,0,-body_len]) {

        linear_extrude(height=3*body_len,center=true,convexity=1,twist=0,slices=1,scale=1.0) {
            polygon([
                [unit_width,0],
                [unit_width,unit_width], 
                [-unit_width,unit_width],
                [-unit_width,0]
            ]);
        }
    }
    
}

module octant_mask(unit_width, body_len) {
    
    translate([0,0,-body_len]) {

        linear_extrude(height=3*body_len,center=true,convexity=1,twist=0,slices=1,scale=1.0) {
            polygon([
                [0,0],
                [unit_width,unit_width],
                [0,unit_width]
            ]);
        }
    }
    
}
