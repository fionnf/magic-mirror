"""'Welcome to HOUSE FORTUNA' — looping welcome animation for the wall.

welcome_frame(t) is a pure function of time t (seconds, wrapped to LOOP_SEC),
so it can be previewed offline (GIF) and played live at any frame rate.

Timeline (s):
  0.0  stars + floating pastel hearts fade in
  1.5  "Welcome to" types in (blinking cursor)
  3.2  HOUSE drops in letter by letter (bounce), rainbow
  4.3  FORTUNA drops in, then all letters wave gently
  6.0  wheel of fortune pops up, spins, slows, stops, sparkles
 14.0  rainbow plasma takes over, FORTUNA pulses on top
 17.6  fade to black, loop
"""
import colorsys
import math
import random

import numpy as np
from PIL import Image, ImageDraw

import config
from display import text_renderer as tr

LOOP_SEC = 19.0

HEART = [".XX.XX.",
         "XXXXXXX",
         "XXXXXXX",
         ".XXXXX.",
         "..XXX..",
         "...X..."]

_rng = random.Random(7)
_STARS = [(_rng.random(), _rng.random(), _rng.random()) for _ in range(45)]
_HEARTS = [(_rng.random(), 14 + 18 * _rng.random(), _rng.random(), _rng.random())
           for _ in range(9)]              # x, speed px/s, phase, hue
_fonts = {}


# ---------------------------------------------------------------- helpers ---

def _hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _bounce(t):
    """easeOutBounce, t in [0,1]."""
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


def _back(t):
    """easeOutBack (overshoot pop)."""
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _font_fit(word, max_w, size):
    """Largest font <= size whose rendering of `word` fits max_w px."""
    while size > 8:
        key = size
        if key not in _fonts:
            _fonts[key] = tr._load_font(size)
        f = _fonts[key]
        if f.getlength(word) + 2 * tr._STROKE <= max_w:
            return f
        size -= 2
    return _fonts.setdefault(8, tr._load_font(8))


def _text(d, xy, s, font, fill):
    d.text(xy, s, font=font, fill=fill, stroke_width=tr._STROKE,
           stroke_fill=tr._STROKE_FILL)


# ----------------------------------------------------------------- layers ---

