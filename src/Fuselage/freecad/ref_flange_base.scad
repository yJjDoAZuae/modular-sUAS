// The two base polygons of bulkhead_flange_positive, isolated so the port's primitive
// decomposition can be checked against them.
//
// Parameters are the DERIVED values for U=1.0 end_bolt 3/16in -- read off the .scad that
// tools/render_variant.py generates, not from fuselage_bulkhead.scad, whose constants are
// one hand-written configuration and disagree with the sweep.
//
// The module builds these inline rather than through a named submodule, so they are
// transcribed here. That transcription is checked when the whole module is compared; this
// file only settles whether the polygons decompose into primitives, which is the question
// the FreeCAD port needs answered.
$fa=1;
$fs=0.05;

unit_width = 100.0;
corner_radius = 10.0;
panel_thickness = 4.7625;
panel_offset = 2.5;
panel_overlap = 4.7625;
panel_tolerance = 0.1;
bulkhead_thickness = 6;
flange_thickness = 1.2;

is_cowling = false;

x_start = -panel_tolerance - panel_offset - panel_overlap - flange_thickness;
y_start = max(x_start, -8.0);              // max(x_start, -bolt_offset), bolt_offset = 8

linear_extrude(height = bulkhead_thickness, center = false, convexity = 5) {
    union() {
        if (!is_cowling) {
            polygon([
                [0, 0],
                [0, corner_radius - panel_thickness - panel_tolerance],
                [-(unit_width/2 - corner_radius), corner_radius - panel_thickness - panel_tolerance],
                [-(unit_width/2 - corner_radius), corner_radius - panel_thickness - panel_tolerance - flange_thickness],
                [x_start, corner_radius - panel_thickness - panel_tolerance - flange_thickness],
                [x_start, y_start],
                [y_start, y_start]
            ]);
        }
        polygon([
            [0, 0],
            [0, corner_radius - panel_thickness - panel_tolerance],
            [-(unit_width/2 - corner_radius), corner_radius - panel_thickness - panel_tolerance],
            [-(unit_width/2 - corner_radius), corner_radius - panel_thickness - panel_tolerance - flange_thickness],
            [0, corner_radius - panel_thickness - panel_tolerance - flange_thickness]
        ]);
    }
}
