"""Max & Fionn: "In Arbeit" - a short German comedy for the LED wall (~2 min loop, 192 x 256).

frame(t) is a pure function of time t.

   0-8    Titel: der graue Porsche SUV, Kofferraum offen, Werkzeug drin, Rolf hinten dran
   8-24   Colibri: "nur ein Getränk", Moods (Zigarillos) in Unmengen
  24-38   Kürbisfarm um Mitternacht
  38-50   Heimfahrt mit einer metrischen Tonne Kürbisse
  50-66   die Terrasse, der Hochdruckreiniger, "in Arbeit"
  66-82   Fortunagasse: Parkverbot, offener Kofferraum, Handwerker-Trick
  82-100  Bauhaus: 47 Pflanzen, der Rolli-Korb Rolf wird Anhänger
 100-118  Dinner im House Fortuna mit dem Prinzen von Belgien: eine Palette Wein
 118-132  Lindenhof: Wein und Tapas bei Kerzenlicht
 132-148  Hive
 148-160  Monsti, die Monstera, wächst aus dem Fenster im ersten Stock
 160-174  Montagmorgen, Abspann

Max: dunkle Haare, schwarzes Oversize-Shirt, schwarze Hose. Fionn: dunkelblond.
Every person, joke and place in here is a friend's inside joke; keep it kind.
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw

import config
from display import text_renderer as tr

LOOP_SEC = 174.0
SCENES = [("titel", 0, 8), ("colibri", 8, 24), ("kuerbis", 24, 38), ("heim", 38, 50), ("terrasse", 50, 66),
          ("parken", 66, 82), ("bauhaus", 82, 100), ("dinner", 100, 118), ("lindenhof", 118, 132), ("hive", 132, 148),
          ("monsti", 148, 160), ("montag", 160, 174)]
CAPTIONS = {
    "titel": [(0.4, "MAX & FIONN präsentieren:"), (4.2, "'Das war so nicht geplant.'")],
    "colibri": [(0.3, "19 Uhr. Vor dem Colibri. Max: 'Nur ein Getränk.'"),
                (4.6, "Ein Verkäufer von der Straße: 'Moods?'"),
                (7.6, "Max: 'Ja.' \u2013 'Wie viele?' \u2013 'Ja.'"),
                (12.5, "Fionn: 'Das sind schon 40.' Max: 'Dann nehmen wir den Rest auch.'")],
    "kuerbis": [(0.3, "Mitternacht. Kürbisfarm."),
                (3.6, "Fionn: 'Max hat gesagt, es sei Erntezeit.' Max: 'Ich sagte Erntedank.'"),
                (8.6, "Bauer: 'Wir haben seit 18 Uhr zu.' Max: 'Wir sind nur am Kürbis.'")],
    "heim": [(0.3, "Heimfahrt. Im Kofferraum: eine metrische Tonne Kürbisse."),
             (4.6, "Fionn: 'Die Federung?' Max: 'Hat Nein gesagt.'"),
             (8.4, "Rolf zieht auch noch 200 kg. Und den Kürbis auf dem Beifahrersitz.")],
    "dinner": [(0.3, "Dinner im House Fortuna. Gast: der Prinz von Belgien."),
               (4.4, "Max: 'Der Wein ist gut. Bestell eine Palette.' Prinz: 'Eine Flasche?'"),
               (9.0, "Max: 'Palette.' Der Prinz: 'Na gut\u2026'"),
               (13.2, "Lieferung: Palast. Butler: 'Wer hat das bestellt?' Prinz: '\u2026Ich.'")],
    "terrasse": [(0.3, "Fionn: 'Mehr Druck!' Max: 'Ist schon Stufe MAX.'"),
                 (5.0, "Moos weg. Fugen weg. Farbe weg."),
                 (9.0, "Die Terrasse ist jetzt: sauber, 3 cm tiefer und nass beim Nachbarn."),
                 (13.0, "Status: in Arbeit.")],
    "parken": [(0.3, "Fortunagasse 24. Parkverbot."),
               (3.6, "Kofferraum auf, Werkzeug rein, Warnweste an."),
               (7.6, "Max: 'Ich bin Handwerker.' Ordnungsamt: 'Und was machen Sie hier?'"),
               (12.4, "Max: 'Terrasse. In Arbeit.' Der Zettel kommt trotzdem.")],
    "bauhaus": [(0.3, "Bauhaus. 47 Pflanzen für die Terrasse."),
                (4.3, "Fionn: 'Der Korb wollte mit.' Kassiererin: 'Und der Korb?'"),
                (9.0, "Max: 'Gehört zu den Pflanzen.'"),
                (12.6, "Der Porsche zieht bis 2,5 Tonnen. Der Korb hat Angst.")],
    "lindenhof": [(0.3, "Lindenhof. Kerzenlicht. Wein und Tapas."),
                  (4.2, "Max: 'Das ist romantisch.' Fionn: 'Das ist ein Picknick.'"),
                  (8.4, "Max: 'Mit Kerzen.' Tapas: 3 Oliven. Rechnung: 80 Franken.")],
    "monsti": [(0.3, "Fionns Monstera heißt Monsti."),
               (3.6, "Haus Fortuna: ein altes Haus in der Fortunagasse 24, gegenüber der Lindenhof. Monsti wächst aus dem Fenster im ersten Stock."),
               (7.6, "Max: 'Wir hätten keine 47 Pflanzen kaufen müssen.' Fionn: 'Monsti ist beleidigt.'")],
    "hive": [(0.3, "23:30 Uhr. Hive."),
             (3.4, "Türsteher: 'Der Korb kommt nicht rein.' Fionn: 'Er hat eine Liste.'"),
             (8.4, "02:00 Uhr: 'Nur noch ein Lied.'"),
             (11.8, "06:00 Uhr: 'Nur noch ein Lied.'")],
    "montag": [(0.3, "Montag. Max: 'Wie spät ist es?'"),
               (3.4, "Fionn: 'Die Terrasse ist immer noch in Arbeit.'"),
               (8.0, "Fortsetzung folgt, wenn die Terrasse fertig ist. (Nie.)")],
}
FADE = 0.4

SKIN = (236, 196, 166)
MAX_HAIR, MAX_BLACK = (28, 22, 24), (22, 22, 26)
FIONN_HAIR, FIONN_SHIRT, FIONN_JEANS = (176, 146, 92), (88, 150, 190), (50, 68, 112)
PORSCHE = (122, 128, 138)
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
    return Image.fromarray(np.repeat(a * (1 - k) + b * k, W, axis=1).astype(np.uint8), "RGB")


def _text(d, xy, s, size, fill, stroke=2, anchor=None):
    d.text(xy, s, font=_font(size), fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0), anchor=anchor)


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
    cur = None
    for start, text in CAPTIONS.get(scene, []):
        if u >= start:
            cur = (start, text)
    if not cur:
        return
    start, text = cur
    n = int((u - start) * 28) + 1                    # typewriter
    size = 12
    lines = _wrap(text, size, W - 10)
    shown, left = [], n
    for ln in lines:
        shown.append(ln[:max(0, left)])
        left -= len(ln) + 1
    lh = size + 3
    y0 = H - lh * len(lines) - 6
    band = img.crop((0, y0 - 4, W, H))
    img.paste(Image.fromarray((np.asarray(band, np.float32) * 0.3).astype(np.uint8), "RGB"), (0, y0 - 4))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(shown):
        if ln:
            _text(d, (W / 2, y0 + i * lh + lh / 2), ln, size, (255, 245, 230), stroke=1, anchor="mm")


class _Safe:
    """ImageDraw that accepts boxes drawn right-to-left (mirrored people and cars)."""
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

    def chord(self, b, st, en, *a, **k):
        self._d.chord(self._box(b), st, en, *a, **k)

    def arc(self, b, st, en, *a, **k):
        self._d.arc(self._box(b), st, en, *a, **k)


# ---------------------------------------------------------------- people ---

def _person(d, x, y, s, t, who, pose="stand", flip=False, prop=None):
    """Feet at (x, y); s = scale (1 ~ 34 px). who: 'max' | 'fionn' | 'bar' | 'amt' | 'bauer' | 'tuer' | 'kasse'."""
    dirn = -1 if flip else 1
    d = _Safe(d)

    def P(px, py):
        return (x + px * s * dirn, y + py * s)

    look = {"max": (MAX_HAIR, MAX_BLACK, MAX_BLACK, 1.35), "fionn": (FIONN_HAIR, FIONN_SHIRT, FIONN_JEANS, 1.0),
            "bar": ((70, 40, 30), (240, 240, 240), (40, 40, 50), 1.0), "amt": ((90, 90, 95), (30, 90, 160), (30, 50, 90), 1.0),
            "bauer": ((150, 150, 150), (60, 110, 60), (80, 60, 40), 1.1), "tuer": ((30, 30, 30), (15, 15, 18), (15, 15, 18), 1.5),
            "kasse": ((200, 120, 50), (230, 90, 40), (40, 40, 50), 1.0),
            "prinz": ((120, 90, 60), (24, 36, 90), (24, 24, 40), 1.05),
            "verk": ((40, 30, 25), (190, 120, 40), (60, 50, 40), 1.0)}
    hair, shirt, trou, wide = look[who]
    walk = math.sin(t * 9) if pose == "walk" else 0.0
    dance = math.sin(t * 11) if pose == "dance" else 0.0
    bob = abs(walk) * 0.8 + abs(dance) * 1.6
    hy = -27 - bob
    lw = max(1, int(2.4 * s))
    d.line([P(-2, -10 - bob), P(-2 - 3 * walk - 2 * dance, 0)], fill=trou, width=lw + (1 if who == "max" else 0))
    d.line([P(2, -10 - bob), P(2 + 3 * walk + 2 * dance, 0)], fill=trou, width=lw + (1 if who == "max" else 0))
    d.ellipse([*P(-4 - 3 * walk, -1), *P(-1 - 3 * walk, 1)], fill=(20, 18, 22))
    d.ellipse([*P(1 + 3 * walk, -1), *P(4 + 3 * walk, 1)], fill=(20, 18, 22))
    d.polygon([P(-4.5 * wide, -20 - bob), P(4.5 * wide, -20 - bob), P(5.2 * wide, -9 - bob), P(-5.2 * wide, -9 - bob)], fill=shirt)
    aw = max(1, int(2.6 * s))
    if pose in ("hold", "spray", "wave", "dance"):
        a = math.sin(t * 8) * (0.9 if pose != "spray" else 0.2)
        d.line([P(4 * wide, -18 - bob), P(10 + 2 * a, -23 - (3 if pose != "spray" else 0))], fill=shirt, width=aw)
        d.line([P(-4 * wide, -18 - bob), P(-9 - 2 * a, -24 if pose in ("wave", "dance") else -11)], fill=shirt, width=aw)
    else:
        d.line([P(4 * wide, -18 - bob), P(6.5 * wide - 2 * walk, -10 - bob)], fill=shirt, width=aw)
        d.line([P(-4 * wide, -18 - bob), P(-6.5 * wide + 2 * walk, -10 - bob)], fill=shirt, width=aw)
    d.ellipse([*P(-5.5, hy - 5.5), *P(5.5, hy + 5.5)], fill=SKIN)
    if who == "fionn":
        d.chord([*P(-6.5, hy - 8), *P(6.5, hy + 2)], 180, 360, fill=hair)
        d.rectangle([*P(-6.5, hy - 3), *P(-4.5, hy + 1)], fill=hair)
    elif who == "bar" or who == "kasse":
        d.chord([*P(-6.5, hy - 8), *P(6.5, hy + 2)], 180, 360, fill=hair)
        d.ellipse([*P(-8, hy - 3), *P(-4, hy + 8)], fill=hair)
    elif who == "tuer":
        d.chord([*P(-6, hy - 7), *P(6, hy + 1)], 180, 360, fill=hair)
        d.rectangle([*P(-5.5, hy - 1), *P(5.5, hy + 1)], fill=(10, 10, 10))   # sunglasses
    elif who == "amt":
        d.chord([*P(-6, hy - 9), *P(6, hy + 1)], 180, 360, fill=(30, 60, 130))    # cap
        d.rectangle([*P(-6, hy - 3), *P(8, hy - 2)], fill=(30, 60, 130))
    elif who == "prinz":
        d.chord([*P(-6.5, hy - 8), *P(6.5, hy + 2)], 180, 360, fill=hair)
        d.polygon([P(-5, hy - 7), P(-5, hy - 12), P(-2.5, hy - 9), P(0, hy - 13), P(2.5, hy - 9), P(5, hy - 12), P(5, hy - 7)], fill=(250, 200, 40))   # crown
        d.line([P(-4.5, -20 - bob), P(4.5, -10 - bob)], fill=(250, 200, 40), width=max(1, int(1.5 * s)))   # sash
    elif who == "verk":
        d.chord([*P(-6.5, hy - 8), *P(6.5, hy + 2)], 180, 360, fill=hair)
        d.rectangle([*P(-6.5, hy - 2), *P(-5, hy + 1)], fill=hair)
    elif who == "bauer":
        d.chord([*P(-9, hy - 9), *P(9, hy + 0)], 180, 360, fill=(200, 170, 80))   # straw hat
        d.rectangle([*P(-9, hy - 4), *P(9, hy - 3)], fill=(200, 170, 80))
    else:                                           # max: dark, slightly tousled
        d.chord([*P(-6.5, hy - 8), *P(6.5, hy + 2)], 180, 360, fill=hair)
        d.rectangle([*P(-6.5, hy - 4), *P(6.5, hy - 2)], fill=hair)
        d.rectangle([*P(-6.5, hy - 3), *P(-5, hy + 2)], fill=hair)
    if who != "tuer":
        ey = hy + 0.5
        if (t % 3.1) < 0.12:
            d.line([P(-3, ey), P(-1.4, ey)], fill=(20, 15, 20))
            d.line([P(1.4, ey), P(3, ey)], fill=(20, 15, 20))
        else:
            d.ellipse([*P(-3.2, ey - 1), *P(-1.6, ey + 1)], fill=(20, 15, 20))
            d.ellipse([*P(1.6, ey - 1), *P(3.2, ey + 1)], fill=(20, 15, 20))
    d.arc([*P(-2.2, hy + 1), *P(2.2, hy + 4.5)], 20, 160, fill=(140, 50, 60))
    if prop == "mood":                              # a Mood (cigarillo) with a glowing tip
        a, b = P(1.5, hy + 3), P(7.5, hy + 2)
        d.line([a, b], fill=(96, 66, 40), width=max(1, int(1.2 * s)))
        d.point(b, fill=(255, 120 + int(60 * abs(math.sin(t * 3))), 40))
    return P(10, -24)


# --------------------------------------------------------------- vehicles ---

def _rolf(d, x, y, s, t, plants=0, shake=0.0):
    """Rolf, the Bauhaus trolley basket. Wheels at y; x = centre."""
    sh = math.sin(t * 14) * shake
    w, h = 30 * s, 16 * s
    x0, y0 = x - w / 2, y - 7 * s - h + sh
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=(200, 205, 210), width=max(1, int(1.2 * s)))
    for i in range(1, 5):
        d.line([(x0 + i * w / 5, y0), (x0 + i * w / 5, y0 + h)], fill=(150, 156, 160))
    for i in range(1, 3):
        d.line([(x0, y0 + i * h / 3), (x0 + w, y0 + i * h / 3)], fill=(150, 156, 160))
    d.line([(x0 + w, y0 + 1), (x0 + w + 6 * s, y0 - 5 * s)], fill=(220, 60, 40), width=max(1, int(2 * s)))
    rs = random.Random(7)
    for i in range(plants):
        px = x0 + 2 * s + (i % 6) * (w - 4 * s) / 6 + rs.random() * 2
        top = y0 - 4 * s - (i % 3) * 3 * s
        d.line([(px, y0 + h * 0.6), (px, top)], fill=(40, 120, 50), width=max(1, int(1.5 * s)))
        col = [(60, 170, 70), (80, 200, 90), (40, 140, 60)][i % 3]
        d.ellipse([px - 3 * s, top - 3 * s, px + 3 * s, top + 2 * s], fill=col)
        if i % 4 == 0:
            d.ellipse([px - 1.3 * s, top - 4.5 * s, px + 1.3 * s, top - 2 * s], fill=(255, 90 + i * 8 % 120, 140))
    for wx in (x0 + 3 * s, x0 + w - 3 * s):
        d.ellipse([wx - 2.5 * s, y - 5 * s + sh, wx + 2.5 * s, y + sh], fill=(30, 30, 34))
    return (x0, y0, w, h)


def _porsche(d, x, y, s, t, boot=0.0, tools=0.0, trailer=False, rolf_plants=0, shake=0.0, face_left=False):
    """Grey Porsche SUV seen from the side, facing right; x = centre, y = ground. boot 0..1 opens the tailgate."""
    d = _Safe(d)

    def P(px, py):
        return (x + px * s * (-1 if face_left else 1), y + py * s)

    body = PORSCHE
    dark = tuple(int(c * 0.6) for c in body)
    light = tuple(min(255, int(c * 1.25)) for c in body)
    d.ellipse([*P(-34, -2), *P(34, 3)], fill=(0, 0, 0))                    # shadow
    d.polygon([P(-30, -6), P(-31, -19), P(-28, -27), P(-12, -30), P(-4, -41), P(17, -41), P(27, -28),
               P(32, -21), P(33, -9), P(30, -6)], fill=body)               # SUV body, tall roof
    d.polygon([P(-3, -29), P(-3, -39), P(16, -39), P(25, -29)], fill=(60, 90, 120))      # windows
    d.line([P(8, -39), P(8, -29)], fill=body, width=max(1, int(s)))
    d.line([P(-30, -14), P(33, -14)], fill=light, width=1)
    d.rectangle([*P(29, -17), *P(33, -14)], fill=(255, 235, 170))                          # headlight
    d.rectangle([*P(-31, -19), *P(-29, -14)], fill=(210, 40, 50))                          # tail light
    d.rectangle([*P(-18, -10), *P(8, -9)], fill=dark)
    for wx in (-18, 20):
        d.ellipse([*P(wx - 7, -12), *P(wx + 7, 2)], fill=(20, 20, 24))
        d.ellipse([*P(wx - 4, -9), *P(wx + 4, -1)], fill=(170, 175, 185))
    if boot > 0:                                                         # the tailgate swings up, the boot shows tools
        ang = boot
        tipx, tipy = -30 - 3 * ang, -26 - 14 * ang
        d.line([P(-30, -25), P(tipx, tipy)], fill=dark, width=max(1, int(2 * s)))
        d.rectangle([*P(-29, -24), *P(-14, -12)], fill=(14, 14, 18))
        if tools > 0:
            d.line([P(-28, -14), P(-16, -22)], fill=(250, 200, 40), width=max(1, int(1.6 * s)))   # Wasserwaage
            d.rectangle([*P(-26, -20), *P(-20, -15)], fill=(200, 60, 40))                          # Eimer
            d.rectangle([*P(-19, -19), *P(-15, -15)], fill=(30, 150, 80))                          # Bohrmaschine
            d.polygon([P(-17, -24), P(-14, -24), P(-14, -19), P(-17, -19)], fill=(255, 140, 20))   # Warnweste
    if trailer:                                                           # Rolf on the tow bar
        d.line([P(-30, -7), P(-37, -6)], fill=(80, 80, 85), width=max(1, int(1.5 * s)))
        rx = x + (37 + 15) * s * (1 if face_left else -1)
        _rolf(d, rx, y, s * 0.55, t, plants=rolf_plants, shake=shake)


# ---------------------------------------------------------------- scenes ---

def _titel(u, t, W, H):
    img = _sky(W, H, (255, 170, 110), (255, 220, 170))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H * 0.62, W, H], fill=(70, 70, 80))
    d.line([(0, H * 0.62), (W, H * 0.62)], fill=(110, 110, 120), width=2)
    k = _back(_clamp(u / 1.2))
    _text(d, (W / 2, H * 0.16), "MAX", int(34 * k) + 1, (255, 255, 255), anchor="mm")
    _text(d, (W / 2, H * 0.27), "& FIONN", int(30 * k) + 1, (255, 235, 120), anchor="mm")
    px = -50 + (W * 0.5 + 50) * _clamp(u / 2.2)
    _porsche(d, px, H * 0.62, 1.7, t, boot=_clamp((u - 2.4) / 0.8) * 0.9, tools=1.0 if u > 3.2 else 0.0, trailer=True,
             rolf_plants=5, shake=0.4 if u < 2.4 else 0.0)
    return img


def _bar_scene(u, t, W, H):
    img = _sky(W, H, (30, 22, 55), (80, 44, 70))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H * 0.08, W, H * 0.52], fill=(70, 36, 50))                   # Colibri's front
    glow = 0.6 + 0.4 * abs(math.sin(t * 2.2))
    _text(d, (W / 2, H * 0.14), "COLIBRI", 19, _lerp((90, 30, 70), (255, 110, 190), glow), stroke=1, anchor="mm")
    d.rectangle([W * 0.08, H * 0.24, W * 0.46, H * 0.46], fill=(255, 200, 120))      # warm windows
    d.rectangle([W * 0.54, H * 0.24, W * 0.92, H * 0.46], fill=(255, 190, 110))
    d.rectangle([0, H * 0.52, W, H], fill=(70, 66, 76))                                # pavement
    d.line([(0, H * 0.52), (W, H * 0.52)], fill=(120, 116, 126), width=2)
    cnt = min(47, int(1 + u * 3.2))
    _text(d, (W - 6, H * 0.06), f"x{cnt}", 15, (255, 220, 120), stroke=1, anchor="rm")
    d.ellipse([W * 0.2, H * 0.62, W * 0.8, H * 0.7], fill=(235, 225, 205))            # the outside table
    d.line([(W * 0.5, H * 0.7), (W * 0.5, H * 0.84)], fill=(120, 120, 125), width=3)
    for i in range(min(18, int(u * 1.6))):                                             # Moods packs pile up on the table
        bx, by = W * 0.24 + (i % 9) * 11, H * 0.62 - 3 - (i // 9) * 7
        d.rectangle([bx, by, bx + 9, by + 5], fill=(70, 40, 90))
        d.rectangle([bx + 1, by + 1, bx + 8, by + 2], fill=(220, 190, 90))
    d.rectangle([W * 0.46, H * 0.58, W * 0.5, H * 0.62], fill=(60, 120, 70))            # one drink. Just one.
    _person(d, W * 0.18, H * 0.92, 2.0, t, "max", "hold", prop="mood")
    _person(d, W * 0.52, H * 0.94, 1.8, t, "fionn", "stand", flip=True)
    vx = W * 1.12 - _clamp(u / 4.4) * (W * 0.34) + (math.sin(t * 4) * 1.5 if u > 4.4 else 0)
    _person(d, vx, H * 0.92, 1.9, t, "verk", "hold", flip=True)
    d.rectangle([vx - 22, H * 0.92 - 34, vx - 8, H * 0.92 - 28], fill=(70, 40, 90))     # his tray of Moods
    if 4.6 < u < 7.5:
        _text(d, (vx - 8, H * 0.92 - 58), "Moods?", 11, (255, 235, 160), stroke=1, anchor="mm")
    if u > 12.5:
        _text(d, (W / 2, H * 0.55), "Keller: " + str(min(99, int((u - 12.5) * 11))) + " Päckchen", 9, (255, 230, 150), anchor="mm")
    return img


def _kuerbis(u, t, W, H):
    img = _sky(W, H, (8, 10, 30), (30, 25, 55))
    d = ImageDraw.Draw(img)
    d.ellipse([W * 0.7, 14, W * 0.7 + 22, 36], fill=(245, 240, 205))
    d.rectangle([0, H * 0.58, W, H], fill=(36, 34, 28))
    rs = random.Random(11)
    for i in range(28):
        px, py = rs.random() * W, H * 0.62 + rs.random() * H * 0.28
        r = 5 + rs.random() * 6
        d.ellipse([px - r, py - r * 0.8, px + r, py + r * 0.8], fill=(235, 120 + rs.randrange(30), 30))
        d.line([(px, py - r * 0.8), (px, py - r)], fill=(60, 110, 40), width=2)
    sx = W * 0.82 + (math.sin(t * 30) * 2 if u > 9.2 and u < 10.4 else 0)
    d.line([(sx, H * 0.38), (sx, H * 0.6)], fill=(110, 80, 40), width=3)                         # scarecrow
    d.line([(sx - 12, H * 0.43), (sx + 12, H * 0.43)], fill=(110, 80, 40), width=3)
    d.ellipse([sx - 6, H * 0.34, sx + 6, H * 0.34 + 12], fill=(220, 200, 120))
    d.chord([sx - 9, H * 0.31, sx + 9, H * 0.31 + 9], 180, 360, fill=(120, 90, 40))
    if u > 9.4:
        _person(d, W * 0.95 + (1 - _clamp((u - 9.4) / 2.0)) * 40, H * 0.76, 1.7, t, "bauer", "walk", flip=True)
    fx = 40 + 34 * _clamp(u / 6) + (math.sin(t * 2) * 3)
    _person(d, fx, H * 0.76, 1.8, t, "fionn", "hold")
    cone = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(cone).polygon([(fx + 18, H * 0.76 - 38), (fx + 90, H * 0.55), (fx + 90, H * 0.92)], fill=(255, 245, 170, 70))
    img.paste(cone, (0, 0), cone)
    d = ImageDraw.Draw(img)
    _person(d, 24, H * 0.82, 2.0, t, "max", "stand", prop="mood")
    pr = _clamp((u - 10.5) / 3.0)                                                    # porsche with a pumpkin, seatbelted
    if u > 10.5:
        _porsche(d, W * 1.3 - pr * W * 0.55, H * 0.92, 0.9, t, face_left=True, trailer=False)
        d.ellipse([W * 1.3 - pr * W * 0.55 - 9, H * 0.92 - 36, W * 1.3 - pr * W * 0.55 - 1, H * 0.92 - 27], fill=(235, 120, 30))
    return img


def _terrasse(u, t, W, H):
    clean = _clamp((u - 2) / 8)
    img = _sky(W, H, (150, 205, 245), (205, 235, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H * 0.4, W, H], fill=_lerp((92, 96, 84), (176, 176, 170), clean))
    sink = _clamp((u - 8.5) / 3.0)
    for i in range(0, W + 30, 30):
        d.line([(i, H * 0.4), (i - 60, H)], fill=_lerp((60, 62, 55), (176, 176, 170), clean), width=2)
    for j in range(5):
        yy = H * 0.4 + j * 36 * (1 + j * 0.1)
        d.line([(0, yy), (W, yy)], fill=_lerp((60, 62, 55), (176, 176, 170), clean), width=2)
    if sink > 0:                                                                       # the terrace is now 3 cm lower
        d.rectangle([W * 0.1, H * 0.62, W * 0.9, H * 0.62 + 10 * sink], fill=(110, 140, 170))
    d.rectangle([0, H * 0.3, W, H * 0.4], fill=(200, 170, 130))                         # house wall
    for i in range(4):
        d.rectangle([14 + i * 44, H * 0.31, 40 + i * 44, H * 0.37], fill=(255, 235, 160))
    mx = 110
    _person(d, mx, H * 0.84, 2.1, t, "max", "spray")
    _person(d, 40, H * 0.9, 1.9, t, "fionn", "wave")
    rs = random.Random(int(t * 24))
    gx, gy = mx - 22, H * 0.84 - 40
    for _ in range(70):                                                                # spray
        a = rs.random()
        sx_, sy_ = gx - a * 80 + rs.random() * 6, gy + a * 40 + rs.random() * 6 - 4 * a
        d.ellipse([sx_, sy_, sx_ + 3, sy_ + 3], fill=(230, 245, 255))
    if 4.5 < u < 6.5:                                                                  # a flowerpot flies off
        k = (u - 4.5) / 2.0
        px, py = 150 + k * 70, H * 0.66 - k * 70 + k * k * 90
        d.polygon([(px, py), (px + 10, py), (px + 8, py + 9), (px + 2, py + 9)], fill=(200, 100, 60))
    if u > 9.0:                                                                        # the neighbour's dog, soaked
        dx = 150
        d.ellipse([dx, H * 0.86, dx + 26, H * 0.86 + 12], fill=(120, 100, 85))
        d.ellipse([dx + 20, H * 0.86 - 6, dx + 32, H * 0.86 + 4], fill=(130, 110, 95))
        d.line([(dx + 12, H * 0.86 + 12), (dx + 12, H * 0.86 + 20)], fill=(100, 85, 70), width=2)
        d.line([(dx + 4, H * 0.86 + 12), (dx + 4, H * 0.86 + 20)], fill=(100, 85, 70), width=2)
    d.rectangle([W * 0.2, 6, W * 0.8, 18], outline=(255, 255, 255))
    d.rectangle([W * 0.2 + 1, 7, W * 0.2 + 1 + (W * 0.6 - 2) * 0.12, 17], fill=(255, 190, 60))
    _text(d, (W / 2, 12), "in Arbeit: 12 %", 8, (255, 255, 255), stroke=1, anchor="mm")
    return img


def _parken(u, t, W, H):
    img = _sky(W, H, (120, 170, 220), (200, 225, 245))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H * 0.28, W, H * 0.55], fill=(220, 190, 160))                        # houses
    for i in range(5):
        d.rectangle([8 + i * 38, H * 0.33, 24 + i * 38, H * 0.43], fill=(120, 150, 180))
        d.rectangle([8 + i * 38, H * 0.47, 24 + i * 38, H * 0.53], fill=(255, 220, 140))
    d.rectangle([0, H * 0.55, W, H], fill=(108, 104, 100))                               # the small cobbled lane
    for j in range(12):
        for i in range(-1, W // 10 + 1):
            cx, cy = i * 10 + (5 if j % 2 else 0), H * 0.58 + j * 6
            d.ellipse([cx, cy, cx + 8, cy + 4], fill=(94 + (i * 7 + j * 5) % 24, 90 + (i * 5) % 20, 86 + (j * 9) % 18))
    d.rectangle([0, H * 0.55, W, H * 0.58], fill=(160, 160, 160))                        # kerb
    d.rectangle([W * 0.04, H * 0.36, W * 0.04 + 52, H * 0.36 + 12], fill=(250, 250, 250))
    _text(d, (W * 0.04 + 26, H * 0.36 + 6), "Fortunagasse 24", 6, (30, 30, 30), stroke=0, anchor="mm")
    sx = W * 0.9                                                                          # Parkverbot sign
    d.line([(sx, H * 0.45), (sx, H * 0.6)], fill=(120, 120, 125), width=2)
    d.ellipse([sx - 9, H * 0.38, sx + 9, H * 0.38 + 18], fill=(40, 70, 190), outline=(255, 255, 255), width=1)
    d.line([(sx - 7, H * 0.38 + 16), (sx + 7, H * 0.38 + 2)], fill=(220, 40, 40), width=3)
    px = -60 + (W * 0.44 + 60) * _clamp(u / 2.8)
    boot = _clamp((u - 3.4) / 0.8) * 0.9
    _porsche(d, px, H * 0.7, 1.75, t, boot=boot, tools=_clamp((u - 4.4) / 2.0), trailer=u > 11.0, rolf_plants=0)
    if u > 6:
        _person(d, W * 0.78, H * 0.78, 1.9, t, "max", "hold")
    if u > 7.6:
        ax = W * 0.98 - (1 - _clamp((u - 7.6) / 2.0)) * 34
        _person(d, ax, H * 0.86, 1.9, t, "amt", "stand", flip=True)
    if u > 12.8:
        d.rectangle([W * 0.58, H * 0.52, W * 0.58 + 38, H * 0.52 + 26], fill=(255, 225, 90), outline=(120, 80, 20), width=2)
        _text(d, (W * 0.58 + 19, H * 0.52 + 13), "Zettel", 9, (60, 40, 10), stroke=0, anchor="mm")
    return img


def _bauhaus(u, t, W, H):
    img = _sky(W, H, (225, 225, 230), (200, 200, 210))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H * 0.06, W, H * 0.2], fill=(220, 40, 40))
    _text(d, (W / 2, H * 0.13), "BAUHAUS", 18, (255, 255, 255), stroke=1, anchor="mm")
    d.rectangle([0, H * 0.2, W, H * 0.6], fill=(196, 202, 206))
    rs = random.Random(3)
    for i in range(36):
        px, py = 6 + (i % 12) * 15, H * 0.26 + (i // 12) * 30
        d.rectangle([px, py + 12, px + 11, py + 18], fill=(190, 90, 60))
        d.ellipse([px - 1, py, px + 12, py + 14], fill=[(70, 170, 80), (50, 140, 70), (90, 190, 100)][i % 3])
    d.rectangle([0, H * 0.6, W, H], fill=(98, 98, 104))
    n = int(_clamp(u / 7) * 47)
    _text(d, (W - 6, H * 0.23), f"{n} Pflanzen", 8, (255, 255, 255), stroke=1, anchor="rm")
    phase = u
    fx = 40 + 70 * _clamp(phase / 6.5) + (_clamp((phase - 12.5) / 4) * 120)
    _person(d, fx, H * 0.78, 1.9, t, "fionn", "walk" if phase < 6.5 or phase > 12.5 else "stand")
    if phase < 9:
        _rolf(d, fx - 36, H * 0.78, 1.0, t, plants=n // 4)
    if 4.3 < phase < 12.5:
        _person(d, 168 if phase > 7 else 190 - (phase - 4.3) * 8, H * 0.8, 1.7, t, "kasse", "stand", flip=True)
    if phase >= 9:
        px = W * 0.5 + _clamp((phase - 13.5) / 4) * W
        _porsche(d, px, H * 0.9, 1.5, t, trailer=True, rolf_plants=n // 3, shake=0.5 if phase > 13.5 else 0.0)
        _person(d, 40 + _clamp((phase - 13.5) / 4) * 40, H * 0.9, 1.9, t, "max", "hold") if phase < 13.5 else None
    return img


def _heim(u, t, W, H):
    img = _sky(W, H, (10, 12, 35), (40, 30, 60))
    d = ImageDraw.Draw(img)
    d.ellipse([W * 0.12, 16, W * 0.12 + 20, 36], fill=(245, 240, 205))
    d.rectangle([0, H * 0.7, W, H], fill=(48, 48, 56))
    for i in range(0, W, 28):
        d.rectangle([(i - u * 40) % W, H * 0.84, (i - u * 40) % W + 14, H * 0.84 + 2], fill=(220, 220, 140))
    cx = W * 0.5 + math.sin(t * 2.4) * 2
    sag = 3 + math.sin(t * 7) * 0.8
    _porsche(d, cx, H * 0.78 + sag, 1.55, t, trailer=True, rolf_plants=0, shake=0.6)
    rs = random.Random(5)
    for i in range(46):                                                       # the mountain of pumpkins on the roof and tailgate
        px = cx - 38 + rs.random() * 70
        py = H * 0.78 - 42 - rs.random() * 38 - (30 - abs(px - cx)) * 0.5
        r = 5 + rs.random() * 4
        d.ellipse([px - r, py - r * 0.8, px + r, py + r * 0.8], fill=(235, 115 + rs.randrange(35), 30), outline=(150, 70, 20))
    for i in range(10):                                                       # Rolf, overflowing
        rx = cx - 82 + rs.random() * 28
        ry = H * 0.78 - 18 - rs.random() * 14
        d.ellipse([rx - 5, ry - 4, rx + 5, ry + 4], fill=(235, 125, 30), outline=(150, 70, 20))
    _text(d, (W / 2, H * 0.12), "1000 kg", 22, (255, 190, 80), anchor="mm")
    if u > 4.6:
        _text(d, (cx, H * 0.78 + 14), "Federung: Nein", 8, (255, 255, 255), stroke=1, anchor="mm")
    return img


def _dinner(u, t, W, H):
    img = _sky(W, H, (60, 28, 36), (96, 52, 52))
    d = ImageDraw.Draw(img)
    in_house = u < 12.0
    if in_house:
        d.rectangle([0, H * 0.62, W, H], fill=(90, 56, 40))                    # floor
        d.rectangle([W * 0.08, H * 0.18, W * 0.92, H * 0.5], fill=(40, 22, 30))   # window
        _text(d, (W / 2, H * 0.12), "HOUSE FORTUNA", 11, (255, 220, 150), stroke=1, anchor="mm")
        d.rectangle([W * 0.1, H * 0.62, W * 0.9, H * 0.68], fill=(235, 225, 205))  # table
        for cx in (W * 0.3, W * 0.7):                                           # candles
            d.rectangle([cx - 1, H * 0.56, cx + 1, H * 0.62], fill=(250, 240, 220))
            d.ellipse([cx - 2, H * 0.53 + math.sin(t * 12 + cx) * 0.8, cx + 2, H * 0.56], fill=(255, 190, 70))
        d.rectangle([W * 0.46, H * 0.55, W * 0.5, H * 0.62], fill=(40, 90, 50))   # the wine bottle
        d.rectangle([W * 0.465, H * 0.52, W * 0.485, H * 0.55], fill=(40, 90, 50))
        _person(d, W * 0.2, H * 0.84, 2.0, t, "max", "hold", prop="mood")
        _person(d, W * 0.5, H * 0.9, 2.0, t, "prinz", "stand")
        _person(d, W * 0.82, H * 0.84, 1.9, t, "fionn", "stand", flip=True)
        if u > 4.4:                                                              # Max slaps the order slip on the table
            d.rectangle([W * 0.38, H * 0.64 + 2, W * 0.62, H * 0.64 + 12], fill=(250, 245, 230), outline=(60, 40, 20))
            _text(d, (W * 0.5, H * 0.64 + 7), "PALETTE WEIN", 7, (160, 30, 30), stroke=0, anchor="mm")
        if u > 9.0:
            _text(d, (W * 0.5, H * 0.38), "1 x Palette", 14, (255, 210, 140), stroke=1, anchor="mm")
    else:                                                                        # delivery to the palace
        k = _clamp((u - 12.0) / 2.5)
        d.rectangle([0, H * 0.62, W, H], fill=(60, 90, 50))
        d.rectangle([W * 0.2, H * 0.3, W * 0.8, H * 0.62], fill=(210, 195, 170))
        for tx in (W * 0.16, W * 0.72):
            d.rectangle([tx, H * 0.2, tx + 28, H * 0.62], fill=(200, 185, 160))
            d.polygon([(tx - 3, H * 0.2), (tx + 14, H * 0.1), (tx + 31, H * 0.2)], fill=(150, 60, 60))
        for i, col in enumerate(((20, 20, 24), (250, 210, 40), (210, 40, 50))):   # flag stripes
            d.rectangle([W * 0.42 + i * 8, H * 0.14, W * 0.42 + i * 8 + 8, H * 0.28], fill=col)
        d.rectangle([W * 0.43, H * 0.46, W * 0.57, H * 0.62], fill=(90, 60, 40))
        tx = W * 1.2 - k * W * 0.65
        d.rectangle([tx, H * 0.62, tx + 70, H * 0.8], fill=(240, 240, 240), outline=(60, 60, 60))
        d.rectangle([tx - 24, H * 0.7, tx, H * 0.8], fill=(230, 110, 40))
        for i in range(4):
            for j in range(3):
                d.rectangle([tx + 4 + i * 16, H * 0.64 + j * 5, tx + 16 + i * 16, H * 0.64 + j * 5 + 4], fill=(150, 40, 70))
        d.ellipse([tx - 18, H * 0.78, tx - 8, H * 0.78 + 10], fill=(20, 20, 24))
        d.ellipse([tx + 48, H * 0.78, tx + 58, H * 0.78 + 10], fill=(20, 20, 24))
        _text(d, (W / 2, H * 0.06), "PALAST", 11, (255, 230, 150), stroke=1, anchor="mm")
        if u > 14.6:
            _person(d, W * 0.2, H * 0.92, 1.9, t, "bar", "stand")                  # the butler
            _text(d, (W * 0.2, H * 0.92 - 70), "?", 22, (255, 255, 255), anchor="mm")
    return img


def _lindenhof(u, t, W, H):
    img = _sky(W, H, (14, 14, 44), (60, 34, 70))
    d = ImageDraw.Draw(img)
    rs = random.Random(8)
    for _ in range(40):
        d.point((rs.random() * W, rs.random() * H * 0.3), fill=(255, 255, 230))
    d.ellipse([W * 0.76, 12, W * 0.76 + 18, 30], fill=(245, 240, 205))
    hz = H * 0.5
    for i in range(16):                                                       # the old town across the Limmat
        bx = i * W / 16
        bh = 12 + (i * 29 % 19)
        d.rectangle([bx, hz - bh, bx + W / 16, hz], fill=(36, 30, 52))
        if i % 3 == 0:
            d.point((bx + 4, hz - bh + 4), fill=(255, 210, 120))
    for tx, th in ((W * 0.22, 44), (W * 0.62, 38), (W * 0.82, 30)):          # church towers
        d.rectangle([tx, hz - th, tx + 9, hz], fill=(44, 36, 62))
        d.polygon([(tx - 1, hz - th), (tx + 4.5, hz - th - 14), (tx + 10, hz - th)], fill=(60, 110, 100))
    for i in range(30):                                                       # the river with the lights
        yy = hz + 4 + i * 2.2
        d.line([(0, yy), (W, yy)], fill=(22 + i, 24 + i // 2, 60 + i), width=1)
        d.line([(30 + (i * 17) % 130, yy), (36 + (i * 17) % 130 + math.sin(t * 3 + i) * 3, yy)], fill=(255, 200, 120), width=1)
    d.rectangle([0, H * 0.7, W, H], fill=(48, 62, 40))                         # the Lindenhof lawn
    d.rectangle([W * 0.08, H * 0.76, W * 0.92, H * 0.92], fill=(170, 60, 70))        # the blanket
    d.rectangle([W * 0.08, H * 0.76, W * 0.92, H * 0.77], fill=(230, 190, 190))
    for cx in (W * 0.34, W * 0.66):                                            # candles
        d.rectangle([cx - 2, H * 0.72, cx + 2, H * 0.78], fill=(250, 240, 220))
        fl = 6 + math.sin(t * 13 + cx) * 1.2
        d.ellipse([cx - 3, H * 0.72 - fl, cx + 3, H * 0.72 + 1], fill=(255, 190, 70))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([cx - 26, H * 0.72 - 26, cx + 26, H * 0.72 + 26], fill=(255, 170, 60, 36))
        img.paste(glow, (0, 0), glow)
        d = ImageDraw.Draw(img)
    d.ellipse([W * 0.42, H * 0.8, W * 0.58, H * 0.86], fill=(240, 235, 220))          # tapas plate: 3 olives
    for ox in (-5, 0, 5):
        d.ellipse([W * 0.5 + ox - 2, H * 0.82, W * 0.5 + ox + 2, H * 0.82 + 4], fill=(60, 70, 30))
    d.rectangle([W * 0.28, H * 0.78, W * 0.32, H * 0.84], fill=(40, 90, 50))               # wine
    d.rectangle([W * 0.675, H * 0.78, W * 0.715, H * 0.84], fill=(130, 30, 50))
    _person(d, W * 0.22, H * 0.86, 1.9, t, "max", "hold", prop="mood")
    _person(d, W * 0.78, H * 0.86, 1.8, t, "fionn", "hold", flip=True)
    if u > 8.4:
        _text(d, (W / 2, H * 0.62), "CHF 80", 16, (255, 210, 120), anchor="mm")
    return img


def _hive(u, t, W, H):
    img = _sky(W, H, (10, 6, 25), (30, 10, 50))
    d = ImageDraw.Draw(img)
    r = 9
    for row in range(5):
        for col in range(8):                                            # honeycomb
            cx, cy = col * r * 1.8 + (r * 0.9 if row % 2 else 0), 16 + row * r * 1.55
            pts = [(cx + r * 0.95 * math.cos(math.radians(60 * k + 30)), cy + r * 0.95 * math.sin(math.radians(60 * k + 30))) for k in range(6)]
            d.polygon(pts, outline=_lerp((80, 50, 10), (255, 190, 40), 0.5 + 0.5 * math.sin(t * 3 + col + row)))
    _text(d, (W / 2, H * 0.12), "HIVE", 24, (255, 200, 50), stroke=1, anchor="mm")
    d.rectangle([0, H * 0.62, W, H], fill=(38, 36, 44))
    strobe = int(t * 6) % 2
    if strobe:
        d.rectangle([0, 0, W, H * 0.62], outline=(255, 255, 255), width=3)
    _person(d, W * 0.84, H * 0.8, 2.1, t, "tuer", "stand", flip=True)
    _porsche(d, W * 0.3, H * 0.9, 1.1, t, boot=0.9, tools=1.0, trailer=True, rolf_plants=3)
    fx = 100 + math.sin(t * 2) * 6
    _person(d, fx, H * 0.78, 1.9, t, "fionn", "dance")
    d.ellipse([fx + 4, H * 0.78 - 78, fx + 22, H * 0.78 - 58], fill=(60, 150, 70))               # Gummibaum
    d.line([(fx + 13, H * 0.78 - 60), (fx + 13, H * 0.78 - 42)], fill=(80, 60, 30), width=2)
    clock = "23:30" if u < 6 else ("02:00" if u < 10.5 else "06:00")
    _text(d, (W - 6, 8), clock, 12, (120, 255, 140), stroke=1, anchor="rm")
    for i in range(14):
        a = t * 1.5 + i
        c = [(255, 60, 140), (80, 200, 255), (255, 210, 70)][i % 3]
        d.line([(W / 2, H * 0.1), (W / 2 + math.cos(a) * 150, H * 0.1 + abs(math.sin(a)) * 140)], fill=_lerp(c, (10, 6, 25), 0.55), width=1)
    return img


def _monsti(u, t, W, H):
    img = _sky(W, H, (255, 205, 150), (255, 235, 195))
    d = ImageDraw.Draw(img)
    for nx, col in ((-14, (206, 170, 140)), (W * 0.84, (196, 160, 150))):                          # the old town's neighbours
        d.rectangle([nx, H * 0.2, nx + 40, H * 0.82], fill=col)
        d.polygon([(nx - 3, H * 0.2), (nx + 20, H * 0.1), (nx + 43, H * 0.2)], fill=(150, 80, 70))
    d.rectangle([W * 0.16, H * 0.12, W * 0.84, H * 0.82], fill=(226, 184, 150))                  # Haus Fortuna: old, narrow, tall
    for i in range(0, int(W * 0.68), 12):
        d.line([(W * 0.16 + i, H * 0.12), (W * 0.16 + i, H * 0.82)], fill=(214, 172, 140), width=1)
    d.polygon([(W * 0.12, H * 0.12), (W * 0.5, H * 0.0), (W * 0.88, H * 0.12)], fill=(160, 70, 60))   # steep tiled roof
    d.rectangle([W * 0.3, H * 0.015, W * 0.7, H * 0.075], fill=(240, 226, 196))
    _text(d, (W * 0.5, H * 0.045), "FORTUNAGASSE 24", 7, (90, 50, 40), stroke=0, anchor="mm")
    for wx, wy in ((W * 0.2, H * 0.17), (W * 0.62, H * 0.17), (W * 0.2, H * 0.6)):
        d.rectangle([wx, wy, wx + 32, wy + 30], fill=(255, 220, 140), outline=(110, 70, 50))
        d.rectangle([wx - 8, wy, wx - 1, wy + 30], fill=(60, 120, 80))                           # green shutters
        d.rectangle([wx + 33, wy, wx + 40, wy + 30], fill=(60, 120, 80))
    fx, fy = W * 0.41, H * 0.34                                                                     # Monsti's window, first floor
    d.rectangle([fx - 8, fy, fx - 1, fy + 34], fill=(60, 120, 80))
    d.rectangle([fx + 41, fy, fx + 48, fy + 34], fill=(60, 120, 80))
    d.rectangle([fx, fy, fx + 40, fy + 34], fill=(60, 50, 60), outline=(110, 70, 50), width=2)
    d.polygon([(fx + 10, fy + 34), (fx + 30, fy + 34), (fx + 27, fy + 44), (fx + 13, fy + 44)], fill=(200, 100, 60))   # the pot
    d.rectangle([0, H * 0.82, W, H], fill=(112, 108, 104))                                          # small cobblestone lane
    for j in range(7):
        for i in range(-1, W // 9 + 1):
            cx, cy = i * 9 + (4 if j % 2 else 0), H * 0.82 + j * 4 + 2
            d.ellipse([cx, cy, cx + 7, cy + 3], fill=(96 + (i * 7 + j * 5) % 24, 92 + (i * 5) % 20, 88 + (j * 9) % 18))
    d.rectangle([W * 0.44, H * 0.62, W * 0.56, H * 0.82], fill=(120, 76, 50))                   # old wooden door
    d.arc([W * 0.44, H * 0.58, W * 0.56, H * 0.66], 180, 360, fill=(120, 76, 50), width=3)
    d.rectangle([W * 0.7, H * 0.64, W + 4, H * 0.82], fill=(150, 146, 140))                    # the Lindenhof's stone wall, opposite
    for i in range(0, 6):
        d.line([(W * 0.7, H * 0.64 + i * 8), (W + 4, H * 0.64 + i * 8)], fill=(120, 116, 112), width=1)
    d.rectangle([W * 0.86, H * 0.42, W * 0.89, H * 0.66], fill=(90, 62, 40))                    # lindens on top
    d.ellipse([W * 0.72, H * 0.2, W * 1.06, H * 0.5], fill=(90, 150, 70))
    d.ellipse([W * 0.66, H * 0.3, W * 0.9, H * 0.5], fill=(70, 130, 60))
    d.rectangle([W * 0.06, H * 0.64, W * 0.06 + 22, H * 0.64 + 16], fill=(40, 90, 190))        # pedestrian-zone sign
    d.ellipse([W * 0.06 + 8, H * 0.64 + 2, W * 0.06 + 14, H * 0.64 + 8], fill=(255, 255, 255))
    grow = _clamp(u / 8.5)
    n = int(2 + grow * 18)
    sw = math.sin(t * 1.4) * 2
    px, py = fx + 20, fy + 34
    pts = [(px, py)]
    for i in range(n):                                                                              # the stem snakes down the wall
        k = i / 18.0
        pts.append((px + math.sin(k * 5.0) * 22 + sw * k, py + 6 + i * (H * 0.42 / 18.0)))
    for a, b in zip(pts, pts[1:]):
        d.line([a, b], fill=(40, 100, 50), width=3)
    for i, (lx, ly) in enumerate(pts[1:]):
        r = 11 - i * 0.2
        side = 1 if i % 2 == 0 else -1
        cx, cy = lx + side * (r + 2), ly
        d.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], fill=(34 + (i * 7) % 30, 130 + (i * 11) % 40, 60))
        for hx in (-0.5, 0.0, 0.5):                                                                 # the Monstera holes
            d.ellipse([cx + hx * r - 1.5, cy - 2, cx + hx * r + 1.5, cy + 3], fill=(224, 176, 150))
        d.line([(lx, ly), (cx, cy)], fill=(40, 100, 50), width=1)
    if u > 2.4:
        _text(d, (fx + 20, fy - 10), "Monsti", 11, (180, 255, 190), stroke=1, anchor="mm")
    _person(d, W * 0.2, H * 0.9, 1.8, t, "max", "stand", prop="mood")
    _person(d, W * 0.82, H * 0.9, 1.8, t, "fionn", "wave", flip=True)
    if u > 7.6:
        _text(d, (W * 0.5, H * 0.5), "Monsti: 4 m", 9, (255, 255, 255), stroke=1, anchor="mm")
    return img


def _montag(u, t, W, H):
    img = _sky(W, H, (255, 218, 160), (255, 240, 205))
    d = ImageDraw.Draw(img)
    d.ellipse([W * 0.7, 18, W * 0.7 + 28, 46], fill=(255, 245, 190))
    d.rectangle([0, H * 0.46, W, H], fill=(150, 155, 150))
    d.rectangle([W * 0.1, H * 0.66, W * 0.9, H * 0.66 + 8], fill=(110, 140, 170))                  # puddle: the terrace is lower
    _person(d, 48, H * 0.74, 2.0, t, "max", "stand", prop="mood")
    _person(d, 96, H * 0.76, 1.9, t, "fionn", "stand")
    _rolf(d, 148, H * 0.78, 1.2, t, plants=12)
    d.ellipse([110, H * 0.66, 128, H * 0.66 + 14], fill=(235, 120, 30))                              # pumpkin
    for i in range(3):
        bx = 16 + i * 14
        d.rectangle([bx, H * 0.84, bx + 12, H * 0.84 + 6], fill=(70, 40, 90))                         # empty Moods boxes
    d.line([(180, H * 0.66), (186, H * 0.82)], fill=(40, 40, 46), width=2)                           # pressure washer hose
    if u > 7.8:
        k = _back(_clamp((u - 7.8) / 0.8))
        _text(d, (W / 2, H * 0.16), "IN ARBEIT", int(22 * k) + 1, (60, 40, 30), anchor="mm")
        _text(d, (W / 2, H * 0.26), "Max & Fionn", 12, (110, 70, 40), stroke=1, anchor="mm")
    if u > 10.4:
        _text(d, (W / 2, H * 0.4), "Kein Porsche kam beim Parken zu Schaden.", 7, (90, 60, 40), stroke=0, anchor="mm")
        _text(d, (W / 2, H * 0.44), "Rolf wurde nicht gestohlen, nur befreit.", 7, (90, 60, 40), stroke=0, anchor="mm")
    return img


SCENE_FN = {"titel": _titel, "colibri": _bar_scene, "kuerbis": _kuerbis, "heim": _heim, "terrasse": _terrasse,
            "parken": _parken, "bauhaus": _bauhaus, "dinner": _dinner, "lindenhof": _lindenhof, "hive": _hive, "monsti": _monsti, "montag": _montag}


def frame(t: float) -> Image.Image:
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    t = t % LOOP_SEC
    for name, a, b in SCENES:
        if a <= t < b:
            u = t - a
            HS = H - 56                                  # the caption lives in its own band below the picture
            img = Image.new("RGB", (W, H), (8, 6, 12))
            img.paste(SCENE_FN[name](u, t, W, HS), (0, 0))
            _caption(img, name, u, W, H)
            fade = min(_clamp(u / FADE), _clamp((b - t) / FADE))
            if fade < 1:
                img = Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8), "RGB")
            return img
    return Image.new("RGB", (W, H))


def thumb() -> Image.Image:
    return frame(5.0)
