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
        _, mask = cv2.threshold(grey, config.SILHOUETTE_DIFF_THRESHOLD,
                                255, cv2.THRESH_BINARY)
    else:
        mask = subtractor.apply(small)
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    mask = cv2.medianBlur(mask, 3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL)
    mask = cv2.resize(mask, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT),
                      interpolation=cv2.INTER_LINEAR)
    if config.SILHOUETTE_MIRROR:
        mask = cv2.flip(mask, 1)        # behave like a mirror: your right = wall's right
    return mask
