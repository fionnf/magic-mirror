"""Build the data for display/storks.py: recorded white stork tracks (assets/migrations/storks.json) and a
coarse Europe-Africa coastline (assets/migrations/storks_map.json). Run on the laptop; the results are committed,
so the wall needs no internet for them.

    python3 tools/build_storks.py            tracks, then the map          (--fresh: ignore the downloads in /tmp)
    python3 tools/build_storks.py tracks
    python3 tools/build_storks.py map
    python3 tools/build_storks.py movebank STUDY_ID [ID ...]    one Movebank study through the public JSON service

Where the tracks come from (all CC0 1.0, Movebank Data Repository, www.datarepository.movebank.org, reached
through its open DSpace API; the cache of the zip files lives in the temp directory):
  * Flack A, Fiedler W, Blas J, Pokrovski I, Kaatz M, Mitropolsky M, Aghababyan K, Fakriadis Y, Makrigianni E,
    Jerzak L, Shamin M, Shamina C, Azafzaf H, Wikelski M. 2015. Data from: Migration costs of eight Eurasian white
    stork populations. doi:10.5441/001/1.78152p3q  (item 72aef22c..., 72 juveniles tagged in 2013: Lake Constance,
    Poland, Russia, Greece and others; we use those four places)
  * Fiedler W, Niederer W, Schoenenberger A, Flack A, Wikelski M. 2024. Data from: Study "LifeTrack White Stork
    Vorarlberg" (2016-2023). doi:10.5441/001/1.71r7pp6q_2  (item 6d60b346..., 27 storks from the Rhine valley at
    Lustenau, Hoechst and the Rheindelta, on the Swiss border at St. Margrethen)
  * Fiedler W, Flack A, Schaefle W, Keeves B, Quetting M, Eid B, Schmid H, Wikelski M. 2024. Data from: Study
    "LifeTrack White Stork SW Germany" (2013-2023). doi:10.5441/001/1.ck04mn78_2  (Lake Constance, Upper Rhine)
  * Fiedler W, Flack A, Schmid H, Reinhard U, Wikelski M. 2024. Data from: Study "LifeTrack White Stork
    Oberschwaben" (2014-2023). doi:10.5441/001/1.c42j3js7_2  (Upper Swabia, north of Lake Constance)

What the wall shows is therefore real, but not all Swiss: the western birds were tagged as nestlings between 46 and
49 N and 5 and 11 E (Lake Constance, the Upper Rhine, Upper Swabia, and the Rhine valley of Vorarlberg, which lies
on the Swiss border), the eastern ones in Poland, Russia and Greece (the eastern flyway). No bird in these open
data was tagged in a Swiss nest, and the piece says so.

How it is thinned: the fix nearest 12:00 UTC each day (between 09:00 and 15:00 UTC), outliers and hidden fixes
dropped; one stork-year per bird, 1 July to 30 June, chosen where the bird is best covered; days on which the bird
barely moved are dropped (at most 4 days are left out in a row); positions to 0.1 degree (11 km, a third of an LED).
A stork-year is kept only if the tag recorded at least 60 days of it.

The Movebank public JSON service (www.movebank.org/movebank/service/public/json?study_id=..&sensor_type=gps...)
answers only for studies whose owners made them public; `movebank STUDY_ID` reads such a study (see
parse_json_individuals, tested on a synthetic sample in tests/test_storks.py).
"""
import csv
import datetime
import io
import json
import math
import os
import random
import re
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

OUT = os.path.join(HERE, "assets", "migrations", "storks.json")
MAP_OUT = os.path.join(HERE, "assets", "migrations", "storks_map.json")
REPO = "https://datarepository.movebank.org/server/api/core/"
UA = {"User-Agent": "fortuna-wall/1.0 (private art project)"}

