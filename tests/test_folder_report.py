import argparse
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from importlib.metadata import PackageNotFoundError
from itertools import permutations
from unittest.mock import patch

from folder_report import (
    FileEntry,
    ExtensionSummary,
    FolderReport,
    NO_EXTENSION,
    build_parser,
    format_size,
    get_version,
    main,
    parse_size,
    read_exclude_patterns,
    read_exclude_directories,
    render_json,
    render_markdown,
    render_text,
    scan_folder,
    write_csv,
    write_json,
    write_markdown,
)


class VersionTests(unittest.TestCase):
    def test_uses_installed_package_metadata(self) -> None:
        with patch("folder_report.version", return_value="9.8.7") as metadata_version:
            self.assertEqual(get_version(), "9.8.7")
        metadata_version.assert_called_once_with("daily-dev-lab")

    def test_uninstalled_source_reads_project_version(self) -> None:
        with patch("folder_report.version", side_effect=PackageNotFoundError), patch(
            "pathlib.Path.read_text",
            return_value='[build-system]\nrequires = []\n[project]\nversion = "8.7.6"\n[tool.example]\nversion = "wrong"\n',
        ):
            self.assertEqual(get_version(), "8.7.6")

    def test_uninstalled_source_reads_real_project_file(self) -> None:
        expected = get_version()
        with patch("folder_report.version", side_effect=PackageNotFoundError):
            self.assertEqual(get_version(), expected)

    def test_version_exits_successfully_without_scanning(self) -> None:
        output = io.StringIO()
        with patch("sys.argv", ["folder-report", "--version"]), patch(
            "folder_report.scan_folder"
        ) as scan, redirect_stdout(output), self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 0)
        self.assertEqual(output.getvalue(), f"folder-report {get_version()}\n")
        scan.assert_not_called()

    def test_direct_script_version_outside_project(self) -> None:
        script = Path(__file__).resolve().parents[1] / "folder_report.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(script), "--version"], cwd=directory,
                capture_output=True, text=True, check=True,
            )
        self.assertEqual(result.stdout.strip(), f"folder-report {get_version()}")
        self.assertEqual(result.stderr, "")


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


