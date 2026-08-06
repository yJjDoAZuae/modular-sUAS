include <shape_modifier_utils.scad>
include <fuselage_corner_geometry.scad>

module bulkhead_section_full(is_interconnect, is_cowling, unit_width, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, greeble_tolerance, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, nozzle_diameter) {

    octant_to_full() {
        bulkhead_section_octant(is_interconnect, is_cowling, unit_width, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, greeble_tolerance, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, nozzle_diameter);
    }
    
}

module bulkhead_section_octant(is_interconnect, is_cowling, unit_width, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, greeble_tolerance, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, nozzle_diameter) {
    
    if (is_interconnect) {
        
        difference() {
        
        union() {
        
            // bottom section
            translate([unit_width/2-corner_radius,unit_width/2-corner_radius,0]) {
                bulkhead_section(true, is_interconnect, is_cowling, unit_width, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, greeble_tolerance, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, nozzle_diameter);
            }
                
            mirror([0,0,-1]) {
                translate([unit_width/2-corner_radius,unit_width/2-corner_radius,-2*bulkhead_thickness]) {
                    bulkhead_section(false, is_interconnect, is_cowling, unit_width, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, greeble_tolerance, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, nozzle_diameter);
                }
                
            }
        }
        translate([unit_width/2-corner_radius,unit_width/2-corner_radius,0]) {
        rotate([90,0,0]) {
        linear_extrude(height=unit_width, center=true, convexity=4,twist=0,slices=1,scale=1){
        polygon([
            [-unit_width/2, bulkhead_thickness], 
            [-(panel_offset+panel_overlap+flange_thickness+2*flange_fillet_radius)-bulkhead_thickness, bulkhead_thickness],
            [-(panel_offset+panel_overlap+flange_thickness+2*flange_fillet_radius), 2*bulkhead_thickness],
            [-unit_width/2, 2*bulkhead_thickness], 
        ]);
        }
        
        }
    }
    }
        
    } else {
        translate([unit_width/2-corner_radius,unit_width/2-corner_radius,0]) {
            bulkhead_section(true, is_interconnect, is_cowling, unit_width, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, greeble_tolerance, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, nozzle_diameter);
        }
    }
}

module bulkhead_section(make_web, is_interconnect, is_cowling, unit_width, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, greeble_tolerance, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, nozzle_diameter)
{
    
    eps = geometry_eps();
    
