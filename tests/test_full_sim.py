"""Full end-to-end sim run. Identical state machine, simulated hardware.

When --receipts is set (default), each cycle also drops a PNG preview of the
receipt that would have been printed into tests/sim_receipts/, named with the
cycle timestamp. Open the folder to flip through them while the sim runs.
"""
import argparse
import datetime
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import main as mirror_main
from tests.test_printer import render_preview


class SimPrinter:
    """Drop-in for ReceiptPrinter that writes a PNG preview per call."""

    def __init__(self, out_dir: str, show_each: bool = False):
        self.out_dir = out_dir
        self.show_each = show_each
        os.makedirs(out_dir, exist_ok=True)

    def print_receipt(self, frame, text):
        if frame is None:
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out = os.path.join(self.out_dir, f"receipt_{ts}.png")
        try:
            render_preview(frame.copy(), text, out)
            print(f"[SIM] receipt preview -> {out}")
            if self.show_each:
                try:
                    from PIL import Image
                    Image.open(out).show()
                except Exception as e:
                    print(f"[SIM] open viewer failed: {e}")
        except Exception as e:
            print(f"[SIM] receipt preview failed: {e}")

    def shutdown(self):
        pass


def run():
    p = argparse.ArgumentParser()
    p.add_argument("--camera", default="webcam", choices=["webcam", "static"])
    p.add_argument("--no-api", action="store_true")
    p.add_argument("--loop", type=int, default=0,
                   help="auto-press the button N times then exit")
    p.add_argument("--no-receipts", action="store_true",
                   help="disable per-cycle receipt preview PNGs")
    p.add_argument("--show-receipts", action="store_true",
                   help="auto-open each receipt PNG in the default viewer")
    args = p.parse_args()

    from simulator.led_simulator import LEDSimulator
    from simulator.camera_mock import CameraMock
    from simulator.button_mock import ButtonMock

    matrix = LEDSimulator()
    camera = CameraMock(mode=args.camera)
    import led_strip
    strip = led_strip.create_strip(sim_matrix=matrix)
    if args.no_receipts:
        import printer as printer_mod
        printer = printer_mod.create_printer()
    else:
        out_dir = os.path.join(os.path.dirname(__file__), "sim_receipts")
        printer = SimPrinter(out_dir, show_each=args.show_receipts)
        print(f"[SIM] receipt previews will be saved to {out_dir}")
    mirror = mirror_main.MagicMirror(matrix, camera, lambda cb: ButtonMock(cb),
                                     strip=strip, printer=printer,
                                     sim_mode=True, no_api=args.no_api)

    worker = threading.Thread(target=mirror.run, daemon=True)
    worker.start()

    auto_remaining = args.loop
    next_auto = time.monotonic() + 5.0 if auto_remaining > 0 else None

    import pygame
    clock = pygame.time.Clock()
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
            if next_auto is not None and time.monotonic() >= next_auto and auto_remaining > 0:
                mirror.button.trigger()
                auto_remaining -= 1
                next_auto = time.monotonic() + 15.0 if auto_remaining > 0 else None
                if auto_remaining == 0:
                    print("[SIM] --loop complete; will exit after current cycle")
            if auto_remaining == 0 and args.loop > 0 and mirror.state.name == "IDLE":
                # one final idle cycle then quit
                time.sleep(2.0)
                running = False
            matrix.tick()
            clock.tick(60)
    except KeyboardInterrupt:
        pass
    finally:
        mirror.shutdown()
        worker.join(timeout=2.0)


if __name__ == "__main__":
    run()
