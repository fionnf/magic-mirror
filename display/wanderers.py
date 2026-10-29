"""Ocean wanderers: tagged animals drifting across the Atlantic as slow lights. Each animal is one lit LED
with a long thread behind it that fades out along the path it has swum or flown, over a dim outline of the
Atlantic basin from the Arctic to the Weddell Sea, with West Cork marked. The Arctic tern, which flies from
Greenland and Iceland to Antarctica and back (the longest migration of any animal, some 70,000 km a year),
leaves the longest threads; turtles, sharks and humpback whales drift slowly between them. A year plays in
about an hour (a day every 10 seconds); the month is in the corner and a thin timeline along the foot
shows the year, with a mark for today's date. Every so often one animal is brought into focus: a faint
ring round its light and a small label beside it with its name (only where the tracking programme gives
the animal a real name), its species and WHAT KIND OF TRACK THIS IS.

WHAT THE WALL SHOWS IS DEPENDABLE ONLY BECAUSE EACH ANIMAL SAYS WHICH IT IS:
  * SOLID thread, label "RECORDED 2007-08" (a year): a real recorded track, replayed. The year is the year
    it was recorded; all animals share one calendar, so the seasons line up (terns leave in August, humpbacks
    go south in the northern winter). The track is the tag's own, thinned and lightly smoothed (the tern's
    light-level geolocator fixes are only good to a couple of hundred km, so seven fixes are averaged).
    Where a tag went quiet for longer than five weeks (the tern geolocators cannot fix a latitude in the Antarctic
    midsummer sun) the light goes out: nothing is drawn across the gap. Shorter gaps (the two equinoxes) are drawn straight.
  * SOLID thread, label "OCEARCH TRACK TO 27 OCT": the last 12 months of an animal on the OCEARCH tracker,
    replayed so that its light reaches its newest real ping exactly when the wall's clock reaches the date of
    that ping on the timeline. There is no "live" claim: it is a replay of a recent track, and the label gives the date
    of its last ping (with the year, "TO 27 OCT 2026", once that ping is more than 30 days old). A cache older than 14
    days is ignored, so a wall that has been offline for months falls back to the bundled tracks and typical routes.
  * DOTTED thread, label "TYPICAL ROUTE": NOT a tracked animal. A hand-drawn typical flyway of the
    species, from general knowledge of where its seasonal grounds are, only drawn for a kind of animal for
    which there is no real track to show (the sharks while OCEARCH is out of reach; the humpback whales
    always, as no open Atlantic whale track was found). It is an illustration of a pattern, never a
    measurement, and the label says so.
Nothing is invented and passed off as real.

DATA (assets/migrations/wanderers.json, built by tools/build_wanderers.py, open data only):
  * Arctic terns Sterna paradisaea, nine birds tagged in 2007 with light-level geolocators on Greenland and Iceland
    colonies and recovered in 2008: the dataset "Tracking of Arctic tern migrations 2007-2008" (Egevang, C. 2012,
    Greenland Institute of Natural Resources), published by OBIS-SEAMAP (doi 10.82144/f1e7b55e, mirrored by GBIF
    dataset 767f57dd-bdb8-44cb-bf20-f9aafafa4137). It is the tracking behind Egevang et al. (2010),
    "Tracking of Arctic terns Sterna paradisaea reveals longest animal migration", PNAS.
  * Loggerhead and leatherback turtles, four OBIS-SEAMAP datasets (positions are given to a one degree cell, about
    110 km, so their paths are coarse):
      - "Duke North Atlantic Turtle Tracking", McClellan C. 2024, doi 10.82144/a9801db3
      - "Georgia Aquarium/DomSeTCO Leatherback's of Dominica", Levenson J. 2025, doi 10.82144/d8dc714b
      - "Gabon 2009-10: Pongara, Leatherback Turtles", Witt M. 2024, doi 10.82144/75fd1c22
      - "Gabon 2012: Pongara, Leatherback Turtles", Witt M. 2024, doi 10.82144/66af5bd9
    all "Dataset published in OBIS-SEAMAP", from the Satellite Tracking and Analysis Tool (seaturtle.org), accessed via GBIF.org.
  * LICENCE, PLAINLY: ALL FIVE of those datasets (the terns and every turtle) are licensed CC BY-NC 4.0 (Creative Commons
    Attribution-NonCommercial 4.0, https://creativecommons.org/licenses/by-nc/4.0/): they may be used with attribution
    for NON-COMMERCIAL purposes only. This code is not under that licence, but the data file built from them is, so the
    bundled tracks may not be used in anything commercial (a paid installation, a product, advertising) without the
    data owners' permission; for commercial use remove them (the piece then falls back to typical routes) or ask
    them. The full citations and licence of each are in the "sources" of assets/migrations/wanderers.json.
  * The coastline: Natural Earth 1:50m land (public domain), assets/maps/atlantic.json, tools/build_wanderers.py.
OCEARCH (live, runtime only, never committed): the Global Shark Tracker's public map feed
(www.mapotic.com/api/v1/maps/3413, the same JSON the tracker's own page loads) is read on a side thread every
6 hours, the last 12 months of a dozen recently-pinging Atlantic animals are kept in
panel_setup/wanderers_cache.json (git-ignored), and the real given names (Mary Lee, ...) appear on the wall.
OCEARCH's data policy (ocearch.org/data-sharing) allows viewing only and asks for permission for other use, so
none of it is stored in the repository and the piece credits OCEARCH on every one of its labels. Set the
environment variable WANDERERS_OCEARCH=0 to turn that off; the piece then shows its bundled data alone.

The view is the Atlantic, 88 W to 27 E and 76 N to 77 S: a tern that wanders on into the Indian Ocean, or an animal in
the Gulf of Mexico or the Pacific, simply leaves the picture and comes back (or does not).

Everything is drawn on whole LEDs (no anti-aliasing), single lit LEDs on black, a one-LED-wide thread.
Without a network the piece never breaks: it uses the bundled data, whatever the cache last held (if under 14 days
old), and the typical flyways, in that order.
"""
import json
import math
import os
import re
import threading
import time
import unicodedata

import numpy as np
from PIL import Image

import config
from display import pixelfont

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "migrations", "wanderers.json")
COAST = os.path.join(ROOT, "assets", "maps", "atlantic.json")
CACHE = os.path.join(ROOT, "panel_setup", "wanderers_cache.json")

