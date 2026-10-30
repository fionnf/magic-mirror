"""Cheap silhouette extraction shared by the real and mock cameras.

All the OpenCV work (absdiff, threshold, blur, morphology) runs on a small
PROC_SIZE image instead of the full 640x480 frame; only the final binary mask
is scaled up to the LED canvas. A silhouette doesn't need the extra pixels, and
this is the biggest per-frame CPU cost of the always-on silhouette loop.
"""
import cv2
import numpy as np
import config

_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
_bg_cache = {"id": None, "small": None}
_clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 6))
last = {"alpha": None, "detail": None, "colour": None}      # the latest silhouette at wall size: soft edge 0..1 and shading 0..1


_tone = {"rgb": None}                             # the last picture: new frames are blended into it


def _detail(frame, alpha):
    """The camera's own light inside the silhouette at wall resolution. Returns (shade, colour): shade is 0..1
    luminance with local contrast (CLAHE, then two scales of unsharp mask: fine for eyes and hair strands, coarse for
    the shape of a face and clothing folds), stretched over the person only; colour is that shade in the camera's own
    hues (a little more saturated, since LEDs wash colour out), an HxWx3 float RGB 0..1."""
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    small = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)     # the shrink itself averages the noise away
    small = cv2.bilateralFilter(small, 5, 28, 5)                        # at wall size: 12x fewer pixels than the full frame
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
    L = _clahe.apply(lab[:, :, 0]).astype(np.float32) / 255.0
    inside = alpha > 0.6
    if inside.sum() > 200:                                              # stretch to the person, not the room
        lo, hi = np.percentile(L[inside], (3, 97))
        L = np.clip((L - lo) / max(hi - lo, 0.08), 0, 1)
    fine = L - cv2.GaussianBlur(L, (0, 0), 1.0)
    coarse = L - cv2.GaussianBlur(L, (0, 0), 3.0)
    L = np.power(np.clip(L + 0.85 * fine + 0.45 * coarse, 0, 1), 0.85)
    shade = np.clip(0.14 + 0.80 * L, 0, 1)                              # dark clothes stay above the LEDs' floor
    a = (lab[:, :, 1].astype(np.float32) - 128.0) * 1.35
    b = (lab[:, :, 2].astype(np.float32) - 128.0) * 1.35
    lab2 = np.dstack([np.clip(shade * 255.0, 0, 255), np.clip(a + 128.0, 0, 255), np.clip(b + 128.0, 0, 255)]).astype(np.uint8)
    rgb = cv2.cvtColor(cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    prev = _tone["rgb"]
    if prev is not None and prev.shape == rgb.shape:                    # blend with the last picture: evens out the camera's
        rgb = prev * 0.4 + rgb * 0.6                                    # exposure pumping and mains-light flicker
    _tone["rgb"] = rgb
    return shade, rgb


def crop_to_aspect(img: np.ndarray, aspect: float, v_bias: float = 0.4) -> np.ndarray:
    """Centre-crop to width/height = aspect. v_bias < 0.5 keeps a little more
    of the top (heads) when cropping height."""
    h, w = img.shape[:2]
    if w / h > aspect:
        nw = int(round(h * aspect))
        x0 = (w - nw) // 2
        return img[:, x0:x0 + nw]
    nh = int(round(w / aspect))
    y0 = int((h - nh) * v_bias)
    return img[y0:y0 + nh, :]


def _small(img):
    wall = config.TOTAL_WIDTH / config.TOTAL_HEIGHT
    pw = config.SILHOUETTE_PROC_SIZE[1] * wall          # keep the wall's aspect
    return cv2.resize(img, (int(round(pw)), config.SILHOUETTE_PROC_SIZE[1]),
                      interpolation=cv2.INTER_AREA)


_hold = {"m": None, "on": None}


def _steady(level, thresh):
    """A calm mask: the per-pixel level is averaged over the last few frames, and a pixel that is
    already part of the person stays in until it falls well below the threshold (hysteresis). Camera
    noise near the threshold made edge pixels flip on and off every frame - the mirror's flicker."""
    m = level.astype(np.float32)
    if _hold["m"] is None or _hold["m"].shape != m.shape:
        _hold["m"], _hold["on"] = m, m > thresh
    else:
        _hold["m"] += (m - _hold["m"]) * 0.5
    m = _hold["m"]
    on = (m > thresh) | (_hold["on"] & (m > 0.6 * thresh))
    _hold["on"] = on
    return on.astype(np.uint8) * 255


def silhouette_mask(frame: np.ndarray, background=None, subtractor=None) -> np.ndarray:
    """Return a uint8 0/255 mask at (TOTAL_WIDTH, TOTAL_HEIGHT)."""
    wall = config.TOTAL_WIDTH / config.TOTAL_HEIGHT
    frame = crop_to_aspect(frame, wall)
    if background is not None:
        background = crop_to_aspect(background, wall)
    small = _small(frame)
    if background is not None:
        key = (background.__array_interface__["data"][0], background.shape)
        if _bg_cache["id"] != key:
            _bg_cache["id"] = key
            _bg_cache["small"] = _small(background)
        grey = cv2.cvtColor(cv2.absdiff(small, _bg_cache["small"]),
                            cv2.COLOR_BGR2GRAY)
        mask = _steady(grey, config.SILHOUETTE_DIFF_THRESHOLD)
    else:
        mask = _steady(subtractor.apply(small), 127)
    mask = cv2.medianBlur(mask, 3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL)
    wall_size = (config.TOTAL_WIDTH, config.TOTAL_HEIGHT)
    if getattr(config, "SILHOUETTE_DETAIL", False):
        alpha = cv2.resize(mask.astype(np.float32) / 255.0, wall_size, interpolation=cv2.INTER_CUBIC)
        alpha = np.clip(cv2.GaussianBlur(alpha, (0, 0), 0.7), 0, 1)        # an anti-aliased edge
        detail, colour = _detail(frame, alpha)
        if config.SILHOUETTE_MIRROR:
            alpha, detail, colour = cv2.flip(alpha, 1), cv2.flip(detail, 1), cv2.flip(colour, 1)
        last["alpha"], last["detail"], last["colour"] = alpha, detail, colour
        mask = (alpha > 0.5).astype(np.uint8) * 255                      # the binary mask the rest of the code expects
        return mask
    mask = cv2.resize(mask, wall_size, interpolation=cv2.INTER_LINEAR)
    if config.SILHOUETTE_MIRROR:
        mask = cv2.flip(mask, 1)        # behave like a mirror: your right = wall's right
    return mask
