"""Build the data for display/wanderers.py (Ocean wanderers). Run on the laptop; the results are committed
(both small), so the wall needs no internet for them.

    python3 tools/build_wanderers.py            -> assets/migrations/wanderers.json  (real recorded tracks, open data)
    python3 tools/build_wanderers.py --coast    -> assets/maps/atlantic.json         (Natural Earth 1:50m coastline)
    python3 tools/build_wanderers.py --movebank STUDY_ID KIND "SPECIES NAME"
                                                 add every individual of a PUBLIC Movebank study (KIND tern|shark|turtle|whale)
    python3 tools/build_wanderers.py --prime-ocearch
                                                 fetch OCEARCH now into panel_setup/wanderers_cache.json (git-ignored; see below)
    [--fresh to ignore the downloads cached in the temp dir]

Where the tracks come from (all checked reachable when this was written, October 2026):
  * Arctic terns, 9 birds, 2007-08 (Egevang et al. 2010, PNAS 107: 2078-2081): the dataset "Tracking of Arctic tern
    migrations 2007-2008" (Greenland Institute of Natural Resources) published by OBIS-SEAMAP and mirrored by GBIF:
    https://api.gbif.org/v1/occurrence/search?datasetKey=767f57dd-bdb8-44cb-bf20-f9aafafa4137   (CC BY-NC 4.0)
  * Loggerhead and leatherback turtles: OBIS-SEAMAP tracking datasets on GBIF (CC BY-NC 4.0, positions to a one-degree
    cell). See DATASETS below.
  * Natural Earth 1:50m land (public domain) for the coastline.
  The Movebank public JSON service (www.movebank.org/movebank/service/public/json?study_id=..) answers for studies whose
  owners allow public download; parse_movebank_json() reads it. No Arctic tern study with open Movebank access was found.
  Dryad's "Hypotheses and tracking results about the longest migration" (Alerstam et al. 2019, doi 10.5061/dryad.d6080nt,
  CC0, Baltic terns, 12 journeys) is an .xlsx behind a token the sandbox could not get: it is not used.

OCEARCH is deliberately NOT built into the committed file. Its data policy (https://www.ocearch.org/data-sharing/) is
"for viewing purposes only ... Any use ... without explicit permission of OCEARCH and the collaborating institution is
strictly prohibited", and this repository is public. display/wanderers.py reads OCEARCH's public map feed at runtime for
viewing and keeps only a git-ignored cache (panel_setup/wanderers_cache.json). --prime-ocearch fills that cache by hand.
If OCEARCH grants permission to redistribute, `--include-ocearch` writes its animals into the bundled file as well.
"""
import html
import json
import math
import os
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from display import wanderers as wd  # noqa: E402

OUT = os.path.join(HERE, "assets", "migrations", "wanderers.json")
COAST_OUT = os.path.join(HERE, "assets", "maps", "atlantic.json")
GBIF = "https://api.gbif.org/v1/"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson"

SPECIES = {"Sterna paradisaea": ("tern", "ARCTIC TERN"), "Caretta caretta": ("turtle", "LOGGERHEAD TURTLE"),
           "Dermochelys coriacea": ("turtle", "LEATHERBACK TURTLE"), "Chelonia mydas": ("turtle", "GREEN TURTLE")}

# (GBIF dataset key, minimum fixes for an animal to be kept, at most this many animals, longest gap in days to draw across)
DATASETS = [
    ("767f57dd-bdb8-44cb-bf20-f9aafafa4137", 150, 12, 35.0),     # Arctic terns, Greenland Institute of Natural Resources
    ("de25c221-9c9d-40ea-abed-d3d1e14eebc4", 25, 3, 40.0),       # Duke North Atlantic Turtle Tracking (loggerheads)
    ("d4baf2c5-090d-417b-9c29-d14d762d2ce1", 60, 1, 40.0),       # Leatherbacks of Dominica
    ("e905c8b5-a437-429a-ba2a-991a1b758309", 40, 1, 40.0),       # Gabon 2009-10 leatherbacks
    ("11f443ac-e9ee-4e90-8011-4955147c6efa", 35, 2, 40.0),       # Gabon 2012 leatherbacks
]


