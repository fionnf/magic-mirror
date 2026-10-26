"""Pi health monitor — CPU, temperature, throttling/undervoltage, memory and
display frame stats. Stdlib only; every reading degrades to '-' off a Pi.

As a library (used by display_test.py):
    mon = PiMonitor(log_path="panel_setup/monitor.csv"); mon.start()
    mon.note_frame(work_seconds, est_amps, sent)   # once per frame drawn
    mon.stop()

Standalone (second SSH session while another test runs):
    python3 panel_setup/monitor.py [--interval 2] [--csv out.csv]
Standalone only sees the Pi itself: frame fields (fps, work, amps) print as '-'
because frames are drawn in the other process.

Undervoltage / throttle flags come from `vcgencmd get_throttled`. Bits 0-3 are
the state right now; bits 16-19 latch from boot until the next reboot, so they
are reported once at start and then only when a new event latches. Undervoltage
on a Pi that shares a supply with the panels means the Pi's own 5 V is sagging
— give the Pi its own supply (shared GND only).
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
_NOW_MASK = 0xF
_LATCHED_MASK = 0xF0000
_NOW_WARN = {
    0: "UNDERVOLTAGE now — Pi's 5 V is sagging; check PSU wiring/leads",
    1: "CPU frequency capped — refresh rate/fps will suffer",
    2: "CPU throttled — refresh rate/fps will suffer",
    3: "soft temperature limit active — CPU clocks reduced, add cooling",
}


def flag_names(raw, mask=0xFFFFFFFF):
    return [n for b, n in _THROTTLE_BITS.items() if raw & mask & (1 << b)]


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
    return raw, flag_names(raw)


class PiMonitor:
    """Background health readout. frames=False (standalone) hides the frame
    fields, which only mean something when note_frame() is being called."""

    HEADER = ["time", "t_s", "cpu_pct", "hottest_core_pct", "temp_c", "mhz",
              "mem_pct", "fps_sent", "fps_held", "work_ms_avg", "work_ms_max",
              "amps_out", "amps_peak", "amps_requested", "throttled_hex"]

    def __init__(self, interval=2.0, log_path=None, quiet=False, frames=True):
        self.interval = interval
        self.log_path = log_path
        self.quiet = quiet
        self.frames = frames
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._reset_frames()
        self._amps = self._amps_req = 0.0
        self._now_bits = 0          # throttle 'now' bits seen on the last tick
        self._latched_seen = 0      # latched bits already reported
        self._warned = set()

    def _reset_frames(self):
        self._sent = self._held = 0
        self._work_s = self._work_max = 0.0
        self._amps_peak = 0.0

    def note_frame(self, work_seconds, est_amps=0.0, sent=True, amps_requested=None):
        """work_seconds: Python cost of the frame (exclude any vsync wait).
        est_amps: estimate after power limiting. sent=False: frame was identical
        and nothing went to the panels (counted as held, not in fps/work)."""
        with self._lock:
            if sent:
                self._sent += 1
                self._work_s += work_seconds
                self._work_max = max(self._work_max, work_seconds)
            else:
                self._held += 1
            self._amps = est_amps
            self._amps_req = est_amps if amps_requested is None else amps_requested
            self._amps_peak = max(self._amps_peak, est_amps)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="pi-monitor")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 3)

    def _open_log(self):
        """Append to the CSV so earlier runs survive; a file with an older
        column layout is moved aside to <name>.old first."""
        try:
            if os.path.exists(self.log_path):
                with open(self.log_path, newline="") as f:
                    first = next(csv.reader(f), None)
                if first and first != self.HEADER:
                    os.replace(self.log_path, self.log_path + ".old")
            fh = open(self.log_path, "a", newline="")
        except OSError as e:
            print(f"[PI] !! cannot write {self.log_path} ({e}) — readout only, "
                  f"no CSV", flush=True)
            return None, None
        writer = csv.writer(fh)
        if fh.tell() == 0:
            writer.writerow(self.HEADER)
        return fh, writer

    def _run(self):
        fh, writer = self._open_log() if self.log_path else (None, None)
        raw, _ = throttle_flags()
        if raw is not None:
            self._latched_seen = raw & _LATCHED_MASK
            if self._latched_seen and not self.quiet:
                print(f"[PI] since boot (latched until reboot): "
                      f"{','.join(flag_names(raw, _LATCHED_MASK))}", flush=True)
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
                sent, held, ws, wm = (self._sent, self._held,
                                      self._work_s, self._work_max)
                amps, amps_req, peak = self._amps, self._amps_req, self._amps_peak
                self._reset_frames()
            dt = now - t_prev
            t_prev = now
            fps = sent / dt if dt > 0 else 0.0
            fps_held = held / dt if dt > 0 else 0.0
            avg_ms = 1000 * ws / sent if sent else 0.0

            temp, mhz, mem = temperature(), cpu_mhz(), memory_used_pct()
            raw, _ = throttle_flags()
            new_events, fresh = [], 0
            if raw is not None:
                fresh = raw & _LATCHED_MASK & ~self._latched_seen
                self._latched_seen |= fresh
                new_events = flag_names(fresh)
            now_flags = flag_names(raw, _NOW_MASK) if raw is not None else []

            if writer:
                fr = self.frames
                writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"), f"{now - t0:.0f}",
                    _f(overall), _f(hottest), _f(temp), mhz or "", _f(mem),
                    f"{fps:.1f}" if fr else "", f"{fps_held:.1f}" if fr else "",
                    f"{avg_ms:.1f}" if fr else "", f"{1000 * wm:.1f}" if fr else "",
                    f"{amps:.1f}" if fr else "", f"{peak:.1f}" if fr else "",
                    f"{amps_req:.1f}" if fr else "",
                    f"{raw:#x}" if raw is not None else ""])
                fh.flush()
            if not self.quiet:
                if self.frames:
                    held_txt = f" +{fps_held:.0f} held" if held else ""
                    limit_txt = (f", wants {amps_req:.1f}"
                                 if amps_req > amps + 0.05 else "")
                    frame_txt = (f"{fps:5.1f} fps{held_txt} work {avg_ms:.1f}ms "
                                 f"(max {1000 * wm:.0f}) | ~{amps:.1f}A "
                                 f"(peak {peak:.1f}{limit_txt})")
                else:
                    frame_txt = "fps - | amps -"
                status = ",".join(now_flags + [f"NEW {e}" for e in new_events])
                print(f"[PI] cpu {_f(overall):>5}% (worst core {_f(hottest)}%) "
                      f"| {_f(temp)}°C {mhz or '-'}MHz | mem {_f(mem)}% "
                      f"| {frame_txt} | {status or 'ok'}", flush=True)
            self._warn(temp, raw, fresh)
        if fh:
            fh.close()

    def _warn(self, temp, raw, fresh):
        def once(key, msg):
            if key not in self._warned:
                self._warned.add(key)
                print(f"[PI] !! {msg}", flush=True)
        if temp is not None and temp >= TEMP_CRIT_C:
            once("tc", f"temperature {temp:.0f}°C — throttling imminent, add cooling")
        elif temp is not None and temp >= TEMP_WARN_C:
            once("tw", f"temperature {temp:.0f}°C is high")
        if raw is not None:
            # 'now' conditions warn every time they switch on, not once per run
            bits = raw & _NOW_MASK
            for b, msg in _NOW_WARN.items():
                if bits & (1 << b) and not self._now_bits & (1 << b):
                    print(f"[PI] !! {msg}", flush=True)
            self._now_bits = bits
            # latched since the last tick while the 'now' bit is already off:
            # it happened and cleared between two readings
            for b in range(16, 20):
                if fresh & (1 << b) and not bits & (1 << (b - 16)):
                    print(f"[PI] !! {_THROTTLE_BITS[b]} since the last reading "
                          f"(brief event)", flush=True)


def _f(v):
    return "-" if v is None else f"{v:.0f}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    m = PiMonitor(a.interval, a.csv, frames=False)
    m.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        m.stop()
