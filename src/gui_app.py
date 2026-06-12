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
from . import smart_crop
from . import utils

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube Shorts Viral Moments Generator")
        self.geometry("1000x850")

        self.settings = settings.load_settings()
        self.ingest_result = None
        self.approved_clips = [] # List of dicts with 'clip_data', 'srt_path', 'crop_x', 'out_clip'
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

        ttk.Label(frame, text="AI Provider:").grid(row=0, column=0, sticky="w", pady=5)
        self.cmb_provider = ttk.Combobox(frame, values=["openrouter", "gemini", "claude", "openai", "custom"], state="readonly")
        self.cmb_provider.set(self.settings.get("provider", "openrouter"))
        self.cmb_provider.grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_api_key = ttk.Entry(frame, width=50, show="*")
        self.ent_api_key.insert(0, self.settings.get("api_key", ""))
        self.ent_api_key.grid(row=1, column=1, sticky="w", padx=5)

        def toggle_key():
            show = "" if self.ent_api_key.cget("show") == "*" else "*"
            self.ent_api_key.config(show=show)
        ttk.Button(frame, text="Show/Hide", command=toggle_key).grid(row=1, column=2, padx=5)

        ttk.Label(frame, text="Model:").grid(row=2, column=0, sticky="w", pady=5)
        self.cmb_model = ttk.Combobox(frame, width=47)
        self.cmb_model.set(self.settings.get("model", "google/gemini-2.0-flash-001"))
        self.cmb_model.grid(row=2, column=1, sticky="w", padx=5)

        def refresh_models():
            config = {"provider": self.cmb_provider.get(), "api_key": self.ent_api_key.get()}
            models = ingest.fetch_available_models(config)
            if models:
                self.cmb_model.config(values=models)
                self.cmb_model.set(models[0])
                self.log(f"Fetched {len(models)} models.")
            else:
                self.log("No models fetched.")
        ttk.Button(frame, text="Refresh Models", command=refresh_models).grid(row=2, column=2, padx=5)

        ttk.Label(frame, text="Custom Endpoint:").grid(row=3, column=0, sticky="w", pady=5)
        self.ent_endpoint = ttk.Entry(frame, width=50)
        self.ent_endpoint.insert(0, self.settings.get("endpoint", ""))
        self.ent_endpoint.grid(row=3, column=1, sticky="w", padx=5)

        ttk.Separator(frame, orient="horizontal").grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(frame, text="Whisper Model:").grid(row=5, column=0, sticky="w", pady=5)
        self.cmb_whisper = ttk.Combobox(frame, values=["tiny", "base", "small", "medium"], state="readonly")
        self.cmb_whisper.set(self.settings.get("whisper_model", "tiny"))
        self.cmb_whisper.grid(row=5, column=1, sticky="w", padx=5)

        ttk.Label(frame, text="Language:").grid(row=6, column=0, sticky="w", pady=5)
        self.cmb_lang = ttk.Combobox(frame, values=["id", "en"], state="readonly")
        self.cmb_lang.set(self.settings.get("language", "id"))
        self.cmb_lang.grid(row=6, column=1, sticky="w", padx=5)

        # Subtitle Style
        ttk.Label(frame, text="Subtitle Style:").grid(row=7, column=0, sticky="w", pady=5)
        self.cmb_style = ttk.Combobox(frame, values=["Clean", "Minimal", "Shorts"], state="readonly")
        self.cmb_style.set(self.settings.get("subtitle_style", "Shorts"))
        self.cmb_style.grid(row=7, column=1, sticky="w", padx=5)

        ttk.Label(frame, text="Detected GPU:").grid(row=8, column=0, sticky="w", pady=5)
        self.lbl_gpu = ttk.Label(frame, text=self.settings.get("gpu_type", "none"))
        self.lbl_gpu.grid(row=8, column=1, sticky="w", padx=5)

        def run_gpu_detect():
            gpu = hardware.detect_gpu()
            self.lbl_gpu.config(text=gpu)
            self.log(f"GPU Detection: {gpu}")
        ttk.Button(frame, text="Detect GPU", command=run_gpu_detect).grid(row=8, column=2, padx=5)

        def save():
            self.settings.update({
                "provider": self.cmb_provider.get(),
                "api_key": self.ent_api_key.get(),
                "model": self.cmb_model.get(),
                "endpoint": self.ent_endpoint.get(),
                "whisper_model": self.cmb_whisper.get(),
                "language": self.cmb_lang.get(),
                "subtitle_style": self.cmb_style.get(),
                "gpu_type": self.lbl_gpu.cget("text")
            })
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

    def run_ingest_thread(self):
        url = self.ent_url.get().strip()
        transcript = self.txt_transcript.get("1.0", "end").strip()
        if not url: return
        self.btn_run_ingest.config(state="disabled")
        self.log("Starting ingestion process...")
        provider_config = {
            "provider": self.cmb_provider.get(), "api_key": self.ent_api_key.get(),
            "model": self.cmb_model.get(), "endpoint": self.ent_endpoint.get()
        }
        def worker():
            try:
                result = ingest.collect_inputs(url, transcript, self.gemini_json_content, provider_config=provider_config)
                self.ingest_result = result
                self.after(0, self.on_ingest_done)
            except Exception as e:
                self.log(f"Ingest Error: {e}")
                self.after(0, lambda: self.btn_run_ingest.config(state="normal"))
        threading.Thread(target=worker, daemon=True).start()

    def on_ingest_done(self):
        self.btn_run_ingest.config(state="normal")
        self.log(f"Ingest complete. Found {len(self.ingest_result['clips'])} clips.")
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
            self.tree.column(col, width=100 if col not in ["Title", "Hook"] else 250)
        self.tree.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(frame, command=self.tree.yview); sb.pack(side="right", fill="y")
        self.tree.config(yscrollcommand=sb.set)

        btn_frame = ttk.Frame(self.tab_review, padding=10); btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Edit Fields", command=self.edit_selected_clip).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Edit Transcript", command=self.edit_transcript).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Generate Preview", command=self.generate_preview).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Re-Burn Subtitles", command=self.re_burn_subtitles).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Approve & Process", command=self.approve_clip).pack(side="left", padx=5)

    def populate_review_tree(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        if not self.ingest_result: return
        for clip in self.ingest_result["clips"]:
            self.tree.insert("", "end", values=(clip["clip"], clip["start"], clip["end"], clip["title"], clip["hook"]))

    def get_selected_clip(self):
        sel = self.tree.selection()
        if not sel: return None
        clip_id = self.tree.item(sel[0])["values"][0]
        return next(c for c in self.ingest_result["clips"] if c["clip"] == clip_id)

    def edit_selected_clip(self):
        clip = self.get_selected_clip()
        if not clip: return
        top = tk.Toplevel(self); top.title(f"Edit Clip {clip['clip']}")
        fields = ["start", "end", "title", "hook", "caption"]
        ents = {}
        for f in fields:
            ttk.Label(top, text=f.capitalize()).pack(padx=10)
            ent = tk.Text(top, height=3) if f in ["hook", "caption"] else ttk.Entry(top, width=50)
            val = clip[f]
            if f in ["hook", "caption"]: ent.insert("1.0", val)
            else: ent.insert(0, f"{val}")
            ent.pack(padx=10, pady=5); ents[f] = ent
        def save():
            for f in fields: clip[f] = ents[f].get("1.0", "end").strip() if f in ["hook", "caption"] else ents[f].get().strip()
            self.populate_review_tree(); top.destroy()
        ttk.Button(top, text="Save", command=save).pack(pady=10)

    def edit_transcript(self):
        clip = self.get_selected_clip()
        if not clip: return
        # Check if srt exists in processed clips
        approved = next((c for c in self.approved_clips if c['clip_data']['clip'] == clip['clip']), None)
        if not approved or not Path(approved['srt_path']).exists():
            messagebox.showwarning("Warning", "Process the clip once first to generate a transcript.")
            return

        top = tk.Toplevel(self); top.title(f"Edit SRT - Clip {clip['clip']}")
        txt = tk.Text(top, width=80, height=20); txt.pack(padx=10, pady=10)
        with open(approved['srt_path'], "r", encoding="utf-8") as f: txt.insert("1.0", f.read())
        def save():
            with open(approved['srt_path'], "w", encoding="utf-8") as f: f.write(txt.get("1.0", "end").strip())
            messagebox.showinfo("Saved", "Transcript updated."); top.destroy()
        ttk.Button(top, text="Save SRT", command=save).pack(pady=5)

    def re_burn_subtitles(self):
        clip = self.get_selected_clip()
        if not clip: return
        approved = next((c for c in self.approved_clips if c['clip_data']['clip'] == clip['clip']), None)
        if not approved: return
        self.log(f"Re-burning subtitles for clip {clip['clip']}...")
        def worker():
            try:
                title_safe = re.sub(r'[^\w\s-]', '', clip["title"]).strip().replace(' ', '_')
                final_path = Path("output/finals") / f"clip_{clip['clip']}_{title_safe}.mp4"
                thumb_path = Path("output/thumbs") / f"thumb_{clip['clip']}_{title_safe}.jpg"
                layout_engine.make_final(
                    approved['out_clip'], "00:00:00", "23:59:59", self.settings["gpu_type"],
                    clip["hook"], clip["caption"], final_path, thumb_path,
                    srt_path=approved['srt_path'], crop_x=approved['crop_x'],
                    style_name=self.settings.get("subtitle_style", "Shorts")
                )
                self.log(f"Re-burn complete: {final_path}")
                utils.open_file(final_path)
            except Exception as e: self.log(f"Re-burn Error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def generate_preview(self):
        clip = self.get_selected_clip()
        if not clip: return
        self.log(f"Generating preview for clip {clip['clip']}...")

        # Check if we have an existing transcript for this clip
        approved = next((c for c in self.approved_clips if c['clip_data']['clip'] == clip['clip']), None)
        srt_path = approved['srt_path'] if approved else None

        def worker():
            try:
                source = video_processor.download_video(self.ingest_result["url"])
                out_path = Path("temp") / f"preview_{clip['clip']}.mp4"
                crop_x = smart_crop.get_smart_crop_params(source, clip["start"], clip["end"])
                layout_engine.make_preview(
                    source, clip["start"], clip["end"], self.settings["gpu_type"],
                    clip["hook"], clip["caption"], out_path, srt_path=srt_path, crop_x=crop_x,
                    style_name=self.settings.get("subtitle_style", "Shorts")
                )
                utils.open_file(out_path)
            except Exception as e: self.log(f"Preview Error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def approve_clip(self):
        clip = self.get_selected_clip()
        if not clip: return
        self.log(f"Processing clip {clip['clip']}...")
        provider_config = {
            "provider": self.cmb_provider.get(), "api_key": self.ent_api_key.get(),
            "model": self.cmb_model.get(), "endpoint": self.ent_endpoint.get()
        }
        def worker():
            try:
                out_clip, srt_path, crop_x = video_processor.process_clip(
                    clip, self.ingest_result["url"], self.settings["gpu_type"],
                    self.settings["whisper_model"], self.settings["language"],
                    youtube_transcript=self.ingest_result["transcript"], provider_config=provider_config
                )
                self.approved_clips.append({'clip_data': clip, 'srt_path': srt_path, 'crop_x': crop_x, 'out_clip': out_clip})
                self.after(0, self.update_process_listbox)
                self.log(f"Clip {clip['clip']} ready for final process.")
            except Exception as e: self.log(f"Process Error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    # --- Process Tab ---
    def setup_process_tab(self):
        frame = ttk.Frame(self.tab_process, padding=20); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Ready for Final Render:").pack(anchor="w")
        self.lb_approved = tk.Listbox(frame, height=10); self.lb_approved.pack(fill="x", pady=10)
        self.btn_process = ttk.Button(frame, text="Process All Approved", command=self.run_process_thread); self.btn_process.pack()
        self.progress = ttk.Progressbar(frame, orient="horizontal", length=400, mode="determinate"); self.progress.pack(fill="x", pady=20)

    def update_process_listbox(self):
        self.lb_approved.delete(0, "end")
        for item in self.approved_clips:
            self.lb_approved.insert("end", f"Clip {item['clip_data']['clip']}: {item['clip_data']['title']}")

    def run_process_thread(self):
        if not self.approved_clips: return
        self.btn_process.config(state="disabled")
        self.progress["value"] = 0; self.progress["maximum"] = len(self.approved_clips)
        def worker():
            try:
                for i, item in enumerate(self.approved_clips):
                    clip = item['clip_data']
                    title_safe = re.sub(r'[^\w\s-]', '', clip["title"]).strip().replace(' ', '_')
                    final_path = Path("output/finals") / f"clip_{clip['clip']}_{title_safe}.mp4"
                    thumb_path = Path("output/thumbs") / f"thumb_{clip['clip']}_{title_safe}.jpg"
                    layout_engine.make_final(
                        item['out_clip'], "00:00:00", "23:59:59", self.settings["gpu_type"],
                        clip["hook"], clip["caption"], final_path, thumb_path,
                        srt_path=item['srt_path'], crop_x=item['crop_x'],
                        style_name=self.settings.get("subtitle_style", "Shorts")
                    )
                    self.after(0, lambda val=i+1: self.progress.configure(value=val))
                self.after(0, lambda: messagebox.showinfo("Done", "All clips processed!"))
                self.after(0, lambda: self.btn_process.config(state="normal"))
                utils.open_file(Path("output/finals"))
            except Exception as e: self.log(f"Final Render Error: {e}")
        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    App().mainloop()
