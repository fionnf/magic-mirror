# Magic Mirror

Raspberry Pi-driven smart mirror: a camera + button trigger captures the person
standing in front of a one-way acrylic sheet, sends the image to Claude, and
renders the response as animated text on a 128×64 HUB75 LED matrix (2×2 P5
panels) hidden behind the glass.

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
4. Copy `.env.example` → `.env` and prompt for your `ANTHROPIC_API_KEY`.
5. Disable Pi onboard audio (`dtparam=audio=off`) — required, the audio PWM
   conflicts with the HUB75 clock pin.
6. Install and enable a `systemd` service that auto-starts on boot.

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

# Full end-to-end run, identical state machine, real Claude API:
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
| `tests/test_ai.py [--image foo.jpg]` | One Claude vision call, prints response + tokens. |
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
IDLE → TRIGGERED → CAPTURING → SILHOUETTE → AI_WAITING
                                            ↓
                              DISPLAYING ← (response or timeout)
                                            ↓
                                         FADE_OUT → IDLE
```

All I/O (camera, Claude API) runs off the display thread. Any exception in a
cycle is caught and logged; the mirror returns to `IDLE` rather than crashing.

## Configuration

Every tunable lives in [`config.py`](config.py) — no magic numbers elsewhere.
