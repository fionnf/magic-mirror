"""Polar bears of Svalbard: recorded satellite-collar tracks of polar bears, one lit LED per bear with a
long fading trail and the bear's own number beside it, over a dim map of Svalbard and the Fram Strait,
with the sea ice of the day underneath.

THIS IS A REPLAY, NOT LIVE. The Norwegian Polar Institute does not publish live bear positions. The
tracks are real, recorded in 2012 (7 April to 30 November) on female bears in Svalbard, and the wall says
so (the month of the replay is in the corner; the app's description says it is a replay). Time is compressed: the 237 days
play in about 28 minutes (6.5 s a day), then the replay starts again. All bears run on one shared clock,
so many are visible at once. Each bear's number is its individual id in the NPI data, drawn with display/pixelfont.py beside its spot.

Data: assets/migrations/polarbears.json, built by tools/build_polarbears.py from the NPI dataset
"Tracking data from polar bears (N=67, 2002-2004 & 2010-2013) and ringed seals" (Hamilton, Kovacs, Ims,
Aars & Lydersen 2017, J. Anim. Ecol. 86: 1054-1064; doi 10.21334/npolar.2017.132248b4), published by the
Norwegian Polar Institute under CC BY 4.0. That file holds the fixes taken near the coast, thinned here
to one fix a day. Coastline: Natural Earth (public domain).

The sea ice is the NOW of the piece, a different thing from the 2012 bears: the newest daily concentration
map of NSIDC's Sea Ice Index (v4.0, 25 km polar stereographic GeoTIFF), shaded pale blue by how much of
each cell is ice, with its date on the wall ("ICE 17 OCT"). It is fetched on a side thread at most once a
day, kept as a small Svalbard window in panel_setup/ice_cache.json, and offline the piece shows the ice
of the day bundled in the data file. Cite: Fetterer, F., K. Knowles, W. N. Meier, M. Savoie, and A. K.
Windnagel. 2017, updated daily. Sea Ice Index, Version 4. Boulder, Colorado USA. NSIDC: National Snow
and Ice Data Center. doi:10.7265/N5K072F8. (Free to use with this citation.)

Everything is drawn on whole LEDs, no anti-aliasing.
"""
import json
import math
import os
import re
import threading
import time

import numpy as np
from PIL import Image

import config
from display import pixelfont

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "migrations", "polarbears.json")
CACHE = os.path.join(ROOT, "panel_setup", "ice_cache.json")

# ---- the view: polar stereographic with Svalbard's meridian (20 E) pointing straight up the wall
CENTRE = (78.5, 19.0)          # lat, lon of the middle of the picture
LON0 = 20.0
KM = 2.5                       # km per LED
SEC_PER_DAY = 6.5              # the replay: one day of the bears per 6.5 s
HOLD = 20.0                    # seconds of rest at the end before it starts over
TRAIL_DAYS = 30.0              # how far back a trail reaches
TAU = 10.0                     # days for a trail to fall to 1/e
STEP = 0.025                    # days between trail samples
GAP = 3.0                      # days without a fix before a bear is taken as off the record

# ---- NSIDC north grid (EPSG:3413): 304 x 448 cells of 25 km, upper-left corner (-3850000, 5850000)
NS_X0, NS_Y0, NS_CELL, NS_LON0 = -3850000.0, 5850000.0, 25000.0, -45.0
ICE_BASE = "https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/geotiff/"
ICE_EVERY = 24 * 3600.0
IDLE = 120.0

# palette: deep colours, every lit channel well above the LEDs' dark floor
SEA_TOP, SEA_BOT = (7, 18, 30), (2, 5, 12)               # polar-night sea, a teal-violet glow high up
LAND_LO, LAND_HI = (15, 20, 33), (27, 35, 54)            # coastal lowland ... inland relief
COAST, COAST_OUT = (46, 70, 112), (7, 12, 24)          # the hairline and its glow offshore
ICE_LO, ICE_MID, ICE_HI = (18, 44, 86), (58, 108, 164), (170, 206, 234)   # 15 % ... 100 % ice
ICE_RIM = (22, 34, 38)                                   # the lit edge / glints
MIN_FLOE = 400                                           # LEDs: smaller ice patches are 25 km cell noise
AUR_ROWS, AUR_AMP = 96, 0.55
AUR_G, AUR_V = (8, 44, 36), (30, 16, 52)
MONTH_COL, DIM_COL, FAINT_COL, RULE_COL = (168, 186, 232), (96, 110, 162), (62, 72, 110), (54, 62, 100)
TL_FUT, TL_PAST, TL_TICK, TL_INI, TL_NOW = (30, 36, 62), (120, 146, 206), (54, 62, 100), (58, 66, 104), (168, 186, 232)

