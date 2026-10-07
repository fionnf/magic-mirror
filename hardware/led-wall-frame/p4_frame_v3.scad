// =====================================================================
// P4 64x64 (256 x 256 mm) LED panels - 3 x 4 mounting frame - v3
// 20 mm deep, prints support-free on a Prusa CORE One (250 x 220 x 270).
//
// v2: rails also screw into the panels' mid-edge / bottom-centre inserts
//     (slotted holes), elephant-foot chamfers on every mating bottom edge,
//     45 deg self-supporting keyhole + windows, engraved UP arrows.
//
// part = "junction" "edge" "corner" "edge_ear" "corner_ear"
//        "bracket_edge" "bracket_corner"
//        "rail_v_inner" "rail_h_inner" "rail_outer"
//        "fit_test" "plate_nodes_A" "plate_nodes_B" "plate_ears"
//        "plate_rails_A" "plate_rails_B" "plate_rails_C" "plate_rails_D"
//        "rail_top_mount" "rail_h_pi" "box_A_body" "box_A_lid" "box_B_body" "box_B_lid"
//        "plate_rails_C2" "plate_rails_D_top" "plate_box_A" "plate_pi_box_B"
//        "assembly"   (preview; variant = "A" or "B", explode = 0..1)
//
// v3 adds a top-centre enclosure:
//   A: 20 mm frame + box on top holding Raspberry Pi 5 (+ shield) and Camera Module 3
//   B: 46 mm frame (-D H=46) with the Pi 5 on a platform inside the frame,
//      small camera-only box on top
// Camera looks out through the box front, tilted cam_tilt degrees down.
// Print everything with z = 0 on the bed (panel side down).
// =====================================================================
part    = "assembly";
explode = 0;
variant = "A";
panel_alpha = 0.35;   // render setting
show_mocks = true;

// ---------- panel / layout ----------
panel = 256;  gap = 0.3;  edge = 8;  cols = 3;  rows = 4;
P  = panel + gap;
hs = edge + gap/2;            // 8.15  insert offset from a seam centre line
a  = hs + 8.5;                // 16.65 node half size

// ---------- depth / plates ----------
H = 20;  plate_t = 4;  bracket_t = 4;
ef = 0.4;                     // elephant-foot chamfer on mating bottom edges
ch = 0.8;  r = 5;

// ---------- screws ----------
screw_d = 3.3;  head_d = 6.4;  head_dep = 2.5;
cs_d = 6.4;  cs_h = (cs_d - screw_d)/2;   // 90 deg countersink for M3 flat heads (DIN 7991 / ISO 10642)
screw_L = 25;  engage = 5;          // panel screws: M3 x screw_L
head_z  = screw_L - engage;         // screw head height above the rim face
cb_on   = H > head_z + 0.5;         // deep frames: counterbore so M3x25 still reaches
cb_d    = 6.6;
tube_d  = cb_on ? 11 : 9;  flare_d = tube_d + 4;  flare_h = 3;
boss_d  = cb_on ? 11 : 10;  slot_play = 1.2;   // rail mid screws: slotted +-1.2 mm

// ---------- wall keyhole (junction nodes) ----------
slot_len = 8;  cw = 9.4;  sw = 4.8;  lip = 3;  chamber = 5.5;
taper_h = (cw - sw)/2;

// ---------- dovetails ----------
neck_w = 8;  head_w = 14;  tl_w = 10;     // interior seams
neck_n = 6;  head_n = 10;  tl_n = 8;      // perimeter
web_len = 10;  c = 0.1;  f = 0.3;          // c = dovetail clearance per side (was 0.2)
rail_L = P - gap/2 - 2*a - 2*f;           // 222.25
Ww = 22;  Wn = 16;  wall_t = 2.7;
deep = H >= 40;
old_windows = false;   // true = earlier 30 mm trapezoid windows (for checking add-ons)
win_len = (deep && !old_windows) ? 32 : 30;  mid_zone = 12;
win_side = 19;   // deep frames: vertical window sides up to this height (passes a 16-pin IDC plug)             // solid zone half-length around the mid screw

// ---------- brackets / engraving ----------
ear_out = 26;  wall_d = 5.5;  csk_d = 11;  engr = 0.6;

// =====================================================================
module rr(w, h, rad) { offset(rad) square([w-2*rad, h-2*rad], center=true); }
module rbox(x0, x1, y0, y1, rad) { translate([(x0+x1)/2,(y0+y1)/2]) rr(x1-x0, y1-y0, rad); }

module plate_body(x0, x1, y0, y1, rad) {
  hull() {
    linear_extrude(0.01) rbox(x0+ef, x1-ef, y0+ef, y1-ef, rad-ef);
    translate([0,0,ef]) linear_extrude(plate_t-ch-ef) rbox(x0, x1, y0, y1, rad);
    translate([0,0,plate_t-ch]) linear_extrude(ch) rbox(x0+ch, x1-ch, y0+ch, y1-ch, rad-ch);
  }
}
module post(x, y, ph) {
  translate([x, y, plate_t-0.01]) {
    cylinder(d1=flare_d, d2=tube_d, h=flare_h, $fn=64);
    cylinder(d=tube_d, h=ph-plate_t+0.01, $fn=64);
  }
}
module bore(x, y, ph) {
  translate([x, y, -0.01]) cylinder(d=screw_d, h=ph+0.02, $fn=48);
  if (ph == H) {
    zc = cb_on ? head_z : H;                          // head sits flush here
    translate([x, y, zc-cs_h]) cylinder(d1=screw_d, d2=cs_d, h=cs_h+0.01, $fn=48);
    if (cb_on) translate([x, y, head_z]) cylinder(d=cb_d, h=H, $fn=48);
  }
}
module up_arrow(x, y, z) {    // engraved triangle pointing +y
  translate([x, y, z-engr]) linear_extrude(engr+0.01) polygon([[-2.5,-1.5],[2.5,-1.5],[0,2.5]]);
}

