"""Build the small maps the live pieces draw on, from OpenStreetMap (data (c) OpenStreetMap
contributors, ODbL). Run on the laptop; the result is committed, so the wall needs no internet for them.

    python3 tools/build_maps.py zurich     -> assets/maps/zurich.json   (lakes, rivers, runways)
    python3 tools/build_maps.py westcork   -> assets/maps/westcork.json (coastline, navigation lights)

Shapes are lists of [lat, lon] points, simplified to ~40 m (finer than one LED).
"""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets", "maps")
API = "https://overpass-api.de/api/interpreter"

QUERIES = {
    "zurich": '[out:json][timeout:120];('
              'way["natural"="water"]["water"~"lake|reservoir"](47.02,8.10,47.79,8.99);'
              'relation["natural"="water"]["water"~"lake|reservoir"](47.02,8.10,47.79,8.99);'
              'way["aeroway"="runway"](47.43,8.50,47.49,8.60);'
              'way["waterway"="river"]["name"~"^(Limmat|Rhein|Sihl)$"](47.02,8.10,47.79,8.99););'
              'out geom;',
    "westcork": '[out:json][timeout:150];('
                'way["natural"="coastline"](51.15,-10.0,51.85,-9.1);'
                'node["seamark:light:character"](51.15,-10.0,51.85,-9.1);'
                'node["seamark:light:1:character"](51.15,-10.0,51.85,-9.1););'
                'out geom;',
}


def fetch(q, name):
    import tempfile
    cache = os.path.join(tempfile.gettempdir(), f"fortuna_osm_{name}.json")
    if os.path.exists(cache) and "--fresh" not in sys.argv:
        with open(cache) as fh:
            return json.load(fh)
    els = _fetch(q)
    with open(cache, "w") as fh:
        json.dump(els, fh)
    return els


def _fetch(q):
    data = urllib.parse.urlencode({"data": q}).encode()
    for k in range(8):
        try:
            req = urllib.request.Request(API, data, headers={"User-Agent": "fortuna-wall/1.0 (private art project)"})
            with urllib.request.urlopen(req, timeout=200) as r:
                return json.load(r)["elements"]
        except Exception as e:
            wait = 15 * 2 ** k
            print(f"overpass busy ({str(e)[:60]}), again in {wait} s", flush=True)
            time.sleep(wait)
    raise SystemExit("overpass did not answer")


def _xy(p, lat0):
    return p[1] * 111.32 * math.cos(math.radians(lat0)), p[0] * 111.32


def simplify(pts, tol_km=0.04):
    """Ramer-Douglas-Peucker on lat/lon points (a closed ring is split at its far point first)."""
    if len(pts) < 3:
        return pts
    if pts[0] == pts[-1]:
        lat0 = pts[0][0]
        x0, y0 = _xy(pts[0], lat0)
        far = max(range(len(pts)), key=lambda i: math.hypot(_xy(pts[i], lat0)[0] - x0, _xy(pts[i], lat0)[1] - y0))
        if 0 < far < len(pts) - 1:
            return simplify(pts[:far + 1], tol_km) + simplify(pts[far:], tol_km)[1:]
    lat0 = pts[0][0]
    xy = [_xy(p, lat0) for p in pts]
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
            px, py = xy[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / n
            if d > best:
                best, bi = d, i
        if best > tol_km:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [[round(p[0], 5), round(p[1], 5)] for p, k in zip(pts, keep) if k]


def join(ways):
    """Join way segments that share end points into longer lines (rings where they close)."""
    ways = [list(w) for w in ways if len(w) > 1]
    out = []
    while ways:
        cur = ways.pop()
        grew = True
        while grew:
            grew = False
            for i, w in enumerate(ways):
                if w[0] == cur[-1]:
                    cur += w[1:]
                elif w[-1] == cur[0]:
                    cur = w[:-1] + cur
                elif w[0] == cur[0]:
                    cur = w[::-1][:-1] + cur
                elif w[-1] == cur[-1]:
                    cur += w[::-1][1:]
                else:
                    continue
                ways.pop(i)
                grew = True
                break
        out.append(cur)
    return out


def geom(e):
    return [[g["lat"], g["lon"]] for g in e.get("geometry", []) if g]


def zurich(els):
    lakes, rivers, runways = [], {}, []
    for e in els:
        t = e.get("tags", {})
        if t.get("aeroway") == "runway":
            runways.append(simplify(geom(e), 0.01))
        elif t.get("waterway") == "river":
            rivers.setdefault(t.get("name", ""), []).append(geom(e))
        elif e["type"] == "way":
            lakes.append(geom(e))
        elif e["type"] == "relation":
            lakes += join([geom(m) for m in e.get("members", []) if m.get("role") == "outer"])
    lakes = [simplify(l) for l in lakes if len(l) > 8]
    rivers = [simplify(r) for ws in rivers.values() for r in join(ws)]
    return {"lakes": lakes, "rivers": rivers, "runways": runways}


def westcork(els):
    coast, lights = [], []
    for e in els:
        t = e.get("tags", {})
        if e["type"] == "way":
            coast.append(geom(e))
        elif e["type"] == "node":
            # a sector light: the colour of its widest sector (how it mostly shows from the sea)
            secs = []
            for i in range(1, 10):
                c = t.get(f"seamark:light:{i}:colour")
                if not c:
                    break
                a, b = t.get(f"seamark:light:{i}:sector_start"), t.get(f"seamark:light:{i}:sector_end")
                width = ((float(b) - float(a)) % 360) if a and b else 360.0
                secs.append((width, i))
            pre = f"seamark:light:{max(secs)[1]}:" if secs else "seamark:light:"
            lights.append({"lat": round(e["lat"], 5), "lon": round(e["lon"], 5),
                           "name": t.get("seamark:name") or t.get("name") or "",
                           "type": t.get("seamark:type", ""),
                           "character": t.get(pre + "character", "Fl"), "colour": t.get(pre + "colour", "white"),
                           "group": t.get(pre + "group", ""), "period": t.get(pre + "period", ""),
                           "sequence": t.get(pre + "sequence", "")})
    coast = [simplify(c) for c in join(coast)]
    return {"coast": coast, "lights": lights}


if __name__ == "__main__":
    name = sys.argv[1]
    els = fetch(QUERIES[name], name)
    out = {"zurich": zurich, "westcork": westcork}[name](els)
    out["source"] = "(c) OpenStreetMap contributors, ODbL"
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".json")
    with open(path, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(path, os.path.getsize(path) // 1024, "KB", {k: len(v) for k, v in out.items() if isinstance(v, list)})