    difference() {
        
        union() {
        
            bulkhead_flange_positive(make_web, is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer);
        
            if (!is_interconnect) {
                bolt_flange_positive(bulkhead_thickness, bolt_hole_radius, bolt_thickness, bolt_offset);
                
                bolt_flange_fillet(bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, flange_chamfer);
            
                bolt_web(bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, web_width);
            }
        
            if (make_web) {
                bulkhead_web(is_interconnect, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, web_fillet_radius, web_width, flange_thickness);
            }
            
            if (is_cowling) {
            intersection() {
                
                difference() {
                cylinder(h=bulkhead_thickness, r=corner_radius, center=false);
                cylinder(h=bulkhead_thickness, r=corner_radius-flange_thickness, center=false);
                    
                }
                    
                linear_extrude(height=through_cut(bulkhead_thickness), center=true, convexity=1,twist=0,slices=1,scale=1){
                    polygon([[0,0], [0, corner_radius], [corner_radius,corner_radius]]);
                }
                
            }
            intersection() {
                
                cylinder(h=plate_thickness, r=corner_radius, center=false);
                    
                   
                linear_extrude(height=through_cut(bulkhead_thickness), center=true, convexity=1,twist=0,slices=1,scale=1){
                    polygon([[0,0], [0, corner_radius], [corner_radius,corner_radius]]);
                }
                
            }
            
            linear_extrude(height=plate_thickness, center=false, convexity=2,twist=0,slices=1,scale=1){
                    polygon([[0,0], [0, corner_radius], [-panel_overlap,corner_radius], [-panel_overlap,0]]);
                }
            
            // longeron flange
            cylinder(h=bulkhead_thickness,r=longeron_radius+bolt_thickness, center=false);
            
            // longeron chamfer
            translate([0,0,plate_thickness]) {
            cylinder(h=flange_chamfer,r1=longeron_radius+bolt_thickness+flange_chamfer,r2=longeron_radius+bolt_thickness, center=false);    
            }
                
            translate([0,0,bulkhead_thickness]) {
        linear_extrude(height=cowl_flange_height, center=false, convexity=4,twist=0,slices=1,scale=1){
            
            polygon([[0,corner_radius-nozzle_diameter-cowl_flange_tolerance],[0,corner_radius-flange_thickness],[corner_radius-unit_width/2,corner_radius-flange_thickness],[corner_radius-unit_width/2,corner_radius-nozzle_diameter-cowl_flange_tolerance]]);
            
            intersection() {
                
                polygon([[0,0], [0, corner_radius], [corner_radius,corner_radius]]);
                
                difference() {
                    circle(r = corner_radius - nozzle_diameter-cowl_flange_tolerance);
                    circle(r = corner_radius - flange_thickness);
                }
                
            }
            
        }                
            }
        
        }

         
    }

   if (!is_cowling) {
        // Use corner_end as a negative shape to form the greeble. The tolerance is
        // zeroed here so the pocket comes out at nominal size: all of the fit
        // clearance lives on the corner's nub, never split across both halves, or
        // the joint would carry it twice.
       greeble_tolerance_local = 0;
       
       U = unit_width/100;
       
       translate([0,0,-eps]) { // note sneaky eps shift to clean up the bottom of the greeble cutout
        corner_end(U, bulkhead_thickness+2*eps, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance_local, nozzle_diameter);
       }
        
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
                    [-(panel_offset+panel_overlap),corner_radius-(panel_thickness+panel_tolerance+eps)],
                    [0,corner_radius-(panel_thickness+panel_tolerance+eps)]
                    ]);
                circle(r=corner_radius-(panel_thickness+panel_tolerance+eps));
            }
        }
        
    }

        // longeron hole
        cylinder(h=through_cut(bulkhead_thickness), r=longeron_radius+longeron_tolerance, center=true);
        

        if (!is_interconnect) {
            // bolt hole
            translate([-bolt_offset,-bolt_offset,0]){
                cylinder(h=through_cut(bulkhead_thickness), r=bolt_hole_radius, center=true);
            }
        }
        
        linear_extrude(height=through_cut(bulkhead_thickness), center=true, convexity=5,twist=0,slices=1,scale=1) {
            octant_mask(unit_width, corner_radius);
        }
    }
}


module greeble_bolt_web(bulkhead_thickness, bolt_offset, plate_thickness, flange_thickness, flange_chamfer) {
    
    union() {
    
        linear_extrude(height=bulkhead_thickness, center=false, convexity=2,twist=0,slices=1,scale=1) { 
            // greeble to bolt web
            polygon([
                [0,0],
                [-flange_thickness/(2*sqrt(2)), flange_thickness/(2*sqrt(2))],
                [-flange_thickness/(2*sqrt(2))-bolt_offset, flange_thickness/(2*sqrt(2))-bolt_offset],
                [-bolt_offset, -bolt_offset]
                ]);
        }
  
        translate([-bolt_offset,-bolt_offset,0]) {
        rotate([0,0,-135]) {
            rotate([0,-90,0]) {
                linear_extrude(height=bolt_offset*sqrt(2), center=false, convexity=3,twist=0,slices=1,scale=1) {
                    polygon([[0,0],[plate_thickness+flange_chamfer,0],[plate_thickness+flange_chamfer,-flange_thickness/2],[plate_thickness,-flange_thickness/2-flange_chamfer],[0,-flange_thickness/2-flange_chamfer]]);
                }
            }
        }
        }
   
   
    }
}

// make a fillet between the side wall of the flange at the greeble and the diagonal web that connects it to the bolt hole flange
module greeble_to_web_fillet(bulkhead_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_offset, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer) {
    
    eps = geometry_eps();
    
