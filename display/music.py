"""Music-reactive art, chill by default, with an AI VJ.

Audio comes from a network stream (the Mac mic via panel_setup/stream_mic.sh,
raw s16le mono 22050 Hz over UDP) or, later, a USB mic through ALSA:
    WALL_AUDIO=udp:9099 (default)   or   WALL_AUDIO=alsa:plughw:1

Layers
  - analysis (Pi, ~43x/s): bass / mids / treble, energy, gentle beat detection,
    auto-gain, heavy smoothing so the art breathes rather than jumps
  - five calm styles: lava, coral, ink, aurora, ripples; soft palettes
  - AI VJ (every 40 s): 8 s of audio to an audio-capable OpenAI model, which
    names genre + mood and picks the calmest fitting style and palette;
    falls back to a feature-based choice if the API is unavailable
  - silence for a few seconds: drifts into slow dusk lava
"""
import base64
import io
import json
import math
import os
import random
import socket
import subprocess
import threading
import time
import wave

import numpy as np
from PIL import Image, ImageDraw

import config
from display.art import _palette, _lut, Coral

SR = 22050
WIN, HOP = 2048, 512
AI_EVERY = 40.0
AI_CLIP = 8.0
STYLES = ["lava", "coral", "ink", "aurora", "ripples"]
PALETTES = {
    "dusk":   [(15, 8, 30), (80, 30, 90), (220, 120, 120), (255, 200, 150)],
    "ocean":  [(2, 8, 25), (10, 50, 90), (30, 140, 160), (170, 230, 230)],
    "forest": [(4, 14, 8), (20, 70, 40), (90, 160, 90), (210, 240, 190)],
    "moon":   [(6, 8, 18), (40, 50, 80), (130, 150, 190), (230, 235, 250)],
    "blush":  [(18, 6, 16), (90, 30, 70), (230, 130, 170), (255, 220, 230)],
    "ember":  [(10, 3, 2), (80, 20, 10), (200, 80, 30), (255, 180, 90)],
    "gold":   [(8, 5, 0), (70, 45, 10), (200, 150, 60), (255, 235, 170)],
}
AI_PROMPT = (
    "You are the VJ for an LED art wall in the hallway of a cosy flatshare. The vibe of the "
    "space is chill and tranquil. Listen to this clip and choose visuals. Prefer calm, slow, "
    "dreamy looks; for upbeat music pick a warmer, livelier but still gentle look - never "
    f"harsh or strobing. Styles: {', '.join(STYLES)}. Palettes: {', '.join(PALETTES)}. "
    "Reply ONLY with JSON: {\"genre\": str, \"mood\": str (one word), \"energy\": number 0-1, "
    "\"style\": one of the styles, \"palette\": one of the palettes, "
    "\"caption\": max 3 lowercase words}"
)
AI_MODELS = ["gpt-audio", "gpt-4o-audio-preview"]


def _ema(old, new, dt, tau):
    a = 1 - math.exp(-dt / max(tau, 1e-3))
    return old + (new - old) * a


# ------------------------------------------------------------------ audio ---

