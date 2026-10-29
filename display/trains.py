"""Trains around Zürich: the rail network of the Zürich region as a schematic S-Bahn map in the manner of
the ZVV's - Zürich HB at the heart, the S-Bahn lines radiating out in their ZVV colours, one LED wide,
straight runs and clean 45-degree bends, lines that share a track running side by side - and every train
running right now as a bright bead travelling along its line, station to station, at its real position:
the timetable plus its live delay. S-Bahn trains glow in their line's colour with a white core; the
long-distance trains (IC, IR, RE, EC ...), the night S-Bahn and the neighbouring networks' trains pass more
faintly along the same tracks. A train brightens in at its first station and fades at its last; trains
that come from beyond the map run in and out at its edge. The big stations are small rings, a few named.

The timetable and the schematic are committed (assets/trains/, from tools/build_trains.py, refreshed twice
a week by .github/workflows/trains.yml), so the map runs on schedule alone with no network and no key.
With OTD_API_KEY set (.env), a side thread reads the GTFS-RT trip updates of opentransportdata.swiss once a
minute while the mode is on screen and moves each train by its reported delay; cancelled trips leave the
map. The Swiss feed is large, so it is parsed in a short-lived child process: the frames never wait for
it. The last delays are kept in panel_setup/trains_cache.json for a quick restart.

Everything is drawn on whole LEDs (no anti-aliasing).
"""
import bisect
import datetime
import gzip
import itertools
import json
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
DATA = os.path.join(ROOT, "assets", "trains", "zurich_trains.json.gz")
LAYOUT = os.path.join(ROOT, "assets", "trains", "layout.json")
CACHE = os.path.join(ROOT, "panel_setup", "trains_cache.json")
RT_URL = "https://api.opentransportdata.swiss/la/gtfs-rt"
EVERY = 60.0                              # seconds between live calls (the key allows 5 a minute, shared with the trams)
IDLE = 10.0                               # no frame for this long: off screen, stop calling
STALE = 15 * 60.0                         # delays older than this are forgotten
TZ = "Europe/Zurich"
FADE = 45.0                               # seconds a train takes to brighten in at its first station / fade at its last
# The network is drawn dim, each line in the LED colour nearest its ZVV colour. With 6 PWM bits each channel
# shows only a few steps (led_matrix.led_lut(35, 6): inputs from 0/94/149/188/219/245 give 0/124/170/203/231/255),
# so scaling the ZVV colours down merges many of them; instead every line gets one of these step colours,
# chosen so lines side by side in a bundle never share one and as few lines as possible share at all.
LED_IN = (0, 120, 166, 203, 232)          # an input in the middle of each step
LED_OUT = (0, 124, 170, 203, 231)         # what the eye gets from it, as sRGB
LED_FROM = (0, 94, 149, 188, 219)         # the input where each step begins (245 and up: 255)
LINE_MAX = (2, 3)                         # the brightest channel of a line: step 170 or 203 (the beads stay above)
OTHER_LINE = (104, 104, 112)              # tracks only long-distance or neighbouring trains use
RING_COL = (150, 150, 160)
LABEL_COL = (128, 128, 138)
# the beads: kind -> (core colour or None for the line's own, body?)
LONG_COL = np.array([255, 236, 205], np.float32) * 0.92     # IC / IR / RE: a pale warm light, one LED (above the lines)
TAIL = ((1, 1.0), (2, 0.85))                                # LEDs behind the head, and their strength
OTHER_COL = np.array([170, 176, 190], np.float32)           # neighbouring S-Bahn: a grey light
NIGHT_COL = np.array([150, 170, 255], np.float32)           # night S-Bahn: moonlight blue


def _rgb(hexs):
    return tuple(int(hexs[i:i + 2], 16) for i in (0, 2, 4))


