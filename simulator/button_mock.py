"""Keyboard SPACE/ENTER button mock. Event-driven via pygame events."""
import time
import config


class ButtonMock:
    def __init__(self, callback):
        self.callback = callback
        self._last_press = 0.0

    def handle_event(self, event) -> bool:
        """Forward a pygame event. Returns True if event was a button press."""
        import pygame
        if event.type != pygame.KEYDOWN:
            return False
        if event.key not in (pygame.K_SPACE, pygame.K_RETURN):
            return False
        now = time.monotonic()
        if (now - self._last_press) * 1000 < config.BUTTON_DEBOUNCE_MS:
            return False
        self._last_press = now
        print("[SIM] Button pressed (SPACE)")
        try:
            self.callback()
        except Exception as e:
            print(f"[SIM] button callback error: {e}")
        return True

    def trigger(self) -> None:
        """Programmatic trigger (used by --loop)."""
        now = time.monotonic()
        if (now - self._last_press) * 1000 < config.BUTTON_DEBOUNCE_MS:
            return
        self._last_press = now
        print("[SIM] Button pressed (auto)")
        try:
            self.callback()
        except Exception as e:
            print(f"[SIM] button callback error: {e}")

    def shutdown(self) -> None:
        pass
