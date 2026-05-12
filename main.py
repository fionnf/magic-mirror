"""Magic Mirror — main state machine.

Runs either on real hardware (default) or with --sim using the simulator.
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
    SILHOUETTE = "SILHOUETTE"
    AI_WAITING = "AI_WAITING"
    DISPLAYING = "DISPLAYING"
    FADE_OUT = "FADE_OUT"


class MagicMirror:
    def __init__(self, matrix, camera, button_factory, sim_mode: bool, no_api: bool):
        self.matrix = matrix
        self.camera = camera
        self.sim_mode = sim_mode
        self.no_api = no_api
        self.state = State.IDLE
        self._trigger_event = threading.Event()
        self._stop = threading.Event()
        self.button = button_factory(self._on_button)
        self._latest_silhouette: Optional[Image.Image] = None
        self._latest_message: Optional[str] = None

    def _on_button(self):
        if self.state == State.IDLE:
            self._trigger_event.set()
        else:
            print(f"[STATE] button ignored in state {self.state.name}")

    def _set_state(self, s: State):
        self.state = s
        print(f"[STATE] {s.name}")
        if hasattr(self.matrix, "set_state_label"):
            self.matrix.set_state_label(s.name)

    def _ai_call(self, frame):
        if self.no_api:
            time.sleep(1.0)
            return "The mirror dreams of electric sheep."
        import ai_client
        return ai_client.get_mirror_message(frame)

    def _flash_white(self, ms: int):
        white = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT), (255, 255, 255))
        self.matrix.draw(white)
        time.sleep(ms / 1000.0)

    def _fade_out(self, base: Image.Image, seconds: float):
        steps = max(1, int(seconds * config.IDLE_ANIMATION_FPS))
        for i in range(steps, -1, -1):
            alpha = i / steps
            faded = Image.eval(base, lambda v: int(v * alpha))
            self.matrix.draw(faded)
            time.sleep(1.0 / config.IDLE_ANIMATION_FPS)

    def _run_idle_until_trigger(self):
        anim = animations.starfield()
        interval = 1.0 / config.IDLE_ANIMATION_FPS
        while not self._stop.is_set():
            if self._trigger_event.is_set():
                self._trigger_event.clear()
                return
            frame = next(anim)
            self.matrix.draw(frame)
            time.sleep(interval)

    def _do_trigger_capture(self):
        self._set_state(State.TRIGGERED)
        self._flash_white(config.TRIGGER_FLASH_MS)
        self._set_state(State.CAPTURING)
        if self.camera._background is None if hasattr(self.camera, "_background") else False:
            self.camera.get_background_frame()
        frame = self.camera.capture_frame()
        if self.sim_mode:
            print("[SIM] Camera: captured frame")
        return frame

    def _do_silhouette(self, frame):
        self._set_state(State.SILHOUETTE)
        mask = self.camera.extract_silhouette(frame, getattr(self.camera, "_background", None))
        sil_img = silhouette_render.render_silhouette(mask)
        self._latest_silhouette = sil_img
        self.matrix.draw(sil_img)
        return sil_img

    def _do_ai_wait(self, frame, sil_img):
        self._set_state(State.AI_WAITING)
        if self.sim_mode:
            print("[SIM] API call started (threaded)")
        result = {"text": None}

        def worker():
            result["text"] = self._ai_call(frame)
        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # Show silhouette + pulsing dots until response arrives or hard timeout
        dots = animations.thinking_dots(base=sil_img)
        deadline = time.monotonic() + config.AI_TIMEOUT_SEC + 2.0
        min_show_until = time.monotonic() + config.SILHOUETTE_DISPLAY_SEC
        interval = 1.0 / config.IDLE_ANIMATION_FPS
        while t.is_alive() or time.monotonic() < min_show_until:
            self.matrix.draw(next(dots))
            if time.monotonic() > deadline:
                break
            time.sleep(interval)
        t.join(timeout=0.5)
        text = result["text"] or config.AI_FALLBACK_MESSAGE
        if self.sim_mode:
            print(f"[SIM] API response: {text!r}")
        return text

    def _do_display(self, sil_img, text):
        self._set_state(State.DISPLAYING)
        dim = Image.eval(sil_img, lambda v: int(v * 0.3))
        if self.sim_mode:
            print("[SIM] Scrolling text...")
        text_renderer.scroll_text(self.matrix, text, background=dim)
        # hold final state with text centred
        held = dim.copy()
        text_renderer.render_static_text(held, text)
        end = time.monotonic() + config.MESSAGE_HOLD_SEC
        while time.monotonic() < end and not self._stop.is_set():
            self.matrix.draw(held)
            time.sleep(0.1)
        return held

    def run_cycle(self):
        try:
            frame = self._do_trigger_capture()
            sil = self._do_silhouette(frame)
            text = self._do_ai_wait(frame, sil)
            held = self._do_display(sil, text)
            self._set_state(State.FADE_OUT)
            self._fade_out(held, config.FADE_OUT_SEC)
        except Exception as e:
            print(f"[ERROR] cycle failed: {e}")
        finally:
            self._set_state(State.IDLE)

    def run(self):
        # capture initial background if camera supports it
        try:
            self.camera.get_background_frame()
        except Exception as e:
            print(f"[WARN] background capture failed: {e}")
        self._set_state(State.IDLE)
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
        for obj in (self.button, self.camera, self.matrix):
            try:
                obj.shutdown()
            except Exception:
                pass


def build_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sim", action="store_true", help="Run in simulator mode (no Pi hardware)")
    p.add_argument("--camera", default="webcam", choices=["webcam", "static"],
                   help="Sim camera source")
    p.add_argument("--no-api", action="store_true", help="Skip Claude API calls (canned reply)")
    return p


def main(argv=None):
    args = build_args().parse_args(argv)

    if args.sim:
        from simulator.led_simulator import LEDSimulator
        from simulator.camera_mock import CameraMock
        from simulator.button_mock import ButtonMock
        matrix = LEDSimulator()
        camera = CameraMock(mode=args.camera)
        button_factory = lambda cb: ButtonMock(cb)
        mirror = MagicMirror(matrix, camera, button_factory,
                             sim_mode=True, no_api=args.no_api)

        # run state machine in a background thread; main thread pumps pygame events
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
    mirror = MagicMirror(matrix, camera, lambda cb: GPIOButton(cb),
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
