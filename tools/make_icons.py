#!/usr/bin/env python3
"""Render a real picture for every gallery tile and commit them, so the app never shows a blank tile:

    .venv/bin/python tools/make_icons.py

  panel_setup/art_icons/<piece id>.jpg   every shader / python / VJ piece (192 x 256)
  panel_setup/web/icons/<mode id>.png    every mode tile (a still from the real piece where it can be made offline,
                                         else a designed icon)
The wall prefers the thumbnails it makes itself and falls back to these (wall_control.py).
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "panel_setup"))
os.environ.setdefault("WALL_SIM", "1")

from PIL import Image, ImageDraw  # noqa: E402

import wall_control as w  # noqa: E402
from display import library  # noqa: E402

ART = os.path.join(HERE, "panel_setup", "art_icons")
ICONS = os.path.join(HERE, "panel_setup", "web", "icons")
SYMBOL = {"daily": ("🎨", (60, 30, 70)), "flow": ("🌊", (10, 30, 60)), "piece": ("🖼️", (40, 30, 20)),
          "exposure": ("📷", (25, 25, 45)), "snapshots": ("🪞", (20, 40, 40)), "livecam": ("🏔️", (20, 45, 70)),
          "planes": ("✈️", (10, 25, 55)), "limmat": ("🌊", (10, 50, 60)), "westcork": ("🌊", (10, 20, 45)),
          "windch": ("💨", (15, 35, 60)), "windie": ("💨", (10, 45, 40)), "windeu": ("💨", (30, 25, 60)),
          "nighttrains": ("🚆", (15, 15, 45)), "issday": ("🛰️", (5, 15, 40)), "wanderers": ("🐢", (5, 40, 55)),
          "skylines": ("🌆", (45, 25, 60)), "polarbears": ("🐻‍❄️", (30, 50, 70)), "snow": ("❄️", (30, 45, 70)),
          "satellites": ("🛰️", (10, 10, 35)), "tides": ("🌊", (5, 35, 60)), "tramlines": ("🚋", (0, 45, 110)),
          "laend": ("🍇", (50, 30, 60)), "quakes": ("🌍", (40, 20, 30)), "lennart": ("🍎", (60, 30, 30)),
          "kilchberg": ("🚆", (0, 45, 110)), "zurichhb": ("🚆", (0, 45, 110))}


def designed(mode, title):
    from display.pride_show import _emoji
    import config
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    ch, bg = SYMBOL.get(mode, ("✨", (30, 30, 60)))
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(c * (1.4 - 0.9 * t)) for c in bg))
    e = _emoji(ch, 90)
    if e is not None:
        img.paste(e, ((W - e.width) // 2, 40), e)
    d.text((W // 2, H - 34), title, fill=(255, 255, 255), anchor="mm")
    return img


def main():
    os.makedirs(ART, exist_ok=True)
    os.makedirs(ICONS, exist_ok=True)
    n = 0
    for p in library.public():
        if p.get("kind") == "daily":
            continue
        try:
            src = library.thumb(p["id"])
            shutil.copy(src, os.path.join(ART, p["id"] + ".jpg"))
            n += 1
        except Exception as e:
            print("piece", p["id"], e)
    print(n, "piece icons")
    w.THUMB_DIR = ICONS                                       # let the app's own generator fill the icons folder
    w.make_thumbs()
    titles = {i: t for i, c, t, d in w.MODES}
    for mode, title in titles.items():
        path = os.path.join(ICONS, mode + ".png")
        if not os.path.exists(path):
            designed(mode, title[:18]).save(path)
            print("designed icon:", mode)
    print(len(os.listdir(ICONS)), "mode icons")


if __name__ == "__main__":
    main()
