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
MAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "maps", "westcork.json")
CENTRE = (51.50, -9.56)
KM_W = 47.0                                   # Mizen Head to past Baltimore across the wall
LAND, COAST = (14, 13, 12), (46, 50, 58)      # land barely there, the coast a fine grey-blue line
COLOURS = {"white": (255, 236, 205), "red": (255, 28, 18), "green": (40, 255, 90), "yellow": (255, 190, 0)}


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

    def level(self, t):
        """0..1: on or off at time t, with a 60 ms rise and fall (a lamp, not a strobe)."""
        if self.period <= 0:
            return 1.0
        u = (t + self.phase) % self.period
        for on, off in self.steps:
            if u < on:
                return min(1.0, u / 0.06, (on - u) / 0.06)
            u -= on
            if u < off:
                return 0.0
            u -= off
        return 0.0


def base_map(coast):
    """Land filled from the coastline. The fill runs on a wider canvas than the wall (the map's own
    data box, so Bantry and Dunmanus Bays reach the open Atlantic as they really do) and is then
    cropped: the sea is flooded in from the far south-west, whatever the coast does not enclose."""
    import cv2
    x0, y0 = (int(math.floor(v)) for v in to_px(51.83, -9.98))      # the canvas: inside the data box,
    x1, y1 = (int(math.ceil(v)) for v in to_px(51.17, -9.12))       # so every coast line crosses its edge
    cw, ch = x1 - x0 + 1, y1 - y0 + 1
    lines = [np.array([[round(v) for v in to_px(*p)] for p in c], np.int32) - (x0, y0) for c in coast]
    mask = np.zeros((ch, cw), np.uint8)
    for ln in lines:
        cv2.polylines(mask, [ln], False, 255, 1, cv2.LINE_8)
    cv2.floodFill(mask, np.zeros((ch + 2, cw + 2), np.uint8), (0, ch - 1), 128)   # the open sea, south-west
    land = (mask == 0)[-y0:-y0 + H, -x0:-x0 + W]
    img = np.zeros((H, W, 3), np.uint8)
    img[land] = LAND
    for ln in lines:
        cv2.polylines(img, [ln + (x0, y0)], False, COAST, 1, cv2.LINE_8)
    return img


class WestCork:
    def __init__(self):
        with open(MAP) as fh:
            m = json.load(fh)
        self.base = base_map(m["coast"]).astype(np.float32)
        self.lights = [Light(L) for L in m["lights"]]
        self.lights = [l for l in self.lights if 0 <= l.x < W and 0 <= l.y < H]

    def __call__(self, t):
        import time
        now = time.time()                          # real time: the lights keep their true rhythm
        img = self.base.copy()
        for L in self.lights:
            v = L.level(now)
            if v > 0:
                img[L.y, L.x] = np.maximum(img[L.y, L.x], L.col * v)
        return Image.fromarray(img.astype(np.uint8), "RGB")


_wc = None


def thumb():
    """A still for the app (the lights need no network)."""
    wc, img = WestCork(), None
    for i in range(40):
        img = wc(i * 0.25)
    return img


def frame(t):
    global _wc
    if _wc is None:
        _wc = WestCork()
    return _wc(t)
