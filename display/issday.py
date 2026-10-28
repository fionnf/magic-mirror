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
where it is night, from assets/maps/land_mask.png (Natural Earth 1:50m, public domain, built by
tools/build_land.py). Where the sun is setting or rising the terminator is a dotted band across each
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
# so every colour keeps its lit channels at or above 100 and a channel that is not meant to show is 0.
COAST_DAY = np.array([0, 138, 112], np.float32)        # the coast where the sun is up
COAST_TWI = np.array([0, 108, 176], np.float32)        # ... where it is rising or setting
COAST_NIGHT = np.array([0, 0, 128], np.float32)        # ... and in the night
TWILIGHT = np.array([0, 98, 142], np.float32)          # the dotted band of dusk and dawn
FOOT = np.array([0, 112, 150], np.float32)             # the footprint ring
HEAD_SUN = np.array([255, 250, 228], np.float32)
HEAD_SHADOW = np.array([160, 160, 255], np.float32)
HOME_LED = np.array([150, 140, 130], np.float32)
PULSE = np.array([255, 196, 84], np.float32)
PULSE_SEEN = np.array([255, 245, 210], np.float32)
NOTE = np.array([108, 108, 120], np.float32)
# track colour by age, in orbits (the track's age over the period): just behind the head to a day ago
AGE_ORBITS = np.array([0.0, 0.08, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0], np.float32)
AGE_COLS = np.array([(255, 224, 124), (255, 206, 98), (255, 178, 74), (255, 140, 60), (232, 82, 100),
                     (166, 60, 190), (120, 0, 160), (100, 0, 124)], np.float32)
OLD_FROM, OLD_EVERY = 3.0, 3                           # beyond three orbits old: one LED in three
ECC2 = 0.00669438                                      # WGS-84 eccentricity squared (geocentric -> geodetic lat)


