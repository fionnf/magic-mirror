"""Idle animations. Each is a generator yielding PIL.Image frames."""
import math
import random
from PIL import Image, ImageDraw
import config


def starfield(num_stars: int = 40):
    w, h = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    stars = [(random.randint(0, w - 1), random.randint(0, h - 1),
              random.random()) for _ in range(num_stars)]
    t = 0
    while True:
        img = Image.new("RGB", (w, h), (0, 0, 0))
        px = img.load()
        for i, (x, y, phase) in enumerate(stars):
            twinkle = 0.5 + 0.5 * math.sin(t * 0.05 + phase * math.tau)
            b = int(40 + 180 * twinkle)
            # tint slightly blue
            px[x, y] = (b // 3, b // 2, b)
            # occasionally relocate a star
            if random.random() < 0.005:
                stars[i] = (random.randint(0, w - 1), random.randint(0, h - 1),
                            random.random())
        t += 1
        yield img


def ripple(colour=(40, 80, 200), max_radius: int = None, speed: float = 1.5):
    w, h = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    cx, cy = w // 2, h // 2
    if max_radius is None:
        max_radius = int(math.hypot(w, h) / 2) + 4
    r = 0.0
    while True:
        img = Image.new("RGB", (w, h), (0, 0, 0))
        d = ImageDraw.Draw(img)
        for k in range(3):
            rk = (r - k * 6) % max_radius
            if rk <= 0:
                continue
            fade = max(0.0, 1.0 - rk / max_radius)
            c = tuple(int(v * fade) for v in colour)
            d.ellipse([cx - rk, cy - rk, cx + rk, cy + rk], outline=c)
        r += speed
        if r > max_radius * 3:
            r = 0
        yield img


def thinking_dots(base: Image.Image = None, colour=(255, 200, 100)):
    """Overlay 3 pulsing dots in the bottom-right corner."""
    w, h = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    t = 0
    while True:
        img = base.copy() if base is not None else Image.new("RGB", (w, h), (0, 0, 0))
        d = ImageDraw.Draw(img)
        for i in range(3):
            phase = (t * 0.1) - i * 0.6
            level = 0.3 + 0.7 * max(0.0, math.sin(phase))
            c = tuple(int(v * level) for v in colour)
            x = w - 10 - i * 4
            y = h - 3
            d.point((x, y), fill=c)
        t += 1
        yield img


ANIMATIONS = {
    "starfield": starfield,
    "ripple": ripple,
}
