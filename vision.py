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


def _small(img):
    return cv2.resize(img, config.SILHOUETTE_PROC_SIZE, interpolation=cv2.INTER_AREA)


def silhouette_mask(frame: np.ndarray, background=None, subtractor=None) -> np.ndarray:
    """Return a uint8 0/255 mask at (TOTAL_WIDTH, TOTAL_HEIGHT)."""
    small = _small(frame)
    if background is not None:
        if _bg_cache["id"] != id(background):
            _bg_cache["id"] = id(background)
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
    return cv2.resize(mask, (config.TOTAL_WIDTH, config.TOTAL_HEIGHT),
                      interpolation=cv2.INTER_LINEAR)
