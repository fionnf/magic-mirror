"""Build the Zürich tram assets for display/tramlines.py from the Swiss GTFS timetable (free, no key:
opentransportdata.swiss, "Timetable 20xx (GTFS2020)"). Run on the laptop or in GitHub Actions - never on the
Pi: the zip is ~300 MB and stop_times.txt inside it ~3.7 GB.

    python3 tools/build_trams.py                 # download the current feed, build both assets
    python3 tools/build_trams.py --zip gtfs.zip  # use a zip already on disk
    python3 tools/build_trams.py --layout-only   # redo the schematic from the committed timetable

Writes
    assets/trams/zurich_trams.json.gz   the VBZ trams for the next DAYS days: stops, lines and colours,
                                        stop patterns, shared time profiles and every trip (with its GTFS
                                        trip_id, to match the live delays)
    assets/trams/layout.json            the schematic: an octilinear position on the 192x256 wall for
                                        every stop, and the drawn route of every line

The zip is downloaded to a temporary file and its members are read as streams (nothing is unpacked).
The schematic is made from the real stop positions: the network is reduced to its junctions and
termini, stretched to the wall with the centre magnified, relaxed towards 0/45/90 degree links, and
each link between two junctions is drawn as a straight run with at most one 45-degree bend. A few
places are set by hand in OVERRIDES.
"""
import argparse
import csv
import datetime
import gzip
import io
import json
import math
import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets", "trams")
DATA = os.path.join(OUT, "zurich_trams.json.gz")
LAYOUT = os.path.join(OUT, "layout.json")
PERMALINK = "https://data.opentransportdata.swiss/en/dataset/timetable-{year}-gtfs2020/permalink"
DAYS = 8                                  # built Tue and Fri: a week ahead covers a missed run or two
TZ = "Europe/Zurich"
W, H = 192, 256

# VBZ line colours (the line signals on the network map; Wikipedia "Trams in Zürich" module). Line 7 is
# black and the construction lines 50/51 white-on-black on paper: on black LEDs they become pale greys.
COLOURS = {
    "2": "ed1c24", "3": "00ac4f", "4": "49479d", "5": "956438", "6": "d99f4f", "7": "231f20",
    "8": "a6ce39", "9": "49479d", "10": "ee3897", "11": "00ac4f", "12": "7ad0e2", "13": "ffd503",
    "14": "00aeef", "15": "ed1c24", "16": "8f7fc0", "17": "9e1762", "20": "9e1762", "21": "ffd503",
    "50": "000000", "51": "000000",
}


# ---------------------------------------------------------------------------------------------------
# the timetable

def download(path):
    import urllib.request
    today = datetime.date.today()
    years = [today.year + 1, today.year] if today.month == 12 else [today.year, today.year + 1]
    for y in years:
        url = PERMALINK.format(year=y)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fortuna-wall/1.0 (private art project)"})
            with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as fh:
                n = 0
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    fh.write(b)
                    n += len(b)
            print(f"downloaded {url}: {n / 1e6:.0f} MB", flush=True)
            if feed_covers(path, today):
                return
            print("  ...but it does not cover today, trying the next year's", flush=True)
        except Exception as e:
            print(f"{url}: {e}", flush=True)
    if not os.path.exists(path) or os.path.getsize(path) < 1e6:
        sys.exit("no GTFS feed")


def feed_covers(path, day):
    with zipfile.ZipFile(path) as z:
        for r in rows(z, "feed_info.txt"):
            return r["feed_start_date"] <= day.strftime("%Y%m%d") <= r["feed_end_date"]
    return True


def rows(z, name):
    with z.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig", newline=""))


def is_vbz(name):
    return name.startswith("Verkehrsbetriebe Zürich") and "Zürichsee" not in name


