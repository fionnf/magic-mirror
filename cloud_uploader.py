"""Async Google Drive uploader.

Auth modes (tried in order)
---------------------------
1. OAuth user token  — GOOGLE_OAUTH_TOKEN_PATH  (token.json)
2. Service account   — GOOGLE_CREDENTIALS_PATH  (gcp-credentials.json)

If no auth file is found every upload call returns silently.
The target Drive folder is read from the GOOGLE_DRIVE_FOLDER_ID env var;
leave it unset to disable uploads while keeping the rest of the app running.

All uploads are fire-and-forget: each public function submits work to a small
thread pool and returns immediately.  create_booth_session_folder() is the
only blocking call (main needs the folder ID before the first shot).
"""
import concurrent.futures
import datetime
import io
import os
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image

import config

_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="drive-upload")

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _build_service():
    """Return an authenticated Drive v3 service, or None."""
    creds = None

    # 1 — OAuth user token (generated once by tools/auth_drive.py)
    if os.path.exists(config.GOOGLE_OAUTH_TOKEN_PATH):
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(
                config.GOOGLE_OAUTH_TOKEN_PATH, _SCOPES)
        except Exception as e:
            print(f"[DRIVE] OAuth token load failed: {e}")

    # 2 — Service account key JSON
    if creds is None and os.path.exists(config.GOOGLE_CREDENTIALS_PATH):
        try:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                config.GOOGLE_CREDENTIALS_PATH, scopes=_SCOPES)
        except Exception as e:
            print(f"[DRIVE] service account load failed: {e}")

    if creds is None:
        return None

    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _parent_folder_id() -> Optional[str]:
    return os.environ.get("GOOGLE_DRIVE_FOLDER_ID") or None


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

def _frame_to_jpeg_bytes(frame: np.ndarray) -> bytes:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _pil_to_jpeg_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _upload_jpeg(service, name: str, jpeg_bytes: bytes,
                 parent_id: Optional[str], description: str = "",
                 make_public: bool = False) -> Optional[str]:
    """Upload JPEG bytes to Drive, optionally make public, return the file ID."""
    from googleapiclient.http import MediaIoBaseUpload
    meta = {"name": name, "description": description}
    if parent_id:
        meta["parents"] = [parent_id]
    media = MediaIoBaseUpload(io.BytesIO(jpeg_bytes), mimetype="image/jpeg")
    f = service.files().create(body=meta, media_body=media,
                               fields="id").execute()
    fid = f.get("id")
    if fid and make_public:
        service.permissions().create(
            fileId=fid,
            body={"role": "reader", "type": "anyone"},
        ).execute()
    return fid


# ---------------------------------------------------------------------------
# Sync workers (run inside the thread pool)
# ---------------------------------------------------------------------------

def _do_upload(frame: np.ndarray, text: str,
               stem: Optional[str] = None) -> None:
    service = _build_service()
    if service is None:
        return
    folder_id = _parent_folder_id()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fid = _upload_jpeg(service, f"mirror_{ts}.jpg",
                       _frame_to_jpeg_bytes(frame), folder_id,
                       description=text, make_public=True)
    print(f"[DRIVE] uploaded mirror_{ts}.jpg (id={fid})")
    if fid and stem:
        try:
            import photo_store
            photo_store.set_drive_id(stem, fid)
        except Exception as e:
            print(f"[DRIVE] set_drive_id failed: {e}")


def _do_upload_photo(frame: np.ndarray, desc: str,
                     folder_id: Optional[str] = None) -> None:
    service = _build_service()
    if service is None:
        return
    if folder_id is None:
        folder_id = _parent_folder_id()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fid = _upload_jpeg(service, f"photo_{ts}.jpg",
                       _frame_to_jpeg_bytes(frame), folder_id,
                       description=desc)
    print(f"[DRIVE] uploaded photo_{ts}.jpg -> {folder_id} (id={fid})")


def _do_upload_booth(strip_image: Image.Image,
                     stem: Optional[str] = None) -> None:
    service = _build_service()
    if service is None:
        return
    receipts_id = (os.environ.get("GOOGLE_DRIVE_RECEIPTS_FOLDER_ID")
                   or _parent_folder_id())
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fid = _upload_jpeg(service, f"booth_strip_{ts}.jpg",
                       _pil_to_jpeg_bytes(strip_image), receipts_id,
                       description="Photobooth strip", make_public=True)
    print(f"[DRIVE] uploaded booth_strip_{ts}.jpg (id={fid})")
    if fid and stem:
        try:
            import photo_store
            photo_store.set_drive_id(stem, fid)
        except Exception as e:
            print(f"[DRIVE] set_drive_id failed: {e}")


def _do_create_session_folder() -> Optional[Tuple[str, str]]:
    service = _build_service()
    parent_id = _parent_folder_id()
    if service is None or not parent_id:
        return None
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    meta = {
        "name": f"booth_{ts}",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=meta, fields="id").execute()
    folder_id: str = folder["id"]
    # make publicly readable so the QR code link works without sign-in
    service.permissions().create(
        fileId=folder_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    print(f"[DRIVE] created session folder: {url}")
    return folder_id, url


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload_async(frame: np.ndarray, text: str,
                 stem: Optional[str] = None) -> None:
    """Fire-and-forget: upload a single mirror frame + AI caption."""
    if frame is None:
        return
    _executor.submit(_do_upload, frame, text, stem)


def upload_photo_only_async(frame: np.ndarray, desc: str) -> None:
    """Fire-and-forget: upload a single frame with a description."""
    if frame is None:
        return
    _executor.submit(_do_upload_photo, frame, desc)


def upload_photo_to_folder_async(frame: np.ndarray,
                                 folder_id: str, desc: str) -> None:
    """Fire-and-forget: upload a frame into a specific Drive folder."""
    if frame is None:
        return
    _executor.submit(_do_upload_photo, frame, desc, folder_id)


def upload_booth_async(strip_image: Image.Image,
                       stem: Optional[str] = None) -> None:
    """Fire-and-forget: upload the composed photobooth strip PIL image."""
    if strip_image is None:
        return
    _executor.submit(_do_upload_booth, strip_image, stem)


def create_booth_session_folder() -> Optional[Tuple[str, str]]:
    """Blocking — create a Drive subfolder before the photobooth shots begin.

    Returns (folder_id, public_url) on success, or None if Drive is not
    configured / available.
    """
    try:
        return _do_create_session_folder()
    except Exception as e:
        print(f"[DRIVE] create_booth_session_folder failed: {e}")
        return None
