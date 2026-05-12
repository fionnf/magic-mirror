"""Pygame-backed LED matrix simulator. Drop-in replacement for LedMatrix."""
import threading
import numpy as np
from PIL import Image
import config


class LEDSimulator:
    def __init__(self):
        import pygame
        pygame.init()
        self.pygame = pygame
        self.scale = config.SIM_SCALE
        self.dot_gap = 1
        self.win_w = config.TOTAL_WIDTH * self.scale
        self.win_h = config.TOTAL_HEIGHT * self.scale
        self.screen = pygame.display.set_mode((self.win_w, self.win_h))
        pygame.display.set_caption(config.SIM_TITLE)
        self._lock = threading.Lock()
        self._brightness = 80
        self._show_grid = False
        self._state_label = "IDLE"
        self._latest_image = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))

    def set_state_label(self, label: str) -> None:
        self._state_label = label
        self.pygame.display.set_caption(f"{config.SIM_TITLE} — {label}")

    def toggle_grid(self) -> None:
        self._show_grid = not self._show_grid

    def draw(self, image: Image.Image) -> None:
        if image.size != (config.TOTAL_WIDTH, config.TOTAL_HEIGHT):
            image = image.resize((config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        if image.mode != "RGB":
            image = image.convert("RGB")
        with self._lock:
            self._latest_image = image
            self._render()

    def _render(self) -> None:
        pg = self.pygame
        self.screen.fill((0, 0, 0))
        arr = np.asarray(self._latest_image, dtype=np.uint8)
        brightness = self._brightness / 100.0
        r = max(1, (self.scale - self.dot_gap) // 2)
        for y in range(config.TOTAL_HEIGHT):
            for x in range(config.TOTAL_WIDTH):
                col = arr[y, x]
                if int(col[0]) + int(col[1]) + int(col[2]) < 6:
                    continue
                c = (int(col[0] * brightness), int(col[1] * brightness), int(col[2] * brightness))
                cx = x * self.scale + self.scale // 2
                cy = y * self.scale + self.scale // 2
                pg.draw.circle(self.screen, c, (cx, cy), r)
        if self._show_grid:
            grid_c = (40, 40, 40)
            for gx in (64,):
                pg.draw.line(self.screen, grid_c, (gx * self.scale, 0),
                             (gx * self.scale, self.win_h))
            for gy in (32,):
                pg.draw.line(self.screen, grid_c, (0, gy * self.scale),
                             (self.win_w, gy * self.scale))
        pg.display.flip()

    def clear(self) -> None:
        self.draw(Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT), (0, 0, 0)))

    def set_brightness(self, value: int) -> None:
        self._brightness = max(0, min(100, int(value)))
        with self._lock:
            self._render()

    def pump_events(self):
        """Returns list of pygame events for the caller to dispatch."""
        return self.pygame.event.get()

    def shutdown(self) -> None:
        try:
            self.pygame.quit()
        except Exception:
            pass
