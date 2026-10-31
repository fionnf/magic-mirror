"""Hand signals for the mirror: who is holding up an open palm, or a peace sign?

Two small ONNX models from the OpenCV Zoo (MediaPipe palm detection + hand landmarks, Apache-2.0, ~4 MB each,
in assets/models/, fetched by assets/models/get_models.sh), run with OpenCV's own DNN: no extra packages, no
internet at run time, and the picture never leaves the Pi. The pre/post-processing is the Zoo's reference code
(models/palm_detection_mediapipe/mp_palmdet.py and models/handpose_estimation_mediapipe/mp_handpose.py),
shortened.

    find(frame_bgr)  ->  [Hand, ...]   (the most confident hand first; x, y normalised 0..1 in the frame)
    Hand.gesture     ->  "palm" | "peace" | None
    Hand.centre      ->  (x, y) of the palm, normalised

A finger counts as held out when its tip is clearly further from the wrist than its middle joint, whatever
way up the hand is. "palm" = all four fingers out (thumb free); "peace" = index and middle out, ring and little folded.
"""
import os

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
PALM = os.path.join(_HERE, "assets", "models", "palm_detection_mediapipe_2023feb.onnx")
POSE = os.path.join(_HERE, "assets", "models", "handpose_estimation_mediapipe_2023feb.onnx")


def available():
    return os.path.exists(PALM) and os.path.exists(POSE)


def _anchors():
    """The SSD anchor grid of the palm detector: 24x24 cells x2 at stride 8, then 12x12 cells x6."""
    out = []
    for n, rep in ((24, 2), (12, 6)):
        for y in range(n):
            for x in range(n):
                out += [((x + 0.5) / n, (y + 0.5) / n)] * rep
    return np.array(out, np.float32)


class Hand:
    def __init__(self, lm, score, shape):
        h, w = shape[:2]
        self.lm = lm[:, :2] / np.array([w, h], np.float32)             # 21 x 2, normalised
        self.score = score
        self.gesture = _gesture(self.lm)

    @property
    def centre(self):
        return tuple(self.lm[[0, 5, 9, 13, 17]].mean(axis=0))

    @property
    def size(self):
        return float(np.linalg.norm(self.lm[0] - self.lm[9]))          # wrist to middle knuckle, as a share of the frame


def _gesture(lm):
    d = lambda a, b: float(np.linalg.norm(lm[a] - lm[b]))
    palm = d(0, 9) + 1e-6
    out = []
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        out.append(d(0, tip) > 1.12 * d(0, pip) and d(0, tip) > 1.35 * palm)
    if all(out):
        return "palm"
    if out[0] and out[1] and not out[2] and not out[3]:
        return "peace"
    return None


