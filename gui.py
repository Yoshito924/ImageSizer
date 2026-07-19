import json
import os
import platform
import queue
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font as tkfont
from tkinterdnd2 import TkinterDnD, DND_FILES
import threading
import traceback
from PIL import Image
from image_processor import process_image, would_overwrite_input

DEFAULT_SETTINGS = {
    "always_on_top": False,
    "crop_type": "none",
    "size_type": "mb",
    "operation": "auto",
    "output_format": "original",
    "filename_pattern": "default",
    "window_width": 950,
    "window_height": 700,
    "window_x": 100,
    "window_y": 100,
    "preset": "カスタム",
    "target_size": 2.0,
    "mb_size": 2,
    "kb_size": 500,
    "width_px": 1920,
    "height_px": 1080,
    "long_edge_px": 1920,
    "aspect_width": 16.0,
    "aspect_height": 9.0,
    "include_crop_type": False,
    "include_size_ratio": False,
    "include_timestamp": False,
    "include_sequential": False,
    "include_preset_name": False,
    "output_destination": "original",
    "warn_on_overwrite": True,
}


class ImageProcessorApp:
    def __init__(self, master):
        self.master = master
        master.title("ImageSizer")

        # 設定をロード
        self.load_settings()

        # プリセットをロード
        self.load_presets()

        # ウィンドウサイズと位置を設定（画面外にならないように調整）
        self.validate_window_position()
        geometry = f"{self.window_width}x{self.window_height}+{self.window_x}+{self.window_y}"
        master.geometry(geometry)
        master.minsize(720, 580)

        self.style = ttk.Style()
        self.configure_styles()
        self.is_processing = False

        # 終了時にワーカーへ停止を通知するイベントと追跡用ハンドル
        self._shutdown_event = threading.Event()
        self._worker_thread = None
        # アプリが Popen で起動した子プロセス（ターミナル等）を登録する
        self._child_processes = []
        self._is_closing = False

        # ウィンドウ位置とサイズ変更のイベントをバインド
        master.bind("<Configure>", self.on_window_configure)

        # アプリケーション終了時に設定を保存
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.create_widgets()
        self.setup_drop_target()

    def _get_theme_colors(self):
        """sv_ttkテーマに合わせた非ttkウィジェット用カラーを返す"""
        style = getattr(self, "style", ttk.Style())
        try:
            bg = style.lookup("TFrame", "background") or "#eef3f9"
        except tk.TclError:
            bg = "#eef3f9"
        return {
            "app_bg": bg,
            "bg": "#ffffff",
            "fg": "#0f172a",
            "surface": "#ffffff",
            "surface_alt": "#f6f8fc",
            "text": "#0f172a",
            "muted": "#5b6473",
            "accent": "#2563eb",
            "accent_soft": "#dbeafe",
            "accent_strong": "#1d4ed8",
            "select_bg": "#2563eb",
            "select_fg": "#ffffff",
            "border": "#d7deea",
            "drop_bg": "#eef6ff",
            "drop_border": "#93c5fd",
            "success": "#15803d",
        }

    def _detect_font_family(self):
        try:
            families = set(tkfont.families(self.master))
        except tk.TclError:
            return tkfont.nametofont("TkDefaultFont").cget("family")

        for family in ("Yu Gothic UI", "Segoe UI", "Hiragino Sans", "Meiryo"):
            if family in families:
                return family
        return tkfont.nametofont("TkDefaultFont").cget("family")

    def _detect_mono_family(self):
        try:
            families = set(tkfont.families(self.master))
        except tk.TclError:
            return tkfont.nametofont("TkFixedFont").cget("family")

        for family in ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "Courier New"):
            if family in families:
                return family
        return tkfont.nametofont("TkFixedFont").cget("family")

    def configure_styles(self):
        self.colors = self._get_theme_colors()
        self.font_family = self._detect_font_family()
        self.mono_family = self._detect_mono_family()

        self.master.configure(bg=self.colors["app_bg"])

        self.style.configure("App.TFrame", background=self.colors["app_bg"])
        self.style.configure("Surface.TFrame", background=self.colors["surface"])
        self.style.configure("Hero.TFrame", background=self.colors["surface"])
        self.style.configure(
            "Card.TLabelframe",
            background=self.colors["surface"],
            borderwidth=1,
            relief="solid",
        )
        self.style.configure(
            "Card.TLabelframe.Label",
            background=self.colors["surface"],
            foreground=self.colors["text"],
            font=(self.font_family, 9, "bold"),
        )
        self.style.configure(
            "HeroTitle.TLabel",
            background=self.colors["surface"],
            foreground=self.colors["text"],
            font=(self.font_family, 15, "bold"),
        )
        self.style.configure(
            "HeroSubtitle.TLabel",
            background=self.colors["surface"],
            foreground=self.colors["muted"],
            font=(self.font_family, 8),
        )
        self.style.configure(
            "HeroHint.TLabel",
            background=self.colors["surface"],
            foreground=self.colors["muted"],
            font=(self.font_family, 8),
        )
        self.style.configure(
            "Badge.TLabel",
            background=self.colors["accent_soft"],
            foreground=self.colors["accent_strong"],
            font=(self.font_family, 8, "bold"),
            padding=(7, 2),
        )
        self.style.configure(
            "Hint.TLabel",
            background=self.colors["surface"],
            foreground=self.colors["muted"],
            font=(self.font_family, 8),
        )
        self.style.configure(
            "SectionTitle.TLabel",
            background=self.colors["surface"],
            foreground=self.colors["text"],
            font=(self.font_family, 9, "bold"),
        )
        self.style.configure("Action.TButton", padding=(9, 4))
        self.style.configure("Ghost.TButton", padding=(8, 4))
        self.style.configure(
            "Tall.Accent.TButton",
            padding=(10, 7),
            font=(self.font_family, 9, "bold"),
        )
        self.style.configure(
            "App.Horizontal.TProgressbar",
            thickness=8,
            troughcolor=self.colors["surface_alt"],
            background=self.colors["accent"],
            borderwidth=0,
        )

    def _set_dropzone_active(self, active):
        border = self.colors["drop_border"] if active else self.colors["border"]
        bg = self.colors["drop_bg"] if active else self.colors["surface_alt"]

        if hasattr(self, "file_listbox_shell") and self.file_listbox_shell.winfo_exists():
            self.file_listbox_shell.config(bg=border)
        if hasattr(self, "file_listbox_inner") and self.file_listbox_inner.winfo_exists():
            self.file_listbox_inner.config(bg=bg)
        if hasattr(self, "file_list_container") and self.file_list_container.winfo_exists():
            self.file_list_container.config(bg=bg)
        if hasattr(self, "file_listbox") and self.file_listbox.winfo_exists():
            self.file_listbox.config(bg=bg)
        if hasattr(self, "file_empty_state") and self.file_empty_state.winfo_exists():
            self.file_empty_state.config(bg=bg)

    def _refresh_ui_state(self):
        self._update_file_summary()
        self._update_output_status()
        self._update_preset_status()

    def _update_file_summary(self):
        count = 0
        if hasattr(self, "file_listbox") and self.file_listbox.winfo_exists():
            count = self.file_listbox.size()

        if hasattr(self, "file_summary_var"):
            self.file_summary_var.set(f"選択中 {count} 枚")

        if hasattr(self, "file_empty_state") and self.file_empty_state.winfo_exists():
            if count == 0:
                self.file_empty_state.place(relx=0.5, rely=0.5, anchor="center")
            else:
                self.file_empty_state.place_forget()

    def _update_output_status(self):
        if not hasattr(self, "output_status_var"):
            return

        destination = (
            self.output_dest_var.get()
            if hasattr(self, "output_dest_var")
            else getattr(self, "output_destination", "original")
        )
        if destination == "output":
            self.output_status_var.set("出力先 output フォルダ")
        else:
            self.output_status_var.set("出力先 元のフォルダ")

    def _update_preset_status(self):
        if not hasattr(self, "preset_status_var"):
            return

        preset = (
            self.preset_var.get()
            if hasattr(self, "preset_var")
            else getattr(self, "preset", "カスタム")
        )
        if preset.startswith("---"):
            preset = "カスタム"
        self.preset_status_var.set(f"プリセット {preset}")

    def _show_log_placeholder(self):
        if not hasattr(self, "output_text") or not self.output_text.winfo_exists():
            return
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, "処理ログがここに表示されます。", "muted")

    def _create_scroll_container(self):
        self.scroll_container = ttk.Frame(self.master, style="App.TFrame")
        self.scroll_container.pack(fill=tk.BOTH, expand=True)

        self.content_canvas = tk.Canvas(
            self.scroll_container,
            bg=self.colors["app_bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.content_scrollbar = ttk.Scrollbar(
            self.scroll_container,
            orient=tk.VERTICAL,
            command=self.content_canvas.yview,
        )
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)

        self.content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.content_frame = ttk.Frame(self.content_canvas, style="App.TFrame")
        self.content_window = self.content_canvas.create_window(
            (0, 0),
            window=self.content_frame,
            anchor="nw",
        )

        self.content_frame.bind("<Configure>", self._on_content_frame_configure)
        self.content_canvas.bind("<Configure>", self._on_content_canvas_configure)
        self.content_canvas.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.content_canvas.bind("<Button-4>", self._on_mousewheel_linux, add="+")
        self.content_canvas.bind("<Button-5>", self._on_mousewheel_linux, add="+")

    def _on_content_frame_configure(self, _event=None):
        if hasattr(self, "content_canvas"):
            self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _on_content_canvas_configure(self, event):
        if hasattr(self, "content_canvas") and hasattr(self, "content_window"):
            self.content_canvas.itemconfigure(self.content_window, width=event.width)

    def _scroll_content(self, direction):
        if not hasattr(self, "content_canvas"):
            return None
        first, last = self.content_canvas.yview()
        if direction < 0 and first <= 0.0:
            return "break"
        if direction > 0 and last >= 1.0:
            return "break"
        self.content_canvas.yview_scroll(direction, "units")
        return "break"

    def _on_mousewheel(self, event):
        if getattr(event, "delta", 0) == 0:
            return None
        direction = -1 if event.delta > 0 else 1
        return self._scroll_content(direction)

    def _on_mousewheel_linux(self, event):
        if getattr(event, "num", None) == 4:
            return self._scroll_content(-1)
        if getattr(event, "num", None) == 5:
            return self._scroll_content(1)
        return None

    def _bind_scroll_support(self, widget):
        scroll_excluded = {"Text", "Listbox", "Scrollbar", "TScrollbar", "Canvas"}
        if widget.winfo_class() not in scroll_excluded:
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
            widget.bind("<Button-4>", self._on_mousewheel_linux, add="+")
            widget.bind("<Button-5>", self._on_mousewheel_linux, add="+")

        for child in widget.winfo_children():
            self._bind_scroll_support(child)

    def _set_wraplength(self, widget, wraplength):
        if widget and widget.winfo_exists():
            widget.configure(wraplength=max(180, int(wraplength)))

    def _apply_responsive_layout(self, width=None):
        required_widgets = (
            "left_frame",
            "right_frame",
            "title_frame",
            "toggle_frame",
            "header_badges_frame",
            "header_hint_label",
            "file_buttons_frame",
            "preset_row",
            "output_text",
        )
        if not all(hasattr(self, name) for name in required_widgets):
            return

        if width is None:
            width = (
                self.content_canvas.winfo_width()
                if hasattr(self, "content_canvas")
                else self.master.winfo_width()
            )
        if width <= 1:
            width = getattr(self, "window_width", 1180)

        stacked = width < 940
        tight = width < 760
        ultra_tight = width < 730
        header_stacked = width < 820

        if getattr(self, "_settings_layout_mode", None) != stacked:
            self.left_frame.pack_forget()
            self.right_frame.pack_forget()
            if stacked:
                self.left_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
                self.right_frame.pack(fill=tk.BOTH, expand=True)
            else:
                self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
                self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))
            self._settings_layout_mode = stacked

        if getattr(self, "_header_layout_mode", None) != header_stacked:
            self.title_frame.pack_forget()
            self.toggle_frame.pack_forget()
            self.title_frame.pack(side=tk.TOP if header_stacked else tk.LEFT, fill=tk.X, expand=True, anchor=tk.W)
            self.toggle_frame.pack(
                side=tk.TOP if header_stacked else tk.RIGHT,
                anchor=tk.W if header_stacked else tk.NE,
                pady=(4, 0) if header_stacked else (0, 0),
            )
            self._header_layout_mode = header_stacked

        if getattr(self, "_meta_layout_mode", None) != tight:
            self.header_badges_frame.pack_forget()
            self.header_hint_label.pack_forget()
            if tight:
                self.header_badges_frame.pack(fill=tk.X, anchor=tk.W)
                self.header_hint_label.pack(anchor=tk.W, pady=(4, 0))
            else:
                self.header_badges_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
                self.header_hint_label.pack(side=tk.RIGHT)
            self._meta_layout_mode = tight

        if getattr(self, "_file_actions_layout_mode", None) != tight:
            for button in self.file_action_buttons:
                button.pack_forget()
            self.file_buttons_hint_label.pack_forget()
            if tight:
                for button in self.file_action_buttons:
                    button.pack(fill=tk.X, pady=(0, 3))
                self.file_buttons_hint_label.pack(anchor=tk.W, pady=(1, 0))
            else:
                self.file_select_button.pack(side=tk.LEFT, padx=(0, 6))
                self.file_process_button.pack(side=tk.LEFT, padx=(0, 6))
                self.file_remove_button.pack(side=tk.LEFT, padx=(0, 6))
                self.file_clear_button.pack(side=tk.LEFT)
                self.file_buttons_hint_label.pack(side=tk.RIGHT)
            self._file_actions_layout_mode = tight

        if getattr(self, "_preset_layout_mode", None) != tight:
            self.preset_row_label.pack_forget()
            self.preset_combo.pack_forget()
            if tight:
                self.preset_row_label.pack(anchor=tk.W, pady=(0, 3))
                self.preset_combo.pack(fill=tk.X)
            else:
                self.preset_row_label.pack(side=tk.LEFT, padx=(0, 8))
                self.preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._preset_layout_mode = tight

        body_wrap = width - 80
        header_wrap = width - (90 if header_stacked else 250)
        column_wrap = width - 80 if stacked else (width - 120) / 2
        self._set_wraplength(self.header_subtitle_label, header_wrap)
        self._set_wraplength(self.file_intro_label, body_wrap)
        self._set_wraplength(self.file_buttons_hint_label, body_wrap if tight else 260)
        self._set_wraplength(self.preset_intro_label, body_wrap)
        self._set_wraplength(self.crop_intro_label, column_wrap)
        self._set_wraplength(self.size_intro_label, column_wrap)
        self._set_wraplength(self.format_intro_label, column_wrap)
        self._set_wraplength(self.output_dest_intro_label, column_wrap)
        self._set_wraplength(self.filename_intro_label, column_wrap)
        self._set_wraplength(self.log_intro_label, body_wrap)
        self.file_empty_state.configure(wraplength=max(200, width - 120))
        self.file_listbox.configure(height=3 if ultra_tight else 4)
        self.output_text.configure(height=4 if ultra_tight else (5 if tight else 6))
        self.content_frame.after_idle(self._on_content_frame_configure)

    def load_settings(self):
        """設定をJSONファイルからロード"""
        self.settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
        settings = dict(DEFAULT_SETTINGS)
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    settings.update(json.load(f))
        except Exception as e:
            print(f"設定ロードエラー: {e}")

        self.always_on_top = settings["always_on_top"]
        self.crop_type = settings["crop_type"]
        self.size_type = settings["size_type"]
        self.operation = settings["operation"]
        self.output_format = settings["output_format"]
        self.filename_pattern = settings["filename_pattern"]
        self.window_width = settings["window_width"]
        self.window_height = settings["window_height"]
        self.window_x = settings["window_x"]
        self.window_y = settings["window_y"]
        self.preset = settings["preset"]
        self.target_size = settings["target_size"]
        self.mb_size = settings["mb_size"]
        self.kb_size = settings["kb_size"]
        self.width_px = settings["width_px"]
        self.height_px = settings["height_px"]
        self.long_edge_px = settings["long_edge_px"]
        self.aspect_width_value = settings["aspect_width"]
        self.aspect_height_value = settings["aspect_height"]
        self.include_crop_type_value = settings["include_crop_type"]
        self.include_size_ratio_value = settings["include_size_ratio"]
        self.include_timestamp_value = settings["include_timestamp"]
        self.include_sequential_value = settings["include_sequential"]
        self.include_preset_name_value = settings["include_preset_name"]
        self.output_destination = settings["output_destination"]
        self.warn_on_overwrite = settings["warn_on_overwrite"]

    def load_presets(self):
        """プリセットをJSONファイルからロード"""
        self.presets_file = os.path.join(os.path.dirname(__file__), "presets.json")
        self.presets_data = {}
        self.preset_values = ["カスタム"]

        try:
            if os.path.exists(self.presets_file):
                with open(self.presets_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    for category in data.get("categories", []):
                        category_name = category.get("name", "")
                        if category_name:
                            self.preset_values.append(f"--- {category_name} ---")

                        for preset in category.get("presets", []):
                            preset_name = preset.get("name", "")
                            if preset_name:
                                self.preset_values.append(preset_name)
                                self.presets_data[preset_name] = preset
        except Exception as e:
            print(f"プリセットロードエラー: {e}")

    def save_settings(self):
        """設定をJSONファイルに保存"""
        try:
            # GUI要素から現在の値を取得
            target_size = None
            mb_size = None
            kb_size = None
            width_px = None
            height_px = None
            long_edge_px = None

            try:
                size_value = float(self.size_entry.get()) if hasattr(self, 'size_entry') and self.size_entry.winfo_exists() else None
                if size_value is not None:
                    size_type = self.size_type_var.get() if hasattr(self, 'size_type_var') else self.size_type
                    if size_type == "mb":
                        mb_size = size_value
                        target_size = size_value
                    elif size_type == "kb":
                        kb_size = size_value
                        target_size = size_value
                    elif size_type == "width":
                        width_px = int(size_value)
                        target_size = size_value
                    elif size_type == "height":
                        height_px = int(size_value)
                        target_size = size_value
                    elif size_type == "long_edge":
                        long_edge_px = int(size_value)
                        target_size = size_value
            except (ValueError, tk.TclError):
                pass

            # アスペクト比の値を取得
            aspect_width = None
            aspect_height = None
            try:
                if hasattr(self, 'aspect_width') and self.aspect_width.winfo_exists():
                    aspect_width = float(self.aspect_width.get())
                if hasattr(self, 'aspect_height') and self.aspect_height.winfo_exists():
                    aspect_height = float(self.aspect_height.get())
            except (ValueError, tk.TclError):
                pass

            settings = {
                "always_on_top": self.always_on_top,
                "crop_type": self.crop_var.get() if hasattr(self, 'crop_var') else self.crop_type,
                "size_type": self.size_type_var.get() if hasattr(self, 'size_type_var') else self.size_type,
                "operation": self.operation_var.get() if hasattr(self, 'operation_var') else self.operation,
                "output_format": self.format_var.get() if hasattr(self, 'format_var') else self.output_format,
                "filename_pattern": self.filename_pattern_var.get() if hasattr(self, 'filename_pattern_var') else self.filename_pattern,
                "preset": self.preset_var.get() if hasattr(self, 'preset_var') else getattr(self, 'preset', "カスタム"),
                "target_size": target_size if target_size is not None else getattr(self, 'target_size', 2.0),
                "mb_size": mb_size if mb_size is not None else getattr(self, 'mb_size', 2),
                "kb_size": kb_size if kb_size is not None else getattr(self, 'kb_size', 500),
                "width_px": width_px if width_px is not None else getattr(self, 'width_px', 1920),
                "height_px": height_px if height_px is not None else getattr(self, 'height_px', 1080),
                "long_edge_px": long_edge_px if long_edge_px is not None else getattr(self, 'long_edge_px', 1920),
                "aspect_width": aspect_width if aspect_width is not None else getattr(self, 'aspect_width_value', 16.0),
                "aspect_height": aspect_height if aspect_height is not None else getattr(self, 'aspect_height_value', 9.0),
                "include_crop_type": self.include_crop_type.get() if hasattr(self, 'include_crop_type') else getattr(self, 'include_crop_type_value', False),
                "include_size_ratio": self.include_size_ratio.get() if hasattr(self, 'include_size_ratio') else getattr(self, 'include_size_ratio_value', False),
                "include_timestamp": self.include_timestamp.get() if hasattr(self, 'include_timestamp') else getattr(self, 'include_timestamp_value', False),
                "include_sequential": self.include_sequential.get() if hasattr(self, 'include_sequential') else getattr(self, 'include_sequential_value', False),
                "include_preset_name": self.include_preset_name.get() if hasattr(self, 'include_preset_name') else getattr(self, 'include_preset_name_value', False),
                "output_destination": self.output_dest_var.get() if hasattr(self, 'output_dest_var') else getattr(self, 'output_destination', "original"),
                "warn_on_overwrite": self.warn_on_overwrite_var.get() if hasattr(self, 'warn_on_overwrite_var') else getattr(self, 'warn_on_overwrite', True),
                "window_width": self.window_width,
                "window_height": self.window_height,
                "window_x": self.window_x,
                "window_y": self.window_y
            }
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"設定保存エラー: {e}")

    def toggle_always_on_top(self):
        """最前面表示のトグル"""
        self.always_on_top = not self.always_on_top
        self.master.attributes("-topmost", self.always_on_top)
        self.save_settings()

    def create_widgets(self):
        colors = self.colors
        self._create_scroll_container()

        self.header_frame = ttk.Frame(
            self.content_frame, style="Hero.TFrame", padding=(10, 8, 10, 7)
        )
        self.header_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        self.header_top = ttk.Frame(self.header_frame, style="Hero.TFrame")
        self.header_top.pack(fill=tk.X)

        self.title_frame = ttk.Frame(self.header_top, style="Hero.TFrame")
        self.title_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(self.title_frame, text="ImageSizer", style="HeroTitle.TLabel").pack(
            anchor=tk.W
        )
        self.header_subtitle_label = ttk.Label(
            self.title_frame,
            text="複数画像をまとめて整形できます。",
            style="HeroSubtitle.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        )
        self.header_subtitle_label.pack(anchor=tk.W, pady=(1, 0))

        self.toggle_frame = ttk.Frame(self.header_top, style="Hero.TFrame")
        self.toggle_frame.pack(side=tk.RIGHT, anchor=tk.NE)
        self.toggle_button = ttk.Checkbutton(
            self.toggle_frame,
            text="常に最前面に表示",
            command=self.toggle_always_on_top
        )
        self.toggle_button.pack(side=tk.RIGHT)
        if self.always_on_top:
            self.toggle_button.state(['selected'])
            self.master.attributes("-topmost", True)

        self.header_meta = ttk.Frame(self.header_frame, style="Hero.TFrame")
        self.header_meta.pack(fill=tk.X, pady=(6, 0))
        self.file_summary_var = tk.StringVar()
        self.output_status_var = tk.StringVar()
        self.preset_status_var = tk.StringVar()
        self.header_badges_frame = ttk.Frame(self.header_meta, style="Hero.TFrame")
        self.header_badges_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            self.header_badges_frame, textvariable=self.file_summary_var, style="Badge.TLabel"
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(
            self.header_badges_frame, textvariable=self.output_status_var, style="Badge.TLabel"
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(
            self.header_badges_frame, textvariable=self.preset_status_var, style="Badge.TLabel"
        ).pack(side=tk.LEFT)
        self.header_hint_label = ttk.Label(
            self.header_meta,
            text="ヒント: 追加した画像はすぐ処理されます",
            style="HeroHint.TLabel",
        )
        self.header_hint_label.pack(side=tk.RIGHT)

        # ファイル選択部分
        self.file_frame = ttk.LabelFrame(
            self.content_frame, text="ファイル選択", style="Card.TLabelframe", padding=(8, 7)
        )
        self.file_frame.pack(fill=tk.X, padx=8, pady=4)
        self.file_intro_label = ttk.Label(
            self.file_frame,
            text="画像をドロップまたは選択すると自動で処理します。",
            style="Hint.TLabel",
        )
        self.file_intro_label.pack(anchor=tk.W, pady=(0, 4))

        # Listbox + Scrollbar
        self.file_listbox_shell = tk.Frame(self.file_frame, bg=colors["border"], bd=0)
        self.file_listbox_shell.pack(fill=tk.X, pady=(0, 3))
        self.file_listbox_inner = tk.Frame(
            self.file_listbox_shell, bg=colors["surface_alt"], padx=1, pady=1
        )
        self.file_listbox_inner.pack(fill=tk.BOTH, expand=True)
        self.file_list_container = tk.Frame(
            self.file_listbox_inner, bg=colors["surface_alt"]
        )
        self.file_list_container.pack(fill=tk.BOTH, expand=True)
        listbox_scrollbar = ttk.Scrollbar(self.file_list_container, orient=tk.VERTICAL)
        self.file_listbox = tk.Listbox(
            self.file_list_container,
            width=70,
            height=4,
            selectmode=tk.EXTENDED,
            yscrollcommand=listbox_scrollbar.set,
            bg=colors["surface_alt"],
            fg=colors["text"],
            selectbackground=colors["select_bg"],
            selectforeground=colors["select_fg"],
            highlightthickness=0,
            borderwidth=0,
            relief=tk.FLAT,
            exportselection=False,
            activestyle="none",
            font=(self.mono_family, 9),
        )
        listbox_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_empty_state = tk.Label(
            self.file_listbox_inner,
            text="ここに画像をドロップ\nまたはファイルを選択して自動処理",
            bg=colors["surface_alt"],
            fg=colors["muted"],
            font=(self.font_family, 9),
            justify=tk.CENTER,
            cursor="hand2",
        )
        self.file_empty_state.bind("<Button-1>", lambda _event: self.browse_files())
        self._set_dropzone_active(False)

        # ボタン行: [ファイルを選択] [選択を削除] [すべてクリア]
        self.file_buttons_frame = ttk.Frame(self.file_frame, style="Surface.TFrame")
        self.file_buttons_frame.pack(fill=tk.X, pady=(1, 0))
        self.file_select_button = ttk.Button(
            self.file_buttons_frame,
            text="ファイルを選択",
            style="Action.TButton",
            command=self.browse_files,
        )
        self.file_select_button.pack(side=tk.LEFT, padx=(0, 6))
        self.file_process_button = ttk.Button(
            self.file_buttons_frame,
            text="処理を開始",
            style="Action.TButton",
            command=self.process_images,
        )
        self.file_process_button.pack(side=tk.LEFT, padx=(0, 6))
        self.file_remove_button = ttk.Button(
            self.file_buttons_frame,
            text="選択を削除",
            style="Ghost.TButton",
            command=self.remove_selected_files,
        )
        self.file_remove_button.pack(side=tk.LEFT, padx=(0, 6))
        self.file_clear_button = ttk.Button(
            self.file_buttons_frame,
            text="すべてクリア",
            style="Ghost.TButton",
            command=self.clear_all_files,
        )
        self.file_clear_button.pack(side=tk.LEFT)
        self.file_action_buttons = [
            self.file_select_button,
            self.file_process_button,
            self.file_remove_button,
            self.file_clear_button,
        ]
        self.file_buttons_hint_label = ttk.Label(
            self.file_buttons_frame,
            text="複数選択のみ削除できます。",
            style="Hint.TLabel",
        )
        self.file_buttons_hint_label.pack(side=tk.RIGHT)

        # プリセット選択部分
        self.preset_frame = ttk.LabelFrame(
            self.content_frame, text="プリセット設定", style="Card.TLabelframe", padding=(8, 7)
        )
        self.preset_frame.pack(fill=tk.X, padx=8, pady=4)

        self.preset_intro_label = ttk.Label(
            self.preset_frame,
            text="よく使う設定を呼び出せます。",
            style="Hint.TLabel",
        )
        self.preset_intro_label.pack(anchor=tk.W, pady=(0, 4))

        self.preset_row = ttk.Frame(self.preset_frame, style="Surface.TFrame")
        self.preset_row.pack(fill=tk.X)
        self.preset_row_label = ttk.Label(
            self.preset_row, text="プリセット", style="SectionTitle.TLabel"
        )
        self.preset_row_label.pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self.preset_var = tk.StringVar(value=getattr(self, 'preset', "カスタム"))
        self.preset_combo = ttk.Combobox(
            self.preset_row,
            textvariable=self.preset_var,
            values=self.preset_values,
            state="readonly",
            width=44
        )
        self.preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_change)

        # 左右のフレームを作成
        self.settings_frame = ttk.Frame(self.content_frame, style="App.TFrame")
        self.settings_frame.pack(fill=tk.BOTH, expand=True, padx=8)

        # 左側のフレーム
        self.left_frame = ttk.Frame(self.settings_frame, style="App.TFrame")
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))

        # 右側のフレーム
        self.right_frame = ttk.Frame(self.settings_frame, style="App.TFrame")
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))

        # クロップ設定部分（左側）
        crop_frame = ttk.LabelFrame(
            self.left_frame, text="クロップ設定", style="Card.TLabelframe", padding=(8, 7)
        )
        crop_frame.pack(fill=tk.X, pady=(0, 6))
        self.crop_intro_label = ttk.Label(
            crop_frame,
            text="仕上がり比率を決めます。",
            style="Hint.TLabel",
        )
        self.crop_intro_label.pack(anchor=tk.W, pady=(0, 4))
        self.crop_var = tk.StringVar(value=self.crop_type)
        ttk.Radiobutton(
            crop_frame,
            text="クロップなし",
            variable=self.crop_var,
            value="none",
            command=self.on_crop_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            crop_frame,
            text="正方形（1:1）",
            variable=self.crop_var,
            value="square",
            command=self.on_crop_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            crop_frame,
            text="16:9",
            variable=self.crop_var,
            value="16:9",
            command=self.on_crop_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            crop_frame,
            text="4:3",
            variable=self.crop_var,
            value="4:3",
            command=self.on_crop_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            crop_frame,
            text="9:16",
            variable=self.crop_var,
            value="9:16",
            command=self.on_crop_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            crop_frame,
            text="1:√2（縦長・A4等）",
            variable=self.crop_var,
            value="1:√2",
            command=self.on_crop_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            crop_frame,
            text="√2:1（横長・A4等）",
            variable=self.crop_var,
            value="√2:1",
            command=self.on_crop_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            crop_frame,
            text="カスタム比率",
            variable=self.crop_var,
            value="custom",
            command=self.on_crop_change,
        ).pack(anchor=tk.W, pady=(0, 1))

        # カスタム比率入力用のフレーム
        self.aspect_ratio_frame = ttk.Frame(crop_frame, style="Surface.TFrame")
        self.aspect_ratio_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(self.aspect_ratio_frame, text="縦横比", style="SectionTitle.TLabel").pack(side=tk.LEFT)
        self.aspect_width = ttk.Entry(self.aspect_ratio_frame, width=6)
        self.aspect_width.insert(0, str(getattr(self, 'aspect_width_value', 16.0)))
        self.aspect_width.pack(side=tk.LEFT, padx=(10, 4))
        ttk.Label(self.aspect_ratio_frame, text=":", style="SectionTitle.TLabel").pack(side=tk.LEFT)
        self.aspect_height = ttk.Entry(self.aspect_ratio_frame, width=6)
        self.aspect_height.insert(0, str(getattr(self, 'aspect_height_value', 9.0)))
        self.aspect_height.pack(side=tk.LEFT, padx=(4, 0))
        # アスペクト比入力値が変更されたときに保存
        self.aspect_width.bind("<KeyRelease>", lambda e: self.master.after(1000, self.save_settings))
        self.aspect_height.bind("<KeyRelease>", lambda e: self.master.after(1000, self.save_settings))
        # 設定からクロップタイプがcustomの場合は表示、それ以外は非表示
        if self.crop_type != "custom":
            self.aspect_ratio_frame.pack_forget()

        # サイズ変更設定部分（右側）
        size_frame = ttk.LabelFrame(
            self.right_frame, text="目標サイズ設定", style="Card.TLabelframe", padding=(8, 7)
        )
        size_frame.pack(fill=tk.X, pady=(0, 6))
        self.size_intro_label = ttk.Label(
            size_frame,
            text="容量かピクセル基準を選びます。",
            style="Hint.TLabel",
        )
        self.size_intro_label.pack(anchor=tk.W, pady=(0, 4))
        self.size_type_var = tk.StringVar(value=self.size_type)
        ttk.Radiobutton(
            size_frame,
            text="変更なし",
            variable=self.size_type_var,
            value="none",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            size_frame,
            text="MBで指定",
            variable=self.size_type_var,
            value="mb",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            size_frame,
            text="KBで指定",
            variable=self.size_type_var,
            value="kb",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            size_frame,
            text="横ピクセルで指定",
            variable=self.size_type_var,
            value="width",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            size_frame,
            text="縦ピクセルで指定",
            variable=self.size_type_var,
            value="height",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            size_frame,
            text="長辺で指定",
            variable=self.size_type_var,
            value="long_edge",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W, pady=(0, 1))

        # サイズ入力用のフレーム
        self.size_input_frame = ttk.Frame(size_frame, style="Surface.TFrame")
        self.size_input_frame.pack(fill=tk.X, pady=(4, 0))
        # 設定から初期値とラベルを取得
        if hasattr(self, 'size_type') and self.size_type == "mb":
            initial_value = str(getattr(self, 'mb_size', 2))
            label_text = "目標サイズ (MB)"
        elif hasattr(self, 'size_type') and self.size_type == "kb":
            initial_value = str(getattr(self, 'kb_size', 500))
            label_text = "目標サイズ (KB)"
        elif hasattr(self, 'size_type') and self.size_type == "width":
            initial_value = str(getattr(self, 'width_px', 1920))
            label_text = "目標サイズ (横px)"
        elif hasattr(self, 'size_type') and self.size_type == "height":
            initial_value = str(getattr(self, 'height_px', 1080))
            label_text = "目標サイズ (縦px)"
        elif hasattr(self, 'size_type') and self.size_type == "long_edge":
            initial_value = str(getattr(self, 'long_edge_px', 1920))
            label_text = "目標サイズ (長辺px)"
        else:
            initial_value = "2"
            label_text = "目標サイズ (MB)"

        self.size_label = ttk.Label(
            self.size_input_frame, text=label_text, style="SectionTitle.TLabel"
        )
        self.size_label.pack(side=tk.LEFT)
        self.size_entry = ttk.Entry(self.size_input_frame, width=10)
        self.size_entry.insert(0, initial_value)
        self.size_entry.pack(side=tk.LEFT, padx=(8, 0))
        # サイズ入力値が変更されたときに保存
        self.size_entry.bind("<KeyRelease>", lambda e: self.master.after(1000, self.save_settings))

        # 設定からサイズタイプが"none"の場合は入力フレームを非表示
        if self.size_type == "none":
            self.size_input_frame.pack_forget()

        # 自動調整モードを固定で使用
        self.operation_var = tk.StringVar(value="auto")

        # 出力フォーマット選択部分（右側）
        format_frame = ttk.LabelFrame(
            self.right_frame, text="出力フォーマット", style="Card.TLabelframe", padding=(8, 7)
        )
        format_frame.pack(fill=tk.X, pady=(0, 6))
        self.format_intro_label = ttk.Label(
            format_frame,
            text="元形式か WebP / PNG を選びます。",
            style="Hint.TLabel",
        )
        self.format_intro_label.pack(anchor=tk.W, pady=(0, 4))
        self.format_var = tk.StringVar(value=self.output_format)
        ttk.Radiobutton(
            format_frame,
            text="元のフォーマットを維持",
            variable=self.format_var,
            value="original",
            command=self.save_settings
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            format_frame,
            text="WebP形式に変換",
            variable=self.format_var,
            value="webp",
            command=self.save_settings
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            format_frame,
            text="PNG形式に変換",
            variable=self.format_var,
            value="png",
            command=self.save_settings
        ).pack(anchor=tk.W, pady=(0, 1))

        # 出力先選択部分（右側）
        output_dest_frame = ttk.LabelFrame(
            self.right_frame, text="出力先", style="Card.TLabelframe", padding=(8, 7)
        )
        output_dest_frame.pack(fill=tk.X, pady=(0, 6))
        self.output_dest_intro_label = ttk.Label(
            output_dest_frame,
            text="元フォルダか output を選びます。",
            style="Hint.TLabel",
        )
        self.output_dest_intro_label.pack(anchor=tk.W, pady=(0, 4))
        self.output_dest_var = tk.StringVar(value=getattr(self, 'output_destination', 'original'))
        ttk.Radiobutton(
            output_dest_frame,
            text="元のフォルダ",
            variable=self.output_dest_var,
            value="original",
            command=self.on_output_destination_change
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Radiobutton(
            output_dest_frame,
            text="outputフォルダ",
            variable=self.output_dest_var,
            value="output",
            command=self.on_output_destination_change
        ).pack(anchor=tk.W, pady=(0, 1))
        ttk.Button(
            output_dest_frame,
            text="出力先フォルダを開く",
            style="Action.TButton",
            command=self.open_output_folder
        ).pack(anchor=tk.W, pady=(4, 0))

        self.warn_on_overwrite_var = tk.BooleanVar(
            value=getattr(self, 'warn_on_overwrite', True)
        )
        ttk.Checkbutton(
            output_dest_frame,
            text="元画像を上書きしそうなとき警告する",
            variable=self.warn_on_overwrite_var,
            command=self.save_settings,
        ).pack(anchor=tk.W, pady=(4, 0))

        # 出力ファイル名パターン選択部分（左側）
        filename_frame = ttk.LabelFrame(
            self.left_frame, text="出力ファイル名パターン", style="Card.TLabelframe", padding=(8, 7)
        )
        filename_frame.pack(fill=tk.X, pady=(0, 6))

        # チェックボックス用の変数（設定から復元）
        self.include_crop_type = tk.BooleanVar(value=getattr(self, 'include_crop_type_value', False))
        self.include_size_ratio = tk.BooleanVar(value=getattr(self, 'include_size_ratio_value', False))
        self.include_timestamp = tk.BooleanVar(value=getattr(self, 'include_timestamp_value', False))
        self.include_sequential = tk.BooleanVar(value=getattr(self, 'include_sequential_value', False))
        self.include_preset_name = tk.BooleanVar(value=getattr(self, 'include_preset_name_value', False))

        self.filename_intro_label = ttk.Label(
            filename_frame,
            text="必要な情報だけ追加します。",
            style="Hint.TLabel",
        )
        self.filename_intro_label.pack(anchor=tk.W, pady=(0, 4))

        ttk.Checkbutton(
            filename_frame,
            text="クロップタイプ（クロップ時のみ）",
            variable=self.include_crop_type,
            command=self.save_settings
        ).pack(anchor=tk.W, pady=(0, 1))

        ttk.Checkbutton(
            filename_frame,
            text="サイズ比率（サイズ変更時のみ）",
            variable=self.include_size_ratio,
            command=self.save_settings
        ).pack(anchor=tk.W, pady=(0, 1))

        ttk.Checkbutton(
            filename_frame,
            text="タイムスタンプ（YYYYMMDD_HHMMSS）",
            variable=self.include_timestamp,
            command=self.save_settings
        ).pack(anchor=tk.W, pady=(0, 1))

        ttk.Checkbutton(
            filename_frame,
            text="連番（001, 002, ...）",
            variable=self.include_sequential,
            command=self.save_settings
        ).pack(anchor=tk.W, pady=(0, 1))

        ttk.Checkbutton(
            filename_frame,
            text="プリセット名（プリセット使用時のみ）",
            variable=self.include_preset_name,
            command=self.save_settings
        ).pack(anchor=tk.W, pady=(0, 1))

        # プログレスバー（ウィンドウ幅に追従）
        self.progress = ttk.Progressbar(
            self.content_frame,
            orient="horizontal",
            mode="determinate",
            style="App.Horizontal.TProgressbar",
        )
        self.progress.pack(fill=tk.X, padx=8, pady=(4, 3))

        # 処理ログ
        log_frame = ttk.LabelFrame(
            self.content_frame, text="処理ログ", style="Card.TLabelframe", padding=(8, 7)
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.log_intro_label = ttk.Label(
            log_frame,
            text="処理結果をここに表示します。",
            style="Hint.TLabel",
        )
        self.log_intro_label.pack(anchor=tk.W, pady=(0, 4))

        log_shell = tk.Frame(log_frame, bg=colors["border"], bd=0)
        log_shell.pack(fill=tk.BOTH, expand=True)
        log_inner = tk.Frame(log_shell, bg=colors["surface_alt"], padx=1, pady=1)
        log_inner.pack(fill=tk.BOTH, expand=True)
        log_scrollbar = ttk.Scrollbar(log_inner, orient=tk.VERTICAL)
        self.output_text = tk.Text(
            log_inner,
            height=6,
            width=70,
            yscrollcommand=log_scrollbar.set,
            bg=colors["surface_alt"],
            fg=colors["text"],
            highlightthickness=0,
            borderwidth=0,
            relief=tk.FLAT,
            wrap=tk.WORD,
            insertbackground=colors["accent"],
            font=(self.mono_family, 9),
            padx=6,
            pady=6,
        )
        log_scrollbar.config(command=self.output_text.yview)
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.output_text.tag_configure("green", foreground=colors["success"])
        self.output_text.tag_configure("muted", foreground=colors["muted"])
        self._show_log_placeholder()
        self._refresh_ui_state()
        self._apply_responsive_layout(self.window_width)
        self._bind_scroll_support(self.content_frame)

    def setup_drop_target(self):
        self.master.drop_target_register(DND_FILES)
        self.master.dnd_bind("<<Drop>>", self.drop)
        self.master.dnd_bind("<<DragEnter>>", self._on_drag_enter)
        self.master.dnd_bind("<<DragLeave>>", self._on_drag_leave)

    def _on_drag_enter(self, event):
        """ドラッグ&ドロップの視覚フィードバック（進入時）"""
        self._set_dropzone_active(True)

    def _on_drag_leave(self, event):
        """ドラッグ&ドロップの視覚フィードバック（離脱時）"""
        self._set_dropzone_active(False)

    def drop(self, event):
        self._set_dropzone_active(False)
        files = self.master.tk.splitlist(event.data)
        self.add_files(files)
        self.process_images()

    def add_files(self, files):
        for file in files:
            if file not in self.file_listbox.get(0, tk.END):
                self.file_listbox.insert(tk.END, file)
        self._refresh_ui_state()

    def remove_selected_files(self):
        """選択されたファイルをリストから削除"""
        selected = self.file_listbox.curselection()
        for i in reversed(selected):
            self.file_listbox.delete(i)
        self._refresh_ui_state()

    def clear_all_files(self):
        """すべてのファイルをリストからクリア"""
        self.file_listbox.delete(0, tk.END)
        self._refresh_ui_state()

    def browse_files(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.heic;*.heif;*.webp")]
        )
        if files:
            self.add_files(files)
            self.process_images()

    def open_output_folder(self):
        """出力先フォルダをエクスプローラーで開く"""
        if self.output_dest_var.get() == "output":
            folder_path = os.path.join(os.path.dirname(__file__), "output")
            # フォルダが存在しない場合は作成
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
        else:
            # 元のフォルダが選択されている場合、リストの最初のファイルのフォルダを開く
            files = list(self.file_listbox.get(0, tk.END))
            if files:
                folder_path = os.path.dirname(files[0])
            else:
                messagebox.showinfo("情報", "ファイルが選択されていません。")
                return

        # OSに応じてフォルダを開く
        if platform.system() == "Windows":
            os.startfile(folder_path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(["open", folder_path])
        else:  # Linux
            subprocess.run(["xdg-open", folder_path])

    def on_crop_change(self):
        if self.crop_var.get() == "custom":
            self.aspect_ratio_frame.pack(fill=tk.X, pady=(4, 0))
        else:
            self.aspect_ratio_frame.pack_forget()
        self.save_settings()

    def on_output_destination_change(self):
        self._refresh_ui_state()
        self.save_settings()

    def on_size_type_change(self):
        size_type = self.size_type_var.get()
        if size_type == "none":
            self.size_input_frame.pack_forget()
        else:
            self.size_input_frame.pack(fill=tk.X, pady=(4, 0))
            if size_type == "mb":
                self.size_label.config(text="目標サイズ (MB)")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'mb_size', 2)))
            elif size_type == "kb":
                self.size_label.config(text="目標サイズ (KB)")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'kb_size', 500)))
            elif size_type == "width":
                self.size_label.config(text="目標サイズ (横px)")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'width_px', 1920)))
            elif size_type == "height":
                self.size_label.config(text="目標サイズ (縦px)")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'height_px', 1080)))
            elif size_type == "long_edge":
                self.size_label.config(text="目標サイズ (長辺px)")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'long_edge_px', 1920)))
        self._refresh_ui_state()
        self.save_settings()

    def process_images(self):
        if self.is_processing:
            return

        files = list(self.file_listbox.get(0, tk.END))
        if not files:
            messagebox.showwarning("警告", "処理する画像ファイルが選択されていません。")
            return

        size_type = self.size_type_var.get()
        if size_type != "none":
            try:
                target_size = float(self.size_entry.get())
            except ValueError:
                messagebox.showerror("エラー", "目標サイズには数値を入力してください。")
                return
        else:
            target_size = None

        operation = self.operation_var.get()
        crop_type = self.crop_var.get()

        aspect_ratio = None
        if crop_type == "custom":
            try:
                aspect_width = float(self.aspect_width.get())
                aspect_height = float(self.aspect_height.get())
                aspect_ratio = (aspect_width, aspect_height)
            except ValueError:
                messagebox.showerror("エラー", "縦横比には数値を入力してください。")
                return

        format_value = self.format_var.get()
        if format_value == "webp":
            output_format = "webp"
        elif format_value == "png":
            output_format = "png"
        else:
            output_format = None

        # Tkinter変数はメインスレッドで読み取り、ワーカーには純粋な値だけ渡す
        output_dest = self.output_dest_var.get()
        filename_pattern = {
            "include_crop_type": self.include_crop_type.get(),
            "include_size_ratio": self.include_size_ratio.get(),
            "include_timestamp": self.include_timestamp.get(),
            "include_sequential": self.include_sequential.get(),
            "include_preset_name": self.include_preset_name.get(),
        }
        preset_value = self.preset_var.get()
        preset_name = preset_value if preset_value != "カスタム" else None

        output_base = None
        if output_dest == "output":
            output_base = os.path.join(os.path.dirname(__file__), "output")
            if not os.path.exists(output_base):
                os.makedirs(output_base)

        if self.warn_on_overwrite_var.get():
            overwrite_candidates = []
            for file in files:
                check_folder = output_base if output_dest == "output" else os.path.dirname(file)
                if would_overwrite_input(
                    file,
                    check_folder,
                    output_format=output_format,
                    filename_pattern=filename_pattern,
                    preset_name=preset_name,
                ):
                    overwrite_candidates.append(file)

            if overwrite_candidates:
                sample = "\n".join(os.path.basename(f) for f in overwrite_candidates[:5])
                more = (
                    f"\n...ほか {len(overwrite_candidates) - 5} 件"
                    if len(overwrite_candidates) > 5
                    else ""
                )
                message = (
                    f"出力が元画像と同じパスになりそうなファイルが {len(overwrite_candidates)} 件あります。\n"
                    f"続行すると、競合するファイルは `_processed` を付けて保存します。\n\n"
                    f"{sample}{more}\n\n"
                    f"処理を続けますか？"
                )
                if not messagebox.askyesno("上書きの可能性", message):
                    self.output_text.delete(1.0, tk.END)
                    self.output_text.insert(
                        tk.END,
                        "上書き警告のため処理を中止しました。設定を調整してから「処理を開始」で再実行できます。\n",
                        "muted",
                    )
                    self.output_text.see(tk.END)
                    return

        self.output_text.delete(1.0, tk.END)
        self.progress["maximum"] = len(files) * 100
        self.progress["value"] = 0
        self.is_processing = True

        max_progress = len(files) * 100
        event_queue = queue.Queue()

        def _log_output(text, tag=None):
            if tag:
                self.output_text.insert(tk.END, text, tag)
            else:
                self.output_text.insert(tk.END, text)
            self.output_text.see(tk.END)

        def _delete_first_item():
            if self.file_listbox.size() > 0:
                self.file_listbox.delete(0)
                self._refresh_ui_state()

        def _finish_batch():
            self.is_processing = False
            self._refresh_ui_state()
            if self.file_listbox.size() > 0:
                self.master.after(50, self.process_images)

        def pump_events():
            # ワーカースレッドから送られたイベントをメインスレッドで反映する
            try:
                while True:
                    event = event_queue.get_nowait()
                    kind = event[0]
                    if kind == "progress_add":
                        self.progress["value"] += event[1]
                    elif kind == "progress_set":
                        self.progress["value"] = event[1]
                    elif kind == "log":
                        _log_output(event[1], event[2])
                    elif kind == "delete_first":
                        _delete_first_item()
                    elif kind == "done":
                        self.progress["value"] = max_progress
                        _finish_batch()
                        return
            except queue.Empty:
                pass
            self.master.after(50, pump_events)

        def process_images_thread():
            try:
                for i, file in enumerate(files):
                    if self._shutdown_event.is_set():
                        event_queue.put(
                            ("log", "アプリ終了要求のため処理を中断しました。\n", "muted")
                        )
                        break
                    event_queue.put(
                        ("log", f"[{i + 1}/{len(files)}] 処理開始: {file}\n", "muted")
                    )
                    try:
                        if output_dest == "output":
                            output_folder = output_base
                        else:
                            output_folder = os.path.dirname(file)

                        # process_image は累積の進捗率を渡してくるため、
                        # 前回値との差分だけをプログレスバーに加算する
                        progress_state = {"last": 0.0}

                        def on_progress(p, _state=progress_state):
                            delta = max(0.0, p - _state["last"])
                            _state["last"] = p
                            if delta > 0:
                                event_queue.put(
                                    ("progress_add", delta * 100 / len(files))
                                )

                        output_path, size_ratio, message = process_image(
                            file,
                            output_folder,
                            target_size,
                            operation,
                            size_type,
                            crop_type,
                            aspect_ratio,
                            progress_callback=on_progress,
                            output_format=output_format,
                            filename_pattern=filename_pattern,
                            preset_name=preset_name,
                        )

                        if output_path:
                            final_size = os.path.getsize(output_path) / (1024 * 1024)
                            original_size = os.path.getsize(file) / (1024 * 1024)
                            with Image.open(file) as img:
                                original_width, original_height = img.size
                                # EXIFの回転指定がある場合は表示上の縦横に合わせる
                                orientation = img.getexif().get(0x0112)
                                if orientation in (5, 6, 7, 8):
                                    original_width, original_height = (
                                        original_height,
                                        original_width,
                                    )
                            with Image.open(output_path) as img:
                                final_width, final_height = img.size
                            log_text = (
                                f"処理完了: {file}\n"
                                f"  出力: {output_path}\n"
                                f"  元のサイズ: {original_size:.2f} MB, {original_width}x{original_height}px\n"
                                f"  最終サイズ: {final_size:.2f} MB, {final_width}x{final_height}px\n"
                                f"  サイズ比率: {size_ratio:.2%}\n"
                            )
                            if message:
                                log_text += f"  注記: {message}\n"
                            log_tag = None
                        elif message:
                            log_text = f"{file}: {message}\n"
                            log_tag = "green"
                        else:
                            log_text = f"処理失敗: {file}\n"
                            log_tag = None

                        event_queue.put(("log", log_text, log_tag))
                    except BaseException as e:
                        err_msg = (
                            f"エラー ({file}): {type(e).__name__}: {e}\n"
                            f"{traceback.format_exc()}"
                        )
                        event_queue.put(("log", err_msg, None))

                    event_queue.put(("progress_set", (i + 1) * 100))
                    event_queue.put(("delete_first",))
            except BaseException as e:
                err_msg = (
                    f"バッチ処理中の予期せぬエラー: {type(e).__name__}: {e}\n"
                    f"{traceback.format_exc()}"
                )
                event_queue.put(("log", err_msg, None))
            finally:
                event_queue.put(("done",))

        self.master.after(50, pump_events)
        self._worker_thread = threading.Thread(target=process_images_thread, daemon=True)
        self._worker_thread.start()

    def on_window_configure(self, event):
        """ウィンドウのサイズや位置が変更されたときの処理"""
        if event.widget == self.master:
            # ウィンドウのサイズと位置を取得
            self.window_width = self.master.winfo_width()
            self.window_height = self.master.winfo_height()
            self.window_x = self.master.winfo_x()
            self.window_y = self.master.winfo_y()
            self._apply_responsive_layout(self.window_width)

            # デバウンス用タイマーがあれば停止
            if hasattr(self, 'save_timer'):
                self.master.after_cancel(self.save_timer)

            # 500ms後に設定を保存（頻繁な保存を防ぐため）
            self.save_timer = self.master.after(500, self.save_settings)

    def validate_window_position(self):
        """ウィンドウ位置が画面内に収まるように調整"""
        try:
            # 仮のTkウィンドウで画面サイズを取得
            screen_width = self.master.winfo_screenwidth()
            screen_height = self.master.winfo_screenheight()

            # ウィンドウが完全に画面外にある場合はデフォルト位置に戻す
            # 最低でもウィンドウの一部（100px）が画面内に表示されるようにする
            min_visible = 100

            # X座標の調整
            if self.window_x + self.window_width < min_visible:
                # ウィンドウが左に行きすぎている
                self.window_x = 100
            elif self.window_x > screen_width - min_visible:
                # ウィンドウが右に行きすぎている
                self.window_x = screen_width - self.window_width - 100

            # Y座標の調整
            if self.window_y < 0:
                # ウィンドウが上に行きすぎている
                self.window_y = 100
            elif self.window_y > screen_height - min_visible:
                # ウィンドウが下に行きすぎている
                self.window_y = screen_height - self.window_height - 100

        except Exception as e:
            print(f"ウィンドウ位置検証エラー: {e}")
            # エラーが発生した場合はデフォルト位置
            self.window_x = 100
            self.window_y = 100

    def register_child_process(self, proc):
        """起動した subprocess.Popen を登録し、アプリ終了時に停止させる。"""
        if proc is not None:
            self._child_processes.append(proc)

    def _terminate_child_processes(self):
        """登録済みの子プロセス（ターミナル等）をプロセスツリーごと停止する。"""
        for proc in list(self._child_processes):
            try:
                if proc.poll() is not None:
                    continue
                if platform.system() == "Windows":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    proc.terminate()
            except Exception:
                pass
        for proc in list(self._child_processes):
            try:
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._child_processes.clear()

    def _get_windows_process_ancestors(self):
        """現在のプロセスから親方向へ辿った Windows プロセス情報を取得する。"""
        if platform.system() != "Windows":
            return []

        command = (
            f"$current = {os.getpid()}; "
            "$items = @(); "
            "while ($current) { "
            "  $p = Get-CimInstance Win32_Process -Filter \"ProcessId=$current\"; "
            "  if (-not $p) { break }; "
            "  $items += [pscustomobject]@{ "
            "    ProcessId = [int]$p.ProcessId; "
            "    ParentProcessId = [int]$p.ParentProcessId; "
            "    Name = [string]$p.Name "
            "  }; "
            "  if ($p.ParentProcessId -eq 0) { break }; "
            "  $current = $p.ParentProcessId "
            "}; "
            "$items | ConvertTo-Json -Compress"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return []
            ancestors = json.loads(result.stdout)
            if isinstance(ancestors, dict):
                return [ancestors]
            if isinstance(ancestors, list):
                return ancestors
        except Exception:
            pass
        return []

    def _close_launcher_terminal(self):
        """bat/ps1 経由で起動された外側のターミナルを閉じる。"""
        ancestors = self._get_windows_process_ancestors()
        if not ancestors:
            return

        shell_names = {"cmd.exe", "powershell.exe", "pwsh.exe"}
        skip_parent_names = {"windowsterminal.exe"}
        shell_index = None
        for index, process_info in enumerate(ancestors[1:], start=1):
            name = str(process_info.get("Name", "")).lower()
            if name in shell_names:
                shell_index = index

        if shell_index is None:
            return

        parent_name = ""
        if shell_index + 1 < len(ancestors):
            parent_name = str(ancestors[shell_index + 1].get("Name", "")).lower()
        if parent_name in skip_parent_names:
            return

        try:
            subprocess.run(
                ["taskkill", "/PID", str(ancestors[shell_index]["ProcessId"]), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass

    def on_closing(self):
        """アプリケーション終了時の処理"""
        if self._is_closing:
            return
        self._is_closing = True

        # 保留中のタイマーがあればキャンセル
        if hasattr(self, 'save_timer'):
            try:
                self.master.after_cancel(self.save_timer)
            except Exception:
                pass

        # 最終的な設定を保存
        self.save_settings()

        # ワーカースレッドへ停止を通知して短時間待機
        self._shutdown_event.set()
        worker = self._worker_thread
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)

        # 登録済みの子プロセス（ターミナル等）を停止
        self._terminate_child_processes()

        # bat/ps1 などで起動された場合に残る起動元ターミナルを閉じる
        self._close_launcher_terminal()

        # ウィンドウを閉じる
        self.master.destroy()

    def on_preset_change(self, event):
        """プリセットが選択されたときの処理"""
        preset = self.preset_var.get()

        # カテゴリータイトルの場合は何もしない
        if preset.startswith("---"):
            return

        # カスタムの場合はプリセット名チェックを外す
        if preset == "カスタム":
            self.include_preset_name.set(False)
            self._refresh_ui_state()
            self.save_settings()
            return

        # プリセットデータから設定を取得
        if preset in self.presets_data:
            settings = self.presets_data[preset]

            # サイズタイプと値を設定
            self.size_type_var.set(settings["size_type"])
            self.on_size_type_change()
            self.size_entry.delete(0, tk.END)
            self.size_entry.insert(0, settings["size"])

            # クロップ設定
            self.crop_var.set(settings["crop"])
            self.on_crop_change()

            # カスタム比率の場合
            if settings["crop"] == "custom" and "aspect_width" in settings:
                self.aspect_width.delete(0, tk.END)
                self.aspect_width.insert(0, settings["aspect_width"])
                self.aspect_height.delete(0, tk.END)
                self.aspect_height.insert(0, settings["aspect_height"])

            # プリセット名をファイル名に含めるチェックボックスを有効にする
            self.include_preset_name.set(True)

            self._refresh_ui_state()
            self.save_settings()
