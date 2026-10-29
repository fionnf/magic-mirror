"""Night trains: every European night train as a slow luminous comet over the sleeping continent, with the real
night side of the Earth drawn as a deep indigo shade, a violet-and-gold band where the sun is rising or setting,
and cities that glow while their evening lasts and fall dark one by one as local night deepens.

THE PICTURE. A Lambert conic map of Europe (Scotland to Konya, Bodo to Sicily, 16 km to the LED). Land is a faint
dithered tone of deep blue, the mountains (Alps, Pyrenees, Carpathians, Apennines, Balkan ranges, Scandes,
Taurus) a little denser along hand-placed ridge lines, the sea is black: there is no outline, only where the
tone ends. The night side is a dithered indigo that deepens with the sun's real depth below the horizon (computed
here, no network); where the sun is within a few degrees of the horizon the shade turns violet, rose and gold,
brighter on the dawn side, and that band creeps west over the continent through the night. Each train is a comet:
a bright head, a smooth tail along the route that thins out over some 15 LEDs, amber for trains heading south
and east, teal for those heading north and west, with a slow twinkle. A train that is running late (5 minutes or
more, in the live data) glows red-gold and pulses, faster the later it is. Routes show as the faintest threads,
which the tails light up. Zurich, where this wall hangs, is marked by a soft halo, no label. In the corner is
one tiny label: LIVE and the number of live night trains, TIMETABLE, or NO DATA.

LIVE DATA, HONESTLY. While frames are being drawn (and for 2 minutes after the last one), a side thread asks the
free Transitous / MOTIS service (https://api.transitous.org, no key; community-run, so it is polite: one call
every 3 minutes at night, 10 minutes by day, backing off on errors, gzip, User-Agent
'fortuna-wall/1.0 (private art project)') for every train segment running in Europe over the next few
minutes (/api/v6/map/trips, zoom 4). The API cannot filter by operator, so the thread keeps what is a night
train: the feed's own NIGHT_RAIL mode, or a rail trip named like a night brand (Nightjet NJ, EuroNight EN,
Intercity Notte ICN, IR-N, European Sleeper, Caledonian Sleeper, Snalltaget, nattag, ...), or a long
overnight run. Each train is placed between its segment's ends by the realtime times of the feed, along the
feed's own track geometry (a great circle if there is none), with its tail along the segments seen in the last
hours. The same train often arrives from several feeds (NJ 421, NJ 40421, EN 40421 ...): trains within 1.5 LEDs
of each other are drawn once. The newest answer is kept in panel_setup/nighttrains_cache.json (git-ignored) so a
restart has something to show; nothing here ever blocks a frame, and with the network dead the piece quietly
runs on the timetable.

What "live" really means differs by country, because Transitous only has real-time delays where an operator
publishes them. Measured on 2026-10-29: real-time updates were flowing for Germany (DELFI), the Czech Republic,
Poland (PKP Intercity), Bulgaria, Finland, Hungary (MAV), Italy (Trenitalia), the Netherlands and Norway (partly),
Romania and Slovakia (partly), a few Austrian (OBB), Swiss, French and Eurostar trips, and the European
Sleeper; Great Britain (the Caledonian Sleeper), Spain, Sweden, Serbia, Turkey and Ukraine are timetable-only
there. Where a trip has no real-time, the live layer shows its scheduled position (still the feed's, not ours),
and no delay glow is possible. The OBB Nightjets, the largest network, are mostly in that last group at the time
of writing, so many "live" Nightjets are really the schedule; the count says live-LAYER trains, not
GPS-tracked ones. Positions are linear in time along each segment, which can be hundreds of kilometres long:
a train that waits at a station inside one segment will run ahead of the dot or behind it.

THE TIMETABLE, the offline fallback and the filler. assets/nighttrains/services.json is built by
tools/build_nighttrains.py (see its docstring) from the Open Night Train Database of Back-on-Track.eu
(https://back-on-track.eu/night-train-database/, read 2026-10-28; credit and thanks to its volunteers). That
database has no open licence that we know of (its site terms are not CC-BY: treat it as all rights reserved
and non-commercial); it is used for a private art wall and credited, but must not be republished in a public
repository without their permission. The source gives weekdays only, no season dates, so a seasonal service
that is not running now but has weekday flags is still drawn: check an operator before travelling. Stops are
placed with GeoNames (CC BY 4.0), the outline with Natural Earth (public domain). Timetable trains are drawn
where the schedule puts them, in straight arcs, and a timetable train is left out when the live layer has the
same train (the same number, or a live train within 3 LEDs). When live data are fresh the corner counts live
night trains, then "+n" timetable trains the live layer lacks. If services.json is missing or malformed and
there is no live data, the wall says NO DATA.

Everything is on whole LEDs (no anti-aliasing), single points in deep colours that keep a channel above the LEDs'
dark floor (~94); gradients are made by ordered dithering. The static layers are computed once, the sky every
30 s, the timetable for the next UTC day on a side thread; a frame costs about 10 ms.
"""
import calendar
import datetime
import gzip
import json
import math
import os
import re
import threading
import time

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "nighttrains")
CACHE = os.path.join(ROOT, "panel_setup", "nighttrains_cache.json")
HOME = (47.3726, 8.5398)                      # Rennweg, Zurich

