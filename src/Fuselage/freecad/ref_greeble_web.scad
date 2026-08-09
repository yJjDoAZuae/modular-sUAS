// greeble_bolt_web on its own. This module was the one checked against an ad-hoc render
// rather than a file in this directory, so its number could not be reproduced from the
// repository; this makes it a reference like every other ported module's.
//
// Derived parameters for U=1.0 end_bolt 3/16in -- note plate_thickness 0.8 and
// flange_thickness 1.2 are distinct here, which the hand driver's equal values hide.
$fa=1;
$fs=0.05;

use <../scad/fuselage_bulkhead_geometry.scad>

bulkhead_thickness = 6;
bolt_offset = 8.0;
plate_thickness = 0.8;
flange_thickness = 1.2;
flange_chamfer = 1.0;

greeble_bolt_web(bulkhead_thickness, bolt_offset, plate_thickness, flange_thickness,
                 flange_chamfer);
