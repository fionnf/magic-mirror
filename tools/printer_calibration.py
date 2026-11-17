"""Printer calibration strips: the same test pattern printed under different settings, side by side on one slip, so you can pick by eye.

    python3 tools/printer_calibration.py density|heat|group|pause|dither|all  [photo.png]

Run it where the printer is plugged in (usb), or set WALL_PRINTER. Each strip is labelled with its settings
(ESC 7 n1,n2,n3 = heat group / heat time / pause; DC2 # d = density). "factory" sends no commands at all, which is what
the wall does today (PRINTER_QUALITY is off). Pick the best, then set PRINTER_QUALITY=1 PRINTER_HEAT=n1,n2,n3 PRINTER_DENSITY=d."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import print_out  # noqa: E402

W = print_out.WIDTH


def _font(size):
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def pattern(label, photo=None):
    """One strip: label, solid black, grey ramp, fine lines, 1-dot checkerboard, small text (and a photo patch if given)."""
    rows = []
    t = Image.new("L", (W, 30), 255)
    ImageDraw.Draw(t).text((4, 2), label, fill=0, font=_font(12))
    ImageDraw.Draw(t).line((0, 28, W, 28), fill=0)
    rows.append(t.convert("1"))
    rows.append(Image.new("1", (W, 22), 0))                                       # solid black: depth and evenness
    ramp = np.tile(np.linspace(255, 0, W, dtype=np.float32), (36, 1))             # white to black ramp (dithered)
    rows.append(Image.fromarray(ramp.astype(np.uint8)).convert("1"))
    fine = Image.new("L", (W, 30), 255)
    d = ImageDraw.Draw(fine)
    for x in range(0, W // 2, 2):                                                 # 1-dot lines, then 2-dot, then 3-dot
        d.line((x, 0, x, 29), fill=0)
    for x in range(W // 2, 3 * W // 4, 4):
        d.line((x, 0, x, 29), fill=0); d.line((x + 1, 0, x + 1, 29), fill=0)
    for x in range(3 * W // 4, W, 6):
        d.rectangle((x, 0, x + 2, 29), fill=0)
    rows.append(fine.convert("1", dither=Image.NONE))
    chk = (np.indices((24, W)).sum(axis=0) % 2 * 255).astype(np.uint8)            # 1-dot checkerboard: the worst case for bleed
    rows.append(Image.fromarray(chk).convert("1", dither=Image.NONE))
    txt = Image.new("L", (W, 44), 255)
    d = ImageDraw.Draw(txt)
    d.text((4, 2), "FORTUNAGASSE 24  0123456789", fill=0, font=_font(16))
    d.text((4, 24), "The quick brown fox jumps over", fill=0, font=_font(11))
    rows.append(txt.convert("1", dither=Image.NONE))
    if photo is not None:
        g = photo.convert("L").resize((W, 150))
        rows.append(print_out._dither(g))
    rows.append(Image.new("1", (W, 10), 1))
    out = Image.new("1", (W, sum(r.height for r in rows)), 1)
    y = 0
    for r in rows:
        out.paste(r, (0, y)); y += r.height
    return out


def run(sections, photo=None):
    """sections: [(label, heat or None, density or None)] - None = send nothing (factory)."""
    p = print_out._open(print_out.where())
    try:
        p._raw(b"\x1b\x40")
        for label, heat, dens in sections:
            p._raw(b"\x1b\x40")                                                   # reset, then this strip's settings only
            if heat:
                p._raw(b"\x1b\x37" + bytes(heat))
            if dens is not None:
                p._raw(b"\x12\x23" + bytes([dens]))
            p.image(pattern(label, photo), impl="bitImageRaster", high_density_vertical=True, high_density_horizontal=True,
                    fragment_height=256, center=False)
        p._raw(b"\x1b\x40")
        p._raw(b"\x1b\x4a" + bytes([print_out.FEED_DOTS]))
        p.cut(feed=False)
    finally:
        p.close()


H = (3, 170, 40)
SWEEPS = {
    "density": [("factory: no commands (what the wall does now)", None, None)]
               + [(f"density {d}  heat 3,170,40", H, d) for d in (6, 12, 18, 24, 31)],
    "heat": [(f"heat time {n2}  (3,{n2},40  density 15)", (3, n2, 40), 15) for n2 in (80, 120, 170, 220, 255)],
    "group": [(f"dots at once {n1 * 8}  ({n1},170,40  density 15)", (n1, 170, 40), 15) for n1 in (1, 2, 3, 5, 7)],
    "pause": [(f"pause {n3}  (3,170,{n3}  density 15)", (3, 170, n3), 15) for n3 in (0, 10, 40, 80, 160)],
}

if __name__ == "__main__":
    args = sys.argv[1:]
    which = args.pop(0) if args else "all"
    photo = Image.open(args[0]) if args else None
    names = list(SWEEPS) + ["dither"] if which == "all" else [which]
    for name in names:
        print("printing", name, flush=True)
        if name == "dither":
            ph = photo or Image.radial_gradient("L")
            for dth in ("floyd", "atkinson", "bayer"):                            # photo patch under each dither (factory settings)
                print_out.DITHER = dth
                run([(f"dither: {dth}  (factory settings)", None, None)], ph)
        else:
            run(SWEEPS[name], photo=None)
