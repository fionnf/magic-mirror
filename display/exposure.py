"""Long exposure: the room's evening as one slowly developing picture. The camera watches for movement
and wherever someone moves, light builds up on the wall - like a photograph with the shutter open
all evening. Busy places glow, places nobody went stay dark, and a quiet evening leaves almost
nothing. It is tinted with today's art-of-the-day palette (shadow -> mid -> highlight), so it
belongs to the day.

Only movement is kept (never a picture of anyone); everything stays on the Pi. The exposure
survives a restart (panel_setup/exposure_now.npz), and at 05:00 the night's picture is saved to
panel_setup/exposures/<date>.png and a fresh one begins.
"""
import datetime
import json
import os
import threading
import time

import numpy as np
from PIL import Image

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = os.path.join(_HERE, "panel_setup", "exposure_now.npz")
ARCHIVE = os.path.join(_HERE, "panel_setup", "exposures")
DAY_STARTS = 5                    # the exposure belongs to the evening before, until 05:00
GAIN = 0.035                      # light added per second of movement on a pixel
KNEE = 6.0                        # exposure at which a pixel is ~63 % of full brightness
FALLBACK = ("#120a18", "#8a3a6a", "#ffd2a0")


def _evening(now=None):
    now = now or datetime.datetime.now()
    return (now - datetime.timedelta(hours=DAY_STARTS)).date().isoformat()


def _palette():
    """Today's art-of-the-day colours (or a warm default), as three RGB floats 0..255."""
    pal = FALLBACK
    try:
        from display import daily
        meta = dict(daily.editions()).get(datetime.date.today().isoformat())
        if meta and len(meta.get("palette") or []) == 3:
            pal = meta["palette"]
    except Exception:
        pass
    return [np.array([int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], np.float32) for h in pal]


class Exposure:
    def __init__(self):
        self.acc = np.zeros((H, W), np.float32)            # accumulated movement (seconds)
        self.live = np.zeros((H, W), np.float32)           # movement right now, for a faint glow
        self.date, self.saved = _evening(), time.monotonic()
        self.pal, self.pal_t = _palette(), time.monotonic()
        self.error = ""
        self._load()
        threading.Thread(target=self._watch, daemon=True).start()

    # -- the camera side: movement only --------------------------------------------------------
    def _watch(self):
        import cv2
        try:
            from camera import Camera
            cam = Camera()
        except Exception as e:
            self.error = str(e)[:80]
            print(f"[exposure] no camera: {self.error}", flush=True)
            return
        prev, last = None, time.monotonic()
        while True:
            try:
                frame = cam.capture_frame()
                g = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (0, 0), 2.0)
                g = cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)
                if getattr(config, "SILHOUETTE_MIRROR", True):
                    g = g[:, ::-1]
                now = time.monotonic()
                dt, last = min(1.0, now - last), now
                if prev is not None:
                    # movement: a clear change between frames, softened so it paints, not speckles
                    m = np.clip((np.abs(g - prev) - 10.0) / 25.0, 0.0, 1.0)
                    m = cv2.GaussianBlur(m, (0, 0), 1.5)
                    self.acc += m * (GAIN * 60.0 * dt)
                    self.live = np.maximum(self.live * 0.8, m)
                prev = g
            except Exception as e:
                print(f"[exposure] {str(e)[:100]}", flush=True)
                time.sleep(1.0)
            time.sleep(0.08)

    # -- keeping the evening -------------------------------------------------------------------
    def _load(self):
        try:
            z = np.load(NOW)
            if z["acc"].shape != self.acc.shape:
                return
            if str(z["date"]) == self.date:
                self.acc = z["acc"].astype(np.float32)
            else:                                          # an earlier evening, never saved as a picture
                today = self.date
                self.acc, self.date = z["acc"].astype(np.float32), str(z["date"])
                self._roll()
                self.date = today
        except Exception:
            pass

    def _save(self):
        try:
            np.savez_compressed(NOW + ".tmp.npz", acc=self.acc, date=self.date)
            os.replace(NOW + ".tmp.npz", NOW)
        except OSError:
            pass

    def _roll(self):
        """A new evening: keep the last one as a picture, start again."""
        try:
            os.makedirs(ARCHIVE, exist_ok=True)
            if self.acc.max() > 0.05:
                self.render().save(os.path.join(ARCHIVE, self.date + ".png"))
                print(f"[exposure] saved the evening of {self.date}", flush=True)
        except OSError:
            pass
        self.acc[:] = 0.0
        self.date = _evening()

    # -- the picture ---------------------------------------------------------------------------
    def render(self):
        a, b, c = self.pal
        v = 1.0 - np.exp(-self.acc / KNEE)                 # builds up fast at first, then saturates softly
        v = np.maximum(v, 0.35 * np.minimum(1.0, self.live))   # what moves now shows faintly at once
        v = v[..., None]
        lo = a + (b - a) * np.clip(v / 0.6, 0.0, 1.0)      # shadow -> mid
        img = np.where(v < 0.6, lo, b + (c - b) * np.clip((v - 0.6) / 0.4, 0.0, 1.0))
        img = img * np.clip(v / 0.08, 0.0, 1.0)            # nothing happened here: black
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")

    def __call__(self, t):
        now = time.monotonic()
        if _evening() != self.date:
            self._roll()
        if now - self.saved > 60:
            self.saved = now
            self._save()
        if now - self.pal_t > 600:                         # a new day's art brings new colours
            self.pal_t, self.pal = now, _palette()
        return self.render()


_ex = None


def frame(t):
    global _ex
    if _ex is None:
        _ex = Exposure()
    return _ex(t)
