"""Async Google Drive uploader for captured mirror frames.

Uses a service account (gcp-credentials.json) and uploads each frame as a
JPEG into the folder identified by GOOGLE_DRIVE_FOLDER_ID. The AI response
text is stored in the file's `description` field for later browsing.
"""
import io
import os
import time
import datetime
import concurrent.futures
import numpy as np
import cv2
from PIL import Image
import config


# single worker so the two uploads queue instead of racing on the same
# httplib2 connection (which isn't thread-safe and trips SSL record-layer
# failures when two threads hit it simultaneously)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
_service = None
_service_lock_failed = False  # cached failure to avoid hammering on bad config


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _enabled() -> bool:
    """At least one destination folder configured AND an auth file present."""
    has_dest = bool(os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
                    or os.environ.get("GOOGLE_DRIVE_RECEIPTS_FOLDER_ID"))
    has_auth = (os.path.exists(config.GOOGLE_OAUTH_TOKEN_PATH)
                or os.path.exists(config.GOOGLE_CREDENTIALS_PATH))
    return has_dest and has_auth


def _load_credentials():
    """Prefer OAuth user creds (token.json); fall back to a service account."""
    # OAuth user credentials path
    if os.path.exists(config.GOOGLE_OAUTH_TOKEN_PATH):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_file(
            config.GOOGLE_OAUTH_TOKEN_PATH, SCOPES)
        # auto-refresh if expired and we have a refresh token
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # persist the refreshed token so next boot doesn't need to
                with open(config.GOOGLE_OAUTH_TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
            except Exception as e:
                print(f"[DRIVE] token refresh failed: {e}")
                return None
        return creds

    # Service-account fallback
    if os.path.exists(config.GOOGLE_CREDENTIALS_PATH):
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_PATH, scopes=SCOPES)

    return None


def _get_service():
    global _service, _service_lock_failed
    if _service is not None:
        return _service
    if _service_lock_failed:
        return None
    try:
        from googleapiclient.discovery import build
        creds = _load_credentials()
        if creds is None:
            _service_lock_failed = True
            return None
        _service = build("drive", "v3", credentials=creds,
                         cache_discovery=False)
        return _service
    except Exception as e:
        print(f"[DRIVE] init failed: {e}")
        _service_lock_failed = True
        return None


def _frame_to_jpeg_bytes(frame: np.ndarray) -> bytes:
    if frame.ndim == 3 and frame.shape[2] == 3:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    else:
        rgb = frame
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _pil_to_png_bytes(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _upload_bytes(data: bytes, mime: str, name: str, folder_id: str,
                  description: str = "") -> str | None:
    svc = _get_service()
    if svc is None:
        return None
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime,
                              resumable=False)
    metadata = {
        "name": name,
        "parents": [folder_id],
        "description": description,
    }
    try:
        f = svc.files().create(body=metadata, media_body=media,
                               fields="id,webViewLink").execute()
        link = f.get("webViewLink")
        print(f"[DRIVE] uploaded {name} -> {link}")
        return link
    except Exception as e:
        print(f"[DRIVE] upload failed: {e}")
        return None


def _do_upload_photo(frame: np.ndarray, response_text: str,
                     folder_id: str) -> str | None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return _upload_bytes(_frame_to_jpeg_bytes(frame), "image/jpeg",
                         f"mirror_{ts}.jpg", folder_id,
                         description=response_text or "")


def _do_upload_receipt(frame: np.ndarray, response_text: str,
                       folder_id: str) -> str | None:
    # rendered here in the worker thread so the caller never blocks
    from printer import render_receipt_pil
    img = render_receipt_pil(frame, response_text)
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return _upload_bytes(_pil_to_png_bytes(img), "image/png",
                         f"receipt_{ts}.png", folder_id,
                         description=response_text or "")


def create_booth_session_folder(name: str = None) -> "tuple[str, str] | None":
    """Create a subfolder inside GOOGLE_DRIVE_FOLDER_ID and make it
    'anyone with the link can view' so the QR code on the printed strip
    actually resolves for whoever scans it.

    Returns (folder_id, web_view_link) or None on failure / no auth.
    This blocks for ~1 round-trip; call from the booth cycle before
    queuing the photo uploads.
    """
    parent = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not parent:
        return None
    svc = _get_service()
    if svc is None:
        return None
    if not name:
        name = "Booth " + datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    try:
        folder = svc.files().create(
            body={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent],
            },
            fields="id,webViewLink",
        ).execute()
        # make publicly readable by anyone with the link
        svc.permissions().create(
            fileId=folder["id"],
            body={"role": "reader", "type": "anyone"},
        ).execute()
        print(f"[DRIVE] booth folder -> {folder.get('webViewLink')}")
        return folder["id"], folder.get("webViewLink", "")
    except Exception as e:
        print(f"[DRIVE] booth folder create failed: {e}")
        return None


def upload_photo_to_folder_async(frame: np.ndarray, folder_id: str,
                                 description: str = "") -> None:
    """Upload one frame to a specific Drive folder ID, e.g. a booth session
    subfolder created by `create_booth_session_folder`."""
    if frame is None or not folder_id:
        return
    if _get_service() is None:
        return
    snapshot = frame.copy()
    _executor.submit(_do_upload_photo, snapshot, description, folder_id)


def upload_photo_only_async(frame: np.ndarray, description: str = "") -> None:
    """Upload a single raw frame to the photos folder. Used by booth mode
    to archive each shot (the strip goes to the receipts folder separately)."""
    photos_folder = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not photos_folder or frame is None:
        return
    if _get_service() is None:
        return
    snapshot = frame.copy()
    _executor.submit(_do_upload_photo, snapshot, description, photos_folder)


def upload_booth_async(strip_image, label: str = "Photobooth strip") -> None:
    """Upload a pre-composed booth strip PNG to the receipts folder."""
    if strip_image is None:
        print("[DRIVE] booth strip upload skipped: no image")
        return
    receipts_folder = os.environ.get("GOOGLE_DRIVE_RECEIPTS_FOLDER_ID")
    if not receipts_folder:
        print("[DRIVE] booth strip upload skipped: "
              "GOOGLE_DRIVE_RECEIPTS_FOLDER_ID not set")
        return
    if _get_service() is None:
        print("[DRIVE] booth strip upload skipped: no auth")
        return
    img_copy = strip_image.copy()

    def _do():
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _upload_bytes(_pil_to_png_bytes(img_copy), "image/png",
                      f"booth_{ts}.png", receipts_folder,
                      description=label)
    print("[DRIVE] booth strip upload queued")
    _executor.submit(_do)


def upload_async(frame: np.ndarray, response_text: str) -> None:
    """Fire both archive uploads in the background:
      - the raw captured photo into GOOGLE_DRIVE_FOLDER_ID
      - a rendered receipt PNG into GOOGLE_DRIVE_RECEIPTS_FOLDER_ID
    Either is skipped if its env var is unset.
    """
    if frame is None:
        return
    photos_folder = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    receipts_folder = os.environ.get("GOOGLE_DRIVE_RECEIPTS_FOLDER_ID")
    if not (photos_folder or receipts_folder):
        return
    if _get_service() is None:
        return  # auth missing/broken — already logged
    snapshot = frame.copy()
    if photos_folder:
        _executor.submit(_do_upload_photo, snapshot, response_text,
                         photos_folder)
    if receipts_folder:
        _executor.submit(_do_upload_receipt, snapshot, response_text,
                         receipts_folder)
