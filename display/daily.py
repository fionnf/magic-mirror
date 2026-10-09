"""Art of the day: every day Claude composes one original, living artwork for the wall - a GPU
shader with a title and an artist's statement - and it becomes the default piece for that day.

Each piece is checked before it may reach the wall: it must compile, and a simulated minute of it
must be calm (no flicker, not blinding, not blank). Failures go back to Claude with the reason.

Every piece is a fixed, reproducible edition, kept in assets/daily/:
  YYYY-MM-DD.frag   the artwork (shader source - the piece itself)
  YYYY-MM-DD.json   ERC-721-style metadata: name, description, image, attributes, the source's
                    sha256 and the model that made it - ready to mint as an NFT later if wanted
  YYYY-MM-DD.png    a still (for the app and for the metadata's image)

    ensure(date)      generate today's piece if it does not exist yet (blocking; ~1 min)
    current()         (date, metadata) of the piece to show now (today's, else the latest)
    frame(t)          the wall frame for play.py ("daily" mode)
"""
import datetime
import hashlib
import json
import os
import time

import numpy as np

import config

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(_HERE, "assets", "daily")
W = H = 192

BRIEF = """You are the artist in residence for a 192 x 192 pixel LED art wall in the living room of a
modern apartment in Zürich (House Fortuna, a gay flatshare). Every day you make ONE new original
artwork for the wall, written as a GLSL fragment shader. It hangs there all day like a painting:
people live with it, read, cook and fall asleep in front of it.

The house's taste (from the residents' own references): soft light fields - blurred gradients with
one glowing core, like light through frosted glass; a single form in a lot of space (an ink orb on
paper, one glass blob, a sphere of light points, a dark disc with a burning rim, a dark shape with
light escaping round its edges); flat two-colour mid-century cut-paper curves; fine topographic
lines in one hue family; thin rods of neon light casting soft coloured fans. Few colours, soft
edges, depth through glow and a little static grain. Make your own piece in this spirit - never a
copy of these.

What makes a good piece here:
- one clear idea, generous negative space or calm fields, beautiful at a glance and rewarding
  over hours; abstract digital art in the spirit of a gallery piece - never a screensaver,
  never a club visual, never busy
- SLOW: motion should be barely perceptible from moment to moment (multiply iTime by 0.01-0.06);
  nothing may flash, strobe, blink or pulse quickly
- colour: use ONLY the scene colours iColA (deep shadow), iColB (mid tone), iColC (highlight),
  mixed and tinted - many tints of one or two neighbouring hues, never a rainbow
- it is shown on LEDs: avoid large areas of full brightness; dark is a colour
- it LISTENS to the room, and you decide how. Invent a musical idea for this piece - how it hears -
  using these smooth signals (all 0..1, all 0 in silence; the piece must be complete and beautiful
  in silence):
    iBreath    slow bass envelope (seconds): breathing, swelling, tides
    iTension   rising energy before a drop or chorus: gathering, tightening, approaching
    iKey       the music's key as an angle around the circle of pitch classes: let the hue lean
               WITHIN your palette towards it (every key has its own tint), or move a form
    iBright    how bright/airy the sound is (treble): haze, sparkle density, sharpness
    iSong      a per-song seed (changes when the song changes): re-seed a composition detail so
               each song leaves its own arrangement
    iBeatPhase position within the current beat: only for tiny MOTION (a sway), never light
    iDay[24]   the day's memory: average music energy in each hour 0..23 so far. Let the piece
               record the day - layers, rings, sediment, tide marks - so by midnight it is a
               portrait of the music that was played (it is finalised as the day's edition then)
  Rules: modulation changes size, position, density, shape or hue by small amounts and always
  smoothly; light level stays steady; nothing pulses faster than once every few seconds.

Technical contract (anything else will not compile):
- write ONLY helper functions plus
      void mainImage(out vec4 fragColor, in vec2 fragCoord)
- available uniforms (already declared, do not redeclare): float iTime; vec2 iResolution;
  float iBass, iMid, iTreble, iEnergy, iLevel; vec3 iColA, iColB, iColC
- GLSL ES 3.00 (WebGL2) rules: no #version, no precision line, no textures, no derivatives, all
  float literals with a decimal point (1.0 not 1), loops with constant bounds <= 64
- it must run fast on a Raspberry Pi 4 GPU at 192 x 192: keep total loop iterations per pixel
  under ~200

Today's date, season and any notes are given by the user message. Let them inspire you, but make
something you have not made before (recent titles are listed). Give: a title (2-5 words), a
one-sentence artist's statement, a palette of three hex colours (shadow, mid, highlight - one or
two neighbouring hues), one sentence on how the piece listens ("listening"), and the GLSL."""

