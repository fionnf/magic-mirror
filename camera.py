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

    def capture_frame(self) -> np.ndarray:
        rgb = self.cam.capture_array()
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def get_background_frame(self) -> np.ndarray:
        self._background = self.capture_frame()
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
