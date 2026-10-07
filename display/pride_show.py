"""HOUSE FORTUNA — pride edition. A looping show for the LED wall.

frame(t) is a pure function of time t (seconds), so it previews offline and
plays live at any frame rate.

Scenes (s):
   0 -  6  disco ball drops in, rainbow beams sweep, glitter
   6 - 13  waving progress-pride flag, HOUSE / FORTUNA in moving pride stripes
  13 - 25  "people nearby" grid: one fictional profile per panel, pixel
           avatars, names, distances counting down, a message pops up,
           then the reveal: YOU, 0 m, closest match
  25 - 31  QR code to grindr.com
  31 - 37  rainbow vortex, SLAY / SERVE / GAY!! zoom out of it
  37 - 41  beating pride heart, WELCOME HOME, fade, loop
"""
import colorsys
import math
import random

import numpy as np
from PIL import Image, ImageDraw

import config
from display import text_renderer as tr

LOOP_SEC = 41.0
SCENES = [("disco", 0, 6), ("title", 6, 13), ("nearby", 13, 25),
          ("qr", 25, 31), ("vortex", 31, 37), ("heart", 37, 41)]
FADE = 0.35
QR_URL = "https://www.grindr.com"

PRIDE = np.array([(228, 3, 3), (255, 140, 0), (255, 237, 0),
                  (0, 160, 60), (36, 64, 220), (140, 41, 170)], np.uint8)
CHEVRON = [(255, 255, 255), (245, 169, 184), (91, 206, 250),
           (97, 57, 21), (0, 0, 0)]
YELLOW = (255, 205, 0)

_fonts, _masks, _cache = {}, {}, {}


# ----------------------------------------------------------------- helpers ---

def _font(size):
    size = max(6, int(size))
    if size not in _fonts:
        _fonts[size] = tr._load_font(size)
    return _fonts[size]


def _hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _bounce(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def _text(d, xy, s, size, fill, stroke=2, anchor=None):
    d.text(xy, s, font=_font(size), fill=fill, stroke_width=stroke,
           stroke_fill=(0, 0, 0), anchor=anchor)


def _fit(text, max_w, size):
    while size > 7 and _font(size).getlength(text) + 4 > max_w:
        size -= 1
    return size


def _text_masks(text, size, stroke=2):
    key = (text, size, stroke)
    if key not in _masks:
        f = _font(size)
        l, t, r, b = f.getbbox(text, stroke_width=stroke)
        w, h = r - l, b - t
        ms = Image.new("L", (w, h), 0)
        ImageDraw.Draw(ms).text((-l, -t), text, font=f, fill=255,
                                stroke_width=stroke, stroke_fill=255)
        mf = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mf).text((-l, -t), text, font=f, fill=255)
        _masks[key] = (ms, mf)
    return _masks[key]


def _pride_text(img, text, size, cx, y, t, shine=True):
    """Text filled with moving pride stripes + a chrome shine, black outline."""
    ms, mf = _text_masks(text, size)
    w, h = ms.size
    yy, xx = np.mgrid[0:h, 0:w]
    idx = np.floor(yy / max(h, 1) * 6 + xx * 0.035 - t * 1.6).astype(int) % 6
    grad = PRIDE[idx].astype(np.float32)
    if shine:
        pos = (t * 140) % (w + h + 60) - 30
        band = np.clip(1 - np.abs(xx + yy * 0.6 - pos) / 6.0, 0, 1)[..., None]
        grad = grad * (1 - band) + 255 * band
    x = int(cx - w / 2)
    img.paste((0, 0, 0), (x, int(y)), ms)
    img.paste(Image.fromarray(grad.astype(np.uint8)), (x, int(y)), mf)


def _sparkles(d, seed, n, box, size=3):
    x0, y0, x1, y1 = box
    rs = random.Random(seed)
    for _ in range(n):
        x, y = rs.uniform(x0, x1), rs.uniform(y0, y1)
        c = _hsv(rs.random(), 0.25, 1.0)
        s = rs.choice([size - 1, size, size + 1])
        d.line([x - s, y, x + s, y], fill=c)
        d.line([x, y - s, x, y + s], fill=c)


