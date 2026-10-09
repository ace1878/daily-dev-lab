import tempfile
import unittest
from pathlib import Path

from folder_report import NO_EXTENSION, format_size, render_text, scan_folder


class ScanFolderTests(unittest.TestCase):
    def test_summarizes_extensions_and_largest_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_bytes(b"abc")
            (root / "README").write_bytes(b"12345")
            nested = root / "nested"
            nested.mkdir()
            (nested / "DATA.TXT").write_bytes(b"1234567")

            report = scan_folder(root, top=2)

            self.assertEqual(report.files, 3)
            self.assertEqual(report.size, 15)
            self.assertEqual(
                [(item.extension, item.files, item.size) for item in report.extensions],
                [(".txt", 2, 10), (NO_EXTENSION, 1, 5)],
            )
            self.assertEqual(
                [(item.path, item.size) for item in report.largest_files],
                [(str(Path("nested") / "DATA.TXT"), 7), ("README", 5)],
            )

    def test_top_zero_returns_no_largest_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.bin").write_bytes(b"1")

            self.assertEqual(scan_folder(root, top=0).largest_files, [])

    def test_ignores_hidden_items_and_cache_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "visible.txt").write_bytes(b"1")
            (root / ".hidden.txt").write_bytes(b"22")
            hidden_directory = root / ".git"
            hidden_directory.mkdir()
            (hidden_directory / "config").write_bytes(b"333")
            cache_directory = root / "__pycache__"
            cache_directory.mkdir()
            (cache_directory / "cached.pyc").write_bytes(b"4444")

            default_report = scan_folder(root)
            complete_report = scan_folder(root, include_hidden=True)

            self.assertEqual(default_report.files, 1)
            self.assertEqual(default_report.size, 1)
            self.assertEqual(complete_report.files, 4)
            self.assertEqual(complete_report.size, 10)

    def test_rejects_missing_folder_and_negative_top(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                scan_folder(root / "missing")
            with self.assertRaises(ValueError):
                scan_folder(root, top=-1)

    def test_render_text_handles_empty_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = render_text(scan_folder(Path(directory)))

            self.assertIn("Files: 0", output)
            self.assertEqual(output.count("(no files)"), 2)


class FormatSizeTests(unittest.TestCase):
    def test_formats_binary_units(self) -> None:
        self.assertEqual(format_size(999), "999 B")
        self.assertEqual(format_size(1536), "1.5 KiB")


if __name__ == "__main__":
    unittest.main()

