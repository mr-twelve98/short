import os
import json
import re
import requests
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 1. Environment loading
# Priority: Current directory .env then ~/.hermes/.env
load_dotenv() # Load from current dir if exists
ENV_PATH = Path.home() / ".hermes" / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = "google/gemini-2.0-flash-001"

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def parse_timestamp(ts_str):
    """Normalizes timestamps to HH:MM:SS.
    Accepts SS, MM:SS, H:MM:SS, HH:MM:SS.
    """
    ts_str = ts_str.strip()
    # Remove common extra characters like brackets
    ts_str = re.sub(r'[\[\]]', '', ts_str)
    parts = ts_str.split(':')
    try:
        if len(parts) == 1: # SS
            total_seconds = int(float(parts[0]))
        elif len(parts) == 2: # MM:SS
            total_seconds = int(float(parts[0])) * 60 + int(float(parts[1]))
        elif len(parts) == 3: # H:MM:SS or HH:MM:SS
            total_seconds = int(float(parts[0])) * 3600 + int(float(parts[1])) * 60 + int(float(parts[2]))
        else:
            raise ValueError(f"Invalid timestamp format: {ts_str}")

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except Exception as e:
        raise ValueError(f"Could not parse timestamp '{ts_str}': {e}")

def get_seconds(ts_str):
    h, m, s = map(int, ts_str.split(':'))
    return h * 3600 + m * 60 + s

def parse_gemini_text(text):
    """Parses the 'CLIP 1...' text format into a list of dicts."""
    clips = []
    warnings = []

    # Split by CLIP followed by a number at the start of a line
    parts = re.split(r'(?i)^CLIP\s+\d+', text, flags=re.MULTILINE)

    # The first part is text before the first CLIP marker
    clip_index = 1
    for part in parts[1:]:
        if not part.strip():
            continue

        clip_data = {}
        patterns = {
            "start": r'(?i)Start:\s*(.*)',
            "end": r'(?i)End:\s*(.*)',
            "title": r'(?i)Title:\s*(.*)',
            "hook": r'(?i)Hook:\s*(.*)',
            "caption": r'(?i)Caption:\s*(.*)',
            "hashtags": r'(?i)Hashtags:\s*(.*)',
            "why": r'(?i)Why:\s*(.*)'
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, part)
            if match:
                clip_data[key] = match.group(1).strip()
            else:
                raise ValueError(f"Clip {clip_index} is missing required field: {key}")

        # Normalize timestamps
        try:
            clip_data["start"] = parse_timestamp(clip_data["start"])
            clip_data["end"] = parse_timestamp(clip_data["end"])
        except ValueError as e:
            raise ValueError(f"Clip {clip_index} has malformed timestamp: {e}")

        # Duration check
        duration = get_seconds(clip_data["end"]) - get_seconds(clip_data["start"])
        if duration < 30:
            warn_msg = f"Clip {clip_index} duration {duration}s < 30s"
            warnings.append(warn_msg)
            log(f"WARNING: {warn_msg}")

        # Parse hashtags into list
        tags_raw = clip_data["hashtags"]
        # Split by spaces or commas, filter out empty strings
        clip_data["hashtags"] = [t.strip() for t in re.split(r'[\s,]+', tags_raw) if t.strip()]

        clip_data["clip"] = clip_index
        clips.append(clip_data)
        clip_index += 1

    if not clips:
        raise ValueError("No clips found in Gemini output. Ensure the model followed the CLIP 1 format.")

    clips.sort(key=lambda x: x["start"])
    return clips, warnings

def call_openrouter(prompt):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Check your .env file.")

    log(f"Calling OpenRouter with model {GEMINI_MODEL}...")
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/jules-agent", # Required by OpenRouter
        "X-Title": "YouTube Shorts Ingest"
    }
    data = {
        "model": GEMINI_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 3000
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=60)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to OpenRouter: {e}")

    if response.status_code != 200:
        raise RuntimeError(f"OpenRouter API error ({response.status_code}): {response.text}")

    result = response.json()
    if 'choices' not in result or not result['choices']:
        raise RuntimeError(f"Unexpected OpenRouter response: {json.dumps(result)}")

    content = result['choices'][0]['message']['content']
    return content

