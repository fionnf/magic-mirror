"""Live webcam silhouette test."""
import os
import sys
import time
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from simulator.camera_mock import CameraMock


def main():
    cam = CameraMock(mode="webcam")
    print("[SIL TEST] capturing background — step out of frame")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1.0)
    bg = cam.get_background_frame()
    print("[SIL TEST] background captured. Press S to save snapshot, Q to quit.")

    while True:
        frame = cam.capture_frame()
        mask_small = cam.extract_silhouette(frame, bg)
        # display: left = frame with contours; right = mask scaled back up
        contours, _ = cv2.findContours(mask_small, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        big_mask = cv2.resize(mask_small,
                              (config.TOTAL_WIDTH * 4, config.TOTAL_HEIGHT * 4),
                              interpolation=cv2.INTER_NEAREST)
        big_mask_rgb = cv2.cvtColor(big_mask, cv2.COLOR_GRAY2BGR)
        left = frame.copy()
        # scale contours back to frame size for overlay
        sx = frame.shape[1] / config.TOTAL_WIDTH
        sy = frame.shape[0] / config.TOTAL_HEIGHT
        for c in contours:
            scaled = (c * np.array([[sx, sy]])).astype(np.int32)
            cv2.drawContours(left, [scaled], -1, (0, 255, 0), 2)
        # resize panes to same height
        h = 480
        left_r = cv2.resize(left, (int(left.shape[1] * h / left.shape[0]), h))
        right_r = cv2.resize(big_mask_rgb, (int(big_mask_rgb.shape[1] * h / big_mask_rgb.shape[0]), h))
        combined = np.hstack([left_r, right_r])
        cv2.imshow("silhouette test (Q=quit S=save)", combined)
        on_pixels = int((mask_small > 127).sum())
        print(f"[SIL TEST] silhouette pixels: {on_pixels}", end="\r")

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            out = os.path.join(os.path.dirname(__file__), "silhouette_test_output.jpg")
            cv2.imwrite(out, combined)
            print(f"\n[SIL TEST] saved {out}")

    cam.shutdown()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
