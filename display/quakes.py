"""Earthquakes: the Earth as a slowly turning globe of dots - every land LED a dot of light, the oceans
dark - tilted like a desk globe so both hemispheres read, turning once every four minutes, with the
real day and night on it (the night side's land sinks to a deep blue). Every earthquake of the last 24
hours (USGS, magnitude 2.5 and up, free, no key) sits on it as one LED where it happened: shallow ones
amber, intermediate rose, the deep ones under the trenches violet; the strong ones as a small cross. A
quake sends rings rippling out across the globe's surface, sized by its magnitude - a M2.5 a ring of a
few LEDs, a M6 one that reaches a fifth of the way round - echoing every few minutes and dying away over
hours, so the restless places (Vanuatu, the Philippines, the Reykjanes Ridge ...) keep breathing on the
globe. A quake of M5 or more puts its place and magnitude quietly at the bottom for three hours, and its
LED slowly blinks while it is named.

Everything is drawn on whole LEDs (no anti-aliasing). The globe is a fixed grid of dots on the wall,
one LED in every two by two, each showing whatever part of the Earth is under it right now; the land
comes from assets/maps/land_mask.png (Natural Earth 1:50m, from tools/build_land.py).

The feed is fetched every 3 minutes on a side thread while the piece is running (USGS regenerates it
every minute and asks clients not to poll faster than that; we send If-Modified-Since), and kept in
panel_setup/quakes_cache.json, so a restart or a day offline still shows the last day that was seen.
"""
import json
import math
import os
import re
import threading
import time
import unicodedata

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASK = os.path.join(ROOT, "assets", "maps", "land_mask.png")
CACHE = os.path.join(ROOT, "panel_setup", "quakes_cache.json")
URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
EVERY = 180.0                                  # seconds between fetches (the feed changes once a minute)
RETRY = (60.0, 900.0)                          # after a failure: 1 min, doubling to 15 min
IDLE = 60.0                                    # no frame for this long: the piece is off, stop fetching
DAY = 86400.0

CX, CY, R = (W - 1) / 2.0, 106.0, 92.0         # the globe on the wall (LEDs); the text sits under it
PITCH = 2                                      # one dot in every PITCH x PITCH LEDs
TURN = 240.0                                   # seconds per turn
VIEW_LAT = math.radians(18.0)                  # we look down on it a little from the north ...
ROLL = math.radians(-20.0)                     # ... and its axis leans, like a desk globe
TEXT_Y = 222

# colours (the wall shows nothing below ~94 in a channel and only ~5 steps above it: 94 149 188 219 245)
LAND_DAY = np.array([120, 225, 160], np.float32)   # sunlit land: a pale mint
LAND_NIGHT = np.array([30, 100, 205], np.float32)  # the night side: deep blue
RIM = np.array([20, 40, 100], np.float32)       # the edge of the globe, faintly, so the oceans have a shore
SHALLOW = np.array([255, 165, 40], np.float32)  # < 70 km
MIDDLE = np.array([255, 50, 120], np.float32)   # 70 - 300 km
DEEP = np.array([180, 60, 255], np.float32)    # > 300 km
TEXT = np.array([200, 200, 190], np.float32)

SAMPLE = [  # a still for the app when there is no cache yet: a few real quakes of a day in October 2026
    ("s1", 0.5, -15.3, 166.3, 10, 6.0, "214 km NW of Port-Olry, Vanuatu"),
    ("s2", 1.0, -15.4, 166.4, 10, 5.5, "221 km NW of Port-Olry, Vanuatu"),
    ("s3", 2.0, 57.0, -33.5, 10, 5.5, "Reykjanes Ridge"),
    ("s4", 3.0, 6.4, 125.5, 46, 5.2, "6 km NW of Balangonan, Philippines"),
    ("s5", 5.0, -21.5, -178.0, 509, 5.0, "south of the Fiji Islands"),
    ("s6", 6.0, 12.7, 143.9, 101, 5.4, "193 km WSW of Merizo Village, Guam"),
    ("s7", 7.0, 34.3, 93.9, 10, 5.4, "210 km ENE of Nagqu, China"),
    ("s8", 9.0, -30.9, -69.1, 186, 4.7, "39 km SSW of Serrezuela, Argentina"),
    ("s9", 11.0, 60.4, -151.0, 70, 3.0, "25 km ESE of Kasilof, Alaska"),
    ("s10", 13.0, 39.3, -122.9, 10, 4.0, "10 km N of Lake Pillsbury, CA"),
    ("s11", 15.0, 19.4, -155.4, 0, 2.6, "24 km WNW of Volcano, Hawaii"),
    ("s12", 17.0, -18.0, -173.5, 10, 4.9, "88 km SE of Hihifo, Tonga"),
]


