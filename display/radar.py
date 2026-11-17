"""Rain radar: the last hour of real radar, then the next two hours of forecast rain, looping over the map around Zürich.

    radar.frame(t)   -> PIL RGB image for the wall (the "radar" mode)
    radar.thumb()    -> a still with synthetic rain for the app (no network)

Where the pictures come from (no accounts, no keys):
  * PAST, REAL RADAR: RainViewer's composite radar (api.rainviewer.com), the last hour in 10-minute steps. Its tiles carry
    rain as a fixed colour palette; each pixel is turned back into an intensity class and redrawn in this wall's own
    bright rain colours (cyan light rain, green, yellow, orange, red, magenta for the heaviest).
  * NEXT 2 HOURS, FORECAST (not radar): RainViewer no longer publishes a nowcast, so the future frames are Open-Meteo's
    15-minute precipitation forecast on a grid of points over the map, smoothed into a field. It is a weather-model
    forecast, much coarser than radar, and the wall says so: the tag reads FORECAST and the map border turns amber.
  * THE HOUSE: a one-line summary for Fortunagasse ("Dry for the next 2 hours", "Rain from 14:30") from the radar
    pixel over the house now and Open-Meteo's 15-minute series for the house after that.

Everything is fetched in the background (radar every 5 minutes, the forecast grid every 30, the house every 10); a
frame never waits for the network after the first. With no internet the wall shows RADAR OFFLINE.

Drawn for the LED panel's few colour steps: near-black ground, saturated rain, bold text with a dark outline, nothing
under 11 px. The map is the Swiss border and lakes (assets/maps/switzerland.json, Natural Earth, public domain).
"""
import concurrent.futures
import datetime
import io
import json
import math
import os
import threading
import time

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import config

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
VW, VH = W, H                                           # the painting fills the whole wall
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(HERE, "assets", "maps", "switzerland.json")

HOME = (float(os.environ.get("WALL_BRIEF_LAT", "47.3715")), float(os.environ.get("WALL_BRIEF_LON", "8.5390")))
HX, HY = 0.55, 0.44                                     # where the house sits on the wall (fractions): west of centre is where weather comes from
Z = 7                                                   # RainViewer tiles stop at zoom 7
WORLD = 256 * 2 ** Z
WIN_W = 200.0                                           # the map is this many zoom-7 pixels wide (~166 km)
WIN_H = WIN_W * VH / VW
TZ = "Europe/Zurich"

PAST_FRAMES = 7                                         # the last hour: -60 .. 0 minutes
FORECAST_STEPS = 8                                      # +15 .. +120 minutes
RADAR_EVERY, GRID_EVERY, HOUSE_EVERY = 300.0, 1800.0, 600.0
GRID_COLS, GRID_ROWS = 7, 9
HOLD, GLIDE, HOLD_NOW, HOLD_END = 0.28, 0.46, 1.5, 1.8  # animation: seconds on a frame, between frames, on "now", on the last frame
SUB = 4                                                 # morph steps precomputed between two frames
WET = 0.2                                               # mm/h that counts as rain at the house
UA = {"User-Agent": "fortuna-wall-radar/1.0"}

CITIES = [("Basel", 47.5596, 7.5886), ("Bern", 46.948, 7.4474), ("Luzern", 47.0502, 8.3093)]


# --------------------------------------------------------------- geometry ---

def _world(lat, lon):
    x = (lon + 180.0) / 360.0 * WORLD
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * WORLD
    return x, y


def _unworld(x, y):
    lon = x / WORLD * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / WORLD))))
    return lat, lon


_hx, _hy = _world(*HOME)
_X0, _Y0 = _hx - HX * WIN_W, _hy - HY * WIN_H


def to_view(lat, lon):
    """Latitude/longitude -> pixel in the map viewport."""
    x, y = _world(lat, lon)
    return (x - _X0) / WIN_W * VW, (y - _Y0) / WIN_H * VH


# ----------------------------------------------------------- the palettes ---
# Rain is painted as light: indigo and electric blue for light rain, cyan, violet, magenta, then gold and a white-hot core
# for the heaviest. The past (real radar) is cool; the forecast is the same painting in warm light.

COOL = [(0.10, (80, 60, 255)), (0.25, (0, 130, 255)), (0.40, (0, 225, 255)), (0.55, (165, 90, 255)),
        (0.70, (255, 50, 210)), (0.85, (255, 170, 50)), (1.0, (255, 248, 220))]
WARM = [(0.10, (215, 40, 150)), (0.25, (255, 75, 90)), (0.40, (255, 135, 30)), (0.55, (255, 185, 0)),
        (0.70, (255, 212, 50)), (0.85, (255, 232, 120)), (1.0, (255, 250, 210))]
NIGHT = [(0.0, (30, 12, 90)), (0.4, (70, 45, 190)), (0.75, (125, 80, 240)), (1.0, (205, 165, 255))]
DAY = [(0.0, (0, 50, 120)), (0.4, (0, 120, 200)), (0.75, (70, 190, 235)), (1.0, (190, 240, 255))]
CYAN, AMBER = (0, 215, 255), (255, 176, 0)


def ramp(pal, t):
    xs = [p[0] for p in pal]
    return np.stack([np.interp(t, xs, [p[1][k] for p in pal]) for k in range(3)], -1).astype(np.float32)


