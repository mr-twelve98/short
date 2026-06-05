import subprocess
import shutil
import logging
import imageio_ffmpeg

logger = logging.getLogger(__name__)

def get_ffmpeg_path():
    """Get the path to the ffmpeg executable."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def check_ffmpeg():
    """Check if ffmpeg is available."""
    return get_ffmpeg_path() is not None

def get_ffmpeg_version():
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return "Not found"
    try:
        result = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True)
        return result.stdout.split("\n")[0]
    except Exception:
        return "Unknown"

def detect_gpu_encoders():
    """
    Detect available hardware-accelerated encoders.
    Returns a list of available encoders in priority order.
    """
    encoders = {
        "nvidia": "h264_nvenc",
        "amd": "h264_amf",
        "intel": "h264_qsv",
    }

    available = []

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return available

    try:
        result = subprocess.run([ffmpeg_path, "-encoders"], capture_output=True, text=True)
        output = result.stdout

        for vendor, encoder in encoders.items():
            if encoder in output:
                available.append(vendor)
    except Exception as e:
        logger.error(f"Error detecting encoders: {e}")

    return available

def get_best_encoder(priority=["nvidia", "amd", "intel", "cpu"]):
    available = detect_gpu_encoders()

    encoders_map = {
        "nvidia": "h264_nvenc",
        "amd": "h264_amf",
        "intel": "h264_qsv",
        "cpu": "libx264"
    }

    for p in priority:
        if p == "cpu":
            return encoders_map["cpu"]
        if p in available:
            return encoders_map[p]

    return "libx264"

def run_ffmpeg_command(args):
    """Wrapper to run ffmpeg commands."""
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg not found")
    cmd = [ffmpeg_path] + args
    logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)