def extract(path, start):
    # start one day early so trips running past midnight from the day before `start` are present
    days = [start + datetime.timedelta(d) for d in range(-1, DAYS)]
    keys = [d.strftime("%Y%m%d") for d in days]
    z = zipfile.ZipFile(path)
    feed = next(rows(z, "feed_info.txt"), {}).get("feed_version", "")
    agencies = {r["agency_id"] for r in rows(z, "agency.txt") if is_vbz(r["agency_name"])}
    routes = {}
    for r in rows(z, "routes.txt"):
        rt = int(r["route_type"] or -1)
        if r["agency_id"] in agencies and (rt == 0 or 900 <= rt < 1000) and r["route_short_name"].isdigit():
            routes[r["route_id"]] = r["route_short_name"]
    print("lines:", sorted(set(routes.values()), key=int), flush=True)
    trips = {}
    for r in rows(z, "trips.txt"):
        if r["route_id"] in routes:
            trips[r["trip_id"]] = (routes[r["route_id"]], r["service_id"], r["direction_id"])
    services = {s for _, s, _ in trips.values()}
    mask = {}                                                 # service -> bit per day
    for r in rows(z, "calendar.txt"):
        if r["service_id"] not in services:
            continue
        m = 0
        for i, d in enumerate(days):
            if r["start_date"] <= keys[i] <= r["end_date"] and r[d.strftime("%A").lower()] == "1":
                m |= 1 << i
        mask[r["service_id"]] = m
    ki = {k: i for i, k in enumerate(keys)}
    for r in rows(z, "calendar_dates.txt"):
        i = ki.get(r["date"])
        if i is None or r["service_id"] not in services:
            continue
        if r["exception_type"] == "1":
            mask[r["service_id"]] = mask.get(r["service_id"], 0) | 1 << i
        else:
            mask[r["service_id"]] = mask.get(r["service_id"], 0) & ~(1 << i)
    trips = {t: v for t, v in trips.items() if mask.get(v[1], 0)}
    print(f"{len(trips)} trips in the {DAYS} days from {start}", flush=True)
    times, stop_ids = {}, set()
    with z.open("stop_times.txt") as fh:
        f = io.TextIOWrapper(fh, "utf-8-sig", newline="")
        head = next(csv.reader([f.readline()]))
        ix = {k: i for i, k in enumerate(head)}
        it, ia, idp, isd, iseq = ix["trip_id"], ix["arrival_time"], ix["departure_time"], ix["stop_id"], ix["stop_sequence"]
        for line in f:
            q = line.find(",")
            if line[:q].strip('"') not in trips:             # cheap test first: 99% of the 3.7 GB is not ours
                continue
            c = next(csv.reader([line]))
            times.setdefault(c[it], []).append((int(c[iseq]), c[isd], hms(c[ia]), hms(c[idp])))
            stop_ids.add(c[isd])
    stops, platform = {}, {}
    for r in rows(z, "stops.txt"):
        sid = r["stop_id"]
        if sid in stop_ids:
            key = r.get("didok") or r["parent_station"] or sid
            platform[sid] = key
            s = stops.setdefault(key, {"name": r["stop_name"], "lat": [], "lon": []})
            s["lat"].append(float(r["stop_lat"]))
            s["lon"].append(float(r["stop_lon"]))
    keys_sorted = sorted(stops, key=lambda k: stops[k]["name"])
    sidx = {k: i for i, k in enumerate(keys_sorted)}
    out_stops = [[short(stops[k]["name"]), round(sum(stops[k]["lat"]) / len(stops[k]["lat"]), 5),
                  round(sum(stops[k]["lon"]) / len(stops[k]["lon"]), 5), k] for k in keys_sorted]
    patterns, profiles, out_trips = {}, {}, []
    for tid, st in times.items():
        st.sort()
        seq = []
        for _, sid, a, d in st:
            i = sidx[platform[sid]]
            if seq and seq[-1][0] == i:                       # the same stop twice (two platforms): merge
                seq[-1][2] = d
            else:
                seq.append([i, a, d])
        if len(seq) < 2:
            continue
        line, service, direction = trips[tid]
        p = patterns.setdefault((line, tuple(s[0] for s in seq)), len(patterns))
        t0 = seq[0][2]
        prof = []
        for _, a, d in seq:
            prof += [a - t0, d - t0]
        prof[0] = 0
        q = profiles.setdefault(tuple(prof), len(profiles))
        out_trips.append([p, q, t0, mask[service], tid])
    out_trips.sort(key=lambda r: (r[2], r[0]))
    pat_list = [None] * len(patterns)
    for (line, seq), i in patterns.items():
        pat_list[i] = [line, list(seq)]
    prof_list = [None] * len(profiles)
    for prof, i in profiles.items():
        prof_list[i] = delta(list(prof))
    lines = sorted({p[0] for p in pat_list}, key=int)
    return {
        "built": datetime.datetime.now().isoformat(timespec="seconds"), "feed": feed, "tz": TZ,
        "source": "opentransportdata.swiss GTFS (timetable), VBZ trams",
        "days": [d.isoformat() for d in days],
        "lines": {l: COLOURS.get(l, "c0c0c0") for l in lines},
        "stops": out_stops,
        "patterns": pat_list,
        "profiles": prof_list,
        "trips": out_trips,
        "_doc": "stops: [name, lat, lon, didok]; patterns: [line, [stop...]]; profiles: [arr,dep per stop, "
                "seconds from the first departure, as differences]; trips: [pattern, profile, first departure "
                "(seconds after the service day's local midnight, may pass 24 h), day bits (bit i = days[i]), "
                "GTFS trip_id]",
    }


def hms(s):
    h, m, sec = (int(x) for x in s.split(":"))
    return h * 3600 + m * 60 + sec


def delta(v):
    return [v[0]] + [v[i] - v[i - 1] for i in range(1, len(v))]


