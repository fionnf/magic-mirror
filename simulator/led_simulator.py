"""Pygame-backed LED matrix simulator with optional strip overlay border.

macOS note: all SDL/NSWindow calls must happen on the main thread. So `draw()`,
`set_state_label()`, `set_strip_pixels()` etc. are thread-safe stash-only
operations; the actual rendering happens in `tick()` which the main thread
is responsible for calling.

The window layout is:

  +----------------------------------+
  |  strip border (SIM_STRIP_BORDER) |  <- SK6812 strip preview, wraps the
  |  +----------------------------+  |     matrix area clockwise from top-left
  |  |                            |  |
  |  |     LED matrix (128x192)   |  |
  |  |                            |  |
  |  +----------------------------+  |
  |          strip border            |
  +----------------------------------+
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
        self.border = config.SIM_STRIP_BORDER_PX
        self.matrix_w = config.TOTAL_WIDTH * self.scale
        self.matrix_h = config.TOTAL_HEIGHT * self.scale
        self.win_w = self.matrix_w + 2 * self.border
        self.win_h = self.matrix_h + 2 * self.border
        self.screen = pygame.display.set_mode((self.win_w, self.win_h))
        pygame.display.set_caption(config.SIM_TITLE)
        self._lock = threading.Lock()
        self._brightness = 80
        self._show_grid = False
        self._state_label = "IDLE"
        self._caption_dirty = False
        self._latest_image = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        self._image_dirty = True
        # strip pixels: list of (R,G,B,W) tuples
        self._strip_pixels = [(0, 0, 0, 0)] * config.LED_STRIP_COUNT
        self._strip_dirty = True

        # precompute matrix dot centres
        self._centres = [
            (self.border + x * self.scale + self.scale // 2,
             self.border + y * self.scale + self.scale // 2)
            for y in range(config.TOTAL_HEIGHT)
            for x in range(config.TOTAL_WIDTH)
        ]
        self._dot_radius = max(1, (self.scale - self.dot_gap) // 2)

        # precompute strip pixel positions on the perimeter, clockwise from
        # top-left. The strip wraps top → right → bottom → left.
        self._strip_positions = self._compute_strip_positions()

    def _compute_strip_positions(self):
        """Return [(cx, cy), ...] for each LED on the perimeter."""
        n = config.LED_STRIP_COUNT
        # perimeter in window pixels: top + right + bottom + left
        top_len = self.matrix_w
        side_len = self.matrix_h
        perim = 2 * top_len + 2 * side_len
        positions = []
        cx0 = self.border
        cy0 = self.border
        b_mid = self.border // 2
        for i in range(n):
            f = (i / n) * perim  # distance along perimeter
            if f < top_len:
                # top edge, left -> right
                x = cx0 + f
                y = cy0 - b_mid
            elif f < top_len + side_len:
                # right edge, top -> bottom
                x = cx0 + self.matrix_w + b_mid
                y = cy0 + (f - top_len)
            elif f < 2 * top_len + side_len:
                # bottom edge, right -> left
                x = cx0 + self.matrix_w - (f - top_len - side_len)
                y = cy0 + self.matrix_h + b_mid
            else:
                # left edge, bottom -> top
                x = cx0 - b_mid
                y = cy0 + self.matrix_h - (f - 2 * top_len - side_len)
            positions.append((int(x), int(y)))
        return positions

    # ---- thread-safe stash methods ----

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

    def set_strip_pixels(self, pixels) -> None:
        with self._lock:
            self._strip_pixels = list(pixels)
            self._strip_dirty = True

    # ---- main-thread only ----

    def tick(self) -> None:
        with self._lock:
            if self._caption_dirty:
                self.pygame.display.set_caption(
                    f"{config.SIM_TITLE} — {self._state_label}")
                self._caption_dirty = False
            if not (self._image_dirty or self._strip_dirty):
                return
            image = self._latest_image
            brightness = self._brightness / 100.0
            show_grid = self._show_grid
            strip_pixels = list(self._strip_pixels)
            self._image_dirty = False
            self._strip_dirty = False

        pg = self.pygame
        self.screen.fill((0, 0, 0))

        # ---- strip border ----
        # Render each LED as a soft circle. SK6812 RGBW: blend W into a warm
        # off-white so it visibly contributes to the dot.
        for (cx, cy), (r, g, b, w) in zip(self._strip_positions, strip_pixels):
            wr = int(w * 1.0)
            wg = int(w * 0.85)
            wb = int(w * 0.55)
            cr = min(255, r + wr)
            cg = min(255, g + wg)
            cb = min(255, b + wb)
            if cr + cg + cb < 6:
                continue
            pg.draw.circle(self.screen, (cr, cg, cb), (cx, cy),
                           max(2, self.border // 3))

        # ---- matrix dots ----
        arr = np.asarray(image, dtype=np.uint8)
        r_dot = self._dot_radius
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
                pg.draw.circle(self.screen, c, self._centres[base + x], r_dot)
        if show_grid:
            grid_c = (40, 40, 40)
            # grid lines at panel boundaries (every 64 px logical)
            for gx in range(64, config.TOTAL_WIDTH, 64):
                pg.draw.line(self.screen, grid_c,
                             (self.border + gx * self.scale, self.border),
                             (self.border + gx * self.scale, self.border + self.matrix_h))
            for gy in range(64, config.TOTAL_HEIGHT, 64):
                pg.draw.line(self.screen, grid_c,
                             (self.border, self.border + gy * self.scale),
                             (self.border + self.matrix_w, self.border + gy * self.scale))
        pg.display.flip()

    def pump_events(self):
        return self.pygame.event.get()

    def shutdown(self) -> None:
        try:
            self.pygame.quit()
        except Exception:
            pass
