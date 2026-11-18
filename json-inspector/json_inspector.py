"""Validate one UTF-8 JSON file without changing its contents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="UTF-8 JSON file to validate")
    args = parser.parse_args(argv)

    try:
        with Path(args.path).open(encoding="utf-8") as source:
            json.load(source)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
