import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "whisper_model": "base",
    "output_folder": "shorts_output",
    "gpu_priority": ["nvidia", "amd", "intel", "cpu"],
    "last_url": "",
    "target_resolution": [1080, 1920]
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                # Merge with defaults for new settings
                return {**DEFAULT_CONFIG, **config}
        except Exception as e:
            print(f"Error loading config: {e}")
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")

class ConfigManager:
    def __init__(self):
        self.config = load_config()

    def get(self, key):
        return self.config.get(key, DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.config[key] = value
        save_config(self.config)
