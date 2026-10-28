# Running the wall: install, deploy, tune, troubleshoot

How to install, deploy, run, tune and troubleshoot the wall on a Raspberry Pi. Everything reads
`../config.py` (panel layout, chain order, timing, power). The default layout is **3 panels wide by
4 tall (12 panels, 192 x 256 px) on two chains of six**; `WALL_PANELS_TALL=3` selects a single chain of
nine (192 x 192). See "Scaling to your own size" in the top-level [README](../README.md) before you
wire anything. Where this page says "the wall", it means the Pi plus the panels.

## 0. On a laptop: the simulator
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
./panel_setup/sim.sh        # app at http://localhost:8080, panels in a pygame window
```
`sim.sh` uses `.venv/bin/python` when it exists; `PORT=8099 ./panel_setup/sim.sh` changes the port (the
banner it prints still says 8080). Same app and modes as on the Pi. Notes:
- Music listens to the **Mac** microphone (`MIC="..."` to choose one). That stream uses ffmpeg's macOS
  `avfoundation` input; on Linux or Windows there is no microphone input unless you send 16-bit mono
  22.05 kHz audio to UDP port 9099 yourself.
- Mirror mode uses the laptop webcam.
- GPU shaders (most of the art, including Art of the day, the default) need `moderngl` and an OpenGL 3.3
  context. Without one the shader pieces draw black; the other galleries (Lava & Coral, Shapes, Art
  Gallery, Artsy, Light Art) do not need a GPU.
- The simulator runs the same background jobs as the real wall, so it writes into `assets/daily/` (an
  offline piece for today, and finishing the bundled past days). `git checkout assets/daily && git clean -fd assets/daily` resets that.

## 1. Install on the Pi (once)
See *New Pi from scratch* below: deploy, then `./panel_setup/bootstrap_pi.sh` and a reboot.
It installs the system packages, compiles the panel library ([hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)),
installs the Python packages, turns off the onboard audio (it conflicts with the panels), downloads the face
models, installs the `wall-control` service (the app on port 80) and runs a health check. The script's own
header says it has **not yet been run on a fresh image**: read its output.

Not installed by the script (install by hand if you want the feature; all are optional except the first):
`moderngl` (GPU shaders: without it Art of the day and every shader piece are black), `pychromecast` ("Follow the
speakers"), `bleak` (the Bluetooth colour rods), `sgp4` (more exact satellites), `cloudflared` (remote access). Example:
`sudo pip3 install --break-system-packages --root-user-action=ignore moderngl pychromecast`.

## 2. Send code to the Pi (from your laptop)
```bash
PI_USER=pi PI_HOST=192.168.1.129 ./panel_setup/deploy.sh
```
`PI_HOST` defaults to `192.168.1.129` (the author's Pi): always set your own. `PI_USER` defaults to `pi`, `PI_DIR`
to `magic-mirror` (relative to the Pi user's home). The script rsyncs the project to `~/magic-mirror` and skips `.env`,
tokens, photos, git, every `*.png`/`*.jpg` (except the app's thumbnails) and the Pi's own settings/state files.
Then `sudo systemctl restart wall-control` on the Pi.

> **Important: the service updates itself from GitHub.** The `wall-control` unit written by
> `install_control.sh` runs `panel_setup/update.sh` before every start. That script fetches `master` from
> `git@github.com:fionnf/magic-mirror.git` (or the https URL when there is no deploy key) and runs
> `git reset --hard FETCH_HEAD`: **tracked files, including your `config.py` edits, are replaced by the author's
> latest code** (untracked files such as `.env` and the state files are kept). The app's *Update & restart* button
> does the same. Pick one:
> - use your own fork: change the two URLs in `update.sh` to your repository (it needs a `master` branch), or
> - stop it: `sudo sed -i '/ExecStartPre/d' /etc/systemd/system/wall-control.service && sudo systemctl daemon-reload && sudo systemctl restart wall-control`.
>   Re-running `install_control.sh` (the bootstrap does) writes the line back. And `deploy.sh` skips PNG files, which the git
>   pull normally supplies (for example `assets/maps/land_mask.png`, used by the Earthquakes piece): if you stop the self-update,
>   clone your fork on the Pi (`git clone https://github.com/<you>/magic-mirror ~/magic-mirror`) instead of using `deploy.sh`.

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
| `run.sh white` | Worst-case power draw: **watch the PSU** |
| `run.sh` | Cycle everything |
| `run.sh tune` | Steps through light-to-heavy timing presets (12 s each); pick the lightest that looks clean |
| `run.sh monitor` | Pi health only (run in a 2nd SSH window) |
| `run.sh --single` | One panel only (`--mapping`, `--multiplexing`) |

