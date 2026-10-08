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
import colorsys
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
from display.beat import BeatTracker
from display import vj_fx
from display.intensity import Intensity
from display import loops as vjloops
LOOP_BANK = vjloops.LoopBank()

SR = 22050
WIN, HOP = 1024, 256
AI_EVERY = 150.0          # audio brain: about once per scene hold (it is the expensive one)
TEXT_EVERY = 45.0         # cheap text brain
# cheapest-first; the next one is tried if a model is unavailable (override with AI_TEXT_MODEL)
TEXT_MODELS = ["gpt-4.1-nano", "gpt-4o-mini"]
# free-tier Gemini (Google AI Studio key in .env as GEMINI_API_KEY); text only, never audio
# 2.5 Flash-Lite is retired for new keys (404); "-latest" survives future retirements.
# Measured with a real key 2026-10-08: ~1.3 s each. Avoid gemini-flash-latest (thinking, ~30 s).
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"]
GEMINI_EVERY = 45.0
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
SONG_CALL_GAP = 12.0      # a newly recognised song may trigger a call, at most this often
USAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "panel_setup", "ai_usage.json")
AI_CLIP = 10.0
SHAPE_STYLES = ["flowdots", "flowlines", "garden", "truchet", "rings", "ridges", "weave"]
STYLES = ["aurora", "lava", "ripples", "coral", "ink"] + SHAPE_STYLES + list(vj_fx.PIECE_STYLES) + ["loops"]      # "glow" retired (Visuals.glow kept)
PALETTES = {
    "dusk":   [(15, 8, 30), (80, 30, 90), (220, 120, 120), (255, 200, 150)],
    "ocean":  [(2, 8, 25), (10, 50, 90), (30, 140, 160), (170, 230, 230)],
    "forest": [(4, 14, 8), (20, 70, 40), (90, 160, 90), (210, 240, 190)],
    "moon":   [(6, 8, 18), (40, 50, 80), (130, 150, 190), (230, 235, 250)],
    "blush":  [(18, 6, 16), (90, 30, 70), (230, 130, 170), (255, 220, 230)],
    "ember":  [(10, 3, 2), (80, 20, 10), (200, 80, 30), (255, 180, 90)],
    "gold":   [(8, 5, 0), (70, 45, 10), (200, 150, 60), (255, 235, 170)],
    "neon":   [(2, 3, 14), (16, 22, 120), (0, 190, 255), (215, 248, 255)],
    "violet": [(6, 0, 18), (70, 12, 125), (215, 40, 205), (255, 205, 255)],
    "acid":   [(0, 6, 5), (0, 72, 62), (0, 215, 140), (215, 255, 205)],
    "ice":    [(2, 6, 18), (20, 60, 130), (110, 190, 245), (240, 252, 255)],
}
VIBES = {"chill": ("chill and tranquil", 1.0), "dreamy": ("dreamy and floaty", 0.75),
         "warm": ("warm and cosy", 1.0), "lively": ("lively but still gentle", 1.4),
         "hypnotic": ("hypnotic and trance-like", 0.6), "euphoric": ("euphoric and glowing", 1.3),
         "electric": ("electric and driving", 1.8)}
PROFILES = {
    "chill": dict(
        label="chill, organic and painterly",
        styles=["aurora", "lava", "coral", "ink", "ripples", "marbling", "oilslick",
                "nebula", "glass", "harmonograph", "ridges", "trails", "loops"],
        palettes=["dusk", "ocean", "forest", "moon", "blush", "ember", "gold"],
        layers=("aurora", "ripples", "nebula"), layer_max=0.4, symmetry=("none",),
        trails=(0.0, 0.25), hue=(0.0, 0.08), accent=(0.0, 0.08), react=(0.2, 0.5),
        speed=(0.25, 0.7), scale=(0.8, 1.6), count=(3, 7), soft=(1.0, 1.8),
        hold=(150.0, 300.0), fade=(14.0, 22.0), glide=5.0, pulse=0.0, breath=0.3, tc=3.0, smooth=0.8, surge=0.0, every=90.0),
    "techno": dict(
        label="cool techno: geometric, neon on black, driving",
        styles=["truchet", "opart", "flowlines", "poles", "garden", "spiral", "flowdots", "trails",
                "marbling", "glass", "loops"],
        palettes=["neon", "violet", "acid", "ice", "ocean", "moon"],
        layers=("rings", "ripples", "garden"), layer_max=0.4,
        symmetry=("none", "mirror", "quad"), trails=(0.0, 0.5), hue=(0.0, 0.25), accent=(0.0, 0.0),
        react=(0.4, 1.0), speed=(0.7, 1.3), scale=(0.7, 1.6), count=(4, 10), soft=(0.6, 1.3),
        hold=(70.0, 140.0), fade=(8.0, 14.0), glide=3.0, pulse=0.0, breath=0.9, tc=2.0, smooth=0.5, surge=0.7, every=60.0),
}
MODES = ("manual", "auto")               # manual = the app's party slider; auto = follow the room
CURRENT_MODE = "manual"                   # set by MusicShow from the app's setting
CURRENT_LEVEL = 0.2                       # set by MusicShow every frame (0 quiet .. 1 rave)
FAVOURITES = ["opart"]                    # the house loves these: offered in every pool


def _lerp(a, b, k):
    return a + (b - a) * k


def _smoothstep(x, lo, hi):
    k = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return k * k * (3 - 2 * k)


def level_for(mode, level):
    return level


def profile(mode=None, level=None):
    """Everything the engine and the designer are allowed to do at this party level: ranges are
    interpolated between the chill pole (level 0) and the techno pole (level 1); the style pool
    is chill's below 0.4, both in between, techno's above 0.65."""
    mode = mode or CURRENT_MODE
    L = level_for(mode, CURRENT_LEVEL if level is None else level)
    c, t = PROFILES["chill"], PROFILES["techno"]
    out = {"level": L, "mode": mode}
    for k in ("trails", "hue", "accent", "react", "speed", "scale", "count", "soft", "hold", "fade"):
        out[k] = (_lerp(c[k][0], t[k][0], L), _lerp(c[k][1], t[k][1], L))
    for k in ("glide", "breath", "tc", "smooth", "every", "layer_max"):
        out[k] = _lerp(c[k], t[k], L)
    out["pulse"] = _smoothstep(L, 0.35, 0.85)              # 0 = organic envelope .. 1 = beat-locked
    out["surge"] = 0.0 if L < 0.55 else 0.8 * (L - 0.55) / 0.45
    out["symmetry"] = t["symmetry"] if L > 0.6 else ("none",)
    out["layers"] = t["layers"] if L > 0.5 else c["layers"]
    if L < 0.4:
        pool, pals = list(c["styles"]), list(c["palettes"])
    elif L > 0.65:
        pool, pals = list(t["styles"]), list(t["palettes"])
    else:
        pool, pals = c["styles"] + t["styles"], c["palettes"] + t["palettes"]
    for fav in FAVOURITES:
        if fav not in pool and L > 0.3:
            pool.append(fav)
    if not len(LOOP_BANK):
        pool = [x for x in pool if x != "loops"]
    out["styles"], out["palettes"] = pool, pals
    out["label"] = ("quiet evening, organic and painterly" if L < 0.4 else
                    "lively living room: organic shapes with a clear groove" if L <= 0.65 else
                    "dance party: geometric neon on black, driving")
    return out


