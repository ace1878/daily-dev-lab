import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from folder_report import (
    NO_EXTENSION,
    build_parser,
    format_size,
    main,
    render_text,
    scan_folder,
    write_csv,
)


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

            report = scan_folder(root, top=0)

            self.assertEqual(report.largest_files, [])
            self.assertEqual(report.files, 1)
            self.assertEqual(report.size, 1)

    def test_same_size_files_keep_path_sort_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in ("zeta.bin", "alpha.bin", "middle.bin"):
                (root / filename).write_bytes(b"1234")

            report = scan_folder(root, top=2)

            self.assertEqual(
                [(item.path, item.size) for item in report.largest_files],
                [("alpha.bin", 4), ("middle.bin", 4)],
            )

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

    def test_excludes_file_patterns_and_directory_names_from_all_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "keep.txt").write_bytes(b"123")
            (root / "app.log").write_bytes(b"12345")

            nested = root / "nested"
            nested.mkdir()
            (nested / "debug.log").write_bytes(b"1234567")
            (nested / "keep.bin").write_bytes(b"12")

            dependency_directory = nested / "node_modules"
            dependency_directory.mkdir()
            (dependency_directory / "package.bin").write_bytes(b"123456789")

            report = scan_folder(root, exclude=["*.log", "node_modules"])

            self.assertEqual(report.files, 2)
            self.assertEqual(report.size, 5)
            self.assertEqual(
                [(item.extension, item.files, item.size) for item in report.extensions],
                [(".bin", 1, 2), (".txt", 1, 3)],
            )
            self.assertEqual(
                [(item.path, item.size) for item in report.largest_files],
                [("keep.txt", 3), (str(Path("nested") / "keep.bin"), 2)],
            )

    def test_parser_accepts_repeated_exclude_options(self) -> None:
        arguments = build_parser().parse_args(
            [".", "--exclude", "*.log", "--exclude", "node_modules"]
        )

        self.assertEqual(arguments.exclude, ["*.log", "node_modules"])

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


class CsvOutputTests(unittest.TestCase):
    def test_writes_extension_statistics_with_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.txt").write_bytes(b"123")
            (root / "second.TXT").write_bytes(b"12")
            (root / "image.png").write_bytes(b"1234")
            output = root / "report.csv"

            write_csv(scan_folder(root), output)

            with output.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(
                rows,
                [
                    {"extension": ".png", "files": "1", "size_bytes": "4"},
                    {"extension": ".txt", "files": "2", "size_bytes": "5"},
                ],
            )

    def test_parser_rejects_json_and_csv_together(self) -> None:
        error_output = io.StringIO()

        with redirect_stderr(error_output), self.assertRaises(SystemExit) as context:
            build_parser().parse_args([".", "--json", "--csv", "report.csv"])

        self.assertEqual(context.exception.code, 2)
        self.assertIn("not allowed with argument", error_output.getvalue())

    def test_main_reports_csv_save_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "missing" / "report.csv"
            error_output = io.StringIO()

            with patch(
                "sys.argv",
                ["folder_report.py", str(root), "--csv", str(output)],
            ), redirect_stderr(error_output):
                exit_code = main()

            self.assertEqual(exit_code, 2)
            self.assertIn("Could not save CSV", error_output.getvalue())
            self.assertIn(str(output), error_output.getvalue())

    def test_main_does_not_include_existing_output_csv_in_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"123")
            output = root / "report.csv"
            output.write_bytes(b"old report data")

            with patch(
                "sys.argv",
                ["folder_report.py", str(root), "--csv", str(output)],
            ), redirect_stdout(io.StringIO()):
                exit_code = main()

            with output.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                rows,
                [{"extension": ".txt", "files": "1", "size_bytes": "3"}],
            )


if __name__ == "__main__":
    unittest.main()

