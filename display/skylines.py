"""Skylines: a new city every hour, as a flat silhouette under the sky that city really has right now.

On the hour (Zürich wall-clock) the wall slowly cross-fades (about 20 s) to the next of 24 cities, one per
hour of the day, ordered so most of them are in or near their own evening when they come up. Each is a
flat dark silhouette in the lower 45% of the wall (with a paler far layer behind it) under a big sky.

What is REAL: the sun and the moon. Their altitude and azimuth for the city's coordinates and the actual
instant are computed locally (the low-precision almanac of display/satellites.py), so the sky goes
night / dawn / day / dusk exactly as there, stars come out when the sun is well down, the moon stands where
it really is, in its real phase and tilt, and the windows light up with the city's local evening (many at
20:00, few at 04:00, a handful always on). The weather is Open-Meteo's (free, no key; cloud cover, rain,
snow, fog, wind) for the city on screen only, fetched on a side thread (the next city is prefetched), kept
in panel_setup/skylines_cache.json, and offline it quietly becomes a clear sky.

What is NOT: the skylines. They are stylised, not survey-accurate: a few hand-authored landmark shapes
(Eiffel, Skytree, Burj Khalifa, the Opera House sails ...) over seeded, deterministic fields of generic
buildings shaped per city (dense for Hong Kong, low for Paris). Recognisable, not a plan.

Everything is whole LEDs (no anti-aliasing); the sky gradient is ordered-dithered so it does not band.
The still layers of a city are drawn once; per frame only sky, weather, lights and the label are composed.
"""
import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageDraw

import config
from display import pixelfont
from display.satellites import gmst, jd, moon_eci, sun_eci

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "panel_setup", "skylines_cache.json")
URL = "https://api.open-meteo.com/v1/forecast"
FADE = 20.0                    # seconds of cross-fade at xx:00
STALE = 45 * 60.0              # refetch a city's weather when older than this
USABLE = 6 * 3600.0            # offline: weather older than this is ignored (clear sky)
IDLE = 120.0                   # no frame drawn for this long: the piece is not showing, stop fetching
LS = 1.12                      # landmarks drawn a little larger than their nominal LEDs
HS = 1.3                       # and the generic buildings
SKYLINE_MAX = 0.45             # the skyline stays in the lower 45% of the wall
FOV = 170.0                    # degrees of horizon across the wall
ZURICH = ZoneInfo("Europe/Zurich")


def _now():
    """Unix seconds. Module level so tests can mock it."""
    return time.time()


# =========================================================================== canvas ===
class Canvas:
    """Draws one silhouette layer. Coordinates: x in LEDs from the left, heights in LEDs up from the ground
    line (row yb - 1). Everything is aliased (whole LEDs)."""

    def __init__(self, yb):
        self.yb = yb
        self.im = Image.new("L", (W, H), 0)
        self.d = ImageDraw.Draw(self.im)
        self.blocks = []        # (x0, x1, h0, h1) rectangles that carry windows
        self.beacons = []       # (x, h) red aircraft lights

    def R(self, x0, x1, h1, h0=0, win=False, v=255):
        x0, x1, h1, h0 = int(round(x0)), int(round(x1)), int(round(h1)), int(round(h0))
        if x1 < x0 or h1 <= h0:
            return
        self.d.rectangle([x0, self.yb - h1, x1, self.yb - 1 - h0], fill=v)
        if win and v:
            self.blocks.append((x0, x1, h0, h1))

    def P(self, pts, v=255):
        self.d.polygon([(int(round(x)), self.yb - int(round(h))) for x, h in pts], fill=v)

    def E(self, cx, ch, rx, ry, v=255):
        self.d.ellipse([int(round(cx - rx)), self.yb - int(round(ch + ry)),
                        int(round(cx + rx)), self.yb - int(round(ch - ry))], fill=v)

    def Lw(self, x0, h0, x1, h1, w=1, v=255):
        self.d.line([(int(round(x0)), self.yb - int(round(h0))), (int(round(x1)), self.yb - int(round(h1)))],
                    fill=v, width=w)

    def A(self, cx, ch, rx, ry, a0, a1, w=1, v=255):
        """Arc of an ellipse, degrees counter-clockwise from +x (so 0..180 is the upper half)."""
        self.d.arc([int(round(cx - rx)), self.yb - int(round(ch + ry)), int(round(cx + rx)), self.yb - int(round(ch - ry))],
                   -a1, -a0, fill=v, width=w)

    def Dm(self, cx, h0, rx, ry, v=255):
        """A solid dome (upper half ellipse) standing on height h0."""
        pts = [(cx + rx * math.cos(math.radians(a)), h0 + ry * math.sin(math.radians(a))) for a in range(0, 181, 10)]
        self.P(pts, v=v)

    def beacon(self, x, h):
        self.beacons.append((int(round(x)), int(round(h))))

    def mask(self):
        return np.asarray(self.im) > 127


# ======================================================================== landmarks ===
LM = {}


def lm(fn):
    LM[fn.__name__] = fn
    return fn


def _prof(c, x, h, f, y0=0, step=2):
    """A tower of half-width f(y) for y in [y0, h]."""
    L, Rr = [], []
    for y in range(y0, int(h) + 1, step):
        w = f(y)
        L.append((x - w, y))
        Rr.append((x + w, y))
    L.append((x - f(h), h))
    Rr.append((x + f(h), h))
    c.P(L + Rr[::-1])


@lm
def eiffel(c, x, s=1.0):
    h, hw = int(80 * s), 16 * s
    f = lambda y: hw * (1 - y / h) ** 2.3 + 0.6
    _prof(c, x, h, f)
    c.E(x, 0, f(0) * 0.55, 15 * s, v=0)                          # the great arch
    for y in (int(0.30 * h), int(0.60 * h)):                     # platforms
        c.R(x - f(y) - 1, x + f(y) + 1, y + 2, y)
    for y in range(int(0.34 * h), int(0.58 * h), 5):             # lattice hints
        c.R(x - 1, x, y + 3, y + 1, v=0)
    c.R(x, x, h + 8 * s, h)
    c.beacon(x, h + 8 * s)


@lm
def tokyotower(c, x, s=1.0):
    h, hw = int(88 * s), 10 * s
    f = lambda y: hw * (1 - y / (0.8 * h)) ** 1.6 + 0.8
    _prof(c, x, int(0.8 * h), f)
    c.E(x, 0, f(0) * 0.5, 9 * s, v=0)
    for y in (int(0.27 * h), int(0.5 * h)):
        c.R(x - f(y) - 1, x + f(y) + 1, y + 3, y)
    c.R(x, x, h + 6, int(0.8 * h))
    c.beacon(x, h + 6)


@lm
def skytree(c, x, s=1.0):
    h = int(112 * s)
    _prof(c, x, int(0.8 * h), lambda y: 4.0 * s * (1 - y / (0.8 * h)) + 1.5, step=3)
    c.E(x, 0.62 * h, 6.5 * s, 3.2 * s)                           # the observation decks
    c.E(x, 0.74 * h, 4.5 * s, 2.4 * s)
    c.R(x, x, h, int(0.78 * h))
    c.beacon(x, h)


@lm
def shibuya(c, x, s=1.0):
    h = int(48 * s)
    c.R(x - 8 * s, x + 8 * s, h, 0, win=True)
    c.R(x - 9 * s, x + 9 * s, h + 2, h)                          # the roof deck, wider
    c.R(x - 6 * s, x - 6 * s, h + 5, h + 2)
    c.R(x + 6 * s, x + 6 * s, h + 5, h + 2)
    c.R(x - 6 * s, x + 6 * s, h + 5, h + 4)


@lm
def empire(c, x, s=1.0):
    for hw, a, b in [(10, 0, 40), (8, 40, 52), (6, 52, 64), (4, 64, 74), (2.6, 74, 80)]:
        c.R(x - hw * s, x + hw * s, b * s, a * s, win=hw > 3)
    c.R(x - 1, x + 1, 86 * s, 80 * s)
    c.R(x, x, 98 * s + 14 * s, 86 * s)
    c.beacon(x, 112 * s)


@lm
def chrysler(c, x, s=1.0):
    c.R(x - 7 * s, x + 7 * s, 58 * s, 0, win=True)
    c.R(x - 5 * s, x + 5 * s, 66 * s, 58 * s)
    for i, r in enumerate((6, 5, 4, 3, 2)):                      # the sunburst crown
        c.A(x, 62 * s + i * 4.2 * s, r * s + 1, 4 * s, 0, 180, w=2)
        c.R(x - r * s, x + r * s, 64 * s + i * 4.2 * s, 62 * s + i * 4.2 * s - 2)
    c.P([(x - 2 * s, 78 * s), (x, 98 * s), (x + 2 * s, 78 * s)])
    c.beacon(x, 98 * s)


@lm
def onewtc(c, x, s=1.0):
    c.P([(x - 8 * s, 0), (x + 8 * s, 0), (x + 8 * s, 74 * s), (x, 82 * s), (x - 8 * s, 74 * s)])
    c.blocks.append((int(x - 7 * s), int(x + 7 * s), 0, int(70 * s)))
    c.P([(x - 3 * s, 80 * s), (x + 3 * s, 80 * s), (x, 96 * s)])
    c.R(x, x, 108 * s, 90 * s)
    c.beacon(x, 108 * s)


@lm
def burj(c, x, s=1.0):
    for hw, a, b in [(7, 0, 34), (6, 34, 50), (5, 50, 64), (4, 64, 78), (3, 78, 92), (2, 92, 102), (1, 102, 108)]:
        c.R(x - hw * s, x + hw * s, b * s, a * s, win=hw > 3)
    c.R(x, x, 124 * s, 108 * s)
    c.beacon(x, 124 * s)


@lm
def burjalarab(c, x, s=1.0):
    c.P([(x - 9 * s, 0), (x - 9 * s, 20 * s), (x - 5 * s, 46 * s), (x - 1 * s, 64 * s), (x - 1 * s, 0)])
    c.P([(x - 1 * s, 0), (x - 1 * s, 64 * s), (x + 4 * s, 56 * s), (x + 10 * s, 30 * s), (x + 9 * s, 0)])
    c.R(x - 1 * s, x, 72 * s, 64 * s)


@lm
def emirates(c, x, s=1.0):
    c.P([(x - 5 * s, 0), (x - 5 * s, 60 * s), (x, 70 * s), (x + 5 * s, 60 * s), (x + 5 * s, 0)])
    c.blocks.append((int(x - 4 * s), int(x + 4 * s), 0, int(56 * s)))


@lm
def shard(c, x, s=1.0):
    c.P([(x - 7 * s, 0), (x, 100 * s), (x + 7 * s, 0)])
    c.R(x - 3, x + 3, 62 * s, 0, win=True)
    c.R(x, x, 108 * s, 100 * s)
    c.beacon(x, 108 * s)


