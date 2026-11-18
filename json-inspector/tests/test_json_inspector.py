import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "json_inspector.py"


class JsonInspectorTests(unittest.TestCase):
    def run_cli(self, *arguments):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotIn("Traceback", result.stderr)
        return result

    def test_valid_object_and_original_contents_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            original = json.dumps({"message": "안녕하세요", "count": 3}, ensure_ascii=False).encode("utf-8")
            path.write_bytes(original)
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, f"Valid JSON: {path}\n")
            self.assertEqual(result.stderr, "")
            self.assertEqual(path.read_bytes(), original)

    def test_valid_array(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "array.json"
            path.write_text('[1, "two", null, true]', encoding="utf-8")
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, f"Valid JSON: {path}\n")
            self.assertEqual(result.stderr, "")

    def test_syntax_error_includes_reason_line_and_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            original = b'{"value":\n}'
            path.write_bytes(original)
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr,
                f"Invalid JSON: {path} (line 2, column 1): Expecting value\n",
            )
            self.assertEqual(path.read_bytes(), original)

    def test_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn(f"Cannot read JSON: {path}:", result.stderr)
            self.assertFalse(path.exists())

    def test_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "encoding.json"
            path.write_bytes(b'{"text": "\xff"}')
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn(f"Cannot read JSON: {path}: invalid UTF-8", result.stderr)

    def test_missing_argument(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("usage:", result.stderr)
        self.assertIn("path", result.stderr)

    def test_extra_argument(self) -> None:
        result = self.run_cli("first.json", "second.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("usage:", result.stderr)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_directory_cannot_be_read_as_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli(directory)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("Cannot read JSON:", result.stderr)

    def test_empty_file_is_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.json"
            path.write_bytes(b"")
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("(line 1, column 1): Expecting value", result.stderr)

if __name__ == "__main__":
    unittest.main()
