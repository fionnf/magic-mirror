"""Kilchberg train board: live S-Bahn departures from Kilchberg ZH, drawn like a station display (amber LED dots on black).

Data: transport.opendata.ch (no key), every 30 s on a side thread. Minutes are computed live from the scheduled time plus
the reported delay, so the board counts down between fetches. A train more than 2 minutes late shows its minutes in red,
and one that is pulling in shows a little train-front pictogram. Offline, the board says so (in German, like the real
ones) instead of showing stale times.

    frame(t) -> PIL image        thumb() -> a still of the board with example departures (no network)
"""
import datetime
import json
import threading
import time
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw

import config
from display.departures import Board, _mono

STATION = "Kilchberg ZH"
API = "https://transport.opendata.ch/v1/stationboard"
REFRESH_SEC = 30
RED = (255, 80, 40)

TRAIN = ["..#######..",
         ".#########.",
         "#.##...##.#",
         "#.##...##.#",
         "#.........#",
         "#.#.....#.#",
         "###########",
         ".##.....##.",
         "..........."]


def _line(s):
    """'S' + '8' -> 'S8'; night S-Bahn 'SN' + '8' -> 'SN8'; the number alone when the category is empty."""
    cat, num = str(s.get("category") or ""), str(s.get("number") or "")
    if num.upper().startswith(cat.upper()) and cat:
        return num[:4]
    return (cat + num)[:4]


def _dest(to):
    return (to or "").replace("Zürich ", "Zürich ").replace("Bahnhof", "Bf").replace(" HB", " HB")


