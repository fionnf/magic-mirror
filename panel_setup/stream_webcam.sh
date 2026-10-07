#!/usr/bin/env bash
# Serve this Mac's webcam as an MJPEG stream for the mirror on the Pi
# (stand-in while the Pi camera port is out of action).
#   ./panel_setup/stream_webcam.sh                       # FaceTime camera, port 8090
#   CAMERA="Fionn’s iPhone Camera" ./panel_setup/stream_webcam.sh
# Then on the Pi:
#   sudo python3 main.py --no-touch --camera-url http://<mac-ip>:8090/cam.mjpg
# ffmpeg serves one client at a time; the loop re-listens after a disconnect.
# macOS may ask once whether ffmpeg may accept incoming connections: allow it.
set -uo pipefail
CAMERA="${CAMERA:-FaceTime HD Camera}"
PORT="${PORT:-8090}"
IP="$(ipconfig getifaddr en0 2>/dev/null || echo '<mac-ip>')"
echo "==> streaming \"$CAMERA\" at http://$IP:$PORT/cam.mjpg  (Ctrl-C to stop)"
while true; do
    ffmpeg -hide_banner -loglevel error \
        -f avfoundation -pixel_format nv12 -framerate 30 -video_size 1280x720 -i "$CAMERA" \
        -vf "fps=15,scale=960:540" -q:v 7 \
        -f mpjpeg -listen 1 "http://0.0.0.0:$PORT/cam.mjpg" || true
    sleep 0.5
done
