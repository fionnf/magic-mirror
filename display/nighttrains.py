"""Night-train atlas: every night train in Europe, as one slow golden dot with a long tail, on the clock of
its own timetable. Each evening they set out - Nightjets from Zurich and Vienna, the European Sleeper from
Brussels and Berlin, the Caledonian Sleeper from Euston, the Swedish, Norwegian and Finnish night trains, the
Italian, French, Polish, Romanian, Bulgarian and Ukrainian ones, the Balkan Express to Istanbul - and crawl
across the dim outline of the continent (about 100 km an hour is five LEDs an hour), each leaving a thread of
gold that cools to ember and dissolves behind it. When a train arrives in the morning its dot lingers a little
and the thread fades away from the far end, until the wall is empty and the next evening's trains start again.

Under them the cities sleep: each city LED is pale while its sun is up and dims to a deep blue as local night
deepens, and a faint dithered shade covers the half of the continent that is in darkness, creeping west with the
real sun (computed here, no network). Zurich, where this wall hangs, is picked out in gold.

WHAT IT SHOWS, HONESTLY. This is the TIMETABLE, not live positions: each dot is where the printed timetable says
the train is at this moment (as the caption on the wall says: TIMETABLE - NOT LIVE), moving in a straight line
(a great-circle arc) between the stops that could be matched to places, with no rail geometry, no delays and no
cancellations. Trains run only on the weekdays the source gives for them (many on fewer than seven); seasonal
services that are not running now are left out. Nothing here is a recorded track.

THE DATA is assets/nighttrains/services.json, built by tools/build_nighttrains.py (see its docstring for how
it is made and edited): the lines and their stop times and weekdays are the Open Night Train Database of
Back-on-Track.eu (https://back-on-track.eu/night-train-database/, read 2026-10-28), re-keyed in compact form;
the places of the stops are GeoNames (CC BY 4.0). It is a secondary source and a snapshot: check a timetable
with the operator before travelling, and rebuild the file when the timetables change. The outline is Natural
Earth 1:50m coastline (public domain), assets/nighttrains/europe.json. The sun, the time zones (EU summer-time
rules, Turkey UTC+3) and all positions are computed here; there is no network use at all, so there is no
cache file and nothing that can fail offline.

Everything is drawn on whole LEDs (no anti-aliasing): single lit LEDs on black, in deep colours that keep a
channel well above the LEDs' dark floor. A frame costs a few milliseconds: the trains' paths are straight arcs
precomputed once, and the dots and tails are interpolated for the moment.
"""
import calendar
import datetime
import json
import math
import os
import time

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "nighttrains")
HOME = (47.3726, 8.5398)                      # Rennweg, Zurich

# ---- the picture: a Lambert conic projection of Europe, 16 km to the LED, Scotland to Konya, Bodo to Sicily
KM_PX = 16.0
X0, Y1, TOP = -1400.0, 1740.0, 8.0            # left edge (km east of the centre meridian), top edge (km north), top margin
EARTH = 6371.0
LAT0, LON0, PAR1, PAR2 = 52.0, 14.0, 40.0, 64.0
_n = math.log(math.cos(math.radians(PAR1)) / math.cos(math.radians(PAR2))) / math.log(
    math.tan(math.pi / 4 + math.radians(PAR2) / 2) / math.tan(math.pi / 4 + math.radians(PAR1) / 2))
_F = math.cos(math.radians(PAR1)) * math.tan(math.pi / 4 + math.radians(PAR1) / 2) ** _n / _n
_RHO0 = EARTH * _F / math.tan(math.pi / 4 + math.radians(LAT0) / 2) ** _n


def project(lat, lon):
    """(lat, lon) degrees -> LED coordinates (float x, y)."""
    la, lo = np.radians(np.asarray(lat, np.float64)), np.radians(np.asarray(lon, np.float64))
    rho = EARTH * _F / np.tan(math.pi / 4 + la / 2) ** _n
    th = _n * (lo - math.radians(LON0))
    return (rho * np.sin(th) - X0) / KM_PX, (Y1 - (_RHO0 - rho * np.cos(th))) / KM_PX + TOP


def unproject(px, py):
    """LED coordinates -> (lat, lon) degrees."""
    x = px * KM_PX + X0
    y = Y1 - (py - TOP) * KM_PX
    d = _RHO0 - y
    rho = np.hypot(x, d)
    th = np.arctan2(x, d)
    lat = 2 * np.arctan((EARTH * _F / rho) ** (1.0 / _n)) - math.pi / 2
    return np.degrees(lat), LON0 + np.degrees(th / _n)


