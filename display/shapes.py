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


class Truchet(_Piece):
    """Quarter-circle arc tiles that flip one by one, so long ribbons keep re-forming."""

    def __init__(self, W, H, lut, tile=16):
        super().__init__(W, H, "Truchet Ribbons", lut)
        self.tile = tile
        self.reset()

    def reset(self):
        n = self.W // self.tile + 1
        r = np.random.default_rng(11)
        self.phase = r.uniform(0, 1, (n, n))
        self.rate = r.uniform(0.01, 0.04, (n, n))

    def render(self, dt, t):
        img, d = self.canvas()
        T, n = self.tile, self.W // self.tile + 1
        for j in range(n):
            for i in range(n):
                flip = int(self.phase[j, i] * 1000 + t * self.rate[j, i] * 12) % 2
                x0, y0 = i * T, j * T
                col = self.colour(0.2 + 0.7 * ((i * 7 + j * 3) % 10) / 10)
                if flip:
                    d.arc([x0 - T / 2, y0 - T / 2, x0 + T / 2, y0 + T / 2], 0, 90, fill=col)
                    d.arc([x0 + T / 2, y0 + T / 2, x0 + 3 * T / 2, y0 + 3 * T / 2], 180, 270, fill=col)
                else:
                    d.arc([x0 + T / 2, y0 - T / 2, x0 + 3 * T / 2, y0 + T / 2], 90, 180, fill=col)
                    d.arc([x0 - T / 2, y0 + T / 2, x0 + T / 2, y0 + 3 * T / 2], 270, 360, fill=col)
        return self.finish(img)


class Chevrons(_Piece):
    """Stacked V-shaped bands that slide sideways at different speeds."""

    def __init__(self, W, H, lut, rows=14):
        super().__init__(W, H, "Chevron Blocks", lut)
        self.rows = rows

    def render(self, dt, t):
        W, H, n = self.W, self.H, self.rows
        img, d = self.canvas()
        rh = H / n
        for k in range(n):
            y = k * rh
            period = 26 + (k % 3) * 8
            shift = (t * (6 + k % 4 * 2) * (1 if k % 2 else -1)) % period
            col = self.colour(0.1 + 0.85 * k / n)
            x = -period + shift
            while x < W + period:
                d.line([(x, y + rh), (x + period / 2, y + 2), (x + period, y + rh)], fill=col, width=1)
                x += period
        return self.finish(img)


class Harmonograph(_Piece):
    """Two decaying pendulums drawing a looping rose; the frequencies drift slowly."""

    def __init__(self, W, H, lut):
        super().__init__(W, H, "Harmonograph", lut)

    def render(self, dt, t):
        W, H = self.W, self.H
        img, d = self.canvas()
        a = 3.0 + 0.5 * math.sin(t * 0.03)
        b = 5.0 + 0.5 * math.cos(t * 0.021)
        u = np.linspace(0, 16 * math.pi, 1500)
        decay = np.exp(-u * 0.02)
        x = W / 2 + W * 0.46 * decay * (np.sin(a * u + t * 0.1) * 0.7 + np.sin(b * u + 0.5) * 0.3)
        y = H / 2 + H * 0.46 * decay * (np.sin(b * u + 1.9 + t * 0.07) * 0.7 + np.sin(a * u * 1.01 + 2.2) * 0.3)
        n = len(u)
        for k in range(0, n - 1, 6):
            d.line(list(zip(x[k:k + 7], y[k:k + 7])), fill=self.colour(k / n), width=1)
        return self.finish(img)


class IsoCubes(_Piece):
    """Isometric cube lattice drawn as wireframes whose heights ripple."""

    def __init__(self, W, H, lut, size=21):
        super().__init__(W, H, "Iso Cubes", lut)
        self.size = size

    def render(self, dt, t):
        W, H, s = self.W, self.H, self.size
        img, d = self.canvas()
        dx, dy = s * 0.866, s * 0.5
        for j in range(-2, int(H / dy) + 3):
            for i in range(-2, int(W / (2 * dx)) + 3):
                cx = i * 2 * dx + (dx if j % 2 else 0)
                cy = j * dy * 1.0
                h = (0.25 + 0.75 * (0.5 + 0.5 * math.sin(i * 0.7 + j * 0.45 + t * 0.5))) * s * 0.9
                top = cy - h
                col = self.colour(0.15 + 0.8 * (0.5 + 0.5 * math.sin(i * 0.3 - j * 0.2 + t * 0.2)))
                d.line([(cx - dx, top), (cx, top - dy), (cx + dx, top), (cx, top + dy), (cx - dx, top)], fill=col)
                d.line([(cx - dx, top), (cx - dx, top + h)], fill=col)
                d.line([(cx + dx, top), (cx + dx, top + h)], fill=col)
                d.line([(cx, top + dy), (cx, top + dy + h)], fill=col)
        return self.finish(img)


class Ridges(_Piece):
    """Stacked contour lines of a slowly evolving noise landscape that hide each other
    (filled black under every line, so near ridges cover far ones)."""

    def __init__(self, W, H, lut, rows=34):
        super().__init__(W, H, "Night Ridges", lut)
        self.rows = rows

    def render(self, dt, t):
        W, H, n = self.W, self.H, self.rows
        img, d = self.canvas()
        xs = np.linspace(0, W, 96)
        for k in range(n):
            base = H * 0.22 + k * (H * 0.78) / n
            depth = k / n
            amp = 6 + depth * 18
            ys = base - amp * (0.5 + 0.5 * np.sin(xs * 0.05 + t * 0.2 + k * 0.4)
                               * np.sin(xs * 0.021 - t * 0.13 + k * 0.17)
                               + 0.35 * np.sin(xs * 0.11 + k * 0.9 - t * 0.3))
            pts = list(zip(xs, ys))
            d.polygon(pts + [(W, H + 2), (0, H + 2)], fill=(0, 0, 0))
            d.line(pts, fill=self.colour(0.15 + 0.8 * depth), width=1)
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
            Truchet(W, H, sun), Chevrons(W, H, ice), Harmonograph(W, H, gold),
            IsoCubes(W, H, mint), Ridges(W, H, rose),
        ]
        self.last_t = None
        self.current = -1


SHAPES_PIECE_SEC = art.PIECE_SEC
LOOP_SEC = SHAPES_PIECE_SEC * 13
_gallery = None


def frame(t):
    global _gallery
    if _gallery is None:
        _gallery = ShapesGallery()
    return _gallery(t)
