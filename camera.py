"""Pi Camera capture and OpenCV silhouette extraction."""
import threading
import time
import numpy as np
import cv2
import config
import vision


class Camera:
    def __init__(self):
        from picamera2 import Picamera2
        self.cam = Picamera2()
        # A video configuration streams continuously (a still one re-arms for every frame: a few fps and a
        # laggy picture). queue=False hands out the newest frame, never one that waited in line.
        cfg = self.cam.create_video_configuration(
            main={"size": (config.FRAME_WIDTH, config.FRAME_HEIGHT), "format": "RGB888"},
            buffer_count=4, queue=False,
            controls={"FrameDurationLimits": (33333, 33333)},          # 30 fps
        )
        try:        # mains lights flicker at twice the mains frequency; exposing in whole flicker periods stops the banding
            cfg["controls"].update({"AeFlickerMode": 1, "AeFlickerPeriod": int(1e6 / (2 * config.CAMERA_MAINS_HZ))})
        except Exception:
            pass
        self.cam.configure(cfg)
        self.cam.start()
        time.sleep(config.CAMERA_WARMUP_SEC)
        self._lock_light()                      # no more auto-exposure / auto-white-balance hunting: that is the biggest flicker
        self._latest, self._seq = None, 0
        self._cond = threading.Condition()
        self._running = True
        threading.Thread(target=self._reader, daemon=True, name="camera-reader").start()
        threading.Thread(target=self._watch_light, daemon=True, name="camera-light").start()
        self._background = None
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=config.BG_HISTORY, varThreshold=config.BG_THRESHOLD, detectShadows=False
        )

    def _lock_light(self):
        """Freeze exposure, gain and white balance at what the camera chose for this room. Left on auto, they keep re-adjusting
        to every movement (a white shirt, a dark coat), and the whole picture on the wall pumps and shimmers. The exposure is
        rounded to whole mains-flicker periods so the room lights cannot band either. Re-done slowly if the room changes."""
        try:
            md = self.cam.capture_metadata()
            exp, gain = float(md["ExposureTime"]), float(md["AnalogueGain"])
            period = 1e6 / (2 * config.CAMERA_MAINS_HZ)                 # 10 000 us at 50 Hz
            exp2 = max(period, round(exp / period) * period)
            exp2 = min(exp2, 33000.0)                                   # one frame at 30 fps
            gain = min(16.0, max(1.0, gain * exp / exp2))               # keep the same brightness at the rounded exposure
            ctl = {"AeEnable": False, "AwbEnable": False, "ExposureTime": int(exp2), "AnalogueGain": gain}
            if "ColourGains" in md:
                ctl["ColourGains"] = tuple(md["ColourGains"])
            self.cam.set_controls(ctl)
            self._lock_ctl = dict(ctl)
            self._lock_mean = None
            self._locked = True
            print(f"[CAMERA] light locked: {int(exp2)} us, gain {gain:.2f}")
        except Exception as e:
            self._locked = False
            print(f"[CAMERA] could not lock exposure ({e}); staying on auto")

    def light_auto(self):
        """For the photo flash: let the camera meter freely while the screen edge lights the person."""
        self._unlock_light()

    def light_restore(self):
        """After the flash: back to the exposure and white balance locked before it."""
        ctl = getattr(self, "_lock_ctl", None)
        try:
            if ctl:
                self.cam.set_controls(ctl)
        except Exception:
            pass

    def _unlock_light(self):
        try:
            self.cam.set_controls({"AeEnable": True, "AwbEnable": True})
        except Exception:
            pass

    def _watch_light(self):
        """Every 20 s: if the picture has been much brighter or darker than when the light was locked for a full minute (the sun
        went down, the lamps came on), let the camera choose again for two seconds and lock the new values."""
        away = 0
        while self._running:
            time.sleep(20)
            if not getattr(self, "_locked", False) or self._latest is None:
                continue
            m = float(self._latest[::8, ::8].mean()) + 1.0
            if self._lock_mean is None:
                self._lock_mean = m
                continue
            away = away + 1 if abs(m / self._lock_mean - 1.0) > 0.35 else 0
            if away >= 3:
                away = 0
                self._unlock_light()
                time.sleep(2.5)
                self._lock_light()
                self._lock_mean = float(self._latest[::8, ::8].mean()) + 1.0

    def _reader(self):
        """Keeps only the newest frame, so a slow consumer never sees an old picture."""
        while self._running:
            try:
                frame = cv2.cvtColor(self.cam.capture_array(), cv2.COLOR_RGB2BGR)
            except Exception:
                time.sleep(0.05)
                continue
            with self._cond:
                self._latest, self._seq = frame, self._seq + 1
                self._cond.notify_all()

    def wait_frame(self, last_seq: int, timeout: float = 0.5):
        """Block until a frame newer than last_seq arrives. Returns (seq, portrait crop), or (last_seq, None)."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq != last_seq, timeout)
            if self._seq == last_seq or self._latest is None:
                return last_seq, None
            return self._seq, vision.crop_to_aspect(self._latest, config.CAMERA_ASPECT)

    def capture_frame(self, raw: bool = False) -> np.ndarray:
        """raw=True: the full-width frame (for the smart portrait crop of photos).
        Default: centred portrait crop (cheap; used by the live silhouette)."""
        with self._cond:
            if self._latest is None:
                self._cond.wait_for(lambda: self._latest is not None, 2.0)
            frame = self._latest
        if frame is None:
            raise RuntimeError("camera has no frame")
        return frame.copy() if raw else vision.crop_to_aspect(frame, config.CAMERA_ASPECT)

    def get_background_frame(self) -> np.ndarray:
        self._background_raw = self.capture_frame(raw=True)      # for the motion crop fallback
        self._background = vision.crop_to_aspect(self._background_raw, config.CAMERA_ASPECT)
        # prime the MOG2 subtractor
        for _ in range(5):
            self._subtractor.apply(self._background)
        return self._background

    def extract_silhouette(self, frame: np.ndarray, background: np.ndarray = None) -> np.ndarray:
        bg = background if background is not None else self._background
        return vision.silhouette_mask(frame, bg, self._subtractor)

    def shutdown(self) -> None:
        self._running = False
        try:
            self.cam.stop()
        except Exception:
            pass
