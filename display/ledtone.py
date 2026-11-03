"""Tone for pictures of people on the LED wall (mirror photos, the booth, the live mirror's shading).

LEDs wash a normal photograph out: shadows go to black, the middle goes flat and colours lose their punch. This keeps the face
readable and gives the picture more bite: local contrast (CLAHE on the luminance), an S-curve that opens the middle, a floor that
keeps dark clothes above the panels' black, a little more colour, and a touch of unsharp mask. Works at wall size (192 x 256).
"""
import cv2
import numpy as np

_clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(4, 4))


def scurve(x, amount=0.55):
    """Contrast curve on 0..1: blends the identity with a smoothstep. amount 0 = unchanged."""
    s = x * x * (3.0 - 2.0 * x)
    return (1.0 - amount) * x + amount * s


def tone_rgb(rgb, local=0.45, curve=0.5, sat=1.28, floor=0.05, sharpen=0.5, smooth=None):
    """rgb: HxWx3 uint8 -> uint8, toned for the wall. `smooth`: a dict kept between frames of a live picture, so the tonal range
    follows the scene slowly instead of pumping with every frame."""
    bgr = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L0 = lab[:, :, 0].astype(np.float32) / 255.0
    L1 = _clahe.apply(lab[:, :, 0]).astype(np.float32) / 255.0
    L = L0 + local * (L1 - L0)                                       # local contrast, not all of it: skin stays natural
    lo, hi = np.percentile(L, (1.5, 98.5))                           # stretch to what is in the picture
    if smooth is not None:
        if "lo" in smooth:
            lo = smooth["lo"] + (lo - smooth["lo"]) * 0.08
            hi = smooth["hi"] + (hi - smooth["hi"]) * 0.08
        smooth["lo"], smooth["hi"] = float(lo), float(hi)
    L = np.clip((L - lo) / max(hi - lo, 0.25), 0, 1)
    L = scurve(L, curve)
    if sharpen:
        L = np.clip(L + sharpen * (L - cv2.GaussianBlur(L, (0, 0), 1.2)), 0, 1)
    L = floor + (0.985 - floor) * L
    a = (lab[:, :, 1].astype(np.float32) - 128.0) * sat + 128.0
    b = (lab[:, :, 2].astype(np.float32) - 128.0) * sat + 128.0
    out = np.dstack([L * 255.0, np.clip(a, 0, 255), np.clip(b, 0, 255)]).astype(np.uint8)
    return cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_LAB2BGR), cv2.COLOR_BGR2RGB)


def tone_pil(img, **kw):
    from PIL import Image
    return Image.fromarray(tone_rgb(np.asarray(img.convert("RGB")), **kw), "RGB")


def fast_tone(rgb, smooth, sat=1.2, curve=0.45, floor=0.04, sharpen=0.35):
    """A cheap version of tone_rgb for the live mirror (a few ms on the Pi instead of 60): one lookup table for the tone (range
    stretch that follows the scene slowly, S-curve, floor), a touch more colour and a small unsharp mask. `smooth` is kept between
    frames."""
    small = rgb[::8, ::8]
    g = small.mean(axis=2)
    lo, hi = np.percentile(g, (1.5, 98.5))
    if "lo" in smooth:
        lo = smooth["lo"] + (lo - smooth["lo"]) * 0.06
        hi = smooth["hi"] + (hi - smooth["hi"]) * 0.06
    smooth["lo"], smooth["hi"] = float(lo), float(hi)
    x = np.clip((np.arange(256, dtype=np.float32) - lo) / max(hi - lo, 70.0), 0, 1)
    lut = ((floor + (0.985 - floor) * scurve(x, curve)) * 255.0).astype(np.uint8)
    out = cv2.LUT(rgb, lut)
    gray = cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)
    out = cv2.addWeighted(out, sat, cv2.merge([gray, gray, gray]), 1.0 - sat, 0)          # more colour
    if sharpen:
        out = cv2.addWeighted(out, 1.0 + sharpen, cv2.GaussianBlur(out, (0, 0), 1.3), -sharpen, 0)
    return out
