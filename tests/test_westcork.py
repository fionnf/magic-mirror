"""West Cork and West Cork Dusk are one map in two colours: the lights must always be identical in both.

    python3 -m pytest tests/test_westcork.py      (or run the file directly)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from display import westcork as wc  # noqa: E402


def _lit_pixels(img, base):
    """Pixels the lights painted: where the picture is brighter than the map under it."""
    a = np.asarray(img).astype(np.int16)
    return a.max(axis=2) > (base.max(axis=2).astype(np.int16) + 8)


def test_same_lights_in_both_maps():
    plain, dusk = wc.WestCork(False), wc.WestCork(True)
    assert [(l.x, l.y, l.steps, l.fastnet) for l in plain.lights] == [(l.x, l.y, l.steps, l.fastnet) for l in dusk.lights]
    assert len(plain.lights) >= 30, "lights are missing from the view"


def test_lights_look_the_same_at_any_moment():
    plain, dusk = wc.WestCork(False), wc.WestCork(True)
    for now in (1000.0 + k * 0.7 for k in range(40)):
        a, b = np.asarray(plain.render_at(now)).astype(np.int16), np.asarray(dusk.render_at(now)).astype(np.int16)
        for l in plain.lights:                                    # the light's own pixel carries the same colour in both
            va, vb = a[l.y, l.x], b[l.y, l.x]
            lv = l.level(now)
            if lv >= 0.999:                                       # at full power the lamp is exactly the same on both maps
                assert np.array_equal(va, vb), f"{l.name or (l.x, l.y)} differs between the two maps"
            else:                                                 # rising or falling: only the faint land under it shows through
                land_gap = float(np.abs(plain.base[l.y, l.x] - dusk.base[l.y, l.x]).max())
                assert np.abs(va - vb).max() <= land_gap * (1.0 - lv) + 1.0, f"{l.name or (l.x, l.y)} differs between the two maps"


def test_fastnet_beam_is_about_a_second_in_five():
    w = wc.WestCork(False)
    f = [l for l in w.lights if l.fastnet][0]
    levels = np.array([f.level(f.phase * 0 + t - f.phase) for t in np.arange(0, 5, 0.05)])
    assert abs(f.period - 5.0) < 1e-6
    assert 0.8 <= (levels > 0.05).sum() * 0.05 <= 1.1
    assert (levels > 0.99).sum() * 0.05 >= 0.85, "the flash should be at full brightness for nearly all of its second"


def test_every_flash_reaches_full_brightness_on_a_single_led():
    w = wc.WestCork(False)
    for l in w.lights:
        assert max(l.level(l.phase * 0 + k / 200.0 - l.phase) for k in range(int(l.period * 200) + 1)) > 0.99, f"{l.name or (l.x, l.y)} never reaches full brightness"
    now = 1234.5
    img = np.asarray(w.render_at(now)).astype(int)
    for l in w.lights:                                    # a light is its own pixel and nothing around it
        if l.level(now) > 0.99:
            around = np.abs(img[l.y - 1:l.y + 2, l.x - 1:l.x + 2] - w.base[l.y - 1:l.y + 2, l.x - 1:l.x + 2]).max(axis=2)
            assert (around > 2).sum() <= 1 + sum(1 for o in w.lights if o is not l and abs(o.x - l.x) <= 1 and abs(o.y - l.y) <= 1) * 1, "a light grew beyond one LED"


def test_all_in_view_lights_are_on_the_wall():
    w = wc.WestCork(False)
    assert all(0 <= l.x < wc.W and 0 <= l.y < wc.H for l in w.lights)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