SCHEMA = {"type": "object",
          "properties": {"title": {"type": "string"}, "statement": {"type": "string"},
                         "listening": {"type": "string"},
                         "palette": {"type": "array", "items": {"type": "string"}},
                         "glsl": {"type": "string"}},
          "required": ["title", "statement", "palette", "glsl", "listening"], "additionalProperties": False}


def _path(date, ext):
    return os.path.join(FOLDER, f"{date}.{ext}")


def _hex(h):
    h = str(h).strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _season(d):
    return ("winter", "winter", "spring", "spring", "spring", "summer", "summer", "summer",
            "autumn", "autumn", "autumn", "winter")[d.month - 1]


def editions():
    """[(date, metadata)] newest first."""
    out = []
    if not os.path.isdir(FOLDER):
        return out
    for fn in sorted(os.listdir(FOLDER), reverse=True):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(FOLDER, fn)) as fh:
                    out.append((fn[:-5], json.load(fh)))
            except Exception:
                pass
    return out


def check(src, palette):
    """Compile and watch a simulated minute. -> (ok, reason, still_image)."""
    from display import shaders
    r = shaders.renderer()
    if not r.ok:
        return False, f"no GPU here ({r.error})", None
    try:
        prog, vao = r.compile(src)
    except Exception as e:
        return False, "GLSL compile error: " + str(e)[:600], None
    key = "check:" + hashlib.sha256(src.encode()).hexdigest()[:12]
    r.progs[key] = (prog, vao)
    cols = [_hex(c) for c in palette]
    frames, means = [], []
    t0 = time.perf_counter()
    for i in range(60):                                   # one simulated minute, a frame per second
        img = r.render(key, i + 0.37, {"bass": 0.3, "energy": 0.3, "level": 0.2}, cols)
        frames.append(img)
        means.append(float(img.mean()))
    ms = (time.perf_counter() - t0) / 60 * 1000
    # real-time bursts: 2 s at 29 fps, in silence and with lively simulated music - catches flicker,
    # strobing and fast pulsing, including any the music modulation would cause
    def music(tt):
        return {"bass": 0.5 + 0.5 * np.sin(tt * 6.6), "breath": 0.5 + 0.5 * np.sin(tt * 1.2),
                "tension": 0.5 + 0.5 * np.sin(tt * 0.3), "key": (tt * 0.05) % 1.0, "bright": 0.6,
                "song": 0.37, "beat_phase": (tt * 2.1) % 1.0, "energy": 0.7, "level": 0.6,
                "day": [0.6 if 8 < h < 23 else 0.0 for h in range(24)]}
    fast, pulse = [], []
    for start, live in ((5.0, False), (21.3, True), (40.7, True), (12.2, False)):
        burst = [r.render(key, start + k / 29.0, music(start + k / 29.0) if live else
                          {"bass": 0.0, "energy": 0.0, "level": 0.2}, cols) for k in range(58)]
        fast.append(max(float(np.abs(burst[k + 1] - burst[k]).mean()) for k in range(57)))
        pulse.append(float(np.std([b.mean() for b in burst])))
    del r.progs[key]
    m = float(np.mean(means))
    if max(fast) > 2.5:
        return False, (f"it moves or changes too fast (frame-to-frame change {max(fast):.1f}/255 at 29 fps); "
                       "slow iTime down a lot and remove any pulsing"), None
    if max(pulse) > 3.0:
        return False, f"the light level pulses within seconds (std {max(pulse):.1f}/255 over 2 s); no pulsing", None
    if m < 4:
        return False, f"the piece is almost entirely black (mean brightness {m:.1f}/255)", None
    if m > 150:
        return False, f"too bright for an LED wall in a living room (mean {m:.0f}/255); keep it darker", None
    if np.std(means) > 25:
        return False, "overall brightness swings too much over a minute; keep the light level steady", None
    if ms > 25:
        return False, f"too slow to render on the Pi ({ms:.0f} ms per frame here); use fewer loop iterations", None
    still = frames[30].astype(np.uint8)
    return True, f"ok (mean {m:.0f}, motion {max(fast):.2f}, {ms:.1f} ms)", still


