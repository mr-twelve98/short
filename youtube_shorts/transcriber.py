import os
import logging
from youtube_transcript_api import YouTubeTranscriptApi
import whisper
import torch

logger = logging.getLogger(__name__)

def get_transcript(video_id, languages=['id', 'en']):
    """Try to get transcript from YouTube captions."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try to find Indonesian first, then English
        try:
            transcript = transcript_list.find_transcript(languages)
            return transcript.fetch()
        except:
            # If specified languages not found, try to find any manually created or auto-generated
            transcript = transcript_list.find_manually_created_transcript(languages)
            return transcript.fetch()

    except Exception as e:
        logger.warning(f"Could not fetch YouTube captions for {video_id}: {e}")
        return None

def transcribe_with_whisper(video_path, model_name="base"):
    """Fallback to Whisper for transcription."""
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model(model_name, device=device)
        result = model.transcribe(video_path, verbose=False)

        # Convert Whisper format to a similar format as youtube-transcript-api
        formatted_transcript = []
        for segment in result['segments']:
            formatted_transcript.append({
                'text': segment['text'].strip(),
                'start': segment['start'],
                'duration': segment['end'] - segment['start']
            })
        return formatted_transcript
    except Exception as e:
        logger.error(f"Error transcribing with Whisper: {e}")
        return None

def format_transcript_for_prompt(transcript):
    """Format transcript into a string for Gemini prompt."""
    if not transcript:
        return ""

    formatted_text = ""
    for entry in transcript:
        start = entry['start']
        # Convert seconds to MM:SS
        minutes = int(start // 60)
        seconds = int(start % 60)
        timestamp = f"[{minutes:02d}:{seconds:02d}]"
        formatted_text += f"{timestamp} {entry['text']}\n"

    return formatted_text

def save_transcript_as_srt(transcript, output_path):
    """Save transcript in SRT format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, entry in enumerate(transcript, 1):
            start = entry['start']
            end = start + entry['duration']

            f.write(f"{i}\n")
            f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            f.write(f"{entry['text']}\n\n")

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
