"""Validate one UTF-8 JSON file without changing its contents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="UTF-8 JSON file to validate")
    parser.add_argument(
        "--summary", action="store_true", help="show root type, root count, and maximum container depth"
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

    print(f"Valid JSON: {args.path}")
    if args.summary:
        print(render_summary(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