def _grid(W, H):
    if (W, H) not in _cache:
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        _cache[(W, H)] = (x, y)
    return _cache[(W, H)]


# ------------------------------------------------------------------ scenes ---

def _disco(t, W, H):
    x, y = _grid(W, H)
    out = np.zeros((H, W, 3), np.float32)
    R = int(min(W, H) * 0.2)
    cx = W / 2
    cy = -R + (H * 0.32 + R) * _bounce(_clamp(t / 1.4))
    # rainbow beams: 6 evenly spaced, all in ONE pass (distance to nearest beam)
    sector = math.pi / 3
    rel = (np.arctan2(y - cy, x - cx) - t * 0.9) % (2 * math.pi)
    k = (rel / sector + 0.5).astype(int) % 6
    dd = np.abs(rel - np.round(rel / sector) * sector)
    beam = np.clip(1 - dd / 0.09, 0, 1) * (_clamp((t - 0.8) / 0.8) * 0.55)
    out += beam[..., None] * PRIDE[k].astype(np.float32)
    # glitter: a few hundred random points, not a full-frame random field
    rs = np.random.default_rng(int(t * 12))
    gx, gy = rs.integers(0, W, 160), rs.integers(0, H, 160)
    out[gy, gx] = 255
    # string
    out[: max(0, int(cy - R)), int(cx)] = 120
    # mirror ball, computed only inside its bounding square
    x0, x1 = int(max(0, cx - R)), int(min(W, cx + R + 1))
    y0, y1 = int(max(0, cy - R)), int(min(H, cy + R + 1))
    if x1 > x0 and y1 > y0:
        bx, by = x[y0:y1, x0:x1], y[y0:y1, x0:x1]
        dx, dy = (bx - cx) / R, (by - cy) / R
        d2 = dx * dx + dy * dy
        inside = d2 < 1
        dz = np.sqrt(np.clip(1 - d2, 0, 1))
        lat = np.arcsin(np.clip(dy, -1, 1))
        lon = np.arctan2(dx, dz + 1e-6) + t * 1.4
        ti, tj = np.floor(lat / (math.pi / 9)), np.floor(lon / (math.pi / 11))
        hsh = np.modf(np.abs(np.sin(ti * 12.9898 + tj * 78.233) * 43758.5453))[0]
        grout = ((np.modf(np.abs(lat / (math.pi / 9)))[0] < 0.14)
                 | (np.modf(np.abs(lon / (math.pi / 11)))[0] < 0.14))
        spec = np.clip(-0.4 * dx - 0.5 * dy + 0.77 * dz, 0, 1) ** 18
        shade = (0.25 + 0.55 * hsh * dz + 0.9 * spec) * np.where(grout, 0.35, 1.0)
        glint = (hsh > 0.93) & (np.sin(t * 9 + hsh * 60) > 0.55)
        tint = np.stack([0.85 + 0.15 * np.sin(lon * 2), 0.85 + 0.15 * np.sin(lon * 2 + 2),
                         0.9 + 0.1 * np.sin(lon * 2 + 4)], -1)
        ball = np.clip(shade, 0, 1.2)[..., None] * 220 * tint
        ball[glint] = 255
        region = out[y0:y1, x0:x1]
        region[inside] = ball[inside]
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
    if t > 2.6:
        d = ImageDraw.Draw(img)
        k = _clamp((t - 2.6) / 0.6)
        size = _fit("LET'S GO GIRLS", W - 6, 18)
        _text(d, (W / 2, H * 0.86 + (1 - _back(k)) * 30), "LET'S GO GIRLS", size,
              _hsv(t * 0.3, 0.4, 1.0), anchor="mm")
    return img


def _flag(t, W, H, dim=0.42):
    x, y = _grid(W, H)
    off = np.sin(x / 18.0 + t * 3.0) * 6 + np.sin(x / 7.0 - t * 2.0) * 1.5
    idx = np.clip(((y - off) / (H / 6)).astype(int), 0, 5)
    shade = 0.8 + 0.2 * np.sin(x / 18.0 + t * 3.0 + 1.2)
    out = PRIDE[idx].astype(np.float32) * shade[..., None] * dim
    # progress chevron on the left
    cw = W * 0.09
    for i, col in enumerate(CHEVRON):
        lim = cw * (len(CHEVRON) - i)
        m = (x + np.abs(y - H / 2) * 0.55) < lim + off * 0.3
        out[m] = np.array(col, np.float32) * (0.65 if col != (0, 0, 0) else 1)
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGB")


