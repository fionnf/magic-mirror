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
W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT

BRIEF = """You are the artist in residence for a pixel LED art wall (a grid of 64 x 64 panels: 3 x 3 = 192 x 192
now, 3 wide x 4 tall = 192 x 256 portrait soon - always compose for iResolution and iPanels) in the living room of a
modern apartment in Zürich (House Fortuna, a gay flatshare). Every day you make ONE new original
artwork for the wall, written as a GLSL fragment shader. It hangs there all day like a painting:
people live with it, read, cook and fall asleep in front of it.

The house's taste (from the residents' own references) is wide: soft light fields and glowing cores,
a single form in a lot of space, flat mid-century cut paper, Bauhaus geometry, op-art stripes and
moire, conic gradient tiles, halftone dot fields, fine topographic lines, neon rods casting coloured
fans, ink on paper, Rothko and Turrell colour fields. Few colours per piece, but the wall should
range widely from day to day: cold and warm, pale and deep, colour fields as well as glows. Each
day comes with a DIRECTION (below) - follow it. Make your own piece, never a copy of a reference. Above all the house loves ONE luminous form in calm
space - like a violet glass orb with a white rim light, a halftone dot ring, a soft out-of-focus blue
ring - never busy patterns.

What makes a good piece here:
- one clear idea, generous negative space or calm fields, beautiful at a glance and rewarding
  over hours; abstract digital art in the spirit of a gallery piece - never a screensaver,
  never a club visual, never busy
- SLOW: motion should be barely perceptible from moment to moment (multiply iTime by 0.01-0.06);
  nothing may flash, strobe, blink or pulse quickly
- colour: use ONLY the scene colours iColA (deep shadow), iColB (mid tone), iColC (highlight),
  mixed and tinted - many tints of one or two neighbouring hues, never a rainbow
- it is shown on LEDs: avoid large areas of glaring pure white; full colour fields and pale grounds
  are welcome when the day's direction asks for them
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
  float iBass, iMid, iTreble, iEnergy, iLevel; vec3 iColA, iColB, iColC; vec2 iPanels (the grid of
  physical panels, e.g. 3 x 4 - seams between panels are real edges you may use); float iClock (hours since
  local midnight, 0..24, for evolution over the day)
- GLSL ES 3.00 (WebGL2) rules: no #version, no precision line, no textures, no derivatives, all
  float literals with a decimal point (1.0 not 1), loops with constant bounds <= 64
- it hangs all day, so it must keep evolving for hours and never visibly loop: drive the form with
  several very slow drifts at unrelated periods (minutes to hours) and with iClock (hours since
  midnight, 0..24). Someone glancing at 9 am, 3 pm and 11 pm should see the same piece in clearly
  different states - light, density or composition moving with the day - never a fast change
- THE DAY IS THE PIECE'S STORY. Give it an arc with iClock, like weather or a tide, not a dimmer:
  decide what the piece is at dawn, at noon, in the evening and late at night, and let something
  real change between them - a form grows, travels across the wall, multiplies, thins out, settles,
  dissolves; a horizon rises; a colour family turns from the shadow tone towards the highlight; a
  composition accumulates (with iDay) until by night it is full. The 9 am and 11 pm stills must be
  recognisably the same work and clearly different pictures.   A RELIABLE RECIPE (the checker measures the arc and rejects anything weaker): start mainImage with
      float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);   // 0 at 7 am, 0.4 at 2 pm, 0.8 at 8 pm, 1 at 11 pm
  and make at least TWO visible things depend on `day` by LARGE amounts - e.g. the main form's radius
  mix(0.10, 0.32, day) of the short side, its centre travelling 0.15-0.25 of the height, the number of
  rings or dots changing by 2-3, the colour weight moving from iColA/iColB towards iColC. Changes of
  30-50% in size, place or colour weight are needed; a 10% change is sent back. The 8 am and 11 pm
  stills must differ by 9/255 on average, and each step 8 am -> 2 pm -> 8 pm -> 11 pm by 2.5/255.
  A piece that only drifts a little or
  only changes brightness over the day will be sent back
- it must run fast on a Raspberry Pi 4 GPU at about 50,000 pixels: keep total loop iterations per pixel
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
        if fn.endswith(".json") and fn.count(".") == 1:          # 2026-10-09.json, not .memory.json
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
    # the day's arc: the same moment at 8, 14, 20 and 23 h must give clearly different pictures
    hours = [r.render(key, 400.0, {"clock": float(h), "level": 0.2,
                                   "day": [0.5 if 9 <= k < h else 0.0 for k in range(24)]}, cols) for h in (8, 14, 20, 23)]
    arc = min(float(np.abs(hours[i + 1] - hours[i]).mean()) for i in range(3))
    span = float(np.abs(hours[3] - hours[0]).mean())
    del r.progs[key]
    m = float(np.mean(means))
    if span < 9.0 or arc < 2.5:
        return False, (f"it barely evolves over the day (8 am vs 11 pm differ by {span:.1f}/255, smallest step "
                       f"between 8, 14, 20 and 23 h {arc:.1f}/255); use iClock to change the composition, "
                       "the form's size or place, its density or its colour family through the day - not just brightness. "
                       "Recipe: float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0); then change the form's radius by "
                       "at least 40% (mix(0.10, 0.32, day)), move its centre by 0.15-0.25 of the height and shift the "
                       "colour weight towards iColC with it - large changes, not 10%"), None
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


CURATOR = """You are the curator of the House Fortuna wall: a pixel LED art wall (64 x 64 panels, seams visible)
in the living room of a modern apartment in Zurich. Every day an artist proposes one generative piece. You see
four stills of it through its day (9 am, 3 pm, 8 pm with music, 11 pm) and, when there is one, the house's mood
board. The piece hangs all day, so it should have a day's arc: the same work, clearly different pictures.