class Listener:
    """Reads audio into a ring buffer and computes smoothed features."""

    def __init__(self, spec=None):
        spec = spec or os.environ.get("WALL_AUDIO", "udp:9099")
        self.buf = np.zeros(SR * 12, np.float32)          # last 12 s
        self.w = 0
        self.lock = threading.Lock()
        self.last_audio = 0.0
        self.f = {"energy": 0.0, "bass": 0.0, "mid": 0.0, "treble": 0.0,
                  "beat": False, "beat_t": 0.0, "bpm_hint": 0.0, "silent": True}
        self.peak = 1e-3
        self.bpeak = {}
        self.bass_hist = []
        self.beats = []
        kind, _, arg = spec.partition(":")
        target = self._udp if kind == "udp" else self._alsa
        threading.Thread(target=target, args=(arg,), daemon=True).start()
        threading.Thread(target=self._analyse, daemon=True).start()

    def _push(self, samples):
        n = len(samples)
        with self.lock:
            i = self.w % len(self.buf)
            first = min(n, len(self.buf) - i)
            self.buf[i:i + first] = samples[:first]
            self.buf[:n - first] = samples[first:]
            self.w += n
            self.last_audio = time.time()

    def _udp(self, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        s.bind(("0.0.0.0", int(port or 9099)))
        while True:
            data, _ = s.recvfrom(65536)
            if len(data) >= 2:
                self._push(np.frombuffer(data[: len(data) // 2 * 2], "<i2").astype(np.float32)
                           / 32768.0)

    def _alsa(self, dev):
        p = subprocess.Popen(["arecord", "-q", "-D", dev or "default", "-f", "S16_LE", "-r",
                              str(SR), "-c", "1", "-t", "raw"], stdout=subprocess.PIPE)
        while True:
            data = p.stdout.read(HOP * 2)
            if not data:
                time.sleep(1)
                continue
            self._push(np.frombuffer(data, "<i2").astype(np.float32) / 32768.0)

    def recent(self, seconds):
        n = int(SR * seconds)
        with self.lock:
            w = self.w
            idx = (np.arange(w - n, w)) % len(self.buf)
            return self.buf[idx].copy() if w >= n else np.zeros(n, np.float32)

    def _analyse(self):
        win = np.hanning(WIN).astype(np.float32)
        freqs = np.fft.rfftfreq(WIN, 1 / SR)
        bands = {"bass": (freqs >= 35) & (freqs < 160), "mid": (freqs >= 160) & (freqs < 2000),
                 "treble": (freqs >= 2000) & (freqs < 8000)}
        last = time.time()
        while True:
            time.sleep(HOP / SR)
            now = time.time()
            dt, last = now - last, now
            x = self.recent(WIN / SR)
            spec = np.abs(np.fft.rfft(x * win))
            rms = float(np.sqrt(np.mean(x * x)))
            raw = {k: float(spec[m].mean()) for k, m in bands.items()}
            self.peak = max(self.peak * (1 - 0.15 * dt), rms, 1e-3)      # slow auto-gain
            for k, v in raw.items():                                      # per-band auto-gain
                self.bpeak[k] = max(self.bpeak.get(k, 1e-6) * (1 - 0.15 * dt), v, 1e-6)
            silent = rms < 0.004 or now - self.last_audio > 1.5
            f = self.f
            norm = lambda k: min(1.0, raw[k] / self.bpeak[k])
            f["energy"] = _ema(f["energy"], 0 if silent else min(1.0, rms / self.peak), dt, 1.6)
            f["bass"] = _ema(f["bass"], 0 if silent else norm("bass"), dt, 0.35)
            f["mid"] = _ema(f["mid"], 0 if silent else norm("mid"), dt, 0.8)
            f["treble"] = _ema(f["treble"], 0 if silent else norm("treble"), dt, 0.8)
            # gentle beat detection: bass well above its recent average, refractory 0.35 s
            self.bass_hist = (self.bass_hist + [raw["bass"]])[-43:]
            avg = sum(self.bass_hist) / len(self.bass_hist)
            beat = (not silent and raw["bass"] > avg * 1.45 and raw["bass"] > self.bpeak["bass"] * 0.35
                    and now - f["beat_t"] > 0.35)
            if beat:
                f["beat_t"] = now
                self.beats = [b for b in self.beats if now - b < 8] + [now]
                if len(self.beats) > 3:
                    f["bpm_hint"] = 60 * (len(self.beats) - 1) / (self.beats[-1] - self.beats[0])
            f["beat"] = beat or f["beat"]
            f["silent"] = silent


# --------------------------------------------------------------- AI VJ ---

class VJ:
    def __init__(self, listener):
        self.l = listener
        self.choice = {"style": "lava", "palette": "dusk", "caption": "", "mood": "", "genre": ""}
        self.changed = 0.0
        self.source = "default"
        threading.Thread(target=self._loop, daemon=True).start()

    def _wav_b64(self, x):
        pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm)
        return base64.b64encode(b.getvalue()).decode()

    def _ask_ai(self, clip):
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     ".env"))
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=30)
        except Exception as e:
            print(f"[VJ] no AI client: {e}")
            return None
        b64 = self._wav_b64(clip)
        for model in AI_MODELS:
            try:
                r = client.chat.completions.create(
                    model=model, modalities=["text"], max_tokens=200,
                    messages=[
                        {"role": "system", "content": AI_PROMPT},
                        {"role": "user", "content": [
                            {"type": "text", "text": "Here is an 8-second clip of what is playing "
                                                     "in the hallway right now. Reply with the "
                                                     "JSON only."},
                            {"type": "input_audio",
                             "input_audio": {"data": b64, "format": "wav"}}]}])
                txt = r.choices[0].message.content or ""
                if "{" not in txt:
                    print(f"[VJ] {model} replied without JSON: {txt[:160]!r}", flush=True)
                    continue
                j = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
                if j.get("style") in STYLES and j.get("palette") in PALETTES:
                    j["model"] = model
                    return j
            except Exception as e:
                print(f"[VJ] {model}: {str(e)[:120]}")
        return None

    def _fallback(self):
        f = self.l.f
        e, bpm = f["energy"], f["bpm_hint"]
        if e < 0.25:
            style, pal = random.choice([("lava", "dusk"), ("coral", "ocean"), ("ink", "moon")])
        elif bpm > 110 or e > 0.6:
            style, pal = random.choice([("ripples", "ember"), ("aurora", "blush"), ("lava", "gold")])
        else:
            style, pal = random.choice([("aurora", "forest"), ("ink", "ocean"), ("coral", "blush")])
        return {"style": style, "palette": pal, "caption": "", "mood": "", "genre": ""}

    def _loop(self):
        time.sleep(10)
        while True:
            clip = self.l.recent(AI_CLIP)
            level = float(np.sqrt(np.mean(clip * clip)))
            if not self.l.f["silent"] and time.time() - self.l.last_audio < 2 and level > 0.003:
                # normalise the clip so quiet rooms still give the model something to hear
                j = self._ask_ai(clip * min(8.0, 0.25 / max(level, 1e-4)))
                if j:
                    self.source = j.get("model", "ai")
                    print(f"[VJ] {j.get('genre')} / {j.get('mood')} / energy {j.get('energy')} "
                          f"-> {j['style']} + {j['palette']}  \"{j.get('caption', '')}\"", flush=True)
                else:
                    j = self._fallback()
                    self.source = "fallback"
                    print(f"[VJ] fallback -> {j['style']} + {j['palette']}", flush=True)
                if (j["style"], j["palette"]) != (self.choice["style"], self.choice["palette"]):
                    self.choice, self.changed = j, time.time()
                else:
                    self.choice.update({k: j.get(k, "") for k in ("caption", "mood", "genre")})
            time.sleep(AI_EVERY)


