"""Storks of Switzerland: white storks' year on the wall. One lit LED per bird, each trailing a long thread that
fades over a few minutes, over a dim outline of Europe and Africa. A whole year is played in an hour (the wall clock
decides where in the year it is, so it is the same year wherever you join it): the birds leave in August and
September, the western ones by Spain and Gibraltar into Mali and Senegal, the eastern ones by the Bosphorus and the
Levant into Sudan and East Africa, some only as far as Spain; and in March and April the survivors come home.
A small calendar in the corner (JUL ... JUN) says which month it is.

What it shows, and what it does not (the wall says so too, in the corner):

  * REAL TRACKS when assets/migrations/storks.json exists (tools/build_storks.py makes it). Those are GPS tags on
    white storks (Movebank Data Repository, CC0, the LifeTrack projects of the Max Planck Institute of Animal
    Behavior and the 2015 'eight populations' study; sources and licence are written inside the file). Each dot is
    one real bird in one real year of its life, placed on the day of the year it was there; different birds are
    different years (2013-2023), shown together on one calendar. They are NOT Swiss birds: none of these open data
    were tagged in a Swiss nest. The western ones were tagged as nestlings at Lake Constance, the Upper Rhine, Upper
    Swabia and the Vorarlberg Rhine valley (the Swiss border, 30-150 km from Zurich), the eastern ones in Poland,
    Russia and Greece. Birds whose tag stopped (a dead or lost tag - the data do not say) simply go out.
    Amber dots spent the winter in Spain/Portugal (or never left central Europe); red ones went on into Africa by the
    western route (or over the central Mediterranean); blue ones took the eastern route. A dot shines brightest while
    its bird is flying, a little less while it rests.
  * TYPICAL ROUTES without it: hand-authored flyways (waypoints through the Rhone valley, the Ebro, Gibraltar and
    the Sahara; through Hungary, the Bosphorus, the Levant and the Nile) with made-up individual variation in dates
    and paths. Nothing here is a bird. The wall says TYPICAL ROUTES, not REAL.

Between the daily fixes a bird moves along the great circle; where the tag recorded nothing for more than a week and
the bird would have had to cross hundreds of km, the dot is not drawn at all (no made-up flight). Everything is drawn
on whole LEDs: single lit LEDs on black, no anti-aliasing. Nothing is fetched at run time (the tracks are history,
bundled), so a missing network changes nothing. The map is assets/migrations/storks_map.json (Natural Earth, public
domain), or the Europe outline of assets/maps/europe.json if that is missing.

Per frame: fade one float image, add one short line per moving bird, merge over the map: well under 2 ms.
"""
import os
import random

import numpy as np

import config
from display import pixelfont
from display import tracks as tk

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
PERIOD = 3600.0                      # seconds a whole year takes on the wall
DAYS = 365
START_MONTH = 7                      # the cycle starts on 1 July: the young are in the nest, the autumn still ahead
TAU = 95.0                           # seconds for a thread to fall to 1/e (about 10 days of the storks' year)
ASSET = tk.asset_path("migrations", "storks.json")
MAP = tk.asset_path("migrations", "storks_map.json")
EUROPE = tk.asset_path("maps", "europe.json")

# the colours: deep ones that keep a channel well above the LED floor
COL = {"W": np.array([255, 62, 40], np.float32),       # western flyway, on into Africa
       "S": np.array([255, 178, 30], np.float32),      # stayed the winter in Spain or north of the Alps
       "R": np.array([255, 178, 30], np.float32),
       "E": np.array([40, 160, 255], np.float32)}      # eastern flyway
COAST, LAKE, BORDER, HOME = (20, 32, 50), (12, 22, 38), (46, 34, 40), (95, 95, 110)
TEXT, TEXT_DIM, CAL_ON, CAL_OFF = (130, 130, 150), (70, 70, 88), (150, 150, 175), (26, 26, 36)
ZURICH = (47.3769, 8.5417)

PROJ = tk.Equirect.fit(-24.0, 50.0, -29.5, 58.0, std_lat=28.0)


# ---- typical flyways (used only when there is no recorded data) ----------------------------------------------

# waypoints (lat, lon, days from the one before) south-bound, from the nest to the wintering ground
WEST = [(47.6, 8.9, 0), (46.4, 6.4, 3), (44.9, 4.8, 3), (43.4, 2.0, 3), (42.2, -1.4, 3), (40.2, -3.8, 4),
        (38.2, -5.2, 4), (36.1, -5.7, 3), (33.9, -6.2, 3), (30.4, -7.6, 5), (26.0, -8.3, 6), (21.0, -7.0, 6),
        (16.4, -5.2, 7), (14.5, -4.5, 4)]