The house's taste: slow, restrained and elegant; one idea per piece; few colours rather than rainbow. Within
that the wall should range widely - colour fields, pale paper grounds, cut paper, Bauhaus, op-art, halftone,
neon, ink - not the same dim warm glow on black every day. They dislike busy, multicolour, clip-art,
watercolour and lava-lamp looks. It must be beautiful enough to fall asleep in front of and read on a coarse
LED grid. The residents' favourites are single glowing forms: a violet glass orb with a white rim light, a
halftone dot ring, a soft out-of-focus blue ring. Busy pieces - stripes, checkerboards, many small elements,
fine high-contrast patterns that shimmer on LEDs - cannot score above 5. Each day has a DIRECTION; a piece
that ignores it, or looks like one of the recent days you are shown, cannot score above 5.

Judge honestly. Score 1-10. 7 means you would hang it; below 7 it goes back with one concrete, actionable
note for the artist (what to change in form, palette, density or motion). Keep the verdict to two sentences."""
CURATOR_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["score", "verdict", "note"],
                  "properties": {"score": {"type": "integer"}, "verdict": {"type": "string"},
                                 "note": {"type": "string"}}}


def _jpeg_block(img, size=384):
    import base64
    import io
    from PIL import Image
    im = img if isinstance(img, Image.Image) else Image.fromarray(np.asarray(img).astype(np.uint8))
    im = im.convert("RGB")
    im.thumbnail((size, size))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode("ascii")}}


def _moodboard_blocks():
    try:
        from display import moodboard
        data, _ = moodboard.sheet()
    except Exception:
        data = None
    if not data:
        return []
    import base64
    return [{"type": "text", "text": "The house's mood board (their newest Pinterest pins) - take the "
                                     "feeling, not a copy:"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(data).decode("ascii")}}]


def _stills(src, pal):
    """Four stills for the curator: the piece at 9 am, 3 pm, 8 pm (with music) and 11 pm."""
    from display import shaders
    from PIL import Image
    r = shaders.renderer()
    path = os.path.join(FOLDER, ".curate.frag")
    with open(path, "w") as fh:
        fh.write(src)
    r.progs.pop("path:" + path, None)
    cols = [_hex(c) for c in pal]
    day = lambda h: [0.5 if 10 <= k < h else 0.0 for k in range(24)]
    out = [r.render("path:" + path, t, f, cols) for t, f in
           ((300.0, {"clock": 9.0, "day": day(9)}), (900.0, {"clock": 15.0, "day": day(15)}),
            (1500.0, {"clock": 20.0, "day": day(20), "bass": 0.6, "energy": 0.5, "breath": 0.7, "level": 0.3,
                      "beat_phase": 0.3, "tension": 0.4}), (2100.0, {"clock": 23.0, "day": day(23)}))]
    r.progs.pop("path:" + path, None)
    os.remove(path)
    strip = Image.new("RGB", (W * 4 + 24, H), (40, 40, 40))
    for i, im in enumerate(out):
        strip.paste(Image.fromarray(im.astype(np.uint8)), (i * (W + 8), 0))
    return strip


def _recent_strip(n=5):
    """The last few days' pieces side by side, so the curator can see repetition."""
    from PIL import Image
    ims = []
    for d, _ in editions()[:n]:
        p = _path(d, "png")
        if os.path.exists(p):
            ims.append(Image.open(p).convert("RGB").resize((160, round(160 * H / W))))
    if not ims:
        return None
    strip = Image.new("RGB", (len(ims) * 168, ims[0].height), (40, 40, 40))
    for i, im in enumerate(ims):
        strip.paste(im, (i * 168, 0))
    return strip


