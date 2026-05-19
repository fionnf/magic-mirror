"""Optional addressable LED strip (SK6812 RGBWW) around the mirror.

Provides three implementations sharing one API:

- RealStrip    — drives a physical SK6812 strip via rpi_ws281x.
- SimStrip     — pushes pixels into the LED simulator's perimeter overlay.
- NullStrip    — silent no-op when no strip is wired up / library missing.

Call sites should only ever talk to the abstract API:
    strip.set_mode("idle" | "countdown" | "capture_flash" | "thinking"
                   | "displaying" | "fading")
    strip.set_centroid(0.0..1.0)        # normalised x of the silhouette
    strip.shutdown()
"""
import math
import threading
import time
import colorsys
import config


class NullStrip:
    def set_mode(self, mode): pass
    def set_centroid(self, x): pass
    def shutdown(self): pass


class _BaseStrip:
    """Drives the strip animation in its own thread. Subclasses implement
    `_write(pixels)` where pixels is a list of (R, G, B, W) tuples 0-255."""

    def __init__(self, num: int):
        self.num = num
        self._mode = "idle"
        self._centroid = 0.5            # target centroid (set by caller)
        self._smoothed_centroid = 0.5   # what we actually render with
        self._lock = threading.Lock()
        self._t0 = time.monotonic()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="led-strip")
        self._thread.start()

    # ---- public ----

    def set_mode(self, mode: str) -> None:
        with self._lock:
            if mode != self._mode:
                self._mode = mode

    def set_centroid(self, x: float) -> None:
        with self._lock:
            self._centroid = max(0.0, min(1.0, float(x)))

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self._thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            self._write([(0, 0, 0, 0)] * self.num)
        except Exception:
            pass

    # ---- animation ----

    def _loop(self):
        interval = 1.0 / max(1, config.LED_STRIP_FPS)
        alpha = config.LED_STRIP_CENTROID_SMOOTHING
        while not self._stop.is_set():
            t = time.monotonic() - self._t0
            with self._lock:
                mode = self._mode
                target = self._centroid
                # exponential smoothing — the rendered centroid creeps toward
                # the target a tiny fraction each frame, so movements look
                # like a slow tide rather than a snap.
                self._smoothed_centroid += alpha * (target - self._smoothed_centroid)
                centroid = self._smoothed_centroid
            try:
                pixels = self._render(t, mode, centroid)
                self._write(pixels)
            except Exception as e:
                print(f"[STRIP] write error: {e}")
                time.sleep(0.5)
                continue
            time.sleep(interval)

    def _render(self, t: float, mode: str, centroid: float):
        n = self.num
        if mode == "capture_flash":
            return [(0, 0, 0, 255)] * n
        if mode == "countdown":
            # ~1Hz breathing, ramp up so the third pulse is brightest
            phase = (t * 2.0) % 2.0
            breath = 0.5 - 0.5 * math.cos(phase * math.pi)
            v = int(255 * breath)
            return [(v, v, v, 0)] * n
        if mode == "thinking":
            return self._warm_with_hue(t, centroid, pulse_strength=1.0,
                                       pulse_hz=1.4)
        if mode == "displaying":
            return self._warm_with_hue(t, centroid, pulse_strength=0.0,
                                       saturation_boost=True)
        if mode == "fading":
            # slow fade towards idle warm white
            fade_t = min(1.0, (t % 4.0) / 1.5)
            return self._warm_with_hue(t, centroid, pulse_strength=0.0,
                                       band_scale=1.0 - fade_t)
        # default: idle
        return self._warm_with_hue(t, centroid, pulse_strength=0.0)

    def _warm_with_hue(self, t, centroid, pulse_strength=0.0, pulse_hz=1.0,
                       saturation_boost=False, band_scale=1.0):
        n = self.num
        hue = (t * config.LED_STRIP_HUE_SPEED) % 1.0
        # Map the smoothed centroid to a position on the top edge of the strip
        # (LEDs 0 .. top_len-1 run left → right across the top of the mirror).
        top_len = max(1, n // 4)
        # Two summed slow sines give a quasi-organic drift even when the
        # subject is perfectly still.
        f1, f2 = config.LED_STRIP_WOBBLE_HZ
        wobble = config.LED_STRIP_WOBBLE_AMPLITUDE * n * (
            0.6 * math.sin(t * math.pi * 2 * f1)
            + 0.4 * math.sin(t * math.pi * 2 * f2 + 1.3))
        band_centre = centroid * (top_len - 1) + wobble

        # Wider band + Gaussian-ish falloff = soft glow rather than a hot spot.
        band_width = max(2.0, n * config.LED_STRIP_BAND_FRACTION)
        sigma = band_width / 2.0
        pulse = (1.0 if pulse_strength == 0
                 else 0.5 + 0.5 * math.sin(t * math.pi * 2 * pulse_hz))
        sat = 0.95 if saturation_boost else 0.75  # lower sat = less assault
        r_c, g_c, b_c = colorsys.hsv_to_rgb(hue, sat, 1.0)
        peak = config.LED_STRIP_BAND_INTENSITY
        warm = config.LED_STRIP_WARM_LEVEL
        out = []
        for i in range(n):
            d = min(abs(i - band_centre), n - abs(i - band_centre))
            # gaussian falloff — much softer edges than the previous linear one
            band = math.exp(-(d * d) / (2 * sigma * sigma)) * band_scale * peak
            if pulse_strength:
                band *= (1.0 - pulse_strength) + pulse_strength * pulse
            r = int(r_c * 255 * band)
            g = int(g_c * 255 * band)
            b = int(b_c * 255 * band)
            # warm-white channel only dips slightly under the band so the
            # frame never looks dim or "lost" where the colour sits.
            w = int(warm * (1.0 - 0.35 * band))
            out.append((r, g, b, w))
        return out

    def _write(self, pixels):
        raise NotImplementedError


class RealStrip(_BaseStrip):
    def __init__(self):
        from rpi_ws281x import PixelStrip, ws
        self._ws = ws
        self._strip = PixelStrip(
            num=config.LED_STRIP_COUNT,
            pin=config.LED_STRIP_PIN,
            freq_hz=800000,
            dma=config.LED_STRIP_DMA,
            invert=False,
            brightness=config.LED_STRIP_BRIGHTNESS,
            channel=config.LED_STRIP_CHANNEL,
            strip_type=ws.SK6812_STRIP_RGBW,
        )
        self._strip.begin()
        super().__init__(num=config.LED_STRIP_COUNT)

    def _write(self, pixels):
        # SK6812 RGBW: 32-bit colour value with W in the high byte
        for i, (r, g, b, w) in enumerate(pixels):
            self._strip.setPixelColor(
                i, (w & 0xFF) << 24 | (r & 0xFF) << 16
                   | (g & 0xFF) << 8 | (b & 0xFF))
        self._strip.show()


class SimStrip(_BaseStrip):
    def __init__(self, sim_matrix):
        self._sim_matrix = sim_matrix
        super().__init__(num=config.LED_STRIP_COUNT)

    def _write(self, pixels):
        self._sim_matrix.set_strip_pixels(pixels)


def create_strip(sim_matrix=None):
    """Factory. Pass `sim_matrix` for simulator rendering; otherwise tries the
    real driver and falls back to NullStrip on any failure."""
    if sim_matrix is not None:
        try:
            return SimStrip(sim_matrix)
        except Exception as e:
            print(f"[STRIP] sim init failed: {e}")
            return NullStrip()
    try:
        return RealStrip()
    except Exception as e:
        print(f"[STRIP] not available, disabling: {e}")
        return NullStrip()