class TrainBoard(Board):
    def __init__(self, station=STATION, rows=6, fetch=True):
        self.station, self.trams_only, self.n_rows = station, False, rows
        self.deps = []                      # (line, dest, departure_ts, delay_min, platform)
        self.ok = False
        self.last_fetch = 0.0
        self.f_row, self.f_head, self.f_small = _mono(11), _mono(13), _mono(9)
        self.cell = int(round(self.f_row.getlength("M"))) + 1
        self._lock = threading.Lock()
        if fetch:
            threading.Thread(target=self._fetch_loop, daemon=True).start()

    # ---- data ----
    def _fetch(self):
        q = urllib.parse.urlencode({"station": self.station, "limit": 20})
        with urllib.request.urlopen(f"{API}?{q}", timeout=15) as r:
            data = json.load(r)
        out = []
        for s in data.get("stationboard", []):
            st = s.get("stop", {})
            ts = st.get("departureTimestamp")
            if ts is None:
                continue
            out.append((_line(s), _dest(s.get("to", "")), float(ts), int(st.get("delay") or 0), str(st.get("platform") or "")))
        return out

    def _fetch_loop(self):
        while True:
            try:
                deps = self._fetch()
                with self._lock:
                    self.deps, self.ok, self.last_fetch = deps, True, time.time()
            except Exception as e:
                print(f"[KILCHBERG] fetch failed: {e}", flush=True)
                with self._lock:
                    self.ok = False
            time.sleep(REFRESH_SEC)

    def _rows(self):
        now = time.time()
        with self._lock:
            deps = list(self.deps)
        rows = []
        for line, dest, ts, delay, plat in sorted(deps, key=lambda d: d[2] + d[3] * 60):
            mins = int((ts + delay * 60 - now) // 60)
            if mins < 0:
                continue
            rows.append((line, dest, mins, delay, plat, ts + delay * 60))
            if len(rows) == self.n_rows:
                break
        return rows

    # ---- drawing (cached: the board only changes when a row, the clock or a blink changes) ----
    def frame(self, t):
        now = datetime.datetime.now()
        rows = self._rows()
        key = (tuple(rows), now.strftime("%H:%M"), self.ok, int(t * 2) % 2 if any(r[2] == 0 for r in rows) else 0,
               int(t * 18) if not self.ok else 0)
        if getattr(self, "_cache_key", None) == key:
            return self._cache_img
        img = self._draw(t, now, rows)
        self._cache_key, self._cache_img = key, img
        return img

    def _train_icon(self, img, x, y, colour=Board.AMBER):
        px = img.load()
        for j, row in enumerate(TRAIN):
            for i, ch in enumerate(row):
                if ch == "#" and 0 <= x + i < img.width and 0 <= y + j < img.height:
                    px[x + i, y + j] = colour
        px[x + 5, y - 1] = colour

    def _draw(self, t, now, rows):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        img = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        f_row, f_head, f_small = self.f_row, self.f_head, self.f_small
        self._led(img, (4, 3), "Kilchberg", f_head)
        self._led(img, (W - 4, 3), now.strftime("%H:%M"), f_head, anchor="ra")
        d.line([4, 21, W - 4, 21], fill=self.AMBER_DIM)
        self._led(img, (4, 24), "Linie", f_small, self.AMBER_DIM)
        self._led(img, (36, 24), "Nach", f_small, self.AMBER_DIM)
        self._led(img, (W - 40, 24), "Gl", f_small, self.AMBER_DIM, anchor="ra")
        self._led(img, (W - 4, 24), "Min", f_small, self.AMBER_DIM, anchor="ra")
        top, rh = 37, (H - 37 - 16) // self.n_rows
        dest_cells = max(6, (W - 36 - 44) // self.cell)
        for r in range(min(self.n_rows, len(rows))):
            y = top + r * rh
            line, dest, mins, delay, plat, dep = rows[r]
            self._led(img, (4, y), line, f_row)
            self._led(img, (36, y), dest[:dest_cells], f_row)
            self._led(img, (W - 40, y + 2), plat, f_small, self.AMBER_DIM, anchor="ra")
            late = delay > 2
            if mins == 0:
                if int(t * 2) % 2 == 0 or not self.ok:
                    self._train_icon(img, W - 16, y + 3, RED if late else self.AMBER)
            else:
                label = f"{mins}'" if mins < 60 else datetime.datetime.fromtimestamp(dep).strftime("%H:%M")   # an hour or more away: the clock time
                self._led(img, (W - 4, y), label, f_row, RED if late else self.AMBER, anchor="ra")
            if late:                                                        # how late, small, under the destination
                self._led(img, (36, y + 11), f"+{delay} Min", f_small, RED if delay > 5 else self.AMBER_DIM)
        if not rows and self.ok:
            self._led(img, (4, top + 6), "Keine Abfahrten", f_row, self.AMBER_DIM)
        if self.ok:
            info = now.strftime("%a %d.%m.%Y").replace("Mon", "Mo").replace("Tue", "Di").replace("Wed", "Mi") \
                .replace("Thu", "Do").replace("Fri", "Fr").replace("Sat", "Sa").replace("Sun", "So")
            self._led(img, (4, H - 12), info, f_small, self.AMBER_DIM)
        else:
            msg = "Keine Daten - Verbindung zur Fahrplanauskunft unterbrochen      "
            w = f_small.getlength(msg)
            self._led(img, (W - (t * 18) % (w + W), H - 12), msg, f_small, self.AMBER_DIM)
        return img


_board = None


def frame(t):
    global _board
    if _board is None:
        _board = TrainBoard()
    return _board.frame(t)


def thumb():
    """A still for the app: example departures, no network."""
    b = TrainBoard(fetch=False)
    now = time.time()
    b.ok = True
    b.deps = [("S8", "Pfäffikon SZ", now + 60 * 3, 0, "1"), ("S24", "Zürich HB", now + 60 * 6, 0, "2"),
              ("S8", "Zürich HB", now + 60 * 9, 4, "2"), ("S24", "Thalwil", now + 60 * 14, 0, "1"),
              ("SN8", "Lachen SZ", now + 60 * 22, 0, "1"), ("S8", "Pfäffikon SZ", now + 60 * 33, 0, "1")]
    return b.frame(0.0)