def get(url, name, binary=False):
    cache = os.path.join(tempfile.gettempdir(), "fortuna_wd_" + name)
    if not os.path.exists(cache) or "--fresh" in sys.argv:
        req = urllib.request.Request(url, headers={"User-Agent": "fortuna-wall/1.0 (art project)"})
        with urllib.request.urlopen(req, timeout=300) as r, open(cache, "wb") as fh:
            fh.write(r.read())
    with open(cache, "rb") as fh:
        data = fh.read()
    return data if binary else json.loads(data)


def gbif_records(key):
    out, off = [], 0
    while True:
        d = get(f"{GBIF}occurrence/search?datasetKey={key}&limit=300&offset={off}", f"gbif_{key}_{off}.json")
        out += d["results"]
        off += 300
        if d.get("endOfRecords") or off >= d["count"]:
            return out


def period(t0, last):
    a, b = time.gmtime(t0).tm_year, time.gmtime(last).tm_year
    return str(a) if a == b else f"{a}-{str(b)[2:]}"


def from_gbif(key, min_fixes, max_n, gap):
    meta = get(f"{GBIF}dataset/{key}", f"meta_{key}.json")
    recs = gbif_records(key)
    by_species = {}
    for r in recs:
        by_species.setdefault(" ".join((r.get("scientificName") or "").split()[:2]), []).append(r)
    src = {"title": html.unescape(meta["title"]), "licence": meta.get("license"), "doi": meta.get("doi"),
           "citation": html.unescape((meta.get("citation") or {}).get("text") or ""), "url": "https://www.gbif.org/dataset/" + key}
    animals = []
    for sci, rs in by_species.items():
        sp = next((v for k, v in SPECIES.items() if sci.startswith(k)), None)
        if sp is None:
            continue
        tracks = wd.parse_gbif_occurrences(rs)
        # a one-degree cell with an animal far off the Atlantic (or a bad fix) is not drawn
        for oid, fixes in sorted(tracks.items(), key=lambda kv: -len(kv[1])):
            if len(animals) >= 99:
                break
            fixes = [f for f in fixes if -100.0 <= f[2] <= 115.0 and -80.0 <= f[1] <= 80.0]
            win, t0 = wd.year_window(fixes)
            if len(win) < min_fixes:
                continue
            animals.append({"id": oid, "kind": sp[0], "species": sp[1], "name": "", "tag": oid.split("_")[-1].rstrip("a"),
                            "src": "recorded", "period": period(t0, t0 + win[-1][0] * 86400.0), "t0": int(t0), "gap": gap,
                            "dataset": key, "fixes": [[round(d, 2), round(la, 2), round(lo, 2)] for d, la, lo in win]})
            if sum(1 for a in animals if a["dataset"] == key) >= max_n:
                break
    return src, animals


def from_movebank(study_id, kind, species, gap=20.0, min_fixes=60):
    url = f"https://www.movebank.org/movebank/service/public/json?study_id={study_id}&sensor_type=gps&max_events_per_individual=100000"
    inds = wd.parse_movebank_json(get(url, f"movebank_{study_id}.json"))
    src = {"title": f"Movebank study {study_id}", "licence": "see the study's page on movebank.org",
           "url": f"https://www.movebank.org/cms/webapp?gwt_fragment=page=studies,path=study{study_id}"}
    animals = []
    for ind in inds:
        win, t0 = wd.year_window(ind["fixes"])
        if len(win) < min_fixes:
            continue
        win = wd.thin(win, 0.5)
        animals.append({"id": f"mb{study_id}_{ind['id']}", "kind": kind, "species": species, "name": "", "tag": ind["id"][-6:],
                        "src": "recorded", "period": period(t0, t0 + win[-1][0] * 86400.0), "t0": int(t0), "gap": gap,
                        "fixes": [[round(d, 2), round(la, 3), round(lo, 3)] for d, la, lo in win]})
    return src, animals


