import cv2
import os
import numpy as np
from pathlib import Path

class SmartCrop:
    def __init__(self):
        self.detector_type = "haar"
        self.detector = None
        self.model_path = Path(__file__).parent.parent / "models" / "face_detection_yunet_2023mar.onnx"
        self._init_detector()

    def _init_detector(self):
        """Initializes YuNet or falls back to Haar Cascade."""
        # 1. Try YuNet
        if not self.model_path.exists():
            print(f"[SmartCrop] YuNet model missing. Attempting download to {self.model_path}...")
            try:
                self.model_path.parent.mkdir(parents=True, exist_ok=True)
                url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
                import requests
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                with open(self.model_path, "wb") as f:
                    f.write(response.content)
                print("[SmartCrop] Model downloaded successfully.")
            except Exception as e:
                print(f"[SmartCrop] Failed to download model: {e}")

        if self.model_path.exists():
            try:
                # In modern OpenCV versions, it's cv2.FaceDetectorYN
                # We need to set a dummy input size, it will be updated per frame
                self.detector = cv2.FaceDetectorYN.create(
                    model=str(self.model_path),
                    config="",
                    input_size=(320, 320),
                    score_threshold=0.8,
                    nms_threshold=0.3,
                    top_k=5000
                )
                self.detector_type = "yunet"
                print(f"[SmartCrop] Initialized YuNet with model: {self.model_path}")
                return
            except Exception as e:
                print(f"[SmartCrop] YuNet initialization failed: {e}")
        else:
            print(f"[SmartCrop] YuNet model not found at {self.model_path}")

        # 2. Fallback to Haar Cascade
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.detector = cv2.CascadeClassifier(cascade_path)
            self.detector_type = "haar"
            print(f"[SmartCrop] Fallback initialized: Haar Cascade")
        except Exception as e:
            print(f"[SmartCrop] Haar Cascade initialization failed: {e}")
            self.detector = None

    def detect_subject_x(self, frame):
        """
        Detects the face in a frame and returns the center X coordinate.
        """
        if self.detector is None:
            return None

        if self.detector_type == "yunet":
            # Update input size for current frame
            h, w = frame.shape[:2]
            self.detector.setInputSize((w, h))
            ret, faces = self.detector.detect(frame)

            if faces is not None and len(faces) > 0:
                # YuNet output: faces is a 2D array, each row is a face
                # [x1, y1, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rc, y_rc, x_lc, y_lc, confidence]
                # Pick face with highest confidence
                best_face = faces[np.argmax(faces[:, 14])]
                x, y, w_face, h_face = map(int, best_face[:4])
                return x + w_face // 2

        elif self.detector_type == "haar":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.detector.detectMultiScale(gray, 1.1, 4)
            if len(faces) > 0:
                # Pick largest face by area
                best_face = max(faces, key=lambda f: f[2] * f[3])
                x, y, w_face, h_face = best_face
                return x + w_face // 2

        return None

def to_sec(ts):
    if not ts: return 0.0
    if isinstance(ts, (int, float)): return float(ts)
    parts = list(map(float, str(ts).split(':')))
    if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
    if len(parts) == 2: return parts[0]*60 + parts[1]
    return parts[0]

def get_smart_crop_params(video_path, start_time, end_time):
    """
    Samples frames from the video, detects subject X, and returns a smoothed crop X.
    Returns None if no faces detected.
    """
    cropper = SmartCrop()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    start_sec = to_sec(start_time)
    end_sec = to_sec(end_time)
    duration = end_sec - start_sec
    if duration <= 0: duration = 5

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if frame_width == 0 or frame_height == 0:
        return None

    # Sample every 0.5 seconds
    sample_interval = 0.5
    num_samples = max(1, int(duration / sample_interval))

    detected_xs = []
    for i in range(num_samples):
        timestamp = start_sec + (i * sample_interval)
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ret, frame = cap.read()
        if ret:
            x = cropper.detect_subject_x(frame)
            if x is not None:
                detected_xs.append(x)

    cap.release()

    if not detected_xs:
        return None

    # Use median to avoid outliers/jitter
    target_x = int(np.median(detected_xs))

    # FFmpeg 'crop' logic for 9:16 (720x1280)
    # 1. Video will be scaled to height 1280.
    scale_factor = 1280 / frame_height
    scaled_width = frame_width * scale_factor
    scaled_target_x = target_x * scale_factor

    # We want scaled_target_x to be in center of 720 width
    crop_x = int(scaled_target_x - 360)

    # Boundary checks
    if crop_x < 0:
        crop_x = 0
    elif crop_x > (scaled_width - 720) and scaled_width > 720:
        crop_x = int(scaled_width - 720)
    elif scaled_width <= 720:
        crop_x = 0

    return crop_x