def smooth(x, a, b):
    t = np.clip((np.asarray(x, np.float32) - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def blur(f, r):
    """Gaussian blur of a 0..1 field (through 8 bits, which is plenty here)."""
    im = Image.fromarray((np.clip(f, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(r))
    return np.asarray(im, np.float32) / 255.0


def make_noise(seed, cell, w=None, h=None):
    """Smooth value noise 0..1 over the viewport (or w x h), features about `cell` px."""
    w, h = w or VW, h or VH
    rng = np.random.default_rng(seed)
    gw, gh = w // cell + 3, h // cell + 3
    im = Image.fromarray(rng.random((gh, gw)).astype(np.float32), "F").resize((gw * cell, gh * cell), Image.BICUBIC)
    a = np.asarray(im, np.float32)[:h, :w]
    return (a - a.min()) / max(1e-6, float(a.max() - a.min()))


NOISE = 0.62 * make_noise(1, 12) + 0.38 * make_noise(2, 5)               # the watercolour wobble of the edges
_yy, _xx = np.mgrid[0:VH, 0:VW].astype(np.float32)
VIG = (1.0 - 0.5 * np.clip(((_xx / VW - 0.5) * 1.7) ** 2 + ((_yy / VH - 0.5) * 1.5) ** 2, 0.0, 1.0))[..., None].astype(np.float32)


def mmh_to_s(x):
    """Rain rate in mm/h -> the 0..1 intensity scale (0.15 mm/h is the faintest drawn, 25 mm/h the top)."""
    return np.clip(np.log1p(np.asarray(x, np.float32) / 0.15) / math.log1p(25.0 / 0.15), 0.0, 1.0)


def _decode_tile(rgba):
    """A RainViewer tile (RGBA) -> intensity 0..1. Faint tan = light rain, opaque cyan to dark blue = moderate to heavy."""
    a = rgba[..., 3].astype(np.float32)
    r, g, b = (rgba[..., k].astype(np.float32) for k in range(3))
    s = np.zeros(a.shape, np.float32)
    faint = (a > 0) & (a < 250)
    s[faint] = 0.05 + 0.30 * np.clip(a[faint] / 190.0, 0, 1)
    solid = a >= 250
    v = np.maximum(np.maximum(r, g), b) / 255.0
    cool = solid & (b > r)
    s[cool] = 0.40 + 0.45 * np.clip((0.93 - v[cool]) / 0.49, 0, 1)
    warm = solid & ~(b > r)
    s[warm] = 0.90 + 0.10 * (1.0 - np.clip(g[warm] / 255.0, 0, 1))
    return s


# ------------------------------------------------------------------ the map ---

def _fonts():
    cache = {}

    def font(size, bold=True):
        key = (size, bold)
        if key not in cache:
            names = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "Arial.ttf"]
            dirs = ["/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "/System/Library/Fonts/Supplemental"]
            f = None
            for p in [os.path.join(d, n) for n in names for d in dirs]:
                if os.path.exists(p):
                    try:
                        f = ImageFont.truetype(p, size)
                        break
                    except Exception:
                        pass
            if f is None:
                try:
                    f = ImageFont.load_default(size=size)
                except TypeError:
                    f = ImageFont.load_default()
            cache[key] = f
        return cache[key]
    return font


font = _fonts()


def _outlined(d, xy, s, fnt, fill=(255, 255, 255), anchor="la", stroke=2):
    d.text(xy, s, font=fnt, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0))


def make_map():
    """The map as fine luminous line work on black: -> (RGB image, lake anchor points for the ripples).
    The border and the lakes are thin glowing contours; the lakes are soft deep-blue pools."""
    S = 3
    img = Image.new("RGB", (VW * S, VH * S), (0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        with open(MAP) as fh:
            m = json.load(fh)
    except Exception:
        m = {"border": [], "lakes": []}
    pts = lambda line: [(to_view(la, lo)[0] * S, to_view(la, lo)[1] * S) for la, lo in line]
    anchors = []
    for lake in m.get("lakes", []):
        p = pts(lake)
        d.polygon(p, fill=(0, 40, 108))
        xs, ys = [q[0] / S for q in p], [q[1] / S for q in p]
        size = max(max(xs) - min(xs), max(ys) - min(ys))
        if 3 < np.mean(xs) < VW - 3 and 3 < np.mean(ys) < VH - 3 and size > 7:
            anchors.append((size, float(np.mean(xs)), float(np.mean(ys))))
    line = Image.new("RGB", img.size, (0, 0, 0))
    dl = ImageDraw.Draw(line)
    for b in m.get("border", []):
        p = pts(b)
        dl.line(p + p[:1], fill=(135, 175, 245), width=S)
    for lake in m.get("lakes", []):
        p = pts(lake)
        dl.line(p + p[:1], fill=(70, 150, 255), width=S)
    glow = line.filter(ImageFilter.GaussianBlur(S * 2.4)).point(lambda v: min(255, int(v * 0.9)))
    img = ImageChops.add(ImageChops.add(img, line), glow).resize((VW, VH), Image.LANCZOS)
    arr = np.asarray(img, np.float32) * VIG
    anchors = [(x, y) for _, x, y in sorted(anchors, reverse=True)[:3]]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), anchors


def _glow_sprite(r, colour, peak=1.0):
    """A small additive soft light (RGB) with a bright core."""
    n = int(r * 2 + 1)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    d = np.hypot(xx - r, yy - r) / r
    a = np.clip(1.0 - d, 0.0, 1.0) ** 2 * peak
    return Image.fromarray(np.clip(a[..., None] * np.array(colour, np.float32), 0, 255).astype(np.uint8), "RGB")


def _add_at(img, sprite, cx, cy):
    """Add a sprite's light onto img with its centre at (cx, cy), clipped to the picture."""
    w, h = sprite.size
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    bx0, by0, bx1, by1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if bx1 <= bx0 or by1 <= by0:
        return
    sub = sprite.crop((bx0 - x0, by0 - y0, bx1 - x0, by1 - y0))
    img.paste(ImageChops.add(img.crop((bx0, by0, bx1, by1)), sub), (bx0, by0))


def make_fixed(dry=False):
    """What never moves, on top of the rain: dark vignettes at the top and bottom for the type, sonar rings round the house,
    the towns as small lights and the house itself."""
    y = np.arange(H, dtype=np.float32)[:, None]
    a = np.maximum(np.clip(1.0 - y / 30.0, 0, 1) * 0.9, smooth(y, 150, 192) * 0.98) * np.ones((1, W), np.float32)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    d = ImageDraw.Draw(img)
    hx, hy = to_view(*HOME)
    for r in ((34,) if dry else (30, 62)):                  # ~26 km and ~52 km from the house
        d.ellipse([hx - r, hy - r, hx + r, hy + r], outline=(85, 115, 185, 255), width=1)
    f = font(11, False)
    for name, la, lo in ([] if dry else CITIES):
        x, y = to_view(la, lo)
        if 6 <= x < VW - 6 and 6 <= y < 144:
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(235, 242, 255, 255), outline=(0, 0, 0, 255))
            d.text((x + 6, y), name, font=f, fill=(200, 212, 235, 255), anchor="lm", stroke_width=2, stroke_fill=(0, 0, 0, 255))
    d.ellipse([hx - 8, hy - 8, hx + 8, hy + 8], outline=(0, 0, 0, 255), width=4)
    d.ellipse([hx - 7, hy - 7, hx + 7, hy + 7], outline=(255, 255, 255, 255), width=2)
    d.ellipse([hx - 2.5, hy - 2.5, hx + 2.5, hy + 2.5], fill=(255, 255, 255, 255))
    d.text((hx + 11, hy - 1), "Zürich", font=font(12), fill=(255, 255, 255, 255), anchor="lm", stroke_width=2, stroke_fill=(0, 0, 0, 255))
    return img


# --------------------------------------------------------------------- data ---

def _tiles_needed():
    return [(tx, ty) for ty in range(int(_Y0 // 256), int((_Y0 + WIN_H) // 256) + 1)
            for tx in range(int(_X0 // 256), int((_X0 + WIN_W) // 256) + 1)]


def _crop_view(mosaic, tx0, ty0):
    """A float mosaic of tiles -> the map viewport (bilinear resize of exactly the window)."""
    im = Image.fromarray(mosaic.astype(np.float32), "F")
    l, t = _X0 - tx0 * 256, _Y0 - ty0 * 256
    out = im.resize((VW, VH), Image.BILINEAR, box=(l, t, l + WIN_W, t + WIN_H))
    return np.asarray(out, np.float32)


def fetch_radar_frames(have=None):
    """-> [(epoch, intensity field (VH, VW))] for the last hour of radar. `have` = {epoch: field} already fetched."""
    import requests
    have = have or {}
    j = requests.get("https://api.rainviewer.com/public/weather-maps.json", timeout=12, headers=UA).json()
    host, past = j["host"], j["radar"]["past"][-PAST_FRAMES:]
    tiles = _tiles_needed()
    tx0, ty0 = min(t[0] for t in tiles), min(t[1] for t in tiles)
    nx, ny = max(t[0] for t in tiles) - tx0 + 1, max(t[1] for t in tiles) - ty0 + 1

    def one(args):
        path, (tx, ty) = args
        r = requests.get(f"{host}{path}/256/{Z}/{tx}/{ty}/2/1_0.png", timeout=12, headers=UA)
        r.raise_for_status()
        return _decode_tile(np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA")))

    out = []
    todo = [p for p in past if p["time"] not in have]
    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        results = {}
        jobs = {(p["time"], t): ex.submit(one, (p["path"], t)) for p in todo for t in tiles}
        for key, fut in jobs.items():
            try:
                results[key] = fut.result()
            except Exception:
                results[key] = None
    for p in past:
        if p["time"] in have:
            out.append((p["time"], have[p["time"]]))
            continue
        mosaic = np.zeros((ny * 256, nx * 256), np.float32)
        ok = 0
        for tx, ty in tiles:
            a = results.get((p["time"], (tx, ty)))
            if a is not None:
                mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = a
                ok += 1
        if ok:
            out.append((p["time"], np.clip(_crop_view(mosaic, tx0, ty0), 0.0, 1.0)))
    return out


def _grid_points():
    """Latitudes (north to south) and longitudes (west to east) of the forecast grid, a little beyond the map."""
    (la0, lo0), (la1, lo1) = _unworld(_X0 - 8, _Y0 - 8), _unworld(_X0 + WIN_W + 8, _Y0 + WIN_H + 8)
    lats = np.linspace(la0, la1, GRID_ROWS)
    lons = np.linspace(lo0, lo1, GRID_COLS)
    return lats, lons, (la0, lo0, la1, lo1)


def _slots(now):
    """The next FORECAST_STEPS quarter-hour times after now (local naive datetimes) with their offsets in minutes."""
    base = now.replace(second=0, microsecond=0)
    base = base.replace(minute=(base.minute // 15) * 15) + datetime.timedelta(minutes=15)
    return [base + datetime.timedelta(minutes=15 * k) for k in range(FORECAST_STEPS)]


def fetch_forecast(now):
    """-> list of (slot datetime, intensity field (VH, VW)) from Open-Meteo's 15-minute rain on a grid of points."""
    import requests
    lats, lons, _ = _grid_points()
    la = [round(float(a), 3) for a in lats for _ in lons]
    lo = [round(float(b), 3) for _ in lats for b in lons]
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&minutely_15=precipitation&forecast_minutely_15=14"
           "&hourly=cloud_cover&forecast_hours=3&timezone=Europe%%2FZurich" % (",".join(map(str, la)), ",".join(map(str, lo))))
    res = requests.get(url, timeout=20, headers=UA).json()
    if not isinstance(res, list):
        res = [res]
    times = res[0]["minutely_15"]["time"]
    slots = _slots(now)
    try:                                                      # cloud cover over the next hours, as a field (for the dry-weather sky)
        cc = np.array([np.mean(r["hourly"]["cloud_cover"]) for r in res], np.float32).reshape(GRID_ROWS, GRID_COLS) / 100.0
        fetch_forecast.clouds = np.clip(np.asarray(Image.fromarray(cc, "F").resize((VW, VH), Image.BICUBIC), np.float32), 0.0, 1.0)
    except Exception:
        fetch_forecast.clouds = None
    out = []
    for slot in slots:
        key = slot.strftime("%Y-%m-%dT%H:%M")
        if key not in times:
            continue
        k = times.index(key)
        grid = np.array([(r["minutely_15"]["precipitation"][k] or 0.0) * 4.0 for r in res], np.float32).reshape(GRID_ROWS, GRID_COLS)
        im = Image.fromarray(grid, "F").resize((VW, VH), Image.BICUBIC)       # mm/h, smoothed
        out.append((slot, mmh_to_s(np.clip(np.asarray(im, np.float32), 0.0, None))))
    return out


def fetch_house(now):
    """-> [(slot datetime, mm/h)] for the house, the next two hours."""
    import requests
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&minutely_15=precipitation&forecast_minutely_15=14"
           "&hourly=precipitation&forecast_hours=14&timezone=Europe%%2FZurich" % HOME)
    j = requests.get(url, timeout=12, headers=UA).json()
    m = j["minutely_15"]
    try:                                                      # the next rain after the two hours shown (within about 14 h)
        horizon = now + datetime.timedelta(hours=2)
        fetch_house.later = next((datetime.datetime.strptime(t, "%Y-%m-%dT%H:%M") for t, v in zip(j["hourly"]["time"], j["hourly"]["precipitation"])
                                  if (v or 0) >= WET and datetime.datetime.strptime(t, "%Y-%m-%dT%H:%M") > horizon), None)
    except Exception:
        fetch_house.later = None
    out = []
    for slot in _slots(now):
        key = slot.strftime("%Y-%m-%dT%H:%M")
        if key in m["time"]:
            out.append((slot, (m["precipitation"][m["time"].index(key)] or 0.0) * 4.0))
    return out


def summarize(now_s_at_house, house):
    """One line about the rain at the house: (text, colour)."""
    raining = now_s_at_house is not None and now_s_at_house >= 0.16
    series = house or []
    if raining:
        dry = next((s for s, v in series if v < WET), None)
        if series and dry is not None:
            return f"Raining now, dry from {dry.strftime('%H:%M')}", (80, 200, 255)
        return ("Raining now, for 2 h+" if series else "Raining now"), (80, 200, 255)
    if not series:
        return ("Dry at the house now" if now_s_at_house is not None else "No rain data"), (230, 235, 245)
    first = next((i for i, (s, v) in enumerate(series) if v >= WET), None)
    if first is None:
        return "Dry for the next 2 hours", (120, 255, 150)
    peak = max(v for _, v in series)
    kind = "heavy" if peak >= 4 else "light" if peak < 1 else "steady"
    return f"Rain from {series[first][0].strftime('%H:%M')} ({kind})", (255, 190, 60)


# ------------------------------------------------------------ the picture ---

def _label_for(off):
    """'-25 MIN' / '+40 MIN': the offset from now, rounded to 5 minutes (the newest radar picture is labelled NOW by the caller)."""
    m = max(5, 5 * int(round(abs(off) / 5.0)))
    return f"{'+' if off > 0 else '-'}{m} MIN"


def _shift(a, b):
    """Rough motion (dx, dy) in px of the rain pattern from field a to b, by phase correlation; (0, 0) when there is too little rain."""
    if (a > 0.2).sum() < 60 or (b > 0.2).sum() < 60:
        return 0.0, 0.0
    A, B = np.fft.rfft2(a - a.mean()), np.fft.rfft2(b - b.mean())
    R = A.conj() * B
    r = np.fft.irfft2(R / (np.abs(R) + 1e-9), s=a.shape)
    iy, ix = np.unravel_index(int(np.argmax(r)), r.shape)
    iy = iy - a.shape[0] if iy > a.shape[0] // 2 else iy
    ix = ix - a.shape[1] if ix > a.shape[1] // 2 else ix
    return (float(ix), float(iy)) if math.hypot(ix, iy) <= 22 else (0.0, 0.0)


def _translate(im, dx, dy):
    return im.transform(im.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy), resample=Image.BILINEAR)


def paint(s, pal):
    """One rain field -> its light (RGB, additive over the map): soft ink blooms with a wobbly edge, and a halo round them."""
    t = np.clip(blur(s, 1.1) * (0.78 + 0.44 * NOISE), 0.0, 1.0)
    core = ramp(pal, t) * smooth(t, 0.10, 0.16)[..., None]
    h = blur(s, 6.0)
    halo = ramp(pal, np.clip(h * 1.4, 0.0, 1.0)) * (smooth(h, 0.015, 0.24)[..., None] * 0.38)
    return Image.fromarray(np.clip((core + halo) * VIG, 0, 255).astype(np.uint8), "RGB")


class Show:
    """The whole painting for one set of data, precomputed: the map, a layer of light per frame, the morphs between them,
    the type for every frame. Rendering a frame is then a few blends and a few lines."""

    ARC = (16.0, W - 16.0, 216.0, 10.0)                        # the time arc along the bottom: x from, x to, y at the ends, how far it bows up

    def __init__(self, frames, summary, hint, dry, hour, clouds):
        self.frames, self.K, self.summary, self.hint, self.dry = frames, len(frames), summary, hint, dry
        self.now_i = max([i for i, f in enumerate(frames) if f["kind"] == "radar"] or [0])     # the newest radar picture is "now"
        self.sky = NIGHT if (hour < 7 or hour >= 19) else DAY
        self.base, lakes = make_map()
        self.fixed = make_fixed(dry)
        self.layers = [paint(f["s"], COOL if f["kind"] == "radar" else WARM) for f in frames]
        self.sub = []                                          # between two frames the rain drifts along its own motion
        for k in range(self.K - 1):
            a, b = self.layers[k], self.layers[k + 1]
            dx, dy = _shift(frames[k]["s"], frames[k + 1]["s"])
            subs = [a]
            for j in range(1, SUB):
                f = j / SUB
                subs.append(Image.blend(_translate(a, f * dx, f * dy), _translate(b, -(1 - f) * dx, -(1 - f) * dy), f))
            subs.append(b)
            self.sub.append(subs)
        hx, hy = to_view(*HOME)
        self.pts = [(hx, hy)] + lakes                          # where ripples bloom when it rains: the house, then the lakes
        self.level = []
        for f in frames:
            s_ = f["s"]
            self.level.append([float(s_[max(0, int(y) - 1):int(y) + 2, max(0, int(x) - 1):int(x) + 2].max()) for x, y in self.pts])
        rng = np.random.default_rng(11)
        self.P = np.column_stack([rng.random(190) * W, rng.random(190) * H, 60 + rng.random(190) * 70,
                                  0.14 + rng.random(190) * 0.76, 0.0 * rng.random(190)]).astype(np.float32)
        self.stars = np.column_stack([rng.random(40) * W, rng.random(40) * H * 0.42, rng.random(40) * 6.28]).astype(np.float32)
        self.orb_c, self.orb_w = _glow_sprite(15, CYAN, 0.9), _glow_sprite(15, AMBER, 0.9)
        self.orb_core = _glow_sprite(5, (255, 255, 255), 1.0)
        if dry:                                                # a calm sky: ink clouds that drift, a glow that breathes
            self.cloud_big = self._clouds(clouds)
            col = ramp(self.sky, np.array([0.85]))[0]
            self.breath = [_glow_sprite(78, tuple(col * k), 1.0) for k in (0.30, 0.36, 0.42, 0.48, 0.54, 0.60)]
        self.ui = [self._ui(i) for i in range(self.K)]
        self.sched, acc = [], 0.0                              # hold on each frame, glide to the next, linger on "now" and on the last
        for i in range(self.K):
            hold = HOLD_NOW if i == self.now_i else HOLD_END if i == self.K - 1 else HOLD
            self.sched.append((acc, acc + hold, i))
            acc += hold
            if i < self.K - 1:
                self.sched.append((acc, acc + GLIDE, i + 0.5))
                acc += GLIDE
        self.length = acc

    # -- the sky when it is dry
    def _clouds(self, field):
        PAD = 26
        c = np.full((VH, VW), 0.5, np.float32) if field is None else field
        big = np.pad(c, ((0, 0), (PAD, PAD)), mode="edge")
        pat = make_noise(7, 34, VW + 2 * PAD, VH) * 0.7 + make_noise(8, 14, VW + 2 * PAD, VH) * 0.3
        v = 0.55 * big + (pat - 0.5) * 1.25 + 0.06
        ink = smooth(v, 0.52, 0.60)[..., None]
        rim = np.clip(ink[..., 0] - smooth(v, 0.60, 0.74), 0, 1)[..., None]
        body = ramp(self.sky, 0.18 + 0.22 * pat) * ink * 0.80
        vig = np.pad(VIG, ((0, 0), (PAD, PAD), (0, 0)), mode="edge")
        out = np.clip((body + ramp(self.sky, np.full(pat.shape, 0.95, np.float32)) * rim * 0.75) * vig, 0, 255)
        return Image.fromarray(out.astype(np.uint8), "RGB")

    # -- the type for one frame
    def _arc_xy(self, pos):
        x0, x1, ye, sag = self.ARC
        u = 0.5 if self.K == 1 else pos / (self.K - 1)
        return x0 + (x1 - x0) * u, ye - 4 * sag * u * (1 - u)

    def _ui(self, idx):
        f = self.frames[idx]
        radar = f["kind"] == "radar"
        col = CYAN if radar else AMBER
        pal = COOL if radar else WARM
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        K = lambda c, a=255: tuple(c) + (a,)
        out = lambda d_, xy, t, fnt, fill, anchor="la", st=2: d_.text(xy, t, font=fnt, fill=K(fill), anchor=anchor, stroke_width=st, stroke_fill=(0, 0, 0, 255))
        out(d, (7, 13), "RAIN RADAR", font(14), (255, 255, 255), "lm")
        tag = "RADAR" if radar else "FORECAST"
        tf = font(12)
        tw = d.textlength(tag, font=tf) + 14
        d.rounded_rectangle([W - 6 - tw, 3, W - 6, 23], radius=9, fill=K(col))
        d.text((W - 6 - tw / 2, 13), tag, font=tf, fill=(0, 0, 10, 255), anchor="mm")
        # the time, big and plain
        lab = "NOW" if idx == self.now_i and radar else _label_for(f["off"])
        clock = f["clock"]
        cf = font(16)
        cw = d.textlength(clock, font=cf)
        if lab == "NOW":
            out(d, (8, 184), "NOW", font(40), (255, 255, 255), "lm", 3)
        else:
            txt = lab[0] + lab.split()[0][1:]
            bf = font(38 if len(txt) <= 3 else 33)
            w = d.textlength(txt, font=bf)
            out(d, (8, 184), txt, bf, col, "lm", 3)
            if 8 + w + 5 + 40 < W - 8 - cw - 4:
                out(d, (8 + w + 5, 193), "MIN", font(16), col, "lm", 2)
        out(d, (W - 8, 178), clock, cf, (240, 244, 252), "rm", 2)
        # the arc: every frame a node, lit up to this one; the moving orb is added per frame
        n = self.K
        pts = [self._arc_xy(i * (n - 1) / 60.0) for i in range(61)] if n > 1 else [self._arc_xy(0)] * 2
        cut_at = (idx / max(1, n - 1)) * 60
        for i in range(60):
            seg = pts[i:i + 2]
            past = (i / 60.0) * (n - 1) <= self.now_i
            lit = i <= cut_at
            c = (CYAN if past else AMBER) if lit else (95, 105, 140)
            d.line(seg, fill=K(c), width=2)
        for i, g in enumerate(self.frames):
            x, y = self._arc_xy(i)
            c = CYAN if g["kind"] == "radar" else AMBER
            r = 3 if i <= idx else 2
            d.ellipse([x - r, y - r, x + r, y + r], fill=K(c if i <= idx else (95, 105, 140)), outline=(0, 0, 0, 255))
        x, y = self._arc_xy(self.now_i)                      # a tick where the past ends and the forecast begins
        d.line([(x, y - 8), (x, y - 4)], fill=K((255, 255, 255)), width=2)
        # the verdict
        text, tc = (self.hint, (190, 205, 235)) if self.dry else self.summary
        vf = font(13)
        while vf.size > 11 and d.textlength(text, font=vf) > W - 10:
            vf = font(vf.size - 1)
        out(d, (W // 2, 232), text, vf, tc, "mm", 2)
        if not self.dry:                                       # the legend: the colours of this part of the loop
            cx0, cx1 = 52, 140
            for x in range(cx0, cx1):
                c = ramp(pal, np.array(0.1 + 0.9 * (x - cx0) / (cx1 - cx0), np.float32))
                d.line([(x, 245), (x, 254)], fill=K(tuple(int(v) for v in c)))
            lf = font(11, False)
            out(d, (5, 250), "light", lf, (210, 220, 240), "lm", 1)
            out(d, (W - 5, 250), "heavy", lf, (210, 220, 240), "rm", 1)
        if self.dry:                                           # a big, calm statement
            out(d, (W // 2, 52), "DRY", font(56), (255, 255, 255), "mm", 4)
            sub = "for the next 2 hours" if self.summary[0].startswith("Dry for") else "at the house now"
            out(d, (W // 2, 88), sub, font(15), (225, 235, 255), "mm", 2)
        return img

    def _pos(self, tt):
        tt %= self.length
        for a, b, i in self.sched:
            if tt < b:
                return i, (tt - a) / (b - a)
        return self.K - 1, 0.0

    # -- one frame
    def render(self, tt):
        pos, frac = self._pos(tt)
        if float(pos).is_integer():
            layer, nearest, upos = self.layers[int(pos)], int(pos), float(pos)
        else:
            i0 = int(math.floor(pos))
            x = frac * SUB
            j = min(SUB - 1, int(x))
            layer = Image.blend(self.sub[i0][j], self.sub[i0][j + 1], x - j)
            nearest = i0 + (1 if frac > 0.5 else 0)
            upos = i0 + frac
        img = ImageChops.add(self.base, layer)
        tl = tt % self.length
        if self.dry:
            br = int((0.5 + 0.5 * math.sin(tl * 0.9)) * (len(self.breath) - 1) + 0.5)
            _add_at(img, self.breath[br], W / 2, 56)
            dx = int(20 * math.sin(tt * 0.11))
            img = ImageChops.add(img, self.cloud_big.crop((26 + dx, 0, 26 + dx + W, H)))
        d = ImageDraw.Draw(img)
        f = self.frames[nearest]
        warm = f["kind"] == "forecast"
        if self.dry:                                           # a few stars that breathe
            for x, y, ph in self.stars:
                v = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(tt * 0.7 + ph))
                c = int(70 + 170 * v)
                d.point((x, y), fill=(c, c, min(255, c + 25)))
        else:                                                  # rain as falling light, thicker where it is heavier
            s_ = f["s"]
            col = (255, 226, 172) if warm else (198, 236, 255)
            for x, y0, sp, thr, _ in self.P:
                y = (y0 + tt * sp) % H
                v = s_[int(y), int(x)]
                if v > thr:
                    ln = 4 + v * 9
                    d.line([(x - 0.28 * ln, y - ln), (x, y)], fill=col, width=1)
        rc = (255, 215, 150) if warm else (170, 232, 255)      # ripples on the lakes and at the house when rain reaches them: added light
        ripples = None
        for a, (ax, ay) in enumerate(self.pts):
            if self.level[nearest][a] > 0.2:
                if ripples is None:
                    ripples = Image.new("RGB", (W, H), (0, 0, 0))
                    dr = ImageDraw.Draw(ripples)
                for r in range(2):
                    ph = (tt * 0.5 + a * 0.37 + r * 0.5) % 1.0
                    rad = 2 + ph * (13 if a == 0 else 7)
                    c = tuple(int(k * (1.0 - ph) ** 1.5) for k in rc)
                    dr.ellipse([ax - rad, ay - rad * 0.55, ax + rad, ay + rad * 0.55], outline=c)
        if ripples is not None:
            img = ImageChops.add(img, ripples)
        img.paste(self.fixed, (0, 0), self.fixed)
        img.paste(self.ui[nearest], (0, 0), self.ui[nearest])
        ox, oy = self._arc_xy(upos)                            # the orb that travels along time
        _add_at(img, self.orb_w if upos > self.now_i + 0.01 else self.orb_c, ox, oy)
        _add_at(img, self.orb_core, ox, oy)
        return img


def build_show(radar, forecast, house, now_dt, clouds=None, later=None):
    """radar = [(epoch, field)], forecast = [(slot, field)], house = [(slot, mm/h)] -> Show."""
    now_ts = now_dt.timestamp()
    frames = []
    for ts, s_ in radar:
        t = datetime.datetime.fromtimestamp(ts, now_dt.tzinfo)
        frames.append({"off": (ts - now_ts) / 60.0, "kind": "radar", "clock": t.strftime("%H:%M"), "s": s_})
    for slot, s_ in forecast:
        frames.append({"off": (slot.replace(tzinfo=now_dt.tzinfo).timestamp() - now_ts) / 60.0, "kind": "forecast",
                       "clock": slot.strftime("%H:%M"), "s": s_})
    hx, hy = to_view(*HOME)
    at_house = None
    radar_frames = [f for f in frames if f["kind"] == "radar"]
    if radar_frames:
        s_ = radar_frames[-1]["s"]
        at_house = float(s_[int(min(VH - 1, max(0, hy))), int(min(VW - 1, max(0, hx)))])
    summary = summarize(at_house, house)
    if later is not None:
        when = later.strftime("%H:%M") if later.date() == now_dt.date() else later.strftime("%a %H:%M")
        hint = f"Next rain about {when}"
    else:
        hint = "No rain in sight for 14 h"
    dry = summary[0].startswith("Dry") and not any((f["s"] > 0.2).sum() > 25 for f in frames)
    return Show(frames, summary, hint, dry, now_dt.hour, clouds)


# ---------------------------------------------------------------- the feed ---

class Feed:
    """Keeps the picture fresh in a background thread; frame() only ever reads the latest finished Show."""

    def __init__(self):
        self.show = None
        self.error = ""
        self.ready = threading.Event()
        self._radar, self._forecast, self._house = {}, [], []
        self._t_radar = self._t_grid = self._t_house = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def _now(self):
        try:
            from zoneinfo import ZoneInfo
            return datetime.datetime.now(ZoneInfo(TZ))
        except Exception:
            return datetime.datetime.now().astimezone()

    def refresh(self):
        now = self._now()
        t = time.time()
        changed = False
        errors = []
        if t - self._t_radar >= RADAR_EVERY or not self._radar:
            try:
                got = fetch_radar_frames(self._radar)
                self._radar = {ts: s for ts, s in got}
                self._t_radar, changed = t, True
            except Exception as e:
                errors.append(f"radar: {e}")
        local = now.replace(tzinfo=None)
        if t - self._t_grid >= GRID_EVERY or not self._forecast:
            try:
                self._forecast = fetch_forecast(local)
                self._t_grid, changed = t, True
            except Exception as e:
                errors.append(f"forecast: {e}")
        if t - self._t_house >= HOUSE_EVERY or not self._house:
            try:
                self._house = fetch_house(local)
                self._t_house, changed = t, True
            except Exception as e:
                errors.append(f"house: {e}")
        self.error = "; ".join(errors)
        if errors:
            print(f"[radar] {self.error}", flush=True)
        # forecast slots that have gone by are dropped; the wall keeps showing what it has
        fc = [(s, f) for s, f in self._forecast if s.replace(tzinfo=now.tzinfo) > now - datetime.timedelta(minutes=1)]
        radar = sorted(self._radar.items())
        if radar or fc:
            if changed or self.show is None:
                self.show = build_show(radar, fc, [(s, v) for s, v in self._house if s.replace(tzinfo=now.tzinfo) > now], now,
                                       clouds=getattr(fetch_forecast, "clouds", None), later=getattr(fetch_house, "later", None))
            self.ready.set()

    def _run(self):
        while True:
            try:
                self.refresh()
            except Exception as e:
                self.error = str(e)
                print(f"[radar] {e}", flush=True)
            self.ready.set()
            time.sleep(60.0 if self.show is None else 60.0)


def offline_card():
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for r in (22, 46, 72):                                    # sonar rings with nothing on them
        d.ellipse([W / 2 - r, H * 0.40 - r, W / 2 + r, H * 0.40 + r], outline=(95, 125, 195), width=1)
    d.text((W // 2, 18), "RAIN RADAR", font=font(15), fill=(255, 255, 255), anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
    d.text((W // 2, int(H * 0.40)), "OFFLINE", font=font(32), fill=(255, 176, 0), anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
    d.text((W // 2, int(H * 0.68)), "No radar data yet", font=font(14, False), fill=(235, 240, 250), anchor="mm")
    d.text((W // 2, int(H * 0.75)), "Trying again soon", font=font(14, False), fill=(235, 240, 250), anchor="mm")
    return img


_feed = None
_t0 = None


def frame(t):
    global _feed, _t0
    if _feed is None:
        _feed = Feed()
        _feed.ready.wait(20)                                  # the first picture waits for the network, a few seconds
    if _t0 is None:
        _t0 = t
    show = _feed.show
    if show is None:
        return offline_card()
    return show.render(t - _t0)


# ------------------------------------------------------------- sample data ---

def sample_show(kind="rain"):
    """Synthetic weather for the app's thumbnail and for tests. kind: "rain" (a band moving north-east, easing, then a new
    shower) or "dry" (nothing on the radar, a cloudy sky, rain only much later)."""
    now = datetime.datetime.now().astimezone()
    yy, xx = np.mgrid[0:VH, 0:VW].astype(np.float32)
    zero = np.zeros((VH, VW), np.float32)

    def field(minute):
        if kind == "dry":
            return zero
        x0 = 10 + (minute + 60) * 0.85
        y0 = VH * 0.95 - (minute + 60) * 0.95
        dd = ((xx - x0) * 0.8 + (yy - y0) * 0.6)
        band = np.exp(-(dd / 17.0) ** 2) * (0.62 + 0.14 * np.sin(xx / 9.0 + yy / 7.0) + 0.1 * np.sin(xx / 4.0 - yy / 5.0))
        cell = 0.85 * np.exp(-(((xx - (150 - minute * 0.3)) / 16.0) ** 2 + ((yy - 70) / 13.0) ** 2))
        v = np.clip(band + cell * (1.0 if minute > 20 else 0.0), 0, 1)
        return np.where(v > 0.12, v, 0).astype(np.float32)
    radar = [(now.timestamp() + m * 60.0, field(m)) for m in range(-60, 1, 10)]
    forecast = [((now + datetime.timedelta(minutes=m)).replace(tzinfo=None), field(m)) for m in range(15, 121, 15)]
    house = [((now + datetime.timedelta(minutes=m)).replace(tzinfo=None), 0.0 if (kind == "dry" or m < 45) else 1.8) for m in range(15, 121, 15)]
    clouds = np.clip(0.35 + 0.6 * make_noise(21, 60), 0, 1) if kind == "dry" else None
    later = (now + datetime.timedelta(hours=5)).replace(tzinfo=None) if kind == "dry" else None
    return build_show(radar, forecast, house, now, clouds=clouds, later=later)


_samples = {}


def thumb(kind="rain"):
    """A still for the app: synthetic weather, no network."""
    if kind not in _samples:
        _samples[kind] = sample_show(kind)
    sh = _samples[kind]
    return sh.render(next(a for a, b, i in sh.sched if i == sh.now_i + 3) + 0.1)
