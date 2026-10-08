"""VJ effects: extra art styles for the music mode plus post effects the AI designer can ask for.

  PIECE_STYLES   name -> one-line description (also shown to the AI)
  PieceBank      lazily builds the pieces and renders them (recoloured with the scene palette, or
                 in their own native colours)
  symmetry()     mirror / quad / diag folds
  hue_rotate()   slow colour drift
  Accents        beat shockwaves and the bigger "drop" shockwave
  DropDetector   notices a build-up followed by a bass drop

All cheap numpy / PIL; each style is a few ms on a Pi 4.
"""
import math
import random

import numpy as np

from display import art

# name -> description (for the designer's menu)
PIECE_STYLES = {
    "spiral": "golden-angle spiral of glowing dots, slowly twisting (hypnotic)",
    "harmonograph": "decaying pendulum rose drawn in light (elegant, mellow)",
    "poles": "streamlines curling around turning vortices and sinks (fluid, dramatic)",
    "marbling": "suminagashi marbling ink swirls (rich, flowing)",
    "oilslick": "iridescent oil-on-water interference colours (psychedelic, dreamy)",
    "opart": "Bridget-Riley op-art stripes bent by waves (dizzying, bold)",
    "glass": "stained-glass Voronoi cells with dark lead lines (jewel-like, warm)",
    "trails": "particles painting long-exposure light trails (airy, cinematic)",
    "nebula": "layered drifting space clouds with stars (spacey, ambient)",
}
# styles also allowed as the second, screen-blended layer (cheap ones)
LAYER_STYLES = ("aurora", "ripples", "garden", "rings", "flowlines", "trails", "nebula")
SYMMETRIES = ("none", "mirror", "quad", "diag")