class Detector:
    def __init__(self):
        self.palm = cv2.dnn.readNet(PALM)
        self.pose = cv2.dnn.readNet(POSE)
        self.anchors = _anchors()

    # ---- palm detection (the Zoo's MPPalmDet) ----
    def _palms(self, image, score_th=0.55, nms_th=0.3):
        size = np.array([192, 192])
        h, w = image.shape[:2]
        pad = np.array([0.0, 0.0])
        ratio = min(size / np.array([h, w]))
        img = image
        if (h, w) != (192, 192):
            rs = (np.array([h, w]) * ratio).astype(np.int32)
            img = cv2.resize(image, (rs[1], rs[0]))
            ph, pw = 192 - rs[0], 192 - rs[1]
            pad = np.array([pw // 2, ph // 2], np.float64)
            img = cv2.copyMakeBorder(img, ph // 2, ph - ph // 2, pw // 2, pw - pw // 2, cv2.BORDER_CONSTANT, None, (0, 0, 0))
        blob = (cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)[None]
        pad = (pad / ratio).astype(np.int32)
        self.palm.setInput(blob)
        out = self.palm.forward(self.palm.getUnconnectedOutLayersNames())
        score = 1 / (1 + np.exp(-out[1][0, :, 0].astype(np.float64)))
        box_d, lm_d = out[0][0, :, 0:4], out[0][0, :, 4:]
        scale = max(h, w)
        c, wh = box_d[:, :2] / size, box_d[:, 2:] / size
        boxes = np.concatenate([(c - wh / 2 + self.anchors) * scale, (c + wh / 2 + self.anchors) * scale], axis=1)
        boxes -= [pad[0], pad[1], pad[0], pad[1]]
        keep = cv2.dnn.NMSBoxes(boxes.tolist(), score.tolist(), score_th, nms_th, top_k=5)
        if len(keep) == 0:
            return []
        keep = np.array(keep).reshape(-1)
        lms = lm_d[keep].reshape(-1, 7, 2) / size + self.anchors[keep][:, None]
        lms = lms * scale - pad
        return [np.r_[boxes[k], lms[i].reshape(-1)] for i, k in enumerate(keep)], score[keep]

    # ---- hand landmarks (the Zoo's MPHandPose) ----
    @staticmethod
    def _crop(image, bbox, rot):
        shift, enl = ([0, 0], 4) if rot else ([0, -0.4], 3)
        bbox = bbox + np.array(shift) * (bbox[1] - bbox[0])
        c = bbox.sum(axis=0) / 2
        half = (bbox[1] - bbox[0]) * enl / 2
        bbox = np.array([c - half, c + half]).astype(np.int32)
        bbox[:, 0] = np.clip(bbox[:, 0], 0, image.shape[1])
        bbox[:, 1] = np.clip(bbox[:, 1], 0, image.shape[0])
        img = image[bbox[0][1]:bbox[1][1], bbox[0][0]:bbox[1][0], :]
        if img.size == 0:
            return None, bbox, np.zeros(2, np.int32)
        side = int(np.linalg.norm(img.shape[:2])) if rot else max(img.shape[:2])
        ph, pw = side - img.shape[0], side - img.shape[1]
        top, left = ph // 2, pw // 2
        img = cv2.copyMakeBorder(img, top, ph - top, left, pw - left, cv2.BORDER_CONSTANT, None, (0, 0, 0))
        return img, bbox, bbox[0] - [left, top]

    def _landmarks(self, image, palm):
        bbox = palm[0:4].reshape(2, 2)
        img, bbox, bias = self._crop(image, bbox, True)
        if img is None:
            return None
        pad_bias = np.array([0, 0], np.int32) + bias
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        bbox = bbox - pad_bias
        pl = palm[4:18].reshape(7, 2) - pad_bias
        p1, p2 = pl[0], pl[2]
        rad = np.pi / 2 - np.arctan2(-(p2[1] - p1[1]), p2[0] - p1[0])
        rad = rad - 2 * np.pi * np.floor((rad + np.pi) / (2 * np.pi))
        angle = np.rad2deg(rad)
        centre = bbox.sum(axis=0) / 2
        rm = cv2.getRotationMatrix2D(tuple(centre), angle, 1.0)
        rotated = cv2.warpAffine(img, rm, (img.shape[1], img.shape[0]))
        hom = np.c_[pl, np.ones(7)]
        rpl = np.array([hom @ rm[0], hom @ rm[1]])
        rb = np.array([rpl.min(axis=1), rpl.max(axis=1)])
        crop, rb, _ = self._crop(rotated, rb, False)
        if crop is None or crop.size == 0:
            return None
        blob = cv2.resize(crop, (224, 224), interpolation=cv2.INTER_AREA).astype(np.float32)[None] / 255.0
        self.pose.setInput(blob)
        lm, conf, _hand, _world = self.pose.forward(self.pose.getUnconnectedOutLayersNames())
        if conf[0][0] < 0.75:
            return None
        lm = lm[0].reshape(-1, 3).copy()
        scale = (rb[1] - rb[0]) / 224.0
        lm[:, :2] = (lm[:, :2] - 112.0) * max(scale)
        cm = cv2.getRotationMatrix2D((0, 0), angle, 1.0)
        rl = lm[:, :2] @ cm[:, :2]
        rot = np.array([[rm[0][0], rm[1][0]], [rm[0][1], rm[1][1]]])
        trans = np.array([rm[0][2], rm[1][2]])
        inv = np.c_[rot, np.array([-np.dot(rot[0], trans), -np.dot(rot[1], trans)])]
        cen = np.append(rb.sum(axis=0) / 2, 1)
        orig = np.array([np.dot(cen, inv[0]), np.dot(cen, inv[1])])
        return rl + orig + pad_bias, float(conf[0][0])

    def find(self, frame):
        """Hands in a BGR frame, most confident first."""
        r = self._palms(frame)
        if not r:
            return []
        palms, scores = r
        hands = []
        for p, s in zip(palms, scores):
            got = self._landmarks(frame, p)
            if got is not None:
                hands.append(Hand(got[0], got[1], frame.shape))
        return sorted(hands, key=lambda h: -h.score)


_det = None


def find(frame):
    global _det
    if _det is None:
        _det = Detector()
    return _det.find(frame)
