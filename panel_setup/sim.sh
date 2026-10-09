#!/usr/bin/env bash
# Run the whole wall on this Mac: the control website on http://localhost:8080 and the panels in a
# window (pygame). Music mode listens to the Mac microphone; mirror mode uses the Mac webcam.
#   ./panel_setup/sim.sh            (Ctrl-C stops everything)
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
echo "==> wall simulator: http://localhost:8080  (panels open in a window when a mode starts)"
exec "$PY" panel_setup/wall_control.py --sim --port "${PORT:-8080}"
