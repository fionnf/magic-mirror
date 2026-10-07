#!/usr/bin/env bash
# Run the panel display test on the Pi (needs root for GPIO).
#   ./panel_setup/run.sh                 # cycle all patterns
#   ./panel_setup/run.sh walk            # one panel at a time (start here)
#   ./panel_setup/run.sh numbers         # one pattern: walk numbers gradient bar text anim white
#   ./panel_setup/run.sh bar --show-refresh --pwm-bits 7 --slowdown 2
#   ./panel_setup/run.sh monitor         # health readout only (2nd SSH session)
#   ./panel_setup/run.sh tune            # find the lightest clean timing preset
#   ./panel_setup/run.sh --single        # one panel only (wiring debug)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--single" ]; then
    shift
    exec sudo python3 panel_setup/single_panel_test.py "$@"
fi

if [ "${1:-}" = "monitor" ]; then
    shift
    exec python3 panel_setup/monitor.py "$@"      # run in a 2nd SSH session
fi

if [ "${1:-}" = "tune" ]; then
    shift
    exec sudo python3 panel_setup/tune.py "$@"    # steps through timing presets
fi

ARGS=()
if [ $# -gt 0 ] && [[ "$1" != -* ]]; then
    ARGS+=(--pattern "$1"); shift
fi
exec sudo python3 panel_setup/display_test.py "${ARGS[@]}" "$@"
