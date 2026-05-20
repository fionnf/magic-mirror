"""Lightweight HTTP API for the magic mirror.

Runs in a daemon thread alongside the main loop.

CORS enabled so GitHub Pages can call it from a local network.
"""
import base64
import io as _io
import os
import threading
from typing import Any, Dict

try:
    from flask import Flask, jsonify, request, send_from_directory
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
        self.port   = port
        self.app    = Flask(__name__)
        CORS(self.app)
        self._register_routes()

    def _register_routes(self) -> None:
        if not self.app:
            return

        # --------------------------------------------------------- status

        @self.app.route("/api/status", methods=["GET"])
        def get_status():
            return jsonify({
                "online":   True,
                "state":    self.mirror.state.name,
                "sim_mode": self.mirror.sim_mode,
            })

        # --------------------------------------------------------- control

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

        # --------------------------------------------------------- config

        @self.app.route("/api/config", methods=["GET"])
        def get_config():
            import config as cfg
            safe_keys = [
                "TOTAL_WIDTH", "TOTAL_HEIGHT", "IDLE_ANIMATION_FPS",
                "MESSAGE_SCROLL_SPEED", "AI_FALLBACK_MESSAGE",
            ]
            return jsonify({k: getattr(cfg, k) for k in safe_keys})

        @self.app.route("/api/config", methods=["POST"])
        def set_config():
            data = request.get_json() or {}
            import config as cfg
            if "MESSAGE_SCROLL_SPEED" in data:
                cfg.MESSAGE_SCROLL_SPEED = int(data["MESSAGE_SCROLL_SPEED"])
            return jsonify({"updated": list(data.keys())})

        # --------------------------------------------------------- prompts

        @self.app.route("/api/prompts", methods=["GET"])
        def get_prompts():
            import config as cfg
            return jsonify({
                "MIRROR_PERSONA":         cfg.MIRROR_PERSONA,
                "BOOTH_AI_PROMPT_SYSTEM": cfg.BOOTH_AI_PROMPT_SYSTEM,
                "AI_FALLBACK_MESSAGE":    cfg.AI_FALLBACK_MESSAGE,
            })

        @self.app.route("/api/prompts", methods=["POST"])
        def set_prompts():
            import config as cfg
            data    = request.get_json() or {}
            allowed = {"MIRROR_PERSONA", "BOOTH_AI_PROMPT_SYSTEM", "AI_FALLBACK_MESSAGE"}
            updated = []
            for k, v in data.items():
                if k in allowed and isinstance(v, str):
                    setattr(cfg, k, v)
                    updated.append(k)
            return jsonify({"updated": updated})

        # ------------------------------------------------------ display overlay

        @self.app.route("/api/display/text", methods=["POST"])
        def display_text():
            data = request.get_json() or {}
            self.mirror._overlay_text  = data.get("text") or None
            self.mirror._overlay_image = None
            return jsonify({"ok": True})

        @self.app.route("/api/display/image", methods=["POST"])
        def display_image():
            from PIL import Image
            import config as cfg
            data     = request.get_json() or {}
            raw      = data.get("data", "")
            if raw:
                img_bytes = base64.b64decode(raw)
                img = Image.open(_io.BytesIO(img_bytes)).convert("RGB")
                img = img.resize((cfg.TOTAL_WIDTH, cfg.TOTAL_HEIGHT))
                self.mirror._overlay_image = img
                self.mirror._overlay_text  = None
            return jsonify({"ok": True})

        @self.app.route("/api/display", methods=["DELETE"])
        def clear_display():
            self.mirror._overlay_text  = None
            self.mirror._overlay_image = None
            return jsonify({"ok": True})

        # --------------------------------------------------------- snapshot

        @self.app.route("/api/snapshot", methods=["GET"])
        def snapshot():
            import cv2
            from PIL import Image
            frame = self.mirror._latest_frame
            if frame is None:
                return jsonify({"data": None})
            small = cv2.resize(frame, (320, 240))
            rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            buf   = _io.BytesIO()
            Image.fromarray(rgb).save(buf, format="JPEG", quality=60)
            return jsonify({"data": base64.b64encode(buf.getvalue()).decode()})

        # ---------------------------------------------------------- photos

        @self.app.route("/api/photos", methods=["GET"])
        def list_photos():
            try:
                import photo_store
                hours = int(request.args.get("hours", 24))
                return jsonify(photo_store.list_recent(hours))
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/photos/<path:filename>", methods=["GET"])
        def serve_photo(filename):
            try:
                import photo_store
                return send_from_directory(photo_store.PHOTOS_DIR, filename)
            except Exception as e:
                return jsonify({"error": str(e)}), 404

        @self.app.route("/api/photos/<stem>/reprint", methods=["POST"])
        def reprint_photo(stem):
            try:
                import photo_store, cv2
                import numpy as np
                from PIL import Image as _Img
                meta = photo_store.get_meta(stem)
                if meta is None:
                    return jsonify({"error": "not found"}), 404
                if meta["type"] == "strip":
                    path = photo_store.get_image_path(stem)
                    self.mirror.printer.print_strip(_Img.open(path))
                else:
                    frame_path = (photo_store.get_image_path(stem + "_frame")
                                  or photo_store.get_image_path(stem))
                    img   = _Img.open(frame_path).convert("RGB")
                    frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                    self.mirror.printer.print_receipt(frame, meta.get("text", ""))
                return jsonify({"ok": True})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        # ------------------------------------------------------ HTML pages

        @self.app.route("/", methods=["GET"])
        def index():
            if os.path.exists("dashboard/index.html"):
                with open("dashboard/index.html") as f:
                    return f.read(), 200, {"Content-Type": "text/html"}
            return jsonify({"api": "magic-mirror", "ready": True})

        @self.app.route("/gallery", methods=["GET"])
        def gallery():
            if os.path.exists("dashboard/photos.html"):
                with open("dashboard/photos.html") as f:
                    return f.read(), 200, {"Content-Type": "text/html"}
            return jsonify({"error": "photos page not found"}), 404

    def start(self) -> None:
        if not self.app:
            return
        thread = threading.Thread(
            target=lambda: self.app.run(host="0.0.0.0", port=self.port,
                                        debug=False, use_reloader=False),
            daemon=True, name="mirror-api")
        thread.start()
        print(f"[API] listening on http://0.0.0.0:{self.port}")