class FilterSortTopBoundaryTests(unittest.TestCase):
    def test_min_size_boundary_tie_at_top_cutoff_keeps_full_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, size in (("below.txt", 1023), ("z.txt", 1024),
                               ("a.txt", 1024), ("large.bin", 2048)):
                (root / name).write_bytes(b"x" * size)
            for sort_by in ("extension", "size", "count"):
                with self.subTest(sort_by=sort_by):
                    report = scan_folder(root, min_size=1024, top=2, sort_by=sort_by)
                    self.assertEqual((report.files, report.size), (3, 4096))
                    self.assertEqual(
                        {item.extension: (item.files, item.size) for item in report.extensions},
                        {".bin": (1, 2048), ".txt": (2, 2048)},
                    )
                    self.assertEqual(report.largest_files, [
                        FileEntry("large.bin", 2048), FileEntry("a.txt", 1024),
                    ])

    def test_filtered_count_below_top_and_all_files_filtered_out(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, size in (("small.txt", 4), ("boundary.txt", 5), ("large.bin", 7)):
                (root / name).write_bytes(b"x" * size)
            for sort_by in ("extension", "size", "count"):
                for file_sort in ("name", "size"):
                    for minimum, expected in ((5, [
                        FileEntry("boundary.txt", 5), FileEntry("large.bin", 7),
                    ]), (8, [])):
                        with self.subTest(sort_by=sort_by, file_sort=file_sort, minimum=minimum):
                            report = scan_folder(
                                root, min_size=minimum, top=10,
                                sort_by=sort_by, file_sort=file_sort,
                            )
                            if file_sort == "size":
                                expected = list(reversed(expected))
                            self.assertEqual(report.largest_files, expected)
                            self.assertEqual((report.files, report.size), (2, 12) if minimum == 5 else (0, 0))
                            if minimum == 8:
                                self.assertEqual(report.extensions, [])

    def test_tied_top_selection_is_independent_of_directory_visit_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            relatives = ("a/z.txt", "b/a.txt", "c/b.txt")
            for relative in relatives:
                path = root / relative
                path.parent.mkdir()
                path.write_bytes(b"x" * 5)
            for order in permutations(relatives):
                for file_sort in ("size", "name"):
                    with self.subTest(order=order, file_sort=file_sort):
                        entries = [
                            (str((root / relative).parent), [], [Path(relative).name])
                            for relative in order
                        ]
                        with patch("folder_report.os.walk", return_value=iter(entries)):
                            report = scan_folder(root, min_size=5, top=2, file_sort=file_sort)
                        selected = ["a/z.txt", "b/a.txt"]
                        if file_sort == "name":
                            selected.reverse()
                        self.assertEqual(report.largest_files, [
                            FileEntry(str(Path(relative)), 5) for relative in selected
                        ])
                        self.assertEqual((report.files, report.size), (3, 15))

    def test_cli_extension_sort_and_file_sort_with_top_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, size in (("a.txt", 5), ("b.txt", 5), ("c.bin", 10),
                               ("d.log", 4), ("e.log", 4), ("below.dat", 3)):
                (root / name).write_bytes(b"x" * size)
            extension_orders = {
                "extension": [".bin", ".log", ".txt"],
                "size": [".bin", ".txt", ".log"],
                "count": [".log", ".txt", ".bin"],
            }
            for sort_by, extensions in extension_orders.items():
                for file_sort in ("size", "name"):
                    with self.subTest(sort_by=sort_by, file_sort=file_sort):
                        stdout, stderr = io.StringIO(), io.StringIO()
                        with patch("sys.argv", [
                            "folder-report", str(root), "--min-size", "4", "--top", "2",
                            "--sort-by", sort_by, "--file-sort", file_sort, "--json",
                        ]), redirect_stdout(stdout), redirect_stderr(stderr):
                            self.assertEqual(main(), 0)
                        report = json.loads(stdout.getvalue())
                        self.assertEqual(stderr.getvalue(), "")
                        self.assertEqual((report["files"], report["size"]), (5, 28))
                        self.assertEqual([item["extension"] for item in report["extensions"]], extensions)
                        expected = ["c.bin", "a.txt"] if file_sort == "size" else ["a.txt", "c.bin"]
                        self.assertEqual([item["path"] for item in report["largest_files"]], expected)

    def test_empty_folder_cli_with_minimum_sort_and_top(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for sort_by in ("extension", "size", "count"):
                for top in (0, 10):
                    with self.subTest(sort_by=sort_by, top=top):
                        stdout, stderr = io.StringIO(), io.StringIO()
                        with patch("sys.argv", [
                            "folder-report", directory, "--min-size", "1KiB",
                            "--sort-by", sort_by, "--top", str(top), "--json",
                        ]), redirect_stdout(stdout), redirect_stderr(stderr):
                            self.assertEqual(main(), 0)
                        report = json.loads(stdout.getvalue())
                        self.assertEqual(stderr.getvalue(), "")
                        self.assertEqual((report["files"], report["size"]), (0, 0))
                        self.assertEqual(report["extensions"], [])
                        self.assertEqual(report["largest_files"], [])


class FileSortTests(unittest.TestCase):
    def test_name_order_uses_basename_then_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, size in (("z/alpha.txt", 1), ("a/zeta.txt", 5),
                                   ("b/alpha.txt", 3), ("middle.txt", 4)):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * size)
            baseline = scan_folder(root)
            report = scan_folder(root, file_sort="name")
            expected = [str(Path(name)) for name in (
                "b/alpha.txt", "z/alpha.txt", "middle.txt", "a/zeta.txt"
            )]
            self.assertEqual([item.path for item in report.largest_files], expected)
            self.assertEqual(report, replace(baseline, largest_files=report.largest_files))

    def test_size_order_and_ties_match_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, size in (("z.txt", 5), ("a.txt", 5), ("middle.txt", 3)):
                (root / name).write_bytes(b"x" * size)
            report = scan_folder(root, file_sort="size")
            self.assertEqual(report, scan_folder(root))
            self.assertEqual([item.path for item in report.largest_files], ["a.txt", "z.txt", "middle.txt"])

    def test_name_sort_keeps_top_n_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, size in (("aaa.txt", 1), ("z.txt", 5), ("b.txt", 3)):
                (root / name).write_bytes(b"x" * size)
            report = scan_folder(root, top=2, file_sort="name")
            self.assertEqual([item.path for item in report.largest_files], ["b.txt", "z.txt"])
            self.assertEqual((report.files, report.size), (3, 9))
            self.assertEqual(scan_folder(root, top=0, file_sort="name").largest_files, [])

    def test_empty_folder_with_name_sort(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(scan_folder(Path(directory), file_sort="name"), scan_folder(Path(directory)))

    def test_invalid_sort_is_rejected(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            build_parser().parse_args(["--file-sort", "count"])
        self.assertEqual(error.exception.code, 2)
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "--file-sort"):
            scan_folder(Path(directory), file_sort="count")

    def test_cli_combines_with_filters_and_extension_sort(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            for name, size in (("a.txt", 1024), ("z.bin", 2048), ("small.txt", 1), ("skip.log", 3000)):
                (root / name).write_bytes(b"x" * size)
            (root / "cache").mkdir()
            (root / "cache" / "ignored.txt").write_bytes(b"x" * 4000)
            config = Path(directory) / "names.txt"
            config.write_text("cache\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch("sys.argv", [
                "folder-report", str(root), "--file-sort", "name", "--sort-by", "size",
                "--min-size", "1KiB", "--exclude", "*.log", "--exclude-file", str(config), "--json",
            ]), redirect_stdout(stdout):
                self.assertEqual(main(), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual([item["path"] for item in report["largest_files"]], ["a.txt", "z.bin"])
            self.assertEqual([item["extension"] for item in report["extensions"]], [".bin", ".txt"])
            self.assertEqual((report["files"], report["size"]), (2, 3072))


class MinListSizeTests(unittest.TestCase):
    def test_inclusive_threshold_changes_only_the_largest_files_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            (root / "small.txt").write_bytes(b"x" * 999)
            (nested / "boundary.bin").write_bytes(b"x" * 1000)
            (root / "large.bin").write_bytes(b"x" * 1024)
            baseline = scan_folder(root)
            filtered = scan_folder(root, min_list_size=1000)
            self.assertEqual((baseline.files, baseline.size), (3, 3023))
            self.assertEqual(len(baseline.largest_files), 3)
            self.assertEqual(filtered, replace(baseline, largest_files=[
                FileEntry("large.bin", 1024),
                FileEntry(str(Path("nested") / "boundary.bin"), 1000),
            ]))
            self.assertEqual(scan_folder(root, min_list_size=0), baseline)
            self.assertEqual(scan_folder(root, min_list_size=1025), replace(baseline, largest_files=[]))

    def test_empty_folder_preserves_empty_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(scan_folder(root, min_list_size=1000), scan_folder(root))

    def test_decimal_and_binary_units(self) -> None:
        parser = build_parser()
        for value, expected in (
            ("1000", 1000), ("3B", 3), ("1 kb", 1000), ("2MB", 2000000),
            ("1GB", 1000000000), ("1KiB", 1024), ("2MiB", 2 * 1024**2),
            ("1GiB", 1024**3),
        ):
            with self.subTest(value=value):
                self.assertEqual(parser.parse_args(["--min-list-size", value]).min_list_size, expected)

    def test_invalid_inputs_return_argparse_error(self) -> None:
        parser = build_parser()
        for value in ("1XB", "1.5KB", "-1KB"):
            with self.subTest(value=value), redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as error:
                    parser.parse_args([f"--min-list-size={value}"])
                self.assertEqual(error.exception.code, 2)
                self.assertIn("--min-list-size", stderr.getvalue())

    def test_cli_exclusions_and_size_limit_use_unchanged_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "small.txt").write_bytes(b"abc")
            (root / "large.bin").write_bytes(b"x" * 1000)
            (root / "ignored.log").write_bytes(b"x" * 1200)
            (root / "cache").mkdir()
            (root / "cache" / "ignored.bin").write_bytes(b"x" * 1300)
            names = Path(directory) / "excluded.txt"
            names.write_text("cache\n", encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("sys.argv", [
                "folder-report", str(root), "--min-list-size", "1KB", "--exclude", "*.log",
                "--exclude-file", str(names), "--fail-over-size", "1001", "--json",
            ]), redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(main(), 4)
            report = json.loads(stdout.getvalue())
            self.assertIn("Total size 1003 bytes exceeds limit 1001 bytes", stderr.getvalue())
            self.assertEqual((report["files"], report["size"]), (2, 1003))
            self.assertEqual(report["largest_files"], [{"path": "large.bin", "size": 1000}])


class ExcludeFileTests(unittest.TestCase):
    def run_cli(self, root, *options):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["folder-report", str(root), *options]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_reads_utf8_names_comments_blanks_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "names.txt"
            config.write_text("\ufeff# comment\n\n  # indented\n cache \ncache\n한글\nname#tag\n", encoding="utf-8")
            self.assertEqual(read_exclude_directories(config), {"cache", "한글", "name#tag"})

    def test_cli_combines_all_existing_exclusion_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            for relative in ("cache", "nested/cache", "vendor", "from-patterns"):
                folder = root / relative
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "skip.bin").write_bytes(b"12345")
            (root / "nested" / "keep.txt").write_bytes(b"abc")
            (root / "keep.txt").write_bytes(b"abc")
            (root / "skip.log").write_bytes(b"12345")
            config = Path(directory) / "names.txt"
            config.write_text("cache\ncache\n", encoding="utf-8")
            patterns = Path(directory) / "patterns.txt"
            patterns.write_text("from-patterns\n", encoding="utf-8")
            code, stdout, stderr = self.run_cli(
                root, "--exclude-file", str(config), "--exclude-dir", "vendor",
                "--exclude-dir", "cache", "--exclude", "*.log",
                "--exclude-from", str(patterns), "--json",
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            report = json.loads(stdout)
            self.assertEqual((report["files"], report["size"]), (2, 6))
            self.assertEqual(report["extensions"], [{"extension": ".txt", "files": 2, "size": 6}])
            self.assertEqual(len(report["largest_files"]), 2)

    def test_literal_case_sensitive_directory_only_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "cache").write_bytes(b"abc")
            folder = root / "nested" / "cache"
            folder.mkdir(parents=True)
            (folder / "data.txt").write_bytes(b"12345")
            config = Path(directory) / "names.txt"
            for name, expected in (("cache", 1), ("CACHE", 2), ("ca*", 2), ("nested/cache", 2)):
                with self.subTest(name=name):
                    config.write_text(name + "\n", encoding="utf-8")
                    code, stdout, stderr = self.run_cli(root, "--exclude-file", str(config), "--json")
                    self.assertEqual(code, 0)
                    self.assertEqual(stderr, "")
                    self.assertEqual(json.loads(stdout)["files"], expected)

    def test_empty_or_comment_only_list_preserves_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "data.txt").write_bytes(b"abc")
            config = Path(directory) / "names.txt"
            baseline = self.run_cli(root, "--json")
            for contents in ("", "\n# comment\n \n"):
                with self.subTest(contents=contents):
                    config.write_text(contents, encoding="utf-8")
                    self.assertEqual(self.run_cli(root, "--exclude-file", str(config), "--json"), baseline)

    def test_file_errors_stop_before_analysis_and_preserve_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.txt"
            invalid = root / "invalid.txt"
            invalid.write_bytes(b"\xff")
            for config in (missing, invalid, root):
                for option, suffix in (("--csv", "csv"), ("--json-output", "json"), ("--markdown-output", "md")):
                    with self.subTest(config=config, option=option):
                        output = root / f"report.{suffix}"
                        output.write_bytes(b"keep")
                        with patch("folder_report.scan_folder") as scan:
                            code, stdout, stderr = self.run_cli(
                                root, "--exclude-file", str(config), option, str(output), "--force", "--quiet"
                            )
                        self.assertEqual((code, stdout), (2, ""))
                        self.assertIn("--exclude-file: Could not read", stderr)
                        self.assertIn(str(config), stderr)
                        self.assertEqual(output.read_bytes(), b"keep")
                        scan.assert_not_called()
            output = root / "new.json"
            code, _, _ = self.run_cli(root, "--exclude-file", str(missing), "--json-output", str(output))
            self.assertEqual(code, 2)
            self.assertFalse(output.exists())

    def test_unreadable_file_reports_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "names.txt"
            with patch("pathlib.Path.open", side_effect=PermissionError("access denied")), patch(
                "folder_report.scan_folder"
            ) as scan:
                code, stdout, stderr = self.run_cli(directory, "--exclude-file", str(config))
            self.assertEqual((code, stdout), (2, ""))
            self.assertIn("access denied", stderr)
            self.assertIn(str(config), stderr)
            scan.assert_not_called()


class ExcludeDirectoryTests(unittest.TestCase):
    def test_single_directory_is_removed_from_all_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "keep.txt").write_bytes(b"abc")
            (root / "cache").mkdir()
            (root / "cache" / "large.bin").write_bytes(b"x" * 10)
            before = scan_folder(root)
            after = scan_folder(root, exclude_dirs=["cache"])
            self.assertEqual((before.files, before.size), (2, 13))
            self.assertEqual((after.files, after.size), (1, 3))
            self.assertEqual(after.extensions, [ExtensionSummary(".txt", 1, 3)])
            self.assertEqual(after.largest_files, [FileEntry("keep.txt", 3)])

    def test_multiple_and_nested_matching_directories_are_not_walked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("cache", "vendor", "nested/cache", "nested/keep"):
                folder = root / relative
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "data.txt").write_bytes(b"abc")
            visited = []
            original_walk = os.walk

            def walk(*args, **kwargs):
                for entry in original_walk(*args, **kwargs):
                    visited.append(Path(entry[0]).relative_to(root).as_posix())
                    yield entry

            with patch("folder_report.os.walk", side_effect=walk):
                report = scan_folder(root, exclude_dirs=["cache", "vendor"])
            self.assertEqual((report.files, report.size), (1, 3))
            self.assertEqual(set(visited), {".", "nested", "nested/keep"})

    def test_same_named_files_remain_and_matching_is_case_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cache").write_bytes(b"abc")
            (root / "nested").mkdir()
            (root / "nested" / "cache").mkdir()
            (root / "nested" / "cache" / "data.bin").write_bytes(b"12345")
            report = scan_folder(root, exclude_dirs=["cache"])
            self.assertEqual((report.files, report.size), (1, 3))
            self.assertEqual(report.largest_files, [FileEntry("cache", 3)])
            self.assertEqual(scan_folder(root, exclude_dirs=["CACHE"]), scan_folder(root))

    def test_missing_names_patterns_and_paths_do_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "nested" / "cache"
            folder.mkdir(parents=True)
            (folder / "data.txt").write_bytes(b"abc")
            baseline = scan_folder(root)
            for name in ("missing", "ca*", "nested/cache"):
                with self.subTest(name=name):
                    self.assertEqual(scan_folder(root, exclude_dirs=[name]), baseline)

    def test_repeatable_parser_option_and_default(self) -> None:
        self.assertEqual(build_parser().parse_args([]).exclude_dir, [])
        args = build_parser().parse_args(["--exclude-dir", "cache", "--exclude-dir", "vendor"])
        self.assertEqual(args.exclude_dir, ["cache", "vendor"])

    def test_combines_with_hidden_depth_size_and_pattern_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (".git", ".venv"):
                (root / name).mkdir()
                (root / name / "data.txt").write_bytes(b"abc")
            (root / "keep.txt").write_bytes(b"abc")
            (root / "skip.log").write_bytes(b"abc")
            report = scan_folder(
                root, include_hidden=True, exclude_dirs=[".git", ".venv"],
                exclude=["*.log"], min_size=3, max_size=3, max_depth=1,
            )
            self.assertEqual((report.files, report.size), (1, 3))
            self.assertEqual(report.largest_files, [FileEntry("keep.txt", 3)])

    def test_cli_json_csv_markdown_preserve_existing_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "keep.txt").write_bytes(b"abc")
            (root / "cache").mkdir()
            (root / "cache" / "skip.bin").write_bytes(b"12345")
            expected = scan_folder(root, exclude_dirs=["cache"])
            for option, suffix in (("--json", None), ("--csv", "csv"),
                                   ("--json-output", "json"), ("--markdown-output", "md")):
                with self.subTest(option=option):
                    output = Path(directory) / f"report.{suffix}"
                    arguments = ["folder-report", str(root), "--exclude-dir", "cache", option]
                    if suffix:
                        arguments.append(str(output))
                    stdout = io.StringIO()
                    with patch("sys.argv", arguments), redirect_stdout(stdout):
                        self.assertEqual(main(), 0)
                    if option == "--json":
                        self.assertEqual(stdout.getvalue(), render_json(expected) + "\n")
                    else:
                        reference = Path(directory) / f"reference.{suffix}"
                        writer = {"csv": write_csv, "json": write_json, "md": write_markdown}[suffix]
                        writer(expected, reference)
                        self.assertEqual(output.read_bytes(), reference.read_bytes())


