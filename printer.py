"""Optional thermal receipt printer (ESC/POS over USB).

After each mirror cycle, prints:
  - a small header with the timestamp
  - the captured frame, centre-cropped to a portrait aspect and sized to the
    printer's pixel width
  - the AI response in chunky double-size bold, word-wrapped to 16 cols
  - feed + cut

If the printer is missing, disconnected, or python-escpos isn't installed, the
module silently no-ops and the rest of the mirror keeps running.

USB IDs and dot width are in config.py — change them if you swap printer.
"""
import io
import os
import textwrap
import datetime
import concurrent.futures
import threading
import numpy as np
import cv2
from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageDraw, ImageFont
import config


# ---------- receipt-as-image rendering ----------
# Reused by the preview test and by the Drive uploader so the same layout
# code drives the on-paper output, the PNG preview, and the cloud archive.

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:\\Windows\\Fonts\\consolab.ttf",
]


def _font(size: int):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _text_size(draw, text, font):
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except Exception:
        return draw.textsize(text, font=font)


def _fit_monospace_font(max_size, cols, max_width):
    probe = ImageDraw.Draw(Image.new("L", (10, 10)))
    sample = "M" * cols
    for size in range(max_size, 9, -1):
        f = _font(size)
        try:
            w = probe.textbbox((0, 0), sample, font=f)[2]
        except Exception:
            w = probe.textsize(sample, font=f)[0]
        if w <= max_width:
            return f, size
    return _font(10), 10


