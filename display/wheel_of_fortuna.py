"""The Wheel of Fortuna — AI-written fates for the flat, spun on the wall,
printed as an official verdict card.

    fates = generate_fates()                 # 8 x {label, emoji, verdict} via OpenAI
    frame(u, fates, winner)                  # u = seconds since the spin started
    card = verdict_card(fates[winner])       # greyscale PIL image for the printer

The winner is picked by the caller with Python's random, not by the AI.
"""
import datetime
import json
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw

import config
from display.maeva_story import _back, _clamp, _font, _text, _wrap
from display.pride_show import PRIDE, _emoji, _paste_emoji

RESIDENTS = ["Fionn", "Dewa"]
STREET = "Fortunagasse"
N = 8
SPIN_SEC = 18.0
PRINT_AT = 12.2
SEG_COLS = [tuple(int(v) for v in PRIDE[i % 6]) for i in range(6)] + [(245, 169, 184), (91, 206, 250)]

PROMPT = (
    "You are the Wheel of Fortuna in the hallway of House Fortuna, a fun, cheeky gay "
    f"flatshare at {STREET} in Zürich where {' and '.join(RESIDENTS)} live. Dewa is a flight "
    "attendant for Edelweiss. Invent exactly 8 different wheel outcomes: a mix of chores, "
    "treats, decisions, house rules and harmless dares, specific to Fionn and Dewa, funny "
    "and a little camp. For each give: label (max 2 short words, under 16 characters), emoji (exactly one emoji), "
    "verdict (one sentence, max 14 words, written like an official ruling that names who "
    "it applies to). Reply as JSON: {\"outcomes\": [{\"label\": ..., \"emoji\": ..., "
    "\"verdict\": ...}, ...]}"
)
FALLBACK = [
    {"label": "Toilet paper", "emoji": "🧻", "verdict": "Dewa buys the toilet paper. Two-ply. Today."},
    {"label": "Dishes", "emoji": "🍽️", "verdict": "Fionn does every dish in the sink. Yes, that one too."},
    {"label": "Movie night", "emoji": "🍿", "verdict": "Dewa picks tonight's film; Fionn may not complain."},
    {"label": "Cocktails", "emoji": "🍹", "verdict": "Fionn shakes cocktails for the house tonight."},
    {"label": "Bins", "emoji": "🗑️", "verdict": "Dewa takes the bins out in full uniform."},
    {"label": "Free pass", "emoji": "👑", "verdict": "Fionn is excused from all chores until midnight."},
    {"label": "Dance break", "emoji": "💃", "verdict": "Both of you dance in the hallway for one full song."},
    {"label": "Breakfast", "emoji": "🥐", "verdict": "Dewa brings croissants for Fionn tomorrow morning."},
]


# ------------------------------------------------------------------- AI ---

def _short(text, n):
    """Trim to n characters at a word boundary (no half words)."""
    text = text.strip()
    if len(text) <= n:
        return text
    cut = text[:n + 1].rsplit(" ", 1)[0].rstrip(" :,-")
    return cut or text[:n]


