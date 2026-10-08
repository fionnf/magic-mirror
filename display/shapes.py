"""Shapes gallery: slowly moving generative patterns (flow dots, flow lines, node garden,
spiral, woven grid, radial rings), inspired by the families on bookofshapes.com but written
from scratch and animated. Same piece interface as display/art.py (reset(), render(dt, t) ->
float32 HxWx3 in 0..255) so it plugs into art.Gallery.

Pieces draw thin glowing lines/dots with PIL on a black canvas, then a small blur gives the
LED-friendly glow. ~2-4 ms per frame at 192x192 on a laptop.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import config
from display import art


class _Piece:
    GLOW = 1.2

    def __init__(self, W, H, name, lut):
        self.W, self.H, self.name, self.lut = W, H, name, lut

    def reset(self):
        pass

    def colour(self, v):
        """Colour from the piece's palette for v in 0..1."""
        return tuple(int(c) for c in self.lut[int(max(0.0, min(1.0, v)) * 255)])

    def canvas(self):
        img = Image.new("RGB", (self.W, self.H), (0, 0, 0))
        return img, ImageDraw.Draw(img)

    def finish(self, img):
        glow = img.filter(ImageFilter.GaussianBlur(self.GLOW))
        a = np.asarray(img, np.float32)
        b = np.asarray(glow, np.float32)
        return np.clip(a * 0.85 + b * 1.1, 0, 255)


class FlowDots(_Piece):
    """A comb of points released along the top edge, each followed down through a two-wave
    field; a dot is left at every fixed arc length."""

    def __init__(self, W, H, lut, lines=False, strands=30, name=None):
        super().__init__(W, H, name or ("Flow Lines" if lines else "Flow Dots"), lut)
        self.lines, self.strands = lines, strands

    def render(self, dt, t):
        W, H = self.W, self.H
        img, d = self.canvas()
        step, every = 1.5, 5 if not self.lines else 1
        p1, p2 = t * 0.35, t * 0.23                       # waves drift slowly
        for s in range(self.strands):
            x0 = x = (s + 0.5) * W / self.strands
            y = -2.0
            pts = []
            for i in range(int(H * 1.4 / step)):
                yy = y / H
                dx = (math.sin(yy * 5.1 + x * 0.034 + p1) * 0.9 +
                      math.sin(yy * 8.9 - x * 0.021 - p2) * 0.6) * (0.3 + yy * 1.1)
                x += dx * step * 1.2 + (x0 - x) * 0.012 * step
                y += step
                if i % every == 0:
                    pts.append((x, y))
            col = self.colour(0.15 + 0.8 * s / self.strands)
            if self.lines:
                d.line(pts, fill=col, width=1)
            else:
                for (px, py) in pts:
                    if 0 <= py < H:
                        d.ellipse([px - 1, py - 1, px + 1, py + 1], fill=col)
        return self.finish(img)


class NodeGarden(_Piece):
    """Drifting nodes; neighbours are joined by lines that fade with distance."""

    def __init__(self, W, H, lut, n=28):
        super().__init__(W, H, "Node Garden", lut)
        self.n = n
        self.reset()

    def reset(self):
        r = np.random.default_rng(7)
        self.ph = r.uniform(0, 6.28, (self.n, 4)).astype(np.float32)
        self.fr = r.uniform(0.04, 0.12, (self.n, 4)).astype(np.float32)

    def render(self, dt, t):
        W, H = self.W, self.H
        x = W / 2 + (np.sin(t * self.fr[:, 0] + self.ph[:, 0]) + 0.4 * np.sin(t * self.fr[:, 2] * 2.3 + self.ph[:, 2])) * W * 0.36
        y = H / 2 + (np.cos(t * self.fr[:, 1] + self.ph[:, 1]) + 0.4 * np.sin(t * self.fr[:, 3] * 2.1 + self.ph[:, 3])) * H * 0.36
        img, d = self.canvas()
        reach = W * 0.30
        dx, dy = x[:, None] - x[None, :], y[:, None] - y[None, :]
        dist = np.sqrt(dx * dx + dy * dy)
        for i in range(self.n):
            for j in range(i + 1, self.n):
                if dist[i, j] < reach:
                    k = 1.0 - dist[i, j] / reach
                    c = self.colour(0.25 + 0.7 * ((i + j) % 9) / 9)
                    d.line([(x[i], y[i]), (x[j], y[j])], fill=tuple(int(v * k) for v in c), width=1)
        for i in range(self.n):
            c = self.colour(0.6 + 0.4 * (i % 5) / 5)
            d.ellipse([x[i] - 1.6, y[i] - 1.6, x[i] + 1.6, y[i] + 1.6], fill=c)
        return self.finish(img)


