"""Per-panel colour calibration using a webcam. Runs on the LAPTOP.

It starts colour_server.py on the Pi over SSH, shows solid red / green / blue /
white / grey on the whole wall, photographs each, finds the lit 3x3 block in
the image, measures every panel, and writes per-panel per-channel gains to
panel_setup/colour_calibration.json (loaded automatically by led_matrix.py).

    python3 panel_setup/calibrate_colour.py                 # measure + write
    python3 panel_setup/calibrate_colour.py --dry-run       # measure only
    python3 panel_setup/calibrate_colour.py --brightness-match

Needs: pip install opencv-python numpy   (and ffmpeg on macOS)

Setup: aim the camera square-on at the wall, as far back as still fills a good
part of the frame, keep people out of shot and room lighting constant.

How the gains are chosen
  * Chroma mode (default): each panel's R:G:B response shares are matched to the
    median panel. This is immune to camera vignetting / viewing angle, because
    those scale all three channels of a panel equally.
  * --brightness-match also scales every panel to the dimmest one. That DOES
    include camera falloff, so check the brightness map before trusting it.
  Gains are <= 1 (we can only dim), applied in 8-bit value space; webcam pixel
  values are gamma-encoded just like the panel's value scale, so the ratios
  carry over to mid-tones approximately (the grey check shows how well).
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import config  # noqa: E402

CELL = 120          # px per panel in the rectified image
CENTRE = 0.5        # fraction of each cell (centred) used for measurement
CH = ["R", "G", "B"]


# ------------------------------------------------------------------ camera --

def grab(camera, warm=25, avg=20, w=1280, h=720):
    """Photograph the wall: discard `warm` frames (auto-exposure settling), then
    AVERAGE `avg` frames. Panel refresh beats against the camera's shutter and
    paints dark bands that drift from frame to frame; averaging washes them out."""
    cmd = ["ffmpeg", "-loglevel", "error", "-f", "avfoundation",
           "-pixel_format", "nv12", "-framerate", "30", "-video_size", f"{w}x{h}",
           "-i", camera, "-frames:v", str(warm + avg), "-pix_fmt", "bgr24",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, stdout=subprocess.PIPE).stdout
    n = len(raw) // (w * h * 3)
    if n < warm + 1:
        raise RuntimeError("camera capture failed")
    frames = np.frombuffer(raw[:n * w * h * 3], np.uint8).reshape(n, h, w, 3)
    return frames[warm:].astype(np.float32).mean(0)


# --------------------------------------------------------------- Pi server --

class Wall:
    def __init__(self, user, host):
        self.p = subprocess.Popen(
            ["ssh", "-o", "BatchMode=yes", f"{user}@{host}",
             "cd ~/magic-mirror && sudo python3 panel_setup/colour_server.py"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("colour_server did not start (is the Pi up?)")
            if line.strip() == "ready":
                break
            print("[PI]", line.rstrip(), file=sys.stderr)

    def cmd(self, text):
        self.p.stdin.write(text + "\n")
        self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("lost connection to colour_server on the Pi "
                                   f"(exit {self.p.poll()})")
            if line.strip() == "ok":
                return
            print("[PI]", line.rstrip(), file=sys.stderr)

    def fill(self, r, g, b, settle=0.7):
        self.cmd(f"fill {r} {g} {b}")
        time.sleep(settle)

    def close(self):
        try:
            self.cmd("quit")
        except Exception:
            pass
        try:
            self.p.wait(timeout=8)
        except Exception:
            self.p.kill()


# --------------------------------------------------------------- geometry ---

def order_corners(pts):
    pts = np.array(pts, dtype=np.float32).reshape(-1, 2)
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)  # tl tr br bl


def _norm_gray(img):
    g = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    return g / max(float(np.median(g)), 1.0)      # cancel auto-exposure differences


def locate(white, black):
    """Find the lit block's 4 corners in the camera image."""
    diff = np.clip(_norm_gray(white) - _norm_gray(black), 0, None)
    diff = cv2.GaussianBlur(diff, (11, 11), 0)
    d8 = np.clip(diff / max(diff.max(), 1e-3) * 255, 0, 255).astype(np.uint8)
    _, th = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        raise RuntimeError("could not find the lit wall - is the camera aimed at it?")
    c = max(cnts, key=cv2.contourArea)
    hull = cv2.convexHull(c)
    peri = cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, 0.02 * peri, True)
    quad = approx if len(approx) == 4 else cv2.boxPoints(cv2.minAreaRect(hull))
    return order_corners(quad)


