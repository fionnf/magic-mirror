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
- 4× P5 SMD2121 HUB75E panels (64×32 each), arranged 2×2, chained in a U
  - HAT → Panel 1 (top-left) → Panel 2 (top-right) → Panel 3 (bottom-right)
    → Panel 4 (bottom-left). The `U-mapper` pixel mapper handles the wrap.
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
```

The live silhouette runs in its own thread and is composited as the background
of every state — even during fade-out the person stays visible. All I/O
(camera, OpenAI, Drive upload) runs off the display thread. Any exception in
a cycle is caught and logged; the mirror returns to `IDLE` rather than
crashing.

## Configuration

Every tunable lives in [`config.py`](config.py) — no magic numbers elsewhere.
