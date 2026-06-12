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
    ts_str = str(ts_str).strip()
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
        raise ValueError("No clips found in AI output. Ensure the model followed the CLIP 1 format.")
    clips.sort(key=lambda x: x["start"])
    return clips, warnings

# ----------------------------------------------------------------------
# Strategy Pattern for AI Providers
# ----------------------------------------------------------------------

class BaseProvider:
    def __init__(self, api_key, model, endpoint=None):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    def call(self, prompt):
        raise NotImplementedError

    def list_models(self):
        return []

class OpenAICompatibleProvider(BaseProvider):
    def get_url(self):
        return self.endpoint or "https://api.openai.com/v1/chat/completions"

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def call(self, prompt):
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 3000
        }
        resp = requests.post(self.get_url(), headers=self.get_headers(), json=data, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def list_models(self):
        url = self.get_url().replace("/chat/completions", "/models")
        if "openai.com" in url and "/v1/models" not in url:
            url = "https://api.openai.com/v1/models"

        resp = requests.get(url, headers=self.get_headers(), timeout=30)
        if resp.status_code == 200:
            return [m["id"] for m in resp.json().get("data", [])]
        return []

class OpenRouterProvider(OpenAICompatibleProvider):
    def get_url(self):
        return "https://openrouter.ai/api/v1/chat/completions"

    def get_headers(self):
        headers = super().get_headers()
        headers.update({
            "HTTP-Referer": "https://github.com/jules-agent",
            "X-Title": "YouTube Shorts Ingest"
        })
        return headers

class GeminiProvider(BaseProvider):
    def call(self, prompt):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 3000}
        }
        resp = requests.post(url, json=data, timeout=90)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    def list_models(self):
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            return [m["name"].replace("models/", "")
                    for m in resp.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])]
        return []

class AnthropicProvider(BaseProvider):
    def call(self, prompt):
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000,
            "temperature": 0.7
        }
        resp = requests.post(url, headers=headers, json=data, timeout=90)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    def list_models(self):
        return [
            "claude-3-5-sonnet-20240620",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]

def get_provider_strategy(config):
    p = config.get("provider", "openrouter").lower()
    key = config.get("api_key")
    model = config.get("model")
    url = config.get("endpoint")

    if p == "openrouter": return OpenRouterProvider(key, model)
    if p == "gemini": return GeminiProvider(key, model)
    if p == "claude": return AnthropicProvider(key, model)
    if p == "openai": return OpenAICompatibleProvider(key, model)
    if p == "custom": return OpenAICompatibleProvider(key, model, url)
    raise RuntimeError(f"Unknown provider: {p}")

def call_ai_api(prompt: str, provider_config: dict) -> str:
    strategy = get_provider_strategy(provider_config)
    log(f"Calling {provider_config['provider']} (model={provider_config['model']})...")
    try:
        return strategy.call(prompt)
    except Exception as e:
        log(f"API Error: {e}")
        raise RuntimeError(f"{provider_config['provider'].capitalize()} API error: {e}")

def fetch_available_models(provider_config: dict) -> list:
    try:
        strategy = get_provider_strategy(provider_config)
        return strategy.list_models()
    except Exception as e:
        log(f"Error listing models: {e}")
        return []

# ----------------------------------------------------------------------
# Core ingest logic
# ----------------------------------------------------------------------
def collect_inputs(url: str, transcript: str = "", gemini_json: str = "", provider_config: dict = None) -> dict:
    url = url.strip()
    if not re.match(r"^https?://(www\.)?youtube\.com/|youtu\.be/", url):
        raise ValueError(f"Invalid YouTube URL: {url}")

    clips = []
    warnings = []

    if gemini_json.strip():
        log("Pre-generated result provided by user.")
        raw_text = gemini_json.strip()
        if raw_text.startswith('[') or raw_text.startswith('{'):
            try:
                data = json.loads(raw_text)
                clips_list = data["clips"] if isinstance(data, dict) and "clips" in data else data
                if not isinstance(clips_list, list): raise ValueError("No clip list found.")

                for i, clip in enumerate(clips_list):
                    required = ["start", "end", "title", "hook", "caption", "hashtags", "why"]
                    for field in required:
                        if field not in clip:
                            for k in list(clip.keys()):
                                if k.lower() == field:
                                    clip[field] = clip.pop(k)
                                    break
                            if field not in clip: raise ValueError(f"Clip {i+1} missing: {field}")
                    clip["start"] = parse_timestamp(clip["start"])
                    clip["end"]   = parse_timestamp(clip["end"])
                    clip["clip"] = i + 1
                    if isinstance(clip["hashtags"], str):
                        clip["hashtags"] = [t.strip() for t in re.split(r'[\s,]+', clip["hashtags"]) if t.strip()]
                    clips.append(clip)
            except Exception as e: raise ValueError(f"Failed to parse JSON: {e}")
        else:
            clips, warnings = parse_gemini_text(raw_text)
    elif transcript.strip():
        log("Transcript supplied - calling AI.")
        if not provider_config: raise RuntimeError("AI config missing.")
        prompt_file = Path(__file__).parent / "prompts" / "gemini_viral_moments.txt"
        with open(prompt_file, "r", encoding="utf-8") as f: template = f.read()
        prompt = template.format(url=url, transcript=transcript)
        ai_output = call_ai_api(prompt, provider_config)
        clips, warnings = parse_gemini_text(ai_output)
    else:
        raise RuntimeError("Provide transcript or result.")

    return {"url": url, "transcript": transcript, "clips": clips, "warnings": warnings}

def prepare_payload(url: str, transcript: str = "", gemini_json: str = "", provider_config: dict = None) -> dict:
    payload = collect_inputs(url, transcript, gemini_json, provider_config)
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "ingest_result.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)
    log(f"Result written.")
    return payload

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--transcript")
    parser.add_argument("--gemini_json")
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--model", default="google/gemini-2.0-flash-001")
    parser.add_argument("--api_key")
    args = parser.parse_args()
    api_key = args.api_key or os.getenv("API_KEY") or os.getenv("OPENROUTER_API_KEY")
    provider_config = {"provider": args.provider, "api_key": api_key, "model": args.model, "endpoint": ""}
    t_text = ""
    if args.transcript:
        with open(args.transcript, "r", encoding="utf-8") as f: t_text = f.read().strip()
    g_text = ""
    if args.gemini_json:
        if os.path.exists(args.gemini_json):
            with open(args.gemini_json, "r", encoding="utf-8") as f: g_text = f.read().strip()
        else: g_text = args.gemini_json
    try:
        prepare_payload(args.url, t_text, g_text, provider_config)
        log("Success.")
    except Exception as e:
        log(f"ERROR: {e}")
        exit(1)
