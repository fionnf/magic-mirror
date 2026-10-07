"""Slow generative art for the wall — a gallery of five pieces, ~60 s each,
cross-fading into one another.

  Ink Flow      particles drifting on a flow field, fading ink trails
  Colour Field  breathing Rothko-like blocks of colour
  Lava          slow metaballs merging and parting
  Coral         Gray-Scott reaction-diffusion growing like coral
  Interference  two orbiting ring systems making moiré

frame(t) keeps state between calls (the ink trails and the coral need
memory), so call it with increasing t. LOOP_SEC = one full tour.
"""
import math

import numpy as np
from PIL import Image

import config

PIECE_SEC = 60.0
XFADE = 4.0


def _grid(W, H):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    return x, y


def _palette(stops, n=256):
    """Piecewise-linear colour ramp -> (n, 3) float32 LUT."""
    stops = np.array(stops, np.float32)
    xs = np.linspace(0, 1, len(stops))
    v = np.linspace(0, 1, n)
    return np.stack([np.interp(v, xs, stops[:, c]) for c in range(3)], -1).astype(np.float32)


def _lut(field, lut):
    idx = np.clip((field * (len(lut) - 1)).astype(int), 0, len(lut) - 1)
    return lut[idx]


# ------------------------------------------------------------- pieces ---

class InkFlow:
    name = "Ink Flow"
    LUT = _palette([(10, 20, 60), (20, 120, 160), (240, 200, 120), (255, 240, 220)])

    def __init__(self, W, H, n=700):
        self.W, self.H, self.n = W, H, n
        self.reset()

    def reset(self):
        rs = np.random.default_rng(1)
        self.p = rs.random((self.n, 2)).astype(np.float32) * [self.W, self.H]
        self.hue = rs.random(self.n).astype(np.float32)
        self.acc = np.zeros((self.H, self.W, 3), np.float32)

    def render(self, dt, t):
        x, y = self.p[:, 0], self.p[:, 1]
        # divergence-free (curl) flow from a stream function psi: particles swirl
        # and weave but never pile up onto a few lines.
        a1, b1, a2 = 0.028, 0.023, 0.011
        s1, s2, s3 = t * 0.05, t * 0.04, t * 0.03
        dpsi_dx = (a1 * np.cos(x * a1 + s1) * np.cos(y * b1 - s2)
                   + 0.7 * a2 * np.cos((x + y) * a2 + s3))
        dpsi_dy = (-b1 * np.sin(x * a1 + s1) * np.sin(y * b1 - s2)
                   + 0.7 * a2 * np.cos((x + y) * a2 + s3))
        vx, vy = dpsi_dy, -dpsi_dx
        norm = np.sqrt(vx * vx + vy * vy) + 1e-6
        step = 12.0 * dt                                         # slow: ~12 px/s
        self.p[:, 0] = (x + vx / norm * step) % self.W
        self.p[:, 1] = (y + vy / norm * step) % self.H
        respawn = np.random.random(self.n) < 0.12 * dt           # ~12 %/s fresh ink
        k = int(respawn.sum())
        if k:
            self.p[respawn] = np.random.random((k, 2)).astype(np.float32) * [self.W, self.H]
        self.acc *= 0.985 ** (dt * 25)                           # trails fade slowly
        xi, yi = self.p[:, 0].astype(int), self.p[:, 1].astype(int)
        col = _lut(self.hue, self.LUT) * 0.09
        np.add.at(self.acc, (yi, xi), col)
        return 255.0 * (1.0 - np.exp(-self.acc / 110.0))          # soft tone-map, no clipping


class ColourField:
    name = "Colour Field"
    PALETTES = [[(120, 30, 40), (200, 90, 40), (60, 20, 50)],
                [(20, 40, 90), (60, 120, 140), (230, 190, 120)],
                [(80, 20, 90), (200, 70, 120), (30, 30, 60)],
                [(20, 60, 50), (180, 160, 80), (60, 30, 20)]]

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.x, self.y = _grid(W, H)
        self.grain = np.random.default_rng(3).normal(0, 4, (H, W, 1)).astype(np.float32)

    def reset(self):
        pass

    def render(self, dt, t):
        W, H = self.W, self.H
        k = (t / 20.0) % len(self.PALETTES)
        i0, f = int(k), k - int(k)
        f = f * f * (3 - 2 * f)                                  # smoothstep
        A = np.array(self.PALETTES[i0], np.float32)
        B = np.array(self.PALETTES[(i0 + 1) % len(self.PALETTES)], np.float32)
        cols = A * (1 - f) + B * f
        out = np.zeros((H, W, 3), np.float32) + cols[2] * 0.4
        bands = [(0.08, 0.42), (0.5, 0.92)]
        for j, (a, b) in enumerate(bands):
            breathe = 0.015 * math.sin(t * 0.25 + j * 2)
            top, bot = (a - breathe) * H, (b + breathe) * H
            soft = 6.0
            m = (np.clip((self.y - top) / soft, 0, 1) * np.clip((bot - self.y) / soft, 0, 1)
                 * np.clip((self.x - W * 0.08) / soft, 0, 1)
                 * np.clip((W * 0.92 - self.x) / soft, 0, 1))
            out = out * (1 - m[..., None]) + cols[j] * m[..., None]
        return np.clip(out + self.grain, 0, 255)


