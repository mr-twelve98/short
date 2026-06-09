# YouTube Shorts Ingest Module

This module handles the ingestion of YouTube video metadata and transcripts to identify viral moments using Gemini 2.0 Flash via OpenRouter.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables in `~/.hermes/.env` or `.env`:
   ```env
   OPENROUTER_API_KEY=your_key_here
   ```

## Usage

### CLI

You can run the script directly from the command line:

**Using a transcript file:**
```bash
python src/ingest.py --url "https://www.youtube.com/watch?v=VIDEO_ID" --transcript path/to/transcript.txt
```

**Using pre-generated Gemini text:**
```bash
python src/ingest.py --url "https://www.youtube.com/watch?v=VIDEO_ID" --gemini_json "CLIP 1\nStart: 00:01:00\n..."
```

**Using a JSON file containing clips:**
```bash
python src/ingest.py --url "https://www.youtube.com/watch?v=VIDEO_ID" --gemini_json path/to/clips.json
```

### Python API

```python
from src.ingest import prepare_payload

url = "https://www.youtube.com/watch?v=..."
transcript = "Full transcript text here..."

result = prepare_payload(url, transcript=transcript)
print(result["clips"])
```

## Output

The results are saved to `output/ingest_result.json` in the following format:

```json
{
    "url": "...",
    "transcript": "...",
    "clips": [
        {
            "clip": 1,
            "start": "00:05:23",
            "end": "00:06:15",
            "title": "...",
            "hook": "...",
            "caption": "...",
            "hashtags": ["#shorts", "#fyp"],
            "why": "..."
        }
    ],
    "warnings": []
}
```