    // upper intersection between bolt flange fillet and corner flange
    x_corner_fillet_start = max(-panel_tolerance-panel_offset-panel_overlap-flange_thickness, -bolt_offset);
    
    // fillet x center point
    x_corner_fillet_center = x_corner_fillet_start-flange_fillet_radius;

    // fillet center angle will be 45 degrees.  I.e. radial to upper tangent point will be at 0 deg center angle and radial to lower tangent point will be at 45 deg center angle (x axis = 0, positive rotation about z).
    
    x_corner_fillet_end = x_corner_fillet_center + flange_fillet_radius/sqrt(2);
    
    // account for thickness of the web
    y_corner_fillet_end = x_corner_fillet_end + sqrt(2)/2*flange_thickness;
    
    // find y start point
    y_corner_fillet_center = y_corner_fillet_end + 1/sqrt(2)*flange_fillet_radius;
    y_corner_fillet_start = y_corner_fillet_center;

//    echo("x_corner_fillet_start = ", x_corner_fillet_start);
//    echo("x_corner_fillet_center = ", x_corner_fillet_center);
//    echo("y_corner_fillet_start = ", y_corner_fillet_start);
//    echo("y_corner_fillet_center = ", y_corner_fillet_center);
//    echo("x_corner_fillet_end = ", x_corner_fillet_end);
//    echo("y_corner_fillet_end = ", y_corner_fillet_end);

    difference() {
        
        linear_extrude(height=bulkhead_thickness, center=false, convexity=3,twist=0,slices=1,scale=1) {
        
            polygon([[x_corner_fillet_center,y_corner_fillet_center],[x_corner_fillet_start,y_corner_fillet_start],[x_corner_fillet_start,y_corner_fillet_end],[x_corner_fillet_end,y_corner_fillet_end]] );
        }
            
        translate([x_corner_fillet_center,y_corner_fillet_center, 0]) {
            cylinder(h = plate_thickness, r=flange_fillet_radius-flange_chamfer, center=false);
        }
        translate([x_corner_fillet_center,y_corner_fillet_center, plate_thickness]) {
            cylinder(h = flange_chamfer, r1=flange_fillet_radius-flange_chamfer, r2 =flange_fillet_radius, center=false);
        }
        translate([x_corner_fillet_center,y_corner_fillet_center, plate_thickness+flange_chamfer]) {
            cylinder(h = bulkhead_thickness-flange_chamfer-plate_thickness+eps, r=flange_fillet_radius, center=false);
        }
        
    }

}

// make a fillet between the bolt hole flange and the side wall of the flange at the greeble
module bulkhead_bolt_flange_fillet(bulkhead_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer) {
    
    eps = geometry_eps();
    
    x_bolt_center = -bolt_offset;
    y_bolt_center = -bolt_offset;
    
    // upper intersection between bolt flange fillet and corner flange
    x_corner_fillet_start = max(-panel_tolerance-panel_offset-panel_overlap-flange_thickness, -bolt_offset);
    
    // fillet x center point
    x_corner_fillet_center = -panel_tolerance-panel_offset-panel_overlap-flange_thickness-flange_fillet_radius;
    
    // difference in x between the bolt hole center and the center of the fillet
    del_x_fillet = x_corner_fillet_center-x_bolt_center;

    // radius from bolt center to fillet center
    r_bolt_fillet = flange_fillet_radius+bolt_hole_radius+bolt_thickness;

    // discriminant, clipped to 0 or larger
    rad_disc = max(r_bolt_fillet^2-del_x_fillet^2, 0);
    
    // fillet y start point
    y_corner_fillet_start = sqrt(rad_disc)+y_bolt_center;
    
    // fillet y center point
    y_corner_fillet_center = y_corner_fillet_start;

    // difference in y between the bolt hole center and the center of the fillet
    del_y_fillet = y_corner_fillet_center-y_bolt_center;
    
    // Distance between bolt center and fillet center
    del_r_fillet = sqrt(del_x_fillet^2 + del_y_fillet^2);

