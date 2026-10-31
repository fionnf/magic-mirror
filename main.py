"""Magic Mirror — main state machine.

Runs on real hardware by default, or with --sim using the simulator.

The live silhouette is ALWAYS rendered as the background of whatever the mirror
is showing — idle, thinking, or speaking. A dedicated thread continuously
captures camera frames, extracts the silhouette mask, and stores the latest
rendered overlay in `_live_silhouette` for the display loop to composite.
"""
import argparse
import signal
import sys
import time

import numpy as np
import math
import threading
import enum
from typing import Optional
from PIL import Image, ImageDraw, ImageOps

from dotenv import load_dotenv
load_dotenv()

import config
from display import animations, text_renderer, silhouette as silhouette_render
from api import MirrorAPI
from mqtt_bridge import MQTTBridge


class State(enum.Enum):
    IDLE = "IDLE"
    TRIGGERED = "TRIGGERED"
    CAPTURING = "CAPTURING"
    AI_WAITING = "AI_WAITING"
    DISPLAYING = "DISPLAYING"
    FADE_OUT = "FADE_OUT"
    BOOTH = "BOOTH"


class NullButton:
    """Stand-in when no touch sensor is wired up. Triggers come from the
    dashboard/API, MQTT, or --auto."""
    def __init__(self, short_cb=None, long_cb=None):
        pass

    def handle_event(self, event):
        pass

    def shutdown(self):
        pass


def start_auto_trigger(mirror, every_sec: float, booth_every: int = 0,
                       count: int = 0):
    """Press the 'button' every N seconds while idle (hands-free testing).
    count > 0 stops after that many presses; the mirror then stays idle."""
    def loop():
        n = 0
        while not mirror._stop.wait(every_sec):
            if count and n >= count:
                if mirror.state == State.IDLE:
                    print(f"[AUTO] done: {count} cycles")
                    return
                continue
            if mirror.state == State.IDLE:
                n += 1
                if booth_every and n % booth_every == 0:
                    mirror._booth_event.set()
                else:
                    mirror._trigger_event.set()
    threading.Thread(target=loop, daemon=True, name="auto-trigger").start()


