"""Local photo storage — receipts and booth strips saved to disk.

Photos are stored in PHOTOS_DIR as:
  receipt_YYYYMMDD_HHMMSS.jpg   — raw camera frame
  receipt_YYYYMMDD_HHMMSS.json  — {type, text, ts}
  strip_YYYYMMDD_HHMMSS.jpg     — composed booth strip
  strip_YYYYMMDD_HHMMSS.json    — {type, prompts, ts}
"""
import datetime
import io
import json
import os
from typing import Dict, List, Optional

import cv2
import numpy as np
from PIL import Image

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "photos")


def _dir() -> str:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    return PHOTOS_DIR


def save_receipt(frame: np.ndarray, text: str) -> str:
    """Save a single-trigger capture. Returns the base filename stem."""
    d   = _dir()
    ts  = datetime.datetime.now()
    stem = ts.strftime("receipt_%Y%m%d_%H%M%S")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    img.thumbnail((1024, 1024))
    img.save(os.path.join(d, f"{stem}.jpg"), format="JPEG", quality=85)
    with open(os.path.join(d, f"{stem}.json"), "w") as f:
        json.dump({"type": "receipt", "text": text, "ts": ts.isoformat()}, f)
    print(f"[PHOTOS] saved {stem}.jpg")
    return stem


def save_strip(strip_image: Image.Image, frames: List[np.ndarray],
               prompts: List[str]) -> str:
    """Save a photobooth strip. Returns the base filename stem."""
    d    = _dir()
    ts   = datetime.datetime.now()
    stem = ts.strftime("strip_%Y%m%d_%H%M%S")
    strip_image.save(os.path.join(d, f"{stem}.jpg"), format="JPEG", quality=90)
    # save representative frame for reprinting
    if frames:
        rgb = cv2.cvtColor(frames[0], cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail((1024, 1024))
        img.save(os.path.join(d, f"{stem}_frame.jpg"), format="JPEG", quality=85)
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
