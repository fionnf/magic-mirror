"""Cycle through animations in the LED simulator."""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from simulator.led_simulator import LEDSimulator
from display import animations


def main():
    matrix = LEDSimulator()
    matrix.set_state_label("ANIMATIONS")
    names = list(animations.ANIMATIONS.keys())
    idx = 0
    interval = 1.0 / config.IDLE_ANIMATION_FPS
    duration = 10.0

    import pygame
    running = True
    while running:
        name = names[idx % len(names)]
        print(f"[ANIM TEST] showing: {name}")
        gen = animations.ANIMATIONS[name]()
        end = time.monotonic() + duration
        skip = False
        while time.monotonic() < end and running and not skip:
            for ev in matrix.pump_events():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_q):
                    running = False
                elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_n:
                    skip = True
                elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_g:
                    matrix.toggle_grid()
            matrix.draw(next(gen))
            time.sleep(interval)
        idx += 1
    matrix.shutdown()


if __name__ == "__main__":
    main()
