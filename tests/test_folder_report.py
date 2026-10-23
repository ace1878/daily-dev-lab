import argparse
import csv
import io
import json
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
    parse_size,
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

    def test_min_size_includes_boundary_and_filters_all_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.txt").write_bytes(b"1234")
            (root / "boundary.txt").write_bytes(b"12345")
            (root / "large.bin").write_bytes(b"123456")
            (root / "ignored.log").write_bytes(b"1234567")

            report = scan_folder(root, min_size=5, exclude=["*.log"])

            self.assertEqual(report.files, 2)
            self.assertEqual(report.size, 11)
            self.assertEqual(
                [(item.extension, item.files, item.size) for item in report.extensions],
                [(".bin", 1, 6), (".txt", 1, 5)],
            )
            self.assertEqual(
                [(item.path, item.size) for item in report.largest_files],
                [("large.bin", 6), ("boundary.txt", 5)],
            )

    def test_max_size_includes_boundary_and_filters_all_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.txt").write_bytes(b"1234")
            (root / "boundary.txt").write_bytes(b"12345")
            (root / "large.bin").write_bytes(b"123456")

            report = scan_folder(root, max_size=5)

            self.assertEqual(report.files, 2)
            self.assertEqual(report.size, 9)
            self.assertEqual(
                [(item.extension, item.files, item.size) for item in report.extensions],
                [(".txt", 2, 9)],
            )
            self.assertEqual(
                [(item.path, item.size) for item in report.largest_files],
                [("boundary.txt", 5), ("small.txt", 4)],
            )

    def test_min_and_max_size_include_only_requested_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.txt").write_bytes(b"123")
            (root / "minimum.txt").write_bytes(b"1234")
            (root / "maximum.bin").write_bytes(b"12345")
            (root / "large.bin").write_bytes(b"123456")

            report = scan_folder(root, min_size=4, max_size=5)

            self.assertEqual(report.files, 2)
            self.assertEqual(report.size, 9)
            self.assertEqual(
                [(item.path, item.size) for item in report.largest_files],
                [("maximum.bin", 5), ("minimum.txt", 4)],
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

    def test_max_depth_zero_one_and_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "root.txt").write_bytes(b"1")
            level_one = root / "level-one"
            level_one.mkdir()
            (level_one / "one.txt").write_bytes(b"22")
            level_two = level_one / "level-two"
            level_two.mkdir()
            (level_two / "two.txt").write_bytes(b"333")
            level_three = level_two / "level-three"
            level_three.mkdir()
            (level_three / "three.txt").write_bytes(b"4444")

            expected = {
                0: (["root.txt"], 1),
                1: ([str(Path("level-one") / "one.txt"), "root.txt"], 3),
                2: (
                    [
                        str(Path("level-one") / "level-two" / "two.txt"),
                        str(Path("level-one") / "one.txt"),
                        "root.txt",
                    ],
                    6,
                ),
            }
            for max_depth, (paths, total_size) in expected.items():
                with self.subTest(max_depth=max_depth):
                    report = scan_folder(root, max_depth=max_depth)
                    self.assertEqual(report.files, max_depth + 1)
                    self.assertEqual(report.size, total_size)
                    self.assertEqual(
                        [item.path for item in report.largest_files],
                        paths,
                    )

    def test_omitted_max_depth_keeps_full_recursive_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deepest = root / "one" / "two" / "three"
            deepest.mkdir(parents=True)
            (root / "root.txt").write_bytes(b"1")
            (deepest / "deep.txt").write_bytes(b"22")

            report = scan_folder(root)

            self.assertEqual(report.files, 2)
            self.assertEqual(report.size, 3)
            self.assertEqual(
                [item.path for item in report.largest_files],
                [str(Path("one") / "two" / "three" / "deep.txt"), "root.txt"],
            )

    def test_max_depth_combines_with_existing_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.txt").write_bytes(b"1")
            level_one = root / "level-one"
            level_one.mkdir()
            (level_one / "keep.TXT").write_bytes(b"123")
            (level_one / "skip.log").write_bytes(b"123")
            level_two = level_one / "level-two"
            level_two.mkdir()
            (level_two / "too-deep.txt").write_bytes(b"123")

            report = scan_folder(
                root,
                max_depth=1,
                extensions=["txt"],
                min_size=2,
                max_size=3,
                exclude=["*.log"],
                sort_by="size",
            )

            self.assertEqual(report.files, 1)
            self.assertEqual(report.size, 3)
            self.assertEqual(
                [item.path for item in report.largest_files],
                [str(Path("level-one") / "keep.TXT")],
            )

    def test_max_depth_prunes_deeper_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child"
            child.mkdir()
            visited_deeper = []

            def fake_walk(*args, **kwargs):
                directories = ["child"]
                yield str(root), directories, []
                if directories:
                    visited_deeper.append(True)
                    yield str(child), [], []

            with patch("folder_report.os.walk", side_effect=fake_walk):
                scan_folder(root, max_depth=0)

            self.assertEqual(visited_deeper, [])

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

    def test_filters_a_single_extension_without_leading_dot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "keep.txt").write_bytes(b"123")
            (root / "skip.bin").write_bytes(b"12345")

            report = scan_folder(root, extensions=["txt"])

            self.assertEqual(report.files, 1)
            self.assertEqual(report.size, 3)
            self.assertEqual(
                [(item.extension, item.files, item.size) for item in report.extensions],
                [(".txt", 1, 3)],
            )
            self.assertEqual(
                [(item.path, item.size) for item in report.largest_files],
                [("keep.txt", 3)],
            )

    def test_multiple_extensions_use_or_condition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_bytes(b"12")
            (root / "data.csv").write_bytes(b"123")
            (root / "skip.bin").write_bytes(b"1234")

            report = scan_folder(root, extensions=[".txt", "csv"])

            self.assertEqual(report.files, 2)
            self.assertEqual(
                [item.extension for item in report.extensions],
                [".csv", ".txt"],
            )

    def test_extension_filter_is_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.TXT").write_bytes(b"1")
            (root / "second.TxT").write_bytes(b"22")
            (root / "skip.csv").write_bytes(b"333")

            report = scan_folder(root, extensions=["tXt"])

            self.assertEqual(report.files, 2)
            self.assertEqual(report.size, 3)
            self.assertEqual(report.extensions[0].extension, ".txt")

    def test_extension_filter_combines_with_size_and_exclude_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "too-small.txt").write_bytes(b"123")
            (root / "keep.txt").write_bytes(b"1234")
            (root / "too-large.txt").write_bytes(b"123456")
            (root / "excluded.txt").write_bytes(b"12345")
            (root / "right-size.bin").write_bytes(b"1234")

            report = scan_folder(
                root,
                extensions=["txt"],
                min_size=4,
                max_size=5,
                exclude=["excluded.txt"],
                sort_by="size",
            )

            self.assertEqual(report.files, 1)
            self.assertEqual(report.size, 4)
            self.assertEqual(report.largest_files[0].path, "keep.txt")

    def test_parser_accepts_repeated_exclude_options(self) -> None:
        arguments = build_parser().parse_args(
            [".", "--exclude", "*.log", "--exclude", "node_modules"]
        )

        self.assertEqual(arguments.exclude, ["*.log", "node_modules"])

    def test_parser_accepts_repeated_extension_options(self) -> None:
        arguments = build_parser().parse_args(
            [".", "--extension", "txt", "--extension", ".CSV"]
        )

        self.assertEqual(arguments.extension, ["txt", ".CSV"])

    def test_rejects_invalid_extension_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for extension in ("", ".", "tar.gz", "folder/txt", "folder\\txt"):
                with self.subTest(extension=extension), self.assertRaisesRegex(
                    ValueError,
                    "--extension must be a single extension name",
                ):
                    scan_folder(root, extensions=[extension])

            output = io.StringIO()
            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--extension", "."],
            ), redirect_stdout(output):
                exit_code = main()

            self.assertEqual(exit_code, 2)
            self.assertIn("--extension must be a single extension name", output.getvalue())

    def test_rejects_missing_folder_and_negative_top(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                scan_folder(root / "missing")
            with self.assertRaises(ValueError):
                scan_folder(root, top=-1)
            with self.assertRaisesRegex(ValueError, "--min-size must be zero or greater"):
                scan_folder(root, min_size=-1)
            with self.assertRaisesRegex(ValueError, "--max-depth must be zero or greater"):
                scan_folder(root, max_depth=-1)

    def test_main_reports_invalid_max_depth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--max-depth", "-1"],
            ), redirect_stdout(output):
                exit_code = main()

            self.assertEqual(exit_code, 2)
            self.assertIn("--max-depth must be zero or greater", output.getvalue())

        error_output = io.StringIO()
        with redirect_stderr(error_output), self.assertRaises(SystemExit) as context:
            build_parser().parse_args([".", "--max-depth", "invalid"])

        self.assertEqual(context.exception.code, 2)
        self.assertIn("invalid int value", error_output.getvalue())

    def test_rejects_invalid_max_size_and_reversed_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "--max-size must be zero or greater"):
                scan_folder(root, max_size=-1)
            with self.assertRaisesRegex(
                ValueError,
                "--min-size must not be greater than --max-size",
            ):
                scan_folder(root, min_size=6, max_size=5)

        error_output = io.StringIO()
        with redirect_stderr(error_output), self.assertRaises(SystemExit) as context:
            build_parser().parse_args([".", "--max-size", "invalid"])

        self.assertEqual(context.exception.code, 2)
        self.assertIn("size must be a whole number", error_output.getvalue())

    def test_main_reports_reversed_size_range_with_units(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "folder_report.py",
                    directory,
                    "--min-size",
                    "2MiB",
                    "--max-size",
                    "1MiB",
                ],
            ), redirect_stdout(output):
                exit_code = main()

            self.assertEqual(exit_code, 2)
            self.assertIn(
                "--min-size must not be greater than --max-size",
                output.getvalue(),
            )

    def test_min_and_max_unit_sizes_filter_cli_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.bin").write_bytes(b"x" * 1023)
            (root / "minimum.bin").write_bytes(b"x" * (2 * 1024))
            (root / "maximum.bin").write_bytes(b"x" * (3 * 1024))
            (root / "large.bin").write_bytes(b"x" * (3 * 1024 + 1))
            output = io.StringIO()

            with patch(
                "sys.argv",
                [
                    "folder_report.py",
                    directory,
                    "--min-size",
                    "2KiB",
                    "--max-size",
                    "3kIb",
                    "--json",
                ],
            ), redirect_stdout(output):
                exit_code = main()

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["files"], 2)
            self.assertEqual(result["size"], 5 * 1024)

    def test_min_size_works_with_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.txt").write_bytes(b"1234")
            (root / "large.txt").write_bytes(b"12345")
            output = io.StringIO()

            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--min-size", "5", "--json"],
            ), redirect_stdout(output):
                exit_code = main()

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["files"], 1)
            self.assertEqual(result["size"], 5)

    def test_sorts_extension_statistics_by_extension_size_and_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, size in (
                ("one.bin", 4),
                ("two.bin", 4),
                ("one.csv", 10),
                ("one.log", 3),
                ("two.log", 5),
                ("one.txt", 2),
                ("two.txt", 2),
                ("three.txt", 2),
                ("ignored.tmp", 20),
                ("small.dat", 1),
            ):
                (root / filename).write_bytes(b"x" * size)

            expected = {
                "extension": [".bin", ".csv", ".log", ".txt"],
                "size": [".csv", ".bin", ".log", ".txt"],
                "count": [".txt", ".bin", ".log", ".csv"],
            }
            for sort_by, extensions in expected.items():
                with self.subTest(sort_by=sort_by):
                    report = scan_folder(
                        root,
                        exclude=["*.tmp"],
                        min_size=2,
                        sort_by=sort_by,
                    )
                    self.assertEqual(
                        [item.extension for item in report.extensions],
                        extensions,
                    )

    def test_rejects_invalid_sort_by(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "--sort-by must be one of"):
                scan_folder(Path(directory), sort_by="unknown")

        error_output = io.StringIO()
        with redirect_stderr(error_output), self.assertRaises(SystemExit) as context:
            build_parser().parse_args([".", "--sort-by", "unknown"])

        self.assertEqual(context.exception.code, 2)
        self.assertIn("invalid choice", error_output.getvalue())

    def test_render_text_handles_empty_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = render_text(scan_folder(Path(directory)))

            self.assertIn("Files: 0", output)
            self.assertEqual(output.count("(no files)"), 2)

    def test_show_skipped_lists_paths_in_name_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "zeta.txt").write_bytes(b"1")
            (root / "alpha.txt").write_bytes(b"2")
            (root / "keep.txt").write_bytes(b"3")
            original_stat = Path.stat

            def fake_stat(path, *args, **kwargs):
                if path.name in {"alpha.txt", "zeta.txt"}:
                    raise PermissionError("access denied", str(path))
                return original_stat(path, *args, **kwargs)

            with patch.object(Path, "stat", new=fake_stat):
                report = scan_folder(root)

            output = render_text(report, show_skipped=True)
            alpha_path = str(root / "alpha.txt")
            zeta_path = str(root / "zeta.txt")
            self.assertIn("Skipped paths: 2", output)
            self.assertLess(output.index(alpha_path), output.index(zeta_path))
            self.assertEqual(report.files, 1)

    def test_show_skipped_omits_section_when_there_are_no_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "readable.txt").write_bytes(b"1")

            output = render_text(scan_folder(root), show_skipped=True)

            self.assertNotIn("Skipped paths:", output)

    def test_default_text_keeps_skipped_count_without_path_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked = root / "blocked.txt"
            blocked.write_bytes(b"1")
            original_stat = Path.stat

            def fake_stat(path, *args, **kwargs):
                if path == blocked:
                    raise PermissionError("access denied", str(path))
                return original_stat(path, *args, **kwargs)

            with patch.object(Path, "stat", new=fake_stat):
                report = scan_folder(root)

            output = render_text(report)
            self.assertIn("Skipped paths: 1", output)
            self.assertNotIn(f"  {blocked}", output)

    def test_main_show_skipped_flag_lists_collected_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked = root / "blocked.txt"
            blocked.write_bytes(b"1")
            original_stat = Path.stat

            def fake_stat(path, *args, **kwargs):
                if path == blocked:
                    raise PermissionError("access denied", str(path))
                return original_stat(path, *args, **kwargs)

            output = io.StringIO()
            with patch.object(Path, "stat", new=fake_stat), patch(
                "sys.argv",
                ["folder_report.py", directory, "--show-skipped"],
            ), redirect_stdout(output):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            self.assertIn(f"  {blocked}", output.getvalue())


