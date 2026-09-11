import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
from PIL import Image

from document_processor import _office_document, process_document


class DocumentProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "日本語 資料.pdf"
        with fitz.open() as doc:
            for width, height in [(720, 405), (405, 720)]:
                page = doc.new_page(width=width, height=height)
                page.insert_text((30, 30), "ImageSizer integration")
            doc.save(self.source)

    def process(self, **options):
        args = dict(target_size=320, operation="auto", size_type="width",
                    crop_type="none", filename_pattern={})
        args.update(options)
        return process_document(self.source, self.root / "out", **args)

    def test_pdf_pages_crop_webp_and_progress(self):
        progress = []
        pages = []
        self.assertEqual(self.process(output_format="webp", crop_type="square",
                                     progress_callback=progress.append,
                                     page_callback=lambda *args: pages.append(args)), 2)
        self.assertEqual(len(pages), 2)
        for path, *_ in pages:
            with Image.open(path) as img:
                self.assertEqual(img.size, (320, 320))
                self.assertEqual(img.format, "WEBP")
        self.assertEqual(progress[-1], 1)
        self.assertEqual(progress, sorted(progress))

    def test_original_format_and_repeat_preserve_existing(self):
        self.process(size_type="none", target_size=None)
        previous = {p: p.read_bytes() for p in (self.root / "out").glob("*.png")}
        self.assertEqual(len(previous), 2)
        self.process(size_type="none", target_size=None)
        self.assertEqual(len(list((self.root / "out").glob("*.png"))), 4)
        for path, data in previous.items():
            self.assertEqual(path.read_bytes(), data)
            with Image.open(path) as img:
                self.assertEqual(img.width, 1920)

    def test_cancel_after_first_page(self):
        completed = []
        self.assertEqual(self.process(cancelled=lambda: bool(completed),
                                     page_callback=lambda *args: completed.append(args)), 1)
        self.assertEqual(len(list((self.root / "out").glob("*.png"))), 1)

    def test_corrupt_pdf_reports_error(self):
        self.source.write_bytes(b"not a PDF")
        with self.assertRaises(Exception):
            self.process()
        self.assertFalse(list((self.root / "out").iterdir()))

    def test_office_cleanup_on_conversion_failure(self):
        import pythoncom
        import win32com.client
        for suffix, collection in [(".docx", "Documents"), (".xlsx", "Workbooks")]:
            with self.subTest(suffix=suffix):
                app = MagicMock()
                doc = getattr(app, collection).Open.return_value
                doc.ExportAsFixedFormat.side_effect = RuntimeError("export failed")
                with patch.object(win32com.client, "DispatchEx", return_value=app), \
                     patch.object(pythoncom, "CoInitialize") as init, \
                     patch.object(pythoncom, "CoUninitialize") as uninit:
                    with self.assertRaisesRegex(RuntimeError, "export failed"):
                        with _office_document(self.root / ("sample" + suffix), self.root / "temp.pdf"):
                            pass
                    init.assert_called_once()
                    uninit.assert_called_once()
                    doc.Close.assert_called_once_with(False)
                    app.Quit.assert_called_once()

    def test_powerpoint_slides_use_common_image_processing(self):
        from contextlib import contextmanager
        source = self.root / "スライド.pptx"
        source.touch()
        doc = MagicMock()
        doc.PageSetup.SlideWidth = 720
        doc.PageSetup.SlideHeight = 405
        doc.Slides.Count = 2

        def export(path, fmt, width, height):
            with Image.new("RGB", (width, height), "white") as img:
                img.save(path)

        doc.Slides.return_value.Export.side_effect = export

        @contextmanager
        def office(*args):
            yield doc

        with patch("document_processor._office_document", office):
            count = process_document(source, self.root / "out", 240, "auto", "height",
                                     "square", output_format="webp")
        self.assertEqual(count, 2)
        for path in (self.root / "out").glob("*.webp"):
            with Image.open(path) as img:
                self.assertEqual(img.size, (240, 240))


if __name__ == "__main__":
    unittest.main()