class QuietTests(unittest.TestCase):
    def run_cli(self, root, *options):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["folder-report", str(root), *options]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_quiet_runs_analysis_without_terminal_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"abc")
            with patch("folder_report.scan_folder", wraps=scan_folder) as scan:
                result = self.run_cli(root, "--quiet")
            self.assertEqual(result, (0, "", ""))
            scan.assert_called_once()
            self.assertEqual(scan.call_args.args[0], root.resolve())

    def test_quiet_limit_below_equal_and_above_filtered_total(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "keep.txt").write_bytes(b"abc")
            (root / "skip.bin").write_bytes(b"x" * 10)
            for limit, expected in ((4, 0), (3, 0), (2, 4)):
                with self.subTest(limit=limit):
                    code, stdout, stderr = self.run_cli(
                        root, "--quiet", "--extension", "txt", "--fail-over-size", str(limit)
                    )
                    self.assertEqual(code, expected)
                    self.assertEqual(stdout, "")
                    if expected == 4:
                        self.assertIn("Total size 3 bytes exceeds limit 2 bytes", stderr)
                    else:
                        self.assertEqual(stderr, "")

    def test_quiet_suppresses_timing_and_json_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "folder_report.time.perf_counter"
        ) as clock:
            self.assertEqual(self.run_cli(directory, "--quiet", "--json", "--show-time"), (0, "", ""))
            clock.assert_not_called()

    def test_quiet_saves_identical_reports_without_confirmations(self) -> None:
        for option, suffix in (("--csv", "csv"), ("--json-output", "json"),
                               ("--markdown-output", "md")):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.txt").write_bytes(b"abc")
                output = root / f"report.{suffix}"
                baseline = self.run_cli(root, option, str(output))
                self.assertEqual(baseline[0], 0)
                self.assertIn("saved to:", baseline[1])
                expected = output.read_bytes()
                output.unlink()
                result = self.run_cli(root, "--quiet", "--show-time", option, str(output))
                self.assertEqual(result, (0, "", ""))
                self.assertEqual(output.read_bytes(), expected)

    def test_quiet_reports_saved_before_size_failure(self) -> None:
        for option, suffix in (("--csv", "csv"), ("--json-output", "json"),
                               ("--markdown-output", "md")):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.txt").write_bytes(b"abc")
                output = root / f"report.{suffix}"
                code, stdout, stderr = self.run_cli(
                    root, "--quiet", option, str(output), "--fail-over-size", "2"
                )
                self.assertEqual(code, 4)
                self.assertEqual(stdout, "")
                self.assertIn("exceeds limit", stderr)
                self.assertTrue(output.is_file())

    def test_quiet_scan_errors_use_stderr_and_keep_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for options in ((str(root / "missing"),), (str(root), "--min-size", "4", "--max-size", "2")):
                with self.subTest(options=options):
                    code, stdout, stderr = self.run_cli(options[0], *options[1:], "--quiet")
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("Error:", stderr)
            code, stdout, stderr = self.run_cli(root / "missing")
            self.assertEqual(code, 2)
            self.assertIn("Error:", stdout)
            self.assertEqual(stderr, "")

    def test_quiet_save_error_preserves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            output.write_bytes(b"keep")
            code, stdout, stderr = self.run_cli(root, "--quiet", "--json-output", str(output))
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("already exists", stderr)
            self.assertEqual(output.read_bytes(), b"keep")

    def test_quiet_strict_error_retains_priority_and_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            output.write_bytes(b"keep")
            report = replace(scan_folder(root), skipped=["blocked"])
            with patch("folder_report.scan_folder", return_value=report):
                code, stdout, stderr = self.run_cli(
                    root, "--quiet", "--strict", "--show-time", "--fail-over-size", "0",
                    "--json-output", str(output), "--force"
                )
            self.assertEqual(code, 3)
            self.assertEqual(stdout, "")
            self.assertIn("Strict analysis failed", stderr)
            self.assertNotIn("Analysis time", stderr)
            self.assertNotIn("exceeds limit", stderr)
            self.assertEqual(output.read_bytes(), b"keep")

    def test_without_quiet_text_output_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"abc")
            self.assertEqual(self.run_cli(root), (0, render_text(scan_folder(root)) + "\n", ""))


