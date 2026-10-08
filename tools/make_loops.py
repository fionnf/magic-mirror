#!/usr/bin/env python3
"""Turn VJ loop videos into Pi-friendly 192x192 clips + an index the wall can pick from.

    python3 tools/make_loops.py ~/Movies/"VJ Loops"            # every video under that folder
    python3 tools/make_loops.py pack1/ pack2/ --out assets/loops

Each clip becomes assets/loops/<pack>__<name>.mp4 (192x192, 29 fps, H.264, no audio, ~0.3-1 MB)
and assets/loops/index.json records frames, fps, duration and two measured numbers:
  motion  mean frame-to-frame change (0..1)  -> calm clips for a quiet room, wild ones for a party
  bright  mean brightness (0..1)
Needs ffmpeg on this machine. Re-run any time: existing outputs are skipped.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = (".mov", ".mp4", ".avi", ".mkv", ".m4v", ".webm", ".mpg", ".mpeg", ".wmv")
SIZE, FPS = 192, 29


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def convert(src, dst):
    vf = (f"scale={SIZE}:{SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={SIZE}:{SIZE},fps={FPS},format=yuv420p")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vf", vf, "-an",
           "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-movflags", "+faststart", dst]
    return subprocess.run(cmd, capture_output=True, text=True)


def measure(path):
    import cv2
    cap = cv2.VideoCapture(path)
    prev, motion, bright, n = None, [], [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(fr, (48, 48)), cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        bright.append(float(g.mean()))
        if prev is not None:
            motion.append(float(np.abs(g - prev).mean()))
        prev = g
        n += 1
    cap.release()
    return n, float(np.mean(motion) * 4) if motion else 0.0, float(np.mean(bright)) if bright else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--out", default=os.path.join(HERE, "assets", "loops"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    index_path = os.path.join(a.out, "index.json")
    index = {}
    if os.path.exists(index_path):
        index = json.load(open(index_path))
    jobs = []
    for folder in a.folders:
        folder = os.path.abspath(os.path.expanduser(folder))
        for root, _, files in os.walk(folder):
            if "__MACOSX" in root:
                continue
            for fn in sorted(files):
                if fn.lower().endswith(EXT) and not fn.startswith("."):
                    pack = slug(os.path.basename(folder) if root == folder else os.path.basename(root))
                    name = f"{pack}__{slug(os.path.splitext(fn)[0])}"
                    jobs.append((os.path.join(root, fn), name))
    print(f"{len(jobs)} videos")
    for i, (src, name) in enumerate(jobs, 1):
        dst = os.path.join(a.out, name + ".mp4")
        if name in index and os.path.exists(dst):
            continue
        r = convert(src, dst)
        if r.returncode != 0 or not os.path.exists(dst):
            print(f"  !! {name}: {r.stderr.strip()[:120]}")
            continue
        n, motion, bright = measure(dst)
        if n < FPS:                                     # under a second: not a loop
            os.remove(dst)
            print(f"  -- {name}: too short")
            continue
        index[name] = {"frames": n, "fps": FPS, "seconds": round(n / FPS, 2),
                       "motion": round(min(1.0, motion), 3), "bright": round(bright, 3),
                       "kb": os.path.getsize(dst) // 1024, "source": os.path.basename(src)}
        print(f"  {i:3d}/{len(jobs)} {name}: {n} frames, motion {motion:.2f}, bright {bright:.2f}, {index[name]['kb']} KB")
        json.dump(index, open(index_path, "w"), indent=1)
    json.dump(index, open(index_path, "w"), indent=1)
    total = sum(v["kb"] for v in index.values()) // 1024
    print(f"index: {len(index)} clips, {total} MB in {a.out}")


if __name__ == "__main__":
    sys.exit(main())
