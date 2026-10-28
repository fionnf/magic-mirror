"""Build the data behind the night-train atlas (display/nighttrains.py). Run on the laptop; the results are
committed, so the wall needs no internet for them.

    python3 tools/build_nighttrains.py trains   -> assets/nighttrains/services.json  (the timetables)
    python3 tools/build_nighttrains.py land     -> assets/nighttrains/europe.json    (the coastline)
    python3 tools/build_nighttrains.py check    -> sanity-check services.json (speeds, times, coverage)

trains: the lines and their timetables come from the Open Night Train Database of Back-on-Track.eu
(https://back-on-track.eu/night-train-database/, read on 2026-10-28; their page for each line gives the stops
with local times and the weekdays it runs, for each direction). Every line in that database is taken, whatever
the operator (Nightjet, European Sleeper, Caledonian Sleeper, GWR, SJ, Snalltaget, Vy, VR, FS, SNCF, PKP, CFR,
BDZ, Ukrzaliznytsia ...), except the few lines that lie wholly east of the picture (eastern Turkey). It is a
secondary source: the timetable facts are re-keyed into a compact table and must be checked against the operators
before anyone relies on them (the page says so itself). Times are local at each stop, as printed.

Stops carry no coordinates in that database, so each station name is matched to a place in GeoNames
(cities1000, CC BY 4.0, https://www.geonames.org) - the place with the most people of that name in the
countries the line runs through. A match that would make the train go faster than 200 km/h between two stops
is dropped, and stops that cannot be matched (small villages) are skipped: a line is then drawn as straight
arcs between the stops that remain, which is all the wall needs. Run `check` after editing.

land: Natural Earth 1:50m coastline (public domain), clipped to Europe and simplified to ~3 km.

The JSON, so it is easy to edit by hand:
  services.json  {"source", "compiled", "cities": [[name, lat, lon, thousand inhabitants], ...],
                  "services": [{"name": "NJ 470", "op": "OBB", "route": "Zurich - Hamburg", "days": "1111111",
                                "stops": [[lat, lon, tz, arrive, depart], ...]}, ...]}
  days   Mo..Su: the weekdays (at the first stop) on which the train sets out
  tz     the stop's standard time in hours from UTC (0 UK/Ireland, 1 central, 2 eastern; the EU's summer time
         rule is added at run time); 3 = Turkey / Belarus (UTC+3 all year)
  arrive, depart   local minutes since midnight of the day the train sets out (1500 = 01:00 next day)
"""
import json
import math
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets", "nighttrains")
CACHE = os.path.join(tempfile.gettempdir(), "fortuna_nighttrains")
UA = {"User-Agent": "fortuna-wall/1.0 (private art project, reads each page once)"}
BOT = "https://back-on-track.eu/night-train-database/"
GEONAMES = "https://download.geonames.org/export/dump/cities1000.zip"
NE_COAST = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_coastline.geojson"
COMPILED = "2026-10-28"
MAX_LON = 37.0                       # lines with a stop east of this are off the picture
MAX_KMH = 200.0

TZ = {}
for z in ("Europe/London", "Europe/Dublin", "Europe/Lisbon", "Atlantic/Reykjavik"):
    TZ[z] = 0
for z in ("Zurich Berlin Paris Vienna Prague Budapest Rome Stockholm Oslo Copenhagen Amsterdam Brussels Warsaw "
          "Belgrade Zagreb Ljubljana Bratislava Podgorica Skopje Sarajevo Tirane Luxembourg Vaduz Madrid Andorra "
          "Monaco San_Marino Vatican Malta Busingen").split():
    TZ["Europe/" + z] = 1
for z in ("Bucharest Sofia Athens Helsinki Kyiv Kiev Uzhgorod Zaporozhye Chisinau Vilnius Riga Tallinn Mariehamn "
          "Nicosia").split():
    TZ["Europe/" + z] = 2
for z in ("Istanbul", "Minsk", "Moscow"):
    TZ["Europe/" + z] = 3