Tuning flags (override `config.py` for one run): `--brightness --pwm-bits --dither --lsb-ns --slowdown
--refresh-limit --multiplexing --row-address --mapping --panel-type`.

## Keeping the load light
The refresh thread always uses one core; what we control is how hard it works and how much Python
adds. Already done in `led_matrix.py`:
- panel remap is a precomputed reshape/index (~0.1 ms/frame, never the bottleneck);
- power estimate uses a 1-in-16 pixel subsample;
- **unchanged frames are not re-uploaded**: static text/held frames cost ~0.

Current settings in `config.py` (see the comments there for the measurements behind them):
`GPIO_SLOWDOWN = 7`, `MATRIX_PWM_BITS = 6` (the driver raises it to 7 or 8 bits for very dark pictures:
`DEPTH_STEPS`), `MATRIX_PWM_LSB_NS = 60`, refresh locked at `MATRIX_REFRESH_LIMIT_HZ = 100`, panel type
`FM6126A`, mapping `regular`, brightness 40. Colour depth per channel is 2^bits levels (6 -> 64, 7 -> 128,
8 -> 256). `MATRIX_PWM_DITHER_BITS` (0-2) smooths fades at a small refresh cost. These are what worked on the
author's panels and Pi 4; yours may want other values, so use `./panel_setup/run.sh tune` and copy the lightest clean preset
into `config.py` (`GPIO_SLOWDOWN`, `MATRIX_PWM_BITS`, `MATRIX_PWM_DITHER_BITS`, `MATRIX_PWM_LSB_NS`).
The comment in `config.py` records that with these panels slowdown 3 gave streaks and 7 the cleanest data.

## Pi health monitoring
Every test prints a `[PI]` line every 2 s and logs to `panel_setup/monitor.csv`:
```
[PI] cpu  62% (worst core 98%) | 58°C 1800MHz | mem 14% |  29.8 fps draw 11.2ms (max 25) | ~5.0A | ok
```
- **worst core ~100%**: the matrix refresh thread is saturating a core. Expected; `isolcpus=3` in
  `/boot/firmware/cmdline.txt` gives it a core to itself (not set by the bootstrap).
- **fps below target / draw ms high**: Python remap + SetImage is the bottleneck.
- **temp >= 75°C** warns once; >= 80°C means throttling is close: add a heatsink/fan.
- **UNDERVOLTAGE / THROTTLED** flags come from `vcgencmd get_throttled`. Undervoltage = the Pi's 5 V is sagging;
  check the Pi's own supply and panel power wiring.
- Copy the CSV back with `scp <user>@<host>:magic-mirror/panel_setup/monitor.csv .`

## 4. Fix what you see
- **Indices not 0,1,2... along the cable** -> edit `PANEL_CHAIN_ORDER` in `config.py`
  (list of `(col, row)` per chain position, starting at the Bonnet cable).
