"""Pixel selfie: a face-centred square cut from the photo, shrunk to a small grid and squeezed
into a handful of punchy colours - like a sprite of the person."""
import cv2
import numpy as np
from PIL import Image, ImageEnhance

import smartcrop

GRID = 48
COLOURS = 10


def square_around_face(frame_bgr):
    """Square crop centred on the biggest face (head and shoulders), else the centre."""
    h, w = frame_bgr.shape[:2]
    rows = smartcrop.find_face_rows(frame_bgr)
    if rows:
        r = max(rows, key=lambda r: r[2] * r[3])
        cx, cy, side = r[0] + r[2] / 2, r[1] + r[3] / 2 + r[3] * 0.3, max(r[2], r[3]) * 2.0
    else:
        cx, cy, side = w / 2, h / 2, min(w, h)
    side = min(side, w, h)
    x0 = int(max(0, min(w - side, cx - side / 2)))
    y0 = int(max(0, min(h - side, cy - side / 2)))
    s = int(side)
    return frame_bgr[y0:y0 + s, x0:x0 + s]


def pixelate(frame_bgr, grid=GRID, colours=COLOURS):
    """-> small PIL RGB image (grid x grid) in a reduced palette."""
    sq = square_around_face(frame_bgr)
    sq = cv2.resize(sq, (grid * 4, grid * 4), interpolation=cv2.INTER_AREA)
    sq = cv2.cvtColor(cv2.bilateralFilter(sq, 9, 40, 9), cv2.COLOR_BGR2RGB)   # calm the clutter, keep edges
    img = Image.fromarray(sq).resize((grid, grid), Image.BOX)
    img = ImageEnhance.Color(img).enhance(1.5)
    img = ImageEnhance.Contrast(img).enhance(1.25)
    return img.quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")


def to_wall(small, size):
    return small.resize((size, size), Image.NEAREST)


def sticker(small, px=300):
    """Chunky pixels, 1-bit dithered for the thermal printer."""
    return small.resize((px, px), Image.NEAREST).convert("L").convert("1")
