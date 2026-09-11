"""文書を一時PNGへ描画し、ImageSizerの画像処理につなぐ。"""
from contextlib import contextmanager
import math
from pathlib import Path
import shutil
import tempfile

from image_processor import crop_image, process_image
from PIL import Image

DOCUMENT_EXTENSIONS = {".pptx", ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".xlsm"}


def is_document(path):
    return Path(path).suffix.lower() in DOCUMENT_EXTENSIONS


def render_dimensions(width, height, target_size, size_type, crop_type, aspect_ratio):
    """クロップ後の指定寸法を満たす解像度で、文書から直接描画する。"""
    scale = 1920 / width
    if size_type in {"width", "height", "long_edge"}:
        with Image.new("L", (max(1, round(width)), max(1, round(height)))) as probe:
            with crop_image(probe, crop_type, aspect_ratio) as cropped:
                cw, ch = cropped.size
        basis = {"width": cw, "height": ch, "long_edge": max(cw, ch)}[size_type]
        scale = float(target_size) / max(1, basis)
    return max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale))


@contextmanager
def _office_document(path, pdf_path):
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("Office文書の変換にはWindowsとpywin32が必要です。") from exc
    pythoncom.CoInitialize()
    app = doc = None
    suffix = path.suffix.lower()
    try:
        # ユーザーが開いているOfficeを終了させないよう専用インスタンスを使用。
        if suffix == ".pptx":
            app = win32com.client.DispatchEx("PowerPoint.Application")
            app.AutomationSecurity = 3
            doc = app.Presentations.Open(str(path), ReadOnly=True, WithWindow=False)
        elif suffix in {".doc", ".docx"}:
            app = win32com.client.DispatchEx("Word.Application")
            app.AutomationSecurity = 3
            app.DisplayAlerts = 0
            doc = app.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False)
            doc.ExportAsFixedFormat(str(pdf_path), 17)
        else:
            app = win32com.client.DispatchEx("Excel.Application")
            app.AutomationSecurity = 3
            app.DisplayAlerts = False
            doc = app.Workbooks.Open(str(path), UpdateLinks=0, ReadOnly=True)
            doc.ExportAsFixedFormat(0, str(pdf_path))
        yield doc
    except Exception as exc:
        raise RuntimeError(
            f"Office文書の変換に失敗しました。対応するOfficeアプリとファイルを確認してください。\n{exc}"
        ) from exc
    finally:
        if doc is not None:
            try:
                doc.Close() if suffix == ".pptx" else doc.Close(False)
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        doc = app = None
        pythoncom.CoUninitialize()


def _pdf_pages(path, temp_dir, dimensions, cancelled):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDFの変換にはPyMuPDFが必要です。pip install -r requirements.txt を実行してください。") from exc
    with fitz.open(str(path)) as doc:
        if doc.needs_pass:
            raise ValueError("パスワードで保護されたPDFは処理できません。")
        total = len(doc)
        for index, page in enumerate(doc, 1):
            if cancelled():
                return
            width, height = dimensions(page.rect.width, page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(width / page.rect.width, height / page.rect.height), alpha=False)
            rendered = temp_dir / f"page_{index:03d}.png"
            pix.save(str(rendered))
            del pix
            yield rendered, index, total
            rendered.unlink(missing_ok=True)


def process_document(input_path, output_folder, target_size, operation, size_type,
                     crop_type, aspect_ratio=None, *, output_format=None,
                     filename_pattern=None, preset_name=None, progress_callback=None,
                     page_callback=None, cancelled=lambda: False):
    """一時画像を1ページずつ処理。既存出力は上書きせず、完了件数を返す。"""
    source = Path(input_path).resolve()
    destination = Path(output_folder).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if not is_document(source):
        raise ValueError(f"未対応の文書形式: {source.suffix}")
    if not source.is_file():
        raise FileNotFoundError(source)

    def dimensions(w, h):
        return render_dimensions(w, h, target_size, size_type, crop_type, aspect_ratio)

    count = 0
    with tempfile.TemporaryDirectory(prefix="imagesizer_document_") as temp:
        temp_dir = Path(temp)
        staging = temp_dir / "processed"
        staging.mkdir()

        def consume(pages):
            nonlocal count
            for rendered, index, total in pages:
                if cancelled():
                    break
                named = temp_dir / f"{source.stem}_{index:03d}.png"
                rendered.replace(named)

                def progress(value):
                    if progress_callback:
                        progress_callback((index - 1 + value) / total)

                result, _, note = process_image(
                    str(named), str(staging), target_size, operation, size_type,
                    crop_type, aspect_ratio, output_format=output_format or "png",
                    filename_pattern=filename_pattern, preset_name=preset_name,
                    progress_callback=progress,
                )
                if result is None:
                    raise RuntimeError(note or f"ページ {index} の画像処理に失敗しました。")
                processed = Path(result)
                candidate = destination / processed.name
                serial = 2
                while True:
                    try:
                        # 排他的作成で、同名文書や過去の出力との衝突を回避。
                        with candidate.open("xb") as output:
                            try:
                                with processed.open("rb") as data:
                                    shutil.copyfileobj(data, output)
                            except BaseException:
                                output.close()
                                candidate.unlink(missing_ok=True)
                                raise
                        break
                    except FileExistsError:
                        candidate = destination / f"{processed.stem}_{serial}{processed.suffix}"
                        serial += 1
                count += 1
                if page_callback:
                    page_callback(str(candidate), index, total, note)
                named.unlink(missing_ok=True)
                processed.unlink(missing_ok=True)

        if source.suffix.lower() == ".pdf":
            consume(_pdf_pages(source, temp_dir, dimensions, cancelled))
        else:
            pdf_path = temp_dir / "converted.pdf"
            with _office_document(source, pdf_path) as doc:
                if source.suffix.lower() == ".pptx":
                    def slides():
                        total = doc.Slides.Count
                        width, height = dimensions(doc.PageSetup.SlideWidth, doc.PageSetup.SlideHeight)
                        for index in range(1, total + 1):
                            if cancelled():
                                return
                            rendered = temp_dir / f"page_{index:03d}.png"
                            doc.Slides(index).Export(str(rendered), "PNG", width, height)
                            yield rendered, index, total
                    consume(slides())
                else:
                    consume(_pdf_pages(pdf_path, temp_dir, dimensions, cancelled))
    return count
