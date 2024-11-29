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
        master.geometry("600x800+100+100")

        self.create_widgets()
        self.setup_drop_target()

    def create_widgets(self):
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

        # クロップ設定部分
        crop_frame = ttk.LabelFrame(self.master, text="クロップ設定", padding=(10, 5))
        crop_frame.pack(fill=tk.X, padx=10, pady=5)
        self.crop_var = tk.StringVar(value="none")
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

        # サイズ変更設定部分
        size_frame = ttk.LabelFrame(self.master, text="目標サイズ設定", padding=(10, 5))
        size_frame.pack(fill=tk.X, padx=10, pady=5)
        self.size_type_var = tk.StringVar(value="mb")
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

        # 拡大・縮小モードの選択部分
        operation_frame = ttk.LabelFrame(
            self.master, text="拡大・縮小モードの選択", padding=(10, 5)
        )
        operation_frame.pack(fill=tk.X, padx=10, pady=5)
        self.operation_var = tk.StringVar(value="auto")
        ttk.Radiobutton(
            operation_frame,
            text="自動調整（目標サイズより小さければ拡大、大きければ圧縮）",
            variable=self.operation_var,
            value="auto",
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            operation_frame, text="圧縮", variable=self.operation_var, value="compress"
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            operation_frame, text="拡大", variable=self.operation_var, value="upscale"
        ).pack(anchor=tk.W)

        # 出力フォーマット選択部分
        format_frame = ttk.LabelFrame(
            self.master, text="出力フォーマット", padding=(10, 5)
        )
        format_frame.pack(fill=tk.X, padx=10, pady=5)
        self.format_var = tk.StringVar(value="original")
        ttk.Radiobutton(
            format_frame,
            text="元のフォーマットを維持",
            variable=self.format_var,
            value="original",
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            format_frame,
            text="WebP形式に変換",
            variable=self.format_var,
            value="webp",
        ).pack(anchor=tk.W)

        # プログレスバーとログ出力
        self.progress = ttk.Progressbar(
            self.master, orient="horizontal", length=400, mode="determinate"
        )
        self.progress.pack(pady=10)
        self.output_text = tk.Text(self.master, height=15, width=70)
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

        output_format = None if self.format_var.get() == "original" else "webp"

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
