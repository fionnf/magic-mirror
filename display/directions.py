"""Art directions for the daily piece, so the wall does not make the same picture every day.

Each day gets one direction: a colour family, how light the ground is, and a kind of form. They are
dealt from a shuffled deck (a new order every cycle), skipping any used in the last days, so
neighbouring days always differ. The palette and brightness the artist chooses are checked against
the direction and against the last few days (palette_problem / brightness_problem).
"""
import colorsys
import datetime
import random

# hue ranges in degrees (0 red, 30 orange, 60 yellow, 120 green, 180 cyan, 220 blue, 280 violet, 320 magenta)
DIRECTIONS = [
    {"name": "Cobalt and chalk", "hues": (205, 240), "ground": "mid",
     "colour": "cobalt and ultramarine with chalky off-white highlights; a deep navy shadow",
     "form": "conic gradients or hard-edged quarter-turns that use the panel seams as a grid"},
    {"name": "Paper and ink", "hues": (0, 360), "ground": "light",
     "colour": "a pale paper ground (warm or cool off-white) with ONE ink colour: indigo, sepia or carmine",
     "form": "ink: a slowly spreading drop, a brushed arc, or fine hatching - lots of empty paper"},
    {"name": "Viridian depth", "hues": (140, 180), "ground": "dark",
     "colour": "viridian, bottle green and pale mint; no warm tones at all",
     "form": "deep water: layered translucent planes, caustic light, slow refraction"},
    {"name": "Ultraviolet", "hues": (260, 300), "ground": "dark",
     "colour": "ultraviolet, electric violet and lilac light",
     "form": "neon: one or two thin rods or arcs of light with soft coloured fans, Dan Flavin-like"},
    {"name": "Rose field", "hues": (325, 355), "ground": "mid",
     "colour": "rose, coral-pink and blush, with a deep wine shadow",
     "form": "a Rothko-like field: two or three soft-edged horizontal bands that breathe"},
    {"name": "Ice and silver", "hues": (185, 215), "ground": "light",
     "colour": "ice blue, glacier white and pale silver-grey; cold, high key",
     "form": "frost or fog: a fine grain, a slow condensation pattern, a horizon dissolving"},
    {"name": "Chartreuse signal", "hues": (65, 95), "ground": "dark",
     "colour": "chartreuse and acid lime on a dark petrol-green ground (one family, no rainbow)",
     "form": "halftone: a field of dots whose size follows a slow folding surface"},
    {"name": "Op-art", "hues": (0, 360), "ground": "mid",
     "colour": "two colours only, high contrast (e.g. black and a saturated red, or navy and cream)",
     "form": "Bridget Riley stripes or concentric bands that warp very slowly into moire"},
    {"name": "Teal and coral", "hues": (170, 200), "ground": "mid",
     "colour": "teal and petrol blue as the body, with a single small accent of coral",
     "form": "mid-century cut paper: flat overlapping curves and circles, crisp edges"},
    {"name": "Red monochrome", "hues": (350, 15), "ground": "dark",
     "colour": "every tint of one red: oxblood, vermilion, scarlet, a pale red-white highlight",
     "form": "a single large geometric form (circle, arch, square) with light escaping round its edge"},
    {"name": "Turrell room", "hues": (190, 290), "ground": "mid",
     "colour": "a saturated colour field that slowly crosses from one cool hue to a neighbour",
     "form": "an aperture: a soft rectangle of light inside a frame of another colour, Turrell-like"},
    {"name": "Prism", "hues": (0, 360), "ground": "dark",
     "colour": "a narrow spectral split of white light (only where the light splits; the rest is dark)",
     "form": "one thin line of white light dividing into a soft spectral fan, or a slow caustic"},
    {"name": "Topography", "hues": (90, 150), "ground": "mid",
     "colour": "moss, sage and pale lichen on a soft green-grey ground",
     "form": "fine contour lines of an imagined landscape that slowly erodes and rises"},
    {"name": "Bauhaus", "hues": (0, 360), "ground": "light",
     "colour": "a primary trio on a warm off-white ground (red, cobalt, ochre), flat and matte",
     "form": "a slowly re-arranging composition of circles, half-discs and bars, Bauhaus poster-like"},
    {"name": "Gold leaf", "hues": (40, 55), "ground": "dark",
     "colour": "gold and pale brass on a deep blue-black ground (not brown, not amber-orange)",
     "form": "a fine geometric lattice or kintsugi crack lines catching light"},
    {"name": "Magenta bloom", "hues": (295, 330), "ground": "mid",
     "colour": "magenta, fuchsia and pale orchid",
     "form": "a slowly opening bloom: overlapping translucent petal-shapes or radial folds"},
]

