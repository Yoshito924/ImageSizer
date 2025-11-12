from PIL import Image, ImageOps
import os
import tempfile
import shutil


def crop_image(img, crop_type, aspect_ratio=None):
    """画像をクロップする関数"""
    width, height = img.size
    
    # アスペクト比の定義（高精度）
    aspect_ratios = {
        "square": (1, 1),
        "16:9": (16, 9),
        "4:3": (4, 3),
        "9:16": (9, 16),
        "1:√2": (1, 2 ** 0.5),  # 1:1.41421356...
        "√2:1": (2 ** 0.5, 1)   # 1.41421356:1
    }
    
    if crop_type == "custom":
        if aspect_ratio is None:
            return img
        target_ratio = aspect_ratio[0] / aspect_ratio[1]
    elif crop_type in aspect_ratios:
        ratio = aspect_ratios[crop_type]
        target_ratio = ratio[0] / ratio[1]
    else:
        return img
    
    # クロップ領域の計算（浮動小数点で計算し、最後に整数化）
    if crop_type == "square":
        size = min(width, height)
        left = (width - size) // 2
        top = (height - size) // 2
        right = left + size
        bottom = top + size
    else:
        current_ratio = width / height
        
        if current_ratio > target_ratio:
            # 幅が広すぎる場合：高さを基準に幅を計算
            new_width = height * target_ratio
            left = (width - new_width) / 2
            right = width - left
            top, bottom = 0, height
        else:
            # 高さが高すぎる場合：幅を基準に高さを計算
            new_height = width / target_ratio
            top = (height - new_height) / 2
            bottom = height - top
            left, right = 0, width
        
        # 最後に整数に変換（roundを使用して精度を保つ）
        left = round(left)
        top = round(top)
        right = round(right)
        bottom = round(bottom)

    return img.crop((left, top, right, bottom))


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
    output_format=None,
    filename_pattern="default",
    preset_name=None
):
    """画像を処理する関数"""
    with Image.open(input_path) as img:
        # EXIFのOrientationタグを適用して画像を正しい向きに回転
        img = ImageOps.exif_transpose(img)
        
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        original_width, original_height = img.size

        base_name = os.path.basename(input_path)
        name, ext = os.path.splitext(base_name)

        # GIFファイルはスキップ
        if ext.lower() == ".gif":
            if progress_callback:
                progress_callback(1.0)
            return None, 1.0, "GIFファイルはスキップされました"

        # 出力フォーマットの設定
        if output_format:
            ext = f".{output_format.lower()}"

        # RGBAモードの画像をRGBに変換（WebP対応）
        if img.mode == 'RGBA' and output_format == 'webp':
            img = img.convert('RGB')

        img = crop_image(img, crop_type, aspect_ratio)
        cropped_width, cropped_height = img.size

        # 出力ファイル名のベース部分を生成
        output_filename = name

        # クロップタイプを追加（クロップが実際に行われた場合のみ）
        if filename_pattern.get("include_crop_type", False) and crop_type != "none":
            if crop_type == "custom" and aspect_ratio is not None:
                aspect_width = (
                    int(aspect_ratio[0])
                    if isinstance(aspect_ratio[0], float) and aspect_ratio[0].is_integer()
                    else aspect_ratio[0]
                )
                aspect_height = (
                    int(aspect_ratio[1])
                    if isinstance(aspect_ratio[1], float) and aspect_ratio[1].is_integer()
                    else aspect_ratio[1]
                )
                crop_type_safe = f"{aspect_width}×{aspect_height}"
            else:
                crop_type_safe = crop_type.replace(":", "×")
            if cropped_width != original_width or cropped_height != original_height:
                output_filename += f"_{crop_type_safe}"

        # プリセット名を追加
        if filename_pattern.get("include_preset_name", False) and preset_name:
            # プリセット名から不要な文字を削除
            preset_safe = preset_name.replace(":", "")
            preset_safe = preset_safe.replace(" ", "_")
            preset_safe = preset_safe.replace("/", "_")
            preset_safe = preset_safe.replace("\\", "_")
            output_filename += f"_{preset_safe}"
        
        # タイムスタンプを追加
        if filename_pattern.get("include_timestamp", False):
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename += f"_{timestamp}"

        # 連番を追加
        if filename_pattern.get("include_sequential", False):
            counter = 1
            while os.path.exists(os.path.join(output_folder, f"{output_filename}_{counter:03d}{ext}")):
                counter += 1
            output_filename += f"_{counter:03d}"

        if size_type == "none":
            output_path = os.path.join(output_folder, f"{output_filename}{ext}")
            if output_format == 'webp':
                img.save(output_path, 'WEBP', quality=quality)
            elif output_format == 'png':
                img.save(output_path, 'PNG', optimize=True)
            else:
                img.save(output_path, quality=quality, optimize=True)
            if progress_callback:
                progress_callback(1.0)
            return output_path, 1.0, None

        if size_type == "mb":
            target_size_mb = float(target_size)
            if operation == "auto":
                operation = "compress" if original_size > target_size_mb else "upscale"
            size_ratio = (target_size_mb / original_size) ** 0.5
        elif size_type == "kb":
            target_size_kb = float(target_size)
            target_size_mb = target_size_kb / 1024.0  # KBをMBに変換
            if operation == "auto":
                operation = "compress" if original_size > target_size_mb else "upscale"
            size_ratio = (target_size_mb / original_size) ** 0.5
        else:
            target_size = int(target_size)
            if size_type == "width":
                target_dimension = cropped_width
            else:
                target_dimension = cropped_height

            if operation == "auto":
                operation = "compress" if target_dimension > target_size else "upscale"
            size_ratio = target_size / target_dimension

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_path = temp_file.name

        try:
            iteration = 0
            max_iterations = 10  # 最大反復回数を減らして高速化
            last_valid_path = None
            while iteration < max_iterations:
                # 精度を保つためroundを使用
                new_width = round(cropped_width * size_ratio)
                new_height = round(cropped_height * size_ratio)

                # LANCZOSは非推奨なので、Resampling.LANCZOSを使用
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                current_ratio = int(
                    (new_width * new_height) / (cropped_width * cropped_height) * 100
                )

                if output_format == 'webp':
                    resized_img.save(temp_path, 'WEBP', quality=quality)
                elif output_format == 'png':
                    resized_img.save(temp_path, 'PNG', optimize=True)
                else:
                    if ext.lower() in [".jpg", ".jpeg"]:
                        resized_img.save(temp_path, quality=quality, optimize=True)
                    else:
                        resized_img.save(temp_path, optimize=True)

                new_size = os.path.getsize(temp_path) / (1024 * 1024)

                if progress_callback:
                    progress_callback((iteration + 1) / max_iterations)

                condition = False
                if size_type == "mb":
                    condition = (
                        operation == "compress" and new_size <= target_size_mb
                    ) or (operation == "upscale" and new_size >= target_size_mb)
                elif size_type == "width":
                    condition = (
                        operation == "compress" and new_width <= target_size
                    ) or (operation == "upscale" and new_width >= target_size)
                else:
                    condition = (
                        operation == "compress" and new_height <= target_size
                    ) or (operation == "upscale" and new_height >= target_size)

                # 有効なファイルを保存
                last_valid_path = temp_path
                
                if condition:
                    # サイズ比率を追加（サイズが実際に変更された場合のみ）
                    if filename_pattern.get("include_size_ratio", False) and size_type != "none":
                        current_ratio = int(
                            (new_width * new_height) / (original_width * original_height) * 100
                        )
                        if current_ratio != 100:  # サイズが変更された場合のみ
                            output_filename += f"_{current_ratio}%"

                    output_path = os.path.join(output_folder, f"{output_filename}{ext}")
                    shutil.copy2(temp_path, output_path)
                    if progress_callback:
                        progress_callback(1.0)
                    return output_path, size_ratio, None

                if operation == "compress":
                    size_ratio *= 0.85  # より大きなステップで調整
                    quality = max(quality - 10, 10)
                else:
                    size_ratio *= 1.15  # より大きなステップで調整
                    quality = min(quality + 10, 95)

                iteration += 1

            # 最後の有効なファイルを使用
            if last_valid_path and os.path.exists(last_valid_path):
                output_path = os.path.join(output_folder, f"{output_filename}{ext}")
                shutil.copy2(last_valid_path, output_path)
                if progress_callback:
                    progress_callback(1.0)
                return output_path, size_ratio, "近似値で保存されました"
            
            if progress_callback:
                progress_callback(1.0)
            return None, 0, "目標サイズに到達できませんでした"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
