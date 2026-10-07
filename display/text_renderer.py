"""Text rendering and scrolling onto a PIL canvas."""
import os
import time
from PIL import Image, ImageDraw, ImageFont
import config


def _load_font(size: int):
    here = os.path.dirname(__file__)
    candidates = list(config.TEXT_FONT_PATHS) + [
        config.FONT_PATH,
        os.path.join(here, "..", config.FONT_PATH),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)      # Pillow >= 10.1: scalable
    except TypeError:
        return ImageFont.load_default()


_FONT = _load_font(config.TEXT_FONT_SIZE)
_STROKE = config.TEXT_STROKE_WIDTH
_STROKE_FILL = config.TEXT_STROKE_COLOUR


def _text_size(draw: ImageDraw.ImageDraw, text: str):
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=_FONT, stroke_width=_STROKE)
        return r - l, b - t
    except Exception:
        return draw.textsize(text, font=_FONT)


def _text_box(draw: ImageDraw.ImageDraw, text: str):
    """(left, top, width, height) of the inked area, outline included."""
    l, t, r, b = draw.textbbox((0, 0), text, font=_FONT, stroke_width=_STROKE)
    return l, t, r - l, b - t


def render_static_text(canvas: Image.Image, text: str,
                       colour=config.TEXT_COLOUR, y_offset: int = None) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    l, t, w, h = _text_box(draw, text)
    x = max(0, (canvas.width - w) // 2) - l
    y = (y_offset if y_offset is not None else max(0, (canvas.height - h) // 2)) - t
    draw.text((x, y), text, fill=colour, font=_FONT,
              stroke_width=_STROKE, stroke_fill=_STROKE_FILL)
    return canvas


def _text_strip(text: str, colour) -> Image.Image:
    """Render the whole message once as an RGBA strip (transparent around the
    outlined text). Scrolling then only slides this strip each frame."""
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, w, h = _text_box(probe, text)
    strip = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    ImageDraw.Draw(strip).text((-l, -t), text, fill=colour + (255,), font=_FONT,
                               stroke_width=_STROKE, stroke_fill=_STROKE_FILL + (255,))
    return strip


def scroll_text_frames(text: str, colour=config.TEXT_COLOUR,
                       speed: int = None,
                       background: Image.Image = None,
                       rgba: bool = False):
    """Yields (frame_image, finished_bool) for the duration of a R->L scroll.

    The text starts entirely off the right edge and finishes once its tail is
    off the left edge. With rgba=True frames are transparent except for the
    outlined text, for pasting over a live background.
    """
    width, height = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    speed = speed or config.MESSAGE_SCROLL_SPEED
    strip = _text_strip(text, tuple(colour))
    tw, th = strip.size
    y = max(0, (height - th) // 2)

    total_px = width + tw
    duration = total_px / max(1, speed)
    start = time.monotonic()
    while True:
        t = time.monotonic() - start
        progress = min(1.0, t / duration)
        x = int(width - progress * total_px)
        if rgba:
            frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            frame.paste(strip, (x, y))
        else:
            frame = (background.copy().convert("RGB") if background is not None
                     else Image.new("RGB", (width, height), (0, 0, 0)))
            frame.paste(strip, (x, y), strip)
        finished = progress >= 1.0
        yield frame, finished
        if finished:
            return


def scroll_text(matrix, text: str, colour=config.TEXT_COLOUR,
                speed: int = None,
                background: Image.Image = None,
                fps: int = config.IDLE_ANIMATION_FPS) -> None:
    interval = 1.0 / fps
    for frame, finished in scroll_text_frames(text, colour, speed, background):
        matrix.draw(frame)
        if finished:
            break
        time.sleep(interval)