# ---- colours (the wall shows nothing below ~94 in a channel, and only ~5 steps above it: 94 149 188 219 245)
COAST = np.array([26, 48, 106], np.float32)           # the quiet outline
SHADE = np.array([38, 16, 100], np.float32)           # the night side, on a few LEDs only
CITY_DAY = np.array([214, 224, 244], np.float32)      # a city whose sun is up
CITY_NIGHT = np.array([62, 82, 164], np.float32)      # asleep
ZURICH = np.array([255, 230, 160], np.float32)
ZURICH_RING = np.array([150, 196, 255], np.float32)   # a cool ring, so it stands out from the gold of the trains
HEAD = np.array([255, 240, 170], np.float32)          # the train: a bright gold point
THREAD_U = np.array([0.0, 0.2, 0.5, 0.8, 1.0])        # thread colour by age (fraction of the tail): gold cooling to ember
THREAD_C = np.array([(244, 158, 44), (228, 116, 38), (194, 76, 34), (156, 52, 34), (124, 42, 40)], np.float32)
TEXT = np.array([158, 126, 64], np.float32)
TEXT_DIM = np.array([112, 100, 80], np.float32)

TAIL = 2.5 * 3600.0                                   # seconds of path a thread shows
STEP = 120.0                                          # seconds between the points of a thread (<1 LED at 190 km/h)
PRE = 600.0                                           # a dot appears this long before its departure
LINGER = 1500.0                                       # and stays this long after its arrival, fading
ARC_KM = 100.0                                        # long legs are bent to the great circle every so often
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) + 0.5) / 16.0
AGES = np.arange(0.0, TAIL + 1.0, STEP)
_U = AGES / TAIL
LUT = np.stack([np.interp(_U, THREAD_U, THREAD_C[:, c]) for c in range(3)], 1).astype(np.float32)   # colour by age
LVL = np.clip((1.0 - _U) / 0.5, 0.0, 1.0)        # how likely an LED of that age is lit: it thins out with age
RUN_SPAN = 1.0e6                                      # seconds between runs in the combined time axis

# ------------------------------------------------------------------ time, the sun ---


def eu_summer(unix):
    """True where the EU's summer time is in force: last Sunday of March to last Sunday of October, 01:00 UTC."""
    unix = np.asarray(unix, np.float64)
    years = unix.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    out = np.zeros(unix.shape, bool)
    for y in np.unique(years):
        span = []
        for month in (3, 10):
            d = datetime.date(int(y), month, 31)
            d -= datetime.timedelta(days=(d.weekday() + 1) % 7)
            span.append(calendar.timegm((int(y), month, d.day, 1, 0, 0)))
        out |= (years == y) & (unix >= span[0]) & (unix < span[1])
    return out


def to_utc(day, minutes, tz):
    """Unix time of a local clock reading: `day` (days since 1970 of the date the train set out), minutes since
    that date's midnight at the stop's clock, tz = standard-time hours (3 = Turkey, no summer time)."""
    naive = day * 86400.0 + np.asarray(minutes, np.float64) * 60.0
    guess = naive - np.asarray(tz, np.float64) * 3600.0
    return guess - np.where((tz < 3) & eu_summer(guess), 3600.0, 0.0)


def sun(unix):
    """(declination, right ascension, Greenwich sidereal angle) in radians (almanac low precision, ~0.01 deg)."""
    j = unix / 86400.0 + 2440587.5
    n = j - 2451545.0
    L = math.radians((280.460 + 0.9856474 * n) % 360)
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 4e-7 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    tu = n / 36525.0
    s = 67310.54841 + (876600.0 * 3600.0 + 8640184.812866) * tu + 0.093104 * tu * tu - 6.2e-6 * tu ** 3
    return dec, ra, (s % 86400.0) / 86400.0 * 2 * math.pi


def sun_elevation(unix, lat_deg, lon_deg):
    """The sun's height above the horizon (degrees) at places given in degrees (arrays or numbers)."""
    dec, ra, gst = sun(unix)
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    h = gst + lon - ra
    return np.degrees(np.arcsin(np.sin(lat) * math.sin(dec) + np.cos(lat) * math.cos(dec) * np.cos(h)))


