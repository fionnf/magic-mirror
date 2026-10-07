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
WIN, HOP = 1024, 256
AI_EVERY = 30.0
AI_CLIP = 10.0
STYLES = ["glow", "aurora", "lava", "ripples", "coral", "ink"]
PALETTES = {
    "dusk":   [(15, 8, 30), (80, 30, 90), (220, 120, 120), (255, 200, 150)],
    "ocean":  [(2, 8, 25), (10, 50, 90), (30, 140, 160), (170, 230, 230)],
    "forest": [(4, 14, 8), (20, 70, 40), (90, 160, 90), (210, 240, 190)],
    "moon":   [(6, 8, 18), (40, 50, 80), (130, 150, 190), (230, 235, 250)],
    "blush":  [(18, 6, 16), (90, 30, 70), (230, 130, 170), (255, 220, 230)],
    "ember":  [(10, 3, 2), (80, 20, 10), (200, 80, 30), (255, 180, 90)],
    "gold":   [(8, 5, 0), (70, 45, 10), (200, 150, 60), (255, 235, 170)],
}
VIBES = {"chill": ("chill and tranquil", 1.0), "dreamy": ("dreamy and floaty", 0.75),
         "warm": ("warm and cosy", 1.0), "lively": ("lively but still gentle", 1.4)}
AI_PROMPT = (
    "You are the resident VJ and light designer of an LED art wall in the hallway of House "
    "Fortuna, a cosy gay flatshare in Zürich. The vibe of the space is chill and tranquil and the "
    "residents love SOFT GLOWS most. Each time you hear a clip you design a complete light scene "
    "for the wall: never harsh, never strobing, always soft and beautiful. "
    f"Base styles: {', '.join(STYLES)} (prefer glow, aurora, lava). Optionally add ONE second "
    "layer on top for depth (glow, aurora or ripples - or none) with opacity 0-0.6. "
    f"Colours: either a preset ({', '.join(PALETTES)}) or invent your own palette of 4 hex colours "
    "from deep shadow to soft highlight that matches the music. "
    "Also set vibe (" + ", ".join(VIBES) + "), drift speed 0.5-1.5, shape size 0.7-1.4, number of "
    "shapes 3-8 and softness 0.7 (crisper) - 1.5 (dreamier). "
    "Let the scenes evolve as a coherent set over the evening - vary them but let them belong "
    "together - and match the music's mood and energy. "
    "If - and only if - you genuinely recognise the song, name it and its artist and let the song "
    "itself inspire the scene (its mood, its era, its artwork); never guess. "
    "Reply ONLY with JSON: {\"song\": \"title\" or null, \"artist\": \"name\" or null, "
    "\"scene\": short evocative name, \"genre\": str, \"mood\": one word, "
    "\"energy\": 0-1, \"style\": base style, \"layer\": style or \"none\", "
    "\"layer_opacity\": number, \"palette\": preset name or \"custom\", "
    "\"colors\": [4 hex strings, when custom], \"vibe\": str, \"speed\": number, "
    "\"scale\": number, \"count\": integer, \"softness\": number}"
)
LAYERS = ("glow", "aurora", "ripples")
DEFAULT_CHOICE = {"scene": "", "genre": "", "mood": "", "song": "", "artist": "", "style": "glow", "layer": "none",
                  "layer_opacity": 0.0, "palkey": "dusk", "palette_desc": "dusk",
                  "vibe": "chill", "speed": 1.0, "scale": 1.0, "count": 6, "softness": 1.0}


def _hex_rgb(h):
    h = str(h).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _soften(cols):
    """Keep an AI palette soft: darkest stays a deep shadow, brightest a soft highlight."""
    lum = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    cols = sorted(cols, key=lum)
    d = cols[0]
    if lum(d) > 45:
        k = 45 / lum(d)
        cols[0] = tuple(int(v * k) for v in d)
    b = cols[-1]
    if lum(b) < 140 and lum(b) > 0:
        k = min(255 / max(b), 140 / lum(b))
        cols[-1] = tuple(min(255, int(v * k)) for v in b)
    return cols


