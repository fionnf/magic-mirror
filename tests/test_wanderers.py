"""Tests for display/wanderers.py (Ocean wanderers): the parsers on small SYNTHETIC samples of each data format
(these samples are made up for the test and never shipped as data), the track maths, and the piece itself.

    python3 tests/test_wanderers.py
"""
import calendar
import os
import sys
import time
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from display import wanderers as wd

T0 = calendar.timegm((2008, 1, 1, 0, 0, 0))

GBIF = [  # the shape of /v1/occurrence/search results (synthetic)
    {"organismID": "A_1", "eventDate": "2008-01-03T00:07", "decimalLatitude": -62.9, "decimalLongitude": -15.7},
    {"organismID": "A_1", "eventDate": "2008-01-01T12:16", "decimalLatitude": -61.2, "decimalLongitude": -18.1},
    {"organismID": "B_2", "eventDate": "2015-08-09T21:11:03/2015-08-11T21:11:03", "decimalLatitude": 44.5, "decimalLongitude": -67.5},
    {"organismID": "1;2", "eventDate": "2015-08-09", "decimalLatitude": 44.5, "decimalLongitude": -67.5},      # shared cell: skipped
    {"organismID": "C", "decimalLatitude": 1.0, "decimalLongitude": 2.0},                                       # no date: skipped
    {"organismID": "D", "eventDate": "2015", "decimalLatitude": 1.0, "decimalLongitude": 2.0},                  # year only: skipped
]
MOVEBANK = {"individuals": [{"individual_local_identifier": "x7", "individual_taxon_canonical_name": "Sterna paradisaea",
                             "locations": [{"timestamp": 1214481620999, "location_long": -89.6, "location_lat": -1.3},
                                           {"timestamp": 1214476255999, "location_long": -89.7, "location_lat": -1.4},
                                           {"timestamp": 1214487043001, "location_long": None, "location_lat": -1.4}]},
                            {"individual_local_identifier": "empty", "locations": []}]}
NOW = calendar.timegm((2026, 10, 28, 12, 0, 0))
OC_POIS = {"type": "FeatureCollection", "features": [
    {"geometry": {"type": "Point", "coordinates": [-79.78, 32.21]},
     "properties": {"id": 1, "name": "Testy", "species": "White Shark (Carcharodon carcharias)", "last_move_datetime": "2026-10-27T22:45:16Z"}},
    {"geometry": {"type": "Point", "coordinates": [-79.78, 32.21]},
     "properties": {"id": 2, "name": "Old", "species": "Tiger Shark (Galeocerdo cuvier)", "last_move_datetime": "2018-12-30T10:28:52Z"}},
    {"geometry": {"type": "Point", "coordinates": [150.0, -30.0]},
     "properties": {"id": 3, "name": "Pacific", "species": "White Shark (Carcharodon carcharias)", "last_move_datetime": "2026-10-28T00:34:51.859000Z"}},
    {"geometry": {"type": "Point", "coordinates": [-40.0, 30.0]},
     "properties": {"id": 4, "name": "Seal", "species": "Harbor Seal (Phoca vitulina)", "last_move_datetime": "2026-10-28T00:34:51Z"}},
    {"geometry": {"type": "Point", "coordinates": [-40.0, 30.0]},
     "properties": {"id": 5, "name": "Toño", "species": "Loggerhead Sea Turtle (Caretta caretta)", "last_move_datetime": "2026-10-20T00:00:00Z"}},
]}
OC_MOTION = {"motion": [{"dt_move": "2016-09-23T02:38:57Z", "point": {"type": "Point", "coordinates": [-69.79, 41.31]}},
                        {"dt_move": "2016-09-21T21:32:12Z", "point": {"type": "Point", "coordinates": [-69.87, 41.47]}}]}


def track(n=40, step=3.0, lat0=30.0, lon0=-60.0, t0=T0):
    return [(t0 + i * step * 86400.0, lat0 + 0.3 * i, lon0 + 0.5 * i) for i in range(n)]


