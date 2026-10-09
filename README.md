# House Fortuna wall

A 192 × 192 pixel LED art wall for a living room: nine 64 × 64 HUB75 panels driven by a
Raspberry Pi 4, controlled from a phone web app. It shows slow generative art, GPU shaders and
video loops, responds (subtly) to the music in the room, and can also act as a camera mirror
with AI one-liners and a receipt printer.

![front](hardware/led-wall-frame/images/01_front.png)

## What it does

| Mode | What you see |
|---|---|
| **Art** (Artsy, Shaders, Shapes, Light Art, Lava & Coral) | Slow galleries that cross-fade; pace set in the app ("Art pace") |
| **Music** | Art that follows the room's sound. The party slider goes from "art just breathes" to dance floor; pieces, video loops and shaders are curated per level; a beat tracker, Shazam song names, an optional Claude designer |
| **Mirror** | Camera silhouette, countdown photo, a Claude one-liner, aura reading, pixel selfie, printed receipt; people recognition is opt-in |
| **Shows & live** | Welcome / Pride / story animations, VBZ-style tram board for Rennweg |
| **Extras** | Smart Life lights (living-room group), guest dedications via QR, a tour that rotates through everything |

## Hardware

| Part | Notes |
|---|---|
| Raspberry Pi 4 | Pi 5 is not supported by the panel library |
| Adafruit RGB Matrix HAT | `hardware_mapping = "regular"` (not `adafruit-hat`) |
| 9 × 64 × 64 HUB75 panels (P4, 256 mm) | 3 × 3, one chain, FM6126A driver, row serpentine from the bottom left (see `config.py`) |
| 5 V / 40 A PSU | Software current limiter at 28 A |
| Camera Module 3 | Mirror mode |
| Logitech C270 (its microphone) | Music mode's mic (any USB mic works) |
| 58 mm ESC/POS USB printer *(optional)* | Receipts |

The printable frame (3D models, OpenSCAD sources, print list) is in
[`hardware/led-wall-frame`](hardware/led-wall-frame/README.md).

## Quick start

**On a laptop (no hardware):**
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
./panel_setup/sim.sh            # http://localhost:8080 - panels open in a window
```

**On a fresh Pi** (Raspberry Pi OS Lite 64-bit):
```bash
# laptop:
PI_USER=pi PI_HOST=<pi-ip> ./panel_setup/deploy.sh
scp .env pi@<pi-ip>:~/magic-mirror/.env
# pi:
cd ~/magic-mirror && ./panel_setup/bootstrap_pi.sh && sudo reboot
```
Then open `http://<pi-ip>/` on your phone. Details, tuning and troubleshooting:
[`panel_setup/README.md`](panel_setup/README.md).

## Configuration

`.env` (git-ignored; copy from `.env.example`):

| Variable | For |
|---|---|
| `ANTHROPIC_API_KEY` | All AI features (mirror lines, aura, booth prompts, wheel, music designer) - model `config.AI_MODEL` |
| `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_DRIVE_RECEIPTS_FOLDER_ID` | Optional photo archive (`tools/auth_drive.py` once) |

Panel layout, timing, brightness and the power budget live in `config.py`.
App settings (party level, art pace, palette, people, lights…) are stored as JSON under
`panel_setup/` on the Pi and never deployed over.

## Layout

```
config.py, led_matrix.py      panel layout + driver (remapping, power limiter)
main.py, api.py               mirror mode (state machine) and its internal API
ai_client.py                  Claude calls (vision one-liner, aura, booth prompts, JSON helper)
camera.py, vision.py, smartcrop.py, faces.py, moods.py   camera, silhouette, crop, recognition
printer.py, photo_store.py, cloud_uploader.py           receipts and photo archive
lights.py                     Smart Life (Tuya) local control
display/                      everything drawn on the wall
  art.py shapes.py light_art.py artsy.py organic.py     generative galleries
  shaders.py (+ assets/shaders/*.frag)                  GPU shaders (EGL on the Pi)
  loops.py (+ assets/loops, tools/make_loops.py)        video loops
  music.py beat.py intensity.py vj_fx.py                music engine
  departures.py welcome.py pride_show.py …              live boards and shows
panel_setup/                  wall_control.py (app server + process runner), web/ (the app),
                              play.py (runs one mode), deploy/bootstrap/sim scripts, README
simulator/                    pygame panel window, webcam/button mocks
hardware/led-wall-frame/      the printable frame
```