def get(url, name, binary=False, pause=1.0):
    """Download once into the temp dir (delete it to fetch again)."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        for k in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                    data = r.read()
                break
            except Exception as e:
                print("retry", url, str(e)[:60], flush=True)
                time.sleep(5 * (k + 1))
        else:
            raise SystemExit("cannot fetch " + url)
        with open(path, "wb") as fh:
            fh.write(data)
        time.sleep(pause)
    with open(path, "rb") as fh:
        data = fh.read()
    return data if binary else data.decode("utf8")


# ------------------------------------------------------------------ the database ---

def lines():
    """[{routeid, nighttrain, itinerary, countries, operators}, ...] from the database page's table."""
    page = get(BOT, "db_page.html", pause=0)
    m = re.search(r'data_request_url":"([^"]*)"', page)
    url = m.group(1).replace("\\u0026", "&").replace("\\/", "/")
    rows = json.loads(get(url, "db_table.json", pause=0))
    return [r for r in rows if str(r["routeid"]).isdigit()]


def parse_route(rid):
    """[{num, days, stops: [(name, [times])]}, ...] - one entry a direction - from a line's page."""
    import html
    s = get(BOT + "?route_id=" + rid, f"route_{rid}.html")
    i, j = s.find('class="row itinerary"'), s.find('class="row traininfo"')
    out = []
    for el in re.split(r'<div class="row itinerary-element">', s[i:j])[1:]:
        h3 = re.search(r'<h3 class="[^"]*">(.*?)</h3>', el, re.S)
        stops = []
        for _, body in re.findall(r'<li aria-label="([^"]*)">(.*?)</li>', el, re.S):
            parts = [html.unescape(p).strip() for p in re.split(r"<br\s*/?>", re.sub(r"</?b>", "", body))]
            stops.append((parts[0], re.findall(r"\d\d:\d\d", " ".join(parts[1:]))))
        days = re.findall(r'<div class="(\w*)"><div aria-hidden="true">(?:Mo|Tu|We|Th|Fr|Sa|Su)</div>', el)
        dur = re.search(r"Trip duration (\d+):(\d+)", el)
        out.append({"num": html.unescape(re.sub(r"<[^>]+>", "", h3.group(1))).strip() if h3 else "",
                    "days": "".join("1" if d == "yes" else "0" for d in days) if len(days) == 7 else "1111111",
                    "dur": int(dur.group(1)) * 60 + int(dur.group(2)) if dur else None, "stops": stops})
    return out


# ------------------------------------------------------------------ places ---

