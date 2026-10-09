"""The house's mood board: the newest pins of a public Pinterest board, read through the board's
public RSS feed (no login, no Pinterest app), laid out as one contact sheet for Claude to look at.

    sheet, n = moodboard.sheet()        # JPEG bytes (or None) and how many pins it shows
Cached once a day under assets/daily/moodboard.jpg. The board is config.MOODBOARD (user/board).
"""
import datetime
import io
import os
import re
import urllib.request

import config

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(_HERE, "assets", "daily", "moodboard.jpg")
UA = {"User-Agent": "Mozilla/5.0 (FortunaWall moodboard)"}


def _get(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def pins(limit=12):
    """Image URLs of the newest pins (largest size Pinterest serves without login)."""
    board = getattr(config, "MOODBOARD", "")
    if not board:
        return []
    xml = _get(f"https://www.pinterest.com/{board.strip('/')}.rss").decode("utf-8", "replace")
    urls = re.findall(r'https://i\.pinimg\.com/236x/[^"&\s]+\.(?:jpg|png|webp)', xml)
    out = []
    for u in urls:
        u = u.replace("/236x/", "/474x/")
        if u not in out:
            out.append(u)
    return out[:limit]


def sheet(limit=12, refresh=False):
    """-> (jpeg bytes or None, pin count). A 4 x 3 grid, each pin fitted into a 256 px cell."""
    from PIL import Image, ImageOps
    today = datetime.date.today().isoformat()
    if not refresh and os.path.exists(CACHE) and \
            datetime.date.fromtimestamp(os.path.getmtime(CACHE)).isoformat() == today:
        with open(CACHE, "rb") as fh:
            data = fh.read()
        return data, None
    try:
        urls = pins(limit)
    except Exception as e:
        print(f"[moodboard] board not readable: {e}", flush=True)
        return None, 0
    imgs = []
    for u in urls:
        try:
            imgs.append(Image.open(io.BytesIO(_get(u))).convert("RGB"))
        except Exception:
            try:
                imgs.append(Image.open(io.BytesIO(_get(u.replace("/474x/", "/236x/")))).convert("RGB"))
            except Exception:
                pass
    if not imgs:
        return None, 0
    cols, cell = 4, 256
    rows = (len(imgs) + cols - 1) // cols
    out = Image.new("RGB", (cols * cell, rows * cell), (0, 0, 0))
    for i, im in enumerate(imgs):
        out.paste(ImageOps.contain(im, (cell - 8, cell - 8)), ((i % cols) * cell + 4, (i // cols) * cell + 4))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=82)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "wb") as fh:
        fh.write(buf.getvalue())
    return buf.getvalue(), len(imgs)
