"""The art library as one catalogue: every piece from every collection, addressable on its own.

    library.catalogue()          -> [{"id", "title", "collection", "kind"}]  (shaders first)
    library.make(id, W, H)       -> a piece with reset() and render(dt, t) -> float32 HxWx3
    library.thumb(id)            -> path of a cached JPEG still (made on first use)

Used by the "piece" mode (one chosen piece on the wall), by music mode's "art" style (library
pieces moving with the music) and by the app's gallery.
"""
import os
import re

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
            return m.group(1).strip()
    except Exception:
        pass
    return name.capitalize()


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


def find(pid):
    return next((e for e in catalogue() if e["id"] == pid), None)


def public():
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in catalogue()]


def make(pid, W=None, H=None):
    """A fresh piece for this id (None if unknown)."""
    W, H = W or config.TOTAL_WIDTH, H or config.TOTAL_HEIGHT
    e = find(pid)
    if e is None:
        return None
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
    if find(pid)["kind"] == "shader":
        return p.render(0.04, 40.0)
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
    todo = [i for i in (ids or [e["id"] for e in catalogue()]) if not os.path.exists(_thumb_path(i))]
    if todo:
        subprocess.run([sys.executable, "-m", "display.library", "thumbs", *todo], cwd=_HERE,
                       timeout=timeout, capture_output=True)
    return [i for i in todo if not os.path.exists(_thumb_path(i))]


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["thumbs"]:
        for pid in sys.argv[2:] or [e["id"] for e in catalogue()]:
            try:
                thumb(pid)
            except Exception as e:
                print(f"[library] thumb {pid}: {e}", flush=True)
