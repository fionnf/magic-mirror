"""Lennart zeigt Fionn das Ländle: a standalone little comedy for the wall (~128 s, in German, loops).

frame(t) is a pure function of t.

   0-  6  title
   6- 24  Bittenfeld: Fionn steals apples and eats them, Lennart holds him back
  24- 38  Fachwerk! Fionn is beside himself
  38- 54  no hedges! Fionn walks across other people's Stückle; a Swabian farmer is not amused
  54- 68  the vineyards: Fionn steals grapes
  68- 85  Fionn looks for the sea and finds fog, the Alb and a duck pond
  85- 99  the vineyard mafia has a word with Fionn; Lennart pays in apples
  99-113  Karlstein at sunset: a kiss
 113-128  home in Bittenfeld: blanket, tea, fire, one more stolen apple
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw

import config
from display import laend_intro as li
from display.laend_intro import _c, _ease, _mix, _text, _sky, _hills, _tree, _fachwerk, _house, _church, _bird, _heart, _apple, font

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
SCENES = [("title", 0, 6), ("apples", 6, 24), ("fachwerk", 24, 38), ("hedges", 38, 54), ("grapes", 54, 68),
          ("sea", 68, 85), ("mafia", 85, 99), ("karlstein", 99, 113), ("home", 113, 128)]
LENGTH = 128.0
CAPS = {
    "title": [(0.4, "Ein Film über Äpfel, Trauben und kein Meer.")],
    "apples": [(0.5, "Station eins: Bittenfeld."), (4.5, "Fionn entdeckt die Streuobstwiese."),
               (9.0, "Fionn klaut Äpfel. Lennart hält ihn zurück."), (14.0, "Fionn: \"Das ist Recherche.\"")],
    "fachwerk": [(0.5, "Fionn liebt Fachwerk."), (6.0, "Er fotografiert jeden einzelnen Balken."), (10.5, "Lennart ist weniger beeindruckt.")],
    "hedges": [(0.5, "Fionn bemerkt: Hier gibt es keine Hecken."), (5.0, "Fionn betritt fremde Stückle."),
               (9.0, "Ein Schwabe bemerkt es."), (13.0, "Lennart entschuldigt sich. Schon wieder.")],
    "grapes": [(0.5, "Dann: die Weinberge."), (4.5, "Fionn klaut Trauben."), (9.5, "Seine Hosentaschen sind jetzt lila.")],
    "sea": [(0.5, "Fionn sucht das Meer."), (5.5, "Fionn findet das Meer. (Es ist Nebel.)"),
            (9.5, "Fionn findet das Meer. (Es ist die Alb.)"), (13.5, "Fionn findet das Meer. (Ein Ententeich.)")],
    "mafia": [(0.5, "Doch Fionn wird beobachtet."), (4.5, "Die Weinberg-Mafia stellt ihn."),
              (9.0, "Lennart verhandelt: Äpfel gegen Trauben."), (12.0, "Respekt. Fionn klaut trotzdem weiter.")],
    "karlstein": [(0.5, "Zum Schluss: Karlstein."), (6.5, "Abendrot. Ein Turm. Ein Kuss."), (11.0, "Fionn: \"Immer noch kein Meer.\"")],
    "home": [(0.5, "Zuhause in Bittenfeld."), (4.5, "Kamin, Tee und eine Decke für zwei."),
             (8.5, "Und ein Apfel. (Natürlich geklaut.)"), (12.0, "ENDE")],
}
for k, v in CAPS.items():
    li.CAPTIONS["f_" + k] = v

DIRTY_BLOND, BROWN, GREY = (172, 142, 88), (82, 50, 28), (200, 200, 205)
SKIN = {"F": (244, 206, 176), "L": (238, 194, 164), "B": (226, 178, 146), "M": (236, 196, 168)}
TOP = {"F": (84, 120, 152), "L": (66, 150, 84), "B": (60, 90, 170), "M": (22, 22, 28)}
LEG = {"F": (58, 60, 76), "L": (74, 60, 46), "B": (110, 90, 64), "M": (22, 22, 28)}


# ------------------------------------------------------------------ people ---

def _body(d, x, y, s, t, who, pose="stand", ph=0.0, bulge=0.0, puff=False, mood=None, item=None):
    """Fionn (F, dirty blond, denim jacket), Lennart (L, brown hair, TAGOS gear), a farmer (B) or a vineyard mafioso (M).
    Feet at (x, y), facing right. s = scale (1 ~ 30 px tall)."""
    def P(px, py):
        return (x + px * s, y + py * s)

    def line(a, b, col, w=2):
        d.line([P(*a), P(*b)], fill=col, width=max(1, int(round(w * s))))
    run = pose == "run"
    w = math.sin(t * (14 if run else 8) + ph) if pose in ("walk", "run") else 0.0
    bob = abs(w) * (1.4 if run else 0.9)
    hy = -25 - bob
    skin, top, leg = SKIN[who], TOP[who], LEG[who]
    if who == "L":                                                           # TAGOS rucksack behind
        d.rectangle([*P(-9, -23 - bob), *P(-4, -10 - bob)], fill=(236, 120, 30))
        d.rectangle([*P(-8, -21 - bob), *P(-5, -19 - bob)], fill=(180, 80, 20))
    if pose == "sit":
        line((-2, -9), (6, -8), leg, 3)
        line((6, -8), (6, 0), leg, 3)
        d.rectangle([*P(3, -1), *P(9, 1)], fill=(36, 30, 34))
    else:
        sw = 3 * (1.7 if run else 1) * w
        line((-2, -10 - bob), (-2 - sw, 0), leg, 3)
        line((2, -10 - bob), (2 + sw, 0), leg, 3)
        d.rectangle([*P(-5 - sw, -1), *P(-1 - sw, 1)], fill=(36, 30, 34))
        d.rectangle([*P(1 + sw, -1), *P(5 + sw, 1)], fill=(36, 30, 34))
    d.rectangle([*P(-4, -19 - bob), *P(4, -9 - bob)], fill=top)
    if who == "L":
        d.rectangle([*P(-4, -19 - bob), *P(4, -17.5 - bob)], fill=(236, 120, 30))
        d.polygon([P(-1, -16 - bob), P(2, -16 - bob), P(0.5, -13 - bob)], fill=(250, 250, 250))
    if who == "M":                                                            # white shirt and a red tie
        d.polygon([P(-1.5, -19 - bob), P(1.5, -19 - bob), P(0, -13 - bob)], fill=(240, 240, 240))
        d.line([P(0, -18 - bob), P(0, -13 - bob)], fill=(190, 20, 30), width=max(1, int(s)))
    if who == "B":                                                            # dungaree straps
        d.line([P(-2, -19), P(-2, -10)], fill=(40, 60, 130), width=max(1, int(s)))
        d.line([P(2, -19), P(2, -10)], fill=(40, 60, 130), width=max(1, int(s)))
    if bulge > 0:                                                             # pockets full of stolen grapes
        r = 1.5 + 2.2 * bulge
        for px in (-4.5, 4.5):
            d.ellipse([*P(px - r, -11 - r * 0.6), *P(px + r, -11 + r)], fill=(96, 40, 112))
            d.point(P(px - r * 0.4, -11 - r * 0.2), fill=(170, 110, 190))
    a = math.sin(t * 7 + ph)
    ra, la = (7 - 2 * w, -10 - bob), (-7 + 2 * w, -10 - bob)
    if run:
        ra, la = (9 - 5 * w, -13), (-9 + 5 * w, -13)
    elif pose == "eat":
        ra = (3.5, -22 + abs(a) * 1.2)
    elif pose == "hold":
        ra = (15, -21 + a * 0.6)
    elif pose == "reach":
        ra = (8 + a, -31 - abs(a))
    elif pose == "binoc":
        ra, la = (4, -24), (2, -24)
    elif pose == "scared":
        ra, la = (8, -30 - abs(a) * 2), (-8, -30 - abs(a) * 2)
    elif pose == "facepalm":
        ra = (2, -25)
    elif pose == "point":
        ra = (14, -24 + a * 0.5)
    elif pose == "cheer":
        ra, la = (8, -31 - abs(a) * 3), (-8, -31 - abs(a) * 3)
    elif pose == "wave":
        ra = (9, -29 + a * 3)
    elif pose == "hands":                                                     # arms out wide: "no hedges!"
        ra, la = (13, -22 + a * 2), (-13, -22 - a * 2)
    elif pose == "sit":
        ra, la = (6, -12), (-6, -12)
    line((4, -17 - bob), ra, skin)
    line((-4, -17 - bob), la, skin)
    if item == "apple" or (who == "F" and pose == "eat" and item is None):
        ax, ay = ra
        d.ellipse([*P(ax - 2, ay - 2.5), *P(ax + 2, ay + 1.5)], fill=(214, 40, 44))
        d.rectangle([*P(ax + 0.5, ay - 1.5), *P(ax + 2.5, ay + 0.5)], fill=skin)
    if item == "grapes":
        ax, ay = ra
        for i, (gx, gy) in enumerate(((0, 0), (1.6, 0.6), (-1.4, 0.8), (0.4, 2), (1.6, 2.2), (-0.8, 3))):
            d.ellipse([*P(ax + gx - 1.2, ay + gy - 1), *P(ax + gx + 1.2, ay + gy + 1.4)], fill=(100, 44, 120))
    if item == "pitchfork":
        ax, ay = ra
        d.line([P(ax, ay + 8), P(ax + 2, ay - 18)], fill=(130, 96, 60), width=max(1, int(s)))
        for k in (-2, 0, 2):
            d.line([P(ax + 2 + k, ay - 18), P(ax + 2 + k, ay - 24)], fill=(190, 190, 196), width=1)
    if item == "binocs":
        d.rectangle([*P(2, hy - 1), *P(8, hy + 3)], fill=(30, 30, 36))
    # head
    d.ellipse([*P(-5, hy - 5), *P(5, hy + 5)], fill=skin)
    if puff:
        d.ellipse([*P(-6.5, hy + 0), *P(-2, hy + 5)], fill=_mix(skin, (210, 120, 110), 0.25))
        d.ellipse([*P(2, hy + 0), *P(6.5, hy + 5)], fill=_mix(skin, (210, 120, 110), 0.25))
    if who == "F":                                                            # dirty blond, tousled
        d.chord([*P(-6.5, hy - 9), *P(6.5, hy + 2)], 180, 360, fill=DIRTY_BLOND)
        d.polygon([P(-5, hy - 4), P(-1, hy - 3), P(-4, hy - 1)], fill=DIRTY_BLOND)
        d.polygon([P(-3, hy - 8), P(-1, hy - 11), P(1, hy - 8.5), P(3, hy - 10.5), P(5, hy - 7)], fill=DIRTY_BLOND)
        d.rectangle([*P(4.5, hy - 4), *P(6, hy)], fill=DIRTY_BLOND)
    elif who == "L":
        d.chord([*P(-6.5, hy - 9), *P(6.5, hy + 2)], 180, 360, fill=BROWN)
        d.rectangle([*P(-6, hy - 4), *P(-4, hy + 1)], fill=BROWN)
        d.rectangle([*P(4, hy - 4), *P(6, hy + 1)], fill=BROWN)
        d.polygon([P(-3, hy - 8), P(-1, hy - 10.5), P(1, hy - 8.5), P(3, hy - 10), P(4, hy - 7)], fill=BROWN)
        d.rectangle([*P(-5, hy + 3), *P(5, hy + 5)], fill=(120, 80, 54))
    elif who == "B":                                                          # grey hair, straw hat, moustache
        d.chord([*P(-6, hy - 6), *P(6, hy + 3)], 180, 360, fill=GREY)
        d.ellipse([*P(-9, hy - 7), *P(9, hy - 3)], fill=(226, 190, 90))
        d.chord([*P(-5, hy - 12), *P(5, hy - 4)], 180, 360, fill=(236, 204, 110))
        d.line([P(-3, hy + 3), P(3, hy + 3)], fill=GREY, width=max(1, int(s)))
    else:                                                                     # mafioso: fedora and dark glasses
        d.ellipse([*P(-8.5, hy - 6.5), *P(8.5, hy - 3)], fill=(20, 20, 24))
        d.rectangle([*P(-4.5, hy - 12), *P(4.5, hy - 5)], fill=(20, 20, 24))
        d.rectangle([*P(-4.5, hy - 7), *P(4.5, hy - 6)], fill=(110, 20, 30))
        d.rectangle([*P(-4.5, hy - 1), *P(4.5, hy + 1.8)], fill=(10, 10, 12))
    blink = (t + ph) % 3.3 < 0.12
    mood = mood or {"eat": "chew", "scared": "open", "cheer": "smile", "facepalm": "flat"}.get(pose, "smile" if pose in ("walk", "stand", "wave") else "flat")
    if who != "M":
        wide = mood == "open" or pose == "binoc"
        for ex in (-2.5, 2.5):
            if blink:
                d.line([P(ex - 1, hy + 1), P(ex + 1, hy + 1)], fill=(30, 20, 30))
            elif wide:
                d.ellipse([*P(ex - 1.3, hy - 0.5), *P(ex + 1.3, hy + 2.3)], fill=(255, 255, 255), outline=(30, 20, 30))
                d.point(P(ex, hy + 1), fill=(30, 20, 30))
            else:
                d.point(P(ex, hy + 1), fill=(30, 20, 30))
    if mood == "chew":
        k = int(t * 5) % 2
        d.ellipse([*P(-1.6, hy + 2.5), *P(1.6, hy + 2.5 + 2 + k)], fill=(150, 50, 60))
    elif mood == "open":
        d.ellipse([*P(-1.8, hy + 2.5), *P(1.8, hy + 5.8)], fill=(120, 30, 40))
    elif mood == "smile":
        d.arc([*P(-2.5, hy + 1.5), *P(2.5, hy + 5)], 20, 160, fill=(150, 50, 60))
    elif who != "M":
        d.line([P(-1.5, hy + 3.5), P(1.5, hy + 3.5)], fill=(150, 50, 60))
    if pose == "binoc":
        d.rectangle([*P(0, hy - 1.5), *P(7, hy + 3)], fill=(30, 30, 36))
        d.rectangle([*P(6, hy - 2.5), *P(8.5, hy + 4)], fill=(60, 60, 70))


def person(img, x, y, s, t, who, pose="stand", ph=0.0, flip=False, **kw):
    """Draw onto img via a small transparent layer, so a person can face left (flip)."""
    cw, ch = 110, 120
    layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    _body(ImageDraw.Draw(layer), cw // 2, ch - 14, s, t, who, pose, ph, **kw)
    if flip:
        layer = layer.transpose(Image.FLIP_LEFT_RIGHT)
    img.paste(layer, (int(x - cw // 2), int(y - ch + 14)), layer)


def _say(d, x, y, txt, col=(190, 30, 40), pop=1.0):
    """A speech bubble whose tail points down to (x, y)."""
    f = font(8)
    lines = li._wrap(txt, 8, 120)
    wd = max(f.getlength(ln) for ln in lines) + 8
    hh = 11 * len(lines) + 3
    bx = min(max(x, wd / 2 + 2), W - wd / 2 - 2)
    top = y - hh * pop - 6
    d.rounded_rectangle([bx - wd / 2, top, bx + wd / 2, top + hh * pop], 4, fill=(255, 255, 255), outline=(30, 30, 40))
    d.polygon([(x - 2, top + hh * pop - 1), (x + 3, top + hh * pop - 1), (x, top + hh * pop + 6)], fill=(255, 255, 255))
    if pop > 0.95:
        for i, ln in enumerate(lines):
            d.text((bx, top + 8 + i * 11), ln, font=f, fill=col, anchor="mm")


def _talk(d, u, items):
    """items: (t0, t1, x, y, text, colour); shown while t0 <= u < t1."""
    for t0, t1, x, y, txt, col in items:
        if t0 <= u < t1:
            _say(d, x, y, txt, col, min(1.0, (u - t0) / 0.25))


def _grass(d, base):
    d.rectangle([0, base, W, H], fill=(86, 142, 66))
    rs = random.Random(3)
    for _ in range(90):
        x, y = rs.randrange(W), rs.randrange(base, H)
        d.line([(x, y), (x + 1, y - 2)], fill=(120, 176, 80))


def _star(d, x, y, r, col=(255, 240, 150)):
    d.line([(x - r, y), (x + r, y)], fill=col)
    d.line([(x, y - r), (x, y + r)], fill=col)
    d.point((x, y), fill=(255, 255, 255))


# ------------------------------------------------------------------ scenes ---

def _title(u, t):
    img = _sky((20, 34, 80), (240, 150, 110), H, mid=(150, 90, 130))
    d = ImageDraw.Draw(img)
    for i, (x, w, h) in enumerate(((0, 44, 70), (44, 36, 56), (84, 40, 80), (124, 34, 60), (158, 40, 74))):
        _fachwerk(d, x, 196, w, h, ((232, 214, 184), (206, 190, 150), (226, 196, 176))[i % 3], (82, 54, 40), (140, 62, 54))
    d.rectangle([0, 196, W, H], fill=(86, 78, 90))
    k = _ease(u / 1.2)
    _text(d, (W / 2, 30), "Lennart zeigt", int(10 + 8 * k), (255, 236, 200), stroke=2)
    _text(d, (W / 2, 62), "Fionn", int(14 + 20 * k), (255, 214, 120), stroke=3)
    _text(d, (W / 2, 96), "das Ländle", int(10 + 10 * k), (255, 236, 200), stroke=2)
    x = -20 + (W * 0.5 + 40) * _ease(u / 5.5)
    person(img, x, 200, 1.9, t, "F", "eat", 0.7)
    person(img, x - 28, 200, 1.9, t, "L", "walk", 0.0)
    return img


def _apples(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((126, 186, 244), (222, 238, 252), int(H * 0.62)), (0, 0))
    d = ImageDraw.Draw(img)
    _hills(d, H * 0.44, 8, (130, 168, 150), 4)
    _hills(d, H * 0.52, 10, (96, 156, 92), 5, stripes=(130, 180, 100))
    _house(d, 118, int(H * 0.54), 22, 12, (240, 220, 190), (190, 80, 60), (90, 110, 140))
    base = int(H * 0.60)
    _grass(d, base)
    for i in range(3):
        cx = (i * 70 + t * 3) % (W + 60) - 30
        d.ellipse([cx - 14, 20 + i * 18, cx + 14, 30 + i * 18], fill=(250, 250, 252))
    _tree(d, 150, base + 42, 1.6, t, 2)
    _tree(d, 34, base + 50, 1.4, t, 1)
    per = 3.4
    q = (u % per) / per
    n = int(u / per) + (1 if q > 0.4 else 0)
    lunge = 6 * math.sin(min(1.0, q / 0.4) * math.pi) if q < 0.4 else 0
    fx = 100 + lunge + (0 if q < 0.4 else 2)
    pose = "reach" if q < 0.4 else ("eat" if q < 0.85 else "stand")
    person(img, 70, 206, 1.9, t, "L", "hold", 0.0, mood="flat")
    person(img, fx, 206, 1.9, t, "F", pose, 1.2, puff=0.45 < q < 0.85, item=None if pose == "eat" else "none")
    d = ImageDraw.Draw(img)
    if q >= 0.85:                                         # the core flies away
        k = (q - 0.85) / 0.15
        d.ellipse([fx + 10 + k * 30 - 1.5, 168 - 20 * math.sin(k * math.pi) + k * 30 - 1.5, fx + 10 + k * 30 + 1.5, 168 - 20 * math.sin(k * math.pi) + k * 30 + 1.5], fill=(150, 120, 80))
    _text(d, (W - 40, 12), f"Äpfel geklaut: {n}", 9, (255, 236, 180), stroke=1)
    _talk(d, u, [(1.0, 3.2, 70, 140, "Fionn! Nein!", (190, 30, 40)), (4.5, 7.2, 70, 140, "Das sind nicht unsere!", (190, 30, 40)),
                 (8.0, 10.5, 70, 140, "Fionn. FIONN.", (190, 30, 40)), (11.5, 14.0, 70, 140, "Wir haben Obst zuhause.", (190, 30, 40)),
                 (15.0, 17.5, 70, 140, "Schluss jetzt!", (190, 30, 40)),
                 (3.4, 4.6, fx, 134, "Mmmh.", (40, 40, 120)), (7.2, 8.4, fx, 134, "Kein Zaun, kein Problem.", (40, 40, 120)),
                 (10.6, 11.6, fx, 134, "Nur noch einen.", (40, 40, 120)), (14.0, 15.0, fx, 134, "*mampf*", (40, 40, 120)),
                 (17.0, 18.0, fx, 134, "Das ist Recherche.", (40, 40, 120))])
    return img


def _fachwerk_scene(u, t):
    img = _sky((130, 190, 244), (236, 232, 220), int(H * 0.6))
    full = Image.new("RGB", (W, H), (120, 110, 120))
    full.paste(img, (0, 0))
    d = ImageDraw.Draw(full)
    base = int(H * 0.68)
    walls = [(232, 214, 184), (206, 190, 150), (226, 196, 176), (214, 224, 196)]
    for i, (x, w, h) in enumerate(((-6, 52, 96), (44, 40, 78), (82, 34, 100), (114, 40, 82), (152, 50, 94))):
        _fachwerk(d, x, base + 4, w, h, walls[i % 4], (82, 54, 40), (140, 62, 54), lit=False)
    _church(d, 100, base - 90, 20, (200, 190, 176))
    d.rectangle([0, base + 4, W, H], fill=(104, 96, 106))
    for yy in range(base + 6, H, 7):
        for xx in range(((yy // 7) % 2) * 4, W, 8):
            d.rectangle([xx, yy, xx + 6, yy + 4], fill=(112 + (xx * 7 + yy) % 14, 104, 114))
    fx = 40 + 56 * _ease(u / 6)
    for i in range(8):                                                   # sparkles around the beams
        x = (i * 41 + 13) % W
        y = base - 60 + (i * 29) % 70
        if int(u * 3 + i) % 3 != 0:
            _star(d, x, y, 2 + (i % 2))
    for fl in (6.0, 8.5, 10.5):                                          # camera flashes
        if fl <= u < fl + 0.18:
            d.rectangle([0, 0, W, H], fill=(255, 255, 255))
    person(full, fx, 206, 1.9, t, "F", "cheer", 0.5)
    person(full, 28, 210, 1.9, t, "L", "stand", 0.0, mood="flat")
    d = ImageDraw.Draw(full)
    _talk(d, u, [(1.0, 4.5, fx, 148, "FACHWERK!!", (150, 40, 150)), (5.0, 8.5, fx, 148, "Das ist UNGLAUBLICH!", (150, 40, 150)),
                 (9.0, 13.5, fx, 148, "Wer baut so was?!", (150, 40, 150)),
                 (4.8, 8.0, 28, 150, "Ja, Fionn. Fachwerk.", (190, 30, 40)), (9.0, 13.5, 28, 150, "Es ist ein Haus.", (190, 30, 40))])
    return full


def _hedges(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((130, 190, 244), (226, 238, 252), int(H * 0.45)), (0, 0))
    d = ImageDraw.Draw(img)
    _hills(d, H * 0.38, 8, (130, 160, 170), 4)
    _hills(d, H * 0.44, 7, (110, 160, 110), 5)
    base = int(H * 0.5)
    cols = [(110, 168, 78), (150, 176, 84), (96, 150, 70), (176, 170, 90), (120, 160, 80)]
    for row in range(5):                                                 # a patchwork of open Stückle
        y0 = base + row * 22
        for i in range(4):
            x0 = i * 52 - (row % 2) * 20
            d.polygon([(x0, y0), (x0 + 52, y0), (x0 + 52 + 6, y0 + 22), (x0 - 6, y0 + 22)], fill=cols[(i + row) % 5])
            if (i + row) % 3 == 0:
                for s_ in range(6):
                    d.line([(x0 + 4, y0 + 3 + s_ * 3), (x0 + 48, y0 + 3 + s_ * 3)], fill=_mix(cols[(i + row) % 5], (60, 100, 50), 0.4))
    for i in range(5):                                                   # signs on posts
        px = 18 + i * 42
        d.rectangle([px, base + 14 + (i % 2) * 28, px + 1, base + 26 + (i % 2) * 28], fill=(110, 76, 44))
        d.rectangle([px - 8, base + 6 + (i % 2) * 28, px + 9, base + 15 + (i % 2) * 28], fill=(250, 244, 220), outline=(120, 40, 40))
        _text(d, (px + 0.5, base + 10.5 + (i % 2) * 28), "PRIVAT", 5, (150, 30, 30), stroke=0)
    fx = -12 + 120 * _c(u / 8.0) if u < 8.5 else 108 - 100 * _c((u - 8.5) / 5.0)
    fy = 190 - (fx - 40) * 0.05 if u < 8.5 else 190
    pose_f = "hands" if u < 8.5 else "run"
    person(img, fx, fy, 1.9, t, "F", pose_f, 0.4, flip=u >= 8.5)
    if u >= 8.0:
        bx = 215 - 180 * _c((u - 8.0) / 5.0)
        person(img, bx, 196, 1.9, t, "B", "run", 0.0, flip=True, item="pitchfork")
    lx = 150 if u < 8.5 else 150
    bow = 1 if (u > 13.0 and int(u * 2) % 2 == 0) else 0
    person(img, lx, 220 + bow, 1.9, t, "L", "stand" if u < 13 else "facepalm", 0.0, flip=True)
    d = ImageDraw.Draw(img)
    _talk(d, u, [(0.8, 4.0, fx, fy - 60, "Wo sind die Hecken?!", (40, 40, 120)), (4.5, 8.2, fx, fy - 60, "KEINE HECKEN! Man darf einfach rein!", (40, 40, 120)),
                 (2.0, 5.0, lx, 150, "Fionn, das ist Privatgrund.", (190, 30, 40)), (8.8, 12.5, bx if u >= 8.0 else 0, 124, "Des isch mei Stückle!", (30, 60, 150)) if u >= 8.0 else (0, 0, 0, 0, "", (0, 0, 0)),
                 (9.5, 12.8, lx, 150, "Entschuldigung!", (190, 30, 40)), (13.2, 15.8, lx, 150, "Das passiert öfter.", (190, 30, 40))])
    return img


def _grapes(u, t):
    img = li._vines(11.0 + u * 0.3, t, people=False)
    d = ImageDraw.Draw(img)
    n = int(u * 1.4)
    bulge = _c(u / 10.0)
    py = int(H * 0.68)
    person(img, 110, py + 28, 2.0, t, "F", "eat", 0.3, bulge=bulge, puff=int(u * 3) % 2 == 0, item="grapes")
    person(img, 62, py + 30, 2.0, t, "L", "facepalm", 0.0)
    d = ImageDraw.Draw(img)
    for i in range(3):
        _bird(d, (i * 60 + t * 12) % (W + 40) - 20, 22 + i * 12, t + i)
    _text(d, (W - 38, 12), f"Trauben geklaut: {n}", 9, (255, 236, 180), stroke=1)
    _talk(d, u, [(1.0, 4.0, 62, py - 34, "Das sind Weintrauben.", (190, 30, 40)), (5.0, 8.8, 62, py - 34, "Fionn. Das ist ein Weinberg, kein Buffet.", (190, 30, 40)),
                 (9.8, 13.5, 62, py - 34, "Deine Taschen sind lila.", (190, 30, 40)),
                 (4.2, 5.2, 110, py - 38, "Mmmh!", (40, 40, 120)), (8.8, 9.8, 110, py - 38, "Zur Probe.", (40, 40, 120)), (12.0, 13.8, 110, py - 38, "*glucks*", (40, 40, 120))])
    return img


def _sea(u, t):
    k = _c(u / 17)
    img = Image.new("RGB", (W, H))
    img.paste(_sky((110, 170, 240), (250, 232, 200), int(H * 0.6)), (0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(0, H * 0.34)] + [(x, H * 0.34 - 6 - 5 * math.sin(x / 24) - 3 * math.sin(x / 9)) for x in range(0, W + 4, 4)] + [(W, H * 0.46), (0, H * 0.46)], fill=(90, 110, 170) if 9 <= u < 13.5 else (120, 140, 190))
    if 9 <= u < 14:
        _text(d, (W / 2, H * 0.27), "~ ~ ~", 8, (220, 230, 255), stroke=0)
    d.rectangle([0, H * 0.43, W, H * 0.62], fill=(110, 150, 90))
    fog_on = 5 <= u < 9.5
    fog = 1.0 if fog_on else max(0.0, 1 - _c((u - 9.5) / 1.0)) if u >= 9.5 else _c((u - 4.5) / 0.5)
    if u < 4.5:
        fog = 0.0
    if fog > 0:
        fl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fl)
        for row in range(14):                                            # fog with waves: it really does look like a sea
            y = H * 0.44 + row * 5
            pts = [(x, y + 2.2 * math.sin(x / 11 + t * 1.8 + row)) for x in range(0, W + 4, 4)]
            fd.polygon(pts + [(W, H * 0.64), (0, H * 0.64)], fill=(236, 240, 250, int(210 * fog)) if row == 0 else (226, 232, 246, int(60 * fog)))
        img.paste(fl, (0, 0), fl)
        d = ImageDraw.Draw(img)
    d.rectangle([0, H * 0.62, W, H], fill=(104, 140, 74))
    d.polygon([(0, H * 0.7), (W, H * 0.66), (W, H), (0, H)], fill=(120, 154, 84))
    if u >= 13:                                                          # the duck pond
        d.ellipse([112, 210, 176, 232], fill=(70, 130, 190))
        d.ellipse([140, 214, 152, 221], fill=(250, 250, 250))
        d.ellipse([149, 209, 155, 215], fill=(30, 110, 60))
        d.polygon([(155, 212), (160, 213), (155, 214)], fill=(255, 150, 0))
    d.rectangle([160, 150, 162, 190], fill=(110, 76, 44))
    d.rectangle([128, 142, 190, 152], fill=(240, 224, 170), outline=(110, 76, 44))
    _text(d, (159, 147), "BODENSEE 160 KM >", 5, (60, 40, 20), stroke=0)
    d.rectangle([128, 156, 190, 166], fill=(240, 224, 170), outline=(110, 76, 44))
    _text(d, (159, 161), "NORDSEE 650 KM >", 5, (60, 40, 20), stroke=0)
    look = math.sin(u * 1.4) if u < 5 else 0.0
    pose = "binoc" if u < 9 or u >= 13 else "point"
    if 5 <= u < 9:
        pose = "cheer"
    person(img, 70 + look * 6, 206, 2.0, t, "F", pose, 0.4, mood="open" if 5 <= u < 9 or u >= 13 else None)
    person(img, 38, 210, 2.0, t, "L", "stand", 0.0, mood="flat")
    d = ImageDraw.Draw(img)
    _talk(d, u, [(0.6, 4.6, 70, 140, "Wo ist das Meer?", (40, 40, 120)), (5.2, 9.0, 70, 134, "MEER!! Ich sehe es!!", (40, 40, 120)),
                 (9.8, 13.0, 70, 140, "Und DAS da?", (40, 40, 120)), (13.6, 16.8, 70, 134, "DAS MEER?!", (40, 40, 120)),
                 (6.8, 9.5, 38, 150, "Das ist Nebel.", (190, 30, 40)), (11.0, 13.8, 38, 150, "Die Schwäbische Alb.", (190, 30, 40)),
                 (15.0, 17.0, 38, 150, "...Ententeich.", (190, 30, 40))])
    return img


def _mafia(u, t):
    img = Image.new("RGB", (W, H))
    img.paste(_sky((28, 24, 70), (230, 110, 90), int(H * 0.6)), (0, 0))
    d = ImageDraw.Draw(img)
    _hills(d, H * 0.44, 8, (70, 54, 100), 21)
    _hills(d, H * 0.52, 10, (52, 50, 84), 22, stripes=(110, 80, 110))
    d.rectangle([0, int(H * 0.56), W, H], fill=(60, 74, 60))
    for row in range(8):
        y = int(H * 0.58) + row * 9
        d.line([(0, y), (W, y)], fill=(46, 58, 46))
    d.rectangle([0, 186, W, 232], fill=(150, 130, 100))
    # the black car with its lights on
    cx = 168
    d.rounded_rectangle([cx - 22, 160, cx + 22, 188], 5, fill=(14, 14, 18))
    d.rectangle([cx - 14, 152, cx + 12, 162], fill=(14, 14, 18))
    d.rectangle([cx - 11, 154, cx + 9, 161], fill=(60, 80, 110))
    for wx in (cx - 14, cx + 14):
        d.ellipse([wx - 5, 184, wx + 5, 194], fill=(8, 8, 10))
    d.polygon([(cx - 22, 170), (cx - 70, 160), (cx - 70, 186)], fill=(255, 240, 190))
    d.ellipse([cx - 25, 168, cx - 19, 175], fill=(255, 250, 220))
    sc = _c((u - 1.5) / 4.0)
    mx = [W + 14 - sc * 70 + i * 17 for i in range(4)] if u < 9.5 else [W - 56 + i * 17 for i in range(4)]
    bow = u >= 11.0
    fx = 44 if u < 4.5 else 40
    scared = 4.5 <= u < 11
    person(img, fx, 214, 2.0, t, "F", "scared" if scared else ("eat" if u < 4.5 else "stand"), 0.3, mood="open" if scared else None, item="grapes" if u < 4.5 else None)
    for i, x in enumerate(mx):
        wlk = "walk" if (u < 6.0 and sc < 1) else "stand"
        person(img, x, 206 + (i % 2) * 5, 1.9, t, "M", wlk, i * 0.8, flip=True)
    if u >= 8.5:
        person(img, 80, 216, 2.0, t, "L", "hold", 0.0)
    d = ImageDraw.Draw(img)
    if u >= 10.0:                                                        # the deal: apples fly to the mafia
        for i in range(3):
            k = _c((u - 10.0 - i * 0.4) / 1.4)
            if 0 < k < 1:
                _apple(d, 94 + (mx[0] - 94) * k, 176 - 26 * math.sin(k * math.pi), 2.2)
    if u >= 11.2:
        for i, x in enumerate(mx):
            _heart(d, x + 2, 170 - ((u - 11.2) * 8 + i * 5) % 14, 2.5, (255, 90, 140))
    _talk(d, u, [(2.4, 6.0, mx[0] + 4, 150, "Du hast unsere Trauben.", (30, 30, 40)), (6.2, 9.2, mx[1] + 4, 150, "Wir sind die Weinberg-Mafia.", (30, 30, 40)),
                 (5.0, 8.2, fx, 140, "Ich dachte, die sind frei!", (40, 40, 120)), (9.2, 12.0, 80, 140, "Wir zahlen in Äpfeln!", (190, 30, 40)),
                 (12.2, 14.0, mx[0] + 4, 150, "Respekt.", (30, 30, 40))])
    return img


def _karlstein(u, t):
    k = _c(u / 12)
    img = Image.new("RGB", (W, H))
    img.paste(_sky(_mix((90, 80, 170), (30, 20, 70), k), _mix((255, 170, 110), (255, 90, 120), k), int(H * 0.7), mid=_mix((240, 120, 140), (210, 70, 130), k)), (0, 0))
    d = ImageDraw.Draw(img)
    sy = H * 0.42 + 22 * _ease(u / 13)
    for r, a in ((26, 0.25), (15, 1.0)):
        d.ellipse([W * 0.7 - r, sy - r, W * 0.7 + r, sy + r], fill=_mix((255, 140, 100), (255, 224, 150), a))
    _hills(d, H * 0.52, 8, _mix((130, 80, 130), (60, 40, 96), k), 31)
    _hills(d, H * 0.60, 8, _mix((100, 64, 110), (44, 30, 80), k), 32)
    d.polygon([(0, H), (0, H * 0.74), (W * 0.45, H * 0.66), (W, H * 0.78), (W, H)], fill=(36, 36, 52))
    tx, ty = 138, int(H * 0.69)                                          # the ruined tower of Karlstein
    d.rectangle([tx, ty - 46, tx + 22, ty + 6], fill=(60, 54, 74))
    for i in range(4):
        d.rectangle([tx + i * 6, ty - 52, tx + i * 6 + 3, ty - 46], fill=(60, 54, 74))
    d.rectangle([tx + 9, ty - 34, tx + 13, ty - 26], fill=(255, 200, 100))
    d.rectangle([34, ty - 8, 36, ty + 14], fill=(110, 76, 44))
    d.rectangle([14, ty - 22, 58, ty - 8], fill=(240, 224, 170), outline=(110, 76, 44))
    _text(d, (36, ty - 15), "KARLSTEIN", 7, (60, 40, 20), stroke=0)
    for i in range(10):
        if u > 3 + i * 0.5:
            _star(d, (i * 71 + 9) % W, 10 + (i * 37) % 70, 1, (255, 250, 220))
    kiss = u >= 7.0
    if not kiss:
        wx = -14 + 104 * _ease(u / 7.0)
        person(img, wx + 12, 210, 2.0, t, "F", "walk", 0.2)
        person(img, wx - 12, 210, 2.0, t, "L", "walk", 0.2)
        d = ImageDraw.Draw(img)
        d.line([(wx + 2, 183), (wx + 8, 184)], fill=(244, 206, 176), width=2)         # holding hands
    else:
        lean = _ease((u - 7.0) / 1.2)
        person(img, 88 + 3 * lean, 210, 2.0, t * 0.0, "L", "stand", 0.0, mood="flat")
        person(img, 107 - 3 * lean, 210, 2.0, t * 0.0, "F", "stand", 0.0, flip=True, mood="flat")
        d = ImageDraw.Draw(img)
        if lean > 0.9:
            for j in range(6):
                _heart(d, 98 + math.sin(t * 2 + j * 1.3) * 16, 150 - ((u - 8) * 10 + j * 9) % 54, 3 + (j % 2), (255, 90, 150))
    d = ImageDraw.Draw(img)
    _talk(d, u, [(11.4, 14.0, 106, 150, "Immer noch kein Meer.", (40, 40, 120))] if u >= 11.4 else [])
    _talk(d, u, [(13.0, 14.0, 90, 150, "Ich weiß.", (190, 30, 40))] if u >= 13.0 else [])
    return img


def _home(u, t):
    img = Image.new("RGB", (W, H), (84, 52, 38))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 170], fill=(236, 220, 188))                    # plaster wall with dark beams
    for x in (0, 62, 130, 188):
        d.rectangle([x, 0, x + 4, 170], fill=(80, 50, 36))
    for y in (0, 56, 112):
        d.rectangle([0, y, W, y + 4], fill=(80, 50, 36))
    d.line([(4, 56), (62, 112)], fill=(80, 50, 36), width=3)
    d.rectangle([14, 64, 54, 108], fill=(30, 40, 90), outline=(80, 50, 36), width=3)       # window onto the night
    rs = random.Random(5)
    for i in range(14):
        d.point((16 + rs.randrange(36), 66 + rs.randrange(40)), fill=(240, 240, 255))
    for i in range(16):
        sx, sy = 16 + (i * 7 + t * 6) % 38, 66 + (i * 13 + t * 14) % 40
        d.point((sx, sy), fill=(255, 255, 255))
    d.line([(34, 64), (34, 108)], fill=(80, 50, 36), width=2)
    d.rectangle([128, 78, 184, 170], fill=(110, 100, 104))               # fireplace
    d.rectangle([138, 108, 174, 170], fill=(24, 18, 18))
    for i in range(7):
        fx = 142 + i * 5
        h = 14 + 10 * math.sin(t * 7 + i * 2) + (i % 3) * 5
        d.polygon([(fx - 3, 170), (fx + 1 + math.sin(t * 5 + i) * 2, 170 - h), (fx + 4, 170)], fill=(255, 150 + (i % 3) * 30, 40))
    for yy in range(0, 3):                                               # string lights
        pts = [(x, 6 + 6 * math.sin((x / W) * math.pi)) for x in range(0, W + 4, 4)]
    d.line(pts, fill=(70, 50, 40))
    for j, (x, y) in enumerate(pts[::3]):
        d.ellipse([x - 1.5, y, x + 1.5, y + 3], fill=(255, 220, 130) if (int(t * 2) + j) % 3 else (200, 130, 80))
    d.rectangle([0, 170, W, H], fill=(120, 76, 50))                      # floor and rug
    d.ellipse([20, 214, 170, 246], fill=(150, 56, 60))
    d.ellipse([34, 220, 156, 240], fill=(190, 90, 84))
    d.rounded_rectangle([34, 130, 124, 176], 6, fill=(70, 94, 120))      # the sofa
    d.rounded_rectangle([28, 148, 44, 192], 5, fill=(60, 82, 108))
    d.rounded_rectangle([114, 148, 130, 192], 5, fill=(60, 82, 108))
    person(img, 62, 186, 1.9, t * 0.3, "L", "sit", 0.0, mood="smile")
    person(img, 90, 186, 1.9, t * 0.3, "F", "sit", 0.5, flip=True, mood="smile")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([34, 164, 124, 194], 5, fill=(214, 120, 70))     # the blanket for two
    for i in range(0, 90, 10):
        d.line([(34 + i, 164), (34 + i, 194)], fill=(234, 160, 100))
    for i in range(0, 30, 10):
        d.line([(34, 164 + i), (124, 164 + i)], fill=(234, 160, 100))
    d.rounded_rectangle([28, 186, 130, 196], 4, fill=(60, 82, 108))
    d.rectangle([14, 206, 46, 212], fill=(120, 80, 54))                  # a little table: tea and apples
    d.rectangle([16, 212, 19, 232], fill=(96, 62, 36))
    d.rectangle([42, 212, 45, 232], fill=(96, 62, 36))
    for j, mx in enumerate((18, 26)):
        d.rectangle([mx, 198, mx + 5, 206], fill=(236, 236, 240))
        for s_ in range(3):
            sy = 194 - ((t * 8 + s_ * 4 + j * 2) % 12)
            d.point((mx + 2 + math.sin(t + s_), sy), fill=(230, 230, 240))
    left = max(0, 5 - int(u / 3.0))
    d.ellipse([30, 200, 44, 207], fill=(150, 98, 48))
    for i in range(left):
        _apple(d, 33 + (i % 3) * 4, 199 - (i // 3) * 2, 1.8)
    if int(u) % 3 == 2 and u > 7:                                        # a stolen apple floats to Fionn
        kk = (u % 1.0)
        _apple(d, 40 + (92 - 40) * kk, 200 - 40 * math.sin(kk * math.pi) - 20 * kk, 2.2)
    cat_y = 236
    d.ellipse([140, cat_y - 8, 164, cat_y + 4], fill=(70, 70, 80))
    d.ellipse([158, cat_y - 12, 170, cat_y], fill=(70, 70, 80))
    d.polygon([(159, cat_y - 11), (161, cat_y - 17), (163, cat_y - 11)], fill=(70, 70, 80))
    d.polygon([(165, cat_y - 11), (167, cat_y - 17), (169, cat_y - 11)], fill=(70, 70, 80))
    if int(t * 0.8) % 2 == 0:
        _text(d, (156, cat_y - 26 - (t * 5) % 8), "z", 8, (230, 230, 255), stroke=0)
    if u > 12.0:
        k = _ease((u - 12.0) / 0.8)
        for j in range(8):
            _heart(d, 96 + math.sin(t * 2 + j) * 40, 120 - ((u - 12) * 9 + j * 8) % 70, 3, (255, 90, 140))
        _text(d, (W / 2, 70), "ENDE", int(8 + 22 * k), (255, 236, 200), stroke=3)
    return img


SCENE_FN = {"title": _title, "apples": _apples, "fachwerk": _fachwerk_scene, "hedges": _hedges, "grapes": _grapes,
            "sea": _sea, "mafia": _mafia, "karlstein": _karlstein, "home": _home}


def frame(t):
    t = t % LENGTH
    for name, a, b in SCENES:
        if a <= t < b:
            u = t - a
            img = SCENE_FN[name](u, t)
            li._caption(img, "f_" + name, u)
            fade = min(_c(u / 0.4), _c((b - t) / 0.4))
            if fade < 1:
                img = Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8), "RGB")
            return img
    return Image.new("RGB", (W, H))


def thumb():
    return frame(14.0)
