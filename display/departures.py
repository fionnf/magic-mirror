"""Live tram departures as a split-flap board (transport.opendata.ch, no key).

    board = Board("Zürich, Rennweg")
    board.frame(t) -> PIL image          (fetches in the background every 30 s)

Rows flip through random characters whenever their content changes, like an
old airport / station board. Minutes are computed live from the scheduled
time plus the reported delay.
"""
import datetime
import json
import random
import threading
import time
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont

import config

API = "https://transport.opendata.ch/v1/stationboard"
REFRESH_SEC = 30
FLIP_SEC = 0.35
CHAR_STAGGER = 0.025
FLAP_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# VBZ tram line colours (approximate)
LINE_COLOURS = {
    "2": ((227, 0, 11), (255, 255, 255)), "3": ((0, 160, 77), (255, 255, 255)),
    "4": ((35, 58, 140), (255, 255, 255)), "5": ((136, 82, 54), (255, 255, 255)),
    "6": ((218, 149, 65), (0, 0, 0)), "7": ((20, 20, 20), (255, 255, 255)),
    "8": ((156, 195, 60), (0, 0, 0)), "9": ((107, 78, 155), (255, 255, 255)),
    "10": ((226, 0, 122), (255, 255, 255)), "11": ((0, 144, 54), (255, 255, 255)),
    "12": ((122, 203, 230), (0, 0, 0)), "13": ((255, 222, 0), (0, 0, 0)),
    "14": ((0, 168, 225), (255, 255, 255)), "15": ((227, 6, 19), (255, 255, 255)),
    "16": ((139, 125, 191), (255, 255, 255)), "17": ((146, 39, 70), (255, 255, 255)),
}
MONO = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/System/Library/Fonts/Menlo.ttc"]


def _mono(size):
    for p in MONO:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _short(dest):
    for pre in ("Zürich, ", "Zürich "):
        if dest.startswith(pre):
            dest = dest[len(pre):]
    return (dest.replace("Bahnhofstrasse/HB", "Bhfstr/HB").replace(", Bahnhof", " Bf")
            .replace("Bahnhof", "Bf").replace("platz", "pl."))


