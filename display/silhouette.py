"""Render a silhouette mask onto a PIL RGB canvas."""
import numpy as np
from PIL import Image
import config


def render_silhouette(mask: np.ndarray, colour=config.SILHOUETTE_COLOUR,
                      brightness: float = 1.0) -> Image.Image:
    """mask: 2D uint8 (0 or 255), size TOTAL_WIDTH x TOTAL_HEIGHT."""
    c = (np.array(colour, dtype=np.float32)
         * float(max(0.0, min(1.0, brightness)))).astype(np.uint8)
    rgb = (mask > 127)[:, :, None] * c            # (h, w, 3) uint8, no fancy-index write
    return Image.fromarray(rgb, "RGB")


def composite(background: Image.Image, overlay: Image.Image, alpha: float = 1.0) -> Image.Image:
    if background.size != overlay.size:
        overlay = overlay.resize(background.size)
    return Image.blend(background.convert("RGB"), overlay.convert("RGB"), alpha)