// ---------- dovetail tenon (on nodes) ----------
module trap2d(nw, hw, tl) polygon([[0,-nw/2],[tl,-hw/2],[tl,hw/2],[0,nw/2]]);
module tenon(px, py, ang, nw, hw, tl, ph) {
  translate([px, py, 0]) rotate([0,0,ang]) {
    translate([-web_len, -nw/2, 0]) cube([web_len+0.01, nw, ph]);
    hull() {
      linear_extrude(0.01) offset(delta=-ef) trap2d(nw, hw, tl);
      translate([0,0,ef]) linear_extrude(H-ef) trap2d(nw, hw, tl);
    }
  }
}
module tenon_w(px,py,ang,ph) tenon(px,py,ang,neck_w,head_w,tl_w,ph);
module tenon_n(px,py,ang,ph) tenon(px,py,ang,neck_n,head_n,tl_n,ph);

// ---------- dovetail socket (in rails) ----------
function sd_(tl) = tl - f + 0.9;
function w0_(nw,hw,tl)  = nw + (hw-nw)*f/tl + 2*c;
function wsd_(nw,hw,tl) = nw + (hw-nw)*(sd_(tl)+f)/tl + 2*c;
module strap2d(nw, hw, tl) {
  sd = sd_(tl); w0 = w0_(nw,hw,tl); wsd = wsd_(nw,hw,tl);
  polygon([[0,-w0/2],[sd,-wsd/2],[sd,wsd/2],[0,w0/2]]);
}
module socket_cut(nw, hw, tl) {
  w0 = w0_(nw,hw,tl);
  translate([0,0,-1]) linear_extrude(H+2) {
    strap2d(nw, hw, tl);
    translate([-1,-w0/2]) square([1.01, w0]);
  }
  hull() {   // bottom chamfer so first-layer squish can't bind the joint
    translate([0,0,-0.01]) linear_extrude(0.01) offset(delta=ef) strap2d(nw, hw, tl);
    translate([0,0,ef]) linear_extrude(0.01) strap2d(nw, hw, tl);
  }
}

// ---------- keyhole ----------
module slot_stadium() { hull() { translate([0,-slot_len/2]) circle(d=sw,$fn=48); translate([0,slot_len/2]) circle(d=sw,$fn=48); } }
module chamber_shape() { hull() { translate([0,-slot_len/2]) circle(d=cw,$fn=64); translate([0,slot_len/2]) circle(d=cw,$fn=64); } }
module keyhole_cut() {
  bottom = H - lip - chamber;
  translate([0,-slot_len/2,bottom]) cylinder(d=cw, h=chamber+lip+0.01, $fn=64);
  translate([0,0,bottom]) linear_extrude(chamber-taper_h) chamber_shape();
  hull() {
    translate([0,0,H-lip-taper_h]) linear_extrude(0.01) chamber_shape();
    translate([0,0,H-lip]) linear_extrude(0.01) slot_stadium();
  }
  translate([0,0,H-lip-0.01]) linear_extrude(lip+0.02) slot_stadium();
}

// ---------- nodes ----------
module junction() {
  difference() {
    union() {
      plate_body(-a, a, -a, a, r);
      for (sx=[-1,1], sy=[-1,1]) post(sx*hs, sy*hs, H);
      translate([0,0,plate_t-0.01]) linear_extrude(H-plate_t+0.01) rr(17, 26, 5);
      tenon_w( a, 0,   0, H);  tenon_w(-a, 0, 180, H);
      tenon_w( 0, a,  90, H);  tenon_w( 0,-a, -90, H);
    }
    for (sx=[-1,1], sy=[-1,1]) bore(sx*hs, sy*hs, H);
    keyhole_cut();
    up_arrow(0, 10, H);
  }
}
module edge_node(ph=H) {      // outline at y=0, panels at y>0
  difference() {
    union() {
      plate_body(-a, a, 0, a, r);
      for (sx=[-1,1]) post(sx*hs, edge, ph);
      tenon_n( a, edge, 0, ph);  tenon_n(-a, edge, 180, ph);
      tenon_w( 0, a, 90, ph);
    }
    for (sx=[-1,1]) bore(sx*hs, edge, ph);
  }
}
module corner_node(ph=H) {    // outline corner at origin, panel at x>0, y>0
  difference() {
    union() {
      plate_body(0, a, 0, a, r);
      post(edge, edge, ph);
      tenon_n(a, edge, 0, ph);  tenon_n(edge, a, 90, ph);
    }
    bore(edge, edge, ph);
  }
}

// ---------- wall-ear brackets (on 16 mm "ear" nodes, back stays flush) ----------
module csk_hole(x, y) {
  translate([x,y,-0.01]) cylinder(d1=csk_d, d2=wall_d, h=(csk_d-wall_d)/2+0.01, $fn=48);
  translate([x,y,-0.01]) cylinder(d=wall_d, h=bracket_t+0.02, $fn=48);
}
module head_pocket(x, y) {   // countersunk, head flush with the bracket back
  translate([x,y,-0.01]) cylinder(d=screw_d, h=bracket_t+0.02, $fn=48);
  translate([x,y,bracket_t-cs_h]) cylinder(d1=screw_d, d2=cs_d, h=cs_h+0.01, $fn=48);
}
module bracket_body(x0, x1, y0, y1) {
  hull() {
    linear_extrude(0.01) rbox(x0+ef, x1-ef, y0+ef, y1-ef, r-ef);
    translate([0,0,ef]) linear_extrude(bracket_t-ef) rbox(x0, x1, y0, y1, r);
  }
}
module bracket_edge() {
  difference() {
    bracket_body(-a, a, -ear_out, a);
    for (sx=[-1,1]) head_pocket(sx*hs, edge);
    for (sx=[-1,1]) csk_hole(sx*9, -ear_out/2);
  }
}
module bracket_corner() {
  difference() {
    bracket_body(-ear_out, a, -ear_out, a);
    head_pocket(edge, edge);
    csk_hole(-ear_out/2, edge);  csk_hole(edge, -ear_out/2);
  }
}

