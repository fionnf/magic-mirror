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
    days = [start + datetime.timedelta(d) for d in range(DAYS)]
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

# The wall's few words: stop name -> its label (the display places it beside the stop where it fits).
LABELS = {
    "Bahnhofplatz/HB": "HB", "Central": "CENTRAL", "Bellevue": "BELLEVUE", "Paradeplatz": "PARADEPL",
    "Rennweg": "RENNWEG", "Oerlikon, Bahnhof": "OERLIKON", "Milchbuck": "MILCHBUCK", "Enge, Bahnhof": "ENGE",
    "Flughafen, Fracht": "AIRPORT", "Stettbach, Bahnhof": "STETTBACH", "Schlieren, Geissweid": "SCHLIEREN",
    "Triemli": "TRIEMLI", "Klusplatz": "KLUSPL", "Rehalp": "REHALP", "Wollishoferplatz": "WOLLISHOFEN",
    "Tiefenbrunnen, Bahnhof": "TIEFENBR", "Zoo": "ZOO", "Hirzenbach": "HIRZENBACH", "Albisgütli": "ALBISGUETLI",
    "Seebach": "SEEBACH", "Frankental": "FRANKENTAL",
}
HOME = "Rennweg"
CENTRE = (47.3745, 8.5395)               # the magnification is around HB / Paradeplatz / Central
MARGIN = (10, 9, 10, 9)                  # left, top, right, bottom: room for the end labels
FISHEYE = float(os.environ.get("TRAMS_FE", 0.7))                           # km: inside this the map is to scale, outside it is squeezed
GAP = 4                                  # LEDs between neighbouring stops at the least
HOP = (4, 7)                             # LEDs a hop between two stops would like to be: least, most
ANCHOR = 0.12                            # how firmly the stops hold to the magnified geography
# Hand adjustments. OVERRIDES: stop -> (x, y), pinned in the relaxation and kept exactly. VIAS: the
# corner points of the run between two junctions, where one bend is not enough or bends the wrong way.
OVERRIDES = {
    # the centre: HB and Central, the Bahnhofstrasse (Rennweg) down to Paradeplatz, the lake front
    "Bahnhofplatz/HB": (104, 116), "Central": (140, 116), "Bahnhofstrasse/HB": (104, 128),
    "Paradeplatz": (104, 152), "Sihlpost/HB": (88, 122), "Stauffacher": (78, 140),
    "Sihlstrasse": (90, 152), "Stockerstrasse": (96, 170), "Tunnelstrasse": (96, 180),
    "Enge, Bahnhof": (96, 188), "Enge, Bahnhof/Bederstr.": (88, 188), "Bürkliplatz": (120, 172),
    "Bellevue": (140, 172), "Stadelhofen, Bahnhof": (146, 178), "Kreuzplatz": (158, 178),
    # west: the spokes to Frankental, Werdhölzli, Altstetten, Schlieren, Albisrieden and Triemli
    "Hardbrücke, Bahnhof": (78, 112), "Schiffbau": (78, 104), "Technopark": (70, 104),
    "Escher-Wyss-Platz": (86, 96), "Wipkingerplatz": (92, 90), "Hardturm": (62, 84),
    "Werdhölzli": (14, 84), "Frankental": (16, 74), "Altstetten, Bahnhof N": (34, 92),
    "Bezirksgebäude": (70, 132), "Kalkbreite/Bhf.Wiedikon": (58, 132), "Albisriederplatz": (42, 116),
    "Kappeli": (42, 104), "Grimselstrasse": (38, 100), "Schlieren, Geissweid": (4, 100),
    "Albisrieden": (10, 128), "Werd": (70, 148), "Wiedikon, Bahnhof": (62, 156),
    "Heuried": (28, 156), "Triemli": (10, 168),
    # south
    "Laubegg": (74, 212), "Albisgütli": (52, 224), "Butzenstrasse": (96, 234),
    "Wollishoferplatz": (96, 244), "Tiefenbrunnen, Bahnhof": (158, 224), "Rehalp": (186, 218),
    # east
    "Haldenegg": (144, 104), "ETH/Universitätsspital": (152, 118), "Platte": (152, 134),
    "Kunsthaus": (152, 154), "Römerhof": (166, 162), "Klusplatz": (180, 162),
    "Kirche Fluntern": (166, 128), "Zoo": (186, 110),
    # north: Milchbuck, Oerlikon, the Glattal and the airport
    "Schaffhauserplatz": (118, 78), "Milchbuck": (130, 66), "Universität Irchel": (138, 74),
    "Langmauerstrasse": (152, 74), "Salersteig": (130, 56), "Sternen Oerlikon": (130, 46),
    "Oerlikon, Bahnhof": (114, 46), "Oerlikon, Bahnhof Ost": (130, 36), "Leutschenbach": (144, 36),
    "Messe/Hallenstadion": (144, 46), "Glattpark, Glattpark": (156, 30), "Auzelg": (168, 42),
    "Flughafen, Fracht": (186, 8), "Seebach": (112, 22), "Bucheggplatz": (100, 66),
    "Schwamendingerplatz": (160, 66), "Hirzenbach": (184, 52), "Stettbach, Bahnhof": (186, 86),
}
VIAS = {
    ("Bahnhofstrasse/HB", "Central"): [(128, 128)],
    ("Bahnhofplatz/HB", "Sihlpost/HB"): [(98, 122)],
    ("Bahnhofstrasse/HB", "Sihlpost/HB"): [(94, 128)],
    ("Sihlpost/HB", "Stauffacher"): [(88, 130)],
    ("Stauffacher", "Stockerstrasse"): [(78, 162), (86, 170)],
    ("Sihlstrasse", "Stockerstrasse"): [(90, 164)],
    ("Paradeplatz", "Stockerstrasse"): [(104, 162)],
    ("Paradeplatz", "Bürkliplatz"): [(120, 168)],
    ("Central", "Kunsthaus"): [(146, 122), (146, 148)],
    ("Haldenegg", "ETH/Universitätsspital"): [(144, 110)],
    ("Haldenegg", "Schaffhauserplatz"): [(144, 92), (130, 78)],
    ("Escher-Wyss-Platz", "Schaffhauserplatz"): [(94, 104), (110, 104), (118, 96)],
    ("Escher-Wyss-Platz", "Hardturm"): [(74, 84)],
    ("Wipkingerplatz", "Frankental"): [(76, 74)],
    ("Technopark", "Altstetten, Bahnhof N"): [(58, 92)],
    ("Stettbach, Bahnhof", "Auzelg"): [(190, 82), (190, 42)],
    ("Bellevue", "Tiefenbrunnen, Bahnhof"): [(140, 206)],
}


