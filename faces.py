"""Face recognition for the mirror: local, opt-in, numbers only.

What is stored (panel_setup/faces.json, this machine only, mode 600) - never photos of people
you have not named, never uploaded:
  people      people you enrolled or named: a few 128-number fingerprints each
  candidates  (only if "learn frequent faces" is switched on) fingerprints of unnamed faces that
              keep turning up. A face becomes a *suggestion* in the app after COUNT sightings on
              DAYS different days; only then a 64 px thumbnail is kept so you can tell who it is.
              Unnamed candidates expire after EXPIRE_DAYS. Dismissing deletes them at once.

    book = FaceBook()
    embs = book.capture(grab)                    # look at the camera for a few seconds
    book.add("Fionn", embs)
    book.observe(frame, rows, learn=True)        # called by the mirror; returns who is there
"""
import base64
import datetime
import json
import os
import threading
import time
import uuid

import cv2
import numpy as np

import smartcrop

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(_HERE, "assets", "models", "face_recognition_sface_2021dec_int8.onnx")
DB_FILE = os.path.join(_HERE, "panel_setup", "faces.json")
THRESHOLD = 0.40          # cosine similarity to call two fingerprints the same person
CAND_THRESHOLD = 0.50     # stricter when grouping unnamed faces (a wrong merge is worse)
MIN_FACE_PX = 70          # ignore faces smaller than this (too far away to be reliable)
MAX_EMBEDDINGS = 12       # fingerprints kept per named person
MAX_CAND_EMB = 6
MAX_CANDIDATES = 30
COUNT, DAYS = 5, 2        # sightings / distinct days before a face is suggested
SIGHTING_GAP = 20.0       # one sighting per candidate per this many seconds
EXPIRE_DAYS = 30
SAVE_EVERY = 30.0

_rec = None
_rec_lock = threading.Lock()


def available() -> bool:
    return os.path.exists(MODEL) and hasattr(cv2, "FaceRecognizerSF") and os.path.exists(smartcrop._MODEL)


def _recognizer():
    global _rec
    with _rec_lock:
        if _rec is None:
            _rec = cv2.FaceRecognizerSF.create(MODEL, "")
        return _rec


def embed(frame, row):
    """Unit-length 128-number fingerprint of one detected face (row from smartcrop.find_face_rows)."""
    rec = _recognizer()
    aligned = rec.alignCrop(frame, np.asarray(row, np.float32).reshape(-1)[:15])
    f = rec.feature(aligned).reshape(-1).astype(np.float32)
    n = np.linalg.norm(f)
    return f / n if n else f


def usable(rows):
    return [r for r in rows if r[14] >= 0.8 and min(r[2], r[3]) >= MIN_FACE_PX]


def thumbnail(frame, row, size=64):
    """Small square JPEG (base64) of the face - only kept for suggestions."""
    x, y, w, h = [float(v) for v in row[:4]]
    cx, cy, s = x + w / 2, y + h / 2, max(w, h) * 1.5
    x0, y0 = int(max(0, cx - s / 2)), int(max(0, cy - s / 2))
    crop = frame[y0:int(min(frame.shape[0], cy + s / 2)), x0:int(min(frame.shape[1], cx + s / 2))]
    if crop.size == 0:
        return ""
    ok, buf = cv2.imencode(".jpg", cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA),
                           [cv2.IMWRITE_JPEG_QUALITY, 70])
    return base64.b64encode(buf.tobytes()).decode() if ok else ""