// ---------- rails ----------
module boss_col(x, y) {   // stadium column from the bed, merges with floor + wall
  hull() {
    for (dx=[-slot_play, slot_play]) {
      translate([x+dx, y, 0]) cylinder(d=boss_d-2*ef, h=0.01, $fn=48);
      translate([x+dx, y, ef]) cylinder(d=boss_d, h=H-ef, $fn=48);
    }
  }
}
module boss_slot(x, y) {
  zc = cb_on ? head_z : H;
  hull() for (dx=[-slot_play, slot_play]) translate([x+dx, y, -0.01]) cylinder(d=screw_d, h=H+0.02, $fn=48);
  hull() for (dx=[-slot_play, slot_play]) translate([x+dx, y, zc-cs_h]) cylinder(d1=screw_d, d2=cs_d, h=cs_h+0.01, $fn=48);
  if (cb_on) hull() for (dx=[-slot_play, slot_play]) translate([x+dx, y, head_z]) cylinder(d=cb_d, h=H, $fn=48);
}
module window2d() {   // cable window in the rail walls (x along rail, y = height)
  if (deep && !old_windows) polygon([[0,5],[win_len,5],[win_len,win_side],[win_len/2+3,win_side+win_len/2-3],[win_len/2-3,win_side+win_len/2-3],[0,win_side]]);
  else      polygon([[0,5],[win_len,5],[win_len-12,17],[12,17]]);
}
module rail(W, nw, hw, tl, fwin, bosses, arrow=false, piplat=false, psuplat=false) {
  L = rail_L;  sd = sd_(tl);  eb = sd + 3;  mid = L/2;
  span = (mid - mid_zone) - eb;
  g = (span - 2*win_len)/3;
  xs = [eb+g, eb+2*g+win_len, L-eb-2*g-2*win_len, L-eb-g-win_len];
  difference() {
    union() {
      hull() {
        translate([ef, -W/2+ef, 0]) cube([L-2*ef, W-2*ef, 0.01]);
        translate([0, -W/2, ef]) cube([L, W, plate_t-ef]);
      }
      for (s=[-1,1]) translate([0, (s>0) ? W/2-wall_t : -W/2, 1]) cube([L, wall_t, H-1]);
      translate([0, -W/2, 1]) cube([eb, W, H-1]);
      translate([L-eb, -W/2, 1]) cube([eb, W, H-1]);
      for (yb = bosses) boss_col(mid, yb);
      if (piplat) pi_platform(W);
      if (psuplat) psu_platform();
    }
    socket_cut(nw, hw, tl);
    translate([L,0,0]) mirror([1,0,0]) socket_cut(nw, hw, tl);
    for (x0 = xs) {
      translate([x0,0,0]) rotate([90,0,0]) linear_extrude(W+30, center=true) window2d();
      if (fwin > 0) translate([x0+4, -fwin/2, -1]) cube([win_len-8, fwin, plate_t+2]);
    }
    for (yb = bosses) boss_slot(mid, yb);
    if (arrow) up_arrow(mid, -4, plate_t);
    if (piplat) pi_platform_holes(W);
    if (psuplat) psu_platform_holes();
  }
}
module rail_v_inner() rail(Ww, neck_w, head_w, tl_w, 12, [-hs, hs]);
module rail_h_inner() rail(Ww, neck_w, head_w, tl_w, 12, [hs], true);   // screw side = UP
module rail_outer()   rail(Wn, neck_n, head_n, tl_n, 0,  [0]);
module rail_h_pi()    rail(Ww, neck_w, head_w, tl_w, 12, [hs], true, true);  // variant B, under the top-middle panel
module rail_v_psu()   rail(Ww, neck_w, head_w, tl_w, 12, [-hs, hs], false, false, true);  // bottom-middle cell, left seam

// ---- power-supply tray (A-200AF-5 / CZCL 5 V 40 A, 190 x 84 x 30 mm) on rail_v_psu ----
// rail-local: x along the rail (= up the wall), -y = into the bottom-middle cell
psu_L = 190;  psu_Wd = 84;  psu_H = 30;  psu_cl = 1.0;   // body size + clearance
psu_gap = 5;                         // air gap under the supply
psu_x0  = 5;                         // lower end of the supply, from the rail end
psu_ynear = -(hs + 30);              // supply edge nearest the rail (keeps clear of the HUB75 plug)
function psu_yfar() = psu_ynear - psu_Wd - psu_cl;
module psu_platform() {
  x0 = 2; x1 = rail_L - 2; y0 = psu_yfar() - 8; y1 = -Ww/2 + 1;
  px1 = psu_x0 + psu_L + psu_cl;  yn = psu_ynear;  yf = psu_yfar();
  difference() {   // lattice plate on the panel back
    hull() {
      translate([x0+ef, y0+ef, 0]) cube([x1-x0-2*ef, y1-y0-ef, 0.01]);
      translate([x0, y0, ef]) cube([x1-x0, y1-y0, 3-ef]);
    }
    for (k=[0:3]) translate([psu_x0+10+k*(psu_L-20)/4, yf+8, -1]) cube([(psu_L-20)/4-8, psu_Wd-15, 5]);
  }
  // two support ribs under the long edges (air gap below the supply)
  for (yy=[yn-7, yf+1]) translate([psu_x0, yy, 0]) cube([psu_L+psu_cl, 6, 3+psu_gap]);
  // side stops near both ends, and a bottom end stop (the wall hangs with +x up)
  for (xx=[psu_x0, px1-16], yy=[yn, yf-2.4]) translate([xx, yy, 0]) cube([16, 2.4, 3+psu_gap+14]);
  for (yy=[yn-14, yf+2]) translate([psu_x0-2.4, yy, 0]) cube([2.4, 12, 3+psu_gap+14]);
}
module psu_platform_holes() {   // zip-tie slots either side of the supply (ties >= 300 x 4.8 mm)
  yn = psu_ynear;  yf = psu_yfar();
  for (xx=[psu_x0+45, psu_x0+psu_L-45], yy=[yn+1.2, yf-6.6]) translate([xx-3, yy, -1]) cube([6, 4, 6]);
}
module mock_psu() { cube([psu_L, psu_Wd, psu_H]); }