def _stars(d, t, W, H, alpha):
    for x, y, ph in _STARS:
        tw = 0.5 + 0.5 * math.sin(t * 2.2 + ph * 6.283)
        v = int((60 + 170 * tw) * alpha)
        if v > 8:
            d.point((int(x * (W - 1)), int(y * (H - 1))), fill=(v * 3 // 4, v * 3 // 4, v))


def _hearts(d, t, W, H, alpha):
    span = H + 20
    for x0, speed, ph, hue in _HEARTS:
        y = H + 8 - ((t * speed + ph * span) % span)
        x = x0 * (W - 16) + 4 * math.sin(t * 1.6 + ph * 6.283)
        r, g, b = _hsv(hue, 0.45, 1.0)
        c = (int(r * alpha), int(g * alpha), int(b * alpha))
        for ry, row in enumerate(HEART):
            for rx, k in enumerate(row):
                if k == "X":
                    px, py = int(x) + rx * 2, int(y) + ry * 2
                    d.rectangle([px, py, px + 1, py + 1], fill=c)


def _typewriter(d, t, W, y, start, text="Welcome to"):
    if t < start:
        return
    font = _font_fit(text, W - 10, 22)
    n = min(len(text), int((t - start) / 0.11) + 1)
    shown = text[:n]
    x = (W - font.getlength(text)) / 2
    _text(d, (x, y), shown, font, (255, 225, 235))
    typing = n < len(text) or t - start < len(text) * 0.11 + 1.2
    if typing and int(t * 3) % 2 == 0:                    # blinking cursor
        cx = x + font.getlength(shown) + 2
        d.rectangle([cx, y + 4, cx + 2, y + font.size], fill=(255, 225, 235))


def _drop_word(d, t, W, y, word, start, size, hue0):
    font = _font_fit(word, W - 6, size)
    x0 = (W - font.getlength(word)) / 2
    for i, ch in enumerate(word):
        lt = (t - start - i * 0.11) / 0.75
        if lt <= 0:
            continue
        yoff = -70 * (1 - _bounce(_clamp(lt)))
        if lt >= 1:                                       # landed: gentle wave
            yoff = 2.2 * math.sin(t * 3.0 + i * 0.7)
        hue = hue0 + i / (len(word) * 1.4) + t * 0.12
        _text(d, (x0 + font.getlength(word[:i]), y + yoff), ch, font,
              _hsv(hue, 0.55, 1.0))


def _wheel(img, d, t, W, H, top):
    """Wheel of fortune under the title: pop in, spin, slow down, sparkle."""
    start, stop = 6.0, 12.6
    if t < start:
        return
    k = _clamp((t - start) / 0.6)
    room = H - top - 6
    r = max(4, int(min(W // 2 - 10, room // 2) * _back(k)))
    cx, cy = W // 2, top + room // 2 + 2
    # spin: fast at first, easing to a stop at `stop`
    u = _clamp((t - start) / (stop - start))
    angle = 900 * (1 - (1 - u) ** 3)
    n = 8
    for i in range(n):
        a0 = angle + i * 360 / n
        d.pieslice([cx - r, cy - r, cx + r, cy + r], a0, a0 + 360 / n,
                   fill=_hsv(i / n, 0.5, 1.0))
    for i in range(n):                                    # spokes
        a = math.radians(angle + i * 360 / n)
        d.line([cx, cy, cx + r * math.cos(a), cy + r * math.sin(a)], fill=(255, 255, 255))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=2)
    hub = max(3, r // 5)
    d.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=(255, 215, 90),
              outline=(255, 255, 255))
    # pointer at the top
    d.polygon([(cx - 6, cy - r - 8), (cx + 6, cy - r - 8), (cx, cy - r + 4)],
              fill=(255, 255, 255), outline=(0, 0, 0))
    # sparkles once it has stopped
    if t > stop:
        rs = random.Random(int(t * 7))
        for _ in range(6):
            a = rs.random() * 6.283
            rr = r + 6 + rs.random() * 14
            sx, sy = cx + rr * math.cos(a), cy + rr * math.sin(a)
            col = _hsv(rs.random(), 0.3, 1.0)
            d.line([sx - 3, sy, sx + 3, sy], fill=col)
            d.line([sx, sy - 3, sx, sy + 3], fill=col)


def _plasma(t, W, H):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    v = (np.sin(x / 15.0 + t * 1.1) + np.sin(y / 11.0 - t * 1.4)
         + np.sin((x + y) / 19.0 + t * 0.8)
         + np.sin(np.sqrt((x - W / 2) ** 2 + (y - H / 2) ** 2) / 9.0 - t * 2.2))
    h = v / 8.0 + t * 0.08
    two_pi = 2 * np.pi
    r = 0.55 + 0.45 * np.sin(two_pi * h)
    g = 0.55 + 0.45 * np.sin(two_pi * (h + 1 / 3))
    b = 0.55 + 0.45 * np.sin(two_pi * (h + 2 / 3))
    return (np.stack([r, g, b], -1) * 230).astype(np.float32)


# ------------------------------------------------------------------- main ---

def welcome_frame(t: float) -> Image.Image:
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    t = t % LOOP_SEC
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)

    intro = _clamp(t / 1.5)
    _stars(d, t, W, H, intro)
    _hearts(d, t, W, H, intro)

    y_welcome = int(H * 0.03)
    y_house = int(H * 0.17)
    y_fortuna = int(H * 0.35)
    _typewriter(d, t, W, y_welcome, 1.5)
    _drop_word(d, t, W, y_house, "HOUSE", 3.2, 30, 0.0)
    _drop_word(d, t, W, y_fortuna, "FORTUNA", 4.3, 36, 0.35)
    _wheel(img, d, t, W, H, top=int(H * 0.61))

    # finale: plasma crossfade with pulsing FORTUNA, then fade to black
    if t >= 14.0:
        a = _clamp((t - 14.0) / 0.7)
        base = np.asarray(img, np.float32)
        out = base * (1 - a) + _plasma(t, W, H) * a
        img = Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGB")
        d = ImageDraw.Draw(img)
        pulse = 1 + 0.08 * math.sin(t * 6)
        font = _font_fit("FORTUNA", int((W - 8) * pulse), int(40 * pulse))
        tw = font.getlength("FORTUNA")
        _text(d, ((W - tw) / 2, H / 2 - font.size * 0.65), "FORTUNA", font, (255, 255, 255))
        fade = 1 - _clamp((t - 17.6) / 0.9)
        if fade < 1:
            img = Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8), "RGB")
    return img


def welcome_frames():
    """Real-time generator (same API as display.animations)."""
    import time
    t0 = time.monotonic()
    while True:
        yield welcome_frame(time.monotonic() - t0)
