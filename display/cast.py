"""What the house's Google Cast speakers (and TV) are playing, pushed to us by the devices themselves.

    w = CastWatcher(); w.start()
    w.now()   -> {"playing": bool, "music": bool, "device", "title", "artist", "album", "image", "app",
                  "state", "since"} for the most relevant device, or None when nothing is casting

"music" is True only for audio (a music track, or a music app such as Spotify): a film on the TV
plays but is not music, so it never turns the wall into music art. The latest state is also written
to panel_setup/cast_now.json so the music mode can show the exact song without asking Shazam.
"""
import json
import os
import threading
import time

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW_FILE = os.path.join(_HERE, "panel_setup", "cast_now.json")
MUSIC_APPS = ("spotify", "youtube music", "deezer", "tidal", "apple music", "soundcloud", "tunein",
              "radio", "pandora", "amazon music", "qobuz", "default media receiver")
OTHER_ROOMS = ("bath", "bedroom", "kitchen", "office", "garage")
MUSIC_TRACK = 3                                        # Cast metadataType for a music track


class CastWatcher:
    def __init__(self):
        self.devices = {}                              # name -> latest status dict
        self.lock = threading.Lock()
        self.browser = None
        self.error = ""

    def start(self):
        try:
            import pychromecast
        except Exception as e:                         # not installed: the feature just stays quiet
            self.error = f"pychromecast missing ({e})"
            return False
        self.browser = pychromecast.get_chromecasts(blocking=False, callback=self._found)
        return True

    # -- device callbacks (pychromecast's own threads)
    def _found(self, cast):
        name = (getattr(cast.cast_info, "friendly_name", None) or cast.name or "").strip()
        watcher = self

        class _Media:
            def new_media_status(self, st):
                watcher._update(name, cast, st)

            def load_media_failed(self, *a):
                pass

        try:
            cast.media_controller.register_status_listener(_Media())
            cast.start()
        except Exception as e:
            print(f"[cast] {name}: {e}", flush=True)

    def _update(self, name, cast, st):
        app = ((cast.status.display_name if cast.status else "") or "").strip()
        state = st.player_state or "UNKNOWN"
        ctype = (st.content_type or "").lower()
        music = (st.metadata_type == MUSIC_TRACK or ctype.startswith("audio/")
                 or any(m in app.lower() for m in MUSIC_APPS)) and not ctype.startswith("video/")
        img = ""
        if st.images:
            img = getattr(st.images[0], "url", "") or ""
        with self.lock:
            old = self.devices.get(name, {})
            playing = state in ("PLAYING", "BUFFERING")
            self.devices[name] = {
                "device": name, "state": state, "playing": playing, "music": bool(music),
                "title": st.title or "", "artist": st.artist or "", "album": st.album_name or "",
                "image": img, "app": app,
                "since": old.get("since") if old.get("playing") == playing else time.time(),
                "seen": time.time()}

    # -- reading
    def names(self):
        """Every speaker / TV / group found on the network."""
        try:
            infos = list(self.browser.devices.values()) if self.browser else []
        except Exception:
            infos = []
        return sorted({(getattr(i, "friendly_name", "") or "").strip() for i in infos} - {""})

    def chosen(self, settings, extra=(), home=()):
        """The devices that count. Default: every Cast speaker not in another room (bathroom...), plus
        `home` (Spotify devices that are a TV or speaker). settings["cast_devices"] = {name: bool}
        holds only what was switched by hand, so a newly found device still gets the default."""
        pick = settings.get("cast_devices") or {}
        default = {n for n in list(self.names()) + list(home) if not any(r in n.lower() for r in OTHER_ROOMS)}
        return {n for n in self.all_names(extra) if pick.get(n, n in default)}

    def all_names(self, extra=()):
        return sorted(set(self.names()) | set(extra))

    def speakers(self, settings, extra=(), home=()):
        ch = self.chosen(settings, extra, home)
        return [{"name": n, "on": n in ch} for n in self.all_names(extra)]

    def now(self, chosen=None):
        """The device that matters most: playing music > playing anything > paused; newest first.
        chosen = names to consider (None = all)."""
        with self.lock:
            devs = [d for d in self.devices.values() if chosen is None or d["device"].strip() in chosen]
        if not devs:
            return None
        rank = lambda d: (d["playing"] and d["music"], d["playing"], d["state"] == "PAUSED", d["since"] or 0)
        best = max(devs, key=rank)
        if best["state"] in ("IDLE", "UNKNOWN") and not best["title"]:
            return None
        return dict(best)



def write_now(d):
    """The playing music the house cares about (written by the server, read by the music mode)."""
    try:
        tmp = NOW_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({**d, "written": time.time()} if d else {}, fh)
        os.replace(tmp, NOW_FILE)
    except Exception:
        pass


def read_now(max_age=900.0):
    """For other processes (the music mode): the speaker's song, if one is playing music right now."""
    try:
        with open(NOW_FILE) as fh:
            d = json.load(fh)
    except Exception:
        return None
    if d.get("playing") and d.get("music") and d.get("title") and time.time() - d.get("written", 0) < max_age:
        return d
    return None


if __name__ == "__main__":                            # python -m display.cast : watch for 30 s
    w = CastWatcher()
    print("started" if w.start() else w.error)
    for _ in range(15):
        time.sleep(2)
        print(w.now())
