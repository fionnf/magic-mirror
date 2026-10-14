"""People on the art: the camera's silhouettes of whoever is in the room, laid over any art as a
very slight colour shift (the art's own colours turn a little in hue and lift a touch inside the
silhouette - no outline, no solid shape). Switched on in the app (wall_state "presence").

    p = Presence(W, H)        # starts the camera on a side thread; quietly does nothing without one
    img = p.apply(img, dt)    # PIL image or float array in, same type out

The camera runs small (320x240, ~8 fps). A background model learns the empty room; the wall itself
lights the room, so each frame is normalised for overall brightness and a frame where nearly
everything "changed" (the art changed the room's light) is ignored. The silhouette is softened and
eased in and out, so it never flickers.
"""
import threading
import time

import numpy as np

STRENGTH = 0.55         # how far the colours move inside a silhouette (0..1) - slight, but readable
HUE = 0.9               # radians of hue turn
GLOW = 0.09             # a faint glow inside, in the art's own brightest colour (shows on black too)
EASE = 0.35             # seconds for the silhouette to follow a movement


class Presence:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.target = None
        self.cur = None
        self.error = ""
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import cv2
            from picamera2 import Picamera2
            import config
            import vision
            cam = Picamera2()
            cam.configure(cam.create_video_configuration(main={"size": (320, 240), "format": "RGB888"},
                                                         controls={"FrameRate": 10}))
            cam.start()
            time.sleep(1.0)
            sub = cv2.createBackgroundSubtractorMOG2(history=900, varThreshold=40, detectShadows=False)
            while True:
                t0 = time.monotonic()
                fr = cam.capture_array()
                fr = fr.astype(np.float32)
                fr *= 110.0 / max(8.0, float(fr.mean()))          # the wall's light varies: normalise it
                fr = np.clip(fr, 0, 255).astype(np.uint8)
                m = vision.silhouette_mask(fr, None, sub)
                fg = float((m > 127).mean())
                if fg < 0.6:                                     # else: the room's light changed, not people
                    soft = cv2.GaussianBlur(m.astype(np.float32) / 255.0, (0, 0), 4.0)
                    self.target = soft if soft.shape == (self.H, self.W) else cv2.resize(soft, (self.W, self.H))
                time.sleep(max(0.0, 0.12 - (time.monotonic() - t0)))
        except Exception as e:
            self.error = str(e)[:120]
            print(f"[presence] off: {self.error}", flush=True)

    def apply(self, img, dt):
        if self.target is None:
            return img
        k = 1.0 - np.exp(-max(0.0, dt) / EASE)
        self.cur = self.target.copy() if self.cur is None else self.cur + (self.target - self.cur) * k
        ys, xs = np.nonzero(self.cur > 0.02)
        if len(ys) == 0:
            return img
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1   # work only where people are
        pil = not isinstance(img, np.ndarray)
        a = np.asarray(img, np.float32)
        if pil:
            a = a.copy()
        from display.vj_fx import hue_rotate
        part = a[y0:y1, x0:x1]
        m = self.cur[y0:y1, x0:x1, None] * STRENGTH
        flat = a[::4, ::4].reshape(-1, 3)
        top = flat[flat.sum(1) >= np.percentile(flat.sum(1), 95)].mean(0)   # the art's brightest colour
        shifted = hue_rotate(part, HUE) + top * (GLOW / STRENGTH)
        a[y0:y1, x0:x1] = np.clip(part + (shifted - part) * m, 0, 255)
        if pil:
            from PIL import Image
            return Image.fromarray(a.astype(np.uint8), "RGB")
        return a
