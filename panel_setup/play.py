"""Play a wall animation.

    sudo python3 panel_setup/play.py pride               # HOUSE FORTUNA pride show
    sudo python3 panel_setup/play.py welcome             # the first welcome animation
    sudo python3 panel_setup/play.py maeva               # Maeva in Zürich, a little story
    sudo python3 panel_setup/play.py ambient             # lava & coral + subtle tram ticker
    sudo python3 panel_setup/play.py trams               # live departures, Zürich Rennweg
    sudo python3 panel_setup/play.py lava                # lava & coral gallery (10 pieces)
    sudo python3 panel_setup/play.py art                 # slow generative art gallery
    sudo python3 panel_setup/play.py dewa                # Dewa, Edelweiss flight attendant
    sudo python3 panel_setup/play.py cow                 # "Dewa is a cow" card
    sudo python3 panel_setup/play.py pride --seconds 60
    python3 panel_setup/play.py pride --gif preview.gif  # offline preview, no hardware
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def _anims():
    from display import (welcome, pride_show, cards, maeva_story, dewa_story, art,
                         departures)
    return {
        "trams":   (departures.frame, 60.0),
        "ambient": (departures.ambient_frame, 600.0),
        "tickerdemo": (departures.demo_frame, 45.0),
        "art":     (art.frame, art.LOOP_SEC),
        "lava":    (art.frame_lava_coral, art.LAVA_CORAL_LOOP_SEC),
        "dewa":    (dewa_story.frame, dewa_story.LOOP_SEC),
        "maeva":   (maeva_story.frame, maeva_story.LOOP_SEC),
        "pride":   (pride_show.frame, pride_show.LOOP_SEC),
        "welcome": (welcome.welcome_frame, welcome.LOOP_SEC),
        "cow":     (cards.cow_card, 1.0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("anim", nargs="?", default="pride", help="ambient | trams | lava | art | pride | maeva | dewa | welcome | cow")
    ap.add_argument("--seconds", type=float, default=0, help="stop after N s (0 = forever)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--gif", help="write one loop to this GIF instead of the wall")
    ap.add_argument("--gif-scale", type=int, default=2)
    a = ap.parse_args()
    frame_fn, loop_sec = _anims()[a.anim]

    if a.gif:
        from PIL import Image
        n = max(1, int(loop_sec * 15))
        frames = [frame_fn(i / 15).resize(
            (config.TOTAL_WIDTH * a.gif_scale, config.TOTAL_HEIGHT * a.gif_scale),
            Image.NEAREST) for i in range(n)]
        frames[0].save(a.gif, save_all=True, append_images=frames[1:],
                       duration=int(1000 / 15), loop=0)
        print(f"wrote {a.gif} ({n} frames)")
        return

    from led_matrix import LedMatrix
    matrix = LedMatrix()
    interval = 1.0 / a.fps
    t0 = time.monotonic()
    try:
        while True:
            t = time.monotonic() - t0
            if a.seconds and t > a.seconds:
                break
            matrix.draw(frame_fn(t))
            time.sleep(max(0.0, interval - (time.monotonic() - t0 - t)))
    except KeyboardInterrupt:
        pass
    matrix.clear()


if __name__ == "__main__":
    main()
