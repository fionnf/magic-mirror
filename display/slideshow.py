"""Mirror photos: a slideshow of every picture the mirror has taken, in random order (art mode `snapshots`).

Each photo is shown for about 8 seconds with a slow zoom, then cross-fades into the next, which is picked at random (no repeat
until all have been shown; new photos join as they are taken). Photos come from photos/ on the Pi: the single mirror photos
and each photobooth shot. The next picture is loaded on a side thread while the current one shows, so the wall never stutters.
With no photos yet it says so.

    frame(t) -> PIL image        thumb() -> a still for the app
"""
import glob
import os
import random
import threading
import time

import cv2
import numpy as np
from PIL import Image

import config
from display import pixelfont

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
try:
    import photo_store
    PHOTOS = photo_store.PHOTOS_DIR                    # honours WALL_PHOTOS_DIR (a USB stick)
except Exception:
    PHOTOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "photos")
HOLD, FADE = 7.0, 1.4                    # seconds a photo stays, and the cross-fade to the next
ZOOM = 0.06                              # a slow push-in over the slot
RESCAN = 30.0


def _files():
    """Photo files, one per picture: the faster small copy when there is one, a booth shot at full size otherwise."""
    out = []
    try:
        names = set(os.listdir(PHOTOS))
    except OSError:
        return out
    for n in sorted(names):
        if not n.endswith(".jpg") or n.endswith(".tmp.jpg"):
            continue
        if n.startswith("receipt_") and not n.endswith("_thumb.jpg"):
            t = n[:-4] + "_thumb.jpg"
            out.append(os.path.join(PHOTOS, t if t in names else n))
        elif n.startswith("strip_") and "_shot" in n:
            out.append(os.path.join(PHOTOS, n))
        elif n.startswith("strip_") and n.endswith("_frame.jpg") and not any(x.startswith(n[:-10] + "_shot") for x in names):
            out.append(os.path.join(PHOTOS, n))          # an older strip: its one saved frame
    return out


def _load(path):
    """The picture as a W+14 x H+18 array (cover-cropped a little larger than the wall, room to zoom and drift), colour-lifted for LEDs."""
    im = Image.open(path)
    im.draft("RGB", (W * 3, H * 3))                      # decode a big JPEG at a fraction of the cost
    im = im.convert("RGB")
    tw, th = int(W * 1.1), int(H * 1.1)
    s = max(tw / im.width, th / im.height)
    im = im.resize((int(round(im.width * s)), int(round(im.height * s))), Image.LANCZOS)
    x0, y0 = (im.width - tw) // 2, int((im.height - th) * 0.35)            # keep the heads
    a = np.asarray(im.crop((x0, y0, x0 + tw, y0 + th)), np.float32)
    a = (a - 128.0) * 1.12 + 128.0                                          # a touch more contrast and colour: LEDs wash pictures out
    g = a.mean(axis=2, keepdims=True)
    a = g + (a - g) * 1.22
    return np.clip(a, 0, 255).astype(np.uint8)


class Show:
    def __init__(self):
        self.files, self.order, self.next_scan = [], [], 0.0
        self.cur = self.nxt = None
        self.t0 = None
        self.loading = None
        self.name = ""

    def _pick(self):
        if time.time() > self.next_scan:
            self.files, self.next_scan = _files(), time.time() + RESCAN
        if not self.files:
            return None
        if not self.order:
            self.order = self.files[:]
            random.shuffle(self.order)
            if self.cur is not None and self.order[-1] == self.name and len(self.order) > 1:
                self.order.reverse()                            # not the one we just showed, first
        return self.order.pop()

    def _fetch_next(self):
        def run():
            for _ in range(5):                                  # skip a damaged file
                p = self._pick()
                if p is None:
                    self.nxt = None
                    return
                try:
                    self.nxt, self._nxt_name = _load(p), p
                    return
                except Exception:
                    continue
            self.nxt = None
        self.loading = threading.Thread(target=run, daemon=True)
        self.loading.start()

    def _view(self, img, e):
        """A window onto the picture: a slow push-in, drifting a little."""
        k = 1.0 - ZOOM * min(1.0, max(0.0, e / (HOLD + FADE)))
        h, w = img.shape[:2]
        vw, vh = w * k, h * k                                    # the part shown shrinks: zooming in
        vw, vh = max(W, vw), max(H, vh)
        x0, y0 = (w - vw) / 2.0, (h - vh) / 2.0 + (1 - k) * h * 0.25            # drifts a little as it zooms
        M = np.float32([[W / vw, 0, -x0 * W / vw], [0, H / vh, -y0 * H / vh]])
        return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def frame(self, t):
        if self.t0 is None:
            self.t0 = t
        if self.cur is None:
            p = self._pick()
            if p is None:
                return self._empty(t)
            try:
                self.cur, self.name = _load(p), p
            except Exception:
                self.cur = None
                return self._empty(t)
            self._fetch_next()
            self.t0 = t
        e = t - self.t0
        slot = HOLD + FADE
        if e >= slot:                                           # the next picture becomes the current one
            if self.loading is not None and self.loading.is_alive():
                self.loading.join(timeout=0.05)
            if self.nxt is not None:
                self.cur, self.name = self.nxt, getattr(self, "_nxt_name", self.name)
            self.t0 += slot
            e -= slot
            self._fetch_next()
        a = self._view(self.cur, e)
        if e > HOLD and self.nxt is not None:                   # cross-fade into the next one
            k = min(1.0, (e - HOLD) / FADE)
            k = k * k * (3 - 2 * k)
            b = self._view(self.nxt, 0.0)
            a = (a.astype(np.float32) * (1 - k) + b.astype(np.float32) * k).astype(np.uint8)
        return Image.fromarray(a, "RGB")

    def _empty(self, t):
        img = np.zeros((H, W, 3), np.float32)
        pulse = 0.55 + 0.45 * np.sin(t * 1.6)
        for i, line in enumerate(("NO PHOTOS", "YET")):
            pixelfont.draw(img, line, (W - pixelfont.width(line)) // 2, H // 2 - 14 + i * 8, (255, 220, 150))
        txt = "TAKE ONE IN THE MIRROR"
        pixelfont.draw(img, txt, (W - pixelfont.width(txt)) // 2, H // 2 + 12, tuple(int(c * pulse) for c in (150, 140, 170)))
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


_show = None


def frame(t):
    global _show
    if _show is None:
        _show = Show()
    return _show.frame(t)


def thumb():
    """A still for the app: a random photo, or the empty card."""
    s = Show()
    return s.frame(0.0)
