"""Live cam: a public webcam on the LED wall, reduced to 192x256 and tuned to look good on LEDs.

LEGAL / TERMS OF USE. You must only configure streams you are permitted to use on a display like this one.
Many YouTube and aggregator streams are NOT licensed for rebroadcast on other displays, and this module
neither scrapes sites nor circumvents anything (no yt-dlp, no URL discovery, nothing hardcoded): you supply
the URL and you are responsible for being entitled to it. Sources that are usually fine: your own IP cameras
(RTSP/MJPEG on your network), municipal or transport webcams published under an open licence, and commercial
webcam networks (EarthCam and others) only as their own terms allow. No specific stream is claimed to be
permitted here. See docs/livecam.md.

Sources are listed in panel_setup/livecams.json (git-ignored; copy livecams.example.json) and/or in the
environment variable WALL_LIVECAMS_JSON (JSON text or the path of a JSON file; its entries win by name).
Each cam: name, url, optional x, y (focus 0..1), zoom (1 = full frame height, 2 = twice as close),
pan (slow drift across the frame), label, rotation (0/90/180/270), flip ("h", "v", "hv" or true), led (dither).
A url may be an HLS .m3u8, an MJPEG http stream, an RTSP URL, a local video file (looped), or an image URL
(polled every few seconds). The cam named "test" is a synthetic crossing and needs no network.

Settings (environment): LIVECAM_MINUTES (default 10) is how long each cam stays on before the next;
LIVECAM_NAME=name stays on one cam; LIVECAM_LED=1 turns on the dithered LED mode for every cam.

A side thread (cv2.VideoCapture, FFMPEG backend) reads the stream, reconnects with backoff and keeps only the
latest frame, so frame(t) never waits for the network. With no cams configured, or a stream that is down,
the wall shows a calm held NO SIGNAL card with one slow scanline. The thread stops itself when frame() is
not called for a while.

LED look: crop around the focus to the portrait wall, INTER_AREA downscale, a quiet bilateral step, CLAHE on
luminance, saturation 1.3, gamma and a shadow lift (night scenes stay above the LEDs' dark floor), a mild
unsharp mask, and optionally ordered dithering against the 6-bit banding.
"""
import json
import os
import threading
import time
from urllib.parse import urlparse

import cv2
import numpy as np
from PIL import Image

import config
from display import pixelfont

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
ASPECT = W / H
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_FILE = os.path.join(ROOT, "panel_setup", "livecams.json")
IDLE = 120.0                  # frame() not called for this long: the piece is not showing, stop reading
STALE = 8.0                   # no new frame for this long: show NO SIGNAL
SKIP_AFTER = 45.0             # a cam down this long is skipped when cycling
LABEL_SECS = 10.0
SAT, GAMMA, LIFT = 1.3, 0.85, 0.09
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

cv2.setNumThreads(2)


def _minutes():
    try:
        return max(0.05, float(os.environ.get("LIVECAM_MINUTES", "10")))
    except ValueError:
        return 10.0


# ---------------------------------------------------------------- config

def _norm(c):
    if not isinstance(c, dict) or not c.get("name"):
        return None
    c = dict(c)
    c["name"] = str(c["name"])
    if not c.get("url") and c["name"].lower() != "test":
        return None
    return c


def _parse(obj):
    if isinstance(obj, dict):
        obj = obj.get("cams", [])
    return [n for n in (_norm(c) for c in obj if True) if n] if isinstance(obj, list) else []


def load_cams():
    """The configured cams: file first, then WALL_LIVECAMS_JSON (JSON text or a file path), env wins by name."""
    cams = {}
    srcs = []
    try:
        with open(CFG_FILE) as fh:
            srcs.append(fh.read())
    except Exception:
        pass
    env = os.environ.get("WALL_LIVECAMS_JSON", "").strip()
    if env:
        if env[0] in "[{":
            srcs.append(env)
        else:
            try:
                with open(os.path.expanduser(env)) as fh:
                    srcs.append(fh.read())
            except Exception:
                pass
    for s in srcs:
        try:
            for c in _parse(json.loads(s)):
                cams[c["name"]] = c
        except Exception:
            pass
    return list(cams.values())


# ---------------------------------------------------------------- synthetic test cam