class SpiralMorph(_Piece):
    """A phyllotaxis-style spiral of dots whose twist slowly morphs."""

    def __init__(self, W, H, lut, n=420):
        super().__init__(W, H, "Spiral Morph", lut)
        self.n = n

    def render(self, dt, t):
        W, H = self.W, self.H
        img, d = self.canvas()
        angle = 2.399963 + 0.06 * math.sin(t * 0.07)       # golden angle, wobbling a little
        rot = t * 0.05
        cx, cy, rmax = W / 2, H / 2, min(W, H) * 0.47
        for i in range(self.n):
            r = rmax * math.sqrt(i / self.n)
            a = i * angle + rot
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            s = 0.7 + 1.6 * (i / self.n) * (0.6 + 0.4 * math.sin(i * 0.05 - t * 0.6))
            d.ellipse([x - s, y - s, x + s, y + s], fill=self.colour((i / self.n + t * 0.02) % 1.0))
        return self.finish(img)


class WovenGrid(_Piece):
    """Horizontal and vertical threads displaced by travelling waves, like cloth."""

    def __init__(self, W, H, lut, n=22):
        super().__init__(W, H, "Woven Grid", lut)
        self.n = n

    def render(self, dt, t):
        W, H, n = self.W, self.H, self.n
        img, d = self.canvas()
        xs = np.linspace(0, W, 70)
        for k in range(n):
            base = (k + 0.5) * H / n
            ys = base + (np.sin(xs * 0.045 + t * 0.5 + k * 0.5) * 4.0 + np.sin(xs * 0.09 - t * 0.31) * 2.0)
            d.line(list(zip(xs, ys)), fill=self.colour(0.1 + 0.4 * k / n), width=1)
        ys2 = np.linspace(0, H, 70)
        for k in range(n):
            base = (k + 0.5) * W / n
            xs2 = base + (np.sin(ys2 * 0.045 - t * 0.43 + k * 0.5) * 4.0 + np.sin(ys2 * 0.08 + t * 0.27) * 2.0)
            d.line(list(zip(xs2, ys2)), fill=self.colour(0.55 + 0.4 * k / n), width=1)
        return self.finish(img)


class RadialRings(_Piece):
    """Concentric rings, each wobbling with its own wave: a slow ripple."""

    def __init__(self, W, H, lut, rings=18):
        super().__init__(W, H, "Ripple Rings", lut)
        self.rings = rings

    def render(self, dt, t):
        W, H = self.W, self.H
        img, d = self.canvas()
        cx, cy = W / 2, H / 2
        ang = np.linspace(0, 2 * math.pi, 120)
        for k in range(self.rings):
            r0 = 6 + k * (min(W, H) * 0.47 - 6) / self.rings
            amp = 1.5 + k * 0.28
            r = r0 + amp * np.sin(ang * (3 + k % 4) + t * (0.35 + 0.03 * k) * (1 if k % 2 else -1))
            pts = list(zip(cx + r * np.cos(ang), cy + r * np.sin(ang)))
            d.line(pts + pts[:1], fill=self.colour(k / self.rings), width=1)
        return self.finish(img)


class HexStrands(_Piece):
    """Rows of short strands on a hex lattice, leaning with a drifting wave."""

    def __init__(self, W, H, lut, pitch=13):
        super().__init__(W, H, "Hex Strands", lut)
        self.pitch = pitch

    def render(self, dt, t):
        W, H, p = self.W, self.H, self.pitch
        img, d = self.canvas()
        rows = int(H / (p * 0.866)) + 2
        for r in range(rows):
            y0 = r * p * 0.866
            off = p / 2 if r % 2 else 0
            for c in range(int(W / p) + 2):
                x0 = c * p + off
                a = math.sin(x0 * 0.04 + y0 * 0.03 + t * 0.4) * 1.3 + math.sin(y0 * 0.07 - t * 0.25)
                l = p * 0.42
                dx, dy = math.cos(a) * l, math.sin(a) * l
                d.line([(x0 - dx, y0 - dy), (x0 + dx, y0 + dy)],
                       fill=self.colour(0.2 + 0.7 * (0.5 + 0.5 * math.sin(a * 2 + t * 0.2))), width=1)
        return self.finish(img)


class ShapesGallery(art.Gallery):
    def __init__(self):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        P = art._palette
        ice = P([(8, 12, 40), (30, 90, 200), (90, 220, 255), (240, 250, 255)])
        sun = P([(40, 8, 20), (220, 60, 50), (255, 170, 60), (255, 245, 200)])
        mint = P([(5, 25, 20), (20, 140, 110), (120, 240, 190), (240, 255, 245)])
        rose = P([(30, 6, 40), (170, 40, 140), (255, 120, 180), (255, 230, 240)])
        gold = P([(20, 10, 0), (150, 90, 10), (240, 180, 60), (255, 245, 190)])
        self.pieces = [
            FlowDots(W, H, ice), WovenGrid(W, H, rose), NodeGarden(W, H, mint),
            FlowDots(W, H, sun, lines=True), SpiralMorph(W, H, gold), RadialRings(W, H, ice),
            HexStrands(W, H, mint), FlowDots(W, H, rose, lines=True, strands=22),
        ]
        self.last_t = None
        self.current = -1


SHAPES_PIECE_SEC = art.PIECE_SEC
LOOP_SEC = SHAPES_PIECE_SEC * 8
_gallery = None


def frame(t):
    global _gallery
    if _gallery is None:
        _gallery = ShapesGallery()
    return _gallery(t)
