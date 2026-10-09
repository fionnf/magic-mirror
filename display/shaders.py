"""GPU shaders on the wall: Shadertoy-style fragment shaders rendered offscreen (EGL on the Pi 4,
~1 ms per 192x192 frame) and read back as a numpy image.

assets/shaders/<name>.frag define  void mainImage(out vec4 fragColor, in vec2 fragCoord)
and may use these uniforms:
  iTime, iResolution                 as on Shadertoy
  iBass, iMid, iTreble, iEnergy      music features 0..1 (0 in art mode)
  iLevel                             party level 0..1
  iColA, iColB, iColC                the scene's colours (dark, mid, light) - keep to these

    r = Renderer()                      # r.ok is False if there is no GPU/EGL (laptop, old Pi)
    img = r.render("silk", t, feats)    # float32 HxWx3
"""
import glob
import os
import time

import numpy as np

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(_HERE, "assets", "shaders")
import config
W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT     # follows the panel grid (3 x 3 now, 3 x 4 later)

PRELUDE = """#version 300 es
precision highp float;
uniform float iTime; uniform vec2 iResolution;
uniform float iBass; uniform float iMid; uniform float iTreble; uniform float iEnergy; uniform float iLevel;
uniform vec3 iColA; uniform vec3 iColB; uniform vec3 iColC;
uniform float iBreath; uniform float iTension; uniform float iKey; uniform float iBright; uniform float iSong;
uniform float iBeatPhase; uniform float iDay[24]; uniform vec2 iPanels;
out vec4 _out;
"""
POSTLUDE = """
void main(){ vec4 c = vec4(0.0); mainImage(c, gl_FragCoord.xy); _out = vec4(clamp(c.rgb, 0.0, 1.0), 1.0); }
"""
VS = "#version 300 es\nin vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }"


def names():
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(FOLDER, "*.frag")))


class Renderer:
    def __init__(self):
        self.ok, self.error, self.progs = False, "", {}
        try:
            os.environ.setdefault("EGL_PLATFORM", "surfaceless")
            import moderngl
            self.gl = moderngl
            try:
                self.ctx = moderngl.create_standalone_context(backend="egl", require=310)
            except Exception:
                self.ctx = moderngl.create_standalone_context(require=330)   # a laptop (desktop GL)
            self.vbo = self.ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32).tobytes())
            self.fbo = self.ctx.simple_framebuffer((W, H))
            self.ok = True
        except Exception as e:
            self.error = str(e)[:160]

    def _program(self, name):
        """name = a file stem in assets/shaders, or 'path:/abs/file.frag' for any shader file."""
        if name in self.progs:
            return self.progs[name]
        path = name[5:] if name.startswith("path:") else os.path.join(FOLDER, name + ".frag")
        with open(path) as fh:
            src = fh.read()
        self.progs[name] = self.compile(src)
        return self.progs[name]

    def compile(self, src):
        """Compile Shadertoy-style source (a mainImage function) -> (program, vao). Raises with the
        GLSL compiler's message on errors."""
        fs = PRELUDE + src + POSTLUDE
        if self.ctx.version_code >= 330 and "300 es" in PRELUDE:          # desktop GL: GLSL 330
            fs = fs.replace("#version 300 es\nprecision highp float;", "#version 330")
        prog = self.ctx.program(vertex_shader=VS if self.ctx.version_code < 330 else VS.replace("300 es", "330"),
                                fragment_shader=fs)
        vao = self.ctx.simple_vertex_array(prog, self.vbo, "p")
        return prog, vao

    def render(self, name, t, feats=None, cols=None):
        feats = feats or {}
        prog, vao = self._program(name)
        cols = cols or ((0.03, 0.02, 0.08), (0.45, 0.2, 0.5), (0.95, 0.85, 0.9))

        def setu(k, v):
            if k in prog:
                prog[k].value = v
        setu("iTime", float(t))
        setu("iResolution", (float(W), float(H)))
        setu("iPanels", (float(config.PANELS_WIDE), float(config.PANELS_TALL)))
        for k, key in (("iBass", "bass"), ("iMid", "mid"), ("iTreble", "treble"), ("iEnergy", "energy"),
                       ("iLevel", "level"), ("iBreath", "breath"), ("iTension", "tension"), ("iKey", "key"),
                       ("iBright", "bright"), ("iSong", "song"), ("iBeatPhase", "beat_phase")):
            setu(k, float(feats.get(key, 0.0)))
        if "iDay" in prog:
            day = list(feats.get("day", [0.0] * 24))[:24] + [0.0] * max(0, 24 - len(feats.get("day", [])))
            u = prog["iDay"]
            n = max(1, int(getattr(u, "array_length", 24) or 24))     # the compiler trims unused tail elements
            u.write(np.array(day[:n], "f4").tobytes())
        setu("iColA", tuple(float(v) for v in cols[0]))
        setu("iColB", tuple(float(v) for v in cols[1]))
        setu("iColC", tuple(float(v) for v in cols[2]))
        self.fbo.use()
        vao.render(self.gl.TRIANGLE_STRIP)
        data = self.fbo.read(components=3)
        return np.frombuffer(data, np.uint8).reshape(H, W, 3)[::-1].astype(np.float32)


