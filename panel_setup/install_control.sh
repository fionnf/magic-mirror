#!/usr/bin/env bash
# Install the wall control website as the boot service (replaces wall-art.service).
# Run ON THE PI:
#   ./panel_setup/install_control.sh             # web page on http://<pi>/  (port 80)
#   ./panel_setup/install_control.sh --remove
# It disables wall-art.service and magic-mirror.service: the controller is the
# one program that drives the panels and starts whatever you pick on the page.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT=/etc/systemd/system/wall-control.service

if [ "${1:-}" = "--remove" ]; then
    sudo systemctl disable --now wall-control.service 2>/dev/null || true
    sudo rm -f "$UNIT"; sudo systemctl daemon-reload
    echo "wall-control removed"; exit 0
fi

sudo systemctl disable --now wall-art.service magic-mirror.service 2>/dev/null || true
sudo tee "$UNIT" >/dev/null <<UNITEOF
[Unit]
Description=LED wall control website + player
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=/usr/bin/python3 $ROOT/panel_setup/wall_control.py --port 80
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=15
User=root

[Install]
WantedBy=multi-user.target
UNITEOF
sudo systemctl daemon-reload
sudo systemctl enable wall-control.service
sudo systemctl restart wall-control.service
IP=$(hostname -I | awk '{print $1}')
echo "wall control running: http://$IP/   (and http://$(hostname).local/)"
