"""Max & Fionn: "In Arbeit" - a German comedy for the LED wall (~3 min loop, 192 x 256), drawn like the Ländle film.

frame(t) is a pure function of time t. Max (dark hair, black oversized shirt, black trousers) pours himself a
Prosecco in every scene, even at the wheel; Fionn is dirty blond. Running gags: "in Arbeit", "Recherche", Rolf
(the red Bauhaus trolley, who only exists once he has been liberated), the Moods, Monsti the monstera.

   0-  8  Titel
   8- 24  Colibri: "nur ein Getränk", the street vendor with the Moods
  24- 38  pumpkin farm at midnight
  38- 50  home with a metric tonne of pumpkins (pouring Prosecco at the wheel)
  50- 66  the terrace and the Kärcher
  66- 82  Fortunagasse: no parking, the open boot, the Ordnungsamt
  82-100  Bauhaus: 47 plants and the liberation of Rolf
 100-118  dinner at House Fortuna with a prince: a pallet of wine, delivered to the palace
 118-132  Lindenhof: wine and tapas by candlelight
 132-148  Hive
 148-160  Monsti
 160-174  Monday morning, credits
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw

import config
from display import laend_intro as li
from display.laend_intro import _c, _ease, _mix, _sky, _hills, _fachwerk, font
from display.lennart_film import person

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
LOOP_SEC = 174.0
SCENES = [("titel", 0, 8), ("colibri", 8, 24), ("kuerbis", 24, 38), ("heim", 38, 50), ("terrasse", 50, 66),
          ("parken", 66, 82), ("bauhaus", 82, 100), ("dinner", 100, 118), ("lindenhof", 118, 132),
          ("hive", 132, 148), ("monsti", 148, 160), ("montag", 160, 174)]
RED, BLUE, PUR, GRN = (176, 30, 40), (40, 44, 128), (124, 44, 124), (30, 104, 64)
PORSCHE = (122, 128, 140)

CAPS = {
    "titel": [(0.4, "Ein Film, der nie fertig wird.")],
    "colibri": [(0.4, "Colibri. 19 Uhr. Es sollte nur ein Getränk werden."), (9.0, "Es waren 47 Packungen Moods.")],
    "kuerbis": [(0.4, "Kürbisfarm. Mitternacht. Natürlich."), (9.5, "Die Vogelscheuche hat alles gesehen.")],
    "heim": [(0.4, "Heimfahrt. Prosecco einschenken geht auch bei 80."), (7.0, "Kein Fahrzeug wurde überladen. Fast.")],
    "terrasse": [(0.4, "Die Terrasse. Seit März in Arbeit."), (9.0, "Jetzt ist sie sauber. Und kleiner.")],
    "parken": [(0.4, "Fortunagasse. Hier darf man nicht parken."), (9.0, "Der Handwerker-Trick: offener Kofferraum.")],
    "bauhaus": [(0.4, "Bauhaus. Ein Einkauf in zwei Akten."), (7.0, "Akt zwei: die Befreiung von Rolf.")],
    "dinner": [(0.4, "Dinner im House Fortuna. Gast: ein Prinz."), (12.4, "Lieferung: Palast.")],
    "lindenhof": [(0.4, "Lindenhof. Kerzenlicht. Wein und Tapas.")],
    "hive": [(0.4, "Hive. Ein Türsteher mit Prinzipien."), (10.0, "Drinnen: Rolf tanzt.")],
    "monsti": [(0.4, "Haus Fortuna, Fortunagasse 24."), (6.0, "Monsti ist jetzt vier Meter.")],
    "montag": [(0.4, "Montag.")],
}
for _k, _v in CAPS.items():
    li.CAPTIONS["mx_" + _k] = _v


# ---------------------------------------------------------------- helpers ---
# Readability on the LED wall: nothing under 9 px, bold bubbles and captions, dark rims on the figures, no strobing.

def _text(d, xy, s, size, fill, stroke=2, anchor="mm", sc=(0, 0, 0)):
    li._text(d, xy, s, max(9, int(size)), fill, stroke=max(1, stroke), anchor=anchor, sc=sc)


BUBBLE_UP = 14                                                               # the figures are bigger: bubbles sit higher


def _say(d, x, y, txt, col, pop=1.0):
    """A speech bubble (10 px type, a thick rim) whose tail points down to (x, y - BUBBLE_UP)."""
    if not txt:
        return
    y = y - BUBBLE_UP
    f = font(10)
    lines = li._wrap(txt, 10, 150)
    wd = max(f.getlength(ln) for ln in lines) + 12
    hh = 13 * len(lines) + 6
    bx = min(max(x, wd / 2 + 3), W - wd / 2 - 3)
    top = y - hh * pop - 7
    d.rounded_rectangle([bx - wd / 2, top, bx + wd / 2, top + hh * pop], 5, fill=(255, 255, 255), outline=(20, 20, 30), width=2)
    d.polygon([(x - 4, top + hh * pop - 1), (x + 5, top + hh * pop - 1), (x, top + hh * pop + 8)], fill=(255, 255, 255), outline=(20, 20, 30))
    d.line([(x - 3, top + hh * pop - 1), (x + 4, top + hh * pop - 1)], fill=(255, 255, 255), width=2)
    if pop > 0.95:
        for i, ln in enumerate(lines):
            d.text((bx, top + 10 + i * 13), ln, font=f, fill=col, anchor="mm")


def _talk(d, u, items):
    for t0, t1, x, y, txt, col in items:
        if t0 <= u < t1:
            _say(d, x, y, txt, col, min(1.0, (u - t0) / 0.25))


def _caption(img, key, u):
    """The narrator line: 12 px, in a dark band at the bottom, typed out."""
    cur = None
    for start, text in li.CAPTIONS.get(key, []):
        if u >= start:
            cur = (start, text)
    if not cur:
        return
    start, text = cur
    lines = li._wrap(text, 12, W - 12)
    n = int((u - start) * 24) + 1
    shown, left = [], n
    for ln in lines:
        shown.append(ln[:max(0, left)])
        left -= len(ln) + 1
    lh = 16
    y0 = H - lh * len(lines) - 8
    arr = np.asarray(img, np.float32)
    arr[y0 - 5:] *= 0.22
    img.paste(Image.fromarray(arr.astype(np.uint8), "RGB"))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(shown):
        if ln:
            _text(d, (W / 2, y0 + i * lh + lh / 2), ln, 12, (255, 246, 224), stroke=1)


class _Safe:
    """ImageDraw that accepts boxes drawn right-to-left (mirrored vehicles)."""
    def __init__(self, d):
        self._d = d

    def __getattr__(self, n):
        return getattr(self._d, n)

    @staticmethod
    def _box(b):
        x0, y0, x1, y1 = b
        return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]

    def ellipse(self, b, *a, **k):
        self._d.ellipse(self._box(b), *a, **k)

    def rectangle(self, b, *a, **k):
        self._d.rectangle(self._box(b), *a, **k)

    def rounded_rectangle(self, b, *a, **k):
        self._d.rounded_rectangle(self._box(b), *a, **k)

    def arc(self, b, st, en, *a, **k):
        self._d.arc(self._box(b), st, en, *a, **k)


def _light(img, cx, cy, r, col, a=0.5):
    """A soft glow, added onto the picture."""
    x0, y0, x1, y1 = max(0, int(cx - r)), max(0, int(cy - r)), min(W, int(cx + r)), min(H, int(cy + r))
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    k = np.clip(1 - np.hypot(xx - cx, yy - cy) / r, 0, 1) ** 2 * a
    arr = np.asarray(img.crop((x0, y0, x1, y1)), np.float32) + k[..., None] * np.array(col, np.float32)
    img.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), (x0, y0))


def _cobbles(d, y0, y1, base=(112, 106, 102), seed=1):
    d.rectangle([0, y0, W, y1], fill=base)
    rs = random.Random(seed)
    rows = max(1, int((y1 - y0) / 6))
    for j in range(rows):
        y = y0 + j * 6 + 2
        sz = 10 + j * 0.8
        for i in range(-1, int(W / sz) + 2):
            x = i * sz + (sz / 2 if j % 2 else 0)
            v = rs.randrange(-6, 6)
            d.ellipse([x, y, x + sz - 2, y + 5], fill=(base[0] + v, base[1] + v, base[2] + v), outline=(base[0] - 12, base[1] - 12, base[2] - 10))


def _stars(d, n, t, ymax=120, seed=2):
    rs = random.Random(seed)
    for i in range(n):
        x, y = rs.randrange(W), rs.randrange(ymax)
        d.rectangle([x, y, x + 1, y + 1], fill=(230, 230, 230))               # steady stars: twinkling reads as flicker on an LED wall


def _persons(img, items, t):
    for (x, y, who, pose, kw) in items:
        person(img, x, y, kw.pop("s", 2.1), t, who, pose, kw.pop("ph", 0.0), kw.pop("flip", False), outline=True, **kw)


def _wheel(d, cx, cy, r, spin):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(16, 16, 20))
    d.ellipse([cx - r * 0.64, cy - r * 0.64, cx + r * 0.64, cy + r * 0.64], fill=(190, 194, 202))
    for k in range(5):
        a = spin + k * 1.2566
        d.line([(cx, cy), (cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62)], fill=(104, 108, 118), width=1)
    d.ellipse([cx - r * 0.2, cy - r * 0.2, cx + r * 0.2, cy + r * 0.2], fill=(60, 60, 68))
    d.arc([cx - r * 0.7, cy - r * 0.7, cx + r * 0.7, cy + r * 0.7], 20, 70, fill=(224, 30, 40), width=max(1, int(r * 0.28)))


def _porsche(d, x, base, s, t, boot=0.0, tools=0.0, face_left=False, sag=0.0, moving=0.0):
    """A grey Porsche SUV (Cayenne-style) from the side: sloping coupé roof, four-point LED headlights, the crest on the wing,
    red calipers, a full-width tail-light bar and PORSCHE along the sill. x = centre, base = ground, facing right unless face_left."""
    d = _Safe(d)
    sg = -1 if face_left else 1

    def P(px, py):
        return (x + px * s * sg, base + (py + sag) * s)

    body, dark, lite = PORSCHE, (78, 82, 92), (176, 182, 194)
    d.ellipse([*P(-42, -2), *P(44, 3)], fill=(0, 0, 0))
    spin = t * 10 * moving
    for wx in (-24, 26):
        _wheel(d, x + wx * s * sg, base - 8 * s, 8.2 * s, spin)
    d.polygon([P(-38, -7), P(-39, -20), P(-35, -29), P(-23, -34), P(-9, -41), P(10, -42), P(23, -33), P(34, -28), P(41, -24),
               P(43, -14), P(41, -6)], fill=body)                                                 # the body
    d.polygon([P(-38, -7), P(-39, -17), P(43, -16), P(41, -6)], fill=dark)                       # the dark sill
    d.line([P(-35, -26), P(30, -25)], fill=lite, width=1)                                         # shoulder line
    d.line([P(-23, -34), P(-9, -41), P(10, -42), P(23, -33)], fill=lite, width=1)                 # roof highlight
    d.line([P(-30, -37), P(0, -44.5), P(15, -44)], fill=(60, 64, 72), width=1)                   # roof rail
    d.polygon([P(-28, -31), P(-10, -39), P(9, -40), P(21, -32), P(-28, -31)], fill=(46, 70, 100))  # glass
    d.line([P(-6, -38), P(-3, -31)], fill=(150, 160, 176), width=1)
    d.line([P(4, -39), P(6, -31)], fill=body, width=2)
    d.polygon([P(-24, -32), P(-18, -36), P(-14, -36), P(-20, -32)], fill=(96, 126, 160))          # reflection
    for dx in (-13, 12):
        d.line([P(dx, -30), P(dx, -17)], fill=(70, 74, 84), width=1)                              # door cuts
    d.rectangle([*P(-12, -24), *P(-9, -23)], fill=lite)
    d.rectangle([*P(14, -24), *P(17, -23)], fill=lite)
    d.ellipse([*P(36, -26), *P(42, -19)], fill=(250, 246, 214))                                   # headlight
    for ox, oy in ((37.5, -24.5), (40, -24.5), (37.5, -21), (40, -21)):                           # the four-point DRL
        d.point(P(ox, oy), fill=(120, 150, 255))
    d.rectangle([*P(41, -15), *P(44, -9)], fill=(24, 24, 30))                                    # intake
    d.rectangle([*P(-40, -27), *P(-37, -17)], fill=(214, 24, 36))                                 # tail-light bar
    d.polygon([P(32, -21), P(35, -21), P(35, -17), P(33.5, -15.5), P(32, -17)], fill=(236, 200, 60))   # the crest on the wing
    d.rectangle([*P(33, -19), *P(34.4, -17.5)], fill=(190, 30, 40))
    d.text(P(2, -11), "PORSCHE", font=font(8), fill=(232, 234, 240), anchor="mm")
    if boot > 0:                                                                                   # the tailgate opens: dark boot, tools, hi-vis vest
        d.polygon([P(-37, -31), P(-24, -31), P(-24, -11), P(-37, -9)], fill=(12, 12, 16))
        if tools > 0:
            d.line([P(-35, -13), P(-26, -25)], fill=(250, 210, 40), width=max(1, int(1.6 * s)))       # spirit level
            d.rectangle([*P(-34, -24), *P(-29, -17)], fill=(206, 56, 40))                            # bucket
            d.rectangle([*P(-28, -20), *P(-24, -14)], fill=(30, 154, 84))                             # drill
            d.polygon([P(-31, -30), P(-26, -30), P(-27, -25), P(-30, -25)], fill=(255, 140, 20))      # hi-vis vest
        a = -boot * 1.95
        hx, hy = -37.0, -31.0
        vx, vy = -5.0, 22.0
        ex, ey = hx + vx * math.cos(a) - vy * math.sin(a), hy + vx * math.sin(a) + vy * math.cos(a)
        d.line([P(hx, hy), P(ex, ey)], fill=body, width=max(2, int(4 * s)))
        d.line([P(hx, hy), P(ex, ey)], fill=lite, width=1)


def _rolf(d, x, base, s, t, plants=0, shake=0.0):
    """Rolf: a red Bauhaus trolley basket on four little wheels. x = centre."""
    d = _Safe(d)
    sh = math.sin(t * 5) * shake
    red, hi = (214, 34, 40), (240, 110, 110)
    x0, x1, y0, y1 = x - 16 * s, x + 16 * s, base - 28 * s + sh, base - 8 * s + sh
    d.rectangle([x0, y0, x1, y1], outline=red, width=max(1, int(1.6 * s)))
    for i in range(1, 6):
        d.line([(x0 + i * 32 * s / 6, y0), (x0 + i * 32 * s / 6, y1)], fill=red, width=1)
    for i in range(1, 3):
        d.line([(x0, y0 + i * 20 * s / 3), (x1, y0 + i * 20 * s / 3)], fill=hi, width=1)
    d.line([(x1, y0), (x1 + 7 * s, y0 - 8 * s)], fill=red, width=max(1, int(2 * s)))             # the push handle
    d.line([(x1 + 7 * s, y0 - 8 * s), (x1 + 11 * s, y0 - 8 * s)], fill=(250, 250, 250), width=max(1, int(2 * s)))
    d.line([(x0, y1 + 2 * s), (x1, y1 + 2 * s)], fill=(90, 90, 96), width=1)
    rs = random.Random(7)
    for i in range(plants):
        px = x0 + 3 * s + (i % 7) * (30 * s / 7) + rs.random() * 2
        top = y0 - 4 * s - (i % 3) * 4 * s
        d.line([(px, y1 - 2 * s), (px, top + 2 * s)], fill=(40, 110, 50), width=max(1, int(1.4 * s)))
        d.ellipse([px - 4 * s, top - 3 * s, px + 4 * s, top + 3 * s], fill=[(64, 170, 76), (84, 196, 96), (44, 140, 62)][i % 3])
        if i % 4 == 0:
            d.ellipse([px - 1.4 * s, top - 5 * s, px + 1.4 * s, top - 2.6 * s], fill=(255, 110 + i * 9 % 100, 150))
    for wx in (x0 + 3 * s, x1 - 3 * s):
        d.ellipse([wx - 2.6 * s, base - 5.4 * s + sh, wx + 2.6 * s, base + sh], fill=(26, 26, 30))
        d.ellipse([wx - 1 * s, base - 3.4 * s + sh, wx + 1 * s, base - 1.4 * s + sh], fill=(150, 150, 156))


def _karcher(d, x, base, s, t):
    """A Kärcher pressure washer: yellow body, black frame and wheels, KÄRCHER on the front, a coiled hose."""
    d = _Safe(d)
    d.ellipse([x - 16 * s, base - 2 * s, x + 16 * s, base + 2 * s], fill=(0, 0, 0))
    d.line([(x - 10 * s, base - 30 * s), (x - 10 * s, base - 38 * s), (x + 10 * s, base - 38 * s), (x + 10 * s, base - 30 * s)], fill=(30, 30, 34), width=max(2, int(2.4 * s)))   # carrying frame
    d.rounded_rectangle([x - 14 * s, base - 31 * s, x + 14 * s, base - 5 * s], 3 * s, fill=(255, 204, 0), outline=(70, 56, 0))
    d.rectangle([x - 14 * s, base - 11 * s, x + 14 * s, base - 5 * s], fill=(34, 34, 38))
    d.rectangle([x - 12 * s, base - 28 * s, x + 12 * s, base - 19 * s], fill=(255, 224, 70))
    d.text((x, base - 24 * s), "KÄRCHER", font=font(9), fill=(20, 20, 24), anchor="mm")
    d.ellipse([x - 9 * s, base - 17 * s, x - 4 * s, base - 12 * s], fill=(34, 34, 38))                # the pressure dial
    d.line([(x - 6.5 * s, base - 16.6 * s), (x - 5.4 * s, base - 14.4 * s)], fill=(250, 60, 40), width=1)
    d.text((x + 6 * s, base - 14.5 * s), "MAX", font=font(8), fill=(220, 40, 30), anchor="mm")
    for wx in (x - 11 * s, x + 11 * s):
        d.ellipse([wx - 4 * s, base - 8 * s, wx + 4 * s, base], fill=(24, 24, 28))
        d.ellipse([wx - 1.6 * s, base - 5.6 * s, wx + 1.6 * s, base - 2.4 * s], fill=(120, 120, 126))
    for k in range(3):                                                                              # the coiled hose
        d.arc([x + 12 * s, base - 30 * s + k * 3 * s, x + 24 * s, base - 16 * s + k * 3 * s], 270, 90, fill=(30, 30, 34), width=max(1, int(1.6 * s)))


def _spray(d, gx, gy, tx, ty, t, n=26, col=(236, 248, 255)):
    """A steady water jet: droplets run along a curve, each at its own phase, so nothing jumps between frames."""
    for i in range(n):
        k = ((t * 1.1 + i / n) % 1.0)
        spread = (i % 5 - 2) * 1.4 * k
        x = gx + (tx - gx) * k
        y = gy + (ty - gy) * k - math.sin(k * math.pi) * 5 + spread
        r = 1.8 + 1.2 * k
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)


def _gummi(d, x, y, s, t):
    d.line([(x, y), (x + math.sin(t * 2) * 2, y - 16 * s)], fill=(86, 60, 34), width=max(1, int(2 * s)))
    for dx, dy, r in ((-6, -18, 7), (5, -22, 8), (0, -28, 7), (-3, -13, 6)):
        d.ellipse([x + (dx - r) * s * 0.5, y + (dy - r) * s * 0.5, x + (dx + r) * s * 0.5, y + (dy + r) * s * 0.5], fill=(50, 142, 66))


def _pumpkin(d, x, y, r):
    d.ellipse([x - r, y - r * 0.8, x + r, y + r * 0.8], fill=(236, 122, 28), outline=(150, 66, 16))
    for k in (-0.5, 0, 0.5):
        d.arc([x + k * r - r * 0.5, y - r * 0.8, x + k * r + r * 0.5, y + r * 0.8], 90, 270, fill=(180, 84, 20))
    d.line([(x, y - r * 0.8), (x + 1, y - r * 1.1)], fill=(60, 110, 40), width=2)


# ---------------------------------------------------------------- scenes ---

def _street_backdrop(img, d, t, night=True):
    top, bot = ((20, 34, 80), (240, 150, 110)) if night else ((130, 190, 244), (236, 232, 220))
    img.paste(_sky(top, bot, 150, mid=(150, 90, 130) if night else None), (0, 0))
    d = ImageDraw.Draw(img)
    walls = [(232, 214, 184), (206, 190, 150), (226, 196, 176), (214, 224, 196)]
    for i, (x, w, h) in enumerate(((-8, 54, 100), (42, 40, 80), (80, 38, 108), (116, 40, 86), (152, 50, 98))):
        _fachwerk(d, x, 150, w, h, _mix(walls[i % 4], (60, 50, 90), 0.4 if night else 0.0), (82, 54, 40), (140, 62, 54), lit=night)
    return d


def _titel(u, t):
    img = Image.new("RGB", (W, H))
    d = _street_backdrop(img, None, t)
    _cobbles(d, 150, H, seed=3)
    k = _ease(u / 1.2)
    _text(d, (W / 2, 28), "MAX", int(12 + 22 * k), (255, 236, 200), stroke=3)
    _text(d, (W / 2, 60), "& FIONN", int(12 + 18 * k), (255, 214, 120), stroke=3)
    _text(d, (W / 2, 88), "In Arbeit", int(8 + 10 * k), (255, 150, 130), stroke=2)
    px = -80 + (86 + 80) * _ease(u / 2.6)
    d = ImageDraw.Draw(img)
    _porsche(d, px, 198, 1.5, t, boot=_c((u - 3.0) / 0.9) * 0.95, tools=1.0 if u > 3.6 else 0.0, moving=1.0 if u < 2.8 else 0.0)
    _persons(img, [(158, 206, "X", "hold", {"item": "prosecco", "ph": 0.3}), (181, 206, "F", "stand", {"flip": True, "ph": 1.1})], t)
    d = ImageDraw.Draw(img)
    _talk(d, u, [(4.6, 7.6, 158, 140, "Prost, Fortunagasse!", RED)])
    return img


def _colibri(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((30, 22, 56), (96, 50, 76), 150), (0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 38, W, 150], fill=(74, 38, 54))                                                  # the bar's front
    for x in range(0, W, 16):
        d.line([(x, 38), (x, 150)], fill=(66, 32, 48))
    d.rectangle([0, 30, W, 42], fill=(120, 40, 50))
    for i in range(0, W, 12):
        d.polygon([(i, 42), (i + 12, 42), (i + 6, 52)], fill=(180, 60, 70) if (i // 12) % 2 else (240, 220, 200))
    glow = 0.6 + 0.4 * abs(math.sin(t * 2.2))
    _text(d, (W / 2, 70), "COLIBRI", 18, _mix((100, 30, 76), (255, 120, 196), glow), stroke=2)
    for wx in (10, 112):
        d.rectangle([wx, 84, wx + 70, 134], fill=(255, 196, 116), outline=(56, 28, 28), width=3)
        for k in range(4):
            d.ellipse([wx + 8 + k * 16, 100 + (k % 2) * 6, wx + 18 + k * 16, 110 + (k % 2) * 6], fill=(150, 80, 50))   # silhouettes
        d.line([(wx + 35, 84), (wx + 35, 134)], fill=(56, 28, 28), width=2)
    for i, x in enumerate(range(0, W + 8, 8)):                                                         # string lights
        y = 54 + 6 * math.sin(x / W * math.pi * 3)
        d.ellipse([x - 1.5, y, x + 1.5, y + 3], fill=(255, 214, 130))
    _cobbles(d, 150, H, base=(86, 80, 90), seed=4)
    _light(img, W / 2, 110, 120, (255, 160, 90), 0.22)
    d = ImageDraw.Draw(img)
    d.ellipse([54, 176, 140, 190], fill=(236, 226, 206), outline=(120, 100, 80))                       # the table
    d.line([(97, 190), (97, 206)], fill=(120, 120, 126), width=3)
    d.rectangle([94, 168, 100, 176], fill=(250, 240, 220))
    d.ellipse([93, 161 + math.sin(t * 3) * 0.6, 101, 170], fill=(255, 190, 70))                       # a candle
    n = min(47, int(max(0.0, u - 6.0) * 5.5))
    for i in range(min(16, n // 3)):                                                                    # the Moods pile up
        bx, by = 58 + (i % 8) * 10, 176 - (i // 8) * 5 - 3
        d.rectangle([bx, by, bx + 8, by + 4], fill=(72, 42, 92))
        d.rectangle([bx + 1, by + 1, bx + 7, by + 2], fill=(224, 192, 92))
    _persons(img, [(40, 208, "X", "hold", {"item": "prosecco", "ph": 0.3}), (154, 208, "F", "stand", {"flip": True, "ph": 1.0})], t)
    vx = 262 - _ease(min(1.0, max(0.0, (u - 3.0) / 3.2))) * 70
    _persons(img, [(vx, 208, "V", "hold", {"flip": True, "item": "tray"})], t)
    d = ImageDraw.Draw(img)
    _text(d, (W - 6, 14), f"Moods: {n}", 14, (255, 226, 130), stroke=2, anchor="rm")
    _talk(d, u, [(0.5, 3.0, 40, 148, "Nur ein Getränk.", RED), (3.0, 5.2, 154, 148, "Ich glaub dir kein Wort.", BLUE),
                 (5.6, 7.6, vx, 148, "Moods?", PUR), (7.6, 9.4, 40, 148, "Ja.", RED), (9.4, 11.2, vx, 148, "Wie viele?", PUR),
                 (11.2, 12.6, 40, 148, "Ja.", RED), (12.6, 15.0, 154, 148, "Max. Das sind 47 Packungen.", BLUE),
                 (15.0, 16.0, 40, 148, "Recherche.", RED)])
    return img


def _kuerbis(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((6, 8, 28), (40, 30, 66), 140), (0, 0))
    d = ImageDraw.Draw(img)
    _stars(d, 60, t, 110)
    d.ellipse([140, 18, 168, 46], fill=(246, 242, 208))
    d.ellipse([148, 24, 154, 30], fill=(226, 222, 186))
    _light(img, 154, 32, 70, (200, 200, 150), 0.25)
    d = ImageDraw.Draw(img)
    _hills(d, 112, 8, (22, 24, 44), 3)
    d.rectangle([14, 96, 62, 138], fill=(70, 30, 34))                                                    # the barn
    d.polygon([(8, 96), (38, 76), (68, 96)], fill=(54, 22, 28))
    d.rectangle([32, 108, 44, 138], fill=(255, 206, 110))
    d.rectangle([34, 110, 42, 138], fill=(230, 170, 80))
    d.rectangle([0, 138, W, H], fill=(36, 34, 30))
    rs = random.Random(11)
    for i in range(34):
        _pumpkin(d, rs.uniform(4, W - 4), rs.uniform(146, 214), rs.uniform(5, 9))
    sx = 100
    d.line([(sx, 120), (sx, 168)], fill=(110, 80, 44), width=3)                                           # the scarecrow
    d.line([(sx - 16, 134), (sx + 16, 134)], fill=(110, 80, 44), width=3)
    for dx in (-14, 14):
        d.line([(sx + dx, 134), (sx + dx + (3 if dx > 0 else -3), 142)], fill=(220, 190, 90), width=1)
    d.ellipse([sx - 7, 106, sx + 7, 120], fill=(226, 206, 130))
    d.polygon([(sx - 11, 108), (sx, 96), (sx + 11, 108)], fill=(122, 90, 44))
    d.rectangle([sx - 3, 110, sx - 1, 112], fill=(30, 24, 20))
    d.rectangle([sx + 1, 110, sx + 3, 112], fill=(30, 24, 20))
    fx = 56 + 20 * _ease(u / 4)
    bx = 236 - _ease(min(1.0, max(0.0, (u - 7.2) / 3.0))) * 100
    cone = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(cone).polygon([(fx + 20, 178), (fx + 120, 140), (fx + 120, 226)], fill=(255, 246, 180, 64))
    img.paste(cone, (0, 0), cone)
    _persons(img, [(24, 210, "X", "hold", {"item": "prosecco", "ph": 0.3}), (fx, 206, "F", "hold", {"ph": 1.0})]
             + ([(bx, 206, "B", "walk", {"flip": True, "item": "pitchfork"})] if u > 7.2 else []), t)
    d = ImageDraw.Draw(img)
    _talk(d, u, [(0.4, 2.8, fx, 150, "Max. Es ist Mitternacht.", BLUE), (2.8, 4.8, 24, 150, "Kürbissaison.", RED),
                 (4.8, 6.8, fx, 150, "Das heißt Erntedank.", BLUE), (6.8, 8.6, sx, 92, "Ich habe nichts gesehen.", (90, 60, 30)),
                 (8.6, 10.6, bx, 146, "WIR HABEN ZU!", PUR), (10.6, 12.6, 24, 150, "Dann nehmen wir, was draußen liegt.", RED),
                 (12.6, 14.0, bx, 146, "ALLES liegt draußen!", PUR)])
    return img


def _heim(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((8, 10, 32), (44, 34, 70), 150), (0, 0))
    d = ImageDraw.Draw(img)
    _stars(d, 50, t, 110)
    d.ellipse([24, 20, 46, 42], fill=(246, 242, 208))
    _hills(d, 124, 10, (22, 22, 44), 5)
    d.rectangle([0, 148, W, H], fill=(46, 46, 54))
    d.rectangle([0, 148, W, 152], fill=(70, 70, 78))
    for i in range(-1, 7):
        xx = (i * 48 - u * 70) % (W + 48) - 24
        d.rectangle([xx, 196, xx + 28, 200], fill=(226, 214, 140))
    cx = 96 + math.sin(t * 1.5) * 1.0
    sag = 2.6 + math.sin(t * 2.5) * 0.35
    _light(img, cx + 54, 186, 70, (255, 240, 180), 0.22)
    d = ImageDraw.Draw(img)
    _porsche(d, cx, 216, 1.45, t, sag=sag, moving=1.0)
    rs = random.Random(5)
    for i in range(52):                                                                                 # a metric tonne of pumpkins
        px = cx - 60 + rs.random() * 112
        py = 216 - (44 + rs.random() * 26 + (1 - abs(px - cx) / 60) * 18 + 0.0) * 1.45 + 12
        _pumpkin(d, px, py, 6.5 + rs.random() * 3.5)
    d.polygon([(cx - 14, 164), (cx + 26, 164), (cx + 24, 174), (cx - 12, 174)], fill=(46, 70, 100))   # people in the window
    d.ellipse([cx - 8, 158, cx + 2, 170], fill=(238, 198, 168))
    d.chord([cx - 9, 156, cx + 3, 168], 180, 360, fill=(30, 24, 26))
    d.ellipse([cx + 12, 158, cx + 22, 170], fill=(244, 206, 176))
    d.chord([cx + 11, 156, cx + 23, 168], 180, 360, fill=(172, 142, 88))
    fl = cx + 58
    d.polygon([(fl - 2, 160), (fl + 2, 160), (fl + 1, 167), (fl - 1, 167)], fill=(236, 240, 226))      # the flute out of the window
    d.line([(fl, 150), (fl, 158)], fill=(250, 214, 96), width=1)
    for k in range(3):
        d.point((fl + math.sin(t * 5 + k) * 1.3, 156 - ((t * 7 + k * 3) % 8)), fill=(255, 255, 220))
    _text(d, (W / 2, 20), "1000 kg", 16, (255, 196, 90), stroke=2)
    _talk(d, u, [(0.3, 2.6, cx + 10, 146, "Max! Beide Hände ans Lenkrad!", BLUE), (2.6, 4.4, cx - 6, 146, "Ich schenke nur ein.", RED),
                 (4.4, 6.2, cx + 10, 146, "Die Federung?", BLUE), (6.2, 8.0, cx - 6, 146, "Hat Nein gesagt.", RED),
                 (8.0, 10.2, cx + 10, 146, "Das Navi sagt: Bitte wenden.", BLUE), (10.2, 12.0, cx - 6, 146, "Das Navi hat Nein gesagt.", RED)])
    return img


def _terrasse(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((126, 186, 244), (222, 238, 252), 120), (0, 0))
    d = ImageDraw.Draw(img)
    _hills(d, 96, 8, (130, 168, 150), 6)
    d.rectangle([0, 52, W, 130], fill=(226, 184, 150))                                                   # Haus Fortuna's back
    for i in range(0, W, 12):
        d.line([(i, 52), (i, 130)], fill=(214, 172, 140))
    d.polygon([(-6, 52), (96, 22), (198, 52)], fill=(160, 70, 60))
    for wx in (14, 100, 148):
        d.rectangle([wx, 66, wx + 30, 96], fill=(255, 226, 150), outline=(110, 70, 50), width=2)
        d.rectangle([wx - 7, 66, wx - 1, 96], fill=(60, 120, 80))
        d.rectangle([wx + 31, 66, wx + 37, 96], fill=(60, 120, 80))
    d.rectangle([62, 82, 86, 130], fill=(120, 76, 50))
    clean = _c((u - 1.5) / 9.0)
    sink = _c((u - 9.0) / 3.0)
    base = _mix((92, 96, 84), (186, 188, 182), clean)
    d.rectangle([0, 130, W, H], fill=base)
    gro = _mix((54, 58, 50), (186, 188, 182), clean * (1 - sink))
    for j in range(7):
        yy = 130 + j * j * 1.6 + j * 5
        d.line([(0, yy), (W, yy)], fill=gro, width=2)
    for i in range(-6, 14):
        d.line([(i * 24 + 40, 130), (i * 30 - 20, H)], fill=gro, width=2)
    rs = random.Random(13)
    for _ in range(int(60 * (1 - clean))):                                                               # moss
        mx_, my_ = rs.uniform(0, W), rs.uniform(134, 214)
        d.ellipse([mx_, my_, mx_ + 4, my_ + 2], fill=(70, 112, 52))
    if sink > 0:                                                                                         # the terrace is now 3 cm lower
        d.polygon([(0, 214), (W, 214), (W, 214 + 8 * sink), (0, 214 + 8 * sink)], fill=(120, 150, 180))
    d.rectangle([150, 128, 192, 150], fill=(90, 150, 70))                                                # the neighbour's lawn, formerly
    for i in range(0, 42, 4):
        d.line([(150 + i, 150), (150 + i, 140)], fill=(60, 124, 50))
    _karcher(d, 30, 220, 1.5, t)
    d.rectangle([44, 190, 48, 202], fill=(44, 112, 74))                                                  # the Prosecco bottle on the Kärcher
    mxp, myp = 84, 212
    gx, gy = mxp + 19 * 1.9 + 2, myp - 22 * 1.9
    _persons(img, [(mxp, myp, "X", "hold", {"ph": 0.3}), (150, 214, "F", "point", {"flip": True, "ph": 1.0})], t)
    d = ImageDraw.Draw(img)
    d.line([(44, 200), (30, 176), (mxp + 4, 178), (gx - 8, gy)], fill=(30, 30, 34), width=2)            # the hose
    d.rectangle([gx - 9, gy - 2, gx + 3, gy + 2], fill=(255, 204, 0), outline=(60, 50, 0))                # the gun
    d.line([(gx + 3, gy), (gx + 22, gy + 4)], fill=(200, 200, 206), width=2)                              # the lance
    _spray(d, gx + 22, gy + 4, gx + 62 + math.sin(t * 5) * 8, 206, t)
    if 4.5 < u < 7.0:
        k = (u - 4.5) / 2.5
        px, py = 130 + k * 60, 200 - k * 90 + k * k * 120
        d.polygon([(px, py), (px + 10, py), (px + 8, py + 9), (px + 2, py + 9)], fill=(206, 104, 62))
        d.ellipse([px + 1, py - 4, px + 9, py + 1], fill=(220, 70, 110))
    if u > 9.0:                                                                                           # the neighbour's dog, soaked
        d.ellipse([156, 124, 180, 140], fill=(126, 104, 88))
        d.ellipse([174, 118, 188, 132], fill=(136, 112, 96))
        d.line([(160, 140), (160, 148)], fill=(100, 84, 70), width=2)
        d.line([(172, 140), (172, 148)], fill=(100, 84, 70), width=2)
    d.rectangle([40, 6, 152, 18], outline=(255, 255, 255))
    d.rectangle([41, 7, 41 + 110 * 0.12, 17], fill=(255, 190, 60))
    _text(d, (96, 12), "in Arbeit: 12 %", 10, (255, 255, 255), stroke=1)
    _talk(d, u, [(0.3, 2.4, 150, 148, "Mehr Druck!", BLUE), (2.4, 4.4, mxp, 148, "Ist schon Stufe MAX.", RED),
                 (4.4, 6.3, 150, 148, "Mehr!", BLUE), (6.3, 8.4, mxp, 148, "Es gibt kein mehr!", RED),
                 (8.4, 10.4, 172, 110, "Das war mein Rasen!", PUR), (10.4, 12.6, 150, 148, "Max. Die Fugen sind weg.", BLUE),
                 (12.6, 14.6, mxp, 148, "Minimalistisch.", RED), (14.6, 16.0, 150, 148, "Prosecco?", BLUE)])
    return img


def _parken(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((130, 190, 244), (236, 232, 220), 150), (0, 0))
    d = ImageDraw.Draw(img)
    walls = [(232, 206, 176), (210, 186, 156), (226, 190, 170)]
    for i, (x, w, h) in enumerate(((-10, 50, 112), (36, 40, 92), (118, 44, 100), (158, 44, 116))):
        _fachwerk(d, x, 156, w, h, walls[i % 3], (82, 54, 40), (150, 66, 58), lit=False)
    d.rectangle([76, 60, 116, 156], fill=(180, 160, 140))
    d.polygon([(72, 60), (96, 40), (120, 60)], fill=(150, 66, 58))
    d.rectangle([80, 70, 112, 84], fill=(250, 246, 232), outline=(110, 80, 60))
    _text(d, (96, 77), "Fortunagasse 24", 10, (50, 40, 36), stroke=0)
    _cobbles(d, 156, H, seed=5)
    d.rectangle([20, 104, 22, 156], fill=(120, 120, 126))                                                 # the signs
    d.ellipse([10, 82, 32, 104], fill=(40, 70, 190), outline=(255, 255, 255), width=2)
    d.line([(14, 100), (28, 86)], fill=(220, 40, 40), width=4)
    d.rectangle([172, 120, 174, 156], fill=(120, 120, 126))
    d.rectangle([160, 100, 186, 122], fill=(40, 90, 190))
    d.ellipse([168, 103, 178, 113], fill=(255, 255, 255))
    d.rectangle([168, 113, 178, 118], fill=(255, 255, 255))
    px = -80 + (82 + 80) * _ease(min(1.0, u / 3.0))
    boot = _c((u - 3.4) / 0.9) * 0.95
    _porsche(d, px, 208, 1.45, t, boot=boot, tools=_c((u - 4.4) / 2.0), moving=1.0 if u < 3.0 else 0.0)
    items = [(150, 210, "X", "hold", {"item": "prosecco", "flip": True, "ph": 0.3})]
    ax = 232 - _ease(min(1.0, max(0.0, (u - 4.0) / 3.0))) * 60
    if u > 4.0:
        items.append((ax, 210, "A", "hold" if u > 11.0 else "walk", {"flip": True, "item": "ticket" if u > 11.0 else None}))
    _persons(img, items, t)
    d = ImageDraw.Draw(img)
    if u > 2.6:                                                                                           # the hi-vis vest goes on
        d.rectangle([145, 184, 155, 198], fill=(255, 146, 20))
        d.rectangle([145, 190, 155, 192], fill=(240, 240, 120))
    _talk(d, u, [(0.5, 2.5, 150, 150, "Handwerker-Trick:", RED), (2.5, 4.8, 150, 150, "Kofferraum auf, Warnweste an.", RED),
                 (4.8, 6.8, ax, 150, "Hier ist Parkverbot.", PUR), (6.8, 8.4, 150, 150, "Ich arbeite.", RED),
                 (8.4, 9.8, ax, 150, "Woran?", PUR), (9.8, 11.6, 150, 150, "An der Terrasse. In Arbeit.", RED),
                 (11.6, 13.2, ax, 150, "Die ist seit März in Arbeit.", PUR), (13.2, 14.6, ax, 150, "Und das Prosecco?", PUR),
                 (14.6, 16.0, 150, 150, "Schmierstoff.", RED)])
    return img


def _bauhaus(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((140, 190, 240), (230, 236, 242), 130), (0, 0))
    d = ImageDraw.Draw(img)
    _hills(d, 90, 6, (140, 170, 150), 8)
    d.rectangle([0, 40, W, 132], fill=(206, 210, 214))                                                     # the store
    d.rectangle([0, 28, W, 56], fill=(220, 36, 40))
    _text(d, (96, 42), "BAUHAUS", 20, (255, 255, 255), stroke=2)
    d.rectangle([66, 80, 128, 132], fill=(160, 220, 240), outline=(90, 110, 130), width=2)               # the glass doors
    d.line([(97, 80), (97, 132)], fill=(90, 110, 130), width=2)
    d.rectangle([0, 132, W, H], fill=(104, 104, 110))
    for x in range(10, W, 40):
        d.rectangle([x, 150, x + 22, 152], fill=(240, 240, 240))
    for i in range(3):                                                                                     # the garden-centre tables
        tx = 4 + i * 20
        d.rectangle([tx, 112, tx + 17, 116], fill=(150, 110, 70))
        for k in range(3):
            d.polygon([(tx + k * 6, 112), (tx + k * 6 + 5, 112), (tx + k * 6 + 4, 105), (tx + k * 6 + 1, 105)], fill=(200, 100, 60))
            d.ellipse([tx + k * 6 - 1, 98 - (k % 2) * 2, tx + k * 6 + 6, 106], fill=[(70, 170, 80), (50, 140, 70), (90, 190, 100)][k % 3])
    n = int(_c(u / 6.0) * 47)
    _text(d, (W - 6, 12), f"Pflanzen: {n}/47", 12, (255, 255, 255), stroke=2, anchor="rm")
    sbx = 176                                                                                               # the cart bay: a red trolley waits
    if u < 6.5:
        fx = 40 + 30 * _ease(min(1.0, u / 4.0))
    elif u < 9.0:
        fx = 70 + (sbx - 82 - 70) * _ease((u - 6.5) / 2.5)
    else:
        fx = sbx - 12 - _ease(min(1.0, (u - 9.0) / 3.0)) * 24
    park = 70
    cx_car = 260 - _ease(min(1.0, max(0.0, (u - 11.0) / 2.6))) * (260 - park) if u < 16 else park - _ease((u - 16.0) / 2.0) * 230
    if u < 9.0:
        trolley_x = sbx
    elif u < 14.2:
        trolley_x = fx + 36
    else:
        trolley_x = cx_car + 82                                                                              # hitched on behind the car
    _rolf(d, trolley_x, 208, 1.35, t, plants=min(14, int(max(0.0, u - 12.0) * 4)) if u > 12 else 0, shake=0.0)
    if u > 11.0:
        _porsche(d, cx_car, 210, 1.4, t, face_left=True, moving=1.0 if (u < 13.6 or u > 16.0) else 0.0)
    kx = 82
    items = [(fx, 210, "F", "hold" if u < 6.5 else "walk", {"item": "plant" if u < 6.5 else None, "ph": 1.0})]
    if u < 12.4:
        items.append((20 + 20 * _ease(min(1.0, u / 3.0)), 210, "X", "hold", {"item": "prosecco", "ph": 0.3}))
    if 3.4 < u < 6.4 or u > 14.0:
        items.append((kx, 134, "K", "stand", {}))
    _persons(img, items, t)
    d = ImageDraw.Draw(img)
    _talk(d, u, [(0.3, 2.0, 70, 154, "Wir brauchen 47 Pflanzen.", BLUE), (2.0, 3.6, 28, 154, "Wir brauchen 48.", RED),
                 (3.6, 5.4, kx, 70, "1.280 Franken.", PUR), (5.4, 6.8, 28, 154, "Stimmt so.", RED),
                 (7.0, 8.8, fx, 154, "Der Korb ist so schön.", BLUE), (8.8, 10.2, 40, 154, "Nimm ihn.", RED),
                 (10.2, 11.6, fx, 154, "Das ist Diebstahl!", BLUE), (11.6, 13.0, 40, 154, "Das ist Recherche.", RED),
                 (13.0, 14.4, fx, 154, "Das ist MEIN Satz!", BLUE), (14.4, 15.8, kx, 70, "UND DER KORB?", PUR),
                 (15.8, 18.0, 40, 154, "Gehört zu den Pflanzen.", RED)])
    return img


def _dinner(u, t):
    if u >= 12.0:
        return _palast(u - 12.0, t)
    img = Image.new("RGB", (W, H), (84, 52, 38))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 170], fill=(236, 220, 188))
    for x in (0, 62, 130, 188):
        d.rectangle([x, 0, x + 4, 170], fill=(80, 50, 36))
    for y in (0, 56, 112):
        d.rectangle([0, y, W, y + 4], fill=(80, 50, 36))
    d.rectangle([14, 64, 54, 108], fill=(30, 40, 90), outline=(80, 50, 36), width=3)
    rs = random.Random(5)
    for i in range(14):
        d.point((16 + rs.randrange(36), 66 + rs.randrange(40)), fill=(240, 240, 255))
    d.line([(34, 64), (34, 108)], fill=(80, 50, 36), width=2)
    _text(d, (96, 24), "HOUSE FORTUNA", 11, (120, 70, 50), stroke=0)
    d.rectangle([0, 170, W, H], fill=(120, 76, 50))
    d.rectangle([20, 148, 172, 160], fill=(240, 236, 226))                                                 # the table
    d.rectangle([20, 160, 172, 190], fill=(250, 246, 236))
    for cxx in (50, 144):
        d.rectangle([cxx - 2, 128, cxx + 2, 148], fill=(250, 240, 220))
        d.ellipse([cxx - 3, 120 + math.sin(t * 3 + cxx) * 0.8, cxx + 3, 130], fill=(255, 190, 70))
    d.rectangle([92, 124, 98, 148], fill=(44, 90, 56))
    d.rectangle([94, 116, 96, 124], fill=(44, 90, 56))
    _light(img, 96, 130, 110, (255, 180, 90), 0.26)
    _persons(img, [(36, 214, "X", "hold", {"item": "prosecco", "ph": 0.3}), (96, 218, "P", "stand", {"ph": 0.6, "s": 2.0}),
                   (158, 214, "F", "stand", {"flip": True, "ph": 1.1})], t)
    d = ImageDraw.Draw(img)
    if u > 4.6:
        d.rectangle([66, 164, 126, 180], fill=(252, 248, 232), outline=(70, 44, 24))
        _text(d, (96, 172), "1 x PALETTE WEIN", 8, (170, 30, 30), stroke=0)
    _talk(d, u, [(0.3, 2.4, 96, 140, "Ein sehr guter Wein.", (30, 40, 110)), (2.4, 4.4, 36, 140, "Bestell eine Palette.", RED),
                 (4.4, 6.2, 96, 140, "Eine Flasche?", (30, 40, 110)), (6.2, 8.0, 36, 140, "PALETTE.", RED),
                 (8.0, 10.0, 96, 140, "Aber mein Keller...", (30, 40, 110)), (10.0, 12.0, 36, 140, "Dann bau einen.", RED)])
    return img


def _palast(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((126, 180, 240), (236, 226, 214), 140), (0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 140, W, H], fill=(90, 130, 70))
    d.rectangle([0, 188, W, H], fill=(150, 140, 120))
    d.rectangle([34, 70, 158, 150], fill=(226, 212, 186))                                                  # the palace
    for tx in (14, 142):
        d.rectangle([tx, 50, tx + 36, 150], fill=(214, 198, 172))
        d.polygon([(tx - 4, 50), (tx + 18, 28), (tx + 40, 50)], fill=(60, 96, 130))
        d.rectangle([tx + 14, 70, tx + 22, 86], fill=(90, 100, 130))
    d.polygon([(60, 70), (96, 44), (132, 70)], fill=(60, 96, 130))
    for k in range(3):                                                                                     # the Belgian flag: black, yellow, red
        d.rectangle([88 + k * 5, 24, 93 + k * 5, 42], fill=[(20, 20, 24), (250, 210, 40), (210, 40, 50)][k])
    d.line([(88, 24), (88, 46)], fill=(90, 90, 96), width=1)
    for wx in range(44, 150, 22):
        d.rectangle([wx, 84, wx + 10, 104], fill=(120, 140, 180))
    d.rectangle([84, 112, 108, 150], fill=(100, 66, 44))
    d.arc([84, 104, 108, 120], 180, 360, fill=(100, 66, 44), width=3)
    _text(d, (96, 18), "PALAST", 10, (255, 236, 160), stroke=2)
    tx = 270 - _ease(min(1.0, u / 3.0)) * 150
    d.rectangle([tx, 168, tx + 80, 200], fill=(244, 244, 244), outline=(70, 70, 70))
    d.rectangle([tx - 28, 182, tx, 200], fill=(230, 110, 40))
    d.rectangle([tx - 24, 174, tx - 6, 184], fill=(150, 200, 230))
    for i in range(5):
        for j in range(2):
            d.rectangle([tx + 4 + i * 15, 171 + j * 13, tx + 17 + i * 15, 182 + j * 13], fill=(150, 40, 70), outline=(100, 20, 40))
            d.ellipse([tx + 8 + i * 15, 174 + j * 13, tx + 12 + i * 15, 178 + j * 13], fill=(60, 120, 80))
    for wx in (tx - 18, tx + 56):
        d.ellipse([wx - 7, 194, wx + 7, 208], fill=(20, 20, 24))
        d.ellipse([wx - 3, 198, wx + 3, 204], fill=(150, 150, 156))
    _text(d, (tx + 40, 160), "PALETTE", 9, (170, 30, 40), stroke=1)
    px = 150 - 0 if u < 2 else 150
    _persons(img, [(60, 214, "A", "stand", {"ph": 0.4}), (px, 216, "P", "hold", {"flip": True, "ph": 0.9}),
                   (20, 214, "X", "hold", {"item": "prosecco", "ph": 0.3})], t)
    d = ImageDraw.Draw(img)
    _talk(d, u, [(2.2, 4.2, 60, 156, "Wer hat DAS bestellt?", PUR), (4.2, 5.8, px, 156, "...Ich.", (30, 40, 110))])
    if u > 4.4:
        d.polygon([(px - 8, 176), (px - 6, 170), (px - 2, 174), (px, 169), (px + 2, 174), (px + 6, 170), (px + 8, 176)], fill=(250, 200, 40))
        d.line([(24, 186), (px - 6, 176)], fill=(250, 214, 96), width=1)                                  # Max pours Prosecco into the crown
    _talk(d, u, [(5.8, 6.0, 20, 156, "Prost, Majestät.", RED)])
    return img


def _lindenhof(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((12, 14, 44), (64, 36, 74), 130), (0, 0))
    d = ImageDraw.Draw(img)
    _stars(d, 70, t, 90)
    d.ellipse([148, 16, 168, 36], fill=(246, 242, 208))
    hz = 120
    for i in range(18):                                                                                    # the old town across the Limmat
        bx = i * 11
        bh = 14 + (i * 31 % 21)
        d.rectangle([bx, hz - bh, bx + 11, hz], fill=(38, 32, 54))
        for wy in range(hz - bh + 3, hz - 2, 6):
            if (i + wy) % 3 == 0:
                d.rectangle([bx + 3, wy, bx + 5, wy + 2], fill=(255, 210, 120))
    for gx, col in ((40, (60, 54, 80)), (62, (60, 54, 80))):                                              # the Grossmünster
        d.rectangle([gx, hz - 58, gx + 12, hz], fill=col)
        d.polygon([(gx - 1, hz - 58), (gx + 6, hz - 74), (gx + 13, hz - 58)], fill=(70, 100, 100))
    d.rectangle([108, hz - 40, 118, hz], fill=(60, 54, 80))                                                # the Fraumünster spire
    d.polygon([(107, hz - 40), (113, hz - 76), (119, hz - 40)], fill=(60, 120, 104))
    d.rectangle([150, hz - 34, 160, hz], fill=(60, 54, 80))
    d.ellipse([150, hz - 32, 160, hz - 22], fill=(236, 226, 190))                                          # St. Peter's clock
    for i in range(28):                                                                                    # the river
        yy = hz + 2 + i * 2
        d.line([(0, yy), (W, yy)], fill=(20 + i, 22 + i // 2, 56 + i), width=1)
        d.line([(20 + (i * 23) % 160, yy), (28 + (i * 23) % 160 + math.sin(t * 3 + i) * 3, yy)], fill=(255, 200, 120), width=1)
    d.polygon([(0, 150), (W, 150), (W, H), (0, H)], fill=(52, 66, 44))
    d.rectangle([0, 150, W, 156], fill=(150, 146, 140))                                                    # the balustrade
    for x in range(2, W, 10):
        d.rectangle([x, 156, x + 4, 166], fill=(130, 126, 120))
    for tx in (20, 176):                                                                                   # lindens with lights
        d.rectangle([tx - 3, 70, tx + 3, 150], fill=(70, 48, 32))
        d.ellipse([tx - 30, 20, tx + 30, 84], fill=(58, 112, 56))
        for i in range(10):
            d.ellipse([tx - 24 + (i * 13) % 48, 30 + (i * 9) % 44, tx - 21 + (i * 13) % 48, 33 + (i * 9) % 44], fill=(255, 222, 140))
    d.rectangle([34, 186, 160, 222], fill=(176, 62, 72))                                                   # the blanket
    d.rectangle([34, 186, 160, 190], fill=(236, 196, 196))
    for cxx in (62, 132):
        d.rectangle([cxx - 2, 176, cxx + 2, 190], fill=(250, 240, 220))
        fl = 7 + math.sin(t * 3 + cxx) * 1.3
        d.ellipse([cxx - 3, 176 - fl, cxx + 3, 178], fill=(255, 190, 70))
        _light(img, cxx, 176, 40, (255, 170, 60), 0.3)
        d = ImageDraw.Draw(img)
    d.ellipse([84, 196, 112, 206], fill=(240, 236, 224))                                                   # the tapas plate: three olives
    for ox in (-7, 0, 7):
        d.ellipse([98 + ox - 3, 198, 98 + ox + 3, 203], fill=(70, 80, 36))
    if 9.8 < u < 11.6:                                                                                     # a pigeon steals one
        px = 150 - (u - 9.8) * 40
        d.ellipse([px, 192, px + 12, 202], fill=(150, 150, 160))
        d.ellipse([px - 4, 190, px + 2, 196], fill=(130, 130, 140))
        d.polygon([(px - 4, 192), (px - 8, 193), (px - 4, 194)], fill=(230, 180, 60))
    _persons(img, [(50, 212, "X", "sit", {"item": "prosecco", "ph": 0.3, "mood": "smile"}), (144, 212, "F", "sit", {"flip": True, "ph": 1.1, "mood": "smile"})], t * 0.4)
    d = ImageDraw.Draw(img)
    if u > 11.6:
        _text(d, (96, 100), "CHF 80", 16, (255, 214, 120), stroke=2)
    _talk(d, u, [(0.3, 2.4, 50, 156, "Wie romantisch.", RED), (2.4, 4.4, 144, 156, "Wir sitzen auf einem Felsen.", BLUE),
                 (4.4, 6.2, 50, 156, "Mit Kerzen.", RED), (6.2, 8.0, 144, 156, "Das sind drei Oliven.", BLUE),
                 (8.0, 9.8, 50, 156, "Tapas.", RED), (9.8, 11.6, 100, 176, "Gurr.", (110, 110, 120)),
                 (11.6, 13.0, 144, 156, "Das war eine Olive.", BLUE), (13.0, 14.0, 50, 156, "Stimmt so.", RED)])
    return img


def _hive(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((10, 6, 26), (36, 12, 56), H), (0, 0))
    d = ImageDraw.Draw(img)
    inside = u >= 10.0
    r = 9
    for row in range(8):
        for col in range(12):                                                                              # honeycomb
            cx, cy = col * r * 1.8 + (r * 0.9 if row % 2 else 0), 12 + row * r * 1.55
            pts = [(cx + r * 0.95 * math.cos(math.radians(60 * k + 30)), cy + r * 0.95 * math.sin(math.radians(60 * k + 30))) for k in range(6)]
            d.polygon(pts, fill=_mix((34, 22, 8), (110, 74, 14), 0.5 + 0.5 * math.sin(t * 0.8 + col * 0.7 + row * 0.5)), outline=(150, 100, 20))
    _text(d, (W / 2, 20), "HIVE", 28, (255, 200, 50), stroke=2)
    if not inside:
        d.rectangle([0, 150, W, H], fill=(40, 38, 46))
        d.rectangle([60, 60, 132, 150], fill=(20, 16, 28), outline=(255, 190, 40), width=2)               # the door
        for k in range(9):
            d.ellipse([8 + k * 20, 140 - (k % 3) * 3, 18 + k * 20, 150], fill=(60, 56, 70)) if k not in (3, 4, 5) else None
        _persons(img, [(116, 214, "M", "stand", {"flip": True}), (150, 210, "F", "cheer", {"flip": True, "ph": 1.0}),
                       (26, 214, "X", "hold", {"item": "prosecco", "ph": 0.3})], t)
        d = ImageDraw.Draw(img)
        _rolf(d, 80, 214, 1.5, t, plants=4)
        _talk(d, u, [(0.3, 2.4, 116, 152, "Der Korb kommt nicht rein.", PUR), (2.4, 4.4, 150, 152, "Er ist auf der Liste.", BLUE),
                     (4.4, 6.2, 116, 152, "Auf welcher?", PUR), (6.2, 8.0, 26, 152, "Rolf.", RED), (8.0, 10.0, 116, 152, "...Rolf darf rein.", PUR)])
    else:
        d.rectangle([0, 150, W, H], fill=(34, 20, 44))
        for i in range(10):                                                   # slow wide beams instead of many thin fast lines
            a = t * 0.5 + i * 0.63
            c = [(255, 60, 140), (80, 200, 255), (255, 210, 70)][i % 3]
            d.polygon([(W / 2, 60), (W / 2 + math.cos(a) * 170 - 8, 60 + abs(math.sin(a)) * 170), (W / 2 + math.cos(a) * 170 + 8, 60 + abs(math.sin(a)) * 170)], fill=_mix(c, (14, 8, 30), 0.62))
        d.ellipse([W / 2 - 12, 46, W / 2 + 12, 70], fill=(200, 204, 220))                                  # the disco ball
        for k in range(8):
            d.line([(W / 2 - 12 + k * 3, 46), (W / 2 - 12 + k * 3, 70)], fill=(120, 124, 140), width=1)
        _persons(img, [(40, 214, "X", "hold", {"item": "prosecco", "ph": 0.3}), (150, 214, "F", "cheer", {"flip": True, "ph": 1.0})], t)
        d = ImageDraw.Draw(img)
        _gummi(d, 176, 214, 1.4, t)
        _rolf(d, 96 + math.sin(t * 5) * 4, 214 + abs(math.sin(t * 5)) * -3, 1.5, t, plants=4)
        clock = "02:00" if u < 13.0 else "06:00"
        _text(d, (W - 6, 14), clock, 16, (120, 255, 140), stroke=2, anchor="rm")
        _talk(d, u, [(10.4, 12.6, 150, 150, "Nur noch ein Lied.", BLUE), (12.6, 14.4, 40, 150, "Nur noch ein Prosecco.", RED),
                     (14.4, 16.0, 96, 150, "*klapper*", (150, 30, 40))])
    return img


def _monsti(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((255, 205, 150), (255, 235, 195), 150), (0, 0))
    d = ImageDraw.Draw(img)
    for nx, col in ((-14, (206, 170, 140)), (150, (196, 160, 150))):
        d.rectangle([nx, 40, nx + 56, 170], fill=col)
        d.polygon([(nx - 3, 40), (nx + 28, 22), (nx + 59, 40)], fill=(150, 80, 70))
    d.rectangle([30, 28, 162, 170], fill=(226, 184, 150))                                                  # Haus Fortuna: old, narrow, tall
    for i in range(0, 132, 12):
        d.line([(30 + i, 28), (30 + i, 170)], fill=(214, 172, 140))
    d.polygon([(22, 28), (96, 4), (170, 28)], fill=(160, 70, 60))
    d.rectangle([54, 8, 138, 22], fill=(240, 226, 196))
    _text(d, (96, 15), "FORTUNAGASSE 24", 10, (90, 50, 40), stroke=0)
    for wx, wy in ((38, 36), (118, 36), (38, 120)):
        d.rectangle([wx, wy, wx + 32, wy + 30], fill=(255, 220, 140), outline=(110, 70, 50))
        d.rectangle([wx - 8, wy, wx - 1, wy + 30], fill=(60, 120, 80))
        d.rectangle([wx + 33, wy, wx + 40, wy + 30], fill=(60, 120, 80))
    fx, fy = 78, 76                                                                                          # Monsti's window, first floor
    d.rectangle([fx - 8, fy, fx - 1, fy + 34], fill=(60, 120, 80))
    d.rectangle([fx + 41, fy, fx + 48, fy + 34], fill=(60, 120, 80))
    d.rectangle([fx, fy, fx + 40, fy + 34], fill=(60, 50, 60), outline=(110, 70, 50), width=2)
    d.polygon([(fx + 10, fy + 34), (fx + 30, fy + 34), (fx + 27, fy + 44), (fx + 13, fy + 44)], fill=(200, 100, 60))
    _cobbles(d, 170, H, base=(112, 108, 104), seed=6)
    d.rectangle([84, 134, 112, 170], fill=(120, 76, 50))
    d.arc([84, 124, 112, 144], 180, 360, fill=(120, 76, 50), width=3)
    d.rectangle([0, 150, 24, 170], fill=(150, 146, 140))                                                   # the Lindenhof wall, opposite
    d.ellipse([-10, 96, 34, 150], fill=(90, 150, 70))
    grow = _c(u / 6.0)
    n = int(2 + grow * 20)
    sw = math.sin(t * 1.4) * 2
    pts = [(fx + 20, fy + 34)]
    for i in range(n):
        k = i / 20.0
        pts.append((fx + 20 + math.sin(k * 5.0) * 26 + sw * k, fy + 40 + i * 4.3))
    for a, b in zip(pts, pts[1:]):
        d.line([a, b], fill=(40, 100, 50), width=3)
    for i, (lx, ly) in enumerate(pts[1:]):
        r = 11 - i * 0.18
        side = 1 if i % 2 == 0 else -1
        cx, cy = lx + side * (r + 2), ly
        d.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], fill=(34 + (i * 7) % 30, 130 + (i * 11) % 40, 60), outline=(20, 80, 40))
        for hx in (-0.5, 0.0, 0.5):
            d.ellipse([cx + hx * r - 1.5, cy - 2, cx + hx * r + 1.5, cy + 3], fill=(226, 184, 150))
        d.line([(lx, ly), (cx, cy)], fill=(40, 100, 50), width=1)
    _text(d, (fx + 20, fy - 10), "Monsti", 13, (190, 255, 200), stroke=2)
    if u > 6.2:                                                                                              # Monsti takes the Prosecco
        lx, ly = pts[-1]
        d.line([(lx, ly), (100, 200)], fill=(40, 100, 50), width=2)
        d.ellipse([92, 196, 108, 204], fill=(54, 150, 70))
    _persons(img, [(60, 212, "X", "hold", {"item": "prosecco", "ph": 0.3}), (140, 212, "F", "wave", {"flip": True, "ph": 1.0})], t)
    d = ImageDraw.Draw(img)
    _talk(d, u, [(0.3, 2.4, 140, 150, "Monsti hat Hunger.", BLUE), (2.4, 4.4, 60, 150, "Gib ihr Prosecco.", RED),
                 (4.4, 6.2, 140, 150, "Nein!", BLUE), (6.2, 8.2, 100, 188, "Danke.", (30, 110, 60)),
                 (8.2, 10.2, 60, 150, "Ich sag ja: Recherche.", RED), (10.2, 12.0, 170, 76, "Ihre Pflanze ist in meinem Wohnzimmer!", PUR)])
    return img


def _montag(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((255, 218, 160), (255, 240, 205), 150), (0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([140, 20, 168, 48], fill=(255, 245, 190))
    _light(img, 154, 34, 80, (255, 220, 120), 0.35)
    d = ImageDraw.Draw(img)
    _hills(d, 100, 8, (150, 190, 160), 9)
    d.rectangle([0, 130, W, H], fill=(160, 164, 158))
    for j in range(7):
        d.line([(0, 134 + j * 14), (W, 134 + j * 14)], fill=(176, 178, 172), width=2)
    d.polygon([(10, 200), (180, 200), (180, 212), (10, 212)], fill=(124, 156, 186))                          # the puddle: the terrace is lower
    _karcher(d, 164, 222, 1.2, t)
    _rolf(d, 112, 214, 1.5, t, plants=12)
    _pumpkin(d, 70, 218, 9)
    _pumpkin(d, 52, 222, 7)
    for i in range(3):
        d.rectangle([8 + i * 16, 222, 22 + i * 16, 230], fill=(72, 42, 92))
        d.rectangle([9 + i * 16, 224, 21 + i * 16, 226], fill=(224, 192, 92))
    _persons(img, [(30, 214, "X", "hold", {"item": "prosecco", "ph": 0.3}), (144, 214, "F", "stand", {"flip": True, "ph": 1.0})], t)
    d = ImageDraw.Draw(img)
    if u < 7.0:
        _talk(d, u, [(0.3, 2.4, 30, 150, "Wie spät ist es?", RED), (2.4, 4.6, 144, 150, "Die Terrasse ist noch in Arbeit.", BLUE),
                     (4.6, 7.0, 30, 150, "Montag.", RED)])
    else:
        k = _ease(min(1.0, (u - 7.0) / 0.8))
        _text(d, (W / 2, 50), "IN ARBEIT", int(10 + 18 * k), (70, 44, 30), stroke=3, sc=(255, 240, 210))
        _text(d, (W / 2, 76), "Max & Fionn", 12, (120, 70, 40), stroke=2, sc=(255, 240, 210))
        yy = 98
        for i, ln in enumerate(("Kein Prosecco wurde während der Fahrt getrunken. (Eingeschenkt schon.)",
                                "Rolf wurde nicht gestohlen, nur befreit.",
                                "Alle Ähnlichkeiten mit dem Ordnungsamt sind zufällig.")):
            if u > 8.0 + i * 1.6:
                for wl in li._wrap(ln, 8, 176):
                    _text(d, (W / 2, yy), wl, 8, (90, 56, 38), stroke=1, sc=(255, 244, 224))
                    yy += 11
                yy += 4
    return img


SCENE_FN = {"titel": _titel, "colibri": _colibri, "kuerbis": _kuerbis, "heim": _heim, "terrasse": _terrasse,
            "parken": _parken, "bauhaus": _bauhaus, "dinner": _dinner, "lindenhof": _lindenhof, "hive": _hive,
            "monsti": _monsti, "montag": _montag}


def _grade(img):
    """Lift the shadows and open the midtones so dark scenes (night, club) stay readable on the LEDs."""
    a = np.asarray(img, np.float32) / 255.0
    a = np.power(a, 0.82)
    a = 0.07 + a * 0.93
    lum = a.mean(axis=2, keepdims=True)
    a = np.clip(lum + (a - lum) * 1.12, 0, 1)
    return Image.fromarray((a * 255).astype(np.uint8), "RGB")


def _scene_at(t):
    for name, a, b in SCENES:
        if a <= t < b:
            u = t - a
            img = SCENE_FN[name](u, t)
            _caption(img, "mx_" + name, u)
            fade = min(_c(u / 0.4), _c((b - t) / 0.4))
            if fade < 1:
                img = Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8), "RGB")
            return name, img
    return None, Image.new("RGB", (W, H))


def frame(t: float) -> Image.Image:
    t = t % LOOP_SEC
    name, img = _scene_at(t)
    pname, prev = _scene_at(t - 0.04) if t >= 0.04 else (None, None)
    if pname == name:                                                       # 25 % of the previous frame: fine detail does not shimmer
        img = Image.blend(img, prev, 0.25)
    return _grade(img)


def thumb() -> Image.Image:
    return frame(5.0)
