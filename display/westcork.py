"""West Cork at night: a minimal map from Sheep's Head and Bantry Bay down to Mizen Head, Fastnet,
Schull, Roaringwater Bay and Baltimore, the land barely there, the sea black - and every navigation
light on it as one LED, flashing its real character in its real colour (from the OpenStreetMap
seamarks: Fastnet Fl W 5s, Mizen Head Iso W 4s, Crookhaven LFl 8s, Baltimore Fl(2) 6s, the cardinal
buoys' quick flashes ...). Each light keeps its own phase, as at sea. Map: assets/maps/westcork.json.
"""
import json
import math
import os
import re
import zlib

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
DARK_PIXEL = (128, 64)        # top-left pixel of the right-hand panel, second row: off in both West Cork maps
MAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "maps", "westcork.json")
CENTRE = (51.535, -9.597)
KM_W = 48.2                                   # from the Beara lights (Ardnakinna, Castletownbere) on the left to just past Baltimore on the right
COAST = (46, 50, 58)                          # the coast a fine grey-blue line
ISLAND, ROCK = COAST, COAST                   # islands and rocks keep the coast's own colour (the cleaner single-pixel lines are the change)
DUSK_COAST = COAST                                      # West Cork Dusk: only the land is tinted (a deep teal); the outlines are the original colour
DUSK_ISLAND, DUSK_ROCK = COAST, COAST   # "West Cork Dusk": land in a deep teal-green, the coast a cool line (sea stays black)
COLOURS = {"white": (255, 236, 205), "red": (255, 28, 18), "green": (40, 255, 90), "yellow": (255, 190, 0)}


def _stable(target, bits=(6, 7, 8), search=7):
    """A very dim fill picks up faint lines on the real panels when a channel sits right on a PWM step edge (one column of LEDs a
    touch more sensitive tips up a step: a half-lit line, as seen on the land at a panel seam). The wall lifts dark colours and the panels
    then show only the top PWM bits (6-8, by how bright the picture is); this finds the colour nearest `target` whose channels all sit
    in the middle of a step, for every one of those bit depths, at the wall's brightness."""
    hw = float(min(config.MATRIX_BRIGHTNESS, config.BRIGHTNESS_CAP))      # config already reads WALL_BRIGHTNESS / WALL_BRIGHTNESS_CAP
    k = float(getattr(config, "ART_SHADOW_LIFT", 0.5))
    m_ = np.arange(256, dtype=np.float64)
    g = 255.0 * (np.maximum(m_, 1.0) / 255.0) ** 0.55
    t = np.clip((m_ - 60.0) / 140.0, 0.0, 1.0)
    f = m_ + k * (g - m_) * (1.0 - t * t * (3 - 2 * t))
    scale = np.where(m_ > 0, f / np.maximum(m_, 1.0), 1.0)

    def margin(rgb):                                         # how far every channel is from a step edge, as a fraction of a step
        top = max(rgb)
        worst = 1.0
        for c in rgb:
            v = min(255.0, c * scale[top]) * hw / 255.0
            y = 2047.0 * (v / 902.3 if v <= 8.0 else ((v + 16.0) / 116.0) ** 3)
            for b in bits:
                step = float(1 << (11 - b))
                pos = y % step
                d = (step - pos) / step if y < step else min(pos, step - pos) / step
                worst = min(worst, d)
        return worst
    best, best_m = tuple(target), margin(target)
    r0, g0, b0 = target
    for r in range(max(0, r0 - search), r0 + search + 1):
        for gg in range(max(0, g0 - search), g0 + search + 1):
            for b in range(max(0, b0 - search), b0 + search + 1):
                mg = margin((r, gg, b))
                dist = abs(r - r0) + abs(gg - g0) + abs(b - b0)
                if mg > best_m + 0.02 or (abs(mg - best_m) <= 0.02 and dist < sum(abs(a - c) for a, c in zip(best, target))):
                    best, best_m = (r, gg, b), max(mg, best_m)
    return best


LAND = _stable((14, 13, 12))                  # land barely there (a dim fill, chosen to sit mid-step on the panels)
DUSK_LAND = _stable((8, 24, 28))              # the same for the teal land of West Cork Dusk


def to_px(lat, lon):
    k = W / KM_W
    return ((lon - CENTRE[1]) * 111.32 * math.cos(math.radians(CENTRE[0])) * k + W / 2,
            (CENTRE[0] - lat) * 111.32 * k + H / 2)


