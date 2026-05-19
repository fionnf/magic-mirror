# Magic Mirror

A Raspberry Pi-driven smart mirror: a Pi Camera + capacitive touch sensor captures whoever is standing in front of a one-way acrylic panel, sends the image to OpenAI (`gpt-4o-mini` vision), and scrolls the response as animated text on a **128 × 192** HUB75 LED matrix hidden behind the glass.

A live silhouette of the subject is rendered continuously as the background of every state — idle, thinking, and speaking — so the mirror always "sees" you. An optional SK6812 RGBWW LED strip around the frame breathes and shifts colour to follow the person. A 56 mm thermal receipt printer can hand out a physical keepsake. A long-press activates **photobooth mode**: three posed shots → AI pose directions → composited strip with a QR code → print + Drive upload.

---

## Hardware

| Part | Notes |
|---|---|
| Raspberry Pi 4 (2 GB+) | Tested on 4 GB |
| Adafruit RGB Matrix HAT (#2345) | Stack directly on the Pi |
| 6× HUB75E 64×64 panels | 2 wide × 3 tall portrait — total canvas **128 × 192 px** |
| 5 V / 40 A PSU | Direct to panels. Share **GND only** with the Pi |
| Pi Camera Module v3 (or v2) | |
| Capacitive touch sensor (e.g. TTP223) | `SIG` → GPIO 25, `VCC` → 3V3, `GND` → GND |
| SK6812 RGBWW strip (optional) | Data → GPIO 10 (SPI MOSI) via 330 Ω resistor |
| 56 mm ESC/POS thermal printer (optional) | USB, `0x0416:0x5011` default |

### Panel chain

Serpentine: HAT → top-left → top-right → middle-right → middle-left → bottom-left → bottom-right.
Default `PIXEL_MAPPER = "U-mapper"`. If the image is mirrored or split, try `"U-mapper;Rotate:180"` or `"V-mapper"`.
Confirm scan rate from the sticker — most 64×64 panels are **1/32** (`SCAN_RATE = 32`).

### LED strip — avoid the GPIO 18 conflict

The RGB Matrix HAT uses **GPIO 18 / PWM** for panel OE. `rpi_ws281x` defaults to the same pin.
Drive the strip over **SPI (GPIO 10 / MOSI)** instead — set in [`config.py`](config.py) as `LED_STRIP_PIN = 10`.

1. Enable SPI: `sudo raspi-config` → Interface Options → SPI → Enable
2. Pin SPI frequency in `/boot/firmware/config.txt`:
   ```
   core_freq=250
   core_freq_min=250
   ```
3. Reboot.

Strip wiring: **VCC** → panel PSU 5V · **GND** → common ground · **DI** → GPIO 10 via 330 Ω resistor (optionally via a 74AHCT125 level shifter for reliability).

---

## Install on the Pi

```bash
git clone <this repo> magic-mirror
cd magic-mirror
./install.sh
sudo reboot
sudo systemctl start magic-mirror.service
```

`install.sh`:
1. `apt`-installs build deps + `picamera2` + OpenCV.
2. Clones and builds [`rpi-rgb-led-matrix`](https://github.com/hzeller/rpi-rgb-led-matrix) Python bindings.
3. Installs pip requirements.
4. Copies `.env.example` → `.env` and prompts for `OPENAI_API_KEY`.
5. Disables onboard audio (`dtparam=audio=off`) — the audio PWM conflicts with the HUB75 clock pin.
6. Installs and enables a `systemd` service that auto-starts on boot.

---

## Running manually

```bash
# Real hardware:
python3 main.py

# Simulator on Mac/Linux (no Pi required):
python3 main.py --sim --no-api
```

---

## Simulator / pre-hardware testing

Run the full system on your laptop. A pygame window replaces the LED panels, your webcam (or a static JPEG) replaces the camera, and the keyboard replaces the physical button.

```bash
pip install -r requirements-dev.txt

# Full state machine, real OpenAI API:
python3 tests/test_full_sim.py --camera webcam

# Skip API calls (free, canned response):
python3 tests/test_full_sim.py --camera webcam --no-api

# No webcam:
python3 tests/test_full_sim.py --camera static
```

### Sim keyboard controls

| Key | Action |
|---|---|
| `SPACE` / `ENTER` | Short press (single fortune cycle) |
| Hold `SPACE` 2 s | Long press → photobooth mode |
| `Q` | Quit |
| `G` | Toggle panel boundary grid |

The window title bar shows the current state name.

### Individual test scripts

| Script | What it tests |
|---|---|
| `tests/test_ai.py [--image foo.jpg]` | One OpenAI vision call — prints response + token count |
| `tests/test_silhouette.py` | Live webcam silhouette preview + 128×192 mask. `S` saves snapshot |
| `tests/test_animations.py` | Starfield + ripple animation cycle in sim window |
| `tests/test_text.py` | Static text, scroll, multi-line, colour cycle |
| `tests/test_printer.py [--booth] [--show]` | Renders receipt or booth strip as PNG (no printer needed) |
| `tests/test_printer_live.py` | Sends a real print job if a printer is connected |
| `tests/test_full_sim.py` | Full state machine in sim mode |

---

## State machine

```
IDLE ──(short press)──► TRIGGERED ──(3-2-1)──► CAPTURING ──► AI_WAITING
                                                                    │
                                         FADE_OUT ◄── DISPLAYING ◄─┘
                                             │
                                           IDLE

IDLE ──(long press 2 s)──► BOOTH ──(per-shot: prompt → 3-2-1 → flash capture × 3)
                                ──► render strip + QR ──► print ──► display ──► FADE_OUT ──► IDLE
```

**LED strip modes per state:**

| State | Strip behaviour |
|---|---|
| Idle / displaying / fading | Warm white base + slow-drifting hue band that tracks the silhouette horizontally |
| Countdown (3-2-1) | Breathes in sync |
| Capture flash | Solid bright white (W channel) |
| AI thinking | Hue band pulses gently |

All I/O (camera, OpenAI, Drive uploads) runs off the display thread. Exceptions are caught and logged; the mirror returns to `IDLE` rather than crashing.

---

## Best-of-3 capture

On every shot (normal and booth), the camera grabs **3 frames in quick succession** and automatically keeps the sharpest one, measured by Laplacian variance. Console output:

```
[CAPTURE] burst 1/3 sharpness=312.4
[CAPTURE] burst 2/3 sharpness=489.1  ← winner
[CAPTURE] burst 3/3 sharpness=401.7
```

Tune in [`config.py`](config.py):
```python
CAPTURE_BURST_COUNT = 3         # frames per shot (1 = off)
CAPTURE_BURST_INTERVAL_MS = 80  # gap between bursts
```

---

## Photobooth mode

Long-press the touch sensor (≥ 2 s) from IDLE to start a photobooth session:

1. GPT is asked for 3 short, playful pose directions (falls back to `BOOTH_FALLBACK_PROMPTS` on API failure).
2. Each prompt is shown on the matrix for 2 s, followed by a 3-2-1 countdown.
3. The matrix + strip flash white as the camera grabs the best-of-3 frame.
4. A Drive subfolder is created for the session and shared as "anyone with link can view".
5. The three photos are uploaded to the subfolder; a composited strip PNG (photos + prompts + QR code pointing to the subfolder) goes to `GOOGLE_DRIVE_RECEIPTS_FOLDER_ID`.
6. The strip is printed on the thermal printer.
7. The strip is displayed on the matrix for a few seconds, then fades out.

---

## Thermal receipt printer

Optional 56 mm ESC/POS USB printer. Default IDs: `0x0416:0x5011`. Find yours with `lsusb`.

**Normal cycle** receipt:
```
      FORTUNAGASSE 24
     2026-05-12  19:04

    [portrait photo, 384 px wide, 3:4 aspect, Floyd-Steinberg dithered]

  YOUR EYES HOLD THE
   WEIGHT OF FORGOTTEN
        STARS
```

**Photobooth strip**: three photos stacked vertically, prompts alongside each, QR code at the bottom.

If the printer is unplugged or `python-escpos` isn't installed, the mirror logs `[PRINTER] not connected; skipping` and continues.

Tune in [`config.py`](config.py): `PRINTER_WIDTH_DOTS`, `PRINTER_IMAGE_ASPECT`, `PRINTER_HEADER`, `PRINTER_IMAGE_GAMMA`.

---

## Google Drive archive

Every cycle can archive the raw JPEG to `GOOGLE_DRIVE_FOLDER_ID` and the rendered receipt PNG to `GOOGLE_DRIVE_RECEIPTS_FOLDER_ID`. Both are optional and independent.

### One-time setup (OAuth — works on Workspace accounts)

1. [Google Cloud Console](https://console.cloud.google.com) → new project → enable **Google Drive API**.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → Desktop App → download JSON → save as `oauth_client.json` in the project root.
3. On your laptop (needs a browser):
   ```bash
   python3 tools/auth_drive.py
   ```
   Completes the OAuth flow and writes `token.json`. Copy both files to the Pi.
4. Create a Drive folder, open it, copy the folder ID from the URL, add to `.env`:
   ```env
   GOOGLE_DRIVE_FOLDER_ID=1abc...xyz
   GOOGLE_DRIVE_RECEIPTS_FOLDER_ID=1def...uvw   # optional
   ```

The uploader auto-refreshes the OAuth token on expiry. It also accepts a service-account JSON at `gcp-credentials.json` as a fallback (for personal Gmail accounts).

### End-of-night timelapse

After an event, build an MP4 from all photos taken that day and upload it back to Drive:

```bash
python3 tools/timelapse.py                    # today
python3 tools/timelapse.py --date 2025-07-04  # specific date
python3 tools/timelapse.py --min 1 --fps 2    # dev / low photo count
python3 tools/timelapse.py --out /tmp/tl.mp4 --no-upload --keep
```

Requires ≥ 10 photos by default — silently skips quiet nights. To run automatically at 4 AM:

```bash
# crontab -e
0 4 * * * cd /home/pi/magic-mirror && python3 tools/timelapse.py >> logs/timelapse.log 2>&1
```

---

## Google Drive auth — tools/auth_drive.py

```bash
python3 tools/auth_drive.py
```

Opens a browser OAuth flow once. Writes `token.json` which the mirror uses on every run (auto-refreshed).

---

## Configuration

Every tunable lives in [`config.py`](config.py) — no magic numbers elsewhere. Key sections:

| Section | Key constants |
|---|---|
| Panel hardware | `PANEL_ROWS/COLS`, `CHAIN_LENGTH`, `PIXEL_MAPPER`, `SCAN_RATE` |
| Camera | `FRAME_WIDTH/HEIGHT`, `LIVE_SILHOUETTE_FPS` |
| Capture | `CAPTURE_BURST_COUNT`, `CAPTURE_BURST_INTERVAL_MS` |
| AI | `AI_MODEL`, `AI_MAX_TOKENS`, `MIRROR_PERSONA` |
| Photobooth | `BOOTH_PHOTO_COUNT`, `BOOTH_PROMPT_HOLD_SEC`, `LONG_PRESS_MS` |
| Printer | `PRINTER_WIDTH_DOTS`, `PRINTER_IMAGE_GAMMA`, `PRINTER_HEADER` |
| LED strip | `LED_STRIP_COUNT`, `LED_STRIP_PIN`, `LED_STRIP_HUE_SPEED` |
| Display timing | `MESSAGE_SCROLL_SPEED`, `FADE_OUT_SEC`, `SILHOUETTE_DIM_FACTOR` |

---

## Usage log

Every API call appends `timestamp\ttokens_in\ttokens_out` to `usage.log`:

```bash
cat usage.log
```

---

## Project structure

```
magic-mirror/
├── main.py                  # State machine — entry point
├── config.py                # All constants (no magic numbers elsewhere)
├── ai_client.py             # OpenAI vision API + booth prompt generation
├── camera.py                # Pi Camera / background / silhouette extraction
├── led_matrix.py            # rpi-rgb-led-matrix wrapper
├── led_strip.py             # SK6812 RGBWW strip animation
├── gpio_button.py           # Capacitive touch + long-press detection
├── printer.py               # ESC/POS thermal printer + receipt/strip rendering
├── cloud_uploader.py        # Async Google Drive upload
├── display/
│   ├── animations.py        # Thinking dots, starfield, ripple
│   ├── silhouette.py        # Silhouette → PIL image
│   └── text_renderer.py     # Scroll + static text on PIL canvas
├── simulator/
│   ├── led_simulator.py     # pygame LED matrix + strip window
│   ├── camera_mock.py       # Webcam / static image camera stand-in
│   └── button_mock.py       # Keyboard short/long-press emulation
├── tools/
│   ├── auth_drive.py        # One-shot OAuth browser flow → token.json
│   └── timelapse.py         # End-of-night MP4 stitcher + Drive upload
├── tests/
│   ├── test_full_sim.py     # Full state machine in sim mode
│   ├── test_printer.py      # Receipt / booth strip PNG preview
│   ├── test_printer_live.py # Live printer test
│   ├── test_ai.py           # Single OpenAI vision call
│   ├── test_silhouette.py   # Live silhouette webcam preview
│   ├── test_animations.py   # Animation cycle
│   └── test_text.py         # Text rendering
├── assets/fonts/            # BDF bitmap fonts
├── requirements.txt         # Pi + Mac dependencies
├── requirements-dev.txt     # Simulator-only extras (pygame)
├── install.sh               # Pi setup script
└── .env.example             # Environment variable template
```
