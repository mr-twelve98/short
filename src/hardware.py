import shutil
import subprocess
import os
import re
from .settings import update_setting

def detect_gpu():
    """Return the FFmpeg encoder name: 'h264_nvenc', 'h264_amf', 'h264_qsv', or 'none'."""
    try:
        # 1. Try to get vendor info from system
        gpu_info = ""
        if os.name == 'nt':
            try:
                gpu_info = subprocess.check_output(["wmic", "path", "win32_VideoController", "get", "name"],
                                                  text=True, stderr=subprocess.DEVNULL).lower()
            except:
                pass
        else:
            try:
                gpu_info = subprocess.check_output(["lspci"], text=True, stderr=subprocess.DEVNULL).lower()
            except:
                pass

        # 2. Check FFmpeg hardware encoders
        result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                capture_output=True, text=True, check=True)
        encoders = result.stdout.lower()

        gpu_type = "none"

        # Priority check with specific vendor strings
        # We check system info FIRST because encoders might contain all names

        # Check for NVIDIA
        if ("nvidia" in gpu_info) and "h264_nvenc" in encoders:
            gpu_type = "h264_nvenc"
        # Check for AMD
        elif ("amd" in gpu_info or "radeon" in gpu_info or "advanced micro devices" in gpu_info) and "h264_amf" in encoders:
            gpu_type = "h264_amf"
        # Check for Intel
        elif ("intel" in gpu_info) and "h264_qsv" in encoders:
            gpu_type = "h264_qsv"
        # If system info didn't help, fallback to checking which encoders exist
        elif "h264_nvenc" in encoders:
            gpu_type = "h264_nvenc"
        elif "h264_amf" in encoders:
            gpu_type = "h264_amf"
        elif "h264_qsv" in encoders:
            gpu_type = "h264_qsv"

        update_setting("gpu_type", gpu_type)
        return gpu_type
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
    print(f"Detected GPU Type: {gpu}")
    try:
        ensure_tools()
        print("Tools found.")
    except Exception as e:
        print(f"Error: {e}")
