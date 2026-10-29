"""Zürich trams: the VBZ tram network as a schematic map in the manner of the London Underground - every
line in its own VBZ colour, one LED wide, straight runs and clean 45-degree bends, lines that share a
track running side by side - and every tram in service right now as a small bright bead travelling
along its line, stop to stop, at its timetabled position (plus its live delay when there is a key).
A tram brightens in at its first stop and fades out at its last, so the map is quiet at night with a
handful of last trams and busy at rush hour. Interchanges are small white rings, a few places are
named, and the home stop, Rennweg, is a warm dot.

The timetable and the schematic are committed (assets/trams/, from tools/build_trams.py, refreshed
twice a week by .github/workflows/trams.yml), so the map runs on schedule alone with no network.
With OTD_API_KEY set (.env), a side thread reads the GTFS-RT trip updates of opentransportdata.swiss
every 90 s (the free tier allows two calls a minute) and moves each tram by its reported delay;
cancelled trips leave the map. The Swiss feed is large, so it is parsed in a short-lived child
process: the panel's frames never wait for it. The last delays are kept in
panel_setup/tramlines_cache.json for a quick restart.

Everything is drawn on whole LEDs (no anti-aliasing).
"""
import datetime
import gzip
import bisect
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time

if __name__ == "__main__":                              # the child that parses the live feed
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "trams", "zurich_trams.json.gz")
LAYOUT = os.path.join(ROOT, "assets", "trams", "layout.json")
CACHE = os.path.join(ROOT, "panel_setup", "tramlines_cache.json")
RT_URL = "https://api.opentransportdata.swiss/la/gtfs-rt"
EVERY = 90.0                              # seconds between live calls (the limit is 2 a minute)
STALE = 15 * 60.0                         # delays older than this are forgotten
TZ = "Europe/Zurich"
FADE = 40.0                               # seconds a tram takes to brighten in at its first stop / fade at its last
LINE_PEAK = 120.0                         # the network, dim (its brightest channel; ~94 is black on the LEDs)
TRAM_PEAK = 255.0                         # the trams: their line's colour at full strength, a white core
# On black LEDs the black line 7 and the construction lines 50/51 (black on paper) become greys.
DISPLAY = {"7": (150, 150, 158), "50": (205, 190, 165), "51": (205, 190, 165)}
LABEL_COL = (150, 150, 160)
RING_COL = (150, 150, 160)
HOME_COL = (255, 170, 60)


def _rgb(hexs):
    return tuple(int(hexs[i:i + 2], 16) for i in (0, 2, 4))


def _walk(corners):
    """Every LED along a polyline, one per step (a diagonal step counts one)."""
    out = [(int(corners[0][0]), int(corners[0][1]))]
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        n = int(max(abs(x1 - x0), abs(y1 - y0)))
        for i in range(1, n + 1):
            p = (int(round(x0 + (x1 - x0) * i / n)), int(round(y0 + (y1 - y0) * i / n)))
            if p != out[-1]:
                out.append(p)
    return out


def _offset(corners, slot):
    """The corner points of a route shifted `slot` LEDs to its side: horizontal and vertical runs move
    across, diagonal runs move sideways by one LED per slot, so neighbouring lines touch and never gap."""
    if slot == 0:
        return [tuple(c) for c in corners]
    segs = []
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        dx, dy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
        nx, ny = -dy, dx                                    # the side the slot counts towards
        o = (nx * slot, 0) if (nx and ny) else (nx * slot, ny * slot)
        segs.append(((x0 + o[0], y0 + o[1]), (dx, dy)))
    pts = [segs[0][0]]
    for (p, d), (q, e) in zip(segs, segs[1:]):
        den = d[0] * e[1] - d[1] * e[0]
        if den == 0:
            pts.append(q)
            continue
        t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
        pts.append((round(p[0] + d[0] * t), round(p[1] + d[1] * t)))
    last = corners[-1]
    (x0, y0), (x1, y1) = corners[-2], corners[-1]
    dx, dy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
    nx, ny = -dy, dx
    o = (nx * slot, 0) if (nx and ny) else (nx * slot, ny * slot)
    pts.append((last[0] + o[0], last[1] + o[1]))
    return pts