_E = 0.0818191908426           # WGS84 eccentricity


def project(lat, lon, lon0=LON0):
    """Latitude/longitude (degrees) -> polar stereographic metres, true scale at 70 N, lon0 straight down
    from the pole (so north is up the wall). Vectorised."""
    lat, lon = np.radians(np.asarray(lat, np.float64)), np.radians(np.asarray(lon, np.float64) - lon0)

    def t(p):
        s = _E * np.sin(p)
        return np.tan(np.pi / 4 - p / 2) / ((1 - s) / (1 + s)) ** (_E / 2)
    pc = math.radians(70.0)
    mc = math.cos(pc) / math.sqrt(1 - (_E * math.sin(pc)) ** 2)
    rho = 6378137.0 * mc * t(lat) / float(t(pc))
    return rho * np.sin(lon), -rho * np.cos(lon)


_XC, _YC = (float(v) for v in project(*CENTRE))


def to_px(lat, lon):
    """Latitude/longitude -> (x, y) in LEDs on the wall, float."""
    x, y = project(lat, lon)
    return (x - _XC) / (KM * 1000) + W / 2, -(y - _YC) / (KM * 1000) + H / 2


# ------------------------------------------------------------------- the sea ice ---
def _ice_geometry():
    """For every LED: where it falls on the NSIDC grid (as float row/col of cell centres)."""
    gx, gy = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    x = (gx - W / 2) * KM * 1000 + _XC
    y = -(gy - H / 2) * KM * 1000 + _YC
    d = math.radians(LON0 - NS_LON0)                      # the same projection, turned by 65 degrees
    x2 = x * math.cos(d) - y * math.sin(d)
    y2 = y * math.cos(d) + x * math.sin(d)
    return (NS_Y0 - y2) / NS_CELL - 0.5, (x2 - NS_X0) / NS_CELL - 0.5


_GEO = None


def ice_window():
    """(r0, c0, rows, cols) of the part of the NSIDC grid the picture covers."""
    global _GEO
    if _GEO is None:
        _GEO = _ice_geometry()
    r, c = _GEO
    r0, r1 = int(math.floor(r.min())) - 1, int(math.ceil(r.max())) + 1
    c0, c1 = int(math.floor(c.min())) - 1, int(math.ceil(c.max())) + 1
    return r0, c0, r1 - r0 + 1, c1 - c0 + 1


def decode_ice(tif_bytes):
    """An NSIDC daily concentration GeoTIFF (uint16: 0-1000 = tenths of a percent; 2510 pole hole, 2520
    unused, 2530 coast, 2540 land, 2550 missing) -> {'r0','c0','cells'}: the Svalbard window as whole
    percents, -1 where there is no ice reading. PIL only."""
    import io
    a = np.array(Image.open(io.BytesIO(tif_bytes)))
    if a.shape != (448, 304):
        raise ValueError(f"unexpected ice grid {a.shape}")
    r0, c0, nr, nc = ice_window()
    win = a[r0:r0 + nr, c0:c0 + nc].astype(np.int32)
    pct = np.where(win <= 1000, np.rint(win / 10.0), -1).astype(int)
    return {"r0": r0, "c0": c0, "cells": pct.tolist()}


def _http_get(url, timeout=40):
    import requests
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "fortuna-wall/1.0 (art project)"})
    r.raise_for_status()
    return r.content


