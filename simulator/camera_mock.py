"""Mock camera: webcam (cv2.VideoCapture) or static image. Same API as Camera."""
import os
import time
import numpy as np
import cv2
import config
import vision


class CameraMock:
    def __init__(self, mode: str = "webcam", static_image: str = None,
                 static_background: str = None):
        self.mode = mode
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=config.BG_HISTORY, varThreshold=config.BG_THRESHOLD, detectShadows=False
        )
        self._background = None
        if mode == "webcam":
            self.cap = cv2.VideoCapture(0)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
            time.sleep(1.0)
        elif mode == "static":
            self.cap = None
            img_path = static_image or os.path.join(
                os.path.dirname(__file__), "..", "tests", "test_image.jpg")
            self._static_frame = cv2.imread(img_path)
            if self._static_frame is None:
                # synthesize: grey with a darker centre blob
                f = np.full((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3), 180, dtype=np.uint8)
                cv2.circle(f, (config.FRAME_WIDTH // 2, config.FRAME_HEIGHT // 2),
                           120, (60, 60, 60), -1)
                self._static_frame = f
            bg_path = static_background or os.path.join(
                os.path.dirname(__file__), "..", "tests", "test_background.jpg")
            bg = cv2.imread(bg_path) if os.path.exists(bg_path) else None
            if bg is None:
                bg = np.full((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3), 180, dtype=np.uint8)
            self._static_background = bg
        else:
            raise ValueError(f"unknown camera mock mode: {mode}")

    def capture_frame(self) -> np.ndarray:
        if self.mode == "webcam":
            ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError("webcam read failed")
            return frame
        return self._static_frame.copy()

    def get_background_frame(self) -> np.ndarray:
        if self.mode == "webcam":
            print("[SIM] Stand clear — capturing background in 3s...")
            time.sleep(3.0)
            ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError("webcam read failed")
            self._background = frame
        else:
            self._background = self._static_background.copy()
        for _ in range(5):
            self._subtractor.apply(self._background)
        return self._background

    def extract_silhouette(self, frame: np.ndarray, background: np.ndarray = None) -> np.ndarray:
        bg = background if background is not None else self._background
        return vision.silhouette_mask(frame, bg, self._subtractor)

    def shutdown(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
