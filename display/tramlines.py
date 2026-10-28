"""Tram map: every Zürich tram moving on an Underground-style map of its lines.

The map is the schematic from tools/build_trams.py (assets/trams/layout.json: every stop on a whole LED,
every link a straight run with at most one 45 degree bend, the centre magnified) and the timetable next to
it (assets/trams/zurich_trams.json.gz: the VBZ trams for a week). Under it all is a still drawing: the
links as faint lines (grey where several lines share them, tinted where one line has them to itself), a dot
per stop, a few names and a marker on Rennweg, the apartment's stop.

Every frame the real clock (Europe/Zürich) is looked up in the timetable: each trip that is on the road
now - today's, and yesterday's that run past midnight - is placed between its stops by its own arrival and
departure times and drawn as one bright LED in its line's colour with a short fading trail behind it.
Timetable only: the trams are where they should be, not where they are (no network, no delays).

Everything is whole LEDs, no anti-aliasing (a soft dot gliding between LEDs shimmers). A tram steps from
LED to LED along its route, so a link a minute long is crossed in a few LED-steps: slow, like the real thing.
"""
import bisect
import datetime
import gzip
import itertools
import json
import math
import os
import threading
import time

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
TZ = "Europe/Zurich"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "assets", "trams", "zurich_trams.json.gz")
LAYOUT = os.path.join(HERE, "assets", "trams", "layout.json")

TRAIL = (0.62, 0.45, 0.32, 0.22, 0.15, 0.10, 0.06)       # LEDs behind the head, as a share of its brightness
EDGE_SHARED = (30, 30, 38)                         # a link several lines run along
EDGE_TINT = 0.34                                   # a link one line has to itself: its colour at this level
STOP, STOP_HUB = (78, 78, 92), (150, 150, 165)    # a stop; one where three or more lines meet
LABEL = (62, 62, 80)
HOME_MARK = (255, 200, 90)
# Lines whose paper colour is black (7, 50, 51) or too dark/close to another to read on an LED become
# these; everything else is the line colour stretched to full brightness.
LED = {"5": (235, 112, 38), "7": (160, 165, 175), "50": (235, 235, 235), "51": (235, 235, 235)}


LIVE_URL = "https://api.opentransportdata.swiss/la/gtfs-rt"      # the whole country, ~9 MB, GTFS-RT trip updates
LIVE_EVERY = float(os.environ.get("TRAM_LIVE_SECS", 120))           # seconds between downloads (~4 GB a day at 120)
LIVE_IDLE = 120.0                                                  # no frame drawn for this long: stop fetching
LIVE_STALE = 600.0                                                 # delays older than this are not trusted
SLACK = 1800                                                       # a late tram may still be on the road this long after its timetable
LIVE_MARK = (40, 150, 70)
OFF_MARK = (70, 70, 80)


class Live:
    """Real delays and cancellations for the timetable's trips from opentransportdata.swiss (GTFS-RT, free key in
    OTD_API_KEY). Fetched on a side thread while the piece is showing; without a key, the protobuf package
    (gtfs-realtime-bindings) or a network the trams simply run to the timetable."""

    def __init__(self, trip_ids, fetch=True):
        self.ids = set(trip_ids)
        self.delay, self.cancelled, self.t = {}, set(), 0.0
        self.last_frame = time.time()
        self.key = os.environ.get("OTD_API_KEY", "").strip()
        if fetch and self.key and self.key != "your_key_here":
            threading.Thread(target=self._loop, daemon=True).start()

    @staticmethod
    def parse(blob, ids):
        """GTFS-RT bytes -> ({trip_id: delay seconds}, {cancelled trip ids}) for the trip ids we know."""
        from google.transit import gtfs_realtime_pb2 as pb
        feed = pb.FeedMessage()
        feed.ParseFromString(blob)
        delay, cancelled = {}, set()
        for e in feed.entity:
            if not e.HasField("trip_update"):
                continue
            tu = e.trip_update
            tid = tu.trip.trip_id
            if tid not in ids:
                continue
            if tu.trip.schedule_relationship == 3:                   # CANCELED
                cancelled.add(tid)
                continue
            d = None
            for su in tu.stop_time_update:                           # the first stop that reports a delay
                for ev in (su.arrival, su.departure):
                    if ev.HasField("delay"):
                        d = ev.delay
                        break
                if d is not None:
                    break
            if d is None and tu.HasField("delay"):
                d = tu.delay
            if d:
                delay[tid] = int(d)
        return delay, cancelled

    def _loop(self):
        import requests
        backoff = 30.0
        while True:
            if time.time() - self.last_frame > LIVE_IDLE:
                time.sleep(5)
                continue
            wait = LIVE_EVERY
            try:
                r = requests.get(LIVE_URL, headers={"Authorization": "Bearer " + self.key,
                                                    "User-Agent": "fortuna-wall/1.0 (private art project)"}, timeout=90)
                r.raise_for_status()
                delay, cancelled = self.parse(r.content, self.ids)
                self.delay, self.cancelled, self.t = delay, cancelled, time.time()
                backoff = 30.0
            except Exception as e:
                print(f"[trams] live: {str(e)[:100]}", flush=True)
                wait, backoff = backoff, min(900.0, backoff * 2)
            time.sleep(wait)

    def fresh(self):
        return self.t and time.time() - self.t < LIVE_STALE