class TestScene:
    """A made-up scramble crossing seen from above at dusk, drawn portrait-native: indigo asphalt, warm pools
    under four street lamps, shopfronts with glowing windows (a few flicker on and off), a soft-white zebra,
    small people streaming across in muted colours (they wait at the kerbs while the cars go) and cars with
    glowing head and tail lights. Pure numpy/cv2, no network. Colours are BGR."""
    SW, SH = 288, 384                                        # drawn at 2x (576 x 768) once, moving parts at 1x

    def __init__(self):
        rng = np.random.default_rng(11)
        w, h = 2 * self.SW, 2 * self.SH
        self.rx0, self.rx1, self.ry0, self.ry1 = 196, 380, 292, 476        # the two roads' edges (2x units)
        rx0, rx1, ry0, ry1 = self.rx0, self.rx1, self.ry0, self.ry1
        yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        bg = np.zeros((h, w, 3), np.float32)
        bg[:] = np.array((82, 42, 30), np.float32) * (0.8 + 0.35 * yy)         # a deep indigo dusk
        bg += rng.normal(0, 1.6, (h, w, 1)).astype(np.float32)                 # asphalt grain
        road = np.zeros((h, w), np.uint8)
        road[:, rx0:rx1] = 1
        road[ry0:ry1, :] = 1
        bg[road > 0] = bg[road > 0] * 0.5 + np.array((46, 26, 18), np.float32) * 0.7
        light = np.zeros((h, w, 3), np.float32)                                # everything that glows
        # pavements and the four blocks
        blocks = [(0, 0, rx0 - 36, ry0 - 36), (rx1 + 36, 0, w, ry0 - 36), (0, ry1 + 36, rx0 - 36, h), (rx1 + 36, ry1 + 36, w, h)]
        self.windows = []
        for (x0, y0, x1, y1) in blocks:
            cv2.rectangle(bg, (x0, y0), (x1, y1), (58, 42, 44), -1)
            cv2.rectangle(bg, (x0, y0), (x1, y1), (86, 62, 60), 2)
            for wy in range(y0 + 16, y1 - 22, 30):
                for wx in range(x0 + 14, x1 - 20, 26):
                    if wx + 14 > w or wy + 18 > h:
                        continue
                    lit = rng.random() < 0.46
                    col = (110, 190, 255) if rng.random() < 0.78 else (255, 215, 150)
                    col = tuple(int(v * rng.uniform(0.65, 1.0)) for v in col)
                    if lit:
                        cv2.rectangle(bg, (wx, wy), (wx + 14, wy + 18), col, -1)
                        cv2.rectangle(light, (wx, wy), (wx + 14, wy + 18), col, -1)
                    else:
                        cv2.rectangle(bg, (wx, wy), (wx + 14, wy + 18), (62, 44, 40), -1)
                    self.windows.append((wx, wy, col, lit, float(rng.uniform(5, 14))))
            sx = int(rng.integers(x0 + 20, max(x0 + 24, x1 - 70)))
            sy = y1 - 10 if y0 > ry1 else y0 + 5                                    # a muted neon on the road side
            ncol = [(170, 190, 60), (190, 90, 210), (80, 150, 255), (200, 170, 60)][int(rng.integers(0, 4))]
            cv2.rectangle(bg, (sx, sy), (sx + 54, sy + 4), ncol, -1)
            cv2.rectangle(light, (sx, sy), (sx + 54, sy + 4), ncol, -1)
        # soft-white zebra on all four arms, thin diagonals for the scramble
        zc = (225, 215, 200)
        for k in range(rx0 + 6, rx1 - 10, 24):
            cv2.rectangle(bg, (k, ry0 - 30), (k + 12, ry0 - 6), zc, -1)
            cv2.rectangle(bg, (k, ry1 + 6), (k + 12, ry1 + 30), zc, -1)
        for k in range(ry0 + 6, ry1 - 10, 24):
            cv2.rectangle(bg, (rx0 - 30, k), (rx0 - 6, k + 12), zc, -1)
            cv2.rectangle(bg, (rx1 + 6, k), (rx1 + 30, k + 12), zc, -1)
        cv2.line(bg, (rx0, ry0), (rx1, ry1), (120, 96, 90), 3)
        cv2.line(bg, (rx1, ry0), (rx0, ry1), (120, 96, 90), 3)
        for (lx, ly) in [(rx0 - 20, ry0 - 20), (rx1 + 20, ry0 - 20), (rx0 - 20, ry1 + 20), (rx1 + 20, ry1 + 20)]:
            cv2.circle(light, (lx, ly), 9, (150, 210, 255), -1)                    # a lamp: its warm pool on the ground
            pool = np.zeros((h, w), np.float32)
            cv2.circle(pool, (lx, ly), 120, 1.0, -1)
            pool = cv2.GaussianBlur(pool, (0, 0), 55)
            bg += pool[:, :, None] * np.array((38, 78, 120), np.float32) * 0.55
        glow = cv2.GaussianBlur(light, (0, 0), 9)
        bg += glow * 0.7 + light * 0.2
        self.bg = cv2.resize(np.clip(bg, 0, 255).astype(np.uint8), (self.SW, self.SH), interpolation=cv2.INTER_AREA)
        self.win = [(wx // 2, wy // 2, col, lit, per) for (wx, wy, col, lit, per) in self.windows]
        n = 280
        self.lane = rng.integers(0, 6, n)                  # 0 E, 1 W, 2 S, 3 N, 4 diagonal, 5 anti-diagonal
        self.p0 = rng.uniform(0, 1, n)
        self.speed = rng.uniform(0.016, 0.034, n)
        self.size = rng.uniform(2.6, 3.8, n)
        pal = np.array([(226, 222, 218), (226, 222, 218), (226, 222, 218), (110, 180, 238), (170, 150, 220),
                        (214, 196, 150), (190, 140, 176)], np.uint8)
        self.col = pal[rng.integers(0, len(pal), n)]
        self.off = rng.uniform(-1, 1, n)
        self.flip = rng.integers(0, 2, n)
        self.flicker = rng.choice(len(self.windows), size=min(14, len(self.windows)), replace=False)

    def render(self, t):
        w, h = self.SW, self.SH
        rx0, rx1, ry0, ry1 = (v // 2 for v in (self.rx0, self.rx1, self.ry0, self.ry1))
        img = self.bg.copy()
        light = np.zeros((h, w, 3), np.uint8)
        for j in self.flicker:                                   # a few windows switch on and off
            wx, wy, col, lit, per = self.win[j]
            on = lit ^ (int(t / per + j) % 2 == 1)
            c = col if on else (62, 44, 40)
            cv2.rectangle(img, (wx, wy), (wx + 6, wy + 8), c, -1)
            if on:
                cv2.rectangle(light, (wx - 1, wy - 1), (wx + 7, wy + 9), tuple(int(v * 0.30) for v in col), -1)
        phase = t % 40.0
        cars_go = phase < 14.0
        if cars_go:                                              # cars along both roads while people wait
            for i in range(6):
                body = [(120, 70, 60), (150, 150, 160), (70, 60, 150), (110, 100, 90), (90, 120, 150), (60, 90, 130)][i]
                if i < 3:
                    east = i % 2 == 0
                    x = (t * 60 + i * 115) % (w + 70) - 35
                    x = int(x if east else w - x)
                    y = (ry0 + 23) if east else (ry1 - 23)
                    cv2.rectangle(img, (x - 10, y - 4), (x + 10, y + 4), body, -1)
                    d = 1 if east else -1
                    for dy in (-3, 3):
                        cv2.circle(light, (x + 11 * d, y + dy), 2, (175, 225, 255), -1)
                        cv2.circle(light, (x - 11 * d, y + dy), 1, (60, 60, 235), -1)
                else:
                    south = i % 2 == 1
                    y = (t * 52 + i * 95) % (h + 70) - 35
                    y = int(y if south else h - y)
                    x = (rx0 + 23) if south else (rx1 - 23)
                    cv2.rectangle(img, (x - 4, y - 10), (x + 4, y + 10), body, -1)
                    d = 1 if south else -1
                    for dx in (-3, 3):
                        cv2.circle(light, (x + dx, y + 11 * d), 2, (175, 225, 255), -1)
                        cv2.circle(light, (x + dx, y - 11 * d), 1, (60, 60, 235), -1)
        tw = (t // 40.0) * 26.0 + max(0.0, phase - 14.0)            # time the lights have been green for people
        for i in range(len(self.lane)):
            L = self.lane[i]
            u = (self.p0[i] + tw * self.speed[i]) % 1.0
            o = self.off[i] * 7.0
            near = self.flip[i]
            if L == 0:   x, y = rx0 - 40 + u * (rx1 - rx0 + 80), (ry0 - 11 if near else ry1 + 11) + o
            elif L == 1: x, y = rx1 + 40 - u * (rx1 - rx0 + 80), (ry1 + 11 if near else ry0 - 11) + o
            elif L == 2: x, y = (rx0 - 11 if near else rx1 + 11) + o, ry0 - 40 + u * (ry1 - ry0 + 80)
            elif L == 3: x, y = (rx1 + 11 if near else rx0 - 11) + o, ry1 + 40 - u * (ry1 - ry0 + 80)
            elif cars_go:
                continue
            elif L == 4: x, y = rx0 + u * (rx1 - rx0) + o * .6, ry0 + u * (ry1 - ry0) + o * .6
            else:        x, y = rx1 - u * (rx1 - rx0) + o * .6, ry0 + u * (ry1 - ry0) - o * .6
            if cars_go and ((L < 2 and rx0 < x < rx1) or (2 <= L < 4 and ry0 < y < ry1)):
                continue                                         # nobody steps into the cars' way
            c = tuple(int(v) for v in self.col[i])
            r = 1 if self.size[i] < 3.2 else 2
            cv2.circle(img, (int(x), int(y)), r, c, -1)
            cv2.circle(light, (int(x), int(y)), r + 1, tuple(int(v * 0.16) for v in c), -1)
        glow = cv2.GaussianBlur(light, (0, 0), 3)
        img = cv2.add(img, cv2.addWeighted(glow, 1.4, light, 0.6, 0))
        return img


# ---------------------------------------------------------------- sources

class Source:
    """One stream read on a side thread. latest() never blocks: (frame BGR or None, seq, age seconds)."""

    def __init__(self, cam):
        self.cam = cam
        self.url = str(cam.get("url", ""))
        self.kind = "test" if cam["name"].lower() == "test" and not self.url else self._kind(self.url)
        self._lock = threading.Lock()
        self._frame, self._seq, self._ts = None, 0, 0.0
        self._stop = threading.Event()
        self._thread = None
        self.born = time.time()
        self._tseq, self._tframe = None, None
        self.scene = TestScene() if self.kind == "test" else None

    @staticmethod
    def _kind(url):
        path = urlparse(url).path.lower()
        if url.lower().startswith(("http://", "https://")) and path.endswith(IMG_EXT):
            return "image"
        return "video"

    def start(self):
        if self.kind == "test" or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="livecam-" + self.cam["name"])
        self._thread.start()

    def stop(self):
        self._stop.set()

    def latest(self, t=None):
        if self.kind == "test":
            now = time.time()
            if t is None:
                t = now
            seq = int(t * 12)                              # the test cam runs at 12 fps
            if self._tseq != seq:
                self._tseq, self._tframe = seq, self.scene.render(t)
            return self._tframe, seq, 0.0
        with self._lock:
            f, seq, ts = self._frame, self._seq, self._ts
        return f, seq, (time.time() - ts) if f is not None else (time.time() - self.born)

    def _put(self, f):
        with self._lock:
            self._frame, self._seq, self._ts = f, self._seq + 1, time.time()

    def _run(self):
        backoff = 1.0
        while not self._stop.is_set():
            try:
                ok = self._poll_images() if self.kind == "image" else self._read_video()
            except Exception:
                ok = False
            if self._stop.is_set():
                break
            backoff = 1.0 if ok else min(60.0, backoff * 2)
            self._stop.wait(backoff)

    def _poll_images(self):
        import requests
        got = False
        while not self._stop.is_set():
            r = requests.get(self.url, timeout=8, headers={"User-Agent": "magic-mirror-livecam"})
            r.raise_for_status()
            f = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
            if f is None:
                return got
            self._put(f)
            got = True
            self._stop.wait(float(self.cam.get("poll", 3.0)))
        return got

    def _read_video(self):
        local = os.path.exists(os.path.expanduser(self.url))
        src = os.path.expanduser(self.url)
        try:
            cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000,
                                                          cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000])
        except Exception:
            cap = cv2.VideoCapture(src)
        got = False
        try:
            if not cap.isOpened():
                return False
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            fps = 25.0 if not (1.0 <= fps <= 120.0) else fps
            nxt = time.time()
            while not self._stop.is_set():
                ok, f = cap.read()
                if not ok or f is None:
                    if local and got:                      # a local file loops
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        got = False
                        ok, f = cap.read()
                        if not ok:
                            return False
                        got = True
                    else:
                        return got
                got = True
                self._put(f)
                if local:                                  # a file is read at its own speed; a stream paces itself
                    nxt += 1.0 / fps
                    d = nxt - time.time()
                    if d > 0:
                        self._stop.wait(d)
                    else:
                        nxt = time.time()
            return got
        finally:
            cap.release()


# ---------------------------------------------------------------- the LED look

_clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(4, 4))
_LUT = np.clip((LIFT + (1 - LIFT) * np.power(np.arange(256) / 255.0, GAMMA)) * 255.0, 0, 255).astype(np.uint8)
_BAYER = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                   [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                   [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], np.float32)
_BAYER = np.tile((_BAYER + 0.5) / 64.0, (H // 8 + 1, W // 8 + 1))[:H, :W, None]


def orient(f, cam):
    rot = int(cam.get("rotation", 0) or 0) % 360
    if rot == 90:
        f = cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE)
    elif rot == 180:
        f = cv2.rotate(f, cv2.ROTATE_180)
    elif rot == 270:
        f = cv2.rotate(f, cv2.ROTATE_90_COUNTERCLOCKWISE)
    fl = cam.get("flip")
    if fl is True:
        fl = "h"
    if fl:
        fl = str(fl).lower()
        f = cv2.flip(f, -1 if ("h" in fl and "v" in fl) else (1 if "h" in fl else 0))
    return f


def crop_box(fw, fh, cam, t):
    """Pixel box (x0, y0, x1, y1) of the portrait crop: focus x, y (0..1), zoom 1 = full height; pan drifts."""
    zoom = max(1.0, float(cam.get("zoom", 1.0) or 1.0))
    ch = fh / zoom
    cw = ch * ASPECT
    if cw > fw:
        cw = float(fw)
        ch = cw / ASPECT
    fx, fy = float(cam.get("x", 0.5)), float(cam.get("y", 0.5))
    cx, cy = fx * fw, fy * fh
    if cam.get("pan"):
        slack = fw - cw
        if slack > 1:
            amp = min(slack / 2, min(cx - cw / 2, fw - cw / 2 - cx) if (cx - cw / 2 >= 0 and cx + cw / 2 <= fw) else slack / 2)
            amp = max(amp, 0.0) if amp > 0 else slack / 2
            cx = (fw / 2 if amp == slack / 2 else cx) + amp * np.sin(t * 2 * np.pi / 90.0)
    x0 = min(max(cx - cw / 2, 0), fw - cw)
    y0 = min(max(cy - ch / 2, 0), fh - ch)
    return int(round(x0)), int(round(y0)), int(round(x0 + cw)), int(round(y0 + ch))


def led_look(f, cam, t=0.0, led=False):
    """Any BGR frame -> HxWx3 uint8 RGB tuned for the wall."""
    f = orient(f, cam)
    x0, y0, x1, y1 = crop_box(f.shape[1], f.shape[0], cam, t)
    crop = f[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    if cw >= 2 * W and ch >= 2 * H:                         # big source: tame the noise at 2x, then area-average down
        big = cv2.resize(crop, (2 * W, 2 * H), interpolation=cv2.INTER_AREA)
        big = cv2.bilateralFilter(big, 5, 26, 5)
        small = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA)
    else:
        interp = cv2.INTER_AREA if cw > W else cv2.INTER_CUBIC
        small = cv2.resize(crop, (W, H), interpolation=interp)
        small = cv2.bilateralFilter(small, 3, 20, 3)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
    L = _clahe.apply(lab[:, :, 0])
    L = cv2.LUT(L, _LUT)                                    # gamma + shadow lift: night stays above the LED floor
    Lf = L.astype(np.float32)
    Lf = np.clip(Lf + 0.6 * (Lf - cv2.GaussianBlur(Lf, (0, 0), 0.9)), 0, 255)
    a = (lab[:, :, 1].astype(np.float32) - 128.0) * SAT + 128.0
    b = (lab[:, :, 2].astype(np.float32) - 128.0) * SAT + 128.0
    lab2 = np.dstack([Lf, np.clip(a, 0, 255), np.clip(b, 0, 255)]).astype(np.uint8)
    rgb = cv2.cvtColor(cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR), cv2.COLOR_BGR2RGB)
    if led:                                                 # ordered dither at the panel's 6 bits
        v = rgb.astype(np.float32) / 4.0
        rgb = np.clip(np.floor(v + _BAYER) * 4.0 + 2.0, 0, 255).astype(np.uint8)
    return rgb