# Movebank Data Repository items (DSpace uuid) and the data files we read from them. `fallback` is the file's
# bitstream id as it was when this was written, tried only when the item listing cannot be read.
SOURCES = [
    {"key": "flack2015", "item": "72aef22c-54fa-4938-a433-5cf4a5cef3e8", "pattern": r"-gps\.csv\.zip$",
     "fallback": ["4872f56d-b7dc-437d-8956-fcdd7f81615e"],
     "cite": "Flack et al. 2015, Data from: Migration costs of eight Eurasian white stork populations, "
             "Movebank Data Repository, doi:10.5441/001/1.78152p3q (CC0 1.0)"},
    {"key": "vorarlberg", "item": "6d60b346-369c-46be-b976-d793b61fa076", "pattern": r"-gps-\dof\d\.csv\.zip$",
     "fallback": ["71df2c72-94a6-44ad-8dd6-4a6cbeb98af0", "16ebabe3-54a3-402f-9fb4-69ba69b5b399"],
     "cite": "Fiedler, Niederer, Schoenenberger, Flack & Wikelski 2024, Data from: Study 'LifeTrack White Stork "
             "Vorarlberg' (2016-2023), Movebank Data Repository, doi:10.5441/001/1.71r7pp6q_2 (CC0 1.0)"},
    {"key": "swgermany", "item": "5f8c5199-c2b0-4e48-9521-8c5d5f6b115c", "pattern": r"-gps\.csv\.zip$",
     "fallback": ["c5d28936-51ce-455c-8827-a0a8027501d8"],
     "cite": "Fiedler, Flack, Schaefle, Keeves, Quetting, Eid, Schmid & Wikelski 2024, Data from: Study 'LifeTrack White "
             "Stork SW Germany' (2013-2023), Movebank Data Repository, doi:10.5441/001/1.ck04mn78_2 (CC0 1.0)"},
    {"key": "oberschwaben", "item": "86008da5-779d-4d96-ac83-66652b552402", "pattern": r"-gps\.csv\.zip$",
     "fallback": ["5993caae-5745-49d9-875f-90cfa861f34f"],
     "cite": "Fiedler, Flack, Schmid, Reinhard & Wikelski 2024, Data from: Study 'LifeTrack White Stork Oberschwaben' "
             "(2014-2023), Movebank Data Repository, doi:10.5441/001/1.c42j3js7_2 (CC0 1.0)"},
]

WINDOW_FROM, WINDOW_TO = 9, 15          # hours (UTC) a fix may come from; the one nearest 12:00 is kept
MIN_DAYS = 60                           # recorded days needed in a stork-year
MAX_SKIP = 4                            # stationary days left out in a row
MIN_STEP_KM = 25.0                      # a fix nearer than this to the last kept one is left out (if nothing is lost)
FULL_YEAR = 330                         # span of days that counts as a whole year


# ---- reading Movebank data --------------------------------------------------------------------------------

_ORD = {}


def day_ordinal(stamp):
    """'2013-07-15 09:15:17.000' -> (date ordinal, seconds into the day)."""
    k = stamp[:10]
    o = _ORD.get(k)
    if o is None:
        o = _ORD[k] = datetime.date(int(k[:4]), int(k[5:7]), int(k[8:10])).toordinal()
    return o, int(stamp[11:13]) * 3600 + int(stamp[14:16]) * 60 + int(stamp[17:19])


def _num(s):
    try:
        return float(s)
    except ValueError:
        return None


def iter_events(lines):
    """Movebank event CSV (the 'gps' export of a study) -> (individual, date ordinal, second of day, lat, lon).

    Skips fixes without coordinates ('NA' or empty), fixes marked not visible, and fixes flagged as outliers by
    an algorithm or by hand. Blank lines (the data repository's files have one after every row) are ignored."""
    rd = csv.reader(lines)
    head = next(rd)
    ix = {k: i for i, k in enumerate(head)}
    it, ila, ilo = ix["timestamp"], ix["location-lat"], ix["location-long"]
    iid = ix.get("individual-local-identifier", ix.get("tag-local-identifier"))
    ivis, ialg, iman = ix.get("visible"), ix.get("algorithm-marked-outlier"), ix.get("manually-marked-outlier")
    top = max(i for i in (it, ila, ilo, iid) if i is not None)
    for r in rd:
        if len(r) <= top:
            continue
        if ivis is not None and r[ivis].strip().lower() == "false":
            continue
        if (ialg is not None and r[ialg].strip().lower() == "true") or (iman is not None and r[iman].strip().lower() == "true"):
            continue
        lat, lon = _num(r[ila]), _num(r[ilo])
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0) or len(r[it]) < 19:
            continue
        o, s = day_ordinal(r[it])
        yield r[iid], o, s, lat, lon


