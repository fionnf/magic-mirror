# Models

`face_detection_yunet_2023mar.onnx` - YuNet face detector (~230 KB), used by `smartcrop.py` to keep
people in frame when photos are cut to portrait. Source: OpenCV Zoo
(https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), MIT licence,
copyright (c) 2020 Shiqi Yu. Runs locally; nothing is sent anywhere. Needs OpenCV >= 4.5.4.

`face_recognition_sface_2021dec_int8.onnx` - SFace face recogniser (~9.9 MB, Apache-2.0, OpenCV Zoo
`face_recognition_sface`). Not committed: fetch with `./get_models.sh`. It turns a face into 128 numbers;
`faces.py` compares them. Only those numbers (never photos) are stored, and only for people who enrol.

`palm_detection_mediapipe_2023feb.onnx` (~3.9 MB) and `handpose_estimation_mediapipe_2023feb.onnx` (~4.1 MB) - MediaPipe palm
detection and hand landmark models, from the OpenCV Zoo (`palm_detection_mediapipe`, `handpose_estimation_mediapipe`), Apache-2.0.
`hands.py` runs them with OpenCV's DNN to recognise an open palm or a peace sign held up to the mirror (the mirror's hand signals).
Committed, and also fetched by `./get_models.sh`. They run locally on the Pi; no picture leaves it.
