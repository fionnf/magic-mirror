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
    "eu": ((56.0, -7.0), 11.0, (47.3726, 8.5398), "europe.json"),     # Iceland to Switzerland
    "ie": ((53.30, -9.60), 3.0, (51.527, -9.547), "ireland.json"),   # zoomed out and west: the Atlantic too
}

N = 1700                       # points of light
K = 0.5                        # LEDs per second for each m/s of wind
TAU = 0.85                     # seconds for a trail to fall to 1/e (about five LED steps from head to dark)
LIFE = (6.0, 14.0)             # each light lives this long, then is born again somewhere else...
RAMP = 1.2                     # ...fading in and out over this, so the field never clumps or pops
EASE = 60.0                    # seconds for a new fetch to blend in
GUST_LEN = 40.0                # LEDs across a gust patch
GUST_EVERY = 6.0               # seconds between surges
# Colour by the wind each light feels (m/s): still = deep teal, breeze = ice, fresh = warm white,
# strong = amber, gale = coral and rose. Every stop keeps a channel well above the LEDs' dark floor.
SPEEDS = np.array([0.0, 2.0, 4.0, 7.0, 11.0, 15.0, 20.0, 27.0], np.float32)
COLS = np.array([(30, 108, 150), (50, 130, 192), (110, 172, 222), (172, 212, 238),
                 (246, 232, 200), (255, 192, 112), (255, 132, 112), (255, 96, 150)], np.float32)
BORDER = (36, 64, 116)         # the quiet map: just over the LEDs' floor, a deep blue line
LAKE = (36, 64, 116)
HOME_LED = (128, 120, 112)

# ---- Europe (key "eu") is drawn differently: not thousands of fast sparks but ~90 long, slow streamers with
# tapering tails, over a black sea with the land as a faint dither, a dotted graticule and the coast as a hairline.
EU_M = 130                     # streamers
EU_L = 34                      # tail points (1 LED apart: a tail is ~34 LEDs long)
EU_K = 0.65                    # LEDs per second per m/s
EU_LIFE = (9.0, 18.0)
EU_FLOOR = 96                  # a lit LED keeps a channel at least this high; fainter light is dithered out
EU_SPEEDS = np.array([0.0, 3.0, 6.0, 10.0, 14.0, 19.0, 25.0, 32.0], np.float32)
EU_COLS = np.array([(36, 112, 150), (48, 136, 196), (96, 168, 224), (170, 212, 236),
                    (238, 230, 200), (255, 190, 120), (255, 140, 120), (240, 104, 150)], np.float32)