def _swatches(mode):
    return ", ".join(profile(mode)["palettes"])


def ai_prompt(mode=None):
    """The designer's brief for the chosen mode (chill/organic or cool techno)."""
    p = profile(mode)
    common = (
        "You are the resident VJ of an LED art wall (192x192 pixels) in the hallway of House Fortuna, a gay "
        "flatshare in Zürich. Each call you design the NEXT SCENE. Make it BEAUTIFUL first: tasteful, "
        "harmonious colours, nothing garish, nothing busy. Scenes change slowly and organically; never "
        "repeat the base style or palette of your recent scenes. "
        f"Mode: {p['label']}. Base styles you may use: {', '.join(p['styles'])}. "
        f"Preset palettes: {_swatches(mode)} - or invent a 4-colour ramp (deep shadow to bright highlight) "
        "in the same spirit. COLOUR DISCIPLINE: a scene uses ONE or TWO neighbouring hues and their tints "
        "(e.g. deep teal to pale mint; plum to rose gold) - tonal and restrained, never a rainbow, never "
        "complementary clashes. 'loops' are real VJ video loops (Beeple, CC) speed-matched to the tempo. "
        "You are told the measured tempo: slow music (under 90 bpm) wants big, slow, long scenes; mid tempo "
        "(90-125) medium; fast music (over 125) quicker flow and shorter scenes. Let it set speed, scale and hold. "
    )
    L = p["level"]
    if L > 0.65:
        mood = (
            "Think underground club: black backgrounds, crisp geometry, cold neon cyan/blue/violet or acid "
            "green, precise and hypnotic, with mirrored or quad symmetry when it suits. A firm beat, scenes "
            "of 1-2 minutes, speed 0.8-1.7. Pick styles by feel: truchet/mesh/opart/mosaic for hard and "
            "graphic, flowlines/poles/spiral for flowing, kaleido/julia for peak moments. "
        )
    elif L > 0.4:
        mood = (
            "Think a lively living room with a good groove on: organic, flowing shapes with a clear pulse, "
            "warm saturated colours, scenes of 1.5-3 minutes, speed 0.7-1.3. Pick styles by feel: lava/coral/"
            "ink/glass for warm and living, flowlines/poles/spiral for flowing, opart (a house favourite) "
            "for hypnotic. "
        )
    else:
        mood = (
            "Think soft light, water, ink, clouds and coral: slow, round, organic shapes in gentle colours, "
            "long dreamy fades, scenes of 3-5 minutes, speed 0.4-1.1. The beat is only a gentle breath. "
            "Pick styles by feel: aurora/ripples/nebula for airy, lava/coral/ink for warm and living, "
            "marbling/oilslick/glass for painterly. "
        )
    ranges = (
        f"Allowed ranges: layer (optional second style, one of {', '.join(p['layers'])}) opacity 0-{p['layer_max']}; "
        f"symmetry one of {', '.join(p['symmetry'])}; trails {p['trails'][0]}-{p['trails'][1]}; hue_drift "
        f"{p['hue'][0]}-{p['hue'][1]}; accent {p['accent'][0]}-{p['accent'][1]}; reactivity {p['react'][0]}-"
        f"{p['react'][1]}; speed {p['speed'][0]}-{p['speed'][1]}; scale {p['scale'][0]}-{p['scale'][1]}; count "
        f"{p['count'][0]}-{p['count'][1]}; softness {p['soft'][0]}-{p['soft'][1]}; hold {int(p['hold'][0])}-"
        f"{int(p['hold'][1])} s; fade {int(p['fade'][0])}-{int(p['fade'][1])} s. "
        f"House favourites (use them often when they fit): {', '.join(FAVOURITES)}. "
        "When Shazam has named the song, use its title and artist: let the song's mood, era and cover "
        "art shape the scene and mention it in the scene name. "
        "If the house typed a request, follow it within these limits. Nothing ever flashes or pulses on the beat: the picture only breathes slowly and the flow follows the tempo; never ask for flashing or strobing. "
        "If - and only if - you genuinely recognise the song, name it and its artist and let it inspire the scene; "
        "never guess. "
    )
    schema = (
        "Reply ONLY with JSON: {\"song\": \"title\" or null, \"artist\": \"name\" or null, \"scene\": short "
        "evocative name, \"concept\": one line, \"genre\": str, \"mood\": one word, \"energy\": 0-1, \"style\": "
        "base style, \"layer\": style or \"none\", \"layer_opacity\": number, \"palette\": preset name or "
        "\"custom\", \"colors\": [4 hex strings, when custom], \"vibe\": str, \"speed\": number, \"scale\": "
        "number, \"count\": integer, \"softness\": number, \"symmetry\": str, \"trails\": number, "
        "\"hue_drift\": number, \"accent\": number, \"reactivity\": number, \"hold\": number, \"fade\": number}"
    )
    return common + mood + ranges + schema


LAYERS = vj_fx.LAYER_STYLES
DEFAULT_CHOICE = {"scene": "", "genre": "", "mood": "", "song": "", "artist": "", "style": "aurora", "layer": "none",
                  "layer_opacity": 0.0, "palkey": "dusk", "palette_desc": "dusk",
                  "vibe": "chill", "speed": 1.0, "scale": 1.0, "count": 6, "softness": 1.0,
                  "concept": "", "symmetry": "none", "trails": 0.0, "hue_drift": 0.0, "accent": 0.4,
                  "reactivity": 1.0, "hold": 150.0, "fade": 12.0}


def _hex_rgb(h):
    h = str(h).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _restrain(cols, max_spread=0.22):
    """Colour discipline: a scene gets at most two neighbouring hues. If the AI's colours span
    more of the hue circle than that, every hue is pulled towards the circular mean."""
    import math as _m
    hsv = [colorsys.rgb_to_hsv(*(v / 255.0 for v in c)) for c in cols]
    sat = [(h, s_, v) for h, s_, v in hsv if s_ > 0.25 and v > 0.15]
    if len(sat) < 2:
        return cols
    cx = sum(_m.cos(2 * _m.pi * h) for h, _, _ in sat)
    cy = sum(_m.sin(2 * _m.pi * h) for h, _, _ in sat)
    mean = (_m.atan2(cy, cx) / (2 * _m.pi)) % 1.0
    dist = lambda h: min(abs(h - mean), 1 - abs(h - mean))
    if max(dist(h) for h, _, _ in sat) <= max_spread:
        return cols
    out = []
    for (h, s_, v) in hsv:
        d = (h - mean + 0.5) % 1.0 - 0.5
        h2 = (mean + max(-max_spread, min(max_spread, d))) % 1.0
        out.append(tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb(h2, s_, v)))
    return out


