"""Display bring-up for the full 3x4 panel wall — no camera, button or API.

Usage:
    sudo python3 panel_setup/display_test.py                      # cycle all patterns
    sudo python3 panel_setup/display_test.py --pattern numbers    # hold one pattern
    python3 panel_setup/display_test.py --sim                     # laptop pygame sim

Patterns:
    walk      lights ONE panel at a time in chain order (0,1,2...), the rest
              stay black. Each shows a test graphic: corner dots (TL red, TR
              green, BL blue, BR white), crosshair, border and its index.
              Safest first test. --panel K holds a single panel, --walk-sec N
              sets seconds per panel.
    numbers   each panel gets a colour + its CHAIN INDEX + an up-arrow. Use this
              to verify PANEL_CHAIN_ORDER / PANEL_ROTATE: indices must read
              0,1,2... along your physical cable path and arrows must point up.
    gradient  full-wall RGB gradients (checks colour channels + dead pixels)
    bar       moving vertical bar (shows flicker / tearing / refresh problems)
    text      static text through the project's text renderer
    anim      starfield then ripple animations
    white     solid white at the configured brightness (check PSU / brightness)

A live "[PI]" line prints every 2 s (CPU, temp, throttling/undervoltage, fps,
draw time, estimated amps) and is logged to panel_setup/monitor.csv.
--no-monitor disables it. Standalone: python3 panel_setup/monitor.py

Tuning overrides (default from config.py): --brightness --pwm-bits --lsb-ns
    --slowdown --refresh-limit --multiplexing --mapping --row-address
"""
import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config
from panel_setup.monitor import PiMonitor

