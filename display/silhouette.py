"""Render a silhouette mask onto a PIL RGB canvas."""
import numpy as np
from PIL import Image
import cv2
import config
import vision


def render_silhouette(mask: np.ndarray, colour=config.SILHOUETTE_COLOUR,
                      brightness: float = 1.0) -> Image.Image:
    """mask: 2D uint8 (0 or 255), size TOTAL_WIDTH x TOTAL_HEIGHT.
    With config.SILHOUETTE_DETAIL the person is lit by the camera's own light (see vision._detail) inside a soft
    edge with a brighter rim; otherwise (or if no detail was made for this mask) it is a flat colour."""
    c = np.array(colour, dtype=np.float32) * float(max(0.0, min(1.0, brightness)))
    alpha, detail = vision.last["alpha"], vision.last["detail"]
    if (getattr(config, "SILHOUETTE_DETAIL", False) and alpha is not None and alpha.shape == mask.shape
            and np.array_equal(alpha > 0.5, mask > 127)):
        rim = np.clip(alpha - cv2.erode(alpha, np.ones((3, 3), np.uint8)), 0, 1)     # a bright edge line
        light = alpha * (0.30 + 0.70 * detail)                       # shadows stay above the LEDs' dark floor
        rgb = light[:, :, None] * c + rim[:, :, None] * (0.45 * c + 40.0 * min(1.0, brightness))
        return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    rgb = (mask > 127)[:, :, None] * c.astype(np.uint8)         # (h, w, 3) uint8, no fancy-index write
    return Image.fromarray(rgb, "RGB")


def composite(background: Image.Image, overlay: Image.Image, alpha: float = 1.0) -> Image.Image:
    if background.size != overlay.size:
        overlay = overlay.resize(background.size)
    return Image.blend(background.convert("RGB"), overlay.convert("RGB"), alpha)
