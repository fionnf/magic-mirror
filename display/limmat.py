"""Limmat: the river as live art. Strands of water run down the wall at the speed the Limmat flows
through Zürich right now (FOEN station 2099, Zürich-Unterhard), and the water's colour follows the
lake it comes from (water temperature at Mythenquai): ink blue in winter, teal in summer.

Data, both open and without a key, fetched every 10 minutes on a side thread:
    flow (m3/s)        api.existenz.ch  (FOEN hydrology)
    lake temperature   tecdottir.herokuapp.com  (Wasserschutzpolizei Zürich)
The last values are kept in panel_setup/limmat.json, so the piece starts in the right mood offline.
"""
import json
import math
import os
import threading
import time

import numpy as np
from PIL import Image

import config

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(_HERE, "panel_setup", "limmat.json")
FLOW_URL = "https://api.existenz.ch/apiv1/hydro/latest?locations=2099&parameters=flow&app=fortuna-wall"
TEMP_URL = "https://tecdottir.herokuapp.com/measurements/mythenquai?sort=timestamp_cet%20desc&limit=1"
EVERY = 600
LOW, HIGH = 20.0, 400.0          # m3/s: a dry autumn trickle .. a flood (the mean is ~100)

# the water by temperature (shadow, mid, highlight): neighbouring hues, cold to warm
COLD = ((0.012, 0.035, 0.10), (0.11, 0.30, 0.56), (0.80, 0.90, 1.00))     # ink, slate blue, ice
WARM = ((0.008, 0.07, 0.075), (0.06, 0.46, 0.44), (0.78, 1.00, 0.92))    # deep teal, teal, sea foam


def _load():
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except Exception:
        return {"flow": 90.0, "temp": 12.0, "time": 0}


def fullness(flow):
    """0 (low water) .. 1 (flood), on a log scale: the river's character changes by ratios."""
    return max(0.0, min(1.0, math.log(max(flow, LOW) / LOW) / math.log(HIGH / LOW)))


def colours(temp):
    k = max(0.0, min(1.0, (temp - 5.0) / 18.0))          # 5 C (deep winter) .. 23 C (August)
    return tuple(tuple(c + (w - c) * k for c, w in zip(a, b)) for a, b in zip(COLD, WARM))


class Limmat:
    def __init__(self):
        self.data = _load()
        self.T, self.e, self.last = 0.0, fullness(self.data["flow"]), None
        threading.Thread(target=self._fetch_loop, daemon=True).start()

    def _fetch_loop(self):
        import requests
        while True:
            d = dict(self.data)
            try:
                p = requests.get(FLOW_URL, timeout=15).json()["payload"]
                d["flow"] = float(next(x["val"] for x in p if x["par"] == "flow"))
            except Exception as e:
                print(f"[limmat] flow: {e}", flush=True)
            try:
                r = requests.get(TEMP_URL, timeout=15).json()["result"][0]["values"]
                d["temp"] = float(r["water_temperature"]["value"])
            except Exception as e:
                print(f"[limmat] lake: {e}", flush=True)
            if d != self.data:
                d["time"] = time.time()
                self.data = d
                print(f"[limmat] {d['flow']:.0f} m3/s, lake {d['temp']:.1f} C", flush=True)
                try:
                    with open(CACHE + ".tmp", "w") as fh:
                        json.dump(d, fh)
                    os.replace(CACHE + ".tmp", CACHE)
                except OSError:
                    pass
            time.sleep(EVERY)

    def __call__(self, t):
        from display import shaders
        dt = 0.04 if self.last is None else max(0.0, min(0.2, t - self.last))
        self.last = t
        target = fullness(self.data["flow"])
        self.e += (target - self.e) * min(1.0, dt / 60.0)   # a change in the river eases in over a minute
        self.T += dt * (0.25 + 1.75 * self.e)               # the water's own clock runs with the flow
        r = shaders.renderer()
        if not r.ok:
            return Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        img = r.render("live/limmat", self.T, {"energy": self.e}, colours(self.data["temp"]))
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


_lim = None


def frame(t):
    global _lim
    if _lim is None:
        _lim = Limmat()
    return _lim(t)
