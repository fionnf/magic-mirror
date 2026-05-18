"""Text rendering and scrolling onto a PIL canvas."""
import os
import time
from PIL import Image, ImageDraw, ImageFont
import config


def _load_font():
    candidates = [
        config.FONT_PATH,
        os.path.join(os.path.dirname(__file__), "..", config.FONT_PATH),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, 10)
            except Exception:
                pass
    return ImageFont.load_default()


_FONT = _load_font()


def _text_size(draw: ImageDraw.ImageDraw, text: str):
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=_FONT)
        return r - l, b - t
    except Exception:
        return draw.textsize(text, font=_FONT)


def render_static_text(canvas: Image.Image, text: str,
                       colour=config.TEXT_COLOUR, y_offset: int = None) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    w, h = _text_size(draw, text)
    x = max(0, (canvas.width - w) // 2)
    y = y_offset if y_offset is not None else max(0, (canvas.height - h) // 2)
    draw.text((x, y), text, fill=colour, font=_FONT)
    return canvas


def scroll_text_frames(text: str, colour=config.TEXT_COLOUR,
                       speed: int = config.MESSAGE_SCROLL_SPEED,
                       background: Image.Image = None):
    """Yields (frame_image, finished_bool) for the duration of a R->L scroll.

    The text starts entirely off the right edge and finishes once its tail is
    off the left edge.
    """
    width, height = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    tmp = Image.new("RGB", (width, height))
    d = ImageDraw.Draw(tmp)
    tw, th = _text_size(d, text)

    total_px = width + tw
    duration = total_px / max(1, speed)
    start = time.monotonic()
    while True:
        t = time.monotonic() - start
        progress = min(1.0, t / duration)
        x = int(width - progress * total_px)
        frame = (background.copy() if background is not None
                 else Image.new("RGB", (width, height), (0, 0, 0)))
        d2 = ImageDraw.Draw(frame)
        y = max(0, (height - th) // 2)
        d2.text((x, y), text, fill=colour, font=_FONT)
        finished = progress >= 1.0
        yield frame, finished
        if finished:
            return


def scroll_text(matrix, text: str, colour=config.TEXT_COLOUR,
                speed: int = config.MESSAGE_SCROLL_SPEED,
                background: Image.Image = None,
                fps: int = config.IDLE_ANIMATION_FPS) -> None:
    interval = 1.0 / fps
    for frame, finished in scroll_text_frames(text, colour, speed, background):
        matrix.draw(frame)
        if finished:
            break
        time.sleep(interval)