# ---- the view: plain latitude/longitude, one scale both ways (the Atlantic from the Arctic to the Weddell Sea)
LON0, LAT0 = -88.0, 76.0         # the top-left corner of the wall
PX = 1.67                        # LEDs per degree (about 66 km an LED at the equator)
HOME = (51.55, -9.50)            # West Cork

YEAR_SEC = 3600.0                # a year of the animals' lives plays in an hour
YEAR_DAYS = 365.25               # days of an animal's recording that one turn of the calendar phase plays
CACHE_MAX_AGE = 14 * 86400.0     # an OCEARCH cache older than this is ignored
OLD_PING = 30 * 86400.0          # a last ping older than this is labelled with its year
FOCUS_SEC = 45.0                 # one animal in focus for this long
FADE_SEC = 2.5                   # the label fades in and out over this
IDLE = 120.0                     # no frame drawn for this long: the piece is not showing, stop fetching
EVERY = 6 * 3600.0               # OCEARCH is read this often
STEP = 0.7                       # LEDs between samples along a path (so a thread is never broken)

KINDS = {  # kind: (colour, thread length in LEDs, smoothing window in fixes, longest gap to draw across in days)
    "tern":   ((255, 232, 150), 112.0, 7, 35.0),       # pale gold
    "shark":  ((172, 140, 255), 76.0, 1, 30.0),        # steel-violet
    "turtle": ((40, 236, 170), 76.0, 1, 40.0),         # sea-green
    "whale":  ((110, 188, 255), 84.0, 1, 30.0),        # glacier blue
}
# The wall shows nothing below ~94 in a channel and only a handful of steps above it (94 149 188 219 245): every colour
# keeps its lit channels at or above that floor, a channel that is not meant to show is 0, and the in-between tones of a
# gradient are made by ordered dithering (a fixed Bayer matrix, so nothing shimmers), never by dimming a channel.
FLOOR = 94.0
OCEAN_DEEP = np.array([0, 0, 108], np.float32)           # specks of the deep basin
OCEAN_SHELF = np.array([0, 100, 150], np.float32)        # specks along the continental shelves
LAND_COL = np.array([100, 100, 160], np.float32)         # dim slate-lilac land relief
COAST_COL = np.array([0, 108, 190], np.float32)      # the hair-thin coastline
GRAT_COL = np.array([0, 0, 124], np.float32)             # graticule dots
EQUATOR_COL = np.array([0, 96, 150], np.float32)
HOME_COL = (100, 230, 140)
TEXT_COL = (118, 130, 186)
LEGEND_COL = (104, 116, 166)
TAIL_LO = 0.30                                           # the thread's last LED is this share of the head's brightness

_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_MDAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]       # the 366-day template of year_phase()


# ------------------------------------------------------------------ calendar and projection ---
def year_phase(t):
    """Unix time -> how far through its calendar year it is (0 at 1 January 00:00 UTC, up to 1). Every year is laid on
    the same 366-day template (a 29 February slot that a common year skips), so a date has the same phase in every year
    and phase_date() is its exact inverse, leap year or not."""
    import calendar
    tm = time.gmtime(t)
    idx = tm.tm_yday - 1
    if tm.tm_mon >= 3 and not calendar.isleap(tm.tm_year):
        idx += 1                                             # skip the 29 February slot
    frac = (tm.tm_hour * 3600 + tm.tm_min * 60 + tm.tm_sec + (t - math.floor(t))) / 86400.0
    return (idx + frac) / 366.0


def _timegm(y, m, d):
    import calendar
    return calendar.timegm((y, m, d, 0, 0, 0))


def phase_date(phase):
    """Year phase -> (month index 0-11, day 1-31), on the 366-day template of year_phase()."""
    d = int(max(0.0, min(0.99999, phase)) * 366.0)
    for m, n in enumerate(_MDAYS):
        if d < n:
            return m, d + 1
        d -= n
    return 11, 31


def wrap_lon(lon, centre=-30.5):
    """Longitude wrapped into [centre-180, centre+180): the Atlantic view stays in one piece, the antimeridian is far off it."""
    return (np.asarray(lon, np.float64) - centre + 180.0) % 360.0 - 180.0 + centre


def unwrap_lon(lon):
    """Longitudes in degrees made continuous (176, 178, 179, -179 -> 176, 178, 179, 181) so that averaging and
    interpolating go the short way round the antimeridian."""
    return np.degrees(np.unwrap(np.radians(np.asarray(lon, np.float64))))


def to_px(lat, lon):
    """Latitude/longitude -> (x, y) in LEDs on the wall (floats; vectorised)."""
    return (np.asarray(lon, np.float64) - LON0) * PX, (LAT0 - np.asarray(lat, np.float64)) * PX


