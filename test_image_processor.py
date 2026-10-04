import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from PIL import Image

from image_processor import WEBP_MAX_DIMENSION, process_image, svg_to_bytes


# A small vector file whose patterned gradient produces much larger PNG/WebP
# output. Keep this self-contained so the regression needs no external assets.
PATTERNED_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="768">
<defs><linearGradient id="g" x2="100%" y2="100%"><stop stop-color="#173f8a"/>
<stop offset="1" stop-color="#f9bc35"/></linearGradient>
<pattern id="p" width="17" height="19" patternUnits="userSpaceOnUse">
<path d="M0 0L17 19M17 0L0 19" stroke="#ffffff" stroke-opacity=".65"
stroke-width="1.3"/></pattern></defs>
<rect width="100%" height="100%" fill="url(#g)"/>
<rect width="100%" height="100%" fill="url(#p)"/></svg>"""


class ImageProcessingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "out"
        self.output.mkdir()

    def process(self, source, **options):
        args = dict(target_size=None, operation="auto", size_type="none",
                    crop_type="none", filename_pattern={})
        args.update(options)
        return process_image(source, self.output, **args)


@unittest.skipIf(svg_to_bytes is None, "SVG tests require resvg-py")
class SVGProcessingTests(ImageProcessingTestCase):
    def setUp(self):
        super().setUp()
        self.source = self.root / "日本語 画像.SVG"
        self.source.write_text(PATTERNED_SVG, encoding="utf-8")

    def assert_size_limit(self, operation):
        limit_bytes = 8 * 1024
        source_bytes = self.source.read_bytes()
        self.assertLess(len(source_bytes), limit_bytes)
        for output_format in (None, "png", "webp"):
            baseline, _, _ = self.process(self.source, output_format=output_format)
            self.assertGreater(Path(baseline).stat().st_size, limit_bytes)
            for size_type, target in (("kb", 8), ("mb", 8 / 1024)):
                with self.subTest(operation=operation, output_format=output_format,
                                  size_type=size_type):
                    progress = []
                    path, ratio, note = self.process(
                        self.source, target_size=target, size_type=size_type,
                        operation=operation, output_format=output_format,
                        progress_callback=progress.append,
                    )
                    self.assertLessEqual(Path(path).stat().st_size, limit_bytes)
                    self.assertLess(ratio, 1)
                    self.assertNotIn("近似値", note or "")
                    with Image.open(path) as img:
                        self.assertEqual(img.format, "WEBP" if output_format == "webp" else "PNG")
                        self.assertLess(img.width, 1024)
                        self.assertLess(img.height, 768)
                    self.assertEqual(progress[-1], 1.0)
                    self.assertEqual(progress, sorted(progress))
                    if output_format is None:
                        self.assertIn("SVG入力はPNG形式で出力しました", note)
        self.assertEqual(self.source.read_bytes(), source_bytes)

    def test_auto_size_limits_use_raster_size(self):
        self.assert_size_limit("auto")

    def test_compress_size_limits_use_raster_size(self):
        self.assert_size_limit("compress")

    def test_thin_svg_size_limits_keep_dimensions_positive(self):
        for width, height in ((1, 10000), (10000, 1)):
            self.source.write_text(
                PATTERNED_SVG.replace('width="1024" height="768"',
                                      f'width="{width}" height="{height}"', 1),
                encoding="utf-8",
            )
            for output_format in (None, "png", "webp"):
                with self.subTest(size=(width, height), output_format=output_format):
                    path, _, _ = self.process(
                        self.source, target_size=1, size_type="kb",
                        output_format=output_format,
                    )
                    self.assertLessEqual(Path(path).stat().st_size, 1024)
                    with Image.open(path) as img:
                        self.assertGreaterEqual(img.width, 1)
                        self.assertGreaterEqual(img.height, 1)
                        self.assertEqual(min(img.size), 1)

    def test_webp_size_reference_accounts_for_dimension_cap(self):
        self.source.write_text(
            PATTERNED_SVG.replace('width="1024" height="768"',
                                  'width="300000" height="2"', 1),
            encoding="utf-8",
        )
        baseline, _, _ = self.process(self.source, output_format="webp")
        limit_bytes = Path(baseline).stat().st_size * 0.9
        for size_type, divisor in (("kb", 1024), ("mb", 1024 * 1024)):
            with self.subTest(size_type=size_type):
                path, _, note = self.process(
                    self.source, target_size=limit_bytes / divisor,
                    size_type=size_type, output_format="webp",
                )
                self.assertLessEqual(Path(path).stat().st_size, limit_bytes)
                self.assertNotIn("近似値", note or "")
                with Image.open(path) as img:
                    self.assertLessEqual(max(img.size), WEBP_MAX_DIMENSION)

    def test_small_raster_is_not_resized_even_with_large_svg_source(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="24">'
               '<rect width="48" height="24" fill="red"/><!--' + "padding" * 2048 +
               '--></svg>')
        self.source.write_text(svg, encoding="utf-8")
        self.assertGreater(self.source.stat().st_size, 1024)
        for output_format in (None, "png", "webp"):
            for size_type, target in (("kb", 1), ("mb", 1 / 1024)):
                with self.subTest(output_format=output_format, size_type=size_type):
                    path, ratio, _ = self.process(
                        self.source, target_size=target, size_type=size_type,
                        output_format=output_format,
                    )
                    self.assertLessEqual(Path(path).stat().st_size, 1024)
                    self.assertEqual(ratio, 1.0)
                    with Image.open(path) as img:
                        self.assertEqual(img.size, (48, 24))

    def test_no_resize_keeps_dimensions_and_output_format(self):
        for output_format in (None, "png", "webp"):
            with self.subTest(output_format=output_format):
                path, ratio, _ = self.process(self.source, output_format=output_format)
                self.assertEqual(ratio, 1.0)
                with Image.open(path) as img:
                    self.assertEqual(img.size, (1024, 768))
                    self.assertEqual(img.format, "WEBP" if output_format == "webp" else "PNG")

    def test_dimension_resize_and_crop_are_preserved(self):
        self.source.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="24">'
            '<rect width="48" height="24" fill="red"/></svg>', encoding="utf-8",
        )
        for output_format in (None, "png", "webp"):
            for size_type in ("width", "height", "long_edge"):
                with self.subTest(output_format=output_format, size_type=size_type):
                    path, _, _ = self.process(
                        self.source, target_size=64, size_type=size_type,
                        crop_type="square", output_format=output_format,
                    )
                    with Image.open(path) as img:
                        self.assertEqual(img.size, (64, 64))


class RasterProcessingTests(ImageProcessingTestCase):
    def test_under_limit_raster_keeps_dimensions(self):
        for suffix in ("png", "jpg", "webp"):
            source = self.root / ("source." + suffix)
            with Image.new("RGB", (96, 64), "red") as img:
                img.save(source)
            source_bytes = source.read_bytes()
            limit_bytes = len(source_bytes) * 2
            for size_type, divisor in (("kb", 1024), ("mb", 1024 * 1024)):
                with self.subTest(suffix=suffix, size_type=size_type):
                    path, ratio, note = self.process(
                        source, target_size=limit_bytes / divisor, size_type=size_type,
                    )
                    self.assertEqual(ratio, 1.0)
                    self.assertIn("リサイズ不要", note)
                    self.assertLessEqual(Path(path).stat().st_size, limit_bytes)
                    with Image.open(path) as img:
                        self.assertEqual(img.size, (96, 64))
            self.assertEqual(source.read_bytes(), source_bytes)


class OutputCollisionTests(ImageProcessingTestCase):
    def setUp(self):
        super().setUp()
        self.source = self.root / "source.png"
        with Image.new("RGB", (96, 64), "red") as img:
            img.save(self.source)

    def test_repeated_outputs_preserve_existing_in_every_save_path(self):
        cases = (
            {},
            dict(size_type="kb", target_size=1024),
            dict(size_type="width", target_size=48),
            dict(size_type="kb", target_size=0.000001),
        )
        for options in cases:
            with self.subTest(options=options):
                first, _, _ = self.process(self.source, **options)
                original = Path(first).read_bytes()
                second, _, _ = self.process(self.source, **options)
                self.assertNotEqual(first, second)
                self.assertEqual(Path(first).read_bytes(), original)
                with Image.open(second) as img:
                    img.load()

    def test_format_conversion_preserves_existing_sibling(self):
        self.output = self.root
        sibling = self.root / "source.webp"
        sibling.write_bytes(b"existing sibling must survive")
        source_bytes = self.source.read_bytes()
        result, _, _ = self.process(self.source, output_format="webp")
        self.assertNotEqual(Path(result), sibling)
        self.assertEqual(sibling.read_bytes(), b"existing sibling must survive")
        self.assertEqual(self.source.read_bytes(), source_bytes)
        with Image.open(result) as img:
            self.assertEqual(img.format, "WEBP")

    def test_same_folder_preserves_source_and_processed_files(self):
        self.output = self.root
        source_bytes = self.source.read_bytes()
        existing = self.root / "source_processed.png"
        existing.write_bytes(b"previous output")
        # A directory with a candidate name must not block processing either.
        (self.root / "source_processed_001.png").mkdir()
        result, _, _ = self.process(self.source)
        self.assertEqual(Path(result).name, "source_processed_002.png")
        self.assertEqual(existing.read_bytes(), b"previous output")
        self.assertEqual(self.source.read_bytes(), source_bytes)

    def test_sequential_and_size_ratio_names_do_not_collide(self):
        options = dict(size_type="width", target_size=48,
                       filename_pattern={"include_sequential": True,
                                         "include_size_ratio": True})
        first, _, _ = self.process(self.source, **options)
        original = Path(first).read_bytes()
        second, _, _ = self.process(self.source, **options)
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), original)

    def test_windows_directory_collision_uses_another_name(self):
        existing = self.output / "source.png"
        existing.mkdir()
        original_open = open

        def windows_open(path, mode="r", *args, **kwargs):
            if Path(path) == existing and mode == "xb":
                raise PermissionError("directory occupies candidate")
            return original_open(path, mode, *args, **kwargs)

        with patch("builtins.open", windows_open):
            result, _, _ = self.process(self.source)
        self.assertEqual(Path(result).name, "source_001.png")
        self.assertTrue(existing.is_dir())

    def test_unwritable_destination_reports_permission_error(self):
        original_open = open

        def denied_open(path, mode="r", *args, **kwargs):
            if mode == "xb":
                raise PermissionError("destination is not writable")
            return original_open(path, mode, *args, **kwargs)

        with patch("builtins.open", denied_open):
            with self.assertRaisesRegex(PermissionError, "not writable"):
                self.process(self.source)
        self.assertFalse(list(self.output.iterdir()))

    def test_concurrent_outputs_reserve_distinct_paths(self):
        barrier = Barrier(2)
        save = Image.Image.save

        def synchronized_save(img, *args, **kwargs):
            barrier.wait(timeout=5)
            return save(img, *args, **kwargs)

        with patch.object(Image.Image, "save", synchronized_save):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(self.process, [self.source, self.source]))
        self.assertNotEqual(results[0][0], results[1][0])
        for path, _, _ in results:
            with Image.open(path) as img:
                img.load()

    def test_failed_save_removes_only_its_reserved_output(self):
        existing = self.output / "source.png"
        existing.write_bytes(b"previous output")
        with patch.object(Image.Image, "save", side_effect=OSError("save failed")):
            with self.assertRaisesRegex(OSError, "save failed"):
                self.process(self.source)
        self.assertEqual(list(self.output.iterdir()), [existing])
        self.assertEqual(existing.read_bytes(), b"previous output")


if __name__ == "__main__":
    unittest.main()
