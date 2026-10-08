"""Light art gallery: soft, filled, slowly evolving pieces (stained-glass cells, a morphing
Julia set, a kaleidoscope, long-exposure particle trails, a nebula). Same piece interface as
display/art.py: reset(), render(dt, t) -> float32 HxWx3 in 0..255, all numpy (cheap on the Pi).
"""
import math

import numpy as np

import config
from display import art

_lut, _palette = art._lut, art._palette


class _Soft:
    def __init__(self, W, H, name, lut):
        self.W, self.H, self.name, self.lut = W, H, name, lut
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        self.x, self.y = x, y

    def reset(self):
        pass


class StainedGlass(_Soft):
    """Voronoi cells that drift; each is a flat glowing colour with dark lead lines."""

    def __init__(self, W, H, lut, n=22):
        super().__init__(W, H, "Stained Glass", lut)
        self.n = n
        r = np.random.default_rng(5)
        self.base = r.random((n, 2)).astype(np.float32)
        self.ph = r.uniform(0, 6.28, (n, 4)).astype(np.float32)
        self.hue = r.random(n).astype(np.float32)

    def render(self, dt, t):
        W, H = self.W, self.H
        sx = (self.base[:, 0] + 0.09 * np.sin(t * 0.11 + self.ph[:, 0])) * W
        sy = (self.base[:, 1] + 0.09 * np.cos(t * 0.09 + self.ph[:, 1])) * H
        d = (self.x[..., None] - sx) ** 2 + (self.y[..., None] - sy) ** 2
        order = np.argsort(d, axis=-1)
        d1 = np.take_along_axis(d, order[..., :1], -1)[..., 0]
        d2 = np.take_along_axis(d, order[..., 1:2], -1)[..., 0]
        cell = order[..., 0]
        edge = np.clip((np.sqrt(d2) - np.sqrt(d1)) / 3.0, 0, 1)             # 0 on the lead line
        v = (self.hue[cell] + 0.12 * np.sin(t * 0.2 + self.ph[cell, 2])) % 1.0
        glow = 0.55 + 0.45 * np.exp(-d1 / (W * W * 0.012))                   # brighter near centres
        return _lut(np.clip(v * 0.85 + 0.1, 0, 1), self.lut) * (edge * glow)[..., None]


class JuliaMorph(_Soft):
    """A Julia set whose constant slowly circles a point, rendered as smooth glowing bands."""

    def __init__(self, W, H, lut, iters=28):
        super().__init__(W, H, "Julia Morph", lut)
        self.iters = iters
        self.zx0 = (self.x / W - 0.5) * 3.0
        self.zy0 = (self.y / H - 0.5) * 3.0

    def render(self, dt, t):
        a = t * 0.04
        c = complex(-0.74 + 0.07 * math.cos(a), 0.15 + 0.09 * math.sin(a * 1.3))
        z = (self.zx0 + 1j * self.zy0).astype(np.complex64)
        alive = np.ones(z.shape, bool)
        mu = np.zeros(z.shape, np.float32)
        for i in range(self.iters):
            z = np.where(alive, z * z + c, z)
            esc = alive & (z.real * z.real + z.imag * z.imag > 16)
            mu[esc] = i + 1 - np.log2(np.log(np.abs(z[esc]) + 1e-9) + 1e-9)
            alive &= ~esc
        v = (mu / self.iters * 1.6 + t * 0.012) % 1.0
        v[alive] = 0.0
        return _lut(np.clip(v, 0, 1), self.lut) * (0.35 + 0.65 * (~alive))[..., None]


class Kaleido(_Soft):
    """A slowly turning plasma folded into a mirrored kaleidoscope."""

    def __init__(self, W, H, lut, folds=6):
        super().__init__(W, H, "Kaleidoscope", lut)
        self.folds = folds
        self.dx, self.dy = self.x - W / 2, self.y - H / 2
        self.r = np.sqrt(self.dx ** 2 + self.dy ** 2) / (W / 2)
        self.a = np.arctan2(self.dy, self.dx)

    def render(self, dt, t):
        seg = math.pi / self.folds
        a = np.abs(((self.a + t * 0.05) % (2 * seg)) - seg)             # mirror fold
        px, py = self.r * np.cos(a), self.r * np.sin(a)
        v = (np.sin(px * 6 + t * 0.4) + np.sin(py * 7 - t * 0.3) +
             np.sin((px + py) * 5 + t * 0.2) + np.sin(self.r * 9 - t * 0.5)) / 4
        v = 0.5 + 0.5 * v
        return _lut(np.clip(v, 0, 1), self.lut) * np.clip(1.15 - self.r * 0.55, 0, 1)[..., None]


