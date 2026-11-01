#!/usr/bin/env python3
"""Print one test slip: the same photo in several dither / resolution settings, each labelled with a letter, so you can
pick the best by eye (run it on the wall's Pi, or anywhere that can reach the printer).

    cd ~/magic-mirror && set -a && . ./.env && set +a      # WALL_PRINTER and PRINT_KEY from .env
    python3 tools/print_test_slip.py                        # the newest photo in photos/
    python3 tools/print_test_slip.py --photo some.jpg       # any picture
    python3 tools/print_test_slip.py --no-print             # only write tests/sim_receipts/test_slip.png

Then set the winner: PRINTER_DITHER (floyd | atkinson | bayer) and PRINTER_SCALE (1 = single dots, 2 = 2 x 2 blocks) in .env.
On the author's printer "B" won (single dots, Floyd-Steinberg), which is now the default. See docs/printing.md.
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import cv2  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import config  # noqa: E402
import print_out  # noqa: E402
import printer  # noqa: E402

VARIANTS = [   # label, scale (dots per pixel), dither, gamma (>1 = lighter)
    ("A  1x dots   Atkinson", 1, "atkinson", 1.0),
    ("B  1x dots   Floyd", 1, "floyd", 1.0),
    ("C  1x dots   Bayer pattern", 1, "bayer", 1.0),
    ("D  2x blocks Atkinson", 2, "atkinson", 1.0),
    ("E  2x blocks Bayer pattern", 2, "bayer", 1.0),
    ("F  1x Atkinson, lighter", 1, "atkinson", 1.35),
    ("G  1x Bayer, lighter", 1, "bayer", 1.35),
]


def font(size):
    for p in config.TEXT_FONT_PATHS + ["/System/Library/Fonts/Supplemental/Arial Bold.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photo", help="a picture to print (default: the newest receipt or booth photo in photos/)")
    ap.add_argument("--no-print", action="store_true", help="write the slip as a PNG instead of printing it")
    a = ap.parse_args()
    src = a.photo or (sorted(glob.glob(os.path.join(HERE, "photos", "receipt_*.jpg")) +
                             glob.glob(os.path.join(HERE, "photos", "strip_*_frame.jpg")), key=os.path.getmtime) or [None])[-1]
    if not src:
        sys.exit("no photo found: pass --photo")
    print("photo:", src)
    W = print_out.WIDTH
    photo = printer._preprocess(printer._crop_portrait(printer._frame_to_pil(cv2.imread(src)), W, int(W / config.PRINTER_IMAGE_ASPECT)))
    crop = photo.crop((0, 30, W, 330))                                  # face and shoulders, 384 x 300
    tiles, was = [], (print_out.SCALE, print_out.DITHER)
    for label, scale, dither, gamma in VARIANTS:
        print_out.SCALE, print_out.DITHER = scale, dither
        img = crop.point([min(255, int((v / 255.0) ** gamma * 255)) for v in range(256)]) if gamma != 1.0 else crop
        bw = print_out.to_1bit(img)
        tile = Image.new("1", (W, bw.height + 34), 1)
        tile.paste(bw, (0, 0))
        ImageDraw.Draw(tile).text((8, bw.height + 4), label, font=font(22), fill=0)
        tiles.append(tile)
    print_out.SCALE, print_out.DITHER = was
    sheet = Image.new("1", (W, sum(t.height for t in tiles) + 10), 1)
    y = 0
    for t in tiles:
        sheet.paste(t, (0, y))
        y += t.height
    print("slip: %d x %d dots (%.0f cm of paper)" % (sheet.width, sheet.height, sheet.height / 203 * 2.54))
    if a.no_print:
        out = os.path.join(HERE, "tests", "sim_receipts", "test_slip.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sheet.save(out)
        print("wrote", out)
    else:
        print_out.send(sheet)
        print("sent to", print_out.where())


if __name__ == "__main__":
    main()
