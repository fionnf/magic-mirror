// =====================================================================
// "Roaming" touch box - 40 x 40 x 10 mm, capacitive touch sensor behind
// an ultra-thin printed front skin. Screws shut (4 x M2 x 8), single cable
// exit clamped between body and lid (built-in strain relief).
//   part = "body" | "lid" | "plate" | "assembly"
// Print the body FRONT-DOWN (skin on the bed = smooth face), lid outer-face-down.
// No supports. Print the front skin solid (it is only skin_t thick).
// =====================================================================
part = "plate";
explode = 0;                      // assembly preview only

W = 40;  D = 10;  r = 4;          // outer size, total depth, corner radius
wall   = 1.6;
skin_t = 0.6;                     // ultra-thin front: 3 layers at 0.2 mm (0.4 = 2 layers, more sensitive, more fragile)
lid_t  = 2;
lip_h  = 1.2;  lip_cl = 0.2;

// touch sensor board (default: common TTP223 module 15 x 11 x 1.6, pad side against the skin)
sensor = "TTP223";                // "TTP223" or "PAD25" (25 x 25 mm large-pad module)
sb = (sensor == "PAD25") ? [25.4, 25.4] : [15.2, 11.2];
sb_t = 1.6;  sb_cl = 0.3;  rib_h = 1.0;  rib_t = 0.8;
press = 0.2;                      // pusher interference, keeps the pad pressed on the skin

// screws
scr_in = 4.2;                     // corner screw inset from the outer edge
pilot  = 1.6;  boss_d = 5;  scr_d = 2.3;  csk_d = 4.3;

// cable exit (e.g. 3-core 3.5 mm cable for VCC / GND / OUT), clamped 0.3 undersize
cable_d = 3.5;  clamp = 0.3;

$fn = 48;
inner_D = D - lid_t;              // body height (front skin + walls)

module rr(w, h, rad) { offset(rad) square([w-2*rad, h-2*rad], center=true); }
module corners() { for (sx=[-1,1], sy=[-1,1]) translate([sx*(W/2-scr_in), sy*(W/2-scr_in)]) children(); }

module body() {
  difference() {
    union() {
      difference() {
        linear_extrude(inner_D) rr(W, W, r);
        translate([0,0,skin_t]) linear_extrude(inner_D) rr(W-2*wall, W-2*wall, r-wall);
      }
      corners() cylinder(d=boss_d, h=inner_D);                       // screw bosses
      // sensor locating ribs on the back of the skin
      translate([0,0,skin_t-0.01]) linear_extrude(rib_h) difference() {
        square([sb[0]+2*sb_cl+2*rib_t, sb[1]+2*sb_cl+2*rib_t], center=true);
        square([sb[0]+2*sb_cl, sb[1]+2*sb_cl], center=true);
        for (sx=[-1,1]) translate([sx*(sb[0]/2+sb_cl+rib_t/2), 0]) square([rib_t+0.2, 4], center=true);   // finger gaps to lift the board
      }
    }
    corners() translate([0,0,skin_t+0.6]) cylinder(d=pilot, h=inner_D);
    // cable exit: U-slot from the top edge; the flat lid face squeezes the cable (strain relief)
    hull() for (zz=[inner_D-(cable_d-clamp)/2, inner_D+2])
      translate([0, -W/2-1, zz]) rotate([-90,0,0]) cylinder(d=cable_d-clamp, h=wall+2);
  }
}

module lid() {
  difference() {
    union() {
      linear_extrude(lid_t) rr(W, W, r);
      // locating lip that drops inside the walls
      translate([0,0,lid_t-0.01]) linear_extrude(lip_h) difference() {
        rr(W-2*wall-2*lip_cl, W-2*wall-2*lip_cl, r-wall-lip_cl);
        rr(W-2*wall-2*lip_cl-2.4, W-2*wall-2*lip_cl-2.4, 1);
        corners() circle(d=boss_d+1);
      }
      // 4 slightly flexible pushers on the sensor board corners
      for (sx=[-1,1], sy=[-1,1])
        translate([sx*(sb[0]/2-1.5), sy*(sb[1]/2-1.5), lid_t-0.01])
          cylinder(d=2.4, h=(inner_D - skin_t - sb_t) + press + 0.01);
    }
    corners() {
      translate([0,0,-0.01]) cylinder(d=scr_d, h=lid_t+lip_h+1);
      translate([0,0,-0.01]) cylinder(d1=csk_d, d2=scr_d, h=(csk_d-scr_d)/2+0.01);   // countersink (prints as 45 deg)
    }
    // clearance in the lip where the cable comes in
    translate([0, -W/2+wall+lip_cl+1.2, lid_t]) cube([cable_d+2, 4, 2*lip_h+1], center=true);
  }
}

module mock_sensor() { color("Green") translate([-sb[0]/2, -sb[1]/2, skin_t]) cube([sb[0], sb[1], sb_t]); }
module mock_cable()  { color("Black") translate([0, -W/2-15, inner_D-cable_d/2+clamp/2]) rotate([-90,0,0]) cylinder(d=cable_d, h=15+wall+3); }

if (part == "body") body();
else if (part == "lid") lid();
else if (part == "plate") { body(); translate([W+6, 0, 0]) lid(); }
else {   // assembly: front at z = 0, lid flipped on top
  color("Orange") body();
  color("Gold") translate([0,0,D+explode]) mirror([0,0,1]) lid();
  mock_sensor(); mock_cable();
}
