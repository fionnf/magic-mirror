"""A live look through the wall's camera, for the control app: what is in front of the wall right now, like a webcam.

It works without mirror mode. The camera is opened only while someone is watching (the app's "Look through the camera" button) and
closed 10 seconds after the last viewer leaves; the picture is a small, low-rate MJPEG stream (about 6 frames a second, 640 px), light
enough for the tunnel. While the mirror is running it owns the camera, so the live view then takes its pictures from the mirror
(`/api/frame.jpg` on the mirror's own port). Starting the mirror closes the live view's camera first.

Visitors from outside the home network need the wall's password, like every other part of the app. And it is never secret that it is
on: while anyone is watching, a small red dot blinks in a corner of the wall (play.py reads `panel_setup/liveview.on`, which this
touches every second) and the app says so.
"""
import os
import threading
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FLAG = os.path.join(HERE, "panel_setup", "liveview.on")
WIDTH, FPS, IDLE = 640, 6, 10.0


class LiveView:
    def __init__(self, mirror_on=lambda: False, mirror_frame=lambda: None):
        self.mirror_on, self.mirror_frame = mirror_on, mirror_frame
        self.viewers = 0
        self.latest, self.error, self.source = None, "", ""
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._first = threading.Event()

    # ---- the camera ----
    @staticmethod
    def _open():
        """-> a function returning a BGR frame, and a function that closes the camera."""
        try:
            from picamera2 import Picamera2
            cam = Picamera2()
            cam.configure(cam.create_video_configuration(main={"size": (WIDTH, 480), "format": "RGB888"}, buffer_count=2))
            cam.start()
            time.sleep(0.8)                                       # let the exposure settle
            return (lambda: cv2.cvtColor(cam.capture_array(), cv2.COLOR_RGB2BGR)), (lambda: (cam.stop(), cam.close()))
        except ImportError:
            if not os.environ.get("WALL_SIM"):
                raise RuntimeError("no Pi camera on this machine")
            cap = cv2.VideoCapture(0)                             # the laptop simulator: its own webcam
            if not cap.isOpened():
                raise RuntimeError("no camera found")
            return (lambda: cap.read()[1]), cap.release

    def _jpeg(self, frame):
        h, w = frame.shape[:2]
        if w > WIDTH:
            frame = cv2.resize(frame, (WIDTH, int(h * WIDTH / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 62])
        return buf.tobytes() if ok else None

    def _loop(self):
        grab = close = None
        last_seen = time.time()
        try:
            while not self._stop.is_set():
                now = time.time()
                if self.viewers:
                    last_seen = now
                elif now - last_seen > IDLE:
                    break
                try:
                    os.utime(FLAG, None) if os.path.exists(FLAG) else open(FLAG, "w").close()      # "someone is watching": the wall shows a dot
                except OSError:
                    pass
                t0 = time.time()
                try:
                    if self.mirror_on():
                        if close:                                  # the mirror owns the camera now
                            close(); grab = close = None
                        jpg = self.mirror_frame()
                        self.source = "mirror"
                    else:
                        if grab is None:
                            grab, close = self._open()
                        frame = grab()
                        jpg = self._jpeg(frame) if frame is not None else None
                        self.source = "camera"
                    if jpg:
                        self.latest, self.error = jpg, ""
                        self._first.set()
                except Exception as e:
                    self.error = str(e)[:100]
                    self._first.set()
                    if grab is None:
                        time.sleep(2.0)
                time.sleep(max(0.0, 1.0 / FPS - (time.time() - t0)))
        finally:
            if close:
                try:
                    close()
                except Exception:
                    pass
            try:
                os.remove(FLAG)
            except OSError:
                pass
            with self._lock:
                self._thread, self.latest = None, None
                self._first.clear()

    def _ensure(self):
        with self._lock:
            if self._thread is None:
                self._stop.clear()
                self._first.clear()
                self._thread = threading.Thread(target=self._loop, daemon=True, name="camera-live")
                self._thread.start()
        self._first.wait(6.0)

    # ---- for the app ----
    def stream(self):
        """MJPEG chunks for a multipart/x-mixed-replace response."""
        self.viewers += 1
        try:
            self._ensure()
            last = None
            while not self._stop.is_set():
                jpg = self.latest
                if jpg is not None and jpg is not last:
                    last = jpg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
                elif self._thread is None:
                    break
                time.sleep(0.05)
        finally:
            self.viewers = max(0, self.viewers - 1)

    def snapshot(self):
        """One JPEG now (starts the camera for a moment if nobody is watching), or None."""
        self.viewers += 1
        try:
            self._ensure()
            return self.latest
        finally:
            self.viewers = max(0, self.viewers - 1)

    def status(self):
        return {"watching": self.viewers > 0, "source": self.source, "error": self.error}

    def stop(self):
        """Close the camera now (the mirror is about to need it)."""
        self._stop.set()
        th = self._thread
        if th is not None:
            th.join(timeout=4.0)