def _now():
    """The wall clock in Zürich. Tests replace this."""
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo(TZ))


def _led(line, hex_):
    if line in LED:
        return np.array(LED[line], np.float32)
    c = np.array([int(hex_[i:i + 2], 16) for i in (0, 2, 4)], np.float32)
    return c * (255.0 / max(c.max(), 1.0))


def _pixels(pts):
    """Every whole LED on a polyline of 0/45/90 degree segments, in order, corners not repeated."""
    out = [tuple(pts[0])]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(abs(x1 - x0), abs(y1 - y0))
        sx, sy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
        out += [(x0 + sx * i, y0 + sy * i) for i in range(1, n + 1)]
    return out


class TramMap:
    def __init__(self):
        with gzip.open(DATA, "rt") as fh:
            d = json.load(fh)
        with open(LAYOUT) as fh:
            lay = json.load(fh)
        self.days = [datetime.date.fromisoformat(x) for x in d["days"]]
        self.patterns, self.profiles = d["patterns"], d["profiles"]
        self.lay = lay
        self.colour = {l: _led(l, c) for l, c in d["lines"].items()}
        trips = d["trips"]
        self.t0 = np.array([t[2] for t in trips], np.int64)             # sorted by the builder
        self.pat = np.array([t[0] for t in trips], np.int32)
        self.prof = np.array([t[1] for t in trips], np.int32)
        self.mask = np.array([t[3] for t in trips], np.int64)
        total = np.array([sum(p) for p in self.profiles], np.int64)     # a profile's last arrival
        self.end = self.t0 + total[self.prof]
        self.tid = [t[4] for t in trips]
        order = np.argsort(self.t0, kind="stable")
        if not (order == np.arange(len(order))).all():              # the builder sorts them; be safe
            self._resort(order)
        self.span = int((self.end - self.t0).max()) if len(trips) else 0
        self._prof_cache, self._route_cache = {}, {}
        self.edge = {}
        for e in lay["edges"]:
            self.edge[(e["a"], e["b"])] = e["pts"]
        self.sx = [s[0] for s in lay["stops"]]
        self.sy = [s[1] for s in lay["stops"]]
        self.live = Live(self.tid)
        self.base = self._base()
        self.home = lay["stops"][lay["home"]][:2]
        for p in range(len(self.patterns)):                    # the routes once, so no frame pays for one
            self._route(p)

    def _resort(self, order):
        self.t0, self.pat, self.prof, self.mask, self.end = (a[order] for a in
                                                            (self.t0, self.pat, self.prof, self.mask, self.end))
        self.tid = [self.tid[i] for i in order]
        return True

    # ---- the still map -------------------------------------------------------------------------------
    def _base(self):
        img = np.zeros((H, W, 3), np.uint8)
        lay = self.lay
        hub = {}
        for e in lay["edges"]:
            for s in (e["a"], e["b"]):
                hub.setdefault(s, set()).update(e["lines"])
        shared = [e for e in lay["edges"] if len(e["lines"]) != 1]
        single = [e for e in lay["edges"] if len(e["lines"]) == 1]
        for group in (shared, single):
            for e in group:
                col = (np.array(EDGE_SHARED, np.float32) if len(e["lines"]) != 1
                       else self.colour.get(e["lines"][0], np.array(EDGE_SHARED, np.float32)) * EDGE_TINT)
                for x, y in _pixels(e["pts"]):
                    if 0 <= x < W and 0 <= y < H:
                        img[y, x] = np.maximum(img[y, x], col.astype(np.uint8))
        for s, ls in hub.items():
            x, y = self.lay["stops"][s][:2]
            if 0 <= x < W and 0 <= y < H:
                img[y, x] = STOP_HUB if len(ls) >= 3 else STOP
        hx, hy = lay["stops"][lay["home"]][:2]
        img[hy, hx] = HOME_MARK
        from display import pixelfont
        for x, y, text in lay["labels"]:
            pixelfont.draw(img, text, x, y, LABEL)
        return img

    # ---- a profile, a pattern's route --------------------------------------------------------------------
    def _times(self, q):
        t = self._prof_cache.get(q)
        if t is None:
            t = self._prof_cache[q] = list(itertools.accumulate(self.profiles[q]))   # arr0, dep0, arr1, dep1...
        return t

    def _route(self, p):
        """(route LEDs as [(x, y)...], index of each stop of pattern p within them)."""
        r = self._route_cache.get(p)
        if r is None:
            seq = self.patterns[p][1]
            leds, at = [], [0]
            for a, b in zip(seq, seq[1:]):
                if (a, b) in self.edge:
                    pts = self.edge[(a, b)]
                elif (b, a) in self.edge:
                    pts = self.edge[(b, a)]
                else:
                    pts = [[self.sx[a], self.sy[a]], [self.sx[b], self.sy[b]]]
                if tuple(pts[0]) != (self.sx[a], self.sy[a]):          # stored from b to a
                    pts = pts[::-1]
                run = _pixels(pts)
                leds += run[1:] if leds else run
                at.append(len(leds) - 1)
            r = self._route_cache[p] = (leds, at)
        return r

    def _at(self, p, q, tau):
        """Position (index into the route's LEDs, as a float) of a trip of pattern p, profile q, tau seconds
        after its first departure; None if it is not on the road."""
        t = self._times(q)
        if tau < 0 or tau > t[-1]:
            return None
        _, at = self._route(p)
        k = bisect.bisect_right(t, tau) - 1                    # t[2i] arrival at stop i, t[2i+1] its departure
        if k >= len(t) - 1:
            return float(at[-1])
        i = k >> 1
        if k & 1 == 0:                                         # in the stop, until it leaves
            return float(at[i])
        span = t[k + 1] - t[k]                                 # on the way to stop i + 1
        f = (tau - t[k]) / span if span > 0 else 1.0
        return at[i] + (at[i + 1] - at[i]) * f

    # ---- a frame ------------------------------------------------------------------------------------------
    def day_index(self, date):
        """Which of the timetable's days stands for this date (the nearest one with the same weekday, when it is not covered)."""
        if date in self.days:
            return self.days.index(date)
        same = [i for i, d in enumerate(self.days) if d.weekday() == date.weekday()]
        return min(same or range(len(self.days)), key=lambda i: abs((self.days[i] - date).days))

    def active(self, di, secs, slack=0):
        """Trips of timetable day di on the road at secs after that day's midnight: (pattern, profile, tau, trip index).
        With slack, also the trips that finished up to that many seconds ago (a late tram is still driving)."""
        if di < 0 or not len(self.t0):
            return []
        lo = int(np.searchsorted(self.t0, secs - self.span - slack, "left"))
        hi = int(np.searchsorted(self.t0, secs, "right"))
        if lo >= hi:
            return []
        sl = slice(lo, hi)
        ok = (((self.mask[sl] >> di) & 1) == 1) & (self.end[sl] >= secs - slack)
        idx = np.nonzero(ok)[0] + lo
        return [(int(self.pat[i]), int(self.prof[i]), secs - int(self.t0[i]), int(i)) for i in idx]

    def trams(self, now):
        """Every tram on the road at the aware datetime `now`: [(line, route, position)...]."""
        local = now.astimezone(_zone())
        today = local.date()
        di = self.day_index(today)
        if self.days[di] != today:                              # not in the timetable: the same time, nearest day
            local = datetime.datetime.combine(self.days[di], local.timetz())
            local = local.replace(tzinfo=_zone())
        midnight = _service_midnight(local.date())
        secs = (local.astimezone(datetime.timezone.utc) - midnight).total_seconds()
        live = self.live if (self.live.fresh() and self.days[di] == today) else None     # delays only for the real today
        delay, cancelled = (live.delay, live.cancelled) if live else ({}, set())
        out = []
        for d, s in ((di, secs), (di - 1, secs + _day_len(self.days[di] - datetime.timedelta(1)))):
            for p, q, tau, i in self.active(d, s, SLACK if live else 0):
                tid = self.tid[i]
                if tid in cancelled:
                    continue
                pos = self._at(p, q, tau - delay.get(tid, 0))             # a late tram is where the timetable had it, that much ago
                if pos is not None:
                    out.append((self.patterns[p][0], p, pos))
        return out

    def render(self, now):
        img = self.base.copy()
        heads = []
        trail = []
        for line, p, pos in self.trams(now):
            leds = self._route(p)[0]
            h = int(pos + 0.5)
            col = self.colour.get(line, np.array((200, 200, 200), np.float32))
            for k, f in enumerate(TRAIL, 1):
                j = h - k
                if j >= 0:
                    trail.append((leds[j], col * f))
            heads.append((leds[min(h, len(leds) - 1)], col))
        for (x, y), c in trail:
            if 0 <= x < W and 0 <= y < H:
                img[y, x] = np.maximum(img[y, x], c.astype(np.uint8))
        for (x, y), c in heads:
            if 0 <= x < W and 0 <= y < H:
                img[y, x] = c.astype(np.uint8)
        self.live.last_frame = time.time()
        from display import pixelfont
        pixelfont.draw(img, "LIVE" if self.live.fresh() else "TIMETABLE", 2, H - 7, LIVE_MARK if self.live.fresh() else OFF_MARK)
        hx, hy = self.home
        pulse = 0.5 + 0.5 * math.sin(now.timestamp() * 2.0) ** 2
        mark = np.array(HOME_MARK, np.float32) * pulse
        for dx, dy in ((-2, -2), (2, -2), (-2, 2), (2, 2), (0, -3), (0, 3), (-3, 0), (3, 0)):
            x, y = hx + dx, hy + dy
            if 0 <= x < W and 0 <= y < H:
                img[y, x] = np.maximum(img[y, x], mark.astype(np.uint8))
        return img, len(heads)


