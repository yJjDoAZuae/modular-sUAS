
module octant_to_full() {
    mirror_x() {
        mirror_y() {
            mirror_xy() {
                children();
            }
        }
    }
}

module mirror_x() {
    union() {
        children();
        mirror([-1,0,0]) {
            children();
        }
    }
    
}

module mirror_y() {
    union() {
        children();
        mirror([0,-1,0]) {
            children();
        }
    }
    
}

module mirror_xy() {
    union() {
        children();
        mirror([1,-1,0]) {
            children();
        }
    }
}

module corner_translate(unit_width, corner_radius) {
    translate([unit_width/2-corner_radius,unit_width/2-corner_radius,0]) {
        children();
    }
}

// Move an octant out to its corner, then mirror it into all four -- the standard way
// a bulkhead profile is built from the one octant that is actually drawn.
//
// Every `*_shape` wrapper in fuselage_bulkhead_geometry.scad had this same pair open-
// coded around its own `*_octant` call. The wrappers stay: they name the full shape as
// distinct from the octant, and they are what seven call sites across two files use.
// It is the repeated body that is worth removing, not the interface.
module octant_tiled(unit_width, corner_radius) {
    octant_to_full() {
        corner_translate(unit_width, corner_radius) {
            children();
        }
    }
}


// mask lower diagonal quadrant
module octant_mask(unit_width, corner_radius) {
    eps = 0.01;
    polygon([[corner_radius+eps,corner_radius],
            [corner_radius+eps,-unit_width/2-corner_radius],
            [-unit_width/2-corner_radius+eps,-unit_width/2-corner_radius]]);
}

// fillet inward
module fillet_inner(radius) {
    intersection() {
        offset(r = -radius) {
            // fillet outward as well to ensure we round off any inward fillet artifacts (from input boundaries that are closer than 2*radius)
            offset(r = 2*radius) {
                offset(r = -radius) {
                    children();
                }
            }
        }
        // guarantee that the resultant shape has not gone outside the boundaries of the input shape
        children();
    }
}

// fillet outward
module fillet_outer(radius) {
    union() {
        offset(r = -radius) {
            offset(r = radius) {
                children();
            }
        }
        // guarantee that the resultant shape has not erroded into the boundaries of teh input shape
        children();
    }
}
