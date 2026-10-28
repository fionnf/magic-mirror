"""Helpers for pieces that replay recorded animal tracks as light on the LED wall (display/storks.py).

  * Track        one animal's fixes (day, lat, lon); position at any moment, great-circle interpolation, and
                 a recording gap is a gap (the dot is not shown), never a straight line made up across it
  * YearClock    time compression: a whole year played in an hour (or any period), on the wall clock
  * Equirect     the plain lat/lon map projection (works on numbers and numpy arrays), fitted to the wall
  * Trails       a float image of fading one-LED threads: fade it, add a step of a track, merge it over a map
  * month labels (JAN..DEC) and a calendar strip for the corner of the wall
  * load_json / draw_lines / to_image: small things every such piece needs

Everything is drawn on whole LEDs (cv2.LINE_8, no anti-aliasing). Nothing here touches the network: pieces
load a bundled asset (built by a tools/build_*.py script) and fall back to something honest without it.
"""
import bisect
import json
import math
import os
import time

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
R_EARTH = 6371.0

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


# ---- geometry on the sphere ---------------------------------------------------------------------------

def to_xyz(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    c = math.cos(la)
    return (c * math.cos(lo), c * math.sin(lo), math.sin(la))


def from_xyz(v):
    x, y, z = v
    return math.degrees(math.asin(max(-1.0, min(1.0, z)))), math.degrees(math.atan2(y, x))


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def slerp(lat1, lon1, lat2, lon2, f):
    """The point a fraction f of the way along the great circle from (lat1, lon1) to (lat2, lon2)."""
    a, b = to_xyz(lat1, lon1), to_xyz(lat2, lon2)
    dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))
    om = math.acos(dot)
    if om < 1e-6:
        return lat1 + (lat2 - lat1) * f, lon1 + (lon2 - lon1) * f
    s = math.sin(om)
    ka, kb = math.sin((1 - f) * om) / s, math.sin(f * om) / s
    return from_xyz((ka * a[0] + kb * b[0], ka * a[1] + kb * b[1], ka * a[2] + kb * b[2]))


# ---- a track ---------------------------------------------------------------------------------------

class Track:
    """One animal: days (ascending, any unit, usually days since the start of its year), lat, lon.

    pos(day) -> (lat, lon) along the great circle between the two fixes around that day, or None before
    the first fix, after the last, and inside a recording gap: a gap of more than max_gap days that also
    spans more than jump_km. (A stationary animal may be stored with a few days between fixes, so a long
    gap alone is no reason to hide it; a long gap with a long jump is data that was never recorded.)
    """

    def __init__(self, days, lat, lon, max_gap=8.0, jump_km=300.0, **meta):
        self.days = [float(d) for d in days]
        self.lat = [float(v) for v in lat]
        self.lon = [float(v) for v in lon]
        self.meta = meta
        n = len(self.days)
        self.xyz = [to_xyz(a, b) for a, b in zip(self.lat, self.lon)]
        self.omega, self.hole = [], []
        for i in range(n - 1):
            a, b = self.xyz[i], self.xyz[i + 1]
            self.omega.append(math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))))
            gap = self.days[i + 1] - self.days[i]
            self.hole.append(gap > max_gap and self.omega[-1] * R_EARTH > jump_km)

    @property
    def start(self):
        return self.days[0]

    @property
    def end(self):
        return self.days[-1]

    def pos(self, day):
        d = self.days
        if not d or day < d[0] or day > d[-1]:
            return None
        i = bisect.bisect_right(d, day) - 1
        if i >= len(d) - 1:
            return self.lat[-1], self.lon[-1]
        if self.hole[i]:
            return None
        f = (day - d[i]) / (d[i + 1] - d[i])
        om = self.omega[i]
        if om < 1e-6:
            return self.lat[i] + (self.lat[i + 1] - self.lat[i]) * f, self.lon[i] + (self.lon[i + 1] - self.lon[i]) * f
        a, b = self.xyz[i], self.xyz[i + 1]
        s = math.sin(om)
        ka, kb = math.sin((1 - f) * om) / s, math.sin(f * om) / s
        return from_xyz((ka * a[0] + kb * b[0], ka * a[1] + kb * b[1], ka * a[2] + kb * b[2]))


# ---- time compression ------------------------------------------------------------------------------

class YearClock:
    """A cycle of `days` days played out over `period` seconds of the wall clock (default: a year in an hour).

    The phase comes from the wall clock, not from when the piece was switched on, so leaving the piece and
    coming back finds the year where it should be. day() is in [0, days)."""

    def __init__(self, period=3600.0, days=365, clock=time.time):
        self.period, self.days, self.clock = float(period), int(days), clock

    @property
    def seconds_per_day(self):
        return self.period / self.days

    def day(self, now=None):
        now = self.clock() if now is None else now
        return (now % self.period) / self.period * self.days


