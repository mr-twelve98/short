import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import os
import json
import re
from pathlib import Path

from . import settings
from . import hardware
from . import ingest
from . import video_processor
from . import layout_engine

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube Shorts Viral Moments Generator")
        self.geometry("1000x800")

        self.settings = settings.load_settings()
        self.ingest_result = None
        self.approved_clips = []
        self.log_queue = queue.Queue()

        self.setup_ui()
        self.update_log_from_queue()

    def setup_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)

        self.tab_settings = ttk.Frame(self.notebook)
        self.tab_input = ttk.Frame(self.notebook)
        self.tab_review = ttk.Frame(self.notebook)
        self.tab_process = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_settings, text="Settings")
        self.notebook.add(self.tab_input, text="Input")
        self.notebook.add(self.tab_review, text="Review")
        self.notebook.add(self.tab_process, text="Process")

        self.setup_settings_tab()
        self.setup_input_tab()
        self.setup_review_tab()
        self.setup_process_tab()

        # Log window at the bottom
        log_frame = ttk.LabelFrame(self, text="Status Logs")
        log_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.log_text = tk.Text(log_frame, height=8, state="disabled")
        self.log_text.pack(side="left", expand=True, fill="x")

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, message):
        self.log_queue.put(message)

    def update_log_from_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_text.config(state="normal")
            self.log_text.insert("end", f"{msg}\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.after(100, self.update_log_from_queue)

    # --- Settings Tab ---
    def setup_settings_tab(self):
        frame = ttk.Frame(self.tab_settings, padding=20)
        frame.pack(fill="both", expand=True)

        # Provider
        ttk.Label(frame, text="AI Provider:").grid(row=0, column=0, sticky="w", pady=5)
        self.cmb_provider = ttk.Combobox(frame, values=["openrouter", "gemini", "claude", "openai", "custom"], state="readonly")
        self.cmb_provider.set(self.settings.get("provider", "openrouter"))
        self.cmb_provider.grid(row=0, column=1, sticky="w", padx=5)

        # API Key
        ttk.Label(frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_api_key = ttk.Entry(frame, width=50, show="*")
        self.ent_api_key.insert(0, self.settings.get("api_key", ""))
        self.ent_api_key.grid(row=1, column=1, sticky="w", padx=5)

        def toggle_key():
            if self.ent_api_key.cget("show") == "*":
                self.ent_api_key.config(show="")
            else:
                self.ent_api_key.config(show="*")

        ttk.Button(frame, text="Show/Hide", command=toggle_key).grid(row=1, column=2, padx=5)

        # Model
        ttk.Label(frame, text="Model:").grid(row=2, column=0, sticky="w", pady=5)
        self.cmb_model = ttk.Combobox(frame, width=47)
        self.cmb_model.set(self.settings.get("model", "google/gemini-2.0-flash-001"))
        self.cmb_model.grid(row=2, column=1, sticky="w", padx=5)

        def refresh_models():
            config = {
                "provider": self.cmb_provider.get(),
                "api_key": self.ent_api_key.get()
            }
            self.log(f"Fetching models for {config['provider']}...")
            models = ingest.fetch_available_models(config)
            if models:
                self.cmb_model.config(values=models)
                self.cmb_model.set(models[0])
                self.log(f"Fetched {len(models)} models.")
            else:
                self.log("No models fetched. Check API key.")

        ttk.Button(frame, text="Refresh Models", command=refresh_models).grid(row=2, column=2, padx=5)

        # Custom Endpoint
        ttk.Label(frame, text="Custom Endpoint:").grid(row=3, column=0, sticky="w", pady=5)
        self.ent_endpoint = ttk.Entry(frame, width=50)
        self.ent_endpoint.insert(0, self.settings.get("endpoint", ""))
        self.ent_endpoint.grid(row=3, column=1, sticky="w", padx=5)

        # Separator
        ttk.Separator(frame, orient="horizontal").grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)

        # Whisper Model
        ttk.Label(frame, text="Whisper Model:").grid(row=5, column=0, sticky="w", pady=5)
        self.cmb_whisper = ttk.Combobox(frame, values=["tiny", "base", "small", "medium"], state="readonly")
        self.cmb_whisper.set(self.settings.get("whisper_model", "tiny"))
        self.cmb_whisper.grid(row=5, column=1, sticky="w", padx=5)

        # Language
        ttk.Label(frame, text="Language:").grid(row=6, column=0, sticky="w", pady=5)
        self.cmb_lang = ttk.Combobox(frame, values=["id", "en"], state="readonly")
        self.cmb_lang.set(self.settings.get("language", "id"))
        self.cmb_lang.grid(row=6, column=1, sticky="w", padx=5)

        # GPU Result
        ttk.Label(frame, text="Detected GPU:").grid(row=7, column=0, sticky="w", pady=5)
        self.lbl_gpu = ttk.Label(frame, text=self.settings.get("gpu_type", "none"))
        self.lbl_gpu.grid(row=7, column=1, sticky="w", padx=5)

        def run_gpu_detect():
            gpu = hardware.detect_gpu()
            self.lbl_gpu.config(text=gpu)
            self.log(f"GPU Detection: {gpu}")

        ttk.Button(frame, text="Detect GPU", command=run_gpu_detect).grid(row=7, column=2, padx=5)

        # Save Button
        def save():
            self.settings["provider"] = self.cmb_provider.get()
            self.settings["api_key"] = self.ent_api_key.get()
            self.settings["model"] = self.cmb_model.get()
            self.settings["endpoint"] = self.ent_endpoint.get()
            self.settings["whisper_model"] = self.cmb_whisper.get()
            self.settings["language"] = self.cmb_lang.get()
            self.settings["gpu_type"] = self.lbl_gpu.cget("text")
            settings.save_settings(self.settings)
            messagebox.showinfo("Success", "Settings saved!")

        ttk.Button(frame, text="Save Settings", command=save).grid(row=8, column=1, sticky="w", pady=20)

    # --- Input Tab ---
    def setup_input_tab(self):
        frame = ttk.Frame(self.tab_input, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="YouTube URL:").pack(anchor="w")
        self.ent_url = ttk.Entry(frame, width=80)
        self.ent_url.pack(anchor="w", pady=(0, 10))

        ttk.Label(frame, text="Raw Transcript:").pack(anchor="w")
        self.txt_transcript = tk.Text(frame, height=10)
        self.txt_transcript.pack(fill="x", pady=(0, 10))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(anchor="w")

        ttk.Button(btn_frame, text="Load Gemini JSON File", command=self.load_gemini_json_file).pack(side="left", padx=(0, 10))

        self.btn_run_ingest = ttk.Button(btn_frame, text="Run Ingest & Analysis", command=self.run_ingest_thread)
        self.btn_run_ingest.pack(side="left")

        self.gemini_json_content = ""

    def load_gemini_json_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text/JSON files", "*.txt *.json"), ("All files", "*.*")])
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self.gemini_json_content = f.read()
            self.log(f"Loaded Gemini data from {path}")
            messagebox.showinfo("Loaded", "Gemini data loaded. You can now 'Run Ingest'.")

    def run_ingest_thread(self):
        url = self.ent_url.get().strip()
        transcript = self.txt_transcript.get("1.0", "end").strip()
        gemini_json = self.gemini_json_content

        if not url:
            messagebox.showerror("Error", "YouTube URL is required.")
            return

        if not transcript and not gemini_json:
            messagebox.showerror("Error", "Provide a transcript or load a Gemini JSON file.")
            return

        self.btn_run_ingest.config(state="disabled")
        self.log("Starting ingestion process...")

        # Build provider config from current UI/settings
        provider_config = {
            "provider": self.cmb_provider.get(),
            "api_key": self.ent_api_key.get(),
            "model": self.cmb_model.get(),
            "endpoint": self.ent_endpoint.get()
        }

        def worker():
            try:
                result = ingest.collect_inputs(url, transcript, gemini_json, provider_config=provider_config)
                self.ingest_result = result
                self.after(0, self.on_ingest_done)
            except Exception as e:
                self.log(f"Ingest Error: {e}")
                self.after(0, lambda: messagebox.showerror("Ingest Error", str(e)))
                self.after(0, lambda: self.btn_run_ingest.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def on_ingest_done(self):
        self.btn_run_ingest.config(state="normal")
        self.log(f"Ingest complete. Found {len(self.ingest_result['clips'])} clips.")
        if self.ingest_result.get("warnings"):
            for w in self.ingest_result["warnings"]:
                self.log(f"Warning: {w}")

        self.populate_review_tree()
        self.notebook.select(self.tab_review)

    # --- Review Tab ---
    def setup_review_tab(self):
        frame = ttk.Frame(self.tab_review, padding=10)
        frame.pack(fill="both", expand=True)

        cols = ("Clip", "Start", "End", "Title", "Hook")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=15)
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100 if col != "Title" and col != "Hook" else 250)

        self.tree.pack(fill="both", expand=True, side="left")

        sb = ttk.Scrollbar(frame, command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.config(yscrollcommand=sb.set)

        btn_frame = ttk.Frame(self.tab_review, padding=10)
        btn_frame.pack(fill="x")

        ttk.Button(btn_frame, text="Edit Selected Clip", command=self.edit_selected_clip).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Generate Preview", command=self.generate_preview).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Approve for Processing", command=self.approve_clip).pack(side="left", padx=5)

    def populate_review_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        if not self.ingest_result:
            return

        for clip in self.ingest_result["clips"]:
            self.tree.insert("", "end", values=(
                clip["clip"],
                clip["start"],
                clip["end"],
                clip["title"],
                clip["hook"]
            ))

    def edit_selected_clip(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])
        clip_id = item["values"][0]
        clip = next(c for c in self.ingest_result["clips"] if c["clip"] == clip_id)

        top = tk.Toplevel(self)
        top.title(f"Edit Clip {clip_id}")
        top.geometry("500x500")

        fields = ["start", "end", "title", "hook", "caption", "why"]
        entries = {}

        for i, field in enumerate(fields):
            ttk.Label(top, text=f"{field.capitalize()}:").pack(anchor="w", padx=10)
            if field in ["hook", "caption", "why"]:
                ent = tk.Text(top, height=3)
                ent.insert("1.0", clip[field])
            else:
                ent = ttk.Entry(top, width=50)
                ent.insert(0, clip[field])
            ent.pack(fill="x", padx=10, pady=(0, 5))
            entries[field] = ent

        def save_edit():
            for field in fields:
                if field in ["hook", "caption", "why"]:
                    clip[field] = entries[field].get("1.0", "end").strip()
                else:
                    clip[field] = entries[field].get().strip()
            self.populate_review_tree()
            top.destroy()

        ttk.Button(top, text="Save Changes", command=save_edit).pack(pady=10)

    def generate_preview(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])
        clip_id = item["values"][0]
        clip = next(c for c in self.ingest_result["clips"] if c["clip"] == clip_id)

        self.log(f"Generating preview for clip {clip_id}...")

        def worker():
            try:
                source = video_processor.download_video(self.ingest_result["url"])
                out_path = Path("temp") / f"preview_{clip_id}.mp4"
                layout_engine.make_preview(
                    source, clip["start"], clip["end"],
                    self.settings["gpu_type"], clip["hook"], clip["caption"],
                    out_path
                )
                self.log(f"Preview ready: {out_path}")
                if hasattr(os, 'startfile'):
                    os.startfile(out_path)
                else:
                    self.log("os.startfile not available on this platform.")
            except Exception as e:
                self.log(f"Preview Error: {e}")
                self.after(0, lambda: messagebox.showerror("Preview Error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def approve_clip(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])
        clip_id = item["values"][0]
        clip = next(c for c in self.ingest_result["clips"] if c["clip"] == clip_id)

        if clip not in self.approved_clips:
            self.approved_clips.append(clip)
            self.log(f"Clip {clip_id} approved.")
            self.update_process_listbox()
        else:
            self.log(f"Clip {clip_id} already approved.")

    # --- Process Tab ---
    def setup_process_tab(self):
        frame = ttk.Frame(self.tab_process, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Approved Clips to Process:").pack(anchor="w")
        self.lb_approved = tk.Listbox(frame, height=10)
        self.lb_approved.pack(fill="x", pady=(0, 10))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x")

        ttk.Button(btn_frame, text="Remove Selected", command=self.remove_approved_clip).pack(side="left", padx=(0, 10))
        self.btn_process = ttk.Button(btn_frame, text="Process All Approved", command=self.run_process_thread)
        self.btn_process.pack(side="left")

        self.progress = ttk.Progressbar(frame, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(fill="x", pady=20)

    def remove_approved_clip(self):
        selection = self.lb_approved.curselection()
        if selection:
            idx = selection[0]
            clip = self.approved_clips.pop(idx)
            self.log(f"Removed Clip {clip['clip']} from processing list.")
            self.update_process_listbox()

    def update_process_listbox(self):
        self.lb_approved.delete(0, "end")
        for clip in self.approved_clips:
            self.lb_approved.insert("end", f"Clip {clip['clip']}: {clip['title']}")

    def run_process_thread(self):
        if not self.approved_clips:
            messagebox.showwarning("Warning", "No clips approved.")
            return

        self.btn_process.config(state="disabled")
        self.progress["value"] = 0
        self.progress["maximum"] = len(self.approved_clips)

        def worker():
            try:
                for i, clip in enumerate(self.approved_clips):
                    self.log(f"[{i+1}/{len(self.approved_clips)}] Processing clip {clip['clip']}...")

                    # 1. Download, Cut & Transcribe
                    clip_path, srt_path = video_processor.process_clip(
                        clip, self.ingest_result["url"],
                        self.settings["gpu_type"], self.settings["whisper_model"],
                        self.settings["language"]
                    )

                    # 2. Final Render
                    title_safe = re.sub(r'[^\w\s-]', '', clip["title"]).strip().replace(' ', '_')
                    final_path = Path("output/finals") / f"clip_{clip['clip']}_{title_safe}.mp4"
                    thumb_path = Path("output/thumbs") / f"thumb_{clip['clip']}_{title_safe}.jpg"

                    layout_engine.make_final(
                        clip_path, "00:00:00", "23:59:59", # Corrected timestamp
                        self.settings["gpu_type"], clip["hook"], clip["caption"],
                        final_path, thumb_path, srt_path=srt_path
                    )

                    self.log(f"Finished: {final_path}")
                    self.after(0, lambda val=i+1: self.progress.configure(value=val))

                self.after(0, self.on_process_done)
            except Exception as e:
                self.log(f"Process Error: {e}")
                self.after(0, lambda: messagebox.showerror("Process Error", str(e)))
                self.after(0, lambda: self.btn_process.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def on_process_done(self):
        self.btn_process.config(state="normal")
        messagebox.showinfo("Done", "All clips processed successfully!")
        if hasattr(os, 'startfile'):
            os.startfile(Path("output/finals"))

if __name__ == "__main__":
    app = App()
    app.mainloop()