// ---- Pi tray (top-middle cell): hooks into the window pairs of the two vertical rails ----
pit_y0 = 805;                      // global y of the tray bottom edge (top row starts at 3P)
pit_Hy = 75;
module pi_tray() {
  c0 = (rows-1)*P;                 // panel bottom edge of the top row
  pix0 = -100;  piy0 = 812 - pit_y0;    // Pi corner (non-USB edge) in tray coordinates
  difference() {
    union() {
      hull() {
        translate([-tray_half+ef, ef, 0]) cube([2*tray_half-2*ef, pit_Hy-2*ef, 0.01]);
        translate([-tray_half, 0, ef]) cube([2*tray_half, pit_Hy, 3-ef]);
      }
      for (sx=[-1,1]) translate([sx>0 ? tray_half-4 : -tray_half, 0, 0]) cube([4, pit_Hy, 10]);
      for (h = pi_holes) translate([pix0+h[0], piy0+h[1], 0]) cylinder(d=(pi_fix=="nut") ? 8 : 7, h=3+pi_so, $fn=40);
      for (sx=[-1,1]) { hook_tab(sx, tray_half, 822.65-pit_y0, 24); hook_tab(sx, tray_half, 861.45-pit_y0, 24); }
    }
    for (h = pi_holes) translate([pix0+h[0], piy0+h[1], 0]) pi_fix_hole(3+pi_so);
    translate([pix0+10, piy0+10, -1]) cube([45, 36, 5]);            // airflow under the Pi
    translate([pix0+69, piy0-2, -1]) cube([12, 60, 5]);
    translate([20, 12, -1]) cube([70, 50, 5]);                      // lighten right half
    translate([6, c0+73-12-pit_y0, -1]) cube([26, 26, 30]);         // clear the panel's power connector
    for (sx=[-1,1]) translate([sx*(tray_half-12)-2, 40, -1]) cube([4, 6, 6]);   // zip tie to each rail
  }
}

// ---- horizontal PSU tray (bottom-middle cell): hooks into the window pairs of the two
//      vertical rails, both terminal ends left free. Local x = 0 at the cell centre. ----
tray_y0  = 82;                         // tray bottom edge above the frame bottom (between the panel's power connectors)
tray_py0 = 8;                          // supply edge inside the tray
tray_gap_end = 7;                      // gap tray end <-> rail face (lets you tilt it in)
tray_half = (P - Ww)/2 - tray_gap_end; // 110.15
tray_Hy   = 101;
win_y_lo  = (P - gap/2 + a + f) - P + 0;   // unused helper
module hook_tab(sx, xface, yc, wb) {   // hook through a rail window; tapered 45 deg in y so it also fits the old trapezoid windows
  tl = tray_gap_end + wall_t + 3;
  translate([sx*xface, yc, 0]) mirror([sx<0 ? 1 : 0, 0, 0]) intersection() {
    rotate([90,0,0]) linear_extrude(wb+2, center=true)   // 45 deg underside all the way: prints with no support, rests on the window sill
      polygon([[-0.01,0],[tray_gap_end-5.5,0],[tray_gap_end+3.5,9.0],[tray_gap_end+3.5,9.5],[-0.01,9.5]]);
    rotate([90,0,90]) translate([0,0,-1]) linear_extrude(tl+2) polygon([[-wb/2,-1],[wb/2,-1],[wb/2,5.5],[wb/2-4,9.6],[-wb/2+4,9.6],[-wb/2,5.5]]);
  }
}
module tray_tab(sx, yc, tw=26) {   // hook through the rail window: 45 deg underside, rests on the window sill
  tl = tray_gap_end + wall_t + 3;
  translate([sx*tray_half, yc, 0]) mirror([sx<0 ? 1 : 0, 0, 0])
    rotate([90,0,0]) linear_extrude(tw, center=true)
      polygon([[-0.01,0],[0,1.5],[4,5.5],[tl,5.5],[tl,9.5],[-0.01,9.5]]);
}
module psu_tray() {
  yn = tray_py0;  yf = tray_py0 + psu_Wd + psu_cl;
  difference() {
    union() {
      hull() {   // lattice deck on the panel back
        translate([-tray_half+ef, ef, 0]) cube([2*tray_half-2*ef, tray_Hy-2*ef, 0.01]);
        translate([-tray_half, 0, ef]) cube([2*tray_half, tray_Hy, 3-ef]);
      }
      for (sx=[-1,1]) translate([sx>0 ? tray_half-4 : -tray_half, 0, 0]) cube([4, tray_Hy, 10]);   // end walls
      for (yy=[yn+1, yf-7]) translate([-psu_L/2, yy, 0]) cube([psu_L+psu_cl, 6, 3+psu_gap]);        // ribs
      for (sx=[-1,1]) translate([sx*(psu_L/2+psu_cl/2) - (sx>0 ? 0 : 2), yn+1, 0]) cube([2, 6, 3+psu_gap+3]);   // low end bumps
      for (sx=[-1,1]) translate([sx*(psu_L/2+psu_cl/2) - (sx>0 ? 0 : 2), yf-7, 0]) cube([2, 6, 3+psu_gap+3]);
      for (xx=[-psu_L/2+4, psu_L/2-20, -8], yy=[yn-2.4, yf]) translate([xx, yy, 0]) cube([16, 2.4, 3+psu_gap+14]);  // side stops
      for (sx=[-1,1]) { hook_tab(sx, tray_half, 92.75-tray_y0, 24); hook_tab(sx, tray_half, 162-tray_y0, 20); }
    }
    for (k=[0:3]) translate([-psu_L/2+12+k*(psu_L-24)/4, yn+9, -1]) cube([(psu_L-24)/4-8, psu_Wd-17, 5]);   // air windows
    for (xx=[-50, 50], yy=[yn-7, yf+2.6]) translate([xx-3, yy, -1]) cube([6, 4, 6]);    // zip ties round the supply
    for (sx=[-1,1]) translate([sx*(tray_half-12)-2, 40, -1]) cube([4, 6, 6]);   // zip tie to each rail
    // keep clear of the panel's HUB75 plugs (upper corners of the cell)
    for (sx=[-1,1]) translate([sx>0 ? 94 : -tray_half-20, 88, -1]) cube([tray_half+20-94, 30, 30]);
  }
}