WEST_SENEGAL = [(47.6, 8.9, 0), (46.4, 6.4, 3), (44.9, 4.8, 3), (43.4, 2.0, 3), (42.2, -1.4, 3), (40.2, -3.8, 4),
                (38.2, -5.2, 4), (36.1, -5.7, 3), (33.9, -6.8, 3), (29.5, -9.8, 5), (24.5, -13.5, 6), (19.5, -15.8, 6),
                (16.2, -15.6, 4)]
SPAIN = [(47.6, 8.9, 0), (46.4, 6.4, 3), (44.9, 4.8, 3), (43.4, 2.0, 3), (41.8, -0.9, 4)]
SPAIN_WEST = [(47.6, 8.9, 0), (46.4, 6.4, 3), (44.9, 4.8, 3), (43.4, 1.0, 3), (41.3, -3.2, 4), (39.6, -4.0, 3)]
EAST = [(51.8, 15.2, 0), (49.6, 17.8, 3), (47.4, 19.4, 3), (44.6, 22.2, 4), (42.1, 26.2, 4), (41.1, 29.0, 3),
        (38.4, 31.2, 4), (36.4, 36.1, 4), (33.3, 35.6, 4), (30.2, 32.4, 4), (26.2, 32.6, 4), (20.5, 32.5, 6),
        (14.5, 33.0, 6), (8.4, 32.6, 5), (2.0, 34.8, 6), (-5.0, 35.2, 6)]
EAST_SOUTH = EAST + [(-12.0, 33.5, 6), (-20.0, 31.5, 7), (-25.5, 30.0, 6)]
EAST_SLOVAK = [(48.5, 19.3, 0), (47.4, 19.4, 2), (44.6, 22.2, 4), (42.1, 26.2, 4), (41.1, 29.0, 3), (38.4, 31.2, 4),
               (36.4, 36.1, 4), (33.3, 35.6, 4), (30.2, 32.4, 4), (26.2, 32.6, 4), (20.5, 32.5, 6), (14.5, 33.0, 6),
               (8.4, 32.6, 5), (2.0, 34.8, 6)]


def _along(route, rng, scale, wobble):
    """Knots (day, lat, lon) along a route: waypoints shifted by one smooth offset for the bird plus a little of their
    own, at a bird's own pace; the first waypoint is day 0."""
    ox, oy = rng.gauss(0, wobble), rng.gauss(0, wobble * 0.8)
    knots, day = [], 0.0
    for i, (la, lo, dd) in enumerate(route):
        day += dd * scale * rng.uniform(0.85, 1.2)
        fade = 0.0 if i == 0 else 1.0
        knots.append((day, la + (oy + rng.gauss(0, 0.35)) * fade, lo + (ox + rng.gauss(0, 0.45)) * fade))
    return knots


def typical_track(kind, rng):
    """One made-up stork-year (days 0..364 from 1 July) along a typical flyway. kind: W, S or E."""
    if kind == "W":
        route = rng.choice([WEST, WEST, WEST_SENEGAL])
    elif kind == "S":
        route = rng.choice([SPAIN, SPAIN_WEST])
    else:
        route = rng.choice([EAST, EAST, EAST_SOUTH, EAST_SLOVAK])
    nest = route[0]
    depart = rng.uniform(34, 76)                      # 4 August .. 15 September
    out = _along(route, rng, rng.uniform(0.85, 1.15), 0.9 if kind != "S" else 0.5)
    n = len(route)
    home_route = [(route[n - 1][0], route[n - 1][1], 0)] + [(route[k - 1][0], route[k - 1][1], route[k][2]) for k in range(n - 1, 0, -1)]
    back = _along(home_route, rng, rng.uniform(0.7, 0.95), 0.8)
    travel_back = back[-1][0]
    arrive = rng.uniform(244, 306) if kind != "S" else rng.uniform(225, 285)      # 1 March .. 30 April (Spain's a bit earlier)
    leave_win = max(depart + out[-1][0] + 8, arrive - travel_back)
    days, lat, lon = [0.0], [nest[0] + rng.gauss(0, 0.03)], [nest[1] + rng.gauss(0, 0.03)]
    for d, la, lo in out:                              # south
        days.append(depart + d)
        lat.append(la)
        lon.append(lo)
    t = days[-1]
    wl, wo = lat[-1], lon[-1]
    while t + 14 < leave_win:                          # winter: a slow wander round the wintering ground
        t += rng.uniform(8, 16)
        days.append(t)
        lat.append(wl + rng.gauss(0, 0.5))
        lon.append(wo + rng.gauss(0, 0.6))
    go = max(leave_win, days[-1] + 1)
    for i, (d, la, lo) in enumerate(back):            # north again, from where the wintering wandered to the nest
        days.append(go + d)
        lat.append(wl if i == 0 else la)
        lon.append(wo if i == 0 else lo)
    out_d, out_la, out_lo = [], [], []
    for d, la, lo in zip(days, lat, lon):              # strictly increasing days, inside the year
        if d >= DAYS - 0.5:
            break
        if out_d and d <= out_d[-1] + 0.2:
            continue
        out_d.append(d)
        out_la.append(la)
        out_lo.append(lo)
    if out_d[-1] < DAYS - 1.0:                          # home: at the nest for the rest of the year
        out_d.append(DAYS - 1.0)
        out_la.append(out_la[-1])
        out_lo.append(out_lo[-1])
    return tk.Track(out_d, out_la, out_lo, cls=kind, id="typical")


