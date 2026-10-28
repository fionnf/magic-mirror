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


def project(lat, lon):
    """Kilometres east and south of CENTRE."""
    return ((lon - CENTRE[1]) * 111.32 * math.cos(math.radians(CENTRE[0])), (CENTRE[0] - lat) * 111.32)


def build_layout(data):
    raise NotImplementedError


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
