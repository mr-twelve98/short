import os
import json
import re
import requests
import argparse
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def parse_timestamp(ts_str):
    """Normalizes timestamps to HH:MM:SS.
    Accepts SS, MM:SS, H:MM:SS, HH:MM:SS."""
    ts_str = ts_str.strip()
    ts_str = re.sub(r'[\[\]]', '', ts_str)
    parts = ts_str.split(':')
    try:
        if len(parts) == 1:          # SS
            total_seconds = int(float(parts[0]))
        elif len(parts) == 2:        # MM:SS
            total_seconds = int(float(parts[0])) * 60 + int(float(parts[1]))
        elif len(parts) == 3:        # H:MM:SS or HH:MM:SS
            total_seconds = (int(float(parts[0])) * 3600 +
                             int(float(parts[1])) * 60 +
                             int(float(parts[2])))
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

# ----------------------------------------------------------------------
# Gemini-style parsing
# ----------------------------------------------------------------------
def parse_gemini_text(text):
    """Parse the "CLIP 1 ..." format into a list of dictionaries."""
    clips = []
    warnings = []

    # Split by lines that start with "CLIP <num>"
    parts = re.split(r'(?i)^CLIP\s+\d+', text, flags=re.MULTILINE)
    clip_index = 1
    for part in parts[1:]:
        if not part.strip():
            continue

        clip_data = {}
        patterns = {
            "start":    r'(?i)Start:\s*(.*)',
            "end":      r'(?i)End:\s*(.*)',
            "title":    r'(?i)Title:\s*(.*)',
            "hook":     r'(?i)Hook:\s*(.*)',
            "caption":  r'(?i)Caption:\s*(.*)',
            "hashtags": r'(?i)Hashtags:\s*(.*)',
            "why":      r'(?i)Why:\s*(.*)'
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, part)
            if match:
                clip_data[key] = match.group(1).strip()
            else:
                raise ValueError(f"Clip {clip_index} is missing required field: {key}")

        # Normalise timestamps
        try:
            clip_data["start"] = parse_timestamp(clip_data["start"])
            clip_data["end"]   = parse_timestamp(clip_data["end"])
        except ValueError as e:
            raise ValueError(f"Clip {clip_index} has malformed timestamp: {e}")

        # Duration warning
        duration = get_seconds(clip_data["end"]) - get_seconds(clip_data["start"])
        if duration < 30:
            warn_msg = f"Clip {clip_index} duration {duration}s < 30s"
            warnings.append(warn_msg)
            log(f"WARNING: {warn_msg}")

        # Normalise hashtags
        tags_raw = clip_data["hashtags"]
        clip_data["hashtags"] = [t.strip() for t in re.split(r'[\s,]+', tags_raw) if t.strip()]

        clip_data["clip"] = clip_index
        clips.append(clip_data)
        clip_index += 1

    if not clips:
        raise ValueError("No clips found in AI output. Ensure the model followed the CLIP 1 format.")
    clips.sort(key=lambda x: x["start"])
    return clips, warnings

