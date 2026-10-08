# Models

`face_detection_yunet_2023mar.onnx` - YuNet face detector (~230 KB), used by `smartcrop.py` to keep
people in frame when photos are cut to portrait. Source: OpenCV Zoo
(https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), MIT licence,
copyright (c) 2020 Shiqi Yu. Runs locally; nothing is sent anywhere. Needs OpenCV >= 4.5.4.
