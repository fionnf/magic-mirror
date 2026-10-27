"""Planes: the sky over Zürich as live art. Every aircraft in range (adsb.lol, open ADS-B data, no
key) drifts across the wall as a point of light with its flight number, leaving a one-LED trail that
fades over minutes, so the approaches and departures of Zürich airport slowly draw themselves. Low
aircraft are warm amber, high ones rose. Underneath, a faint map: the lakes, the rivers, the runways
and a dot for the apartment (assets/maps/zurich.json, from tools/build_maps.py).

Everything is drawn on whole LEDs (no anti-aliasing): a soft dot gliding between LEDs shimmers.

Positions are fetched every 10 s on a side thread; between fetches each aircraft glides on at its
reported speed and track, so the motion is continuous.
"""
import json
import math
import os
import threading
import time

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
HOME = (47.3726, 8.5398)                  # Rennweg
AIRPORT = (47.4582, 8.5481)
CENTRE = (47.405, 8.545)                  # a little north of home, so the airport's paths fit
KM_W = 60.0                               # the wall shows 60 km across (and 80 km top to bottom)
URL = "https://api.adsb.lol/v2/point/{:.4f}/{:.4f}/40".format(*CENTRE)
EVERY = 10.0
FADE = 150.0                              # seconds for a trail to fall to 1/e
LOW_COL = np.array([255, 150, 55], np.float32)    # below ~2 km: approach and climb-out
HIGH_COL = np.array([235, 95, 135], np.float32)   # cruise


def to_px(lat, lon):
    kx = W / KM_W
    x = (lon - CENTRE[1]) * 111.32 * math.cos(math.radians(CENTRE[0])) * kx + W / 2
    y = (CENTRE[0] - lat) * 111.32 * kx + H / 2
    return x, y


MAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "maps", "zurich.json")
LAKE, LAKE_EDGE = (6, 12, 24), (16, 30, 56)       # the map stays far below the planes
RIVER, RUNWAY = (12, 22, 40), (44, 42, 46)


def base_map():
    """The still map under the planes: lakes (filled, a fine edge), rivers and runways, one LED wide."""
    import cv2
    img = np.zeros((H, W, 3), np.uint8)
    try:
        with open(MAP) as fh:
            m = json.load(fh)
    except Exception:
        return img
    pts = lambda line: np.array([[round(v) for v in to_px(*p)] for p in line], np.int32)
    for lake in m.get("lakes", []):
        cv2.fillPoly(img, [pts(lake)], LAKE)
        cv2.polylines(img, [pts(lake)], True, LAKE_EDGE, 1, cv2.LINE_8)
    for r in m.get("rivers", []):
        cv2.polylines(img, [pts(r)], False, RIVER, 1, cv2.LINE_8)
    for r in m.get("runways", []):
        cv2.polylines(img, [pts(r)], False, RUNWAY, 1, cv2.LINE_8)
    x, y = (round(v) for v in to_px(*HOME))
    img[y, x] = (90, 90, 90)
    return img


class Sky:
    def __init__(self):
        self.ac, self.ok = {}, False                  # hex -> {lat, lon, gs (m/s), track, alt (ft), t, flight}
        self.trail = np.zeros((H, W, 3), np.float32)
        self.base = base_map().astype(np.float32)
        self.drawn, self.last = {}, None
        threading.Thread(target=self._fetch_loop, daemon=True).start()

    def _fetch_loop(self):
        import requests
        while True:
            try:
                now = time.time()
                got = requests.get(URL, timeout=10).json().get("ac", [])
                for a in got:
                    if "lat" not in a or a.get("alt_baro") == "ground":
                        continue
                    self.ac[a["hex"]] = {"lat": a["lat"], "lon": a["lon"], "gs": float(a.get("gs") or 0) * 0.5144,
                                         "track": float(a.get("track") or 0), "t": now - float(a.get("seen_pos") or 0),
                                         "alt": float(a.get("alt_baro") or a.get("alt_geom") or 0),
                                         "flight": (a.get("flight") or a.get("r") or "").strip()[:8]}
                for k in [k for k, v in self.ac.items() if now - v["t"] > 60]:
                    del self.ac[k]
                self.ok = True
            except Exception as e:
                self.ok = False
                print(f"[planes] {str(e)[:100]}", flush=True)
            time.sleep(EVERY)

    @staticmethod
    def _now_pos(a, now):
        """Dead reckoning: glide on from the last fix at the reported ground speed and track."""
        age = max(0.0, min(30.0, now - a["t"]))
        d = a["gs"] * age / 1000.0                                  # km
        tr = math.radians(a["track"])
        lat = a["lat"] + d * math.cos(tr) / 111.32
        lon = a["lon"] + d * math.sin(tr) / (111.32 * math.cos(math.radians(a["lat"])))
        return to_px(lat, lon)

    def __call__(self, t):
        import cv2
        from display import pixelfont
        dt = 0.04 if self.last is None else max(0.0, min(0.5, t - self.last))
        self.last = t
        now = time.time()
        self.trail *= math.exp(-dt / FADE)
        stamp = np.zeros((H, W, 3), np.uint8)
        heads, seen = [], set()
        for k, a in list(self.ac.items()):
            x, y = self._now_pos(a, now)
            seen.add(k)
            hi = max(0.0, min(1.0, (a["alt"] - 6000.0) / 24000.0))
            col = LOW_COL + (HIGH_COL - LOW_COL) * hi
            p = (int(round(x)), int(round(y)))
            prev = self.drawn.get(k)
            if prev is not None and prev != p and abs(prev[0] - p[0]) + abs(prev[1] - p[1]) < 40:
                cv2.line(stamp, prev, p, tuple(int(c * 0.72) for c in col), 1, cv2.LINE_8)
            self.drawn[k] = p
            heads.append((p, col, a.get("flight", "")))
        np.maximum(self.trail, stamp, out=self.trail)
        for k in [k for k in self.drawn if k not in seen]:
            del self.drawn[k]
        img = np.maximum(self.base, self.trail)
        for (x, y), col, flight in heads:
            if 0 <= x < W and 0 <= y < H:
                img[y, x] = col                                      # the plane: one bright LED
                if flight:
                    w = pixelfont.width(flight)
                    tx = x + 3 if x + 3 + w <= W else x - 2 - w      # beside it, on the side with room
                    pixelfont.draw(img, flight, tx, min(H - 5, max(0, y - 2)), col * 0.6)
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


_sky = None


def frame(t):
    global _sky
    if _sky is None:
        _sky = Sky()
    return _sky(t)
