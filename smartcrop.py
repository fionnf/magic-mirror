"""Smart portrait crop: keep the people in frame when cutting a landscape photo to portrait.

    frame, how = portrait_crop(raw_frame, aspect=3/4, background=None)

Order of preference
  1. faces (YuNet, a tiny neural network that ships with the project, runs locally in
     ~10-60 ms): the crop window is placed to cover as many people as possible, centred on
     the group
  2. motion: where the frame differs from the empty-room `background` (people turned away)
  3. the centre

`how` says which one was used (for logs), e.g. "faces:2", "motion", "centre".
"""
import os

import cv2
import numpy as np

import config

_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "models",
                      "face_detection_yunet_2023mar.onnx")
_det = None
_det_size = None
DETECT_WIDTH = 320            # faces are found on a downscaled copy (speed)
SHOULDER = 1.0                # person region = face width * (1 + 2 * SHOULDER) wide
MIN_SCORE = 0.6


def _detector(w, h):
    global _det, _det_size
    if not os.path.exists(_MODEL):
        return None
    if _det is None:
        _det = cv2.FaceDetectorYN.create(_MODEL, "", (w, h), MIN_SCORE, 0.3, 20)
        _det_size = (w, h)
    elif _det_size != (w, h):
        _det.setInputSize((w, h))
        _det_size = (w, h)
    return _det


def find_face_rows(frame):
    """YuNet rows in the coordinates of `frame`: x, y, w, h, 5 landmarks (x, y) x5, score.
    Landmark order: right eye, left eye, nose tip, right mouth corner, left mouth corner."""
    h, w = frame.shape[:2]
    scale = DETECT_WIDTH / float(w) if w > DETECT_WIDTH else 1.0
    small = cv2.resize(frame, (int(round(w * scale)), int(round(h * scale)))) if scale != 1.0 else frame
    det = _detector(small.shape[1], small.shape[0])
    if det is None:
        return []
    try:
        _, faces = det.detect(small)
    except Exception:
        return []
    if faces is None:
        return []
    rows = []
    for f in faces:
        r = np.array(f, np.float32).copy()
        r[:14] /= scale
        rows.append(r)
    return rows


def find_faces(frame):
    """[(x, y, w, h, score)] in the coordinates of `frame`."""
    return [(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[14]))
            for r in find_face_rows(frame)]


def _motion_extent(frame, background):
    """(centre_x, centre_y, weight) of what changed against the background, or None."""
    if background is None or background.shape != frame.shape:
        return None
    small = lambda im: cv2.GaussianBlur(cv2.resize(im, (160, int(160 * im.shape[0] / im.shape[1]))),
                                        (5, 5), 0)
    a, b = small(frame), small(background)
    diff = cv2.cvtColor(cv2.absdiff(a, b), cv2.COLOR_BGR2GRAY)
    mask = diff > 30
    if mask.mean() < 0.02:
        return None
    ys, xs = np.nonzero(mask)
    sx = frame.shape[1] / mask.shape[1]
    sy = frame.shape[0] / mask.shape[0]
    return float(xs.mean() * sx), float(ys.mean() * sy), float(mask.mean())


def _window(lo_ok, hi_ok, span, size, centre):
    """Start of a window of `size` inside [0, span]. Prefer `centre`; return clamped start."""
    start = centre - size / 2.0
    return int(round(max(0.0, min(span - size, start))))


def portrait_crop(frame, aspect=None, background=None, faces=None):
    aspect = aspect or config.CAMERA_ASPECT
    h, w = frame.shape[:2]
    if w / h <= aspect + 1e-3:                       # already portrait or squarer: crop height
        cw, ch = w, int(round(w / aspect))
    else:                                            # landscape: full height, crop width
        cw, ch = int(round(h * aspect)), h
    if cw >= w and ch >= h:
        return frame, "as-is"

    if not getattr(config, "SMART_CROP", True):
        faces = []
    else:                                            # reuse detections if the caller has them
        faces = [f for f in (faces if faces is not None else find_faces(frame)) if f[4] >= MIN_SCORE]
    cx, cy, how = w / 2.0, h / 2.0, "centre"
    if faces:
        # person region per face (face + shoulders), weighted by face size (near people first)
        regs = []
        for x, y, fw, fh, sc in faces:
            half = fw * (0.5 + SHOULDER)
            regs.append((x + fw / 2.0 - half, x + fw / 2.0 + half, y, y + fh, fw * fh))
        # slide the window: most important is keeping whole faces inside, then how much of the
        # shoulders fit, then being close to the middle of the group
        mid = (min(r[0] for r in regs) + max(r[1] for r in regs)) / 2.0
        best_x0, best_key = 0.0, None
        for x0 in np.linspace(0, max(0, w - cw), 81):
            whole = cover = 0.0
            for (x, y, fw, fh, sc), (r0, r1, y0_, y1_, wgt) in zip(faces, regs):
                if x >= x0 - 1 and x + fw <= x0 + cw + 1:
                    whole += wgt
                cover += wgt * max(0.0, min(r1, x0 + cw) - max(r0, x0)) / max(1.0, r1 - r0)
            key = (round(whole, 1), round(cover, 1), -abs(x0 + cw / 2.0 - mid))
            if best_key is None or key > best_key:
                best_key, best_x0 = key, x0
        left, right = min(r[0] for r in regs), max(r[1] for r in regs)
        cx = (left + right) / 2.0 if right - left <= cw else best_x0 + cw / 2.0
        # vertical (only matters when cropping height): keep heads with some headroom
        top = min(f[1] for f in faces)
        bottom = max(f[1] + f[3] for f in faces)
        cy = (top + bottom) / 2.0 + (bottom - top) * 0.9      # bias downwards: show shoulders
        how = f"faces:{len(faces)}"
    else:
        m = _motion_extent(frame, background)
        if m:
            cx, cy, _ = m
            how = "motion"
    x0 = _window(0, 0, w, cw, cx)
    y0 = _window(0, 0, h, ch, cy) if ch < h else 0
    return frame[y0:y0 + ch, x0:x0 + cw], how
