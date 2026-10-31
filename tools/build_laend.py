"""Build the map of the Remstal ("im Ländle": Bittenfeld, Korb, Schorndorf) the Ländle piece
(display/laend.py) draws, on the wall's own LED grid. Run on the laptop; the result is committed,
so the wall needs no internet for it.

    python3 tools/build_laend.py          -> assets/maps/laend.npz

Framing: north up, 192 LEDs wide = 20.5 km (107 m per LED), 256 LEDs tall = 27.4 km, centred on the
valley between Waiblingen and Schorndorf. Everything is stored 4 x finer than the LEDs (768 x 1024) so
the wall can shade and dither it down.

Elevation: the AWS open terrain tiles (Mapzen Terrarium, zoom 12; SRTM / EU-DEM and others, see
https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
Vineyards, orchards, woods, built-up land, rivers, railways, stations and place names: OpenStreetMap
(c) OpenStreetMap contributors, ODbL, through the Overpass API.
"""
import io
import json
import math
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets", "maps", "laend.npz")
TILE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
Z = 12
W, H, SUP = 192, 256, 4
M_PER_LED = 107.0
LON0, LAT_C = 9.280, 48.850                       # west edge, and the latitude of the wall's middle row
KX = 111320.0 * math.cos(math.radians(LAT_C))     # metres per degree of longitude
KY = 110950.0                                     # ... of latitude
LAT0 = LAT_C + (H / 2) * M_PER_LED / KY           # north edge
PLACES = ["Bittenfeld", "Korb", "Schorndorf", "Waiblingen", "Winnenden", "Endersbach", "Beutelsbach",
          "Grunbach", "Winterbach", "Backnang", "Weinstadt", "Fellbach", "Esslingen am Neckar", "Hohenacker",
          "Rudersberg", "Urbach", "Plüderhausen", "Remshalden", "Geradstetten", "Haubersbronn", "Buoch"]


def to_px(lat, lon, k=SUP):
    """lat/lon -> fine pixel coordinates (x right, y down)."""
    x = (np.asarray(lon) - LON0) * KX / M_PER_LED * k
    y = (LAT0 - np.asarray(lat)) * KY / M_PER_LED * k
    return x, y


def from_px(x, y, k=SUP):
    return LAT0 - np.asarray(y) * M_PER_LED / k / KY, LON0 + np.asarray(x) * M_PER_LED / k / KX


def bbox(pad=0.0):
    la1, lo0 = from_px(0, H * SUP)
    la0, lo1 = from_px(W * SUP, 0)
    return la1 - pad, lo0 - pad, la0 + pad, lo1 + pad     # south, west, north, east


def get(url, name, data=None):
    path = os.path.join(tempfile.gettempdir(), "fortuna_laend_" + name)
    if not os.path.exists(path) or "--fresh" in sys.argv:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "fortuna-wall/1.0 (private art project)"})
        with urllib.request.urlopen(req, timeout=240) as r:
            blob = r.read()
        with open(path, "wb") as fh:
            fh.write(blob)
    with open(path, "rb") as fh:
        return fh.read()


def overpass(q, name):
    err = None
    for url in OVERPASS:
        for attempt in range(3):
            try:
                return json.loads(get(url, name, data=urllib.parse.urlencode({"data": q}).encode()))
            except Exception as e:                                   # busy server: wait and go on
                err = e
                try:
                    os.remove(os.path.join(tempfile.gettempdir(), "fortuna_laend_" + name))
                except OSError:
                    pass
                time.sleep(8 * (attempt + 1))
    raise SystemExit(f"overpass failed: {err}")


# ---------------------------------------------------------------- elevation ---

