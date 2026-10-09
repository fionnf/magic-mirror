# Running the wall (9 × 64×64 HUB75, 3 × 3, 192 × 192 px)

How to install, deploy, run, tune and troubleshoot the wall. Everything reads `../config.py`
(panel layout, chain order, timing, power). For an overview see the top-level README.

## 0. On a laptop: the simulator
```bash
./panel_setup/sim.sh        # http://localhost:8080, panels open in a window
```
Same app and modes as on the Pi; music listens to the Mac microphone (`MIC="..."` to choose),
mirror mode uses the Mac webcam. GPU shaders need `pip install moderngl`.

## 1. Install on the Pi (once)
See *New Pi from scratch* below: deploy, then `./panel_setup/bootstrap_pi.sh` and a reboot.
It installs the system packages, compiles the panel library, installs the Python packages,
turns off the onboard audio (it conflicts with the panels), installs the `wall-control`
service (the app on port 80) and runs a health check.

## 2. Send code to the Pi (from your laptop)
```bash
PI_USER=pi PI_HOST=192.168.1.129 ./panel_setup/deploy.sh
```
It rsyncs the project to `~/magic-mirror` (skips `.env`, tokens, photos, git, and the Pi's own
settings/state files). Then `sudo systemctl restart wall-control` on the Pi.

## 3. Run on the Pi
```bash
ssh pi@192.168.1.129
cd ~/magic-mirror
sudo systemctl stop wall-control    # the app drives the panels; stop it for the bring-up tools
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
  disable onboard audio (done by `bootstrap_pi.sh`: it also blacklists `snd_bcm2835`).

## Power (40 A @ 5 V PSU)
12 panels at full white ≈ 48 A. Protections:
- `MATRIX_BRIGHTNESS = 40` (full white ≈ 19 A)
- `MATRIX_MAX_AMPS = 28`: the driver estimates current per frame and dims it
  to stay under budget. `MATRIX_AMPS_PER_PANEL = 4.0` is a guess — measure.
- Give each panel (or pair) its own power lead to the PSU. Share GND with the Pi only.

## New Pi from scratch
1. Raspberry Pi Imager: Raspberry Pi OS Lite (64-bit), user `pi`, hostname, your **home** Wi-Fi,
   SSH on with your public key (`~/.ssh/id_rsa.pub`).
2. Boot with the camera ribbon already attached (the CSI port is only probed at power-on).
3. Join a network (see below), then from the laptop: `PI_HOST=<ip> ./panel_setup/deploy.sh`
4. On the Pi: `cd ~/magic-mirror && ./panel_setup/bootstrap_pi.sh && sudo reboot`
5. Copy the secrets over: `.env` (and `token.json` / `oauth_client.json` if Drive uploads are used).

Joining eduroam on a keyboard-only Pi (NetworkManager). `--ask` prompts for the password so it
never lands in the shell history; check the exact identity / CA settings with your institution's
eduroam page (or https://cat.eduroam.org):
```
sudo nmcli --ask connection add type wifi con-name eduroam ifname wlan0 ssid eduroam \
  wifi-sec.key-mgmt wpa-eap 802-1x.eap peap 802-1x.phase2-auth mschapv2 \
  802-1x.identity "USERNAME@your.institution" 802-1x.system-ca-certs yes
