"""Getting a finished picture onto paper, wherever the receipt printer is.

The printer is chosen by WALL_PRINTER (in .env) or config.PRINTER:
  usb                      the printer is plugged into this Pi (default)
  http://other-pi:8631     the printer hangs off another Pi in the room, on Wi-Fi: that Pi runs
                           tools/print_server.py (needs PRINT_KEY on both sides)
  tcp://192.168.1.50:9100  a Wi-Fi / Ethernet ESC/POS printer (raw port 9100)
  serial:/dev/rfcomm0      a Bluetooth printer paired as a serial port (see panel_setup/README)

Quality over speed, always: images are dithered here at the printer's full 384-dot width (Atkinson
by default, which keeps midtones open on thermal paper), sent with the native raster command at
full density in both directions, and the print head is set to heat longer, fewer dots at a time,
with longer pauses - slower but deeper, more even black. Only Pillow (and python-escpos for a local
printer) is needed, so tools/print_server.py can run on a tiny Pi.
"""
import io
import os
import urllib.request

import numpy as np
from PIL import Image

WIDTH = int(os.environ.get("PRINTER_WIDTH_DOTS", 384))
# ESC 7 n1 n2 n3: n1 = max dots heated at once in units of 8 (fewer = more even), n2 = heating time in
# 10 us (longer = darker), n3 = pause between heats in 10 us (longer = cleaner). Factory ~ 7, 80, 2.
HEAT = tuple(int(v) for v in os.environ.get("PRINTER_HEAT", "3,170,40").split(","))
DENSITY = int(os.environ.get("PRINTER_DENSITY", 15))       # DC2 #: 0-31 print density, 15 = deep
DITHER = os.environ.get("PRINTER_DITHER", "atkinson")       # atkinson | floyd


def where():
    try:
        import config
        default = getattr(config, "PRINTER", "usb")
    except Exception:
        default = "usb"
    return (os.environ.get("WALL_PRINTER") or default or "usb").strip()


def to_1bit(img):
    """Greyscale picture -> 1-bit at exactly the printer's width (no scaling on the printer)."""
    g = img.convert("L")
    if g.width != WIDTH:
        g = g.resize((WIDTH, round(g.height * WIDTH / g.width)), Image.LANCZOS)
    if DITHER != "atkinson":
        return g.convert("1")                                    # Floyd-Steinberg
    a = np.asarray(g, np.float32).copy()
    h, w = a.shape
    a = np.pad(a, ((0, 2), (1, 2)))
    for y in range(h):                                           # Atkinson: 6/8 of the error spread,
        row, nxt, nn = a[y], a[y + 1], a[y + 2]                  # crisp highlights, open shadows
        for x in range(1, w + 1):
            old = row[x]
            new = 255.0 if old >= 128 else 0.0
            err = (old - new) / 8.0
            row[x] = new
            if err:
                row[x + 1] += err; row[x + 2] += err
                nxt[x - 1] += err; nxt[x] += err; nxt[x + 1] += err
                nn[x] += err
    return Image.fromarray(a[:h, 1:w + 1].clip(0, 255).astype(np.uint8)).convert("1", dither=Image.NONE)


def _quality(p):
    """Slow, hot, even printing (ignored by printers that do not know the commands)."""
    p._raw(b"\x1b\x40")                                          # reset
    p._raw(b"\x1b\x37" + bytes(HEAT))                            # heating dots / time / interval
    p._raw(b"\x12\x23" + bytes([max(0, min(31, DENSITY))]))      # print density


def _open(spec):
    from escpos import printer as P
    if spec == "usb":
        vid = int(os.environ.get("PRINTER_VENDOR_ID", "0x0416"), 16)
        pid = int(os.environ.get("PRINTER_PRODUCT_ID", "0x5011"), 16)
        try:
            import config
            vid, pid = config.PRINTER_VENDOR_ID, config.PRINTER_PRODUCT_ID
        except Exception:
            pass
        return P.Usb(vid, pid, timeout=0)
    if spec.startswith("tcp://"):
        host, _, port = spec[6:].partition(":")
        return P.Network(host, int(port or 9100), timeout=30)
    if spec.startswith("serial:"):
        return P.Serial(spec[7:], baudrate=int(os.environ.get("PRINTER_BAUD", 115200)), timeout=30)
    raise ValueError(f"unknown printer {spec!r}")


def print_local(bw, spec="usb", cut=True):
    """bw: a 1-bit image at printer width."""
    p = _open(spec)
    try:
        _quality(p)
        p.image(bw, impl="bitImageRaster", high_density_vertical=True, high_density_horizontal=True,
                fragment_height=256, center=False)                # small bands: the head never starves
        p.ln(4)
        if cut:
            p.cut()
    finally:
        p.close()


def send(img, cut=True):
    """Print a greyscale/colour picture wherever the printer is. Raises on failure."""
    spec = where()
    bw = to_1bit(img)
    if spec.startswith(("http://", "https://")):
        buf = io.BytesIO()
        bw.save(buf, "PNG")
        req = urllib.request.Request(spec.rstrip("/") + "/print" + ("" if cut else "?cut=0"), data=buf.getvalue(),
                                     headers={"Content-Type": "image/png",
                                              "X-Print-Key": os.environ.get("PRINT_KEY", "")})
        with urllib.request.urlopen(req, timeout=180) as r:
            if r.status != 200:
                raise RuntimeError(f"print server: {r.status}")
        return
    print_local(bw, spec, cut)


def status():
    """{'where': ..., 'ok': bool, 'note': str} - for the app."""
    spec = where()
    try:
        if spec.startswith(("http://", "https://")):
            with urllib.request.urlopen(spec.rstrip("/") + "/health", timeout=4) as r:
                return {"where": spec, "ok": r.status == 200, "note": r.read().decode()[:80]}
        if spec == "usb":
            import usb.core
            import config
            dev = usb.core.find(idVendor=config.PRINTER_VENDOR_ID, idProduct=config.PRINTER_PRODUCT_ID)
            return {"where": spec, "ok": dev is not None, "note": "" if dev else "not plugged in"}
        return {"where": spec, "ok": True, "note": ""}
    except Exception as e:
        return {"where": spec, "ok": False, "note": str(e)[:80]}