def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    for a, b in (("ß", "ss"), ("ł", "l"), ("ø", "o"), ("đ", "d"), ("æ", "ae")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


STOP_WORDS = set("hbf hb hauptbahnhof bf bad station stn sbb centraal central centrale centrala nord sud sever north "
                 "south east west gara glavna glowny glowna dworzec zahodni zapad zapadni wschod zachod pn pd dolny "
                 "horny hl n zst zastavka zsr gl main nuova porta garibaldi termini tiburtina rogoredo principe "
                 "piazza santa lucia maria novella campo marte smn airport flughafen lotnisko port".split())


def candidates(name):
    """The spellings to try for a station name, most specific first: 'Frankfurt (Oder) Hbf' -> 'frankfurt oder'."""
    plain = norm(re.sub(r"[()]", " ", name))
    bare = [t for t in norm(re.sub(r"\(.*?\)", " ", name)).split() if t not in STOP_WORDS]
    kept = [t for t in plain.split() if t not in STOP_WORDS]
    out = []
    for c in (plain, " ".join(kept), " ".join(bare), " ".join(bare[:2]) if len(bare) > 2 else "",
              bare[0] if len(bare) > 1 else ""):
        if c and c not in out:
            out.append(c)
    return out


def places():
    """name key -> [(population, lat, lon, country, timezone, name)] from GeoNames cities1000."""
    z = zipfile.ZipFile(__import__("io").BytesIO(get(GEONAMES, "cities1000.zip", binary=True, pause=0)))
    g = defaultdict(list)
    for ln in z.read("cities1000.txt").decode("utf8").splitlines():
        f = ln.split("\t")
        rec = (int(f[14] or 0), float(f[4]), float(f[5]), f[8], f[17], f[1])
        for n in {norm(f[1]), norm(f[2])} | {norm(a) for a in f[3].split(",") if a}:
            if n:
                g[n].append(rec)
    return g


def find(g, name, countries):
    """The most populous place that goes by this station's name, in the line's countries first, then anywhere."""
    for scope in (countries, None):
        for c in candidates(name):
            recs = [r for r in g.get(c, []) if (r[3] in scope if scope else 34.0 < r[1] < 72.0 and -12.0 < r[2] < 45.0)]
            if recs:
                return max(recs)
    return None


def tz_code(rec):
    z = TZ.get(rec[4])
    if z is None:
        z = 1 if rec[2] < 19 else 2
        print("  unknown timezone", rec[4], rec[5], "->", z)
    return z


def km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 6371.0 * math.acos(max(-1.0, min(1.0, c)))


# ------------------------------------------------------------------ one direction ---

def direction(g, countries, e, label):
    """The compact stop list of one direction, or None. Each stop: [lat, lon, tz, arrive, depart].

    The source lists are not always clean (two sections of a train glued together, a typo in a time, a station
    name that matches the wrong place), so the stops that cannot be one journey are left out: the kept stops are
    the longest run of them in which every leg is a plausible speed (6-200 km/h) at the clock times given."""
    rows = []                                              # [place, tz, arrive, depart, name], times in wall minutes
    for name, times in e["stops"]:
        rec = find(g, name, countries)
        if rec is None:
            continue
        t = [int(x[:2]) * 60 + int(x[3:]) for x in times]
        rows.append([rec, tz_code(rec), t[0] if t else None, t[-1] if t else None, name])
    pos = lambda r: r[0][1:3]
    # a place met twice, not one after the other (the lists of two sections joined): the later one counts
    rows = [r for i, r in enumerate(rows)
            if not any(km(pos(r), pos(q)) < 8.0 for q in rows[i + 2:])]
    merged = []                                            # Basel SBB + Basel Bad Bf: arrive at the first, leave from the last
    for r in rows:
        if merged and km(pos(merged[-1]), pos(r)) < 4.0:
            m = merged[-1]
            m[3] = r[3] if r[3] is not None else m[3]
            m[2] = m[2] if m[2] is not None else r[2]
            continue
        merged.append(list(r))
    rows = merged
    u = lambda r, k: r[k] - 60 * r[1]                     # standard-time UTC, minutes in the day
    timed = [i for i, r in enumerate(rows) if r[2] is not None and r[3] is not None]
    if len(timed) < 2:
        return None

    def wrap(a, b):                                        # minutes from a to b on the clock, a slip of <15 min back = 0
        d = (b - a) % 1440
        return 0 if d > 1440 - 15 else d

    def ok(p, q):
        d = km(pos(rows[p]), pos(rows[q]))
        dt = wrap(u(rows[p], 3), u(rows[q], 2))
        if d <= 12.0:
            return dt <= 600
        return dt > 0 and 6.0 <= d / (dt / 60.0) <= MAX_KMH

    best = {}                                              # index -> (score, previous index)
    for n, j in enumerate(timed):
        w = 5.0 if n in (0, len(timed) - 1) else 1.0
        best[j] = (w, None)
        for i in timed[:n]:
            if ok(i, j) and best[i][0] + w > best[j][0]:
                best[j] = (best[i][0] + w, i)
    end = max(timed, key=lambda j: best[j][0])
    chain = []
    while end is not None:
        chain.append(end)
        end = best[end][1]
    chain.reverse()
    for j in timed:
        if j not in chain:
            print(f"  {label}: left out {rows[j][4]!r}")
    if len(chain) < 2:
        return None
    # the stops with no time that lie between the kept ones and near the line they make
    keep = list(range(chain[0], chain[-1] + 1))
    out = []
    for i in keep:
        if i in chain:
            out.append((i, True))
            continue
        a = max(c for c in chain if c < i)
        b = min(c for c in chain if c > i)
        if rows[i][2] is None and km(pos(rows[a]), pos(rows[i])) + km(pos(rows[i]), pos(rows[b])) \
                < 1.35 * km(pos(rows[a]), pos(rows[b])) + 40.0:
            out.append((i, False))
    # absolute times (standard UTC minutes): each leg takes the clock's difference, a stop's wait likewise
    U = {}
    prev = None
    for i, timed_stop in out:
        if not timed_stop:
            continue
        r = rows[i]
        arr = u(r, 2) if prev is None else U[prev][1] + wrap(u(rows[prev], 3), u(r, 2))
        dep = arr + (wrap(u(r, 2), u(r, 3)) if wrap(u(r, 2), u(r, 3)) <= 600 else 0)
        U[i] = (arr, dep)
        prev = i
    legs = [(U[b][0] - U[a][1], a, b) for a, b in zip(chain, chain[1:])]
    naive = lambda: (U[chain[-1]][0] + 60 * rows[chain[-1]][1]) - (U[chain[0]][1] + 60 * rows[chain[0]][1])
    if e["dur"]:
        extra = e["dur"] - naive()
        k = round(extra / 1440.0)
        if k >= 1 and abs(extra - 1440.0 * k) <= 90:       # the page counts whole days a sparse list cannot show
            leg = max(legs)
            for i in chain:
                if i >= leg[2]:
                    U[i] = (U[i][0] + 1440 * k, U[i][1] + 1440 * k)
        if abs(e["dur"] - naive()) > 90:
            print(f"  note: {label} lasts {e['dur']} min on the page, {naive():.0f} here")
    # untimed stops: by distance between their timed neighbours
    for i, timed_stop in out:
        if timed_stop:
            continue
        a = max(c for c in chain if c < i)
        b = min(c for c in chain if c > i)
        da = sum(km(pos(rows[k]), pos(rows[k + 1])) for k in range(a, i))
        db = sum(km(pos(rows[k]), pos(rows[k + 1])) for k in range(i, b))
        t = U[a][1] + (U[b][0] - U[a][1]) * da / max(da + db, 1e-9)
        U[i] = (t, t)
    res = []
    for i, _ in out:
        r = rows[i]
        res.append([r[0], r[1], int(round(U[i][0] + 60 * r[1])), int(round(U[i][1] + 60 * r[1])), r[4]])
    return res


def compile_services():
    g = places()
    cities, services, skipped = {}, [], []
    for row in lines():
        rid = row["routeid"]
        countries = {c.strip() for c in row["countries"].split(",")} | {"LI"}
        print(rid, row["nighttrain"], "|", row["itinerary"], flush=True)
        for e in parse_route(rid):
            if "1" not in e["days"]:
                print("  not running (no days):", e["num"])
                continue
            rows = direction(g, countries, e, f"{row['nighttrain']} {e['num']}")
            if rows is None:
                print("  no usable stops in", e["num"])
                continue
            if any(r[0][2] > MAX_LON for r in rows):
                skipped.append(f"{row['nighttrain']} {e['num']}")
                continue
            services.append({
                "name": e["num"], "op": row["operators"].replace(",", "/").replace(" ", ""),
                "route": f"{rows[0][4]} - {rows[-1][4]}", "days": e["days"],
                "stops": [[round(r[0][1], 3), round(r[0][2], 3), r[1], r[2], r[3]] for r in rows]})
            for r in rows:
                rec = r[0]
                key = (round(rec[1], 2), round(rec[2], 2))
                if rec[0] >= 30000 or r in (rows[0], rows[-1]):
                    cities[key] = (rec[5], round(rec[1], 3), round(rec[2], 3), max(1, rec[0] // 1000))
    # the compact table must not be bulky: 3 decimals of a degree is ~100 m
    cities = sorted(cities.values(), key=lambda c: -c[3])
    out = {"source": "Back-on-Track.eu Open Night Train Database (timetables, read 2026-10-28; check with the "
                     "operators), GeoNames cities1000 (CC BY 4.0, places)",
           "compiled": COMPILED, "cities": [list(c) for c in cities], "services": services}
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "services.json")
    with open(path, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(path, os.path.getsize(path) // 1024, "KB,", len(services), "services,", len(cities), "cities")
    if skipped:
        print("left out (east of the picture):", ", ".join(skipped))


# ------------------------------------------------------------------ the coast ---

def rdp(pts, tol):
    """Ramer-Douglas-Peucker on (lat, lon), tolerance in km (flat approximation round the first point)."""
    if len(pts) < 3:
        return pts
    if pts[0] == pts[-1]:                                     # a ring (an island): split at its far point first
        far = max(range(len(pts)), key=lambda i: km(pts[0], pts[i]))
        if 0 < far < len(pts) - 1:
            return rdp(pts[:far + 1], tol) + rdp(pts[far:], tol)[1:]
    k = math.cos(math.radians(pts[0][0]))
    xy = [(p[1] * 111.32 * k, p[0] * 111.32) for p in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = xy[a], xy[b]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy) or 1e-9
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            d = abs(dy * (xy[i][0] - ax) - dx * (xy[i][1] - ay)) / n
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, kp in zip(pts, keep) if kp]


def land():
    gj = json.loads(get(NE_COAST, "ne_50m_coastline.geojson", pause=0))
    box = (32.0, -14.0, 72.0, 46.0)                           # lat0, lon0, lat1, lon1: a little more than the picture
    out = []
    for f in gj["features"]:
        g = f["geometry"]
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for part in parts:
            run = []
            for lon, lat in part:
                if box[0] <= lat <= box[2] and box[1] <= lon <= box[3]:
                    run.append((lat, lon))
                else:
                    if len(run) > 1:
                        out.append(run)
                    run = []
            if len(run) > 1:
                out.append(run)
    coast = []
    for run in out:
        length = sum(km(run[i], run[i + 1]) for i in range(len(run) - 1))
        if length < 25.0:                                      # a speck: under two LEDs
            continue
        s = rdp(run, 3.0)
        coast.append([[round(p[0], 2), round(p[1], 2)] for p in s])
    res = {"source": "Natural Earth 1:50m coastline (public domain)", "coast": coast}
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "europe.json")
    with open(path, "w") as fh:
        json.dump(res, fh, separators=(",", ":"))
    print(path, os.path.getsize(path) // 1024, "KB,", len(coast), "lines,", sum(len(c) for c in coast), "points")


# ------------------------------------------------------------------ check ---

def check():
    with open(os.path.join(OUT, "services.json")) as fh:
        d = json.load(fh)
    bad = 0
    stats = []
    for s in d["services"]:
        st = s["stops"]
        problems = []
        if len(s["days"]) != 7:
            problems.append("days")
        for i, x in enumerate(st):
            if x[4] < x[3]:
                problems.append(f"stop {i} leaves before it arrives")
            if i:
                a, b = st[i - 1], x
                dt = ((b[3] - 60 * b[2]) - (a[4] - 60 * a[2])) / 60.0
                d_km = km(a[:2], b[:2])
                if dt < 0 or (d_km > 30 and (dt == 0 or d_km / dt > MAX_KMH)):
                    problems.append(f"leg {i}: {d_km:.0f} km in {dt:.2f} h")
        total = sum(km(st[i - 1][:2], st[i][:2]) for i in range(1, len(st)))
        hours = ((st[-1][3] - 60 * st[-1][2]) - (st[0][4] - 60 * st[0][2])) / 60.0
        stats.append((s["name"], total, hours, total / max(hours, 0.1)))
        if hours > 30 or hours < 1.0:
            problems.append(f"{hours:.1f} h long")
        if problems:
            bad += 1
            print(s["name"], s["route"], "|", "; ".join(problems))
    print(len(d["services"]), "services,", bad, "with problems;",
          "mean speed %.0f km/h" % (sum(x[3] for x in stats) / len(stats)))


if __name__ == "__main__":
    {"trains": compile_services, "land": land, "check": check}[sys.argv[1]]()
