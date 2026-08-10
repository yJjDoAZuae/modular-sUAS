// Does Part::Offset2D reproduce OpenSCAD's offset(r=) and fillet_inner()?
//
// The bulkhead's web shape is built with `offset(r = -web_width)` and `fillet_inner(
// web_fillet_radius)`, and fillet_inner is itself three chained offsets plus an
// intersection. Everything downstream of that in the bulkhead depends on the two agreeing,
// so this isolates the question on a polygon with both convex and concave corners.
//
// **Sweep `shrink`; do not read one value.** The bottom bar is exactly 10 wide, so at
// shrink = 3 the chained erosion of shrink + fillet is exactly half of it, and the erosion
// of that bar is a hairline -- zero area, 20 mm long. The following dilation paints it into
// an 8 mm band, so this file's own answer at mode = 4 runs 573.97 at shrink = 2.999,
// 453.82 at 3.000 and 381.04 at 3.001, against a few units per 0.02 everywhere else. A
// value read only at shrink = 3 is a reading off a knife edge, and was taken for a
// disagreement with FreeCAD for two days. See freecad/spike_offset2d.py.
//
// Extruded 1 mm, so the reported volume is the area.
$fa=1;
$fs=0.1;

include <../scad/shape_modifier_utils.scad>

shrink = 3;
fillet = 2;

module test_shape() {
    polygon([[0, 0], [40, 0], [40, 20], [25, 20], [25, 10], [10, 10], [10, 30], [0, 30]]);
}

mode = 0;   // 0 = raw, 1 = offset only, 2 = offset + fillet_inner

linear_extrude(height = 1) {
    if (mode == 0) {
        test_shape();
    } else if (mode == 1) {
        offset(r = -shrink) { test_shape(); }
    } else if (mode == 2) {
        fillet_inner(fillet) { offset(r = -shrink) { test_shape(); } }
    } else if (mode == 3) {
        // fillet_inner step 1
        offset(r = -fillet) { offset(r = -shrink) { test_shape(); } }
    } else if (mode == 4) {
        // fillet_inner step 2
        offset(r = 2*fillet) { offset(r = -fillet) { offset(r = -shrink) { test_shape(); } } }
    } else if (mode == 5) {
        // fillet_inner step 3, before the intersection with the input
        offset(r = -fillet) { offset(r = 2*fillet) { offset(r = -fillet) {
            offset(r = -shrink) { test_shape(); } } } }
    }
}