def clean_text(s, limit=24):
    """Text the 3x5 pixel font can draw: capitals, digits, - . and space."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()   # Toño -> TONO
    s = re.sub(r"[^A-Z0-9 .\-]", " ", s)
    return re.sub(r" +", " ", s).strip()[:limit].strip()


# ------------------------------------------------------------------ parsers (tested; also used by tools/build_wanderers.py) ---
def _iso_to_unix(s):
    """'2008-01-03T00:07', '2012-07-31', '2013-02-14T08:21Z', '2015-08-09T21:11:03/2015-08-15T06:00:16' -> unix seconds
    (the middle of a range), or None."""
    import calendar
    vals = []
    for part in str(s).split("/"):
        part = part.strip().rstrip("Z")
        part = re.sub(r"\.\d+$", "", part)
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                vals.append(calendar.timegm(time.strptime(part, fmt)))
                break
            except ValueError:
                pass
    return sum(vals) / len(vals) if vals else None


def parse_gbif_occurrences(records):
    """GBIF/OBIS-SEAMAP tracking occurrences (the 'results' of /v1/occurrence/search) -> {individual: [(t, lat, lon), ...]}
    sorted by time. A record that several animals share (organismID 'a;b': a one-degree cell holding more than one
    animal) is skipped, as is one without a date or position."""
    by = {}
    for r in records:
        oid = r.get("organismID")
        lat, lon = r.get("decimalLatitude"), r.get("decimalLongitude")
        t = _iso_to_unix(r["eventDate"]) if r.get("eventDate") else None
        if not oid or ";" in str(oid) or lat is None or lon is None or t is None:
            continue
        by.setdefault(str(oid), []).append((float(t), float(lat), float(lon)))
    return {k: sorted(v) for k, v in by.items()}


def parse_movebank_json(doc):
    """Movebank's public JSON (/movebank/service/public/json?study_id=..) -> [{'id', 'taxon', 'fixes': [(t, lat, lon)]}],
    time in unix seconds (Movebank gives milliseconds)."""
    out = []
    for ind in (doc or {}).get("individuals", []):
        fixes = sorted((loc["timestamp"] / 1000.0, float(loc["location_lat"]), float(loc["location_long"]))
                       for loc in ind.get("locations", [])
                       if loc.get("location_lat") is not None and loc.get("location_long") is not None)
        if fixes:
            out.append({"id": str(ind.get("individual_local_identifier") or ind.get("individual_id")),
                        "taxon": ind.get("individual_taxon_canonical_name", ""), "fixes": fixes})
    return out


OC_KIND = (("whale shark", "shark"), ("shark", "shark"), ("hammerhead", "shark"), ("turtle", "turtle"),
           ("whale", "whale"))


def ocearch_kind(species):
    s = str(species or "").lower()
    for key, kind in OC_KIND:
        if key in s:
            return kind
    return None


def short_species(species):
    """'White Shark (Carcharodon carcharias)' -> 'WHITE SHARK'; 'Shortfin Mako Shark' -> 'MAKO SHARK'."""
    s = re.sub(r"\(.*?\)", "", str(species or "")).strip()
    s = re.sub(r"^shortfin ", "", s, flags=re.I)
    s = re.sub(r" sea turtle$", " TURTLE", s, flags=re.I)
    return clean_text(s, 20)


def parse_ocearch_pois(doc, now, max_age_days=60.0):
    """The OCEARCH tracker's pois.geojson (a FeatureCollection) -> candidate animals that pinged within max_age_days and
    whose newest position is in the Atlantic view: [{'id', 'name', 'species', 'kind', 'last', 'lat', 'lon'}], newest first."""
    out = []
    for f in (doc or {}).get("features", []):
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        kind = ocearch_kind(p.get("species"))
        last = _iso_to_unix(p["last_move_datetime"]) if p.get("last_move_datetime") else None
        try:
            lon, lat = g["coordinates"][:2]
        except Exception:
            continue
        if kind is None or last is None or now - last > max_age_days * 86400.0 or last > now + 86400.0:
            continue
        if not (-100.0 <= lon <= 30.0 and -70.0 <= lat <= 78.0):
            continue
        out.append({"id": p.get("id"), "name": p.get("name") or "", "species": p.get("species") or "",
                    "kind": kind, "last": last, "lat": lat, "lon": lon})
    return sorted(out, key=lambda a: -a["last"])


def parse_ocearch_motion(doc):
    """The OCEARCH tracker's pois/<id>/motion/with-meta/ -> sorted [(t, lat, lon)] (GeoJSON order is lon, lat)."""
    out = []
    for m in (doc or {}).get("motion", []):
        t = _iso_to_unix(m["dt_move"]) if m.get("dt_move") else None
        try:
            lon, lat = m["point"]["coordinates"][:2]
        except Exception:
            continue
        if t is not None:
            out.append((float(t), float(lat), float(lon)))
    return sorted(out)


def year_window(fixes, end=None, span_days=365.0, min_fixes=2):
    """Pick the 12 months of a track to replay. With `end` (a live track) it is the span ending there; otherwise the
    365 days holding the most fixes. -> the fixes inside it, as [(days since the first, lat, lon)] plus the first fix's
    unix time, or ([], None) when there is too little."""
    if not fixes:
        return [], None
    fixes = sorted(fixes)
    ts = np.array([f[0] for f in fixes])
    span = span_days * 86400.0
    if end is not None:
        lo = end - span
    else:
        best, lo = -1, ts[0]
        for s in ts:
            n = int(np.searchsorted(ts, s + span, "left") - np.searchsorted(ts, s, "left"))
            if n > best:
                best, lo = n, s
    inside = [f for f in fixes if lo <= f[0] <= lo + span]
    if len(inside) < min_fixes:
        return [], None
    t0 = inside[0][0]
    return [((f[0] - t0) / 86400.0, f[1], f[2]) for f in inside], t0


def thin(fixes, min_days):
    """Keep a fix only when it is at least min_days after the last kept one (the first and last are always kept)."""
    if len(fixes) <= 2 or min_days <= 0:
        return list(fixes)
    out = [fixes[0]]
    for f in fixes[1:-1]:
        if f[0] - out[-1][0] >= min_days:
            out.append(f)
    out.append(fixes[-1])
    return out


# ------------------------------------------------------------------ typical flyways (NOT tracks) ---
# (month, day, lat, lon) in the order the year goes; the last leads back to the first. From general knowledge of
# where each species' seasonal grounds lie, drawn by hand: illustrations of a pattern, shown dotted and labelled TYPICAL ROUTE.
TYPICAL = [
    {"id": "T-TERN", "kind": "tern", "species": "ARCTIC TERN", "wps": [
        (7, 1, 66.0, -52.0), (8, 12, 63.0, -44.0), (8, 28, 55.0, -35.0), (9, 20, 49.0, -33.0), (10, 8, 36.0, -25.0),
        (10, 28, 15.0, -22.0), (11, 15, -10.0, -10.0), (12, 3, -38.0, 0.0), (12, 22, -58.0, -20.0), (1, 25, -66.0, -42.0),
        (2, 20, -68.0, -50.0), (3, 25, -64.0, -45.0), (4, 12, -40.0, -32.0), (4, 28, -10.0, -30.0), (5, 12, 15.0, -34.0),
        (5, 26, 42.0, -34.0), (6, 12, 62.0, -42.0)]},
    {"id": "T-WHITE", "kind": "shark", "species": "WHITE SHARK", "wps": [
        (7, 15, 41.7, -69.9), (9, 25, 41.0, -69.5), (10, 28, 38.0, -73.5), (11, 20, 33.5, -76.0), (12, 22, 29.0, -80.0),
        (2, 12, 27.0, -84.5), (4, 2, 30.5, -79.0), (5, 18, 36.0, -74.0), (6, 24, 40.5, -70.5)]},
    {"id": "T-BLUESHK", "kind": "shark", "species": "BLUE SHARK", "wps": [
        (6, 15, 39.0, -68.0), (8, 10, 41.0, -50.0), (10, 5, 43.0, -32.0), (12, 8, 39.0, -17.0), (2, 12, 29.0, -21.0),
        (4, 8, 22.0, -36.0), (5, 12, 21.0, -55.0), (6, 3, 31.0, -66.0)]},
    {"id": "T-HUMP-W", "kind": "whale", "species": "HUMPBACK WHALE", "wps": [
        (7, 1, 42.5, -68.5), (10, 20, 42.5, -68.5), (11, 22, 35.0, -70.0), (12, 22, 24.5, -68.5), (2, 5, 20.5, -69.5),
        (3, 20, 21.0, -68.5), (4, 14, 29.0, -69.0), (5, 12, 38.0, -68.5), (6, 20, 42.0, -68.5)]},
    {"id": "T-HUMP-E", "kind": "whale", "species": "HUMPBACK WHALE", "wps": [
        (7, 1, 66.5, -18.0), (10, 15, 65.5, -20.0), (11, 22, 50.0, -22.0), (1, 2, 30.0, -22.5), (2, 5, 16.5, -23.5),
        (3, 28, 17.0, -24.0), (4, 25, 35.0, -22.0), (5, 22, 55.0, -20.0), (6, 24, 65.5, -19.0)]},
]


