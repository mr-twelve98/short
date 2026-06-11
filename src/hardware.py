import shutil
import subprocess
import os
import re
from .settings import update_setting

def detect_gpu():
    """
    Return the FFmpeg encoder name: 'h264_nvenc', 'h264_amf', 'h264_qsv', or 'none'.
    Strict Vendor-Explicit Logic: Only returns a hardware encoder if the
    corresponding vendor hardware is confirmed present in the system.
    """
    try:
        # 1. Get system GPU info
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

        # 2. Determine Vendor
        vendor = None
        if "nvidia" in gpu_info:
            vendor = "nvidia"
        elif "amd" in gpu_info or "radeon" in gpu_info or "advanced micro devices" in gpu_info:
            vendor = "amd"
        elif "intel" in gpu_info:
            vendor = "intel"

        # 3. Check FFmpeg encoders
        result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                capture_output=True, text=True, check=True)
        encoders = result.stdout.lower()

        gpu_type = "none"

        # 4. Strict Encoder Mapping
        if vendor == "nvidia" and "h264_nvenc" in encoders:
            gpu_type = "h264_nvenc"
        elif vendor == "amd" and "h264_amf" in encoders:
            gpu_type = "h264_amf"
        elif vendor == "intel" and "h264_qsv" in encoders:
            gpu_type = "h264_qsv"

        update_setting("gpu_type", gpu_type)
        return gpu_type
    except Exception:
        # Fallback to software encoding on any error
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
    print(f"Vendor-Explicit GPU Type: {gpu}")
    try:
        ensure_tools()
        print("Tools found.")
    except Exception as e:
        print(f"Error: {e}")
