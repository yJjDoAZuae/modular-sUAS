$fa=1;
$fs=0.5;

FX = 1;
U = 1;

scale([FX*U,U,U]) {
rotate([0,90,0]) {
    difference(){
        minkowski()
        {
            cube(size = [80,80,80], center = true);
            cylinder(r=10,h=20, center = true);
        }
        union() {
            translate([40,40,0]) {
                cylinder(r=2,h=200, center = true);
            }
            translate([40,-40,0]) {
                cylinder(r=2,h=200, center = true);
            }
            translate([-40,40,0]) {
                cylinder(r=2,h=200, center = true);
            }
            translate([-40,-40,0]) {
                cylinder(r=2,h=200, center = true);
            }
            translate([32,32,0]) {
                cylinder(r=2,h=200, center = true);
            }
            translate([32,-32,0]) {
                cylinder(r=2,h=200, center = true);
            }
            translate([-32,32,0]) {
                cylinder(r=2,h=200, center = true);
            }
            translate([-32,-32,0]) {
                cylinder(r=2,h=200, center = true);
            }
        }
    }
}
}