#!/usr/bin/env python3
"""Numbered panel-setting tests on whatever the wall is showing as 'daily' (the current piece), to rate by eye.

Run ON THE PI with the wall stopped:
    sudo systemctl stop wall-control; sudo WALL_BRIGHTNESS=75 WALL_MAX_AMPS=35 python3 tools/piece_test.py [numbers...]; sudo systemctl start wall-control
Each test shows the piece for 15 s with its number in the top-left corner (big for the first 3 s, then small).
"""
import os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# number: (name, overrides)
TESTS = {
    1: ("current: 6 bits, slowdown 5, 125 Hz", {}),
    2: ("+ one hardware dither bit", {"MATRIX_PWM_DITHER_BITS": 1}),
    3: ("old: slowdown 7, 100 Hz", {"GPIO_SLOWDOWN": 7, "MATRIX_REFRESH_LIMIT_HZ": 100}),
    4: ("5 bits, slowdown 5, 125 Hz", {"MATRIX_PWM_BITS": 5}),
    5: ("current, brightness 60", {"_BRIGHT": 60}),
    6: ("current, 20 fps pieces (slower, steadier)", {"_FPS": 20}),
}


def one(n):
    import config
    name, ov = TESTS[n]
    for k, v in ov.items():
        if not k.startswith("_"):
            setattr(config, k, v)
    config.DEPTH_STEPS = []
    config.MATRIX_BRIGHTNESS = ov.get("_BRIGHT", int(os.environ.get("WALL_BRIGHTNESS", 75)))
    config.MATRIX_MAX_AMPS = float(os.environ.get("WALL_MAX_AMPS", 35))
    from PIL import ImageDraw
    from display import daily, houseslip
    from led_matrix import LedMatrix
    m = LedMatrix()
    fps = ov.get("_FPS", 31)
    ff = max(1, round(config.MATRIX_REFRESH_LIMIT_HZ / fps))
    big, small = houseslip._font(90), houseslip._font(26)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 15:
        e = time.monotonic() - t0
        img = daily.frame(e).convert("RGB")
        d = ImageDraw.Draw(img)
        if e < 3:
            d.text((96, 128), str(n), font=big, fill=(255, 255, 255), anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
        else:
            d.text((6, 4), str(n), font=small, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        m.draw(img, ff)
    print(f"test {n}: {name}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        one(int(sys.argv[2]))
    else:
        for n in ([int(a) for a in sys.argv[1:]] or sorted(TESTS)):
            subprocess.run([sys.executable, __file__, "--one", str(n)])