class Parsers(unittest.TestCase):
    def test_gbif(self):
        got = wd.parse_gbif_occurrences(GBIF)
        self.assertEqual(sorted(got), ["A_1", "B_2"])
        self.assertEqual([round(f[1], 1) for f in got["A_1"]], [-61.2, -62.9])            # sorted by time
        self.assertEqual(got["B_2"][0][0], calendar.timegm((2015, 8, 10, 21, 11, 3)))    # the middle of a range

    def test_movebank(self):
        got = wd.parse_movebank_json(MOVEBANK)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["id"], "x7")
        self.assertEqual(len(got[0]["fixes"]), 2)                                         # the fix without a position is dropped
        self.assertAlmostEqual(got[0]["fixes"][0][0], 1214476255.999, 2)
        self.assertEqual(got[0]["fixes"][0][1:], (-1.4, -89.7))

    def test_ocearch_pois(self):
        got = wd.parse_ocearch_pois(OC_POIS, NOW)
        self.assertEqual([g["name"] for g in got], ["Testy", "Toño"])                     # newest first; old, Pacific, seal dropped
        self.assertEqual([g["kind"] for g in got], ["shark", "turtle"])
        self.assertEqual(wd.ocearch_kind("Whale Shark (Rhincodon typus)"), "shark")
        self.assertEqual(wd.ocearch_kind("Pilot Whales (Globicephala species)"), "whale")
        self.assertIsNone(wd.ocearch_kind("American alligator"))

    def test_ocearch_motion(self):
        got = wd.parse_ocearch_motion(OC_MOTION)
        self.assertEqual([round(f[2], 2) for f in got], [-69.87, -69.79])                 # GeoJSON is lon, lat; sorted by time
        self.assertEqual(round(got[0][1], 2), 41.47)

    def test_text(self):
        self.assertEqual(wd.clean_text("Toño & Mary-Lee"), "TONO MARY-LEE")
        self.assertEqual(wd.short_species("Shortfin Mako Shark (Isurus oxyrinchus)"), "MAKO SHARK")
        self.assertEqual(wd.short_species("Loggerhead Sea Turtle (Caretta caretta)"), "LOGGERHEAD TURTLE")


