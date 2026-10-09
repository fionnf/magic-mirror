// =====================================================================
// Logitech C270 webcam box for the P4 LED frame (top-centre, looks 15 deg down)
// Camera with its clip removed slides in from the back; the lid CLICKS shut
// (two snap tongues in the side walls) and its pads lock the camera. Two mounts:
//   mount = "clip" : peg into the window of the standard middle top rail + 1 zip tie
//   mount = "rail" : 2 x M3 into the pads of the full-frame top-mount rail
// part = "body" | "lid" | "plate" | "assembly"
// Print the body FRONT-DOWN (window on the bed), the lid outer-face-down. No supports.
// Default camera size = C270 body WITHOUT clip - measure yours and adjust cam_*.
// =====================================================================
part  = "plate";
mount = "clip";

cam_w = 73.0;   cam_h = 32.0;   cam_d = 24.0;   cam_r = 12;  // body (pill-shaped ends, from the photo); depth assumed - measure
lens_dx = 15;   lens_dy = 0;    // lens sits 15 mm off-centre (to the left seen from the front), from the photo
cl    = 0.4;    tilt = 15;      // pocket clearance, look-down angle
fov_h = 24.4 + 4;  fov_v = 14.3 + 4;   // half angles (55 deg dFOV, 16:9) + margin

// snap fit: tongues on the lid flex into slots in the thick side walls
snap_x0 = cam_w/2 + cl;        // slot opens onto the camera channel (tongue can flex inward)
tng_t = 1.6;  tng_w = 10;  tng_l = 12;  bump = 0.8;  snap_cl = 0.2;
tng_x = snap_x0 + 1.1;         // tongue inner face
wall = 2.6;  front_t = 2.4;  floor_t = 3;  roof_t = 2.5;  lid_t = 3;  press = 0.3;
W  = cam_w + 2*cl + 2*6;       // side walls thick enough for the lid screws
// camera front-face centre in box coords (x centred, y up from the frame top edge, z from the front face)
zf = front_t + cl + (cam_h/2)*sin(tilt) + 0.6;
yc = floor_t + cl + (cam_h/2)*cos(tilt);
Db = ceil(zf + (cam_h/2)*sin(tilt) + cam_d*cos(tilt) + cl + 1);    // body depth (lid on top)
Hb = ceil(yc + (cam_h/2)*cos(tilt) + cam_d*sin(tilt) + cl + roof_t);
D  = Db + lid_t;
echo(str("C270 box: ", W, " x ", Hb, " x ", D, " mm (w x h x depth)"));

// frame interface (matches p4_frame_v3: 46 mm frame, middle top rail)
z_front = -18;                 // frame z of the box front face (panel face is at -14)
peg_x = -36.3;   cab_x = 28;   // clip mount: peg window left of centre, cable window right of centre
pad_x = 16;      pad_z = 10;   // rail mount: screw pads of rail_top_mount

$fn = 48;
module rr(w, h, r) { offset(r) square([w-2*r, h-2*r], center=true); }
module cam_tf() { translate([lens_dx*0, yc, zf]) rotate([-tilt,0,0]) children(); }   // camera frame: front-face centre, +z = backwards
module cam_body(extra=0, back=0) {      // camera envelope (+ sweep out of the back for insertion)
  cam_tf() translate([0,0,-extra]) linear_extrude(cam_d + 2*extra + back) rr(cam_w+2*extra, cam_h+2*extra, cam_r+extra);
}
module teardrop2d(r) { hull() { circle(r=r); polygon([[-r*0.7071, r*0.7071],[r*0.7071, r*0.7071],[0, r*1.4142]]); } }
module lid_screws() { for (sx=[-1,1], yy=[6, Hb-6]) translate([sx*(W/2-3.2), yy]) children(); }

