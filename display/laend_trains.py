"""Live trains on the Ländle map: the S2 (Schorndorf - Waiblingen - Stuttgart), the S3 (Waiblingen - Winnenden -
Backnang) and the regional trains (MEX 13/19, RE 90...) in the Remstal and the Murr valley, moving on the real track.

Data: the VVS departure monitor (EFA, www3.vvs.de, open, no key), polled every minute on a side thread for
11 stations along the two lines. Every departure there says "this trip is at this station at this (real,
delay-corrected) time". The same trip shows up at several stations, so between two stations a train is placed
by interpolating those times along the track; beyond its first or last station it carries on at line speed, off
the edge of the map. The track is the OpenStreetMap railway of assets/maps/laend.npz (a shortest path through its
graph from station to station). Nothing here needs a key; offline, the map just has no trains and says so.

Each train is a bright head with a short fading tail in its line's colour; S2 red, S3 orange, regional blue.
"""
import datetime
import heapq
import math
import threading
import time

import numpy as np

import config
from display import pixelfont

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
URL = "https://www3.vvs.de/mngvvs/XML_DM_REQUEST"
EVERY = 60.0
IDLE = 120.0                                   # no frame for this long: stop fetching
SPEED = 0.2                                    # LEDs per second beyond a train's known stations (~80 km/h at 107 m a LED)
REMS = ["Waiblingen", "Rommelshausen", "Stetten-Beinstein", "Endersbach", "Beutelsbach", "Grunbach", "Geradstetten",
        "Winterbach", "Weiler (Rems)", "Schorndorf"]
MURR = ["Waiblingen", "Neustadt-Hohenacker", "Nellmersbach", "Winnenden", "Maubach", "Backnang"]
POLL = ["Waiblingen", "Rommelshausen", "Endersbach", "Beutelsbach", "Grunbach", "Winterbach", "Schorndorf",
        "Neustadt-Hohenacker", "Nellmersbach", "Winnenden", "Backnang"]
EAST = ("Schorndorf", "Aalen", "Plüderhausen", "Urbach", "Lorch", "Welzheim", "Rudersberg", "Göppingen")
NORTH = ("Backnang", "Murrhardt", "Crailsheim", "Schwäbisch", "Sulzbach")
COLOURS = {"S2": (255, 70, 80), "S3": (255, 160, 40)}
REGIONAL = (110, 190, 255)


def _ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


