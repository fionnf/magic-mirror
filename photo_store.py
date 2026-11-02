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
    reg = _load_reg()
    return {"dir": d, "photos": n, "bytes": size, "free": free, "total": total, "low": free < 3 * MIN_FREE,
            "budget": budget_bytes(), "backed_up": sum(1 for v in reg.values() if v.get("drive")),
            "shrunk": sum(1 for v in reg.values() if v.get("shrunk"))}


# ---- the budget: how much the pictures may take on the wall, and what is allowed to shrink ----------------------------------
# Drive keeps the originals. When the pictures on the wall exceed the budget (the "photos_gb" setting, default 1 GB), the oldest ones that
# Drive has CONFIRMED are replaced in place by a small copy (640 px), so the app and the slideshow still show them. Nothing that is not
# safely in Drive is ever touched. Strips (the small print layouts) and the sidecar files are never shrunk.
import threading

_reg_lock = threading.Lock()
SMALL_SIDE = 640


def _reg_path() -> str:
    return os.path.join(PHOTOS_DIR, ".backed_up.json")


def _load_reg() -> Dict:
    try:
        with open(_reg_path()) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_reg(reg: Dict) -> None:
    tmp = _reg_path() + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(reg, fh)
    os.replace(tmp, _reg_path())


def mark_backed_up(name: str, drive_id: str) -> None:
    """Record that Drive has this file (called by cloud_uploader after a successful upload), then see whether the budget needs tidying."""
    if not name or not drive_id:
        return
    with _reg_lock:
        reg = _load_reg()
        reg.setdefault(name, {})["drive"] = drive_id
        _save_reg(reg)
    prune_async()


def budget_bytes() -> int:
    gb = None
    try:
        import mirror_settings
        gb = mirror_settings.load().get("photos_gb")
    except Exception:
        pass
    if gb is None:
        gb = os.environ.get("WALL_PHOTOS_MAX_GB", 1)
    try:
        return int(float(gb) * 1024 ** 3)
    except (TypeError, ValueError):
        return 1024 ** 3


def _dir_bytes() -> int:
    total = 0
    try:
        for f in os.scandir(PHOTOS_DIR):
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass
    return total


def shrink(path: str, side: int = SMALL_SIDE) -> int:
    """Replace a picture by a small copy of itself, in place; returns the bytes saved."""
    before = os.path.getsize(path)
    st = os.stat(path)
    im = Image.open(path)
    im.draft("RGB", (side * 2, side * 2))
    im = im.convert("RGB")
    im.thumbnail((side, side), Image.LANCZOS)
    tmp = path + ".tmp.jpg"
    im.save(tmp, format="JPEG", quality=82)
    os.replace(tmp, path)
    try:
        os.utime(path, (st.st_atime, st.st_mtime))             # keep the picture's date: the gallery sorts by it
    except OSError:
        pass
    return max(0, before - os.path.getsize(path))


def prune() -> int:
    """Over budget? Shrink the oldest pictures that Drive has confirmed until it fits. Returns how many were shrunk."""
    budget = budget_bytes()
    total = _dir_bytes()
    if total <= budget:
        return 0
    done = 0
    with _reg_lock:
        reg = _load_reg()
        cands = [n for n, v in reg.items() if v.get("drive") and not v.get("shrunk") and n.endswith(".jpg")
                 and not (n.startswith("strip_") and "_shot" not in n) and os.path.exists(os.path.join(PHOTOS_DIR, n))]
        cands.sort(key=lambda n: os.path.getmtime(os.path.join(PHOTOS_DIR, n)))
        for n in cands:
            if total <= budget:
                break
            try:
                total -= shrink(os.path.join(PHOTOS_DIR, n))
                reg[n]["shrunk"] = True
                done += 1
            except Exception as e:
                print(f"[PHOTOS] could not shrink {n}: {e}", flush=True)
        _save_reg(reg)
    if done:
        print(f"[PHOTOS] over the {budget // 1048576} MB budget: shrank {done} backed-up picture(s) to small copies (originals are in Drive)", flush=True)
    return done


def prune_async() -> None:
    threading.Thread(target=lambda: _safe(prune), daemon=True, name="photo-prune").start()


def _safe(fn):
    try:
        fn()
    except Exception as e:
        print(f"[PHOTOS] prune failed: {e}", flush=True)


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
