import json
import os
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
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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

    def test_summary_is_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            path.write_text('{"values": [1, 2]}', encoding="utf-8")
            result = self.run_cli(path)
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            self.assertEqual(result.stdout, f"Valid JSON: {path}\n")

    def test_object_summary_and_file_bytes_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "object.json"
            original = b' { "name":"Alice", "skills":["Python","SQL"], "active":true }\n'
            path.write_bytes(original)
            result = self.run_cli(path, "--summary")
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            self.assertEqual(result.stdout, (
                f"Valid JSON: {path}\nRoot type: object\nRoot keys: 3\nMax depth: 2\n"
            ))
            self.assertEqual(path.read_bytes(), original)

    def test_root_array_summary(self) -> None:
        for data, depth in (([1, 2, 3], 1), ([1, {}, ["value"]], 2)):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "array.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                result = self.run_cli(path, "--summary")
                self.assertEqual((result.returncode, result.stderr), (0, ""))
                self.assertEqual(result.stdout, (
                    f"Valid JSON: {path}\nRoot type: array\nRoot items: 3\nMax depth: {depth}\n"
                ))

    def test_empty_containers_have_depth_one(self) -> None:
        for data, root_type, count_label in (({}, "object", "keys"), ([], "array", "items")):
            with self.subTest(root_type=root_type), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "empty.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                result = self.run_cli(path, "--summary")
                self.assertEqual((result.returncode, result.stderr), (0, ""))
                self.assertEqual(result.stdout, (
                    f"Valid JSON: {path}\nRoot type: {root_type}\nRoot {count_label}: 0\nMax depth: 1\n"
                ))

    def test_primitive_summaries_have_depth_zero_and_no_count(self) -> None:
        for data, root_type in (("hello", "string"), (0, "number"), (1.25, "number"),
                                (True, "boolean"), (False, "boolean"), (None, "null")):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "primitive.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                result = self.run_cli(path, "--summary")
                self.assertEqual((result.returncode, result.stderr), (0, ""))
                self.assertEqual(result.stdout, (
                    f"Valid JSON: {path}\nRoot type: {root_type}\nMax depth: 0\n"
                ))

    def test_maximum_depth_across_mixed_branches_counts_only_containers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.json"
            data = {"deep": [{"child": [{"leaf": {}}]}], "shallow": [True, 1, "x", None]}
            path.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_cli(path, "--summary")
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            self.assertEqual(result.stdout, (
                f"Valid JSON: {path}\nRoot type: object\nRoot keys: 2\nMax depth: 6\n"
            ))

    def test_invalid_json_with_summary_keeps_original_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            original = b'{"value":\n}'
            path.write_bytes(original)
            before = self.run_cli(path)
            result = self.run_cli(path, "--summary")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, before.stderr)
            self.assertEqual(path.read_bytes(), original)

    def test_read_errors_with_summary_keep_original_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "encoding.json"
            invalid.write_bytes(b"\xff")
            for path in (root / "missing.json", invalid, root):
                with self.subTest(path=path):
                    before = self.run_cli(path)
                    result = self.run_cli(path, "--summary")
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, before.stderr)

    def assert_path_result(self, data, expression, expected):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            original = json.dumps(data, ensure_ascii=False).encode("utf-8")
            path.write_bytes(original)
            result = self.run_cli(path, "--path", expression)
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            self.assertEqual(result.stdout, json.dumps(expected, ensure_ascii=False) + "\n")
            self.assertEqual(json.loads(result.stdout), expected)
            self.assertEqual(path.read_bytes(), original)

    def test_path_single_object_key(self) -> None:
        self.assert_path_result({"user": {"name": "Alice"}}, "user", {"name": "Alice"})

    def test_path_nested_object_key(self) -> None:
        self.assert_path_result({"user": {"name": "Alice"}}, "user.name", "Alice")

    def test_path_array_index(self) -> None:
        self.assert_path_result({"skills": ["Python", "SQL"]}, "skills[0]", "Python")

    def test_path_mixed_object_and_array(self) -> None:
        self.assert_path_result({"users": [{"name": "Alice"}]}, "users[0].name", "Alice")

    def test_path_consecutive_array_indices(self) -> None:
        self.assert_path_result({"matrix": [[1, 2], [3, 4]]}, "matrix[0][1]", 2)

    def test_path_root_array(self) -> None:
        self.assert_path_result([{"name": "Alice"}], "[0].name", "Alice")

    def test_path_primitive_values_are_json(self) -> None:
        for value in ("안녕하세요", 21, 1.25, True, False, None):
            with self.subTest(value=value):
                self.assert_path_result({"value": value}, "value", value)

    def test_path_container_values_are_json(self) -> None:
        for value in ({"name": "Alice"}, [1, True, None], {}, []):
            with self.subTest(value=value):
                self.assert_path_result({"value": value}, "value", value)

    def test_path_lookup_failures_have_distinct_errors_and_empty_stdout(self) -> None:
        data = {"users": [{"name": "Alice"}], "number": 21, "object": {}}
        cases = (
            ("missing", "Object key not found"),
            ("users[0].missing", "Object key not found"),
            ("users[1]", "Array index out of range"),
            ("users[999999999999999999999999]", "Array index out of range"),
            ("number.name", "Type mismatch"),
            ("number[0]", "Type mismatch"),
            ("object[0]", "Type mismatch"),
            ("users.name", "Type mismatch"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            original = json.dumps(data).encode("utf-8")
            path.write_bytes(original)
            for expression, message in cases:
                with self.subTest(expression=expression):
                    result = self.run_cli(path, "--path", expression)
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertIn(message, result.stderr)
                    self.assertEqual(path.read_bytes(), original)

    def test_invalid_path_syntax_and_negative_indices(self) -> None:
        cases = (
            "", ".users", "users.", "users..name", "users[]", "users[",
            "users[0", "users[0]name", "users.[0]", "users[1.0]", "users[+1]",
            "$.users", "users[*]", "users[0:1]", "users[?(@.active)]", "users['name']",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            path.write_text('{"users": []}', encoding="utf-8")
            for expression in cases:
                with self.subTest(expression=expression):
                    result = self.run_cli(path, "--path", expression)
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertIn("Invalid path syntax", result.stderr)
            for expression in ("users[-1]", "[-1]", "users[-0]"):
                with self.subTest(expression=expression):
                    result = self.run_cli(path, "--path", expression)
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertIn("Negative array index", result.stderr)

    def test_path_and_summary_are_mutually_exclusive(self) -> None:
        result = self.run_cli("sample.json", "--path", "user", "--summary")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("not allowed with argument", result.stderr)
        self.assertIn("--path", result.stderr)
        self.assertIn("--summary", result.stderr)

    def test_invalid_json_with_path_preserves_parsing_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            original = b'{"value":\n}'
            path.write_bytes(original)
            baseline = self.run_cli(path)
            for expression in ("value", "users["):
                with self.subTest(expression=expression):
                    result = self.run_cli(path, "--path", expression)
                    self.assertEqual((result.returncode, result.stdout), (1, ""))
                    self.assertEqual(result.stderr, baseline.stderr)
                    self.assertEqual(path.read_bytes(), original)

    def test_read_errors_with_path_preserve_existing_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "encoding.json"
            invalid.write_bytes(b"\xff")
            for path in (root / "missing.json", invalid, root):
                with self.subTest(path=path):
                    baseline = self.run_cli(path)
                    result = self.run_cli(path, "--path", "value")
                    self.assertEqual((result.returncode, result.stdout), (2, ""))
                    self.assertEqual(result.stderr, baseline.stderr)

    def test_path_does_not_emit_non_json_numeric_constants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nonfinite.json"
            path.write_text('{"value": NaN}', encoding="utf-8")
            result = self.run_cli(path, "--path", "value")
            self.assertEqual((result.returncode, result.stdout), (2, ""))
            self.assertIn("JSON compliant", result.stderr)

    def test_help_lists_summary(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertIn("--summary", result.stdout)


if __name__ == "__main__":
    unittest.main()