def short(name):
    for pre in ("Zürich, ", "Zürich,"):
        if name.startswith(pre):
            return name[len(pre):]
    return name.replace("Zürich ", "")


# ---------------------------------------------------------------------------------------------------
# the schematic
#
# A hand-set skeleton of the network in the style of the VBZ map: the junctions and termini sit where
# POS puts them (wall LEDs), the stops between two of them are strung along the link, every link is an
# octilinear run (straight + at most one 45 degree bend) and the lines of a link run side by side as
# parallel one-LED lanes in an order chosen so that they stay in their lane through the junctions.

# stop name -> (label shown on the wall)
LABELS = {
    "Bahnhofplatz/HB": "HB", "Central": "CENTRAL", "Bellevue": "BELLEVUE", "Paradeplatz": "PARADE",
    "Stadelhofen, Bahnhof": "STADELH", "Stauffacher": "STAUFF", "Hardbrücke, Bahnhof": "HARDBR",
    "Oerlikon, Bahnhof": "OERLIKON", "Triemli": "TRIEMLI", "Zoo": "ZOO", "Flughafen, Fracht": "AIRPORT",
}
HOME = "Rennweg"
ALIASES = {"Enge, Bahnhof/Bederstr.": "Enge, Bahnhof"}      # two platforms of one place: one point
# Junctions and termini: stop name -> (x, y) on the 192x256 wall. HB top-centre, Bahnhofstrasse running
# south to the lake at Bellevue, the Sihl side to the left, Zürichberg right, the airport in the corner.
POS = {
    "Flughafen, Fracht": (150, 8), "Glattpark, Glattpark": (136, 34), "Auzelg": (160, 44),
    "Stettbach, Bahnhof": (176, 84), "Hirzenbach": (172, 58), "Seebach": (106, 16),
    "Oerlikon, Bahnhof Ost": (108, 44), "Leutschenbach": (124, 44), "Sternen Oerlikon": (98, 54),
    "Oerlikon, Bahnhof": (84, 54), "Bucheggplatz": (88, 68), "Milchbuck": (108, 68),
    "Schwamendingerplatz": (150, 68), "Schaffhauserplatz": (94, 82), "Escher-Wyss-Platz": (54, 84),
    "Frankental": (14, 40), "Hardturm": (20, 70), "Werdhölzli": (6, 56), "Schiffbau": (40, 100),
    "Altstetten, Bahnhof N": (8, 90), "Bahnhofplatz/HB": (84, 112), "Bahnhofstrasse/HB": (84, 126),
    "Central": (108, 112), "Haldenegg": (112, 102), "ETH/Universitätsspital": (132, 102),
    "Platte": (142, 124), "Kirche Fluntern": (164, 116), "Zoo": (180, 98), "Kantonsschule": (130, 138),
    "Kunsthaus": (118, 148), "Stauffacher": (50, 138), "Albisriederplatz": (24, 136),
    "Albisrieden": (8, 150), "Schlieren, Geissweid": (8, 112), "Heuried": (20, 168), "Triemli": (8, 180),
    "Paradeplatz": (84, 144), "Bürkliplatz": (86, 158), "Bellevue": (104, 166),
    "Stadelhofen, Bahnhof": (116, 174), "Kreuzplatz": (134, 178), "Römerhof": (150, 160),
    "Klusplatz": (172, 172), "Rehalp": (178, 206), "Tiefenbrunnen, Bahnhof": (150, 226),
    "Tunnelstrasse": (66, 164), "Enge, Bahnhof": (56, 176), "Laubegg": (42, 192),
    "Albisgütli": (24, 214), "Wollishoferplatz": (66, 246),
}
# Optional hand-set waypoints for a link: (stop name A, stop name B) -> [(x, y), ...] (octilinear steps).
VIA = {}
# bundles of up to this many lines are drawn with a dark LED between the lanes
GAP_UP_TO = 3
MIN_SHARE = 0.15                          # a line has a lane on a link if it runs there at least this often
ALL_TICKS = 16                            # interchange ticks drawn (busiest first)
LABEL_MAX_COST = 26                       # about one stray LED under a word is the most we accept
Z_ORDER = ["7", "50", "51", "5", "13", "14", "12", "6", "8", "3", "11", "2", "15", "17", "10", "9", "4"]


def project(lat, lon):
    """Kilometres east and south of the middle of town."""
    return ((lon - 8.5395) * 111.32 * math.cos(math.radians(47.3745)), (47.3745 - lat) * 111.32)


