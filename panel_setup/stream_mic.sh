#!/usr/bin/env bash
# Stream this Mac's microphone to the Pi for the "music" mode (stand-in until a
# USB sound card is on the Pi). Raw 16-bit mono 22050 Hz over UDP, ~20 ms delay.
#   ./panel_setup/stream_mic.sh                         # to 192.168.1.207:9099
#   PI=192.168.1.50 MIC="External Microphone" ./panel_setup/stream_mic.sh
# List microphones: ffmpeg -f avfoundation -list_devices true -i ""
set -uo pipefail
PI="${PI:-192.168.1.207}"
PORT="${PORT:-9099}"
MIC="${MIC:-MacBook Pro Microphone}"
echo "==> streaming \"$MIC\" to udp://$PI:$PORT  (Ctrl-C to stop)"
while true; do
    ffmpeg -hide_banner -loglevel error -f avfoundation -i ":$MIC" \
        -ac 1 -ar 22050 -f s16le "udp://$PI:$PORT?pkt_size=1024" || true
    sleep 1
done
