"""Step through matrix timing presets, fastest/lightest first, to find the
lowest-load setting that still looks good. Pi only (needs sudo).

    sudo python3 panel_setup/tune.py            # 12 s per preset
    sudo python3 panel_setup/tune.py --secs 20

Each preset runs the moving-bar pattern with the refresh rate printed. Watch
the wall for flicker/banding/ghosting and the [PI] line for CPU/fps. Note the
last preset that still looks clean, then copy its values into config.py
(GPIO_SLOWDOWN, MATRIX_PWM_BITS, MATRIX_PWM_DITHER_BITS, MATRIX_PWM_LSB_NS).
"""
import argparse
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# (label, slowdown, pwm_bits, dither, lsb_ns)
PRESETS = [
    ("lightest: 6 bit, slowdown 3",     3, 6, 0, 100),
    ("7 bit, slowdown 3 (confirmed on 1 panel)", 3, 7, 0, 130),
    ("7 bit + dither 1, slowdown 3",    3, 7, 1, 130),
    ("8 bit, slowdown 3",               3, 8, 0, 130),
    ("8 bit + dither 1, slowdown 3",    3, 8, 1, 130),
    ("7 bit, slowdown 4 (safe)",        4, 7, 0, 130),
]

ap = argparse.ArgumentParser()
ap.add_argument("--secs", type=int, default=12)
a = ap.parse_args()

for label, slow, bits, dith, lsb in PRESETS:
    print(f"\n=== {label}  [--slowdown {slow} --pwm-bits {bits} "
          f"--dither {dith} --lsb-ns {lsb}]", flush=True)
    p = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "display_test.py"),
         "--pattern", "bar", "--show-refresh", "--slowdown", str(slow),
         "--pwm-bits", str(bits), "--dither", str(dith), "--lsb-ns", str(lsb),
         "--log", ""])
    time.sleep(a.secs)
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
print("\nDone. Put the best clean preset's values into config.py.")