def _load_env_key():
    key = os.environ.get("OTD_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(os.path.join(ROOT, ".env")) as fh:
            for ln in fh:
                if ln.strip().startswith("OTD_API_KEY="):
                    return ln.split("=", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return ""


class Trams:
    def __init__(self, fetch=True):
        from zoneinfo import ZoneInfo
        self.tz = ZoneInfo(TZ)
        with gzip.open(DATA, "rt") as fh:
            d = json.load(fh)
        with open(LAYOUT) as fh:
            lay = json.load(fh)
        self.days = [datetime.date.fromisoformat(s) for s in d["days"]]
        self.colour = {}
        for l, c in d["lines"].items():
            v = np.array(DISPLAY.get(l, _rgb(c)), np.float32)
            self.colour[l] = v * (TRAM_PEAK / max(1.0, float(v.max())))
        self.dim = {l: v * (LINE_PEAK / max(1.0, float(v.max()))) for l, v in self.colour.items()}
        keys = [s[3] for s in d["stops"]]
        self._build_map(lay)
        self._build_patterns(d, keys)
        # trips: arrays for the quick "who is out now" test
        tr = d["trips"]
        self.t_pat = np.array([r[0] for r in tr], np.int32)
        self.t_prof = np.array([r[1] for r in tr], np.int32)
        self.t_t0 = np.array([r[2] for r in tr], np.float64)
        self.t_mask = np.array([r[3] for r in tr], np.int64)
        self.t_id = [r[4] for r in tr]
        self.id_index = {tid: i for i, tid in enumerate(self.t_id)}
        self.profiles = [np.cumsum(p).astype(np.float64) for p in d["profiles"]]
        self.t_dur = np.array([self.profiles[p][-1] for p in self.t_prof], np.float64)
        self.t_ok = np.array([self.pat_ok[p] for p in self.t_pat], bool)
        self.delays, self.cancelled, self.rt_at = {}, set(), 0.0
        self.active, self.active_at, self.active_rt, self._entries = [], -1e9, 0.0, {}
        self._load_cache()
        if fetch:
            threading.Thread(target=self._fetch_loop, daemon=True).start()

    # ------------------------------------------------------------------ the map
    def _build_map(self, lay):
        self.xy = {k: (v[0], v[1]) for k, v in lay["stops"].items()}
        self.names = {k: v[2] for k, v in lay["stops"].items()}
        self.links = []
        self.nbr = {}                                       # stop -> {stop: (link, i, j)}
        for k, (stops, at, corners, lines) in enumerate(lay["links"]):
            n = len(lines)
            paths = {}
            cl = len(_walk(corners))
            for i, line in enumerate(lines):
                slot = i - (n - 1) // 2
                p = _walk(_offset(corners, slot))
                paths[line] = p
            self.links.append({"stops": stops, "at": at, "len": cl, "paths": paths,
                               "centre": _walk(corners), "lines": lines})
            for i, (u, v) in enumerate(zip(stops, stops[1:])):
                self.nbr.setdefault(u, {})[v] = (k, i, i + 1, at[i + 1] - at[i])
                self.nbr.setdefault(v, {})[u] = (k, i + 1, i, at[i + 1] - at[i])
        self.labels, self.home = lay.get("labels", {}), lay.get("home")

    def _route(self, a, b):
        import heapq
        if a not in self.nbr or b not in self.nbr:
            return None
        dist, prev, q = {a: 0}, {}, [(0, a)]
        while q:
            dd, u = heapq.heappop(q)
            if u == b:
                break
            if dd > dist[u]:
                continue
            for v, (_, _, _, w) in self.nbr[u].items():
                if dd + w < dist.get(v, 1 << 30):
                    dist[v], prev[v] = dd + w, u
                    heapq.heappush(q, (dd + w, v))
        if b not in dist:
            return None
        p = [b]
        while p[-1] != a:
            p.append(prev[p[-1]])
        return p[::-1]

    def _piece(self, line, u, v):
        k, i, j, _ = self.nbr[u][v]
        L = self.links[k]
        path = L["paths"].get(line) or L["centre"]
        scale = (len(path) - 1) / max(1, L["len"] - 1)
        a, b = int(round(L["at"][i] * scale)), int(round(L["at"][j] * scale))
        return path[a:b + 1] if a <= b else path[b:a + 1][::-1]

    def _build_patterns(self, d, keys):
        """For every stop pattern: the LEDs its trams pass, and where along them each stop is."""
        self.pat_path, self.pat_stop, self.pat_line, self.pat_ok, self.pat_path_l = [], [], [], [], []
        self._pat_keys = [[keys[s] for s in seq] for _, seq in d["patterns"]]
        for line, seq in d["patterns"]:
            pix, at, ok = [], [], True
            for n, (a, b) in enumerate(zip(seq, seq[1:])):
                ka, kb = keys[a], keys[b]
                r = self._route(ka, kb) if ka != kb else [ka]
                if r is None:
                    ok = False
                    break
                if n == 0:
                    if len(r) > 1:
                        first = self._piece(line, r[0], r[1])[0]
                    else:
                        first = self.xy.get(ka, (0, 0))
                    pix.append(first)
                    at.append(0)
                for u, v in zip(r, r[1:]):
                    seg = self._piece(line, u, v)
                    if pix[-1] != seg[0]:                    # the jog between two routes at a junction
                        seg = _walk([pix[-1], seg[0]])[1:] + seg[1:]
                    else:
                        seg = seg[1:]
                    pix.extend(seg)
                at.append(len(pix) - 1)
            self.pat_line.append(line)
            self.pat_ok.append(ok and len(pix) > 1)
            self.pat_path.append(np.array(pix if pix else [(0, 0)], np.int32))
            self.pat_path_l.append([tuple(q) for q in (pix if pix else [(0, 0)])])
            self.pat_stop.append([float(v) for v in (at if at else [0])])
        self.base = self._draw_base()

    def _draw_base(self):
        from display import pixelfont
        img = np.zeros((H, W, 3), np.float32)
        lines_px = np.zeros((H, W), bool)
        drawn = set()
        for p, (path, ok, line) in enumerate(zip(self.pat_path, self.pat_ok, self.pat_line)):
            if not ok or (line, path.tobytes()) in drawn:
                continue
            drawn.add((line, path.tobytes()))
            x, y = path[:, 0], path[:, 1]
            m = (x >= 0) & (x < W) & (y >= 0) & (y < H)
            img[y[m], x[m]] = self.dim[line]
            lines_px[y[m], x[m]] = True
        self._line_px = lines_px
        # interchanges: a ring round a stop where lines meet or part (or where two or more lines stop)
        served = {}
        for ks, line, ok in zip(self._pat_keys, self.pat_line, self.pat_ok):
            if ok:
                for s in ks:
                    served.setdefault(s, set()).add(line)
        rings = []
        for k, (x, y) in self.xy.items():
            n = len(served.get(k, ()))
            deg = len(self.nbr.get(k, {}))
            if (n >= 2 and deg >= 3) or k in self.labels:
                rings.append(k)
        self.ring_px = set()
        for k in rings:
            self._ring(img, k)
        if self.home in self.xy:
            x, y = self.xy[self.home]
            for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
                if 0 <= x + dx < W and 0 <= y + dy < H:
                    img[y + dy, x + dx] = HOME_COL
            img[y, x] = (0, 0, 0)
        # the few names, where they fit: beside the stop, clear of the lines and of each other
        taken = lines_px.copy()
        for k in self.labels:
            if k in self.xy:
                x, y = self.xy[k]
                taken[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = True
        for k, text in sorted(self.labels.items(), key=lambda kv: kv[0] != self.home):
            if k not in self.xy:
                continue
            x, y = self.xy[k]
            w = pixelfont.width(text)
            best = None
            cands = []
            for ty in range(y - 14, y + 11):
                for tx in range(x - w - 12, x + 13):
                    # distance from the stop to the nearest point of the label, a little in favour of beside it
                    ddx = max(tx - x, 0, x - (tx + w - 1))
                    ddy = max(ty - y, 0, y - (ty + 4))
                    cands.append((ddx * ddx + 1.6 * ddy * ddy, ty, tx))
            cands.sort()
            for dd, ty, tx in cands:
                if dd < 4 or tx < 0 or ty < 0 or tx + w > W or ty + 5 > H:
                    continue
                if not taken[max(0, ty - 1):ty + 6, max(0, tx - 1):tx + w + 1].any():
                    best = (tx, ty)
                    break
            if best:
                tx, ty = best
                pixelfont.draw(img, text, tx, ty, HOME_COL if k == self.home else LABEL_COL)
                taken[ty - 1:ty + 6, tx - 1:tx + w + 1] = True
        return img

    def _ring(self, img, k):
        """A small white ring round the stop, as wide as the bundle of lines through it."""
        x, y = self.xy[k]
        span = 1
        for v, (li, i, j, _) in self.nbr.get(k, {}).items():
            span = max(span, len(self.links[li]["lines"]))
        r = 1 + (span - 1) // 2 + (1 if span > 1 else 0)
        r = min(r, 4)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) == r and not (abs(dx) == r and abs(dy) == r and r > 1):
                    px, py = x + dx, y + dy
                    if 0 <= px < W and 0 <= py < H and not self._line_px[py, px]:
                        img[py, px] = RING_COL

    # ------------------------------------------------------------------ time
    def _day_index(self, day):
        """The timetable day to use for `day`: itself, or when the asset has gone stale, the latest
        day in it that is the same weekday (the network keeps running on its usual week)."""
        if day in self.days:
            return self.days.index(day)
        same = [i for i, d in enumerate(self.days) if d.weekday() == day.weekday()]
        return same[-1] if same else len(self.days) - 1

    def _midnight(self, day):
        return datetime.datetime(day.year, day.month, day.day, tzinfo=self.tz).timestamp()

    def _select(self, now):
        """The trips out now (or about to be, or just in), with their stop times ready to use."""
        today = datetime.datetime.fromtimestamp(now, self.tz).date()
        act, cache = [], {} if self.rt_at != self.active_rt else self._entries
        self._entries = {}
        for back in (1, 0):
            day = today - datetime.timedelta(days=back)
            di = self._day_index(day)
            base = self._midnight(day)
            e = now - base - self.t_t0
            m = (((self.t_mask >> di) & 1) == 1) & self.t_ok & (e > -FADE - 600) & (e < self.t_dur + FADE + 1800)
            for i in np.nonzero(m)[0].tolist():
                ent = cache.get((i, base))
                if ent is None:
                    if self.t_id[i] in self.cancelled:
                        continue
                    p = int(self.t_pat[i])
                    ent = (base + float(self.t_t0[i]), self._times(i), self.pat_stop[p], p)
                self._entries[(i, base)] = ent
                act.append(ent)
        self.active = act
        self.active_at, self.active_rt = now, self.rt_at

    def _times(self, i):
        """[arr0, dep0, arr1, dep1, ...] seconds after the first departure, with the live delays."""
        prof = self.profiles[self.t_prof[i]]
        dl = self.delays.get(self.t_id[i])
        return (prof if dl is None else prof + dl).tolist()

    def render(self, now):
        if now - self.active_at > 2.0 or now < self.active_at or self.rt_at != self.active_rt:
            self._select(now)
        img = self.base.copy()
        heads = []
        for start, tm, stops, p in self.active:
            e = now - start
            if e < tm[1]:                                   # waiting at the first stop: brightening
                a = 1.0 - (tm[1] - e) / FADE
                pos = stops[0]
            elif e > tm[-2]:                                # arrived at the last: fading
                a = 1.0 - (e - tm[-2]) / FADE
                pos = stops[-1]
            else:
                a = 1.0
                k = bisect.bisect_right(tm, e) - 1
                s = k >> 1
                if k & 1 and s + 1 < len(stops):            # between stop s and s+1
                    t0, t1 = tm[k], tm[k + 1]
                    f = 0.0 if t1 <= t0 else (e - t0) / (t1 - t0)
                    f = 0.6 * f + 0.4 * f * f * (3 - 2 * f)     # trams pull away and brake
                    pos = stops[s] + f * (stops[s + 1] - stops[s])
                else:
                    pos = stops[min(s, len(stops) - 1)]
            if a > 0.0:
                heads.append((p, int(pos + 0.5), a if a < 1.0 else 1.0))
        if heads:
            bx, by, bc, cx, cy, cc = [], [], [], [], [], []
            for p, j, a in heads:
                path = self.pat_path_l[p]
                col = self.colour[self.pat_line[p]]
                n = len(path)
                for jj in (j - 1, j + 1):                   # the tram's body, a LED either side, in full colour
                    if 0 <= jj < n:
                        bx.append(path[jj][0]); by.append(path[jj][1]); bc.append(col * a)
                cx.append(path[j][0]); cy.append(path[j][1]); cc.append((col * 0.3 + 178.5) * a)   # the core: near white
            for xs, ys, cs in ((bx, by, bc), (cx, cy, cc)):
                xs, ys = np.array(xs), np.array(ys)
                ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
                xs, ys, cs = xs[ok], ys[ok], np.array(cs, np.float32)[ok]
                img[ys, xs] = np.maximum(img[ys, xs], cs)
        self.n_trams, self._heads = len(heads), heads
        return Image.fromarray(img.astype(np.uint8), "RGB")

    # ------------------------------------------------------------------ live delays
    def _load_cache(self):
        try:
            with open(CACHE) as fh:
                c = json.load(fh)
            if time.time() - c.get("fetched", 0) < STALE:
                self._apply(c)
        except Exception:
            pass

    def _apply(self, c):
        """Delays per trip -> arrays like the profile: [arr0, dep0, ...] shifted by the delay at each
        stop. Before its first report a trip carries that first delay; after a report, the delay holds
        until the next one (GTFS-RT propagation)."""
        delays = {}
        for tid, ups in c.get("delays", {}).items():
            i = self.id_index.get(tid)
            if i is None:
                continue
            p = self.t_pat[i]
            n = len(self.pat_stop[p])
            arr = np.zeros(2 * n)
            ups = sorted((u for u in ups if 0 <= u[0] < n), key=lambda u: u[0])
            if not ups:
                continue
            cur_a, cur_d = ups[0][1], ups[0][2]
            k = 0
            for s in range(n):
                while k < len(ups) and ups[k][0] <= s:
                    cur_a, cur_d = ups[k][1], ups[k][2]
                    k += 1
                arr[2 * s], arr[2 * s + 1] = cur_a, cur_d
            delays[tid] = arr
        self.delays = delays
        self.cancelled = set(c.get("cancelled", []))
        self.rt_at = c.get("fetched", 0)

    def _fetch_loop(self):
        key = _load_env_key()
        if not key:
            return                                          # schedule only
        import requests
        while True:
            t_next = time.time() + EVERY
            try:
                self._fetch_once(key, requests)
            except Exception as e:
                print(f"[tramlines] {str(e)[:120]}", flush=True)
            if time.time() - self.rt_at > STALE:
                self.delays, self.cancelled = {}, set()
            time.sleep(max(5.0, t_next - time.time()))

    def _fetch_once(self, key, requests):
        try:
            import google.transit.gtfs_realtime_pb2  # noqa: F401  (only to know which format to ask for)
            fmt = "pb"
        except Exception:
            fmt = "json"
        hdr = {"Authorization": "Bearer " + key, "User-Agent": "fortuna-wall/1.0 (private art project)",
               "Accept-Encoding": "gzip"}
        r = requests.get(RT_URL, headers=hdr, params={"format": "JSON"} if fmt == "json" else None, timeout=40)
        r.raise_for_status()
        now = time.time()
        tdir = tempfile.mkdtemp(prefix="tramlines_")
        try:
            feed, ids = os.path.join(tdir, "feed"), os.path.join(tdir, "ids.json")
            with open(feed, "wb") as fh:
                fh.write(r.content)
            today = datetime.datetime.fromtimestamp(now, self.tz).date()
            want = {}
            for back in (1, 0):
                di = self._day_index(today - datetime.timedelta(days=back))
                for i in np.nonzero(((self.t_mask >> di) & 1) == 1)[0]:
                    want[self.t_id[i]] = self._pat_keys[self.t_pat[i]]
            with open(ids, "w") as fh:
                json.dump(want, fh)
            out = subprocess.run([sys.executable, os.path.abspath(__file__), "--rt", feed, ids, fmt],
                                 capture_output=True, timeout=60, check=True,
                                 env=dict(os.environ, OMP_NUM_THREADS="1")).stdout
        finally:
            for f in os.listdir(tdir):
                os.unlink(os.path.join(tdir, f))
            os.rmdir(tdir)
        c = json.loads(out)
        c["fetched"] = now
        self._apply(c)
        try:
            tmp = CACHE + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(c, fh, separators=(",", ":"))
            os.replace(tmp, CACHE)
        except Exception:
            pass


def parse_feed(raw, fmt, want):
    """GTFS-RT trip updates -> {"delays": {trip_id: [[stop index, arrival delay, departure delay], ...]},
    "cancelled": [trip_id, ...]} for the trips in `want` (trip_id -> its stop keys). Stops are matched
    by their id (the didok number before any ':'), else by stop_sequence (1 = the first stop)."""
    delays, cancelled = {}, []

    def one(tid, rel, ups):
        keys = want.get(tid)
        if keys is None:
            return
        if rel in (3, "CANCELED", "CANCELLED"):
            cancelled.append(tid)
            return
        out = []
        for sid, seq, a, d in ups:
            idx = None
            if sid:
                k = str(sid).split(":")[0].replace("Parent", "")
                if k in keys:
                    idx = keys.index(k)
            if idx is None and seq:
                idx = int(seq) - 1
            if idx is None or not 0 <= idx < len(keys):
                continue
            if a is None and d is None:
                continue
            a = d if a is None else a
            d = a if d is None else d
            out.append([idx, int(a), int(d)])
        if out:
            delays[tid] = out

    if fmt == "pb":
        from google.transit import gtfs_realtime_pb2
        f = gtfs_realtime_pb2.FeedMessage()
        f.ParseFromString(raw)
        for e in f.entity:
            if not e.HasField("trip_update"):
                continue
            tu = e.trip_update
            if tu.trip.trip_id not in want:
                continue
            ups = []
            for u in tu.stop_time_update:
                a = u.arrival.delay if u.HasField("arrival") and u.arrival.HasField("delay") else None
                d = u.departure.delay if u.HasField("departure") and u.departure.HasField("delay") else None
                ups.append((u.stop_id, u.stop_sequence, a, d))
            one(tu.trip.trip_id, tu.trip.schedule_relationship, ups)
    else:
        j = json.loads(raw)
        for e in j.get("entity", j.get("Entity", [])):
            tu = e.get("tripUpdate") or e.get("trip_update")
            if not tu:
                continue
            trip = tu.get("trip", {})
            tid = trip.get("tripId") or trip.get("trip_id")
            if tid not in want:
                continue
            ups = []
            for u in tu.get("stopTimeUpdate") or tu.get("stop_time_update") or []:
                g = lambda o: (o or {}).get("delay")
                ups.append((u.get("stopId") or u.get("stop_id"), u.get("stopSequence") or u.get("stop_sequence"),
                            g(u.get("arrival")), g(u.get("departure"))))
            one(tid, trip.get("scheduleRelationship") or trip.get("schedule_relationship"), ups)
    return {"delays": delays, "cancelled": cancelled}


_trams = None


def thumb():
    """A still for the app: an evening rush hour on the committed timetable (no network)."""
    tr = Trams(fetch=False)
    day = tr.days[min(1, len(tr.days) - 1)]
    return tr.render(tr._midnight(day) + 17.5 * 3600)


def frame(t):
    global _trams
    if _trams is None:
        _trams = Trams()
    return _trams.render(time.time())


if __name__ == "__main__" and len(sys.argv) >= 5 and sys.argv[1] == "--rt":
    with open(sys.argv[2], "rb") as fh:
        raw_feed = fh.read()
    with open(sys.argv[3]) as fh:
        wanted = json.load(fh)
    sys.stdout.write(json.dumps(parse_feed(raw_feed, sys.argv[4], wanted), separators=(",", ":")))