def _soften(cols):
    """Keep an AI palette soft: darkest stays a deep shadow, brightest a soft highlight."""
    lum = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    cols = sorted(_restrain(cols), key=lum)
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
    """Clamp an AI scene to the chosen mode's pool and ranges; None if unusable."""
    if not isinstance(j, dict) or not isinstance(j.get("style"), str):
        return None
    if j.get("style") == "glow":
        j = {**j, "style": "aurora"}                      # retired style -> nearest calm one
    if j.get("style") not in STYLES and not str(j.get("style")).startswith("loop:"):
        return None
    P = profile()
    num = lambda v, lo, hi, d: max(lo, min(hi, float(v))) if isinstance(v, (int, float)) else d
    out = dict(DEFAULT_CHOICE)
    out.update({k: str(j.get(k, ""))[:40] for k in ("scene", "genre", "mood")})
    for k in ("song", "artist"):                      # only when the AI really recognised it
        v = j.get(k)
        out[k] = str(v)[:60] if v and str(v).strip().lower() not in ("null", "none", "unknown", "") else ""
    style = j["style"]
    if style not in P["styles"] and not style.startswith("loop:"):   # outside this mode's world: pick a fitting one
        style = random.choice(P["styles"])
    if style == "loops":                              # a real video loop whose motion suits the level
        clip = LOOP_BANK.pick(P["level"], avoid=set(_recent_loops))
        if clip is None:
            style = random.choice([x for x in P["styles"] if x != "loops"] or ["aurora"])
        else:
            style = "loop:" + clip
            _recent_loops.append(clip)
            del _recent_loops[:-6]
    out["style"] = style
    layer = j.get("layer", "none")
    out["layer"] = layer if layer in P["layers"] and layer != style else "none"
    out["layer_opacity"] = num(j.get("layer_opacity"), 0.0, P["layer_max"], 0.25) if out["layer"] != "none" else 0.0
    out["concept"] = str(j.get("concept", ""))[:120]
    pal = j.get("palette")
    if pal == "native" and style.startswith("loop:"):
        out["palkey"] = out["palette_desc"] = "native"
    elif pal in P["palettes"]:
        out["palkey"] = out["palette_desc"] = pal
    else:
        try:
            cols = _soften([_hex_rgb(c) for c in j.get("colors", [])][:4])
            if len(cols) != 4:
                raise ValueError
            out["palkey"] = "custom:" + ",".join("%02x%02x%02x" % c for c in cols)
            out["palette_desc"] = "custom " + " ".join("#%02x%02x%02x" % c for c in cols)
        except Exception:
            out["palkey"] = out["palette_desc"] = random.choice(P["palettes"])
    out["vibe"] = j.get("vibe") if j.get("vibe") in VIBES else "chill"
    out["speed"] = num(j.get("speed"), *P["speed"], sum(P["speed"]) / 2)
    out["scale"] = num(j.get("scale"), *P["scale"], 1.0)
    out["count"] = num(j.get("count"), *P["count"], 6)
    out["softness"] = num(j.get("softness"), *P["soft"], 1.2)
    out["symmetry"] = j.get("symmetry") if j.get("symmetry") in P["symmetry"] else "none"
    out["trails"] = num(j.get("trails"), *P["trails"], 0.0)
    out["hue_drift"] = num(j.get("hue_drift"), *P["hue"], 0.0)
    out["accent"] = num(j.get("accent"), *P["accent"], P["accent"][0])
    out["reactivity"] = num(j.get("reactivity"), *P["react"], sum(P["react"]) / 2)
    out["hold"] = num(j.get("hold"), *P["hold"], sum(P["hold"]) / 2)
    out["fade"] = num(j.get("fade"), *P["fade"], sum(P["fade"]) / 2)
    out["scene"] = out["scene"] or out["mood"] or "untitled"
    return out


_recent_loops = []


def _scene_key(c):
    return (c["style"], c["palkey"], c["layer"], c.get("symmetry", "none"))


AI_MODELS = ["gpt-audio"]
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(_HERE, "panel_setup", "music_settings.json")   # written by the app
NOW_FILE = os.path.join(_HERE, "panel_setup", "music_now.json")             # read by the app
DEFAULT_SETTINGS = {"style": "auto", "palette": "auto", "vibe": "auto", "source": "pi",
                    "sensitivity": 50, "ai": True, "shazam": True, "song_on_wall": True,
                    "brain": "text", "beat_offset": 0, "beat_strength": 100, "art_reacts": False,
                    "prompt": "", "mode": "manual", "party": 15}


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
        s["source"] = "pi"
    for k in ("ai", "shazam", "song_on_wall"):
        s[k] = bool(s.get(k, True))
    if s.get("brain") == "gemini":                      # retired (the key ran out of credits)
        s["brain"] = "text"
    if s.get("brain") not in ("text", "openai", "claude"):
        s["brain"] = "text"
    try:
        s["sensitivity"] = max(0, min(100, int(s["sensitivity"])))
    except (TypeError, ValueError):
        s["sensitivity"] = 50
    for k, lo, hi, d in (("beat_offset", -250, 250, 0), ("beat_strength", 0, 200, 100)):
        try:
            s[k] = max(lo, min(hi, int(s[k])))
        except (TypeError, ValueError):
            s[k] = d
    s["art_reacts"] = bool(s.get("art_reacts", False))
    s["prompt"] = " ".join(str(s.get("prompt", "") or "").split())[:200]
    if s.get("mode") not in MODES:
        s["mode"] = "manual"
    try:
        s["party"] = max(0, min(100, int(s["party"])))
    except (TypeError, ValueError):
        s["party"] = 15
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


def wav_bytes(x):
    """float32 mono samples -> WAV file bytes (16-bit, SR Hz)."""
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return b.getvalue()


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
                  "beat": False, "beat_t": 0.0, "bpm_hint": 0.0, "silent": True,
                  "bpm": 0.0, "bconf": 0.0, "anchor": 0.0, "period": 0.0}
        self.tracker = BeatTracker(SR / HOP)
        self._prev_log = None
        self._onset_avg = 1e-3
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

    @staticmethod
    def _raise_capture_volume(dev):
        """USB webcam mics often start quiet: best-effort raise the capture level of that card."""
        try:
            card = dev.split(":")[1].split(",")[0]
            ctl = subprocess.run(["amixer", "-c", card, "scontrols"], capture_output=True, text=True,
                                 timeout=5).stdout
            for line in ctl.splitlines():
                name = line.split("'")[1] if "'" in line else ""
                if name.lower() in ("mic", "capture", "mic capture", "headset"):
                    subprocess.run(["amixer", "-q", "-c", card, "sset", name, "cap", "85%"],
                                   capture_output=True, timeout=5)
        except Exception:
            pass

    def _alsa(self, dev):
        self._raise_capture_volume(dev or "")
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
        self._flux_bands = [((freqs >= 30) & (freqs < 200), 1.0), ((freqs >= 200) & (freqs < 2500), 0.4),
                            ((freqs >= 2500) & (freqs < 8000), 0.12)]
        self._band_avg = [1e-3, 1e-3, 1e-3]
        self._all_bins = (freqs >= 30) & (freqs < 8000)
        self._rms_slow, self._prev_onset, self._onset_edges = 1e-5, 0.0, []
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
            silent = rms < 0.0018 / self.react or now - self.last_audio > 1.5     # ~-55 dBFS: quiet music still counts
            f = self.f
            # absolute loudness and bass share (for the party level)
            self._rms_slow = _ema(self._rms_slow, rms, dt, 1.5)
            f["db"] = 20.0 * math.log10(max(self._rms_slow, 1e-6))
            share = float(spec[bands["kickband"]].sum() / (spec[self._all_bins].sum() + 1e-9))
            f["bass_share"] = _ema(f.get("bass_share", 0.0), 0.0 if silent else share, dt, 3.0)
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
            # beat tracking: onset strength = rise of the log spectrum (30 Hz - 6 kHz)
            # (per band, normalised, then weighted to favour kick/bass over hi-hats: the beat lives low)
            lg = np.log1p(spec * 30.0)
            if self._prev_log is not None and not silent:
                rise = np.maximum(lg - self._prev_log, 0.0)
                onset = 0.0
                for i, (mask, w) in enumerate(self._flux_bands):
                    fl = float(rise[mask].sum())
                    self._band_avg[i] = 0.98 * self._band_avg[i] + 0.02 * fl
                    onset += w * fl / (self._band_avg[i] + 1e-6)
                self.tracker.update(onset, now)
                if onset > 3.0 and self._prev_onset <= 3.0:            # a new hit
                    self._onset_edges.append(now)
                self._prev_onset = onset
            self._prev_log = lg
            self._onset_edges = [e for e in self._onset_edges if now - e < 4.0]
            f["busy"] = 0.0 if silent else len(self._onset_edges) / 4.0     # hits per second
            if silent:
                self.tracker.conf *= 0.97
            tr = self.tracker
            f["bpm"], f["bconf"] = tr.bpm, (0.0 if silent else tr.conf)
            f["anchor"], f["period"] = tr.anchor, tr.period
            if tr.period > 0:
                bi = tr.beat_index(now)
                f["beat_idx"], f["bar_pos"] = bi, (bi - tr.downbeat) % 4
                f["phrase_pos"] = (bi - tr.downbeat) % 32