def pattern(L):
    """[(on seconds, off seconds), ...] for one period of a light's character."""
    seq = L.get("sequence", "")
    if seq:
        out = []
        for part in seq.split(","):
            m = re.match(r"\s*([\d.]+)\s*\+\s*\(([\d.]+)\)", part)
            if m:
                out.append((float(m.group(1)), float(m.group(2))))
        if out:
            return out
    ch = L.get("character", "Fl")
    n = int(re.match(r"\d+", L.get("group") or "1").group(0)) if re.match(r"\d+", L.get("group") or "1") else 1
    p = float(L.get("period") or 0) or None
    if ch == "F":
        return [(1.0, 0.0)]
    if ch == "Iso":
        p = p or 4.0
        return [(p / 2, p / 2)]
    if ch == "Oc":
        p = p or 4.0
        return [(p - 1.0, 1.0)]
    if ch in ("Q", "VQ"):
        q = 1.0 if ch == "Q" else 0.5
        if p and n > 1:
            return [(q * 0.4, q * 0.6)] * (n - 1) + [(q * 0.4, p - q * (n - 1) - q * 0.4)]
        return [(q * 0.4, q * 0.6)]
    if ch in ("Q+LFl", "VQ+LFl"):                     # south cardinal: six quick, one long, dark
        q = 1.0 if ch == "Q+LFl" else 0.5
        p = p or 15.0
        return [(q * 0.4, q * 0.6)] * n + [(2.0, max(0.5, p - n * q - 2.0))]
    on = 2.0 if ch == "LFl" else 0.5
    p = p or (10.0 if n > 1 else 5.0)
    gap = 1.0
    return [(on, gap)] * (n - 1) + [(on, max(0.5, p - n * on - (n - 1) * gap))]


class Light:
    def __init__(self, L):
        self.x, self.y = (int(round(v)) for v in to_px(L["lat"], L["lon"]))
        self.col = np.array(COLOURS.get(L.get("colour", "white"), COLOURS["white"]), np.float32)
        self.steps = pattern(L)
        self.period = sum(a + b for a, b in self.steps)
        self.phase = (zlib.crc32(f"{L['lat']}{L['lon']}".encode()) % 1000) / 1000.0 * self.period
        self.name = L.get("name", "")
        self.major = L.get("type") == "light_major"
        self.fastnet = "fastnet" in self.name.lower()
        if self.fastnet:                                   # Fl W 5s: the beam passes once every 5 s and is on for about a second
            self.steps = [(1.0, 4.0)]
            self.period = 5.0

    def level(self, t):
        """0..1: on or off at time t. A flash is at full brightness for its whole length, with 40 ms edges."""
        if self.period <= 0:
            return 1.0
        u = (t + self.phase) % self.period
        for on, off in self.steps:
            if u < on:                                     # full power for the whole flash; quick edges (a lamp, not a strobe)
                edge = min(0.04, on / 3.0)
                return min(1.0, u / edge, (on - u) / edge)
            u -= on
            if u < off:
                return 0.0
            u -= off
        return 0.0


def _simplify(px, closed):
    """A coastline at pixel scale: drop the wobbles that only make a thick, blobby line, keeping a clean single-pixel path."""
    import cv2
    arr = np.asarray(px, np.float32).reshape(-1, 1, 2)
    return np.rint(cv2.approxPolyDP(arr, 0.6, closed).reshape(-1, 2)).astype(np.int32)