def rectify(img, corners):
    w, h = config.PANELS_WIDE * CELL, config.PANELS_TALL * CELL
    M = cv2.getPerspectiveTransform(
        corners, np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32))
    return cv2.warpPerspective(img.astype(np.float32), M, (w, h), flags=cv2.INTER_AREA)


def measure(img, corners):
    """-> (chain, 3) mean R,G,B per panel (0-255) and clipped-pixel fraction."""
    rect = rectify(img, corners)
    out = np.zeros((config.CHAIN_LENGTH, 3))
    clip = 0.0
    m = int(CELL * (1 - CENTRE) / 2)
    for k, (col, row) in enumerate(config.PANEL_CHAIN_ORDER):
        cell = rect[row * CELL + m:(row + 1) * CELL - m, col * CELL + m:(col + 1) * CELL - m]
        out[k] = cell.reshape(-1, 3).mean(0)[::-1]          # BGR -> RGB
        clip = max(clip, float((cell.max(axis=2) >= 245).mean()))
    return out, clip


def capture_set(wall, camera, corners, dark, level, grey=128, shots=1):
    """Measure R, G, B, W, grey patterns. Returns dict name -> (chain,3) minus dark."""
    pats = {"R": (level, 0, 0), "G": (0, level, 0), "B": (0, 0, level),
            "W": (level, level, level), "grey": (grey, grey, grey)}
    res, worst_clip = {}, 0.0
    for name, rgb in pats.items():
        wall.fill(*rgb)
        acc = []
        for _ in range(shots):
            m, clip = measure(grab(camera), corners)
            acc.append(m)
            worst_clip = max(worst_clip, clip)
        res[name] = np.clip(np.mean(acc, axis=0) - dark, 1e-3, None)
    return res, worst_clip


# ------------------------------------------------------------------ maths ---

def shares(res):
    """(chain,3): each panel's measured response to its OWN primary, as shares."""
    prim = np.stack([res["R"][:, 0], res["G"][:, 1], res["B"][:, 2]], axis=1)
    return prim / prim.sum(1, keepdims=True), prim


def compute_gains(res, brightness_match):
    sh, prim = shares(res)
    target = np.median(sh, axis=0)
    g = target[None, :] / sh
    g /= g.max(1, keepdims=True)                           # <= 1, one channel at 1
    if brightness_match:
        lum = (g * prim).sum(1)
        g *= (lum.min() / lum)[:, None]
    return np.clip(g, 0.0, 1.0)


def spread(res, label):
    sh, prim = shares(res)
    lum = prim.sum(1)
    dev = (sh - np.median(sh, axis=0)) * 100              # percentage points
    grey_sh = res["grey"] / res["grey"].sum(1, keepdims=True)
    gdev = (grey_sh - np.median(grey_sh, axis=0)) * 100
    print(f"  {label:<8} colour spread max |dev| R/G/B share: "
          f"{np.abs(dev[:, 0]).max():.1f} / {np.abs(dev[:, 1]).max():.1f} / "
          f"{np.abs(dev[:, 2]).max():.1f} pts | grey: {np.abs(gdev).max():.1f} pts | "
          f"brightness std {100 * lum.std() / lum.mean():.1f}%")
    return np.abs(dev).max(), np.abs(gdev).max(), 100 * lum.std() / lum.mean()


def grid(values, fmt="{:6.1f}"):
    """Print a per-chain-index vector arranged as the physical wall."""
    cells = {}
    for k, (c, r) in enumerate(config.PANEL_CHAIN_ORDER):
        cells[(c, r)] = values[k]
    for r in range(config.PANELS_TALL):
        print("   " + "  ".join(fmt.format(cells[(c, r)]) for c in range(config.PANELS_WIDE)))


# ------------------------------------------------------------------- main ---

def correction(res, gains_now, damp):
    """One damped correction step from a measurement taken WITH gains_now applied."""
    sh, _ = shares(res)
    target = np.median(sh, axis=0)
    g = gains_now * (target[None, :] / sh) ** damp
    return np.clip(g / g.max(1, keepdims=True), 0.0, 1.0)


