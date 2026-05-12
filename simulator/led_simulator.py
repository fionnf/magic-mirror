"""Pygame-backed LED matrix simulator. Drop-in replacement for LedMatrix.

macOS note: all SDL/NSWindow calls must happen on the main thread. So `draw()`,
`set_state_label()`, etc. are thread-safe stash-only operations; the actual
rendering happens in `tick()` which the main thread is responsible for calling.
"""
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
        self._caption_dirty = False
        self._grid_dirty = False
        self._latest_image = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        self._image_dirty = True
        # precompute pixel centres for fast render
        self._centres = [
            (x * self.scale + self.scale // 2, y * self.scale + self.scale // 2)
            for y in range(config.TOTAL_HEIGHT)
            for x in range(config.TOTAL_WIDTH)
        ]
        self._dot_radius = max(1, (self.scale - self.dot_gap) // 2)

    # ---- thread-safe stash methods (callable from any thread) ----

    def set_state_label(self, label: str) -> None:
        with self._lock:
            self._state_label = label
            self._caption_dirty = True

    def toggle_grid(self) -> None:
        with self._lock:
            self._show_grid = not self._show_grid
            self._image_dirty = True

    def draw(self, image: Image.Image) -> None:
        if image.size != (config.TOTAL_WIDTH, config.TOTAL_HEIGHT):
            image = image.resize((config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        if image.mode != "RGB":
            image = image.convert("RGB")
        with self._lock:
            self._latest_image = image
            self._image_dirty = True

    def clear(self) -> None:
        self.draw(Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT), (0, 0, 0)))

    def set_brightness(self, value: int) -> None:
        with self._lock:
            self._brightness = max(0, min(100, int(value)))
            self._image_dirty = True

    # ---- main-thread only ----

    def tick(self) -> None:
        """Render any pending updates. MUST be called from the main thread."""
        with self._lock:
            if self._caption_dirty:
                self.pygame.display.set_caption(
                    f"{config.SIM_TITLE} — {self._state_label}")
                self._caption_dirty = False
            if not self._image_dirty:
                return
            image = self._latest_image
            brightness = self._brightness / 100.0
            show_grid = self._show_grid
            self._image_dirty = False

        pg = self.pygame
        self.screen.fill((0, 0, 0))
        arr = np.asarray(image, dtype=np.uint8)
        r = self._dot_radius
        # Per-pixel circle is acceptable at 128x64; vectorising would need a
        # surfarray pass which loses the round-dot look.
        for y in range(config.TOTAL_HEIGHT):
            row = arr[y]
            base = y * config.TOTAL_WIDTH
            for x in range(config.TOTAL_WIDTH):
                col = row[x]
                if int(col[0]) + int(col[1]) + int(col[2]) < 6:
                    continue
                c = (int(col[0] * brightness),
                     int(col[1] * brightness),
                     int(col[2] * brightness))
                pg.draw.circle(self.screen, c, self._centres[base + x], r)
        if show_grid:
            grid_c = (40, 40, 40)
            pg.draw.line(self.screen, grid_c, (64 * self.scale, 0),
                         (64 * self.scale, self.win_h))
            pg.draw.line(self.screen, grid_c, (0, 32 * self.scale),
                         (self.win_w, 32 * self.scale))
        pg.display.flip()

    def pump_events(self):
        return self.pygame.event.get()

    def shutdown(self) -> None:
        try:
            self.pygame.quit()
        except Exception:
            pass
