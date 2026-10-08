"""Beat tracker: tempo (BPM) from the onset envelope's autocorrelation, then a phase-locked
beat clock, so visuals can pulse exactly on the beat and keep time through quiet gaps.

    bt = BeatTracker(fps)
    bt.update(onset, now)      # call once per audio hop with the onset strength
    bt.bpm, bt.conf            # tempo (0 = unknown) and confidence 0..1
    bt.phase(now)              # 0 at a beat, rising to 1 just before the next
"""
import collections

import numpy as np


class BeatTracker:
    BPM_MIN, BPM_MAX, BPM_PRIOR = 68.0, 176.0, 120.0
    WINDOW = 8.0                 # seconds of onset history
    EVERY = 0.35                 # re-estimate this often (s)

    def __init__(self, fps):
        self.fps = float(fps)
        self.t = collections.deque(maxlen=int(self.WINDOW * fps))
        self.x = collections.deque(maxlen=int(self.WINDOW * fps))
        self.bpm = 0.0
        self.period = 0.0
        self.anchor = 0.0        # a time at which a beat happened
        self.conf = 0.0
        self._last_est = 0.0
        self._pending = []       # recent tempo candidates, to avoid octave jumps

    # ------------------------------------------------------------------
    def update(self, onset, now):
        self.t.append(now)
        self.x.append(float(onset))
        if now - self._last_est >= self.EVERY and len(self.x) > self.fps * 4:
            self._last_est = now
            try:
                self._estimate(now)
            except Exception:
                pass

    def phase(self, now):
        if self.period <= 0:
            return 0.0
        return ((now - self.anchor) / self.period) % 1.0

    # ------------------------------------------------------------------
    def _estimate(self, now):
        x = np.asarray(self.x, np.float64)
        t = np.asarray(self.t, np.float64)
        n = len(x)
        span = t[-1] - t[0]
        if span > 1.0:
            self.fps = (n - 1) / span                  # the analysis loop does not run at exactly SR/HOP
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
