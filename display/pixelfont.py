"""A 3x5 pixel font (capitals, digits, a few signs): the smallest text that still reads on the wall."""
import numpy as np

_G = {
    "A": "010101111101101", "B": "110101110101110", "C": "011100100100011", "D": "110101101101110",
    "E": "111100110100111", "F": "111100110100100", "G": "011100101101011", "H": "101101111101101",
    "I": "111010010010111", "J": "001001001101010", "K": "101101110101101", "L": "100100100100111",
    "M": "101111111101101", "N": "110101101101101", "O": "010101101101010", "P": "110101110100100",
    "Q": "010101101110011", "R": "110101110101101", "S": "011100010001110", "T": "111010010010010",
    "U": "101101101101111", "V": "101101101101010", "W": "101101111111101", "X": "101101010101101",
    "Y": "101101010010010", "Z": "111001010100111",
    "0": "111101101101111", "1": "010110010010111", "2": "110001010100111", "3": "110001010001110",
    "4": "101101111001001", "5": "111100110001110", "6": "011100111101111", "7": "111001010010010",
    "8": "111101111101111", "9": "111101111001110", "-": "000000111000000", ".": "000000000000010",
    " ": "000000000000000",
}
GLYPHS = {k: np.array([int(c) for c in v], np.float32).reshape(5, 3) for k, v in _G.items()}


def width(text):
    return max(0, 4 * len(text) - 1)


def draw(img, text, x, y, colour):
    """Write text into an HxWx3 float/uint8 array at (x, y) (top-left), clipped to the image."""
    H, W = img.shape[:2]
    col = np.asarray(colour, np.float32)
    for ch in text.upper():
        g = GLYPHS.get(ch)
        if g is not None:
            y0, y1, x0, x1 = max(0, y), min(H, y + 5), max(0, x), min(W, x + 3)
            if y0 < y1 and x0 < x1:
                m = g[y0 - y:y1 - y, x0 - x:x1 - x][..., None]
                region = img[y0:y1, x0:x1]
                img[y0:y1, x0:x1] = np.maximum(region, (m * col).astype(img.dtype))
        x += 4
