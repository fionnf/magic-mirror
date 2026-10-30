"""Real HUB75 LED matrix driver. Requires rpi-rgb-led-matrix Python bindings.

The panels form one long chain. The driver exposes a logical canvas of
TOTAL_WIDTH x TOTAL_HEIGHT and remaps it onto the flat chain strip
(CHAIN_LENGTH * PANEL_COLS wide, PANEL_ROWS tall) following
config.PANEL_CHAIN_ORDER, so any wiring layout works without pixel mappers.
"""
import json
import os
import threading
import time
import numpy as np
from PIL import Image
import config


_CH = np.arange(3)
SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_setup", "now.png")
_snap_t = [0.0]
_snap_q = []


def led_lut(hw, bits):
    """What the eye gets from each channel value 0..255, as an sRGB value for a screen: the panel
    library's own mapping (rpi-rgb-led-matrix lib/framebuffer.cc) - the value read as CIE lightness
    scaled by the hardware brightness hw (1..100), turned into light in 11 bit planes, of which only the
    top `bits` are shown (the lower planes are dropped, so dark values fall to black and fades step).
    Relative to the wall's own white at this brightness: on a phone the colours and tones are true, the
    overall light level is the screen's."""
    c = np.arange(256, dtype=np.float64)
    v = c * hw / 255.0
    y11 = np.rint(2047.0 * np.where(v <= 8.0, v / 902.3, ((v + 16.0) / 116.0) ** 3))
    step = 1 << (11 - int(bits))
    shown = np.floor(y11 / step) * step
    y = shown / max(shown[255], 1.0)
    srgb = np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(y, 1 / 2.4) - 0.055)
    return np.clip(np.rint(srgb * 255.0), 0, 255).astype(np.uint8)


def _snap_writer():
    import json
    import time
    luts = {}
    while True:
        time.sleep(0.2)
        if not _snap_q:
            continue
        image, led = _snap_q.pop()
        _snap_q.clear()
        try:
            a = np.asarray(image, np.uint8)
            if led is not None:                               # as the panels light it (see led_lut)
                key = (led["hw"], led["bits"])
                if key not in luts:
                    luts[key] = led_lut(*key)
                a = luts[key][a]
            tmp = SNAPSHOT + ".tmp.png"
            Image.fromarray(a, "RGB").save(tmp, compress_level=1)
            os.replace(tmp, SNAPSHOT)
            info = os.path.splitext(SNAPSHOT)[0] + ".json"
            with open(info + ".tmp", "w") as fh:
                json.dump(led or {}, fh)
            os.replace(info + ".tmp", info)
        except Exception:
            pass


def write_snapshot(image, led=None):
    """What the wall shows, for the app's live preview, at most once a second: the exact pixels
    (TOTAL_WIDTH x TOTAL_HEIGHT, lossless PNG) after the wall's own colour work (shadow lift, power
    limit), then lit as the panels light them when led = {"hw", "bits", "brightness"} is given (see
    led_lut; now.json next to it carries those numbers for the app). Encoded and written on a side
    thread, so the frame loop never waits on it (a late frame is a visible hitch)."""
    import threading
    import time
    now = time.monotonic()
    if now - _snap_t[0] < 1.0:
        return
    if _snap_t[0] == 0.0:
        threading.Thread(target=_snap_writer, daemon=True).start()
    _snap_t[0] = now
    _snap_q.append((np.array(image, np.uint8, copy=True), led))


