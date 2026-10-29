"""The ISS's day: the International Space Station's ground track drawing itself across a dim map of the
world. The station is one bright LED crawling along its real orbit (about 7.7 km a second: an LED every
13 seconds, a lap of the planet in 93 minutes); behind it the track it has just flown stays lit, fading
as it ages - gold for the orbit it is on now, then orange, rose and violet for the three before it - and
the older orbits of the last 24 hours stay as a dim dotted thread, so the day's 15 or 16 laps weave
themselves into the grid the Earth's turning gives them (each orbit lands 22.9 degrees west of the
last). A faint dotted ring round the station is the footprint it can see (everything above its horizon,
about 2,300 km from the station to the edge), and moves with it.

The map is plain latitude/longitude, cut in two and stacked so a world fits a portrait wall: the upper
strip is longitude 25 W to 155 E (the Atlantic, Africa, Europe, Asia, Australia), the lower strip 155 E
eastwards to 25 W (the Pacific and the Americas), from 58 N to 58 S, a degree and a bit (1.067) to the
LED. Read it like two lines of text: a track that leaves the right edge of the upper strip carries on
from the left edge of the lower one, and one that leaves the lower strip's right edge returns to the
upper strip's left. Only the coastlines are drawn, one LED wide: green-teal where the sun is up, blue
in the twilight (the sun between the horizon and 12 degrees below it) and dark navy at night, from
assets/maps/land_mask.png (Natural Earth 1:50m, public domain, built by tools/build_land.py). Where the sun is setting or rising the terminator is a dotted band across each
strip (dense from the sun on the horizon to 3 degrees below, sparser to 7): the sun is the real sun of
the moment. The station itself is warm white while the sun lights it and a cool lilac in the Earth's
shadow, which it enters and leaves every 45 minutes or so.

Zürich is the one dim LED of home. When the station is within 1,500 km of it a ring of light pulses
out from it, faster the closer the station gets, and in a paler gold when you could actually see the
station from the Rennweg (more than 10 degrees up, in sunlight, while the sky is dark).

What is real and what is reckoned. Nothing is invented, but nothing is a live GPS fix either: every
position is COMPUTED, from the station's public orbital elements (a "TLE": the US Space Force's, as
republished by CelesTrak, free to use) with the same propagator display/satellites.py uses (the 'sgp4'
package when it is installed, otherwise that module's built-in version of the same theory; the two
agree to under 1 km over two days). The track behind the station is not remembered, it is back-computed
from the same elements, so it is the orbit the station flew, within a few km, not a log of what some
receiver heard. Away from the elements' epoch the error grows: a few km a day normally, but several
hundred km a day after a reboost burn (the station raises its orbit every month or two), which old
elements cannot know about. So the age of the elements matters:

 * The elements are fetched every 8 hours on a side thread while the piece runs and kept in
   panel_setup/issday_cache.json (git-ignored with the other *_cache.json). The newest of that cache,
   panel_setup/satellites_cache.json (the satellites piece keeps a copy of the same ISS elements) and
   the bundled ones is used, so a restart or a dead network changes nothing.
 * With no cache at all the bundled elements are used: ISS (ZARYA), catalogue 25544, epoch
   2026-10-27 19:43 UTC (day 300.82187419 of 2026), fetched from CelesTrak's 'stations' group on
   2026-10-28. They are good for a few days; the older they get, the worse the positions.
 * Elements more than 2.5 days old: the whole track dims, step by step, to half brightness at 10 days
   old, and a small grey note says how old they are ("TLE 27 OCT": the elements' epoch), so the wall is
   honest that its positions are ageing. The piece never blanks: it draws on from the old elements.

Everything is drawn on whole LEDs (no anti-aliasing), one LED a sample: the track is a chain of single
LEDs on the map, not a line, so nothing shimmers.
"""
import json
import math
import os
import threading
import time

import numpy as np
from PIL import Image

import config
from display import satellites as sat

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "panel_setup", "issday_cache.json")
SAT_CACHE = sat.CACHE                                  # the satellites piece's cache holds the same ISS elements
MASK = os.path.join(ROOT, "assets", "maps", "land_mask.png")
URL = sat.URLS[1]                                      # CelesTrak 'stations': the ISS and its docked modules
NORAD = 25544
REFRESH = 8 * 3600.0                                   # CelesTrak asks for at most one fetch per 2 hours
RETRY = (600.0, 7200.0)                                # after a failure: 10 min, doubling to 2 h

# Bundled so a wall that has never been online still draws the right orbit (see the docstring: the
# positions drift as these age). Fetched from CelesTrak 'stations' on 2026-10-28; epoch 2026-10-27 19:43 UTC.
BUNDLED = ("ISS (ZARYA)",
           "1 25544U 98067A   26300.82187419  .00005456  00000+0  10681-3 0  9999",
           "2 25544  51.6336   3.7485 0007015 317.3678  42.6766 15.49080514592319")

HOME = sat.HOME                                        # Rennweg, Zürich: lat, lon, km above the sea
NEAR_KM = 1500.0                                       # the station this close: Zürich pulses
STALE_FROM, STALE_HALF = 2.5, 10.0                     # days: dimming starts, half brightness
HISTORY = 24 * 3600.0                                  # the track kept lit: the last day
STEP = 12.0                                            # seconds between track samples (< one LED apart)
REBUILD = 20.0                                         # seconds between redrawing the map under the track (the sun)