def _tps(src, dst, smooth=1.0):
    """Thin-plate-spline warp from src points (n,2) to dst points (n,2); returns f(points (m,2)) -> (m,2)."""
    import numpy as np
    n = len(src)

    def U(r2):
        return np.where(r2 > 0, r2 * np.log(np.maximum(r2, 1e-12)) * 0.5, 0.0)
    d2 = ((src[:, None, :] - src[None, :, :]) ** 2).sum(-1)
    K = U(d2) + np.eye(n) * smooth
    P = np.hstack([np.ones((n, 1)), src])
    A = np.zeros((n + 3, n + 3))
    A[:n, :n], A[:n, n:], A[n:, :n] = K, P, P.T
    b = np.zeros((n + 3, 2))
    b[:n] = dst
    w = np.linalg.solve(A, b)

    def f(pts):
        pts = np.asarray(pts, float).reshape(-1, 2)
        r2 = ((pts[:, None, :] - src[None, :, :]) ** 2).sum(-1)
        return U(r2) @ w[:n] + np.hstack([np.ones((len(pts), 1)), pts]) @ w[n:]
    return f


def line(p, q):
    """Whole LEDs from p to q (Bresenham), both ends included."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
    out, err = [(x0, y0)], dx - dy
    while (x0, y0) != (x1, y1):
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
        out.append((x0, y0))
    return out


def poly(pts):
    out = [tuple(pts[0])]
    for a, b in zip(pts, pts[1:]):
        out += line(tuple(a), tuple(b))[1:]
    return out


def _sgn(v):
    return (v > 0) - (v < 0)


def _octi_routes(a, b):
    """Candidate centre lines from a to b: one straight run, or a straight run and one 45 degree bend."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    m = min(abs(dx), abs(dy))
    if dx == 0 or dy == 0 or abs(dx) == abs(dy):
        return [[a, b]]
    sx, sy = _sgn(dx), _sgn(dy)
    return [[a, (a[0] + sx * m, a[1] + sy * m), b], [a, (b[0] - sx * m, b[1] - sy * m), b]]


def _kind(p, q):
    dx, dy = q[0] - p[0], q[1] - p[1]
    if dy == 0:
        return "H"
    if dx == 0:
        return "V"
    return "D1" if (dx > 0) == (dy > 0) else "D2"      # D1: x - y constant, D2: x + y constant


def _left(p, q):
    """Left-hand normal of the step p -> q (screen coordinates, y down)."""
    ux, uy = _sgn(q[0] - p[0]), _sgn(q[1] - p[1])
    return (uy, -ux)


def _shift(p, q, o):
    """How a lane o LEDs left of the centre line p -> q moves a point of it (horizontal for the diagonals)."""
    lx, ly = _left(p, q)
    return (o * lx, o * ly) if _kind(p, q) in ("H", "V") else (o * _sgn(lx), 0)


def lane_poly(pts, o):
    """The centre line pts (corners) moved o LEDs to its left: corners are the meets of the moved runs."""
    if o == 0:
        return [tuple(p) for p in pts]
    segs = list(zip(pts, pts[1:]))
    cons = []
    for p, q in segs:
        k, s = _kind(p, q), _shift(p, q, o)
        base = {"H": p[1] + s[1], "V": p[0] + s[0], "D1": p[0] - p[1] + s[0], "D2": p[0] + p[1] + s[0]}[k]
        cons.append((k, base))
    first, last = segs[0], segs[-1]
    sa, sb = _shift(*first, o), _shift(*last, o)
    out = [(first[0][0] + sa[0], first[0][1] + sa[1])]
    for (k1, c1), (k2, c2) in zip(cons, cons[1:]):
        out.append(_meet(k1, c1, k2, c2, out[-1]))
    out.append((last[1][0] + sb[0], last[1][1] + sb[1]))
    return out


def _meet(k1, c1, k2, c2, prev):
    if k1 == k2:
        return prev
    pair = {k1: c1, k2: c2}
    if "H" in pair and "V" in pair:
        return (pair["V"], pair["H"])
    if "H" in pair:
        y = pair["H"]
        return ((pair["D1"] + y) if "D1" in pair else (pair["D2"] - y), y)
    if "V" in pair:
        x = pair["V"]
        return (x, (x - pair["D1"]) if "D1" in pair else (pair["D2"] - x))
    x = (pair["D1"] + pair["D2"]) // 2
    return (x, pair["D2"] - x)


