#!/usr/bin/env bash
# Set up the room's second Pi as the wireless receipt-printer server, from this laptop, once it has booted and joined
# the Wi-Fi (flash it with Raspberry Pi Imager: hostname printpi, user pi, your Wi-Fi, SSH on - see docs/printer-pi.md).
#
#   PRINTER_PI=printpi.local ./tools/setup_printer_pi.sh
#
# It (1) copies the print server to the printer Pi, (2) installs and starts it as a service with a fresh shared secret,
# (3) tells the wall's Pi (WALL_HOST, default the live wall) where the printer is, and restarts the wall's app.
# Nothing here prints: after it, "Mirror" > photo or photobooth strip prints on the wireless printer.
set -euo pipefail
cd "$(dirname "$0")/.."
PRINTER_PI="${PRINTER_PI:-printpi.local}"
PRINTER_USER="${PRINTER_USER:-pi}"
WALL_HOST="${WALL_HOST:-192.168.1.129}"
WALL_USER="${WALL_USER:-pi}"
PRINTER_TARGET="${PRINTER_TARGET:-usb}"          # usb | serial:/dev/rfcomm0 (Bluetooth) | tcp://192.168.1.50:9100
KEY="${PRINT_KEY:-$(openssl rand -hex 16)}"

echo "==> printer Pi: ${PRINTER_USER}@${PRINTER_PI}"
ssh -o StrictHostKeyChecking=accept-new "${PRINTER_USER}@${PRINTER_PI}" 'mkdir -p ~/print-server'
scp -q tools/print_server.py tools/install_print_server.sh print_out.py "${PRINTER_USER}@${PRINTER_PI}:print-server/"
ssh "${PRINTER_USER}@${PRINTER_PI}" "cd ~/print-server && chmod +x install_print_server.sh && PRINT_KEY='${KEY}' PRINTER_TARGET='${PRINTER_TARGET}' ./install_print_server.sh"

HOST="$(ssh "${PRINTER_USER}@${PRINTER_PI}" hostname)"
URL="http://${HOST}.local:8631"
echo "==> wall Pi: ${WALL_USER}@${WALL_HOST} will print through ${URL}"
ssh "${WALL_USER}@${WALL_HOST}" "cd ~/magic-mirror && sudo sed -i '/^WALL_PRINTER=/d;/^PRINT_KEY=/d' .env && printf 'WALL_PRINTER=${URL}\nPRINT_KEY=${KEY}\n' | sudo tee -a .env >/dev/null && sudo systemctl restart wall-control"
sleep 20
echo "==> checking from the wall's side:"
ssh "${WALL_USER}@${WALL_HOST}" "curl -s localhost/api/printer; echo"
echo "Done. The secret is stored on both Pis (not printed here)."