# ------------------------------------------------------------- visuals ---

class Visuals:
    def __init__(self, W, H):
        self.W, self.H = W, H
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        self.x, self.y = x, y
        self.phase = 0.0
        self.coral = Coral(W, H)
        rs = np.random.default_rng(2)
        self.ink_p = rs.random((600, 2)).astype(np.float32) * [W, H]
        self.ink_acc = np.zeros((H, W), np.float32)
        self.ripples = []

    def step(self, f, dt):
        speed = 0.45 + 0.9 * f["energy"]
        self.phase += dt * speed
        if f["beat"]:
            rs = random.random
            self.ripples.append([rs() * self.W, rs() * self.H * 0.9, time.time()])
            self.ripples = self.ripples[-12:]

    def lava(self, f, lut):
        p, W, H = self.phase, self.W, self.H
        fld = np.zeros((H, W), np.float32)
        swell = 1 + 0.35 * f["bass"]
        for i in range(6):
            s = 0.11 + i * 0.025
            cx = W * (0.5 + 0.33 * math.sin(p * s * 3 + i * 1.7))
            cy = H * (0.5 + 0.38 * math.sin(p * s * 2.4 + i * 2.9))
            r = ((14 + 5 * math.sin(p * 0.4 + i)) * swell) ** 2
            fld += r / ((self.x - cx) ** 2 + (self.y - cy) ** 2 + 1.0)
        v = np.clip((fld - 0.35) / 1.6, 0, 1) ** 0.8
        return _lut(v, lut)

    def coral_(self, f, lut, dt, beat):
        c = self.coral
        if beat:                                           # a beat plants new growth
            h, w = c.B.shape
            cy, cx = random.randrange(4, h - 4), random.randrange(4, w - 4)
            c.B[cy - 2:cy + 2, cx - 2:cx + 2] = 0.9
        steps = max(1, int(round(dt * (50 + 150 * f["energy"]))))
        F, k = 0.0545, 0.062
        for _ in range(steps):
            AB2 = c.A * c.B * c.B
            c.A += 0.2 * Coral._lap(c.A) - AB2 + F * (1 - c.A)
            c.B += 0.1 * Coral._lap(c.B) + AB2 - (k + F) * c.B
            np.clip(c.A, 0, 1, out=c.A)
            np.clip(c.B, 0, 1, out=c.B)
        img = _lut(np.clip(c.B * 2.6, 0, 1), lut)
        return np.repeat(np.repeat(img, c.s, 0), c.s, 1)[:self.H, :self.W]

    def ink(self, f, lut, dt):
        W, H, p = self.W, self.H, self.phase
        x, y = self.ink_p[:, 0], self.ink_p[:, 1]
        a1, b1 = 0.028, 0.023
        dpx = a1 * np.cos(x * a1 + p * 0.3) * np.cos(y * b1 - p * 0.25)
        dpy = -b1 * np.sin(x * a1 + p * 0.3) * np.sin(y * b1 - p * 0.25)
        vx, vy = dpy, -dpx
        n = np.sqrt(vx * vx + vy * vy) + 1e-6
        step = (8 + 22 * f["energy"]) * dt
        self.ink_p[:, 0] = (x + vx / n * step) % W
        self.ink_p[:, 1] = (y + vy / n * step) % H
        self.ink_acc *= 0.985 ** (dt * 25)
        np.add.at(self.ink_acc, (self.ink_p[:, 1].astype(int), self.ink_p[:, 0].astype(int)),
                  0.12 + 0.2 * f["treble"])
        return _lut(1 - np.exp(-self.ink_acc * 1.2), lut)

    def aurora(self, f, lut):
        p, W, H = self.phase, self.W, self.H
        out = np.zeros((H, W), np.float32)
        for k in range(3):
            band = (H * (0.3 + 0.15 * k) + np.sin(self.x / (24 - 4 * k) + p * (0.8 + k * 0.3)) *
                    (8 + 14 * f["bass"]) + np.sin(self.x / 9 - p * 1.3 + k) * 3)
            width = 90 + 140 * f["mid"]
            out += np.exp(-((self.y - band) ** 2) / width) * (0.45 + 0.4 * f["energy"]) * \
                (0.6 + 0.4 * np.sin(self.x / 14 + p * 2 + k))
        rs = np.random.default_rng(int(p * 4))
        stars = rs.random((H, W)) > 0.997
        out[stars] = np.maximum(out[stars], 0.5)
        return _lut(np.clip(out, 0, 1), lut)

    def ripples_(self, f, lut):
        W, H, now = self.W, self.H, time.time()
        v = 0.12 + 0.05 * np.sin(self.x / 11 + self.phase * 2) * np.sin(self.y / 13 - self.phase)
        for cx, cy, t0 in self.ripples:
            age = now - t0
            if age > 6:
                continue
            r = age * 26
            d = np.sqrt((self.x - cx) ** 2 + (self.y - cy) ** 2)
            v = v + np.exp(-((d - r) ** 2) / 10) * (1 - age / 6) * 0.7
        return _lut(np.clip(v, 0, 1), lut)

    def render(self, style, f, lut, dt, beat):
        if style == "coral":
            return self.coral_(f, lut, dt, beat)
        if style == "ink":
            return self.ink(f, lut, dt)
        if style == "aurora":
            return self.aurora(f, lut)
        if style == "ripples":
            return self.ripples_(f, lut)
        return self.lava(f, lut)


