"""Full end-to-end sim run. Identical state machine, simulated hardware."""
import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import main as mirror_main


def run():
    p = argparse.ArgumentParser()
    p.add_argument("--camera", default="webcam", choices=["webcam", "static"])
    p.add_argument("--no-api", action="store_true")
    p.add_argument("--loop", type=int, default=0,
                   help="auto-press the button N times then exit")
    args = p.parse_args()

    from simulator.led_simulator import LEDSimulator
    from simulator.camera_mock import CameraMock
    from simulator.button_mock import ButtonMock

    matrix = LEDSimulator()
    camera = CameraMock(mode=args.camera)
    import led_strip, printer as printer_mod
    strip = led_strip.create_strip(sim_matrix=matrix)
    printer = printer_mod.create_printer()
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