class ShowTimeTests(unittest.TestCase):
    def run_cli(self, root, *options):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["folder-report", str(root), *options]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_reports_scan_duration_after_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"abc")
            events = []
            original_render = render_text

            def clock():
                events.append("clock")
                return 10.0 if len(events) == 1 else 10.125

            def render(report, **kwargs):
                events.append("render")
                return original_render(report, **kwargs)

            with patch("folder_report.time.perf_counter", side_effect=clock), patch(
                "folder_report.render_text", side_effect=render
            ):
                code, stdout, stderr = self.run_cli(root, "--show-time")
            self.assertEqual(code, 0)
            self.assertIn("Files: 1", stdout)
            self.assertNotIn("Analysis time", stdout)
            self.assertEqual(stderr, "Analysis time: 0.125 seconds\n")
            self.assertEqual(events, ["clock", "clock", "render"])

    def test_omitted_option_preserves_output_and_does_not_measure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = render_text(scan_folder(root)) + "\n"
            with patch("folder_report.time.perf_counter") as clock:
                code, stdout, stderr = self.run_cli(root)
            self.assertEqual((code, stdout, stderr), (0, expected, ""))
            clock.assert_not_called()

    def test_empty_folder_can_report_zero_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "folder_report.time.perf_counter", side_effect=[5.0, 5.0]
        ):
            code, stdout, stderr = self.run_cli(directory, "--show-time")
        self.assertEqual(code, 0)
        self.assertEqual(stdout.count("(no files)"), 2)
        self.assertEqual(stderr, "Analysis time: 0.000 seconds\n")

    def test_json_stdout_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"abc")
            baseline = self.run_cli(root, "--json")
            with patch("folder_report.time.perf_counter", side_effect=[0.0, 0.25]):
                code, stdout, stderr = self.run_cli(root, "--json", "--show-time")
            self.assertEqual(code, 0)
            self.assertEqual(stdout, baseline[1])
            self.assertEqual(json.loads(stdout)["files"], 1)
            self.assertEqual(stderr, "Analysis time: 0.250 seconds\n")

    def test_saved_reports_and_confirmation_are_unchanged(self) -> None:
        for option, suffix in (("--csv", "csv"), ("--json-output", "json"),
                               ("--markdown-output", "md")):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.txt").write_bytes(b"abc")
                output = root / f"report.{suffix}"
                baseline = self.run_cli(root, option, str(output))
                expected = output.read_bytes()
                with patch("folder_report.time.perf_counter", side_effect=[0.0, 0.25]):
                    code, stdout, stderr = self.run_cli(
                        root, option, str(output), "--force", "--show-time"
                    )
                self.assertEqual(code, 0)
                self.assertEqual(stdout, baseline[1])
                self.assertEqual(output.read_bytes(), expected)
                self.assertEqual(stderr, "Analysis time: 0.250 seconds\n")

    def test_strict_failure_preserves_output_file_and_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            output.write_bytes(b"existing report")
            report = replace(scan_folder(root), skipped=["blocked"])
            with patch("folder_report.scan_folder", return_value=report), patch(
                "folder_report.time.perf_counter", side_effect=[0.0, 0.25]
            ):
                code, stdout, stderr = self.run_cli(
                    root, "--strict", "--json-output", str(output), "--force", "--show-time"
                )
            self.assertEqual(code, 3)
            self.assertEqual(stdout, "")
            self.assertIn("Strict analysis failed", stderr)
            self.assertNotIn("Analysis time", stderr)
            self.assertEqual(output.read_bytes(), b"existing report")

    def test_save_failure_does_not_print_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "missing" / "report.json"
            code, stdout, stderr = self.run_cli(directory, "--json-output", str(output), "--show-time")
            self.assertEqual(code, 2)
            self.assertIn("Could not save JSON", stderr)
            self.assertNotIn("Analysis time", stderr)
            self.assertFalse(output.exists())

    def test_size_limit_still_returns_four_after_report_and_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"abc")
            code, stdout, stderr = self.run_cli(root, "--json", "--fail-over-size", "0", "--show-time")
            self.assertEqual(code, 4)
            self.assertEqual(json.loads(stdout)["size"], 3)
            self.assertIn("Analysis time:", stderr)
            self.assertIn("exceeds limit", stderr)


