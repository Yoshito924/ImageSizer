from PIL import Image
import os
import tempfile
import shutil


def crop_image(img, crop_type, aspect_ratio=None):
    """画像をクロップする関数"""
    width, height = img.size
    if crop_type == "square":
        size = min(width, height)
        left = (width - size) // 2
        top = (height - size) // 2
        right = left + size
        bottom = top + size
    elif crop_type == "custom":
        if aspect_ratio is None:
            return img
        target_ratio = aspect_ratio[0] / aspect_ratio[1]
        if width / height > target_ratio:
            new_width = int(height * target_ratio)
            left = (width - new_width) // 2
            right = left + new_width
            top, bottom = 0, height
        else:
            new_height = int(width / target_ratio)
            top = (height - new_height) // 2
            bottom = top + new_height
            left, right = 0, width
    elif crop_type == "16:9":
        target_ratio = 16 / 9
        if width / height > target_ratio:
            new_width = int(height * target_ratio)
            left = (width - new_width) // 2
            right = left + new_width
            top, bottom = 0, height
        else:
            new_height = int(width / target_ratio)
            top = (height - new_height) // 2
            bottom = top + new_height
            left, right = 0, width
    elif crop_type == "4:3":
        target_ratio = 4 / 3
        if width / height > target_ratio:
            new_width = int(height * target_ratio)
            left = (width - new_width) // 2
            right = left + new_width
            top, bottom = 0, height
        else:
            new_height = int(width / target_ratio)
            top = (height - new_height) // 2
            bottom = top + new_height
            left, right = 0, width
    else:
        return img

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
):
    """画像を処理する関数"""
    with Image.open(input_path) as img:
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

        if crop_type != "none":
            if crop_type == "custom" and aspect_ratio is not None:
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
                crop_type_safe = crop_type.replace(":", "×")
            name += f"_{crop_type_safe}"

        if size_type == "none":
            output_path = os.path.join(output_folder, f"{name}{ext}")
            if output_format == 'webp':
                img.save(output_path, 'WEBP', quality=quality)
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
            max_iterations = 20
            while iteration < max_iterations:
                new_width = int(cropped_width * size_ratio)
                new_height = int(cropped_height * size_ratio)

                resized_img = img.resize((new_width, new_height), Image.LANCZOS)

                current_ratio = int(
                    (new_width * new_height) / (cropped_width * cropped_height) * 100
                )

                if output_format == 'webp':
                    resized_img.save(temp_path, 'WEBP', quality=quality)
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

                if condition:
                    operation_name = "compressed" if operation == "comp" else "upscale"
                    output_path = os.path.join(
                        output_folder,
                        f"{name}_{current_ratio}%{ext}",
                    )
                    shutil.copy2(temp_path, output_path)
                    if progress_callback:
                        progress_callback(1.0)
                    return output_path, size_ratio, None

                if operation == "compress":
                    size_ratio *= 0.9
                    quality = max(quality - 5, 10)
                else:
                    size_ratio *= 1.1
                    quality = min(quality + 5, 95)

                iteration += 1

            if progress_callback:
                progress_callback(1.0)
            return None, 0, "目標サイズに到達できませんでした"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