PATTERNS = ["walk", "numbers", "gradient", "bar", "text", "anim", "white"]
HOLD_SEC = 6.0


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def pat_numbers():
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    pw, ph = config.PANEL_COLS, config.PANEL_ROWS
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    big, small = _font(30), _font(12)
    for k, (col, row) in enumerate(config.PANEL_CHAIN_ORDER):
        x0, y0 = col * pw, row * ph
        hue = k / len(config.PANEL_CHAIN_ORDER)
        rgb = tuple(int(255 * c) for c in _hsv(hue, 1.0, 0.35))
        d.rectangle([x0, y0, x0 + pw - 1, y0 + ph - 1], fill=rgb,
                    outline=(255, 255, 255))
        label = str(k)
        d.text((x0 + pw // 2, y0 + ph // 2 + 4), label, fill=(255, 255, 255),
               font=big, anchor="mm")
        # up arrow in the top-left of the panel (as *displayed*)
        ax, ay = x0 + 8, y0 + 12
        d.polygon([(ax, ay - 7), (ax - 5, ay), (ax + 5, ay)], fill=(255, 255, 0))
        d.line([(ax, ay), (ax, ay + 6)], fill=(255, 255, 0))
        d.text((x0 + pw - 4, y0 + 4), "TOP", fill=(255, 255, 0), font=small,
               anchor="ra")
    return img


def _hsv(h, s, v):
    import colorsys
    return colorsys.hsv_to_rgb(h, s, v)


def pat_panel(k):
    """Full-wall black frame with only chain panel k drawn."""
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    pw, ph = config.PANEL_COLS, config.PANEL_ROWS
    img = Image.new("RGB", (W, H))
    col, row = config.PANEL_CHAIN_ORDER[k]
    x0, y0 = col * pw, row * ph
    tile = Image.new("RGB", (pw, ph))
    d = ImageDraw.Draw(tile)
    d.rectangle([0, 0, pw - 1, ph - 1], outline=(255, 255, 255))
    d.line([(0, 0), (pw - 1, ph - 1)], fill=(60, 60, 60))
    d.line([(0, ph - 1), (pw - 1, 0)], fill=(60, 60, 60))
    d.line([(pw // 2, 0), (pw // 2, ph - 1)], fill=(0, 90, 160))
    d.line([(0, ph // 2), (pw - 1, ph // 2)], fill=(0, 90, 160))
    for (x, y), c in (((2, 2), (255, 0, 0)), ((pw - 5, 2), (0, 255, 0)),
                      ((2, ph - 5), (0, 0, 255)), ((pw - 5, ph - 5), (255, 255, 255))):
        d.rectangle([x, y, x + 2, y + 2], fill=c)
    d.text((pw // 2, ph // 2), str(k), fill=(255, 200, 0), font=_font(26),
           anchor="mm")
    d.text((pw // 2, 8), "TOP", fill=(255, 255, 0), font=_font(9), anchor="mm")
    img.paste(tile, (x0, y0))
    return img


def pat_gradient(t=0.0):
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    x = np.linspace(0, 1, W)[None, :].repeat(H, 0)
    y = np.linspace(0, 1, H)[:, None].repeat(W, 1)
    r = x
    g = y
    b = 0.5 + 0.5 * np.sin((x + y) * 6 + t)
    arr = (np.stack([r, g, b], -1) * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def pat_bar(t):
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    x = int((t * 60) % W)
    d.rectangle([x, 0, x + 6, H - 1], fill=(255, 255, 255))
    y = int((t * 80) % H)
    d.rectangle([0, y, W - 1, y + 4], fill=(0, 160, 255))
    return img


def pat_text():
    from display import text_renderer
    img = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
    text_renderer.render_static_text(img, "HELLO MIRROR 192x256")
    return img


def pat_white():
    return Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT), (255, 255, 255))


def frames_for(name, panel=None, walk_sec=3.0):
    """Yield (image) frames for a pattern, forever."""
    t0 = time.monotonic()
    if name == "walk":
        n = len(config.PANEL_CHAIN_ORDER)
        frames = [pat_panel(k) for k in range(n)]
        last = -1
        while True:
            k = panel if panel is not None else int((time.monotonic() - t0) // walk_sec) % n
            if k != last:
                last = k
                print(f"[TEST] panel {k} of {n - 1} (chain order) -> "
                      f"logical col,row {config.PANEL_CHAIN_ORDER[k]}")
            yield frames[k]
    elif name == "numbers":
        img = pat_numbers()
        while True:
            yield img
    elif name == "text":
        img = pat_text()
        while True:
            yield img
    elif name == "white":
        img = pat_white()
        while True:
            yield img
    elif name == "gradient":
        while True:
            yield pat_gradient(time.monotonic() - t0)
    elif name == "bar":
        while True:
            yield pat_bar(time.monotonic() - t0)
    elif name == "anim":
        from display import animations
        a, b = animations.starfield(120), animations.ripple()
        while True:
            gen = a if ((time.monotonic() - t0) % 12) < 6 else b
            yield next(gen)
    else:
        raise SystemExit(f"unknown pattern {name}")


def run():
    p = argparse.ArgumentParser()
    p.add_argument("--pattern", choices=PATTERNS, default=None)
    p.add_argument("--panel", type=int, default=None,
                   help="walk: hold this chain index only")
    p.add_argument("--walk-sec", type=float, default=3.0)
    p.add_argument("--sim", action="store_true", help="pygame simulator")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--brightness", type=int)
    p.add_argument("--pwm-bits", type=int)
    p.add_argument("--lsb-ns", type=int)
    p.add_argument("--dither", type=int, help="pwm dither bits 0-2")
    p.add_argument("--slowdown", type=int)
    p.add_argument("--refresh-limit", type=int)
    p.add_argument("--multiplexing", type=int)
    p.add_argument("--row-address", type=int)
    p.add_argument("--mapping")
    p.add_argument("--panel-type", help="e.g. FM6126A, FM6127 ('' for none)")
    p.add_argument("--no-monitor", action="store_true",
                   help="disable the Pi health readout")
    p.add_argument("--log", default="panel_setup/monitor.csv",
                   help="CSV file for health stats ('' to disable)")
    p.add_argument("--show-refresh", action="store_true",
                   help="print the panel refresh rate (hardware only)")
    args = p.parse_args()

    for flag, attr in (("brightness", "MATRIX_BRIGHTNESS"),
                       ("pwm_bits", "MATRIX_PWM_BITS"),
                       ("lsb_ns", "MATRIX_PWM_LSB_NS"),
                       ("dither", "MATRIX_PWM_DITHER_BITS"),
                       ("slowdown", "GPIO_SLOWDOWN"),
                       ("refresh_limit", "MATRIX_REFRESH_LIMIT_HZ"),
                       ("multiplexing", "MATRIX_MULTIPLEXING"),
                       ("row_address", "MATRIX_ROW_ADDRESS_TYPE"),
                       ("mapping", "HARDWARE_MAPPING"),
                       ("panel_type", "MATRIX_PANEL_TYPE")):
        v = getattr(args, flag)
        if v is not None:
            setattr(config, attr, v)
    if args.show_refresh:
        config.MATRIX_SHOW_REFRESH = True

    if args.sim:
        from simulator.led_simulator import LEDSimulator
        matrix = LEDSimulator()
    else:
        from led_matrix import LedMatrix
        matrix = LedMatrix()
        print(f"[TEST] {config.TOTAL_WIDTH}x{config.TOTAL_HEIGHT}, chain "
              f"{config.CHAIN_LENGTH}, brightness {config.MATRIX_BRIGHTNESS}, "
              f"pwm_bits {config.MATRIX_PWM_BITS}, slowdown {config.GPIO_SLOWDOWN}")

    mon = None
    if not args.no_monitor:
        mon = PiMonitor(interval=2.0, log_path=args.log or None)
        mon.start()

    names = [args.pattern] if args.pattern else PATTERNS
    interval = 1.0 / args.fps
    quit_ = False
    try:
        while not quit_:
            for name in names:
                print(f"[TEST] pattern: {name}")
                hold = (len(config.PANEL_CHAIN_ORDER) * args.walk_sec
                        if name == "walk" else HOLD_SEC)
                end = time.monotonic() + hold if not args.pattern else None
                gen = frames_for(name, args.panel, args.walk_sec)
                while end is None or time.monotonic() < end:
                    t0 = time.monotonic()
                    td = time.monotonic()
                    matrix.draw(next(gen))
                    if mon:
                        mon.note_frame(time.monotonic() - td,
                                       getattr(matrix, "last_amps", 0.0))
                    if args.sim:
                        import pygame
                        for ev in matrix.pump_events():
                            if ev.type == pygame.QUIT or (
                                    ev.type == pygame.KEYDOWN and ev.key == pygame.K_q):
                                quit_ = True
                        matrix.tick()
                        if quit_:
                            break
                    time.sleep(max(0.0, interval - (time.monotonic() - t0)))
                if quit_:
                    break
            if args.pattern:
                break
    except KeyboardInterrupt:
        pass
    if mon:
        mon.stop()
    matrix.clear()
    print("[TEST] done")


if __name__ == "__main__":
    run()
