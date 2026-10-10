"""Summarize file counts and sizes for a directory tree."""

from __future__ import annotations

import argparse
import json
import os
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
) -> FolderReport:
    """Return a report for regular files below *root* without following links."""
    root = root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Folder not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")
    if top < 0:
        raise ValueError("top must be zero or greater")
    exclude_patterns = tuple(exclude)

    grouped: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    entries: list[FileEntry] = []
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

            extension = _extension_for(path)
            grouped[extension][0] += 1
            grouped[extension][1] += size
            entries.append(FileEntry(str(path.relative_to(root)), size))

    extensions = [
        ExtensionSummary(extension, values[0], values[1])
        for extension, values in sorted(grouped.items())
    ]
    largest_files = sorted(entries, key=lambda entry: (-entry.size, entry.path))[:top]

    return FolderReport(
        root=str(root),
        files=len(entries),
        size=sum(entry.size for entry in entries),
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize file counts and sizes in a folder."
    )
    parser.add_argument("path", nargs="?", default=".", help="folder to scan (default: current folder)")
    parser.add_argument("--top", type=int, default=5, help="number of largest files to show")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
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
    try:
        report = scan_folder(
            Path(args.path),
            top=args.top,
            include_hidden=args.include_hidden,
            exclude=args.exclude,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        print(f"Error: {error}")
        return 2

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

