"""Mock camera: webcam (cv2.VideoCapture), network stream, or static image.
Same API as Camera.

stream mode reads an MJPEG/HTTP (or any OpenCV-readable) URL, e.g. a laptop
webcam served by panel_setup/stream_webcam.sh. A reader thread keeps only the
newest frame so the silhouette never lags behind a growing network buffer.
"""
import os
import threading
import time
import numpy as np
import cv2
import config
import vision


class CameraMock:
    def __init__(self, mode: str = "webcam", static_image: str = None,
                 static_background: str = None, source: str = None):
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
        elif mode == "stream":
            if not source:
                raise ValueError("stream mode needs a source URL")
            # The laptop streamer serves one client at a time and needs a
            # moment to re-arm after the previous client leaves: retry.
            deadline = time.monotonic() + 20
            while True:
                self.cap = cv2.VideoCapture(source)
                if self.cap.isOpened():
                    break
                self.cap.release()
                if time.monotonic() > deadline:
                    raise RuntimeError(f"cannot open camera stream {source}")
                time.sleep(1.0)
            self._latest = None
            self._lock = threading.Lock()
            self._running = True
            threading.Thread(target=self._reader, daemon=True, name="stream-reader").start()
            deadline = time.monotonic() + 10
            while self._latest is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if self._latest is None:
                raise RuntimeError(f"no frames from camera stream {source}")
            print(f"[CAMERA] streaming from {source}")
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

    def _reader(self):
        while self._running:
            ok, frame = self.cap.read()
            if ok:
                with self._lock:
                    self._latest = frame
            else:
                time.sleep(0.05)

    def capture_frame(self) -> np.ndarray:
        return vision.crop_to_aspect(self._raw_frame(), config.CAMERA_ASPECT)

    def _raw_frame(self) -> np.ndarray:
        if self.mode == "stream":
            with self._lock:
                if self._latest is None:
                    raise RuntimeError("camera stream has no frame")
                return self._latest.copy()
        if self.mode == "webcam":
            ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError("webcam read failed")
            return frame
        return self._static_frame.copy()

    def get_background_frame(self) -> np.ndarray:
        if self.mode in ("webcam", "stream"):
            print("[SIM] Stand clear — capturing background in 3s...")
            time.sleep(3.0)
            self._background = self.capture_frame()
        else:
            self._background = vision.crop_to_aspect(self._static_background,
                                                     config.CAMERA_ASPECT).copy()
        for _ in range(5):
            self._subtractor.apply(self._background)
        return self._background

    def extract_silhouette(self, frame: np.ndarray, background: np.ndarray = None) -> np.ndarray:
        bg = background if background is not None else self._background
        return vision.silhouette_mask(frame, bg, self._subtractor)

    def shutdown(self) -> None:
        self._running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
