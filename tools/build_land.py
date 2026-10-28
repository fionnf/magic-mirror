"""Build the land mask the earthquakes piece (display/quakes.py) turns into a globe of dots: the whole
Earth on a plain latitude/longitude grid, half a degree per cell, 1 where it is land. Run on the laptop;
the result is committed (a 1-bit PNG of a few KB), so the wall needs no internet for it.

    python3 tools/build_land.py            -> assets/maps/land_mask.png   (720 x 360, row 0 = 90 N)

Source: Natural Earth 1:50m land, minus the 1:50m lakes (so the Caspian, the great lakes of Africa and
America stay water), public domain, from the natural-earth-vector repository on GitHub. Each cell is
drawn 4 x 4 times finer and counts as land when at least half of it is.
"""
import json
import os
import sys
import tempfile
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets", "maps", "land_mask.png")
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"
PER_DEG = 2                                   # cells per degree
SUB = 4                                       # finer drawing per cell, averaged down


def get(name):
    """Download once into the temp dir (rerun with --fresh to fetch again)."""
    path = os.path.join(tempfile.gettempdir(), "fortuna_land_" + name + ".geojson")
    if not os.path.exists(path) or "--fresh" in sys.argv:
        req = urllib.request.Request(NE.format(name), headers={"User-Agent": "fortuna-wall/1.0 (private art project)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        with open(path, "wb") as fh:
            fh.write(data)
    with open(path) as fh:
        return json.load(fh)


def rings(gj):
    for f in gj["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            for ring in poly:                         # outer ring and holes alike: drawn with XOR below
                yield np.asarray(ring, np.float64)


def draw(gj, w, h):
    import cv2
    k = w / 360.0
    m = np.zeros((h, w), np.uint8)
    for ring in rings(gj):
        pts = np.stack([(ring[:, 0] + 180.0) * k, (90.0 - ring[:, 1]) * k], 1)
        layer = np.zeros_like(m)
        cv2.fillPoly(layer, [np.round(pts * 8).astype(np.int32)], 1, cv2.LINE_8, shift=3)
        m ^= layer                                    # a hole inside a polygon cancels it out
    return m


def main():
    from PIL import Image
    w, h = 360 * PER_DEG * SUB, 180 * PER_DEG * SUB
    land = draw(get("ne_50m_land"), w, h) & (1 - draw(get("ne_50m_lakes"), w, h))
    cover = land.reshape(h // SUB, SUB, w // SUB, SUB).mean(axis=(1, 3))
    mask = cover >= 0.5
    Image.fromarray((mask * 255).astype(np.uint8)).convert("1").save(OUT, optimize=True)
    print(f"{OUT}: {mask.shape[1]} x {mask.shape[0]}, {mask.mean() * 100:.1f}% land, {os.path.getsize(OUT)} bytes")


if __name__ == "__main__":
    main()
