"""Pi health monitor — CPU, temperature, throttling/undervoltage, memory and
display frame stats. Stdlib only; every reading degrades to '-' off a Pi.

As a library (used by display_test.py):
    mon = PiMonitor(log_path="panel_setup/monitor.csv"); mon.start()
    mon.note_frame(draw_seconds, est_amps)     # call once per drawn frame
    mon.stop()

Standalone (second SSH session while another test runs):
    python3 panel_setup/monitor.py [--interval 2] [--csv out.csv]

Undervoltage / throttle flags come from `vcgencmd get_throttled`. Undervoltage
on a Pi that shares a supply with the panels means the Pi's own 5 V is sagging
— power the Pi separately from the panel PSU rail's drop (shared GND only).
"""
import argparse
import csv
import os
import subprocess
import threading
import time

TEMP_WARN_C = 75.0
TEMP_CRIT_C = 80.0

_THROTTLE_BITS = {
    0: "UNDERVOLTAGE", 1: "FREQ-CAPPED", 2: "THROTTLED", 3: "TEMP-LIMIT",
    16: "undervoltage-occurred", 17: "freq-cap-occurred",
    18: "throttle-occurred", 19: "temp-limit-occurred",
}


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _vcgencmd(*args):
    try:
        return subprocess.run(["vcgencmd", *args], capture_output=True,
                              text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def cpu_times():
    """Return {core: (busy, total)} from /proc/stat ('cpu' = overall)."""
    out = {}
    txt = _read("/proc/stat")
    if not txt:
        return out
    for line in txt.splitlines():
        if line.startswith("cpu"):
            p = line.split()
            v = [int(x) for x in p[1:9]]
            idle = v[3] + v[4]
            out[p[0]] = (sum(v) - idle, sum(v))
    return out


def temperature():
    t = _read("/sys/class/thermal/thermal_zone0/temp")
    return int(t) / 1000.0 if t and t.lstrip("-").isdigit() else None


def cpu_mhz():
    f = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    return int(f) // 1000 if f and f.isdigit() else None


def memory_used_pct():
    txt = _read("/proc/meminfo")
    if not txt:
        return None
    m = {l.split(":")[0]: int(l.split()[1]) for l in txt.splitlines() if ":" in l}
    if "MemTotal" in m and "MemAvailable" in m:
        return 100.0 * (1 - m["MemAvailable"] / m["MemTotal"])


def throttle_flags():
    """(raw_int | None, [flag names])"""
    out = _vcgencmd("get_throttled")
    if not out or "=" not in out:
        return None, []
    try:
        raw = int(out.split("=")[1], 16)
    except ValueError:
        return None, []
    return raw, [n for b, n in _THROTTLE_BITS.items() if raw & (1 << b)]


class PiMonitor:
    def __init__(self, interval=2.0, log_path=None, quiet=False):
        self.interval = interval
        self.log_path = log_path
        self.quiet = quiet
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._frames = 0
        self._draw_s = 0.0
        self._draw_max = 0.0
        self._amps = 0.0
        self._warned = set()

    def note_frame(self, draw_seconds, est_amps=0.0):
        with self._lock:
            self._frames += 1
            self._draw_s += draw_seconds
            self._draw_max = max(self._draw_max, draw_seconds)
            self._amps = est_amps

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="pi-monitor")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 1)

    def _run(self):
        writer = fh = None
        if self.log_path:
            fh = open(self.log_path, "w", newline="")
            writer = csv.writer(fh)
            writer.writerow(["t_s", "cpu_pct", "hottest_core_pct", "temp_c",
                             "mhz", "mem_pct", "fps", "draw_ms_avg",
                             "draw_ms_max", "est_amps", "throttled_hex"])
        prev, t_prev, t0 = cpu_times(), time.monotonic(), time.monotonic()
        while not self._stop.wait(self.interval):
            now = time.monotonic()
            cur = cpu_times()
            pct = {}
            for k, (b, t) in cur.items():
                pb, pt = prev.get(k, (b, t))
                pct[k] = 100.0 * (b - pb) / (t - pt) if t > pt else 0.0
            prev = cur
            overall = pct.get("cpu")
            cores = [v for k, v in pct.items() if k != "cpu"]
            hottest = max(cores) if cores else None

            with self._lock:
                n, ds, dm, amps = (self._frames, self._draw_s,
                                   self._draw_max, self._amps)
                self._frames, self._draw_s, self._draw_max = 0, 0.0, 0.0
            dt = now - t_prev
            t_prev = now
            fps = n / dt if dt > 0 else 0.0
            avg_ms = 1000 * ds / n if n else 0.0

            temp, mhz, mem = temperature(), cpu_mhz(), memory_used_pct()
            raw, flags = throttle_flags()

            if writer:
                writer.writerow([f"{now - t0:.0f}", _f(overall), _f(hottest),
                                 _f(temp), mhz or "", _f(mem), f"{fps:.1f}",
                                 f"{avg_ms:.1f}", f"{1000 * dm:.1f}",
                                 f"{amps:.1f}",
                                 f"{raw:#x}" if raw is not None else ""])
                fh.flush()
            if not self.quiet:
                print(f"[PI] cpu {_f(overall):>5}% (worst core {_f(hottest)}%) "
                      f"| {_f(temp)}°C {mhz or '-'}MHz | mem {_f(mem)}% "
                      f"| {fps:5.1f} fps draw {avg_ms:.1f}ms (max {1000 * dm:.0f}) "
                      f"| ~{amps:.1f}A | {','.join(flags) or 'ok'}", flush=True)
            self._warn(temp, flags)
        if fh:
            fh.close()

    def _warn(self, temp, flags):
        def once(key, msg):
            if key not in self._warned:
                self._warned.add(key)
                print(f"[PI] !! {msg}", flush=True)
        if temp is not None and temp >= TEMP_CRIT_C:
            once("tc", f"temperature {temp:.0f}°C — throttling imminent, add cooling")
        elif temp is not None and temp >= TEMP_WARN_C:
            once("tw", f"temperature {temp:.0f}°C is high")
        if "UNDERVOLTAGE" in flags:
            once("uv", "UNDERVOLTAGE now — Pi's 5 V is sagging; check PSU wiring/leads")
        if "THROTTLED" in flags or "FREQ-CAPPED" in flags:
            once("th", "CPU throttled — refresh rate/fps will suffer")


def _f(v):
    return "-" if v is None else f"{v:.0f}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    m = PiMonitor(a.interval, a.csv)
    m.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        m.stop()
