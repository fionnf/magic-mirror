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
import threading
import enum
from typing import Optional
from PIL import Image

from dotenv import load_dotenv
load_dotenv()

import config
from display import animations, text_renderer, silhouette as silhouette_render


class State(enum.Enum):
    IDLE = "IDLE"
    TRIGGERED = "TRIGGERED"
    CAPTURING = "CAPTURING"
    AI_WAITING = "AI_WAITING"
    DISPLAYING = "DISPLAYING"
    FADE_OUT = "FADE_OUT"


class MagicMirror:
    def __init__(self, matrix, camera, button_factory, strip, printer,
                 sim_mode: bool, no_api: bool):
        self.matrix = matrix
        self.camera = camera
        self.strip = strip
        self.printer = printer
        self.sim_mode = sim_mode
        self.no_api = no_api
        self.state = State.IDLE
        self._trigger_event = threading.Event()
        self._stop = threading.Event()
        self.button = button_factory(self._on_button)
        self._latest_frame = None              # last raw camera frame (for AI)
        self._live_silhouette: Optional[Image.Image] = None  # PIL RGB, full canvas
        self._silhouette_lock = threading.Lock()
        self._capture_thread: Optional[threading.Thread] = None

    # ---- button ----

    def _on_button(self):
        if self.state == State.IDLE:
            self._trigger_event.set()
        else:
            print(f"[STATE] touch ignored in state {self.state.name}")

    # ---- state ----

    def _set_state(self, s: State):
        self.state = s
        print(f"[STATE] {s.name}")
        if hasattr(self.matrix, "set_state_label"):
            self.matrix.set_state_label(s.name)

    # ---- continuous silhouette capture ----

    def _capture_loop(self):
        interval = 1.0 / max(1, config.LIVE_SILHOUETTE_FPS)
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                frame = self.camera.capture_frame()
                self._latest_frame = frame
                mask = self.camera.extract_silhouette(
                    frame, getattr(self.camera, "_background", None))
                img = silhouette_render.render_silhouette(mask)
                with self._silhouette_lock:
                    self._live_silhouette = img
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
            dt = time.monotonic() - t0
            time.sleep(max(0.0, interval - dt))

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
        return ai_client.get_mirror_message(frame)

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
            self.matrix.draw(combined)
            time.sleep(interval)

    def _run_idle_until_trigger(self):
        interval = 1.0 / config.IDLE_ANIMATION_FPS
        while not self._stop.is_set():
            if self._trigger_event.is_set():
                self._trigger_event.clear()
                return
            self.matrix.draw(self._silhouette())
            time.sleep(interval)

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
                self.matrix.draw(canvas)
                time.sleep(interval)

    def _do_trigger_capture(self):
        self._set_state(State.TRIGGERED)
        self._flash_white(config.TRIGGER_FLASH_MS)
        self._do_countdown(3)
        self._set_state(State.CAPTURING)
        # strip goes pure white for the photo moment
        self.strip.set_mode("capture_flash")
        frame = self._latest_frame
        if frame is None:
            frame = self.camera.capture_frame()
        if self.sim_mode:
            print("[SIM] Camera: using latest live frame")
        # brief hold so the flash registers visually
        time.sleep(0.15)
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
        # pulsing thinking dots overlaid on the live silhouette
        dots_gen = animations.thinking_dots(base=self._silhouette())
        while t.is_alive() or time.monotonic() < min_show_until:
            # rebuild dot generator each frame against fresh silhouette so the
            # background tracks the person as they move
            base = self._silhouette()
            dots_gen = animations.thinking_dots(base=base)
            self.matrix.draw(next(dots_gen))
            if time.monotonic() > hard_deadline:
                break
            time.sleep(interval)
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
        import numpy as np
        # The scroll generator renders text over a (now-stale) silhouette
        # snapshot. We composite each produced frame with the *current* live
        # silhouette via per-channel max — text stays bright, the live
        # silhouette tracks the person underneath. Scroll the message twice.
        for _pass in range(2):
            gen = text_renderer.scroll_text_frames(
                text, background=self._silhouette(dim=config.SILHOUETTE_DIM_FACTOR))
            for text_frame, finished in gen:
                live_dim = self._silhouette(dim=config.SILHOUETTE_DIM_FACTOR)
                a = np.asarray(text_frame, dtype=np.uint8)
                b = np.asarray(live_dim, dtype=np.uint8)
                self.matrix.draw(Image.fromarray(np.maximum(a, b), "RGB"))
                if finished:
                    break
                time.sleep(interval)
            if self._stop.is_set():
                break
        # return the dim live silhouette for the fade-out to consume
        return self._silhouette(dim=config.SILHOUETTE_DIM_FACTOR)

    def run_cycle(self):
        try:
            frame = self._do_trigger_capture()
            text = self._do_ai_wait(frame)
            try:
                import cloud_uploader
                cloud_uploader.upload_async(frame, text)
            except Exception as e:
                print(f"[DRIVE] skip: {e}")
            try:
                self.printer.print_receipt(frame, text)
            except Exception as e:
                print(f"[PRINTER] skip: {e}")
            held = self._do_display(text)
            self._set_state(State.FADE_OUT)
            self.strip.set_mode("fading")
            self._fade_out(held, config.FADE_OUT_SEC)
        except Exception as e:
            print(f"[ERROR] cycle failed: {e}")
        finally:
            self._set_state(State.IDLE)
            self.strip.set_mode("idle")

    def run(self):
        # capture initial background frame for absdiff silhouette extraction
        try:
            self.camera.get_background_frame()
        except Exception as e:
            print(f"[WARN] background capture failed: {e}")

        # start the continuous silhouette capture thread
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="silhouette-capture")
        self._capture_thread.start()

        self._set_state(State.IDLE)
        self.strip.set_mode("idle")
        while not self._stop.is_set():
            self._run_idle_until_trigger()
            if self._stop.is_set():
                break
            self.run_cycle()

    def shutdown(self):
        self._stop.set()
        self._trigger_event.set()
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
    return p


def main(argv=None):
    args = build_args().parse_args(argv)

    if args.sim:
        from simulator.led_simulator import LEDSimulator
        from simulator.camera_mock import CameraMock
        from simulator.button_mock import ButtonMock
        matrix = LEDSimulator()
        camera = CameraMock(mode=args.camera)
        import led_strip, printer as printer_mod
        strip = led_strip.create_strip(sim_matrix=matrix)
        printer = printer_mod.create_printer()
        mirror = MagicMirror(matrix, camera, lambda cb: ButtonMock(cb),
                             strip=strip, printer=printer,
                             sim_mode=True, no_api=args.no_api)

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
    from camera import Camera
    from gpio_button import GPIOButton
    matrix = LedMatrix()
    camera = Camera()
    import led_strip, printer as printer_mod
    strip = led_strip.create_strip()
    printer = printer_mod.create_printer()
    mirror = MagicMirror(matrix, camera, lambda cb: GPIOButton(cb),
                         strip=strip, printer=printer,
                         sim_mode=False, no_api=args.no_api)

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