# ---------------------------------------------------------------- cards and label

_NS_YY, _NS_XX = np.mgrid[0:H, 0:W]
_NS_R = np.hypot((_NS_XX - W / 2) / (W / 2), (_NS_YY - H / 2) / (H / 2)).astype(np.float32)
_NS_THR = _BAYER[:, :, 0]
_NS_HASH = ((_NS_XX * 73856093) ^ (_NS_YY * 19349663)) & 0xFFFF


_NS_BASE = None


def _ns_base():
    """The still part of the card, made once: a faint dithered pool of deep blue, fine scanlines, a thin ring."""
    lit = lambda inten, col: np.where(np.clip(inten, 0, 1) > _NS_THR, 1.0, 0.0)[:, :, None] * np.array(col, np.float32)
    centre = np.clip(1.0 - _NS_R, 0, 1)
    img = lit(centre ** 1.6 * 0.26, (32, 52, 108))
    lines = ((_NS_YY % 4) == 0).astype(np.float32) * (0.07 + 0.16 * centre)         # scanlines, strongest mid-card
    img = np.maximum(img, lit(lines, (30, 50, 104)))
    ring = (np.abs(_NS_R * (W / 2) - 40.0) < 0.7) & (((_NS_XX + _NS_YY) % 4) == 0)  # a dotted ring round the words
    img[ring] = np.maximum(img[ring], (40, 66, 128))
    return img