def project(lat, lon):
    """Kilometres east and south of CENTRE."""
    return ((lon - CENTRE[1]) * 111.32 * math.cos(math.radians(CENTRE[0])), (CENTRE[0] - lat) * 111.32)


def fisheye(x, y):
    r = math.hypot(x, y)
    if r < 1e-9:
        return 0.0, 0.0
    k = FISHEYE * math.asinh(r / FISHEYE) / r
    return x * k, y * k


DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def snap_dir(vx, vy):
    a = math.atan2(vy, vx)
    return DIRS[int(round(a / (math.pi / 4))) % 8]


def cheb(v):
    return max(abs(v[0]), abs(v[1]))


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
    45-degree part, bent on the side nearer `mid` (where the stops in between really are)."""
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    if dx == 0 or dy == 0 or abs(dx) == abs(dy):
        return [list(pa), list(pb)]
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    m = min(abs(dx), abs(dy))
    diag = (sx * m, sy * m)
    c1 = (pa[0] + diag[0], pa[1] + diag[1])                     # diagonal first
    c2 = (pb[0] - diag[0], pb[1] - diag[1])                     # straight first
    if mid is not None:
        d1 = (c1[0] - mid[0]) ** 2 + (c1[1] - mid[1]) ** 2
        d2 = (c2[0] - mid[0]) ** 2 + (c2[1] - mid[1]) ** 2
        c = c1 if d1 < d2 else c2
    else:
        c = c2 if abs(dx) > abs(dy) else c1
    return [list(pa), list(c), list(pb)]


def walk(corners):
    """Every LED along the corner points, one per step (diagonal steps count one)."""
    out = [tuple(corners[0])]
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        n = max(abs(x1 - x0), abs(y1 - y0))
        sx, sy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
        for i in range(1, n + 1):
            out.append((x0 + sx * i, y0 + sy * i))
    return out


def build_layout(data):
    stops = data["stops"]
    names = [s[0] for s in stops]
    keys = [s[3] for s in stops]
    geo = [project(s[1], s[2]) for s in stops]
    # the drawing graph: every hop of every pattern; a hop that skips stops another pattern serves
    # (an express or a turn) is left out of the drawing and routed along the stopping track
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
        if p is None or len(p) > 6 or sum(dist(u, v) for u, v in zip(p, p[1:])) > 1.35 * w:
            adj[a][b] = adj[b][a] = w                          # a real track of its own
    used = [i for i in adj if adj[i]]
    # junctions: forks, ends and the termini of any line
    ends = {seq[0] for _, seq in data["patterns"]} | {seq[-1] for _, seq in data["patterns"]}
    junc = {i for i in used if len(adj[i]) != 2 or i in ends}
    for nm, _ in OVERRIDES.items():
        junc |= {i for i in used if names[i] == nm}
    links, seen = [], set()
    for j in sorted(junc):
        for n in sorted(adj[j]):
            if (j, n) in seen:
                continue
            chain = [j, n]
            while chain[-1] not in junc:
                nx = [v for v in adj[chain[-1]] if v != chain[-2]][0]
                chain.append(nx)
            if chain[-1] == j:                                  # a loop: its middle becomes a junction
                junc.add(chain[len(chain) // 2])
                return build_layout_retry(data)
            seen.add((chain[-1], chain[-2]))
            seen.add((j, n))
            links.append(chain)
    # first positions: the geography, magnified in the centre, stretched to the wall
    fe = {i: fisheye(*geo[i]) for i in used}
    xs, ys = [fe[i][0] for i in used], [fe[i][1] for i in used]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sx = (W - 1 - MARGIN[0] - MARGIN[2]) / (x1 - x0)
    sy = (H - 1 - MARGIN[1] - MARGIN[3]) / (y1 - y0)
    sx, sy = min(sx, sy * 1.25), min(sy, sx * 1.4)
    ox = MARGIN[0] + ((W - 1 - MARGIN[0] - MARGIN[2]) - (x1 - x0) * sx) / 2
    oy = MARGIN[1] + ((H - 1 - MARGIN[1] - MARGIN[3]) - (y1 - y0) * sy) / 2
    p0 = {i: ((fe[i][0] - x0) * sx + ox, (fe[i][1] - y0) * sy + oy) for i in used}
    # relax every stop towards octilinear hops (linear least squares, a few dozen rounds): each hop
    # keeps to its nearest 0/45/90 degree direction and is at least GAP long, chains run smoothly
    # through their ordinary stops, stops that are not neighbours keep GAP apart, and everything is
    # held lightly to the magnified geography (firmly where OVERRIDES pins it)
    import numpy as np
    N = len(used)
    ui = {u: k for k, u in enumerate(used)}
    edges = sorted({(min(a, b), max(a, b)) for a in used for b in adj[a]})
    pos = np.array([p0[u] for u in used], float)
    pins = {ui[i]: OVERRIDES[names[i]] for i in used if names[i] in OVERRIDES}
    dirs = {}
    nb = {u: set(adj[u]) for u in used}
    # schematic maps space their stops nearly evenly: every hop wants HOP LEDs, a little more where
    # the real hop is long (the outskirts), however squeezed the magnified geography is there
    hop_len = {}
    for a, b in edges:
        g = math.hypot(p0[b][0] - p0[a][0], p0[b][1] - p0[a][1])
        n = len(hops.get(frozenset((a, b)), ()))
        hop_len[(a, b)] = max(HOP[0], min(HOP[1], g), n + 3)   # room for the rings round a wide bundle
    width = {u: max([len(hops.get(frozenset((u, v)), ())) for v in adj[u]] + [1]) for u in used}
    for it in range(int(os.environ.get("TRAMS_ITERS", 60))):
        rows, rhs = [], []

        def row(coefs, val, w):
            r = np.zeros(2 * N)
            for idx, c in coefs:
                r[idx] += c * w
            rows.append(r)
            rhs.append(val * w)
        for a, b in edges:
            ia, ib = ui[a], ui[b]
            v = pos[ib] - pos[ia]
            if (a, b) not in dirs:
                dirs[(a, b)] = snap_dir(*v)
            dx, dy = dirs[(a, b)]
            nx, ny = -dy, dx
            row([(2 * ib, nx), (2 * ib + 1, ny), (2 * ia, -nx), (2 * ia + 1, -ny)], 0.0, 3.0)
            m = max(abs(dx), abs(dy))
            k = 1.0 / (dx * dx + dy * dy) * m                 # along the hop in steps (diagonal = 1)
            along = (v[0] * dx + v[1] * dy) * k
            row([(2 * ib, dx * k), (2 * ib + 1, dy * k), (2 * ia, -dx * k), (2 * ia + 1, -dy * k)],
                max(along, GAP) if it < 3 else hop_len[(a, b)], 1.0)
            gap = max(GAP, (width[a] + width[b]) / 2 + 1)
            if along < gap:
                row([(2 * ib, dx * k), (2 * ib + 1, dy * k), (2 * ia, -dx * k), (2 * ia + 1, -dy * k)], gap, 3.0)
        for u in used:
            if len(nb[u]) == 2 and u not in junc:
                a, b = sorted(nb[u])
                for c in range(2):
                    row([(2 * ui[a] + c, 1), (2 * ui[b] + c, 1), (2 * ui[u] + c, -2)], 0.0, 0.6)
        if it > 5:
            near = pos[:, None, :] - pos[None, :, :]
            dd = np.abs(near).max(axis=2)
            wv = np.array([width[u] for u in used], float)
            need = np.maximum(GAP, (wv[:, None] + wv[None, :]) / 2 + 2)
            for ia, ib in zip(*np.nonzero((dd < need) & (np.triu(np.ones((N, N)), 1) > 0))):
                a, b = used[ia], used[ib]
                if b in nb[a]:
                    continue
                v = pos[ib] - pos[ia]
                n = np.hypot(*v)
                v = v / n if n > 1e-6 else np.array([1.0, 0.0])
                row([(2 * ib, v[0]), (2 * ib + 1, v[1]), (2 * ia, -v[0]), (2 * ia + 1, -v[1])], need[ia, ib], 2.0)
        for k, u in enumerate(used):
            w = 4.0 if k in pins else ANCHOR
            target = pins.get(k, p0[u])
            for c in range(2):
                row([(2 * k + c, 1)], target[c], w)
        A = np.array(rows)
        pos = np.linalg.lstsq(A, np.array(rhs), rcond=None)[0].reshape(-1, 2)
    # onto the wall: one scale for both axes (the 45-degree runs stay 45 degrees), centred
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    room = np.array([W - 1 - MARGIN[0] - MARGIN[2], H - 1 - MARGIN[1] - MARGIN[3]], float)
    k = min(room[0] / (hi[0] - lo[0]), room[1] / (hi[1] - lo[1]))
    print(f"schematic: {hi[0] - lo[0]:.0f} x {hi[1] - lo[1]:.0f} LEDs before fitting, scaled by {k:.2f}")
    pos = (pos - lo) * k + np.array([MARGIN[0], MARGIN[1]]) + (room - (hi - lo) * k) / 2
    solved = {u: pos[ui[u]] for u in used}
    for u in used:
        if names[u] in OVERRIDES:
            solved[u] = np.array(OVERRIDES[names[u]], float)
    P = {j: (int(round(solved[j][0])), int(round(solved[j][1]))) for j in junc}
    want = [(ch[0], ch[-1], None, None, ch) for ch in links]
    # the links' routes and the stops along them
    xy = {j: P[j] for j in junc}
    out_links = []
    for a, b, d, L, ch in want:
        mids = ch[1:-1]
        mid = None
        if mids:
            m = mids[len(mids) // 2]
            mid = solved[m]
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
        # stops along the route: half by their real spacing, half evenly
        g = [0.0]
        for u, v in zip(ch, ch[1:]):
            g.append(g[-1] + float(np.hypot(*(solved[v] - solved[u]))) + 1e-6)
        at = [0]
        for k in range(1, len(ch) - 1):
            f = 0.5 * g[k] / g[-1] + 0.5 * k / (len(ch) - 1)
            at.append(int(round(f * n)))
        at.append(n)
        for k in range(1, len(at) - 1):                         # keep them apart where there is room
            at[k] = max(at[k], at[k - 1] + min(GAP, max(1, n // (len(ch) - 1))))
        for k in range(len(at) - 2, 0, -1):
            at[k] = min(at[k], at[k + 1] - min(GAP, max(1, n // (len(ch) - 1))))
        for k, u in enumerate(ch[1:-1], 1):
            xy[u] = path[max(0, min(n, at[k]))]
        lines = set()
        for u, v in zip(ch, ch[1:]):
            lines |= hops.get(frozenset((u, v)), set())
        out_links.append({"stops": [keys[u] for u in ch], "at": at, "corners": corners, "lines": lines})
    # every pattern's hops routed over the drawing graph, so each link knows all the lines on it
    link_of = {}
    for k, L in enumerate(out_links):
        for u, v in zip(L["stops"], L["stops"][1:]):
            link_of[frozenset((u, v))] = k
    for line, seq in data["patterns"]:
        for a, b in zip(seq, seq[1:]):
            p = dijkstra(adj, a, b) if a != b else None
            for u, v in zip(p or [], (p or [])[1:]):
                k = link_of.get(frozenset((keys[u], keys[v])))
                if k is not None:
                    out_links[k]["lines"].add(line)
    order_lines(out_links)
    lab = {}
    for i in used:
        if names[i] in LABELS:
            lab[keys[i]] = LABELS[names[i]]
    home = next((keys[i] for i in used if names[i] == HOME), None)
    return {
        "w": W, "h": H, "built": data.get("built", ""),
        "stops": {keys[i]: [xy[i][0], xy[i][1], names[i]] for i in used if i in xy},
        "links": [[L["stops"], L["at"], L["corners"], L["lines"]] for L in out_links],
        "labels": lab, "home": home,
        "_doc": "stops: didok -> [x, y, name]; links: [stops along it, their step index along the route, "
                "the route's corner points, the lines on it in their side-by-side order]",
    }


def build_layout_retry(data):
    raise RuntimeError("loop in the network: add its middle stop to OVERRIDES")


def order_lines(links):
    """Side-by-side order of the lines on every link, so a line keeps its side through junctions:
    a few rounds of swapping neighbours where that shortens the jogs at the link ends."""
    for L in links:
        L["lines"] = sorted(L["lines"], key=int)
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

    for _ in range(12):
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