# the map: plain lat/lon, two strips of 180 degrees of longitude one above the other
PPD = W / 180.0                                        # LEDs per degree
L0 = -25.0                                             # longitude at the left of the upper strip
LAT_TOP = 58.0                                         # strips run from 58 N to 58 S
ROWS = int(round(2 * LAT_TOP * PPD))                   # 124 LEDs tall
Y0 = ((H - 2 * ROWS - 4) // 2, (H - 2 * ROWS - 4) // 2 + ROWS + 4)       # top row of the upper, lower strip

# colours: the wall shows nothing below ~94 in a channel and only ~5 steps above it (94 149 188 219 245),
# so every colour keeps its lit channels at or above 100 and a channel that is not meant to show is 0. The in-between
# tones of the gradients (the twilight, the night side) are made by ORDERED DITHERING: a fixed Bayer matrix decides which
# LEDs of an area are lit, so a soft gradient is a denser or sparser field of whole LEDs and never a dimmed one.
SEA_DAY = np.array([0, 104, 150], np.float32)          # specks of the sunlit sea
SEA_NIGHT = np.array([0, 0, 108], np.float32)          # ... and of the night's
LAND_DAY = np.array([0, 150, 112], np.float32)         # sunlit land
LAND_NIGHT = np.array([0, 0, 132], np.float32)         # land in the dark
DUSK = np.array([200, 100, 138], np.float32)           # the twilight band: rose, warming to amber at the sun's edge
DUSK_EDGE = np.array([255, 168, 100], np.float32)      # the line of sunrise and sunset itself
LIGHTS = np.array([236, 156, 0], np.float32)           # the cities of the night side
LIGHTS_BIG = np.array([255, 206, 96], np.float32)
COAST_DAY = np.array([0, 150, 122], np.float32)        # the coast where the sun is up
COAST_DUSK = np.array([196, 104, 150], np.float32)     # ... where it is rising or setting
COAST_NIGHT = np.array([0, 0, 150], np.float32)        # ... and in the night
GRAT = np.array([0, 0, 112], np.float32)               # the graticule, very faint
FOOT = np.array([0, 124, 176], np.float32)             # the footprint ring
HEAD_SUN = np.array([255, 250, 228], np.float32)
HEAD_SHADOW = np.array([176, 168, 255], np.float32)
HOME_LED = np.array([196, 188, 176], np.float32)
PULSE = np.array([255, 196, 84], np.float32)
PULSE_SEEN = np.array([255, 245, 210], np.float32)
NOTE = np.array([108, 108, 120], np.float32)
# track colour by age, in orbits (the track's age over the period): just behind the head to a day ago
AGE_ORBITS = np.array([0.0, 0.06, 0.5, 1.0, 2.0, 3.0, 4.5, 6.5], np.float32)
AGE_COLS = np.array([(255, 238, 170), (255, 212, 110), (255, 178, 80), (255, 126, 90), (236, 84, 128),
                     (170, 70, 200), (120, 40, 196), (100, 0, 150)], np.float32)
AGE_DENS = np.array([1.0, 1.0, 0.96, 0.88, 0.66, 0.46, 0.34, 0.26], np.float32)     # share of the samples kept (ordered)
OLD_FROM = 3.0                                         # beyond three orbits old the thread is a fine dotted hair
ECC2 = 0.00669438                                      # WGS-84 eccentricity squared (geocentric -> geodetic lat)


def shade(col, f):
    """col * f, but a channel that falls under the wall's dimmest visible step drops out and the brightest
    channel never goes below it: a dimmed amber turns red, a dimmed violet a deep blue, then they go dark
    (one colour, or rows of them)."""
    c = np.asarray(col, np.float32) * f
    top = c.max(axis=-1, keepdims=True)
    return np.where(c >= 94.0, c, np.where((c >= top) & (top >= 40.0), 100.0, 0.0)).astype(np.float32)


def _bayer(n):
    m = np.zeros((1, 1))
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return ((m + 0.5) / (n * n)).astype(np.float32)


BAYER = np.tile(_bayer(16), (H // 16 + 1, W // 16 + 1))[:H, :W]                       # an ordered threshold per LED
NOISE = np.random.RandomState(11).random_sample((H, W)).astype(np.float32)          # a second, unrelated one
JIT = 0.75 * BAYER + 0.25 * NOISE                                                    # ordered with a little jitter: no visible lattice

# the cities whose lights show on the night side (lat, lon, size 1-3): the world's big conurbations, drawn as a few
# LEDs each. Zürich is left out: it is the marker of home. Decoration of the dark, not data.
CITIES = [
    (40.7, -74.0, 3), (42.4, -71.1, 2), (38.9, -77.0, 2), (41.9, -87.6, 3), (34.1, -118.2, 3), (37.8, -122.4, 2),
    (29.8, -95.4, 2), (33.7, -84.4, 2), (25.8, -80.2, 2), (32.8, -96.8, 2), (47.6, -122.3, 1), (39.7, -105.0, 1),
    (45.5, -73.6, 2), (43.7, -79.4, 2), (19.4, -99.1, 3), (4.7, -74.1, 2), (-12.0, -77.0, 2), (-23.5, -46.6, 3),
    (-22.9, -43.2, 3), (-34.6, -58.4, 3), (-33.5, -70.7, 2), (-15.8, -47.9, 1), (10.5, -66.9, 2), (-3.1, -60.0, 1),
    (51.5, -0.1, 3), (48.9, 2.35, 3), (52.5, 13.4, 2), (50.1, 8.7, 2), (50.9, 6.9, 2), (52.4, 4.9, 2), (50.8, 4.4, 2),
    (45.5, 9.2, 2), (41.9, 12.5, 2), (40.4, -3.7, 2), (41.4, 2.2, 2), (38.7, -9.1, 1), (48.2, 16.4, 1), (52.2, 21.0, 2),
    (47.5, 19.0, 1), (44.4, 26.1, 1), (59.9, 30.3, 1), (55.8, 37.6, 3), (50.5, 30.5, 1), (41.0, 29.0, 3),
    (39.9, 32.9, 1), (37.97, 23.7, 1), (30.0, 31.2, 3), (36.8, 10.2, 1), (33.6, -7.6, 1), (6.5, 3.4, 3),
    (9.0, 38.7, 1), (-1.3, 36.8, 1), (-26.2, 28.0, 2), (-33.9, 18.4, 1), (-4.3, 15.3, 2), (-8.8, 13.2, 1),
    (33.3, 44.4, 2), (35.7, 51.4, 2), (24.7, 46.7, 1), (25.2, 55.3, 1), (24.9, 67.0, 2), (31.5, 74.3, 2),
    (28.6, 77.2, 3), (19.1, 72.9, 3), (13.1, 80.3, 2), (22.6, 88.4, 3), (23.8, 90.4, 3), (12.97, 77.6, 2),
    (17.4, 78.5, 2), (39.9, 116.4, 3), (31.2, 121.5, 3), (23.1, 113.3, 3), (22.3, 114.2, 2), (30.6, 104.1, 2),
    (30.6, 114.3, 2), (37.6, 127.0, 3), (35.7, 139.7, 3), (34.7, 135.5, 3), (35.2, 136.9, 2), (25.0, 121.5, 2),
    (14.6, 121.0, 3), (10.8, 106.7, 2), (13.8, 100.5, 2), (1.35, 103.8, 2), (-6.2, 106.8, 3), (-7.3, 112.7, 2),
    (3.1, 101.7, 2), (-33.9, 151.2, 2), (-37.8, 145.0, 2), (-27.5, 153.0, 1), (-31.95, 115.9, 1), (-36.85, 174.8, 1),
    (21.3, -157.9, 1), (23.1, -82.4, 1), (18.5, -69.9, 1), (-0.2, -78.5, 1), (-16.5, -68.1, 1), (-34.9, -56.2, 1),
]


def city_lights():
    """(H, W) uint8: 0 dark, 1 a dim light, 2 a bright one: the cities as LEDs with a scatter round the big ones."""
    rng = np.random.RandomState(5)
    out = np.zeros((H, W), np.uint8)
    for lat, lon, size in CITIES:
        x, y, inside = to_led(lat, lon)
        if not inside[0]:
            continue
        x, y = int(x[0]), int(y[0])
        out[y, x] = 2 if size >= 2 else 1
        for _ in range(size * 2 + 1):
            dx, dy = rng.randint(-size, size + 1), rng.randint(-size, size + 1)
            if 0 <= x + dx < W and 0 <= y + dy < H and out[y + dy, x + dx] == 0:
                out[y + dy, x + dx] = 1
    return out


# ------------------------------------------------------------------ orbit ---

def tle_age_days(tle, now):
    return (now - sat.tle_epoch(tle[1])) / 86400.0


def tle_note(tle):
    """'27 OCT': the date of the elements, in letters the 3x5 font has."""
    e = time.gmtime(sat.tle_epoch(tle[1]))
    return "%d %s" % (e.tm_mday, "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()[e.tm_mon - 1])


def positions(prop, times):
    """Geodetic latitude/longitude (degrees), altitude (km), 'in sunlight', 'usable' and the inertial
    vector (km) of the ISS at each unix time in the array. The propagator is display/satellites.py's, asked
    for one satellite at many times (its Fallback broadcasts over time; the sgp4 package takes arrays)."""
    times = np.atleast_1d(np.asarray(times, np.float64))
    j = times / 86400.0 + 2440587.5
    if isinstance(prop, sat.WithSGP4):
        whole = np.floor(j - 0.5) + 0.5
        _, r, _ = prop.arr.sgp4(whole, j - whole)
        r = r[0]
    else:
        r = prop(times)[0]
    g = sat.gmst(j)
    c, s = np.cos(g), np.sin(g)
    x, y, z = c * r[:, 0] + s * r[:, 1], -s * r[:, 0] + c * r[:, 1], r[:, 2]     # inertial -> Earth-fixed
    rad = np.sqrt(x * x + y * y + z * z)
    lat = np.degrees(np.arctan(np.tan(np.arctan2(z, np.hypot(x, y))) / (1.0 - ECC2)))
    lon = np.degrees(np.arctan2(y, x))
    node = np.arange(0, len(j), max(1, len(j) // 100))                    # the sun moves 0.04 deg a minute:
    if node[-1] != len(j) - 1:                                            # a coarse series is plenty
        node = np.append(node, len(j) - 1)
    ser = np.array([sat.sun_eci(j[k]) for k in node])
    sun = np.stack([np.interp(np.arange(len(j)), node, ser[:, k]) for k in range(3)], 1)
    along = np.einsum("ij,ij->i", r, sun)
    lit = (along > 0) | (np.linalg.norm(r - along[:, None] * sun, axis=1) > sat.RE)
    ok = np.isfinite(rad) & (rad > 6500.0) & (rad < 7300.0)
    return lat, lon, rad - 6371.0, lit, ok, r


def to_led(lat, lon):
    """Latitude/longitude (degrees) -> the LED's column and row on the stacked map, and whether the point
    is inside the map (the strips stop at 58 degrees north and south). Arrays in, arrays out."""
    lat, lon = np.atleast_1d(np.asarray(lat, np.float64)), np.atleast_1d(np.asarray(lon, np.float64))
    u = np.mod(lon - L0, 360.0)
    strip = (u // 180.0).astype(np.int64)
    x = np.minimum(((u - 180.0 * strip) * PPD).astype(np.int64), W - 1)
    row = np.floor((LAT_TOP - lat) * PPD).astype(np.int64)
    inside = (row >= 0) & (row < ROWS)
    y = np.take(np.array(Y0), strip) + np.clip(row, 0, ROWS - 1)
    return x, y, inside


def ground_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def footprint(lat, lon, alt, n=96):
    """The ring on the ground at the station's horizon (elevation 0): n points, degrees."""
    rho = math.acos(6371.0 / (6371.0 + max(alt, 1.0)))
    p, l = math.radians(lat), math.radians(lon)
    th = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    p2 = np.arcsin(math.sin(p) * math.cos(rho) + math.cos(p) * math.sin(rho) * np.cos(th))
    l2 = l + np.arctan2(np.sin(th) * math.sin(rho) * math.cos(p), math.cos(rho) - math.sin(p) * np.sin(p2))
    return np.degrees(p2), np.degrees(l2)


# ------------------------------------------------------------------ the map ---

def land_strips():
    """(land, coast) boolean arrays (H, W): the land mask resampled onto the two strips (area-averaged, land
    where at least half the LED is), and the LEDs on its edge, where land meets sea (one LED wide)."""
    import cv2
    try:
        m = np.asarray(Image.open(MASK).convert("L"), np.float32) / 255.0          # 720 x 360, row 0 = 90 N
    except Exception:
        return np.zeros((H, W), bool), np.zeros((H, W), bool)
    per = m.shape[1] / 360.0
    r0, r1 = int(round((90.0 - LAT_TOP) * per)), int(round((90.0 + LAT_TOP) * per))
    m = np.roll(m[r0:r1], -int(round((L0 + 180.0) * per)), axis=1)                   # column 0 = L0
    flat = cv2.resize(m, (int(round(360.0 * PPD)), ROWS), interpolation=cv2.INTER_AREA) >= 0.5     # 384 x 124
    up = np.pad(flat, ((1, 1), (0, 0)), mode="edge")
    inner = flat & up[:-2] & up[2:] & np.roll(flat, 1, 1) & np.roll(flat, -1, 1)
    coast = flat & ~inner
    land, edge = np.zeros((H, W), bool), np.zeros((H, W), bool)
    for s in (0, 1):
        land[Y0[s]:Y0[s] + ROWS] = flat[:, s * W:(s + 1) * W]
        edge[Y0[s]:Y0[s] + ROWS] = coast[:, s * W:(s + 1) * W]
    return land, edge


class Geo:
    """Latitude and longitude of every LED of the map (precomputed once), and the sun's height there."""

    def __init__(self):
        self.mapped = np.zeros((H, W), bool)
        rows = np.arange(ROWS)
        lat = np.radians(LAT_TOP - (rows + 0.5) / PPD)
        self.sin_lat, self.cos_lat = np.sin(lat)[None, :, None], np.cos(lat)[None, :, None]
        lon = np.radians(L0 + 180.0 * np.arange(2)[:, None] + (np.arange(W)[None, :] + 0.5) / PPD)
        self.lon = lon[:, None, :]                                                   # (2, 1, W)
        for s in (0, 1):
            self.mapped[Y0[s]:Y0[s] + ROWS] = True

    def sun_height(self, sun_lat, sun_lon):
        """The sun's elevation in degrees at every LED, as (H, W) (zero off the map)."""
        s = (self.sin_lat * math.sin(sun_lat) + self.cos_lat * math.cos(sun_lat) * np.cos(self.lon - sun_lon))
        out = np.zeros((H, W), np.float32)
        deg = np.degrees(np.arcsin(np.clip(s, -1.0, 1.0)))
        for k in (0, 1):
            out[Y0[k]:Y0[k] + ROWS] = deg[k]
        return out


# ------------------------------------------------------------------ the piece ---

class ISSDay:
    def __init__(self, fetch=True):
        from display import pixelfont
        self.font = pixelfont
        self.tle, self.source, self.prop, self.period = None, "", None, 5574.0
        self.land, self.coast = land_strips()
        self.geo = Geo()
        ys, xs = np.mgrid[0:H, 0:W]
        self.chequer = (xs + ys) % 2 == 0
        self.sparse = (xs % 2 == 0) & (ys % 2 == 0)
        self.cy, self.cx = np.nonzero(self.coast)
        self.lights = city_lights()
        self.grat = self._graticule()
        self.bias = (self.land & ~self.coast)
        self.sky, self.sky_t = None, -1e9                  # the map under the track (coasts, terminator)
        self.track = None                                  # (times, x, y, last time) of the last day's orbit
        self.fetched = 0.0
        self._cfg, self._cfg_seen = None, None
        self._use(self._best(time.time()))
        if fetch:
            threading.Thread(target=self._fetch_loop, daemon=True).start()

    # ---------------------------------------------------------- data
    @staticmethod
    def _read(path):
        """(tle, fetched at) of the ISS in a cache file, or None."""
        try:
            with open(path) as fh:
                c = json.load(fh)
            for x in c["tle"]:
                try:
                    if int(x[1][2:7]) == NORAD:
                        return tuple(x), float(c.get("fetched", 0.0))
                except (ValueError, IndexError):
                    continue
        except Exception:
            pass
        return None

    def _best(self, now):
        """(tle, source): the newest elements of the bundled ones, our cache and the satellites piece's."""
        cands = [(BUNDLED, "bundled")]
        for path, name in ((CACHE, "cache"), (SAT_CACHE, "satellites cache")):
            got = self._read(path)
            if got:
                cands.append((got[0], name))
        ok = []
        for tle, name in cands:
            try:
                e = sat.tle_epoch(tle[1])
                if e < now + 2 * 86400.0 and self._sane(tle, e):   # a future epoch is a damaged file
                    ok.append((e, tle, name))
            except Exception:
                continue
        if not ok:
            return BUNDLED, "bundled"
        e, tle, name = max(ok, key=lambda c: c[0])
        return tle, name

    @staticmethod
    def _sane(tle, e):
        """True when the elements propagate to an ISS-like orbit: finite, 340-460 km up, about 7.66 km/s.
        A damaged cache line that still parses must not be taken just because its epoch is newest."""
        try:
            n = float(tle[2][52:63])
            if not 15.0 < n < 16.2:
                return False
            prop = sat.propagator([tle])
            t = e + np.array([0.0, 10.0, 1500.0, 3000.0, 4500.0])
            _, _, alt, _, ok, r = positions(prop, t)
            if not (np.all(np.isfinite(r)) and np.all(np.isfinite(alt)) and np.all(ok)):
                return False
            if np.any(alt < 340.0) or np.any(alt > 460.0):
                return False
            v = float(np.linalg.norm(r[1] - r[0])) / 10.0
            return 7.4 < v < 7.9
        except Exception:
            return False

    def _use(self, pick):
        tle, source = pick
        if self.tle is not None and tle[1:] == self.tle[1:]:
            self.source = source
            return
        prop = sat.propagator([tle])
        period = 86400.0 / float(tle[2][52:63])             # seconds an orbit takes
        self.source = source
        self.tle, self.period, self.prop = tle, period, prop
        self._cfg = (tle, prop, period)                    # ONE reference: the frame thread reads only this

    def _fetch_loop(self):
        import requests
        wait = RETRY[0]
        while True:
            try:
                self._use(self._best(time.time()))
                for path in (CACHE, SAT_CACHE):               # someone fetched these recently: no need to
                    got = self._read(path)
                    if got:
                        self.fetched = max(self.fetched, got[1])
                if self.fetched and time.time() - self.fetched < REFRESH:
                    time.sleep(900.0)
                    continue
                r = requests.get(URL, timeout=30, headers={"User-Agent": "magic-mirror-wall/1.0"})
                r.raise_for_status()
                got = [x for x in sat.parse_tle(r.text) if int(x[1][2:7]) == NORAD]
                if not got:
                    raise ValueError("no ISS in the answer")
                tle = got[0]
                if abs(time.time() - sat.tle_epoch(tle[1])) > 30 * 86400:
                    raise ValueError("elements too old")
                if not self._sane(tle, sat.tle_epoch(tle[1])):
                    raise ValueError("elements implausible")
                self.fetched = time.time()
                tmp = CACHE + ".tmp"
                with open(tmp, "w") as fh:
                    json.dump({"fetched": self.fetched, "tle": [tle]}, fh)
                os.replace(tmp, CACHE)
                self._use((tle, "live"))
                wait = RETRY[0]
            except Exception as e:
                print(f"[issday] {str(e)[:100]}", flush=True)
                time.sleep(wait)
                wait = min(wait * 2, RETRY[1])

    # ---------------------------------------------------------- layers
    def _sun(self, unix):
        """The sun's sub-point: latitude and longitude, radians."""
        j = sat.jd(unix)
        s = sat.sun_eci(j)
        return math.asin(max(-1.0, min(1.0, s[2]))), math.atan2(s[1], s[0]) - float(sat.gmst(j))

    def _graticule(self):
        """A very faint dotted graticule: every 30 degrees of latitude and longitude, a dot every 8 LEDs."""
        g = np.zeros((H, W), bool)
        for s_ in (0, 1):
            for lat in range(-30, 31, 30):
                y = Y0[s_] + int((LAT_TOP - lat) * PPD)
                if Y0[s_] <= y < Y0[s_] + ROWS:
                    g[y, 3::8] = True
            lon0 = L0 + 180.0 * s_
            for lon in range(int(math.ceil(lon0 / 30.0)) * 30, int(lon0 + 180), 30):
                x = int((lon - lon0) * PPD)
                if 0 <= x < W:
                    g[Y0[s_] + 3:Y0[s_] + ROWS:8, x] = True
        return g

    @staticmethod
    def _sstep(x, a, b):
        t = np.clip((x - a) / (b - a), 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    def _sky(self, unix):
        """The map under the track, redrawn every 20 s, all in ordered dither: the sea and land as fields of whole LEDs that
        thin out into the night, a rose twilight band that warms to amber at the terminator itself, the coasts coloured by
        the sun's height, and on the dark side the dim lights of the cities."""
        lat, lon = self._sun(unix)
        h = self.geo.sun_height(lat, lon)
        m = self.geo.mapped
        img = np.zeros((H, W, 3), np.uint8)
        sst = self._sstep
        w_day = sst(h, -3.0, 7.0)                                   # 1 in full day, 0 once the sun is well down
        w_nig = 1.0 - sst(h, -15.0, -5.0)                           # 1 in the night proper
        band = np.exp(-((h + 3.0) / 3.6) ** 2)                      # the twilight band, centred 3 degrees below the horizon
        edge = np.exp(-(h / 0.9) ** 2)                              # the terminator itself, a thread of amber
        sea = m & ~self.land
        land = m & self.land
        # which kind of speck each LED would be (decided by the unrelated noise, so the mix is a soft blend)
        n = NOISE
        is_dusk = n < band * 0.75
        is_day = ~is_dusk & (((n - band * 0.75) / np.maximum(1e-3, 1.0 - band * 0.75)) < w_day)
        d_sea = np.interp(h, [-18, -6, 0, 8], [0.030, 0.050, 0.100, 0.150]) + 0.25 * band
        d_land = np.interp(h, [-18, -6, 0, 8], [0.07, 0.10, 0.20, 0.27]) + 0.14 * band
        lit_sea = sea & (JIT < d_sea)
        lit_land = land & ~self.coast & (JIT < d_land)
        img[lit_sea & ~is_dusk & ~is_day] = SEA_NIGHT
        img[lit_sea & is_day] = SEA_DAY
        img[lit_sea & is_dusk] = DUSK
        img[lit_land & ~is_dusk & ~is_day] = LAND_NIGHT
        img[lit_land & is_day] = LAND_DAY
        img[lit_land & is_dusk] = DUSK
        # a very faint graticule on the dark parts
        gm = self.grat & m & (img.max(-1) == 0) & (BAYER < 0.75)
        img[gm] = GRAT
        # the cities, as the night comes on
        ramp = np.clip((-5.0 - h) / 7.0, 0.0, 1.0)
        city = (self.lights > 0) & (BAYER < 0.35 + 0.65 * ramp) & (ramp > 0.0)
        img[city & (self.lights == 1)] = LIGHTS
        img[city & (self.lights == 2)] = LIGHTS_BIG
        # the terminator: a hair of amber where the sun stands on the horizon
        te = m & (edge > 0.62) & (BAYER < 0.6)
        img[te] = DUSK_EDGE
        # the coasts: a hair-thin line, its colour the colour of the light it lies in
        ch = h[self.cy, self.cx]
        cn = NOISE[self.cy, self.cx]
        wd, bd = w_day[self.cy, self.cx], band[self.cy, self.cx]
        col = np.where((cn < bd * 0.9)[:, None], COAST_DUSK,
                       np.where((((cn - bd * 0.9) / np.maximum(1e-3, 1.0 - bd * 0.9)) < wd)[:, None], COAST_DAY, COAST_NIGHT))
        keep = JIT[self.cy, self.cx] < 0.9
        img[self.cy[keep], self.cx[keep]] = col[keep].astype(np.uint8)
        return img

    def _track(self, unix, prop):
        """The orbit of the last day as LEDs, one sample every 12 s on a fixed grid of times: (times, x, y,
        last time), oldest first. Built whole the first time (a few ms), then each new sample is added as its
        time comes and the ones older than a day dropped, so a frame costs next to nothing."""
        grid = math.floor(unix / STEP) * STEP
        tr = self.track
        if tr is None or not (0.0 <= grid - tr[3] <= 300.0):
            t = grid - HISTORY + STEP * np.arange(int(HISTORY / STEP) + 1)
            tt, tx, ty = np.zeros(0), np.zeros(0, np.int64), np.zeros(0, np.int64)
        elif grid == tr[3]:
            return tr
        else:
            t = tr[3] + STEP * np.arange(1, int(round((grid - tr[3]) / STEP)) + 1)
            tt, tx, ty = tr[:3]
        lat, lon, _, _, ok, _ = positions(prop, t)
        x, y, inside = to_led(lat, lon)
        keep = ok & inside
        tt, tx, ty = np.concatenate([tt, t[keep]]), np.concatenate([tx, x[keep]]), np.concatenate([ty, y[keep]])
        fresh = tt >= grid - HISTORY
        return tt[fresh], tx[fresh], ty[fresh], grid

    def _factor(self, unix, tle):
        """How bright the elements' age lets the track be: 1 until 2.5 days old, half at 10, a third after."""
        d = tle_age_days(tle, unix)
        return float(np.interp(abs(d), [STALE_FROM, STALE_HALF, 30.0], [1.0, 0.5, 0.33]))

    # ---------------------------------------------------------- frames
    def __call__(self, t, now=None):
        unix = time.time() if now is None else now
        cfg = self._cfg                                    # one snapshot of the elements for the whole frame
        tle, prop, period = cfg
        if cfg is not self._cfg_seen:                      # new elements: restart the caches (frame thread only)
            self.sky, self.sky_t, self.track, self._cfg_seen = None, -1e9, None, cfg
        sky = self.sky
        if sky is None or abs(unix - self.sky_t) > REBUILD:
            sky = self.sky = self._sky(unix)
            self.sky_t = unix
        track = self.track = self._track(unix, prop)
        img = sky.copy()
        f = self._factor(unix, tle)
        tt, tx, ty = track[:3]                        # oldest first, so a crossing LED takes the newest colour
        if len(tt):
            age = (unix - tt) / period
            col = np.stack([np.interp(age, AGE_ORBITS, AGE_COLS[:, k]) for k in range(3)], 1)
            dens = np.interp(age, AGE_ORBITS, AGE_DENS)
            keep = JIT[ty, tx] < dens                 # the thread thins with age: ordered, so it never twinkles
            keep &= (age < OLD_FROM) | (np.round(tt / STEP).astype(np.int64) % 2 == 0)
            c = shade(col, f * (1.0 - 0.18 * np.clip(age / 6.5, 0.0, 1.0))[:, None])
            img[ty[keep], tx[keep]] = np.clip(c[keep], 0, 255).astype(np.uint8)
            fresh = keep & (age < 0.045)              # the newest stretch swells, two LEDs wide: a comet's tail
            if fresh.any():
                wx, wy = np.minimum(tx[fresh] + 1, W - 1), ty[fresh]
                img[wy, wx] = np.maximum(img[wy, wx], np.clip(shade(col[fresh], 0.55 * f), 0, 255).astype(np.uint8))
        # the station
        lat, lon, alt, lit, ok, r = positions(prop, np.array([unix]))
        lat, lon, alt, lit, ok = float(lat[0]), float(lon[0]), float(alt[0]), bool(lit[0]), bool(ok[0])
        if ok:
            self._footprint(img, unix, lat, lon, alt, f)
        self._home(img, unix, lat, lon, r[0] if ok else None, ok)
        if ok:
            hx, hy, hin = to_led(lat, lon)
            if hin[0]:
                self._station(img, unix, int(hx[0]), int(hy[0]), lit, f)
        if tle_age_days(tle, unix) > STALE_FROM:
            self.font.draw(img, "TLE " + tle_note(tle), 2, Y0[1] + ROWS - 6, NOTE)
        return Image.fromarray(img, "RGB")

    @staticmethod
    def _ring(img, cx, cy, rx, ry, col, dens, n=None, phase=0.0):
        """A ring of whole LEDs (radii in LEDs), each kept when the ordered threshold under it is below `dens`."""
        n = n or max(16, int(max(rx, ry) * 8))
        a = np.linspace(0.0, 2 * math.pi, n, endpoint=False) + phase
        px = np.round(cx + rx * np.cos(a)).astype(int)
        py = np.round(cy + ry * np.sin(a)).astype(int)
        ok = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        px, py = px[ok], py[ok]
        k = BAYER[py, px] < dens
        img[py[k], px[k]] = np.maximum(img[py[k], px[k]], np.clip(col, 0, 255).astype(np.uint8))

    def _footprint(self, img, unix, lat, lon, alt, f):
        """The station's horizon, a dotted ring that breathes (its density swells and ebbs on a 7 s beat), and a second, fainter
        ring that opens out from the station and fades before it reaches the horizon."""
        fp_lat, fp_lon = footprint(lat, lon, alt, 120)
        fx, fy, fin = to_led(fp_lat, fp_lon)
        fx, fy = fx[fin], fy[fin]
        beat = 0.5 + 0.5 * math.sin(unix * 2 * math.pi / 7.0)
        k = (JIT[fy, fx] < 0.38 + 0.38 * beat) & (np.arange(len(fx)) % 2 == 0)
        img[fy[k], fx[k]] = np.clip(shade(FOOT, f), 0, 255).astype(np.uint8)
        ph = (unix / 9.0) % 1.0                                              # the opening ring
        if ph < 0.9:
            sc = 0.12 + 0.88 * ph
            p2, l2 = footprint(lat, lon, alt, 72)
            p2 = lat + (p2 - lat) * sc
            l2 = lon + (l2 - lon) * sc
            gx, gy, gin = to_led(p2, l2)
            gx, gy = gx[gin], gy[gin]
            k = JIT[gy, gx] < 0.8 * (1.0 - ph / 0.9)
            img[gy[k], gx[k]] = np.clip(shade(FOOT, f), 0, 255).astype(np.uint8)

    def _station(self, img, unix, x, y, lit, f):
        """The station: a hot core with a bloom of graded LEDs (a cross, its diagonals, a loose outer ring that twinkles slowly)
        and its name, small, to one side."""
        base = HEAD_SUN if lit else HEAD_SHADOW
        glow = shade(base * np.array([1.0, 0.82, 0.55], np.float32) if lit else base, max(f, 0.7))
        near = shade(glow, 0.80)
        diag = shade(glow, 0.52)
        put = lambda dx, dy, c: self._px(img, x + dx, y + dy, c)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            put(dx, dy, near)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            put(dx, dy, diag)
        beat = 0.5 + 0.5 * math.sin(unix * 2.2)
        for k, (dx, dy) in enumerate(((-2, 0), (2, 0), (0, -2), (0, 2))):
            if (k % 2 == 0) == (beat > 0.5):
                put(dx, dy, shade(glow, 0.55))
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            if JIT[min(H - 1, max(0, y + dy)), min(W - 1, max(0, x + dx))] < 0.5 * beat + 0.15:
                put(dx, dy, shade(glow, 0.45))
        self._px(img, x, y, np.clip(base * (0.9 + 0.1 * beat), 0, 255))
        # label: "ISS" on the side with room, clear of Zürich's name when the two are close
        s1 = "ISS"
        w = self.font.width(s1)
        zx, zy, _ = to_led(HOME[0], HOME[1])
        zr = (int(zx[0]) - 4 - self.font.width("ZURICH") - 1, int(zy[0]) - 4, int(zx[0]) + 3, int(zy[0]) + 4)   # x0, y0, x1, y1
        for lx, ly in ((x + 6, y - 3), (x - 6 - w, y - 3), (x + 6, y + 5), (x - 6 - w, y + 5), (x + 6, y - 10)):
            if lx < 1 or lx + w >= W - 1 or ly < 1 or ly + 5 >= H - 1:
                continue
            if lx < zr[2] + 1 and lx + w > zr[0] - 1 and ly < zr[3] + 1 and ly + 5 > zr[1] - 1:
                continue
            break
        img[max(0, ly - 1):ly + 6, max(0, lx - 1):min(W, lx + w + 1)] = 0
        self.font.draw(img, s1, lx, ly, shade(base, 0.9))

    @staticmethod
    def _px(img, x, y, c):
        if 0 <= x < W and 0 <= y < H:
            img[y, x] = np.maximum(img[y, x], np.clip(c, 0, 255).astype(np.uint8))

    def _home(self, img, unix, lat, lon, r, ok):
        """Zürich: a dim steady LED with four faint points; while the station is within 1,500 km, rings of light open out from
        it (faster the closer it gets), fading by ordered dither as they widen, in gold, or paler gold when it could be seen."""
        hx, hy, _ = to_led(HOME[0], HOME[1])
        hx, hy = int(hx[0]), int(hy[0])
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            self._px(img, hx + dx, hy + dy, shade(HOME_LED, 0.55))
        img[hy, hx] = HOME_LED.astype(np.uint8)
        if not ok:
            return
        d = ground_km(lat, lon, HOME[0], HOME[1])
        if d > NEAR_KM:
            return
        close = 1.0 - d / NEAR_KM                                            # 0 at the edge, 1 overhead
        period = 4.6 - 2.6 * close                                           # seconds a pulse takes
        seen = self._visible(unix, r)
        col = PULSE_SEEN if seen else PULSE
        reach = 5.0 + 6.0 * close
        for k in range(3 if seen or close > 0.5 else 2):                     # up to three rings in flight, evenly spaced
            ph = ((unix / period) + k / 3.0) % 1.0
            rad = 1.6 + ph * reach
            self._ring(img, hx, hy, rad, rad, shade(col, 1.0), 1.0 - ph * 0.92, n=max(14, int(rad * 7)))
        # the label arrives with the first ring and fades with the last one gone
        s = "ZURICH"
        w = self.font.width(s)
        fade = min(1.0, close * 3.0 + 0.2)
        lx, ly = max(1, hx - 5 - w), hy - 2
        img[ly - 1:ly + 6, max(0, lx - 1):lx + w + 1] = 0
        for i, ch in enumerate(s):
            gx = lx + i * 4
            if BAYER[ly, min(W - 1, gx)] < fade:
                self.font.draw(img, ch, gx, ly, shade(col, 0.8))
        img[hy, hx] = col.astype(np.uint8)

    def _visible(self, unix, r):
        """True when the ISS could be seen from Zürich now: above 10 degrees, in sunlight, the sun 6 degrees down."""
        if r is None:
            return False
        j = sat.jd(unix)
        g = float(sat.gmst(j))
        s = sat.sun_eci(j)
        az, el = sat.look(sat.to_ecef(np.asarray(r)[None], g))
        sun_el = sat.look(sat.to_ecef(s, g)[None], distant=True)[1][0]
        along = float(np.dot(r, s))
        lit = along > 0 or np.linalg.norm(np.asarray(r) - along * s) > sat.RE
        return bool(el[0] > math.radians(10) and sun_el < math.radians(-6) and lit)


_iss = None


def thumb():
    """A still for the app, no network: the orbit as the newest elements on disk (or the bundled ones)
    put it. If those are more than a few days old, the picture is drawn for a time just after their
    epoch, so the still shows the piece as it looks with fresh elements, not a dimmed one."""
    d = ISSDay(fetch=False)
    now = time.time()
    e = sat.tle_epoch(d.tle[1])
    if now - e > STALE_FROM * 86400.0:
        now = e + 20 * 3600.0
    return d(0.0, now)


def frame(t):
    global _iss
    if _iss is None:
        _iss = ISSDay()
    return _iss(t)
