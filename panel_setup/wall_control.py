"""Wall control — one web page (on the Pi) to choose what the LED wall shows.

    sudo python3 panel_setup/wall_control.py            # http://<pi>/  (port 80)
    sudo python3 panel_setup/wall_control.py --port 8080

It is the only program that drives the panels: each mode runs as a child
process (play.py <anim>, main.py for the mirror, wheel.py for a spin), the
controller stops the old one before starting the next, restarts a mode that
crashes, runs playlists, and remembers the choice across reboots
(panel_setup/wall_state.json). Install as a boot service with
panel_setup/install_control.sh.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
STATE_FILE = os.path.join(HERE, "wall_state.json")
LOG_DIR = os.path.join(HERE, "logs")
WEB_DIR = os.path.join(HERE, "web")
THUMB_DIR = os.path.join(WEB_DIR, "thumbs")
PY = sys.executable or "/usr/bin/python3"

MODES = [
    # id, category, title, description
    ("lava", "Art", "Lava & Coral", "Lava lamps, brain coral, mercury, neon contours - 10 slow pieces"),
    ("art", "Art", "Art Gallery", "Ink flow, colour fields, lava, coral, moiré"),
    ("pride", "Shows", "Pride Show", "Disco ball, HOUSE FORTUNA, people nearby, vortex, heart"),
    ("dewa", "Shows", "Dewa's Story", "Edelweiss flight attendant, a date at every layover"),
    ("maeva", "Shows", "Maeva in Zürich", "Tram at 8:00:00, the Limmat, Sprüngli, sledging"),
    ("welcome", "Shows", "Welcome", "Welcome to HOUSE FORTUNA, wheel of fortune"),
    ("cow", "Shows", "Dewa is a cow", "A message card"),
    ("music", "Live", "Music", "Chill art that breathes with the music; an AI VJ picks the vibe (Mac mic for now)"),
    ("ambient", "Live", "Art + trams", "Lava & Coral with a small Rennweg tram strip"),
    ("trams", "Live", "Tram board", "Live departures from Rennweg, split-flap style"),
]
MODE_IDS = {m[0] for m in MODES}
DEFAULT_STATE = {"mode": "lava", "brightness": 40, "playlist": None,
                 "camera_url": "http://192.168.1.217:8090/cam.mjpg", "camera": "stream",
                 "mirror_auto": 0}


# ------------------------------------------------------------------ state ---

def load_state():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        return {**DEFAULT_STATE, **s}
    except Exception:
        return dict(DEFAULT_STATE)


def save_state(s):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, STATE_FILE)


# ----------------------------------------------------------------- runner ---

class Runner:
    def __init__(self):
        self.state = load_state()
        self.proc = None
        self.current = None          # what is running now (mode id, "mirror", "wheel", "off")
        self.since = time.time()
        self.lock = threading.RLock()
        self.restarts = []
        self.error = ""
        self.oneshot_resume = None
        self.playlist_idx = 0
        self.playlist_next = 0.0
        os.makedirs(LOG_DIR, exist_ok=True)
        threading.Thread(target=self._watch, daemon=True).start()

    # -- commands
    def _cmd(self, what):
        if what in MODE_IDS:
            return [PY, "panel_setup/play.py", what, "--fps", "29"]
        if what == "mirror":
            cmd = [PY, "-u", "main.py", "--no-touch", "--no-mqtt"]
            if self.state.get("camera") == "stream" and self.state.get("camera_url"):
                cmd += ["--camera-url", self.state["camera_url"]]
            elif self.state.get("camera") == "pi":
                pass                                    # real Pi camera
            else:
                cmd += ["--mock-camera", "static"]
            if int(self.state.get("mirror_auto") or 0) > 0:
                cmd += ["--auto", str(int(self.state["mirror_auto"]))]
            return cmd
        if what == "wheel":
            return [PY, "-u", "panel_setup/wheel.py", "--spins", "1"] + \
                   ([] if self.state.get("wheel_print", True) else ["--no-print"])
        return None

    def _stop_proc(self):
        p = self.proc
        self.proc = None
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGINT)
                p.wait(timeout=8)
            except Exception:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except Exception:
                    pass

    def _start(self, what):
        self._stop_proc()
        self.current, self.since, self.error = what, time.time(), ""
        cmd = self._cmd(what)
        if cmd is None:                                 # "off"
            return
        env = dict(os.environ, WALL_BRIGHTNESS=str(int(self.state.get("brightness", 40))),
                   PYTHONUNBUFFERED="1")
        log = open(os.path.join(LOG_DIR, f"{what}.log"), "ab")
        log.write(f"\n==== {time.ctime()} {' '.join(cmd)}\n".encode())
        self.proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, start_new_session=True)

    # -- public API
    def play(self, what, remember=True):
        with self.lock:
            self.oneshot_resume = None
            if remember:
                self.state["mode"] = what
                self.state["playlist"] = None
                save_state(self.state)
            self._start(what)

    def playlist(self, ids, minutes):
        ids = [i for i in ids if i in MODE_IDS]
        if not ids:
            return
        with self.lock:
            self.state["playlist"] = {"ids": ids, "minutes": max(1, int(minutes))}
            self.state["mode"] = "playlist"
            save_state(self.state)
            self.playlist_idx = 0
            self.playlist_next = time.time() + self.state["playlist"]["minutes"] * 60
            self._start(ids[0])

    def oneshot(self, what):
        with self.lock:
            resume = self.state["mode"]
            self._start(what)
            self.oneshot_resume = resume

    def set_brightness(self, value):
        with self.lock:
            self.state["brightness"] = max(5, min(100, int(value)))
            save_state(self.state)
            if self.current not in (None, "off") and self.oneshot_resume is None:
                self._start(self.current)               # brightness applies at start

    def resume_saved(self):
        with self.lock:
            m = self.state.get("mode", "lava")
            if m == "playlist" and self.state.get("playlist"):
                pl = self.state["playlist"]
                self.playlist(pl["ids"], pl["minutes"])
            else:
                self._start(m)

    def status(self):
        with self.lock:
            alive = self.proc is not None and self.proc.poll() is None
            pl = self.state.get("playlist")
            return {"current": self.current, "saved": self.state.get("mode"),
                    "since": self.since, "running": alive or self.current == "off",
                    "brightness": self.state.get("brightness"), "playlist": pl,
                    "playlist_next": self.playlist_next if pl else None,
                    "camera": self.state.get("camera"), "camera_url": self.state.get("camera_url"),
                    "mirror_auto": self.state.get("mirror_auto", 0),
                    "wheel_print": self.state.get("wheel_print", True),
                    "error": self.error, "oneshot": self.oneshot_resume is not None}

    # -- watchdog: crashes, one-shots, playlists
    def _watch(self):
        while True:
            time.sleep(1.0)
            with self.lock:
                p = self.proc
                if self.current not in (None, "off") and p is not None and p.poll() is not None:
                    if self.oneshot_resume is not None:          # wheel finished: go back
                        resume, self.oneshot_resume = self.oneshot_resume, None
                        self.resume_saved() if resume else self._start("off")
                        continue
                    now = time.time()
                    self.restarts = [r for r in self.restarts if now - r < 120] + [now]
                    tail = _tail(os.path.join(LOG_DIR, f"{self.current}.log"))
                    if len(self.restarts) > 4:
                        self.error = f"'{self.current}' keeps crashing - stopped. {tail}"
                        self.proc = None
                        continue
                    self.error = f"'{self.current}' restarted after exit code {p.returncode}"
                    self._start(self.current)
                    continue
                pl = self.state.get("playlist")
                if (self.state.get("mode") == "playlist" and pl and self.oneshot_resume is None
                        and time.time() >= self.playlist_next):
                    self.playlist_idx = (self.playlist_idx + 1) % len(pl["ids"])
                    self.playlist_next = time.time() + pl["minutes"] * 60
                    self._start(pl["ids"][self.playlist_idx])

    def shutdown(self):
        with self.lock:
            self._stop_proc()


def _tail(path, n=300):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - n))
            return f.read().decode(errors="replace").strip().splitlines()[-1]
    except Exception:
        return ""


# ------------------------------------------------------------- thumbnails ---

def make_thumbs():
    """Render a preview still of every animation (runs once in the background)."""
    os.makedirs(THUMB_DIR, exist_ok=True)
    try:
        from PIL import Image, ImageDraw
        from display import (art, cards, dewa_story, maeva_story, pride_show, welcome)
        from display.pride_show import _emoji
        import config
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT

        def seq(fn, until, step=0.04):
            t, img = 0.0, None
            while t <= until:
                img = fn(t)
                t += step
            return img

        def icon(ch, bg, label):
            img = Image.new("RGB", (W, H), bg)
            e = _emoji(ch, 90)
            if e is not None:
                img.paste(e, ((W - e.width) // 2, 30), e)
            ImageDraw.Draw(img).text((W // 2, H - 30), label, fill=(255, 255, 255), anchor="mm")
            return img

        jobs = {
            "lava": lambda: seq(art.LavaCoralGallery(), 4.0),
            "art": lambda: seq(art.Gallery(), 12.0),
            "pride": lambda: pride_show.frame(9.5),
            "dewa": lambda: dewa_story.frame(24.5),
            "maeva": lambda: maeva_story.frame(8.0),
            "welcome": lambda: welcome.welcome_frame(10.0),
            "cow": lambda: cards.cow_card(),
            "ambient": lambda: seq(art.LavaCoralGallery(), 4.0),
            "trams": lambda: icon("🚋", (0, 45, 110), "Rennweg"),
            "music": lambda: icon("🎵", (20, 10, 40), "listening"),
            "mirror": lambda: icon("🪞", (10, 40, 30), "silhouette"),
            "wheel": lambda: icon("🎡", (40, 10, 50), "spin"),
        }
        for k, fn in jobs.items():
            path = os.path.join(THUMB_DIR, f"{k}.png")
            if os.path.exists(path):
                continue
            try:
                fn().save(path)
            except Exception as e:
                print(f"[THUMB] {k}: {e}")
    except Exception as e:
        print(f"[THUMB] skipped: {e}")


# ------------------------------------------------------------------- web ---

def make_app(runner):
    from flask import Flask, jsonify, request, send_from_directory
    app = Flask(__name__, static_folder=None)

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/thumbs/<path:name>")
    def thumbs(name):
        return send_from_directory(THUMB_DIR, name, max_age=3600)

    @app.get("/api/modes")
    def modes():
        return jsonify([{"id": i, "cat": c, "title": t, "desc": d} for i, c, t, d in MODES])

    @app.get("/api/status")
    def status():
        return jsonify(runner.status())

    @app.post("/api/play")
    def play():
        mode = (request.get_json(force=True, silent=True) or {}).get("mode")
        if mode not in MODE_IDS and mode != "off":
            return jsonify({"error": "unknown mode"}), 400
        runner.play(mode)
        return jsonify(runner.status())

    @app.post("/api/off")
    def off():
        runner.play("off")
        return jsonify(runner.status())

    @app.post("/api/brightness")
    def brightness():
        runner.set_brightness((request.get_json(force=True, silent=True) or {}).get("value", 40))
        return jsonify(runner.status())

    @app.post("/api/playlist")
    def playlist():
        d = request.get_json(force=True, silent=True) or {}
        runner.playlist(d.get("ids", []), d.get("minutes", 5))
        return jsonify(runner.status())

    @app.post("/api/wheel")
    def wheel():
        d = request.get_json(force=True, silent=True) or {}
        runner.state["wheel_print"] = bool(d.get("print", True))
        save_state(runner.state)
        runner.oneshot("wheel")
        return jsonify(runner.status())

    @app.post("/api/mirror")
    def mirror():
        d = request.get_json(force=True, silent=True) or {}
        for k in ("camera", "camera_url"):
            if k in d:
                runner.state[k] = d[k]
        runner.state["mirror_auto"] = int(d.get("auto", 0) or 0)
        runner.play("mirror")
        return jsonify(runner.status())

    @app.get("/api/music")
    def music_get():
        from display import music as mu
        try:
            with open(mu.NOW_FILE) as fh:
                now = json.load(fh)
            if time.time() - now.get("time", 0) > 15 or runner.current != "music":
                now = None
        except Exception:
            now = None
        return jsonify({"settings": mu.load_settings(), "now": now,
                        "styles": mu.STYLES, "palettes": list(mu.PALETTES),
                        "vibes": list(mu.VIBES)})

    @app.post("/api/music")
    def music_set():
        from display import music as mu
        d = request.get_json(force=True, silent=True) or {}
        st = mu.load_settings()
        for k in ("style", "palette", "vibe"):
            if k in d:
                st[k] = d[k]
        mu._write_json(mu.SETTINGS_FILE, st)
        if d.get("start") and runner.current != "music":
            runner.play("music")
        return jsonify({"settings": mu.load_settings(), "status": runner.status()})

    @app.post("/api/mirror/photo")
    def photo():
        if runner.current != "mirror":
            return jsonify({"error": "mirror mode is not running"}), 409
        try:
            req = urllib.request.Request("http://127.0.0.1:5000/api/trigger/short", method="POST")
            urllib.request.urlopen(req, timeout=3).read()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": f"mirror not ready yet ({e})"}), 503

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=80)
    a = ap.parse_args()
    runner = Runner()
    runner.resume_saved()
    threading.Thread(target=make_thumbs, daemon=True).start()

    def bye(*_):
        runner.shutdown()
        os._exit(0)
    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    app = make_app(runner)
    app.run(host="0.0.0.0", port=a.port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
