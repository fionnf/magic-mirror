"""Test Claude vision API with a single image."""
import argparse
import os
import sys
import time
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import ai_client
import config


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", default=os.path.join(os.path.dirname(__file__), "test_image.jpg"))
    args = p.parse_args()

    if not os.path.exists(args.image):
        print(f"[AI TEST] image not found: {args.image}")
        sys.exit(2)

    frame = cv2.imread(args.image)
    if frame is None:
        print(f"[AI TEST] could not decode: {args.image}")
        sys.exit(2)

    print("[AI TEST] Sending image to Claude...")
    t0 = time.monotonic()
    text = ai_client.get_mirror_message(frame)
    elapsed = time.monotonic() - t0
    print(f"[AI TEST] Response ({elapsed:.2f}s): {text!r}")
    print(f"[AI TEST] Logged to {config.USAGE_LOG}")


if __name__ == "__main__":
    main()