def fetch_ice(today=None):
    """The newest NSIDC daily map there is -> {'date': 'YYYYMMDD', 'r0', 'c0', 'cells'}. The directory
    listing of the month names the files; the last days are often not there yet, so it takes the newest
    listed (this month, else last month)."""
    today = today or time.time()
    err = None
    for back in (0, 31):
        tm = time.gmtime(today - back * 86400)
        folder = f"{tm.tm_year}/{tm.tm_mon:02d}_{time.strftime('%b', tm)}/"
        try:
            names = sorted(set(re.findall(r"N_(\d{8})_concentration_v4\.0\.tif", _http_get(ICE_BASE + folder).decode("utf8", "replace"))))
        except Exception as e:
            err = e
            continue
        for date in reversed(names[-5:]):                          # fall back day by day
            try:
                rec = decode_ice(_http_get(f"{ICE_BASE}{folder}N_{date}_concentration_v4.0.tif", 90))
                rec["date"] = date
                return rec
            except Exception as e:
                err = e
    raise RuntimeError(f"no NSIDC ice map: {str(err)[:80]}")


_lock = threading.Lock()


def _read_cache():
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_cache(rec):
    tmp = CACHE + ".tmp"
    try:
        with _lock, open(tmp, "w") as fh:
            json.dump(rec, fh, separators=(",", ":"))
            fh.flush()
        os.replace(tmp, CACHE)
    except Exception as e:
        print(f"[polarbears] cache: {str(e)[:80]}", flush=True)


def _ice_ok(rec):
    try:
        r0, c0, nr, nc = ice_window()
        return rec["r0"] == r0 and rec["c0"] == c0 and len(rec["cells"]) == nr and len(rec["cells"][0]) == nc and len(rec["date"]) == 8
    except Exception:
        return False


def ice_concentration(rec):
    """A window record -> 0..1 ice concentration for every LED (bilinear between the 25 km cells; cells
    without a reading, such as land, do not pull the edge down)."""
    global _GEO
    if _GEO is None:
        _GEO = _ice_geometry()
    r, c = _GEO
    cells = np.array(rec["cells"], np.float32)
    ok = (cells >= 0).astype(np.float32)
    val = np.where(cells >= 0, cells, 0.0) / 100.0
    r = r - rec["r0"]
    c = c - rec["c0"]
    r0 = np.clip(np.floor(r).astype(int), 0, cells.shape[0] - 2)
    c0 = np.clip(np.floor(c).astype(int), 0, cells.shape[1] - 2)
    fr, fc = np.clip(r - r0, 0, 1), np.clip(c - c0, 0, 1)
    num = den = 0.0
    for dr, dc, w in ((0, 0, (1 - fr) * (1 - fc)), (0, 1, (1 - fr) * fc), (1, 0, fr * (1 - fc)), (1, 1, fr * fc)):
        wk = w * ok[r0 + dr, c0 + dc]
        num = num + wk * val[r0 + dr, c0 + dc]
        den = den + wk
    return np.where(den > 0.05, num / np.maximum(den, 1e-6), 0.0).astype(np.float32)


# --------------------------------------------------------------------- the piece ---
def _hsv(h, s, v):
    import colorsys
    return tuple(int(round(255 * x)) for x in colorsys.hsv_to_rgb((h % 360) / 360.0, s, v))


def _smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