class Rail:
    """The track as a graph, and the two corridors (polyline + the distance of each station along it)."""

    def __init__(self, meta):
        self.adj, self.xy = {}, {}
        for r in meta["rails"]:
            pts = [(round(p[0] * 2) / 2, round(p[1] * 2) / 2) for p in r["pts"]]
            for a, b in zip(pts, pts[1:]):
                if a == b:
                    continue
                d = math.hypot(a[0] - b[0], a[1] - b[1])
                self.adj.setdefault(a, []).append((b, d))
                self.adj.setdefault(b, []).append((a, d))
        self.nodes = list(self.adj)
        self.arr = np.array(self.nodes, np.float32)
        self.st = {s["name"]: tuple(s["xy"]) for s in meta["stations"]}
        self.corr = {"rems": self._corridor(REMS, "x1"), "murr": self._corridor(MURR, "top")}

    def snap(self, xy):
        d = np.hypot(self.arr[:, 0] - xy[0], self.arr[:, 1] - xy[1])
        return self.nodes[int(d.argmin())]

    def path(self, a, b=None, goal=None):
        """Shortest path a -> b (nodes), or a -> the nearest node for which goal(node) is true."""
        dist, prev, h = {a: 0.0}, {}, [(0.0, a)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist.get(u, 1e18):
                continue
            if (b is not None and u == b) or (goal is not None and goal(u)):
                out = [u]
                while out[-1] != a:
                    out.append(prev[out[-1]])
                return out[::-1]
            for v, w in self.adj[u]:
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(h, (nd, v))
        return [a]

    def _corridor(self, names, far):
        way = [self.snap(self.st[n]) for n in names if n in self.st]
        edge_w = self.path(way[0], goal=lambda n: n[0] <= 1.5)[::-1]                   # west to the map's edge, then onwards
        if far == "x1":
            edge_e = self.path(way[-1], goal=lambda n: n[0] >= W - 3)
        else:
            edge_e = self.path(way[-1], goal=lambda n: n[1] <= 2 or n[0] >= W - 3)
        pts = list(edge_w)                                                              # edge ... first station
        if pts[-1] != way[0]:
            pts.append(way[0])
        for k in range(1, len(way)):
            pts += self.path(way[k - 1], way[k])[1:]
        pts += edge_e[1:]
        pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        arr = np.array(pts, np.float32)
        seglen = np.hypot(*np.diff(arr, axis=0).T)
        cum = np.concatenate([[0.0], np.cumsum(seglen)])
        pos = {}
        for n in names:
            if n in self.st:
                d = np.hypot(arr[:, 0] - self.st[n][0], arr[:, 1] - self.st[n][1])
                pos[n] = float(cum[int(d.argmin())])
        return {"pts": arr, "cum": cum, "pos": pos, "len": float(cum[-1])}

    def at(self, corr, s):
        c = self.corr[corr]
        s = min(max(s, 0.0), c["len"])
        return float(np.interp(s, c["cum"], c["pts"][:, 0])), float(np.interp(s, c["cum"], c["pts"][:, 1]))


class Trains:
    def __init__(self, meta, fetch=True):
        self.rail = Rail(meta)
        self.trips = {}
        self.last_frame = time.time()
        self.ok_at = 0.0
        self.error = ""
        if fetch:
            threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------ data ---
    def _loop(self):
        import requests
        while True:
            if time.time() - self.last_frame > IDLE:
                time.sleep(5)
                continue
            got = 0
            for name in POLL:
                try:
                    r = requests.get(URL, params=dict(outputFormat="rapidJSON", coordOutputFormat="WGS84[dd.ddddd]", language="de", type_dm="stop",
                                                      name_dm=name, mode="direct", useRealtime=1, limit=14, itdDateTimeDepArr="dep"),
                                     headers={"User-Agent": "fortuna-wall/1.0 (private art project)"}, timeout=20)
                    self.ingest(name, r.json())
                    got += 1
                except Exception as e:
                    self.error = f"{name}: {e}"
                time.sleep(0.4)
            if got:
                self.ok_at = time.time()
                print(f"[laend] {got}/{len(POLL)} stations, {len(self.trips)} trips", flush=True)
            time.sleep(EVERY)

    def ingest(self, station, data):
        for e in data.get("stopEvents", []):
            tr = e.get("transportation", {})
            if tr.get("product", {}).get("class") not in (0, 1):
                continue
            planned = e.get("departureTimePlanned")
            if not planned:
                continue
            est = e.get("departureTimeEstimated") or planned
            dest = tr.get("destination", {}).get("name", "")
            key = f"{tr.get('number')}|{tr.get('properties', {}).get('tripCode')}|{dest}"
            trip = self.trips.setdefault(key, {"line": tr.get("number", ""), "dest": dest, "obs": {}})
            trip["obs"][station] = (_ts(est), (_ts(est) - _ts(planned)) / 60.0)
        cut = time.time() - 1800
        for k in [k for k, t in self.trips.items() if max(v[0] for v in t["obs"].values()) < cut]:
            del self.trips[k]

    # --------------------------------------------------------- placing ---
    def place(self, trip, now):
        """-> (corridor, s, direction) for a trip, or None when it is not on the map now."""
        rail = self.rail
        rems = [n for n in trip["obs"] if n in REMS and n != "Waiblingen"]
        murr = [n for n in trip["obs"] if n in MURR and n != "Waiblingen"]
        d = trip["dest"]
        if murr and not rems:
            corr = "murr"
        elif rems and not murr:
            corr = "rems"
        elif d.startswith(("Backnang", "Murrhardt", "Vaihingen")) and not rems:
            corr = "murr"
        else:
            corr = "rems"
        pos = rail.corr[corr]["pos"]
        obs = sorted((t[0], pos[n]) for n, t in trip["obs"].items() if n in pos)
        if not obs:
            return None
        if len(obs) >= 2:                                           # the times must run along the line one way; if the feed
            ss = [o[1] for o in obs]                                #   contradicts itself, trust only the stop nearest to now
            if not (all(x < y for x, y in zip(ss, ss[1:])) or all(x > y for x, y in zip(ss, ss[1:]))):
                obs = [min(obs, key=lambda o: abs(o[0] - now))]
        if len(obs) >= 2:
            dr = 1 if obs[-1][1] > obs[0][1] else -1
        elif corr == "rems":
            dr = 1 if d.startswith(EAST) else -1
        else:
            dr = 1 if d.startswith(NORTH) else -1
            if not d.startswith(NORTH) and trip["line"].startswith("S"):
                dr = -1
        t0, s0 = obs[0]
        t1, s1 = obs[-1]
        if now <= t0:
            s = s0 - dr * (t0 - now) * SPEED
            if t0 - now > 420:
                return None
        elif now >= t1:
            s = s1 + dr * (now - t1) * SPEED
            if now - t1 > 420:
                return None
        else:
            s = float(np.interp(now, [o[0] for o in obs], [o[1] for o in obs]))
        L = rail.corr[corr]["len"]
        if s < -4 or s > L + 4:
            return None
        return corr, s, dr

    def __call__(self, out, t):
        self.last_frame = time.time()
        now = time.time()
        n = 0
        for trip in list(self.trips.values()):
            p = self.place(trip, now)
            if p is None:
                continue
            corr, s, dr = p
            col = np.array(COLOURS.get(trip["line"], REGIONAL), np.float32)
            n += 1
            pts = [self.rail.at(corr, s - dr * k * 1.15) for k in range(9)]
            hx, hy = int(round(pts[0][0])), int(round(pts[0][1]))
            for x, y in pts[:6]:                                      # dark halo first, so the train stands out from the busiest hillside
                ix, iy = int(round(x)), int(round(y))
                y0, y1, x0, x1 = max(0, iy - 2), min(H, iy + 3), max(0, ix - 2), min(W, ix + 3)
                out[y0:y1, x0:x1] *= 0.5
            for k, (x, y) in enumerate(pts):
                ix, iy = int(round(x)), int(round(y))
                if 0 <= ix < W and 0 <= iy < H:
                    a = (1.0, 0.95, 0.8, 0.65, 0.5, 0.38, 0.28, 0.2, 0.12)[k]
                    out[iy, ix] = col * a if k else col
            if 0 <= hx + 1 < W and 0 <= hy < H and 0 <= hy + 1 < H and 0 <= hx < W:   # the head is a 2 x 2 hot spot
                out[hy:hy + 2, hx:hx + 2] = np.minimum(255, col * 0.55 + 140)
        live = self.ok_at and now - self.ok_at < 300
        label = f"LIVE {n}" if live else "NO DATA"
        pixelfont.draw(out, label, W - pixelfont.width(label) - 3, H - 8, (60, 220, 110) if live else (110, 110, 130))
