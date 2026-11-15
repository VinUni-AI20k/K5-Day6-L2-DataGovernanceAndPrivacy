# models_optional/

| File | Source | License | sha256 |
|---|---|---|---|
| `haarcascade_frontalface_default.xml` | OpenCV 4.10.0 wheel (`opencv-python-headless==4.10.0.84`, `cv2/data/`) | Intel License Agreement for Open Source Computer Vision Library (BSD-style; notice kept inside the file) | `0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0` |

Used only by the optional T07 Haar reference baseline (`src/t07_baseline_haar.py`). It needs
`cv2.CascadeClassifier`, which exists in OpenCV 4.x and in opencv-contrib 5.x but not in plain OpenCV 5.x;
the main baseline (`src/t07_baseline.py`) and the PoC do not need it.
The PoC detector (`src/t07_detector.py`) uses no model files.