sudo nmcli connection up eduroam
```
A web-login ("captive portal") network cannot be completed on a headless Pi: use eduroam,
Ethernet, or a phone hotspot instead.

## Portrait photos that keep people in frame
Every photo (the picture the AI comments on, the receipt, the photobooth shots) is cut to
portrait **around the people**: a small local face detector (`smartcrop.py`, model in
`assets/models/`) places the crop over everyone's face; if no face is found it uses where the
scene changed against the empty room, then the centre. The website's Mirror card has a switch
("Follow people when cropping photos to portrait") and shows the last photo with the AI's line.
The live silhouette on the wall keeps its cheap centred crop.

## Smart Life lights (Tuya, local control)
The website's **Lights** card switches your Smart Life lights/plugs off (and on) over the home
network with `tinytuya` - fast, no cloud at runtime, works if the internet is down - plus an
optional nightly "lights off at HH:MM". Google Home is not needed. One-time setup, **at home**
(the laptop must be on the same Wi-Fi as the lights); each light's *local key* comes from Tuya's
developer cloud:
1. Create a free account at https://iot.tuya.com -> Cloud -> Development -> **Create Cloud Project**
   (industry "Smart Home", data centre **Central Europe** for Switzerland). Note its **Access ID**
   and **Access Secret**. Under the project's *Service API*, make sure **IoT Core** and
   **Authorization** are subscribed.
2. In the project, *Devices* -> **Link Tuya App Account** -> *Add App Account*, and scan the QR code
   with the **Smart Life** app (Me -> the scan icon). Your lights now appear under the project.
3. On the laptop, in the project folder:
   `pip install tinytuya && python -m tinytuya wizard`
   Enter the Access ID, the Access Secret, any one device ID from the project's device list and the
   region (`eu` for Central Europe); say yes to scanning the network for IP addresses. It writes
   `devices.json` (names, local keys, IPs) - and `tinytuya.json` (your API secret).
4. `./panel_setup/deploy.sh` copies `devices.json` to the Pi (not `tinytuya.json`), then on the Pi
   `sudo pip3 install --break-system-packages tinytuya` (the bootstrap script does this) and
   `sudo systemctl restart wall-control`. The lights show up in the Lights card.
Keep `devices.json` / `tinytuya.json` out of git (they are ignored): they hold the keys to your lights.
The **Living room** group (default: "Living room lights" + "White LED strip") is what the 🌙 button and the
nightly schedule switch off; tap the 🏠/＋ tag next to a light in the app to add or remove it from the group.
**At home**, press 🔍 Find lights once (or run it again if a light's address changes): it scans the Wi-Fi and
caches each light's IP address and protocol version. Sensors, the gateway and Zigbee sub-devices are never
controlled. To use only some devices, create `panel_setup/lights.json` with `{"only": ["Living room lights"]}`.
Give each light a fixed address in your router (DHCP reservation), or re-run the wizard if one moves.
Re-pairing a light in the Smart Life app changes its local key - re-run the wizard then.

## Mirror extras (app: "Mirror voice & people", Mirror mode, Dedications)
- **Tone & language**: slider kind -> roast and a language (English, Deutsch, Züridütsch, Français, Drama queen);
  applies to the very next photo, no restart (`mirror_settings.json`).
- **Smile sparkles**: smile ratio from the face landmarks (`moods.py`; tune with env `MIRROR_SMILE_RATIO`, default 0.90 -
  higher = needs a bigger smile). Switch in the app.
- **People**: "Learn my face" needs mirror mode running (it looks through the camera ~5 s). Stored only as numbers in
  `faces.json` on the Pi. "Learn frequent faces" is OFF by default; it suggests unnamed regulars after 5 sightings on 2 days.
  Models: `assets/models/get_models.sh` (the bootstrap script runs it).
- **Aura** / **Pixel selfie** buttons (mirror mode): AI colour reading with the wall glowing in that colour; 48x48 sprite portrait.
- **Nobody around**: after N quiet minutes (default 10) the mirror shows Lava & Coral; motion or a face brings the silhouette back only if "Motion or a face brings the mirror back" is ticked in the app (default off: only a button does).
- **Dedications**: guests open `http://<pi>/d` (or scan the QR from the app) - messages scroll across the bottom of the wall.
  No filtering by design; pause / delete / clear in the app. Off until you switch it on.
- **Art**: *Shapes* (13 thin generative line patterns; also available as music styles) and *Light Art* (stained glass,
  Julia set, kaleidoscope, long-exposure trails, nebula).

## Music mode: the party slider
The **Party level** slider (0-100 %) sets everything: at 0 the art just breathes (slow painterly
pieces, a few-percent swell with the bass, never a flash); towards 100 it becomes neon geometry
whose motion follows the beat, with scene changes on 4-bar boundaries. Brightness never pulses on
the beat. Optional "let the wall listen" (under More) estimates the level from loudness, beat lock,
tempo and bass (`display/intensity.py`). The app shows the live microphone (level, bass, detected
beats) next to the Sensitivity slider: raise it if the trace stays flat while music plays.
"Video loops only" plays the clip library (pick one, or Auto); "Music affects the loops" sets how.

## AI (Claude)
All AI features call the Anthropic API through `ai_client.ask()` (model `config.AI_MODEL`, low
effort, server-side refusal fallbacks, structured JSON where needed). Put `ANTHROPIC_API_KEY=...`
in `.env` on the laptop and copy it to the Pi (`scp .env pi@<ip>:~/magic-mirror/.env`), then
restart `wall-control`. Without a key every feature falls back to built-in text/rules.

## Video loops
`tools/make_loops.py <folders>` converts any video folder to 192 × 192 clips in `assets/loops/`
(with an index of motion/brightness the curator uses); deploy copies them. The current library is
abstract Beeple clips (CC) and calm Mixkit footage; originals live in `~/Movies/VJ Loops/`.
