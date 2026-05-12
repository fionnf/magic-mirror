# Magic Mirror

Raspberry Pi-driven smart mirror: a camera + capacitive touch trigger captures
the person standing in front of a one-way acrylic sheet, sends the image to
OpenAI (`gpt-4o-mini`, vision), and renders the response as animated text on a
128×64 HUB75 LED matrix (2×2 P5 panels) hidden behind the glass.

A live silhouette of whoever is in frame is rendered continuously as the
background of every state — idle, thinking, and speaking — so the mirror
always "sees" you.

## Hardware

- Raspberry Pi 4 (2GB+)
- Adafruit RGB Matrix HAT (#2345)
- 6× HUB75E **64×64** panels, arranged 2 wide × 3 tall (**portrait**, total
  canvas 128 × 192). Chain serpentine: HAT → top-left → top-right →
  middle-right → middle-left → bottom-left → bottom-right.
  - Default `PIXEL_MAPPER = "U-mapper"` in [`config.py`](config.py) — if your
    image is mirrored, flipped, or split, try `"U-mapper;Rotate:180"`,
    `"V-mapper"`, or re-wire. The mapper has to match your physical chain.
  - Confirm scan rate from the sticker; most 64×64 panels are 1/32, which is
    the new default (`SCAN_RATE = 32`).
- 5V 40A PSU **direct to panels**. Share **GND only** with the Pi. Never feed
  panel +5V through the Pi.
- Pi Camera Module v3 (or v2)
- Capacitive touch sensor (e.g. TTP223 breakout): `VCC` → 3V3, `GND` → GND,
  `SIG` → GPIO 25. Default config assumes active-HIGH output with no pull
  resistor. If your module's jumper is set to active-LOW, flip
  `TOUCH_ACTIVE_HIGH` and `TOUCH_PULL` in [`config.py`](config.py).

## Install on the Pi

```bash
git clone <this repo> magic-mirror
cd magic-mirror
./install.sh
sudo reboot
sudo systemctl start magic-mirror.service
```

`install.sh` will:

1. apt-install build deps + `picamera2` + OpenCV.
2. Clone & build [`rpi-rgb-led-matrix`](https://github.com/hzeller/rpi-rgb-led-matrix)
   Python bindings.
3. Install pip requirements.
4. Copy `.env.example` → `.env` and prompt for your `OPENAI_API_KEY`.
5. Disable Pi onboard audio (`dtparam=audio=off`) — required, the audio PWM
   conflicts with the HUB75 clock pin.
6. Install and enable a `systemd` service that auto-starts on boot.

## SK6812 RGBWW LED strip around the frame (optional)

The mirror can drive an addressable RGBWW strip (e.g. SK6812 60 LEDs/m)
wrapped around the perimeter. It's **fully optional** — if the strip isn't
wired up or the library isn't installed, the project runs unchanged with
no strip behaviour. The strip is also rendered in the simulator window as
a border around the matrix preview, so you can see it without the hardware.

### Behaviours

| State | Strip |
|---|---|
| Idle / displaying / fading | Warm white base with a slow-drifting hue band that *follows the silhouette horizontally* — the colour bloom tracks where you're standing. |
| Countdown (3-2-1) | Breathes on/off in sync with the on-screen countdown. |
| Photo capture moment | Solid bright white (uses the dedicated W channel). |
| Thinking (AI in flight) | Hue band pulses gently. |

### Wiring — **important, has a real conflict**

The Adafruit RGB Matrix HAT uses **GPIO 18 / PWM** for panel OE. `rpi_ws281x`
defaults to the same pin. They will fight and the strip will glitch or the
panels will flicker.

**Solution: drive the strip over SPI (GPIO 10 / MOSI) instead.** This is the
default in [`config.py`](config.py) (`LED_STRIP_PIN = 10`). It needs three
things on the Pi:

1. Enable SPI:
   ```bash
   sudo raspi-config   # Interface Options → SPI → Enable
   ```
2. Pin SPI frequency for stable timing — append to `/boot/firmware/config.txt`
   (or `/boot/config.txt` on older OSes):
   ```
   core_freq=250
   core_freq_min=250
   ```
   then reboot.
3. The `rpi_ws281x` user must be able to access `/dev/spidev0.0`. The
   systemd unit runs as root, so this is already fine.

### Strip wiring

- **VCC** → 5V (use the panel PSU — the strip can pull 60mA × LEDs × 3 channels;
  a 60-LED strip at full white can draw ~3A. Don't power from the Pi.)
- **GND** → common ground (Pi + PSU + strip all share GND)
- **DI (data in)** → Pi **GPIO 10** via a 330Ω series resistor
- Optionally a level shifter (74AHCT125) for reliability — the Pi's 3.3V
  signal is sometimes marginal for 5V WS/SK strips. Most short runs work
  without one.

### Configuration

In [`config.py`](config.py):

```python
LED_STRIP_COUNT = 60        # how many LEDs you actually have
LED_STRIP_PIN = 10          # leave at 10 (SPI MOSI) to avoid HAT conflict
LED_STRIP_BRIGHTNESS = 180  # 0-255
LED_STRIP_BAND_FRACTION = 0.25  # width of the hue band as % of strip length
LED_STRIP_HUE_SPEED = 0.05  # how fast the colour drifts; Hz-ish
LED_STRIP_WARM_LEVEL = 60   # warm-white base brightness (W channel, 0-255)
```

If `rpi_ws281x` isn't installed or the strip fails to init, the project logs
`[STRIP] not available, disabling: …` and runs without it.

## Thermal receipt printer (optional)

A 56 mm ESC/POS thermal receipt printer connected via USB can print a
**physical keepsake** after every cycle: header, portrait-cropped photo,
and the AI's response in chunky double-size bold underneath. Same printer
family as your existing Slack `/ptsk` setup — `Usb(0x0416, 0x5011)` is the
default.

### Wiring & permissions

1. Plug the printer into a free USB port on the Pi. It needs **its own
   power** — these printers pull 1.5–2 A peaks, more than the Pi can
   safely supply.
2. Find its USB IDs (in case you have a different model):
   ```bash
   lsusb
   # Bus 001 Device 005: ID 0416:5011 Winbond Electronics ...
   ```
   Update `PRINTER_VENDOR_ID` / `PRINTER_PRODUCT_ID` in [`config.py`](config.py)
   if they differ.
3. Grant non-root USB access (the `systemd` unit runs as root anyway, so
   this is only needed if you run `main.py` manually as a user). Create
   `/etc/udev/rules.d/99-thermalprinter.rules`:
   ```
   SUBSYSTEM=="usb", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5011", MODE="0666"
   ```
   Then `sudo udevadm control --reload-rules && sudo udevadm trigger`.

### What gets printed

```
        MAGIC MIRROR
       2026-05-12  19:04

      [portrait photo —
       384 dots wide,
       3:4 aspect,
       autocontrasted]

  YOUR EYES HOLD
   THE WEIGHT OF
   FORGOTTEN STARS

         (cut)
```

### Tuning

In [`config.py`](config.py):

- `PRINTER_WIDTH_DOTS = 384` — drop to 360 if the right edge wraps.
- `PRINTER_TEXT_COLS = 16` — chars per line at 2×2 font size.
- `PRINTER_IMAGE_ASPECT = 0.75` — width/height. Lower = taller image.

### Graceful disable

If the printer is unplugged or python-escpos isn't installed, the mirror
logs `[PRINTER] not connected; skipping receipt` and runs unchanged. To
disable entirely, just keep the printer disconnected — there's no flag
to flip.

## Google Drive archive (optional)

Every time the mirror takes a photo and gets an AI response, the JPEG can be
uploaded to a Google Drive folder you own, with the AI's response stored in
the file's `description` field so you can browse the archive later.

The integration is **fully optional** — leave `GOOGLE_DRIVE_FOLDER_ID` blank
or omit `gcp-credentials.json` and the mirror runs exactly the same, it just
won't upload.

### One-time Google Cloud setup

You'll do this once, in a browser, on any machine. It takes ~5 minutes.

#### 1. Create (or pick) a Google Cloud project

1. Go to https://console.cloud.google.com
2. Top bar → project dropdown → **New Project**.
3. Name it e.g. `magic-mirror`. No org needed. Click **Create**.
4. Wait for it to finish, then make sure the new project is selected in the
   top bar.

#### 2. Enable the Drive API

1. Left nav → **APIs & Services** → **Library**.
2. Search "Google Drive API" → click it → **Enable**.

#### 3. Create a service account

A service account is a robot Google identity that the Pi will use — no
browser-based login required, which is what we want on a headless device.

1. Left nav → **IAM & Admin** → **Service Accounts** → **+ Create service
   account**.
2. **Name**: `magic-mirror-uploader` (anything works). Click **Create and
   continue**.
3. Skip the optional "Grant access" step — click **Continue**, then **Done**.
4. You're back on the service-accounts list. **Copy its email address** —
   it looks like `magic-mirror-uploader@magic-mirror.iam.gserviceaccount.com`.
   You'll need it in step 5.

#### 4. Generate a JSON key

1. Click the service account row.
2. **Keys** tab → **Add key** → **Create new key** → **JSON** → **Create**.
3. Your browser downloads a `.json` file. **This is a secret — treat it
   like a password.**
4. Rename the file to `gcp-credentials.json` and drop it in the project root,
   next to `main.py`. (`.gitignore` already excludes it.)

If you're setting up the Pi from a Mac, the simplest transfer is:

```bash
scp ~/Downloads/<that-long-name>.json pi@<pi-hostname>:~/magic-mirror/gcp-credentials.json
```

#### 5. Create a Drive folder and share it with the service account

1. Go to https://drive.google.com → **New** → **Folder** → name it
   "Magic Mirror" (anything).
2. Right-click the folder → **Share** → paste the service-account email
   from step 3 → set role to **Editor** → **Send**. Google may warn that
   "this address can't receive notifications" — that's expected, the
   service account doesn't have an inbox. Click **Share anyway**.
3. Open the folder. Look at the URL: it ends in
   `…/folders/<FOLDER_ID>?…`. Copy `<FOLDER_ID>`.

#### 6. Tell the mirror where to upload

Edit `.env` and add:

```env
GOOGLE_DRIVE_FOLDER_ID=<paste the folder ID here>
```

That's it. The next mirror cycle will upload its frame to that folder. On
first upload, the console prints e.g.:

```
[DRIVE] uploaded mirror_2026-05-12_19-04-31.jpg -> https://drive.google.com/file/d/…/view
```

### What gets stored

- **Filename**: `mirror_YYYY-MM-DD_HH-MM-SS.jpg`
- **Image**: the exact frame that was sent to OpenAI (full camera resolution,
  JPEG quality 88).
- **Description field**: the AI's response text. Visible in Drive's right-hand
  details pane and searchable.

### Troubleshooting

- **`[DRIVE] init failed: …file not found`** — `gcp-credentials.json` isn't
  where the code expects. Make sure it's in the project root and the working
  directory is correct (the `systemd` unit sets `WorkingDirectory`).
- **`[DRIVE] upload failed: … 404 … File not found`** — the folder ID is
  wrong, or you forgot to share the folder with the service account. Recheck
  step 5.
- **`[DRIVE] upload failed: … 403 … insufficientPermissions`** — the service
  account has only Viewer access. Re-share as **Editor**.
- **Nothing happens, no `[DRIVE]` log lines** — either `GOOGLE_DRIVE_FOLDER_ID`
  is empty in `.env` or `gcp-credentials.json` is missing. Both must be
  present for uploads to fire.
- **Storage quota**: uploads count against the service account's 15GB free
  Drive quota by default, not yours. If you'd rather they count against your
  personal account, set the service account as the *file owner's delegate* —
  or just sweep the folder periodically; mirror JPEGs are ~100KB each.

### Disabling later

Comment out or blank the `GOOGLE_DRIVE_FOLDER_ID` line in `.env` and restart
the service. Or delete `gcp-credentials.json`. Either is enough.

## Tuning the panels

1. **Scan rate**: read the sticker on the panel (1/16 or 1/32) and set
   `SCAN_RATE` in [`config.py`](config.py).
2. **Display glitches / scrambled output**: raise `GPIO_SLOWDOWN` (try 3, 4, 5).
3. **Brightness**: `matrix.set_brightness(0–100)` or edit the default in
   `led_matrix.py`.

## Running manually

```bash
python3 main.py
```

## Usage log

Every API call appends `timestamp\ttokens_in\ttokens_out` to `usage.log`:

```bash
cat usage.log
```

## Simulator / pre-hardware testing

Run everything on your Mac/Windows/Linux laptop before the Pi or panels arrive.
A pygame window replaces the LED panels, your webcam (or a static JPEG)
replaces the Pi camera, and the SPACE bar replaces the physical button.

```bash
pip install -r requirements-dev.txt

# Full end-to-end run, identical state machine, real OpenAI API:
python tests/test_full_sim.py --camera webcam

# Same but skip API calls (free, canned response):
python tests/test_full_sim.py --camera webcam --no-api

# No webcam? Use a static image:
python tests/test_full_sim.py --camera static

# Or run main.py directly:
python main.py --sim --no-api
```

### Individual tests

| Script | What it does |
|---|---|
| `tests/test_ai.py [--image foo.jpg]` | One OpenAI vision call, prints response + tokens. |
| `tests/test_silhouette.py` | Live webcam preview with contour overlay + 128×64 mask. `S` saves snapshot. |
| `tests/test_animations.py` | Cycles starfield + ripple in sim window. `N` skips. |
| `tests/test_text.py` | Static text, scroll, multi-line, colour cycle. |
| `tests/test_full_sim.py` | Full state machine in sim mode. `--loop N` stress-tests. |

### Sim window controls

- `SPACE` / `ENTER` — press the (virtual) button
- `Q` — quit
- `G` — toggle 64×32 panel boundary grid

The window title bar always shows the current state name
(e.g. `Magic Mirror Simulator — SILHOUETTE`).

## State machine

```
IDLE → TRIGGERED → (3-2-1 countdown) → CAPTURING → AI_WAITING
                                                       ↓
                              DISPLAYING (scrolls 2x) ← (response or timeout)
                                                       ↓
                                                    FADE_OUT → IDLE

Strip:  idle  →  countdown (breathing)  →  capture_flash (white)
                  ↓
                  thinking (hue pulse)  →  displaying  →  fading  →  idle
```

The live silhouette runs in its own thread and is composited as the background
of every state — even during fade-out the person stays visible. All I/O
(camera, OpenAI, Drive upload) runs off the display thread. Any exception in
a cycle is caught and logged; the mirror returns to `IDLE` rather than
crashing.

## Configuration

Every tunable lives in [`config.py`](config.py) — no magic numbers elsewhere.