def dim(c, f):
    """c * f, but a channel that was lit stays at the wall's dimmest visible step (so a dimmed amber stays
    amber, instead of falling to red when its green drops out)."""
    c = np.asarray(c, np.float32)
    return np.where(c >= 94, np.maximum(c * f, 100.0), 0.0).astype(np.float32)


def depth_colour(d):
    return SHALLOW if d < 70 else MIDDLE if d < 300 else DEEP


def short_place(place):
    """'214 km NW of Port-Olry, Vanuatu' -> 'PORT-OLRY VANUATU', in letters the 3x5 font has."""
    p = re.sub(r"^\s*\d+(\.\d+)?\s*km\s+[NSEW]{1,3}\s+of\s+", "", place or "")
    p = unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode().upper()
    p = re.sub(r"[^A-Z0-9 .-]", " ", p)
    return re.sub(r"\s+", " ", p).strip()


def ripple(mag):
    """(largest ring in degrees of arc, seconds one ripple takes, seconds between echoes, life in s)."""
    m = max(2.5, min(8.0, mag))
    return (min(40.0, 2.2 * 1.8 ** (m - 2.5)), 22.0 + 26.0 * (m - 2.5), 150.0 + 30.0 * (m - 2.5),
            3600.0 * (1.0 + (m - 2.5)))


def sun_vector(now):
    """The point the sun is overhead, as a unit vector (low-precision almanac, good to a degree)."""
    d = now / DAY - 10957.5                                 # days since J2000
    g = math.radians(357.529 + 0.98560028 * d)
    q = 280.459 + 0.98564736 * d
    L = math.radians(q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    e = math.radians(23.439 - 0.00000036 * d)
    dec = math.asin(math.sin(e) * math.sin(L))
    ra = math.degrees(math.atan2(math.cos(e) * math.sin(L), math.cos(L)))
    gmst = (280.46061837 + 360.98564736629 * d) % 360.0
    lon = math.radians(((ra - gmst + 180.0) % 360.0) - 180.0)
    return np.array([math.cos(dec) * math.cos(lon), math.cos(dec) * math.sin(lon), math.sin(dec)])


def unit(lat, lon):
    lat, lon = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1)


