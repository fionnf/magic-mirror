"""Satellites: the sky above the apartment as a round star chart - zenith in the middle, the horizon a
faint ring, north at the top and east on the left, as a chart is held overhead. The ISS, Tiangong and
the brightest satellites (CelesTrak's 'visual' and 'stations' groups, public orbital elements, no key)
cross it at their real positions, each one LED leaving a fading one-LED trail, the ISS brighter and
named. A satellite you could see with your own eyes right now - in sunlight while we are in the dark,
the sun more than 6 degrees down, the satellite more than 10 degrees up - burns warm gold and draws a
long trail; one in the Earth's shadow is a small cool point; so on a clear evening the wall says: look
up. Behind them the bright stars turn with the sidereal day (Orion, the Plough, Cassiopeia ...), coming
out one by one as the sky darkens, the moon in its phase, and by day the dome fills with blue and the
sun. At dusk the horizon glows on the side where the sun went down.

Everything is drawn on whole LEDs (no anti-aliasing): a soft dot gliding between LEDs shimmers.

The orbital elements (TLEs) are fetched every 8 hours on a side thread while the piece is running, and
kept in panel_setup/satellites_cache.json, so a restart or a day without internet changes nothing. The
positions are computed here: with the 'sgp4' package when it is installed, otherwise with a built-in
version of the same theory's main terms (J2 secular and short-period, J3 long-period, the TLE's
decay rate), good to a few km over a day - well under one LED. Every satellite is propagated once a
second, all at once in numpy, and its LED glides between those fixes. The sun and moon come from the
usual low-precision almanac formulas.
"""
import calendar
import json
import math
import os
import threading
import time

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
HOME = (47.3726, 8.5398, 0.42)                       # Rennweg: lat, lon, km above the sea
URLS = ["https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle",
        "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"]
STATIONS = {25544: "ISS", 48274: "CSS"}              # the only 'stations' objects kept (the rest are docked
                                                      # ships at the same spot, or faint cubesats)
REFRESH = 8 * 3600.0                                 # CelesTrak updates a few times a day; asks for <= 1 per 2 h
RETRY = (600.0, 7200.0)                              # after a failure: 10 min, doubling to 2 h
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel_setup",
                     "satellites_cache.json")
STEP = 1.0                                            # seconds between propagations
FADE = 100.0                                          # seconds for a trail to fall to 1/e

CX, CY, R = (W - 1) / 2.0, (H - 1) / 2.0, min(W, H) / 2.0 - 4.0     # the dome: horizon at R
# colours (the wall shows nothing below ~94 in a channel and only ~5 steps above it: 94 149 188 219 245)
SEEN = np.array([255, 205, 120], np.float32)          # sunlit while we are in the dark: look up
SEEN_ISS = np.array([255, 250, 225], np.float32)
DAY = np.array([150, 170, 210], np.float32)           # sunlit, but so is our sky
DAY_TRAIL = np.array([0, 104, 160], np.float32)       # its trail: red and green drop out together, no teal
SHADOW = np.array([105, 112, 200], np.float32)        # in the Earth's shadow
LOW = 0.72                                            # below 10 degrees: a little dimmer
RING = np.array([34, 62, 124], np.float32)            # the horizon at night: the deepest blue the wall shows
RING_DAY = np.array([70, 112, 180], np.float32)
GLOW = np.array([240, 120, 0], np.float32)            # the horizon where the sun is, at dusk and dawn,
EMBER = np.array([170, 0, 0], np.float32)             # stepped (no blends: those turn magenta and grey on LEDs)
SKY = np.array([10, 46, 128], np.float32)             # the dome by day (on every other LED: the wall's
                                                      # dimmest blue, halved), in civil twilight on one in four
SUN = np.array([255, 190, 70], np.float32)
MOON = np.array([235, 228, 205], np.float32)
MARK = np.array([100, 104, 116], np.float32)          # the N above the dome

