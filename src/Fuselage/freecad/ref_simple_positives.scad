// The six positives of bulkhead_section that are plain solids of revolution or boxes:
// the bolt boss and its web and chamfer, the plate, and the longeron flange and its chamfer.
// Isolated so the port can be checked against them before the fillet modules are attempted.
//
// Derived parameters for U=1.0 end_bolt 3/16in, from the .scad that render_variant.py emits.
// The three named modules are called; the three built inline in bulkhead_section are
// transcribed, and that transcription is checked when the whole module is compared.
$fa=1;
$fs=0.05;

use <../scad/fuselage_bulkhead_geometry.scad>

bulkhead_thickness = 6;
corner_radius = 10.0;
bolt_hole_radius = 2.0;
bolt_thickness = 3.0;
bolt_offset = 8.0;
plate_thickness = 0.8;
web_width = 3.0;
flange_chamfer = 1.0;
panel_overlap = 4.7625;
longeron_radius = 2.0;

union() {
    bolt_flange_positive(bulkhead_thickness, bolt_hole_radius, bolt_thickness, bolt_offset);
    bolt_flange_fillet(bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness,
                       flange_chamfer);
    bolt_web(bolt_hole_radius, bolt_thickness, bolt_offset, plate_thickness, web_width);

    // inline in bulkhead_section: the plate
    linear_extrude(height = plate_thickness, center = false, convexity = 2) {
        polygon([[0, 0], [0, corner_radius], [-panel_overlap, corner_radius],
                 [-panel_overlap, 0]]);
    }

    // inline in bulkhead_section: the longeron flange and its chamfer
    cylinder(h = bulkhead_thickness, r = longeron_radius + bolt_thickness, center = false);
    translate([0, 0, plate_thickness]) {
        cylinder(h = flange_chamfer,
                 r1 = longeron_radius + bolt_thickness + flange_chamfer,
                 r2 = longeron_radius + bolt_thickness, center = false);
    }
}