def render_receipt_pil(frame_bgr, response_text: str) -> "Image.Image":
    """Build a PIL Image that mirrors what the thermal printer outputs.

    Uses the same image pre-processing pipeline as the real printer so
    cloud-archived previews match what came out on paper to the pixel.
    """
    W = config.PRINTER_WIDTH_DOTS
    rp = ReceiptPrinter.__new__(ReceiptPrinter)   # no __init__, no probe
    photo = rp._prepare_image(frame_bgr)

    body_font = _font(20)
    response_font, _ = _fit_monospace_font(
        max_size=22, cols=config.PRINTER_TEXT_COLS, max_width=W - 6)

    resp_lines = justify_lines(
        (response_text or "").strip() or "...",
        width=config.PRINTER_TEXT_COLS)

    probe = Image.new("L", (W, 10), 255)
    d = ImageDraw.Draw(probe)
    pad = 12
    header_text = config.PRINTER_HEADER or ""
    ts_text = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")
    header_h = _text_size(d, header_text, body_font)[1] if header_text else 0
    ts_h = _text_size(d, ts_text, body_font)[1]
    resp_line_h = int(_text_size(d, "Ag", response_font)[1] * 1.2)
    resp_h = resp_line_h * len(resp_lines)
    header_gap = 28 if header_text else 0
    total_h = (pad
               + (header_h + header_gap if header_text else 0)
               + ts_h + pad
               + photo.height + pad
               + resp_h + pad * 2
               + 24)

    canvas = Image.new("L", (W, total_h), 255)
    d = ImageDraw.Draw(canvas)
    y = pad

    if header_text:
        bw, bh = _text_size(d, header_text, body_font)
        bx = (W - bw) // 2
        d.text((bx, y), header_text, fill=0, font=body_font)
        d.text((bx + 1, y), header_text, fill=0, font=body_font)
        y += bh + header_gap

    # timestamp
    tw, th = _text_size(d, ts_text, body_font)
    d.text(((W - tw) // 2, y), ts_text, fill=0, font=body_font)
    y += th + pad

    canvas.paste(photo, (0, y))
    y += photo.height + pad

    char_w, _ = _text_size(d, "M" * config.PRINTER_TEXT_COLS, response_font)
    left = max(0, (W - char_w) // 2)
    for line in resp_lines:
        d.text((left, y), line, fill=0, font=response_font)
        y += resp_line_h

    y_cut = total_h - 12
    for x in range(0, W, 6):
        d.line([(x, y_cut), (x + 3, y_cut)], fill=0)

    bg = Image.new("RGB", canvas.size, (250, 246, 235))
    bg.paste(canvas.convert("RGB"), (0, 0),
             ImageOps.invert(canvas).convert("L"))
    return bg


def save_receipt_png(frame_bgr, response_text: str, out_path: str) -> str:
    render_receipt_pil(frame_bgr, response_text).save(out_path)
    return out_path


def render_booth_pil(frames_bgr, label: str = "PHOTOBOOTH",
                     prompts=None, qr_url: str = None) -> "Image.Image":
    """Compose a photobooth strip from N captured frames into one PIL image.

    Layout: optional store header, the word PHOTOBOOTH, timestamp, then the
    frames stacked vertically with a thin black border per photo and an
    optional pose-prompt caption under each, then (if qr_url) a small QR
    code with a 'SCAN TO DOWNLOAD' label, then a cut line.
    """
    W = config.PRINTER_WIDTH_DOTS
    rp = ReceiptPrinter.__new__(ReceiptPrinter)
    body_font = _font(20)
    caption_font = _font(16)

    prompts = prompts or []

    # process each photo: same dither pipeline as the single-shot receipt,
    # but scaled down to BOOTH_PHOTO_HEIGHT for the strip aesthetic.
    photos = []
    for f in frames_bgr:
        p = rp._prepare_image(f)
        scale = config.BOOTH_PHOTO_HEIGHT / p.height
        new_w = max(1, int(round(p.width * scale)))
        new_h = config.BOOTH_PHOTO_HEIGHT
        if new_w > W:
            new_h = int(round(p.height * (W / p.width)))
            new_w = W
        # re-dither at the new size for crisp output
        rescaled = p.convert("L").resize((new_w, new_h), Image.LANCZOS)
        photos.append(rescaled.convert("1", dither=Image.FLOYDSTEINBERG))

    pad = 12
    photo_gap = 10
    border = 2
    probe = Image.new("L", (W, 10), 255)
    d = ImageDraw.Draw(probe)
    header_text = config.PRINTER_HEADER or ""
    ts_text = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")
    header_h = _text_size(d, header_text, body_font)[1] if header_text else 0
    label_h = _text_size(d, label, body_font)[1] if label else 0
    ts_h = _text_size(d, ts_text, body_font)[1]
    caption_h = _text_size(d, "Ag", caption_font)[1] if prompts else 0
    caption_gap = 4 if prompts else 0
    photos_total_h = (sum(p.height + 2 * border for p in photos)
                      + photo_gap * (len(photos) - 1)
                      + len(photos) * (caption_h + caption_gap if prompts else 0))

    # QR code section — generated once to know its size
    qr_img = None
    qr_label = ""
    qr_section_h = 0
    if qr_url:
        try:
            import qrcode
            # box_size=2 + border=2 keeps the QR around 70-80 px wide on 56mm
            # paper — small but still reliably scannable by phone cameras.
            qr = qrcode.QRCode(
                version=None,
                box_size=2,
                border=2,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("L")
            qr_label = "SCAN TO DOWNLOAD"
            qr_label_h = _text_size(d, qr_label, caption_font)[1]
            # extra top padding so the QR never crowds the last caption
            qr_section_h = pad + qr_img.height + 4 + qr_label_h + pad
        except Exception as e:
            print(f"[BOOTH] QR generation failed: {e}")
            qr_img = None

    header_gap = 24 if header_text else 0
    label_gap = 14 if label else 0

    total_h = (pad
               + (header_h + header_gap if header_text else 0)
               + (label_h + label_gap if label else 0)
               + ts_h + pad
               + photos_total_h + pad
               + qr_section_h
               + 24)

    canvas = Image.new("L", (W, total_h), 255)
    d = ImageDraw.Draw(canvas)
    y = pad

    if header_text:
        bw, bh = _text_size(d, header_text, body_font)
        bx = (W - bw) // 2
        d.text((bx, y), header_text, fill=0, font=body_font)
        d.text((bx + 1, y), header_text, fill=0, font=body_font)
        y += bh + header_gap

    if label:
        lw, lh = _text_size(d, label, body_font)
        lx = (W - lw) // 2
        d.text((lx, y), label, fill=0, font=body_font)
        d.text((lx + 1, y), label, fill=0, font=body_font)
        y += lh + label_gap

    tw, th = _text_size(d, ts_text, body_font)
    d.text(((W - tw) // 2, y), ts_text, fill=0, font=body_font)
    y += th + pad

    for i, photo in enumerate(photos):
        x = (W - photo.width) // 2
        # thin black border around each photo so it reads as a strip
        d.rectangle([x - border, y - border,
                     x + photo.width + border - 1,
                     y + photo.height + border - 1], outline=0, width=border)
        canvas.paste(photo, (x, y))
        y += photo.height + 2 * border
        # caption under the photo (the pose prompt that was on screen)
        if prompts and i < len(prompts) and prompts[i]:
            y += caption_gap
            cap = prompts[i]
            cw, ch = _text_size(d, cap, caption_font)
            d.text(((W - cw) // 2, y), cap, fill=0, font=caption_font)
            y += caption_h
        if i < len(photos) - 1:
            y += photo_gap

    # QR code + small label
    if qr_img is not None:
        y += pad   # breathing room above the QR, never crowds the caption
        qx = (W - qr_img.width) // 2
        canvas.paste(qr_img, (qx, y))
        y += qr_img.height + 4
        lw, lh = _text_size(d, qr_label, caption_font)
        d.text(((W - lw) // 2, y), qr_label, fill=0, font=caption_font)
        y += lh + pad

    # cut line
    y_cut = total_h - 12
    for x in range(0, W, 6):
        d.line([(x, y_cut), (x + 3, y_cut)], fill=0)

    bg = Image.new("RGB", canvas.size, (250, 246, 235))
    bg.paste(canvas.convert("RGB"), (0, 0),
             ImageOps.invert(canvas).convert("L"))
    return bg


def justify_lines(text: str, width: int) -> list[str]:
    """Word-wrap `text` to `width` columns, then full-justify each line
    (except the last) by distributing extra spaces across the gaps. The
    final line is left as-is — that's the typographic convention and it
    avoids ugly stretched-space single-word lines.

    Works because the receipt printer's 1x bold font and our preview font
    are both monospaced: column count == visual width.
    """
    out = []
    paragraphs = text.splitlines() or [text]
    for para in paragraphs:
        wrapped = textwrap.wrap(para, width=width) or [""]
        for i, line in enumerate(wrapped):
            is_last = (i == len(wrapped) - 1)
            words = line.split()
            if is_last or len(words) <= 1 or len(line) >= width:
                out.append(line)
                continue
            extra = width - sum(len(w) for w in words) - (len(words) - 1)
            gaps = len(words) - 1
            # spread `extra` over `gaps`, with the first `extra % gaps`
            # getting one more space than the rest.
            base, leftover = divmod(extra, gaps)
            spaces = [" " * (1 + base + (1 if g < leftover else 0))
                      for g in range(gaps)]
            justified = ""
            for w, s in zip(words, spaces + [""]):
                justified += w + s
            out.append(justified)
    return out


# single worker — receipt printers are slow and serial; queueing protects us
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
_print_lock = threading.Lock()  # the actual USB transfer is not re-entrant


class _NullPrinter:
    def print_receipt(self, frame, text): pass
    def print_strip(self, pil_image): pass
    def shutdown(self): pass


class ReceiptPrinter:
    def __init__(self):
        # cheap probe: import the lib so we fail fast if missing. Don't open
        # the USB device yet — that's done per-print so we recover from
        # printer power-cycles without a restart.
        from escpos.printer import Usb  # noqa: F401

    # ---- image helpers ----

    def _crop_portrait(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Centre-crop to PRINTER_IMAGE_ASPECT (width/height, <1 = portrait)."""
        h, w = frame_bgr.shape[:2]
        target = config.PRINTER_IMAGE_ASPECT
        current = w / h
        if current > target:
            # too wide — crop sides
            new_w = int(round(h * target))
            x0 = (w - new_w) // 2
            return frame_bgr[:, x0:x0 + new_w]
        # too tall — crop top/bottom
        new_h = int(round(w / target))
        y0 = (h - new_h) // 2
        return frame_bgr[y0:y0 + new_h, :]

    def _prepare_image(self, frame_bgr: np.ndarray) -> Image.Image:
        """Crop → resize → tonemap → dither.

        The key step is Floyd–Steinberg dithering to 1-bit at the printer's
        native pixel grid. Pre-dithering it ourselves gives much better
        midtone reproduction than letting the printer threshold a greyscale
        image — without dither, anything below ~50% grey collapses to black,
        which is what made the photo look like a silhouette.
        """
        portrait = self._crop_portrait(frame_bgr)
        rgb = cv2.cvtColor(portrait, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)

        # scale to the printer's exact pixel width so the dither pattern
        # matches the dot grid 1:1 (avoids the printer re-sampling and
        # smearing the dither into mud)
        target_w = config.PRINTER_WIDTH_DOTS
        scale = target_w / img.width
        target_h = int(round(img.height * scale))
        img = img.resize((target_w, target_h), Image.LANCZOS)

        # greyscale + gentle global stretch
        img = img.convert("L")
        img = ImageOps.autocontrast(img, cutoff=config.PRINTER_IMAGE_AUTOCONTRAST)

        # brightness / contrast tweak before gamma
        if config.PRINTER_IMAGE_BRIGHTNESS != 1.0:
            img = ImageEnhance.Brightness(img).enhance(
                config.PRINTER_IMAGE_BRIGHTNESS)
        if config.PRINTER_IMAGE_CONTRAST != 1.0:
            img = ImageEnhance.Contrast(img).enhance(
                config.PRINTER_IMAGE_CONTRAST)

        # gamma — push midtones up so the dither has detail to play with
        gamma = config.PRINTER_IMAGE_GAMMA
        if gamma != 1.0:
            lut = [min(255, int(round(255 * (i / 255) ** gamma)))
                   for i in range(256)]
            img = img.point(lut)

        if config.PRINTER_IMAGE_SHARPEN:
            # a tiny unsharp before dither preserves edges through the
            # 1-bit conversion (faces, hair, eyes survive better)
            img = img.filter(ImageFilter.UnsharpMask(radius=1.2,
                                                    percent=120,
                                                    threshold=2))

        # Floyd–Steinberg dither to 1-bit at native resolution.
        return img.convert("1", dither=Image.FLOYDSTEINBERG)

    # ---- printing ----

    def _do_print(self, frame: np.ndarray, text: str):
        from escpos.printer import Usb
        from escpos.exceptions import USBNotFoundError
        with _print_lock:
            try:
                p = Usb(config.PRINTER_VENDOR_ID, config.PRINTER_PRODUCT_ID,
                        timeout=config.PRINTER_TIMEOUT_MS)
            except USBNotFoundError:
                # printer not plugged in — silently do nothing
                return
            except Exception as e:
                # any other open failure (permissions, busy, etc.) is worth a
                # one-liner so the user can debug
                print(f"[PRINTER] open failed: {e}")
                return
            try:
                ts = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")
                p.set(align="center", bold=True, width=1, height=1)
                if config.PRINTER_HEADER:
                    p.text(config.PRINTER_HEADER + "\n")
                    p.text("\n")  # breathing room between header and date
                p.set(align="center", bold=False)
                p.text(ts + "\n")
                p.text("\n")

                img = self._prepare_image(frame)
                # bitImageColumn is the most widely compatible image mode;
                # raster is faster on newer printers but breaks on some.
                p.image(img, impl="bitImageColumn", center=True)
                p.text("\n")

                response = (text or "").strip() or "..."
                # 1x bold, left-aligned + manually full-justified so the
                # text spans the full 32-col receipt width.
                p.set(align="left", bold=True, width=1, height=1)
                lines = justify_lines(response, width=config.PRINTER_TEXT_COLS)
                p.text("\n".join(lines) + "\n")

                p.set(align="center", bold=False, width=1, height=1)
                p.text("\n\n")
                p.cut()
            except Exception as e:
                print(f"[PRINTER] print failed: {e}")
            finally:
                # best-effort close; not all transports implement it
                try:
                    p.close()
                except Exception:
                    pass

    # ---- public ----

    def print_receipt(self, frame: np.ndarray, text: str) -> None:
        """Non-blocking: queues the receipt for printing."""
        if frame is None:
            return
        snapshot = frame.copy()
        _executor.submit(self._do_print, snapshot, text)

    def print_strip(self, pil_image: "Image.Image") -> None:
        """Print a pre-composed PIL image (e.g. a photobooth strip) and cut.
        Non-blocking. Skips silently if no printer is connected."""
        if pil_image is None:
            return
        _executor.submit(self._do_print_strip, pil_image.copy())

    def _do_print_strip(self, pil_image: "Image.Image"):
        from escpos.printer import Usb
        from escpos.exceptions import USBNotFoundError
        with _print_lock:
            try:
                p = Usb(config.PRINTER_VENDOR_ID, config.PRINTER_PRODUCT_ID,
                        timeout=config.PRINTER_TIMEOUT_MS)
            except USBNotFoundError:
                return
            except Exception as e:
                print(f"[PRINTER] open failed: {e}")
                return
            try:
                # escpos accepts greyscale; the PIL image already has the
                # dither baked in so the printer doesn't need to re-quantise.
                p.image(pil_image.convert("L"), impl="bitImageColumn",
                        center=True)
                p.text("\n\n")
                p.cut()
            except Exception as e:
                print(f"[PRINTER] strip print failed: {e}")
            finally:
                try:
                    p.close()
                except Exception:
                    pass

    def shutdown(self) -> None:
        # nothing persistent to clean up; the executor is process-lifetime
        pass


def create_printer():
    """Return a ReceiptPrinter, or _NullPrinter if the library is missing."""
    try:
        return ReceiptPrinter()
    except Exception as e:
        print(f"[PRINTER] not available, disabling: {e}")
        return _NullPrinter()