def build_layout(data):
    """The wall schematic from the timetable: {w, h, stops [[x,y,name]], home, lanes, routes, marks, labels,
    water}. See the comment above POS. lanes: one polyline per line on each link, drawn in order (each with
    the LEDs it clears where it crosses another link); routes: for every timetable pattern the whole-LED
    path of its trams (vertices) and the vertex of each of its stops."""
    import numpy as np
    import collections
    names = [s[0] for s in data["stops"]]
    nid = {n: i for i, n in enumerate(names)}
    alias = list(range(len(names)))
    for a, b in ALIASES.items():
        if a in nid and b in nid:
            alias[nid[a]] = nid[b]
    trips = collections.Counter(t[0] for t in data["trips"])
    pats = [(line, [alias[i] for i in seq]) for line, seq in data["patterns"]]
    # 1. the links (consecutive stops) with how often each line runs on them
    use = collections.defaultdict(collections.Counter)
    for p, (line, seq) in enumerate(pats):
        for a, b in zip(seq, seq[1:]):
            if a != b:
                use[(min(a, b), max(a, b))][line] += trips[p]
    peak = collections.Counter()
    for c in use.values():
        for line, n in c.items():
            peak[line] = max(peak[line], n)
    lines_on = {e: frozenset(l for l, n in c.items() if n >= MIN_SHARE * peak[l]) for e, c in use.items()}
    solid = {e: ls for e, ls in lines_on.items() if ls}
    adj = collections.defaultdict(list)
    for (a, b) in solid:
        adj[a].append(b)
        adj[b].append(a)
    key = set()
    for s, nb in adj.items():
        e = lambda x: (min(s, x), max(s, x))
        if len(nb) != 2 or solid[e(nb[0])] != solid[e(nb[1])] or names[s] in POS:
            key.add(s)
    # 2. chains: from a key stop along links of one line set to the next key stop
    chains, seen = [], set()
    for s in sorted(key):
        for n in adj[s]:
            if (min(s, n), max(s, n)) in seen:
                continue
            seq, prev = [s, n], s
            seen.add((min(s, n), max(s, n)))
            while seq[-1] not in key:
                cur = seq[-1]
                nxt = [x for x in adj[cur] if x != prev][0]
                seen.add((min(cur, nxt), max(cur, nxt)))
                prev = cur
                seq.append(nxt)
            chains.append(seq)
    where = {}                                                      # link -> (chain, index of its first stop)
    for ci, seq in enumerate(chains):
        for i, (a, b) in enumerate(zip(seq, seq[1:])):
            where[(min(a, b), max(a, b))] = (ci, i)
    # 3. where the key stops are: hand-set, else warped from the geography by the hand-set ones
    ll = np.array([project(data["stops"][i][1], data["stops"][i][2]) for i in range(len(names))])
    placed = {nid[n]: xy for n, xy in POS.items() if n in nid and nid[n] in key}
    ctl = sorted(placed)
    warp = _tps(ll[ctl], np.array([placed[i] for i in ctl], float), smooth=2.0)
    pos = {}
    for s in key:
        pos[s] = tuple(int(round(v)) for v in (placed[s] if s in placed else warp(ll[s])[0]))
    for s in pos:
        pos[s] = (min(max(pos[s][0], 3), W - 4), min(max(pos[s][1], 3), H - 4))
    # 4. centre lines, the busiest links first, each avoiding what is already there
    occupied = collections.Counter()
    centre = {}
    order = sorted(range(len(chains)), key=lambda c: (-len(solid[(min(chains[c][:2]), max(chains[c][:2]))]), -len(chains[c])))
    for ci in order:
        seq = chains[ci]
        a, b = pos[seq[0]], pos[seq[-1]]
        via = VIA.get((names[seq[0]], names[seq[-1]]))
        if via:
            cands = [[a] + [tuple(v) for v in via] + [b]]
        else:
            cands = _octi_routes(a, b)
        mid = None
        if len(seq) > 2:
            mid = warp(ll[seq[len(seq) // 2]])[0]
        best, bc = None, None
        for cand in cands:
            px = poly(cand)
            cost = sum(4 * occupied[p] for p in px[2:-2])
            if mid is not None:
                cost += 0.05 * min(math.hypot(p[0] - mid[0], p[1] - mid[1]) for p in px)
            if bc is None or cost < bc - 1e-9:
                best, bc = cand, cost
        best = [best[0]] + [p for i, p in enumerate(best[1:-1], 1) if _kind(best[i - 1], p) != _kind(p, best[i + 1])] + [best[-1]]
        centre[ci] = best
        for p in poly(best):
            occupied[p] += 1
    # 5. lanes: the lines of each chain in a left-to-right order that keeps each one level through junctions
    lane_of = {}
    for ci, seq in enumerate(chains):
        ls = sorted(solid[(min(seq[0], seq[1]), max(seq[0], seq[1]))], key=int)
        lane_of[ci] = ls
    pitch = lambda k: 2 if k <= GAP_UP_TO else 1             # a dark LED between lanes while the bundle stays slim
    offs = lambda k: [i * pitch(k) - ((k - 1) * pitch(k)) // 2 for i in range(k)]

    def end_point(ci, line, at_start):
        pts = centre[ci]
        ls = lane_of[ci]
        o = offs(len(ls))[ls.index(line)]
        if at_start:
            p, q = pts[0], pts[1]
            s = _shift(p, q, o)
            return (p[0] + s[0], p[1] + s[1])
        p, q = pts[-2], pts[-1]
        s = _shift(p, q, o)
        return (q[0] + s[0], q[1] + s[1])

    passes = set()                                      # (stop, chain a, at start of a, chain b, at start of b, line)
    for p, (line, seq) in enumerate(pats):
        prev = None
        for a, b in zip(seq, seq[1:]):
            w = where.get((min(a, b), max(a, b)))
            if w is None:
                prev = None
                continue
            ci, i = w
            fwd = chains[ci][i] == a
            if prev is not None and prev[0] != ci and line in lane_of[prev[0]] and line in lane_of[ci]:
                passes.add((a, prev[0], not prev[1], ci, fwd, line))
            prev = (ci, fwd)

    chain_pass = collections.defaultdict(list)
    for t in passes:
        chain_pass[t[1]].append(t)
        chain_pass[t[3]].append(t)

    def local(ci):
        t = 0.0
        for a, c1, s1, c2, s2, line in chain_pass[ci]:
            p, q = end_point(c1, line, s1), end_point(c2, line, s2)
            t += math.hypot(p[0] - q[0], p[1] - q[1])
        return t
    multi = [c for c in lane_of if len(lane_of[c]) > 1]
    for _ in range(60):
        improved = False
        for c in multi:
            ls = lane_of[c]
            for i in range(len(ls)):
                for j in range(i + 1, len(ls)):
                    before = local(c)
                    ls[i], ls[j] = ls[j], ls[i]
                    if local(c) < before - 1e-9:
                        improved = True
                    else:
                        ls[i], ls[j] = ls[j], ls[i]
        if not improved:
            break
    # 6. the lane polylines, the stops on them
    lanes_xy = {}                                                   # (chain, line or None) -> LED path
    stop_idx = {}                                                   # chain -> [index into a path of each stop]
    centre_px = {ci: poly(centre[ci]) for ci in centre}
    stops_xy = {}
    for ci, seq in enumerate(chains):
        px = centre_px[ci]
        m = len(seq) - 1
        fr = [k / m for k in range(m + 1)]
        stop_idx[ci] = fr
        for k, s in enumerate(seq):
            stops_xy[s] = px[round(fr[k] * (len(px) - 1))]
        ls = lane_of[ci]
        o_list = offs(len(ls))
        for line, o in zip(ls, o_list):
            lanes_xy[(ci, line)] = poly(lane_poly(centre[ci], o))
        lanes_xy[(ci, None)] = px
    for s in key:
        stops_xy[s] = pos[s]
    # stops no solid link serves (rare variants): the warp of the geography
    for s in range(len(names)):
        if alias[s] != s:
            continue
        if s not in stops_xy:
            stops_xy[s] = tuple(int(round(v)) for v in warp(ll[s])[0])
    for s in range(len(names)):
        if alias[s] != s:
            stops_xy[s] = stops_xy[alias[s]]
    for s, (x, y) in list(stops_xy.items()):
        stops_xy[s] = (min(max(x, 1), W - 2), min(max(y, 1), H - 2))

    def stop_at(ci, line, k):
        path = lanes_xy.get((ci, line)) or lanes_xy[(ci, None)]
        return path[round(stop_idx[ci][k] * (len(path) - 1))], round(stop_idx[ci][k] * (len(path) - 1))

    # 7. every timetable pattern's route along its lanes
    routes = {}
    for p, (line, seq) in enumerate(pats):
        pts, at = [], []
        for n in range(1, len(seq)):
            a, b = seq[n - 1], seq[n]
            w = where.get((min(a, b), max(a, b))) if a != b else None
            if w is None:                                       # no lane (a rare link, or the same place twice)
                if not pts:
                    pts = [stops_xy[a]]
                    at.append(0)
                if a != b and pts[-1] != stops_xy[b]:
                    pts += line_pts(pts[-1], stops_xy[b])[1:]
                at.append(len(pts) - 1)
                continue
            ci, i = w
            path = lanes_xy.get((ci, line)) or lanes_xy[(ci, None)]
            ia, ib = (i, i + 1) if chains[ci][i] == a else (i + 1, i)
            ja = round(stop_idx[ci][ia] * (len(path) - 1))
            jb = round(stop_idx[ci][ib] * (len(path) - 1))
            seg = path[ja:jb + 1] if ja <= jb else path[jb:ja + 1][::-1]
            if not pts:
                pts = list(seg)
                at.append(0)
            else:
                if pts[-1] != seg[0]:
                    pts += line_pts(pts[-1], seg[0])[1:]
                pts += seg[1:]
            at.append(len(pts) - 1)
        if not pts:
            pts = [stops_xy[seq[0]]]
            at = [0] * len(seq)
        routes[p] = _compress(pts, at)
    # 8. lane drawings in z-order, with the LEDs each clears where it crosses a link it does not meet
    z = {l: (Z_ORDER.index(l) if l in Z_ORDER else 99) for l in {l for l, _ in pats}}
    ends = {ci: {chains[ci][0], chains[ci][-1]} for ci in range(len(chains))}
    own = {}
    for (ci, line), path in lanes_xy.items():
        if line is not None:
            for p in path:
                own.setdefault(p, set()).add(ci)
    draw = []
    for ci in sorted(range(len(chains)), key=lambda c: max([z[l] for l in lane_of[c]] or [0])):
        ls = lane_of[ci]
        if not ls:
            continue
        mine = set()
        for line in ls:
            mine.update(lanes_xy[(ci, line)])
        clear = set()
        for p in mine:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (p[0] + dx, p[1] + dy)
                    if q in mine or q not in own:
                        continue
                    others = own[q] - {ci}
                    if others and all(not (ends[ci] & ends[o]) for o in others) and all(
                            (max([z[l] for l in lane_of[o]] or [0]), o) < (max(z[l] for l in ls), ci) for o in others):
                        clear.add(q)
        for line in sorted(ls, key=lambda l: z[l]):
            draw.append({"l": line, "v": _vertices(lanes_xy[(ci, line)]), "c": [list(q) for q in clear] if line == ls[0] else []})
    # connectors where a line passes from one link to the next
    conn = set()
    for a, c1, s1, c2, s2, line in passes:
        p, q = end_point(c1, line, s1), end_point(c2, line, s2)
        if p != q:
            conn.add((line, p, q) if p < q else (line, q, p))
    for line, p, q in sorted(conn):
        draw.append({"l": line, "v": _vertices(line_pts(p, q)), "c": []})
    # 9. marks: ticks across the bundles of the busiest junctions, bars at the ends of the lines
    marks = _marks(chains, centre, lane_of, key, adj, offs, names)
    out_stops = [[int(stops_xy[i][0]), int(stops_xy[i][1]), names[i]] for i in range(len(names))]
    all_px = set()
    for path in lanes_xy.values():
        all_px.update(path)
    all_px.update((m[0], m[1]) for m in marks)
    labels = _place_labels(out_stops, all_px)
    home = next(i for i, s in enumerate(out_stops) if s[2] == HOME)
    water = _water(warp, ll)
    return {"w": W, "h": H, "stops": out_stops, "home": home, "lanes": draw,
            "routes": {str(p): r for p, r in routes.items()}, "marks": marks, "labels": labels, "water": water}


def line_pts(p, q):
    return line(tuple(p), tuple(q))


def _vertices(px):
    """Corner points of a whole-LED path (the LEDs between are the straight runs between them)."""
    if len(px) < 3:
        return [list(p) for p in px]
    out = [px[0]]
    for i in range(1, len(px) - 1):
        d1 = (px[i][0] - px[i - 1][0], px[i][1] - px[i - 1][1])
        d2 = (px[i + 1][0] - px[i][0], px[i + 1][1] - px[i][1])
        if d1 != d2:
            out.append(px[i])
    out.append(px[-1])
    return [list(p) for p in out]


def _compress(px, at):
    """A route as vertices, plus the vertex of each stop (stops are kept as vertices)."""
    keep = set(at) | {0, len(px) - 1}
    out, idx = [], {}
    for i, p in enumerate(px):
        if i in keep or (0 < i < len(px) - 1 and (px[i][0] - px[i - 1][0], px[i][1] - px[i - 1][1]) !=
                         (px[i + 1][0] - px[i][0], px[i + 1][1] - px[i][1])):
            idx[i] = len(out)
            out.append(list(p))
    # a stop LED repeated (same LED twice in a row) keeps its own vertex index
    return {"v": out, "s": [idx[i] for i in at]}


def _marks(chains, centre, lane_of, key, adj, offs, names):
    """[[x, y, kind]]: kind 0 an interchange tick across the busiest bundle at the stop, 1 a bar closing a terminus."""
    marks = []
    info = {}
    for ci, seq in enumerate(chains):
        for end, s in ((0, seq[0]), (1, seq[-1])):
            info.setdefault(s, []).append((ci, end))
    ranked = []
    for s, lst in info.items():
        union = set()
        for ci, _ in lst:
            union.update(lane_of[ci])
        ranked.append((len(union), len(lst), s))
    ranked.sort(reverse=True)
    ticks = [s for u, d, s in ranked if d >= 3 and u >= 3][:ALL_TICKS]
    for s, lst in info.items():
        term = len(lst) == 1
        if s not in ticks and not term:
            continue
        ci, end = max(lst, key=lambda t: len(lane_of[t[0]]))
        pts = centre[ci]
        k = len(lane_of[ci])
        o = offs(k)
        if end == 0:
            p, q = pts[0], pts[1]
            at = p
        else:
            p, q = pts[-2], pts[-1]
            at = q
        ux, uy = _sgn(q[0] - p[0]), _sgn(q[1] - p[1])
        if term:                                                     # one LED beyond the last stop, outwards
            at = (at[0] - ux, at[1] - uy) if end == 0 else (at[0] + ux, at[1] + uy)
        for t in range(o[0] - 1, o[-1] + 2):
            sx, sy = _shift(p, q, t)
            marks.append([at[0] + sx, at[1] + sy, 1 if term else 0])
    return marks


def _water(warp, ll):
    """The lake and the rivers of assets/maps/zurich.json warped to the wall (dim background)."""
    import numpy as np
    try:
        with open(os.path.join(HERE, "assets", "maps", "zurich.json")) as fh:
            m = json.load(fh)
    except Exception:
        return {"lakes": [], "rivers": []}

    def inside(poly_):
        la = [p[0] for p in poly_]
        lo = [p[1] for p in poly_]
        return 47.20 < sum(la) / len(la) < 47.45 and 8.40 < sum(lo) / len(lo) < 8.80 and max(la) - min(la) > 0.003

    def conv(pts):
        a = np.array([project(*p) for p in pts], float)
        w = warp(a)
        return [[int(round(x)), int(round(y))] for x, y in w]
    lakes = []
    for lk in m.get("lakes", []):
        if inside(lk) and len(lk) > 3:
            lakes.append(conv(lk))
    rivers = []
    for r in m.get("rivers", []):
        rr = [p for p in r if 47.30 < p[0] < 47.46 and 8.40 < p[1] < 8.66]
        if len(rr) > 3:
            rivers.append(conv(rr))
    return {"lakes": lakes, "rivers": rivers}


def _place_labels(stops, busy_px):
    """Each LABELS word beside its stop, on whichever side crosses the fewest lines and other words and stays
    on the wall."""
    glyph_w = lambda t: max(0, 4 * len(t) - 1)
    HOME_XY = next((s[0], s[1]) for s in stops if s[2] == HOME)
    dots = {(s[0], s[1]) for s in stops}
    placed, out = [], []
    wanted = [(i, LABELS[s[2]]) for i, s in enumerate(stops) if s[2] in LABELS]
    wanted.sort(key=lambda t: -len(t[1]))
    for i, text in wanted:
        x, y = stops[i][0], stops[i][1]
        w = glyph_w(text)
        # every spot within reach, nearest first: right of the stop, left, above, below, then further out
        cands = sorted(((x + dx, y + dy) for dx in range(-w - 22, 23) for dy in range(-22, 19)),
                       key=lambda c: abs(c[0] + w / 2 - x) * 0.5 + abs(c[1] + 2 - y))
        best, best_cost = None, None
        for k, (tx, ty) in enumerate(cands):
            if tx < 1 or ty < 1 or tx + w > W - 1 or ty + 5 > H - 9:
                continue
            gx, gy = max(tx - x, x - (tx + w), 0), max(ty - y, y - (ty + 4), 0)       # gap to the stop
            if gx + gy < 3 or gx + gy > 13:
                continue                                          # never on its own stop, never so far it names another
            cost = 0.7 * max(0, gx + gy - 3)
            for xx in range(tx - 1, tx + w + 1):
                for yy in range(ty - 1, ty + 6):
                    cost += 12 * ((xx, yy) in busy_px) + (8 if (xx, yy) in dots else 0)
                    cost += 12 * (abs(xx - HOME_XY[0]) + abs(yy - HOME_XY[1]) <= 4)
            for (ox, oy, ow) in placed:
                if tx - 2 < ox + ow and ox - 2 < tx + w and ty - 2 < oy + 5 and oy - 2 < ty + 5:
                    cost += 200
            if best_cost is None or cost < best_cost:
                best, best_cost = (tx, ty), cost
        if best is not None and best_cost < LABEL_MAX_COST:
            placed.append((best[0], best[1], w))
            out.append([best[0], best[1], text])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip")
    ap.add_argument("--layout-only", action="store_true")
    ap.add_argument("--start", help="first day (YYYY-MM-DD), default today in Zürich")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.layout_only:
        with gzip.open(DATA, "rt") as fh:
            data = json.load(fh)
    else:
        from zoneinfo import ZoneInfo
        start = (datetime.date.fromisoformat(a.start) if a.start
                 else datetime.datetime.now(ZoneInfo(TZ)).date())
        path, tmp = a.zip, None
        if not path:
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.close()
            path = tmp.name
            download(path)
        try:
            data = extract(path, start)
        finally:
            if tmp:
                os.unlink(tmp.name)
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
        with gzip.GzipFile(DATA, "wb", mtime=0) as fh:
            fh.write(raw)
        print(f"{DATA}: {len(data['stops'])} stops, {len(data['patterns'])} patterns, "
              f"{len(data['profiles'])} profiles, {len(data['trips'])} trips, "
              f"{os.path.getsize(DATA) / 1e3:.0f} kB", flush=True)
    lay = build_layout(data)
    with open(LAYOUT, "w") as fh:
        json.dump(lay, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"{LAYOUT}: {os.path.getsize(LAYOUT) / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
