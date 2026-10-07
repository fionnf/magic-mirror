#!/usr/bin/env python3
"""Minimal panel test — fills with solid white.

Confirmed working: Pi 4B + P3 64x64 FM6124 panel + regular wiring
"""
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import time

opts = RGBMatrixOptions()
opts.rows = 64
opts.cols = 64
opts.chain_length = 1
opts.parallel = 1
opts.hardware_mapping = "regular"
opts.gpio_slowdown = 3
opts.panel_type = "FM6126A"
opts.pwm_bits = 7
opts.brightness = 50
opts.drop_privileges = False

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
