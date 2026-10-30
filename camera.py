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
        self._latest, self._seq = None, 0
        self._cond = threading.Condition()
        self._running = True
        threading.Thread(target=self._reader, daemon=True, name="camera-reader").start()
        self._background = None
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=config.BG_HISTORY, varThreshold=config.BG_THRESHOLD, detectShadows=False
        )

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
