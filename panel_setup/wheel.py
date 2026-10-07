"""Spin the Wheel of Fortuna on the wall: AI writes the fates, the Pi picks the
winner, the printer prints the verdict card.

    sudo python3 panel_setup/wheel.py               # one spin
    sudo python3 panel_setup/wheel.py --spins 3
    sudo python3 panel_setup/wheel.py --no-print    # no receipt
    python3 panel_setup/wheel.py --preview out.png  # offline: one card + frames, no hardware
"""
import argparse
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import config
from display import wheel_of_fortuna as wof


def spin_once(matrix, printer, fps, n, total):
    result = {}
    th = threading.Thread(target=lambda: result.update(zip(("fates", "src"), wof.generate_fates())),
                          daemon=True)
    th.start()
    t0 = time.monotonic()
    while th.is_alive() or time.monotonic() - t0 < 2.0:              # loading screen
        matrix.draw(wof.loading_frame(time.monotonic() - t0))
        time.sleep(1 / fps)
    fates, src = result["fates"], result["src"]
    winner = random.randrange(wof.N)
    print(f"[WHEEL] spin {n}/{total} ({src}):")
    for i, f in enumerate(fates):
        mark = "  <== WINNER" if i == winner else ""
        print(f"    {f['emoji']}  {f['label']}: {f['verdict']}{mark}")
    t0 = time.monotonic()
    printed = False
    while True:
        u = time.monotonic() - t0
        if u > wof.SPIN_SEC:
            break
        matrix.draw(wof.frame(u, fates, winner))
        if u >= wof.PRINT_AT and not printed and printer is not None:
            printed = True
            card = wof.verdict_card(fates[winner])
            threading.Thread(target=printer.print_strip, args=(card,), daemon=True).start()
        time.sleep(max(0.0, 1 / fps - (time.monotonic() - t0 - u)))
    return fates[winner]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spins", type=int, default=1)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--no-print", action="store_true")
    ap.add_argument("--preview", help="offline: save a card + key frames to this PNG")
    a = ap.parse_args()

    if a.preview:
        from PIL import Image
        fates, src = wof.generate_fates()
        winner = random.randrange(wof.N)
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        frames = [wof.loading_frame(1.0)] + [wof.frame(u, fates, winner) for u in (1.5, 6.0, 11.5, 15.0)]
        card = wof.verdict_card(fates[winner]).convert("RGB")
        sheet = Image.new("RGB", (W * 2 * len(frames) + card.width, max(H * 2, card.height)))
        for i, f in enumerate(frames):
            sheet.paste(f.resize((W * 2, H * 2), Image.NEAREST), (i * W * 2, 0))
        sheet.paste(card, (len(frames) * W * 2, 0))
        sheet.save(a.preview)
        print(f"({src}) winner: {fates[winner]}")
        return

    from led_matrix import LedMatrix
    import printer as printer_mod
    matrix = LedMatrix()
    printer = None if a.no_print else printer_mod.create_printer()
    try:
        for n in range(1, a.spins + 1):
            spin_once(matrix, printer, a.fps, n, a.spins)
            time.sleep(1.5)                                          # let the printer finish
    except KeyboardInterrupt:
        pass
    matrix.clear()


if __name__ == "__main__":
    main()
