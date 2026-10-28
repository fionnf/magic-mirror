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
    light-level geolocator fixes are only good to a couple of hundred km, so five fixes are averaged).
    Where a tag went quiet for longer than five weeks (the tern geolocators cannot fix a latitude in the Antarctic
    midsummer sun) the light goes out: nothing is drawn across the gap. Shorter gaps (the two equinoxes) are drawn straight.
  * SOLID thread, label "OCEARCH TRACK TO 27 OCT": the last 12 months of an animal on the OCEARCH tracker,
    replayed so that its light reaches its newest real ping exactly when the wall's clock reaches today's
    date on the timeline ("LIVE" while that ping is under a week old).
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
    dataset 767f57dd-bdb8-44cb-bf20-f9aafafa4137), licence CC BY-NC 4.0. It is the tracking behind Egevang et al. (2010),
    "Tracking of Arctic terns Sterna paradisaea reveals longest animal migration", PNAS.
  * Loggerhead and leatherback turtles: OBIS-SEAMAP datasets (Duke North Atlantic Turtle Tracking; Georgia
    Aquarium / DomSeTCO Leatherbacks of Dominica; Gabon leatherback tracking), CC BY-NC 4.0, whose positions are
    given to a one degree cell (about 110 km), so their paths are coarse. Exact citations in the file.
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
Without a network the piece never breaks: it uses the bundled data, whatever the cache last held, and the typical
flyways, in that order.
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
YEAR_DAYS = 365.25
FOCUS_SEC = 45.0                 # one animal in focus for this long
FADE_SEC = 2.5                   # the label fades in and out over this
IDLE = 120.0                     # no frame drawn for this long: the piece is not showing, stop fetching
EVERY = 6 * 3600.0               # OCEARCH is read this often
STEP = 0.7                       # LEDs between samples along a path (so a thread is never broken)
TAIL_LO = 0.42                   # the thread's last LED is this fraction of the head's brightness (the wall shows nothing below ~94)

KINDS = {  # kind: (colour, thread length in LEDs, smoothing window in fixes, longest gap to draw across in days)
    "tern":   ((255, 236, 150), 72.0, 7, 35.0),
    "shark":  ((255, 84, 112), 46.0, 1, 30.0),
    "turtle": ((70, 236, 140), 46.0, 1, 40.0),
    "whale":  ((130, 150, 255), 52.0, 1, 30.0),
}
COAST_COL = (16, 30, 112)
EQUATOR_COL = (12, 24, 100)
HOME_COL = (90, 230, 140)
TEXT_COL = (112, 122, 172)
LEGEND_COL = (96, 108, 156)

_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_MDAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


# ------------------------------------------------------------------ calendar and projection ---
def year_phase(t):
    """Unix time -> how far through its calendar year it is (0 at 1 January 00:00 UTC, up to 1)."""
    tm = time.gmtime(t)
    y0 = _timegm(tm.tm_year, 1, 1)
    y1 = _timegm(tm.tm_year + 1, 1, 1)
    return (t - y0) / float(y1 - y0)


def _timegm(y, m, d):
    import calendar
    return calendar.timegm((y, m, d, 0, 0, 0))


def phase_date(phase):
    """Year phase -> (month index 0-11, day 1-31) of an ordinary year."""
    d = int(max(0.0, min(0.9999, phase)) * 365.0)
    for m, n in enumerate(_MDAYS):
        if d < n:
            return m, d + 1
        d -= n
    return 11, 31


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
        return list(fixes)
    d = np.array([f[0] for f in fixes])
    lat = np.array([f[1] for f in fixes])
    lon = np.array([f[2] for f in fixes])
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
    return [(float(a), float(b), float(c)) for a, b, c in zip(d, olat, olon)]


class Animal:
    """One animal: its fixes (days since its first, lat, lon), turned into a dense path in LEDs with the distance
    travelled, so that at any moment of the year the head and the length of thread behind it are a lookup."""

    def __init__(self, rec):
        self.id = str(rec["id"])
        self.kind = rec["kind"]
        self.col = np.array(KINDS[self.kind][0], np.float32)
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
        x, y = to_px([f[1] for f in fixes], [f[2] for f in fixes])
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
        self.ix, self.iy = np.rint(self.px).astype(np.int32), np.rint(self.py).astype(np.int32)

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
        return x, y, max(i, 0)

    def label_lines(self):
        """(name or species, species or id, honesty line)."""
        if self.typical:
            third = "TYPICAL ROUTE"
        elif self.source == "ocearch":
            third = "OCEARCH TRACK"
            if self.last:
                m, d = phase_date(year_phase(self.last))
                third += f" TO {d} {_MONTHS[m]}"
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
    try:
        with open(CACHE) as fh:
            rec = json.load(fh)
        if isinstance(rec, dict) and isinstance(rec.get("animals"), list):
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


