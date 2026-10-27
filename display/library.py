"""The art library as one catalogue: every piece from every collection, addressable on its own.

    library.catalogue()          -> [{"id", "title", "collection", "kind"}]  (shaders first)
    library.make(id, W, H)       -> a piece with reset() and render(dt, t) -> float32 HxWx3
    library.thumb(id)            -> path of a cached JPEG still (made on first use)

Used by the "piece" mode (one chosen piece on the wall), by music mode's "art" style (library
pieces moving with the music) and by the app's gallery.
"""
import os
import re

import numpy as np

import config

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMBS = os.path.join(_HERE, "panel_setup", "artthumbs")

COLLECTIONS = [          # (key, title in the app, how to get its pieces)
    ("shaders", "Light & form", None),
    ("artsy", "Marbling & op-art", ("display.artsy", "ArtsyGallery")),
    ("shapes", "Lines & dots", ("display.shapes", "ShapesGallery")),
    ("glass", "Glass & trails", ("display.light_art", "LightGallery")),
    ("lava", "Coral & breath", ("display.art", "LavaCoralGallery")),
    ("art", "Ink & moire", ("display.art", "Gallery")),
    ("vj", "Music visuals", None),                   # the music mode's GPU scenes, in calm palettes
    ("loops", "Video loops", None),                  # the music mode's VJ video loops
    ("daily", "Art of the day", None),               # every edition made for this wall; new days appear by themselves
]
_cat = None


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _shader_title(name):
    """'// Glass orb: one soft ...' -> 'Glass orb'; else the file name, spaced."""
    try:
        from display import shaders
        with open(os.path.join(shaders.FOLDER, name + ".frag")) as fh:
            first = fh.readline()
        m = re.match(r"//\s*([^:.\n]{2,40})[:.]", first)
        if m:
            return re.sub(r"\s*\(.*", "", m.group(1)).strip()
    except Exception:
        pass
    return os.path.basename(name).capitalize()


def _gallery(mod, cls):
    import importlib
    return getattr(importlib.import_module(mod), cls)()


def catalogue():
    """All pieces, in the app's order. Cheap after the first call."""
    global _cat
    if _cat is not None:
        return _cat
    from display import shaders
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    out = []
    for key, title, src in COLLECTIONS:
        if key == "daily":
            continue
        if key == "vj":
            for n in _vj_names():
                out.append({"id": "vj-" + n, "title": _shader_title("vj/" + n), "collection": key,
                            "collection_title": title, "kind": "vj"})
            continue
        if key == "loops":
            try:
                from display import loops
                clips = sorted(loops.LoopBank().clips)
            except Exception:
                clips = []
            for i, n in enumerate(clips):
                out.append({"id": "loop-" + n, "title": f"Loop {i + 1}", "collection": key,
                            "collection_title": title, "kind": "loop", "_clip": n})
            continue
        if src is None:
            for p in shaders.gallery_pieces(W, H):
                out.append({"id": "shader-" + p.name, "title": _shader_title(p.name), "collection": key,
                            "collection_title": title, "kind": "shader"})
            continue
        seen = {}
        for i, p in enumerate(_gallery(*src).pieces):
            name = getattr(p, "name", type(p).__name__)
            base = f"{key}-{_slug(name)}"
            seen[base] = seen.get(base, 0) + 1
            pid = base if seen[base] == 1 else f"{base}-{seen[base]}"
            out.append({"id": pid, "title": name + ("" if seen[base] == 1 else f" {seen[base]}"),
                        "collection": key, "collection_title": title, "kind": "python", "_index": i})
    _cat = out
    return out


def _vj_names():
    from display import shaders
    import glob
    return sorted(os.path.splitext(os.path.basename(p))[0]
                  for p in glob.glob(os.path.join(shaders.FOLDER, "vj", "*.frag")))


# calm palettes for the music scenes outside music mode (shadow, mid, highlight): one or two neighbouring hues
VJ_PALETTES = [("#06060c", "#3850b8", "#c8d8ff"), ("#120606", "#b03a18", "#ffd48a"),
               ("#04101a", "#1a6a8a", "#c8f4ff"), ("#0a0714", "#5a2c8c", "#f0d6ff"),
               ("#081208", "#2a7a4a", "#d8f4c8"), ("#140810", "#a03060", "#ffd0dc")]


class VJPiece:
    """A music-mode GPU scene as a gallery piece: its own calm palette, not listening."""

    def __init__(self, W, H, name):
        from display import shaders
        self.W, self.H, self.name = W, H, name
        pal = VJ_PALETTES[sum(map(ord, name)) % len(VJ_PALETTES)]
        self.cols = tuple(shaders._rgb(c) for c in pal)

    def reset(self):
        pass

    def render(self, dt, t):
        from display import shaders
        r = shaders.renderer()
        if not r.ok:
            return np.zeros((self.H, self.W, 3), np.float32)
        return r.render("vj/" + self.name, t * 0.7, {"level": 0.1, "evolve": True}, self.cols)


