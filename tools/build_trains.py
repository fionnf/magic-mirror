"""Build the assets of display/trains.py (Trains around Zürich) from the Swiss GTFS timetable (free, no key:
opentransportdata.swiss, "Timetable 20xx (GTFS2020)"). Run on the laptop or in GitHub Actions - never on
the Pi: the zip is ~300 MB and stop_times.txt inside it ~3.7 GB (read as a stream, nothing is unpacked).

    python3 tools/build_trains.py                 # download the current feed, build both assets
    python3 tools/build_trains.py --zip gtfs.zip  # use a zip already on disk
    python3 tools/build_trains.py --layout-only   # redo the schematic from the committed timetable
    python3 tools/build_trains.py --skip-if-current   # (the workflow) nothing to do if built today already

Writes
    assets/trains/zurich_trains.json.gz   every rail trip that calls inside the region (an ellipse of about
                                          54 x 62 km round Zürich) on the next DAYS days: stops, lines (ZVV
                                          S-Bahn in their ZVV colours; long-distance, night and neighbouring
                                          networks by kind), stop patterns, shared time profiles and every
                                          trip with its GTFS trip_id (to match the live delays). A trip that
                                          leaves the region keeps one stop beyond it, an "edge" stop, so it
                                          can run off the wall at its real time.
    assets/trains/layout.json             the schematic: an octilinear position on the 192x256 wall for every
                                          station, and the drawn route of every link between junctions

The schematic is made from geography: the rail network is reduced to its junctions and termini, slightly
magnified round Zürich HB, relaxed towards 0/45/90 degree links (least squares), each link drawn as a
straight run with at most one 45-degree bend; a small OVERRIDES table pins the places that matter.
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
OUT = os.path.join(HERE, "assets", "trains")
DATA = os.path.join(OUT, "zurich_trains.json.gz")
LAYOUT = os.path.join(OUT, "layout.json")
PERMALINK = "https://data.opentransportdata.swiss/en/dataset/timetable-{year}-gtfs2020/permalink"
DAYS = 8                                   # built Tue and Fri: a week ahead covers a missed run or two
TZ = "Europe/Zurich"
W, H = 192, 256
CENTRE = (47.40, 8.60)                     # the region: an ellipse round this point, km east-west, north-south
AXES = (24.0, 28.5)

# ZVV S-Bahn line colours (the ZVV network map, as in Wikipedia's Template:S-Bahn-Zürich).
ZVV = {
    "S2": "7DC242", "S3": "587AC2", "S4": "EE7267", "S5": "64A8CA", "S6": "734B89", "S7": "FBB402",
    "S8": "62198F", "S9": "069A5D", "S10": "FBCF02", "S11": "CCAAFF", "S12": "EF0503", "S13": "BA8C53",
    "S14": "AC6547", "S15": "BB9977", "S16": "4FAD82", "S17": "0F89AB", "S18": "EE1C23", "S19": "F08513",
    "S20": "C44F97", "S21": "A3CCEE", "S23": "A1C854", "S24": "BA8C53", "S25": "B80E80", "S26": "0F89AB",
    "S29": "069A5D", "S30": "0B5A9C", "S33": "7C93CE", "S35": "ACBCE7", "S36": "D181B5", "S40": "B793C9",
    "S41": "F2B49B", "S42": "9A6B31",
}
# A ZVV line touches at least one of these (others with the same number belong to Zug, Aargau, St. Gallen ...)
ZVV_ANCHORS = ("Zürich ", "Winterthur", "Uster", "Wetzikon ZH", "Dietikon", "Wädenswil", "Bülach", "Rüti ZH",
               "Effretikon", "Thalwil", "Bauma", "Biberbrugg", "Affoltern am Albis")
LONG = {"IC", "ICE", "IR", "IRE", "RE", "EC", "EN", "NJ", "TGV", "RJ", "RJX", "PE", "VAE", "ICN", "RB", "R"}
DROP_TYPES = {104, 107, 108, 116, 117}     # car trains, tourist and rack lines, extra trains


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


def km(lat, lon):
    """Kilometres east and south of CENTRE."""
    return ((lon - CENTRE[1]) * 111.32 * math.cos(math.radians(CENTRE[0])), (CENTRE[0] - lat) * 111.32)


def inside(lat, lon):
    x, y = km(lat, lon)
    if lat < 47.32 and lon < 8.40:                              # the Freiamt (Muri, Sins): only Aargau lines
        return False
    return (x / AXES[0]) ** 2 + (y / AXES[1]) ** 2 <= 1.0


def hms(s):
    h, m, sec = (int(x) for x in s.split(":"))
    return h * 3600 + m * 60 + sec


def delta(v):
    return [v[0]] + [v[i] - v[i - 1] for i in range(1, len(v))]


def extract(path, start):
    days = [start + datetime.timedelta(d) for d in range(DAYS)]
    keys = [d.strftime("%Y%m%d") for d in days]
    z = zipfile.ZipFile(path)
    feed = next(rows(z, "feed_info.txt"), {}).get("feed_version", "")
    platform, station = {}, {}                                  # stop_id -> didok; didok -> [name, lat, lon]
    for r in rows(z, "stops.txt"):
        key = r.get("didok") or r["parent_station"].replace("Parent", "") or r["stop_id"]
        platform[r["stop_id"]] = key
        if r["location_type"] == "1" or key not in station:
            station[key] = [r["stop_name"], float(r["stop_lat"]), float(r["stop_lon"])]
    near = {k for k, (_, la, lo) in station.items() if inside(la, lo)}
    routes = {}
    for r in rows(z, "routes.txt"):
        rt = int(r["route_type"] or -1)
        if (rt == 2 or 100 <= rt <= 117) and rt not in DROP_TYPES:
            routes[r["route_id"]] = (r["route_short_name"], r["route_desc"])
    trips = {}
    for r in rows(z, "trips.txt"):
        if r["route_id"] in routes:
            trips[r["trip_id"]] = (r["route_id"], r["service_id"])
    services = {s for _, s in trips.values()}
    mask = {}
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
    print(f"{len(trips)} rail trips in Switzerland on the {DAYS} days from {start}", flush=True)
    times = {}
    with z.open("stop_times.txt") as fh:
        f = io.TextIOWrapper(fh, "utf-8-sig", newline="")
        head = next(csv.reader([f.readline()]))
        ix = {k: i for i, k in enumerate(head)}
        it, ia, idp, isd, iseq = ix["trip_id"], ix["arrival_time"], ix["departure_time"], ix["stop_id"], ix["stop_sequence"]
        for line in f:
            q = line.find(",")
            if line[:q].strip('"') not in trips:               # cheap test first: most of the 3.7 GB is not ours
                continue
            c = next(csv.reader([line]))
            times.setdefault(c[it], []).append((int(c[iseq]), platform.get(c[isd], c[isd]), hms(c[ia]), hms(c[idp])))
    # every trip cut to its runs inside the region, plus one stop either side (the edge stops)
    runs = []                                                   # (trip_id, line name, desc, [(didok, arr, dep, edge)])
    for tid, st in times.items():
        st.sort()
        seq = []
        for _, k, a, d in st:
            if seq and seq[-1][0] == k:
                seq[-1][2] = d
            else:
                seq.append([k, a, d])
        flags = [s[0] in near for s in seq]
        i = 0
        while i < len(seq):
            if not flags[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(seq) and flags[j + 1]:
                j += 1
            lo, hi = max(0, i - 1), min(len(seq) - 1, j + 1)
            part = [(s[0], s[1], s[2], not flags[n]) for n, s in enumerate(seq[lo:hi + 1], lo)]
            if len(part) >= 2:
                rid = trips[tid][0]
                runs.append((tid, routes[rid][0], routes[rid][1], part, trips[tid][1]))
            i = j + 1
    print(f"{len(runs)} runs in the region", flush=True)
    # line kinds: S = ZVV S-Bahn (coloured), N = night S-Bahn, L = long distance and regional expresses,
    # X = neighbouring networks' S-Bahn (grey)
    comp = {}                                                   # (name) -> union-find over stops
    pats_by_name = {}
    for tid, name, desc, part, _ in runs:
        if desc == "S" and name in ZVV:
            pats_by_name.setdefault(name, set()).add(tuple(p[0] for p in part if not p[3]))
    zvv_stops = {}
    for name, pats in pats_by_name.items():
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for p in pats:
            for a in p[1:]:
                parent[find(a)] = find(p[0])
        groups = {}
        for p in pats:
            for a in p:
                groups.setdefault(find(a), set()).add(a)
        good = set()
        for g in groups.values():
            if any(station[a][0].startswith(ZVV_ANCHORS) for a in g):
                good |= g
        zvv_stops[name] = good
    lines = {}

    def line_of(name, desc, part):
        if desc == "S" and name in ZVV and any(p[0] in zvv_stops.get(name, ()) for p in part if not p[3]):
            lines[name] = [name, "S", ZVV[name]]
            return name
        if desc == "SN":
            lines["N"] = ["SN", "N", ""]
            return "N"
        if desc in LONG:
            lines["L"] = ["IC IR RE", "L", ""]
            return "L"
        lines["X"] = ["S", "X", ""]
        return "X"
    used = set()
    for r in runs:
        used |= {p[0] for p in r[3]}
    # stops: inside ones by didok, edge ones by didok@neighbour (the same far station is reached by several
    # lines from different sides)
    skeys, stops = {}, []

    def sidx(key, name, lat, lon, edge):
        if key not in skeys:
            skeys[key] = len(stops)
            stops.append([name, round(lat, 5), round(lon, 5), key, 1 if edge else 0])
        return skeys[key]
    patterns, profiles, out_trips = {}, {}, []
    for tid, name, desc, part, service in runs:
        line = line_of(name, desc, part)
        seq = []
        for n, (k, a, d, edge) in enumerate(part):
            if edge:
                nb = part[n + 1][0] if n == 0 else part[n - 1][0]
                key = f"{k}@{nb}"
            else:
                key = k
            nm, la, lo = station.get(k, (k, 0.0, 0.0))
            seq.append((sidx(key, nm, la, lo, edge), a, d))
        p = patterns.setdefault((line, tuple(s[0] for s in seq)), len(patterns))
        t0 = seq[0][2]
        prof = []
        for _, a, d in seq:
            prof += [a - t0, d - t0]
        prof[0] = 0
        q = profiles.setdefault(tuple(delta(prof)), len(profiles))
        out_trips.append([p, q, t0, mask[service], tid])
    out_trips.sort(key=lambda r: (r[2], r[0]))
    pat_list = [None] * len(patterns)
    for (line, seq), i in patterns.items():
        pat_list[i] = [line, list(seq)]
    prof_list = [None] * len(profiles)
    for prof, i in profiles.items():
        prof_list[i] = list(prof)
    return {
        "built": datetime.datetime.now().isoformat(timespec="seconds"), "feed": feed, "tz": TZ,
        "source": "opentransportdata.swiss GTFS (timetable), rail round Zürich",
        "days": [d.isoformat() for d in days],
        "lines": lines,
        "stops": stops,
        "patterns": pat_list,
        "profiles": prof_list,
        "trips": out_trips,
        "_doc": "lines: key -> [name, kind (S ZVV S-Bahn, N night S-Bahn, L long distance, X other networks), "
                "colour]; stops: [name, lat, lon, key (didok, or didok@neighbour for an edge stop), edge]; "
                "patterns: [line, [stop...]]; profiles: [arr,dep per stop, seconds from the first departure, as "
                "differences]; trips: [pattern, profile, first departure (seconds after the service day's noon "
                "minus 12 h, may pass 24 h), day bits (bit i = days[i]), GTFS trip_id]",
    }


# ---------------------------------------------------------------------------------------------------
# the schematic

# The wall's few words: station -> label (placed beside the station where it fits).
LABELS = {
    "Zürich HB": "HB", "Zürich Oerlikon": "OERLIKON", "Winterthur": "WINTERTHUR", "Zürich Flughafen": "AIRPORT",
    "Baden": "BADEN", "Zug": "ZUG", "Uster": "USTER", "Wädenswil": "WAEDENSWIL", "Rapperswil SG": "RAPPERSWIL",
    "Bülach": "BUELACH", "Dietikon": "DIETIKON", "Wetzikon ZH": "WETZIKON",
    "Thalwil": "THALWIL", "Affoltern am Albis": "AFFOLTERN", "Zürich Stadelhofen": "STADELHOFEN",
    "Zürich Altstetten": "ALTSTETTEN", "Zürich Hardbrücke": "HARDBRUECKE",
}
# Stations drawn as rings (interchanges are found automatically; these are added).
RINGS = {"Zürich HB", "Zürich Stadelhofen", "Zürich Hardbrücke", "Zürich Oerlikon", "Zürich Altstetten",
         "Zürich Flughafen", "Winterthur", "Uster", "Wädenswil", "Baden", "Zug", "Thalwil", "Rapperswil SG",
         "Bülach", "Dietikon", "Effretikon", "Wetzikon ZH", "Stettbach", "Pfäffikon SZ", "Zürich Enge",
         "Zürich Wiedikon", "Zürich Selnau", "Meilen", "Affoltern am Albis", "Rüti ZH"}
HOME = None                                # no home marker: the map is the region's, not a stop's
MAG = 2.5                                  # km: inside this the geography is to scale, outside it is squeezed
MARGIN = (4, 4, 4, 4)
GAP = 3                                    # LEDs between neighbouring stations at the least
HOP = (3, 6)
ANCHOR = 0.10
OVERRIDES = {
    # the heart: one wide rainbow across the city, Altstetten - Hardbrücke - HB - Stadelhofen, the fourteen
    # lines between Hardbrücke and HB side by side; Oerlikon above, the lake below
    "Zürich HB": (88, 120), "Zürich Hardbrücke": (64, 120), "Zürich Altstetten": (40, 120),
    "Zürich Stadelhofen": (112, 120), "Zürich Oerlikon": (88, 76), "Stettbach": (136, 96),
    "Zürich Tiefenbrunnen": (120, 128), "Zürich Selnau": (72, 136), "Zürich Saalsporthalle": (72, 148),
    "Zürich Binz": (64, 144), "Zürich Triemli": (56, 152), "Ringlikon": (48, 160), "Uetliberg": (48, 168),
    # west: the Limmat valley to Baden, the Furttal, the Freiamt
    "Dietikon": (24, 120), "Killwangen-Spreitenbach": (12, 120), "Wettingen": (12, 100), "Baden": (12, 88),
    "Würenlos": (28, 92), "Regensdorf-Watt": (56, 76), "Berikon-Widen": (24, 140), "Bremgarten": (12, 152),
    "Bremgarten West": (6, 158), "Erdmannlistein": (2, 162), "Muri AG": (8, 240), "Boswil-Bünzen": (6, 228), "Mühlau": (16, 250),
    # north: the airport, the Glatt valley, the Rhine
    "Zürich Flughafen": (104, 56), "Oberglatt ZH": (80, 52), "Niederweningen": (48, 40), "Bülach": (80, 40),
    "Eglisau": (80, 28), "Rümikon AG": (60, 28), "Rafz": (80, 18), "Jestetten": (80, 8),
    # north-east: Winterthur and its valleys
    "Winterthur": (152, 48), "Andelfingen": (152, 24), "Marthalen": (144, 14), "Ossingen": (168, 14), "Oberwinterthur": (164, 48), "Seuzach": (164, 32),
    "Islikon": (186, 48), "Winterthur Grüze": (158, 54), "Elgg": (186, 54), "Winterthur Seen": (164, 60),
    "Sennhof-Kyburg": (170, 66), "Wila": (186, 82), "Bauma": (186, 96),
    "Effretikon": (136, 72), "Bassersdorf": (120, 64), "Wallisellen": (104, 84), "Dietlikon": (120, 84),
    # east: the Glatt valley and the Zürcher Oberland
    "Dübendorf": (148, 96), "Uster": (164, 120), "Pfäffikon ZH": (172, 108), "Wetzikon ZH": (172, 148),
    "Hinwil": (186, 156), "Rüti ZH": (176, 172), "Tann-Dürnten": (184, 172),
    # the lake: the right bank down to Rapperswil, the left bank to Wädenswil and Pfäffikon SZ
    "Küsnacht ZH": (132, 140), "Herrliberg-Feldmeilen": (140, 148), "Meilen": (144, 152),
    "Uetikon": (148, 156), "Stäfa": (156, 164), "Uerikon": (160, 168), "Rapperswil SG": (168, 200),
    "Pfäffikon SZ": (148, 224), "Thalwil": (88, 156), "Wädenswil": (116, 184), "Samstagern": (124, 236), "Schindellegi-Feusisberg": (128, 246),
    # south: the Sihl valley, the Knonaueramt, Zug
    "Langnau-Gattikon": (72, 184), "Sihlwald": (72, 192), "Affoltern am Albis": (36, 164),
    "Knonau": (48, 208), "Baar": (88, 212), "Baar Lindenpark": (84, 226), "Zug": (80, 240), "Cham": (64, 248), "Zug Fridbach": (80, 252),
}
VIAS = {
    ("Zürich Hardbrücke", "Zürich Oerlikon"): [(64, 100)],
}

CENTRE_KM = (0.0, 0.0)                     # km() is already relative to CENTRE
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def fisheye(x, y):
    r = math.hypot(x, y)
    if r < 1e-9:
        return 0.0, 0.0
    k = MAG * math.asinh(r / MAG) / r
    return x * k, y * k


def snap_dir(vx, vy):
    a = math.atan2(vy, vx)
    return DIRS[int(round(a / (math.pi / 4))) % 8]


def dijkstra(adj, a, b):
    import heapq
    dist, prev, q = {a: 0.0}, {}, [(0.0, a)]
    while q:
        d, u = heapq.heappop(q)
        if u == b:
            break
        if d > dist[u]:
            continue
        for v, w in adj[u].items():
            if d + w < dist.get(v, 1e18):
                dist[v], prev[v] = d + w, u
                heapq.heappush(q, (d + w, v))
    if b not in dist:
        return None
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])
    return path[::-1]


def polyline(pa, pb, mid=None):
    """Corner points from pa to pb: straight if the run is octilinear, else a straight part and a
    45-degree part, bent on the side nearer `mid` (where the stations in between really are)."""
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    if dx == 0 or dy == 0 or abs(dx) == abs(dy):
        return [list(pa), list(pb)]
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    m = min(abs(dx), abs(dy))
    diag = (sx * m, sy * m)
    c1 = (pa[0] + diag[0], pa[1] + diag[1])
    c2 = (pb[0] - diag[0], pb[1] - diag[1])
    if mid is not None:
        d1 = (c1[0] - mid[0]) ** 2 + (c1[1] - mid[1]) ** 2
        d2 = (c2[0] - mid[0]) ** 2 + (c2[1] - mid[1]) ** 2
        c = c1 if d1 < d2 else c2
    else:
        c = c2 if abs(dx) > abs(dy) else c1
    return [list(pa), list(c), list(pb)]


def walk(corners):
    out = [tuple(corners[0])]
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        n = max(abs(x1 - x0), abs(y1 - y0))
        sx, sy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
        for i in range(1, n + 1):
            out.append((x0 + sx * i, y0 + sy * i))
    return out


def build_layout(data):
    import numpy as np
    stops = data["stops"]
    names = [s[0] for s in stops]
    keys = [s[3] for s in stops]
    edge = [bool(s[4]) for s in stops]
    geo = [km(s[1], s[2]) for s in stops]
    kind = {k: v[1] for k, v in data["lines"].items()}
    # the drawing graph: every hop of every pattern; a hop that skips stations another pattern serves
    # (an express) is routed along the stopping track when that is not much of a detour
    hops = {}
    for line, seq in data["patterns"]:
        for a, b in zip(seq, seq[1:]):
            if a != b:
                hops.setdefault(frozenset((a, b)), set()).add(line)
    dist = lambda a, b: math.hypot(geo[a][0] - geo[b][0], geo[a][1] - geo[b][1])
    adj = {i: {} for i in range(len(stops))}
    for h in hops:
        a, b = tuple(h)
        adj[a][b] = adj[b][a] = dist(a, b)
    for h in sorted(hops, key=lambda h: -dist(*tuple(h))):
        a, b = tuple(h)
        w = adj[a].pop(b)
        del adj[b][a]
        p = dijkstra(adj, a, b)
        if p is None or sum(dist(u, v) for u, v in zip(p, p[1:])) > 1.45 * w + 0.5 \
                or any(edge[u] for u in p[1:-1]):
            adj[a][b] = adj[b][a] = w                          # a real track of its own
    # an edge station hangs off the wall where its trains really leave the region: a train from Zürich HB
    # straight to Bern leaves along the Limmat valley, not across the map. Exits by stopping trains from a
    # station near the border are true exits; any other edge station is moved onto the true exit where the
    # way out along the drawn tracks and then on to the far station is shortest, and leaves the wall there.
    def inside_len(a, b, n=24):
        tot = 0.0
        for k in range(n):
            t = (k + 0.5) / n
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            if (x / AXES[0]) ** 2 + (y / AXES[1]) ** 2 <= 1.0:
                tot += 1.0 / n
        return tot * math.hypot(b[0] - a[0], b[1] - a[1])
    import heapq
    inner_adj = {u: {v: w for v, w in adj[u].items() if not edge[v]} for u in adj if not edge[u] and adj[u]}
    exits, moved, exit_dir = [], [], {}
    for e in [i for i in adj if edge[i] and adj[i]]:
        n = next(iter(adj[e]))
        if dist(n, e) < 12.0 or inside_len(geo[n], geo[e]) < 3.0:
            exits.append((n, e))
        else:
            moved.append((n, e))
    for n, e in moved:
        gd, q = {n: 0.0}, [(0.0, n)]
        while q:
            d0, u = heapq.heappop(q)
            if d0 > gd[u]:
                continue
            for v, w in inner_adj.get(u, {}).items():
                if d0 + w < gd.get(v, 1e18):
                    gd[v] = d0 + w
                    heapq.heappush(q, (d0 + w, v))
        best = min(((gd[b] + dist(b, x) + dist(x, e), b, x) for b, x in exits if b in gd), default=None)
        if best is None:
            continue
        _, b, x = best
        del adj[n][e]
        del adj[e][n]
        adj[e][b] = adj[b][e] = dist(b, e)
        exit_dir[e] = x                                         # it leaves the wall along that exit
    used = [i for i in adj if adj[i]]
    inner = [i for i in used if not edge[i]]
    ends = {seq[0] for _, seq in data["patterns"]} | {seq[-1] for _, seq in data["patterns"]}
    junc = {i for i in used if len(adj[i]) != 2 or i in ends or edge[i]}
    junc |= {i for i in used if names[i] in OVERRIDES}
    junc |= {n for i in used if edge[i] for n in adj[i]}             # the stations trains leave the wall from
    links, seen = [], set()
    for j in sorted(junc):
        for n in sorted(adj[j]):
            if (j, n) in seen:
                continue
            chain = [j, n]
            while chain[-1] not in junc:
                nx = [v for v in adj[chain[-1]] if v != chain[-2]][0]
                chain.append(nx)
            if chain[-1] == j:
                raise RuntimeError(f"loop in the network at {names[j]}: add a station on it to OVERRIDES")
            seen.add((chain[-1], chain[-2]))
            seen.add((j, n))
            links.append(chain)
    # first positions: the geography, magnified round the centre, stretched to the wall
    hb = next(i for i in used if names[i] == "Zürich HB")
    fe = {i: fisheye(geo[i][0] - geo[hb][0], geo[i][1] - geo[hb][1]) for i in used}
    xs, ys = [fe[i][0] for i in inner], [fe[i][1] for i in inner]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sx = (W - 1 - MARGIN[0] - MARGIN[2]) / (x1 - x0)
    sy = (H - 1 - MARGIN[1] - MARGIN[3]) / (y1 - y0)
    p0 = {i: ((fe[i][0] - x0) * sx + MARGIN[0], (fe[i][1] - y0) * sy + MARGIN[1]) for i in used}
    N = len(inner)
    ui = {u: k for k, u in enumerate(inner)}
    nb = {u: {v for v in adj[u] if not edge[v]} for u in inner}
    edges = sorted({(min(a, b), max(a, b)) for a in inner for b in nb[a]})
    pos = np.array([p0[u] for u in inner], float)
    pins = {ui[i]: OVERRIDES[names[i]] for i in inner if names[i] in OVERRIDES}
    s_lines = lambda a, b: {l for l in hops.get(frozenset((a, b)), ()) if kind.get(l) == "S"}
    width = {u: max([len(s_lines(u, v)) for v in nb[u]] + [1]) for u in inner}
    dirs = {}
    hop_len = {}
    for a, b in edges:
        g = math.hypot(p0[b][0] - p0[a][0], p0[b][1] - p0[a][1])
        hop_len[(a, b)] = max(HOP[0], min(HOP[1], g), len(s_lines(a, b)) + 2)
    for it in range(int(os.environ.get("TRAINS_ITERS", 50))):
        A, rhs = [], []

        def row(coefs, val, w):
            r = np.zeros(2 * N)
            for idx, c in coefs:
                r[idx] += c * w
            A.append(r)
            rhs.append(val * w)
        for a, b in edges:
            ia, ib = ui[a], ui[b]
            v = pos[ib] - pos[ia]
            if (a, b) not in dirs or it == 10:
                dirs[(a, b)] = snap_dir(*v)
            dx, dy = dirs[(a, b)]
            nx, ny = -dy, dx
            row([(2 * ib, nx), (2 * ib + 1, ny), (2 * ia, -nx), (2 * ia + 1, -ny)], 0.0, 3.0)
            m = max(abs(dx), abs(dy))
            k = 1.0 / (dx * dx + dy * dy) * m
            along = (v[0] * dx + v[1] * dy) * k
            row([(2 * ib, dx * k), (2 * ib + 1, dy * k), (2 * ia, -dx * k), (2 * ia + 1, -dy * k)],
                max(along, GAP) if it < 3 else hop_len[(a, b)], 0.7)
            gap = max(GAP, (width[a] + width[b]) / 2 + 1)
            if along < gap:
                row([(2 * ib, dx * k), (2 * ib + 1, dy * k), (2 * ia, -dx * k), (2 * ia + 1, -dy * k)], gap, 3.0)
        for u in inner:
            if len(nb[u]) == 2 and u not in junc:
                a, b = sorted(nb[u])
                for c in range(2):
                    row([(2 * ui[a] + c, 1), (2 * ui[b] + c, 1), (2 * ui[u] + c, -2)], 0.0, 0.6)
        if it > 5:
            near = pos[:, None, :] - pos[None, :, :]
            dd = np.abs(near).max(axis=2)
            wv = np.array([width[u] for u in inner], float)
            need = np.maximum(GAP, (wv[:, None] + wv[None, :]) / 2 + 2)
            for ia, ib in zip(*np.nonzero((dd < need) & (np.triu(np.ones((N, N)), 1) > 0))):
                a, b = inner[ia], inner[ib]
                if b in nb[a]:
                    continue
                v = pos[ib] - pos[ia]
                n = np.hypot(*v)
                v = v / n if n > 1e-6 else np.array([1.0, 0.0])
                row([(2 * ib, v[0]), (2 * ib + 1, v[1]), (2 * ia, -v[0]), (2 * ia + 1, -v[1])], need[ia, ib], 2.0)
        for k, u in enumerate(inner):
            w = 4.0 if k in pins else ANCHOR
            target = pins.get(k, p0[u])
            for c in range(2):
                row([(2 * k + c, 1)], target[c], w)
        pos = np.linalg.lstsq(np.array(A), np.array(rhs), rcond=None)[0].reshape(-1, 2)
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    room = np.array([W - 1 - MARGIN[0] - MARGIN[2], H - 1 - MARGIN[1] - MARGIN[3]], float)
    if not pins:
        k = min(room[0] / (hi[0] - lo[0]), room[1] / (hi[1] - lo[1]))
        pos = (pos - lo) * k + np.array([MARGIN[0], MARGIN[1]]) + (room - (hi - lo) * k) / 2
        print(f"schematic: {hi[0] - lo[0]:.0f} x {hi[1] - lo[1]:.0f} LEDs before fitting, scaled by {k:.2f}")
    solved = {u: pos[ui[u]] for u in inner}
    for u in inner:
        if names[u] in OVERRIDES:
            solved[u] = np.array(OVERRIDES[names[u]], float)
    P = {j: (int(round(solved[j][0])), int(round(solved[j][1]))) for j in junc if not edge[j]}
    loose = sorted(names[j] for j in P if names[j] not in OVERRIDES)
    if loose:
        print("junctions placed by the solver alone:", ", ".join(f"{n} {P[next(j for j in P if names[j] == n)]}" for n in loose))
    # edge stations: off the wall, straight out from their neighbour towards the real far station
    for j in junc:
        if not edge[j]:
            continue
        n = next(iter(adj[j]))
        if n not in P:
            continue
        far = exit_dir.get(j, j)
        d0 = snap_dir(geo[far][0] - geo[n][0], geo[far][1] - geo[n][1])
        k0 = DIRS.index(d0)

        def reach(d):
            x, y, s = P[n][0], P[n][1], 0
            while 0 <= x < W and 0 <= y < H:
                x, y, s = x + d[0], y + d[1], s + 1
            return s
        d = min((DIRS[(k0 + o) % 8] for o in (0, -1, 1)), key=lambda d: reach(d) + (0 if d == d0 else 4) + (6 if d[0] and d[1] else 0))
        x, y = P[n]
        steps = 0
        while 0 <= x < W and 0 <= y < H or steps < 4:
            x, y = x + d[0], y + d[1]
            steps += 1
        P[j] = (x + d[0] * 2, y + d[1] * 2)
    xy = dict(P)
    out_links = []
    for ch in links:
        a, b = ch[0], ch[-1]
        if a not in P or b not in P:
            continue
        mids = ch[1:-1]
        mid = solved[mids[len(mids) // 2]] if mids else None
        via = VIAS.get((names[a], names[b]))
        if via is None and (names[b], names[a]) in VIAS:
            via = VIAS[(names[b], names[a])][::-1]
        if via:
            corners = []
            for q0, q1 in zip([P[a]] + via, via + [P[b]]):
                c = polyline(tuple(q0), tuple(q1))
                corners += c[1:] if corners else c
        else:
            corners = polyline(P[a], P[b], mid)
        path = walk(corners)
        n = len(path) - 1
        g = [0.0]
        for u, v in zip(ch, ch[1:]):
            g.append(g[-1] + float(np.hypot(*(solved.get(v, P.get(v)) - np.array(solved.get(u, P.get(u)))))) + 1e-6)
        at = [0]
        for k in range(1, len(ch) - 1):
            f = 0.5 * g[k] / g[-1] + 0.5 * k / (len(ch) - 1)
            at.append(int(round(f * n)))
        at.append(n)
        sp = min(GAP, max(1, n // (len(ch) - 1)))
        for k in range(1, len(at) - 1):
            at[k] = max(at[k], at[k - 1] + sp)
        for k in range(len(at) - 2, 0, -1):
            at[k] = min(at[k], at[k + 1] - sp)
        for k, u in enumerate(ch[1:-1], 1):
            xy[u] = path[max(0, min(n, at[k]))]
        out_links.append({"stops": [keys[u] for u in ch], "at": at, "corners": corners, "lines": set()})
    # every pattern's hops routed over the drawing graph: each link knows the S lines on it (side by side)
    # and whether anything else runs there
    link_of = {}
    for k, L in enumerate(out_links):
        for u, v in zip(L["stops"], L["stops"][1:]):
            link_of[frozenset((u, v))] = k
    other = set()
    for line, seq in data["patterns"]:
        for a, b in zip(seq, seq[1:]):
            p = dijkstra(adj, a, b) if a != b else None
            for u, v in zip(p or [], (p or [])[1:]):
                k = link_of.get(frozenset((keys[u], keys[v])))
                if k is None:
                    continue
                if kind.get(line) == "S":
                    out_links[k]["lines"].add(line)
                else:
                    other.add(k)
    order_lines(out_links)
    key_of = {names[i]: keys[i] for i in inner}
    lab = {key_of[n]: t for n, t in LABELS.items() if n in key_of}       # in LABELS order: the first placed first
    rings = [keys[i] for i in inner if names[i] in RINGS]
    home = next((keys[i] for i in inner if names[i] == HOME), None)
    return {
        "w": W, "h": H, "built": data.get("built", ""),
        "stops": {keys[i]: [int(xy[i][0]), int(xy[i][1]), names[i]] for i in used if i in xy},
        "links": [[L["stops"], L["at"], [list(map(int, c)) for c in L["corners"]], L["lines"], 1 if k in other else 0]
                  for k, L in enumerate(out_links)],
        "labels": lab, "rings": rings, "home": home,
        "_doc": "stops: key -> [x, y, name] (edge stations lie off the wall); links: [stations along it, their "
                "step index along the route, the route's corner points, the ZVV S lines on it in their "
                "side-by-side order, 1 if other trains (long distance, night, neighbours) run on it too]",
    }


def _num(l):
    try:
        return int(l.lstrip("S"))
    except ValueError:
        return 999


def order_lines(links):
    """Side-by-side order of the S lines on every link, so a line keeps its side through junctions:
    a few rounds of swapping neighbours where that shortens the jogs at the link ends."""
    for L in links:
        L["lines"] = sorted(L["lines"], key=_num)
    at_node = {}
    for k, L in enumerate(links):
        at_node.setdefault(L["stops"][0], []).append((k, 0))
        at_node.setdefault(L["stops"][-1], []).append((k, 1))

    def offset(k, line, end):
        L = links[k]
        n = len(L["lines"])
        slot = L["lines"].index(line) - (n - 1) / 2.0
        c = L["corners"]
        a, b = (c[0], c[1]) if end == 0 else (c[-2], c[-1])
        d = (b[0] - a[0], b[1] - a[1])
        m = max(abs(d[0]), abs(d[1])) or 1
        d = (d[0] / m, d[1] / m)
        return (-d[1] * slot, d[0] * slot)

    def cost(k):
        tot = 0.0
        L = links[k]
        for end in (0, 1):
            node = L["stops"][-end]
            for line in L["lines"]:
                o = offset(k, line, end)
                for k2, e2 in at_node[node]:
                    if k2 != k and line in links[k2]["lines"]:
                        o2 = offset(k2, line, e2)
                        tot += math.hypot(o[0] - o2[0], o[1] - o2[1])
        return tot

    # first a propagation: the widest link keeps its order, every other link (widest first, next to one
    # already ordered) sorts its lines by where they lie across the links already ordered at its ends
    done = set()
    order = sorted(range(len(links)), key=lambda k: -len(links[k]["lines"]))
    if order:
        done.add(order[0])
    for _ in range(len(links)):
        best = None
        for k in order:
            if k in done or not links[k]["lines"]:
                continue
            ends = [(e, k2, e2) for e in (0, 1) for k2, e2 in at_node[links[k]["stops"][-e]] if k2 in done]
            if ends:
                best = (k, ends)
                break
        if best is None:
            break
        k, ends = best
        L = links[k]
        c = L["corners"]

        def side(line):
            vals = []
            for e, k2, e2 in ends:
                if line in links[k2]["lines"]:
                    o = offset(k2, line, e2)
                    a, b = (c[0], c[1]) if e == 0 else (c[-2], c[-1])
                    d = (b[0] - a[0], b[1] - a[1])
                    m = max(abs(d[0]), abs(d[1])) or 1
                    nx, ny = -d[1] / m, d[0] / m
                    vals.append(o[0] * nx + o[1] * ny)
            return sum(vals) / len(vals) if vals else 0.0
        L["lines"] = sorted(L["lines"], key=side)
        done.add(k)
    for _ in range(16):
        changed = False
        for k, L in enumerate(links):
            best = cost(k)
            for i in range(len(L["lines"]) - 1):
                L["lines"][i], L["lines"][i + 1] = L["lines"][i + 1], L["lines"][i]
                c = cost(k)
                if c < best - 1e-9:
                    best, changed = c, True
                else:
                    L["lines"][i], L["lines"][i + 1] = L["lines"][i + 1], L["lines"][i]
        if not changed:
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip")
    ap.add_argument("--layout-only", action="store_true")
    ap.add_argument("--start", help="first day (YYYY-MM-DD), default today in Zürich")
    ap.add_argument("--skip-if-current", action="store_true", help="do nothing when the asset already starts today")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.skip_if_current and not a.layout_only:
        from zoneinfo import ZoneInfo
        today = (a.start or datetime.datetime.now(ZoneInfo(TZ)).date().isoformat())
        try:
            with gzip.open(DATA, "rt") as fh:
                if json.load(fh)["days"][0] == today:
                    print("the timetable already starts today: nothing to do")
                    return
        except Exception:
            pass
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
    try:
        lay = build_layout(data)
    except Exception as e:                                      # keep the last schematic: the display skips
        print(f"schematic failed, the old one stays: {e}")     # what it cannot route, the rest runs on
        return
    with open(LAYOUT, "w") as fh:
        json.dump(lay, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"{LAYOUT}: {os.path.getsize(LAYOUT) / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