class Lava:
    name = "Lava"
    LUT = _palette([(5, 0, 10), (90, 10, 40), (230, 70, 30), (255, 190, 80), (255, 250, 220)])

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.x, self.y = _grid(W, H)

    def reset(self):
        pass

    def render(self, dt, t):
        W, H = self.W, self.H
        f = np.zeros((H, W), np.float32)
        for i in range(6):
            s = 0.05 + i * 0.013
            cx = W * (0.5 + 0.33 * math.sin(t * s + i * 1.7))
            cy = H * (0.5 + 0.38 * math.sin(t * s * 0.8 + i * 2.9))
            r = (14 + 5 * math.sin(t * 0.1 + i)) ** 2
            f += r / ((self.x - cx) ** 2 + (self.y - cy) ** 2 + 1.0)
        v = np.clip((f - 0.35) / 1.6, 0, 1) ** 0.8
        return _lut(v, self.LUT)


class Coral:
    name = "Coral"
    LUT = _palette([(4, 8, 25), (10, 60, 90), (40, 170, 170), (220, 250, 240)])

    def __init__(self, W, H, scale=2):
        self.W, self.H, self.s = W, H, scale
        self.reset()

    def reset(self):
        h, w = self.H // self.s, self.W // self.s
        self.A = np.ones((h, w), np.float32)
        self.B = np.zeros((h, w), np.float32)
        rs = np.random.default_rng(5)
        for _ in range(9):                                       # seeds
            cy, cx = rs.integers(8, h - 8), rs.integers(8, w - 8)
            self.B[cy - 3:cy + 3, cx - 3:cx + 3] = 1.0

    @staticmethod
    def _lap(Z):
        return (np.roll(Z, 1, 0) + np.roll(Z, -1, 0) + np.roll(Z, 1, 1) + np.roll(Z, -1, 1)
                - 4 * Z)

    def render(self, dt, t):
        F, k, Da, Db = 0.0545, 0.062, 1.0, 0.5                   # 'coral' regime
        for _ in range(max(1, int(round(dt * 100)))):            # ~100 steps/s: slow growth
            AB2 = self.A * self.B * self.B
            self.A += Da * 0.2 * self._lap(self.A) - AB2 + F * (1 - self.A)
            self.B += Db * 0.2 * self._lap(self.B) + AB2 - (k + F) * self.B
        v = np.clip(self.B * 2.6, 0, 1)
        img = _lut(v, self.LUT)
        return np.repeat(np.repeat(img, self.s, 0), self.s, 1)[:self.H, :self.W]


class Interference:
    name = "Interference"

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.x, self.y = _grid(W, H)

    def reset(self):
        pass

    def render(self, dt, t):
        W, H = self.W, self.H
        c1 = (W * (0.5 + 0.25 * math.cos(t * 0.07)), H * (0.5 + 0.25 * math.sin(t * 0.07)))
        c2 = (W * (0.5 + 0.25 * math.cos(t * 0.07 + math.pi)), H * (0.5 + 0.25 * math.sin(t * 0.05 + math.pi)))
        d1 = np.sqrt((self.x - c1[0]) ** 2 + (self.y - c1[1]) ** 2)
        d2 = np.sqrt((self.x - c2[0]) ** 2 + (self.y - c2[1]) ** 2)
        v = 0.5 + 0.5 * np.sin(d1 * 0.55 - t * 0.6) * np.sin(d2 * 0.55 - t * 0.45)
        v = v ** 2.2
        gold = np.array([255, 190, 90], np.float32)
        deep = np.array([10, 6, 25], np.float32)
        return deep + (gold - deep) * v[..., None]


# ------------------------------------------------------------- gallery ---

class Gallery:
    def __init__(self):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        self.pieces = [InkFlow(W, H), ColourField(W, H), Lava(W, H), Coral(W, H),
                       Interference(W, H)]
        self.last_t = None
        self.current = -1

    def __call__(self, t):
        dt = 0.04 if self.last_t is None else max(0.0, min(0.2, t - self.last_t))
        self.last_t = t
        n = len(self.pieces)
        k = int(t // PIECE_SEC) % n
        u = t % PIECE_SEC
        if k != self.current:
            self.current = k
            self.pieces[k].reset()
        img = self.pieces[k].render(dt, t)
        # cross-fade: in the last XFADE seconds, blend in the next piece
        if u > PIECE_SEC - XFADE:
            j = (k + 1) % n
            if u - dt <= PIECE_SEC - XFADE:
                self.pieces[j].reset()
            a = (u - (PIECE_SEC - XFADE)) / XFADE
            a = a * a * (3 - 2 * a)
            img = img * (1 - a) + self.pieces[j].render(dt, t) * a
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


LOOP_SEC = PIECE_SEC * 5
_gallery = None


def frame(t):
    global _gallery
    if _gallery is None:
        _gallery = Gallery()
    return _gallery(t)
