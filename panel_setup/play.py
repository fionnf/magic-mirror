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
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")     # numpy must not fight the panel refresh for cores
os.environ.setdefault("OMP_NUM_THREADS", "1")
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def _anims():
    from display import (welcome, pride_show, cards, maeva_story, dewa_story, art,
                         departures, music, shapes, light_art, artsy)
    return {
        "music":   (music.frame, 600.0),
        "trams":   (departures.frame, 60.0),
        "ambient": (departures.ambient_frame, 600.0),
        "tickerdemo": (departures.demo_frame, 45.0),
        "art":     (art.frame, art.LOOP_SEC),
        "shapes":  (shapes.frame, shapes.LOOP_SEC),
        "glass":   (light_art.frame, light_art.LOOP_SEC),
        "artsy":   (artsy.frame, artsy.LOOP_SEC),
        "lava":    (art.frame_lava_coral, art.LAVA_CORAL_LOOP_SEC),
        "dewa":    (dewa_story.frame, dewa_story.LOOP_SEC),
        "maeva":   (maeva_story.frame, maeva_story.LOOP_SEC),
        "pride":   (pride_show.frame, pride_show.LOOP_SEC),
        "welcome": (welcome.welcome_frame, welcome.LOOP_SEC),
        "cow":     (cards.cow_card, 1.0),
    }


ART_MODES = {"art", "lava", "shapes", "glass", "artsy", "ambient"}   # galleries: art for the house, slow
ART_SPEED = float(os.environ.get("WALL_ART_SPEED", "0.35"))         # 1.0 = the old pace


class _MusicClock:
    """Optional: when "Make all art move to music" is on (app, Music card) and music is playing,
    any art mode runs faster with the energy and breathes on the detected beat. In silence it is
    ordinary time - so nothing changes unless there is music."""

    def __init__(self):
        self.l, self.enabled, self.checked, self.t, self.last = None, False, 0.0, 0.0, None
        self.st = {}
        self.phase = 0.0
        self.inten, self.env = None, 0.0

    def _poll(self, now):
        if now - self.checked < 3.0:
            return
        self.checked = now
        try:
            from display import music
            self.st = music.load_settings()
            self.enabled = bool(self.st["art_reacts"])
            if self.enabled and self.l is None:
                from display.intensity import Intensity
                self.l, self.inten = music.Listener(), Intensity()
        except Exception as e:
            print(f"[music-clock] {e}")
            self.enabled = False

    def step(self, real_t):
        """-> (time for the animation, brightness factor)"""
        now = time.monotonic()
        dt = 0.0 if self.last is None else max(0.0, min(0.2, real_t - self.last))
        self.last = real_t
        self._poll(now)
        if not (self.enabled and self.l is not None) or self.l.f["silent"]:
            self.t += dt
            return self.t, 1.0
        from display import music
        f = self.l.f
        sens = self.st.get("sensitivity", 50)
        react = music.reactivity(sens)
        lvl = self.inten.update(f, time.time(), sens)                 # quiet evening .. dance floor
        P = music.profile("auto", lvl)
        energy = min(1.0, f["energy"] * react)
        tempo = music.tempo_factor(f.get("bpm", 0.0), f.get("bconf", 0.0), "chill" if lvl < 0.5 else "techno")
        self.t += dt * tempo * (0.9 + 0.6 * energy * lvl)
        (pulse, self.phase, w), _ = music.beat_pulse(f, time.time(), 0, 1.0, self.phase)
        self.env = music._ema(self.env, min(1.0, f["kick"] * react), dt, P["smooth"])
        mix = w * P["pulse"]
        kick = (1 - mix) * self.env + mix * pulse
        br = P["breath"]
        return self.t, 1.0 - 0.1 * br + 0.14 * br * kick


def _boot_frame(progress):
    """Start-up screen: HOUSE FORTUNA and a progress bar (shown while the animation loads)."""
    from PIL import Image, ImageDraw
    from display import text_renderer
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    img = Image.new("RGB", (W, H), (6, 3, 12))
    d = ImageDraw.Draw(img)
    f = text_renderer._load_font(26)
    for i, word in enumerate(("HOUSE", "FORTUNA")):
        w = d.textlength(word, font=f)
        d.text(((W - w) / 2, 34 + i * 34), word, font=f, fill=(255, 150, 215) if i == 0 else (255, 214, 120))
    x0, x1, y0, y1 = 36, W - 36, 128, 140
    d.rounded_rectangle([x0, y0, x1, y1], radius=6, outline=(120, 80, 150), width=1)
    fill = int((x1 - x0 - 4) * max(0.0, min(1.0, progress)))
    for x in range(fill):                                  # pink -> gold gradient
        u = x / max(1, x1 - x0 - 4)
        d.line([(x0 + 2 + x, y0 + 2), (x0 + 2 + x, y1 - 2)],
               fill=(int(255 * (0.9 + 0.1 * u)), int(110 + 110 * u), int(190 - 100 * u)))
    small = text_renderer._load_font(11)
    label = "starting up" if progress < 1 else "ready"
    d.text(((W - d.textlength(label, font=small)) / 2, y1 + 8), label, font=small, fill=(170, 150, 190))
    return img