module body() {
  difference() {
    translate([0, Hb/2, 0]) linear_extrude(Db) rr(W, Hb, 4);
    cam_body(cl, 80);                                                  // pocket + back insertion sweep
    // lens window: flares at the field of view (plus margin) toward the outside
    cam_tf() translate([lens_dx, lens_dy, 0]) hull() {
      translate([0,0,1]) linear_extrude(0.01) square([30, 18], center=true);
      translate([0,0,-12]) linear_extrude(0.01) square([30 + 2*13*tan(fov_h), 18 + 2*13*tan(fov_v)], center=true);
    }
    for (sx=[-1,1]) mirror([sx<0 ? 1 : 0,0,0]) {
      // tongue slot from the back face, open to the camera channel
      translate([snap_x0-0.01, Hb/2-tng_w/2-snap_cl, Db-tng_l-0.5]) cube([tng_x+tng_t+snap_cl-snap_x0, tng_w+2*snap_cl, tng_l+1]);
      // catch: 45 deg on both sides -> clicks in, prints without support, opens with a firm pull
      translate([0, Hb/2-tng_w/2-snap_cl, 0]) rotate([90,0,0]) mirror([0,0,1]) linear_extrude(tng_w+2*snap_cl)
        translate([tng_x+tng_t, Db]) polygon([[0,-tng_l-0.2],[bump+snap_cl,-tng_l+bump+0.2-0.2+snap_cl],[bump+snap_cl,-tng_l+bump+1.6+snap_cl],[0,-tng_l+2*bump+1.6+2*snap_cl]]);
      // pry notch at the lid edge
      translate([W/2-1.2, Hb/2-4, Db-1.2]) cube([2, 8, 2]);
    }
    if (mount == "clip") {
      // cable channel down to the rail window, open to the lid (lay the cable in, plug stays outside the box)
      translate([cab_x-3.2, -1, Db-12]) cube([6.4, yc, 13]);
      translate([cab_x+6, -1, Db-9]) cube([4, floor_t+2, 5]);       // zip-tie slot
    } else {
      translate([-3.2, -1, Db-14]) cube([6.4, yc, 15]);              // cable channel into the rail's centre window
      for (sx=[-1,1]) {                                               // M3 into the rail pads + driver access through the roof
        translate([sx*pad_x, floor_t+1, pad_z - z_front]) rotate([90,0,0]) linear_extrude(floor_t+2) teardrop2d(1.7);
        translate([sx*pad_x, Hb+1, pad_z - z_front]) rotate([90,0,0]) linear_extrude(roof_t+2) teardrop2d(3.2);
      }
    }
  }
  if (mount == "clip")   // peg down into the rail window (frame z 6..16 at the root, 45 deg back face)
    translate([peg_x, 0, 0]) rotate([0,90,0]) rotate([0,0,90]) linear_extrude(6, center=true)
      polygon([[0.01, 6-z_front],[0.01, 16-z_front],[-6, 12-z_front],[-6, 6-z_front]]);
}

module lid() {
  difference() {
    union() {
      translate([0, Hb/2, 0]) linear_extrude(lid_t) rr(W, Hb, 4);
      // pusher pads at both ends of the camera (centre left free for the cable): fill the sweep behind the camera
      intersection() {
        translate([0,0,lid_t+Db]) mirror([0,0,1]) difference() {
          intersection() {
            cam_body(cl-0.2, 80);                                     // the insertion channel behind the camera
            cam_tf() translate([-100,-100,cam_d-press]) cube([200,200,200]);   // starts press mm INSIDE the camera back
          }
          translate([-cam_w/2+12, -50, -50]) cube([cam_w-24, 200, 200]);    // centre left free for the cable
        }
        translate([-W/2, 0, lid_t-0.01]) cube([W, Hb, Db]);
      }
    }
  }
  for (sx=[-1,1]) mirror([sx<0 ? 1 : 0,0,0]) translate([0, Hb/2-tng_w/2, 0]) rotate([90,0,0]) mirror([0,0,1]) linear_extrude(tng_w)
    polygon([[tng_x, lid_t-0.01],[tng_x+tng_t, lid_t-0.01],
             [tng_x+tng_t, lid_t+tng_l-2*bump-1.6],[tng_x+tng_t+bump, lid_t+tng_l-bump-1.6],
             [tng_x+tng_t+bump, lid_t+tng_l-bump],[tng_x+tng_t, lid_t+tng_l],[tng_x, lid_t+tng_l]]);
}

if (part == "body") body();
else if (part == "lid") lid();
else if (part == "plate") { body(); translate([W+6, 0, 0]) lid(); }
else {                      // assembly preview in box coords
  color("Orange") body();
  color("Gold") translate([0,0,D]) mirror([0,0,1]) lid();
  color("DimGray") cam_body(0, 0);
}
