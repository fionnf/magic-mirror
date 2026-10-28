# Optional: archive photos and receipts to Google Drive

Mirror photos and photobooth strips can be uploaded to a Google Drive folder
(`cloud_uploader.py`). It is fire-and-forget: if no credentials or no folder id are found, every
upload call returns silently and the rest of the app is unaffected. The wall only ever *writes*
(scope `drive.file`: files the app itself created).

## Set up (once, on your laptop)

1. Open <https://console.cloud.google.com/apis/credentials> in a Google Cloud project of yours
   (create one if needed; enable the **Google Drive API** for it).
2. **Create credentials, OAuth client ID**, application type **Desktop app**, any name.
   You may have to configure the OAuth consent screen first; add your own Google account as a test
   user if the app stays in testing mode.
3. Download the JSON and save it as `oauth_client.json` in the project root.
4. Run the one-time sign-in:

   ```bash
   .venv/bin/python tools/auth_drive.py
   ```

   A browser opens; approve. It writes `token.json` in the project root.
5. Make a folder in Drive, open it, and copy the id from the address bar
   (`https://drive.google.com/drive/folders/<THIS PART>`). Put it in `.env`:

   ```
   GOOGLE_DRIVE_FOLDER_ID=<folder id>
   # optional: a separate folder for booth strips and receipts (defaults to the folder above)
   GOOGLE_DRIVE_RECEIPTS_FOLDER_ID=<folder id>
   ```
6. Copy the token to the Pi. `deploy.sh` deliberately never sends `.env`, `token.json` or
   `oauth_client.json`:

   ```bash
   scp .env token.json pi@<pi-ip>:~/magic-mirror/
   ```

`token.json` refreshes itself while the wall keeps using it; `tools/auth_drive.py`'s header notes that
about six months of inactivity forces a re-run.

## Alternative: a service account

If your Google account cannot create OAuth clients, download a service-account key and save it as
`gcp-credentials.json` in the project root; share the target Drive folder with the service account's
e-mail address. The uploader tries the OAuth token first, then the service account.

## Never commit these

`token.json`, `oauth_client.json`, `gcp-credentials.json` and `.env` are in `.gitignore`.

## End-of-night timelapse

`tools/timelapse.py` downloads the day's `mirror_*.jpg` photos from the folder and stitches them into
an MP4, then uploads the video back (it skips nights with fewer than 10 photos):

```bash
python tools/timelapse.py --date 2026-10-12 --min 1 --fps 2 --no-upload --out /tmp/tl.mp4
```
