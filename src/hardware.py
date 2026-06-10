import shutil
import subprocess
import os
from .settings import update_setting

def detect_gpu():
    """Return 'nvenc', 'qsv', 'amf', or 'none'."""
    try:
        # ffmpeg hardware accel list
        result = subprocess.run(["ffmpeg", "-hide_banner", "-hwaccels"],
                                capture_output=True, text=True, check=True)
        out = result.stdout.lower()

        # Priority check
        if "cuda" in out or "nvenc" in out:
            gpu = "nvenc"
        elif "amf" in out:
            gpu = "amf"
        elif "qsv" in out:
            gpu = "qsv"
        else:
            gpu = "none"

        update_setting("gpu_type", gpu)
        return gpu
    except Exception:
        return "none"

def ensure_tools():
    """Verify ffmpeg and yt-dlp are in PATH."""
    missing = []
    for tool in ("ffmpeg", "yt-dlp"):
        if not shutil.which(tool):
            missing.append(tool)

    if missing:
        raise RuntimeError(f"Missing tools: {', '.join(missing)}. Please install them and add to PATH.")

if __name__ == "__main__":
    gpu = detect_gpu()
    print(f"Detected GPU: {gpu}")
    try:
        ensure_tools()
        print("Tools found.")
    except Exception as e:
        print(f"Error: {e}")
