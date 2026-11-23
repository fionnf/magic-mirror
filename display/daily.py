"""Art of the day: plays the editions already kept in assets/daily/ (no new art is made any more).

Each edition:
  YYYY-MM-DD.frag   the artwork (shader source - the piece itself)
  YYYY-MM-DD.json   metadata: name, description, palette, ...
  YYYY-MM-DD.png    a still (for the app)

    current()         (date, metadata) of the piece to show now (today's, else the latest)
    frame(t)          the wall frame for play.py ("daily" mode)
    finalise(date)    midnight: bake the day's music into the edition
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
W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT

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
        if fn.endswith(".json") and fn.count(".") == 1:          # 2026-10-09.json, not .memory.json
            try:
                with open(os.path.join(FOLDER, fn)) as fh:
                    out.append((fn[:-5], json.load(fh)))
            except Exception:
                pass
    return out


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
        img = r.render("path:" + _path(date, "frag"), 3600.0,             # the piece as it ends the day
                       {"day": mem["hours"], "level": 0.1, "clock": 23.95}, [_hex(c) for c in meta["palette"]])
        Image.fromarray(img.astype(np.uint8)).resize((W * 3, H * 3), Image.NEAREST).save(_path(date, "final.png"))
        meta["image"] = f"{date}.final.png"
    heard = sum(1 for v in mem["hours"] if v > 0.05)
    meta["attributes"] = [a for a in meta.get("attributes", []) if a.get("trait_type") not in
                          ("Hours with music", "Songs heard", "Loudest hour")]
    meta["attributes"] += [{"trait_type": "Hours with music", "value": heard},
                           {"trait_type": "Songs heard", "value": len(mem["songs"])},
                           {"trait_type": "Loudest hour", "value": int(np.argmax(mem["hours"])) if heard else None}]
    meta["songs"] = mem["songs"][:200]          # stays on the wall's computer; the public gallery drops it
    meta["hours"] = [round(float(v), 3) for v in mem["hours"]]
    meta["final"] = True
    with open(_path(date, "json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print(f"[daily] finalised {date}: {heard} h of music, {len(mem['songs'])} songs", flush=True)


class _Ears:
    """The room's music for the daily piece: smooth features + the hourly memory."""

    def __init__(self):
        from display import music
        self.mu = music
        self.l = music.Listener("none:")                   # the daily art does not react to sound: it hears nothing, and is complete in silence
        self.rec = music.Recognizer(self.l, enabled=lambda: False)
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


# The light of the day over every daily piece: (hour, red, green, blue gain, brightness). Dawn rose, a clear cool
# midday, golden evening, a deep blue night. Strength WALL_DAY_GRADE (0 = off, 1 = as written).
_GRADE = [(0.0, 0.84, 0.92, 1.16, 0.94), (5.5, 0.92, 0.95, 1.12, 0.94), (7.5, 1.16, 0.94, 0.88, 0.92),
          (10.0, 1.0, 1.0, 1.0, 1.0), (13.5, 0.93, 1.0, 1.10, 1.06), (17.0, 1.04, 1.0, 0.94, 1.02),
          (19.0, 1.20, 0.96, 0.78, 1.0), (21.0, 1.10, 0.92, 1.0, 0.94), (24.0, 0.84, 0.92, 1.16, 0.94)]
_GRADE_K = float(os.environ.get("WALL_DAY_GRADE", "1.0"))


def day_grade(hour):
    """(r, g, b) multipliers for this hour of the day, eased between the keyframes."""
    for (h0, *c0), (h1, *c1) in zip(_GRADE, _GRADE[1:]):
        if h0 <= hour <= h1:
            f = (hour - h0) / (h1 - h0)
            f = f * f * (3 - 2 * f)
            r, g, b, v = (a + (b_ - a) * f for a, b_ in zip(c0, c1))
            k = _GRADE_K
            return tuple(1.0 + (x * v - 1.0) * k for x in (r, g, b))
    return 1.0, 1.0, 1.0


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
    feats = dict(feats, evolve=True)                        # slow drift of colour, size and form
    img = r.render("path:" + _path(date, "frag"), t, feats, cols)
    if _GRADE_K > 0:
        lt = time.localtime(now)
        g = np.array(day_grade(lt.tm_hour + lt.tm_min / 60.0 + lt.tm_sec / 3600.0), np.float32)
        img = np.clip(img.astype(np.float32) * g, 0, 255)
    return Image.fromarray(img.astype(np.uint8), "RGB")
