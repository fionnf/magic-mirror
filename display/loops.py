"""VJ loops: real video loops (e.g. Beeple's free CC packs) played on the wall, speed-matched to
the music's tempo so one loop spans a whole number of beats.

assets/loops/<name>.mp4 + index.json come from tools/make_loops.py (192x192, 29 fps).

    bank = LoopBank()              # the index
    bank.pick(level, avoid=...)    # a clip whose motion suits the party level
    player = LoopPlayer(name)
    img = player.frame(dt, rate)   # rate = clip frames per second to advance (float32 HxWx3 RGB)
"""
import json
import os
import random

import numpy as np

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(_HERE, "assets", "loops")
INDEX = os.path.join(FOLDER, "index.json")


class LoopBank:
    def __init__(self):
        self._mtime, self.clips = None, {}
        self.reload()

    def reload(self):
        try:
            m = os.path.getmtime(INDEX)
        except OSError:
            self.clips = {}
            return
        if m != self._mtime:
            try:
                with open(INDEX) as fh:
                    self.clips = {k: v for k, v in json.load(fh).items()
                                  if os.path.exists(os.path.join(FOLDER, k + ".mp4"))}
            except Exception:
                self.clips = {}
            self._mtime = m

    def __len__(self):
        return len(self.clips)

    def pick(self, level, avoid=()):
        """A clip whose motion suits the party level (0 calm .. 1 wild), not one of `avoid`."""
        self.reload()
        if not self.clips:
            return None
        items = sorted(self.clips.items(), key=lambda kv: kv[1].get("motion", 0.5))
        n = len(items)
        lo, hi = int(n * max(0.0, level - 0.35)), int(n * min(1.0, level + 0.35)) + 1
        pool = [k for k, _ in items[lo:hi] if k not in avoid] or [k for k, _ in items if k not in avoid] or [k for k, _ in items]
        return random.choice(pool)

    def path(self, name):
        return os.path.join(FOLDER, name + ".mp4")

    def info(self, name):
        return self.clips.get(name, {})


class LoopPlayer:
    """Sequential decoder with a fractional play head; loops seamlessly."""

    def __init__(self, name, bank=None):
        import cv2
        self.bank = bank or LoopBank()
        self.name = name
        self.info = self.bank.info(name)
        self.frames = max(1, int(self.info.get("frames", 1)))
        self.fps = float(self.info.get("fps", 29))
        self.cap = cv2.VideoCapture(self.bank.path(name))
        self.pos, self.idx, self.last = 0.0, -1, None

    def _next(self):
        import cv2
        ok, fr = self.cap.read()
        if not ok:                                        # end: wrap around
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, fr = self.cap.read()
            self.idx = -1
            if not ok:
                return
        self.idx += 1
        self.last = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB).astype(np.float32)

    def frame(self, dt, rate):
        """Advance by rate*dt clip frames (rate in frames/s; the native speed is self.fps)."""
        self.pos += max(0.0, rate) * dt
        target = int(self.pos)
        if target >= self.frames:                          # keep the head inside the loop
            self.pos -= self.frames * (target // self.frames)
            target = int(self.pos)
            if self.idx > target:
                self.idx = -1
                import cv2
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        steps = 0
        while self.idx < target and steps < 6:             # catch up (skip a few if the rate is high)
            if target - self.idx > 1:
                self.cap.grab()
                self.idx += 1
            else:
                self._next()
            steps += 1
        if self.last is None:
            self._next()
        return self.last if self.last is not None else np.zeros((192, 192, 3), np.float32)

    def close(self):
        try:
            self.cap.release()
        except Exception:
            pass


def beats_for(seconds, period):
    """How many beats one loop should span so its native length stays about the same: 2/4/8/16."""
    if period <= 0:
        return 0
    want = seconds / period
    return min((2, 4, 8, 16), key=lambda b: abs(b - want))