class TextOutputTests(unittest.TestCase):
    def test_readable_sizes_and_aligned_columns(self) -> None:
        report = FolderReport(
            "sample", 3, 1573379,
            [ExtensionSummary(".bin", 1, 1572864), ExtensionSummary(".txt", 2, 515)],
            [FileEntry("archive.bin", 1572864), FileEntry("notes.txt", 512), FileEntry("tiny.txt", 3)],
            [],
        )
        self.assertEqual(render_text(report), "\n".join([
            "Folder: sample", "Files: 3", "Total size: 1.5 MiB", "",
            "By extension:", "  Extension  Files     Size", "  ---------  -----  -------",
            "  .bin           1  1.5 MiB", "  .txt           2    515 B", "",
            "Largest files:", "     Size  Path", "  -------  -----------",
            "  1.5 MiB  archive.bin", "    512 B  notes.txt", "      3 B  tiny.txt",
        ]))

    def test_long_extensions_and_large_counts_fit_columns(self) -> None:
        report = FolderReport(
            "sample", 123456, 1024**3,
            [ExtensionSummary(".verylongextension", 123456, 1024**3)],
            [FileEntry("nested/file.verylongextension", 1024**3)], [],
        )
        lines = render_text(report).splitlines()
        header = lines[5]
        row = lines[7]
        self.assertEqual(header.index("Files") + len("Files"), row.index("123456") + 6)
        self.assertEqual(header.index("Size") + len("Size"), len(row))
        self.assertIn(".verylongextension", row)
        self.assertIn("1.0 GiB", row)
        self.assertTrue(lines[-1].endswith("nested/file.verylongextension"))

    def test_size_filter_and_tied_file_order_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skip.txt").write_bytes(b"x")
            for name in ("z.txt", "a.txt"):
                (root / name).write_bytes(b"x" * 1024)
            args = build_parser().parse_args(["--min-size", "1KiB", "--max-size", "1kIb"])
            report = scan_folder(root, min_size=args.min_size, max_size=args.max_size)
        output = render_text(report)
        self.assertEqual(report.files, 2)
        self.assertIn("Total size: 2.0 KiB", output)
        self.assertLess(output.index("a.txt"), output.index("z.txt"))
        self.assertNotIn("skip.txt", output)

    def test_empty_report_omits_table_headers(self) -> None:
        output = render_text(FolderReport("empty", 0, 0, [], [], []))
        self.assertIn("Total size: 0 B", output)
        self.assertEqual(output.count("  (no files)"), 2)
        self.assertNotIn("Extension  Files", output)
        self.assertNotIn("Path", output)


class FormatSizeTests(unittest.TestCase):
    def test_formats_binary_units(self) -> None:
        self.assertEqual(format_size(999), "999 B")
        self.assertEqual(format_size(1536), "1.5 KiB")

    def test_zero_and_binary_unit_boundaries(self) -> None:
        for size, expected in (
            (0, "0 B"), (1023, "1023 B"), (1024, "1.0 KiB"),
            (1024**2, "1.0 MiB"), (1024**3, "1.0 GiB"), (1024**4, "1.0 TiB"),
        ):
            with self.subTest(size=size):
                self.assertEqual(format_size(size), expected)


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