def _title(t, W, H):
    img = _flag(t, W, H)
    d = ImageDraw.Draw(img)
    size_w = _fit("WELCOME TO", W - 12, 18)
    _text(d, (W / 2, H * 0.12), "WELCOME TO", size_w, (255, 255, 255), anchor="mm")
    for word, y, start, side in (("HOUSE", H * 0.24, 0.3, -1), ("FORTUNA", H * 0.50, 0.8, 1)):
        k = _clamp((t - start) / 0.9)
        if k <= 0:
            continue
        size = _fit(word, W - 4, 44)
        cx = W / 2 + side * (1 - _back(k)) * W
        bob = 2 * math.sin(t * 3 + (side + 1))
        _pride_text(img, word, size, cx, y + bob, t)
    if t > 1.8:
        _sparkles(ImageDraw.Draw(img), int(t * 6), 10, (4, H * 0.2, W - 4, H * 0.85))
    d = ImageDraw.Draw(img)
    if t > 2.5:
        sz = _fit("est. with love", W - 20, 13)
        _text(d, (W / 2, H * 0.9), "est. with love", sz, (255, 230, 240), anchor="mm")
    return img


# ------------------------------------------------------- people nearby -----

PROFILES = [
    # name,      metres, hair,     hair colour,     skin,           shirt,          extra
    ("GymBoi",   42.0, "short",  (40, 30, 20),   (230, 180, 140), (220, 40, 40),  "tank"),
    ("Otter",    27.0, "curly",  (110, 70, 30),  (210, 160, 120), (40, 120, 200), "stubble"),
    ("BearHug",  61.0, "cap",    (60, 40, 25),   (225, 170, 130), (90, 60, 40),   "beard"),
    ("Twink",    14.0, "swoop",  (250, 220, 90), (245, 200, 170), (255, 120, 190), ""),
    ("???",       0.5, "hidden", (0, 0, 0),      (90, 90, 90),    (70, 70, 70),   ""),
    ("DragQ",    33.0, "wig",    (170, 60, 230), (240, 190, 160), (255, 40, 160), "drag"),
    ("Neighb",    9.0, "short",  (20, 20, 20),   (150, 100, 70),  (40, 170, 90),  "glasses"),
    ("Your Ex",   4.0, "short",  (90, 50, 20),   (230, 185, 150), (30, 30, 30),   "shades"),
    ("Fridge",    2.0, "fridge", (0, 0, 0),      (230, 230, 235), (0, 0, 0),      ""),
    ("Pup",      18.0, "pup",    (30, 30, 30),   (220, 175, 140), (20, 20, 20),   ""),
    ("Daddy",    55.0, "short",  (170, 170, 170), (225, 180, 145), (30, 60, 120), "beard"),
    ("Cutie",    21.0, "swoop",  (200, 60, 40),  (240, 200, 175), (120, 220, 200), ""),
]
YOU = ("YOU", 0.0, "crown", (250, 210, 60), (240, 195, 165), None, "you")


