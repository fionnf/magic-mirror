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

# The wall's few words: stop name -> (label, where the label goes relative to the stop: dx, dy of its
# top-left corner). Only places that matter and fit.
LABELS = {
    "Bahnhofplatz/HB": "HB", "Central": "CENTRAL", "Bellevue": "BELLEVUE", "Paradeplatz": "PARADEPL",
    "Rennweg": "RENNWEG", "Oerlikon, Bahnhof": "OERLIKON", "Stadelhofen, Bahnhof": "STADELH",
    "Flughafen, Fracht": "AIRPORT", "Stettbach, Bahnhof": "STETTBACH", "Schlieren, Geissweid": "SCHLIEREN",
    "Triemli": "TRIEMLI", "Altstetten, Bahnhof N": "ALTSTETTEN", "Klusplatz": "KLUSPL",
    "Rehalp": "REHALP", "Wollishoferplatz": "WOLLISHOFEN", "Tiefenbrunnen, Bahnhof": "TIEFENBR",
    "Hardturm": "HARDTURM", "Zoo": "ZOO", "Hirzenbach": "HIRZENBACH", "Albisgütli": "ALBISGUETLI",
    "Milchbuck": "MILCHBUCK", "Enge, Bahnhof": "ENGE", "Werdhölzli": "WERDHOELZLI",
    "Albisrieden": "ALBISRIEDEN", "Seebach": "SEEBACH", "Auzelg": "AUZELG", "Frankental": "FRANKENTAL",
}
HOME = "Rennweg"
CENTRE = (47.3745, 8.5395)               # the magnification is around HB / Paradeplatz / Central
# Hand adjustments: stop name -> (x, y) on the wall, pinned before the relaxation.
OVERRIDES = {}
MAGNIFY = 0.42                           # radial power: distance from the centre ** MAGNIFY (1 = true to scale)
MARGIN_X, MARGIN_Y = 8, 10  # wall edge kept clear for the terminus labels
RELAX_ITERS = 300
OCTILINEAR = 1.0                         # 1 = edges end up exactly on 0/45/90, less keeps the true geography
SPRING = 0.06                            # pull of each stop back to its magnified geographic place
STRAIGHTEN = 0.05                        # how hard a plain stop is pulled onto the line between its neighbours
MIN_GAP = 8.0                            # LEDs between stops while relaxing
LABEL_MAX_COST = 60


def project(lat, lon):
    """Kilometres east and south of CENTRE."""
    return ((lon - CENTRE[1]) * 111.32 * math.cos(math.radians(CENTRE[0])), (CENTRE[0] - lat) * 111.32)


