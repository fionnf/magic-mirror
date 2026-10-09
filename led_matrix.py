"""Real HUB75 LED matrix driver. Requires rpi-rgb-led-matrix Python bindings.

The panels form one long chain. The driver exposes a logical canvas of
TOTAL_WIDTH x TOTAL_HEIGHT and remaps it onto the flat chain strip
(CHAIN_LENGTH * PANEL_COLS wide, PANEL_ROWS tall) following
config.PANEL_CHAIN_ORDER, so any wiring layout works without pixel mappers.
"""
import json
import os
import threading
import numpy as np
from PIL import Image
import config


_CH = np.arange(3)
SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_setup", "now.jpg")
_snap_t = [0.0]


def write_snapshot(image):
    """What the wall shows, for the app's live preview: a small JPEG at most once a second."""
    import time
    now = time.monotonic()
    if now - _snap_t[0] < 1.0:
        return
    _snap_t[0] = now
    try:
        tmp = SNAPSHOT + ".tmp.jpg"
        image.convert("RGB").save(tmp, quality=85)
        os.replace(tmp, SNAPSHOT)
    except Exception:
        pass


class LedMatrix:
    def __init__(self):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        opts = RGBMatrixOptions()
        opts.rows = config.PANEL_ROWS
        opts.cols = config.PANEL_COLS
        opts.chain_length = config.CHAIN_LENGTH
        opts.parallel = config.PARALLEL
        opts.hardware_mapping = config.HARDWARE_MAPPING
        opts.pixel_mapper_config = config.PIXEL_MAPPER
        opts.gpio_slowdown = config.GPIO_SLOWDOWN
        if config.MATRIX_PANEL_TYPE:
            opts.panel_type = config.MATRIX_PANEL_TYPE
        opts.multiplexing = config.MATRIX_MULTIPLEXING
        opts.row_address_type = config.MATRIX_ROW_ADDRESS_TYPE
        opts.pwm_bits = config.MATRIX_PWM_BITS
        opts.pwm_dither_bits = config.MATRIX_PWM_DITHER_BITS
        opts.pwm_lsb_nanoseconds = config.MATRIX_PWM_LSB_NS
        opts.limit_refresh_rate_hz = config.MATRIX_REFRESH_LIMIT_HZ
        opts.show_refresh_rate = config.MATRIX_SHOW_REFRESH
        opts.brightness = config.MATRIX_BRIGHTNESS
        opts.drop_privileges = False
        self.matrix = RGBMatrix(options=opts)
        self.canvas = self.matrix.CreateFrameCanvas()
        self._lock = threading.Lock()
        self._brightness = config.MATRIX_BRIGHTNESS
        self.last_amps = 0.0
        self._prepare_layout()
        self._luts = None
        if config.MATRIX_APPLY_PANEL_GAINS:
            self._load_gains()

    def _load_gains(self):
        """Load per-panel colour gains if a calibration file exists."""
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            config.PANEL_GAINS_FILE)
        try:
            with open(path) as f:
                data = json.load(f)
            gains = np.array(data["gains"], dtype=np.float64)
            if gains.shape != (config.CHAIN_LENGTH, 3):
                print(f"[MATRIX] ignoring {config.PANEL_GAINS_FILE}: "
                      f"{gains.shape[0]} panels, chain is {config.CHAIN_LENGTH}")
                return
            if [list(p) for p in data.get("chain_order", [])] != \
                    [list(p) for p in config.PANEL_CHAIN_ORDER]:
                print("[MATRIX] warning: calibration was made with a different "
                      "PANEL_CHAIN_ORDER; re-run calibrate_colour.py")
            self.set_gains(gains)
            print(f"[MATRIX] colour calibration loaded ({config.PANEL_GAINS_FILE})")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[MATRIX] calibration load failed: {e}")

    def set_gains(self, gains) -> None:
        """gains: (chain, 3) array in [0, 1], or None to disable."""
        if gains is None or np.allclose(gains, 1.0):
            self._luts = None
        else:
            x = np.arange(256, dtype=np.float64)
            self._luts = np.clip(np.rint(x[None, None, :] * np.asarray(gains)[:, :, None]),
                                 0, 255).astype(np.uint8)       # (chain, 3, 256)
        self._prev = None                                       # force a redraw

    def _prepare_layout(self):
        """Precompute everything about the chain layout once (not per frame)."""
        order = config.PANEL_CHAIN_ORDER
        if len(order) != config.CHAIN_LENGTH:
            raise ValueError("PANEL_CHAIN_ORDER length != CHAIN_LENGTH")
        self._tile_idx = np.array([r * config.PANELS_WIDE + c for c, r in order])
        self._rots = {k: (config.PANEL_ROTATE.get(k, 0) % 360) // 90
                      for k in range(len(order))
                      if config.PANEL_ROTATE.get(k, 0) % 360}
        self._prev = None

    def _limit_power(self, arr: np.ndarray) -> np.ndarray:
        """Scale the frame down if its estimated current exceeds the budget.

        Estimate: each panel draws AMPS_PER_PANEL at full white, linear in mean
        channel value and in brightness. Mean is taken on a 1-in-16 subsample -
        plenty accurate for a budget check and ~16x cheaper.
        The scale is smoothed over time: it drops quickly when the frame needs it (safety)
        but recovers slowly, so content hovering around the budget never flickers.
        """
        mean = float(arr[::4, ::4].mean()) / 255.0
        amps = (mean * config.CHAIN_LENGTH * config.MATRIX_AMPS_PER_PANEL
                * self._brightness / 100.0)
        self.last_amps = amps
        want = min(1.0, config.MATRIX_MAX_AMPS * 0.97 / amps) if amps > 0 else 1.0
        cur = getattr(self, "_pscale", 1.0)
        if want < cur:
            cur = max(want, cur - 0.25)                      # down: within a few frames
        else:
            cur = min(want, cur + 0.008)                     # up: ~2 s to recover
        self._pscale = cur
        if cur >= 0.999:
            return arr
        return (arr.astype(np.float32) * cur).astype(np.uint8)

    def _remap(self, image: Image.Image) -> np.ndarray:
        """Logical canvas -> flat chain strip (rows, chain*cols, 3) uint8.

        Pure reshape/transpose/fancy-index: no per-panel Python loop on the
        hot path.
        """
        if not hasattr(self, "_tile_idx"):
            self._prepare_layout()
        pr, pc = config.PANEL_ROWS, config.PANEL_COLS
        arr = self._limit_power(np.asarray(image, dtype=np.uint8))
        tiles = (arr.reshape(config.PANELS_TALL, pr, config.PANELS_WIDE, pc, 3)
                 .transpose(0, 2, 1, 3, 4)
                 .reshape(-1, pr, pc, 3))
        sel = tiles[self._tile_idx]                      # (chain, pr, pc, 3)
        if self._luts is not None:
            for k in range(len(sel)):
                sel[k] = self._luts[k][_CH, sel[k]]
        for k, quarter_turns in self._rots.items():
            sel[k] = np.rot90(sel[k], k=-quarter_turns)
        return np.ascontiguousarray(
            sel.transpose(1, 0, 2, 3).reshape(pr, len(self._tile_idx) * pc, 3))

    def draw(self, image: Image.Image, frame_fraction: int = 1) -> bool:
        """Show a frame. frame_fraction=N holds it for exactly N panel refreshes
        (the library paces it on vsync - smooth motion with no timer drift).
        Returns False if the frame was identical and nothing was sent."""
        if image.size != (config.TOTAL_WIDTH, config.TOTAL_HEIGHT):
            image = image.resize((config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        if image.mode != "RGB":
            image = image.convert("RGB")
        write_snapshot(image)
        strip = self._remap(image)
        # Static content (idle text, held frames) costs nothing: skip the
        # upload when nothing changed — the panels keep showing the last frame.
        if self._prev is not None and np.array_equal(strip, self._prev):
            return False
        self._prev = strip
        with self._lock:
            self.canvas.SetImage(Image.fromarray(strip, "RGB"))
            self.canvas = self.matrix.SwapOnVSync(self.canvas, max(1, int(frame_fraction)))
        return True

    def clear(self) -> None:
        black = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT), (0, 0, 0))
        self.draw(black)

    def set_brightness(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self._brightness = value
        with self._lock:
            self.matrix.brightness = value

    def shutdown(self) -> None:
        self.clear()
