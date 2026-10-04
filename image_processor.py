from datetime import datetime
from contextlib import contextmanager
from io import BytesIO

from PIL import Image, ImageOps
import os
import tempfile
import shutil

try:
    from resvg_py import svg_to_bytes
except ImportError:
    svg_to_bytes = None

WEBP_MAX_DIMENSION = 16383


@contextmanager
def open_supported_image(input_path, target_size=None, size_type=None):
    """Pillow対応画像に加え、SVGをラスタライズして開く。"""
    if os.path.splitext(input_path)[1].lower() != ".svg":
        with Image.open(input_path) as img:
            yield img
        return

    if svg_to_bytes is None:
        raise RuntimeError(
            "SVGの処理にはresvg-pyが必要です。"
            " `pip install -r requirements.txt` を実行してください。"
        )

    render_options = {
        "svg_path": os.fspath(input_path),
        "resources_dir": os.path.dirname(os.path.abspath(input_path)),
    }
    png_data = svg_to_bytes(**render_options)

    # SVGを小さな固有サイズでラスタライズしてから拡大すると
    # 輪郭が荒れる。クロップの余裕も見込み、目標辺の最大4倍で先に描画する。
    if size_type in {"width", "height", "long_edge"} and target_size is not None:
        with BytesIO(png_data) as initial_buffer, Image.open(initial_buffer) as initial:
            width, height = initial.size

        requested_size = max(1, int(float(target_size)))
        target_render_size = min(requested_size * 4, max(requested_size, 8192))
        if size_type == "width":
            basis = width
        elif size_type == "height":
            basis = height
        else:
            basis = max(width, height)

        if basis < target_render_size:
            render_options["zoom"] = target_render_size / basis
            png_data = svg_to_bytes(**render_options)

    with BytesIO(png_data) as buffer, Image.open(buffer) as img:
        img.load()
        yield img

# HEIC形式のサポートを追加
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    # pillow-heifがインストールされていない場合は警告を出すが、処理は続行
    pass


@contextmanager
def _safe_output_path(input_path, output_path):
    """既存ファイルを上書きしない出力先を予約し、保存失敗時は片付ける。"""
    if os.path.abspath(output_path) == os.path.abspath(input_path):
        name, ext = os.path.splitext(output_path)
        output_path = f"{name}_processed{ext}"
    name, ext = os.path.splitext(output_path)
    counter = 1
    while True:
        try:
            # 同時処理でも同じ出力先を選ばないよう、排他的に作成する。
            with open(output_path, "xb"):
                pass
            break
        except (FileExistsError, PermissionError) as exc:
            # Windowsでは同名ディレクトリとの衝突もPermissionErrorになる。
            if isinstance(exc, PermissionError) and not os.path.lexists(output_path):
                raise
            output_path = f"{name}_{counter:03d}{ext}"
            counter += 1
    try:
        yield output_path
    except BaseException:
        try:
            os.remove(output_path)
        except FileNotFoundError:
            pass
        raise


def _merge_messages(*messages):
    """空でないメッセージだけを結合する"""
    filtered = [message for message in messages if message]
    return " / ".join(filtered) if filtered else None


def _limit_target_size_for_webp(target_size, size_type):
    """WebPの最大寸法を超える目標値を安全な範囲に丸める"""
    if size_type not in {"width", "height", "long_edge"}:
        return target_size, None
    if target_size <= WEBP_MAX_DIMENSION:
        return target_size, None

    label_map = {
        "width": "横幅",
        "height": "高さ",
        "long_edge": "長辺",
    }
    return (
        WEBP_MAX_DIMENSION,
        f"WebPの上限に合わせて{label_map[size_type]}を{WEBP_MAX_DIMENSION}pxに制限しました",
    )


def _limit_image_for_webp(img):
    """WebPの最大寸法を超える場合は、縦横比を保って縮小する"""
    width, height = img.size
    if width <= WEBP_MAX_DIMENSION and height <= WEBP_MAX_DIMENSION:
        return img, None

    scale = min(WEBP_MAX_DIMENSION / width, WEBP_MAX_DIMENSION / height)
    new_width = max(1, min(WEBP_MAX_DIMENSION, int(width * scale)))
    new_height = max(1, min(WEBP_MAX_DIMENSION, int(height * scale)))
    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return (
        resized_img,
        (
            f"WebPの上限に合わせて {width}x{height}px から "
            f"{new_width}x{new_height}px に縮小しました"
        ),
    )


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


