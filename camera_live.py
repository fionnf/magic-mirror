"""A live look through the wall's camera, for the control app: what is in front of the wall right now, like a webcam.

It works without mirror mode. The camera is opened only while someone is watching (the app's "Look through the camera" button) and
closed 10 seconds after the last viewer leaves; the picture is a small, low-rate MJPEG stream (about 6 frames a second, 640 px), light
enough for the tunnel. The camera is opened by a small helper process (`python3 camera_live.py --worker`), never by the web server itself, so
if the camera layer misbehaves only the helper dies and the app gets the reason. While the mirror is running it owns the camera, so the live view then takes its pictures from the mirror
(`/api/frame.jpg` on the mirror's own port). Starting the mirror closes the live view's camera first.

Visitors from outside the home network need the wall's password, like every other part of the app. And it is never secret that it is
on: while anyone is watching, a small red dot blinks in a corner of the wall (play.py reads `panel_setup/liveview.on`, which this
touches every second) and the app says so.
"""
import os
import select
import struct
import subprocess
import sys
import threading
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FLAG = os.path.join(HERE, "panel_setup", "liveview.on")
LOG = os.path.join(HERE, "panel_setup", "logs", "camera_live.log")
WIDTH, FPS, IDLE = 640, 6, 10.0


def _jpeg(frame):
    h, w = frame.shape[:2]
    if w > WIDTH:
        frame = cv2.resize(frame, (WIDTH, int(h * WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 62])
    return buf.tobytes() if ok else None


# ------------------------------------------------------------------ the helper process ---

def worker():
    """Open the camera and write JPEG frames to stdout, each as a 4-byte big-endian length and the bytes, until stdin closes or SIGTERM."""
    if os.environ.get("CAMERA_LIVE_FAKE"):                    # tests: a synthetic picture, no camera
        n = {"i": 0}

        def grab():
            n["i"] += 1
            f = np.zeros((480, 640, 3), np.uint8)
            f[:, :, 1] = (n["i"] * 20) % 255
            return f
    else:
        try:
            from picamera2 import Picamera2
            cam = Picamera2()
            cam.configure(cam.create_video_configuration(main={"size": (WIDTH, 480), "format": "RGB888"}, buffer_count=2))
            cam.start()
            time.sleep(0.8)                                   # let the exposure settle
            grab = lambda: cv2.cvtColor(cam.capture_array(), cv2.COLOR_RGB2BGR)
        except ImportError:
            if not os.environ.get("WALL_SIM"):
                sys.exit("no Pi camera on this machine (picamera2 is not installed)")
            cap = cv2.VideoCapture(0)                         # the laptop simulator: its own webcam
            if not cap.isOpened():
                sys.exit("no camera found")
            grab = lambda: cap.read()[1]
    out = sys.stdout.buffer
    while True:
        t0 = time.time()
        frame = grab()
        jpg = _jpeg(frame) if frame is not None else None
        if jpg:
            out.write(struct.pack(">I", len(jpg)) + jpg)
            out.flush()
        time.sleep(max(0.0, 1.0 / FPS - (time.time() - t0)))


# ------------------------------------------------------------------ the web server's side ---

class LiveView:
    def __init__(self, mirror_on=lambda: False, mirror_frame=lambda: None):
        self.mirror_on, self.mirror_frame = mirror_on, mirror_frame
        self.viewers = 0
        self.latest, self.error, self.source = None, "", ""
        self._lock = threading.Lock()
        self._thread = None
        self._proc = None
        self._stop = threading.Event()
        self._first = threading.Event()

    def _spawn(self):
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        log = open(LOG, "ab")
        log.write(f"\n==== {time.ctime()} live view starts the camera helper\n".encode())
        log.flush()
        return subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--worker"], cwd=HERE, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=log, env=dict(os.environ))

    def _why_it_died(self, proc):
        try:
            with open(LOG, "rb") as fh:
                fh.seek(max(0, os.path.getsize(LOG) - 1500))
                tail = [x for x in fh.read().decode(errors="replace").strip().splitlines() if x.strip()]
        except OSError:
            tail = []
        return (tail[-1] if tail else f"the camera helper stopped (exit {proc.returncode})")[:200]

    def _kill(self):
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _read_frame(self, proc, timeout=1.0):
        """One JPEG from the helper, None if none came in `timeout` seconds, raises EOFError when it has gone."""
        r, _, _ = select.select([proc.stdout], [], [], timeout)
        if not r:
            if proc.poll() is not None:
                raise EOFError
            return None
        hdr = proc.stdout.read(4)
        if len(hdr) < 4:
            raise EOFError
        n = struct.unpack(">I", hdr)[0]
        data = b""
        while len(data) < n:
            chunk = proc.stdout.read(n - len(data))
            if not chunk:
                raise EOFError
            data += chunk
        return data

    def _loop(self):
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
                    if self.mirror_on():                      # the mirror owns the camera: its pictures, not ours
                        self._kill()
                        self.source = "mirror"
                        jpg = self.mirror_frame()
                        if jpg:
                            self.latest, self.error = jpg, ""
                        else:
                            self.error = "the mirror is running but sent no picture (restart the mirror)"
                        self._first.set()
                        time.sleep(max(0.0, 1.0 / FPS - (time.time() - t0)))
                        continue
                    self.source = "camera"
                    if self._proc is None:
                        self._proc = self._spawn()
                    jpg = self._read_frame(self._proc)
                    if jpg:
                        self.latest, self.error = jpg, ""
                        self._first.set()
                except EOFError:
                    proc = self._proc
                    self.error = self._why_it_died(proc) if proc else "the camera helper stopped"
                    print(f"[camera] live view: {self.error}", flush=True)
                    self._kill()
                    self._first.set()
                    time.sleep(2.0)                           # not in a tight loop if the camera cannot be opened
                except Exception as e:
                    self.error = (type(e).__name__ + ": " + str(e))[:160]
                    print(f"[camera] live view: {self.error}", flush=True)
                    self._kill()
                    self._first.set()
                    time.sleep(2.0)
        finally:
            self._kill()
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
        self._first.wait(8.0)

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
        """One JPEG now (starts the camera for a moment if nobody is watching), or None (then `error` says why)."""
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
            th.join(timeout=5.0)
        self._kill()


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker()
