"""Validate one UTF-8 JSON file without changing its contents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


def render_summary(data: object) -> str:
    """Describe the root and count only object/array nesting levels."""
    if isinstance(data, dict):
        lines = ["Root type: object", f"Root keys: {len(data)}"]
    elif isinstance(data, list):
        lines = ["Root type: array", f"Root items: {len(data)}"]
    elif isinstance(data, str):
        lines = ["Root type: string"]
    elif isinstance(data, bool):
        lines = ["Root type: boolean"]
    elif data is None:
        lines = ["Root type: null"]
    else:
        lines = ["Root type: number"]

    max_depth = 0
    pending = []
    if isinstance(data, (dict, list)):
        pending.append((data, 1))
    while pending:
        container, depth = pending.pop()
        max_depth = max(max_depth, depth)
        children = container.values() if isinstance(container, dict) else container
        for child in children:
            if isinstance(child, (dict, list)):
                pending.append((child, depth + 1))

    lines.append(f"Max depth: {max_depth}")
    return "\n".join(lines)


def parse_path(expression: str) -> list[str | int]:
    """Parse dot-separated keys and nonnegative bracketed array indices."""
    key = r"[^.\[\]$*?]+"
    index = r"\[-?[0-9]+\]"
    if not re.fullmatch(rf"(?:{key}|{index})(?:\.{key}|{index})*", expression):
        raise ValueError(f"Invalid path syntax: {expression!r}")
    steps: list[str | int] = []
    for match in re.finditer(rf"({key})|\[(-?[0-9]+)\]", expression):
        if match.group(1) is not None:
            steps.append(match.group(1))
        else:
            value = match.group(2)
            if value.startswith("-"):
                raise ValueError(f"Negative array index is not supported: {value}")
            try:
                steps.append(int(value))
            except ValueError as error:
                raise ValueError("Invalid path syntax: array index is too long") from error
    return steps


def resolve_path(data: object, steps: list[str | int]) -> object:
    """Follow parsed keys and indices without modifying the document."""
    current = data
    for step in steps:
        if isinstance(step, str):
            if not isinstance(current, dict):
                raise ValueError(f"Type mismatch: key {step!r} requires an object")
            if step not in current:
                raise ValueError(f"Object key not found: {step!r}")
        else:
            if not isinstance(current, list):
                raise ValueError(f"Type mismatch: index {step} requires an array")
            if step >= len(current):
                raise ValueError(f"Array index out of range: {step} (length {len(current)})")
        current = current[step]
    return current


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="UTF-8 JSON file to validate")
    output_options = parser.add_mutually_exclusive_group()
    output_options.add_argument(
        "--summary", action="store_true", help="show root type, root count, and maximum container depth"
    )
    output_options.add_argument(
        "--path", dest="query_path", metavar="PATH",
        help="print the JSON value at a dot/bracket path, such as users[0].name",
    )
    args = parser.parse_args(argv)

    try:
        with Path(args.path).open(encoding="utf-8") as source:
            data = json.load(source)
    except json.JSONDecodeError as error:
        print(
            f"Invalid JSON: {args.path} (line {error.lineno}, column {error.colno}): {error.msg}",
            file=sys.stderr,
        )
        return 1
    except UnicodeDecodeError as error:
        print(f"Cannot read JSON: {args.path}: invalid UTF-8 ({error.reason})", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"Cannot read JSON: {args.path}: {error}", file=sys.stderr)
        return 2
    except (RecursionError, ValueError) as error:
        print(f"Cannot validate JSON: {args.path}: {error}", file=sys.stderr)
        return 2

    if args.query_path is not None:
        try:
            value = resolve_path(data, parse_path(args.query_path))
            output = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (ValueError, RecursionError) as error:
            print(f"Path error: {error}", file=sys.stderr)
            return 2
        print(output)
        return 0

    print(f"Valid JSON: {args.path}")
    if args.summary:
        print(render_summary(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