- **A panel upside down** -> `PANEL_ROTATE = {chain_index: 180}`.
- **Scrambled/striped image** -> `--multiplexing 1` (or 2, 4); try `--row-address 3` (display_test commands such as `run.sh walk`); with `run.sh --single` the flag is `--row-addr-type 3`.
- **Flicker / low refresh** -> lower `--pwm-bits` (7->6, 6->5), `--lsb-ns`, or the refresh limit;
  run `run.sh tune`; add `isolcpus=3` to `/boot/firmware/cmdline.txt`; keep onboard audio off
  (`bootstrap_pi.sh` does that: it also blacklists `snd_bcm2835`).
- **Dark or garbled panels that are wired correctly** -> the panel type: `config.MATRIX_PANEL_TYPE = "FM6126A"`
  is the init sequence these (FM6124/FM6126A driver) panels need; other drivers may need another value or none.

## Power (5 V PSU)
`config.py` estimates 4 A per panel at full white (`MATRIX_AMPS_PER_PANEL`, a guess: measure yours). So 12
panels at full white are about 48 A, more than the 40 A supply in the parts list. Protections in software:
- `MATRIX_BRIGHTNESS = 40` (full white then ~19 A by that estimate; 9 panels ~14 A);
- `MATRIX_MAX_AMPS = 28`: the driver estimates current per frame from pixel values and dims the frame to stay under it.
  This is an estimate, **not** a fuse or a measurement.
- Give each panel (or pair) its own power lead to the PSU. Share GND with the Pi only.
Fit a fuse on the mains side and on the 5 V output, and see the frame's notes in
[`hardware/led-wall-frame`](../hardware/led-wall-frame/README.md).

## New Pi from scratch
1. Raspberry Pi Imager: Raspberry Pi OS Lite (64-bit), user `pi`, hostname, your **home** Wi-Fi,
   SSH on with your public key (`~/.ssh/id_rsa.pub`).
2. Boot with the camera ribbon already attached (the CSI port is only probed at power-on).
3. Join a network (see below), then from the laptop: `PI_HOST=<ip> ./panel_setup/deploy.sh`
4. On the Pi: `cd ~/magic-mirror && ./panel_setup/bootstrap_pi.sh && sudo reboot`
5. Copy the secrets over: `.env` (and `token.json` / `oauth_client.json` if Drive uploads are used).
6. Decide what to do about the self-update (section 2) before you edit anything on the Pi.

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

## Where the app keeps its state
The app writes its settings as JSON under `panel_setup/` (all git-ignored, never overwritten by `deploy.sh`):
`wall_state.json` (mode, brightness, pace, playlist, scenes, camera), `music_settings.json`, `mirror_settings.json`,
`faces.json`, `dedications.json`, `lights.json` / `lights_state.json` / `lights_cache.json`, `rods.json`, the
`*_cache.json` files of the live pieces, and `logs/<mode>.log` (one log per mode: look here first when a mode
misbehaves). `sudo journalctl -u wall-control` has the service's own output.

## Portrait photos that keep people in frame
Every photo (the picture the AI comments on, the receipt, the photobooth shots) is cut to
portrait **around the people**: a small local face detector (`smartcrop.py`, model in
`assets/models/`) places the crop over everyone's face; if no face is found it uses where the
scene changed against the empty room, then the centre. The app's Photos tab can switch this off
(config `SMART_CROP`, env `WALL_SMART_CROP`). The live silhouette on the wall keeps its cheap centred crop.

## Smart Life lights (Tuya, local control)
The app's **Room** tab controls your Smart Life / Tuya lights over the home network with `tinytuya`: fast, no
cloud at runtime for switching, works if the internet is down. The *Living room lights* card appears only
once the wall knows at least one device (`devices.json` or `panel_setup/lights.json`). What it offers:

| Control | What it does |
|---|---|
| All on / All off | Switches every light in "the room" (by default all known lights) |
| Presets | Bright, Evening, Dim, Candle (white at a brightness and warmth); Movie, Party, Ocean (a colour at a brightness) |
| Smart Life scenes | One button per tap-to-run scene read from Smart Life (after an import) |
| Import living room from Smart Life | Reads your Smart Life rooms and scenes from the Tuya cloud: the lights in the Smart Life room whose **name contains "living"** become "the room", and the home's scenes appear as buttons (see below) |
| Brightness, Warmth, Colour | Sliders, a candle-to-daylight white slider, nine swatches and a colour picker; applied to the room |
| Each light | Tap to switch one light; bulbs get their own brightness slider |
| Lights off at | A daily time at which the wall switches the room off (Set / Clear) |

One-time setup, **at home** (the laptop must be on the same Wi-Fi as the lights); each light's *local key* comes
from Tuya's developer cloud:
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
   `devices.json` (names, local keys, IPs) and `tinytuya.json` (your API secret).
4. `./panel_setup/deploy.sh` copies `devices.json` to the Pi (not `tinytuya.json`), then on the Pi
   `sudo pip3 install --break-system-packages tinytuya` (the bootstrap script does this) and
   `sudo systemctl restart wall-control`. The lights show up in the Room tab.

**Import (untested).** The *Import living room from Smart Life* button calls `tinytuya.Cloud()`, which reads the
cloud keys in `tinytuya.json`. `deploy.sh` does not copy that file (it holds your API secret), so for the import to
work on the Pi you have to copy it there yourself, into the project folder. The import code has not been run against a
real Smart Life account yet; if it fails, the app shows the error and nothing else changes. Without it the app
still works: "the room" is simply every known light, and you can choose members through the API
(`POST /api/lights/members {"names": [...]}`).

Lights' addresses: the wizard records them. If a light's address changes, either give it a fixed address in your
router (DHCP reservation) or re-scan with `curl -X POST http://<pi>/api/lights/scan` (at home; there is no button for it
in the app any more). Sensors, the gateway and Zigbee sub-devices are never controlled. To use only some devices,
create `panel_setup/lights.json` with `{"only": ["Living room lights"]}`. Re-pairing a light in the Smart Life app
changes its local key: re-run the wizard.

Keep `devices.json`, `tinytuya.json` and `panel_setup/lights*.json` out of git (they are ignored): they hold the keys to your lights.

## Mirror extras (the More tab, Mirror mode, Guests)
- **Tone & language**: slider sweet -> roast and a language (English, Deutsch, Züridütsch, Français, Drama queen);
  applies to the very next photo, no restart (`mirror_settings.json`).
- **Smile sparkles**: smile ratio from the face landmarks (`moods.py`; tune with env `MIRROR_SMILE_RATIO`, default 0.90:
  higher = needs a bigger smile). Switch in the app.
- **People**: "Learn my face" needs mirror mode running (it looks through the camera ~5 s). Stored only as numbers in
  `faces.json` on the Pi. "Learn frequent faces" is OFF by default; it suggests unnamed regulars after 5 sightings on 2 days.
  Models: `assets/models/get_models.sh` (the bootstrap script runs it).
- **Aura** / **Pixel portrait** buttons (Photos tab, mirror mode): AI colour reading with the wall glowing in that colour; 48x48 sprite portrait.
- **Quiet hours**: after N quiet minutes (the app offers never / 5 / 10 / 30) the mirror shows art; motion or a face
  brings the silhouette back only if "Wake the mirror when someone moves" is ticked (default off: only a button does).
- **Guests**: visitors open `http://<pi>/d` (or scan the QR from the app) and their message scrolls across the bottom of the wall.
  No filtering by design (house rule); pause / delete / clear in the app. Off until you switch it on.
- **Art collections** in the Gallery: Light & form (shaders), Marbling & op-art, Lines & dots, Glass & trails (long-exposure light),
  Coral & breath, Ink & moire, Music visuals and the daily editions. The authoritative list is `display/library.py`.

