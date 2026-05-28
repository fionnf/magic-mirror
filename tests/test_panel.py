"""Simple panel hardware test — fills the display with solid colours.

Usage:
    sudo python3 tests/test_panel.py                        # white → red → green → blue
    sudo python3 tests/test_panel.py --colour white         # hold white
    sudo python3 tests/test_panel.py --mapping regular      # try different HAT wiring
    sudo python3 tests/test_panel.py --multiplexing 1       # try stripe multiplexing
    sudo python3 tests/test_panel.py --row-addr-type 1      # try alternate row addressing

Common --mapping values:      adafruit-hat (default), regular, adafruit-hat-pwm
Common --multiplexing values: 0 (default), 1 (stripe), 2 (checker), 4 (z-stripe)
Common --row-addr-type:       0 (default), 1 (AB-addressed), 2 (direct), 3 (ABC-shift)
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
    args = p.parse_args()

    config.PANEL_ROWS    = args.rows
    config.PANEL_COLS    = args.cols
    config.CHAIN_LENGTH  = 1
    config.TOTAL_WIDTH   = args.cols
    config.TOTAL_HEIGHT  = args.rows
    config.PIXEL_MAPPER  = ""
    if args.mapping:
        config.HARDWARE_MAPPING = args.mapping

    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    opts = RGBMatrixOptions()
    opts.rows             = config.PANEL_ROWS
    opts.cols             = config.PANEL_COLS
    opts.chain_length     = 1
    opts.parallel         = 1
    opts.hardware_mapping = config.HARDWARE_MAPPING
    opts.gpio_slowdown    = config.GPIO_SLOWDOWN
    opts.brightness       = args.brightness
    opts.drop_privileges  = False
    opts.multiplexing     = args.multiplexing if args.multiplexing is not None else 0
    opts.row_address_type = args.row_addr_type if args.row_addr_type is not None else 0

    from rgbmatrix import RGBMatrix
    matrix = RGBMatrix(options=opts)
    canvas = matrix.CreateFrameCanvas()

    print(f"[TEST] mapping={config.HARDWARE_MAPPING}  multiplexing={opts.multiplexing}  row_addr_type={opts.row_address_type}")

    def draw_fill(colour):
        from PIL import Image
        img = Image.new("RGB", (args.cols, args.rows), colour)
        canvas.SetImage(img)
        matrix.SwapOnVSync(canvas)

    if args.colour:
        print(f"[TEST] solid {args.colour} — Ctrl-C to quit")
        draw_fill(COLOURS[args.colour])
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
            draw_fill(rgb)
            time.sleep(2)

    draw_fill((0, 0, 0))
    print("[TEST] done")


if __name__ == "__main__":
    run()

