"""Pi Camera capture and OpenCV silhouette extraction."""
import threading
import time
import numpy as np
import cv2
import config
import vision


AF_IDLE, AF_SCANNING, AF_FOCUSED, AF_FAILED = 0, 1, 2, 3     # libcamera AfState
FACE_EXPOSURE_TARGET = 0.50         # face mean luma (0..1) the still is metered for
FACE_EXPOSURE_RANGE = (0.5, 2.0)    # the correction is never more than this, so a bright wall cannot blow out or crush the picture
FACE_GAMMA = 2.2                    # the live frame is gamma encoded; a luma ratio is turned into a light ratio with this


def face_to_af_window(rect, crop, bounds, pad=0.15):
    """A face rectangle (x, y, w, h) normalised to the raw live frame -> an AfWindows entry (x, y, w, h) in sensor pixels.
    `crop` is the live stream's ScalerCrop (x, y, w, h) in sensor pixels (what the frame shows of the sensor), `bounds` the
    (width, height) of the sensor array. The window is grown by `pad` and clamped inside the sensor. Returns ints."""
    x, y, w, h = [float(v) for v in rect]
    x, y, w, h = x - w * pad, y - h * pad, w * (1 + 2 * pad), h * (1 + 2 * pad)
    x0, y0 = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    x1, y1 = max(0.0, min(1.0, x + w)), max(0.0, min(1.0, y + h))
    cx, cy, cw, ch = crop
    bw, bh = bounds
    sx0, sx1 = [max(0.0, min(float(bw), cx + v * cw)) for v in (x0, x1)]
    sy0, sy1 = [max(0.0, min(float(bh), cy + v * ch)) for v in (y0, y1)]
    return (int(sx0), int(sy0), max(1, int(sx1 - sx0)), max(1, int(sy1 - sy0)))


def exposure_correction(face_luma, target=FACE_EXPOSURE_TARGET, limits=FACE_EXPOSURE_RANGE, gamma=FACE_GAMMA):
    """How much more (>1) or less (<1) light the face needs to land on `target`; face_luma is the face's mean in 0..1."""
    face_luma = max(0.02, min(1.0, float(face_luma)))
    corr = (target / face_luma) ** gamma
    return max(limits[0], min(limits[1], corr))


