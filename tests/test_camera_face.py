"""Face focus / face exposure: the maths (no camera needed) and the capture path with stub cameras.
Run: python tests/test_camera_face.py   (or pytest)"""
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config  # noqa: E402


def _camera_funcs():
    """camera.py imports picamera2 only inside Camera(), so its helpers import anywhere."""
    import camera
    return camera


def test_af_window_maps_linearly_onto_the_live_crop():
    cam = _camera_funcs()
    crop, bounds = (1168, 456, 2304, 1728), (4608, 2592)       # what the Camera Module 3 live stream shows
    x, y, w, h = cam.face_to_af_window((0.25, 0.25, 0.5, 0.5), crop, bounds, pad=0.0)
    assert (x, y, w, h) == (1168 + 576, 456 + 432, 1152, 864)
    x, y, w, h = cam.face_to_af_window((0.0, 0.0, 1.0, 1.0), crop, bounds, pad=0.0)
    assert (x, y, w, h) == (1168, 456, 2304, 1728)


def test_af_window_is_clamped_to_the_sensor():
    cam = _camera_funcs()
    bounds = (4608, 2592)
    for rect in [(-0.2, -0.2, 0.5, 0.5), (0.9, 0.9, 0.5, 0.5), (0.4, 0.4, 3.0, 3.0), (1.5, 1.5, 0.1, 0.1)]:
        x, y, w, h = cam.face_to_af_window(rect, (0, 0, 4608, 2592), bounds)
        assert 0 <= x and 0 <= y and w >= 1 and h >= 1
        assert x + w <= bounds[0] + 1 and y + h <= bounds[1] + 1, (rect, (x, y, w, h))


def test_exposure_correction_targets_and_clamps():
    cam = _camera_funcs()
    assert abs(cam.exposure_correction(0.5) - 1.0) < 1e-6
    assert cam.exposure_correction(0.05) == 2.0            # a dark face: never more than 2x
    assert cam.exposure_correction(0.0) == 2.0
    assert cam.exposure_correction(0.95) == 0.5            # a bright one: never less than 0.5x
    assert 1.0 < cam.exposure_correction(0.4) < 2.0
    assert 0.5 < cam.exposure_correction(0.6) < 1.0


def test_corrected_exposure_in_flicker_periods_and_gain_range():
    cam = _camera_funcs()
    for exp in (10000, 20000, 30000, 7000):
        for gain in (1.0, 2.5, 16.0):
            for corr in (0.5, 0.7, 1.0, 1.4, 2.0):
                e, g = cam.corrected_exposure(exp, gain, corr, period=10000.0)
                assert e in (10000, 20000, 30000), (exp, gain, corr, e)
                assert 1.0 <= g <= 16.0
                want, got = exp * gain * corr, e * g          # the light is as asked unless a limit bites
                assert got <= want * 1.0001 or g == 1.0 or e == 10000
    e, g = cam.corrected_exposure(20000, 2.0, 2.0, 10000.0)      # 80000 units of light: 40 ms is too long, so 30 ms at gain 2.67
    assert e == 30000 and abs(g - 80000 / 30000) < 0.01
    e, g = cam.corrected_exposure(30000, 16.0, 2.0, 10000.0)     # already at the ceiling: cannot brighten
    assert e == 30000 and g == 16.0
    e, g = cam.corrected_exposure(10000, 1.0, 0.5, 10000.0)      # already at the floor: cannot darken
    assert e == 10000 and g == 1.0


def test_focus_rect_picks_the_big_central_face():
    import smartcrop
    row = lambda x, y, w, h: np.array([x, y, w, h] + [0] * 10 + [0.9], np.float32)
    assert smartcrop.focus_rect([], 640, 480) is None
    assert smartcrop.focus_rect([row(10, 10, 30, 30)], 640, 480) is None          # too small
    small_edge, big_mid = row(0, 0, 60, 60), row(280, 200, 80, 80)
    r = smartcrop.focus_rect([small_edge, big_mid], 640, 480)
    assert np.allclose(r, (280 / 640, 200 / 480, 80 / 640, 80 / 480))
    r = smartcrop.focus_rect([row(600, 400, 100, 100)], 640, 480)                 # runs off the frame: clipped
    assert r[0] + r[2] <= 1.0 and r[1] + r[3] <= 1.0


