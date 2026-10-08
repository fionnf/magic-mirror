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
./panel_setup/install_autostart.sh ambient    # art + tram ticker
./panel_setup/install_autostart.sh            # lava & coral gallery (current default)
./panel_setup/install_autostart.sh art        # or any play.py animation
./panel_setup/install_autostart.sh --remove   # turn it off
sudo systemctl stop wall-art                  # stop it for now (e.g. to run tests)
```
Installs `wall-art.service` (restarts on crash) and disables `magic-mirror.service`
so only one program drives the panels. Stop it before running other panel tools.

## Music "designer brain": OpenAI or Claude
The Music card on the website has a **Designer brain** switch:
- **OpenAI · hears** (default): `gpt-audio` listens to a 10 s clip every 30 s and designs the scene.
- **Claude · text**: Claude Code (Haiku) designs from text only - the Shazam song title, bass/mid/treble
  levels, energy, tempo, time of day and its last scenes - every 60 s. It cannot hear audio.

If Claude is selected but not set up, the app says what is missing and the wall carries on
with the built-in rules. To set it up (steps per Anthropic's docs - verify them, and check the
usage terms for always-on automated use of a *subscription* before relying on it; an API key is
the other option):
1. On the Pi: `curl -fsSL https://claude.ai/install.sh | bash` (installs to `~/.local/bin/claude`)
2. On your laptop: `claude setup-token` -> copy the token it prints
3. On the Pi, add to `~/magic-mirror/.env` (never commit it):
   `CLAUDE_CODE_OAUTH_TOKEN=<token>`   (or `ANTHROPIC_API_KEY=<key>`), optional `CLAUDE_MODEL=haiku`
4. `sudo systemctl restart wall-control`, then pick "Claude · text" in the app.
Test the CLI alone first: `claude -p "say hi" --model haiku` on the Pi.

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

## Free Gemini as the music designer (default brain)
Music mode's **Gemini · free** brain calls Gemini 3.5 Flash-Lite (fallbacks: `gemini-flash-lite-latest`,
3.1 Flash-Lite) on Google's free tier. Keep the key's project **without billing** (or set a budget cap), so a
used-up free quota can never turn into charges. It sends **text only** (Shazam song, bass/mid/treble levels, energy, tempo, time of
day, its last scenes) - never audio. Free-tier requests may be used by Google to improve their
products, which is why the room microphone is never sent.
1. Create a free key at https://aistudio.google.com/apikey (any Google account).
2. On the Pi add one line to `~/magic-mirror/.env` (never commit it): `GEMINI_API_KEY=<key>`
   (optional: `GEMINI_MODEL=<model>`)
3. `sudo systemctl restart wall-control`, then check the Music card: it should say
   "Gemini free (gemini-3.5-flash-lite) ok". Without a key, or when the free-tier limit is hit
   (it rests for 10 min), the wall uses the built-in rules - it never falls back to a paid model.
Quick key test on the Pi:
```
curl -s -H "x-goog-api-key: $GEMINI_API_KEY" -H 'Content-Type: application/json' \
  -d '{"contents":[{"parts":[{"text":"say hi"}]}]}' \
  https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent
```

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
