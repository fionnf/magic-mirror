"""Snow: Switzerland as a dark relief, and every slope above the height where snow falls right now lit
white and ice-blue, so the snow line draws itself across the Alps and the Jura and rises and falls with
the weather - low on the north side when the cold comes in from the north, high in Ticino under a warm
south wind. Where it is snowing now, flakes (single LEDs) drift down onto those slopes, as many as the
real snowfall; where snow is lying below the line the ground keeps a soft glow, more for deeper snow.
The snow line is written small at the foot of the wall (SNOW 1400 M). One faint LED is Zürich.

Data: Open-Meteo (open-meteo.com, free, no key), the current conditions on a 5 x 7 grid over the
country, fetched every 45 min while the piece runs: freezing_level_height (m), snowfall (cm in the
last interval), precipitation (mm), snow_depth (m), temperature_2m (C), plus snowfall_height (m)
where the API offers it. The snow line is snowfall_height if given, otherwise the freezing level
less 300 m (snow falls through the 0 C level and melts on the way down within ~300 m: the MeteoSwiss
rule of thumb), otherwise the point's own height plus temperature / 6.5 K per km, less 300 m. Between
the grid points every field is spread with a smooth 40 km weighting, so the line differs north and
south of the Alps as it really does. Last good data is kept in panel_setup/snow_cache.json.

Relief: assets/maps/ch_relief.npz (tools/build_relief.py, AWS terrain tiles + Natural Earth), one
mean elevation per LED, true proportions, the full width of the wall.

Everything is drawn on whole LEDs in a few well-separated levels (the dim ones the wall can show).
"""
import json
import math
import os
import random
import threading
import time

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELIEF = os.path.join(ROOT, "assets", "maps", "ch_relief.npz")
CACHE = os.path.join(ROOT, "panel_setup", "snow_cache.json")
HOME = (47.3726, 8.5398)                          # Rennweg, Zürich
GRID_LAT = (45.95, 46.40, 46.85, 47.30, 47.70)
GRID_LON = (6.20, 6.90, 7.60, 8.30, 9.00, 9.70, 10.35)
URL = "https://api.open-meteo.com/v1/forecast"
VARS = ["temperature_2m", "precipitation", "snowfall", "snow_depth", "freezing_level_height"]
EVERY = 45 * 60                                   # 35 points every 45 min = 1120 calls a day (free: 10 000)
RETRY = 5 * 60
BELOW_FREEZING = 300.0                            # snow line = freezing level - 300 m
SIGMA_KM = 40.0                                   # how far a grid point's weather reaches
EDGE_M = 120.0                                    # the snow line's own band, one level dimmer
EASE = 90.0                                       # seconds for the line to move to new data
INTRO = 12.0                                      # at start the line comes down from the summits
SEASON = (900, 1000, 1200, 1600, 2100, 2700, 3200, 3300, 2800, 2200, 1500, 1000)   # no data at all: a usual month

# Colours: channel values chosen at the wall's visible steps (94, 149, 188, 219, 245 survive 6 bits at
# brightness 35; anything lower is black), so every tone below shows and stays distinct.
PAL = np.array([
    (0, 0, 0),          # 0  valley, plain, slopes facing away
    (0, 0, 100),        # 1  slopes facing the light, deep blue
    (0, 0, 155),        # 2  steep sunlit slopes
    (0, 100, 100),      # 3  lakes (flat and still: one tone, unshaded)
    (0, 100, 155),      # 4  snow, faintest: the line's band in shade, a thin cover lit
    (100, 155, 195),    # 5  snow in shade / the line's band
    (155, 195, 225),    # 6  snow
    (195, 225, 250),    # 7  snow in full light
    (0, 0, 0),          # 8  outside Switzerland
], np.uint8)
OUTSIDE = 8
# snow lying below the line glows with the relief's own light: [thin, deep] x [shade, level, lit]
LYING = np.array([[0, 0, 4], [1, 4, 5]], np.uint8)
FLAKE = np.array([250, 250, 250], np.uint8)
HOME_COL = (155, 100, 0)
TEXT_COL = (100, 100, 155)


def _load_relief():
    d = np.load(RELIEF)
    lat_c, lon_c, km_px, y0 = (float(v) for v in d["meta"])
    return d["elev"].astype(np.float32), d["ch"].astype(bool), d["lakes"].astype(bool), lat_c, lon_c, km_px, int(y0)