class PieceBank:
    """Builds the registry pieces on first use."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        self._p = {}

    def _build(self, name):
        from display import shapes, artsy, light_art
        W, H, P = self.W, self.H, art._palette
        ice = P([(8, 12, 40), (30, 90, 200), (90, 220, 255), (240, 250, 255)])
        sun = P([(40, 8, 20), (220, 60, 50), (255, 170, 60), (255, 245, 200)])
        mint = P([(5, 25, 20), (20, 140, 110), (120, 240, 190), (240, 255, 245)])
        rose = P([(30, 6, 40), (170, 40, 140), (255, 120, 180), (255, 230, 240)])
        gold = P([(20, 10, 0), (150, 90, 10), (240, 180, 60), (255, 245, 190)])
        jewel = P([(8, 4, 30), (50, 25, 130), (160, 70, 170), (250, 220, 240)])
        dusk = P([(15, 6, 35), (90, 30, 110), (230, 90, 120), (255, 200, 140)])
        ocean = P([(2, 6, 25), (10, 60, 120), (20, 170, 190), (160, 240, 230)])
        forest = P([(3, 12, 8), (15, 80, 60), (90, 190, 120), (230, 250, 190)])
        ink = P([(8, 10, 30), (30, 60, 140), (230, 200, 150), (250, 245, 235)])
        wash = P([(60, 120, 220), (220, 70, 120), (250, 190, 70), (60, 190, 160), (60, 120, 220)])
        stripe = P([(10, 10, 20), (20, 40, 120), (240, 90, 120), (250, 240, 220)])
        make = {
            "spiral": lambda: shapes.SpiralMorph(W, H, gold),
            "hex": lambda: shapes.HexStrands(W, H, mint),
            "harmonograph": lambda: shapes.Harmonograph(W, H, gold),
            "isocubes": lambda: shapes.IsoCubes(W, H, mint),
            "chevrons": lambda: shapes.Chevrons(W, H, ice),
            "poles": lambda: shapes.FlowPoles(W, H, ice),
            "mosaic": lambda: shapes.TriMosaic(W, H, rose),
            "mesh": lambda: shapes.InterferenceMesh(W, H, sun),
            "marbling": lambda: artsy.Marbling(W, H, ink),
            "oilslick": lambda: artsy.OilSlick(W, H),
            "kandinsky": lambda: artsy.Kandinsky(W, H),
            "opart": lambda: artsy.OpArt(W, H, stripe),
            "mondrian": lambda: artsy.Mondrian(W, H),
            "glass": lambda: light_art.StainedGlass(W, H, jewel),
            "julia": lambda: light_art.JuliaMorph(W, H, ocean),
            "kaleido": lambda: light_art.Kaleido(W, H, jewel),
            "trails": lambda: light_art.Trails(W, H, forest),
            "nebula": lambda: light_art.Nebula(W, H, dusk),
        }
        piece = make[name]()
        piece.reset()
        return piece

    def prewarm(self):
        """Build and run every piece once in the background so a scene change never hitches."""
        import time
        for name in PIECE_STYLES:
            try:
                p = self._p.get(name) or self._build(name)
                self._p.setdefault(name, p)
                p.render(0.04, 0.0)
            except Exception:
                pass
            time.sleep(0.4)

    def render(self, name, t, lut=None, native=False):
        """float32 HxWx3. Recoloured with `lut` (luminance -> palette) unless native."""
        piece = self._p.get(name)
        if piece is None:
            piece = self._p[name] = self._build(name)
        img = np.asarray(piece.render(0.04, t), np.float32)
        if native or lut is None:
            return img
        lum = (img[..., 0] * 0.3 + img[..., 1] * 0.59 + img[..., 2] * 0.11) / 255.0
        return art._lut(np.clip(lum ** 0.85 * 1.15, 0, 1), lut)


def symmetry(img, kind):
    if kind == "mirror":
        h = img.shape[1] // 2
        out = img.copy()
        out[:, h:] = img[:, :h][:, ::-1][:, : img.shape[1] - h]
        return out
    if kind == "quad":
        h, w = img.shape[0] // 2, img.shape[1] // 2
        q = img[:h, :w]
        out = np.empty_like(img)
        out[:h, :w] = q
        out[:h, w:] = q[:, ::-1][:, : img.shape[1] - w]
        out[h:, :w] = q[::-1][: img.shape[0] - h]
        out[h:, w:] = q[::-1, ::-1][: img.shape[0] - h, : img.shape[1] - w]
        return out
    if kind == "diag" and img.shape[0] == img.shape[1]:
        up = np.triu(np.ones(img.shape[:2], bool))
        return np.where(up[..., None], img, np.transpose(img, (1, 0, 2)))
    return img


def hue_rotate(img, angle):
    """Rotate colours around the grey axis by `angle` radians."""
    c, s = math.cos(angle), math.sin(angle)
    k = 1.0 / 3.0
    sq = math.sqrt(k)
    m = np.array([
        [c + (1 - c) * k, k * (1 - c) - sq * s, k * (1 - c) + sq * s],
        [k * (1 - c) + sq * s, c + k * (1 - c), k * (1 - c) - sq * s],
        [k * (1 - c) - sq * s, k * (1 - c) + sq * s, c + k * (1 - c)]], np.float32)
    return np.clip(img @ m.T, 0, 255)


class Accents:
    """Expanding light rings: small ones on the beat, one big one on a drop.
    Computed on a coarse grid and smoothly upscaled (they are soft): ~1 ms on a Pi."""
    STEP = 3

    def __init__(self, W, H):
        self.W, self.H = W, H
        y, x = np.mgrid[0:H:self.STEP, 0:W:self.STEP].astype(np.float32)
        self.x, self.y = x, y
        self.rings = []          # [cx, cy, born, strength, speed]

    def beat(self, amount, now):
        if random.random() < 0.15 + 0.5 * amount:
            self.rings.append([random.uniform(0.2, 0.8) * self.W, random.uniform(0.2, 0.8) * self.H,
                               now, 0.16 + 0.28 * amount, 55.0])
        self.rings = self.rings[-3:]

    def drop(self, now):
        self.rings.append([self.W / 2, self.H / 2, now, 1.0, 120.0])
        self.rings = self.rings[-3:]

    def apply(self, img, now, colour):
        from PIL import Image
        alive, total = [], np.zeros_like(self.x)
        for cx, cy, born, st, sp in self.rings:
            age = now - born
            if age > 2.2:
                continue
            alive.append([cx, cy, born, st, sp])
            d = np.sqrt((self.x - cx) ** 2 + (self.y - cy) ** 2)
            total += np.exp(-((d - age * sp) ** 2) / (2 * (3.0 + age * 3.0) ** 2)) * st * (1 - age / 2.2)
        self.rings = alive
        if not alive:
            return img
        big = np.asarray(Image.fromarray(total.astype(np.float32), "F").resize((self.W, self.H), Image.BICUBIC))
        return np.clip(img + np.clip(big, 0, 1.5)[..., None] * colour, 0, 255)


class DropDetector:
    """A drop = bass jumps well above its recent level after a calmer stretch."""

    def __init__(self):
        self.slow = 0.0
        self.fast = 0.0
        self.low_since = None
        self.last = 0.0

    def update(self, bass, energy, dt, now):
        self.slow += (bass - self.slow) * min(1.0, dt / 6.0)
        self.fast += (bass - self.fast) * min(1.0, dt / 0.25)
        calm = energy < 0.55 and self.slow < 0.5
        if calm:
            self.low_since = self.low_since or now
        if (self.low_since and now - self.low_since > 2.0 and self.fast > 0.75
                and self.fast > self.slow * 1.8 and now - self.last > 14.0):
            self.last, self.low_since = now, None
            return True
        if not calm and self.low_since and now - self.low_since < 2.0:
            self.low_since = None
        return False