# ----------------------------------------------------------------------
# Multi-provider AI client
# ----------------------------------------------------------------------
def call_ai_api(prompt: str, provider_config: dict) -> str:
    """
    Sends prompt to the configured provider and returns the raw text response.
    Supported providers: openrouter, gemini, claude, openai, custom.
    """
    provider = provider_config.get("provider", "openrouter").lower()
    api_key  = provider_config.get("api_key")
    model    = provider_config.get("model")
    endpoint = provider_config.get("endpoint")  # only used for custom

    if not api_key:
        raise RuntimeError(f"API key for {provider} not provided.")

    log(f"Calling {provider} (model={model})...")
    headers = {"Content-Type": "application/json"}
    data = {}
    url = ""

    # ------------------ OpenRouter ------------------
    if provider == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        headers["HTTP-Referer"] = "https://github.com/jules-agent"
        headers["X-Title"]      = "YouTube Shorts Ingest"
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 3000
        }

    # ------------------ Gemini ------------------
    elif provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 3000
            }
        }

    # ------------------ Claude (Anthropic) ------------------
    elif provider == "claude":
        url = "https://api.anthropic.com/v1/messages"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000,
            "temperature": 0.7
        }

    # ------------------ OpenAI ------------------
    elif provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 3000
        }

    # ------------------ Custom ------------------
    elif provider == "custom":
        if not endpoint:
            raise RuntimeError("Custom endpoint not provided in settings.")
        url = endpoint
        # Assume the same payload schema as OpenAI for simplicity
        headers["Authorization"] = f"Bearer {api_key}"
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 3000
        }

    else:
        raise RuntimeError(f"Unknown AI provider: {provider}")

    # Make the request
    try:
        response = requests.post(url, headers=headers, json=data, timeout=90)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to {provider}: {e}")

    if response.status_code != 200:
        raise RuntimeError(f"{provider.capitalize()} API error ({response.status_code}): {response.text}")

    result = response.json()

    # Normalise the response text across providers
    try:
        if provider in ["openrouter", "openai", "custom"]:
            content = result["choices"][0]["message"]["content"]
        elif provider == "gemini":
            content = result["candidates"][0]["content"]["parts"][0]["text"]
        elif provider == "claude":
            content = result["content"][0]["text"]
        else:
            content = str(result)
        return content
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected {provider} response structure: {json.dumps(result)}")

