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

// The collet that grips the boom, with the tab that keys it against rotation.
//
// **The four corners are true fillets, constructed directly.** This module used to reach the
// same shape morphologically, as
//
//     fillet_outer(r) { fillet_inner(r) { circle ∪ tab } }
//
// and reading that pair is what makes the direct form obvious. `fillet_inner` is an *opening*
// clipped to its input, so it rounds the tab's two **convex** top corners; `fillet_outer` is a
// *closing* unioned with its input, so it fills the two **concave** junctions where the tab
// side meets the collet. That is four arcs of one radius at four computable centres, and
// nothing else. Written directly, the radius is a dimension rather than the by-product of six
// chained offsets, and it does not degrade where features crowd.
//
// OQ-DES-B9 asked whether such a fillet or the morphological result is the authority and chose
// the fillet; OQ-DES-B11 scoped that answer, because the boom bulkhead's *other* three
// `fillet_inner` uses wrap whole compound regions rather than named corners and keep the
// morphological chain. This module is the one place here that is unambiguously a corner round.
//
// **Validity.** The construction is exact only inside its domain, and the domain is a design
// statement rather than a numerical convenience. `boom_key_validity_check()` in
// tools/fuselage_variants.py enforces it; the geometry here assumes it:
//
//   * `boom_key_width  >= 2*boom_key_radius` — two arcs of `radius` have to fit across the
//     tab. Below it the morphological form did not merely round the tab, it **deleted** it:
//     an opening removes any protrusion thinner than twice its radius.
//   * `boom_key_height >= 2*boom_key_radius` — the same along the protrusion, and it is also
//     what holds the junction fillets clear of the cap fillets: the junction tangent point is
//     at most `collet_radius + radius` and the cap starts at `collet_radius + height - radius`.
//   * `boom_key_width  <  2*collet_radius` — narrower than the **hole the collet passes
//     through**, not than the boom. Design limit and singularity coincide here: `yc` below is
//     `sqrt((cr + r)^2 - (w/2 + r)^2)`, which goes imaginary at exactly `w = 2*cr`, where the
//     tab spans the hole and the junctions being filleted no longer exist.
module boom_key_shape(boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness, boom_key_width, boom_key_height, boom_key_radius, boom_key_angle, boom_tolerance) {

    collet_radius = boom_diameter/2 + boom_collet_thickness + boom_tolerance;

    mirror_x() {

        translate([boom_y_position, boom_z_position]) {

            rotate([0,0,boom_key_angle]) {
                boom_key_profile(collet_radius, boom_key_width, boom_key_height,
                                 boom_key_radius);
            }
        }
    }
}

// One keyed collet: the circle, the tab, the tab's two rounded top corners and the two
// junction gussets. Drawn in the key's own frame, tab pointing +y.
module boom_key_profile(collet_radius, key_width, key_height, radius) {

    a = key_width/2;
    y_top = collet_radius + key_height;

    union() {

        circle(r = collet_radius);

        // the tab, up to the height where its top corners start to round
        translate([-a, 0]) {
            square([key_width, y_top - radius], center=false);
        }

        // those corners: the hull of the two arc centres is the rounded cap, exactly
        hull() {
            translate([ a - radius, y_top - radius]) { circle(r = radius); }
            translate([-a + radius, y_top - radius]) { circle(r = radius); }
        }

        boom_key_junction_fillet(collet_radius, a, radius);
        mirror([1,0,0]) { boom_key_junction_fillet(collet_radius, a, radius); }
    }
}

// The gusset filling one tab-to-collet junction.
//
// The fillet arc is tangent to the collet externally and to the tab side, which puts its
// centre at distance `collet_radius + radius` from the collet centre and `radius` clear of
// the side — so at (a + radius, yc), with yc from Pythagoras. The gusset is everything in the
// notch *outside* that arc.
//
// It is bounded exactly by the box [a, a+radius] x [ty, yc], where ty is the height of the
// tangent point on the collet. That box needs no clipping of its own: its right edge and top
// edge lie wholly inside the arc, its bottom edge lies inside the collet up to the tangent
// point and inside the arc beyond it, and its remaining corner (a, sqrt(cr^2 - a^2)) is the
// junction itself, which is in the box whenever a <= cr. So subtracting the collet and the arc
// from the box leaves the gusset and nothing else.
module boom_key_junction_fillet(collet_radius, a, radius) {

    cr = collet_radius;
    yc = sqrt((cr + radius)*(cr + radius) - (a + radius)*(a + radius));
    ty = yc * cr / (cr + radius);

    difference() {
        translate([a, ty]) { square([radius, yc - ty], center=false); }
        circle(r = cr);
        translate([a + radius, yc]) { circle(r = radius); }
    }
}
