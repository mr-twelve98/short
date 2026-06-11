import cv2
import os
import subprocess
from pathlib import Path

def detect_subject_x(frame):
    """
    Detects the face in a frame and returns the center X coordinate.
    If no face is detected, returns None.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Load pre-trained Haar Cascade for face detection
    # Using the standard path in opencv-python
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)

    faces = face_cascade.detectMultiScale(gray, 1.1, 4)

    if len(faces) > 0:
        # Get the first face detected
        (x, y, w, h) = faces[0]
        # Return the center X of the face
        return x + w // 2

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
    Samples frames from the video between start and end times,
    detects subject X, and returns a recommended crop X coordinate.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0 # Fallback to left side (or center if handled by layout)

    start_sec = to_sec(start_time)
    end_sec = to_sec(end_time)

    # Total duration of the clip
    duration = end_sec - start_sec
    if duration <= 0:
        duration = 5 # fallback

    # Get frame width
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    if frame_width == 0:
        return 0

    # Sample every 0.5 seconds
    sample_interval = 0.5
    num_samples = int(duration / sample_interval)
    if num_samples < 1: num_samples = 1

    detected_xs = []

    for i in range(num_samples):
        timestamp = start_sec + (i * sample_interval)
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ret, frame = cap.read()
        if ret:
            x = detect_subject_x(frame)
            if x is not None:
                detected_xs.append(x)

    cap.release()

    if not detected_xs:
        # Default to center of the frame
        target_x = frame_width // 2
    else:
        # Average the detected X positions
        target_x = sum(detected_xs) // len(detected_xs)

    # Now calculate the 'crop_x' for FFmpeg's crop=720:1280:crop_x:0
    # The output width is 720. We want 'target_x' to be in the center of those 720 pixels.
    # So crop_x = target_x - (720 / 2)
    crop_x = target_x - 360

    # Boundary checks: crop_x cannot be less than 0 or greater than (frame_width - 720)
    if crop_x < 0:
        crop_x = 0
    elif crop_x > (frame_width - 720) and frame_width > 720:
        crop_x = frame_width - 720
    elif frame_width <= 720:
        crop_x = 0

    return int(crop_x)
