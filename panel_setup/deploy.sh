#!/usr/bin/env bash
# Copy the project from this machine to the Pi (code only, no secrets/photos).
#   ./panel_setup/deploy.sh                 # uses pi@mirror.local
#   PI_HOST=192.168.1.50 PI_USER=fionn ./panel_setup/deploy.sh
set -euo pipefail
PI_USER="${PI_USER:-pi}"
PI_HOST="${PI_HOST:-192.168.1.207}"     # Fortuna
PI_DIR="${PI_DIR:-magic-mirror}"          # relative to the Pi user's home
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Syncing ${ROOT} -> ${PI_USER}@${PI_HOST}:~/${PI_DIR}"
rsync -avz \
    --exclude '.git' --exclude '.idea' --exclude '.venv' --exclude 'venv' --exclude '.claude' --exclude '.build' --exclude '__pycache__' \
    --exclude '.env' --exclude 'token.json' --exclude 'oauth_client.json' \
    --exclude 'gcp-credentials.json' --exclude 'tinytuya.json' --exclude 'tuya-raw.json' --exclude 'snapshot.json' --exclude 'photos/' --exclude 'tests/sim_receipts' \
    --include 'panel_setup/web/thumbs/' --include 'panel_setup/web/thumbs/*.png' --exclude 'gifs/' \
    --exclude 'panel_setup/wall_state.json' --exclude 'panel_setup/music_settings.json' --exclude 'panel_setup/music_now.json' --exclude 'panel_setup/audio_now.json' --exclude 'panel_setup/lights_state.json' --exclude 'panel_setup/mirror_settings.json' --exclude 'panel_setup/faces.json' --exclude 'panel_setup/dedications.json' --exclude 'panel_setup/logs/' \
    --exclude '*.png' --exclude '*.jpg' --exclude 'usage.log' --exclude 'panel_setup/monitor.csv' \
    "${ROOT}/" "${PI_USER}@${PI_HOST}:${PI_DIR}/"
echo "==> Done. On the Pi:  cd ~/${PI_DIR} && ./panel_setup/run.sh numbers"