def _line_palette(official, links):
    """line -> its dim colour: the LED step colour nearest its official colour (hue first), such that
    lines next to each other in a bundle differ clearly and lines elsewhere preferably differ too."""
    near, same = {}, {}
    for L in links:
        ls = [x for x in L["lines"] if x in official]
        for i, a in enumerate(ls):
            for j, b in enumerate(ls):
                if a != b:
                    (near if abs(i - j) == 1 else same).setdefault(a, set()).add(b)
    def step(v):
        return np.array([255 if x >= 245 else LED_OUT[bisect.bisect_right(LED_FROM, x) - 1] for x in v], np.float64)
    beads = [step(c) for c in (LONG_COL, OTHER_COL, NIGHT_COL)]  # the one-LED trains must show on any line
    cands = []
    for c in itertools.product(range(len(LED_OUT)), repeat=3):
        m = max(c)
        out = np.array([LED_OUT[i] for i in c], np.float64)
        if any(np.abs(out - b).sum() < 30 for b in beads):
            continue
        if m in LINE_MAX and len(set(c)) > 1:            # no greys: those are the long-distance tracks
            cands.append((c, out, out / out.max(), m))

    def lab(rgb):                                       # OKLab of an sRGB colour, normalised to its brightest channel
        c = np.asarray(rgb, np.float64)
        c = c / max(1.0, c.max())
        c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        lms = np.cbrt(np.array([[0.4122, 0.5363, 0.0514], [0.2119, 0.6807, 0.1074], [0.0883, 0.2817, 0.6300]]) @ c)
        return np.array([[0.2105, 0.7936, -0.0041], [1.9780, -2.4286, 0.4506], [0.0259, 0.7828, -0.8087]]) @ lms

    labs = {}

    def cost(v, cand):
        a = labs.setdefault(tuple(v), lab(v))
        b = labs.setdefault(cand[0], lab(cand[1]))
        return 0.3 * (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2

    ranked = {k: sorted(cands, key=lambda c: cost(v, c)) for k, v in official.items()}
    order = sorted(official, key=lambda k: (-len(near.get(k, ())) - 0.5 * len(same.get(k, ())), k))
    chosen, used = {}, {}
    for k in order:
        best, bc = None, 1e9
        for cand in ranked[k][:40]:
            out = cand[1]
            c = cost(official[k], cand)
            for o in near.get(k, ()):
                if o in chosen and np.abs(chosen[o][1] - out).sum() < 90:
                    c += 1.0
            for o in same.get(k, ()):
                if o in chosen and np.abs(chosen[o][1] - out).sum() < 45:
                    c += 0.3
            if cand[0] in used and tuple(official[used[cand[0]]]) != tuple(official[k]):
                c += 0.001                                  # shared with a line elsewhere: allowed, not liked
            if c < bc:
                best, bc = cand, c
        chosen[k] = best
        used.setdefault(best[0], k)
    return {k: np.array([LED_IN[i] for i in c[0]], np.float32) for k, c in chosen.items()}


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
        nx, ny = -dy, dx
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
    (x0, y0), (x1, y1) = corners[-2], corners[-1]
    dx, dy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
    nx, ny = -dy, dx
    o = (nx * slot, 0) if (nx and ny) else (nx * slot, ny * slot)
    pts.append((x1 + o[0], y1 + o[1]))
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


def stop_key(sid):
    """A GTFS(-RT) stop id -> the station's didok number: 'ch:1:sloid:3000:5:8' -> '8503000',
    '8503000:0:5' -> '8503000', 'Parent8503000' -> '8503000'."""
    s = str(sid or "")
    if "sloid:" in s:
        try:
            n = int(s.split("sloid:", 1)[1].split(":")[0])
            return str(8500000 + n) if n < 100000 else str(n)
        except ValueError:
            return s
    return s.replace("Parent", "").split(":")[0]


class Trains:
    def __init__(self, fetch=True):
        from zoneinfo import ZoneInfo
        self.tz = ZoneInfo(TZ)
        with gzip.open(DATA, "rt") as fh:
            d = json.load(fh)
        with open(LAYOUT) as fh:
            lay = json.load(fh)
        self.days = [datetime.date.fromisoformat(s) for s in d["days"]]
        self.kind = {k: v[1] for k, v in d["lines"].items()}
        self.colour, self.dim = {}, {}
        for k, (name, kd, c) in d["lines"].items():
            if kd == "S":
                v = np.array(_rgb(c), np.float32)
                self.colour[k] = v * (255.0 / max(1.0, float(v.max())))
        keys = [s[3] for s in d["stops"]]
        self.edge = [bool(s[4]) for s in d["stops"]]
        self._build_map(lay)
        self.dim = _line_palette({k: _rgb(c) for k, (_, kd, c) in d["lines"].items() if kd == "S"}, self.links)
        self._build_patterns(d, keys)
        tr = d["trips"]
        self.t_pat = np.array([r[0] for r in tr], np.int32)
        self.t_prof = np.array([r[1] for r in tr], np.int32)
        self.t_t0 = np.array([r[2] for r in tr], np.float64)
        self.t_mask = np.array([r[3] for r in tr], np.int64)
        self.t_id = [r[4] for r in tr]
        self.id_index = {}
        for i, tid in enumerate(self.t_id):
            self.id_index.setdefault(tid, []).append(i)      # a trip that leaves and re-enters has two runs
        self.profiles = [np.cumsum(p).astype(np.float64) for p in d["profiles"]]
        self.t_dur = np.array([self.profiles[p][-1] for p in self.t_prof], np.float64)
        self.t_ok = np.array([self.pat_ok[p] for p in self.t_pat], bool)
        self.delays, self.cancelled, self.rt_at = {}, set(), 0.0
        self.active, self.active_at, self.active_rt, self._entries = [], -1e9, 0.0, {}
        self.n_trains, self.seen = 0, time.time()
        self._load_cache()
        if fetch:
            threading.Thread(target=self._fetch_loop, daemon=True).start()

    # ------------------------------------------------------------------ the map
    def _build_map(self, lay):
        self.xy = {k: (v[0], v[1]) for k, v in lay["stops"].items()}
        self.links, self.nbr = [], {}
        for k, (stops, at, corners, lines, other) in enumerate(lay["links"]):
            n = len(lines)
            centre = _walk(corners)
            paths = {line: _walk(_offset(corners, i - (n - 1) // 2)) for i, line in enumerate(lines)}
            self.links.append({"stops": stops, "at": at, "len": len(centre), "paths": paths, "centre": centre,
                               "lines": lines, "other": other})
            for i, (u, v) in enumerate(zip(stops, stops[1:])):
                self.nbr.setdefault(u, {})[v] = (k, i, i + 1, at[i + 1] - at[i])
                self.nbr.setdefault(v, {})[u] = (k, i + 1, i, at[i + 1] - at[i])
        self.labels, self.rings = lay.get("labels", {}), lay.get("rings", [])

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
        """For every stop pattern: the LEDs its trains pass, and where along them each station is."""
        self.pat_path, self.pat_stop, self.pat_line, self.pat_ok = [], [], [], []
        self.pat_keys, self.pat_edge = [], []
        routes = {}
        for line, seq in d["patterns"]:
            pix, at, ok = [], [], True
            for n, (a, b) in enumerate(zip(seq, seq[1:])):
                ka, kb = keys[a], keys[b]
                if (ka, kb) not in routes:
                    routes[(ka, kb)] = self._route(ka, kb) if ka != kb else [ka]
                r = routes[(ka, kb)]
                if r is None:
                    ok = False
                    break
                if n == 0:
                    pix.append(self._piece(line, r[0], r[1])[0] if len(r) > 1 else self.xy.get(ka, (0, 0)))
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
            self.pat_path.append([tuple(q) for q in (pix if pix else [(0, 0)])])
            self.pat_stop.append([float(v) for v in (at if at else [0])])
            self.pat_keys.append([keys[s] for s in seq])
            self.pat_edge.append((self.edge[seq[0]], self.edge[seq[-1]]))
        self.base = self._draw_base()
        self.base8 = np.clip(self.base, 0, 255).astype(np.uint8)
        self.pat_col, self.kind_s = [], []
        for line in self.pat_line:                          # each pattern's bead: (core, body or None)
            kd = self.kind.get(line)
            if kd == "S":
                col = self.colour[line]
                self.pat_col.append((col * 0.04 + 245.0, col * 0.4 + 153.0))   # a white head, a pale body in its colour
            elif kd == "N":
                self.pat_col.append((NIGHT_COL, NIGHT_COL * 0.7))
            elif kd == "L":
                self.pat_col.append((LONG_COL, None))
            else:
                self.pat_col.append((OTHER_COL, None))
            self.kind_s.append(kd == "S")

    def _draw_base(self):
        from display import pixelfont
        img = np.zeros((H, W, 3), np.float32)
        lines_px = np.zeros((H, W), bool)

        def put(path, col):
            for x, y in path:
                if 0 <= x < W and 0 <= y < H:
                    img[y, x] = col
                    lines_px[y, x] = True
        for L in self.links:                                 # tracks without S-Bahn: a fine grey
            if not L["lines"] and L["other"]:
                put(L["centre"], OTHER_LINE)
        for L in self.links:
            for line, path in L["paths"].items():
                put(path, self.dim[line])
        for p, (path, ok, line) in enumerate(zip(self.pat_path, self.pat_ok, self.pat_line)):
            if ok and line in self.dim:                      # the jogs at junctions
                for q in path:
                    if 0 <= q[0] < W and 0 <= q[1] < H and not lines_px[q[1], q[0]]:
                        img[q[1], q[0]] = self.dim[line]
                        lines_px[q[1], q[0]] = True
        self._line_px = lines_px
        for k in self.rings:
            if k in self.xy:
                self._ring(img, k)
        taken = lines_px.copy()
        for k in self.labels:
            if k in self.xy:
                x, y = self.xy[k]
                taken[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = True
        for k, text in self.labels.items():
            if k not in self.xy:
                continue
            x, y = self.xy[k]
            w = pixelfont.width(text)
            cands = []
            for ty in range(y - 11, y + 7):
                for tx in range(x - w - 8, x + 9):
                    ddx = max(tx - x, 0, x - (tx + w - 1))
                    ddy = max(ty - y, 0, y - (ty + 4))
                    cands.append((ddx * ddx + 1.6 * ddy * ddy, ty, tx))
            cands.sort()
            for dd, ty, tx in cands:
                if dd < 4 or tx < 0 or ty < 0 or tx + w > W or ty + 5 > H:
                    continue
                if not taken[max(0, ty - 1):ty + 6, max(0, tx - 1):tx + w + 1].any():
                    pixelfont.draw(img, text, tx, ty, LABEL_COL)
                    taken[max(0, ty - 1):ty + 6, max(0, tx - 1):tx + w + 1] = True
                    break
        return img

    def _ring(self, img, k):
        """A ring round the station: a small one on a single line, a rounded box spanning the whole
        bundle where lines run side by side (as the white station capsules on the ZVV map)."""
        x, y = self.xy[k]
        xs, ys = [x], [y]
        for v, (li, i, j, _) in self.nbr.get(k, {}).items():
            L = self.links[li]
            for path in L["paths"].values():
                scale = (len(path) - 1) / max(1, L["len"] - 1)
                px, py = path[int(round(L["at"][i] * scale))]
                xs.append(px)
                ys.append(py)
        x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
        for px in range(x0, x1 + 1):
            for py in range(y0, y1 + 1):
                edge = px in (x0, x1) or py in (y0, y1)
                corner = px in (x0, x1) and py in (y0, y1)
                if edge and not (corner and (x1 - x0 > 2 or y1 - y0 > 2)):
                    if 0 <= px < W and 0 <= py < H and not self._line_px[py, px]:
                        img[py, px] = RING_COL

    # ------------------------------------------------------------------ time
    def _day_index(self, day):
        """The timetable day to use for `day`: itself, or when the asset has gone stale, the latest day
        in it that is the same weekday (the network keeps to its usual week)."""
        if day in self.days:
            return self.days.index(day)
        same = [i for i, d in enumerate(self.days) if d.weekday() == day.weekday()]
        return same[-1] if same else len(self.days) - 1

    def _day_base(self, day):
        """GTFS times count from noon minus 12 h (local midnight except on the two DST days)."""
        noon = datetime.datetime(day.year, day.month, day.day, 12, tzinfo=self.tz).timestamp()
        return noon - 12 * 3600.0

    def _select(self, now):
        """The trips out now (or about to be, or just in), with their stop times ready to use."""
        today = datetime.datetime.fromtimestamp(now, self.tz).date()
        act, cache = [], {} if self.rt_at != self.active_rt else self._entries
        self._entries = {}
        for back in (1, 0):
            day = today - datetime.timedelta(days=back)
            di = self._day_index(day)
            base = self._day_base(day)
            ds = day.strftime("%Y%m%d")                     # the service day, as GTFS-RT start_date gives it
            e = now - base - self.t_t0
            m = (((self.t_mask >> di) & 1) == 1) & self.t_ok & (e > -FADE - 900) & (e < self.t_dur + FADE + 1800)
            for i in np.nonzero(m)[0].tolist():
                ent = cache.get((i, base))
                if ent is None:
                    tid = self.t_id[i]
                    if (tid, ds) in self.cancelled or (tid, "") in self.cancelled:
                        continue
                    p = int(self.t_pat[i])
                    ent = (base + float(self.t_t0[i]), self._times(i, ds), self.pat_stop[p], p)
                self._entries[(i, base)] = ent
                act.append(ent)
        self.active = act
        self.active_at, self.active_rt = now, self.rt_at

    def _times(self, i, ds):
        prof = self.profiles[self.t_prof[i]]
        dl = self.delays.get((i, ds))
        if dl is None:
            dl = self.delays.get((i, ""))                  # an update without a start_date: any day
        return (prof if dl is None else prof + dl).tolist()

    def render(self, now):
        self.seen = time.time()
        if now - self.active_at > 2.0 or now < self.active_at or self.rt_at != self.active_rt:
            self._select(now)
        img = self.base8.copy()
        heads = []
        for start, tm, stops, p in self.active:
            e = now - start
            ein, eout = self.pat_edge[p]
            if e < tm[1]:                                   # waiting at the first station: brightening
                if ein:
                    continue
                a = 1.0 - (tm[1] - e) / FADE
                pos = stops[0]
            elif e > tm[-2]:                                # arrived: fading
                if eout:
                    continue
                a = 1.0 - (e - tm[-2]) / FADE
                pos = stops[-1]
            else:
                a = 1.0
                k = bisect.bisect_right(tm, e) - 1
                s = k >> 1
                if k & 1 and s + 1 < len(stops):            # between station s and s+1
                    t0, t1 = tm[k], tm[k + 1]
                    f = 0.0 if t1 <= t0 else (e - t0) / (t1 - t0)
                    f = 0.5 * f + 0.5 * f * f * (3 - 2 * f)     # trains pull away and brake
                    pos = stops[s] + f * (stops[s + 1] - stops[s])
                else:
                    pos = stops[min(s, len(stops) - 1)]
            if a > 0.0:
                heads.append((p, int(pos + 0.5), a if a < 1.0 else 1.0))
        # every bead's LEDs gathered, then written at once: bodies first, then cores, the S-Bahn over the
        # faint ones (where two beads meet, the later write wins)
        heads.sort(key=lambda h: self.kind_s[h[0]])
        bx, by, bc, cx, cy, cc = [], [], [], [], [], []
        for p, j, a in heads:
            path = self.pat_path[p]
            core, body = self.pat_col[p]
            if body is not None:                            # a short comet: the head, the train behind it
                for back, f in TAIL:
                    jj = j - back
                    if 0 <= jj < len(path):
                        q = path[jj]
                        bx.append(q[0]); by.append(q[1]); bc.append(body * (a * f))
                if j + 1 < len(path):
                    q = path[j + 1]
                    bx.append(q[0]); by.append(q[1]); bc.append(body * (a * 0.8))
            q = path[j]
            cx.append(q[0]); cy.append(q[1]); cc.append(core * a)
        for xs, ys, cs in ((bx, by, bc), (cx, cy, cc)):
            if xs:
                xs, ys = np.array(xs), np.array(ys)
                ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
                cs = np.array(cs, np.float32)[ok].astype(np.uint8)
                xs, ys = xs[ok], ys[ok]
                img[ys, xs] = np.maximum(img[ys, xs], cs)
        self.n_trains = len(heads)
        return Image.fromarray(img, "RGB")

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
        station. Before its first report a trip carries that first delay; after a report the delay holds
        until the next one (GTFS-RT propagation). A trip with two runs in the region gets both. Each update
        holds for the run of its own service day (start_date; "" when the feed gives none)."""
        delays = {}
        items = []
        for tid, v in c.get("delays", {}).items():
            if isinstance(v, dict):
                items.extend((tid, ds, ups) for ds, ups in v.items())
            else:
                items.append((tid, "", v))                  # an older cache: no service day
        for tid, ds, ups in items:
            for i in self.id_index.get(tid, ()):
                keys = self.pat_keys[self.t_pat[i]]
                kk = [k.split("@")[0] for k in keys]
                n = len(keys)
                pts = sorted((kk.index(s), a, d) for s, a, d in ups if s in kk)
                if not pts:
                    continue
                arr = np.zeros(2 * n)
                cur_a, cur_d = pts[0][1], pts[0][2]
                k = 0
                for s in range(n):
                    while k < len(pts) and pts[k][0] <= s:
                        cur_a, cur_d = pts[k][1], pts[k][2]
                        k += 1
                    arr[2 * s], arr[2 * s + 1] = cur_a, cur_d
                delays[(i, ds)] = arr
        self.delays = delays
        self.cancelled = {(x, "") if isinstance(x, str) else tuple(x) for x in c.get("cancelled", [])}
        self.rt_at = c.get("fetched", 0)

    def _fetch_loop(self):
        key = _load_env_key()
        if not key:
            return                                          # schedule only
        import requests
        while True:
            if time.time() - self.seen > IDLE:              # off screen: no calls
                time.sleep(2.0)
                continue
            t_next = time.time() + EVERY
            try:
                self._fetch_once(key, requests)
            except Exception as e:
                print(f"[trains] {type(e).__name__}: {str(e)[:100]}", flush=True)
            if time.time() - self.rt_at > STALE and self.rt_at:
                self.delays, self.cancelled, self.rt_at = {}, set(), 0.0
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
        tdir = tempfile.mkdtemp(prefix="trains_")
        try:
            feed, ids = os.path.join(tdir, "feed"), os.path.join(tdir, "ids.json")
            with open(feed, "wb") as fh:
                fh.write(r.content)
            with open(ids, "w") as fh:
                json.dump(sorted(self.id_index), fh)
            out = subprocess.run([sys.executable, os.path.abspath(__file__), "--rt", feed, ids, fmt],
                                 capture_output=True, timeout=60, check=True,
                                 env=dict(os.environ, OMP_NUM_THREADS="1")).stdout
        finally:
            for f in os.listdir(tdir):
                os.unlink(os.path.join(tdir, f))
            os.rmdir(tdir)
        c = json.loads(out)
        if not c.pop("ok", False):                         # an empty or headless answer: keep what we have
            raise ValueError(f"empty feed ({len(r.content)} bytes)")
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
    """GTFS-RT trip updates -> {"delays": {trip_id: {start_date: [[didok, arrival delay, departure delay],
    ...]}}, "cancelled": [[trip_id, start_date], ...], "ok": bool} for the trip ids in `want`. Stop ids are
    reduced to the station's didok number (stop_key), so both 'ch:1:sloid:...' and numeric ids match the
    timetable's stations. "ok" is False for a feed with no header timestamp or no trip updates at all (an
    empty answer must not wipe the delays we have)."""
    want = set(want)
    delays, cancelled = {}, []
    seen = [0, False]                                       # trip updates in the feed, header timestamp

    def one(tid, ds, rel, ups):
        ds = str(ds or "")
        if rel in (3, "CANCELED", "CANCELLED"):
            cancelled.append([tid, ds])
            return
        out = []
        for sid, a, d in ups:
            if a is None and d is None:
                continue
            a = d if a is None else a
            d = a if d is None else d
            out.append([stop_key(sid), int(a), int(d)])
        if out:
            delays.setdefault(tid, {})[ds] = out

    if fmt == "pb":
        from google.transit import gtfs_realtime_pb2
        f = gtfs_realtime_pb2.FeedMessage()
        f.ParseFromString(raw)
        seen[1] = f.HasField("header") and f.header.timestamp > 0
        for e in f.entity:
            if not e.HasField("trip_update"):
                continue
            seen[0] += 1
            tu = e.trip_update
            if tu.trip.trip_id not in want:
                continue
            ups = []
            for u in tu.stop_time_update:
                a = u.arrival.delay if u.HasField("arrival") and u.arrival.HasField("delay") else None
                d = u.departure.delay if u.HasField("departure") and u.departure.HasField("delay") else None
                ups.append((u.stop_id, a, d))
            one(tu.trip.trip_id, tu.trip.start_date, tu.trip.schedule_relationship, ups)
    else:
        j = json.loads(raw)
        seen[1] = bool((j.get("header") or {}).get("timestamp"))
        for e in j.get("entity", j.get("Entity", [])):
            tu = e.get("tripUpdate") or e.get("trip_update")
            if not tu:
                continue
            seen[0] += 1
            trip = tu.get("trip", {})
            tid = trip.get("tripId") or trip.get("trip_id")
            if tid not in want:
                continue
            ups = []
            for u in tu.get("stopTimeUpdate") or tu.get("stop_time_update") or []:
                g = lambda o: (o or {}).get("delay")
                ups.append((u.get("stopId") or u.get("stop_id"), g(u.get("arrival")), g(u.get("departure"))))
            one(tid, trip.get("startDate") or trip.get("start_date"),
                trip.get("scheduleRelationship") or trip.get("schedule_relationship"), ups)
    return {"delays": delays, "cancelled": cancelled, "ok": bool(seen[0] and seen[1])}


_trains, _building, _ready_at, _last = None, False, 0.0, None
_BLACK = None


def _build():
    global _trains, _ready_at
    try:
        _trains = Trains()
        _ready_at = time.time()
    except Exception as e:                                  # no assets: the wall stays dark, nothing breaks
        print(f"[trains] {type(e).__name__}: {str(e)[:120]}", flush=True)


def thumb():
    """A still for the app: an evening rush hour on the committed timetable (no network, no thread)."""
    try:
        tr = Trains(fetch=False)
        day = tr.days[min(1, len(tr.days) - 1)]
        return tr.render(tr._day_base(day) + 17.6 * 3600)
    except Exception as e:                                  # no assets: a dark still, as frame() shows
        print(f"[trains] thumb: {type(e).__name__}: {str(e)[:120]}", flush=True)
        return Image.new("RGB", (W, H))


def frame(t):
    """The map at this moment. The timetable is read on a side thread (half a second on the Pi), the
    map fades in from black when it is ready; a frame never waits and never raises."""
    global _building, _last, _BLACK
    if _BLACK is None:
        _BLACK = Image.new("RGB", (W, H))
    if _trains is None:
        if not _building:
            _building = True
            threading.Thread(target=_build, daemon=True).start()
        return _BLACK
    try:
        img = _trains.render(time.time())
        f = (time.time() - _ready_at) / 1.5
        if f < 1.0:
            img = Image.fromarray((np.asarray(img, np.float32) * max(0.0, f)).astype(np.uint8), "RGB")
        _last = img
        return img
    except Exception as e:
        print(f"[trains] {type(e).__name__}: {str(e)[:120]}", flush=True)
        return _last or _BLACK


if __name__ == "__main__" and len(sys.argv) >= 5 and sys.argv[1] == "--rt":
    with open(sys.argv[2], "rb") as fh:
        raw_feed = fh.read()
    with open(sys.argv[3]) as fh:
        wanted = json.load(fh)
    sys.stdout.write(json.dumps(parse_feed(raw_feed, sys.argv[4], wanted), separators=(",", ":")))