def _catmull(p0, p1, p2, p3, s):
    s2, s3 = s * s, s * s * s
    return tuple(0.5 * ((2 * b) + (-a + c) * s + (2 * a - 5 * b + 4 * c - d) * s2 + (-a + 3 * b - 3 * c + d) * s3)
                 for a, b, c, d in zip(p0, p1, p2, p3))


def typical_fixes(wps, step_days=2.0):
    """A closed loop of (month, day, lat, lon) waypoints -> (fixes [(days, lat, lon)], t0 unix of the first waypoint in an
    ordinary year). The path is a smooth closed curve through the waypoints; the animal is back where it started after a year."""
    base = _timegm(2001, 1, 1)
    days = []
    for m, d, *_ in wps:
        days.append((_timegm(2001, m, d) - base) / 86400.0)
    d0 = days[0]
    rel = []
    prev = -1.0
    for d in days:
        d = d - d0
        if d <= prev:
            d += 365.0
        rel.append(d)
        prev = d
    rel.append(365.25)
    pts = [(w[2], w[3]) for w in wps]
    n = len(pts)
    out = []
    for i in range(n):
        a, b, c, e = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        d_a, d_b = rel[i], rel[i + 1]
        k = max(1, int(math.ceil((d_b - d_a) / step_days)))
        for j in range(k):
            s = j / float(k)
            la, lo = _catmull(a, b, c, e, s)
            out.append((d_a + (d_b - d_a) * s, la, lo))
    out.append((365.25, pts[0][0], pts[0][1]))
    return out, base + d0 * 86400.0


# ------------------------------------------------------------------ one animal ---
def smooth(fixes, k, gap):
    """A centred moving average of the positions over k fixes, never across a gap longer than `gap` days."""
    if k <= 1 or len(fixes) < 3:
        return [tuple(f) for f in fixes]
    d = np.array([f[0] for f in fixes])
    lat = np.array([f[1] for f in fixes])
    lon = unwrap_lon([f[2] for f in fixes])                  # 179 -> -179 is 2 degrees, not 358
    cut = np.where(np.diff(d) > gap)[0] + 1
    bounds = [0] + list(cut) + [len(d)]
    olat, olon = lat.copy(), lon.copy()
    h = k // 2
    for a, b in zip(bounds[:-1], bounds[1:]):
        for i in range(a, b):
            lo, hi = max(a, i - h), min(b, i + h + 1)
            r = min(i - lo, hi - 1 - i)                      # symmetric window, narrower at the ends
            lo, hi = i - r, i + r + 1
            olat[i], olon[i] = lat[lo:hi].mean(), lon[lo:hi].mean()
    olon = wrap_lon(olon, 0.0)
    return [(float(a), float(b), float(c)) for a, b, c in zip(d, olat, olon)]


