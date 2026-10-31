"""Ländle: the Remstal as living art. A long German intro (display/laend_intro.py: the "Nett hier" sticker,
then two girls and a guy picking apples in Bittenfeld, walking the vineyards to Korb and toasting new wine
in Schorndorf), then the map of the valley for as long as you like.

The map (assets/maps/laend.npz, tools/build_laend.py): north up, 107 m per LED, Bittenfeld top left,
Korb in the middle, Schorndorf right. Painted once as a night picture: hillshaded relief, every vineyard a
band of terrace lines (plum in the shade, gold in the sun), orchards as pale dots, woods as dark dither,
the towns as warm windows, the Rems and its brooks as blue water. Over it, every frame: evening fog lying in
the valley, the river running, windows twinkling, fireflies, drifting apple-blossom/leaves, and slow pulses
from the three places the piece is about.

frame(t): t is seconds since the piece started; the intro plays first.
"""
import json
import math
import os
import time

import numpy as np
from PIL import Image, ImageDraw

import config
from display import pixelfont

W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "assets", "maps", "laend.npz")
HEROES = ("Bittenfeld", "Korb", "Schorndorf")
MINOR = ("Waiblingen", "Winnenden", "Backnang", "Weinstadt", "Fellbach", "Esslingen am Neckar", "Rudersberg", "Remshalden")
GOLD, PLUM = np.array((255, 196, 70), np.float32), np.array((158, 38, 120), np.float32)
_B4 = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) + 0.5) / 16.0
REVEAL = 7.0                                        # seconds the map takes to ink itself in


