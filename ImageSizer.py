import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image
import threading
from tkinterdnd2 import TkinterDnD, DND_FILES
import tempfile
import shutil


def process_image(
    input_path,
    output_folder,
    target_size,
    operation,
    size_type,
    quality=85,
    progress_callback=None,
):
    with Image.open(input_path) as img:
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        original_width, original_height = img.size

        base_name = os.path.basename(input_path)
        name, ext = os.path.splitext(base_name)

        if ext.lower() == ".gif":
            if progress_callback:
                progress_callback(1.0)
            return None, 1.0, "GIFファイルはスキップされました"

        if size_type == "mb":
            target_size_mb = float(target_size)
            if operation == "auto":
                if original_size == target_size_mb:
                    if progress_callback:
                        progress_callback(1.0)
                    return None, 1.0, f"既に目標サイズ（{target_size_mb:.2f}MB）です"
                operation = "compress" if original_size > target_size_mb else "upscale"
            if operation == "compress" and original_size <= target_size_mb:
                if progress_callback:
                    progress_callback(1.0)
                return None, 1.0, f"既に目標サイズ（{target_size_mb:.2f}MB）以下です"
            elif operation == "upscale" and original_size >= target_size_mb:
                if progress_callback:
                    progress_callback(1.0)
                return None, 1.0, f"既に目標サイズ（{target_size_mb:.2f}MB）以上です"
            size_ratio = (target_size_mb / original_size) ** 0.5
        else:  # size_type == "px"
            target_size = int(target_size)
            if size_type == "width":
                target_dimension = original_width
            else:  # size_type == "height"
                target_dimension = original_height

            if operation == "auto":
                if target_dimension == target_size:
                    if progress_callback:
                        progress_callback(1.0)
                    return None, 1.0, f"既に目標サイズ（{target_size}px）です"
                operation = "compress" if target_dimension > target_size else "upscale"

            if (operation == "compress" and target_dimension <= target_size) or (
                operation == "upscale" and target_dimension >= target_size
            ):
                if progress_callback:
                    progress_callback(1.0)
                return (
                    None,
                    1.0,
                    f"既に目標サイズ（{target_size}px）{'以下' if operation == 'compress' else '以上'}です",
                )

            size_ratio = target_size / target_dimension

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_path = temp_file.name

        try:
            iteration = 0
            max_iterations = 20
            while iteration < max_iterations:
                new_width = int(original_width * size_ratio)
                new_height = int(original_height * size_ratio)

                resized_img = img.resize((new_width, new_height), Image.LANCZOS)

                current_ratio = int(
                    (new_width * new_height) / (original_width * original_height) * 100
                )

                if ext.lower() in [".jpg", ".jpeg"]:
                    resized_img.save(temp_path, quality=quality, optimize=True)
                else:
                    resized_img.save(temp_path, optimize=True)

                new_size = os.path.getsize(temp_path) / (1024 * 1024)

                if progress_callback:
                    progress_callback((iteration + 1) / max_iterations)

                if size_type == "mb":
                    condition = (
                        operation == "compress" and new_size <= target_size_mb
                    ) or (operation == "upscale" and new_size >= target_size_mb)
                else:  # size_type == "px"
                    if size_type == "width":
                        condition = (
                            operation == "compress" and new_width <= target_size
                        ) or (operation == "upscale" and new_width >= target_size)
                    else:  # size_type == "height"
                        condition = (
                            operation == "compress" and new_height <= target_size
                        ) or (operation == "upscale" and new_height >= target_size)

                if condition:
                    operation_name = (
                        "compressed" if operation == "compress" else "upscaled"
                    )
                    output_path = os.path.join(
                        output_folder,
                        f"{name}_{operation_name}_{current_ratio}of100%{ext}",
                    )
                    shutil.copy2(temp_path, output_path)
                    if progress_callback:
                        progress_callback(1.0)
                    return output_path, size_ratio, None

                if operation == "compress":
                    size_ratio *= 0.9
                    quality = max(quality - 5, 10)
                else:  # upscale
                    size_ratio *= 1.1
                    quality = min(quality + 5, 95)

                iteration += 1

            if progress_callback:
                progress_callback(1.0)
            return None, 0, "目標サイズに到達できませんでした"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class ImageProcessorApp:
    def __init__(self, master):
        self.master = master
        master.title("画像処理ツール")
        master.geometry("600x650")  # ウィンドウサイズを少し大きくしました

        self.create_widgets()
        self.setup_drop_target()

    def create_widgets(self):
        ttk.Label(self.master, text="画像をドラッグアンドドロップしてください:").pack(
            pady=10
        )

        self.file_listbox = tk.Listbox(self.master, width=70, height=5)
        self.file_listbox.pack(pady=5)

        ttk.Button(self.master, text="ファイルを選択", command=self.browse_files).pack(
            pady=5
        )

        # サイズタイプの選択
        self.size_type_var = tk.StringVar(value="mb")
        ttk.Radiobutton(
            self.master,
            text="MBで指定",
            variable=self.size_type_var,
            value="mb",
            command=self.on_size_type_change,
        ).pack()
        ttk.Radiobutton(
            self.master,
            text="横ピクセルで指定",
            variable=self.size_type_var,
            value="width",
            command=self.on_size_type_change,
        ).pack()
        ttk.Radiobutton(
            self.master,
            text="縦ピクセルで指定",
            variable=self.size_type_var,
            value="height",
            command=self.on_size_type_change,
        ).pack()
        self.size_frame = ttk.Frame(self.master)
        self.size_frame.pack(pady=5)

        self.size_label = ttk.Label(self.size_frame, text="目標サイズ (MB):")
        self.size_label.pack(side=tk.LEFT)

        self.size_entry = ttk.Entry(self.size_frame, width=10)
        self.size_entry.insert(0, "2")
        self.size_entry.pack(side=tk.LEFT, padx=5)
        self.size_entry.bind("<FocusOut>", self.on_setting_change)

        # 操作モードの選択（自動調整を追加）
        self.operation_var = tk.StringVar(value="auto")
        ttk.Radiobutton(
            self.master,
            text="自動調整",
            variable=self.operation_var,
            value="auto",
            command=self.on_setting_change,
        ).pack()
        ttk.Radiobutton(
            self.master,
            text="圧縮",
            variable=self.operation_var,
            value="compress",
            command=self.on_setting_change,
        ).pack()
        ttk.Radiobutton(
            self.master,
            text="拡大",
            variable=self.operation_var,
            value="upscale",
            command=self.on_setting_change,
        ).pack()

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
        self.process_images()

    def on_size_type_change(self):
        size_type = self.size_type_var.get()
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
        self.on_setting_change()

    def on_setting_change(self, event=None):
        self.process_images()

    def process_images(self):
        files = list(self.file_listbox.get(0, tk.END))
        try:
            target_size = float(self.size_entry.get())
        except ValueError:
            messagebox.showerror("エラー", "目標サイズには数値を入力してください。")
            return

        if not files:
            return

        operation = self.operation_var.get()
        size_type = self.size_type_var.get()

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
                        progress_callback=lambda p: update_progress(
                            p * 100 / len(files)
                        ),
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

                # 処理が終わったファイルをリストから削除
                self.master.after(0, lambda: self.file_listbox.delete(0))

            self.progress["value"] = self.progress["maximum"]
            self.master.update_idletasks()

        threading.Thread(target=process_images_thread, daemon=True).start()


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = ImageProcessorApp(root)
    root.mainloop()