class Globe:
    def __init__(self, fetch=True):
        from display import pixelfont
        self.font = pixelfont
        try:
            self.mask = np.asarray(Image.open(MASK).convert("L")) > 127
        except Exception:
            self.mask = np.zeros((360, 720), bool)
        self.mh, self.mw = self.mask.shape
        # the dot grid: for each dot, where on the Earth it looks, before the turn (longitude relative
        # to the middle of the view)
        ys, xs = np.mgrid[0:H:PITCH, 0:W:PITCH]
        ys, xs = ys.ravel() + 1, xs.ravel()                  # odd rows, even columns: centred on CX
        su, sv = (xs - CX) / R, (CY - ys) / R
        u = su * math.cos(ROLL) - sv * math.sin(ROLL)        # undo the lean
        v = su * math.sin(ROLL) + sv * math.cos(ROLL)
        r2 = u * u + v * v
        keep = r2 < 1.0
        self.gx, self.gy = xs[keep], ys[keep]
        u, v = u[keep], v[keep]
        z = np.sqrt(1.0 - r2[keep])
        sp, cp = math.sin(VIEW_LAT), math.cos(VIEW_LAT)
        self.glat = np.arcsin(np.clip(v * cp + z * sp, -1, 1))
        self.gdlon = np.arctan2(u, z * cp - v * sp)
        self.mu = z                                          # facing us: 1, at the edge: 0
        self.gview = np.stack([u, v, z], 1)                  # each dot's point in the view's own axes
        self.row = np.clip(((math.pi / 2 - self.glat) / math.pi * self.mh).astype(np.int32), 0, self.mh - 1)
        self.limb = (0.62 + 0.38 * np.sqrt(self.mu)).astype(np.float32)[:, None]
        self.rim = self.mu < 0.16                            # the outermost dots
        self.quakes, self.seen, self.generated, self.fetched = [], {}, None, 0.0
        self.last_mod = None
        self._load_cache()
        self.last_frame = time.time()
        self.thread = None
        if fetch:
            self.thread = threading.Thread(target=self._fetch_loop, daemon=True)
            self.thread.start()

    # ---- data ------------------------------------------------------------------------------------
    def _load_cache(self):
        try:
            with open(CACHE) as fh:
                c = json.load(fh)
            self.seen = {k: float(v) for k, v in c.get("seen", {}).items()}
            self.fetched = float(c.get("fetched", 0.0))
            self.last_mod = c.get("last_modified")
            self._set(c.get("quakes", []))
        except Exception:
            pass

    def _save_cache(self, raw):
        try:
            tmp = CACHE + ".tmp"
            with open(tmp, "w") as fh:
                json.dump({"fetched": self.fetched, "last_modified": self.last_mod, "quakes": raw,
                           "seen": self.seen}, fh)
            os.replace(tmp, CACHE)
        except Exception as e:
            print(f"[quakes] cache: {str(e)[:80]}", flush=True)

    def _set(self, raw):
        """raw: [[id, unix time, lat, lon, depth km, mag, place], ...] -> the drawable list."""
        out = []
        for q in raw:
            try:
                qid, t, lat, lon, depth, mag, place = q
                t, mag, depth = float(t), float(mag), float(depth or 0)
            except Exception:
                continue
            seen = self.seen.get(qid, t)
            start = seen if 0 < seen - t < 3600 else t      # reported late: its ripple starts when it arrives
            rho, dur, per, life = ripple(mag)
            out.append({"id": qid, "t": t, "start": start, "mag": mag, "depth": depth,
                        "place": short_place(place), "v": unit(lat, lon), "col": depth_colour(depth),
                        "rho": math.radians(rho), "dur": dur, "per": per, "life": life})
        self.quakes = sorted(out, key=lambda q: q["mag"])   # the strongest drawn last, on top

    def _fetch_loop(self):
        import requests
        wait = 0.0
        while True:
            now = time.time()
            if now - self.last_frame > IDLE or now - self.fetched < max(EVERY, wait):
                time.sleep(5.0)
                continue
            try:
                hdr = {"User-Agent": "fortuna-wall/1.0 (private art project)"}
                if self.last_mod and self.quakes:
                    hdr["If-Modified-Since"] = self.last_mod
                r = requests.get(URL, headers=hdr, timeout=20)
                if r.status_code == 304:
                    self.fetched, wait = now, 0.0
                    continue
                r.raise_for_status()
                feats = r.json()["features"]
                first = not self.seen and not self.quakes    # first ever: nothing counts as new
                raw = []
                for f in feats:
                    p, c = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or []
                    if p.get("mag") is None or len(c) < 2 or p.get("type", "earthquake") != "earthquake":
                        continue
                    qid, t = f.get("id") or p.get("code"), p["time"] / 1000.0
                    if qid not in self.seen:
                        self.seen[qid] = t if first else now
                    raw.append([qid, t, c[1], c[0], c[2] if len(c) > 2 else 0.0, p["mag"], p.get("place") or ""])
                self.seen = {k: v for k, v in self.seen.items() if now - v < DAY + 7200}
                self.fetched, self.last_mod, wait = now, r.headers.get("Last-Modified"), 0.0
                self._set(raw)
                self._save_cache(raw)
            except Exception as e:
                self.fetched = now
                wait = min(RETRY[1], max(RETRY[0], wait * 2))
                print(f"[quakes] {str(e)[:100]}", flush=True)

    # ---- drawing ---------------------------------------------------------------------------------
    def _basis(self, lam0):
        """Earth vectors -> screen: rows are the view's right, up and towards-us axes."""
        sp, cp, sl, cl = math.sin(VIEW_LAT), math.cos(VIEW_LAT), math.sin(lam0), math.cos(lam0)
        right = np.array([-sl, cl, 0.0])
        up = np.array([-sp * cl, -sp * sl, cp])
        out = np.array([cp * cl, cp * sl, sp])
        return np.stack([right, up, out])

    def _project(self, M, v):
        p = v @ M.T
        u, w = p[..., 0], p[..., 1]
        sx = CX + R * (u * math.cos(ROLL) + w * math.sin(ROLL))
        sy = CY - R * (-u * math.sin(ROLL) + w * math.cos(ROLL))
        return np.rint(sx).astype(np.int32), np.rint(sy).astype(np.int32), p[..., 2]

    def render(self, now, spin=None, sun=None):
        """The globe at time now; spin (seconds) sets the turn and sun (a unit vector) the light, when
        they are not now's own."""
        lam0 = -2 * math.pi * (((now if spin is None else spin) / TURN) % 1.0) + math.pi   # west to east
        img = np.zeros((H, W, 3), np.float32)
        # the land, lit by the real sun
        lon = self.gdlon + lam0
        col = ((lon / (2 * math.pi) + 0.5) % 1.0 * self.mw).astype(np.int32) % self.mw
        land = self.mask[self.row, col]
        M = self._basis(lam0)
        cos_sun = self.gview @ (M @ (sun_vector(now) if sun is None else sun))
        day = np.clip((cos_sun + 0.08) / 0.16, 0.0, 1.0)[:, None]  # a soft twilight band
        c = (LAND_NIGHT + (LAND_DAY - LAND_NIGHT) * day) * self.limb
        rim = self.rim & ~land
        img[self.gy[land], self.gx[land]] = c[land]
        img[self.gy[rim], self.gx[rim]] = RIM
        if not self.quakes:
            return img
        # the rings: each quake echoes every few minutes, weaker as it ages, gone after its life
        for q in self.quakes:
            age = now - q["start"]
            if age < 0 or age > q["life"]:
                continue
            ph = (age % q["per"]) / q["dur"]
            if ph >= 1.0:
                continue
            strength = (1.0 - age / q["life"]) * (1.0 - ph) ** 0.8
            rho = q["rho"] * (1.0 - (1.0 - ph) ** 2)                # fast at first, settling
            n = max(10, int(2 * math.pi * math.sin(rho) * R * 1.4))
            th = np.linspace(0, 2 * math.pi, n, endpoint=False)
            cv = q["v"]
            e1 = np.cross(cv, [0.0, 0.0, 1.0])
            e1 = e1 / (np.linalg.norm(e1) + 1e-9) if np.linalg.norm(e1) > 1e-6 else np.array([1.0, 0, 0])
            e2 = np.cross(cv, e1)
            pts = (math.cos(rho) * cv + math.sin(rho) * (np.cos(th)[:, None] * e1 + np.sin(th)[:, None] * e2))
            if strength < 0.5:                                      # fading: the ring breaks into dots
                keep = ((np.arange(n) * 0.6180339) % 1.0) < strength * 2.0
                pts = pts[keep]
                if not len(pts):
                    continue
            x, y, z = self._project(M, pts)
            ok = (z > 0.05) & (x >= 0) & (x < W) & (y >= 0) & (y < H)
            c = dim(q["col"], 0.5 + 0.5 * min(1.0, strength * 2.0))
            img[y[ok], x[ok]] = np.maximum(img[y[ok], x[ok]], c)
        # the quakes themselves
        V = np.array([q["v"] for q in self.quakes])
        x, y, z = self._project(M, V)
        named = self.named(now)
        blink = 0.5 + 0.5 * math.cos(now * 2.4)
        for q, qx, qy, qz in zip(self.quakes, x, y, z):
            if qz < 0.03 or not (1 <= qx < W - 1 and 1 <= qy < H - 1):
                continue
            age = now - q["t"]
            if age > DAY + 1800:
                continue
            lvl = 1.0 - 0.35 * min(1.0, max(0.0, age / DAY))
            if named is q:
                lvl = 0.6 + 0.4 * blink
            c = dim(q["col"], lvl)
            if q["mag"] >= 4.5:
                arm = dim(c, 0.8 if q["mag"] >= 5.5 else 0.62)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    img[qy + dy, qx + dx] = np.maximum(img[qy + dy, qx + dx], arm)
            img[qy, qx] = c
        if named is not None:
            self._label(img, named)
        return img

    def named(self, now):
        """The M5+ quake whose name is showing: of those in their first three hours, one strongest per
        place, newest first, each for twelve seconds in turn."""
        recent = [q for q in self.quakes if q["mag"] >= 5.0 and 0 <= now - q["start"] < 3 * 3600]
        if not recent:
            return None
        best = {}
        for q in recent:
            k = q["place"]
            if k not in best or q["mag"] > best[k]["mag"]:
                best[k] = q
        lst = sorted(best.values(), key=lambda q: -q["start"])
        return lst[int(now // 12.0) % len(lst)]

    def _label(self, img, q):
        mag = f"M{q['mag']:.1f}"
        place = q["place"]
        maxc = (W + 1) // 4 - len(mag) - 1
        if len(place) > maxc:
            place = place[:maxc].rsplit(" ", 1)[0]
        w = self.font.width(mag + " " + place) if place else self.font.width(mag)
        x0 = int((W - w) // 2)
        self.font.draw(img, mag, x0, TEXT_Y, q["col"])
        if place:
            self.font.draw(img, place, x0 + self.font.width(mag) + 4, TEXT_Y, TEXT * 0.82)

    def __call__(self, t):
        self.last_frame = now = time.time()
        img = self.render(now)
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


_globe = None


def thumb():
    """A still for the app, from the cache (or a built-in day of quakes): no network."""
    g = Globe(fetch=False)
    now = time.time()
    if not g.quakes:
        g.seen = {}
        g._set([[i, now - h * 3600.0, la, lo, d, m, p] for i, h, la, lo, d, m, p in SAMPLE])
    elif now - g.fetched > DAY:
        now = g.fetched                                   # an old cache: show it as it was then
    big = max(g.quakes, key=lambda q: q["mag"] if now - q["t"] < DAY else 0)
    lon = math.atan2(big["v"][1], big["v"][0])
    spin = ((math.pi - lon) / (2 * math.pi)) % 1.0 * TURN    # turned so the strongest faces us
    img = g.render(now, spin, sun=unit(15.0, math.degrees(lon) - 35.0))   # and lit, morning on its left
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def frame(t):
    global _globe
    if _globe is None:
        _globe = Globe()
    return _globe(t)
