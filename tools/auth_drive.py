"""One-time OAuth flow for the Drive uploader.

Run this on a machine with a browser (your laptop). It opens Google's auth
page, you approve, and the resulting credentials are written to
`token.json` in the project root. Copy that file to the Pi alongside
`main.py` and the uploader will use it automatically — refreshing in the
background as long as you keep using it occasionally (~6 months of
inactivity will force a re-run)..

Requires `oauth_client.json` in the project root — see README for the
3-step "OAuth client ID" download from Google Cloud Console.

Usage:
    python tools/auth_drive.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def main():
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_path = config.GOOGLE_OAUTH_CLIENT_PATH
    token_path = config.GOOGLE_OAUTH_TOKEN_PATH
    scopes = ["https://www.googleapis.com/auth/drive.file"]

    if not os.path.exists(client_path):
        print(f"ERROR: {client_path} not found.")
        print()
        print("Create an OAuth client in Google Cloud Console:")
        print("  1. https://console.cloud.google.com/apis/credentials")
        print("  2. + Create Credentials → OAuth client ID")
        print("  3. Application type: Desktop app")
        print("  4. Name: 'magic-mirror'")
        print("  5. Create → Download JSON → save it as 'oauth_client.json'")
        print(f"     in {os.path.abspath('.')}")
        sys.exit(2)

    flow = InstalledAppFlow.from_client_secrets_file(client_path, scopes)
    print("[AUTH] Opening browser for Google sign-in...")
    creds = flow.run_local_server(port=0, prompt="consent")

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"[AUTH] Wrote {token_path}")
    print()
    print("Next:")
    print(f"  scp {token_path} pi@<pi-hostname>:{os.path.abspath(token_path)}")
    print("…or just leave it here if you're testing locally with --sim.")


if __name__ == "__main__":
    main()
