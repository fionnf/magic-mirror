"""Organic pieces that breathe with the music (same family as Lava & Coral): soft, slow, tonal.

Each piece: reset(), render(dt, t, f=None) -> float32 HxWx3 (0..255). `f` carries music features
(kick 0..1 smoothed, energy, groove) when used by the VJ; None in the galleries (= still breathing
on its own). Computed at half resolution and upscaled: 2-5 ms on a Pi 4.
"""
import math

import numpy as np
from PIL import Image

from display import art

_palette, _lut = art._palette, art._lut


def _up(arr, W, H):
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").resize((W, H), Image.BICUBIC)
    return np.asarray(img, np.float32)


class _Org:
    def __init__(self, W, H, name, lut, scale=2):
        self.W, self.H, self.name, self.lut = W, H, name, lut
        self.w, self.h = W // scale, H // scale
        y, x = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.x, self.y = x / self.w, y / self.h
        self.breath = 0.0

    def reset(self):
        pass

    def _pulse(self, dt, t, f):
        """A slow breath: the music's bass when there is music, a 7-second sine otherwise."""
        target = f.get("kick", 0.0) if f else 0.5 + 0.5 * math.sin(t * 0.9)
        self.breath += (target - self.breath) * min(1.0, dt / 0.5)
        return self.breath


class Jelly(_Org):
    """Jellyfish bells drifting upward, pulsing with the bass, tendrils trailing below."""

    def __init__(self, W, H, lut, n=5):
        super().__init__(W, H, "Jellyfish", lut)
        r = np.random.default_rng(12)
        self.n = n
        self.ph = r.uniform(0, 6.28, (n, 3)).astype(np.float32)
        self.sz = r.uniform(0.09, 0.16, n).astype(np.float32)

    def render(self, dt, t, f=None):
        b = self._pulse(dt, t, f)
        out = np.zeros((self.h, self.w), np.float32)
        for i in range(self.n):
            cx = 0.5 + 0.38 * math.sin(t * 0.05 + self.ph[i, 0])
            cy = (0.9 - ((t * 0.02 + self.ph[i, 1] * 0.1) % 1.0) * 1.1)       # rising slowly
            s = self.sz[i] * (1.0 + 0.25 * b + 0.08 * math.sin(t * 1.3 + self.ph[i, 2]))
            dx, dy = (self.x - cx) / s, (self.y - cy) / s
            bell = np.exp(-(dx * dx + np.where(dy < 0, dy * dy * 2.2, dy * dy * 0.9)) * 1.6)
            rim = np.exp(-((np.sqrt(dx * dx + dy * dy) - 1.0) ** 2) * 9.0) * 0.6
            for k in range(4):                                    # tendrils
                tx = cx + (k - 1.5) * s * 0.35 + 0.02 * math.sin(t * 0.8 + k + i)
                tend = np.exp(-((self.x - tx - 0.03 * np.sin(self.y * 18 + t * 1.1 + k)) ** 2) * 2500.0) \
                    * np.clip((self.y - cy) / (s * 3.5), 0, 1) * np.clip(1.6 - (self.y - cy) / (s * 3.5), 0, 1)
                out += tend * 0.35
            out += bell * 0.9 + rim
        v = np.clip(out, 0, 1) ** 0.9
        return _up(_lut(v, self.lut) * (0.75 + 0.25 * b), self.W, self.H)


class Cells(_Org):
    """Soft living cells (smooth Voronoi) whose walls glow; they swell with the bass."""

    def __init__(self, W, H, lut, n=14):
        super().__init__(W, H, "Living Cells", lut)
        r = np.random.default_rng(5)
        self.n = n
        self.c = r.random((n, 2)).astype(np.float32)
        self.ph = r.uniform(0, 6.28, (n, 2)).astype(np.float32)

    def render(self, dt, t, f=None):
        b = self._pulse(dt, t, f)
        cx = self.c[:, 0] + 0.07 * np.sin(t * 0.07 + self.ph[:, 0])
        cy = self.c[:, 1] + 0.07 * np.cos(t * 0.06 + self.ph[:, 1])
        d = np.sqrt((self.x[..., None] - cx) ** 2 + (self.y[..., None] - cy) ** 2)
        d.sort(axis=-1)
        d1, d2 = d[..., 0], d[..., 1]
        wall = np.exp(-((d2 - d1) / (0.012 + 0.01 * b)) ** 2)                   # bright membranes
        body = np.exp(-d1 / (0.11 + 0.05 * b))                                  # glowing nuclei
        v = np.clip(0.15 + 0.55 * body + 0.6 * wall, 0, 1)
        return _up(_lut(v, self.lut), self.W, self.H)


class Breath(_Org):
    """Concentric soft rings that expand from the centre with every breath of the bass."""

    def __init__(self, W, H, lut):
        super().__init__(W, H, "Breath", lut)
        self.r = np.sqrt((self.x - 0.5) ** 2 + (self.y - 0.5) ** 2)
        self.phase = 0.0

    def render(self, dt, t, f=None):
        b = self._pulse(dt, t, f)
        self.phase += dt * (0.08 + 0.35 * b)                                     # rings travel out on the beat
        v = 0.5 + 0.5 * np.sin(self.r * 22.0 - self.phase * 6.0)
        v = v ** (2.2 - 1.2 * b) * np.clip(1.2 - self.r * 1.8, 0, 1)
        glow = np.exp(-self.r * self.r * (16.0 - 8.0 * b)) * 0.6
        return _up(_lut(np.clip(v * 0.8 + glow, 0, 1), self.lut), self.W, self.H)


def pieces(W, H):
    P = _palette
    sea = P([(2, 8, 22), (8, 60, 110), (40, 170, 190), (200, 245, 240)])
    plum = P([(18, 4, 28), (90, 20, 100), (200, 80, 160), (255, 220, 235)])
    moss = P([(3, 12, 6), (15, 70, 40), (80, 170, 100), (220, 250, 200)])
    return [Jelly(W, H, sea), Cells(W, H, plum), Breath(W, H, moss)]