@lm
def gherkin(c, x, s=1.0):
    h = 46 * s
    f = lambda y: max(0.6, 8 * s * math.sin(math.pi * min(1.0, (y + 0.12 * h) / (1.12 * h))) ** 0.7 * (1 - 0.15 * y / h))
    _prof(c, x, int(h), f, step=1)
    c.E(x, h, 1.5, 1.5)
    for yy in range(8, int(h) - 4, 5):                           # diagonal-lattice hints
        c.R(x - 1, x, yy + 1, yy, v=0)


@lm
def bigben(c, x, s=1.0):
    c.R(x - 4 * s, x + 4 * s, 62 * s, 0)
    c.R(x - 5 * s, x + 5 * s, 56 * s, 46 * s)
    c.P([(x - 5 * s, 62 * s), (x, 82 * s), (x + 5 * s, 62 * s)])
    c.R(x, x, 90 * s, 82 * s)
    c.R(x - 1, x + 1, 54 * s, 50 * s, v=0)                       # the clock face
    c.blocks.append((x, x, int(53 * s), int(54 * s)))


@lm
def stpauls(c, x, s=1.0):
    c.R(x - 14 * s, x + 14 * s, 18 * s, 0, win=True)
    c.R(x - 8 * s, x + 8 * s, 28 * s, 18 * s)
    c.Dm(x, 28 * s, 8 * s, 10 * s)
    c.R(x, x, 52 * s, 37 * s)
    c.E(x, 53 * s, 1.5, 1.5)
    c.R(x - 11 * s, x - 9 * s, 30 * s, 18 * s)
    c.R(x + 9 * s, x + 11 * s, 30 * s, 18 * s)


@lm
def walkietalkie(c, x, s=1.0):
    c.P([(x - 6 * s, 0), (x - 5 * s, 30 * s), (x - 9 * s, 52 * s), (x + 9 * s, 52 * s), (x + 5 * s, 30 * s), (x + 6 * s, 0)])
    c.blocks.append((int(x - 5 * s), int(x + 5 * s), 0, int(48 * s)))


@lm
def towerbridge(c, x, s=1.0):
    for dx in (-14, 14):
        c.R(x + dx * s - 3 * s, x + dx * s + 3 * s, 36 * s, 0)
        c.P([(x + dx * s - 3 * s, 36 * s), (x + dx * s, 46 * s), (x + dx * s + 3 * s, 36 * s)])
    c.R(x - 11 * s, x + 11 * s, 30 * s, 28 * s)                  # high walkway
    c.R(x - 40 * s, x + 40 * s, 8 * s, 6 * s)                    # road deck


@lm
def prime(c, x, s=1.0):
    c.R(x - 8 * s, x + 8 * s, 56 * s, 0, win=True)
    c.R(x - 8 * s, x + 2 * s, 80 * s, 56 * s, win=True)          # the stepped, shifting slabs
    c.R(x - 3 * s, x + 8 * s, 70 * s, 56 * s, win=True)
    c.R(x - 8 * s, x - 1 * s, 86 * s, 80 * s)


@lm
def grossmunster(c, x, s=1.0):
    c.R(x - 14 * s, x + 14 * s, 24 * s, 0, win=True)             # nave
    c.P([(x - 14 * s, 24 * s), (x - 8 * s, 31 * s), (x + 8 * s, 31 * s), (x + 14 * s, 24 * s)])
    for dx in (-8, 8):                                           # the twin towers, with their domed lanterns
        tx = x + dx * s
        c.R(tx - 4 * s, tx + 4 * s, 52 * s, 0, win=True)
        c.R(tx - 5 * s, tx + 5 * s, 56 * s, 52 * s)
        c.R(tx - 3 * s, tx + 3 * s, 64 * s, 56 * s)
        c.Dm(tx, 64 * s, 4 * s, 7 * s)
        c.R(tx, tx, 78 * s, 68 * s)
        c.R(tx - 1, tx + 1, 74 * s, 72 * s)
        c.R(tx - 1, tx + 1, 40 * s, 38 * s, v=0)


@lm
def fraumunster(c, x, s=1.0):
    c.R(x - 5 * s, x + 5 * s, 36 * s, 0, win=True)
    c.P([(x - 3 * s, 36 * s), (x, 82 * s), (x + 3 * s, 36 * s)])
    c.R(x + 5 * s, x + 16 * s, 24 * s, 0, win=True)


@lm
def stpeter(c, x, s=1.0):
    c.R(x - 5 * s, x + 5 * s, 44 * s, 0, win=True)
    c.R(x - 6 * s, x + 6 * s, 52 * s, 44 * s)
    c.P([(x - 6 * s, 52 * s), (x, 62 * s), (x + 6 * s, 52 * s)])


@lm
def uetliberg_tv(c, x, s=1.0):
    c.R(x - 1, x + 1, 36 * s, 0)
    c.R(x - 3 * s, x + 3 * s, 20 * s, 14 * s)
    c.R(x, x, 52 * s, 36 * s)
    c.beacon(x, 52 * s)


@lm
def tvtower_berlin(c, x, s=1.0):
    c.P([(x - 4 * s, 0), (x - 1, 62 * s), (x + 1, 62 * s), (x + 4 * s, 0)])
    c.E(x, 68 * s, 7 * s, 7 * s)
    c.R(x - 1, x + 1, 82 * s, 74 * s)
    c.R(x, x, 108 * s, 82 * s)
    c.beacon(x, 108 * s)


@lm
def brandenburg(c, x, s=1.0):
    c.R(x - 16 * s, x + 16 * s, 24 * s, 0, win=True)
    for dx in range(-14, 15, 6):
        c.R(x + dx * s - 1, x + dx * s + 1, 18 * s, 0, v=0)
    c.R(x - 18 * s, x + 18 * s, 28 * s, 24 * s)
    c.R(x - 4 * s, x + 4 * s, 36 * s, 28 * s)
    c.R(x - 1, x + 1, 42 * s, 36 * s)


@lm
def montparnasse(c, x, s=1.0):
    c.R(x - 6 * s, x + 6 * s, 62 * s, 0, win=True)
    c.P([(x - 6 * s, 62 * s), (x - 5 * s, 66 * s), (x + 5 * s, 66 * s), (x + 6 * s, 62 * s)])


@lm
def notredame(c, x, s=1.0):
    c.R(x - 14 * s, x + 14 * s, 26 * s, 0, win=True)
    for dx in (-10, 10):
        c.R(x + dx * s - 4 * s, x + dx * s + 4 * s, 40 * s, 26 * s)
    c.P([(x - 6 * s, 26 * s), (x, 34 * s), (x + 6 * s, 26 * s)])
    c.R(x, x, 52 * s, 34 * s)


@lm
def sacrecoeur(c, x, s=1.0):
    c.R(x - 13 * s, x + 13 * s, 16 * s, 0, win=True)
    c.Dm(x, 16 * s, 6 * s, 10 * s)
    for dx in (-9, 9):
        c.Dm(x + dx * s, 16 * s, 3 * s, 6 * s)
    c.R(x, x, 38 * s, 26 * s)


@lm
def pearl(c, x, s=1.0):
    c.R(x - 7 * s, x - 5 * s, 38 * s, 0)
    c.R(x + 5 * s, x + 7 * s, 38 * s, 0)
    c.Lw(x - 6 * s, 0, x, 36 * s, 1)
    c.Lw(x + 6 * s, 0, x, 36 * s, 1)
    c.E(x, 14 * s, 6.5 * s, 6.5 * s)
    c.E(x, 40 * s, 8.5 * s, 8.5 * s)
    c.R(x - 1, x + 1, 64 * s, 46 * s)
    c.E(x, 66 * s, 4 * s, 4 * s)
    c.R(x, x, 94 * s, 70 * s)
    c.beacon(x, 94 * s)


@lm
def shanghaitower(c, x, s=1.0):
    h = 104 * s
    _prof(c, x, int(h), lambda y: 9 * s * (1 - 0.82 * (y / h) ** 1.3), step=2)
    c.blocks.append((int(x - 5 * s), int(x + 5 * s), 0, int(h * 0.7)))
    c.R(x, x, h + 6 * s, h)
    c.beacon(x, h + 6 * s)


@lm
def jinmao(c, x, s=1.0):
    for i, hw in enumerate((8, 7, 6, 5, 4, 3, 2.2, 1.5, 0.8)):
        c.R(x - hw * s, x + hw * s, (i + 1) * 8 * s, i * 8 * s, win=hw > 3)
    c.R(x, x, 84 * s, 72 * s)


@lm
def swfc(c, x, s=1.0):
    c.P([(x - 8 * s, 0), (x - 8 * s, 82 * s), (x - 4 * s, 90 * s), (x + 8 * s, 90 * s), (x + 8 * s, 0)])
    c.blocks.append((int(x - 7 * s), int(x + 7 * s), 0, int(78 * s)))
    c.P([(x - 2 * s, 90 * s), (x + 2 * s, 90 * s), (x, 78 * s)], v=0)      # the bottle-opener
    c.R(x - 1, x + 1, 87 * s, 72 * s, v=0)


@lm
def mbs(c, x, s=1.0):
    for dx in (-13, 0, 13):
        tx = x + dx * s
        c.P([(tx - 5 * s, 0), (tx - 3 * s, 64 * s), (tx + 3 * s, 64 * s), (tx + 5 * s, 0)])
        c.blocks.append((int(tx - 3 * s), int(tx + 3 * s), 0, int(60 * s)))
    c.P([(x - 30 * s, 72 * s), (x - 20 * s, 64 * s), (x + 20 * s, 64 * s), (x + 34 * s, 74 * s),
         (x + 30 * s, 68 * s), (x - 26 * s, 68 * s)])              # the ship on top
    c.R(x - 28 * s, x + 30 * s, 68 * s, 64 * s)


@lm
def esplanade(c, x, s=1.0):
    c.E(x - 8 * s, 0, 10 * s, 11 * s)
    c.E(x + 9 * s, 0, 10 * s, 9 * s)


@lm
def supertrees(c, x, s=1.0):
    for dx, hh in ((-14, 44), (0, 56), (14, 40)):
        tx = x + dx * s
        c.R(tx - 1, tx + 1, hh * s, 0)
        c.P([(tx - 8 * s, hh * s + 8 * s), (tx - 1, hh * s - 2), (tx + 1, hh * s - 2), (tx + 8 * s, hh * s + 8 * s),
             (tx + 5 * s, hh * s + 10 * s), (tx - 5 * s, hh * s + 10 * s)])