_clock = time.time                            # the wall's clock; tests replace it

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
LAND = np.array([34, 54, 128], np.float32)            # land: a faint dithered tone
RIDGE = np.array([78, 96, 178], np.float32)           # mountains, a little lighter
EDGE = np.array([46, 82, 156], np.float32)            # where land meets sea
THREAD = np.array([62, 56, 128], np.float32)          # a route, barely there
CITY_WARM = np.array([236, 196, 150], np.float32)
CITY_EMBER = np.array([128, 88, 70], np.float32)
CITY_DAY = np.array([150, 170, 222], np.float32)
GOLD = np.array([255, 226, 150], np.float32)
HALO = np.array([140, 120, 70], np.float32)
AMBER = (np.array([255, 236, 190], np.float32), np.array([255, 160, 44], np.float32), np.array([150, 62, 30], np.float32))
TEAL = (np.array([210, 255, 250], np.float32), np.array([60, 214, 206], np.float32), np.array([28, 96, 124], np.float32))
LATE = np.array([255, 70, 40], np.float32)
LABEL = np.array([104, 112, 178], np.float32)
LABEL2 = np.array([92, 98, 150], np.float32)
LABEL_WARN = np.array([220, 130, 60], np.float32)

# the sky: by the sun's height (deg) the density of lit LEDs and their colour (night side, terminator, dawn)
SKY_E = np.array([-40.0, -24.0, -18.0, -12.0, -7.0, -3.0, 0.0, 3.0, 6.5])
SKY_D = np.array([0.02, 0.035, 0.05, 0.08, 0.12, 0.15, 0.15, 0.07, 0.0])
SKY_C = np.array([(30, 22, 112), (36, 26, 128), (46, 30, 142), (68, 40, 162), (120, 56, 178), (206, 84, 122),
                  (240, 140, 60), (255, 190, 90), (255, 200, 120)], np.float32)

TAIL = 3.5 * 3600.0                                   # seconds of path a tail shows
STEP = 120.0                                          # seconds between the points of a tail
PRE = 600.0                                           # a timetable dot appears this long before its departure
LINGER = 1500.0                                       # and stays this long after its arrival, fading
ARC_KM = 100.0                                        # long timetable legs are bent to the great circle every so often
AGES = np.arange(0.0, TAIL + 1.0, STEP)
_U = AGES / TAIL
RUN_SPAN = 1.0e6                                      # seconds between tracks in a combined time axis
LATE_S = 300.0                                        # a train this late glows red-gold
FRESH = 900.0                                         # live data older than this are not shown as live
DEDUP_LIVE, DEDUP_TT = 1.5, 3.0                       # LEDs: the same train from two feeds / live vs timetable


def _bayer(n):
    m = np.array([[0, 2], [3, 1]], np.float32)
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / (n * n)


BAYER = _bayer(8)

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


def _km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(math.radians(b[1] - a[1]))
    return EARTH * math.acos(max(-1.0, min(1.0, c)))


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


# ------------------------------------------------------------------ a set of trains on one time axis ---

class TrainSet:
    """Tracks (timetable runs or live trips) joined into one time axis, so one np.interp places them all.
    A track is (name, key, T unix seconds nondecreasing, X, Y LED coordinates, D delay seconds, real-time flag)."""

    def __init__(self, tracks):
        self.n = len(tracks)
        self.names = [t[0] for t in tracks]
        self.keys = [t[1] for t in tracks]
        self.rt = np.array([t[6] for t in tracks], bool)
        if not tracks:
            self.rs = self.re = self.warm = np.zeros(0)
            self.TT = self.XX = self.YY = self.DD = np.zeros(1)
            self.off = np.zeros(0)
            self.phase = np.zeros(0)
            self.nums = []
            return
        self.base = min(float(t[2][0]) for t in tracks)
        self.rs = np.array([t[2][0] for t in tracks], np.float64)
        self.re = np.array([t[2][-1] for t in tracks], np.float64)
        self.off = np.arange(self.n) * RUN_SPAN - self.base
        self.TT = np.concatenate([t[2] - self.base + i * RUN_SPAN for i, t in enumerate(tracks)])
        self.XX = np.concatenate([t[3] for t in tracks])
        self.YY = np.concatenate([t[4] for t in tracks])
        self.DD = np.concatenate([t[5] for t in tracks])
        # amber for trains heading south and east, teal for north and west
        self.warm = np.array([(t[4][-1] - t[4][0]) + 0.3 * (t[3][-1] - t[3][0]) >= 0 for t in tracks], bool)
        self.phase = (np.arange(self.n) * 0.6180339887) % 1.0
        self.nums = [_number(t[0]) for t in tracks]

    def active(self, unix):
        return np.nonzero((self.rs - PRE <= unix) & (unix <= self.re + TAIL + LINGER))[0]

    def at(self, idx, q):
        """x, y, delay of tracks idx at times q (unix, clipped to each track)."""
        qq = np.clip(q, self.rs[idx], self.re[idx]) + self.off[idx]
        return np.interp(qq, self.TT, self.XX), np.interp(qq, self.TT, self.YY), np.interp(qq, self.TT, self.DD)


def _number(name):
    m = re.findall(r"\d+", name or "")
    return m[-1] if m else ""


def _same_number(a, b):
    return len(a) >= 3 and len(b) >= 3 and (a == b or a.endswith(b) or b.endswith(a))


# ------------------------------------------------------------------ the timetable (offline, and the filler) ---

