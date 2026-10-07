"""Dewa, flight attendant for Edelweiss — a little animated story (~86 s loop).

A date at every layover; one day they all turn up at House Fortuna for a party.
frame(t) is a pure function of time t.

  0-9    Zürich airport: Dewa, his suitcase, the Edelweiss plane
  9-17   in the cabin: trolley, "Chicken or pasta?"
 17-57   four layovers, four dates (10 s each): Cancún, Cape Town,
         Las Vegas, Reykjavík - plane lands, phone pings, date walks up
 57-66   the doorbell at House Fortuna: all four dates arrive
 66-80   the party
 80-86   THE END
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw

import config
from display.maeva_story import (_back, _clamp, _font, _heart, _lerp, _sky, _text,
                                 _water, _wrap, _alps)
from display.pride_show import _paste_emoji, PRIDE

LOOP_SEC = 86.0
FADE = 0.4
EDEL_RED = (200, 25, 45)

DEWA = dict(skin=(200, 145, 105), hair=(25, 20, 20), style="short",
            top=(25, 35, 70), bottom=(25, 35, 70), extra="uniform")
DATES = {
    "Carlos": dict(skin=(205, 150, 105), hair=(20, 15, 15), style="curly",
                   top=(255, 120, 60), bottom=(240, 230, 210), extra="flowers"),
    "Thabo": dict(skin=(110, 70, 45), hair=(15, 10, 10), style="buzz",
                  top=(40, 150, 90), bottom=(60, 60, 80), extra=""),
    "Brad": dict(skin=(240, 200, 170), hair=(240, 210, 110), style="short",
                 top=(70, 120, 200), bottom=(40, 60, 110), extra="cowboy"),
    "Gunnar": dict(skin=(245, 215, 195), hair=(200, 80, 30), style="short",
                   top=(230, 225, 215), bottom=(70, 70, 90), extra="beard_sweater"),
}
STOPS = [
    ("CANCÚN", "Carlos", "🍹", "Cancún: margaritas with Carlos."),
    ("CAPE TOWN", "Thabo", "🌅", "Cape Town: a sunset hike with Thabo."),
    ("LAS VEGAS", "Brad", "🎰", "Las Vegas: Brad. What happens in Vegas..."),
    ("REYKJAVÍK", "Gunnar", "🌌", "Reykjavík: northern lights with Gunnar."),
]
SCENES = [("airport", 0, 9), ("cabin", 9, 17)] + \
         [(f"stop{i}", 17 + 10 * i, 27 + 10 * i) for i in range(4)] + \
         [("door", 57, 66), ("party", 66, 80), ("end", 80, 86)]
CAPTIONS = {
    "airport": [(0.6, "This is Dewa."), (4.0, "Flight attendant for Edelweiss.")],
    "cabin": [(0.5, "Serving looks at 38,000 ft."), (5.0, "Chicken or pasta, darling?")],
    "door": [(0.5, "One day the doorbell rang at House Fortuna..."),
             (5.0, "It was ALL of them.")],
    "party": [(0.5, "Surprise party!"), (5.0, "Awkward? No. Iconic.")],
    "end": [],
}


# ------------------------------------------------------------- helpers ---

def _caption(img, scene, u, W, H, extra=None):
    caps = list(CAPTIONS.get(scene, [])) + (extra or [])
    cur = None
    for start, text in caps:
        if u >= start:
            cur = (start, text)
    if not cur:
        return
    start, text = cur
    n = int((u - start) * 24) + 1
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


def _person(d, x, y, s, t, look, pose="stand", face=1):
    """A little character with feet at (x, y). face=1 looks right, -1 left."""
    def P(px, py):
        return (x + px * s * face, y + py * s)

    walk = math.sin(t * 9) if pose == "walk" else 0.0
    dance = math.sin(t * 7 + x) if pose == "dance" else 0.0
    bob = abs(walk) * 0.8 + abs(dance) * 2
    w = max(1, int(2 * s))
    skin, hair, top, bottom = look["skin"], look["hair"], look["top"], look["bottom"]
    # legs
    d.line([P(-2, -10 - bob), P(-2 - 3 * walk - 2 * dance, 0)], fill=bottom, width=w)
    d.line([P(2, -10 - bob), P(2 + 3 * walk + 2 * dance, 0)], fill=bottom, width=w)
    d.ellipse(sorted_box(P(-4 - 3 * walk, -1), P(-1 - 3 * walk, 1)), fill=(30, 25, 25))
    d.ellipse(sorted_box(P(1 + 3 * walk, -1), P(4 + 3 * walk, 1)), fill=(30, 25, 25))
    # torso
    d.rounded_rectangle([min(P(-5, -21 - bob)[0], P(5, -9 - bob)[0]), P(-5, -21 - bob)[1],
                         max(P(-5, -21 - bob)[0], P(5, -9 - bob)[0]), P(5, -9 - bob)[1]],
                        2, fill=top)
    if look["extra"] == "uniform":
        d.polygon([P(-1, -21 - bob), P(1, -21 - bob), P(0.6, -14 - bob), P(-0.6, -14 - bob)],
                  fill=EDEL_RED)                                         # tie
        d.point(P(-3, -18 - bob), fill=(255, 255, 255))                 # edelweiss pin
    if look["extra"] == "flowers":
        for px, py in ((-3, -19), (2, -16), (-1, -12), (3, -11)):
            d.point(P(px, py - bob), fill=(255, 230, 80))
    # arms
    if pose == "wave":
        a = math.sin(t * 8) * 0.5
        d.line([P(5, -19 - bob), P(9 + 2 * a, -27)], fill=skin, width=w)
        d.line([P(-5, -19 - bob), P(-7, -11 - bob)], fill=skin, width=w)
    elif pose == "dance":
        up = math.sin(t * 7 + x * 0.3)
        d.line([P(5, -19 - bob), P(9, -26 + 6 * up)], fill=skin, width=w)
        d.line([P(-5, -19 - bob), P(-9, -26 - 6 * up)], fill=skin, width=w)
    elif pose == "toast":
        d.line([P(5, -19), P(8, -24)], fill=skin, width=w)
        d.line([P(-5, -19), P(-7, -11)], fill=skin, width=w)
    else:
        d.line([P(5, -19 - bob), P(7 - 2 * walk, -11 - bob)], fill=skin, width=w)
        d.line([P(-5, -19 - bob), P(-7 + 2 * walk, -11 - bob)], fill=skin, width=w)
    # head
    hy = -27 - bob
    d.ellipse([*sorted_box(P(-6, hy - 6), P(6, hy + 6))], fill=skin)
    st = look["style"]
    if st == "short":
        d.chord([*sorted_box(P(-7, hy - 8), P(7, hy + 3))], 180, 360, fill=hair)
    elif st == "curly":
        for cx in (-5, -1, 3):
            d.ellipse([*sorted_box(P(cx - 3, hy - 9), P(cx + 4, hy - 2))], fill=hair)
    elif st == "buzz":
        d.chord([*sorted_box(P(-6, hy - 7), P(6, hy + 1))], 180, 360, fill=hair)
    if look["extra"] == "beard_sweater":
        d.chord([*sorted_box(P(-6, hy - 2), P(6, hy + 8))], 0, 180, fill=hair)
        for i in range(-4, 5, 2):                                        # sweater pattern
            d.point(P(i, -18 - bob), fill=(200, 40, 40))
    if look["extra"] == "cowboy":
        d.rectangle([*sorted_box(P(-9, hy - 6), P(9, hy - 5))], fill=(140, 90, 50))
        d.rectangle([*sorted_box(P(-5, hy - 11), P(5, hy - 6))], fill=(140, 90, 50))
    ey = hy + 1
    blink = (t + x * 0.01) % 3.1 < 0.12
    for ex in (-2.5, 2.5):
        if blink:
            d.line([P(ex - 1, ey), P(ex + 1, ey)], fill=(20, 15, 20))
        else:
            d.ellipse([*sorted_box(P(ex - 1, ey - 1), P(ex + 1, ey + 1))], fill=(20, 15, 20))
    d.arc([*sorted_box(P(-2.5, hy + 1), P(2.5, hy + 5))], 20, 160, fill=(120, 40, 40))


def sorted_box(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def _plane(d, x, y, s=1.0, face=1):
    def P(px, py):
        return (x + px * s * face, y + py * s)
    d.polygon([P(-40, -4), P(34, -6), P(44, -1), P(36, 4), P(-40, 4)], fill=(250, 250, 250))
    d.polygon([P(-40, -4), P(-46, -20), P(-34, -20), P(-26, -4)], fill=EDEL_RED)   # tail
    cx, cy = P(-38, -13)
    for k in range(6):                                                   # edelweiss flower
        a = k * math.pi / 3
        d.ellipse([cx + 2.4 * s * math.cos(a) - 1.2 * s, cy + 2.4 * s * math.sin(a) - 1.2 * s,
                   cx + 2.4 * s * math.cos(a) + 1.2 * s, cy + 2.4 * s * math.sin(a) + 1.2 * s],
                  fill=(255, 255, 255))
    d.polygon([P(-4, 1), P(10, 1), P(-10, 14), P(-18, 14)], fill=(220, 220, 225))   # wing
    for i in range(10):
        wx, wy = P(-28 + i * 6, -2)
        d.rectangle([wx - 1, wy - 1, wx + 1, wy + 1], fill=(90, 120, 160))
    d.line([P(-36, 2), P(34, 1)], fill=EDEL_RED)


def _phone_ping(img, d, W, u, start, name, emo):
    if not (start < u < start + 3.0):
        return
    k = _clamp((u - start) / 0.35) - _clamp((u - start - 2.6) / 0.35)
    y = -24 + 28 * _back(_clamp(k))
    d.rounded_rectangle([5, y, W - 5, y + 22], 6, fill=(255, 205, 0), outline=(0, 0, 0))
    txt = f"{name} · 300 m"
    _text(d, (24, y + 11), txt, 12, (15, 15, 15), stroke=0, anchor="lm")
    _paste_emoji(img, "📍", 8, y + 4, 13)
    _paste_emoji(img, "😏", 24 + _font(12).getlength(txt) + 3, y + 4, 13)


# --------------------------------------------------------------- scenes ---

def _airport(u, t, W, H):
    img = _sky(W, H, (110, 170, 235), (215, 235, 255))
    d = ImageDraw.Draw(img)
    _alps(d, W, int(H * 0.5))
    d.rectangle([0, H * 0.5, W, H], fill=(120, 125, 130))
    for x in range(0, W, 24):
        d.rectangle([x, H * 0.74, x + 12, H * 0.75], fill=(240, 240, 240))
    _plane(d, W * 0.62, H * 0.6, 1.25)
    mx = -15 + (W * 0.4 + 15) * _clamp(u / 4)
    pose = "walk" if u < 4 else "wave"
    d.rounded_rectangle([mx - 22, H * 0.86 - 14, mx - 12, H * 0.86], 2, fill=EDEL_RED)  # suitcase
    d.line([mx - 17, H * 0.86 - 14, mx - 12, H * 0.86 - 22], fill=(60, 60, 60))
    _person(d, mx, H * 0.86, 1.5, t, DEWA, pose)
    return img


def _cabin(u, t, W, H):
    img = Image.new("RGB", (W, H), (225, 225, 230))
    d = ImageDraw.Draw(img)
    for i in range(5):                                                   # windows + clouds
        wx = 14 + i * 38
        d.rounded_rectangle([wx, 18, wx + 18, 44], 8, fill=(120, 180, 240))
        cx = wx + ((t * 20 + i * 13) % 30) - 8
        d.ellipse([cx, 30, cx + 12, 36], fill=(255, 255, 255))
    d.rectangle([0, 56, W, 60], fill=EDEL_RED)
    for r in range(3):                                                   # seats + heads
        for c in range(6):
            sx, sy = 6 + c * 32, 76 + r * 34
            if c in (2, 3):
                continue
            d.rounded_rectangle([sx, sy, sx + 22, sy + 26], 4, fill=(40, 70, 140))
            hc = [(230, 190, 160), (160, 110, 80), (250, 215, 190)][(r + c) % 3]
            d.ellipse([sx + 6, sy - 6, sx + 16, sy + 4], fill=hc)
    tx = -30 + (W + 40) * _clamp(u / 7)
    _person(d, tx + 30, H * 0.86, 1.6, t, DEWA, "walk" if u < 7 else "stand", face=-1)
    d.rounded_rectangle([tx - 4, H * 0.86 - 32, tx + 20, H * 0.86 - 2], 2, fill=(170, 170, 180))
    d.rectangle([tx - 2, H * 0.86 - 28, tx + 18, H * 0.86 - 26], fill=EDEL_RED)
    if 3 < u < 7.5:
        bx, by = tx + 30, H * 0.86 - 72
        d.rounded_rectangle([bx - 36, by - 10, bx + 36, by + 10], 6, fill=(255, 255, 255),
                            outline=(0, 0, 0))
        _text(d, (bx, by), "Chicken or pasta?", 9, (20, 20, 20), stroke=0, anchor="mm")
    return img


def _cancun(d, img, W, H, t):
    img.paste(_sky(W, H, (60, 180, 245), (190, 235, 255)), (0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(W * 0.62, H * 0.5), (W * 0.9, H * 0.5), (W * 0.84, H * 0.36),
               (W * 0.68, H * 0.36)], fill=(190, 170, 130))                 # pyramid
    for i in range(4):
        y = H * 0.5 - i * 4
        d.line([W * 0.62 + i * 2, y, W * 0.9 - i * 2, y], fill=(150, 130, 100))
    _water(img, W, int(H * 0.5), t, (40, 210, 210), (20, 150, 190))
    d = ImageDraw.Draw(img)
    d.polygon([(0, H * 0.72), (W, H * 0.66), (W, H), (0, H)], fill=(245, 225, 170))
    d.line([W * 0.12, H * 0.72, W * 0.16, H * 0.4], fill=(120, 80, 40), width=4)   # palm
    for a in range(5):
        ang = -math.pi / 2 + (a - 2) * 0.6
        d.line([W * 0.16, H * 0.4, W * 0.16 + 22 * math.cos(ang), H * 0.4 + 12 + 10 * math.sin(ang)],
               fill=(40, 150, 60), width=3)
    return d


def _capetown(d, img, W, H, t):
    img.paste(_sky(W, H, (90, 60, 140), (255, 160, 90)), (0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([W * 0.7, H * 0.36, W * 0.7 + 26, H * 0.36 + 26], fill=(255, 200, 90))
    d.polygon([(0, H * 0.55), (W * 0.18, H * 0.34), (W * 0.62, H * 0.33), (W * 0.78, H * 0.5),
               (W, H * 0.55), (W, H * 0.6), (0, H * 0.6)], fill=(70, 55, 80))   # Table Mountain
    _water(img, W, int(H * 0.6), t, (230, 130, 90), (90, 60, 110), sparkle=(255, 220, 160))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H * 0.78, W, H], fill=(90, 70, 70))
    return d


def _vegas(d, img, W, H, t):
    img.paste(_sky(W, H, (15, 10, 40), (60, 20, 80)), (0, 0))
    d = ImageDraw.Draw(img)
    for i in range(7):                                                   # casinos
        bx = i * W / 7
        bh = 40 + (i * 29 % 50)
        d.rectangle([bx + 2, H * 0.78 - bh, bx + W / 7 - 2, H * 0.78], fill=(40, 30, 60))
        for wy in range(int(H * 0.78 - bh + 4), int(H * 0.78) - 4, 7):
            on = math.sin(t * 6 + i * 3 + wy) > 0
            d.point((bx + 8, wy), fill=_lerp((255, 60, 180), (255, 220, 60), (i % 3) / 2) if on else (60, 50, 80))
    sx, sy = W * 0.5, H * 0.28                                           # the famous sign
    d.polygon([(sx, sy - 26), (sx + 34, sy), (sx, sy + 26), (sx - 34, sy)], fill=(250, 250, 240),
              outline=(255, 60, 60))
    _text(d, (sx, sy - 9), "WELCOME", 7, (220, 30, 30), stroke=0, anchor="mm")
    col = (255, 60, 60) if int(t * 4) % 2 else (40, 120, 255)
    _text(d, (sx, sy + 4), "VEGAS", 13, col, stroke=0, anchor="mm")
    d.rectangle([0, H * 0.78, W, H], fill=(50, 45, 55))
    return d


def _reykjavik(d, img, W, H, t):
    base = _sky(W, H, (5, 10, 30), (20, 35, 70))
    arr = np.asarray(base, np.float32).copy()
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    band = H * 0.25 + np.sin(x / 22 + t * 0.9) * 12 + np.sin(x / 9 - t * 1.7) * 4
    g = np.exp(-((y - band) ** 2) / 120) * (0.6 + 0.4 * np.sin(x / 15 + t * 2))
    arr += g[..., None] * np.array([40, 230, 140], np.float32)
    img.paste(Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB"), (0, 0))
    d = ImageDraw.Draw(img)
    cx, gy = W * 0.78, H * 0.72                                          # Hallgrimskirkja
    for i in range(5):
        d.rectangle([cx - 14 + i * 3, gy - 12 - i * 9, cx + 14 - i * 3, gy], fill=(200, 205, 215))
    d.polygon([(cx - 3, gy - 56), (cx, gy - 70), (cx + 3, gy - 56)], fill=(200, 205, 215))
    d.rectangle([0, gy, W, H], fill=(235, 240, 250))
    return d


BACKDROPS = [_cancun, _capetown, _vegas, _reykjavik]


def _stop(i, u, t, W, H):
    city, date, emo, cap = STOPS[i]
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    if u < 1.8:                                                          # fly-in title card
        img.paste(_sky(W, H, (90, 160, 235), (200, 230, 255)), (0, 0))
        d = ImageDraw.Draw(img)
        px = -60 + (W + 120) * (u / 1.8)
        _plane(d, px, H * 0.62 - u * 10, 1.0)
        k = _back(_clamp(u / 0.5))
        _text(d, (W / 2, H * 0.3), city, int(26 * k) + 1, (255, 255, 255), anchor="mm")
        return img, []
    d = BACKDROPS[i](d, img, W, H, t)
    v = u - 1.8
    ground = H * 0.86
    _person(d, W * 0.32, ground, 1.5, t, DEWA, "toast" if v > 5.2 else "stand")
    dx = W + 20 - (W + 20 - W * 0.64) * _clamp((v - 2.6) / 2.2)
    if v > 2.6:
        _person(d, dx, ground, 1.5, t, DATES[date], "walk" if v < 4.8 else "toast", face=-1)
    _phone_ping(img, d, W, v, 0.4, date, emo)
    if v > 4.8:
        for k2 in range(3):
            _heart(d, W * 0.48 + math.sin(t * 2 + k2 * 2) * 8,
                   ground - 52 - ((v - 4.8) * 14 + k2 * 9) % 30, 3, (255, 90, 140))
    if v > 5.2:
        _paste_emoji(img, emo, W * 0.48 - 8, ground - 70, 16)
    return img, [(2.0, cap)]


def _door(u, t, W, H):
    img = _sky(W, H, (120, 180, 240), (215, 235, 255))
    d = ImageDraw.Draw(img)
    hx, hy = W * 0.3, H * 0.84
    d.rectangle([hx, hy - 70, hx + 90, hy], fill=(230, 190, 150))
    d.polygon([(hx - 8, hy - 70), (hx + 45, hy - 104), (hx + 98, hy - 70)], fill=(170, 60, 60))
    _text(d, (hx + 45, hy - 80), "HOUSE FORTUNA", 8, (255, 240, 210), stroke=1, anchor="mm")
    for wx in (hx + 8, hx + 66):
        d.rectangle([wx, hy - 60, wx + 16, hy - 44], fill=(255, 225, 140))
    door_open = _clamp((u - 2.2) / 0.6)
    d.rectangle([hx + 36, hy - 34, hx + 56, hy], fill=(255, 220, 150) if door_open else (120, 70, 40))
    if door_open < 1:
        d.rectangle([hx + 36, hy - 34, hx + 36 + 20 * (1 - door_open), hy], fill=(120, 70, 40))
    else:
        _person(d, hx + 46, hy, 1.3, t, DEWA, "stand")
    d.rectangle([0, hy, W, H], fill=(110, 140, 90))
    if 0.8 < u < 2.4:
        _text(d, (hx + 46, hy - 50), "DING DONG!", 12, (255, 255, 255), anchor="mm")
    for k, name in enumerate(DATES):                                     # they all arrive
        end_x = hx + 66 + k * 18                                         # beside the door
        x = end_x + (W + 20 - end_x) * (1 - _clamp((u - 3.0 - k * 0.3) / 3.0))
        _person(d, x, hy + 2, 1.2, t, DATES[name], "walk" if u < 6.6 + k * 0.3 else "wave", face=-1)
    if u > 5.0:
        _text(d, (hx + 46, hy - 112), "!!!", 16, (255, 80, 80), anchor="mm")
    return img


def _party(u, t, W, H):
    img = Image.new("RGB", (W, H), (15, 5, 25))
    arr = np.asarray(img, np.float32).copy()
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, 14
    ang = np.arctan2(y - cy, x - cx)
    rel = (ang - t * 1.1) % (2 * math.pi)
    sector = math.pi / 3
    k = (rel / sector + 0.5).astype(int) % 6
    dd = np.abs(rel - np.round(rel / sector) * sector)
    beam = np.clip(1 - dd / 0.12, 0, 1) * 0.5
    arr += beam[..., None] * PRIDE[k].astype(np.float32)
    img = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(200, 200, 215))   # disco ball
    for i in range(-8, 9, 4):
        d.line([cx - 10, cy + i, cx + 10, cy + i], fill=(120, 120, 140))
    rs = random.Random(int(t * 10))
    for _ in range(40):                                                  # confetti
        cx2, cy2 = rs.random() * W, rs.random() * H * 0.84
        d.rectangle([cx2, cy2, cx2 + 2, cy2 + 1],
                    fill=tuple(int(v) for v in PRIDE[rs.randrange(6)]))
    d.rectangle([0, H * 0.84, W, H], fill=(60, 30, 70))
    cast = [DATES["Carlos"], DATES["Thabo"], DEWA, DATES["Brad"], DATES["Gunnar"]]
    for i, look in enumerate(cast):
        px = W * (0.12 + i * 0.19)
        _person(d, px, H * 0.86, 1.25 if look is not DEWA else 1.5, t + i * 0.4, look, "dance")
    s = 1 + 0.12 * math.sin(t * 6)
    _text(d, (W / 2, H * 0.32), "PARTY!", int(26 * s), _lerp((255, 80, 200), (80, 220, 255),
                                                            0.5 + 0.5 * math.sin(t * 3)), anchor="mm")
    return img


def _end(u, t, W, H):
    img = _sky(W, H, (90, 160, 235), (200, 230, 255))
    d = ImageDraw.Draw(img)
    px = -60 + (W + 120) * (u / 6)
    _plane(d, px, H * 0.62, 1.1)
    k = _back(_clamp(u / 0.8))
    _text(d, (W / 2, H * 0.17), "THE END", int(26 * k) + 1, (255, 255, 255), anchor="mm")
    _text(d, (W / 2, H * 0.85), "Dewa: flight attendant.", 12, (255, 255, 255), anchor="mm")
    _text(d, (W / 2, H * 0.93), "Legend.", 13, (255, 200, 60), anchor="mm")
    return img


def frame(t: float) -> Image.Image:
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    t = t % LOOP_SEC
    for name, a, b in SCENES:
        if a <= t < b:
            u = t - a
            extra = None
            if name == "airport":
                img = _airport(u, t, W, H)
            elif name == "cabin":
                img = _cabin(u, t, W, H)
            elif name.startswith("stop"):
                img, extra = _stop(int(name[4:]), u, t, W, H)
            elif name == "door":
                img = _door(u, t, W, H)
            elif name == "party":
                img = _party(u, t, W, H)
            else:
                img = _end(u, t, W, H)
            _caption(img, name, u, W, H, extra)
            fade = min(_clamp(u / FADE), _clamp((b - t) / FADE))
            if fade < 1:
                img = Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8), "RGB")
            return img
    return Image.new("RGB", (W, H))