def build_base():
    """The still map: the coast one LED wide, the equator dotted, a mark for West Cork. float32 H x W x 3."""
    import cv2
    img = np.zeros((H, W, 3), np.uint8)
    for ring in load_coast():
        lat, lon = [p[0] for p in ring], [p[1] for p in ring]
        x, y = to_px(lat, lon)
        pts = np.stack([np.rint(x), np.rint(y)], 1).astype(np.int32)
        cv2.polylines(img, [pts], False, COAST_COL, 1, cv2.LINE_8)
    ey = int(round(to_px(0.0, 0.0)[1]))
    for x in range(2, W, 6):                                   # the equator, dotted
        if np.all(img[ey, x] == 0):
            img[ey, x] = EQUATOR_COL
    return img.astype(np.float32)


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
                frac = (a.ps[i] - a.ps[idx]) / a.length
                lvl = 1.0 - (1.0 - TAIL_LO) * np.clip(frac, 0.0, 1.0)
                keep = np.ones(len(idx), bool)
                if a.typical:                                   # dotted: a pattern, not a track
                    keep = (np.floor(a.ps[idx] / 1.6).astype(int) % 2) == 0
                ix, iy = a.ix[idx][keep], a.iy[idx][keep]
                ok = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
                ix, iy, lv = ix[ok], iy[ok], lvl[keep][ok]
                if len(ix):
                    img[iy, ix] = np.maximum(img[iy, ix], a.col[None, :] * lv[:, None])
            hx, hy = int(round(x)), int(round(y))
            if 0 <= hx < W and 0 <= hy < H:
                heads.append((a, hx, hy))
        if force_focus is not None:
            if force_focus != self.focus:
                self.focus, self.focus_t = force_focus, t
        else:
            self._update_focus(heads, t)
        breathe = 0.93 + 0.07 * math.sin(t * 2.0)
        for a, hx, hy in heads:
            img[hy, hx] = (a.col * 0.6 + 255.0 * 0.4) * (breathe if a.id == self.focus else 1.0)
        self._home(img, t)
        for a, hx, hy in heads:
            if a.id == self.focus:
                self._label(img, a, hx, hy, t)
        self._corners(img, phase)
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")

    def _home(self, img, t):
        """West Cork: one steady LED in green with a slow pulse of four dim ones around it, and its name."""
        x, y = self.hx, self.hy
        img[y, x] = HOME_COL
        pulse = 0.5 + 0.5 * math.sin(t * 1.1)
        c = np.array(HOME_COL, np.float32) * (0.45 + 0.4 * pulse)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            img[y + dy, x + dx] = np.maximum(img[y + dy, x + dx], c)
        s = "W CORK"
        pixelfont.draw(img, s, x - 6 - pixelfont.width(s), y - 3, np.array(HOME_COL, np.float32) * 0.62)

    def _label(self, img, a, hx, hy, t):
        lines = [s for s in a.label_lines() if s]
        a_in = min(1.0, max(0.0, (t - self.focus_t) / FADE_SEC), max(0.0, (self.focus_t + FOCUS_SEC - t) / FADE_SEC))
        if a_in <= 0.0:
            return
        w = max(pixelfont.width(s) for s in lines)
        h = 7 * len(lines) - 2
        # the ring round the focus: four dim LEDs a little way off
        ring = a.col * (0.55 * a_in + 0.0)
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            x, y = hx + dx, hy + dy
            if 0 <= x < W and 0 <= y < H:
                img[y, x] = np.maximum(img[y, x], ring)
        best, lx, ly = None, None, None
        for dx in (5, -5 - w, -w // 2):                       # beside the animal, or above or below it: where it hides least
            for dy in (-h // 2, -h - 4, 5, -h - 10, 11):
                x, y = hx + dx, hy + dy
                if x < 2 or x + w > W - 2 or y < 10 or y + h > H - 10:
                    continue
                if dx == -w // 2 and abs(dy) < 5:
                    continue
                lit = int((img[max(0, y - 2):y + h + 1, max(0, x - 2):x + w + 2].max(-1) > 0).sum())
                score = lit + (0 if dx > 0 else 3)
                if best is None or score < best:
                    best, lx, ly = score, x, y
        if best is None:
            lx = min(max(2, hx + 5), W - 2 - w)
            ly = min(max(10, hy - h // 2), H - 10 - h)
        x0, x1, y0, y1 = max(0, lx - 2), min(W, lx + w + 2), max(0, ly - 2), min(H, ly + h + 1)
        img[y0:y1, x0:x1] *= (1.0 - a_in)                    # a dark patch behind the text, so threads do not run through it
        for n, s in enumerate(lines):
            if n == 0:
                col = a.col * 0.92
            elif n == 1:
                col = a.col * 0.66
            else:
                col = np.array(TEXT_COL, np.float32) * 1.15
            m = col.max()
            if m < 135.0:
                col = col * (135.0 / m)                      # the wall shows nothing dim: keep the text above its floor
            pixelfont.draw(img, s, lx, ly + 7 * n, col * a_in)

    def _corners(self, img, phase):
        m, d = phase_date(phase)
        pixelfont.draw(img, f"{_MONTHS[m]} {d}", 3, 3, TEXT_COL)
        if any(a.typical for a in self.animals):
            s = "DOTTED LINES ARE TYPICAL ROUTES"
            pixelfont.draw(img, s, W - 3 - pixelfont.width(s), 3, LEGEND_COL)
        # a timeline along the foot: a tick at every month, the moving mark for the date shown, a green tick for today
        y = H - 4
        x0, x1 = 3, W - 4
        img[y, x0:x1 + 1] = np.maximum(img[y, x0:x1 + 1], (30, 42, 100))
        day = 0
        for n in _MDAYS:
            x = x0 + int(day / 365.0 * (x1 - x0))
            img[y - 1:y + 2, x] = np.maximum(img[y - 1:y + 2, x], (60, 74, 140))
            day += n
        xt = x0 + int(year_phase(time.time()) * (x1 - x0))
        img[y - 2:y + 3, xt] = HOME_COL
        xp = x0 + int(phase * (x1 - x0))
        img[y - 1:y + 2, xp] = (200, 210, 255)

    def __call__(self, t, phase0=None):
        self.last_frame = time.time()
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