@lm
def opera_sails(c, x, s=1.0):
    """Sydney Opera House: clusters of leaning shell sails on a podium."""
    c.R(x - 30 * s, x + 30 * s, 5 * s, 0)
    for dx, hh, wd, lean in ((-22, 20, 12, -1), (-8, 28, 14, -1), (6, 32, 14, -1), (18, 20, 12, 1), (26, 14, 8, 1)):
        cx = x + dx * s
        c.P([(cx - wd * s * 0.5, 4 * s), (cx + wd * s * 0.5, 4 * s),
             (cx + lean * wd * s * 0.1 + wd * s * 0.15, hh * s * 0.7),
             (cx + lean * wd * s * 0.25, hh * s),
             (cx + lean * wd * s * 0.05 - wd * s * 0.3, hh * s * 0.7)])
        c.P([(cx + wd * s * 0.5 - 1, 4 * s), (cx + wd * s * 0.95, 4 * s),
             (cx + wd * s * 0.7 - lean * 2, hh * s * 0.55), (cx + wd * s * 0.5 - 2, hh * s * 0.45)])


@lm
def harbourbridge(c, x, s=1.0):
    span = 40 * s
    c.A(x, -36 * s, span, 78 * s, 24, 156, w=4)
    c.R(x - span - 6, x + span + 6, 18 * s, 15 * s)
    for dx in (-span * 0.92, span * 0.92):
        c.R(x + dx - 3, x + dx + 3, 36 * s, 0)



@lm
def sydneytower(c, x, s=1.0):
    c.R(x - 1, x + 1, 74 * s, 0)
    c.E(x, 64 * s, 6 * s, 4 * s)
    c.R(x, x, 98 * s, 74 * s)
    c.beacon(x, 98 * s)


@lm
def petronas(c, x, s=1.0):
    for dx in (-9, 9):
        tx = x + dx * s
        for hw, a, b in ((7, 0, 52), (6, 52, 64), (5, 64, 74), (4, 74, 82), (3, 82, 88)):
            c.R(tx - hw * s, tx + hw * s, b * s, a * s, win=hw > 4)
        c.P([(tx - 2 * s, 88 * s), (tx, 100 * s), (tx + 2 * s, 88 * s)])
        c.R(tx, tx, 108 * s, 100 * s)
        c.beacon(tx, 108 * s)
    c.R(x - 4 * s, x + 4 * s, 48 * s, 44 * s)                    # the skybridge


@lm
def kltower(c, x, s=1.0):
    c.R(x - 1, x + 1, 70 * s, 0)
    c.E(x, 64 * s, 5 * s, 4 * s)
    c.R(x, x, 92 * s, 68 * s)
    c.beacon(x, 92 * s)


@lm
def cntower(c, x, s=1.0):
    c.P([(x - 4 * s, 0), (x - 1, 78 * s), (x + 1, 78 * s), (x + 4 * s, 0)])
    c.E(x, 76 * s, 6 * s, 3.5 * s)
    c.E(x, 82 * s, 3 * s, 2.4 * s)
    c.R(x, x, 112 * s, 82 * s)
    c.beacon(x, 112 * s)


@lm
def rogers(c, x, s=1.0):
    c.R(x - 18 * s, x + 18 * s, 18 * s, 0, win=True)
    c.Dm(x, 16 * s, 17 * s, 15 * s)


@lm
def spaceneedle(c, x, s=1.0):
    h = 90 * s
    f = lambda y: 1.2 + 4.2 * abs(1 - y / (0.45 * h)) ** 1.5
    _prof(c, x, int(0.62 * h), f, step=2)
    c.E(x, 0.74 * h, 12 * s, 3.5 * s)
    c.E(x, 0.8 * h, 5 * s, 2.5 * s)
    c.R(x, x, h + 8 * s, 0.8 * h)
    c.beacon(x, h + 8 * s)


@lm
def columbia(c, x, s=1.0):
    c.R(x - 6 * s, x + 6 * s, 88 * s, 0, win=True)
    c.R(x - 4 * s, x + 4 * s, 94 * s, 88 * s)
    c.R(x - 2 * s, x + 2 * s, 98 * s, 94 * s)


@lm
def rainier(c, x, s=1.0):
    pts = [(x - 90 * s, 0)]
    for i in range(-9, 10):
        pts.append((x + i * 10 * s, max(2.0, 62 * s * max(0.0, 1 - abs(i) / 9) ** 1.2 + 6 * math.sin(i * 1.7) * s)))
    pts.append((x + 90 * s, 0))
    c.P(pts)


@lm
def transamerica(c, x, s=1.0):
    c.P([(x - 6 * s, 0), (x - 1, 80 * s), (x + 1, 80 * s), (x + 6 * s, 0)])
    c.R(x - 8 * s, x - 5 * s, 44 * s, 20 * s)
    c.R(x + 5 * s, x + 8 * s, 44 * s, 20 * s)
    c.R(x, x, 96 * s, 80 * s)
    c.beacon(x, 96 * s)


@lm
def salesforce(c, x, s=1.0):
    c.R(x - 6 * s, x + 6 * s, 84 * s, 0, win=True)
    c.E(x, 84 * s, 6 * s, 6 * s)


@lm
def coit(c, x, s=1.0):
    c.P([(x - 2, 0), (x - 1, 44 * s), (x + 1, 44 * s), (x + 2, 0)])
    c.R(x - 3, x + 3, 50 * s, 44 * s)


@lm
def goldengate(c, x, s=1.0):
    span = 56 * s
    for dx in (-span, span):
        c.R(x + dx - 2, x + dx + 2, 64 * s, 0)
        c.R(x + dx - 3, x + dx + 3, 54 * s, 52 * s)
    c.R(x - span - 30 * s, x + span + 30 * s, 12 * s, 10 * s)
    xs = np.linspace(-span, span, 40)
    hy = lambda u: 14 * s + 48 * s * (u / span) ** 2
    for a, b in zip(xs[:-1], xs[1:]):
        c.Lw(x + a, hy(a), x + b, hy(b), 1)
    for u in range(-int(span) + 4, int(span) - 3, 5):
        c.R(x + u, x + u, hy(u), 12 * s)


@lm
def corcovado(c, x, s=1.0):
    c.P([(x - 44 * s, 0), (x - 30 * s, 28 * s), (x - 14 * s, 54 * s), (x - 4 * s, 66 * s), (x + 6 * s, 64 * s),
         (x + 20 * s, 44 * s), (x + 40 * s, 14 * s), (x + 50 * s, 0)])
    c.R(x - 1, x + 1, 82 * s, 66 * s)                            # Christ the Redeemer
    c.R(x - 8 * s, x + 8 * s, 78 * s, 76 * s)
    c.R(x - 1, x + 1, 86 * s, 82 * s)


@lm
def sugarloaf(c, x, s=1.0):
    c.P([(x - 36 * s, 0), (x - 24 * s, 24 * s), (x - 10 * s, 52 * s), (x, 58 * s), (x + 8 * s, 52 * s),
         (x + 18 * s, 28 * s), (x + 36 * s, 14 * s), (x + 50 * s, 18 * s), (x + 60 * s, 0)])


@lm
def pyramids(c, x, s=1.0):
    c.P([(x - 40 * s, 0), (x - 6 * s, 56 * s), (x + 28 * s, 0)])
    c.P([(x + 10 * s, 0), (x + 32 * s, 38 * s), (x + 54 * s, 0)])
    c.P([(x + 50 * s, 0), (x + 62 * s, 16 * s), (x + 74 * s, 0)])


def _minaret(c, x, s, h):
    c.R(x - 1, x + 1, h * s, 0)
    c.R(x - 2, x + 2, (h - 12) * s, (h - 14) * s)
    c.P([(x - 1, h * s), (x, (h + 10) * s), (x + 1, h * s)])


@lm
def minaret(c, x, s=1.0):
    _minaret(c, x, s, 60)


@lm
def hagiasophia(c, x, s=1.0):
    c.R(x - 20 * s, x + 20 * s, 22 * s, 0, win=True)
    c.Dm(x, 22 * s, 14 * s, 17 * s)
    c.Dm(x - 18 * s, 20 * s, 7 * s, 9 * s)
    c.Dm(x + 18 * s, 20 * s, 7 * s, 9 * s)
    for dx in (-26, 26):
        _minaret(c, x + dx * s, s, 54)
    c.R(x, x, 52 * s, 38 * s)


@lm
def galata(c, x, s=1.0):
    c.R(x - 5 * s, x + 5 * s, 54 * s, 0, win=True)
    c.R(x - 6 * s, x + 6 * s, 60 * s, 54 * s)
    c.P([(x - 6 * s, 60 * s), (x, 78 * s), (x + 6 * s, 60 * s)])


@lm
def bluemosque(c, x, s=1.0):
    c.R(x - 16 * s, x + 16 * s, 16 * s, 0, win=True)
    c.Dm(x, 16 * s, 11 * s, 13 * s)
    for dx in (-18, 18):
        c.Dm(x + dx * s * 0.6, 16 * s, 6 * s, 8 * s)
    for dx in (-22, 22):
        _minaret(c, x + dx * s, s, 62)


@lm
def stbasil(c, x, s=1.0):
    c.R(x - 12 * s, x + 12 * s, 16 * s, 0, win=True)
    for dx, hh, r in ((0, 44, 5), (-9, 30, 3.5), (9, 30, 3.5), (-15, 20, 3), (15, 20, 3), (4, 28, 3)):
        tx = x + dx * s
        c.R(tx - 2 * s, tx + 2 * s, (hh - 6) * s, 0)
        c.E(tx, (hh - 4) * s, r * s, (r + 2) * s)
        c.P([(tx - 1, hh * s), (tx, (hh + 7) * s), (tx + 1, hh * s)])
        c.R(tx, tx, (hh + 10) * s, (hh + 6) * s)


@lm
def spasskaya(c, x, s=1.0):
    c.R(x - 5 * s, x + 5 * s, 50 * s, 0, win=True)
    c.R(x - 4 * s, x + 4 * s, 62 * s, 50 * s)
    c.P([(x - 4 * s, 62 * s), (x, 82 * s), (x + 4 * s, 62 * s)])
    c.beacon(x, 82 * s)


@lm
def kremlinwall(c, x, s=1.0):
    c.R(x - 36 * s, x + 36 * s, 14 * s, 0, win=True)
    for i in range(-35, 36, 3):
        c.R(x + i * s, x + i * s, 16 * s, 14 * s)


@lm
def ostankino(c, x, s=1.0):
    c.P([(x - 4 * s, 0), (x - 1, 70 * s), (x + 1, 70 * s), (x + 4 * s, 0)])
    c.R(x - 6 * s, x + 6 * s, 80 * s, 66 * s)
    c.R(x, x, 110 * s, 80 * s)
    c.beacon(x, 110 * s)