def _avatar(d, p, ox, oy, t):
    name, _, hair, hc, skin, shirt, extra = p
    if hair == "fridge":                                  # the fridge, obviously
        d.rounded_rectangle([ox + 12, oy + 2, ox + 36, oy + 42], 3, fill=skin,
                            outline=(160, 160, 170))
        d.line([ox + 12, oy + 16, ox + 36, oy + 16], fill=(160, 160, 170))
        d.rectangle([ox + 31, oy + 6, ox + 33, oy + 13], fill=(120, 120, 130))
        d.rectangle([ox + 31, oy + 20, ox + 33, oy + 32], fill=(120, 120, 130))
        return
    if hair == "hidden":                                  # mystery silhouette
        d.ellipse([ox + 13, oy + 6, ox + 35, oy + 30], fill=skin)
        d.rounded_rectangle([ox + 7, oy + 30, ox + 41, oy + 44], 8, fill=skin)
        _text(d, (ox + 24, oy + 18), "?", 16, (230, 230, 230), stroke=1, anchor="mm")
        return
    # shoulders / shirt
    sh = shirt if shirt else None
    if extra == "you":
        for i in range(6):                                # rainbow shirt
            d.rectangle([ox + 7, oy + 33 + i * 2, ox + 41, oy + 34 + i * 2],
                        fill=tuple(int(v) for v in PRIDE[i]))
    elif extra == "tank":
        d.rounded_rectangle([ox + 5, oy + 32, ox + 43, oy + 44], 6, fill=skin)
        d.rectangle([ox + 14, oy + 33, ox + 34, oy + 44], fill=sh)
    else:
        d.rounded_rectangle([ox + 6, oy + 32, ox + 42, oy + 44], 7, fill=sh)
    # head
    d.ellipse([ox + 13, oy + 7, ox + 35, oy + 33], fill=skin)
    # hair styles
    if hair == "short":
        d.chord([ox + 12, oy + 5, ox + 36, oy + 26], 180, 360, fill=hc)
    elif hair == "curly":
        for cx in range(ox + 14, ox + 36, 5):
            d.ellipse([cx - 4, oy + 4, cx + 4, oy + 13], fill=hc)
    elif hair == "cap":
        d.chord([ox + 12, oy + 4, ox + 36, oy + 24], 180, 360, fill=(200, 40, 40))
        d.rectangle([ox + 26, oy + 13, ox + 42, oy + 15], fill=(170, 30, 30))
    elif hair == "swoop":
        d.chord([ox + 11, oy + 4, ox + 37, oy + 26], 180, 360, fill=hc)
        d.polygon([(ox + 13, oy + 12), (ox + 30, oy + 8), (ox + 20, oy + 19)], fill=hc)
    elif hair == "wig":
        d.ellipse([ox + 6, oy + 1, ox + 42, oy + 26], fill=hc)
        d.rectangle([ox + 8, oy + 14, ox + 15, oy + 36], fill=hc)
        d.rectangle([ox + 33, oy + 14, ox + 40, oy + 36], fill=hc)
        d.ellipse([ox + 14, oy + 9, ox + 34, oy + 33], fill=skin)
    elif hair == "pup":
        d.ellipse([ox + 13, oy + 7, ox + 35, oy + 33], fill=(25, 25, 25))
        d.polygon([(ox + 13, oy + 12), (ox + 9, oy + 0), (ox + 19, oy + 7)], fill=(25, 25, 25))
        d.polygon([(ox + 35, oy + 12), (ox + 39, oy + 0), (ox + 29, oy + 7)], fill=(25, 25, 25))
        d.ellipse([ox + 18, oy + 21, ox + 30, oy + 32], fill=skin)
    elif hair == "crown":
        d.polygon([(ox + 13, oy + 11), (ox + 15, oy + 0), (ox + 19, oy + 7), (ox + 24, oy - 2),
                   (ox + 29, oy + 7), (ox + 33, oy + 0), (ox + 35, oy + 11)], fill=hc)
        tw = 0.5 + 0.5 * math.sin(t * 8)
        d.point((ox + 24, oy + 1), fill=(255, 255, int(200 + 55 * tw)))
    # face details
    if extra == "beard":
        d.chord([ox + 12, oy + 14, ox + 36, oy + 38], 0, 180, fill=hc)
    if extra == "stubble":
        for i in range(8):
            d.point((ox + 17 + i * 2, oy + 29 + (i % 2)), fill=hc)
    eye_y = oy + 19
    if extra == "shades":
        d.rectangle([ox + 15, eye_y - 2, ox + 33, eye_y + 2], fill=(10, 10, 10))
        d.line([ox + 16, eye_y - 1, ox + 19, eye_y - 1], fill=(120, 120, 140))
    else:
        d.rectangle([ox + 18, eye_y, ox + 19, eye_y + 1], fill=(20, 20, 30))
        d.rectangle([ox + 28, eye_y, ox + 29, eye_y + 1], fill=(20, 20, 30))
        if extra == "glasses":
            d.ellipse([ox + 15, eye_y - 3, ox + 22, eye_y + 4], outline=(30, 30, 30))
            d.ellipse([ox + 26, eye_y - 3, ox + 33, eye_y + 4], outline=(30, 30, 30))
        if extra == "drag":
            d.line([ox + 16, eye_y - 3, ox + 21, eye_y - 2], fill=(20, 20, 20))
            d.line([ox + 27, eye_y - 2, ox + 32, eye_y - 3], fill=(20, 20, 20))
            d.rectangle([ox + 16, eye_y - 2, ox + 21, eye_y - 1], fill=(80, 200, 255))
            d.rectangle([ox + 27, eye_y - 2, ox + 32, eye_y - 1], fill=(80, 200, 255))
            d.point((ox + 13, oy + 27), fill=(255, 215, 0))
            d.point((ox + 35, oy + 27), fill=(255, 215, 0))
    if extra == "you":
        d.ellipse([ox + 15, oy + 23, ox + 19, oy + 26], fill=(255, 140, 170))
        d.ellipse([ox + 29, oy + 23, ox + 33, oy + 26], fill=(255, 140, 170))
    mouth = (230, 30, 70) if extra == "drag" else (150, 50, 50)
    if extra == "shades":
        d.line([ox + 20, oy + 28, ox + 28, oy + 27], fill=mouth)        # unbothered
    else:
        d.arc([ox + 19, oy + 23, ox + 29, oy + 30], 15, 165, fill=mouth, width=2)


