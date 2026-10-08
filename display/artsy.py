"""Artsy gallery: slow, painterly pieces (marbling, oil slick, watercolour, Kandinsky, op-art
stripes, a drifting Mondrian). Same piece interface as display/art.py. Soft pieces are computed at
half resolution and upscaled (4x cheaper, and it looks like paint); each piece is built to stay
well under ~8 ms on a Pi 4 so the 29 fps panel refresh never stutters.
"""
import math

import numpy as np
from PIL import Image, ImageDraw

import config
from display import art

_palette, _lut = art._palette, art._lut


def _up(arr, W, H):
    """float32 HxWx3 (small) -> float32 (H, W, 3) smooth upscale."""
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").resize((W, H), Image.BICUBIC)
    return np.asarray(img, np.float32)


class _P:
    def __init__(self, W, H, name, scale=2):
        self.W, self.H, self.name = W, H, name
        self.w, self.h = W // scale, H // scale
        y, x = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.x, self.y = x / self.w, y / self.h                 # 0..1 coordinates

    def reset(self):
        pass


class Marbling(_P):
    """Suminagashi-style marbling: layered domain warps turned into banded ink stripes."""

    def __init__(self, W, H, lut):
        super().__init__(W, H, "Marbling")
        self.lut = lut

    def render(self, dt, t):
        x, y = self.x * 3.0, self.y * 3.0
        for k, (a, f) in enumerate(((0.55, 1.3), (0.35, 2.3), (0.18, 4.1))):
            x, y = (x + a * np.sin(y * f + t * (0.07 + 0.03 * k) + k),
                    y + a * np.cos(x * f - t * (0.06 + 0.02 * k) + 2 * k))
        v = 0.5 + 0.5 * np.sin((x + y) * 4.2 + np.sin(x * 2.0 - y * 1.5) * 1.5)
        v = np.where(v > 0.5, v, v * 0.55)                      # crisp ink lines, calm gaps
        return _up(_lut(np.clip(v, 0, 1), self.lut), self.W, self.H)


class OilSlick(_P):
    """Thin-film interference: a slowly flowing field read through a cyclic iridescent palette."""

    def __init__(self, W, H):
        super().__init__(W, H, "Oil Slick")
        self.lut = _palette([(6, 8, 28), (20, 70, 150), (30, 170, 170), (220, 245, 240), (30, 170, 170),
                             (20, 70, 150), (6, 8, 28)])

    def render(self, dt, t):
        x, y = self.x * 2.2, self.y * 2.2
        f = (np.sin(x * 2.1 + t * 0.09 + np.sin(y * 1.7 - t * 0.06) * 1.6) +
             np.sin(y * 2.7 - t * 0.07 + np.sin(x * 1.3 + t * 0.05) * 1.4) +
             np.sin((x + y) * 1.5 + t * 0.04)) / 3.0
        v = (f * 1.15 + 0.5 + t * 0.012) % 1.0
        out = _lut(v, self.lut) * (0.55 + 0.45 * np.clip(0.5 + f, 0, 1))[..., None]
        return _up(out, self.W, self.H)


class Watercolour(_P):
    """Big soft pigment blooms that overlap and bleed, with the darker rim real washes have."""

    def __init__(self, W, H, lut):
        super().__init__(W, H, "Watercolour", scale=3)
        self.lut = lut
        r = np.random.default_rng(21)
        self.c = r.random((7, 2)).astype(np.float32)
        self.ph = r.uniform(0, 6.28, (7, 3)).astype(np.float32)
        self.size = r.uniform(0.16, 0.30, 7).astype(np.float32)
        self.hue = r.random(7).astype(np.float32)

    def render(self, dt, t):
        out = np.zeros((self.h, self.w, 3), np.float32)
        for i in range(7):
            cx = self.c[i, 0] + 0.10 * math.sin(t * 0.05 + self.ph[i, 0])
            cy = self.c[i, 1] + 0.10 * math.cos(t * 0.04 + self.ph[i, 1])
            wob = 1 + 0.18 * np.sin(np.arctan2(self.y - cy, self.x - cx) * 3 + t * 0.1 + self.ph[i, 2])
            d = np.sqrt((self.x - cx) ** 2 + (self.y - cy) ** 2) / (self.size[i] * wob)
            body = np.clip(1.0 - d, 0, 1) ** 0.8
            rim = np.exp(-((d - 0.92) ** 2) / 0.02) * 0.45
            col = self.lut[int(((self.hue[i] + t * 0.004) % 1.0) * 255)]
            out += (body * 0.55 + rim)[..., None] * col
        return _up(np.clip(out * 0.9, 0, 255), self.W, self.H)