@lm
def gateway(c, x, s=1.0):
    c.R(x - 12 * s, x + 12 * s, 28 * s, 0, win=True)
    c.R(x - 5 * s, x + 5 * s, 14 * s, 0, v=0)
    c.A(x, 12 * s, 5 * s, 6 * s, 0, 180, w=6, v=0)
    for dx in (-10, 10):
        c.E(x + dx * s, 30 * s, 2.2 * s, 3 * s)
    c.E(x, 33 * s, 6 * s, 5 * s)


@lm
def rajabai(c, x, s=1.0):
    c.R(x - 4 * s, x + 4 * s, 70 * s, 0, win=True)
    c.R(x - 5 * s, x + 5 * s, 54 * s, 46 * s)
    c.P([(x - 4 * s, 70 * s), (x, 88 * s), (x + 4 * s, 70 * s)])


@lm
def sealink(c, x, s=1.0):
    """Bandra-Worli sea link: a deck on the water and a cable-stayed pylon."""
    c.R(x - 90 * s, x + 90 * s, 7 * s, 5 * s)
    for dx in (-26, 26):
        tx = x + dx * s
        c.P([(tx - 5 * s, 0), (tx - 1, 78 * s), (tx + 1, 78 * s), (tx + 5 * s, 0)])
        for k in range(1, 6):
            c.Lw(tx, 74 * s, tx + k * 9 * s, 6 * s, 1)
            c.Lw(tx, 74 * s, tx - k * 9 * s, 6 * s, 1)


@lm
def sagrada(c, x, s=1.0):
    c.R(x - 22 * s, x + 22 * s, 30 * s, 0, win=True)
    for dx, hh in [(-18, 66), (-12, 80), (-6, 72), (0, 104), (6, 72), (12, 80), (18, 66), (-24, 50), (24, 50)]:
        tx = x + dx * s
        hw = 2.2 * s if hh < 100 else 3.2 * s
        c.R(tx - hw, tx + hw, (hh - 8) * s, 28 * s)
        c.P([(tx - hw, (hh - 8) * s), (tx, hh * s), (tx + hw, (hh - 8) * s)])
    c.R(x, x, 112 * s, 104 * s)


@lm
def torreglories(c, x, s=1.0):
    h = 56 * s
    f = lambda y: 7 * s * min(1.0, 0.7 + y / h) * (1 - (max(0.0, y - 0.6 * h) / (0.4 * h)) ** 2) ** 0.5 + 0.5
    _prof(c, x, int(h), f, step=1)
    c.blocks.append((int(x - 5 * s), int(x + 5 * s), 0, int(0.62 * h)))


@lm
def shandon(c, x, s=1.0):
    c.R(x - 6 * s, x + 6 * s, 52 * s, 0, win=True)
    c.R(x - 5 * s, x + 5 * s, 62 * s, 52 * s)
    c.R(x - 4 * s, x + 4 * s, 70 * s, 62 * s)
    c.P([(x - 4 * s, 70 * s), (x, 84 * s), (x + 4 * s, 70 * s)])
    c.R(x, x, 90 * s, 84 * s)
    c.R(x - 1, x, 56 * s, 54 * s, v=0)


@lm
def finbarres(c, x, s=1.0):
    c.R(x - 18 * s, x + 18 * s, 22 * s, 0, win=True)
    c.P([(x - 18 * s, 22 * s), (x - 13 * s, 34 * s), (x + 13 * s, 34 * s), (x + 18 * s, 22 * s)])
    c.R(x - 5 * s, x + 5 * s, 52 * s, 22 * s)
    c.P([(x - 5 * s, 52 * s), (x, 92 * s), (x + 5 * s, 52 * s)])
    for dx in (-15, 15):
        c.R(x + dx * s - 3 * s, x + dx * s + 3 * s, 46 * s, 22 * s)
        c.P([(x + dx * s - 3 * s, 46 * s), (x + dx * s, 64 * s), (x + dx * s + 3 * s, 46 * s)])
    c.R(x, x, 100 * s, 92 * s)


@lm
def stpeters_dome(c, x, s=1.0):
    c.R(x - 22 * s, x + 22 * s, 22 * s, 0, win=True)
    c.R(x - 8 * s, x + 8 * s, 40 * s, 22 * s)
    c.Dm(x, 40 * s, 9 * s, 13 * s)
    c.R(x, x, 66 * s, 50 * s)
    c.R(x - 1, x + 1, 62 * s, 61 * s)


@lm
def colosseum(c, x, s=1.0):
    c.R(x - 26 * s, x + 26 * s, 26 * s, 0, win=True)
    for dx in range(-23, 24, 5):
        for hh in (3, 11, 19):
            c.R(x + dx * s - 1, x + dx * s + 1, (hh + 5) * s, hh * s, v=0)


@lm
def willis(c, x, s=1.0):
    c.R(x - 11 * s, x + 11 * s, 50 * s, 0, win=True)
    c.R(x - 11 * s, x - 1 * s, 70 * s, 50 * s, win=True)
    c.R(x - 1 * s, x + 11 * s, 90 * s, 50 * s, win=True)
    c.R(x - 11 * s, x - 5 * s, 82 * s, 70 * s)
    c.R(x + 4 * s, x + 11 * s, 100 * s, 90 * s)
    c.R(x - 8 * s, x - 8 * s, 96 * s, 82 * s)
    c.R(x + 6 * s, x + 6 * s, 108 * s, 100 * s)
    c.beacon(x + 6 * s, 108 * s)
    c.beacon(x - 8 * s, 96 * s)


@lm
def hancock(c, x, s=1.0):
    c.P([(x - 8 * s, 0), (x - 5 * s, 96 * s), (x + 5 * s, 96 * s), (x + 8 * s, 0)])
    c.blocks.append((int(x - 6 * s), int(x + 6 * s), 0, int(90 * s)))
    c.R(x - 4 * s, x - 4 * s, 106 * s, 96 * s)
    c.R(x + 4 * s, x + 4 * s, 106 * s, 96 * s)
    c.Lw(x - 7 * s, 4, x + 4 * s, 90 * s, 1, v=0)
    c.Lw(x + 7 * s, 4, x - 4 * s, 90 * s, 1, v=0)


@lm
def aon(c, x, s=1.0):
    c.R(x - 7 * s, x + 7 * s, 86 * s, 0, win=True)
    c.R(x - 3 * s, x + 3 * s, 90 * s, 86 * s)


@lm
def ifc(c, x, s=1.0):
    c.R(x - 8 * s, x + 8 * s, 92 * s, 0, win=True)
    c.Dm(x, 92 * s, 8 * s, 6 * s)
    c.R(x - 3 * s, x + 3 * s, 100 * s, 92 * s)
    c.R(x, x, 108 * s, 100 * s)
    c.beacon(x, 108 * s)


@lm
def bankofchina(c, x, s=1.0):
    c.R(x - 8 * s, x + 8 * s, 40 * s, 0, win=True)
    c.R(x - 8 * s, x + 0 * s, 64 * s, 40 * s, win=True)
    c.R(x - 8 * s, x - 3 * s, 80 * s, 64 * s, win=True)
    c.P([(x - 8 * s, 80 * s), (x - 3 * s, 80 * s), (x - 3 * s, 90 * s)])
    c.R(x - 5 * s, x - 5 * s, 100 * s, 90 * s)
    c.beacon(x - 5 * s, 100 * s)


@lm
def centralplaza(c, x, s=1.0):
    c.R(x - 7 * s, x + 7 * s, 82 * s, 0, win=True)
    c.P([(x - 7 * s, 82 * s), (x, 94 * s), (x + 7 * s, 82 * s)])
    c.R(x, x, 112 * s, 94 * s)
    c.beacon(x, 112 * s)


@lm
def hkhills(c, x, s=1.0):
    pts = [(0, 0), (0, 36 * s)]
    for xx in range(0, W + 8, 8):
        pts.append((xx, 40 * s + 22 * s * math.sin(xx * 0.035 + 1.3) + 10 * s * math.sin(xx * 0.09)))
    pts.append((W, 0))
    c.P(pts)


@lm
def fuji(c, x, s=1.0):
    c.P([(x - 95 * s, 0), (x - 30 * s, 50 * s), (x - 8 * s, 60 * s), (x + 8 * s, 60 * s), (x + 30 * s, 50 * s),
         (x + 95 * s, 0)])


@lm
def ridge(c, x, s=1.0, amp=30, base=22, seed=1):
    r = np.random.default_rng(seed)
    ph = r.uniform(0, 6.28, 3)
    pts = [(0, 0)]
    for xx in range(0, W + 4, 4):
        pts.append((min(xx, W), base * s + amp * s * (0.5 * math.sin(xx * 0.021 + ph[0]) + 0.3 * math.sin(xx * 0.057 + ph[1])
                                                     + 0.2 * math.sin(xx * 0.13 + ph[2]) + 0.6)))
    pts.append((W, 0))
    c.P(pts)


@lm
def uetliberg(c, x, s=1.0):
    ridge(c, x, s, amp=26, base=34, seed=7)


@lm
def dome_rotunda(c, x, s=1.0):
    c.R(x - 8 * s, x + 8 * s, 14 * s, 0, win=True)
    c.Dm(x, 14 * s, 9 * s, 11 * s)


# =========================================================================== cities ===
# bg: the generic buildings, seeded: heights (LED rows), widths, how low-biased (pw), roofs, cluster centres.
def bg(hmin, hmax, wmin, wmax, gap=0, pw=1.6, roof="flat", cl=((96, 70),), floor=0.35, tank=0.0, ant=0.1):
    return dict(hmin=hmin, hmax=hmax, wmin=wmin, wmax=wmax, gap=gap, pw=pw, roof=roof, cl=cl, floor=floor,
                tank=tank, ant=ant)