def collect_inputs(url: str, transcript: str = "", gemini_json: str = "") -> dict:
    url = url.strip()
    if not re.match(r'^https?://(www\.)?youtube\.com/|youtu\.be/', url):
        raise ValueError(f"Invalid YouTube URL: {url}")

    clips = []
    warnings = []

    if gemini_json.strip():
        log("Gemini result provided by user.")
        raw_text = gemini_json.strip()
        if raw_text.startswith('{'):
            try:
                data = json.loads(raw_text)
                # If it's a full payload, just take clips
                if isinstance(data, dict) and "clips" in data:
                    clips_list = data["clips"]
                elif isinstance(data, list):
                    clips_list = data
                else:
                    raise ValueError("Provided JSON does not contain a list of clips.")

                # Normalize and validate provided JSON clips
                for i, clip in enumerate(clips_list):
                    required = ["start", "end", "title", "hook", "caption", "hashtags", "why"]
                    for field in required:
                        if field not in clip:
                            # Try case-insensitive
                            found = False
                            for k in clip.keys():
                                if k.lower() == field:
                                    clip[field] = clip.pop(k)
                                    found = True
                                    break
                            if not found:
                                raise ValueError(f"Clip at index {i} missing field: {field}")

                    clip["start"] = parse_timestamp(str(clip["start"]))
                    clip["end"] = parse_timestamp(str(clip["end"]))
                    clip["clip"] = i + 1

                    # Re-check duration
                    duration = get_seconds(clip["end"]) - get_seconds(clip["start"])
                    if duration < 30:
                        warnings.append(f"Clip {i+1} duration {duration}s < 30s")

                    if isinstance(clip["hashtags"], str):
                        clip["hashtags"] = [t.strip() for t in re.split(r'[\s,]+', clip["hashtags"]) if t.strip()]

                clips = clips_list
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse gemini_json: {e}")
        else:
            # It's the "CLIP 1..." text
            clips, warnings = parse_gemini_text(raw_text)
    elif transcript.strip():
        log("Transcript provided. Generating clips via Gemini...")
        prompt_file = Path(__file__).parent / "prompts" / "gemini_viral_moments.txt"
        if not prompt_file.exists():
            raise RuntimeError(f"Prompt template not found at {prompt_file}")

        with open(prompt_file, "r", encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(url=url, transcript=transcript)
        gemini_output = call_openrouter(prompt)
        clips, warnings = parse_gemini_text(gemini_output)
    else:
        raise RuntimeError("Provide transcript or gemini_result_json")

    return {
        "url": url,
        "transcript": transcript,
        "clips": clips,
        "warnings": warnings
    }

def prepare_payload(url, transcript, gemini_json):
    payload = collect_inputs(url, transcript, gemini_json)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True, parents=True)
    output_file = output_dir / "ingest_result.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

    log(f"Result written to {output_file}")
    return payload

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest YouTube transcript and generate viral clips.")
    parser.add_argument("--url", required=True, help="YouTube video URL")
    parser.add_argument("--transcript", help="Path to raw transcript file")
    parser.add_argument("--gemini_json", help="Path to pre-generated Gemini result text or JSON, or raw text")

    args = parser.parse_args()

    t_text = ""
    if args.transcript:
        if os.path.exists(args.transcript):
            with open(args.transcript, "r", encoding="utf-8") as f:
                t_text = f.read()
        else:
            log(f"Transcript file not found: {args.transcript}")
            exit(1)

    g_text = ""
    if args.gemini_json:
        if os.path.exists(args.gemini_json):
            with open(args.gemini_json, "r", encoding="utf-8") as f:
                g_text = f.read()
        else:
            g_text = args.gemini_json

    try:
        result = prepare_payload(args.url, t_text, g_text)
        log("Ingest complete successfully.")
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        # traceback.print_exc()
        exit(1)