    // fillet end point
    x_corner_fillet_end = x_corner_fillet_center + del_x_fillet*flange_fillet_radius/del_r_fillet;
    y_corner_fillet_end = y_corner_fillet_center + del_y_fillet*flange_fillet_radius/del_r_fillet;

//    echo("x_corner_fillet_start = ", x_corner_fillet_start);
//    echo("x_corner_fillet_center = ", x_corner_fillet_center);
//    echo("del_x_fillet = ", del_x_fillet);
//    echo("r_bolt_fillet = ", r_bolt_fillet);
//    echo("rad_disc = ", rad_disc);
//    echo("y_corner_fillet_start = ", y_corner_fillet_start);
//    echo("y_corner_fillet_center = ", y_corner_fillet_center);
//    echo("del_y_fillet = ", del_y_fillet);
//    echo("del_r_fillet = ", del_r_fillet);
//    echo("x_corner_fillet_end = ", x_corner_fillet_end);
//    echo("y_corner_fillet_end = ", y_corner_fillet_end);

    difference() {
        linear_extrude(height=bulkhead_thickness, center=false, convexity=3,twist=0,slices=1,scale=1) {
        polygon([[x_corner_fillet_center,y_corner_fillet_center],[x_corner_fillet_start,y_corner_fillet_start],[x_corner_fillet_start,y_bolt_center],[x_bolt_center,y_bolt_center],[x_corner_fillet_end,y_corner_fillet_end]] );
        }
        
        translate([x_corner_fillet_center,y_corner_fillet_center, 0]) {
            cylinder(h = plate_thickness, r=flange_fillet_radius-flange_chamfer, center=false);
        }
        translate([x_corner_fillet_center,y_corner_fillet_center, plate_thickness]) {
            cylinder(h = flange_chamfer, r1=flange_fillet_radius-flange_chamfer, r2 =flange_fillet_radius, center=false);
        }
        translate([x_corner_fillet_center,y_corner_fillet_center, plate_thickness+flange_chamfer]) {
            cylinder(h = bulkhead_thickness-flange_chamfer-plate_thickness + eps, r=flange_fillet_radius, center=false);
        }
    }

}


module bulkhead_flange_chamfer(is_interconnect, unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_offset, plate_thickness, flange_thickness, flange_chamfer) {
    
    union() {
    
    // chamfer along flange at the plate
    translate([-(panel_offset + panel_overlap + panel_tolerance),corner_radius - panel_thickness - panel_tolerance,0]) {
        rotate([0,-90,0]) {
            linear_extrude(height=unit_width/2-corner_radius-(panel_offset + panel_overlap + panel_tolerance), center=false, convexity=3,twist=0,slices=1,scale=1) {
                polygon([[0,0],[plate_thickness+flange_chamfer,0],[plate_thickness+flange_chamfer,-flange_thickness],[plate_thickness,-flange_thickness-flange_chamfer],[0,-flange_thickness-flange_chamfer]]);
            }
        }
    }
   
    if (is_interconnect) {

    translate([-(panel_offset + panel_overlap + panel_tolerance),0,0]) {
    rotate([0,0,-90]) {
        rotate([0,-90,0]) {
            linear_extrude(height=(corner_radius - panel_thickness - panel_tolerance), center=false, convexity=3,twist=0,slices=1,scale=1) {
                polygon([[0,0],[plate_thickness+flange_chamfer,0],[plate_thickness+flange_chamfer,-flange_thickness],[plate_thickness,-flange_thickness-flange_chamfer],[0,-flange_thickness-flange_chamfer]]);
            }
        }
    }
    }
        
        
    } else {
    
    translate([-(panel_offset + panel_overlap + panel_tolerance),-bolt_offset,0]) {
    rotate([0,0,-90]) {
        rotate([0,-90,0]) {
            linear_extrude(height=(corner_radius + bolt_offset - panel_thickness - panel_tolerance), center=false, convexity=3,twist=0,slices=1,scale=1) {
                polygon([[0,0],[plate_thickness+flange_chamfer,0],[plate_thickness+flange_chamfer,-flange_thickness],[plate_thickness,-flange_thickness-flange_chamfer],[0,-flange_thickness-flange_chamfer]]);
            }
        }
    }
    }
    
    }
}
    
}

