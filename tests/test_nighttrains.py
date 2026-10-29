"""Tests for display/nighttrains.py (Night trains): the live layer on a RECORDED real Transitous answer
(tests/fixtures/nighttrains_transitous.json.gz, the night-train segments of /api/v6/map/trips for the evening of
2026-10-29 plus ten non-night ones), with no network, and the piece itself.

    python3 tests/test_nighttrains.py
"""
import calendar
import gzip
import json
import os
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from display import nighttrains as nt

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "nighttrains_transitous.json.gz")
with gzip.open(FIX) as fh:
    FIXTURE = json.loads(fh.read())
SEGS = FIXTURE["segments"]
NOW = calendar.timegm((2026, 10, 29, 21, 5, 0))          # inside the recorded window
NOCACHE = "/nonexistent_dir/nighttrains_cache.json"      # unreadable and unwritable: no cache in tests


def feed_with_fixture():
    f = nt.LiveFeed(fetch=lambda a, b: (_ for _ in ()).throw(AssertionError("no network in tests")), cache=NOCACHE)
    f.ingest(SEGS, NOW, save=False)
    return f


class TestParsing(unittest.TestCase):
    def test_polyline_known_answer(self):                 # the example from Google's polyline documentation
        la, lo = nt.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 5)
        np.testing.assert_allclose(la, [38.5, 40.7, 43.252], atol=1e-9)
        np.testing.assert_allclose(lo, [-120.2, -120.95, -126.453], atol=1e-9)

    def test_times(self):
        self.assertEqual(nt._unix("2026-10-29T20:05:00Z"), calendar.timegm((2026, 10, 29, 20, 5, 0)))
        self.assertEqual(nt._unix("2026-10-29T22:05:00+02:00"), calendar.timegm((2026, 10, 29, 20, 5, 0)))
        self.assertIsNone(nt._unix("soon"))

    def test_night_detection_on_the_recording(self):
        night = [s for s in SEGS if nt.is_night(s)]
        self.assertGreater(len(night), 100)
        names = {s["trips"][0]["displayName"].split()[0] for s in night}
        self.assertTrue({"NJ", "EN", "ICN"} <= names)
        self.assertEqual(len(SEGS) - len(night), 10)       # the ten negatives are not night trains
        self.assertFalse(nt.is_night({"mode": "COACH", "trips": [{"displayName": "NJ 1"}]}))
        self.assertTrue(nt.is_night({"mode": "LONG_DISTANCE", "trips": [{"displayName": "Caledonian Sleeper"}],
                                     "departure": "2026-10-29T21:00:00Z", "arrival": "2026-10-30T07:00:00Z",
                                     "from": {"lon": 0.0}}))
        self.assertFalse(nt.is_night({"mode": "LONG_DISTANCE", "trips": [{"displayName": "ICE 70"}],
                                      "departure": "2026-10-29T10:00:00Z", "arrival": "2026-10-29T16:00:00Z",
                                      "from": {"lon": 8.0}}))

    def test_tracks_run_forward_in_time_and_carry_delay(self):
        f = feed_with_fixture()
        ts = f.set
        self.assertGreater(ts.n, 50)
        self.assertTrue(np.all(np.diff(ts.TT) >= -1e-6 + 0))
        self.assertTrue(ts.rt.any())
        self.assertTrue(np.isfinite(ts.XX).all() and np.isfinite(ts.DD).all())


