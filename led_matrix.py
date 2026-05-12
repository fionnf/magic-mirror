"""Real HUB75 LED matrix driver. Requires rpi-rgb-led-matrix Python bindings."""
import threading
import numpy as np
from PIL import Image
import config


class LedMatrix:
    def __init__(self):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        opts = RGBMatrixOptions()
        opts.rows = config.PANEL_ROWS
        opts.cols = config.PANEL_COLS
        opts.chain_length = config.CHAIN_LENGTH
        opts.parallel = config.PARALLEL
        opts.hardware_mapping = config.HARDWARE_MAPPING
        opts.pixel_mapper_config = config.PIXEL_MAPPER
        opts.gpio_slowdown = config.GPIO_SLOWDOWN
        opts.multiplexing = 0
        opts.brightness = 80
        opts.drop_privileges = False
        self.matrix = RGBMatrix(options=opts)
        self.canvas = self.matrix.CreateFrameCanvas()
        self._lock = threading.Lock()
        self._brightness = 80

    def draw(self, image: Image.Image) -> None:
        if image.size != (config.TOTAL_WIDTH, config.TOTAL_HEIGHT):
            image = image.resize((config.TOTAL_WIDTH, config.TOTAL_HEIGHT))
        if image.mode != "RGB":
            image = image.convert("RGB")
        with self._lock:
            self.canvas.SetImage(image)
            self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self) -> None:
        black = Image.new("RGB", (config.TOTAL_WIDTH, config.TOTAL_HEIGHT), (0, 0, 0))
        self.draw(black)

    def set_brightness(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self._brightness = value
        with self._lock:
            self.matrix.brightness = value

    def shutdown(self) -> None:
        self.clear()
