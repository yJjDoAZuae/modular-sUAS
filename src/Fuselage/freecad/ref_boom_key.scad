// OQ-DES-B11: the key's direct fillet construction against the morphological one it replaces.
//
// `boom_key_shape` now builds its four corners as true fillets. The shape it replaced was
//
//     fillet_outer(r) { fillet_inner(r) { circle ∪ tab } }
//
// which is an opening (rounding the tab's two convex top corners) followed by a closing
// (filleting the two concave tab-to-collet junctions). The two forms should agree to
// tessellation, and the point of this file is to check that across the swept parameter space
// rather than at one size -- the same discipline ref_offset2d.scad exists to enforce.
//
// The morphological form is kept here, and only here, because it is the thing being measured
// against. It is not a second implementation: nothing includes this file.
//
// Extruded 1 mm, so every reported volume is an area. Modes 2 and 3 are the two halves of the
// symmetric difference, and both must be ~0 -- comparing total areas alone would let equal
// amounts of added and removed material cancel.
$fa=1;
$fs=0.1;

include <../scad/fuselage_boom_bulkhead_geometry.scad>

boom_diameter = 8.0;
boom_collet_thickness = 3.0;
boom_tolerance = 0.2;
boom_key_width = 2.0;
boom_key_height = 2.0;
boom_key_radius = 0.5;
boom_key_angle = 0.0;
boom_y_position = 0.0;
boom_z_position = 25.0;

mode = 0;

module key_direct() {
    boom_key_shape(boom_diameter, boom_y_position, boom_z_position, boom_collet_thickness,
                   boom_key_width, boom_key_height, boom_key_radius, boom_key_angle,
                   boom_tolerance);
}

// The historical morphological form, verbatim apart from indentation.
module key_morphological() {
    fillet_outer(boom_key_radius) {
        fillet_inner(boom_key_radius) {
            mirror_x() {
                translate([boom_y_position, boom_z_position]) {
                    rotate([0, 0, boom_key_angle]) {
                        union() {
                            circle(r = boom_diameter/2 + boom_collet_thickness + boom_tolerance);
                            translate([-boom_key_width/2, 0, 0]) {
                                square([boom_key_width,
                                        boom_diameter/2 + boom_collet_thickness
                                        + boom_tolerance + boom_key_height],
                                       center = false);
                            }
                        }
                    }
                }
            }
        }
    }
}

linear_extrude(height = 1) {
    if (mode == 0) {
        key_direct();
    } else if (mode == 1) {
        key_morphological();
    } else if (mode == 2) {
        // material the direct form adds
        difference() { key_direct(); key_morphological(); }
    } else if (mode == 3) {
        // material the direct form removes
        difference() { key_morphological(); key_direct(); }
    }
}