def parse_json_individuals(obj):
    """The Movebank public JSON service ({"individuals": [{"individual_local_identifier": ..., "locations":
    [{"timestamp": ms since 1970, "location_long": .., "location_lat": ..}]}]}) -> the same tuples as iter_events."""
    for ind in obj.get("individuals", []):
        name = str(ind.get("individual_local_identifier") or ind.get("individual_id"))
        for loc in ind.get("locations", []):
            lat, lon, ts = loc.get("location_lat"), loc.get("location_long"), loc.get("timestamp")
            if lat is None or lon is None or ts is None or (lat == 0 and lon == 0):
                continue
            sec = int(ts // 1000)
            yield name, datetime.date(1970, 1, 1).toordinal() + sec // 86400, sec % 86400, float(lat), float(lon)


def daily_fixes(events):
    """-> {individual: {date ordinal: (lat, lon)}}: per day the fix nearest 12:00 UTC, within WINDOW_FROM..TO."""
    best = {}
    for name, o, s, lat, lon in events:
        h = s // 3600
        if h < WINDOW_FROM or h > WINDOW_TO:
            continue
        d = best.setdefault(name, {})
        score = abs(s - 43200)
        cur = d.get(o)
        if cur is None or score < cur[0]:
            d[o] = (score, lat, lon)
    return {n: {o: (v[1], v[2]) for o, v in d.items()} for n, d in best.items()}


# ---- choosing a stork-year -------------------------------------------------------------------------------

def hav(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 12742.0 * math.asin(min(1.0, math.sqrt(x)))


def year_window(days, year):
    """The fixes of 1 July `year` .. 30 June year+1 as {day offset 0..364: (lat, lon)}."""
    start = datetime.date(year, 7, 1).toordinal()
    return {o - start: p for o, p in days.items() if 0 <= o - start < 365}


def cycles(days, home):
    """Every stork-year with enough recorded days: [{year, w, span, near, back}] where span is the days from first
    to last fix, near says the bird was at home (within 250 km of its nest) in the first 25 days of July, and
    back says it was home again (within 300 km) at the end of June."""
    ys = sorted({datetime.date.fromordinal(o).year for o in days})
    out = []
    for y in range(ys[0] - 1, ys[-1] + 1):
        w = year_window(days, y)
        if len(w) >= MIN_DAYS:
            ks = sorted(w)
            out.append({"year": y, "w": w, "span": ks[-1] - ks[0],
                        "near": any(k <= 25 and hav(w[k], home) < 250 for k in ks),
                        "back": ks[-1] >= 330 and hav(w[ks[-1]], home) < 300})
    return out


def best_cycle(cyc, rng):
    """The most telling stork-year: at home in July, whole year recorded, back home again; ties at random."""
    key = lambda c: (c["near"], c["span"] >= FULL_YEAR, c["back"], min(c["span"], 364) // 30)
    top = max(map(key, cyc))
    return rng.choice([c for c in cyc if key(c) == top])


def winter_spot(w):
    """Median position over 1 Dec .. 31 Jan (day offsets 153..214) or None."""
    pts = [p for k, p in w.items() if 153 <= k <= 214]
    if len(pts) < 5:
        return None
    la = sorted(p[0] for p in pts)
    lo = sorted(p[1] for p in pts)
    return la[len(la) // 2], lo[len(lo) // 2]


def in_iberia(p):
    """Wintering in Spain or Portugal: north of the Strait of Gibraltar's coast, west of the Pyrenees' end."""
    return p is not None and p[0] >= 36.2 and -10.0 <= p[1] <= 4.5


def classify(w, home):
    """'E' eastern flyway (tagged east of 12 E; it crossed 42 N southward), 'W' wintered in or reached Africa by the
    western route (or the central Mediterranean), 'S' wintered in Spain/Portugal, 'R' stayed north of 43 N all winter.
    None when the stork-year says nothing (it never went anywhere, or it stopped before it could)."""
    south = min(p[0] for p in w.values())
    if home[1] > 12.0:
        return "E" if south < 42.0 else None
    win = winter_spot(w)
    if win is None:
        return "W" if south < 36.2 else None
    if in_iberia(win):
        return "S"
    return "R" if win[0] >= 43.0 else "W"


def thin(w):
    """One fix a day -> the fixes worth keeping: [(day, lat, lon)], stationary days left out (MAX_SKIP in a row)."""
    ks = sorted(w)
    keep = [ks[0]]
    for i in range(1, len(ks) - 1):
        k = ks[i]
        last = keep[-1]
        if hav(w[last], w[k]) > MIN_STEP_KM or k - last > MAX_SKIP or ks[i + 1] - k > 1 or k - ks[i - 1] > 1:
            keep.append(k)
    if len(ks) > 1:
        keep.append(ks[-1])
    return [(k, round(w[k][0], 1), round(w[k][1], 1)) for k in keep]


def pick(birds, caps, rng):
    """birds: [{cls, span, ...}]. A few of each class: whole years first, at most a quarter part years."""
    chosen = []
    for cls, cap in caps.items():
        pool = [b for b in birds if b["cls"] == cls]
        rng.shuffle(pool)
        whole = [b for b in pool if b["span"] >= FULL_YEAR]
        part = [b for b in pool if b["span"] < FULL_YEAR]
        n_part = min(len(part), max(cap // 4, cap - len(whole)))
        chosen += whole[:cap - n_part] + part[:n_part]
    return chosen


# ---- download -----------------------------------------------------------------------------------------

def download(url, name):
    cache = os.path.join(tempfile.gettempdir(), "fortuna_storks_" + name)
    if not os.path.exists(cache) or "--fresh" in sys.argv:
        print("downloading", name, flush=True)
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r, open(cache + ".part", "wb") as fh:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                fh.write(b)
        os.replace(cache + ".part", cache)
    return cache


def source_files(src):
    """[(name, local zip path)] for the data files of a source (item listing first, known ids if that fails)."""
    ids = []
    try:
        def get(u):
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r:
                return json.load(r)
        for bun in get(REPO + "items/" + src["item"] + "/bundles")["_embedded"]["bundles"]:
            if bun["name"] != "ORIGINAL":
                continue
            for b in get(bun["_links"]["bitstreams"]["href"] + "?size=100")["_embedded"]["bitstreams"]:
                if re.search(src["pattern"], b["name"]):
                    ids.append((b["name"], b["uuid"]))
    except Exception as e:
        print("item listing failed (%s), using the known file ids" % str(e)[:80], flush=True)
    if not ids:
        ids = [(src["key"] + str(i), u) for i, u in enumerate(src["fallback"])]
    return [(n, download(REPO + "bitstreams/" + u + "/content", u + ".zip")) for n, u in ids]


def zip_events(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv") and "__MACOSX" not in n]
        with z.open(names[0]) as raw:
            yield from iter_events(io.TextIOWrapper(raw, encoding="utf-8", newline=""))


# ---- build ----------------------------------------------------------------------------------------------

def origin(first):
    """Where a stork was tagged: 'W' the Lake Constance / Rhine valley area, 'E' Poland, Russia or Greece, else None
    (the Spanish, Tunisian, Armenian, Uzbek and South African tags of the same data package are not shown)."""
    la, lo = first
    if 46.0 <= la <= 49.0 and 5.0 <= lo <= 11.0:
        return "W"
    if (50.0 < la < 56.5 and 12.0 < lo < 40.0) or (39.5 < la < 42.0 and 22.0 < lo < 30.0):
        return "E"
    return None


def bird_key(ind):
    """The same stork is in several studies under one name; its ring number (DER AL582) is the same in all."""
    m = re.search(r"\b(DER|GRA|PLG)\s?([A-Z0-9]{4,6})\b", ind)
    return (m.group(1) + m.group(2)) if m else ind


def cached_daily(path):
    """daily_fixes of a downloaded zip, remembered next to it (reading a few GB of CSV takes minutes)."""
    import pickle
    pk = path + ".daily.pkl"
    if os.path.exists(pk) and "--fresh" not in sys.argv:
        with open(pk, "rb") as fh:
            return pickle.load(fh)
    d = daily_fixes(zip_events(path))
    with open(pk, "wb") as fh:
        pickle.dump(d, fh)
    return d


def tracks(caps=None, seed=2013):
    caps = caps or {"W": 26, "S": 8, "R": 3, "E": 18}
    rng = random.Random(seed)
    merged, where = {}, {}
    for src in SOURCES:
        for name, path in source_files(src):                   # a bird can run across several files, and across studies
            for ind, days in cached_daily(path).items():
                k = bird_key(ind)
                merged.setdefault(k, {}).update(days)
                where.setdefault(k, (src["key"], ind))
    cands = []
    for k, days in merged.items():
        key, ind = where[k]
        if len(days) < MIN_DAYS:
            continue
        first = days[min(days)]                                    # the nest, near enough
        if origin(first) is None:
            continue
        cyc = cycles(days, first)
        if not cyc:
            continue
        c = best_cycle(cyc, rng)
        cls = classify(c["w"], first)
        if cls is None:
            continue
        cands.append({"id": f"{key}:{ind}", "year": c["year"], "cls": cls, "span": c["span"], "fixes": thin(c["w"])})
    chosen = pick(cands, caps, rng)
    chosen.sort(key=lambda b: ("WSRE".index(b["cls"]), b["id"]))
    birds = [{"id": b["id"], "cls": b["cls"], "year": b["year"],
              "d": [f[0] for f in b["fixes"]], "lat": [f[1] for f in b["fixes"]], "lon": [f[2] for f in b["fixes"]]}
             for b in chosen]
    data = {
        "kind": "recorded",
        "cycle": "each bird shows one year of its recorded life, 1 July to 30 June (d = days from 1 July of `year`)",
        "birds": birds,
        "source": [s["cite"] for s in SOURCES],
        "licence": "CC0 1.0 (public domain dedication), as stated in the README of each data package",
        "thinning": f"one fix a day (nearest 12:00 UTC); stationary days dropped; positions to 0.1 deg; {MIN_DAYS}+ recorded days per stork-year",
        "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    }
    with open(OUT, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    n = sum(len(b["d"]) for b in birds)
    cnt = {c: sum(1 for b in birds if b["cls"] == c) for c in "WSRE"}
    print(f"{len(birds)} storks {cnt}, {n} fixes, {os.path.getsize(OUT) / 1000:.0f} kB -> {OUT}")
    return data


def movebank(study_id, individuals, out=OUT):
    """Read one study that is public on Movebank (the JSON service) and write it in the same shape, to
    storks.json. Only for studies whose owners made the data public; most need a login."""
    url = "https://www.movebank.org/movebank/service/public/json?study_id=%s&sensor_type=gps" % study_id
    if individuals:
        url += "&individual_local_identifiers=" + ",".join(urllib.request.quote(i) for i in individuals)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        obj = json.load(r)
    got = daily_fixes(parse_json_individuals(obj))
    birds = []
    for ind, days in sorted(got.items()):
        if len(days) < MIN_DAYS:
            continue
        first = days[min(days)]
        cyc = cycles(days, first)
        if not cyc:
            continue
        c = best_cycle(cyc, random.Random(1))
        kept = thin(c["w"])
        birds.append({"id": f"movebank:{study_id}:{ind}", "cls": classify(c["w"], first) or "W", "year": c["year"],
                      "d": [f[0] for f in kept], "lat": [f[1] for f in kept], "lon": [f[2] for f in kept]})
    data = {"kind": "recorded", "birds": birds, "source": [f"Movebank study {study_id} (public JSON service)"],
            "licence": "see the study's licence on movebank.org", "built": datetime.date.today().isoformat()}
    with open(out, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"{len(birds)} storks -> {out}")


# ---- the coastline ------------------------------------------------------------------------------------

BOX = (-38.0, 66.0, -28.0, 62.0)        # lat min, lat max, lon min, lon max (with a margin round the wall)
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"


def clip_runs(ring, box, margin=4.0):
    """Cut a ring into the runs that lie inside the box (with a margin), each with its first outside neighbour,
    so a huge continent outline becomes just the coast that can be seen."""
    la0, la1, lo0, lo1 = box
    inside = [la0 - margin <= p[0] <= la1 + margin and lo0 - margin <= p[1] <= lo1 + margin for p in ring]
    runs, cur = [], []
    for i, p in enumerate(ring):
        if inside[i]:
            if not cur and i > 0:
                cur.append(ring[i - 1])
            cur.append(p)
        else:
            if cur:
                cur.append(p)
                runs.append(cur)
                cur = []
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) >= 2]


def build_map():
    from build_maps import natural_earth, simplify, _rings
    land = natural_earth("ne_50m_land")
    lakes = natural_earth("ne_50m_lakes")
    coast, big_lakes = [], []
    for f in land:
        for ring in _rings(f["geometry"]):
            for run in clip_runs(ring, BOX):
                s = simplify(run, 6.0)
                if len(s) >= 2:
                    coast.append(s)
    for f in lakes:
        if (f["properties"].get("scalerank") or 9) > 1:
            continue
        for ring in _rings(f["geometry"]):
            la0, la1, lo0, lo1 = BOX
            if all(la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1 for p in ring):
                s = simplify(ring, 6.0)
                if len(s) >= 4:
                    big_lakes.append(s)
    ch = []
    try:
        with open(os.path.join(HERE, "assets", "maps", "switzerland.json")) as fh:
            m = json.load(fh)
        for line in m.get("border", []):
            ch.append(simplify(line, 6.0))
    except Exception:
        pass
    r2 = lambda lines: [[[round(p[0], 2), round(p[1], 2)] for p in l] for l in lines]
    data = {"coast": r2(coast), "lakes": r2(big_lakes), "ch": r2(ch),
            "source": "Natural Earth 1:50m land and lakes (public domain), simplified to 6 km; Switzerland's border from assets/maps/switzerland.json"}
    with open(MAP_OUT, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"{len(coast)} coast lines {sum(map(len, coast))} points, {len(big_lakes)} lakes, {os.path.getsize(MAP_OUT) / 1000:.0f} kB -> {MAP_OUT}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    what = args[0] if args else "all"
    if what == "movebank":
        movebank(args[1], args[2:])
        return
    if what in ("all", "tracks"):
        tracks()
    if what in ("all", "map"):
        build_map()


if __name__ == "__main__":
    main()
