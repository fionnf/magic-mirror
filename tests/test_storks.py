"""Storks of Switzerland: the Movebank parsers (on small SYNTHETIC samples shaped like Movebank's CSV and JSON; the
numbers in them are made up and never shipped), the thinning and stork-year choice, the track helpers, and the piece
(real asset and the typical-routes fallback).

    python3 -m unittest tests.test_storks        (or python3 tests/test_storks.py)
"""
import datetime
import io
import json
import math
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import build_storks as bs
from display import storks, tracks as tk

# The shape of the data repository's gps files: a blank line after every row, NA for a missing fix, quoted names
# with commas in them, the individual name after the sensor columns.
CSV = (
    'event-id,visible,timestamp,location-long,location-lat,algorithm-marked-outlier,manually-marked-outlier,'
    'sensor-type,individual-taxon-canonical-name,tag-local-identifier,individual-local-identifier,study-name\r\n\r\n'
    '1,"true","2013-07-15 11:58:00.000",8.90,47.80,,,"gps","Ciconia ciconia",3030,"Test A (DER XX001)","synthetic"\r\n\r\n'
    '2,"true","2013-07-15 09:15:17.000",8.95,47.81,,,"gps","Ciconia ciconia",3030,"Test A (DER XX001)","synthetic"\r\n\r\n'
    '3,"true","2013-07-16 12:05:00.000",NA,NA,,,"gps","Ciconia ciconia",3030,"Test A (DER XX001)","synthetic"\r\n\r\n'
    '4,"false","2013-07-17 12:00:00.000",9.0,47.9,,,"gps","Ciconia ciconia",3030,"Test A (DER XX001)","synthetic"\r\n\r\n'
    '5,"true","2013-07-18 12:00:00.000",9.1,48.0,true,,"gps","Ciconia ciconia",3030,"Test A (DER XX001)","synthetic"\r\n\r\n'
    '6,"true","2013-07-19 12:00:00.000",9.2,48.1,,true,"gps","Ciconia ciconia",3030,"Test A (DER XX001)","synthetic"\r\n\r\n'
    '7,"true","2013-07-20 12:00:00.000",0.0,0.0,,,"gps","Ciconia ciconia",3030,"Test A (DER XX001)","synthetic"\r\n\r\n'
    '8,"true","2013-07-21 03:00:00.000",9.3,47.7,,,"gps","Ciconia ciconia",3031,"Test B, the second","synthetic"\r\n\r\n'
    '9,"true","2013-07-21 12:30:00.000",9.4,47.6,,,"gps","Ciconia ciconia",3031,"Test B, the second","synthetic"\r\n'
)


