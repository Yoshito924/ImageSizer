import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES
import threading
from PIL import Image
from image_processor import process_image


class ImageProcessorApp:
    def __init__(self, master):
        self.master = master
        master.title("ImageSizer")
        
        # 設定をロード
        self.load_settings()
        
        # ウィンドウサイズと位置を設定
        geometry = f"{self.window_width}x{self.window_height}+{self.window_x}+{self.window_y}"
        master.geometry(geometry)
        
        # ウィンドウ位置とサイズ変更のイベントをバインド
        master.bind("<Configure>", self.on_window_configure)

        self.create_widgets()
        self.setup_drop_target()

    def load_settings(self):
        """設定をJSONファイルからロード"""
        self.settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    import json
                    settings = json.load(f)
                    self.always_on_top = settings.get("always_on_top", False)
                    self.crop_type = settings.get("crop_type", "none")
                    self.size_type = settings.get("size_type", "mb")
                    self.operation = settings.get("operation", "auto")
                    self.output_format = settings.get("output_format", "original")
                    self.filename_pattern = settings.get("filename_pattern", "default")
                    self.window_width = settings.get("window_width", 900)
                    self.window_height = settings.get("window_height", 600)
                    self.window_x = settings.get("window_x", 100)
                    self.window_y = settings.get("window_y", 100)
            else:
                self.always_on_top = False
                self.crop_type = "none"
                self.size_type = "mb"
                self.operation = "auto"
                self.output_format = "original"
                self.filename_pattern = "default"
                self.window_width = 900
                self.window_height = 600
                self.window_x = 100
                self.window_y = 100
        except Exception as e:
            print(f"設定ロードエラー: {e}")
            self.always_on_top = False
            self.crop_type = "none"
            self.size_type = "mb"
            self.operation = "auto"
            self.output_format = "original"
            self.filename_pattern = "default"
            self.window_width = 900
            self.window_height = 600
            self.window_x = 100
            self.window_y = 100

    def save_settings(self):
        """設定をJSONファイルに保存"""
        try:
            settings = {
                "always_on_top": self.always_on_top,
                "crop_type": self.crop_var.get(),
                "size_type": self.size_type_var.get(),
                "operation": self.operation_var.get(),
                "output_format": self.format_var.get(),
                "filename_pattern": self.filename_pattern_var.get(),
                "window_width": self.window_width,
                "window_height": self.window_height,
                "window_x": self.window_x,
                "window_y": self.window_y
            }
            with open(self.settings_file, "w", encoding="utf-8") as f:
                import json
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"設定保存エラー: {e}")

    def toggle_always_on_top(self):
        """最前面表示のトグル"""
        self.always_on_top = not self.always_on_top
        self.master.attributes("-topmost", self.always_on_top)
        self.save_settings()

    def create_widgets(self):
        # 最前面表示トグルボタン
        toggle_frame = ttk.Frame(self.master)
        toggle_frame.pack(fill=tk.X, padx=10, pady=5)
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
            file_frame, text="画像をドラッグアンドドロップしてください（複数選択可）:"
        ).pack(pady=5)
        self.file_listbox = tk.Listbox(file_frame, width=70, height=5)
        self.file_listbox.pack(pady=5)
        ttk.Button(file_frame, text="ファイルを選択", command=self.browse_files).pack(
            pady=5
        )

        # プリセット選択部分
        preset_frame = ttk.LabelFrame(self.master, text="プリセット設定", padding=(10, 5))
        preset_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(preset_frame, text="プリセット:").pack(side=tk.LEFT, padx=(0, 5))
        self.preset_var = tk.StringVar(value="カスタム")
        self.preset_combo = ttk.Combobox(
            preset_frame,
            textvariable=self.preset_var,
            values=[
                "カスタム",
                "--- SNSヘッダー ---",
                "X (Twitter) ヘッダー: 1500x500",
                "note ヘッダー: 1280x670",
                "YouTube ヘッダー: 2048x1152",
                "--- Web画像 ---",
                "メインビジュアル: 1600px幅",
                "プロジェクト詳細: 1200px幅",
                "サムネイル: 400px幅",
                "--- SNS投稿 ---",
                "Instagram 正方形: 1080x1080",
                "Instagram 縦長: 1080x1350",
                "Instagram ストーリー: 1080x1920"
            ],
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
        self.aspect_width.pack(side=tk.LEFT)
        ttk.Label(self.aspect_ratio_frame, text=":").pack(side=tk.LEFT)
        self.aspect_height = ttk.Entry(self.aspect_ratio_frame, width=5)
        self.aspect_height.pack(side=tk.LEFT)
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

        # サイズ入力用のフレーム
        self.size_input_frame = ttk.Frame(size_frame)
        self.size_input_frame.pack(pady=5)
        self.size_label = ttk.Label(self.size_input_frame, text="目標サイズ (MB):")
        self.size_label.pack(side=tk.LEFT)
        self.size_entry = ttk.Entry(self.size_input_frame, width=10)
        self.size_entry.insert(0, "2")
        self.size_entry.pack(side=tk.LEFT, padx=5)

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

        # 出力ファイル名パターン選択部分（左側）
        filename_frame = ttk.LabelFrame(
            left_frame, text="出力ファイル名パターン", padding=(10, 5)
        )
        filename_frame.pack(fill=tk.X, pady=5)
        
        # チェックボックス用の変数
        self.include_crop_type = tk.BooleanVar(value=False)
        self.include_size_ratio = tk.BooleanVar(value=False)
        self.include_timestamp = tk.BooleanVar(value=False)
        self.include_sequential = tk.BooleanVar(value=False)
        self.include_preset_name = tk.BooleanVar(value=False)
        
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

        # プログレスバーとログ出力
        self.progress = ttk.Progressbar(
            self.master, orient="horizontal", length=400, mode="determinate"
        )
        self.progress.pack(pady=10)
        self.output_text = tk.Text(self.master, height=10, width=70)
        self.output_text.pack(pady=10)
        self.output_text.tag_configure("green", foreground="green")

    def setup_drop_target(self):
        self.master.drop_target_register(DND_FILES)
        self.master.dnd_bind("<<Drop>>", self.drop)

    def drop(self, event):
        files = self.master.tk.splitlist(event.data)
        self.add_files(files)
        self.process_images()

    def add_files(self, files):
        for file in files:
            if file not in self.file_listbox.get(0, tk.END):
                self.file_listbox.insert(tk.END, file)

    def browse_files(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff")]
        )
        self.add_files(files)

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
                self.size_entry.insert(0, "2")
            elif size_type == "width":
                self.size_label.config(text="目標サイズ (横px):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, "1920")
            else:  # height
                self.size_label.config(text="目標サイズ (縦px):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, "1080")
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
        if format_value == "original":
            output_format = None
        elif format_value == "webp":
            output_format = "webp"
        elif format_value == "png":
            output_format = "png"

        self.output_text.delete(1.0, tk.END)
        self.progress["maximum"] = len(files) * 100
        self.progress["value"] = 0

        def update_progress(file_progress):
            self.progress["value"] += file_progress
            self.master.update_idletasks()

        def process_images_thread():
            for i, file in enumerate(files):
                try:
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

                    if message:
                        self.output_text.insert(tk.END, f"{file}: {message}\n", "green")
                    elif output_path:
                        final_size = os.path.getsize(output_path) / (1024 * 1024)
                        original_size = os.path.getsize(file) / (1024 * 1024)
                        with Image.open(file) as img:
                            original_width, original_height = img.size
                        with Image.open(output_path) as img:
                            final_width, final_height = img.size
                        self.output_text.insert(tk.END, f"処理完了: {file}\n")
                        self.output_text.insert(tk.END, f"  出力: {output_path}\n")
                        self.output_text.insert(
                            tk.END,
                            f"  元のサイズ: {original_size:.2f} MB, {original_width}x{original_height}px\n",
                        )
                        self.output_text.insert(
                            tk.END,
                            f"  最終サイズ: {final_size:.2f} MB, {final_width}x{final_height}px\n",
                        )
                        self.output_text.insert(
                            tk.END, f"  サイズ比率: {size_ratio:.2%}\n"
                        )
                    else:
                        self.output_text.insert(tk.END, f"処理失敗: {file}\n")
                    self.output_text.see(tk.END)
                except Exception as e:
                    self.output_text.insert(tk.END, f"エラー ({file}): {str(e)}\n")

                self.progress["value"] = (i + 1) * 100
                self.master.after(0, lambda: self.file_listbox.delete(0))

            self.progress["value"] = self.progress["maximum"]
            self.master.update_idletasks()

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
    
    def on_preset_change(self, event):
        """プリセットが選択されたときの処理"""
        preset = self.preset_var.get()
        
        # プリセット定義
        presets = {
            "X (Twitter) ヘッダー: 1500x500": {
                "size_type": "width",
                "size": "1500",
                "crop": "custom",
                "aspect_width": "3",
                "aspect_height": "1"
            },
            "note ヘッダー: 1280x670": {
                "size_type": "width",
                "size": "1280",
                "crop": "custom",
                "aspect_width": "128",
                "aspect_height": "67"
            },
            "YouTube ヘッダー: 2048x1152": {
                "size_type": "width",
                "size": "2048",
                "crop": "16:9"
            },
            "メインビジュアル: 1600px幅": {
                "size_type": "width",
                "size": "1600",
                "crop": "none"
            },
            "プロジェクト詳細: 1200px幅": {
                "size_type": "width",
                "size": "1200",
                "crop": "none"
            },
            "サムネイル: 400px幅": {
                "size_type": "width",
                "size": "400",
                "crop": "none"
            },
            "Instagram 正方形: 1080x1080": {
                "size_type": "width",
                "size": "1080",
                "crop": "square"
            },
            "Instagram 縦長: 1080x1350": {
                "size_type": "width",
                "size": "1080",
                "crop": "custom",
                "aspect_width": "4",
                "aspect_height": "5"
            },
            "Instagram ストーリー: 1080x1920": {
                "size_type": "width",
                "size": "1080",
                "crop": "9:16"
            }
        }
        
        if preset in presets:
            settings = presets[preset]
            
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
            
            self.save_settings()