EU_LAND = (30, 50, 104)
EU_COAST = (58, 98, 168)
EU_GRID = (34, 54, 108)
EU_HALO = (236, 216, 186)
_BAYER8 = (np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
                     [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
                     [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                     [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], np.float32) + 0.5) / 64.0

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
        self.area = [self.lat0, self.lon0, self.km]
        self.coslat = math.cos(math.radians(self.lat0))
        if key == "eu":
            self.base = self._base_eu(os.path.join(ROOT, "assets", "maps", mapname), home).astype(np.float32)
        else:
            self.base = self._base_map(os.path.join(ROOT, "assets", "maps", mapname), home).astype(np.float32)
        # the grid: the centres of a 6 x 8 tiling of the picture, as lat/lon for the API
        self.gx = (np.arange(NX) + 0.5) * W / NX
        self.gy = (np.arange(NY) + 0.5) * H / NY
        self.lats = [round(self.lat0 - (y - H / 2) * self.km / 111.32, 3) for y in self.gy for _ in self.gx]
        self.lons = [round(self.lon0 + (x - W / 2) * self.km / (111.32 * self.coslat), 3) for _ in self.gy for x in self.gx]
        self.field, self.prev, self.t_new = None, None, 0.0      # (u, v, gust at every LED, mean direction)
        self.arrived = None
        self.trail = np.zeros((H, W, 3), np.float32)
        rng = np.random.default_rng()
        self.rng = rng
        self.x, self.y = rng.uniform(0, W, N), rng.uniform(0, H, N)
        self.life = rng.uniform(*LIFE, N)
        self.age = rng.uniform(0, 1, N) * self.life
        self.phase = self._phase(self.x, self.y)
        self.last, self.last_frame, self.ok = None, time.time(), False
        if key == "eu":
            self._init_eu(home)
        rec = _read_cache().get(key)
        if not (rec and rec.get("grid") == [NX, NY] and rec.get("area") == self.area):
            rec = None                                        # fetched for another grid or another view
        if rec:
            self._use(rec, ease=False)
        self.fetched = rec.get("t", 0.0) if rec else 0.0
        if fetch:
            threading.Thread(target=self._fetch_loop, daemon=True).start()

    def _phase(self, x, y):
        """Each light's place in the gust cycle, from where it was born: neighbours surge together."""
        return (np.sin(x * (2 * math.pi / GUST_LEN)) + np.sin(y * (2 * math.pi / (GUST_LEN * 1.3)) + 1.0)
                + 0.35 * self.rng.standard_normal(len(x))) * 1.6

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
                rec = {**self.parse(r.json()), "area": self.area}
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
        field = (up(u), up(v), up(gu), (mu / mean, mv / mean) if mean > 0.5 else None)
        self.prev = self.field if (ease and self.field is not None) else None
        self.field, self.t_new = field, time.time()


    # ------------------------------------------------------------- europe ---
    def _base_eu(self, path, home):
        """Europe's still layer: black sea, the land as a faint ordered dither, a dotted graticule, the coast as
        a hairline, Switzerland's border as a fainter one."""
        import cv2
        try:
            with open(path) as fh:
                m = json.load(fh)
        except Exception:
            m = {}
        pts = lambda line: np.array([[int(round(v)) for v in self.to_px(*p)] for p in line], np.int32)
        land = np.zeros((H, W), np.uint8)
        coast = m.get("coast", [])
        for c in coast:                                           # islands: closed rings
            if len(c) > 3 and c[0] == c[-1]:
                cv2.fillPoly(land, [pts(c)], 1)
        # the mainland coast comes as open lines cut at the map's edge: join them off the picture and fill
        open_ = [c for c in coast if len(c) > 100 and c[0] != c[-1]]
        if len(open_) >= 2:
            open_.sort(key=lambda c: -c[0][0])                    # north to south
            ring = []
            for c in open_:
                ring += pts(c).tolist()
            far = [self.to_px(30.0, -60.0), self.to_px(30.0, 40.0), self.to_px(80.0, 40.0)]
            ring += [[int(v) for v in p] for p in far]
            cv2.fillPoly(land, [np.array(ring, np.int32)], 1)
        img = np.zeros((H, W, 3), np.uint8)
        yy, xx = np.mgrid[0:H, 0:W]
        dens = _BAYER8[yy % 8, xx % 8] < 0.14                     # about one LED in seven: a soft landmass tone
        img[(land > 0) & dens] = EU_LAND
        # graticule: dotted lines every 5 degrees of latitude and 10 of longitude
        for lat in range(40, 75, 5):
            y = int(round(self.to_px(lat, 0)[1]))
            if 0 <= y < H:
                img[y, ::6] = EU_GRID
        for lon in range(-40, 30, 10):
            x = int(round(self.to_px(56, lon)[0]))
            if 0 <= x < W:
                img[::6, x] = EU_GRID
        for c in coast:
            if len(c) >= 4:
                cv2.polylines(img, [pts(c)], False, EU_COAST, 1, cv2.LINE_8)
        for b in m.get("border", []):
            cv2.polylines(img, [pts(b)], True, (46, 78, 140), 1, cv2.LINE_8)
        return img

    def _init_eu(self, home):
        rng = self.rng
        self.ex = np.zeros((EU_M, 2), np.float32)
        self.eh = np.zeros((EU_M, EU_L, 2), np.float32)
        self.elife = rng.uniform(*EU_LIFE, EU_M)
        self.eage = rng.uniform(0, 1, EU_M) * self.elife
        self.ephase = rng.uniform(0, 6.3, EU_M)
        for i in range(EU_M):
            self.ex[i] = self._best_spot(self.ex[:i])
        self.eh[:] = self.ex[:, None, :]
        self.efeel = np.zeros(EU_M, np.float32)
        hx, hy = (int(round(v)) for v in self.to_px(*home))
        self.home_px = (hx, hy)
        r = 9
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
        d = np.hypot(xx, yy)
        self.halo = np.clip(1 - d / r, 0, 1) ** 1.1                # soft falloff, dithered by the floor pass
        self.halo[r, r] = 0.0
        self.eyy, self.exx = np.mgrid[0:H, 0:W]
        self.ethr = _BAYER8[self.eyy % 8, self.exx % 8]

    def _best_spot(self, others):
        """Best-candidate sampling: of a few random spots take the one farthest from the other streamers."""
        c = np.stack([self.rng.uniform(0, W, 7), self.rng.uniform(0, H, 7)], 1).astype(np.float32)
        if len(others) == 0:
            return c[0]
        d = np.hypot(c[:, None, 0] - others[None, :, 0], c[:, None, 1] - others[None, :, 1]).min(1)
        return c[int(np.argmax(d))]

    def _uvg(self, ix, iy):
        f = self.field
        u, v, g = f[0][iy, ix], f[1][iy, ix], f[2][iy, ix]
        p = self.prev
        if p is not None:
            a = (time.time() - self.t_new) / EASE
            if a >= 1:
                self.prev = None
            else:
                a = a * a * (3 - 2 * a)
                u = p[0][iy, ix] + (u - p[0][iy, ix]) * a
                v = p[1][iy, ix] + (v - p[1][iy, ix]) * a
                g = p[2][iy, ix] + (g - p[2][iy, ix]) * a
        return u, v, g

    def _call_eu(self, t, dt):
        img = self.base.copy()
        if self.field is not None:
            if self.arrived is None:
                self.arrived = t
            self._step_eu(t, dt, img)
        # the home halo: Switzerland breathes gently
        hx, hy = self.home_px
        r = self.halo.shape[0] // 2
        breath = 0.80 + 0.20 * math.sin(t * 0.9)
        x0, x1, y0, y1 = max(hx - r, 0), min(hx + r + 1, W), max(hy - r, 0), min(hy + r + 1, H)
        if x1 > x0 and y1 > y0:
            patch = self.halo[y0 - hy + r:y1 - hy + r, x0 - hx + r:x1 - hx + r, None] * breath * np.array(EU_HALO, np.float32)
            img[y0:y1, x0:x1] = np.maximum(img[y0:y1, x0:x1], patch)
        if 0 <= hx < W and 0 <= hy < H:
            img[hy, hx] = np.maximum(img[hy, hx], (255, 240, 214))
        # the floor: light too faint for the LEDs is dithered out (kept with probability = its brightness)
        m = img.max(2)
        faint = (m > 0) & (m < EU_FLOOR)
        keep = faint & (m / EU_FLOOR > self.ethr)
        lit = img[keep] * (EU_FLOOR / m[keep])[:, None]
        img[faint] = 0
        img[keep] = lit
        return Image.fromarray(img.astype(np.uint8), "RGB")

    def _step_eu(self, t, dt, img):
        pos = self.ex
        ix = np.clip(pos[:, 0].astype(np.int32), 0, W - 1)
        iy = np.clip(pos[:, 1].astype(np.int32), 0, H - 1)
        u, v, g = self._uvg(ix, iy)
        s = np.hypot(u, v)
        pulse = np.clip(np.sin(t * (2 * math.pi / 8.0) + self.ephase), 0, None) ** 3
        boost = 1 + (g / np.maximum(s, 0.3) - 1) * pulse * 0.45
        pos[:, 0] += u * boost * (EU_K * dt)
        pos[:, 1] += v * boost * (EU_K * dt)
        self.eage += dt
        self.efeel += (s * boost - self.efeel) * min(1.0, dt * 1.5)
        out = (pos[:, 0] < 0) | (pos[:, 0] >= W) | (pos[:, 1] < 0) | (pos[:, 1] >= H)
        # a head that leaves the picture lets its tail fade, then is born again somewhere sparse
        self.eage[out] = np.maximum(self.eage[out], self.elife[out] - RAMP)
        dead = self.eage > self.elife
        if dead.any():
            for i in np.nonzero(dead)[0]:
                others = np.delete(pos, i, axis=0)
                pos[i] = self._best_spot(others)
                self.eh[i] = pos[i]
            n = int(dead.sum())
            self.eage[dead], self.elife[dead] = 0.0, self.rng.uniform(*EU_LIFE, n)
            self.efeel[dead] = s[dead]
        # a new tail point whenever the head has moved a whole LED
        step = np.hypot(pos[:, 0] - self.eh[:, 0, 0], pos[:, 1] - self.eh[:, 0, 1]) >= 1.0
        if step.any():
            self.eh[step, 1:] = self.eh[step, :-1]
            self.eh[step, 0] = pos[step]
        # draw: head, then tail points and the midpoints between them, brightest last
        pts = np.concatenate([pos[:, None, :], self.eh], 1)               # (M, L+1, 2)
        mid = (pts[:, :-1] + pts[:, 1:]) * 0.5
        allp = np.empty((EU_M, 2 * EU_L + 1, 2), np.float32)
        allp[:, 0::2], allp[:, 1::2] = pts, mid
        k = np.arange(2 * EU_L + 1, dtype=np.float32)
        taper = (1 - k / (2 * EU_L + 1)) ** 1.7
        lvl = np.minimum(1.0, np.minimum(self.eage, self.elife - self.eage) / RAMP).clip(0, 1)
        lvl = lvl * min(1.0, (t - self.arrived) / 3.0)
        feel = self.efeel
        base = np.stack([np.interp(feel, EU_SPEEDS, EU_COLS[:, c]) for c in range(3)], 1)       # (M, 3)
        col = base[:, None, :] * (taper[None, :, None] * lvl[:, None, None])
        col[:, 0] = np.minimum(255, base * 0.78 + 70) * lvl[:, None]                             # the head glints
        xs = np.rint(allp[:, :, 0]).astype(np.int32)
        ys = np.rint(allp[:, :, 1]).astype(np.int32)
        ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
        order = slice(None, None, -1)                                    # oldest first
        xs, ys, ok, col = xs[:, order], ys[:, order], ok[:, order], col[:, order]
        xs, ys, ok = xs.T.ravel(), ys.T.ravel(), ok.T.ravel()
        col = col.transpose(1, 0, 2).reshape(-1, 3)
        xs, ys, col = xs[ok], ys[ok], col[ok]
        cur = img[ys, xs]
        img[ys, xs] = np.maximum(cur, col)

    # -------------------------------------------------------------- frame ---
    def __call__(self, t):
        self.last_frame = time.time()
        dt = 1 / 30 if self.last is None else max(0.0, min(0.2, t - self.last))
        self.last = t
        if self.key == "eu":
            return self._call_eu(t, dt)
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
        # gusts: every few seconds a light surges towards the gust speed and back, in step with the
        # lights born near it, so patches of the field rush and brighten - as hard as the real gusts.
        pulse = np.clip(np.sin(t * (2 * math.pi / GUST_EVERY) + self.phase), 0, None) ** 3
        boost = 1 + (g / np.maximum(s, 0.3) - 1) * pulse * 0.7
        self.x += u * boost * (K * dt)
        self.y += v * boost * (K * dt)
        self.age += dt
        out = (self.x < 0) | (self.x >= W) | (self.y < 0) | (self.y >= H)
        dead = out | (self.age > self.life)
        if dead.any():
            n = int(dead.sum())
            self.x[dead], self.y[dead] = self.rng.uniform(0, W, n), self.rng.uniform(0, H, n)
            self.age[dead], self.life[dead] = 0.0, self.rng.uniform(*LIFE, n)
            if f[3] is not None and out.any():
                # a light that blew off the picture comes back in where the wind blows in, already lit,
                # so the upwind side is as full as the rest
                dx, dy = f[3]
                px, py = self.x[out], self.y[out]
                with np.errstate(divide="ignore"):
                    tx = np.where(dx > 1e-3, px / dx, np.where(dx < -1e-3, (W - 1e-3 - px) / -dx, np.inf))
                    ty = np.where(dy > 1e-3, py / dy, np.where(dy < -1e-3, (H - 1e-3 - py) / -dy, np.inf))
                back = np.minimum(tx, ty)
                self.x[out] = np.clip(px - dx * back, 0, W - 1e-3)
                self.y[out] = np.clip(py - dy * back, 0, H - 1e-3)
                self.age[out] = RAMP
            self.phase[dead] = self._phase(self.x[dead], self.y[dead])
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


def frame_eu(t):
    return _frame("eu", t)


frame = frame_ch


def _thumb(key, direction, speeds):
    """A still for the app: the map with the wind drawn in as a typical, made-up westerly (no network, no saved
    data) - an illustration of the piece, not today's wind."""
    w = Wind(key, fetch=False)
    rng = np.random.default_rng(7)
    sp = [float(speeds[(i // NX + i % NX) % len(speeds)]) for i in range(NX * NY)]
    w._use({"speed": sp, "dir": [direction + float(rng.uniform(-18, 18)) for _ in sp], "gust": [v * 1.5 for v in sp]}, ease=False)
    img = None
    for i in range(240):
        img = w(i / 15.0)
    return img


def thumb_ch():
    return _thumb("ch", 250.0, (4, 7, 11, 6, 9))


def thumb_ie():
    return _thumb("ie", 245.0, (9, 13, 17, 11, 15))


def thumb_eu():
    """A still for the app: a made-up Atlantic depression (counter-clockwise, west of Scotland) with a high
    over Iberia and a westerly stream between - an illustration, not today's wind."""
    w = Wind("eu", fetch=False)
    sp, di = [], []
    for lat, lon in zip(w.lats, w.lons):
        ue, vn = 9.0, 2.0                                         # a steady westerly
        for (cl, co, rad, vmax, sign) in ((58.0, -17.0, 650.0, 22.0, 1), (44.0, -9.0, 800.0, 9.0, -1),
                                          (63.0, 4.0, 500.0, 12.0, 1)):
            dx = (lon - co) * 111.32 * w.coslat
            dy = (lat - cl) * 111.32
            r = math.hypot(dx, dy) + 1e-6
            vt = sign * vmax * (r / rad) * math.exp(0.5 * (1 - (r / rad) ** 2))   # Rankine-ish vortex
            ue += -vt * dy / r                                    # counter-clockwise for sign=+1
            vn += vt * dx / r
        sp.append(math.hypot(ue, vn))
        di.append(math.degrees(math.atan2(-ue, -vn)) % 360)
    w._use({"speed": sp, "dir": di, "gust": [v * 1.4 for v in sp]}, ease=False)
    img = None
    for i in range(300):
        img = w(i / 15.0)
    return img
