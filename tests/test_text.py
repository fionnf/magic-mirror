"""Text rendering tests in the LED simulator."""
import argparse
import os
import sys
import time
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from simulator.led_simulator import LEDSimulator
from display import text_renderer


def hold(matrix, image, seconds, poll):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if poll():
            return False
        matrix.draw(image)
        time.sleep(0.05)
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--message", default="The mirror sees all things hidden in plain sight.")
    args = p.parse_args()

    matrix = LEDSimulator()
    matrix.set_state_label("TEXT")
    import pygame
    quit_flag = {"q": False}

    def poll():
        for ev in matrix.pump_events():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_q):
                quit_flag["q"] = True
        return quit_flag["q"]

    while not quit_flag["q"]:
        # Static centred
        canvas = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        text_renderer.render_static_text(canvas, "Magic Mirror")
        if not hold(matrix, canvas, 2.0, poll):
            break

        # Scroll
        t0 = time.monotonic()
        px = 0
        for frame, finished in text_renderer.scroll_text_frames(args.message):
            if poll():
                break
            matrix.draw(frame)
            px += 1
            time.sleep(1.0 / config.IDLE_ANIMATION_FPS)
            if finished:
                break
        dt = time.monotonic() - t0
        print(f"[TEXT TEST] scroll completed in {dt:.2f}s "
              f"(target speed {config.MESSAGE_SCROLL_SPEED} px/s)")

        # Multi-word long string scroll
        long = "Reflections ripple through forgotten silences and distant winters."
        for frame, finished in text_renderer.scroll_text_frames(long):
            if poll():
                break
            matrix.draw(frame)
            time.sleep(1.0 / config.IDLE_ANIMATION_FPS)
            if finished:
                break

        # Colour cycle
        for colour in [(255, 60, 60), (60, 255, 100), (60, 120, 255), config.TEXT_COLOUR]:
            canvas = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
            text_renderer.render_static_text(canvas, "Mirror", colour=colour)
            if not hold(matrix, canvas, 1.0, poll):
                break

    matrix.shutdown()


if __name__ == "__main__":
    main()