# ----------------------------------------------------------------------
# Model discovery (optional UI helper)
# ----------------------------------------------------------------------
def fetch_available_models(provider_config: dict) -> list:
    """
    Returns a list of model identifiers for the configured provider.
    For Claude we return a hard-coded list because the public endpoint does not expose models.
    """
    provider = provider_config.get("provider", "openrouter").lower()
    api_key  = provider_config.get("api_key")

    if not api_key and provider != "claude":
        return []  # Cannot list without a key (except Claude)

    log(f"Fetching model list for {provider}...")

    try:
        if provider == "openrouter":
            resp = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
            if resp.status_code == 200:
                return [m["id"] for m in resp.json().get("data", [])]

        elif provider == "openai":
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=30)
            if resp.status_code == 200:
                return [m["id"] for m in resp.json().get("data", [])]

        elif provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                # Only keep models that support generateContent (the default for Gemini)
                return [m["name"].replace("models/", "")
                        for m in resp.json().get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", [])]

        elif provider == "claude":
            # Hard-coded list of Claude-3 models (publicly known)
            return [
                "claude-3-5-sonnet-20240620",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307"
            ]

    except Exception as e:
        log(f"Error fetching models for {provider}: {e}")

    return []


# ----------------------------------------------------------------------
# Core ingest logic (URL -> clip list)
# ----------------------------------------------------------------------
def collect_inputs(
    url: str,
    transcript: str = "",
    gemini_json: str = "",
    provider_config: dict = None
) -> dict:
    """
    Returns a dict:
        {
            "url": url,
            "transcript": transcript,
            "clips": [...],
            "warnings": [...]
        }
    """
    url = url.strip()
    if not re.match(r"^https?://(www\.)?youtube\.com/|youtu\.be/", url):
        raise ValueError(f"Invalid YouTube URL: {url}")

    clips = []
    warnings = []

    # --------------------------------------------------------------
    # 1. Pre-generated Gemini/JSON result supplied by the user
    # --------------------------------------------------------------
    if gemini_json.strip():
        log("Pre-generated result provided by user.")
        raw_text = gemini_json.strip()

        # JSON-style (list or dict with "clips" key)
        if raw_text.startswith('[') or raw_text.startswith('{'):
            try:
                data = json.loads(raw_text)
                if isinstance(data, dict) and "clips" in data:
                    clips_list = data["clips"]
                elif isinstance(data, list):
                    clips_list = data
                else:
                    raise ValueError("Provided JSON does not contain a list of clips.")

                for i, clip in enumerate(clips_list):
                    # Ensure required fields exist (case-insensitive)
                    required = ["start", "end", "title", "hook", "caption", "hashtags", "why"]
                    for field in required:
                        if field not in clip:
                            # try case-insensitive match
                            found = False
                            for k in list(clip.keys()):
                                if k.lower() == field:
                                    clip[field] = clip.pop(k)
                                    found = True
                                    break
                            if not found:
                                raise ValueError(f"Clip {i+1} missing field: {field}")

                    # Normalise timestamps & hashtags
                    clip["start"] = parse_timestamp(str(clip["start"]))
                    clip["end"]   = parse_timestamp(str(clip["end"]))
                    clip["clip"] = i + 1
                    if isinstance(clip["hashtags"], str):
                        clip["hashtags"] = [t.strip() for t in re.split(r'[\s,]+', clip["hashtags"]) if t.strip()]
                    clips.append(clip)

            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse gemini_json: {e}")

        # Plain text "CLIP 1 ..." format
        else:
            clips, warnings = parse_gemini_text(raw_text)

    # --------------------------------------------------------------
    # 2. No pre-generated result - we must ask the AI
    # --------------------------------------------------------------
    elif transcript.strip():
        log("Transcript supplied - calling AI to extract clips.")
        if not provider_config:
            raise RuntimeError("AI provider configuration missing.")

        # Load the prompt template (you should have a file under src/prompts/)
        prompt_file = Path(__file__).parent / "prompts" / "gemini_viral_moments.txt"
        if not prompt_file.is_file():
            raise RuntimeError(f"Prompt template not found at {prompt_file}")

        with open(prompt_file, "r", encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(url=url, transcript=transcript)
        ai_output = call_ai_api(prompt, provider_config)
        clips, warnings = parse_gemini_text(ai_output)

    else:
        raise RuntimeError("You must provide either a transcript or a pre-generated Gemini/JSON result.")

    return {
        "url": url,
        "transcript": transcript,
        "clips": clips,
        "warnings": warnings
    }


# ----------------------------------------------------------------------
# Helper to write the JSON payload to disk
# ----------------------------------------------------------------------
def prepare_payload(
    url: str,
    transcript: str = "",
    gemini_json: str = "",
    provider_config: dict = None
) -> dict:
    payload = collect_inputs(url, transcript, gemini_json, provider_config)

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "ingest_result.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

    log(f"Result written to {output_file}")
    return payload


# ----------------------------------------------------------------------
# CLI entry-point (still usable for quick testing)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest YouTube transcript and generate viral-short clips."
    )
    parser.add_argument("--url", required=True, help="YouTube video URL")
    parser.add_argument("--transcript", help="Path to raw transcript file")
    parser.add_argument("--gemini_json", help="Path to pre-generated Gemini result (JSON or CLIP text)")

    # Provider-specific args (optional - can also be read from env or settings.json)
    parser.add_argument("--provider", default="openrouter",
                        help="AI provider (openrouter|gemini|claude|openai|custom)")
    parser.add_argument("--model", default="google/gemini-2.0-flash-001",
                        help="Model identifier for the chosen provider")
    parser.add_argument("--api_key", help="API key (overrides env vars)")

    args = parser.parse_args()

    # Load API key from argument, then fall back to environment variables
    api_key = args.api_key or os.getenv("API_KEY") or os.getenv("OPENROUTER_API_KEY")

    provider_config = {
        "provider": args.provider,
        "api_key": api_key,
        "model": args.model,
        "endpoint": ""          # only used for custom provider
    }

    # Load transcript if a file path was supplied
    t_text = ""
    if args.transcript:
        if os.path.exists(args.transcript):
            with open(args.transcript, "r", encoding="utf-8") as f:
                t_text = f.read().strip()

    # Load Gemini/JSON result if a file path was supplied
    g_text = ""
    if args.gemini_json:
        if os.path.exists(args.gemini_json):
            with open(args.gemini_json, "r", encoding="utf-8") as f:
                g_text = f.read().strip()
        else:
            g_text = args.gemini_json

    try:
        result = prepare_payload(args.url, t_text, g_text, provider_config)
        log("Ingest complete successfully.")
    except Exception as e:
        log(f"ERROR: {e}")
        exit(1)
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
