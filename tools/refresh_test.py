#!/usr/bin/env python3
"""Numbered flicker / colour-depth tests for the LED wall, to rate by eye.

Run ON THE PI with the wall stopped:  sudo systemctl stop wall-control; sudo -E python3 tools/refresh_test.py [numbers...]; sudo systemctl start wall-control
Each test shows its big number for 3 s, then a bright flowing colour field (top), a mid-tone one (middle) and a dark one (bottom)
for 12 s, with a fixed PWM setting. Rate each number 1-5 for flicker (5 = none) and for colour depth (5 = smooth, no steps).
"""
import math, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("WALL_FIXED_DEPTH", "1")

# number: (pwm bits, refresh Hz, static dither levels, hardware dither bits, what it is)
TESTS = {
    1: (5, 110, 0, 0, "5 bits, 110 Hz (current for bright)"),
    2: (6, 100, 0, 0, "6 bits, 100 Hz"),
    3: (7, 100, 0, 0, "7 bits, up to 100 Hz (about 92)"),
    4: (8, 100, 0, 0, "8 bits (about 80 Hz)"),
    5: (5, 110, 2, 0, "5 bits, 110 Hz + fine dither 2"),
    6: (6, 100, 2, 0, "6 bits, 100 Hz + fine dither 2"),
    7: (5, 110, 0, 1, "5 bits, 110 Hz + hardware dither bit"),
    8: (6, 100, 0, 1, "6 bits, 100 Hz + hardware dither bit"),
    9: (5, 110, 0, 2, "5 bits, 110 Hz + 2 hardware dither bits"),
    10: (4, 120, 0, 1, "4 bits, 120 Hz + hardware dither bit"),
    11: (5, 110, 0, 1, "= 7 but at brightness 50 (power limiter idle?)"),
    12: (5, 110, 0, 1, "= 7 with the real 35 A budget"),
}
BRIGHT = {11: 50}


def field(w, h, t):
    import numpy as np
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    v = (np.sin(x / 31 + t * .35) + np.sin(y / 23 - t * .3) + np.sin((x + y) / 41 + t * .2)) / 3 * .5 + .5    # slow, smooth, 0..1
    img = np.zeros((h, w, 3), np.float32)
    top, mid = h // 3, 2 * h // 3
    hue = np.stack([v, 1 - v * .6, .5 + .5 * np.sin(v * 3 + t * .2)], -1)
    img[:top] = hue[:top] * 255                      # bright
    img[top:mid] = hue[top:mid] * 110                # mid-tone
    img[mid:] = hue[mid:] * 38                       # dark
    return img.clip(0, 255).astype(np.uint8)


def run(n):
    import config
    bits, hz, dith, hwd, name = TESTS[n]
    config.MATRIX_PWM_BITS, config.MATRIX_REFRESH_LIMIT_HZ = bits, hz
    config.MATRIX_PWM_DITHER_BITS, config.COLOUR_DITHER = hwd, dith
    config.MATRIX_BRIGHTNESS = BRIGHT.get(n, int(os.environ.get("WALL_BRIGHTNESS", 80)))
    config.MATRIX_MAX_AMPS = float(os.environ.get("WALL_MAX_AMPS", 35))
    from PIL import Image, ImageDraw, ImageFont
    from led_matrix import LedMatrix
    import numpy as np
    m = LedMatrix()
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    try:
        f = ImageFont.load_default(size=110)
    except TypeError:
        f = ImageFont.load_default()
    card = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(card)
    d.text((W // 2, H // 2), str(n), font=f, fill=(255, 255, 255), anchor="mm")
    ff = max(1, round(hz / 29))
    t0 = time.monotonic()
    while time.monotonic() - t0 < 3:
        m.draw(card, ff)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 12:
        m.draw(Image.fromarray(field(W, H, time.monotonic() - t0)), ff)
    print(f"test {n}: {name}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        run(int(sys.argv[2]))
    else:
        nums = [int(a) for a in sys.argv[1:]] or sorted(TESTS)
        for n in nums:
            subprocess.run([sys.executable, __file__, "--one", str(n)], check=False)
