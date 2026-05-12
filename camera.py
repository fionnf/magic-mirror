"""Pi Camera capture and OpenCV silhouette extraction."""
import time
import numpy as np
import cv2
import config


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
        if bg is not None:
            # absdiff against a static reference keeps stationary subjects
            # visible — required for the always-on live silhouette.
            diff = cv2.absdiff(frame, bg)
            grey = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(grey, config.SILHOUETTE_DIFF_THRESHOLD,
                                    255, cv2.THRESH_BINARY)
        else:
            mask = self._subtractor.apply(frame)
            _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        mask = cv2.medianBlur(mask, 5)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return cv2.resize(mask, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT),
                          interpolation=cv2.INTER_AREA)

    def shutdown(self) -> None:
        try:
            self.cam.stop()
        except Exception:
            pass