class Tracks(unittest.TestCase):
    def test_window_live_ends_at_last_ping(self):
        fixes = track(200, 3.0)                                                           # 600 days
        win, t0 = wd.year_window(fixes, end=fixes[-1][0])
        self.assertLessEqual(win[-1][0], 365.0)
        self.assertEqual(round(t0 + win[-1][0] * 86400.0), round(fixes[-1][0]))

    def test_window_archive_picks_the_busiest_year(self):
        a = track(10, 30.0)                                                               # sparse
        b = track(100, 2.0, t0=T0 + 900 * 86400.0)                                         # dense, later
        win, t0 = wd.year_window(a + b)
        self.assertAlmostEqual(t0, b[0][0])
        self.assertEqual(len(win), 100)

    def test_thin(self):
        f = [(i * 0.1, 0.0, 0.0) for i in range(100)]
        self.assertLess(len(wd.thin(f, 1.0)), 15)
        self.assertEqual(wd.thin(f, 1.0)[-1], f[-1])

    def test_smooth_stays_inside_gaps(self):
        f = [(0, 0.0, 0.0), (1, 0.0, 0.0), (2, 0.0, 0.0), (60, 10.0, 10.0), (61, 10.0, 10.0), (62, 10.0, 10.0)]
        s = wd.smooth(f, 3, gap=10)
        self.assertAlmostEqual(s[2][1], 0.0)                                              # the far side of the gap does not pull it
        self.assertAlmostEqual(s[3][1], 10.0)

    def test_typical_route_is_a_closed_loop(self):
        for tr in wd.TYPICAL:
            fixes, t0 = wd.typical_fixes(tr["wps"])
            self.assertAlmostEqual(fixes[0][1], fixes[-1][1])
            self.assertAlmostEqual(fixes[0][2], fixes[-1][2])
            self.assertAlmostEqual(fixes[-1][0], 365.25)
            self.assertTrue(all(b[0] > a[0] for a, b in zip(fixes, fixes[1:])))           # time only goes forward

    def test_year_phase(self):
        self.assertAlmostEqual(wd.year_phase(calendar.timegm((2026, 1, 1, 0, 0, 0))), 0.0)
        self.assertAlmostEqual(wd.year_phase(calendar.timegm((2026, 7, 2, 12, 0, 0))), 0.5, 2)
        self.assertEqual(wd.phase_date(0.0), (0, 1))
        self.assertEqual(wd.phase_date(300 / 366.0), (9, 27))

    def test_phase_date_roundtrips_in_leap_and_common_years(self):
        for y in (2026, 2027, 2028, 2100):
            for m in range(1, 13):
                for d in (1, 15, 28):
                    got = wd.phase_date(wd.year_phase(calendar.timegm((y, m, d, 12, 0, 0))))
                    self.assertEqual(got, (m - 1, d), (y, m, d))
        self.assertEqual(wd.phase_date(wd.year_phase(calendar.timegm((2028, 3, 1, 12, 0, 0)))), (2, 1))
        self.assertEqual(wd.phase_date(wd.year_phase(calendar.timegm((2028, 2, 29, 12, 0, 0)))), (1, 29))
        self.assertEqual(wd.phase_date(wd.year_phase(calendar.timegm((2028, 12, 31, 23, 59, 0)))), (11, 31))

    def test_smooth_across_the_antimeridian(self):
        f = [(i, 0.0, lon) for i, lon in enumerate([176.0, 178.0, 179.0, -179.0, -178.0])]
        s = wd.smooth(f, 3, gap=10)
        self.assertAlmostEqual(abs(((s[2][2] - 179.0) + 180) % 360 - 180), 0.33, 1)       # raw averaging would give 59
        for a, b in zip(s, s[1:]):
            self.assertLess(abs(((b[2] - a[2]) + 180) % 360 - 180), 3.5)

    def test_animal_crosses_the_antimeridian_the_short_way(self):
        a = wd.Animal(rec(kind="shark", fixes=[[0, 10, 178.0], [5, 10, 179.5], [10, 10, -179.0], [15, 10, -177.0]]))
        self.assertLess(np.abs(np.diff(a.fx)).max(), 20.0 * wd.PX)                        # no leap through the Atlantic
        self.assertLess(np.abs(np.diff(a.px)).max(), 2.0)                                 # the dense path is one smooth line
        # a track that comes into view from the east across 180 is continuous at the view's edge
        b = wd.Animal(rec(kind="shark", fixes=[[0, 10, 170.0], [15, 10, -170.0], [30, 10, -150.0]]))
        self.assertLess(np.abs(np.diff(b.px)).max(), 2.0)


def rec(**kw):
    d = {"id": "t1", "kind": "tern", "species": "ARCTIC TERN", "src": "recorded", "period": "2008", "t0": T0, "gap": 20.0,
         "fixes": [[i * 3.0, 30.0 + 0.3 * i, -60.0 + 0.5 * i] for i in range(40)]}
    d.update(kw)
    return d


