"""Pi-side helper for colour calibration: holds one LedMatrix open and obeys
line commands on stdin, so the laptop can change colours without re-initialising
the panels each time. Started over SSH by calibrate_colour.py.

Commands (one per line; every command is answered with a line "ok"):
    fill R G B      full wall solid colour
    gains on|off    apply / bypass the calibration file
    reload          re-read the calibration file (and apply it)
    quit
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

import config
from led_matrix import LedMatrix


def main():
    matrix = LedMatrix()
    matrix.set_gains(None)                       # measure the raw panels first
    saved = matrix._luts
    print("ready", flush=True)
    try:
        for line in sys.stdin:
            parts = line.split()
            if not parts:
                continue
            cmd = parts[0]
            if cmd == "fill":
                r, g, b = (int(v) for v in parts[1:4])
                matrix.draw(Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT),
                                      (r, g, b)))
            elif cmd == "gains":
                if parts[1] == "on":
                    matrix._load_gains()
                else:
                    matrix.set_gains(None)
            elif cmd == "reload":
                matrix._load_gains()
            elif cmd == "quit":
                break
            print("ok", flush=True)
    finally:
        matrix.clear()


if __name__ == "__main__":
    main()