def base_map(coast, land_col=LAND, coast_col=COAST, island_col=ISLAND, rock_col=ROCK, islets=()):
    """Land filled from the coastline. The fill runs on a wider canvas than the wall (the map's own
    data box, so Bantry and Dunmanus Bays reach the open Atlantic as they really do) and is then
    cropped: the sea is flooded in from the far south-west, whatever the coast does not enclose.
    Lines are simplified to single pixels; islands (closed rings) have their own brighter outline and the
    named islets too small for a ring (the Calf Islands, Bull Rock ...) are a small solid mark; the anonymous specks of rock are left out
    (they only looked like stray, half-lit LEDs)."""
    import cv2
    x0, y0 = (int(math.floor(v)) for v in to_px(51.83, -9.98))      # the canvas: inside the data box,
    x1, y1 = (int(math.ceil(v)) for v in to_px(51.17, -9.12))       # so every coast line crosses its edge
    cw, ch = x1 - x0 + 1, y1 - y0 + 1
    shore, islands, rocks = [], [], []
    for c in coast:
        px = [to_px(*p) for p in c]
        closed = len(c) > 3 and c[0] == c[-1]
        a = np.asarray(px)
        size = max(np.ptp(a[:, 0]), np.ptp(a[:, 1]))
        if closed and size < 3.0:                                   # an anonymous speck of rock: not drawn
            continue
        (islands if closed else shore).append(_simplify(px, closed) - (x0, y0))
    mask = np.zeros((ch, cw), np.uint8)
    for ln in shore:
        cv2.polylines(mask, [ln], False, 255, 1, cv2.LINE_8)
    for ln in islands:                                              # rings are closed: simplifying drops the duplicate end point
        cv2.polylines(mask, [ln], True, 255, 1, cv2.LINE_8)
    cv2.floodFill(mask, np.zeros((ch + 2, cw + 2), np.uint8), (0, ch - 1), 128)   # the open sea, south-west
    land = (mask == 0)[-y0:-y0 + H, -x0:-x0 + W]
    img = np.zeros((H, W, 3), np.uint8)
    img[land] = land_col
    for ln in shore:
        cv2.polylines(img, [ln + (x0, y0)], False, coast_col, 1, cv2.LINE_8)
    for ln in islands:                                              # islands over the shore: brighter, a single clean line
        cv2.polylines(img, [ln + (x0, y0)], True, island_col, 1, cv2.LINE_8)
    ring_px = [(np.asarray([to_px(*p) for p in c]).mean(axis=0), max(np.ptp([to_px(*p)[0] for p in c]), np.ptp([to_px(*p)[1] for p in c])))
               for c in coast if len(c) > 3 and c[0] == c[-1]]
    for it in islets:                                               # named islets: a solid 2 x 2 mark unless a ring already shows them
        X, Y = (int(round(v)) for v in to_px(it["lat"], it["lon"]))
        if not (0 <= X < W - 1 and 0 <= Y < H - 1):
            continue
        if any(abs(c[0] - X) < 4 and abs(c[1] - Y) < 4 and sz >= 6 for c, sz in ring_px):
            continue                                                # a proper island outline is drawn there already
        img[Y:Y + 2, X:X + 2] = rock_col
    return img


class WestCork:
    def __init__(self, dusk=False):
        with open(MAP) as fh:
            m = json.load(fh)
        self.base = (base_map(m["coast"], DUSK_LAND, DUSK_COAST, DUSK_ISLAND, DUSK_ROCK, m.get("islets", ())) if dusk
                     else base_map(m["coast"], islets=m.get("islets", ()))).astype(np.float32)
        self.lights = [Light(L) for L in m["lights"]]
        self.lights = [l for l in self.lights if 0 <= l.x < W and 0 <= l.y < H and (l.x, l.y) != DARK_PIXEL]
        self.base[DARK_PIXEL[1], DARK_PIXEL[0]] = 0          # this panel's corner pixel stays dark (it lit the seam line)

    def __call__(self, t):
        import time
        return self.render_at(time.time())         # real time: the lights keep their true rhythm

    def render_at(self, now):
        img = self.base.copy()
        for L in self.lights:
            v = L.level(now)
            if v <= 0:
                continue
            img[L.y, L.x] = img[L.y, L.x] * (1.0 - v) + L.col * v    # the lamp over the map: at full power the same colour on any land
        return Image.fromarray(img.astype(np.uint8), "RGB")


_wc = None
_wc_dusk = None


def thumb(dusk=False):
    """A still for the app (the lights need no network): a moment with plenty of lights on."""
    import time as _time
    wc = WestCork(dusk)
    best, bestn = None, -1
    t0 = _time.time()
    for i in range(80):                                    # pick the instant with the most lights lit
        img = wc.render_at(t0 + i * 0.25)
        n = int((np.asarray(img).max(axis=2) > 120).sum())
        if n > bestn:
            best, bestn = img, n
    return best


def thumb_dusk():
    return thumb(True)


def frame(t):
    global _wc
    if _wc is None:
        _wc = WestCork()
    return _wc(t)


def frame_dusk(t):
    """West Cork Dusk: the same lights over land in a deep teal, so the map reads as a place without taking attention from the lights."""
    global _wc_dusk
    if _wc_dusk is None:
        _wc_dusk = WestCork(dusk=True)
    return _wc_dusk(t)