class LoopPiece:
    """A VJ video loop filling the wall (cover: scaled to the wall's height, centred)."""

    def __init__(self, W, H, clip):
        self.W, self.H, self.clip, self.name, self.player = W, H, clip, "loop-" + clip, None

    def reset(self):
        from display import loops
        self.player = loops.LoopPlayer(self.clip)

    def render(self, dt, t):
        import cv2
        if self.player is None:
            self.reset()
        img = self.player.frame(dt, self.player.fps * 0.5)       # half speed: calmer than in music mode
        h, w = img.shape[:2]
        k = max(self.W / w, self.H / h)
        img = cv2.resize(img, (max(self.W, round(w * k)), max(self.H, round(h * k))), interpolation=cv2.INTER_AREA)
        y, x = (img.shape[0] - self.H) // 2, (img.shape[1] - self.W) // 2
        return img[y:y + self.H, x:x + self.W].astype(np.float32)


def _daily_entries():
    """The art-of-the-day editions on this wall, newest first (read each time: a new day appears by itself)."""
    try:
        from display import daily
        eds = daily.editions()
    except Exception:
        return []
    return [{"id": "daily-" + d, "title": (m.get("name") or d), "collection": "daily",
             "collection_title": "Art of the day", "kind": "daily", "date": d}
            for d, m in eds if os.path.exists(os.path.join(daily.FOLDER, d + ".frag"))]


def _all():
    return catalogue() + _daily_entries()


def find(pid):
    return next((e for e in _all() if e["id"] == pid), None)


def public():
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in _all()]


class DailyPiece:
    """One art-of-the-day edition as a library piece: its shader, its palette, its own day (not listening)."""

    def __init__(self, W, H, date):
        self.W, self.H, self.date, self.name = W, H, date, "daily-" + date
        from display import daily
        self.meta = next((m for d, m in daily.editions() if d == date), {})
        self.cols = [daily._hex(c) for c in self.meta.get("palette", ["#000000", "#808080", "#ffffff"])]
        self.hours = daily.load_memory(date)["hours"]

    def reset(self):
        pass

    def render(self, dt, t):
        from display import daily, shaders
        r = shaders.renderer()
        if not r.ok:
            return np.zeros((self.H, self.W, 3), np.float32)
        return r.render("path:" + daily._path(self.date, "frag"), t, {"level": 0.1, "day": self.hours, "evolve": True},
                        self.cols)


def make(pid, W=None, H=None):
    """A fresh piece for this id (None if unknown)."""
    W, H = W or config.TOTAL_WIDTH, H or config.TOTAL_HEIGHT
    e = find(pid)
    if e is None:
        return None
    if e["kind"] == "daily":
        return DailyPiece(W, H, e["date"])
    if e["kind"] == "vj":
        return VJPiece(W, H, pid[len("vj-"):])
    if e["kind"] == "loop":
        return LoopPiece(W, H, e["_clip"])
    if e["kind"] == "shader":
        from display import shaders
        name = pid[len("shader-"):]
        cols = tuple(shaders._rgb(c) for c in shaders.CURATED.get(name, ("#08060f", "#4a3080", "#efe6ff")))
        return shaders.ShaderPiece(W, H, name, cols)
    src = next(s for k, _, s in COLLECTIONS if k == e["collection"])
    return _gallery(*src).pieces[e["_index"]]


def render_still(pid, seconds=8.0):
    """A representative frame (python pieces need a few simulated seconds to develop)."""
    import numpy as np
    p = make(pid)
    if p is None:
        return None
    p.reset()
    if find(pid)["kind"] in ("shader", "daily", "vj"):
        return p.render(0.04, 40.0)
    if find(pid)["kind"] == "loop":
        img = None
        for k in range(60):
            img = p.render(0.1, 0.0)
        return np.clip(img, 0, 255)
    img = None
    for k in range(int(seconds / 0.04)):
        img = p.render(0.04, 30.0 + k * 0.04)
    return np.clip(img, 0, 255)


def thumb(pid):
    """Path of a cached JPEG thumbnail, made on first use."""
    from PIL import Image
    import numpy as np
    if find(pid) is None:
        return None
    os.makedirs(THUMBS, exist_ok=True)
    path = _thumb_path(pid)
    if not os.path.exists(path):
        img = render_still(pid)
        Image.fromarray(np.asarray(img, np.uint8)).save(path, quality=85)
    return path


def _thumb_path(pid):
    return os.path.join(THUMBS, f"{pid}-{config.TOTAL_WIDTH}x{config.TOTAL_HEIGHT}.jpg")


def thumbs_in_subprocess(ids=None, timeout=600):
    """Make missing thumbnails in a separate process: a GPU context belongs to one thread, so a web
    server must never render shaders itself."""
    import subprocess
    import sys
    todo = [i for i in (ids or [e["id"] for e in _all()]) if not os.path.exists(_thumb_path(i))]
    if todo:
        subprocess.run([sys.executable, "-m", "display.library", "thumbs", *todo], cwd=_HERE,
                       timeout=timeout, capture_output=True)
    return [i for i in todo if not os.path.exists(_thumb_path(i))]


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["thumbs"]:
        for pid in sys.argv[2:] or [e["id"] for e in _all()]:
            try:
                thumb(pid)
            except Exception as e:
                print(f"[library] thumb {pid}: {e}", flush=True)
