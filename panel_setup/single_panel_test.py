"""Simple panel hardware test — fills the display with solid colours.

Usage:
    sudo python3 panel_setup/single_panel_test.py                    # white → red → green → blue
    sudo python3 panel_setup/single_panel_test.py --colour white     # hold white
    sudo python3 panel_setup/single_panel_test.py --mapping regular  # try different HAT wiring
    sudo python3 panel_setup/single_panel_test.py --multiplexing 1   # try stripe multiplexing

Common --mapping values: adafruit-hat (default), regular, adafruit-hat-pwm
Common --multiplexing values: 0 (default), 1 (stripe), 2 (checker), 4 (z-stripe)
"""
import argparse
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

COLOURS = {
    "white":   (255, 255, 255),
    "red":     (255, 0,   0),
    "green":   (0,   255, 0),
    "blue":    (0,   0,   255),
    "black":   (0,   0,   0),
}


def fill(matrix, colour, rows, cols):
    from PIL import Image
    img = Image.new("RGB", (cols, rows), colour)
    matrix.draw(img)


def run():
    p = argparse.ArgumentParser()
    p.add_argument("--rows",         type=int, default=64)
    p.add_argument("--cols",         type=int, default=64)
    p.add_argument("--colour",       default=None, choices=list(COLOURS))
    p.add_argument("--brightness",   type=int, default=50)
    p.add_argument("--mapping",      default=None,
                   help="hardware_mapping override (e.g. regular, adafruit-hat)")
    p.add_argument("--multiplexing", type=int, default=None,
                   help="multiplexing override (0=default, 1=stripe, 2=checker)")
    args = p.parse_args()

    config.PANEL_ROWS    = args.rows
    config.PANEL_COLS    = args.cols
    config.CHAIN_LENGTH  = 1
    config.TOTAL_WIDTH   = args.cols
    config.TOTAL_HEIGHT  = args.rows
    config.PIXEL_MAPPER  = ""
    config.PANELS_WIDE = 1
    config.PANELS_TALL = 1
    config.PANEL_CHAIN_ORDER = [(0, 0)]
    if args.mapping:
        config.HARDWARE_MAPPING = args.mapping

    from led_matrix import LedMatrix
    matrix = LedMatrix()
    if args.multiplexing is not None:
        matrix.matrix.multiplexing = args.multiplexing
    print(f"[TEST] mapping={config.HARDWARE_MAPPING}  multiplexing={args.multiplexing if args.multiplexing is not None else 0}")

    if args.colour:
        print(f"[TEST] solid {args.colour} — Ctrl-C to quit")
        fill(matrix, COLOURS[args.colour], args.rows, args.cols)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        for name, rgb in COLOURS.items():
            if name == "black":
                continue
            print(f"[TEST] {name}")
            fill(matrix, rgb, args.rows, args.cols)
            time.sleep(2)

    matrix.clear()
    print("[TEST] done")


if __name__ == "__main__":
    run()
