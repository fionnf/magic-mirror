"""Receipt and booth-strip printer tests.

Usage
-----
  python tests/test_printer.py                    # receipt preview PNG
  python tests/test_printer.py --strip            # booth-strip composer
  python tests/test_printer.py --print            # also send to USB printer
  python tests/test_printer.py --strip --qr-url https://example.com

render_preview() is imported by test_full_sim.py to save per-cycle PNG
previews of what would come out of the printer.
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import config
from printer import _receipt_image, create_printer, render_booth_pil


# ---------------------------------------------------------------------------
# Public helper used by test_full_sim.SimPrinter
# ---------------------------------------------------------------------------

def render_preview(frame: np.ndarray, text: str, out_path: str) -> None:
    """Save a greyscale PNG preview of what the receipt printer would produce."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img = _receipt_image(frame, text)
    img.save(out_path)


# ---------------------------------------------------------------------------
# Standalone test helpers
# ---------------------------------------------------------------------------

def _make_test_frame() -> np.ndarray:
    """Synthesise a plausible camera frame when no test image is available."""
    h, w = config.FRAME_HEIGHT, config.FRAME_WIDTH
    f = np.full((h, w, 3), (130, 110, 90), dtype=np.uint8)
    cy, cx = h // 3, w // 2
    cv2.circle(f, (cx, cy), min(h, w) // 5, (50, 45, 40), -1)
    return cv2.cvtColor(f, cv2.COLOR_RGB2BGR)


def _out_dir() -> str:
    d = os.path.join(os.path.dirname(__file__), "sim_receipts")
    os.makedirs(d, exist_ok=True)
    return d


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--image",
                   default=os.path.join(os.path.dirname(__file__), "test_image.jpg"))
    p.add_argument("--strip", action="store_true",
                   help="Test the booth-strip composer instead of a receipt")
    p.add_argument("--print", dest="do_print", action="store_true",
                   help="Also send output to the USB printer")
    p.add_argument("--qr-url", default="",
                   help="Embed a QR code pointing at this URL (strip only)")
    args = p.parse_args()

    frame = cv2.imread(args.image)
    if frame is None:
        print(f"[PRINTER TEST] {args.image} not found — using synthetic frame")
        frame = _make_test_frame()

    out = _out_dir()

    if args.strip:
        frames = [frame, frame, frame]
        prompts = ["Best regal pose", "Show me chaos", "Fake-laugh at a joke"]
        strip = render_booth_pil(
            frames, label="PHOTOBOOTH", prompts=prompts,
            qr_url=args.qr_url or None)
        path = os.path.join(out, "strip_preview.png")
        strip.save(path)
        print(f"[PRINTER TEST] booth strip  -> {path}  ({strip.width}×{strip.height}px)")
        if args.do_print:
            create_printer().print_strip(strip)
    else:
        text = "The mirror sees all, but speaks slowly tonight."
        path = os.path.join(out, "receipt_preview.png")
        render_preview(frame, text, path)
        print(f"[PRINTER TEST] receipt preview -> {path}")
        if args.do_print:
            create_printer().print_receipt(frame, text)


if __name__ == "__main__":
    main()
