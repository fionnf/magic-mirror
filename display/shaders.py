"""GPU shaders on the wall: Shadertoy-style fragment shaders rendered offscreen (EGL on the Pi 4,
~1 ms per 192x192 frame) and read back as a numpy image.

assets/shaders/<name>.frag define  void mainImage(out vec4 fragColor, in vec2 fragCoord)
and may use these uniforms:
  iTime, iResolution                 as on Shadertoy
  iBass, iMid, iTreble, iEnergy      music features 0..1 (0 in art mode)
  iLevel                             party level 0..1
  iColA, iColB, iColC                the scene's colours (dark, mid, light) - keep to these
  iEvolve                            four very slow drifts -1..1 (periods ~11-60 min, each piece its own):
                                     use them for the form itself - lobes, size of parts, density, angles
  (iZoom is applied outside mainImage: music mode redraws the scene slightly larger on the bass)

Slow evolution (feats["evolve"]: True = wall clock, or a time in seconds): besides iEvolve, the piece's
palette drifts in hue and saturation, and its frame slowly grows, shrinks, turns and wanders, so after
half an hour it is a different picture. Full-frame pieces (fc / iResolution) only zoom in and pan inside
themselves; pieces that use iPanels keep their frame (the panel seams stay put). Without "evolve" the
piece renders exactly as written (the daily art checks rely on that).

    r = Renderer()                      # r.ok is False if there is no GPU/EGL (laptop, old Pi)
    img = r.render(t, feats)    # float32 HxWx3
"""
import colorsys
import glob
import math
import os
import re
import time
import zlib

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
uniform float iBeatPhase; uniform float iDay[24]; uniform vec2 iPanels; uniform float iClock;
uniform float iZoom; uniform vec4 iEvolve; uniform vec4 iFrame;
out vec4 _out;
"""
POSTLUDE = """
void main(){
    // iFrame = (scale, turn, x, y): the slow drift of size and place (1,0,0,0 = as drawn);
    // iZoom: music mode breathes with the bass
    vec2 m = 0.5 * iResolution, q = gl_FragCoord.xy - m;
    float cs = cos(iFrame.y), sn = sin(iFrame.y);
    q = mat2(cs, -sn, sn, cs) * q / max(iFrame.x * iZoom, 0.3);
    vec2 p = m + q - iFrame.zw * iResolution;
    vec4 c = vec4(0.0); mainImage(c, p); _out = vec4(clamp(c.rgb, 0.0, 1.0), 1.0); }
