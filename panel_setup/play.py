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
import math
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")     # numpy must not fight the panel refresh for cores
os.environ.setdefault("OMP_NUM_THREADS", "1")
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


_sg = None


def _shader_gallery_frame(t):
    """GPU shader gallery (slow, two-hue pieces) via the usual cross-fading Gallery."""
    global _sg
    if _sg is None:
        from display import art, shaders
        g = art.Gallery.__new__(art.Gallery)
        g.pieces = shaders.gallery_pieces(config.TOTAL_WIDTH, config.TOTAL_HEIGHT)
        g.last_t, g.current = None, -1
        _sg = g
    return _sg(t)


_pc = {"piece": None, "last": None}


def _piece_frame(t):
    """One piece from the library, chosen in the app (WALL_PIECE), on the wall for as long as you like."""
    from PIL import Image
    import numpy as np
    from display import library
    if _pc["piece"] is None:
        pid = os.environ.get("WALL_PIECE", "") or library.catalogue()[0]["id"]
        _pc["piece"] = library.make(pid) or library.make(library.catalogue()[0]["id"])
        _pc["piece"].reset()
    dt = 0.04 if _pc["last"] is None else max(0.0, min(0.2, t - _pc["last"]))
    _pc["last"] = t
    img = _pc["piece"].render(dt, t)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def _anims():
    from display import (welcome, pride_show, cards, maeva_story, dewa_story, art,
                         departures, music, shapes, light_art, artsy, shaders, daily)
    return {
        "music":   (music.frame, 600.0),
        "trams":   (departures.frame, 60.0),
        "ambient": (departures.ambient_frame, 600.0),
        "art":     (art.frame_everything, 3600.0),
        "shapes":  (shapes.frame, shapes.LOOP_SEC),
        "glass":   (light_art.frame, light_art.LOOP_SEC),
        "artsy":   (artsy.frame, artsy.LOOP_SEC),
        "shaders": (_shader_gallery_frame, 60.0 * 5),
        "piece":   (_piece_frame, 3600.0),
        "daily":   (daily.frame, 3600.0),
        "lava":    (art.frame_lava_coral, art.LAVA_CORAL_LOOP_SEC),
        "dewa":    (dewa_story.frame, dewa_story.LOOP_SEC),
        "maeva":   (maeva_story.frame, maeva_story.LOOP_SEC),
        "pride":   (pride_show.frame, pride_show.LOOP_SEC),
        "welcome": (welcome.welcome_frame, welcome.LOOP_SEC),
        "cow":     (cards.cow_card, 1.0),
    }


ART_MODES = {"art", "lava", "shapes", "glass", "artsy", "ambient", "shaders", "piece"}   # galleries: art for the house, slow
ART_SPEED = float(os.environ.get("WALL_ART_SPEED", "0.12"))         # 1.0 = the old pace; sleep-friendly by default


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
        measured = self.inten.update(f, time.time(), sens)            # quiet evening .. dance floor
        lvl = measured if self.st.get("mode") == "auto" else self.st.get("party", 15) / 100.0
        P = music.profile("auto", lvl)
        energy = min(1.0, f["energy"] * react)
        tempo = music.tempo_factor(f.get("bpm", 0.0), f.get("bconf", 0.0), "chill" if lvl < 0.5 else "techno")
        self.t += dt * tempo * (0.9 + 0.4 * energy * lvl)
        self.env = music._ema(self.env, energy, dt, 2.5)            # slow breathing only, never per beat
        br = P["breath"]
        return self.t, 0.95 + 0.06 * br * self.env


class _SimMatrix:
    """The panel wall in a window on a laptop (pygame), with the same draw() contract."""

    def __init__(self):
        from simulator.led_simulator import LEDSimulator
        self.sim = LEDSimulator()
        self.last = 0.0

    def draw(self, image, frame_fraction=1):
        for ev in self.sim.pump_events():
            if ev.type == self.sim.pygame.QUIT:
                raise KeyboardInterrupt
        self.sim.draw(image)
        self.sim.tick()
        # pace like the real wall (29 fps)
        wait = self.last + frame_fraction / float(config.MATRIX_REFRESH_LIMIT_HZ) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        return True

    def clear(self):
        self.sim.clear()
        self.sim.tick()


