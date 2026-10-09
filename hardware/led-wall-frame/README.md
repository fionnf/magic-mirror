# Modular LED Wall Frame – 3 × 4 P4 64×64 panels (256 mm)

A fully printable, support-free mounting frame for twelve P4 64×64 HUB75 LED panels
(256 × 256 mm, e.g. `P4-2121-64X64-32S`) in a 3 × 4 grid. Overall size 768.6 × 1024.9 mm,
46 mm deep, so a Raspberry Pi 4/5 with HUB75 shield and a 5 V 40 A supply hide inside.
A small pod on the top edge holds a Raspberry Pi Camera Module 3 (or a Logitech C270).

Every part prints flat, with no supports, and fits a 250 × 220 mm bed (Prusa CORE One, Bambu X1/P1/H2, Prusa MK4…).
The compact Pi holder, camera pod, touch box and test pieces also fit 180 mm beds.

![front](images/01_front.png)

## What's in the box

| Folder | Contents |
|---|---|
| `3mf/` | Ready-to-slice plates, one object per part (open in PrusaSlicer, Bambu Studio, OrcaSlicer) |
| `stl/` | The same plates as STL |
| `source/` | Fully parametric OpenSCAD source (`led_wall_frame.scad`, `c270_webcam_box.scad`, `touch_box.scad`) |
| `images/` | Renders |

## Print list

| File | Qty | Notes |
|---|---|---|
| `00_fit_test_PRINT_FIRST` | 1 | Junction node + rail ends: check dovetail fit, M3 screw and wall keyhole |
| `00b_dovetail_gauge_c005_c010_c015` | 1 | Optional: 3 sockets at 0.05 / 0.10 / 0.15 mm clearance (1–3 dots) |
| `01_nodes_junction_x6` | 1 | |
| `02_nodes_edge_x10_corner_x4` | 1 | |
| `03_rails_vertical_x7` | 1 | |
| `04_rails_vertical_x1_horizontal_x6` | 1 | |
| `05_rails_horizontal_x3_outer_x6` | 1 | |
| `06_rails_outer_x7_top_mount_x1` | 1 | Includes the top-centre rail the camera pod screws to |
| `07_pi_tray_*` **or** `07_pi_holder_compact_*` | 1 | Pick one: full-width tray (stronger) or compact holder (fits 180 mm beds). `selftap` / `insert` (M2.5 heat-set) / `nut` (M2.5 bolt + nut). Pi 4 and Pi 5 share the hole pattern. |
| `08_psu_tray_A-200AF-5` | 1 | For a 190 × 84 × 30 mm 5 V 40 A supply (CZCL A-200AF-5) |
| `09_camera_module3_pod` **or** `10_c270_webcam_box` | 1 | Camera Module 3 (portrait, 15° down) or Logitech C270 (snap-on lid) |
| `11_touch_box_TTP223` / `11_touch_box_25mm_pad` | optional | 40 × 40 × 10 mm "roaming" capacitive touch button, 0.6 mm skin |
| `12_OPTIONAL_wall_ears_set` | optional | Only if you prefer ear brackets over the built-in keyholes |

Roughly 2 kg of filament for the full build.

## Print settings

- PETG (panels run warm – avoid PLA)
- 0.4 mm nozzle, 0.20 mm layers
- 5 perimeters, 40 % gyroid, 5 top / 5 bottom layers
- No supports, no brim, keep elephant-foot compensation on
- Print as laid out (panel side down). Touch box: front face down, 100 % infill.

## Hardware

| Item | Qty |
|---|---|
| M3 × 20 flat-head countersunk (DIN 7991 / ISO 10642) – panel screws | 84 (+2 optional) |
| 2 mm hex key with a long shaft (≥ 35 mm reach) | 1 |
| M3 × 12 pan/cheese head – camera pod or C270 box to the top rail | 2 |
| M3 × 12 countersunk – camera pod lid | 4 |
| M2 × 5 self-tapping – Camera Module 3 | 4 |
| M2.5 × 6 (+ 4 heat-set inserts for `insert`, or M2.5 × 10 + nuts for `nut`) – Pi | 4 |
| Zip ties ≥ 300 × 4.8 mm – around the PSU | 2 |
| Wall screws, pan head ≤ 8.2 mm, standing ~5 mm proud, + anchors (keyholes on a 256.3 mm grid) | 6 |
| Touch box: M2 × 8 countersunk self-tapping | 4 |
| Wall ears only: M3 × 50 countersunk at the 8 ear-node screws, 5 mm wall screws | 8 / 12 |

Electronics: 12 × P4 64×64 HUB75 panels, Raspberry Pi 5 (or 4) + active cooler, HUB75 driver shield,
Camera Module 3 + 500 mm camera cable (Pi 5: 22→15 pin) **or** Logitech C270, CZCL A-200AF-5 5 V 40 A supply,
HUB75 ribbons, panel power leads, 1.5–2.5 mm² 5 V wiring, mains cable, fuse + switch.

## Assembly

1. Lay the panels face down on a soft mat, all "up" arrows on the back pointing the same way.
2. Place the nodes on the panel corner inserts (8 mm from each edge).
3. Drop the rails in from above – the dovetails slide down over the node tenons. Horizontal rails: engraved arrow up.
4. Screw everything down with M3 × 20 (heads sit flush deep inside the posts).
5. Press the PSU tray and Pi tray into the rail windows: shift ~5 mm sideways, push one end's plugs in, bring the other end in, slide back to centre.
6. Fit the camera pod (or C270 box) on the top-centre rail; route the cable down through the rail window.
7. Hang the frame on six wall screws.

The two outer top rails have a mid screw hole at the top-centre of the outer panels – only use it if your panels have an insert there.

## Customising

All key values are at the top of `source/led_wall_frame.scad`:
`H` (frame depth), `screw_L` (panel screw length), `c` (dovetail clearance), `plug_cl` / `crush` (holder fit),
`pi_stack` (Pi + shield height), `psu_L` / `psu_Wd` (power supply size).

```
openscad -D 'part="plate_rails_A"' -o rails.stl source/led_wall_frame.scad
```

## Notes

- A single 200 W supply is short for 12 panels at full white (~240 W): cap the brightness (e.g. `--led-brightness`) or add a second supply.
- Mains: cover the AC terminals, strain-relieve the cable, fuse and switch outside the frame.
- Default Pi + shield stack: ≤ 32 mm above the Pi board.