def great_circle(a, b, k):
    """k-1 points between two (lat, lon) places, as degrees, along the great circle."""
    p1, l1, p2, l2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    va = np.array([math.cos(p1) * math.cos(l1), math.cos(p1) * math.sin(l1), math.sin(p1)])
    vb = np.array([math.cos(p2) * math.cos(l2), math.cos(p2) * math.sin(l2), math.sin(p2)])
    om = math.acos(max(-1.0, min(1.0, float(va @ vb))))
    f = np.arange(1, k) / k
    if om < 1e-6:
        return np.full(k - 1, a[0]), np.full(k - 1, a[1])
    v = (np.sin((1 - f) * om)[:, None] * va + np.sin(f * om)[:, None] * vb) / math.sin(om)
    return np.degrees(np.arcsin(v[:, 2])), np.degrees(np.arctan2(v[:, 1], v[:, 0]))


# ------------------------------------------------------------------ the piece ---

class Service:
    """One direction of one night train: its stops, and its path as LED coordinates with a time recipe."""
    __slots__ = ("name", "op", "days", "tz", "arr", "dep", "x", "y", "ia", "ib", "f", "zurich")

    def __init__(self, s):
        st = s["stops"]
        self.name, self.op = s["name"], s["op"]
        self.days = [c == "1" for c in s["days"]]
        self.tz = np.array([p[2] for p in st], np.float64)
        self.arr = np.array([p[3] for p in st], np.float64)
        self.dep = np.array([p[4] for p in st], np.float64)
        n = len(st)
        lat, lon, ia, ib, f = [], [], [], [], []

        def add(la, lo, a, b, fr):
            lat.append(la)
            lon.append(lo)
            ia.append(a)
            ib.append(b)
            f.append(fr)

        for i in range(n):
            if i and self.arr[i] < self.dep[i]:                      # it waits here
                add(st[i][0], st[i][1], 2 * i, 2 * i, 0.0)
            add(st[i][0], st[i][1], 2 * i + 1 if i < n - 1 else 2 * i, 2 * i + 1 if i < n - 1 else 2 * i, 0.0)
            if i < n - 1:
                d = _km((st[i][0], st[i][1]), (st[i + 1][0], st[i + 1][1]))
                k = max(1, int(math.ceil(d / ARC_KM)))
                if k > 1:
                    la, lo = great_circle(st[i][:2], st[i + 1][:2], k)
                    for j in range(k - 1):
                        add(la[j], lo[j], 2 * i + 1, 2 * i + 2, (j + 1) / k)
        self.x, self.y = project(np.array(lat), np.array(lon))
        self.ia, self.ib, self.f = np.array(ia), np.array(ib), np.array(f)
        self.zurich = any(_km(HOME, (p[0], p[1])) < 8.0 for p in st)


def _km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(math.radians(b[1] - a[1]))
    return EARTH * math.acos(max(-1.0, min(1.0, c)))


class Run:
    """One journey on one date: its times in unix seconds along the service's path."""
    __slots__ = ("svc", "T", "start", "end")

    def __init__(self, svc, day):
        V = np.empty(2 * len(svc.tz))
        V[0::2] = to_utc(day, svc.arr, svc.tz)
        V[1::2] = to_utc(day, svc.dep, svc.tz)
        self.svc = svc
        self.T = np.maximum.accumulate((1.0 - svc.f) * V[svc.ia] + svc.f * V[svc.ib])
        self.start, self.end = float(self.T[0]), float(self.T[-1])


def _load():
    """(services, cities, coast) from the assets; whatever is missing is simply left out."""
    services, cities, coast = [], [], []
    try:
        with open(os.path.join(DATA, "services.json")) as fh:
            d = json.load(fh)
        services = [Service(s) for s in d["services"] if len(s["stops"]) >= 2 and "1" in s["days"]]
        cities = d["cities"]
    except Exception as e:
        print(f"[nighttrains] services: {str(e)[:100]}", flush=True)
    try:
        with open(os.path.join(DATA, "europe.json")) as fh:
            coast = json.load(fh)["coast"]
    except Exception as e:
        print(f"[nighttrains] coast: {str(e)[:100]}", flush=True)
    return services, cities, coast


