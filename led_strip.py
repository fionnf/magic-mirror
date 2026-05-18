"""SK6812 RGBW LED strip around the mirror frame.

In simulator mode the pixels are forwarded to LEDSimulator.set_strip_pixels()
so the window's border shows a live preview. On real hardware rpi_ws281x
drives the GPIO directly.

If neither path works, create_strip() returns NullStrip so the rest of the
app runs without error.

Modes
-----
idle          – warm-white base + slow-drifting hue band tracking the person
countdown     – same but with a 2 Hz breathing pulse for the 3-2-1 beat
thinking      – cool-blue chase wave while the AI is processing
displaying    – same as idle but with a slightly brighter band
fading        – dim warm only; colour band drops out
capture_flash – full bright white on every LED for the photo
"""
import colorsys
import math
import threading
import time
from typing import List, Optional, Tuple

import config

_Pixel = Tuple[int, int, int, int]   # (R, G, B, W)


# ---------------------------------------------------------------------------
# Hardware back-ends
# ---------------------------------------------------------------------------

class _HWStrip:
    """Real SK6812 via rpi_ws281x."""

    def __init__(self) -> None:
        from rpi_ws281x import PixelStrip, ws
        self._strip = PixelStrip(
            config.LED_STRIP_COUNT,
            config.LED_STRIP_PIN,
            dma=config.LED_STRIP_DMA,
            brightness=config.LED_STRIP_BRIGHTNESS,
            channel=config.LED_STRIP_CHANNEL,
            strip_type=ws.SK6812_STRIP_RGBW,
        )
        self._strip.begin()

    def show(self, pixels: List[_Pixel]) -> None:
        for i, (r, g, b, w) in enumerate(pixels):
            # 32-bit WRGB word — high byte = W for SK6812
            self._strip.setPixelColor(i, (w << 24) | (r << 16) | (g << 8) | b)
        self._strip.show()

    def clear(self) -> None:
        for i in range(config.LED_STRIP_COUNT):
            self._strip.setPixelColor(i, 0)
        self._strip.show()


class _SimHWStrip:
    """Forwards pixel data to the simulator's matrix border."""

    def __init__(self, sim_matrix) -> None:
        self._matrix = sim_matrix

    def show(self, pixels: List[_Pixel]) -> None:
        self._matrix.set_strip_pixels(pixels)

    def clear(self) -> None:
        self._matrix.set_strip_pixels([(0, 0, 0, 0)] * config.LED_STRIP_COUNT)


# ---------------------------------------------------------------------------
# Null strip — used when hardware and sim are both unavailable
# ---------------------------------------------------------------------------

class NullStrip:
    def set_mode(self, _mode: str) -> None:
        pass

    def set_centroid(self, _x: float) -> None:
        pass

    def shutdown(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Main strip controller
# ---------------------------------------------------------------------------

class LEDStrip:
    def __init__(self, hw) -> None:
        self._hw = hw
        self._mode = "idle"
        self._centroid = 0.5    # smoothed 0-1 horizontal position of subject
        self._hue = 0.0         # current hue for the slowly drifting band
        self._t = 0.0           # elapsed seconds (animation clock)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="led-strip")
        self._thread.start()

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode

    def set_centroid(self, x: float) -> None:
        """Smoothly track silhouette centroid (0 = left, 1 = right)."""
        with self._lock:
            a = config.LED_STRIP_CENTROID_SMOOTHING
            self._centroid += a * (x - self._centroid)

    # ------------------------------------------------------------------ loop

    def _loop(self) -> None:
        interval = 1.0 / config.LED_STRIP_FPS
        while not self._stop.is_set():
            t0 = time.monotonic()
            with self._lock:
                mode = self._mode
                centroid = self._centroid
                self._hue = (self._hue + config.LED_STRIP_HUE_SPEED / config.LED_STRIP_FPS) % 1.0
                hue = self._hue
                self._t += interval
                t = self._t
            try:
                pixels = self._render(mode, centroid, hue, t)
                self._hw.show(pixels)
            except Exception as e:
                print(f"[STRIP] {e}")
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))

    # --------------------------------------------------------------- render

    def _render(self, mode: str, centroid: float,
                hue: float, t: float) -> List[_Pixel]:
        n = config.LED_STRIP_COUNT

        if mode == "capture_flash":
            return [(255, 255, 255, 255)] * n

        if mode == "fading":
            w = max(0, config.LED_STRIP_WARM_LEVEL // 3)
            return [(0, 0, 0, w)] * n

        if mode == "thinking":
            return self._thinking(n, t)

        # idle / countdown / displaying all use the same warm-base + hue-band
        # logic, with countdown adding a breathing pulse on top.
        breath = (0.5 + 0.5 * math.sin(t * math.tau * 2.0)
                  if mode == "countdown" else 1.0)

        warm = config.LED_STRIP_WARM_LEVEL
        intensity = config.LED_STRIP_BAND_INTENSITY
        if mode == "displaying":
            intensity = min(1.0, intensity * 1.3)

        # Two coprime slow sinusoids keep the band moving even when the person
        # stands perfectly still.
        wobble = sum(
            math.sin(t * math.tau * hz)
            for hz in config.LED_STRIP_WOBBLE_HZ
        ) * config.LED_STRIP_WOBBLE_AMPLITUDE * 0.5
        band_centre = (centroid + wobble) % 1.0
        band_half = config.LED_STRIP_BAND_FRACTION / 2.0

        r_f, g_f, b_f = colorsys.hsv_to_rgb(hue, 0.85, 1.0)

        pixels: List[_Pixel] = []
        for i in range(n):
            pos = i / n
            dist = abs(pos - band_centre)
            if dist > 0.5:
                dist = 1.0 - dist
            band_w = max(0.0, 1.0 - dist / band_half)

            lum = intensity * band_w * breath
            r = min(255, int(r_f * 255 * lum))
            g = min(255, int(g_f * 255 * lum))
            b = min(255, int(b_f * 255 * lum))
            w = min(255, int(warm * (1.0 - band_w * 0.5) * breath))
            pixels.append((r, g, b, w))
        return pixels

    def _thinking(self, n: int, t: float) -> List[_Pixel]:
        """Cool-blue chase wave while the AI call is in flight."""
        warm_base = int(config.LED_STRIP_WARM_LEVEL * 0.25)
        pixels: List[_Pixel] = []
        for i in range(n):
            pos = i / n
            wave = (
                0.55 * max(0.0, math.sin((pos * 5 - t * 0.7) * math.tau)) +
                0.35 * max(0.0, math.sin((pos * 8 + t * 0.4) * math.tau))
            )
            lev = min(1.0, wave)
            pixels.append((
                int(lev * 50),
                int(lev * 110),
                int(lev * 255),
                warm_base,
            ))
        return pixels

    # ------------------------------------------------------------------ stop

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self._hw.clear()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_strip(sim_matrix=None):
    """Return a live LEDStrip, or NullStrip if hardware is unavailable."""
    if sim_matrix is not None:
        return LEDStrip(_SimHWStrip(sim_matrix))
    try:
        return LEDStrip(_HWStrip())
    except Exception as e:
        print(f"[STRIP] hardware unavailable ({e}); strip disabled")
        return NullStrip()
