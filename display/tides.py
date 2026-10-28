"""Tides: the sea at Baltimore as it is right now. A side-on cross-section of the harbour - the stone
quay on the left with its courses a metre apart and the metres painted on it, the sand of the bottom,
the shore climbing on the right to the white Beacon on its headland - and the water standing at the
real height of the tide, so over a day it climbs the quay wall and walks up the beach and goes back
down again, twice, a little later each day. Across it rolls the swell, at the real height and period
of the Atlantic just offshore, travelling the way it really runs; under the surface a few deeper
lines follow it more and more lazily, as water does. Above, the moon in its real place in the sky and
its real phase (the sun by day), and its path of light on the water. At the bottom, in the 3x5 font,
the next high and low water (HW 18.15 3.6M, local time, metres above chart datum) and the swell.

Data: the Marine Institute's ERDDAP server (no key). The tide is the official prediction for Union
Hall, the nearest station of the Irish National Tide Gauge Network to Baltimore (dataset
imiTidePrediction, Water_Level in metres above LAT every 5 minutes, interpolated between; high and low
water from IMI_TidePrediction_HighLow). The swell is the Irish Weather Buoy Network (dataset
IWBNetwork), station M3 south-west of Mizen Head - WaveHeight (significant wave height) and Tp (peak
period) and MeanWaveDirection, hourly - with M5 off Waterford standing in when M3 is silent.
Predictions are fetched every 3 hours for the next two days, the buoy every 30 minutes, on a side
thread, and kept in panel_setup/tides_cache.json; with no data at all the tide carries on from a
harmonic estimate (the principal lunar M2 and solar S2 tides, springs and neaps following the moon)
anchored to the last high water known, so the picture never stops.

Everything is drawn on whole LEDs (no anti-aliasing): a soft line gliding between LEDs shimmers.
"""
import csv
import io
import json
import math
import os
import threading
import time
from datetime import datetime, timezone

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "panel_setup", "tides_cache.json")
LAT, LON = 51.483, -9.373                     # Baltimore harbour

ERDDAP = "https://erddap.marine.ie/erddap/tabledap/"
STATION = "Union_Hall"                        # nearest tide station to Baltimore (13 km east)
CURVE_URL = (ERDDAP + "imiTidePrediction.csv?time,Water_Level,Water_Level_ODM"
             "&stationID=%22" + STATION + "%22&time%3E=now-6hours&time%3C=now%2B2days")
EVENTS_URL = (ERDDAP + "IMI_TidePrediction_HighLow.csv?time,tide_time_category,Water_Level_ODMalin"
              "&stationID=%22" + STATION + "%22&time%3E=now-1day&time%3C=now%2B3days")
BUOY_URL = (ERDDAP + "IWBNetwork.csv?station_id,time,WaveHeight,WavePeriod,Tp,MeanWaveDirection"
            "&time%3E=now-12hours")
BUOYS = ("M3", "M5")                          # M3 off Mizen; M5 off Waterford if M3 is silent
TIDE_EVERY, BUOY_EVERY, RETRY = 3 * 3600.0, 1800.0, 300.0

# The tide when nothing is known: Union Hall's M2 and S2 (metres), mean level above LAT and a real
# high water (2026-10-28 05:50 UTC, 1.66 m OD Malin) to anchor the phase.
M2_AMP, S2_AMP, MSL_LAT, ODM_TO_LAT = 1.22, 0.40, 2.08, 2.08
ANCHOR_HW = 1793166600.0
M2_PERIOD, S2_PERIOD, SYNODIC = 12.4206012 * 3600, 12.0 * 3600, 29.530589 * 86400
SPRING_LAG = 1.5 * 86400                      # springs come ~1.5 days after new and full moon

# --- the picture ---------------------------------------------------------------------------------
PX_PER_M = 11                                 # tide drawn true to scale: 11 LEDs to the metre
DATUM_Y = 197                                 # chart datum (LAT, 0 m) on the wall
QUAY_X = 20                                   # the quay's face
QUAY_TOP = DATUM_Y - 5 * PX_PER_M
SEABED = 226
SKY_BOTTOM = QUAY_TOP - 4                     # the moon and sun live above this
SURFACE = np.array([165, 205, 232], np.float32)
DEEP = [(np.array(c, np.float32), d) for c, d in (       # lines below the surface: colour, depth
    ((100, 155, 205), 7), ((0, 155, 200), 15), ((0, 110, 175), 25), ((0, 60, 160), 38))]
