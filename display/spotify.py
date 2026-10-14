"""What Spotify is playing on the house's account, on any device: the Samsung TV's own Spotify app,
a speaker, a laptop. Read from the Spotify Web API (scope user-read-playback-state only).

Linking is one-time, on the laptop: python3 tools/spotify_login.py <client id>
That saves panel_setup/spotify_token.json (client id + refresh token; git-ignored, never deployed by
rsync) and copies it to the wall. No client secret is needed (PKCE).

    s = SpotifyWatcher(); s.poll() -> same shape as cast.CastWatcher.now(), or None
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(_HERE, "panel_setup", "spotify_token.json")
DEVICES_FILE = os.path.join(_HERE, "panel_setup", "spotify_devices.json")
# device types that belong to the room (a phone or laptop playing into headphones does not)
HOME_TYPES = ("tv", "speaker", "avr", "stb", "castaudio", "castvideo", "audiodongle", "gameconsole")


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


class SpotifyWatcher:
    def __init__(self):
        self.access, self.expires = None, 0.0
        self.error = ""
        self.last = None
        self.since = {}
        try:
            with open(DEVICES_FILE) as fh:
                self.devices = json.load(fh)               # name -> type, every device seen so far
        except Exception:
            self.devices = {}

    def linked(self):
        return os.path.exists(TOKEN_FILE)

    def _token(self):
        if self.access and time.time() < self.expires - 60:
            return self.access
        with open(TOKEN_FILE) as fh:
            tok = json.load(fh)
        body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                       "client_id": tok["client_id"]}).encode()
        req = urllib.request.Request("https://accounts.spotify.com/api/token", body,
                                     {"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            j = json.load(r)
        if j.get("refresh_token") and j["refresh_token"] != tok["refresh_token"]:
            tok["refresh_token"] = j["refresh_token"]       # Spotify may rotate it: keep the new one
            _save(TOKEN_FILE, tok)
        self.access, self.expires = j["access_token"], time.time() + int(j.get("expires_in", 3600))
        return self.access

    def _get(self, path):
        req = urllib.request.Request("https://api.spotify.com/v1" + path,
                                     headers={"Authorization": "Bearer " + self._token()})
        with urllib.request.urlopen(req, timeout=10) as r:
            return None if r.status == 204 else json.loads(r.read() or b"null")

    def poll(self):
        """Ask Spotify what is playing now. -> status dict or None. Never raises."""
        if not self.linked():
            self.last = None
            return None
        try:
            p = self._get("/me/player?additional_types=episode")
            self.error = ""
        except urllib.error.HTTPError as e:
            self.error = f"Spotify said {e.code}"
            if e.code == 401:
                self.access = None
            return self.last
        except Exception as e:
            self.error = str(e)[:80]
            return self.last
        if not p or not p.get("device"):
            self.last = None
            return None
        dev = p["device"]
        name, kind = (dev.get("name") or "Spotify").strip(), (dev.get("type") or "").strip()
        if self.devices.get(name) != kind:
            self.devices[name] = kind
            try:
                _save(DEVICES_FILE, self.devices)
            except Exception:
                pass
        item = p.get("item") or {}
        playing = bool(p.get("is_playing"))
        if self.since.get(name, (None, 0))[0] != playing:
            self.since[name] = (playing, time.time())
        imgs = (item.get("album") or {}).get("images") or []
        self.last = {
            "device": name, "kind": kind, "state": "PLAYING" if playing else "PAUSED", "playing": playing,
            "music": p.get("currently_playing_type") == "track", "title": item.get("name") or "",
            "artist": ", ".join(a.get("name", "") for a in item.get("artists") or []),
            "album": (item.get("album") or {}).get("name") or "", "image": imgs[0]["url"] if imgs else "",
            "app": "Spotify", "since": self.since[name][1], "seen": time.time()}
        return self.last

    def home_devices(self):
        """Seen devices that belong to the room by their type (TV, speaker...), for the default choice."""
        return {n for n, t in self.devices.items() if t.lower() in HOME_TYPES}
