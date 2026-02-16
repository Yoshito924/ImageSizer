import json
import os
import platform
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES
import threading
from PIL import Image
from image_processor import process_image

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

        # ウィンドウ位置とサイズ変更のイベントをバインド
        master.bind("<Configure>", self.on_window_configure)

        # アプリケーション終了時に設定を保存
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.create_widgets()
        self.setup_drop_target()

    def _get_theme_colors(self):
        """sv_ttkテーマに合わせた非ttkウィジェット用カラーを返す"""
        style = ttk.Style()
        try:
            bg = style.lookup("TFrame", "background") or "#fafafa"
        except tk.TclError:
            bg = "#fafafa"
        return {
            "bg": bg,
            "fg": "#1c1c1c",
            "select_bg": "#0078d4",
            "select_fg": "#ffffff",
            "border": "#e0e0e0",
        }

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
        colors = self._get_theme_colors()

        # 最前面表示トグルボタン
        toggle_frame = ttk.Frame(self.master)
        toggle_frame.pack(fill=tk.X, padx=10, pady=(8, 2))
        self.toggle_button = ttk.Checkbutton(
            toggle_frame,
            text="常に最前面に表示",
            command=self.toggle_always_on_top
        )
        self.toggle_button.pack(side=tk.RIGHT)
        if self.always_on_top:
            self.toggle_button.state(['selected'])
            self.master.attributes("-topmost", True)

        # ファイル選択部分
        file_frame = ttk.LabelFrame(self.master, text="ファイル選択", padding=(10, 5))
        file_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(
            file_frame, text="画像をドラッグ&ドロップ、またはファイルを選択してください："
        ).pack(anchor=tk.W, pady=(0, 5))

        # Listbox + Scrollbar
        listbox_frame = ttk.Frame(file_frame)
        listbox_frame.pack(fill=tk.X, pady=(0, 5))
        listbox_scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL)
        self.file_listbox = tk.Listbox(
            listbox_frame,
            width=70,
            height=5,
            selectmode=tk.EXTENDED,
            yscrollcommand=listbox_scrollbar.set,
            bg=colors["bg"],
            fg=colors["fg"],
            selectbackground=colors["select_bg"],
            selectforeground=colors["select_fg"],
            highlightthickness=1,
            highlightcolor=colors["border"],
            highlightbackground=colors["border"],
            relief=tk.FLAT,
            font=("Consolas", 9),
        )
        listbox_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # ドラッグ&ドロップ時の背景色を保持
        self._listbox_default_bg = colors["bg"]

        # ボタン行: [ファイルを選択] [選択を削除] [すべてクリア]
        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_frame, text="ファイルを選択", command=self.browse_files).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(btn_frame, text="選択を削除", command=self.remove_selected_files).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(btn_frame, text="すべてクリア", command=self.clear_all_files).pack(
            side=tk.LEFT
        )

        # プリセット選択部分
        preset_frame = ttk.LabelFrame(self.master, text="プリセット設定", padding=(10, 5))
        preset_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(preset_frame, text="プリセット:").pack(side=tk.LEFT, padx=(0, 5))
        self.preset_var = tk.StringVar(value=getattr(self, 'preset', "カスタム"))
        self.preset_combo = ttk.Combobox(
            preset_frame,
            textvariable=self.preset_var,
            values=self.preset_values,
            state="readonly",
            width=40
        )
        self.preset_combo.pack(side=tk.LEFT)
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_change)

        # 左右のフレームを作成
        settings_frame = ttk.Frame(self.master)
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        # 左側のフレーム
        left_frame = ttk.Frame(settings_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # 右側のフレーム
        right_frame = ttk.Frame(settings_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # クロップ設定部分（左側）
        crop_frame = ttk.LabelFrame(left_frame, text="クロップ設定", padding=(10, 5))
        crop_frame.pack(fill=tk.X, pady=5)
        self.crop_var = tk.StringVar(value=self.crop_type)
        ttk.Radiobutton(
            crop_frame,
            text="クロップなし",
            variable=self.crop_var,
            value="none",
            command=self.on_crop_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            crop_frame,
            text="正方形（1:1）",
            variable=self.crop_var,
            value="square",
            command=self.on_crop_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            crop_frame,
            text="16:9",
            variable=self.crop_var,
            value="16:9",
            command=self.on_crop_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            crop_frame,
            text="4:3",
            variable=self.crop_var,
            value="4:3",
            command=self.on_crop_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            crop_frame,
            text="9:16",
            variable=self.crop_var,
            value="9:16",
            command=self.on_crop_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            crop_frame,
            text="1:√2（縦長・A4等）",
            variable=self.crop_var,
            value="1:√2",
            command=self.on_crop_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            crop_frame,
            text="√2:1（横長・A4等）",
            variable=self.crop_var,
            value="√2:1",
            command=self.on_crop_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            crop_frame,
            text="カスタム比率",
            variable=self.crop_var,
            value="custom",
            command=self.on_crop_change,
        ).pack(anchor=tk.W)

        # カスタム比率入力用のフレーム
        self.aspect_ratio_frame = ttk.Frame(crop_frame)
        self.aspect_ratio_frame.pack(pady=5)
        ttk.Label(self.aspect_ratio_frame, text="縦横比:").pack(side=tk.LEFT)
        self.aspect_width = ttk.Entry(self.aspect_ratio_frame, width=5)
        self.aspect_width.insert(0, str(getattr(self, 'aspect_width_value', 16.0)))
        self.aspect_width.pack(side=tk.LEFT)
        ttk.Label(self.aspect_ratio_frame, text=":").pack(side=tk.LEFT)
        self.aspect_height = ttk.Entry(self.aspect_ratio_frame, width=5)
        self.aspect_height.insert(0, str(getattr(self, 'aspect_height_value', 9.0)))
        self.aspect_height.pack(side=tk.LEFT)
        # アスペクト比入力値が変更されたときに保存
        self.aspect_width.bind("<KeyRelease>", lambda e: self.master.after(1000, self.save_settings))
        self.aspect_height.bind("<KeyRelease>", lambda e: self.master.after(1000, self.save_settings))
        # 設定からクロップタイプがcustomの場合は表示、それ以外は非表示
        if self.crop_type != "custom":
            self.aspect_ratio_frame.pack_forget()

        # サイズ変更設定部分（右側）
        size_frame = ttk.LabelFrame(right_frame, text="目標サイズ設定", padding=(10, 5))
        size_frame.pack(fill=tk.X, pady=5)
        self.size_type_var = tk.StringVar(value=self.size_type)
        ttk.Radiobutton(
            size_frame,
            text="変更なし",
            variable=self.size_type_var,
            value="none",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            size_frame,
            text="MBで指定",
            variable=self.size_type_var,
            value="mb",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            size_frame,
            text="KBで指定",
            variable=self.size_type_var,
            value="kb",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            size_frame,
            text="横ピクセルで指定",
            variable=self.size_type_var,
            value="width",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            size_frame,
            text="縦ピクセルで指定",
            variable=self.size_type_var,
            value="height",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            size_frame,
            text="長辺で指定",
            variable=self.size_type_var,
            value="long_edge",
            command=self.on_size_type_change,
        ).pack(anchor=tk.W)

        # サイズ入力用のフレーム
        self.size_input_frame = ttk.Frame(size_frame)
        self.size_input_frame.pack(pady=5)
        # 設定から初期値とラベルを取得
        if hasattr(self, 'size_type') and self.size_type == "mb":
            initial_value = str(getattr(self, 'mb_size', 2))
            label_text = "目標サイズ (MB):"
        elif hasattr(self, 'size_type') and self.size_type == "kb":
            initial_value = str(getattr(self, 'kb_size', 500))
            label_text = "目標サイズ (KB):"
        elif hasattr(self, 'size_type') and self.size_type == "width":
            initial_value = str(getattr(self, 'width_px', 1920))
            label_text = "目標サイズ (横px):"
        elif hasattr(self, 'size_type') and self.size_type == "height":
            initial_value = str(getattr(self, 'height_px', 1080))
            label_text = "目標サイズ (縦px):"
        elif hasattr(self, 'size_type') and self.size_type == "long_edge":
            initial_value = str(getattr(self, 'long_edge_px', 1920))
            label_text = "目標サイズ (長辺px):"
        else:
            initial_value = "2"
            label_text = "目標サイズ (MB):"

        self.size_label = ttk.Label(self.size_input_frame, text=label_text)
        self.size_label.pack(side=tk.LEFT)
        self.size_entry = ttk.Entry(self.size_input_frame, width=10)
        self.size_entry.insert(0, initial_value)
        self.size_entry.pack(side=tk.LEFT, padx=5)
        # サイズ入力値が変更されたときに保存
        self.size_entry.bind("<KeyRelease>", lambda e: self.master.after(1000, self.save_settings))

        # 設定からサイズタイプが"none"の場合は入力フレームを非表示
        if self.size_type == "none":
            self.size_input_frame.pack_forget()

        # 自動調整モードを固定で使用
        self.operation_var = tk.StringVar(value="auto")

        # 出力フォーマット選択部分（右側）
        format_frame = ttk.LabelFrame(
            right_frame, text="出力フォーマット", padding=(10, 5)
        )
        format_frame.pack(fill=tk.X, pady=5)
        self.format_var = tk.StringVar(value=self.output_format)
        ttk.Radiobutton(
            format_frame,
            text="元のフォーマットを維持",
            variable=self.format_var,
            value="original",
            command=self.save_settings
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            format_frame,
            text="WebP形式に変換",
            variable=self.format_var,
            value="webp",
            command=self.save_settings
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            format_frame,
            text="PNG形式に変換",
            variable=self.format_var,
            value="png",
            command=self.save_settings
        ).pack(anchor=tk.W)

        # 出力先選択部分（右側）
        output_dest_frame = ttk.LabelFrame(
            right_frame, text="出力先", padding=(10, 5)
        )
        output_dest_frame.pack(fill=tk.X, pady=5)
        self.output_dest_var = tk.StringVar(value=getattr(self, 'output_destination', 'original'))
        ttk.Radiobutton(
            output_dest_frame,
            text="元のフォルダ",
            variable=self.output_dest_var,
            value="original",
            command=self.save_settings
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            output_dest_frame,
            text="outputフォルダ",
            variable=self.output_dest_var,
            value="output",
            command=self.save_settings
        ).pack(anchor=tk.W)
        ttk.Button(
            output_dest_frame,
            text="出力先フォルダを開く",
            command=self.open_output_folder
        ).pack(anchor=tk.W, pady=(5, 0))

        # 出力ファイル名パターン選択部分（左側）
        filename_frame = ttk.LabelFrame(
            left_frame, text="出力ファイル名パターン", padding=(10, 5)
        )
        filename_frame.pack(fill=tk.X, pady=5)

        # チェックボックス用の変数（設定から復元）
        self.include_crop_type = tk.BooleanVar(value=getattr(self, 'include_crop_type_value', False))
        self.include_size_ratio = tk.BooleanVar(value=getattr(self, 'include_size_ratio_value', False))
        self.include_timestamp = tk.BooleanVar(value=getattr(self, 'include_timestamp_value', False))
        self.include_sequential = tk.BooleanVar(value=getattr(self, 'include_sequential_value', False))
        self.include_preset_name = tk.BooleanVar(value=getattr(self, 'include_preset_name_value', False))

        ttk.Label(
            filename_frame,
            text="ファイル名に含める情報を選択してください："
        ).pack(anchor=tk.W, pady=(0, 5))

        ttk.Checkbutton(
            filename_frame,
            text="クロップタイプ（クロップ時のみ）",
            variable=self.include_crop_type
        ).pack(anchor=tk.W)

        ttk.Checkbutton(
            filename_frame,
            text="サイズ比率（サイズ変更時のみ）",
            variable=self.include_size_ratio
        ).pack(anchor=tk.W)

        ttk.Checkbutton(
            filename_frame,
            text="タイムスタンプ（YYYYMMDD_HHMMSS）",
            variable=self.include_timestamp
        ).pack(anchor=tk.W)

        ttk.Checkbutton(
            filename_frame,
            text="連番（001, 002, ...）",
            variable=self.include_sequential
        ).pack(anchor=tk.W)

        ttk.Checkbutton(
            filename_frame,
            text="プリセット名（プリセット使用時のみ）",
            variable=self.include_preset_name
        ).pack(anchor=tk.W)

        # 「処理を実行」ボタン
        process_btn_frame = ttk.Frame(self.master)
        process_btn_frame.pack(fill=tk.X, padx=10, pady=(8, 4))
        self.process_button = ttk.Button(
            process_btn_frame,
            text="処理を実行",
            style="Accent.TButton",
            command=self.process_images,
        )
        self.process_button.pack(fill=tk.X)

        # プログレスバー（ウィンドウ幅に追従）
        self.progress = ttk.Progressbar(
            self.master, orient="horizontal", mode="determinate"
        )
        self.progress.pack(fill=tk.X, padx=10, pady=(4, 4))

        # 処理ログ
        log_frame = ttk.LabelFrame(self.master, text="処理ログ", padding=(10, 5))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        log_inner = ttk.Frame(log_frame)
        log_inner.pack(fill=tk.BOTH, expand=True)
        log_scrollbar = ttk.Scrollbar(log_inner, orient=tk.VERTICAL)
        self.output_text = tk.Text(
            log_inner,
            height=8,
            width=70,
            yscrollcommand=log_scrollbar.set,
            bg=colors["bg"],
            fg=colors["fg"],
            highlightthickness=1,
            highlightcolor=colors["border"],
            highlightbackground=colors["border"],
            relief=tk.FLAT,
            font=("Consolas", 9),
        )
        log_scrollbar.config(command=self.output_text.yview)
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.output_text.tag_configure("green", foreground="green")

    def setup_drop_target(self):
        self.master.drop_target_register(DND_FILES)
        self.master.dnd_bind("<<Drop>>", self.drop)
        self.master.dnd_bind("<<DragEnter>>", self._on_drag_enter)
        self.master.dnd_bind("<<DragLeave>>", self._on_drag_leave)

    def _on_drag_enter(self, event):
        """ドラッグ&ドロップの視覚フィードバック（進入時）"""
        self.file_listbox.config(bg="#e3f2fd")

    def _on_drag_leave(self, event):
        """ドラッグ&ドロップの視覚フィードバック（離脱時）"""
        self.file_listbox.config(bg=self._listbox_default_bg)

    def drop(self, event):
        self.file_listbox.config(bg=self._listbox_default_bg)
        files = self.master.tk.splitlist(event.data)
        self.add_files(files)

    def add_files(self, files):
        for file in files:
            if file not in self.file_listbox.get(0, tk.END):
                self.file_listbox.insert(tk.END, file)

    def remove_selected_files(self):
        """選択されたファイルをリストから削除"""
        selected = self.file_listbox.curselection()
        for i in reversed(selected):
            self.file_listbox.delete(i)

    def clear_all_files(self):
        """すべてのファイルをリストからクリア"""
        self.file_listbox.delete(0, tk.END)

    def browse_files(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.heic;*.heif;*.webp")]
        )
        self.add_files(files)

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
            self.aspect_ratio_frame.pack()
        else:
            self.aspect_ratio_frame.pack_forget()
        self.save_settings()

    def on_size_type_change(self):
        size_type = self.size_type_var.get()
        if size_type == "none":
            self.size_input_frame.pack_forget()
        else:
            self.size_input_frame.pack()
            if size_type == "mb":
                self.size_label.config(text="目標サイズ (MB):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'mb_size', 2)))
            elif size_type == "kb":
                self.size_label.config(text="目標サイズ (KB):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'kb_size', 500)))
            elif size_type == "width":
                self.size_label.config(text="目標サイズ (横px):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'width_px', 1920)))
            elif size_type == "height":
                self.size_label.config(text="目標サイズ (縦px):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'height_px', 1080)))
            elif size_type == "long_edge":
                self.size_label.config(text="目標サイズ (長辺px):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, str(getattr(self, 'long_edge_px', 1920)))
        self.save_settings()

    def process_images(self):
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

        self.output_text.delete(1.0, tk.END)
        self.progress["maximum"] = len(files) * 100
        self.progress["value"] = 0

        # 処理中はボタンを無効化
        self.process_button.config(state="disabled")

        # スレッドセーフなGUI更新用ヘルパー関数
        def _add_progress(value):
            self.progress["value"] += value

        def update_progress(file_progress):
            self.master.after(0, lambda v=file_progress: _add_progress(v))

        def _set_progress(value):
            self.progress["value"] = value

        def _delete_first_item():
            if self.file_listbox.size() > 0:
                self.file_listbox.delete(0)

        def _log_output(text, tag=None):
            if tag:
                self.output_text.insert(tk.END, text, tag)
            else:
                self.output_text.insert(tk.END, text)
            self.output_text.see(tk.END)

        max_progress = len(files) * 100

        def process_images_thread():
            # 出力先の決定
            output_dest = self.output_dest_var.get()
            if output_dest == "output":
                output_base = os.path.join(os.path.dirname(__file__), "output")
                if not os.path.exists(output_base):
                    os.makedirs(output_base)

            for i, file in enumerate(files):
                try:
                    if output_dest == "output":
                        output_folder = output_base
                    else:
                        output_folder = os.path.dirname(file)
                    output_path, size_ratio, message = process_image(
                        file,
                        output_folder,
                        target_size,
                        operation,
                        size_type,
                        crop_type,
                        aspect_ratio,
                        progress_callback=lambda p: update_progress(
                            p * 100 / len(files)
                        ),
                        output_format=output_format,
                        filename_pattern={
                            "include_crop_type": self.include_crop_type.get(),
                            "include_size_ratio": self.include_size_ratio.get(),
                            "include_timestamp": self.include_timestamp.get(),
                            "include_sequential": self.include_sequential.get(),
                            "include_preset_name": self.include_preset_name.get()
                        },
                        preset_name=self.preset_var.get() if self.preset_var.get() != "カスタム" else None
                    )

                    # ログメッセージを構築（スレッド内で計算してからGUIに送る）
                    if message:
                        log_text = f"{file}: {message}\n"
                        log_tag = "green"
                    elif output_path:
                        final_size = os.path.getsize(output_path) / (1024 * 1024)
                        original_size = os.path.getsize(file) / (1024 * 1024)
                        with Image.open(file) as img:
                            original_width, original_height = img.size
                        with Image.open(output_path) as img:
                            final_width, final_height = img.size
                        log_text = (
                            f"処理完了: {file}\n"
                            f"  出力: {output_path}\n"
                            f"  元のサイズ: {original_size:.2f} MB, {original_width}x{original_height}px\n"
                            f"  最終サイズ: {final_size:.2f} MB, {final_width}x{final_height}px\n"
                            f"  サイズ比率: {size_ratio:.2%}\n"
                        )
                        log_tag = None
                    else:
                        log_text = f"処理失敗: {file}\n"
                        log_tag = None

                    self.master.after(0, lambda t=log_text, tag=log_tag: _log_output(t, tag))
                except Exception as e:
                    err_msg = f"エラー ({file}): {str(e)}\n"
                    self.master.after(0, lambda m=err_msg: _log_output(m))

                progress_val = (i + 1) * 100
                self.master.after(0, lambda v=progress_val: _set_progress(v))
                self.master.after(0, _delete_first_item)

            self.master.after(0, lambda: _set_progress(max_progress))
            # 処理完了後にボタンを再有効化
            self.master.after(0, lambda: self.process_button.config(state="normal"))

        threading.Thread(target=process_images_thread, daemon=True).start()

    def on_window_configure(self, event):
        """ウィンドウのサイズや位置が変更されたときの処理"""
        if event.widget == self.master:
            # ウィンドウのサイズと位置を取得
            self.window_width = self.master.winfo_width()
            self.window_height = self.master.winfo_height()
            self.window_x = self.master.winfo_x()
            self.window_y = self.master.winfo_y()

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

    def on_closing(self):
        """アプリケーション終了時の処理"""
        # 保留中のタイマーがあればキャンセル
        if hasattr(self, 'save_timer'):
            try:
                self.master.after_cancel(self.save_timer)
            except Exception:
                pass

        # 最終的な設定を保存
        self.save_settings()

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

            self.save_settings()