def typical_tracks(seed=11):
    rng = random.Random(seed)
    kinds = ["W"] * 13 + ["S"] * 8 + ["E"] * 14
    return [typical_track(k, rng) for k in kinds]


# ---- recorded tracks -------------------------------------------------------------------------------------

def load_recorded(path=ASSET):
    """(tracks, info) from the bundled real data, or None when it is missing or does not look right."""
    try:
        data = tk.load_json(path)
        out = []
        for b in data["birds"]:
            d, la, lo = b["d"], b["lat"], b["lon"]
            if not (len(d) == len(la) == len(lo) >= 2) or any(y <= x for x, y in zip(d, d[1:])):
                continue
            if not all(-90 <= v <= 90 for v in la) or not all(-180 <= v <= 180 for v in lo):
                continue
            out.append(tk.Track(d, la, lo, cls=b.get("cls", "W"), id=b.get("id", ""), year=b.get("year")))
        if not out:
            return None
        yrs = [b.get("year") for b in data["birds"] if b.get("year")]
        info = {"years": (min(yrs), max(yrs) + 1) if yrs else None, "n": len(out),
                "source": data.get("source"), "licence": data.get("licence")}
        return out, info
    except Exception as e:
        if os.path.exists(path):
            print(f"[storks] {str(e)[:100]}", flush=True)
        return None


# ---- the map ----------------------------------------------------------------------------------------------

def base_map():
    """The still map under the storks: coast, big lakes, Switzerland's border, Zurich: one LED wide, very dim."""
    img = np.zeros((H, W, 3), np.uint8)
    try:
        m = tk.load_json(MAP)
        tk.draw_lines(img, m.get("coast", []), PROJ, COAST)
        tk.draw_lines(img, m.get("lakes", []), PROJ, LAKE, closed=True)
        tk.draw_lines(img, m.get("ch", []), PROJ, BORDER)
    except Exception:
        try:                                              # Europe only, from the wind map
            m = tk.load_json(EUROPE)
            tk.draw_lines(img, m.get("coast", []), PROJ, COAST)
        except Exception:
            pass
    x, y = PROJ.to_led(*ZURICH)
    if 0 <= x < W and 0 <= y < H:
        img[y, x] = HOME
    return img.astype(np.float32)


# ---- the piece --------------------------------------------------------------------------------------------

