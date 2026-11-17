# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"House Fortuna": a wall of 64x64 HUB75 LED panels (3 wide x 4 tall = 192x256 px, portrait) driven by a Raspberry Pi 4 and controlled from a phone web app. It shows generative art, GPU shaders, an AI-composed daily piece, live data boards, and a camera mirror/photobooth with a receipt printer. `README.md` is long and authoritative on features, env vars and wiring; `docs/` has per-feature pages.

## Commands

- Run on a laptop with no hardware (pygame simulator + web app at http://localhost:8080): `./panel_setup/sim.sh` (`PORT=8099` to change port). Install with `.venv/bin/pip install -r requirements-dev.txt`. Python 3.12/3.13.
- Tests live in `tests/` (e.g. `tests/test_64x64.py`, `tests/test_brief.py`); run with pytest from `requirements-dev.txt`, one file or test via `pytest tests/test_brief.py -k name`.
- Deploy code to the Pi: `PI_HOST=<ip> PI_USER=pi ./panel_setup/deploy.sh` (rsync; excludes secrets, photos, `assets/daily/`).
- Panel bring-up on the Pi (needs root/GPIO): `./panel_setup/run.sh numbers|walk|gradient|bar|text|anim|white`, `run.sh tune`, `run.sh monitor`. Tools in `panel_setup/` do not read `.env`; pass env vars on the command line.
- The simulator writes into `assets/daily/`; undo with `git checkout assets/daily && git clean -fd assets/daily`.

## Architecture

- `config.py` is the single source of hardware truth: panel size, `PANELS_WIDE/TALL` (`WALL_PANELS_TALL` env), the HUB75 wiring (`PORT_SLOTS`, `CHAIN_PER_PORT`, `PARALLEL`, `PANEL_CHAIN_ORDER`, `PANEL_ROTATE`), timing (`GPIO_SLOWDOWN`, PWM bits) and brightness tuning. Many comments record measured flicker/refresh tests; read them before changing timing.
- `led_matrix.py` is the driver. Art is drawn on a logical `TOTAL_WIDTH x TOTAL_HEIGHT` canvas; `_remap` reshapes it to each port's flat `CHAIN_PER_PORT*64 x 64` strip in software using `PANEL_CHAIN_ORDER`/`PANEL_ROTATE` (no library pixel mappers). Port slot `p` occupies rows `p*64...` of the buffer passed to the library. `PANEL_CHAIN_ORDER[k]` = wall `(col,row)` of the k-th panel in cable order, port after port.
- `panel_setup/` is the control service: `wall_control.py` (Flask API + mode/scene switching, started by the Pi), `web/index.html` (phone app), `play.py` (runs modes), `voice.py` (offline "Hey Fortuna" via Vosk), `sim.sh` (simulator). `main.py` is the camera mirror (started with `--no-touch` by the control service).
- `display/` holds every wall mode as a module (shaders, live boards such as planes/tides/trains/radar, shows, the daily art in `daily.py` + `assets/daily/`, `brief.py` for the Fortuna Brief). Shaders need `moderngl` and an OpenGL 3.3 context; without one they draw black.
- Other top-level modules: `ai_client.py`/`vision.py`/`moods.py` (AI features, fall back to built-in text without a key), `printer.py`/`print_out.py` (58 mm ESC/POS receipts), `lights.py`/`led_strip.py`/`mqtt_bridge.py` (room lights), `photo_store.py`/`cloud_uploader.py` (photos, gallery), `site/` and `docs/gallery.md` (public GitHub Pages gallery).

## Gotchas

- Wiring changes require updating `config.py` (ports/chains, `PANEL_CHAIN_ORDER`, `PANEL_ROTATE`) and verifying with the `numbers` pattern: each panel shows its chain index and an up arrow.
- `.env`, `token.json`, `oauth_client.json` hold secrets and are not deployed.