CITIES = [
    dict(name="RIO", lat=-22.91, lon=-43.17, tz="America/Sao_Paulo", az0=0, water=10, seed=3,
         bg=bg(10, 40, 5, 11, 0, 1.8, "flat", ((150, 50),)), far=bg(12, 34, 8, 14, 0, 1.4),
         land=[("corcovado", 46, 1.0), ("sugarloaf", 150, 1.0)]),
    dict(name="TORONTO", lat=43.65, lon=-79.38, tz="America/Toronto", az0=180, water=12, seed=4,
         bg=bg(14, 66, 6, 12, 0, 1.6, "flat", ((130, 60),)), far=bg(14, 40, 7, 13, 0, 1.4),
         land=[("cntower", 70, 1.0), ("rogers", 112, 1.0)]),
    dict(name="NEW YORK", lat=40.71, lon=-74.00, tz="America/New_York", az0=180, water=10, seed=5,
         bg=bg(16, 70, 6, 12, 0, 1.4, "tank", ((60, 40), (150, 45)), 0.4, 0.5), far=bg(16, 50, 8, 14, 0, 1.3),
         land=[("empire", 60, 1.0), ("chrysler", 100, 1.0), ("onewtc", 158, 1.0)]),
    dict(name="CHICAGO", lat=41.88, lon=-87.63, tz="America/Chicago", az0=90, water=10, seed=6,
         bg=bg(16, 72, 6, 12, 0, 1.4, "flat", ((50, 40), (140, 50)), 0.4), far=bg(16, 50, 8, 14, 0, 1.3),
         land=[("willis", 54, 1.0), ("hancock", 110, 1.0), ("aon", 152, 1.0)]),
    dict(name="SEATTLE", lat=47.61, lon=-122.33, tz="America/Los_Angeles", az0=180, water=12, seed=8,
         bg=bg(10, 56, 6, 12, 0, 1.7, "flat", ((150, 40),)), far=bg(8, 30, 9, 16, 0, 1.2),
         farland=[("rainier", 110, 1.0)], land=[("spaceneedle", 54, 1.0), ("columbia", 130, 1.0)]),
    dict(name="SAN FRANCISCO", lat=37.77, lon=-122.42, tz="America/Los_Angeles", az0=180, water=12, seed=9,
         bg=bg(8, 36, 5, 10, 0, 1.8, "flat", ((120, 50),)), far=bg(8, 22, 8, 14, 0, 1.4),
         farland=[("goldengate", 96, 0.8)], land=[("transamerica", 118, 1.0), ("salesforce", 142, 1.0), ("coit", 68, 1.0)]),
    dict(name="LONDON", lat=51.507, lon=-0.128, tz="Europe/London", az0=180, water=10, seed=10,
         bg=bg(8, 32, 6, 12, 0, 2.0, "gable", ((130, 40),)), far=bg(8, 22, 8, 14, 0, 1.4),
         land=[("bigben", 26, 1.0), ("stpauls", 62, 1.0), ("gherkin", 96, 1.0), ("shard", 130, 1.0),
               ("walkietalkie", 158, 0.8), ("towerbridge", 182, 0.5)]),
    dict(name="CORK", lat=51.90, lon=-8.47, tz="Europe/Dublin", az0=180, water=8, seed=11,
         bg=bg(6, 24, 6, 11, 0, 2.2, "gable", ((100, 60),), 0.5), far=bg(6, 20, 9, 16, 0, 1.6),
         farland=[("ridge", 96, 1.0)], land=[("shandon", 60, 1.0), ("finbarres", 124, 1.0)]),
    dict(name="SYDNEY", lat=-33.87, lon=151.21, tz="Australia/Sydney", az0=0, water=14, seed=12,
         bg=bg(12, 56, 5, 11, 0, 1.6, "flat", ((150, 40),)), far=bg(10, 34, 8, 14, 0, 1.3),
         land=[("opera_sails", 46, 1.35), ("harbourbridge", 132, 1.0), ("sydneytower", 176, 0.8)]),
    dict(name="TOKYO", lat=35.68, lon=139.69, tz="Asia/Tokyo", az0=180, water=0, seed=13,
         bg=bg(14, 52, 5, 10, 0, 1.3, "tank", ((70, 60), (150, 60)), 0.5, 0.5, 0.25), far=bg(14, 40, 7, 12, 0, 1.2),
         farland=[("fuji", 150, 1.0)],
         land=[("tokyotower", 50, 1.0), ("shibuya", 98, 1.0), ("skytree", 154, 1.0)]),
    dict(name="SHANGHAI", lat=31.23, lon=121.47, tz="Asia/Shanghai", az0=180, water=12, seed=14,
         bg=bg(16, 66, 5, 10, 0, 1.3, "flat", ((100, 60),), 0.5), far=bg(16, 48, 7, 12, 0, 1.2),
         land=[("jinmao", 36, 1.0), ("swfc", 72, 1.0), ("shanghaitower", 108, 1.0), ("pearl", 156, 1.0)]),
    dict(name="HONG KONG", lat=22.30, lon=114.17, tz="Asia/Hong_Kong", az0=180, water=12, seed=15,
         bg=bg(26, 74, 4, 8, 0, 1.0, "flat", ((90, 70),), 0.7, 0.0, 0.25), far=bg(24, 58, 6, 11, 0, 1.0),
         farland=[("hkhills", 96, 1.0)], land=[("bankofchina", 52, 1.0), ("centralplaza", 118, 1.0), ("ifc", 156, 1.0)]),
    dict(name="SINGAPORE", lat=1.29, lon=103.85, tz="Asia/Singapore", az0=180, water=14, seed=16,
         bg=bg(12, 52, 5, 10, 0, 1.6, "flat", ((50, 40), (160, 40)), 0.5), far=bg(12, 36, 7, 13, 0, 1.3),
         land=[("esplanade", 28, 1.0), ("mbs", 104, 1.0), ("supertrees", 168, 0.7)]),
    dict(name="KUALA LUMPUR", lat=3.15, lon=101.71, tz="Asia/Kuala_Lumpur", az0=180, water=0, seed=17,
         bg=bg(14, 56, 5, 10, 0, 1.4, "flat", ((50, 40), (150, 50)), 0.45), far=bg(14, 44, 7, 12, 0, 1.2),
         land=[("petronas", 70, 1.0), ("kltower", 148, 1.0)]),
    dict(name="MUMBAI", lat=19.08, lon=72.88, tz="Asia/Kolkata", az0=180, water=10, seed=18,
         bg=bg(10, 58, 5, 10, 0, 1.4, "flat", ((60, 50), (140, 40)), 0.4), far=bg(10, 34, 8, 14, 0, 1.2),
         farland=[("sealink", 140, 0.9)], land=[("gateway", 40, 1.0), ("rajabai", 82, 1.0)]),
    dict(name="DUBAI", lat=25.20, lon=55.27, tz="Asia/Dubai", az0=180, water=10, seed=19,
         bg=bg(10, 46, 5, 10, 0, 1.8, "flat", ((50, 40), (160, 30)), 0.4), far=bg(10, 30, 8, 14, 0, 1.4),
         land=[("emirates", 30, 1.0), ("burj", 104, 1.0), ("burjalarab", 168, 1.0)]),
    dict(name="MOSCOW", lat=55.75, lon=37.62, tz="Europe/Moscow", az0=180, water=0, seed=20,
         bg=bg(10, 44, 6, 12, 0, 1.8, "flat", ((150, 50),), 0.4), far=bg(10, 30, 8, 14, 0, 1.4),
         land=[("ostankino", 30, 0.9), ("kremlinwall", 106, 1.2), ("spasskaya", 124, 1.2), ("stbasil", 74, 1.6)]),
    dict(name="ISTANBUL", lat=41.01, lon=28.98, tz="Europe/Istanbul", az0=180, water=10, seed=21,
         bg=bg(8, 30, 6, 12, 0, 2.0, "gable", ((100, 80),), 0.5), far=bg(8, 22, 8, 14, 0, 1.4),
         land=[("hagiasophia", 52, 1.0), ("bluemosque", 118, 1.0), ("galata", 170, 1.0)]),
    dict(name="CAIRO", lat=30.04, lon=31.24, tz="Africa/Cairo", az0=180, water=0, seed=22,
         bg=bg(8, 34, 6, 12, 0, 2.0, "flat", ((150, 40),), 0.4), far=bg(8, 24, 8, 14, 0, 1.4),
         land=[("pyramids", 52, 1.3), ("minaret", 126, 1.0), ("minaret", 140, 0.8), ("minaret", 170, 0.9)]),
    dict(name="ROME", lat=41.90, lon=12.50, tz="Europe/Rome", az0=180, water=0, seed=23,
         bg=bg(8, 26, 6, 12, 0, 2.2, "gable", ((100, 80),), 0.5), far=bg(8, 20, 8, 14, 0, 1.4),
         farland=[("ridge", 96, 0.7)], land=[("colosseum", 52, 1.4), ("stpeters_dome", 138, 1.3)]),
    dict(name="BARCELONA", lat=41.39, lon=2.17, tz="Europe/Madrid", az0=180, water=0, seed=24,
         bg=bg(10, 30, 6, 11, 0, 2.0, "flat", ((100, 80),), 0.5, 0.2), far=bg(10, 24, 8, 14, 0, 1.4),
         farland=[("ridge", 96, 0.8)], land=[("sagrada", 62, 1.0), ("torreglories", 150, 1.0)]),
    dict(name="ZURICH", lat=47.37, lon=8.54, tz="Europe/Zurich", az0=180, water=12, seed=25,
         bg=bg(8, 28, 6, 12, 0, 2.2, "gable", ((100, 70),), 0.5), far=bg(8, 22, 8, 14, 0, 1.6),
         farland=[("uetliberg", 96, 1.0), ("uetliberg_tv", 146, 1.0)],
         land=[("grossmunster", 52, 1.0), ("fraumunster", 100, 0.9), ("stpeter", 128, 0.8), ("prime", 166, 1.0)]),
    dict(name="PARIS", lat=48.86, lon=2.35, tz="Europe/Paris", az0=180, water=10, seed=26,
         bg=bg(8, 22, 7, 13, 0, 1.8, "mansard", ((100, 80),), 0.5), far=bg(8, 18, 8, 14, 0, 1.4),
         land=[("notredame", 26, 1.0), ("sacrecoeur", 62, 1.0), ("eiffel", 108, 1.0), ("montparnasse", 160, 1.0)]),
    dict(name="BERLIN", lat=52.52, lon=13.40, tz="Europe/Berlin", az0=180, water=0, seed=27,
         bg=bg(8, 30, 6, 12, 0, 2.0, "flat", ((100, 80),), 0.5), far=bg(8, 22, 8, 14, 0, 1.4),
         land=[("brandenburg", 44, 1.5), ("tvtower_berlin", 112, 1.0), ("dome_rotunda", 166, 1.5)]),
]
# slot = the Zürich wall-clock hour. Each city comes up near its own evening where the globe allows.
_ORDER = ["RIO", "TORONTO", "NEW YORK", "CHICAGO", "SEATTLE", "SAN FRANCISCO", "LONDON", "CORK", "SYDNEY",
          "TOKYO", "SHANGHAI", "HONG KONG", "SINGAPORE", "KUALA LUMPUR", "MUMBAI", "DUBAI", "MOSCOW",
          "ISTANBUL", "CAIRO", "ROME", "BARCELONA", "ZURICH", "PARIS", "BERLIN"]
_BY = {c["name"]: c for c in CITIES}
SLOTS = [_BY[n] for n in _ORDER]
assert len(SLOTS) == 24 and len(_BY) == 24


