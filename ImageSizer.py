import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image
import threading
from tkinterdnd2 import TkinterDnD, DND_FILES
import tempfile
import shutil


# 画像をクロップする関数
def crop_image(img, crop_type, aspect_ratio=None):
    # 画像の幅と高さを取得
    width, height = img.size
    # クロップタイプに応じて処理を分岐
    if crop_type == "square":
        # 正方形にクロップ
        size = min(width, height)  # 幅と高さの小さい方を取得
        left = (width - size) // 2  # 左端の座標
        top = (height - size) // 2  # 上端の座標
        right = left + size  # 右端の座標
        bottom = top + size  # 下端の座標
    elif crop_type == "custom":
        # カスタム比率でクロップ
        if aspect_ratio is None:
            # 比率が指定されていない場合はそのまま返す
            return img
        target_ratio = aspect_ratio[0] / aspect_ratio[1]  # 目標比率を計算
        if width / height > target_ratio:
            # 幅の方が比率的に大きい場合
            new_width = int(height * target_ratio)  # 新しい幅を計算
            left = (width - new_width) // 2  # 左端の座標
            right = left + new_width  # 右端の座標
            top, bottom = 0, height  # 上端と下端はそのまま
        else:
            # 高さの方が比率的に大きい場合
            new_height = int(width / target_ratio)  # 新しい高さを計算
            top = (height - new_height) // 2  # 上端の座標
            bottom = top + new_height  # 下端の座標
            left, right = 0, width  # 左端と右端はそのまま
    elif crop_type == "16:9":
        # 16:9 比率でクロップ
        target_ratio = 16 / 9  # 16:9 の比率
        if width / height > target_ratio:
            # 幅の方が比率的に大きい場合
            new_width = int(height * target_ratio)  # 新しい幅を計算
            left = (width - new_width) // 2  # 左端の座標
            right = left + new_width  # 右端の座標
            top, bottom = 0, height  # 上端と下端はそのまま
        else:
            # 高さの方が比率的に大きい場合
            new_height = int(width / target_ratio)  # 新しい高さを計算
            top = (height - new_height) // 2  # 上端の座標
            bottom = top + new_height  # 下端の座標
            left, right = 0, width  # 左端と右端はそのまま
    elif crop_type == "4:3":
        # 4:3 比率でクロップ
        target_ratio = 4 / 3  # 4:3 の比率
        if width / height > target_ratio:
            # 幅の方が比率的に大きい場合
            new_width = int(height * target_ratio)  # 新しい幅を計算
            left = (width - new_width) // 2  # 左端の座標
            right = left + new_width  # 右端の座標
            top, bottom = 0, height  # 上端と下端はそのまま
        else:
            # 高さの方が比率的に大きい場合
            new_height = int(width / target_ratio)  # 新しい高さを計算
            top = (height - new_height) // 2  # 上端の座標
            bottom = top + new_height  # 下端の座標
            left, right = 0, width  # 左端と右端はそのまま
    else:
        # クロップタイプが不正な場合はそのまま返す
        return img

    # 指定された範囲で画像をクロップ
    return img.crop((left, top, right, bottom))


