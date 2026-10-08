"""Pi Camera capture and OpenCV silhouette extraction."""
import time
import numpy as np
import cv2
import config
import vision


class Camera:
    def __init__(self):
        from picamera2 import Picamera2
        self.cam = Picamera2()
        cfg = self.cam.create_still_configuration(
            main={"size": (config.FRAME_WIDTH, config.FRAME_HEIGHT), "format": "RGB888"}
        )
        self.cam.configure(cfg)
        self.cam.start()
        time.sleep(config.CAMERA_WARMUP_SEC)
        self._background = None
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=config.BG_HISTORY, varThreshold=config.BG_THRESHOLD, detectShadows=False
        )

    def capture_frame(self, raw: bool = False) -> np.ndarray:
        """raw=True: the full-width frame (for the smart portrait crop of photos).
        Default: centred portrait crop (cheap; used by the live silhouette)."""
        frame = cv2.cvtColor(self.cam.capture_array(), cv2.COLOR_RGB2BGR)
        return frame if raw else vision.crop_to_aspect(frame, config.CAMERA_ASPECT)

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
        try:
            self.cam.stop()
        except Exception:
            pass