def score(res):
    """Worst colour / grey share deviation (percentage points) - lower is better."""
    sh, _ = shares(res)
    grey = res["grey"] / res["grey"].sum(1, keepdims=True)
    return max(np.abs((sh - np.median(sh, 0)) * 100).max(),
               np.abs((grey - np.median(grey, 0)) * 100).max())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="192.168.1.207")
    ap.add_argument("--user", default="pi")
    ap.add_argument("--camera", default="FaceTime HD Camera")
    ap.add_argument("--level", type=int, default=125,
                    help="drive level 0-255 for the measurement (lower if the camera clips)")
    ap.add_argument("--iterations", type=int, default=3,
                    help="correction rounds; each is measured and only kept if it improves")
    ap.add_argument("--damp", type=float, default=0.6,
                    help="fraction of the measured error corrected per round (0-1)")
    ap.add_argument("--brightness-match", action="store_true",
                    help="finally also scale panels to the dimmest (includes camera falloff!)")
    ap.add_argument("--dry-run", action="store_true", help="measure only, don't write")
    ap.add_argument("--out", default=os.path.join(HERE, "colour_calibration.json"))
    ap.add_argument("--report-dir", default=os.path.join(HERE, "calibration_report"))
    a = ap.parse_args()
    os.makedirs(a.report_dir, exist_ok=True)

    def save(gains, path):
        data = {"created": datetime.datetime.now().isoformat(timespec="seconds"),
                "mode": "chroma", "level": a.level,
                "chain_order": [list(p) for p in config.PANEL_CHAIN_ORDER],
                "gains": np.round(gains, 4).tolist()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def push():
        subprocess.run(["rsync", "-q", a.out, f"{a.user}@{a.host}:magic-mirror/panel_setup/"],
                       check=True)
        wall.cmd("reload")

    wall = Wall(a.user, a.host)
    try:
        print("[CAL] locating the wall ...")
        wall.fill(0, 0, 0, settle=1.0)
        black = grab(a.camera)
        wall.fill(120, 120, 120)
        white = grab(a.camera)
        corners = locate(white, black)
        cv2.imwrite(os.path.join(a.report_dir, "located.jpg"),
                    cv2.polylines(white.astype(np.uint8).copy(), [corners.astype(np.int32)],
                                  True, (0, 255, 0), 3))
        dark, _ = measure(black, corners)

        print(f"[CAL] measuring raw panels at level {a.level} ...")
        raw, clip = capture_set(wall, a.camera, corners, dark, a.level)
        if clip > 0.05:
            print(f"[CAL] WARNING: camera is clipping ({100 * clip:.0f}% of pixels) - "
                  f"rerun with a lower --level (e.g. {int(a.level * 0.7)})")
        print("[CAL] panel brightness map (camera units, includes camera falloff):")
        grid(raw["W"].mean(1))
        print("[CAL] raw panels")
        spread(raw, "raw")
        if a.dry_run:
            print("[CAL] dry run - nothing written")
            return

        best_gains, best_res, best_score = np.ones((config.CHAIN_LENGTH, 3)), raw, score(raw)
        cur_gains, cur_res = best_gains.copy(), raw
        for i in range(1, a.iterations + 1):
            cur_gains = correction(cur_res, cur_gains, a.damp)
            save(cur_gains, a.out)
            push()
            cur_res, _ = capture_set(wall, a.camera, corners, dark, a.level)
            sc = score(cur_res)
            print(f"[CAL] round {i}:")
            spread(cur_res, f"round {i}")
            if sc < best_score - 0.1:
                best_gains, best_res, best_score = cur_gains.copy(), cur_res, sc
            else:
                print("[CAL] no improvement - stopping")
                break

        if a.brightness_match and best_score < score(raw):
            sh, prim = shares(best_res)
            lum = prim.sum(1)
            best_gains = best_gains * (lum.min() / lum)[:, None]

        if best_score >= score(raw) - 0.1:
            print("[CAL] calibration did not beat the uncalibrated panels - keeping none")
            if os.path.exists(a.out):
                os.remove(a.out)
            subprocess.run(["ssh", "-o", "BatchMode=yes", f"{a.user}@{a.host}",
                            "rm -f ~/magic-mirror/panel_setup/colour_calibration.json"], check=True)
            return
        save(best_gains, a.out)
        push()
        print("[CAL] gains (R,G,B) per panel, laid out as the wall:")
        for r in range(config.PANELS_TALL):
            print("   " + "   ".join(
                "(%.2f %.2f %.2f)" % tuple(best_gains[config.PANEL_CHAIN_ORDER.index((c, r))])
                for c in range(config.PANELS_WIDE)))
        print(f"[CAL] worst deviation {score(raw):.1f} -> {best_score:.1f} pts; "
              f"wrote {os.path.relpath(a.out, ROOT)}")
    finally:
        wall.close()


if __name__ == "__main__":
    main()