def month_of(day, start_month=7):
    """(0-11 month index, 1-based day of month) for `day` days after the 1st of start_month (1-12), in a
    365-day year."""
    m = (start_month - 1) % 12
    d = int(day)
    while d >= MONTH_DAYS[m]:
        d -= MONTH_DAYS[m]
        m = (m + 1) % 12
    return m, d + 1


def month_label(day, start_month=7):
    return MONTHS[month_of(day, start_month)[0]]


def month_edges(start_month=7):
    """Day offsets at which each month of the cycle starts, 12 of them, from start_month."""
    out, acc = [], 0
    for k in range(12):
        out.append(acc)
        acc += MONTH_DAYS[(start_month - 1 + k) % 12]
    return out


# ---- projection ------------------------------------------------------------------------------------

class Equirect:
    """Plain lat/lon map. y = (lat_top - lat) * k;  x = (lon - lon_left) * k * cos(std_lat). Works on
    floats and on numpy arrays alike and returns floats (round them yourself: whole LEDs)."""

    def __init__(self, lon_left, lat_top, px_per_deg, std_lat=0.0, width=W, height=H):
        self.lon_left, self.lat_top, self.k = lon_left, lat_top, px_per_deg
        self.kx = px_per_deg * math.cos(math.radians(std_lat))
        self.width, self.height = width, height

    @classmethod
    def fit(cls, lon_min, lon_max, lat_min, lat_max, std_lat=0.0, width=W, height=H, margin=0):
        """The largest scale at which the box fits the wall, centred."""
        c = math.cos(math.radians(std_lat))
        k = min((width - 2 * margin) / ((lon_max - lon_min) * c), (height - 2 * margin) / (lat_max - lat_min))
        left = (lon_min + lon_max) / 2 - width / (2 * k * c)
        top = (lat_min + lat_max) / 2 + height / (2 * k)
        return cls(left, top, k, std_lat, width, height)

    def to_px(self, lat, lon):
        x = (np.asarray(lon, np.float64) - self.lon_left) * self.kx
        y = (self.lat_top - np.asarray(lat, np.float64)) * self.k
        if x.ndim == 0 and y.ndim == 0:
            return float(x), float(y)
        return x, y

    def to_led(self, lat, lon):
        """(x, y) of the LED a point falls on: ints."""
        x, y = self.to_px(lat, lon)
        return int(math.floor(x + 0.5)), int(math.floor(y + 0.5))

    def km_per_px(self):
        return 111.32 / self.k


# ---- fading threads --------------------------------------------------------------------------------

class Trails:
    """A float image of one-LED-wide threads that fade away: fade(dt, tau) each frame, line() to add a
    step of a track. Brighter wins where threads cross (a thread never darkens another)."""

    def __init__(self, width=W, height=H):
        self.w, self.h = width, height
        self.buf = np.zeros((height, width, 3), np.float32)
        self._n = 0

    def clear(self):
        self.buf[:] = 0

    def fade(self, dt, tau):
        self.buf *= math.exp(-max(0.0, dt) / tau)
        self._n += 1
        if self._n % 24 == 0:                          # let the last faint dregs go dark, not flicker at 1-3/255
            self.buf[self.buf < 3.0] = 0.0

    def scale(self, k):
        self.buf *= k

    def line(self, p0, p1, colour):
        """Whole-LED line from p0 to p1 ((x, y) ints); a single point if they are the same."""
        import cv2
        x0, y0 = p0
        x1, y1 = p1
        xa, xb = max(0, min(x0, x1)), min(self.w - 1, max(x0, x1))
        ya, yb = max(0, min(y0, y1)), min(self.h - 1, max(y0, y1))
        if xa > xb or ya > yb:
            return
        tmp = np.zeros((yb - ya + 1, xb - xa + 1, 3), np.float32)
        col = tuple(float(c) for c in colour)
        cv2.line(tmp, (x0 - xa, y0 - ya), (x1 - xa, y1 - ya), col, 1, cv2.LINE_8)
        roi = self.buf[ya:yb + 1, xa:xb + 1]
        np.maximum(roi, tmp, out=roi)

    def over(self, base):
        """The base map with the threads on top (float32 H x W x 3, a fresh array)."""
        return np.maximum(base, self.buf)


# ---- drawing helpers -------------------------------------------------------------------------------

def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def asset_path(*parts):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", *parts)


def draw_lines(img, lines, proj, colour, closed=False):
    """Draw polylines of [lat, lon] points one LED wide into a uint8 H x W x 3 array."""
    import cv2
    col = tuple(int(c) for c in colour)
    for line in lines:
        if len(line) < 2:
            continue
        a = np.asarray(line, np.float64)
        x, y = proj.to_px(a[:, 0], a[:, 1])
        pts = np.stack([np.floor(x + 0.5), np.floor(y + 0.5)], 1).astype(np.int32)
        cv2.polylines(img, [pts.reshape(-1, 1, 2)], closed, col, 1, cv2.LINE_8)


def to_image(arr):
    """float H x W x 3 -> PIL RGB, clipped to 0..255 (what every piece's frame() returns)."""
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
