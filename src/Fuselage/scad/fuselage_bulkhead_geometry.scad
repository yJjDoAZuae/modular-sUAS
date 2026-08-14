include <shape_modifier_utils.scad>
include <fuselage_corner_geometry.scad>

// A bulkhead does not know how long the bay is. Bay length is FX * unit_length and it
// reaches the corner only -- which is exactly why one bulkhead design serves bays of
// any length, and why FX is a separate axis of variation that the bulkhead sweep does
// not carry. Until 2026-08-06 unit_length was threaded through all three modules here
// and used by none of them, which quietly implied a dependency that does not exist.
// See OQ-DES-C3 in doc/design/corner.md.
module bulkhead_section_full(is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width) {

    octant_to_full() {
        bulkhead_section_octant(is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width);
    }
    
}

module bulkhead_section_octant(is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width) {
    
    if (is_interconnect) {
        
        difference() {
        
        union() {
        
            // bottom section
            translate([unit_width/2-corner_radius,unit_width/2-corner_radius,0]) {
                bulkhead_section(true, is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width);
            }
                
            mirror([0,0,-1]) {
                translate([unit_width/2-corner_radius,unit_width/2-corner_radius,-2*bulkhead_thickness]) {
                    bulkhead_section(false, is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width);
                }
                
            }
        }
        // Mass reduction: the interconnect is only full 2*bulkhead_thickness deep at the
        // corners, where the longerons and the bolted joints put the load. Between the
        // corners the upper section is cut away and the flange runs at 1*bulkhead_
        // thickness. Full depth is kept out to the flange plus two fillet radii, so the
        // retained region is defined by the flange rather than by a separate number.
        //
        // Watch the transform: rotate([90,0,0]) puts the polygon in the x-z plane and
        // sweeps it along y, so the polygon's SECOND coordinate is a height, not a
        // width. The two inboard vertices differ by one bulkhead_thickness in x over one
        // bulkhead_thickness in z -- a 45 degree ramp, self-supporting when printed.
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
            bulkhead_section(true, is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width);
        }
    }
}

module bulkhead_section(make_web, is_interconnect, is_cowling, unit_width, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, bolt_hole_radius, bolt_thickness, bolt_offset, greeble_opening_angle, greeble_thickness, greeble_nub_thickness, plate_thickness, web_fillet_radius, web_width, flange_fillet_radius, flange_thickness, flange_chamfer, cowl_flange_height, cowl_flange_tolerance, extrusion_width)
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
            
            polygon([[0,corner_radius-extrusion_width-cowl_flange_tolerance],[0,corner_radius-flange_thickness],[corner_radius-unit_width/2,corner_radius-flange_thickness],[corner_radius-unit_width/2,corner_radius-extrusion_width-cowl_flange_tolerance]]);
            
            intersection() {
                
                polygon([[0,0], [0, corner_radius], [corner_radius,corner_radius]]);
                
                difference() {
                    circle(r = corner_radius - extrusion_width-cowl_flange_tolerance);
                    circle(r = corner_radius - flange_thickness);
                }
                
            }
            
        }                
            }
        
        }

         
    }

   if (!is_cowling) {
        // Use corner_end as a negative shape to form the greeble. Subtracting the
        // corner's own end section leaves bulkhead material exactly where the corner
        // has none -- so the greeble is the *positive* post standing out of the
        // bulkhead, with the snap rib at greeble_nub_radius, and the corner carries
        // the matching bore and groove. One description, two mating halves.
        //
        // The literal 0 is the greeble tolerance, and it is deliberately not a
        // parameter of this module. The post is nominal by construction: all of the
        // fit clearance is taken on the corner's bore instead
        // (GREEBLE_TOLERANCE_CORNER_MM), because split across both halves the joint
        // would carry it twice. That is an invariant of the design, not a setting.
        //
        // Until 2026-08-06 bulkhead_section_full/_octant/_section did each take a
        // greeble_tolerance, and each threw it away for a local zero right here --
        // so the interface advertised a knob that could not do anything. Anyone
        // tuning the fit from this side would have seen no change at all. See
        // OQ-DES-B6 in doc/design/bulkhead.md.
       U = unit_width/100;
       
       // The end section is used here as a CUT TOOL, so it asks for overshoot explicitly.
       // It used to buy the same overshoot by passing bulkhead_thickness+2*eps and shifting
       // the result down by eps -- which also inflated the snap rib, because corner_end
       // sizes it from the thickness. See OQ-DES-B12. Same z extent as before; the rib is
       // now nominal.
       //
       // The trailing 0 is corner_tolerance, and it is a literal for the same reason the
       // greeble tolerance above is: the socket this cuts is nominal by construction, and the
       // clearance on the flat and diagonal faces is taken entirely on the corner. Passing
       // anything else here would apply it twice. OQ-DES-C5.
       corner_end(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, 0, extrusion_width, eps, 0);
        
        // Longeron opening cutout: the mouth the longeron snaps in through, which is
        // what makes the greeble a C rather than a closed ring. greeble_opening_angle is
        // a HALF-angle -- the vertices below sit at 45-a and 45+a, so a=35 removes 70
        // degrees centred on the diagonal. The chord across that mouth is 57% of the
        // tube diameter, so the tube spreads the arms and snaps home rather than
        // dropping through. The angle was arrived at by experiment; it is tuned, not
        // derived. See doc/design/bulkhead.md.
        linear_extrude(height=through_cut(bulkhead_thickness), center=true, convexity=3,twist=0,slices=1,scale=1){
            polygon([[0,0],[sin(45-greeble_opening_angle)*corner_radius,cos(45-greeble_opening_angle)*corner_radius],[cos(45-greeble_opening_angle)*corner_radius,sin(45-greeble_opening_angle)*corner_radius]]);
        }
        
        // Clean up the outer faces of the corner cutout.
        //
        // The radius is the flange's finished outer surface, flush behind the panel, with NO
        // eps: it is a material face, not a cut overshoot, and an eps here cut it 0.01 mm too
        // deep. That went unnoticed for as long as it did because the only material in reach
        // of the overcut was the bulkhead's overhang over the corner, which the corner's short
        // rectangular extension used to create -- fixed there, so this now removes nothing
        // measurable. Both halves of that are OQ-DES-B13.
        //
        // The outboard limit stays -(panel_offset+panel_overlap) = flat_x, untoleranced. That
        // is the corner/bulkhead interface itself, cut into both parts by the same polygon,
        // so the cleanup already stops exactly at the joint.
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
            
            // Until 2026-08-08 the last three arguments were passed rotated --
            // (flange_thickness, flange_chamfer, plate_thickness) into
            // (plate_thickness, flange_thickness, flange_chamfer). OpenSCAD matches
            // positionally and says nothing, and plate_thickness and flange_thickness are
            // both 0.8 at the driver's settings, so one of the three landed correctly by
            // coincidence and the part looked right. The diagonal web was built 25%
            // thicker than flange_thickness intends, and would have changed shape for no
            // apparent reason the first time layer height or extrusion width moved.
            // The names are the interface; the old alignment was the accident.
            // See OQ-DES-B10 in doc/design/bulkhead.md.
            greeble_bolt_web(bulkhead_thickness, bolt_offset, plate_thickness, flange_thickness, flange_chamfer);
            
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
