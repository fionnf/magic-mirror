#!/usr/bin/env bash
# Start a wall animation automatically at boot (systemd), restart it if it dies.
# Run ON THE PI:
#   ./panel_setup/install_autostart.sh            # lava & coral gallery
#   ./panel_setup/install_autostart.sh art        # any play.py animation
#   ./panel_setup/install_autostart.sh --remove   # turn autostart off
# Disables magic-mirror.service so two programs never fight over the panels.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT=/etc/systemd/system/wall-art.service

if [ "${1:-}" = "--remove" ]; then
    sudo systemctl disable --now wall-art.service 2>/dev/null || true
    sudo rm -f "$UNIT"; sudo systemctl daemon-reload
    echo "autostart removed"; exit 0
fi

ANIM="${1:-lava}"
sudo systemctl disable --now magic-mirror.service 2>/dev/null || true
sudo tee "$UNIT" >/dev/null <<UNITEOF
[Unit]
Description=LED wall animation ($ANIM)
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=/usr/bin/python3 $ROOT/panel_setup/play.py $ANIM --fps 25
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=10
User=root
Nice=-5

[Install]
WantedBy=multi-user.target
UNITEOF
sudo systemctl daemon-reload
sudo systemctl enable --now wall-art.service
echo "autostart installed: $ANIM (status: sudo systemctl status wall-art)"