def shade(col, f):
    """col * f, but a channel that falls under the wall's dimmest visible step drops out and the brightest
    channel never goes below it: a dimmed amber turns red, a dimmed violet a deep blue, then they go dark
    (one colour, or rows of them)."""
    c = np.asarray(col, np.float32) * f
    top = c.max(axis=-1, keepdims=True)
    return np.where(c >= 94.0, c, np.where((c >= top) & (top >= 40.0), 100.0, 0.0)).astype(np.float32)


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
        self.sky, self.sky_t = None, -1e9                  # the map under the track (coasts, terminator)
        self.track = None                                  # (times, x, y, last time) of the last day's orbit
        self.fetched = 0.0
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
                if e < now + 2 * 86400.0:                  # a future epoch is a damaged file
                    sat.propagator([tle])
                    ok.append((e, tle, name))
            except Exception:
                continue
        e, tle, name = max(ok, key=lambda c: c[0])
        return tle, name

    def _use(self, pick):
        tle, source = pick
        if self.tle is not None and tle[1:] == self.tle[1:]:
            self.source = source
            return
        prop = sat.propagator([tle])
        self.tle, self.source = tle, source
        self.period = 86400.0 / float(tle[2][52:63])        # seconds an orbit takes
        self.track, self.sky = None, None
        self.prop = prop                                   # swapped last: the frame thread picks it up

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

    def _sky(self, unix):
        """The map under the track, redrawn every 20 s: the coasts coloured by the sun's height there and
        the dotted band of dusk and dawn."""
        lat, lon = self._sun(unix)
        h = self.geo.sun_height(lat, lon)
        img = np.zeros((H, W, 3), np.uint8)
        m = self.geo.mapped
        img[m & (h < 0) & (h >= -3) & self.chequer] = TWILIGHT
        img[m & (h < -3) & (h >= -7) & self.sparse] = TWILIGHT
        ch = h[self.cy, self.cx]
        col = np.where((ch > 0)[:, None], COAST_DAY, np.where((ch > -12)[:, None], COAST_TWI, COAST_NIGHT))
        img[self.cy, self.cx] = col.astype(np.uint8)
        return img

    def _track(self, unix):
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
        lat, lon, _, _, ok, _ = positions(self.prop, t)
        x, y, inside = to_led(lat, lon)
        keep = ok & inside
        tt, tx, ty = np.concatenate([tt, t[keep]]), np.concatenate([tx, x[keep]]), np.concatenate([ty, y[keep]])
        fresh = tt >= grid - HISTORY
        return tt[fresh], tx[fresh], ty[fresh], grid

    def _factor(self, unix):
        """How bright the elements' age lets the track be: 1 until 2.5 days old, half at 10, a third after."""
        d = tle_age_days(self.tle, unix)
        return float(np.interp(abs(d), [STALE_FROM, STALE_HALF, 30.0], [1.0, 0.5, 0.33]))

    # ---------------------------------------------------------- frames
    def __call__(self, t, now=None):
        unix = time.time() if now is None else now
        if self.sky is None or abs(unix - self.sky_t) > REBUILD:
            self.sky, self.sky_t = self._sky(unix), unix
        self.track = self._track(unix)
        img = self.sky.copy()
        f = self._factor(unix)
        tt, tx, ty = self.track[:3]                        # oldest first, so a crossing LED takes the newest colour
        if len(tt):
            age = (unix - tt) / self.period
            col = np.stack([np.interp(age, AGE_ORBITS, AGE_COLS[:, k]) for k in range(3)], 1)
            keep = (age < OLD_FROM) | (np.round(tt / STEP).astype(np.int64) % OLD_EVERY == 0)     # old orbits: dotted
            img[ty[keep], tx[keep]] = np.clip(shade(col[keep], f), 0, 255).astype(np.uint8)
        # the station
        lat, lon, alt, lit, ok, r = positions(self.prop, np.array([unix]))
        lat, lon, alt, lit, ok = float(lat[0]), float(lon[0]), float(alt[0]), bool(lit[0]), bool(ok[0])
        if ok:
            fp_lat, fp_lon = footprint(lat, lon, alt)
            fx, fy, fin = to_led(fp_lat, fp_lon)
            fx, fy = fx[fin][::2], fy[fin][::2]                              # dotted: every other point
            img[fy, fx] = np.clip(shade(FOOT, f), 0, 255).astype(np.uint8)
        self._home(img, unix, lat, lon, r[0] if ok else None, ok)
        if ok:
            hx, hy, hin = to_led(lat, lon)
            if hin[0]:
                col = (HEAD_SUN if lit else HEAD_SHADOW) * (0.86 + 0.14 * math.sin(unix * 3.0))
                img[hy[0], hx[0]] = np.clip(shade(col, max(f, 0.6)), 0, 255).astype(np.uint8)
        if tle_age_days(self.tle, unix) > STALE_FROM:
            self.font.draw(img, "TLE " + tle_note(self.tle), 2, Y0[1] + ROWS - 6, NOTE)
        return Image.fromarray(img, "RGB")

    def _home(self, img, unix, lat, lon, r, ok):
        """Zürich: one dim LED, and a ring of light pulsing out from it while the station is within 1,500 km."""
        hx, hy, _ = to_led(HOME[0], HOME[1])
        hx, hy = int(hx[0]), int(hy[0])
        img[hy, hx] = HOME_LED.astype(np.uint8)
        if not ok:
            return
        d = ground_km(lat, lon, HOME[0], HOME[1])
        if d > NEAR_KM:
            return
        close = 1.0 - d / NEAR_KM                                            # 0 at the edge, 1 overhead
        period = 4.0 - 2.4 * close                                           # seconds a pulse takes
        seen = self._visible(unix, r)
        col = PULSE_SEEN if seen else PULSE
        for k in range(2 if seen or close > 0.5 else 1):                     # a second ring when it is near
            ph = ((unix / period) + 0.5 * k) % 1.0
            if ph > 0.85:
                continue                                                     # the ring has faded out
            rad = 1.5 + ph * (6.0 + 6.0 * close)
            c = col * (1.0 if ph < 0.45 else 1.0 - (ph - 0.45) * 1.2)        # full, then dimming to ~half:
            c = np.where(c >= 94.0, c, 0.0)                                  # the gold stays gold
            a = np.linspace(0.0, 2 * math.pi, max(12, int(rad * 7)), endpoint=False)
            px = np.round(hx + rad * np.cos(a)).astype(int)
            py = np.round(hy + rad * np.sin(a)).astype(int)
            fine = (px >= 0) & (px < W) & (py >= 0) & (py < H)
            img[py[fine], px[fine]] = np.clip(c, 0, 255).astype(np.uint8)
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
