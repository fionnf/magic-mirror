"""Intro of the Ländle piece (display/laend.py): a long little film in German, ~106 s, played once when the
piece starts. frame(t) is a pure function of t (seconds since the start).

   0-  8   the sticker on a wall: "Nett hier. Fortunagasse 24. Aber warst du schon mal in Baden-Württemberg?"
   8- 19   dawn over the Remstal
  19- 40   Bittenfeld: Katha, Becky and Lennart pick apples on the Streuobstwiese
  40- 62   through the vineyards towards Korb
  62- 80   Korb: the Korber Kopf at sunset
  80-100   Schorndorf: half-timbered houses, fairy lights, Federweisser and onion tart
 100-106   night, a wave, and on to the map
"""
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
LENGTH = 120.0
SCENES = [("sticker", 0, 8.5), ("dawn", 8.5, 19), ("apples", 19, 40), ("vines", 40, 62),
          ("korb", 62, 80), ("schorndorf", 80, 100), ("night", 100, 106), ("feige", 106, 120)]
CAPTIONS = {
    "sticker": [],
    "dawn": [(0.8, "Das Ländle."), (5.0, "Ein goldener Herbsttag im Remstal.")],
    "apples": [(0.6, "In Bittenfeld hängen die Äpfel voll."),
               (7.0, "Katha pflückt, Becky fängt, Lennart schleppt die Kisten."),
               (12.0, "Becky trägt natürlich Salomon. Zum Äpfelpflücken."),
               (16.5, "Streuobstwiese: Herbstgold für alle!")],
    "vines": [(0.6, "Weiter geht's durch die Weinberge..."),
              (8.0, "...vorbei an Trauben, Trauben, Trauben."),
              (12.0, "Becky in Salomon: Gipfelsturm auf 300 Höhenmeter."),
              (15.5, "Nächste Station: Korb.")],
    "korb": [(0.6, "Auf dem Korber Kopf wird es golden."),
             (8.5, "Das ganze Remstal liegt uns zu Füßen.")],
    "schorndorf": [(0.6, "Abends in Schorndorf: Fachwerk und Lichterketten."),
                   (8.0, "Federweißer und Zwiebelkuchen..."),
                   (14.0, "Prost aufs Ländle!")],
    "night": [(0.5, "Auf geht's durchs Ländle!")],
    "feige": [(0.5, "Doch dann kam die Wanderfeige..."), (5.5, "...und eroberte das ganze Ländle."), (10.5, "Feigen für alle!")],
}
FADE = 0.5
HAIR = [(60, 36, 28), (236, 196, 96), (84, 52, 30)]
SKIN = [(240, 196, 166), (250, 214, 186), (214, 164, 132)]
TOP = [(214, 52, 56), (70, 130, 220), (66, 150, 84)]
LEGS = [(44, 48, 90), (60, 70, 110), (74, 60, 46)]
_fonts = {}
_FONT_FILES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
               "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]


def font(size):
    """A bold font that has ä ö ü ß (DejaVu on the wall, Arial on a Mac)."""
    size = max(6, int(size))
    if size not in _fonts:
        f = None
        for p in _FONT_FILES:
            if os.path.exists(p):
                try:
                    f = ImageFont.truetype(p, size)
                    break
                except Exception:
                    pass
        if f is None:
            from display import text_renderer as tr
            f = tr._load_font(size)
        _fonts[size] = f
    return _fonts[size]


