#!/usr/bin/env python3
"""Honest refresh measurement and one-at-a-time parameter sweep for the HUB75 wall.

Run ON THE PI with the wall stopped:
    sudo systemctl stop wall-control
    sudo WALL_BRIGHTNESS=75 WALL_MAX_AMPS=35 python3 tools/panel_sweep.py [--out sweep.csv]
    sudo systemctl start wall-control
Every run is its own process (the GPIO is released between runs). The refresh limit is effectively OFF (limit=1000) and the library's own
refresh readout is on, so the Hz in the CSV is what the panel really does. Each run shows 6 s of a flowing gradient, then 6 s of a
bright full-field frame; the reported Hz is the median of the readings in the last 6 s (the bright part, the worst case).
Implausible rows are flagged (Hz above what the settings can give, or a reading that does not settle).
"""
import csv, os, re, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("WALL_FIXED_DEPTH", "1")

BASE = dict(bits=6, lsb=60, dither=0, slow=7)


def one(params):
    import config
    config.MATRIX_PWM_BITS, config.MATRIX_PWM_LSB_NS = params["bits"], params["lsb"]
    config.MATRIX_PWM_DITHER_BITS, config.GPIO_SLOWDOWN = params["dither"], params["slow"]
    config.MATRIX_REFRESH_LIMIT_HZ = 1000       # far above anything the panel reaches: no limit, measure what it really does
    config.MATRIX_SHOW_REFRESH = True
    config.DEPTH_STEPS = []
    config.MATRIX_BRIGHTNESS = int(os.environ.get("WALL_BRIGHTNESS", 75))
    config.MATRIX_MAX_AMPS = float(os.environ.get("WALL_MAX_AMPS", 35))
    from PIL import Image
    import numpy as np
    from led_matrix import LedMatrix
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from refresh_test import field
    m = LedMatrix()
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    t0 = time.monotonic()
    while time.monotonic() - t0 < 12:
        t = time.monotonic() - t0
        if t < 6:
            img = Image.fromarray(field(W, H, t))                                  # gradient: banding / flicker by eye
        else:
            img = Image.fromarray(np.full((H, W, 3), (235, 205, 170), np.uint8))     # bright full-field (the power limiter will trim it)
        m.draw(img, 1)
    m.clear()


def run_all(out):
    runs = [("baseline", BASE)]
    for b in (5, 7):
        runs.append((f"bits={b}", dict(BASE, bits=b)))
    for l in (130, 100, 75, 50):
        runs.append((f"lsb={l}", dict(BASE, lsb=l)))
    for d in (1, 2):
        runs.append((f"dither={d}", dict(BASE, dither=d)))
    for s in (6, 5, 4, 3, 2, 1):
        runs.append((f"slow={s}", dict(BASE, slow=s)))
    rows = []
    for name, p in runs:
        args = [sys.executable, __file__, "--one"] + [f"{k}={v}" for k, v in p.items()]
        t0 = time.monotonic()
        r = subprocess.run(args, capture_output=True, text=True, timeout=60)
        text = (r.stdout or "") + (r.stderr or "")
        hz = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*Hz", text)]
        late = hz[len(hz) // 2:] or hz                 # the bright half
        med = sorted(late)[len(late) // 2] if late else None
        flag = ""
        if med is None:
            flag = "NO READING (" + (r.stderr or "").strip().splitlines()[-1][:60] + ")" if r.stderr.strip() else "NO READING"
        else:
            spread = (max(late) - min(late)) / med if med else 0
            if med > 1000 or med < 20:
                flag = "IMPLAUSIBLE"
            elif spread > 0.2:
                flag = f"UNSETTLED ({min(late):.0f}-{max(late):.0f})"
        rows.append(dict(run=name, **p, hz=med, flag=flag, readings=len(hz)))
        print(f"{name:12} bits={p['bits']} lsb={p['lsb']} dither={p['dither']} slow={p['slow']}  ->  {med} Hz  {flag}", flush=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", out)


if __name__ == "__main__":
    if "--one" in sys.argv:
        one({k: int(v) for k, v in (a.split("=") for a in sys.argv[sys.argv.index("--one") + 1:])})
    else:
        run_all(sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "/tmp/panel_sweep.csv")
