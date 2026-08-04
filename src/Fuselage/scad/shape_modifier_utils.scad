
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
