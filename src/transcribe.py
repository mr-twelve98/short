import os
import json
import requests
from pathlib import Path
from faster_whisper import WhisperModel
from . import ingest

def format_timestamp(seconds):
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def json_to_srt(merged_data):
    """
    Converts the AI-merge JSON into a standard SRT string.
    Expects [{"start": float, "end": float, "text": str}, ...]
    """
    srt_lines = []
    for i, segment in enumerate(merged_data, 1):
        start = format_timestamp(segment["start"])
        end = format_timestamp(segment["end"])
        text = segment["text"].strip()
        srt_lines.append(f"{i}\n{start} --> {end}\n{text}\n\n")
    return "".join(srt_lines)

def run_whisper_word_level(audio_path, model_size="base", language="id"):
    """
    Runs Whisper to get word-level timestamps.
    Returns a list of dicts: {"word": str, "start": float, "end": float}
    """
    print(f"[Whisper] Loading model {model_size}...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"[Whisper] Transcribing {audio_path}...")
    segments, _ = model.transcribe(str(audio_path), language=language, word_timestamps=True)

    word_level_data = []
    for segment in segments:
        for word in segment.words:
            word_level_data.append({
                "word": word.word.strip(),
                "start": word.start,
                "end": word.end
            })

    return word_level_data

def merge_transcripts(whisper_data, youtube_text, provider_config):
    """
    Calls LLM to merge Whisper timestamps with YouTube transcript text.
    """
    prompt_path = Path(__file__).parent / "prompts" / "merge_transcript.txt"
    if not prompt_path.exists():
        raise RuntimeError(f"Prompt file not found at {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    whisper_json = json.dumps(whisper_data, indent=2)
    full_prompt = f"{prompt_template}\n\nWhisper transcript:\n{whisper_json}\n\nYouTube transcript:\n{youtube_text}"

    print(f"[AI-Merge] Calling {provider_config.get('provider')} to merge transcripts...")
    ai_response = ingest.call_ai_api(full_prompt, provider_config)

    try:
        clean = ai_response.strip()
        if clean.startswith("```"):
            clean = clean.split("```", 2)[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip().rstrip("`").strip()
        return json.loads(clean)
    except Exception as e:
        print(f"[AI-Merge] Error parsing LLM response: {e}")
        print(f"Raw Response: {ai_response}")
        raise RuntimeError("Failed to parse merged transcript from AI response.")

def transcribe_and_merge(audio_path, youtube_transcript, provider_config, clip_id="unknown", language="id"):
    """
    Orchestrates the transcription and AI-merge process.
    Saves both JSON and SRT versions.
    """
    # 1. Run Whisper
    whisper_data = run_whisper_word_level(audio_path, language=language)

    # 2. Call LLM to merge
    merged_data = merge_transcripts(whisper_data, youtube_transcript, provider_config)

    # 3. Save result
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"merged_transcript_{clip_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, indent=4, ensure_ascii=False)

    srt_path = output_dir / f"merged_transcript_{clip_id}.srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(json_to_srt(merged_data))

    print(f"[AI-Merge] Saved merged transcript to {json_path} and {srt_path}")
    return srt_path