class Animal:
    """One animal: its fixes (days since its first, lat, lon), turned into a dense path in LEDs with the distance
    travelled, so that at any moment of the year the head and the length of thread behind it are a lookup."""

    def __init__(self, rec):
        self.id = str(rec["id"])
        self.kind = rec["kind"]
        self.col = np.array(KINDS[self.kind][0], np.float32)
        self.c_core = self.col * 0.2 + 255.0 * 0.8           # the head's light and its halo, shaded once
        self.c_near, self.c_diag, self.c_outer = (shade(self.col, f) for f in (0.88, 0.72, 0.72))
        self.c_wide = shade(self.col, 0.72)
        self.seed = (sum(ord(c) for c in str(rec["id"])) % 628) / 100.0
        self.length, k, self.gap = KINDS[self.kind][1], KINDS[self.kind][2], KINDS[self.kind][3]
        self.gap = float(rec.get("gap") or self.gap)
        self.name = clean_text(rec.get("name"), 18)
        self.species = clean_text(rec.get("species"), 20)
        self.tag = clean_text(rec.get("tag"), 8)
        self.typical = rec.get("src") == "typical"
        self.source = rec.get("src", "")                       # 'typical', 'ocearch' or a source name of the bundled file
        self.period = clean_text(rec.get("period"), 8)
        self.last = rec.get("last")                            # unix time of the newest real ping (live tracks)
        fixes = [tuple(f) for f in rec["fixes"]]
        fixes = smooth(fixes, k if not self.typical else 1, self.gap)
        self.d = np.array([f[0] for f in fixes], np.float64)
        x, y = to_px([f[1] for f in fixes], unwrap_lon([f[2] for f in fixes]))   # interpolate on unwrapped longitude
        self.fx, self.fy = x, y
        self.span = float(self.d[-1])
        self.phase0 = year_phase(rec["t0"])
        # arc length at every fix, and a dense path (a point about every STEP LEDs) for the thread
        seg = np.hypot(np.diff(x), np.diff(y))
        ok = np.diff(self.d) <= self.gap
        self.s = np.concatenate([[0.0], np.cumsum(np.where(ok, seg, 0.0))])
        px, py, ps, sg = [x[0]], [y[0]], [0.0], [0]
        seg_id = 0
        for i in range(len(x) - 1):
            if not ok[i]:
                seg_id += 1
                px.append(x[i + 1]); py.append(y[i + 1]); ps.append(self.s[i + 1]); sg.append(seg_id)
                continue
            n = max(1, int(math.ceil(seg[i] / STEP)))
            for j in range(1, n + 1):
                f = j / float(n)
                px.append(x[i] + (x[i + 1] - x[i]) * f)
                py.append(y[i] + (y[i + 1] - y[i]) * f)
                ps.append(self.s[i] + (self.s[i + 1] - self.s[i]) * f)
                sg.append(seg_id)
        self.px, self.py, self.ps, self.sg = (np.array(a) for a in (px, py, ps, sg))
        self.px = self._wrap_x(self.px)                         # ... and wrap back for drawing
        self.ix, self.iy = np.rint(self.px).astype(np.int32), np.rint(self.py).astype(np.int32)

    @staticmethod
    def _wrap_x(x):
        w = 360.0 * PX
        mid = (-30.5 - LON0) * PX
        return (np.asarray(x, np.float64) - mid + w / 2) % w - w / 2 + mid

    def day_at(self, phase):
        """Days into this animal's recording at a given moment of the calendar year."""
        return ((phase - self.phase0) % 1.0) * YEAR_DAYS

    def head(self, phase):
        """(x, y, index into the dense path) of the head, or None before it starts, after it ends or inside a gap."""
        dd = self.day_at(phase)
        if dd > self.span:
            return None
        k = int(np.searchsorted(self.d, dd, "right")) - 1
        k = min(max(k, 0), len(self.d) - 2)
        if k < 0 or self.d[k + 1] - self.d[k] > self.gap:
            return None
        f = (dd - self.d[k]) / max(1e-9, self.d[k + 1] - self.d[k])
        x = self.fx[k] + (self.fx[k + 1] - self.fx[k]) * f
        y = self.fy[k] + (self.fy[k + 1] - self.fy[k]) * f
        s = self.s[k] + (self.s[k + 1] - self.s[k]) * f
        i = min(int(np.searchsorted(self.ps, s, "right")) - 1, len(self.ps) - 1)
        return float(self._wrap_x(x)), y, max(i, 0)

    def label_lines(self):
        """(name or species, species or id, honesty line)."""
        if self.typical:
            third = "TYPICAL ROUTE"
        elif self.source == "ocearch":
            third = "OCEARCH TRACK"
            if self.last:
                m, d = phase_date(year_phase(self.last))
                third += f" TO {d} {_MONTHS[m]}"
                if time.time() - self.last > OLD_PING:         # an old track says which year it is from
                    third += " " + str(time.gmtime(self.last).tm_year)
        else:
            third = "RECORDED " + self.period if self.period else "RECORDED TRACK"
        if self.name:
            return self.name, self.species, third
        return self.species, ("ID " + self.tag) if self.tag else "", third


def animal_from_asset(rec):
    """A record of assets/migrations/wanderers.json (or the cache) -> Animal, or None when it cannot be used."""
    try:
        if rec.get("kind") not in KINDS or len(rec["fixes"]) < 2:
            return None
        return Animal(rec)
    except Exception as e:
        print(f"[wanderers] skipped {rec.get('id')}: {str(e)[:60]}", flush=True)
        return None


# ------------------------------------------------------------------ OCEARCH, live (cached, never committed) ---
OC_API = "https://www.mapotic.com/api/v1/maps/3413/"
OC_MAX_MOTIONS = 22                      # requests per refresh: polite
OC_KEEP = 12                             # animals kept on the wall
OC_PER_KIND = {"shark": 9, "turtle": 3, "whale": 2}
OC_MIN_FIXES = 15                        # ... and this many pings
OC_MIN_DAYS = 90.0                       # a track needs this many days to be worth replaying


def _http_json(url, timeout=40):
    import requests
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "fortuna-wall/1.0 (art project; viewing only)",
                                                    "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def ocearch_animals(now=None, get=_http_json, pause=1.5, log=True):
    """Read the OCEARCH tracker: the animals that pinged recently in the Atlantic, with the last 12 months of each ->
    [record] in the format of the bundled file (src 'ocearch'). Raises when the feed is unreachable."""
    now = now or time.time()
    cands = parse_ocearch_pois(get(OC_API + "pois.geojson/"), now)
    out, per = [], {}
    asked = 0
    for c in cands:
        if len(out) >= OC_KEEP:
            break
        if per.get(c["kind"], 0) >= OC_PER_KIND.get(c["kind"], 2):
            continue
        if asked >= OC_MAX_MOTIONS:
            break
        asked += 1
        try:
            fixes = parse_ocearch_motion(get(OC_API + f"pois/{c['id']}/motion/with-meta/"))
        except Exception as e:
            if log:
                print(f"[wanderers] {c['name']}: {str(e)[:60]}", flush=True)
            time.sleep(pause)
            continue
        time.sleep(pause)
        win, t0 = year_window(fixes, end=fixes[-1][0] if fixes else None)
        if not win or win[-1][0] < OC_MIN_DAYS:
            continue
        win = thin(win, 0.5)
        if len(win) < OC_MIN_FIXES:
            continue
        out.append({"id": f"oc{c['id']}", "kind": c["kind"], "name": c["name"], "species": short_species(c["species"]),
                    "src": "ocearch", "t0": int(t0), "last": int(fixes[-1][0]), "gap": 30.0,
                    "fixes": [[round(d, 2), round(la, 3), round(lo, 3)] for d, la, lo in win]})
        per[c["kind"]] = per.get(c["kind"], 0) + 1
    return out


def read_cache():
    """The cached OCEARCH animals, or {} when there is none, it is unreadable, or it is older than CACHE_MAX_AGE."""
    try:
        with open(CACHE) as fh:
            rec = json.load(fh)
        if isinstance(rec, dict) and isinstance(rec.get("animals"), list):
            age = time.time() - float(rec.get("t", 0.0) or 0.0)
            if -3600.0 <= age <= CACHE_MAX_AGE:                # a stale (or undated) cache is not shown as current
                return rec
    except Exception:
        pass
    return {}


def write_cache(rec):
    tmp = CACHE + ".tmp"
    try:
        with open(tmp, "w") as fh:
            json.dump(rec, fh, separators=(",", ":"))
        os.replace(tmp, CACHE)
    except Exception as e:
        print(f"[wanderers] cache: {str(e)[:80]}", flush=True)


