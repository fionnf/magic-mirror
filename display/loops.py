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
        # white-background clips are blinding on an LED wall: skip anything that bright
        items = sorted(((k, v) for k, v in self.clips.items() if v.get("bright", 0.3) <= 0.5),
                       key=lambda kv: kv[1].get("motion", 0.5)) or sorted(self.clips.items(), key=lambda kv: kv[1].get("motion", 0.5))
        n = len(items)
        lo, hi = int(n * max(0.0, level - 0.35)), int(n * min(1.0, level + 0.35)) + 1
        pool = [k for k, _ in items[lo:hi] if k not in avoid] or [k for k, _ in items if k not in avoid] or [k for k, _ in items]
        return random.choice(pool)

    def path(self, name):
        return os.path.join(FOLDER, name + ".mp4")

    def info(self, name):
        return self.clips.get(name, {})


class LoopPlayer:
    """Sequential decoder with a fractional play head. Every clip loops seamlessly: the last K
    frames are cross-dissolved into the first K, and the loop runs over frames K..end."""
    K = 24                      # ~0.8 s dissolve at 29 fps

    def __init__(self, name, bank=None):
        import cv2
        self.bank = bank or LoopBank()
        self.name = name
        self.info = self.bank.info(name)
        self.frames = max(1, int(self.info.get("frames", 1)))
        self.fps = float(self.info.get("fps", 29))
        self.K = max(1, min(self.K, self.frames // 4))
        self.cap = cv2.VideoCapture(self.bank.path(name))
        self.head = []                                   # the first K frames (uint8 RGB)
        for _ in range(self.K):
            ok, fr = self.cap.read()
            if not ok:
                break
            self.head.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
        self.K = len(self.head) or 1
        self.total = max(1, self.frames - self.K)        # effective loop length
        self.seconds = self.total / self.fps
        self.pos, self.idx, self.last = 0.0, self.K - 1, None

    def _read(self):
        import cv2
        ok, fr = self.cap.read()
        if ok:
            self.idx += 1
            self.last = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB).astype(np.float32)
        return ok

    def frame(self, dt, rate):
        """Advance by rate*dt clip frames (rate in frames/s; the native speed is self.fps)."""
        import cv2
        self.pos += max(0.0, rate) * dt
        if self.pos >= self.total:
            self.pos %= self.total
        target = self.K + int(self.pos)                  # absolute frame in the file
        if target < self.idx:                            # wrapped: continue after the head
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.K)
            self.idx = self.K - 1
        steps = 0
        while self.idx < target and steps < 6:           # catch up (skip a few if the rate is high)
            if target - self.idx > 1:
                if self.cap.grab():
                    self.idx += 1
                else:
                    break
            elif not self._read():
                break
            steps += 1
        if self.last is None:
            self._read()
        if self.last is None:
            return np.zeros((192, 192, 3), np.float32)
        out = self.last
        tail = self.idx - (self.frames - self.K)         # 0..K-1 inside the dissolve
        if 0 <= tail < self.K:
            a = (tail + 1) / (self.K + 1)
            out = out * (1.0 - a) + self.head[tail].astype(np.float32) * a
        return out

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