// =====================================================================
// Raspberry Pi 5 + Camera Module 3 enclosure parts (v3)
// =====================================================================
pi_L = 85;  pi_W = 56;  pi_pcb = 1.6;
pi_holes = [[3.5,3.5],[61.5,3.5],[3.5,52.5],[61.5,52.5]];   // from the non-USB short edge
pi_so    = 5;       // standoff height
pi_fix   = "selftap";   // "selftap" (M2.5x6 into 2.2 pilot) | "insert" (M2.5 heat-set, 3.5 OD) | "nut" (M2.5 bolt + nut from below)
pi_stack = 32;      // Pi PCB top -> tallest part (shield, plugs, cables)  <- measure yours
cam_tilt = 15;      // camera looks this many degrees down
pad_x    = deep ? 16 : 30;     // enclosure screws into the top rail, +- from the centre
pad_z    = deep ? 10 : H/2;    // height of those screws above the rim face
cam_hole = [[-10.5,7.5],[10.5,7.5],[-10.5,-5],[10.5,-5]];   // CM2/CM3 M2 holes, lens at (0,0)
lens_tip = 10.5;    // board face -> lens tip

// ---- small helpers ----
module teardrop2d(rr) { hull() { circle(r=rr, $fn=32); polygon([[-rr*0.7071, rr*0.7071],[rr*0.7071, rr*0.7071],[0, rr*1.4142]]); } }
module diamond(sz) { rotate(45) square(sz, center=true); }

// ---- top-centre mounting rail (replaces the middle top perimeter rail) ----
module rail_top_mount() {
  W = Wn; tl = tl_n; L = rail_L; sd = sd_(tl); eb = sd + 3; mid = L/2;
  span = (mid - mid_zone) - eb;  g = (span - 2*win_len)/3;
  difference() {
    union() {
      hull() {
        translate([ef, -W/2+ef, 0]) cube([L-2*ef, W-2*ef, 0.01]);
        translate([0, -W/2, ef]) cube([L, W, plate_t-ef]);
      }
      for (s=[-1,1]) translate([0, (s>0) ? W/2-wall_t : -W/2, 1]) cube([L, wall_t, H-1]);
      translate([0, -W/2, 1]) cube([eb, W, H-1]);
      translate([L-eb, -W/2, 1]) cube([eb, W, H-1]);
      for (s=[-1,1]) translate([mid+s*pad_x-5, -W/2, 1]) cube([10, W, H-1]);     // screw pads
    }
    socket_cut(neck_n, head_n, tl);
    translate([L,0,0]) mirror([1,0,0]) socket_cut(neck_n, head_n, tl);
    for (x0 = [eb+g, L-eb-g-win_len])
      translate([x0,0,0]) rotate([90,0,0]) linear_extrude(W+30, center=true) window2d();
    // centre cable window straight under the enclosure
    translate([mid,0,0]) rotate([90,0,0]) linear_extrude(W+30, center=true)
      if (deep) polygon([[-10,4],[10,4],[10,14],[3,21],[-3,21],[-10,14]]);   // camera cable
      else      polygon([[-20,4],[20,4],[7,17],[-7,17]]);
    // M3 pilots (self-tapping) for the enclosure, drilled down from the top face
    for (s=[-1,1]) translate([mid+s*pad_x, W/2+0.01, pad_z]) rotate([90,0,0]) linear_extrude(13) teardrop2d(1.3);
  }
}

// ---- Pi platform on rail_h_pi (variant B) : lattice plate at the rim face ----
function pi_x0(W) = rail_L/2 - 100;          // non-USB edge of the Pi (USB/Ethernet faces the centre)
function pi_y0(W) = W/2 + 6;
module pi_platform(W) {
  x0 = 6; x1 = rail_L/2 - 10; y0 = W/2 - 1; y1 = W/2 + 72;
  difference() {
    hull() {
      translate([x0+ef, y0, 0]) cube([x1-x0-2*ef, y1-y0-ef, 0.01]);
      translate([x0, y0, ef]) cube([x1-x0, y1-y0, 3-ef]);
    }
    translate([pi_x0(W)+10, pi_y0(W)+10, -1]) cube([45, 36, 5]);
    translate([pi_x0(W)+69, pi_y0(W)-2, -1]) cube([16, 60, 5]);
  }
  for (h = pi_holes) translate([pi_x0(W)+h[0], pi_y0(W)+h[1], 0]) cylinder(d=(pi_fix=="nut") ? 8 : 7, h=3+pi_so, $fn=40);
}
module pi_fix_hole(top) {   // one Pi mounting hole, standoff top at z = top
  if (pi_fix == "insert") translate([0,0,top-4.5]) cylinder(d=3.6, h=4.6, $fn=32);
  else if (pi_fix == "nut") {
    translate([0,0,-0.01]) cylinder(d=2.8, h=top+0.02, $fn=24);
    translate([0,0,-0.01]) cylinder(d=5.9, h=2.4, $fn=6);       // M2.5 nut trap from below
  }
  else translate([0,0,top-6]) cylinder(d=2.2, h=6.01, $fn=24);
}
module pi_platform_holes(W) {
  for (h = pi_holes) translate([pi_x0(W)+h[0], pi_y0(W)+h[1], 0]) pi_fix_hole(3+pi_so);
}

