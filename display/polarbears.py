"""Polar bears of Svalbard: recorded satellite-collar tracks of polar bears, one lit LED per bear with a
long fading trail and the bear's own number beside it, over a dim map of Svalbard and the Fram Strait,
with the sea ice of the day underneath.

THIS IS A REPLAY, NOT LIVE. The Norwegian Polar Institute does not publish live bear positions. The
tracks are real, recorded in 2012 (7 April to 30 November) on female bears in Svalbard, and the wall says
so ("BEARS 2012 NOT LIVE", with the date of the replay in the corner). Time is compressed: the 237 days
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

SEA = (0, 0, 0)
LAND = (22, 24, 36)
COAST = (52, 60, 92)
ICE_LO, ICE_HI = (22, 52, 92), (92, 142, 186)      # 15 % ice ... 100 % ice: deep blue to pale blue
TEXT = (112, 122, 172)
LABEL = (110, 118, 160)

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
        for rank, i in enumerate(order):                           # warm hues only, so bears stand out from the blue ice
            hue = -40 + 150.0 * ((rank * 0.618034) % 1.0)
            self.bears[i]["col"] = np.array(_hsv(hue, 0.80, 1.0), np.float32)
        self.land = self._land_mask()
        self.ice_rec = None
        self.ice_t = 0.0
        self.base = None
        self.last_frame = time.time()
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
        cv2 = self.cv2
        img = np.zeros((H, W, 3), np.float32)
        img[:] = SEA
        if self.ice_rec is not None:
            c = ice_concentration(self.ice_rec)
            # the 25 km cells cannot see fjords (their passive microwave reading bleeds off the land): 
            # ice within ~10 km of the coast
            dist = self.cv2.distanceTransform((~self.land).astype(np.uint8), self.cv2.DIST_L2, 3)
            lit = (c >= 0.15) & (dist > 9.0)
            f = np.clip((c - 0.15) / 0.85, 0, 1)[..., None]
            col = np.array(ICE_LO, np.float32) + (np.array(ICE_HI, np.float32) - np.array(ICE_LO, np.float32)) * f
            img = np.where(lit[..., None], col, img)
            d = self.ice_rec["date"]
            self.ice_label = f"ICE {int(d[6:8])} {_MONTHS[int(d[4:6]) - 1]}"
        else:
            self.ice_label = "ICE NONE"
        img[self.land] = LAND
        u8 = img.astype(np.uint8)
        for pts in self.coast:
            cv2.polylines(u8, [pts], True, COAST, 1, cv2.LINE_8)
        self.base = u8.astype(np.float32)

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
        self.last_frame = time.time()
        cyc = t % self.cycle
        day = min(cyc / SEC_PER_DAY, self.days)
        T = self.t0 + day * 86400.0
        img = self.base.copy()
        ages = np.arange(0.0, TRAIL_DAYS, STEP)
        lvl = np.exp(-ages / TAU)
        keep = lvl >= 0.16
        ages, lvl = ages[keep], lvl[keep]
        # a quiet breath on every head
        breathe = 0.9 + 0.1 * math.sin(t * 2.2)
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
            ix, iy, lv = np.rint(xs).astype(int), np.rint(ys).astype(int), lvl[inside]
            ok = near & (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
            if not ok.any():
                continue
            ix, iy, lv = ix[ok], iy[ok], lv[ok]
            col = b["col"][None, :] * lv[:, None]
            img[iy, ix] = np.maximum(img[iy, ix], col)
            if ages[inside][ok][0] < 0.5 and T <= b["t"][-1]:        # the newest sample is the head
                heads.append((b, int(ix[0]), int(iy[0])))
        for b, x, y in heads:
            img[y, x] = np.maximum(img[y, x], b["col"] * breathe)
        taken = []
        for b, x, y in heads:
            self._label(img, b, x, y, taken)
        self._corners(img, day, T, cyc)
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")

    def _label(self, img, b, x, y, taken):
        """The bear's number beside its spot, where it overlaps no other label."""
        s = b["id"]
        w, h = pixelfont.width(s), 5
        for dx, dy in ((3, -2), (-3 - w, -2), (3, -8), (-3 - w, -8), (3, 4), (-3 - w, 4), (-w // 2, -8), (-w // 2, 4),
                       (3, -12), (-3 - w, 6), (3, 8)):
            lx, ly = x + dx, y + dy
            if lx < 1 or ly < 9 or lx + w > W - 1 or ly + h > H - 9:
                continue
            if any(lx < r[2] + 3 and lx + w + 3 > r[0] and ly < r[3] + 2 and ly + h + 2 > r[1] for r in taken):
                continue
            taken.append((lx, ly, lx + w, ly + h))
            pixelfont.draw(img, s, lx, ly, b["col"] * 0.72)
            return
        # no free place: leave this bear unlabelled for the moment

    def _corners(self, img, day, T, cyc):
        tm = time.gmtime(T)
        pixelfont.draw(img, f"{_MONTHS[tm.tm_mon - 1]} {tm.tm_year}", 3, 3, TEXT)
        pixelfont.draw(img, "SVALBARD", W - 3 - pixelfont.width("SVALBARD"), 3, TEXT)
        pixelfont.draw(img, "BEARS 2012 NOT LIVE", 3, H - 9 - 6, TEXT)
        pixelfont.draw(img, self.ice_label, W - 3 - pixelfont.width(self.ice_label), H - 9 - 6, TEXT)
        # a thin timeline along the foot: the replay's 237 days, a tick at each month and a mark for now
        y = H - 4
        x0, x1 = 3, W - 4
        img[y, x0:x1 + 1] = np.maximum(img[y, x0:x1 + 1], (34, 38, 64))
        t = self.t0
        while t <= self.t1:
            tm2 = time.gmtime(t)
            if tm2.tm_mday == 1 or t == self.t0:
                x = x0 + int((t - self.t0) / (self.t1 - self.t0) * (x1 - x0))
                img[y - 1:y + 2, x] = np.maximum(img[y - 1:y + 2, x], (50, 56, 90))
            t += 86400.0
        x = x0 + int(min(1.0, (T - self.t0) / (self.t1 - self.t0)) * (x1 - x0))
        img[y - 1:y + 2, x] = (150, 160, 215)


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
    return b(b.cycle * 0.0 + (74 / 1.0) * SEC_PER_DAY)