# 画像を処理する関数
def process_image(
    input_path,
    output_folder,
    target_size,
    operation,
    size_type,
    crop_type,
    aspect_ratio=None,
    quality=85,
    progress_callback=None,
):
    # 画像を開く
    with Image.open(input_path) as img:
        # 元の画像のサイズを取得
        original_size = os.path.getsize(input_path) / (1024 * 1024)  # MB単位に変換
        original_width, original_height = img.size  # 幅と高さ

        # ファイル名と拡張子を取得
        base_name = os.path.basename(input_path)  # ファイル名
        name, ext = os.path.splitext(base_name)  # ファイル名と拡張子

        # GIFファイルはスキップ
        if ext.lower() == ".gif":
            if progress_callback:
                progress_callback(1.0)  # プログレスバーを100%にする
            return None, 1.0, "GIFファイルはスキップされました"

        # クロップ処理を適用
        img = crop_image(img, crop_type, aspect_ratio)  # 画像をクロップ
        cropped_width, cropped_height = img.size  # クロップ後の幅と高さ

        # クロップが適用された場合、ファイル名に"_cropped_クロップタイプ"を追加
        if crop_type != "none":
            if crop_type == "custom" and aspect_ratio is not None:
                # カスタム比率の場合、入力値をファイル名に反映
                aspect_width = (
                    int(aspect_ratio[0])
                    if aspect_ratio[0].is_integer()
                    else aspect_ratio[0]
                )
                aspect_height = (
                    int(aspect_ratio[1])
                    if aspect_ratio[1].is_integer()
                    else aspect_ratio[1]
                )
                crop_type_safe = f"{aspect_width}×{aspect_height}"
            else:
                # クロップタイプが16:9などの場合、ファイル名にバグが発生しないように変換
                crop_type_safe = crop_type.replace(":", "×")
            name += f"_{crop_type_safe}"

        # サイズ変更なしの場合
        if size_type == "none":
            # クロップ後の画像を保存
            output_path = os.path.join(output_folder, f"{name}{ext}")
            img.save(output_path, quality=quality, optimize=True)
            if progress_callback:
                progress_callback(1.0)  # プログレスバーを100%にする
            return output_path, 1.0, None  # 出力パス、サイズ比率、メッセージ

        # サイズ変更ありの場合
        if size_type == "mb":
            # 目標サイズをMB単位で取得
            target_size_mb = float(target_size)
            # 自動調整モードの場合
            if operation == "auto":
                # 元のサイズが目標サイズより大きければ圧縮、小さければ拡大
                operation = "compress" if original_size > target_size_mb else "upscale"
            # サイズ比率を計算
            size_ratio = (target_size_mb / original_size) ** 0.5
        else:  # size_type == "width" or "height"
            # 目標サイズをピクセル単位で取得
            target_size = int(target_size)
            # 幅で指定した場合
            if size_type == "width":
                target_dimension = cropped_width  # 目標寸法は幅
            else:  # size_type == "height"
                target_dimension = cropped_height  # 目標寸法は高さ

            # 自動調整モードの場合
            if operation == "auto":
                # 目標寸法が元の寸法より大きければ拡大、小さければ圧縮
                operation = "compress" if target_dimension > target_size else "upscale"
            # サイズ比率を計算
            size_ratio = target_size / target_dimension

        # 一時ファイルを作成
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_path = temp_file.name  # 一時ファイルのパス

        try:
            # イテレーション回数
            iteration = 0
            max_iterations = 20  # 最大イテレーション回数
            # 目標サイズに到達するまでループ
            while iteration < max_iterations:
                # 新しい幅と高さを計算
                new_width = int(cropped_width * size_ratio)
                new_height = int(cropped_height * size_ratio)

                # 画像をリサイズ
                resized_img = img.resize((new_width, new_height), Image.LANCZOS)

                # リサイズ後のサイズ比率を計算
                current_ratio = int(
                    (new_width * new_height) / (cropped_width * cropped_height) * 100
                )

                # 画像を一時ファイルに保存
                if ext.lower() in [".jpg", ".jpeg"]:
                    resized_img.save(temp_path, quality=quality, optimize=True)
                else:
                    resized_img.save(temp_path, optimize=True)

                # リサイズ後のファイルサイズを取得
                new_size = os.path.getsize(temp_path) / (1024 * 1024)

                # プログレスバーを更新
                if progress_callback:
                    progress_callback((iteration + 1) / max_iterations)

                # 目標サイズに到達したかどうか判定
                condition = False
                if size_type == "mb":
                    # MBで指定した場合
                    condition = (
                        operation == "compress" and new_size <= target_size_mb
                    ) or (operation == "upscale" and new_size >= target_size_mb)
                elif size_type == "width":
                    # 幅で指定した場合
                    condition = (
                        operation == "compress" and new_width <= target_size
                    ) or (operation == "upscale" and new_width >= target_size)
                else:  # size_type == "height"
                    # 高さで指定した場合
                    condition = (
                        operation == "compress" and new_height <= target_size
                    ) or (operation == "upscale" and new_height >= target_size)

                # 目標サイズに到達した場合
                if condition:
                    # 処理結果を記録
                    operation_name = "compressed" if operation == "comp" else "upscale"
                    output_path = os.path.join(
                        output_folder,
                        f"{name}_{current_ratio}%{ext}",
                    )
                    shutil.copy2(temp_path, output_path)
                    if progress_callback:
                        progress_callback(1.0)  # プログレスバーを100%にする
                    return (
                        output_path,
                        size_ratio,
                        None,
                    )  # 出力パス、サイズ比率、メッセージ

                # 目標サイズに到達していない場合、サイズ比率と品質を調整
                if operation == "compress":
                    # 圧縮の場合、サイズ比率を小さくし、品質を下げる
                    size_ratio *= 0.9
                    quality = max(quality - 5, 10)  # 品質は10以下にならないようにする
                else:  # upscale
                    # 拡大の場合、サイズ比率を大きくし、品質を上げる
                    size_ratio *= 1.1
                    quality = min(quality + 5, 95)  # 品質は95以上にならないようにする

                # イテレーション回数を増やす
                iteration += 1

            # 最大イテレーション回数に達しても目標サイズに到達できなかった場合
            if progress_callback:
                progress_callback(1.0)  # プログレスバーを100%にする
            return None, 0, "目標サイズに到達できませんでした"
        finally:
            # 一時ファイルを削除
            if os.path.exists(temp_path):
                os.remove(temp_path)


