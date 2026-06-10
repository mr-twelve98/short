# YouTube Shorts Viral Moments Generator

A Python-based tool to automatically identify, cut, and process viral moments from YouTube videos for TikTok and YouTube Shorts.

## Features

- **AI Analysis**: Uses Gemini 2.0 Flash (via OpenRouter) to find the best moments based on a transcript.
- **Hardware Acceleration**: Detects and uses NVIDIA (nvenc), AMD (amf), or Intel (qsv) GPUs for fast encoding.
- **Auto-Transcribe**: Generates accurate subtitles using `faster-whisper`.
- **Layout Engine**: Automatic 9:16 vertical video formatting with blurred background and text overlays.
- **Interactive GUI**: Review, edit, and approve clips before final rendering.

## Setup

1. **Install FFmpeg & yt-dlp**:
   Ensure `ffmpeg` and `yt-dlp` are installed and available in your system PATH.

2. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **API Keys**:
   Get an OpenRouter API key from [openrouter.ai](https://openrouter.ai/).

## Usage

Run the GUI application:
```bash
python -m src.gui_app
```

### Workflow

1. **Settings**: Enter your OpenRouter API Key and click "Detect GPU". Save settings.
2. **Input**: Paste a YouTube URL and its transcript (from a site like `youtubetotranscript.com`). Click "Run Ingest".
3. **Review**: See the detected viral clips. You can double-click to edit the titles/hooks or hit "Generate Preview" to check the layout.
4. **Process**: Select clips you like, hit "Approve", then go to the Process tab and click "Process All Approved".
5. **Output**: Find your final MP4s and thumbnails in `output/finals/` and `output/thumbs/`.

## Development

- `src/ingest.py`: Handles AI analysis and prompt logic.
- `src/video_processor.py`: Manages downloads, cutting, and Whisper transcription.
- `src/layout_engine.py`: FFmpeg filter builder and rendering logic.
- `src/gui_app.py`: Tkinter interface.
- `src/hardware.py`: GPU and tool detection.
- `src/settings.py`: JSON-based settings storage.

## License

MIT