def _noise(h, w, seed, cells):
    """Smooth tileable value noise, h x w, 0..1."""
    import cv2
    rs = np.random.RandomState(seed)
    ch, cw = cells
    g = rs.rand(ch, cw).astype(np.float32)
    g = np.tile(g, (3, 3))
    big = cv2.resize(g, (cw * 3 * (w // cw), ch * 3 * (h // ch)), interpolation=cv2.INTER_CUBIC)
    oy, ox = big.shape[0] // 3, big.shape[1] // 3
    return np.clip(big[oy:oy + h, ox:ox + w], 0, 1)


class Map:
    def __init__(self):
        import cv2
        self.cv2 = cv2
        z = np.load(DATA)
        self.meta = json.loads(bytes(z["meta"]).decode())
        S = self.meta["SUP"]
        fh, fw = H * S, W * S
        el = z["elev"].astype(np.float32)
        m = {k: np.unpackbits(z[k], axis=1)[:, :fw].astype(np.float32) for k in ("vineyard", "orchard", "forest", "urban", "water", "farm")}
        riv = z["rivers"].astype(np.float32) / 255.0
        stm = z["streams"].astype(np.float32) / 255.0

        def down(a):
            return cv2.resize(a, (W, H), interpolation=cv2.INTER_AREA)
        elm = cv2.GaussianBlur(el, (0, 0), 2.0)
        dzdx = np.gradient(elm, axis=1) / (self.meta["m_per_led"] / S)
        dzdy = np.gradient(elm, axis=0) / (self.meta["m_per_led"] / S)
        ex = 2.6                                                     # relief exaggeration
        nx, ny, nz = -dzdx * ex, -dzdy * ex, np.ones_like(elm)
        ln = np.sqrt(nx * nx + ny * ny + 1)
        L = np.array((-0.62, -0.58, 0.52), np.float32)
        L /= np.linalg.norm(L)
        shade = np.clip((nx * L[0] + ny * L[1] + nz * L[2]) / ln, 0, 1)
        self.shade = down(shade)                                     # 0 shadow .. 1 lit, around 0.5 on the flat
        lo, hi = float(np.percentile(el, 1)), float(np.percentile(el, 99))
        self.elev = down(elm)
        e01 = np.clip((self.elev - lo) / (hi - lo), 0, 1)
        self.e01 = e01
        sh = np.clip(0.18 + 1.25 * (self.shade - 0.18), 0.05, 1.3)[..., None]
        # land: deep indigo valleys to warm sandstone ridges
        valley, ridge = np.array((10, 12, 38), np.float32), np.array((96, 74, 62), np.float32)
        land = valley + (ridge - valley) * e01[..., None]
        img = land * sh
        fm = down(m["farm"])[..., None]
        img = img * (1 - fm * 0.7) + np.array((46, 58, 26), np.float32) * sh * fm * 0.7
        fo = down(m["forest"])
        dith = (_B4[np.arange(H)[:, None] % 4, np.arange(W)[None, :] % 4] < fo * 0.9).astype(np.float32)
        wood = np.array((4, 30, 26), np.float32) * (0.5 + 1.0 * sh)
        img = img * (1 - fo[..., None] * 0.65) + wood * fo[..., None] * 0.65
        img = img + (np.array((10, 52, 40), np.float32) * dith[..., None] * fo[..., None] * 0.9)
        # orchards: pale blossom-green dots on a spaced grid
        orc = down(m["orchard"])
        yy, xx = np.mgrid[0:H, 0:W]
        dots = (((xx + (yy // 2) % 2) % 3 == 0) & (yy % 2 == 0)).astype(np.float32)
        img = img + np.array((120, 200, 90), np.float32) * (dots * orc * 0.85)[..., None] + np.array((20, 40, 16), np.float32) * orc[..., None]
        # vineyards: terrace lines that follow the contours, gold where the sun hits, plum in the shade
        vin = m["vineyard"]
        ph = el / 4.5
        stripe = (np.sin(ph * 2 * math.pi) > 0.1).astype(np.float32) * vin
        vs, vf = down(stripe), down(vin)
        lit = np.clip((self.shade - 0.25) * 2.0, 0, 1)[..., None]
        vcol = PLUM + (GOLD - PLUM) * lit
        vg = cv2.GaussianBlur(vf, (0, 0), 1.6)[..., None]
        img = img * (1 - vf[..., None] * 0.6) + vcol * (0.25 + 1.0 * vs[..., None]) * vf[..., None] + vcol * vg * 0.35
        # towns: dark blocks; windows lit at runtime
        ur = down(m["urban"])
        img = img * (1 - ur[..., None] * 0.6) + np.array((46, 30, 40), np.float32) * ur[..., None]
        self.urban = ur
        rs = np.random.RandomState(5)
        self.win = (rs.rand(H, W) < 0.30 * ur).astype(np.float32)      # a lit window here?
        self.win_ph = rs.rand(H, W).astype(np.float32) * 6.28
        # water
        wa = np.clip(down(m["water"]) + down(riv) * 1.6, 0, 1)
        self.water = wa
        self.brook = np.clip(down(stm) * 0.9, 0, 1) * (1 - wa)
        self.base = np.clip(img, 0, 255)
        # contour glints: a faint line every 25 m of height
        self.contour = down((np.abs(((el / 25.0) % 1.0) - 0.5) > 0.47).astype(np.float32)) * 0.10
        # rails (dim, the live trains ride on them) and the fog
        rail = np.zeros((H, W), np.uint8)
        for r in self.meta["rails"]:
            pts = np.array(r["pts"], np.float32)
            cv2.polylines(rail, [np.round(pts).astype(np.int32)], False, 255, 1, cv2.LINE_8)
        self.rail = rail > 0
        self.fog = [_noise(H, W, s, c) for s, c in ((1, (8, 6)), (2, (14, 10)))]
        self.low = np.clip(1.0 - e01 * 1.5, 0, 1) ** 1.5              # fog sits in the valley, ridges stand out
        self.px = {k: tuple(v) for k, v in self.meta["places"].items()}
        self.flies = np.random.RandomState(8).rand(46, 4).astype(np.float32)
        self.leaves = np.random.RandomState(9).rand(26, 4).astype(np.float32)
        self.hero_xy = [self.px[h] for h in HEROES if h in self.px]
        self.trains = None                                        # phase 2 (display/laend_trains.py) draws here
        # the Wanderfeige: colonies seeded along the water that creep outwards, very slowly, for as long as the piece runs
        ys, xs = np.nonzero(wa > 0.5)
        rs2 = np.random.RandomState(31)
        pick = rs2.choice(len(ys), 12, replace=False) if len(ys) > 12 else np.arange(len(ys))
        dist = np.full((H, W), 1e9, np.float32)
        for i in pick:
            dist = np.minimum(dist, np.hypot(np.arange(W)[None, :] - xs[i], np.arange(H)[:, None] - ys[i]).astype(np.float32) * (0.7 + 0.6 * rs2.rand()))
        self.fig_birth = dist + _noise(H, W, 11, (24, 18)) * 9.0
        self.fig_dot = rs2.rand(H, W)
        self.static_labels = self._labels()

    def _labels(self):
        """The label layer: a dark halo and the pixel-font word, for every place worth naming."""
        lay = np.zeros((H, W, 3), np.float32)
        halo = np.zeros((H, W), np.float32)
        for name in list(HEROES) + [p for p in MINOR if p in self.px]:
            if name not in self.px:
                continue
            x, y = self.px[name]
            word = name.split()[0].upper()
            wd = pixelfont.width(word)
            hero = name in HEROES
            lx = int(round(min(max(x - wd / 2, 2), W - wd - 2)))
            ly = int(round(y - 9 if hero else y + 4))
            ly = max(1, min(H - 7, ly))
            h2 = np.zeros((H, W), np.float32)
            pixelfont.draw(h2[..., None], word, lx, ly, (1.0,))
            halo = np.maximum(halo, self.cv2.dilate(h2, np.ones((3, 3), np.uint8)))
            col = (255, 236, 190) if hero else (130, 140, 190)
            pixelfont.draw(lay, word, lx, ly, col)
        self.halo = halo
        return lay

    def _prep(self):
        """Everything a frame needs that does not change, so a frame is a few cheap sparse updates (the Pi has ~10 ms to spare)."""
        cv2 = self.cv2
        # rails and the brooks never move: bake them into the picture
        b = self.base
        bk = self.brook[..., None]
        b = b * (1 - bk * 0.35) + np.array((30, 80, 150), np.float32) * 0.5 * bk
        b[self.rail] = b[self.rail] * 0.35 + np.array((150, 156, 178), np.float32) * 0.65
        b += self.contour[..., None] * np.array((150, 170, 255), np.float32) * 0.8
        self.base = np.ascontiguousarray(np.clip(b, 0, 255), np.float32)
        # sparse sets: the river, the lit windows
        self.wy, self.wx = np.nonzero(self.water > 0.03)
        self.wa = self.water[self.wy, self.wx][:, None]
        self.winy, self.winx = np.nonzero(self.win > 0)
        self.winph = self.win_ph[self.winy, self.winx]
        # fog at half resolution (smooth anyway), shifted with sub-LED steps
        self.fogl = [_noise(H // 2, W // 2, s, c) for s, c in ((1, (8, 6)), (2, (14, 10)))]
        self.lowf = (self.low[..., None] * 0.55).astype(np.float32)
        cx, cy = self.hero_xy[1] if len(self.hero_xy) > 1 else (W / 2, H / 2)
        yy, xx = np.mgrid[0:H, 0:W]
        self.reveal_d = np.hypot(xx - cx, (yy - cy) * 0.8).astype(np.float32)
        self.halo3 = (1 - self.halo[..., None] * 0.7).astype(np.float32)
        self.label_idx = np.nonzero(self.halo > 0)
        self.fig_state = (-1.0, None)
        self.title_cache = None

    def _fog(self, t):
        cv2 = self.cv2
        h, w = H // 2, W // 2
        out = []
        for f, sp in ((self.fogl[0], 1.1), (self.fogl[1], -1.75)):
            M = np.float32([[1, 0, t * sp], [0, 1, 0]])
            out.append(cv2.warpAffine(f, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP))
        fog = np.clip((out[0] * 0.7 + out[1] * 0.5 - 0.42) * 1.6, 0, 1)
        return cv2.resize(fog, (W, H), interpolation=cv2.INTER_LINEAR)

    def frame(self, t, since):
        """since = seconds the map has been on the wall."""
        if not hasattr(self, "wy"):
            self._prep()
        img = self.base.copy()
        # the river runs: slow, soft light moving along it (fast per-LED shimmer is what reads as flicker on the panels)
        wy, wx = self.wy, self.wx
        run = 0.62 + 0.38 * np.sin(wx * 0.35 - t * 1.1 + wy * 0.2) * np.sin(wy * 0.45 + t * 0.6)
        wcol = np.array((22, 92, 200), np.float32) * (0.55 + 0.6 * run[:, None]) + np.array((110, 190, 255), np.float32) * (np.clip(run - 0.88, 0, 1) * 2.5)[:, None]
        img[wy, wx] = img[wy, wx] * (1 - self.wa * 0.9) + wcol * self.wa * 0.9
        # windows glow and breathe a little (only some of them move at all)
        tw = 0.78 + 0.22 * np.sin(t * 0.35 + self.winph)
        img[self.winy, self.winx] += tw[:, None] * np.array((255, 190, 90), np.float32) * 0.9
        # evening fog in the valley, drifting
        fog = self._fog(t)[..., None] * self.lowf
        img = img * (1 - fog) + np.array((78, 92, 150), np.float32) * fog
        if since < REVEAL:                                           # the map inks itself in from Korb outwards
            k = since / REVEAL
            img *= np.clip((12 + k * 260 - self.reveal_d) / 22.0, 0, 1)[..., None]
        out = img
        k = min(1.0, since / REVEAL)
        # fireflies over the vineyards and orchards
        if k >= 1:
            for i, (a, b, c, e) in enumerate(self.flies):
                fx = (a * W + math.sin(t * (0.2 + c * 0.3) + e * 9) * 7) % W
                fy = (b * H + math.cos(t * (0.17 + e * 0.3) + c * 9) * 7) % H
                ix, iy = int(fx), int(fy)
                if self.base[iy, ix, 0] > 0:
                    v = max(0.0, math.sin(t * (0.5 + c * 0.5) + e * 20)) ** 3
                    out[iy, ix] = np.maximum(out[iy, ix], np.array((255, 244, 140), np.float32) * v)
        # drifting leaves and the odd apple
        for i, (a, b, c, e) in enumerate(self.leaves):
            lx = (a * W + t * (2.5 + c * 4) + math.sin(t * 0.8 + e * 9) * 5) % W
            ly = (b * H + t * (3 + e * 3.5)) % H
            ix, iy = int(lx), int(ly)
            col = np.array(((235, 120, 40), (210, 60, 40), (230, 190, 60), (200, 40, 50))[i % 4], np.float32)
            out[iy, ix] = np.maximum(out[iy, ix], col * 0.8)
        # Wanderfeige creeping along the valley (the set is recomputed every few seconds: it grows very slowly)
        grow = since * 0.11
        if abs(grow - self.fig_state[0]) > 0.4:
            fm = (self.fig_birth < grow) & (self.fig_dot < 0.55) & (self.water < 0.3) & (self.urban < 0.5)
            ys, xs = np.nonzero(fm)
            self.fig_state = (grow, (ys, xs, self.fig_dot[ys, xs] < 0.06, self.win_ph[ys, xs]))
        ys, xs, purple, ph = self.fig_state[1]
        if len(ys):
            g = np.array((52, 150, 66), np.float32) * (0.75 + 0.25 * np.sin(t * 0.3 + ph))[:, None]
            g[purple] = (150, 70, 170)
            out[ys, xs] = out[ys, xs] * 0.4 + g * 0.6
        # live trains
        if self.trains is not None:
            self.trains(out, t)
        # labels, with a dark halo so the words read over the busiest vineyards
        la = float(np.clip(since / 3.0 - 1.5, 0, 1)) if since < 7 else 1.0
        ly, lx = self.label_idx
        out[ly, lx] = out[ly, lx] * (1 - (1 - self.halo3[ly, lx]) * la) + self.static_labels[ly, lx] * la
        # the three places pulse (small patches only)
        for i, (x, y) in enumerate(self.hero_xy):
            ph = (t * 0.42 + i * 0.33) % 1.0
            r = 2 + ph * 15
            y0, y1, x0, x1 = max(0, int(y - r - 2)), min(H, int(y + r + 3)), max(0, int(x - r - 2)), min(W, int(x + r + 3))
            gy, gx = np.mgrid[y0:y1, x0:x1]
            ring = np.abs(np.hypot(gx - x, gy - y) - r) < 0.75
            patch = out[y0:y1, x0:x1]
            patch[ring] = np.maximum(patch[ring], np.array((255, 215, 120), np.float32) * (1 - ph) ** 1.5 * la)
            ix, iy = int(round(x)), int(round(y))
            blk = out[max(0, iy - 1):iy + 2, max(0, ix - 1):ix + 2]
            blk[:] = np.array((255, 244, 200), np.float32) * la + blk * (1 - la)
        self._title(out, since)
        return np.clip(out, 0, 255).astype(np.uint8)

    def _title(self, out, since):
        from display import laend_intro
        k = min(1.0, max(0.0, (since - 1.0) / 2.0))
        if k <= 0:
            return
        if not hasattr(self, "_tcache"):
            im = Image.new("L", (W, 30), 0)
            d = ImageDraw.Draw(im)
            f = laend_intro.font(19)
            wd = d.textlength("Ländle", font=f)
            d.text(((W - wd) / 2, 2), "Ländle", font=f, fill=255)
            self._tcache = np.asarray(im, np.float32) / 255.0
        a = self._tcache
        band = np.linspace(1.0, 0.0, 30)[:, None] * 0.7
        out[:30] = out[:30] * (1 - band[..., None] * k)
        col = np.array((255, 214, 120), np.float32) + np.array((0, 30, 80), np.float32) * (np.linspace(0, 1, 30)[:, None, None])
        out[:30] = out[:30] * (1 - a[..., None] * k) + col * a[..., None] * k


_map = None
_start = None


def _get_map():
    global _map
    if _map is None:
        _map = Map()
    return _map


def frame(t):
    from display import laend_intro
    global _start
    m = _get_map()
    if m.trains is None and t >= laend_intro.LENGTH - 5:
        from display import laend_trains
        m.trains = laend_trains.Trains(m.meta)
    if t < laend_intro.LENGTH:
        return laend_intro.frame(t)
    return Image.fromarray(m.frame(t, t - laend_intro.LENGTH), "RGB")


def thumb():
    """A still for the app: the settled map."""
    return Image.fromarray(_get_map().frame(20.0, 20.0), "RGB")