# ---- the capture path with stub cameras -----------------------------------------------------------------------------------
class _Matrix:
    def draw(self, img, frame_fraction=1):
        time.sleep(0.005)
        return True


class _Strip:
    def set_mode(self, m): pass
    def set_centroid(self, x): pass


class _Printer:
    def print_receipt(self, *a): pass
    def print_strip(self, *a): pass


class _BaseCam:
    _background_raw = None

    def __init__(self):
        self.stills = []

    def capture_frame(self, raw=False):
        return np.full((480, 640, 3), 90, np.uint8)

    def capture_still(self, size=None):
        self.stills.append("plain")
        return np.full((270, 480, 3), 100, np.uint8)

    def light_auto(self): pass
    def light_restore(self): pass


class _AfCam(_BaseCam):
    def __init__(self, focused=True, boom=False):
        super().__init__()
        self.focused, self.boom, self.events = focused, boom, []

    def has_autofocus(self): return True

    def start_focus(self, rect):
        if self.boom:
            raise RuntimeError("lens fault")
        self.events.append(("start", rect))
        return True

    def focus_done(self): return self.focused
    def focus_release(self): self.events.append("release")

    def capture_still(self, size=None, face_rect=None):
        self.events.append(("still", face_rect))
        return np.full((270, 480, 3), 100, np.uint8)


def _mirror(cam):
    import main
    import mirror_settings
    mirror_settings.FILE = os.path.join(tempfile.mkdtemp(), "s.json")
    m = main.MagicMirror.__new__(main.MagicMirror)
    main.MagicMirror.__init__(m, _Matrix(), cam, lambda a, b: main.NullButton(a, b), _Strip(), _Printer(), sim_mode=True, no_api=True)
    return m


def _fake_faces(monkeypatch_target):
    import smartcrop
    row = np.array([280, 200, 80, 80] + [0] * 10 + [0.9], np.float32)
    orig = smartcrop.find_face_rows
    smartcrop.find_face_rows = lambda frame: [row]
    return orig


def test_capture_path_focuses_exposes_and_releases():
    import smartcrop
    orig = _fake_faces(None)
    try:
        cam = _AfCam()
        m = _mirror(cam)
        m._capture_with_flash()
        assert cam.events[0][0] == "start" and cam.events[1][0] == "still" and cam.events[1][1] == cam.events[0][1]
        assert cam.events[-1] == "release"
        # a failed focus still takes the photo, and releases the lens
        cam = _AfCam(focused=False)
        m = _mirror(cam)
        m.camera = cam
        m._capture_with_flash()
        assert any(e[0] == "still" for e in cam.events if isinstance(e, tuple)) and "release" in cam.events
    finally:
        smartcrop.find_face_rows = orig


def test_capture_path_untouched_without_autofocus_or_on_errors():
    import smartcrop
    import mirror_settings
    orig = _fake_faces(None)
    try:
        cam = _BaseCam()                                   # simulator-style camera: nothing to call
        m = _mirror(cam)
        f = m._capture_with_flash()
        assert f is not None and cam.stills == ["plain"]
        cam = _AfCam(boom=True)                            # focus raises: today's behaviour
        m = _mirror(cam)
        f = m._capture_with_flash()
        assert f is not None and cam.events == [("still", None)]
        cam = _AfCam()                                     # switched off in the app
        m = _mirror(cam)
        mirror_settings.save({"face_focus": False})
        m._capture_with_flash()
        assert cam.events == [("still", None)]
    finally:
        smartcrop.find_face_rows = orig


def test_setting_default_and_coercion():
    import mirror_settings
    mirror_settings.FILE = os.path.join(tempfile.mkdtemp(), "s.json")
    assert mirror_settings.load()["face_focus"] is True
    assert mirror_settings.save({"face_focus": 0})["face_focus"] is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
