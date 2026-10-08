"""Beat tracker: tempo (BPM) from the onset envelope's autocorrelation, then a phase-locked
beat clock, so visuals can pulse exactly on the beat and keep time through quiet gaps.

    bt = BeatTracker(fps)
    bt.update(onset, now)      # call once per audio hop with the onset strength
    bt.bpm, bt.conf            # tempo (0 = unknown) and confidence 0..1
    bt.phase(now)              # 0 at a beat, rising to 1 just before the next
"""
import collections
import math

import numpy as np


class BeatTracker:
    BPM_MIN, BPM_MAX, BPM_PRIOR = 68.0, 176.0, 120.0
    WINDOW = 8.0                 # seconds of onset history
    EVERY = 0.35                 # re-estimate this often (s)

    def __init__(self, fps):
        self.fps = float(fps)
        self.fps0 = float(fps)          # nominal analysis rate: the onset series is resampled onto it
        self.t = collections.deque(maxlen=int(self.WINDOW * fps))
        self.x = collections.deque(maxlen=int(self.WINDOW * fps))
        self.bpm = 0.0
        self.period = 0.0
        self.anchor = 0.0        # a time at which a beat happened
        self.conf = 0.0
        self._last_est = 0.0
        self._pending = []       # recent tempo candidates, to avoid octave jumps
        self.bar_acc = np.zeros(4)   # onset energy landing on each beat of the bar -> which one is "1"
        self.downbeat = 0

    # ------------------------------------------------------------------
    def update(self, onset, now):
        self.t.append(now)
        self.x.append(float(onset))
        if self.period > 0 and self.anchor:
            rel = (now - self.anchor) / self.period
            near = rel - round(rel)
            w = math.exp(-(near / 0.12) ** 2)          # only onsets close to a beat count
            self.bar_acc *= 0.9995                     # ~25 s memory
            self.bar_acc[int(round(rel)) % 4] += onset * w
            best = int(np.argmax(self.bar_acc))
            if best != self.downbeat and self.bar_acc[best] > 1.3 * self.bar_acc[self.downbeat]:
                self.downbeat = best
        if now - self._last_est >= self.EVERY and len(self.x) > self.fps * 4:
            self._last_est = now
            try:
                self._estimate(now)
            except Exception:
                pass

    def beat_index(self, now):
        return int(round((now - self.anchor) / self.period)) if self.period > 0 else 0

    def bar_pos(self, now):
        """0 on the downbeat, 1..3 for the other beats of a 4/4 bar."""
        return (self.beat_index(now) - self.downbeat) % 4

    def phase(self, now):
        if self.period <= 0:
            return 0.0
        return ((now - self.anchor) / self.period) % 1.0

    # ------------------------------------------------------------------
    def _estimate(self, now):
        xr = np.asarray(self.x, np.float64)
        tr = np.asarray(self.t, np.float64)
        span = tr[-1] - tr[0]
        if span < 2.0:
            return
        # the analysis loop's hops are irregular when the renderer is busy: put the onsets on a
        # uniform grid first, or the autocorrelation smears and the tempo wanders
        self.fps = self.fps0
        t = np.arange(tr[0], tr[-1], 1.0 / self.fps)
        x = np.interp(t, tr, xr)
        n = len(x)
        x = x - x.mean()
        if x.std() < 1e-6:
            self.conf *= 0.8
            return
        f = np.fft.rfft(x, 2 * n)
        ac = np.fft.irfft(f * np.conj(f))[:n]
        ac /= ac[0] + 1e-12
        lo = int(self.fps * 60.0 / self.BPM_MAX)
        hi = min(n // 2 - 1, int(self.fps * 60.0 / self.BPM_MIN))
        lags = np.arange(lo, hi)
        bpms = 60.0 * self.fps / lags
        # a tempo is supported by its multiples too (2x, 3x, 4x lag), and mildly favoured near 120
        score = ac[lags].copy()
        for m, w in ((2, 0.5), (3, 0.25), (4, 0.25)):
            idx = lags * m
            ok = idx < n
            score[ok] += w * ac[idx[ok]]
        score *= np.exp(-0.5 * (np.log2(bpms / self.BPM_PRIOR) / 0.7) ** 2)
        k = int(np.argmax(score))
        lag = lags[k]
        if 0 < k < len(lags) - 1:                       # parabolic refinement
            a, b, c = score[k - 1], score[k], score[k + 1]
            d = (a - c) / (2 * (a - 2 * b + c) + 1e-12)
            lag = lag + max(-0.5, min(0.5, d))
        bpm = 60.0 * self.fps / lag
        conf = float(np.clip(ac[int(round(lag))] * 1.6, 0.0, 1.0))
        # tempo changes need to be confirmed; small drifts are followed smoothly
        if self.bpm > 0 and abs(bpm - self.bpm) / self.bpm < 0.04:
            self.bpm = 0.75 * self.bpm + 0.25 * bpm
            self._pending = []
        elif self.bpm <= 0:
            self.bpm = bpm
        else:
            self._pending = (self._pending + [bpm])[-3:]
            if len(self._pending) >= 3 and max(self._pending) / min(self._pending) < 1.05 and conf > 0.25:
                self.bpm = float(np.mean(self._pending))
                self._pending = []
        self.conf = 0.7 * self.conf + 0.3 * conf if self.conf else conf
        self.period = 60.0 / self.bpm
        # phase: circular mean of onset times modulo the period, weighted by onset strength
        u = 2 * np.pi * ((t - now) % self.period) / self.period
        w = np.maximum(x, 0) ** 2
        # newer onsets count more
        w = w * np.linspace(0.4, 1.0, n)
        c, s = (w * np.cos(u)).sum(), (w * np.sin(u)).sum()
        if c == 0 and s == 0:
            return
        b = (np.arctan2(s, c) % (2 * np.pi)) / (2 * np.pi) * self.period      # beat at now + b (mod period)
        new_anchor = now + b
        if self.anchor == 0.0:
            self.anchor = new_anchor
        else:                                           # phase-locked loop: nudge towards the new estimate
            e = (new_anchor - self.anchor + self.period / 2) % self.period - self.period / 2
            self.anchor += 0.35 * e
