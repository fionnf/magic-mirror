"""Lightweight HTTP API for the magic mirror.

Runs in a daemon thread alongside the main loop. Exposes JSON endpoints for:
  - status (online/state/last trigger)
  - trigger (short/long press)
  - power (on/off)
  - settings (read/write config)
  - photos (list/fetch from Drive or local)

CORS enabled so GitHub Pages can call it from a local network.
"""
import json
import os
import threading
import time
from typing import Any, Dict

try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


class MirrorAPI:
    def __init__(self, mirror, port: int = 5000):
        if not HAS_FLASK:
            self.app = None
            return

        self.mirror = mirror
        self.port = port
        self.app = Flask(__name__)
        CORS(self.app)
        self._register_routes()

    def _register_routes(self) -> None:
        if not self.app:
            return

        @self.app.route("/api/status", methods=["GET"])
        def get_status():
            return jsonify({
                "online": True,
                "state": self.mirror.state.name,
                "sim_mode": self.mirror.sim_mode,
            })

        @self.app.route("/api/trigger/short", methods=["POST"])
        def trigger_short():
            self.mirror._trigger_event.set()
            return jsonify({"triggered": "short"})

        @self.app.route("/api/trigger/long", methods=["POST"])
        def trigger_long():
            self.mirror._booth_event.set()
            return jsonify({"triggered": "long"})

        @self.app.route("/api/power/on", methods=["POST"])
        def power_on():
            self.mirror._stop.clear()
            return jsonify({"power": "on"})

        @self.app.route("/api/power/off", methods=["POST"])
        def power_off():
            self.mirror._stop.set()
            return jsonify({"power": "off"})

        @self.app.route("/api/config", methods=["GET"])
        def get_config():
            import config as cfg
            # safe subset of config
            safe_keys = [
                "TOTAL_WIDTH", "TOTAL_HEIGHT", "IDLE_ANIMATION_FPS",
                "MESSAGE_SCROLL_SPEED", "AI_FALLBACK_MESSAGE",
            ]
            return jsonify({k: getattr(cfg, k) for k in safe_keys})

        @self.app.route("/api/config", methods=["POST"])
        def set_config():
            data = request.get_json() or {}
            # only allow safe mutations (e.g., scroll speed)
            import config as cfg
            if "MESSAGE_SCROLL_SPEED" in data:
                cfg.MESSAGE_SCROLL_SPEED = int(data["MESSAGE_SCROLL_SPEED"])
            return jsonify({"updated": list(data.keys())})

        @self.app.route("/", methods=["GET"])
        def index():
            # serve the dashboard if it exists locally
            if os.path.exists("dashboard/index.html"):
                with open("dashboard/index.html") as f:
                    return f.read(), 200, {"Content-Type": "text/html"}
            return jsonify({"api": "magic-mirror", "ready": True})

    def start(self) -> None:
        if not self.app:
            return
        thread = threading.Thread(
            target=lambda: self.app.run(host="0.0.0.0", port=self.port,
                                       debug=False, use_reloader=False),
            daemon=True, name="mirror-api")
        thread.start()
        print(f"[API] listening on http://0.0.0.0:{self.port}")
