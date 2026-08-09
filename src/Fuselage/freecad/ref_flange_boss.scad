// The quadrant boss block of bulkhead_flange_positive -- the ring of flange material around
// the longeron, chamfered out into the plate, kept only in the corner quadrant.
//
// Unlike the other ref_*.scad, this one does NOT call a module: the source builds this block
// inline inside bulkhead_flange_positive (fuselage_bulkhead_geometry.scad, the make_web
// branch), so there is nothing to `use`. The code below is a transcription, which means this
// file on its own only checks the port against the transcription. The binding check is the
// assembled bulkhead_flange_positive comparison, which does go through the real module.
//
// Derived parameters for U=1.0 end_bolt 3/16in, make_web = true.
$fa=1;
$fs=0.05;

bulkhead_thickness = 6;
panel_offset = 2.5;
panel_overlap = 4.7625;
panel_tolerance = 0.1;
plate_thickness = 0.8;
flange_thickness = 1.2;
flange_chamfer = 1.0;

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