# ------------------------------------------------------- song recognition ---

class Recognizer:
    """Names the playing song with Shazam (unofficial shazamio library)."""
    EVERY_MISS, EVERY_HIT = 45.0, 100.0

    def __init__(self, listener, enabled=lambda: True):
        self.l, self.enabled = listener, enabled
        self.song = None                    # {"title", "artist", "at", "seen"}
        self.status = "idle"
        threading.Thread(target=self._loop, daemon=True).start()

    def current(self, max_age=300.0):
        s = self.song
        if s and time.time() - s["seen"] < max_age and not self.l.f["silent"]:
            return s
        return None

    @staticmethod
    def _recognize(clip):
        import asyncio
        from shazamio import Shazam
        wav = wav_bytes(clip)

        async def go():
            return await Shazam().recognize(wav)
        track = (asyncio.run(go()) or {}).get("track")
        if track and track.get("title"):
            return track["title"], track.get("subtitle", "")
        return None

    def _loop(self):
        time.sleep(15)
        wait = self.EVERY_MISS
        while True:
            time.sleep(wait)
            wait = self.EVERY_MISS
            if not self.enabled():
                self.status = "off"
                continue
            if self.l.f["silent"] or time.time() - self.l.last_audio > 2:
                self.status = "waiting for music"
                continue
            clip = self.l.recent(10.0)
            level = float(np.sqrt(np.mean(clip * clip)))
            if level < 0.003:
                continue
            self.status = "listening"
            try:
                r = self._recognize(clip * min(8.0, 0.25 / max(level, 1e-4)))
            except Exception as e:
                self.status = f"error: {str(e)[:60]}"
                print(f"[SHAZAM] {str(e)[:120]}", flush=True)
                continue
            now = time.time()
            if r:
                title, artist = r
                if self.song and self.song["title"] == title:
                    self.song["seen"] = now
                else:
                    self.song = {"title": title, "artist": artist, "at": now, "seen": now}
                    print(f"[SHAZAM] {title} - {artist}", flush=True)
                self.status = "found"
                wait = self.EVERY_HIT
            else:
                self.status = "no match"
                print("[SHAZAM] no match", flush=True)


# ------------------------------------------------------ Claude CLI brain ---

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "haiku")       # alias; any model the plan allows
CLAUDE_TIMEOUT = 90
CLAUDE_EVERY = 120.0                                         # go easy on the plan


def find_claude():
    """Path of the Claude Code CLI, or None."""
    import shutil
    cands = [os.environ.get("CLAUDE_BIN"), shutil.which("claude"),
             "/home/pi/.local/bin/claude", os.path.expanduser("~/.local/bin/claude"),
             "/usr/local/bin/claude"]
    for c in cands:
        if c and os.path.exists(c) and os.access(c, os.X_OK):
            return c
    return None


def claude_credentials():
    return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY"))


def claude_json(stdout):
    """Pull the scene JSON out of `claude -p --output-format json` output."""
    text = stdout
    try:
        outer = json.loads(stdout)
        if isinstance(outer, dict) and "result" not in outer and "style" in outer:
            return outer                                      # the scene itself, not wrapped
        if isinstance(outer, dict):
            if outer.get("is_error"):
                raise RuntimeError(str(outer.get("result") or outer.get("error") or "claude error")[:160])
            text = outer.get("result", "") or ""
        elif isinstance(outer, list):                         # stream-style: last result item
            for item in reversed(outer):
                if isinstance(item, dict) and item.get("type") == "result":
                    text = item.get("result", "") or ""
                    break
    except json.JSONDecodeError:
        pass
    if "{" not in text:
        raise RuntimeError(f"no JSON in reply: {text[:100]!r}")
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


# --------------------------------------------------------------- AI VJ ---