def _c(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _ease(k):
    k = _c(k)
    return k * k * (3 - 2 * k)


def _sky(top, bottom, h=None, mid=None):
    h = h or H
    k = np.linspace(0, 1, h)[:, None, None]
    a, b = np.array(top, np.float32), np.array(bottom, np.float32)
    if mid is None:
        arr = a * (1 - k) + b * k
    else:
        m = np.array(mid, np.float32)
        arr = np.where(k < 0.5, a * (1 - k * 2) + m * k * 2, m * (2 - k * 2) + b * (k * 2 - 1))
    return Image.fromarray(np.repeat(arr, W, axis=1).astype(np.uint8), "RGB")


def _text(d, xy, s, size, fill, stroke=2, anchor="mm", sc=(0, 0, 0)):
    d.text(xy, s, font=font(size), fill=fill, stroke_width=stroke, stroke_fill=sc, anchor=anchor)


def _wrap(text, size, max_w):
    f = font(size)
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if f.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _caption(img, scene, u):
    cur = None
    for start, text in CAPTIONS.get(scene, []):
        if u >= start:
            cur = (start, text)
    if not cur:
        return
    start, text = cur
    size = 11
    lines = _wrap(text, size, W - 12)
    n = int((u - start) * 22) + 1
    shown, left = [], n
    for ln in lines:
        shown.append(ln[:max(0, left)])
        left -= len(ln) + 1
    lh = size + 4
    y0 = H - lh * len(lines) - 8
    arr = np.asarray(img, np.float32)
    arr[y0 - 5:] *= 0.30
    img.paste(Image.fromarray(arr.astype(np.uint8), "RGB"))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(shown):
        if ln:
            _text(d, (W / 2, y0 + i * lh + lh / 2), ln, size, (255, 244, 220), stroke=1)


# ------------------------------------------------------------------ people ---

def person(d, x, y, s, t, who, pose="stand", phase=0.0, item=None):
    """One of the three friends, feet at (x, y). who: 0 Katha (dark hair, red jacket), 1 Becky (blond ponytail,
    blue), 2 Lennart (cap, green). s = scale (1 ~ 30 px tall)."""
    def P(px, py):
        return (x + px * s, y + py * s)

    def line(a, b, col, w=2):
        d.line([P(*a), P(*b)], fill=col, width=max(1, int(round(w * s))))
    walk = math.sin(t * 8 + phase) if pose == "walk" else 0.0
    bob = abs(walk) * 0.9
    hy = -25 - bob
    hair, skin, top, leg = HAIR[who], SKIN[who], TOP[who], LEGS[who]
    if who == 0:
        d.rectangle([*P(-6, hy - 3), *P(6, hy + 11)], fill=hair)                       # long hair
    if who == 1:
        sw = math.sin(t * 4 + phase) * 2 + (walk * 2)
        d.polygon([P(5, hy - 2), P(9 + sw, hy + 3), P(8 + sw, hy + 12), P(6, hy + 4)], fill=hair)   # ponytail
    # legs
    if pose == "sit":
        line((-2, -9), (6, -8), leg, 3)
        line((6, -8), (6, 0), leg, 3)
    else:
        line((-2, -10 - bob), (-2 - 3 * walk, 0), leg, 3)
        line((2, -10 - bob), (2 + 3 * walk, 0), leg, 3)
        if who == 1:                                                              # Becky: chunky Salomon trail shoes
            for sx in (-3 - 3 * walk, 3 + 3 * walk):
                d.rectangle([*P(sx - 4, -4), *P(sx + 4, 1.5)], fill=(34, 36, 44))
                d.rectangle([*P(sx - 4, -1.5), *P(sx + 4, 0.5)], fill=(250, 120, 30))
                d.line([P(sx - 1, -4), P(sx + 2, -1.5)], fill=(236, 236, 240))
        else:
            d.rectangle([*P(-5 - 3 * walk, -1), *P(-1 - 3 * walk, 1)], fill=(36, 30, 34))
            d.rectangle([*P(1 + 3 * walk, -1), *P(5 + 3 * walk, 1)], fill=(36, 30, 34))
    # body
    if who == 1:
        d.polygon([P(-4, -19 - bob), P(4, -19 - bob), P(7, -9 - bob), P(-7, -9 - bob)], fill=top)       # dress
    else:
        d.rectangle([*P(-4, -19 - bob), *P(4, -9 - bob)], fill=top)
    # arms
    a = math.sin(t * 7 + phase)
    if pose == "reach":
        line((4, -18), (7 + a, -31 - abs(a) * 2), skin)
        line((-4, -18), (-7, -11), skin)
    elif pose == "catch":
        line((4, -17), (10, -13 + a), skin)
        line((-4, -17), (-10, -13 - a), skin)
    elif pose == "cheer":
        line((4, -18), (8, -31 - abs(a) * 3), skin)
        line((-4, -18), (-8, -31 - abs(a) * 3), skin)
    elif pose == "toast":
        line((4, -18), (11, -23 + a * 2), skin)
        line((-4, -18), (-6, -11), skin)
    elif pose == "carry":
        line((4, -17), (6, -10), skin)
        line((-4, -17), (-6, -10), skin)
    else:
        line((4, -17 - bob), (7 - 2 * walk, -10 - bob), skin)
        line((-4, -17 - bob), (-7 + 2 * walk, -10 - bob), skin)
    # head
    d.ellipse([*P(-5, hy - 5), *P(5, hy + 5)], fill=skin)
    if who == 2:
        d.chord([*P(-6, hy - 8), *P(6, hy + 2)], 180, 360, fill=(220, 190, 60))                           # cap
        d.rectangle([*P(0, hy - 2), *P(8, hy)], fill=(220, 190, 60))
        d.rectangle([*P(-5, hy + 3), *P(5, hy + 5)], fill=(120, 80, 54))                               # stubble
    else:
        d.chord([*P(-6, hy - 7), *P(6, hy + 3)], 180, 360, fill=hair)
    blink = (t + phase) % 3.1 < 0.12
    for ex in (-2.5, 2.5):
        if blink:
            d.line([P(ex - 1, hy + 1), P(ex + 1, hy + 1)], fill=(30, 20, 30))
        else:
            d.point(P(ex, hy + 1), fill=(30, 20, 30))
    d.line([P(-1.5, hy + 3.5), P(1.5, hy + 3.5)], fill=(150, 50, 60))
    if item == "basket":
        d.polygon([P(-12, -9), P(-3, -9), P(-4, -3), P(-11, -3)], fill=(150, 98, 48))
        d.line([P(-11, -9), P(-7.5, -14), P(-4, -9)], fill=(120, 76, 36))
    if item == "glass":
        gx, gy = 11, -24 + a * 2
        d.polygon([P(gx - 2, gy - 4), P(gx + 2, gy - 4), P(gx + 1, gy + 1), P(gx - 1, gy + 1)], fill=(246, 236, 150))
        d.line([P(gx, gy + 1), P(gx, gy + 4)], fill=(236, 236, 240))


def _apple(d, x, y, r=1.6, col=(214, 40, 44)):
    d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    d.point((x, y - r - 0.5), fill=(70, 120, 40))


def _tree(d, x, y, s, t, seed, apples=True, leafcol=(70, 140, 60)):
    d.rectangle([x - 2 * s, y - 28 * s, x + 2 * s, y], fill=(86, 58, 38))
    d.line([x, y - 22 * s, x - 9 * s, y - 34 * s], fill=(86, 58, 38), width=max(1, int(2 * s)))
    d.line([x, y - 20 * s, x + 10 * s, y - 33 * s], fill=(86, 58, 38), width=max(1, int(2 * s)))
    rs = random.Random(seed)
    for i in range(16):
        ox, oy = rs.uniform(-17, 17) * s, rs.uniform(-18, 6) * s
        r = rs.uniform(6, 10) * s
        sway = math.sin(t * 0.8 + i) * 0.6
        col = _mix(leafcol, (30, 90, 50), rs.random() * 0.6)
        d.ellipse([x + ox - r + sway, y - 40 * s + oy - r, x + ox + r + sway, y - 40 * s + oy + r], fill=col)
    if apples:
        for i in range(10):
            ox, oy = rs.uniform(-17, 17) * s, rs.uniform(-17, 5) * s
            _apple(d, x + ox, y - 40 * s + oy, 1.6 * s)


def _hills(d, base, amp, col, seed, step=2, stripes=None, drift=0.0):
    rs = random.Random(seed)
    ph = [rs.uniform(0, 6.28) for _ in range(3)]
    pts = [(0, H)]
    for x in range(0, W + step, step):
        y = base + amp * (math.sin(x / 38 + ph[0] + drift) * 0.55 + math.sin(x / 17 + ph[1]) * 0.25 + math.sin(x / 83 + ph[2]) * 0.6)
        pts.append((x, y))
    pts.append((W, H))
    d.polygon(pts, fill=col)
    if stripes:
        for i in range(1, 10):
            ln = [(x, y + i * 4.2) for x, y in pts[1:-1]]
            d.line(ln, fill=stripes, width=1)
    return pts


def _bird(d, x, y, t, col=(40, 36, 52)):
    f = math.sin(t * 9 + x) * 2.2
    d.line([(x - 4, y - f), (x, y), (x + 4, y - f)], fill=col)


def _church(d, x, base, h, col, win=None):
    d.rectangle([x - 5, base - h, x + 5, base], fill=col)
    d.polygon([(x - 6, base - h), (x, base - h - 15), (x + 6, base - h)], fill=col)
    d.rectangle([x - 14, base - h * 0.45, x - 5, base], fill=col)
    if win:
        d.rectangle([x - 1, base - h + 5, x + 1, base - h + 9], fill=win)


def _house(d, x, base, w, h, wall, roof, win=None):
    d.rectangle([x, base - h, x + w, base], fill=wall)
    d.polygon([(x - 2, base - h), (x + w / 2, base - h - w * 0.45), (x + w + 2, base - h)], fill=roof)
    if win:
        for wx in range(int(x + 3), int(x + w - 3), 6):
            d.rectangle([wx, base - h + 4, wx + 2, base - h + 7], fill=win)


# ------------------------------------------------------------------ scenes ---

def _sticker_face(u):
    """The sticker itself: sunny yellow, black type, a thick rounded rim."""
    sw, sh = 150, 190
    im = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sw - 1, sh - 1], 12, fill=(250, 250, 244))                       # white vinyl rim
    d.rounded_rectangle([4, 4, sw - 5, sh - 5], 9, fill=(255, 204, 0))
    lines = [(0.35, "Nett hier.", 30, 34), (1.9, "Fortunagasse 24.", 13, 62)]
    for start, s, size, y in lines:
        k = _ease((u - start) / 0.35)
        if k > 0:
            f = font(size)
            if f.getlength(s) > sw - 18:
                f = font(size - 1)
            d.text((sw / 2, y + (1 - k) * 8), s, font=f, fill=(20, 20, 20), anchor="mm")
    if u > 3.6:
        for i, ln in enumerate(_wrap("Aber warst du schon mal in", 14, sw - 14)):
            k = _ease((u - 3.6 - i * 0.2) / 0.3)
            if k > 0:
                d.text((sw / 2, 96 + i * 16 + (1 - k) * 8), ln, font=font(14), fill=(20, 20, 20), anchor="mm")
    if u > 5.0:
        k = _ease((u - 5.0) / 0.4)
        d.text((sw / 2, 138 + (1 - k) * 8), "Baden-", font=font(22), fill=(20, 20, 20), anchor="mm")
        d.text((sw / 2, 162 + (1 - k) * 8), "Württemberg?", font=font(17), fill=(20, 20, 20), anchor="mm")
    sh_ = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(sh_).rounded_rectangle([0, 0, sw - 1, sh - 1], 12, fill=255)
    return im