def _validate(j):
    """Clamp an AI scene to safe values; None if unusable."""
    if not isinstance(j, dict) or j.get("style") not in STYLES:
        return None
    num = lambda v, lo, hi, d: max(lo, min(hi, float(v))) if isinstance(v, (int, float)) else d
    out = dict(DEFAULT_CHOICE)
    out.update({k: str(j.get(k, ""))[:40] for k in ("scene", "genre", "mood")})
    for k in ("song", "artist"):                      # only when the AI really recognised it
        v = j.get(k)
        out[k] = str(v)[:60] if v and str(v).strip().lower() not in ("null", "none", "unknown", "") else ""
    out["style"] = j["style"]
    layer = j.get("layer", "none")
    out["layer"] = layer if layer in LAYERS and layer != j["style"] else "none"
    out["layer_opacity"] = num(j.get("layer_opacity"), 0.0, 0.6, 0.3) if out["layer"] != "none" else 0.0
    pal = j.get("palette")
    if pal in PALETTES:
        out["palkey"] = out["palette_desc"] = pal
    else:
        try:
            cols = _soften([_hex_rgb(c) for c in j.get("colors", [])][:4])
            if len(cols) != 4:
                raise ValueError
            out["palkey"] = "custom:" + ",".join("%02x%02x%02x" % c for c in cols)
            out["palette_desc"] = "custom " + " ".join("#%02x%02x%02x" % c for c in cols)
        except Exception:
            out["palkey"] = out["palette_desc"] = "dusk"
    out["vibe"] = j.get("vibe") if j.get("vibe") in VIBES else "chill"
    out["speed"] = num(j.get("speed"), 0.5, 1.5, 1.0)
    out["scale"] = num(j.get("scale"), 0.7, 1.4, 1.0)
    out["count"] = num(j.get("count"), 3, 8, 6)
    out["softness"] = num(j.get("softness"), 0.7, 1.5, 1.0)
    out["scene"] = out["scene"] or out["mood"] or "untitled"
    return out


def _scene_key(c):
    return (c["style"], c["palkey"], c["layer"])


AI_MODELS = ["gpt-audio"]
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(_HERE, "panel_setup", "music_settings.json")   # written by the app
NOW_FILE = os.path.join(_HERE, "panel_setup", "music_now.json")             # read by the app
DEFAULT_SETTINGS = {"style": "auto", "palette": "auto", "vibe": "auto", "source": "mac",
                    "sensitivity": 50}


def load_settings():
    try:
        with open(SETTINGS_FILE) as fh:
            s = {**DEFAULT_SETTINGS, **json.load(fh)}
    except Exception:
        s = dict(DEFAULT_SETTINGS)
    if s["style"] != "auto" and s["style"] not in STYLES:
        s["style"] = "auto"
    if s["palette"] != "auto" and s["palette"] not in PALETTES:
        s["palette"] = "auto"
    if s["vibe"] != "auto" and s["vibe"] not in VIBES:
        s["vibe"] = "auto"
    if s["source"] not in ("mac", "pi"):
        s["source"] = "mac"
    try:
        s["sensitivity"] = max(0, min(100, int(s["sensitivity"])))
    except (TypeError, ValueError):
        s["sensitivity"] = 50
    return s


def reactivity(sensitivity):
    """Slider 0..100 -> reaction strength 0.3..2.0 (50 = 1.0, the tuned default)."""
    v = max(0, min(100, sensitivity)) / 50.0 - 1.0
    return 2.0 ** (v * (1.0 if v > 0 else 1.74))


def find_pi_mic():
    """First ALSA capture device (USB sound card / USB mic) as 'plughw:N,0', or None."""
    try:
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if line.startswith("card ") and "device" in line:
            try:
                card = int(line.split()[1].rstrip(":"))
                dev = int(line.split("device")[1].split(":")[0])
                return f"plughw:{card},{dev}"
            except (ValueError, IndexError):
                continue
    return None


def _write_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except Exception:
        pass


def _ema(old, new, dt, tau):
    a = 1 - math.exp(-dt / max(tau, 1e-3))
    return old + (new - old) * a


# ------------------------------------------------------------------ audio ---

