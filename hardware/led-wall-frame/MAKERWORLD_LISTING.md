# MakerWorld listing – copy & paste

**Title:** Modular LED Wall Frame for 12 × P4 64×64 panels – Raspberry Pi inside, camera pod, support-free

**Category:** Gadgets / Electronics (or Household → Wall mounts)

**Tags:** LED matrix, HUB75, P4, 64x64, LED wall, magic mirror, Raspberry Pi 5, Raspberry Pi 4, Pi camera, Logitech C270, frame, wall mount, modular, dovetail, support-free, PETG, OpenSCAD, parametric

**Cover image:** `images/01_front.png` · then `02_rear`, `03_rear_exploded`, `04_pi_tray`, `05_psu_tray`, `06_camera_module3_pod`, `07_c270_box_option`, `08`–`10` plates, `11_touch_box`, `12_c270_box_snap_lid` (add a photo of your build as soon as you have one).

---

## Description

Turn twelve cheap P4 64×64 LED panels (256 × 256 mm, the common AliExpress `P4-2121-64X64-32S` type) into a clean 77 × 102 cm LED wall – with the Raspberry Pi, HUB75 shield and 5 V power supply hidden inside the frame, and a small camera pod on top for interactive / magic-mirror projects.

**Highlights**
- Fully modular: 20 nodes screw into the panels' brass inserts, 31 dovetailed rails lock them into one rigid lattice.
- 84 × M3 × 20 countersunk screws – every corner and mid-edge insert is used, heads sit flush.
- 46 mm deep: room for a Raspberry Pi 4/5 + HUB75 shield and a 5 V 40 A supply (CZCL A-200AF-5) inside.
- Snug press-fit trays for the Pi and the PSU – they plug into the rail windows, no tools.
- Camera pod for Raspberry Pi Camera Module 3 (portrait, 15° down) or a box for the Logitech C270 with a snap-on lid.
- Bonus: 40 × 40 × 10 mm touch button box (TTP223 / 25 mm pad) with a 0.6 mm front skin.
- Built-in wall keyholes (optional ear brackets).
- Cable windows big enough for HUB75 ribbon plugs.
- **No supports anywhere.** Every plate fits a 250 × 220 mm bed.
- Parametric OpenSCAD source included.

**What to print** – see the plate list in the files: `00` fit test first, then `01`–`06` frame, one `07` Pi holder, `08` PSU tray, `09` or `10` camera, optional `11` touch box and `12` wall ears. ≈ 2 kg PETG.

**Print settings:** PETG, 0.2 mm layers, 5 walls, 40 % gyroid, no supports, no brim.

**Hardware:** 84 × M3 × 20 DIN 7991 countersunk + long 2 mm hex key · 2 + 4 × M3 × 12 (camera pod) · 4 × M2.5 × 6 (Pi) · 4 × M2 × 5 (camera) · 2 zip ties ≥ 300 mm · 6 wall screws (head ≤ 8.2 mm).

**Assembly:** panels face down → nodes on the corner inserts → drop the rails in (dovetails) → screw down → press in the Pi and PSU trays → camera pod on the top rail → hang on 6 screws.

**Safety:** the supply runs on mains – cover the AC terminals, strain-relieve the cable and fit a fuse/switch outside the frame. One 200 W supply is short for 12 panels at full white, so limit brightness in software or add a second supply.

---

## Print profile notes (per plate, for MakerWorld "print profiles")

| Plate | Time est.* | Filament (≈) |
|---|---|---|
| 00 fit test | short | 55 g |
| 01 junction nodes | medium | 240 g |
| 02 edge + corner nodes | medium | 215 g |
| 03–06 rails (each) | long | 320–400 g |
| 07 Pi tray / compact holder | short | 50 / 30 g |
| 08 PSU tray | short | 70 g |
| 09 camera pod / 10 C270 box | short | 30 / 60 g |

\*Slice once in Bambu Studio and publish the plates as print profiles to get exact times.
