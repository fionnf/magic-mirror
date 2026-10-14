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
DIRECTIONS = [   # one quiet, glowing form each (the house's favourites: glass orb, dot ring, blue ring); colour varies
    {"name": "Violet glass", "hues": (235, 275), "ground": "dark",
     "colour": "deep violet and indigo glass with a cold white rim light",
     "form": "one soft, slightly lumpy glass body in space, its edge catching the light, a faint glow below"},
    {"name": "Halftone ring", "hues": (300, 340), "ground": "dark",
     "colour": "magenta into warm orange, round a ring",
     "form": "a wide ring of halftone dots around an empty dark centre, dots largest in the ring's middle"},
    {"name": "Azure ring", "hues": (185, 215), "ground": "dark",
     "colour": "cyan and azure light with a thin warm fringe on its outer edge",
     "form": "one soft out-of-focus ring of light floating in the dark, drifting in and out of focus"},
    {"name": "Emerald orb", "hues": (140, 165), "ground": "dark",
     "colour": "emerald, jade and pale mint light",
     "form": "one luminous orb with a soft halo, light pooling and fading around it"},
    {"name": "Ruby eclipse", "hues": (345, 10), "ground": "dark",
     "colour": "ruby and scarlet light with a hot pale core at the rim",
     "form": "a dark disc with a burning rim of light escaping round its edge"},
    {"name": "Amber aperture", "hues": (25, 45), "ground": "dark",
     "colour": "amber and soft gold light (glowing, not brown)",
     "form": "a soft-edged rectangle of light - a window or aperture - with light bleeding past its frame"},
    {"name": "Ultraviolet arc", "hues": (265, 295), "ground": "dark",
     "colour": "ultraviolet and lilac neon",
     "form": "one thin neon line or arc of light casting a soft coloured fan on the dark around it"},
    {"name": "Ice halo", "hues": (190, 220), "ground": "dark",
     "colour": "ice blue and glacier white",
     "form": "a dark rounded shape with a cold halo of light spilling round its whole edge"},
    {"name": "Rose glass", "hues": (330, 355), "ground": "dark",
     "colour": "rose and blush pink glass with a peach rim light",
     "form": "a soft translucent glass droplet or pebble, lit from one side"},
    {"name": "Teal dot sphere", "hues": (170, 195), "ground": "dark",
     "colour": "teal and aqua points of light",
     "form": "a sphere or blob made of fine light points, denser and brighter at its edges"},
    {"name": "Gold ring", "hues": (40, 55), "ground": "dark",
     "colour": "pale gold and champagne light on a deep blue-black",
     "form": "a single thin ring of light, slightly broken, slowly closing or opening"},
    {"name": "Coral bloom", "hues": (5, 25), "ground": "dark",
     "colour": "coral, salmon and soft peach light",
     "form": "one soft glowing bloom - a blurred round light with a brighter heart"},
    {"name": "Cobalt pill", "hues": (215, 240), "ground": "dark",
     "colour": "cobalt and electric blue with a pale mint highlight",
     "form": "a tall rounded capsule outline of neon light, its glow pooling softly below it"},
    {"name": "Lime glow", "hues": (75, 100), "ground": "dark",
     "colour": "lime and chartreuse light on a dark petrol green",
     "form": "one soft glowing blob that slowly changes shape, like light inside frosted glass"},
    {"name": "Magenta cross", "hues": (300, 325), "ground": "mid",
     "colour": "magenta and violet light seeping between deep plum cushions",
     "form": "four soft cushions pressed together, light escaping along the seams as a glowing cross"},
    {"name": "Prism line", "hues": (0, 360), "ground": "dark",
     "colour": "white light splitting into a narrow soft spectrum only where it fans out",
     "form": "one thin vertical line of light opening into a soft spectral fan towards the bottom"},
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
            "Interpret it freely and make it yours, but stay inside it: ONE form, quiet and luminous, lots of "
            "calm space around it. No stripes, checkerboards, grids of fine lines or other busy patterns - "
            "they shimmer on an LED wall.")


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