class FailOverSizeTests(unittest.TestCase):
    def run_cli(self, root, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["folder_report.py", str(root), *arguments]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_below_equal_and_above_limit_preserve_text_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"12345")
            for limit, expected_code in ((6, 0), (5, 0), (4, 4), (0, 4)):
                with self.subTest(limit=limit):
                    code, stdout, stderr = self.run_cli(root, "--fail-over-size", str(limit))
                    self.assertEqual(code, expected_code)
                    self.assertIn("Files: 1", stdout)
                    if expected_code == 4:
                        self.assertIn("Total size 5 bytes", stderr)
                        self.assertIn(f"limit {limit} bytes", stderr)
                    else:
                        self.assertEqual(stderr, "")

    def test_empty_folder_at_zero_limit_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, stdout, stderr = self.run_cli(Path(directory), "--fail-over-size", "0")
            self.assertEqual(code, 0)
            self.assertIn("Files: 0", stdout)
            self.assertEqual(stderr, "")

    def test_units_reuse_size_parser(self) -> None:
        for size, expected in (("1kIb", 1024), ("2MiB", 2 * 1024**2),
                               ("3GIB", 3 * 1024**3)):
            with self.subTest(size=size):
                args = build_parser().parse_args(["--fail-over-size", size])
                self.assertEqual(args.fail_over_size, expected)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.bin").write_bytes(b"x" * 1025)
            self.assertEqual(self.run_cli(root, "--fail-over-size", "1KiB")[0], 4)

    def test_invalid_sizes_are_rejected(self) -> None:
        for value in ("-1", "1.5MiB", "2MB", "invalid"):
            with self.subTest(value=value), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as context:
                    build_parser().parse_args(["--fail-over-size", value])
                self.assertEqual(context.exception.code, 2)

    def test_checks_filtered_total_and_keeps_json_stdout_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            for name, size in (("keep.txt", 5), ("small.txt", 1), ("large.txt", 10),
                               ("other.bin", 5), ("excluded.txt", 5), ("config-skip.txt", 5)):
                (root / name).write_bytes(b"x" * size)
            config = Path(directory) / "patterns.txt"
            config.write_text("config-skip.txt\n", encoding="utf-8")
            options = ["--extension", "txt", "--min-size", "2", "--max-size", "6",
                       "--exclude", "excluded.txt", "--exclude-from", str(config), "--json"]
            for limit, expected in ((5, 0), (4, 4)):
                with self.subTest(limit=limit):
                    code, stdout, stderr = self.run_cli(
                        root, *options, "--fail-over-size", str(limit)
                    )
                    report = json.loads(stdout)
                    self.assertEqual(code, expected)
                    self.assertEqual(report["files"], 1)
                    self.assertEqual(report["size"], 5)
                    self.assertEqual(bool(stderr), expected == 4)

    def test_report_files_are_saved_even_when_limit_is_exceeded(self) -> None:
        for option, suffix in (("--csv", "csv"), ("--json-output", "json"),
                               ("--markdown-output", "md")):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.txt").write_bytes(b"12345")
                output = root / f"report.{suffix}"
                code, stdout, stderr = self.run_cli(
                    root, option, str(output), "--fail-over-size", "4"
                )
                self.assertEqual(code, 4)
                self.assertIn("saved to:", stdout)
                self.assertIn("Total size 5 bytes", stderr)
                text = output.read_text(encoding="utf-8")
                if suffix == "json":
                    self.assertEqual(json.loads(text)["size"], 5)
                elif suffix == "csv":
                    self.assertEqual(list(csv.DictReader(io.StringIO(text)))[0]["size_bytes"], "5")
                else:
                    self.assertIn("(5 bytes)", text)

    def test_strict_errors_take_priority_and_preserve_existing_files(self) -> None:
        modes = ([], ["--json"], ["--csv", "report.csv"],
                 ["--json-output", "report.json"], ["--markdown-output", "report.md"])
        for options in modes:
            for existing in (False, True):
                with self.subTest(options=options, existing=existing):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        (root / "data.txt").write_bytes(b"12345")
                        report = replace(scan_folder(root), skipped=[str(root / "blocked")])
                        arguments = list(options)
                        output = None
                        if len(options) == 2:
                            output = root / options[1]
                            arguments[1] = str(output)
                            if existing:
                                output.write_bytes(b"existing report")
                        with patch("folder_report.scan_folder", return_value=report):
                            code, stdout, stderr = self.run_cli(
                                root, *arguments, "--strict", "--force", "--fail-over-size", "0"
                            )
                        self.assertEqual(code, 3)
                        self.assertEqual(stdout, "")
                        self.assertIn("Strict analysis failed", stderr)
                        self.assertNotIn("exceeds limit", stderr)
                        if output is not None:
                            if existing:
                                self.assertEqual(output.read_bytes(), b"existing report")
                            else:
                                self.assertFalse(output.exists())

    def test_save_failure_retains_exit_code_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"123")
            code, stdout, stderr = self.run_cli(
                root, "--json-output", str(root / "missing" / "report.json"),
                "--fail-over-size", "0",
            )
            self.assertEqual(code, 2)
            self.assertIn("Could not save JSON", stderr)
            self.assertNotIn("exceeds limit", stderr)


