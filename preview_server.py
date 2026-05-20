"""Standalone mock server for dashboard preview — no mirror hardware needed."""
import datetime, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- mock data ---
MOCK_PHOTOS = [
    {"id":"receipt_20250520_143200","type":"receipt","text":"Looking suspiciously fabulous today.","prompts":[],"ts":"2025-05-20T14:32:00","url":"/photos/receipt_20250520_143200.jpg"},
    {"id":"strip_20250520_130500","type":"strip","text":"","prompts":["Best regal pose","Show me chaos","Fake-laugh at a joke"],"ts":"2025-05-20T13:05:00","url":"/photos/strip_20250520_130500.jpg"},
]

import config as cfg

@app.route("/api/status")
def status():
    return jsonify({"online":True,"state":"IDLE","sim_mode":True})

@app.route("/api/prompts", methods=["GET","POST"])
def prompts():
    if request.method == "POST":
        data = request.get_json() or {}
        for k in ("MIRROR_PERSONA","BOOTH_AI_PROMPT_SYSTEM","AI_FALLBACK_MESSAGE"):
            if k in data: setattr(cfg, k, data[k])
        return jsonify({"updated": list(data.keys())})
    return jsonify({"MIRROR_PERSONA":cfg.MIRROR_PERSONA,"BOOTH_AI_PROMPT_SYSTEM":cfg.BOOTH_AI_PROMPT_SYSTEM,"AI_FALLBACK_MESSAGE":cfg.AI_FALLBACK_MESSAGE})

@app.route("/api/config", methods=["GET","POST"])
def config_route():
    if request.method == "POST":
        return jsonify({"updated":[]})
    return jsonify({"MESSAGE_SCROLL_SPEED":cfg.MESSAGE_SCROLL_SPEED})

@app.route("/api/snapshot")
def snapshot():
    return jsonify({"data":None})

@app.route("/api/trigger/short", methods=["POST"])
def trig_short(): return jsonify({"triggered":"short"})

@app.route("/api/trigger/long", methods=["POST"])
def trig_long(): return jsonify({"triggered":"long"})

@app.route("/api/power/on",  methods=["POST"])
def power_on():  return jsonify({"power":"on"})

@app.route("/api/power/off", methods=["POST"])
def power_off(): return jsonify({"power":"off"})

@app.route("/api/display/text",  methods=["POST"])
def disp_text():  return jsonify({"ok":True})

@app.route("/api/display/image", methods=["POST"])
def disp_img():   return jsonify({"ok":True})

@app.route("/api/display", methods=["DELETE"])
def disp_clear(): return jsonify({"ok":True})

@app.route("/api/photos")
def photos(): return jsonify(MOCK_PHOTOS)

@app.route("/api/photos/<stem>/reprint", methods=["POST"])
def reprint(stem): return jsonify({"ok":True})

@app.route("/photos/<path:f>")
def photo_file(f): return jsonify({"error":"no local photos in preview"}), 404

@app.route("/")
def index():
    with open("dashboard/index.html") as fh: return fh.read(), 200, {"Content-Type":"text/html"}

@app.route("/gallery")
def gallery():
    with open("dashboard/photos.html") as fh: return fh.read(), 200, {"Content-Type":"text/html"}

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    print(f"Preview server → http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