def _hillshade(elev, km_px, z=2.5, az=315.0, alt=40.0):
    """Light from the north-west, slopes exaggerated for the shading only (the map keeps true shape)."""
    gy, gx = np.gradient(elev * z, km_px * 1000.0)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, s = math.radians(az), math.radians(alt)
    hs = np.sin(s) * np.cos(slope) + np.cos(s) * np.sin(slope) * np.cos(a - aspect - math.pi / 2)
    return hs, slope


class Snow:
    def __init__(self):
        self.elev, self.ch, self.lakes, lat_c, lon_c, km_px, self.y0 = _load_relief()
        self.bh = self.elev.shape[0]
        kx = math.cos(math.radians(lat_c)) * 111.32
        self.to_px = lambda lat, lon: ((lon - lon_c) * kx / km_px + W / 2 - 0.5,
                                       (lat_c - lat) * 111.32 / km_px + H / 2 - 0.5)
        hs, slope = _hillshade(self.elev, km_px)
        flat = math.sin(math.radians(40.0))           # what level ground gets
        # quiet relief: flat land and shade dark, only the faces turned to the light show
        self.relief_idx = np.where(hs > flat + 0.16, 2, np.where(hs > flat + 0.05, 1, 0)).astype(np.uint8)
        self.relief_idx[self.lakes] = 3
        self.relief_idx[~self.ch] = OUTSIDE
        # the border: the outermost LEDs of the country, faint, so its shape holds on a dark night
        inner = self.ch.copy()
        inner[1:] &= self.ch[:-1]; inner[:-1] &= self.ch[1:]
        inner[:, 1:] &= self.ch[:, :-1]; inner[:, :-1] &= self.ch[:, 1:]
        self.border = self.ch & ~inner
        self.relief_idx[self.border & (self.relief_idx == 0)] = 1
        self.light = np.where(hs > flat + 0.05, 2, np.where(hs > flat - 0.05, 1, 0)).astype(np.uint8)
        self.snow_idx = np.where(hs > flat + 0.15, 7, np.where(hs > flat - 0.08, 6, 5)).astype(np.uint8)
        self.edge_idx = np.minimum(self.snow_idx - 1, 5)          # the band at the line: a step dimmer
        # field weights: every LED of the band against every grid point
        self.pts = [(la, lo) for la in GRID_LAT for lo in GRID_LON]
        yy, xx = np.mgrid[0:self.bh, 0:W].astype(np.float32)
        yy += self.y0
        wts = []
        for la, lo in self.pts:
            px, py = self.to_px(la, lo)
            d2 = ((xx - px) ** 2 + (yy - py) ** 2) * km_px ** 2
            wts.append(np.exp(-d2 / (2 * SIGMA_KM ** 2)) + 1e-9)
        wts = np.stack(wts, -1)
        self.wts = (wts / wts.sum(-1, keepdims=True)).reshape(-1, len(self.pts)).astype(np.float32)
        hx, hy = self.to_px(*HOME)
        self.home = (int(round(hx)), int(round(hy)))
        self.data, self.data_t = None, 0.0
        self.no_height = False                        # the API refused snowfall_height once: stop asking
        self.lock = threading.Lock()
        self.fresh = False
        self._load_cache()
        self.line_from = None                          # the line field easing from ...
        self.line_to = self._line_field()              # ... to this
        self.ease_t0 = None
        self.start = None
        self.cached_key, self.cached_img = None, None
        self.flakes = np.zeros((0, 5), np.float32)     # x, y, target y, speed, phase
        self.spawn_acc = 0.0
        self.last_t = None
        self.rng = np.random.default_rng()
        threading.Thread(target=self._fetch_loop, daemon=True).start()

    # ---------------------------------------------------------------- data
    def _load_cache(self):
        try:
            with open(CACHE) as fh:
                c = json.load(fh)
            if len(c.get("points", [])) == len(self.pts):
                self.data, self.data_t = c["points"], float(c.get("t", 0))
                self._derive()
        except Exception:
            pass

    def _derive(self):
        """Per-LED fields from the grid points (on data arrival only, never per frame)."""
        age = time.time() - self.data_t
        p = self.data
        line = np.array([q["line"] for q in p], np.float32)
        rate = np.array([q["rate"] for q in p], np.float32) if age < 3 * 3600 else np.zeros(len(p), np.float32)
        wet = np.array([q.get("precip", 0.0) for q in p], np.float32) if age < 3 * 3600 else np.zeros(len(p), np.float32)
        depth = np.array([q["depth"] for q in p], np.float32) if age < 48 * 3600 else np.zeros(len(p), np.float32)
        f = lambda v: (self.wts @ v).reshape(self.bh, W)
        self.f_line = f(line)
        lf = self.f_line
        # snowfall per LED: the model's snowfall, or its precipitation (0.7 cm of snow per mm) on slopes
        # above the line - a valley grid point raining while the peaks around it get snow
        self.f_rate = np.maximum(f(rate), np.where(self.elev >= lf - 100.0, f(wet) * 0.7, 0.0))
        self.f_rate[~self.ch] = 0.0
        self.f_depth = f(depth)
        self.snowing = float(self.f_rate.sum())
        rows, cols = np.nonzero(self.f_rate > 0.02)
        w = self.f_rate[rows, cols]
        self.spawn_cells = (rows, cols, (np.cumsum(w) / w.sum()) if len(w) else None)
        self.label = "SNOW {} M".format(int(round(float(np.median(lf[self.ch])) / 100.0) * 100)) if age < 48 * 3600 else ""

    def _line_field(self):
        if self.data is not None and time.time() - self.data_t < 48 * 3600:
            return self.f_line.copy()
        self.label = ""
        self.f_rate = np.zeros((self.bh, W), np.float32)
        self.f_depth = np.zeros((self.bh, W), np.float32)
        self.spawn_cells, self.snowing = (None, None, None), 0.0
        return np.full((self.bh, W), SEASON[time.localtime().tm_mon - 1], np.float32)

    def _fetch_loop(self):
        import requests
        if time.time() - self.data_t < EVERY - 60:
            time.sleep(EVERY - (time.time() - self.data_t))
        while True:
            ok = False
            try:
                ok = self._fetch(requests)
            except Exception as e:
                print(f"[snow] {str(e)[:120]}", flush=True)
            time.sleep(EVERY if ok else RETRY)

    def _fetch(self, requests):
        vars_ = VARS + ([] if self.no_height else ["snowfall_height"])
        params = {"latitude": ",".join(str(p[0]) for p in self.pts),
                  "longitude": ",".join(str(p[1]) for p in self.pts),
                  "current": ",".join(vars_), "timezone": "GMT"}
        r = requests.get(URL, params=params, timeout=20)
        if r.status_code == 400 and not self.no_height:        # the variable is not offered: ask without it
            self.no_height = True
            print("[snow] no snowfall_height, using freezing level - 300 m", flush=True)
            return self._fetch(requests)
        r.raise_for_status()
        got = r.json()
        got = got if isinstance(got, list) else [got]
        if len(got) != len(self.pts):
            raise ValueError(f"{len(got)} points back")
        pts = [self.parse(g) for g in got]
        if all(q is None for q in pts):
            raise ValueError("no usable values")
        fill = [q for q in pts if q is not None]           # a gap takes the mean of the rest
        mean = {k: sum(q[k] for q in fill) / len(fill) for k in fill[0]}
        pts = [q if q is not None else dict(mean) for q in pts]
        with self.lock:
            self.data, self.data_t = pts, time.time()
            self.fresh = True
        try:
            tmp = CACHE + ".tmp"
            with open(tmp, "w") as fh:
                json.dump({"t": self.data_t, "points": pts}, fh)
            os.replace(tmp, CACHE)
        except Exception as e:
            print(f"[snow] cache: {str(e)[:80]}", flush=True)
        return True

    @staticmethod
    def parse(g):
        """One location of the response -> {line m, rate cm/h, precip mm/h, depth m}."""
        c = g.get("current") or {}
        num = lambda k: float(c[k]) if isinstance(c.get(k), (int, float)) else None
        step = float(c.get("interval") or 900) / 3600.0      # sums are over the current interval (15 min)
        line = num("snowfall_height")
        if line is None and num("freezing_level_height") is not None:
            line = num("freezing_level_height") - BELOW_FREEZING
        if line is None and num("temperature_2m") is not None:
            line = float(g.get("elevation") or 500.0) + num("temperature_2m") / 0.0065 - BELOW_FREEZING
        if line is None:
            return None
        return {"line": max(0.0, min(5000.0, line)),
                "rate": max(0.0, (num("snowfall") or 0.0) / step),
                "precip": max(0.0, (num("precipitation") or 0.0) / step),
                "depth": max(0.0, num("snow_depth") or 0.0)}

    # ---------------------------------------------------------------- drawing
    def _line_now(self, t):
        if self.fresh:
            with self.lock:
                self.fresh = False
                self._derive()
            self.line_from, self.line_to, self.ease_t0 = self._current_line(t), self.f_line.copy(), t
        if self.start is None:
            self.start = t
        u = (t - self.start) / INTRO
        if u < 1.0:                                    # the snow line comes down from the summits
            s = 1.0 - (1.0 - u) ** 3
            return 4800.0 + (self.line_to - 4800.0) * s, ("intro", int(u * 400))
        if self.ease_t0 is not None:
            v = (t - self.ease_t0) / EASE
            if v < 1.0:
                s = v * v * (3 - 2 * v)
                return self.line_from + (self.line_to - self.line_from) * s, ("ease", self.ease_t0, int(v * 400))
            self.ease_t0 = None
        return self.line_to, ("still", id(self.line_to))

    def _current_line(self, t):
        line, _ = self._line_now_peek(t)
        return line

    def _line_now_peek(self, t):
        if self.start is not None and (t - self.start) < INTRO:
            s = 1.0 - (1.0 - (t - self.start) / INTRO) ** 3
            return 4800.0 + (self.line_to - 4800.0) * s, None
        if self.ease_t0 is not None and (t - self.ease_t0) < EASE:
            v = (t - self.ease_t0) / EASE
            s = v * v * (3 - 2 * v)
            return self.line_from + (self.line_to - self.line_from) * s, None
        return self.line_to, None

    def _compose(self, line):
        from display import pixelfont
        e = self.elev
        idx = self.relief_idx.copy()
        lying = (self.f_depth > 0.02) & self.ch & ~self.lakes
        deep = (self.f_depth > 0.25).astype(np.uint8)
        idx[lying] = LYING[deep[lying], self.light[lying]]
        snow = (e >= line) & self.ch & ~self.lakes
        idx[snow] = self.edge_idx[snow]
        top = (e >= line + EDGE_M) & self.ch & ~self.lakes
        idx[top] = self.snow_idx[top]
        img = np.zeros((H, W, 3), np.uint8)
        img[self.y0:self.y0 + self.bh] = PAL[idx]
        hx, hy = self.home
        if 0 <= hx < W and 0 <= hy < H:
            img[hy, hx] = np.maximum(img[hy, hx], HOME_COL)
        if self.label:
            pixelfont.draw(img, self.label, W - 2 - pixelfont.width(self.label), H - 8, TEXT_COL)
        return img

    def _flakes(self, img, t, dt):
        rows, cols, cum = self.spawn_cells
        if cum is not None and len(self.flakes) < 700:
            # concurrent flakes per LED ~ 0.03 per cm/h; each lives ~ fall / speed seconds
            self.spawn_acc += self.snowing * 0.012 * dt
            n = int(self.spawn_acc)
            self.spawn_acc -= n
            if n:
                k = np.searchsorted(cum, self.rng.random(n))
                k = np.minimum(k, len(cum) - 1)
                ty = rows[k].astype(np.float32) + self.y0
                fall = self.rng.uniform(6, 20, n).astype(np.float32)
                new = np.stack([cols[k].astype(np.float32), ty - fall, ty,
                                self.rng.uniform(4.0, 8.0, n).astype(np.float32),
                                self.rng.uniform(0, 6.28, n).astype(np.float32)], 1)
                self.flakes = np.concatenate([self.flakes, new])
        if not len(self.flakes):
            return
        f = self.flakes
        f[:, 1] += f[:, 3] * dt
        self.flakes = f = f[f[:, 1] < f[:, 2]]
        x = np.rint(f[:, 0] + np.sin(t * 0.9 + f[:, 4]) * 1.2).astype(np.int32)
        y = np.rint(f[:, 1]).astype(np.int32)
        ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
        img[y[ok], x[ok]] = FLAKE

    def __call__(self, t):
        dt = 0.03 if self.last_t is None else max(0.0, min(0.5, t - self.last_t))
        self.last_t = t
        line, key = self._line_now(t)
        if key != self.cached_key:
            self.cached_key, self.cached_img = key, self._compose(line)
        img = self.cached_img.copy()
        self._flakes(img, t, dt)
        return Image.fromarray(img, "RGB")


_snow = None
_dead = None


def frame(t):
    global _snow, _dead
    try:
        if _snow is None:
            _snow = Snow()
        return _snow(t)
    except Exception as e:                             # never take the wall down: a quiet black frame
        if _dead is None:
            _dead = Image.new("RGB", (W, H))
            print(f"[snow] {str(e)[:160]}", flush=True)
        return _dead
