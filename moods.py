"""Cheap mood cues from the YuNet face landmarks (no extra model).

Landmarks in a smartcrop.find_face_rows() row: 4,5 right eye; 6,7 left eye; 8,9 nose;
10,11 right mouth corner; 12,13 left mouth corner.

smile_ratio = mouth width / distance between the eyes. A relaxed mouth is roughly 0.7-0.8 of
the eye distance, a smile stretches it towards 1.0. The threshold differs between people and
cameras, so it is tunable: env MIRROR_SMILE_RATIO (default 0.90), tune it live with the app.
"""
import math
import os

SMILE_RATIO = float(os.environ.get("MIRROR_SMILE_RATIO", "0.90"))


def smile_ratio(row):
    eyes = math.hypot(row[4] - row[6], row[5] - row[7])
    mouth = math.hypot(row[10] - row[12], row[11] - row[13])
    return mouth / eyes if eyes > 1e-6 else 0.0


def is_smiling(row, threshold=None):
    return smile_ratio(row) >= (SMILE_RATIO if threshold is None else threshold)
