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
    # deep grounds: a dark colour fills the wall (not black); the form is a few tones lighter in the same hue
    {"name": "Oxblood velvet", "hues": (345, 12), "ground": "deep",
     "colour": "oxblood, garnet and deep wine, the form a few tones lighter in dusky rose",
     "form": "one large soft fold or drape of velvet slowly shifting, its ridge catching a little light"},
    {"name": "Ink tide", "hues": (215, 240), "ground": "deep",
     "colour": "ink blue and midnight navy, the form in slate and soft steel blue",
     "form": "a slow broad swell, like deep water seen from above, one long crest lit faintly"},
    {"name": "Forest dusk", "hues": (120, 155), "ground": "deep",
     "colour": "deep forest and bottle green, the form in moss and muted sage",
     "form": "a few large overlapping soft shapes like leaves in shadow, drifting very slowly"},
    {"name": "Aubergine hour", "hues": (280, 310), "ground": "deep",
     "colour": "aubergine and deep plum, the form in mauve and smoky lilac",
     "form": "one large rounded shape, lit from one side, its shadow side melting into the ground"},
    {"name": "Petrol depth", "hues": (175, 200), "ground": "deep",
     "colour": "deep petrol and dark teal, the form in muted aqua",
     "form": "soft vertical veils of colour hanging and swaying, like light far down in a lake"},
    {"name": "Umber ember", "hues": (15, 35), "ground": "deep",
     "colour": "dark umber and burnt sienna, the form in muted copper",
     "form": "one low, wide glow like the last embers under ash, breathing very slowly"},
    {"name": "Flow lines", "hues": (0, 360), "ground": "dark", "shapes": True,
     "colour": "one or two luminous colours on black, a soft glow around bright cores",
     "form": "a comb of thin bright lines released along one edge and flowing through a slow two-wave field, "
             "each line a few LEDs wide and brightest at its head, like the gallery's Flow Lines / Night Ridges"},
    {"name": "Dot trails", "hues": (0, 360), "ground": "dark", "shapes": True,
     "colour": "warm or cool luminous dots on black with a soft glow",
     "form": "dots left at a fixed spacing along a handful of flowing paths (Flow Dots), dots 2-3 LEDs across, "
             "brighter towards the path's head"},
    {"name": "Prism line", "hues": (0, 360), "ground": "dark",
     "colour": "white light splitting into a narrow soft spectrum only where it fans out",
     "form": "one thin vertical line of light opening into a soft spectral fan towards the bottom"},
]

GROUND = {   # mean brightness range (0..255) of the still for each ground
    "dark": (22, 80, "a dark ground, but the piece should still glow clearly (not a dim smudge on black)"),
    "mid": (40, 130, "a mid-tone ground: the whole wall is coloured, not black"),
    "light": (90, 150, "a light, high-key ground: pale paper or sky, with darker marks on it"),
    "deep": (30, 95, "a deep, dark COLOUR fills the whole wall (not black): the form is the same hue a few tones "
                     "lighter, a dark and moody piece"),
}


def _clashes(direction, recent_pals):
    """True when the direction's colour family sits on one of the last 3 pieces' colours, so every
    palette it allows would fail palette_problem's 'too close' rule."""
    lo, hi = direction["hues"]
    if (lo, hi) == (0, 360):
        return False
    for old in recent_pals[:3]:
        oh = _main_hue(old)
        if oh is not None and (_in_range(oh, lo, hi) or min(_hue_dist(oh, lo), _hue_dist(oh, hi)) < 25):
            return True
    return False


def pick(date, used=(), recent_pals=()):
    """The direction for this date: dealt from a deck shuffled per cycle, skipping recently used names
    and colour families the last days already showed."""
    d = datetime.date.fromisoformat(date) if isinstance(date, str) else date
    n = len(DIRECTIONS)
    cycle, pos = divmod(d.toordinal(), n)
    order = list(range(n))
    random.Random(cycle * 7919).shuffle(order)
    deck = [DIRECTIONS[order[(pos + k) % n]] for k in range(n)]
    for ok in (lambda c: c["name"] not in used and not _clashes(c, recent_pals),
               lambda c: not _clashes(c, recent_pals),
               lambda c: c["name"] not in used):
        for cand in deck:
            if ok(cand):
                return cand
    return deck[0]


VISIBILITY = (
    "VISIBILITY (measured on the real wall in a lit living room): anything darker than about 80/255 reads as black, "
    "so a piece whose brightest area is dim looks empty. Keep the key form luminous (peak 200-255, body above 110) "
    "and put the dark only in the background. Lines must be at least 2 LEDs wide and at least 100/255 bright "
    "(a 1-LED line vanishes unless nearly white); dots 2-3 LEDs across; neighbouring tones must differ by at "
    "least 30/255 or they merge into one. Soft glows are welcome but need a bright core.")


def brief(direction):
    lo, hi, words = GROUND[direction["ground"]]
    if direction.get("shapes"):
        style = ("Interpret it freely and make it yours: the house loves this thin-line / dot shape art on black. "
                 "Few, deliberate, flowing shapes with lots of calm space; no grids, checkerboards or dense fine "
                 "patterns - they shimmer on an LED wall.")
    else:
        style = ("Interpret it freely and make it yours, but stay inside it: ONE form, quiet and luminous, lots of "
                 "calm space around it. No stripes, checkerboards, grids of fine lines or other busy patterns - "
                 "they shimmer on an LED wall.")
    return (f"TODAY'S DIRECTION - \"{direction['name']}\" (required; it keeps the wall from repeating itself):\n"
            f"- colour: {direction['colour']}\n- ground: {words}\n- form: {direction['form']}\n"
            f"{style}\n\n{VISIBILITY_DEEP if direction['ground'] == 'deep' else VISIBILITY}")


VISIBILITY_DEEP = (
    "VISIBILITY (measured on the real wall in a lit living room): the wall lifts dark colours so they keep their "
    "hue, but keep the ground's strongest channel at least 45/255 everywhere (a true black reads as a hole, not "
    "a deep colour) and saturated, so it reads as a colour, not grey. The form must stand out by at least "
    "40/255 from the ground and reach 130-190 at its lightest; no white, no neon. Lines at least 3 LEDs wide.")


def visibility_problem(still, ground="dark"):
    """-> None if fine, else a note for the artist: would this read on the real wall? still = HxWx3 uint8."""
    import numpy as np
    mx = np.asarray(still).max(axis=2)
    if ground == "deep":
        p99, filled = float(np.percentile(mx, 99)), float((mx >= 40).mean())
        if filled < 0.7:
            return (f"only {filled * 100:.0f}% of the wall carries the deep colour (channel 40+/255): the ground "
                    "must be a dark colour everywhere, not black")
        if p99 < 120:
            return (f"its lightest areas only reach {p99:.0f}/255: the form needs to lift to 130-190 to read")
        if p99 - float(np.percentile(mx, 30)) < 40:
            return "the form does not stand out from the ground: make it at least 40/255 lighter"
        return None
    p99 = float(np.percentile(mx, 99))
    lit = float((mx >= 100).mean())
    if p99 < 170:
        return (f"its brightest areas only reach {p99:.0f}/255: on the real wall anything under ~80 looks black, so it "
                "would look empty. Make the key form luminous (peak 200-255) with a bright core")
    if lit < 0.025:
        return (f"only {lit * 100:.1f}% of the wall is brighter than 100/255: the form is too small or too dim to read. "
                "Make the main form larger or brighter, lines 2+ LEDs wide")
    return None


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