class Service:
    """One direction of one night train: its stops, and its path as LED coordinates with a time recipe."""
    __slots__ = ("name", "op", "days", "tz", "arr", "dep", "x", "y", "ia", "ib", "f", "idx")

    def __init__(self, s, idx):
        st = s["stops"]
        self.idx = idx
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


def run_times(svc, day):
    """The unix time at each point of the service's path, for the journey that set out on `day` (days since 1970)."""
    V = np.empty(2 * len(svc.tz))
    V[0::2] = to_utc(day, svc.arr, svc.tz)
    V[1::2] = to_utc(day, svc.dep, svc.tz)
    return np.maximum.accumulate((1.0 - svc.f) * V[svc.ia] + svc.f * V[svc.ib])


def timetable_set(services, d0, nice=False):
    """Every journey that could be on the move on UTC days d0 and d0+1: each service on its origin dates d0-2 .. d0+2.
    nice=True (on a side thread) sleeps a moment between services so that the frames keep the GIL."""
    tracks = []
    for svc in services:
        if nice:
            time.sleep(0.002)
        for day in range(d0 - 2, d0 + 3):
            if svc.days[(day + 3) % 7]:
                T = run_times(svc, day)
                tracks.append((svc.name, (svc.idx, day), T, svc.x, svc.y, np.zeros(len(T)), False))
    return TrainSet(tracks)


# ------------------------------------------------------------------ live: Transitous ---

API = "https://api.transitous.org/api/v6/map/trips"
UA = "fortuna-wall/1.0 (private art project)"
BOX = ("34,-11", "70,42")                    # min (lat,lon), max: all of the picture
PREC = 3                                     # polyline precision asked for (about 100 m)
NIGHT_NAME = re.compile(
    r"(?i)^(nj|en|icn|ir-n|euronight|nightjet|nattåg|nattog|snälltåget|snalltaget|sn[åa]|intercit\S* de nuit|"
    r"ic nuit|caledonian|european sleeper)\b|sleeper|nightjet|nattåg|nattog")
RAIL = ("NIGHT_RAIL", "LONG_DISTANCE", "HIGHSPEED_RAIL", "REGIONAL_FAST", "REGIONAL_RAIL")


def _unix(s):
    """'2026-10-29T20:05:00Z' (or with a +00:00 / fractions) -> unix seconds; None if it is not a time."""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)(?::(\d\d))?(?:\.\d+)?(Z|[+-]\d\d:?\d\d)?", s or "")
    if not m:
        return None
    y, mo, d, hh, mi, ss = (int(m.group(i) or 0) for i in range(1, 7))
    off = 0
    if m.group(7) and m.group(7) != "Z":
        sg = -1 if m.group(7)[0] == "-" else 1
        z = m.group(7)[1:].replace(":", "")
        off = sg * (int(z[:2]) * 3600 + int(z[2:]) * 60)
    return calendar.timegm((y, mo, d, hh, mi, ss)) - off


def decode_polyline(s, prec=PREC):
    """Google encoded polyline -> (lat, lon) arrays in degrees."""
    lat = lon = 0
    i, out = 0, []
    k = 10.0 ** prec
    while i < len(s):
        vals = []
        for _ in range(2):
            shift = res = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                res |= (b & 31) << shift
                shift += 5
                if b < 32:
                    break
            vals.append(~(res >> 1) if res & 1 else res >> 1)
        lat += vals[0]
        lon += vals[1]
        out.append((lat / k, lon / k))
    a = np.array(out, np.float64).reshape(-1, 2)
    return a[:, 0], a[:, 1]


def is_night(seg):
    """A raw API segment: is it a night train? The feed's NIGHT_RAIL mode, a night brand's name, or a long overnight run."""
    mode = seg.get("mode")
    if mode not in RAIL:
        return False
    if mode == "NIGHT_RAIL":
        return True
    name = (seg.get("trips") or [{}])[0].get("displayName", "")
    if NIGHT_NAME.search(name):
        return True
    d, a = _unix(seg.get("departure")), _unix(seg.get("arrival"))
    if d is None or a is None or mode not in ("LONG_DISTANCE", "REGIONAL_FAST") or a - d < 4 * 3600:
        return False
    lon = float(seg["from"].get("lon", 0.0))
    h0 = ((d + lon * 240.0) % 86400.0) / 3600.0               # local solar hour at the start
    span = (a - d) / 3600.0
    over = 0.0
    for lo, hi in ((1.0, 4.0), (25.0, 28.0)):                  # the hours 01..04, today or tomorrow
        over += max(0.0, min(h0 + span, hi) - max(h0, lo))
    return over >= 2.5


def compact(seg):
    """The raw API segment -> the small dict kept (and cached): enough to draw the train."""
    d, a = _unix(seg.get("departure")), _unix(seg.get("arrival"))
    sd, sa = _unix(seg.get("scheduledDeparture")), _unix(seg.get("scheduledArrival"))
    if d is None or a is None or a < d:
        return None
    t = (seg.get("trips") or [{}])[0]
    f, to = seg["from"], seg["to"]
    return {"id": t.get("tripId", ""), "n": t.get("displayName", ""), "d": d, "a": a,
            "sd": d if sd is None else sd, "sa": a if sa is None else sa, "rt": bool(seg.get("realTime")),
            "f": [round(f["lat"], 4), round(f["lon"], 4)], "t": [round(to["lat"], 4), round(to["lon"], 4)],
            "p": seg.get("polyline") or "", "pr": PREC}


