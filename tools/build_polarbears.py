"""Build assets/migrations/polarbears.json for display/polarbears.py: recorded polar bear collar tracks
from the Norwegian Polar Institute's open data (api.npolar.no), the Svalbard land from Natural Earth, and
a bundled sea-ice window from NSIDC's Sea Ice Index. Run on the laptop; the result is committed.

    python3 tools/build_polarbears.py          [--fresh to ignore the downloads cached in /tmp]

Where the bear data comes from (verified working):
  * dataset record  https://api.npolar.no/dataset/132248b4-34fc-41e0-b34e-5772b52a8fdf.json   (licences: CC BY 4.0)
  * data file       https://api.npolar.no/dataset/132248b4-34fc-41e0-b34e-5772b52a8fdf/_file/PBRS_CoastalLocations.txt
    tab separated: ID ("<individual>,<platform>"), Date, Longitude, Latitude, Species. 61 polar bears, 2002-2013.
  (The tracking positions collection of api.npolar.no/tracking/ answers 0 rows or 401 for polar bears; the
  open way to real polar bear positions is this dataset file, published by NPI as open data.)

We keep the 2012 bears (one season, one shared clock), at most one fix a day (the one nearest noon),
only bears with a long enough track.
"""
import calendar
import datetime
import json
import os
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

DATASET = "132248b4-34fc-41e0-b34e-5772b52a8fdf"
API = "https://api.npolar.no/dataset/"
NE_LAND = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson"
YEAR = 2012
MIN_DAYS = 40                    # a bear needs this many days of track to be shown
OUT = os.path.join(HERE, "assets", "migrations", "polarbears.json")


def get(url, name):
    cache = os.path.join(tempfile.gettempdir(), f"fortuna_pb_{name}")
    if not os.path.exists(cache) or "--fresh" in sys.argv:
        req = urllib.request.Request(url, headers={"User-Agent": "fortuna-wall/1.0 (art project)"})
        with urllib.request.urlopen(req, timeout=300) as r, open(cache, "wb") as fh:
            fh.write(r.read())
    with open(cache, "rb") as fh:
        return fh.read()


def bears():
    meta = json.loads(get(f"{API}{DATASET}.json", "meta.json"))
    lic = meta.get("licences") or []
    raw = get(f"{API}{DATASET}/_file/PBRS_CoastalLocations.txt", "pbrs.txt").decode("utf8").splitlines()
    assert raw[0].split("\t")[:4] == ["ID", "Date", "Longitude", "Latitude"], raw[0]
    by = {}
    for line in raw[1:]:
        i, d, lon, lat, sp = line.split("\t")
        if sp != "polar_bear" or not d.startswith(str(YEAR)):
            continue
        t = calendar.timegm(time.strptime(d, "%Y-%m-%d %H:%M:%S"))
        by.setdefault(i.split(",")[0], []).append((t, float(lat), float(lon)))
    out = []
    for bid, fixes in by.items():
        day = {}
        for t, la, lo in fixes:                                  # one fix a day: the one nearest noon
            k = t // 86400
            if k not in day or abs(t - k * 86400 - 43200) < abs(day[k][0] - k * 86400 - 43200):
                day[k] = (t, la, lo)
        tr = [[v[0], round(v[1], 3), round(v[2], 3)] for k, v in sorted(day.items())]
        if len(tr) >= MIN_DAYS:
            out.append({"id": bid, "tracks": tr})
    out.sort(key=lambda b: int(b["id"]))
    return out, lic, meta


def land():
    """Svalbard's land rings ([lat, lon], simplified to ~1.2 km) from Natural Earth 1:10m."""
    from build_maps import simplify
    feats = json.loads(get(NE_LAND, "ne_10m_land.geojson"))["features"]
    rings = []
    for f in feats:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            ring = poly[0]
            lons, lats = [p[0] for p in ring], [p[1] for p in ring]
            if min(lats) < 74.5 or max(lats) > 84 or min(lons) < 0 or max(lons) > 42:
                continue                                         # Svalbard's islands only
            r = simplify([[p[1], p[0]] for p in ring], 1.2)
            if len(r) >= 4:
                rings.append(r)
    return rings


def main():
    from display import polarbears as pb
    bs, lic, meta = bears()
    t0 = min(b["tracks"][0][0] for b in bs)
    t1 = max(b["tracks"][-1][0] for b in bs)
    ice = pb.fetch_ice()
    data = {
        "bears": bs,
        "land": land(),
        "ice": ice,
        "source": {
            "bears": f"Norwegian Polar Institute, dataset '{meta.get('title')}' (doi {meta.get('doi')}), file PBRS_CoastalLocations.txt via "
                     f"{API}{DATASET}/_file/PBRS_CoastalLocations.txt; Hamilton, Kovacs, Ims, Aars & Lydersen 2017, J. Anim. Ecol. 86:1054-1064",
            "land": "Natural Earth ne_10m_land (public domain)",
            "ice": "NSIDC Sea Ice Index v4.0 daily concentration, Fetterer et al. doi:10.7265/N5K072F8",
            "thinning": "one fix a day (nearest 12:00 UTC); 2012 only",
        },
        "licence": {"bears": lic, "bears_name": "CC BY 4.0 (as stated in the NPI dataset metadata)",
                    "land": "public domain", "ice": "free to use with citation (NSIDC)"},
        "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(OUT, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    n = sum(len(b["tracks"]) for b in bs)
    print(f"{len(bs)} bears, {n} fixes, {time.strftime('%Y-%m-%d', time.gmtime(t0))} .. {time.strftime('%Y-%m-%d', time.gmtime(t1))}, "
          f"{len(data['land'])} land rings, ice {ice['date']}, {os.path.getsize(OUT) / 1000:.0f} kB -> {OUT}")


if __name__ == "__main__":
    main()
