"""Link the wall to Spotify, once. Run on the laptop:

    python3 tools/spotify_login.py <client id>

1. Make an app at https://developer.spotify.com/dashboard (any name), tick "Web API", and add the
   redirect URI  http://127.0.0.1:8888/callback  - then copy its Client ID.
2. Run this; a browser opens; log in to Spotify and allow "read your playback state".
3. The token is saved in panel_setup/spotify_token.json (git-ignored) and copied to the wall.

PKCE: no client secret exists anywhere. The wall can only read what is playing.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from display.spotify import TOKEN_FILE, _save                     # noqa: E402

REDIRECT = "http://127.0.0.1:8888/callback"
PI = os.environ.get("WALL_HOST", "pi@192.168.1.129")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    client_id = sys.argv[1].strip()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": "user-read-playback-state", "code_challenge_method": "S256",
        "code_challenge": challenge, "state": state})
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state:
                got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = "code" in got
            self.wfile.write(("<p style='font:20px sans-serif;margin:40px'>" + (
                "Linked. You can close this tab." if ok else "Not linked: " + got.get("error", "no code")) + "</p>").encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8888), H)
    print("Opening Spotify in the browser...")
    webbrowser.open(url)
    while not got:
        srv.handle_request()
    if "code" not in got:
        sys.exit("Spotify did not link: " + got.get("error", "?"))
    body = urllib.parse.urlencode({"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT,
                                   "client_id": client_id, "code_verifier": verifier}).encode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", body,
                                 {"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.load(r)
    _save(TOKEN_FILE, {"client_id": client_id, "refresh_token": j["refresh_token"]})
    print("Saved", os.path.relpath(TOKEN_FILE, ROOT))
    dest = PI + ":/home/pi/magic-mirror/panel_setup/spotify_token.json"
    if subprocess.run(["scp", "-q", TOKEN_FILE, dest]).returncode == 0:
        subprocess.run(["ssh", PI, "chmod 600 /home/pi/magic-mirror/panel_setup/spotify_token.json"])
        print("Copied to the wall. Switch on 'Follow the speakers' in the app's Music tab.")
    else:
        print("Could not copy to the wall; copy it yourself:", dest)


if __name__ == "__main__":
    main()
