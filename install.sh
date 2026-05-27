#!/usr/bin/env bash
# Magic Mirror installer — Raspberry Pi OS Bookworm / Trixie or later.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="magic-mirror.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

echo "==> Updating apt"
sudo apt-get update

echo "==> Installing system deps"
sudo apt-get install -y \
    git build-essential python3-pip python3-dev python3-venv \
    python3-picamera2 libopencv-dev cython3 \
    libopenblas-dev

echo "==> Building rpi-rgb-led-matrix Python bindings"
WORK="${PROJECT_DIR}/.build"
mkdir -p "$WORK"
rm -rf "$WORK/rpi-rgb-led-matrix"
git clone --depth=1 https://github.com/hzeller/rpi-rgb-led-matrix "$WORK/rpi-rgb-led-matrix"
sudo pip3 install --break-system-packages "$WORK/rpi-rgb-led-matrix"

echo "==> Installing Python requirements"
pip3 install --break-system-packages -r "${PROJECT_DIR}/requirements.txt"

echo "==> Setting up .env"
if [ ! -f "${PROJECT_DIR}/.env" ]; then
    cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
    read -rp "Enter your OPENAI_API_KEY: " KEY
    sed -i "s|your_key_here|${KEY}|" "${PROJECT_DIR}/.env"
fi

echo "==> Disabling onboard audio (frees GPIO PWM for HUB75)"
if ! grep -q "^dtparam=audio=off" /boot/config.txt 2>/dev/null; then
    if [ -f /boot/firmware/config.txt ]; then
        TARGET=/boot/firmware/config.txt
    else
        TARGET=/boot/config.txt
    fi
    echo "dtparam=audio=off" | sudo tee -a "$TARGET" >/dev/null
    echo "  (rebooting required)"
fi

echo "==> Installing systemd service"
sudo tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=Magic Mirror
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=/usr/bin/python3 ${PROJECT_DIR}/main.py
Restart=on-failure
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
echo "==> Done. Reboot recommended. Start now with: sudo systemctl start $SERVICE_NAME"
