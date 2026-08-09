
use <cowl_geometry.scad>

// draft settings
$fa=15;
$fs=0.5;
// publish settings
//$fa=1;
//$fs=0.1;

U = 1;

plate_diam = U*60;
plate_tol = 0.1;
plate_thickness = 0.8;
plate_flange_width = 2;
cone_angle = 35;

nose_len = U*50;
cut_len = U*6;
unit_width = U*100;
nose_flange_inset = 0.5;
nose_flange_height = 1.0;
plate_flange_height = 1.0;

buttress_z_offset = U*2;
buttress_r_start = U*0;
buttress_r_end = U*6.6;
buttress_r_inset = U*3;
buttress_thickness = 0.05;

// Relative to scad/, because the import() lives in cowl_geometry.scad and OpenSCAD
// resolves it against the file containing the call. This is the same prefix
// oml_ref() adds in fuselage_variants.py -- keep the two in step.
oml_filename="../oml/vsp_nose.stl";
oml_scale_m_per_mm=1e-3;
oml_length_m = 0.050;
oml_offset_x_m=0;
oml_reversed = false;


//cowl_octant();
//body_blank_octant_lower(U, unit_width, oml_filename, oml_scale_m_per_mm, oml_length_m, oml_offset_x_m, oml_reversed, cut_len);
//body_blank_full_lower(U, unit_width, oml_filename, oml_scale_m_per_mm, oml_offset_x_m, oml_reversed, cut_len);

//nose(U, unit_width, oml_filename, oml_scale_m_per_mm, oml_offset_x_m, oml_reversed, cut_len, nose_flange_height, nose_flange_inset, plate_diam, plate_thickness, plate_tol, cone_angle);

//mirror([0,0,-1]) {
//nose_plate(plate_diam, plate_thickness, plate_flange_width, plate_flange_height, cone_angle);
//}

nose_cowl(U, unit_width, oml_filename, oml_scale_m_per_mm, oml_length_m, oml_offset_x_m, oml_reversed, cut_len, buttress_thickness, buttress_z_offset, buttress_r_start, buttress_r_end, buttress_r_inset, cone_angle);

//assembly_tool(U, unit_width, oml_filename, oml_scale_m_per_mm, oml_offset_x_m, oml_reversed, cut_len, plate_diam, plate_tol);