class MagicMirror:
    def __init__(self, matrix, camera, button_factory, strip, printer,
                 sim_mode: bool, no_api: bool, booth_mode: bool = False):
        self.booth_mode = booth_mode              # photobooth mode: a tap (or the app) takes a whole strip
        self.matrix = matrix
        self.camera = camera
        self.strip = strip
        self.printer = printer
        self.sim_mode = sim_mode
        self.no_api = no_api
        self.state = State.IDLE
        self._trigger_event = threading.Event()
        self._booth_event = threading.Event()
        self._gesture = None                     # (name, progress 0..1, x, y, valid_until): an open palm / peace sign being held
        self._repeat_at = 0.0                    # photobooth repeat: when the next strip starts by itself (0 = not repeating)
        self._gesture_cd = 0.0                   # no new hand signal before this time
        self._stop = threading.Event()
        self.button = button_factory(self._on_button, self._on_long_press)
        self._latest_frame = None              # last raw camera frame (for AI)
        self._live_silhouette: Optional[Image.Image] = None  # PIL RGB, full canvas
        self._silhouette_lock = threading.Lock()
        self._silhouette_version = 0           # bumps when the silhouette changes
        self._capture_thread: Optional[threading.Thread] = None
        self._overlay_text: Optional[str] = None   # pushed from dashboard
        self._overlay_image: Optional[Image.Image] = None
        self._aura_event = threading.Event()
        self._pixel_event = threading.Event()
        self._sparkle = None                       # (cx, cy normalised, until_monotonic)
        self._sparkle_check = 0.0
        self._last_presence = time.monotonic()      # last time someone/something moved in front
        self._prev_small = None
        self._idle_min = (10, False, 0.0)           # (minutes, wake_on_motion, when read) cache of the settings
        self._info = {"names": [], "smiling": False, "faces": 0}   # who/what the last photo saw

    # ---- button ----

    def _on_button(self):
        if self.state == State.IDLE:
            (self._booth_event if self.booth_mode else self._trigger_event).set()
        else:
            print(f"[STATE] touch ignored in state {self.state.name}")

    def _on_long_press(self):
        if self.state == State.IDLE:
            print("[STATE] long press -> photobooth")
            self._booth_event.set()
        else:
            print(f"[STATE] long press ignored in state {self.state.name}")

    # ---- state ----

    def _set_state(self, s: State):
        self.state = s
        print(f"[STATE] {s.name}")
        if hasattr(self.matrix, "set_state_label"):
            self.matrix.set_state_label(s.name)

    # ---- continuous silhouette capture ----

    def _capture_loop(self):
        """Newest camera frame in, silhouette out, as fast as the CPU allows (capped at LIVE_SILHOUETTE_FPS).
        It waits for a new frame instead of sleeping a fixed interval, so the picture is never older than one
        frame; the slow face check for smiles runs in its own thread so it can't stall this one."""
        min_dt = 1.0 / max(1, config.LIVE_SILHOUETTE_FPS)
        wait = getattr(self.camera, "wait_frame", None)
        seq = 0
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                if wait:
                    seq, frame = wait(seq)
                    if frame is None:
                        continue
                else:
                    frame = self.camera.capture_frame()
                self._latest_frame = frame
                self._note_motion(frame)
                mask = self.camera.extract_silhouette(
                    frame, getattr(self.camera, "_background", None))
                img = silhouette_render.render_silhouette(mask)
                with self._silhouette_lock:
                    self._live_silhouette = img
                    self._silhouette_version += 1
                # tell the strip where the silhouette is so its hue band can
                # follow the person horizontally
                try:
                    import numpy as np
                    cols = np.where(mask.any(axis=0))[0]
                    if len(cols) > 0:
                        centroid_x = float(cols.mean()) / max(1, mask.shape[1])
                        self.strip.set_centroid(centroid_x)
                except Exception:
                    pass
            except Exception as e:
                print(f"[CAPTURE] {e}")
                time.sleep(0.5)
                continue
            time.sleep(max(0.0, min_dt - (time.monotonic() - t0)))

    def _smile_loop(self):
        """Face detection is slow (about a tenth of a second on the Pi): keep it off the picture's thread."""
        while not self._stop.wait(0.1):
            frame = self._latest_frame
            if frame is not None:
                self._look_for_smile(frame)

    HAND_HOLD_SEC = 1.3                          # how long a hand signal must be held
    HAND_NAMES = {"palm": "open palm", "peace": "peace sign"}

    def _gesture_loop(self):
        """A few times a second, while the mirror waits and someone is about: an open palm held up for a moment starts the
        photo sequence (in photobooth mode: the strip); a peace sign starts the photobooth strip. The wall draws a ring
        around the hand that fills as you hold it. Off with the "hand signal" switch in the app (mirror_settings)."""
        try:
            import hands
            import mirror_settings
            if not hands.available():
                print("[HAND] models missing (assets/models/get_models.sh): hand signals are off")
                return
        except Exception as e:
            print(f"[HAND] off: {e}")
            return
        name, since, miss, last_set = None, 0.0, 0, 0.0
        while not self._stop.wait(0.22):                  # ~3 looks a second on the Pi (each takes 0.12-0.19 s): the panels keep their cores
            now = time.monotonic()
            if self.state != State.IDLE or now < self._gesture_cd or not self._person_here() or getattr(self, "_art_on", False):
                name, self._gesture = None, None
                time.sleep(0.3)
                continue
            if now - last_set > 5.0:
                try:
                    on = mirror_settings.load().get("gesture", True)
                except Exception:
                    on = True
                last_set = now
            if not on:
                name, self._gesture = None, None
                time.sleep(0.5)
                continue
            frame = self._latest_frame
            if frame is None:
                continue
            try:
                hs = hands.find(frame)
            except Exception as e:
                print(f"[HAND] {e}")
                time.sleep(1.0)
                continue
            h = hs[0] if hs and hs[0].size > 0.05 else None
            g = h.gesture if h is not None else None
            now = time.monotonic()
            if g is not None and g == name:
                miss = 0
            elif g is not None:
                name, since, miss = g, now, 0                  # a different signal: start counting again
            else:
                miss += 1
                if miss >= 3:                                   # lost for a moment is fine, three samples is not
                    name, self._gesture = None, None
                    continue
            if name is None:
                continue
            cx, cy = h.centre if h is not None else (self._gesture[2] if self._gesture else 0.5, self._gesture[3] if self._gesture else 0.5)
            if config.SILHOUETTE_MIRROR:
                cx = 1.0 - cx
            prog = min(1.0, (now - since) / self.HAND_HOLD_SEC)
            self._gesture = (name, prog, float(cx), float(cy), now + 0.6)
            if prog >= 1.0:
                fired = name
                print(f"[HAND] {self.HAND_NAMES.get(fired, fired)} held: starting")
                self._gesture, name = None, None
                self._gesture_cd = time.monotonic() + 6.0
                self._last_presence = time.monotonic()
                if fired == "peace" or self.booth_mode:
                    self._booth_event.set()                     # the photobooth strip
                else:
                    self._trigger_event.set()                   # the photo sequence

    @staticmethod
    def _person_here() -> bool:
        """A person-sized silhouette is in front of the mirror (not just camera noise in an empty, dark hall)."""
        try:
            import vision
            a = vision.last["alpha"]
            return a is not None and float(a.mean()) > 0.04
        except Exception:
            return False

    def _gesture_ring(self, canvas):
        """The ring that fills while a hand signal is held, drawn around the hand."""
        gs = self._gesture
        if gs is None or time.monotonic() > gs[4]:
            return
        name, prog, cx, cy, _ = gs
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        x, y, r = cx * W, cy * H, 15
        col = (255, 200, 80) if name == "palm" else (255, 110, 190)
        d = ImageDraw.Draw(canvas)
        d.ellipse([x - r, y - r, x + r, y + r], outline=tuple(c // 4 for c in col), width=1)
        d.arc([x - r, y - r, x + r, y + r], -90, -90 + 360 * prog, fill=col, width=3)

    def _note_motion(self, frame):
        """Presence = the picture is changing (someone moves) - cheap 40x30 frame difference."""
        try:
            import cv2
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (40, 30)).astype("float32")
            if self._prev_small is not None and abs(small - self._prev_small).mean() > 2.5:
                self._last_presence = time.monotonic()
            self._prev_small = small
        except Exception:
            self._last_presence = time.monotonic()

    def _idle_art_wanted(self):
        """True when nobody has been in front of the mirror for the configured time."""
        mins, wake, read = self._idle_min
        now = time.monotonic()
        if now - read > 5.0:
            try:
                import mirror_settings
                st = mirror_settings.load()
                mins, wake = st["idle_art_minutes"], st["wake_on_motion"]
            except Exception:
                pass
            self._idle_min = (mins, wake, now)
        if mins <= 0:
            return False
        if getattr(self, "_art_on", False) and not wake:
            return True                  # art stays until a button/trigger (run() clears _art_on)
        return now - self._last_presence > mins * 60

    def _look_for_smile(self, frame):
        """About 3x a second: if the main face is smiling, sparkle around it for 2 seconds."""
        now = time.monotonic()
        if now - self._sparkle_check < 0.33 or self.state != State.IDLE:
            return
        self._sparkle_check = now
        try:
            import mirror_settings
            if not mirror_settings.load()["smile"]:
                return
            import smartcrop, moods
            rows = [r for r in smartcrop.find_face_rows(frame) if min(r[2], r[3]) >= 40]
            if not rows:
                return
            self._last_presence = now                    # a face is there
            r = max(rows, key=lambda r: r[2] * r[3])
            if moods.is_smiling(r):
                h, w = frame.shape[:2]
                cx = (r[0] + r[2] / 2) / w
                if config.SILHOUETTE_MIRROR:
                    cx = 1.0 - cx
                self._sparkle = (cx, (r[1] + r[3] / 2) / h, now + 2.0)
        except Exception as e:
            print(f"[SMILE] {e}")

    def _silhouette(self, dim: float = 1.0) -> Image.Image:
        with self._silhouette_lock:
            img = self._live_silhouette
        if img is None:
            return Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        if dim >= 0.999:
            return img.copy()
        return Image.eval(img, lambda v: int(v * dim))

    # ---- behaviours ----

    def _ai_call(self, frame):
        if self.no_api:
            time.sleep(1.0)
            return "The mirror dreams of electric sheep."
        import ai_client
        return self._shorten(ai_client.get_mirror_message(frame, self._hint()))

    @staticmethod
    def _shorten(text):
        """Safety net: strip quotes and cap the reply at AI_MAX_WORDS words."""
        if not text:
            return text
        words = text.strip().strip('"\u201c\u201d').split()
        if len(words) <= config.AI_MAX_WORDS:
            return " ".join(words)
        return " ".join(words[:config.AI_MAX_WORDS]).rstrip(",;:-") + "..."

    def _show(self, img, fps: int = 25):
        """One frame to the wall, paced by the panels' own refresh when it can: each frame is held for exactly N refreshes,
        so motion advances in equal steps (a sleep() timer drifts against the refresh, and that unevenness is flicker).
        25 fps (each frame held 4 refreshes at 100 Hz) is plenty: the camera delivers 15-20 pictures a second, and drawing
        faster only costs the CPU the panel driver needs."""
        refresh = float(config.MATRIX_REFRESH_LIMIT_HZ)
        ff = max(1, round(refresh / fps))
        try:
            drew = self.matrix.draw(img, frame_fraction=ff)
        except TypeError:                                   # the simulator has no frame_fraction
            drew = self.matrix.draw(img)
        if drew is not True:                                # nothing was sent (unchanged frame) or no vsync: pace by timer
            time.sleep(1.0 / fps)

    def _flash_white(self, ms: int):
        # short white flash on top of the silhouette as touch feedback
        white = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT), (255, 255, 255))
        self.matrix.draw(white)
        time.sleep(ms / 1000.0)

    def _fade_out(self, base: Image.Image, seconds: float):
        """Fade `base` (the text+silhouette composite) down to just the live
        silhouette — the mirror never goes fully black while someone is there.
        """
        steps = max(1, int(seconds * config.IDLE_ANIMATION_FPS))
        interval = 1.0 / config.IDLE_ANIMATION_FPS
        for i in range(steps, -1, -1):
            alpha = i / steps
            faded = Image.eval(base, lambda v: int(v * alpha))
            # composite over current live silhouette so it bleeds through
            live = self._silhouette()
            combined = Image.blend(live, faded, alpha)
            self._show(combined, 25)

    def _run_idle_until_trigger(self) -> str:
        """Block until short or long press. Returns 'short' or 'long'."""
        interval = 1.0 / config.IDLE_ANIMATION_FPS

        last_key = None
        while not self._stop.is_set():
            if self._booth_event.is_set():
                self._booth_event.clear()
                return "long"
            if self.booth_mode and self._repeat_at:
                now = time.monotonic()
                if now - self._last_presence > 30:
                    self._repeat_at = 0.0                      # everyone left: the booth stops by itself
                elif now >= self._repeat_at and now - self._last_presence < 10:
                    self._repeat_at = 0.0
                    print("[BOOTH] repeat: next strip")
                    return "long"
            if self._aura_event.is_set():
                self._aura_event.clear()
                return "aura"
            if self._pixel_event.is_set():
                self._pixel_event.clear()
                return "pixel"
            if self._trigger_event.is_set():
                self._trigger_event.clear()
                return "short"

            if self._idle_art_wanted():
                # nobody around for a while: show slow art instead of the (empty) silhouette
                if not getattr(self, "_art_on", False):
                    print("[IDLE] nobody around - showing art")
                    self._art_on = True
                from display import art
                self._show(art.frame_lava_coral(time.monotonic()))
                last_key = None
                continue
            if getattr(self, "_art_on", False):
                print("[IDLE] someone is back - silhouette")
                self._art_on = False

            # Recompose when something changed (a new silhouette or overlay), but draw every tick:
            # the wall glides towards each new camera frame instead of jumping to it 10 times a
            # second, which also evens out the camera's exposure pumping.
            sp = self._sparkle
            sparkling = sp is not None and time.monotonic() < sp[2]
            key = (self._silhouette_version, id(self._overlay_image),
                   self._overlay_text, int(time.monotonic() * 8) if sparkling else None,
                   int(time.monotonic() * 4) if self.booth_mode else None,
                   (self._gesture[0], int(self._gesture[1] * 24)) if self._gesture is not None else None)
            if key != last_key:
                last_key = key
                canvas = self._silhouette()
                if self._overlay_image is not None:
                    try:
                        canvas.paste(self._overlay_image, (0, 0))
                    except Exception:
                        pass
                elif self._overlay_text is not None:
                    try:
                        text_renderer.render_static_text(canvas, self._overlay_text)
                    except Exception:
                        pass
                if self.booth_mode and self._overlay_image is None and self._overlay_text is None:
                    self._booth_hint(canvas)
                self._gesture_ring(canvas)
                if sparkling:
                    try:
                        from display import sparkle
                        sparkle.draw(canvas, sp[0] * config.TOTAL_WIDTH, sp[1] * config.TOTAL_HEIGHT,
                                     time.monotonic())
                    except Exception:
                        pass
                self._target = np.asarray(canvas, np.float32)
            target = getattr(self, "_target", None)
            if target is not None:
                shown = getattr(self, "_shown", None)
                if shown is None or shown.shape != target.shape:
                    shown = target.copy()
                else:
                    # Ease towards the newest picture, per pixel: where it only wobbles a little (camera noise, the mains light's
                    # flicker) the wall barely follows, where something really moved it follows fast. That removes the shimmer
                    # without smearing a moving person.
                    diff = np.abs(target - shown).max(axis=2, keepdims=True)
                    shown += (target - shown) * (0.10 + 0.40 * np.clip(diff / 36.0, 0.0, 1.0))
                self._shown = shown
                self._show(Image.fromarray(np.clip(shown + 0.5, 0, 255).astype(np.uint8), "RGB"))
            else:
                time.sleep(interval)
        return "short"

    def _do_countdown(self, seconds: int = 3):
        """Show a 3-2-1 countdown centred on top of the live silhouette,
        with the strip breathing in sync."""
        self.strip.set_mode("countdown")
        interval = 1.0 / config.IDLE_ANIMATION_FPS
        for n in range(seconds, 0, -1):
            end = time.monotonic() + 1.0
            while time.monotonic() < end and not self._stop.is_set():
                canvas = self._silhouette(dim=config.SILHOUETTE_DIM_FACTOR)
                text_renderer.render_static_text(canvas, str(n),
                                                 colour=(255, 255, 255))
                self._show(canvas)

    def _grab_photo(self):
        """A full-width frame cut to portrait around the people (smart crop). Falls back to
        the last live frame (already a centred portrait crop) if the camera hiccups."""
        try:
            raw = self.camera.capture_frame(raw=True)
        except TypeError:                        # a camera without raw support
            return self.camera.capture_frame()
        import smartcrop
        rows = smartcrop.find_face_rows(raw)
        self._read_faces(raw, rows)
        faces = [(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[14])) for r in rows]
        frame, how = smartcrop.portrait_crop(raw, config.CAMERA_ASPECT,
                                             getattr(self.camera, "_background_raw", None), faces=faces)
        print(f"[CROP] portrait via {how}")
        return frame

    def _read_faces(self, raw, rows):
        """Who is in front of the mirror and are they smiling (names only for people who were
        enrolled in the app; never anything else is stored)."""
        info = {"names": [], "smiling": False, "faces": len(rows)}
        try:
            import mirror_settings
            st = mirror_settings.load()
            import moods
            big = [r for r in rows if min(r[2], r[3]) >= 40]
            if st["smile"] and big:
                info["smiling"] = moods.is_smiling(max(big, key=lambda r: r[2] * r[3]))
            if st["recognise"]:
                import faces
                if faces.available():
                    book = getattr(self, "_facebook", None) or faces.FaceBook()
                    self._facebook = book
                    if book.people():
                        seen = book.observe(raw, rows, learn=st["learn_faces"])
                        info["names"] = [n for _, n, _ in seen if n]
        except Exception as e:
            print(f"[FACES] skipped: {e}")
        self._info = info
        print(f"[FACES] {info}")

    def _hint(self):
        """Facts for the AI line, e.g. 'The person is called Fionn. They are smiling.'"""
        i, parts = self._info, []
        if i["names"]:
            parts.append("The person is called " + " and ".join(dict.fromkeys(i["names"])) + ".")
        if i["smiling"]:
            parts.append("They are smiling.")
        if i["faces"] > 1:
            parts.append(f"There are {i['faces']} people in the picture.")
        return " ".join(parts)

    def _do_trigger_capture(self):
        """Single-shot capture: countdown then grab the latest frame from the
        live thread — no LED flash. Booth mode has its own _capture_with_flash
        that does illuminate the subject."""
        self._set_state(State.TRIGGERED)
        self._do_countdown(3)
        self._set_state(State.CAPTURING)
        try:
            frame = self._grab_photo()
        except Exception as e:
            print(f"[CAPTURE] direct grab failed, falling back: {e}")
            frame = self._latest_frame
        if self.sim_mode:
            print("[SIM] Camera: captured frame (no flash)")
        return frame

    def _do_ai_wait(self, frame):
        self._set_state(State.AI_WAITING)
        self.strip.set_mode("thinking")
        if self.sim_mode:
            print("[SIM] API call started (threaded)")
        result = {"text": None}

        def worker():
            result["text"] = self._ai_call(frame)
        t = threading.Thread(target=worker, daemon=True)
        t.start()

        min_show_until = time.monotonic() + config.SILHOUETTE_DISPLAY_SEC
        hard_deadline = time.monotonic() + config.AI_TIMEOUT_SEC + 2.0
        interval = 1.0 / config.IDLE_ANIMATION_FPS
        import numpy as np
        # Single persistent generator so its internal t counter advances each
        # frame and the dots actually pulse. Composite with the live silhouette
        # via per-channel max so the background tracks the person.
        dots_gen = animations.thinking_dots()
        while t.is_alive() or time.monotonic() < min_show_until:
            base = self._silhouette()
            a = np.asarray(base, dtype=np.uint8)
            b = np.asarray(next(dots_gen), dtype=np.uint8)
            self._show(Image.fromarray(np.maximum(a, b), "RGB"), 25)
            if time.monotonic() > hard_deadline:
                break
        t.join(timeout=0.5)
        text = result["text"] or config.AI_FALLBACK_MESSAGE
        if self.sim_mode:
            print(f"[SIM] API response: {text!r}")
        return text

    def _do_display(self, text: str):
        self._set_state(State.DISPLAYING)
        self.strip.set_mode("displaying")
        if self.sim_mode:
            print("[SIM] Scrolling text...")

        interval = 1.0 / config.IDLE_ANIMATION_FPS
        # Text frames are transparent except for the outlined message; paste
        # them over the *current* (dimmed) live silhouette so the person stays
        # visible underneath while the outline keeps the text readable.
        gen = text_renderer.scroll_text_frames(text, rgba=True)
        for text_frame, finished in gen:
            canvas = self._silhouette(dim=config.SILHOUETTE_DIM_FACTOR)
            canvas.paste(text_frame, (0, 0), text_frame)
            self._show(canvas, 25)
            if finished:
                break
        # return the dim live silhouette for the fade-out to consume
        return self._silhouette(dim=config.SILHOUETTE_DIM_FACTOR)

    def _capture_with_flash(self):
        """Run the same illumination flash as a single-shot capture and
        return the captured frame. Sets strip back to 'thinking' after."""
        self.strip.set_mode("capture_flash")
        white = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT),
                          (255, 255, 255))
        self.matrix.draw(white)
        time.sleep(config.PHOTO_FLASH_PRE_MS / 1000.0)
        try:
            frame = self._grab_photo()
        except Exception as e:
            print(f"[CAPTURE] direct grab failed: {e}")
            frame = self._latest_frame
        time.sleep(config.PHOTO_FLASH_POST_MS / 1000.0)
        return frame

    def _booth_display_strip(self, strip_image):
        """Show the booth strip scaled to fit the matrix for BOOTH_DISPLAY_SEC.
        Aspect is preserved; height-bound to TOTAL_HEIGHT so the photos read."""
        import numpy as np
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        src = strip_image.convert("L")
        # height-bound scaling — photo strips are far taller than they are wide
        scale = H / src.height
        new_w = max(1, int(round(src.width * scale)))
        new_h = H
        if new_w > W:
            scale = W / src.width
            new_w = W
            new_h = int(round(src.height * scale))
        thumb = src.resize((new_w, new_h), Image.LANCZOS)
        # invert so dark print pixels show as lit panel pixels
        thumb = ImageOps.invert(thumb)
        # convert to RGB on a black canvas, centred
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        x = (W - new_w) // 2
        y = (H - new_h) // 2
        canvas.paste(thumb.convert("RGB"), (x, y))
        # subtle outline frame around the strip area
        d = ImageDraw.Draw(canvas)
        d.rectangle([x - 1, y - 1, x + new_w, y + new_h],
                    outline=(255, 200, 80))
        end = time.monotonic() + config.BOOTH_DISPLAY_SEC
        while time.monotonic() < end and not self._stop.is_set():
            self._show(canvas)

    def _booth_hint(self, canvas):
        """Photobooth mode, waiting: the title in gold and a pulsing 'tap' underneath."""
        d = ImageDraw.Draw(canvas)
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        f1, f2 = text_renderer._load_font(15), text_renderer._load_font(10)
        pulse = 0.55 + 0.45 * math.sin(time.monotonic() * 3.0)
        t1, t2 = "PHOTOBOOTH", "tap to start"
        if self._repeat_at:
            t2 = f"next strip in {max(0, int(self._repeat_at - time.monotonic()) + 1)}"
        for txt, f, y, col in ((t1, f1, 6, (255, 200, 80)), (t2, f2, H - 20, tuple(int(c * pulse) for c in (255, 235, 190)))):
            w = d.textlength(txt, font=f)
            d.text(((W - w) / 2, y), txt, font=f, fill=col, stroke_width=1, stroke_fill=(0, 0, 0))

    def _booth_display_frames(self, frames, seconds: float = 9.0, label="PHOTOBOOTH"):
        """Photobooth mode: the shots themselves, in colour, stacked in a gold-framed strip on the wall.
        Each photo flashes in one after the other."""
        import cv2
        from PIL import ImageEnhance
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        n, gap, margin, label_h = len(frames), 4, 6, (16 if label else 0)
        tw = W - 2 * margin
        th = (H - 2 * margin - gap * (n - 1) - label_h) // n
        tiles = []
        for f in frames:
            img = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
            t = ImageOps.fit(img, (tw, th), Image.LANCZOS, centering=(0.5, 0.35))
            t = ImageEnhance.Color(ImageEnhance.Contrast(t).enhance(1.15)).enhance(1.2)
            tiles.append(t)
        font = text_renderer._load_font(11)
        t0 = time.monotonic()
        while not self._stop.is_set():
            e = time.monotonic() - t0
            if e > seconds:
                break
            canvas = Image.new("RGB", (W, H), (6, 4, 10))
            d = ImageDraw.Draw(canvas)
            for i, t in enumerate(tiles):
                k = min(1.0, max(0.0, (e - i * 0.9) / 0.45))
                if k <= 0:
                    continue
                y = margin + i * (th + gap)
                shown = Image.blend(Image.new("RGB", t.size, (255, 255, 255)), t, k)
                canvas.paste(shown, (margin, y))
                d.rectangle([margin - 1, y - 1, margin + tw, y + th], outline=(255, 200, 80))
            if label and e > n * 0.9:
                w = d.textlength(label, font=font)
                d.text(((W - w) / 2, H - label_h - 1), label, font=font, fill=(255, 200, 80), stroke_width=1, stroke_fill=(0, 0, 0))
            self._show(canvas)

    def _show_booth_prompt(self, text: str, seconds: float):
        """Display a pose direction big on the matrix for `seconds`."""
        import textwrap
        from display.text_renderer import _FONT, _text_size
        from PIL import ImageDraw as _ImageDraw
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT

        # measure character width to pick a sensible wrap column
        probe = Image.new("RGB", (W, H))
        d = _ImageDraw.Draw(probe)
        char_w, _ = _text_size(d, "M")
        cols = max(8, W // max(1, char_w))
        lines = textwrap.wrap(text, width=cols) or [text]

        # Use a brighter silhouette than the normal text-overlay state — the
        # prompt is a call-to-action, not a quiet caption, and dim blue with
        # amber-on-top reads as "off". Bright base + white text is legible
        # even from across the hallway.
        canvas = self._silhouette(dim=0.7)
        d = _ImageDraw.Draw(canvas)
        line_h = _text_size(d, "Ag")[1] + 2
        total_h = line_h * len(lines)
        y0 = max(0, (H - total_h) // 2)
        for i, line in enumerate(lines):
            tw, _ = _text_size(d, line)
            d.text(((W - tw) // 2, y0 + i * line_h),
                   line, fill=(255, 255, 255), font=_FONT)

        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            self._show(canvas)

    def run_booth_cycle(self):
        self._overlay_text = None
        self._overlay_image = None
        from printer import render_booth_pil
        import ai_client
        try:
            import mirror_settings
            shots = mirror_settings.load().get("booth_shots", config.BOOTH_PHOTO_COUNT)
        except Exception:
            shots = config.BOOTH_PHOTO_COUNT
        try:
            self._set_state(State.BOOTH)
            self.strip.set_mode("countdown")
            self._flash_white(config.TRIGGER_FLASH_MS)

            # ask GPT for direction prompts (with fallback)
            prompts = ai_client.get_booth_prompts(shots)

            frames = []
            for i in range(shots):
                prompt_text = prompts[i] if i < len(prompts) else ""
                if prompt_text:
                    print(f"[BOOTH] prompt {i + 1}: {prompt_text}")
                    self._show_booth_prompt(prompt_text,
                                            config.BOOTH_PROMPT_HOLD_SEC)
                # short countdown per shot
                self._do_countdown(config.BOOTH_PER_PHOTO_COUNTDOWN)
                frame = self._capture_with_flash()
                if frame is not None:
                    frames.append(frame)
                print(f"[BOOTH] captured photo {i + 1}/{shots}")
                # tiny breath between shots so people can re-pose
                if i < shots - 1:
                    self.strip.set_mode("countdown")
                    time.sleep(config.BOOTH_INTER_PHOTO_PAUSE_MS / 1000.0)

            if not frames:
                print("[BOOTH] no frames captured; aborting cycle")
                return

            # Create a fresh Drive subfolder for this session so its three
            # photos live together, and the QR on the strip can link to it.
            qr_url = None
            booth_folder_id = None
            try:
                import cloud_uploader
                session = cloud_uploader.create_booth_session_folder()
                if session is not None:
                    booth_folder_id, qr_url = session
            except Exception as e:
                print(f"[BOOTH] folder create skip: {e}")

            # compose strip (now with optional QR), print, display, upload.
            strip_image = render_booth_pil(frames, label="PHOTOBOOTH",
                                           prompts=prompts[:len(frames)],
                                           qr_url=qr_url)
            try:
                self.printer.print_strip(strip_image)
            except Exception as e:
                print(f"[BOOTH] print failed: {e}")
            strip_stem = None
            try:
                import photo_store
                strip_stem = photo_store.save_strip(
                    strip_image, frames, prompts[:len(frames)])
            except Exception as e:
                print(f"[PHOTOS] skip: {e}")
            try:
                if booth_folder_id:
                    for i, f in enumerate(frames):
                        prompt = prompts[i] if i < len(prompts) else ""
                        desc = (f"Photobooth {i + 1}/{len(frames)}"
                                + (f" — {prompt}" if prompt else ""))
                        cloud_uploader.upload_photo_to_folder_async(
                            f, booth_folder_id, desc)
                else:
                    for i, f in enumerate(frames):
                        prompt = prompts[i] if i < len(prompts) else ""
                        desc = (f"Photobooth {i + 1}/{len(frames)}"
                                + (f" — {prompt}" if prompt else ""))
                        cloud_uploader.upload_photo_only_async(f, desc)
                cloud_uploader.upload_booth_async(strip_image, stem=strip_stem)
            except Exception as e:
                print(f"[BOOTH] drive upload skip: {e}")

            self.strip.set_mode("displaying")
            if self.booth_mode:
                self._booth_display_frames(frames)
            else:
                self._booth_display_strip(strip_image)

            self._set_state(State.FADE_OUT)
            self.strip.set_mode("fading")
            # fade from the strip view back to bare silhouette
            fade_base = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT),
                                  (0, 0, 0))
            self._fade_out(fade_base, config.FADE_OUT_SEC)
        except Exception as e:
            print(f"[BOOTH] cycle failed: {e}")
        finally:
            self._set_state(State.IDLE)
            self.strip.set_mode("idle")
            try:
                import mirror_settings
                self._repeat_at = time.monotonic() + 7.0 if (self.booth_mode and mirror_settings.load().get("booth_repeat")) else 0.0
            except Exception:
                self._repeat_at = 0.0

    def run_cycle(self):
        self._overlay_text = None
        self._overlay_image = None
        try:
            frame = self._do_trigger_capture()
            try:
                import mirror_settings
                comment = mirror_settings.load().get("comment", True)
            except Exception:
                comment = True
            text = self._do_ai_wait(frame) if comment else ""      # "no comment": just the photo
            stem = None
            try:
                import photo_store
                stem = photo_store.save_receipt(frame, text)
            except Exception as e:
                print(f"[PHOTOS] skip: {e}")
            try:
                import cloud_uploader
                cloud_uploader.upload_async(frame, text, stem=stem)
            except Exception as e:
                print(f"[DRIVE] skip: {e}")
            try:
                self.printer.print_receipt(frame, text)
            except Exception as e:
                print(f"[PRINTER] skip: {e}")
            if comment:
                held = self._do_display(text)
            else:
                self._set_state(State.DISPLAYING)
                self.strip.set_mode("displaying")
                self._booth_display_frames([frame], seconds=5.0, label=None)      # the photo itself, in colour
                held = self._silhouette(dim=config.SILHOUETTE_DIM_FACTOR)
            self._set_state(State.FADE_OUT)
            self.strip.set_mode("fading")
            self._fade_out(held, config.FADE_OUT_SEC)
        except Exception as e:
            print(f"[ERROR] cycle failed: {e}")
        finally:
            self._set_state(State.IDLE)
            self.strip.set_mode("idle")

    def _aura_glow(self, hexcol, name, seconds=7.0):
        """The wall breathes in the person's aura colour (a soft halo over the silhouette)."""
        import numpy as np
        col = np.array([int(hexcol[i:i + 2], 16) for i in (1, 3, 5)], np.float32)
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt((x - W / 2) ** 2 + (y - H / 2) ** 2) / (W / 2)
        interval = 1.0 / config.IDLE_ANIMATION_FPS
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds and not self._stop.is_set():
            u = (time.monotonic() - t0) / seconds
            grow = min(1.0, u * 3.0)                                   # halo swells in
            breathe = 0.75 + 0.25 * math.sin((time.monotonic() - t0) * 2.4)
            halo = np.clip(1.15 - r / (0.35 + 0.75 * grow), 0, 1) ** 1.5 * breathe
            fade = min(1.0, (1.0 - u) * 4.0)                           # and fades out at the end
            base = np.asarray(self._silhouette(dim=0.55), np.float32)
            out = np.clip(base * (1 - halo[..., None] * 0.5) + halo[..., None] * col * fade, 0, 255)
            canvas = Image.fromarray(out.astype(np.uint8), "RGB")
            if u > 0.12:
                text_renderer.render_static_text(canvas, name, colour=(255, 255, 255))
            self._show(canvas, 25)

    def run_pixel_cycle(self):
        """Pixel selfie: photo -> 48x48 sprite revealed row by row on the wall, sticker printed."""
        self._overlay_text = None
        self._overlay_image = None
        try:
            frame = self._do_trigger_capture()
            self._set_state(State.DISPLAYING)
            from display import pixel_art
            small = pixel_art.pixelate(frame)
            full = pixel_art.to_wall(small, min(config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
            canvas0 = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
            off = ((config.TOTAL_WIDTH - full.width) // 2, (config.TOTAL_HEIGHT - full.height) // 2)
            cell = full.height // small.height
            rows = small.height
            for r in range(rows + 1):                          # reveal like a scanner, row by row
                c = canvas0.copy()
                c.paste(full.crop((0, 0, full.width, r * cell)), off)
                self.matrix.draw(c)
                time.sleep(0.05)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 6.0 and not self._stop.is_set():
                c = canvas0.copy()
                c.paste(full, off)
                self.matrix.draw(c)
                time.sleep(0.2)
            try:
                import numpy as np, cv2
                stick = np.asarray(pixel_art.to_wall(small, 240).convert("RGB"))[:, :, ::-1]
                name = self._info["names"][0] if self._info.get("names") else "House Fortuna"
                self.printer.print_receipt(np.ascontiguousarray(stick), f"Pixel {name}")
            except Exception as e:
                print(f"[PRINTER] skip: {e}")
            self._set_state(State.FADE_OUT)
            self._fade_out(canvas0.copy(), config.FADE_OUT_SEC)
        except Exception as e:
            print(f"[ERROR] pixel cycle failed: {e}")
        finally:
            self._set_state(State.IDLE)
            self.strip.set_mode("idle")

    def run_aura_cycle(self):
        self._overlay_text = None
        self._overlay_image = None
        try:
            frame = self._do_trigger_capture()
            self._set_state(State.AI_WAITING)
            self.strip.set_mode("thinking")
            result = {}
            if self.no_api:
                result.update(colour="Rose Gold", hex="#E8A0A0", reading="Soft heart, fierce timing.")
            else:
                import ai_client
                t = threading.Thread(target=lambda: result.update(ai_client.get_aura(frame, self._hint())),
                                     daemon=True)
                t.start()
                import numpy as np
                dots = animations.thinking_dots()
                t0 = time.monotonic()
                while (t.is_alive() or time.monotonic() - t0 < 1.5) and time.monotonic() - t0 < config.AI_TIMEOUT_SEC + 3:
                    a = np.asarray(self._silhouette(), np.uint8)
                    b = np.asarray(next(dots), np.uint8)
                    self._show(Image.fromarray(np.maximum(a, b), "RGB"), 25)
            hexcol = result.get("hex", "#9B5DE5")
            name = result.get("colour", "Aura")
            reading = self._shorten(result.get("reading", "")) or config.AI_FALLBACK_MESSAGE
            print(f"[AURA] {name} {hexcol}: {reading}")
            try:
                import photo_store
                photo_store.save_receipt(frame, f"Aura: {name}. {reading}")
            except Exception as e:
                print(f"[PHOTOS] skip: {e}")
            try:
                self.printer.print_receipt(frame, f"Your aura is {name}. {reading}")
            except Exception as e:
                print(f"[PRINTER] skip: {e}")
            self._set_state(State.DISPLAYING)
            self._aura_glow(hexcol, name)
            held = self._do_display(reading)
            self._set_state(State.FADE_OUT)
            self.strip.set_mode("fading")
            self._fade_out(held, config.FADE_OUT_SEC)
        except Exception as e:
            print(f"[ERROR] aura cycle failed: {e}")
        finally:
            self._set_state(State.IDLE)
            self.strip.set_mode("idle")

    def run(self):
        if not self.no_api:
            try:
                import ai_client
                ai_client.warm_up()          # so the first photo is not slowed by a cold start
            except Exception:
                pass
        # capture initial background frame for absdiff silhouette extraction
        try:
            self.camera.get_background_frame()
        except Exception as e:
            print(f"[WARN] background capture failed: {e}")

        # start the continuous silhouette capture thread
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="silhouette-capture")
        self._capture_thread.start()
        threading.Thread(target=self._smile_loop, daemon=True, name="smile-watch").start()
        threading.Thread(target=self._gesture_loop, daemon=True, name="hand-signal").start()

        self._set_state(State.IDLE)
        self.strip.set_mode("idle")
        while not self._stop.is_set():
            kind = self._run_idle_until_trigger()
            if self._stop.is_set():
                break
            self._last_presence = time.monotonic()
            self._art_on = False
            if kind == "long" or (self.booth_mode and kind == "short"):
                self.run_booth_cycle()
            elif kind == "aura":
                self.run_aura_cycle()
            elif kind == "pixel":
                self.run_pixel_cycle()
            else:
                self.run_cycle()

    def shutdown(self):
        self._stop.set()
        self._trigger_event.set()
        self._aura_event.set()
        self._pixel_event.set()
        try:
            self.matrix.clear()
        except Exception:
            pass
        for obj in (self.button, self.camera, self.strip, self.printer, self.matrix):
            try:
                obj.shutdown()
            except Exception:
                pass


def build_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sim", action="store_true", help="Run in simulator mode (no Pi hardware)")
    p.add_argument("--camera", default="webcam", choices=["webcam", "static"],
                   help="Sim camera source")
    p.add_argument("--no-api", action="store_true", help="Skip API call (canned reply)")
    p.add_argument("--no-touch", action="store_true",
                   help="No touch sensor wired: trigger via dashboard/API or --auto")
    p.add_argument("--mock-camera", choices=["webcam", "static"], default=None,
                   help="Use the mock camera on hardware (no Pi camera attached)")
    p.add_argument("--camera-url", default=None, metavar="URL",
                   help="Use a network camera stream (e.g. laptop webcam via "
                        "panel_setup/stream_webcam.sh) instead of the Pi camera")
    p.add_argument("--auto", type=float, default=0, metavar="SEC",
                   help="Auto-trigger a cycle every SEC seconds while idle")
    p.add_argument("--auto-count", type=int, default=0, metavar="N",
                   help="With --auto, stop after N cycles (0 = keep going)")
    p.add_argument("--auto-booth-every", type=int, default=0, metavar="N",
                   help="With --auto, every Nth trigger is a photobooth run")
    p.add_argument("--booth", action="store_true",
                   help="Photobooth mode: a tap (or the app) takes a whole strip, shown in colour on the wall")
    p.add_argument("--no-mqtt", action="store_true", help="Disable MQTT bridge")
    return p


def main(argv=None):
    args = build_args().parse_args(argv)
    try:                                      # OpenCV spreading over every core starves the panel driver's refresh: that is flicker
        import cv2
        cv2.setNumThreads(2)
    except Exception:
        pass

    if args.sim:
        from simulator.led_simulator import LEDSimulator
        from simulator.camera_mock import CameraMock
        from simulator.button_mock import ButtonMock
        matrix = LEDSimulator()
        camera = CameraMock(mode=args.camera)
        import led_strip, printer as printer_mod
        strip = led_strip.create_strip(sim_matrix=matrix)
        printer = printer_mod.create_printer()
        mirror = MagicMirror(matrix, camera,
                             lambda short, long_: ButtonMock(short, long_),
                             strip=strip, printer=printer,
                             sim_mode=True, no_api=args.no_api, booth_mode=args.booth)

        api = MirrorAPI(mirror, port=5000)
        api.start()

        if not args.no_mqtt:
            bridge = MQTTBridge(mirror, host=config.MQTT_HOST, port=config.MQTT_PORT)
            bridge.start()

        worker = threading.Thread(target=mirror.run, daemon=True)
        worker.start()

        import pygame
        clock = pygame.time.Clock()
        running = True
        try:
            while running and worker.is_alive():
                for event in matrix.pump_events():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_q:
                            running = False
                        elif event.key == pygame.K_g:
                            matrix.toggle_grid()
                        else:
                            mirror.button.handle_event(event)
                    elif event.type == pygame.KEYUP:
                        # forward releases so the button can distinguish
                        # short vs long press
                        mirror.button.handle_event(event)
                matrix.tick()
                clock.tick(60)
        except KeyboardInterrupt:
            pass
        finally:
            mirror.shutdown()
            worker.join(timeout=2.0)
        return

    # real hardware
    from led_matrix import LedMatrix
    matrix = LedMatrix()
    if args.camera_url:
        from simulator.camera_mock import CameraMock
        camera = CameraMock(mode="stream", source=args.camera_url)
    elif args.mock_camera:
        from simulator.camera_mock import CameraMock
        camera = CameraMock(mode=args.mock_camera)
    else:
        from camera import Camera
        camera = Camera()
    if args.no_touch:
        button_factory = lambda short, long_: NullButton(short, long_)
    else:
        from gpio_button import GPIOButton
        button_factory = lambda short, long_: GPIOButton(short, long_)
    import led_strip, printer as printer_mod
    strip = led_strip.create_strip()
    printer = printer_mod.create_printer()
    mirror = MagicMirror(matrix, camera, button_factory,
                         strip=strip, printer=printer,
                         sim_mode=False, no_api=args.no_api, booth_mode=args.booth)
    if args.auto > 0:
        start_auto_trigger(mirror, args.auto, args.auto_booth_every, args.auto_count)

    api = MirrorAPI(mirror, port=5000)
    api.start()

    if not args.no_mqtt:
        bridge = MQTTBridge(mirror, host=config.MQTT_HOST, port=config.MQTT_PORT)
        bridge.start()

    def handle_signal(signum, _frame):
        print(f"[SIGNAL] {signum} received, shutting down")
        mirror.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    try:
        mirror.run()
    finally:
        mirror.shutdown()


if __name__ == "__main__":
    main()