class FormatSizeTests(unittest.TestCase):
    def test_formats_binary_units(self) -> None:
        self.assertEqual(format_size(999), "999 B")
        self.assertEqual(format_size(1536), "1.5 KiB")


class ParseSizeTests(unittest.TestCase):
    def test_parses_existing_byte_input(self) -> None:
        self.assertEqual(parse_size("0"), 0)
        self.assertEqual(parse_size("1048576"), 1048576)

    def test_parses_kib_mib_and_gib(self) -> None:
        self.assertEqual(parse_size("2KiB"), 2 * 1024)
        self.assertEqual(parse_size("3MiB"), 3 * 1024**2)
        self.assertEqual(parse_size("4GiB"), 4 * 1024**3)

    def test_units_are_case_insensitive(self) -> None:
        self.assertEqual(parse_size("2kIb"), 2 * 1024)
        self.assertEqual(parse_size("3MIB"), 3 * 1024**2)
        self.assertEqual(parse_size("4gib"), 4 * 1024**3)

    def test_rejects_negative_decimal_and_invalid_unit(self) -> None:
        cases = {
            "-1": "size must be zero or greater",
            "1.5MiB": "size must be a whole number",
            "2MB": "size must be a whole number",
            "abc": "size must be a whole number",
        }
        for value, message in cases.items():
            with self.subTest(value=value), self.assertRaisesRegex(
                argparse.ArgumentTypeError,
                message,
            ):
                parse_size(value)

    def test_parser_converts_min_and_max_sizes_to_bytes(self) -> None:
        arguments = build_parser().parse_args(
            [".", "--min-size", "2KiB", "--max-size", "3mIb"]
        )

        self.assertEqual(arguments.min_size, 2 * 1024)
        self.assertEqual(arguments.max_size, 3 * 1024**2)


