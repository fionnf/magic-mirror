"""Thermal receipt printer (ESC/POS over USB) and PIL photo-strip composer.

Public surface
--------------
  create_printer()  -> ReceiptPrinter | _NullPrinter
  render_booth_pil(frames, label, prompts, qr_url) -> PIL.Image  (greyscale "L")

Image processing pipeline (config-driven)
-----------------------------------------
  greyscale → autocontrast → gamma → brightness/contrast → optional sharpen
  The processed greyscale image goes to print_out.py, which dithers it at full printer
  resolution and sends it to the printer wherever it is (USB, another Pi, Wi-Fi, Bluetooth).
"""
import datetime
import io
import os
import textwrap
from typing import List, Optional

import cv2
import numpy as np
from PIL import (Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter,
                 ImageFont, ImageOps)

import config


# ---------------------------------------------------------------------------
# Image pre-processing for thermal output
# ---------------------------------------------------------------------------

def _preprocess(img: Image.Image) -> Image.Image:
    """Return a processed greyscale image ready for the printer."""
    grey = img.convert("L")
    grey = ImageOps.autocontrast(grey, cutoff=config.PRINTER_IMAGE_AUTOCONTRAST)
    # gamma < 1 brightens midtones; apply via LUT for speed
    lut = bytes(
        min(255, int((v / 255.0) ** config.PRINTER_IMAGE_GAMMA * 255))
        for v in range(256)
    )
    grey = grey.point(lut)
    grey = ImageEnhance.Brightness(grey).enhance(config.PRINTER_IMAGE_BRIGHTNESS)
    grey = ImageEnhance.Contrast(grey).enhance(config.PRINTER_IMAGE_CONTRAST)
    if config.PRINTER_IMAGE_SHARPEN:
        grey = grey.filter(ImageFilter.UnsharpMask(radius=1, percent=80, threshold=2))
    return grey


def _frame_to_pil(frame: np.ndarray) -> Image.Image:
    """BGR numpy array → RGB PIL Image."""
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))



# ---------------------------------------------------------------------------
# Little decorations, drawn as shapes (they print the same whatever the font has)
# ---------------------------------------------------------------------------

def _heart(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill=0) -> None:
    d.ellipse([cx - r, cy - r, cx, cy], fill=fill)
    d.ellipse([cx, cy - r, cx + r, cy], fill=fill)
    d.polygon([(cx - r, cy - r * 0.45), (cx + r, cy - r * 0.45), (cx, cy + r * 0.95)], fill=fill)


def _sparkle(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill=0) -> None:
    k = r * 0.28
    d.polygon([(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
               (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], fill=fill)


def _scallop(d: ImageDraw.ImageDraw, y: int, W: int, r: int = 7) -> None:
    """A row of little half-circles: a cute edge to hang a title from."""
    x = r
    while x < W + r:
        d.pieslice([x - r, y - r, x + r, y + r], 0, 180, fill=0)
        x += 2 * r


def _sticker(base: Image.Image, ink_draw: ImageDraw.ImageDraw, photo: Image.Image, xy, radius: int, border: int = 4) -> None:
    """The photo with rounded corners goes into `base` (the layer that gets the halftone); its black frame goes into the
    ink layer (drawn crisp, after the halftone)."""
    x, y = xy
    w, h = photo.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius, fill=255)
    base.paste(photo.convert("L"), (x, y), mask)
    ink_draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius, outline=0, width=border)


def _layers(w: int, h: int):
    """Two white layers: `base` for photographs (dithered at half resolution) and `ink` for text, frames and little drawings
    (printed as crisp black dots at full resolution). Their darker() is the picture as a whole."""
    base, ink = Image.new("L", (w, h), 255), Image.new("L", (w, h), 255)
    return base, ink, ImageDraw.Draw(ink)


def _compose(base: Image.Image, ink: Image.Image) -> Image.Image:
    out = ImageChops.darker(base, ink)
    out.info["base"], out.info["ink"] = base, ink            # print_out.to_1bit uses the two layers when it finds them
    return out


# ---------------------------------------------------------------------------
# Receipt layout (single-shot)
# ---------------------------------------------------------------------------

