# Panel setup (12× 64×64 HUB75, 3 wide × 4 tall)

Bring-up tools for the display only — no camera, button, strip or API.
Everything reads `../config.py` (panel layout, chain order, tuning, power).

## 1. Install on the Pi (once)
Fresh Pi, from the project folder (after the first deploy):
```bash
./install.sh          # builds rpi-rgb-led-matrix, installs deps
sudo reboot
```
Only the display needs: `sudo apt install python3-pil python3-numpy` plus the
`rgbmatrix` bindings from `install.sh`.

## 2. Send code to the Pi (from your laptop)
```bash
./panel_setup/deploy.sh                                   # pi@192.168.1.207
PI_USER=fionn PI_HOST=192.168.1.50 ./panel_setup/deploy.sh
```
It rsyncs the project to `~/magic-mirror` (skips `.env`, tokens, photos, git).
Re-run after every edit. Needs SSH access (`ssh pi@192.168.1.207` works).

## 3. Run on the Pi
```bash
ssh pi@192.168.1.207
cd ~/magic-mirror
./panel_setup/run.sh walk         # START HERE: one panel at a time
```
Ctrl-C quits (display is cleared).

| Command | Purpose |
|---|---|
| `run.sh walk` | One panel lit at a time in chain order, 3 s each, with corner dots + index. `--panel 5` holds one, `--walk-sec 6` slows it |
| `run.sh numbers` | Each panel shows its chain index + up arrow. Verify order/orientation |
| `run.sh gradient` | Colour channels, dead pixels |
| `run.sh bar --show-refresh` | Moving bar: flicker / tearing / refresh rate |
| `run.sh text` / `anim` | Project text renderer and animations |
| `run.sh white` | Worst-case power draw — **watch the PSU** |
| `run.sh` | Cycle everything |
| `run.sh tune` | Steps through light→heavy timing presets (12 s each); pick the lightest that looks clean |
| `run.sh monitor` | Pi health only (run in a 2nd SSH window) |
| `run.sh --single` | One panel only (`--mapping`, `--multiplexing`) |

Tuning flags (override `config.py` for one run): `--brightness --pwm-bits
--lsb-ns --slowdown --refresh-limit --multiplexing --row-address --mapping`.

Laptop preview (no Pi): `python3 panel_setup/display_test.py --sim`

## Keeping the load light
The refresh thread always uses one core (see above); what we control is how hard
it works and how much Python adds. Already done in `led_matrix.py`:
- panel remap is a precomputed reshape/index (~0.1 ms/frame — never the bottleneck);
- power estimate uses a 1-in-16 pixel subsample;
- **unchanged frames are not re-uploaded** — static text/held frames cost ~0.

Tuning (`./panel_setup/run.sh tune`): the defaults are `pwm_bits=7`, slowdown 3, `panel_type FM6126A`, mapping `regular`.
Colour depth per channel is 2^bits levels (7 → 128, 8 → 256, 6 → 64). The
library already applies luminance correction, so 7 bits still looks smooth in
normal content; `pwm_dither_bits=1` recovers smooth fades for a small refresh
cost. `gpio_slowdown` 3 is confirmed on these panels; lower values are untested here. Use the
lightest preset that shows no flicker, banding or noise on the bar test.

## Pi health monitoring
Every test prints a `[PI]` line every 2 s and logs to `panel_setup/monitor.csv`:
```
[PI] cpu  62% (worst core 98%) | 58°C 1800MHz | mem 14% |  29.8 fps draw 11.2ms (max 25) | ~5.0A | ok
```
- **worst core ~100%**: the matrix refresh thread is saturating a core — expected;
  use `isolcpus=3` so it has one to itself.
- **fps below target / draw ms high**: Python remap+SetImage is the bottleneck.
- **temp ≥ 75°C** warns once; ≥ 80°C means throttling is close — add a heatsink/fan.
- **UNDERVOLTAGE / THROTTLED** flags come from `vcgencmd get_throttled`. Undervoltage
  = the Pi's 5 V is sagging; check the Pi's own supply and panel power wiring.
- Copy the CSV back with `scp <user>@<host>:magic-mirror/panel_setup/monitor.csv .`
 .

## 4. Fix what you see
- **Indices not 0,1,2… along the cable** → edit `PANEL_CHAIN_ORDER` in `config.py`
  (list of `(col, row)` per chain position, starting at the HAT cable).
- **A panel upside down** → `PANEL_ROTATE = {chain_index: 180}`.
- **Scrambled/striped image** → `--multiplexing 1` (or 2, 4); try `--row-address 3`.
- **Flicker / low refresh** → lower `--pwm-bits` (7→6), `--lsb-ns` (130→100),
  `--slowdown` (4→2); add `isolcpus=3` to `/boot/firmware/cmdline.txt`;
  disable onboard audio (done by `install.sh`).

## Power (40 A @ 5 V PSU)
12 panels at full white ≈ 48 A. Protections:
- `MATRIX_BRIGHTNESS = 40` (full white ≈ 19 A)
- `MATRIX_MAX_AMPS = 28`: the driver estimates current per frame and dims it
  to stay under budget. `MATRIX_AMPS_PER_PANEL = 4.0` is a guess — measure.
- Give each panel (or pair) its own power lead to the PSU. Share GND with the Pi only.

## Running the whole program without a touch sensor
```bash
sudo python3 main.py --no-touch --mock-camera static --no-api     # display + silhouette + text
sudo python3 main.py --no-touch --auto 20                          # a cycle every 20 s
sudo python3 main.py --no-touch --auto 20 --auto-booth-every 3     # every 3rd = photobooth
```
Without `--auto`, trigger from the dashboard (`http://<pi-ip>:5000`) or
`curl -X POST http://<pi-ip>:5000/api/trigger/short` (`/long` = photobooth).
Drop `--mock-camera static` once the Pi camera is attached (`--mock-camera webcam`
for a USB webcam). The LED strip and printer are optional and skipped if absent.

## Autostart on boot
```bash
./panel_setup/install_autostart.sh            # lava & coral gallery at every boot
./panel_setup/install_autostart.sh art        # or any play.py animation
./panel_setup/install_autostart.sh --remove   # turn it off
sudo systemctl stop wall-art                  # stop it for now (e.g. to run tests)
```
Installs `wall-art.service` (restarts on crash) and disables `magic-mirror.service`
so only one program drives the panels. Stop it before running other panel tools.