# ------------------------------------------------------------------ the piece ---
def load_coast():
    try:
        with open(COAST) as fh:
            return json.load(fh).get("rings", [])
    except Exception:
        return []


def bayer(n):
    """An n x n (power of two) Bayer matrix scaled to thresholds in (0, 1): ordered dithering."""
    m = np.zeros((1, 1))
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return ((m + 0.5) / (n * n)).astype(np.float32)


BAYER = np.tile(bayer(16), (H // 16 + 1, W // 16 + 1))[:H, :W]            # one threshold per LED
BAYER2 = np.random.RandomState(7).random_sample((H, W)).astype(np.float32)   # a second, unrelated threshold (white noise)


def shade(col, f):
    """col * f for a wall that shows nothing below ~94: a channel that falls under the floor drops out and the brightest
    channel is held at it (a dimmed gold turns amber, then a dull orange; it never turns to mud)."""
    c = np.asarray(col, np.float32) * f
    top = c.max(axis=-1, keepdims=True)
    return np.where(c >= FLOOR, c, np.where((c >= top) & (top >= 40.0), 100.0, 0.0)).astype(np.float32)


def build_base():
    """The still map, float32 H x W x 3: a dark ocean whose tone is made of dithered specks (denser and bluer-green on the
    shelves, near the coasts), the land as dim slate relief (denser at the coast, thinning inland), a hair-thin coastline,
    a very faint graticule and the dotted equator, a soft vignette."""
    import cv2
    land = np.zeros((H, W), np.uint8)
    rings = []
    for ring in load_coast():
        lat, lon = [p[0] for p in ring], [p[1] for p in ring]
        x, y = to_px(lat, lon)
        pts = np.stack([np.rint(x), np.rint(y)], 1).astype(np.int32)
        rings.append(pts)
    if rings:
        cv2.fillPoly(land, rings, 1)
    sea = (land == 0).astype(np.uint8)
    d_sea = cv2.distanceTransform(sea, cv2.DIST_L2, 3)                   # LEDs from the nearest land, over the sea
    d_land = cv2.distanceTransform(land, cv2.DIST_L2, 3)                 # LEDs from the nearest sea, over the land
    T1 = 0.72 * BAYER + 0.28 * BAYER2                                   # ordered, with a little jitter so sparse specks do not form a lattice

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = 1.0 - 0.55 * np.clip((((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.55) / (H * 0.62)) ** 2) - 0.25, 0, 1.2)
    shelf = np.exp(-d_sea / 7.0)
    dens = (0.012 + 0.075 * shelf + 0.02 * (1.0 - yy / H)) * vig
    teal = BAYER2[::-1, ::-1] < (0.10 + 0.55 * shelf)                                # which kind of speck
    img = np.zeros((H, W, 3), np.float32)
    on = (land == 0) & (T1 < dens)
    img[on & ~teal] = OCEAN_DEEP
    img[on & teal] = OCEAN_SHELF
    # the graticule: a dot every 6 LEDs along every 20 degrees, brighter where lines cross
    for lat in range(-60, 80, 20):
        y = int(round(float(to_px(lat, 0.0)[1])))
        if 0 <= y < H:
            xs = np.arange(1, W, 6)
            ok = (land[y, xs] == 0) & (img[y, xs].max(-1) == 0)
            img[y, xs[ok]] = EQUATOR_COL if lat == 0 else GRAT_COL
    for lon in range(-80, 40, 20):
        x = int(round(float(to_px(0.0, lon)[0])))
        if 0 <= x < W:
            ys = np.arange(1, H, 6)
            ok = (land[ys, x] == 0) & (img[ys, x].max(-1) == 0)
            img[ys[ok], x] = GRAT_COL
    # the land: slate specks, dense at the coast and thinning inland
    ld = (0.035 + 0.30 * np.exp(-d_land / 6.0)) * vig
    img[(land > 0) & (T1 < ld)] = LAND_COL
    # the coastline: one LED wide, three in four lit (ordered), so it reads as a fine thread and not an outline
    edge = (land > 0) & (d_land <= 1.0)
    img[edge & (BAYER2 < 0.86)] = COAST_COL
    return img


class Wanderers:
    def __init__(self, fetch=True, use_cache=True):
        self.base = build_base()
        self.hx, self.hy = (int(round(float(v))) for v in to_px(*HOME))
        self.real, self.live_ok, self.fetched = [], False, 0.0
        self.focus, self.focus_t, self.last_focus = None, -1e9, {}
        self.last_kind = None
        self.last_frame = time.time()
        self.animals = []
        recs = self._bundled()
        cache = read_cache() if use_cache and os.environ.get("WANDERERS_OCEARCH", "1") != "0" else {}
        self.fetched = float(cache.get("t", 0.0) or 0.0)
        self.bundled = recs
        self._assemble(recs, cache.get("animals", []))
        if fetch and os.environ.get("WANDERERS_OCEARCH", "1") != "0":
            threading.Thread(target=self._fetch_loop, args=(recs,), daemon=True).start()

    @staticmethod
    def _bundled():
        try:
            with open(DATA) as fh:
                return json.load(fh).get("animals", [])
        except Exception:
            return []

    def _assemble(self, bundled, live):
        """Real tracks first (the bundled file, then OCEARCH); a typical route only for a kind with no real animal."""
        recs = [dict(r, src=r.get("src") or "recorded") for r in bundled] + [dict(r, src="ocearch") for r in live]
        animals = [a for a in (animal_from_asset(r) for r in recs) if a is not None]
        have = {a.kind for a in animals}
        for tr in TYPICAL:
            if tr["kind"] in have:
                continue
            fixes, t0 = typical_fixes(tr["wps"])
            animals.append(Animal({"id": tr["id"], "kind": tr["kind"], "species": tr["species"], "src": "typical",
                                   "t0": t0, "fixes": fixes}))
        self.animals = animals
        self.has_live = bool(live)

    # ---- live data, on a side thread
    def _fetch_loop(self, bundled):
        wait = max(0.0, self.fetched + EVERY - time.time())
        backoff = 600.0
        while True:
            time.sleep(min(wait, 10.0))
            wait -= 10.0
            if wait > 0:
                continue
            if time.time() - self.last_frame > IDLE:                    # not on the wall: no calls
                wait = 10.0
                continue
            try:
                got = ocearch_animals()
                if got:
                    write_cache({"t": time.time(), "animals": got})
                    self.fetched = time.time()
                    self._assemble(bundled, got)
                wait, backoff = EVERY, 600.0
            except Exception as e:
                print(f"[wanderers] {str(e)[:100]}", flush=True)
                wait, backoff = backoff, min(EVERY, backoff * 2)

    # ---- focus
    def _pick(self, heads, t):
        """The next animal to bring into focus: one in view now that has waited longest, of another kind than the last."""
        cands = [(self.last_focus.get(a.id, -1e9) + (1e6 if a.kind == self.last_kind else 0.0), a.id) for a, *_ in heads]
        if not cands:
            return None
        return min(cands)[1]

    def _update_focus(self, heads, t):
        ids = {a.id for a, *_ in heads}
        if self.focus is not None and (self.focus not in ids or t - self.focus_t > FOCUS_SEC or t < self.focus_t):
            self.last_focus[self.focus] = t
            self.last_kind = next((a.kind for a in self.animals if a.id == self.focus), self.last_kind)
            self.focus = None
        if self.focus is None:
            self.focus = self._pick(heads, t)
            self.focus_t = t

    # ---- one frame
    def draw(self, phase, t, force_focus=None):
        img = self.base.copy()
        heads = []
        for a in self.animals:
            h = a.head(phase)
            if h is None:
                continue
            x, y, i = h
            # the thread: the last `length` LEDs of path behind the head, in the same stretch of the track
            lo = int(np.searchsorted(a.ps, a.ps[i] - a.length, "left"))
            while lo < i and a.sg[lo] != a.sg[i]:
                lo += 1
            idx = np.arange(lo, i + 1)
            if len(idx):
                frac = np.clip((a.ps[i] - a.ps[idx]) / a.length, 0.0, 1.0)
                ix, iy = a.ix[idx], a.iy[idx]
                ok = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
                ix, iy, frac = ix[ok], iy[ok], frac[ok]
                if len(ix):
                    # a comet: full and two LEDs wide at the head, tapering to a sparse dotted hair at the tail. The
                    # level falls with the age along the thread; the density (ordered dither) falls faster, so the
                    # end of the thread dissolves into specks instead of dimming into the dark floor.
                    lvl = 1.0 - (1.0 - TAIL_LO) * frac
                    keep = BAYER[iy, ix] < np.clip(1.25 - 1.15 * frac ** 1.25, 0.0, 1.0)
                    if a.typical:                                    # dotted: a pattern, not a track
                        keep &= (np.floor(a.ps[idx][ok] / 1.6).astype(int) % 2) == 0
                    col = shade(a.col[None, :] * (0.55 + 0.45 * lvl[:, None]), 1.0)
                    kx, ky = ix[keep], iy[keep]
                    img[ky, kx] = np.maximum(img[ky, kx], col[keep])
                    wide = keep & (frac < 0.04) & (not a.typical)
                    if wide.any():                                   # the swelling of the comet's head
                        wcol = a.c_wide
                        for dx, dy in ((1, 0),):
                            wx, wy = ix[wide] + dx, iy[wide] + dy
                            m = (wx < W) & (wy < H)
                            img[wy[m], wx[m]] = np.maximum(img[wy[m], wx[m]], wcol)
            hx, hy = int(round(x)), int(round(y))
            if 0 <= hx < W and 0 <= hy < H:
                heads.append((a, hx, hy))
        if force_focus is not None:
            if force_focus != self.focus:
                self.focus, self.focus_t = force_focus, t
        else:
            self._update_focus(heads, t)
        for a, hx, hy in heads:
            self._head(img, a, hx, hy, t)
        self._home(img, t)
        for a, hx, hy in heads:
            if a.id == self.focus:
                self._label(img, a, hx, hy, t)
        self._corners(img, phase)
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")

    @staticmethod
    def _put(img, x, y, col):
        if 0 <= x < W and 0 <= y < H:
            img[y, x] = np.maximum(img[y, x], col)

    def _head(self, img, a, hx, hy, t):
        """An animal's light: a white-hot core with a halo of graded LEDs (a cross, then its diagonals, then a loose outer
        ring that twinkles on a slow, per-animal beat)."""
        focus = a.id == self.focus
        core, near, diag, outer = a.c_core, a.c_near, a.c_diag, a.c_outer
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self._put(img, hx + dx, hy + dy, near)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            self._put(img, hx + dx, hy + dy, diag)
        beat = 0.5 + 0.5 * math.sin(t * 1.3 + a.seed)
        for k, (dx, dy) in enumerate(((-2, 0), (2, 0), (0, -2), (0, 2))):
            if (k % 2 == 0) == (beat > 0.5) or focus:
                self._put(img, hx + dx, hy + dy, outer)
        self._put(img, hx, hy, core)

    def _home(self, img, t):
        """West Cork: a steady green LED with a soft ring that breathes out and back, and its name, quietly."""
        x, y = self.hx, self.hy
        col = np.array(HOME_COL, np.float32)
        ph = (t / 5.0) % 1.0
        r = 2.0 + 3.0 * ph
        thr = 1.0 - ph                                          # the ring thins out as it grows
        for k in range(16):
            a_ = k * math.pi / 8.0 + 0.3
            px, py = int(round(x + r * math.cos(a_))), int(round(y + r * math.sin(a_)))
            if 0 <= px < W and 0 <= py < H and BAYER[py, px] < thr * 0.9:
                img[py, px] = np.maximum(img[py, px], shade(col, 0.62))
        img[y, x] = col
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self._put(img, x + dx, y + dy, shade(col, 0.42))
        s = "W CORK"
        pixelfont.draw(img, s, x - 7 - pixelfont.width(s), y - 2, shade(col, 0.72))

    @staticmethod
    def _text(img, s, x, y, col, a_in):
        """Text that fades in and out by dissolving: each lit LED of a glyph appears when the ordered-dither threshold under it
        falls below the fade, at the text's full level (so it stays above the wall's floor at every moment)."""
        tmp = np.zeros((7, 4 * len(s) + 1, 3), np.float32)
        pixelfont.draw(tmp, s, 0, 1, col)
        ys, xs = np.nonzero(tmp.any(-1))
        px, py = x + xs, y + ys - 1
        ok = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        ys, xs, px, py = ys[ok], xs[ok], px[ok], py[ok]
        k = BAYER[py, px] < a_in
        img[py[k], px[k]] = np.maximum(img[py[k], px[k]], tmp[ys[k], xs[k]])

    def _label(self, img, a, hx, hy, t):
        lines = [s for s in a.label_lines() if s]
        a_in = min(1.0, max(0.0, (t - self.focus_t) / FADE_SEC), max(0.0, (self.focus_t + FOCUS_SEC - t) / FADE_SEC))
        a_in = a_in * a_in * (3.0 - 2.0 * a_in)                  # eased
        if a_in <= 0.0:
            return
        w = max(pixelfont.width(s) for s in lines)
        h = 6 * len(lines) - 1
        # a dotted ring round the focus, turning slowly
        ring = shade(a.col, 0.75)
        for k in range(12):
            ang = k * math.pi / 6.0 + t * 0.25
            x, y = int(round(hx + 5.0 * math.cos(ang))), int(round(hy + 5.0 * math.sin(ang)))
            if 0 <= x < W and 0 <= y < H and BAYER[y, x] < a_in:
                img[y, x] = np.maximum(img[y, x], ring)
        best, lx, ly = None, None, None
        for dx in (9, -9 - w):                                  # beside the animal, right first
            for dy in (-h // 2, -h - 3, 4, -h - 9, 10):
                x, y = hx + dx, hy + dy
                if x < 3 or x + w > W - 3 or y < 11 or y + h > H - 12:
                    continue
                lit = int((img[max(0, y - 2):y + h + 2, max(0, x - 2):x + w + 2].max(-1) > 0).sum())
                score = lit + (0 if dx > 0 else 6) + abs(dy + h // 2) * 0.5
                if best is None or score < best:
                    best, lx, ly = score, x, y
        if best is None:
            lx = min(max(3, hx + 9), W - 3 - w)
            ly = min(max(11, hy - h // 2), H - 12 - h)
        # thin the picture behind the text (every other LED goes dark) so threads do not run through the letters, then
        # the tidy leader: a dotted line from the ring to the middle of the text's near edge
        x0, x1, y0, y1 = max(0, lx - 2), min(W, lx + w + 2), max(0, ly - 2), min(H, ly + h + 2)
        cut = (BAYER2[y0:y1, x0:x1] < a_in)
        img[y0:y1, x0:x1][cut] = 0.0
        ex = lx - 3 if lx > hx else lx + w + 3
        ey = ly + 2
        n = int(max(abs(ex - hx), abs(ey - hy)))
        lead = shade(a.col, 0.62)
        for k in range(6, n + 1):
            px, py = int(round(hx + (ex - hx) * k / n)), int(round(hy + (ey - hy) * k / n))
            if k % 2 == 0 and 0 <= px < W and 0 <= py < H and BAYER[py, px] < a_in:
                img[py, px] = np.maximum(img[py, px], lead)
        for n_, s in enumerate(lines):
            if n_ == 0:
                col = shade(a.col, 0.86)
            elif n_ == 1:
                col = shade(a.col, 0.66)
            else:
                col = shade(np.array(TEXT_COL, np.float32), 1.0)
            self._text(img, s, lx, ly + 6 * n_, col, a_in)

    def _corners(self, img, phase):
        m, d = phase_date(phase)
        s = f"{_MONTHS[m]} {d}"
        img[1:11, 1:5 + pixelfont.width(s) + 2] = 0.0                  # a clear patch under the small print
        pixelfont.draw(img, s, 4, 4, np.array((168, 178, 226), np.float32))
        if any(a.typical for a in self.animals):
            s = "DOTTED LINES ARE TYPICAL ROUTES"
            x = W - 4 - pixelfont.width(s)
            img[1:11, x - 2:W - 1] = 0.0
            pixelfont.draw(img, s, x, 4, np.array(LEGEND_COL, np.float32))
        # the foot: a dotted year line, a short tick at every month with its initial, the part of the year gone brighter,
        # the date shown as a small lamp and today as a green dot
        y = H - 5
        x0, x1 = 6, W - 7
        img[y - 9:y + 4, 0:W] = 0.0                                    # a clear strip under the calendar
        xp = x0 + int(phase * (x1 - x0))
        base = np.array((0, 0, 118), np.float32)
        past = np.array((0, 104, 186), np.float32)
        for x in range(x0, x1 + 1):
            if x % 2 == 0:
                img[y, x] = np.maximum(img[y, x], past if x <= xp else base)
        day = 0
        for n, ini in zip(_MDAYS, "JFMAMJJASOND"):
            xa = x0 + int(day / 366.0 * (x1 - x0))
            xb = x0 + int((day + n) / 366.0 * (x1 - x0))
            img[y - 1, xa] = np.maximum(img[y - 1, xa], (0, 0, 150))
            cur = xa <= xp < xb
            col = np.array((200, 210, 250) if cur else (104, 112, 160), np.float32)
            pixelfont.draw(img, ini, (xa + xb) // 2 - 1, y - 8, col)
            day += n
        xt = x0 + int(year_phase(time.time()) * (x1 - x0))
        img[y + 2, xt] = HOME_COL
        for dx, dy, f in ((0, 0, 1.0), (-1, 0, 0.6), (1, 0, 0.6), (0, -1, 1.0), (0, 1, 0.6)):
            img[y + dy, xp + dx] = np.maximum(img[y + dy, xp + dx], shade(np.array((235, 240, 255), np.float32), f))

    def __call__(self, t, phase0=None):
        self.last_frame = time.time()
        if self.has_live and self.last_frame - self.fetched > CACHE_MAX_AGE:   # offline for weeks: stop showing it as current
            self._assemble(self.bundled, [])
        p0 = year_phase(time.time()) if phase0 is None else phase0
        return self.draw((p0 + t / YEAR_SEC) % 1.0, t)


_w = None
_t0 = None


def frame(t):
    global _w, _t0
    if _w is None:
        _w = Wanderers()
        _t0 = year_phase(time.time())          # the wall starts at today's date on the calendar
    return _w(t, _t0)


def thumb():
    """A still for the app: mid-May, the terns sweeping back up the Atlantic and one of them in focus; the bundled tracks (and
    whatever OCEARCH last cached), no network."""
    w = Wanderers(fetch=False)
    phase = 134.0 / 365.0
    focus = next((a.id for a in w.animals if a.kind == "tern" and a.head(phase)), None)
    w.focus, w.focus_t = focus, 0.0
    return w.draw(phase, 20.0, force_focus=focus)