class Board:
    def __init__(self, station="Zürich, Rennweg", trams_only=True, rows=7):
        self.station, self.trams_only, self.n_rows = station, trams_only, rows
        self.deps = []                    # list of (line, dest, departure_ts, delay_min)
        self.ok = False
        self.last_fetch = 0.0
        self.shown = {}                   # row -> text currently displayed
        self.changed_at = {}              # row -> t when the flip started
        self.f_row = _mono(11)
        self.f_head = _mono(13)
        self.cell = int(round(self.f_row.getlength("M"))) + 1
        self._lock = threading.Lock()
        threading.Thread(target=self._fetch_loop, daemon=True).start()

    # ---------------------------------------------------------------- data
    def _fetch(self):
        q = urllib.parse.urlencode({"station": self.station, "limit": 20})
        with urllib.request.urlopen(f"{API}?{q}", timeout=15) as r:
            data = json.load(r)
        deps = []
        for s in data.get("stationboard", []):
            if self.trams_only and s.get("category") not in ("T", "Tram"):
                continue
            st = s.get("stop", {})
            ts = st.get("departureTimestamp")
            if ts is None:
                continue
            deps.append((str(s.get("number", "")), _short(s.get("to", "")),
                         float(ts), int(st.get("delay") or 0)))
        return deps

    def _fetch_loop(self):
        while True:
            try:
                deps = self._fetch()
                with self._lock:
                    self.deps, self.ok, self.last_fetch = deps, True, time.time()
            except Exception as e:
                print(f"[TRAMS] fetch failed: {e}")
                with self._lock:
                    self.ok = False
            time.sleep(REFRESH_SEC)

    def _rows(self):
        now = time.time()
        rows = []
        with self._lock:
            deps = list(self.deps)
        for line, dest, ts, delay in deps:
            mins = int((ts + delay * 60 - now) // 60)
            if mins < 0:
                continue
            rows.append((line, dest, mins, delay))
            if len(rows) == self.n_rows:
                break
        return rows

    # -------------------------------------------------------------- drawing
    def _flap_text(self, d, x, y, text, n_cells, t, start, colour):
        for i in range(n_cells):
            ch = text[i] if i < len(text) else " "
            cx = x + i * self.cell
            d.rectangle([cx, y, cx + self.cell - 2, y + 15], fill=(28, 28, 32))
            d.line([cx, y + 7, cx + self.cell - 2, y + 7], fill=(10, 10, 12))
            ts = start + i * CHAR_STAGGER
            if start and ts <= t < ts + FLIP_SEC and ch != " ":
                ch = random.choice(FLAP_CHARS)
            if ch != " ":
                d.text((cx + 0.5, y + 1), ch, font=self.f_row, fill=colour)

    # --- VBZ stop display look: amber LED dot-matrix on black, nothing else
    AMBER = (255, 158, 16)
    AMBER_DIM = (120, 70, 6)

    def _led(self, img, xy, text, font, colour=AMBER, anchor="la"):
        """Crisp (non-antialiased) text, like the LED dots of the real display."""
        if not text:
            return
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).text(xy, text, font=font, fill=255, anchor=anchor)
        img.paste(colour, mask=mask.point(lambda v: 255 if v > 110 else 0))

    # a small tram-front pictogram (as on the real boards when a tram is pulling in)
    TRAM = ["..#######..",
            ".#########.",
            "#..#...#..#",
            "#..#...#..#",
            "#.........#",
            "#.#.....#.#",
            "###########",
            ".##.....##.",
            "...........",
            ]

    def _tram_icon(self, img, x, y, colour=AMBER):
        px = img.load()
        for j, row in enumerate(self.TRAM):
            for i, ch in enumerate(row):
                if ch == "#" and 0 <= x + i < img.width and 0 <= y + j < img.height:
                    px[x + i, y + j] = colour
        px[x + 5, y - 1] = colour                                   # pantograph

    def frame(self, t):
        """The board only changes when a departure, the clock or the blink state changes, so the
        drawing (many text masks) is cached and most frames are a free repeat."""
        now = datetime.datetime.now()
        rows = self._rows()
        key = (tuple(rows), now.strftime("%H:%M"), self.ok, int(t * 2) % 2 if any(r[2] == 0 for r in rows) else 0,
               int(t * 18) if not self.ok else 0)
        if getattr(self, "_cache_key", None) == key:
            return self._cache_img
        img = self._draw(t, now, rows)
        self._cache_key, self._cache_img = key, img
        return img

    def _draw(self, t, now, rows):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        img = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        f_row, f_head, f_small = self.f_row, self.f_head, _mono(9)
        name = self.station.split(", ")[-1]
        self._led(img, (4, 3), name, f_head)
        self._led(img, (W - 4, 3), now.strftime("%H:%M"), f_head, anchor="ra")
        d.line([4, 21, W - 4, 21], fill=self.AMBER_DIM)
        top, rh = 26, (H - 26 - 16) // self.n_rows
        dest_cells = max(6, (W - 30 - 3 * self.cell - 6) // self.cell)
        for r in range(min(self.n_rows, len(rows))):
            y = top + r * rh
            line, dest, mins, delay = rows[r]
            self._led(img, (22, y), line, f_row, anchor="ra")               # line number, right-aligned
            self._led(img, (30, y), dest[:dest_cells], f_row)
            if mins == 0:                                                   # pulling in: the tram pictogram
                self._tram_icon(img, W - 16, y + 3)
            else:
                self._led(img, (W - 4, y), f"{mins}'", f_row, anchor="ra")
        # bottom info line: the date, or the outage notice (real boards scroll messages here)
        if self.ok:
            info = now.strftime("%a %d.%m.%Y").replace("Mon", "Mo").replace("Tue", "Di").replace("Wed", "Mi") \
                .replace("Thu", "Do").replace("Fri", "Fr").replace("Sat", "Sa").replace("Sun", "So")
            self._led(img, (4, H - 12), info, f_small, self.AMBER_DIM)
        else:
            msg = "Keine Daten - Verbindung zur Fahrplanauskunft unterbrochen      "
            w = f_small.getlength(msg)
            x = W - (t * 18) % (w + W)
            self._led(img, (x, H - 12), msg, f_small, self.AMBER_DIM)
        return img


_board = None


def frame(t):
    global _board
    if _board is None:
        _board = Board()
    return _board.frame(t)


# ------------------------------------------------- subtle ambient overlay ---

def _bold(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/Library/Fonts/Arial Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def draw_ticker(board, img, t, n=4, band=17, darken=0.42):
    """Quiet strip along the bottom of `img`: next n trams as small chips."""
    import numpy as np
    W, H = img.size
    a = np.asarray(img, np.float32).copy()
    a[H - band:] *= darken                                  # translucent dark band
    a[H - band] = a[H - band] * 0.6 + 40                    # faint top edge
    img = Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    f_num, f_min = _bold(8), _bold(9)
    rows = board._rows()[:n]
    slot = W / n
    y = H - band + (band - 10) // 2
    for i, (line, dest, mins, delay) in enumerate(rows):
        x = int(i * slot + 4)
        bg, fg = LINE_COLOURS.get(line, ((90, 90, 100), (255, 255, 255)))
        bg = tuple(int(c * 0.8) for c in bg)
        d.rounded_rectangle([x, y, x + 15, y + 10], 2, fill=bg,
                            outline=(110, 110, 110) if sum(bg) < 80 else None)
        d.text((x + 8, y + 5), line, font=f_num, fill=fg, anchor="mm")
        txt = "now" if mins == 0 else f"{mins}'"
        col = (225, 150, 70) if delay > 0 else (215, 210, 195)
        if mins == 0:                                       # gentle breathing, no blink
            k = 0.6 + 0.4 * (0.5 + 0.5 * np.sin(t * 2.5))
            col = tuple(int(c * k) for c in col)
        d.text((x + 18, y + 5), txt, font=f_min, fill=col, anchor="lm")
    if not board.ok:
        d.ellipse([W - 5, H - band + 2, W - 2, H - band + 5], fill=(150, 50, 50))
    return img


_ambient_board = None


def ambient_frame(t):
    """Lava & Coral art with the tram ticker along the bottom."""
    global _ambient_board
    from display import art
    if _ambient_board is None:
        _ambient_board = Board()
    return draw_ticker(_ambient_board, art.frame_lava_coral(t), t)