def generate(date=None, notes="", attempts=4):
    """Ask Claude for today's piece, check it, save it. -> metadata dict (raises if all attempts fail)."""
    import ai_client
    from PIL import Image
    d = datetime.date.fromisoformat(date) if date else datetime.date.today()
    date = d.isoformat()
    recent = [m.get("name", "") for _, m in editions()[:10]]
    user = (f"Today is {d.strftime('%A %d %B %Y')} ({_season(d)} in Zürich). "
            f"Recent titles (do something different): {', '.join(recent) or 'none yet'}. {notes}").strip()
    feedback = ""
    for attempt in range(1, attempts + 1):
        msg = user + (f"\n\nYour previous attempt was rejected: {feedback}. Fix that and send the "
                      "whole piece again." if feedback else "")
        j, tin, tout = ai_client.ask(BRIEF, msg, max_tokens=16000, effort="medium", schema=SCHEMA, timeout=300)
        pal = (j.get("palette") or [])[:3]
        try:
            [_hex(c) for c in pal]
            assert len(pal) == 3
        except Exception:
            feedback = "the palette must be exactly three #rrggbb colours"
            continue
        src = j["glsl"].replace("#version 300 es", "").replace("precision highp float;", "")
        ok, reason, still = check(src, pal)
        print(f"[daily] attempt {attempt}: {j.get('title')!r} -> {reason}", flush=True)
        if not ok:
            feedback = reason
            continue
        os.makedirs(FOLDER, exist_ok=True)
        with open(_path(date, "frag"), "w") as fh:
            fh.write(f"// {j['title']} - art of the day {date}\n// {j['statement']}\n" + src)
        Image.fromarray(still).resize((576, 576), Image.NEAREST).save(_path(date, "png"))
        sha = hashlib.sha256(src.encode()).hexdigest()
        meta = {"name": j["title"].strip()[:60], "description": j["statement"].strip()[:300],
                "image": f"{date}.png", "animation_source": f"{date}.frag",
                "attributes": [{"trait_type": "Date", "value": date},
                               {"trait_type": "Season", "value": _season(d)},
                               {"trait_type": "Palette", "value": " ".join(pal)},
                               {"trait_type": "Medium", "value": "GLSL shader, 192 x 192 LED wall"},
                               {"trait_type": "Artist", "value": f"Claude ({config.AI_MODEL})"}],
                "listening": j.get("listening", "").strip()[:300],
                "palette": pal, "source_sha256": sha, "model": config.AI_MODEL,
                "tokens": {"in": tin, "out": tout}, "attempts": attempt, "created": time.time()}
        with open(_path(date, "json"), "w") as fh:
            json.dump(meta, fh, indent=1)
        return meta
    raise RuntimeError(f"no acceptable piece after {attempts} attempts (last: {feedback})")


def ensure(date=None):
    date = date or datetime.date.today().isoformat()
    if os.path.exists(_path(date, "json")) and os.path.exists(_path(date, "frag")):
        return None
    return generate(date)


def current(prefer=None):
    """(date, metadata) to show: `prefer` if it exists, else today's, else the newest."""
    eds = dict(editions())
    for d in (prefer, datetime.date.today().isoformat()):
        if d and d in eds:
            return d, eds[d]
    newest = editions()
    return newest[0] if newest else (None, None)


# ------------------------------------------------------- the day's memory ---

def _memory_path(date):
    return _path(date, "memory.json")


def load_memory(date):
    try:
        with open(_memory_path(date)) as fh:
            m = json.load(fh)
        return m
    except Exception:
        return {"hours": [0.0] * 24, "samples": [0] * 24, "songs": []}


def save_memory(date, m):
    tmp = _memory_path(date) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(m, fh)
    os.replace(tmp, _memory_path(date))