// ---- enclosure (box local: x centred, y up from the frame top edge, z = 0 at the wall) ----
bw = 3;   // wall
module box_body(W, Hb, Db, pi=true, back_z=H, rail_screws=true) {
  cx = W/2 - 7;
  difference() {
    union() {
      difference() {
        linear_extrude(Db) rbox(-W/2, W/2, 0, Hb, 6);
        translate([0,0,bw]) linear_extrude(Db) rbox(-W/2+bw, W/2-bw, bw, Hb-bw, 3);
      }
      for (sx=[-1,1], yy=[7, Hb-7]) translate([sx*cx, yy, 0]) cylinder(d=8.6, h=Db, $fn=40);
      if (pi) for (h = pi_holes) translate([-pi_L/2+h[0], 10+h[1], 0]) cylinder(d=(pi_fix=="nut") ? 8 : 7, h=bw+pi_so, $fn=40);
    }
    for (sx=[-1,1], yy=[7, Hb-7]) translate([sx*cx, yy, Db-12]) cylinder(d=2.6, h=13, $fn=24);   // lid screws
    if (pi) for (h = pi_holes) translate([-pi_L/2+h[0], 10+h[1], 0]) pi_fix_hole(bw+pi_so);
    // M3 down into the top rail pads
    if (rail_screws) for (sx=[-1,1]) translate([sx*pad_x, bw+1, back_z-pad_z]) rotate([90,0,0]) linear_extrude(bw+2) teardrop2d(1.75);
    // cable slot down into the rail's centre window
    if (rail_screws) translate([0, bw+1, 0]) rotate([90,0,0]) linear_extrude(bw+2)
      if (deep) polygon([[-9,3],[9,3],[9,9],[3,15],[-3,15],[-9,9]]);
      else      polygon([[-18,H-16],[18,H-16],[6,H-4],[-6,H-4]]);
    // optional wall screws, countersunk from inside
    if (back_z == H) for (sx=[-1,1]) translate([sx*(W/2-22), Hb-20, 0]) {
      translate([0,0,-0.01]) cylinder(d=4.5, h=bw+0.02, $fn=32);
      translate([0,0,bw-2.25]) cylinder(d1=4.5, d2=9, h=2.26, $fn=32);
    }
    // vents (diamonds = no bridging)
    if (pi) {
      for (sx=[-1,1], yy=[18:9:Hb-30], zz=[14:9:Db-8]) translate([sx*W/2, yy, zz]) rotate([0,90,0]) linear_extrude(10, center=true) diamond(5);
      for (xx=[-W/2+18:9:W/2-18], zz=[14:9:Db-8]) translate([xx, Hb, zz]) rotate([90,0,0]) linear_extrude(10, center=true) diamond(5);
    }
  }
}
cam_z = 2.6;        // lens tip depth behind the lid's outer face
cam_rot = 90;       // 90 = portrait, 0 = landscape
module cam_tf(cam_by) { translate([0, cam_by, cam_z]) rotate([-cam_tilt,0,0]) rotate([0,0,cam_rot]) children(); }
module box_lid(W, Hb, cam_by) {
  cx = W/2 - 7;
  difference() {
    union() {
      linear_extrude(bw) rbox(-W/2, W/2, 0, Hb, 6);
      difference() {   // locating ring
        translate([0,0,bw-0.01]) linear_extrude(2) rbox(-W/2+bw+0.25, W/2-bw-0.25, bw+0.25, Hb-bw-0.25, 2.75);
        translate([0,0,bw-0.1]) linear_extrude(3) rbox(-W/2+bw+2.25, W/2-bw-2.25, bw+2.25, Hb-bw-2.25, 1);
        for (sx=[-1,1], yy=[7, Hb-7]) translate([sx*cx, yy, 0]) cylinder(d=10, h=10, $fn=40);
      }
      intersection() {   // camera pillars on the tilted plane
        cam_tf(cam_by) for (h = cam_hole) translate([h[0], h[1], -12]) cylinder(d=5, h=12+lens_tip, $fn=32);
        translate([-W/2, 0, 0]) cube([W, Hb, 40]);
      }
    }
    for (sx=[-1,1], yy=[7, Hb-7]) translate([sx*cx, yy, 0]) {
      translate([0,0,-0.01]) cylinder(d=3.4, h=bw+3, $fn=32);
      translate([0,0,-0.01]) cylinder(d1=6.6, d2=3.4, h=1.61, $fn=32);
    }
    cam_tf(cam_by) {
      for (h = cam_hole) translate([h[0], h[1], lens_tip-6]) cylinder(d=1.7, h=6.1, $fn=20);
      translate([0,0,-8]) linear_extrude(lens_tip+8-0.1) square([13, 17], center=true);   // straight, tilted 15 deg: no overhang, >60 deg half-angle view
    }
  }
}
// variant A: Pi 5 + shield + camera in one box
A_W = 112;  A_H = 108;  A_D = max(bw + pi_so + pi_pcb + pi_stack + 6 + bw, H + 30);
A_cam_by = A_H - 24;
module box_A_body() box_body(A_W, A_H, A_D - bw, true);
module box_A_lid()  box_lid(A_W, A_H, A_cam_by);
// variant B: camera only (Pi lives in the frame)
B_W = 60;  B_H = 44;  B_back = 20;  B_front = -16;   // pod spans frame z 20 .. -16
B_D = B_back - B_front;
B_cam_by = 22;
module box_B_body() box_body(B_W, B_H, B_D - bw, false, B_back);
module box_B_lid()  box_lid(B_W, B_H, B_cam_by);

