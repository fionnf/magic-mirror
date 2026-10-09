#!/usr/bin/env bash
# Fresh Raspberry Pi 4 (Raspberry Pi OS Lite 64-bit, Debian 13 "trixie") -> LED wall.
# Run ON THE NEW PI, from the project folder, after it is on the network and the code is there:
#   laptop:  PI_USER=pi PI_HOST=<new-pi-ip> ./panel_setup/deploy.sh
#   pi:      cd ~/magic-mirror && ./panel_setup/bootstrap_pi.sh
# Safe to re-run. Takes ~10-15 minutes (the panel library is compiled).
# NOT yet run on a fresh image - read the output, and tell Claude what fails.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
say() {
    printf '\n==> %s\n' "$*"
    local n="${1%%/*}" total=7
    if [[ "$n" =~ ^[0-9]+$ ]]; then
        local filled=$(( n * 20 / total )) bar="" i
        for ((i = 0; i < 20; i++)); do [ $i -lt $filled ] && bar+="#" || bar+="-"; done
        printf '    [%s] step %s of %s (%d%%)\n' "$bar" "$n" "$total" $(( n * 100 / total ))
    fi
}

say "1/7 system packages"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git build-essential python3-dev python3-pip cython3 \
    python3-pil python3-numpy python3-opencv python3-picamera2 \
    python3-flask python3-flask-cors python3-paho-mqtt python3-dotenv \
    ffmpeg alsa-utils i2c-tools libopenblas-dev rsync \
    fonts-dejavu-core fonts-noto-color-emoji

say "2/7 panel library (rpi-rgb-led-matrix, compiled from source)"
WORK="$ROOT/.build"
mkdir -p "$WORK"
if [ ! -d "$WORK/rpi-rgb-led-matrix/.git" ]; then
    git clone --depth=1 https://github.com/hzeller/rpi-rgb-led-matrix "$WORK/rpi-rgb-led-matrix"
fi
sudo pip3 install --break-system-packages --root-user-action=ignore "$WORK/rpi-rgb-led-matrix"

say "3/7 python packages (system-wide: the services run as root)"
sudo pip3 install --break-system-packages --root-user-action=ignore --ignore-installed \
    anthropic python-escpos pyusb qrcode \
    google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 \
    shazamio audioop-lts tinytuya
# optional hardware extras (touch button, LED strip): fine if they fail
sudo pip3 install --break-system-packages --root-user-action=ignore RPi.GPIO rpi_ws281x \
    || echo "(optional RPi.GPIO / rpi_ws281x not installed - only needed for touch button / LED strip)"

say "4/7 boot config (HUB75 needs the onboard audio off)"
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
if ! grep -q '^dtparam=audio=off' "$CFG"; then
    echo 'dtparam=audio=off' | sudo tee -a "$CFG" >/dev/null
    echo "   added dtparam=audio=off (takes effect after a reboot)"
fi
sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$CFG"      # the stock line 'audio=on' would re-enable it
echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf >/dev/null
grep -q '^camera_auto_detect=1' "$CFG" || echo "   note: camera_auto_detect=1 is not set in $CFG"

say "5/7 secrets file"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   created .env from .env.example - fill in ANTHROPIC_API_KEY (or copy the laptop's .env)"
else
    echo "   .env already present"
fi

say "5b/7 face models (OpenCV zoo)"
./assets/models/get_models.sh

say "6/7 wall control website + autostart (port 80)"
chmod +x panel_setup/*.sh
./panel_setup/install_control.sh

say "7/7 health check"
echo "-- panel library:  $(python3 -c 'import rgbmatrix; print("ok")' 2>&1 | tail -1)"
echo "-- shazamio:       $(python3 -c 'import shazamio; print("ok")' 2>&1 | tail -1)"
echo "-- camera:         $(rpicam-hello --list-cameras 2>&1 | head -3 | tr '\n' ' ')"
echo "-- throttling:     $(vcgencmd get_throttled 2>&1)"
echo "-- sound capture:  $(arecord -l 2>&1 | grep -c '^card') device(s)"
echo
echo "Done. Reboot once ('sudo reboot') so the audio setting applies, then open http://$(hostname -I | awk '{print $1}')/"