class FaceBook:
    def __init__(self, path=DB_FILE):
        self.path = path
        self.lock = threading.RLock()
        self._mtime = None
        self._people, self._cands = {}, []
        self._dirty, self._last_save = False, 0.0

    # ------------------------------------------------------------ storage
    def _load(self):
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            if self._mtime is not None:
                self._people, self._cands, self._mtime = {}, [], None
            return
        if m == self._mtime:
            return
        try:
            with open(self.path) as fh:
                raw = json.load(fh)
            self._people = {n: {"embeddings": [np.array(e, np.float32) for e in v["embeddings"]],
                                "added": v.get("added", 0)} for n, v in raw.get("people", {}).items()}
            self._cands = [{**c, "embeddings": [np.array(e, np.float32) for e in c["embeddings"]],
                            "days": list(c.get("days", []))} for c in raw.get("candidates", [])]
        except Exception:
            self._people, self._cands = {}, []
        self._mtime = m

    def _save(self):
        data = {"people": {n: {"embeddings": [e.round(5).tolist() for e in v["embeddings"]],
                               "added": v["added"]} for n, v in self._people.items()},
                "candidates": [{**c, "embeddings": [e.round(5).tolist() for e in c["embeddings"]]}
                               for c in self._cands]}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        self._mtime = os.path.getmtime(self.path)
        self._dirty, self._last_save = False, time.time()

    def flush(self, force=False):
        with self.lock:
            if self._dirty and (force or time.time() - self._last_save >= SAVE_EVERY):
                self._save()

    # ------------------------------------------------------------- people
    def people(self):
        with self.lock:
            self._load()
            return {n: len(v["embeddings"]) for n, v in self._people.items()}

    def add(self, name, embeddings):
        name = " ".join(str(name).split())[:30]
        if not name or not embeddings:
            raise ValueError("a name and at least one face are needed")
        with self.lock:
            self._load()
            cur = self._people.get(name, {"embeddings": [], "added": time.time()})
            cur["embeddings"] = (cur["embeddings"] + list(embeddings))[-MAX_EMBEDDINGS:]
            self._people[name] = cur
            self._save()
        return name

    def forget(self, name):
        with self.lock:
            self._load()
            gone = self._people.pop(name, None) is not None
            if gone:
                self._save()
            return gone

    def forget_everything(self):
        """Delete all people and everything learned."""
        with self.lock:
            n = len(self._people) + len(self._cands)
            self._people, self._cands, self._dirty = {}, [], False
            if os.path.exists(self.path):
                os.remove(self.path)
            self._mtime = None
            return n

    def forget_learned(self):
        """Delete only the unnamed learned faces (keep named people)."""
        with self.lock:
            self._load()
            n = len(self._cands)
            self._cands = []
            self._save()
            return n

    # ------------------------------------------------------- recognising
    @staticmethod
    def _sim(emb, embs):
        sims = sorted((float(np.dot(emb, e)) for e in embs), reverse=True)
        return float(np.mean(sims[:3])) if sims else -1.0

    def identify(self, emb):
        """(name or None, best similarity) among named people."""
        with self.lock:
            self._load()
            best_name, best = None, -1.0
            for name, v in self._people.items():
                s = self._sim(emb, v["embeddings"])
                if s > best:
                    best_name, best = name, s
        return (best_name if best >= THRESHOLD else None), best

    def identify_frame(self, frame, rows=None):
        """[(row, name or None, similarity)] for every usable face."""
        rows = usable(rows if rows is not None else smartcrop.find_face_rows(frame))
        if not rows or not self.people():
            return [(r, None, 0.0) for r in rows]
        return [(r, *self.identify(embed(frame, r))) for r in rows]

    def capture(self, grab, shots=8, seconds=5.0):
        """Look at the camera for a few seconds; one fingerprint per good sighting of the
        largest face. grab() must return a full-width BGR frame."""
        t0, embs = time.time(), []
        while time.time() - t0 < seconds and len(embs) < shots:
            frame = grab()
            rows = usable(smartcrop.find_face_rows(frame))
            if rows:
                embs.append(embed(frame, max(rows, key=lambda r: r[2] * r[3])))
            time.sleep(0.4)
        return embs

    # ------------------------------------------------- learning (opt-in)
    def observe(self, frame, rows=None, learn=False, now=None):
        """Identify faces; with learn=True also keep fingerprints of unnamed faces that
        keep turning up. Returns [(row, name or None, similarity)]."""
        now = now if now is not None else time.time()
        rows = usable(rows if rows is not None else smartcrop.find_face_rows(frame))
        out = []
        for r in rows:
            emb = embed(frame, r)
            name, sim = self.identify(emb)
            out.append((r, name, sim))
            if name is None and learn:
                self._sighting(frame, r, emb, now)
        if learn:
            self.flush()
        return out

    def _sighting(self, frame, row, emb, now):
        today = datetime.date.fromtimestamp(now).isoformat()
        with self.lock:
            self._load()
            best, best_sim = None, -1.0
            for c in self._cands:
                s = self._sim(emb, c["embeddings"])
                if s > best_sim:
                    best, best_sim = c, s
            if best is not None and best_sim >= CAND_THRESHOLD:
                if now - best["last_seen"] < SIGHTING_GAP:
                    return                                   # same visit: don't count twice
                best["count"] += 1
                best["last_seen"] = now
                if today not in best["days"]:
                    best["days"].append(today)
                if len(best["embeddings"]) < MAX_CAND_EMB:
                    best["embeddings"].append(emb)
                if not best.get("thumb") and best["count"] >= COUNT and len(best["days"]) >= DAYS:
                    best["thumb"] = thumbnail(frame, row)    # kept only once it is a suggestion
            else:
                self._cands.append({"id": uuid.uuid4().hex[:8], "embeddings": [emb], "count": 1,
                                    "days": [today], "first_seen": now, "last_seen": now, "thumb": ""})
                if len(self._cands) > MAX_CANDIDATES:        # drop the least-seen, oldest ones
                    self._cands.sort(key=lambda c: (c["count"], c["last_seen"]))
                    self._cands = self._cands[len(self._cands) - MAX_CANDIDATES:]
            self._dirty = True

    def purge(self, now=None):
        now = now if now is not None else time.time()
        with self.lock:
            self._load()
            keep = [c for c in self._cands if now - c["last_seen"] < EXPIRE_DAYS * 86400]
            if len(keep) != len(self._cands):
                self._cands, self._dirty = keep, True
                self._save()

    def suggestions(self):
        """Frequent unnamed faces, most seen first."""
        with self.lock:
            self._load()
            out = [{"id": c["id"], "thumb": c.get("thumb", ""), "count": c["count"],
                    "days": len(c["days"]), "last_seen": c["last_seen"]}
                   for c in self._cands if c["count"] >= COUNT and len(c["days"]) >= DAYS and c.get("thumb")]
        return sorted(out, key=lambda s: -s["count"])

    def name_suggestion(self, cid, name):
        with self.lock:
            self._load()
            c = next((c for c in self._cands if c["id"] == cid), None)
            if c is None:
                raise KeyError("that suggestion is gone")
            n = self.add(name, c["embeddings"])
            self._cands = [x for x in self._cands if x["id"] != cid]
            self._save()
            return n

    def dismiss(self, cid):
        with self.lock:
            self._load()
            before = len(self._cands)
            self._cands = [c for c in self._cands if c["id"] != cid]
            if len(self._cands) != before:
                self._save()
            return len(self._cands) != before
