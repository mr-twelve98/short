import subprocess
import os
import re
from pathlib import Path

# Subtitle and Drawtext Style Configs
STYLE_CONFIGS = {
    "Clean": {
        "hook_size": 32,
        "cap_size": 28,
        "sub_size": 20,
        "box": 1,
        "boxcolor": "black@0.5",
        "alignment": 2, # Bottom Center
    },
    "Minimal": {
        "hook_size": 24,
        "cap_size": 20,
        "sub_size": 16,
        "box": 0,
        "boxcolor": "none",
        "alignment": 2,
    },
    "Shorts": {
        "hook_size": 44,
        "cap_size": 36,
        "sub_size": 32,
        "box": 1,
        "boxcolor": "black@0.7",
        "alignment": 10, # Middle Center
    }
}

def _seconds_to_ass(s: float) -> str:
    """Convert float seconds to ASS timestamp format H:MM:SS.cs"""
    cs = int((s % 1) * 100)
    s  = int(s)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"

def _chunk_words(words: list, max_words: int = 4) -> list:
    """Split word-level segments into small chunks for karaoke-style display."""
    chunks, buf = [], []
    for w in words:
        buf.append(w)
        if len(buf) >= max_words:
            chunks.append({
                "text":  " ".join(x["word"] for x in buf),
                "start": buf[0]["start"],
                "end":   buf[-1]["end"],
            })
            buf = []
    if buf:
        chunks.append({
            "text":  " ".join(x["word"] for x in buf),
            "start": buf[0]["start"],
            "end":   buf[-1]["end"],
        })
    return chunks

def write_ass(segs: list, path: str, style_name: str = "Shorts", w: int = 720, h: int = 1280):
    """
    Write an ASS subtitle file from transcript segments.
    Uses word-chunking for 'Shorts' style, full segments for others.
    segs format: [{"start": float, "end": float, "text": str, "words": [...optional]}]
    """
    presets = {
        "Shorts":  dict(fs=80,  bold=-1, primary="&H00FFFFFF", outline="&H00000000",
                        back="&H40000000", ow=6, sh=3, mv=int(h * 0.12), chunks=True),
        "Clean":   dict(fs=60,  bold=-1, primary="&H00FFFFFF", outline="&H00000000",
                        back="&H80000000", ow=4, sh=2, mv=int(h * 0.08), chunks=False),
        "Minimal": dict(fs=50,  bold=0,  primary="&H00FFFFFF", outline="&H00000000",
                        back="&H60000000", ow=2, sh=1, mv=int(h * 0.06), chunks=False),
    }
    p = presets.get(style_name, presets["Shorts"])

    header = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\n"
        f"WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        f"[V4+ Styles]\n"
        f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        f"OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        f"ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        f"Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{p['fs']},{p['primary']},&H000000FF,{p['outline']},"
        f"{p['back']},{p['bold']},0,0,0,100,100,0,0,1,{p['ow']},{p['sh']},2,10,10,{p['mv']},1\n\n"
        f"[Events]\n"
        f"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    if p["chunks"]:
        all_words = []
        for seg in segs:
            all_words.extend(seg.get("words", []))
        items = _chunk_words(all_words, 4) if all_words else segs
    else:
        items = segs

    events = []
    for item in items:
        txt = item.get("text", "").replace("\\", "\\\\").replace("{", "\\{")
        events.append(
            f"Dialogue: 0,{_seconds_to_ass(item['start'])},"
            f"{_seconds_to_ass(item['end'])},Default,,0,0,0,,{txt}"
        )

    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")

def get_encoder_params(codec):
    """
    Returns valid FFmpeg encoder parameters (preset/quality) for the given codec.
    """
    if codec == "h264_amf":
        # Use balanced quality and CQP to avoid access violation on AMD iGPUs
        return ["-usage", "transcoding", "-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24"]
    elif codec == "h264_nvenc":
        # NVIDIA NVENC uses p1-p7 presets
        return ["-preset", "p1"]
    elif codec == "h264_qsv":
        # Intel QSV uses veryfast, faster, fast, etc.
        return ["-preset", "veryfast"]
    elif codec == "libx264":
        return ["-preset", "fast", "-crf", "18"]
    return []

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

