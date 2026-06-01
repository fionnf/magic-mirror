#!/usr/bin/env python3
"""Minimal panel test — just fill with white.

Usage:
    sudo python3 tests/test_simple.py
    sudo python3 tests/test_simple.py adafruit-hat-pwm
    sudo python3 tests/test_simple.py regular
"""
import sys
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import time

mapping = sys.argv[1] if len(sys.argv) > 1 else "adafruit-hat"

opts = RGBMatrixOptions()
opts.rows = 64
opts.cols = 64
opts.chain_length = 1
opts.parallel = 1
opts.hardware_mapping = mapping
opts.gpio_slowdown = 4
opts.brightness = 50
opts.drop_privileges = False

print(f"[TEST] mapping={mapping}")

matrix = RGBMatrix(options=opts)
canvas = matrix.CreateFrameCanvas()

img = Image.new("RGB", (64, 64), (255, 255, 255))
canvas.SetImage(img)
matrix.SwapOnVSync(canvas)

print("[TEST] solid white — Ctrl-C to quit")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

canvas.SetImage(Image.new("RGB", (64, 64), (0, 0, 0)))
matrix.SwapOnVSync(canvas)
print("[TEST] done")
