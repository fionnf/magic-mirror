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
import urllib.error
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
    ("lava", "Art", "Lava & Coral", "Coral, bloom, cells and slow bioluminescence"),
    ("shapes", "Art", "Shapes", "Flow dots, woven grids, ripples: thin glowing lines"),
    ("daily", "Art", "Art of the day", "A new piece every day, composed by Claude"),
    ("shaders", "Art", "Shaders", "Conic tiles, aperture, eclipse, halo, glass and more"),
    ("artsy", "Art", "Artsy", "Marbling, op-art stripes, oil slick, a drifting Mondrian"),
    ("glass", "Art", "Light Art", "Stained glass, long-exposure trails, nebula"),
    ("art", "Art", "Art Gallery", "Ink flow, colour fields, moiré"),
    ("pride", "Shows", "Pride Show", "Disco ball, HOUSE FORTUNA, people nearby, vortex, heart"),
    ("dewa", "Shows", "Dewa's Story", "Edelweiss flight attendant, a date at every layover"),
    ("maeva", "Shows", "Maeva in Zürich", "Tram at 8:00:00, the Limmat, Sprüngli, sledging"),
    ("welcome", "Shows", "Welcome", "Welcome to HOUSE FORTUNA, wheel of fortune"),
    ("cow", "Shows", "Dewa is a cow", "A message card"),
    ("music", "Live", "Music", "Art that breathes with the music in the room"),
    ("ambient", "Live", "Art + trams", "Lava & Coral with a small Rennweg tram strip"),
    ("trams", "Live", "Tram board", "Live departures from Rennweg, split-flap style"),
]
MODE_IDS = {m[0] for m in MODES}
DEFAULT_STATE = {"mode": "lava", "brightness": 40, "playlist": None,
                 "camera_url": "http://192.168.1.217:8090/cam.mjpg", "camera": "stream",
                 "mirror_auto": 0, "smart_crop": True, "art_speed": 0.12}


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
            if os.environ.get("WALL_SIM"):
                cmd += ["--sim", "--camera", "webcam"]           # laptop: pygame window + its webcam
            elif self.state.get("camera") == "stream" and self.state.get("camera_url"):
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
                   WALL_DAILY_DATE=str(self.state.get("daily_date") or ""),
                   WALL_ART_SPEED=str(float(self.state.get("art_speed", 0.12))),
                   WALL_SMART_CROP="1" if self.state.get("smart_crop", True) else "0",
                   PYTHONUNBUFFERED="1")
        if getattr(self, "boot_pending", False) and self.state.get("boot_welcome", True):
            env["WALL_BOOT"] = "1"               # first start after power-on: play the welcome once
        self.boot_pending = False
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

    def restart_current(self):
        with self.lock:
            if self.current not in (None, "off"):
                self._start(self.current)

    def set_brightness(self, value):
        with self.lock:
            self.state["brightness"] = max(5, min(100, int(value)))
            save_state(self.state)
            if self.current not in (None, "off") and self.oneshot_resume is None:
                self._start(self.current)               # brightness applies at start

    def set_art_speed(self, value):
        with self.lock:
            self.state["art_speed"] = max(0.03, min(1.0, float(value)))
            save_state(self.state)
            if self.current in ("art", "lava", "shapes", "glass", "artsy", "ambient", "shaders"):
                self._start(self.current)

    def resume_saved(self):
        with self.lock:
            self.boot_pending = True
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
                    "smart_crop": self.state.get("smart_crop", True),
                    "art_speed": self.state.get("art_speed", 0.12),
                    "wall_w": __import__("config").TOTAL_WIDTH, "wall_h": __import__("config").TOTAL_HEIGHT,
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
        from display import (art, artsy, cards, dewa_story, maeva_story, light_art, pride_show, shapes, welcome)
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
            "shapes": lambda: seq(shapes.ShapesGallery(), 60.0),
            "glass": lambda: seq(light_art.LightGallery(), 60.0),
            "artsy": lambda: seq(artsy.ArtsyGallery(), 60.0),
            "shaders": lambda: icon("🌊", (10, 20, 50), "shaders"),
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

