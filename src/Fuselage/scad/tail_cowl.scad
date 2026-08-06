
use <cowl_geometry.scad>

// draft settings
$fa=15;
$fs=0.5;
// publish settings
//$fa=1;
//$fs=0.1;


U = 1;

unit_width = U*100;
//tail_len = U*100;
cut_len = 0;

cone_angle = 35;
flange_inset = 0.5;
tail_flange_height = 1.0;

buttress_z_offset = U*2;
buttress_r_inset = U*5;
buttress_thickness = 0.05;

side_buttress_z_end = U*25;
side_buttress_r_start = U*0;
side_buttress_r_end = U*23.3; // U*32.1;

top_buttress_z_end = U*3;
top_buttress_r_start = U*0;
top_buttress_r_end = U*0;

top_diag_buttress_z_start = U*20;
top_diag_buttress_depth = U*2;

bottom_buttress_z_end = U*20;
bottom_buttress_r_start = U*0;
bottom_buttress_r_end = U*28.8; // U*38.3;

// Relative to scad/, because the import() lives in cowl_geometry.scad and OpenSCAD
// resolves it against the file containing the call. This is the same prefix
// oml_ref() adds in fuselage_variants.py -- keep the two in step.
oml_filename = "../oml/vsp_tail.stl";
oml_scale = 1e-3;
oml_length = 0.1;
oml_offset_x = -0.25;
oml_reversed = true;

tail_cowl(U, unit_width, oml_filename, oml_scale, oml_length, oml_offset_x, oml_reversed, cut_len, buttress_thickness, buttress_z_offset, buttress_r_inset, side_buttress_z_end, side_buttress_r_start, side_buttress_r_end, top_buttress_z_end, top_buttress_r_start, top_buttress_r_end, bottom_buttress_z_end, bottom_buttress_r_start, bottom_buttress_r_end, top_diag_buttress_depth, top_diag_buttress_z_start, cone_angle);
