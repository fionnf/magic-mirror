"""Local photo storage — receipts and booth strips saved to disk.

Photos are stored in PHOTOS_DIR as:
  receipt_YYYYMMDD_HHMMSS_ffffff.jpg   — raw camera frame
  receipt_YYYYMMDD_HHMMSS_ffffff.json  — {type, text, ts}
  strip_YYYYMMDD_HHMMSS_ffffff.jpg     — composed booth strip
  strip_YYYYMMDD_HHMMSS_ffffff.json    — {type, prompts, ts}

(ffffff = microseconds for uniqueness)
"""
import datetime
import io
import json
import os
from typing import Dict, List, Optional

import cv2
import numpy as np
from PIL import Image

import config

# Where the pictures live. Set WALL_PHOTOS_DIR in .env to keep them on a USB stick or SSD (mount it, e.g. at /mnt/photos).
PHOTOS_DIR = os.environ.get("WALL_PHOTOS_DIR") or os.path.join(os.path.dirname(__file__), "photos")
MIN_FREE = 400 * 1024 * 1024          # below this much free space new photos are not saved (the wall must never fill its card)


def disk_info() -> Dict:
    """{'dir', 'photos', 'bytes', 'free', 'total', 'low'}: what the pictures take, and what is left on the disk they are on."""
    d = PHOTOS_DIR
    n = size = 0
    try:
        for f in os.scandir(d):
            if f.name.endswith(".jpg") and not f.name.endswith(("_thumb.jpg", "_frame.jpg")) and "_shot" not in f.name and not f.name.startswith("strip_"):
                n += 1
            if f.is_file():
                size += f.stat().st_size
    except OSError:
        pass
    try:
        st = os.statvfs(d if os.path.isdir(d) else os.path.dirname(d))
        free, total = st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize
    except OSError:
        free = total = 0
    return {"dir": d, "photos": n, "bytes": size, "free": free, "total": total, "low": free < 3 * MIN_FREE}


def _room_for_more() -> bool:
    free = disk_info()["free"]
    if free and free < MIN_FREE:
        print(f"[PHOTOS] disk almost full ({free // 1048576} MB free): not saving this picture. Free space or set WALL_PHOTOS_DIR to a USB stick.", flush=True)
        return False
    return True


def _dir() -> str:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    return PHOTOS_DIR


def _save_full(frame: np.ndarray, path: str) -> None:
    """The picture at its full resolution: JPEG at config.PHOTO_JPEG_QUALITY, no chroma subsampling."""
    if not _room_for_more():
        return
    Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(
        path, format="JPEG", quality=getattr(config, "PHOTO_JPEG_QUALITY", 95), subsampling=0, optimize=True)


def _save_thumb(frame: np.ndarray, path: str, side: int = 640) -> None:
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    img.thumbnail((side, side))
    img.save(path, format="JPEG", quality=82)


def save_receipt(frame: np.ndarray, text: str) -> str:
    """Save a single-trigger capture. Returns the base filename stem."""
    d   = _dir()
    ts  = datetime.datetime.now()
    stem = ts.strftime("receipt_%Y%m%d_%H%M%S_%f")
    _save_full(frame, os.path.join(d, f"{stem}.jpg"))                       # the picture as the camera took it, full resolution
    _save_thumb(frame, os.path.join(d, f"{stem}_thumb.jpg"))               # a small copy for the app's grid
    with open(os.path.join(d, f"{stem}.json"), "w") as f:
        json.dump({"type": "receipt", "text": text, "ts": ts.isoformat()}, f)
    print(f"[PHOTOS] saved {stem}.jpg")
    return stem


def save_strip(strip_image: Image.Image, frames: List[np.ndarray],
               prompts: List[str]) -> str:
    """Save a photobooth strip. Returns the base filename stem."""
    d    = _dir()
    ts   = datetime.datetime.now()
    stem = ts.strftime("strip_%Y%m%d_%H%M%S_%f")
    strip_image.save(os.path.join(d, f"{stem}.jpg"), format="JPEG", quality=90)
    # every shot at full resolution (the strip itself is only the print layout), and a small cover for the app's grid
    for i, fr in enumerate(frames):
        _save_full(fr, os.path.join(d, f"{stem}_shot{i + 1}.jpg"))
    if frames:
        _save_thumb(frames[0], os.path.join(d, f"{stem}_frame.jpg"))
    with open(os.path.join(d, f"{stem}.json"), "w") as f:
        json.dump({"type": "strip", "prompts": prompts, "ts": ts.isoformat()}, f)
    print(f"[PHOTOS] saved {stem}.jpg")
    return stem


def list_recent(hours: int = 24) -> List[Dict]:
    """Return photos from the last N hours, newest first."""
    d = PHOTOS_DIR
    if not os.path.exists(d):
        return []
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
    out = []
    for fname in os.listdir(d):
        if not fname.endswith(".json"):
            continue
        stem = fname[:-5]
        try:
            with open(os.path.join(d, fname)) as f:
                meta = json.load(f)
            ts = datetime.datetime.fromisoformat(meta["ts"])
            if ts < cutoff:
                continue
            img_path = os.path.join(d, f"{stem}.jpg")
            if not os.path.exists(img_path):
                continue
            entry = {
                "id":      stem,
                "type":    meta.get("type", "receipt"),
                "text":    meta.get("text", ""),
                "prompts": meta.get("prompts", []),
                "ts":      meta["ts"],
                "url":     f"/photos/{stem}.jpg",
            }
            if "drive_id" in meta:
                entry["drive_url"] = (
                    f"https://drive.google.com/uc?export=view&id={meta['drive_id']}"
                )
            out.append(entry)
        except Exception:
            pass
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out


def set_drive_id(stem: str, drive_id: str) -> None:
    """Persist a Drive file ID into the sidecar JSON after async upload."""
    path = os.path.join(PHOTOS_DIR, f"{stem}.json")
    if not os.path.exists(path):
        return
    try:
        with open(path) as f:
            meta = json.load(f)
        meta["drive_id"] = drive_id
        with open(path, "w") as f:
            json.dump(meta, f)
    except Exception as e:
        print(f"[PHOTOS] set_drive_id failed for {stem}: {e}")


def get_meta(stem: str) -> Optional[Dict]:
    path = os.path.join(PHOTOS_DIR, f"{stem}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def get_image_path(stem: str) -> Optional[str]:
    path = os.path.join(PHOTOS_DIR, f"{stem}.jpg")
    return path if os.path.exists(path) else None