class ImageProcessorApp:
    # 画像処理アプリケーションのメインクラス
    def __init__(self, master):
        # 初期化処理
        self.master = master  # 親ウィンドウを保持
        master.title("ImageSizer")  # ウィンドウタイトルを設定
        master.geometry("600x800+100+100")  # ウィンドウサイズと位置を設定

        self.create_widgets()  # ウィジェットを作成
        self.setup_drop_target()  # ドロップターゲットを設定

    def create_widgets(self):
        # ウィジェット作成処理
        # ファイル選択部分
        file_frame = ttk.LabelFrame(self.master, text="ファイル選択", padding=(10, 5))
        # ファイル選択用のフレームを作成
        file_frame.pack(fill=tk.X, padx=10, pady=5)  # フレームを配置
        # ラベルとリストボックス、ボタンを作成
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
        # クロップ設定用のフレームを作成
        crop_frame.pack(fill=tk.X, padx=10, pady=5)  # フレームを配置
        # クロップ設定用のラジオボタンを作成
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

        # カスタム比率入力用のフレームを作成
        self.aspect_ratio_frame = ttk.Frame(crop_frame)
        self.aspect_ratio_frame.pack(pady=5)
        # カスタム比率入力用のラベルとエントリーを作成
        ttk.Label(self.aspect_ratio_frame, text="縦横比:").pack(side=tk.LEFT)
        self.aspect_width = ttk.Entry(self.aspect_ratio_frame, width=5)
        self.aspect_width.pack(side=tk.LEFT)
        ttk.Label(self.aspect_ratio_frame, text=":").pack(side=tk.LEFT)
        self.aspect_height = ttk.Entry(self.aspect_ratio_frame, width=5)
        self.aspect_height.pack(side=tk.LEFT)
        # カスタム比率入力フレームを非表示にする
        self.aspect_ratio_frame.pack_forget()

        # サイズ変更設定部分
        size_frame = ttk.LabelFrame(self.master, text="目標サイズ設定", padding=(10, 5))
        # サイズ変更設定用のフレームを作成
        size_frame.pack(fill=tk.X, padx=10, pady=5)  # フレームを配置
        # サイズ変更設定用のラジオボタンを作成
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

        # サイズ入力用のフレームを作成
        self.size_input_frame = ttk.Frame(size_frame)
        self.size_input_frame.pack(pady=5)
        # サイズ入力用のラベルとエントリーを作成
        self.size_label = ttk.Label(self.size_input_frame, text="目標サイズ (MB):")
        self.size_label.pack(side=tk.LEFT)
        self.size_entry = ttk.Entry(self.size_input_frame, width=10)
        self.size_entry.insert(0, "2")
        self.size_entry.pack(side=tk.LEFT, padx=5)

        # 拡大・縮小モードの選択部分
        operation_frame = ttk.LabelFrame(
            self.master, text="拡大・縮小モードの選択", padding=(10, 5)
        )
        # 拡大・縮小モード選択用のフレームを作成
        operation_frame.pack(fill=tk.X, padx=10, pady=5)  # フレームを配置
        # 拡大・縮小モード選択用のラジオボタンを作成
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

        # プログレスバーとログ出力
        self.progress = ttk.Progressbar(
            self.master, orient="horizontal", length=400, mode="determinate"
        )
        # プログレスバーを作成
        self.progress.pack(pady=10)  # プログレスバーを配置
        # ログ出力用のテキストエリアを作成
        self.output_text = tk.Text(self.master, height=15, width=70)
        self.output_text.pack(pady=10)
        # ログ出力用のテキストエリアに緑色のタグを設定
        self.output_text.tag_configure("green", foreground="green")

    def setup_drop_target(self):
        # ドロップターゲット設定処理
        self.master.drop_target_register(DND_FILES)  # ファイルドロップを登録
        self.master.dnd_bind("<<Drop>>", self.drop)  # ドロップイベントにバインド

    def drop(self, event):
        # ドロップイベント処理
        files = self.master.tk.splitlist(event.data)  # ドロップされたファイルを取得
        self.add_files(files)  # ファイルをリストに追加
        self.process_images()  # 画像処理を開始

    def add_files(self, files):
        # ファイル追加処理
        for file in files:
            if file not in self.file_listbox.get(0, tk.END):
                # リストに存在しないファイルのみ追加
                self.file_listbox.insert(tk.END, file)

    def browse_files(self):
        # ファイル選択ダイアログ表示処理
        files = filedialog.askopenfilenames(
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff")]
        )
        # 選択されたファイルを追加
        self.add_files(files)

    def on_crop_change(self):
        # クロップ設定変更処理
        if self.crop_var.get() == "custom":
            # カスタム比率の場合、入力フレームを表示
            self.aspect_ratio_frame.pack()
        else:
            # カスタム比率以外の場合、入力フレームを非表示
            self.aspect_ratio_frame.pack_forget()

    def on_size_type_change(self):
        # サイズ変更設定変更処理
        size_type = self.size_type_var.get()
        if size_type == "none":
            # 変更なしの場合、サイズ入力フレームを非表示
            self.size_input_frame.pack_forget()
        else:
            # 変更ありの場合、サイズ入力フレームを表示
            self.size_input_frame.pack()
            if size_type == "mb":
                # MBで指定の場合、ラベルとエントリーを初期化
                self.size_label.config(text="目標サイズ (MB):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, "2")
            elif size_type == "width":
                # 横ピクセルで指定の場合、ラベルとエントリーを初期化
                self.size_label.config(text="目標サイズ (横px):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, "1920")
            else:  # height
                # 縦ピクセルで指定の場合、ラベルとエントリーを初期化
                self.size_label.config(text="目標サイズ (縦px):")
                self.size_entry.delete(0, tk.END)
                self.size_entry.insert(0, "1080")

    def process_images(self):
        # 画像処理処理
        files = list(self.file_listbox.get(0, tk.END))
        # リストボックスからファイルを取得
        if not files:
            # ファイルが選択されていない場合、警告を表示
            messagebox.showwarning("警告", "処理する画像ファイルが選択されていません。")
            return

        size_type = self.size_type_var.get()
        # サイズ変更設定を取得
        if size_type != "none":
            # サイズ変更設定が変更なし以外の場合、目標サイズを取得
            try:
                target_size = float(self.size_entry.get())
            except ValueError:
                # 目標サイズが数値でない場合、エラーを表示
                messagebox.showerror("エラー", "目標サイズには数値を入力してください。")
                return
        else:
            # サイズ変更設定が変更なしの場合、目標サイズをNoneにする
            target_size = None

        operation = self.operation_var.get()
        # 拡大・縮小モードを取得
        crop_type = self.crop_var.get()
        # クロップ設定を取得

        aspect_ratio = None
        # カスタム比率を取得
        if crop_type == "custom":
            try:
                aspect_width = float(self.aspect_width.get())
                aspect_height = float(self.aspect_height.get())
                aspect_ratio = (aspect_width, aspect_height)
            except ValueError:
                # カスタム比率が数値でない場合、エラーを表示
                messagebox.showerror("エラー", "縦横比には数値を入力してください。")
                return

        # ログ出力エリアをクリア
        self.output_text.delete(1.0, tk.END)
        # プログレスバーの最大値を設定
        self.progress["maximum"] = len(files) * 100
        # プログレスバーの初期値を設定
        self.progress["value"] = 0

        # プログレスバー更新用の関数
        def update_progress(file_progress):
            self.progress["value"] += file_progress
            self.master.update_idletasks()

        # 画像処理を行うスレッド関数
        def process_images_thread():
            for i, file in enumerate(files):
                try:
                    # ファイルの出力フォルダを取得
                    output_folder = os.path.dirname(file)
                    # 画像処理を実行
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
                    )
                    # 処理結果に応じてログ出力
                    if message:
                        self.output_text.insert(tk.END, f"{file}: {message}\n", "green")
                    elif output_path:
                        # 処理成功の場合、ファイルサイズと解像度をログ出力
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
                        # 処理失敗の場合、ログ出力
                        self.output_text.insert(tk.END, f"処理失敗: {file}\n")
                    self.output_text.see(tk.END)
                except Exception as e:
                    # エラーが発生した場合、ログ出力
                    self.output_text.insert(tk.END, f"エラー ({file}): {str(e)}\n")

                # プログレスバーの値を更新
                self.progress["value"] = (i + 1) * 100

                # 処理が終わったファイルをリストから削除
                self.master.after(0, lambda: self.file_listbox.delete(0))

            # プログレスバーを100%にする
            self.progress["value"] = self.progress["maximum"]
            self.master.update_idletasks()

        # 画像処理スレッドを開始
        threading.Thread(target=process_images_thread, daemon=True).start()


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = ImageProcessorApp(root)
    root.mainloop()
