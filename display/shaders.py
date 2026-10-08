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
W = H = 192

PRELUDE = """#version 300 es
precision highp float;
uniform float iTime; uniform vec2 iResolution;
uniform float iBass; uniform float iMid; uniform float iTreble; uniform float iEnergy; uniform float iLevel;
uniform vec3 iColA; uniform vec3 iColB; uniform vec3 iColC;
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
        if name in self.progs:
            return self.progs[name]
        with open(os.path.join(FOLDER, name + ".frag")) as fh:
            src = fh.read()
        fs = PRELUDE + src + POSTLUDE
        if self.ctx.version_code >= 330 and "300 es" in PRELUDE:          # desktop GL: GLSL 330
            fs = fs.replace("#version 300 es\nprecision highp float;", "#version 330")
        prog = self.ctx.program(vertex_shader=VS if self.ctx.version_code < 330 else VS.replace("300 es", "330"),
                                fragment_shader=fs)
        vao = self.ctx.simple_vertex_array(prog, self.vbo, "p")
        self.progs[name] = (prog, vao)
        return self.progs[name]

    def render(self, name, t, feats=None, cols=None):
        feats = feats or {}
        prog, vao = self._program(name)
        cols = cols or ((0.03, 0.02, 0.08), (0.45, 0.2, 0.5), (0.95, 0.85, 0.9))

        def setu(k, v):
            if k in prog:
                prog[k].value = v
        setu("iTime", float(t))
        setu("iResolution", (float(W), float(H)))
        for k, key in (("iBass", "bass"), ("iMid", "mid"), ("iTreble", "treble"), ("iEnergy", "energy"), ("iLevel", "level")):
            setu(k, float(feats.get(key, 0.0)))
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


def gallery_pieces(Wd, Hd):
    """One piece per shader with a restrained two-hue palette each."""
    palettes = [((0.02, 0.03, 0.10), (0.10, 0.35, 0.55), (0.80, 0.95, 1.00)),
                ((0.08, 0.02, 0.06), (0.55, 0.15, 0.30), (1.00, 0.85, 0.80)),
                ((0.03, 0.05, 0.03), (0.15, 0.45, 0.30), (0.85, 1.00, 0.85)),
                ((0.06, 0.04, 0.02), (0.60, 0.40, 0.10), (1.00, 0.95, 0.75)),
                ((0.04, 0.02, 0.10), (0.35, 0.20, 0.60), (0.95, 0.90, 1.00))]
    return [ShaderPiece(Wd, Hd, n, palettes[i % len(palettes)]) for i, n in enumerate(names())]
