"""The playing song's album cover, for the music mode's two switches (Music tab):

    cover_show     the cover itself on the wall, large and softly lit, over a blurred glow of itself
    cover_colours  the music art keeps its look but takes its colours from the cover

The cover's address comes from the speaker or Spotify (display.cast.read_now). It is downloaded once
per song on a side thread, so the frame loop never waits on the network.

    c = Covers(W, H); c.update()          # cheap: call every frame
    c.palette_key()  -> "cover:#rrggbb,..." for MusicShow._lut, or None
    c.frame()        -> float32 HxWx3 of the composed cover, or None
"""
import colorsys
import io
import threading
import time
import urllib.request

import numpy as np
from PIL import Image, ImageFilter


def palette_from(img, n=5):
    """Calm colours from a cover: its main colours, darkest first, held to one family of hues."""
    from display.music import _soften
    small = img.convert("RGB").resize((64, 64))
    q = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:24]
    counts = sorted(q.getcolors(), reverse=True)                 # (count, index), most used first
    cols = [tuple(pal[i * 3:i * 3 + 3]) for _, i in counts]
    vivid = lambda c: colorsys.rgb_to_hsv(*(v / 255 for v in c))[1] * max(c) / 255
    cols = sorted(cols[:6], key=vivid, reverse=True)[:n - 1]      # the coloured ones carry the piece
    lum = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    cols = sorted(cols, key=lum)
    dark = tuple(int(v * 0.18) for v in cols[0])                 # a deep shadow of its darkest colour
    cols = _soften([dark] + cols)
    return ["#%02x%02x%02x" % tuple(int(v) for v in c) for c in cols]


def compose(img, W, H):
    """The cover centred and large, a blurred dim glow of itself filling the rest of the wall."""
    img = img.convert("RGB")
    side = int(min(W, H) * 0.78)
    bg = img.resize((max(W, H), max(W, H))).filter(ImageFilter.GaussianBlur(14))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    out = np.asarray(bg, np.float32) * 0.32                      # the glow: dim, so the cover reads
    fg = np.asarray(img.resize((side, side), Image.LANCZOS), np.float32) * 0.9
    x, y = (W - side) // 2, (H - side) // 2
    out[y:y + side, x:x + side] = fg
    return out


class Covers:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.url, self.img, self.pal, self.comp = None, None, None, None
        self.checked, self.busy = 0.0, False

    def update(self):
        now = time.time()
        if now - self.checked < 1.0:
            return
        self.checked = now
        try:
            from display import cast
            d = cast.read_now()
        except Exception:
            d = None
        url = (d or {}).get("image") or None
        if url and not url.startswith(("http://", "https://")):
            url = None
        if url is None:
            self.url, self.img, self.pal, self.comp = None, None, None, None
            return
        if url != self.url and not self.busy:
            self.busy = True
            threading.Thread(target=self._load, args=(url,), daemon=True).start()

    def _load(self, url):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "fortuna-wall"}),
                                        timeout=10) as r:
                img = Image.open(io.BytesIO(r.read(4_000_000))).convert("RGB")
            pal, comp = palette_from(img), compose(img, self.W, self.H)
            self.url, self.img, self.pal, self.comp = url, img, pal, comp
            print(f"[cover] {pal}", flush=True)
        except Exception as e:
            self.url = url                                  # do not retry a broken cover every second
            print(f"[cover] {type(e).__name__}: {e}", flush=True)
        finally:
            self.busy = False

    def palette_key(self):
        return "cover:" + ",".join(self.pal) if self.pal else None

    def frame(self):
        return self.comp
