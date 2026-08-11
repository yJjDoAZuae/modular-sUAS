// mirror_xy() lives here. This file had no includes and open-coded that union three
// times; fuselage_bulkhead_geometry.scad already includes both files, so the module
// was always available there and only missing when corner geometry is used on its own
// -- which is exactly how the sweep uses it.
include <shape_modifier_utils.scad>

// Greeble dimensions, derived rather than passed in. corner_end() and
// corner_transition() computed all of these identically, so the two could drift apart
// silently -- and the greeble is a mating feature, where the two halves must agree
// exactly or the parts do not assemble.
//
// These radii describe the joint, not one part of it. The greeble itself is the
// positive post on the *bulkhead*: bulkhead_section() subtracts corner_end() from the
// bulkhead, so bulkhead material survives exactly where the corner has none. Read from
// the corner's side -- which is where these functions are used -- the same radii are a
// bore and an internal groove.

// Radius of the greeble body: the longeron, its clearance, the greeble wall, and the
// fit tolerance. The post on the bulkhead; the bore in the corner.
function greeble_radius_of(longeron_radius, longeron_tolerance, greeble_thickness,
                           greeble_tolerance) =
    longeron_radius + longeron_tolerance + greeble_thickness + greeble_tolerance;

// The snap feature, one wall thickness out from the body -- a rib around the bulkhead's
// post, a groove in the corner's bore. Written in terms of greeble_radius_of() rather
// than repeating the sum, so that relationship is explicit and cannot be broken by
// editing one and not the other.
function greeble_nub_radius_of(longeron_radius, longeron_tolerance, greeble_thickness,
                               greeble_nub_thickness, greeble_tolerance) =
    greeble_radius_of(longeron_radius, longeron_tolerance, greeble_thickness,
                      greeble_tolerance) + greeble_nub_thickness;

// The snap feature occupies the middle third of the bulkhead's thickness, leaving a
// third of lead-in either side for the joint to ride over as it engages.
function greeble_nub_height_of(bulkhead_thickness) = bulkhead_thickness/3;

module fuselage_corner(U, unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, extrusion_width) {


    union() {
    corner_middle(unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, extrusion_width);
    corner_transition(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, extrusion_width);
    corner_end(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, extrusion_width);
        translate([0,0,unit_length]) {
            mirror([0,0,1]) {
                union() {    
                    corner_middle(unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, extrusion_width);
                    corner_transition(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, extrusion_width);
                    corner_end(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, extrusion_width);
                }
            }
        }
    }
}


// `overshoot` extends this section past both of its nominal faces, for callers that use it
// as a CUT TOOL and need it to pass cleanly through the material it forms. It moves the
// extrusion and the greeble bore only. It must never be folded into bulkhead_thickness.
//
// It used to be, and that was OQ-DES-B12: bulkhead_section() asked for overshoot by calling
// this module with `bulkhead_thickness + 2*eps` and shifting the result down by eps. That
// buys the overshoot, but bulkhead_thickness ALSO drives greeble_nub_height (= bt/3) and
// every nub z level, so the socket's snap rib came out at 2.00667 mm against the corner
// post's 2.00000 -- about 0.0033 mm of gap at each end of a snap the design requires to be
// nominal. The design carries all greeble clearance once, on the corner's bore; this was a
// second, unasked-for clearance, and it was invisible because the -eps shift re-centred the
// nub band and left only its height wrong.
//
// So: one argument, one meaning. bulkhead_thickness is the thickness and sizes the rib.
// overshoot is slop for the boolean and sizes nothing.
module corner_end(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, extrusion_width, overshoot = 0) {
    
    eps = geometry_eps();
    
    longeron_chamfer = extrusion_width;
    greeble_nub_height = greeble_nub_height_of(bulkhead_thickness);
    greeble_radius = greeble_radius_of(longeron_radius, longeron_tolerance,
                                       greeble_thickness, greeble_tolerance);
    greeble_nub_radius = greeble_nub_radius_of(longeron_radius, longeron_tolerance,
                                               greeble_thickness, greeble_nub_thickness,
                                               greeble_tolerance);
    
    difference() {
        translate([0,0,-overshoot]) {
            linear_extrude(height=bulkhead_thickness+eps+2*overshoot,center=false,convexity=3,twist=0,slices=1) {
                mirror_xy() {
                    corner_middle_shape(corner_radius, panel_thickness, longeron_radius, panel_offset, panel_overlap, longeron_chamfer, longeron_tolerance, panel_tolerance);
                }
            }
        }
    
        cylinder(h=through_cut(bulkhead_thickness),r1=greeble_radius, r2=greeble_radius, center=true);
        
        rotate([0,0,45]){
            translate([-(greeble_radius),0,0]) {
                cube([2*(greeble_radius),2*(greeble_radius), through_cut(bulkhead_thickness)], center = true);
            }
        }
        difference() {
            rotate_extrude(angle = 360, convexity = 2) {
                // the four nub vertices are dimensioned from bulkhead_thickness and must
                // stay that way; only the two end pairs carry the overshoot
                polygon(
                    [[0,-overshoot], 
                    [greeble_radius,-overshoot],
                    [greeble_radius,bulkhead_thickness/2 - greeble_nub_height/2-greeble_nub_thickness],
                    [greeble_nub_radius,bulkhead_thickness/2 - greeble_nub_height/2],
                    [greeble_nub_radius,bulkhead_thickness/2 + greeble_nub_height/2],
                    [greeble_radius,bulkhead_thickness/2 + greeble_nub_height/2+greeble_nub_thickness],
                    [greeble_radius,bulkhead_thickness+overshoot,],
                    [0,bulkhead_thickness+overshoot]] 
                );
            }
            rotate([0,0,-45]) {
                linear_extrude(height = through_cut(bulkhead_thickness), center=true, convexity=3,twist=0,slices=1) {
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

module corner_transition(U, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, greeble_thickness, greeble_nub_thickness, greeble_tolerance, extrusion_width) {
    
    eps = geometry_eps();
    
    longeron_chamfer = extrusion_width;
    greeble_nub_height = greeble_nub_height_of(bulkhead_thickness);
    greeble_radius = greeble_radius_of(longeron_radius, longeron_tolerance,
                                       greeble_thickness, greeble_tolerance);
    greeble_nub_radius = greeble_nub_radius_of(longeron_radius, longeron_tolerance,
                                               greeble_thickness, greeble_nub_thickness,
                                               greeble_tolerance);
    
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


module corner_middle(unit_length, bulkhead_thickness, corner_radius, panel_thickness, panel_offset, panel_overlap, panel_tolerance, longeron_radius, longeron_tolerance, extrusion_width) {
    
    eps = geometry_eps();
    longeron_chamfer = extrusion_width;
    
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
            
            // bulkhead boundary. The trailing vertices only have to sit off the part;
            // mask_reach() states that intent and single-sources the distance.
            far = mask_reach(corner_radius);

            polygon(points = [
            [flat_x,corner_radius],  // top inner edge of the panel interface
            [flat_x,flat_y],
            [flat_offset,0],
            [0,flat_offset],
            [flat_y,flat_x],
            [0,-far],
            [-far,-far],
            [-far,far]]);
            
            // diagonal mirror line mask
            polygon(points = [[-far,-far],[far,far],[far,-far]]);
            
            // longeron chamfer
            polygon(points = [[0,0.0],[-far,0.0],[-far,-far],[0,-far]]);
            
        }

    }
}

