#!/usr/bin/env bash
# Download the face models (OpenCV Zoo). YuNet (detector) is committed; SFace (recogniser, 9.9 MB,
# Apache-2.0) is fetched. Run from anywhere: ./assets/models/get_models.sh
set -euo pipefail
cd "$(dirname "$0")"
base=https://github.com/opencv/opencv_zoo/raw/main/models
fetch() { [ -s "$2" ] || { echo "downloading $2"; curl -fsSL -o "$2" "$base/$1/$2"; }; }
fetch face_detection_yunet face_detection_yunet_2023mar.onnx
fetch face_recognition_sface face_recognition_sface_2021dec_int8.onnx
ls -la *.onnx