class Listener:
    """Reads audio into a ring buffer and computes smoothed features."""

    def __init__(self, spec=None):
        self.error = ""
        self.react = 1.0
        if spec is None:
            spec = os.environ.get("WALL_AUDIO")
        if spec is None:
            if load_settings()["source"] == "pi":
                dev = find_pi_mic()
                spec = f"alsa:{dev}" if dev else "none:"
                if not dev:
                    self.error = "no microphone found on the Pi (needs a USB sound card or USB mic)"
            else:
                spec = "udp:9099"
        self.spec = spec
        self.buf = np.zeros(SR * 12, np.float32)          # last 12 s
        self.w = 0
        self.lock = threading.Lock()
        self.last_audio = 0.0
        self.f = {"energy": 0.0, "bass": 0.0, "kick": 0.0, "mid": 0.0, "treble": 0.0,
                  "beat": False, "beat_t": 0.0, "bpm_hint": 0.0, "silent": True}
        self.peak = 1e-3
        self.bpeak = {}
        self.bass_hist = []
        self.beats = []
        kind, _, arg = spec.partition(":")
        if kind in ("udp", "alsa"):
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
        while True:
            p = subprocess.Popen(["arecord", "-q", "-D", dev or "default", "-f", "S16_LE", "-r",
                                  str(SR), "-c", "1", "-t", "raw"], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            while True:
                data = p.stdout.read(HOP * 2)
                if not data:
                    break
                self.error = ""
                self._push(np.frombuffer(data, "<i2").astype(np.float32) / 32768.0)
            err = (p.stderr.read() or b"").decode(errors="replace").strip()
            self.error = f"Pi microphone stopped: {err[:120]}" if err else "Pi microphone stopped"
            time.sleep(2)

    def recent(self, seconds):
        n = int(SR * seconds)
        with self.lock:
            w = self.w
            idx = (np.arange(w - n, w)) % len(self.buf)
            return self.buf[idx].copy() if w >= n else np.zeros(n, np.float32)

    def _analyse(self):
        win = np.hanning(WIN).astype(np.float32)
        freqs = np.fft.rfftfreq(WIN, 1 / SR)
        bands = {"kickband": (freqs >= 40) & (freqs < 120),
                 "bass": (freqs >= 35) & (freqs < 160), "mid": (freqs >= 160) & (freqs < 2000),
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
            silent = rms < 0.004 / self.react or now - self.last_audio > 1.5
            f = self.f
            norm = lambda k: min(1.0, raw[k] / self.bpeak[k])
            f["energy"] = _ema(f["energy"], 0 if silent else min(1.0, rms / self.peak), dt, 2.0)
            f["bass"] = _ema(f["bass"], 0 if silent else norm("bass"), dt, 0.12)
            kin = 0.0 if silent else norm("kickband") ** 1.2
            k0 = f.get("kick", 0.0)
            f["kick"] = _ema(k0, kin, dt, 0.09 if kin > k0 else 0.6)     # ease in, slow fade
            f["mid"] = _ema(f["mid"], 0 if silent else norm("mid"), dt, 0.25)
            f["treble"] = _ema(f["treble"], 0 if silent else norm("treble"), dt, 0.25)
            # gentle beat detection: bass well above its recent average, refractory 0.35 s
            self.bass_hist = (self.bass_hist + [raw["kickband"]])[-86:]
            avg = sum(self.bass_hist) / len(self.bass_hist)
            beat = (not silent and raw["kickband"] > avg * 1.3
                    and raw["kickband"] > self.bpeak["kickband"] * 0.3
                    and now - f["beat_t"] > 0.22)
            if beat:
                f["beat_t"] = now
                self.beats = [b for b in self.beats if now - b < 8] + [now]
                if len(self.beats) > 3:
                    f["bpm_hint"] = 60 * (len(self.beats) - 1) / (self.beats[-1] - self.beats[0])
            f["beat"] = beat or f["beat"]
            f["silent"] = silent


# --------------------------------------------------------------- AI VJ ---

class VJ:
    """The AI light designer: listens every AI_EVERY s and designs a whole scene."""

    def __init__(self, listener, vibe=lambda: "chill"):
        self.l = listener
        self.vibe = vibe
        self.choice = dict(DEFAULT_CHOICE)
        self.history = []
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

    def _context(self):
        lt = time.localtime()
        h = lt.tm_hour
        part = ("night" if h < 6 or h >= 22 else "morning" if h < 11 else
                "afternoon" if h < 17 else "evening")
        f = self.l.f
        hist = "; ".join(f"\"{s['scene']}\" ({s['style']}"
                         + (f" + {s['layer']}" if s["layer"] != "none" else "")
                         + f", {s['palette']})" for s in self.history[-4:]) or "none yet"
        return (f"Here is a {AI_CLIP:.0f}-second clip of what is playing in the hallway now. "
                f"Local time {lt.tm_hour:02d}:{lt.tm_min:02d} ({part}). Measured energy "
                f"{f['energy']:.2f}, tempo roughly {f['bpm_hint']:.0f} bpm. Your recent scenes: "
                f"{hist}. Design the next scene. Reply with the JSON only.")

    def _ask_ai(self, clip):
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(_HERE, ".env"))
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=40)
        except Exception as e:
            print(f"[VJ] no AI client: {e}")
            return None
        b64 = self._wav_b64(clip)
        vibe = self.vibe()
        system = AI_PROMPT.replace("chill and tranquil",
                                   VIBES[vibe][0] if vibe in VIBES
                                   else "chill and tranquil by default (you pick the vibe)")
        for model in AI_MODELS:
            try:
                r = client.chat.completions.create(
                    model=model, modalities=["text"], max_tokens=350,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": [
                                  {"type": "text", "text": self._context()},
                                  {"type": "input_audio",
                                   "input_audio": {"data": b64, "format": "wav"}}]}])
                txt = r.choices[0].message.content or ""
                if "{" not in txt:
                    print(f"[VJ] {model} replied without JSON: {txt[:160]!r}", flush=True)
                    continue
                j = _validate(json.loads(txt[txt.index("{"): txt.rindex("}") + 1]))
                if j:
                    j["model"] = model
                    return j
            except Exception as e:
                print(f"[VJ] {model}: {str(e)[:120]}")
        return None

    def _fallback(self):
        f = self.l.f
        e = f["energy"]
        style, pal = random.choice([("glow", "dusk"), ("aurora", "ocean"), ("lava", "ember")]
                                   if e < 0.5 else
                                   [("glow", "blush"), ("aurora", "forest"), ("ripples", "gold")])
        return _validate({"scene": "", "style": style, "palette": pal, "layer": "none"})

    def _loop(self):
        time.sleep(8)
        while True:
            clip = self.l.recent(AI_CLIP)
            level = float(np.sqrt(np.mean(clip * clip)))
            if not self.l.f["silent"] and time.time() - self.l.last_audio < 2 and level > 0.003:
                # normalise the clip so quiet rooms still give the model something to hear
                j = self._ask_ai(clip * min(8.0, 0.25 / max(level, 1e-4)))
                if j:
                    self.source = j.get("model", "ai")
                    if j.get("song"):
                        print(f"[VJ] song: {j['song']} - {j.get('artist') or '?'}", flush=True)
                    print(f"[VJ] \"{j['scene']}\" - {j.get('genre')} / {j.get('mood')}: "
                          f"{j['style']}" + (f" + {j['layer']} {j['layer_opacity']:.0%}"
                                             if j["layer"] != "none" else "")
                          + f", {j['palette_desc']}, {j['vibe']}, speed {j['speed']:.2f}, size "
                          f"{j['scale']:.2f}, {int(j['count'])} shapes, soft {j['softness']:.2f}",
                          flush=True)
                    self.history = (self.history + [{"scene": j["scene"], "style": j["style"],
                                                     "layer": j["layer"],
                                                     "palette": j["palette_desc"]}])[-6:]
                else:
                    j = self._fallback()
                    self.source = "fallback"
                    print(f"[VJ] fallback -> {j['style']} + {j['palkey']}", flush=True)
                if _scene_key(j) != _scene_key(self.choice):
                    self.choice, self.changed = j, time.time()
                else:
                    self.choice.update({k: v for k, v in j.items()
                                        if k not in ("style", "palkey", "layer")})
                self.choice["song"], self.choice["artist"] = j.get("song", ""), j.get("artist", "")
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
        # drift speed follows the music only slowly - no speeding up on every bass note
        target = (0.35 + 0.6 * f["energy"]) * f.get("vibe_speed", 1.0) * f.get("d_speed", 1.0)
        self.speed = _ema(getattr(self, "speed", target), target, dt, 3.0)
        self.phase += dt * self.speed
        if f["beat"] and (not self.ripples or time.time() - self.ripples[-1][2] > 1.2):
            rs = random.random
            self.ripples.append([rs() * self.W, rs() * self.H * 0.9, time.time()])
            self.ripples = self.ripples[-16:]

    def lava(self, f, lut):
        p, W, H = self.phase, self.W, self.H
        fld = np.zeros((H, W), np.float32)
        swell = (1 + 0.45 * f["kick"]) * f.get("d_scale", 1.0)
        n = f.get("d_count", 6.0)
        for i in range(8):
            w = max(0.0, min(1.0, n - i))
            if w <= 0:
                continue
            s = 0.11 + i * 0.025
            cx = W * (0.5 + 0.33 * math.sin(p * s * 3 + i * 1.7))
            cy = H * (0.5 + 0.38 * math.sin(p * s * 2.4 + i * 2.9))
            r = ((14 + 5 * math.sin(p * 0.4 + i)) * swell) ** 2
            fld += w * r / ((self.x - cx) ** 2 + (self.y - cy) ** 2 + 1.0)
        v = np.clip((fld - 0.35) / 1.6, 0, 1) ** 0.8
        return _lut(v, lut)

    def coral_(self, f, lut, dt, beat):
        c = self.coral
        if beat:                                           # a beat plants new growth
            h, w = c.B.shape
            cy, cx = random.randrange(4, h - 4), random.randrange(4, w - 4)
            c.B[cy - 4:cy + 4, cx - 4:cx + 4] = 1.0
        steps = max(1, int(round(dt * (50 + 90 * f["energy"] + 40 * f["kick"]))))
        F, k = 0.0545, 0.062
        for _ in range(steps):
            AB2 = c.A * c.B * c.B
            c.A += 0.2 * Coral._lap(c.A) - AB2 + F * (1 - c.A)
            c.B += 0.1 * Coral._lap(c.B) + AB2 - (k + F) * c.B
            np.clip(c.A, 0, 1, out=c.A)
            np.clip(c.B, 0, 1, out=c.B)
        img = _lut(np.clip(c.B * 2.6, 0, 1), lut) * (0.85 + 0.3 * f["kick"])  # breathes with bass
        return np.repeat(np.repeat(img, c.s, 0), c.s, 1)[:self.H, :self.W]

    def ink(self, f, lut, dt):
        W, H, p = self.W, self.H, self.phase
        x, y = self.ink_p[:, 0], self.ink_p[:, 1]
        a1, b1 = 0.028, 0.023
        dpx = a1 * np.cos(x * a1 + p * 0.3) * np.cos(y * b1 - p * 0.25)
        dpy = -b1 * np.sin(x * a1 + p * 0.3) * np.sin(y * b1 - p * 0.25)
        vx, vy = dpy, -dpx
        n = np.sqrt(vx * vx + vy * vy) + 1e-6
        step = (8 + 16 * f["energy"] + 8 * f["kick"]) * dt
        self.ink_p[:, 0] = (x + vx / n * step) % W
        self.ink_p[:, 1] = (y + vy / n * step) % H
        self.ink_acc *= 0.985 ** (dt * 25)
        np.add.at(self.ink_acc, (self.ink_p[:, 1].astype(int), self.ink_p[:, 0].astype(int)),
                  0.12 + 0.35 * f["treble"] + 0.3 * f["kick"])
        return _lut(1 - np.exp(-self.ink_acc * 1.2), lut)

    def aurora(self, f, lut):
        p, W, H = self.phase, self.W, self.H
        out = np.zeros((H, W), np.float32)
        for k in range(3):
            band = (H * (0.3 + 0.15 * k) + np.sin(self.x / (24 - 4 * k) + p * (0.8 + k * 0.3)) *
                    (8 + 10 * f["kick"]) + np.sin(self.x / 9 - p * 1.3 + k) * 3)
            width = (110 + 120 * f["mid"]) * f.get("d_soft", 1.0) ** 2
            out += np.exp(-((self.y - band) ** 2) / width) * (0.35 + 0.35 * f["energy"] + 0.3 * f["kick"]) * \
                (0.6 + 0.4 * np.sin(self.x / 14 + p * 2 + k))
        rs = np.random.default_rng(int(p * 4))
        stars = rs.random((H, W)) > 0.997
        out[stars] = np.maximum(out[stars], 0.5)
        return _lut(np.clip(out, 0, 1), lut)

    def glow(self, f, lut):
        """Soft orbs of light drifting slowly, breathing with the bass."""
        p, W, H = self.phase, self.W, self.H
        if not hasattr(self, "_glow_pal"):
            self._glow_pal = None
        out = np.zeros((H, W, 3), np.float32)
        breathe = (1 + 0.35 * f["kick"]) * f.get("d_scale", 1.0)
        n = f.get("d_count", 6.0)
        for i in range(8):
            w = max(0.0, min(1.0, n - i))                  # orbs fade in/out, never pop
            if w <= 0:
                continue
            s = 0.05 + i * 0.012
            cx = W * (0.5 + 0.42 * math.sin(p * s * 2.2 + i * 2.1))
            cy = H * (0.5 + 0.42 * math.sin(p * s * 1.7 + i * 1.3))
            sig = (26 + 10 * math.sin(p * 0.2 + i * 1.7)) * breathe * f.get("d_soft", 1.0)
            g = np.exp(-((self.x - cx) ** 2 + (self.y - cy) ** 2) / (2 * sig * sig))
            col = lut[int(150 + 100 * ((i * 0.37) % 1))]
            out += g[..., None] * col * (0.55 + 0.25 * math.sin(p * 0.5 + i)) * w
        base = lut[18][None, None, :] * 0.6
        return np.clip(base + out, 0, 255)

    def ripples_(self, f, lut):
        W, H, now = self.W, self.H, time.time()
        v = 0.12 + 0.05 * np.sin(self.x / 11 + self.phase * 2) * np.sin(self.y / 13 - self.phase)
        for cx, cy, t0 in self.ripples:
            age = now - t0
            if age > 6:
                continue
            r = age * 26
            d = np.sqrt((self.x - cx) ** 2 + (self.y - cy) ** 2)
            v = v + np.exp(-((d - r) ** 2) / 30) * (1 - age / 6) * 0.45
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
        if style == "glow":
            return self.glow(f, lut)
        return self.lava(f, lut)


