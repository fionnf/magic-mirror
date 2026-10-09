#!/usr/bin/env bash
# Set up a second Pi as the room's print server (run ON that Pi, from a folder holding
# print_server.py, print_out.py and this script):
#   PRINT_KEY=<secret> ./install_print_server.sh            # USB printer
#   PRINT_KEY=<secret> PRINTER_TARGET=serial:/dev/rfcomm0 ./install_print_server.sh   # Bluetooth
# The wall then uses WALL_PRINTER=http://$(hostname).local:8631 with the same PRINT_KEY.
set -euo pipefail
: "${PRINT_KEY:?set PRINT_KEY}"
DIR="$(cd "$(dirname "$0")" && pwd)"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pil python3-numpy python3-usb avahi-daemon
pip3 install --break-system-packages --quiet python-escpos
# let the service user talk to the USB printer (0416:5011 = the house's POS-58)
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="0416", ATTR{idProduct}=="5011", MODE="0666"' |
  sudo tee /etc/udev/rules.d/60-receipt-printer.rules >/dev/null
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo tee /etc/systemd/system/print-server.service >/dev/null <<UNIT
[Unit]
Description=Receipt print server for the Fortuna wall
After=network-online.target
Wants=network-online.target
[Service]
User=$USER
Environment=PRINT_KEY=$PRINT_KEY
Environment=PRINTER_TARGET=${PRINTER_TARGET:-usb}
ExecStart=/usr/bin/python3 $DIR/print_server.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now print-server
sleep 2 && curl -s "http://localhost:8631/health"; echo
echo "On the wall's Pi, add to .env:  WALL_PRINTER=http://$(hostname).local:8631  and  PRINT_KEY=<same secret>"