_BAYER = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                   [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                   [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], np.float32)
_BAYER = np.tile((_BAYER + 0.5) / 64.0, (H // 8 + 1, W // 8 + 1))[:H, :W, None]

# the soft halo around a head: whole LEDs at graded levels (centre 1, the four neighbours about half, ...)
_HALO = np.array([[0.00, 0.06, 0.10, 0.06, 0.00],
                  [0.06, 0.22, 0.36, 0.22, 0.06],
                  [0.10, 0.36, 1.00, 0.36, 0.10],
                  [0.06, 0.22, 0.36, 0.22, 0.06],
                  [0.00, 0.06, 0.10, 0.06, 0.00]], np.float32)

# where a label may sit relative to its bear: (dx, dy of the label's top-left, leader start, leader end)
_SLOTS = (("R", 6, -2), ("L", -6, -2), ("UR", 5, -10), ("DR", 5, 6), ("UL", -5, -10), ("DL", -5, 6))

FADE_IN = 2.5                  # seconds of fade up at the start of every loop (and of the piece)
FADE_OUT = 3.0                 # seconds of fade down at the end of the rest
N_LABELS = 6                   # only the bears nearest the middle of the picture wear their number
TAIL_DAYS = 27.0               # a comet tail's reach, tapering smoothly to nothing


def _noise(seed, sigma):
    rng = np.random.RandomState(seed)
    import cv2
    n = cv2.GaussianBlur(rng.randn(H, W).astype(np.float32), (0, 0), sigma)
    return n / (np.abs(n).max() + 1e-6)


class Bears:
    def __init__(self, fetch=True):
        import cv2
        self.cv2 = cv2
        with open(DATA) as fh:
            d = json.load(fh)
        self.meta = d
        self.bears = []
        starts, ends = [], []
        for b in d["bears"]:
            tr = np.array(b["tracks"], np.float64)
            if len(tr) < 2:
                continue
            tr = tr[np.argsort(tr[:, 0])]
            px, py = to_px(tr[:, 1], tr[:, 2])
            self.bears.append({"id": str(b["id"]), "t": tr[:, 0], "x": px, "y": py})
            starts.append(tr[0, 0])
            ends.append(tr[-1, 0])
        self.t0, self.t1 = float(min(starts)), float(max(ends))
        self.days = (self.t1 - self.t0) / 86400.0
        self.cycle = self.days * SEC_PER_DAY + HOLD
        n = len(self.bears)
        order = sorted(range(n), key=lambda i: self.bears[i]["id"])
        for rank, i in enumerate(order):
            # one family of hues, rose through coral and amber to gold: warm against the cool ice, never a rainbow
            hue = -22 + 84.0 * ((rank * 0.618034) % 1.0)
            c = np.array(_hsv(hue, 0.74, 1.0), np.float32)
            self.bears[i]["col"] = c
            self.bears[i]["core"] = c + (255.0 - c) * 0.50
        self.land = self._land_mask()
        self.ice_rec = None
        self.ice_t = 0.0
        self.base = None
        self.last_frame = time.time()
        self.first_t = None
        self.lab_alpha, self.lab_slot = {}, {}
        self.lab_t = None
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.ph = (_noise(5, 6.0) * 1.6 + xx * 0.045 + yy * 0.035).astype(np.float32)
        self.ph2 = (_noise(9, 4.0) * 2.5 + xx * 0.06 - yy * 0.045).astype(np.float32)
        rec = _read_cache()
        if _ice_ok(rec):
            self.ice_rec, self.ice_t = rec, float(rec.get("t", 0.0))
        elif _ice_ok(d.get("ice") or {}):
            self.ice_rec = d["ice"]                                # offline: the ice bundled with the data
        self.rebuild_base()
        if fetch:
            threading.Thread(target=self._fetch_loop, daemon=True).start()

    # ---- the map
    def _land_mask(self):
        cv2 = self.cv2
        m = np.zeros((H, W), np.uint8)
        self.coast = []
        for ring in self.meta.get("land", []):
            xs, ys = to_px([p[0] for p in ring], [p[1] for p in ring])
            pts = np.stack([np.rint(xs), np.rint(ys)], 1).astype(np.int32)
            self.coast.append(pts)
            cv2.fillPoly(m, [pts], 1)
        return m.astype(bool)

    def rebuild_base(self):
        """Everything that does not move: night sea, land relief, the coast's hairline glow, the ice field.
        Built as float RGB; the ice is kept as a separate additive layer so it can shimmer."""
        cv2 = self.cv2
        land = self.land
        v = (self.yy / (H - 1)).astype(np.float32)
        top, bot = np.array(SEA_TOP, np.float32), np.array(SEA_BOT, np.float32)
        t = _smooth(v, 0.0, 0.85)[..., None]
        sea = top * (1 - t) + bot * t                               # polar night: a faint teal-violet glow high up

        # land: a soft relief. Distance from the coast lifts the inland, smooth noise adds ridges, and a light
        # from the north-west shades them. Always a quiet, dark slate so the bears stay the brightest thing.
        din = cv2.distanceTransform(land.astype(np.uint8), cv2.DIST_L2, 3)
        h = 0.9 * (1 - np.exp(-din / 7.0)) + 0.5 * _noise(3, 3.5) + 0.25 * _noise(4, 1.8)
        h = cv2.GaussianBlur(h.astype(np.float32), (0, 0), 0.8)
        gy, gx = np.gradient(h)
        shade = np.clip(-(gx + gy) * 4.0, -1, 1)
        lo, hi = np.array(LAND_LO, np.float32), np.array(LAND_HI, np.float32)
        f = np.clip(0.35 + 0.65 * (1 - np.exp(-din / 9.0)), 0, 1)[..., None]
        ld = lo + (hi - lo) * f
        ld = ld * (1.0 + 0.28 * shade[..., None]) + np.array((2, 3, 6), np.float32) * shade[..., None]
        img = np.where(land[..., None], ld, sea).astype(np.float32)

        # the ice: only ice that is part of a real field (no stray 25 km cells), softly feathered
        self.ice_add = None
        self.ice_idx = None
        if self.ice_rec is not None:
            c = ice_concentration(self.ice_rec)
            dist = cv2.distanceTransform((~land).astype(np.uint8), cv2.DIST_L2, 3)
            c = c * _smooth(dist, 5.0, 10.0)                        # the 25 km cells bleed off the land: keep off the coast
            n, lab, stats, _ = cv2.connectedComponentsWithStats((c >= 0.15).astype(np.uint8), connectivity=8)
            keep = np.zeros(n, bool)
            keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= MIN_FLOE
            c = np.where(keep[lab], c, 0.0).astype(np.float32)
            c = cv2.GaussianBlur(c, (0, 0), 1.3)
            a = _smooth(c, 0.10, 0.34)
            a[land] = 0.0
            # colour by concentration: deep blue, then pale blue, then near white
            cc = np.clip((c - 0.15) / 0.85, 0, 1)[..., None]
            c0, c1, c2 = (np.array(x, np.float32) for x in (ICE_LO, ICE_MID, ICE_HI))
            col = np.where(cc < 0.5, c0 + (c1 - c0) * (cc / 0.5), c1 + (c2 - c1) * ((cc - 0.5) / 0.5))
            rim = np.exp(-((c - 0.22) / 0.07) ** 2)[..., None] * a[..., None]       # the lit edge of the field
            col = col + rim * np.array(ICE_RIM, np.float32)
            add = (col - img) * a[..., None]
            idx = np.nonzero(a > 0.01)
            self.ice_idx = idx
            self.ice_add = add[idx].astype(np.float32)
            self.ice_a = a[idx].astype(np.float32)
            d = self.ice_rec["date"]
            self.ice_label = f"ICE {int(d[6:8])} {_MONTHS[int(d[4:6]) - 1]}"
        else:
            self.ice_label = "ICE NONE"
        # the coast: a hair-thin lit line on the land's rim and the faintest glow just offshore
        u = land.astype(np.uint8)
        er = cv2.erode(u, np.ones((3, 3), np.uint8)).astype(bool)
        dl = cv2.dilate(u, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], np.uint8)).astype(bool)
        rim_in = land & ~er
        rim_out = dl & ~land
        img[rim_out] = img[rim_out] + np.array(COAST_OUT, np.float32)
        img[rim_in] = np.maximum(img[rim_in], COAST)
        self.base = img.astype(np.float32)
        self.sea_w = (~land).astype(np.float32)[..., None]
        self.ice_cover = None
        # aurora: curtains confined to the upper part, precomputed envelope
        ay = np.exp(-self.yy / 52.0).astype(np.float32)
        self.aur_env = (ay * _smooth(self.yy, 0, 6)).astype(np.float32)[:AUR_ROWS]

    # ---- the ice, fetched once a day
    def _fetch_loop(self):
        wait = max(0.0, self.ice_t + ICE_EVERY - time.time())
        backoff = 300.0
        while True:
            time.sleep(min(wait, 10.0))
            wait -= 10.0
            if wait > 0:
                continue
            if time.time() - self.last_frame > IDLE:               # not on the wall: no calls
                wait = 10.0
                continue
            try:
                rec = fetch_ice()
                rec["t"] = time.time()
                self.ice_rec, self.ice_t = rec, rec["t"]
                self.rebuild_base()
                _write_cache(rec)
                wait, backoff = ICE_EVERY, 300.0
            except Exception as e:
                print(f"[polarbears] {str(e)[:100]}", flush=True)
                wait, backoff = backoff, min(ICE_EVERY, backoff * 2)

    # ---- one frame
    def __call__(self, t):
        cv2 = self.cv2
        self.last_frame = time.time()
        if self.first_t is None:
            self.first_t = t
        base, ice_add, idx = self.base, self.ice_add, self.ice_idx
        cyc = t % self.cycle
        day = min(cyc / SEC_PER_DAY, self.days)
        T = self.t0 + day * 86400.0
        img = base.copy()
        # the ice breathes: a slow swell with a few pale glints drifting across it
        if ice_add is not None:
            ph, ph2 = self.ph[idx], self.ph2[idx]
            sh = 1.0 + 0.09 * np.sin(ph + t * 0.35) + 0.05 * np.sin(ph2 - t * 0.6)
            gl = np.maximum(0.0, np.sin(ph2 * 0.8 + t * 0.4 + 1.3)) ** 6
            img[idx] = img[idx] + ice_add * sh[:, None] + (gl * 0.30 * self.ice_a)[:, None] * np.array(ICE_RIM, np.float32)
        # the aurora: slow green-violet curtains high in the night, over the sea only
        ar = AUR_ROWS
        x = self.xx[:ar]
        y = self.yy[:ar]
        wv = 0.5 + 0.5 * np.sin(x * 0.038 + 1.7 * np.sin(y * 0.045 + t * 0.05) + t * 0.09)
        wv = wv * (0.55 + 0.45 * np.sin(x * 0.011 - t * 0.04 + 1.0))
        a = (wv * self.aur_env * AUR_AMP)[..., None]
        mix = np.clip(0.5 + 0.5 * np.sin(x * 0.02 + t * 0.03), 0, 1)[..., None]
        acol = np.array(AUR_G, np.float32) * (1 - mix) + np.array(AUR_V, np.float32) * mix
        img[:ar] += a * acol * self.sea_w[:ar]

        # ---- the comet trails: one smooth brightness taper per bear, screened together
        ages = np.arange(0.0, TAIL_DAYS, STEP)
        lvl = (1.0 - ages / TAIL_DAYS) ** 2.0 * (0.80 + 0.20 * np.exp(-ages / 2.5))
        trail = np.zeros((H, W, 3), np.float32)
        heads = []
        for b in self.bears:
            ts = T - ages * 86400.0
            inside = (ts >= b["t"][0]) & (ts <= b["t"][-1])
            if not inside.any():
                continue
            ts = ts[inside]
            # drop samples where the nearest real fix is more than GAP days away
            j = np.clip(np.searchsorted(b["t"], ts), 1, len(b["t"]) - 1)
            near = np.minimum(np.abs(ts - b["t"][j - 1]), np.abs(b["t"][j] - ts)) <= GAP * 86400.0
            xs, ys = np.interp(ts, b["t"], b["x"]), np.interp(ts, b["t"], b["y"])
            ix, iy = np.rint(xs).astype(int), np.rint(ys).astype(int)
            lv, ag = lvl[inside], ages[inside]
            ok = near & (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
            if not ok.any():
                continue
            ix, iy, lv, ag = ix[ok], iy[ok], lv[ok], ag[ok]
            ri, rj = iy[::-1], ix[::-1]                              # oldest first, so the newest LED wins
            trail[ri, rj] = np.maximum(trail[ri, rj], b["col"][None, :] * lv[::-1, None])
            age0 = float(ag[0])
            if age0 < 2.0:                                           # the newest sample is the head
                al = _smooth(2.0 - age0, 0.0, 1.0) * _smooth((T - b["t"][0]) / 86400.0, 0.0, 1.5)
                if al > 0.02:
                    heads.append((b, int(ix[0]), int(iy[0]), al))
        glow = cv2.GaussianBlur(trail, (0, 0), 1.1)
        img += trail
        img += glow * 0.75

        # ---- the heads: a bright core with a soft halo of graded LEDs
        breathe = 0.93 + 0.07 * math.sin(t * 1.9)
        if heads:
            hl = np.zeros((H, W, 3), np.float32)
            for b, x, y, al in heads:
                hl[y, x] = np.maximum(hl[y, x], b["col"] * al)
            halo = cv2.filter2D(hl, -1, _HALO, borderType=cv2.BORDER_CONSTANT) * 0.8
            img += halo
            for b, x, y, al in heads:
                img[y, x] = np.maximum(img[y, x] * (1 - al), b["core"] * (al * breathe)) if al < 1 else b["core"] * breathe
        # ---- labels, interface
        ov = np.zeros((H, W, 3), np.float32)
        self._labels(ov, heads, t)
        img = np.maximum(img, ov)
        self._corners(img, day, T, cyc, len(heads))
        # ---- fades: up at the start of the piece and of every loop, down before it starts over
        fade = min(_smooth(cyc, 0.0, FADE_IN), _smooth(self.cycle - cyc, 0.0, FADE_OUT), _smooth(t - self.first_t, 0.0, FADE_IN))
        img *= fade
        # ordered dither for the gradients, whole LEDs at the panel's 6 bits
        out = np.clip(np.floor(img / 4.0 + _BAYER) * 4.0, 0, 255).astype(np.uint8)
        return Image.fromarray(out, "RGB")

    # ---- the numbers: only the bears nearest the middle, quiet, fading in and out
    def _labels(self, ov, heads, t):
        dt = 0.04 if self.lab_t is None else min(max(t - self.lab_t, 0.0), 0.5)
        self.lab_t = t
        step = dt / 0.9
        cx, cy = W / 2.0, H / 2.0 - 8
        ranked = sorted(heads, key=lambda h: (h[1] - cx) ** 2 + (h[2] - cy) ** 2)
        want = set()
        for r, (b, x, y, al) in enumerate(ranked):
            if r < N_LABELS or (self.lab_alpha.get(b["id"], 0.0) > 0.05 and r < N_LABELS + 2):   # a little hysteresis
                want.add(b["id"])
        occupied = [(x - 3, y - 3, x + 3, y + 3) for b, x, y, al in heads]
        taken = []
        cv2 = self.cv2
        by_id = {h[0]["id"]: h for h in heads}
        for r, (b, x, y, al) in enumerate(ranked):
            bid = b["id"]
            s = b["id"]
            w = pixelfont.width(s)
            slot = None
            if bid in want:
                prefer = self.lab_slot.get(bid)
                order = [prefer] if prefer is not None else []
                order += [k for k in range(len(_SLOTS)) if k != prefer]
                for k in order:
                    name, dx, dy = _SLOTS[k]
                    lx = x + dx if dx > 0 else x + dx - w
                    ly = y + dy
                    if lx < 2 or ly < 18 or lx + w > W - 2 or ly + 5 > H - 40:
                        continue
                    box = (lx - 1, ly - 1, lx + w + 1, ly + 6)
                    if any(box[0] < o[2] and box[2] > o[0] and box[1] < o[3] and box[3] > o[1] for o in occupied + taken):
                        continue
                    slot = (k, lx, ly, box)
                    break
            a = self.lab_alpha.get(bid, 0.0)
            a = min(1.0, a + step) if slot is not None else max(0.0, a - step * 1.4)
            self.lab_alpha[bid] = a
            if slot is None:
                if a <= 0.0:
                    continue
                k = self.lab_slot.get(bid)                          # fading out where it was
                if k is None:
                    continue
                name, dx, dy = _SLOTS[k]
                lx = x + dx if dx > 0 else x + dx - w
                ly = y + dy
                box = (lx - 1, ly - 1, lx + w + 1, ly + 6)
            else:
                k, lx, ly, box = slot
                self.lab_slot[bid] = k
            taken.append(box)
            e = a * a * (3 - 2 * a)
            self._leader(ov, x, y, k, w, lx, ly, b["col"] * (0.45 * e))
            pixelfont.draw(ov, s, lx, ly, b["core"] * (0.66 * e))
        # forget bears that are gone
        for bid in [k for k, v in self.lab_alpha.items() if v <= 0.0 and k not in by_id]:
            del self.lab_alpha[bid]

    def _leader(self, ov, x, y, k, w, lx, ly, col):
        name = _SLOTS[k][0]
        cy = ly + 2
        if name == "R":
            pts = ((x + 3, y), (x + 4, y))
        elif name == "L":
            pts = ((x - 3, y), (x - 4, y))
        elif name == "UR":
            pts = ((x + 2, y - 2), (x + 3, y - 3))
        elif name == "DR":
            pts = ((x + 2, y + 2), (x + 3, y + 3))
        elif name == "UL":
            pts = ((x - 2, y - 2), (x - 3, y - 3))
        else:
            pts = ((x - 2, y + 2), (x - 3, y + 3))
        for px, py in pts:
            if 0 <= px < W and 0 <= py < H:
                ov[py, px] = np.maximum(ov[py, px], col)

    # ---- the frame of the picture: month, place, ice date, bears on the record, and the season's timeline
    def _big(self, img, text, x, y, colour):
        col = np.asarray(colour, np.float32)
        for ch in text.upper():
            g = pixelfont.GLYPHS.get(ch)
            if g is not None:
                m = np.kron(g, np.ones((2, 2), np.float32))
                img[y:y + 10, x:x + 6] = np.maximum(img[y:y + 10, x:x + 6], m[..., None] * col)
            x += 8

    def _corners(self, img, day, T, cyc, nheads):
        tm = time.gmtime(T)
        mon = _MONTHS[tm.tm_mon - 1]
        my = H - 36
        self._big(img, mon, 4, my, MONTH_COL)
        pixelfont.draw(img, str(tm.tm_mday), 4 + 22 + 4, my + 5, DIM_COL)
        img[my + 12, 4:4 + 22] = np.maximum(img[my + 12, 4:4 + 22], RULE_COL)
        pixelfont.draw(img, "SVALBARD", W - 4 - pixelfont.width("SVALBARD"), 4, DIM_COL)
        pixelfont.draw(img, "POLAR BEARS", W - 4 - pixelfont.width("POLAR BEARS"), 10, FAINT_COL)
        pixelfont.draw(img, self.ice_label, W - 4 - pixelfont.width(self.ice_label), H - 21, (84, 124, 178))
        pixelfont.draw(img, f"{nheads} ON RECORD", 4, my + 15, FAINT_COL)
        # the timeline: the season's 237 days along the foot, month initials beneath their stretch, now lit
        y = H - 5
        x0, x1 = 4, W - 5
        span = self.t1 - self.t0
        img[y, x0:x1 + 1] = np.maximum(img[y, x0:x1 + 1], TL_FUT)
        xn = x0 + min(1.0, (T - self.t0) / span) * (x1 - x0)
        n = int(xn) - x0 + 1
        if n > 0:
            ramp = (0.35 + 0.65 * np.linspace(0, 1, n, dtype=np.float32))[:, None]
            img[y, x0:x0 + n] = np.maximum(img[y, x0:x0 + n], np.array(TL_PAST, np.float32) * ramp)
        starts = [self.t0]
        t = self.t0 + 86400.0
        while t <= self.t1:
            if time.gmtime(t).tm_mday == 1:
                starts.append(t)
            t += 86400.0
        starts.append(self.t1)
        cur = -1
        for i in range(len(starts) - 1):
            if starts[i] <= T < starts[i + 1] or (i == len(starts) - 2 and T >= starts[i]):
                cur = i
        for i, s in enumerate(starts):
            xs = int(round(x0 + (s - self.t0) / span * (x1 - x0)))
            img[y - 1:y + 2, xs] = np.maximum(img[y - 1:y + 2, xs], TL_TICK)
        for i in range(len(starts) - 1):
            a = x0 + (starts[i] - self.t0) / span * (x1 - x0)
            b = x0 + (starts[i + 1] - self.t0) / span * (x1 - x0)
            m = time.gmtime((starts[i] + starts[i + 1]) / 2)
            ini = _MONTHS[m.tm_mon - 1][0]
            pixelfont.draw(img, ini, int(round((a + b) / 2)) - 1, y - 9, TL_NOW if i == cur else TL_INI)
        # now: a bright LED with a short halo
        xi = int(round(xn))
        img[y - 1:y + 2, xi] = np.maximum(img[y - 1:y + 2, xi], (235, 240, 255))
        for dx, v in ((-2, 0.25), (-1, 0.55), (1, 0.55), (2, 0.25)):
            if 0 <= xi + dx < W:
                img[y, xi + dx] = np.maximum(img[y, xi + dx], np.array((235, 240, 255), np.float32) * v)


_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

_b = None


def frame(t):
    global _b
    if _b is None:
        _b = Bears()
    return _b(t)


def thumb():
    """A still for the app: the replay at a busy moment in July, the bundled ice, no network."""
    b = Bears(fetch=False)
    b.ice_rec = b.meta.get("ice") or b.ice_rec
    b.rebuild_base()
    b.first_t = -1e9
    return b(74 * SEC_PER_DAY)
