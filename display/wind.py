"""Wind: the air over Switzerland, or over Ireland, as live art. Thousands of points of light drift with
the real 10 m wind of the moment, each leaving a short trail that fades, so the air visibly flows:
on a still day the lights barely creep and glow a cool deep teal; a breeze turns them ice white; a
föhn storm or an Atlantic gale sends warm amber and coral streaks racing across the wall. Gusts
travel through the field as bands where the lights surge and brighten, as strong as the gusts are.
Underneath, very quiet, the country: Switzerland's border and its big lakes, or Ireland's coast, with
one faint LED for home (Rennweg in Zürich; Schull in West Cork). Maps: assets/maps/switzerland.json
and ireland.json (Natural Earth, from tools/build_maps.py).

The wind is Open-Meteo's (free, no key): speed, direction and gusts at a 6 x 8 grid of points over the
picture, fetched every 30 minutes on a side thread while the piece runs, kept in
panel_setup/wind_cache.json, and blended between the points (as east and north components, so the
directions turn smoothly). A new fetch eases in over a minute. The direction is where the wind comes
FROM, so the lights move the other way. The air runs about 1000 times faster than real (1 m/s is half
an LED a second at 2 km per LED): calm is calm, a gale is spectacular.

Everything is drawn on whole LEDs (no anti-aliasing): a soft dot gliding between LEDs shimmers.
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
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "panel_setup", "wind_cache.json")
URL = "https://api.open-meteo.com/v1/forecast"
EVERY = 1800.0                 # 48 points every 30 min = 2304 location-calls a day per region (free tier 10,000)
IDLE = 120.0                   # no frame drawn for this long: the piece is not showing, stop fetching
NX, NY = 6, 8                  # the grid of wind points over the picture
REGIONS = {
    #       centre of the picture   km per LED  home (one faint LED)  map
    "ch": ((46.80, 8.21), 2.0, (47.3726, 8.5398), "switzerland.json"),
    "ie": ((53.41, -7.95), 1.95, (51.527, -9.547), "ireland.json"),
}

N = 2600                       # points of light
K = 0.5                        # LEDs per second for each m/s of wind
TAU = 0.85                     # seconds for a trail to fall to 1/e (about five LED steps from head to dark)
LIFE = (6.0, 14.0)             # each light lives this long, then is born again somewhere else...
RAMP = 1.2                     # ...fading in and out over this, so the field never clumps or pops
EASE = 60.0                    # seconds for a new fetch to blend in
GUST_LEN = 46.0                # LEDs between gust bands
# Colour by the wind each light feels (m/s): still = deep teal, breeze = ice, fresh = warm white,
# strong = amber, gale = coral and rose. Every stop keeps a channel well above the LEDs' dark floor.
SPEEDS = np.array([0.0, 2.0, 4.0, 7.0, 11.0, 15.0, 20.0, 27.0], np.float32)
COLS = np.array([(30, 108, 150), (50, 130, 192), (110, 172, 222), (172, 212, 238),
                 (246, 232, 200), (255, 192, 112), (255, 132, 112), (255, 96, 150)], np.float32)
BORDER = (36, 64, 116)         # the quiet map: just over the LEDs' floor, a deep blue line
LAKE = (36, 64, 116)
HOME_LED = (128, 120, 112)

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
        except Exception as e:
            print(f"[wind] cache: {str(e)[:80]}", flush=True)


class Wind:
    def __init__(self, key, fetch=True):
        self.key = key
        centre, self.km, home, mapname = REGIONS[key]
        self.lat0, self.lon0 = centre
        self.coslat = math.cos(math.radians(self.lat0))
        self.base = self._base_map(os.path.join(ROOT, "assets", "maps", mapname), home).astype(np.float32)
        # the grid: the centres of a 6 x 8 tiling of the picture, as lat/lon for the API
        self.gx = (np.arange(NX) + 0.5) * W / NX
        self.gy = (np.arange(NY) + 0.5) * H / NY
        self.lats = [round(self.lat0 - (y - H / 2) * self.km / 111.32, 3) for y in self.gy for _ in self.gx]
        self.lons = [round(self.lon0 + (x - W / 2) * self.km / (111.32 * self.coslat), 3) for _ in self.gy for x in self.gx]
        self.field, self.prev, self.t_new = None, None, 0.0      # (u, v, gust, dir_x, dir_y, mean) per LED
        self.arrived = None
        self.trail = np.zeros((H, W, 3), np.float32)
        rng = np.random.default_rng()
        self.rng = rng
        self.x, self.y = rng.uniform(0, W, N), rng.uniform(0, H, N)
        self.life = rng.uniform(*LIFE, N)
        self.age = rng.uniform(0, 1, N) * self.life
        self.last, self.last_frame, self.ok = None, time.time(), False
        rec = _read_cache().get(key)
        if rec and rec.get("grid") == [NX, NY]:
            self._use(rec, ease=False)
        self.fetched = rec.get("t", 0.0) if rec and rec.get("grid") == [NX, NY] else 0.0
        if fetch:
            threading.Thread(target=self._fetch_loop, daemon=True).start()

    # ---------------------------------------------------------------- map ---
    def to_px(self, lat, lon):
        return ((lon - self.lon0) * 111.32 * self.coslat / self.km + W / 2,
                (self.lat0 - lat) * 111.32 / self.km + H / 2)

    def _base_map(self, path, home):
        """The still map under the wind, one LED wide: the border or coast, the lakes, home."""
        import cv2
        img = np.zeros((H, W, 3), np.uint8)
        try:
            with open(path) as fh:
                m = json.load(fh)
        except Exception:
            m = {}
        pts = lambda line: np.array([[round(v) for v in self.to_px(*p)] for p in line], np.int32)
        for lake in m.get("lakes", []):
            cv2.polylines(img, [pts(lake)], True, LAKE, 1, cv2.LINE_8)
        for b in m.get("border", []):
            cv2.polylines(img, [pts(b)], True, BORDER, 1, cv2.LINE_8)
        for c in m.get("coast", []):
            cv2.polylines(img, [pts(c)], False, BORDER, 1, cv2.LINE_8)
        x, y = (int(round(v)) for v in self.to_px(*home))
        if 0 <= x < W and 0 <= y < H:
            img[y, x] = HOME_LED
        return img

    # --------------------------------------------------------------- data ---
    def _fetch_loop(self):
        import requests
        wait = max(0.0, self.fetched + EVERY - time.time())
        backoff = 120.0
        while True:
            time.sleep(min(wait, 10.0))
            wait -= 10.0
            if wait > 0:
                continue
            if time.time() - self.last_frame > IDLE:                 # not on the wall: no calls
                wait = 10.0
                continue
            try:
                r = requests.get(URL, timeout=25, params={
                    "latitude": ",".join(f"{v:.3f}" for v in self.lats),
                    "longitude": ",".join(f"{v:.3f}" for v in self.lons),
                    "current": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
                    "wind_speed_unit": "ms", "cell_selection": "nearest"})
                if r.status_code == 429:                             # the free tier's daily limit: come back later
                    raise RuntimeError("429 " + r.text[:80])
                r.raise_for_status()
                rec = self.parse(r.json())
                self._use(rec, ease=True)
                _write_cache(self.key, rec)
                self.ok, wait, backoff = True, EVERY, 120.0
            except Exception as e:
                self.ok = False
                wait = 3600.0 if str(e).startswith("429") else backoff
                backoff = min(EVERY, backoff * 2)
                print(f"[wind {self.key}] {str(e)[:100]}", flush=True)

    @staticmethod
    def parse(js):
        """Open-Meteo's answer (a list, one entry per point, in the order asked) -> a cache record."""
        pts = js if isinstance(js, list) else [js]
        if len(pts) != NX * NY:
            raise ValueError(f"{len(pts)} points, wanted {NX * NY}")
        get = lambda k: [p.get("current", {}).get(k) for p in pts]
        sp, di, gu = get("wind_speed_10m"), get("wind_direction_10m"), get("wind_gusts_10m")
        return {"t": time.time(), "grid": [NX, NY], "time": pts[0].get("current", {}).get("time", ""),
                "speed": sp, "dir": di, "gust": gu}

    def _use(self, rec, ease):
        """A cache record -> the wind at every LED (bilinear between the grid points)."""
        sp = np.array([np.nan if v is None else v for v in rec["speed"]], np.float32)
        di = np.array([np.nan if v is None else v for v in rec["dir"]], np.float32)
        gu = np.array([np.nan if v is None else v for v in rec["gust"]], np.float32)
        good = np.isfinite(sp) & np.isfinite(di)
        if not good.any():
            return
        r = np.radians(np.where(good, di, 0))
        u = np.where(good, -sp * np.sin(r), 0)                      # the way the air goes, east...
        v = np.where(good, sp * np.cos(r), 0)                       # ...and down the picture (south)
        u[~good], v[~good] = u[good].mean(), v[good].mean()
        gu = np.where(np.isfinite(gu), gu, np.where(good, sp, 0) * 1.4)
        gu = np.maximum(gu, np.hypot(u, v))

        def up(a):
            a = a.reshape(NY, NX)
            fx = np.clip((np.arange(W) + 0.5) / (W / NX) - 0.5, 0, NX - 1)
            fy = np.clip((np.arange(H) + 0.5) / (H / NY) - 0.5, 0, NY - 1)
            x0, y0 = np.minimum(fx.astype(int), NX - 2), np.minimum(fy.astype(int), NY - 2)
            tx, ty = (fx - x0)[None, :], (fy - y0)[:, None]
            a00, a01 = a[y0][:, x0], a[y0][:, x0 + 1]
            a10, a11 = a[y0 + 1][:, x0], a[y0 + 1][:, x0 + 1]
            return ((a00 * (1 - tx) + a01 * tx) * (1 - ty) + (a10 * (1 - tx) + a11 * tx) * ty).astype(np.float32)

        mu, mv = float(u.mean()), float(v.mean())
        mean = math.hypot(mu, mv)
        d = (mu / mean, mv / mean) if mean > 0.2 else (1.0, 0.0)
        field = (up(u), up(v), up(gu), d, float(np.hypot(u, v).mean()))
        self.prev = self.field if (ease and self.field is not None) else None
        self.field, self.t_new = field, time.time()

    # -------------------------------------------------------------- frame ---
    def __call__(self, t):
        self.last_frame = time.time()
        dt = 1 / 30 if self.last is None else max(0.0, min(0.2, t - self.last))
        self.last = t
        self.trail *= math.exp(-dt / TAU)
        f = self.field
        if f is not None:
            if self.arrived is None:
                self.arrived = t
            self._step(f, t, dt)
        img = np.maximum(self.base, self.trail)
        return Image.fromarray(img.astype(np.uint8), "RGB")

    def _step(self, f, t, dt):
        ix = np.clip(self.x.astype(np.int32), 0, W - 1)
        iy = np.clip(self.y.astype(np.int32), 0, H - 1)
        u, v, g = f[0][iy, ix], f[1][iy, ix], f[2][iy, ix]
        p = self.prev
        if p is not None:                                            # a new fetch eases in
            a = (time.time() - self.t_new) / EASE
            if a >= 1:
                self.prev = None
            else:
                a = a * a * (3 - 2 * a)
                u = p[0][iy, ix] + (u - p[0][iy, ix]) * a
                v = p[1][iy, ix] + (v - p[1][iy, ix]) * a
                g = p[2][iy, ix] + (g - p[2][iy, ix]) * a
        s = np.hypot(u, v)
        # gusts: bands across the mean wind that travel with it; inside a band the air runs at up to
        # the gust speed. Patchy along the band, so it reads as gusts, not as a wave machine.
        dx, dy = f[3]
        along = (self.x * dx + self.y * dy - t * K * f[4]) * (2 * math.pi / GUST_LEN)
        across = (self.y * dx - self.x * dy) * (2 * math.pi / (GUST_LEN * 1.7)) + 0.9 * math.sin(t * 0.07)
        pulse = np.clip(np.sin(along), 0, None) ** 2 * (0.55 + 0.45 * np.sin(across))
        boost = 1 + (g / np.maximum(s, 0.3) - 1) * pulse * 0.8
        self.x += u * boost * (K * dt)
        self.y += v * boost * (K * dt)
        self.age += dt
        dead = (self.age > self.life) | (self.x < 0) | (self.x >= W) | (self.y < 0) | (self.y >= H)
        if dead.any():
            n = int(dead.sum())
            self.x[dead], self.y[dead] = self.rng.uniform(0, W, n), self.rng.uniform(0, H, n)
            self.age[dead], self.life[dead] = 0.0, self.rng.uniform(*LIFE, n)
        feel = s * boost
        lvl = np.minimum(1.0, np.minimum(self.age, self.life - self.age) / RAMP)
        lvl *= min(1.0, (t - self.arrived) / 3.0)                     # the first data fades in
        col = np.stack([np.interp(feel, SPEEDS, COLS[:, c]) for c in range(3)], 1) * lvl[:, None]
        ix = self.x.astype(np.int32)
        iy = self.y.astype(np.int32)
        self.trail[iy, ix] = np.maximum(self.trail[iy, ix], col)


_w = {}


def _frame(key, t):
    if key not in _w:
        _w[key] = Wind(key)
    return _w[key](t)


def frame_ch(t):
    return _frame("ch", t)


def frame_ie(t):
    return _frame("ie", t)


frame = frame_ch
