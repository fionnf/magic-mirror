"""Print a real receipt on the actual thermal printer.

Exercises the full ReceiptPrinter pipeline — header, timestamp, portrait-
cropped image, justified phrase, cut — so you can verify the printer is
wired correctly and the output looks like the preview.

Usage:
    python tests/test_printer_live.py                          # default sample
    python tests/test_printer_live.py --image foo.jpg
    python tests/test_printer_live.py --text "Custom phrase."
    python tests/test_printer_live.py --pattern                # alignment ruler

If python-escpos isn't installed or the printer isn't plugged in, you'll
get a clear error. Otherwise the receipt prints and the script exits.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import printer as printer_mod


SAMPLE_PHRASE = "Your eyes hold the weight of forgotten stars."


def synthetic_image():
    """A simple test image with a target + text so you can see if the
    image pipeline lands at the right size and orientation."""
    h, w = 480, 360  # already portrait
    img = np.full((h, w, 3), 220, dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (w - 11, h - 11), (0, 0, 0), 3)
    cv2.circle(img, (w // 2, h // 2), 110, (60, 60, 60), -1)
    cv2.line(img, (0, 0), (w, h), (0, 0, 0), 1)
    cv2.line(img, (w, 0), (0, h), (0, 0, 0), 1)
    cv2.putText(img, "MIRROR TEST", (40, h // 2 + 8),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return img


def alignment_pattern(p):
    """Print a column ruler + every-char string so you can spot if the
    rightmost characters are getting clipped at PRINTER_WIDTH_DOTS."""
    p.set(align="left", bold=False, width=1, height=1)
    ruler = "".join(str(i % 10) for i in range(config.PRINTER_TEXT_COLS))
    p.text(ruler + "\n")
    p.text("." * config.PRINTER_TEXT_COLS + "\n")
    p.text("M" * config.PRINTER_TEXT_COLS + "\n")
    p.text("W" * config.PRINTER_TEXT_COLS + "\n")
    p.text("|" + "-" * (config.PRINTER_TEXT_COLS - 2) + "|" + "\n")
    p.text("\n\n")
    p.cut()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image",
                    default=os.path.join(os.path.dirname(__file__), "test_image.jpg"))
    ap.add_argument("--text", default=SAMPLE_PHRASE)
    ap.add_argument("--pattern", action="store_true",
                    help="print an alignment-ruler test instead of a receipt")
    args = ap.parse_args()

    # Pattern mode: open the printer directly, dump the ruler, cut, done.
    if args.pattern:
        try:
            from escpos.printer import Usb
        except Exception as e:
            print(f"[LIVE] python-escpos not installed: {e}")
            sys.exit(1)
        try:
            p = Usb(config.PRINTER_VENDOR_ID, config.PRINTER_PRODUCT_ID,
                    timeout=config.PRINTER_TIMEOUT_MS)
        except Exception as e:
            print(f"[LIVE] open failed: {e}")
            sys.exit(1)
        alignment_pattern(p)
        try:
            p.close()
        except Exception:
            pass
        print("[LIVE] alignment pattern printed")
        return

    # Receipt mode: go through the real ReceiptPrinter.
    if os.path.exists(args.image):
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"[LIVE] could not decode {args.image}, using synthetic")
            frame = synthetic_image()
    else:
        print(f"[LIVE] {args.image} missing — using synthetic placeholder")
        frame = synthetic_image()

    rp = printer_mod.create_printer()
    if isinstance(rp, printer_mod._NullPrinter):
        print("[LIVE] python-escpos missing — install requirements first")
        sys.exit(1)

    print(f"[LIVE] vendor={config.PRINTER_VENDOR_ID:#06x} "
          f"product={config.PRINTER_PRODUCT_ID:#06x} "
          f"width={config.PRINTER_WIDTH_DOTS}dot cols={config.PRINTER_TEXT_COLS}")
    print(f"[LIVE] header={config.PRINTER_HEADER!r}")
    print(f"[LIVE] text={args.text!r}")

    # Call the underlying sync method directly so we know when it finishes
    # (the public print_receipt is fire-and-forget via an executor).
    rp._do_print(frame, args.text)
    # the per-print USB open inside _do_print already closes; give the
    # printer a moment to flush before we exit.
    time.sleep(0.5)
    print("[LIVE] done")


if __name__ == "__main__":
    main()