_renderer = None


def renderer():
    global _renderer
    if _renderer is None:
        _renderer = Renderer()
        if not _renderer.ok:
            print(f"[shaders] no GPU context: {_renderer.error}", flush=True)
    return _renderer


class ShaderPiece:
    """Gallery piece wrapper (same interface as display/art.py pieces)."""

    def __init__(self, Wd, Hd, name, cols):
        self.W, self.H, self.name, self.cols = Wd, Hd, name, cols

    def reset(self):
        pass

    def render(self, dt, t):
        r = renderer()
        if not r.ok:
            return np.zeros((self.H, self.W, 3), np.float32)
        img = r.render(self.name, t, None, self.cols)
        if (self.H, self.W) != (H, W):
            from PIL import Image
            img = np.asarray(Image.fromarray(img.astype(np.uint8)).resize((self.W, self.H)), np.float32)
        return img


CURATED = {   # (shadow, mid, highlight) per piece - the gallery's look; the VJ recolours freely
    "aura": ("#120806", "#7a3a12", "#f2c98a"), "canvas": ("#0c1450", "#3a3fb0", "#f0a860"),
    "inkorbs": ("#081a4a", "#3c62a8", "#b8bfc4"), "cutpaper": ("#1a0605", "#a8261c", "#e6dccb"),
    "topo": ("#1c120c", "#4a3426", "#d8ccb8"), "dotsphere": ("#000000", "#6a5cff", "#66c8ff"),
    "glassblob": ("#04040a", "#2050c8", "#ff9a5a"), "neonlines": ("#12051c", "#b0281c", "#e070ff"),
    "eclipse": ("#000000", "#3040e0", "#ff6a2a"), "halo": ("#140808", "#b02810", "#ff9a40"),
    "silk": ("#030805", "#26734d", "#d8ffd8"), "veil": ("#0a0518", "#5a3399", "#f2e6ff"),
    "dunes": ("#0f0a05", "#99661a", "#fff2bf"), "lanterns": ("#140510", "#8c2650", "#ffd9cc"),
    "tide": ("#05081a", "#1a598c", "#ccf2ff"), "aperture": ("#02020c", "#2a30d0", "#c070ff"),
    "conic": ("#1a0614", "#2048e0", "#f4ead0"), "prism": ("#ff7a2a", "#e04070", "#7a5cff"),
    "halftone": ("#08041a", "#5a2cff", "#7cff5a"),
}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def gallery_pieces(Wd, Hd):
    """One piece per shader, each in its curated palette (newest, strongest first)."""
    order = ["conic", "aperture", "eclipse", "prism", "halftone", "aura", "inkorbs", "cutpaper", "glassblob", "halo", "canvas", "dotsphere",
             "neonlines", "topo", "silk", "veil", "tide", "lanterns", "dunes"]
    have = names()
    picked = [n for n in order if n in have] + [n for n in have if n not in order]
    return [ShaderPiece(Wd, Hd, n, tuple(_rgb(c) for c in CURATED.get(n, ("#08060f", "#4a3080", "#efe6ff"))))
            for n in picked]