module bulkhead_web(is_interconnect, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, web_fillet_radius, web_width, flange_thickness) {
    
    difference() {
        linear_extrude(height=plate_thickness, center=false, convexity=5,twist=0,slices=1,scale=1) {
            bulkhead_web_shape(is_interconnect, unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, web_fillet_radius, web_width, flange_thickness);
        }
        
        // web fillet
        translate([-bolt_offset-(bolt_hole_radius+bolt_thickness+web_width)-web_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width-web_fillet_radius,0]) {
            cylinder(h=through_cut(bulkhead_thickness), r=web_fillet_radius, center=true);
        }
    }
    
}

// make a fillet between the bolt hole flange and the side wall of the flange at the greeble
module web_to_bolt_fillet(bulkhead_thickness, bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer)
 {
    
    eps = geometry_eps();
     
    x_bolt_center = -bolt_offset;
    y_bolt_center = -bolt_offset;
    
    disc = max((bolt_hole_radius + bolt_thickness + flange_fillet_radius)^2 - (flange_fillet_radius + flange_thickness/2)^2, 0);
    
    tan_len = sqrt(disc);
    
    // fillet x center point
    x_corner_fillet_center = x_bolt_center + 1/sqrt(2)*(tan_len -flange_fillet_radius - flange_thickness/2);

    // fillet y center point
    y_corner_fillet_center = y_bolt_center + 1/sqrt(2)*(tan_len +flange_fillet_radius + flange_thickness/2);
    
    // upper intersection between side wall of the flange at the greeble and corner flange
    x_corner_fillet_start = x_bolt_center + 1/sqrt(2)*(tan_len - flange_thickness/2) ;
    
    // fillet y start point
    y_corner_fillet_start = y_bolt_center + 1/sqrt(2)*(tan_len + flange_thickness/2);
    
    // difference in x between the bolt hole center and the center of the fillet
    del_x_fillet = x_corner_fillet_center-x_bolt_center;

    // difference in y between the bolt hole center and the center of the fillet
    del_y_fillet = y_corner_fillet_center-y_bolt_center;

    // radius from bolt center to fillet center
    r_bolt_fillet = flange_fillet_radius+bolt_hole_radius+bolt_thickness;
    
    // Distance between bolt center and fillet center
    del_r_fillet = sqrt(del_x_fillet^2 + del_y_fillet^2);

    // fillet end point
    x_corner_fillet_end = x_corner_fillet_center + del_x_fillet*flange_fillet_radius/del_r_fillet;
    y_corner_fillet_end = y_corner_fillet_center + del_y_fillet*flange_fillet_radius/del_r_fillet;

//    echo("disc = ", disc);
//    echo("tan_len = ", tan_len);
//    echo("x_corner_fillet_start = ", x_corner_fillet_start);
//    echo("x_corner_fillet_center = ", x_corner_fillet_center);
//    echo("y_corner_fillet_start = ", y_corner_fillet_start);
//    echo("y_corner_fillet_center = ", y_corner_fillet_center);
//    echo("r_bolt_fillet = ", r_bolt_fillet);
//    echo("del_x_fillet = ", del_x_fillet);
//    echo("del_y_fillet = ", del_y_fillet);
//    echo("del_r_fillet = ", del_r_fillet);
//    echo("x_corner_fillet_end = ", x_corner_fillet_end);
//    echo("y_corner_fillet_end = ", y_corner_fillet_end);

    difference() {
        
        linear_extrude(height=bulkhead_thickness, center=false, convexity=3,twist=0,slices=1,scale=1) {
        polygon([[x_corner_fillet_center,y_corner_fillet_center],[x_corner_fillet_start,y_corner_fillet_start],[x_corner_fillet_start,y_bolt_center],[x_bolt_center,y_bolt_center],[x_corner_fillet_end,y_corner_fillet_end]] );
        }
        translate([x_corner_fillet_center,y_corner_fillet_center, 0]) {
            cylinder(h = plate_thickness, r=flange_fillet_radius-flange_chamfer, center=false);
        }
        translate([x_corner_fillet_center,y_corner_fillet_center, plate_thickness]) {
            cylinder(h = flange_chamfer, r1=flange_fillet_radius-flange_chamfer, r2 =flange_fillet_radius, center=false);
        }
        translate([x_corner_fillet_center,y_corner_fillet_center, plate_thickness+flange_chamfer]) {
            cylinder(h = bulkhead_thickness-flange_chamfer-plate_thickness + eps, r=flange_fillet_radius, center=false);
        }
   }

}