// variant C: camera pod that clips onto the standard middle top rail (no special rail)
C_W = 96;  C_H = 44;  C_back = 20;  C_front = -16;  C_D = C_back - C_front;  C_cam_by = 22;
c_peg_x = -36.3;    // peg into the rail window left of centre (frame x 348)
c_fpc_x = 32.5;     // camera cable slot over the window right of centre (frame x 409..425)
module box_C_body() {
  difference() {
    union() {
      box_body(C_W, C_H, C_D - bw, false, C_back, false);
      // peg (frame z 6..16 at the root, 45 deg back face) down into the rail window
      translate([c_peg_x, 0, 0]) rotate([0,90,0]) rotate([0,0,90]) linear_extrude(6, center=true)
        polygon([[0.01, C_back-16],[0.01, C_back-6],[-6, C_back-6],[-6, C_back-10]]);
    }
    // camera cable slot (frame z 5.5..8) with a 45 deg peaked top
    translate([0, bw+1, 0]) rotate([90,0,0]) linear_extrude(bw+2)
      polygon([[c_fpc_x-8, C_back-8],[c_fpc_x+8, C_back-8],[c_fpc_x+8, C_back-7],[c_fpc_x, C_back+1],[c_fpc_x-8, C_back-7]]);
    // zip tie slot next to the cable slot
    translate([c_fpc_x-14, -1, C_back-14]) cube([4, bw+2, 5]);
  }
}
module box_C_lid() box_lid(C_W, C_H, C_cam_by);

// mock electronics for previews / clearance checks
module mock_pi() { cube([pi_L, pi_W, pi_pcb]); translate([0,0,pi_pcb]) cube([pi_L, pi_W, pi_stack]); }
module mock_cam() {
  translate([0,0,0]) cylinder(d=8.5, h=lens_tip, $fn=32);
  translate([-12.5,-14.5,lens_tip]) cube([25, 24, 1]);
  translate([-8,-14.5,lens_tip+1]) cube([16, 6, 2.5]);
}

// ---------- dovetail gauge stub: short wide-rail end, dots = clearance x 20 ----------
module gauge_stub() {
  difference() {
    intersection() { rail_v_inner(); translate([-1,-20,-1]) cube([22, 40, 25]); }
    for (k=[0:round(c*20)-1]) translate([16, -6+k*4, H-0.6]) cylinder(d=2.2, h=1, $fn=16);
  }
}
// ---------- fit-test coupon (print first) ----------
module fit_test() {
  junction();
  translate([40, -22, 0]) intersection() { rail_v_inner(); translate([-1,-20,-1]) cube([45, 40, 25]); }
  translate([40-rail_L/2+18, 30, 0]) intersection() {
    rail_v_inner(); translate([rail_L/2-18, -20, -1]) cube([36, 40, 25]);
  }
}

// ---------- print plates (all inside 250 x 220) ----------
module plate_nodes_A() { for (i=[0:2], j=[0:1]) translate([i*58, j*58, 0]) junction(); }
module plate_nodes_B() {
  for (k=[0:9]) translate([(k%4)*54, floor(k/4)*32, 0]) edge_node();
  for (k=[0:3]) translate([k*29, 100, 0]) corner_node();
}
module plate_ears() {
  for (k=[0:3]) translate([k*48, 0, 0]) bracket_corner();
  for (k=[0:1]) translate([k*40, 50, 0]) bracket_edge();
  for (k=[0:1]) translate([100+k*54, 55, 0]) edge_node(H-bracket_t);
  for (k=[0:3]) translate([k*30, 110, 0]) corner_node(H-bracket_t);
}
module plate_rails_A() { for (k=[0:6]) translate([0, k*29, 0]) rail_v_inner(); }
module plate_rails_B() {
  rail_v_inner();
  for (k=[0:5]) translate([0, 29 + k*27, 0]) rail_h_inner();
}
module plate_rails_C() {
  for (k=[0:2]) translate([0, k*27, 0]) rail_h_inner();
  for (k=[0:5]) translate([0, 78 + k*19, 0]) rail_outer();
}
module plate_rails_D() { for (k=[0:7]) translate([0, k*19, 0]) rail_outer(); }
module plate_rails_C2() {     // variant B: one horizontal rail is the Pi rail instead
  for (k=[0:1]) translate([0, k*27, 0]) rail_h_inner();
  for (k=[0:5]) translate([0, 51 + k*19, 0]) rail_outer();
}
module plate_rails_D_top() {  // 7 perimeter rails + the top-centre mounting rail
  for (k=[0:6]) translate([0, k*19, 0]) rail_outer();
  translate([0, 7*19, 0]) rail_top_mount();
}
module plate_box_A() {
  box_A_body();
  translate([A_W + 6, 0, 0]) box_A_lid();
}
module plate_pi_box_B() {
  rail_h_pi();
  translate([B_W/2, 90, 0]) box_B_body();
  translate([B_W*1.5 + 8, 90, 0]) box_B_lid();
}
module plate_pi_rail_B() rail_h_pi();
module plate_rails_B_noV() { for (k=[0:5]) translate([0, k*27, 0]) rail_h_inner(); }
module plate_psu_rail() rail_v_psu();
module plate_psu_tray() psu_tray();
module plate_pi_tray() pi_tray();
module plate_cam_pod_C() { box_C_body(); translate([C_W + 6, 0, 0]) box_C_lid(); }
module plate_cam_pod_B() { box_B_body(); translate([B_W + 6, 0, 0]) box_B_lid(); }

