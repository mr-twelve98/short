import cv2
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

class FaceDetector:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = os.path.join(os.path.dirname(__file__), "face_detection_yunet.onnx")

        self.model_path = model_path
        self.detector = None
        if os.path.exists(model_path):
            try:
                self.detector = cv2.FaceDetectorYN.create(
                    model_path,
                    "",
                    (320, 320),
                    0.9,
                    0.3,
                    5000
                )
            except Exception as e:
                logger.error(f"Failed to load YuNet model: {e}")
        else:
            logger.warning(f"YuNet model not found at {model_path}")

    def detect(self, frame):
        if self.detector is None:
            return None

        height, width, _ = frame.shape
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        return faces

def get_best_face(faces, frame_width, frame_height):
    if faces is None or len(faces) == 0:
        return None

    # Sort by area (largest face)
    # faces[i] is [x1, y1, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score]
    # We want to find the largest/most centered face

    best_face = None
    max_score = -1

    center_x = frame_width / 2
    center_y = frame_height / 2

    for face in faces:
        x, y, w, h = face[:4]
        face_center_x = x + w / 2
        face_center_y = y + h / 2

        # Distance from center (normalized)
        dist = np.sqrt(((face_center_x - center_x)/frame_width)**2 + ((face_center_y - center_y)/frame_height)**2)

        # Area (normalized)
        area = (w * h) / (frame_width * frame_height)

        # Combined score: large and centered
        score = area * (1 - dist)

        if score > max_score:
            max_score = score
            best_face = face

    return best_face

def calculate_crop_window(face, frame_width, frame_height, target_ratio=9/16):
    """
    Calculate the x-coordinate for a 9:16 crop window centered on the face.
    Returns (crop_x, crop_y, crop_w, crop_h)
    """
    target_w = int(frame_height * target_ratio)
    target_h = frame_height

    if target_w > frame_width:
        # If the frame is already narrower than 9:16 (unlikely for landscape), adjust
        target_w = frame_width
        target_h = int(frame_width / target_ratio)

    if face is not None:
        x, y, w, h = face[:4]
        face_center_x = x + w / 2

        crop_x = int(face_center_x - target_w / 2)
    else:
        # Fallback to center crop
        crop_x = int((frame_width - target_w) / 2)

    # Ensure crop window is within frame boundaries
    crop_x = max(0, min(crop_x, frame_width - target_w))
    crop_y = int((frame_height - target_h) / 2)

    return crop_x, crop_y, target_w, target_h

def process_video_face_tracking(video_path, output_path, start_time, end_time, encoder_name="libx264"):
    """
    Process video with dynamic face tracking and crop to 9:16.
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    target_w = int(height * (9/16))
    target_h = height

    # Pre-calculate crop windows for each frame (or sample)
    # To avoid jitter, we can smooth the crop window coordinates

    # For now, let's use a simpler approach:
    # detect face every X frames and interpolate or use a moving average.

    detector = FaceDetector()

    # We'll use a sliding window average for crop_x to smooth movement
    window_size = int(fps) # 1 second window
    crop_x_history = []

    # Use ffmpeg for the actual cropping and encoding as it's faster
    # But we need the crop coordinates over time.
    # FFmpeg 'crop' filter can take expressions.

    # Alternatively, we can generate a list of crop coordinates and use them.
    # Given the complexity of dynamic cropping in FFmpeg with varying coordinates,
    # we might need to use the 'zoompan' filter or write a script for FFmpeg.

    # A simpler way for a "Dynamic" effect is to calculate a smooth crop_x(t)
    # and use FFmpeg's crop filter with an expression if possible,
    # but FFmpeg's expression language is limited for arbitrary data.

    # We will process frame by frame using OpenCV and write to a pipe/temporary file
    # then let FFmpeg handle the final encoding with subtitles.

    # Actually, a better way is to detect faces in a first pass,
    # then use that info to build an FFmpeg command or process.

    # Let's do a simplified dynamic tracking:
    # 1. Sample frames to find face positions
    # 2. Smooth the positions
    # 3. Use FFmpeg with a crop expression or multiple crop filters (complex)
    # OR just process via OpenCV (easiest to implement correctly now).

    temp_output = output_path + ".tmp.mp4"
    # Use a more compatible fourcc for temporary video
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output, fourcc, fps, (target_w, target_h))

    cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)

    current_crop_x = (width - target_w) / 2

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        curr_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if curr_time > end_time:
            break

        # Detect face
        faces = detector.detect(frame)
        best_face = get_best_face(faces, width, height)

        target_crop_x, _, _, _ = calculate_crop_window(best_face, width, height)

        # Smooth movement (simple lerp)
        current_crop_x = current_crop_x * 0.9 + target_crop_x * 0.1

        ix = int(current_crop_x)
        ix = max(0, min(ix, width - target_w))

        cropped_frame = frame[0:height, ix:ix+target_w]
        out.write(cropped_frame)

    cap.release()
    out.release()

    # After writing the cropped video, we need to add the audio back from the original video
    final_tracked_video = output_path + ".tracked.mp4"
    ffmpeg_path = get_ffmpeg_path()

    # Extract audio from original for the specific segment and merge with cropped video
    cmd = [
        ffmpeg_path, "-y",
        "-i", temp_output,
        "-ss", str(start_time),
        "-t", str(end_time - start_time),
        "-i", video_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        final_tracked_video
    ]

    subprocess.run(cmd, capture_output=True)

    # Cleanup temp video (silent one)
    if os.path.exists(temp_output):
        os.remove(temp_output)

    return final_tracked_video

from .encoder import get_ffmpeg_path
import subprocess
