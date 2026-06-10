import re
from pathlib import Path

def sanitize_filename(text):
    """Sanitizes a string to be safe for filenames."""
    # Remove non-alphanumeric/spaces, then replace spaces with underscores
    clean = re.sub(r'[^\w\s-]', '', text).strip()
    return re.sub(r'[-\s]+', '_', clean)

def format_timestamp(seconds):
    """Formats seconds to HH:MM:SS,mmm for SRT."""
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def to_seconds(ts):
    """Parses HH:MM:SS or MM:SS to total seconds."""
    if not ts: return 0.0
    parts = list(map(float, ts.split(':')))
    if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
    if len(parts) == 2: return parts[0]*60 + parts[1]
    return parts[0]