def curate(title, statement, src, pal, direction=None):
    """-> (score, verdict, note) from Claude looking at the piece."""
    import ai_client
    from display import directions
    recent = _recent_strip()
    content = _moodboard_blocks()
    if recent is not None:
        content += [{"type": "text", "text": "The wall's recent days (newest first) - today must look clearly different:"},
                    _jpeg_block(recent, 1024)]
    content += [
        {"type": "text", "text": (directions.brief(direction) + "\n\n" if direction else "")
                                 + f"Today's proposal: \"{title}\" - {statement}\nPalette {', '.join(pal)}. "
                                 "Stills (left to right: 9 am, 3 pm, 8 pm while music plays, 11 pm):"},
        _jpeg_block(_stills(src, pal), 1024)]
    j, _, _ = ai_client.ask(CURATOR, content, max_tokens=1500, effort="low", schema=CURATOR_SCHEMA, timeout=120)
    return int(j.get("score", 0)), j.get("verdict", "").strip(), j.get("note", "").strip()


def generate(date=None, notes="", attempts=6, min_score=7, direction=None):
    """Ask Claude for today's piece, check it, save it. -> metadata dict (raises if all attempts fail)."""
    import ai_client
    from PIL import Image
    d = datetime.date.fromisoformat(date) if date else datetime.date.today()
    date = d.isoformat()
    from display import directions
    past = [m for dd, m in editions() if dd < date][:10]
    recent = [m.get("name", "") for m in past]
    recent_pals = [m["palette"] for m in past if len(m.get("palette") or []) == 3]
    if isinstance(direction, str):
        direction = next(x for x in directions.DIRECTIONS if x["name"] == direction)
    direction = direction or directions.pick(d, used=[m.get("direction") for m in past[:8]])
    print(f"[daily] {date}: direction {direction['name']!r}", flush=True)
    user = (f"Today is {d.strftime('%A %d %B %Y')} ({_season(d)} in Zürich; the season is background, "
            "not a subject - do not reach for autumn ambers).\n\n" + directions.brief(direction) +
            f"\n\nRecent titles (do something different): {', '.join(recent) or 'none yet'}. "
            f"Recent palettes (stay well away from these): {'; '.join(' '.join(p) for p in recent_pals[:5]) or 'none'}. "
            f"{notes}").strip()
    feedback = ""
    board = _moodboard_blocks()
    best = None                                       # (score, j, src, pal, verdict, attempt) of curated pieces
    tin = tout = 0
    for attempt in range(1, attempts + 1):
        msg = user + (f"\n\nYour previous attempt was rejected: {feedback}. Fix that and send the "
                      "whole piece again." if feedback else "")
        j, a_in, a_out = ai_client.ask(BRIEF, board + [{"type": "text", "text": msg}] if board else msg,
                                       max_tokens=24000, effort="low", schema=SCHEMA, timeout=400, images="drop", art=True)
        tin, tout = tin + a_in, tout + a_out
        pal = (j.get("palette") or [])[:3]
        try:
            [_hex(c) for c in pal]
            assert len(pal) == 3
        except Exception:
            feedback = "the palette must be exactly three #rrggbb colours"
            continue
        why = directions.palette_problem(pal, direction, recent_pals)
        if why:
            print(f"[daily] attempt {attempt}: {j.get('title')!r} -> {why}", flush=True)
            feedback = why
            continue
        src = j["glsl"].replace("#version 300 es", "").replace("precision highp float;", "")
        ok, reason, still = check(src, pal)
        print(f"[daily] attempt {attempt}: {j.get('title')!r} -> {reason}", flush=True)
        if ok:
            why = directions.brightness_problem(float(still.mean()), direction) or directions.visibility_problem(still)
            if why:
                ok, reason = False, why
                print(f"[daily] attempt {attempt}: {why}", flush=True)
        if not ok:
            feedback = reason
            continue
        try:
            score, verdict, note = curate(j["title"], j["statement"], src, pal, direction)
        except Exception as e:                        # the curator is a bonus, never a blocker
            print(f"[daily] curator unavailable: {e}", flush=True)
            score, verdict, note = min_score, "", ""
        print(f"[daily] curator: {score}/10 - {verdict}", flush=True)
        if best is None or score > best[0]:
            best = (score, j, src, pal, verdict, attempt, still)
        if score >= min_score:
            break
        feedback = f"the curator gave it {score}/10: {verdict} Their note: {note}"
    if best is None:
        raise RuntimeError(f"no acceptable piece after {attempts} attempts (last: {feedback})")
    score, j, src, pal, verdict, attempt, still = best   # the best curated try hangs
    os.makedirs(FOLDER, exist_ok=True)
    with open(_path(date, "frag"), "w") as fh:
        fh.write(f"// {j['title']} - art of the day {date}\n// {j['statement']}\n" + src)
    Image.fromarray(still).resize((W * 3, H * 3), Image.NEAREST).save(_path(date, "png"))
    sha = hashlib.sha256(src.encode()).hexdigest()
    meta = {"name": j["title"].strip()[:60], "description": j["statement"].strip()[:600],
            "image": f"{date}.png", "animation_source": f"{date}.frag",
            "attributes": [{"trait_type": "Date", "value": date},
                           {"trait_type": "Season", "value": _season(d)},
                           {"trait_type": "Palette", "value": " ".join(pal)},
                           {"trait_type": "Medium", "value": f"GLSL shader, {W} x {H} LED wall"},
                           {"trait_type": "Artist", "value": "Dewa and Fionn"},
                           {"trait_type": "Curator score", "value": score}],
            "listening": j.get("listening", "").strip()[:800],
            "palette": pal, "source_sha256": sha, "model": ai_client.model_name(art=True), "size": [W, H],
            "tokens": {"in": tin, "out": tout}, "attempts": attempt, "created": time.time(),
            "curator": {"score": score, "verdict": verdict}, "direction": direction["name"]}
    with open(_path(date, "json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    return meta

def online(timeout=3.0):
    """True when the internet answers (the AI artist and the gallery both need it)."""
    import socket
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            socket.create_connection((host, 443), timeout=timeout).close()
            return True
        except OSError:
            pass
    return False


_OFFLINE_NAMES = ["Variation", "Second light", "Echo", "Another hour", "Quiet study", "Afterimage", "Reprise", "Undertone"]


def compose_offline(date=None, tries=8):
    """No internet: make today's piece on the wall itself. A past edition's shader (chosen by the date)
    is hung in a new palette - one or two neighbouring hues, as the house likes - and passes the same
    checks as an AI piece. Marked "offline": it never goes to the public gallery, and the cloud's piece
    replaces it as soon as the wall is back online. -> metadata or None."""
    import colorsys
    import random
    from PIL import Image
    from display import directions
    d = datetime.date.fromisoformat(date) if date else datetime.date.today()
    date = d.isoformat()
    rnd = random.Random("offline-" + date)
    pool = [(dd, m) for dd, m in editions() if dd != date and not m.get("offline") and os.path.exists(_path(dd, "frag"))]
    if not pool:
        return None
    recent = [m.get("palette") for _, m in editions()[:5] if m.get("palette")]
    for _ in range(tries):
        src_date, src_meta = rnd.choice(pool[:60])
        with open(_path(src_date, "frag")) as fh:
            src = "\n".join(l for l in fh.read().split("\n") if not l.startswith("// "))   # drop the old label
        h = rnd.random()
        h2 = (h + rnd.choice((-1, 1)) * rnd.uniform(0.02, 0.07)) % 1.0
        to = lambda hh, ss, vv: "#%02x%02x%02x" % tuple(int(v * 255) for v in colorsys.hsv_to_rgb(hh, ss, vv))
        pal = [to(h, 0.85, rnd.uniform(0.10, 0.16)), to(h, 0.78, rnd.uniform(0.55, 0.7)), to(h2, 0.42, 1.0)]
        if any(p and abs(colorsys.rgb_to_hsv(*_hex(p[1]))[0] - h) < 0.05 for p in recent):
            continue                                       # too close to a recent day's colour
        ok, reason, still = check(src, pal)
        if ok:
            why = directions.visibility_problem(still)
            ok, reason = (False, why) if why else (True, reason)
        print(f"[daily] offline {date}: {src_meta.get('name')!r} in {pal} -> {reason}", flush=True)
        if not ok:
            continue
        name = f"{rnd.choice(_OFFLINE_NAMES)} of {src_meta.get('name', src_date)}"[:60]
        statement = f"Made on the wall while it was offline: {src_meta.get('name', src_date)} ({src_date}) in a new light."
        os.makedirs(FOLDER, exist_ok=True)
        with open(_path(date, "frag"), "w") as fh:
            fh.write(f"// {name} - art of the day {date} (offline)\n// {statement}\n" + src)
        Image.fromarray(still).resize((W * 3, H * 3), Image.NEAREST).save(_path(date, "png"))
        meta = {"name": name, "description": statement, "image": f"{date}.png", "animation_source": f"{date}.frag",
                "attributes": [{"trait_type": "Date", "value": date}, {"trait_type": "Season", "value": _season(d)},
                               {"trait_type": "Palette", "value": " ".join(pal)},
                               {"trait_type": "Medium", "value": f"GLSL shader, {W} x {H} LED wall"},
                               {"trait_type": "Artist", "value": "Dewa and Fionn"}],
                "listening": src_meta.get("listening", ""), "palette": pal, "offline": True, "remix_of": src_date,
                "size": [W, H], "created": time.time(), "direction": src_meta.get("direction", "")}
        with open(_path(date, "json"), "w") as fh:
            json.dump(meta, fh, indent=1)
        return meta
    return None


GALLERY_RAW = os.environ.get("GALLERY_RAW", "https://raw.githubusercontent.com/fionnf/magic-mirror/master/gallery/")


def refresh(date):
    """If the gallery's piece for this date has been replaced (a better one hung), fetch it again.
    -> new metadata, or None when nothing changed."""
    import requests
    if not os.path.exists(_path(date, "json")):
        return None
    try:
        with open(_path(date, "json")) as fh:
            mine = json.load(fh).get("source_sha256")
        r = requests.get(f"{GALLERY_RAW}{date}.json", timeout=20)
        if r.status_code != 200 or r.json().get("source_sha256") in (None, mine):
            return None
    except Exception:
        return None
    print(f"[daily] {date}: the gallery has a new piece", flush=True)
    return fetch(date)


def fetch(date):
    """Today's piece may already have been made in the cloud (the daily workflow): pull it from the
    public gallery into assets/daily so the wall hangs the same piece. -> metadata or None."""
    import requests
    try:
        r = requests.get(f"{GALLERY_RAW}{date}.json", timeout=20)
        if r.status_code != 200:
            return None
        meta = r.json()
        files = {}
        for ext in ("frag", "png") + (("final.png",) if meta.get("final") else ()):
            fr = requests.get(f"{GALLERY_RAW}{date}.{ext}", timeout=30)
            if ext == "final.png" and fr.status_code == 404:      # a day closed without its picture
                continue
            fr.raise_for_status()
            files[ext] = fr.content
    except Exception as e:
        print(f"[daily] gallery fetch {date}: {e}", flush=True)
        return None
    os.makedirs(FOLDER, exist_ok=True)
    for ext, data in files.items():
        with open(_path(date, ext), "wb") as fh:
            fh.write(data)
    with open(_path(date, "json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print(f"[daily] {date}: fetched {meta.get('name')!r} from the gallery", flush=True)
    return meta


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


WRITER = """You write the daily post for the Fortuna gallery: a public feed where one generative LED artwork from
a living room in Zurich is published every day. People follow it like a quiet art account.

You get the day's piece (its title, statement and the still it settled into at midnight) and what the room
heard that day: how much music there was, hour by hour (0..1), and how many songs. The piece shapes itself
around that listening (iDay), so the still is a record of the day.

Write:
- caption: 2-3 sentences, plain and warm, like a good museum label crossed with a diary entry. Say what the
  day sounded like through what the piece did (quiet morning, a loud late evening...). Never name songs,
  people or anything private. No hashtags, no emojis, no exclamation marks.
- alt: one sentence describing the image for someone who cannot see it."""
WRITER_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["caption", "alt"],
                 "properties": {"caption": {"type": "string"}, "alt": {"type": "string"}}}


def write_post(meta, mem, still_path, note=""):
    """Claude looks at the finished edition and writes its feed post. -> {'caption', 'alt'}"""
    import ai_client
    from PIL import Image
    hours = ", ".join(f"{h}h {v:.2f}" for h, v in enumerate(mem["hours"]) if v > 0.02) or "silence all day"
    if note:
        hours = note
    content = [{"type": "text", "text": f"Piece: \"{meta['name']}\" - {meta['description']}\n"
                                        f"How it listens: {meta.get('listening', '')}\n"
                                        f"Music by hour: {hours}. Songs recognised: {len(mem['songs'])}.\n"
                                        "The still at midnight:"},
               _jpeg_block(Image.open(still_path), 512)]
    j, _, _ = ai_client.ask(WRITER, content, max_tokens=1200, effort="low", schema=WRITER_SCHEMA, timeout=120)
    return {"caption": j["caption"].strip()[:600], "alt": j["alt"].strip()[:300]}


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
    try:
        meta["post"] = write_post(meta, mem, _path(date, "final.png" if r.ok else "png"))
    except Exception as e:
        print(f"[daily] post writer unavailable: {e}", flush=True)
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
    img = r.render("path:" + _path(date, "frag"), t, feats, cols)
    if _GRADE_K > 0:
        lt = time.localtime(now)
        g = np.array(day_grade(lt.tm_hour + lt.tm_min / 60.0 + lt.tm_sec / 3600.0), np.float32)
        img = np.clip(img.astype(np.float32) * g, 0, 255)
    return Image.fromarray(img.astype(np.uint8), "RGB")
