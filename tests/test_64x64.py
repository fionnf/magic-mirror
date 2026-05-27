"""Full state-machine test against a single 64×64 HUB75 panel.

On a Pi with the panel wired up this drives real hardware; on a laptop it
falls back to the pygame LED simulator at 64×64.  Camera and button are
always mocked so a keyboard/webcam is enough to run the full cycle.

Usage
-----
    # Laptop (pygame sim):
    python3 tests/test_64x64.py --camera webcam

    # Pi with real panel (no pygame window):
    python3 tests/test_64x64.py --camera webcam --hardware

Keyboard (sim mode): SPACE/ENTER = short press · hold SPACE 2 s = long press
                     Q = quit · G = toggle grid
"""
import argparse
import datetime
import os
import platform
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

# --- patch config BEFORE anything else imports it ---
import config
config.PANEL_ROWS    = 64
config.PANEL_COLS    = 64
config.CHAIN_LENGTH  = 1
config.TOTAL_WIDTH   = 64
config.TOTAL_HEIGHT  = 64
config.PIXEL_MAPPER  = ""

import main as mirror_main
from tests.test_full_sim import SimPrinter

_IS_PI = platform.machine() in ("armv7l", "aarch64")


def run():
    p = argparse.ArgumentParser()
    p.add_argument("--camera", default="static", choices=["webcam", "static"])
    p.add_argument("--hardware", action="store_true",
                   help="use real rpi-rgb-led-matrix instead of pygame sim "
                        "(auto-enabled on Pi)")
    p.add_argument("--no-api",   action="store_true")
    p.add_argument("--no-mqtt",  action="store_true")
    p.add_argument("--loop", type=int, default=0,
                   help="auto-press the button N times then exit")
    p.add_argument("--no-receipts", action="store_true")
    p.add_argument("--show-receipts", action="store_true")
    args = p.parse_args()

    use_hw = args.hardware or _IS_PI

    from simulator.camera_mock import CameraMock
    from simulator.button_mock import ButtonMock
    import led_strip
    import printer as printer_mod

    if use_hw:
        from led_matrix import LedMatrix
        matrix = LedMatrix()
        strip  = led_strip.create_strip()
        print("[64x64] real HUB75 panel + hardware strip")
    else:
        from simulator.led_simulator import LEDSimulator
        matrix = LEDSimulator()
        strip  = led_strip.create_strip(sim_matrix=matrix)
        print("[64x64] pygame sim at 64×64")

    camera = CameraMock(mode=args.camera)

    if args.no_receipts:
        printer = printer_mod.create_printer()
    else:
        out_dir = os.path.join(os.path.dirname(__file__), "sim_receipts")
        real = printer_mod.create_printer()
        if isinstance(real, printer_mod._NullPrinter):
            real = None
        else:
            try:
                from escpos.printer import Usb
                from escpos.exceptions import USBNotFoundError
                Usb(config.PRINTER_VENDOR_ID, config.PRINTER_PRODUCT_ID,
                    timeout=config.PRINTER_TIMEOUT_MS).close()
                print("[64x64] real printer detected")
            except Exception:
                real = None
        printer = SimPrinter(out_dir, show_each=args.show_receipts,
                             real_printer=real)

    mirror = mirror_main.MagicMirror(
        matrix, camera,
        lambda short, long_: ButtonMock(short, long_),
        strip=strip, printer=printer,
        sim_mode=not use_hw, no_api=args.no_api,
    )

    from api import MirrorAPI
    api = MirrorAPI(mirror, port=5000)
    api.start()

    if not args.no_mqtt:
        from mqtt_bridge import MQTTBridge
        MQTTBridge(mirror, host=config.MQTT_HOST, port=config.MQTT_PORT).start()

    print(f"[64x64] dashboard → http://localhost:{api.port}")

    worker = threading.Thread(target=mirror.run, daemon=True)
    worker.start()

    if use_hw:
        # No pygame window — just run until Ctrl-C or worker dies
        auto_remaining = args.loop
        next_auto = time.monotonic() + 5.0 if auto_remaining > 0 else None
        try:
            while worker.is_alive():
                if next_auto and time.monotonic() >= next_auto and auto_remaining > 0:
                    mirror.button.trigger()
                    auto_remaining -= 1
                    next_auto = time.monotonic() + 15.0 if auto_remaining > 0 else None
                if auto_remaining == 0 and args.loop > 0 and mirror.state.name == "IDLE":
                    time.sleep(2.0)
                    break
                time.sleep(0.05)
        except KeyboardInterrupt:
            pass
    else:
        import pygame
        clock = pygame.time.Clock()
        auto_remaining = args.loop
        next_auto = time.monotonic() + 5.0 if auto_remaining > 0 else None
        running = True
        try:
            while running and worker.is_alive():
                for event in matrix.pump_events():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_q:
                            running = False
                        elif event.key == pygame.K_g:
                            matrix.toggle_grid()
                        else:
                            mirror.button.handle_event(event)
                    elif event.type == pygame.KEYUP:
                        mirror.button.handle_event(event)
                if next_auto and time.monotonic() >= next_auto and auto_remaining > 0:
                    mirror.button.trigger()
                    auto_remaining -= 1
                    next_auto = time.monotonic() + 15.0 if auto_remaining > 0 else None
                if auto_remaining == 0 and args.loop > 0 and mirror.state.name == "IDLE":
                    time.sleep(2.0)
                    running = False
                matrix.tick()
                clock.tick(60)
        except KeyboardInterrupt:
            pass

    mirror.shutdown()
    worker.join(timeout=2.0)


if __name__ == "__main__":
    run()
