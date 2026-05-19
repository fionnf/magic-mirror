"""Render a PNG preview of the receipt that would be printed.

No printer required. Uses the shared renderer in `printer.py` so the
preview is byte-identical to what the real printer outputs.

Usage:
    python tests/test_printer.py [--image foo.jpg] [--text "..."] [--show]
"""
import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from printer import save_receipt_png


def _synth_face_frame():
    """Synthetic gradient placeholder so the dither has something to render."""
    import numpy as np
    h, w = 480, 640
    yy, xx = np.indices((h, w))
    grad = (yy * (180 / h)).astype("uint8") + 50
    frame = np.stack([grad, grad, grad], axis=-1).astype("uint8")
    cy, cx, r = 230, 320, 150
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2) / r
    shade = np.clip(255 - 200 * dist, 0, 255).astype("uint8")
    mask = dist < 1.0
    for c in range(3):
        ch = frame[..., c]
        ch[mask] = shade[mask]
    cv2.circle(frame, (280, 215), 14, (40, 40, 40), -1)
    cv2.circle(frame, (360, 215), 14, (40, 40, 40), -1)
    cv2.ellipse(frame, (320, 280), (40, 12), 0, 0, 180, (60, 60, 60), -1)
    cv2.circle(frame, (260, 250), 22, (220, 220, 220), -1)
    cv2.circle(frame, (380, 250), 22, (220, 220, 220), -1)
    return cv2.GaussianBlur(frame, (15, 15), 0)


# back-compat: tests/test_full_sim imports `render_preview`
def render_preview(frame_bgr, response_text, out_path):
    return save_receipt_png(frame_bgr, response_text, out_path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", default=os.path.join(
        os.path.dirname(__file__), "test_image.jpg"))
    p.add_argument("--text", default=(
        "Your eyes hold the weight of forgotten stars."))
    p.add_argument("--out", default=os.path.join(
        os.path.dirname(__file__), "printer_preview.png"))
    p.add_argument("--show", action="store_true",
                   help="open the preview in the default image viewer")
    p.add_argument("--booth", action="store_true",
                   help="render a photobooth strip preview instead")
    args = p.parse_args()

    if not os.path.exists(args.image):
        frame = _synth_face_frame()
        print(f"[PREVIEW] {args.image} missing — using a synthetic placeholder")
    else:
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"[PREVIEW] could not decode {args.image}")
            sys.exit(2)

    if args.booth:
        # build three slightly varied frames so the strip looks like a real
        # photobooth sequence (different poses)
        from printer import render_booth_pil
        import numpy as np
        variants = [frame]
        for shift in (35, -40):
            shifted = np.roll(frame, shift, axis=1).copy()
            variants.append(shifted)
        booth_out = args.out.replace(".png", "_booth.png")
        sample_prompts = [
            "Best regal pose",
            "Pretend you saw a ghost",
            "Fake-laugh at a joke",
        ]
        render_booth_pil(variants, label="PHOTOBOOTH",
                         prompts=sample_prompts,
                         qr_url="https://drive.google.com/drive/folders/PREVIEW"
                         ).save(booth_out)
        out = booth_out
    else:
        out = save_receipt_png(frame, args.text, args.out)
    from PIL import Image as PILImage
    print(f"[PREVIEW] wrote {out} ({config.PRINTER_WIDTH_DOTS}px wide, "
          f"{PILImage.open(out).height}px tall)")
    if args.show:
        try:
            PILImage.open(out).show()
        except Exception as e:
            print(f"[PREVIEW] could not open viewer: {e}")


if __name__ == "__main__":
    main()
