import os
import subprocess
import logging
from .encoder import get_ffmpeg_path

logger = logging.getLogger(__name__)

def generate_srt(transcript, output_path, start_offset=0, end_offset=None):
    """
    Generates an SRT file from transcript segments,
    adjusting timestamps to a specific clip range.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        count = 1
        for entry in transcript:
            start = entry['start']
            duration = entry['duration']
            end = start + duration

            # Check if this segment is within our clip range
            if end <= start_offset:
                continue
            if end_offset and start >= end_offset:
                break

            # Adjust timestamps relative to clip start
            adj_start = max(0, start - start_offset)
            adj_end = end - start_offset
            if end_offset and end > end_offset:
                adj_end = end_offset - start_offset

            f.write(f"{count}\n")
            f.write(f"{format_timestamp(adj_start)} --> {format_timestamp(adj_end)}\n")
            f.write(f"{entry['text']}\n\n")
            count += 1

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def burn_subtitles(video_path, srt_path, output_path, encoder="libx264"):
    """
    Uses FFmpeg to burn subtitles into the video.
    """
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg not found")

    # Escape path for FFmpeg filter
    # For Windows, paths in filters need special escaping
    escaped_srt_path = srt_path.replace("\\", "/").replace(":", "\\:")

    # Subtitle style: White text, black outline, bottom-center, Bold
    style = "FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,Fontname=Arial,Bold=1"

    filter_complex = f"subtitles='{escaped_srt_path}':force_style='{style}'"

    cmd = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-vf", filter_complex,
        "-c:v", encoder,
        "-c:a", "copy",
        output_path
    ]

    logger.info(f"Burning subtitles: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error(f"FFmpeg error: {result.stderr}")
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    return output_path