# ---------------------------------------------------------------- show ---

class MusicShow:
    XFADE = 15.0       # slow fade between scenes
    HOLD = 180.0       # a scene stays at least this long

    def __init__(self):
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        self.W, self.H = W, H
        self.l = Listener()
        self.settings, self.settings_mtime, self.settings_checked = load_settings(), None, 0.0
        self.force = False
        self.xfade = self.XFADE
        self.vj = VJ(self.l, vibe=lambda: self.settings["vibe"])
        self.vis = Visuals(W, H)
        self.luts = {k: _palette(v) for k, v in PALETTES.items()}
        self.prev = None
        self.cur = ("glow", "dusk", "none")
        self.switched = 0.0
        self.last_t = None
        self.silent_since = None
        self.pulse = 0.0
        self.layer_op = 0.0
        self.design = {"d_speed": 1.0, "d_scale": 1.0, "d_count": 6.0, "d_soft": 1.0}

    def _lut(self, key):
        if key not in self.luts:
            try:
                cols = [_hex_rgb(h) for h in key.split(":", 1)[1].split(",")]
                self.luts[key] = _palette(cols)
            except Exception:
                return self.luts["dusk"]
        return self.luts[key]

    def _poll_settings(self):
        now = time.time()
        if now - self.settings_checked < 2.0:
            return
        self.settings_checked = now
        try:
            m = os.path.getmtime(SETTINGS_FILE)
        except OSError:
            m = None
        if m != self.settings_mtime:
            self.settings_mtime = m
            self.settings = load_settings()
            self.force = True                              # the app changed something: go now

    def _target(self):
        f = self.l.f
        now = time.time()
        st, c = self.settings, self.vj.choice
        auto_style = st["style"] == "auto"
        style = c["style"] if auto_style else st["style"]
        pal = c["palkey"] if st["palette"] == "auto" else st["palette"]
        layer = c["layer"] if auto_style else "none"
        if f["silent"]:
            self.silent_since = self.silent_since or now
            if now - self.silent_since > 30:               # quiet room: soft dusk glow
                return ("glow" if auto_style else style,
                        "dusk" if st["palette"] == "auto" else pal, "none")
        else:
            self.silent_since = None
        return (style, pal, layer)

    def _publish(self):
        c = self.vj.choice
        lut = self._lut(self.cur[1])
        swatch = ["#%02x%02x%02x" % tuple(int(v) for v in lut[i]) for i in (20, 100, 180, 250)]
        _write_json(NOW_FILE, {"scene": c.get("scene", ""), "style": self.cur[0],
                               "layer": self.cur[2], "palette": self.cur[1].split(":")[0],
                               "colors": swatch, "vibe": c.get("vibe", ""),
                               "design": self.design, "layer_opacity": round(self.layer_op, 2),
                               "genre": c.get("genre", ""), "mood": c.get("mood", ""),
                               "song": c.get("song", ""), "artist": c.get("artist", ""),
                               "source": self.vj.source, "settings": self.settings,
                               "audio": {"source": self.settings.get("source", "mac"),
                                         "spec": self.l.spec, "error": self.l.error,
                                         "receiving": time.time() - self.l.last_audio < 2},
                               "silent": self.l.f["silent"], "time": time.time()})

    def _render(self, key, f, dt, beat, op):
        style, palkey, layer = key
        lut = self._lut(palkey)
        img = self.vis.render(style, f, lut, dt, beat)
        if layer != "none" and op > 0.01:                  # second layer, screen-blended
            top = self.vis.render(layer, f, lut, dt, False) * op
            img = 255.0 - (255.0 - img) * (255.0 - top) / 255.0
        return img

    def __call__(self, t):
        dt = 0.033 if self.last_t is None else max(0.0, min(0.2, t - self.last_t))
        self.last_t = t
        f = dict(self.l.f)
        beat = f["beat"]
        self.l.f["beat"] = False
        react = reactivity(self.settings.get("sensitivity", 50))      # live from the app
        self.l.react = react
        for key in ("energy", "bass", "kick", "mid", "treble"):
            f[key] = min(1.0, f[key] * react)
        # visuals breathe with a ~0.6 s average of the bass, so nothing twitches
        self.ks = _ema(getattr(self, "ks", 0.0), f["kick"], dt, 0.6)
        f["kick"] = self.ks
        self._poll_settings()
        c = self.vj.choice
        vibe = self.settings["vibe"] if self.settings["vibe"] != "auto" else c.get("vibe", "chill")
        f["vibe_speed"] = VIBES.get(vibe, VIBES["chill"])[1]
        auto = self.settings["style"] == "auto"
        for key, src, dflt in (("d_speed", "speed", 1.0), ("d_scale", "scale", 1.0),
                               ("d_count", "count", 6.0), ("d_soft", "softness", 1.0)):
            tgt_v = float(c.get(src, dflt)) if auto else dflt
            self.design[key] = _ema(self.design[key], tgt_v, dt, 5.0)   # redesigns blend in slowly
            f[key] = self.design[key]
        self.layer_op = _ema(self.layer_op, float(c.get("layer_opacity", 0.0)) if auto else 0.0,
                             dt, 5.0)
        self.vis.step(f, dt)
        tgt = self._target()
        held = time.time() - self.switched
        if tgt != self.cur and (held >= self.HOLD or self.force):   # hold, unless the app asks
            self.xfade = 4.0 if self.force else self.XFADE
            self.prev, self.cur, self.switched = self.cur, tgt, time.time()
        self.force = False
        if time.time() - getattr(self, "_published", 0) > 3:
            self._published = time.time()
            self._publish()
        img = self._render(self.cur, f, dt, beat, self.layer_op)
        k = (time.time() - self.switched) / self.xfade
        if self.prev and k < 1:
            old = self._render(self.prev, f, dt, False, self.layer_op)
            k = k * k * (3 - 2 * k)
            img = old * (1 - k) + img * k
        img = img * (0.93 + 0.1 * f["kick"])                     # gently rides the (smoothed) bass
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


_show = None


def frame(t):
    global _show
    if _show is None:
        _show = MusicShow()
    return _show(t)
