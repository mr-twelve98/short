import json
from pathlib import Path

SETTINGS_FILE = Path("settings.json")

DEFAULT_SETTINGS = {
    "provider": "openrouter",
    "api_key": "",
    "model": "google/gemini-2.0-flash-001",
    "endpoint": "",
    "whisper_model": "tiny",
    "language": "id",
    "gpu_type": "none"
}

def load_settings():
    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)

            # Migration: if old openrouter_api_key exists, move it to api_key
            if "openrouter_api_key" in settings and not settings.get("api_key"):
                settings["api_key"] = settings.pop("openrouter_api_key")

            # Ensure all default keys exist
            updated = False
            for key, val in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = val
                    updated = True

            if updated:
                save_settings(settings)

            return settings
    except Exception:
        return DEFAULT_SETTINGS

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)

def update_setting(key, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)