class TestPiece(unittest.TestCase):
    def test_live_frame(self):
        p = nt.NightTrains(feed=feed_with_fixture())
        im = p(1.0, NOW)
        self.assertEqual(im.size, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        self.assertEqual(im.mode, "RGB")
        self.assertTrue(p.last["fresh"])
        self.assertGreater(p.last["live"], 30)
        a = np.array(im)
        self.assertGreater(int(np.count_nonzero(a.max(2))), 500)
        lit = a[a.max(2) > 0].max(1)
        self.assertGreaterEqual(int(lit.min()), 8)       # only whole, deliberate LEDs

    def test_no_double_counting(self):
        """The same train arrives from several feeds (NJ 421 / NJ 40421 ...): within 1.5 LEDs it is drawn once, and a
        timetable train with a live twin is not drawn."""
        p = nt.NightTrains(feed=feed_with_fixture())
        p(1.0, NOW)
        live, tt = p.last["live"], p.last["timetable"]
        ts = p.feed.set
        idx = ts.active(NOW)
        x, y, _ = ts.at(idx, np.full(len(idx), NOW))
        moving = int(np.count_nonzero((NOW >= ts.rs[idx]) & (NOW <= ts.re[idx])))
        self.assertLess(live, moving)                       # duplicates and standing trains removed
        bare = nt.NightTrains()
        bare(1.0, NOW)
        self.assertLess(live + tt, live + bare.last["timetable"])

    def test_stale_live_falls_back_to_timetable(self):
        p = nt.NightTrains(feed=feed_with_fixture())
        im = p(1.0, NOW + 3600)
        self.assertFalse(p.last["fresh"])
        self.assertEqual(p.last["live"], 0)
        self.assertGreater(p.last["timetable"], 50)
        self.assertEqual(im.size, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))

    def test_many_times_without_network(self):
        p = nt.NightTrains()
        for h in (0, 3, 6.5, 12, 18, 21):
            im = p(0.5, calendar.timegm((2026, 10, 29, 0, 0, 0)) + h * 3600)
            self.assertEqual(im.size, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))

    def test_counts_only_moving_trains(self):
        p = nt.NightTrains()
        u = calendar.timegm((2026, 10, 29, 2, 0, 0))
        p(1.0, u)
        tt = p.tt
        idx = tt.active(u)
        _, _, _, mv = p._heads(tt, idx, u)
        keys = {tt.keys[i] for i in idx[mv]}
        self.assertEqual(p.last["timetable"], len(keys))   # distinct (service, day), none of them standing
        self.assertLess(p.last["timetable"], len(idx))

    def test_speed(self):
        p = nt.NightTrains(feed=feed_with_fixture())
        p(0.0, NOW)
        t0 = time.time()
        for i in range(30):
            p(i * 0.1, NOW + i)
        self.assertLess((time.time() - t0) / 30, 0.03)

    def test_no_data_state(self):
        old = nt.DATA
        try:
            nt.DATA = tempfile.mkdtemp()
            p = nt.NightTrains()
            im = p(0.0, NOW)
        finally:
            nt.DATA = old
        self.assertTrue(p.error)
        self.assertEqual(im.size, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        self.assertFalse(p.services)
        self.assertEqual(p.last["timetable"], 0)

    def test_timetable_rolls_over_without_blocking(self):
        p = nt.NightTrains()
        d0 = calendar.timegm((2026, 10, 29, 12, 0, 0))
        p(0.0, d0)
        t0 = time.time()
        p(0.0, d0 + 86400)                                  # a new UTC day: the next set is built on a thread
        self.assertLess(time.time() - t0, 0.05)
        for _ in range(100):
            if p.tt_day == int((d0 + 86400) // 86400):
                break
            time.sleep(0.05)
        self.assertEqual(p.tt_day, int((d0 + 86400) // 86400))

    def test_thumb(self):
        self.assertEqual(nt.thumb().size, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))


class TestFeed(unittest.TestCase):
    def test_dead_network_backs_off_and_never_raises(self):
        def dead(a, b):
            raise OSError("network is down")
        f = nt.LiveFeed(fetch=dead, cache=NOCACHE)
        f.poll(1000.0)
        self.assertEqual(f.fail, 1)
        self.assertGreaterEqual(f.next_try, 1000.0 + 60)
        f.poll(f.next_try)
        f.poll(f.next_try)
        self.assertGreater(f.next_try - 1000.0, 200.0)
        self.assertLessEqual(f.next_try - f.ok_time, 1e12)
        p = nt.NightTrains(feed=f)
        p(0.0, NOW)
        self.assertFalse(p.last["fresh"])

    def test_good_poll_resets(self):
        f = nt.LiveFeed(fetch=lambda a, b: SEGS, cache=NOCACHE)
        f.fail = 3
        f.poll(NOW)
        self.assertEqual(f.fail, 0)
        self.assertTrue(f.fresh(NOW))
        self.assertGreaterEqual(f.next_try - NOW, 180.0)

    def test_garbage_answers(self):
        f = nt.LiveFeed(fetch=lambda a, b: [{"mode": "NIGHT_RAIL"}, 5, None, {"mode": "NIGHT_RAIL", "from": {}}], cache=NOCACHE)
        f.poll(NOW)                                         # must not raise
        self.assertEqual(f.set.n, 0)

    def test_cache_round_trip(self):
        path = os.path.join(tempfile.mkdtemp(), "c.json")
        f = nt.LiveFeed(fetch=lambda a, b: SEGS, cache=path)
        f.ingest(SEGS, NOW)
        self.assertTrue(os.path.exists(path))
        g = nt.LiveFeed(cache=path)
        self.assertEqual(g.set.n, f.set.n)
        self.assertEqual(g.ok_time, NOW)
        with open(path, "w") as fh:
            fh.write("{ not json")
        self.assertEqual(nt.LiveFeed(cache=path).set.n, 0)  # a broken cache is ignored

    def test_thread_stops_when_idle(self):
        f = nt.LiveFeed(fetch=lambda a, b: [], cache=NOCACHE)
        f.last_draw = time.time() - 500
        done = threading.Event()
        threading.Thread(target=lambda: (f._run(), done.set()), daemon=True).start()
        self.assertTrue(done.wait(3.0))


if __name__ == "__main__":
    unittest.main()