class Trails(_Soft):
    """Particles riding a smooth flow field, painting long-exposure trails that fade."""

    def __init__(self, W, H, lut, n=1100):
        super().__init__(W, H, "Long Exposure", lut)
        self.n = n
        self.reset()

    def reset(self):
        r = np.random.default_rng(3)
        self.p = r.random((self.n, 2)).astype(np.float32) * [self.W, self.H]
        self.life = r.random(self.n).astype(np.float32)
        self.buf = np.zeros((self.H, self.W), np.float32)
        self.last = None

    def render(self, dt, t):
        W, H = self.W, self.H
        steps = 1 if self.last is None else max(1, min(3, int(round((t - self.last) / 0.04))))
        self.last = t
        for _ in range(steps):
            x, y = self.p[:, 0], self.p[:, 1]
            ang = (np.sin(x * 0.03 + t * 0.12) + np.sin(y * 0.037 - t * 0.09) +
                   np.sin((x + y) * 0.021 + t * 0.07)) * 1.3
            self.p[:, 0] += np.cos(ang) * 1.3 + np.random.normal(0, 0.25, self.n)
            self.p[:, 1] += np.sin(ang) * 1.3 + np.random.normal(0, 0.25, self.n)
            self.life += 0.006
            dead = (self.life > 1) | (self.p[:, 0] < 0) | (self.p[:, 0] >= W) | (self.p[:, 1] < 0) | (self.p[:, 1] >= H)
            if dead.any():
                k = int(dead.sum())
                self.p[dead] = np.random.random((k, 2)).astype(np.float32) * [W, H]
                self.life[dead] = 0.0
            self.buf *= 0.975
            xi, yi = self.p[:, 0].astype(int), self.p[:, 1].astype(int)
            np.add.at(self.buf, (yi, xi), 0.22 * np.sin(np.pi * self.life))
        v = np.clip(self.buf, 0, 1)
        return _lut(v, self.lut) * np.clip(v * 3.0 + 0.0, 0, 1)[..., None]


class Nebula(_Soft):
    """Layered, slowly shifting noise clouds with a few stars."""

    def __init__(self, W, H, lut):
        super().__init__(W, H, "Nebula", lut)
        self.stars = np.random.default_rng(9).random((H, W)) > 0.9975

    def render(self, dt, t):
        x, y = self.x / self.W, self.y / self.H
        v = np.zeros_like(x)
        for k, (fx, fy, sp) in enumerate(((3.0, 2.2, 0.05), (5.5, 4.1, -0.07), (9.5, 7.0, 0.09))):
            amp = 0.55 / (k + 1)
            v += amp * np.sin(x * fx * 3 + np.sin(y * fy * 2 + t * sp * 3) * 1.4 + t * sp) * \
                np.cos(y * fy * 3 + np.sin(x * fx * 2 - t * sp * 2) * 1.3)
        v = np.clip(0.5 + v * 0.7, 0, 1) ** 1.6
        out = _lut(v, self.lut)
        s = self.stars * (0.5 + 0.5 * np.sin(self.x * 7 + t * 1.3 + self.y))
        return np.clip(out + (s * 200)[..., None], 0, 255)


class LightGallery(art.Gallery):
    def __init__(self):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        P = _palette
        jewel = P([(10, 4, 30), (60, 20, 140), (200, 40, 120), (255, 170, 60), (255, 240, 200)])
        ocean = P([(2, 6, 25), (10, 60, 120), (20, 170, 190), (160, 240, 230)])
        dusk = P([(15, 6, 35), (90, 30, 110), (230, 90, 120), (255, 200, 140)])
        forest = P([(3, 12, 8), (15, 80, 60), (90, 190, 120), (230, 250, 190)])
        self.pieces = [StainedGlass(W, H, jewel), Nebula(W, H, dusk), JuliaMorph(W, H, ocean),
                       Trails(W, H, forest), Kaleido(W, H, jewel), Trails(W, H, dusk, n=1500),
                       StainedGlass(W, H, ocean, n=30), Kaleido(W, H, forest, folds=8)]
        self.last_t = None
        self.current = -1


LOOP_SEC = art.PIECE_SEC * 8
_gallery = None


def frame(t):
    global _gallery
    if _gallery is None:
        _gallery = LightGallery()
    return _gallery(t)
