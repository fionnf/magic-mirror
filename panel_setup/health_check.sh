#!/usr/bin/env bash
# Health check for the wall Pi. Run by bootstrap_pi.sh, and again after the reboot:
#   ./panel_setup/run.sh health
# Read-only: it does not stop or start anything.
set -uo pipefail
cd "$(dirname "$0")/.."

SND=0
lsmod 2>/dev/null | grep -q '^snd_bcm2835' && SND=1

echo "-- panel library:  $(python3 -c 'import rgbmatrix; print("installed")' 2>&1 | tail -1)"
if [ $SND = 1 ]; then
    echo "-- onboard sound:  LOADED - the panel library refuses to run until it is off (reboot after bootstrap)"
else
    echo "-- onboard sound:  off (ok)"
fi

# the service is what actually drives the panels, so its state is the real hardware test
STATE=$(systemctl is-active wall-control.service 2>/dev/null)
if [ "$STATE" = "active" ]; then
    RESTARTS=$(systemctl show -p NRestarts --value wall-control.service 2>/dev/null)
    if [ "${RESTARTS:-0}" -gt 0 ]; then
        echo "-- wall-control:   active but restarted ${RESTARTS}x - check: journalctl -u wall-control -n 30"
    else
        echo "-- wall-control:   running"
    fi
elif [ $SND = 1 ] && systemctl is-enabled -q wall-control.service 2>/dev/null; then
    echo "-- wall-control:   enabled, starts after the reboot"
else
    echo "-- wall-control:   ${STATE:-not installed} - last log lines:"
    journalctl -u wall-control.service -n 5 --no-pager 2>/dev/null | sed 's/^/     /'
fi

echo "-- shazamio:       $(python3 -c 'import shazamio; print("ok")' 2>&1 | tail -1)"
if command -v rpicam-hello >/dev/null; then
    echo "-- camera:         $(rpicam-hello --list-cameras 2>&1 | head -3 | tr '\n' ' ')"
else
    echo "-- camera:         rpicam-hello not installed (sudo apt install rpicam-apps-lite) - not checked"
fi
echo "-- throttling:     $(python3 - <<'PY' 2>&1 | tail -1
from panel_setup.monitor import throttle_flags, flag_names
raw, _ = throttle_flags()
if raw is None:
    print("vcgencmd not available")
else:
    now = flag_names(raw, 0xF)
    past = flag_names(raw, 0xF0000)
    print(f"{raw:#x} now: {','.join(now) or 'ok'}"
          + (f" | since boot: {','.join(past)}" if past else ""))
PY
)"
echo "-- sound capture:  $(arecord -l 2>/dev/null | grep -c '^card') device(s)"