def generate_fates():
    """8 outcomes from OpenAI; falls back to a built-in set on any failure."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"),
                        timeout=config.AI_TIMEOUT_SEC + 10)
        r = client.chat.completions.create(
            model=config.AI_MODEL, temperature=1.1, max_tokens=700,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": PROMPT},
                      {"role": "user", "content": f"Spin #{random.randint(1, 10**6)}. Go."}])
        out = json.loads(r.choices[0].message.content)["outcomes"]
        fates = []
        for o in out[:N]:
            fates.append({"label": _short(str(o["label"]), 18),
                          "emoji": str(o["emoji"]).strip()[:8],
                          "verdict": _short(str(o["verdict"]), 120)})
        if len(fates) == N:
            return fates, "ai"
    except Exception as e:
        print(f"[WHEEL] AI failed, using fallback fates: {e}")
    fates = FALLBACK[:]
    random.shuffle(fates)
    return fates, "fallback"


# ------------------------------------------------------------- drawing ---

def _wheel(img, d, cx, cy, r, rot, fates, highlight=None, t=0.0):
    seg = 360 / N
    for i in range(N):
        a0 = rot + i * seg
        col = SEG_COLS[i]
        if highlight == i and int(t * 6) % 2 == 0:
            col = (255, 255, 255)
        d.pieslice([cx - r, cy - r, cx + r, cy + r], a0, a0 + seg, fill=col, outline=(0, 0, 0))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=3)
    for i, f in enumerate(fates):                                    # emoji on each slice
        a = math.radians(rot + i * seg + seg / 2)
        ex, ey = cx + r * 0.66 * math.cos(a), cy + r * 0.66 * math.sin(a)
        e = _emoji(f["emoji"], 15)
        if e is not None:
            img.paste(e, (int(ex - e.width / 2), int(ey - e.height / 2)), e)
    hub = r // 6
    d.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=(255, 215, 90), outline=(0, 0, 0))
    d.polygon([(cx - 8, cy - r - 10), (cx + 8, cy - r - 10), (cx, cy - r + 6)],
              fill=(255, 255, 255), outline=(0, 0, 0))                # pointer


def _under_pointer(rot):
    """Index of the slice currently under the pointer (top, -90 deg)."""
    seg = 360 / N
    return int(((-90 - rot) % 360) // seg)


def loading_frame(t):
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    img = Image.new("RGB", (W, H), (20, 8, 35))
    d = ImageDraw.Draw(img)
    _title(d, W, H, t)
    for i in range(8):                                               # spinner
        a = t * 4 + i * math.pi / 4
        c = int(80 + 175 * ((i / 8 + t) % 1))
        d.ellipse([W / 2 + 22 * math.cos(a) - 3, H * 0.58 + 22 * math.sin(a) - 3,
                   W / 2 + 22 * math.cos(a) + 3, H * 0.58 + 22 * math.sin(a) + 3],
                  fill=(c, c // 2, c))
    _text(d, (W / 2, H * 0.86), "consulting the fates...", 12, (230, 200, 255), anchor="mm")
    return img


def _title(d, W, H, t):
    s = 1 + 0.05 * math.sin(t * 4)
    _text(d, (W / 2, 12), "WHEEL OF FORTUNA", int(17 * s), (255, 215, 90), anchor="mm")
    _text(d, (W / 2, 28), " · ".join(RESIDENTS), 10, (255, 170, 210), stroke=1, anchor="mm")


def frame(u, fates, winner, t=None):
    """One frame of a spin. u = seconds since the spin started (0 .. SPIN_SEC)."""
    t = u if t is None else t
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    img = Image.new("RGB", (W, H), (20, 8, 35))
    d = ImageDraw.Draw(img)
    rs = random.Random(int(t * 3))
    for _ in range(25):                                              # twinkles
        d.point((rs.random() * W, rs.random() * H), fill=(120, 100, 160))
    seg = 360 / N
    rot_final = -90 - seg / 2 - winner * seg
    p = _clamp((u - 2.5) / 8.5)                                      # spin 2.5 .. 11 s
    rot = rot_final - 6 * 360 * (1 - p) ** 3
    if u < 12.0:
        _title(d, W, H, t)
        r = int(min(W, H) * 0.36 * _back(_clamp(u / 1.2)))
        cx, cy = W / 2, H * 0.6
        if r > 4:
            _wheel(img, d, cx, cy, r, rot, fates, winner if u > 11 else None, t)
        if 2.5 < u < 11:                                             # ticker
            f = fates[_under_pointer(rot)]
            d.rounded_rectangle([8, 36, W - 8, 52], 5, fill=(0, 0, 0), outline=(255, 215, 90))
            _text(d, (W / 2, 44), f["label"].upper(), 11, (255, 255, 255), stroke=0, anchor="mm")
        if u > 11.0:
            rs2 = random.Random(7)
            for _ in range(40):                                      # confetti burst
                a = rs2.random() * 6.283
                rr = (30 + rs2.random() * 90) * _clamp((u - 11) / 1.0)
                x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
                d.rectangle([x, y, x + 2, y + 2], fill=SEG_COLS[rs2.randrange(N)])
        return img
    # verdict screen
    f = fates[winner]
    v = u - 12.0
    k = _back(_clamp(v / 0.6))
    e = _emoji(f["emoji"], max(1, int(44 * k)))
    if e is not None:
        img.paste(e, (int(W / 2 - e.width / 2), 8), e)
    _text(d, (W / 2, 66), f["label"].upper(), min(22, int(22 * k) + 1), (255, 215, 90), anchor="mm")
    lines = _wrap(f["verdict"], 13, W - 14)
    n = int(v * 26)
    y = 84
    for ln in lines:
        _text(d, (W / 2, y), ln[:max(0, n)], 13, (255, 255, 255), stroke=1, anchor="mm")
        n -= len(ln) + 1
        y += 17
    if v > 1.5:
        dots = "." * (int(v * 3) % 4)
        _text(d, (W / 2, H - 22), "PRINTING YOUR FATE" + dots, 11, (255, 170, 210), anchor="mm")
        py = H - 12 + 0 * v
        h = min(10, (v - 1.5) * 6)
        d.rectangle([W / 2 - 16, py, W / 2 + 16, py + h], fill=(250, 250, 250))
    return img


# -------------------------------------------------------------- receipt ---

def verdict_card(fate, when=None):
    """Greyscale receipt image for the thermal printer."""
    from printer import _ttf, _wrap_px
    W = config.PRINTER_WIDTH_DOTS
    when = when or datetime.datetime.now()
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    f_head, f_small = _ttf(26), _ttf(18)
    f_label, f_body = _ttf(40), _ttf(26)
    label_lines = _wrap_px(probe, fate["label"].upper(), f_label, W - 16)
    body_lines = _wrap_px(probe, fate["verdict"], f_body, W - 20)
    emoji = _emoji(fate["emoji"], 96)
    h = (44 + 30 + 26 + (110 if emoji else 0) + len(label_lines) * 46
         + 12 + len(body_lines) * 32 + 20 + 26 + 24 + 90 + 20)
    out = Image.new("L", (W, h), 255)
    d = ImageDraw.Draw(out)

    def centred(y, s, font, fill=0):
        d.text(((W - d.textlength(s, font=font)) / 2, y), s, font=font, fill=fill)

    d.rectangle([0, 0, W, 40], fill=0)
    centred(6, "WHEEL OF FORTUNA", f_head, fill=255)
    y = 48
    centred(y, (config.PRINTER_HEADER or STREET).upper(), f_small); y += 24
    centred(y, when.strftime("%Y-%m-%d  %H:%M"), f_small); y += 30
    if emoji is not None:
        bg = Image.new("RGBA", emoji.size, (255, 255, 255, 255))
        bg.alpha_composite(emoji)
        out.paste(bg.convert("L"), ((W - emoji.width) // 2, y))
        y += 110
    for ln in label_lines:
        centred(y, ln, f_label); y += 46
    y += 12
    for ln in body_lines:
        centred(y, ln, f_body); y += 32
    y += 20
    centred(y, "Spun for " + " & ".join(RESIDENTS), f_small); y += 26
    centred(y, "This ruling is final. No appeals.", f_small); y += 30
    cx, cy, r = W // 2, y + 40, 38                                   # little wheel
    for i in range(N):
        d.pieslice([cx - r, cy - r, cx + r, cy + r], i * 45, i * 45 + 45,
                   fill=255 if i % 2 else 0, outline=0)
    d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=255, outline=0)
    return out
