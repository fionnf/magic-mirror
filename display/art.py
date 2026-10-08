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


# ================================================== Lava & Coral gallery ===

class LavaPlus:
    """Metaball variations: style = glow | lamp | contour | chrome."""

    def __init__(self, W, H, name, style, lut=None, n=6, speed=1.0):
        self.W, self.H, self.name, self.style = W, H, name, style
        self.lut, self.n, self.speed = lut, n, speed
        self.x, self.y = _grid(W, H)

    def reset(self):
        pass

    def _field(self, t):
        W, H = self.W, self.H
        f = np.zeros((H, W), np.float32)
        ts = t * self.speed
        for i in range(self.n):
            if self.style == "lamp":                             # rise and sink in lanes
                cx = W * (0.2 + 0.6 * ((i * 0.37) % 1)) + 6 * math.sin(ts * 0.3 + i)
                cy = H * (0.5 + 0.42 * math.sin(ts * (0.06 + i * 0.011) + i * 2.1))
                r = (13 + 4 * math.sin(ts * 0.2 + i * 1.3)) ** 2
                sx, sy = 1.0, 0.8                                # slightly tall blobs
            else:
                s = 0.05 + i * 0.013
                cx = W * (0.5 + 0.33 * math.sin(ts * s + i * 1.7))
                cy = H * (0.5 + 0.38 * math.sin(ts * s * 0.8 + i * 2.9))
                r = (14 + 5 * math.sin(ts * 0.1 + i)) ** 2
                sx = sy = 1.0
            f += r / (((self.x - cx) * sx) ** 2 + ((self.y - cy) * sy) ** 2 + 1.0)
        if self.style == "lamp":                                 # hot puddle + cap
            f += 260 / ((self.y - (H + 4)) ** 2 + 1.0) * (1 + 0.15 * math.sin(ts * 0.4))
            f += 160 / ((self.y + 4) ** 2 + 1.0)
        return f

    def render(self, dt, t):
        W, H = self.W, self.H
        f = self._field(t)
        if self.style == "lamp":                                 # distinct blobs in purple glass
            v = np.clip((f - 1.0) / 1.4, 0, 1) ** 0.7
            halo = np.clip((f - 0.55) / 0.45, 0, 1)[..., None] * 0.35
            bg = _palette([(40, 10, 70), (95, 25, 120)])[
                np.clip((self.y / H * 255).astype(int), 0, 255)]
            blob = _lut(v, self.lut)
            a = np.clip(v * 4, 0, 1)[..., None]
            glow = np.array([255, 90, 40], np.float32)
            return (bg * (1 - halo) + glow * halo) * (1 - a) + blob * a
        if self.style == "glow":
            v = np.clip((f - 0.35) / 1.6, 0, 1) ** 0.8
            return _lut(v, self.lut)
        if self.style == "contour":                              # neon topography
            lv = np.log1p(f) * 5.0
            line = np.clip(1 - np.abs(lv - np.round(lv)) / 0.12, 0, 1) ** 1.5
            hue = (np.round(lv) * 0.09 + t * 0.01) % 1.0
            col = np.stack([0.5 + 0.5 * np.sin(6.283 * hue),
                            0.5 + 0.5 * np.sin(6.283 * (hue + 0.33)),
                            0.5 + 0.5 * np.sin(6.283 * (hue + 0.66))], -1)
            inside = np.clip((f - 1.0) / 2.0, 0, 1)[..., None] * 0.18
            return (col * line[..., None] * 255 + col * inside * 255)
        # chrome: normal from the field gradient, fake environment reflection
        g = np.log1p(f)
        gy, gx = np.gradient(g)
        inside = np.clip((f - 1.0) * 3, 0, 1)
        nz = 1.0 / np.sqrt(gx * gx * 60 + gy * gy * 60 + 1)
        ny = gy * np.sqrt(60) * nz
        env = 0.5 + 0.5 * np.tanh(-ny * 2.5)                      # sky above, floor below
        spec = np.clip(nz * 0.6 - 0.6 * gx * np.sqrt(60) * nz - 0.5 * ny, 0, 1) ** 12
        steel = (np.array([60, 70, 90], np.float32) * (1 - env[..., None])
                 + np.array([210, 220, 240], np.float32) * env[..., None])
        img = steel + 255 * spec[..., None]
        bg = np.array([8, 10, 18], np.float32)
        return bg + (img - bg) * inside[..., None]