LOGIN_PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Fortuna wall</title><style>
html,body{margin:0;height:100%;background:#17141a;color:#efe8f2;font:16px/1.4 -apple-system,system-ui,sans-serif}
main{min-height:100%;display:grid;place-items:center;padding:24px;box-sizing:border-box}
form{width:min(320px,100%);display:grid;gap:12px}
h1{font:italic 400 34px/1.1 Georgia,serif;margin:0 0 8px}
input{font:inherit;padding:14px 16px;border-radius:14px;border:1px solid #3a3240;background:#221d26;color:inherit}
button{font:inherit;font-weight:600;padding:14px;border:0;border-radius:14px;background:#efe8f2;color:#17141a}
p{color:#a69bab;margin:0;min-height:1.4em}
</style><main><form method=post action=/login>
<h1>Fortuna wall</h1>
<input type=text name=username value=fortuna autocomplete=username hidden>
<input type=password name=password placeholder=Password autocomplete=current-password autofocus required>
<button>Open the wall</button><p>{error}</p></form></main>"""


def _is_local(req):
    """On the home network (not through the tunnel)?"""
    import ipaddress
    if req.headers.get("Cf-Connecting-Ip") or req.headers.get("X-Forwarded-For"):
        return False
    try:
        ip = ipaddress.ip_address((req.remote_addr or "").split("%")[0])
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def _secret():
    path = os.path.join(HERE, ".session_secret")
    if not os.path.exists(path):
        import secrets
        with open(path, "w") as fh:
            fh.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as fh:
        return fh.read().strip()


def make_app(runner):
    from flask import Flask, jsonify, request, send_from_directory, redirect, make_response
    import hmac
    import hashlib as _hl
    app = Flask(__name__, static_folder=None)
    SECRET = _secret()
    TOKEN = hmac.new(SECRET.encode(), b"wall-session-v1", _hl.sha256).hexdigest()

    @app.before_request
    def require_login():
        """Remote visitors (through the tunnel) need the password; the home network does not.
        Guests' dedication page stays open."""
        if _is_local(request) or request.path.startswith(("/login", "/d")):
            return None
        if hmac.compare_digest(request.cookies.get("wall_session", ""), TOKEN):
            return None
        if request.path.startswith("/api/") or request.method != "GET":
            return jsonify({"error": "login needed"}), 401
        return redirect("/login")

    @app.get("/login")
    def login_page():
        return app.response_class(LOGIN_PAGE.replace("{error}", ""), mimetype="text/html")

    @app.post("/login")
    def login_post():
        want = os.environ.get("WALL_PASSWORD", "")
        got = request.form.get("password", "")
        if not want or not hmac.compare_digest(got.strip().upper(), want.strip().upper()):
            time.sleep(1.0)                                # slow down guessing
            msg = "Remote access is not set up yet." if not want else "That password is not right."
            return app.response_class(LOGIN_PAGE.replace("{error}", msg), mimetype="text/html", status=401)
        resp = make_response(redirect("/"))
        resp.set_cookie("wall_session", TOKEN, max_age=180 * 86400, httponly=True, samesite="Lax",
                        secure=request.headers.get("X-Forwarded-Proto", request.scheme) == "https")
        return resp

    @app.get("/api/now.jpg")
    def now_jpg():
        resp = send_from_directory(HERE, "now.jpg", max_age=0)
        resp.headers["Cache-Control"] = "no-store"
        return resp

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

    @app.post("/api/artspeed")
    def artspeed():
        try:
            runner.set_art_speed((request.get_json(force=True, silent=True) or {}).get("value", 0.12))
        except (TypeError, ValueError):
            return jsonify({"error": "bad value"}), 400
        return jsonify(runner.status())

    @app.post("/api/playlist")
    def playlist():
        d = request.get_json(force=True, silent=True) or {}
        runner.playlist(d.get("ids", []), d.get("minutes", 5))
        return jsonify(runner.status())

    @app.post("/api/wheel")
    def wheel():
        return jsonify({"error": "Wheel of Fortuna is switched off for now"}), 410
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
        if "smart_crop" in d:
            runner.state["smart_crop"] = bool(d["smart_crop"])
        runner.play("mirror")
        return jsonify(runner.status())

    @app.get("/api/audio")
    def audio_now():
        from display import music as mu
        try:
            with open(mu.AUDIO_FILE) as fh:
                d = json.load(fh)
            if time.time() - d.get("time", 0) > 3:
                d = {"stale": True}
        except Exception:
            d = {"stale": True}
        return jsonify(d)

    @app.get("/api/daily")
    def daily_list():
        from display import daily
        return jsonify({"today": __import__("datetime").date.today().isoformat(),
                        "chosen": runner.state.get("daily_date") or "",
                        "editions": [{"date": d, **{k: m.get(k) for k in ("name", "description", "palette", "source_sha256",
                                                                          "listening", "final", "caption")}}
                                     for d, m in daily.editions()]})

    @app.get("/daily/<path:name>")
    def daily_file(name):
        from display import daily
        return send_from_directory(daily.FOLDER, name, max_age=3600)

    @app.post("/api/daily/show")
    def daily_show():
        d = (request.get_json(force=True, silent=True) or {}).get("date", "")
        runner.state["daily_date"] = d                     # "" = always today's
        save_state(runner.state)
        runner.play("daily")
        return jsonify(runner.status())

    @app.get("/api/loops")
    def loops_list():
        from display import loops as lp
        b = lp.LoopBank()
        out = [{"name": k, "pack": k.split("__")[0], "seconds": v.get("seconds"), "motion": v.get("motion"),
                "bright": v.get("bright")} for k, v in sorted(b.clips.items(), key=lambda kv: kv[1].get("motion", 0))]
        return jsonify(out)

    @app.get("/loops/thumb/<name>.jpg")
    def loop_thumb(name):
        from display import loops as lp
        from PIL import Image
        b = lp.LoopBank()
        if name not in b.clips:
            return jsonify({"error": "no such loop"}), 404
        path = os.path.join(THUMB_DIR, "loop_" + name + ".jpg")
        if not os.path.exists(path):
            import cv2
            cap = cv2.VideoCapture(b.path(name))
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, b.clips[name].get("frames", 2) // 2))
            ok, fr = cap.read()
            cap.release()
            if not ok:
                return jsonify({"error": "cannot read"}), 500
            Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)).resize((96, 96)).save(path, quality=80)
        return send_from_directory(THUMB_DIR, "loop_" + name + ".jpg", max_age=86400)

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
        old_source = st.get("source")
        for k in ("style", "palette", "vibe", "source", "sensitivity", "ai", "shazam",
                  "song_on_wall", "brain", "beat_offset", "beat_strength", "art_reacts", "prompt", "mode", "party", "loop", "loop_music"):
            if k in d:
                st[k] = d[k]
        mu._write_json(mu.SETTINGS_FILE, st)
        if d.get("start") and runner.current != "music":
            runner.play("music")
        elif runner.current == "music" and mu.load_settings()["source"] != old_source:
            runner.restart_current()                      # new microphone: restart listening
        return jsonify({"settings": mu.load_settings(), "status": runner.status()})

    PHOTOS = os.path.join(ROOT, "photos")

    @app.post("/api/mirror/crop")
    def mirror_crop():
        """Switch the smart portrait crop on/off; restarts mirror mode if it is running."""
        runner.state["smart_crop"] = bool((request.get_json(force=True, silent=True) or {}).get("on", True))
        save_state(runner.state)
        if runner.current == "mirror":
            runner.restart_current()
        return jsonify(runner.status())

    @app.get("/api/mirror/last")
    def mirror_last():
        """The newest mirror photo and what the AI said about it."""
        try:
            names = [n for n in os.listdir(PHOTOS) if n.startswith("receipt_") and n.endswith(".jpg")]
            newest = max(names, key=lambda n: os.path.getmtime(os.path.join(PHOTOS, n)))
        except (OSError, ValueError):
            return jsonify({"photo": None})
        text = ""
        try:
            with open(os.path.join(PHOTOS, newest[:-4] + ".json")) as fh:
                text = json.load(fh).get("text", "")
        except Exception:
            pass
        return jsonify({"photo": f"/photos/{newest}", "text": text,
                        "age": int(time.time() - os.path.getmtime(os.path.join(PHOTOS, newest)))})

    @app.get("/photos/<path:name>")
    def photos(name):
        return send_from_directory(PHOTOS, name, max_age=86400)

    @app.get("/api/photos")
    def photos_list():
        """Every stored photo, newest first: the mirror's portraits, auras and photobooth strips."""
        try:
            names = [x for x in os.listdir(PHOTOS) if x.endswith(".jpg") and not x.endswith("_frame.jpg")
                     and not x.endswith(".tmp.jpg")]
        except OSError:
            names = []
        names.sort(key=lambda x: os.path.getmtime(os.path.join(PHOTOS, x)), reverse=True)
        off = int(request.args.get("offset", 0) or 0)
        lim = min(200, int(request.args.get("limit", 60) or 60))
        out = []
        for x in names[off:off + lim]:
            meta = {}
            try:
                with open(os.path.join(PHOTOS, x[:-4] + ".json")) as fh:
                    meta = json.load(fh)
            except Exception:
                pass
            out.append({"name": x, "url": f"/photos/{x}", "text": meta.get("text", ""),
                        "kind": meta.get("type", "receipt"), "time": os.path.getmtime(os.path.join(PHOTOS, x))})
        return jsonify({"total": len(names), "photos": out})

    @app.post("/api/photos/delete")
    def photos_delete():
        x = os.path.basename((request.get_json(force=True, silent=True) or {}).get("name", ""))
        if not x.endswith(".jpg"):
            return jsonify({"error": "no such photo"}), 404
        removed = 0
        for f in (x, x[:-4] + ".json", x[:-4] + "_frame.jpg"):
            try:
                os.remove(os.path.join(PHOTOS, f))
                removed += 1
            except OSError:
                pass
        return jsonify({"removed": removed})

    # ---------------------------------------------------------------- lights
    import lights as lt
    _light_cache = {"t": 0.0, "data": None}

    @app.get("/api/lights")
    def lights_get():
        devs = lt.devices()
        if not devs:
            return jsonify({"configured": False, "installed": lt.installed(), "devices": [],
                            "schedule": lt.schedule()})
        if not lt.installed():
            return jsonify({"configured": True, "installed": False, "devices": [], "schedule": lt.schedule()})
        if time.time() - _light_cache["t"] > 8 or request.args.get("fresh"):
            _light_cache.update(t=time.time(), data=lt.status())
        members = set(lt.room())
        return jsonify({"configured": True, "installed": True,
                        "devices": [{**x, "room": x["name"] in members} for x in _light_cache["data"]],
                        "schedule": lt.schedule(), "room": sorted(members)})

    @app.post("/api/lights/room")
    def lights_room():
        on = bool((request.get_json(force=True, silent=True) or {}).get("on", False))
        res = lt.set_group(lt.room(), on)
        _light_cache["t"] = 0
        return jsonify({"results": res})

    @app.post("/api/lights/members")
    def lights_members():
        names = (request.get_json(force=True, silent=True) or {}).get("names", [])
        return jsonify({"room": lt.set_room_members(names)})

    @app.post("/api/lights/scan")
    def lights_scan():
        try:
            return jsonify(lt.rescan())
        except Exception as e:
            return jsonify({"error": str(e)[:120]}), 500

    @app.post("/api/lights/one")
    def lights_one():
        d = request.get_json(force=True, silent=True) or {}
        try:
            res = lt.set_one(d.get("name", ""), bool(d.get("on")))
        except KeyError as e:
            return jsonify({"error": str(e)}), 404
        _light_cache["t"] = 0
        return jsonify({"results": res})

    @app.post("/api/lights/schedule")
    def lights_schedule():
        off = (request.get_json(force=True, silent=True) or {}).get("off") or None
        try:
            return jsonify(lt.set_schedule(off))
        except ValueError:
            return jsonify({"error": "time must look like 23:30"}), 400

    @app.get("/api/mirror/settings")
    def mirror_settings_get():
        import mirror_settings as ms
        return jsonify({**ms.load(), "languages": list(ms.LANGUAGES)})

    @app.post("/api/mirror/settings")
    def mirror_settings_set():
        import mirror_settings as ms
        d = request.get_json(force=True, silent=True) or {}
        if "language" in d and d["language"] not in ms.LANGUAGES:
            return jsonify({"error": "unknown language"}), 400
        return jsonify(ms.save(d))

    # ---- dedications: a guest page (/d) anybody on the Wi-Fi can use + admin API for the app
    GUEST_PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Say hi to the wall</title><style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#150f1f;color:#fff;font-family:-apple-system,system-ui,sans-serif}
main{width:min(92vw,420px);text-align:center}h1{font-size:26px;margin:0 0 4px}p{color:#bbb;margin:0 0 18px}
input,textarea{width:100%;box-sizing:border-box;padding:14px;border-radius:12px;border:1px solid #3a2f4f;background:#211833;color:#fff;font-size:17px;margin-bottom:10px;font-family:inherit}
button{width:100%;padding:14px;border:0;border-radius:12px;background:linear-gradient(90deg,#ff5fa2,#ffb347);color:#1b0f1f;font-weight:700;font-size:17px}
#m{min-height:24px;margin-top:12px;color:#ffd36b}</style><main><h1>💌 House Fortuna</h1><p>Write something for the wall</p>
<textarea id=t maxlength=140 rows=3 placeholder="Happy birthday Dewa!! 🎂"></textarea><input id=n maxlength=24 placeholder="Your name (optional)">
<button onclick=go()>Send to the wall</button><div id=m></div></main><script>
async function go(){const r=await fetch('/d/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t.value,name:n.value})});
const j=await r.json().catch(()=>({}));m.textContent=r.ok?'✨ Sent! Look at the wall.':(j.error||'Something went wrong');if(r.ok)t.value=''}</script>"""

    @app.get("/d")
    def guest_page():
        return app.response_class(GUEST_PAGE, mimetype="text/html")

    @app.post("/d/send")
    def guest_send():
        from display import dedications
        d = request.get_json(force=True, silent=True) or {}
        try:
            dedications.add(d.get("text", ""), d.get("name", ""), who=request.remote_addr or "?")
            return jsonify({"ok": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 429 if "Slow down" in str(e) else 400

    @app.get("/d/qr.png")
    def guest_qr():
        import io
        from display import dedications
        buf = io.BytesIO()
        dedications.qr_image(dedications.guest_url(request.host.split(":")[0]), 360).save(buf, "PNG")
        return app.response_class(buf.getvalue(), mimetype="image/png")

    @app.get("/api/dedications")
    def dedications_get():
        from display import dedications
        d = dedications.load()
        return jsonify({**d, "url": dedications.guest_url(request.host.split(":")[0]), "items": d["items"][::-1]})

    @app.post("/api/dedications")
    def dedications_set():
        from display import dedications
        d = request.get_json(force=True, silent=True) or {}
        dedications.update(**{k: d[k] for k in ("enabled", "show_qr", "paused") if k in d})
        return dedications_get()

    @app.post("/api/dedications/delete")
    def dedications_delete():
        from display import dedications
        d = request.get_json(force=True, silent=True) or {}
        return jsonify({"removed": dedications.clear() if d.get("all") else dedications.delete(d.get("id", ""))})

    def _book():
        import faces
        return faces.FaceBook()

    @app.get("/api/faces")
    def faces_list():
        try:
            import faces
            ok = faces.available()
            b = faces.FaceBook()
            return jsonify({"available": ok, "people": b.people() if ok else {},
                            "suggestions": b.suggestions() if ok else []})
        except Exception as e:
            return jsonify({"available": False, "people": {}, "suggestions": [], "note": str(e)[:80]})

    @app.post("/api/faces/enrol")
    def faces_enrol():
        if runner.current != "mirror":
            return jsonify({"error": "start mirror mode first - the camera is used to learn the face"}), 409
        d = request.get_json(force=True, silent=True) or {}
        try:
            req = urllib.request.Request("http://127.0.0.1:5000/api/faces/enrol", method="POST",
                                         data=json.dumps({"name": d.get("name", "")}).encode(),
                                         headers={"Content-Type": "application/json"})
            return app.response_class(urllib.request.urlopen(req, timeout=20).read(), mimetype="application/json")
        except urllib.error.HTTPError as e:
            return app.response_class(e.read(), status=e.code, mimetype="application/json")
        except Exception as e:
            return jsonify({"error": f"mirror not ready ({e})"}), 503

    @app.post("/api/faces/forget")
    def faces_forget():
        d = request.get_json(force=True, silent=True) or {}
        if d.get("all"):
            return jsonify({"removed": _book().forget_everything()})
        if d.get("learned"):
            return jsonify({"removed": _book().forget_learned()})
        return jsonify({"removed": _book().forget(d.get("name", ""))})

    @app.post("/api/faces/name")
    def faces_name():
        d = request.get_json(force=True, silent=True) or {}
        try:
            return jsonify({"name": _book().name_suggestion(d.get("id", ""), d.get("name", ""))})
        except (KeyError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/faces/dismiss")
    def faces_dismiss():
        return jsonify({"ok": _book().dismiss((request.get_json(force=True, silent=True) or {}).get("id", ""))})

    def _mirror_trigger(kind):
        if runner.current != "mirror":
            return jsonify({"error": "mirror mode is not running"}), 409
        try:
            req = urllib.request.Request(f"http://127.0.0.1:5000/api/trigger/{kind}", method="POST")
            urllib.request.urlopen(req, timeout=3).read()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": f"mirror not ready yet ({e})"}), 503

    @app.post("/api/mirror/photo")
    def photo():
        return _mirror_trigger("short")

    @app.post("/api/mirror/pixel")
    def pixel():
        return _mirror_trigger("pixel")

    @app.post("/api/mirror/aura")
    def aura():
        return _mirror_trigger("aura")

    return app


def _start_mac_mic():
    """Simulator: stream this Mac's microphone to the music engine over UDP (needs ffmpeg)."""
    import shutil
    if not shutil.which("ffmpeg"):
        print("[sim] ffmpeg not found: music mode will have no microphone", flush=True)
        return
    mic = os.environ.get("MIC", "MacBook Pro Microphone")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-fflags", "nobuffer", "-flags", "low_delay",
           "-f", "avfoundation", "-i", f":{mic}", "-ac", "1", "-ar", "22050", "-flush_packets", "1",
           "-f", "s16le", "udp://127.0.0.1:9099?pkt_size=512"]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        print(f"[sim] streaming '{mic}' to the music engine (set MIC=... to change)", flush=True)
    except Exception as e:
        print(f"[sim] mic stream failed: {e}", flush=True)


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))          # WALL_PASSWORD, ANTHROPIC_API_KEY
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--sim", action="store_true", help="laptop: panels in a window, Mac mic, port 8080")
    a = ap.parse_args()
    if a.sim or sys.platform == "darwin":
        os.environ["WALL_SIM"] = "1"
        os.environ.setdefault("WALL_AUDIO", "udp:9099")
        _start_mac_mic()
    if a.port is None:
        a.port = 8080 if os.environ.get("WALL_SIM") else 80
    try:
        os.nice(12)                          # the website must never steal time from the panel refresh
    except OSError:
        pass
    runner = Runner()
    runner.resume_saved()
    if len([f for f in os.listdir(THUMB_DIR)] if os.path.isdir(THUMB_DIR) else []) < len(MODES) + 2:
        threading.Thread(target=make_thumbs, daemon=True).start()   # normally shipped by deploy.sh

    def _publish_pending(daily):
        """Send new or changed editions to the public gallery (remembers what went out)."""
        from display import publish
        if not publish.available():
            return
        sent_path = os.path.join(HERE, "gallery_sent.json")
        try:
            with open(sent_path) as fh:
                sent = json.load(fh)
        except Exception:
            sent = {}
        todo = [d for d, m in daily.editions()[:14]
                if sent.get(d) != ("final" if m.get("final") else "new")]
        if todo:
            publish.publish(todo)
            for d, m in daily.editions()[:14]:
                if d in todo:
                    sent[d] = "final" if m.get("final") else "new"
            with open(sent_path, "w") as fh:
                json.dump(sent, fh)

    def daily_watch():                       # compose the art of the day (once a day, ~05:00 or at boot)
        import datetime as _dt
        from display import daily
        time.sleep(30)
        while True:
            try:
                today = _dt.date.today().isoformat()
                if not os.path.exists(os.path.join(daily.FOLDER, today + ".json")) and \
                        (_dt.datetime.now().hour >= 5 or not daily.editions()):
                    meta = daily.generate(today)
                    print(f"[daily] {today}: {meta['name']}", flush=True)
                    if runner.current == "daily" and not runner.state.get("daily_date"):
                        runner.restart_current()
                for d, m in daily.editions():          # past days the wall did not close itself
                    if d < today and not m.get("final"):
                        daily.finalise(d)
                _publish_pending(daily)
            except Exception as e:
                print(f"[daily] {e}", flush=True)
                time.sleep(1800)
            time.sleep(600)

    threading.Thread(target=daily_watch, daemon=True).start()

    def lights_watch():                      # fires the daily "lights off at HH:MM"
        import lights
        while True:
            time.sleep(20)
            try:
                if lights.installed() and lights.devices() and lights.due():
                    print("[LIGHTS] scheduled lights-off (the room)", flush=True)
                    lights.set_group(lights.room(), False)
            except Exception as e:
                print(f"[LIGHTS] {e}", flush=True)
    threading.Thread(target=lights_watch, daemon=True).start()

    def bye(*_):
        runner.shutdown()
        os._exit(0)
    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    app = make_app(runner)
    app.run(host="0.0.0.0", port=a.port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
