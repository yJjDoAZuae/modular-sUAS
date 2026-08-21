// Overlap used to break coincident faces in booleans. Subtracting a cut that lands
// exactly on a surface leaves zero-thickness geometry, which renders unpredictably and
// slices worse; every cut is extended by this much so the faces genuinely cross.
//
// A function rather than a variable: `use <...>` exports functions but not top-level
// variable assignments, and the sweep reaches these files through `use`. Twelve modules
// across four files each declared their own `eps = 0.01` before this existed.
function geometry_eps() = 0.01;

// Length for a *centred* cutting solid that must pass entirely through material of
// depth `extent`. A centred cut reaches half this each way, so the factor leaves 50%
// clearance beyond `extent` on both sides -- a cut that lands flush on a face produces
// a zero-thickness shell rather than a clean hole.
//
// Measured against the swept parameter space: the deepest thing any of these cuts must
// clear is one bulkhead_section, one bulkhead_thickness tall, so the margin is 0.5 *
// bulkhead_thickness everywhere and scales with the part. Interconnect bulkheads stack
// two sections, but each section's cuts are applied before stacking, so the stack is
// not what a cut has to span.
function through_cut(extent) = 3 * extent;

// Distance at which to place a mask vertex so it lies outside anything within `extent`
// of the origin. Used by the half-plane polygons that trim an octant down to its
// wedge, where the vertex position only has to be "far enough" to be off the part.
//
// Worst case across 412 valid combinations is 3.25 mm of clearance, at U=0.5 with 1 mm
// panel: the shape reaches panel_offset + panel_overlap = 6.75 mm while the mask sits
// at 10 mm. Positive everywhere, and the gap widens with U.
function mask_reach(extent) = 2 * extent;


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
    eps = geometry_eps();
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
