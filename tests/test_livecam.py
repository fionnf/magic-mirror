"""Livecam tests: python tests/test_livecam.py"""
import http.server
import os
import socketserver
import sys
import tempfile
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from display import livecam as L


def make_video(path, n=40):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 20, (640, 360))
    for i in range(n):
        f = np.full((360, 640, 3), (30, 40, 60), np.uint8)
        cv2.circle(f, (20 + i * 15, 180), 30, (0, 200, 255), -1)
        vw.write(f)
    vw.release()


def fresh(cams, **env):
    os.environ["WALL_LIVECAMS_JSON"] = __import__("json").dumps(cams)
    for k, v in env.items():
        os.environ[k] = v
    L.CFG_FILE = "/nonexistent"
    return L.LiveCam()


def wait_live(p, secs=8):
    t0 = time.time()
    while time.time() - t0 < secs:
        p(0)
        if p.src is not None and p.src.latest()[0] is not None:
            return True
        time.sleep(0.05)
    return False


def test_shape_and_test_cam():
    p = fresh([{"name": "test"}])
    im = p(1.0)
    assert im.size == (192, 256) and im.mode == "RGB"
    assert L.thumb().size == (192, 256)


def test_no_cams_and_dead_url():
    p = fresh([])
    assert p(0).size == (192, 256)
    p = fresh([{"name": "dead", "url": "http://127.0.0.1:9/nothing.m3u8"}])
    t0 = time.time()
    for _ in range(5):
        assert p(0).size == (192, 256)
    assert time.time() - t0 < 1.0, "frame() blocked"


def test_video_file_latency():
    d = tempfile.mkdtemp()
    v = os.path.join(d, "a.mp4")
    make_video(v)
    p = fresh([{"name": "file", "url": v, "pan": True}])
    assert wait_live(p)
    ts = []
    for i in range(60):
        t = time.time()
        p(i * 0.05)
        ts.append(time.time() - t)
        time.sleep(0.02)
    print("file cam ms/frame max %.1f median %.1f" % (max(ts) * 1e3, np.median(ts) * 1e3))
    assert np.median(ts) < 0.02
    p(0).save("/tmp/livecam_file.png")


KILL = threading.Event()


class _MJPEG(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        i = 0
        try:
            while not KILL.is_set():
                f = np.full((360, 640, 3), (50, 30, 20), np.uint8)
                cv2.circle(f, (20 + (i * 9) % 600, 180), 30, (0, 255, 0), -1)
                ok, jb = cv2.imencode(".jpg", f)
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jb) + jb.tobytes() + b"\r\n")
                i += 1
                time.sleep(0.05)
        except Exception:
            pass


class _TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def test_mjpeg_reconnect():
    port = 18765
    srv = _TS(("127.0.0.1", port), _MJPEG)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p = fresh([{"name": "mjpeg", "url": "http://127.0.0.1:%d/s.mjpg" % port}])
    assert wait_live(p), "never connected"
    KILL.set(); srv.shutdown(); srv.server_close()           # kill the stream
    time.sleep(L.STALE + 1.5)
    p(0).save("/tmp/livecam_down.png")
    assert p.src.latest()[2] > L.STALE                        # shows NO SIGNAL
    KILL.clear()
    srv2 = _TS(("127.0.0.1", port), _MJPEG)                   # it comes back
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    t0 = time.time()
    while time.time() - t0 < 20 and p.src.latest()[2] > 2:
        p(0); time.sleep(0.1)
    srv2.shutdown()
    assert p.src.latest()[2] < 3, "did not reconnect"
    p.src.stop()


def test_config_crop():
    x0, y0, x1, y1 = L.crop_box(1920, 1080, {"x": 0.5, "y": 0.5, "zoom": 1}, 0)
    assert y1 - y0 == 1080 and abs((x1 - x0) / (y1 - y0) - 0.75) < 0.01
    x0, y0, x1, y1 = L.crop_box(1920, 1080, {"x": 0.0, "zoom": 3}, 0)
    assert x0 == 0


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
