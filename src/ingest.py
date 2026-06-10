python
    import json
    import re
    import requests
    import argparse
    from datetime import datetime
    from pathlib import Path

    GEMINI_MODEL = "google/gemini-2.0-flash-001"

    def log(message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")

    def parse_timestamp(ts_str):
        """Normalizes timestamps to HH:MM:SS.
        Accepts SS, MM:SS, H:MM:SS, HH:MM:SS.
        """
        ts_str = ts_str.strip()
        ts_str = re.sub(r'[\[\]]', '', ts_str)
        parts = ts_str.split(':')
        try:
            if len(parts) == 1:          # SS
                total_seconds = int(float(parts[0]))
            elif len(parts) == 2:        # MM:SS
                total_seconds = int(float(parts[0])) * 60 + int(float(parts[1]))
            elif len(parts) == 3:        # H:MM:SS or HH:MM:SS
                total_seconds = int(float(parts[0])) * 3600 + int(float(parts[1])) * 60 + int(float(parts[2]))
            else:
                raise ValueError(f"Invalid timestamp format: {ts_str}")

            hours, minutes = divmod(total_seconds, 3600)
            minutes, seconds = divmod(minutes, 60)
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
        parts = re.split(r'(?i)^CLIP\s+\d+', text, flags=re.MULTILINE)
        clip_index = 1
        for part in parts[1:]:
            if not part.strip():
                continue
            clip_data = {}
            patterns = {
                "start": r'(?i)Start:\s(.)',
                "end": r'(?i)End:\s(.)',
                "title": r'(?i)Title:\s(.)',
                "hook": r'(?i)Hook:\s(.)',
                "caption": r'(?i)Caption:\s(.)',
                "hashtags": r'(?i)Hashtags:\s(.)',
                "why": r'(?i)Why:\s(.)'
            }
            for key, pattern in patterns.items():
                match = re.search(pattern, part)
                if match:
                    clip_data[key] = match.group(1).strip()
                else:
                    raise ValueError(f"Clip {clip_index} is missing required field: {key}")

            try:
                clip_data["start"] = parse_timestamp(clip_data["start"])
                clip_data["end"]   = parse_timestamp(clip_data["end"])
            except ValueError as e:
                raise ValueError(f"Clip {clip_index} has malformed timestamp: {e}")

            duration = get_seconds(clip_data["end"]) - get_seconds(clip_data["start"])
            if duration < 30:
                warn_msg = f"Clip {clip_index} duration {duration}s < 30s"
                warnings.append(warn_msg)
                log(f"WARNING: {warn_msg}")

            tags_raw = clip_data["hashtags"]
            clip_data["hashtags"] = [t.strip() for t in re.split(r'[\s,]+', tags_raw) if t.strip()]

            clip_data["clip"] = clip_index
            clips.append(clip_data)
            clip_index += 1

        if not clips:
            raise ValueError("No clips found in Gemini output. Ensure the model followed the CLIP 1 format.")
        clips.sort(key=lambda x: x["start"])
        return clips, warnings

    def call_openrouter(prompt, openrouter_api_key):
        if not openrouter_api_key:
            raise RuntimeError("OpenRouter API key not provided.")
        log(f"Calling OpenRouter with model {GEMINI_MODEL}...")
        headers = {
            "Authorization": f"Bearer {openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jules-agent",   # Required by OpenRouter
            "X-Title": "YouTube Shorts Ingest"
        }
        data = {
            "model": GEMINI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 3000
        }
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        if response.status_code != 200:
            raise RuntimeError(f"OpenRouter API error ({response.status_code}): {response.text}")
        result = response.json()
        return result['choices'][0]['message']['content']

    def collect_inputs(url: str, transcript: str = "", gemini_json: str = "", openrouter_api_key: str = "") -> dict:
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
                    clips_list = data["clips"] if isinstance(data, dict) and "clips" in data else (
                        data if isinstance(data, list) else []
                    )
                    for i, clip in enumerate(clips_list):
                        clip["start"] = parse_timestamp(str(clip["start"]))
                        clip["end"]   = parse_timestamp(str(clip["end"]))
                        clip["clip"] = i + 1
                        clips.append(clip)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to parse gemini_json: {e}")
            else:
                # It's the "CLIP 1..." text
                clips, warnings = parse_gemini_text(raw_text)

        elif transcript.strip():
            log("Transcript provided. Generating clips via Gemini...")
            if not openrouter_api_key:
                raise RuntimeError("Provide OpenRouter API key to use Gemini.")
            prompt_file = Path(file).parent.parent / "prompts" / "gemini_viral_moments.txt"
            with open(prompt_file, "r", encoding="utf-8") as f:
                template = f.read()
            gemini_output = call_openrouter(template.format(url=url, transcript=transcript), openrouter_api_key)
            clips, warnings = parse_gemini_text(gemini_output)

        else:
            raise RuntimeError("Provide transcript or gemini_result_json")

        return {
            "url": url,
            "transcript": transcript,
            "clips": clips,
            "warnings": warnings
        }

    def prepare_payload(url, transcript="", gemini_json="", openrouter_api_key=""):
        payload = collect_inputs(url, transcript, gemini_json, openrouter_api_key)
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True, parents=True)
        output_file = output_dir / "ingest_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
        log(f"Result written to {output_file}")
        return payload