class VJ:
    """The AI light designer: listens every AI_EVERY s and designs a whole scene."""

    def __init__(self, listener, vibe=lambda: "chill", enabled=lambda: True, song=lambda: None,
                 brain=lambda: "openai", prompt=lambda: ""):
        self.l = listener
        self.prompt = prompt
        self._last_prompt = prompt()
        self.urgent = False                   # a result that should switch the scene right now
        self._e_ref = 0.0
        self.vibe = vibe
        self.enabled = enabled
        self.song = song
        self.brain = brain
        self.brain_status = ""
        self.usage = {}
        self._last_call, self._last_song = 0.0, None
        self.choice = dict(DEFAULT_CHOICE)
        self.history = []
        self.changed = 0.0
        self.source = "default"
        threading.Thread(target=self._loop, daemon=True).start()

    def _wav_b64(self, x):
        return base64.b64encode(wav_bytes(x)).decode()

    def _context(self):
        lt = time.localtime()
        h = lt.tm_hour
        part = ("night" if h < 6 or h >= 22 else "morning" if h < 11 else
                "afternoon" if h < 17 else "evening")
        f = self.l.f
        hist = "; ".join(f"\"{s['scene']}\" ({s['style']}"
                         + (f" + {s['layer']}" if s["layer"] != "none" else "")
                         + f", {s['palette']})" for s in self.history[-4:]) or "none yet"
        bpm = f.get("bpm") or f.get("bpm_hint") or 0
        lock = f.get("bconf", 0.0)
        tempo = (f"tempo {bpm:.0f} bpm (beat lock {lock:.0%})" if bpm else "tempo unknown")
        P = profile()
        tempo += (f"; party level {P['level']:.0%} ({P['label'].split(':')[0]}; loudness "
                  f"{f.get('db', -80):.0f} dBFS, {f.get('busy', 0):.1f} hits/s)")
        ask = self.prompt()
        want = (f"THE HOUSE ASKS FOR THIS (it overrides your own taste - follow it as the art direction): "
                f"\"{ask}\". " if ask else "")
        return (f"Here is a {AI_CLIP:.0f}-second clip of what is playing in the hallway now. "
                f"Local time {lt.tm_hour:02d}:{lt.tm_min:02d} ({part}). Measured energy "
                f"{f['energy']:.2f}, {tempo}. Your recent scenes: "
                f"{hist}. {want}{self._song_line()}Design the next scene. Reply with the JSON only.")

    def _song_line(self):
        sg = self.song()
        if not sg:
            return ""
        return (f"Shazam has identified the song as \"{sg['title']}\" by {sg['artist']} - treat "
                f"that as fact and let the song itself (its mood, era, lyrics, cover art) inspire "
                f"the scene; set \"song\" and \"artist\" accordingly. ")

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
        self._count("openai")
        vibe = self.vibe()
        system = ai_prompt()
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

    def _text_prompt(self):
        """(system, user) for the text-only brains: no audio, just the song and measurements."""
        f = self.l.f
        vibe = self.vibe()
        system = ai_prompt()
        user = self._context().replace(
            f"Here is a {AI_CLIP:.0f}-second clip of what is playing in the hallway now. ",
            "You cannot hear the music (you are text only); here is what the hallway sensors "
            f"measure: bass {f['bass']:.2f}, mids {f['mid']:.2f}, treble {f['treble']:.2f} (0-1). ")
        return system, user + "\nIf no song is given, do not invent one: use null."

    def _count(self, brain):
        """Count AI calls per day (shown in the app)."""
        day = time.strftime("%Y-%m-%d")
        try:
            with open(USAGE_FILE) as fh:
                u = json.load(fh)
        except Exception:
            u = {}
        if u.get("date") != day:
            u = {"date": day}
        u[brain] = u.get(brain, 0) + 1
        _write_json(USAGE_FILE, u)
        self.usage = u

    def _ask_text(self):
        """Cheap text-only designer: a small OpenAI text model (default: the project's AI_MODEL)."""
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(_HERE, ".env"))
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=40)
        except Exception as e:
            self.brain_status = f"no OpenAI client: {str(e)[:80]}"
            return None
        models = [os.environ["AI_TEXT_MODEL"]] if os.environ.get("AI_TEXT_MODEL") else TEXT_MODELS
        system, user = self._text_prompt()
        t0 = time.time()
        self._count("text")
        last = ""
        for model in models:
            try:
                r = client.chat.completions.create(
                    model=model, max_tokens=350, temperature=1.0,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}])
                j = _validate(json.loads(r.choices[0].message.content or "{}"))
                if not j:
                    raise RuntimeError("scene was not valid")
                j["model"] = model
                self.brain_status = f"text ({model}) ok - {time.time() - t0:.0f} s"
                return j
            except Exception as e:
                last = f"{model}: {str(e)[:90]}"
                print(f"[VJ] text brain {last}", flush=True)
        self.brain_status = f"text error: {last}"
        return None

    def _ask_gemini(self):
        """Free-tier Gemini, text only (song + sensor numbers, never audio)."""
        import urllib.request, urllib.error
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(_HERE, ".env"))
        except Exception:
            pass
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            self.brain_status = "no GEMINI_API_KEY in the Pi's .env (free key: aistudio.google.com/apikey)"
            return None
        models = [os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else GEMINI_MODELS
        system, user = self._text_prompt()
        t0 = time.time()
        self._count("gemini")
        last = ""
        for model in models:
            for thinking in (True, False):                 # retry once without thinkingConfig
                cfg = {"responseMimeType": "application/json", "maxOutputTokens": 600,
                       "temperature": 1.0}
                if thinking:
                    cfg["thinkingConfig"] = {"thinkingBudget": 0}
                body = json.dumps({"systemInstruction": {"parts": [{"text": system}]},
                                   "contents": [{"role": "user", "parts": [{"text": user}]}],
                                   "generationConfig": cfg}).encode()
                req = urllib.request.Request(GEMINI_URL.format(model=model), data=body, method="POST",
                                             headers={"Content-Type": "application/json",
                                                      "x-goog-api-key": key})
                try:
                    with urllib.request.urlopen(req, timeout=40) as r:
                        out = json.load(r)
                    text = out["candidates"][0]["content"]["parts"][0]["text"]
                    j = _validate(json.loads(text[text.index("{"): text.rindex("}") + 1]))
                    if not j:
                        raise RuntimeError("scene was not valid")
                    j["model"] = model
                    self.brain_status = f"Gemini free ({model}) ok - {time.time() - t0:.0f} s"
                    return j
                except urllib.error.HTTPError as e:
                    detail = ""
                    try:
                        detail = json.load(e).get("error", {}).get("message", "")[:90]
                    except Exception:
                        pass
                    last = f"{model}: HTTP {e.code} {detail}"
                    if e.code == 429:                      # free-tier limit: rest for a while
                        self._backoff_until = time.time() + 600
                        self.brain_status = "Gemini free-tier limit reached - using built-in rules for 10 min"
                        print(f"[VJ] {self.brain_status}", flush=True)
                        return None
                    if e.code in (401, 403):
                        self.brain_status = f"Gemini key rejected (HTTP {e.code}) - check GEMINI_API_KEY"
                        print(f"[VJ] {self.brain_status}", flush=True)
                        return None
                    if e.code == 400 and thinking:
                        continue                           # try again without thinkingConfig
                    break                                  # unknown model etc.: next model
                except Exception as e:
                    last = f"{model}: {str(e)[:90]}"
                    break
        self.brain_status = f"Gemini error: {last}"
        print(f"[VJ] {self.brain_status}", flush=True)
        return None

    def _ask_claude(self):
        """Text-only designer: the Claude Code CLI (Haiku) sees the song + measurements, not audio."""
        import subprocess
        exe = find_claude()
        if not exe:
            self.brain_status = "Claude CLI is not installed on the Pi (see panel_setup/README.md)"
            return None
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(_HERE, ".env"))
        except Exception:
            pass
        if not claude_credentials():
            self.brain_status = "no CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY in the Pi's .env"
            return None
        system, user = self._text_prompt()
        prompt = system + "\n\n" + user
        import tempfile
        wd = os.path.join(tempfile.gettempdir(), "wall_claude_cwd")
        os.makedirs(wd, exist_ok=True)                 # empty dir: no project files to load
        t0 = time.time()
        try:
            self._count("claude")
            r = subprocess.run([exe, "-p", prompt, "--model", CLAUDE_MODEL,
                                "--output-format", "json"],
                               capture_output=True, text=True, timeout=CLAUDE_TIMEOUT, cwd=wd,
                               env=dict(os.environ))
            if r.returncode != 0 and not r.stdout.strip():
                raise RuntimeError((r.stderr or "claude exited with an error").strip()[:160])
            j = _validate(claude_json(r.stdout))
            if not j:
                raise RuntimeError("scene was not valid")
            j["model"] = f"claude-{CLAUDE_MODEL}"
            self.brain_status = f"Claude ({CLAUDE_MODEL}) ok - {time.time() - t0:.0f} s"
            return j
        except subprocess.TimeoutExpired:
            self.brain_status = f"Claude timed out after {CLAUDE_TIMEOUT} s"
        except Exception as e:
            self.brain_status = f"Claude error: {str(e)[:120]}"
        print(f"[VJ] {self.brain_status}", flush=True)
        return None

    def _fallback(self):
        """No AI available (or the mode just changed): a good scene from this mode's pool."""
        P = profile()
        last = self.history[-1]["style"] if self.history else None
        style = random.choice([x for x in P["styles"] if x != last] or P["styles"])
        pal = random.choice(P["palettes"])
        if style == "loops":
            pal = "native"
        e = self.l.f["energy"]
        return _validate({"scene": "", "style": style, "palette": pal, "layer": "none",
                          "symmetry": random.choice(P["symmetry"]), "speed": 0.5 + e,
                          "hold": sum(P["hold"]) / 2})

    def reset_for_mode(self):
        """The app switched chill <-> techno: change the scene now, then let the AI refine it."""
        self.choice, self.changed = self._fallback(), time.time()
        self.urgent = True
        self._last_call = 0.0

    def _due(self, now):
        """Call the brain about once per scene, or soon after a newly recognised song."""
        if now < getattr(self, "_backoff_until", 0.0):
            return False                                   # provider said slow down
        brain = self.brain()
        gap = {"openai": AI_EVERY, "claude": CLAUDE_EVERY}.get(brain, profile()["every"])
        sg = self.song()
        title = sg["title"] if sg else None
        if self.prompt() != self._last_prompt and now - self._last_call >= 4.0:
            return True                                    # the house typed something: answer now
        if title and title != self._last_song and now - self._last_call >= SONG_CALL_GAP:
            return True
        # the music changed character (energy jumped or fell): don't wait for the timer
        e = self.l.f["energy"]
        if self._e_ref == 0.0:
            self._e_ref = e
        if abs(e - self._e_ref) > 0.3 and now - self._last_call >= 15.0:
            return True
        return now - self._last_call >= gap

    def _loop(self):
        time.sleep(8)
        while True:
            time.sleep(5)
            now = time.time()
            if not self._due(now):
                continue
            clip = self.l.recent(AI_CLIP)
            level = float(np.sqrt(np.mean(clip * clip)))
            if not self.l.f["silent"] and now - self.l.last_audio < 2 and level > 0.003:
                self._last_call = now
                self._e_ref = self.l.f["energy"]
                prompt_now = self.prompt()
                urgent = prompt_now != self._last_prompt
                self._last_prompt = prompt_now
                sg = self.song()
                self._last_song = sg["title"] if sg else self._last_song
                if not self.enabled():
                    j = None
                elif self.brain() == "claude":
                    j = self._ask_claude()
                elif self.brain() == "gemini":
                    j = self._ask_gemini()
                elif self.brain() == "text":
                    j = self._ask_text()
                else:
                    # normalise the clip so quiet rooms still give the model something to hear
                    j = self._ask_ai(clip * min(8.0, 0.25 / max(level, 1e-4)))
                    self.brain_status = "OpenAI (hears the clip) ok" if j else "OpenAI did not answer"
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
                    self.source = "rules" if not self.enabled() else "fallback"
                    print(f"[VJ] {self.source} -> {j['style']} + {j['palkey']}", flush=True)
                if _scene_key(j) != _scene_key(self.choice):
                    self.choice, self.changed = j, time.time()
                    self.urgent = urgent
                else:
                    self.choice.update({k: v for k, v in j.items()
                                        if k not in ("style", "palkey", "layer")})
                self.choice["song"], self.choice["artist"] = j.get("song", ""), j.get("artist", "")