def _loading_screen(matrix, frame_fn):
    """Warm the animation up in a thread (first-frame set-up can take seconds on the Pi) while
    the wall shows a progress bar that eases towards 90% and snaps to 100% when it is ready."""
    import math
    import threading
    done = threading.Event()

    def warm():
        try:
            frame_fn(0.0)
        finally:
            done.set()
    threading.Thread(target=warm, daemon=True).start()
    t0, p = time.monotonic(), 0.0
    while True:
        el = time.monotonic() - t0
        target = 1.0 if done.is_set() else 0.9 * (1 - math.exp(-el / 2.5))
        p += (target - p) * 0.25
        matrix.draw(_boot_frame(p))
        if done.is_set() and p > 0.985:
            break
        time.sleep(0.05)
    matrix.draw(_boot_frame(1.0))
    time.sleep(0.25)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("anim", nargs="?", default="pride", help="music | ambient | trams | shapes | glass | artsy | lava | art | pride | maeva | dewa | welcome | cow")
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
    from display import dedications
    matrix = LedMatrix()
    overlay = dedications.Overlay()
    interval = 1.0 / a.fps
    booting = bool(os.environ.get("WALL_BOOT"))          # set by wall_control for the first start after power-on only
    if booting:
        try:
            _loading_screen(matrix, frame_fn)
        except KeyboardInterrupt:                        # stopped while starting up
            return
        except Exception as e:
            print(f"[boot] loading screen skipped: {e}")
    if booting and a.anim not in ("welcome", "music"):
        try:                                             # power-on greeting, once
            from display import welcome
            tw = time.monotonic()
            while time.monotonic() - tw < welcome.LOOP_SEC:
                if not matrix.draw(welcome.welcome_frame(time.monotonic() - tw), frame_fraction=2):
                    time.sleep(interval)
        except KeyboardInterrupt:
            return
        except Exception as e:
            print(f"[boot] welcome skipped: {e}")
    t0 = time.monotonic()
    clock = _MusicClock() if a.anim != "music" else None
    stats = [] if os.environ.get("WALL_STATS") else None
    stats_t = time.monotonic()
    try:
        while True:
            t = time.monotonic() - t0
            if a.seconds and t > a.seconds:
                break
            # each frame held for exactly 2 refreshes (58 Hz -> 29 fps), paced by the
            # panels' own vsync instead of a sleep timer that drifts against it
            c0 = time.perf_counter()
            gain = 1.0
            if clock is not None:
                t, gain = clock.step(t)
            if a.anim in ART_MODES:
                t *= ART_SPEED                               # house art: slow
            img = overlay.apply(frame_fn(t))
            if gain < 0.999 or gain > 1.001:
                img = img.point([min(255, int(i * gain)) for i in range(256)] * 3)
            c1 = time.perf_counter()
            if not matrix.draw(img, frame_fraction=2):
                time.sleep(interval)                    # unchanged frame: nothing to pace
            if stats is not None:
                stats.append((c1 - c0, time.perf_counter() - c1))
                if time.monotonic() - stats_t > 10.0:
                    import numpy as np
                    arr = np.array(stats) * 1000
                    print(f"[stats] {len(arr)} frames/10s  render p50 {np.percentile(arr[:,0],50):.1f} p95 "
                          f"{np.percentile(arr[:,0],95):.1f} max {arr[:,0].max():.1f} ms | draw(wait) p50 "
                          f"{np.percentile(arr[:,1],50):.1f} p95 {np.percentile(arr[:,1],95):.1f} "
                          f"max {arr[:,1].max():.1f} ms (budget 34.5)", flush=True)
                    stats.clear()
                    stats_t = time.monotonic()
    except KeyboardInterrupt:
        pass
    matrix.clear()


if __name__ == "__main__":
    main()