class LedMatrix:
    def __init__(self):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        opts = RGBMatrixOptions()
        opts.rows = config.PANEL_ROWS
        opts.cols = config.PANEL_COLS
        opts.chain_length = getattr(config, "CHAIN_PER_PORT", config.CHAIN_LENGTH)
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
        opts.brightness = self._hw_brightness(config.MATRIX_BRIGHTNESS)
        opts.drop_privileges = False
        self.matrix = RGBMatrix(options=opts)
        self.canvas = self.matrix.CreateFrameCanvas()
        self._lock = threading.Lock()
        self._brightness = config.MATRIX_BRIGHTNESS
        self.last_amps = 0.0
        self._bits, self._bits_t = config.MATRIX_PWM_BITS, time.monotonic()
        self._lvl, self._lvl_t = 1.0, time.monotonic()                 # start "bright": the start-up animation stays on the safe bits
        LedMatrix._bits_now = config.MATRIX_PWM_BITS
        self.send_s = 0.0
        self._prepare_layout()
        self._luts = None
        if config.MATRIX_APPLY_PANEL_GAINS:
            self._load_gains()

    @staticmethod
    def _hw_brightness(value) -> int:
        """The panel's duty grows with the refresh rate (less idle time between scans), so the app's
        brightness % is scaled back to what it looked like at BRIGHTNESS_REF_HZ."""
        scale = min(1.0, config.BRIGHTNESS_REF_HZ / float(LedMatrix._hz_for(getattr(LedMatrix, "_bits_now", config.MATRIX_PWM_BITS))))
        return max(1, int(round(value * scale))) if value > 0 else 0

    @staticmethod
    def _hz_for(bits) -> float:
        """The refresh the panels run at with this many PWM bits (measured under real art)."""
        return float(min(config.MATRIX_REFRESH_LIMIT_HZ, config.PWM_BITS_HZ.get(bits, config.BRIGHTNESS_REF_HZ)))

    @staticmethod
    def _depth_for(level: float) -> int:
        """PWM bits for a picture level: the darker the picture, the more colour steps (flicker hides in the dark)."""
        for below, bits in config.DEPTH_STEPS:               # darkest first
            if level < below:
                return bits
        return config.MATRIX_PWM_BITS

    def _adapt_bits(self, mean: float, bright_frac: float = 0.0) -> None:
        """More colour steps for dark art, a faster refresh for bright art.
        It follows the picture's 8-second average (never single frames), needs a clear margin past each
        threshold, waits ~25 s before going deeper, and a bright moment sends it straight back to
        MATRIX_PWM_BITS. So it never hops back and forth."""
        if not config.DEPTH_STEPS or os.environ.get("WALL_FIXED_DEPTH") == "1":
            return                       # points of light on black (the live maps): the fastest refresh, always
        if getattr(config, "FORCE_FAST_REFRESH", False):
            # set while the album cover is on the wall (a dim picture that would otherwise drop to 7-8 bits and a
            # slower, flickery refresh): back to the fast setting now, and stay there
            if self._bits != config.MATRIX_PWM_BITS:
                self._bits, self._bits_t = config.MATRIX_PWM_BITS, time.monotonic()
                LedMatrix._bits_now = self._bits
                with self._lock:
                    self.matrix.pwmBits = self._bits
                    self.matrix.brightness = self._hw_brightness(self._brightness)
            return
        eff = max(mean, 0.7 * bright_frac) * self._brightness / 100.0     # small bright areas count too
        now = time.monotonic()
        self._lvl += (eff - self._lvl) * min(1.0, (now - self._lvl_t) / 8.0)
        self._lvl_t = now
        want = self._bits
        cand = self._depth_for(self._lvl)
        if eff > 0.30:
            want = config.MATRIX_PWM_BITS
        elif cand > self._bits and self._depth_for(self._lvl * 1.25) == cand and eff < 1.25 * self._lvl + 0.02:
            want = cand
        elif cand < self._bits and self._depth_for(self._lvl / 1.25) == cand:
            want = cand
        dwell = 25.0 if want > self._bits else 0.4                        # slow to enrich, quick to calm
        if want != self._bits and now - self._bits_t > dwell:
            self._bits, self._bits_t = want, now
            print(f"[bits] {want} PWM bits (picture level {eff:.2f})", flush=True)
            LedMatrix._bits_now = want
            with self._lock:
                self.matrix.pwmBits = want
                self.matrix.brightness = self._hw_brightness(self._brightness)

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
        sub = arr[::4, ::4]
        self._adapt_bits(mean, float((sub.max(axis=2) > 200).mean()))
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

    @staticmethod
    def _lift_lut(strength: float) -> np.ndarray:
        """scale[m] for a pixel whose brightest channel is m: dark pixels are scaled up (hue kept), bright ones left alone."""
        m = np.arange(256, dtype=np.float32)
        g = 255.0 * (np.maximum(m, 1.0) / 255.0) ** 0.55                     # a strong gamma lift of the shadows
        t = np.clip((m - 60.0) / 140.0, 0.0, 1.0)
        w = 1.0 - t * t * (3 - 2 * t)                                        # full lift below 60, none above 200
        f = m + strength * (g - m) * w
        scale = np.where(m > 0, f / np.maximum(m, 1.0), 1.0)
        return scale.astype(np.float32)

    def _lift(self, arr: np.ndarray) -> np.ndarray:
        k = config.ART_SHADOW_LIFT
        if k <= 0.001:
            return arr
        if getattr(self, "_lift_k", None) != k:
            self._lift_k, self._lift_scale = k, self._lift_lut(k)
        m = arr.max(axis=2)
        out = arr.astype(np.float32) * self._lift_scale[m][..., None]
        return np.minimum(out, 255.0).astype(np.uint8)

    def _remap(self, image: Image.Image) -> np.ndarray:
        """Logical canvas -> flat chain strip (rows, chain*cols, 3) uint8.

        Pure reshape/transpose/fancy-index: no per-panel Python loop on the
        hot path.
        """
        if not hasattr(self, "_tile_idx"):
            self._prepare_layout()
        pr, pc = config.PANEL_ROWS, config.PANEL_COLS
        arr = self._limit_power(self._lift(np.asarray(image, dtype=np.uint8)))
        self._shown = arr                                # what the LEDs show (before per-panel calibration)
        tiles = (arr.reshape(config.PANELS_TALL, pr, config.PANELS_WIDE, pc, 3)
                 .transpose(0, 2, 1, 3, 4)
                 .reshape(-1, pr, pc, 3))
        sel = tiles[self._tile_idx]                      # (chain, pr, pc, 3)
        if self._luts is not None:
            for k in range(len(sel)):
                sel[k] = self._luts[k][_CH, sel[k]]
        for k, quarter_turns in self._rots.items():
            sel[k] = np.rot90(sel[k], k=-quarter_turns)
        per = getattr(config, "CHAIN_PER_PORT", len(sel))
        slots = getattr(config, "PORT_SLOTS", [0])
        if len(slots) == 1 and config.PARALLEL == 1:
            return np.ascontiguousarray(sel.transpose(1, 0, 2, 3).reshape(pr, len(sel) * pc, 3))
        out = np.zeros((config.PARALLEL * pr, per * pc, 3), np.uint8)    # port slot p = rows p*64 ...
        for i, slot in enumerate(slots):
            out[slot * pr:(slot + 1) * pr] = (sel[i * per:(i + 1) * per]
                                              .transpose(1, 0, 2, 3).reshape(pr, per * pc, 3))
        return out

    def draw(self, image: Image.Image, frame_fraction: int = 1) -> bool:
        """Show a frame. frame_fraction=N holds it for exactly N panel refreshes
        (the library paces it on vsync - smooth motion with no timer drift).
        Returns False if the frame was identical and nothing was sent."""
        if image.size != (config.TOTAL_WIDTH, config.TOTAL_HEIGHT):
            image = image.resize((config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        if image.mode != "RGB":
            image = image.convert("RGB")
        t0 = time.perf_counter()
        strip = self._remap(image)
        write_snapshot(self._shown, {"hw": self._hw_brightness(self._brightness), "brightness": self._brightness,
                                     "bits": int(getattr(LedMatrix, "_bits_now", config.MATRIX_PWM_BITS))})
        # Static content (idle text, held frames) costs nothing: skip the
        # upload when nothing changed — the panels keep showing the last frame.
        if self._prev is not None and np.array_equal(strip, self._prev):
            return False
        self._prev = strip
        with self._lock:
            self.canvas.SetImage(Image.fromarray(strip, "RGB"))
            self.send_s = time.perf_counter() - t0               # remap + upload, before the vsync wait
            self.canvas = self.matrix.SwapOnVSync(self.canvas, max(1, int(frame_fraction)))
        return True

    def clear(self) -> None:
        black = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT), (0, 0, 0))
        self.draw(black)

    def set_brightness(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self._brightness = value
        with self._lock:
            self.matrix.brightness = self._hw_brightness(value)

    def shutdown(self) -> None:
        self.clear()