class ExcludeFromTests(unittest.TestCase):
    def test_reads_utf8_patterns_and_ignores_blanks_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "patterns.txt"
            config.write_text(
                "\ufeff# comment\n\n  # indented comment\n  *.log  \n한글/\nname#tag.txt\n",
                encoding="utf-8",
            )

            self.assertEqual(
                read_exclude_patterns([config]), ["*.log", "한글/", "name#tag.txt"]
            )

    def test_repeated_files_combine_with_exclude_and_filter_all_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "keep.txt").write_bytes(b"123")
            (root / "app.log").write_bytes(b"12345")
            (root / "cache.tmp").write_bytes(b"123456")
            dependency = root / "node_modules"
            dependency.mkdir()
            (dependency / "large.bin").write_bytes(b"x" * 10)
            first = Path(directory) / "first.txt"
            second = Path(directory) / "second.txt"
            first.write_text("# comment\n\n*.log\n", encoding="utf-8")
            second.write_text("node_modules\n", encoding="utf-8")
            stdout = io.StringIO()

            with patch("sys.argv", [
                "folder_report.py", str(root), "--exclude-from", str(first),
                "--exclude-from", str(second), "--exclude", "*.tmp", "--json",
            ]), redirect_stdout(stdout):
                code = main()

            self.assertEqual(code, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["files"], 1)
            self.assertEqual(result["size"], 3)
            self.assertEqual(result["extensions"], [
                {"extension": ".txt", "files": 1, "size": 3}
            ])
            self.assertEqual(result["largest_files"], [{"path": "keep.txt", "size": 3}])

    def test_parser_accepts_repeated_pattern_files(self) -> None:
        args = build_parser().parse_args(
            [".", "--exclude-from", "first.txt", "--exclude-from", "second.txt"]
        )
        self.assertEqual(args.exclude_from, [Path("first.txt"), Path("second.txt")])

    def test_empty_pattern_file_preserves_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "patterns.txt"
            config.write_text("# only comments\n\n", encoding="utf-8")
            patterns = read_exclude_patterns([config])
            self.assertEqual(patterns, [])
            self.assertEqual(scan_folder(root, exclude=patterns), scan_folder(root))

    def test_unreadable_pattern_files_fail_before_scan_or_report_save(self) -> None:
        for failure in ("missing", "permission", "invalid-utf8"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / "patterns.txt"
                if failure == "invalid-utf8":
                    config.write_bytes(b"\xff\xfe")
                output = root / "report.json"
                original = b"existing report"
                output.write_bytes(original)
                original_open = Path.open

                def fake_open(path, *args, **kwargs):
                    if failure == "permission" and path == config:
                        raise PermissionError(13, "access denied", str(path))
                    return original_open(path, *args, **kwargs)

                error = io.StringIO()
                stdout = io.StringIO()
                with patch.object(Path, "open", new=fake_open), patch(
                    "folder_report.scan_folder"
                ) as scanner, patch("sys.argv", [
                    "folder_report.py", directory, "--exclude-from", str(config),
                    "--json-output", str(output), "--force",
                ]), redirect_stderr(error), redirect_stdout(stdout):
                    code = main()

                self.assertEqual(code, 2)
                self.assertIn("--exclude-from", error.getvalue())
                self.assertIn(str(config), error.getvalue())
                self.assertEqual(stdout.getvalue(), "")
                scanner.assert_not_called()
                self.assertEqual(output.read_bytes(), original)


class StrictModeTests(unittest.TestCase):
    output_modes = ((), ("--json",), ("--csv", "report.csv"),
                    ("--json-output", "report.json"),
                    ("--markdown-output", "report.md"))

    def run_analysis(self, root, arguments, deny_access=False):
        """Simulate a file access failure without changing OS permissions."""
        arguments = list(arguments)
        for index, argument in enumerate(arguments):
            if argument in {"--csv", "--json-output", "--markdown-output"}:
                arguments[index + 1] = str(root / arguments[index + 1])
        blocked = root / "blocked.txt"
        original_stat = Path.stat

        def fake_stat(path, *args, **kwargs):
            if deny_access and path == blocked:
                raise PermissionError(13, "access denied", str(path))
            return original_stat(path, *args, **kwargs)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(Path, "stat", new=fake_stat), patch(
            "sys.argv", ["folder_report.py", str(root), *arguments]
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main()
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_successful_strict_analysis_in_all_output_modes(self) -> None:
        for options in self.output_modes:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.txt").write_bytes(b"123")

                code, stdout, stderr = self.run_analysis(root, ["--strict", *options])

                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                if len(options) == 2:
                    self.assertTrue((root / options[1]).is_file())

    def test_file_error_returns_three_without_output_or_report_files(self) -> None:
        for options in self.output_modes:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "blocked.txt").write_bytes(b"123")

                code, stdout, stderr = self.run_analysis(
                    root, ["--strict", *options], deny_access=True
                )

                self.assertEqual(code, 3)
                self.assertEqual(stdout, "")
                self.assertIn("1 path(s) were skipped", stderr)
                self.assertIn("access errors", stderr)
                if len(options) == 2:
                    self.assertFalse((root / options[1]).exists())

    def test_existing_reports_preserved_even_with_force(self) -> None:
        for options in self.output_modes[2:]:
            for force in ([], ["--force"]):
                with self.subTest(options=options, force=force):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        (root / "blocked.txt").write_bytes(b"123")
                        output = root / options[1]
                        original = b"existing report\x00\xff"
                        output.write_bytes(original)

                        code, stdout, stderr = self.run_analysis(
                            root, ["--strict", *options, *force], deny_access=True
                        )

                        self.assertEqual(code, 3)
                        self.assertEqual(output.read_bytes(), original)
                        self.assertEqual(stdout, "")

    def test_non_strict_keeps_partial_reports_in_all_output_modes(self) -> None:
        for options in self.output_modes:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "blocked.txt").write_bytes(b"123")
                (root / "keep.txt").write_bytes(b"12")

                code, stdout, stderr = self.run_analysis(
                    root, list(options), deny_access=True
                )

                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                if len(options) == 2:
                    self.assertTrue((root / options[1]).is_file())
                elif options == ("--json",):
                    report = json.loads(stdout)
                    self.assertEqual(report["files"], 1)
                    self.assertEqual(report["skipped"], [str(root / "blocked.txt")])
                else:
                    self.assertIn("Skipped paths: 1", stdout)

    def test_directory_walk_error_also_fails_strict_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def fake_walk(scan_root, onerror, followlinks):
                yield str(scan_root), [], []
                onerror(PermissionError(13, "access denied", str(root / "blocked")))

            with patch("folder_report.os.walk", side_effect=fake_walk):
                code, stdout, stderr = self.run_analysis(root, ["--strict"])

            self.assertEqual(code, 3)
            self.assertEqual(stdout, "")
            self.assertIn("1 path(s) were skipped", stderr)

    def test_filtered_and_depth_limited_paths_do_not_trigger_strict_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "blocked.txt").write_bytes(b"1")
            (root / "keep.py").write_bytes(b"1234")
            child = root / "child"
            child.mkdir()
            (child / "blocked.txt").write_bytes(b"12")

            code, stdout, stderr = self.run_analysis(
                root,
                ["--strict", "--exclude", "blocked.txt", "--max-depth", "0",
                 "--extension", "py", "--min-size", "2", "--max-size", "5",
                 "--sort-by", "size", "--json"],
                deny_access=True,
            )

            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            report = json.loads(stdout)
            self.assertEqual(report["files"], 1)
            self.assertEqual(report["size"], 4)
            self.assertEqual(report["skipped"], [])