# ============================================================================ build ===
class Layers:
    """The still parts of one city, drawn once."""

    def __init__(self, city):
        self.city = city
        self.name = city["name"]
        rng = np.random.default_rng(city["seed"] * 7919)
        wh = city["water"]
        self.yb = H - wh
        self.water = wh
        self.lim = H - int(SKYLINE_MAX * H)                       # nothing above this row
        far, near = Canvas(self.yb), Canvas(self.yb)
        self._bg(far, rng, city["far"], far=True)
        for name, x, s in city.get("farland", []):
            LM[name](far, x, s)
        lim = self.lim
        self._bg(near, rng, city["bg"], far=False, clear=[x for n, x, _ in city["land"] if n not in ("ridge", "rainier")])
        k = LS
        for _ in range(6):                                        # landmarks fit under the limit, spires and all
            lmk = Canvas(self.yb)
            for name, x, s in city["land"]:
                LM[name](lmk, x, s * k)
            rows = np.nonzero(lmk.mask().any(1))[0]
            top = int(rows.min()) if len(rows) else self.yb
            if top >= lim:
                break
            k *= 0.985 * (self.yb - lim) / (self.yb - top)
        near.im = Image.fromarray(np.maximum(np.asarray(near.im), np.asarray(lmk.im)))
        near.blocks += lmk.blocks
        near.beacons += lmk.beacons
        self.k = k
        self.near_m, self.far_m = near.mask(), far.mask()
        self.top = int(np.nonzero(self.near_m.any(1))[0].min())
        self.far_m &= ~self.near_m
        self.far_m[self.yb:] = False
        self.near_m[self.yb:] = False
        self.ny, self.nx = np.nonzero(self.near_m)
        self.fy, self.fx = np.nonzero(self.far_m)
        self.beacons = [(x, self.yb - h) for x, h in near.beacons if 0 <= x < W and lim <= self.yb - h < H]
        self._windows(rng, near.blocks, self.near_m, far=False)
        self._windows(rng, far.blocks, self.far_m, far=True)
        if wh:                                                    # reflections in the water
            ys, xs = [], []
            for dy in range(wh):
                src = self.yb - 1 - dy * 2
                if src < 0:
                    break
                row = np.nonzero(self.near_m[src])[0]
                ys.append(np.full(len(row), self.yb + dy))
                xs.append(row)
            self.ry = np.concatenate(ys)
            self.rx = np.concatenate(xs)
        else:
            self.ry = self.rx = np.zeros(0, int)
        ys_ = np.arange(H, dtype=np.float32)
        self.trow = (np.clip((self.yb - ys_) / self.yb, 0, 1) ** 0.62)[:, None, None]
        self.hz = np.exp(-np.clip(self.yb - ys_, 0, None) / 55.0).astype(np.float32)
        self.fogw = np.clip(1 - (self.yb - ys_) / (0.6 * self.yb), 0, 1).astype(np.float32)[:, None, None]

    def _bg(self, cv, rng, p, far, clear=()):
        x = -2
        cl = p["cl"]
        while x < W:
            w = int(rng.integers(p["wmin"], p["wmax"] + 1))
            env = 0.3 + 0.7 * max(math.exp(-((x + w / 2 - cx) / sp) ** 2) for cx, sp in cl)
            h = min(self.yb - self.lim - 14, int(HS * max(p["hmin"], int(p["hmin"] + (p["hmax"] - p["hmin"]) * env * rng.random() ** p["pw"]))))
            x0, x1 = x, x + w - 1
            if any(abs(x + w / 2 - cx) < 15 for cx in clear):      # keep the landmarks' own air
                h = min(h, int(HS * p["hmin"] * 1.7))
            cv.R(x0, x1, h, 0, win=True)
            roof = p["roof"]
            if roof == "gable" and w >= 6 and rng.random() < 0.7:
                cv.P([(x0 - 1, h), ((x0 + x1) / 2, h + w * 0.45), (x1 + 1, h)])
            elif roof == "mansard" and rng.random() < 0.85:
                cv.P([(x0 - 1, h), (x0 + 1, h + 3), (x1 - 1, h + 3), (x1 + 1, h)])
                for k in range(x0 + 2, x1 - 1, 4):
                    cv.R(k, k + 1, h + 5, h + 3)                  # chimneys
            elif roof == "tank" and rng.random() < p["tank"]:
                tx = int((x0 + x1) / 2)
                cv.R(tx - 2, tx + 2, h + 5, h + 3)
                cv.R(tx - 2, tx - 2, h + 3, h)
                cv.R(tx + 2, tx + 2, h + 3, h)
                cv.P([(tx - 3, h + 5), (tx, h + 7), (tx + 3, h + 5)])
            elif h > p["hmax"] * 0.6 and rng.random() < 0.45:
                cv.R(x0 + w // 4, x1 - w // 4, h + max(2, h // 8), h)           # a setback
            if rng.random() < p["ant"] and h > p["hmin"] * 1.2:
                ax = int((x0 + x1) / 2)
                cv.R(ax, ax, h + int(rng.integers(4, 11)), h)
                if not far and rng.random() < 0.3:
                    cv.beacon(ax, h + 6)
            x += w + p["gap"]

    def _windows(self, rng, blocks, mask, far):
        """Single LEDs on a loose grid inside every window-bearing block."""
        ys, xs, rk, tn, br = [], [], [], [], []
        for x0, x1, h0, h1 in blocks:
            hp = int(rng.integers(2, 4))
            vp = int(rng.integers(2, 4)) if not far else 3
            ox = int(rng.integers(0, hp))
            for hh in range(h0 + 3, h1 - 2, vp):
                y = self.yb - 1 - hh
                for xx in range(x0 + 1 + ox, x1, hp):
                    if 0 <= y < H and 1 <= xx < W - 1 and mask[y, xx] and mask[y, xx - 1] and mask[y, xx + 1]:
                        ys.append(y)
                        xs.append(xx)
                        rk.append(rng.random())
                        tn.append(rng.random())
                        br.append(0.55 + 0.45 * rng.random())
        a = lambda v, d: np.array(v, d)
        if far:
            self.fwy, self.fwx, self.fwr, self.fwt, self.fwb = a(ys, int), a(xs, int), a(rk, np.float32), a(tn, np.float32), a(br, np.float32)
        else:
            self.wy, self.wx, self.wr, self.wt, self.wb = a(ys, int), a(xs, int), a(rk, np.float32), a(tn, np.float32), a(br, np.float32)
            if self.water:                                        # their reflections
                ry = self.yb + (self.yb - self.wy) // 2
                ok = ry < H
                self.wry, self.wrx, self.wrr, self.wrt, self.wrb = ry[ok], self.wx[ok], self.wr[ok], self.wt[ok], self.wb[ok]
            else:
                self.wry = self.wrx = np.zeros(0, int)
                self.wrr = self.wrt = self.wrb = np.zeros(0, np.float32)


# ============================================================================ astronomy ===
def sky_state(ts, lat, lon):
    """Sun and moon for a place and instant: (sun_alt, sun_az, moon_alt, moon_az, moon_illum, bright_limb_angle,
    elongation). Degrees for the first four; the limb angle is the screen direction (radians, 0 = +x i.e.
    azimuth increasing, pi/2 = up) from the moon's centre towards the sun."""
    j = jd(ts)
    phi, lam = math.radians(lat), math.radians(lon)
    lst = gmst(j) + lam
    cl, sl = math.cos(lst), math.sin(lst)

    def horiz(v):
        x, y, z = v
        xp, yp = cl * x + sl * y, -sl * x + cl * y
        return np.array([yp, -math.sin(phi) * xp + math.cos(phi) * z, math.cos(phi) * xp + math.sin(phi) * z])   # E, N, U

    sv = sun_eci(j)
    mv = moon_eci(j)
    mu = mv / np.linalg.norm(mv)
    hs, hm = horiz(sv), horiz(mu)
    az_s = math.degrees(math.atan2(hs[0], hs[1])) % 360
    alt_s = math.degrees(math.asin(max(-1, min(1, hs[2]))))
    az_m = math.degrees(math.atan2(hm[0], hm[1])) % 360
    alt_m = math.degrees(math.asin(max(-1, min(1, hm[2]))))
    alt_m -= 0.95 * math.cos(math.radians(alt_m))                  # topocentric parallax
    elong = math.acos(max(-1, min(1, float(np.dot(sv, mu)))))
    illum = (1 - math.cos(elong)) / 2
    d = hs - np.dot(hs, hm) * hm                                   # towards the sun, in the moon's sky plane
    nrm = np.linalg.norm(d)
    if nrm < 1e-9:
        ang = math.pi / 2
    else:
        d /= nrm
        up = np.array([0, 0, 1.0]) - hm[2] * hm
        up /= max(1e-9, np.linalg.norm(up))
        eaz = np.array([hm[1], -hm[0], 0.0])                       # tangent of increasing azimuth
        eaz /= max(1e-9, np.linalg.norm(eaz))
        ang = math.atan2(float(np.dot(d, up)), float(np.dot(d, eaz)))
    return alt_s, az_s, alt_m, az_m, illum, ang, elong


def _wrap(a):
    return (a + 180) % 360 - 180


# =========================================================================== palette ===
_ALT = np.array([-18, -12, -6, -2, 0.5, 4, 10, 25, 90], np.float32)
_ZEN = np.array([(3, 5, 17), (6, 9, 30), (16, 22, 62), (30, 40, 98), (36, 58, 122), (44, 84, 152), (50, 104, 182),
                 (52, 114, 198), (50, 112, 196)], np.float32)
_HOR = np.array([(8, 12, 32), (22, 26, 62), (96, 56, 92), (200, 96, 82), (244, 134, 76), (240, 178, 120),
                 (168, 202, 232), (150, 196, 236), (146, 192, 234)], np.float32)


def sky_colours(alt):
    z = np.array([np.interp(alt, _ALT, _ZEN[:, i]) for i in range(3)], np.float32)
    h = np.array([np.interp(alt, _ALT, _HOR[:, i]) for i in range(3)], np.float32)
    return z, h


def _bayer(n):
    m = np.array([[0]], np.float32)
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / (n * n)


BAYER = np.tile(_bayer(8), (H // 8, W // 8))[:, :, None].astype(np.float32)


def _noise_tex():
    """A horizontally tileable cloud texture (H x 384): stretched fractal noise whose vertical profile keeps
    the clouds in the upper-middle sky."""
    import cv2
    P = 384
    rng = np.random.default_rng(99)
    acc = np.zeros((H, P), np.float32)
    amp, tot = 1.0, 0.0
    for gy, gx in ((5, 4), (9, 9), (17, 18), (33, 36)):
        g = rng.random((gy, gx)).astype(np.float32)
        big = cv2.resize(np.tile(g, (1, 3)), (P * 3, H), interpolation=cv2.INTER_CUBIC)[:, P:2 * P]
        acc += amp * big
        tot += amp
        amp *= 0.55
    acc /= tot
    y = np.arange(H, dtype=np.float32) / H
    prof = np.exp(-((y - 0.34) / 0.2) ** 2)[:, None]
    return (acc * (0.35 + 0.65 * prof) + 0.10 * prof).astype(np.float32)


_TEX = None


def _tex():
    global _TEX
    if _TEX is None:
        t = _noise_tex()
        _TEX = np.concatenate([t, t], axis=1)
    return _TEX


# ============================================================================ weather ===
_cache_lock = threading.Lock()


def _read_cache():
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_cache(key, rec):
    with _cache_lock:
        c = _read_cache()
        c[key] = rec
        tmp = CACHE + ".tmp"
        try:
            with open(tmp, "w") as fh:
                json.dump(c, fh, separators=(",", ":"))
            os.replace(tmp, CACHE)
        except OSError:
            pass


def weather_word(code):
    if code is None:
        return ""
    if code in (45, 48):
        return "FOG"
    if 51 <= code <= 57:
        return "DRIZZLE"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "RAIN"
    if 71 <= code <= 77 or code in (85, 86):
        return "SNOW"
    if code >= 95:
        return "STORM"
    if code == 3:
        return "OVERCAST"
    if code == 2:
        return "CLOUDY"
    return "CLEAR"


def precip_kind(code, precip):
    """(kind, intensity 0..1): kind 'rain' | 'snow' | None."""
    if code is not None:
        if 71 <= code <= 77 or code in (85, 86):
            return "snow", {71: 0.3, 73: 0.55, 75: 0.9, 77: 0.25, 85: 0.4, 86: 0.8}.get(code, 0.5)
        if 51 <= code <= 57:
            return "rain", 0.18
        if code in (61, 80):
            return "rain", 0.4
        if code in (63, 81, 66):
            return "rain", 0.65
        if code in (65, 82, 67) or code >= 95:
            return "rain", 0.95
    if precip and precip > 0.05:
        return "rain", min(0.9, 0.25 + precip / 4.0)
    return None, 0.0


class Weather:
    """Open-Meteo 'current' for the cities on show. A side thread fetches only the city on screen and the next;
    the last good answers are kept in panel_setup/skylines_cache.json."""

    def __init__(self, fetch=True):
        self.recs = _read_cache()
        self.want = []
        self.last_frame = time.time()
        self.eased = {}
        self.fetch = fetch
        self.thread = None

    def get(self, name):
        r = self.recs.get(name)
        if not r or time.time() - r.get("t", 0) > USABLE:
            return None
        return r

    def touch(self, names):
        self.last_frame = time.time()
        self.want = list(names)
        if self.fetch and (self.thread is None or not self.thread.is_alive()):
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def _loop(self):
        import requests
        while True:
            if time.time() - self.last_frame > IDLE:               # not on the wall: no calls, and the thread ends
                return
            pause = 20.0
            for name in list(self.want):
                r = self.recs.get(name)
                if r and time.time() - r.get("t", 0) < STALE:
                    continue
                city = _BY[name]
                try:
                    resp = requests.get(URL, timeout=20, params={
                        "latitude": f"{city['lat']:.3f}", "longitude": f"{city['lon']:.3f}",
                        "current": "cloud_cover,precipitation,temperature_2m,weather_code,wind_speed_10m"})
                    resp.raise_for_status()
                    cur = resp.json()["current"]
                    rec = {"t": time.time(), "cloud": float(cur.get("cloud_cover") or 0),
                           "precip": float(cur.get("precipitation") or 0), "temp": cur.get("temperature_2m"),
                           "code": cur.get("weather_code"), "wind": float(cur.get("wind_speed_10m") or 0)}
                    self.recs[name] = rec
                    _write_cache(name, rec)
                except Exception:
                    pause = 300.0                                  # offline or limited: calm retry later
                    break
            time.sleep(pause)

    def ease(self, name, dt):
        """Smoothed cloud / fog / rain numbers for a city (they glide when a new fetch arrives)."""
        r = self.get(name) or {}
        code = r.get("code")
        kind, inten = precip_kind(code, r.get("precip"))
        tgt = {"cloud": float(r.get("cloud", 0)) / 100.0, "fog": 1.0 if code in (45, 48) else 0.0,
               "rain": inten if kind == "rain" else 0.0, "snow": inten if kind == "snow" else 0.0}
        e = self.eased.setdefault(name, dict(tgt))
        k = min(1.0, dt / 30.0)
        for key in tgt:
            e[key] += (tgt[key] - e[key]) * k
        return e, r


# ============================================================================ render ===
LIT_BY_HOUR = np.array([0.20, 0.14, 0.10, 0.07, 0.07, 0.12, 0.30, 0.34, 0.22, 0.10, 0.06, 0.05, 0.05, 0.05, 0.06,
                        0.08, 0.14, 0.30, 0.62, 0.90, 1.00, 0.92, 0.70, 0.42], np.float32)


def lit_fraction(local_hour):
    """Share of windows lit at a local clock hour (fractional): many at 20:00, few at 04:00, never none."""
    h0 = int(local_hour) % 24
    f = local_hour - int(local_hour)
    v = LIT_BY_HOUR[h0] * (1 - f) + LIT_BY_HOUR[(h0 + 1) % 24] * f
    return 0.03 + 0.62 * float(v)


class Stars:
    def __init__(self):
        rng = np.random.default_rng(31)
        n = 230
        self.y = (rng.random(n) ** 1.3 * 0.62 * H).astype(int)
        self.x = rng.integers(0, W, n)
        self.b = (0.25 + 0.75 * rng.random(n) ** 2.5).astype(np.float32)
        self.ph = rng.uniform(0, 6.28, n).astype(np.float32)
        self.col = np.array([(190, 205, 255), (255, 244, 220), (255, 255, 255)], np.float32)[rng.integers(0, 3, n)]


_stars = Stars()


def _moon_sprite(illum, ang, r=6):
    """RGB (float) and inside-mask of the moon disc for an illuminated fraction and bright-limb screen angle."""
    n = 2 * r + 1
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    rr = np.hypot(xx, yy)
    inside = rr <= r + 0.15
    nx, ny = xx / (r + 0.5), -yy / (r + 0.5)
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    i = math.acos(max(-1.0, min(1.0, 2 * illum - 1)))              # phase angle: 0 = full
    lit = nx * math.cos(ang) * math.sin(i) + ny * math.sin(ang) * math.sin(i) + nz * math.cos(i)
    shade = np.clip(lit * 3.0, 0, 1)
    bright = np.array([232, 230, 214], np.float32)
    dark = np.array([18, 22, 38], np.float32)                      # earthshine
    col = dark + (bright - dark) * shade[..., None]
    mar = (np.sin(xx * 1.1 + 1) * np.cos(yy * 0.9) > 0.55) & (rr < r - 1.2)
    col[mar] *= 0.86
    return col.astype(np.float32), inside * np.clip(shade + 0.3, 0, 1)


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class Skylines:
    def __init__(self, fetch=True):
        self.layers = {}
        self.lock = threading.Lock()
        self.weather = Weather(fetch=fetch)
        self.fetch = fetch
        self.last_t = None
        self._sky_cache = {}
        self.pref = None

    @staticmethod
    def slot(ts):
        return datetime.fromtimestamp(ts, timezone.utc).astimezone(ZURICH).hour

    def pick(self, ts):
        """(current city, previous city, fade 0..1): the fade starts at xx:00 and reaches 1 after FADE seconds.
        A repeated hour (DST fall back) or a skipped one (spring forward) never makes a false fade."""
        z = datetime.fromtimestamp(ts, timezone.utc).astimezone(ZURICH)
        cur = SLOTS[z.hour]
        into = z.minute * 60 + z.second + z.microsecond / 1e6
        if into >= FADE:
            return cur, cur, 1.0
        prev = SLOTS[datetime.fromtimestamp(ts - into - 1.0, timezone.utc).astimezone(ZURICH).hour]
        if prev is cur:
            return cur, cur, 1.0
        return cur, prev, _smooth(into / FADE)

    def get_layers(self, city):
        L = self.layers.get(city["name"])
        if L is None:
            with self.lock:
                L = self.layers.get(city["name"])
                if L is None:
                    L = Layers(city)
                    self.layers[city["name"]] = L
        return L

    def render(self, city, ts, t, dt=1 / 30):
        """One city's full frame as float RGB (H, W, 3), 0..255, before dithering."""
        L = self.get_layers(city)
        key = (city["name"], int(ts))
        st = self._sky_cache.get(key)
        if st is None:
            st = sky_state(ts, city["lat"], city["lon"])
            self._sky_cache[key] = st
            if len(self._sky_cache) > 8:
                self._sky_cache.pop(next(iter(self._sky_cache)))
        alt, saz, malt, maz, illum, mang, elong = st
        ease, rec = self.weather.ease(city["name"], dt)
        cover, fog, rain, snow = ease["cloud"], ease["fog"], ease["rain"], ease["snow"]
        local = datetime.fromtimestamp(ts, timezone.utc).astimezone(ZoneInfo(city["tz"]))
        yb = L.yb
        zen, hor = sky_colours(alt)
        grey_amt = min(0.75, 0.55 * cover + 0.5 * fog)             # overcast and fog take colour out of the sky
        for v in (zen, hor):
            g = float(v @ np.array([0.3, 0.55, 0.15], np.float32))
            v += (np.array([g, g, g * 1.05], np.float32) * (1 - 0.3 * cover) - v) * grey_amt
        img = np.empty((H, W, 3), np.float32)
        img[:] = hor + (zen - hor) * L.trow
        xs = np.arange(W, dtype=np.float32)
        sx = W / 2 + _wrap(saz - city["az0"]) * (W / FOV)
        gamt = _smooth((alt + 10) / 8) * (1 - _smooth((alt - 4) / 16)) * (1 - 0.6 * cover)
        if gamt > 0.01:                                            # the twilight glow toward the sun
            wcol = np.array([255, 110 + 7 * max(0, alt), 50 + 9 * max(0, alt)], np.float32) * 0.55 * gamt
            gx = np.exp(-((xs - sx) / 52.0) ** 2)
            img += (L.hz[:, None] * gx[None, :])[..., None] * wcol
        elif alt > 4:                                              # the sun's own broad glow by day
            gx = np.exp(-((xs - sx) / 70.0) ** 2)
            img += (L.hz[:, None] * gx[None, :])[..., None] * (np.array([255, 235, 190], np.float32) * 0.10 * (1 - cover))
        ng = float(np.clip((-alt - 2.0) / 10.0, 0, 1)) * (1 - 0.5 * cover)       # the city's own glow under a dark sky
        if ng > 0.01:
            img += L.hz[:, None, None] * (np.array([46, 34, 44], np.float32) * ng)
        # stars
        sa = float(np.clip((-alt - 4.0) / 10.0, 0, 1)) * (1 - min(1.0, cover * 1.1)) * (1 - 0.8 * fog)
        mx = W / 2 + _wrap(maz - city["az0"]) * (W / FOV)
        my = yb - ((max(malt, 0.0) / 90.0) ** 0.8) * (yb - 8)
        if sa > 0.01:
            tw = 0.75 + 0.25 * np.sin(t * (0.7 + _stars.b * 2.2) + _stars.ph)
            a = (sa * _stars.b * tw)[:, None]
            if malt > 0:
                dm = np.hypot(_stars.x - mx, _stars.y - my)
                a = a * (np.clip(dm / 26.0, 0.1, 1.0) ** (0.6 + illum))[:, None]
            img[_stars.y, _stars.x] = np.maximum(img[_stars.y, _stars.x], _stars.col * a * 0.95)
        # sun and moon (before the clouds, so thin cloud passes over them)
        dim = 1 - 0.85 * cover
        if alt > -2.5 and abs(_wrap(saz - city["az0"])) < FOV / 2:
            sy = yb - ((max(alt, 0.0) / 90.0) ** 0.8) * (yb - 8) - (3 * alt if alt < 0 else 0)
            col = np.array([255, 244, 214], np.float32) if alt > 6 else np.array([255, 170, 90], np.float32)
            self._disc(img, sx, sy, 4.2, col, dim)
        if malt > -1.5 and abs(_wrap(maz - city["az0"])) < FOV / 2:
            a = float(np.clip((6.0 - alt) / 14.0, 0.0, 1.0)) * (0.35 + 0.65 * (1 - cover)) * (1 - 0.5 * fog)
            if a > 0.02:
                spr, ins = _moon_sprite(illum, mang)
                r = 6
                x0, y0 = int(round(mx)) - r, int(round(my)) - r
                ys0, ys1, xs0, xs1 = max(0, y0), min(H, y0 + 2 * r + 1), max(0, x0), min(W, x0 + 2 * r + 1)
                if ys0 < ys1 and xs0 < xs1:
                    sub = img[ys0:ys1, xs0:xs1]
                    sp = spr[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
                    m = (ins[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0].astype(np.float32) * a)[..., None]
                    img[ys0:ys1, xs0:xs1] = sub + (sp - sub) * m
        # clouds: slow soft bands
        wind = float(rec.get("wind", 8.0)) if rec else 6.0
        if cover > 0.04:
            off = int(t * (0.5 + wind * 0.05)) % 384
            tex = _tex()[:, off:off + W]
            a = np.clip((tex - (1.02 - 0.95 * cover)) * 5.0, 0, 0.88 if cover < 0.9 else 0.97)
            d = float(np.clip((alt + 3) / 16, 0, 1))
            ccol = (1 - d) * (hor * 0.9 + np.array([16, 16, 26], np.float32)) + d * np.array([238, 241, 247], np.float32)
            if d > 0.5:
                ccol = ccol * (1 - 0.22 * cover)
            img += (ccol - img) * a[..., None]
        if fog > 0.02:                                             # haze
            img += ((hor * 0.9 + 12) - img) * (L.fogw * (0.55 * fog))
        d = float(np.clip((alt + 6) / 22, 0, 1))
        near_col = np.array([5, 6, 11], np.float32) * (1 - d) + np.array([20, 24, 36], np.float32) * d
        if len(L.fy):                                              # the paler far layer
            a = 0.50 - 0.15 * fog
            img[L.fy, L.fx] = img[L.fy, L.fx] * (1 - a) + near_col * a
            self._lights(img, L.fwy, L.fwx, L.fwr, L.fwt, L.fwb, alt, local, 0.5 * (1 - 0.7 * fog))
        if L.water:
            col = hor * 0.66 + near_col * 0.25
            ys = np.arange(yb, H, dtype=np.float32)[:, None, None]
            wcol = col + (near_col - col) * ((ys - yb) / L.water) * 0.6
            xx = xs[None, :, None]
            img[yb:] = wcol * (1 + 0.10 * np.sin(xx * 0.7 + ys * 1.9 + t * 0.9) * np.sin(xx * 0.17 - t * 0.3))
            if len(L.rx):
                img[L.ry, L.rx] = img[L.ry, L.rx] * 0.3 + near_col * 0.7
            self._lights(img, L.wry, L.wrx, L.wrr, L.wrt, L.wrb, alt, local, 0.4)
        img[L.ny, L.nx] = near_col * (1 - 0.30 * fog) + (hor * 0.9 + 12) * (0.30 * fog)
        self._lights(img, L.wy, L.wx, L.wr, L.wt, L.wb, alt, local, 1.0 - 0.6 * fog)
        for i, (bx, by) in enumerate(L.beacons):
            if math.sin(t * 1.6 + i * 1.3) > 0.0:
                img[by, bx] = (255, 38, 28) if alt < 8 else (150, 40, 34)
        if rain > 0.02 or snow > 0.02:
            self._precip(img, t, rain, snow, wind)
        self._label(img, city, local, rec, alt)
        return img

    @staticmethod
    def _disc(img, cx, cy, r, col, dim):
        ri = int(math.ceil(r)) + 1
        x0, y0 = int(round(cx)) - ri, int(round(cy)) - ri
        ys0, ys1, xs0, xs1 = max(0, y0), min(H, y0 + 2 * ri + 1), max(0, x0), min(W, x0 + 2 * ri + 1)
        if ys0 >= ys1 or xs0 >= xs1:
            return
        yy, xx = np.mgrid[ys0:ys1, xs0:xs1].astype(np.float32)
        rr = np.hypot(xx - round(cx), yy - round(cy))
        core = (rr <= r)[..., None].astype(np.float32)
        glow = np.exp(-(rr / (r * 2.2)) ** 2)[..., None] * 0.35
        sub = img[ys0:ys1, xs0:xs1]
        img[ys0:ys1, xs0:xs1] = sub + (col * (0.75 + 0.25 * core) - sub) * (np.maximum(core, glow) * dim)

    @staticmethod
    def _lights(img, wy, wx, wr, wt, wb, alt, local, gain):
        if len(wy) == 0:
            return
        dark = float(np.clip((6.0 - alt) / 10.0, 0.0, 1.0))        # lit windows read at dusk and after
        if dark <= 0.02:
            return
        sel = wr < lit_fraction(local.hour + local.minute / 60.0)
        if not sel.any():
            return
        b = (wb[sel] * dark * gain)[:, None]
        tint = np.where((wt[sel] < 0.22)[:, None], np.array([186, 218, 255], np.float32), np.array([255, 196, 108], np.float32))
        y, x = wy[sel], wx[sel]
        img[y, x] = np.maximum(img[y, x], tint * b)

    @staticmethod
    def _precip(img, t, rain, snow, wind):
        rng = np.random.default_rng(5)
        n = 230
        x0, y0, v0, p0 = rng.random(n), rng.random(n), rng.random(n), rng.random(n)
        if rain > 0.02:
            k = int(rain * 215)
            yy = ((y0[:k] * H + t * (70 + 40 * v0[:k])) % H).astype(int)
            xx = ((x0[:k] * W - yy * min(0.35, wind / 90.0)) % W).astype(int)
            col = np.array([150, 185, 240], np.float32) * (0.6 + 0.4 * v0[:k, None])
            img[yy, xx] = np.maximum(img[yy, xx], col)
        if snow > 0.02:
            k = int(snow * 170)
            yy = ((y0[:k] * H + t * (9 + 9 * v0[:k])) % H).astype(int)
            xx = ((x0[:k] * W + 4 * np.sin(t * 0.6 + p0[:k] * 6.28) + t * min(8, wind * 0.3)) % W).astype(int)
            col = np.array([226, 232, 244], np.float32) * (0.6 + 0.4 * v0[:k, None])
            img[yy, xx] = np.maximum(img[yy, xx], col)

    @staticmethod
    def _label(img, city, local, rec, alt):
        col = np.array([150, 162, 196] if alt < 0 else [238, 242, 250], np.float32)
        x, y = 3, 3
        name = city["name"]
        pixelfont.draw(img, name, x, y, col)
        x += pixelfont.width(name) + 3
        pixelfont.draw(img, f"{local.hour:02d}", x, y, col)
        x += 8
        for dy in (1, 3):                                          # the colon: the font has none
            img[y + dy, x] = np.maximum(img[y + dy, x], col)
        pixelfont.draw(img, f"{local.minute:02d}", x + 2, y, col)
        word = weather_word(rec.get("code")) if rec else ""
        if word:
            t_ = rec.get("temp")
            pixelfont.draw(img, word + (f" {int(round(t_))}C" if t_ is not None else ""), 3, y + 7, col * 0.78)

    def __call__(self, t, ts=None):
        ts = _now() if ts is None else ts
        dt = 1 / 30 if self.last_t is None else max(0.0, min(0.5, t - self.last_t))
        self.last_t = t
        cur, prev, f = self.pick(ts)
        nxt = SLOTS[(self.slot(ts) + 1) % 24]
        self.weather.touch([cur["name"], nxt["name"]])
        if self.fetch and self.pref != nxt["name"]:                # draw the next city's layers ahead of its hour
            self.pref = nxt["name"]
            threading.Thread(target=self.get_layers, args=(nxt,), daemon=True).start()
        img = self.render(cur, ts, t, dt)
        if f < 1.0:
            old = self.render(prev, ts, t, 0.0)
            img = old + (img - old) * f
        return Image.fromarray(np.floor(np.clip(img, 0, 255) + BAYER).clip(0, 255).astype(np.uint8), "RGB")


_sk = None


def frame(t):
    global _sk
    if _sk is None:
        _sk = Skylines()
    return _sk(t)


def thumb():
    """A still for the app (no network): Tokyo at dusk, a little cloud, the sun just under the horizon."""
    sk = Skylines(fetch=False)
    city = _BY["TOKYO"]
    best, bestd = 1700000000.0, 1e9
    for k in range(0, 24 * 6):
        ts = 1700000000.0 + k * 600
        alt = sky_state(ts, city["lat"], city["lon"])[0]
        loc = datetime.fromtimestamp(ts, timezone.utc).astimezone(ZoneInfo(city["tz"]))
        if loc.hour >= 12 and alt < 0 and abs(alt + 5.0) < bestd:
            best, bestd = ts, abs(alt + 5.0)
    sk.weather.eased[city["name"]] = {"cloud": 0.3, "fog": 0.0, "rain": 0.0, "snow": 0.0}
    img = sk.render(city, best, 20.0)
    return Image.fromarray(np.floor(np.clip(img, 0, 255) + BAYER).clip(0, 255).astype(np.uint8), "RGB")