# ---------------------------------------------------------------- show ---

class MusicShow:
    XFADE = 3.0

    def __init__(self):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        self.W, self.H = W, H
        self.l = Listener()
        self.vj = VJ(self.l)
        self.vis = Visuals(W, H)
        self.luts = {k: _palette(v) for k, v in PALETTES.items()}
        self.prev = None
        self.cur = ("lava", "dusk")
        self.switched = 0.0
        self.last_t = None
        self.silent_since = None

    def _target(self):
        f = self.l.f
        now = time.time()
        if f["silent"]:
            self.silent_since = self.silent_since or now
            if now - self.silent_since > 5:
                return ("lava", "dusk")                   # quiet room: slow dusk lava
        else:
            self.silent_since = None
        return (self.vj.choice["style"], self.vj.choice["palette"])

    def __call__(self, t):
        dt = 0.033 if self.last_t is None else max(0.0, min(0.2, t - self.last_t))
        self.last_t = t
        f = dict(self.l.f)
        beat = f["beat"]
        self.l.f["beat"] = False
        self.vis.step(f, dt)
        tgt = self._target()
        if tgt != self.cur:
            self.prev, self.cur, self.switched = self.cur, tgt, time.time()
        img = self.vis.render(self.cur[0], f, self.luts[self.cur[1]], dt, beat)
        k = (time.time() - self.switched) / self.XFADE
        if self.prev and k < 1:
            old = self.vis.render(self.prev[0], f, self.luts[self.prev[1]], dt, False)
            k = k * k * (3 - 2 * k)
            img = old * (1 - k) + img * k
        out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
        cap = self.vj.choice.get("caption") or ""
        age = time.time() - self.vj.changed
        if cap and age < 8 and not f["silent"]:
            a = min(1.0, age / 1.0, (8 - age) / 1.5)
            d = ImageDraw.Draw(out)
            from display.maeva_story import _text
            col = tuple(int(c * a) for c in (235, 230, 220))
            _text(d, (6, self.H - 14), f"♪ {cap}", 10, col, stroke=1)
        return out


_show = None


def frame(t):
    global _show
    if _show is None:
        _show = MusicShow()
    return _show(t)