def _dist(m):
    return f"{m * 100:.0f} cm" if m < 1 else f"{m:.0f} m"


def _tile(p, u, t, dimmed=0.0, tapped=False):
    pw, ph = config.PANEL_COLS, config.PANEL_ROWS
    img = Image.new("RGB", (pw, ph), (18, 18, 22))
    d = ImageDraw.Draw(img)
    online = p[0] not in ("Fridge", "Your Ex") or int(t * 2) % 2 == 0
    d.rectangle([0, 0, pw - 1, ph - 1], outline=YELLOW if p[6] == "you" else (55, 55, 60))
    _avatar(d, p, (pw - 48) // 2, 3, t)
    name = p[0]
    _text(d, (3, ph - 20), name, _fit(name, pw - 6, 10), (255, 255, 255), stroke=1)
    if p[6] == "you":
        metres = 0.0
    else:
        metres = max(0.3 if p[0] == "???" else 1.0, p[1] * (1 - 0.55 * _clamp(u / 7.5)))
    if online:
        d.ellipse([3, ph - 7, 7, ph - 3], fill=(0, 220, 90))
    _text(d, (10, ph - 10), _dist(metres), 9, (200, 200, 210), stroke=1)
    if tapped:
        s = 1 + 0.25 * math.sin(t * 10)
        cx, cy = pw - 10, 9
        r = 4 * s
        d.ellipse([cx - r - 2, cy - r, cx, cy + r * 0.3], fill=(255, 60, 120))
        d.ellipse([cx - 1, cy - r, cx + r + 1, cy + r * 0.3], fill=(255, 60, 120))
        d.polygon([(cx - r - 2, cy - 0.5), (cx + r + 1, cy - 0.5), (cx, cy + r + 3)],
                  fill=(255, 60, 120))
    if dimmed > 0:
        a = np.asarray(img, np.float32) * (1 - 0.8 * dimmed)
        img = Image.fromarray(a.astype(np.uint8), "RGB")
    return img


def _nearby(u, t, W, H):
    pw, ph = config.PANEL_COLS, config.PANEL_ROWS
    cols, rows = W // pw, H // ph
    img = Image.new("RGB", (W, H), (0, 0, 0))
    centre = (cols // 2, rows // 2)
    reveal = _clamp((u - 8.0) / 0.8)
    tiles = [(c, r) for r in range(rows) for c in range(cols)]
    others = [p for p in PROFILES if p[0] != "???"]
    k = 0
    for i, (c, r) in enumerate(tiles):
        appear = _clamp((u - 0.12 * i) / 0.35)
        if appear <= 0:
            continue
        if (c, r) == centre:
            p = YOU if reveal >= 0.5 else PROFILES[4]
            dim = 0.0
        else:
            p = others[k % len(others)]
            k += 1
            dim = reveal
        tapped = p[0] == "Twink" and 3.0 < u < 7.5
        tile = _tile(p, u, t, dimmed=dim, tapped=tapped)
        if appear < 1:                                    # flip in
            h = max(1, int(ph * appear))
            tile = tile.resize((pw, h))
            img.paste(tile, (c * pw, r * ph + (ph - h) // 2))
        else:
            img.paste(tile, (c * pw, r * ph))
    d = ImageDraw.Draw(img)
    # banner
    if u < 2.4:
        a = 1 - _clamp((u - 1.9) / 0.5)
        y = H / 2
        d.rectangle([0, y - 13, W, y + 13], fill=tuple(int(v * a) for v in YELLOW))
        _text(d, (W / 2, y), "PEOPLE NEARBY", _fit("PEOPLE NEARBY", W - 8, 18),
              tuple(int(v * a) for v in (20, 20, 20)), stroke=0, anchor="mm")
    # incoming message
    if 4.6 < u < 7.6:
        k2 = _clamp((u - 4.6) / 0.4) - _clamp((u - 7.2) / 0.4)
        y = -24 + 30 * _back(_clamp(k2))
        d.rounded_rectangle([6, y, W - 6, y + 22], 6, fill=YELLOW, outline=(0, 0, 0))
        _text(d, (12, y + 11), "GymBoi: hey ;) u up?", _fit("GymBoi: hey ;) u up?", W - 26, 13),
              (15, 15, 15), stroke=0, anchor="lm")
    # reveal
    if reveal > 0:
        cx, cy = (centre[0] + 0.5) * pw, (centre[1] + 0.5) * ph
        rs = random.Random(5)
        for _ in range(26):                               # heart burst
            a = rs.random() * 6.283
            sp = 20 + rs.random() * 70
            rr = sp * _clamp((u - 8.4) / 2.0)
            if rr <= 1:
                continue
            x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
            col = tuple(int(v) for v in PRIDE[rs.randrange(6)])
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=col)
        if u > 8.6:
            ky = _back(_clamp((u - 8.6) / 0.5))
            d.rectangle([0, 2, W, 2 + 22 * ky], fill=YELLOW)
            _text(d, (W / 2, 2 + 11 * ky), "CLOSEST MATCH", _fit("CLOSEST MATCH", W - 8, 16),
                  (15, 15, 15), stroke=0, anchor="mm")
            _text(d, (W / 2, H - 12), "it's you, babe", _fit("it's you, babe", W - 8, 15),
                  (255, 120, 190), anchor="mm")
    return img


# ------------------------------------------------------------------- QR ---

def _qr_matrix():
    if "qr" not in _cache:
        import qrcode
        q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(QR_URL)
        q.make(fit=True)
        _cache["qr"] = np.array(q.get_matrix(), bool)
    return _cache["qr"]


def _qr(u, t, W, H):
    m = _qr_matrix()
    n = m.shape[0]
    scale = max(1, min(W - 8, H - 50) // n)
    size = n * scale
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    x0, y0 = (W - size) // 2, (H - size) // 2 + 3
    # glowing rainbow frame
    for i in range(3):
        d.rectangle([x0 - 3 + i, y0 - 3 + i, x0 + size + 2 - i, y0 + size + 2 - i],
                    outline=_hsv(t * 0.5 + i * 0.1, 0.7, 1.0))
    k = _clamp(u / 0.8)
    q = np.where(m, 0, 240).astype(np.uint8)                 # dark modules on light
    q = np.kron(q, np.ones((scale, scale), np.uint8))
    rows = int(size * k)                                     # wipe in from the top
    if rows > 0:
        block = np.repeat(q[:rows, :, None], 3, axis=2)
        img.paste(Image.fromarray(block, "RGB"), (x0, y0))
    _text(d, (W / 2, y0 - 13), "WHO'S NEARBY?", _fit("WHO'S NEARBY?", W - 8, 16), YELLOW,
          anchor="mm")
    _text(d, (W / 2, y0 + size + 13), "scan me, darling", _fit("scan me, darling", W - 8, 14),
          (255, 255, 255), anchor="mm")
    return img


# ---------------------------------------------------------------- vortex ---

def _vortex(u, t, W, H):
    x, y = _grid(W, H)
    dx, dy = x - W / 2, y - H / 2
    key = ("polar", W, H)
    if key not in _cache:
        _cache[key] = (np.arctan2(dy, dx), np.log(np.sqrt(dx * dx + dy * dy) + 1.0))
    th, lr = _cache[key]
    h = th / (2 * math.pi) * 2 + lr * 0.9 - t * 0.9
    spiral = 0.5 + 0.5 * np.sin(th * 6 + lr * 9 - t * 6)
    rgb = np.stack([0.5 + 0.5 * np.sin(2 * math.pi * h),
                    0.5 + 0.5 * np.sin(2 * math.pi * (h + 1 / 3)),
                    0.5 + 0.5 * np.sin(2 * math.pi * (h + 2 / 3))], -1)
    v = (0.35 + 0.65 * spiral) * np.clip(lr / 3.0, 0.15, 1.0)
    img = Image.fromarray((rgb * v[..., None] * 255).astype(np.uint8), "RGB")
    words = ["SLAY", "SERVE", "GAY!!"]
    i = min(len(words) - 1, int(u / 2))
    p = (u % 2) / 2
    size = int(10 + 50 * (p ** 1.4))
    word = words[i]
    size = min(size, _fit(word, W * 1.3, size))
    if p < 0.9 and size >= 8:
        _pride_text(img, word, size, W / 2, H / 2 - size * 0.55, t, shine=False)
    return img


# ----------------------------------------------------------------- heart ---

def _heart(u, t, W, H):
    x, y = _grid(W, H)
    beat = 1 + 0.08 * max(0.0, math.sin(t * 7)) ** 6 + 0.04 * math.sin(t * 7)
    s = min(W, H) * 0.30 * beat * _back(_clamp(u / 0.6))
    hx = (x - W / 2) / max(s, 1)
    hy = -(y - H * 0.52) / max(s, 1) + 0.25
    f = (hx * hx + hy * hy - 1) ** 3 - hx * hx * hy ** 3
    inside = f < 0
    stripe = np.clip(((y - (H * 0.52 - s * 1.2)) / (s * 2.2) * 6).astype(int), 0, 5)
    out = np.zeros((H, W, 3), np.uint8)
    out[inside] = PRIDE[stripe][inside]
    img = Image.fromarray(out, "RGB")
    d = ImageDraw.Draw(img)
    _sparkles(d, int(t * 5), 12, (4, 4, W - 4, H - 4))
    if u > 0.5:
        _text(d, (W / 2, H * 0.09), "WELCOME", _fit("WELCOME", W - 10, 26), (255, 255, 255),
              anchor="mm")
        _text(d, (W / 2, H * 0.92), "HOME", _fit("HOME", W - 10, 26), (255, 255, 255),
              anchor="mm")
    return img


# ------------------------------------------------------------------ main ---

def frame(t: float) -> Image.Image:
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    t = t % LOOP_SEC
    for name, a, b in SCENES:
        if a <= t < b:
            u = t - a
            if name == "disco":
                img = _disco(u, W, H)
            elif name == "title":
                img = _title(u, W, H)
            elif name == "nearby":
                img = _nearby(u, t, W, H)
            elif name == "qr":
                img = _qr(u, t, W, H)
            elif name == "vortex":
                img = _vortex(u, t, W, H)
            else:
                img = _heart(u, t, W, H)
            fade = min(_clamp(u / FADE), _clamp((b - t) / FADE))
            if name == "qr":                       # keep the QR fully bright
                fade = min(1.0, _clamp(u / FADE))
            if fade < 1:
                img = Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8),
                                      "RGB")
            return img
    return Image.new("RGB", (W, H))


def frames():
    import time
    t0 = time.monotonic()
    while True:
        yield frame(time.monotonic() - t0)
