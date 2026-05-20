# Magic Mirror

A Raspberry Pi smart mirror: Pi Camera + capacitive touch button captures whoever stands in front of a one-way acrylic panel, sends the image to OpenAI (`gpt-4o-mini` vision), and scrolls the response on a **128 × 192** HUB75 LED matrix hidden behind the glass. A live silhouette renders continuously as the background. An SK6812 LED strip around the frame breathes and shifts colour. A thermal receipt printer hands out a keepsake. Long-press activates **photobooth mode**: three posed shots with AI-generated prompts, composited strip, and print.

---

- [Hardware](#hardware)
- [Install](#install)
- [Run](#run)
- [Dashboard](#dashboard)
- [Configuration](#configuration)
- [Google Drive](#google-drive)
- [Project structure](#project-structure)

---

## Hardware

| Part | Notes |
|---|---|
| Raspberry Pi 4 (2 GB+) | |
| Adafruit RGB Matrix HAT (#2345) | Stacks directly on the Pi |
| 6× HUB75E 64×64 panels | 2 wide × 3 tall — canvas **128 × 192 px** |
| 5 V / 40 A PSU | Direct to panels; share GND only with the Pi |
| Pi Camera Module v2/v3 | |
| Capacitive touch sensor (TTP223) | SIG → GPIO 25 |
| SK6812 RGBWW LED strip *(optional)* | Data → GPIO 10 (SPI MOSI) via 330 Ω |
| 56 mm ESC/POS USB printer *(optional)* | Default VID:PID `0x0416:0x5011` |

**Panel chain:** serpentine — HAT → top-left → top-right → middle-right → middle-left → bottom-left → bottom-right. Default `PIXEL_MAPPER = "U-mapper"`. Confirm scan rate from the panel sticker (most 64×64 are `1/32`).

**LED strip — avoid GPIO 18 conflict:** the Matrix HAT uses GPIO 18 for panel OE; drive the strip over SPI (GPIO 10) instead. Enable SPI with `sudo raspi-config`, then pin the clock in `/boot/firmware/config.txt`:
```
core_freq=250
core_freq_min=250
```

---

## Install

```bash
git clone <repo> magic-mirror && cd magic-mirror
./install.sh
sudo reboot
sudo systemctl start magic-mirror.service
```

`install.sh` installs apt + pip deps, builds the `rpi-rgb-led-matrix` Python bindings, copies `.env.example → .env` (prompts for your OpenAI key), disables onboard audio (conflicts with HUB75), and sets up a systemd service.

---

## Run

```bash
# On the Pi:
python3 main.py

# Laptop simulator (no hardware needed):
python3 tests/test_full_sim.py --camera webcam
python3 tests/test_full_sim.py --camera webcam --no-api   # skip OpenAI calls
python3 tests/test_full_sim.py --camera static            # no webcam
```

Simulator keys: `SPACE`/`ENTER` = short press · hold `SPACE` 2 s = long press (photobooth) · `Q` = quit · `G` = toggle grid.

---

## Dashboard

A web control panel and photo gallery are served by the mirror's Flask API (`http://<pi-ip>:5000`).

- **Control panel** (`/`) — live preview, trigger buttons, prompt editor, push text/image overlays
- **Photo gallery** (`/gallery`) — last 24 h photos, download, reprint

The gallery is also deployed to **GitHub Pages** (`https://fionnf.github.io/magic-mirror/photos.html`) as a shareable NFC tap target — program your NFC tag with that URL so flatmates can tap to browse photos without accessing the control panel.

To preview the dashboard on your laptop without a Pi:
```bash
pip install flask flask-cors
python3 preview_server.py        # serves on :5001
```

---

## Configuration

All tunables live in [`config.py`](config.py). Key sections:

| Section | Constants |
|---|---|
| Panel | `PANEL_ROWS/COLS`, `CHAIN_LENGTH`, `PIXEL_MAPPER`, `SCAN_RATE` |
| Camera | `FRAME_WIDTH/HEIGHT`, `LIVE_SILHOUETTE_FPS` |
| Capture | `CAPTURE_BURST_COUNT`, `CAPTURE_BURST_INTERVAL_MS` |
| AI | `AI_MODEL`, `MIRROR_PERSONA`, `AI_FALLBACK_MESSAGE` |
| Photobooth | `BOOTH_PHOTO_COUNT`, `BOOTH_PROMPT_HOLD_SEC`, `LONG_PRESS_MS` |
| Printer | `PRINTER_WIDTH_DOTS`, `PRINTER_IMAGE_GAMMA`, `PRINTER_HEADER` |
| LED strip | `LED_STRIP_COUNT`, `LED_STRIP_PIN`, `LED_STRIP_HUE_SPEED` |
| MQTT | `MQTT_HOST`, `MQTT_PORT`, `MQTT_WS_PORT` |

Environment variables (`.env`): `OPENAI_API_KEY`, `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_DRIVE_RECEIPTS_FOLDER_ID`.

---

## Google Drive

Every cycle archives the raw JPEG (and rendered receipt) to Drive. Setup:

1. Google Cloud Console → new project → enable Drive API → create OAuth Desktop App credential → save as `oauth_client.json`.
2. Run once on a machine with a browser: `python3 tools/auth_drive.py` → writes `token.json`. Copy both files to the Pi.
3. Add folder IDs to `.env`.

End-of-night timelapse (stitches day's photos into MP4, uploads to Drive):
```bash
python3 tools/timelapse.py
python3 tools/timelapse.py --date 2025-07-04
```

---

## Project structure

```
magic-mirror/
├── main.py              # State machine entry point
├── config.py            # All constants
├── ai_client.py         # OpenAI vision + booth prompt generation
├── camera.py            # Camera + silhouette extraction
├── led_matrix.py        # HUB75 matrix wrapper
├── led_strip.py         # SK6812 strip animation
├── gpio_button.py       # Touch sensor + long-press detection
├── printer.py           # ESC/POS receipt + strip rendering
├── cloud_uploader.py    # Async Google Drive upload
├── photo_store.py       # Local JPEG + JSON photo archive
├── api.py               # Flask REST API + gallery server
├── mqtt_bridge.py       # MQTT bridge (status, preview, commands)
├── preview_server.py    # Mock server for dashboard preview (no Pi needed)
├── display/
│   ├── animations.py    # Starfield, ripple, thinking dots
│   ├── silhouette.py    # Silhouette → PIL image
│   └── text_renderer.py # Scroll + static text
├── simulator/
│   ├── led_simulator.py # pygame LED + strip window
│   ├── camera_mock.py   # Webcam / static image stand-in
│   └── button_mock.py   # Keyboard press emulation
├── tools/
│   ├── auth_drive.py    # One-shot OAuth flow → token.json
│   └── timelapse.py     # End-of-night MP4 + Drive upload
├── tests/
│   ├── test_full_sim.py     # Full state machine sim
│   ├── test_printer.py      # Receipt/strip PNG preview
│   ├── test_printer_live.py # Live printer test
│   ├── test_ai.py           # Single vision API call
│   ├── test_silhouette.py   # Live silhouette preview
│   ├── test_animations.py   # Animation cycle
│   └── test_text.py         # Text rendering
├── dashboard/
│   ├── index.html       # Control panel
│   └── photos.html      # Public photo gallery (GitHub Pages / NFC)
├── requirements.txt
├── requirements-dev.txt
├── install.sh
└── .env.example
```