def no_signal(t, name=""):
    """A calm held card, designed for LEDs: black with a faint dithered pool of deep blue, fine scanlines, a
    slow band, a thin dotted ring, a whisper of static, a breathing standby LED and small type. Every lit LED
    keeps a channel above the dark floor; the gradients are ordered dither."""
    global _NS_BASE
    if _NS_BASE is None:
        _NS_BASE = _ns_base()
    img = _NS_BASE.copy()
    y = (t % 18.0) / 18.0 * (H + 30) - 15                                      # the slow band
    band = np.clip(1.0 - np.abs(_NS_YY[:, :1] - y) / 7.0, 0, 1) ** 2 * 0.7
    img = np.maximum(img, np.where(band > _NS_THR, 1.0, 0.0)[:, :, None] * np.array((44, 74, 142), np.float32))
    snow = ((_NS_HASH + int(t * 8) * 40503) % 2003) < 4                         # static, a few LEDs at a time
    img[snow] = np.maximum(img[snow], (56, 86, 154))
    s = "NO SIGNAL"
    wd = pixelfont.width(s)
    x0, y0 = (W - wd) // 2, H // 2 - 3
    img[y0 - 3:y0 + 11, x0 - 4:x0 + wd + 4] = 0.0                               # a clear patch under the words
    pixelfont.draw(img, s, x0, y0, (150, 182, 230))
    img[y0 + 7, x0:x0 + wd] = (44, 72, 136)                                     # a hairline under the title
    if name:
        n = name[:44]
        nw = pixelfont.width(n)
        if nw > wd:
            img[y0 + 9:y0 + 17, (W - nw) // 2 - 3:(W + nw) // 2 + 3] = 0.0
        pixelfont.draw(img, n, (W - nw) // 2, y0 + 11, (92, 118, 164))
    br = 0.5 + 0.5 * np.sin(t * 1.6)                                           # the standby LED, breathing
    if br > 0.3:
        img[y0 - 8, W // 2] = np.array((255, 150, 96), np.float32) * (0.5 + 0.5 * br)
    return np.clip(img, 0, 255).astype(np.uint8)


def add_label(rgb, text, alpha):
    if alpha <= 0.01 or not text:
        return rgb
    text = text[:46]
    img = rgb.astype(np.float32)
    w = pixelfont.width(text)
    x, y = 3, H - 9
    reg = img[y - 2:H, 0:min(W, x + w + 3)]
    reg *= 1.0 - 0.6 * alpha
    pixelfont.draw(img, text, x, y, np.array((235, 235, 225), np.float32) * alpha)
    return np.clip(img, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- the piece

class LiveCam:
    def __init__(self):
        self.cams, self.cfg_check, self.cfg_sig = [], 0.0, None
        self.src, self.src_name = None, None
        self.shown_at = 0.0                    # when the current cam came on: the label fades from here
        self.last_call = 0.0
        self.bump = 0
        self.cache_key, self.cache = None, None
        self.override = None

    def set_cam(self, name):
        """Stay on one cam by name (None: cycle). Also LIVECAM_NAME."""
        self.override = name

    def _reload(self, now):
        if now - self.cfg_check < 30.0 and self.cfg_sig is not None:
            return
        self.cfg_check = now
        sig = json.dumps(load_cams(), sort_keys=True)
        if sig != self.cfg_sig:
            self.cfg_sig = sig
            self.cams = json.loads(sig)

    def _pick(self, now):
        cams = self.cams
        if not cams:
            return None
        want = self.override or os.environ.get("LIVECAM_NAME", "").strip()
        if want:
            for c in cams:
                if c["name"].lower() == want.lower():
                    return c
        slot = int(now // (_minutes() * 60.0))
        return cams[(slot + self.bump) % len(cams)]

    def __call__(self, t):
        now = time.time()
        if now - self.last_call > IDLE:                      # shown again after a break: label again, fresh bump
            self.shown_at, self.bump = now, 0
        self.last_call = now
        try:
            return self._frame(t, now)
        except Exception:
            return Image.fromarray(no_signal(t), "RGB")

    def _frame(self, t, now):
        self._reload(now)
        cam = self._pick(now)
        if cam is None:
            self._drop()
            return Image.fromarray(no_signal(t, "NO CAMS CONFIGURED"), "RGB")
        if self.src is None or self.src_name != cam["name"] or self.src.cam != cam:
            self._drop()
            self.src, self.src_name, self.shown_at = Source(cam), cam["name"], now
        self.src.start()
        f, seq, age = self.src.latest(now)
        live = f is not None and age < STALE
        if not live:
            if len(self.cams) > 1 and not (self.override or os.environ.get("LIVECAM_NAME")) and age > SKIP_AFTER:
                self.bump += 1
            return Image.fromarray(no_signal(t, cam["name"]), "RGB")
        led = bool(cam.get("led")) or os.environ.get("LIVECAM_LED", "") not in ("", "0")
        # re-process only when the picture or (if panning) the crop moved
        key = (cam["name"], seq, led, int(t * 8) if cam.get("pan") else 0)
        if key != self.cache_key:
            self.cache = led_look(f, cam, now, led)
            self.cache_key = key
        alpha = float(np.clip((LABEL_SECS - (now - self.shown_at)) / 1.5, 0, 1))
        out = add_label(self.cache, cam.get("label") or cam["name"], alpha)
        return Image.fromarray(out, "RGB")

    def _drop(self):
        if self.src is not None:
            self.src.stop()
        self.src, self.src_name, self.cache_key = None, None, None


_piece = LiveCam()


def frame(t):
    return _piece(t)


def thumb():
    """A still for the app: the synthetic test crossing through the full LED pipeline, labelled TEST CAM (no network)."""
    cam = {"name": "test", "zoom": 1.0, "x": 0.5, "y": 0.5}
    f = TestScene().render(31.0)
    rgb = led_look(f, cam, 0.0, False)
    return Image.fromarray(add_label(rgb, "TEST CAM", 1.0), "RGB")
