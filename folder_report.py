"""Summarize file counts and sizes for a directory tree."""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import os
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable


NO_EXTENSION = "[no extension]"


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


def scan_folder(
    root: Path,
    top: int = 5,
    include_hidden: bool = False,
    exclude: Iterable[str] = (),
    min_size: int = 0,
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
    exclude_patterns = tuple(exclude)

    grouped: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    largest_heap: list[_HeapFile] = []
    file_count = 0
    total_size = 0
    skipped: list[str] = []

    def on_error(error: OSError) -> None:
        skipped.append(str(error.filename or error))

    for current, directories, filenames in os.walk(root, onerror=on_error, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name
            for name in directories
            if not (current_path / name).is_symlink()
            and (include_hidden or (not name.startswith(".") and name != "__pycache__"))
            and not _is_excluded(current_path / name, root, exclude_patterns)
        ]

        for filename in filenames:
            path = current_path / filename
            if not include_hidden and filename.startswith("."):
                continue
            if _is_excluded(path, root, exclude_patterns):
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

            extension = _extension_for(path)
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

    extensions = [
        ExtensionSummary(extension, values[0], values[1])
        for extension, values in sorted(grouped.items())
    ]
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
        extensions=extensions,
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


def render_text(report: FolderReport) -> str:
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

    return "\n".join(lines)


def write_csv(report: FolderReport, output: Path) -> None:
    """Write extension statistics to a CSV file."""
    with output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["extension", "files", "size_bytes"])
        for item in report.extensions:
            writer.writerow([item.extension, item.files, item.size])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize file counts and sizes in a folder."
    )
    parser.add_argument("path", nargs="?", default=".", help="folder to scan (default: current folder)")
    parser.add_argument("--top", type=int, default=5, help="number of largest files to show")
    parser.add_argument(
        "--min-size",
        type=int,
        default=0,
        metavar="BYTES",
        help="include only files at least this many bytes",
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scan_root = Path(args.path).expanduser().resolve()
    exclude_patterns = list(args.exclude)
    csv_output = args.csv.expanduser().resolve() if args.csv else None
    if csv_output:
        try:
            exclude_patterns.append(csv_output.relative_to(scan_root).as_posix())
        except ValueError:
            pass

    try:
        report = scan_folder(
            scan_root,
            top=args.top,
            include_hidden=args.include_hidden,
            exclude=exclude_patterns,
            min_size=args.min_size,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        print(f"Error: {error}")
        return 2

    if csv_output:
        try:
            write_csv(report, csv_output)
        except OSError as error:
            print(f"Error: Could not save CSV to {csv_output}: {error}", file=sys.stderr)
            return 2
        print(f"CSV saved to: {csv_output}")
    elif args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

