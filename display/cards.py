"""Static message cards for the wall."""
from PIL import Image, ImageDraw

import config
from display import text_renderer as tr

COW = [
    "..Y..........Y..",
    "..YY........YY..",
    ".KKWWWWWWWWWWKK.",
    "KKKWWWKKWWWWWKKK",
    "...WWKKKWWWWWW..",
    "...WEWWWWWWEWW..",
    "...WEWWWWWWEWW..",
    "...WWWWWWWWWWW..",
    "..PPPPPPPPPPPP..",
    ".PPPPPPPPPPPPPP.",
    ".PPKKPPPPPPKKPP.",
    ".PPKKPPPPPPKKPP.",
    ".PPPPPPPPPPPPPP.",
    "..PPPPPPPPPPPP..",
]
PALETTE = {"W": (235, 235, 235), "K": (0, 0, 0), "E": (0, 0, 0),
           "P": (255, 110, 160), "Y": (220, 180, 90)}


def text_card(lines, sprite=None, scale=4, t=0.0):
    """Centred outlined text lines, with an optional pixel-art sprite below."""
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    y = 14
    for line in lines:
        l, t0, w, h = tr._text_box(d, line)
        d.text(((W - w) // 2 - l, y - t0), line, fill=tuple(config.TEXT_COLOUR),
               font=tr._FONT, stroke_width=tr._STROKE, stroke_fill=tr._STROKE_FILL)
        y += h + 6
    if sprite:
        cw, ch = len(sprite[0]) * scale, len(sprite) * scale
        x0, y0 = (W - cw) // 2, y + max(4, (H - y - ch) // 2)
        for r, row in enumerate(sprite):
            for c, k in enumerate(row):
                if k in PALETTE:
                    d.rectangle([x0 + c * scale, y0 + r * scale,
                                 x0 + c * scale + scale - 1, y0 + r * scale + scale - 1],
                                fill=PALETTE[k])
    return img


def cow_card(t=0.0):
    return text_card(["Dewa is", "a cow"], COW)
