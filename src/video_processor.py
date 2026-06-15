import os
import subprocess
import json
import re
from pathlib import Path
from faster_whisper import WhisperModel
from .hardware import ensure_tools, detect_gpu
from . import transcribe
from . import smart_crop
from .utils import format_timestamp

def download_video(url, out_dir=Path("downloads")):
    out_dir.mkdir(exist_ok=True, parents=True)
    try:
        cmd = [
            "yt-dlp",
            "-f", "bestvideo+bestaudio",
            "--merge-output-format", "mp4",
            "-o", str(out_dir / "%(title)s.%(ext)s"),
            "--restrict-filenames", # safer filenames
            url
        ]
        print(f"Downloading: {url}")
        subprocess.check_call(cmd)

        get_name_cmd = ["yt-dlp", "--get-filename", "-o", str(out_dir / "%(title)s.%(ext)s"), "--restrict-filenames", url]
        filename = subprocess.check_output(get_name_cmd, text=True).strip()
        return Path(filename).with_suffix(".mp4")
    except Exception as e:
        print(f"Download error: {e}")
        mp4_files = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        return mp4_files[0] if mp4_files else None

def cut_clip(source_mp4, start, end, gpu, out_path):
    """Cut segment, using hardware accel if available."""
    out_path.parent.mkdir(exist_ok=True, parents=True)
    v_codec = gpu if gpu != "none" else "libx264"

    from .layout_engine import get_encoder_params
    enc_params = get_encoder_params(v_codec)

    cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-to", end,
        "-i", str(source_mp4),
        "-c:v", v_codec,
        "-c:a", "aac",
        *enc_params,
        str(out_path)
    ]
    print(f"Cutting clip: {start} to {end}")
    subprocess.check_call(cmd)
    return out_path

def transcribe_clip(clip_path, model_size="tiny", device="cpu", language="id"):
    """Transcribes a clip and saves to SRT."""
    print(f"Transcribing {clip_path} with Whisper ({model_size})...")
    model = WhisperModel(model_size, device=device, compute_type="int8" if device == "cpu" else "float16")
    segments, _ = model.transcribe(str(clip_path), language=language)

    srt_path = clip_path.with_suffix(".srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start_str = format_timestamp(seg.start)
            end_str = format_timestamp(seg.end)
            text = seg.text.strip()
            if text:
                f.write(f"{i}\n{start_str} --> {end_str}\n{text}\n\n")
    return srt_path

def process_clip(clip_dict, url, gpu_type, whisper_model, language="id", youtube_transcript="", provider_config=None):
    ensure_tools()

    # 1. Download
    source = download_video(url)
    if not source or not source.exists():
        raise RuntimeError("Failed to download or find source video.")

    # 2. Cut
    clip_id = clip_dict.get('clip', 'unknown')
    temp_dir = Path("temp")
    out_clip = temp_dir / f"clip_{clip_id}.mp4"
    cut_clip(source, clip_dict['start'], clip_dict['end'], gpu_type, out_clip)

    # 3. Smart Crop
    print(f"Calculating smart crop for clip {clip_id}...")
    crop_x = smart_crop.get_smart_crop_params(source, clip_dict['start'], clip_dict['end'])

    # 3.5 Metadata Export
    meta_dir = Path("output/metadata")
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_file = meta_dir / f"clip_{clip_id}_metadata.txt"
    with open(meta_file, "w", encoding="utf-8") as f:
        f.write(f"Title: {clip_dict.get('title')}\n")
        f.write(f"Hook: {clip_dict.get('hook')}\n")
        f.write(f"Caption: {clip_dict.get('caption')}\n")
    print(f"Metadata saved to {meta_file}")

    # 4. Transcribe
    if youtube_transcript and provider_config:
        print(f"Using AI-Merge transcription for clip {clip_id}...")
        srt_path = transcribe.transcribe_and_merge(
            out_clip, youtube_transcript, provider_config, clip_id=clip_id, language=language
        )
    else:
        whisper_device = "cuda" if gpu_type == "h264_nvenc" else "cpu"
        srt_path = transcribe_clip(out_clip, model_size=whisper_model, device=whisper_device, language=language)

    # 4.5 Generate ASS (for rich styling like word-chunking)
    try:
        from . import layout_engine
        # Try to load the JSON if it exists (from AI-Merge)
        json_path = Path("output") / f"merged_transcript_{clip_id}.json"
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ass_path = str(srt_path).replace(".srt", ".ass")
            layout_engine.write_ass(data, ass_path, style_name=provider_config.get("subtitle_style", "Shorts"))
            print(f"Rich subtitles saved to {ass_path}")
    except Exception as e:
        print(f"Optional ASS generation failed: {e}")

    return out_clip, srt_path, crop_x