def _sticker(u, t):
    img = Image.new("RGB", (W, H), (38, 44, 56))
    d = ImageDraw.Draw(img)
    rs = random.Random(1)
    for row in range(0, H, 14):                                  # a dark brick wall
        off = 0 if (row // 14) % 2 == 0 else 12
        for x in range(-off, W, 24):
            v = rs.randint(-6, 8)
            d.rectangle([x + 1, row + 1, x + 23, row + 13], fill=(56 + v, 52 + v, 64 + v))
    for _ in range(30):                                          # graffiti dust
        d.point((rs.randrange(W), rs.randrange(H)), fill=(90, 96, 110))
    face = _sticker_face(u)
    ang = -4.0 + math.sin(t * 1.3) * 0.5
    zoom = 1.0 + (_ease((u - 7.0) / 1.5) * 2.4 if u > 7.0 else 0)
    pop = _ease(u / 0.5)
    sc = (0.4 + 0.6 * pop) * zoom
    big = face.resize((max(1, int(face.width * sc)), max(1, int(face.height * sc))), Image.BICUBIC).rotate(ang, expand=True, resample=Image.BICUBIC)
    sh_ = Image.new("RGBA", big.size, (0, 0, 0, 0))
    sh_.paste((0, 0, 0, 110), mask=big.split()[3])
    cx, cy = W // 2, H // 2 - 8
    img.paste(sh_, (cx - big.width // 2 + 3, cy - big.height // 2 + 4), sh_)
    img.paste(big, (cx - big.width // 2, cy - big.height // 2), big)
    if u > 5.8:
        _text(ImageDraw.Draw(img), (W / 2, H - 14), "Remstal · Ländle", 9, (255, 214, 120), stroke=1)
    return img


def _dawn(u, t):
    k = _c(u / 10)
    img = _sky(_mix((52, 36, 96), (110, 150, 226), k), _mix((255, 128, 110), (255, 226, 160), k), int(H * 0.7), mid=_mix((210, 90, 130), (190, 205, 240), k))
    full = Image.new("RGB", (W, H), (20, 16, 40))
    full.paste(img, (0, 0))
    d = ImageDraw.Draw(full)
    sy = H * 0.52 - 52 * _ease(u / 9)
    for r, a in ((26, 0.18), (18, 0.3), (11, 1.0)):
        col = _mix((255, 150, 90), (255, 236, 160), a) if r == 11 else _mix((255, 170, 120), (255, 210, 140), a)
        d.ellipse([W * 0.7 - r, sy - r, W * 0.7 + r, sy + r], fill=col)
    for i, (base, col, amp) in enumerate(((H * 0.5, _mix((120, 84, 130), (110, 150, 170), k), 10),
                                           (H * 0.58, _mix((90, 62, 110), (70, 128, 120), k), 12),
                                           (H * 0.67, _mix((64, 44, 88), (60, 118, 70), k), 14),
                                           (H * 0.78, _mix((40, 28, 66), (96, 130, 60), k), 16))):
        _hills(d, base, amp, col, 10 + i, stripes=_mix(col, (230, 170, 80), 0.35) if i >= 2 else None)
    _church(d, 52, int(H * 0.62), 22, (62, 44, 84), (255, 214, 120))
    mist = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    md = ImageDraw.Draw(mist)
    for i in range(7):
        x = (i * 37 + t * 4) % (W + 80) - 40
        md.ellipse([x - 40, H * 0.60 + i * 9, x + 40, H * 0.60 + i * 9 + 10], fill=(255, 220, 220, 50))
    full.paste(mist, (0, 0), mist)
    d = ImageDraw.Draw(full)
    for i in range(5):
        _bird(d, (i * 30 + t * 9) % (W + 30) - 10, 36 + i * 7 + math.sin(t + i) * 3, t + i)
    ts = _ease((u - 1.0) / 1.5) * (1 - _ease((u - 8.5) / 1.5))
    if ts > 0:
        _text(d, (W / 2, H * 0.2), "Ländle", int(18 + 14 * ts), _mix((255, 224, 150), (255, 250, 230), ts), stroke=2)
    return full


def _picker_scene_ground(d, base):
    d.rectangle([0, base, W, H], fill=(86, 142, 66))
    rs = random.Random(3)
    for _ in range(90):
        x, y = rs.randrange(W), rs.randrange(base, H)
        d.line([(x, y), (x + 1, y - 2)], fill=(120, 176, 80))


def _apples(u, t):
    img = _sky((126, 186, 244), (222, 238, 252), int(H * 0.62))
    full = Image.new("RGB", (W, H))
    full.paste(img, (0, 0))
    d = ImageDraw.Draw(full)
    _hills(d, H * 0.44, 8, (130, 168, 150), 4)
    _hills(d, H * 0.52, 10, (96, 156, 92), 5, stripes=(130, 180, 100))
    _house(d, 120, int(H * 0.54), 22, 12, (240, 220, 190), (190, 80, 60), (90, 110, 140))
    _church(d, 160, int(H * 0.55), 14, (210, 196, 180))
    base = int(H * 0.60)
    _picker_scene_ground(d, base)
    for i in range(4):                                       # clouds
        cx = (i * 60 + t * 3) % (W + 60) - 30
        d.ellipse([cx - 14, 20 + i * 14, cx + 14, 30 + i * 14], fill=(250, 250, 252))
        d.ellipse([cx - 4, 14 + i * 14, cx + 20, 28 + i * 14], fill=(250, 250, 252))
    _tree(d, 38, base + 46, 1.7, t, 1)
    _tree(d, 150, base + 38, 1.4, t, 2)
    # signpost
    d.rectangle([13, base + 48, 15, base + 72], fill=(110, 76, 44))
    d.rectangle([2, base + 34, 40, base + 46], fill=(236, 214, 160), outline=(110, 76, 44))
    _text(d, (21, base + 40), "BITTENFELD", 6, (60, 40, 20), stroke=0)
    # the three
    gy = 206
    for nx, nm in ((62, "Katha"), (100, "Becky"), (138, "Lennart")):
        _text(d, (nx, gy - 74), nm, 8, (255, 244, 200), stroke=1)
    person(d, 62, gy - 6, 1.9, t, 0, "reach" if (u % 3.0) < 2.2 else "stand", 0.0)
    person(d, 100, gy + 4, 2.0, t, 1, "catch", 1.7, item="basket")
    carry = u < 11 or u > 13
    person(d, 138, gy - 2, 1.9, t, 2, "carry" if carry else "walk", 2.9)
    # falling apples from the tree into Becky's basket
    n = 0
    for i in range(14):
        t0 = 1.0 + i * 1.35
        ph = (u - t0)
        if 0 <= ph < 1.1:
            x0, y0, x1, y1 = 66, base + 60, 90, gy - 14
            kx = ph / 1.1
            _apple(d, x0 + (x1 - x0) * kx, y0 + (y1 - y0) * kx * kx + math.sin(kx * 3) * 0, 2.2)
        if ph >= 1.1:
            n += 1
    d.rectangle([89, gy - 12, 98, gy - 8], fill=(150, 98, 48))
    for i in range(min(n, 9)):
        _apple(d, 91 + (i % 5) * 2, gy - 12 - (i // 5) * 2, 1.6)
    _text(d, (W - 28, 14), f"Äpfel: {n * 3}", 10, (255, 236, 180), stroke=1)
    # a few apples on the ground, a butterfly
    for i in range(6):
        _apple(d, 20 + i * 31 % 170, base + 70 + (i * 11) % 22, 1.8)
    bx = 20 + (t * 10) % 160
    by = base + 30 + math.sin(t * 2) * 8
    d.line([(bx - 2, by - math.sin(t * 20) * 2), (bx, by), (bx + 2, by - math.sin(t * 20) * 2)], fill=(250, 190, 40))
    return full


def _vines(u, t, people=True):
    img = _sky((110, 170, 240), (252, 226, 170), int(H * 0.5))
    full = Image.new("RGB", (W, H))
    full.paste(img, (0, 0))
    d = ImageDraw.Draw(full)
    sh = u * 4.0
    _hills(d, H * 0.36, 8, (146, 150, 190), 21, drift=sh * 0.01)
    _hills(d, H * 0.44, 10, (118, 150, 130), 22, drift=sh * 0.02)
    # the slope of vine rows: diagonal terraces with grapes
    top = int(H * 0.5)
    d.rectangle([0, top, W, H], fill=(104, 138, 66))
    for row in range(14):
        y = top + 4 + row * (6 + row * 1.1)
        sc = 0.5 + row * 0.12
        d.line([(0, y), (W, y)], fill=(70, 100, 50), width=max(1, int(1 + row * 0.12)))
        spacing = max(5, int(7 * sc * 1.8))
        off = (sh * (0.4 + row * 0.18)) % spacing
        for x in np.arange(-spacing, W + spacing, spacing):
            vx = x - off
            r = 2 + sc * 2.2
            d.ellipse([vx - r, y - r * 1.5, vx + r, y + r * 0.4], fill=(60 + row * 4, 120 + row * 4, 56))
            if (int(x / spacing) + row) % 3 == 0:
                for g in range(3):
                    d.ellipse([vx - 1 + g * 1.2 - 1, y - 1 + g * 0.6, vx + 1 + g * 1.2, y + 2 + g * 0.6], fill=(94, 40, 110) if row % 2 else (176, 214, 90))
    # the path they walk along
    py = int(H * 0.68)
    d.polygon([(0, py + 14), (W, py + 6), (W, py + 28), (0, py + 34)], fill=(206, 176, 132))
    for i in range(3 if people else 0):
        person(d, 150 - i * 34 + math.sin(t * 8 + i) * 0.5, py + 30 - i * 2, 1.9, t, i, "walk", i * 1.4)
    # a mile post and birds
    for i in range(6):
        _bird(d, (i * 40 + t * 12) % (W + 40) - 20, 24 + (i * 11) % 40 + math.sin(t + i) * 3, t + i)
    sunx = W * 0.2
    d.ellipse([sunx - 11, 18, sunx + 11, 40], fill=(255, 246, 190))
    if u > 14:
        k = _ease((u - 14) / 3)
        d.rectangle([W - 70 * k, py - 28, W - 70 * k + 26, py - 12], fill=(236, 214, 160), outline=(110, 76, 44))
        _text(d, (W - 70 * k + 13, py - 20), "KORB", 7, (60, 40, 20), stroke=0)
        d.rectangle([W - 70 * k + 12, py - 12, W - 70 * k + 14, py + 6], fill=(110, 76, 44))
    return full


def _korb(u, t):
    k = _c(u / 17)
    top, bot = _mix((90, 110, 190), (40, 30, 90), k), _mix((255, 190, 100), (255, 100, 90), k)
    img = _sky(top, bot, int(H * 0.62), mid=_mix((255, 160, 130), (230, 90, 120), k))
    full = Image.new("RGB", (W, H))
    full.paste(img, (0, 0))
    d = ImageDraw.Draw(full)
    sy = H * 0.34 + 30 * _ease(u / 17)
    for r, a in ((22, 0.25), (13, 1.0)):
        d.ellipse([W * 0.5 - r, sy - r, W * 0.5 + r, sy + r], fill=_mix((255, 140, 90), (255, 214, 120), a))
    for i in range(5):
        cx = (i * 50 - t * 2) % (W + 70) - 30
        d.ellipse([cx - 22, 30 + i * 9, cx + 22, 40 + i * 9], fill=_mix((255, 150, 130), (250, 190, 150), 0.4))
    cols = [_mix((160, 90, 120), (70, 50, 100), k), _mix((120, 70, 110), (50, 36, 86), k), _mix((84, 56, 96), (34, 26, 66), k)]
    _hills(d, H * 0.47, 8, cols[0], 31)
    _hills(d, H * 0.53, 10, cols[1], 32, stripes=_mix(cols[1], (240, 170, 80), 0.3))
    # the village of Korb below: houses and a church
    vb = int(H * 0.64)
    d.rectangle([0, vb - 4, W, H], fill=cols[2])
    _church(d, 70, vb, 20, (36, 28, 56), (255, 200, 100))
    for i, x in enumerate(range(8, 180, 15)):
        if abs(x - 70) > 18:
            _house(d, x, vb + (i % 2) * 2, 11, 8 + (i * 3) % 6, (46, 36, 66), (74, 40, 60), (255, 200, 100) if (u * 0.6 + i) % 4 > 1 else None)
    # the hill with the bench
    d.polygon([(0, H), (0, H * 0.78), (W * 0.35, H * 0.72), (W, H * 0.82), (W, H)], fill=(34, 40, 52))
    for i in range(14):
        x = i * 14 + 5
        d.line([(x, H * 0.75 + (i % 3) * 4 + 8), (x - 1, H * 0.75 + (i % 3) * 4 + 3)], fill=(70, 100, 60))
    d.rectangle([60, H * 0.78, 130, H * 0.78 + 3], fill=(96, 62, 36))                    # the bench
    d.rectangle([62, H * 0.78 + 3, 64, H * 0.78 + 10], fill=(96, 62, 36))
    d.rectangle([126, H * 0.78 + 3, 128, H * 0.78 + 10], fill=(96, 62, 36))
    d.rectangle([60, H * 0.78 - 8, 130, H * 0.78 - 6], fill=(96, 62, 36))
    by = int(H * 0.78 + 5)
    for i, x in enumerate((78, 97, 116)):
        person(d, x, by + 6, 1.8, t, i, "sit", i)
    d.rectangle([20, H * 0.78 - 26, 30, H * 0.78 - 6], fill=(60, 44, 36))
    d.rectangle([14, H * 0.78 - 32, 36, H * 0.78 - 26], fill=(236, 214, 160), outline=(90, 62, 36))
    _text(d, (25, H * 0.78 - 29), "KORB", 6, (60, 40, 20), stroke=0)
    for i in range(24):                                      # lights come on in the valley
        if u > 6 + i * 0.4:
            x, y = (i * 53) % 180 + 6, vb + 12 + (i * 7) % 30
            d.point((x, y), fill=(255, 210, 120))
    for i in range(3):
        _bird(d, (i * 55 + t * 8) % (W + 40) - 10, 30 + i * 10, t + i, col=(60, 36, 70))
    return full


def _fachwerk(d, x, base, w, h, wall, beam, roof, win=(255, 206, 120), lit=True):
    d.rectangle([x, base - h, x + w, base], fill=wall)
    d.polygon([(x - 2, base - h), (x + w / 2, base - h - w * 0.5), (x + w + 2, base - h)], fill=roof)
    for yy in range(int(base - h), int(base), 12):
        d.line([(x, yy), (x + w, yy)], fill=beam)
    for xx in (x, x + w / 2, x + w):
        d.line([(xx, base - h), (xx, base)], fill=beam)
    d.line([(x, base - h), (x + w / 2, base - h + 12)], fill=beam)
    d.line([(x + w, base - h), (x + w / 2, base - h + 12)], fill=beam)
    for yy in range(int(base - h + 4), int(base - 8), 12):
        for xx in (x + w * 0.2, x + w * 0.65):
            d.rectangle([xx, yy, xx + 4, yy + 5], fill=win if lit else (50, 56, 80))


def _schorndorf(u, t):
    k = _c(u / 8)
    img = _sky(_mix((60, 50, 120), (16, 20, 56), k), _mix((255, 130, 110), (90, 70, 130), k), int(H * 0.6))
    full = Image.new("RGB", (W, H), (30, 26, 44))
    full.paste(img, (0, 0))
    d = ImageDraw.Draw(full)
    rs = random.Random(6)
    for _ in range(26):
        x, y = rs.randrange(W), rs.randrange(int(H * 0.3))
        if k > 0.4:
            v = int(120 + 120 * (0.5 + 0.5 * math.sin(t * 2 + x)))
            d.point((x, y), fill=(v, v, min(255, v + 20)))
    base = int(H * 0.62)
    # the Stadtkirche behind
    d.rectangle([84, base - 74, 106, base], fill=(70, 58, 84))
    d.polygon([(82, base - 74), (95, base - 104), (108, base - 74)], fill=(96, 50, 64))
    d.rectangle([92, base - 66, 98, base - 54], fill=(255, 214, 130))
    d.ellipse([90, base - 50, 100, base - 40], fill=(240, 236, 220))
    # half-timbered houses either side of the Marktplatz
    walls = [(232, 214, 184), (206, 190, 150), (226, 196, 176)]
    for i, (x, w, h) in enumerate(((0, 40, 70), (38, 30, 58), (140, 28, 62), (166, 30, 78))):
        _fachwerk(d, x, base + 4, w, h, walls[i % 3], (82, 54, 40), (140, 62, 54))
    d.rectangle([0, base + 4, W, H], fill=(96, 88, 98))                          # cobbles
    for yy in range(base + 6, H, 7):
        for xx in range(((yy // 7) % 2) * 4, W, 8):
            d.rectangle([xx, yy, xx + 6, yy + 4], fill=(106 + (xx * 7 + yy) % 14, 98, 108))
    # fairy lights
    for i in range(3):
        pts = [(x, 28 + i * 14 + 12 * math.sin((x / W) * math.pi) + 3 * math.sin(x * 0.2)) for x in range(0, W + 4, 4)]
        d.line(pts, fill=(60, 50, 50))
        for j, (x, y) in enumerate(pts[::3]):
            on = (int(t * 2 + j + i) % 3) != 0
            d.ellipse([x - 1.5, y, x + 1.5, y + 3], fill=(255, 220, 130) if on else (190, 120, 70))
    # the table: onion tart and Federweisser
    ty = int(H * 0.73)
    d.rectangle([58, ty, 136, ty + 5], fill=(120, 80, 48))
    d.rectangle([62, ty + 5, 65, ty + 16], fill=(96, 62, 36))
    d.rectangle([128, ty + 5, 131, ty + 16], fill=(96, 62, 36))
    d.ellipse([70, ty - 5, 94, ty + 3], fill=(226, 184, 100))                           # Zwiebelkuchen
    d.ellipse([74, ty - 4, 90, ty], fill=(236, 206, 130))
    d.rectangle([108, ty - 16, 114, ty], fill=(236, 226, 150))                           # bottle
    d.rectangle([110, ty - 22, 112, ty - 16], fill=(236, 226, 150))
    d.rectangle([110, ty - 25, 112, ty - 22], fill=(60, 60, 70))
    toast = u > 14
    for i, x in enumerate((42, 98, 150)):
        person(d, x, ty + 19, 1.9, t, i, "cheer" if toast and i != 1 else "toast", i * 1.1, item="glass")
    if toast:
        for j in range(10):
            a = (t * 2 + j * 0.7) % 2.0
            sx = 96 + math.cos(j * 2.1) * (6 + a * 30)
            sy = ty - 52 - a * 14 + math.sin(j * 1.7) * 10
            d.line([(sx - 2, sy), (sx + 2, sy)], fill=(255, 240, 160))
            d.line([(sx, sy - 2), (sx, sy + 2)], fill=(255, 240, 160))
        pk = _ease((u - 14) / 0.6)
        _text(d, (W / 2, H * 0.3), "PROST!", int(10 + 18 * pk), (255, 232, 140), stroke=3)
    return full


def _night(u, t):
    img = _sky((6, 8, 30), (36, 30, 80), H)
    d = ImageDraw.Draw(img)
    rs = random.Random(12)
    for i in range(70):
        x, y = rs.randrange(W), rs.randrange(int(H * 0.8))
        v = int(110 + 130 * (0.5 + 0.5 * math.sin(t * (1 + rs.random()) + i)))
        d.point((x, y), fill=(v, v, min(255, v + 30)))
    d.ellipse([W * 0.7, 26, W * 0.7 + 22, 48], fill=(250, 246, 214))
    d.ellipse([W * 0.7 + 7, 23, W * 0.7 + 29, 45], fill=(10, 12, 38))
    _hills(d, H * 0.82, 6, (14, 14, 34), 41)
    for i, x in enumerate((64, 94, 124)):
        person(d, x, int(H * 0.8), 1.8, t, i, "cheer" if u > 1 else "stand", i)
    shoot = (t * 0.5) % 3.0
    if shoot < 0.5:
        x0 = 30 + shoot * 200
        d.line([(x0, 20 + shoot * 90), (x0 - 18, 14 + shoot * 90 - 20 * shoot)], fill=(255, 250, 220))
    return img


def _fig_leaf(d, x, y, r, ang, col, vein):
    """A lobed fig leaf: five fingers fanned from the stalk."""
    for i, a in enumerate((-1.1, -0.55, 0.0, 0.55, 1.1)):
        L = r * (1.0 if i in (1, 2, 3) else 0.75)
        ex, ey = x + math.cos(ang + a) * L, y + math.sin(ang + a) * L
        mx, my = (x + ex) / 2, (y + ey) / 2
        w = r * 0.36
        d.ellipse([mx - w, my - w, mx + w, my + w], fill=col)
        d.ellipse([ex - w * 0.8, ey - w * 0.8, ex + w * 0.8, ey + w * 0.8], fill=col)
        d.line([(x, y), (ex, ey)], fill=vein)


_tendrils = []


def _make_tendrils():
    rs = random.Random(77)
    starts = [(-6, H * 0.9), (W + 6, H * 0.85), (W * 0.5, H + 6), (-6, H * 0.45), (W + 6, H * 0.4),
              (W * 0.2, H + 6), (W * 0.8, H + 6), (-6, H * 0.7), (W + 6, H * 0.62), (W * 0.35, H * 0.35), (W * 0.7, H * 0.3)]
    for sx, sy in starts:
        pts = [(sx, sy)]
        ang = math.atan2(H * 0.55 - sy, W / 2 - sx) + rs.uniform(-0.5, 0.5)
        x, y = sx, sy
        for i in range(70):
            ang += rs.uniform(-0.35, 0.35)
            x, y = x + math.cos(ang) * 4.2, y + math.sin(ang) * 4.2
            pts.append((x, y))
        _tendrils.append(pts)


def _feige(u, t):
    img = _vines(11.0, 11.0, people=False)
    d = ImageDraw.Draw(img)
    if not _tendrils:
        _make_tendrils()
    g = _c(u / 11.0)
    for ti, pts in enumerate(_tendrils):
        n = int(len(pts) * _c(g * 1.25 - ti * 0.02))
        if n < 2:
            continue
        d.line(pts[:n], fill=(70, 74, 40), width=2)
        for i in range(2, n, 3):
            x, y = pts[i]
            age = (n - i) / 14.0
            r = 4 + 9 * _c(age) + 2 * math.sin(t * 1.5 + i)
            a = i * 1.3 + ti
            _fig_leaf(d, x, y, r, a + math.sin(t + i) * 0.1, (46 + (i * 7) % 30, 120 + (i * 11) % 40, 52), (28, 80, 40))
            if i % 9 == 0 and age > 0.6:                                                    # the figs themselves
                fx, fy = x + math.cos(a + 1.5) * 4, y + math.sin(a + 1.5) * 4 + 4
                d.ellipse([fx - 2.5, fy - 3, fx + 2.5, fy + 3], fill=(86, 36, 96))
                d.point((fx - 1, fy - 1), fill=(150, 90, 160))
    for i, x in enumerate((60, 98, 136)):
        person(d, x, 205, 1.9, t, i, "cheer" if u > 9 else "stand", i * 0.9)
        _fig = (86, 36, 96)
        d.ellipse([x + 9, 190, x + 15, 198], fill=_fig)
    if u > 8.5:
        k = _ease((u - 8.5) / 0.7)
        _text(d, (W / 2, H * 0.22), "WANDER-", int(8 + 14 * k), (240, 220, 255), stroke=3, sc=(40, 12, 56))
        _text(d, (W / 2, H * 0.22 + 14 + 10 * k), "FEIGE!", int(8 + 20 * k), (176, 110, 200), stroke=3, sc=(30, 10, 40))
    return img


SCENE_FN = {"sticker": _sticker, "dawn": _dawn, "apples": _apples, "vines": _vines, "korb": _korb,
            "schorndorf": _schorndorf, "night": _night, "feige": _feige}


def frame(t):
    t = max(0.0, min(t, LENGTH - 1e-3))
    for name, a, b in SCENES:
        if a <= t < b:
            u = t - a
            img = SCENE_FN[name](u, t)
            _caption(img, name, u)
            fade = min(_c(u / FADE), _c((b - t) / FADE)) if name != "sticker" else _c((b - t) / FADE)
            if name == "night":
                fade = min(fade, _c((b - t) / 0.8))
            if fade < 1:
                img = Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8), "RGB")
            return img
    return Image.new("RGB", (W, H))