GROUND = {   # mean brightness range (0..255) of the still for each ground
    "dark": (12, 70, "a dark ground, but the piece should still glow clearly (not a dim smudge on black)"),
    "mid": (40, 130, "a mid-tone ground: the whole wall is coloured, not black"),
    "light": (90, 150, "a light, high-key ground: pale paper or sky, with darker marks on it"),
}


def pick(date, used=()):
    """The direction for this date: dealt from a deck shuffled per cycle, skipping recently used names."""
    d = datetime.date.fromisoformat(date) if isinstance(date, str) else date
    n = len(DIRECTIONS)
    cycle, pos = divmod(d.toordinal(), n)
    order = list(range(n))
    random.Random(cycle * 7919).shuffle(order)
    for k in range(n):
        cand = DIRECTIONS[order[(pos + k) % n]]
        if cand["name"] not in used:
            return cand
    return DIRECTIONS[order[pos]]


def brief(direction):
    lo, hi, words = GROUND[direction["ground"]]
    return (f"TODAY'S DIRECTION - \"{direction['name']}\" (required; it keeps the wall from repeating itself):\n"
            f"- colour: {direction['colour']}\n- ground: {words}\n- form: {direction['form']}\n"
            "Interpret it freely and make it yours, but stay inside it. Do not fall back on a dim warm "
            "glow on black - that has been done.")


def _hsv(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, s, v = colorsys.rgb_to_hsv(r, g, b)
    return hh * 360, s, v


def _hue_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _in_range(h, lo, hi):
    return lo <= h <= hi if lo <= hi else (h >= lo or h <= hi)


def _main_hue(pal):
    """The palette's colour: the hue of its most saturated colour (greys and near-blacks do not count)."""
    best = max((_hsv(c) for c in pal), key=lambda x: x[1] * min(1.0, x[2] * 2))
    return best[0] if best[1] > 0.2 else None


def palette_problem(pal, direction, recent):
    """-> None if fine, else a note for the artist. recent = palettes of the last days, newest first."""
    lo, hi = direction["hues"]
    hue = _main_hue(pal)
    if (lo, hi) != (0, 360):
        if hue is None:
            return f"the palette is almost grey; today's direction ({direction['name']}) needs real colour"
        if not _in_range(hue, lo - 15, hi + 15):
            return (f"the palette's main hue ({hue:.0f} degrees) is outside today's direction "
                    f"\"{direction['name']}\" ({direction['colour']})")
    for k, old in enumerate(recent[:3]):
        oh = _main_hue(old)
        if hue is not None and oh is not None and _hue_dist(hue, oh) < 25 \
                and abs(_hsv(pal[0])[2] - _hsv(old[0])[2]) < 0.2:
            return (f"the palette is too close to the piece from {k + 1} day(s) ago ({', '.join(old)}); "
                    "the wall needs a visibly different colour today")
    return None


def brightness_problem(mean, direction):
    lo, hi, words = GROUND[direction["ground"]]
    if mean < lo:
        return f"it is too dark for today's direction (mean {mean:.0f}/255, want {lo}-{hi}): {words}"
    if mean > hi:
        return f"it is too bright for today's direction (mean {mean:.0f}/255, want {lo}-{hi}): {words}"
    return None