def corrected_exposure(exp, gain, corr, period=10000.0, max_exp=33000.0, max_gain=16.0):
    """Scale exposure*gain by `corr`: the exposure time in whole mains-flicker periods (one period .. max_exp), the rest as
    analogue gain (1 .. max_gain). Returns (exposure_us int, gain float)."""
    top = max(period, (max_exp // period) * period)
    exp2 = max(period, min(top, round(float(exp) * corr / period) * period))
    gain2 = max(1.0, min(max_gain, float(exp) * float(gain) * corr / exp2))
    return int(exp2), gain2


class Camera:
    def __init__(self):
        from picamera2 import Picamera2
        self.cam = Picamera2()
        # A video configuration streams continuously (a still one re-arms for every frame: a few fps and a
        # laggy picture). queue=False hands out the newest frame, never one that waited in line.
        cfg = self.cam.create_video_configuration(
            main={"size": (config.FRAME_WIDTH, config.FRAME_HEIGHT), "format": "RGB888"},
            buffer_count=4, queue=False,
            controls={"FrameDurationLimits": (33333, 33333)},          # 30 fps
        )
        self._af = False
        self._focus_held = False
        try:        # Camera Module 3 has a motorised lens: follow the subject continuously (Fast: a person steps in front)
            if "AfMode" in self.cam.camera_controls:
                # Start with the lens held at a normal standing distance: continuous autofocus on an EMPTY scene hunts back and forth
                # (the wall's picture pumps). focus_follow(True) turns continuous AF on while somebody is in front of the mirror.
                cfg["controls"].update({"AfMode": 0, "LensPosition": float(getattr(config, "CAMERA_IDLE_LENS", 0.8))})
                self._af = True
        except Exception:
            pass
        try:        # mains lights flicker at twice the mains frequency; exposing in whole flicker periods stops the banding
            cfg["controls"].update({"AeFlickerMode": 1, "AeFlickerPeriod": int(1e6 / (2 * config.CAMERA_MAINS_HZ))})
        except Exception:
            pass
        self.cam.configure(cfg)
        self.cam.start()
        time.sleep(config.CAMERA_WARMUP_SEC)
        self._lock_light()                      # no more auto-exposure / auto-white-balance hunting: that is the biggest flicker
        self._latest, self._seq = None, 0
        self._cam_lock = threading.Lock()        # the live reader and a full-resolution still never use the camera together
        self._cond = threading.Condition()
        self._running = True
        threading.Thread(target=self._reader, daemon=True, name="camera-reader").start()
        threading.Thread(target=self._watch_light, daemon=True, name="camera-light").start()
        self._background = None
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=config.BG_HISTORY, varThreshold=config.BG_THRESHOLD, detectShadows=False
        )

    def _lock_light(self):
        """Freeze exposure, gain and white balance at what the camera chose for this room. Left on auto, they keep re-adjusting
        to every movement (a white shirt, a dark coat), and the whole picture on the wall pumps and shimmers. The exposure is
        rounded to whole mains-flicker periods so the room lights cannot band either. Re-done slowly if the room changes."""
        try:
            md = self.cam.capture_metadata()
            exp, gain = float(md["ExposureTime"]), float(md["AnalogueGain"])
            period = 1e6 / (2 * config.CAMERA_MAINS_HZ)                 # 10 000 us at 50 Hz
            exp2 = max(period, round(exp / period) * period)
            exp2 = min(exp2, 33000.0)                                   # one frame at 30 fps
            gain = min(16.0, max(1.0, gain * exp / exp2))               # keep the same brightness at the rounded exposure
            ctl = {"AeEnable": False, "AwbEnable": False, "ExposureTime": int(exp2), "AnalogueGain": gain}
            if "ColourGains" in md:
                ctl["ColourGains"] = tuple(md["ColourGains"])
            self.cam.set_controls(ctl)
            self._lock_ctl = dict(ctl)
            self._lock_mean = None
            self._locked = True
            print(f"[CAMERA] light locked: {int(exp2)} us, gain {gain:.2f}")
        except Exception as e:
            self._locked = False
            print(f"[CAMERA] could not lock exposure ({e}); staying on auto")

    def capture_still(self, size=None, face_rect=None):
        """A photo at the sensor's full resolution (config.STILL_SIZE: 4608 x 2592 on a Camera Module 3), BGR, or None if it cannot
        be taken (the caller then uses the live frame). The live stream pauses for about a second while the camera switches mode;
        the exposure is the one the camera has just metered (the flash is lit), held fixed for the exposure itself. With
        face_rect (normalised x, y, w, h in the live frame) the exposure is corrected so that face lands near mid-grey
        (face_exposure). The lens is pinned where it is (where focus_on left it) for the exposure."""
        size = tuple(size or getattr(config, "STILL_SIZE", (4608, 2592)))
        try:
            with self._cam_lock:
                md = self.cam.capture_metadata()
                exp, gain = int(md["ExposureTime"]), float(md["AnalogueGain"])
                if face_rect is not None:
                    try:
                        fx = self.face_exposure(face_rect, exp, gain)
                        if fx:
                            exp, gain = fx
                    except Exception as e:
                        print(f"[CAMERA] face exposure skipped ({e})", flush=True)
                ctl = {"AeEnable": False, "AwbEnable": False, "ExposureTime": exp, "AnalogueGain": gain}
                if "ColourGains" in md:
                    ctl["ColourGains"] = tuple(md["ColourGains"])
                if self._af and md.get("LensPosition") is not None:
                    ctl.update({"AfMode": 0, "LensPosition": float(md["LensPosition"])})     # Manual: no refocusing during the exposure
                cfg = self.cam.create_still_configuration(main={"size": size, "format": "RGB888"}, buffer_count=1, controls=ctl)
                arr = self.cam.switch_mode_and_capture_array(cfg, "main")
            frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            print(f"[CAMERA] still {frame.shape[1]}x{frame.shape[0]}", flush=True)
            return frame
        except Exception as e:
            print(f"[CAMERA] full-resolution still failed ({e}); using the live frame", flush=True)
            return None

    # ---- autofocus -------------------------------------------------------------------------------------------------------
    def has_autofocus(self):
        return bool(getattr(self, "_af", False))

    def _live_crop(self, md=None):
        """The part of the sensor the live frame shows: ScalerCrop from the frame metadata (x, y, w, h in sensor pixels). The
        live frame maps linearly onto it. (On this camera it is a 4:3 window, 2304 x 1728 of the 4608 x 2592 array around the
        middle, not the whole width.)"""
        md = md or self.cam.capture_metadata()
        crop = md.get("ScalerCrop")
        if crop:
            return tuple(crop)
        w, h = self._sensor_size()
        return (0, 0, w, h)

    def _sensor_size(self):
        try:
            return tuple(self.cam.camera_properties["PixelArraySize"])
        except Exception:
            return tuple(getattr(config, "STILL_SIZE", (4608, 2592)))

    def af_state(self):
        """(AfState, LensPosition) from the newest frame metadata, for logs."""
        md = self.cam.capture_metadata()
        return md.get("AfState"), md.get("LensPosition")

    def start_focus(self, face_rect):
        """Aim the autofocus metering window at a face (x, y, w, h normalised to the raw live frame) and start one AF cycle.
        Returns False if there is no autofocus or it could not be started."""
        if not self._af:
            return False
        try:
            md = self.cam.capture_metadata()
            win = face_to_af_window(face_rect, self._live_crop(md), self._sensor_size())
            self.cam.set_controls({"AfMode": 1, "AfMetering": 1, "AfWindows": [win]})     # Auto, Windows
            self.cam.set_controls({"AfTrigger": 0})                                       # Start
            self._focus_held = True
            self._focus_t0 = time.monotonic()
            self._focus_seen_scan = False
            print(f"[CAMERA] AF window {win}", flush=True)
            return True
        except Exception as e:
            print(f"[CAMERA] could not start focus ({e})", flush=True)
            return False

    def focus_done(self):
        """None while the AF cycle is running, True when it reports focused, False when it failed."""
        md = self.cam.capture_metadata()
        st = md.get("AfState")
        if st == AF_SCANNING:
            self._focus_seen_scan = True
        if st in (AF_FOCUSED, AF_FAILED) and (self._focus_seen_scan or time.monotonic() - self._focus_t0 > 0.25):
            print(f"[CAMERA] AF {'focused' if st == AF_FOCUSED else 'failed'} after {time.monotonic() - self._focus_t0:.2f} s, "
                  f"lens {md.get('LensPosition')}", flush=True)
            return st == AF_FOCUSED
        return None

    def wait_focus(self, timeout=1.2):
        """Wait for the AF cycle started by start_focus (at most `timeout` s after it started); True if it reports focused."""
        t_end = getattr(self, "_focus_t0", time.monotonic()) + timeout
        ok = False
        try:
            while time.monotonic() < t_end:
                r = self.focus_done()
                if r is not None:
                    ok = r
                    break
            else:
                st, lens = self.af_state()
                print(f"[CAMERA] AF still scanning after {timeout:.1f} s (state {st}, lens {lens}): giving up", flush=True)
        except Exception as e:
            print(f"[CAMERA] focus wait failed ({e})", flush=True)
        if not ok:
            # a cycle that did not finish leaves the lens mid-scan: cancel it and let continuous AF carry on from here
            self.focus_release()
        return ok

    def focus_on(self, face_rect, timeout=1.2):
        """Focus on a face and keep the lens there. True if the camera reports focused within `timeout` seconds."""
        return bool(self.start_focus(face_rect) and self.wait_focus(timeout))

    def focus_hold(self):
        """Keep the lens exactly where it is now (manual focus at the current position)."""
        if not self._af:
            return
        try:
            md = self.cam.capture_metadata()
            self.cam.set_controls({"AfMode": 0, "LensPosition": float(md["LensPosition"])})
            self._focus_held = True
        except Exception:
            pass

    def focus_release(self):
        """Back to following the subject continuously (when somebody is there), over the whole picture; else the lens rests."""
        if not self._af:
            return
        try:
            if getattr(self, "_follow", False):
                self.cam.set_controls({"AfMetering": 0, "AfMode": 2, "AfRange": 0, "AfSpeed": 1})
            else:
                self.cam.set_controls({"AfMetering": 0, "AfMode": 0, "LensPosition": float(getattr(config, "CAMERA_IDLE_LENS", 0.8))})
        except Exception:
            pass
        self._focus_held = False

    def focus_follow(self, on: bool):
        """Continuous autofocus only while somebody is in front of the mirror. With nobody there the lens rests at a normal
        distance instead of hunting across an empty room."""
        if not self._af or on == getattr(self, "_follow", False):
            return
        self._follow = on
        if getattr(self, "_focus_held", False):
            return                                   # a photo's own focus cycle is running: it calls focus_release when it is done
        try:
            if on:
                self.cam.set_controls({"AfMetering": 0, "AfMode": 2, "AfRange": 0, "AfSpeed": 1})
            else:
                self.cam.set_controls({"AfMode": 0, "LensPosition": float(getattr(config, "CAMERA_IDLE_LENS", 0.8))})
            print(f"[CAMERA] autofocus {'following' if on else 'resting'}", flush=True)
        except Exception as e:
            print(f"[CAMERA] focus_follow failed ({e})", flush=True)

    # ---- face exposure ---------------------------------------------------------------------------------------------------
    def face_luma(self, face_rect):
        """Mean luma (0..1) of the middle of the face rectangle in the newest live frame, or None."""
        frame = self._latest
        if frame is None:
            return None
        H, W = frame.shape[:2]
        x, y, w, h = face_rect
        x, y, w, h = x + w * 0.2, y + h * 0.2, w * 0.6, h * 0.6          # the inner part: no hair, no background
        x0, x1 = int(max(0, min(W - 1, x * W))), int(max(1, min(W, (x + w) * W)))
        y0, y1 = int(max(0, min(H - 1, y * H))), int(max(1, min(H, (y + h) * H)))
        if x1 <= x0 or y1 <= y0:
            return None
        return float(cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).mean()) / 255.0

    def face_exposure(self, face_rect, exp, gain):
        """(exposure_us, gain) for the still so the face lands near FACE_EXPOSURE_TARGET, from the exposure/gain `exp`/`gain`
        the live frame was taken with. None if the face cannot be measured (then nothing changes)."""
        luma = self.face_luma(face_rect)
        if luma is None:
            return None
        corr = exposure_correction(luma)
        period = 1e6 / (2 * config.CAMERA_MAINS_HZ)
        exp2, gain2 = corrected_exposure(exp, gain, corr, period)
        print(f"[CAMERA] face luma {luma:.2f} -> x{corr:.2f}: {exp} us gain {gain:.2f} -> {exp2} us gain {gain2:.2f}", flush=True)
        return exp2, gain2

    def light_auto(self):
        """For the photo flash: let the camera meter freely while the screen edge lights the person."""
        self._unlock_light()

    def light_restore(self):
        """After the flash: back to the exposure and white balance locked before it."""
        ctl = getattr(self, "_lock_ctl", None)
        try:
            if ctl:
                self.cam.set_controls(ctl)
        except Exception:
            pass

    def _unlock_light(self):
        try:
            self.cam.set_controls({"AeEnable": True, "AwbEnable": True})
        except Exception:
            pass

    def _watch_light(self):
        """Every 20 s: if the picture has been much brighter or darker than when the light was locked for a full minute (the sun
        went down, the lamps came on), let the camera choose again for two seconds and lock the new values."""
        away = 0
        while self._running:
            time.sleep(20)
            if not getattr(self, "_locked", False) or self._latest is None:
                continue
            m = float(self._latest[::8, ::8].mean()) + 1.0
            if self._lock_mean is None:
                self._lock_mean = m
                continue
            away = away + 1 if abs(m / self._lock_mean - 1.0) > 0.35 else 0
            if away >= 3:
                away = 0
                self._unlock_light()
                time.sleep(2.5)
                self._lock_light()
                self._lock_mean = float(self._latest[::8, ::8].mean()) + 1.0

    def _reader(self):
        """Keeps only the newest frame, so a slow consumer never sees an old picture."""
        while self._running:
            try:
                with self._cam_lock:
                    arr = self.cam.capture_array()
                frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            except Exception:
                time.sleep(0.05)
                continue
            with self._cond:
                self._latest, self._seq = frame, self._seq + 1
                self._cond.notify_all()

    def wait_frame(self, last_seq: int, timeout: float = 0.5):
        """Block until a frame newer than last_seq arrives. Returns (seq, portrait crop), or (last_seq, None)."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq != last_seq, timeout)
            if self._seq == last_seq or self._latest is None:
                return last_seq, None
            return self._seq, vision.crop_to_aspect(self._latest, config.CAMERA_ASPECT)

    def capture_frame(self, raw: bool = False) -> np.ndarray:
        """raw=True: the full-width frame (for the smart portrait crop of photos).
        Default: centred portrait crop (cheap; used by the live silhouette)."""
        with self._cond:
            if self._latest is None:
                self._cond.wait_for(lambda: self._latest is not None, 2.0)
            frame = self._latest
        if frame is None:
            raise RuntimeError("camera has no frame")
        return frame.copy() if raw else vision.crop_to_aspect(frame, config.CAMERA_ASPECT)

    def get_background_frame(self) -> np.ndarray:
        self._background_raw = self.capture_frame(raw=True)      # for the motion crop fallback
        self._background = vision.crop_to_aspect(self._background_raw, config.CAMERA_ASPECT)
        # prime the MOG2 subtractor
        for _ in range(5):
            self._subtractor.apply(self._background)
        return self._background

    def extract_silhouette(self, frame: np.ndarray, background: np.ndarray = None) -> np.ndarray:
        bg = background if background is not None else self._background
        return vision.silhouette_mask(frame, bg, self._subtractor)

    def shutdown(self) -> None:
        self._running = False
        try:
            self.cam.stop()
        except Exception:
            pass
