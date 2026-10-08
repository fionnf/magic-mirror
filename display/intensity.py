"""Party level: how much of a party the room is, 0 (quiet evening) .. 1 (dance floor).

One slow, continuous number the VJ engine slides every parameter along, estimated from what the
microphone can measure:

  loud   absolute loudness (dBFS, slow)      - the gate: a quiet room is never a party
  beat   how locked/regular the beat is      - four-on-the-floor vs. a wandering ballad
  fast   tempo                               - 85 bpm .. 135 bpm
  busy   onsets per second                   - dense percussion vs. pads
  bass   share of energy below 120 Hz        - club music is bass-heavy
  night  a small bump late in the evening

level = loud * (0.45 + 0.55 * drive) where drive mixes beat/fast/busy/bass. It rises in ~10 s and
falls in ~45 s (hysteresis), and only drifts down slowly in silence, so a gap between songs does
not drop the party. The app's sensitivity slider shifts the loudness thresholds (+/- 8 dB).
"""
import math
import time


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _ema(prev, new, dt, tc):
    a = 1.0 - math.exp(-dt / tc) if tc > 0 else 1.0
    return prev + (new - prev) * a


LABELS = ((0.2, "quiet"), (0.4, "background music"), (0.6, "lively"), (0.8, "party"), (9.9, "rave"))


class Intensity:
    QUIET_DB, LOUD_DB = -50.0, -22.0        # what counts as quiet / loud at sensitivity 50

    def __init__(self):
        self.level = 0.0
        self.parts = {}
        self.label = "quiet"
        self.last = None

    def update(self, f, now=None, sensitivity=50):
        now = now if now is not None else time.time()
        dt = 0.033 if self.last is None else _clamp(now - self.last, 0.0, 0.5)
        self.last = now
        shift = (float(sensitivity) - 50.0) / 50.0 * 8.0            # dB easier at high sensitivity
        db = float(f.get("db", -80.0))
        silent = bool(f.get("silent", True))
        loud = _clamp((db - (self.QUIET_DB - shift)) / (self.LOUD_DB - self.QUIET_DB))
        bconf, bpm = float(f.get("bconf", 0.0)), float(f.get("bpm", 0.0))
        beat = _clamp((bconf - 0.25) / 0.5)
        fast = _clamp((bpm - 85.0) / 50.0) if bconf > 0.3 else 0.25
        busy = _clamp(float(f.get("busy", 0.0)) / 6.0)
        bass = _clamp((float(f.get("bass_share", 0.0)) - 0.15) / 0.25)
        h = time.localtime(now).tm_hour
        night = 1.0 if (h >= 21 or h < 4) else 0.0
        drive = 0.4 * beat + 0.25 * fast + 0.2 * busy + 0.15 * bass
        raw = 0.0 if silent else _clamp(loud * (0.45 + 0.55 * drive) + 0.06 * night)
        tc = 90.0 if silent else (10.0 if raw > self.level else 45.0)
        self.level = _ema(self.level, raw, dt, tc)
        self.parts = {"db": round(db, 1), "loud": round(loud, 2), "beat": round(beat, 2),
                      "fast": round(fast, 2), "busy": round(busy, 2), "bass": round(bass, 2),
                      "drive": round(drive, 2), "raw": round(raw, 2)}
        self.label = next(name for top, name in LABELS if self.level < top)
        return self.level
