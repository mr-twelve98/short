import subprocess
import os
import re
from pathlib import Path

def _run_ffmpeg(cmd):
    """Helper that runs a FFmpeg command via subprocess.check_call."""
    print(f"[FFMPEG] {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg failed with exit code {e.returncode}")

def to_sec(ts):
    if not ts: return 0
    parts = list(map(float, ts.split(':')))
    if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
    if len(parts) == 2: return parts[0]*60 + parts[1]
    return parts[0]

def build_filter(gpu_type, hook, caption, srt_path=None, font_path=None, crop_x=None):
    """Returns the FFmpeg filter-graph string for a 9:16 output (720x1280)."""
    # Escape single quotes and colons for drawtext and subtitles
    def escape_text(t):
        return t.replace("'", r"\'").replace(":", r"\:")

    hook_esc = escape_text(hook)
    # If caption is long, we might want to wrap it or just use the first line
    caption_esc = escape_text(caption.split('\n')[0])

    # Font config fix for Windows
    if font_path:
        font = f"fontfile='{font_path}'"
    elif os.name == 'nt':
        font = "fontfile='C\\:\\\\Windows\\\\Fonts\\\\arial.ttf'"
    else:
        font = "font=DejaVuSans"

    # background blur: scale to 720:1280, then blur
    bg = "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=20[bg]"

    # foreground:
    if crop_x is not None:
        # Smart crop: scale to height 1280 and crop
        fg = f"[0:v]scale=-1:1280,crop=720:1280:{crop_x}:0[fg]"
    else:
        # Legacy/Fallback: scale to height 1280 and center-crop width
        fg = "[0:v]scale=-1:1280,crop=720:1280:(iw-720)/2:0[fg]"

    # overlay
    ov = "[bg][fg]overlay=0:0[vid]"
    # drawtext hook (near top)
    hook_dt = f"[vid]drawtext={font}:text='{hook_esc}':x=(w-text_w)/2:y=100:fontsize=36:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10[vid1]"

    # If we have SRT, we burn it. Otherwise we use the static caption.
    if srt_path and os.path.exists(srt_path):
        # ffmpeg subtitles filter needs escaped path. For Windows, backslashes are tricky.
        srt_esc = str(Path(srt_path).absolute()).replace("\\", "/").replace(":", "\\:")
        # We'll place subtitles above the static caption area or instead of it
        sub_filter = f"[vid1]subtitles='{srt_esc}':force_style='Alignment=2,FontSize=24,OutlineColour=&H80000000,BorderStyle=3'[final]"
        return ";".join([bg, fg, ov, hook_dt, sub_filter])
    else:
        cap_dt  = f"[vid1]drawtext={font}:text='{caption_esc}':x=(w-text_w)/2:y=h-250:fontsize=32:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10[final]"
        return ";".join([bg, fg, ov, hook_dt, cap_dt])

def make_preview(source_mp4, start, end, gpu_type, hook, caption, out_path, srt_path=None, font_path=None, crop_x=None):
    """Generates a full-length, low-res preview with optional subtitles."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    filter_complex = build_filter(gpu_type, hook, caption, srt_path=srt_path, font_path=font_path, crop_x=crop_x)

    cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-to", end,
        "-i", str(source_mp4),
        "-filter_complex", filter_complex,
        "-map", "[final]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        str(out_path)
    ]
    _run_ffmpeg(cmd)

def make_final(source_mp4, start, end, gpu_type, hook, caption, out_path, thumb_path, srt_path=None, font_path=None, full_file=False, crop_x=None):
    """Generates high-quality final clip and a thumbnail.
    If full_file is True, 'end' is ignored for duration but used for thumbnail midpoint if valid.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Path(thumb_path).parent.mkdir(parents=True, exist_ok=True)

    filter_complex = build_filter(gpu_type, hook, caption, srt_path=srt_path, font_path=font_path, crop_x=crop_x)

    v_codec = gpu_type if gpu_type != "none" else "libx264"

    cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-to", end,
        "-i", str(source_mp4),
        "-filter_complex", filter_complex,
        "-map", "[final]",
        "-map", "0:a?",
        "-c:v", v_codec,
        "-c:a", "aac",
        "-preset", "fast",
        "-crf", "18",
        str(out_path)
    ]
    _run_ffmpeg(cmd)

    # Thumbnail midpoint
    try:
        s_sec = to_sec(start)
        e_sec = to_sec(end)
        # If e_sec is very large (dummy), we should use a shorter duration for thumb
        # For our cut segments, they are already short (30-90s).
        if e_sec > 3600: # more than an hour
            mid_sec = s_sec + 2.0
        else:
            mid_sec = (s_sec + e_sec) / 2
    except:
        mid_sec = 1.0 # fallback

    h = int(mid_sec // 3600)
    m = int(mid_sec % 3600 // 60)
    s = mid_sec % 60
    mid_ts = f"{h:02d}:{m:02d}:{s:06.3f}"

    hook_esc = hook.replace("'", r"\'").replace(":", r"\:")
    # Font config fix for Windows in thumbnail too
    if font_path:
        font = f"fontfile='{font_path}'"
    elif os.name == 'nt':
        font = "fontfile='C\\:\\\\Windows\\\\Fonts\\\\arial.ttf'"
    else:
        font = "font=DejaVuSans"

    thumb_filter = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,{font}:text='{hook_esc}':x=(w-text_w)/2:y=100:fontsize=40:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10"
    # wait, the original thumb_filter was scale=...,crop=...,drawtext=...
    # I should re-add drawtext=
    thumb_filter = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,drawtext={font}:text='{hook_esc}':x=(w-text_w)/2:y=100:fontsize=40:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10"

    thumb_cmd = [
        "ffmpeg", "-y",
        "-ss", mid_ts,
        "-i", str(source_mp4),
        "-vf", thumb_filter,
        "-vframes", "1",
        "-update", "1",
        str(thumb_path)
    ]
    _run_ffmpeg(thumb_cmd)
