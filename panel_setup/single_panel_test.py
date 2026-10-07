"""Simple panel hardware test — fills ONE panel (chain length 1) with solid colours.

Usage:
    sudo python3 panel_setup/single_panel_test.py                     # white → red → green → blue
    sudo python3 panel_setup/single_panel_test.py --colour white      # hold white
    sudo python3 panel_setup/single_panel_test.py --mapping regular   # try different HAT wiring
    sudo python3 panel_setup/single_panel_test.py --multiplexing 1    # try stripe multiplexing
    sudo python3 panel_setup/single_panel_test.py --row-addr-type 1   # try alternate row addressing
    sudo python3 panel_setup/single_panel_test.py --slowdown 4        # GPIO timing override

Goes through LedMatrix, so it uses config.py's panel type (FM6126A for the
FM6124 panels), PWM bits etc. — the same settings as the full wall.

Common --mapping values:      regular (this build), adafruit-hat, adafruit-hat-pwm
Common --multiplexing values: 0 (default), 1 (stripe), 2 (checker), 4 (z-stripe)
Common --row-addr-type:       0 (default), 1 (AB-addressed), 2 (direct), 3 (ABC-shift)
Common --slowdown values:     6 (this wall), 3-4 (single panel), 1 (Pi 5 — not supported)
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
    p.add_argument("--rows",          type=int, default=64)
    p.add_argument("--cols",          type=int, default=64)
    p.add_argument("--colour",        default=None, choices=list(COLOURS))
    p.add_argument("--brightness",    type=int, default=50)
    p.add_argument("--mapping",       default=None,
                   help="hardware_mapping override (e.g. regular, adafruit-hat)")
    p.add_argument("--multiplexing",  type=int, default=None,
                   help="multiplexing override (0=default, 1=stripe, 2=checker)")
    p.add_argument("--row-addr-type", type=int, default=None, dest="row_addr_type",
                   help="row address type (0=default, 1=AB-addressed, 2=direct, 3=ABC-shift)")
    p.add_argument("--slowdown",      type=int, default=None, help="GPIO slowdown override")
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
    config.PANEL_ROTATE = {}
    config.MATRIX_APPLY_PANEL_GAINS = False
    config.MATRIX_BRIGHTNESS = args.brightness
    if args.mapping:
        config.HARDWARE_MAPPING = args.mapping
    if args.multiplexing is not None:
        config.MATRIX_MULTIPLEXING = args.multiplexing
    if args.row_addr_type is not None:
        config.MATRIX_ROW_ADDRESS_TYPE = args.row_addr_type
    if args.slowdown is not None:
        config.GPIO_SLOWDOWN = args.slowdown

    from led_matrix import LedMatrix
    matrix = LedMatrix()
    print(f"[TEST] mapping={config.HARDWARE_MAPPING}  panel_type={config.MATRIX_PANEL_TYPE}  "
          f"multiplexing={config.MATRIX_MULTIPLEXING}  row_addr_type={config.MATRIX_ROW_ADDRESS_TYPE}  "
          f"slowdown={config.GPIO_SLOWDOWN}")

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