class Storks:
    def __init__(self, recorded=True, clock=None):
        got = load_recorded() if recorded else None
        if got:
            self.tracks, self.info = got
            self.real = True
            yrs = self.info["years"]
            self.caption = "%d STORKS REAL" % len(self.tracks) + ("  %d-%02d" % (yrs[0], (yrs[1] - 1) % 100) if yrs else "")
        else:
            self.tracks, self.info = typical_tracks(), {}
            self.real = False
            self.caption = "TYPICAL ROUTES"
        self.clock = clock or tk.YearClock(PERIOD, DAYS)
        self.base = base_map()
        self.trails = tk.Trails(W, H)
        self.cols = [COL.get(t.meta.get("cls", "W"), COL["W"]) for t in self.tracks]
        self.prev = [None] * len(self.tracks)
        self.speed = [self._speeds(t) for t in self.tracks]
        self.last_day, self.last_t = None, None
        self.edges = tk.month_edges(START_MONTH)

    @staticmethod
    def _speeds(t):
        """km moved in each day of the year (0 where the bird is not tracked): a flying bird shines, a resting one dims."""
        out = []
        for d in range(DAYS):
            a, b = t.pos(d), t.pos(d + 1.0)
            out.append(tk.distance_km(a[0], a[1], b[0], b[1]) if a and b else 0.0)
        return out

    def _heat(self, i, day):
        s = self.speed[i]
        k = int(day)
        a, b = s[min(k, DAYS - 1)], s[min(k + 1, DAYS - 1)]
        v = a + (b - a) * (day - k)
        return 0.8 + 0.2 * min(1.0, v / 140.0)

    def step(self, day, dt):
        """Advance to `day` of the year, `dt` seconds after the last step: fade, then add what each bird flew."""
        if self.last_day is not None and not (0.0 <= day - self.last_day < 6.0):     # the year turned, or time jumped
            self.trails.clear()
            self.prev = [None] * len(self.tracks)
        self.last_day = day
        tau = TAU if day < DAYS - 3 else 5.0                  # the threads go out as the year ends
        self.trails.fade(dt, tau)
        veil = min(1.0, day / 2.0, (DAYS - day) / 2.0)        # the dots fade in and out over the turn of the year
        heads = []
        for i, t in enumerate(self.tracks):
            p = t.pos(day)
            life = 1.0
            if p is None and t.end < day < t.end + 2.0 and t.end < DAYS - 3:       # the tag stopped: the dot dies away
                p = t.pos(t.end)
                life = 1.0 - (day - t.end) / 2.0
            elif p is not None and day < t.start + 1.5:
                life = (day - t.start) / 1.5 if t.start > 1.0 else 1.0
            if p is None or veil <= 0.0:
                self.prev[i] = None
                continue
            life *= veil
            q = PROJ.to_led(*p)
            col = self.cols[i]
            pv = self.prev[i]
            if pv is not None and pv != q and abs(pv[0] - q[0]) + abs(pv[1] - q[1]) < 60:
                self.trails.line(pv, q, col * (0.78 * life))
            self.prev[i] = q
            heads.append((q, (col + (255.0 - col) * 0.3) * (self._heat(i, day) * life)))
        return heads

    def draw(self, day, heads):
        img = self.trails.over(self.base)
        for (x, y), col in heads:
            if 0 <= x < W and 0 <= y < H:
                img[y, x] = col
        self._corner(img, day)
        return tk.to_image(img)

    def _corner(self, img, day):
        """Bottom left, over the empty South Atlantic: the month, a strip of twelve months, what the dots are."""
        m, dom = tk.month_of(day, START_MONTH)
        x0, y0 = 5, H - 18
        pixelfont.draw(img, tk.MONTHS[m], x0, y0, TEXT)
        cur = (m - (START_MONTH - 1)) % 12
        for k in range(12):                                   # months: past ones dim, this one bright with its day
            x = x0 + k * 7
            img[y0 + 8:y0 + 10, x:x + 6] = np.maximum(img[y0 + 8:y0 + 10, x:x + 6], CAL_OFF if k > cur else TEXT_DIM)
            if k == cur:
                frac = (day - self.edges[k]) / (self.edges[(k + 1) % 12] - self.edges[k] if k < 11 else DAYS - self.edges[k])
                img[y0 + 8:y0 + 10, x:x + 6] = CAL_OFF
                img[y0 + 8:y0 + 10, x:x + 1 + int(round(frac * 5))] = CAL_ON
        pixelfont.draw(img, self.caption, x0, y0 + 12, TEXT_DIM)

    def __call__(self, t):
        now = self.clock.clock()
        day = self.clock.day(now)
        dt = 0.04 if self.last_t is None else max(0.0, min(0.5, t - self.last_t))
        self.last_t = t
        return self.draw(day, self.step(day, dt))

    def preroll(self, day, span=40.0, step=0.5):
        """Play the `span` days before `day` fast, so the threads are already drawn (for a still)."""
        self.last_day = None
        self.trails.clear()
        self.prev = [None] * len(self.tracks)
        d = max(0.0, day - span)
        heads = []
        while d < day:
            d = min(day, d + step)
            heads = self.step(d, step * self.clock.seconds_per_day)
        return heads


_s = None


def frame(t):
    global _s
    if _s is None:
        _s = Storks()
    return _s(t)


def thumb(day=84.0):
    """A still for the app (no network): the storks in the last week of September, threads drawn in."""
    s = Storks()
    heads = s.preroll(day)
    return s.draw(day, heads)