class OutputOverwriteTests(unittest.TestCase):
    outputs = (("--csv", "csv"), ("--json-output", "json"),
               ("--markdown-output", "md"))

    def test_new_files_are_created_in_all_formats(self) -> None:
        for option, suffix in self.outputs:
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.txt").write_bytes(b"123")
                output = root / f"report.{suffix}"
                with patch("sys.argv", [
                    "folder_report.py", directory, option, str(output),
                ]), redirect_stdout(io.StringIO()):
                    exit_code = main()
                self.assertEqual(exit_code, 0)
                self.assertTrue(output.read_bytes())

    def test_existing_files_are_preserved_and_error_explains_force(self) -> None:
        for option, suffix in self.outputs:
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / f"report.{suffix}"
                original = b"original contents\x00\xff"
                output.write_bytes(original)
                error = io.StringIO()
                stdout = io.StringIO()
                with patch("sys.argv", [
                    "folder_report.py", directory, option, str(output),
                ]), redirect_stderr(error), redirect_stdout(stdout):
                    exit_code = main()
                self.assertEqual(exit_code, 2)
                self.assertEqual(output.read_bytes(), original)
                self.assertIn("already exists", error.getvalue())
                self.assertIn("--force", error.getvalue())
                self.assertIn(str(output), error.getvalue())
                self.assertNotIn("saved to:", stdout.getvalue())

    def test_force_overwrites_with_valid_report_in_all_formats(self) -> None:
        for option, suffix in self.outputs:
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.txt").write_bytes(b"123")
                output = root / f"report.{suffix}"
                output.write_bytes(b"old contents" * 100)
                with patch("sys.argv", [
                    "folder_report.py", directory, option, str(output), "--force",
                ]), redirect_stdout(io.StringIO()):
                    exit_code = main()
                self.assertEqual(exit_code, 0)
                text = output.read_text(encoding="utf-8")
                self.assertNotIn("old contents", text)
                if suffix == "json":
                    self.assertEqual(json.loads(text)["files"], 1)
                elif suffix == "csv":
                    self.assertEqual(list(csv.DictReader(io.StringIO(text))), [
                        {"extension": ".txt", "files": "1", "size_bytes": "3"}
                    ])
                else:
                    self.assertIn("- Files: 1", text)

    def test_file_created_at_open_time_is_not_overwritten(self) -> None:
        for writer in (write_csv, write_json, write_markdown):
            with self.subTest(writer=writer.__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report = scan_folder(root)
                output = root / "raced-output"
                original_open = Path.open
                original = b"created by another process"

                def racing_open(path, mode="r", *args, **kwargs):
                    if path == output:
                        with original_open(path, "wb") as competing_file:
                            competing_file.write(original)
                    return original_open(path, mode, *args, **kwargs)

                with patch.object(Path, "open", new=racing_open):
                    with self.assertRaises(FileExistsError):
                        writer(report, output)
                self.assertEqual(output.read_bytes(), original)


class MarkdownOutputTests(unittest.TestCase):
    def test_creates_markdown_with_correct_statistics_and_excludes_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "한글.txt").write_bytes(b"123")
            (root / "other.txt").write_bytes(b"12")
            (root / "image.bin").write_bytes(b"123456")
            output = root / "report.md"
            output.write_text("previous report", encoding="utf-8")

            with patch("sys.argv", [
                "folder_report.py", directory, "--sort-by", "size",
                "--markdown-output", str(output), "--force",
            ]), redirect_stdout(io.StringIO()):
                exit_code = main()

            text = output.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertTrue(text.startswith("# Folder Report\n"))
            self.assertIn("- Files: 3", text)
            self.assertIn("(11 bytes)", text)
            self.assertIn("| &#46;txt | 2 | 5 |", text)
            self.assertIn("| &#46;bin | 1 | 6 |", text)
            self.assertLess(text.index("&#46;bin"), text.index("&#46;txt"))
            self.assertIn("| 한글&#46;txt | 3 |", text)
            self.assertNotIn("| report&#46;md |", text)

    def test_empty_folder_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            text = render_markdown(scan_folder(Path(directory)))

            self.assertIn("- Files: 0", text)
            self.assertIn("(0 bytes)", text)
            self.assertEqual(text.count("(no files)"), 2)

    def test_special_characters_in_real_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "한글[link]`&_.txt").write_bytes(b"123")
            text = render_markdown(scan_folder(root))

            self.assertIn(
                "| 한글&#91;link&#93;&#96;&#38;&#95;&#46;txt | 3 |", text
            )

    def test_paths_cannot_inject_markdown_rows_links_or_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = replace(
                scan_folder(Path(directory)),
                root="root\n# heading",
                largest_files=[FileEntry("[x](url)|`<tag>\\\nrow.txt", 7)],
            )
            text = render_markdown(report)

            self.assertIn("root&#10;&#35; heading", text)
            row = next(line for line in text.splitlines() if "&#91;x&#93;" in line)
            self.assertEqual(row.count("|"), 3)
            self.assertIn("&#124;&#96;&#60;tag&#62;&#92;&#10;row&#46;txt", row)
            self.assertNotIn("<tag>", text)

    def test_rejects_other_output_options(self) -> None:
        for option in (["--json"], ["--json-output", "report.json"],
                       ["--csv", "report.csv"]):
            with self.subTest(option=option):
                error = io.StringIO()
                with redirect_stderr(error), self.assertRaises(SystemExit) as context:
                    build_parser().parse_args(
                        [".", "--markdown-output", "report.md", *option]
                    )
                self.assertEqual(context.exception.code, 2)
                self.assertIn("not allowed with argument", error.getvalue())

    def test_reports_save_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "missing" / "report.md"
            error = io.StringIO()
            with patch("sys.argv", [
                "folder_report.py", directory, "--markdown-output", str(output),
            ]), redirect_stderr(error):
                exit_code = main()

            self.assertEqual(exit_code, 2)
            self.assertIn("Could not save Markdown", error.getvalue())

    def test_works_with_existing_filters_and_depth_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "keep.txt").write_bytes(b"1234")
            (root / "small.txt").write_bytes(b"1")
            (root / "large.txt").write_bytes(b"123456")
            (root / "skip.txt").write_bytes(b"1234")
            (root / "other.bin").write_bytes(b"1234")
            child = root / "child"
            child.mkdir()
            (child / "deep.txt").write_bytes(b"1234")
            output = root / "report.md"
            with patch("sys.argv", [
                "folder_report.py", directory, "--extension", "TXT",
                "--min-size", "2", "--max-size", "5", "--exclude", "skip.txt",
                "--max-depth", "0", "--markdown-output", str(output),
            ]), redirect_stdout(io.StringIO()):
                exit_code = main()

            text = output.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertIn("- Files: 1", text)
            self.assertIn("| keep&#46;txt | 4 |", text)


class CsvOutputTests(unittest.TestCase):
    def test_json_output_creates_utf8_file_with_expected_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "한글.txt").write_bytes(b"123")
            output = root / "report.json"

            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--json-output", str(output)],
            ), redirect_stdout(io.StringIO()):
                exit_code = main()

            raw_json = output.read_bytes()
            result = json.loads(raw_json.decode("utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["files"], 1)
            self.assertEqual(result["size"], 3)
            self.assertEqual(result["largest_files"][0]["path"], "한글.txt")
            self.assertIn("한글.txt".encode("utf-8"), raw_json)

    def test_json_output_matches_existing_json_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"123")

            stdout = io.StringIO()
            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--json"],
            ), redirect_stdout(stdout):
                stdout_exit_code = main()

            output = root / "report.json"
            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--json-output", str(output)],
            ), redirect_stdout(io.StringIO()):
                file_exit_code = main()

            self.assertEqual(stdout_exit_code, 0)
            self.assertEqual(file_exit_code, 0)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                json.loads(stdout.getvalue()),
            )

    def test_parser_rejects_json_output_with_other_output_options(self) -> None:
        for arguments in (
            [".", "--json", "--json-output", "report.json"],
            [".", "--csv", "report.csv", "--json-output", "report.json"],
        ):
            with self.subTest(arguments=arguments):
                error_output = io.StringIO()
                with redirect_stderr(error_output), self.assertRaises(
                    SystemExit
                ) as context:
                    build_parser().parse_args(arguments)

                self.assertEqual(context.exception.code, 2)
                self.assertIn("not allowed with argument", error_output.getvalue())

    def test_main_does_not_include_existing_json_output_in_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"123")
            output = root / "report.json"
            output.write_text('{"old": "report"}', encoding="utf-8")

            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--json-output", str(output), "--force"],
            ), redirect_stdout(io.StringIO()):
                exit_code = main()

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["files"], 1)
            self.assertEqual(
                result["extensions"],
                [{"extension": ".txt", "files": 1, "size": 3}],
            )

    def test_main_reports_json_save_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "missing" / "report.json"
            error_output = io.StringIO()

            with patch(
                "sys.argv",
                ["folder_report.py", directory, "--json-output", str(output)],
            ), redirect_stderr(error_output):
                exit_code = main()

            self.assertEqual(exit_code, 2)
            self.assertIn("Could not save JSON", error_output.getvalue())
            self.assertIn(str(output), error_output.getvalue())

    def test_json_helpers_share_the_same_representation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_bytes(b"123")
            report = scan_folder(root)
            output = root / "report.json"

            write_json(report, output)

            self.assertEqual(output.read_text(encoding="utf-8"), render_json(report))

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
                ["folder_report.py", str(root), "--csv", str(output), "--force"],
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

