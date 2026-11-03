"""The house-info slip for the receipt printer: Wi-Fi, writing on the board, today's pictures, and a few notes.

slip_image() returns a black-on-white greyscale picture at the printer's width (print_out.WIDTH, 384 dots). The QR codes are pure black and
white at whole-dot module sizes, so the printer's dithering leaves them crisp and they scan from the paper.
"""
import datetime
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

import config

WIDTH = 384
QR_PX = 224


def _font(size):
    for path in list(getattr(config, "TEXT_FONT_PATHS", [])) + ["/System/Library/Fonts/Supplemental/Arial Bold.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _qr(data, px=QR_PX):
    import qrcode
    q = qrcode.QRCode(border=2, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(data)
    q.make(fit=True)
    n = len(q.get_matrix())
    box = max(2, px // n)                                   # whole dots per module: no blur
    q2 = qrcode.QRCode(border=2, box_size=box, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q2.add_data(data)
    q2.make(fit=True)
    return q2.make_image(fill_color="black", back_color="white").convert("L")


def _centered(d, y, text, font, fill=0, max_w=WIDTH - 24):
    """Draw wrapped, centred text; returns the next y."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    for ln in lines:
        d.text((WIDTH / 2, y), ln, font=font, fill=fill, anchor="ma")
        y += int(font.size * 1.25)
    return y


def slip_image(wifi, guest_url, pictures_url, notes="", today=None):
    """wifi = (ssid, password, security, payload) or None. Any missing link is simply left out."""
    today = today or datetime.date.today()
    big, mid, small = _font(40), _font(28), _font(22)
    blocks = []                                             # (title, qr data, caption lines)
    if wifi and wifi[0]:
        ssid, pw, sec, payload = wifi
        cap = [f"Network: {ssid}"] + ([f"Password: {pw}"] if pw and sec != "nopass" else ["Open network, no password"])
        blocks.append(("1  Join the Wi-Fi", payload, cap))
    if guest_url:
        blocks.append(("2  Write on the board", guest_url, ["Send a message to the LED wall.", "Join the Wi-Fi first."]))
    if pictures_url:
        blocks.append(("3  Today's pictures", pictures_url, ["Everything from today, to keep."]))

    # measure first, draw second
    probe = ImageDraw.Draw(Image.new("L", (WIDTH, 10)))
    h = 18 + 52 + 34 + 16
    for title, data, cap in blocks:
        h += 44 + QR_PX + 10 + sum(int(small.size * 1.25) * (1 + int(probe.textlength(c, font=small) // (WIDTH - 24))) for c in cap) + 26
    note_lines = []
    for para in (notes or "").splitlines():
        note_lines += textwrap.wrap(para, 28) or [""]
    if note_lines:
        h += 50 + len(note_lines) * int(small.size * 1.3) + 16
    h += 70
    img = Image.new("L", (WIDTH, h), 255)
    d = ImageDraw.Draw(img)
    y = 18
    d.text((WIDTH / 2, y), "HOUSE FORTUNA", font=big, fill=0, anchor="ma"); y += 52
    d.text((WIDTH / 2, y), "Fortunagasse 24", font=mid, fill=0, anchor="ma"); y += 34
    d.text((WIDTH / 2, y), today.strftime("%A %-d %B") if os.name != "nt" else today.isoformat(), font=small, fill=80, anchor="ma"); y += 30
    d.line([(20, y), (WIDTH - 20, y)], fill=0, width=3); y += 14
    for title, data, cap in blocks:
        d.text((WIDTH / 2, y), title, font=mid, fill=0, anchor="ma"); y += 44
        qr = _qr(data)
        img.paste(qr, ((WIDTH - qr.width) // 2, y)); y += qr.height + 10
        for c in cap:
            y = _centered(d, y, c, small)
        y += 8
        d.line([(60, y), (WIDTH - 60, y)], fill=0, width=1); y += 18
    if note_lines:
        d.text((WIDTH / 2, y), "House notes", font=mid, fill=0, anchor="ma"); y += 44
        for ln in note_lines:
            d.text((24, y), ln, font=small, fill=0); y += int(small.size * 1.3)
        y += 16
    d.text((WIDTH / 2, y + 6), "Prost!", font=big, fill=0, anchor="ma")
    return img.crop((0, 0, WIDTH, min(h, y + 64)))