def finalise(date):
    """Midnight: bake the day's music into the edition (final still + metadata attributes)."""
    from PIL import Image
    from display import shaders
    if not os.path.exists(_path(date, "json")):
        return
    with open(_path(date, "json")) as fh:
        meta = json.load(fh)
    if meta.get("final"):
        return
    mem = load_memory(date)
    r = shaders.renderer()
    if r.ok:
        img = r.render("path:" + _path(date, "frag"), 3600.0,
                       {"day": mem["hours"], "level": 0.1}, [_hex(c) for c in meta["palette"]])
        Image.fromarray(img.astype(np.uint8)).resize((576, 576), Image.NEAREST).save(_path(date, "final.png"))
        meta["image"] = f"{date}.final.png"
    heard = sum(1 for v in mem["hours"] if v > 0.05)
    meta["attributes"] = [a for a in meta.get("attributes", []) if a.get("trait_type") not in
                          ("Hours with music", "Songs heard", "Loudest hour")]
    meta["attributes"] += [{"trait_type": "Hours with music", "value": heard},
                           {"trait_type": "Songs heard", "value": len(mem["songs"])},
                           {"trait_type": "Loudest hour", "value": int(np.argmax(mem["hours"])) if heard else None}]
    meta["songs"] = mem["songs"][:200]
    meta["final"] = True
    with open(_path(date, "json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print(f"[daily] finalised {date}: {heard} h of music, {len(mem['songs'])} songs", flush=True)


class _Ears:
    """The room's music for the daily piece: smooth features + the hourly memory."""

    def __init__(self):
        from display import music
        self.mu = music
        self.l = music.Listener()
        self.rec = music.Recognizer(self.l, enabled=lambda: music.load_settings().get("shazam", True))
        self.breath = self.tension = 0.0
        self.e_fast = self.e_slow = 0.0
        self.key = None
        self.phase = 0.0
        self.last = time.time()
        self.saved = 0.0

    def features(self, date):
        now = time.time()
        dt = max(0.0, min(0.5, now - self.last))
        self.last = now
        f = self.l.f
        silent = f.get("silent", True)
        ema = self.mu._ema
        self.breath = ema(self.breath, 0.0 if silent else f.get("kick", 0.0), dt, 2.0)
        self.e_fast = ema(self.e_fast, f.get("energy", 0.0), dt, 2.0)
        self.e_slow = ema(self.e_slow, f.get("energy", 0.0), dt, 15.0)
        self.tension = ema(self.tension, max(0.0, min(1.0, (self.e_fast - self.e_slow) * 4.0)), dt, 3.0)
        k = f.get("key")
        if k is not None and not silent:                   # move around the circle the short way, slowly
            if self.key is None:
                self.key = k
            d = (k - self.key + 0.5) % 1.0 - 0.5
            self.key = (self.key + d * min(1.0, dt / 8.0)) % 1.0
        sg = self.rec.current()
        song = (int(hashlib.sha256(sg["title"].encode()).hexdigest()[:8], 16) / 0xFFFFFFFF) if sg else 0.0
        mem = getattr(self, "_mem", None)
        if mem is None or self._mem_date != date:
            self._mem, self._mem_date = load_memory(date), date
            mem = self._mem
        h = time.localtime(now).tm_hour
        if not silent:                                       # running mean of this hour's energy
            n = mem["samples"][h] + 1
            mem["samples"][h] = n
            mem["hours"][h] += (f.get("energy", 0.0) - mem["hours"][h]) / n
            if sg and sg["title"] not in [x["title"] for x in mem["songs"][-30:]]:
                mem["songs"].append({"title": sg["title"], "artist": sg.get("artist", ""), "hour": h})
        if now - self.saved > 60:
            self.saved = now
            save_memory(date, mem)
        period = f.get("period", 0.0)
        if period > 0 and f.get("bconf", 0.0) > 0.5:
            self.phase = ((now - f["anchor"]) / period) % 1.0
        return {"breath": self.breath, "tension": self.tension, "key": self.key or 0.0,
                "bright": 0.0 if silent else f.get("bright", 0.0), "song": song, "beat_phase": self.phase,
                "bass": self.breath, "energy": self.e_slow, "level": 0.1, "day": mem["hours"]}


# ---------------------------------------------------------------- wall ---

_state = {"date": None, "mtime": 0.0, "ears": None, "today": None}


def frame(t):
    """play.py "daily": today's piece (or the one chosen in the app, WALL_DAILY_DATE)."""
    from PIL import Image
    from display import shaders
    now = time.time()
    if now - _state["mtime"] > 30:                         # pick up a new day / a new choice
        _state["mtime"] = now
        date, meta = current(os.environ.get("WALL_DAILY_DATE") or None)
        if date != _state["date"]:
            _state.update(date=date, meta=meta)
    date, meta = _state.get("date"), _state.get("meta")
    r = shaders.renderer()
    if not date or not r.ok:
        return Image.new("RGB", (W, H), (0, 0, 0))
    today = datetime.date.today().isoformat()
    if _state["today"] and _state["today"] != today:      # midnight: yesterday's edition is final
        try:
            finalise(_state["today"])
        except Exception as e:
            print(f"[daily] finalise failed: {e}", flush=True)
    _state["today"] = today
    feats = {"level": 0.1, "day": load_memory(date)["hours"] if date != today else [0.0] * 24}
    if date == today:                                       # today's piece listens; past editions show their day
        if _state["ears"] is None:
            try:
                _state["ears"] = _Ears()
            except Exception as e:
                print(f"[daily] no microphone: {e}", flush=True)
                _state["ears"] = False
        if _state["ears"]:
            feats = _state["ears"].features(today)
    cols = [_hex(c) for c in meta["palette"]]
    img = r.render("path:" + _path(date, "frag"), t, feats, cols)
    return Image.fromarray(img.astype(np.uint8), "RGB")