def _zone():
    from zoneinfo import ZoneInfo
    return ZoneInfo(TZ)


def _service_midnight(date):
    """GTFS counts service seconds from 'noon minus 12 hours' of the day (so it is right across DST changes)."""
    noon = datetime.datetime(date.year, date.month, date.day, 12, tzinfo=_zone())
    return noon.astimezone(datetime.timezone.utc) - datetime.timedelta(hours=12)


def _day_len(date):
    """Seconds from one service midnight to the next (86400, give or take a DST hour)."""
    return (_service_midnight(date + datetime.timedelta(1)) - _service_midnight(date)).total_seconds()


_map = None


def _get():
    global _map
    if _map is None:
        _map = TramMap()
    return _map


def frame(t):
    """The wall now: a PIL image like the other live pieces (t, the animation clock, is not used: the
    trams follow the real one)."""
    arr, _ = _get().render(_now())
    return Image.fromarray(arr, "RGB")


def thumb():
    """A still for the app: the map in the early evening rush of a weekday of the timetable (no network)."""
    m = _get()
    today = _now().date()
    wk = [d for d in m.days if d.weekday() < 5] or m.days
    day = min(wk, key=lambda d: abs((d - today).days))
    when = datetime.datetime(day.year, day.month, day.day, 17, 30, tzinfo=_zone())
    arr, _ = m.render(when)
    return Image.fromarray(arr, "RGB")