def _matrix():
    if os.environ.get("WALL_SIM") or sys.platform == "darwin":
        return _SimMatrix()
    from led_matrix import LedMatrix
    return LedMatrix()


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
    """Warm the animation up (first-frame set-up can take seconds on the Pi) while the wall shows a
    progress bar that eases towards 90% and snaps to 100% when it is ready. The warm-up runs on THIS
    thread: a GPU (EGL) context only works on the thread that made it, so warming up on a side thread
    left every later frame black or garbled. The bar is drawn from the side thread instead."""
    import math
    import threading
    done = threading.Event()

    def bar():
        t0, p = time.monotonic(), 0.0
        while True:
            el = time.monotonic() - t0
            target = 1.0 if done.is_set() else 0.9 * (1 - math.exp(-el / 2.5))
            p += (target - p) * 0.25
            matrix.draw(_boot_frame(p))
            if done.is_set() and p > 0.985:
                break
            time.sleep(0.05)

    th = threading.Thread(target=bar, daemon=True)
    th.start()
    try:
        frame_fn(0.0)
    finally:
        done.set()
        th.join(timeout=10)
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

    from display import dedications
    matrix = _matrix()
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
    presence = None                                     # people on the art (app switch, off by default)
    if os.environ.get("WALL_PRESENCE") == "1" and a.anim in ART_MODES | {"music", "daily"}:
        from display.presence import Presence
        presence = Presence(config.TOTAL_WIDTH, config.TOTAL_HEIGHT)
    stats = [] if os.environ.get("WALL_STATS") else None
    stats_t = time.monotonic()
    # 58 fps (a new frame every panel refresh) when the mode is light enough, else 29 fps (each frame
    # held for 2 refreshes). Halving the step between frames is what makes slow motion stop quivering.
    refresh = float(config.MATRIX_REFRESH_LIMIT_HZ)
    ff_min = max(1, math.ceil(refresh / 60.0 - 0.01))   # fewest refreshes per frame: 58 Hz -> 1 (58 fps), 90 Hz -> 2 (45 fps)
    ff = ff_min if a.fps >= 50 else max(1, round(refresh / a.fps))    # a heavy mode holds each frame ~30 fps
    recent = []
    # The animation's clock runs on the panels' refresh, not on when Python gets round to a frame:
    # each frame is drawn for the moment it will be on screen (last swap + ff refreshes), so motion
    # advances in exactly equal steps. The refresh period is measured; a dropped refresh or a long
    # pause pulls the clock back to real time.
    period, shown, tv, late = 1 / (refresh + 0.1), None, 0.0, 0
    import gc
    gc.collect()
    gc.freeze()                                         # start-up objects never rescanned mid-frame
    try:
        while True:
            now = time.monotonic()
            if shown is None or now - shown > 0.25:
                tv = now - t0
            else:
                tv += ff * period
                tv += 0.02 * ((now - t0) - tv)          # slow pull towards real time, never a jump
            t = tv
            if a.seconds and t > a.seconds:
                break
            # each frame held for exactly ff refreshes (58 Hz -> 58 or 29 fps), paced by the
            # panels' own vsync instead of a sleep timer that drifts against it
            c0 = time.perf_counter()
            gain = 1.0
            if clock is not None:
                t, gain = clock.step(t)
            if a.anim in ART_MODES:
                t *= ART_SPEED                               # house art: slow
            img = frame_fn(t)
            if presence is not None:
                img = presence.apply(img, ff / refresh)
            img = overlay.apply(img)
            if gain < 0.999 or gain > 1.001:
                img = img.point([min(255, int(i * gain)) for i in range(256)] * 3)
            c1 = time.perf_counter()
            if not matrix.draw(img, frame_fraction=ff):
                time.sleep(interval / (2 if ff == 1 else 1))   # unchanged frame: nothing to pace
                shown = None
            else:
                ts = time.monotonic()
                if shown is not None:
                    gap = (ts - shown) / ff
                    if abs(gap - period) < 0.15 * period:  # a normal swap: refine the refresh period
                        period += 0.01 * (gap - period)
                    elif gap > 1.5 * period:
                        late += 1
                shown = ts
            if a.fps >= 50:                             # adapt: heavy moments take more refreshes per frame
                recent.append(c1 - c0 + getattr(matrix, "send_s", 0.003))   # render + sending it, not the vsync wait
                if len(recent) >= 60:
                    worst = sorted(recent)[int(len(recent) * 0.9)] * 1000
                    if worst > ff * 1000 / refresh - 2.0 and ff < 4:   # misses its slot: give it one more refresh
                        ff += 1
                        print(f"[fps] {refresh / ff:.0f} fps (frames take {worst:.0f} ms)", flush=True)
                    elif ff > ff_min and len(recent) >= 300 and worst < (ff - 1) * 1000 / refresh - 6.0:
                        ff -= 1
                        print(f"[fps] {refresh / ff:.0f} fps (frames take {worst:.0f} ms)", flush=True)
                    if ff == ff_min or len(recent) >= 300:
                        recent.clear()
            if stats is not None:
                stats.append((c1 - c0, time.perf_counter() - c1))
                if time.monotonic() - stats_t > 10.0:
                    import numpy as np
                    arr = np.array(stats) * 1000
                    print(f"[stats] {len(arr)} frames/10s  render p50 {np.percentile(arr[:,0],50):.1f} p95 "
                          f"{np.percentile(arr[:,0],95):.1f} max {arr[:,0].max():.1f} ms | draw(wait) p50 "
                          f"{np.percentile(arr[:,1],50):.1f} p95 {np.percentile(arr[:,1],95):.1f} "
                          f"max {arr[:,1].max():.1f} ms (budget {ff * 1000 / refresh:.1f}, {refresh / ff:.0f} fps) | late {late} | "
                          f"refresh {1 / period:.2f} Hz", flush=True)
                    stats.clear()
                    late = 0
                    stats_t = time.monotonic()
    except KeyboardInterrupt:
        pass
    matrix.clear()


if __name__ == "__main__":
    main()
