"""Sparkles around a smiling face: little four-point stars that twinkle for a moment."""
import math
import random

from PIL import ImageDraw

COLOURS = [(255, 236, 160), (255, 150, 210), (170, 235, 255), (255, 255, 255)]


def draw(canvas, cx, cy, t, radius=34, count=16):
    """cx, cy in canvas pixels; t in seconds (any origin) - stars twinkle with it."""
    d = ImageDraw.Draw(canvas)
    rnd = random.Random(int(t * 4))                      # a fresh scatter every ~0.25 s
    for i in range(count):
        a = rnd.uniform(0, 2 * math.pi)
        r = radius * (0.55 + 0.75 * rnd.random())
        x, y = cx + r * math.cos(a), cy - 8 + r * math.sin(a) * 0.9
        size = 1.5 + 3.5 * abs(math.sin(t * 7 + i * 1.7))
        c = COLOURS[i % len(COLOURS)]
        d.line([(x - size, y), (x + size, y)], fill=c)
        d.line([(x, y - size), (x, y + size)], fill=c)
        d.point((x, y), fill=(255, 255, 255))
    return canvas