# a handful of bright stars: RA (h), Dec (deg), magnitude, colour (J2000; precession since is < 1 LED)
STARS = [
    (6.752, -16.716, -1.46, (205, 220, 255)), (14.261, 19.182, -0.05, (255, 214, 165)),  # Sirius, Arcturus
    (18.616, 38.784, 0.03, (210, 222, 255)), (5.278, 45.998, 0.08, (255, 240, 205)),     # Vega, Capella
    (5.242, -8.202, 0.13, (205, 220, 255)), (7.655, 5.225, 0.34, (255, 250, 235)),       # Rigel, Procyon
    (5.919, 7.407, 0.50, (255, 165, 105)), (19.846, 8.868, 0.77, (238, 242, 255)),       # Betelgeuse, Altair
    (4.599, 16.509, 0.85, (255, 180, 120)), (13.420, -11.161, 0.97, (205, 220, 255)),    # Aldebaran, Spica
    (16.490, -26.432, 1.06, (255, 150, 100)), (7.755, 28.026, 1.14, (255, 222, 175)),    # Antares, Pollux
    (22.961, -29.622, 1.16, (238, 242, 255)), (20.690, 45.280, 1.25, (238, 242, 255)),   # Fomalhaut, Deneb
    (10.140, 11.967, 1.36, (215, 225, 255)), (7.577, 31.888, 1.58, (238, 242, 255)),     # Regulus, Castor
    (5.419, 6.350, 1.64, (215, 225, 255)), (5.604, -1.202, 1.69, (215, 225, 255)),       # Bellatrix, Alnilam
    (5.679, -1.943, 1.74, (215, 225, 255)), (5.533, -0.299, 2.23, (215, 225, 255)),      # Alnitak, Mintaka
    (5.796, -9.670, 2.07, (215, 225, 255)), (3.405, 49.861, 1.79, (255, 245, 225)),      # Saiph, Mirfak
    (11.062, 61.751, 1.79, (255, 225, 180)), (11.031, 56.382, 2.37, (238, 242, 255)),    # Dubhe, Merak
    (11.897, 53.695, 2.44, (238, 242, 255)), (12.257, 57.033, 3.31, (238, 242, 255)),    # Phecda, Megrez
    (12.900, 55.960, 1.77, (238, 242, 255)), (13.399, 54.925, 2.27, (238, 242, 255)),    # Alioth, Mizar
    (13.792, 49.313, 1.86, (225, 232, 255)), (2.530, 89.264, 1.98, (255, 245, 220)),     # Alkaid, Polaris
    (0.675, 56.537, 2.24, (255, 220, 175)), (0.153, 59.150, 2.28, (255, 250, 235)),      # Schedar, Caph
    (0.945, 60.717, 2.47, (225, 232, 255)), (1.430, 60.235, 2.68, (238, 242, 255)),      # Gamma Cas, Ruchbah
    (1.907, 63.670, 3.37, (225, 232, 255)), (0.140, 29.091, 2.06, (225, 232, 255)),      # Segin, Alpheratz
    (23.063, 28.083, 2.42, (255, 200, 150)), (23.079, 15.205, 2.49, (225, 232, 255)),    # Scheat, Markab
    (0.220, 15.184, 2.83, (225, 232, 255)),                                              # Algenib
]

# ------------------------------------------------------------------ time, frames, the observer ---

RE = 6378.135                                         # km (WGS-72, as the TLEs are made)
MU = 398600.8
XKE = 60.0 / math.sqrt(RE ** 3 / MU)                  # Earth radii^1.5 per minute
J2, J3, J4 = 0.001082616, -0.00000253881, -0.00000165597
TWO_PI = 2.0 * math.pi


def jd(unix):
    return unix / 86400.0 + 2440587.5


def gmst(j):
    """Greenwich mean sidereal time, radians (UT1 taken as UTC: under a second, a fraction of an LED)."""
    tu = (j - 2451545.0) / 36525.0
    s = 67310.54841 + (876600.0 * 3600.0 + 8640184.812866) * tu + 0.093104 * tu * tu - 6.2e-6 * tu ** 3
    return (s % 86400.0) / 86400.0 * TWO_PI


def _observer():
    lat, lon, h = math.radians(HOME[0]), math.radians(HOME[1]), HOME[2]
    a, f = 6378.137, 1 / 298.257223563
    e2 = f * (2 - f)
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    pos = np.array([(n + h) * math.cos(lat) * math.cos(lon), (n + h) * math.cos(lat) * math.sin(lon),
                    (n * (1 - e2) + h) * math.sin(lat)])
    enu = np.array([[-math.sin(lon), math.cos(lon), 0.0],
                    [-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)],
                    [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]])
    return pos, enu


