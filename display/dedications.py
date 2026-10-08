"""Dedications wall: guests scan a QR code, type a message, and it scrolls across the bottom of
the wall. Deliberately NOT filtered (house rule) - the only guard rails are a length cap, a rate
limit per phone, a pause switch and delete/clear in the app.

Stored in panel_setup/dedications.json (git-ignored):
  {"enabled": false, "show_qr": true, "paused": false,
   "items": [{"id", "text", "name", "ts"}]}

    add(text, name, who)       -> item (raises ValueError with a friendly message)
    Overlay().apply(img, now)  -> img with the marquee / QR painted on (used by panel_setup/play.py)
"""
import json
import os
import re
import socket
import threading
import time
import uuid

from PIL import Image, ImageDraw, ImageFont

import config

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(_HERE, "panel_setup", "dedications.json")
MAX_TEXT, MAX_NAME, MAX_ITEMS = 140, 24, 50
RATE_SEC = 45.0
_NO_EMOJI = re.compile("[\U00010000-\U0010ffff\u2190-\u27bf\ufe0f\u200d]")
_lock = threading.Lock()
_last_by = {}


def _clean(s, n):
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", str(s or ""))
    return " ".join(s.split())[:n]


def load():
    try:
        with open(FILE) as fh:
            d = json.load(fh)
    except Exception:
        d = {}
    return {"enabled": bool(d.get("enabled", False)), "show_qr": bool(d.get("show_qr", True)),
            "paused": bool(d.get("paused", False)), "items": list(d.get("items", []))}


def _save(d):
    tmp = FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh)
    os.replace(tmp, FILE)


def update(**kw):
    with _lock:
        d = load()
        for k in ("enabled", "show_qr", "paused"):
            if k in kw:
                d[k] = bool(kw[k])
        _save(d)
        return d


def add(text, name="", who="?", now=None):
    now = now if now is not None else time.time()
    text, name = _clean(text, MAX_TEXT), _clean(name, MAX_NAME)
    if not text:
        raise ValueError("Write something first")
    with _lock:
        d = load()
        if not d["enabled"] or d["paused"]:
            raise ValueError("The wall is not taking dedications right now")
        wait = RATE_SEC - (now - _last_by.get(who, 0))
        if wait > 0:
            raise ValueError(f"Slow down a little - try again in {int(wait) + 1} s")
        _last_by[who] = now
        item = {"id": uuid.uuid4().hex[:8], "text": text, "name": name, "ts": now}
        d["items"] = (d["items"] + [item])[-MAX_ITEMS:]
        _save(d)
    return item


def delete(item_id):
    with _lock:
        d = load()
        n = len(d["items"])
        d["items"] = [i for i in d["items"] if i["id"] != item_id]
        _save(d)
        return n - len(d["items"])


def clear():
    with _lock:
        d = load()
        n = len(d["items"])
        d["items"] = []
        _save(d)
        return n


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def guest_url(host=None):
    return f"http://{host or local_ip()}/d"


def qr_image(url, px=60):
    import qrcode
    q = qrcode.QRCode(border=1, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(url)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((px, px), Image.NEAREST)


class Overlay:
    BAND = 24
    SPEED = 30.0                 # px / s
    GAP = 18.0                   # s between messages
    QR_EVERY, QR_FOR = 150.0, 12.0

    def __init__(self):
        from display import text_renderer
        self.font = text_renderer._load_font(17)
        self.small = text_renderer._load_font(10)
        self._data, self._mtime, self._checked = load(), None, 0.0
        self.cur = None          # (item, started, width)
        self.next_at = 0.0
        self.shown = set()
        self.idx = 0
        self.qr = None
        self.t_start = time.monotonic()

    def _refresh(self, now):
        if now - self._checked < 2.0:
            return
        self._checked = now
        try:
            m = os.path.getmtime(FILE)
        except OSError:
            m = None
        if m != self._mtime:
            self._mtime, self._data = m, load()

    def apply(self, img, now=None):
        now = now if now is not None else time.monotonic()
        self._refresh(now)
        d = self._data
        if not d["enabled"] or d["paused"]:
            self.cur = None
            return img
        img = img.copy()
        W, H = img.size
        if d["items"]:
            self._marquee(img, d, now, W, H)
        if d["show_qr"] and (now - self.t_start) % self.QR_EVERY < self.QR_FOR:
            self._qr(img, W, H)
        return img

    def _marquee(self, img, d, now, W, H):
        items = d["items"]
        if self.cur is None and now >= self.next_at:
            fresh = [i for i in items if i["id"] not in self.shown]
            item = fresh[0] if fresh else items[self.idx % len(items)]
            if not fresh:
                self.idx += 1
            self.shown.add(item["id"])
            label = (item["name"] + ": " if item["name"] else "") + item["text"]
            label = " ".join(_NO_EMOJI.sub("", label).split())      # the LED font has no emoji
            w = int(ImageDraw.Draw(img).textlength(label, font=self.font))
            self.cur = (label, now, w)
        if self.cur is None:
            return
        label, t0, w = self.cur
        x = W - (now - t0) * self.SPEED
        if x < -w:
            self.cur = None
            fresh = any(i["id"] not in self.shown for i in items)
            self.next_at = now + (2.0 if fresh else self.GAP)
            return
        band = Image.new("RGBA", (W, self.BAND), (0, 0, 0, 170))
        ImageDraw.Draw(band).text((x, 2), label, font=self.font, fill=(255, 225, 245, 255),
                                  stroke_width=1, stroke_fill=(120, 20, 90, 255))
        img.paste(band, (0, H - self.BAND), band)

    def _qr(self, img, W, H):
        if self.qr is None:
            try:
                self.qr = qr_image(guest_url(), 62)
            except Exception:
                self.qr = False
        if not self.qr:
            return
        x, y = W - 66, H - 66 - self.BAND - 4
        img.paste(self.qr, (x + 2, y))
        ImageDraw.Draw(img).text((x + 2, y - 11), "say hi", font=self.small, fill=(255, 255, 255))