def build_layout(data):
    """The wall schematic from the timetable: {w, h, stops [[x,y,name]], edges [{a,b,lines,pts}],
    labels [[x,y,text]], home}. Every consecutive stop pair of every pattern is one edge (undirected, with the
    set of lines that use it); every stop sits on a whole LED and every edge is a polyline of whole-LED
    corners with 0/45/90 degree segments (a straight run plus at most one 45 degree bend)."""
    import numpy as np
    names = [s[0] for s in data["stops"]]
    edges = {}
    for line, seq in data["patterns"]:
        for a, b in zip(seq, seq[1:]):
            if a != b:
                edges.setdefault((min(a, b), max(a, b)), set()).add(line)
    used = sorted({i for e in edges for i in e})
    ix = {s: k for k, s in enumerate(used)}                    # stop index -> row in the working arrays
    n = len(used)
    km = np.array([project(data["stops"][s][1], data["stops"][s][2]) for s in used], float)
    # 1. radial power compression around the centre: dense middle spread out, outskirts pulled in
    r = np.hypot(km[:, 0], km[:, 1])
    rmax = r.max()
    k = np.where(r > 1e-9, (rmax * (np.maximum(r, 1e-9) / rmax) ** MAGNIFY) / np.maximum(r, 1e-9), 1.0)
    pos = km * k[:, None]
    # 2. fit to the wall, each axis on its own (a schematic need not keep the aspect)
    lo, hi = pos.min(0), pos.max(0)
    box_lo, box_hi = np.array([MARGIN_X, MARGIN_Y], float), np.array([W - 1 - MARGIN_X, H - 1 - MARGIN_Y], float)
    pos = box_lo + (pos - lo) / (hi - lo) * (box_hi - box_lo)
    home0 = pos.copy()
    pinned = {}
    for name, xy in OVERRIDES.items():
        if name in names and names.index(name) in ix:
            pinned[ix[names.index(name)]] = np.array(xy, float)
            pos[ix[names.index(name)]] = xy
    E = np.array([(ix[a], ix[b]) for a, b in edges], int)
    degree = np.zeros(n, int)
    np.add.at(degree, E.ravel(), 1)
    deg2 = degree == 2
    # 3. relax: edges turn towards the nearest of the eight directions, stops keep apart and near home
    oct_dirs = np.array([(math.cos(i * math.pi / 4), math.sin(i * math.pi / 4)) for i in range(8)])
    for it in range(RELAX_ITERS):
        f = 1.0 - it / RELAX_ITERS
        move = np.zeros_like(pos)
        v = pos[E[:, 1]] - pos[E[:, 0]]
        ln = np.hypot(v[:, 0], v[:, 1]) + 1e-9
        best = oct_dirs[np.argmax(v @ oct_dirs.T / ln[:, None], axis=1)]
        d = (best * ln[:, None] - v) * 0.5 * OCTILINEAR * (0.25 + 0.75 * (1 - f))
        np.add.at(move, E[:, 0], -d)
        np.add.at(move, E[:, 1], d)
        move += (home0 - pos) * SPRING * (0.3 + 0.7 * f)
        nb = np.zeros_like(pos)                                 # a stop with two neighbours drifts to their midpoint
        np.add.at(nb, E[:, 0], pos[E[:, 1]])
        np.add.at(nb, E[:, 1], pos[E[:, 0]])
        move += np.where(deg2[:, None], nb / 2 - pos, 0.0) * STRAIGHTEN
        diff = pos[:, None, :] - pos[None, :, :]
        dist = np.hypot(diff[..., 0], diff[..., 1]) + np.eye(n) * 1e9
        close = dist < MIN_GAP
        push = np.where(close, (MIN_GAP - dist) / (dist * 2), 0.0)
        move += (diff * push[..., None]).sum(1) * 0.6
        pos += move
        for i, xy in pinned.items():
            pos[i] = xy
        pos[:, 0] = np.clip(pos[:, 0], MARGIN_X, W - 1 - MARGIN_X)
        pos[:, 1] = np.clip(pos[:, 1], MARGIN_Y, H - 1 - MARGIN_Y)
    px = np.rint(pos).astype(int)
    # whole LEDs: no two stops on one LED, and none right next to another
    for _ in range(40):
        moved = False
        for i in range(n):
            if i in pinned:
                continue
            for j in range(n):
                if j != i and max(abs(px[i, 0] - px[j, 0]), abs(px[i, 1] - px[j, 1])) < 2:
                    step = np.sign(pos[i] - pos[j]).astype(int)
                    if not step.any():
                        step = np.array([1, 0])
                    px[i] += step * 2
                    moved = True
        if not moved:
            break
    # 4. route every edge: a straight run and at most one 45 degree bend, bend placed to stay clear
    stop_at = {(int(x), int(y)): i for i, (x, y) in enumerate(px)}
    taken = {}                                                  # pixel -> number of edges through it
    routed = {}
    order = sorted(range(len(E)), key=lambda e: -np.abs(px[E[e, 1]] - px[E[e, 0]]).max())
    for e in order:
        a, b = [int(v) for v in px[E[e, 0]]], [int(v) for v in px[E[e, 1]]]
        dx, dy = int(b[0] - a[0]), int(b[1] - a[1])
        sx, sy, m = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0), min(abs(dx), abs(dy))
        cands = [[tuple(a), tuple(b)]]
        if dx and dy and abs(dx) != abs(dy):
            cands = [[tuple(a), (a[0] + sx * m, a[1] + sy * m), tuple(b)],
                     [tuple(a), (b[0] - sx * m, b[1] - sy * m), tuple(b)]]
        best, best_cost = None, None
        for c in cands:
            cost = 0.0
            for p in _pixels(c):
                if p in stop_at and p != tuple(a) and p != tuple(b):
                    cost += 50
                cost += 3 * taken.get(p, 0)
            if best_cost is None or cost < best_cost - 1e-9:
                best, best_cost = c, cost
        routed[e] = best
        for p in _pixels(best):
            taken[p] = taken.get(p, 0) + 1
    out_edges = []
    for e, ((a, b), lines) in enumerate(edges.items()):
        out_edges.append({"a": a, "b": b, "lines": sorted(lines, key=int),
                          "pts": [[int(x), int(y)] for x, y in routed[e]]})
    # the output keeps the timetable's stop numbering (a stop no line serves sits off the wall at -1, -1)
    out_stops = [[int(px[ix[i], 0]), int(px[ix[i], 1]), data["stops"][i][0]] if i in ix
                 else [-1, -1, data["stops"][i][0]] for i in range(len(data["stops"]))]
    labels = _place_labels(out_stops, out_edges)
    home = next(i for i, s in enumerate(out_stops) if s[2] == HOME)
    return {"w": W, "h": H, "stops": out_stops, "edges": out_edges, "labels": labels, "home": home}


def _pixels(pts):
    """Every whole LED on a polyline of 0/45/90 degree segments."""
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(abs(x1 - x0), abs(y1 - y0))
        sx, sy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
        out += [(x0 + sx * i, y0 + sy * i) for i in range(n + 1)]
    return out


def _place_labels(stops, edges):
    """Each LABELS word beside its stop, on whichever side crosses the fewest lines and other words and stays
    on the wall."""
    glyph_w = lambda t: max(0, 4 * len(t) - 1)
    busy = {}
    for ed in edges:
        for p in _pixels([tuple(q) for q in ed["pts"]]):
            busy[p] = busy.get(p, 0) + 1
    dots = {(s[0], s[1]) for s in stops}
    placed, out = [], []
    wanted = [(i, LABELS[s[2]]) for i, s in enumerate(stops) if s[2] in LABELS]
    wanted.sort(key=lambda t: -len(t[1]))
    for i, text in wanted:
        x, y = stops[i][0], stops[i][1]
        w = glyph_w(text)
        cands = [(x + 3, y - 2), (x - 2 - w, y - 2), (x - w // 2, y - 8), (x - w // 2, y + 4),
                 (x + 3, y - 7), (x + 3, y + 3), (x - 2 - w, y - 7), (x - 2 - w, y + 3),
                 (x + 2, y - 10), (x - 1 - w, y - 10), (x + 2, y + 6), (x - 1 - w, y + 6),
                 (x + 6, y - 2), (x - 5 - w, y - 2), (x + 5, y - 6), (x - 4 - w, y + 2),
                 (x - w // 2, y - 12), (x - w // 2, y + 8)]
        best, best_cost = None, None
        for k, (tx, ty) in enumerate(cands):
            if tx < 1 or ty < 1 or tx + w > W - 1 or ty + 5 > H - 1:
                continue
            cost = k * 0.5
            for xx in range(tx - 1, tx + w + 1):
                for yy in range(ty - 1, ty + 6):
                    cost += 1.0 * busy.get((xx, yy), 0) + (4 if (xx, yy) in dots else 0)
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