class Kandinsky(_P):
    """A Bauhaus composition - circles, arcs, lines, triangles - drifting like a mobile."""

    def __init__(self, W, H):
        super().__init__(W, H, "Composition VIII")
        r = np.random.default_rng(8)
        self.items = []
        cols = [(235, 70, 60), (250, 200, 60), (60, 120, 230), (240, 240, 230), (70, 190, 150), (230, 110, 190)]
        for i in range(16):
            self.items.append({"k": ["circle", "line", "tri", "arc", "ring"][i % 5], "c": cols[i % len(cols)],
                               "p": r.random(2), "s": r.uniform(0.05, 0.16), "a": r.uniform(0, 6.28),
                               "w": r.uniform(0.02, 0.06), "ph": r.uniform(0, 6.28)})

    def render(self, dt, t):
        W, H = self.W, self.H
        img = Image.new("RGB", (W, H), (12, 14, 30))
        d = ImageDraw.Draw(img)
        for it in self.items:
            x = (it["p"][0] + 0.05 * math.sin(t * 0.06 + it["ph"])) * W
            y = (it["p"][1] + 0.05 * math.cos(t * 0.05 + it["ph"])) * H
            s = it["s"] * W * (1 + 0.08 * math.sin(t * 0.1 + it["ph"]))
            a = it["a"] + t * 0.03 * (1 if it["ph"] > 3 else -1)
            c = it["c"]
            if it["k"] == "circle":
                d.ellipse([x - s / 2, y - s / 2, x + s / 2, y + s / 2], fill=c)
            elif it["k"] == "ring":
                d.ellipse([x - s, y - s, x + s, y + s], outline=c, width=2)
            elif it["k"] == "line":
                dx, dy = math.cos(a) * s * 1.6, math.sin(a) * s * 1.6
                d.line([(x - dx, y - dy), (x + dx, y + dy)], fill=c, width=2)
            elif it["k"] == "arc":
                d.arc([x - s, y - s, x + s, y + s], math.degrees(a), math.degrees(a) + 140, fill=c, width=3)
            else:
                pts = [(x + s * math.cos(a + k * 2.094), y + s * math.sin(a + k * 2.094)) for k in range(3)]
                d.polygon(pts, fill=c)
        return np.asarray(img, np.float32) * 0.9


class OpArt(_P):
    """Bridget-Riley-like stripes bent by slow waves, two colours from a palette."""

    def __init__(self, W, H, lut):
        super().__init__(W, H, "Op Waves", scale=1)
        self.lut = lut

    def render(self, dt, t):
        bend = 0.07 * np.sin(self.y * 9.0 + t * 0.35) + 0.05 * np.sin(self.y * 17.0 - t * 0.22 + self.x * 3.0)
        v = np.sin((self.x + bend + 0.5 * self.y * 0.15) * 62.0 + t * 0.4)
        s = np.clip(v * 3.0, -1, 1) * 0.5 + 0.5              # soft-edged stripes
        glow = 0.5 + 0.5 * np.sin(self.y * 3.0 + t * 0.1)
        c1, c2 = self.lut[40], self.lut[215]
        return (s[..., None] * c1 + (1 - s[..., None]) * c2) * (0.65 + 0.35 * glow)[..., None]


class Mondrian(_P):
    """Rectangles with black lines whose dividers drift; a few cells glow primary colours."""

    def __init__(self, W, H):
        super().__init__(W, H, "Broadway Boogie", scale=1)
        r = np.random.default_rng(4)
        self.v = [(r.uniform(0.15, 0.85), r.uniform(0, 6.28)) for _ in range(4)]
        self.h = [(r.uniform(0.15, 0.85), r.uniform(0, 6.28)) for _ in range(4)]
        self.fills = r.integers(0, 5, (5, 5))

    def render(self, dt, t):
        W, H = self.W, self.H
        xs = sorted(0.0 + 0.5 * 0 + p + 0.05 * math.sin(t * 0.07 + ph) for p, ph in self.v)
        ys = sorted(p + 0.05 * math.cos(t * 0.06 + ph) for p, ph in self.h)
        xs, ys = [0.0] + xs + [1.0], [0.0] + ys + [1.0]
        img = Image.new("RGB", (W, H), (235, 232, 220))
        d = ImageDraw.Draw(img)
        pal = [(235, 232, 220), (220, 40, 40), (250, 210, 50), (30, 70, 190), (235, 232, 220)]
        for j in range(5):
            for i in range(5):
                f = self.fills[j, i]
                pulse = 0.85 + 0.15 * math.sin(t * 0.2 + i * 1.3 + j * 0.7)
                c = tuple(int(v * (pulse if f in (1, 2, 3) else 1.0)) for v in pal[f])
                d.rectangle([xs[i] * W, ys[j] * H, xs[i + 1] * W, ys[j] * H + (ys[j + 1] - ys[j]) * H], fill=c)
        for x in xs[1:-1]:
            d.line([(x * W, 0), (x * W, H)], fill=(10, 10, 10), width=4)
        for y in ys[1:-1]:
            d.line([(0, y * H), (W, y * H)], fill=(10, 10, 10), width=4)
        return np.asarray(img, np.float32) * 0.62


class ArtsyGallery(art.Gallery):
    def __init__(self):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        P = _palette
        ink = P([(8, 10, 30), (30, 60, 140), (230, 200, 150), (250, 245, 235)])
        rose = P([(25, 6, 35), (150, 40, 120), (250, 120, 150), (255, 220, 200)])
        wash = P([(60, 120, 220), (220, 70, 120), (250, 190, 70), (60, 190, 160), (60, 120, 220)])
        stripe = P([(10, 10, 20), (20, 40, 120), (240, 90, 120), (250, 240, 220)])
        self.pieces = [Marbling(W, H, ink), OilSlick(W, H), OpArt(W, H, stripe), Marbling(W, H, rose)]
        self.last_t = None
        self.current = -1


LOOP_SEC = art.PIECE_SEC * 4
_gallery = None


def frame(t):
    global _gallery
    if _gallery is None:
        _gallery = ArtsyGallery()
    return _gallery(t)