def build():
    sources, animals = [], []
    for key, mn, mx, gap in DATASETS:
        src, got = from_gbif(key, mn, mx, gap)
        for a in got:
            a["src_i"] = len(sources)
            a.pop("dataset", None)
        sources.append(src)
        animals += got
        print(f"{src['title'][:70]}: {len(got)} animals")
    if "--movebank" in sys.argv:
        i = sys.argv.index("--movebank")
        src, got = from_movebank(sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3])
        for a in got:
            a["src_i"] = len(sources)
        sources.append(src)
        animals += got
        print(f"{src['title']}: {len(got)} animals")
    if "--include-ocearch" in sys.argv:
        got = wd.ocearch_animals()
        sources.append({"title": "OCEARCH Global Shark Tracker (included with OCEARCH's permission only)",
                        "licence": "all rights reserved by OCEARCH and its collaborating institutions", "url": "https://www.ocearch.org/tracker/"})
        for a in got:
            a["src_i"] = len(sources) - 1
        animals += got
    doc = {"format": 1, "built": time.strftime("%Y-%m-%d", time.gmtime()),
           "about": "Real recorded animal tracks, one calendar year each (t0 = unix time of the first fix; fixes = [days since t0, lat, lon]). "
                    "Open data only; see sources. Built by tools/build_wanderers.py for display/wanderers.py.",
           "sources": sources, "animals": animals}
    text = json.dumps(doc, separators=(",", ":"))
    with open(OUT, "w") as fh:
        fh.write(text)
    print(f"wrote {OUT}: {len(animals)} animals, {len(text) / 1000:.0f} kB")


# --------------------------------------------------------------------------- the coastline ---
VIEW = (-95.0, 35.0, -82.0, 80.0)          # lon min/max, lat min/max kept (a margin around the wall's view)


def rdp(pts, tol):
    """Ramer-Douglas-Peucker on [lat, lon] points in degrees (the view is plate carree, so degrees are the metric)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ay, ax), (by, bx) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy) or 1e-12
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            py, px = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / n
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def coast(min_extent=0.9, tol=0.1):
    gj = get(NE, "ne_50m_land.geojson")
    lo0, lo1, la0, la1 = VIEW
    runs = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            ring = poly[0]                                    # the outline; holes (inland lakes) are not drawn
            lons, lats = [p[0] for p in ring], [p[1] for p in ring]
            if max(lons) - min(lons) < min_extent and max(lats) - min(lats) < min_extent:
                continue                                      # a speck of an island: noise at this scale
            if max(lons) < lo0 or min(lons) > lo1 or max(lats) < la0 or min(lats) > la1:
                continue
            inside = [lo0 <= x <= lo1 and la0 <= y <= la1 for x, y in ring]
            if all(inside):
                runs.append([[y, x] for x, y in ring])
                continue
            cur = []
            for i, p in enumerate(ring):                      # the parts inside the view, each reaching one point past its edge
                if inside[i]:
                    if not cur and i > 0:
                        cur.append([ring[i - 1][1], ring[i - 1][0]])
                    cur.append([p[1], p[0]])
                elif cur:
                    cur.append([p[1], p[0]])
                    runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
    rings = []
    for r in runs:
        s = rdp(r, tol)
        if len(s) >= 3 or (len(s) == 2 and math.dist(s[0], s[1]) > 1.0):
            rings.append([[round(a, 2), round(b, 2)] for a, b in s])
    doc = {"about": "Coastline of the Atlantic for display/wanderers.py: Natural Earth 1:50m land (public domain), outlines only, simplified to 0.1 degree. Lines of [lat, lon].",
           "rings": rings}
    text = json.dumps(doc, separators=(",", ":"))
    with open(COAST_OUT, "w") as fh:
        fh.write(text)
    print(f"wrote {COAST_OUT}: {len(rings)} lines, {sum(len(r) for r in rings)} points, {len(text) / 1000:.0f} kB")


def prime_ocearch():
    got = wd.ocearch_animals()
    wd.write_cache({"t": time.time(), "animals": got})
    for a in got:
        print(a["kind"], a["name"], a["species"], len(a["fixes"]), "fixes, last ping", time.strftime("%Y-%m-%d", time.gmtime(a["last"])))
    print(f"wrote {wd.CACHE} ({len(got)} animals; git-ignored, never commit)")


if __name__ == "__main__":
    if "--coast" in sys.argv:
        coast()
    elif "--prime-ocearch" in sys.argv:
        prime_ocearch()
    else:
        build()
