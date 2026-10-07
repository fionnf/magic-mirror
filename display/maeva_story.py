"""Maeva in Zürich — a little animated story for the LED wall (~75 s loop).

frame(t) is a pure function of time t.

  0-10   morning: sunrise over the Alps, the lake, the Grossmünster
 10-22   the tram: Paradeplatz, Swiss station clock, tram on time to the second
 22-34   summer: floating down the Limmat in a swim ring, a swan follows
 34-45   Sprüngli: Luxemburgerli, "just one" (twelve)
 45-57   winter: sledging down the Uetliberg in the snow
 57-69   evening: city lights on the lake, home to House Fortuna
 69-75   THE END
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw

import config
from display import text_renderer as tr

LOOP_SEC = 75.0
SCENES = [("morning", 0, 10), ("tram", 10, 22), ("swim", 22, 34),
          ("spruengli", 34, 45), ("snow", 45, 57), ("home", 57, 69), ("end", 69, 75)]
CAPTIONS = {
    "morning": [(0.6, "This is Maeva."), (5.0, "She lives in Zürich, by the lake.")],
    "tram": [(0.5, "Every morning she takes the tram..."),
             (5.5, "...which arrives at exactly 8:00:00. Of course.")],
    "swim": [(0.5, "In summer she floats down the Limmat..."),
             (6.0, "...with her new best friend, Schwan.")],
    "spruengli": [(0.5, "Then: Luxemburgerli from Sprüngli."),
                  (5.5, "Just one. (She had twelve.)")],
    "snow": [(0.5, "Winter weekends: sledging down the Uetliberg!"),
             (6.5, "Wheeeeeee!")],
    "home": [(0.5, "At night the lake sparkles..."),
             (6.0, "...and she comes home to House Fortuna.")],
    "end": [],
}
FADE = 0.4

HAIR = (95, 55, 30)
SKIN = (245, 205, 175)
DRESS = (255, 105, 125)
_fonts = {}


# ---------------------------------------------------------------- helpers ---

def _font(size):
    size = max(6, int(size))
    if size not in _fonts:
        _fonts[size] = tr._load_font(size)
    return _fonts[size]


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _lerp(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _sky(W, H, top, bottom):
    k = np.linspace(0, 1, H)[:, None, None]
    a = np.array(top, np.float32)[None, None, :]
    b = np.array(bottom, np.float32)[None, None, :]
    arr = np.repeat(a * (1 - k) + b * k, W, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def _text(d, xy, s, size, fill, stroke=2, anchor=None):
    d.text(xy, s, font=_font(size), fill=fill, stroke_width=stroke,
           stroke_fill=(0, 0, 0), anchor=anchor)


def _wrap(text, size, max_w):
    f = _font(size)
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


def _caption(img, scene, u, W, H):
    caps = CAPTIONS.get(scene, [])
    cur = None
    for start, text in caps:
        if u >= start:
            cur = (start, text)
    if not cur:
        return
    start, text = cur
    n = int((u - start) * 24) + 1                    # typewriter
    size = 13
    lines = _wrap(text, size, W - 12)
    shown, left = [], n
    for ln in lines:
        shown.append(ln[:max(0, left)])
        left -= len(ln) + 1
    lh = size + 4
    y0 = H - lh * len(lines) - 6
    band = img.crop((0, y0 - 4, W, H))
    band = Image.fromarray((np.asarray(band, np.float32) * 0.35).astype(np.uint8), "RGB")
    img.paste(band, (0, y0 - 4))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(shown):
        if ln:
            _text(d, (W / 2, y0 + i * lh + lh / 2), ln, size, (255, 245, 230), stroke=1,
                  anchor="mm")


def _heart(d, cx, cy, r, col):
    d.ellipse([cx - r, cy - r, cx, cy], fill=col)
    d.ellipse([cx, cy - r, cx + r, cy], fill=col)
    d.polygon([(cx - r, cy - r / 2), (cx + r, cy - r / 2), (cx, cy + r)], fill=col)


# ---------------------------------------------------------------- Maeva ---

def _maeva(d, x, y, s, t, pose="stand", coat=DRESS):
    """Maeva with feet at (x, y). s = scale (1 ~ 34 px tall)."""
    def P(px, py):
        return (x + px * s, y + py * s)

    walk = math.sin(t * 9) if pose == "walk" else 0.0
    bob = abs(walk) * 0.8
    hy = -27 - bob                                   # head centre
    # long hair behind
    d.ellipse([*P(-8, hy - 7), *P(8, hy + 10)], fill=HAIR)
    if pose not in ("swim",):
        # legs
        d.line([P(-2, -9 - bob), P(-2 - 3 * walk, 0)], fill=(60, 40, 50), width=max(1, int(2 * s)))
        d.line([P(2, -9 - bob), P(2 + 3 * walk, 0)], fill=(60, 40, 50), width=max(1, int(2 * s)))
        d.ellipse([*P(-4 - 3 * walk, -1), *P(-1 - 3 * walk, 1)], fill=(40, 30, 40))
        d.ellipse([*P(1 + 3 * walk, -1), *P(4 + 3 * walk, 1)], fill=(40, 30, 40))
        # dress
        d.polygon([P(-4, -19 - bob), P(4, -19 - bob), P(8, -8 - bob), P(-8, -8 - bob)], fill=coat)
    else:
        d.rectangle([*P(-5, -19), *P(5, -14)], fill=coat)
    # arms
    if pose == "wave":
        a = math.sin(t * 8) * 0.5
        d.line([P(4, -17 - bob), P(9 + 2 * a, -26)], fill=SKIN, width=max(1, int(2 * s)))
        d.line([P(-4, -17 - bob), P(-7, -10 - bob)], fill=SKIN, width=max(1, int(2 * s)))
    elif pose == "eat":
        d.line([P(4, -17), P(3, -22)], fill=SKIN, width=max(1, int(2 * s)))
        d.line([P(-4, -17), P(-7, -10)], fill=SKIN, width=max(1, int(2 * s)))
    elif pose != "swim":
        d.line([P(4, -17 - bob), P(7 - 2 * walk, -10 - bob)], fill=SKIN, width=max(1, int(2 * s)))
        d.line([P(-4, -17 - bob), P(-7 + 2 * walk, -10 - bob)], fill=SKIN, width=max(1, int(2 * s)))
    # head
    d.ellipse([*P(-6, hy - 6), *P(6, hy + 6)], fill=SKIN)
    d.chord([*P(-7, hy - 8), *P(7, hy + 3)], 180, 360, fill=HAIR)       # fringe
    blink = (t % 3.3) < 0.12
    ey = hy + 1
    if blink:
        d.line([P(-3.5, ey), P(-1.5, ey)], fill=(30, 20, 30))
        d.line([P(1.5, ey), P(3.5, ey)], fill=(30, 20, 30))
    else:
        d.ellipse([*P(-3.5, ey - 1), *P(-1.5, ey + 1)], fill=(30, 20, 30))
        d.ellipse([*P(1.5, ey - 1), *P(3.5, ey + 1)], fill=(30, 20, 30))
    d.ellipse([*P(-5.5, ey + 2), *P(-3.5, ey + 3.5)], fill=(255, 150, 160))
    d.ellipse([*P(3.5, ey + 2), *P(5.5, ey + 3.5)], fill=(255, 150, 160))
    if pose == "eat" and int(t * 4) % 2 == 0:
        d.ellipse([*P(-1.5, hy + 2.5), *P(1.5, hy + 5)], fill=(150, 40, 60))   # nom
    else:
        d.arc([*P(-2.5, hy + 1), *P(2.5, hy + 5)], 20, 160, fill=(150, 40, 60))
    # little red beret
    d.chord([*P(-5, hy - 10), *P(5, hy - 3)], 180, 360, fill=(220, 40, 50))
    d.point(P(0, hy - 10), fill=(220, 40, 50))


# -------------------------------------------------------------- scenery ---

def _alps(d, W, base, col=(120, 140, 175), snow=(245, 248, 255)):
    pts = [(0, base), (W * 0.1, base - 22), (W * 0.22, base - 8), (W * 0.36, base - 34),
           (W * 0.5, base - 12), (W * 0.63, base - 40), (W * 0.78, base - 14),
           (W * 0.9, base - 28), (W, base - 6), (W, base)]
    d.polygon(pts, fill=col)
    for i in (1, 3, 5, 7):
        px, py = pts[i]
        d.polygon([(px, py), (px - 7, py + 7), (px + 7, py + 7)], fill=snow)


def _grossmuenster(d, x, base, col):
    for dx in (0, 14):
        d.rectangle([x + dx, base - 46, x + dx + 9, base], fill=col)
        d.polygon([(x + dx - 1, base - 46), (x + dx + 4.5, base - 58), (x + dx + 10, base - 46)],
                  fill=col)
        d.rectangle([x + dx + 3, base - 40, x + dx + 6, base - 35], fill=(255, 220, 140))
    d.rectangle([x - 4, base - 22, x + 27, base], fill=col)


def _water(img, W, y0, t, top, bottom, sparkle=(255, 255, 255)):
    H = img.height
    water = _sky(W, H - y0, top, bottom)
    img.paste(water, (0, y0))
    d = ImageDraw.Draw(img)
    rs = random.Random(3)
    for _ in range(28):
        x = (rs.random() * W + t * 8 * (0.5 + rs.random())) % W
        y = y0 + 3 + rs.random() * (H - y0 - 3)
        L = 3 + rs.random() * 6
        d.line([x, y, x + L, y], fill=sparkle if rs.random() < 0.5 else _lerp(sparkle, bottom, 0.5))


def _clock(d, cx, cy, r, sec, minute=0, hour=8):
    d.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=(40, 40, 40))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(250, 250, 250))
    for i in range(12):
        a = i * math.pi / 6
        d.line([cx + (r - 3) * math.sin(a), cy - (r - 3) * math.cos(a),
                cx + r * math.sin(a), cy - r * math.cos(a)], fill=(20, 20, 20))
    for ang, L, w in ((hour / 12 + minute / 720, 0.5, 2), (minute / 60, 0.8, 2)):
        a = ang * 2 * math.pi
        d.line([cx, cy, cx + r * L * math.sin(a), cy - r * L * math.cos(a)], fill=(20, 20, 20),
               width=w)
    a = sec / 60 * 2 * math.pi                         # the famous red seconds hand
    ex, ey = cx + r * 0.8 * math.sin(a), cy - r * 0.8 * math.cos(a)
    d.line([cx, cy, ex, ey], fill=(220, 20, 20))
    d.ellipse([ex - 2, ey - 2, ex + 2, ey + 2], fill=(220, 20, 20))


def _tram(d, x, y, W):
    L = 120
    d.rounded_rectangle([x, y - 26, x + L, y], 5, fill=(0, 90, 190))
    d.rectangle([x + 2, y - 12, x + L - 2, y - 8], fill=(250, 250, 250))
    for i in range(7):
        wx = x + 6 + i * 16
        d.rectangle([wx, y - 23, wx + 11, y - 14], fill=(170, 210, 240))
    d.line([x + 40, y - 26, x + 52, y - 36], fill=(60, 60, 60), width=2)       # pantograph
    d.line([x + 52, y - 36, x + 64, y - 26], fill=(60, 60, 60), width=2)
    for wx in (x + 14, x + 34, x + L - 34, x + L - 14):
        d.ellipse([wx - 4, y - 3, wx + 4, y + 5], fill=(30, 30, 30))
    _text(d, (x + L - 10, y - 18), "4", 9, (255, 255, 255), stroke=1, anchor="mm")


def _swan(d, x, y, t):
    bob = math.sin(t * 2.5) * 1.5
    y += bob
    d.ellipse([x - 10, y - 6, x + 10, y + 3], fill=(250, 250, 250))
    d.line([x + 6, y - 3, x + 9, y - 16], fill=(250, 250, 250), width=3)
    d.ellipse([x + 7, y - 20, x + 13, y - 14], fill=(250, 250, 250))
    d.polygon([(x + 13, y - 18), (x + 18, y - 16), (x + 13, y - 15)], fill=(255, 140, 0))
    d.point((x + 11, y - 18), fill=(0, 0, 0))


def _macaron(d, x, y, col, s=1.0):
    w, h = 7 * s, 2.5 * s
    d.ellipse([x - w, y - h * 2, x + w, y], fill=col)
    d.rectangle([x - w + 1, y - h * 0.4, x + w - 1, y + h * 0.4], fill=(255, 245, 230))
    d.ellipse([x - w, y, x + w, y + h * 2], fill=col)


# ----------------------------------------------------------------- scenes ---

def _morning(u, t, W, H):
    k = _clamp(u / 7)
    img = _sky(W, H, _lerp((70, 40, 110), (90, 160, 235), k),
               _lerp((255, 150, 120), (200, 230, 255), k))
    d = ImageDraw.Draw(img)
    horizon = int(H * 0.55)
    sy = horizon + 10 - 50 * _clamp(u / 6)
    d.ellipse([W * 0.72 - 12, sy - 12, W * 0.72 + 12, sy + 12], fill=(255, 220, 90))
    _alps(d, W, horizon)
    _water(img, W, horizon, t, (70, 120, 190), (20, 50, 110))
    d = ImageDraw.Draw(img)
    _grossmuenster(d, int(W * 0.1), horizon + 2, (60, 55, 70))
    d.rectangle([0, int(H * 0.8), W, H], fill=(120, 110, 100))      # quay
    _maeva(d, W * 0.66, H * 0.8, 1.6, t, "wave" if u > 2.5 else "stand")
    return img


def _tram_scene(u, t, W, H):
    img = _sky(W, H, (120, 180, 240), (210, 235, 255))
    d = ImageDraw.Draw(img)
    street = int(H * 0.72)
    cols = [(240, 210, 180), (210, 225, 200), (245, 230, 160), (220, 200, 225), (200, 220, 240)]
    for i in range(5):                                 # facades
        x0 = i * W / 5
        d.rectangle([x0, H * 0.18 + (i % 2) * 8, x0 + W / 5 - 1, street], fill=cols[i])
        for wy in range(int(H * 0.25 + (i % 2) * 8), street - 10, 16):
            for wx in (x0 + 6, x0 + W / 10 + 3):
                d.rectangle([wx, wy, wx + 7, wy + 9], fill=(90, 110, 140))
    d.rectangle([0, street, W, H], fill=(110, 110, 115))
    d.line([0, street + 30, W, street + 30], fill=(200, 200, 205))       # rails
    sec = _clamp((u - 0.5) / 5.5) * 60                   # 7:59:00 -> 8:00:00
    minute = 59 if sec < 60 else 0
    hour = 7 if sec < 60 else 8
    _clock(d, W * 0.82, H * 0.14, 15, sec % 60, minute, hour)
    d.rectangle([W * 0.3, street - 34, W * 0.3 + 2, street], fill=(60, 60, 60))   # stop sign
    d.rectangle([W * 0.3 - 16, street - 44, W * 0.3 + 18, street - 34], fill=(255, 255, 255),
                outline=(0, 60, 150))
    _text(d, (W * 0.3 + 1, street - 39), "Paradeplatz", 7, (0, 60, 150), stroke=0, anchor="mm")
    # Maeva walks to the stop, waits, boards
    mx = -10 + (W * 0.42 + 10) * _clamp(u / 3)
    tram_x = W + 10 - (W + 10 - W * 0.12) * _clamp((u - 3.2) / 2.8)    # arrives at 6.0
    if u > 8.0:
        tram_x = W * 0.12 - (u - 8.0) ** 2 * 18                       # departs
    if u < 7.0:
        _maeva(d, mx, street + 22, 1.5, t, "walk" if u < 3 else "stand")
    _tram(d, tram_x, street + 28, W)
    if 6.0 < u < 7.5:
        _text(d, (W * 0.82, H * 0.32), "8:00:00!", 11, (255, 255, 255), stroke=2, anchor="mm")
    return img


def _swim(u, t, W, H):
    img = _sky(W, H, (90, 170, 245), (190, 230, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([W * 0.08, H * 0.06, W * 0.08 + 24, H * 0.06 + 24], fill=(255, 225, 90))
    shore = int(H * 0.36)
    d.rectangle([0, shore - 18, W, shore], fill=(110, 160, 90))         # trees/bank
    for x in range(0, W, 14):
        d.ellipse([x - 4, shore - 30, x + 14, shore - 10], fill=(80, 140, 70))
    _water(img, W, shore, t * 2, (60, 150, 200), (20, 90, 150))
    d = ImageDraw.Draw(img)
    x = -20 + (W + 40) * (u / 12)
    y = H * 0.62 + math.sin(t * 2) * 2
    _maeva(d, x, y + 22, 1.4, t, "swim")                          # waist at y
    d.ellipse([x - 15, y - 5, x + 15, y + 7], outline=(255, 110, 160), width=5)   # swim ring
    d.arc([x - 15, y - 5, x + 15, y + 7], 200, 250, fill=(255, 255, 255), width=2)
    if u > 4:
        _swan(d, x - 34 - math.sin(t) * 3, y + 4, t)
    if u > 6.5:
        _heart(d, x - 18, y - 30 - (u - 6.5) * 4 % 14, 4, (255, 90, 140))
    return img


def _spruengli(u, t, W, H):
    img = _sky(W, H, (255, 220, 230), (255, 190, 210))
    d = ImageDraw.Draw(img)
    _text(d, (W / 2, 12), "SPRÜNGLI", 15, (120, 70, 50), stroke=0, anchor="mm")
    cols = [(255, 160, 190), (180, 230, 170), (255, 230, 140), (200, 170, 240),
            (250, 200, 150), (170, 210, 250)]
    for row in range(3):                               # the counter display
        for i in range(8):
            _macaron(d, 14 + i * 23, 34 + row * 16, cols[(i + row) % 6], 1.1)
    d.rectangle([0, 82, W, 88], fill=(200, 160, 140))
    _maeva(d, W * 0.42, H * 0.86, 1.8, t, "eat")
    eaten = min(12, int(max(0, u - 1.0) / 0.75))
    # macaron travelling to her mouth
    ph = (max(0, u - 1.0) % 0.75) / 0.75
    if eaten < 12:
        mx, my = W * 0.42 + 6, H * 0.86 - 50 + 6 * (1 - ph)
        _macaron(d, mx, my, cols[eaten % 6], 0.6)
    _text(d, (W * 0.8, H * 0.6), f"x{eaten}", 20, (255, 255, 255), stroke=2, anchor="mm")
    for i in range(min(eaten, 6)):
        _heart(d, W * 0.72 + (i % 3) * 14, H * 0.42 - (i // 3) * 12 - (t * 6 + i * 5) % 8,
               3, (255, 80, 130))
    return img


def _snow(u, t, W, H):
    img = _sky(W, H, (150, 190, 235), (230, 240, 255))
    d = ImageDraw.Draw(img)
    _alps(d, W, int(H * 0.38), (150, 165, 195))
    d.polygon([(0, H * 0.35), (W, H * 0.85), (W, H), (0, H)], fill=(245, 248, 255))   # slope
    for i in range(7):                                  # pine trees
        tx, ty = 12 + i * 30, H * 0.35 + (12 + i * 30) * (0.5 * H / W) - 4
        d.polygon([(tx, ty - 22), (tx - 8, ty), (tx + 8, ty)], fill=(40, 100, 70))
    rs = random.Random(9)
    for _ in range(70):                                 # snowfall
        x = (rs.random() * W + math.sin(t + rs.random() * 6) * 6) % W
        y = (rs.random() * H + t * (18 + rs.random() * 20)) % H
        d.point((x, y), fill=(255, 255, 255))
    run = (u % 4.0) / 4.0                               # sledge down, again and again
    x = -20 + (W + 40) * run
    y = H * 0.35 + x * (0.5 * H / W) + 4
    ang = math.atan(0.5 * H / W)
    d.line([x - 14, y + 2, x + 12, y + 2 + 26 * math.tan(ang) * 0.5], fill=(150, 80, 40), width=3)
    _maeva(d, x, y, 1.3, t, "stand", coat=(80, 140, 230))
    d.line([x - 4, y - 25, x - 16 - math.sin(t * 12) * 3, y - 27], fill=(230, 40, 50), width=2)
    if 6.5 < u < 11:
        _text(d, (x, y - 50), "Wheee!", 12, (255, 255, 255), stroke=2, anchor="mm")
    return img


def _home(u, t, W, H):
    img = _sky(W, H, (10, 15, 45), (40, 40, 90))
    d = ImageDraw.Draw(img)
    rs = random.Random(2)
    for _ in range(40):
        x, y = rs.random() * W, rs.random() * H * 0.4
        v = int(120 + 120 * (0.5 + 0.5 * math.sin(t * 2 + x)))
        d.point((x, y), fill=(v, v, v))
    d.ellipse([W * 0.12, H * 0.08, W * 0.12 + 18, H * 0.08 + 18], fill=(250, 245, 210))
    horizon = int(H * 0.42)
    for i in range(16):                                 # city skyline lights
        bx = i * W / 16
        bh = 10 + (i * 37 % 23)
        d.rectangle([bx, horizon - bh, bx + W / 16 - 1, horizon], fill=(30, 30, 55))
        if i % 2 == 0:
            d.point((bx + 4, horizon - bh + 4), fill=(255, 210, 120))
    _water(img, W, horizon, t, (25, 30, 70), (10, 10, 35), sparkle=(255, 200, 110))
    d = ImageDraw.Draw(img)
    # House Fortuna
    hx, hy = W * 0.58, H * 0.86
    d.rectangle([hx, hy - 50, hx + 66, hy], fill=(230, 190, 150))
    d.polygon([(hx - 6, hy - 50), (hx + 33, hy - 76), (hx + 72, hy - 50)], fill=(170, 60, 60))
    for wx in (hx + 6, hx + 46):
        d.rectangle([wx, hy - 42, wx + 13, hy - 30], fill=(255, 210, 110))
    door_open = _clamp((u - 6.5) / 0.8)
    d.rectangle([hx + 25, hy - 26, hx + 41, hy], fill=(255, 220, 140) if door_open else (120, 70, 40))
    if door_open < 1:
        d.rectangle([hx + 25, hy - 26, hx + 25 + 16 * (1 - door_open), hy], fill=(120, 70, 40))
    _text(d, (hx + 33, hy - 58), "HOUSE FORTUNA", 7, (255, 240, 200), stroke=1, anchor="mm")
    d.rectangle([0, hy, W, H], fill=(60, 55, 60))
    mx = -10 + (hx + 33 + 10) * _clamp(u / 7.2)
    if u < 8.0:
        _maeva(d, mx, hy, 1.4, t, "walk" if u < 7.2 else "stand")
    if u > 8.0:
        for i in range(4):
            _heart(d, hx + 33 + math.sin(t * 2 + i) * 10, hy - 80 - ((u - 8) * 12 + i * 10) % 40,
                   3, (255, 100, 150))
    return img


def _end(u, t, W, H):
    img = Image.new("RGB", (W, H), (20, 10, 30))
    d = ImageDraw.Draw(img)
    rs = random.Random(4)
    for _ in range(14):
        hx, hy = rs.random() * W, (rs.random() * H - t * 10) % H
        _heart(d, hx, hy, 3, (255, 90 + rs.randrange(80), 150))
    k = _back(_clamp(u / 0.8))
    _text(d, (W / 2, H * 0.16), "THE END", int(26 * k) + 1, (255, 230, 240), anchor="mm")
    _maeva(d, W / 2, H * 0.78, 2.4, t, "wave")
    _text(d, (W / 2, H * 0.92), "Maeva x Zürich", 14, (255, 150, 190), anchor="mm")
    return img


SCENE_FN = {"morning": _morning, "tram": _tram_scene, "swim": _swim,
            "spruengli": _spruengli, "snow": _snow, "home": _home, "end": _end}


def frame(t: float) -> Image.Image:
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    t = t % LOOP_SEC
    for name, a, b in SCENES:
        if a <= t < b:
            u = t - a
            img = SCENE_FN[name](u, t, W, H)
            _caption(img, name, u, W, H)
            fade = min(_clamp(u / FADE), _clamp((b - t) / FADE))
            if fade < 1:
                img = Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8), "RGB")
            return img
    return Image.new("RGB", (W, H))