# ------------------------------------------------------------- visuals ---

def tempo_factor(bpm, lock, mode=None):
    """How fast the art should flow for this music: slow songs drift, fast ones move along.
    ~1.0 at 110 bpm; gentler range in chill, wider in techno. 1.0 when the tempo is unknown."""
    if not bpm or lock < 0.25:
        return 1.0
    lo, hi = (0.75, 1.3) if (mode or CURRENT_MODE) == "chill" else (0.7, 1.6)
    return max(lo, min(hi, bpm / 110.0))


def beat_pulse(f, now, offset_ms=0, strength=1.0, last_phase=0.0):
    """Beat-locked pulse from the tracker's clock.
    -> ((pulse 0..1, new_phase, weight 0..1 how much to trust the tempo), wrapped)
    pulse jumps up on the beat (35 ms attack) and decays until the next one; `wrapped` is True on
    the frame a new beat starts."""
    period, conf = f.get("period", 0.0), f.get("bconf", 0.0)
    if period <= 0 or f.get("silent") or conf < 0.2:
        return (0.0, last_phase, 0.0), False
    ph = ((now - f["anchor"] - offset_ms / 1000.0) / period) % 1.0
    pulse = math.exp(-3.2 * ph) * min(1.0, ph * period / 0.035) * strength
    w = max(0.0, min(1.0, (conf - 0.2) / 0.4))
    return (min(1.0, pulse), ph, w), ph < last_phase - 0.5


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
        self._shapes = None
        self.bank = vj_fx.PieceBank(W, H)
        self.players = {}                                  # clip name -> LoopPlayer (a few open at once)
        threading.Thread(target=self.bank.prewarm, daemon=True).start()

    def shape_(self, style, f, lut):
        """Thin generative line patterns (display/shapes.py) recoloured with the scene palette;
        they drift with the music's energy and glow a little on the kick."""
        if self._shapes is None:
            from display import shapes
            grey = _palette([(0, 0, 0), (255, 255, 255)])
            W, H = self.W, self.H
            self._shapes = {
                "flowdots": shapes.FlowDots(W, H, grey), "flowlines": shapes.FlowDots(W, H, grey, lines=True),
                "garden": shapes.NodeGarden(W, H, grey), "truchet": shapes.Truchet(W, H, grey),
                "rings": shapes.RadialRings(W, H, grey), "ridges": shapes.Ridges(W, H, grey),
                "weave": shapes.WovenGrid(W, H, grey),
            }
        img = self._shapes[style].render(0.04, self.phase * 1.5)
        field = np.clip(img.mean(-1) / 255.0 * (1.1 + 0.3 * f["kick"]), 0, 1)
        return _lut(field, lut)

    def step(self, f, dt):
        # drift speed follows the music only slowly - no speeding up on every bass note
        target = (0.35 + 0.6 * f["energy"]) * f.get("vibe_speed", 1.0) * f.get("d_speed", 1.0)
        self.speed = _ema(getattr(self, "speed", target), target, dt, f.get("speed_tc", 3.0))
        self.phase += dt * self.speed * (1.0 + 0.45 * f.get("groove", 0.0))
        if f["beat"] and (not self.ripples or time.time() - self.ripples[-1][2] > 1.2):
            rs = random.random
            self.ripples.append([rs() * self.W, rs() * self.H * 0.9, time.time()])
            self.ripples = self.ripples[-16:]

    def lava(self, f, lut):
        p, W, H = self.phase, self.W, self.H
        fld = np.zeros((H, W), np.float32)
        swell = (1 + 0.45 * f["kick"] + 0.15 * f.get("groove", 0.0)) * f.get("d_scale", 1.0)
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

    def loop_(self, name, f, dt):
        pl = self.players.get(name)
        if pl is None:
            if len(self.players) >= 3:                     # keep memory small
                old = next(iter(self.players))
                self.players.pop(old).close()
            pl = self.players[name] = vjloops.LoopPlayer(name, LOOP_BANK)
        period = f.get("period", 0.0) if f.get("bconf", 0.0) > 0.5 else 0.0
        beats = vjloops.beats_for(pl.frames / pl.fps, period)
        if beats:                                           # one loop = a whole number of beats
            target = pl.frames / (beats * period)
        else:
            target = pl.fps * max(0.4, min(1.6, f.get("d_speed", 1.0)))
        pl.rate = _ema(getattr(pl, "rate", target), target, dt, 2.0)
        img = pl.frame(dt, pl.rate)
        if img.shape[0] != self.H or img.shape[1] != self.W:
            from PIL import Image as _I
            img = np.asarray(_I.fromarray(img.astype(np.uint8)).resize((self.W, self.H)), np.float32)
        return img

    def render(self, style, f, lut, dt, beat, native=False):
        if style.startswith("loop:"):
            return self.loop_(style[5:], f, dt)
        if style in vj_fx.PIECE_STYLES:
            return self.bank.render(style, self.phase * 1.5, lut, native)
        if style in SHAPE_STYLES:
            return self.shape_(style, f, lut)
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
        global CURRENT_MODE
        CURRENT_MODE = self.settings["mode"]
        self.ks = 0.0
        self.force = False
        self.xfade = self.XFADE
        self.rec = Recognizer(self.l, enabled=lambda: self.settings["shazam"])
        self.vj = VJ(self.l, vibe=lambda: self.settings["vibe"],
                     enabled=lambda: self.settings["ai"], song=self.rec.current,
                     brain=lambda: self.settings["brain"],
                     prompt=lambda: self.settings.get("prompt", ""))
        self.drop = vj_fx.DropDetector()
        self.inten = Intensity()
        self.e_fast = self.e_slow = self.rise = 0.0
        self._last_pp, self._pending = 0, None
        self.accents = vj_fx.Accents(W, H)
        self.surge, self.prev_out = 0.0, None
        self.vis = Visuals(W, H)
        self.luts = {k: _palette(v) for k, v in PALETTES.items()}
        self.prev = None
        self.cur = ("aurora", "dusk", "none", "none")
        self.switched = 0.0
        self.last_t = None
        self.silent_since = None
        self.pulse = 0.0
        self.layer_op = 0.0
        self._last_phase = 0.0
        self.design = {"d_speed": 1.0, "d_scale": 1.0, "d_count": 6.0, "d_soft": 1.0,
                       "d_trails": 0.0, "d_hue": 0.0, "d_accent": 0.4, "d_react": 1.0}

    def _lut(self, key):
        if key == "native":
            return self.luts["dusk"]
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
            global CURRENT_MODE, CURRENT_LEVEL
            new_level = (self.settings["party"] / 100.0 if self.settings["mode"] == "manual"
                         else CURRENT_LEVEL)
            big_jump = abs(new_level - CURRENT_LEVEL) >= 0.25
            if self.settings["mode"] != CURRENT_MODE or big_jump:
                CURRENT_MODE = self.settings["mode"]
                CURRENT_LEVEL = new_level
                self.vj.reset_for_mode()                   # a new scene from the new pool, soon
                print(f"[VJ] mode {CURRENT_MODE}, party {CURRENT_LEVEL:.0%}", flush=True)

    def _target(self):
        f = self.l.f
        now = time.time()
        st, c = self.settings, self.vj.choice
        auto_style = st["style"] == "auto"
        style = c["style"] if auto_style else st["style"]
        pal = c["palkey"] if st["palette"] == "auto" else st["palette"]
        layer = c["layer"] if auto_style else "none"
        sym = c.get("symmetry", "none") if auto_style else "none"
        if f["silent"]:
            self.silent_since = self.silent_since or now
            if now - self.silent_since > 30:               # quiet room: soft dusk glow
                return ("aurora" if auto_style else style,
                        "dusk" if st["palette"] == "auto" else pal, "none", "none")
        else:
            self.silent_since = None
        return (style, pal, layer, sym)

    def _publish(self):
        c = self.vj.choice
        lut = self._lut(self.cur[1])
        swatch = ["#%02x%02x%02x" % tuple(int(v) for v in lut[i]) for i in (20, 100, 180, 250)]
        _write_json(NOW_FILE, {"scene": c.get("scene", ""), "style": self.cur[0],
                               "layer": self.cur[2], "palette": self.cur[1].split(":")[0],
                               "colors": swatch, "vibe": c.get("vibe", ""),
                               "design": self.design, "layer_opacity": round(self.layer_op, 2),
                               "genre": c.get("genre", ""), "mood": c.get("mood", ""),
                               "song": (self.rec.current() or {}).get("title") or c.get("song", ""),
                               "artist": (self.rec.current() or {}).get("artist") or c.get("artist", ""),
                               "shazam": self.rec.status, "brain_status": self.vj.brain_status,
                               "ai_calls": {k: v for k, v in self.vj.usage.items() if k != "date"},
                               "source": self.vj.source, "settings": self.settings,
                               "audio": {"source": self.settings.get("source", "pi"),
                                         "spec": self.l.spec, "error": self.l.error,
                                         "receiving": time.time() - self.l.last_audio < 2,
                                         "bpm": round(self.l.f.get("bpm", 0.0), 1),
                                         "beat_conf": round(self.l.f.get("bconf", 0.0), 2)},
                               "party": {"level": round(CURRENT_LEVEL, 2), "measured": round(self.inten.level, 2),
                                         "label": self.inten.label, "mode": CURRENT_MODE, "why": self.inten.parts},
                               "silent": self.l.f["silent"], "time": time.time()})

    def _render(self, key, f, dt, beat, op):
        style, palkey, layer, sym = key
        lut = self._lut(palkey)
        native = palkey == "native"
        img = self.vis.render(style, f, lut, dt, beat, native)
        if layer != "none" and op > 0.01:                  # second layer, screen-blended
            top = self.vis.render(layer, f, lut, dt, False, native) * op
            img = 255.0 - (255.0 - img) * (255.0 - top) / 255.0
        if sym != "none":
            img = vj_fx.symmetry(img, sym)
        return img

    def __call__(self, t):
        t_in = time.perf_counter()
        out = self._frame(t)
        # cost guard: if frames take too long for the 29 fps budget, the VJ simplifies itself
        self.cost = _ema(getattr(self, "cost", 0.0), (time.perf_counter() - t_in) * 1000.0, 0.033, 1.5)
        return out

    def _frame(self, t):
        global CURRENT_LEVEL
        now = time.time()
        dt = 0.033 if self.last_t is None else max(0.0, min(0.2, t - self.last_t))
        self.last_t = t
        f = dict(self.l.f)
        beat = f["beat"]
        self.l.f["beat"] = False
        sens = self.settings.get("sensitivity", 50)
        react = reactivity(sens)                                     # live from the app
        self.l.react = react
        self._poll_settings()
        # --- how much of a party is this? one slow number everything else follows
        measured = self.inten.update(self.l.f, now, sens)            # what the room sounds like
        CURRENT_LEVEL = measured if self.settings["mode"] == "auto" else self.settings["party"] / 100.0
        P = profile()
        L = P["level"]
        for key in ("energy", "bass", "kick", "mid", "treble"):
            f[key] = min(1.0, f[key] * react)
        self.ks = _ema(self.ks, f["kick"], dt, P["smooth"])          # organic: a smoothed bass envelope
        env = self.ks
        c = self.vj.choice
        auto = self.settings["style"] == "auto"
        # --- the scene's design values glide in (quicker at a party)
        for key, src, dflt in (("d_speed", "speed", 1.0), ("d_scale", "scale", 1.0),
                               ("d_count", "count", 6.0), ("d_soft", "softness", 1.0),
                               ("d_trails", "trails", 0.0), ("d_hue", "hue_drift", 0.0),
                               ("d_accent", "accent", 0.4), ("d_react", "reactivity", 1.0)):
            tgt_v = float(c.get(src, dflt)) if auto else dflt
            self.design[key] = _ema(self.design[key], tgt_v, dt, P["glide"])
            f[key] = self.design[key]
        # --- beat clock: from "barely there" (organic swell) to locked on the beat, strong/weak bars
        # No per-beat pulsing of the picture - ever (it reads as flicker in a room). The beat
        # clock only times scene changes; what the pieces feel is a slow, smoothed envelope.
        pulse, wrapped = beat_pulse(f, now, 0, 1.0, self._last_phase)
        self._last_phase = pulse[1]
        f["kick"] = 0.55 * env * min(1.0, f["d_react"])
        f["pulse"] = 0.0
        # GROOVE: beat-matched *motion* (never brightness). A soft 120 ms attack so it reads as a
        # bounce, strong/weak bars, trusted only with a locked tempo, fading in with the party level.
        g = _smoothstep(L, 0.45, 0.9) * pulse[2] * min(1.0, f["d_react"])
        if g > 0.01 and f.get("period", 0) > 0:
            ph = pulse[1]
            soft = math.exp(-2.5 * ph) * min(1.0, ph * f["period"] / 0.12)
            bar_w = (1.0, 0.6, 0.85, 0.6)[int(f.get("bar_pos", 0)) % 4]
            f["groove"] = g * soft * bar_w
        else:
            f["groove"] = 0.0
        self.vis_last_groove = f["groove"]
        downbeat = wrapped and int(f.get("bar_pos", 1)) == 0 and g > 0.3
        if beat and now - getattr(self, "_last_beat_evt", 0.0) < 2.5:
            beat = False                                   # pieces that react to "a beat" get one every few seconds at most
        if beat or downbeat:
            self._last_beat_evt = now
        beat = beat or downbeat                            # at a party, the bar's first beat is an event (ripples etc.)
        # --- build-ups (riser) and drops - only once it is a party
        self.e_fast = _ema(self.e_fast, f["energy"], dt, 2.0)
        self.e_slow = _ema(self.e_slow, f["energy"], dt, 12.0)
        rising = max(0.0, min(1.0, (self.e_fast - self.e_slow - 0.1) / 0.2)) if L > 0.55 else 0.0
        self.rise = _ema(self.rise, rising, dt, 1.5)
        if P["surge"] > 0 and not f["silent"] and self.drop.update(f["bass"], f["energy"], dt, now):
            self.surge = 0.5 * P["surge"]                  # a drop: the flow quickens for a few seconds, nothing flashes
            print(f"[VJ] DROP (party {L:.0%})", flush=True)
        self.surge *= math.exp(-dt / 2.5)
        # --- the music's speed sets the flow; a build-up and a drop push it
        f["vibe_speed"] = 1.0
        self.tempo_f = _ema(getattr(self, "tempo_f", 1.0),
                            tempo_factor(f.get("bpm", 0.0), f.get("bconf", 0.0), "chill" if L < 0.5 else "techno"),
                            dt, 6.0)
        f["d_speed"] *= self.tempo_f * (1.0 + 0.3 * self.rise + 0.6 * self.surge)
        f["d_speed"] = min(f["d_speed"], 0.6 + 0.8 * L)   # never frantic; near-still when quiet
        f["speed_tc"] = max(2.0, P["tc"])
        self.layer_op = _ema(self.layer_op, float(c.get("layer_opacity", 0.0)) if auto else 0.0, dt, P["glide"])
        self.vis.step(f, dt)
        # --- scene changes: whenever, when it is quiet; on a 4-bar boundary when the party is on
        tgt = self._target()
        held = now - self.switched
        hold = float(c.get("hold", 150.0)) if auto else self.HOLD
        urgent = self.vj.urgent
        want = tgt != self.cur and (held >= hold or self.force or urgent or (self.surge > 0.6 and held > 20))
        pp = int(f.get("phrase_pos", 0)) % 16
        boundary = pp < self._last_pp
        self._last_pp = pp
        musical = L > 0.6 and f.get("bconf", 0.0) > 0.5 and not (self.force or urgent)
        if want and musical:
            self._pending = self._pending or now
            if not (boundary or now - self._pending > 16 * max(0.3, f.get("period", 0.5))):
                want = False
        if want:
            if self.force or urgent:
                self.xfade = 3.5
            elif musical:
                self.xfade = max(6.0, 8 * f.get("period", 0.5))       # lands on the phrase, but eases in
            elif self.surge > 0.3:
                self.xfade = 6.0
            else:
                self.xfade = float(c.get("fade", self.XFADE))
            self.prev, self.cur, self.switched = self.cur, tgt, now
            self.vj.urgent, self._pending = False, None
        self.force = False
        if now - getattr(self, "_published", 0) > 3:
            self._published = now
            self._publish()
        slow = getattr(self, "cost", 0.0) > 26.0
        lop = 0.0 if slow else self.layer_op                  # too slow: drop the second layer
        if slow and self.xfade > 2.5:
            self.xfade = 2.5                                  # ...and cross-fade quickly (two renders at once)
        img = self._render(self.cur, f, dt, beat, lop)
        k = (now - self.switched) / max(0.5, self.xfade)
        if self.prev and k < 1:
            old = self._render(self.prev, f, dt, False, lop)
            k = k * k * (3 - 2 * k)
            img = old * (1 - k) + img * k
        # --- post effects: colour drift, beat rings, light trails, and the swell with the sound
        if f["d_hue"] > 0.02:
            img = vj_fx.hue_rotate(img, now * f["d_hue"] * 0.12)
        if f["d_trails"] > 0.02:
            if self.prev_out is not None:
                img = np.maximum(img, self.prev_out * (0.5 + 0.46 * f["d_trails"]))
            self.prev_out = img
        else:
            self.prev_out = None
        # brightness only breathes slowly with the overall energy (a few percent over seconds)
        self.glow = _ema(getattr(self, "glow", 0.0), f["energy"], dt, 2.5)
        br = P["breath"]
        img = img * (0.95 + 0.06 * br * self.glow)
        out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
        return self._song_overlay(out)

    SONG_ALPHA = 0.38       # how visible the ghost title is (0..1) - deliberately barely there

    def _song_overlay(self, out):
        """The playing song as one tiny, very faint line along the bottom - while it plays."""
        sg = self.rec.current(600.0)
        if not (sg and self.settings.get("song_on_wall", True)):
            self._song_fade = max(0.0, getattr(self, "_song_fade", 0.0) - 0.05)
            if self._song_fade <= 0:
                return out
        else:
            self._song_fade = min(1.0, getattr(self, "_song_fade", 0.0) + 0.02)   # ~2 s fade in
            self._song_text = sg["title"] + (" - " + sg["artist"] if sg.get("artist") else "")
        from display.maeva_story import _font
        W, H = out.size
        font = _font(8)
        text = self._song_text
        while text and font.getlength(text) > W - 12:
            text = text[:-2].rstrip() + "…" if len(text) > 2 else ""
        a = int(255 * self.SONG_ALPHA * self._song_fade)
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        tw = font.getlength(text)
        d.text(((W - tw) / 2, H - 12), text, font=font, fill=(255, 255, 255, a))
        return Image.alpha_composite(out.convert("RGBA"), layer).convert("RGB")


_show = None


def frame(t):
    global _show
    if _show is None:
        _show = MusicShow()
    return _show(t)
