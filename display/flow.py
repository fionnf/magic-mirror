"""Flow: the whole gallery as one continuous piece. Each artwork hangs for a while, then the next one
bleeds in through it - not a plain cross-fade but an organic front: a slow, drifting cloud decides
where the new piece arrives first, and its bright parts come through before its dark ones, so one
picture grows out of the other.

Only GPU pieces (the shaders, the music visuals and every art-of-the-day edition) are in the flow:
two pieces render at once during a bleed, and CPU pieces would cost the panel refresh.

    WALL_FLOW_HOLD   minutes a piece hangs on its own (default 6)
    WALL_FLOW_BLEED  seconds the bleed into the next one takes (default 75)
"""
import os
import random

import numpy as np
from PIL import Image

import config

HOLD = 60.0 * float(os.environ.get("WALL_FLOW_HOLD", 6))
BLEED = float(os.environ.get("WALL_FLOW_BLEED", 75))
KINDS = ("shader", "vj", "daily")
W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT


def _smooth(rng, cells=(5, 4)):
    """A soft random field 0..1 the size of the wall (a few cells, bicubically blown up)."""
    import cv2
    small = rng.random((cells[0] + 2, cells[1] + 2)).astype(np.float32)
    big = cv2.resize(small, (W + 2 * W // cells[1], H + 2 * H // cells[0]), interpolation=cv2.INTER_CUBIC)
    y, x = H // cells[0], W // cells[1]
    f = big[y:y + H, x:x + W]
    return (f - f.min()) / max(1e-6, float(f.max() - f.min()))


class Flow:
    def __init__(self):
        from display import library
        self.library = library
        self.rng = random.Random()
        self.order, self.cur, self.nxt = [], None, None
        self.held, self.k, self.last = 0.0, 0.0, None
        self.cur = self._make(self._next_id())

    def _next_id(self):
        if not self.order:
            ids = [e["id"] for e in self.library.public() if e.get("kind") in KINDS]
            self.rng.shuffle(ids)
            self.order = ids
        return self.order.pop()

    def _make(self, pid):
        p = self.library.make(pid, W, H)
        p.reset()
        print(f"[flow] {pid}", flush=True)
        # each piece keeps its own clock: the art of the day is written for real time, the gallery
        # pieces run at the app's pace (as in "One piece")
        pace = 1.0 if pid.startswith("daily-") else float(os.environ.get("WALL_ART_SPEED", "0.12"))
        return {"p": p, "pace": pace, "t": 30.0}

    @staticmethod
    def _render(piece, dt):
        d = dt * piece["pace"]
        piece["t"] += d
        return piece["p"].render(d, piece["t"])

    def _start_bleed(self):
        import cv2
        nrng = np.random.default_rng(self.rng.randrange(1 << 30))
        q = (W // 4, H // 4)
        self.cloud_a, self.cloud_b = (cv2.resize(_smooth(nrng), q, interpolation=cv2.INTER_AREA) for _ in range(2))
        self.nxt, self.k, self.w = self._make(self._next_id()), 0.0, None

    def _mask(self, new):
        """Where the new piece shows (0..1, HxWx1): a drifting cloud, nudged so its bright parts come first."""
        import cv2
        lum = cv2.resize(new.max(axis=2), (W // 4, H // 4), interpolation=cv2.INTER_AREA) / 255.0
        drift = 0.5 - 0.5 * np.cos(np.pi * self.k)
        field = 0.65 * (self.cloud_a * (1 - drift) + self.cloud_b * drift) + 0.35 * (1.0 - lum)
        edge = self.k * 1.5 - 0.25                       # sweeps from below 0 to above 1: everything is covered
        w = np.clip((edge - field) / 0.25 + 0.5, 0.0, 1.0)
        w = (w * w * (3 - 2 * w)).astype(np.float32)
        return cv2.resize(w, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]

    def __call__(self, t):
        dt = 0.04 if self.last is None else max(0.0, min(0.2, t - self.last))
        self.last = t
        img = self._render(self.cur, dt)
        if self.nxt is None:
            self.held += dt
            if self.held >= HOLD:
                self._start_bleed()
            return self._out(img)
        self.k = min(1.0, self.k + dt / BLEED)
        new = self._render(self.nxt, dt)
        self.n = getattr(self, "n", 0) + 1
        if self.n % 3 == 1 or getattr(self, "w", None) is None:
            self.w = self._mask(new)                    # the front moves slowly: a quarter-size mask every 3rd frame
        img = img + (new - img) * self.w
        if self.k >= 1.0:
            self.cur, self.nxt, self.held = self.nxt, None, 0.0
        return self._out(img)

    @staticmethod
    def _out(img):
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


_flow = None


def frame(t):
    global _flow
    if _flow is None:
        _flow = Flow()
    return _flow(t)
