"""Capacitive touch sensor on GPIO with software debounce.

Default wiring assumes a TTP223-style module: VCC → 3V3, GND → GND,
SIG → BUTTON_PIN. Module outputs HIGH on touch (active-high) and is push-pull,
so no pull resistor is strictly needed — but a weak pull-down keeps the line
defined if the wire is ever disconnected.

Flip TOUCH_ACTIVE_HIGH / TOUCH_PULL in config.py if your module is jumpered
differently.
"""
import time
import threading
import config


class GPIOButton:
    def __init__(self, callback):
        import RPi.GPIO as GPIO
        self.GPIO = GPIO
        self.callback = callback
        self._last_press = 0.0
        self._stop = threading.Event()

        pull_map = {
            "up": GPIO.PUD_UP,
            "down": GPIO.PUD_DOWN,
            "off": GPIO.PUD_OFF,
        }
        pud = pull_map.get(config.TOUCH_PULL, GPIO.PUD_OFF)
        self._edge = GPIO.RISING if config.TOUCH_ACTIVE_HIGH else GPIO.FALLING

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.BUTTON_PIN, GPIO.IN, pull_up_down=pud)
        GPIO.add_event_detect(
            config.BUTTON_PIN, self._edge,
            callback=self._on_touch, bouncetime=config.BUTTON_DEBOUNCE_MS
        )

    def _on_touch(self, _channel):
        now = time.monotonic()
        if (now - self._last_press) * 1000 < config.BUTTON_DEBOUNCE_MS:
            return
        # confirm the line is still in the active state — guards against
        # single-sample noise spikes on the capacitive output.
        active = self.GPIO.HIGH if config.TOUCH_ACTIVE_HIGH else self.GPIO.LOW
        if self.GPIO.input(config.BUTTON_PIN) != active:
            return
        self._last_press = now
        try:
            self.callback()
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