module bulkhead_flange_positive(make_web, is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer) {
    
    x_start = -panel_tolerance-panel_offset-panel_overlap-flange_thickness;
    y_start = max(x_start, -bolt_offset);
    
    union() {
    
        // bulkhead flange
        linear_extrude(height=bulkhead_thickness, center=false, convexity=5,twist=0,slices=1,scale=1) {
            
            if (is_interconnect) {
            
            // base bulkhead shape
            union() {
                
                polygon([
                    [0,0], 
                    [0, corner_radius - panel_thickness - panel_tolerance], 
                    [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance], 
                    [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance-flange_thickness],

                    [x_start, corner_radius - panel_thickness - panel_tolerance-flange_thickness],
                    [x_start, 0],
                ]);
                
            }
    } else {
            // base bulkhead shape
            union() {
                
                if (!is_cowling) {
                
                polygon([
                    [0,0], 
                    [0, corner_radius - panel_thickness - panel_tolerance], 
                    [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance], 
                    [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance-flange_thickness],

                    [x_start, corner_radius - panel_thickness - panel_tolerance-flange_thickness],
                    [x_start, y_start],
                    [y_start, y_start]
                ]);
                
                }
                
                polygon([
                    [0,0], 
                    [0, corner_radius - panel_thickness - panel_tolerance], 
                    [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance], 
                    [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance-flange_thickness],
                    [0, corner_radius - panel_thickness - panel_tolerance-flange_thickness]
                ]);
                
                    
            }
        
    }
        
        }
        
        if (!is_cowling) {
        
        if (make_web) {
            bulkhead_flange_chamfer(is_interconnect, unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_offset, plate_thickness, flange_thickness, flange_chamfer);
            
            intersection() {
            
                union() {
            translate([0,0,plate_thickness]) {
            cylinder(h=flange_chamfer, r1=panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer, r2 = panel_tolerance+panel_offset+panel_overlap+flange_thickness, center=false);
            }
            cylinder(h=bulkhead_thickness, r=panel_tolerance+panel_offset+panel_overlap+flange_thickness, center=false);
            }
            
            linear_extrude(height=bulkhead_thickness, center=false, convexity=4,twist=0,slices=1,scale=1) {
            polygon([[0,0],[-(panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer),0],[-(panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer),-(panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer)],[0, -(panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer)]]);
            }
            
            }
        } else {
            
            intersection() {
            
                cylinder(h=bulkhead_thickness, r=panel_tolerance+panel_offset+panel_overlap+flange_thickness, center=false);
                
                linear_extrude(height=bulkhead_thickness, center=false, convexity=4,twist=0,slices=1,scale=1) {
                polygon([[0,0],[-(panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer),0],[-(panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer),-(panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer)],[0, -(panel_tolerance+panel_offset+panel_overlap+flange_thickness+flange_chamfer)]]);
                }
            }
        }
        
        outer_corner_fillet(make_web, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer);
        
        if (!is_interconnect) {
            
            greeble_bolt_web(bulkhead_thickness, bolt_offset, flange_thickness, flange_chamfer, plate_thickness);
            
            greeble_to_web_fillet(bulkhead_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_offset, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer);
            
            web_to_bolt_fillet(bulkhead_thickness, bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer);
            
            bulkhead_bolt_flange_fillet(bulkhead_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer);
            
        }
        }
    }
}


module outer_corner_fillet(make_web, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, plate_thickness, flange_fillet_radius, flange_thickness, flange_chamfer) {
    