def _ttf(size: int):
    """Bold TrueType font at `size` px; falls back to Pillow's scalable default."""
    for path in getattr(config, "TEXT_FONT_PATHS", []):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap_px(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> List[str]:
    """Greedy word wrap by rendered pixel width."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _crop_portrait(photo: Image.Image, w: int, h: int) -> Image.Image:
    """Crop (never stretch) to w:h, keeping a bit more of the top, then resize."""
    target = w / h
    src = photo.width / photo.height
    if src > target:
        nw = int(photo.height * target)
        x0 = (photo.width - nw) // 2
        photo = photo.crop((x0, 0, x0 + nw, photo.height))
    elif src < target:
        nh = int(photo.width / target)
        y0 = (photo.height - nh) // 3
        photo = photo.crop((0, y0, photo.width, y0 + nh))
    return photo.resize((w, h), Image.LANCZOS)


def _receipt_image(frame: np.ndarray, text: str) -> Image.Image:
    """Build a printable greyscale PIL Image for a single-shot receipt:
    header + timestamp, portrait photo, then the AI message in large type."""
    W = config.PRINTER_WIDTH_DOTS
    photo_h = int(round(W / config.PRINTER_IMAGE_ASPECT))     # portrait
    processed = _preprocess(_crop_portrait(_frame_to_pil(frame), W, photo_h))

    head_font = _ttf(config.PRINTER_HEADER_FONT_SIZE)
    msg_font = _ttf(config.PRINTER_MESSAGE_FONT_SIZE)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    margin = 8

    header_lines: List[str] = []
    if config.PRINTER_HEADER:
        header_lines.append(config.PRINTER_HEADER)
    header_lines.append(datetime.datetime.now().strftime("%Y-%m-%d  %H:%M"))
    msg_lines = (_wrap_px(probe, text.upper(), msg_font, W - 2 * margin) or [text.upper()]) if text.strip() else []

    def line_h(font):
        l, t, r, b = probe.textbbox((0, 0), "AgÄ", font=font)
        return (b - t) + 6

    hh, mh = line_h(head_font), line_h(msg_font)
    total_h = 6 + len(header_lines) * hh + 6 + photo_h + 12 + len(msg_lines) * mh + 10

    base, ink, draw = _layers(W, total_h)

    def centred(y, line, font):
        w = draw.textlength(line, font=font)
        draw.text(((W - w) // 2, y), line, fill=0, font=font)
        return w

    y = 6
    for i, line in enumerate(header_lines):
        w = centred(y, line, head_font)
        if i == 0:                                           # a sparkle on each side of the first line
            _sparkle(draw, (W - w) / 2 - 18, y + hh / 2 - 2, 8)
            _sparkle(draw, (W + w) / 2 + 18, y + hh / 2 - 2, 8)
        y += hh
    y += 6
    _sticker(base, draw, processed, (0, y), 28)              # rounded corners and a frame, same size as before
    _heart(draw, W - 30, y + 30, 13, 255)                    # a small heart sticker on the corner
    _heart(draw, W - 30, y + 30, 10, 0)
    y += photo_h + 12
    for line in msg_lines:
        centred(y, line, msg_font)
        y += mh
    return _compose(base, ink)


# ---------------------------------------------------------------------------
# Photobooth strip composer
# ---------------------------------------------------------------------------

def render_booth_pil(frames: List[np.ndarray], label: str = "PHOTOBOOTH",
                     prompts: Optional[List[str]] = None,
                     qr_url: Optional[str] = None) -> Image.Image:
    """Compose the photo strip (greyscale "L") for printing: a scalloped title, then each photo as a rounded portrait
    sticker the shape of a single printout, numbered, with its pose direction under it between sparkles, and a footer with
    the QR code beside the date. Shorter than the plain strip it replaces."""
    if prompts is None:
        prompts = []
    W = config.PRINTER_WIDTH_DOTS
    pw = W - 24                                              # photo width: a 12-dot margin each side
    ph = int(round(pw / config.PRINTER_IMAGE_ASPECT))        # portrait, 3:4
    title_font, cap_font = _ttf(30), _ttf(21)
    small, tiny = _ttf(18), _ttf(14)
    header_h, cap_h, gap = 50, 30, 8

    qr_img: Optional[Image.Image] = None
    if qr_url:
        try:
            import qrcode as _qrcode
            qr = _qrcode.QRCode(box_size=3, border=2)
            qr.add_data(qr_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("L").resize((104, 104), Image.LANCZOS)
        except Exception as e:
            print(f"[PRINTER] QR generation skipped: {e}")
            qr_img = None
    footer_h = 112 if qr_img is not None else 46

    total_h = header_h + len(frames) * (ph + cap_h + gap) + footer_h
    base, ink, d = _layers(W, total_h)

    # ---- title ----
    tw = d.textlength(label, font=title_font)
    d.text(((W - tw) / 2, 4), label, fill=0, font=title_font)
    _heart(d, (W - tw) / 2 - 24, 24, 10)
    _heart(d, (W + tw) / 2 + 24, 24, 10)
    _sparkle(d, 22, 34, 7)
    _sparkle(d, W - 22, 34, 7)
    _scallop(d, header_h - 8, W)
    y = header_h

    # ---- photos ----
    for i, frame in enumerate(frames):
        try:                       # keep the people in the frame (face-aware, then centre)
            import smartcrop
            frame, _ = smartcrop.portrait_crop(frame, pw / ph)
        except Exception:
            pass
        photo = _crop_portrait(_frame_to_pil(frame), pw, ph)
        _sticker(base, d, _preprocess(photo), (12, y), 30)
        bx, by = 12 + 24, y + 24                             # a round number sticker on the corner
        d.ellipse([bx - 19, by - 19, bx + 19, by + 19], fill=255, outline=0, width=3)
        n = str(i + 1)
        d.text((bx - d.textlength(n, font=cap_font) / 2, by - 13), n, fill=0, font=cap_font)
        y += ph
        caption = (prompts[i] if i < len(prompts) else f"Photo {i + 1}").strip()
        font = cap_font
        for size in (21, 19, 17, 15):                        # shrink a long direction to fit between the sparkles
            font = _ttf(size)
            if d.textlength(caption, font=font) <= W - 80:
                break
        while d.textlength(caption, font=font) > W - 80 and len(caption) > 6:
            caption = caption[:-2]                           # last resort: never wider than the paper
        cw = d.textlength(caption, font=font)
        d.text(((W - cw) / 2, y + 5 + (21 - font.size) // 2 if hasattr(font, "size") else y + 3), caption, fill=0, font=font)
        _sparkle(d, (W - cw) / 2 - 16, y + 16, 7)
        _sparkle(d, (W + cw) / 2 + 16, y + 16, 7)
        y += cap_h + gap

    # ---- footer: QR beside the date and the house, or just the house ----
    ts = datetime.datetime.now().strftime("%d.%m.%Y  %H:%M")
    house = config.PRINTER_HEADER or "HOUSE FORTUNA"
    if qr_img is not None:
        ink.paste(qr_img.point(lambda v: 0 if v < 128 else 255), (14, y + 4))
        tx = 14 + 104 + 14
        hw = d.textlength(house, font=small)
        d.text((tx, y + 12), house, fill=0, font=small)
        _heart(d, tx + hw + 14, y + 24, 7)
        d.text((tx, y + 40), ts, fill=0, font=small)
        d.text((tx, y + 68), "scan for your photos", fill=0, font=tiny)
    else:
        hw = d.textlength(house, font=small)
        d.text(((W - hw) / 2, y + 1), house, fill=0, font=small)
        _heart(d, (W - hw) / 2 - 18, y + 13, 7)
        _heart(d, (W + hw) / 2 + 18, y + 13, 7)
        tw2 = d.textlength(ts, font=tiny)
        d.text(((W - tw2) / 2, y + 26), ts, fill=0, font=tiny)
    return _compose(base, ink)


# ---------------------------------------------------------------------------
# Printer classes
# ---------------------------------------------------------------------------

class ReceiptPrinter:
    """The receipt printer, wherever it is (see print_out.py: USB here, another Pi, Wi-Fi, Bluetooth).
    Pictures are dithered here at full resolution and printed slowly for the deepest, cleanest black."""

    def _emit(self, img: Image.Image, what: str) -> None:
        import print_out
        try:
            print_out.send(img)
        except Exception as e:
            print(f"[PRINTER] {what} failed ({print_out.where()}): {e}")

    def print_receipt(self, frame: np.ndarray, text: str) -> None:
        if frame is not None:
            self._emit(_receipt_image(frame, text), "print_receipt")

    def print_strip(self, pil_image: Image.Image) -> None:
        if pil_image is not None:
            self._emit(pil_image, "print_strip")

    def shutdown(self) -> None:
        pass


class _NullPrinter:
    def print_receipt(self, frame, text) -> None:
        pass

    def print_strip(self, pil_image) -> None:
        pass

    def shutdown(self) -> None:
        pass


def create_printer():
    """A ReceiptPrinter when a printer can be reached (python-escpos here, or a printer on another
    machine), else _NullPrinter."""
    import print_out
    if print_out.where().startswith(("http://", "https://")):
        return ReceiptPrinter()
    try:
        import escpos  # noqa: F401
        return ReceiptPrinter()
    except ImportError:
        print("[PRINTER] python-escpos not installed; printer disabled")
        return _NullPrinter()