def segments_to_set(segs, nice=False):
    """Compact segments -> a TrainSet with one track per trip: its segments' geometry laid end to end, timed
    linearly along each segment between its real-time ends, with the delay at each end."""
    by = {}
    for s in segs:
        by.setdefault(s["id"] or ("%s%s" % (s["n"], s["f"])), []).append(s)
    tracks = []
    for tid, ss in by.items():
        if nice:
            time.sleep(0.001)
        ss.sort(key=lambda s: (s["d"], s["a"]))
        Ts, Xs, Ys, Ds = [], [], [], []
        last = -1e18
        for s in ss:
            try:
                la, lo = decode_polyline(s["p"], s.get("pr", PREC)) if s["p"] else (np.zeros(0), np.zeros(0))
            except Exception:
                la, lo = np.zeros(0), np.zeros(0)
            if len(la) < 2:
                gl, gn = great_circle(s["f"], s["t"], max(2, int(_km(s["f"], s["t"]) / ARC_KM) + 1))
                la = np.concatenate([[s["f"][0]], gl, [s["t"][0]]])
                lo = np.concatenate([[s["f"][1]], gn, [s["t"][1]]])
            x, y = project(la, lo)
            seg_len = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
            fr = seg_len / seg_len[-1] if seg_len[-1] > 0 else np.linspace(0, 1, len(x))
            T = s["d"] + (s["a"] - s["d"]) * fr
            D = (s["d"] - s["sd"]) + ((s["a"] - s["sa"]) - (s["d"] - s["sd"])) * fr
            T = np.maximum(T, last)
            last = float(T[-1])
            Ts.append(T)
            Xs.append(x)
            Ys.append(y)
            Ds.append(D)
        T = np.maximum.accumulate(np.concatenate(Ts))
        if len(T) >= 2:
            tracks.append((ss[0]["n"], tid, T, np.concatenate(Xs), np.concatenate(Ys), np.concatenate(Ds),
                           any(s["rt"] for s in ss)))
    return TrainSet(tracks)


