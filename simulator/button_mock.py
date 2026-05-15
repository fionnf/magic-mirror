"""Keyboard SPACE/ENTER button mock with short / long-press detection.

KEYDOWN starts the press timer, KEYUP fires the short callback (if the
press was shorter than LONG_PRESS_MS). A background monitor fires the
long callback as soon as the held key crosses the threshold.
"""
import time
import threading
import config


class ButtonMock:
    def __init__(self, short_callback, long_callback=None):
        self.short_cb = short_callback
        self.long_cb = long_callback
        self._press_t = None
        self._long_fired = False
        self._last_release = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._monitor, daemon=True,
                         name="sim-button-monitor").start()

    def handle_event(self, event) -> bool:
        """Forward a pygame event. Returns True if it was a button event."""
        import pygame
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
            with self._lock:
                if self._press_t is None:
                    self._press_t = time.monotonic()
                    self._long_fired = False
            return True
        if event.type == pygame.KEYUP and event.key in (pygame.K_SPACE, pygame.K_RETURN):
            with self._lock:
                if self._press_t is None:
                    return True
                duration = (time.monotonic() - self._press_t) * 1000
                fired_long = self._long_fired
                self._press_t = None
                self._long_fired = False
            if not fired_long and duration < config.LONG_PRESS_MS:
                now = time.monotonic()
                if (now - self._last_release) * 1000 < config.BUTTON_DEBOUNCE_MS:
                    return True
                self._last_release = now
                print("[SIM] Button short press (SPACE)")
                self._fire(self.short_cb)
            return True
        return False

    def trigger(self, long: bool = False) -> None:
        """Programmatic trigger (used by --loop)."""
        cb = self.long_cb if long else self.short_cb
        label = "auto-long" if long else "auto-short"
        print(f"[SIM] Button pressed ({label})")
        self._fire(cb)

    def _monitor(self):
        while not self._stop.is_set():
            time.sleep(0.05)
            with self._lock:
                t0 = self._press_t
                already = self._long_fired
            if t0 is None or already or self.long_cb is None:
                continue
            if (time.monotonic() - t0) * 1000 >= config.LONG_PRESS_MS:
                with self._lock:
                    self._long_fired = True
                print("[SIM] Button LONG press (held 2s)")
                self._fire(self.long_cb)

    @staticmethod
    def _fire(cb):
        if cb is None:
            return
        try:
            cb()
        except Exception as e:
            print(f"[SIM] button callback error: {e}")

    def shutdown(self) -> None:
        self._stop.set()
