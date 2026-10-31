"""Summarize file counts and sizes for a directory tree."""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import os
import re
import string
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, TextIO


NO_EXTENSION = "[no extension]"
SIZE_UNITS = {
    "": 1,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
}


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int


@dataclass(frozen=True)
class _HeapFile:
    """Heap item ordered with the least desirable top-file candidate first."""

    path: str
    size: int

    def __lt__(self, other: _HeapFile) -> bool:
        if self.size != other.size:
            return self.size < other.size
        return self.path > other.path


@dataclass(frozen=True)
class ExtensionSummary:
    extension: str
    files: int
    size: int


@dataclass(frozen=True)
class FolderReport:
    root: str
    files: int
    size: int
    extensions: list[ExtensionSummary]
    largest_files: list[FileEntry]
    skipped: list[str]


def _extension_for(path: Path) -> str:
    return path.suffix.lower() or NO_EXTENSION


def _is_excluded(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
    """Return whether a path's name or root-relative path matches a pattern."""
    relative_path = path.relative_to(root).as_posix()
    return any(
        fnmatch(path.name, pattern) or fnmatch(relative_path, pattern)
        for pattern in patterns
    )


def read_exclude_patterns(paths: Iterable[Path]) -> list[str]:
    """Read one pattern per line, ignoring blank lines and full-line comments."""
    patterns: list[str] = []
    for path in paths:
        path = path.expanduser()
        try:
            with path.open(encoding="utf-8-sig") as pattern_file:
                for line in pattern_file:
                    pattern = line.strip()
                    if pattern and not pattern.startswith("#"):
                        patterns.append(pattern)
        except (OSError, UnicodeError) as error:
            raise ValueError(f"--exclude-from: Could not read {path}: {error}") from error
    return patterns


def _normalize_extensions(extensions: Iterable[str]) -> set[str]:
    """Return extensions in lowercase with one leading dot."""
    normalized: set[str] = set()
    for value in extensions:
        name = value.strip()
        if name.startswith("."):
            name = name[1:]
        if not name or "." in name or "/" in name or "\\" in name:
            raise ValueError(
                "--extension must be a single extension name, such as txt or .txt"
            )
        normalized.add(f".{name.lower()}")
    return normalized


def parse_size(value: str) -> int:
    """Parse a whole-number byte size with an optional binary unit."""
    match = re.fullmatch(r"([+-]?\d+)\s*(KiB|MiB|GiB)?", value.strip(), re.IGNORECASE)
    if not match:
        raise argparse.ArgumentTypeError(
            "size must be a whole number optionally followed by KiB, MiB, or GiB"
        )

    amount = int(match.group(1))
    if amount < 0:
        raise argparse.ArgumentTypeError("size must be zero or greater")
    unit = (match.group(2) or "").lower()
    return amount * SIZE_UNITS[unit]


def scan_folder(
    root: Path,
    top: int = 5,
    include_hidden: bool = False,
    exclude: Iterable[str] = (),
    min_size: int = 0,
    max_size: int | None = None,
    sort_by: str = "extension",
    extensions: Iterable[str] = (),
    max_depth: int | None = None,
) -> FolderReport:
    """Return a report for regular files below *root* without following links."""
    root = root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Folder not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")
    if top < 0:
        raise ValueError("top must be zero or greater")
    if min_size < 0:
        raise ValueError("--min-size must be zero or greater")
    if max_size is not None and max_size < 0:
        raise ValueError("--max-size must be zero or greater")
    if max_size is not None and min_size > max_size:
        raise ValueError("--min-size must not be greater than --max-size")
    if max_depth is not None and max_depth < 0:
        raise ValueError("--max-depth must be zero or greater")
    if sort_by not in {"extension", "size", "count"}:
        raise ValueError("--sort-by must be one of: extension, size, count")
    exclude_patterns = tuple(exclude)
    included_extensions = _normalize_extensions(extensions)

    grouped: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    largest_heap: list[_HeapFile] = []
    file_count = 0
    total_size = 0
    skipped: list[str] = []

    def on_error(error: OSError) -> None:
        skipped.append(str(error.filename or error))

    for current, directories, filenames in os.walk(root, onerror=on_error, followlinks=False):
        current_path = Path(current)
        current_depth = len(current_path.relative_to(root).parts)
        if max_depth is not None and current_depth >= max_depth:
            directories.clear()
        else:
            directories[:] = [
                name
                for name in directories
                if not (current_path / name).is_symlink()
                and (
                    include_hidden
                    or (not name.startswith(".") and name != "__pycache__")
                )
                and not _is_excluded(current_path / name, root, exclude_patterns)
            ]

        for filename in filenames:
            path = current_path / filename
            if not include_hidden and filename.startswith("."):
                continue
            if _is_excluded(path, root, exclude_patterns):
                continue
            extension = _extension_for(path)
            if included_extensions and extension not in included_extensions:
                continue
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                size = path.stat().st_size
            except OSError:
                skipped.append(str(path))
                continue
            if size < min_size:
                continue
            if max_size is not None and size > max_size:
                continue

            grouped[extension][0] += 1
            grouped[extension][1] += size
            file_count += 1
            total_size += size

            if top:
                candidate = _HeapFile(str(path.relative_to(root)), size)
                if len(largest_heap) < top:
                    heapq.heappush(largest_heap, candidate)
                elif largest_heap[0] < candidate:
                    heapq.heapreplace(largest_heap, candidate)

    extension_summaries = [
        ExtensionSummary(extension, values[0], values[1])
        for extension, values in grouped.items()
    ]
    if sort_by == "size":
        extension_summaries.sort(key=lambda item: (-item.size, item.extension))
    elif sort_by == "count":
        extension_summaries.sort(key=lambda item: (-item.files, item.extension))
    else:
        extension_summaries.sort(key=lambda item: item.extension)
    largest_files = [
        FileEntry(entry.path, entry.size)
        for entry in sorted(
            largest_heap,
            key=lambda entry: (-entry.size, entry.path),
        )
    ]

    return FolderReport(
        root=str(root),
        files=file_count,
        size=total_size,
        extensions=extension_summaries,
        largest_files=largest_files,
        skipped=sorted(set(skipped)),
    )


def format_size(size: int) -> str:
    """Format a byte count using binary units."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def render_text(report: FolderReport, show_skipped: bool = False) -> str:
    lines = [
        f"Folder: {report.root}",
        f"Files: {report.files}",
        f"Total size: {format_size(report.size)}",
        "",
        "By extension:",
    ]

    if report.extensions:
        for item in report.extensions:
            lines.append(f"  {item.extension:<15} {item.files:>5} files  {format_size(item.size):>10}")
    else:
        lines.append("  (no files)")

    lines.extend(["", "Largest files:"])
    if report.largest_files:
        for item in report.largest_files:
            lines.append(f"  {format_size(item.size):>10}  {item.path}")
    else:
        lines.append("  (no files)")

    if report.skipped:
        lines.extend(["", f"Skipped paths: {len(report.skipped)}"])
        if show_skipped:
            lines.extend(f"  {path}" for path in sorted(report.skipped))

    return "\n".join(lines)


def _open_output(output: Path, force: bool = False, newline: str | None = None) -> TextIO:
    """Create exclusively unless overwriting was explicitly requested."""
    try:
        return output.open("w" if force else "x", encoding="utf-8", newline=newline)
    except FileExistsError as error:
        raise FileExistsError(
            f"Output file already exists: {output}. Use --force to overwrite."
        ) from error


def write_csv(report: FolderReport, output: Path, force: bool = False) -> None:
    """Write extension statistics to a CSV file."""
    with _open_output(output, force=force, newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["extension", "files", "size_bytes"])
        for item in report.extensions:
            writer.writerow([item.extension, item.files, item.size])


def render_json(report: FolderReport) -> str:
    """Return the report using the command's JSON representation."""
    return json.dumps(asdict(report), ensure_ascii=False, indent=2)


def write_json(report: FolderReport, output: Path, force: bool = False) -> None:
    """Write the complete report to a UTF-8 JSON file."""
    with _open_output(output, force=force) as json_file:
        json_file.write(render_json(report))


def _markdown_text(value: str) -> str:
    """Keep user-supplied text literal inside Markdown paragraphs and tables."""
    return "".join(
        f"&#{ord(character)};"
        if character in string.punctuation or ord(character) < 32
        else character
        for character in value
    )


def render_markdown(report: FolderReport) -> str:
    """Render the existing report data as Markdown tables."""
    lines = [
        "# Folder Report",
        "",
        f"- Folder: {_markdown_text(report.root)}",
        f"- Files: {report.files}",
        f"- Total size: {format_size(report.size)} ({report.size} bytes)",
        f"- Skipped paths: {len(report.skipped)}",
        "",
        "## By extension",
        "",
    ]
    if report.extensions:
        lines.extend(["| Extension | Files | Size (bytes) |", "| --- | ---: | ---: |"])
        lines.extend(
            f"| {_markdown_text(item.extension)} | {item.files} | {item.size} |"
            for item in report.extensions
        )
    else:
        lines.append("(no files)")
    lines.extend(["", "## Largest files", ""])
    if report.largest_files:
        lines.extend(["| Path | Size (bytes) |", "| --- | ---: |"])
        lines.extend(
            f"| {_markdown_text(item.path)} | {item.size} |"
            for item in report.largest_files
        )
    else:
        lines.append("(no files)")
    return "\n".join(lines) + "\n"


def write_markdown(report: FolderReport, output: Path, force: bool = False) -> None:
    """Save a Markdown report using UTF-8."""
    with _open_output(output, force=force) as markdown_file:
        markdown_file.write(render_markdown(report))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize file counts and sizes in a folder."
    )
    parser.add_argument("path", nargs="?", default=".", help="folder to scan (default: current folder)")
    parser.add_argument("--top", type=int, default=5, help="number of largest files to show")
    parser.add_argument(
        "--min-size",
        type=parse_size,
        default=0,
        metavar="SIZE",
        help="include only files at least this size (bytes, KiB, MiB, or GiB)",
    )
    parser.add_argument(
        "--max-size",
        type=parse_size,
        metavar="SIZE",
        help="include only files at most this size (bytes, KiB, MiB, or GiB)",
    )
    parser.add_argument(
        "--fail-over-size",
        type=parse_size,
        metavar="SIZE",
        help="return exit code 4 if the filtered total size exceeds this limit",
    )
    parser.add_argument(
        "--sort-by",
        choices=("extension", "size", "count"),
        default="extension",
        help="sort extension statistics (default: extension)",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    output_group.add_argument(
        "--csv",
        type=Path,
        metavar="OUTPUT.csv",
        help="save extension statistics as CSV",
    )
    output_group.add_argument(
        "--json-output",
        type=Path,
        metavar="OUTPUT.json",
        help="save the complete report as JSON",
    )
    output_group.add_argument(
        "--markdown-output",
        type=Path,
        metavar="OUTPUT.md",
        help="save the report as Markdown",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="include dotfiles, dot-directories, and __pycache__",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="exclude a file pattern or directory name (repeatable)",
    )
    parser.add_argument(
        "--extension",
        action="append",
        default=[],
        metavar="EXT",
        help="include only this file extension (repeatable)",
    )
    parser.add_argument(
        "--exclude-from",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help="read exclude patterns from a UTF-8 file (repeatable)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        metavar="DEPTH",
        help="limit folder traversal depth (0 scans only the selected folder)",
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="list paths skipped because of access errors",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow overwriting an existing CSV, JSON, or Markdown output file",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail with exit code 3 if any paths were skipped because of access errors",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scan_root = Path(args.path).expanduser().resolve()
    exclude_patterns = list(args.exclude)
    try:
        exclude_patterns.extend(read_exclude_patterns(args.exclude_from))
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    csv_output = args.csv.expanduser().resolve() if args.csv else None
    json_output = args.json_output.expanduser().resolve() if args.json_output else None
    markdown_output = (
        args.markdown_output.expanduser().resolve() if args.markdown_output else None
    )
    output_path = csv_output or json_output or markdown_output
    if output_path:
        try:
            exclude_patterns.append(output_path.relative_to(scan_root).as_posix())
        except ValueError:
            pass

    try:
        report = scan_folder(
            scan_root,
            top=args.top,
            include_hidden=args.include_hidden,
            exclude=exclude_patterns,
            extensions=args.extension,
            max_depth=args.max_depth,
            min_size=args.min_size,
            max_size=args.max_size,
            sort_by=args.sort_by,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        print(f"Error: {error}")
        return 2

    if args.strict and report.skipped:
        print(
            f"Error: Strict analysis failed: {len(report.skipped)} path(s) were skipped "
            "because of access errors. No report was written.",
            file=sys.stderr,
        )
        return 3

    if csv_output:
        try:
            write_csv(report, csv_output, force=args.force)
        except OSError as error:
            print(f"Error: Could not save CSV to {csv_output}: {error}", file=sys.stderr)
            return 2
        print(f"CSV saved to: {csv_output}")
    elif json_output:
        try:
            write_json(report, json_output, force=args.force)
        except OSError as error:
            print(
                f"Error: Could not save JSON to {json_output}: {error}",
                file=sys.stderr,
            )
            return 2
        print(f"JSON saved to: {json_output}")
    elif markdown_output:
        try:
            write_markdown(report, markdown_output, force=args.force)
        except OSError as error:
            print(
                f"Error: Could not save Markdown to {markdown_output}: {error}",
                file=sys.stderr,
            )
            return 2
        print(f"Markdown saved to: {markdown_output}")
    elif args.json:
        print(render_json(report))
    else:
        print(render_text(report, show_skipped=args.show_skipped))
    if args.fail_over_size is not None and report.size > args.fail_over_size:
        print(
            f"Error: Total size {report.size} bytes exceeds limit "
            f"{args.fail_over_size} bytes.",
            file=sys.stderr,
        )
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