class CsvOutputTests(unittest.TestCase):
    def test_show_skipped_does_not_change_json_or_csv_output_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"123")

            json_output = io.StringIO()
            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--show-skipped", "--json"],
            ), redirect_stdout(json_output):
                json_exit_code = main()
            json_result = json.loads(json_output.getvalue())

            csv_output = root / "report.csv"
            with patch(
                "sys.argv",
                [
                    "folder_report.py",
                    directory,
                    "--show-skipped",
                    "--csv",
                    str(csv_output),
                ],
            ), redirect_stdout(io.StringIO()):
                csv_exit_code = main()
            with csv_output.open(encoding="utf-8", newline="") as csv_file:
                csv_rows = list(csv.DictReader(csv_file))

            self.assertEqual(json_exit_code, 0)
            self.assertEqual(json_result["files"], 1)
            self.assertEqual(json_result["skipped"], [])
            self.assertEqual(csv_exit_code, 0)
            self.assertEqual(
                csv_rows,
                [{"extension": ".txt", "files": "1", "size_bytes": "3"}],
            )

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

    def test_min_size_works_with_csv_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.txt").write_bytes(b"1234")
            (root / "large.bin").write_bytes(b"12345")
            output = root / "report.csv"

            with patch(
                "sys.argv",
                [
                    "folder_report.py",
                    str(root),
                    "--min-size",
                    "5",
                    "--csv",
                    str(output),
                ],
            ), redirect_stdout(io.StringIO()):
                exit_code = main()

            with output.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                rows,
                [{"extension": ".bin", "files": "1", "size_bytes": "5"}],
            )

    def test_sort_order_is_shared_by_text_json_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_bytes(b"123")
            (root / "one.bin").write_bytes(b"12345")
            expected = [".bin", ".txt"]

            report = scan_folder(root, sort_by="size")
            text_output = render_text(report)
            self.assertLess(text_output.index(".bin"), text_output.index(".txt"))

            json_output = io.StringIO()
            with patch(
                "sys.argv",
                ["folder_report.py", str(root), "--sort-by", "size", "--json"],
            ), redirect_stdout(json_output):
                json_exit_code = main()
            json_extensions = [
                item["extension"]
                for item in json.loads(json_output.getvalue())["extensions"]
            ]

            csv_output = root / "report.csv"
            with patch(
                "sys.argv",
                [
                    "folder_report.py",
                    str(root),
                    "--sort-by",
                    "size",
                    "--csv",
                    str(csv_output),
                ],
            ), redirect_stdout(io.StringIO()):
                csv_exit_code = main()
            with csv_output.open(encoding="utf-8", newline="") as csv_file:
                csv_extensions = [row["extension"] for row in csv.DictReader(csv_file)]

            self.assertEqual(json_exit_code, 0)
            self.assertEqual(csv_exit_code, 0)
            self.assertEqual(json_extensions, expected)
            self.assertEqual(csv_extensions, expected)

    def test_extension_filter_works_with_csv_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "keep.TXT").write_bytes(b"123")
            (root / "skip.bin").write_bytes(b"12345")
            output = root / "report.csv"

            with patch(
                "sys.argv",
                [
                    "folder_report.py",
                    str(root),
                    "--extension",
                    "txt",
                    "--csv",
                    str(output),
                ],
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