class NightTrains:
    def __init__(self):
        from display import pixelfont
        self.font = pixelfont
        self.services, cities, coast = _load()
        self.coast = self._coast(coast)
        self.cities = cities
        c = np.array([[c[1], c[2], c[3]] for c in cities], np.float64).reshape(-1, 3)
        self.c_lat, self.c_lon, pop = c[:, 0], c[:, 1], c[:, 2]
        self.c_x, self.c_y = project(self.c_lat, self.c_lon)
        self.c_px = np.round(self.c_x).astype(int)
        self.c_py = np.round(self.c_y).astype(int)
        self.c_size = np.clip(0.62 + 0.14 * np.log10(np.maximum(pop, 30.0) / 30.0), 0.62, 1.0)
        self.c_in = (self.c_px >= 0) & (self.c_px < W) & (self.c_py >= 0) & (self.c_py < H)
        ys, xs = np.mgrid[0:H, 0:W]
        lat, lon = unproject(xs.astype(np.float64), ys.astype(np.float64))
        self.sin_lat, self.cos_lat, self.lon = np.sin(np.radians(lat)), np.cos(np.radians(lat)), np.radians(lon)
        self.thr = BAYER[ys % 4, xs % 4]
        self.map_rows = (ys > 3) & (ys < TOP + (Y1 + 1680.0) / KM_PX + 2)         # the shade stays on the map
        self.zx, self.zy = (int(round(float(v))) for v in project(*HOME))
        self.base, self.base_t = None, -1e9
        self.runs, self.rs, self.re, self.window = [], np.zeros(0), np.zeros(0), None
        self.noise = np.random.RandomState(7).random_sample((H, W))

    # ---------------------------------------------------------- the still layers
    def _coast(self, coast):
        import cv2
        m = np.zeros((H, W), np.uint8)
        for line in coast:
            la, lo = np.array(line, np.float64).T
            x, y = project(la, lo)
            cv2.polylines(m, [np.round(np.stack([x, y], 1)).astype(np.int32)], False, 1, 1, cv2.LINE_8)
        return m > 0

    def _base(self, unix):
        """The slow layer, redrawn every 30 s: the night side, the coast, the sleeping cities, Zurich, the title."""
        img = np.zeros((H, W, 3), np.float32)
        dec, ra, gst = sun(unix)
        sin_el = self.sin_lat * math.sin(dec) + self.cos_lat * math.cos(dec) * np.cos(gst + self.lon - ra)
        el = np.degrees(np.arcsin(np.clip(sin_el, -1, 1)))
        dark = np.clip((2.0 - el) / 20.0, 0.0, 1.0)                # 0 by day, 1 from 18 degrees below the horizon
        img[self.map_rows & (dark * 0.07 > self.noise)] = SHADE
        img[self.coast] = COAST
        # the cities: pale while the sun is up, dim as local night deepens
        awake = np.clip((sun_elevation(unix, self.c_lat, self.c_lon) + 9.0) / 13.0, 0.0, 1.0)
        for k in np.nonzero(self.c_in)[0]:
            col = CITY_NIGHT + (CITY_DAY - CITY_NIGHT) * awake[k] ** 1.3 * self.c_size[k]
            img[self.c_py[k], self.c_px[k]] = col
        zel = float(sun_elevation(unix, HOME[0], HOME[1]))
        za = min(1.0, max(0.0, (zel + 9.0) / 13.0))
        zx, zy = self.zx, self.zy
        img[zy, zx] = ZURICH * (0.8 + 0.2 * za)
        for dx, dy in ((3, 0), (-3, 0), (0, 3), (0, -3), (2, 2), (-2, 2), (2, -2), (-2, -2)):
            img[zy + dy, zx + dx] = ZURICH_RING
        self.font.draw(img, "NIGHT TRAINS", 2, 1, TEXT)
        return img

    # ---------------------------------------------------------- the timetable
    def _runs_for(self, unix):
        """All journeys that could be on the move around `unix`: every service on its origin dates d-2 .. d+1,
        joined into one time axis (each run RUN_SPAN seconds after the last) so that one np.interp finds them all."""
        d0 = int(unix // 86400)
        if self.window == d0:
            return
        runs = [Run(svc, day) for svc in self.services for day in range(d0 - 2, d0 + 2) if svc.days[(day + 3) % 7]]
        self.base_unix = d0 * 86400.0 - 3 * 86400.0
        self.runs = runs
        self.rs = np.array([r.start for r in runs])
        self.re = np.array([r.end for r in runs])
        self.zr = np.array([r.svc.zurich for r in runs], bool)
        self.phase = (np.arange(len(runs)) * 0.6180339887) % 1.0
        self.TT = np.concatenate([r.T - self.base_unix + i * RUN_SPAN for i, r in enumerate(runs)]) if runs else np.zeros(1)
        self.XX = np.concatenate([r.svc.x for r in runs]) if runs else np.zeros(1)
        self.YY = np.concatenate([r.svc.y for r in runs]) if runs else np.zeros(1)
        self.window = d0

    # ---------------------------------------------------------- frames
    def draw(self, t, unix):
        if self.base is None or abs(unix - self.base_t) > 30.0:
            self.base, self.base_t = self._base(unix), unix
        self._runs_for(unix)
        img = self.base.copy()
        flat = img.reshape(-1, 3)
        live = np.nonzero((self.rs - PRE <= unix) & (unix <= self.re + TAIL + LINGER))[0]
        moving = int(np.count_nonzero((self.rs <= unix) & (unix <= self.re)))
        if len(live):
            rs, re = self.rs[live], self.re[live]
            off = live * RUN_SPAN - self.base_unix
            # the threads: the path over the last hours, a point every STEP seconds, cooling with age
            tau = unix - AGES[None, :]                                  # (runs, ages)
            ri, ai = np.nonzero((tau >= rs[:, None]) & (tau <= re[:, None]))
            if len(ri):
                q = unix - AGES[ai] + off[ri]
                x = np.round(np.interp(q, self.TT, self.XX)).astype(np.int64)
                y = np.round(np.interp(q, self.TT, self.YY)).astype(np.int64)
                ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
                x, y, ai = x[ok], y[ok], ai[ok]
                show = LVL[ai] > self.thr[y, x]
                x, y, ai = x[show], y[show], ai[show]
                order = np.argsort(-ai, kind="stable")                   # youngest written last: it wins
                flat[(y * W + x)[order]] = LUT[ai[order]]
            # the heads: pale gold points, breathing a little; one comes a little before its departure, stays after its arrival
            a = np.where(unix < rs, (unix - (rs - PRE)) / PRE, np.where(unix > re, 1.0 - (unix - re) / LINGER, 1.0))
            t_h = np.clip(unix, rs, re) + off
            hx = np.round(np.interp(t_h, self.TT, self.XX)).astype(np.int64)
            hy = np.round(np.interp(t_h, self.TT, self.YY)).astype(np.int64)
            lvl = np.clip(a, 0.0, 1.0) * (0.88 + 0.12 * np.sin(2 * math.pi * (t / 6.0 + self.phase[live])))
            ok = (hx >= 0) & (hx < W) & (hy >= 0) & (hy < H) & (lvl * HEAD.max() >= 100.0)
            hx, hy, lvl = hx[ok], hy[ok], lvl[ok]
            flat[hy * W + hx] = HEAD[None, :] * lvl[:, None]
        self._label(img)
        self._caption(img, unix, moving)
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")

    def _label(self, img):
        """Zurich's name, over everything, on a black patch so it reads through the traffic."""
        label = "ZURICH"
        w = self.font.width(label)
        lx = self.zx - 5 - w if self.zx > W // 2 else self.zx + 6
        ly = self.zy + 6
        img[ly - 1:ly + 6, lx - 1:lx + w + 1] = 0.0
        self.font.draw(img, label, lx, ly, ZURICH_RING * 0.95)

    def _caption(self, img, unix, moving):
        """At the foot: Zurich's clock, how many trains are on the move, and that it is only the timetable."""
        summer = bool(eu_summer(np.array([unix]))[0])
        local = unix + (7200 if summer else 3600)
        hh, mm = int(local // 3600 % 24), int(local // 60 % 60)
        y0 = H - 25
        f = self.font
        f.draw(img, f"{hh:02d}", 2, y0, ZURICH * 0.75)
        for yy in (y0 + 1, y0 + 3):                                  # the colon the 3x5 font does not have
            img[yy, 9] = ZURICH * 0.75
        f.draw(img, f"{mm:02d}", 12, y0, ZURICH * 0.75)
        f.draw(img, "CEST" if summer else "CET", 22, y0, TEXT_DIM)
        f.draw(img, f"{moving} TRAINS UNDERWAY", 2, y0 + 8, TEXT)
        f.draw(img, "TIMETABLE - NOT LIVE", 2, y0 + 16, TEXT_DIM)

    def __call__(self, t, now=None):
        return self.draw(t, time.time() if now is None else now)


_nt = None


def frame(t):
    global _nt
    if _nt is None:
        _nt = NightTrains()
    return _nt(t)


def thumb():
    """A still for the app, no network: today's dawn over Zurich, the moment the sun there climbs through 3
    degrees below the horizon, when the night trains are arriving and their threads begin to fade."""
    nt = NightTrains()
    day0 = int(time.time() // 86400) * 86400.0
    when = day0 + 5.5 * 3600
    for m in range(0, 24 * 60, 5):                          # first time after 03:00 UTC the sun is rising through -3
        u = day0 + 3 * 3600 + m * 60
        if sun_elevation(u, HOME[0], HOME[1]) > -3.0:
            when = u
            break
    return nt(0.0, when)