class CoralPlus:
    """Gray-Scott variations: params, palette, seeding and optional relief light."""

    def __init__(self, W, H, name, F, k, lut, seed="random", relief=False, scale=2,
                 steps_per_sec=110):
        self.W, self.H, self.name = W, H, name
        self.F, self.k, self.lut, self.seed = F, k, lut, seed
        self.relief, self.s, self.sps = relief, scale, steps_per_sec
        self.reset()

    def reset(self):
        h, w = self.H // self.s, self.W // self.s
        self.A = np.ones((h, w), np.float32)
        self.B = np.zeros((h, w), np.float32)
        rs = np.random.default_rng(abs(hash(self.name)) % 1000)
        if self.seed == "centre":
            cy, cx = h // 2, w // 2
            self.B[cy - 4:cy + 4, cx - 4:cx + 4] = 1.0
            self.B += (rs.random((h, w)) < 0.0015).astype(np.float32)   # a few spores
        else:
            for _ in range(10):
                cy, cx = rs.integers(8, h - 8), rs.integers(8, w - 8)
                self.B[cy - 3:cy + 3, cx - 3:cx + 3] = 1.0

    def render(self, dt, t):
        lap = Coral._lap
        for _ in range(max(1, int(round(dt * self.sps)))):
            AB2 = self.A * self.B * self.B
            self.A += 0.2 * lap(self.A) - AB2 + self.F * (1 - self.A)
            self.B += 0.1 * lap(self.B) + AB2 - (self.k + self.F) * self.B
            np.clip(self.A, 0.0, 1.0, out=self.A)                # keep the sim bounded
            np.clip(self.B, 0.0, 1.0, out=self.B)
        v = np.clip(self.B * 2.6, 0, 1)
        img = _lut(v, self.lut)
        if self.relief:                                          # carved, lit from top-left
            gy, gx = np.gradient(v)
            nx, ny, nz = -gx * 6, -gy * 6, np.ones_like(v)
            n = np.sqrt(nx * nx + ny * ny + nz * nz)
            light = np.clip((-0.55 * nx - 0.6 * ny + 0.58 * nz) / n, 0, 1)
            img = img * (0.35 + 0.95 * light[..., None])
        return np.repeat(np.repeat(img, self.s, 0), self.s, 1)[:self.H, :self.W]


class LavaCoralGallery(Gallery):
    def __init__(self):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        lava_lut = Lava.LUT
        bio = _palette([(0, 5, 20), (0, 50, 90), (0, 160, 170), (120, 255, 200), (230, 255, 250)])
        lamp = _palette([(40, 10, 70), (200, 30, 40), (255, 110, 30), (255, 200, 90)])
        brain = _palette([(5, 20, 10), (20, 110, 60), (90, 200, 120), (220, 255, 200)])
        pink = _palette([(15, 5, 20), (120, 20, 80), (255, 110, 170), (255, 230, 240)])
        gold = _palette([(5, 3, 0), (90, 50, 0), (230, 170, 50), (255, 240, 180)])
        bloom = _palette([(5, 10, 30), (40, 30, 110), (230, 90, 140), (255, 210, 160)])
        self.pieces = [
            CoralPlus(W, H, "3D Brain Coral", 0.0545, 0.062, brain, relief=True),
            LavaPlus(W, H, "Neon Topography", "contour", n=6, speed=0.8),
            CoralPlus(W, H, "Bloom", 0.0545, 0.062, bloom, seed="centre", relief=True),
            CoralPlus(W, H, "Mitosis", 0.0367, 0.0649, pink),
            LavaPlus(W, H, "Bioluminescence", "glow", bio, n=7, speed=0.7),
            CoralPlus(W, H, "Gold Labyrinth", 0.029, 0.057, gold, relief=True),
            Lava(W, H),
            Coral(W, H),
        ]
        self.last_t = None
        self.current = -1


LAVA_CORAL_LOOP_SEC = PIECE_SEC * 8
_lc_gallery = None


def frame_lava_coral(t):
    global _lc_gallery
    if _lc_gallery is None:
        _lc_gallery = LavaCoralGallery()
    return _lc_gallery(t)