def elevation():
    import cv2
    from PIL import Image
    s, w, n, e = bbox(0.01)

    def tile(lat, lon):
        nn = 2 ** Z
        return (lon + 180.0) / 360.0 * nn, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * nn
    x0, y0 = tile(n, w)
    x1, y1 = tile(s, e)
    tx0, tx1, ty0, ty1 = int(x0), int(x1), int(y0), int(y1)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            im = np.asarray(Image.open(io.BytesIO(get(TILE.format(z=Z, x=tx, y=ty), f"t{Z}_{tx}_{ty}.png"))).convert("RGB"), np.float32)
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = im[..., 0] * 256 + im[..., 1] + im[..., 2] / 256 - 32768
    gx, gy = np.meshgrid(np.arange(W * SUP) + 0.5, np.arange(H * SUP) + 0.5)
    lat, lon = from_px(gx, gy)
    nn = 2 ** Z
    px = ((lon + 180.0) / 360.0 * nn - tx0) * 256
    py = ((1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * nn - ty0) * 256
    return cv2.remap(mosaic, px.astype(np.float32), py.astype(np.float32), cv2.INTER_LINEAR)


# ------------------------------------------------------------------- OSM ---

QUERY = """[out:json][timeout:180];
(
  way["landuse"~"^(vineyard|orchard|forest|residential|commercial|industrial|retail|farmland|meadow|grass)$"]({b});
  relation["landuse"~"^(vineyard|orchard|forest|residential|commercial|industrial)$"]({b});
  way["natural"~"^(wood|water)$"]({b});
  relation["natural"~"^(wood|water)$"]({b});
  way["waterway"~"^(river|stream|canal)$"]({b});
  way["railway"~"^(rail|light_rail)$"]({b});
  node["railway"~"^(station|halt)$"]({b});
);
out geom;
"""


def rings_of(el):
    """The outer rings of a way or a multipolygon relation, as lists of (lat, lon)."""
    if el["type"] == "way":
        g = el.get("geometry") or []
        return [[(p["lat"], p["lon"]) for p in g]] if len(g) > 2 else []
    out = []
    for m in el.get("members", []):
        g = m.get("geometry") or []
        if m.get("role") == "outer" and len(g) > 2:
            out.append([(p["lat"], p["lon"]) for p in g])
    return out


def draw_all(osm):
    import cv2
    Wf, Hf = W * SUP, H * SUP
    names = ("vineyard", "orchard", "forest", "urban", "water", "farm")
    mask = {n: np.zeros((Hf, Wf), np.uint8) for n in names}
    rivers = np.zeros((Hf, Wf), np.uint8)
    streams = np.zeros((Hf, Wf), np.uint8)
    rails, stations = [], []
    for el in osm["elements"]:
        tags = el.get("tags", {})
        if el["type"] == "node":
            if tags.get("railway") in ("station", "halt") and "name" in tags:
                stations.append({"name": tags["name"], "lat": el["lat"], "lon": el["lon"]})
            continue
        lu, nat, ww, rw = tags.get("landuse"), tags.get("natural"), tags.get("waterway"), tags.get("railway")
        if ww:
            pts = [(p["lat"], p["lon"]) for p in el.get("geometry", [])]
            if len(pts) > 1:
                x, y = to_px([p[0] for p in pts], [p[1] for p in pts])
                th = {"river": 5, "canal": 3}.get(ww, 2)
                cv2.polylines(streams if ww == "stream" else rivers, [np.round(np.stack([x, y], 1) * 8).astype(np.int32)], False, 255, th, cv2.LINE_AA, shift=3)
            continue
        if rw:
            pts = [(p["lat"], p["lon"]) for p in el.get("geometry", [])]
            if len(pts) > 1 and tags.get("service") not in ("yard", "siding", "spur"):
                rails.append({"pts": pts, "name": tags.get("name", ""), "usage": tags.get("usage", "")})
            continue
        kind = {"vineyard": "vineyard", "orchard": "orchard", "forest": "forest", "residential": "urban", "commercial": "urban",
                "industrial": "urban", "retail": "urban", "farmland": "farm", "meadow": "farm", "grass": "farm"}.get(lu)
        if nat == "wood":
            kind = "forest"
        elif nat == "water":
            kind = "water"
        if not kind:
            continue
        layer = np.zeros((Hf, Wf), np.uint8)
        for ring in rings_of(el):
            x, y = to_px([p[0] for p in ring], [p[1] for p in ring])
            cv2.fillPoly(layer, [np.round(np.stack([x, y], 1) * 8).astype(np.int32)], 1, cv2.LINE_8, shift=3)
        mask[kind] |= layer
    return mask, rivers, streams, rails, stations


def places():
    q = '[out:json][timeout:60];node["place"~"^(town|village|suburb|city)$"]["name"]({b});out;'.format(b=",".join(f"{v:.5f}" for v in bbox()))
    out = {}
    for e in overpass(q, "places.json")["elements"]:
        n = e["tags"]["name"]
        if n in PLACES and n not in out:
            out[n] = (e["lat"], e["lon"])
    return out


def main():
    s, w, n, e = bbox(0.004)
    print("bbox", s, w, n, e)
    elev = elevation()
    print("elevation", elev.min(), elev.max())
    osm = overpass(QUERY.format(b=",".join(f"{v:.5f}" for v in (s, w, n, e))), "osm.json")
    print("osm elements", len(osm["elements"]))
    mask, rivers, streams, rails, stations = draw_all(osm)
    pl = places()
    print({k: int(v.sum()) for k, v in mask.items()}, "rails", len(rails), "stations", len(stations), "places", len(pl))
    pl_px = {k: [float(a) for a in to_px(la, lo, 1)] for k, (la, lo) in pl.items()}      # LED coordinates
    rail_px = [{"name": r["name"], "usage": r["usage"],
                "pts": np.round(np.stack(to_px([p[0] for p in r["pts"]], [p[1] for p in r["pts"]], 1), 1), 2).tolist()} for r in rails]
    st_px = [{"name": s_["name"], "xy": [round(float(a), 2) for a in to_px(s_["lat"], s_["lon"], 1)]} for s_ in stations]
    np.savez_compressed(
        OUT, elev=elev.astype(np.float16), rivers=rivers, streams=streams,
        **{k: np.packbits(v, axis=1) for k, v in mask.items()},
        meta=np.frombuffer(json.dumps({"W": W, "H": H, "SUP": SUP, "places": pl_px, "rails": rail_px, "stations": st_px,
                                       "lon0": LON0, "lat0": LAT0, "m_per_led": M_PER_LED, "kx": KX, "ky": KY}).encode(), np.uint8))
    print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