class LiveFeed:
    """The live layer: night-train segments from Transitous, fetched on a side thread, never blocking a frame."""

    def __init__(self, fetch=None, cache=CACHE, interval_night=180.0, interval_day=600.0):
        self.lock = threading.Lock()
        self.segs = {}                    # (id, d, a) -> compact segment
        self.set = TrainSet([])
        self.ok_time = 0.0                # when the last answer arrived (unix)
        self.err = ""
        self.cache = cache
        self.fetch = fetch or self._http
        self.interval_night, self.interval_day = interval_night, interval_day
        self.fail = 0
        self.next_try = 0.0
        self.last_draw = 0.0
        self.thread = None
        self.cache_saved = 0.0
        self.load_cache()

    # ---- the answer
    def ingest(self, raw, now, save=True, nice=False):
        """Take a raw /map/trips answer (a list of segments): keep the night trains, drop old ones, rebuild the set."""
        new = {}
        for seg in raw:
            try:
                if is_night(seg):
                    c = compact(seg)
                    if c:
                        new[(c["id"], c["d"], c["a"])] = c
            except Exception:
                continue
        with self.lock:
            segs = dict(self.segs)
        segs.update(new)
        segs = {k: v for k, v in segs.items() if v["a"] > now - 4 * 3600 and v["d"] < now + 3 * 3600}
        ts = segments_to_set(list(segs.values()), nice=nice)
        with self.lock:
            self.segs, self.set, self.ok_time, self.err = segs, ts, now, ""
        if save and now - self.cache_saved > 900:
            self.save_cache(now)
        return len(new)

    def snapshot(self):
        with self.lock:
            return self.set, self.ok_time

    def fresh(self, now):
        return self.ok_time > 0 and now - self.ok_time <= FRESH

    # ---- the cache file
    def load_cache(self):
        try:
            with open(self.cache) as fh:
                d = json.load(fh)
            segs = {(s["id"], s["d"], s["a"]): s for s in d["segs"]}
            ts = segments_to_set(list(segs.values()))
            self.segs, self.set, self.ok_time = segs, ts, float(d["fetched"])
        except Exception:
            pass

    def save_cache(self, now):
        try:
            tmp = self.cache + ".tmp"
            with self.lock:
                body = {"fetched": self.ok_time, "segs": list(self.segs.values())}
            with open(tmp, "w") as fh:
                json.dump(body, fh, separators=(",", ":"))
            os.replace(tmp, self.cache)
            self.cache_saved = now
        except Exception:
            pass

    # ---- the network
    def _http(self, start, end):
        import requests
        last = None
        for ver in ("v6", "v5"):
            r = requests.get(API.replace("v6", ver), params={
                "min": BOX[0], "max": BOX[1], "zoom": 4, "precision": PREC,
                "startTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)),
                "endTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end))},
                headers={"User-Agent": UA, "Accept-Encoding": "gzip"}, timeout=(8, 40))
            if r.status_code == 404:
                last = r
                continue
            if r.status_code == 429:
                raise RuntimeError("429 retry-after %s" % r.headers.get("Retry-After", "60"))
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                raise ValueError("unexpected answer")
            return data
        raise RuntimeError("HTTP %s" % (last.status_code if last is not None else "?"))

    def poll(self, now):
        """One fetch, in whatever thread calls it; on any failure the next try is pushed out (doubling, to 30 min)."""
        try:
            raw = self.fetch(now - 120, now + 480)
            self.ingest(raw, now, nice=True)
            self.fail = 0
            hour = (now // 3600) % 24
            night = hour >= 16 or hour <= 10
            self.next_try = now + (self.interval_night if night else self.interval_day)
        except Exception as e:
            self.fail += 1
            self.err = str(e)[:80]
            wait = min(1800.0, 60.0 * 2 ** min(self.fail, 5))
            m = re.search(r"retry-after (\d+)", self.err)
            if m:
                wait = max(wait, float(m.group(1)))
            self.next_try = now + wait

    def touch(self):
        """Called from frame(): note that frames are being drawn, and start the thread if it is not running."""
        self.last_draw = time.time()
        if self.thread is None or not self.thread.is_alive():
            with self.lock:
                if self.thread is None or not self.thread.is_alive():
                    self.thread = threading.Thread(target=self._run, name="nighttrains-live", daemon=True)
                    self.thread.start()

    def _run(self):
        while time.time() - self.last_draw < 120.0:
            now = _clock()
            if now >= self.next_try:
                self.poll(now)
            time.sleep(1.0)


# ------------------------------------------------------------------ the piece ---

RIDGES = [  # hand-placed ridge lines, (lat, lon): the tone of the mountains, not a survey
    [(43.9, 7.3), (44.4, 7.0), (45.2, 6.9), (45.9, 7.1), (46.3, 8.2), (46.5, 9.3), (46.6, 10.5), (46.8, 11.8),
     (47.0, 12.8), (47.3, 13.8), (47.5, 15.5)],                                          # Alps
    [(43.3, -1.8), (42.8, -0.5), (42.6, 0.9), (42.4, 2.2)],                              # Pyrenees
    [(49.1, 19.2), (49.3, 20.2), (49.1, 22.5), (48.5, 24.2), (47.7, 25.0), (46.5, 25.7), (45.6, 25.5),
     (45.4, 24.0), (45.3, 22.5), (44.7, 22.2)],                                          # Carpathians
    [(58.8, 6.5), (60.5, 7.5), (62.0, 8.5), (63.5, 10.5), (65.0, 13.5), (66.5, 15.5), (68.0, 17.5), (69.3, 19.5)],  # Scandes
    [(44.4, 8.8), (44.0, 10.8), (43.3, 12.6), (42.3, 13.6), (41.4, 14.7), (40.2, 15.6), (39.3, 16.3), (38.2, 15.9)],  # Apennines
    [(45.6, 14.5), (44.2, 16.5), (43.0, 18.5), (42.2, 19.5), (41.5, 20.5), (40.5, 21.0)],  # Dinaric Alps, Pindus
    [(43.1, 22.5), (42.8, 24.5), (42.9, 26.5), (42.8, 27.8)],                            # Balkan range
    [(36.7, 30.5), (37.0, 32.5), (37.5, 35.0)],                                          # Taurus
    [(57.5, -5.0), (56.8, -4.5)],                                                        # Highlands
]
SEAS = [(56, 3), (54.5, 0.5), (53.8, -4.8), (53, -9), (45.5, -4), (38, 5), (42, 15), (35.5, 18), (38, 24.5), (43.5, 34),
        (57, 19.5), (61.5, 20), (59.8, 25), (43.5, 15), (66, 5), (68, 12), (40.7, 28.2), (36, 12), (37, 0), (41.5, 29.5)]


def _load():
    """(services, cities, coast, error) from the assets; whatever is missing is left out and named in `error`."""
    services, cities, coast, err = [], [], [], ""
    try:
        with open(os.path.join(DATA, "services.json")) as fh:
            d = json.load(fh)
        for s in d["services"]:
            if len(s["stops"]) >= 2 and "1" in s["days"]:
                services.append(Service(s, len(services)))
        cities = d["cities"]
    except Exception as e:
        services, cities = [], []
        err = "services: %s" % str(e)[:80]
        print(f"[nighttrains] {err}", flush=True)
    try:
        with open(os.path.join(DATA, "europe.json")) as fh:
            coast = json.load(fh)["coast"]
    except Exception as e:
        print(f"[nighttrains] coast: {str(e)[:100]}", flush=True)
    return services, cities, coast, err


class NightTrains:
    def __init__(self, live=False, feed=None):
        from display import pixelfont
        self.font = pixelfont
        self.services, cities, coast, self.error = _load()
        self.coast_lines = coast
        self.cities = cities
        c = np.array([[c[1], c[2], c[3]] for c in cities], np.float64).reshape(-1, 3)
        self.c_lat, self.c_lon, pop = c[:, 0], c[:, 1], c[:, 2]
        cx, cy = project(self.c_lat, self.c_lon)
        self.c_px, self.c_py = np.round(cx).astype(int), np.round(cy).astype(int)
        self.c_size = np.clip(0.2 + 0.8 * np.log10(np.maximum(pop, 30.0) / 30.0) / np.log10(500.0), 0.0, 1.0)
        keep = (self.c_px >= 0) & (self.c_px < W) & (self.c_py >= 0) & (self.c_py < H)
        self.c_px, self.c_py, self.c_size, self.c_lat, self.c_lon = (a[keep] for a in (
            self.c_px, self.c_py, self.c_size, self.c_lat, self.c_lon))
        self.c_rand = np.random.RandomState(3).random_sample(len(self.c_px))
        self.c_phase = np.random.RandomState(4).random_sample(len(self.c_px)) * 6.283
        self.c_act = np.zeros(len(self.c_px))
        self.c_day = np.zeros(len(self.c_px))
        ys, xs = np.mgrid[0:H, 0:W]
        lat, lon = unproject(xs.astype(np.float64), ys.astype(np.float64))
        self.sin_lat, self.cos_lat, self.lon = np.sin(np.radians(lat)), np.cos(np.radians(lat)), np.radians(lon)
        self.bay = BAYER[ys % 8, xs % 8].astype(np.float32)
        self.noise = np.random.RandomState(7).random_sample((H, W)).astype(np.float32)
        self.zx, self.zy = (int(round(float(v))) for v in project(*HOME))
        self.still = self._still()
        self.sky, self.sky_t = None, -1e9
        self.tt, self.tt_day, self._tt_busy = None, None, False
        self.feed = feed if feed is not None else (LiveFeed() if live else None)
        self.live = live
        self.last = {}

    # ---------------------------------------------------------- the still layers
    def _still(self):
        """Land tone, mountains, route threads and Zurich's halo: computed once."""
        import cv2
        coast = np.zeros((H, W), np.uint8)
        for line in self.coast_lines:
            la, lo = np.array(line, np.float64).T
            x, y = project(la, lo)
            cv2.polylines(coast, [np.round(np.stack([x, y], 1)).astype(np.int32)], False, 1, 1, cv2.LINE_8)
        land = np.zeros((H, W), bool)
        if coast.any():
            fill = coast.copy()                                   # 1 = coast; the seas are flooded from seeds, 4-connected
            for la, lo in SEAS:
                px, py = (int(round(float(v))) for v in project(la, lo))
                if 0 <= px < W and 0 <= py < H and fill[py, px] == 0:
                    cv2.floodFill(fill, np.zeros((H + 2, W + 2), np.uint8), (px, py), 2, flags=4)
            land = fill != 2
        self.land = land
        img = np.zeros((H, W, 3), np.float32)
        thr = self.bay * 0.7 + self.noise * 0.3
        img[land & (thr < 0.17)] = LAND
        edge = (coast > 0) & (thr < 0.55)
        img[edge & (thr < 0.3)] = EDGE
        # mountains: closeness to a ridge line
        rm = np.zeros((H, W), np.uint8)
        for line in RIDGES:
            la, lo = np.array(line, np.float64).T
            x, y = project(la, lo)
            cv2.polylines(rm, [np.round(np.stack([x, y], 1)).astype(np.int32)], False, 1, 1, cv2.LINE_8)
        dist = cv2.distanceTransform((rm == 0).astype(np.uint8), cv2.DIST_L2, 3)
        rel = np.exp(-(dist / 3.2) ** 2)
        img[land & (rel * 0.4 > thr)] = RIDGE
        # routes: the faintest threads
        tm = np.zeros((H, W), np.uint8)
        for s in self.services:
            cv2.polylines(tm, [np.round(np.stack([s.x, s.y], 1)).astype(np.int32)], False, 1, 1, cv2.LINE_8)
        img[(tm > 0) & (thr < 0.3)] = THREAD
        # Zurich: a soft halo of gold points thinning outwards, and its own bright LED
        d = np.hypot(xs_ := np.arange(W)[None, :] - self.zx, ys_ := np.arange(H)[:, None] - self.zy)
        halo = np.clip(1.0 - d / 7.5, 0.0, 1.0) ** 1.6 * 0.75
        img[(halo > thr) & (d > 0.5)] = HALO
        img[self.zy, self.zx] = GOLD
        return img

    def _sky(self, unix):
        """The slow layer, redrawn every 30 s: the night side, the terminator, the cities' sleep."""
        dec, ra, gst = sun(unix)
        ha = gst + self.lon - ra
        sin_el = self.sin_lat * math.sin(dec) + self.cos_lat * math.cos(dec) * np.cos(ha)
        el = np.degrees(np.arcsin(np.clip(sin_el, -1, 1))).astype(np.float32)
        dens = np.interp(el, SKY_E, SKY_D).astype(np.float32)
        morning = (np.sin(ha) < 0)                                  # the sun is still east: dawn light
        dens = dens * np.where(morning, 1.0, 0.75).astype(np.float32)
        thr = self.bay * 0.8 + self.noise * 0.2
        lit = dens > thr
        col = np.stack([np.interp(el, SKY_E, SKY_C[:, k]) for k in range(3)], -1).astype(np.float32)
        sky = np.zeros((H, W, 3), np.float32)
        sky[lit] = col[lit]
        # cities: awake in the evening, asleep in the small hours (local solar time), pale by day
        sel = sun_elevation(unix, self.c_lat, self.c_lon)
        hour = ((unix / 3600.0 + self.c_lon / 15.0) % 24.0)
        act = np.interp(hour, [0, 2, 4, 5.5, 7, 9, 17, 18.5, 21, 23, 24], [0.45, 0.14, 0.06, 0.18, 0.5, 0.30, 0.30, 0.8, 1.0, 0.85, 0.45])
        self.c_act = act * (0.45 + 0.75 * self.c_size)
        self.c_day = np.clip((sel + 4.0) / 10.0, 0.0, 1.0)
        return sky

    # ---------------------------------------------------------- the timetable
    def _ensure_tt(self, unix):
        """The timetable set for the UTC day, built once at the start and then a day ahead on a thread."""
        d0 = int(unix // 86400)
        if self.tt is None:
            self.tt, self.tt_day = timetable_set(self.services, d0), d0
        elif d0 > self.tt_day and not self._tt_busy:
            self._tt_busy = True

            def work():
                try:
                    s = timetable_set(self.services, d0, nice=True)
                    self.tt, self.tt_day = s, d0
                finally:
                    self._tt_busy = False
            threading.Thread(target=work, name="nighttrains-tt", daemon=True).start()
        return self.tt

    # ---------------------------------------------------------- frames
    def _paint(self, img, ts, idx, unix, t, thr):
        """Tails and heads of tracks idx of set ts. Returns the head pixel positions."""
        if not len(idx):
            return
        flat = img.reshape(-1, 3)
        off = ts.off[idx]
        rs, re = ts.rs[idx], ts.re[idx]
        tau = unix - AGES[None, :]
        ri, ai = np.nonzero((tau >= rs[:, None]) & (tau <= re[:, None]))
        late = np.clip((self.delay_min[idx] - 4.0) / 25.0, 0.0, 1.0)
        warm = ts.warm[idx]
        if len(ri):
            q = unix - AGES[ai] + off[ri]
            x = np.round(np.interp(q, ts.TT, ts.XX)).astype(np.int64)
            y = np.round(np.interp(q, ts.TT, ts.YY)).astype(np.int64)
            ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
            x, y, ai, ri = x[ok], y[ok], ai[ok], ri[ok]
            u = _U[ai]
            lvl = (1.0 - u) ** 1.5
            show = lvl > thr[y, x]
            x, y, ai, ri, u, lvl = x[show], y[show], ai[show], ri[show], u[show], lvl[show]
            order = np.argsort(-ai, kind="stable")
            x, y, ri, u = x[order], y[order], ri[order], u[order]
            mix = np.clip(u * 1.25, 0.0, 1.0)[:, None] ** 0.8
            a_col = AMBER[1] * (1 - mix) + AMBER[2] * mix
            t_col = TEAL[1] * (1 - mix) + TEAL[2] * mix
            col = np.where(warm[ri][:, None], a_col, t_col)
            lr = late[ri][:, None] * (1.0 - np.clip(u, 0, 1))[:, None]
            col = col * (1 - lr) + (LATE * (1 - 0.45 * mix)) * lr
            flat[y * W + x] = col
        # heads
        hx, hy, hd = ts.at(idx, np.full(len(idx), unix))
        a = np.where(unix < rs, (unix - (rs - PRE)) / PRE, np.where(unix > re, 1.0 - (unix - re) / LINGER, 1.0))
        a = np.clip(a, 0.0, 1.0)
        pulse = 0.5 + 0.5 * np.sin(2 * math.pi * t * (0.5 + 1.5 * late) + ts.phase[idx] * 6.283)
        twink = 0.9 + 0.1 * np.sin(2 * math.pi * (t / 5.0 + ts.phase[idx]))
        px, py = np.round(hx).astype(np.int64), np.round(hy).astype(np.int64)
        ok = (px >= 1) & (px < W - 1) & (py >= 1) & (py < H - 1) & (a > 0.35)
        px, py, a, pulse, twink, late, warm = (v[ok] for v in (px, py, a, pulse, twink, late, warm))
        if len(px):
            hc = np.where(warm[:, None], AMBER[0], TEAL[0])
            mc = np.where(warm[:, None], AMBER[1], TEAL[1])
            core = hc * (0.8 + 0.2 * twink)[:, None]
            halo = mc * (0.55 + 0.25 * pulse * late)[:, None]
            g = (late * (0.4 + 0.5 * pulse))[:, None]                   # a late train glows red-gold and pulses
            core = np.maximum(core * (1 - g) + LATE * g, np.where(late[:, None] > 0, 120.0, 0.0))
            lh = (late[:, None] * (0.62 + 0.3 * pulse)[:, None])
            halo = halo * (1 - late[:, None]) + LATE * lh
            core, halo = core * a[:, None], halo * a[:, None]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                i = (py + dy) * W + px + dx
                flat[i] = np.maximum(flat[i], halo)
            flat[py * W + px] = core
        return px, py

    def _heads(self, ts, idx, unix):
        x, y, d = ts.at(idx, np.full(len(idx), unix))
        x2, y2, _ = ts.at(idx, np.full(len(idx), unix + 120.0))
        moving = (np.hypot(x2 - x, y2 - y) > 0.08) & (unix >= ts.rs[idx]) & (unix <= ts.re[idx])
        return x, y, d, moving

    def draw(self, t, unix):
        if self.sky is None or abs(unix - self.sky_t) > 30.0:
            self.sky, self.sky_t = self._sky(unix), unix
        img = np.maximum(self.still, self.sky)
        thr = (self.bay * 0.55 + ((self.noise + t * 0.17) % 1.0) * 0.45).astype(np.float32)
        self._cities(img, t)
        tt = self._ensure_tt(unix) if self.services else None
        live_n = tt_n = 0
        fresh = False
        self.delay_min = np.zeros(0)
        lts, lidx = None, np.zeros(0, int)
        lx = ly = np.zeros(0)
        if self.feed is not None:
            if self.live:
                self.feed.touch()
            lts, ok_time = self.feed.snapshot()
            fresh = ok_time > 0 and unix - ok_time <= FRESH
            if fresh and lts.n:
                lidx = lts.active(unix)
                # the same train from two feeds: draw it once (real-time ones first, then the longer)
                if len(lidx):
                    x, y, d, mv = self._heads(lts, lidx, unix)
                    order = np.lexsort((lidx, -(lts.re[lidx] - lts.rs[lidx]), ~lts.rt[lidx]))
                    D = (x[:, None] - x[None, :]) ** 2 + (y[:, None] - y[None, :]) ** 2 <= DEDUP_LIVE ** 2
                    gone = np.zeros(len(lidx), bool)
                    for k in order:                                        # the best of a group stays, the rest go
                        if not gone[k]:
                            gone |= D[k]
                            gone[k] = False
                    keep = np.nonzero(~gone)[0]
                    lidx, x, y, d, mv = lidx[keep], x[keep], y[keep], d[keep], mv[keep]
                    live_n = int(mv.sum())
                    lx, ly = x, y
        tidx = np.zeros(0, int)
        if tt is not None and tt.n:
            tidx = tt.active(unix)
            if len(tidx):
                x, y, d, mv = self._heads(tt, tidx, unix)
                drop = np.zeros(len(tidx), bool)
                if fresh and len(lidx):
                    drop = (((x[:, None] - lx[None, :]) ** 2 + (y[:, None] - ly[None, :]) ** 2) < DEDUP_TT ** 2).any(1)
                    by_tail = {}
                    for j in lidx:
                        if len(lts.nums[j]) >= 3:
                            by_tail.setdefault(lts.nums[j][-3:], []).append(lts.nums[j])
                    for k in np.nonzero(~drop)[0]:
                        num = tt.nums[tidx[k]]
                        if len(num) >= 3 and any(_same_number(num, m) for m in by_tail.get(num[-3:], ())):
                            drop[k] = True
                tidx, mv = tidx[~drop], mv[~drop]
                tt_n = int(mv.sum())
        # paint timetable first, live over it
        if len(tidx):
            self.delay_min = np.zeros(tt.n)
            self._paint(img, tt, tidx, unix, t, thr)
        if len(lidx):
            dm = np.zeros(lts.n)
            if lts.n:
                _, _, dd = lts.at(lidx, np.full(len(lidx), unix))
                dm[lidx] = dd / 60.0
            self.delay_min = dm
            self._paint(img, lts, lidx, unix, t, thr)
        self._label(img, fresh, live_n, tt_n)
        self.last = {"live": live_n, "timetable": tt_n, "fresh": fresh}
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")

    def _cities(self, img, t):
        """Warm points that breathe; the small ones go dark as their night deepens, the big ones keep an ember."""
        if not len(self.c_px):
            return
        breath = 0.5 + 0.5 * np.sin(t * 2 * math.pi / (7.0 + 5.0 * self.c_rand) + self.c_phase)
        lvl = self.c_act * (0.78 + 0.22 * breath)
        on = lvl > 0.3
        k = np.nonzero(on)[0]
        if not len(k):
            return
        f = np.clip((lvl[k] - 0.3) / 0.7, 0.0, 1.0)[:, None]
        night = CITY_EMBER + (CITY_WARM - CITY_EMBER) * f
        day = CITY_DAY * (0.8 + 0.2 * f)
        dw = self.c_day[k][:, None]
        col = night * (1 - dw) + day * dw
        x, y = self.c_px[k], self.c_py[k]
        img[y, x] = np.maximum(img[y, x], col)
        big = self.c_size[k] > 0.7                                   # the large ones have a soft shoulder
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            xb, yb = np.clip(x[big] + dx, 0, W - 1), np.clip(y[big] + dy, 0, H - 1)
            img[yb, xb] = np.maximum(img[yb, xb], col[big] * 0.5 + 8.0)

    def _label(self, img, fresh, live_n, tt_n):
        """The one small label in the corner: LIVE n (+filler), TIMETABLE, or NO DATA."""
        if fresh:
            self.font.draw(img, f"LIVE {live_n}", 2, 2, LABEL)
            if tt_n:                                                  # timetable trains the live layer lacks
                self.font.draw(img, f"TIMETABLE {tt_n}", 2, 8, LABEL2)
        elif self.services:
            self.font.draw(img, "TIMETABLE", 2, 2, LABEL)
        else:
            self.font.draw(img, "NO DATA", 2, 2, LABEL_WARN)
            self.font.draw(img, "NO DATA", W // 2 - 14, H // 2 - 2, LABEL_WARN)

    def __call__(self, t, now=None):
        return self.draw(t, _clock() if now is None else now)


_nt = None
_lock = threading.Lock()


def frame(t):
    global _nt
    if _nt is None:
        with _lock:
            if _nt is None:
                _nt = NightTrains(live=True)
    return _nt(t)


def thumb():
    """A still for the app, offline: the timetable at dawn over Zurich, the moment the sun there climbs through 3
    degrees below the horizon, when the night trains are arriving and the gold band crosses the map."""
    nt = NightTrains()
    day0 = int(_clock() // 86400) * 86400.0
    when = day0 + 5.5 * 3600
    for m in range(0, 24 * 60, 5):
        u = day0 + 3 * 3600 + m * 60
        if sun_elevation(u, HOME[0], HOME[1]) > -3.0:
            when = u
            break
    return nt(0.0, when)
