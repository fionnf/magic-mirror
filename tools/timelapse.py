"""End-of-night timelapse builder.

Downloads every mirror_*.jpg from GOOGLE_DRIVE_FOLDER_ID that was created
today (or on --date YYYY-MM-DD), sorts by timestamp, and stitches them into
an MP4 using OpenCV. The finished video is uploaded back to the same folder.

Requires ≥10 photos by default (override with --min). Skips if not enough
photos were taken — perfect for running as a cron job at the end of every
event night.

Usage:
    python tools/timelapse.py                   # today, real Drive
    python tools/timelapse.py --date 2025-07-04 # specific date
    python tools/timelapse.py --min 1 --fps 2   # dev/testing
    python tools/timelapse.py --out /tmp/tl.mp4 --no-upload
"""
import argparse
import datetime
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
import config


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_service():
    """Reuse cloud_uploader's credential loading rather than duplicating it."""
    from cloud_uploader import _get_service as _svc
    return _svc()


def _list_photos(svc, folder_id: str, date_str: str) -> list[dict]:
    """Return Drive file metadata for mirror_*.jpg on `date_str` (YYYY-MM-DD),
    sorted chronologically by file name (which encodes the timestamp)."""
    # createdTime filter: anything from midnight to midnight UTC on that day.
    day = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    start = day.strftime("%Y-%m-%dT00:00:00")
    end = (day + datetime.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")

    query = (
        f"'{folder_id}' in parents"
        f" and name contains 'mirror_'"
        f" and mimeType = 'image/jpeg'"
        f" and trashed = false"
        f" and createdTime >= '{start}'"
        f" and createdTime < '{end}'"
    )
    results = []
    page_token = None
    while True:
        resp = svc.files().list(
            q=query,
            fields="nextPageToken, files(id, name, createdTime)",
            orderBy="name",
            pageSize=200,
            pageToken=page_token,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def _download_jpeg(svc, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    request = svc.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def _build_video(photo_bytes_list: list[bytes], fps: float, out_path: str,
                 width: int = None, height: int = None) -> str:
    """Decode JPEG bytes, resize to a common canvas, write MP4 via OpenCV."""
    import cv2
    import numpy as np
    from PIL import Image

    # Determine canvas from first frame
    first = Image.open(io.BytesIO(photo_bytes_list[0])).convert("RGB")
    if width is None or height is None:
        # Normalise to 720px wide, maintain aspect
        w, h = first.size
        width = 720
        height = int(round(h * width / w))
        # ensure even for H.264
        width = width if width % 2 == 0 else width + 1
        height = height if height % 2 == 0 else height + 1

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open VideoWriter for {out_path}")

    for i, data in enumerate(photo_bytes_list):
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img = img.resize((width, height), Image.LANCZOS)
            frame = cv2.cvtColor(np.asarray(img, dtype=np.uint8),
                                 cv2.COLOR_RGB2BGR)
            writer.write(frame)
        except Exception as e:
            print(f"[TIMELAPSE] frame {i+1} skipped: {e}")

    writer.release()
    return out_path


def _upload_video(svc, folder_id: str, path: str, name: str,
                  description: str = "") -> str | None:
    from googleapiclient.http import MediaFileUpload
    metadata = {
        "name": name,
        "parents": [folder_id],
        "description": description,
    }
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True)
    try:
        f = svc.files().create(
            body=metadata, media_body=media, fields="id,webViewLink"
        ).execute()
        link = f.get("webViewLink", "")
        print(f"[TIMELAPSE] uploaded → {link}")
        return link
    except Exception as e:
        print(f"[TIMELAPSE] upload failed: {e}")
        return None


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default=datetime.date.today().isoformat(),
                   help="Date to pull photos from (YYYY-MM-DD). Default: today.")
    p.add_argument("--min", type=int, default=10, dest="min_photos",
                   help="Minimum photos required to build a timelapse (default 10).")
    p.add_argument("--fps", type=float, default=6.0,
                   help="Playback frame rate of the output video (default 6).")
    p.add_argument("--out", default=None,
                   help="Local output path for the MP4. Default: temp file.")
    p.add_argument("--no-upload", action="store_true",
                   help="Skip uploading the finished video to Drive.")
    p.add_argument("--keep", action="store_true",
                   help="Keep the local MP4 after uploading (default: delete it).")
    args = p.parse_args()

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        print("[TIMELAPSE] GOOGLE_DRIVE_FOLDER_ID not set — aborting.")
        sys.exit(1)

    svc = _get_service()
    if svc is None:
        print("[TIMELAPSE] Drive auth not available — aborting.")
        sys.exit(1)

    print(f"[TIMELAPSE] scanning folder for photos on {args.date} …")
    photos = _list_photos(svc, folder_id, args.date)
    print(f"[TIMELAPSE] found {len(photos)} photo(s)")

    if len(photos) < args.min_photos:
        print(f"[TIMELAPSE] fewer than {args.min_photos} photos "
              f"({len(photos)}) — skipping timelapse.")
        sys.exit(0)

    print("[TIMELAPSE] downloading frames …")
    photo_bytes = []
    for i, f in enumerate(photos):
        print(f"  [{i+1}/{len(photos)}] {f['name']}", end="\r", flush=True)
        try:
            data = _download_jpeg(svc, f["id"])
            photo_bytes.append(data)
        except Exception as e:
            print(f"\n[TIMELAPSE] download failed for {f['name']}: {e}")
    print(f"\n[TIMELAPSE] downloaded {len(photo_bytes)} frames")

    if len(photo_bytes) < args.min_photos:
        print("[TIMELAPSE] too many download failures — aborting.")
        sys.exit(1)

    # Build the video
    out_path = args.out
    tmp_file = None
    if out_path is None:
        tmp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        out_path = tmp_file.name
        tmp_file.close()

    print(f"[TIMELAPSE] stitching {len(photo_bytes)} frames @ {args.fps} fps → {out_path}")
    try:
        _build_video(photo_bytes, fps=args.fps, out_path=out_path)
    except Exception as e:
        print(f"[TIMELAPSE] video build failed: {e}")
        sys.exit(1)

    size_mb = os.path.getsize(out_path) / 1_048_576
    print(f"[TIMELAPSE] video ready — {size_mb:.1f} MB")

    if not args.no_upload:
        video_name = f"timelapse_{args.date}.mp4"
        desc = (f"Magic Mirror timelapse — {args.date} — "
                f"{len(photo_bytes)} frames @ {args.fps} fps")
        _upload_video(svc, folder_id, out_path, video_name, desc)

    # Clean up unless user asked to keep it
    if tmp_file is not None and not args.keep:
        try:
            os.unlink(out_path)
            print("[TIMELAPSE] local temp file removed")
        except Exception:
            pass
    elif args.keep or args.out:
        print(f"[TIMELAPSE] local file kept at {out_path}")


if __name__ == "__main__":
    main()