class Piece(unittest.TestCase):
    def setUp(self):
        self._data, self._cache = wd.DATA, wd.CACHE
        wd.CACHE = "/nonexistent/wanderers_cache.json"

    def tearDown(self):
        wd.DATA, wd.CACHE = self._data, self._cache

    def test_animal_head_and_gap(self):
        a = wd.Animal(rec(fixes=[[0, 10, -50], [5, 10, -45], [60, 10, -40], [65, 10, -35]]))
        p0 = a.phase0
        self.assertIsNotNone(a.head(p0 + 2.0 / wd.YEAR_DAYS))
        self.assertIsNone(a.head(p0 + 30.0 / wd.YEAR_DAYS))                                # inside a gap longer than 20 days: dark
        self.assertIsNone(a.head(p0 + 200.0 / wd.YEAR_DAYS))                               # after the track ends
        x, y, _ = a.head(p0 + 2.5 / wd.YEAR_DAYS)
        self.assertAlmostEqual(x, (-47.5 - wd.LON0) * wd.PX, 3)

    def test_labels_say_what_each_thing_is(self):
        self.assertEqual(wd.Animal(rec()).label_lines(), ("ARCTIC TERN", "", "RECORDED 2008"))
        oc = wd.Animal(rec(src="ocearch", name="Mary Lee", species="WHITE SHARK", last=NOW, kind="shark"))
        old = wd.Animal(rec(src="ocearch", name="Mary Lee", species="WHITE SHARK", last=time.time() - 100 * 86400.0, kind="shark"))
        self.assertRegex(old.label_lines()[2], r"^OCEARCH TRACK TO \d+ [A-Z]{3} 20\d\d$")                # an old track names its year
        fresh = wd.Animal(rec(src="ocearch", name="Mary Lee", species="WHITE SHARK", last=time.time() - 86400.0, kind="shark"))
        self.assertNotRegex(fresh.label_lines()[2], r"20\d\d")
        self.assertNotIn("LIVE", fresh.label_lines()[2])
        fixes, t0 = wd.typical_fixes(wd.TYPICAL[1]["wps"])
        ty = wd.Animal({"id": "T", "kind": "shark", "species": "WHITE SHARK", "src": "typical", "t0": t0, "fixes": fixes})
        self.assertEqual(ty.label_lines()[2], "TYPICAL ROUTE")

    def test_stale_cache_is_ignored(self):
        import json
        import tempfile
        d = tempfile.mkdtemp()
        wd.CACHE = os.path.join(d, "c.json")
        for age, expect in ((2 * 86400.0, True), (30 * 86400.0, False), (200 * 86400.0, False)):
            with open(wd.CACHE, "w") as fh:
                json.dump({"t": time.time() - age, "animals": [rec()]}, fh)
            self.assertEqual(bool(wd.read_cache()), expect, age)
        with open(wd.CACHE, "w") as fh:
            json.dump({"animals": [rec()]}, fh)                                               # undated: not trusted
        self.assertEqual(wd.read_cache(), {})

    def test_without_any_data_it_shows_typical_routes(self):
        wd.DATA = "/nonexistent/wanderers.json"
        w = wd.Wanderers(fetch=False, use_cache=False)
        self.assertTrue(w.animals and all(a.typical for a in w.animals))
        self.assertEqual({a.kind for a in w.animals}, {"tern", "shark", "whale"})
        img = w(100.0, 0.5)
        self.assertEqual(img.size, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))

    def test_real_tracks_replace_typical_ones_of_their_kind(self):
        w = wd.Wanderers(fetch=False, use_cache=False)
        kinds_real = {a.kind for a in w.animals if not a.typical}
        kinds_typ = {a.kind for a in w.animals if a.typical}
        self.assertFalse(kinds_real & kinds_typ)
        if os.path.exists(wd.DATA):
            self.assertIn("tern", kinds_real)

    def test_frames_at_many_times(self):
        w = wd.Wanderers(fetch=False, use_cache=False)
        worst = 0.0
        for i in range(200):
            t0 = time.time()
            img = w(i * 17.3, 0.123)
            worst = max(worst, time.time() - t0)
            self.assertIsInstance(img, Image.Image)
            self.assertEqual(img.mode, "RGB")
            self.assertEqual(img.size, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        self.assertLess(worst, 0.02)                                                      # under 20 ms a frame

    def test_whole_leds_on_black(self):
        w = wd.Wanderers(fetch=False, use_cache=False)
        a = np.asarray(w(500.0, 0.6))
        lit = a.max(-1) > 0
        self.assertTrue(0.002 < lit.mean() < 0.15)                                         # dim map, a few lights: mostly black

    def test_thumb(self):
        wd.DATA = self._data
        img = wd.thumb()
        self.assertEqual(img.size, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        self.assertGreater(np.asarray(img).max(), 200)

    def test_focus_rotates(self):
        w = wd.Wanderers(fetch=False, use_cache=False)
        seen = set()
        for i in range(0, 4000, 5):
            w.draw(0.62, float(i))
            seen.add(w.focus)
        self.assertGreater(len(seen), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
