import sys
import os
import threading
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QTextEdit, QLabel, QProgressBar,
                             QFileDialog, QComboBox, QMessageBox, QTabWidget, QGroupBox,
                             QScrollArea, QFormLayout)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from .downloader import download_video, get_video_info
from .transcriber import get_transcript, transcribe_with_whisper, format_transcript_for_prompt
from .clip_selector import generate_gemini_prompt, parse_gemini_response
from .face_detector import process_video_face_tracking
from .subtitle_handler import generate_srt, burn_subtitles
from .encoder import get_best_encoder, check_ffmpeg
from .config import ConfigManager

class WorkerSignals(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

class VideoShortsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.current_video_info = None
        self.current_transcript = None
        self.worker_signals = WorkerSignals()
        self.worker_signals.progress.connect(self.update_status)
        self.worker_signals.error.connect(self.on_error)
        self.init_ui()

    def on_error(self, message):
        QMessageBox.critical(self, "Error", message)
        self.fetch_btn.setEnabled(True)
        self.process_clips_btn.setEnabled(True)

    def init_ui(self):
        self.setWindowTitle("YouTube Shorts Generator")
        self.setMinimumSize(900, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Main Process
        process_tab = QWidget()
        self.tabs.addTab(process_tab, "Generator")
        self.setup_process_tab(process_tab)

        # Tab 2: Settings
        settings_tab = QWidget()
        self.tabs.addTab(settings_tab, "Settings")
        self.setup_settings_tab(settings_tab)

        # Bottom: Progress and Status
        bottom_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Ready")
        bottom_layout.addWidget(self.progress_bar)
        bottom_layout.addWidget(self.status_label)
        main_layout.addLayout(bottom_layout)

        # Check FFmpeg
        if not check_ffmpeg():
            QMessageBox.critical(self, "FFmpeg Missing",
                               "FFmpeg was not found on your system. Please install it to use this application.")

    def setup_process_tab(self, tab):
        layout = QVBoxLayout(tab)

        # URL Input
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube URL here...")
        self.fetch_btn = QPushButton("Fetch Video & Transcript")
        self.fetch_btn.clicked.connect(self.start_fetch)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.fetch_btn)
        layout.addLayout(url_layout)

        # Content Layout
        content_layout = QHBoxLayout()

        # Left side: Transcript and Prompt
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Transcript:"))
        self.transcript_display = QTextEdit()
        self.transcript_display.setReadOnly(True)
        left_layout.addWidget(self.transcript_display)

        self.gen_prompt_btn = QPushButton("Generate & Copy Gemini Prompt")
        self.gen_prompt_btn.clicked.connect(self.copy_gemini_prompt)
        self.gen_prompt_btn.setEnabled(False)
        left_layout.addWidget(self.gen_prompt_btn)

        content_layout.addLayout(left_layout, 1)

        # Right side: Gemini Response and Processing
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Paste Gemini Response here:"))
        self.gemini_input = QTextEdit()
        right_layout.addWidget(self.gemini_input)

        self.process_clips_btn = QPushButton("Generate Shorts")
        self.process_clips_btn.clicked.connect(self.start_processing)
        self.process_clips_btn.setEnabled(False)
        right_layout.addWidget(self.process_clips_btn)

        content_layout.addLayout(right_layout, 1)
        layout.addLayout(content_layout)

    def setup_settings_tab(self, tab):
        layout = QFormLayout(tab)

        self.whisper_model_combo = QComboBox()
        self.whisper_model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.whisper_model_combo.setCurrentText(self.config_manager.get("whisper_model"))
        self.whisper_model_combo.currentTextChanged.connect(lambda v: self.config_manager.set("whisper_model", v))
        layout.addRow("Whisper Model:", self.whisper_model_combo)

        output_layout = QHBoxLayout()
        self.output_dir_label = QLabel(self.config_manager.get("output_folder"))
        self.change_output_btn = QPushButton("Change")
        self.change_output_btn.clicked.connect(self.change_output_dir)
        output_layout.addWidget(self.output_dir_label)
        output_layout.addWidget(self.change_output_btn)
        layout.addRow("Output Directory:", output_layout)

        self.gpu_priority_label = QLabel(", ".join(self.config_manager.get("gpu_priority")))
        layout.addRow("GPU Priority:", self.gpu_priority_label)

    def change_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.config_manager.set("output_folder", dir_path)
            self.output_dir_label.setText(dir_path)

    def update_status(self, progress, message):
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)

    def start_fetch(self):
        url = self.url_input.text().strip()
        if not url:
            return

        self.fetch_btn.setEnabled(False)
        self.update_status(10, "Fetching video info...")

        thread = threading.Thread(target=self.fetch_task, args=(url,))
        thread.start()

    def fetch_task(self, url):
        try:
            info = get_video_info(url)
            if not info:
                raise Exception("Could not fetch video info.")

            self.current_video_info = info
            video_id = info.get('id')

            self.worker_signals.progress.emit(30, "Fetching transcript...")
            transcript = get_transcript(video_id)

            if not transcript:
                self.worker_signals.progress.emit(40, "No YouTube captions found. Downloading audio for Whisper...")
                download_info = download_video(url)
                self.worker_signals.progress.emit(60, "Transcribing with Whisper...")
                transcript = transcribe_with_whisper(download_info['path'], self.config_manager.get("whisper_model"))

            self.current_transcript = transcript
            transcript_text = format_transcript_for_prompt(transcript)

            # Use QMetaObject to update UI text safely or another signal
            # For now, let's just use the status signal to finish
            self.worker_signals.progress.emit(100, "Fetch complete.")

            # Schedule UI updates back to main thread
            from PyQt6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self.transcript_display, "setPlainText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, transcript_text))
            QMetaObject.invokeMethod(self.gen_prompt_btn, "setEnabled", Qt.ConnectionType.QueuedConnection, Q_ARG(bool, True))
            QMetaObject.invokeMethod(self.process_clips_btn, "setEnabled", Qt.ConnectionType.QueuedConnection, Q_ARG(bool, True))
            QMetaObject.invokeMethod(self.fetch_btn, "setEnabled", Qt.ConnectionType.QueuedConnection, Q_ARG(bool, True))

        except Exception as e:
            self.worker_signals.error.emit(str(e))
            self.worker_signals.progress.emit(0, f"Error: {str(e)}")

    def copy_gemini_prompt(self):
        if not self.current_transcript:
            return

        transcript_text = format_transcript_for_prompt(self.current_transcript)
        prompt = generate_gemini_prompt(transcript_text)
        QApplication.clipboard().setText(prompt)
        QMessageBox.information(self, "Prompt Copied", "Gemini prompt has been copied to your clipboard. Paste it into Gemini and then copy the response back here.")

    def start_processing(self):
        gemini_text = self.gemini_input.toPlainText().strip()
        if not gemini_text:
            QMessageBox.warning(self, "Missing Input", "Please paste the Gemini response first.")
            return

        clips = parse_gemini_response(gemini_text)
        if not clips:
            QMessageBox.warning(self, "Parse Error", "Could not find any clips in the Gemini response. Please ensure it follows the expected format.")
            return

        self.process_clips_btn.setEnabled(False)
        thread = threading.Thread(target=self.process_task, args=(clips,))
        thread.start()

    def process_task(self, clips):
        try:
            url = self.url_input.text().strip()
            output_root = self.config_manager.get("output_folder")
            if not os.path.exists(output_root):
                os.makedirs(output_root)

            self.worker_signals.progress.emit(5, "Downloading video...")
            video_info = download_video(url, output_dir=os.path.join(output_root, "temp"))
            video_path = video_info['path']

            encoder = get_best_encoder(self.config_manager.get("gpu_priority"))

            for i, clip in enumerate(clips):
                self.worker_signals.progress.emit(10 + int(i / len(clips) * 80), f"Processing Clip {i+1}/{len(clips)}: {clip['title']}")

                # 1. Face tracking and Dynamic Crop
                clip_output_name = f"clip_{i+1}_{slugify(clip['title'])}.mp4"
                clip_path = os.path.join(output_root, clip_output_name)

                tracked_video = process_video_face_tracking(
                    video_path, clip_path,
                    clip['start'], clip['end'],
                    encoder=encoder
                )

                # 2. Generate SRT
                srt_path = clip_path + ".srt"
                generate_srt(self.current_transcript, srt_path, start_offset=clip['start'], end_offset=clip['end'])

                # 3. Burn subtitles
                final_path = os.path.join(output_root, f"final_{clip_output_name}")
                burn_subtitles(tracked_video, srt_path, final_path, encoder=encoder)

                # Cleanup intermediate
                if os.path.exists(tracked_video):
                    os.remove(tracked_video)
                if os.path.exists(srt_path):
                    os.remove(srt_path)

            # Cleanup original video and temp folder
            if os.path.exists(video_path):
                os.remove(video_path)

            temp_dir = os.path.dirname(video_path)
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)

            self.worker_signals.progress.emit(100, f"Successfully generated {len(clips)} shorts!")
            from PyQt6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self.process_clips_btn, "setEnabled", Qt.ConnectionType.QueuedConnection, Q_ARG(bool, True))

        except Exception as e:
            self.worker_signals.error.emit(str(e))
            self.worker_signals.progress.emit(0, f"Error: {str(e)}")
            from PyQt6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self.process_clips_btn, "setEnabled", Qt.ConnectionType.QueuedConnection, Q_ARG(bool, True))

def slugify(text):
    import re
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')

def main():
    app = QApplication(sys.argv)
    window = VideoShortsApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
