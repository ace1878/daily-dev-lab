"""Verify a built wheel in a temporary virtual environment outside the repository."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import venv


def verify_wheel(wheel: Path) -> None:
    wheel = wheel.resolve(strict=True)
    # Do not inherit paths that could make the source checkout importable.
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONIOENCODING"] = "utf-8"

    with tempfile.TemporaryDirectory(prefix="folder-report-wheel-") as directory:
        workspace = Path(directory).resolve()
        virtualenv = workspace / "venv"
        venv.EnvBuilder(with_pip=True).create(virtualenv)
        executables = virtualenv / ("Scripts" if os.name == "nt" else "bin")
        python = executables / ("python.exe" if os.name == "nt" else "python")
        cli = executables / ("folder-report.exe" if os.name == "nt" else "folder-report")

        def run(*command: str) -> str:
            return subprocess.run(
                command, cwd=workspace, env=environment, check=True,
                capture_output=True, text=True, encoding="utf-8",
            ).stdout

        run(str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel))
        installed_module = Path(run(
            str(python), "-I", "-c",
            "import folder_report; print(folder_report.__file__)",
        ).strip()).resolve()
        if not installed_module.is_relative_to(virtualenv.resolve()):
            raise RuntimeError(f"Module was not loaded from the wheel environment: {installed_module}")

        help_text = run(str(cli), "--help")
        if "--json" not in help_text or "--exclude-from" not in help_text:
            raise RuntimeError("Installed CLI help is missing expected options")

        fixture = workspace / "data"
        fixture.mkdir()
        (fixture / "notes.txt").write_bytes(b"abc")
        nested = fixture / "nested"
        nested.mkdir()
        (nested / "data.bin").write_bytes(b"12345")
        report = json.loads(run(str(cli), str(fixture), "--json"))
        if (
            report["files"] != 2 or report["size"] != 8
            or report["extensions"] != [
                {"extension": ".bin", "files": 1, "size": 5},
                {"extension": ".txt", "files": 1, "size": 3},
            ]
            or report["largest_files"] != [
                {"path": str(Path("nested") / "data.bin"), "size": 5},
                {"path": "notes.txt", "size": 3},
            ]
            or report["skipped"] != []
        ):
            raise RuntimeError(f"Unexpected installed CLI analysis result: {report}")
        print(f"PASS: {wheel.name}: isolated installation, import, --help, 2 files / 8 bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", type=Path, help="wheel to verify (default: one dist/daily_dev_lab-*.whl)")
    args = parser.parse_args()
    if args.wheel is None:
        wheels = sorted(Path("dist").glob("daily_dev_lab-*.whl"))
        if len(wheels) != 1:
            parser.error("expected exactly one dist/daily_dev_lab-*.whl; pass a wheel path explicitly")
        args.wheel = wheels[0]
    verify_wheel(args.wheel)


if __name__ == "__main__":
    main()