def build_filter(gpu_type, hook, caption, sub_path=None, font_path=None, crop_x=None, style_name="Shorts", burn_text=True):
    """Returns the FFmpeg filter-graph string for a 9:16 output (720x1280)."""
    style = STYLE_CONFIGS.get(style_name, STYLE_CONFIGS["Shorts"])

    # Escape single quotes and colons for drawtext and subtitles
    def escape_text(t):
        return t.replace("'", r"\'").replace(":", r"\:")

    hook_esc = escape_text(hook)
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
    if not burn_text:
        ov = "[bg][fg]overlay=0:0[final]"
        return ";".join([bg, fg, ov])

    ov = "[bg][fg]overlay=0:0[vid]"

    # drawtext hook (near top)
    box_opt = f":box={style['box']}:boxcolor={style['boxcolor']}" if style['box'] else ""
    hook_dt = f"[vid]drawtext={font}:text='{hook_esc}':x=(w-text_w)/2:y=100:fontsize={style['hook_size']}:fontcolor=white{box_opt}:boxborderw=10[vid1]"

    # If we have subtitles, we burn them.
    if sub_path and os.path.exists(sub_path):
        ass_path = str(sub_path).replace(".srt", ".ass")
        if not os.path.exists(ass_path):
            # fallback: use srt directly with force_style if no ass found
            srt_esc = str(Path(sub_path).absolute()).replace("\\", "/").replace(":", "\\:")
            sub_filter = f"[vid1]subtitles='{srt_esc}':force_style='Alignment={style['alignment']},FontSize={style['sub_size']},OutlineColour=&H80000000,BorderStyle=3'[final] "
        else:
            ass_esc = str(Path(ass_path).absolute()).replace("\\", "/").replace(":", "\\:")
            sub_filter = f"[vid1]subtitles='{ass_esc}'[final] "
        return ";".join([bg, fg, ov, hook_dt, sub_filter])
    else:
        cap_dt  = f"[vid1]drawtext={font}:text='{caption_esc}':x=(w-text_w)/2:y=h-250:fontsize={style['cap_size']}:fontcolor=white{box_opt}:boxborderw=10[final]"
        return ";".join([bg, fg, ov, hook_dt, cap_dt])

def make_preview(source_mp4, start, end, gpu_type, hook, caption, out_path, sub_path=None, font_path=None, crop_x=None, style_name="Shorts", burn_text=True):
    """Generates a full-length, low-res preview with optional subtitles."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    filter_complex = build_filter(gpu_type, hook, caption, sub_path=sub_path, font_path=font_path, crop_x=crop_x, style_name=style_name, burn_text=burn_text)

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

def make_final(source_mp4, start, end, gpu_type, hook, caption, out_path, thumb_path, sub_path=None, font_path=None, full_file=False, crop_x=None, style_name="Shorts", burn_text=True):
    """Generates high-quality final clip and a thumbnail."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Path(thumb_path).parent.mkdir(parents=True, exist_ok=True)

    filter_complex = build_filter(gpu_type, hook, caption, sub_path=sub_path, font_path=font_path, crop_x=crop_x, style_name=style_name, burn_text=burn_text)

    v_codec = gpu_type if gpu_type != "none" else "libx264"
    enc_params = get_encoder_params(v_codec)

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
        *enc_params,
        str(out_path)
    ]
    _run_ffmpeg(cmd)

    # Thumbnail midpoint
    try:
        s_sec = to_sec(start)
        e_sec = to_sec(end)
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
    if font_path:
        font = f"fontfile='{font_path}'"
    elif os.name == 'nt':
        font = "fontfile='C\\:\\\\Windows\\\\Fonts\\\\arial.ttf'"
    else:
        font = "font=DejaVuSans"

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
