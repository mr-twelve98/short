# YouTube Shorts Viral Moments Generator

A Python desktop app (Windows) to automatically identify, cut, and process viral moments from YouTube videos for TikTok and YouTube Shorts.

## Features

- **AI Analysis**: Uses Gemini 2.0 Flash (via OpenRouter) to find the best moments from a transcript.
- **Hardware Acceleration**: Auto-detects and uses NVIDIA (nvenc), AMD (amf), or Intel (qsv) GPUs for fast encoding.
- **Auto-Transcribe**: Generates accurate subtitles using `faster-whisper`.
- **Layout Engine**: Automatic 9:16 vertical video with blurred background and text overlays.
- **Interactive GUI**: Review, edit, and approve clips before final rendering.

---

## Prerequisites

- Windows 10/11
- Python 3.10 or newer installed. [Download here](https://www.python.org/downloads/)
- FFmpeg installed.
- yt-dlp installed.
- An OpenRouter API Key ([openrouter.ai](https://openrouter.ai/)).

---

## 1. Install FFmpeg & yt-dlp

### Option A: Using winget (Easiest)
Open Command Prompt (`cmd`) or PowerShell and run:
```cmd
winget install Gyan.FFmpeg
winget install yt-dlp.yt-dlp
```
**Close and reopen your terminal after installation.**

### Option B: Manual Install
1. **FFmpeg**: Download from [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/). Extract the ZIP to `C:\ffmpeg`.
2. **yt-dlp**: Download `yt-dlp.exe` from the [latest releases](https://github.com/yt-dlp/yt-dlp/releases) and place it in `C:\bin`.

#### Add to Windows PATH
1. Press `Win + R`, type `sysdm.cpl`, press Enter.
2. Go to **Advanced** → **Environment Variables**.
3. Under **User Variables**, find **Path** → **Edit** → **New**.
4. Add `C:\ffmpeg\bin` (or wherever you extracted it) and `C:\bin` (where `yt-dlp.exe` is).
5. Click OK on all windows.
6. Open a new Command Prompt and type:
   ```cmd
   ffmpeg -version
   yt-dlp --version
   ```
   If you see version numbers, you are ready.

---

## 2. Install Python Dependencies

Open Command Prompt in the project folder and run:
```cmd
pip install -r requirements.txt
```

---

## 3. Run the Application

### Important: Ensure src is a package
Make sure there is an empty file named `__init__.py` inside the `src` folder. If it's missing, create it.

### Launch the GUI
From the root project folder (where `requirements.txt` is), run:
```cmd
python -m src.gui_app
```
(If `python` doesn't work, try `py -m src.gui_app`)

You should see the application window appear.

---

## How to Use

### Step 1: Settings
- Go to the **Settings** tab.
- Paste your **OpenRouter API Key**.
- Select your **Whisper Model** (tiny/fastest to medium/slow but accurate).
- Click **Detect GPU** then **Save Settings**.

### Step 2: Input
- Paste your **YouTube URL**.
- Go to `youtubetotranscript.com`, copy the full transcript, and paste it into the **Raw Transcript** box.
- Click **Run Ingest & Analysis**. The AI will detect potential viral clips.

### Step 3: Review
- See the detected clips in the list.
- Select a clip and click **Generate Preview** to see a quick test video.
- Double-click a clip to edit its title, hook, or timestamps if needed.

### Step 4: Process
- Select the clips you like and click **Approve**.
- Go to the **Process** tab and click **Process All Approved**.
- Wait for the progress bar to finish.

### Step 5: Find your videos
- **Final clips**: `output/finals/`
- **Thumbnails**: `output/thumbs/`

---

## Troubleshooting

- **Problem**: `ffmpeg` not recognized
  **Fix**: Add it to your Windows PATH (see Step 1). Close and reopen your terminal.
- **Problem**: `yt-dlp` not recognized
  **Fix**: Add `yt-dlp.exe` folder to PATH or put it in `C:\Windows\System32`.
- **Problem**: `python -m src.gui_app` fails
  **Fix**: Ensure you are in the root project folder and `src/__init__.py` exists.
- **Problem**: GUI freezes during process
  **Fix**: This is expected for heavy work. Wait for the background thread to finish.
- **Problem**: Preview is blank/black
  **Fix**: Your FFmpeg build might be missing `libbluray` or `drawtext` filters. Use the official Gyan build.

---

## File Map

- `src/ingest.py`: AI analysis and prompt logic.
- `src/video_processor.py`: Downloads, cuts, and Whisper transcription.
- `src/layout_engine.py`: FFmpeg filter builder for the 9:16 layout.
- `src/gui_app.py`: Tkinter user interface.
- `src/hardware.py`: GPU detection and tool validation.
- `src/settings.py`: Saves your API key and preferences to `settings.json`.

## License

MIT
