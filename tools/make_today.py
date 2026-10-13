#!/usr/bin/env python3
"""The cloud artist: make today's piece without the wall (GitHub Actions, .github/workflows/daily.yml).

    xvfb-run -a python3 tools/make_today.py            # today, if gallery/ has no piece for it yet
    xvfb-run -a python3 tools/make_today.py 2026-10-12 # one date

Runs the same pipeline the wall runs at 05:00 (Claude composes, the shader check, the Claude curator)
on a software GPU, writes the edition to assets/daily/ and its public files to gallery/, and closes
the day before if the wall never did (a post written from the still; the room's listening is only
known to the wall). The workflow commits the result; the wall fetches the piece from the gallery
instead of making its own. Needs ANTHROPIC_API_KEY.
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
GALLERY = os.path.join(ROOT, "gallery")


def to_gallery(date):
    from display import publish
    for path, data in publish.files_for(date).items():
        with open(os.path.join(ROOT, path), "wb") as fh:
            fh.write(data)


def close(date):
    """A day the wall did not finalise: mark it final with a post, without listening data."""
    from display import daily
    p = os.path.join(GALLERY, f"{date}.json")
    if not os.path.exists(p):
        return False
    with open(p) as fh:
        meta = json.load(fh)
    if meta.get("final"):
        return False
    if not os.path.exists(daily._path(date, "json")):
        daily.fetch(date)
    try:
        meta["post"] = daily.write_post(meta, daily.load_memory(date), daily._path(date, "png"),
                                        note="not recorded (the wall was offline that day); write about the piece itself")
    except Exception as e:
        print(f"[daily] post writer unavailable: {e}", flush=True)
    try:                                       # the closing picture, as the wall would have made it
        import numpy as np
        from PIL import Image
        from display import shaders
        r = shaders.renderer()
        if r.ok:
            img = r.render("path:" + daily._path(date, "frag"), 3600.0, {"level": 0.1, "clock": 23.95},
                           [daily._hex(c) for c in meta["palette"]])
            big = Image.fromarray(img.astype(np.uint8)).resize((daily.W * 3, daily.H * 3), Image.NEAREST)
            for folder in (GALLERY, daily.FOLDER):
                big.save(os.path.join(folder, f"{date}.final.png"))
            meta["image"] = f"{date}.final.png"
    except Exception as e:
        print(f"[daily] closing picture unavailable: {e}", flush=True)
    meta["final"] = True
    meta["closed_by"] = "cloud"
    for path in (p, daily._path(date, "json")):
        with open(path, "w") as fh:
            json.dump(meta, fh, indent=1)
    print(f"[daily] closed {date} without the wall", flush=True)
    return True


def main():
    from display import daily
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    changed = False
    if not os.path.exists(os.path.join(GALLERY, f"{date}.json")):
        if not os.path.exists(daily._path(date, "json")):
            meta = daily.generate(date)
            print(f"[daily] {date}: {meta['name']!r} ({meta['attempts']} attempts, "
                  f"curator {meta['curator']['score']}/10)", flush=True)
        to_gallery(date)
        changed = True
    else:
        print(f"[daily] {date}: already in the gallery", flush=True)
    yesterday = (datetime.date.fromisoformat(date) - datetime.timedelta(days=1)).isoformat()
    changed = close(yesterday) or changed
    print("changed" if changed else "nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