class Parsers(unittest.TestCase):
    def test_csv_events(self):
        ev = list(bs.iter_events(io.StringIO(CSV, newline="")))
        names = [e[0] for e in ev]
        # kept: rows 1, 2, 8, 9; dropped: NA, not visible, algorithm outlier, manual outlier, 0/0
        self.assertEqual(len(ev), 4, ev)
        self.assertEqual(names, ["Test A (DER XX001)"] * 2 + ["Test B, the second"] * 2)
        name, o, s, lat, lon = ev[0]
        self.assertEqual(o, datetime.date(2013, 7, 15).toordinal())
        self.assertEqual(s, 11 * 3600 + 58 * 60)
        self.assertAlmostEqual(lat, 47.8)
        self.assertAlmostEqual(lon, 8.9)

    def test_daily_keeps_the_fix_nearest_noon_in_the_window(self):
        d = bs.daily_fixes(bs.iter_events(io.StringIO(CSV, newline="")))
        a = d["Test A (DER XX001)"]
        self.assertEqual(list(a.values()), [(47.8, 8.9)])        # 11:58 beats 09:15
        b = d["Test B, the second"]
        self.assertEqual(list(b.values()), [(47.6, 9.4)])        # 03:00 is outside 09-15 UTC

    def test_json_individuals(self):
        ts = int(datetime.datetime(2020, 9, 1, 12, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)
        obj = {"individuals": [
            {"individual_local_identifier": "J1", "locations": [
                {"timestamp": ts, "location_long": 5.5, "location_lat": 45.5},
                {"timestamp": ts + 86400000, "location_long": 5.6, "location_lat": 44.5},
                {"timestamp": ts + 2 * 86400000},                                     # no position
                {"timestamp": ts + 3 * 86400000, "location_long": 0, "location_lat": 0}]},
            {"individual_local_identifier": "J2", "locations": []}]}
        ev = list(bs.parse_json_individuals(obj))
        self.assertEqual(len(ev), 2)
        self.assertEqual(ev[0][0], "J1")
        self.assertEqual(ev[0][1], datetime.date(2020, 9, 1).toordinal())
        self.assertEqual(ev[0][2], 12 * 3600)
        d = bs.daily_fixes(iter(ev))
        self.assertEqual(sorted(d["J1"].values()), [(44.5, 5.6), (45.5, 5.5)])

    def test_movebank_json_to_asset(self):
        """The public-JSON path end to end on a synthetic study (urlopen replaced; nothing is fetched or shipped)."""
        days = synth_year(2015)
        locs = [{"timestamp": (o - datetime.date(1970, 1, 1).toordinal()) * 86400000 + 12 * 3600 * 1000,
                 "location_lat": p[0], "location_long": p[1]} for o, p in days.items()]
        obj = {"individuals": [{"individual_local_identifier": "synthetic-1", "locations": locs}]}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        real = bs.urllib.request.urlopen
        bs.urllib.request.urlopen = lambda *a, **k: Resp(json.dumps(obj).encode())
        out = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        out.close()
        try:
            bs.movebank("0", [], out=out.name)
            with open(out.name) as fh:
                data = json.load(fh)
        finally:
            bs.urllib.request.urlopen = real
            os.unlink(out.name)
        self.assertEqual(len(data["birds"]), 1)
        self.assertEqual(data["birds"][0]["cls"], "S")
        self.assertEqual(data["birds"][0]["year"], 2015)
        self.assertLess(len(data["birds"][0]["d"]), 150)

    def test_bird_key_joins_studies(self):
        self.assertEqual(bs.bird_key("Karamell (DER AL582)"), bs.bird_key("Karamell + / DER AL582 (eobs3031)"))
        self.assertEqual(bs.bird_key("Maximilian (E0343, e-obs 8032)"), "Maximilian (E0343, e-obs 8032)")


def synth_year(year=2015, leave=40, back=250, stay=(41.5, -1.0), nest=(47.8, 8.9)):
    """A made-up daily track (date ordinal -> (lat, lon)) of a bird that goes to `stay` and returns."""
    start = datetime.date(year, 7, 1).toordinal()
    out = {}
    for k in range(365):
        if k < leave:
            p = nest
        elif k < leave + 20:
            f = (k - leave) / 20.0
            p = (nest[0] + (stay[0] - nest[0]) * f, nest[1] + (stay[1] - nest[1]) * f)
        elif k < back:
            p = stay
        elif k < back + 20:
            f = (k - back) / 20.0
            p = (stay[0] + (nest[0] - stay[0]) * f, stay[1] + (nest[1] - stay[1]) * f)
        else:
            p = nest
        out[start + k] = p
    return out


class Choosing(unittest.TestCase):
    def test_cycle_and_class(self):
        days = synth_year()
        cyc = bs.cycles(days, (47.8, 8.9))
        self.assertTrue(cyc)
        c = bs.best_cycle(cyc, random.Random(1))
        self.assertTrue(c["near"] and c["back"])
        self.assertGreaterEqual(c["span"], bs.FULL_YEAR)
        self.assertEqual(bs.classify(c["w"], (47.8, 8.9)), "S")          # winters in Spain
        africa = synth_year(stay=(14.0, -4.0))
        c = bs.best_cycle(bs.cycles(africa, (47.8, 8.9)), random.Random(1))
        self.assertEqual(bs.classify(c["w"], (47.8, 8.9)), "W")
        home = synth_year(stay=(47.5, 9.0))
        c = bs.best_cycle(bs.cycles(home, (47.8, 8.9)), random.Random(1))
        self.assertEqual(bs.classify(c["w"], (47.8, 8.9)), "R")
        east = synth_year(nest=(52.0, 15.0), stay=(5.0, 33.0))
        c = bs.best_cycle(bs.cycles(east, (52.0, 15.0)), random.Random(1))
        self.assertEqual(bs.classify(c["w"], (52.0, 15.0)), "E")

    def test_short_tracks_are_not_a_stork_year(self):
        days = {datetime.date(2015, 7, 1).toordinal() + k: (47.8, 8.9) for k in range(30)}
        self.assertEqual(bs.cycles(days, (47.8, 8.9)), [])

    def test_thin_keeps_the_journey_and_drops_the_rest(self):
        w = bs.year_window(synth_year(), 2015)
        kept = bs.thin(w)
        self.assertLess(len(kept), len(w) / 2)
        self.assertEqual(kept[0][0], 0)
        self.assertEqual(kept[-1][0], 364)
        ds = [k[0] for k in kept]
        self.assertEqual(ds, sorted(set(ds)))
        self.assertLessEqual(max(b - a for a, b in zip(ds, ds[1:])), bs.MAX_SKIP + 1)
        # rebuilding the track from the kept fixes stays within a third of an LED (~13 km) of the truth
        t = tk.Track([k[0] for k in kept], [k[1] for k in kept], [k[2] for k in kept])
        for k in range(0, 365, 3):
            p = t.pos(k)
            self.assertLess(tk.distance_km(p[0], p[1], *w[k]), 150.0)

    def test_pick_caps(self):
        birds = [{"cls": "W", "span": 360 if i % 2 else 100, "i": i} for i in range(20)]
        got = bs.pick(birds, {"W": 8}, random.Random(3))
        self.assertEqual(len(got), 8)
        self.assertGreaterEqual(sum(1 for b in got if b["span"] >= bs.FULL_YEAR), 6)


class TrackHelpers(unittest.TestCase):
    def test_slerp_ends_and_midpoint(self):
        la, lo = tk.slerp(0, 0, 0, 90, 0.5)
        self.assertAlmostEqual(la, 0, places=6)
        self.assertAlmostEqual(lo, 45, places=6)
        self.assertEqual(tk.slerp(10, 20, 10, 20, 0.3), (10, 20))
        # along the great circle a long hop at 60 N bows north of the straight lat/lon line
        la, _ = tk.slerp(60, -30, 60, 30, 0.5)
        self.assertGreater(la, 60.5)

    def test_distance(self):
        self.assertAlmostEqual(tk.distance_km(0, 0, 0, 1), 111.19, delta=0.1)

    def test_track_pos_and_gaps(self):
        t = tk.Track([0, 1, 2, 20], [47, 46, 45, 10], [8, 8, 8, 8])
        self.assertIsNone(t.pos(-0.1))
        self.assertIsNone(t.pos(20.1))
        self.assertAlmostEqual(t.pos(0.5)[0], 46.5, places=2)
        self.assertEqual(t.pos(20), (10, 8))
        self.assertIsNone(t.pos(10))                              # 18 days and 3900 km with no fix: no made-up flight
        still = tk.Track([0, 15], [47.0, 47.1], [8.0, 8.0])      # long gap, but it only sat there
        self.assertIsNotNone(still.pos(7))

    def test_year_clock_and_months(self):
        c = tk.YearClock(3600, 365, clock=lambda: 1800.0)
        self.assertAlmostEqual(c.day(), 182.5)
        self.assertAlmostEqual(c.day(3600.0 * 5), 0.0)
        self.assertEqual(tk.month_label(0), "JUL")
        self.assertEqual(tk.month_label(31), "AUG")
        self.assertEqual(tk.month_label(364), "JUN")
        self.assertEqual(tk.month_of(0)[1], 1)
        self.assertEqual(len(tk.month_edges()), 12)
        self.assertEqual(tk.month_edges()[-1] + 30, 365)

    def test_projection_roundtrip_and_arrays(self):
        p = tk.Equirect.fit(-24, 50, -30, 58, std_lat=28)
        x, y = p.to_px(47.4, 8.5)
        self.assertTrue(0 < x < tk.W and 0 < y < tk.H)
        xs, ys = p.to_px(np_array([47.4, 0.0]), np_array([8.5, 0.0]))
        self.assertAlmostEqual(xs[0], x)
        self.assertGreater(ys[1], ys[0])

    def test_trails_fade_and_keep_the_brighter(self):
        tr = tk.Trails(20, 10)
        tr.line((1, 1), (8, 1), (200, 0, 0))
        tr.line((4, 0), (4, 3), (50, 0, 0))
        self.assertEqual(tr.buf[1, 4, 0], 200)
        self.assertEqual(tr.buf[2, 4, 0], 50)
        tr.fade(10.0, 10.0)
        self.assertAlmostEqual(float(tr.buf[1, 2, 0]), 200 * math.exp(-1), places=3)
        tr.line((-5, -5), (-2, -2), (255, 255, 255))               # entirely off the image: nothing, no error
        tr.line((18, 8), (30, 30), (255, 255, 255))                # partly off: clipped


def np_array(v):
    import numpy as np
    return np.array(v, np.float64)


class Piece(unittest.TestCase):
    def check(self, s):
        import numpy as np
        for day in (0.2, 40.0, 100.0, 200.0, 364.5):
            heads = s.preroll(day, span=12.0)
            img = s.draw(day, heads)
            self.assertEqual(img.size, (192, 256))
            self.assertEqual(img.mode, "RGB")
            a = np.asarray(img)
            self.assertEqual(a.dtype, np.uint8)
        # the sea is black: whole LEDs only, no soft edges (every lit pixel is a thread, a head, the map or text)
        self.assertGreater(int((np.asarray(s.draw(100.0, s.preroll(100.0))).sum(2) > 0).sum()), 500)

    def test_real_asset(self):
        s = storks.Storks()
        if not s.real:
            self.skipTest("no assets/migrations/storks.json in this checkout")
        self.check(s)
        self.assertIn("REAL", s.caption)
        self.assertNotIn("TYPICAL", s.caption)

    def test_typical_fallback(self):
        s = storks.Storks(recorded=False)
        self.assertFalse(s.real)
        self.assertEqual(s.caption, "TYPICAL ROUTES")
        self.check(s)
        kinds = {t.meta["cls"] for t in s.tracks}
        self.assertEqual(kinds, {"W", "S", "E"})
        for t in s.tracks:                                          # inside the year, strictly increasing
            self.assertTrue(all(b > a for a, b in zip(t.days, t.days[1:])))
            self.assertGreaterEqual(t.start, 0)
            self.assertLess(t.end, 365)

    def test_typical_flyways_make_sense(self):
        s = storks.Storks(recorded=False)
        for t in s.tracks:
            south = min(t.lat)
            if t.meta["cls"] == "S":
                self.assertGreater(south, 38.0)                    # never past Spain
            elif t.meta["cls"] == "W":
                self.assertLess(south, 18.0)                       # into the Sahel
                self.assertLess(max(t.lon), 12.0)                  # by the west
            else:
                self.assertLess(south, 10.0)                       # East Africa
                self.assertGreater(max(t.lon), 28.0)               # by the Bosphorus / Levant
            d_dep = next(d for d, la in zip(t.days, t.lat) if la < t.lat[0] - 2.0)
            self.assertTrue(30 < d_dep < 90, d_dep)                # leaves in August-September
            home = next(d for d, la, lo in zip(t.days, t.lat, t.lon) if d > d_dep + 60 and abs(la - t.lat[0]) < 3 and abs(lo - t.lon[0]) < 4)
            self.assertTrue(215 < home < 330, home)                # back at the nest between mid-February and May
            self.assertGreater(t.end, 360)

    def test_missing_or_broken_asset(self):
        self.assertIsNone(storks.load_recorded("/nonexistent/storks.json"))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"birds": [{"d": [3, 2], "lat": [1, 2], "lon": [1, 2]}]}, fh)      # days not ascending
        try:
            self.assertIsNone(storks.load_recorded(fh.name))
        finally:
            os.unlink(fh.name)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{not json")
        try:
            self.assertIsNone(storks.load_recorded(fh.name))
        finally:
            os.unlink(fh.name)

    def test_frame_and_thumb(self):
        img = storks.frame(0.0)
        self.assertEqual(img.size, (192, 256))
        self.assertEqual(storks.thumb().size, (192, 256))

    def test_missing_map_falls_back(self):
        old = storks.MAP
        storks.MAP = "/nonexistent/map.json"
        try:
            img = storks.base_map()
            self.assertEqual(img.shape, (256, 192, 3))
        finally:
            storks.MAP = old


class Assets(unittest.TestCase):
    def test_storks_json(self):
        path = storks.ASSET
        if not os.path.exists(path):
            self.skipTest("no storks.json")
        self.assertLess(os.path.getsize(path), 300_000)
        with open(path) as fh:
            data = json.load(fh)
        self.assertEqual(data["kind"], "recorded")
        self.assertIn("CC0", data["licence"])
        self.assertTrue(data["source"])
        self.assertGreaterEqual(len(data["birds"]), 20)
        for b in data["birds"]:
            self.assertEqual(len(b["d"]), len(b["lat"]))
            self.assertEqual(len(b["d"]), len(b["lon"]))
            self.assertTrue(all(y > x for x, y in zip(b["d"], b["d"][1:])))
            self.assertTrue(0 <= b["d"][0] and b["d"][-1] <= 365)
            self.assertIn(b["cls"], "WSRE")

    def test_map_json(self):
        if not os.path.exists(storks.MAP):
            self.skipTest("no map")
        self.assertLess(os.path.getsize(storks.MAP), 300_000)


if __name__ == "__main__":
    unittest.main()
