"""Simple panel hardware test — fills the display with solid colours.

Usage:
    sudo python3 tests/test_panel.py          # white, then colour cycle
    sudo python3 tests/test_panel.py --colour red
    sudo python3 tests/test_panel.py --rows 64 --cols 64
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
    p.add_argument("--rows",    type=int, default=64)
    p.add_argument("--cols",    type=int, default=64)
    p.add_argument("--colour",  default=None, choices=list(COLOURS))
    p.add_argument("--brightness", type=int, default=50)
    args = p.parse_args()

    config.PANEL_ROWS    = args.rows
    config.PANEL_COLS    = args.cols
    config.CHAIN_LENGTH  = 1
    config.TOTAL_WIDTH   = args.cols
    config.TOTAL_HEIGHT  = args.rows
    config.PIXEL_MAPPER  = ""

    from led_matrix import LedMatrix
    matrix = LedMatrix()
    matrix.set_brightness(args.brightness)

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