OBS, ENU = _observer()


def to_ecef(v, g):
    """Inertial (TEME / of-date) vectors (..., 3) -> Earth-fixed, by the sidereal angle g."""
    c, s = math.cos(g), math.sin(g)
    x, y = v[..., 0], v[..., 1]
    return np.stack([c * x + s * y, -s * x + c * y, v[..., 2]], -1)


def look(v_ecef, distant=False):
    """Earth-fixed positions (km) or directions -> (azimuth, elevation) in radians."""
    rho = v_ecef if distant else v_ecef - OBS
    e, n, u = (rho @ ENU.T).T
    return np.arctan2(e, n), np.arctan2(u, np.hypot(e, n))


def chart(az, el):
    """Azimuth/elevation -> chart position (float LEDs): zenith centre, horizon at R, N up, E left."""
    r = R * (0.5 * math.pi - el) / (0.5 * math.pi)
    return CX - r * np.sin(az), CY - r * np.cos(az)


def sun_eci(j):
    """Unit vector to the sun, equatorial of date (Astronomical Almanac low-precision, ~0.01 deg)."""
    n = j - 2451545.0
    L = math.radians((280.460 + 0.9856474 * n) % 360)
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 4e-7 * n)
    return np.array([math.cos(lam), math.cos(eps) * math.sin(lam), math.sin(eps) * math.sin(lam)])


def moon_eci(j):
    """Geocentric moon, km, equatorial of date (Almanac low-precision series, ~0.3 deg)."""
    T = (j - 2451545.0) / 36525.0
    d = lambda a, b: math.radians((a + b * T) % 360)
    lam = (218.32 + 481267.881 * T + 6.29 * math.sin(d(135.0, 477198.87)) - 1.27 * math.sin(d(259.3, -413335.36))
           + 0.66 * math.sin(d(235.7, 890534.22)) + 0.21 * math.sin(d(269.9, 954397.74))
           - 0.19 * math.sin(d(357.5, 35999.05)) - 0.11 * math.sin(d(186.5, 966404.03)))
    beta = (5.13 * math.sin(d(93.3, 483202.03)) + 0.28 * math.sin(d(228.2, 960400.87))
            - 0.28 * math.sin(d(318.3, 6003.18)) - 0.17 * math.sin(d(217.6, -407332.20)))
    par = (0.9508 + 0.0518 * math.cos(d(135.0, 477198.87)) + 0.0095 * math.cos(d(259.3, -413335.38))
           + 0.0078 * math.cos(d(235.7, 890534.23)) + 0.0028 * math.cos(d(269.9, 954397.70)))
    lam, beta = math.radians(lam), math.radians(beta)
    r = RE / math.sin(math.radians(par))
    eps = math.radians(23.439 - 0.0130 * T)
    x, y, z = math.cos(beta) * math.cos(lam), math.cos(beta) * math.sin(lam), math.sin(beta)
    return r * np.array([x, math.cos(eps) * y - math.sin(eps) * z, math.sin(eps) * y + math.cos(eps) * z])


# ------------------------------------------------------------------ orbits ---