"""
GROUNDED = {"cutcurves", "neonarc"}   # stand on the bottom edge: never tilt or lift
_FIELD = re.compile(r"(fc|fragCoord)(\.xy)?\s*/\s*iResolution")


def _drift(seed, k, minutes, period):
    """A smooth wander in -1..1 with a main period in minutes (two unrelated sines, seeded)."""
    ph = (seed * (k + 1) * 0.618034) % 1.0 * 2 * math.pi
    return (0.62 * math.sin(2 * math.pi * minutes / period + ph)
            + 0.38 * math.sin(2 * math.pi * minutes / (period * 1.618) + 1.7 * ph))


def evolution(seed, secs, kind="free"):
    """The slow evolution of one piece at a time in seconds: (iEvolve, iFrame, palette shift).
    seed: zlib.crc32 of the shader source (site/gallery.js does the same, so the wall and the
    website show a piece in the same state at the same moment).
    kind: 'free' (a form on a ground: may shrink, grow, turn, wander), 'grounded' (stands on the
    bottom edge: grows and slides sideways, never tilts or lifts), 'field' (fills the frame: zoom in
    and pan only), 'fixed' (lined up with the panel seams: frame never moves)."""
    seed = seed / 2 ** 32 * 1000.0
    m = secs / 60.0
    d = lambda k, period: _drift(seed, k, m, period)
    evolve = (d(0, 11.0), d(1, 17.0), d(2, 26.0), d(3, 41.0))
    if kind == "fixed":
        frame = (1.0, 0.0, 0.0, 0.0)
    elif kind == "field":
        sc = 1.0 + 0.09 * (d(4, 23.0) + 1.0)                     # 1 .. 1.18: never shows past the edge
        room = 0.45 * (1.0 - 1.0 / sc)
        frame = (sc, 0.0, room * d(6, 19.0), room * d(7, 29.0))
    elif kind == "grounded":
        sc = 2.0 ** (0.18 * d(4, 23.0))
        frame = (sc, 0.0, 0.07 * d(6, 19.0), 0.5 * (1.0 - 1.0 / sc))   # scaled about the bottom edge
    else:
        frame = (2.0 ** (0.24 * d(4, 23.0)), 0.2 * d(5, 37.0), 0.08 * d(6, 19.0), 0.1 * d(7, 29.0))
    shift = (34.0 * d(8, 31.0), 14.0 * d(10, 47.0), 0.2 * d(9, 21.0))   # hue all, hue mid+light, saturation
    return evolve, frame, shift


def shift_palette(cols, shift):
    """Turn the palette round the colour wheel and change its saturation, keeping each colour's
    brightness (dark stays dark, the highlight stays light)."""
    hue, hue2, sat = shift
    out = []
    for i, c in enumerate(cols):
        h, l, s_ = colorsys.rgb_to_hls(*(min(1.0, max(0.0, float(v))) for v in c))
        h = (h + (hue + (hue2 if i else 0.0)) / 360.0) % 1.0
        r, g, b = colorsys.hls_to_rgb(h, l, min(1.0, s_ * (1.0 + sat)))
        out.append((r, g, b))
    return tuple(out)


VS = "#version 300 es\nin vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }"


def names():
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(FOLDER, "*.frag")))


class Renderer:
    def __init__(self):
        self.ok, self.error, self.progs, self.kinds, self.seeds = False, "", {}, {}, {}
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
        self.seeds[name] = zlib.crc32(src.encode())
        self.kinds[name] = ("fixed" if "iPanels" in src else "field" if _FIELD.search(src)
                            else "grounded" if name in GROUNDED else "free")
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
        evolve, frame = (0.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)
        ev = feats.get("evolve")
        if ev is not None and ev is not False:
            secs = time.time() if ev is True else float(ev)
            evolve, frame, shift = evolution(self.seeds.get(name, zlib.crc32(name.encode())), secs,
                                             self.kinds.get(name, "free"))
            cols = shift_palette(cols, shift)

        def setu(k, v):
            if k in prog:
                prog[k].value = v
        setu("iTime", float(t))
        setu("iResolution", (float(W), float(H)))
        setu("iPanels", (float(config.PANELS_WIDE), float(config.PANELS_TALL)))
        if "clock" in feats:
            clock = float(feats["clock"])
        else:
            now = time.time()                               # with the fraction of a second: whole seconds made
            lt = time.localtime(now)                        # clock-driven forms move in visible 1 s steps
            clock = lt.tm_hour + lt.tm_min / 60.0 + (lt.tm_sec + now % 1.0) / 3600.0
        setu("iClock", clock)
        setu("iZoom", float(feats.get("zoom", 1.0)))         # 1 = as drawn (music mode zooms gently on the bass)
        setu("iEvolve", tuple(float(v) for v in evolve))
        setu("iFrame", tuple(float(v) for v in frame))
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
        img = r.render(self.name, t, {"evolve": True}, self.cols)
        if (self.H, self.W) != (H, W):
            from PIL import Image
            img = np.asarray(Image.fromarray(img.astype(np.uint8)).resize((self.W, self.H)), np.float32)
        return img


CURATED = {   # (shadow, mid, highlight) per piece - the gallery's look; the VJ recolours freely
        "dotsphere": ("#000000", "#6a5cff", "#66c8ff"),
    "eclipse": ("#000000", "#3040e0", "#ff6a2a"), "halo": ("#140808", "#b02810", "#ff9a40"),
    "tide": ("#05081a", "#1a598c", "#ccf2ff"), "aperture": ("#02020c", "#2a30d0", "#c070ff"),
    "conic": ("#1a0614", "#2048e0", "#f4ead0"), "prism": ("#ff7a2a", "#e04070", "#7a5cff"),
    # the second collection: light fields, one form in space, cut paper, fine lines, water and weather
    "ribbon": ("#0a0714", "#5a2c8c", "#f0d6ff"),
    "orbit": ("#06060c", "#3850b8", "#c8d8ff"), "dandelion": ("#0a0a12", "#6a5a9a", "#fff4d8"), # remade from the mood board: light through frosted glass, an ink orb on paper, a disc with a burning
    # rim, light escaping round dark shapes, cut-paper curves, topographic lines, a neon tube, a sphere of
    # points, one lit orb, light through blinds
    "inkdrop": ("#0c1a3a", "#2c4a80", "#efe6d2"),
    "cutcurves": ("#1a1410", "#d85a3a", "#efe2c6"), "contours": ("#0e1410", "#3a6a52", "#d8f0dc"),
    "neonarc": ("#120610", "#c0287a", "#ff9ad0"), "pointcloud": ("#04060c", "#3a5ad0", "#d8e8ff"),
    "blinds": ("#140e0a", "#a8602a", "#ffd8a0"),
    # recreated from the house's own reference images (Pinterest board + pictures sent in chat)
    "glassorb": ("#140a3a", "#3a3cff", "#ece8ff"),
    "metamorphosis": ("#140a3a", "#5a3cff", "#f0e8ff"),   # the glass orb's hour-long transformation
    "halftonewave": ("#8a2cff", "#2a6cff", "#7cff4a"),
    "dotring": ("#ff3aa0", "#ff8a2a", "#7a3cff"),
    "emberweb": ("#ff3a1a", "#2a4cff", "#ffa040"),
    "linewave": ("#30d060", "#2a8cff", "#9a40ff"),
    "slats": ("#2a1060", "#40c0ff", "#ff60c0"),
    "pixelfield": ("#ff3020", "#c8e020", "#2070ff"),
    "dotsea": ("#020a30", "#0a2a8a", "#60c0ff"),
    "crossglow": ("#0a1aa0", "#a060ff", "#ffc040"),
    "pill": ("#141c1a", "#ff8aa0", "#80ffd0"),
    "linefan": ("#c01848", "#ff60a0", "#9a50ff"),
    "bluering": ("#ff7040", "#20a0ff", "#a0f0ff"),
}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def gallery_pieces(Wd, Hd):
    """One piece per shader, each in its curated palette (newest, strongest first)."""
    order = ["metamorphosis", "glassorb", "halftonewave", "dotring", "emberweb", "linewave", "slats", "pixelfield", "dotsea", "crossglow", "pill", "linefan", "bluering", "conic", "cutcurves", "aperture", "eclipse",
             "inkdrop", "orbit", "neonarc", "prism", "contours", "pointcloud", "blinds",
             "halo", "ribbon",
             "dandelion", "dotsphere",
             "tide"]
    have = names()
    picked = [n for n in order if n in have] + [n for n in have if n not in order]
    return [ShaderPiece(Wd, Hd, n, tuple(_rgb(c) for c in CURATED.get(n, ("#08060f", "#4a3080", "#efe6ff"))))
            for n in picked]
