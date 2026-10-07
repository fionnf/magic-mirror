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

    def frame(self, t):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        img = Image.new("RGB", (W, H), (8, 8, 12))
        d = ImageDraw.Draw(img)
        # header
        d.rectangle([0, 0, W, 20], fill=(0, 45, 110))
        name = self.station.split(", ")[-1].upper()
        d.text((5, 3), name, font=self.f_head, fill=(255, 210, 0))
        now = datetime.datetime.now()
        clock = now.strftime("%H:%M") if now.second % 2 == 0 else now.strftime("%H %M")
        d.text((W - 5 - self.f_head.getlength(clock), 3), clock, font=self.f_head,
               fill=(255, 255, 255))
        if not self.ok:
            d.ellipse([W - 52, 8, W - 47, 13], fill=(255, 40, 40))      # offline dot
        rows = self._rows()
        top, rh = 24, (H - 26) // self.n_rows
        dest_cells = max(6, (W - 30 - 5 * self.cell - 6) // self.cell)
        for r in range(self.n_rows):
            y = top + r * rh
            if r < len(rows):
                line, dest, mins, delay = rows[r]
                mtxt = "now" if mins == 0 else f"{mins}'"
                text = f"{line}|{dest[:dest_cells]}|{mtxt}"
            else:
                line, dest, mins, delay, mtxt, text = "", "", 0, 0, "", ""
            if self.shown.get(r) != text:                # content changed: flip
                key = text.split("|")[:2]
                old = (self.shown.get(r) or "").split("|")[:2]
                self.shown[r] = text
                if key != old:
                    self.changed_at[r] = t
            start = self.changed_at.get(r, 0.0)
            if line:
                bg, fg = LINE_COLOURS.get(line, ((90, 90, 100), (255, 255, 255)))
                d.rounded_rectangle([3, y, 25, y + 15], 3, fill=bg,
                                    outline=(200, 200, 200) if bg == (20, 20, 20) else None)
                d.text((14, y + 8), line, font=self.f_row, fill=fg, anchor="mm")
            self._flap_text(d, 29, y, dest[:dest_cells], dest_cells, t, start,
                            (240, 235, 210))
            mcol = (255, 150, 40) if delay > 0 else (255, 210, 0)
            if mtxt == "now" and int(t * 2) % 2 == 0:
                mcol = (90, 90, 90)
            mx = W - 4 - 4 * self.cell
            self._flap_text(d, mx, y, mtxt.rjust(4), 4, t, start, mcol)
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
