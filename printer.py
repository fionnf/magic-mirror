"""Thermal receipt printer (ESC/POS over USB) and PIL photo-strip composer.

Public surface
--------------
  create_printer()  -> ReceiptPrinter | _NullPrinter
  render_booth_pil(frames, label, prompts, qr_url) -> PIL.Image  (greyscale "L")

Image processing pipeline (config-driven)
-----------------------------------------
  greyscale → autocontrast → gamma → brightness/contrast → optional sharpen
  The processed greyscale image is passed to python-escpos which performs the
  final 1-bit conversion and Floyd-Steinberg dither internally.
"""
import datetime
import io
import os
import textwrap
from typing import List, Optional

import cv2
import numpy as np
from PIL import (Image, ImageDraw, ImageEnhance, ImageFilter,
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
    msg_lines = _wrap_px(probe, text.upper(), msg_font, W - 2 * margin) or [text.upper()]

    def line_h(font):
        l, t, r, b = probe.textbbox((0, 0), "AgÄ", font=font)
        return (b - t) + 6

    hh, mh = line_h(head_font), line_h(msg_font)
    total_h = 6 + len(header_lines) * hh + 6 + photo_h + 12 + len(msg_lines) * mh + 10

    out = Image.new("L", (W, total_h), 255)
    draw = ImageDraw.Draw(out)

    def centred(y, line, font):
        w = draw.textlength(line, font=font)
        draw.text(((W - w) // 2, y), line, fill=0, font=font)

    y = 6
    for line in header_lines:
        centred(y, line, head_font)
        y += hh
    y += 6
    out.paste(processed, (0, y))
    y += photo_h + 12
    for line in msg_lines:
        centred(y, line, msg_font)
        y += mh
    return out


# ---------------------------------------------------------------------------
# Photobooth strip composer
# ---------------------------------------------------------------------------

def render_booth_pil(frames: List[np.ndarray], label: str = "PHOTOBOOTH",
                     prompts: Optional[List[str]] = None,
                     qr_url: Optional[str] = None) -> Image.Image:
    """Compose a greyscale photo-strip PIL Image for printing and display.

    Layout (top → bottom):
      black header bar with label
      for each photo: image + pose-direction caption
      optional QR code + URL
      timestamp footer
    """
    if prompts is None:
        prompts = []

    W = config.PRINTER_WIDTH_DOTS
    photo_h = config.BOOTH_PHOTO_HEIGHT
    caption_h = 18
    header_h = 28
    footer_h = 16
    gap = 6

    # ---- optional QR code ----
    qr_img: Optional[Image.Image] = None
    if qr_url:
        try:
            import qrcode as _qrcode
            qr = _qrcode.QRCode(box_size=3, border=2)
            qr.add_data(qr_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black",
                                   back_color="white").convert("L")
            qr_size = min(W // 2, 120)
            qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
        except Exception as e:
            print(f"[PRINTER] QR generation skipped: {e}")
            qr_img = None

    qr_block_h = (qr_img.height + gap * 2) if qr_img is not None else 0
    url_line_h = 14 if qr_url else 0

    total_h = (
        header_h
        + len(frames) * (photo_h + caption_h + gap)
        + qr_block_h
        + url_line_h
        + footer_h
    )

    strip = Image.new("L", (W, total_h), 255)
    draw = ImageDraw.Draw(strip)
    font = ImageFont.load_default()

    # ---- header bar ----
    draw.rectangle([0, 0, W - 1, header_h - 1], fill=0)
    label_x = max(0, (W - len(label) * 6) // 2)
    draw.text((label_x, (header_h - 8) // 2), label, fill=255, font=font)

    y = header_h

    # ---- photos ----
    target_ratio = W / photo_h
    for i, frame in enumerate(frames):
        photo = _frame_to_pil(frame)
        # crop to target aspect ratio before resizing
        src_ratio = photo.width / photo.height
        if src_ratio > target_ratio:
            new_w = int(photo.height * target_ratio)
            x0 = (photo.width - new_w) // 2
            photo = photo.crop((x0, 0, x0 + new_w, photo.height))
        elif src_ratio < target_ratio:
            new_h = int(photo.width / target_ratio)
            y0 = (photo.height - new_h) // 3
            photo = photo.crop((0, y0, photo.width, y0 + new_h))
        photo = photo.resize((W, photo_h), Image.LANCZOS)
        strip.paste(_preprocess(photo), (0, y))
        y += photo_h

        caption = prompts[i] if i < len(prompts) else f"Photo {i + 1}"
        draw.text((4, y + 2), caption[:config.PRINTER_TEXT_COLS], fill=0, font=font)
        y += caption_h + gap

    # ---- QR code ----
    if qr_img is not None:
        qr_x = (W - qr_img.width) // 2
        strip.paste(qr_img, (qr_x, y + gap))
        y += qr_img.height + gap * 2

    if qr_url:
        url_display = (qr_url if len(qr_url) <= config.PRINTER_TEXT_COLS
                       else qr_url[:config.PRINTER_TEXT_COLS - 1] + "…")
        url_x = max(0, (W - len(url_display) * 6) // 2)
        draw.text((url_x, y), url_display, fill=0, font=font)
        y += url_line_h

    # ---- footer ----
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.text((max(0, (W - len(ts) * 6) // 2), y + 2), ts, fill=0, font=font)

    return strip


# ---------------------------------------------------------------------------
# Printer classes
# ---------------------------------------------------------------------------

class ReceiptPrinter:
    """ESC/POS thermal printer over USB (python-escpos)."""

    def __init__(self) -> None:
        from escpos.printer import Usb as _Usb
        self._Usb = _Usb

    def _open(self):
        return self._Usb(
            config.PRINTER_VENDOR_ID,
            config.PRINTER_PRODUCT_ID,
            timeout=config.PRINTER_TIMEOUT_MS,
        )

    def print_receipt(self, frame: np.ndarray, text: str) -> None:
        if frame is None:
            return
        img = _receipt_image(frame, text)
        try:
            p = self._open()
            try:
                p.image(img)
                p.ln(4)
                p.cut()
            finally:
                p.close()
        except Exception as e:
            print(f"[PRINTER] print_receipt failed: {e}")

    def print_strip(self, pil_image: Image.Image) -> None:
        if pil_image is None:
            return
        img = pil_image if pil_image.mode == "L" else pil_image.convert("L")
        try:
            p = self._open()
            try:
                p.image(img)
                p.ln(4)
                p.cut()
            finally:
                p.close()
        except Exception as e:
            print(f"[PRINTER] print_strip failed: {e}")

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
    """Return a ReceiptPrinter if python-escpos is available, else _NullPrinter."""
    try:
        import escpos  # noqa: F401
        return ReceiptPrinter()
    except ImportError:
        print("[PRINTER] python-escpos not installed; printer disabled")
        return _NullPrinter()
