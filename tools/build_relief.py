"""Build the relief the snow piece (display/snow.py) draws on: Switzerland on the wall's own LED grid,
one elevation in metres per LED, with the country mask and the lakes. Run on the laptop; the result is
committed, so the wall needs no internet for it.

    python3 tools/build_relief.py          -> assets/maps/ch_relief.npz

Elevation: the AWS open terrain tiles (Mapzen Terrarium encoding, zoom 8, ~420 m per pixel there:
elevation = R * 256 + G + B / 256 - 32768; sources SRTM, EU-DEM and others, see
https://github.com/tilezen/joerd/blob/master/docs/attribution.md). Each LED takes the mean of 5 x 5
samples across its own square, so a LED is the mean height of its 1.8 km x 1.8 km of ground.
Border and lakes: Natural Earth 1:10m (public domain), admin-0 countries and lakes (+ the European
supplement, which has the smaller Swiss lakes).

The framing: Switzerland across the full 192 LED width (1 LED margin each side), in true proportions
(one cos(latitude) for the whole country), the country vertically centred on the 256 LED wall.
The asset stores the band of rows that hold the country (plus a margin) and where it sits.
"""
import io
import json
import math
import os
import sys
import tempfile
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "assets", "maps", "ch_relief.npz")
TILE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"
Z = 8
CH_BOX = (45.818, 5.956, 47.808, 10.492)          # lat0, lon0, lat1, lon1 of Switzerland
MARGIN_PX = 1                                     # LEDs left free at each side
BAND_PAD = 6                                      # rows of relief kept above and below the country
SUB = 5                                           # samples per LED per axis


def get(url, name):
    """Download once into the temp dir (rerun with --fresh to fetch again)."""
    path = os.path.join(tempfile.gettempdir(), "fortuna_relief_" + name)
    if not os.path.exists(path) or "--fresh" in sys.argv:
        req = urllib.request.Request(url, headers={"User-Agent": "fortuna-wall/1.0 (private art project)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        with open(path, "wb") as fh:
            fh.write(data)
    with open(path, "rb") as fh:
        return fh.read()


def merc(lat, lon, z):
    """Lat/lon -> global pixel coordinates of the 256 px web-mercator tiles at zoom z."""
    n = 256.0 * 2 ** z
    x = (lon + 180.0) / 360.0 * n
    s = np.sin(np.radians(lat))
    y = (0.5 - np.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def main():
    import cv2
    from PIL import Image
    import config
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT

    lat_c = (CH_BOX[0] + CH_BOX[2]) / 2
    lon_c = (CH_BOX[1] + CH_BOX[3]) / 2
    kx = math.cos(math.radians(lat_c)) * 111.32
    km_w = (CH_BOX[3] - CH_BOX[1]) * kx
    km_px = km_w / (W - 2 * MARGIN_PX)
    ch_rows = (CH_BOX[2] - CH_BOX[0]) * 111.32 / km_px
    band_h = int(math.ceil(ch_rows)) + 2 * BAND_PAD
    y0 = int(round(H / 2 - band_h / 2))           # the band's top row on the wall

    def to_px(lat, lon):                          # wall pixel coordinates (centre of LED (i, j) = (j, i))
        return ((lon - lon_c) * kx / km_px + W / 2 - 0.5,
                (lat_c - lat) * 111.32 / km_px + H / 2 - 0.5)

    # lat/lon of every sample: SUB x SUB per LED of the band
    jj = (np.arange(W * SUB) + 0.5) / SUB - 0.5
    ii = (np.arange(band_h * SUB) + 0.5) / SUB - 0.5 + y0
    lon = lon_c + (jj - W / 2 + 0.5) * km_px / kx
    lat = lat_c - (ii - H / 2 + 0.5) * km_px / 111.32
    LON, LAT = np.meshgrid(lon, lat)
    mx, my = merc(LAT, LON, Z)
    tx0, tx1 = int(mx.min() // 256), int(mx.max() // 256)
    ty0, ty1 = int(my.min() // 256), int(my.max() // 256)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            png = get(TILE.format(z=Z, x=tx, y=ty), f"z{Z}_{tx}_{ty}.png")
            a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), np.float32)
            e = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = e
            print(f"tile {tx},{ty}  {e.min():.0f}..{e.max():.0f} m", flush=True)
    samp = cv2.remap(mosaic, (mx - tx0 * 256 - 0.5).astype(np.float32), (my - ty0 * 256 - 0.5).astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    elev = samp.reshape(band_h, SUB, W, SUB).mean(axis=(1, 3))
    elev = np.clip(np.rint(elev), -100, 4900).astype(np.int16)

    def polys(name, keep):
        g = json.loads(get(NE.format(name), name + ".geojson"))
        out = []
        for f in g["features"]:
            if not keep(f["properties"]):
                continue
            geom = f["geometry"]
            parts = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            for poly in parts:
                rings = []
                for ring in poly:
                    r = np.array(ring, np.float64)
                    if r[:, 0].max() < 5.0 or r[:, 0].min() > 11.5 or r[:, 1].max() < 45.0 or r[:, 1].min() > 48.5:
                        break
                    x, y = to_px(r[:, 1], r[:, 0])
                    rings.append(np.stack([x, y - y0], 1))
                if rings:
                    out.append(rings)
        return out

    def raster(ps):
        """Fill polygons (holes cut) on a 4x finer grid, then a LED is in when most of it is."""
        k = 4
        m = np.zeros((band_h * k, W * k), np.uint8)
        for rings in ps:
            pts = [np.rint((r + 0.5) * k - 0.5).astype(np.int32) for r in rings]
            cv2.fillPoly(m, pts[:1], 255)
            if len(pts) > 1:
                cv2.fillPoly(m, pts[1:], 0)
        return m.reshape(band_h, k, W, k).mean(axis=(1, 3)) >= 127.5

    ch = raster(polys("ne_10m_admin_0_countries",
                      lambda p: p.get("ADM0_A3") == "CHE" or p.get("ISO_A3") == "CHE"))
    lakes = raster(polys("ne_10m_lakes", lambda p: True) + polys("ne_10m_lakes_europe", lambda p: True))
    lakes &= np.pad(ch, 3, mode="edge")[3:-3, 3:-3] | ch       # Swiss lakes, whole (Geneva and Constance reach out)
    lakes = lakes & (elev < 2000)
    print(f"band {band_h} rows from y={y0}, {km_px:.3f} km/LED, {ch.sum()} LEDs of Switzerland, "
          f"{lakes.sum()} of lake, elevation {elev[ch].min()}..{elev[ch].max()} m", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(OUT, elev=elev, ch=ch, lakes=lakes,
                        meta=np.array([lat_c, lon_c, km_px, y0], np.float64))
    print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