// ---------- assembly ----------
function xl(i) = (i==0) ? 0 : (i==cols) ? cols*P-gap : i*P - gap/2;
function yl(j) = (j==0) ? 0 : (j==rows) ? rows*P-gap : j*P - gap/2;
module place_nodes() {
  for (i=[0:cols], j=[0:rows]) {
    x = xl(i); y = yl(j);
    cp = (i==0||i==cols) && (j==0||j==rows);
    sp = (i==0||i==cols||j==0||j==rows) && !cp;
    if (!cp && !sp) translate([x,y,0]) junction();
    else if (sp) translate([x,y,0]) rotate([0,0,(j==0)?0:(j==rows)?180:(i==0)?-90:90]) edge_node();
    else translate([x,y,0]) rotate([0,0,(i==0&&j==0)?0:(i==cols&&j==0)?90:(i==cols&&j==rows)?180:-90]) corner_node();
  }
}
module place_rails() {
  for (j=[0:rows], i=[0:cols-1]) {
    perim = (j==0 || j==rows);
    yc = (j==0) ? edge : (j==rows) ? yl(j)-edge : yl(j);
    translate([xl(i)+a+f, yc, 0]) {
      if (j==rows && i==1 && variant!="C") rail_top_mount();
      else if (perim) rail_outer();
      else if (variant=="B" && j==rows-1 && i==1) rail_h_pi();
      else rail_h_inner();
    }
  }
  for (i=[0:cols], j=[0:rows-1]) {
    perim = (i==0 || i==cols);
    xc = (i==0) ? edge : (i==cols) ? xl(i)-edge : xl(i);
    translate([xc, yl(j)+a+f, 0]) rotate([0,0,90]) {
      if (perim) rail_outer();
      else rail_v_inner();
    }
  }
}
xc_box = (xl(1) + xl(2))/2;
module place_box() {
  if (variant!="C") {
  D  = (variant=="A") ? A_D : B_D;
  bk = (variant=="A") ? H : B_back;
  ex = explode*120;
  translate([xc_box, yl(rows)+ex, bk]) mirror([0,0,1]) {
    color("Orange") if (variant=="A") box_A_body(); else box_B_body();
    if (variant=="A" && show_mocks) color("ForestGreen") translate([-pi_L/2, 10, bw+pi_so]) mock_pi();
  }
  translate([xc_box, yl(rows)+ex, bk-D-explode*60]) {
    color("Orange") if (variant=="A") box_A_lid(); else box_B_lid();
    if (show_mocks) color("Crimson") cam_tf(variant=="A" ? A_cam_by : B_cam_by) mock_cam();
  }
  if (variant=="C") translate([P+panel/2, pit_y0, explode*70]) {
    color("SteelBlue") pi_tray();
    if (show_mocks) color("ForestGreen") translate([-100, 812-pit_y0, 3+pi_so]) mock_pi();
  }
  if (variant=="C") translate([xc_box, yl(rows)+explode*120, C_back]) mirror([0,0,1]) color("Orange") box_C_body();
  if (variant=="C") translate([xc_box, yl(rows)+explode*120, C_back-C_D-explode*60]) {
    color("Orange") box_C_lid();
    if (show_mocks) color("Crimson") cam_tf(C_cam_by) mock_cam();
  }
  if (variant=="B" || variant=="C") translate([P+panel/2, tray_y0, explode*70]) {
    color("SteelBlue") psu_tray();
    if (show_mocks) color("SlateGray") translate([-psu_L/2, tray_py0, 3+psu_gap]) mock_psu();
  }
  if (variant=="B" && show_mocks) color("ForestGreen")
    translate([xl(1)+a+f + pi_x0(Ww), yl(rows-1) + pi_y0(Ww), 3+pi_so + explode*70]) mock_pi();
  }
}
module assembly() {
  color("DimGray") place_nodes();
  place_box();
  color("SteelBlue") translate([0,0,explode*70]) place_rails();
  color([0.16,0.16,0.18], panel_alpha) translate([0,0,-explode*90]) for (i=[0:cols-1], j=[0:rows-1])
    translate([i*P, j*P, -14]) cube([panel, panel, 14]);
}

// ---------- dispatch ----------
if      (part=="junction")       junction();
else if (part=="edge")           edge_node();
else if (part=="corner")         corner_node();
else if (part=="edge_ear")       edge_node(H-bracket_t);
else if (part=="corner_ear")     corner_node(H-bracket_t);
else if (part=="bracket_edge")   bracket_edge();
else if (part=="bracket_corner") bracket_corner();
else if (part=="rail_v_inner")   rail_v_inner();
else if (part=="rail_h_inner")   rail_h_inner();
else if (part=="rail_outer")     rail_outer();
else if (part=="fit_test")       fit_test();
else if (part=="gauge_stub")     gauge_stub();
else if (part=="rail_top_mount") rail_top_mount();
else if (part=="rail_h_pi")      rail_h_pi();
else if (part=="box_A_body")     box_A_body();
else if (part=="box_A_lid")      box_A_lid();
else if (part=="box_B_body")     box_B_body();
else if (part=="box_B_lid")      box_B_lid();
else if (part=="plate_rails_C2") plate_rails_C2();
else if (part=="plate_rails_D_top") plate_rails_D_top();
else if (part=="plate_box_A")    plate_box_A();
else if (part=="plate_pi_box_B") plate_pi_box_B();
else if (part=="plate_pi_rail_B") plate_pi_rail_B();
else if (part=="plate_rails_B_noV") plate_rails_B_noV();
else if (part=="plate_psu_rail") plate_psu_rail();
else if (part=="plate_psu_tray") plate_psu_tray();
else if (part=="plate_pi_tray")  plate_pi_tray();
else if (part=="plate_cam_pod_C") plate_cam_pod_C();
else if (part=="pi_tray")        pi_tray();
else if (part=="box_C_body")     box_C_body();
else if (part=="box_C_lid")      box_C_lid();
else if (part=="psu_tray") psu_tray();
else if (part=="rail_v_psu") rail_v_psu();
else if (part=="mock_psu") mock_psu();
else if (part=="plate_cam_pod_B") plate_cam_pod_B();
else if (part=="plate_nodes_A")  plate_nodes_A();
else if (part=="plate_nodes_B")  plate_nodes_B();
else if (part=="plate_ears")     plate_ears();
else if (part=="plate_rails_A")  plate_rails_A();
else if (part=="plate_rails_B")  plate_rails_B();
else if (part=="plate_rails_C")  plate_rails_C();
else if (part=="plate_rails_D")  plate_rails_D();
else if (part=="display") rotate([90,0,0]) assembly();   // y-up for renders
else assembly();
