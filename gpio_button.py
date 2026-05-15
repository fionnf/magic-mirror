"""Capacitive touch sensor on GPIO with short / long-press detection.

Two callbacks:
    short_callback(): fires on release if held < LONG_PRESS_MS
    long_callback() : fires as soon as the touch is held for LONG_PRESS_MS

If `long_callback` is None, the button behaves like a regular momentary
touch — fires once on press (same UX as before).
"""
import time
import threading
import config


class GPIOButton:
    def __init__(self, short_callback, long_callback=None):
        import RPi.GPIO as GPIO
        self.GPIO = GPIO
        self.short_cb = short_callback
        self.long_cb = long_callback

        pull_map = {"up": GPIO.PUD_UP, "down": GPIO.PUD_DOWN, "off": GPIO.PUD_OFF}
        pud = pull_map.get(config.TOUCH_PULL, GPIO.PUD_OFF)

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.BUTTON_PIN, GPIO.IN, pull_up_down=pud)
        # Listen for both edges so we can time the press duration.
        GPIO.add_event_detect(
            config.BUTTON_PIN, GPIO.BOTH,
            callback=self._on_edge, bouncetime=50)

        self._press_t = None      # monotonic time of last press-down, or None
        self._long_fired = False  # set when long_cb has already fired this press
        self._last_release = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        # Monitor thread: fires long_cb the moment a held press crosses the
        # threshold, without waiting for the user to release.
        self._monitor = threading.Thread(target=self._monitor_loop, daemon=True,
                                         name="button-monitor")
        self._monitor.start()

    def _is_pressed(self) -> bool:
        active = self.GPIO.HIGH if config.TOUCH_ACTIVE_HIGH else self.GPIO.LOW
        return self.GPIO.input(config.BUTTON_PIN) == active

    def _on_edge(self, _channel):
        # The GPIO library doesn't tell us which edge fired; check the
        # current pin state to decide.
        if self._is_pressed():
            with self._lock:
                self._press_t = time.monotonic()
                self._long_fired = False
            return
        # release
        with self._lock:
            if self._press_t is None:
                return
            duration = (time.monotonic() - self._press_t) * 1000
            fired_long = self._long_fired
            self._press_t = None
            self._long_fired = False
        if not fired_long and duration < config.LONG_PRESS_MS:
            # short press — debounce against multiple bounces
            now = time.monotonic()
            if (now - self._last_release) * 1000 < config.BUTTON_DEBOUNCE_MS:
                return
            self._last_release = now
            self._fire(self.short_cb)

    def _monitor_loop(self):
        while not self._stop.is_set():
            time.sleep(0.05)
            with self._lock:
                t0 = self._press_t
                already = self._long_fired
            if t0 is None or already or self.long_cb is None:
                continue
            if (time.monotonic() - t0) * 1000 >= config.LONG_PRESS_MS:
                # confirm still pressed (guards against missed release edge)
                if not self._is_pressed():
                    with self._lock:
                        self._press_t = None
                    continue
                with self._lock:
                    self._long_fired = True
                self._fire(self.long_cb)

    @staticmethod
    def _fire(cb):
        if cb is None:
            return
        try:
            cb()
        except Exception as e:
            print(f"[TOUCH] callback error: {e}")

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self.GPIO.remove_event_detect(config.BUTTON_PIN)
        except Exception:
            pass
        try:
            self.GPIO.cleanup(config.BUTTON_PIN)
        except Exception:
            pass
