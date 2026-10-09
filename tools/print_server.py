#!/usr/bin/env python3
"""Print server for a receipt printer that hangs off another Pi in the room (Wi-Fi to the wall).

On the printer's Pi (just this file + print_out.py, see tools/install_print_server.sh):
    PRINT_KEY=<shared secret> python3 print_server.py            # listens on :8631
On the wall's Pi, in .env:
    WALL_PRINTER=http://<printer-pi>.local:8631
    PRINT_KEY=<the same secret>

POST /print   a 1-bit PNG at printer width (the wall dithers it), header X-Print-Key; ?cut=0 to not cut
GET  /health  "ok <printer>" when the printer answers
The printer on this Pi is PRINTER_TARGET (default usb; tcp://... or serial:/dev/rfcomm0 also work).
Jobs print one at a time, in order.
"""
import hmac
import io
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import print_out  # noqa: E402
from PIL import Image  # noqa: E402

KEY = os.environ.get("PRINT_KEY", "")
TARGET = os.environ.get("PRINTER_TARGET", "usb")
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, text):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            return self._reply(404, "no")
        os.environ["WALL_PRINTER"] = TARGET
        s = print_out.status()
        self._reply(200 if s["ok"] else 503, f"{'ok' if s['ok'] else 'down'} {TARGET} {s['note']}".strip())

    def do_POST(self):
        if not self.path.startswith("/print"):
            return self._reply(404, "no")
        if not KEY or not hmac.compare_digest(self.headers.get("X-Print-Key", ""), KEY):
            return self._reply(403, "wrong key")
        n = int(self.headers.get("Content-Length", 0))
        if not 0 < n < 8_000_000:
            return self._reply(400, "no image")
        try:
            img = Image.open(io.BytesIO(self.rfile.read(n)))
            img = img.convert("1") if img.mode == "1" else print_out.to_1bit(img)
            with LOCK:
                print_out.print_local(img, TARGET, cut="cut=0" not in self.path)
            self._reply(200, "printed")
        except Exception as e:
            print(f"[print server] {e}", flush=True)
            self._reply(500, str(e)[:200])

    def log_message(self, fmt, *args):
        print(f"[print server] {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    if not KEY:
        sys.exit("set PRINT_KEY (the same secret as on the wall's Pi)")
    port = int(os.environ.get("PRINT_PORT", 8631))
    print(f"[print server] {TARGET} on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