STONE, STONE_DIM = (150, 135, 110), (104, 96, 84)
SAND = (160, 118, 40)
LAND = (112, 104, 96)
BEACON = (235, 232, 220)
INK = (205, 178, 120)
INK_DIM = (150, 132, 96)
MOON = np.array([240, 232, 196], np.float32)
MOON_DARK = np.array([96, 96, 104], np.float32)
SUN = np.array([255, 170, 40], np.float32)


# --- data ----------------------------------------------------------------------------------------
def _iso(s):
    return datetime.strptime(s.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def _rows(text):
    """ERDDAP .csv: a header row, a units row, then data."""
    rows = list(csv.reader(io.StringIO(text)))
    return rows[0], rows[2:]


class Sea:
    def __init__(self, fetch=True):
        self.lock = threading.Lock()
        self.data = {"curve": [], "events": [], "buoy": None, "odm_to_lat": ODM_TO_LAT}
        self.fetched = {"tide": 0.0, "buoy": 0.0}
        self._load()
        self._arrays()
        if fetch:
            threading.Thread(target=self._loop, daemon=True).start()

    def _load(self):
        try:
            with open(CACHE) as fh:
                c = json.load(fh)
            self.data.update({k: c[k] for k in ("curve", "events", "buoy", "odm_to_lat") if k in c})
            self.fetched.update(c.get("fetched", {}))
        except Exception:
            pass

    def _save(self):
        try:
            tmp = CACHE + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(dict(self.data, fetched=self.fetched), fh, separators=(",", ":"))
            os.replace(tmp, CACHE)
        except Exception as e:
            print(f"[tides] cache: {str(e)[:80]}", flush=True)

    def _arrays(self):
        c = self.data["curve"]
        with self.lock:
            self.ct = np.array([p[0] for p in c], np.float64)
            self.ch = np.array([p[1] for p in c], np.float64)

    def _loop(self):
        import requests
        while True:
            now = time.time()
            try:
                if now - self.fetched["tide"] > TIDE_EVERY or not self._covered(now + 6 * 3600):
                    self._fetch_tide(requests)
                    self.fetched["tide"] = now
                    self._save()
            except Exception as e:
                self.fetched["tide"] = now - TIDE_EVERY + RETRY        # try again in 5 minutes
                print(f"[tides] tide: {str(e)[:100]}", flush=True)
            try:
                if now - self.fetched["buoy"] > BUOY_EVERY:
                    self._fetch_buoy(requests)
                    self.fetched["buoy"] = now
                    self._save()
            except Exception as e:
                self.fetched["buoy"] = now - BUOY_EVERY + RETRY
                print(f"[tides] buoy: {str(e)[:100]}", flush=True)
            time.sleep(30)

    def _covered(self, t):
        return len(self.ct) > 1 and self.ct[0] <= time.time() and self.ct[-1] >= t

    def _fetch_tide(self, requests):
        r = requests.get(CURVE_URL, timeout=30)
        r.raise_for_status()
        head, rows = _rows(r.text)
        i_t, i_h, i_o = head.index("time"), head.index("Water_Level"), head.index("Water_Level_ODM")
        curve, offs = [], []
        for row in rows:
            try:
                t, h = _iso(row[i_t]), float(row[i_h])
            except (ValueError, IndexError):
                continue
            curve.append([t, h])
            try:
                offs.append(h - float(row[i_o]))
            except (ValueError, IndexError):
                pass
        if len(curve) < 10:
            raise ValueError("tide: too few rows")
        off = float(np.median(offs)) if offs else self.data["odm_to_lat"]
        r = requests.get(EVENTS_URL, timeout=30)
        r.raise_for_status()
        head, rows = _rows(r.text)
        i_t, i_c, i_h = head.index("time"), head.index("tide_time_category"), head.index("Water_Level_ODMalin")
        events = []
        for row in rows:
            try:
                events.append([_iso(row[i_t]), row[i_c].strip().upper()[:1], round(float(row[i_h]) + off, 2)])
            except (ValueError, IndexError):
                continue
        self.data.update(curve=sorted(curve), odm_to_lat=round(off, 3))
        if events:
            self.data["events"] = sorted(events)
        self._arrays()

    def _fetch_buoy(self, requests):
        r = requests.get(BUOY_URL, timeout=30)
        r.raise_for_status()
        head, rows = _rows(r.text)
        ix = {k: head.index(k) for k in ("station_id", "time", "WaveHeight", "WavePeriod", "Tp", "MeanWaveDirection")}
        best = {}
        for row in rows:
            try:
                st, t, hs = row[ix["station_id"]], _iso(row[ix["time"]]), float(row[ix["WaveHeight"]])
            except (ValueError, IndexError):
                continue
            if st not in BUOYS or not (0.05 < hs < 25):
                continue

            def num(k):
                try:
                    v = float(row[ix[k]])
                    return v if math.isfinite(v) else None
                except (ValueError, IndexError):
                    return None
            tp = num("Tp") or num("WavePeriod")
            if not tp or not (2 < tp < 30):
                continue
            if t >= best.get(st, {}).get("time", 0):
                best[st] = {"station": st, "time": t, "hs": hs, "tp": tp, "dir": num("MeanWaveDirection")}
        for st in BUOYS:
            if st in best:
                self.data["buoy"] = best[st]
                return
        raise ValueError("buoy: no wave rows")

    # -- reading, from frame(): no network, no waiting --
    def level(self, t):
        """Metres above LAT at time t: the prediction where it covers t, the harmonic estimate beyond."""
        with self.lock:
            ct, ch = self.ct, self.ch
        if len(ct) > 1 and ct[0] <= t <= ct[-1]:
            return float(np.interp(t, ct, ch))
        return self.harmonic(t)

    def harmonic(self, t):
        hw = ANCHOR_HW
        for e in self.data["events"]:
            if e[1] == "H" and e[0] <= t:
                hw = e[0]
        if hw < t - 30 * 86400:                     # a stale anchor is fine: M2 is very regular
            pass
        w2, ws = 2 * math.pi / M2_PERIOD, 2 * math.pi / S2_PERIOD
        tau = (moon_elongation(hw) % 180.0) / 360.0 * SYNODIC - SPRING_LAG   # since the last springs
        phi = (ws - w2) * tau                       # S2 against M2 at the anchor
        # the two together reach their crest at the anchor: shift both by the combined phase there
        cx, cy = M2_AMP + S2_AMP * math.cos(phi), S2_AMP * math.sin(phi)
        psi = math.atan2(cy, cx)
        d = t - hw
        return MSL_LAT + M2_AMP * math.cos(w2 * d - psi) + S2_AMP * math.cos(ws * d + phi - psi)

    def next_events(self, now):
        """The next high and the next low water, [(time, 'H'|'L', metres LAT), ...] in time order."""
        out = {}
        for t, k, h in self.data["events"]:
            if t > now and k not in out:
                out[k] = (t, k, h)
        if len(out) < 2:                                # no predictions ahead: from the model
            ts = now + np.arange(0, 26 * 3600, 300.0)
            hs = np.array([self.level(x) for x in ts])
            for i in range(1, len(ts) - 1):
                k = "H" if hs[i] >= hs[i - 1] and hs[i] > hs[i + 1] else "L" if hs[i] <= hs[i - 1] and hs[i] < hs[i + 1] else None
                if k and k not in out:
                    out[k] = (ts[i], k, round(float(hs[i]), 1))
        return sorted(out.values())

    def swell(self, now):
        """(Hs metres, period s, direction from, fresh?)"""
        b = self.data.get("buoy")
        if not b:
            return 1.0, 9.0, 260.0, False
        return b["hs"], b["tp"], b.get("dir") if b.get("dir") is not None else 260.0, now - b["time"] < 12 * 3600


# --- the sky: low-precision sun and moon (about a degree; enough for a picture) ------------------
def _days(t):
    return t / 86400.0 + 2440587.5 - 2451545.0


def _sun_ecl(d):
    g = math.radians(357.529 + 0.98560028 * d)
    return (280.459 + 0.98564736 * d + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360.0


def _moon_ecl(d):
    L = 218.316 + 13.176396 * d
    M = math.radians(134.963 + 13.064993 * d)
    F = math.radians(93.272 + 13.229350 * d)
    D = math.radians(297.850 + 12.190749 * d)
    lam = L + 6.289 * math.sin(M) + 1.274 * math.sin(2 * D - M) + 0.658 * math.sin(2 * D) + 0.214 * math.sin(2 * M)
    return lam % 360.0, 5.128 * math.sin(F)


def moon_elongation(t):
    """Moon's ecliptic longitude minus the sun's, degrees 0..360 (0 new, 180 full)."""
    d = _days(t)
    return (_moon_ecl(d)[0] - _sun_ecl(d)) % 360.0


def _altaz(lam, beta, d):
    e = math.radians(23.439 - 0.00000036 * d)
    lam, beta = math.radians(lam), math.radians(beta)
    ra = math.atan2(math.sin(lam) * math.cos(e) - math.tan(beta) * math.sin(e), math.cos(lam))
    dec = math.asin(math.sin(beta) * math.cos(e) + math.cos(beta) * math.sin(e) * math.sin(lam))
    ha = math.radians((280.46061837 + 360.98564736629 * d + LON) % 360.0) - ra
    phi = math.radians(LAT)
    alt = math.asin(math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha), math.tan(dec) * math.cos(phi) - math.sin(phi) * math.cos(ha))
    return math.degrees(alt), math.degrees(az) % 360.0


def sky(t):
    """{'sun': (alt, az), 'moon': (alt, az), 'elong': deg, 'beta': deg}"""
    d = _days(t)
    ls = _sun_ecl(d)
    lm, bm = _moon_ecl(d)
    return {"sun": _altaz(ls, 0.0, d), "moon": _altaz(lm, bm, d), "elong": (lm - ls) % 360.0, "beta": bm}


def sky_px(alt, az):
    """Looking out of the harbour to the south: east on the left, west on the right; the zenith up top."""
    x = (az - 90.0) / 180.0 * (W - 40) + 20
    y = SKY_BOTTOM - 8 - max(0.0, alt) / 62.0 * (SKY_BOTTOM - 24)
    return int(round(min(W - 9, max(QUAY_X + 8, x)))), int(round(max(10, y)))


def disc(r, sun_dir, phase_angle):
    """Masks (lit, dark) of a sphere of radius r seen whole-LED, lit from screen direction sun_dir
    (unit dx, dy) with the given phase angle (0 full, 180 new)."""
    n = 2 * r + 1
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    inside = xx * xx + yy * yy <= (r + 0.35) ** 2
    zz = np.sqrt(np.maximum(0.0, r * r - xx * xx - yy * yy))
    i = math.radians(phase_angle)
    sx, sy, sz = math.sin(i) * sun_dir[0], math.sin(i) * sun_dir[1], math.cos(i)
    lit = inside & ((xx * sx + yy * sy + zz * sz) > 0.0)
    return lit, inside & ~lit


# --- the still parts -----------------------------------------------------------------------------
def _ground():
    """y of the bottom (sand, then the shore and headland) for every column."""
    x = np.arange(W, dtype=np.float32)
    g = SEABED + 2.0 * np.sin(x / 9.0) + 1.5 * np.sin(x / 23.0 + 1.0)
    shore = np.clip((x - 112) / 80.0, 0, 1)                              # the shore, rising right
    climb = SEABED - (SEABED - (QUAY_TOP - 26)) * shore ** 1.6 + 1.5 * np.sin(x / 5.0) * shore
    g = np.where(x >= 112, np.minimum(g, climb), g)
    g[x < QUAY_X] = SEABED
    return np.round(g).astype(np.int32)


def base_picture():
    img = np.zeros((H, W, 3), np.uint8)
    g = _ground()
    from display import pixelfont
    # the sand and the shore: one line, whole LEDs, gaps closed
    for x in range(QUAY_X, W):
        a = g[x]
        b = g[x - 1] if x > QUAY_X else a
        lo, hi = min(a, b + (1 if b < a else 0)), max(a, b - (1 if b > a else 0))
        col = SAND if a > DATUM_Y - 6 * PX_PER_M + 40 else LAND
        img[min(lo, a):max(hi, a) + 1, x] = col
    # a few stones on the bottom
    for sx in (37, 58, 96):
        img[g[sx] - 1, sx:sx + 2] = SAND
    # the Beacon (Lot's Wife) on the headland: a white cone
    bx = 176
    top = g[bx] - 1
    for k in range(11):
        hw = k // 4
        img[top - 10 + k, bx - hw:bx + hw + 1] = BEACON
    # the quay: its face, its top, courses a metre apart and the metres painted on it
    img[QUAY_TOP:SEABED + 1, QUAY_X - 1] = STONE
    img[QUAY_TOP, 0:QUAY_X] = STONE
    img[QUAY_TOP - 3:QUAY_TOP, 7:10] = STONE_DIM                          # a bollard
    for m in range(0, 5):
        y = DATUM_Y - m * PX_PER_M
        img[y, 2:QUAY_X - 1] = STONE_DIM
        img[y, QUAY_X - 4:QUAY_X - 1] = STONE
        if m > 0:
            pixelfont.draw(img, str(m), QUAY_X - 9, y - 7, STONE)
    return img, g


def _text_lines(sea, now):
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Dublin")
    lines = []
    for t, k, h in sea.next_events(now):
        hm = datetime.fromtimestamp(t, tz).strftime("%H.%M")
        lines.append(("HW " if k == "H" else "LW ") + hm + " " + f"{h:.1f}" + "M")
    hs, tp, _, fresh = sea.swell(now)
    if fresh:
        lines.append(f"SWELL {hs:.1f}M {tp:.0f}S")
    return lines


# --- the live picture ----------------------------------------------------------------------------
class Harbour:
    def __init__(self, fetch=True):
        self.sea = Sea(fetch=fetch)
        self.base, self.ground = base_picture()
        self.rows = np.arange(H, dtype=np.int32)[:, None]
        self.xs = np.arange(W, dtype=np.float32)
        self.slow_at, self.slow = -1e9, None
        self.stars = self._stars()

    @staticmethod
    def _stars():
        rng = np.random.default_rng(7)
        out = []
        while len(out) < 34:
            x, y = int(rng.integers(26, W - 2)), int(rng.integers(4, SKY_BOTTOM - 12))
            out.append((x, y, 104 + int(rng.integers(0, 3)) * 30))
        return out

    def _slow_layer(self, now):
        """Everything that changes slower than once a minute: sky, moon, sun, words, tide level."""
        from display import pixelfont
        img = self.base.copy()
        sk = sky(now)
        sun_alt, sun_az = sk["sun"]
        moon_alt, moon_az = sk["moon"]
        g = self.ground
        night = sun_alt < -6
        if night:
            for x, y, v in self.stars:
                if y < g[x] - 4:
                    img[y, x] = (v, v, min(255, v + 12))
        lights = []                                           # (x, colour, strength) for paths on the water
        if sun_alt > -1:
            sx, sy = sky_px(sun_alt, sun_az)
            lit, _ = disc(4, (0, 1), 0)
            self._stamp(img, sx, sy, lit, SUN)
            lights.append((sx, SUN, 1.0))
        illum = (1 - math.cos(math.radians(sk["elong"]))) / 2
        moon_px = None
        if moon_alt > -1:
            mx, my = sky_px(moon_alt, moon_az)
            dx = ((sun_az - moon_az + 180) % 360 - 180)
            dy = -(sun_alt - moon_alt)
            n = math.hypot(dx, dy) or 1.0
            phase_angle = 180.0 - math.degrees(math.acos(max(-1, min(1, math.cos(math.radians(sk["elong"])) * math.cos(math.radians(sk["beta"]))))))
            lit, dark = disc(6, (dx / n, dy / n), phase_angle)
            if night and illum < 0.6:
                rim = dark & ~np.pad(np.pad(dark, 1)[2:, 1:-1] & np.pad(dark, 1)[:-2, 1:-1]
                                     & np.pad(dark, 1)[1:-1, 2:] & np.pad(dark, 1)[1:-1, :-2], 0)
                self._stamp(img, mx, my, rim, MOON_DARK)     # earthshine: the old moon's dark rim
            self._stamp(img, mx, my, lit, MOON * (0.85 if not night else 1.0))
            if night and illum > 0.08:
                lights.append((mx, MOON, illum))
            moon_px = (mx, my)
        # the words, bottom left, under the sand
        lines = _text_lines(self.sea, now)
        y = H - 2 - 7 * len(lines)
        for i, s in enumerate(lines):
            col = INK if i < 2 else INK_DIM
            if s.startswith(("HW", "LW")):
                pixelfont.draw(img, s[:2], 4, y, INK_DIM)
                pixelfont.draw(img, s[3:], 4 + 12, y, col)
            else:
                pixelfont.draw(img, s, 4, y, col)
            y += 7
        # the moon's phase beside the words when it is below the horizon
        if moon_px is None:
            lit, dark = disc(2, (1.0 if sk["elong"] < 180 else -1.0, 0.0),
                             180.0 - sk["elong"] if sk["elong"] < 180 else sk["elong"] - 180.0)
            cx, cy = W - 8, H - 2 - 7 * len(lines) + 2
            self._stamp(img, cx, cy, lit, MOON)
        hs, tp, wdir, _ = self.sea.swell(now)
        return {"img": img, "lights": lights, "hs": hs, "tp": tp, "dir": wdir}

    @staticmethod
    def _stamp(img, cx, cy, mask, col):
        r = mask.shape[0] // 2
        ys, xs = np.nonzero(mask)
        ys, xs = ys + cy - r, xs + cx - r
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
        img[ys[ok], xs[ok]] = np.clip(col, 0, 255).astype(np.uint8)

    def _line(self, img, y, col, below):
        """One whole-LED line along y (float per column), columns QUAY_X.., gaps on steep slopes closed,
        never into the ground and never above `below` (the surface, for the deeper lines)."""
        yi = np.round(y).astype(np.int32)
        prev = np.concatenate([yi[:1], yi[:-1]])
        lo = np.minimum(yi, np.where(prev < yi, prev + 1, yi))
        hi = np.maximum(yi, np.where(prev > yi, prev - 1, yi))
        lo = np.maximum(lo, below)
        hi = np.minimum(hi, self.ground - 1)
        band0, band1 = max(0, int(lo.min())), min(H, int(hi.max()) + 1)
        if band1 <= band0:
            return
        rows = self.rows[band0:band1]
        m = (rows >= lo[None, :]) & (rows <= hi[None, :])
        m[:, :QUAY_X] = False
        sub = img[band0:band1]
        sub[m] = col.astype(np.uint8)

    def __call__(self, t):
        now = time.time()
        if now - self.slow_at > 20 or self.slow is None:
            self.slow, self.slow_at = self._slow_layer(now), now
        s = self.slow
        img = s["img"].copy()
        level = self.sea.level(now)
        mean_y = DATUM_Y - level * PX_PER_M
        # the swell: deep-water wavelength from the period, drawn shortened so a few crests show
        hs, tp = s["hs"], s["tp"]
        L = 9.81 * tp * tp / (2 * math.pi)                      # metres
        lam = max(60.0, min(150.0, L * 0.7))                    # LEDs
        amp = min(16.0, hs * 0.5 * PX_PER_M * 0.45)             # sheltered in the harbour
        towards = ((s["dir"] or 260.0) + 180.0) % 360.0
        sign = -1.0 if math.sin(math.radians(towards)) >= 0 else 1.0     # east is on the left
        k = 2 * math.pi / lam
        w = 2 * math.pi / tp
        ph0 = (sign * w * now) % (2 * math.pi)                  # in float64 first: now is ~1.8e9
        ph = k * self.xs - ph0
        chop_l = lam * 0.29
        ph1 = (sign * w * 1.007 * now) % (2 * math.pi)
        chop = 0.22 * amp * np.sin(2 * math.pi / chop_l * self.xs - ph1 + 1.3)
        # a slight peak to the crests (troughs long, crests short), as a real swell
        wave = amp * (np.sin(ph) + 0.18 * np.cos(2 * ph))
        surf = mean_y - wave - chop
        surf_i = np.round(surf).astype(np.int32)
        for col, depth in reversed(DEEP):
            lag = depth * 0.06
            damp = math.exp(-k * depth * 1.2)
            y = mean_y + depth - damp * amp * np.sin(ph - lag)
            self._line(img, y, col, surf_i + 2)
        self._line(img, surf, SURFACE, np.zeros(W, np.int32))
        # the path of light under the moon or sun: whole LEDs on the surface and just beneath,
        # each one coming and going on its own slow beat
        for lx, col, strength in s["lights"]:
            half = int(4 + amp * 0.6)
            slot = int(now / 0.7)
            for x in range(max(QUAY_X, lx - half), min(W, lx + half + 1)):
                for j, dy in enumerate((0, 3, 6, 10)):
                    yy = surf_i[x] + dy
                    if yy >= self.ground[x]:
                        break
                    hsh = (x * 73856093 ^ dy * 19349663 ^ slot * 83492791) & 0xFFFF
                    p = (1 - abs(x - lx) / (half + 1)) * strength * (0.9 - 0.2 * j)
                    if hsh / 65535.0 < p * 0.55:
                        img[yy, x] = np.clip(col * (1.0 if dy == 0 else 0.8), 0, 255).astype(np.uint8)
        return Image.fromarray(img, "RGB")


_h = None


def thumb():
    """A still for the app (from the cache if there is one; no network)."""
    return Harbour(fetch=False)(0.0)


def frame(t):
    global _h
    if _h is None:
        _h = Harbour()
    return _h(t)