    eps = geometry_eps();
    
    difference() {
        
        linear_extrude(height=bulkhead_thickness, center=false, convexity=3,twist=0,slices=1,scale=1) {
        
        polygon([
            [-panel_tolerance-panel_offset-panel_overlap-flange_thickness-flange_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness],
        
            [-panel_tolerance-panel_offset-panel_overlap-flange_thickness-flange_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness - flange_fillet_radius],        

            [-panel_tolerance-panel_offset-panel_overlap-flange_thickness, corner_radius - panel_thickness - panel_tolerance-flange_thickness-flange_fillet_radius],
            [-panel_tolerance-panel_offset-panel_overlap-flange_thickness, corner_radius - panel_thickness - panel_tolerance-flange_thickness]
        ]);
        }
        
        if (make_web) {
        // bulkhead flange fillet negative mask at outer corner
        translate([-panel_tolerance-panel_offset-panel_overlap-flange_thickness-flange_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness-flange_fillet_radius, 0]) {
            cylinder(h = plate_thickness, r=flange_fillet_radius-flange_chamfer, center=false);
        }
        translate([-panel_tolerance-panel_offset-panel_overlap-flange_thickness-flange_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness-flange_fillet_radius, plate_thickness]) {
            cylinder(h = flange_chamfer, r1=flange_fillet_radius-flange_chamfer, r2 =flange_fillet_radius, center=false);
        }
        translate([-panel_tolerance-panel_offset-panel_overlap-flange_thickness-flange_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness-flange_fillet_radius, plate_thickness+flange_chamfer]) {
            cylinder(h = bulkhead_thickness-flange_chamfer-plate_thickness + eps, r=flange_fillet_radius, center=false);
        }
        }else {
            translate([-panel_tolerance-panel_offset-panel_overlap-flange_thickness-flange_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness-flange_fillet_radius, 0]) {
            cylinder(h = bulkhead_thickness + eps, r=flange_fillet_radius, center=false);
            }
        }
        
    }    
}

// web shapes

module bulkhead_web_shape(is_interconnect, unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, web_fillet_radius, web_width, flange_thickness) {
    
    eps = geometry_eps();
    
    if (!is_interconnect) {
        polygon([
            [0,0], 
            [0, corner_radius - panel_thickness - panel_tolerance], 
            [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance], 
            [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width],
            [-bolt_offset-(bolt_hole_radius+bolt_thickness+web_width), corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width],
            [-bolt_offset-(bolt_hole_radius+bolt_thickness+web_width)-web_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width],
            [-bolt_offset-(bolt_hole_radius+bolt_thickness+web_width)-web_fillet_radius, corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width-web_fillet_radius],
            [-bolt_offset-(bolt_hole_radius+bolt_thickness+web_width), corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width-web_fillet_radius],
            [-bolt_offset-(bolt_hole_radius+bolt_thickness+web_width), -bolt_offset],
            [-bolt_offset, -bolt_offset]
        ]);
    } else {
        
        big_r = (panel_offset+panel_overlap+flange_thickness+web_width);
        
        // fillet start y
        y_start = corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width;
        
        y_center = corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width-web_fillet_radius;
        
        // fillet end y
        y_end = max(y_center * big_r/(big_r+web_fillet_radius),y_center);
        
        x_center = -sqrt((big_r+web_fillet_radius)^2 - min(y_center,0)^2);
        
        x_start = x_center;
        x_end = x_center * big_r/(big_r+web_fillet_radius);
        
//        echo("big_r = ", big_r);
//        echo("y_start = ", y_start);
//        echo("y_center = ", y_center);
//        echo("y_end = ", y_end);
//        echo("x_center = ", x_center);
//        echo("x_start = ", x_start);
//        echo("x_end = ", x_end);
        
        difference() {
        union() {
            
            
        polygon([
            [0,0], 
            [0, corner_radius - panel_thickness - panel_tolerance], 
            [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance], 
            [-(unit_width/2-corner_radius), corner_radius - panel_thickness - panel_tolerance-flange_thickness-web_width],
            [x_start, y_start],
            [x_center, y_center],
            [x_end, y_end],
            [x_end, min(y_end,0)]
        ]);
            
        intersection() {
            polygon([
                [0,0],
                [-(big_r+web_fillet_radius)+eps,0],
                [-(big_r+web_fillet_radius+eps),-(big_r+web_fillet_radius+eps)],
                [0, -(big_r+web_fillet_radius+eps)]
            ]);
        
            circle(r=big_r);
            
        }
        }
        translate([x_center,y_center,0]){
        circle(r=web_fillet_radius);
        }
    }
    }
}