def parse_tle(text):
    """[(name, line1, line2), ...] from a 3-line TLE text, skipping anything malformed."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    out = []
    for i in range(len(lines) - 2):
        a, b, c = lines[i], lines[i + 1], lines[i + 2]
        if b.startswith("1 ") and c.startswith("2 ") and len(b) >= 63 and len(c) >= 63 and not a.startswith(("1 ", "2 ")):
            out.append((a.strip(), b, c))
    return out


def _checksum_ok(line):
    if len(line) < 69 or not line[68].isdigit():
        return False
    return sum(int(ch) if ch.isdigit() else ch == "-" for ch in line[:68]) % 10 == int(line[68])


def valid(tle):
    """True when every field the propagators read parses and both lines pass their checksum."""
    try:
        _, l1, l2 = tle
        if not (_checksum_ok(l1) and _checksum_ok(l2)):
            return False
        int(l1[2:7])
        tle_epoch(l1)
        float(l1[33:43])
        float("0." + l2[26:33].strip())
        for a, b in ((8, 16), (17, 25), (34, 42), (43, 51), (52, 63)):
            float(l2[a:b])
        return float(l2[52:63]) > 0.5
    except (ValueError, TypeError, IndexError):
        return False


def tle_epoch(l1):
    yy = int(l1[18:20])
    year = yy + (2000 if yy < 57 else 1900)
    return calendar.timegm((year, 1, 1, 0, 0, 0)) + (float(l1[20:32]) - 1.0) * 86400.0


class Fallback:
    """SGP4's near-Earth theory without its drag model, vectorised over all satellites: Brouwer mean
    motion from the TLE's Kozai one, J2/J4 secular rates of node, perigee and mean anomaly, J3 long-period
    and J2 short-period terms, and the decay rate (the TLE's ndot/2) for drag. Against full SGP4 it
    stays within a few km over a day for these low orbits."""

    def __init__(self, tles):
        f = lambda s: float(s.strip() or 0)
        self.epoch = np.array([tle_epoch(l1) for _, l1, _ in tles])
        ndot2 = np.array([f(l1[33:43]) for _, l1, _ in tles]) * TWO_PI / 1440.0 ** 2      # rad/min^2
        i0 = np.radians([f(l2[8:16]) for _, _, l2 in tles])
        self.node0 = np.radians([f(l2[17:25]) for _, _, l2 in tles])
        e0 = np.array([float("0." + l2[26:33].strip()) for _, _, l2 in tles])
        self.argp0 = np.radians([f(l2[34:42]) for _, _, l2 in tles])
        self.m0 = np.radians([f(l2[43:51]) for _, _, l2 in tles])
        n_k = np.array([f(l2[52:63]) for _, _, l2 in tles]) * TWO_PI / 1440.0            # rad/min
        cosi, sini = np.cos(i0), np.sin(i0)
        c2 = cosi ** 2
        om = 1.0 - e0 ** 2
        rte = np.sqrt(om)
        ak = (XKE / n_k) ** (2.0 / 3.0)                                                    # un-Kozai
        d1 = 0.75 * J2 * (3.0 * c2 - 1.0) / (rte * om)
        de = d1 / ak ** 2
        adel = ak * (1.0 - de ** 2 - de * (1.0 / 3.0 + 134.0 * de ** 2 / 81.0))
        de = d1 / adel ** 2
        n = n_k / (1.0 + de)
        a = (XKE / n) ** (2.0 / 3.0)
        pinv2 = 1.0 / (a * om) ** 2
        t1 = 1.5 * J2 * pinv2 * n
        t2 = 0.5 * t1 * J2 * pinv2
        t3 = -0.46875 * J4 * pinv2 ** 2 * n
        con41 = 3.0 * c2 - 1.0
        self.mdot = n + 0.5 * t1 * rte * con41 + 0.0625 * t2 * rte * (13.0 - 78.0 * c2 + 137.0 * c2 ** 2)
        self.argpdot = (-0.5 * t1 * (1.0 - 5.0 * c2) + 0.0625 * t2 * (7.0 - 114.0 * c2 + 395.0 * c2 ** 2)
                        + t3 * (3.0 - 36.0 * c2 + 49.0 * c2 ** 2))
        self.nodedot = -t1 * cosi + (0.5 * t2 * (4.0 - 19.0 * c2) + 2.0 * t3 * (3.0 - 7.0 * c2)) * cosi
        self.n, self.e, self.i, self.ndot2 = n, e0, i0, ndot2
        self.cosi, self.sini, self.con41 = cosi, sini, con41
        self.x1mth2, self.x7thm1 = 1.0 - c2, 7.0 * c2 - 1.0
        j3oj2 = J3 / J2
        self.aycof = -0.5 * j3oj2 * sini
        den = np.where(np.abs(1.0 + cosi) > 1.5e-12, 1.0 + cosi, 1.5e-12)
        self.xlcof = -0.25 * j3oj2 * sini * (3.0 + 5.0 * cosi) / den

    def __call__(self, unix):
        """Positions (n, 3), km, TEME, and a validity mask."""
        t = (unix - self.epoch) / 60.0                                                      # minutes
        nm = np.maximum(self.n + 2.0 * self.ndot2 * t, 1e-4)
        am = (XKE / nm) ** (2.0 / 3.0)
        mm = self.m0 + self.mdot * t + self.ndot2 * t * t
        argp = self.argp0 + self.argpdot * t
        node = self.node0 + self.nodedot * t
        ep = self.e
        axn = ep * np.cos(argp)
        tmp = 1.0 / (am * (1.0 - ep * ep))
        ayn = ep * np.sin(argp) + tmp * self.aycof
        xl = mm + argp + node + tmp * self.xlcof * axn
        u = np.mod(xl - node, TWO_PI)
        eo = u.copy()
        for _ in range(8):                                                                  # Kepler
            s, c = np.sin(eo), np.cos(eo)
            d = (u - ayn * c + axn * s - eo) / (1.0 - c * axn - s * ayn)
            eo += np.clip(d, -0.95, 0.95)
        s, c = np.sin(eo), np.cos(eo)
        ecose, esine = axn * c + ayn * s, axn * s - ayn * c
        el2 = axn * axn + ayn * ayn
        pl = am * (1.0 - el2)
        rl = am * (1.0 - ecose)
        betal = np.sqrt(1.0 - el2)
        tmp = esine / (1.0 + betal)
        sinu = am / rl * (s - ayn - axn * tmp)
        cosu = am / rl * (c - axn + ayn * tmp)
        su = np.arctan2(sinu, cosu)
        sin2u, cos2u = 2.0 * cosu * sinu, 1.0 - 2.0 * sinu * sinu
        t1 = 0.5 * J2 / pl
        t2 = t1 / pl
        mrt = rl * (1.0 - 1.5 * t2 * betal * self.con41) + 0.5 * t1 * self.x1mth2 * cos2u     # short-period
        su = su - 0.25 * t2 * self.x7thm1 * sin2u
        xnode = node + 1.5 * t2 * self.cosi * sin2u
        xinc = self.i + 1.5 * t2 * self.cosi * self.sini * cos2u
        sn, cn, si, ci, ss, cs = np.sin(xnode), np.cos(xnode), np.sin(xinc), np.cos(xinc), np.sin(su), np.cos(su)
        r = np.stack([cn * cs - sn * ci * ss, sn * cs + cn * ci * ss, si * ss], -1) * (mrt * RE)[:, None]
        ok = (pl > 0) & (mrt > 1.0) & (np.abs(t) < 30 * 1440.0)
        return r, ok


class WithSGP4:
    """The real thing, when the 'sgp4' package is installed (vectorised via SatrecArray)."""

    def __init__(self, tles):
        from sgp4.api import Satrec, SatrecArray
        self.arr = SatrecArray([Satrec.twoline2rv(l1, l2) for _, l1, l2 in tles])
        self.epoch = np.array([tle_epoch(l1) for _, l1, _ in tles])

    def __call__(self, unix):
        j = jd(unix)
        whole = math.floor(j - 0.5) + 0.5
        err, r, _ = self.arr.sgp4(np.array([whole]), np.array([j - whole]))
        ok = (err[:, 0] == 0) & (np.abs(unix - self.epoch) < 30 * 86400.0)
        return np.nan_to_num(r[:, 0, :]), ok


def propagator(tles):
    try:
        return WithSGP4(tles)
    except Exception:
        return Fallback(tles)


def pick(groups):
    """Merge the downloaded groups into one list, by catalogue number: all of 'visual', and of 'stations'
    only the two station cores."""
    out = {}
    for gi, tles in enumerate(groups):
        for name, l1, l2 in tles:
            try:
                num = int(l1[2:7])
            except ValueError:
                continue
            if gi == 0 or num in STATIONS:
                out.setdefault(num, (name, l1, l2))
    return list(out.values())


# ------------------------------------------------------------------ the piece ---

class Satellites:
    def __init__(self, fetch=True):
        self.data = None                                      # (propagator, catalogue numbers, labels),
        self.fetched = 0.0                                    # swapped as one tuple: frames never see a mix
        self.samples = None                                   # (data, t0, fix0, t1, fix1)
        self.trail = np.zeros((H, W, 3), np.float32)
        self.drawn = {}                                       # catalogue number -> last LED
        self.base, self.base_t = None, -1e9
        self.night = 0.0
        self.last = None
        ys, xs = np.mgrid[0:H, 0:W]
        self.inside = (xs - CX) ** 2 + (ys - CY) ** 2 <= (R - 0.5) ** 2
        self.dither = ((xs + ys) % 2) * 2 + ys % 2               # 0..3: <2 a chequerboard, <1 one LED in four
        self.ring = self._ring_pixels()
        if fetch:                                             # the cache is read there too: frame() never waits
            threading.Thread(target=self._fetch_loop, daemon=True).start()
        else:
            self._load_cache()

    # ---------------------------------------------------------- data
    def _set(self, tles, fetched):
        now = time.time()
        tles = [x for x in tles if valid(x) and abs(now - tle_epoch(x[1])) < 30 * 86400]
        if len(tles) < 5:
            return False
        try:
            prop = propagator(tles)
        except Exception as e:
            print(f"[satellites] {str(e)[:100]}", flush=True)
            return False
        nums = [int(l1[2:7]) for _, l1, _ in tles]
        self.fetched = min(fetched, now)                       # a clock that ran ahead must not stop refreshes
        self.data = (prop, nums, [STATIONS.get(n, "") for n in nums])
        return True

    def _load_cache(self):
        try:
            with open(CACHE) as fh:
                c = json.load(fh)
            self._set([tuple(x) for x in c["tle"]], float(c["fetched"]))
        except Exception:
            pass

    def _fetch_loop(self):
        import requests
        self._load_cache()
        wait = RETRY[0]
        while True:
            age = time.time() - self.fetched
            if 0 <= age < REFRESH and self.data is not None:
                time.sleep(min(REFRESH - age, 900.0))
                continue
            answered = False                                   # CelesTrak replied (with anything at all)
            try:
                groups = []
                for url in URLS:
                    try:
                        r = requests.get(url, timeout=30, headers={"User-Agent": "magic-mirror-wall/1.0"})
                        answered = True
                        r.raise_for_status()
                        groups.append(parse_tle(r.text))
                    except Exception as e:
                        if not groups:
                            raise                              # no 'visual': try again later
                        print(f"[satellites] {url[-30:]}: {str(e)[:80]}", flush=True)
                        groups.append([])
                tles = pick(groups)
                now = time.time()
                if not self._set(tles, now):
                    raise ValueError(f"only {len(tles)} usable TLEs")
                tmp = CACHE + ".tmp"
                with open(tmp, "w") as fh:
                    json.dump({"fetched": now, "tle": tles}, fh)
                os.replace(tmp, CACHE)
                wait = RETRY[0]
            except Exception as e:
                print(f"[satellites] {str(e)[:100]}", flush=True)
                if answered:                                   # the server is up but had nothing for us:
                    time.sleep(RETRY[1])                       # keep to its one-download-per-2-h rule
                else:                                          # no connection: nobody is bothered, retry sooner
                    time.sleep(wait)
                    wait = min(wait * 2, RETRY[1])

    # ---------------------------------------------------------- geometry
    def _fix(self, prop, unix):
        """Every satellite at one instant: chart x, y, elevation, and its light (0 shadow, 1 day, 2 seen)."""
        r, ok = prop(unix)
        j = jd(unix)
        g = gmst(j)
        az, el = look(to_ecef(r, g))
        x, y = chart(az, el)
        s = sun_eci(j)
        along = r @ s
        lit = (along > 0) | (np.linalg.norm(r - along[:, None] * s, axis=1) > RE)
        sun_el = look(to_ecef(s, g)[None], distant=True)[1][0]
        light = np.where(lit, 2 if sun_el < math.radians(-6) else 1, 0)     # 2: look up (dimmer below 10 deg)
        el = np.where(ok, el, -1.0)
        return np.stack([x, y, el, light.astype(np.float64)], 1)

    @staticmethod
    def _ring_pixels():
        """The horizon as a thin 8-connected circle of whole LEDs (one octant, mirrored eight ways)."""
        ox, oy = CX % 1.0, CY % 1.0                            # 0.5 when the centre falls between LEDs
        pts = set()
        k = 0
        while True:
            dx = k + ox
            dy = round(math.sqrt(max(R * R - dx * dx, 0.0)) - oy) + oy
            if dx > dy:
                break
            for a, b in ((dx, dy), (dy, dx)):
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        pts.add((int(round(CX + sx * a)), int(round(CY + sy * b))))
            k += 1
        xs, ys = (np.array(v) for v in zip(*sorted(pts)))
        return ys, xs, np.arctan2(CX - xs, CY - ys)            # the azimuth of each ring LED

    def _base(self, unix):
        """The slow layer, redrawn every 20 s: day sky, horizon (glowing toward the sun at dusk), the N,
        the stars as the darkness allows, the sun and the moon."""
        from display import pixelfont
        j = jd(unix)
        g = gmst(j)
        img = np.zeros((H, W, 3), np.float32)
        s = sun_eci(j)
        saz, sel = (v[0] for v in look(to_ecef(s, g)[None], distant=True))
        sel_d = math.degrees(sel)
        day = min(1.0, max(0.0, (sel_d + 6.0) / 6.0))          # 0 below -6, 1 above the horizon
        self.night = min(1.0, max(0.0, (-sel_d - 3.0) / 12.0))  # 0 above -3, 1 below -15
        if sel_d > -6:
            img[self.inside & (self.dither < (2 if sel_d > 0 else 1))] = SKY
        ys, xs, az = self.ring
        ring = RING + (RING_DAY - RING) * day
        twi = max(0.0, 1.0 - abs(sel_d + 4.0) / 8.0)            # strongest with the sun 4 degrees down
        near = np.clip(np.cos(az - saz), 0, 1) ** 3 * twi
        img[ys, xs] = ring
        img[ys[near > 0.22], xs[near > 0.22]] = EMBER
        img[ys[near > 0.5], xs[near > 0.5]] = GLOW
        pixelfont.draw(img, "N", int(round(CX)) - 1, int(round(CY - R)) - 8, MARK)
        if self.night > 0:                                      # the stars: bright ones come out first
            ra = np.radians([st[0] * 15.0 for st in STARS])
            de = np.radians([st[1] for st in STARS])
            v = np.stack([np.cos(de) * np.cos(ra), np.cos(de) * np.sin(ra), np.sin(de)], 1)
            az_s, el_s = look(to_ecef(v, g), distant=True)
            x, y = chart(az_s, el_s)
            for k, st in enumerate(STARS):
                if el_s[k] <= 0:
                    continue
                lvl = min(1.0, max(0.42, 1.0 - (st[2] + 0.5) * 0.19)) * self.night
                col = np.array(st[3], np.float32) * lvl
                if col.max() >= 94:
                    xi, yi = int(round(x[k])), int(round(y[k]))
                    img[yi, xi] = np.maximum(img[yi, xi], col)
        if sel > 0:                                             # the sun: a small warm disc
            x, y = (int(round(v)) for v in chart(saz, sel))
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    q = dx * dx + dy * dy
                    if q <= 5 and self.inside[y + dy, x + dx]:
                        img[y + dy, x + dx] = SUN * (1.0 if q <= 2 else 0.75)
        self._moon(img, j, g, s)
        return img

    def _moon(self, img, j, g, s):
        """The moon as a 7-LED disc, lit on the side facing the sun, in its true phase."""
        m = moon_eci(j)
        me = to_ecef(m, g)
        az, el = (v[0] for v in look(me[None]))
        if el <= math.radians(1.5):
            return
        md = (me - OBS) / np.linalg.norm(me - OBS)                 # topocentric unit vectors, Earth-fixed
        sd = to_ecef(s, g)
        cos_i = float(np.clip(-(md @ sd), -1.0, 1.0))              # phase angle i: 0 = full
        sin_i = math.sqrt(max(0.0, 1.0 - cos_i * cos_i))
        tan = sd - (sd @ md) * md
        tan /= max(np.linalg.norm(tan), 1e-9)
        p = md + 0.02 * tan
        x0, y0 = chart(az, el)
        x1, y1 = chart(*(v[0] for v in look((OBS + p)[None])))
        ux, uy = x1 - x0, y1 - y0
        nrm = math.hypot(ux, uy) or 1.0
        ux, uy = ux / nrm, uy / nrm                                 # toward the sun, on the chart
        xc, yc = int(round(x0)), int(round(y0))
        rr = 3.2
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                q = (dx * dx + dy * dy) / (rr * rr)
                if q > 1.0 or not (0 <= yc + dy < H and 0 <= xc + dx < W):
                    continue
                a = (dx * ux + dy * uy) / rr                        # along the sun direction
                z = math.sqrt(1.0 - q)                              # toward us
                if a * sin_i + z * cos_i > -0.05:
                    img[yc + dy, xc + dx] = MOON * (1.0 if q < 0.55 else 0.82)

    # ---------------------------------------------------------- frames
    def _positions(self, data, unix):
        prop = data[0]
        sm = self.samples
        if sm is None or sm[0] is not data or not (sm[1] <= unix < sm[3] + STEP):
            t0 = math.floor(unix / STEP) * STEP
            sm = (data, t0, self._fix(prop, t0), t0 + STEP, self._fix(prop, t0 + STEP))
        elif unix >= sm[3]:                                         # one new fix a second
            sm = (data, sm[3], sm[4], sm[3] + STEP, self._fix(prop, sm[3] + STEP))
        self.samples = sm
        f = (unix - sm[1]) / STEP
        a, b = sm[2], sm[4]
        out = a + (b - a) * f
        out[:, 3] = b[:, 3]
        return out

    def __call__(self, t, now=None):
        from display import pixelfont
        unix = time.time() if now is None else now
        dt = 0.04 if self.last is None else max(0.0, min(0.5, t - self.last))
        self.last = t
        if self.base is None or abs(unix - self.base_t) > 20.0:
            self.base, self.base_t = self._base(unix), unix
        self.trail *= math.exp(-dt / FADE)
        data = self.data                                            # one read: the fetch thread may swap it
        pos = None if data is None else self._positions(data, unix)
        heads = []
        seen = set()
        if pos is not None:
            ids, labels = data[1], data[2]
            for k in np.nonzero(pos[:, 2] > 0.0)[0]:
                x, y, el, light = pos[k]
                p = (int(round(x)), int(round(y)))
                if not self.inside[p[1], p[0]]:
                    continue
                num, label = ids[k], labels[k]
                if light == 2:
                    col, tcol = (SEEN_ISS if label else SEEN), SEEN * 0.78
                elif light == 1:
                    col, tcol = DAY * (1.25 if label else 1.0), DAY_TRAIL
                else:
                    col, tcol = SHADOW * (1.25 if label else 1.0), SHADOW * 0.55
                if el < math.radians(10):
                    col, tcol = col * LOW, tcol * LOW
                prev = self.drawn.get(num)
                if prev is not None and prev != p:
                    n = max(abs(prev[0] - p[0]), abs(prev[1] - p[1]))
                    if n < 12:                                      # the LEDs it just left
                        for i in range(n):
                            xi = prev[0] + round((p[0] - prev[0]) * i / n)
                            yi = prev[1] + round((p[1] - prev[1]) * i / n)
                            np.maximum(self.trail[yi, xi], tcol, out=self.trail[yi, xi])
                self.drawn[num] = p
                seen.add(num)
                heads.append((p, np.minimum(col, 255), label))
        for k in [k for k in self.drawn if k not in seen]:
            del self.drawn[k]
        img = np.maximum(self.base, self.trail)
        for (x, y), col, label in heads:
            img[y, x] = col                                         # the satellite: one LED
        for (x, y), col, label in heads:
            if label:
                w = pixelfont.width(label)
                tx = x + 3 if x + 3 + w <= W else x - 2 - w
                pixelfont.draw(img, label, tx, min(H - 5, max(0, y - 2)), col * (max(160.0, col.max() * 0.75) / col.max()))
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


_sats = None


def thumb():
    """A still for the app from the cached elements (no network): the last three minutes, fast-forwarded."""
    s = Satellites(fetch=False)
    now = time.time()
    img = None
    for i in range(90):
        img = s(i * 2.0, now - 180.0 + i * 2.0)
    return img


def frame(t):
    global _sats
    if _sats is None:
        _sats = Satellites()
    return _sats(t)
