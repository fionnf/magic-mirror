#!/usr/bin/env python3
"""Pin the day's piece to a Pinterest board (Pinterest API v5).

One-time login on a laptop (prints the values to keep as repository secrets):
    PINTEREST_APP_ID=... PINTEREST_APP_SECRET=... python3 tools/pinterest.py login

Pin an edition (the daily workflow runs this after publishing; needs PINTEREST_APP_ID,
PINTEREST_APP_SECRET, PINTEREST_REFRESH_TOKEN, PINTEREST_BOARD_ID):
    python3 tools/pinterest.py pin 2026-10-12

The pin carries the still (uploaded inline, so it works before the site has rebuilt), the title, the
statement and a link to the edition's page. Each run refreshes the access token from the refresh token.
"""
import base64
import json
import os
import sys
import urllib.parse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.pinterest.com/v5"
SITE_URL = os.environ.get("GALLERY_URL", "https://fionnf.github.io/magic-mirror/").rstrip("/") + "/"
SCOPES = "boards:read,pins:read,pins:write"
REDIRECT = "https://localhost/fortuna"       # must be listed in the app's redirect URIs; never served
CREDIT = "Fortuna, a living LED wall in Zürich by Dewa and Fionn. One piece a day, shaped by the room's music."


def _basic():
    app, secret = os.environ["PINTEREST_APP_ID"], os.environ["PINTEREST_APP_SECRET"]
    return {"Authorization": "Basic " + base64.b64encode(f"{app}:{secret}".encode()).decode()}


def token_from(grant):
    r = requests.post(f"{API}/oauth/token", headers=_basic(), data=grant, timeout=30)
    if r.status_code >= 300:
        raise SystemExit(f"Pinterest token: {r.status_code} {r.text[:300]}")
    return r.json()


def access_token():
    t = token_from({"grant_type": "refresh_token", "refresh_token": os.environ["PINTEREST_REFRESH_TOKEN"]})
    # The stored refresh token cannot be rotated from inside the workflow, so say so well before it runs out.
    left = int(t.get("refresh_token_expires_in") or 0) // 86400
    if t.get("refresh_token") and t["refresh_token"] != os.environ["PINTEREST_REFRESH_TOKEN"]:
        print("::notice::Pinterest issued a new refresh token; run `python3 tools/pinterest.py login` "
              "and update the PINTEREST_REFRESH_TOKEN secret when convenient.")
    if 0 < left <= 14:
        print(f"::warning::The Pinterest login runs out in {left} days: run `python3 tools/pinterest.py login` "
              "and update the PINTEREST_REFRESH_TOKEN secret.")
    return t["access_token"]


def login():
    url = ("https://www.pinterest.com/oauth/?" + urllib.parse.urlencode(
        {"client_id": os.environ["PINTEREST_APP_ID"], "redirect_uri": REDIRECT, "response_type": "code",
         "scope": SCOPES, "state": "fortuna"}))
    print("\n1. Open this in a browser, logged in to the Pinterest account that owns the board:\n\n   " + url)
    print("\n2. Approve. The browser lands on a page that does not load (that is fine). Copy its address.\n")
    back = input("3. Paste that address here: ").strip()
    code = urllib.parse.parse_qs(urllib.parse.urlparse(back).query).get("code", [""])[0] or back
    t = token_from({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                    "continuous_refresh": "true"})
    h = {"Authorization": "Bearer " + t["access_token"]}
    boards = requests.get(f"{API}/boards?page_size=50", headers=h, timeout=30).json().get("items", [])
    print("\nYour boards:")
    for b in boards:
        print(f"   {b['id']}   {b['name']}  ({b.get('privacy', '')})")
    print("\nRepository secrets to add (Settings -> Secrets and variables -> Actions):\n")
    print(f"   PINTEREST_REFRESH_TOKEN = {t['refresh_token']}")
    print("   PINTEREST_BOARD_ID      = <the id of the board above you want the pieces on>")
    print("   PINTEREST_APP_ID / PINTEREST_APP_SECRET = the app's")
    print(f"\n(the refresh token lasts about {t.get('refresh_token_expires_in', 0) // 86400} days and renews itself on use)")


def pin(date):
    need = ("PINTEREST_APP_ID", "PINTEREST_APP_SECRET", "PINTEREST_REFRESH_TOKEN", "PINTEREST_BOARD_ID")
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        print(f"Pinterest is not set up ({', '.join(missing)} missing) - not pinning {date}")
        return
    with open(os.path.join(ROOT, "gallery", f"{date}.json")) as fh:
        m = json.load(fh)
    still = f"{date}.final.png" if m.get("final") else f"{date}.png"
    with open(os.path.join(ROOT, "gallery", still), "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    post = m.get("post") or {}
    desc = (post.get("caption") or m.get("description", "")).strip()
    body = {"board_id": os.environ["PINTEREST_BOARD_ID"], "title": m["name"][:100],
            "description": (desc + "\n\n" + CREDIT)[:800], "alt_text": (post.get("alt") or m["name"])[:500],
            "link": f"{SITE_URL}e/{date}/",
            "media_source": {"source_type": "image_base64", "content_type": "image/png", "data": data}}
    r = requests.post(f"{API}/pins", headers={"Authorization": "Bearer " + access_token()}, json=body, timeout=60)
    if r.status_code >= 300:
        raise SystemExit(f"Pinterest pin: {r.status_code} {r.text[:300]}")
    j = r.json()
    print(f"pinned {date} {m['name']!r} -> https://www.pinterest.com/pin/{j.get('id')}/")


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    if cmd == ["login"]:
        login()
    elif cmd == ["pin"] and len(sys.argv) > 2:
        pin(sys.argv[2])
    else:
        sys.exit(__doc__)