module bolt_flange_positive(bulkhead_thickness, bolt_hole_radius, bolt_thickness, bolt_offset) {
    translate([-bolt_offset,-bolt_offset,0]) {
        cylinder(h=bulkhead_thickness, r = bolt_hole_radius+bolt_thickness);
    }
}

module bolt_web(bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, web_width) {
    translate([-bolt_offset,-bolt_offset,0]) {
        cylinder(h=plate_thickness, r = bolt_hole_radius+bolt_thickness+web_width);
    }
}

module bolt_flange_fillet(bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, flange_chamfer) {
    translate([-bolt_offset,-bolt_offset,plate_thickness]) {
        cylinder(h=flange_chamfer, r1 = bolt_hole_radius+bolt_thickness+flange_chamfer, r2 = bolt_hole_radius+bolt_thickness);
    }
}

// outer-inner shapes

module bulkhead_oml_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset) {
    
    octant_tiled(unit_width, corner_radius) {
        bulkhead_oml_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);
    }
}

// outer shapes

module bulkhead_oml_outer_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset) {
    
    octant_tiled(unit_width, corner_radius) {
        bulkhead_oml_outer_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);
    }
}

// inner shapes

module bulkhead_oml_inner_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset) {
    
    octant_tiled(unit_width, corner_radius) {
        bulkhead_oml_inner_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);
    }
}

module bulkhead_web_inner_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset, web_fillet_radius, web_width) {
    
    octant_tiled(unit_width, corner_radius) {
        bulkhead_web_inner_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset, web_fillet_radius, web_width);
    }
}

// octant shapes

module bulkhead_oml_outer_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset) {
    
    difference() {
        union(){
            translate([-(unit_width/2-corner_radius),-(unit_width/2-corner_radius),0]) {
                square(size = [unit_width/2-corner_radius,unit_width/2-corner_radius], center = false);
            }
            translate([-(unit_width/2-corner_radius),0,0]) {
                square(size = [unit_width/2-corner_radius,corner_radius], center = false);
            }
            circle(r=corner_radius);
        }
        union() {
            translate([-(unit_width/2-corner_radius+panel_tolerance),corner_radius-panel_thickness-panel_tolerance,0]) {
                square(size = [(unit_width/2-corner_radius-panel_offset+panel_tolerance),corner_radius-panel_thickness-panel_tolerance], center = false);
            }
            octant_mask(unit_width, corner_radius);
        }
    }
}

module bulkhead_web_inner_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset, web_fillet_radius, web_width) {
    
    translate([-(unit_width/2-corner_radius),-(unit_width/2-corner_radius),0]) {
        
    
    intersection() {
        
        bulkhead_oml_outer_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);
        
        fillet_inner(web_fillet_radius) {
        offset(r = -web_width) {
            
            bulkhead_oml_shape(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);
            
        }
        }
        
        polygon([
            [0,0],
            [unit_width/2,unit_width/2],
            [0,unit_width/2]]);
        
    }

    }
    
}

// cutouts for longeron and bolt holes
module bulkhead_oml_inner_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset) {
    
    union() {
        circle(r=longeron_radius+longeron_tolerance);
        translate([-bolt_offset,-bolt_offset,0]) {
            circle(r=bolt_hole_radius);
        }
    }
}

module bulkhead_oml_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset) {
    
    difference() {
        
        bulkhead_oml_outer_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);
        
        bulkhead_oml_inner_shape_octant(unit_width, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_offset);
    }
}