## Music mode: the party slider
The **Party level** slider (0-100 %) sets everything: at 0 the art just breathes (slow painterly
pieces, a few-percent swell with the bass, never a flash); towards 100 it becomes neon geometry
whose motion follows the beat, with scene changes on 4-bar boundaries. Brightness never pulses on
the beat. Optional "Set the party level from the room" (under *Microphone and listening*) estimates the level from loudness, beat lock,
tempo and bass (`display/intensity.py`). The app shows the live microphone (level, bass, detected
beats) next to the Sensitivity slider: raise it if the trace stays flat while music plays. The
microphone is the first ALSA capture device on the Pi (a USB sound card or USB microphone: the Pi has no
analogue input; check with `arecord -l`). Song names come from Shazam (`shazamio`), or from your speakers
(Cast) and Spotify when "Follow the speakers" is linked.

## AI providers
All AI features go through `ai_client.ask()`. The default provider is **OpenAI** (`config.AI_PROVIDER = "openai"`,
quick calls on `gpt-4.1-mini`, the daily art on `gpt-5.4-mini`, key `OPENAI_API_KEY`). `WALL_AI_PROVIDER=anthropic`
switches to Claude (`config.AI_MODEL`, key `ANTHROPIC_API_KEY`); `groq` is also supported (`GROQ_API_KEY`; it cannot see
pictures, so vision calls go to OpenAI). If the chosen provider has no key but `ANTHROPIC_API_KEY` is set, Claude is used.
Put the keys in `.env` on the laptop and copy it to the Pi (`scp .env pi@<ip>:~/magic-mirror/.env`), then restart
`wall-control`. Without a working key every feature falls back to built-in text or rules.

## Control app extras
**Scenes** (Dinner, Party, Reading, Sleep, plus your own: "+ Save this" keeps the wall as it is now, optionally with
the room lights; hold one you made to remove it), a **sleep timer** (the moon button: off in 30 min / 1 h / 2 h or at a time),
the live preview drawn as **real LED dots** (swipe it left or right for the next collection; an enlarge button fills the screen), and a **Surprise me** button.

## The public gallery
Every day's piece can be published to a public GitHub Pages site, and a GitHub Actions workflow can make the piece when the
wall is off. How it works and what to change for your own fork: [`../docs/gallery.md`](../docs/gallery.md). Remote
control of the wall (password, tunnel): [`../docs/remote-access.md`](../docs/remote-access.md).

## Receipt printer: here, on another Pi, Wi-Fi or Bluetooth

`WALL_PRINTER` in `.env` says where the printer is (default `usb`: plugged into the wall's Pi). The USB vendor/product ids
default to `0x0416` / `0x5011` (a GOOJPRT/Xprinter-type 58 mm printer): check yours with `lsusb` and set `PRINTER_VENDOR_ID` /
`PRINTER_PRODUCT_ID` (hex) if they differ.

| Setup | `WALL_PRINTER` |
|---|---|
| USB on the wall's Pi | `usb` |
| USB on a second Pi elsewhere in the room | `http://<that-pi>.local:8631` + the same `PRINT_KEY` on both |
| Wi-Fi / Ethernet ESC/POS printer | `tcp://<printer-ip>:9100` |
| Bluetooth printer (paired, bound to `/dev/rfcomm0`) | `serial:/dev/rfcomm0` |

Second Pi: copy `print_out.py`, `tools/print_server.py` and `tools/install_print_server.sh` into
one folder on it and run `PRINT_KEY=<secret> ./install_print_server.sh`. It installs a service
on port 8631, and the app's More tab shows whether the printer answers.

Quality always beats speed. Paper is 57 mm, so the printable width is 384 dots at 203 dpi, the
printer's full resolution. Pictures are Atkinson-dithered at exactly that width and sent as native
raster. The head prints slowly and hot (`PRINTER_HEAT`, `PRINTER_DENSITY`, `PRINTER_DITHER` env
vars in `print_out.py` if a printer needs tuning).
