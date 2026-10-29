"""Tram map: shape, every tram on the wall across 26 h, the live-delay path."""
import datetime
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from display import tramlines as T  # noqa: E402


def main():
    m = T._get()
    assert T.thumb().size == (192, 256) and T.frame(0).mode == "RGB"
    day = m.days[3]
    for k in range(0, 26 * 60, 7):
        when = datetime.datetime(day.year, day.month, day.day, tzinfo=T._zone()) + datetime.timedelta(minutes=k)
        img, _ = m.render(when)
        assert img.shape == (256, 192, 3)
        for line, p, pos in m.trams(when):
            leds = m._route(p)[0]
            x, y = leds[min(int(pos + .5), len(leds) - 1)]
            assert 0 <= x < 192 and 0 <= y < 256
    now = datetime.datetime.now(T._zone())
    m.live.delay, m.live.cancelled, m.live.t = {m.tid[0]: 120}, {m.tid[1]}, time.time()
    m.render(now)
    m.live.t = 0
    print("ok")


if __name__ == "__main__":
    main()