def would_overwrite_input(
    input_path,
    output_folder,
    output_format=None,
    filename_pattern=None,
    preset_name=None,
):
    """出力が入力ファイルと同じパスになる可能性を保守的に判定する。

    実行前にGUIから呼び、同名出力の恐れがあれば警告を出すためのヘルパー。
    crop_type や size_ratio による改名は実行時に確定するため、
    タイムスタンプ・連番・（選択された）プリセット名が付かない限りリスクありと見なす。
    """
    filename_pattern = filename_pattern or {}

    if os.path.abspath(output_folder) != os.path.abspath(os.path.dirname(input_path)):
        return False

    _, ext = os.path.splitext(os.path.basename(input_path))
    if not output_format and ext.lower() == ".svg":
        out_ext = ".png"
    else:
        out_ext = f".{output_format.lower()}" if output_format else ext
    if out_ext.lower() != ext.lower():
        return False

    if filename_pattern.get("include_timestamp", False):
        return False
    if filename_pattern.get("include_sequential", False):
        return False
    if filename_pattern.get("include_preset_name", False) and preset_name:
        return False

    return True


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
    filename_pattern=None,
    preset_name=None,
    trace_callback=None,
):
    """画像を処理する関数"""
    if not isinstance(filename_pattern, dict):
        filename_pattern = {}

    def trace(message):
        if trace_callback:
            try:
                trace_callback(message)
            except Exception:
                pass

    trace(f"open: {input_path}")
    with open_supported_image(input_path, target_size, size_type) as img:
        notes = []
        webp_limit_note = None

        def add_note(note):
            if note and note not in notes:
                notes.append(note)

        def set_webp_limit_note(note):
            nonlocal webp_limit_note
            if note:
                webp_limit_note = note

        trace(f"opened mode={img.mode} size={img.size}")
        img = ImageOps.exif_transpose(img)
        trace("exif_transpose done")
        
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        original_width, original_height = img.size

        base_name = os.path.basename(input_path)
        name, ext = os.path.splitext(base_name)
        is_svg_input = ext.lower() == ".svg"

        # GIFファイルはスキップ
        if ext.lower() == ".gif":
            if progress_callback:
                progress_callback(1.0)
            return None, 1.0, "GIFファイルはスキップされました"

        # 出力フォーマットの設定
        if output_format:
            ext = f".{output_format.lower()}"
        elif ext.lower() == ".svg":
            ext = ".png"
            add_note("SVG入力はPNG形式で出力しました")
        is_webp_output = ext.lower() == ".webp"

        # 出力形式が対応していないモードは事前に変換する
        # （JPEGはRGBA/LA/P等を、PNGはCMYKをサポートしない）
        if ext.lower() in ['.jpg', '.jpeg']:
            if img.mode not in ('RGB', 'L', 'CMYK'):
                img = img.convert('RGB')
        elif ext.lower() in ['.png', '.webp'] and img.mode == 'CMYK':
            img = img.convert('RGB')

        trace(f"crop start: {crop_type}")
        img = crop_image(img, crop_type, aspect_ratio)
        cropped_width, cropped_height = img.size
        trace(f"crop done: {cropped_width}x{cropped_height}")

        # 入力容量ではなく、クロップ・向き補正後の出力形式で容量を測る。
        size_reference_ratio = 1.0
        if size_type in ("mb", "kb"):
            size_img = img
            if is_webp_output:
                size_img, _ = _limit_image_for_webp(img)
                size_reference_ratio = max(size_img.size) / max(img.size)
            try:
                with BytesIO() as size_buffer:
                    if is_webp_output:
                        size_img.save(size_buffer, "WEBP", quality=quality)
                    else:
                        size_img.save(
                            size_buffer, Image.registered_extensions()[ext.lower()],
                            quality=quality, optimize=True,
                        )
                    original_size = size_buffer.tell() / (1024 * 1024)
            finally:
                if size_img is not img:
                    size_img.close()
            trace(f"rasterized output size: {original_size:.6f}MB")

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
            with _safe_output_path(input_path, output_path) as output_path:
                if is_webp_output:
                    save_img, note = _limit_image_for_webp(img)
                    set_webp_limit_note(note)
                    save_img.save(output_path, 'WEBP', quality=quality)
                elif output_format == 'png':
                    img.save(output_path, 'PNG', optimize=True)
                else:
                    img.save(output_path, quality=quality, optimize=True)
            if progress_callback:
                progress_callback(1.0)
            return output_path, 1.0, _merge_messages(*notes, webp_limit_note)

        def _save_without_resize(note_text):
            """出力画像がすでに目標以下のときにリサイズなしで保存する"""
            save_path = os.path.join(output_folder, f"{output_filename}{ext}")
            with _safe_output_path(input_path, save_path) as save_path:
                trace(f"pass-through save to {save_path}")
                save_img = img
                webp_note = None
                if is_webp_output:
                    save_img, webp_note = _limit_image_for_webp(save_img)
                    set_webp_limit_note(webp_note)
                    save_img.save(save_path, 'WEBP', quality=quality)
                elif output_format == 'png':
                    save_img.save(save_path, 'PNG', optimize=True)
                elif ext.lower() in [".jpg", ".jpeg"]:
                    save_img.save(save_path, quality=quality, optimize=True)
                else:
                    save_img.save(save_path, optimize=True)
            if progress_callback:
                progress_callback(1.0)
            add_note(note_text)
            return save_path, 1.0, _merge_messages(*notes, webp_limit_note)

        if size_type == "mb":
            target_size_mb = float(target_size)
            if operation == "auto":
                if original_size <= target_size_mb:
                    return _save_without_resize(
                        f"出力画像のサイズ "
                        f"{original_size:.2f}MB が目標 {target_size_mb:.2f}MB 以下のためリサイズ不要"
                    )
                operation = "compress"
            size_ratio = size_reference_ratio * (target_size_mb / original_size) ** 0.5
        elif size_type == "kb":
            target_size_kb = float(target_size)
            target_size_mb = target_size_kb / 1024.0  # KBをMBに変換
            if operation == "auto":
                if original_size <= target_size_mb:
                    return _save_without_resize(
                        f"出力画像のサイズ "
                        f"{original_size * 1024:.0f}KB が目標 {target_size_kb:.0f}KB 以下のためリサイズ不要"
                    )
                operation = "compress"
            size_ratio = size_reference_ratio * (target_size_mb / original_size) ** 0.5
        else:
            target_size = int(target_size)
            if is_webp_output:
                target_size, note = _limit_target_size_for_webp(target_size, size_type)
                add_note(note)
            if size_type == "width":
                target_dimension = cropped_width
            elif size_type == "height":
                target_dimension = cropped_height
            elif size_type == "long_edge":
                # 長辺を基準にリサイズ（幅と高さの大きい方）
                target_dimension = max(cropped_width, cropped_height)
            else:
                target_dimension = cropped_width  # デフォルト

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
                trace(f"iter {iteration}: size_ratio={size_ratio:.3f} quality={quality}")
                new_width = max(1, round(cropped_width * size_ratio))
                new_height = max(1, round(cropped_height * size_ratio))

                trace(f"iter {iteration}: resize to {new_width}x{new_height}")
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                if is_webp_output:
                    resized_img, note = _limit_image_for_webp(resized_img)
                    new_width, new_height = resized_img.size
                    set_webp_limit_note(note)

                current_ratio = int(
                    (new_width * new_height) / (cropped_width * cropped_height) * 100
                )

                trace(f"iter {iteration}: save to temp {temp_path}")
                if is_webp_output:
                    resized_img.save(temp_path, 'WEBP', quality=quality)
                elif output_format == 'png':
                    resized_img.save(temp_path, 'PNG', optimize=True)
                else:
                    if ext.lower() in [".jpg", ".jpeg"]:
                        resized_img.save(temp_path, quality=quality, optimize=True)
                    else:
                        resized_img.save(temp_path, optimize=True)
                trace(f"iter {iteration}: save done")

                new_size = os.path.getsize(temp_path) / (1024 * 1024)

                if progress_callback:
                    progress_callback((iteration + 1) / max_iterations)

                condition = False
                if size_type in ("mb", "kb"):
                    condition = (
                        operation == "compress" and new_size <= target_size_mb
                    ) or (operation == "upscale" and new_size >= target_size_mb)
                elif size_type == "width":
                    condition = (
                        operation == "compress" and new_width <= target_size
                    ) or (operation == "upscale" and new_width >= target_size)
                elif size_type == "height":
                    condition = (
                        operation == "compress" and new_height <= target_size
                    ) or (operation == "upscale" and new_height >= target_size)
                elif size_type == "long_edge":
                    # 長辺（幅と高さの大きい方）で判定
                    new_long_edge = max(new_width, new_height)
                    condition = (
                        operation == "compress" and new_long_edge <= target_size
                    ) or (operation == "upscale" and new_long_edge >= target_size)

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
                    with _safe_output_path(input_path, output_path) as output_path:
                        trace(f"copy to {output_path}")
                        shutil.copy2(temp_path, output_path)
                    trace("copy done")
                    if progress_callback:
                        progress_callback(1.0)
                    return output_path, size_ratio, _merge_messages(*notes, webp_limit_note)

                if operation == "compress":
                    if size_type in ("mb", "kb"):
                        # 縮小で圧縮率が変わる場合も、実際の出力容量で再調整する。
                        size_ratio *= min(0.85, (target_size_mb / new_size) ** 0.5)
                    else:
                        size_ratio *= 0.85  # より大きなステップで調整
                    quality = max(quality - 10, 10)
                else:
                    size_ratio *= 1.15  # より大きなステップで調整
                    quality = min(quality + 10, 95)

                iteration += 1

            # 容量上限を満たせない場合は、上限超過の出力を保存しない。
            if size_type in ("mb", "kb") and operation == "compress":
                if progress_callback:
                    progress_callback(1.0)
                return None, 0, _merge_messages(*notes, webp_limit_note, "指定容量以下にできませんでした。目標サイズを大きくしてください")

            # 最後の有効なファイルを使用
            if last_valid_path and os.path.exists(last_valid_path):
                output_path = os.path.join(output_folder, f"{output_filename}{ext}")
                with _safe_output_path(input_path, output_path) as output_path:
                    shutil.copy2(last_valid_path, output_path)
                if progress_callback:
                    progress_callback(1.0)
                return output_path, size_ratio, _merge_messages(*notes, webp_limit_note, "近似値で保存されました")
            
            if progress_callback:
                progress_callback(1.0)
            return None, 0, _merge_messages(*notes, webp_limit_note, "目標サイズに到達できませんでした")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
