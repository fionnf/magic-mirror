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
    """A made-up scramble crossing seen from above at dusk: crosswalks, lit shopfronts, a dense crowd of dots
    streaming in four directions, and cars that go while the people wait. Pure numpy/cv2, no network."""
    SW, SH = 960, 540

    def __init__(self):
        rng = np.random.default_rng(11)
        w, h = self.SW, self.SH
        bg = np.full((h, w, 3), (20, 19, 24), np.uint8)
        bg[:] += (rng.integers(0, 6, (h, w, 1))).astype(np.uint8)
        cx0, cx1, cy0, cy1 = 250, 710, 130, 410          # the crossing square
        cv2.rectangle(bg, (cx0, 0), (cx1, h), (27, 26, 32), -1)
        cv2.rectangle(bg, (0, cy0), (w, cy1), (27, 26, 32), -1)
        for k in range(0, 460, 28):                      # zebra stripes on all four sides and the diagonals
            cv2.rectangle(bg, (cx0 + k, cy0 - 38), (cx0 + k + 14, cy0 - 6), (150, 150, 150), -1)
            cv2.rectangle(bg, (cx0 + k, cy1 + 6), (cx0 + k + 14, cy1 + 38), (150, 150, 150), -1)
        for k in range(0, 280, 28):
            cv2.rectangle(bg, (cx0 - 38, cy0 + k), (cx0 - 6, cy0 + k + 14), (150, 150, 150), -1)
            cv2.rectangle(bg, (cx1 + 6, cy0 + k), (cx1 + 38, cy0 + k + 14), (150, 150, 150), -1)
        cv2.line(bg, (cx0, cy0), (cx1, cy1), (70, 70, 76), 4)
        cv2.line(bg, (cx1, cy0), (cx0, cy1), (70, 70, 76), 4)
        for (x, y, ww, hh) in [(0, 0, cx0 - 40, cy0 - 40), (cx1 + 40, 0, w - cx1 - 40, cy0 - 40),
                               (0, cy1 + 40, cx0 - 40, h - cy1 - 40), (cx1 + 40, cy1 + 40, w - cx1 - 40, h - cy1 - 40)]:
            cv2.rectangle(bg, (x, y), (x + ww, y + hh), (28, 26, 34), -1)    # building blocks seen from above
            for i in range(int(rng.integers(5, 8))):                         # neon signs along their edges
                col = [(40, 60, 240), (240, 120, 40), (60, 220, 240), (200, 60, 220), (60, 230, 120)][int(rng.integers(0, 5))]
                sx = int(rng.integers(x + 4, x + max(6, ww - 70))); sy = int(rng.integers(y + 4, y + max(6, hh - 40)))
                cv2.rectangle(bg, (sx, sy), (sx + int(rng.integers(30, 70)), sy + int(rng.integers(10, 26))), col, -1)
        glow = cv2.GaussianBlur(bg, (0, 0), 14)
        self.bg = cv2.addWeighted(bg, 1.0, glow, 0.7, 0)
        n = 760
        lane = rng.integers(0, 6, n)                      # 0 E, 1 W, 2 S, 3 N, 4 diag, 5 anti-diag
        self.lane = lane
        self.p0 = np.stack([rng.uniform(0, 1, n), rng.uniform(0, 1, n)], 1)
        self.speed = rng.uniform(0.018, 0.04, n)
        self.size = rng.uniform(3.0, 4.6, n)
        pal = np.array([(235, 235, 235), (60, 70, 220), (230, 150, 60), (60, 190, 235), (190, 80, 200), (90, 220, 120),
                        (40, 40, 45), (150, 150, 160), (60, 60, 200)], np.uint8)
        self.col = pal[rng.integers(0, len(pal), n)]
        self.off = rng.uniform(-1, 1, n)
        self.cross = (cx0, cx1, cy0, cy1)

    def render(self, t):
        w, h = self.SW, self.SH
        cx0, cx1, cy0, cy1 = self.cross
        img = self.bg.copy()
        phase = (t % 40.0)
        cars_go = phase < 12.0
        if cars_go:                                       # cars along the two roads while people wait at the kerbs
            for i in range(7):
                x = int(((t * 150 + i * 190) % (w + 120)) - 60)
                cv2.rectangle(img, (x, cy0 + 56 + (i % 2) * 90), (x + 44, cy0 + 78 + (i % 2) * 90), (200, 200, 205) if i % 3 else (60, 60, 210), -1)
                cv2.circle(img, (x + 44, cy0 + 62 + (i % 2) * 90), 7, (170, 240, 255), -1)
            for i in range(5):
                y = int(((t * 130 + i * 140) % (h + 100)) - 50)
                cv2.rectangle(img, (cx0 + 50 + (i % 2) * 160, y), (cx0 + 72 + (i % 2) * 160, y + 40), (190, 200, 200), -1)
                cv2.circle(img, (cx0 + 61 + (i % 2) * 160, y + 40), 7, (60, 60, 240), -1)
        walk = 0.0 if cars_go else min(1.0, (phase - 12.0) / 3.0)
        for i in range(len(self.lane)):
            L = self.lane[i]
            u = (self.p0[i, 0] + t * self.speed[i]) % 1.0
            o = self.off[i]
            if cars_go and L > 3:
                continue
            if L == 0:   x, y = -40 + u * (w + 80), (cy0 - 22) + o * 30 if i % 2 else (cy1 + 22) + o * 30
            elif L == 1: x, y = w + 40 - u * (w + 80), (cy1 + 22 + o * 30) if i % 2 else (cy0 - 22) + o * 30
            elif L == 2: x, y = ((cx0 - 22) + o * 30) if i % 2 else (cx1 + 22 + o * 30), -40 + u * (h + 80)
            elif L == 3: x, y = ((cx1 + 22) + o * 30) if i % 2 else (cx0 - 22 + o * 30), h + 40 - u * (h + 80)
            elif L == 4: x, y = cx0 + u * (cx1 - cx0) + o * 20, cy0 + u * (cy1 - cy0) + o * 20
            else:        x, y = cx1 - u * (cx1 - cx0) + o * 20, cy0 + u * (cy1 - cy0) - o * 20
            r = float(self.size[i])
            c = tuple(int(v) for v in self.col[i])
            cv2.circle(img, (int(x) + 2, int(y) + 2), int(r + 1), (12, 12, 14), -1)
            cv2.circle(img, (int(x), int(y)), int(r), c, -1)
            if i % 5 == 0:                                # an umbrella now and then
                cv2.circle(img, (int(x), int(y)), int(r * 2.1), tuple(int(v) for v in self.col[(i * 7) % len(self.col)]), -1)
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

def no_signal(t, name=""):
    """A calm held card: deep blue-grey, NO SIGNAL, one slow scanline."""
    img = np.zeros((H, W, 3), np.float32)
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    img[:] = np.array((16, 22, 34), np.float32) * (1.0 - 0.3 * yy)
    y = int((t % 14.0) / 14.0 * (H + 24)) - 12
    for d in range(-9, 10):                                 # a soft band, brightest at its centre line
        if 0 <= y + d < H:
            img[y + d] += np.array((26, 40, 62), np.float32) * (1.0 - abs(d) / 10.0) ** 2
    s = "NO SIGNAL"
    pixelfont.draw(img, s, (W - pixelfont.width(s)) // 2, H // 2 - 3, (120, 150, 190))
    if name:
        n = name[:44]
        pixelfont.draw(img, n, (W - pixelfont.width(n)) // 2, H // 2 + 9, (60, 80, 110))
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
